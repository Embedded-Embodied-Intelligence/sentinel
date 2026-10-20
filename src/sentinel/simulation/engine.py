"""Day-by-day execution of a plan under hidden durations and disruptions (spec sections 2-3).

Every day t runs the six steps of spec section 3: (1) realise D1-D3, (2) pause activities with
an absent worker, (3) let the policy decide at a decision epoch, (4) dispatch in order of the
planned start, (5) progress every running activity by one unit of work, (6) close activities
without remaining work; section 3.1 fixes the details. The loop works on the plain lists of
`EngineState`; pydantic models are built only for events, observations and the result.
"""

import heapq
import math
import operator
from bisect import insort
from collections.abc import Sequence
from typing import assert_never

from pydantic import BaseModel, ConfigDict, NonNegativeInt

from sentinel.model.instance import ProjectInstance
from sentinel.model.schedule import Schedule
from sentinel.policies.base import Decision, Noop, Policy
from sentinel.simulation.events import (
    Absence,
    DisruptionParams,
    Event,
    NewActivity,
    NewActivityDraw,
    NewActivitySkipped,
    ScenarioStreams,
    WorkIncrease,
)
from sentinel.simulation.state import (
    DONE,
    PAUSED,
    RUNNING,
    UNSTARTED,
    EngineState,
    InsertedActivity,
    WorkSegment,
)
from sentinel.simulation.uncertainty import PertParams, realised_duration, role_costs


class DayRecord(BaseModel):
    """Trace of one day: activities that progressed and their workers, absent workers, epoch."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    day: NonNegativeInt
    working: tuple[tuple[int, tuple[int, ...]], ...]
    absent: tuple[int, ...]
    epoch: bool


class SimulationResult(BaseModel):
    """Outcome of one run for evaluation, hidden quantities included (spec section 3).

    Activities `0 .. n_original - 1` are the instance's; later ids were inserted by D3. `work`
    is the true duration plus all D2 increases. A truncated run reports `makespan = max_days`
    (right-censored); its unstarted activities have no start.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    seed: NonNegativeInt
    n_original: NonNegativeInt
    starts: tuple[int | None, ...]
    finishes: tuple[int | None, ...]
    work: tuple[NonNegativeInt, ...]
    segments: tuple[WorkSegment, ...]
    makespan: NonNegativeInt
    deadline: NonNegativeInt | None
    deadline_met: bool | None
    total_cost: float
    n_epochs: NonNegativeInt
    events: tuple[Event, ...]
    truncated: bool
    max_days: NonNegativeInt
    trace: tuple[DayRecord, ...] | None = None


def simulate(
    instance: ProjectInstance,
    plan: Schedule,
    policy: Policy,
    seed: int,
    *,
    pert: PertParams,
    disruptions: DisruptionParams,
    deadline: int | None = None,
    review_period: int = 5,
    costs: Sequence[float] | None = None,
    record_trace: bool = False,
) -> SimulationResult:
    """Execute `plan` under `policy` for one replication seed (spec sections 2-3).

    The run ends when the sink completes, or after day `max_days` = 5 D (5 sum p_j without a
    deadline) with `truncated = True`. Decision epochs are the days with a D1-D3 event and the
    days t with t % review_period == 0; a passive policy (see `Policy`) is not consulted there.
    Each worker-day of work costs c_k (default 1.0).
    """
    if len(plan.starts) != instance.n_activities:
        raise ValueError(
            f"plan has {len(plan.starts)} starts but {instance.name} has "
            f"{instance.n_activities} activities"
        )
    if seed < 0:
        raise ValueError(f"seed must be non-negative, got {seed}")
    if deadline is not None and deadline < 0:
        raise ValueError(f"deadline must be non-negative, got {deadline}")
    if review_period < 1:
        raise ValueError(f"review_period must be at least 1, got {review_period}")
    # max_days = ceil(5 D) is 5 D for an integral deadline (spec section 3.1 f).
    if deadline is None:
        max_days = 5 * sum(act.duration for act in instance.activities)
    else:
        max_days = 5 * deadline
    streams = ScenarioStreams(seed, instance, disruptions, pert)
    state = EngineState(
        instance,
        plan,
        streams.durations,
        role_costs(instance, costs),
        pert=pert,
        disruptions=disruptions,
        deadline=deadline,
    )
    events: list[Event] = []
    trace: list[DayRecord] | None = [] if record_trace else None
    returns: dict[int, list[int]] = {}
    shocks = disruptions.lambda_s > 0
    passive = getattr(policy, "passive", False) is True
    status, running, sink = state.status, state.running, state.sink
    work_done, remaining, daily_cost = state.work_done, state.remaining, state.daily_cost
    n_epochs = 0
    for t in range(max_days + 1):
        state.day = t
        # Step 1: disruptions D1-D3 (spec section 2.2).
        absence, to_pause = _absences(state, streams, t, returns, events)
        shocked = shocks and _work_increases(state, streams, t, events)
        draw = streams.new_activity(t)
        inserted = draw is not None and _new_activity(state, t, draw, events)
        # Step 2: pause activities with an absent worker.
        for j in to_pause:
            _pause(state, j, t)
        # Step 3: decision epoch (spec section 3.1 g).
        epoch = absence or shocked or inserted or t % review_period == 0
        if epoch:
            n_epochs += 1
            if not passive:
                _apply(state, policy.decide(state.observe()))
        # Step 4: dispatch.
        _dispatch(state, streams, t, shocks)
        if trace is not None:
            trace.append(_day_record(state, t, epoch))
        if status[sink] == DONE:
            break
        # Steps 5-6: one unit of work per running activity, then close finished ones.
        finished: list[int] = []
        day_cost = 0.0
        for j in running:
            work_done[j] += 1
            remaining[j] -= 1
            day_cost += daily_cost[j]
            if remaining[j] == 0:
                finished.append(j)
        state.cost += day_cost
        for j in finished:
            _finish(state, j, t)

    sink_start = state.start[sink]
    truncated = sink_start is None
    if truncated:
        for j in running:
            segment = WorkSegment(j, state.open_since[j], max_days + 1, state.assigned[j])
            state.segments.append(segment)
    makespan = max_days if sink_start is None else sink_start
    # Built from the engine's own lists, so validation is skipped for speed.
    return SimulationResult.model_construct(
        seed=seed,
        n_original=instance.n_activities,
        starts=tuple(state.start),
        finishes=tuple(state.finish),
        work=tuple(map(operator.add, work_done, remaining)),
        segments=tuple(sorted(state.segments)),
        makespan=makespan,
        deadline=deadline,
        deadline_met=None if deadline is None else (not truncated and makespan <= deadline),
        total_cost=state.cost,
        n_epochs=n_epochs,
        events=tuple(events),
        truncated=truncated,
        max_days=max_days,
        trace=None if trace is None else tuple(trace),
    )


def _absences(
    state: EngineState,
    streams: ScenarioStreams,
    t: int,
    returns: dict[int, list[int]],
    events: list[Event],
) -> tuple[bool, list[int]]:
    """D1: returns of day t, then onsets; returns (any onset, activities to pause in step 2)."""
    present, idle, role, busy = state.present, state.idle, state.role, state.busy
    for w in returns.pop(t, []):
        state.changed = True
        present[w] = True
        state.return_day[w] = -1
        state.absent_since[w] = None
        state.announced[w] = None
        insort(idle[role[w]], w)
    onsets = streams.absence_onsets(t)
    to_pause: list[int] = []
    for w, length, announced in onsets:
        present[w] = False
        state.return_day[w] = t + length
        state.absent_since[w] = t
        state.announced[w] = announced
        returns.setdefault(t + length, []).append(w)
        if busy[w] >= 0:
            to_pause.append(busy[w])
        else:
            idle[role[w]].remove(w)
        events.append(Absence(day=t, worker=w, length=length, announced=announced))
    return bool(onsets), to_pause


def _work_increases(
    state: EngineState, streams: ScenarioStreams, t: int, events: list[Event]
) -> bool:
    """D2: shock every running activity whose work-day counter reached its next shock."""
    # SPEC-Q: activities running at step 1 use check k = e_j (days progressed so far), so a
    # shock never hits an activity's first day and a one-day activity is never shocked.
    shocked = False
    for j in state.running:
        k = state.work_done[j]
        if k != state.next_shock[j]:
            continue
        before = state.remaining[j]
        factor = state.shock_factor[j]
        # ceil(before * F); the tolerance keeps integral products such as 5 * 1.2 integral.
        after = math.ceil(before * factor - 1e-9)
        state.remaining[j] = after
        state.work_increases.append((j, k, factor))
        events.append(
            WorkIncrease(
                day=t,
                activity=j,
                work_done=k,
                factor=factor,
                remaining_before=before,
                remaining_after=after,
            )
        )
        _plan_next_shock(state, streams, j)
        shocked = True
    return shocked


def _plan_next_shock(state: EngineState, streams: ScenarioStreams, j: int) -> None:
    """Look up the next D2 shock of j among its remaining checks e_j + 1 .. e_j + remaining - 1."""
    done = state.work_done[j]
    shock = streams.work_shock(j, done + 1, done + state.remaining[j] - 1)
    if shock is None:
        state.next_shock[j] = 0
    else:
        state.next_shock[j], state.shock_factor[j] = shock


def _new_activity(state: EngineState, t: int, draw: NewActivityDraw, events: list[Event]) -> bool:
    """D3: insert a copy of a real original activity before an unstarted one (spec 2.2, 3.1 e)."""
    n_real = state.instance.n_real
    if n_real == 0:
        events.append(NewActivitySkipped(day=t, reason="the instance has no real activity"))
        return False
    template = 1 + _index(draw.template, n_real)
    status, sink = state.status, state.sink
    unstarted = [j for j in range(1, len(status)) if j != sink and status[j] == UNSTARTED]
    successor = unstarted[_index(draw.successor, len(unstarted))] if unstarted else sink
    below = _descendants(state.successors, successor)
    # SPEC-Q: "activities" read literally, so the source and finished activities are valid
    # predecessors and the skip below only happens for instances without real activities.
    allowed = [i for i in range(len(status)) if i != successor and i != sink and i not in below]
    if not allowed:
        events.append(NewActivitySkipped(day=t, reason=f"no valid predecessor of {successor}"))
        return False
    predecessor = allowed[_index(draw.predecessor, len(allowed))]
    act = state.instance.activities[template]
    true_duration = realised_duration(act.duration, draw.multiplier)
    # Earliest precedence-feasible day >= t + 1 from current plan starts and realised finishes.
    ready = state.finish[predecessor]
    if ready is None:
        ready = state.plan[predecessor] + state.duration[predecessor]
    plan_start = max(t + 1, ready)
    new = state.add_activity(
        act.duration, act.demands, true_duration, plan_start, predecessor, successor
    )
    state.inserted.append(
        InsertedActivity(
            id=new,
            day=t,
            duration=act.duration,
            demands=act.demands,
            predecessor=predecessor,
            successor=successor,
        )
    )
    events.append(
        NewActivity(
            day=t,
            activity=new,
            template=template,
            duration=act.duration,
            true_duration=true_duration,
            demands=act.demands,
            predecessor=predecessor,
            successor=successor,
        )
    )
    return True


def _index(u: float, n: int) -> int:
    """Map a uniform u in [0, 1) onto 0 .. n-1."""
    return min(n - 1, int(u * n))


def _descendants(successors: list[list[int]], j: int) -> set[int]:
    """All activities reachable from j along precedences (j itself excluded)."""
    seen: set[int] = set()
    stack = list(successors[j])
    while stack:
        i = stack.pop()
        if i not in seen:
            seen.add(i)
            stack.extend(successors[i])
    return seen


def _pause(state: EngineState, j: int, t: int) -> None:
    """Step 2 and spec section 3.1 a: pause j, keep its work and release its present workers."""
    if state.status[j] != RUNNING:
        return
    state.status[j] = PAUSED
    state.running.remove(j)
    state.segments.append(WorkSegment(j, state.open_since[j], t, state.assigned[j]))
    state.release(j)
    state.eligible.add(j)


def _apply(state: EngineState, decision: Decision) -> None:
    """Step 3 hook: apply the policy's operations; WP4 adds SUBST, RESEQ, OVERTIME, ... here."""
    for op in decision.operations:
        match op:
            case Noop():
                pass
            case _:
                assert_never(op)


def _dispatch(state: EngineState, streams: ScenarioStreams, t: int, shocks: bool) -> None:
    """Step 4: start or resume eligible activities in order of planned start (spec 3.1 b-c).

    Ties go to the smallest id. Paused activities resume only with all their original workers;
    unstarted ones take the lowest-id idle workers of each role. Zero-duration activities need
    no workers and complete at once, and the successors they release join the same pass. If no
    worker became idle and no activity eligible since the last dispatch, every candidate that
    failed then fails again, so only activities whose planned start is today are tried.
    """
    plan = state.plan
    # SPEC-Q: "never start earlier than planned" holds for the sink too, so a project that
    # finishes its work early still completes on its planned makespan.
    if state.changed:
        ready = [(plan[j], j) for j in state.eligible if plan[j] <= t]
    else:
        ready = [(plan[j], j) for j in state.eligible if plan[j] == t]
    state.changed = False
    if not ready:
        return
    heapq.heapify(ready)
    status, eligible, idle, busy, present, role = (
        state.status,
        state.eligible,
        state.idle,
        state.busy,
        state.present,
        state.role,
    )
    while ready:
        j = heapq.heappop(ready)[1]
        if status[j] == PAUSED:
            workers = state.assigned[j]
            for w in workers:
                if busy[w] >= 0 or not present[w]:
                    break
            else:
                for w in workers:
                    busy[w] = j
                    idle[role[w]].remove(w)
                _start_work(state, j, t)
        elif state.remaining[j] == 0:
            status[j] = DONE
            state.start[j] = state.finish[j] = t
            eligible.discard(j)
            state.segments.append(WorkSegment(j, t, t, ()))
            for s in state.successors[j]:
                state.pending[s] -= 1
                if state.pending[s] == 0:
                    eligible.add(s)
                    if plan[s] <= t:
                        heapq.heappush(ready, (plan[s], s))
        else:
            needs = state.demands[j]
            for k, r in needs:
                if len(idle[k]) < r:
                    break
            else:
                taken: list[int] = []
                for k, r in needs:
                    pool = idle[k]
                    taken += pool[:r]
                    del pool[:r]
                for w in taken:
                    busy[w] = j
                state.assigned[j] = tuple(taken)
                state.start[j] = t
                _start_work(state, j, t)
                if shocks:
                    _plan_next_shock(state, streams, j)


def _start_work(state: EngineState, j: int, t: int) -> None:
    """Mark j as running from day t on (start or resume)."""
    state.status[j] = RUNNING
    insort(state.running, j)
    state.eligible.discard(j)
    state.open_since[j] = t


def _finish(state: EngineState, j: int, t: int) -> None:
    """Step 6 and spec section 3.1 d: j worked on day t for the last time, so F_j = t + 1."""
    state.running.remove(j)
    state.status[j] = DONE
    state.finish[j] = t + 1
    state.segments.append(WorkSegment(j, state.open_since[j], t + 1, state.assigned[j]))
    state.release(j)
    for s in state.successors[j]:
        state.pending[s] -= 1
        if state.pending[s] == 0:
            state.eligible.add(s)
            state.changed = True


def _day_record(state: EngineState, t: int, epoch: bool) -> DayRecord:
    return DayRecord(
        day=t,
        working=tuple((j, state.assigned[j]) for j in state.running),
        absent=tuple(w for w, here in enumerate(state.present) if not here),
        epoch=epoch,
    )
