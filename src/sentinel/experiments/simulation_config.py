"""Validated configuration of the simulation study runner (e.g. configs/wp2_noreaction.toml)."""

from pathlib import Path
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveInt, model_validator

from sentinel.data.reference import ReferenceKind
from sentinel.simulation.baselines import (
    DEFAULT_CACHE_ROOT,
    BaselineMethod,
    BaselineName,
    CpsatDet,
    SgsLft,
)
from sentinel.simulation.events import DisruptionParams
from sentinel.simulation.uncertainty import PertParams

DURATIONS_ONLY = "durations_only"

Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
MeanAbsence = Annotated[float, Field(ge=1, allow_inf_nan=False)]


def met_column(delta: float) -> str:
    """Results column of the post hoc deadline check for slack delta_D, e.g. `met_0.1`."""
    return f"met_{delta:g}"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SetConfig(_Frozen):
    """An instance set and the PSPLIB reference makespans used as C*."""

    name: str = Field(min_length=1)
    reference: ReferenceKind


class BaselineSettings(_Frozen):
    """Parameters of every baseline method; `sentinel baselines` reads them from the config."""

    cpsat_det: CpsatDet
    sgs_lft: SgsLft = SgsLft()

    def method(self, name: BaselineName) -> BaselineMethod:
        """The configured method called `name`."""
        return self.cpsat_det if name == "cpsat_det" else self.sgs_lft


class Scenario(_Frozen):
    """A named disruption scenario; `mean_absence` is None for `durations_only`."""

    name: str
    disruptions: DisruptionParams
    lambda_a: float
    mean_absence: float | None


class ScenarioGrid(_Frozen):
    """lambda_a x mean_absence with fixed lambda_s and lambda_n; at lambda_a = 0 only the first
    mean_absence (it has no effect there). `durations_only` adds a scenario without disruptions."""

    lambda_a: tuple[Probability, ...] = Field(min_length=1)
    mean_absence: tuple[MeanAbsence, ...] = Field(min_length=1)
    lambda_s: Probability
    lambda_n: Probability
    durations_only: bool = True

    @model_validator(mode="after")
    def _check_distinct(self) -> Self:
        for name, values in (("lambda_a", self.lambda_a), ("mean_absence", self.mean_absence)):
            if len(set(values)) != len(values):
                raise ValueError(f"duplicate {name} values: {values}")
        return self

    def expand(self) -> tuple[Scenario, ...]:
        """Scenarios in table order: `durations_only` first, then by (lambda_a, mean_absence)."""
        scenarios = []
        if self.durations_only:
            none = DisruptionParams.none()
            scenarios.append(
                Scenario(name=DURATIONS_ONLY, disruptions=none, lambda_a=0.0, mean_absence=None)
            )
        for lambda_a in sorted(self.lambda_a):
            for mean_absence in sorted(self.mean_absence)[: 1 if lambda_a == 0 else None]:
                params = DisruptionParams(
                    lambda_a=lambda_a,
                    mean_absence=mean_absence,
                    lambda_s=self.lambda_s,
                    lambda_n=self.lambda_n,
                )
                scenarios.append(
                    Scenario(
                        name=f"la{lambda_a:g}_L{mean_absence:g}",
                        disruptions=params,
                        lambda_a=lambda_a,
                        mean_absence=mean_absence,
                    )
                )
        return tuple(scenarios)


class StudyConfig(_Frozen):
    """NoReaction on baseline plans over sets x scenarios x replications (common random numbers).

    `deltas` are the deadline slacks delta_D evaluated post hoc (spec section 1.2); every run uses
    max_days of the largest one. `beta` is the budget reserve of B.
    """

    name: str = Field(min_length=1)
    base_seed: NonNegativeInt
    max_workers: PositiveInt
    data_root: Path
    baseline_cache: Path = DEFAULT_CACHE_ROOT
    baseline: BaselineName
    baselines: BaselineSettings
    sets: tuple[SetConfig, ...] = Field(min_length=1)
    replications: PositiveInt
    deltas: tuple[float, ...] = Field(min_length=1)
    beta: float = Field(default=0.10, ge=0, allow_inf_nan=False)
    review_period: PositiveInt = 5
    pert: PertParams = PertParams()
    scenarios: ScenarioGrid

    @model_validator(mode="after")
    def _check(self) -> Self:
        names = [s.name for s in self.sets]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"duplicate set names: {duplicates}")
        if list(self.deltas) != sorted(set(self.deltas)) or self.deltas[0] < 0:
            raise ValueError(f"deltas must be distinct, non-negative and ascending: {self.deltas}")
        return self

    @property
    def baseline_method(self) -> BaselineMethod:
        """The method of the plans every run starts from."""
        return self.baselines.method(self.baseline)
