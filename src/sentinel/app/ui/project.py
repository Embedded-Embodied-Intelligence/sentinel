"""The screens of a live project (WP9b; spec section 11): the overview with the chance of meeting
the deadline, the check-in, a recommendation with its decision, the history and the settings.

Every number shown comes from the services' views: the forecast of spec section 11.4 (cached by
the project's last change), the recommendation of spec section 11.5 with the figures of its own
simulated futures, and the event log for the history.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response

from sentinel.app.calendar import WorkCalendar
from sentinel.app.errors import AppError
from sentinel.app.events import (
    BaselineSet,
    CheckinDone,
    Decided,
    Recommended,
    Undone,
    parse,
)
from sentinel.app.live import LiveProject
from sentinel.app.models import CheckIn
from sentinel.app.services import JobView
from sentinel.app.ui.charts import forecast_strip, live_gantt
from sentinel.app.ui.core import Ui, chance_level, is_htmx
from sentinel.app.ui.forms import Form, read_checkin, read_settings, team_roles
from sentinel.app.ui.pages import job_progress, trend
from sentinel.app.ui.text import Texts
from sentinel.app.views import (
    ForecastSummary,
    ForecastView,
    ProjectView,
    RecommendationView,
    TaskView,
)

HISTORY_FILTERS = ("all", "checkins", "recommendations", "changes")
NEXT_DAYS = 10  # unstarted tasks planned within this many working days are shown at check-in
FLASHES_WITH_CHANCE = ("checkin_saved", "approved")  # toasts that add the new chance when known


def why_text(rec: RecommendationView, texts: Texts) -> str:
    """Why Sentinel recommends the action, in plain language from the figures shown with it
    (spec sections 10.4 and 11.5; the template explanation without internal terms)."""
    before = rec.without
    after = rec.with_action
    options = max(rec.options, len(rec.alternatives) + 1)
    if not rec.acts or after is None:
        if before is None:
            return texts("why.keep_plain")
        if rec.reason == "needs_met":
            return texts("why.on_track", p=texts.pct(before.p_on_time))
        kept = texts("why.keep", options=options, p=texts.pct(before.p_on_time))
        return kept if rec.tie is None else f"{kept} {texts.tie(rec.tie, rec.reason)}"
    parts = []
    if before is not None:
        parts.append(texts("why.without", p=texts.pct(before.p_on_time)))
    parts.append(
        texts(
            "why.with" if rec.compared else "why.with_own",
            options=options,
            futures=after.rollouts,
            p=texts.pct(after.p_on_time),
        )
    )
    if after.tardiness >= 0.05:
        parts.append(texts("why.delay", days=texts.decimal(after.tardiness)))
    if rec.tie is None:
        parts.append(texts("why.reason", reason=rec.reason_text))
    runner = next((a for a in rec.alternatives if a.runner_up), None)
    if runner is not None:
        title = texts("rec.alt_noop") if runner.label == "NOOP" else runner.title
        parts.append(texts("why.runner", title=title, p=texts.pct(runner.p_on_time)))
    if rec.tie is not None:
        parts.append(texts.tie(rec.tie, rec.reason))
    return " ".join(parts)


@dataclass(frozen=True)
class Chip:
    """An effect of a recommendation: its label, the change in words and whether it is good."""

    label: str
    text: str
    tone: str = "neutral"  # good, bad, neutral


def impact_chips(rec: RecommendationView, texts: Texts) -> list[Chip]:
    """The effect of the action against no change (spec section 11.5): the chance of meeting
    the deadline, the expected finish date, the expected cost and the tasks whose dates move."""
    before, after = rec.without, rec.with_action
    chips: list[Chip] = []
    if before is None:
        return chips
    if after is None or not rec.acts:
        chips.append(Chip(texts("chip.chance"), texts.pct(before.p_on_time)))
        if before.expected_finish is not None:
            chips.append(Chip(texts("chip.finish"), texts.date(before.expected_finish)))
        return chips
    delta = after.p_on_time - before.p_on_time
    tone = "good" if delta > 0.005 else "bad" if delta < -0.005 else "neutral"
    chips.append(
        Chip(
            texts("chip.chance"),
            texts(
                "chip.from_to", before=texts.pct(before.p_on_time), after=texts.pct(after.p_on_time)
            ),
            tone,
        )
    )
    if before.expected_finish is not None and after.expected_finish is not None:
        moved = (after.expected_finish - before.expected_finish).days
        tone = "good" if moved < 0 else "bad" if moved > 0 else "neutral"
        text = texts(
            "chip.from_to",
            before=texts.date(before.expected_finish),
            after=texts.date(after.expected_finish),
        )
        chips.append(Chip(texts("chip.finish"), text, tone))
    cost = after.expected_cost - before.expected_cost
    tone = "bad" if cost > 0.5 else "good" if cost < -0.5 else "neutral"
    chips.append(Chip(texts("chip.cost"), texts.cost_change(cost, rec.budget), tone))
    moved_tasks = len(rec.changes)
    chips.append(
        Chip(texts("chip.moved"), texts.plural("chip.tasks", moved_tasks) if moved_tasks else "–")
    )
    return chips


@dataclass(frozen=True)
class Gap:
    """How far a forecast finish lies from the deadline, in words, with its status."""

    text: str
    tone: str  # good, warn, bad, neutral
    icon: str


def finish_gap(
    finish: date, deadline: date | None, calendar: WorkCalendar, texts: Texts, worst: bool = False
) -> Gap | None:
    """The sub-line of a finish date's tile: working days before or after the deadline; the bad
    case's lateness counts as a problem, the most likely finish's as a warning."""
    if deadline is None:
        return None
    days = calendar.last(finish) - calendar.last(deadline)
    if days == 0:
        return Gap(texts("overview.gap_on"), "neutral", "minus")
    span = texts.plural("overview.days", abs(days))
    if days < 0:
        return Gap(texts("overview.gap_before", days=span), "good", "check")
    text = texts("overview.gap_after", days=span)
    return Gap(text, "bad", "cross-circle") if worst else Gap(text, "warn", "alert")


@dataclass(frozen=True)
class Threat:
    """A task that threatens the deadline: its sentence (spec sections 11.4, 11.7) and share."""

    task: str
    text: str
    percent: int


def threats_of(forecast: ForecastView, texts: Texts, limit: int = 3) -> list[Threat]:
    """The tasks shown as threats: the highest shares, at least one in twenty late futures."""
    shown = [d for d in forecast.drivers if d.share >= 0.05][:limit]
    found = []
    for driver in shown:
        count = texts.tenths(driver.share)
        if driver.share >= 1:
            text = texts("overview.driver_all", task=driver.name)
        elif count >= 10:
            text = texts("overview.driver_nearly", task=driver.name)
        else:
            text = texts("overview.driver", task=driver.name, count=count)
        found.append(Threat(driver.task, text, round(100 * driver.share)))
    return found


def split_pending(
    pending: list[RecommendationView],
) -> tuple[list[RecommendationView], list[RecommendationView]]:
    """The decisions in the first layer and those behind "other proposals": what can wait folds
    unless nothing else is waiting (docs/design/brief.md, section 3.6)."""
    urgent = [r for r in pending if not r.can_wait]
    waiting = [r for r in pending if r.can_wait]
    if not urgent and waiting:
        return waiting[:1], waiting[1:]
    return urgent, waiting


def toast_text(kind: str, summary: ForecastSummary | None, texts: Texts) -> str | None:
    """The toast of a saved check-in or an approval once the new forecast is known."""
    if summary is None or summary.forecast.p_on_time is None:
        return None
    now = texts.pct(summary.forecast.p_on_time)
    if kind == "checkin_saved" and summary.previous_p is not None:
        return texts("flash.checkin_chance", before=texts.pct(summary.previous_p), after=now)
    if kind == "approved":
        return texts("flash.approved_chance", after=now)
    return None


@dataclass
class HistoryItem:
    """An entry of the project's history."""

    kind: str  # checkin, recommendation, decision, change
    when: str
    title: str
    lines: list[str] = field(default_factory=list)
    href: str | None = None
    status: str | None = None


def history(ui: Ui, request: Request, project_id: str, view: ProjectView) -> list[HistoryItem]:
    """The project's history from its event log, newest first (spec section 11.5)."""
    texts = ui.texts(request)
    services = ui.services
    session = ui.session(request)
    state = services.state(session, project_id)
    project = state.project
    names = {key: node.name for key, node in project.nodes().items()}
    people = {p.key: p.name for p in project.definition.team}
    titles = {r.seq: r for r in view.recommendations}
    items: list[HistoryItem] = []
    previous = ""
    for row in services.store.events(session, project_id):
        stamp = texts.moment(row.created)
        event = parse(row)
        if row.type == "definition" and previous == "definition":
            continue  # consecutive edits (autosave) are one change
        previous = row.type
        match event:
            case CheckinDone():
                items.append(checkin_item(event.checkin, project, names, people, texts))
            case Recommended():
                rec = titles.get(row.seq)
                if rec is None:
                    continue
                title = rec.title
                status = rec.status_text
                items.append(
                    HistoryItem(
                        "recommendation",
                        texts.date(rec.date),
                        texts("history.recommendation", title=title),
                        [texts("history.status", status=status)],
                        f"/projects/{project_id}/recommendations/{rec.seq}",
                        rec.status,
                    )
                )
            case Decided():
                rec = titles.get(event.recommendation)
                title = rec.title if rec else "?"
                key = (
                    "history.discarded"
                    if event.verdict == "approve" and event.discarded is not None
                    else f"history.verdict.{event.verdict}"
                )
                when = texts.date(rec.date) if rec else stamp
                items.append(HistoryItem("decision", when, texts(key, title=title)))
            case Undone():
                rec = titles.get(event.recommendation)
                when = texts.date(rec.date) if rec else stamp
                title = rec.title if rec else "?"
                items.append(HistoryItem("change", when, texts("history.undone", title=title)))
            case BaselineSet():
                finish = project.calendar.finish_date(event.baseline.makespan)
                items.append(
                    HistoryItem("change", stamp, texts("history.plan", date=texts.date(finish)))
                )
            case _:
                if row.type == "created":
                    items.append(HistoryItem("change", stamp, texts("history.created")))
                elif row.type == "definition":
                    items.append(HistoryItem("change", stamp, texts("history.definition")))
                elif row.type == "explanation":
                    items.append(HistoryItem("recommendation", stamp, texts("history.explanation")))
    items.reverse()
    return items


def checkin_item(
    checkin: CheckIn,
    project: LiveProject,
    names: dict[str, str],
    people: dict[str, str],
    texts: Texts,
) -> HistoryItem:
    lines = []
    for report in checkin.tasks:
        name = names.get(report.task, report.task)
        if report.status == "done":
            finish = texts.date(report.finish) if report.finish else "?"
            lines.append(texts("history.task_done", task=name, date=finish))
        elif report.status == "in_progress":
            lines.append(
                texts("history.task_progress", task=name, percent=round(report.percent or 0))
            )
    for absence in checkin.absences:
        who = people.get(absence.person, absence.person)
        if absence.return_date is not None:
            lines.append(
                texts(
                    "history.away_back",
                    person=who,
                    first=texts.date(absence.first_day),
                    back=texts.date(absence.return_date),
                )
            )
        else:
            lines.append(texts("history.away", person=who, first=texts.date(absence.first_day)))
    for increase in checkin.increases:
        name = names.get(increase.task, increase.task)
        if increase.extra_days is not None:
            lines.append(
                texts("history.grows_days", task=name, days=texts.decimal(increase.extra_days))
            )
        else:
            percent = round(100 * ((increase.factor or 1.0) - 1))
            lines.append(texts("history.grows_factor", task=name, percent=percent))
    for added in checkin.new_tasks:
        lines.append(texts("history.new_task", task=added.name, days=added.duration))
    if not lines:
        lines.append(texts("history.nothing"))
    return HistoryItem(
        "checkin",
        texts.date(checkin.date),
        texts("history.checkin", date=texts.date(checkin.date)),
        lines,
    )


def shown_tasks(view: ProjectView) -> tuple[list[TaskView], list[TaskView]]:
    """The tasks a check-in asks about: those in progress and the next ones (unstarted tasks
    whose predecessors are done or in progress, or planned within NEXT_DAYS working days); the
    other unstarted tasks are offered behind "show all"."""
    state = {task.key: task.state for task in view.tasks}
    first: list[TaskView] = []
    rest: list[TaskView] = []
    for task in view.tasks:
        if task.state in ("done", "removed"):
            continue
        if task.state in ("in_progress", "paused"):
            first.append(task)
            continue
        ready = all(state.get(p) in ("done", "in_progress", "paused") for p in task.predecessors)
        soon = (
            task.planned_start is not None
            and (task.planned_start - view.as_of).days <= NEXT_DAYS * 7 // 5
        )
        (first if ready or soon else rest).append(task)
    return first, rest


def router(ui: Ui) -> APIRouter:
    routes = APIRouter()
    services = ui.services

    def live(request: Request, project_id: str) -> ProjectView:
        return services.live(ui.session(request), project_id, ui.language(request))

    def chart_html(
        request: Request, project: LiveProject, forecast: ForecastView | None = None
    ) -> str:
        """The chart of a project; with the forecast also its window and threats."""
        texts = ui.texts(request)
        window = None if forecast is None else (forecast.p50, forecast.p90)
        threats = None
        if forecast is not None and forecast.late:
            threats = {threat.task: threat.text for threat in threats_of(forecast, texts)}
        model = live_gantt(project, texts, date.today(), window, threats)
        return ui.render(request, "_gantt.html", {"g": model})

    @routes.get("/projects/{project_id}")
    def overview(request: Request, project_id: str) -> Response:
        session = ui.session(request)
        row = services.store.project(session, project_id)
        if row is None:
            raise AppError("project_not_found", "not_found")
        if row.kind == "simulator":
            from sentinel.app.ui.sim import simulation_page

            return simulation_page(ui, request, project_id)
        view = live(request, project_id)
        if not view.has_plan:
            step = "tasks" if view.definition.team else "team"
            return ui.redirect(request, f"/projects/{project_id}/setup/{step}")
        state = services.state(session, project_id)
        flash = request.query_params.get("flash")
        running = services.store.project_jobs(session, project_id)
        job = next((j for j in running if j.kind == "recommend"), None)
        open_recs = [r for r in view.recommendations if r.status in ("open", "later")]
        urgent, waiting = split_pending(open_recs)
        auto = checked = None
        latest = view.recommendations[-1] if view.recommendations else None
        if latest is not None and latest.status == "auto":
            auto = latest
        if latest is not None and latest.status == "none" and view.checkins:
            checked = latest if latest.date > view.checkins[-1].date else None
        away = [p for p in view.people if p.absent]
        late = [t for t in view.tasks if t.late]
        return ui.page(
            request,
            "overview.html",
            title=view.name,
            nav="projects",
            view=view,
            tab="overview",
            pending=open_recs,
            urgent=urgent,
            waiting=waiting,
            flash_key=flash if flash in FLASHES_WITH_CHANCE else None,
            auto=auto,
            checked=checked,
            away=away,
            late=late,
            job=None if job is None else services.job(session, job.id, ui.language(request)),
            chart=chart_html(request, state.project),
            chips=impact_chips,
        )

    @routes.get("/projects/{project_id}/forecast")
    def forecast(request: Request, project_id: str) -> Response:
        """The forecast block of the overview (loaded after the page; spec section 11.4)."""
        view = live(request, project_id)
        try:
            summary = services.forecast_summary(
                ui.session(request), project_id, ui.language(request)
            )
        except AppError as exc:
            texts = ui.texts(request)
            return ui.page(
                request,
                "_forecast.html",
                summary=None,
                view=view,
                failed=texts.error(exc),
                level="neutral",
                delta=None,
            )
        texts = ui.texts(request)
        state = services.state(ui.session(request), project_id)
        calendar = state.project.calendar
        f = None if summary is None else summary.forecast
        p = None if f is None else f.p_on_time
        values: dict[str, Any] = {}
        if f is not None:
            dated = [
                (view.as_of, texts("strip.today")),
                (f.p50, texts("strip.likely", date=texts.day_month(f.p50))),
            ]
            if f.deadline is not None:
                dated.append(
                    (f.deadline, texts("strip.deadline", date=texts.day_month(f.deadline)))
                )
            dated.append((f.p90, texts("strip.bad", date=texts.day_month(f.p90))))
            values = {
                "strip": forecast_strip(view.as_of, f.p50, f.p90, f.deadline, calendar),
                "strip_labels": [label for _, label in sorted(dated, key=lambda item: item[0])],
                "likely_gap": finish_gap(f.p50, f.deadline, calendar, texts),
                "bad_gap": finish_gap(f.p90, f.deadline, calendar, texts, worst=True),
                "threats": threats_of(f, texts),
                "chart": chart_html(request, state.project, f),
            }
        checkins = view.checkins
        since = (
            texts("trend.since_checkin", date=texts.date(checkins[-2].date))
            if len(checkins) > 1
            else texts("trend.since_plan")
        )
        toast = request.query_params.get("toast", "")
        return ui.page(
            request,
            "_forecast.html",
            summary=summary,
            view=view,
            failed=None,
            level=chance_level(p),
            delta=trend(summary),
            since=since,
            nav_level="decision" if state.open is not None else chance_level(p),
            toast=toast_text(toast, summary, texts),
            **values,
        )

    @routes.post("/projects/{project_id}/ask")
    def ask(request: Request, project_id: str) -> Response:
        job = services.recommend(ui.session(request), project_id, ui.language(request))
        return job_progress(ui, request, job, "job.recommend")

    # ---- check-in

    def checkin_values(request: Request, project_id: str, form: Form | None) -> dict[str, Any]:
        view = live(request, project_id)
        first, rest = shown_tasks(view)
        roles = team_roles(view.definition.team)
        today = date.today()
        last = view.checkins[-1].date if view.checkins else None
        default = max(today, last or today, view.definition.start)

        def fv(name: str, fallback: object = "") -> object:
            """The value the manager entered (after a refused submit), else `fallback`."""
            return form.get(name, str(fallback)) if form is not None else fallback

        def fl(name: str) -> list[str]:
            return form.getlist(name) if form is not None else []

        def crew_text(task: TaskView) -> str:
            return ", ".join(f"{count} × {role}" for role, count in task.crew.items() if count)

        def role_needed(task: TaskView, role: str) -> bool:
            from sentinel.app.live import role_key

            return any(role_key(r) == role_key(role) and n > 0 for r, n in task.crew.items())

        return {
            "fv": fv,
            "fl": fl,
            "crew_text": crew_text,
            "role_needed": role_needed,
            "title": ui.texts(request)("checkin.title"),
            "nav": "projects",
            "view": view,
            "tab": "checkin",
            "first": first,
            "rest": rest,
            "roles": roles,
            "people": [p for p in view.people if not p.temporary],
            "running": [t for t in view.tasks if t.state in ("in_progress", "paused")],
            "open_tasks": [t for t in view.tasks if t.state not in ("done", "removed")],
            "default_date": default,
            "last": last,
            "form": form,
            "errors": {},
            "issues": [],
        }

    @routes.get("/projects/{project_id}/checkin")
    def checkin_page(request: Request, project_id: str) -> Response:
        values = checkin_values(request, project_id, None)
        if values["view"].finished:
            return ui.redirect(request, f"/projects/{project_id}")
        return ui.page(request, "checkin.html", **values)

    @routes.post("/projects/{project_id}/checkin")
    async def checkin_save(request: Request, project_id: str) -> Response:
        form = await Form.read(request)
        view = live(request, project_id)
        current = {
            t.key: (t.state if t.state != "paused" else "in_progress", t.percent)
            for t in view.tasks
        }
        read = read_checkin(form, current)
        texts = ui.texts(request)
        if read.checkin is None:
            values = checkin_values(request, project_id, form)
            values["errors"] = {e.name: texts(e.key, **e.values) for e in read.errors}
            return checkin_form(request, values, 422)
        try:
            result = services.checkin(
                ui.session(request), project_id, read.checkin, ui.language(request)
            )
        except AppError as exc:
            values = checkin_values(request, project_id, form)
            values["issues"] = texts.issues(exc)
            return checkin_form(request, values, 422)
        del result
        return ui.redirect(request, f"/projects/{project_id}", flash="checkin_saved")

    def checkin_form(request: Request, values: dict[str, Any], status: int) -> Response:
        if is_htmx(request):
            return ui.page(request, "_checkin_form.html", status, **values)
        return ui.page(request, "checkin.html", status, **values)

    @routes.post("/projects/{project_id}/checkin/message")
    async def read_message(request: Request, project_id: str) -> Response:
        form = await Form.read(request)
        when = form.get("date")
        try:
            day = date.fromisoformat(when)
        except ValueError:
            day = date.today()
        job = services.read_message(
            ui.session(request), project_id, form.get("message"), day, ui.language(request)
        )
        return job_progress(ui, request, job, "job.message", project=project_id)

    # ---- recommendations

    def recommendation(
        request: Request, project_id: str, seq: int
    ) -> tuple[ProjectView, RecommendationView]:
        view = live(request, project_id)
        rec = next((r for r in view.recommendations if r.seq == seq), None)
        if rec is None:
            raise AppError("recommendation_not_found", "not_found")
        return view, rec

    @routes.get("/projects/{project_id}/recommendations/{seq}")
    def recommendation_page(request: Request, project_id: str, seq: int) -> Response:
        view, rec = recommendation(request, project_id, seq)
        texts = ui.texts(request)
        return ui.page(
            request,
            "recommendation.html",
            title=texts("rec.title"),
            nav="projects",
            view=view,
            tab="overview",
            rec=rec,
            chips=impact_chips(rec, texts),
            why=why_text(rec, texts),
            autonomy=view.definition.settings.autonomy,
        )

    @routes.post("/projects/{project_id}/recommendations/{seq}/decision")
    async def decide(request: Request, project_id: str, seq: int) -> Response:
        form = await Form.read(request)
        verdict = form.get("verdict")
        if verdict not in ("approve", "reject", "later"):
            raise AppError("field_invalid", field="verdict", detail=verdict)
        after = services.decide(ui.session(request), project_id, seq, verdict, ui.language(request))  # type: ignore[arg-type]
        entry = next((r for r in after.recommendations if r.seq == seq), None)
        flash = {"approve": "approved", "reject": "rejected", "later": "later"}[verdict]
        if entry is not None and entry.status == "discarded":
            flash = "discarded"
        return ui.redirect(request, f"/projects/{project_id}", flash=flash)

    @routes.post("/projects/{project_id}/recommendations/{seq}/undo")
    def undo(request: Request, project_id: str, seq: int) -> Response:
        services.undo(ui.session(request), project_id, seq, ui.language(request))
        return ui.redirect(request, f"/projects/{project_id}", flash="undone")

    @routes.post("/projects/{project_id}/recommendations/{seq}/explain")
    def explain(request: Request, project_id: str, seq: int) -> Response:
        job = services.explain(ui.session(request), project_id, seq, ui.language(request))
        return job_progress(
            ui, request, job, "job.explain", next=f"/projects/{project_id}/recommendations/{seq}"
        )

    # ---- history

    @routes.get("/projects/{project_id}/history")
    def history_page(request: Request, project_id: str) -> Response:
        view = live(request, project_id)
        show = request.query_params.get("show", "all")
        show = show if show in HISTORY_FILTERS else "all"
        items = history(ui, request, project_id, view)
        kinds = {
            "checkins": ("checkin",),
            "recommendations": ("recommendation", "decision"),
            "changes": ("change",),
        }
        if show != "all":
            items = [i for i in items if i.kind in kinds[show]]
        return ui.page(
            request,
            "history.html",
            title=ui.texts(request)("history.title"),
            nav="projects",
            view=view,
            tab="history",
            items=items,
            show=show,
            filters=HISTORY_FILTERS,
        )

    # ---- settings, exports, deletion

    def settings_values(request: Request, project_id: str) -> dict[str, Any]:
        view = live(request, project_id)
        roles = team_roles(view.definition.team)
        from sentinel.app.live import role_key

        costs = {role_key(c.role): c.daily_cost for c in view.definition.roles}
        return {
            "title": ui.texts(request)("psettings.title"),
            "nav": "projects",
            "view": view,
            "tab": "settings",
            "roles": roles,
            "cost_of": lambda role: costs.get(role_key(role), 1.0),
            "errors": {},
        }

    @routes.get("/projects/{project_id}/settings")
    def settings_page(request: Request, project_id: str) -> Response:
        return ui.page(request, "project_settings.html", **settings_values(request, project_id))

    @routes.post("/projects/{project_id}/settings")
    async def settings_save(request: Request, project_id: str) -> Response:
        form = await Form.read(request)
        values = settings_values(request, project_id)
        view: ProjectView = values["view"]
        read = read_settings(form, view.definition, values["roles"])
        texts = ui.texts(request)
        if read.definition is None:
            values["errors"] = {e.name: texts(e.key, **e.values) for e in read.errors}
            return ui.page(request, "project_settings.html", 422, **values)
        services.update_definition(
            ui.session(request), project_id, read.definition, ui.language(request)
        )
        return ui.redirect(request, f"/projects/{project_id}/settings", flash="settings_saved")

    @routes.post("/projects/{project_id}/report")
    def report(request: Request, project_id: str) -> Response:
        job = services.cockpit(ui.session(request), project_id, ui.language(request))
        return _job(request, job, "job.cockpit")

    def _job(request: Request, job: JobView, label: str) -> Response:
        return job_progress(ui, request, job, label)

    @routes.get("/projects/{project_id}/delete")
    def delete_page(request: Request, project_id: str) -> Response:
        row = services.store.project(ui.session(request), project_id)
        if row is None:
            raise AppError("project_not_found", "not_found")
        return ui.page(
            request,
            "delete.html",
            title=ui.texts(request)("delete.title"),
            nav="projects",
            name=row.name,
            project_id=project_id,
        )

    @routes.post("/projects/{project_id}/delete")
    def delete(request: Request, project_id: str) -> Response:
        services.delete(ui.session(request), project_id)
        return ui.redirect(request, "/", flash="deleted")

    return routes


def message_review(ui: Ui, request: Request, view: JobView) -> Response:
    """The events the AI read from a check-in message, each to confirm (spec section 10.2)."""
    from sentinel.app.llm import MessageDraft

    result = view.result or {}
    found = MessageDraft.model_validate(result)
    project_id = request.query_params.get("project", "")
    state = ui.services.state(ui.session(request), project_id)
    names = {key: node.name for key, node in state.project.nodes().items()}
    people = {p.key: p.name for p in state.project.definition.team}
    return ui.page(
        request,
        "_message_review.html",
        found=found,
        names=names,
        people=people,
    )
