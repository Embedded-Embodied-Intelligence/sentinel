"""Validated configuration of the policy study runner (configs/wp4_baselines.toml,
configs/wp5_rq4_main.toml, ...)."""

from pathlib import Path
from typing import Annotated, Any, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    model_validator,
)

from sentinel.agent.params import SentinelParams
from sentinel.experiments.forecast_config import ForecastSetConfig
from sentinel.experiments.policy_runs import SentinelVariant
from sentinel.experiments.simulation_config import StudyConfig
from sentinel.policies.registry import COMPARED, make_policy
from sentinel.policies.resolve import T_CP

Name = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]+$")]
# Keys of a variant table that are not Sentinel parameters.
VARIANT_KEYS = ("delta_d", "optional_share")


class PolicySummarySettings(BaseModel):
    """Settings of the generated summaries: the cluster bootstrap over the instances of a set,
    the policies that paired differences are taken against (`reference_policy`, then
    `references`) and the output names."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bootstrap_resamples: PositiveInt = 1000
    bootstrap_seed: NonNegativeInt = 2026
    reference_policy: Name = "no_reaction"
    references: tuple[Name, ...] = ()
    table: Name = "table_wp4"
    figure_prefix: Name = "fig_wp4"

    @property
    def reference_policies(self) -> tuple[str, ...]:
        """Every policy that paired differences are taken against, the main one first."""
        return tuple(dict.fromkeys((self.reference_policy, *self.references)))


class PolicyStudyConfig(StudyConfig):
    """The compared policies of spec section 7 on baseline plans (RQ4), scored post hoc, and
    Sentinel variants (spec sections 4-6).

    Runs, seeds and scenario names follow the WP2b study (`StudyConfig`): replication r of an
    instance uses the same seed in every scenario and for every policy (common random numbers).
    Each set keeps every `stride`-th instance, and the scenarios have one E[L], so that the
    summaries can plot against lambda_A. `policies` are registry names (`make_policy`) or names
    of `variants`, run with the CP-SAT limit `deterministic_time_limit` (T_cp, spec section 8)
    per stage and `cp_seed`. A variant is Sentinel with the parameters of the `sentinel` table
    updated by its own, the deadline slack `delta_d` it works towards (default 0.2) and the
    share `optional_share` of optional activities for DESCOPE (default 0). `wp2b_results` is the
    WP2b results file whose seeds and makespans the NoReaction runs must reproduce (None skips
    the check). `wp4b_results` is the results file of an earlier policy study: the summaries
    read its `joined` policies on the run's worlds instead of running them, after checking its
    seeds and NoReaction makespans against the run's NoReaction rows. Without `start_estimate`
    the runner skips its up-front timing probe (long for Sentinel).
    """

    sets: tuple[ForecastSetConfig, ...] = Field(min_length=1)
    policies: tuple[Name, ...] = Field(default=COMPARED, min_length=1)
    deterministic_time_limit: PositiveFloat = T_CP
    cp_seed: NonNegativeInt = 0
    wp2b_results: Path | None = None
    sentinel: dict[str, Any] = Field(default_factory=dict)
    variants: dict[Name, dict[str, Any]] = Field(default_factory=dict)
    wp4b_results: Path | None = None
    joined: tuple[Name, ...] = ()
    start_estimate: bool = True
    summary: PolicySummarySettings = PolicySummarySettings()

    @model_validator(mode="after")
    def _check_policies(self) -> Self:
        if len(set(self.policies)) != len(self.policies):
            raise ValueError(f"duplicate policies: {self.policies}")
        for name in self.policies:
            if name not in self.variants:
                make_policy(name)  # raises ValueError for an unknown name
        unused = sorted(set(self.variants) - set(self.policies))
        if unused:
            raise ValueError(f"variants not among the policies: {unused}")
        self.sentinel_variants  # noqa: B018 - validates every variant's parameters
        for name in self.joined:
            make_policy(name)
            if name in self.policies:
                raise ValueError(f"policy {name!r} is both run and joined")
        if self.joined and self.wp4b_results is None:
            raise ValueError("joined policies need wp4b_results")
        if len(self.scenarios.mean_absence) != 1:
            raise ValueError(f"need one mean_absence, got {self.scenarios.mean_absence}")
        for reference in self.summary.reference_policies:
            if reference not in self.analysed_policies:
                raise ValueError(f"reference policy {reference!r} is not among the policies")
        return self

    @property
    def sentinel_variants(self) -> dict[str, SentinelVariant]:
        """Every variant by name, its parameters merged over the shared `sentinel` table."""
        found: dict[str, SentinelVariant] = {}
        for name, table in self.variants.items():
            own = {key: value for key, value in table.items() if key not in VARIANT_KEYS}
            extra = {key: table[key] for key in VARIANT_KEYS if key in table}
            params = SentinelParams.model_validate({**self.sentinel, **own})
            found[name] = SentinelVariant(params=params, **extra)
        return found

    @property
    def analysed_policies(self) -> tuple[str, ...]:
        """The policies of the summaries: the baselines of spec section 7 that are run or
        joined, in registry order, then the run's other policies in config order."""
        present = {*self.policies, *self.joined}
        first = [p for p in (*COMPARED, "stable_resolve") if p in present]
        rest = [p for p in (*self.joined, *self.policies) if p not in first]
        return (*first, *dict.fromkeys(rest))
