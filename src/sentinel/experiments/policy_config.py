"""Validated configuration of the policy study runner (configs/wp4_baselines.toml, ...)."""

from pathlib import Path
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    model_validator,
)

from sentinel.experiments.forecast_config import ForecastSetConfig
from sentinel.experiments.simulation_config import StudyConfig
from sentinel.policies.registry import COMPARED, make_policy
from sentinel.policies.resolve import T_CP

Name = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]+$")]


class PolicySummarySettings(BaseModel):
    """Settings of the generated summaries: the cluster bootstrap over the instances of a set,
    the policy that paired differences are taken against, and the output names."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bootstrap_resamples: PositiveInt = 1000
    bootstrap_seed: NonNegativeInt = 2026
    reference_policy: Name = "no_reaction"
    table: Name = "table_wp4"
    figure_prefix: Name = "fig_wp4"


class PolicyStudyConfig(StudyConfig):
    """The compared policies of spec section 7 on baseline plans (RQ4), scored post hoc.

    Runs, seeds and scenario names follow the WP2b study (`StudyConfig`): replication r of an
    instance uses the same seed in every scenario and for every policy (common random numbers).
    Each set keeps every `stride`-th instance, and the scenarios have one E[L], so that the
    summaries can plot against lambda_A. `policies` are registry names (`make_policy`),
    run with the CP-SAT limit `deterministic_time_limit` (T_cp, spec section 8) per stage and
    `cp_seed`; `wp2b_results` is the WP2b results file whose seeds and makespans the NoReaction
    runs must reproduce (None skips the check).
    """

    sets: tuple[ForecastSetConfig, ...] = Field(min_length=1)
    policies: tuple[Name, ...] = Field(default=COMPARED, min_length=1)
    deterministic_time_limit: PositiveFloat = T_CP
    cp_seed: NonNegativeInt = 0
    wp2b_results: Path | None = None
    summary: PolicySummarySettings = PolicySummarySettings()

    @model_validator(mode="after")
    def _check_policies(self) -> Self:
        if len(set(self.policies)) != len(self.policies):
            raise ValueError(f"duplicate policies: {self.policies}")
        for name in self.policies:
            make_policy(name)  # raises ValueError for an unknown name
        if len(self.scenarios.mean_absence) != 1:
            raise ValueError(f"need one mean_absence, got {self.scenarios.mean_absence}")
        if self.summary.reference_policy not in self.policies:
            raise ValueError(
                f"reference policy {self.summary.reference_policy!r} is not among the policies"
            )
        return self
