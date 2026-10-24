"""RQ1 error analysis of a WBS study run (WP7): the run's sessions replayed from its bundle
(replay mode: no LLM call, a request missing from the bundle is an error), the outcome of every
true edge by its phrasing (`sentinel.wbs.analysis`), and a check that the replay reproduces the
score columns of every committed round row."""

import csv
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import numpy as np

from sentinel.data.psplib_loader import natural_key
from sentinel.experiments.forecast_summary import Estimate
from sentinel.experiments.runs import derive_seed
from sentinel.experiments.wbs_config import WbsStudyConfig
from sentinel.experiments.wbs_study import (
    BUNDLE_FILE,
    RESULTS_FILE,
    ROUNDS_FILE,
    build_subjects,
    data_provenance,
    llm_seed,
    make_client,
    score_columns,
    score_round,
)
from sentinel.forecasting.metrics import cluster_resamples, percentile_interval, resampled_ratio
from sentinel.llm import LlmCache
from sentinel.wbs.analysis import (
    DISTANCE_BINS,
    ErrorCell,
    Rate,
    answers_by_round,
    distance_label,
    edge_outcomes,
    error_cells,
)
from sentinel.wbs.extract import repair
from sentinel.wbs.narrate import EdgePhrasing, Style, edge_phrasings

TABLE = "table_wp6_rq1_errors"
SIDES = ("successor", "predecessor")


class DataMismatch(RuntimeError):
    """The instance data differ from those the run recorded."""


@dataclass(frozen=True)
class ReplayedErrors:
    """The error cells of a run and how many committed round rows the replay reproduced."""

    cells: list[ErrorCell]
    round_rows: int
    reproduced: int


def replay_errors(run_dir: Path, config: WbsStudyConfig) -> ReplayedErrors:
    """Replay every session of the run from its bundle and pool the edge outcomes per backend,
    style and round (backends in the run's order, then styles and rounds)."""
    manifest_path = run_dir / "manifest.json"  # absent while the run writes its summaries
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        recorded = manifest.get("data", {}).get("instances_content_sha256")
        current = data_provenance(config)["instances_content_sha256"]
        if recorded is not None and recorded != current:
            raise DataMismatch(f"the instance data {current} differ from the run's {recorded}")
    sessions = _sessions(run_dir / RESULTS_FILE, config)
    backends = list(dict.fromkeys(backend for _, _, backend in sessions))
    cache = LlmCache(run_dir / BUNDLE_FILE, readonly=True, store_prompts=config.store_prompts)
    clients = {name: make_client(name, config.backend[name], cache, "replay") for name in backends}
    committed = _round_rows(run_dir / ROUNDS_FILE)
    subjects = {s.stem: s for s in build_subjects(config, None)}
    rounds = config.extraction.max_repair_rounds
    replayed = []
    reproduced = 0
    for stem, style, backend in sorted(
        sessions, key=lambda s: (backends.index(s[2]), config.styles.index(s[1]))
    ):
        subject = subjects[stem]
        session = repair(
            clients[backend],
            subject.texts[style],
            seed=llm_seed(config, subject, style),
            settings=config.extraction,
        )
        phrasings = edge_phrasings(subject.instance, style=style, seed=subject.narrator_seed)
        answers = answers_by_round(session, rounds)
        replayed.append(
            (stem, backend, style, [edge_outcomes(a, subject.truth, phrasings) for a in answers])
        )
        for index in range(rounds + 1):
            step = session.rounds[min(index, len(session.rounds) - 1)]
            columns = score_columns(score_round(subject, step))
            row = committed.get((stem, style, backend, index), {})
            reproduced += all(row.get(name) == _cell(value) for name, value in columns.items())
    return ReplayedErrors(error_cells(replayed), len(committed), reproduced)


def _sessions(path: Path, config: WbsStudyConfig) -> list[tuple[str, Style, str]]:
    """The (instance, style, backend) sessions of a results file in file order."""
    with path.open(newline="", encoding="utf-8") as handle:
        keys = [(row["instance"], row["style"], row["backend"]) for row in csv.DictReader(handle)]
    unknown = sorted({style for _, style, _ in keys} - set(config.styles))
    if unknown:
        raise ValueError(f"{path} has styles outside the run config: {unknown}")
    return [(stem, cast(Style, style), backend) for stem, style, backend in dict.fromkeys(keys)]


def _round_rows(path: Path) -> dict[tuple[str, str, str, int], dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {
            (row["instance"], row["style"], row["backend"], int(row["round"])): row
            for row in csv.DictReader(handle)
        }


def _cell(value: object) -> str:
    """A value as `write_csv` writes it."""
    if value is None:
        return ""
    return str(int(value)) if isinstance(value, bool) else str(value)


@dataclass(frozen=True)
class SideIntervals:
    """Recall by side, their gap and the predecessor side's share of the missed edges (in %),
    with 95 % cluster bootstrap intervals over instances."""

    successor: Estimate
    predecessor: Estimate
    gap: Estimate
    missed_predecessor: Estimate


def side_intervals(cell: ErrorCell, weights: np.ndarray, instances: Sequence[str]) -> SideIntervals:
    """The estimates of a cell; `weights` resamples `instances` (cluster bootstrap)."""

    def sums(keep: Callable[[EdgePhrasing], bool]) -> tuple[np.ndarray, np.ndarray]:
        rates = cell.by_instance(keep)
        found = np.array([rates.get(i, Rate(0, 0)).found for i in instances], dtype=np.float64)
        total = np.array([rates.get(i, Rate(0, 0)).total for i in instances], dtype=np.float64)
        return found, total

    def estimate(value: float | None, replicates: np.ndarray) -> Estimate:
        low, high = percentile_interval(replicates)
        return Estimate(float("nan") if value is None else value, low, high)

    found_s, total_s = sums(lambda p: p.side == "successor")
    found_p, total_p = sums(lambda p: p.side == "predecessor")
    found_a, total_a = sums(lambda _: True)
    succ = resampled_ratio(weights, found_s, total_s)
    pred = resampled_ratio(weights, found_p, total_p)
    missed = resampled_ratio(weights, total_p - found_p, total_a - found_a)
    s_rate, p_rate = cell.side("successor").value, cell.side("predecessor").value
    share = cell.missing_predecessor_share
    return SideIntervals(
        estimate(s_rate, succ),
        estimate(p_rate, pred),
        estimate(None if s_rate is None or p_rate is None else s_rate - p_rate, succ - pred),
        estimate(None if share is None else 100 * share, 100 * missed),
    )


def bootstrap_weights(
    cells: Sequence[ErrorCell], config: WbsStudyConfig
) -> tuple[np.ndarray, list[str]]:
    """One resample matrix over the run's instances (natural order), seeded from
    (bootstrap_seed, "bootstrap", "wp6_rq1_errors"), shared by every estimate."""
    instances = sorted({i for c in cells for i, _ in c.outcomes}, key=natural_key)
    settings = config.summary
    rng = np.random.default_rng(derive_seed(settings.bootstrap_seed, "bootstrap", "wp6_rq1_errors"))
    return cluster_resamples(max(1, len(instances)), settings.bootstrap_resamples, rng), instances


def _rate(rate: Rate, digits: int = 3) -> str:
    return "-" if rate.value is None else f"{rate.value:.{digits}f}"


def _share(value: float | None) -> str:
    return "-" if value is None else f"{100 * value:.1f}"


def _ci(estimate: Estimate, digits: int, *, signed: bool = False) -> str:
    if estimate.value != estimate.value:
        return "-"
    sign = "+" if signed else ""
    return (
        f"{estimate.value:{sign}.{digits}f} "
        f"[{estimate.low:{sign}.{digits}f}, {estimate.high:{sign}.{digits}f}]"
    )


def summary_section(errors: ReplayedErrors, config: WbsStudyConfig, bundle: str) -> list[str]:
    """The error-analysis section of `summary.md`."""
    bins = [distance_label(low, high) for low, high in DISTANCE_BINS]
    weights, instances = bootstrap_weights(errors.cells, config)
    lines = [
        "## Error analysis: missed precedence edges",
        "",
        f"Every session replayed from `{bundle}` in replay mode (no LLM call): "
        f"{errors.reproduced} of {errors.round_rows} round rows of `rounds.csv` reproduced "
        "(every score column). Edges: the true edges whose two activities the answer matches by "
        "name (those of edge recall), pooled over the sessions of a cell; recall = stated / "
        'edges. Side: the narrative states each dependency once, with its successor ("It can '
        'only start once A is done.") or with its predecessor ("It must be finished before C '
        "begins.\"); the structured style lists every activity's predecessors. Numbers: the "
        "stating block's duration in words or digits. d: paragraphs between the blocks of the two "
        "activities (structured: one paragraph per activity). Missed: edges not stated; on the "
        "predecessor side: their share stated with the predecessor (all: the share of all "
        "edges). Intervals: 95 % percentile intervals of a cluster bootstrap over instances "
        f"({config.summary.bootstrap_resamples} resamples).",
        "",
        "| Backend | Style | Round | Sessions | Edges | Recall | Successor side (n) | "
        "Predecessor side (n) | Words | Digits | "
        + " | ".join(f"d = {b}" for b in bins)
        + " | Missed | On predecessor side [%] | All on predecessor side [%] |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | "
        + " | ".join("---:" for _ in bins)
        + " | ---: | ---: | ---: |",
    ]
    for cell in errors.cells:
        succ, pred = cell.side("successor"), cell.side("predecessor")
        lines.append(
            f"| {cell.backend} | {cell.style} | {cell.round} | {cell.sessions} | "
            f"{cell.rate().total} | {_rate(cell.rate())} | {_rate(succ)} ({succ.total}) | "
            f"{_rate(pred)} ({pred.total}) | {_rate(cell.numbers('words'))} | "
            f"{_rate(cell.numbers('digits'))} | "
            + " | ".join(_rate(cell.distance(low, high)) for low, high in DISTANCE_BINS)
            + f" | {cell.rate().missing} | {_share(cell.missing_predecessor_share)} | "
            f"{_share(cell.predecessor_share)} |"
        )
    narrative = [cell for cell in errors.cells if cell.style == "narrative"]
    if not narrative:
        return [*lines, ""]
    lines += [
        "",
        "Narrative style, recall by side and distance (edges in parentheses):",
        "",
        "| Backend | Round | Side | " + " | ".join(f"d = {b}" for b in bins) + " |",
        "| --- | ---: | --- | " + " | ".join("---:" for _ in bins) + " |",
    ]
    for cell in narrative:
        for side in SIDES:
            parts = []
            for low, high in DISTANCE_BINS:
                rate = cell.distance(low, high, side)
                parts.append(f"{_rate(rate)} ({rate.total})")
            lines.append(f"| {cell.backend} | {cell.round} | {side} | " + " | ".join(parts) + " |")
    lines += [
        "",
        "Narrative style, recall by side with 95 % intervals:",
        "",
        "| Backend | Round | Successor side | Predecessor side | Successor - predecessor | "
        "Missed on predecessor side [%] |",
        "| --- | ---: | --- | --- | --- | --- |",
    ]
    for cell in narrative:
        e = side_intervals(cell, weights, instances)
        lines.append(
            f"| {cell.backend} | {cell.round} | {_ci(e.successor, 3)} | {_ci(e.predecessor, 3)} | "
            f"{_ci(e.gap, 3, signed=True)} | {_ci(e.missed_predecessor, 1)} |"
        )
    return [*lines, ""]


def latex_table(run_id: str, errors: ReplayedErrors, config: WbsStudyConfig) -> str:
    """Booktabs tabular of the narrative cells: recall overall, by side and by distance, and the
    predecessor side's share of the missed edges with its bootstrap interval."""
    weights, instances = bootstrap_weights(errors.cells, config)
    bins = ["$d=0$", "$1$--$2$", "$3$--$5$", r"${\geq}6$"]
    if len(bins) != len(DISTANCE_BINS):
        raise ValueError("the LaTeX table needs one header per distance bin")
    lines = [
        f"% Generated by sentinel.experiments.wbs_errors from run {run_id}; do not edit.",
        "% Narrative style: recall of the true edges between matched activities, pooled over "
        "the sessions of a backend and round, by the side that states the dependency and by",
        "% the paragraph distance d of the two activities; Missed pred.: share of the missed edges "
        "stated with the predecessor, 95 % cluster bootstrap interval over instances.",
        "% Typeset with \\small.",
        r"{\setlength{\tabcolsep}{3pt}%",
        r"\begin{tabular}{@{}lrrrrrrrrrr@{}}",
        r"\toprule",
        "Backend & Round & Edges & Recall & Succ. & Pred. & "
        + " & ".join(bins)
        + r" & Missed pred. [\%] \\",
        r"\midrule",
    ]
    for cell in errors.cells:
        if cell.style != "narrative":
            continue
        e = side_intervals(cell, weights, instances)
        share = e.missed_predecessor
        lines.append(
            f"{_latex_text(cell.backend) if cell.round == 0 else ''} & {cell.round} & "
            f"{cell.rate().total} & {_rate(cell.rate())} & {_rate(cell.side('successor'))} & "
            f"{_rate(cell.side('predecessor'))} & "
            + " & ".join(_rate(cell.distance(low, high)) for low, high in DISTANCE_BINS)
            + f" & {share.value:.1f} \\tiny[{share.low:.1f}, {share.high:.1f}] \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}}"]
    return "\n".join(lines) + "\n"


def _latex_text(text: str) -> str:
    for char in "\\&%$#_{}":
        text = text.replace(char, f"\\{char}" if char != "\\" else r"\textbackslash{}")
    return text
