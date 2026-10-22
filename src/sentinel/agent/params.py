"""Parameters of the Sentinel agent (spec sections 4, 5, 6 and 8)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, PositiveInt, model_validator

from sentinel.policies.base import Decision
from sentinel.simulation.state import HANDOVER_FACTOR

Variant = Literal["full", "no_overtime", "scalarised"]
# Components of the lexicographic rule in their order (spec section 6); "scope" only matters
# with DESCOPE candidates.
Component = Literal["on_time", "tardiness", "scope", "budget", "stability", "level"]
COMPONENTS: tuple[Component, ...] = (
    "on_time",
    "tardiness",
    "scope",
    "budget",
    "stability",
    "level",
)


class SentinelParams(BaseModel):
    """Sentinel's settings; the defaults are those of spec section 8.

    `variant`: `full`, `no_overtime` (no OVERTIME candidate, the fair comparison with the
    baselines of spec section 7) or `scalarised` (the ablation U_a = p_a - lambda_B o_a -
    lambda_Delta Delta_a instead of the lexicographic rule of spec section 6). Racing runs
    `n_stage1` rollouts per candidate, then `n_rollouts` for the survivors. Two candidates tie in
    a stochastic component when their paired difference is within `se_factor` paired standard
    errors or below its materiality threshold (`eps_d`, `eps_t`, `eps_b`); in Delta when it is
    below `eps_delta`. The permission gate (spec section 4) runs an action automatically iff
    its level is below `autonomy` (Lambda) and it has no DESCOPE; otherwise it defers if the
    urgency exceeds `tau_def` days, else escalates to a simulated human who approves after
    `approval_delay` (delta_h) days. `descope` enables the DESCOPE candidates (at most
    `max_descope`). CP-SAT runs with one worker, `cp_seed` and `deterministic_time_limit` per
    stage. The budget B and the costs come from the observation.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    variant: Variant = "full"
    n_rollouts: PositiveInt = 200  # N
    n_stage1: PositiveInt = 50  # N_1
    se_factor: float = Field(default=2.0, ge=0)
    theta_d: float = Field(default=0.8, ge=0, le=1)  # theta_D
    eps_d: float = Field(default=0.02, ge=0)  # epsilon_D
    eps_b: float = Field(default=0.01, ge=0)  # epsilon_B
    eps_t: float = Field(default=0.5, ge=0)  # epsilon_T, days
    eps_delta: float = Field(default=0.5, ge=0)  # epsilon_Delta, days
    kappa_h: float = Field(default=2.0, ge=0)  # kappa_h
    review_period: PositiveInt = 5  # T_r
    max_single_subst: int = Field(default=3, ge=0)
    overtime_window: PositiveInt | None = None  # H, default 2 T_r
    deterministic_time_limit: PositiveFloat = 0.1  # T_cp
    cp_seed: int = Field(default=0, ge=0)
    lambda_b: float = Field(default=1.0, ge=0)  # lambda_B of the scalarised rule
    lambda_delta: float = Field(default=0.01, ge=0)  # lambda_Delta per day
    handover_factor: float = Field(default=HANDOVER_FACTOR, ge=0)  # alpha
    autonomy: int = Field(default=2, ge=0, le=3)  # Lambda
    tau_def: float = 3.0  # tau_def, days
    approval_delay: PositiveInt = 1  # delta_h, days
    descope: bool = False
    max_descope: int = Field(default=2, ge=0)

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

    def ties(self, component: Component, difference: float, se: float = 0.0) -> bool:
        """Whether a candidate worse than another by `difference` in `component` ties with it
        (spec section 6): in min(p, theta_D), T and o when the paired difference is within
        `se_factor` paired standard errors `se` or below the materiality threshold (eps_D,
        eps_T, eps_B); in Delta when below eps_Delta; in the scope loss and the level only when
        equal. A negative difference (the candidate is better) is always a tie."""
        match component:
            case "on_time":
                threshold = self.eps_d
            case "tardiness":
                threshold = self.eps_t
            case "budget":
                threshold = self.eps_b
            case "stability":
                return difference < self.eps_delta
            case "scope" | "level":
                return difference <= 0
        return difference <= self.se_factor * se or difference < threshold

    def needs_approval(self, decision: Decision) -> bool:
        """Whether the permission gate stops `decision` (spec section 4): an action other than
        NOOP with level l(a) >= Lambda or with a DESCOPE."""
        if all(op.kind == "noop" for op in decision.operations):
            return False
        return decision.level >= self.autonomy or decision.descopes

    def delay(self, decision: Decision) -> int:
        """Days after which rollouts apply `decision`: delta_h if it needs approval, else 0
        (spec section 6, the agent imagines the approval delay)."""
        return self.approval_delay if self.needs_approval(decision) else 0
