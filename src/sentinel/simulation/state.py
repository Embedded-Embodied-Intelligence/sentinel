"""Mutable engine state and the agent's frozen observation of it (spec section 3)."""

import math
import operator
from bisect import insort
from collections.abc import Sequence
from typing import Final, Literal, NamedTuple

from pydantic import BaseModel, ConfigDict, Field, NonNegativeFloat, NonNegativeInt

from sentinel.model.instance import ProjectInstance
from sentinel.model.schedule import Schedule
from sentinel.simulation.events import DisruptionParams
from sentinel.simulation.uncertainty import PertParams, role_costs

ActivityStatus = Literal["unstarted", "running", "paused", "done"]
UNSTARTED: Final = "unstarted"
RUNNING: Final = "running"
PAUSED: Final = "paused"
DONE: Final = "done"
HANDOVER_FACTOR: Final = 0.3  # alpha of the handover cost h_j (spec sections 3 and 8)
OVERTIME_CAP: Final = 0.2  # gamma: at most floor(gamma R_k) temporary workers of role k (4, 8)
OVERTIME_RATE: Final = 1.5  # c_OT_k / c_k, the daily cost of a temporary worker (spec 4, 8)


def overtime_cap(capacity: int, cap: float = OVERTIME_CAP) -> int:
    """floor(gamma R_k): the temporary workers of a role with R_k = `capacity` that may be hired
    at once (spec section 4); the floor ignores rounding noise below 1e-9."""
    return math.floor(cap * capacity + 1e-9)


def onboarding_days(work: float, handover_factor: float = HANDOVER_FACTOR) -> int:
    """o_j = max(1, ceil(alpha e_j)): the crew-member days a substitute needs before it
    contributes, after e_j = `work` full-crew days (spec section 3); a SUBST replacing m_j
    members adds m_j o_j crew-member days, h_j = m_j o_j / M_j full-crew days. The ceiling
    ignores rounding noise below 1e-9."""
    return max(1, math.ceil(handover_factor * work - 1e-9))


def _unset(value: object) -> bool:
    """Leave a field out of serialisation while it is empty or zero, so that the dumps of runs
    and observations without interventions are what they were before WP4a."""
    return not value


class WorkSegment(NamedTuple):
    """Days `start .. end - 1` on which `activity` progressed with the same present crew members
    `workers` (spec section 3.1 a); a pause or a change of the present members starts a new one.
    """

    activity: int
    start: int
    end: int
    workers: tuple[int, ...]


class SampledWorld(NamedTuple):
    """The hidden quantities of a state (spec section 5.1): what an `Observation` leaves out.

    `remaining` is the remaining work of every activity in crew-member days, the engine's unit
    (M_j per full-crew day, 1 without demands), so P_j M_j for an unstarted activity. `return_day`
    is the day each absent worker is back, -1 for present workers. `fallbacks` counts conditions
    of the belief that had probability zero and were replaced by the smallest feasible value.
    """

    remaining: tuple[float, ...]
    return_day: tuple[int, ...]
    fallbacks: int = 0


class InsertedActivity(BaseModel):
    """A D3 activity as announced to the agent: nominal data only, true duration hidden."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: NonNegativeInt
    day: NonNegativeInt
    duration: NonNegativeInt
    demands: tuple[NonNegativeInt, ...]
    predecessor: NonNegativeInt
    successor: NonNegativeInt


class TemporaryWorker(BaseModel):
    """A worker hired by OVERTIME (spec section 4): worker id `id` of `role`, hired on day
    `hired` for the window [hired, until). It is never absent; after the window it takes no new
    assignment and leaves when idle. `left` is the first day it is no longer hired (None while
    it is); it is paid for the days [hired, left)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: NonNegativeInt
    role: NonNegativeInt
    hired: NonNegativeInt
    until: NonNegativeInt
    left: NonNegativeInt | None = None


class Observation(BaseModel):
    """What the agent may see on `day` (spec section 3): no true durations, no true absence
    lengths, no future events.

    Per-activity tuples are indexed by activity id (the instance's ids, then the D3 ids in
    `inserted`); per-worker tuples by worker id (the instance's workers, then the temporary
    workers in `temporary`, spec section 4; a temporary worker is present while it is hired and
    never absent). `work_done` is e_j in full-crew days.
    `assigned` holds the crew of every started activity, reserved until it completes, absent
    members included (spec section 3.1 a); a member replaced by SUBST has left it (spec section
    4). `work_increases` lists every observed D2 shock as (activity, e_j before the shock,
    factor F), and `handovers` every SUBST handover as (activity, e_j at the handover, work
    added m_j o_j in crew-member days, i.e. h_j M_j; spec section 3).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    day: NonNegativeInt
    instance: ProjectInstance
    inserted: tuple[InsertedActivity, ...]
    plan: tuple[int, ...]
    status: tuple[ActivityStatus, ...]
    work_done: tuple[NonNegativeFloat, ...]
    start: tuple[int | None, ...]
    finish: tuple[int | None, ...]
    assigned: tuple[tuple[int, ...], ...]
    work_increases: tuple[tuple[int, float, float], ...]
    present: tuple[bool, ...]
    absent_since: tuple[int | None, ...]
    announced: tuple[int | None, ...]  # L_low of the current absence
    cost: float
    deadline: int | None
    pert: PertParams
    disruptions: DisruptionParams
    handovers: tuple[tuple[int, float, int], ...] = Field(default=(), exclude_if=_unset)
    temporary: tuple[TemporaryWorker, ...] = Field(default=(), exclude_if=_unset)


def worker_roles(observation: Observation) -> list[int]:
    """The role of every worker id of an observation, temporary workers included."""
    roles = [worker.role for worker in observation.instance.workers]
    return roles + [temp.role for temp in observation.temporary]


class EngineState:
    """Mutable state of one run in plain lists (spec section 3), hidden quantities included.

    Work is counted in crew-member days: a full-crew day of activity j is `unit[j]` = M_j units
    (1 for an activity without demands), and a work day with c present crew members does c
    units, so rho_j = c / M_j (spec section 3.1 a) needs no fractions and remaining work hits
    zero exactly; only D2 factors make it fractional. Hidden: `remaining` (true remaining work),
    `return_day` (true end of an absence) and `next_shock`/`shock_factor` (the next D2 shock).
    Only `observe()` passes information to a policy. Per-activity lists are indexed by activity
    id and grow with D3 insertions; per-worker lists by worker id and grow with the temporary
    workers of OVERTIME (`hire`, spec section 4), whose ids start at `first_temporary`. A crew
    member's work costs `wage` per day, c_k of its role, but 0 for a temporary worker, which is
    paid OVERTIME_RATE c_k for every day it is hired instead (`temp_cost` per day for all of them,
    added up in `temp_days` and `overtime_cost`). `handover_factor` is alpha of the SUBST
    handover cost.
    """

    __slots__ = (
        "absent_since",
        "announced",
        "assigned",
        "busy",
        "changed",
        "cost",
        "daily_cost",
        "day",
        "deadline",
        "demands",
        "disruptions",
        "done",
        "duration",
        "eligible",
        "finish",
        "first_temporary",
        "handover_factor",
        "handovers",
        "hired",
        "idle",
        "inserted",
        "instance",
        "leaving",
        "max_days",
        "next_shock",
        "open_since",
        "overtime_cost",
        "pending",
        "pert",
        "plan",
        "present",
        "rate",
        "remaining",
        "return_day",
        "role",
        "role_costs",
        "running",
        "segments",
        "shock_factor",
        "sink",
        "start",
        "status",
        "successors",
        "temp_cost",
        "temp_days",
        "temporary",
        "unit",
        "wage",
        "work_cost",
        "work_days",
        "work_increases",
        "working",
    )

    def __init__(
        self,
        instance: ProjectInstance,
        plan: Schedule,
        durations: Sequence[int],
        role_costs: Sequence[float],
        *,
        pert: PertParams,
        disruptions: DisruptionParams,
        deadline: int | None,
        max_days: int,
        handover_factor: float = HANDOVER_FACTOR,
    ) -> None:
        acts = instance.activities
        n = len(acts)
        self.instance = instance
        self.pert = pert
        self.disruptions = disruptions
        self.handover_factor = handover_factor
        self.deadline = deadline
        self.max_days = max_days  # last simulated day
        self.role_costs = tuple(role_costs)
        self.sink = n - 1
        self.day = 0
        self.cost = 0.0
        # False once a dispatch found nothing else to start; set again when workers become
        # idle or activities become eligible, so that a dispatch can only succeed afterwards.
        self.changed = True

        self.duration = [act.duration for act in acts]  # nominal p_j
        self.demands = [tuple((k, r) for k, r in enumerate(act.demands) if r > 0) for act in acts]
        self.daily_cost = [sum(self.role_costs[k] * r for k, r in dem) for dem in self.demands]
        self.unit = [max(1, sum(r for _, r in dem)) for dem in self.demands]  # M_j
        self.successors = [list(act.successors) for act in acts]
        self.pending = [len(instance.predecessors(j)) for j in range(n)]  # unfinished preds
        self.status: list[ActivityStatus] = [UNSTARTED] * n
        self.done = [0] * n  # units of work done
        self.remaining: list[float] = [p * u for p, u in zip(durations, self.unit, strict=True)]
        self.plan = list(plan.starts)
        self.start: list[int | None] = [None] * n
        self.finish: list[int | None] = [None] * n
        self.assigned: list[tuple[int, ...]] = [()] * n  # crew, reserved until completion
        self.working: list[tuple[int, ...]] = [()] * n  # present crew members
        self.rate = [0] * n  # units per work day: present crew members, 1 without demands
        self.work_cost = [0.0] * n  # daily cost of the present crew members
        self.open_since = [-1] * n  # first day of the current work segment
        self.work_days = [0] * n  # days with rho_j > 0 so far, the D2 counter k
        self.next_shock = [0] * n  # work-day counter of the next D2 shock, 0 if none
        self.shock_factor = [0.0] * n
        self.segments: list[WorkSegment] = []

        self.role = [worker.role for worker in instance.workers]
        n_workers = len(self.role)
        self.present = [True] * n_workers
        self.return_day = [-1] * n_workers
        self.absent_since: list[int | None] = [None] * n_workers
        self.announced: list[int | None] = [None] * n_workers
        self.busy = [-1] * n_workers  # activity whose crew the worker is in, -1 if none
        self.wage = [self.role_costs[k] for k in self.role]  # daily cost of a member's work
        # idle[k]: present workers of role k in no crew, in increasing id order
        self.idle = [[w for w, k in enumerate(self.role) if k == r.id] for r in instance.roles]

        self.running: list[int] = []  # increasing ids
        self.eligible = {j for j in range(n) if self.pending[j] == 0}  # unstarted only
        self.inserted: list[InsertedActivity] = []
        self.work_increases: list[tuple[int, float, float]] = []
        self.handovers: list[tuple[int, float, int]] = []

        self.first_temporary = n_workers
        self.temporary: list[TemporaryWorker] = []  # by id - first_temporary
        self.leaving: dict[int, list[int]] = {}  # first day after a window -> its workers
        self.hired = 0  # temporary workers hired now
        self.temp_cost = 0.0  # their daily cost
        self.temp_days = 0  # temporary worker-days paid so far
        self.overtime_cost = 0.0

    def copy(self) -> "EngineState":
        """An independent copy for another run from the same state: every container a run
        changes is copied, the instance and immutable values are shared."""
        other = object.__new__(EngineState)
        for name in EngineState.__slots__:
            value = getattr(self, name)
            if name in _NESTED:
                value = [inner.copy() for inner in value]
            elif name == "leaving":
                value = {day: workers.copy() for day, workers in value.items()}
            elif isinstance(value, list | set):
                value = value.copy()
            setattr(other, name, value)
        return other

    def add_activity(
        self,
        duration: int,
        demands: tuple[int, ...],
        true_duration: int,
        plan_start: int,
        predecessor: int,
        successor: int,
    ) -> int:
        """Insert an unstarted activity between `predecessor` and `successor`; returns its id."""
        new = len(self.status)
        dem = tuple((k, r) for k, r in enumerate(demands) if r > 0)
        unit = max(1, sum(r for _, r in dem))
        self.duration.append(duration)
        self.demands.append(dem)
        self.daily_cost.append(sum(self.role_costs[k] * r for k, r in dem))
        self.unit.append(unit)
        self.successors[predecessor].append(new)
        self.successors.append([successor])
        self.pending.append(0 if self.status[predecessor] == DONE else 1)
        self.pending[successor] += 1
        self.eligible.discard(successor)
        self.status.append(UNSTARTED)
        self.done.append(0)
        self.remaining.append(true_duration * unit)
        self.plan.append(plan_start)
        self.start.append(None)
        self.finish.append(None)
        self.assigned.append(())
        self.working.append(())
        self.rate.append(0)
        self.work_cost.append(0.0)
        self.open_since.append(-1)
        self.work_days.append(0)
        self.next_shock.append(0)
        self.shock_factor.append(0.0)
        if self.pending[new] == 0:
            self.eligible.add(new)
            self.changed = True
        return new

    def release(self, j: int) -> None:
        """Dissolve the crew of the completed activity j at the end of the current day; its
        present members become idle, except temporary workers whose window is over, who leave
        (spec section 4 OVERTIME)."""
        busy, present, idle, role = self.busy, self.present, self.idle, self.role
        self.changed = True
        first, tomorrow = self.first_temporary, self.day + 1
        for w in self.assigned[j]:
            busy[w] = -1
            if present[w]:
                if w >= first and self.temporary[w - first].until <= tomorrow:
                    self.leave(w, tomorrow)
                else:
                    insort(idle[role[w]], w)

    def hire(self, role: int, until: int) -> int:
        """A temporary worker of `role`, present and idle from today to day `until` - 1 (the
        window of spec section 4 OVERTIME); returns its id, the next free worker id."""
        w = len(self.role)
        self.role.append(role)
        self.present.append(True)
        self.return_day.append(-1)
        self.absent_since.append(None)
        self.announced.append(None)
        self.busy.append(-1)
        self.wage.append(0.0)
        self.idle[role].append(w)  # the largest id, so the pool stays sorted
        self.temporary.append(TemporaryWorker(id=w, role=role, hired=self.day, until=until))
        self.leaving.setdefault(until, []).append(w)
        self.changed = True
        self.count_hired()
        return w

    def leave(self, w: int, day: int) -> None:
        """Temporary worker w is no longer hired from `day` on: gone, and paid no more."""
        i = w - self.first_temporary
        self.temporary[i] = self.temporary[i].model_copy(update={"left": day})
        self.present[w] = False
        self.count_hired()

    def count_hired(self) -> None:
        """Recount the temporary workers hired now and their daily cost OVERTIME_RATE c_k."""
        hired = [temp.role for temp in self.temporary if temp.left is None]
        self.hired = len(hired)
        self.temp_cost = sum(OVERTIME_RATE * self.role_costs[k] for k in hired)

    def hidden(self) -> SampledWorld:
        """The true hidden quantities: the perfect-information test hook of the forecaster.

        Never passed to a policy; together with `observe()` it gives back this state through
        `state_from_observation`.
        """
        return SampledWorld(tuple(self.remaining), tuple(self.return_day))

    def observe(self) -> Observation:
        """The agent's view of the current day (spec section 3); hidden fields are left out."""
        # The engine maintains the invariants, so validation is skipped for speed.
        return Observation.model_construct(
            day=self.day,
            instance=self.instance,
            inserted=tuple(self.inserted),
            plan=tuple(self.plan),
            status=tuple(self.status),
            work_done=tuple(map(operator.truediv, self.done, self.unit)),
            start=tuple(self.start),
            finish=tuple(self.finish),
            assigned=tuple(self.assigned),
            work_increases=tuple(self.work_increases),
            present=tuple(self.present),
            absent_since=tuple(self.absent_since),
            announced=tuple(self.announced),
            cost=self.cost,
            deadline=self.deadline,
            pert=self.pert,
            disruptions=self.disruptions,
            handovers=tuple(self.handovers),
            temporary=tuple(self.temporary),
        )


_NESTED: Final = frozenset({"idle", "successors"})  # EngineState lists of lists


def day_limit(instance: ProjectInstance, deadline: int | None) -> int:
    """Last simulated day max_days = ceil(5 D) = 5 D, or 5 sum p_j without a deadline (3.1 f)."""
    if deadline is None:
        return 5 * sum(act.duration for act in instance.activities)
    return 5 * deadline


def state_from_observation(
    observation: Observation,
    world: SampledWorld,
    *,
    plan: Sequence[int] | None = None,
    costs: Sequence[float] | None = None,
    handover_factor: float = HANDOVER_FACTOR,
) -> EngineState:
    """The engine state at step 3 of the observed day, completed by the hidden `world`.

    `plan` replaces the observed plan (one start per activity id, D3 activities included),
    `costs` are the daily role costs c_k (default 1.0) and `handover_factor` the alpha of later
    SUBST operations (default 0.3, spec section 8). The D2 work-day counters restart at 0 and
    no D2 shock is planned yet: the run that continues the state looks them up in its own streams
    (`Run.resume`). Work segments before the day are not reconstructed, nor are the counts of
    temporary worker-days and overtime cost (both in the observed cost).
    """
    instance = observation.instance
    n_original = instance.n_activities
    starts = list(observation.plan if plan is None else plan)
    n = len(observation.status)
    if not len(starts) == len(world.remaining) == n:
        raise ValueError(
            f"need one plan start and one remaining work per activity ({n}), got "
            f"{len(starts)} and {len(world.remaining)}"
        )
    if len(world.return_day) != len(observation.present):
        raise ValueError(f"need one return day per worker, got {len(world.return_day)}")
    state = EngineState(
        instance,
        Schedule(starts=tuple(starts[:n_original])),
        [0] * n_original,
        role_costs(instance, costs),
        pert=observation.pert,
        disruptions=observation.disruptions,
        deadline=observation.deadline,
        max_days=day_limit(instance, observation.deadline),
        handover_factor=handover_factor,
    )
    for act in observation.inserted:
        new = state.add_activity(
            act.duration, act.demands, 0, starts[act.id], act.predecessor, act.successor
        )
        if new != act.id:
            raise ValueError(f"inserted activity {act.id} would get id {new}")
    t = observation.day
    state.day = t
    for temp in observation.temporary:
        if temp.id != len(state.role):
            raise ValueError(f"temporary worker {temp.id} would get id {len(state.role)}")
        state.role.append(temp.role)
        state.busy.append(-1)
        state.wage.append(0.0)
        state.temporary.append(temp)
        if temp.left is None and temp.until > t:
            state.leaving.setdefault(temp.until, []).append(temp.id)
    state.count_hired()
    state.cost = observation.cost
    state.inserted = list(observation.inserted)
    state.work_increases = list(observation.work_increases)
    state.handovers = list(observation.handovers)
    status = state.status = list(observation.status)
    state.start = list(observation.start)
    state.finish = list(observation.finish)
    state.remaining = list(world.remaining)
    state.done = [
        crew_member_days(e, u) for e, u in zip(observation.work_done, state.unit, strict=True)
    ]
    pending = [0] * n
    for i in range(n):
        if status[i] != DONE:
            for j in state.successors[i]:
                pending[j] += 1
    state.pending = pending
    state.eligible = {j for j in range(n) if status[j] == UNSTARTED and pending[j] == 0}

    present = state.present = list(observation.present)
    state.return_day = list(world.return_day)
    state.absent_since = list(observation.absent_since)
    state.announced = list(observation.announced)
    role, busy = state.role, state.busy
    for j in range(n):
        crew = state.assigned[j] = observation.assigned[j]
        if status[j] in (DONE, UNSTARTED):
            continue
        for w in crew:
            busy[w] = j
        workers = tuple(w for w in crew if present[w])
        state.working[j] = workers
        if not state.demands[j]:
            workers_rate, cost = state.unit[j], state.daily_cost[j]
        else:
            workers_rate = len(workers)
            cost = sum(state.wage[w] for w in workers)
        if (status[j] == RUNNING) != (workers_rate > 0):
            raise ValueError(f"activity {j} is {status[j]} with {len(workers)} present members")
        if status[j] == RUNNING:
            state.running.append(j)
            state.open_since[j] = t
            state.rate[j] = workers_rate
            state.work_cost[j] = cost
    state.idle = [
        [w for w, k in enumerate(role) if k == r.id and present[w] and busy[w] < 0]
        for r in instance.roles
    ]
    return state


def crew_member_days(work: float, unit: int) -> int:
    """Work done in crew-member days from full-crew days `work` = done / M_j (an observation's
    `work_done`); every work day adds whole crew-member days, so the result is an integer."""
    units = work * unit
    rounded = round(units)
    if abs(units - rounded) > 1e-6:
        raise ValueError(f"work done {work} is not a whole number of crew-member days of {unit}")
    return rounded


def nominal_activity(observation: Observation, j: int) -> tuple[int, tuple[int, ...]]:
    """Nominal duration p_j and demands of activity j of an observation, D3 activities included."""
    instance = observation.instance
    if j < instance.n_activities:
        act = instance.activities[j]
        return act.duration, act.demands
    inserted = observation.inserted[j - instance.n_activities]
    return inserted.duration, inserted.demands


def work_history(observation: Observation) -> dict[int, list[tuple[int, float, float]]]:
    """Observed changes of the remaining work of every started activity, in crew-member days
    and in the order they happened: (work done at the change, factor, work added).

    A D2 shock multiplies the remaining work by F and adds nothing; a SUBST handover adds its
    m_j o_j = h_j M_j crew-member days with factor 1. At equal work done a handover (step 3)
    comes before a shock (step 5 of the same day, before any progress); shocks and handovers keep
    their observed order (spec section 5.1).
    """
    changes: dict[int, list[tuple[int, int, int, float, float]]] = {}
    for i, (j, work_done, factor) in enumerate(observation.work_increases):
        unit = max(1, sum(nominal_activity(observation, j)[1]))
        entry = (crew_member_days(work_done, unit), 1, i, factor, 0.0)
        changes.setdefault(j, []).append(entry)
    for i, (j, work_done, added) in enumerate(observation.handovers):
        unit = max(1, sum(nominal_activity(observation, j)[1]))
        entry = (crew_member_days(work_done, unit), 0, i, 1.0, float(added))
        changes.setdefault(j, []).append(entry)
    return {
        j: [(at, factor, added) for at, _, _, factor, added in sorted(entries)]
        for j, entries in changes.items()
    }


def nominal_world(observation: Observation) -> SampledWorld:
    """The hidden state with nominal values (spec section 5.2), in crew-member days.

    An unstarted activity has remaining work p_j M_j (inserted ones: their nominal duration).
    A started one starts from p_j M_j and replays its observed changes (`work_history`): before
    each change it loses the work done since the previous one and keeps at least one
    crew-member day; a D2 shock then multiplies the remaining work by F and a SUBST handover
    adds h_j M_j. After the last change it loses the work done since and again keeps at least
    one crew-member day. An absent worker returns on day s + max(L_low, t - s + 1): after the
    announced bound, or tomorrow once it has passed. Temporary workers are never absent.
    """
    history = work_history(observation)
    remaining = [0.0] * len(observation.status)
    for j, status in enumerate(observation.status):
        if status == DONE:
            continue
        nominal, demands = nominal_activity(observation, j)
        unit = max(1, sum(demands))  # M_j crew-member days per full-crew day
        units = float(nominal * unit)
        if status != UNSTARTED:
            before = 0
            for at, factor, added in history.get(j, ()):
                units = max(units - (at - before), 1.0) * factor + added
                before = at
            done = crew_member_days(observation.work_done[j], unit)
            units = max(units - (done - before), 1.0)
        remaining[j] = units
    t = observation.day
    return_day = [-1] * len(observation.present)
    for w in range(len(observation.instance.workers)):
        if observation.present[w]:
            continue
        start, announced = observation.absent_since[w], observation.announced[w]
        if start is None or announced is None:
            raise ValueError(f"absent worker {w} has no absence start or announced bound")
        return_day[w] = start + max(announced, t - start + 1)
    return SampledWorld(tuple(remaining), tuple(return_day))
