"""The machinery of the pages (ADR-0025): the Jinja2 environment, the context every page gets
(language, texts, CSRF token, demo flag), HTMX-aware responses and redirects, and the friendly
error pages, which show a reference id and never a stack trace (the details go to the log)."""

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from sentinel.app.config import AppConfig
from sentinel.app.models import Language
from sentinel.app.services import Services
from sentinel.app.ui.text import Texts

LOG = logging.getLogger("sentinel.app")
LANG_COOKIE = "sentinel_lang"
DEFAULT_LANGUAGE: Language = "pl"
STATIC_DIR = Path(__file__).parent / "static"
STATIC_PREFIX = "/static/"
HTMX = "htmx-2.0.11.min.js"
# HTMX swaps error responses too (into #flash when the server retargets them), so a refused
# form shows its plain-language message; 204 swaps nothing.
HTMX_CONFIG = (
    '{"responseHandling":[{"code":"204","swap":false},{"code":"[2345]..","swap":true}],'
    '"includeIndicatorStyles":false,"allowScriptTags":false,"historyCacheSize":0}'
)
FLASHES = (
    "checkin_saved",
    "approved",
    "rejected",
    "later",
    "undone",
    "deleted",
    "settings_saved",
    "plan_ready",
    "discarded",
    "no_change",
)


def is_htmx(request: Request) -> bool:
    return request.headers.get("hx-request") == "true"


def local_path(value: str | None, default: str = "/") -> str:
    """A path on this site (no scheme, no host), else `default`: no open redirects."""
    if not value or not value.startswith("/") or value.startswith("//") or "\\" in value:
        return default
    return value


class Ui:
    """The pages of one app: templates, services and settings."""

    def __init__(self, config: AppConfig, services: Services, version: str) -> None:
        self.config = config
        self.services = services
        self.version = version
        self.env = Environment(
            loader=PackageLoader("sentinel.app.ui", "templates"),
            autoescape=select_autoescape(("html",)),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env.globals["static"] = self.static

    def static(self, name: str) -> str:
        return f"{STATIC_PREFIX}{name}?v={self.version}"

    @staticmethod
    def language(request: Request) -> Language:
        language: Language = getattr(request.state, "language", DEFAULT_LANGUAGE)
        return language

    @staticmethod
    def session(request: Request) -> str:
        return str(request.state.session)

    def texts(self, request: Request) -> Texts:
        return Texts(self.language(request))

    def context(self, request: Request, values: Mapping[str, Any]) -> dict[str, Any]:
        """The context of every page: texts, CSRF token, demo flag, AI availability, where the
        language switch returns to, and a flash message named in the query."""
        texts = self.texts(request)
        flash = request.query_params.get("flash")
        here = request.url.path
        query = [
            (k, v) for k, v in request.query_params.multi_items() if k not in ("flash", "lang")
        ]
        if query:
            here += "?" + urlencode(query)
        context: dict[str, Any] = {
            "t": texts,
            "csrf": getattr(request.state, "csrf", ""),
            "demo": self.config.demo,
            "demo_hours": round(self.config.limits.sandbox_hours),
            "llm": self.services.llm.available,
            "version": self.version,
            "htmx": HTMX,
            "htmx_config": HTMX_CONFIG,
            "here": here,
            "nav": "",
            "flash": texts(f"flash.{flash}") if flash in FLASHES else None,
        }
        context.update(values)
        return context

    def render(self, request: Request, template: str, values: Mapping[str, Any]) -> str:
        return self.env.get_template(template).render(self.context(request, values))

    def page(
        self,
        request: Request,
        template: str,
        status: int = 200,
        headers: Mapping[str, str] | None = None,
        **values: Any,
    ) -> HTMLResponse:
        """A full page, or a fragment template (names starting with "_")."""
        html = self.render(request, template, values)
        return HTMLResponse(html, status_code=status, headers=dict(headers or {}))

    def redirect(self, request: Request, url: str, **query: str) -> Response:
        """Go to `url` (a full page load): HX-Redirect for HTMX requests, else 303."""
        target = url + ("?" + urlencode(query) if query else "")
        if is_htmx(request):
            return Response(status_code=200, headers={"HX-Redirect": target})
        return RedirectResponse(target, status_code=303)

    def error(
        self,
        request: Request,
        message: str,
        status: int,
        *,
        details: list[str] | None = None,
        reference: str | None = None,
    ) -> HTMLResponse:
        """A refused or failed request in plain language: into #flash for HTMX requests, else
        as a page."""
        listed = details or []
        if is_htmx(request):
            headers = {"HX-Retarget": "#flash", "HX-Reswap": "innerHTML"}
            return self.page(
                request,
                "_error.html",
                status,
                headers,
                message=message,
                details=listed,
                reference=reference,
            )
        return self.page(
            request, "error.html", status, message=message, details=listed, reference=reference
        )


def mount(app: FastAPI, ui: Ui) -> None:
    """Serve the pages and their static files from `app`."""
    from sentinel.app.ui import pages, project, setup, sim

    app.mount(STATIC_PREFIX.rstrip("/"), StaticFiles(directory=STATIC_DIR), name="static")
    for module in (pages, setup, project, sim):
        app.include_router(module.router(ui))
