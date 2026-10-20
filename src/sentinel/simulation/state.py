"""Mutable engine state and the agent's frozen observation of it (spec section 3)."""

from bisect import insort
from collections.abc import Sequence
from typing import Final, Literal, NamedTuple

from pydantic import BaseModel, ConfigDict, NonNegativeInt

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
    """Days `start .. end - 1` on which `activity` progressed with `workers` without a pause."""

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
    `inserted`); per-worker tuples by worker id. `assigned` holds the current workers of a
    running activity, the original workers of a paused one and the last workers of a finished
    one. `work_increases` lists every observed D2 shock as (activity, work done, factor F).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    day: NonNegativeInt
    instance: ProjectInstance
    inserted: tuple[InsertedActivity, ...]
    plan: tuple[int, ...]
    status: tuple[ActivityStatus, ...]
    work_done: tuple[NonNegativeInt, ...]
    start: tuple[int | None, ...]
    finish: tuple[int | None, ...]
    assigned: tuple[tuple[int, ...], ...]
    work_increases: tuple[tuple[int, int, float], ...]
    present: tuple[bool, ...]
    absent_since: tuple[int | None, ...]
    announced: tuple[int | None, ...]  # L_low of the current absence
    cost: float
    deadline: int | None
    pert: PertParams
    disruptions: DisruptionParams


class EngineState:
    """Mutable state of one run in plain lists (spec section 3), hidden quantities included.

    Hidden: `remaining` (true remaining work), `return_day` (true end of an absence) and
    `next_shock`/`shock_factor` (the next D2 shock). Only `observe()` passes information to a
    policy. Per-activity lists are indexed by activity id and grow with D3 insertions.
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
        "duration",
        "eligible",
        "finish",
        "idle",
        "inserted",
        "instance",
        "next_shock",
        "open_since",
        "pending",
        "pert",
        "plan",
        "present",
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
        "work_done",
        "work_increases",
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
    ) -> None:
        acts = instance.activities
        n = len(acts)
        self.instance = instance
        self.pert = pert
        self.disruptions = disruptions
        self.deadline = deadline
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
        self.successors = [list(act.successors) for act in acts]
        self.pending = [len(instance.predecessors(j)) for j in range(n)]  # unfinished preds
        self.status: list[ActivityStatus] = [UNSTARTED] * n
        self.work_done = [0] * n
        self.remaining = list(durations)
        self.plan = list(plan.starts)
        self.start: list[int | None] = [None] * n
        self.finish: list[int | None] = [None] * n
        self.assigned: list[tuple[int, ...]] = [()] * n
        self.open_since = [-1] * n  # first day of the current work segment
        self.next_shock = [0] * n  # work-day counter of the next D2 shock, 0 if none
        self.shock_factor = [0.0] * n
        self.segments: list[WorkSegment] = []

        self.role = [worker.role for worker in instance.workers]
        n_workers = len(self.role)
        self.present = [True] * n_workers
        self.return_day = [-1] * n_workers
        self.absent_since: list[int | None] = [None] * n_workers
        self.announced: list[int | None] = [None] * n_workers
        self.busy = [-1] * n_workers  # activity the worker works on, -1 if idle
        # idle[k]: present idle workers of role k in increasing id order
        self.idle = [[w for w, k in enumerate(self.role) if k == r.id] for r in instance.roles]

        self.running: list[int] = []  # increasing ids
        self.eligible = {j for j in range(n) if self.pending[j] == 0}  # unstarted or paused
        self.inserted: list[InsertedActivity] = []
        self.work_increases: list[tuple[int, int, float]] = []

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
        self.duration.append(duration)
        self.demands.append(dem)
        self.daily_cost.append(sum(self.role_costs[k] * r for k, r in dem))
        self.successors[predecessor].append(new)
        self.successors.append([successor])
        self.pending.append(0 if self.status[predecessor] == DONE else 1)
        self.pending[successor] += 1
        self.eligible.discard(successor)
        self.status.append(UNSTARTED)
        self.work_done.append(0)
        self.remaining.append(true_duration)
        self.plan.append(plan_start)
        self.start.append(None)
        self.finish.append(None)
        self.assigned.append(())
        self.open_since.append(-1)
        self.next_shock.append(0)
        self.shock_factor.append(0.0)
        if self.pending[new] == 0:
            self.eligible.add(new)
            self.changed = True
        return new

    def release(self, j: int) -> None:
        """Make the workers of activity j idle again; absent ones stay unavailable."""
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
            work_done=tuple(self.work_done),
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
