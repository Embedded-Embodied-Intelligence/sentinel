"""The v2 Plan (docs/design/v2-spec.md, section 8.7): "Harmonogram", the current plan as a Gantt
chart with today, the deadline and the forecast's band, the tasks of "Główne ryzyka" in amber and
absences hatched; "Zadania", every task with its state, progress, planned end, people and
dependencies, one not started yet correctable (spec section 11.2, v2.2.0); "Zespół", each
person's absences by date, current and next tasks and the plan's demand on their role next week:
workload, never performance (section 2); and the plan as CSV."""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response

from sentinel.app.errors import AppError
from sentinel.app.live import LiveProject
from sentinel.app.models import Task
from sentinel.app.ui.charts import Gantt, live_gantt
from sentinel.app.ui.core import Ui
from sentinel.app.ui.forms import Form, parse_int, team_roles
from sentinel.app.ui.v2.shell import PREFIX, header, page, texts
from sentinel.app.ui.v2.text import TextsV2
from sentinel.app.views import ForecastView, ProjectView, TaskView

VIEWS = ("schedule", "tasks", "team")
WEEK = 5
FLAG_CHAR = 8.6  # a flag character at 14 px semibold, in px (section 5: text never below 14 px)


@dataclass(frozen=True)
class TaskRow:
    """A task of "Zadania": its words and, while it has not started, its definition to correct
    (None once it started, for a task added at a report, or before the first report)."""

    key: str
    name: str
    state: str
    state_text: str
    percent: int | None
    end: date | None
    people: str
    after: str
    risk: bool
    added: bool
    task: Task | None = None


@dataclass(frozen=True)
class PersonRow:
    """A person of "Zespół": role, absences by date, current and next tasks, and the plan's
    demand on their role next week in working days (no measure of anyone's performance)."""

    key: str
    name: str
    role: str
    temporary: bool
    absences: list[str]
    now: list[str]
    next: list[str]
    busy: int | None  # working days of next week the plan needs the role, per person present
    days: int  # working days of next week the person is present
    absent_now: bool = False
    notes: list[str] = field(default_factory=list)


def end_of(task: TaskView) -> date | None:
    """A task's end: its finish, the expected one while it runs, else the planned one."""
    if task.state == "done":
        return task.finish
    if task.state in ("in_progress", "paused"):
        return task.expected_finish or task.planned_finish
    return task.planned_finish


def crew_words(t: TextsV2, crew: dict[str, int]) -> str:
    return ", ".join(t("v2.plan.crew", n=n, role=role) for role, n in crew.items())


def task_rows(
    t: TextsV2, view: ProjectView, project: LiveProject, risks: set[str]
) -> list[TaskRow]:
    """The tasks in the plan's order, the removed ones last."""
    names = {task.key: task.name for task in view.tasks}
    defined = {task.key: task for task in view.definition.tasks}
    rows = []
    for task in view.tasks:
        editable = (
            project.tracking
            and task.state == "not_started"
            and task.key in defined
            and not task.added
        )
        people = ", ".join(task.crew_names) if task.crew_names else crew_words(t, task.crew)
        rows.append(
            TaskRow(
                key=task.key,
                name=task.name,
                state=task.state,
                state_text=task.state_text,
                percent=None if task.percent is None else round(task.percent),
                end=end_of(task),
                people=people,
                after=", ".join(names.get(p, p) for p in task.predecessors),
                risk=task.key in risks,
                added=task.added,
                task=defined[task.key] if editable else None,
            )
        )
    order = {"removed": 1}
    return sorted(rows, key=lambda row: order.get(row.state, 0))


def next_week(project: LiveProject, as_of: date, weeks: int = 1) -> list[date]:
    """The working days of the `weeks` calendar weeks after `as_of` (holidays and days off
    excluded)."""
    monday = as_of + timedelta(days=7 - as_of.weekday())
    return [
        day
        for day in (monday + timedelta(days=7 * w + i) for w in range(weeks) for i in range(WEEK))
        if project.calendar.is_working(day)
    ]


def team_rows(
    t: TextsV2, view: ProjectView, project: LiveProject, today: date, weeks: int = 1
) -> tuple[list[PersonRow], list[date]]:
    """Every person with their absences, current and next tasks and the demand on their role in
    the next `weeks` weeks: for each working day, the people the active tasks need of the role
    over those of it present (at most one day a day), summed over the days the person is
    present (Plan: next week; Ludzie: the next two, v3 spec section 5)."""
    status = view.checkins[-1].date if view.checkins else view.definition.start
    as_of = max(today, status)  # the week after the latest report's, or this week's
    week = next_week(project, as_of, weeks)
    active: list[tuple[TaskView, date, date]] = []
    for task in view.tasks:
        if task.state in ("done", "removed"):
            continue
        first = task.start or task.planned_start
        last = end_of(task)
        if first is not None and last is not None:
            active.append((task, first, last))

    def present(person: Any, day: date) -> bool:
        return not any(
            a.first_day <= day and (a.return_date is None or day < a.return_date)
            for a in person.absences
        )

    rows = []
    for person in view.people:
        role = person.role
        same = [p for p in view.people if p.role == role]
        busy_share = 0.0
        days = 0
        for day in week:
            if not present(person, day):
                continue
            days += 1
            need = sum(
                task.crew.get(role, 0) for task, first, last in active if first <= day <= last
            )
            there = sum(1 for p in same if present(p, day))
            busy_share += min(1.0, need / there) if there else 0.0
        now = [
            task.name
            for task in view.tasks
            if task.state in ("in_progress", "paused") and person.name in task.crew_names
        ]
        upcoming = sorted(
            (task for task in view.tasks if task.state == "not_started" and role in task.crew),
            key=lambda task: task.planned_start or date.max,
        )
        absences = []
        for absence in person.absences:
            if absence.return_date is not None and absence.return_date <= as_of - timedelta(
                days=30
            ):
                continue  # long past
            if absence.return_date is None:
                absences.append(t("v2.plan.away_open", first=t.date(absence.first_day)))
            else:
                absences.append(
                    t(
                        "v2.plan.away",
                        first=t.date(absence.first_day),
                        back=t.date(absence.return_date),
                    )
                )
        rows.append(
            PersonRow(
                key=person.key,
                name=person.name,
                role=role,
                temporary=person.temporary,
                absences=absences,
                now=now,
                next=[task.name for task in upcoming[:2]],
                busy=round(busy_share) if week else None,
                days=days,
                absent_now=person.absent,
            )
        )
    return rows, week


def gantt_of(t: TextsV2, project: LiveProject, forecast: ForecastView | None) -> Gantt:
    """The current plan with today, the deadline, the forecast's most likely and bad-case
    finish as a band, and the tasks of "Główne ryzyka" marked (section 8.7)."""
    window = None if forecast is None else (forecast.p50, forecast.p90)
    threats = None
    if forecast is not None and forecast.drivers:
        threats = {d.task: t("v2.plan.risk_tip", name=d.name) for d in forecast.drivers}
    return live_gantt(project, t, date.today(), window, threats, flag_char=FLAG_CHAR)


def router(ui: Ui) -> APIRouter:
    routes = APIRouter()
    services = ui.services

    def values(request: Request, project_id: str, shown: str) -> dict[str, Any]:
        session, language = ui.session(request), ui.language(request)
        t = texts(request)
        view = services.live(session, project_id, language)
        state = services.state(session, project_id)
        project = state.project
        found: dict[str, Any] = {
            "title": t("v2.plan.title"),
            "nav": "projects",
            "tab": "plan",
            "project": header(ui, request, view),
            "view": view,
            "shown": shown,
            "views": VIEWS,
            "has_plan": view.has_plan,
            "tracking": project.tracking,
            "errors": {},
            "editing": None,
            "kept": None,
            "today": date.today(),
        }
        if not view.has_plan:
            return found
        forecast = services.forecast_now(session, project_id)
        waiting = False
        if forecast is not None and forecast.late and forecast.drivers is None:
            job = services.threats_job(session, project_id, language)  # "Główne ryzyka"
            waiting = job.status in ("queued", "running")
            if not waiting:
                forecast = services.forecast_now(session, project_id) or forecast
        risks = {d.task for d in (forecast.drivers or [])} if forecast is not None else set()
        found["waiting"] = waiting
        if shown == "schedule":
            found["g"] = gantt_of(t, project, forecast)
            found["forecast"] = forecast
        elif shown == "tasks":
            found["rows"] = task_rows(t, view, project, risks)
            found["roles"] = team_roles(view.definition.team)
            found["choices"] = [(task.key, task.name) for task in view.tasks]
        else:
            found["people"], found["week"] = team_rows(t, view, project, date.today())
        return found

    def view_of(request: Request) -> str:
        value = request.query_params.get("view", "schedule")
        return value if value in VIEWS else "schedule"

    @routes.get(PREFIX + "/projects/{project_id}/plan")
    def plan_page(request: Request, project_id: str) -> Response:
        found = values(request, project_id, view_of(request))
        if request.query_params.get("done") == "corrected":
            found["notice"] = {
                "tone": "good",
                "icon": "check-circle",
                "text": texts(request)("v2.plan.corrected"),
            }
        return page(ui, request, "plan.html", **found)

    @routes.get(PREFIX + "/projects/{project_id}/plan/chart")
    def chart(request: Request, project_id: str) -> Response:
        """The chart, polled while the main risks are being found."""
        found = values(request, project_id, "schedule")
        return page(ui, request, "_plan_chart.html", **found)

    @routes.post(PREFIX + "/projects/{project_id}/plan/tasks/{key}")
    async def correct(request: Request, project_id: str, key: str) -> Response:
        """A correction of a task not started yet (spec section 11.2, v2.2.0): its days, people,
        dependencies and whether it is optional; the forecast follows the new definition."""
        session, language = ui.session(request), ui.language(request)
        form = await Form.read(request)
        t = texts(request)
        project = services.state(session, project_id).project
        definition = project.definition
        task = next((task for task in definition.tasks if task.key == key), None)
        tracked = project.tasks.get(key)
        if task is None or tracked is None or tracked.state != "unstarted" or not project.tracking:
            raise AppError("invalid_request")
        errors: dict[str, str] = {}
        duration = parse_int(form.get("duration"))
        if duration is None or duration < 1:
            errors["duration"] = t("v2.plan.days_error")
        crew: dict[str, int] = {}
        for i, role in enumerate(team_roles(definition.team)):
            count = parse_int(form.get(f"crew_{i}") or "0")
            if count is None or count < 0:
                errors[f"crew_{i}"] = t("v2.plan.crew_error")
            elif count > 0:
                crew[role] = count
        keys = {other.key for other in definition.tasks} | {t.key for t in project.inserted}
        after = tuple(k for k in form.getlist("after") if k in keys and k != key)
        if not errors:
            changed = task.model_copy(
                update={
                    "duration": duration,
                    "crew": crew,
                    "predecessors": after,
                    "optional": form.flag("optional"),
                }
            )
            tasks = tuple(changed if other.key == key else other for other in definition.tasks)
            try:
                services.update_definition(
                    session, project_id, definition.model_copy(update={"tasks": tasks}), language
                )
            except AppError as exc:
                errors["form"] = " ".join(t.issues(exc))
            else:
                target = f"{PREFIX}/projects/{project_id}/plan"
                return ui.redirect(request, target, view="tasks", done="corrected")
        found = values(request, project_id, "tasks")
        found.update(errors=errors, editing=key, kept=form)
        return page(ui, request, "plan.html", 422, **found)

    return routes
