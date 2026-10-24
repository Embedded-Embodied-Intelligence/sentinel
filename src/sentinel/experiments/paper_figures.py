"""Figures of the paper artifacts (WP7, ADR-0020), English and Polish, for print.

One style for all: the categorical palette and ink colours of the WP3-WP5 figures, a marker
and a line style per series and direct labels, so that the figures read in grey scale; every
text at 8 pt at the final width of 12.2 cm (LNCS text width) or 5.8 cm (half). The data are
the cells of the runs' summaries, as printed, or the runs' raw rows read by the summaries' own
readers (RQ1 rounds, RQ2 deviations). PDFs carry no creation date, so the same inputs give the
same bytes.
"""

import csv
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, MaxNLocator

from sentinel.experiments.paper import (
    BACKENDS,
    FORECASTERS,
    MAIN_POLICIES,
    METHODS,
    RQ4_SECTIONS,
    SETS,
    LadderPoint,
    Run,
    _caption,
    _main_table,
)
from sentinel.experiments.rcpsp_summary import read_results as read_rcpsp
from sentinel.experiments.summary_tables import Parts, Table, parse_cell

CM = 1 / 2.54  # inches per centimetre
FULL, HALF = 12.2 * CM, 5.8 * CM
FONT = 8.0
_COLORS = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
_MARKERS = ("o", "s", "^", "D", "v", "P", "X", "*")
_INK, _INK_2, _GRID, _AXIS = "#0b0b0b", "#52514e", "#e1e0d9", "#c3c2b7"
# Policy slots of the WP4/WP5 figures: the five baselines in registry order; the Sentinel
# variants share the next slot and differ by marker.
_POLICY_SLOTS = {name: i for i, name in enumerate(list(MAIN_POLICIES)[:5])}
_SENTINEL_SLOT = 6
_SENTINEL_MARKERS = {"Sentinel": "o", "Sentinel no OT": "H"}

LABELS = {
    "en": {},
    "pl": {
        "Valid answers [%]": "Poprawne odpowiedzi [%]",
        "Edge recall": "Czułość krawędzi",
        "Round": "Runda",
        "structured": "strukturalny",
        "narrative": "narracyjny",
        "Deviation from reference [%]": "Odchylenie od wzorca [%]",
        "J30 (optimum)": "J30 (optimum)",
        "J60 (best known)": "J60 (najlepsze znane)",
        "Checkpoint f": "Punkt kontrolny f",
        "Brier score": "Wynik Briera",
        "base rate": "częstość bazowa",
        "MC, full": "MC, pełna",
        "MC, no future": "MC, bez przyszłości",
        "deterministic": "deterministyczna",
        "Plan changes per run": "Zmiany planu na przebieg",
        "On time [%]": "Terminowo [%]",
        "Sentinel no OT": "Sentinel bez OT",
        "Autonomy level Λ": "Poziom autonomii Λ",
        "Seconds per run": "Sekundy na przebieg",
        "Win rate [%]": "Odsetek wygranych [%]",
        "random": "losowe",
    },
}


def write_figures(
    runs: Mapping[str, Run], point: LadderPoint, language: str, folder: Path
) -> list[Path]:
    """Every figure of the paper in `language` ("en" or "pl") into `folder`."""
    say = _translator(language)
    figures: dict[str, Callable[[], Figure]] = {
        "fig_rq1.pdf": lambda: fig_rq1(runs["rq1"], say, language),
        "fig_rq2.pdf": lambda: fig_rq2(runs["rq2"], say, language),
        "fig_rq3.pdf": lambda: fig_rq3(runs["rq3"], say, language),
        "fig_rq4.pdf": lambda: fig_rq4(runs["rq4_main"], say, language),
        "fig_rq4_autonomy.pdf": lambda: fig_rq4_autonomy(runs, point, say, language),
        "fig_rq5.pdf": lambda: fig_rq5(runs["rq5_proposals"], say, language),
    }
    written = []
    for name, build in figures.items():
        path = folder / name
        # A fixed creation date keeps repeated renders of the same data byte-identical.
        build().savefig(path, metadata={"CreationDate": None})
        written.append(path)
    return written


def _translator(language: str) -> Callable[[str], str]:
    labels = LABELS[language]
    return lambda text: labels.get(text, text)


def _decimal(language: str) -> Callable[[float, int | None], str]:
    def format_tick(value: float, _: int | None = None) -> str:
        text = f"{value:g}"
        return text.replace(".", ",") if language == "pl" else text

    return format_tick


def _number(text: str, language: str) -> str:
    return text.replace(".", ",") if language == "pl" else text


def _style(ax: Axes, language: str, *, x: bool = True, y: bool = True) -> None:
    """The common look; `x`, `y`: whether that axis is numeric (decimal mark of `language`)."""
    ax.grid(True, axis="both", color=_GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", which="both", labelsize=FONT, colors=_INK_2, length=2.5)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(_AXIS)
    formatter = FuncFormatter(_decimal(language))
    if x:
        ax.xaxis.set_major_formatter(formatter)
    if y:
        ax.yaxis.set_major_formatter(formatter)


def _label_ends(ax: Axes, ends: Sequence[tuple[float, float, str, str]], gap: float) -> None:
    """Direct labels right of line ends (x, y, text, colour), pushed apart by at least `gap`
    in data units of y."""
    placed: list[float] = []
    for x, y, text, color in sorted(ends, key=lambda e: e[1]):
        at = max([y, *(p + gap for p in placed[-1:])])
        placed.append(at)
        ax.annotate(
            text,
            (x, y),
            xytext=(x, at),
            textcoords="data",
            fontsize=FONT,
            color=color,
            va="center",
            ha="left",
            annotation_clip=False,
        )


def _point_labels(
    fig: Figure, ax: Axes, points: Sequence[tuple[float, float, str, str]], *, split: float = 0.62
) -> None:
    """Labels beside points (x, y, text, colour): right of a point in the left part of the
    axes, left of it beyond `split`; stacked at least a line apart, with a thin leader line from
    a label moved off its point."""
    fig.draw_without_rendering()
    to_axes = ax.transData + ax.transAxes.inverted()
    step = 1.2 * FONT / (ax.bbox.height * 72 / fig.dpi)
    for side in ("right", "left"):
        items = []
        for x, y, text, color in points:
            fx, fy = to_axes.transform((x, y))
            if (fx > split) == (side == "left"):
                items.append((fy, fx, x, y, text, color))
        items.sort()
        heights: list[float] = []
        for fy, *_ in items:
            heights.append(max(fy, heights[-1] + step) if heights else fy)
        shift = max(0.0, heights[-1] - 0.97) if heights else 0.0
        for (fy, fx, x, y, text, color), at in zip(items, heights, strict=True):
            at -= shift
            moved = abs(at - fy) > 0.25 * step
            label = ax.annotate(
                text,
                (x, y),
                xytext=(fx + (0.035 if side == "right" else -0.035), at),
                textcoords="axes fraction",
                ha="left" if side == "right" else "right",
                va="center",
                fontsize=FONT,
                color=color,
                annotation_clip=False,
                arrowprops={"arrowstyle": "-", "color": _AXIS, "lw": 0.5, "shrinkB": 2.5}
                if moved
                else None,
            )
            label.set_in_layout(False)


def fig_rq1(run: Run, say: Callable[[str], str], language: str) -> Figure:
    """RQ1: share of valid answers and mean edge recall after rounds 0-3, per backend (colour,
    marker) and style (line); a session that stopped keeps its last answer (rounds.csv). The
    lines of several series coincide, so a legend names them."""
    with (run.path / "rounds.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    fig = Figure(figsize=(FULL, 6.0 * CM), layout="constrained")
    axes = fig.subplots(1, 2)
    lines = {"structured": "-", "narrative": "--"}
    models = {"ollama": "qwen2.5:7b", "openrouter": "gpt-oss-120b"}
    panels = (("valid", "Valid answers [%]", 100.0), ("edge_recall", "Edge recall", 1.0))
    for ax, (column, label, scale) in zip(axes, panels, strict=True):
        for b, backend in enumerate(BACKENDS):
            for style, linestyle in lines.items():
                mine = [r for r in rows if r["backend"] == backend and r["style"] == style]
                rounds = sorted({int(r["round"]) for r in mine})
                values = [
                    scale
                    * sum(float(r[column]) for r in mine if int(r["round"]) == k)
                    / sum(1 for r in mine if int(r["round"]) == k)
                    for k in rounds
                ]
                ax.plot(
                    rounds,
                    values,
                    linestyle=linestyle,
                    marker=_MARKERS[2 * b],
                    color=_COLORS[b],
                    lw=1.1,
                    ms=3.5,
                    mfc="white" if style == "narrative" else _COLORS[b],
                    label=f"{models[backend]}, {say(style)}",
                )
        ax.set_xticks(range(4))
        ax.set_ylim(0, 1.05 * scale)
        ax.set_xlabel(say("Round"), fontsize=FONT, color=_INK)
        ax.set_ylabel(say(label), fontsize=FONT, color=_INK)
        _style(ax, language)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="outside upper center",
        ncols=2,
        frameon=False,
        fontsize=FONT,
        labelcolor=_INK,
    )
    return fig


def fig_rq2(run: Run, say: Callable[[str], str], language: str) -> Figure:
    """RQ2: box plots of the deviation from the reference makespan per method and set (mean as
    a diamond)."""
    rows = read_rcpsp(run.path / "results.csv")
    names = {m["name"]: m["label"] for m in run.manifest["config"]["methods"]}
    fig = Figure(figsize=(FULL, 6.4 * CM), layout="constrained")
    axes = fig.subplots(1, 2, sharey=True)
    titles = {"J30": "J30 (optimum)", "J60": "J60 (best known)"}
    for ax, set_name in zip(axes, SETS, strict=True):
        labels = [label for label in names.values() if label in METHODS]
        data = [
            [
                r.dev_ref_pct
                for r in rows
                if r.set_name == set_name.lower()
                and names.get(r.method) == label
                and r.dev_ref_pct is not None
            ]
            for label in labels
        ]
        ax.boxplot(
            data,
            tick_labels=labels,
            widths=0.55,
            patch_artist=True,
            showmeans=True,
            boxprops={"facecolor": "#dcdcd7", "edgecolor": _INK_2, "linewidth": 0.7},
            medianprops={"color": _INK, "linewidth": 1.2},
            whiskerprops={"color": _INK_2, "linewidth": 0.7},
            capprops={"color": _INK_2, "linewidth": 0.7},
            meanprops={
                "marker": "D",
                "markersize": 3,
                "markerfacecolor": "white",
                "markeredgecolor": _INK,
            },
            flierprops={
                "marker": "o",
                "markersize": 2,
                "markerfacecolor": _INK_2,
                "markeredgecolor": "none",
                "alpha": 0.5,
            },
        )
        ax.axhline(0, color=_INK_2, linewidth=0.6, linestyle=":", zorder=0)
        ax.set_title(say(titles[set_name]), fontsize=FONT, color=_INK)
        _style(ax, language, x=False)
        ax.tick_params(axis="x", labelrotation=40)
        for tick in ax.get_xticklabels():
            tick.set_horizontalalignment("right")
    axes[0].set_ylabel(say("Deviation from reference [%]"), fontsize=FONT, color=_INK)
    return fig


def fig_rq3(run: Run, say: Callable[[str], str], language: str) -> Figure:
    """RQ3: Brier score of P(C <= D) at the checkpoints f per forecaster with 95 % cluster
    bootstrap intervals, and the base-rate forecast's score (UNC), per set; delta_D = 0.2."""
    fig = Figure(figsize=(FULL, 5.6 * CM), layout="constrained")
    axes = fig.subplots(1, 2, sharey=True)
    labels = {
        "mc_full": "MC, full",
        "mc_no_future": "MC, no future",
        "deterministic": "deterministic",
    }
    for ax, set_name in zip(axes, SETS, strict=True):
        reference = "optimum" if set_name == "J30" else "best known"
        table = run.tables.table(
            f"{set_name} (C*: {reference}), δ_D = 0.2", "Calibration and discrimination of P(C ≤ D)"
        )
        checkpoints = [f for f in table.column("f") if f != "all"]
        steps = sorted({float(f) for f in checkpoints})
        texts = [f"{f:g}" for f in steps]
        ends = []
        for k, forecaster in enumerate(FORECASTERS):
            parts = [_parts(table, "Brier", {"f": f, "Forecaster": forecaster}) for f in texts]
            values = [float(p.value) for p in parts]
            low = [v - float(p.low or p.value) for v, p in zip(values, parts, strict=True)]
            high = [float(p.high or p.value) - v for v, p in zip(values, parts, strict=True)]
            ax.errorbar(
                steps,
                values,
                yerr=[low, high],
                color=_COLORS[k],
                marker=_MARKERS[k],
                ms=3.5,
                lw=1.1,
                capsize=1.5,
                elinewidth=0.7,
            )
            ends.append((steps[-1] + 0.03, values[-1], say(labels[forecaster]), _COLORS[k]))
        base = [float(_parts(table, "UNC", {"f": f, "Forecaster": "mc_full"}).value) for f in texts]
        ax.plot(steps, base, linestyle=":", color=_INK_2, lw=1.0)
        ends.append((steps[-1] + 0.03, base[-1], say("base rate"), _INK_2))
        _label_ends(ax, ends, gap=0.055)
        ax.set_xlim(-0.04, 1.32)
        ax.set_xticks(steps)
        ax.set_title(say(f"{set_name} ({reference})"), fontsize=FONT, color=_INK)
        ax.set_xlabel(say("Checkpoint f"), fontsize=FONT, color=_INK)
        _style(ax, language)
    axes[0].set_ylabel(say("Brier score"), fontsize=FONT, color=_INK)
    return fig


def _parts(table: Table, column: str, key: Mapping[str, str]) -> Parts:
    return parse_cell(table.cell(column, **key).text)


def _policy_style(policy: str) -> tuple[str, str]:
    if policy in _SENTINEL_MARKERS:
        return _COLORS[_SENTINEL_SLOT], _SENTINEL_MARKERS[policy]
    slot = _POLICY_SLOTS[policy]
    return _COLORS[slot], _MARKERS[slot]


def fig_rq4(run: Run, say: Callable[[str], str], language: str) -> Figure:
    """RQ4: on time (delta_D = 0.2) with 95 % Wilson intervals against plan changes per run
    (nervousness), pooled over lambda_A, per policy; one panel per set, one above the other."""
    fig = Figure(figsize=(FULL, 10.0 * CM), layout="constrained")
    axes = fig.subplots(2, 1)
    labels: dict[int, list[tuple[float, float, str, str]]] = {0: [], 1: []}
    for index, (ax, set_name) in enumerate(zip(axes, SETS, strict=True)):
        table = _main_table(run.tables, RQ4_SECTIONS[set_name])
        for policy in MAIN_POLICIES:
            key = {"λ_A": "all", "Policy": policy}
            on_time = _parts(table, "On time δ=0.2 [%]", key)
            x = float(_parts(table, "Nervousness", key).value)
            y = float(on_time.value)
            color, marker = _policy_style(policy)
            ax.errorbar(
                [x],
                [y],
                yerr=[[y - float(on_time.low or y)], [float(on_time.high or y) - y]],
                color=color,
                marker=marker,
                ms=4.5 if policy.startswith("Sentinel") else 3.5,
                capsize=1.5,
                elinewidth=0.7,
                lw=0,
            )
            labels[index].append((x, y, say(policy), _INK_2))
        ax.set_title(set_name, fontsize=FONT, color=_INK)
        ax.set_ylabel(say("On time [%]"), fontsize=FONT, color=_INK)
        ax.xaxis.set_major_locator(MaxNLocator(6))
        ax.set_xlim(left=-0.05 * max(x for x, *_ in labels[index]))
        _style(ax, language)
    axes[1].set_xlabel(say("Plan changes per run"), fontsize=FONT, color=_INK)
    for index, ax in enumerate(axes):
        _point_labels(fig, ax, labels[index], split=0.55)
    return fig


def fig_rq4_autonomy(
    runs: Mapping[str, Run], point: LadderPoint, say: Callable[[str], str], language: str
) -> Figure:
    """RQ4 autonomy ladder: Sentinel at autonomy levels 0-3 on the same worlds (J30 every 8th,
    lambda_A = 0.01): on time with 95 % Wilson intervals, NoReaction and FullResolve as
    reference lines, and seconds per run."""
    section = RQ4_SECTIONS["J30"]
    autonomy = _main_table(runs["rq4_autonomy"].tables, section)
    ablation = _main_table(runs["rq4_ablation"].tables, section)
    cells = [
        (autonomy, "Sentinel Λ=0"),
        (autonomy, "Sentinel Λ=1"),
        (ablation, "Sentinel Λ=2"),
    ]
    on_time = [_parts(t, "On time δ=0.2 [%]", {"λ_A": "0.01", "Policy": p}) for t, p in cells]
    on_time.append(Parts(point.on_time, point.low, point.high))
    seconds = [float(_parts(t, "s / run", {"λ_A": "0.01", "Policy": p}).value) for t, p in cells]
    seconds.append(float(point.seconds))
    levels = [0, 1, 2, 3]
    fig = Figure(figsize=(FULL, 5.0 * CM), layout="constrained")
    left, right = fig.subplots(1, 2)
    values = [float(p.value) for p in on_time]
    left.errorbar(
        levels,
        values,
        yerr=[
            [v - float(p.low or v) for v, p in zip(values, on_time, strict=True)],
            [float(p.high or v) - v for v, p in zip(values, on_time, strict=True)],
        ],
        color=_COLORS[_SENTINEL_SLOT],
        marker="o",
        ms=4,
        lw=1.1,
        capsize=1.5,
        elinewidth=0.7,
    )
    for policy, linestyle in (("NoReaction", ":"), ("FullResolve", "--")):
        value = float(
            _parts(autonomy, "On time δ=0.2 [%]", {"λ_A": "0.01", "Policy": policy}).value
        )
        color, _ = _policy_style(policy)
        left.hlines(value, -0.3, 3.2, color=color, linestyle=linestyle, lw=1.0)
        left.annotate(
            policy, (3.3, value), fontsize=FONT, color=color, va="center", annotation_clip=False
        )
    left.set_xlim(-0.3, 4.6)
    left.set_ylabel(say("On time [%]"), fontsize=FONT, color=_INK)
    right.plot(levels, seconds, color=_COLORS[_SENTINEL_SLOT], marker="o", ms=4, lw=1.1)
    right.set_ylabel(say("Seconds per run"), fontsize=FONT, color=_INK)
    right.set_ylim(0, 1.1 * max(seconds))
    for ax in (left, right):
        ax.set_xticks(levels)
        ax.set_xlabel(say("Autonomy level Λ"), fontsize=FONT, color=_INK)
        _style(ax, language)
    return fig


def fig_rq5(run: Run, say: Callable[[str], str], language: str) -> Figure:
    """RQ5: share of decision states whose choice is a proposal of the source, with 95 %
    Wilson intervals (150 states)."""
    table = _caption(run.tables, "150 decision states")
    sources = [("random", "random"), ("ollama", "qwen2.5:7b"), ("openrouter", "gpt-oss-120b")]
    fig = Figure(figsize=(HALF, 4.2 * CM), layout="constrained")
    ax = fig.subplots()
    for k, (source, _) in enumerate(sources):
        parts = _parts(table, "Win rate", {"Source": source})
        value = float(parts.value)
        color = _INK_2 if source == "random" else _COLORS[k - 1]
        marker = "D" if source == "random" else _MARKERS[k - 1]
        ax.errorbar(
            [value],
            [k],
            xerr=[[value - float(parts.low or value)], [float(parts.high or value) - value]],
            color=color,
            marker=marker,
            ms=4,
            capsize=1.5,
            elinewidth=0.8,
            lw=0,
        )
        ax.annotate(
            _number(parts.value, language),
            (float(parts.high or value), k),
            xytext=(3, 0),
            textcoords="offset points",
            fontsize=FONT,
            color=_INK_2,
            va="center",
        )
    ax.set_yticks(range(len(sources)))
    ax.set_yticklabels([say(label) for _, label in sources])
    ax.set_ylim(-0.6, len(sources) - 0.4)
    ax.set_xlim(0, 22)
    ax.set_xlabel(say("Win rate [%]"), fontsize=FONT, color=_INK)
    _style(ax, language, y=False)
    return fig
