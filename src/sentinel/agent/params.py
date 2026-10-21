"""Parameters of the Sentinel agent (spec sections 5, 6 and 8)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, PositiveInt, model_validator

from sentinel.simulation.state import HANDOVER_FACTOR

Variant = Literal["full", "no_overtime", "scalarised"]


class SentinelParams(BaseModel):
    """Sentinel's settings; the defaults are those of spec section 8.

    `variant`: `full`, `no_overtime` (no OVERTIME candidate, the fair comparison with the
    baselines of spec section 7) or `scalarised` (the ablation U_a = p_a - lambda_B o_a -
    lambda_Delta Delta_a instead of the lexicographic rule of spec section 6). Racing runs
    `n_stage1` rollouts per candidate, then `n_rollouts` for the survivors; a difference of
    more than `se_factor` paired standard errors drops a candidate, and one of at most that
    many is a tie. `budget_reserve` is beta of B (spec section 1.2), which the observation does
    not carry. CP-SAT runs with one worker, `cp_seed` and `deterministic_time_limit` per stage.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    variant: Variant = "full"
    n_rollouts: PositiveInt = 200  # N
    n_stage1: PositiveInt = 50  # N_1
    se_factor: float = Field(default=2.0, ge=0)
    theta_d: float = Field(default=0.8, ge=0, le=1)  # theta_D
    eps_d: float = Field(default=0.02, ge=0)  # epsilon_D
    eps_b: float = Field(default=0.01, ge=0)  # epsilon_B
    kappa_h: float = Field(default=2.0, ge=0)  # kappa_h
    review_period: PositiveInt = 5  # T_r
    max_single_subst: int = Field(default=3, ge=0)
    overtime_window: PositiveInt | None = None  # H, default 2 T_r
    deterministic_time_limit: PositiveFloat = 0.1  # T_cp
    cp_seed: int = Field(default=0, ge=0)
    lambda_b: float = Field(default=1.0, ge=0)  # lambda_B of the scalarised rule
    lambda_delta: float = Field(default=0.01, ge=0)  # lambda_Delta per day
    budget_reserve: float = Field(default=0.10, ge=0)  # beta
    handover_factor: float = Field(default=HANDOVER_FACTOR, ge=0)  # alpha

    @model_validator(mode="after")
    def _check_stages(self) -> "SentinelParams":
        if self.n_stage1 > self.n_rollouts:
            raise ValueError(f"need n_stage1 <= n_rollouts, got {self.n_stage1}")
        return self

    @property
    def window(self) -> int:
        """H of the OVERTIME candidate: `overtime_window`, else 2 T_r (spec section 6)."""
        return 2 * self.review_period if self.overtime_window is None else self.overtime_window

    @property
    def rule(self) -> Literal["lexicographic", "scalarised"]:
        return "scalarised" if self.variant == "scalarised" else "lexicographic"
