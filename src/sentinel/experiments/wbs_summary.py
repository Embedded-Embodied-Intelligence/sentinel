"""Summaries of an RQ1 WBS extraction run (WP6a), generated from its results files only.

Writes `summary.md` with every statistic, the LaTeX table `<table>.tex`, the figure
`<figure>.pdf/.png` (share of valid answers and mean edge F1 after repair rounds 0..3, per
backend and style) and `summary_manifest.json` (provenance as in ADR-0011). Rates (valid,
exact, team exact) carry 95 % Wilson intervals over the sessions of a cell (Wilson 1927).
Paired differences repair - single-shot are taken within sessions, since one session yields
both conditions, and carry 95 % percentile intervals of a cluster bootstrap over instances
(Davison & Hinkley 1997; a cell pooled over the styles has two sessions per instance). Duration
and crew accuracy are pooled over the matched activities of a cell (ratio of sums), the other
scores are means over sessions; the makespan error is over sessions with a valid answer. A run
with a replay bundle also gets the error analysis of its missed precedence edges (WP7,
`wbs_errors`: sessions replayed from the bundle, texts narrated from the PSPLIB data) as a
section and `table_wp6_rq1_errors.tex`. To regenerate the summaries of a run:

    uv run sentinel summarise-wbs results/wp6/<run_id>
"""

import csv
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from sentinel.data.psplib_loader import natural_key
from sentinel.experiments.forecast_summary import (
    GIT_EXCLUDE,
    MANIFEST_FILE,
    SUMMARY_FILE,
    SUMMARY_MANIFEST_FILE,
    Estimate,
)
from sentinel.experiments.runs import derive_seed, load_toml, summary_provenance, write_json
from sentinel.experiments.simulation_summary import wilson_interval
from sentinel.experiments.wbs_config import WbsStudyConfig
from sentinel.forecasting.metrics import (
    FloatArray,
    IntArray,
    cluster_resamples,
    percentile_interval,
    resampled_ratio,
)

RESULTS_FILE = "results.csv"
ROUNDS_FILE = "rounds.csv"
CONDITION_LABELS = {"single_shot": "single shot", "repair": "repair"}
_INK, _INK_2, _GRID, _AXIS = "#0b0b0b", "#52514e", "#e1e0d9", "#c3c2b7"
_COLORS = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100")  # categorical slots 1-4, by backend
_STYLE_LINES = {"structured": ("-", "o"), "narrative": ("--", "s")}

Session = tuple[str, str, str, str]  # set, instance, style, backend


def _number(text: str) -> float:
    return float(text) if text else math.nan


@dataclass(frozen=True)
class ResultRow:
    """One row of results.csv: a condition of one session."""

    set_name: str
    instance: str
    style: str
    backend: str
    model: str
    condition: str
    rounds_used: int
    calls: int
    unchanged_rounds: int
    valid: bool
    exact: bool
    team_exact: bool
    activity_recall: float
    activity_precision: float
    edge_precision: float
    edge_recall: float
    edge_f1: float
    team_accuracy: float
    n_matched: int
    durations_correct: int
    crews_correct: int
    makespan_rel_error: float
    prompt_tokens: int
    completion_tokens: int
    latency_s: float
    issues: str

    @property
    def session(self) -> Session:
        return (self.set_name, self.instance, self.style, self.backend)


@dataclass(frozen=True)
class RoundRow:
    """One row of rounds.csv: the answer of a session after a round."""

    set_name: str
    instance: str
    style: str
    backend: str
    round: int
    valid: bool
    edge_f1: float


def read_results(path: Path) -> list[ResultRow]:
    """The rows of a results.csv."""
    with path.open(newline="", encoding="utf-8") as handle:
        return [
            ResultRow(
                set_name=r["set"],
                instance=r["instance"],
                style=r["style"],
                backend=r["backend"],
                model=r["model"],
                condition=r["condition"],
                rounds_used=int(r["rounds_used"]),
                calls=int(r["calls"]),
                unchanged_rounds=int(r["unchanged_rounds"]),
                valid=r["valid"] == "1",
                exact=r["exact"] == "1",
                team_exact=r["team_exact"] == "1",
                activity_recall=_number(r["activity_recall"]),
                activity_precision=_number(r["activity_precision"]),
                edge_precision=_number(r["edge_precision"]),
                edge_recall=_number(r["edge_recall"]),
                edge_f1=_number(r["edge_f1"]),
                team_accuracy=_number(r["team_accuracy"]),
                n_matched=int(r["n_matched"]),
                durations_correct=int(r["durations_correct"]),
                crews_correct=int(r["crews_correct"]),
                makespan_rel_error=_number(r["makespan_rel_error"]),
                prompt_tokens=int(r["prompt_tokens"]),
                completion_tokens=int(r["completion_tokens"]),
                latency_s=float(r["latency_s"]),
                issues=r["issues"],
            )
            for r in csv.DictReader(handle)
        ]


def read_rounds(path: Path) -> list[RoundRow]:
    """The rows of a rounds.csv."""
    with path.open(newline="", encoding="utf-8") as handle:
        return [
            RoundRow(
                r["set"],
                r["instance"],
                r["style"],
                r["backend"],
                int(r["round"]),
                r["valid"] == "1",
                _number(r["edge_f1"]),
            )
            for r in csv.DictReader(handle)
        ]


@dataclass(frozen=True)
class Cell:
    """Statistics of the rows of one (backend, style or pooled, condition)."""

    n: int
    valid: int
    exact: int
    team_exact: int
    activity_recall: float
    activity_precision: float
    edge_precision: float
    edge_recall: float
    edge_f1: float
    duration_accuracy: float
    crew_accuracy: float
    team_accuracy: float
    makespan_n: int
    makespan_abs_error: float
    makespan_equal: int
    rounds_used: float
    unchanged_rounds: float
    calls: float
    prompt_tokens: float
    completion_tokens: float
    latency_s: float

    def share(self, count: int) -> float:
        return count / self.n

    def interval(self, count: int) -> tuple[float, float]:
        """95 % Wilson interval of a share of this cell's sessions."""
        return wilson_interval(count, self.n)


def _mean(values: Sequence[float]) -> float:
    finite = [v for v in values if not math.isnan(v)]
    return sum(finite) / len(finite) if finite else math.nan


def aggregate(rows: Sequence[ResultRow]) -> Cell:
    """The cell of a non-empty group of rows."""
    matched = sum(r.n_matched for r in rows)
    errors = [r.makespan_rel_error for r in rows if not math.isnan(r.makespan_rel_error)]
    return Cell(
        n=len(rows),
        valid=sum(r.valid for r in rows),
        exact=sum(r.exact for r in rows),
        team_exact=sum(r.team_exact for r in rows),
        activity_recall=_mean([r.activity_recall for r in rows]),
        activity_precision=_mean([r.activity_precision for r in rows]),
        edge_precision=_mean([r.edge_precision for r in rows]),
        edge_recall=_mean([r.edge_recall for r in rows]),
        edge_f1=_mean([r.edge_f1 for r in rows]),
        duration_accuracy=sum(r.durations_correct for r in rows) / matched if matched else math.nan,
        crew_accuracy=sum(r.crews_correct for r in rows) / matched if matched else math.nan,
        team_accuracy=_mean([r.team_accuracy for r in rows]),
        makespan_n=len(errors),
        makespan_abs_error=_mean([abs(e) for e in errors]),
        makespan_equal=sum(e == 0 for e in errors),
        rounds_used=_mean([float(r.rounds_used) for r in rows]),
        unchanged_rounds=_mean([float(r.unchanged_rounds) for r in rows]),
        calls=_mean([float(r.calls) for r in rows]),
        prompt_tokens=_mean([float(r.prompt_tokens) for r in rows]),
        completion_tokens=_mean([float(r.completion_tokens) for r in rows]),
        latency_s=_mean([r.latency_s for r in rows]),
    )


@dataclass(frozen=True)
class Difference:
    """Paired differences repair - single-shot over the sessions of a cell: valid and exact
    shares in percentage points, the session means and the pooled accuracies; `repaired` is
    the number of sessions that used at least one repair round."""

    n: int
    repaired: int
    valid: Estimate
    exact: Estimate
    activity_recall: Estimate
    edge_f1: Estimate
    duration_accuracy: Estimate
    crew_accuracy: Estimate


CellKey = tuple[str, str | None, str]  # backend, style (None: pooled), condition


class Analysis:
    """Cells, paired differences and scores by round of a run, in the config's backend and
    style order. Clusters are the run's instances; one resample matrix, seeded from
    (bootstrap_seed, "bootstrap", "wp6_rq1"), serves every difference."""

    def __init__(
        self, rows: Sequence[ResultRow], rounds: Sequence[RoundRow], config: WbsStudyConfig
    ) -> None:
        self.config = config
        present = {r.backend for r in rows}
        known = [*config.backends, *sorted(set(config.backend) - set(config.backends))]
        self.backends = [b for b in known if b in present]
        self.styles = [s for s in config.styles if any(r.style == s for r in rows)]
        self.models = {r.backend: r.model for r in rows}
        groups: dict[CellKey, list[ResultRow]] = {}
        for row in rows:
            groups.setdefault((row.backend, row.style, row.condition), []).append(row)
            groups.setdefault((row.backend, None, row.condition), []).append(row)
        self.cells = {key: aggregate(group) for key, group in groups.items()}
        self.rows = list(rows)
        names = sorted(
            {(r.set_name, r.instance) for r in rows}, key=lambda k: (k[0], natural_key(k[1]))
        )
        self.instances = names
        self.clusters = {name: c for c, name in enumerate(names)}
        settings = config.summary
        rng = np.random.default_rng(derive_seed(settings.bootstrap_seed, "bootstrap", "wp6_rq1"))
        self.weights = cluster_resamples(max(1, len(names)), settings.bootstrap_resamples, rng)
        self.differences: dict[tuple[str, str | None], Difference] = {}
        for backend in self.backends:
            for style in [*self.styles, None]:
                difference = self._difference(backend, style)
                if difference is not None:
                    self.differences[(backend, style)] = difference
        self.by_round: dict[tuple[str, str], list[tuple[int, int, int, float]]] = {}
        for backend in self.backends:
            for style in self.styles:
                mine = [r for r in rounds if r.backend == backend and r.style == style]
                steps = sorted({r.round for r in mine})
                self.by_round[(backend, style)] = [
                    (
                        step,
                        sum(r.valid for r in mine if r.round == step),
                        sum(1 for r in mine if r.round == step),
                        _mean([r.edge_f1 for r in mine if r.round == step]),
                    )
                    for step in steps
                ]

    def cell(self, backend: str, style: str | None, condition: str) -> Cell | None:
        return self.cells.get((backend, style, condition))

    def _difference(self, backend: str, style: str | None) -> Difference | None:
        def chosen(condition: str) -> dict[Session, ResultRow]:
            return {
                r.session: r
                for r in self.rows
                if r.backend == backend and r.condition == condition and style in (None, r.style)
            }

        single, repaired = chosen("single_shot"), chosen("repair")
        sessions = sorted(set(single) & set(repaired))
        if not sessions:
            return None
        pairs = [(single[s], repaired[s]) for s in sessions]
        codes = np.array([self.clusters[(s[0], s[1])] for s in sessions], dtype=np.int64)

        def mean(values: Sequence[float]) -> Estimate:
            return self._mean(codes, values)

        return Difference(
            n=len(pairs),
            repaired=sum(b.rounds_used > 0 for _, b in pairs),
            valid=mean([100.0 * (b.valid - a.valid) for a, b in pairs]),
            exact=mean([100.0 * (b.exact - a.exact) for a, b in pairs]),
            activity_recall=mean([b.activity_recall - a.activity_recall for a, b in pairs]),
            edge_f1=mean([b.edge_f1 - a.edge_f1 for a, b in pairs]),
            duration_accuracy=self._pooled(
                codes,
                [
                    (a.durations_correct, a.n_matched, b.durations_correct, b.n_matched)
                    for a, b in pairs
                ],
            ),
            crew_accuracy=self._pooled(
                codes,
                [(a.crews_correct, a.n_matched, b.crews_correct, b.n_matched) for a, b in pairs],
            ),
        )

    def _mean(self, codes: IntArray, values: Sequence[float]) -> Estimate:
        size = self.weights.shape[1]
        total = np.bincount(codes, weights=np.asarray(values, dtype=np.float64), minlength=size)
        count = np.bincount(codes, minlength=size).astype(np.float64)
        value = float(total.sum() / count.sum()) if count.sum() else math.nan
        return Estimate(value, *percentile_interval(resampled_ratio(self.weights, total, count)))

    def _pooled(self, codes: IntArray, parts: Sequence[tuple[int, int, int, int]]) -> Estimate:
        """Difference of two ratios of sums (repair - single shot), resampled together."""
        size = self.weights.shape[1]
        sums = [
            np.bincount(
                codes, weights=np.asarray([p[i] for p in parts], dtype=np.float64), minlength=size
            )
            for i in range(4)
        ]
        value = _ratio(sums[2].sum(), sums[3].sum()) - _ratio(sums[0].sum(), sums[1].sum())
        replicates: FloatArray = resampled_ratio(self.weights, sums[2], sums[3]) - resampled_ratio(
            self.weights, sums[0], sums[1]
        )
        return Estimate(value, *percentile_interval(replicates))


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else math.nan


def _pct(cell: Cell, count: int) -> str:
    low, high = cell.interval(count)
    return f"{100 * cell.share(count):.1f} [{100 * low:.1f}, {100 * high:.1f}]"


def _num(value: float, digits: int = 3) -> str:
    return "-" if math.isnan(value) else f"{value:.{digits}f}"


def _signed(estimate: Estimate, digits: int) -> str:
    if math.isnan(estimate.value):
        return "-"
    return f"{estimate.value:+.{digits}f} [{estimate.low:+.{digits}f}, {estimate.high:+.{digits}f}]"


def _style_label(style: str | None) -> str:
    return "pooled" if style is None else style


def summary_markdown(
    run_id: str, analysis: Analysis, rows: Sequence[ResultRow], *, git: Mapping[str, Any]
) -> str:
    """Every statistic of the run as Markdown tables."""
    config = analysis.config
    commit = git.get("commit") or "unknown"
    lines = [
        f"# RQ1 WBS extraction — run {run_id}",
        "",
        f"Generated by `sentinel.experiments.wbs_summary` at commit `{str(commit)[:12]}`"
        f"{' (dirty)' if git.get('dirty') else ''} from `{RESULTS_FILE}` and `{ROUNDS_FILE}`.",
        "",
        f"- Instances: {len(analysis.instances)} ("
        + ", ".join(f"{s.name} every {s.stride}th" for s in config.sets)
        + f"); styles: {', '.join(analysis.styles)}.",
        "- Backends: "
        + ", ".join(f"{b} (`{analysis.models.get(b, '?')}`)" for b in analysis.backends)
        + ".",
        f"- Conditions: single shot (round 0 of each session) and repair (at most "
        f"{config.extraction.max_repair_rounds} repair rounds); prompts "
        f"{config.extraction.prompt_version}, temperature {config.extraction.temperature:g}, "
        f"max tokens {config.extraction.max_tokens}.",
        "- Rates: share of sessions with 95 % Wilson intervals. Paired differences repair - single "
        f"shot: 95 % cluster bootstrap over instances ({config.summary.bootstrap_resamples} "
        "resamples). Duration and crew accuracy pooled over matched activities; |ΔC|/C: mean "
        "absolute relative CP-SAT makespan error over valid answers (equal: makespan equal to "
        "the true one). Rounds: repair rounds per session (unchanged: rounds whose answer "
        "repeated the previous one).",
        "",
    ]
    for backend in analysis.backends:
        lines += [
            f"## {backend} (`{analysis.models.get(backend, '?')}`)",
            "",
            "| Style | Condition | n | Valid [%] | Exact [%] | Team exact [%] | Act. recall | "
            "Act. precision | Edge P | Edge R | Edge F1 | Duration acc. | Crew acc. | Team acc. | "
            "\\|ΔC\\|/C (n, equal) | Rounds (unchanged) | Calls | Prompt tok. | "
            "Completion tok. | Latency [s] |",
            "| --- | --- | " + " | ".join(["---:"] * 18) + " |",
        ]
        for style in [*analysis.styles, None]:
            for condition in ("single_shot", "repair"):
                cell = analysis.cell(backend, style, condition)
                if cell is None:
                    continue
                lines.append(
                    f"| {_style_label(style)} | {CONDITION_LABELS[condition]} | {cell.n} | "
                    f"{_pct(cell, cell.valid)} | {_pct(cell, cell.exact)} | "
                    f"{_pct(cell, cell.team_exact)} | {_num(cell.activity_recall)} | "
                    f"{_num(cell.activity_precision)} | {_num(cell.edge_precision)} | "
                    f"{_num(cell.edge_recall)} | {_num(cell.edge_f1)} | "
                    f"{_num(cell.duration_accuracy)} | {_num(cell.crew_accuracy)} | "
                    f"{_num(cell.team_accuracy)} | {_num(cell.makespan_abs_error, 4)} "
                    f"({cell.makespan_n}, {cell.makespan_equal}) | {_num(cell.rounds_used, 2)} "
                    f"({_num(cell.unchanged_rounds, 2)}) | "
                    f"{_num(cell.calls, 2)} | {_num(cell.prompt_tokens, 0)} | "
                    f"{_num(cell.completion_tokens, 0)} | {_num(cell.latency_s, 1)} |"
                )
        lines += [
            "",
            "Paired differences repair - single shot (sessions repaired: with at least one "
            "repair round):",
            "",
            "| Style | Sessions (repaired) | Δ valid [pp] | Δ exact [pp] | Δ act. recall | "
            "Δ edge F1 | Δ duration acc. | Δ crew acc. |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for style in [*analysis.styles, None]:
            d = analysis.differences.get((backend, style))
            if d is None:
                continue
            lines.append(
                f"| {_style_label(style)} | {d.n} ({d.repaired}) | {_signed(d.valid, 1)} | "
                f"{_signed(d.exact, 1)} | {_signed(d.activity_recall, 3)} | "
                f"{_signed(d.edge_f1, 3)} | {_signed(d.duration_accuracy, 3)} | "
                f"{_signed(d.crew_accuracy, 3)} |"
            )
        lines += [
            "",
            "Answers after each round (a session that stopped keeps its last answer):",
            "",
        ]
        steps = sorted(
            {s for (b, _), v in analysis.by_round.items() if b == backend for s, *_ in v}
        )
        lines.append(
            "| Style | " + " | ".join(f"valid r{s} [%] | edge F1 r{s}" for s in steps) + " |"
        )
        lines.append("| --- | " + " | ".join(["---:", "---:"] * len(steps)) + " |")
        for style in analysis.styles:
            values = analysis.by_round.get((backend, style), [])
            parts = [f"{100 * valid / n:.1f} | {_num(f1)}" for _, valid, n, f1 in values]
            lines.append(f"| {style} | " + " | ".join(parts) + " |")
        lines += ["", "Issues of the final answers (sessions with the kind, total issues):", ""]
        lines += _issue_table(rows, backend, analysis.styles)
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def _issue_table(rows: Sequence[ResultRow], backend: str, styles: Sequence[str]) -> list[str]:
    counts: dict[tuple[str, str], dict[str, tuple[int, int]]] = {}
    kinds: set[str] = set()
    for row in rows:
        if row.backend != backend or not row.issues:
            continue
        cell = counts.setdefault((row.style, row.condition), {})
        for part in row.issues.split(";"):
            kind, _, number = part.partition(":")
            sessions, total = cell.get(kind, (0, 0))
            cell[kind] = (sessions + 1, total + int(number))
            kinds.add(kind)
    if not kinds:
        return ["No final answer has issues."]
    ordered = sorted(kinds)
    lines = [
        "| Style | Condition | " + " | ".join(ordered) + " |",
        "| --- | --- | " + " | ".join(["---:"] * len(ordered)) + " |",
    ]
    for style in styles:
        for condition in ("single_shot", "repair"):
            cell = counts.get((style, condition), {})
            values = [f"{cell[k][0]} ({cell[k][1]})" if k in cell else "0" for k in ordered]
            lines.append(
                f"| {style} | {CONDITION_LABELS[condition]} | " + " | ".join(values) + " |"
            )
    return lines


def _tex(value: float, digits: int) -> str:
    return "--" if math.isnan(value) else f"{value:.{digits}f}"


def _tex_ci(estimate: Estimate, digits: int) -> str:
    if math.isnan(estimate.low):
        return ""
    return rf"\tiny[{estimate.low:+.{digits}f}, {estimate.high:+.{digits}f}]"


def latex_table(run_id: str, analysis: Analysis) -> str:
    """Booktabs tabular per backend and style: both conditions, then the paired difference
    with its bootstrap interval (shares in percentage points)."""
    lines = [
        f"% Generated by sentinel.experiments.wbs_summary from run {run_id}; do not edit.",
        "% Valid, Exact: share of sessions in %; Recall: activity recall; Edge F1 on matched "
        "activities; Dur., Crew: exact accuracy pooled over matched activities;",
        "% |dC|/C: mean absolute relative CP-SAT makespan error over valid answers; Tok.: tokens "
        "per session (prompt + completion). Third rows: repair - single shot,",
        "% 95 % cluster bootstrap intervals over instances. Typeset with \\small.",
        r"{\setlength{\tabcolsep}{3pt}%",
        r"\begin{tabular}{@{}llrrrrrrrr@{}}",
        r"\toprule",
        r"Style & Condition & Valid & Exact & Recall & Edge $F_1$ & Dur. & Crew & "
        r"$|\Delta C|/C$ & Tok. \\",
    ]
    for backend in analysis.backends:
        lines += [
            r"\midrule",
            rf"\multicolumn{{10}}{{@{{}}l}}{{\textit{{{_latex(backend)}: "
            rf"\texttt{{{_latex(analysis.models.get(backend, ''))}}}}}}} \\",
        ]
        for style in [*analysis.styles, None]:
            for condition in ("single_shot", "repair"):
                cell = analysis.cell(backend, style, condition)
                if cell is None:
                    continue
                label = _style_label(style) if condition == "single_shot" else ""
                tokens = cell.prompt_tokens + cell.completion_tokens
                lines.append(
                    f"{label} & {CONDITION_LABELS[condition]} & "
                    f"{100 * cell.share(cell.valid):.1f} & {100 * cell.share(cell.exact):.1f} & "
                    f"{_tex(cell.activity_recall, 3)} & {_tex(cell.edge_f1, 3)} & "
                    f"{_tex(cell.duration_accuracy, 3)} & {_tex(cell.crew_accuracy, 3)} & "
                    f"{_tex(cell.makespan_abs_error, 3)} & {_tex(tokens, 0)} " + r"\\"
                )
            d = analysis.differences.get((backend, style))
            if d is not None:
                lines.append(
                    rf" & $\Delta$ & {_tex_ci(d.valid, 1)} & {_tex_ci(d.exact, 1)} & "
                    rf"{_tex_ci(d.activity_recall, 3)} & {_tex_ci(d.edge_f1, 3)} & "
                    rf"{_tex_ci(d.duration_accuracy, 3)} & {_tex_ci(d.crew_accuracy, 3)} & & \\"
                )
    lines += [r"\bottomrule", r"\end{tabular}}"]
    return "\n".join(lines) + "\n"


def _latex(text: str) -> str:
    for char in "\\&%$#_{}":
        text = text.replace(char, f"\\{char}" if char != "\\" else r"\textbackslash{}")
    return text


def _axes_style(ax: Axes) -> None:
    ax.grid(True, axis="both", color=_GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", which="both", labelsize=7, colors=_INK_2, length=2.5)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(_AXIS)


def write_figure(path_stem: Path, analysis: Analysis) -> list[str]:
    """Share of valid answers (95 % Wilson bars) and mean edge F1 after each round, one line per
    backend (colour) and style (line and marker); round 0 is the single-shot answer."""
    fig = Figure(figsize=(6.4, 2.5), layout="constrained")
    left, right = fig.subplots(1, 2, sharex=True)
    steps: set[int] = set()
    series = [
        (b, backend, style)
        for b, backend in enumerate(analysis.backends)
        for style in analysis.styles
    ]
    for k, (b, backend, style) in enumerate(series):
        values = analysis.by_round.get((backend, style), [])
        if values:
            line, marker = _STYLE_LINES.get(style, ("-", "o"))
            label = f"{backend}, {style}"
            steps.update(step for step, *_ in values)
            # Dodged sideways so that the error bars of equal shares stay apart.
            xs = [step + (k - (len(series) - 1) / 2) * 0.05 for step, *_ in values]
            shares = [100 * valid / n for _, valid, n, _ in values]
            bounds = [wilson_interval(valid, n) for _, valid, n, _ in values]
            low = [max(0.0, s - 100 * lo) for s, (lo, _) in zip(shares, bounds, strict=True)]
            high = [max(0.0, 100 * hi - s) for s, (_, hi) in zip(shares, bounds, strict=True)]
            style_kw = {"color": _COLORS[b % len(_COLORS)], "linestyle": line, "marker": marker}
            left.errorbar(
                xs,
                shares,
                yerr=[low, high],
                markersize=4,
                linewidth=1.4,
                elinewidth=0.8,
                capsize=1.5,
                clip_on=False,
                label=label,
                **style_kw,
            )
            f1 = [value for *_, value in values]
            right.plot(xs, f1, markersize=4, linewidth=1.4, clip_on=False, **style_kw)
    ticks = sorted(steps)
    for ax, title, unit in ((left, "Valid answers", "[%]"), (right, "Edge F1 (matched)", "")):
        ax.set_xticks(ticks, [f"{s}" for s in ticks])
        ax.set_xlabel("Repair rounds (0 = single shot)", fontsize=8, color=_INK)
        ax.set_title(title, fontsize=9, color=_INK)
        if unit:
            ax.set_ylabel(f"Share {unit}", fontsize=8, color=_INK)
        _axes_style(ax)
    left.set_ylim(0, 100)
    right.set_ylim(0, 1)
    handles, labels = left.get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="outside upper center",
        ncols=min(4, len(labels)),
        frameon=False,
        fontsize=7,
        labelcolor=_INK,
    )
    # Fixed metadata keeps repeated renders of the same results byte-identical.
    fig.savefig(path_stem.with_suffix(".pdf"), metadata={"CreationDate": None})
    fig.savefig(path_stem.with_suffix(".png"), dpi=200, metadata={"Software": None})
    return [f"{path_stem.name}.pdf", f"{path_stem.name}.png"]


def write_summaries(
    run_dir: Path,
    run_id: str,
    config: WbsStudyConfig,
    *,
    read: Sequence[Path] = (),
    settings_source: str = "run config",
    pinned: Mapping[str, Any] | None = None,
) -> list[str]:
    """Generate summary.md, the LaTeX tables, the figure and summary_manifest.json from the
    run's results.csv and rounds.csv, with the error analysis of the sessions replayed from the
    run's bundle when it has one (WP7); `read` lists further files read to obtain `config`;
    `pinned` is a recorded summary manifest whose provenance is kept (`summary_provenance`)."""
    # Imported here: the error analysis replays sessions with the study's code, which imports
    # this module.
    from sentinel.experiments import wbs_errors, wbs_study

    git, generated = summary_provenance(GIT_EXCLUDE, pinned)
    rows = read_results(run_dir / RESULTS_FILE)
    rounds = read_rounds(run_dir / ROUNDS_FILE)
    analysis = Analysis(rows, rounds, config)
    settings = config.summary
    texts = {
        SUMMARY_FILE: summary_markdown(run_id, analysis, rows, git=git),
        f"{settings.table}.tex": latex_table(run_id, analysis),
    }
    inputs = [run_dir / RESULTS_FILE, run_dir / ROUNDS_FILE]
    bundle = run_dir / wbs_study.BUNDLE_FILE
    if bundle.is_file():
        errors = wbs_errors.replay_errors(run_dir, config)
        section = wbs_errors.summary_section(errors, config, bundle.name)
        texts[SUMMARY_FILE] += "\n" + "\n".join(section)
        texts[f"{wbs_errors.TABLE}.tex"] = wbs_errors.latex_table(run_id, errors, config)
        inputs.append(bundle)
    for name, text in texts.items():
        (run_dir / name).write_text(text, encoding="utf-8")
    files = [*texts, *write_figure(run_dir / settings.figure, analysis)]
    inputs += read
    write_json(
        run_dir / SUMMARY_MANIFEST_FILE,
        {
            "run_id": run_id,
            "generator": "sentinel.experiments.wbs_summary",
            "generated_utc": generated,
            "git_commit": git["commit"],
            "git_dirty": git["dirty"],
            "git_dirty_ignores": list(GIT_EXCLUDE),
            "summary_settings_source": settings_source,
            "summary_settings": settings.model_dump(mode="json"),
            "inputs": [_file_record(path, run_dir) for path in inputs],
            "outputs": files,
        },
    )
    return [*files, SUMMARY_MANIFEST_FILE]


def _file_record(path: Path, run_dir: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    shown = path.name if path.parent == run_dir else path.as_posix()
    return {"path": shown, "bytes": path.stat().st_size, "sha256": digest}


def run_config(manifest: Mapping[str, Any]) -> tuple[WbsStudyConfig, Path | None]:
    """The config of a run from its manifest, with the [summary] settings of its config file
    if that file still describes the same run (ADR-0011); returns that file or None."""
    recorded: dict[str, Any] = manifest["config"]
    name = manifest.get("config_path")
    path = Path(name) if name else None
    if path is not None and path.is_file():
        current = load_toml(path)
        if _run_part(current) == _run_part(recorded):
            merged = {**recorded, "summary": current.get("summary", {})}
            return WbsStudyConfig.model_validate(merged), path
    return WbsStudyConfig.model_validate(recorded), None


def _run_part(config: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in config.items() if key != "summary"}


def regenerate(run_dir: Path, *, pinned: Mapping[str, Any] | None = None) -> list[str]:
    """Regenerate the summaries of a run directory from its manifest and results files (with
    `pinned`, the provenance of that recorded summary manifest)."""
    manifest_path = run_dir / MANIFEST_FILE
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    config, source = run_config(manifest)
    return write_summaries(
        run_dir,
        manifest["run_id"],
        config,
        read=[manifest_path, *([] if source is None else [source])],
        settings_source=MANIFEST_FILE if source is None else source.as_posix(),
        pinned=pinned,
    )
