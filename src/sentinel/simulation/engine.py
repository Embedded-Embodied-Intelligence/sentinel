"""Day-by-day execution of a plan under hidden durations and disruptions (spec sections 2-3).

Every day t runs the six steps of spec section 3: (1) realise D1 and D3, (2) update the crews
whose presence changed, (3) let the policy decide at a decision epoch, (4) dispatch in order of
the planned start, (5) draw D2 and progress every running activity by its present share of the
crew, (6) close activities without remaining work; section 3.1 fixes the details, (a) the
partial crews. The loop works on the plain lists of `EngineState`; pydantic models are built
only for events, observations and the result. `Run` holds the loop: `simulate` runs it from day 0
of a fresh state, and rollouts continue a state rebuilt from an observation (`Run.resume`).
"""

import math
from bisect import insort
from collections.abc import Sequence
from typing import assert_never

from pydantic import BaseModel, ConfigDict, NonNegativeFloat, NonNegativeInt

from sentinel.model.instance import ProjectInstance
from sentinel.model.schedule import Schedule
from sentinel.policies.base import Decision, Noop, Policy
from sentinel.simulation.events import (
    Absence,
    DisruptionParams,
    DisruptionStreams,
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
    day_limit,
)
from sentinel.simulation.uncertainty import PertParams, realised_duration, role_costs


class DayRecord(BaseModel):
    """Trace of one day: activities that progressed with their present crew members, absent
    workers, epoch."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    day: NonNegativeInt
    working: tuple[tuple[int, tuple[int, ...]], ...]
    absent: tuple[int, ...]
    epoch: bool


class SimulationResult(BaseModel):
    """Outcome of one run for evaluation, hidden quantities included (spec section 3).

    Activities `0 .. n_original - 1` are the instance's; later ids were inserted by D3. `work`
    is the true duration plus all D2 increases, in full-crew days. `crews` holds the crew of
    every started activity, reserved from its start to its finish (spec section 3.1 a), and
    `segments` the days on which it progressed and with which present members. A truncated run
    reports `makespan = max_days` (right-censored); its unstarted activities have no start.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    seed: NonNegativeInt
    n_original: NonNegativeInt
    starts: tuple[int | None, ...]
    finishes: tuple[int | None, ...]
    work: tuple[NonNegativeFloat, ...]
    crews: tuple[tuple[NonNegativeInt, ...], ...]
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
    deadline) with `truncated = True`. Decision epochs are the days with a D1 or D3 event, the
    days after a D2 event and the days t with t % review_period == 0; a passive policy (see
    `Policy`) is not consulted there. Each worker-day of work costs c_k (default 1.0); absent
    crew members do not work and cost nothing.
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
    streams = ScenarioStreams(seed, instance, disruptions, pert)
    state = EngineState(
        instance,
        plan,
        streams.durations,
        role_costs(instance, costs),
        pert=pert,
        disruptions=disruptions,
        deadline=deadline,
        max_days=day_limit(instance, deadline),
    )
    run = Run(state, streams, policy, review_period=review_period, record_trace=record_trace)
    run.days(0)
    return run.result(seed)


class Run:
    """The day loop of spec section 3 on one state: `open_day` runs steps 1-3 of a day and
    `close_day` steps 4-6.

    `days(0)` runs a fresh state to the end (`simulate`). `resume()` continues a state observed at
    step 3 of its day, e.g. one rebuilt by `state_from_observation` for a rollout: it closes that
    day and runs the following ones. Without `record_events` no events are logged, which rollouts
    do not need.
    """

    __slots__ = (
        "events",
        "n_epochs",
        "passive",
        "policy",
        "returns",
        "review_period",
        "shocked",
        "shocks",
        "state",
        "streams",
        "trace",
    )

    def __init__(
        self,
        state: EngineState,
        streams: DisruptionStreams,
        policy: Policy,
        *,
        review_period: int = 5,
        record_events: bool = True,
        record_trace: bool = False,
    ) -> None:
        self.state = state
        self.streams = streams
        self.policy = policy
        self.review_period = review_period
        self.events: list[Event] | None = [] if record_events else None
        self.trace: list[DayRecord] | None = [] if record_trace else None
        self.returns: dict[int, list[int]] = {}  # day -> workers back that day
        for w, day in enumerate(state.return_day):
            if day >= 0:
                self.returns.setdefault(day, []).append(w)
        self.shocks = streams.params.lambda_s > 0
        self.passive = getattr(policy, "passive", False) is True
        self.n_epochs = 0
        self.shocked = False  # a D2 shock on the previous day

    def days(self, first: int) -> None:
        """Run days `first`, `first + 1`, ... until the sink completes or day max_days is over."""
        for t in range(first, self.state.max_days + 1):
            if self.close_day(t, self.open_day(t)):
                return

    def resume(self) -> None:
        """Continue a state observed at step 3 of its day t: look up the next D2 shock of every
        started activity, close day t (steps 4-6), then run days t + 1, t + 2, ..."""
        state = self.state
        t = state.day
        if self.shocks:
            for j, status in enumerate(state.status):
                if status in (RUNNING, PAUSED):
                    _plan_next_shock(state, self.streams, j, t)
        if not self.close_day(t, True):
            self.days(t + 1)

    def open_day(self, t: int) -> bool:
        """Steps 1-3 of day t; returns whether t is a decision epoch (spec section 3.1 g)."""
        state = self.state
        state.day = t
        # Step 1: D1 returns and absences, D3 new activities (spec section 2.2).
        absence, crews = _absences(state, self.streams, t, self.returns, self.events)
        draw = self.streams.new_activity(t)
        inserted = draw is not None and _new_activity(state, t, draw, self.events)
        # Step 2: crews whose presence changed go on at a new rate, pause or resume.
        for j in dict.fromkeys(crews):
            _update_crew(state, j, t)
        # Step 3: decision epoch (spec section 3.1 g).
        # D2 is drawn in step 5, after the decision of its day, so a shock on day t - 1 makes
        # day t a decision epoch (spec section 3.1 g).
        epoch = absence or inserted or self.shocked or t % self.review_period == 0
        if epoch:
            self.n_epochs += 1
            if not self.passive:
                _apply(state, self.policy.decide(state.observe()))
        return epoch

    def close_day(self, t: int, epoch: bool) -> bool:
        """Steps 4-6 of day t; returns True once the sink is complete."""
        state = self.state
        # Step 4: dispatch.
        _dispatch(state, self.streams, t, self.shocks)
        if self.trace is not None:
            self.trace.append(_day_record(state, t, epoch))
        if state.status[state.sink] == DONE:
            return True
        # Steps 5-6: the D2 draw of the work day, then progress by the present crew members;
        # close activities without remaining work.
        self.shocked = False
        done, remaining, rate, work_cost = state.done, state.remaining, state.rate, state.work_cost
        work_days, next_shock = state.work_days, state.next_shock
        finished: list[int] = []
        day_cost = 0.0
        for j in state.running:
            k = work_days[j] + 1
            work_days[j] = k
            if k == next_shock[j]:
                _work_increase(state, self.streams, j, t, self.events)
                self.shocked = True
            units = rate[j]
            done[j] += units
            remaining[j] -= units
            day_cost += work_cost[j]
            if remaining[j] <= 0:
                finished.append(j)
        state.cost += day_cost
        for j in finished:
            _finish(state, j, t)
        return False

    def result(self, seed: int) -> SimulationResult:
        """The outcome of a run that started at day 0 (spec section 3.1 f for truncation)."""
        state = self.state
        max_days, sink_start = state.max_days, state.start[state.sink]
        truncated = sink_start is None
        if truncated:
            for j in state.running:
                segment = WorkSegment(j, state.open_since[j], max_days + 1, state.working[j])
                state.segments.append(segment)
        makespan = max_days if sink_start is None else sink_start
        deadline = state.deadline
        # Built from the engine's own lists, so validation is skipped for speed.
        return SimulationResult.model_construct(
            seed=seed,
            n_original=state.instance.n_activities,
            starts=tuple(state.start),
            finishes=tuple(state.finish),
            work=tuple(
                (d + r) / u for d, r, u in zip(state.done, state.remaining, state.unit, strict=True)
            ),
            crews=tuple(state.assigned),
            segments=tuple(sorted(state.segments)),
            makespan=makespan,
            deadline=deadline,
            deadline_met=None if deadline is None else (not truncated and makespan <= deadline),
            total_cost=state.cost,
            n_epochs=self.n_epochs,
            events=() if self.events is None else tuple(self.events),
            truncated=truncated,
            max_days=max_days,
            trace=None if self.trace is None else tuple(self.trace),
        )


def _absences(
    state: EngineState,
    streams: DisruptionStreams,
    t: int,
    returns: dict[int, list[int]],
    events: list[Event] | None,
) -> tuple[bool, list[int]]:
    """D1: returns of day t, then onsets; returns (any onset, activities whose crew changed)."""
    present, idle, role, busy = state.present, state.idle, state.role, state.busy
    crews: list[int] = []
    for w in returns.pop(t, []):
        present[w] = True
        state.return_day[w] = -1
        state.absent_since[w] = None
        state.announced[w] = None
        if busy[w] >= 0:
            crews.append(busy[w])  # rejoins its crew (spec section 3.1 a)
        else:
            state.changed = True
            insort(idle[role[w]], w)
    onsets = streams.absence_onsets(t)
    for w, length, announced in onsets:
        present[w] = False
        state.return_day[w] = t + length
        state.absent_since[w] = t
        state.announced[w] = announced
        returns.setdefault(t + length, []).append(w)
        if busy[w] >= 0:
            crews.append(busy[w])  # stays reserved for its crew
        else:
            idle[role[w]].remove(w)
        if events is not None:
            events.append(Absence(day=t, worker=w, length=length, announced=announced))
    return bool(onsets), crews


def _update_crew(state: EngineState, j: int, t: int) -> None:
    """Step 2 and spec section 3.1 a: from day t on, j works with its present crew members.

    The rate becomes their number (rho_j = rate / M_j) and the daily cost theirs; without a
    present member j is paused, and it resumes when one returns. Every change of the present
    members ends the current work segment.
    """
    present, role, role_costs = state.present, state.role, state.role_costs
    workers = tuple(w for w in state.assigned[j] if present[w])
    if state.status[j] == RUNNING:
        state.segments.append(WorkSegment(j, state.open_since[j], t, state.working[j]))
        if not workers:
            state.status[j] = PAUSED
            state.running.remove(j)
    elif workers:
        state.status[j] = RUNNING
        insort(state.running, j)
    state.working[j] = workers
    state.open_since[j] = t if workers else -1
    state.rate[j] = len(workers)
    state.work_cost[j] = sum(role_costs[role[w]] for w in workers)


def _work_increase(
    state: EngineState, streams: DisruptionStreams, j: int, t: int, events: list[Event] | None
) -> None:
    """D2 (spec section 2.2): before progress on this work day, j's remaining work times F."""
    unit = state.unit[j]
    before = state.remaining[j]
    factor = state.shock_factor[j]
    after = before * factor
    state.remaining[j] = after
    work_done = state.done[j] / unit
    state.work_increases.append((j, work_done, factor))
    if events is not None:
        events.append(
            WorkIncrease(
                day=t,
                activity=j,
                work_day=state.work_days[j],
                work_done=work_done,
                factor=factor,
                remaining_before=before / unit,
                remaining_after=after / unit,
            )
        )
    _plan_next_shock(state, streams, j, t + 1)


def _plan_next_shock(state: EngineState, streams: DisruptionStreams, j: int, day: int) -> None:
    """Look up the next D2 shock of j among the work days it can still have from `day` on.

    Every work day does at least one unit and none comes after max_days, so after k work days
    the checks k + 1 .. k + min(ceil(remaining units), days left) cover all of them.
    """
    k = state.work_days[j]
    remaining = state.remaining[j]
    span = state.max_days + 1 - day
    if remaining < span:
        span = math.ceil(remaining)
    shock = streams.work_shock(j, k + 1, k + span)
    if shock is None:
        state.next_shock[j] = 0
    else:
        state.next_shock[j], state.shock_factor[j] = shock


def _new_activity(
    state: EngineState, t: int, draw: NewActivityDraw, events: list[Event] | None
) -> bool:
    """D3: insert a copy of a real original activity before an unstarted one (spec 2.2, 3.1 e)."""
    n_real = state.instance.n_real
    if n_real == 0:
        if events is not None:
            events.append(NewActivitySkipped(day=t, reason="the instance has no real activity"))
        return False
    template = 1 + _index(draw.template, n_real)
    status, sink = state.status, state.sink
    unstarted = [j for j in range(1, len(status)) if j != sink and status[j] == UNSTARTED]
    successor = unstarted[_index(draw.successor, len(unstarted))] if unstarted else sink
    below = _descendants(state.successors, successor)
    # The source and finished activities are valid predecessors (spec section 2.2 D3), so the
    # skip below only happens for instances without real activities.
    allowed = [i for i in range(len(status)) if i != successor and i != sink and i not in below]
    if not allowed:
        if events is not None:
            reason = f"no valid predecessor of {successor}"
            events.append(NewActivitySkipped(day=t, reason=reason))
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
    if events is not None:
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


def _apply(state: EngineState, decision: Decision) -> None:
    """Step 3 hook: apply the policy's operations; WP4 adds SUBST, RESEQ, OVERTIME, ... here."""
    for op in decision.operations:
        match op:
            case Noop():
                pass
            case _:
                assert_never(op)


def _dispatch(state: EngineState, streams: DisruptionStreams, t: int, shocks: bool) -> None:
    """Step 4: complete milestones, then start activities in order of planned start (3.1 b-d).

    Zero-duration activities complete as soon as their predecessors are complete, whatever
    their planned start, and the activities they release join the same pass. Activities with
    p_j > 0 start no earlier than planned, in order of (planned start, id), each with the
    lowest-id idle present workers of every role it needs. If no worker became idle and no
    activity eligible since the last dispatch, every candidate that failed then fails again, so
    only activities whose planned start is today are tried.
    """
    plan, eligible = state.plan, state.eligible
    if state.changed:
        state.changed = False
        duration, pending = state.duration, state.pending
        milestones = [j for j in eligible if duration[j] == 0]
        ready = [(plan[j], j) for j in eligible if plan[j] <= t and duration[j] > 0]
        while milestones:
            j = milestones.pop()
            state.status[j] = DONE
            state.start[j] = state.finish[j] = t
            eligible.discard(j)
            for s in state.successors[j]:
                pending[s] -= 1
                if pending[s] == 0:
                    eligible.add(s)
                    if duration[s] == 0:
                        milestones.append(s)
                    elif plan[s] <= t:
                        ready.append((plan[s], s))
    else:
        ready = [(plan[j], j) for j in eligible if plan[j] == t]
    if not ready:
        return
    # Starts release nothing, so the candidates of this pass are known: try them in order.
    ready.sort()
    idle, busy, demands = state.idle, state.busy, state.demands
    for _, j in ready:
        needs = demands[j]
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
            _start(state, j, t, tuple(taken))
            if shocks:
                _plan_next_shock(state, streams, j, t)


def _start(state: EngineState, j: int, t: int, crew: tuple[int, ...]) -> None:
    """Start j on day t with its crew, all present, so rho_j = 1 (spec section 3.1 a-b)."""
    state.status[j] = RUNNING
    insort(state.running, j)
    state.eligible.discard(j)
    state.start[j] = t
    state.open_since[j] = t
    state.assigned[j] = state.working[j] = crew
    state.rate[j] = state.unit[j]  # M_j present members; 1 unit without demands
    state.work_cost[j] = state.daily_cost[j]


def _finish(state: EngineState, j: int, t: int) -> None:
    """Step 6 and spec section 3.1 d: j's remaining work reached zero on day t, so F_j = t + 1."""
    state.running.remove(j)
    state.status[j] = DONE
    state.finish[j] = t + 1
    state.segments.append(WorkSegment(j, state.open_since[j], t + 1, state.working[j]))
    state.release(j)
    for s in state.successors[j]:
        state.pending[s] -= 1
        if state.pending[s] == 0:
            state.eligible.add(s)
            state.changed = True


def _day_record(state: EngineState, t: int, epoch: bool) -> DayRecord:
    return DayRecord(
        day=t,
        working=tuple((j, state.working[j]) for j in state.running),
        absent=tuple(w for w, here in enumerate(state.present) if not here),
        epoch=epoch,
    )
