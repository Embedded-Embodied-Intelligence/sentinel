"""The cockpit's charts as inline SVG, built by hand (WP8; ADR-0021): the Gantt chart of baseline
plan and realised execution with the day's disruptions above it, and the risk chart of the
forecasts. Both share one time axis (day 0 .. horizon), so they align on the page.

Style as in the WP7 figures: the policy colours of the WP4/WP5 figures, and every series also
told apart by shape, fill or line style and named by a direct label or the legend, so that the
charts read in grey scale and in print. Coordinates are written with one decimal, so the same
data give the same bytes. Each mark carries a `<title>` (a native tooltip, which the page's
script turns into its own).
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from html import escape
from itertools import pairwise

from sentinel.dashboard.assemble import DayEvents, Row
from sentinel.dashboard.labels import AXIS, DEADLINE, GRID, INK, INK_2, Text
from sentinel.dashboard.world import Forecast

WIDTH = 1000.0
LEFT = 110.0  # row and lane labels
RIGHT = 150.0  # direct labels
PLOT = WIDTH - LEFT - RIGHT
ROW = 14.0
LANE = 13.0


def num(x: float) -> str:
    """A coordinate with one decimal, without a trailing ".0"."""
    text = f"{x:.1f}"
    return text[:-2] if text.endswith(".0") else text


def _title(text: str) -> str:
    return f"<title>{escape(text)}</title>"


@dataclass(frozen=True)
class Axis:
    """Day 0 .. `horizon` on the plot width."""

    horizon: int

    def x(self, day: float) -> float:
        return LEFT + day / self.horizon * PLOT

    @property
    def step(self) -> int:
        return 5 if self.horizon <= 120 else 10


def horizon(*days: float) -> int:
    """The day axis: the latest day shown, plus a margin, at least 10 days."""
    return max(10, math.ceil(max(days, default=0)) + 3)


def _grid(axis: Axis, top: float, bottom: float) -> list[str]:
    """Light vertical lines every step (a week of 5 working days, spec section 10.1)."""
    return [
        f'<line x1="{num(axis.x(d))}" y1="{num(top)}" x2="{num(axis.x(d))}" y2="{num(bottom)}" '
        f'stroke="{GRID}" stroke-width="0.6"/>'
        for d in range(0, axis.horizon + 1, axis.step)
    ]


def _ticks(axis: Axis, y: float, t: Text) -> list[str]:
    parts = [
        f'<line x1="{num(LEFT)}" y1="{num(y)}" x2="{num(LEFT + PLOT)}" y2="{num(y)}" '
        f'stroke="{AXIS}" stroke-width="0.8"/>'
    ]
    for d in range(0, axis.horizon + 1, axis.step):
        x = num(axis.x(d))
        parts.append(f'<line x1="{x}" y1="{num(y)}" x2="{x}" y2="{num(y + 3)}" stroke="{AXIS}"/>')
        if d % (2 * axis.step) == 0:
            parts.append(
                f'<text x="{x}" y="{num(y + 13)}" text-anchor="middle" class="tick">{d}</text>'
            )
    parts.append(
        f'<text x="{num(LEFT + PLOT + 6)}" y="{num(y + 13)}" class="tick">{escape(t["day"])}</text>'
    )
    return parts


def _open(width: float, height: float, key: str, title: str, desc: str) -> str:
    return (
        f'<svg viewBox="0 0 {num(width)} {num(height)}" role="img" class="chart" '
        f'aria-labelledby="{key}-title {key}-desc">'
        f'<title id="{key}-title">{escape(title)}</title>'
        f'<desc id="{key}-desc">{escape(desc)}</desc>'
    )


def triangle(x: float, y: float, size: float, down: bool) -> str:
    h = size if down else -size
    return f"M{num(x - size)} {num(y - h)}L{num(x + size)} {num(y - h)}L{num(x)} {num(y + h)}Z"


def diamond(x: float, y: float, size: float) -> str:
    return (
        f"M{num(x)} {num(y - size)}L{num(x + size)} {num(y)}L{num(x)} {num(y + size)}"
        f"L{num(x - size)} {num(y)}Z"
    )


@dataclass(frozen=True)
class VLine:
    """A vertical reference line on the day axis with its label and style."""

    day: float
    label: str
    color: str
    dash: str
    width: float = 1.2


def gantt(
    rows: Sequence[Row],
    events: Sequence[DayEvents],
    axis: Axis,
    lines: Sequence[VLine],
    *,
    color: str,
    key: str,
    title: str,
    t: Text,
) -> str:
    """The Gantt chart of one run: lanes of the day's absences, D2 and D3 events, then one row
    per activity with its baseline bar (thin, grey) over its realised execution (solid: full
    crew, striped: partial crew, outline: paused), markers and the reference lines."""
    lanes_top = 8.0
    top = lanes_top + 3 * LANE + 8
    bottom = top + len(rows) * ROW + 4
    height = bottom + 22 + 13 * len(lines) + 6
    parts = [
        _open(WIDTH, height, key, title, t.gantt_desc(len(rows), events)),
        f'<defs><pattern id="stripes-{key}" width="4" height="4" patternUnits="userSpaceOnUse" '
        f'patternTransform="rotate(45)"><rect width="4" height="4" fill="white"/>'
        f'<rect width="2" height="4" fill="{color}"/></pattern></defs>',
        *_grid(axis, lanes_top, bottom),
    ]
    for i, name in enumerate(("lane_absences", "lane_work", "lane_new")):
        y = lanes_top + i * LANE + LANE / 2 + 3.5
        parts.append(
            f'<text x="{num(LEFT - 6)}" y="{num(y)}" text-anchor="end" class="lane">'
            f"{escape(t[name])}</text>"
        )
    parts += _lanes(events, axis, lanes_top, t)
    parts.append(
        f'<line x1="{num(LEFT)}" y1="{num(top - 4)}" x2="{num(LEFT + PLOT)}" y2="{num(top - 4)}" '
        f'stroke="{AXIS}" stroke-width="0.6"/>'
        f'<text x="{num(LEFT - 6)}" y="{num(top + 1)}" text-anchor="end" class="lane">'
        f"{escape(t['activity_axis'])}</text>"
    )
    for i, row in enumerate(rows):
        parts += _row(row, axis, top + i * ROW, color, key, t)
    parts += _ticks(axis, bottom, t)
    parts += _vlines(lines, axis, lanes_top, bottom, bottom + 26)
    parts.append("</svg>")
    return "".join(parts)


def _lanes(events: Sequence[DayEvents], axis: Axis, top: float, t: Text) -> list[str]:
    parts = []
    for day in events:
        x = axis.x(day.day + 0.5)
        y = top + LANE / 2
        if day.crew_absences or day.idle_absences:
            filled = bool(day.crew_absences)
            tip = t.absences_tip(day)
            fill = INK if filled else "white"
            parts.append(
                f'<path d="{triangle(x, y, 3.2, True)}" fill="{fill}" stroke="{INK}" '
                f'stroke-width="0.8">{_title(tip)}</path>'
            )
        if day.work_increases:
            tip = t.work_tip(day)
            y = top + LANE * 1.5
            mark = triangle(x, y, 3.2, False)
            parts.append(f'<path d="{mark}" fill="{INK}">{_title(tip)}</path>')
        if day.new_activities:
            tip = t.new_tip(day)
            y = top + LANE * 2.5
            parts.append(
                f'<path d="{diamond(x, y, 3.6)}" fill="white" stroke="{INK}" stroke-width="1">'
                f"{_title(tip)}</path>"
            )
    return parts


def _row(row: Row, axis: Axis, y: float, color: str, key: str, t: Text) -> list[str]:
    label = ("+" if row.inserted else "") + str(row.activity)
    parts = [
        f'<text x="{num(LEFT - 6)}" y="{num(y + 10)}" text-anchor="end" class="row">'
        f"{escape(label)}{_title(t.activity_tip(row))}</text>"
    ]
    if row.descoped_day is not None:
        x = axis.x(row.descoped_day)
        width = 6.5 * len(label)
        parts.append(
            f'<line x1="{num(LEFT - 6 - width)}" y1="{num(y + 7)}" x2="{num(LEFT - 4)}" '
            f'y2="{num(y + 7)}" stroke="{INK}"/>'
            f'<path d="M{num(x - 3)} {num(y + 4)}L{num(x + 3)} {num(y + 10)}M{num(x + 3)} '
            f'{num(y + 4)}L{num(x - 3)} {num(y + 10)}" stroke="{INK}" stroke-width="1.4">'
            f"{_title(t.descoped_tip(row))}</path>"
        )
    if row.planned is not None:
        x0, x1 = axis.x(row.planned), axis.x(row.planned + row.duration)
        parts.append(
            f'<rect x="{num(x0)}" y="{num(y + 2)}" width="{num(x1 - x0)}" height="3.5" '
            f'fill="{AXIS}">{_title(t.planned_tip(row))}</rect>'
        )
    if row.inserted_day is not None:
        x = axis.x(row.inserted_day)
        parts.append(
            f'<path d="{diamond(x, y + 7, 3.2)}" fill="white" stroke="{INK}" stroke-width="1">'
            f"{_title(t.inserted_tip(row))}</path>"
        )
    for segment in row.segments:
        x0, x1 = axis.x(segment.start), axis.x(segment.end)
        full = segment.present >= row.crew
        fill = color if full else f"url(#stripes-{key})"
        parts.append(
            f'<rect x="{num(x0)}" y="{num(y + 6.5)}" width="{num(x1 - x0)}" height="6.5" '
            f'fill="{fill}" stroke="{color}" stroke-width="0.6">'
            f"{_title(t.segment_tip(row, segment))}</rect>"
        )
    for first, last in row.paused:
        x0, x1 = axis.x(first), axis.x(last)
        parts.append(
            f'<rect x="{num(x0)}" y="{num(y + 7)}" width="{num(x1 - x0)}" height="5.5" '
            f'fill="none" stroke="{color}" stroke-width="0.9" stroke-dasharray="2 1.5">'
            f"{_title(t.paused_tip(first, last))}</rect>"
        )
    temporary = [s for s in row.segments if s.temporary]
    if temporary:
        x = axis.x(temporary[0].start) + 2.5
        parts.append(
            f'<circle cx="{num(x)}" cy="{num(y + 9.75)}" r="2.3" fill="white" stroke="{INK}" '
            f'stroke-width="0.9">{_title(t.temporary_tip(row, temporary[0].start))}</circle>'
        )
    for substitution in row.substitutions:
        x = axis.x(substitution.day)
        parts.append(
            f'<path d="{diamond(x, y + 9.75, 3.2)}" fill="{INK}" stroke="white" '
            f'stroke-width="0.6">{_title(t.substitution_tip(substitution))}</path>'
        )
    for day, factor in row.shocks:
        x = axis.x(day + 0.5)
        parts.append(
            f'<path d="{triangle(x, y + 4.2, 2.6, False)}" fill="{INK}">'
            f"{_title(t.shock_tip(row, day, factor))}</path>"
        )
    return parts


def _vlines(
    lines: Sequence[VLine], axis: Axis, top: float, bottom: float, label_top: float
) -> list[str]:
    """Reference lines over the plot, each labelled on its own line below the axis."""
    parts = []
    for i, line in enumerate(lines):
        x = axis.x(line.day)
        dash = f' stroke-dasharray="{line.dash}"' if line.dash else ""
        parts.append(
            f'<line x1="{num(x)}" y1="{num(top)}" x2="{num(x)}" y2="{num(bottom)}" '
            f'stroke="{line.color}" stroke-width="{num(line.width)}"{dash}/>'
        )
        anchor = "end" if x > LEFT + PLOT * 0.85 else "middle"
        parts.append(
            f'<text x="{num(x)}" y="{num(label_top + 13 * i)}" text-anchor="{anchor}" '
            f'class="vlabel" fill="{line.color}">{escape(line.label)}</text>'
        )
    return parts


@dataclass(frozen=True)
class Outcome:
    """A realised makespan drawn on the makespan panel."""

    label: str
    makespan: int
    color: str
    dash: str


def risk(
    forecasts: Sequence[Forecast],
    axis: Axis,
    *,
    deadline: int,
    target: float,
    outcomes: Sequence[Outcome],
    color: str,
    key: str,
    title: str,
    t: Text,
) -> str:
    """Two panels on the day axis: NOOP's P(C <= D) at each forecast with the chosen action's
    p (filled triangle: applied at once; hollow: deferred or escalated) and the target theta_D;
    below, the P10-P90 band and the median of the makespan forecast with the deadline and the
    realised makespans."""
    a_top, a_height = 22.0, 150.0
    b_top, b_height = a_top + a_height + 42, 180.0
    bottom = b_top + b_height
    parts = [
        _open(WIDTH, bottom + 24, key, title, t.risk_desc(forecasts, deadline)),
        f'<text x="{num(LEFT)}" y="12" class="panel">{escape(t["risk_panel_p"])}</text>',
        f'<text x="{num(LEFT)}" y="{num(b_top - 10)}" class="panel">'
        f"{escape(t['risk_panel_c'])}</text>",
    ]
    parts += _grid(axis, a_top, a_top + a_height) + _grid(axis, b_top, bottom)

    def y_p(p: float) -> float:
        return a_top + (1 - p) * a_height

    for i in range(6):
        p = i / 5
        parts.append(
            f'<line x1="{num(LEFT)}" y1="{num(y_p(p))}" x2="{num(LEFT + PLOT)}" y2="{num(y_p(p))}" '
            f'stroke="{GRID}" stroke-width="0.6"/>'
            f'<text x="{num(LEFT - 6)}" y="{num(y_p(p) + 3.5)}" text-anchor="end" class="tick">'
            f"{t.num(p, 1)}</text>"
        )
    parts.append(
        f'<line x1="{num(LEFT)}" y1="{num(y_p(target))}" x2="{num(LEFT + PLOT)}" '
        f'y2="{num(y_p(target))}" stroke="{INK_2}" stroke-width="1" stroke-dasharray="5 3"/>'
    )
    labels = [(t.target_label(target), y_p(target), INK_2)]
    if forecasts:
        labels.append((t["series_noop"], y_p(forecasts[-1].p_on_time), color))
    spread = _spread([y for _, y, _ in labels], 11.0)
    for (label, _, label_color), y in zip(labels, spread, strict=True):
        parts.append(
            f'<text x="{num(LEFT + PLOT + 6)}" y="{num(y + 3.5)}" class="vlabel" '
            f'fill="{label_color}">{escape(label)}</text>'
        )
    xd = axis.x(deadline)
    for y0, y1 in ((a_top, a_top + a_height), (b_top, bottom)):
        parts.append(
            f'<line x1="{num(xd)}" y1="{num(y0)}" x2="{num(xd)}" y2="{num(y1)}" '
            f'stroke="{DEADLINE}" stroke-width="1" stroke-dasharray="4 2"/>'
        )
    if forecasts:
        points = " ".join(f"{num(axis.x(f.day))},{num(y_p(f.p_on_time))}" for f in forecasts)
        parts.append(
            f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="1.4"/>'
        )
        for f in forecasts:
            parts.append(
                f'<circle cx="{num(axis.x(f.day))}" cy="{num(y_p(f.p_on_time))}" r="2.6" '
                f'fill="{color}" stroke="white" stroke-width="0.6">{_title(t.forecast_tip(f))}'
                "</circle>"
            )
        for f in forecasts:
            if f.p_chosen is None:
                continue
            applied = f.gate == "auto"
            fill = INK if applied else "white"
            parts.append(
                f'<path d="{triangle(axis.x(f.day), y_p(f.p_chosen), 3.6, False)}" '
                f'fill="{fill}" stroke="{INK}" stroke-width="1">{_title(t.chosen_tip(f))}</path>'
            )
    values = [v for f in forecasts for v in (f.p10, f.p90)]
    values += [deadline, *(o.makespan for o in outcomes)]
    step = 5 if max(values) - min(values) <= 60 else 10
    low = step * math.floor((min(values) - 2) / step)
    high = step * math.ceil((max(values) + 2) / step)

    def y_c(c: float) -> float:
        return b_top + (high - c) / (high - low) * b_height

    for c in range(int(low), int(high) + 1, step):
        parts.append(
            f'<line x1="{num(LEFT)}" y1="{num(y_c(c))}" x2="{num(LEFT + PLOT)}" y2="{num(y_c(c))}" '
            f'stroke="{GRID}" stroke-width="0.6"/>'
            f'<text x="{num(LEFT - 6)}" y="{num(y_c(c) + 3.5)}" text-anchor="end" class="tick">'
            f"{c}</text>"
        )
    if forecasts:
        upper = [f"{num(axis.x(f.day))},{num(y_c(f.p90))}" for f in forecasts]
        lower = [f"{num(axis.x(f.day))},{num(y_c(f.p10))}" for f in reversed(forecasts)]
        parts.append(
            f'<polygon points="{" ".join(upper + lower)}" fill="{color}" fill-opacity="0.18" '
            f'stroke="{color}" stroke-width="0.6" stroke-dasharray="2 2"/>'
        )
        medians = " ".join(f"{num(axis.x(f.day))},{num(y_c(f.p50))}" for f in forecasts)
        parts.append(
            f'<polyline points="{medians}" fill="none" stroke="{color}" stroke-width="1.2"/>'
        )
        for f in forecasts:
            parts.append(
                f'<rect x="{num(axis.x(f.day) - 2)}" y="{num(y_c(f.p50) - 2)}" width="4" '
                f'height="4" fill="{color}">{_title(t.forecast_tip(f))}</rect>'
            )
    references = [(t.deadline_label(deadline), deadline, DEADLINE, "4 2")]
    references += [(o.label, o.makespan, o.color, o.dash) for o in outcomes]
    ys = _spread([y_c(value) for _, value, _, _ in references], 11.0)
    for (label, value, line_color, dash), y_label in zip(references, ys, strict=True):
        dashes = f' stroke-dasharray="{dash}"' if dash else ""
        parts.append(
            f'<line x1="{num(LEFT)}" y1="{num(y_c(value))}" x2="{num(LEFT + PLOT)}" '
            f'y2="{num(y_c(value))}" stroke="{line_color}" stroke-width="1.3"{dashes}/>'
            f'<text x="{num(LEFT + PLOT + 6)}" y="{num(y_label + 3.5)}" class="vlabel" '
            f'fill="{line_color}">{escape(label)}</text>'
        )
    parts += _ticks(axis, bottom, t)
    parts.append(
        f'<text x="{num(14)}" y="{num(a_top + a_height / 2)}" class="tick" '
        f'transform="rotate(-90 14 {num(a_top + a_height / 2)})" text-anchor="middle">'
        f"P(C ≤ D)</text>"
        f'<text x="{num(14)}" y="{num(b_top + b_height / 2)}" class="tick" '
        f'transform="rotate(-90 14 {num(b_top + b_height / 2)})" text-anchor="middle">'
        f"{escape(t['makespan_axis'])}</text>"
    )
    parts.append("</svg>")
    return "".join(parts)


def _spread(values: Sequence[float], gap: float) -> list[float]:
    """Label positions near `values`, pushed apart to at least `gap` (input order kept)."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    placed = list(values)
    for previous, current in pairwise(order):
        placed[current] = max(placed[current], placed[previous] + gap)
    return placed
