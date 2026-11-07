"""The v2 Start page and the project list (docs/design/v2-spec.md, section 8.1)."""

from dataclasses import dataclass

from fastapi import APIRouter, Request
from fastapi.responses import Response

from sentinel.app.ui.core import Ui
from sentinel.app.ui.v2.shell import PREFIX, page, texts
from sentinel.app.ui.v2.status import Status, status


@dataclass(frozen=True)
class Tile:
    """A project on Start: its link, name, status and the decisions waiting."""

    id: str
    name: str
    href: str
    status: Status
    pending: int


def tiles(ui: Ui, request: Request) -> list[Tile]:
    """The live projects of the session in the order they were created."""
    services = ui.services
    session, language = ui.session(request), ui.language(request)
    t = texts(request)
    found = []
    for summary in services.projects(session):
        if summary.kind != "live":
            continue
        view = services.live(session, summary.id, language)
        href = f"{PREFIX}/projects/{summary.id}" if view.has_plan else f"{PREFIX}/new/{summary.id}"
        pending = sum(1 for r in view.recommendations if r.status in ("open", "later"))
        found.append(Tile(summary.id, view.name, href, status(ui, request, view, t), pending))
    return found


def router(ui: Ui) -> APIRouter:
    routes = APIRouter()

    @routes.get(PREFIX)
    def start(request: Request) -> Response:
        t = texts(request)
        return page(
            ui,
            request,
            "start.html",
            title=t("v2.start.title"),
            nav="start",
            tiles=tiles(ui, request),
        )

    @routes.get(PREFIX + "/projects")
    def projects(request: Request) -> Response:
        t = texts(request)
        return page(
            ui,
            request,
            "projects.html",
            title=t("v2.nav.projects"),
            nav="projects",
            tiles=tiles(ui, request),
        )

    return routes
