"""The machinery of the pages (ADR-0025): the Jinja2 environment, the context every page gets
(language, texts, CSRF token, demo flag), HTMX-aware responses and redirects, and the friendly
error pages, which show a reference id and never a stack trace (the details go to the log)."""

import logging
from collections.abc import Mapping
from dataclasses import dataclass
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
from sentinel.app.ui.icons import icon
from sentinel.app.ui.text import Texts

LOG = logging.getLogger("sentinel.app")
LANG_COOKIE = "sentinel_lang"
DEFAULT_LANGUAGE: Language = "pl"
STATIC_DIR = Path(__file__).parent / "static"
STATIC_PREFIX = "/static/"
HTMX = "htmx-2.0.11.min.js"
# HTMX swaps error responses too (into #alerts when the server retargets them), so a refused
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
    "imported",
)
FLASH_TO_HISTORY = ("checkin_saved", "approved", "rejected", "later", "undone")
NAV_PROJECTS = 5  # the sidebar's "your projects" group (docs/design/brief.md, section 3.1)


@dataclass(frozen=True)
class NavProject:
    """A project in the sidebar: its name and the status its icon and hidden word tell."""

    id: str
    name: str
    level: str


def chance_level(p: float | None) -> str:
    """The badge of a chance of meeting the deadline: good from the target 80 % (spec section 8,
    theta_D), at risk from 50 %, else bad."""
    if p is None:
        return "neutral"
    return "good" if p >= 0.8 else "warn" if p >= 0.5 else "bad"


def nav_rank(level: str, chance: float | None) -> tuple[int, float]:
    """The order of projects (docs/design/brief.md, section 4.1): those with a decision waiting
    first, then by chance from lowest to highest, unknown chances last."""
    return (0 if level == "decision" else 1, 2.0 if chance is None else chance)


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
        self.env.globals["icon"] = icon

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

    def nav_projects(self, request: Request) -> list[NavProject]:
        """The live projects of the sidebar with a status known without calculating anything (a
        forecast not cached yet shows as unknown until the page's own forecast arrives). The
        sidebar never takes a page down: an error here leaves the group out."""
        try:
            session = self.session(request)
            found: list[tuple[tuple[int, float], NavProject]] = []
            for summary in self.services.projects(session):
                if summary.kind != "live":
                    continue
                state = self.services.state(session, summary.id)
                if state.project.baseline is None:
                    continue  # drafts are on the start page
                chance = self.services.known_chance(summary.id, state)
                level = "decision" if state.open is not None else chance_level(chance)
                item = NavProject(summary.id, summary.name, level)
                found.append((nav_rank(level, chance), item))
        except Exception:
            LOG.exception("the sidebar's projects could not be read")
            return []
        found.sort(key=lambda entry: entry[0])
        return [item for _, item in found[:NAV_PROJECTS]]

    def context(self, request: Request, values: Mapping[str, Any]) -> dict[str, Any]:
        """The context of every page: texts, CSRF token, demo flag, AI availability, where the
        language switch returns to, the sidebar's projects, and a flash message named in the
        query (a toast, with a link to the history after something the history records)."""
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
            "flash_link": f"{request.url.path}/history"
            if flash in FLASH_TO_HISTORY and request.url.path.startswith("/projects/")
            else None,
            "nav_projects": lambda: self.nav_projects(request),
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
        """A refused or failed request in plain language: an inline alert for HTMX requests,
        never a toast (docs/design/brief.md, section 3.11), else a page."""
        listed = details or []
        if is_htmx(request):
            headers = {"HX-Retarget": "#alerts", "HX-Reswap": "innerHTML"}
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
