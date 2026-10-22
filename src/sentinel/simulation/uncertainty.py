"""Stochastic durations (spec section 2.1) and the derived deadline and budget (section 1.2)."""

import math
from collections.abc import Sequence
from typing import Self

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict, Field, model_validator

from sentinel.model.instance import ProjectInstance


class PertParams(BaseModel):
    """Beta-PERT multiplier X ~ PERT(a, m, b) with shape lam (spec section 2.1; Malcolm 1959)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    a: float = Field(default=0.8, gt=0, allow_inf_nan=False)
    m: float = Field(default=1.0, gt=0, allow_inf_nan=False)
    b: float = Field(default=1.6, gt=0, allow_inf_nan=False)
    lam: float = Field(default=4.0, gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _check_order(self) -> Self:
        if not self.a <= self.m <= self.b:
            raise ValueError(f"PERT needs a <= m <= b, got ({self.a}, {self.m}, {self.b})")
        return self

    @property
    def mean(self) -> float:
        """E[X] = (a + lam m + b) / (lam + 2), i.e. (a + 4m + b) / 6 for lam = 4 (Malcolm 1959)."""
        return (self.a + self.lam * self.m + self.b) / (self.lam + 2)


DEFAULT_PERT = PertParams()


def pert_multipliers(
    n: int, rng: np.random.Generator, params: PertParams
) -> npt.NDArray[np.float64]:
    """n multipliers X = a + (b - a) Beta(alpha, beta) (Beta-PERT; Malcolm et al. 1959).

    alpha = 1 + lam (m - a) / (b - a) and beta = 1 + lam (b - m) / (b - a). If a == b the
    constant a is returned without drawing from `rng`.
    """
    if n < 0:
        raise ValueError(f"n must be non-negative, got {n}")
    a, m, b, lam = params.a, params.m, params.b, params.lam
    if a == b:
        return np.full(n, a, dtype=np.float64)
    alpha = 1 + lam * (m - a) / (b - a)
    beta = 1 + lam * (b - m) / (b - a)
    return a + (b - a) * rng.beta(alpha, beta, size=n)


def realised_duration(nominal: int, multiplier: float) -> int:
    """P = 0 if p = 0, else max(1, round(p X)) (spec section 2.1); ties round half to even."""
    if nominal == 0:
        return 0
    return max(1, round(nominal * multiplier))


def realise_durations(
    instance: ProjectInstance, rng: np.random.Generator, params: PertParams
) -> tuple[int, ...]:
    """True durations P_j of every activity (spec section 2.1), one multiplier per activity id.

    Dummies and milestones also get a multiplier, so the draws do not depend on the durations.
    """
    multipliers = pert_multipliers(instance.n_activities, rng, params).tolist()
    return tuple(
        realised_duration(act.duration, x)
        for act, x in zip(instance.activities, multipliers, strict=True)
    )


def expected_durations(instance: ProjectInstance, params: PertParams) -> tuple[float, ...]:
    """p-bar_j = p_j E[X] for every activity (spec section 1.2; rounding of 2.1 ignored)."""
    mean = params.mean
    return tuple(act.duration * mean for act in instance.activities)


def role_costs(instance: ProjectInstance, costs: Sequence[float] | None) -> tuple[float, ...]:
    """Daily cost c_k of a worker of each role; None means 1.0 for every role (spec section 8)."""
    if costs is None:
        return (1.0,) * len(instance.roles)
    values = tuple(float(c) for c in costs)
    if len(values) != len(instance.roles):
        raise ValueError(f"got {len(values)} role costs for {len(instance.roles)} roles")
    if any(not math.isfinite(c) or c < 0 for c in values):
        raise ValueError(f"role costs must be finite and non-negative, got {values}")
    return values


def derive_deadline(c_star: int, delta_d: float) -> int:
    """D = ceil((1 + delta_D) C*) (spec section 1.2)."""
    if c_star < 0 or not delta_d >= 0:
        raise ValueError(f"need C* >= 0 and delta_D >= 0, got {c_star} and {delta_d}")
    # 1.1 * 10 == 11.000000000000002 in binary floating point; the tolerance keeps
    # mathematically integral products from being rounded up.
    return math.ceil((1 + delta_d) * c_star - 1e-9)


def derive_budget(
    instance: ProjectInstance,
    beta: float = 0.10,
    costs: Sequence[float] | None = None,
    params: PertParams = DEFAULT_PERT,
) -> float:
    """B = (1 + beta) sum_j sum_k c_k r_jk p-bar_j (spec section 1.2)."""
    if not beta >= 0:
        raise ValueError(f"budget reserve beta must be non-negative, got {beta}")
    per_role = role_costs(instance, costs)
    expected = expected_durations(instance, params)
    work_cost = sum(
        p_bar * sum(c * r for c, r in zip(per_role, act.demands, strict=True))
        for act, p_bar in zip(instance.activities, expected, strict=True)
    )
    return (1 + beta) * work_cost


def optional_activities(instance: ProjectInstance, share: float, seed: int) -> tuple[int, ...]:
    """The optional activities O of spec section 4, drawn with `seed` (derive_seed(base,
    "optional", instance) in the studies): `share` = phi of the real activities, taken
    uniformly among the real activities whose only successor is the sink (at most all of them).
    """
    # SPEC-Q: "a share phi of the real activities whose only successor is the sink" read as
    # round(phi n_real) of them; every J30/J60 instance has exactly 3 such activities, so the
    # share of those 3 would give round(0.1 * 3) = 0 optional activities.
    if not 0 <= share <= 1:
        raise ValueError(f"share phi must lie in [0, 1], got {share}")
    sink = instance.sink_id
    eligible = [
        act.id
        for act in instance.activities
        if act.id not in (0, sink) and tuple(act.successors) == (sink,)
    ]
    count = min(len(eligible), round(share * instance.n_real))
    if count == 0:
        return ()
    rng = np.random.default_rng(seed)
    chosen = rng.choice(len(eligible), size=count, replace=False).tolist()
    return tuple(sorted(eligible[i] for i in chosen))
