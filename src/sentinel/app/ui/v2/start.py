"""The v2 Start page and the project list (docs/design/v2-spec.md, section 8.1): the decisions of
every project sorted by their validity date (a hard date, never an AI's judgement), the project
tiles, the recent events of the log, and three large cards on the first visit."""

from dataclasses import dataclass
from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import Response

from sentinel.app import showcase
from sentinel.app.events import OPEN
from sentinel.app.ui.core import Ui
from sentinel.app.ui.text import MINUS
from sentinel.app.ui.v2.decision import Validity, validity_view
from sentinel.app.ui.v2.log import LogItem, entries
from sentinel.app.ui.v2.numbers import per_hundred
from sentinel.app.ui.v2.shell import PREFIX, page, texts
from sentinel.app.ui.v2.status import Status, status
from sentinel.app.ui.v2.text import TextsV2
from sentinel.app.views import ProjectView

EVENTS_SHOWN = 8


@dataclass(frozen=True)
class Tile:
    """A project on Start: its link, name, status and the decisions waiting."""

    id: str
    name: str
    href: str
    status: Status
    pending: int


@dataclass(frozen=True)
class Todo:
    """A decision to make on Start: its project, words, effect and validity."""

    href: str
    project: str
    title: str
    effect: str
    validity: Validity
    order: tuple[int, date]


def effect_of(t: TextsV2, view: ProjectView, seq: int) -> str:
    rec = next((r for r in view.recommendations if r.seq == seq), None)
    if rec is None or rec.with_action is None or rec.without is None:
        return ""
    gain = per_hundred(rec.with_action.p_on_time) - per_hundred(rec.without.p_on_time)
    return t("v2.chance.value", n=f"{gain:+d}".replace("-", MINUS))


@dataclass(frozen=True)
class Overview:
    tiles: list[Tile]
    todos: list[Todo]
    events: list[LogItem]


def overview(ui: Ui, request: Request, with_feed: bool = True) -> Overview:
    """The live projects of the session in the order they were created, their pending
    decisions by validity date (unknown dates last) and the latest events of their logs."""
    services = ui.services
    session, language = ui.session(request), ui.language(request)
    t = texts(request)
    today = date.today()
    tiles: list[Tile] = []
    todos: list[Todo] = []
    events: list[LogItem] = []
    for summary in services.projects(session):
        if summary.kind != "live":
            continue
        services.expire(session, summary.id, today)
        view = services.live(session, summary.id, language)
        state = services.state(session, summary.id)
        href = f"{PREFIX}/projects/{summary.id}" if view.has_plan else f"{PREFIX}/new/{summary.id}"
        pending = [entry for entry in state.recommendations if entry.status in OPEN]
        tiles.append(Tile(summary.id, view.name, href, status(ui, request, view, t), len(pending)))
        titles = {r.seq: r.title for r in view.recommendations}
        if any(entry.validity is None for entry in pending):
            services.validity_job(session, summary.id, language)  # computed in the background
            state = services.state(session, summary.id)
            pending = [entry for entry in state.recommendations if entry.status in OPEN]
        for entry in pending:
            valid = validity_view(state.project, entry, today)
            order = (0, valid.valid) if valid.valid is not None else (1, date.max)
            todos.append(
                Todo(
                    f"{PREFIX}/projects/{summary.id}/decisions/{entry.seq}",
                    view.name,
                    titles.get(entry.seq, ""),
                    effect_of(t, view, entry.seq),
                    valid,
                    order,
                )
            )
        if with_feed:
            rows = services.store.events(session, summary.id)
            events += entries(t, view, state, rows)
    todos.sort(key=lambda todo: todo.order)
    rank = {id(item): i for i, item in enumerate(events)}  # the log's order breaks ties
    events.sort(key=lambda item: (item.when, rank[id(item)]), reverse=True)
    return Overview(tiles, todos, events[:EVENTS_SHOWN])


def deleted_notice(t: TextsV2) -> dict[str, str]:
    return {"tone": "good", "icon": "check-circle", "text": t("v2.psettings.deleted")}


def router(ui: Ui) -> APIRouter:
    routes = APIRouter()

    @routes.get(PREFIX)
    def start(request: Request) -> Response:
        t = texts(request)
        found = overview(ui, request)
        return page(
            ui,
            request,
            "start.html",
            title=t("v2.start.title"),
            nav="start",
            tiles=found.tiles,
            todos=found.todos,
            events=found.events,
            today=date.today(),
            notice=deleted_notice(t) if request.query_params.get("done") == "deleted" else None,
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
            tiles=overview(ui, request, with_feed=False).tiles,
        )

    @routes.post(PREFIX + "/example")
    def example(request: Request) -> Response:
        """ "Otwórz projekt przykładowy": a copy of the showcase in the visitor's language."""
        session, language = ui.session(request), ui.language(request)
        log = showcase.events(language)
        store = ui.services.store
        name = showcase.definition(language).name
        row = store.create_project(session, "live", name, log[0][0], log[0][1])
        for event_type, payload in log[1:]:
            store.append(session, row.id, event_type, payload)
        return ui.redirect(request, f"{PREFIX}/projects/{row.id}")

    return routes
