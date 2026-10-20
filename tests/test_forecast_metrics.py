"""Forecast scores and bootstrap intervals against hand-computed values (spec section 5.2)."""

import math

import numpy as np
import pytest

from sentinel.forecasting import metrics


def test_brier_decomposition_by_hand() -> None:
    # Bins 1 (p = 0.1: outcomes 0, 1) and 9 (p = 0.9: outcomes 1, 1); base rate 0.75.
    p, y = [0.1, 0.1, 0.9, 0.9], [0, 1, 1, 1]
    result = metrics.brier_decomposition(p, y)
    assert result.brier == pytest.approx((0.01 + 0.81 + 0.01 + 0.01) / 4)  # 0.21
    assert result.reliability == pytest.approx((2 * 0.4**2 + 2 * 0.1**2) / 4)  # 0.085
    assert result.resolution == pytest.approx((2 * 0.25**2 + 2 * 0.25**2) / 4)  # 0.0625
    assert result.uncertainty == pytest.approx(0.75 * 0.25)
    assert result.ece == pytest.approx((2 * 0.4 + 2 * 0.1) / 4)
    assert result.binning_error == pytest.approx(0.0, abs=1e-15)
    assert metrics.sharpness(p) == pytest.approx(0.16)


def test_brier_decomposition_sums_to_brier_up_to_binning_error() -> None:
    """BS = REL - RES + UNC + WBV - 2 WBC (within-bin variance and covariance); the extra term
    vanishes for forecasts that are constant within bins."""
    rng = np.random.default_rng(3)
    p = rng.integers(0, 201, size=5000) / 200
    y = (rng.random(5000) < p**1.3).astype(float)
    result = metrics.brier_decomposition(p, y)
    k = metrics.bin_index(p)
    wbv = wbc = 0.0
    for b in range(metrics.BINS):
        inside = k == b
        if inside.any():
            dp = p[inside] - p[inside].mean()
            wbv += float((dp**2).sum())
            wbc += float((dp * (y[inside] - y[inside].mean())).sum())
    assert result.binning_error == pytest.approx((wbv - 2 * wbc) / len(p), abs=1e-12)
    assert abs(result.binning_error) < 0.01
    centred = (k + 0.5) / metrics.BINS
    constant = metrics.brier_decomposition(centred, y)
    assert constant.binning_error == pytest.approx(0.0, abs=1e-12)


def test_bins_put_edges_into_the_upper_bin() -> None:
    assert metrics.bin_index([0, 0.1, 0.3, 0.7, 0.95, 1.0]).tolist() == [0, 1, 3, 7, 9, 9]
    counts = metrics.histogram(np.arange(201) / 200)  # forecasts of 200 rollouts
    assert counts.tolist() == [20] * 9 + [21]


def test_log_score_by_hand_and_clipped() -> None:
    expected = (3 * -math.log(0.9) - math.log(0.1)) / 4
    assert metrics.log_score([0.1, 0.1, 0.9, 0.9], [0, 1, 1, 1]) == pytest.approx(expected)
    clipped = (-math.log(0.005) - math.log(0.995)) / 2
    assert metrics.log_score([0.0, 1.0], [1, 1]) == pytest.approx(clipped)


def test_crps_by_hand_and_of_a_point_mass() -> None:
    # (1/3)(1 + 0 + 1) - (1/18)(2 (1 + 2 + 1)) = 2/9
    assert metrics.crps_samples([1, 2, 3], 2) == pytest.approx(2 / 9)
    for forecast, outcome in [(5, 8), (8, 5), (7, 7)]:
        assert metrics.crps_samples([forecast], outcome) == pytest.approx(abs(forecast - outcome))
        scores = metrics.sample_scores([forecast], outcome, (0.1, 0.5, 0.9))
        assert scores.crps == pytest.approx(abs(forecast - outcome))
        assert scores.quantiles == (forecast,) * 3
    assert metrics.crps_samples([4] * 7, 1) == pytest.approx(3)


def test_crps_is_the_integral_of_the_squared_cdf_difference() -> None:
    """For integer samples and outcome, CRPS = sum over integers z of (F(z) - 1[z >= C])^2."""
    rng = np.random.default_rng(8)
    for _ in range(20):
        samples = rng.integers(40, 60, size=int(rng.integers(1, 60)))
        outcome = int(rng.integers(35, 65))
        grid = np.arange(30, 70)
        cdf = np.searchsorted(np.sort(samples), grid, side="right") / samples.size
        expected = float(((cdf - (grid >= outcome)) ** 2).sum())
        assert metrics.crps_samples(samples, outcome) == pytest.approx(expected, abs=1e-12)


def test_sample_scores_by_hand() -> None:
    scores = metrics.sample_scores([3, 2, 1, 2], 2, (0.25, 0.5, 0.75))
    assert scores.mean == 2.0
    assert scores.quantiles == (1, 2, 2)
    assert (scores.cdf_below, scores.cdf_at) == (0.25, 0.75)
    assert scores.crps == pytest.approx(metrics.crps_samples([1, 2, 2, 3], 2))
    low = metrics.sample_scores([3, 2, 1, 2], 0, (0.5,))
    high = metrics.sample_scores([3, 2, 1, 2], 9, (0.5,))
    assert (low.cdf_below, low.cdf_at, high.cdf_below, high.cdf_at) == (0, 0, 1, 1)
    with pytest.raises(ValueError):
        metrics.sample_scores([], 1, (0.5,))


def poisson_cdf(c: int, mean: float) -> float:
    if c < 0:
        return 0.0
    return math.fsum(math.exp(-mean) * mean**k / math.factorial(k) for k in range(c + 1))


def test_randomised_pit_is_uniform_for_the_true_distribution() -> None:
    """Exact CDF: every bin share is 0.1 within 5 standard errors (n = 20,000). Ensemble of 200
    samples from the true distribution: within 0.03 (n = 2,000); a biased ensemble is not."""
    rng = np.random.default_rng(11)
    outcomes = rng.poisson(4.0, size=20_000)
    below = [poisson_cdf(int(c) - 1, 4.0) for c in outcomes]
    at = [poisson_cdf(int(c), 4.0) for c in outcomes]
    shares = metrics.histogram(metrics.randomised_pit(below, at, rng)) / len(outcomes)
    assert np.abs(shares - 0.1).max() < 5 * math.sqrt(0.1 * 0.9 / len(outcomes))

    def ensemble_shares(forecast_mean: float) -> np.ndarray:
        pairs = []
        for _ in range(2000):
            scores = metrics.sample_scores(
                rng.poisson(forecast_mean, size=200).tolist(), int(rng.poisson(6.0)), (0.5,)
            )
            pairs.append((scores.cdf_below, scores.cdf_at))
        lower, upper = zip(*pairs, strict=True)
        return metrics.histogram(metrics.randomised_pit(lower, upper, rng)) / 2000

    assert np.abs(ensemble_shares(6.0) - 0.1).max() < 0.03
    assert ensemble_shares(10.0)[0] > 0.3  # forecasts too high: PIT piles up near 0


def test_first_warning() -> None:
    days, p = [0, 10, 20], [0.9, 0.7, 0.4]
    assert metrics.first_warning(days, p, 0.8) == 10
    assert metrics.first_warning(days, p, 0.5) == 20
    assert metrics.first_warning(days, p, 0.3) is None
    assert metrics.first_warning([], [], 0.5) is None


def test_cluster_bootstrap_resamples_and_intervals() -> None:
    weights = metrics.cluster_resamples(5, 1000, np.random.default_rng(1))
    assert weights.shape == (1000, 5) and set(weights.sum(axis=1)) == {5.0}
    again = metrics.cluster_resamples(5, 1000, np.random.default_rng(1))
    assert np.array_equal(weights, again)
    assert abs(weights.mean() - 1) < 0.05
    # The same ratio in every cluster gives the same ratio in every resample.
    same = metrics.resampled_ratio(weights, [2.0, 4.0, 6.0, 8.0, 10.0], [1, 2, 3, 4, 5])
    assert np.allclose(same, 2.0)
    assert metrics.percentile_interval(np.arange(1001)) == pytest.approx((25.0, 975.0))
    assert metrics.percentile_interval([np.nan, 1.0, 1.0]) == (1.0, 1.0)
    low, high = metrics.percentile_interval([np.nan])
    assert math.isnan(low) and math.isnan(high)
    empty = metrics.resampled_ratio(np.ones((2, 2)), [1.0, 1.0], [0.0, 0.0])
    assert np.isnan(empty).all()
    with pytest.raises(ValueError):
        metrics.cluster_resamples(0, 10, np.random.default_rng(1))


def test_resampled_calibration_terms_match_replicated_rows() -> None:
    """Bin sums per cluster, weighted by a resample, give the decomposition of the rows of the
    drawn clusters repeated as often as they were drawn."""
    rng = np.random.default_rng(5)
    clusters = [(rng.integers(0, 201, size=12) / 200, rng.random(12) < 0.4) for _ in range(6)]
    per_cluster = [metrics.bin_sums(p, y) for p, y in clusters]
    weights = metrics.cluster_resamples(len(clusters), 4, rng)
    stacked = metrics.BinSums(
        *(weights @ np.array([getattr(s, f) for s in per_cluster]) for f in metrics.BinSums._fields)
    )
    terms = metrics.calibration_terms(stacked)
    for b, row in enumerate(weights):
        p = np.concatenate([np.repeat(c[0], int(w)) for c, w in zip(clusters, row, strict=True)])
        y = np.concatenate([np.repeat(c[1], int(w)) for c, w in zip(clusters, row, strict=True)])
        expected = metrics.brier_decomposition(p, y)
        assert terms.reliability[b] == pytest.approx(expected.reliability)
        assert terms.resolution[b] == pytest.approx(expected.resolution)
        assert terms.uncertainty[b] == pytest.approx(expected.uncertainty)
        assert terms.ece[b] == pytest.approx(expected.ece)
