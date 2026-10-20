"""Scores of probabilistic makespan forecasts and cluster bootstrap intervals (spec section 5.2).

Binary forecasts p = P(C <= D) with outcomes y = 1[C <= D]: Brier score (Brier 1950), its
reliability-resolution-uncertainty decomposition over equal-width bins (Murphy 1973), expected
calibration error, sharpness and the clipped log score. Makespan distributions given by samples:
CRPS of the empirical CDF (Gneiting & Raftery 2007), its quantiles and the PIT pair, and the
randomised PIT of an integer quantity (Czado, Gneiting & Held 2009). Bin statistics accept leading
resample axes, so the same code gives point estimates and bootstrap replicates.
"""

from collections.abc import Sequence
from typing import NamedTuple

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]
ArrayLike = npt.ArrayLike

BINS = 10  # equal-width bins of [0, 1] for reliability and PIT histograms
LOG_CLIP = 0.005  # log score clips p to [LOG_CLIP, 1 - LOG_CLIP]
# A value on a bin edge, e.g. p = 0.3 = 60/200, belongs to the upper bin despite rounding.
EDGE_TOLERANCE = 1e-9


class SampleScores(NamedTuple):
    """One forecast's samples x_1, ..., x_n scored against the realised makespan C."""

    mean: float
    quantiles: tuple[int, ...]  # inverted empirical CDF at the requested levels
    cdf_below: float  # F(C - 1), the lower end of the PIT pair
    cdf_at: float  # F(C), the upper end
    crps: float


def sample_scores(samples: Sequence[int], outcome: int, levels: Sequence[float]) -> SampleScores:
    """Mean, quantiles q_a (smallest x with F(x) >= a), PIT pair (F(C - 1), F(C)) and CRPS of the
    empirical CDF F of integer `samples` at the realised integer `outcome`."""
    x = np.sort(np.asarray(samples, dtype=np.float64))
    if not x.size:
        raise ValueError("need at least one sample")
    n = x.size
    quantiles = np.quantile(x, list(levels), method="inverted_cdf")
    return SampleScores(
        mean=float(x.mean()),
        quantiles=tuple(int(q) for q in quantiles),
        cdf_below=int(np.searchsorted(x, outcome - 1, side="right")) / n,
        cdf_at=int(np.searchsorted(x, outcome, side="right")) / n,
        crps=_crps_sorted(x, outcome),
    )


def crps_samples(samples: ArrayLike, outcome: float) -> float:
    """CRPS of the empirical CDF of `samples` at `outcome` (Gneiting & Raftery 2007):
    (1/n) sum_i |x_i - y| - (1/(2 n^2)) sum_i sum_k |x_i - x_k|; a point mass gives |x - y|."""
    x = np.sort(np.asarray(samples, dtype=np.float64))
    if not x.size:
        raise ValueError("need at least one sample")
    return _crps_sorted(x, outcome)


def _crps_sorted(x: FloatArray, outcome: float) -> float:
    """The energy form with sum_i sum_k |x_i - x_k| = 2 sum_i (2i - n - 1) x_(i) for sorted x."""
    n = x.size
    spread = float(np.dot(2 * np.arange(1, n + 1) - n - 1, x)) / (n * n)
    return float(np.abs(x - outcome).mean()) - spread


def bin_index(values: ArrayLike, bins: int = BINS) -> IntArray:
    """Bin k of [k/bins, (k+1)/bins) for values in [0, 1]; the last bin includes 1."""
    scaled = np.floor(np.asarray(values, dtype=np.float64) * bins + EDGE_TOLERANCE)
    return np.clip(scaled, 0, bins - 1).astype(np.int64)


class BinSums(NamedTuple):
    """Per-bin count n_k, sum of forecasts and sum of outcomes (last axis = bins)."""

    n: FloatArray
    p_sum: FloatArray
    y_sum: FloatArray


def bin_sums(p: ArrayLike, y: ArrayLike, bins: int = BINS) -> BinSums:
    """Count, forecast sum and outcome sum of each equal-width bin of the forecasts p."""
    p_arr = np.asarray(p, dtype=np.float64)
    y_arr = np.asarray(y, dtype=np.float64)
    k = bin_index(p_arr, bins)
    return BinSums(
        np.bincount(k, minlength=bins).astype(np.float64),
        np.bincount(k, weights=p_arr, minlength=bins),
        np.bincount(k, weights=y_arr, minlength=bins),
    )


class Calibration(NamedTuple):
    """Murphy's reliability, resolution and uncertainty, and the expected calibration error."""

    reliability: FloatArray
    resolution: FloatArray
    uncertainty: FloatArray
    ece: FloatArray


def calibration_terms(sums: BinSums) -> Calibration:
    """REL = sum_k n_k (p_k - y_k)^2 / N, RES = sum_k n_k (y_k - y)^2 / N, UNC = y (1 - y) and
    ECE = sum_k n_k |p_k - y_k| / N from bin sums (Murphy 1973), with p_k and y_k the bin means of
    forecasts and outcomes and y the overall frequency; leading axes are kept (resamples)."""
    n, p_sum, y_sum = sums
    total = n.sum(axis=-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        filled = n > 0
        mean_p = np.where(filled, p_sum / np.where(filled, n, 1), 0.0)
        freq = np.where(filled, y_sum / np.where(filled, n, 1), 0.0)
        base = y_sum.sum(axis=-1) / total
        gap = mean_p - freq
        return Calibration(
            reliability=(n * gap**2).sum(axis=-1) / total,
            resolution=(n * (freq - base[..., None]) ** 2).sum(axis=-1) / total,
            uncertainty=base * (1 - base),
            ece=(n * np.abs(gap)).sum(axis=-1) / total,
        )


class BrierDecomposition(NamedTuple):
    """Brier score and its binned decomposition; `binning_error` is BS - (REL - RES + UNC)."""

    brier: float
    reliability: float
    resolution: float
    uncertainty: float
    ece: float

    @property
    def binning_error(self) -> float:
        return self.brier - (self.reliability - self.resolution + self.uncertainty)


def brier_score(p: ArrayLike, y: ArrayLike) -> float:
    """BS = (1/N) sum (p - y)^2 (Brier 1950)."""
    diff = np.asarray(p, dtype=np.float64) - np.asarray(y, dtype=np.float64)
    return float(np.mean(diff**2))


def brier_decomposition(p: ArrayLike, y: ArrayLike, bins: int = BINS) -> BrierDecomposition:
    """Brier score with REL, RES, UNC and ECE over `bins` equal-width bins (Murphy 1973).

    REL - RES + UNC equals BS when the forecasts are constant within bins; otherwise the gap is
    the within-bin variance minus twice the within-bin covariance of forecasts and outcomes.
    """
    terms = calibration_terms(bin_sums(p, y, bins))
    return BrierDecomposition(
        brier_score(p, y),
        float(terms.reliability),
        float(terms.resolution),
        float(terms.uncertainty),
        float(terms.ece),
    )


def sharpness(p: ArrayLike) -> float:
    """Variance of the forecasts, (1/N) sum (p - mean p)^2."""
    return float(np.var(np.asarray(p, dtype=np.float64)))


def log_score(p: ArrayLike, y: ArrayLike, clip: float = LOG_CLIP) -> float:
    """Mean negative log likelihood -(1/N) sum [y ln p' + (1 - y) ln(1 - p')] with p clipped to
    [clip, 1 - clip] (lower is better)."""
    q = np.clip(np.asarray(p, dtype=np.float64), clip, 1 - clip)
    y_arr = np.asarray(y, dtype=np.float64)
    return float(-np.mean(y_arr * np.log(q) + (1 - y_arr) * np.log1p(-q)))


def randomised_pit(cdf_below: ArrayLike, cdf_at: ArrayLike, rng: np.random.Generator) -> FloatArray:
    """u = F(C - 1) + V (F(C) - F(C - 1)), V ~ U(0, 1): uniform on [0, 1] when the forecast CDF F
    of an integer quantity is calibrated (Czado, Gneiting & Held 2009)."""
    below = np.asarray(cdf_below, dtype=np.float64)
    at = np.asarray(cdf_at, dtype=np.float64)
    result: FloatArray = below + rng.random(below.shape) * (at - below)
    return result


def histogram(values: ArrayLike, bins: int = BINS) -> IntArray:
    """Counts of values in [0, 1] per equal-width bin, the last bin closed."""
    return np.bincount(bin_index(values, bins), minlength=bins).astype(np.int64)


def first_warning(days: Sequence[int], p: Sequence[float], threshold: float) -> int | None:
    """The first checkpoint day (days in checkpoint order) with p < threshold, None if none."""
    for day, prob in zip(days, p, strict=True):
        if prob < threshold:
            return day
    return None


def cluster_resamples(n_clusters: int, n_resamples: int, rng: np.random.Generator) -> FloatArray:
    """Multiplicities w_bc of cluster c in resample b: each resample draws `n_clusters` clusters
    with replacement, so every row of a drawn cluster enters the statistic w_bc times (cluster
    bootstrap; Davison & Hinkley 1997, section 3.8)."""
    if n_clusters < 1 or n_resamples < 1:
        raise ValueError(f"need clusters and resamples, got {n_clusters} and {n_resamples}")
    draws = rng.integers(0, n_clusters, size=(n_resamples, n_clusters))
    flat = (draws + n_clusters * np.arange(n_resamples)[:, None]).ravel()
    counts = np.bincount(flat, minlength=n_resamples * n_clusters)
    return counts.reshape(n_resamples, n_clusters).astype(np.float64)


def resampled_ratio(
    weights: FloatArray, numerator: ArrayLike, denominator: ArrayLike
) -> FloatArray:
    """sum_c w_bc a_c / sum_c w_bc b_c for every resample b (NaN where the denominator is 0), from
    per-cluster sums a_c and b_c, e.g. squared errors and forecast counts for the Brier score."""
    top = weights @ np.asarray(numerator, dtype=np.float64)
    bottom = weights @ np.asarray(denominator, dtype=np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        result: FloatArray = np.where(bottom > 0, top / np.where(bottom > 0, bottom, 1), np.nan)
    return result


def percentile_interval(replicates: ArrayLike, level: float = 0.95) -> tuple[float, float]:
    """Percentile interval of bootstrap replicates, ignoring undefined (NaN) ones."""
    values = np.asarray(replicates, dtype=np.float64)
    values = values[np.isfinite(values)]
    if not values.size:
        return float("nan"), float("nan")
    tail = 50 * (1 - level)
    low, high = np.percentile(values, [tail, 100 - tail])
    return float(low), float(high)
