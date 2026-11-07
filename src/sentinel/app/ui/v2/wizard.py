"""The v2 wizard of a new project (docs/design/v2-spec.md, section 8.5): "Podstawy", "Zespół"
(pasted, typed or dictated), "Zadania" (a spreadsheet, words or voice read by the AI as cards to
confirm, or a table) and "Gotowe" with the chance of the plan and its budget as information.
No question about how often anyone is away: one team-wide rate from ZUS's statistics
(ADR-0034)."""

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response

from sentinel.app import io
from sentinel.app.errors import AppError
from sentinel.app.live import role_key
from sentinel.app.models import Advanced, Person, ProjectDefinition, Settings, Task
from sentinel.app.ui.core import Ui
from sentinel.app.ui.forms import Form, parse_number
from sentinel.app.ui.v2.numbers import per_hundred
from sentinel.app.ui.v2.shell import PREFIX, page, texts
from sentinel.app.ui.v2.text import TextsV2
from sentinel.app.views import ProjectView, issue_views

ABSENCE_RATE = 0.014  # lambda_A from ZUS, "Absencja chorobowa w 2025 roku" (ADR-0034)
ABSENCE_SHARE = 0.04  # the share of working days absent it means, shown in the wizard
STEPS = ("basics", "team", "tasks", "ready")
MAX_ROWS = 60
DATE_WORDS = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")


def parse_day(text: str) -> date | None:
    """A date as "31.12.2026" or "2026-12-31"."""
    text = text.strip()
    found = DATE_WORDS.fullmatch(text)
    try:
        if found:
            return date(int(found.group(3)), int(found.group(2)), int(found.group(1)))
        return date.fromisoformat(text)
    except ValueError:
        return None


def people_of(text: str) -> list[tuple[str, str]]:
    """(name, role) pairs from a pasted or dictated list: one person per line or per ";", "Name,
    role"; a dictated line of several "name, role" pairs is split into pairs."""
    pairs: list[tuple[str, str]] = []
    for line in re.split(r"[\n;]+|\.\s+", text):
        parts = [p.strip(" .") for p in re.split(r"\s*[,\t]\s*", line.strip()) if p.strip(" .")]
        if not parts:
            continue
        if len(parts) == 1:
            pairs.append((parts[0], ""))
            continue
        for i in range(0, len(parts) - 1, 2):
            pairs.append((parts[i], parts[i + 1]))
        if len(parts) % 2:
            pairs.append((parts[-1], ""))
    return [(" ".join(n.split())[:120], " ".join(r.split())[:120]) for n, r in pairs][:MAX_ROWS]


def team_text(definition: ProjectDefinition) -> str:
    return "\n".join(f"{p.name}, {p.role}" for p in definition.team)


@dataclass(frozen=True)
class Row:
    """A task in the wizard's table: its name, days, people, role, what it waits for."""

    key: str
    name: str
    days: int
    count: int
    role: str
    after: str
    optional: bool


def rows_of(definition: ProjectDefinition) -> list[Row]:
    names = {task.key: task.name for task in definition.tasks}
    rows = []
    for task in definition.tasks:
        role, count = next(iter(task.crew.items()), ("", 0))
        after = names.get(task.predecessors[0], "") if task.predecessors else ""
        rows.append(Row(task.key, task.name, task.duration, count, role, after, task.optional))
    return rows


def read_rows(form: Form, definition: ProjectDefinition) -> tuple[Task, ...]:
    """The table's tasks: one role per task, its predecessor named (spec section 11.2)."""
    names = form.getlist("t_name")
    days = form.getlist("t_days")
    counts = form.getlist("t_count")
    roles = form.getlist("t_role")
    afters = form.getlist("t_after")
    optional = set(form.getlist("t_optional"))
    old = {task.name: task for task in definition.tasks}
    tasks: list[Task] = []
    keys: dict[str, str] = {}
    for i, raw in enumerate(names[:MAX_ROWS]):
        name = " ".join(raw.split())[:120]
        if not name:
            continue
        key = old[name].key if name in old else f"T{len(keys) + 1}"
        while key in keys.values():
            key = f"T{len(keys) + 2}"
        keys[name] = key
        duration = parse_number(days[i] if i < len(days) else "") or 1
        count = int(parse_number(counts[i] if i < len(counts) else "") or 0)
        role = roles[i] if i < len(roles) else ""
        after = afters[i] if i < len(afters) else ""
        preds = (keys[after],) if after in keys and after != name else ()
        tasks.append(
            Task(
                key=key,
                name=name,
                duration=max(1, round(duration)),
                crew={role: count} if role and count else {},
                predecessors=preds,
                optional=str(i) in optional,
            )
        )
    return tuple(tasks)


def step_of(view: ProjectView) -> str:
    if view.has_plan:
        return "ready"
    if not view.definition.team:
        return "team"
    return "tasks"


def roles_of(definition: ProjectDefinition) -> list[str]:
    found: dict[str, str] = {}
    for person in definition.team:
        found.setdefault(role_key(person.role), person.role)
    return list(found.values())


def router(ui: Ui) -> APIRouter:
    routes = APIRouter()
    services = ui.services

    def live(request: Request, project_id: str) -> ProjectView:
        return services.live(ui.session(request), project_id, ui.language(request))

    def show(request: Request, step: str, view: ProjectView | None, **values: Any) -> Response:
        t = texts(request)
        return page(
            ui,
            request,
            "wizard.html",
            title=t("v2.new.title"),
            nav="projects",
            step=step,
            steps=STEPS,
            view=view,
            share=t.share(ABSENCE_SHARE),
            **values,
        )

    @routes.get(PREFIX + "/new")
    def new(request: Request) -> Response:
        return show(
            request, "basics", None, errors=[], tasks_way=request.query_params.get("tasks", "")
        )

    @routes.post(PREFIX + "/new")
    async def create(request: Request) -> Response:
        form = await Form.read(request)
        t = texts(request)
        name = " ".join(form.get("name").split())[:120]
        start = parse_day(form.get("start"))
        deadline = parse_day(form.get("deadline")) if form.get("deadline") else None
        days_off = tuple(d for line in form.get("days_off").splitlines() if (d := parse_day(line)))
        errors = []
        if not name:
            errors.append(t.msg("empty_project_name"))
        if start is None:
            errors.append(t.msg("field_invalid", field=t("v2.new.start"), detail=""))
        if deadline is not None and start is not None and deadline <= start:
            errors.append(t.msg("field_invalid", field=t("v2.new.deadline"), detail=""))
        if errors or start is None:
            return show(request, "basics", None, errors=errors, tasks_way=form.get("tasks_way"))
        settings = Settings(
            language=ui.language(request),
            advanced=Advanced(lambda_a=ABSENCE_RATE),
            days_off=days_off,
        )
        definition = ProjectDefinition(name=name, start=start, deadline=deadline, settings=settings)
        view = services.create(ui.session(request), definition, ui.language(request))
        return ui.redirect(request, f"{PREFIX}/new/{view.id}/team", tasks=form.get("tasks_way"))

    @routes.get(PREFIX + "/new/{project_id}")
    def resume(request: Request, project_id: str) -> Response:
        return ui.redirect(
            request, f"{PREFIX}/new/{project_id}/{step_of(live(request, project_id))}"
        )

    @routes.get(PREFIX + "/new/{project_id}/team")
    def team(request: Request, project_id: str) -> Response:
        view = live(request, project_id)
        return show(
            request,
            "team",
            view,
            team=team_text(view.definition),
            roles=roles_of(view.definition),
            errors=[],
            tasks_way=request.query_params.get("tasks", ""),
        )

    @routes.post(PREFIX + "/new/{project_id}/team")
    async def team_save(request: Request, project_id: str) -> Response:
        form = await Form.read(request)
        view = live(request, project_id)
        t = texts(request)
        pairs = people_of(form.get("team"))
        people = tuple(
            Person(key=f"P{i + 1}", name=name, role=role or t("v2.new.team"))
            for i, (name, role) in enumerate(pairs)
        )
        if not people:
            return show(
                request,
                "team",
                view,
                team="",
                roles=[],
                errors=[t("form.team_empty")],
                tasks_way="",
            )
        definition = view.definition.model_copy(update={"team": people})
        try:
            services.update_definition(
                ui.session(request), project_id, definition, ui.language(request)
            )
        except AppError as exc:
            return show(
                request,
                "team",
                view,
                team=form.get("team"),
                roles=[],
                errors=t.issues(exc),
                tasks_way="",
            )
        return ui.redirect(request, f"{PREFIX}/new/{project_id}/tasks", tasks=form.get("tasks_way"))

    def tasks_values(view: ProjectView) -> dict[str, Any]:
        return {
            "rows": rows_of(view.definition),
            "roles": roles_of(view.definition),
            "errors": [],
        }

    @routes.get(PREFIX + "/new/{project_id}/tasks")
    def tasks(request: Request, project_id: str) -> Response:
        view = live(request, project_id)
        return show(
            request,
            "tasks",
            view,
            tasks_way=request.query_params.get("tasks", ""),
            **tasks_values(view),
        )

    @routes.post(PREFIX + "/new/{project_id}/tasks")
    async def tasks_save(request: Request, project_id: str) -> Response:
        """The table, or the tasks confirmed from a description ("c_task" JSON cards)."""
        form = await Form.read(request)
        view = live(request, project_id)
        t = texts(request)
        confirmed = [Task.model_validate_json(v) for v in form.getlist("c_task") if v]
        found = tuple(confirmed) if confirmed else read_rows(form, view.definition)
        definition = view.definition.model_copy(update={"tasks": found})
        try:
            services.update_definition(
                ui.session(request), project_id, definition, ui.language(request)
            )
        except AppError as exc:
            values = tasks_values(view)
            values["errors"] = t.issues(exc)
            return show(request, "tasks", view, tasks_way="table", **values)
        return ui.redirect(request, f"{PREFIX}/new/{project_id}/tasks", tasks="table")

    @routes.post(PREFIX + "/new/{project_id}/import")
    async def import_sheet(request: Request, project_id: str) -> Response:
        view = live(request, project_id)
        t = texts(request)
        data = await upload(request)
        found, issues = io.parse_tasks(data)
        values = tasks_values(view)
        if issues:
            values["errors"] = [i.message for i in issue_views(issues, ui.language(request))]
            return show(request, "tasks", view, tasks_way="import", **values)
        definition = view.definition.model_copy(update={"tasks": tuple(found)})
        try:
            services.update_definition(
                ui.session(request), project_id, definition, ui.language(request)
            )
        except AppError as exc:
            values["errors"] = t.issues(exc)
            return show(request, "tasks", view, tasks_way="import", **values)
        return ui.redirect(request, f"{PREFIX}/new/{project_id}/tasks", tasks="table")

    async def upload(request: Request) -> bytes:
        form = await request.form()
        sheet = form.get("file")
        limit = ui.config.limits.upload_kb * 1024
        if sheet is None or isinstance(sheet, str) or not sheet.filename:
            raise AppError("csv_no_file")
        data = await sheet.read(limit + 1)
        if len(data) > limit:
            raise AppError("too_large", "too_large", limit=ui.config.limits.upload_kb)
        if not data:
            raise AppError("csv_empty")
        return data

    @routes.post(PREFIX + "/new/{project_id}/describe")
    async def describe(request: Request, project_id: str) -> Response:
        form = await Form.read(request)
        view = live(request, project_id)
        job = services.extract(
            ui.session(request), form.get("text"), ui.language(request), team=view.definition.team
        )
        return page(
            ui,
            request,
            "_wizard_tasks.html",
            project_id=project_id,
            job=job.id,
            cards=[],
            failed=None,
        )

    @routes.get(PREFIX + "/new/{project_id}/describe")
    def describe_poll(request: Request, project_id: str) -> Response:
        session, language = ui.session(request), ui.language(request)
        t = texts(request)
        job = services.job(session, request.query_params.get("job", ""), language)
        cards: list[tuple[str, str]] = []
        failed = None
        if job.status == "done":
            found = ProjectDefinition.model_validate((job.result or {}).get("definition", {}))
            cards = [(task.model_dump_json(), task_card(t, task, found)) for task in found.tasks]
            if not cards:
                failed = t("v2.new.no_tasks")
        elif job.status == "failed":
            failed = job.error.message if job.error is not None else t("v2.failed")
        waiting = job.status in ("queued", "running")
        return page(
            ui,
            request,
            "_wizard_tasks.html",
            project_id=project_id,
            job=job.id if waiting else None,
            cards=cards,
            failed=failed,
        )

    @routes.post(PREFIX + "/new/{project_id}/plan")
    def plan(request: Request, project_id: str) -> Response:
        session, language = ui.session(request), ui.language(request)
        services.plan(session, project_id, language)
        return ui.redirect(request, f"{PREFIX}/new/{project_id}/ready")

    @routes.get(PREFIX + "/new/{project_id}/ready")
    def ready(request: Request, project_id: str) -> Response:
        view = live(request, project_id)
        if not view.has_plan:
            running = [
                job
                for job in services.store.project_jobs(ui.session(request), project_id)
                if job.kind == "plan" and job.status in ("queued", "running")
            ]
            if not running:
                return ui.redirect(request, f"{PREFIX}/new/{project_id}/tasks")
            return show(request, "ready", view, planning=True, n=None, budget=None)
        f = services.forecast_now(ui.session(request), project_id)
        n = None if f is None or f.p_on_time is None else per_hundred(f.p_on_time)
        return show(request, "ready", view, planning=False, n=n, budget=view.budget)

    @routes.post(PREFIX + "/new/{project_id}/budget")
    async def budget(request: Request, project_id: str) -> Response:
        form = await Form.read(request)
        view = live(request, project_id)
        value = parse_number(form.get("budget"))
        if value is None or value <= 0:
            raise AppError("field_invalid", field="budget", detail=form.get("budget"))
        definition = view.definition.model_copy(update={"budget": value})
        services.update_definition(
            ui.session(request), project_id, definition, ui.language(request)
        )
        return ui.redirect(request, f"{PREFIX}/new/{project_id}/ready")

    return routes


def task_card(t: TextsV2, task: Task, definition: ProjectDefinition) -> str:
    names = {other.key: other.name for other in definition.tasks}
    crew = ", ".join(f"{count} × {role}" for role, count in task.crew.items()) or "—"
    after = ", ".join(names.get(p, p) for p in task.predecessors)
    tail = t("v2.new.task.card_after", after=after) if after else ""
    return t("v2.new.task.card", name=task.name, days=task.duration, crew=crew, after=tail)
