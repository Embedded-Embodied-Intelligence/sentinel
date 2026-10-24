"""Simulator projects (spec section 11.6): a PSPLIB instance shown with the IT role names, the
narrator's task names and a roster of people (WP6), its hidden world fixed by a seed, run day
by day under a chosen policy next to NoReaction on the same seed (common random numbers).

`Simulation` builds the engine state and the day loop exactly as `simulate` does and executes
the days through the loop's own `open_day`/`close_day`, so a run advanced to its end equals
`simulate` with the same plan, policy and seed. The world seed of scenario r is that of
replication r in the studies, derive_seed(2026, set, instance, str(r)); the baseline plan is the
studies' cached `cpsat_det` plan, the deadline D = ceil((1 + delta_D) C*) with C* the reference
makespan of the instance (the plan's if there is none), and the budget that of spec section 1.2.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from sentinel.agent.params import SentinelParams
from sentinel.app.calendar import WorkCalendar
from sentinel.app.models import ESTIMATION_PRESETS, Disruptions, Estimation, Settings
from sentinel.dashboard.world import Observed
from sentinel.data.psplib_loader import instance_path, list_instances, load_psplib
from sentinel.data.reference import ReferenceKind, load_reference, reference_path
from sentinel.experiments.policy_runs import WP2B_BASELINE
from sentinel.experiments.runs import derive_seed
from sentinel.interpret.team import names_of, roster
from sentinel.model import ProjectInstance
from sentinel.policies.base import Policy
from sentinel.policies.registry import make_policy
from sentinel.policies.sentinel import Sentinel
from sentinel.simulation.baselines import BaselinePlan, cached_baseline
from sentinel.simulation.engine import Run, SimulationResult
from sentinel.simulation.events import DisruptionParams, ScenarioStreams
from sentinel.simulation.state import (
    DONE,
    HANDOVER_FACTOR,
    PAUSED,
    REMOVED,
    RUNNING,
    EngineState,
    Observation,
    day_limit,
)
from sentinel.simulation.uncertainty import (
    PertParams,
    derive_budget,
    derive_deadline,
    role_costs,
)
from sentinel.wbs.narrate import role_names

BASE_SEED = 2026  # world seeds of the studies (WP2b)
REVIEW_PERIOD = 5  # T_r (spec section 8)
T_CP = 0.1  # deterministic CP-SAT limit of the policies (spec section 8)
SETS = ("j30", "j60")
SimPolicy = Literal[
    "sentinel",
    "no_reaction",
    "always_substitute",
    "full_resolve",
    "full_resolve_subst",
    "stable_resolve_subst",
]
POLICIES: tuple[SimPolicy, ...] = (
    "sentinel",
    "no_reaction",
    "always_substitute",
    "full_resolve",
    "full_resolve_subst",
    "stable_resolve_subst",
)


class SimulatorSpec(BaseModel):
    """A simulator project as created (spec section 11.6)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(default="", max_length=120)
    set_name: Literal["j30", "j60"] = "j30"
    instance: str = Field(pattern=r"^j[0-9]{2,3}[0-9]+_[0-9]+$")
    scenario: int = Field(default=0, ge=0, lt=10_000)
    start: date
    estimation: Estimation = "typical"
    disruptions: Disruptions = "typical"
    delta_d: float = Field(default=0.2, ge=0, le=2)
    policy: SimPolicy = "sentinel"
    autonomy: int = Field(default=2, ge=0, le=3)

    @property
    def seed(self) -> int:
        """The world seed: that of replication `scenario` in the studies (WP2b)."""
        return derive_seed(BASE_SEED, self.set_name, self.instance, str(self.scenario))

    @property
    def pert(self) -> PertParams:
        a, m, b = ESTIMATION_PRESETS[self.estimation]
        return PertParams(a=a, m=m, b=b)

    @property
    def disruption_params(self) -> DisruptionParams:
        return Settings(disruptions=self.disruptions).disruption_params()

    @property
    def names_seed(self) -> int:
        """The seed of the task and people names, the same for every scenario of an instance."""
        return derive_seed(BASE_SEED, "names", self.set_name, self.instance)


@dataclass(frozen=True)
class World:
    """The instance, its plan and goals, and the names shown for roles, tasks and people."""

    spec: SimulatorSpec
    instance: ProjectInstance
    plan: BaselinePlan
    c_star: int
    reference: ReferenceKind | None
    deadline: int
    budget: float
    roles: tuple[str, ...]
    people: tuple[str, ...]

    @property
    def calendar(self) -> WorkCalendar:
        return WorkCalendar(self.spec.start)


def available(set_name: str, root: Path) -> list[str]:
    """The instances of a set in the data root (none if the data are missing)."""
    try:
        return list_instances(set_name, root)
    except FileNotFoundError:
        return []


def build_world(spec: SimulatorSpec, root: Path, cache: Path) -> World:
    """The world of a simulator project; FileNotFoundError without the PSPLIB data."""
    path = instance_path(spec.set_name, spec.instance, root)
    if not path.is_file():
        raise FileNotFoundError(path)
    instance = load_psplib(path)
    plan = cached_baseline(instance, WP2B_BASELINE, cache)[0]
    c_star, reference = plan.makespan, None
    kinds: tuple[ReferenceKind, ...] = ("opt", "hrs")
    for kind in kinds:
        if reference_path(spec.set_name, kind, root).is_file():
            value = load_reference(spec.set_name, kind, root).get(instance.name)
            if value is not None and value > 0:
                c_star, reference = value, kind
                break
    return World(
        spec=spec,
        instance=instance,
        plan=plan,
        c_star=c_star,
        reference=reference,
        deadline=derive_deadline(c_star, spec.delta_d),
        budget=derive_budget(instance, 0.10, params=spec.pert),
        roles=role_names(instance),
        people=tuple(member.name for member in roster(instance, spec.names_seed)),
    )


def policy_of(spec: SimulatorSpec, name: str) -> Policy:
    """A fresh policy: Sentinel (full variant, autonomy Lambda, spec section 8) or a baseline of
    the registry (spec section 7), with the CP-SAT settings of the policies."""
    if name == "sentinel":
        params = SentinelParams(autonomy=spec.autonomy, deterministic_time_limit=T_CP)
        return Observed(Sentinel(params, seed=spec.seed))
    return make_policy(name, deterministic_time_limit=T_CP, seed=0, run_seed=spec.seed)


class PolicyRun:
    """One policy on the world, advanced day by day by the engine's own loop (`Run`)."""

    def __init__(self, world: World, name: str) -> None:
        spec = world.spec
        self.world = world
        self.name = name
        self.policy = policy_of(spec, name)
        self.streams = ScenarioStreams(spec.seed, world.instance, spec.disruption_params, spec.pert)
        instance = world.instance
        self.state = EngineState(
            instance,
            world.plan.schedule,
            self.streams.durations,
            role_costs(instance, None),
            pert=spec.pert,
            disruptions=spec.disruption_params,
            deadline=world.deadline,
            max_days=day_limit(instance, world.deadline),
            handover_factor=HANDOVER_FACTOR,
            budget=world.budget,
        )
        self.run = Run(self.state, self.streams, self.policy, review_period=REVIEW_PERIOD)
        self.day = 0  # the next day to execute
        self.finished = False

    def advance(self, days: int) -> int:
        """Execute up to `days` more days (spec section 3); returns the days executed."""
        run, state = self.run, self.state
        done = 0
        while done < days and not self.finished:
            t = self.day
            if t > state.max_days:
                self.finished = True
                break
            self.finished = run.close_day(t, run.open_day(t))
            self.day = t + 1
            done += 1
            if self.day > state.max_days:
                self.finished = True
        return done

    def result(self) -> SimulationResult:
        """The run's result (spec section 3.1 f); the same as `simulate` once finished."""
        return self.run.result(self.world.spec.seed)

    @property
    def sentinel(self) -> Sentinel | None:
        policy = self.policy
        inner = policy.policy if isinstance(policy, Observed) else policy
        return inner if isinstance(inner, Sentinel) else None

    @property
    def observations(self) -> dict[int, Observation]:
        return dict(self.policy.observations) if isinstance(self.policy, Observed) else {}


class Simulation:
    """A simulator project's two runs: the chosen policy and NoReaction on the same seed."""

    def __init__(self, world: World) -> None:
        self.world = world
        self.main = PolicyRun(world, world.spec.policy)
        self.compare = (
            PolicyRun(world, "no_reaction") if world.spec.policy != "no_reaction" else None
        )
        self.days = 0

    @property
    def runs(self) -> tuple[PolicyRun, ...]:
        return (self.main,) if self.compare is None else (self.main, self.compare)

    @property
    def finished(self) -> bool:
        return all(run.finished for run in self.runs)

    def advance(self, days: int, progress: Callable[[float], None] | None = None) -> int:
        """Advance both runs by `days` days, one day at a time; returns the days advanced."""
        moved = 0
        for _ in range(days):
            if self.finished:
                break
            for run in self.runs:
                run.advance(1)
            moved += 1
            if progress is not None:
                progress(moved / days)
        self.days += moved
        return moved


# --------------------------------------------------------------------------- views


class SimTask(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: int
    name: str
    duration: int
    state: Literal["not_started", "in_progress", "paused", "done", "removed"]
    percent: float | None
    planned_start: date | None
    start: date | None
    finish: date | None
    crew: list[str]
    added: bool


class SimSide(BaseModel):
    """One run at the current day, and its outcome once finished."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    policy: str
    day: int
    finished: bool
    done_tasks: int
    tasks_total: int
    cost: float
    cost_ratio: float
    plan_changes: int
    moved_starts: int
    hired: int
    substituted: int
    deliberations: int | None
    escalations: int | None
    makespan: int | None
    finish: date | None
    on_time: bool | None
    late_days: int | None
    tasks: list[SimTask]


class SimulatorView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    kind: Literal["simulator"] = "simulator"
    name: str
    seq: int
    spec: SimulatorSpec
    instance: str
    roles: list[str]
    team: int
    deadline: date
    deadline_day: int
    budget: float
    c_star: int
    reference: str | None
    baseline_finish: date
    days: int
    as_of: date
    finished: bool
    main: SimSide
    compare: SimSide | None


def side_view(run: PolicyRun) -> SimSide:
    world, state = run.world, run.state
    calendar = world.calendar
    names = names_of(state.observe(), world.spec.names_seed)
    people = list(world.people)
    n_people = len(people)
    shocks: dict[int, float] = {}
    for j, _, factor in state.work_increases:
        shocks[j] = shocks.get(j, 1.0) * factor
    tasks = []
    real = [j for j in range(1, len(state.status)) if j != state.sink]
    for j in real:
        status = state.status[j]
        if status == RUNNING:
            shown: Literal["not_started", "in_progress", "paused", "done", "removed"] = (
                "in_progress"
            )
        elif status == PAUSED:
            shown = "paused"
        elif status == DONE:
            shown = "done"
        elif status == REMOVED:
            shown = "removed"
        else:
            shown = "not_started"
        duration = state.duration[j]
        percent = None
        if shown in ("in_progress", "paused") and duration > 0:
            total = duration * shocks.get(j, 1.0) * state.unit[j]
            percent = round(min(99.9, 100 * state.done[j] / total), 1)
        start, finish = state.start[j], state.finish[j]
        crew = [
            people[w] if w < n_people else f"Temporary {world.roles[state.role[w]]}"
            for w in state.assigned[j]
        ]
        tasks.append(
            SimTask(
                id=j,
                name=names.get(j, f"Task {j}"),
                duration=duration,
                state=shown,
                percent=percent,
                planned_start=calendar.date_of(state.plan[j]) if shown == "not_started" else None,
                start=None if start is None else calendar.date_of(start),
                finish=None if finish is None else calendar.finish_date(finish),
                crew=crew,
                added=j >= world.instance.n_activities,
            )
        )
    sentinel = run.sentinel
    run_view = run.run
    makespan = finish_date = on_time = late = None
    if run.finished:
        result = run.result()
        makespan = result.makespan
        finish_date = calendar.finish_date(makespan)
        on_time = not result.truncated and makespan <= world.deadline
        late = max(0, makespan - world.deadline)
    return SimSide(
        policy=run.name,
        day=run.day,
        finished=run.finished,
        done_tasks=sum(t.state == "done" for t in tasks),
        tasks_total=len(tasks),
        cost=state.cost,
        cost_ratio=state.cost / world.budget,
        plan_changes=run_view.reseqs + run_view.shifts,
        moved_starts=run_view.nervousness,
        hired=len(state.temporary),
        substituted=sum(len(s.replaced) for s in run_view.substitutions),
        deliberations=None if sentinel is None else sentinel.stats.deliberations,
        escalations=None if sentinel is None else sentinel.stats.escalations,
        makespan=makespan,
        finish=finish_date,
        on_time=on_time,
        late_days=late,
        tasks=tasks,
    )


def simulator_view(project_id: str, seq: int, simulation: Simulation) -> SimulatorView:
    world = simulation.world
    spec = world.spec
    calendar = world.calendar
    return SimulatorView(
        id=project_id,
        name=spec.name or f"{spec.set_name}/{spec.instance}",
        seq=seq,
        spec=spec,
        instance=world.instance.name,
        roles=list(world.roles),
        team=len(world.instance.workers),
        deadline=calendar.finish_date(world.deadline),
        deadline_day=world.deadline,
        budget=world.budget,
        c_star=world.c_star,
        reference=world.reference,
        baseline_finish=calendar.finish_date(world.plan.makespan),
        days=simulation.days,
        as_of=calendar.date_of(simulation.days),
        finished=simulation.finished,
        main=side_view(simulation.main),
        compare=None if simulation.compare is None else side_view(simulation.compare),
    )
