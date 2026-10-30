"""The plan-and-progress chart as inline SVG (WP9b, WP10; ADR-0025, ADR-0027), on an axis of working
days labelled with calendar dates (spec section 11.1): the original plan over the reported work and
the current plan, the status line and today, the deadline, the forecast window, the absences and
the tasks that threaten the deadline; and the small charts of the overview and the history.

The bars' horizontal positions are percentages of the plot, so the chart fills its card and its
rows keep their height; the names are an HTML column beside it, so they stay in view when a small
screen scrolls the plot and every row can take the focus. Colours come from CSS classes (light and
dark mode); every series also differs by shape and is named in the legend (docs/design/brief.md,
section 3.15), and a table of the same facts goes with the chart.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from sentinel.app.calendar import WorkCalendar
from sentinel.app.live import LiveProject
from sentinel.app.simulator import PolicyRun
from sentinel.app.ui.text import Texts
from sentinel.simulation.state import DONE, PAUSED, REMOVED, RUNNING

ROW = 32
BAR = 14
BAR_TOP = 12  # a bar's place in its row; the original plan's line runs 3 px above it
ORIGINAL = 3
AXIS = 20  # the row of date labels
TIER = 22  # a row of flags above the date labels
PX_PER_DAY = 9  # the plot's least width per working day: it scrolls in its card below that
MIN_PLOT = 480
FLAG_CHAR = 6.8  # the estimated width of a flag's character at 12 px, in px
FLAG_PAD = 8
WEEK = 5


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
    threat: str | None = None  # the sentence of a task that threatens the deadline


@dataclass(frozen=True)
class Bar:
    """A shape of a row, in per cent of the plot's width and px of its height."""

    x: float
    width: float
    y: float
    height: float
    cls: str


@dataclass(frozen=True)
class Line:
    """A vertical line of the chart with its flag: the status, today, the deadline, a limit of the
    forecast window."""

    day: int
    cls: str
    label: str
    x: float = 0.0
    tier: int = 0
    width: float = 0.0
    flip: bool = False


@dataclass(frozen=True)
class Tick:
    x: float
    label: str | None
    anchor: str = "middle"


@dataclass(frozen=True)
class PlotRow:
    row: ChartRow
    y: float
    bars: tuple[Bar, ...]


@dataclass(frozen=True)
class Gantt:
    """Everything the chart's template (`_gantt.html`) draws."""

    title: str
    desc: str
    rows: tuple[PlotRow, ...]
    ticks: tuple[Tick, ...]
    lines: tuple[Line, ...]
    window: tuple[float, float] | None
    top: int
    bottom: int
    height: int
    min_width: int
    open_at: float  # where a small screen opens the plot: a week before the status line
    tiers: int


def flags_in_tiers(lines: Sequence[Line], min_width: int, percent: float = 100.0) -> list[Line]:
    """The lines with their flags placed: each flag on the lowest tier where it overlaps no other,
    turned to the left of its line if it would run over the plot's end."""
    placed: list[Line] = []
    taken: list[list[tuple[float, float]]] = []
    for line in lines:
        width = (len(line.label) * FLAG_CHAR + 2 * FLAG_PAD) / min_width * percent
        flip = line.x + width > percent
        left, right = (line.x - width, line.x) if flip else (line.x, line.x + width)
        tier = next(
            (i for i, spans in enumerate(taken) if all(right <= a or left >= b for a, b in spans)),
            len(taken),
        )
        if tier == len(taken):
            taken.append([])
        taken[tier].append((left, right))
        pixels = len(line.label) * FLAG_CHAR + 2 * FLAG_PAD
        placed.append(
            Line(line.day, line.cls, line.label, line.x, tier, width=pixels, flip=flip),
        )
    return placed


def layout(
    rows: Sequence[ChartRow],
    calendar: WorkCalendar,
    t: int,
    lines: Sequence[tuple[int, str, str]],
    window: tuple[int, int] | None,
    title: str,
    desc: str,
    texts: Texts,
    ends: Sequence[int] = (),
) -> Gantt:
    """The chart's geometry: the range runs from the project's start to a week after the latest
    thing it shows (the bad case, when there is a forecast)."""
    reach = [t + 3, *ends, *(day for day, _, _ in lines)]
    if window is not None:
        reach.append(window[1] + WEEK)
    for row in rows:
        for span in (row.original, row.actual, row.planned):
            if span is not None:
                reach.append(span[1])
        reach += [end for _, end, _ in row.absences]
    horizon = max(10, max(reach) + 2)
    min_width = max(MIN_PLOT, horizon * PX_PER_DAY)

    def x(day: float) -> float:
        return round(max(0.0, min(day, horizon)) / horizon * 100, 3)

    flags = flags_in_tiers(
        [Line(day, cls, label, x(day)) for day, cls, label in lines if day <= horizon], min_width
    )
    tiers = 1 + max((f.tier for f in flags), default=0)
    top = tiers * TIER + AXIS
    plotted = []
    for i, row in enumerate(rows):
        y = top + i * ROW
        plotted.append(PlotRow(row, y, tuple(_bars(row, y, x))))
    bottom = top + len(rows) * ROW
    mondays = [d for d in range(horizon + 1) if calendar.date_of(d).weekday() == 0]
    # One label a week while they fit at the plot's least width; every second or fourth one after.
    step = 1 if len(mondays) * 44 <= min_width else 2 if len(mondays) * 22 <= min_width else 4
    ticks = tuple(
        Tick(
            x(d),
            texts.day_month(calendar.date_of(d)) if i % step == 0 else None,
            "start" if x(d) < 3 else "end" if x(d) > 97 else "middle",
        )
        for i, d in enumerate(mondays)
    )
    return Gantt(
        title=title,
        desc=desc,
        rows=tuple(plotted),
        ticks=ticks,
        lines=tuple(flags),
        window=None if window is None else (x(window[0]), x(window[1]) - x(window[0])),
        top=top,
        bottom=bottom,
        height=bottom + 4,
        min_width=min_width,
        open_at=x(max(0, t - WEEK)),
        tiers=tiers,
    )


def _bars(row: ChartRow, y: float, x: object) -> list[Bar]:
    assert callable(x)
    bars: list[Bar] = []

    def bar(span: tuple[int, int], top: float, height: float, cls: str) -> None:
        left = x(span[0])
        bars.append(Bar(left, max(0.25, round(x(span[1]) - left, 3)), y + top, height, cls))

    if row.state == "absence":
        for start, end, open_ in row.absences:
            bar((start, end), BAR_TOP - 3, BAR, "bar-away open" if open_ else "bar-away")
        return bars
    if row.original is not None:
        bar(row.original, BAR_TOP - ORIGINAL - 3, ORIGINAL, "bar-original")
    if row.actual is not None:
        cls = {"done": "bar-done", "running": "bar-running", "paused": "bar-paused"}[row.state]
        bar(row.actual, BAR_TOP, BAR, cls)
    if row.planned is not None:
        cls = "bar-rest" if row.actual is not None else "bar-planned"
        bar(row.planned, BAR_TOP, BAR, cls)
    return bars


def rows_of(
    project: LiveProject, texts: Texts, threats: Mapping[str, str] | None = None
) -> list[ChartRow]:
    """The chart's rows: one per person with absences, then the tasks by start date."""
    calendar = project.calendar
    t = project.day
    baseline = project.baseline
    nodes = project.nodes()
    rows: list[ChartRow] = []
    names = {p.key: p.name for p in project.definition.team}
    names.update({temp.key: temp.name for temp in project.temps})
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
        crew_names = [names.get(member, member) for member in tracked.crew]
        if crew_names:
            tip = f"{tip} · {', '.join(crew_names)}"
        threat = None if threats is None else threats.get(key)
        added = key in {task.key for task in project.inserted}
        tasks.append(
            (
                sort,
                ChartRow(
                    key, name, state, original, actual, planned, tip, added=added, threat=threat
                ),
            )
        )
    rows += [row for _, row in sorted(tasks, key=lambda item: item[0])]
    return rows


def status_lines(
    calendar: WorkCalendar, t: int, status: date, today: date | None, texts: Texts
) -> list[tuple[int, str, str]]:
    """The status line and, when it differs and has come, today's date."""
    now = None if today is None or today < calendar.date_of(0) else calendar.first(today)
    if now == t:
        return [(t, "line-today", texts("chart.flag.today", date=texts.day_month(status)))]
    lines = [(t, "line-today", texts("chart.flag.status", date=texts.day_month(status)))]
    if now is not None and today is not None:
        lines.append((now, "line-now", texts("chart.flag.today", date=texts.day_month(today))))
    return lines


def live_gantt(
    project: LiveProject,
    texts: Texts,
    today: date | None = None,
    window: tuple[date, date] | None = None,
    threats: Mapping[str, str] | None = None,
) -> Gantt:
    """The chart of a live project; `window` is the forecast's most likely and bad-case finish."""
    calendar = project.calendar
    rows = rows_of(project, texts, threats)
    model = project.require_model()
    t = project.day
    status = project.checkins[-1][0] if project.checkins else calendar.date_of(0)
    lines = status_lines(calendar, t, status, today, texts)
    if model.deadline is not None:
        last_day = project.definition.deadline or calendar.date_of(model.deadline - 1)
        lines.append(
            (
                model.deadline,
                "line-deadline",
                texts("chart.flag.deadline", date=texts.day_month(last_day)),
            )
        )
    days = None
    if window is not None:
        days = (calendar.last(window[0]) + 1, calendar.last(window[1]) + 1)
        lines.append(
            (days[1], "line-window", texts("chart.flag.bad", date=texts.day_month(window[1])))
        )
        lines.insert(
            -1,
            (days[0], "line-window", texts("chart.flag.likely", date=texts.day_month(window[0]))),
        )
    counts = {
        state: sum(1 for row in rows if row.state == state)
        for state in ("done", "running", "paused", "planned")
    }
    desc = texts(
        "chart.desc",
        tasks=sum(counts.values()),
        done=counts["done"],
        running=counts["running"] + counts["paused"],
        planned=counts["planned"],
        status=texts.date(calendar.date_of(t)),
    )
    ends = [project.sink_plan]
    if project.baseline is not None:
        ends.append(project.baseline.makespan)
    return layout(rows, calendar, t, lines, days, texts("chart.title"), desc, texts, ends)


def sim_gantt(run: PolicyRun, names: Mapping[int, str], texts: Texts) -> Gantt:
    """The chart of a simulator run: the same shapes from the engine's state (spec section 11.6)."""
    world = run.world
    state = run.state
    calendar = world.calendar
    t = run.day
    starts = world.plan.schedule.starts
    rows = []
    for j in range(1, len(state.status)):
        if j == state.sink:
            continue
        name = names.get(j, str(j))
        status = state.status[j]
        duration = state.duration[j]
        original = None
        if j < len(starts):
            original = (starts[j], starts[j] + world.instance.activities[j].duration)
        start, finish = state.start[j], state.finish[j]
        actual = planned = None
        if status == REMOVED:
            shown, tip = "removed", texts("chart.tip_removed", task=name)
        elif status == DONE and start is not None and finish is not None:
            shown, actual = "done", (start, finish)
            tip = texts(
                "chart.tip_done",
                task=name,
                start=texts.date(calendar.date_of(start)),
                finish=texts.date(calendar.finish_date(finish)),
            )
        elif status in (RUNNING, PAUSED) and start is not None:
            shown = "running" if status == RUNNING else "paused"
            actual = (start, max(t, start + 1))
            total = duration * state.unit[j]
            percent = round(min(99.0, 100 * state.done[j] / total)) if total > 0 else 0
            rest = max(1, math.ceil(duration * (1 - state.done[j] / total))) if total > 0 else 1
            planned = (actual[1], actual[1] + rest)
            tip = texts(
                "chart.tip_running",
                task=name,
                start=texts.date(calendar.date_of(start)),
                percent=percent,
            )
        else:
            shown, planned = "planned", (state.plan[j], state.plan[j] + duration)
            tip = texts(
                "chart.tip_planned",
                task=name,
                start=texts.date(calendar.date_of(state.plan[j])),
                finish=texts.date(calendar.finish_date(state.plan[j] + max(1, duration))),
            )
        order = actual[0] if actual is not None else planned[0] if planned else math.inf
        rows.append((order, j, ChartRow(str(j), name, shown, original, actual, planned, tip)))
    rows.sort(key=lambda item: (item[0], item[1]))
    status_day = calendar.date_of(t)
    lines = [
        (t, "line-today", texts("chart.flag.status", date=texts.day_month(status_day))),
        (
            world.deadline,
            "line-deadline",
            texts(
                "chart.flag.deadline",
                date=texts.day_month(calendar.finish_date(world.deadline)),
            ),
        ),
    ]
    plotted = [row for _, _, row in rows]
    counts = {
        name: sum(1 for row in plotted if row.state == name)
        for name in ("done", "running", "paused", "planned")
    }
    desc = texts(
        "chart.desc",
        tasks=sum(counts.values()),
        done=counts["done"],
        running=counts["running"] + counts["paused"],
        planned=counts["planned"],
        status=texts.date(status_day),
    )
    ends = [world.plan.makespan, state.plan[state.sink]]
    return layout(plotted, calendar, t, lines, None, texts("chart.title"), desc, texts, ends)


@dataclass(frozen=True)
class Strip:
    """The forecast window strip, in per cent from today to its end (brief, section 3.3)."""

    likely: float
    bad: float
    deadline: float | None


def forecast_strip(
    today: date, likely: date, bad: date, deadline: date | None, calendar: WorkCalendar
) -> Strip:
    """Where the most likely finish, the bad case and the deadline lie on the strip, whose track
    runs from today to the later of the bad case and the deadline."""
    start = calendar.first(today)
    points = [calendar.last(value) + 1 for value in (likely, bad)]
    limit = calendar.last(deadline) + 1 if deadline is not None else None
    end = max(start + 1, points[1], *([limit] if limit is not None else []))

    def at(day: int) -> float:
        return round(max(0, day - start) / (end - start) * 100, 1)

    return Strip(at(points[0]), at(points[1]), None if limit is None else at(limit))


@dataclass(frozen=True)
class ChancePoint:
    """A point of the chart of the chance over time."""

    x: float
    y: float
    label: str
    value: str


def chance_points(values: Sequence[tuple[date, float]], texts: Texts) -> list[ChancePoint]:
    """The chance after every check-in on a 0-100 % chart, in per cent of its width and height,
    evenly spaced, one point per report (brief, section 4.6)."""
    count = len(values)
    points = []
    for i, (day, p) in enumerate(values):
        x = 50.0 if count == 1 else round(100 * i / (count - 1), 2)
        points.append(ChancePoint(x, round(100 * (1 - p), 2), texts.date(day), texts.pct(p)))
    return points
