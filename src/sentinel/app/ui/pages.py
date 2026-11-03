"""The start page, the "how it works" page, the app settings, the language switch and the
progress of background jobs (WP9b; ADR-0025)."""

import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import Response

from sentinel.app.errors import AppError
from sentinel.app.llm import LlmSettingsUpdate, Provider
from sentinel.app.services import JobView
from sentinel.app.simulator import SimulatorSpec
from sentinel.app.ui.core import LANG_COOKIE, STATIC_DIR, Ui, chance_level, local_path, nav_rank
from sentinel.app.ui.forms import Form
from sentinel.app.views import ForecastSummary
from sentinel.llm.ollama import DEFAULT_HOST, HOST_VARIABLE

PROVIDERS: tuple[Provider, ...] = ("none", "ollama", "groq", "openrouter")
REPOSITORY = "https://github.com/Embedded-Embodied-Intelligence/sentinel"
JOB_LABELS = (
    "job.plan",
    "job.recommend",
    "job.advance",
    "job.simulator",
    "job.extract",
    "job.message",
    "job.llm_test",
    "job.explain",
)
JOB_NOTES = ("sim.end_note.j30", "sim.end_note.j60", "job.slow_ai")


@dataclass(frozen=True)
class Card:
    """A project on the start page."""

    id: str
    kind: str
    name: str
    href: str
    planned: bool = False
    finished: bool = False
    deadline: date | None = None
    pending: int = 0
    as_of: date | None = None
    size: str = ""
    days: int = 0
    manager: str = ""
    chance: float | None = None
    step: int = 1  # the wizard's steps a draft has finished


def project_cards(cards: Sequence[Card]) -> list[Card]:
    """The running projects in the order of the start page (docs/design/brief.md, section 4.1)."""
    return sorted(
        (c for c in cards if c.kind == "live" and c.planned),
        key=lambda c: nav_rank("decision" if c.pending else "", c.chance),
    )


def trend(summary: ForecastSummary | None) -> int | None:
    """The change of the chance since before the latest check-in, in whole percentage points."""
    if summary is None or summary.previous_p is None or summary.forecast.p_on_time is None:
        return None
    return round(100 * (summary.forecast.p_on_time - summary.previous_p))


def ollama_placeholder() -> str:
    """The Ollama address a settings page suggests: the server's own `OLLAMA_HOST` (in Docker the
    compose file sets the container's, http://ollama:11434; the WP12 test), else the local one."""
    return os.environ.get(HOST_VARIABLE, "").strip() or DEFAULT_HOST


def router(ui: Ui) -> APIRouter:
    routes = APIRouter()
    services = ui.services

    @routes.get("/")
    def start(request: Request) -> Response:
        session = ui.session(request)
        cards = []
        for summary in services.projects(session):
            href = f"/projects/{summary.id}"
            if summary.kind == "simulator":
                events = services.store.events(session, summary.id)
                spec = SimulatorSpec.model_validate(events[0].payload["spec"])
                days = sum(int(e.payload.get("days", 0)) for e in events[1:])
                cards.append(
                    Card(
                        summary.id,
                        "simulator",
                        summary.name,
                        href,
                        size=spec.set_name,
                        days=days,
                        manager=spec.policy,
                    )
                )
                continue
            state = services.state(session, summary.id)
            project = state.project
            planned = project.baseline is not None
            cards.append(
                Card(
                    summary.id,
                    "live",
                    summary.name,
                    href
                    if planned
                    else f"{href}/setup/{'tasks' if project.definition.team else 'team'}",
                    planned=planned,
                    finished=project.finished,
                    deadline=project.definition.deadline,
                    pending=0 if state.open is None else 1,
                    as_of=project.checkins[-1][0] if project.checkins else None,
                    chance=services.known_chance(summary.id, state),
                    step=2 if project.definition.team else 1,
                )
            )
        return ui.page(
            request,
            "start.html",
            title=ui.texts(request)("start.title"),
            nav="projects",
            cards=project_cards(cards),
            drafts=[c for c in cards if c.kind == "live" and not c.planned],
            examples=[c for c in cards if c.kind == "simulator"],
        )

    @routes.get("/projects/{project_id}/chance")
    def chance(request: Request, project_id: str) -> Response:
        """The chance of meeting the deadline on a project card (loaded after the page)."""
        try:
            summary = services.forecast_summary(
                ui.session(request), project_id, ui.language(request)
            )
        except AppError:
            summary = None
            failed = True
        else:
            failed = False
        p = None if summary is None else summary.forecast.p_on_time
        return ui.page(
            request,
            "_chance.html",
            summary=summary,
            level=chance_level(p),
            delta=trend(summary),
            failed=failed,
            project_id=project_id,
            nav_level="decision"
            if services.state(ui.session(request), project_id).open is not None
            else chance_level(p),
        )

    @routes.get("/how-it-works")
    def how(request: Request) -> Response:
        return ui.page(
            request,
            "how.html",
            title=ui.texts(request)("how.title"),
            nav="how",
            repository=REPOSITORY,
        )

    @routes.get("/settings")
    def settings(request: Request) -> Response:
        return _settings_page(request)

    def _settings_page(
        request: Request, status: int = 200, issues: list[str] | None = None, **values: Any
    ) -> Response:
        view = services.llm.view()
        return ui.page(
            request,
            "settings.html",
            status,
            title=ui.texts(request)("settings.title"),
            nav="settings",
            view=view,
            providers=PROVIDERS,
            issues=issues or [],
            repository=REPOSITORY,
            today=date.today(),
            ollama_host=ollama_placeholder(),
            **values,
        )

    def _save_settings(request: Request, form: Form) -> LlmSettingsUpdate:
        if ui.config.demo:
            raise AppError("demo_forbidden", "forbidden")
        provider = form.get("provider", "none")
        if provider not in PROVIDERS:
            raise AppError("field_invalid", field="provider", detail=provider)
        key = form.get("api_key", "").strip()
        change = LlmSettingsUpdate(
            provider=provider,
            model=form.get("model", "").strip() or None,
            host=form.get("host", "").strip() or None,
            api_key="" if form.flag("forget_key") else (key or None),
        )
        services.llm.update(change)
        return change

    @routes.post("/settings")
    async def save_settings(request: Request) -> Response:
        form = await Form.read(request)
        _save_settings(request, form)
        return ui.redirect(request, "/settings", flash="settings_saved")

    @routes.post("/settings/test")
    async def test_settings(request: Request) -> Response:
        form = await Form.read(request)
        _save_settings(request, form)
        job = services.test_llm(ui.session(request), ui.language(request))
        return job_progress(ui, request, job, "job.llm_test")

    @routes.get("/lang/{code}")
    def language(request: Request, code: str) -> Response:
        target = local_path(request.query_params.get("next"))
        response = ui.redirect(request, target)
        if code in ("pl", "en"):
            response.set_cookie(LANG_COOKIE, code, max_age=365 * 24 * 3600, samesite="lax")
        return response

    @routes.get("/favicon.ico")
    def favicon() -> Response:
        data = (STATIC_DIR / "favicon.svg").read_bytes()
        return Response(data, media_type="image/svg+xml")

    @routes.get("/jobs/{job_id}")
    def job(request: Request, job_id: str) -> Response:
        """The progress of a job, polled by its fragment; when done, the next page or the
        result (spec section 11: long operations never block a page)."""
        view = services.job(ui.session(request), job_id, ui.language(request))
        label = request.query_params.get("label", "job.plan")
        label = label if label in JOB_LABELS else "job.plan"
        target = local_path(request.query_params.get("next"), "")
        if view.status in ("queued", "running"):
            kept = ("next", "project", "note", "cancel")
            passed = {k: v for k, v in request.query_params.items() if k in kept}
            return job_progress(ui, request, view, label, **passed)
        if view.status == "failed":
            error = view.error
            message = error.message if error else ui.texts(request)("error.title")
            details = [] if error is None else [d.message for d in error.details[:8]]
            return ui.page(request, "_error.html", message=message, details=details, reference=None)
        result = view.result or {}
        project = view.project or ""
        match view.kind:
            case "llm_test":
                return ui.page(request, "_test_ok.html", model=str(result.get("model", "?")))
            case "extract":
                from sentinel.app.ui.setup import extraction_review

                return extraction_review(ui, request, view)
            case "message":
                from sentinel.app.ui.project import message_review

                return message_review(ui, request, view)
            case "recommend" if not target:
                seq = int(result.get("recommendation", 0))
                return ui.redirect(request, f"/projects/{project}/recommendations/{seq}")
            case "plan" if not target:
                return ui.redirect(request, f"/projects/{project}", flash="plan_ready")
            case "simulator" | "advance" if not target:
                return ui.redirect(request, f"/projects/{project}")
        return ui.redirect(request, target or f"/projects/{project}")

    @routes.post("/jobs/{job_id}/cancel")
    def cancel_job(request: Request, job_id: str) -> Response:
        """Stop a simulator run after the current day and show what it reached."""
        session = ui.session(request)
        services.cancel_advance(session, job_id)
        job = services.job(session, job_id, ui.language(request))
        return ui.redirect(request, f"/projects/{job.project}" if job.project else "/")

    return routes


def job_progress(ui: Ui, request: Request, job: JobView, label: str, **query: str) -> Response:
    """The fragment of a running job, which polls `/jobs/{id}` until it is done; a run to the end
    says how long it takes and can be cancelled."""
    texts = ui.texts(request)
    values = {"label": label} | query
    note = query.get("note", "")
    return ui.page(
        request,
        "_job.html",
        job=job,
        label=texts(label),
        query=urlencode(values),
        note=texts(note) if note in JOB_NOTES else "",
        cancel=f"/jobs/{job.id}/cancel" if query.get("cancel") else "",
    )
