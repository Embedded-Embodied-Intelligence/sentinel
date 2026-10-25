"""The new-project wizard (WP9b; spec section 11.2): (1) name, dates, budget and the two
presets, (2) the team, (3) the tasks, described in words (read by the AI, if one is set up),
imported from a spreadsheet or entered in a table; then the original plan.

A project exists from the end of step 1, as a draft without a plan: every later change is saved
as it is made (autosave), so a manager can leave and continue from the start page. The issues of
the definition are shown in plain language as the manager types (spec section 11.2).
"""

import json
from collections.abc import Sequence
from datetime import date
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response

from sentinel.app import io
from sentinel.app.errors import AppError
from sentinel.app.models import Person, ProjectDefinition, Task
from sentinel.app.services import JobView
from sentinel.app.ui.core import Ui, is_htmx
from sentinel.app.ui.forms import (
    Basics,
    FieldError,
    Form,
    apply_basics,
    next_key,
    pasted_people,
    read_basics,
    read_tasks,
    read_team,
    team_roles,
)
from sentinel.app.ui.pages import job_progress
from sentinel.app.ui.text import Texts
from sentinel.app.views import IssueView

STEPS = ("basics", "team", "tasks")
TABS = ("describe", "import", "manual")
ROLE_SUGGESTIONS = {
    "en": (
        "Developer",
        "Backend developer",
        "Frontend developer",
        "Tester",
        "Designer",
        "Analyst",
        "DevOps engineer",
        "Writer",
    ),
    "pl": (
        "Programista",
        "Programista backend",
        "Programista frontend",
        "Tester",
        "Projektant",
        "Analityk",
        "Inżynier DevOps",
        "Redaktor",
    ),
}


def field_errors(errors: Sequence[FieldError], texts: Texts) -> dict[str, str]:
    return {e.name: texts(e.key, **e.values) for e in errors}


def step_issues(
    issues: Sequence[IssueView], step: str, texts: Texts
) -> tuple[list[IssueView], set[int]]:
    """The issues of a wizard step in plain language, and the table rows they concern."""
    shown: list[IssueView] = []
    rows: set[int] = set()
    for issue in issues:
        where = issue.where or ""
        team = where.startswith("team[")
        if (step == "team") != team or where.startswith("roles["):
            continue
        if step == "tasks" and issue.code == "empty_project_name":
            continue
        index = _row(where)
        if index is not None:
            rows.add(index)
        if issue.code in ("empty_person_name", "empty_task_name") and index is not None:
            key = "form.person_name_missing" if team else "form.task_name_missing"
            issue = issue.model_copy(update={"message": texts(key, row=index + 1)})
        shown.append(issue)
    return shown, rows


def _row(where: str) -> int | None:
    if "[" not in where:
        return None
    text = where.split("[", 1)[1].split("]", 1)[0]
    return int(text) if text.isdigit() else None


def router(ui: Ui) -> APIRouter:
    routes = APIRouter()
    services = ui.services

    def draft(request: Request, project_id: str) -> ProjectDefinition:
        state = services.state(ui.session(request), project_id)
        if state.project.tracking:
            raise AppError("structure_frozen", "conflict")
        return state.project.definition

    def save(request: Request, project_id: str, definition: ProjectDefinition) -> None:
        current = draft(request, project_id)
        if definition != current:
            services.update_definition(
                ui.session(request), project_id, definition, ui.language(request)
            )

    def values(
        request: Request,
        step: str,
        definition: ProjectDefinition | None,
        project_id: str | None,
        **extra: Any,
    ) -> dict[str, Any]:
        texts = ui.texts(request)
        language = ui.language(request)
        issues: list[IssueView] = []
        marked: set[int] = set()
        if definition is not None and step != "basics":
            all_issues = services.validate(definition, language)
            issues, marked = step_issues(all_issues, step, texts)
        team = list(definition.team) if definition else []
        tasks = list(definition.tasks) if definition else []
        roles = team_roles(team)
        numbers = {task.key: i + 1 for i, task in enumerate(tasks)}
        names = {task.key: task.name or str(numbers[task.key]) for task in tasks}

        def crew_of(task: Task, role: str) -> str:
            from sentinel.app.live import role_key

            count = sum(c for r, c in task.crew.items() if role_key(r) == role_key(role))
            return str(count) if count else ""

        def after_numbers(task: Task) -> str:
            return ", ".join(str(numbers[p]) for p in task.predecessors if p in numbers)

        def after_names(task: Task) -> str:
            return ", ".join(names.get(p, p) for p in task.predecessors) or "—"

        def crew_text(task: Task) -> str:
            return ", ".join(f"{count} × {role}" for role, count in task.crew.items()) or "—"

        result: dict[str, Any] = {
            "title": texts("setup.title") if definition is None else definition.name,
            "nav": "projects",
            "step": step,
            "index": STEPS.index(step) + 1,
            "project_id": project_id,
            "issues": issues,
            "marked": marked,
            "team": team,
            "tasks": tasks,
            "roles": roles,
            "suggestions": _suggestions(roles, language),
            "crew_of": crew_of,
            "after_numbers": after_numbers,
            "after_names": after_names,
            "crew_text": crew_text,
            "focus": None,
            "tab": "manual",
            "cell_errors": [],
            "paste_open": False,
            "errors": {},
            "action": f"/projects/{project_id}/setup/basics" if project_id else "/new",
        }
        if definition is not None and step == "basics":
            result["basics"] = Basics(
                name=definition.name,
                start=definition.start,
                deadline=definition.deadline,
                budget=definition.budget,
                estimation=definition.settings.estimation,
                disruptions=definition.settings.disruptions,
            )
        result.update(extra)
        return result

    def render_step(
        request: Request,
        step: str,
        definition: ProjectDefinition | None,
        project_id: str | None,
        status: int = 200,
        **extra: Any,
    ) -> Response:
        context = values(request, step, definition, project_id, **extra)
        if is_htmx(request):
            return ui.page(request, f"_setup_{step}.html", status, **context)
        return ui.page(request, "setup.html", status, **context)

    @routes.get("/new")
    def new(request: Request) -> Response:
        basics = Basics(start=date.today())
        return render_step(request, "basics", None, None, basics=basics)

    @routes.post("/new")
    async def create(request: Request) -> Response:
        form = await Form.read(request)
        basics = read_basics(form)
        texts = ui.texts(request)
        if basics.errors:
            errors = field_errors(basics.errors, texts)
            return render_step(request, "basics", None, None, 422, basics=basics, errors=errors)
        definition = apply_basics(None, basics)
        definition = definition.model_copy(
            update={
                "settings": definition.settings.model_copy(
                    update={"language": ui.language(request)}
                )
            }
        )
        view = services.create(ui.session(request), definition, ui.language(request))
        return ui.redirect(request, f"/projects/{view.id}/setup/team")

    @routes.get("/projects/{project_id}/setup/{step}")
    def show(request: Request, project_id: str, step: str) -> Response:
        if step not in STEPS:
            raise AppError("not_found", "not_found")
        definition = draft(request, project_id)
        tab = request.query_params.get("tab", "manual")
        return render_step(
            request, step, definition, project_id, tab=tab if tab in TABS else "manual"
        )

    @routes.post("/projects/{project_id}/setup/basics")
    async def save_basics(request: Request, project_id: str) -> Response:
        definition = draft(request, project_id)
        form = await Form.read(request)
        basics = read_basics(form)
        if basics.errors:
            errors = field_errors(basics.errors, ui.texts(request))
            return render_step(
                request, "basics", definition, project_id, 422, basics=basics, errors=errors
            )
        save(request, project_id, apply_basics(definition, basics))
        return ui.redirect(request, f"/projects/{project_id}/setup/team")

    @routes.post("/projects/{project_id}/setup/team")
    async def save_team(request: Request, project_id: str) -> Response:
        definition = draft(request, project_id)
        form = await Form.read(request)
        action = form.get("action", "autosave")
        team = read_team(form)
        focus = None
        if action == "paste":
            team = pasted_people(form.get("paste"), team)
        elif action.startswith("remove:"):
            team = [p for p in team if p.key != action.split(":", 1)[1]]
        changed = definition.model_copy(update={"team": tuple(team)})
        save(request, project_id, changed)
        if action == "autosave":
            return autosave_status(request, changed, "team")
        if action == "back":
            return ui.redirect(request, f"/projects/{project_id}/setup/basics")
        if action == "next":
            issues = [i for i in services.validate(changed, ui.language(request))]
            shown, _ = step_issues(issues, "team", ui.texts(request))
            if not team or any(i.severity == "error" for i in shown):
                empty = [] if team else [_team_needed(ui.texts(request))]
                return render_step(
                    request, "team", changed, project_id, 422, issues=[*empty, *shown]
                )
            return ui.redirect(request, f"/projects/{project_id}/setup/tasks")
        shown_team = list(team)
        if action == "add":
            key = next_key("P", [p.key for p in team])
            shown_team.append(Person(key=key, name="", role=""))
            focus = key
        return render_step(request, "team", changed, project_id, team=shown_team, focus=focus)

    @routes.post("/projects/{project_id}/setup/tasks")
    async def save_tasks(request: Request, project_id: str) -> Response:
        definition = draft(request, project_id)
        form = await Form.read(request)
        action = form.get("action", "autosave")
        roles = team_roles(definition.team)
        rows = read_tasks(form, roles)
        tasks = rows.tasks
        texts = ui.texts(request)
        if action.startswith("remove:"):
            removed = action.split(":", 1)[1]
            tasks = [
                t.model_copy(
                    update={"predecessors": tuple(p for p in t.predecessors if p != removed)}
                )
                for t in tasks
                if t.key != removed
            ]
        changed = definition.model_copy(update={"tasks": tuple(tasks)})
        save(request, project_id, changed)
        cell_errors = [texts(e.key, **e.values) for e in rows.errors]
        if action == "autosave":
            return autosave_status(request, changed, "tasks", cell_errors)
        if action == "back":
            return ui.redirect(request, f"/projects/{project_id}/setup/team")
        if action == "finish":
            issues = services.validate(changed, ui.language(request))
            errors = [i for i in issues if i.severity == "error"]
            if errors or rows.errors:
                shown, marked = step_issues(errors, "tasks", texts)
                team_errors = [i for i in errors if (i.where or "").startswith("team[")]
                return render_step(
                    request,
                    "tasks",
                    changed,
                    project_id,
                    422,
                    issues=[*team_errors, *shown],
                    marked=marked,
                    cell_errors=cell_errors,
                )
            job = services.plan(ui.session(request), project_id, ui.language(request))
            response = job_progress(ui, request, job, "job.plan")
            response.headers["HX-Retarget"] = "#finish-area"
            response.headers["HX-Reswap"] = "innerHTML"
            return response
        shown_tasks = list(tasks)
        focus = None
        if action == "add":
            key = next_key("T", [t.key for t in tasks])
            shown_tasks.append(Task(key=key, name="", duration=0))
            focus = key
        return render_step(
            request,
            "tasks",
            changed,
            project_id,
            tasks=shown_tasks,
            focus=focus,
            cell_errors=cell_errors,
        )

    def autosave_status(
        request: Request,
        definition: ProjectDefinition,
        step: str,
        cell_errors: Sequence[str] = (),
    ) -> Response:
        issues = services.validate(definition, ui.language(request))
        shown, _ = step_issues(issues, step, ui.texts(request))
        extra = [
            IssueView(code="cell", message=e, where=None, severity="error") for e in cell_errors
        ]
        return ui.page(
            request,
            "_save_status.html",
            saved=True,
            unsaved=False,
            issues=[*extra, *shown],
            oob=True,
        )

    @routes.post("/projects/{project_id}/setup/describe")
    async def describe(request: Request, project_id: str) -> Response:
        draft(request, project_id)
        form = await Form.read(request)
        job = services.extract(ui.session(request), form.get("text"), ui.language(request))
        return job_progress(ui, request, job, "job.extract", project=project_id)

    @routes.post("/projects/{project_id}/setup/use-extraction")
    async def use_extraction(request: Request, project_id: str) -> Response:
        definition = draft(request, project_id)
        form = await Form.read(request)
        try:
            found = ProjectDefinition.model_validate(json.loads(form.get("draft")))
        except ValueError as exc:
            raise AppError("json_invalid", detail="draft") from exc
        update: dict[str, Any] = {"tasks": found.tasks}
        if not definition.team:
            update["team"] = found.team
        save(request, project_id, definition.model_copy(update=update))
        return ui.redirect(request, f"/projects/{project_id}/setup/tasks", tab="manual")

    @routes.post("/projects/{project_id}/setup/import")
    async def import_csv(request: Request, project_id: str) -> Response:
        definition = draft(request, project_id)
        form = await request.form()
        upload = form.get("file")
        limit = ui.config.limits.upload_kb * 1024
        data = b""
        if upload is not None and not isinstance(upload, str):
            data = await upload.read(limit + 1)
        if len(data) > limit:
            raise AppError("too_large", "too_large", limit=ui.config.limits.upload_kb)
        if not data:
            raise AppError("csv_empty")
        tasks, found = io.parse_tasks(data)
        if found:
            messages = [i.message for i in services_issue_views(found, request)]
            return ui.page(request, "_import_errors.html", 422, issues=messages)
        save(request, project_id, definition.model_copy(update={"tasks": tuple(tasks)}))
        return ui.redirect(
            request, f"/projects/{project_id}/setup/tasks", tab="manual", flash="imported"
        )

    def services_issue_views(found: Sequence[Any], request: Request) -> list[IssueView]:
        from sentinel.app.views import issue_views

        return issue_views(found, ui.language(request))

    return routes


def _team_needed(texts: Texts) -> IssueView:
    return IssueView(
        code="team_empty", message=texts("form.team_empty"), where=None, severity="error"
    )


def _suggestions(roles: Sequence[str], language: str) -> list[str]:
    known = {role.casefold() for role in roles}
    extra = [r for r in ROLE_SUGGESTIONS.get(language, ()) if r.casefold() not in known]
    return [*roles, *extra]


def extraction_review(ui: Ui, request: Request, view: JobView) -> Response:
    """The tasks the AI read from a description, for the manager to check and use."""
    result = view.result or {}
    definition = ProjectDefinition.model_validate(result.get("definition", {}))
    project_id = request.query_params.get("project", "")
    names = {task.key: task.name for task in definition.tasks}

    def crew_text(task: Task) -> str:
        return ", ".join(f"{count} × {role}" for role, count in task.crew.items()) or "—"

    def after_names(task: Task) -> str:
        return ", ".join(names.get(p, p) for p in task.predecessors) or "—"

    team = [f"{p.name} ({p.role})" for p in definition.team]
    return ui.page(
        request,
        "_extract_review.html",
        tasks=list(definition.tasks),
        team=team,
        issues=int(result.get("issues", 0)),
        draft=definition.model_dump_json(),
        project_id=project_id,
        crew_text=crew_text,
        after_names=after_names,
    )
