"""Summaries of an RCPSP benchmark run, generated from its results.csv only (no hand edits).

Writes `summary.md` (all statistics), `table_rq2.tex` (booktabs tabular) and
`fig_rq2_deviation.pdf` / `.png` (box plots of dev_ref per method, one panel per set).
To regenerate them for an existing run:

    uv run python -m sentinel.experiments.rcpsp_summary results/wp1/<run_id>
"""

import argparse
import csv
import json
import statistics
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from matplotlib.figure import Figure

from sentinel.experiments.rcpsp_config import BenchmarkConfig

SUMMARY_FILE = "summary.md"
TABLE_FILE = "table_rq2.tex"
FIGURE_STEM = "fig_rq2_deviation"
REFERENCE_LABELS = {"opt": "optimum", "hrs": "best known", "lb": "lower bound"}

# One hue for every box (methods are named on the axis), recessive grid and spines.
_BOX_FILL, _BOX_EDGE, _MEDIAN, _GRID, _INK = "#cddcea", "#3e5c76", "#1b3349", "#dddddd", "#333333"


@dataclass(frozen=True)
class ResultRow:
    """The results.csv fields the summaries use."""

    set_name: str
    method: str
    makespan: int | None
    dev_ref_pct: float | None
    dev_lb0_pct: float | None
    matches_ref: bool | None
    status: str
    runtime_s: float


@dataclass(frozen=True)
class Stats:
    """Aggregates of one (set, method) cell; means over the instances with a schedule."""

    n: int
    n_solved: int
    mean_dev_ref: float | None
    mean_dev_lb0: float | None
    matches: int
    below_ref: int
    mean_runtime_s: float | None
    max_runtime_s: float | None
    statuses: dict[str, int]


def read_results(path: Path) -> list[ResultRow]:
    """Parse results.csv; empty cells become None."""
    with path.open(newline="", encoding="utf-8") as handle:
        return [
            ResultRow(
                set_name=record["set"],
                method=record["method"],
                makespan=int(record["makespan"]) if record["makespan"] else None,
                dev_ref_pct=float(record["dev_ref_pct"]) if record["dev_ref_pct"] else None,
                dev_lb0_pct=float(record["dev_lb0_pct"]) if record["dev_lb0_pct"] else None,
                matches_ref=record["matches_ref"] == "True" if record["matches_ref"] else None,
                status=record["status"],
                runtime_s=float(record["runtime_s"]),
            )
            for record in csv.DictReader(handle)
        ]


def aggregate(rows: Sequence[ResultRow]) -> Stats:
    """Counts, means and maxima of one (set, method) cell."""
    dev_ref = [r.dev_ref_pct for r in rows if r.dev_ref_pct is not None]
    dev_lb0 = [r.dev_lb0_pct for r in rows if r.dev_lb0_pct is not None]
    runtimes = [r.runtime_s for r in rows]
    return Stats(
        n=len(rows),
        n_solved=sum(r.makespan is not None for r in rows),
        mean_dev_ref=statistics.fmean(dev_ref) if dev_ref else None,
        mean_dev_lb0=statistics.fmean(dev_lb0) if dev_lb0 else None,
        matches=sum(r.matches_ref is True for r in rows),
        below_ref=sum(d < 0 for d in dev_ref),
        mean_runtime_s=statistics.fmean(runtimes) if runtimes else None,
        max_runtime_s=max(runtimes) if runtimes else None,
        statuses=dict(sorted(Counter(r.status for r in rows).items())),
    )


def cell_stats(rows: Sequence[ResultRow], config: BenchmarkConfig) -> dict[tuple[str, str], Stats]:
    """Stats for every (set, method) pair of the config."""
    return {
        (s.name, m.name): aggregate(
            [r for r in rows if r.set_name == s.name and r.method == m.name]
        )
        for s in config.sets
        for m in config.methods
    }


def summary_markdown(
    run_id: str, config: BenchmarkConfig, stats: dict[tuple[str, str], Stats]
) -> str:
    """Human-readable tables: one per set, one row per method."""
    lines = [
        f"# {config.name}: run {run_id}",
        "",
        "Generated from `results.csv` by `sentinel.experiments.rcpsp_summary`; do not edit.",
        "dev_ref = 100 (C - C_ref) / C_ref and dev_lb0 = 100 (C - LB0) / LB0 in % (spec section",
        "1.5), averaged over the instances with a schedule; matches: C = C_ref; below: C < C_ref.",
    ]
    for s in config.sets:
        lines += [
            "",
            f"## {s.name.upper()} (reference: {REFERENCE_LABELS[s.reference]}, `{s.reference}`)",
            "",
            "| Method | n | with schedule | mean dev_ref % | matches | below ref "
            "| mean dev_lb0 % | mean runtime s | max runtime s | statuses |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
        for m in config.methods:
            st = stats[(s.name, m.name)]
            statuses = ", ".join(f"{name} {count}" for name, count in st.statuses.items())
            share = f"{100 * st.matches / st.n:.1f}%" if st.n else "--"
            lines.append(
                f"| {m.label} | {st.n} | {st.n_solved} | {_num(st.mean_dev_ref, 2)} "
                f"| {st.matches} ({share}) | {st.below_ref} | {_num(st.mean_dev_lb0, 2)} "
                f"| {_num(st.mean_runtime_s, 4)} | {_num(st.max_runtime_s, 4)} | {statuses} |"
            )
    return "\n".join(lines) + "\n"


def latex_table(run_id: str, config: BenchmarkConfig, stats: dict[tuple[str, str], Stats]) -> str:
    """Booktabs tabular: rows = methods; per set mean dev_ref, [mean dev_lb0], match share, time."""
    groups = [
        (s, ["ref", "lb0", "match", "time"] if s.dev_lb0 else ["ref", "match", "time"])
        for s in config.sets
    ]
    headers = {
        "ref": r"$\Delta_{\mathrm{ref}}$ [\%]",
        "lb0": r"$\Delta_{\mathrm{LB0}}$ [\%]",
        "match": r"match [\%]",
        "time": r"$t$ [s]",
    }
    n_cols = sum(len(cols) for _, cols in groups)
    top, rules, first = [""], [], 2
    for s, cols in groups:
        title = f"{s.name.upper()} (ref.\\ {REFERENCE_LABELS[s.reference]})"
        top.append(rf"\multicolumn{{{len(cols)}}}{{c}}{{{title}}}")
        rules.append(rf"\cmidrule(lr){{{first}-{first + len(cols) - 1}}}")
        first += len(cols)
    lines = [
        f"% Generated by sentinel.experiments.rcpsp_summary from results.csv of run {run_id};",
        "% do not edit. Means per instance: Delta = deviation from the reference or LB0,",
        "% match = share of instances with C = C_ref, t = runtime per instance.",
        rf"\begin{{tabular}}{{l{'r' * n_cols}}}",
        r"\toprule",
        " & ".join(top) + r" \\",
        "".join(rules),
        " & ".join(["Method"] + [headers[c] for _, cols in groups for c in cols]) + r" \\",
        r"\midrule",
    ]
    for m in config.methods:
        cells = [_latex_escape(m.label)]
        for s, cols in groups:
            st = stats[(s.name, m.name)]
            values = {
                "ref": _num(st.mean_dev_ref, 2),
                "lb0": _num(st.mean_dev_lb0, 2),
                "match": f"{100 * st.matches / st.n:.1f}" if st.n else "--",
                "time": _seconds(st.mean_runtime_s),
            }
            cells += [values[c] for c in cols]
        lines.append(" & ".join(cells) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    return "\n".join(lines) + "\n"


def write_figure(path_stem: Path, config: BenchmarkConfig, rows: Sequence[ResultRow]) -> None:
    """Box plots of dev_ref per method (mean as a diamond), one panel per set; PDF and PNG."""
    labels = [m.label for m in config.methods]
    fig = Figure(figsize=(3.6 * len(config.sets), 3.4), layout="constrained")
    axes = fig.subplots(1, len(config.sets), squeeze=False)[0]
    for ax, s in zip(axes, config.sets, strict=True):
        data = [
            [
                r.dev_ref_pct
                for r in rows
                if r.set_name == s.name and r.method == m.name and r.dev_ref_pct is not None
            ]
            for m in config.methods
        ]
        ax.boxplot(
            data,
            tick_labels=labels,
            widths=0.55,
            patch_artist=True,
            showmeans=True,
            boxprops={"facecolor": _BOX_FILL, "edgecolor": _BOX_EDGE, "linewidth": 0.8},
            medianprops={"color": _MEDIAN, "linewidth": 1.4},
            whiskerprops={"color": _BOX_EDGE, "linewidth": 0.8},
            capprops={"color": _BOX_EDGE, "linewidth": 0.8},
            meanprops={
                "marker": "D",
                "markersize": 3.5,
                "markerfacecolor": "white",
                "markeredgecolor": _MEDIAN,
            },
            flierprops={
                "marker": "o",
                "markersize": 2.5,
                "markerfacecolor": _BOX_EDGE,
                "markeredgecolor": "none",
                "alpha": 0.5,
            },
        )
        ax.axhline(0, color=_BOX_EDGE, linewidth=0.6, linestyle=":", zorder=0)
        ax.set_title(f"{s.name.upper()} (reference: {REFERENCE_LABELS[s.reference]})", fontsize=9)
        ax.set_ylabel("deviation from reference [%]", fontsize=8, color=_INK)
        ax.yaxis.grid(True, color=_GRID, linewidth=0.6)
        ax.set_axisbelow(True)
        ax.tick_params(axis="both", labelsize=7, colors=_INK)
        ax.tick_params(axis="x", labelrotation=35)
        for label in ax.get_xticklabels():
            label.set_horizontalalignment("right")
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color("#999999")
    # Fixed metadata keeps repeated renders of the same results byte-identical.
    fig.savefig(path_stem.with_suffix(".pdf"), metadata={"CreationDate": None})
    fig.savefig(path_stem.with_suffix(".png"), dpi=200, metadata={"Software": None})


def write_summaries(run_dir: Path, run_id: str, config: BenchmarkConfig) -> list[str]:
    """Generate summary.md, the LaTeX table and the figure from `<run_dir>/results.csv`."""
    rows = read_results(run_dir / "results.csv")
    stats = cell_stats(rows, config)
    (run_dir / SUMMARY_FILE).write_text(summary_markdown(run_id, config, stats), encoding="utf-8")
    (run_dir / TABLE_FILE).write_text(latex_table(run_id, config, stats), encoding="utf-8")
    write_figure(run_dir / FIGURE_STEM, config, rows)
    return [SUMMARY_FILE, TABLE_FILE, f"{FIGURE_STEM}.pdf", f"{FIGURE_STEM}.png"]


def _num(value: float | None, digits: int) -> str:
    return "--" if value is None else f"{value:.{digits}f}"


def _seconds(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value:.3f}" if value >= 0.001 else "$<$0.001"


def _latex_escape(text: str) -> str:
    for char in "\\&%$#_{}":
        text = text.replace(char, f"\\{char}")
    return text


def main(argv: Sequence[str] | None = None) -> int:
    """Regenerate the summaries of an existing run directory from its manifest and CSV."""
    parser = argparse.ArgumentParser(
        prog="python -m sentinel.experiments.rcpsp_summary",
        description="Regenerate summary.md, the LaTeX table and the figure of a benchmark run.",
    )
    parser.add_argument("run_dir", type=Path, help="results/<wp>/<run_id> with manifest.json")
    args = parser.parse_args(argv)
    run_dir: Path = args.run_dir
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    config = BenchmarkConfig.model_validate(manifest["config"])
    for name in write_summaries(run_dir, manifest["run_id"], config):
        print(run_dir / name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
