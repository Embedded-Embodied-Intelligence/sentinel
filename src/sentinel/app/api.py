"""The HTTP API and the pages of the application (WP9a, WP9b; spec section 11; ADR-0022,
ADR-0024, ADR-0025).

JSON endpoints under /api for every service, typed request and response models, and one error
format `{"error": {"code", "message", "details": [...]}}` with messages in English or Polish
(`?lang=pl` or the Accept-Language header). Long operations answer 202 with a job to poll at
/api/jobs/{id}. The pages (`sentinel.app.ui`) are served from the same app, in Polish unless the
visitor chose English (a cookie). Every request but a static file goes through one guard: the
request rate per client address, the session (the local one, or in demo mode a signed cookie of
an anonymous sandbox, created on the first request), and the CSRF token of the session on every
state-changing request (`X-CSRF-Token`; the pages send it with every HTMX request). The LLM
settings endpoints, which never return the key, do not exist in the demo; no endpoint shows
files, settings or another session's data, and no page shows a stack trace: an unexpected error
is logged with a reference id, which the page or the JSON error names. The client address of
the limits is the TCP peer, or behind the local proxy of the demo its X-Forwarded-For
(`security.client_address`); `/api/client-address` reports it to requests from 127.0.0.1 only.
"""

import json
import logging
import secrets
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import date
from importlib.metadata import PackageNotFoundError, version
from typing import Annotated, Any, Literal

from fastapi import FastAPI, File, Form, Query, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.responses import Response as FastResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from sentinel.app.config import AppConfig, Limits
from sentinel.app.errors import AppError, ErrorKind
from sentinel.app.events import Verdict
from sentinel.app.io import TASKS_TEMPLATE, TEAM_TEMPLATE
from sentinel.app.live import LiveError
from sentinel.app.llm import LlmSettingsUpdate, LlmSettingsView
from sentinel.app.messages import language_of, render
from sentinel.app.models import CheckIn, Language, ProjectDefinition
from sentinel.app.security import (
    CSRF_COOKIE,
    CSRF_HEADER,
    LOCAL_PROXY,
    SESSION_COOKIE,
    UNSAFE_METHODS,
    RateLimiter,
    client_address,
    csrf_token,
    csrf_valid,
    load_key,
    sign,
    unsign,
)
from sentinel.app.services import (
    CheckinResult,
    ErrorView,
    EventView,
    JobView,
    Services,
    error_view,
)
from sentinel.app.simulator import SimulatorSpec, SimulatorView
from sentinel.app.store import LOCAL_SESSION
from sentinel.app.ui.core import LANG_COOKIE, STATIC_PREFIX, Ui
from sentinel.app.views import IssueView, ProjectSummary, ProjectView

LOG = logging.getLogger("sentinel.app")
STATUS: dict[ErrorKind, int] = {
    "invalid": 422,
    "not_found": 404,
    "conflict": 409,
    "forbidden": 403,
    "limit": 429,
    "too_large": 413,
    "unavailable": 503,
}
EXPIRY_CHECK_S = 60.0
UNLIMITED = ("/api/health", "/favicon.ico")  # neither limited nor given a session
SESSIONLESS = ("/api/client-address",)  # rate-limited, but no sandbox is made for it


def _version() -> str:
    try:
        return version("sentinel")
    except PackageNotFoundError:  # pragma: no cover - installed with the project
        return "?"


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    demo: bool


class ClientAddress(BaseModel):
    """What the app sees of a request (WP9c, the public demo's check): the address its limits
    count, the TCP peer, the X-Forwarded-For header and whether it was trusted."""

    address: str
    peer: str | None
    forwarded_for: str | None
    trusted: bool
    limited: bool


class SessionInfo(BaseModel):
    """The visitor's session: demo or local, its CSRF token, limits and the LLM's state."""

    demo: bool
    csrf_token: str
    limits: Limits | None
    llm_available: bool
    expires_hours: float | None


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Verdict


class AdvanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: int = Field(ge=1, le=10_000)


class ExtractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(max_length=50_000)


class MessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(max_length=5_000)
    date: date


def _language(request: Request) -> Language:
    lang = request.query_params.get("lang")
    if lang in ("en", "pl"):
        return lang  # type: ignore[return-value]
    if not _is_api(request.url.path):  # pages: Polish unless the visitor chose English
        return "en" if request.cookies.get(LANG_COOKIE) == "en" else "pl"
    return language_of(request.headers.get("accept-language"))


def _is_api(path: str) -> bool:
    return path.startswith("/api/")


def _error(code: str, status: int, language: Language, **params: object) -> JSONResponse:
    view = ErrorView(code=code, message=render(code, language, params), details=[])
    return JSONResponse({"error": view.model_dump(mode="json")}, status_code=status)


def create_app(config: AppConfig, services: Services | None = None) -> FastAPI:
    """The FastAPI app of `sentinel ui` (`--demo`: per-visitor sandboxes with limits)."""
    services = services or Services(config)
    key = load_key(config.secret_file)
    per_minute = config.limits.requests_per_minute
    limiter = RateLimiter(per_minute) if config.demo and per_minute else None
    if not config.demo:
        services.local_session()
    if config.demo and config.showcase:
        from sentinel.app.showcase import install

        install(services)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        services.close()

    app = FastAPI(
        title="Sentinel",
        version=_version(),
        docs_url=None,  # Swagger UI loads a CDN (ADR-0025); the schema is JSON
        redoc_url=None,
        openapi_url=None if config.demo else "/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.services = services
    ui = Ui(config, services, _version())
    last_expiry = [0.0]

    def refuse(request: Request, code: str, status: int, language: Language) -> FastResponse:
        """A request the guard refuses: JSON for the API, a page or a message for the pages."""
        if _is_api(request.url.path):
            return _error(code, status, language)
        request.state.language = language
        return ui.error(request, render(code, language), status)

    @app.middleware("http")
    async def guard(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        language = _language(request)
        path = request.url.path
        if path.startswith(STATIC_PREFIX) or path in UNLIMITED:
            return await call_next(request)
        peer = request.client.host if request.client else None
        address = client_address(peer, request.headers.get("x-forwarded-for"), config.trust_proxy)
        request.state.address = address
        if limiter is not None and not limiter.allow(address):
            return refuse(request, "rate_limited", 429, language)
        if path in SESSIONLESS:
            return await call_next(request)
        new_session = None
        if config.demo:
            now = time.monotonic()
            if now - last_expiry[0] > EXPIRY_CHECK_S:
                last_expiry[0] = now
                services.expire_sandboxes()
            session_id = unsign(key, request.cookies.get(SESSION_COOKIE))
            session = None if session_id is None else services.store.session(session_id)
            if session is None:
                if request.method in UNSAFE_METHODS:  # a fresh sandbox has no token yet
                    return refuse(request, "csrf_failed", 403, language)
                session = services.new_session(language)
                new_session = session.id
            session_id = session.id
        else:
            session_id = LOCAL_SESSION
        if request.method in UNSAFE_METHODS and not csrf_valid(
            key, session_id, request.headers.get(CSRF_HEADER)
        ):
            return refuse(request, "csrf_failed", 403, language)
        request.state.session = session_id
        request.state.language = language
        request.state.csrf = csrf_token(key, session_id)
        response = await call_next(request)
        if new_session is not None:
            response.set_cookie(
                SESSION_COOKIE,
                sign(key, new_session),
                max_age=int(config.limits.sandbox_hours * 3600),
                httponly=True,
                samesite="lax",
                secure=config.secure_cookies,
            )
        token = csrf_token(key, session_id)
        if request.cookies.get(CSRF_COOKIE) != token:
            response.set_cookie(CSRF_COOKIE, token, samesite="strict", secure=config.secure_cookies)
        return response

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError) -> FastResponse:
        view = error_view(exc, _language(request))
        if not _is_api(request.url.path):
            details = [d.message for d in view.details if d.message != view.message]
            return ui.error(request, view.message, STATUS[exc.kind], details=details[:8])
        return JSONResponse({"error": view.model_dump(mode="json")}, status_code=STATUS[exc.kind])

    @app.exception_handler(LiveError)
    async def live_error(request: Request, exc: LiveError) -> FastResponse:
        return await app_error(request, AppError.of(exc))

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError) -> FastResponse:
        language = _language(request)
        if not _is_api(request.url.path):
            return ui.error(request, render("invalid_request", language), 422)
        details = []
        for error in exc.errors():
            field = ".".join(str(part) for part in error.get("loc", ()) if part != "body")
            if error.get("type") == "missing":
                code, params = "field_required", {"field": field}
            else:
                code, params = "field_invalid", {"field": field, "detail": error.get("msg", "")}
            details.append(
                IssueView(
                    code=code,
                    message=render(code, language, params),
                    where=field or None,
                    severity="error",
                )
            )
        view = ErrorView(
            code="invalid_request",
            message=render("invalid_request", language),
            details=details,
        )
        return JSONResponse({"error": view.model_dump(mode="json")}, status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> FastResponse:
        code = "not_found" if exc.status_code == 404 else "invalid_request"
        language = _language(request)
        if not _is_api(request.url.path):
            request.state.language = language
            return ui.error(request, render(code, language), exc.status_code)
        return _error(code, exc.status_code, language)

    @app.exception_handler(Exception)
    async def crash(request: Request, exc: Exception) -> FastResponse:
        reference = secrets.token_hex(4)
        LOG.exception(
            "request %s %s failed (reference %s)", request.method, request.url.path, reference
        )
        language = _language(request)
        if not _is_api(request.url.path):
            request.state.language = language
            message = render("internal_error", language)
            return ui.error(request, message, 500, reference=reference)
        view = ErrorView(
            code="internal_error",
            message=render("internal_error_ref", language, {"reference": reference}),
            details=[],
        )
        return JSONResponse({"error": view.model_dump(mode="json")}, status_code=500)

    def sid(request: Request) -> str:
        return str(request.state.session)

    def lang(request: Request) -> Language:
        language: Language = request.state.language
        return language

    # ---- health, session, settings

    @app.get("/api/health", response_model=Health)
    def health() -> Health:
        return Health(version=_version(), demo=config.demo)

    @app.get("/api/client-address", response_model=ClientAddress)
    def client(request: Request) -> ClientAddress:
        """The address the limits count for this request; only for requests from 127.0.0.1
        (the server itself, or the demo's local proxy), others get 404."""
        peer = request.client.host if request.client else None
        if peer != LOCAL_PROXY:
            raise StarletteHTTPException(status_code=404)
        forwarded = request.headers.get("x-forwarded-for")
        address = str(request.state.address)
        return ClientAddress(
            address=address,
            peer=peer,
            forwarded_for=forwarded,
            trusted=address != peer,
            limited=limiter is not None,
        )

    @app.get("/api/session", response_model=SessionInfo)
    def session_info(request: Request) -> SessionInfo:
        return SessionInfo(
            demo=config.demo,
            csrf_token=csrf_token(key, sid(request)),
            limits=config.limits if config.demo else None,
            llm_available=services.llm.available,
            expires_hours=config.limits.sandbox_hours if config.demo else None,
        )

    @app.get("/api/settings/llm", response_model=LlmSettingsView)
    def llm_settings() -> LlmSettingsView:
        if config.demo:
            raise AppError("demo_forbidden", "forbidden")
        return services.llm.view()

    @app.put("/api/settings/llm", response_model=LlmSettingsView)
    def set_llm_settings(change: LlmSettingsUpdate) -> LlmSettingsView:
        if config.demo:
            raise AppError("demo_forbidden", "forbidden")
        return services.llm.update(change)

    @app.post("/api/settings/llm/test", response_model=JobView, status_code=202)
    def test_llm_settings(request: Request) -> JobView:
        if config.demo:
            raise AppError("demo_forbidden", "forbidden")
        return services.test_llm(sid(request), lang(request))

    # ---- live projects

    @app.get("/api/projects", response_model=list[ProjectSummary])
    def projects(request: Request) -> list[ProjectSummary]:
        return services.projects(sid(request))

    @app.post("/api/projects", response_model=ProjectView, status_code=201)
    def create(request: Request, definition: ProjectDefinition) -> ProjectView:
        return services.create(sid(request), definition, lang(request))

    @app.post("/api/projects/validate", response_model=list[IssueView])
    def validate(request: Request, definition: ProjectDefinition) -> list[IssueView]:
        return services.validate(definition, lang(request))

    @app.get("/api/projects/{project_id}", response_model=ProjectView | SimulatorView)
    def project(request: Request, project_id: str) -> Any:
        return services.project(sid(request), project_id, lang(request))

    @app.put("/api/projects/{project_id}/definition", response_model=ProjectView)
    def update(request: Request, project_id: str, definition: ProjectDefinition) -> ProjectView:
        return services.update_definition(sid(request), project_id, definition, lang(request))

    @app.delete("/api/projects/{project_id}", status_code=204)
    def delete(request: Request, project_id: str) -> Response:
        services.delete(sid(request), project_id)
        return Response(status_code=204)

    @app.get("/api/projects/{project_id}/events", response_model=list[EventView])
    def events(request: Request, project_id: str) -> list[EventView]:
        return services.events(sid(request), project_id)

    @app.post("/api/projects/{project_id}/plan", response_model=JobView, status_code=202)
    def plan(request: Request, project_id: str) -> JobView:
        return services.plan(sid(request), project_id, lang(request))

    @app.post("/api/projects/{project_id}/forecast", response_model=JobView, status_code=202)
    def forecast(request: Request, project_id: str) -> JobView:
        return services.forecast(sid(request), project_id, lang(request))

    @app.post("/api/projects/{project_id}/checkins", response_model=CheckinResult)
    def checkin(request: Request, project_id: str, report: CheckIn) -> CheckinResult:
        return services.checkin(sid(request), project_id, report, lang(request))

    @app.post("/api/projects/{project_id}/recommendations", response_model=JobView, status_code=202)
    def recommend(request: Request, project_id: str) -> JobView:
        return services.recommend(sid(request), project_id, lang(request))

    @app.post(
        "/api/projects/{project_id}/recommendations/{seq}/decision", response_model=ProjectView
    )
    def decide(request: Request, project_id: str, seq: int, body: DecisionRequest) -> ProjectView:
        return services.decide(sid(request), project_id, seq, body.verdict, lang(request))

    @app.post("/api/projects/{project_id}/recommendations/{seq}/undo", response_model=ProjectView)
    def undo(request: Request, project_id: str, seq: int) -> ProjectView:
        return services.undo(sid(request), project_id, seq, lang(request))

    @app.post("/api/projects/{project_id}/messages", response_model=JobView, status_code=202)
    def read_message(request: Request, project_id: str, body: MessageRequest) -> JobView:
        return services.read_message(sid(request), project_id, body.text, body.date, lang(request))

    @app.post(
        "/api/projects/{project_id}/recommendations/{seq}/explanation",
        response_model=JobView,
        status_code=202,
    )
    def explain(request: Request, project_id: str, seq: int) -> JobView:
        return services.explain(sid(request), project_id, seq, lang(request))

    @app.get("/api/projects/{project_id}/export.json")
    def export(request: Request, project_id: str) -> Response:
        data = services.export(sid(request), project_id)
        text = json.dumps(data, indent=2, ensure_ascii=False)
        headers = {"Content-Disposition": 'attachment; filename="project.json"'}
        return Response(text, media_type="application/json", headers=headers)

    @app.get("/api/projects/{project_id}/plan.csv")
    def plan_csv(request: Request, project_id: str) -> Response:
        text = services.plan_csv(sid(request), project_id)
        headers = {"Content-Disposition": 'attachment; filename="plan.csv"'}
        return Response(text, media_type="text/csv; charset=utf-8", headers=headers)

    def slim(job: JobView) -> JobView:
        """A cockpit job points at its page instead of holding it."""
        if job.kind == "cockpit" and job.result is not None:
            return job.model_copy(update={"result": {"html": f"/api/jobs/{job.id}/cockpit.html"}})
        return job

    @app.post("/api/projects/{project_id}/cockpit", response_model=JobView, status_code=202)
    def cockpit(request: Request, project_id: str) -> JobView:
        return slim(services.cockpit(sid(request), project_id, lang(request)))

    # ---- import, templates, extraction

    @app.post("/api/import/csv", response_model=ProjectView, status_code=201)
    async def import_csv(
        request: Request,
        tasks: Annotated[UploadFile, File()],
        name: Annotated[str, Form(max_length=120)],
        start: Annotated[date, Form()],
        team: Annotated[UploadFile | None, File()] = None,
        deadline: Annotated[date | None, Form()] = None,
        budget: Annotated[float | None, Form(gt=0)] = None,
    ) -> ProjectView:
        limit = config.limits.upload_kb * 1024
        tasks_data = await tasks.read(limit + 1)
        team_data = None if team is None else await team.read(limit + 1)
        if len(tasks_data) > limit or (team_data is not None and len(team_data) > limit):
            raise AppError("too_large", "too_large", limit=config.limits.upload_kb)
        return services.import_csv(
            sid(request),
            tasks_data,
            team_data,
            name=name,
            start=start,
            deadline=deadline,
            budget=budget,
            language=lang(request),
        )

    @app.post("/api/import/json", response_model=ProjectView | SimulatorView, status_code=201)
    async def import_json(request: Request, file: Annotated[UploadFile, File()]) -> Any:
        limit = config.limits.upload_kb * 1024
        data = await file.read(limit + 1)
        if len(data) > limit:
            raise AppError("too_large", "too_large", limit=config.limits.upload_kb)
        try:
            parsed = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise AppError("json_invalid", detail="not JSON") from exc
        return services.import_json(sid(request), parsed, lang(request))

    @app.get("/api/templates/{name}")
    def template(name: Literal["tasks.csv", "team.csv"]) -> PlainTextResponse:
        text = TASKS_TEMPLATE if name == "tasks.csv" else TEAM_TEMPLATE
        headers = {"Content-Disposition": f'attachment; filename="{name}"'}
        return PlainTextResponse(text, media_type="text/csv; charset=utf-8", headers=headers)

    @app.post("/api/extract", response_model=JobView, status_code=202)
    def extract(request: Request, body: ExtractRequest) -> JobView:
        return services.extract(sid(request), body.text, lang(request))

    # ---- simulator

    @app.get("/api/simulator/instances", response_model=list[str])
    def instances(
        set_name: Annotated[Literal["j30", "j60"], Query(alias="set")] = "j30",
    ) -> list[str]:
        return services.instances(set_name)

    @app.post("/api/simulator", response_model=JobView, status_code=202)
    def create_simulator(request: Request, spec: SimulatorSpec) -> JobView:
        return services.create_simulator(sid(request), spec, lang(request))

    @app.post("/api/projects/{project_id}/advance", response_model=JobView, status_code=202)
    def advance(request: Request, project_id: str, body: AdvanceRequest) -> JobView:
        return services.advance(sid(request), project_id, body.days, lang(request))

    # ---- jobs

    @app.get("/api/jobs/{job_id}", response_model=JobView)
    def job(request: Request, job_id: str) -> JobView:
        return slim(services.job(sid(request), job_id, lang(request)))

    @app.get("/api/jobs/{job_id}/cockpit.html", response_class=HTMLResponse)
    def cockpit_page(request: Request, job_id: str) -> HTMLResponse:
        row = services.job_row(sid(request), job_id)
        if row.kind != "cockpit" or row.result is None:
            raise AppError("job_not_done", "conflict")
        return HTMLResponse(str(row.result.get("html", "")))

    from sentinel.app.ui.core import mount

    mount(app, ui)
    app.add_middleware(GZipMiddleware, minimum_size=1024)  # pages, scripts and JSON
    return app
