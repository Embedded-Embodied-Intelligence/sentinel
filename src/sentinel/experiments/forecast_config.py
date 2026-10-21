"""Validated configuration of the forecast study runner (configs/wp3_calibration.toml, ...)."""

from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    model_validator,
)

from sentinel.experiments.simulation_config import SetConfig, StudyConfig
from sentinel.forecasting.forecast import Priors
from sentinel.simulation.events import DisruptionParams
from sentinel.simulation.state import Observation
from sentinel.simulation.uncertainty import PertParams

Share = Annotated[float, Field(ge=0, lt=1, allow_inf_nan=False)]
Threshold = Annotated[float, Field(gt=0, le=1, allow_inf_nan=False)]
Name = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]+$")]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ForecastSetConfig(SetConfig):
    """An instance set; `stride` k keeps every k-th instance in natural order (1 = all)."""

    stride: PositiveInt = 1


class ForecasterSpec(_Frozen):
    """A forecaster of spec section 5.2: `monte_carlo` rollouts (spec 5.1) or `deterministic`.

    `prior_scale` (kappa) multiplies the forecaster's (lambda_A, lambda_S, lambda_N) and
    `prior_pert` replaces its PERT; both default to the observation's own priors.
    """

    name: Name
    kind: Literal["monte_carlo", "deterministic"]
    n_rollouts: PositiveInt = 200
    future_disruptions: bool = True
    prior_scale: PositiveFloat = 1.0
    prior_pert: PertParams | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.kind == "deterministic" and (
            self.prior_scale != 1.0 or self.prior_pert is not None
        ):
            raise ValueError(f"forecaster {self.name}: the deterministic one takes no priors")
        return self

    def priors(self, observation: Observation) -> Priors | None:
        """The priors passed to `forecast`; None keeps the observation's own."""
        if self.prior_scale == 1.0 and self.prior_pert is None:
            return None
        own = observation.disruptions
        scaled = own.model_dump() | {
            "lambda_a": self.prior_scale * own.lambda_a,
            "lambda_s": self.prior_scale * own.lambda_s,
            "lambda_n": self.prior_scale * own.lambda_n,
        }
        return Priors(
            pert=self.prior_pert or observation.pert,
            disruptions=DisruptionParams.model_validate(scaled),
        )


class SummarySettings(_Frozen):
    """Metric parameters (spec section 5.2) and output names of the generated summaries.

    `differences` lists forecaster pairs (a, b) whose paired differences a - b get intervals;
    `reliability_checkpoints` are the shares f shown in the reliability diagrams and
    `headline_checkpoints` those of the headline table. Early warning counts the checkpoints
    f >= `warning_from`; f = 0 is reported as plan-stage risk. `reference_run` is the directory
    of another run on the same worlds whose `reference_forecasters` are added to every table.
    """

    bins: PositiveInt = 10
    thresholds: tuple[Threshold, ...] = Field(default=(0.5, 0.8), min_length=1)
    warning_from: Share = 0.2
    log_clip: float = Field(default=0.005, gt=0, lt=0.5)
    bootstrap_resamples: PositiveInt = 1000
    bootstrap_seed: NonNegativeInt = 2026
    pit_seed: NonNegativeInt = 2026
    differences: tuple[tuple[str, str], ...] = ()
    reliability_checkpoints: tuple[Share, ...] = (0.0, 0.4, 0.8)
    headline_checkpoints: tuple[Share, ...] = (0.0, 0.4, 0.8)
    reference_run: Path | None = None
    reference_forecasters: tuple[Name, ...] = ()
    table: Name = "table_wp3_calibration"
    warning_table: Name = "table_wp3_warning"
    plan_stage_table: Name = "table_wp3_plan_stage"
    headline_table: Name = "table_wp3_headline"
    figure_prefix: Name = "fig_wp3"

    @model_validator(mode="after")
    def _check_reference(self) -> Self:
        if (self.reference_run is None) != (not self.reference_forecasters):
            raise ValueError("reference_run and reference_forecasters must be given together")
        if len(set(self.reference_forecasters)) != len(self.reference_forecasters):
            raise ValueError(f"duplicate reference forecasters: {self.reference_forecasters}")
        return self


class ForecastStudyConfig(StudyConfig):
    """Forecasts at checkpoints of NoReaction worlds (spec section 5.2), scored post hoc.

    The world runs, seeds and scenario names follow the WP2b study (`StudyConfig`): replication
    r of an instance uses the same seed in every scenario. `checkpoints` are the shares f of the
    baseline makespan, `wp2b_results` the WP2b results file whose makespans the worlds must
    reproduce (None skips the check).
    """

    sets: tuple[ForecastSetConfig, ...] = Field(min_length=1)
    checkpoints: tuple[Share, ...] = Field(min_length=1)
    forecasters: tuple[ForecasterSpec, ...] = Field(min_length=1)
    wp2b_results: Path | None = None
    summary: SummarySettings = SummarySettings()

    @model_validator(mode="after")
    def _check_forecasts(self) -> Self:
        if list(self.checkpoints) != sorted(set(self.checkpoints)):
            raise ValueError(f"checkpoints must be distinct and ascending: {self.checkpoints}")
        names = [f.name for f in self.forecasters]
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate forecaster names: {names}")
        unknown = {n for pair in self.summary.differences for n in pair} - set(names)
        if unknown:
            raise ValueError(f"differences name unknown forecasters: {sorted(unknown)}")
        for kind, shares in (
            ("reliability", self.summary.reliability_checkpoints),
            ("headline", self.summary.headline_checkpoints),
        ):
            missing = set(shares) - set(self.checkpoints)
            if missing:
                raise ValueError(f"{kind} checkpoints {sorted(missing)} are not checkpoints")
        clash = set(self.summary.reference_forecasters) & set(names)
        if clash:
            raise ValueError(f"reference forecasters {sorted(clash)} are forecasters of this run")
        return self
