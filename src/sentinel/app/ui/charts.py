"""The plan-and-progress chart of a live project as inline SVG (WP9b; ADR-0025), built on the
cockpit's chart primitives (`dashboard.svg`): the original plan over the reported work and the
current plan, the status line and today's date, the deadline and the absences, on an axis of
working days labelled with calendar dates (spec section 11.1).

Colours come from CSS classes (light and dark mode); every series is also told apart by its
shape or outline and named in the legend, and each bar carries a `<title>` in words, so colour is
never the only signal. A table of the same dates follows the chart for screen readers.
"""

import math
from dataclasses import dataclass
from datetime import date
from html import escape

from sentinel.app.live import LiveProject
from sentinel.app.ui.text import Texts
from sentinel.dashboard.svg import num

WIDTH = 1000.0
LABEL = 230.0  # task names
RIGHT = 20.0
ROW = 24.0
BAR = 14.0
TOP = 34.0  # date labels and the reference lines' labels
MAX_LABEL = 32


@dataclass(frozen=True)
class ChartRow:
    """A row of the chart: a task, or the absences of one person."""

    key: str
    label: str
    state: str  # done, running, paused, planned, removed, absence
    original: tuple[int, int] | None  # the original plan [start, finish) in working days
    actual: tuple[int, int] | None  # reported work [start, end)
    planned: tuple[int, int] | None  # the current plan (unstarted) or the expected rest
    tip: str
    added: bool = False
    absences: tuple[tuple[int, int, bool], ...] = ()  # [start, end), open-ended


def rows_of(project: LiveProject, texts: Texts) -> list[ChartRow]:
    """The chart's rows: one per person with absences, then the tasks by start date."""
    calendar = project.calendar
    t = project.day
    baseline = project.baseline
    nodes = project.nodes()
    rows: list[ChartRow] = []
    names = {p.key: p.name for p in project.definition.team}
    people: dict[str, list[tuple[int, int, bool]]] = {}
    for absence in project.absences:
        end = absence.back if absence.back is not None else max(t, absence.start) + 1
        people.setdefault(absence.person, []).append((absence.start, end, absence.back is None))
    for person, spans in people.items():
        parts = []
        for start, end, open_ in spans:
            first = texts.date(calendar.date_of(start))
            if open_:
                parts.append(texts("chart.away_open", first=first))
            else:
                parts.append(
                    texts("chart.away", first=first, back=texts.date(calendar.date_of(end)))
                )
        name = names.get(person, person)
        rows.append(
            ChartRow(
                key=f"away-{person}",
                label=name,
                state="absence",
                original=None,
                actual=None,
                planned=None,
                tip=f"{name}: " + "; ".join(parts),
                absences=tuple(spans),
            )
        )
    tasks = []
    for order, (key, tracked) in enumerate(project.tasks.items()):
        node = nodes[key]
        duration = max(1, node.duration)
        original = None
        if baseline is not None and key in baseline.starts:
            start = baseline.starts[key]
            original = (start, start + node.duration)
        factor = 1.0
        for shock in project.shocks:
            if shock.task == key:
                factor *= shock.factor
        name = node.name
        actual = planned = None
        if tracked.state == "removed":
            state = "removed"
            tip = texts("chart.tip_removed", task=name)
            sort = (math.inf, order)
        elif tracked.state == "done" and tracked.start is not None and tracked.finish is not None:
            state = "done"
            actual = (tracked.start, tracked.finish)
            tip = texts(
                "chart.tip_done",
                task=name,
                start=texts.date(calendar.date_of(tracked.start)),
                finish=texts.date(calendar.finish_date(tracked.finish)),
            )
            sort = (tracked.start, order)
        elif tracked.start is not None:
            crew = [m for m in tracked.crew if not m.startswith("temp:")]
            away = bool(crew) and all(project.absent(m, t) is not None for m in crew)
            state = "paused" if away else "running"
            actual = (tracked.start, max(t, tracked.start + 1))
            total = duration * factor
            done = tracked.work / max(1, node.unit)
            rest = max(1, math.ceil(total - done - 1e-9))
            planned = (actual[1], actual[1] + rest)
            percent = round(100 * min(0.99, done / total)) if total > 0 else 0
            tip = texts(
                "chart.tip_running",
                task=name,
                start=texts.date(calendar.date_of(tracked.start)),
                percent=percent,
            )
            sort = (tracked.start, order)
        else:
            state = "planned"
            planned = (tracked.planned, tracked.planned + node.duration)
            tip = texts(
                "chart.tip_planned",
                task=name,
                start=texts.date(calendar.date_of(tracked.planned)),
                finish=texts.date(calendar.finish_date(tracked.planned + max(1, node.duration))),
            )
            sort = (tracked.planned, order)
        label = name if len(name) <= MAX_LABEL else name[: MAX_LABEL - 1] + "…"
        added = key in {task.key for task in project.inserted}
        tasks.append(
            (sort, ChartRow(key, label, state, original, actual, planned, tip, added=added))
        )
    rows += [row for _, row in sorted(tasks, key=lambda item: item[0])]
    return rows


def gantt(project: LiveProject, texts: Texts, today: date | None = None) -> str:
    """The chart (module docstring) as an inline SVG element."""
    calendar = project.calendar
    rows = rows_of(project, texts)
    model = project.require_model()
    t = project.day
    ends = [t + 3, project.sink_plan]
    if project.baseline is not None:
        ends.append(project.baseline.makespan)
    if model.deadline is not None:
        ends.append(model.deadline)
    for row in rows:
        for span in (row.original, row.actual, row.planned):
            if span is not None:
                ends.append(span[1])
        ends += [end for _, end, _ in row.absences]
    horizon = max(10, max(ends) + 2)
    plot = WIDTH - LABEL - RIGHT

    def x(day: float) -> float:
        return LABEL + max(0.0, min(day, horizon)) / horizon * plot

    height = TOP + len(rows) * ROW + 30
    title = texts("chart.title")
    counts = {
        state: sum(1 for row in rows if row.state == state)
        for state in ("done", "running", "paused", "planned")
    }
    desc = texts(
        "chart.desc",
        tasks=sum(counts.values()),
        done=counts["done"],
        running=counts["running"] + counts["paused"],
        status=texts.date(calendar.date_of(t)),
    )
    parts = [
        f'<svg class="gantt" viewBox="0 0 {num(WIDTH)} {num(height)}" role="img" '
        'aria-labelledby="gantt-title gantt-desc" preserveAspectRatio="xMinYMin meet">'
        f'<title id="gantt-title">{escape(title)}</title>'
        f'<desc id="gantt-desc">{escape(desc)}</desc>',
        '<defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" '
        'patternTransform="rotate(45)"><rect width="6" height="6" class="hatch-bg"/>'
        '<rect width="2.5" height="6" class="hatch-fg"/></pattern></defs>',
    ]
    # Weeks: a light line on every Monday, labelled with its date (every second or fourth one
    # on long projects).
    mondays = [d for d in range(horizon + 1) if calendar.date_of(d).weekday() == 0]
    step = 1 if len(mondays) <= 14 else 2 if len(mondays) <= 28 else 4
    bottom = TOP + len(rows) * ROW
    for i, d in enumerate(mondays):
        xd = num(x(d))
        parts.append(
            f'<line class="grid" x1="{xd}" y1="{num(TOP - 6)}" x2="{xd}" y2="{num(bottom)}"/>'
        )
        if i % step == 0:
            label = texts.day_month(calendar.date_of(d))
            parts.append(
                f'<text class="tick" x="{xd}" y="{num(bottom + 16)}" text-anchor="middle">'
                f"{escape(label)}</text>"
            )
    for i, row in enumerate(rows):
        y = TOP + i * ROW
        mid = y + ROW / 2
        cls = "row-label" + (" removed" if row.state == "removed" else "")
        label = escape(row.label) + (" " + escape(texts("chart.new")) if row.added else "")
        parts.append(
            f'<text class="{cls}" x="{num(LABEL - 8)}" y="{num(mid + 4)}" text-anchor="end">{label}'
            f"<title>{escape(row.tip)}</title></text>"
        )
        if i % 2 == 0:
            parts.append(
                f'<rect class="band" x="{num(LABEL)}" y="{num(y)}" width="{num(plot)}" '
                f'height="{num(ROW)}"/>'
            )
        if row.state == "absence":
            for start, end, open_ in row.absences:
                cls = "bar-away" + (" open" if open_ else "")
                parts.append(_bar(x(start), x(end), mid - BAR / 2, BAR, cls, row.tip))
            continue
        if row.original is not None:
            a, b = row.original
            parts.append(
                _bar(
                    x(a),
                    x(b),
                    y + 3,
                    4,
                    "bar-original",
                    texts("chart.tip_original", task=row.label),
                )
            )
        if row.actual is not None:
            a, b = row.actual
            cls = {"done": "bar-done", "running": "bar-running", "paused": "bar-paused"}[row.state]
            parts.append(_bar(x(a), x(b), mid - BAR / 2 + 2, BAR - 2, cls, row.tip))
        if row.planned is not None:
            a, b = row.planned
            cls = "bar-rest" if row.actual is not None else "bar-planned"
            parts.append(_bar(x(a), x(b), mid - BAR / 2 + 2, BAR - 2, cls, row.tip))
    status = project.checkins[-1][0] if project.checkins else calendar.date_of(0)
    lines = [(t, "line-status", texts("chart.status", date=texts.day_month(status)))]
    if model.deadline is not None:
        last_day = project.definition.deadline or calendar.date_of(model.deadline - 1)
        label = texts("chart.deadline", date=texts.day_month(last_day))
        lines.append((model.deadline, "line-deadline", label))
    if today is not None and calendar.date_of(0) <= today:
        now = calendar.first(today)  # the line stands at the start of today
        if now <= horizon and now != t:
            lines.append((now, "line-today", texts("chart.today")))
    for k, (day, cls, label) in enumerate(lines):
        xd = num(x(day))
        parts.append(
            f'<line class="{cls}" x1="{xd}" y1="{num(TOP - 8)}" x2="{xd}" y2="{num(bottom)}"/>'
        )
        anchor = "start" if x(day) < WIDTH - 140 else "end"
        dx = 4 if anchor == "start" else -4
        parts.append(
            f'<text class="line-label {cls}-label" x="{num(x(day) + dx)}" y="{num(10 + 11 * k)}" '
            f'text-anchor="{anchor}">{escape(label)}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _bar(x1: float, x2: float, y: float, height: float, cls: str, tip: str) -> str:
    width = max(2.0, x2 - x1)
    return (
        f'<rect class="{cls}" x="{num(x1)}" y="{num(y)}" width="{num(width)}" '
        f'height="{num(height)}" rx="2"><title>{escape(tip)}</title></rect>'
    )
