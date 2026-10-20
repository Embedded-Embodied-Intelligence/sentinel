"""Summaries of a simulation study run, generated from its results file only (no hand edits).

Writes `summary.md` (all statistics), `table_wp2.tex` (booktabs tabular) and
`fig_wp2_ontime.pdf` / `.png` (P(on time) against lambda_A, one line per delta_D, one panel
per set and E[L]). To regenerate them for an existing run:

    uv run python -m sentinel.experiments.simulation_summary results/wp2/<run_id>
"""

import argparse
import csv
import gzip
import json
import math
import statistics
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from matplotlib.figure import Figure

from sentinel.experiments.simulation_config import (
    DURATIONS_ONLY,
    Scenario,
    StudyConfig,
    met_column,
)

SUMMARY_FILE = "summary.md"
TABLE_FILE = "table_wp2.tex"
FIGURE_STEM = "fig_wp2_ontime"
REFERENCE_LABELS = {"opt": "optimum", "hrs": "best known", "lb": "lower bound"}
Z_95 = 1.959963984540054  # standard normal quantile of 0.975

# Blue ramp, steps 250..700 (dataviz reference palette): delta_D is ordinal, so its lines take
# monotone lightness steps of one hue; markers repeat the identity for print and CVD.
_RAMP = (
    "#86b6ef",
    "#6da7ec",
    "#5598e7",
    "#3987e5",
    "#2a78d6",
    "#256abf",
    "#1c5cab",
    "#184f95",
    "#104281",
    "#0d366b",
)
_MARKERS = ("o", "s", "^", "D", "v", "P")
_GRID, _INK, _SPINE = "#dddddd", "#333333", "#999999"


@dataclass(frozen=True)
class ResultRow:
    """The results fields the summaries use; `met` follows the config's deltas."""

    set_name: str
    instance: str
    scenario: str
    baseline_makespan: int
    c_star: int
    ratio_c_star: float
    met: tuple[bool, ...]
    cost_ratio: float
    n_absence: int
    n_work_increase: int
    n_new_activity: int
    n_epochs: int
    truncated: bool


@dataclass(frozen=True)
class Cell:
    """Aggregates of one (set, scenario) cell over all its runs."""

    n: int
    mean_ratio: float
    on_time: tuple[int, ...]
    mean_cost_ratio: float
    mean_absences: float
    mean_work_increases: float
    mean_new_activities: float
    mean_epochs: float
    truncated: int

    def share(self, i: int) -> float:
        """Share of runs on time for the i-th delta_D."""
        return self.on_time[i] / self.n

    def interval(self, i: int) -> tuple[float, float]:
        """95 % Wilson interval of the i-th on-time share."""
        return wilson_interval(self.on_time[i], self.n)


def wilson_interval(successes: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score interval of a binomial proportion (Wilson 1927)."""
    if n <= 0 or not 0 <= successes <= n:
        raise ValueError(f"need 0 <= successes <= n and n > 0, got {successes} of {n}")
    p = successes / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return max(0.0, center - half), min(1.0, center + half)


@contextmanager
def _open_text(path: Path) -> Iterator[TextIO]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
            yield handle
    else:
        with path.open(newline="", encoding="utf-8") as handle:
            yield handle


def read_results(path: Path, deltas: Sequence[float]) -> list[ResultRow]:
    """Parse results.csv or results.csv.gz."""
    with _open_text(path) as handle:
        return [
            ResultRow(
                set_name=record["set"],
                instance=record["instance"],
                scenario=record["scenario"],
                baseline_makespan=int(record["baseline_makespan"]),
                c_star=int(record["c_star"]),
                ratio_c_star=float(record["ratio_c_star"]),
                met=tuple(record[met_column(delta)] == "True" for delta in deltas),
                cost_ratio=float(record["cost_ratio"]),
                n_absence=int(record["n_absence"]),
                n_work_increase=int(record["n_work_increase"]),
                n_new_activity=int(record["n_new_activity"]),
                n_epochs=int(record["n_epochs"]),
                truncated=record["truncated"] == "True",
            )
            for record in csv.DictReader(handle)
        ]


def aggregate(rows: Sequence[ResultRow], n_deltas: int) -> Cell | None:
    """Means and on-time counts of one cell; None for a cell without runs."""
    if not rows:
        return None
    return Cell(
        n=len(rows),
        mean_ratio=statistics.fmean(r.ratio_c_star for r in rows),
        on_time=tuple(sum(r.met[i] for r in rows) for i in range(n_deltas)),
        mean_cost_ratio=statistics.fmean(r.cost_ratio for r in rows),
        mean_absences=statistics.fmean(r.n_absence for r in rows),
        mean_work_increases=statistics.fmean(r.n_work_increase for r in rows),
        mean_new_activities=statistics.fmean(r.n_new_activity for r in rows),
        mean_epochs=statistics.fmean(r.n_epochs for r in rows),
        truncated=sum(r.truncated for r in rows),
    )


def cell_stats(rows: Sequence[ResultRow], config: StudyConfig) -> dict[tuple[str, str], Cell]:
    """Cells of every (set, scenario) pair of the config that has runs."""
    groups: dict[tuple[str, str], list[ResultRow]] = {}
    for row in rows:
        groups.setdefault((row.set_name, row.scenario), []).append(row)
    stats = {}
    for s in config.sets:
        for scenario in config.scenarios.expand():
            cell = aggregate(groups.get((s.name, scenario.name), []), len(config.deltas))
            if cell is not None:
                stats[(s.name, scenario.name)] = cell
    return stats


def plan_line(rows: Sequence[ResultRow], set_name: str, baseline: str) -> str:
    """Baseline plan quality of a set: mean plan / C* over its instances and plans at C*."""
    plans = {r.instance: (r.baseline_makespan, r.c_star) for r in rows if r.set_name == set_name}
    if not plans:
        return "No runs."
    ratios = [plan / c_star for plan, c_star in plans.values()]
    at_c_star = sum(plan == c_star for plan, c_star in plans.values())
    return (
        f"Baseline plans (`{baseline}`): {len(plans)} instances; plan / C* mean "
        f"{statistics.fmean(ratios):.4f}, max {max(ratios):.4f}; {at_c_star} at C* "
        f"({100 * at_c_star / len(plans):.1f}%)."
    )


def _shown_mean_absence(scenario: Scenario) -> float | None:
    """E[L] as shown in tables: none when nobody can be absent (it has no effect there)."""
    return scenario.mean_absence if scenario.lambda_a > 0 else None


def summary_markdown(
    run_id: str,
    config: StudyConfig,
    stats: dict[tuple[str, str], Cell],
    rows: Sequence[ResultRow],
    results_file: str,
) -> str:
    """Human-readable tables: one per set, one row per scenario."""
    grid = config.scenarios
    lines = [
        f"# {config.name}: run {run_id}",
        "",
        f"Generated from `{results_file}` by `sentinel.experiments.simulation_summary`; "
        "do not edit.",
        "",
        f"- NoReaction on `{config.baseline}` baseline plans; {config.replications} replications "
        "per instance, seeds shared by all scenarios (common random numbers).",
        f"- Scenarios other than durations only use λ_S = {grid.lambda_s:g} and "
        f"λ_N = {grid.lambda_n:g}; E[L] has no effect at λ_A = 0.",
        "- C / C*: realised makespan over the PSPLIB reference makespan C*.",
        "- On time for δ: C ≤ D = ceil((1 + δ) C*) (spec section 1.2); truncated runs are late. "
        "95 % Wilson intervals over all runs of a cell understate the uncertainty across "
        "instances, because runs of one instance are not independent.",
        f"- Cost / B with β = {config.beta:g}. Events (absences, D2 work increases, D3 new "
        "activities) and decision epochs are means per run.",
    ]
    on_time_headers = " | ".join(f"On time δ={delta:g}" for delta in config.deltas)
    for s in config.sets:
        lines += [
            "",
            f"## {s.name.upper()} (C*: {REFERENCE_LABELS[s.reference]}, `{s.reference}`)",
            "",
            plan_line(rows, s.name, config.baseline),
            "",
            f"| Scenario | λ_A | E[L] | Runs | C / C* | {on_time_headers} | Cost / B | Absences "
            "| D2 | D3 | Epochs | Truncated |",
            "| --- | ---: | ---: | ---: | ---: | "
            + "---: | " * len(config.deltas)
            + "---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for scenario in grid.expand():
            cell = stats.get((s.name, scenario.name))
            if cell is None:
                continue
            shares = " | ".join(_share_markdown(cell, i) for i in range(len(config.deltas)))
            durations_only = scenario.name == DURATIONS_ONLY
            lambda_a = "--" if durations_only else f"{scenario.lambda_a:g}"
            lines.append(
                f"| {scenario.name} | {lambda_a} | {_num(_shown_mean_absence(scenario), 'g')} "
                f"| {cell.n} | {cell.mean_ratio:.3f} | {shares} | {cell.mean_cost_ratio:.3f} "
                f"| {cell.mean_absences:.1f} | {cell.mean_work_increases:.2f} "
                f"| {cell.mean_new_activities:.2f} | {cell.mean_epochs:.1f} | {cell.truncated} |"
            )
    return "\n".join(lines) + "\n"


def latex_table(run_id: str, config: StudyConfig, stats: dict[tuple[str, str], Cell]) -> str:
    """Booktabs tabular: per set and scenario C/C*, P(on time) per delta_D, cost/B, events."""
    n_deltas = len(config.deltas)
    lines = [
        f"% Generated by sentinel.experiments.simulation_summary from the results of run {run_id};",
        "% do not edit. Means per run of NoReaction; P(on time) in % with 95 % Wilson intervals;",
        "% events: absences (D1) / work increases (D2) / new activities (D3) per run.",
        rf"\begin{{tabular}}{{lll{'r' * (n_deltas + 3)}}}",
        r"\toprule",
        r"Set & $\lambda_A$ & $E[L]$ & $C/C^*$ & "
        rf"\multicolumn{{{n_deltas}}}{{c}}{{P(on time) [\%]}} & cost$/B$ & events \\",
        rf"\cmidrule(lr){{5-{4 + n_deltas}}}",
        " & & & & "
        + " & ".join(rf"$\delta_D = {delta:g}$" for delta in config.deltas)
        + r" & & D1/D2/D3 \\",
        r"\midrule",
    ]
    for index, s in enumerate(config.sets):
        if index:
            lines.append(r"\midrule")
        first = True
        for scenario in config.scenarios.expand():
            cell = stats.get((s.name, scenario.name))
            if cell is None:
                continue
            set_cell = s.name.upper() if first else ""
            first = False
            if scenario.name == DURATIONS_ONLY:
                scenario_cells = r"\multicolumn{2}{l}{durations only}"
            else:
                mean_absence = _num(_shown_mean_absence(scenario), "g")
                scenario_cells = f"{scenario.lambda_a:g} & {mean_absence}"
            shares = " & ".join(_share_latex(cell, i) for i in range(n_deltas))
            events = (
                f"{cell.mean_absences:.1f}/{cell.mean_work_increases:.1f}/"
                f"{cell.mean_new_activities:.1f}"
            )
            lines.append(
                f"{set_cell} & {scenario_cells} & {cell.mean_ratio:.3f} & {shares} & "
                f"{cell.mean_cost_ratio:.3f} & {events} " + r"\\"
            )
    lines += [r"\bottomrule", r"\end{tabular}"]
    return "\n".join(lines) + "\n"


def write_figure(path_stem: Path, config: StudyConfig, stats: dict[tuple[str, str], Cell]) -> None:
    """P(on time) against 100 lambda_A, one line per delta_D with its Wilson band, one panel per
    set (rows) and E[L] (columns); the lambda_A = 0 point appears in every panel. PDF and PNG."""
    mean_absences = sorted(config.scenarios.mean_absence)
    colors = _ordinal_colors(len(config.deltas))
    scenarios = [s for s in config.scenarios.expand() if s.name != DURATIONS_ONLY]
    fig = Figure(figsize=(3.3 * len(mean_absences), 2.5 * len(config.sets)), layout="constrained")
    axes = fig.subplots(len(config.sets), len(mean_absences), squeeze=False, sharey=True)
    for row, s in enumerate(config.sets):
        for col, mean_absence in enumerate(mean_absences):
            ax = axes[row][col]
            points = [
                (100 * sc.lambda_a, stats[(s.name, sc.name)])
                for sc in scenarios
                if (sc.lambda_a == 0 or sc.mean_absence == mean_absence)
                and (s.name, sc.name) in stats
            ]
            xs = [x for x, _ in points]
            for i, delta in enumerate(config.deltas):
                lows = [100 * cell.interval(i)[0] for _, cell in points]
                highs = [100 * cell.interval(i)[1] for _, cell in points]
                ax.fill_between(xs, lows, highs, color=colors[i], alpha=0.18, linewidth=0)
                ax.plot(
                    xs,
                    [100 * cell.share(i) for _, cell in points],
                    color=colors[i],
                    marker=_MARKERS[i % len(_MARKERS)],
                    markersize=4,
                    linewidth=1.4,
                    clip_on=False,  # markers at 0 % and 100 % stay whole
                    label=rf"$\delta_D = {delta:g}$",
                )
            ax.set_title(f"{s.name.upper()}, E[L] = {mean_absence:g}", fontsize=9, color=_INK)
            ax.set_xticks(xs, [f"{x:g}" for x in xs])
            ax.set_ylim(0, 100)
            ax.set_xlabel(r"$\lambda_A$ [% per worker-day]", fontsize=8, color=_INK)
            if col == 0:
                ax.set_ylabel("P(on time) [%]", fontsize=8, color=_INK)
            ax.yaxis.grid(True, color=_GRID, linewidth=0.6)
            ax.set_axisbelow(True)
            ax.tick_params(axis="both", labelsize=7, colors=_INK)
            for side in ("top", "right"):
                ax.spines[side].set_visible(False)
            for side in ("left", "bottom"):
                ax.spines[side].set_color(_SPINE)
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(
        handles, labels, loc="outside upper center", ncols=len(labels), frameon=False, fontsize=8
    )
    # Fixed metadata keeps repeated renders of the same results byte-identical.
    fig.savefig(path_stem.with_suffix(".pdf"), metadata={"CreationDate": None})
    fig.savefig(path_stem.with_suffix(".png"), dpi=200, metadata={"Software": None})


def write_summaries(
    run_dir: Path, run_id: str, config: StudyConfig, results_file: str
) -> list[str]:
    """Generate summary.md, the LaTeX table and the figure from the run's results file."""
    rows = read_results(run_dir / results_file, config.deltas)
    stats = cell_stats(rows, config)
    summary = summary_markdown(run_id, config, stats, rows, results_file)
    (run_dir / SUMMARY_FILE).write_text(summary, encoding="utf-8")
    (run_dir / TABLE_FILE).write_text(latex_table(run_id, config, stats), encoding="utf-8")
    write_figure(run_dir / FIGURE_STEM, config, stats)
    return [SUMMARY_FILE, TABLE_FILE, f"{FIGURE_STEM}.pdf", f"{FIGURE_STEM}.png"]


def _ordinal_colors(n: int) -> list[str]:
    """n monotone steps of the blue ramp from step 300 to 700 (one middle step for n = 1)."""
    if n == 1:
        return [_RAMP[5]]
    return [_RAMP[1 + round(i * (len(_RAMP) - 2) / (n - 1))] for i in range(n)]


def _share_markdown(cell: Cell, i: int) -> str:
    low, high = cell.interval(i)
    return f"{100 * cell.share(i):.1f}% [{100 * low:.1f}, {100 * high:.1f}]"


def _share_latex(cell: Cell, i: int) -> str:
    low, high = cell.interval(i)
    return rf"{100 * cell.share(i):.1f}\,{{\scriptsize[{100 * low:.1f}, {100 * high:.1f}]}}"


def _num(value: float | None, spec: str) -> str:
    return "--" if value is None else format(value, spec)


def main(argv: Sequence[str] | None = None) -> int:
    """Regenerate the summaries of an existing run directory from its manifest and results."""
    parser = argparse.ArgumentParser(
        prog="python -m sentinel.experiments.simulation_summary",
        description="Regenerate summary.md, the LaTeX table and the figure of a study run.",
    )
    parser.add_argument("run_dir", type=Path, help="results/<wp>/<run_id> with manifest.json")
    args = parser.parse_args(argv)
    run_dir: Path = args.run_dir
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    config = StudyConfig.model_validate(manifest["config"])
    for name in write_summaries(run_dir, manifest["run_id"], config, manifest["results_file"]):
        print(run_dir / name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
