"""Domain models of a live project (spec section 11.2-11.3): team, tasks, settings and the
reports of a check-in, as the project manager enters them.

The models check types and shapes only, so that a draft with mistakes can be stored and shown
with its issues; the project's validity (names, dependencies, crews, deadline) is checked by
`live.validate_definition`, which explains every issue in plain language.
"""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from sentinel.simulation.events import DisruptionParams
from sentinel.simulation.uncertainty import PertParams

Key = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,39}$")]
Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]
Estimation = Literal["confident", "typical", "uncertain"]
Disruptions = Literal["calm", "typical", "turbulent"]
Language = Literal["en", "pl"]

# PERT multipliers (a, m, b) of the estimation-uncertainty presets (spec section 11.2).
ESTIMATION_PRESETS: dict[Estimation, tuple[float, float, float]] = {
    "confident": (0.9, 1.0, 1.3),
    "typical": (0.8, 1.0, 1.6),
    "uncertain": (0.7, 1.0, 2.0),
}
# lambda_A of the disruption-rate presets; lambda_S, lambda_N and E[L] are common to all.
DISRUPTION_PRESETS: dict[Disruptions, float] = {
    "calm": 0.005,
    "typical": 0.01,
    "turbulent": 0.02,
}
LAMBDA_S = 0.01
LAMBDA_N = 0.02
MEAN_ABSENCE = 3.0
DEFAULT_SEED = 2026
BUDGET_RESERVE = 0.10  # beta of the default budget (spec section 1.2)


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Person(_Frozen):
    """A team member: a stable key, a display name and a role (free text)."""

    key: Key
    name: Text
    role: Text


class RoleCost(_Frozen):
    """The daily cost c_k of one person of a role, in cost units (default 1.0)."""

    role: Text
    daily_cost: float = Field(default=1.0, ge=0, allow_inf_nan=False)


class Task(_Frozen):
    """A task: duration in working days, people per role, predecessors by key, optional flag."""

    key: Key
    name: Text
    duration: int
    crew: dict[str, int] = Field(default_factory=dict)
    predecessors: tuple[str, ...] = ()
    optional: bool = False


class Advanced(_Frozen):
    """Advanced settings: values that replace those of the presets (spec section 11.2)."""

    pert_a: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    pert_m: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    pert_b: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    lambda_a: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    lambda_s: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    lambda_n: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    mean_absence: float | None = Field(default=None, ge=1, allow_inf_nan=False)


class Settings(_Frozen):
    """The project's settings: presets, autonomy Lambda, the seed of its forecasts and
    deliberations, and the optional LLM features (off by default)."""

    estimation: Estimation = "typical"
    disruptions: Disruptions = "typical"
    advanced: Advanced = Advanced()
    autonomy: int = Field(default=2, ge=0, le=3)
    seed: int = Field(default=DEFAULT_SEED, ge=0, lt=2**31)
    llm_explanations: bool = False
    llm_proposals: bool = False
    language: Language = "en"

    def pert(self) -> PertParams:
        """The PERT multiplier of the estimation preset with the advanced overrides."""
        a, m, b = ESTIMATION_PRESETS[self.estimation]
        extra = self.advanced
        return PertParams(
            a=a if extra.pert_a is None else extra.pert_a,
            m=m if extra.pert_m is None else extra.pert_m,
            b=b if extra.pert_b is None else extra.pert_b,
        )

    def disruption_params(self) -> DisruptionParams:
        """The disruption rates of the preset with the advanced overrides (spec 2.2, 11.2)."""
        extra = self.advanced
        return DisruptionParams(
            lambda_a=DISRUPTION_PRESETS[self.disruptions]
            if extra.lambda_a is None
            else extra.lambda_a,
            mean_absence=MEAN_ABSENCE if extra.mean_absence is None else extra.mean_absence,
            lambda_s=LAMBDA_S if extra.lambda_s is None else extra.lambda_s,
            lambda_n=LAMBDA_N if extra.lambda_n is None else extra.lambda_n,
        )


class ProjectDefinition(_Frozen):
    """A live project as the manager defines it (spec section 11.2)."""

    name: Text
    start: date
    deadline: date | None = None
    budget: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    team: tuple[Person, ...] = ()
    roles: tuple[RoleCost, ...] = ()
    tasks: tuple[Task, ...] = ()
    settings: Settings = Settings()

    def structure(self) -> tuple[object, ...]:
        """What the baseline plan depends on: the team's roles and the tasks, names aside."""
        team = tuple((p.key, p.role) for p in self.team)
        tasks = tuple(
            (t.key, t.duration, tuple(sorted(t.crew.items())), t.predecessors, t.optional)
            for t in self.tasks
        )
        return team, tasks


TaskStatus = Literal["not_started", "in_progress", "done"]


class TaskReport(_Frozen):
    """The state of one task at a check-in: not started, in progress with the percentage done,
    or done with its finish date (the last day of work); a started task may carry its start date
    and its crew (person keys), else they are derived (spec section 11.3)."""

    task: str
    status: TaskStatus
    percent: float | None = Field(default=None, allow_inf_nan=False)
    start: date | None = None
    finish: date | None = None
    crew: tuple[str, ...] | None = None


class AbsenceReport(_Frozen):
    """An absence: who, from which day, and the announced return date (none if unknown). There
    is no field for a reason (CLAUDE.md invariant 7, GDPR Art. 9)."""

    person: str
    first_day: date
    return_date: date | None = None


class WorkIncreaseReport(_Frozen):
    """More work for a task in progress: `extra_days` more working days or a `factor` > 1."""

    task: str
    extra_days: float | None = Field(default=None, allow_inf_nan=False)
    factor: float | None = Field(default=None, allow_inf_nan=False)


class NewTaskReport(_Frozen):
    """A task that came up, inserted after the task `after` (None: can start right away) and
    before the task `before` (None: before the end of the project)."""

    key: Key | None = None
    name: Text
    duration: int
    crew: dict[str, int] = Field(default_factory=dict)
    after: str | None = None
    before: str | None = None
    optional: bool = False


class CheckIn(_Frozen):
    """A check-in: the state at the end of `date` (spec section 11.1, 11.3)."""

    date: date
    tasks: tuple[TaskReport, ...] = ()
    absences: tuple[AbsenceReport, ...] = ()
    increases: tuple[WorkIncreaseReport, ...] = ()
    new_tasks: tuple[NewTaskReport, ...] = ()
