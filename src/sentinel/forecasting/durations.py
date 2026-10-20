"""Exact pmf of the true duration P_j (spec sections 2.1 and 5.1), computed without scipy."""

import math
from bisect import bisect_right
from collections.abc import Callable, Sequence
from functools import cache
from itertools import pairwise

import numpy as np
import numpy.typing as npt

from sentinel.simulation.uncertainty import PertParams, realised_duration

# Composite Simpson intervals per value of P_j when a Beta shape is not an integer.
SIMPSON_INTERVALS = 20_000
# Beta shapes within this distance of an integer use the closed form: the default PERT gives
# alpha = 1 + 4 * 0.2 / 0.8 = 1.9999999999999998 in floating point.
_INTEGER_SHAPE = 1e-9


class IntegerPmf:
    """A pmf on the consecutive integers `first, first + 1, ...`, sampled by inverse CDF."""

    __slots__ = ("_cdf", "first", "probs")

    def __init__(self, first: int, weights: Sequence[float]) -> None:
        """Normalise non-negative `weights` of `first, first + 1, ...` (their sum must be > 0)."""
        total = math.fsum(weights)
        if not weights or not total > 0 or min(weights) < 0:
            raise ValueError(f"need non-negative weights with a positive sum, got {weights}")
        self.first = first
        self.probs = tuple(w / total for w in weights)
        cdf = np.cumsum(self.probs).tolist()
        cdf[-1] = 1.0  # so that every u in [0, 1) falls into the support
        self._cdf: list[float] = cdf

    @property
    def last(self) -> int:
        return self.first + len(self.probs) - 1

    @property
    def mean(self) -> float:
        return math.fsum((self.first + i) * p for i, p in enumerate(self.probs))

    def sample(self, u: float) -> int:
        """Inverse CDF: the smallest value whose cumulative probability exceeds u in [0, 1)."""
        return self.first + min(bisect_right(self._cdf, u), len(self._cdf) - 1)

    def at_least(self, least: int) -> "IntegerPmf | None":
        """The pmf conditioned on values >= `least`; None if that has probability zero."""
        if least <= self.first:
            return self
        weights = self.probs[least - self.first :]
        if not math.fsum(weights) > 0:
            return None
        return IntegerPmf(least, weights)


@cache
def duration_pmf(nominal: int, params: PertParams) -> IntegerPmf:
    """Exact pmf of P_j = max(1, round(p_j X)), X ~ PERT (spec section 2.1); P_j = 0 if p_j = 0.

    Value k collects p_j X in (k - 1/2, k + 1/2) (ties have probability zero), and k = 1 also
    p_j X < 1/2. The Beta CDF (Malcolm et al. 1959 PERT, X = a + (b - a) Beta(alpha, beta)) is the
    closed-form regularised incomplete beta for integer shapes, else composite Simpson on
    `SIMPSON_INTERVALS` intervals per value. Results are cached per (p_j, params).
    """
    if nominal < 0:
        raise ValueError(f"nominal duration must be non-negative, got {nominal}")
    if nominal == 0:
        return IntegerPmf(0, (1.0,))
    a, m, b, lam = params.a, params.m, params.b, params.lam
    if a == b:
        return IntegerPmf(realised_duration(nominal, a), (1.0,))
    alpha = 1 + lam * (m - a) / (b - a)
    beta = 1 + lam * (b - m) / (b - a)
    # Values whose rounding interval meets p_j X in (p_j a, p_j b), clamped at 1.
    first = max(1, math.floor(nominal * a - 0.5) + 1)
    last = max(1, math.ceil(nominal * b + 0.5) - 1)
    edges = [0.0] + [((k + 0.5) / nominal - a) / (b - a) for k in range(first, last)] + [1.0]
    edges = [min(1.0, max(0.0, x)) for x in edges]
    mass = _bin_masses(edges, alpha, beta)
    # Drop values without mass at both ends (an interval that only touches the support).
    lo, hi = 0, len(mass)
    while mass[lo] <= 0:
        lo += 1
    while mass[hi - 1] <= 0:
        hi -= 1
    return IntegerPmf(first + lo, mass[lo:hi])


def _bin_masses(edges: Sequence[float], alpha: float, beta: float) -> list[float]:
    """Beta(alpha, beta) mass of each interval [edges[i], edges[i + 1]], up to a common factor."""
    if abs(alpha - round(alpha)) < _INTEGER_SHAPE and abs(beta - round(beta)) < _INTEGER_SHAPE:
        cdf, sf = _integer_beta(round(alpha), round(beta))
        # The CDF is accurate in the lower tail, the survival function in the upper one.
        return [
            max(0.0, cdf(hi) - cdf(lo) if hi <= 0.5 else sf(lo) - sf(hi))
            for lo, hi in pairwise(edges)
        ]

    def density(x: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        result: npt.NDArray[np.float64] = x ** (alpha - 1) * (1 - x) ** (beta - 1)
        return result

    return [_simpson(density, lo, hi) for lo, hi in pairwise(edges)]


def _integer_beta(
    alpha: int, beta: int
) -> tuple[Callable[[float], float], Callable[[float], float]]:
    """CDF I_x(alpha, beta) = sum_{k=alpha}^{n} C(n, k) x^k (1 - x)^(n - k), n = alpha + beta - 1,
    and its complement 1 - I_x (the terms k < alpha)."""
    n = alpha + beta - 1
    coefficients = [math.comb(n, k) for k in range(n + 1)]

    def terms(x: float, ks: range) -> float:
        return math.fsum(coefficients[k] * x**k * (1 - x) ** (n - k) for k in ks)

    return (lambda x: terms(x, range(alpha, n + 1))), (lambda x: terms(x, range(alpha)))


def _simpson(
    f: Callable[[npt.NDArray[np.float64]], npt.NDArray[np.float64]], lo: float, hi: float
) -> float:
    """Composite Simpson rule for the integral of f over [lo, hi] (SIMPSON_INTERVALS intervals)."""
    if hi <= lo:
        return 0.0
    n = SIMPSON_INTERVALS
    y = f(np.linspace(lo, hi, n + 1))
    return float((hi - lo) / (3 * n) * (y[0] + y[-1] + 4 * y[1:-1:2].sum() + 2 * y[2:-1:2].sum()))
