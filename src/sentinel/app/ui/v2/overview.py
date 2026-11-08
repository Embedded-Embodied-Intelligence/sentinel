"""The v2 Pulpit of a project (docs/design/v2-spec.md, sections 4 and 8.2): the verdict, the three
numbers, the pending decision in place, and below the fold the "Zapas czasu" chart, the next
seven days, the causes of the latest change and the main risks."""

import dataclasses
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response
from markupsafe import Markup

from sentinel.app.errors import AppError
from sentinel.app.events import replay
from sentinel.app.ui.core import Ui
from sentinel.app.ui.text import MINUS
from sentinel.app.ui.v2.numbers import (
    BufferPoint,
    buffer_point,
    per_hundred,
    reserve_of,
    work_share,
    zone_of,
)
from sentinel.app.ui.v2.shell import PREFIX, header, page, texts
from sentinel.app.ui.v2.status import Status, main_cause, status
from sentinel.app.ui.v2.text import TextsV2
from sentinel.app.views import ForecastView, ProjectView, RecommendationView, task_views

NOTICES = ("approved", "rejected", "postponed", "report", "adjusted", "discarded")


@dataclass(frozen=True)
class Chip:
    """An effect of a decision: its words and whether it is better (good) or worse (bad)."""

    text: str
    tone: str = "neutral"


def signed(t: TextsV2, value: float) -> str:
    """A whole change with its sign: "+2", "\u22121", "±0"."""
    number = t.money(abs(value))
    if number == "0":
        return "±0"
    return ("+" if value > 0 else MINUS) + number


def tone_of(delta: float, better_up: bool = True, eps: float = 0.0) -> str:
    if abs(delta) <= eps:
        return "neutral"
    return "good" if (delta > 0) == better_up else "bad"


def decision_chips(t: TextsV2, rec: RecommendationView, person_days: bool) -> list[Chip]:
    """The effect of a decision against no change, as the overview shows it: the chance in 100,
    the most likely end and the budget change (green ▲ better, red ▼ worse; section 8.4)."""
    before, after = rec.without, rec.with_action
    if before is None or after is None:
        return []
    first, then = per_hundred(before.p_on_time), per_hundred(after.p_on_time)
    chips = [Chip(t("v2.effect.chance", before=first, after=then), tone_of(then - first))]
    end_before = before.likely_finish or before.expected_finish
    end_after = after.likely_finish or after.expected_finish
    if end_before is not None and end_after is not None:
        moved = (end_after - end_before).days
        text = t("v2.effect.end", before=t.date(end_before), after=t.date(end_after))
        chips.append(Chip(text, tone_of(moved, better_up=False)))
    cost = after.expected_cost - before.expected_cost
    key = "v2.effect.budget" if person_days else "v2.effect.budget_units"
    chips.append(Chip(t(key, change=signed(t, cost)), tone_of(cost, better_up=False, eps=0.5)))
    return chips


def budget_end(t: TextsV2, view: ProjectView, f: ForecastView | None) -> str | None:
    """ "na koniec ok. {c} ({±p} %)": the expected cost and its difference from the budget."""
    if f is None or f.expected_cost is None or not view.budget:
        return None
    over = (f.expected_cost - view.budget) / view.budget
    share = t.share(abs(over))
    sign = "" if share.startswith("0") else ("+" if over > 0 else MINUS)
    return t("v2.budget.end", c=t.money(f.expected_cost), p=sign + share)


# --------------------------------------------------------------------------- "Zapas czasu"


@dataclass(frozen=True)
class FeverPoint:
    when: str
    point: BufferPoint
    zone: str


def fever_points(ui: Ui, request: Request, view: ProjectView) -> tuple[list[FeverPoint], int]:
    """The chart's points: the plan before the first report, then one per report; and the
    reserve of the original plan in working days (section 4; spec section 11.8)."""
    services = ui.services
    session, language = ui.session(request), ui.language(request)
    t = texts(request)
    rows = services.store.events(session, view.id)
    current = replay(rows)
    project = current.project
    deadline = project.definition.deadline
    if project.baseline is None or deadline is None:
        return [], 0
    calendar = project.calendar
    baseline_end = project.baseline.makespan
    reserve = reserve_of(calendar.deadline(deadline), baseline_end)
    if reserve <= 0:
        return [], reserve
    marks = [row.seq for row in rows if row.type == "checkin"]
    points = []
    for seq in marks:
        state = replay([row for row in rows if row.seq <= seq])
        result = services.forecast_of(view.id, state)
        if result is None:
            continue
        observation = state.project.observation()
        tasks = task_views(state.project, observation, language)
        done, total = work_share([(x.state, x.percent, x.work_total) for x in tasks])
        point = buffer_point(done, total, result.quantiles[1], baseline_end, reserve)
        when = t.date(observation_date(state))
        points.append(FeverPoint(when, point, zone_of(point)))
    return points, reserve


def observation_date(state: Any) -> date:
    checkins = state.project.checkins
    found: date = checkins[-1][0]
    return found


def tag(name: str, body: str = "", **attrs: object) -> str:
    """An SVG element; attribute names with "_" become "-" (text_anchor), values escaped."""
    words = " ".join(
        f'{key.rstrip("_").replace("_", "-")}="{escape(str(value))}"'
        for key, value in attrs.items()
    )
    return f"<{name} {words}>{body}</{name}>" if body else f"<{name} {words}/>"


def fever_svg(t: TextsV2, points: list[FeverPoint]) -> Markup:
    """The buffer-consumption chart as inline SVG: three zones, one dot per report joined by a
    line, the latest dot larger; every dot has its words as a title."""
    width, height, left, bottom, top, right = 560, 300, 76, 40, 12, 28
    plot_w, plot_h = width - left - right, height - top - bottom
    y_max = max([1.0, *(p.point.used for p in points)])
    y_max = min(2.0, y_max * 1.05) if y_max > 1 else 1.0

    def x(v: float) -> float:
        return round(left + v * plot_w, 1)

    def y(v: float) -> float:
        return round(top + plot_h - min(v, y_max) / y_max * plot_h, 1)

    def band(low: float, high: float) -> str:
        """The polygon between y = low + 2x/3 and y = high + 2x/3 inside the plot."""
        lower = [(x(v), y(max(0.0, low + 2 * v / 3))) for v in (0.0, 1.0)]
        upper = [(x(v), y(min(y_max, high + 2 * v / 3))) for v in (1.0, 0.0)]
        return " ".join(f"{a},{b}" for a, b in (*lower, *upper))

    def words(p: FeverPoint) -> str:
        return t(
            "v2.buffer.point",
            date=p.when,
            work=t.share(p.point.work),
            used=t.share(p.point.used),
            zone=t(f"v2.buffer.zone.{p.zone}"),
        )

    base, mid = top + plot_h, round(top + plot_h / 2, 1)
    parts = [
        tag("title", escape(t("v2.buffer.title")), id="fever-title"),
        tag("desc", escape("; ".join(words(p) for p in points)), id="fever-desc"),
        tag("polygon", class_="zone-good", points=band(-1.0, 0.0)),
        tag("polygon", class_="zone-warn", points=band(0.0, 1 / 3)),
        tag("polygon", class_="zone-bad", points=band(1 / 3, y_max + 1)),
        tag("line", class_="axis", x1=left, y1=base, x2=left + plot_w, y2=base),
        tag("line", class_="axis", x1=left, y1=top, x2=left, y2=base),
    ]
    for v in (0.0, 0.5, 1.0):
        label = escape(t.share(v))
        parts.append(tag("text", label, x=x(v), y=height - 20, text_anchor="middle"))
        parts.append(tag("text", label, x=left - 8, y=y(v) + 4, text_anchor="end"))
    parts.append(
        tag("text", escape(t("v2.buffer.x")), x=x(0.5), y=height - 2, text_anchor="middle")
    )
    turn = f"rotate(-90 16 {mid})"
    parts.append(
        tag("text", escape(t("v2.buffer.y")), x=16, y=mid, text_anchor="middle", transform=turn)
    )
    if points:
        line = " ".join(f"{x(p.point.work)},{y(p.point.used)}" for p in points)
        parts.append(tag("polyline", class_="path", points=line))
        for i, p in enumerate(points):
            last = i == len(points) - 1
            parts.append(
                tag(
                    "circle",
                    tag("title", escape(words(p))),
                    class_="pt-last" if last else "pt",
                    cx=x(p.point.work),
                    cy=y(p.point.used),
                    r=9 if last else 5,
                )
            )
    head = (
        f'<svg class="fever" viewBox="0 0 {width} {height}" role="img" '
        'aria-labelledby="fever-title fever-desc">'
    )
    return Markup(head + "".join(parts) + "</svg>")


def escape(text: str) -> str:
    return str(Markup.escape(text))


# --------------------------------------------------------------------------- the next 7 days


@dataclass(frozen=True)
class Upcoming:
    day: date
    text: str
    deadline: bool = False


def upcoming(t: TextsV2, view: ProjectView, today: date) -> tuple[date, list[Upcoming]]:
    """What happens in the seven days from the later of today and the day after the status
    date: absences starting and ending, tasks starting and ending, the deadline (section 8.2)."""
    first = max(today, view.as_of)
    last = first + timedelta(days=6)
    items: list[Upcoming] = []

    def add(day: date | None, text: str, deadline: bool = False) -> None:
        if day is not None and first <= day <= last:
            items.append(Upcoming(day, text, deadline))

    for person in view.people:
        for absence in person.absences:
            add(absence.first_day, t("v2.week.absence_start", name=person.name))
            add(absence.return_date, t("v2.week.absence_end", name=person.name))
    for task in view.tasks:
        if task.state == "not_started":
            add(task.planned_start, t("v2.week.task_start", name=task.name))
            add(task.planned_finish, t("v2.week.task_end", name=task.name))
        elif task.state in ("in_progress", "paused"):
            add(task.expected_finish, t("v2.week.task_end", name=task.name))
    add(view.deadline, t("v2.week.deadline"), deadline=True)
    items.sort(key=lambda item: (item.day, not item.deadline))
    return first, items


def next_report(view: ProjectView, today: date, weekday: int = 3) -> date:
    """The day of the next weekly report: the first reminder day (Thursday by default, section
    8.9) after the latest report, or the first one from today if that has passed."""
    base = view.checkins[-1].date if view.checkins else view.definition.start - timedelta(days=1)
    day = base + timedelta(days=1)
    while day.weekday() != weekday:
        day += timedelta(days=1)
    if day < today:
        day = today
        while day.weekday() != weekday:
            day += timedelta(days=1)
    return day


def reminder_day(ui: Ui, request: Request, project_id: str) -> int:
    """The weekday of the project's report reminder (Thursday unless changed, section 8.10)."""
    found = ui.services.store.calendar(ui.session(request), project_id)
    return 3 if found is None else found.reminder_day


# --------------------------------------------------------------------------- causes and risks


@dataclass(frozen=True)
class Insights:
    """The causes of the latest change and the main risks, or that they are being found."""

    waiting: bool
    since: str | None
    causes: list[str]
    risks: list[str]
    risk_note: str | None
    failed: bool = False


def insights(t: TextsV2, f: ForecastView | None, waiting: bool) -> Insights:
    if f is None:
        return Insights(False, None, [], [], None)
    since = None
    causes: list[str] = []
    if f.causes is not None:
        c = f.causes
        since = t(
            "v2.causes.since",
            date=t.date(c.reported),
            before=per_hundred(c.p_before),
            after=per_hundred(c.p_after),
        )
        for line in c.lines:
            n = per_hundred(line.p_without)
            if line.kind == "progress":
                causes.append(t("v2.causes.progress", date=t.date(c.since), n=n))
            else:
                causes.append(t(f"v2.causes.{line.kind}", name=line.name, n=n))
    risks = [t("v2.risks.item", name=d.name) for d in (f.drivers or [])]
    note = None
    if not f.late:
        note = t("v2.risks.none")
    elif f.drivers is not None and not f.drivers:
        note = t("v2.risks.spread")
    return Insights(waiting, since, causes, risks, note)


def router(ui: Ui) -> APIRouter:
    routes = APIRouter()
    services = ui.services

    def threats_waiting(request: Request, project_id: str) -> bool:
        """Whether the background job still finds the risks or the causes (spec 11.4)."""
        session, language = ui.session(request), ui.language(request)
        f = services.forecast_now(session, project_id)
        if f is None or (f.drivers is not None and not f.causes_pending):
            return False
        job = services.threats_job(session, project_id, language)
        if job.status == "failed":
            return False
        return job.status != "done"

    def pending_of(view: ProjectView) -> RecommendationView | None:
        found = [r for r in view.recommendations if r.status in ("open", "later")]
        return found[-1] if found else None

    @routes.get(PREFIX + "/projects/{project_id}")
    def overview(request: Request, project_id: str) -> Response:
        session, language = ui.session(request), ui.language(request)
        row = services.store.project(session, project_id)
        if row is None or row.kind != "live":
            raise AppError("project_not_found", "not_found")
        services.expire(session, project_id, date.today())  # spec section 11.8
        view = services.live(session, project_id, language)
        if not view.has_plan:
            return ui.redirect(request, f"{PREFIX}/new/{project_id}")
        t = texts(request)
        today = date.today()
        s: Status = status(ui, request, view, t)
        pending = pending_of(view)
        waiting = threats_waiting(request, project_id)
        f = None if s.summary is None else s.summary.forecast
        if f is not None:  # again, with what the job has found (at once with inline jobs)
            f = services.forecast_now(session, project_id) or f
            if s.cause is None and s.summary is not None:
                found = s.summary.model_copy(update={"forecast": f})
                s = dataclasses.replace(s, cause=main_cause(t, found, view), summary=found)
        points, reserve = fever_points(ui, request, view)
        first, week = upcoming(t, view, today)
        thinking = any(
            job.kind == "recommend" and job.status in ("queued", "running")
            for job in services.store.project_jobs(session, project_id)
        )
        done = request.query_params.get("done")
        return page(
            ui,
            request,
            "overview.html",
            title=view.name,
            nav="projects",
            tab="overview",
            project=header(ui, request, view),
            view=view,
            s=s,
            f=f,
            pending=pending,
            chips=[] if pending is None else decision_chips(t, pending, view.person_days),
            lifecycle=lifecycle_of(ui, request, view, pending),
            thinking=thinking,
            fever=fever_svg(t, points) if points else None,
            fever_latest=points[-1] if points else None,
            reserve=reserve,
            week=week,
            week_from=first,
            insights=insights(t, f, waiting),
            next_report=next_report(view, today, reminder_day(ui, request, project_id)),
            notice=notice_of(t, done, request),
            person_days=view.person_days,
            budget_end=budget_end(t, view, f),
        )

    @routes.get(PREFIX + "/projects/{project_id}/insights")
    def insight_block(request: Request, project_id: str) -> Response:
        """The causes and risks, polled while their background job runs."""
        t = texts(request)
        waiting = threats_waiting(request, project_id)
        f = services.forecast_now(ui.session(request), project_id)
        return page(
            ui, request, "_insights.html", insights=insights(t, f, waiting), project_id=project_id
        )

    @routes.get(PREFIX + "/projects/{project_id}/pending")
    def pending_block(request: Request, project_id: str) -> Response:
        """The pending-decision block, polled while Sentinel analyses a new report."""
        session, language = ui.session(request), ui.language(request)
        view = services.live(session, project_id, language)
        t = texts(request)
        pending = pending_of(view)
        thinking = any(
            job.kind == "recommend" and job.status in ("queued", "running")
            for job in services.store.project_jobs(session, project_id)
        )
        return page(
            ui,
            request,
            "_pending.html",
            view=view,
            pending=pending,
            chips=[] if pending is None else decision_chips(t, pending, view.person_days),
            lifecycle=lifecycle_of(ui, request, view, pending),
            thinking=thinking,
            next_report=next_report(view, date.today(), reminder_day(ui, request, project_id)),
        )

    return routes


@dataclass(frozen=True)
class Notice:
    text: str
    tone: str = "good"
    icon: str = "check-circle"


def notice_of(t: TextsV2, done: str | None, request: Request) -> Notice | None:
    """The one-line confirmation after an action (a calm notice, not a toast)."""
    if done not in NOTICES:
        return None
    if done == "postponed":
        valid = request.query_params.get("valid")
        try:
            day = date.fromisoformat(valid or "")
        except ValueError:
            return Notice(t("v2.done.postponed_open"), "info", "clock")
        return Notice(t("v2.done.postponed", date=t.date(day)), "info", "clock")
    if done in ("rejected", "discarded"):
        return Notice(t(f"v2.done.{done}"), "info", "info")
    return Notice(t(f"v2.done.{done}"))


def lifecycle_of(
    ui: Ui, request: Request, view: ProjectView, pending: RecommendationView | None
) -> Any:
    """The validity of the pending decision (section 3), None until it is known."""
    if pending is None:
        return None
    from sentinel.app.ui.v2.decision import validity_of

    return validity_of(ui, request, view, pending)
