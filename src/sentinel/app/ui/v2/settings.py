"""The v2 Ustawienia (docs/design/v2-spec.md, section 8.10). Application: "Wygląd" (light by
default, dark, system), "Język" and "Model AI" in plain words, the cloud (recommended, more
accurate) or a local model (the data stay in the company, slower), whose keys are set only in an
installed copy, never in the demo. Project: the basics, the team, the company's days off, the
calendar (section 8.9), the weekly report reminder, the exports, the fixed text on how Sentinel
decides (section 3) and "Usuń projekt" in a red zone, with a confirmation."""

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response

from sentinel.app.errors import AppError
from sentinel.app.llm import LlmSettingsUpdate
from sentinel.app.models import MAX_DAYS_OFF
from sentinel.app.store import CalendarRow
from sentinel.app.ui.core import Ui
from sentinel.app.ui.forms import Form, parse_date, parse_number, text_of
from sentinel.app.ui.v2.calendar import link_of
from sentinel.app.ui.v2.shell import PREFIX, THEMES, header, page, texts
from sentinel.app.views import ProjectView

CHOICES = ("cloud", "local", "none")  # "Chmura (zalecany)", "Lokalny", none
CLOUD = ("openrouter", "groq")
WEEKDAYS = (0, 1, 2, 3, 4)
TIME = re.compile(r"^([01][0-9]|2[0-3]):([0-5][0-9])$")


def choice_of(provider: str) -> str:
    """The plain-language choice of a provider."""
    if provider in CLOUD:
        return "cloud"
    return "local" if provider == "ollama" else "none"


@dataclass(frozen=True)
class Basics:
    """What "Podstawy" holds: the name, the deadline and the budget, and what to correct."""

    name: str
    deadline: date | None
    budget: float | None
    errors: dict[str, str]


def calendar_of(ui: Ui, request: Request, project_id: str) -> CalendarRow:
    found = ui.services.store.calendar(ui.session(request), project_id)
    if found is None:
        raise AppError("project_not_found", "not_found")
    return found


def router(ui: Ui) -> APIRouter:
    routes = APIRouter()
    services = ui.services

    # ---- the application

    def app_page(request: Request, status: int = 200, **values: Any) -> Response:
        t = texts(request)
        view = services.llm.view()
        return page(
            ui,
            request,
            "settings.html",
            status,
            title=t("v2.settings.title"),
            nav="settings",
            llm=view,
            choice=choice_of(view.provider),
            choices=CHOICES,
            themes_all=THEMES,
            saved=request.query_params.get("done") == "saved",
            **values,
        )

    @routes.get(PREFIX + "/settings")
    def app_settings(request: Request) -> Response:
        return app_page(request)

    @routes.post(PREFIX + "/settings/ai")
    async def save_ai(request: Request) -> Response:
        """The model in plain words; the keys only outside the demo, never shown again."""
        if ui.config.demo:
            raise AppError("demo_forbidden", "forbidden")
        form = await Form.read(request)
        choice = form.get("choice", "none")
        if choice not in CHOICES:
            raise AppError("field_invalid", field="choice", detail=choice)
        current = services.llm.view()
        if choice == "cloud":
            provider = current.provider if current.provider in CLOUD else "openrouter"
        else:
            provider = "ollama" if choice == "local" else "none"
        key = form.get("api_key", "").strip()
        groq = form.get("groq_key", "").strip()
        host = current.host
        if choice == "local":
            host = form.get("host", "").strip() or None
        change = LlmSettingsUpdate(
            provider=provider,
            model=current.model if provider == current.provider else None,
            host=host,
            api_key="" if form.flag("forget_key") else (key or None),
            groq_key="" if form.flag("forget_groq_key") else (groq or None),
        )
        services.llm.update(change)
        return ui.redirect(request, f"{PREFIX}/settings", done="saved")

    # ---- the project

    def project_values(request: Request, project_id: str) -> dict[str, Any]:
        session, language = ui.session(request), ui.language(request)
        t = texts(request)
        view = services.live(session, project_id, language)
        project = services.state(session, project_id).project
        return {
            "title": t("v2.tab.settings"),
            "nav": "projects",
            "tab": "settings",
            "project": header(ui, request, view),
            "view": view,
            "tracking": project.tracking,
            "calendar": calendar_of(ui, request, project_id),
            "calendar_link": link_of(ui, request, calendar_of(ui, request, project_id)),
            "weekdays": WEEKDAYS,
            "errors": {},
            "kept": None,
            "open_delete": False,
        }

    def project_page(
        request: Request, project_id: str, status: int = 200, **values: Any
    ) -> Response:
        found = project_values(request, project_id)
        found.update(values)
        done = request.query_params.get("done")
        if done in ("basics", "days_off", "reminder", "calendar", "revoked", "assessment"):
            found["notice"] = {
                "tone": "good",
                "icon": "check-circle",
                "text": texts(request)(f"v2.psettings.saved.{done}"),
            }
        return page(ui, request, "project_settings.html", status, **found)

    @routes.get(PREFIX + "/projects/{project_id}/settings")
    def project_settings(request: Request, project_id: str) -> Response:
        return project_page(request, project_id)

    def saved(request: Request, project_id: str, what: str) -> Response:
        return ui.redirect(request, f"{PREFIX}/projects/{project_id}/settings", done=what)

    def read_basics(form: Form, view: ProjectView, t: Any) -> Basics:
        errors: dict[str, str] = {}
        name = text_of(form, "name")
        if not name:
            errors["name"] = t("form.name_required")
        deadline = None
        if form.get("deadline").strip():
            deadline = parse_date(form.get("deadline"))
            if deadline is None:
                errors["deadline"] = t("form.date_invalid")
            elif deadline < view.definition.start:
                errors["deadline"] = t("form.deadline_before_start")
        budget = None
        if form.get("budget").strip():
            budget = parse_number(form.get("budget"))
            if budget is None or budget <= 0:
                errors["budget"] = t("form.budget_positive")
                budget = None
        return Basics(name, deadline, budget, errors)

    @routes.post(PREFIX + "/projects/{project_id}/settings/basics")
    async def save_basics(request: Request, project_id: str) -> Response:
        session, language = ui.session(request), ui.language(request)
        form = await Form.read(request)
        t = texts(request)
        view = services.live(session, project_id, language)
        read = read_basics(form, view, t)
        if not read.errors:
            changed = view.definition.model_copy(
                update={"name": read.name, "deadline": read.deadline, "budget": read.budget}
            )
            try:
                services.update_definition(session, project_id, changed, language)
            except AppError as exc:
                read.errors["basics"] = " ".join(t.issues(exc))
            else:
                return saved(request, project_id, "basics")
        return project_page(request, project_id, 422, errors=read.errors, kept=form)

    @routes.post(PREFIX + "/projects/{project_id}/settings/days-off")
    async def save_days_off(request: Request, project_id: str) -> Response:
        """A company day off added or removed (spec section 11.1), until the first report: the
        project's calendar is fixed from then on."""
        session, language = ui.session(request), ui.language(request)
        form = await Form.read(request)
        t = texts(request)
        view = services.live(session, project_id, language)
        days = set(view.definition.settings.days_off)
        day = parse_date(form.get("day"))
        errors: dict[str, str] = {}
        if day is None:
            errors["days_off"] = t("form.date_invalid")
        elif form.get("action") == "remove":
            days.discard(day)
        elif len(days) >= MAX_DAYS_OFF:
            errors["days_off"] = t("v2.psettings.days_off_full", n=MAX_DAYS_OFF)
        else:
            days.add(day)
        if not errors:
            settings = view.definition.settings.model_copy(update={"days_off": tuple(sorted(days))})
            changed = view.definition.model_copy(update={"settings": settings})
            try:
                services.update_definition(session, project_id, changed, language)
            except AppError as exc:
                errors["days_off"] = " ".join(t.issues(exc))
            else:
                return saved(request, project_id, "days_off")
        return project_page(request, project_id, 422, errors=errors, kept=form)

    @routes.post(PREFIX + "/projects/{project_id}/settings/reminder")
    async def save_reminder(request: Request, project_id: str) -> Response:
        """The weekly report reminder of the calendar (section 8.9): a weekday and an hour."""
        form = await Form.read(request)
        t = texts(request)
        current = calendar_of(ui, request, project_id)
        day = form.get("reminder_day", "3")
        hour = form.get("reminder_time", "17:00").strip()
        if not day.isdigit() or int(day) not in WEEKDAYS or not TIME.match(hour):
            errors = {"reminder": t("v2.psettings.reminder_error")}
            return project_page(request, project_id, 422, errors=errors, kept=form)
        changed = CalendarRow(current.project, current.session, current.nonce, int(day), hour)
        services.store.save_calendar(ui.session(request), changed)
        return saved(request, project_id, "reminder")

    @routes.post(PREFIX + "/projects/{project_id}/settings/assessment")
    async def save_assessment(request: Request, project_id: str) -> Response:
        """ "Najpierw moja ocena" on or off (v3 spec section 6; spec section 11.8)."""
        session, language = ui.session(request), ui.language(request)
        form = await Form.read(request)
        view = services.live(session, project_id, language)
        settings = view.definition.settings.model_copy(
            update={"assessment_first": form.flag("assessment_first")}
        )
        changed = view.definition.model_copy(update={"settings": settings})
        services.update_definition(session, project_id, changed, language)
        return saved(request, project_id, "assessment")

    @routes.post(PREFIX + "/projects/{project_id}/delete")
    def delete(request: Request, project_id: str) -> Response:
        """ "Usuń projekt", after the confirmation in the red zone."""
        services.delete(ui.session(request), project_id)
        return ui.redirect(request, PREFIX, done="deleted")

    return routes
