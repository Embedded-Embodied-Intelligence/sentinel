"""Mutable engine state and the agent's frozen observation of it (spec section 3)."""

import operator
from bisect import insort
from collections.abc import Sequence
from typing import Final, Literal, NamedTuple

from pydantic import BaseModel, ConfigDict, NonNegativeFloat, NonNegativeInt

from sentinel.model.instance import ProjectInstance
from sentinel.model.schedule import Schedule
from sentinel.simulation.events import DisruptionParams
from sentinel.simulation.uncertainty import PertParams

ActivityStatus = Literal["unstarted", "running", "paused", "done"]
UNSTARTED: Final = "unstarted"
RUNNING: Final = "running"
PAUSED: Final = "paused"
DONE: Final = "done"


class WorkSegment(NamedTuple):
    """Days `start .. end - 1` on which `activity` progressed with the same present crew members
    `workers` (spec section 3.1 a); a pause or a change of the present members starts a new one.
    """

    activity: int
    start: int
    end: int
    workers: tuple[int, ...]


class InsertedActivity(BaseModel):
    """A D3 activity as announced to the agent: nominal data only, true duration hidden."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: NonNegativeInt
    day: NonNegativeInt
    duration: NonNegativeInt
    demands: tuple[NonNegativeInt, ...]
    predecessor: NonNegativeInt
    successor: NonNegativeInt


class Observation(BaseModel):
    """What the agent may see on `day` (spec section 3): no true durations, no true absence
    lengths, no future events.

    Per-activity tuples are indexed by activity id (the instance's ids, then the D3 ids in
    `inserted`); per-worker tuples by worker id. `work_done` is e_j in full-crew days.
    `assigned` holds the crew of every started activity, reserved until it completes, absent
    members included (spec section 3.1 a). `work_increases` lists every observed D2 shock as
    (activity, e_j before the shock, factor F).
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


class EngineState:
    """Mutable state of one run in plain lists (spec section 3), hidden quantities included.

    Work is counted in crew-member days: a full-crew day of activity j is `unit[j]` = M_j units
    (1 for an activity without demands), and a work day with c present crew members does c
    units, so rho_j = c / M_j (spec section 3.1 a) needs no fractions and remaining work hits
    zero exactly; only D2 factors make it fractional. Hidden: `remaining` (true remaining work),
    `return_day` (true end of an absence) and `next_shock`/`shock_factor` (the next D2 shock).
    Only `observe()` passes information to a policy. Per-activity lists are indexed by activity
    id and grow with D3 insertions.
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
        "idle",
        "inserted",
        "instance",
        "max_days",
        "next_shock",
        "open_since",
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
        "unit",
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
    ) -> None:
        acts = instance.activities
        n = len(acts)
        self.instance = instance
        self.pert = pert
        self.disruptions = disruptions
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
        # idle[k]: present workers of role k in no crew, in increasing id order
        self.idle = [[w for w, k in enumerate(self.role) if k == r.id] for r in instance.roles]

        self.running: list[int] = []  # increasing ids
        self.eligible = {j for j in range(n) if self.pending[j] == 0}  # unstarted only
        self.inserted: list[InsertedActivity] = []
        self.work_increases: list[tuple[int, float, float]] = []

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
        """Dissolve the crew of the completed activity j; its present members become idle."""
        busy, present, idle, role = self.busy, self.present, self.idle, self.role
        self.changed = True
        for w in self.assigned[j]:
            busy[w] = -1
            if present[w]:
                insort(idle[role[w]], w)

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
        )
