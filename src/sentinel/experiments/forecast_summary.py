"""Summaries of a forecast study run, generated from its forecasts file only (spec section 5.2).

Writes `summary.md` (every statistic by set x checkpoint f x lambda_A and pooled over lambda_A),
for the first delta_D the LaTeX tables `<table>.tex` (calibration per set x f x forecaster) and
`<warning_table>.tex` (early warning), appendix tables `<table>_delta<d>.tex` and
`<warning_table>_delta<d>.tex` for the other slacks, and the figures `<prefix>_reliability`,
`<prefix>_brier` and `<prefix>_pit` as PDF and PNG. Intervals are 95 % percentile intervals of a
cluster bootstrap over the instances of a set. Regenerate the summaries of a run with

    uv run sentinel summarise-forecasts results/wp3/<run_id>
"""

import csv
import gzip
import json
import math
from array import array
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TextIO

import numpy as np
import numpy.typing as npt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter

from sentinel.data.psplib_loader import natural_key
from sentinel.experiments.forecast_config import ForecasterSpec, ForecastStudyConfig
from sentinel.experiments.runs import derive_seed
from sentinel.forecasting import metrics
from sentinel.forecasting.metrics import BinSums, FloatArray, IntArray

FORECASTS_FILE = "forecasts.csv.gz"
SUMMARY_FILE = "summary.md"
QUANTILE_LEVELS = (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)
QUANTILE_COLUMNS = tuple(f"q{round(100 * q):02d}" for q in QUANTILE_LEVELS)
REFERENCE_LABELS = {"opt": "optimum", "hrs": "best known", "lb": "lower bound"}
_CATEGORIES = ("set", "instance", "scenario", "forecaster")
_FLAGS = ("skipped", "truncated")

# Categorical slots of the dataviz reference palette (light) in their fixed order: forecaster i
# of the config keeps slot i in every figure; markers repeat the identity for print and CVD.
_COLORS = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
_MARKERS = ("o", "s", "^", "D", "v", "P", "X", "*")
_INK, _INK_2, _MUTED, _GRID, _AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"

BoolArray = npt.NDArray[np.bool_]
Level = float | None  # a checkpoint share or lambda_A; None pools over all of them


@dataclass(frozen=True)
class ForecastTable:
    """forecasts.csv.gz as column arrays, NaN where a skipped checkpoint has no forecast.

    Categorical columns are codes into `names` in order of first appearance.
    """

    numbers: dict[str, FloatArray]
    flags: dict[str, BoolArray]
    codes: dict[str, IntArray]
    names: dict[str, tuple[str, ...]]

    @property
    def n_rows(self) -> int:
        return len(self.flags["skipped"])


def read_forecasts(path: Path) -> ForecastTable:
    """Parse forecasts.csv.gz in one pass into typed columns (no per-row objects are kept)."""
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        position = {name: i for i, name in enumerate(header)}
        categories = [(name, position[name]) for name in _CATEGORIES]
        flag_columns = [(name, position[name]) for name in _FLAGS]
        number_columns = [
            (name, i) for i, name in enumerate(header) if name not in _CATEGORIES + _FLAGS
        ]
        lookup: dict[str, dict[str, int]] = {name: {} for name in _CATEGORIES}
        codes = {name: array("q") for name in _CATEGORIES}
        flags = {name: array("b") for name in _FLAGS}
        numbers = {name: array("d") for name, _ in number_columns}
        nan = math.nan
        for record in reader:
            for name, i in categories:
                known = lookup[name]
                codes[name].append(known.setdefault(record[i], len(known)))
            for name, i in flag_columns:
                flags[name].append(record[i] == "True")
            for name, i in number_columns:
                value = record[i]
                numbers[name].append(float(value) if value else nan)
    return ForecastTable(
        numbers={name: np.frombuffer(values, dtype=np.float64) for name, values in numbers.items()},
        flags={name: np.frombuffer(values, dtype=np.int8) > 0 for name, values in flags.items()},
        codes={name: np.frombuffer(values, dtype=np.int64) for name, values in codes.items()},
        names={name: tuple(known) for name, known in lookup.items()},
    )


@dataclass(frozen=True)
class SeedCheck:
    """Comparison of the worlds' makespans and seeds with the WP2b results of the same
    (set, instance, scenario, replication); `available` is False if no file was found."""

    path: str | None
    available: bool
    checked: int = 0
    makespan_mismatches: int = 0
    seed_mismatches: int = 0
    missing: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "available": self.available,
            "worlds_checked": self.checked,
            "makespan_mismatches": self.makespan_mismatches,
            "seed_mismatches": self.seed_mismatches,
            "missing": self.missing,
        }

    def line(self) -> str:
        if not self.available:
            return f"- WP2b seed check: not run (results file `{self.path}` not found)."
        return (
            f"- WP2b seed check against `{self.path}`: {self.checked} worlds compared, "
            f"**{self.makespan_mismatches} makespan mismatches** (expected 0), "
            f"{self.seed_mismatches} seed mismatches, {self.missing} without a WP2b row."
        )


def wp2b_check(table: ForecastTable, path: Path | None) -> SeedCheck:
    """Compare every world (one per set, instance, scenario, replication) with WP2b."""
    if path is None or not path.is_file():
        return SeedCheck(None if path is None else str(path), available=False)
    names, codes, numbers = table.names, table.codes, table.numbers
    worlds: dict[tuple[str, str, str, int], tuple[int, int]] = {}
    for row in range(table.n_rows):
        key = (
            names["set"][codes["set"][row]],
            names["instance"][codes["instance"][row]],
            names["scenario"][codes["scenario"][row]],
            int(numbers["replication"][row]),
        )
        worlds[key] = (int(numbers["makespan"][row]), int(numbers["seed"][row]))
    found: dict[tuple[str, str, str, int], tuple[int, int]] = {}
    with _open_text(path) as handle:
        for record in csv.DictReader(handle):
            key = (
                record["set"],
                record["instance"],
                record["scenario"],
                int(record["replication"]),
            )
            if key in worlds:
                found[key] = (int(record["makespan"]), int(record["seed"]))
    compared = [(worlds[key], found[key]) for key in worlds if key in found]
    return SeedCheck(
        str(path),
        available=True,
        checked=len(compared),
        makespan_mismatches=sum(ours[0] != theirs[0] for ours, theirs in compared),
        seed_mismatches=sum(ours[1] != theirs[1] for ours, theirs in compared),
        missing=len(worlds) - len(compared),
    )


@contextmanager
def _open_text(path: Path) -> Iterator[TextIO]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
            yield handle
    else:
        with path.open(newline="", encoding="utf-8") as handle:
            yield handle


@dataclass(frozen=True)
class Estimate:
    """A statistic with its 95 % cluster bootstrap interval (NaN where undefined)."""

    value: float
    low: float
    high: float


@dataclass(frozen=True)
class BinaryCell:
    """Scores of the forecasts p = P(C <= D) of one cell for one delta_D (spec section 5.2)."""

    n: int
    on_time: float
    brier: Estimate
    reliability: Estimate
    resolution: Estimate
    uncertainty: float
    binning_error: float
    ece: Estimate
    sharpness: float
    log_score: Estimate
    bins: BinSums


@dataclass(frozen=True)
class DistributionCell:
    """Scores of the makespan distributions of one cell; CRPS, MAE and width relative to C*."""

    n: int
    crps: Estimate
    mae: Estimate
    coverage: Estimate
    width: float
    pit: IntArray


@dataclass(frozen=True)
class DifferenceCell:
    """Paired differences a - b of two forecasters on the same checkpoints."""

    brier: Estimate
    crps: Estimate


@dataclass(frozen=True)
class WarningCell:
    """Early warning at one threshold: late runs warned, their lead time, false alarms."""

    late: int
    warned: Estimate
    lead: Estimate
    on_time: int
    false_alarms: Estimate


class Analysis:
    """Per-row scores, instance clusters and bootstrap resamples of one run (spec section 5.2).

    Rows of skipped checkpoints are excluded from every statistic. Instance clusters are local to
    a set; each set has its own resample matrix, seeded from (bootstrap_seed, set), shared by all
    statistics so that paired differences use the same resamples.
    """

    def __init__(self, table: ForecastTable, config: ForecastStudyConfig) -> None:
        settings = config.summary
        self.config = config
        self.bins = settings.bins
        self.sets = [s.name for s in config.sets]
        self.forecasters = [f.name for f in config.forecasters]
        codes, names, num, flags = table.codes, table.names, table.numbers, table.flags
        self.set_row = _recode(codes["set"], names["set"], self.sets)
        self.forecaster_row = _recode(codes["forecaster"], names["forecaster"], self.forecasters)
        self.valid = ~flags["skipped"]
        self.share = num["f"]
        self.lambda_a = num["lambda_a"]
        self.day = num["checkpoint_day"]
        makespan, c_star = num["makespan"], num["c_star"]
        on_time = [
            ~flags["truncated"] & (makespan <= num[f"deadline_{d:g}"]) for d in config.deltas
        ]
        self.deadline = [num[f"deadline_{d:g}"] for d in config.deltas]
        self.p = [num[f"p_on_time_{d:g}"] for d in config.deltas]
        self.y = [o.astype(np.float64) for o in on_time]
        self.crps = num["crps"] / c_star
        self.abs_error = np.abs(num["q50"] - makespan) / c_star
        self.covered = ((num["q10"] <= makespan) & (makespan <= num["q90"])).astype(np.float64)
        self.width = (num["q90"] - num["q10"]) / c_star
        pit_rng = np.random.default_rng(settings.pit_seed)
        self.pit = metrics.randomised_pit(num["pit_lower"], num["pit_upper"], pit_rng)
        self.wall_s = num["wall_s"]
        self.cluster = np.full(table.n_rows, -1, dtype=np.int64)
        self.weights: list[FloatArray] = []
        instance_names = names["instance"]
        for s, set_name in enumerate(self.sets):
            in_set = self.set_row == s
            present = np.unique(codes["instance"][in_set]).tolist()
            order = sorted(present, key=lambda c: natural_key(instance_names[c]))
            local = np.full(len(instance_names), -1, dtype=np.int64)
            local[order] = np.arange(len(order))
            self.cluster[in_set] = local[codes["instance"][in_set]]
            rng = np.random.default_rng(derive_seed(settings.bootstrap_seed, "bootstrap", set_name))
            resamples = settings.bootstrap_resamples
            self.weights.append(
                metrics.cluster_resamples(len(order), resamples, rng)
                if order
                else np.zeros((resamples, 0))
            )
        # Runs (a world seen by one forecaster) for early warning.
        sizes = [len(names[c]) for c in ("instance", "scenario")]
        n_rep = int(np.nanmax(num["replication"])) + 1 if table.n_rows else 1
        key = self.set_row.astype(np.int64)
        for part, size in (
            (codes["instance"], sizes[0]),
            (codes["scenario"], sizes[1]),
            (num["replication"].astype(np.int64), n_rep),
            (self.forecaster_row.astype(np.int64), len(self.forecasters)),
        ):
            key = key * size + part
        _, first, self.run_of_row = np.unique(key, return_index=True, return_inverse=True)
        self.run_of_row = self.run_of_row.reshape(-1)
        self.n_runs = len(first)
        self.run_set = self.set_row[first]
        self.run_forecaster = self.forecaster_row[first]
        self.run_cluster = self.cluster[first]
        self.run_lambda = self.lambda_a[first]
        self.run_late = [~o[first] for o in on_time]
        self.run_deadline = [d[first] for d in self.deadline]

    def rows(self, s: int, k: int, share: Level = None, lam: Level = None) -> BoolArray:
        """Forecasts of forecaster k in set s at checkpoint `share` and lambda_A `lam`."""
        mask: BoolArray = self.valid & (self.set_row == s) & (self.forecaster_row == k)
        if share is not None:
            mask &= self.share == share
        if lam is not None:
            mask &= self.lambda_a == lam
        return mask

    def _ratio(self, s: int, mask: BoolArray, values: FloatArray) -> Estimate:
        """Mean of `values` over the rows of `mask` with its cluster bootstrap interval."""
        size = self.weights[s].shape[1]
        cluster = self.cluster[mask]
        total = np.bincount(cluster, weights=values[mask], minlength=size)
        count = np.bincount(cluster, minlength=size).astype(np.float64)
        return _estimate(self.weights[s], total, count)

    def binary(self, i: int, s: int, k: int, share: Level, lam: Level) -> BinaryCell | None:
        """Brier score, decomposition, ECE, sharpness and log score of p for delta_D i."""
        mask = self.rows(s, k, share, lam)
        if not mask.any():
            return None
        p, y, cluster = self.p[i][mask], self.y[i][mask], self.cluster[mask]
        weights, bins = self.weights[s], self.bins
        size = weights.shape[1]
        flat = cluster * bins + metrics.bin_index(p, bins)
        per_cluster = [
            np.bincount(flat, weights=w, minlength=size * bins).reshape(size, bins)
            for w in (np.ones_like(p), p, y)
        ]
        point = BinSums(*(a.sum(axis=0) for a in per_cluster))
        terms = metrics.calibration_terms(point)
        resampled = metrics.calibration_terms(BinSums(*(weights @ a for a in per_cluster)))
        brier = self._ratio(s, mask, (self.p[i] - self.y[i]) ** 2)
        clip = self.config.summary.log_clip
        losses = np.zeros_like(self.p[i])
        losses[mask] = metrics.log_losses(p, y, clip)
        reliability, resolution = float(terms.reliability), float(terms.resolution)
        uncertainty = float(terms.uncertainty)
        return BinaryCell(
            n=int(mask.sum()),
            on_time=float(y.mean()),
            brier=brier,
            reliability=Estimate(reliability, *metrics.percentile_interval(resampled.reliability)),
            resolution=Estimate(resolution, *metrics.percentile_interval(resampled.resolution)),
            uncertainty=uncertainty,
            binning_error=brier.value - (reliability - resolution + uncertainty),
            ece=Estimate(float(terms.ece), *metrics.percentile_interval(resampled.ece)),
            sharpness=metrics.sharpness(p),
            log_score=self._ratio(s, mask, losses),
            bins=point,
        )

    def distribution(self, s: int, k: int, share: Level, lam: Level) -> DistributionCell | None:
        """CRPS / C*, MAE / C*, 80 % coverage, width / C* and the randomised PIT histogram."""
        mask = self.rows(s, k, share, lam)
        if not mask.any():
            return None
        return DistributionCell(
            n=int(mask.sum()),
            crps=self._ratio(s, mask, self.crps),
            mae=self._ratio(s, mask, self.abs_error),
            coverage=self._ratio(s, mask, self.covered),
            width=float(self.width[mask].mean()),
            pit=metrics.histogram(self.pit[mask], self.bins),
        )

    def difference(
        self, i: int, s: int, pair: tuple[str, str], share: Level, lam: Level
    ) -> DifferenceCell | None:
        """Brier (delta_D i) and CRPS / C* of forecaster a minus forecaster b, paired by row."""
        a, b = (self.forecasters.index(name) for name in pair)
        mask_a, mask_b = self.rows(s, a, share, lam), self.rows(s, b, share, lam)
        if not mask_a.any():
            return None
        size = self.weights[s].shape[1]
        count = np.bincount(self.cluster[mask_a], minlength=size).astype(np.float64)
        if not np.array_equal(count, np.bincount(self.cluster[mask_b], minlength=size)):
            raise ValueError(f"forecasters {pair} were not scored on the same checkpoints")
        squared = (self.p[i] - self.y[i]) ** 2

        def gap(values: FloatArray) -> FloatArray:
            top_a = np.bincount(self.cluster[mask_a], weights=values[mask_a], minlength=size)
            top_b = np.bincount(self.cluster[mask_b], weights=values[mask_b], minlength=size)
            result: FloatArray = top_a - top_b
            return result

        return DifferenceCell(
            brier=_estimate(self.weights[s], gap(squared), count),
            crps=_estimate(self.weights[s], gap(self.crps), count),
        )

    def warning(self, i: int, s: int, k: int, theta: float, lam: Level) -> WarningCell | None:
        """Early warning (spec section 5.2): a run is warned at its first checkpoint with
        p < theta; lead time D - t_w over warned late runs; false alarms among on-time runs."""
        warn = self.valid & (self.p[i] < theta)
        warned = np.bincount(self.run_of_row[warn], minlength=self.n_runs) > 0
        first_day = np.full(self.n_runs, np.inf)
        np.minimum.at(first_day, self.run_of_row[warn], self.day[warn])
        runs = (self.run_set == s) & (self.run_forecaster == k)
        if lam is not None:
            runs &= self.run_lambda == lam
        if not runs.any():
            return None
        late, size = self.run_late[i], self.weights[s].shape[1]
        lead = np.where(warned, self.run_deadline[i] - first_day, 0.0)

        def per_cluster(mask: BoolArray, values: FloatArray | None = None) -> FloatArray:
            result: FloatArray = np.bincount(
                self.run_cluster[mask],
                weights=None if values is None else values[mask],
                minlength=size,
            ).astype(np.float64)
            return result

        late_runs, on_runs = runs & late, runs & ~late
        warned_late = late_runs & warned
        return WarningCell(
            late=int(late_runs.sum()),
            warned=_estimate(self.weights[s], per_cluster(warned_late), per_cluster(late_runs)),
            lead=_estimate(
                self.weights[s], per_cluster(warned_late, lead), per_cluster(warned_late)
            ),
            on_time=int(on_runs.sum()),
            false_alarms=_estimate(
                self.weights[s], per_cluster(on_runs & warned), per_cluster(on_runs)
            ),
        )


def _recode(codes: IntArray, names: Sequence[str], order: Sequence[str]) -> IntArray:
    """Codes in order of appearance mapped onto positions in `order` (the config's order)."""
    unknown = set(names) - set(order)
    if unknown:
        raise ValueError(f"forecasts file has values missing from the config: {sorted(unknown)}")
    mapping = np.array([order.index(name) for name in names], dtype=np.int64)
    result: IntArray = mapping[codes] if len(codes) else np.zeros(0, dtype=np.int64)
    return result


def _estimate(weights: FloatArray, numerator: FloatArray, denominator: FloatArray) -> Estimate:
    """Ratio of the summed per-cluster numerators and denominators with its bootstrap interval."""
    total = float(denominator.sum())
    value = float(numerator.sum()) / total if total > 0 else math.nan
    replicates = metrics.resampled_ratio(weights, numerator, denominator)
    return Estimate(value, *metrics.percentile_interval(replicates))


@dataclass
class Cells:
    """All cells of a run: keys use the indices of delta_D, set, forecaster or difference pair,
    the checkpoint share and lambda_A (None: pooled)."""

    binary: dict[tuple[int, int, int, Level, Level], BinaryCell]
    distribution: dict[tuple[int, int, Level, Level], DistributionCell]
    differences: dict[tuple[int, int, int, Level, Level], DifferenceCell]
    warnings: dict[tuple[int, int, int, float, Level], WarningCell]


def compute_cells(analysis: Analysis, config: ForecastStudyConfig) -> Cells:
    """Every cell by set x checkpoint x lambda_A, each also pooled over checkpoints and lambda_A."""
    shares: list[Level] = [*config.checkpoints, None]
    lambdas: list[Level] = [*sorted({s.lambda_a for s in config.scenarios.expand()}), None]
    cells = Cells({}, {}, {}, {})
    for s in range(len(analysis.sets)):
        for share in shares:
            for lam in lambdas:
                for k in range(len(analysis.forecasters)):
                    dist = analysis.distribution(s, k, share, lam)
                    if dist is not None:
                        cells.distribution[(s, k, share, lam)] = dist
                    for i in range(len(config.deltas)):
                        binary = analysis.binary(i, s, k, share, lam)
                        if binary is not None:
                            cells.binary[(i, s, k, share, lam)] = binary
                for i in range(len(config.deltas)):
                    for d, pair in enumerate(config.summary.differences):
                        diff = analysis.difference(i, s, pair, share, lam)
                        if diff is not None:
                            cells.differences[(i, s, d, share, lam)] = diff
        for lam in lambdas:
            for k in range(len(analysis.forecasters)):
                for i in range(len(config.deltas)):
                    for theta in config.summary.thresholds:
                        warning = analysis.warning(i, s, k, theta, lam)
                        if warning is not None:
                            cells.warnings[(i, s, k, theta, lam)] = warning
    return cells


# --- Markdown -----------------------------------------------------------------------------------


def _num(value: float, digits: int = 3) -> str:
    return f"{value:.{digits}f}" if math.isfinite(value) else "--"


def _est(estimate: Estimate, digits: int = 3, scale: float = 1.0) -> str:
    low, high = estimate.low * scale, estimate.high * scale
    return f"{_num(estimate.value * scale, digits)} [{_num(low, digits)}, {_num(high, digits)}]"


def _level(value: Level) -> str:
    return "all" if value is None else f"{value:g}"


def summary_markdown(
    run_id: str,
    config: ForecastStudyConfig,
    analysis: Analysis,
    cells: Cells,
    seed_check: SeedCheck,
    table: ForecastTable,
    results_file: str,
) -> str:
    """Human-readable tables of every cell; the first delta_D in the main part, others after."""
    settings = config.summary
    scenarios = config.scenarios.expand()
    lambdas: list[Level] = [*sorted({s.lambda_a for s in scenarios})]
    shares: list[Level] = [*config.checkpoints, None]
    checkpoints = ", ".join(f"{f:g}" for f in config.checkpoints)
    deltas = ", ".join(f"{d:g}" for d in config.deltas)
    n_worlds = analysis.n_runs // max(1, len(analysis.forecasters))
    skipped = table.flags["skipped"]
    lines = [
        f"# {config.name}: run {run_id}",
        "",
        f"Generated from `{results_file}` by `sentinel.experiments.forecast_summary`; do not edit.",
        "",
        f"- NoReaction worlds on `{config.baseline}` baseline plans, {config.replications} "
        f"replications per instance and scenario ({n_worlds} worlds); world seeds as in WP2b. "
        f"Scenarios: {', '.join(s.name for s in scenarios)} (λ_S = {config.scenarios.lambda_s:g}, "
        f"λ_N = {config.scenarios.lambda_n:g}).",
        f"- Checkpoints t_f = floor(f · C_plan), f ∈ {{{checkpoints}}}; a checkpoint with "
        "C ≤ t_f is skipped. Forecasters: "
        + ", ".join(_describe(spec) for spec in config.forecasters)
        + "; one forecast seed per checkpoint (CRN).",
        f"- Deadlines D = ceil((1 + δ_D) C*) for δ_D ∈ {{{deltas}}}; on time: C ≤ D (a truncated "
        "world is late). Binary scores of p = P(C ≤ D) (spec 5.2): "
        f"Brier score, Murphy decomposition over {settings.bins} equal-width bins (REL, RES, UNC; "
        "the binning error is BS - (REL - RES + UNC)), ECE, sharpness = Var(p), log score with p "
        f"clipped to [{settings.log_clip:g}, {1 - settings.log_clip:g}].",
        "- Makespan distribution: CRPS of the empirical CDF and the absolute error of its median, "
        "both / C*; coverage of the 10-90 % interval and its width / C*; randomised PIT "
        f"(seed {settings.pit_seed}).",
        f"- [a, b]: 95 % percentile intervals of a cluster bootstrap over the instances of a set "
        f"({settings.bootstrap_resamples} resamples, seed {settings.bootstrap_seed}); paired "
        "differences use the same resamples.",
        "",
        "## Checks",
        "",
        seed_check.line(),
        f"- Skipped checkpoints: {int(skipped.sum()) // max(1, len(analysis.forecasters))}; worlds "
        f"truncated: {int(table.flags['truncated'][~skipped].sum())} forecast rows; rollouts "
        f"truncated: {int(np.nansum(table.numbers['rollouts_truncated']))}; belief fallbacks: "
        f"{int(np.nansum(table.numbers['fallbacks']))} (summed over forecasts).",
        "",
        "| Forecaster | Forecasts | Mean s / forecast | p95 s | Max s |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for k, name in enumerate(analysis.forecasters):
        times = analysis.wall_s[analysis.valid & (analysis.forecaster_row == k)]
        if times.size:
            lines.append(
                f"| {name} | {times.size} | {times.mean():.4f} | "
                f"{np.quantile(times, 0.95):.4f} | {times.max():.4f} |"
            )
    for i, delta in enumerate(config.deltas):
        if i == 1:
            lines += ["", "# Appendix: other deadline slacks"]
        for s, set_cfg in enumerate(config.sets):
            if not (analysis.set_row == s).any():
                continue
            label = f"{set_cfg.name.upper()} (C*: {REFERENCE_LABELS[set_cfg.reference]})"
            lines += ["", f"## {label}, δ_D = {delta:g}"]
            lines += _calibration_section(analysis, cells, i, s, shares)
            if i == 0:
                lines += _distribution_section(analysis, cells, s, shares)
            lines += _difference_section(config, cells, i, s, shares, None, i == 0)
            lines += _warning_section(analysis, config, cells, i, s, [*lambdas, None])
            if i == 0:
                lines += _lambda_section(analysis, config, cells, i, s, lambdas, shares)
                lines += _pit_section(analysis, cells, s, shares)
    return "\n".join(lines) + "\n"


def _describe(spec: ForecasterSpec) -> str:
    if spec.kind == "deterministic":
        return f"`{spec.name}` (deterministic, nominal state, no future disruptions)"
    parts = [f"{spec.n_rollouts} rollouts"]
    parts.append("future disruptions" if spec.future_disruptions else "no future disruptions")
    if spec.prior_scale != 1.0:
        parts.append(f"κ = {spec.prior_scale:g}")
    if spec.prior_pert is not None:
        pert = spec.prior_pert
        parts.append(f"PERT({pert.a:g}, {pert.m:g}, {pert.b:g})")
    return f"`{spec.name}` ({', '.join(parts)})"


def _calibration_section(
    analysis: Analysis, cells: Cells, i: int, s: int, shares: Sequence[Level]
) -> list[str]:
    lines = [
        "",
        "### Calibration of P(C ≤ D), pooled over λ_A",
        "",
        "| f | Forecaster | N | On time | Brier | REL | RES | UNC | Bin. err. | ECE | Sharpness "
        "| Log score |",
        "| --- | --- | ---: | ---: | --- | --- | --- | ---: | ---: | --- | ---: | --- |",
    ]
    for share in shares:
        for k, name in enumerate(analysis.forecasters):
            cell = cells.binary.get((i, s, k, share, None))
            if cell is None:
                continue
            lines.append(
                f"| {_level(share)} | {name} | {cell.n} | {_num(cell.on_time)} | "
                f"{_est(cell.brier)} | {_est(cell.reliability)} | {_est(cell.resolution)} | "
                f"{_num(cell.uncertainty)} | {_num(cell.binning_error, 4)} | {_est(cell.ece)} | "
                f"{_num(cell.sharpness)} | {_est(cell.log_score)} |"
            )
    return lines


def _distribution_section(
    analysis: Analysis, cells: Cells, s: int, shares: Sequence[Level]
) -> list[str]:
    lines = [
        "",
        "### Makespan distribution, pooled over λ_A",
        "",
        "| f | Forecaster | N | CRPS / C* | MAE / C* | Coverage 80 % | Width / C* |",
        "| --- | --- | ---: | --- | --- | --- | ---: |",
    ]
    for share in shares:
        for k, name in enumerate(analysis.forecasters):
            cell = cells.distribution.get((s, k, share, None))
            if cell is None:
                continue
            lines.append(
                f"| {_level(share)} | {name} | {cell.n} | {_est(cell.crps, 4)} | "
                f"{_est(cell.mae, 4)} | {_est(cell.coverage)} | {_num(cell.width, 4)} |"
            )
    return lines


def _difference_section(
    config: ForecastStudyConfig,
    cells: Cells,
    i: int,
    s: int,
    shares: Sequence[Level],
    lam: Level,
    with_crps: bool,
) -> list[str]:
    if not config.summary.differences:
        return []
    header = "| f | Difference | ΔBrier |" + (" ΔCRPS / C* |" if with_crps else "")
    lines = [
        "",
        "### Paired differences, pooled over λ_A (negative: the first forecaster scores better)",
        "",
        header,
        "| --- | --- | --- |" + (" --- |" if with_crps else ""),
    ]
    for share in shares:
        for d, (a, b) in enumerate(config.summary.differences):
            cell = cells.differences.get((i, s, d, share, lam))
            if cell is None:
                continue
            crps = f" {_est(cell.crps, 4)} |" if with_crps else ""
            lines.append(f"| {_level(share)} | {a} - {b} | {_est(cell.brier, 4)} |{crps}")
    return lines


def _warning_section(
    analysis: Analysis,
    config: ForecastStudyConfig,
    cells: Cells,
    i: int,
    s: int,
    lambdas: Sequence[Level],
) -> list[str]:
    lines = [
        "",
        "### Early warning (warned: p < θ at some checkpoint; lead time D - t_w in days)",
        "",
        "| λ_A | Forecaster | θ | Late runs | Warned | Lead time | On-time runs | False alarms |",
        "| --- | --- | ---: | ---: | --- | --- | ---: | --- |",
    ]
    for lam in lambdas:
        for k, name in enumerate(analysis.forecasters):
            for theta in config.summary.thresholds:
                cell = cells.warnings.get((i, s, k, theta, lam))
                if cell is None:
                    continue
                lines.append(
                    f"| {_level(lam)} | {name} | {theta:g} | {cell.late} | "
                    f"{_est(cell.warned)} | {_est(cell.lead, 1)} | {cell.on_time} | "
                    f"{_est(cell.false_alarms)} |"
                )
    return lines


def _lambda_section(
    analysis: Analysis,
    config: ForecastStudyConfig,
    cells: Cells,
    i: int,
    s: int,
    lambdas: Sequence[Level],
    shares: Sequence[Level],
) -> list[str]:
    lines = [
        "",
        "### By λ_A",
        "",
        "| λ_A | f | Forecaster | N | On time | Brier | ECE | CRPS / C* | Coverage 80 % |",
        "| --- | --- | --- | ---: | ---: | --- | --- | --- | --- |",
    ]
    for lam in lambdas:
        for share in shares:
            for k, name in enumerate(analysis.forecasters):
                binary = cells.binary.get((i, s, k, share, lam))
                dist = cells.distribution.get((s, k, share, lam))
                if binary is None or dist is None:
                    continue
                lines.append(
                    f"| {_level(lam)} | {_level(share)} | {name} | {binary.n} | "
                    f"{_num(binary.on_time)} | {_est(binary.brier)} | {_est(binary.ece)} | "
                    f"{_est(dist.crps, 4)} | {_est(dist.coverage)} |"
                )
    for lam in lambdas:
        diff = _difference_section(config, cells, i, s, shares, lam, True)
        if diff:
            diff[1] = f"### Paired differences at λ_A = {lam:g}"
            lines += diff
    return lines


def _pit_section(analysis: Analysis, cells: Cells, s: int, shares: Sequence[Level]) -> list[str]:
    bins = analysis.bins
    edges = " | ".join(f"{b / bins:g}-{(b + 1) / bins:g}" for b in range(bins))
    lines = [
        "",
        "### Randomised PIT of the makespan, % of forecasts per bin, pooled over λ_A",
        "",
        f"| f | Forecaster | {edges} |",
        "| --- | --- |" + " ---: |" * bins,
    ]
    for share in shares:
        for k, name in enumerate(analysis.forecasters):
            cell = cells.distribution.get((s, k, share, None))
            if cell is None:
                continue
            shown = " | ".join(f"{100 * c / cell.pit.sum():.1f}" for c in cell.pit)
            lines.append(f"| {_level(share)} | {name} | {shown} |")
    return lines


# --- LaTeX ----------------------------------------------------------------------------------


def _tex(text: str) -> str:
    return text.replace("_", r"\_")


def _tex_ci(estimate: Estimate, digits: int = 3, scale: float = 1.0) -> str:
    low, high = estimate.low * scale, estimate.high * scale
    return rf"{{\scriptsize[{_num(low, digits)}, {_num(high, digits)}]}}"


def calibration_table(run_id: str, config: ForecastStudyConfig, cells: Cells, i: int) -> str:
    """Booktabs tabular per set x checkpoint x forecaster, pooled over lambda_A, delta_D i."""
    lines = [
        f"% Generated by sentinel.experiments.forecast_summary from run {run_id}; do not edit.",
        f"% P(C <= D) with D = ceil((1 + {config.deltas[i]:g}) C*), pooled over lambda_A; 95 % "
        "cluster bootstrap intervals over instances;",
        f"% REL, RES: Murphy decomposition over {config.summary.bins} bins; CRPS / C*; coverage of "
        "the central 80 % interval in %.",
        r"\begin{tabular}{lllrlrrrrr}",
        r"\toprule",
        r"Set & $f$ & Forecaster & Brier & 95\,\% CI & REL & RES & ECE & CRPS$/C^*$ & "
        r"Cov.\ [\%] \\",
        r"\midrule",
    ]
    first_set = True
    for s, set_cfg in enumerate(config.sets):
        rows: list[str] = []
        for share in config.checkpoints:
            for k, spec in enumerate(config.forecasters):
                binary = cells.binary.get((i, s, k, share, None))
                dist = cells.distribution.get((s, k, share, None))
                if binary is None or dist is None:
                    continue
                rows.append(
                    f"{set_cfg.name.upper() if not rows else ''} & "
                    f"{f'{share:g}' if k == 0 else ''} & {_tex(spec.name)} & "
                    f"{_num(binary.brier.value)} & {_tex_ci(binary.brier)} & "
                    f"{_num(binary.reliability.value)} & {_num(binary.resolution.value)} & "
                    f"{_num(binary.ece.value)} & {_num(dist.crps.value, 4)} & "
                    f"{_num(100 * dist.coverage.value, 1)} " + r"\\"
                )
        if rows:
            if not first_set:
                lines.append(r"\midrule")
            first_set = False
            lines += rows
    lines += [r"\bottomrule", r"\end{tabular}"]
    return "\n".join(lines) + "\n"


def warning_table(run_id: str, config: ForecastStudyConfig, cells: Cells, i: int) -> str:
    """Booktabs tabular of early warning per set x forecaster x threshold, pooled over lambda_A."""
    lines = [
        f"% Generated by sentinel.experiments.forecast_summary from run {run_id}; do not edit.",
        f"% Early warning for D = ceil((1 + {config.deltas[i]:g}) C*), pooled over lambda_A: a run "
        "is warned at its first checkpoint with P(C <= D) < theta;",
        "% warned share of late runs and false alarms among on-time runs in %, lead time D - t_w "
        "in days; 95 % cluster bootstrap intervals.",
        r"\begin{tabular}{llrrrlrrl}",
        r"\toprule",
        r"Set & Forecaster & $\theta$ & Late & Warned [\%] & & Lead [d] & On time & "
        r"False alarms [\%] \\",
        r"\midrule",
    ]
    first_set = True
    for s, set_cfg in enumerate(config.sets):
        rows: list[str] = []
        for k, spec in enumerate(config.forecasters):
            for theta in config.summary.thresholds:
                cell = cells.warnings.get((i, s, k, theta, None))
                if cell is None:
                    continue
                rows.append(
                    f"{set_cfg.name.upper() if not rows else ''} & "
                    f"{_tex(spec.name) if theta == config.summary.thresholds[0] else ''} & "
                    f"{theta:g} & {cell.late} & {_num(100 * cell.warned.value, 1)} & "
                    f"{_tex_ci(cell.warned, 1, 100)} & {_num(cell.lead.value, 1)} & "
                    f"{cell.on_time} & {_num(100 * cell.false_alarms.value, 1)}\\,"
                    f"{_tex_ci(cell.false_alarms, 1, 100)} " + r"\\"
                )
        if rows:
            if not first_set:
                lines.append(r"\midrule")
            first_set = False
            lines += rows
    lines += [r"\bottomrule", r"\end{tabular}"]
    return "\n".join(lines) + "\n"


# --- Figures ------------------------------------------------------------------------------------


def _style(ax: Axes, *, grid_axis: Literal["both", "x", "y"] = "y") -> None:
    ax.grid(True, axis=grid_axis, color=_GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", which="both", labelsize=7, colors=_INK_2, length=2.5)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(_AXIS)


def _save(fig: Figure, path_stem: Path) -> list[str]:
    # Fixed metadata keeps repeated renders of the same results byte-identical.
    fig.savefig(path_stem.with_suffix(".pdf"), metadata={"CreationDate": None})
    fig.savefig(path_stem.with_suffix(".png"), dpi=200, metadata={"Software": None})
    return [f"{path_stem.name}.pdf", f"{path_stem.name}.png"]


def reliability_figure(path_stem: Path, config: ForecastStudyConfig, cells: Cells) -> list[str]:
    """Reliability diagrams for the first delta_D: rows of sets, columns of the configured
    checkpoints, one line per forecaster; below each, the forecasts per bin (log scale)."""
    shares = config.summary.reliability_checkpoints
    bins = config.summary.bins
    n_sets, n_fc = len(config.sets), len(config.forecasters)
    fig = Figure(figsize=(2.35 * len(shares), 3.1 * n_sets), layout="constrained")
    grid = fig.add_gridspec(2 * n_sets, len(shares), height_ratios=[3.0, 1.1] * n_sets)
    centres = (np.arange(bins) + 0.5) / bins
    slot = 1 / bins / (n_fc + 1)
    for row, set_cfg in enumerate(config.sets):
        for col, share in enumerate(shares):
            ax = fig.add_subplot(grid[2 * row, col])
            counts = fig.add_subplot(grid[2 * row + 1, col], sharex=ax)
            ax.plot([0, 1], [0, 1], color=_MUTED, linewidth=0.8, label="perfect calibration")
            for k, spec in enumerate(config.forecasters):
                cell = cells.binary.get((0, row, k, share, None))
                if cell is None:
                    continue
                n, p_sum, y_sum = cell.bins
                filled = n > 0
                ax.plot(
                    p_sum[filled] / n[filled],
                    y_sum[filled] / n[filled],
                    color=_COLORS[k % len(_COLORS)],
                    marker=_MARKERS[k % len(_MARKERS)],
                    markersize=3.5,
                    markeredgecolor="white",
                    markeredgewidth=0.5,
                    linewidth=1.3,
                    label=spec.name,
                )
                offset = (k - (n_fc - 1) / 2) * slot
                counts.bar(
                    centres[filled] + offset,
                    n[filled],
                    width=0.8 * slot,
                    color=_COLORS[k % len(_COLORS)],
                    linewidth=0,
                )
            ax.set_xlim(-0.03, 1.03)  # markers at p = 0 and p = 1 stay whole
            ax.set_ylim(-0.03, 1.03)
            ax.set_title(f"{set_cfg.name.upper()}, f = {share:g}", fontsize=8.5, color=_INK)
            ax.tick_params(labelbottom=False)
            counts.set_yscale("log")
            counts.yaxis.set_major_locator(LogLocator(base=10))
            counts.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
            counts.yaxis.set_minor_formatter(NullFormatter())
            counts.set_xlabel(r"forecast $P(C \leq D)$", fontsize=7.5, color=_INK_2)
            if col == 0:
                ax.set_ylabel("observed frequency on time", fontsize=7.5, color=_INK_2)
                counts.set_ylabel("forecasts", fontsize=7.5, color=_INK_2)
            _style(ax, grid_axis="both")
            _style(counts)
    handles, labels = fig.axes[0].get_legend_handles_labels()
    fig.legend(
        handles, labels, loc="outside upper center", ncols=len(labels), frameon=False, fontsize=7.5
    )
    return _save(fig, path_stem)


def brier_figure(path_stem: Path, config: ForecastStudyConfig, cells: Cells) -> list[str]:
    """Brier score for the first delta_D against the checkpoint share f, one line per
    forecaster with its 95 % band, one panel per set."""
    n_sets = len(config.sets)
    fig = Figure(figsize=(3.1 * n_sets, 2.5), layout="constrained")
    axes = fig.subplots(1, n_sets, squeeze=False, sharey=True)
    for s, set_cfg in enumerate(config.sets):
        ax = axes[0][s]
        for k, spec in enumerate(config.forecasters):
            points = [
                (share, cells.binary[(0, s, k, share, None)].brier)
                for share in config.checkpoints
                if (0, s, k, share, None) in cells.binary
            ]
            if not points:
                continue
            xs = [share for share, _ in points]
            color = _COLORS[k % len(_COLORS)]
            ax.fill_between(
                xs, [e.low for _, e in points], [e.high for _, e in points], color=color, alpha=0.12
            )
            ax.plot(
                xs,
                [e.value for _, e in points],
                color=color,
                marker=_MARKERS[k % len(_MARKERS)],
                markersize=3.5,
                linewidth=1.3,
                label=spec.name,
            )
        ax.set_xticks(list(config.checkpoints), [f"{f:g}" for f in config.checkpoints])
        ax.set_title(set_cfg.name.upper(), fontsize=8.5, color=_INK)
        ax.set_xlabel(r"checkpoint $f$ (share of $C_{plan}$)", fontsize=7.5, color=_INK_2)
        if s == 0:
            label = rf"Brier score, $\delta_D = {config.deltas[0]:g}$"
            ax.set_ylabel(label, fontsize=7.5, color=_INK_2)
        ax.set_ylim(bottom=0)
        _style(ax)
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(
        handles, labels, loc="outside upper center", ncols=len(labels), frameon=False, fontsize=7.5
    )
    return _save(fig, path_stem)


def pit_figure(path_stem: Path, config: ForecastStudyConfig, cells: Cells) -> list[str]:
    """Randomised PIT histograms (density, uniform = 1) pooled over checkpoints and lambda_A:
    rows of sets, one column per forecaster."""
    bins = config.summary.bins
    n_sets, n_fc = len(config.sets), len(config.forecasters)
    fig = Figure(figsize=(2.0 * n_fc, 1.9 * n_sets), layout="constrained")
    axes = fig.subplots(n_sets, n_fc, squeeze=False, sharex=True, sharey=True)
    centres = (np.arange(bins) + 0.5) / bins
    for s, set_cfg in enumerate(config.sets):
        for k, spec in enumerate(config.forecasters):
            ax = axes[s][k]
            cell = cells.distribution.get((s, k, None, None))
            if cell is not None and cell.pit.sum() > 0:
                density = bins * cell.pit / cell.pit.sum()
                ax.bar(centres, density, width=0.8 / bins, color=_COLORS[k % len(_COLORS)])
            ax.axhline(1.0, color=_MUTED, linewidth=0.8)
            ax.set_title(f"{set_cfg.name.upper()}, {spec.name}", fontsize=8, color=_INK)
            ax.set_xlim(0, 1)
            if s == n_sets - 1:
                ax.set_xlabel("PIT", fontsize=7.5, color=_INK_2)
            if k == 0:
                ax.set_ylabel("density", fontsize=7.5, color=_INK_2)
            _style(ax)
    return _save(fig, path_stem)


# --- Entry points -------------------------------------------------------------------------------


@dataclass(frozen=True)
class SummaryOutputs:
    """Names of the generated files and the result of the WP2b seed check."""

    files: list[str]
    seed_check: SeedCheck


def write_summaries(
    run_dir: Path, run_id: str, config: ForecastStudyConfig, results_file: str
) -> SummaryOutputs:
    """Generate summary.md, the LaTeX tables and the figures from the run's forecasts file."""
    table = read_forecasts(run_dir / results_file)
    seed_check = wp2b_check(table, config.wp2b_results)
    analysis = Analysis(table, config)
    cells = compute_cells(analysis, config)
    settings = config.summary
    summary = summary_markdown(run_id, config, analysis, cells, seed_check, table, results_file)
    (run_dir / SUMMARY_FILE).write_text(summary, encoding="utf-8")
    files = [SUMMARY_FILE]
    for i, delta in enumerate(config.deltas):
        suffix = "" if i == 0 else f"_delta{delta:g}"
        for stem, text in (
            (settings.table, calibration_table(run_id, config, cells, i)),
            (settings.warning_table, warning_table(run_id, config, cells, i)),
        ):
            name = f"{stem}{suffix}.tex"
            (run_dir / name).write_text(text, encoding="utf-8")
            files.append(name)
    prefix = run_dir / settings.figure_prefix
    files += reliability_figure(prefix.with_name(f"{prefix.name}_reliability"), config, cells)
    files += brier_figure(prefix.with_name(f"{prefix.name}_brier"), config, cells)
    files += pit_figure(prefix.with_name(f"{prefix.name}_pit"), config, cells)
    return SummaryOutputs(files, seed_check)


def regenerate(run_dir: Path) -> SummaryOutputs:
    """Regenerate the summaries of an existing run directory from its manifest and forecasts."""
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    config = ForecastStudyConfig.model_validate(manifest["config"])
    return write_summaries(run_dir, manifest["run_id"], config, manifest["results_file"])
