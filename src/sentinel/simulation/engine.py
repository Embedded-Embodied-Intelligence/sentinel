"""Day-by-day execution of a plan under hidden durations and disruptions (spec sections 2-3).

Every day t runs the six steps of spec section 3: (1) realise D1 and D3, (2) update the crews
whose presence changed, (3) let the policy decide at a decision epoch, (4) dispatch in order of
the planned start, (5) draw D2 and progress every running activity by its present share of the
crew, (6) close activities without remaining work; section 3.1 fixes the details, (a) the
partial crews and (g) the decision epochs, absence returns included. Step 3 applies the
operations of spec section 4 (`Run.apply`): SHIFT, RESEQ, SUBST and OVERTIME, whose temporary
workers leave after their window (step 1, or when their crew is released). The loop works on
the plain lists of `EngineState`; pydantic models are built only for events, observations and
the result. `Run` holds the loop: `simulate` runs it from day 0 of a fresh state, and rollouts
continue a state rebuilt from an observation (`Run.resume`), to which they may first apply a
decision with the same `Run.apply`.
"""

import math
from bisect import insort
from collections.abc import Collection, Sequence
from itertools import compress
from typing import assert_never

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
)

from sentinel.model.instance import ProjectInstance
from sentinel.model.schedule import Schedule
from sentinel.policies.base import (
    Decision,
    Noop,
    Operation,
    Overtime,
    Policy,
    Reseq,
    Shift,
    Subst,
)
from sentinel.policies.no_reaction import NoReaction
from sentinel.scheduling.residual import planning_view, validate_residual, validate_shift
from sentinel.simulation.events import (
    Absence,
    AbsenceDraw,
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
    HANDOVER_FACTOR,
    PAUSED,
    RUNNING,
    UNSTARTED,
    EngineState,
    InsertedActivity,
    Observation,
    TemporaryWorker,
    WorkSegment,
    day_limit,
    nominal_world,
    onboarding_days,
    overtime_cap,
    state_from_observation,
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


def _unset(value: object) -> bool:
    """Leave a field out of serialisation while it is empty or zero, so that runs without
    interventions serialise exactly as before WP4a (the engine regression digests)."""
    return not value


class Substitution(BaseModel):
    """An applied SUBST (spec section 4): on `day` the absent members `replaced` of `activity`
    left its crew and the idle `workers` took their slots (same order). Each substitute needs
    `onboarding` crew-member days o_j, so m_j o_j crew-member days, `handover` = h_j =
    m_j o_j / M_j full-crew days, were added to its remaining work (spec section 3)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    day: NonNegativeInt
    activity: NonNegativeInt
    replaced: tuple[NonNegativeInt, ...]
    workers: tuple[NonNegativeInt, ...]
    onboarding: PositiveInt
    handover: PositiveFloat


class Rejection(BaseModel):
    """An operation rejected on `day` because it was invalid in the state it met (spec 4)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    day: NonNegativeInt
    operation: Operation
    reason: str


class SimulationResult(BaseModel):
    """Outcome of one run for evaluation, hidden quantities included (spec section 3).

    Activities `0 .. n_original - 1` are the instance's; later ids were inserted by D3. `work`
    is the true duration plus all D2 increases and SUBST handovers, in full-crew days. `crews`
    holds the final crew of every started activity, reserved until its finish, absent members
    included (spec section 3.1 a): its crew from the start, unless `substitutions` record that
    absent members left it and idle workers took their slots on some day (spec section 4).
    `segments` gives the days on which an activity progressed and with which present members.
    A truncated run reports `makespan = max_days` (right-censored); its unstarted activities
    have no start. `rejected` lists invalid operations, `reseqs` and `shifts` count the applied
    RESEQs and SHIFTs, `nervousness` the (epoch, activity) pairs whose planned start a decision
    changed and `infeasible_reseqs` the RESEQ and SHIFT plans that failed their check (also in
    `rejected`; spec section 7.1). `temporary` lists the workers hired by OVERTIME (ids after
    the instance's workers, in `crews` too), `temporary_days` the worker-days paid for them and
    `overtime_cost` that part of `total_cost` (spec section 4). These fields are serialised only
    when set. `observations` holds the agent's view of each requested day the run reached
    (`simulate`'s `observe_days`); it is a by-product, left out of `model_dump` and
    serialisation.
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
    observations: tuple[Observation, ...] = Field(default=(), exclude=True, repr=False)
    substitutions: tuple[Substitution, ...] = Field(default=(), exclude_if=_unset)
    rejected: tuple[Rejection, ...] = Field(default=(), exclude_if=_unset)
    reseqs: NonNegativeInt = Field(default=0, exclude_if=_unset)
    nervousness: NonNegativeInt = Field(default=0, exclude_if=_unset)
    infeasible_reseqs: NonNegativeInt = Field(default=0, exclude_if=_unset)
    shifts: NonNegativeInt = Field(default=0, exclude_if=_unset)
    temporary: tuple[TemporaryWorker, ...] = Field(default=(), exclude_if=_unset)
    temporary_days: NonNegativeInt = Field(default=0, exclude_if=_unset)
    overtime_cost: NonNegativeFloat = Field(default=0.0, exclude_if=_unset)

    @property
    def hired(self) -> int:
        """Temporary workers hired by OVERTIME (spec section 4)."""
        return len(self.temporary)

    @property
    def n_substituted(self) -> int:
        """Crew members replaced by SUBST (the substitutions of spec section 7.1)."""
        return sum(len(s.replaced) for s in self.substitutions)

    @property
    def onboarding_days(self) -> int:
        """Crew-member days of onboarding added by SUBST, the sum of m_j o_j (spec 3, 7.1)."""
        return sum(len(s.replaced) * s.onboarding for s in self.substitutions)

    @property
    def handover_days(self) -> float:
        """Full-crew days added by SUBST handovers, the sum of h_j (spec sections 3, 7.1)."""
        return sum(s.handover for s in self.substitutions)


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
    observe_days: Collection[int] = (),
    handover_factor: float = HANDOVER_FACTOR,
    debug: bool = False,
) -> SimulationResult:
    """Execute `plan` under `policy` for one replication seed (spec sections 2-3).

    The run ends when the sink completes, or after day `max_days` = 5 D (5 sum p_j without a
    deadline) with `truncated = True`. Decision epochs are the days with a D1 event (an absence
    onset or return) or a D3 event, the days after a D2 event and the days t with
    t % review_period == 0; a passive policy (see
    `Policy`) is not consulted there. Each worker-day of work costs c_k (default 1.0); absent
    crew members do not work and cost nothing. SUBST handovers use alpha = `handover_factor`;
    with `debug`, a RESEQ plan that fails `validate_residual` raises instead of being rejected
    and counted (`Run.apply`). For every day in `observe_days` that the run reaches, the
    observation of step 3 (after any decision) is kept in `result.observations` (checkpoints of
    spec section 5.2); recording changes nothing else.
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
        handover_factor=handover_factor,
    )
    run = Run(
        state,
        streams,
        policy,
        review_period=review_period,
        record_trace=record_trace,
        observe_days=observe_days,
        debug=debug,
    )
    run.days(0)
    return run.result(seed)


class Run:
    """The day loop of spec section 3 on one state: `open_day` runs steps 1-3 of a day and
    `close_day` steps 4-6.

    `days(0)` runs a fresh state to the end (`simulate`). `resume()` continues a state observed at
    step 3 of its day, e.g. one rebuilt by `state_from_observation` for a rollout: it closes that
    day and runs the following ones. Without `record_events` no events are logged, which rollouts
    do not need. The observations of step 3 on `observe_days` are collected in `observations`.
    `apply` is step 3's treatment of a decision; a rollout may also use it to apply a candidate
    action to a rebuilt state before `resume`. Applied and rejected operations are logged in
    `substitutions`, `rejected`, `reseqs`, `shifts`, `nervousness` and `infeasible_reseqs`.
    Without `check_plans`, RESEQ and SHIFT plans are applied unchecked: for rollouts of a
    decision already checked on the same observation (`rehearse`), as the check depends on
    the observation only.
    """

    __slots__ = (
        "check_plans",
        "debug",
        "events",
        "infeasible_reseqs",
        "n_epochs",
        "nervousness",
        "observations",
        "observe_days",
        "passive",
        "policy",
        "rejected",
        "reseqs",
        "returns",
        "review_period",
        "shifts",
        "shocked",
        "shocks",
        "state",
        "streams",
        "substitutions",
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
        observe_days: Collection[int] = (),
        debug: bool = False,
        check_plans: bool = True,
    ) -> None:
        self.state = state
        self.streams = streams
        self.check_plans = check_plans
        self.policy = policy
        self.review_period = review_period
        self.events: list[Event] | None = [] if record_events else None
        self.trace: list[DayRecord] | None = [] if record_trace else None
        self.observe_days = frozenset(observe_days)
        self.observations: list[Observation] = []
        self.returns: dict[int, list[int]] = {}  # day -> workers back that day
        for w, day in enumerate(state.return_day):
            if day >= 0:
                self.returns.setdefault(day, []).append(w)
        self.shocks = streams.params.lambda_s > 0
        self.passive = getattr(policy, "passive", False) is True
        self.n_epochs = 0
        self.shocked = False  # a D2 shock on the previous day
        self.debug = debug
        self.substitutions: list[Substitution] = []
        self.rejected: list[Rejection] = []
        self.reseqs = 0
        self.shifts = 0
        self.nervousness = 0
        self.infeasible_reseqs = 0

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
        if state.leaving:  # idle temporary workers whose window ended leave (spec 4 OVERTIME)
            _window_end(state, t)
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
                self.apply(self.policy.decide(state.observe()))
        if t in self.observe_days:
            self.observations.append(state.observe())
        return epoch

    def apply(self, decision: Decision) -> None:
        """Step 3 of the state's day: apply the operations of `decision` (spec section 4).

        Operations run in the order given, each validated against the state left by the
        previous ones; an invalid one is rejected and logged in `rejected`, and the others still
        apply. SUBST takes, per replaced absent member, an idle present worker of the same role,
        adds the handover h_j to the remaining work and recomputes rho_j at once, so the new
        crew works on the same day. OVERTIME hires its temporary workers, idle and present from
        today (`_hire`). RESEQ and SHIFT set the planned starts of all unstarted activities;
        the plan must pass `validate_residual` (SHIFT: `validate_shift`) on the planning view of
        the current state, and one that does not is rejected and counted in
        `infeasible_reseqs`, or raises AssertionError in `debug` mode. The decision's changes of
        planned starts count towards `nervousness` if they belong to the deviation set U'_t
        (`_replanned`).
        """
        state = self.state
        t = state.day
        before: list[int] | None = None  # planned starts before the first RESEQ or SHIFT
        for op in decision.operations:
            match op:
                case Noop():
                    pass
                case Subst():
                    outcome = _substitute(state, op, t)
                    if isinstance(outcome, str):
                        self.rejected.append(Rejection(day=t, operation=op, reason=outcome))
                        continue
                    self.substitutions.append(outcome)
                    if self.shocks:  # more work: the next D2 shock may lie further on
                        _plan_next_shock(state, self.streams, op.activity, t)
                case Overtime():
                    reason = _hire(state, op, t)
                    if reason is not None:
                        self.rejected.append(Rejection(day=t, operation=op, reason=reason))
                case Reseq() | Shift():
                    reason = _infeasible_plan(state, op) if self.check_plans else None
                    if reason is not None:
                        if self.debug:
                            raise AssertionError(f"{op.kind.upper()} on day {t}: {reason}")
                        self.infeasible_reseqs += 1
                        self.rejected.append(Rejection(day=t, operation=op, reason=reason))
                        continue
                    if before is None:
                        before = state.plan.copy()
                    plan = state.plan
                    for j, day in op.starts.items():
                        plan[j] = day
                    state.changed = True  # dispatch tries every eligible activity again
                    if isinstance(op, Shift):
                        self.shifts += 1
                    else:
                        self.reseqs += 1
                case _:
                    assert_never(op)
        if before is not None:
            self.nervousness += _replanned(state, before)

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
        if state.hired:  # every hired temporary worker is paid for the day (spec 4 OVERTIME)
            state.cost += state.temp_cost
            state.overtime_cost += state.temp_cost
            state.temp_days += state.hired
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
            observations=tuple(self.observations),
            substitutions=tuple(self.substitutions),
            rejected=tuple(self.rejected),
            reseqs=self.reseqs,
            nervousness=self.nervousness,
            infeasible_reseqs=self.infeasible_reseqs,
            shifts=self.shifts,
            temporary=tuple(state.temporary),
            temporary_days=state.temp_days,
            overtime_cost=state.overtime_cost,
        )


def _absences(
    state: EngineState,
    streams: DisruptionStreams,
    t: int,
    returns: dict[int, list[int]],
    events: list[Event] | None,
) -> tuple[bool, list[int]]:
    """D1: returns of day t, then onsets; returns (any return or onset, activities whose crew
    changed). Both make day t a decision epoch (spec section 3.1 g)."""
    present, idle, role, busy = state.present, state.idle, state.role, state.busy
    crews: list[int] = []
    back = returns.pop(t, [])
    for w in back:
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
    return bool(back or onsets), crews


def _update_crew(state: EngineState, j: int, t: int) -> None:
    """Step 2 and spec section 3.1 a: from day t on, j works with its present crew members.

    The rate becomes their number (rho_j = rate / M_j) and the daily cost theirs; without a
    present member j is paused, and it resumes when one returns. Every change of the present
    members ends the current work segment.
    """
    crew = state.assigned[j]
    workers = tuple(compress(crew, map(state.present.__getitem__, crew)))
    if state.status[j] == RUNNING:
        if state.open_since[j] < t:  # a second change on one day (SUBST) adds no empty segment
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
    state.work_cost[j] = sum(map(state.wage.__getitem__, workers))


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


def _substitute(state: EngineState, op: Subst, t: int) -> Substitution | str:
    """SUBST(j, W') on day t (spec section 4); returns what was done, or why it is invalid.

    j must be paused or running with absent members; every substitute must be an existing,
    present worker in no crew, and per role there must be as many absent members as
    substitutes. Within a role, the substitutes in the given order replace the absent members
    in increasing id order and take their slots; the replaced members leave the crew at once
    and are idle when they return. Each of the m_j substitutes needs o_j = max(1, ceil(alpha
    e_j)) crew-member days of onboarding (`onboarding_days`), so m_j o_j crew-member days,
    h_j = m_j o_j / M_j full-crew days, are added to the remaining work, and the crew goes on at
    its new rate from today (`_update_crew`).
    """
    j = op.activity
    status = state.status
    if j >= len(status):
        return f"activity {j} does not exist"
    if status[j] != RUNNING and status[j] != PAUSED:
        return f"activity {j} is {status[j]}, not running or paused"
    present, busy, role = state.present, state.busy, state.role
    crew = state.assigned[j]
    open_slots: dict[int, list[int]] = {}  # role -> absent members, increasing ids
    for w in sorted(crew):
        if not present[w]:
            open_slots.setdefault(role[w], []).append(w)
    if not open_slots:
        return f"activity {j} has no absent member"
    if len(set(op.workers)) != len(op.workers):
        return f"substitutes {op.workers} are not distinct"
    replaced: dict[int, int] = {}  # absent member -> substitute
    for w in op.workers:
        if w >= len(present):
            return f"worker {w} does not exist"
        if not present[w]:
            if w >= state.first_temporary:
                return f"temporary worker {w} has left"
            return f"worker {w} is absent"
        if busy[w] >= 0:
            return f"worker {w} is in the crew of activity {busy[w]}"
        slots = open_slots.get(role[w])
        if not slots:
            return f"activity {j} has no absent member of role {role[w]} left for worker {w}"
        replaced[slots.pop(0)] = w
    unit = state.unit[j]  # M_j
    work = state.done[j] / unit  # e_j in full-crew days
    onboarding = onboarding_days(work, state.handover_factor)  # o_j per substitute
    added = len(replaced) * onboarding  # m_j o_j crew-member days = h_j M_j
    state.remaining[j] += added
    idle = state.idle
    for old, new in replaced.items():
        busy[old] = -1
        busy[new] = j
        idle[role[new]].remove(new)
    state.assigned[j] = tuple(replaced.get(w, w) for w in crew)
    state.handovers.append((j, work, added))
    _update_crew(state, j, t)
    return Substitution(
        day=t,
        activity=j,
        replaced=tuple(replaced),
        workers=tuple(replaced.values()),
        onboarding=onboarding,
        handover=added / unit,
    )


def _replanned(state: EngineState, before: Sequence[int]) -> int:
    """Activities of the deviation set U'_t whose planned start differs from `before` (spec
    sections 7 and 7.1): p_j > 0 and not inserted on the current day, so milestones, the sink
    and fresh D3 activities do not count; a RESEQ only moves unstarted activities."""
    t = state.day
    fresh = {act.id for act in state.inserted if act.day == t}
    duration = state.duration
    return sum(
        1
        for j, (old, new) in enumerate(zip(before, state.plan, strict=True))
        if old != new and duration[j] > 0 and j not in fresh
    )


def _infeasible_plan(state: EngineState, op: Reseq | Shift) -> str | None:
    """Why the plan of a RESEQ is not a feasible solution of the residual problem of the
    current state (spec section 4.1), or that of a SHIFT also changes the order of the planned
    starts (spec section 4); None if the plan is valid."""
    problem = planning_view(state.observe())
    if isinstance(op, Shift):
        violations = validate_shift(problem, op.starts)
    else:
        violations = validate_residual(problem, op.starts)
    if not violations:
        return None
    return f"{len(violations)} residual violations, first: {violations[0].detail}"


def _hire(state: EngineState, op: Overtime, t: int) -> str | None:
    """OVERTIME(k, u, H) on day t (spec section 4): u temporary workers of role k, present and
    idle on days t .. t + H - 1; None, or why the operation is invalid. At most floor(gamma R_k)
    temporary workers of a role are hired at a time (`overtime_cap`)."""
    roles = state.instance.roles
    if op.role >= len(roles):
        return f"role {op.role} does not exist"
    cap = overtime_cap(roles[op.role].capacity)
    hired = sum(1 for temp in state.temporary if temp.role == op.role and temp.left is None)
    if hired + op.workers > cap:
        return (
            f"{op.workers} more temporary workers of role {op.role} exceed floor(gamma R_k) = "
            f"{cap} with {hired} hired"
        )
    for _ in range(op.workers):
        state.hire(op.role, t + op.days)
    return None


def _window_end(state: EngineState, t: int) -> None:
    """Before day t: idle temporary workers whose window ends leave; those in a crew stay until
    their activity completes (`EngineState.release`; spec section 4 OVERTIME)."""
    present, busy = state.present, state.busy
    for w in state.leaving.pop(t, ()):
        if present[w] and busy[w] < 0:
            state.idle[state.role[w]].remove(w)
            state.leave(w, t)


class _Quiet:
    """Streams without any disruption, for applying a decision outside a run (`preview`)."""

    params = DisruptionParams.none()

    def absence_onsets(self, day: int) -> Sequence[AbsenceDraw]:
        return ()

    def work_shock(self, activity: int, first: int, last: int) -> tuple[int, float] | None:
        return None

    def new_activity(self, day: int) -> NewActivityDraw | None:
        return None


def preview(
    observation: Observation, decision: Decision, *, handover_factor: float = HANDOVER_FACTOR
) -> Observation:
    """The observation after `decision` is applied at step 3 of the observed day (spec 4).

    The operations run through the engine's own `Run.apply` on the state rebuilt from the
    observation, so crews, plan, handovers and rejections are those of a run; the hidden
    quantities are set to nominal values, which no observation shows. A policy uses this to see
    the state left by its own SUBST operations, e.g. before planning a RESEQ.
    """
    return rehearse(observation, decision, handover_factor=handover_factor)[0]


def rehearse(
    observation: Observation, decision: Decision, *, handover_factor: float = HANDOVER_FACTOR
) -> tuple[Observation, tuple[Rejection, ...]]:
    """`preview` and the operations the engine would reject: an operation rejected here is
    rejected in every state with this observation, whatever its hidden quantities."""
    world = nominal_world(observation)
    state = state_from_observation(observation, world, handover_factor=handover_factor)
    run = Run(state, _Quiet(), NoReaction(), record_events=False)
    run.apply(decision)
    return state.observe(), tuple(run.rejected)


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
    """Start j on day t with its crew, all present, so rho_j = 1 (spec section 3.1 a-b); the
    work of temporary workers in the crew costs nothing beyond their daily pay (spec 4)."""
    state.status[j] = RUNNING
    insort(state.running, j)
    state.eligible.discard(j)
    state.start[j] = t
    state.open_since[j] = t
    state.assigned[j] = state.working[j] = crew
    state.rate[j] = state.unit[j]  # M_j present members; 1 unit without demands
    if state.temporary and crew and max(crew) >= state.first_temporary:
        state.work_cost[j] = sum(state.wage[w] for w in crew)
    else:
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
    present = state.present
    return DayRecord(
        day=t,
        working=tuple((j, state.working[j]) for j in state.running),
        absent=tuple(w for w in range(state.first_temporary) if not present[w]),
        epoch=epoch,
    )
