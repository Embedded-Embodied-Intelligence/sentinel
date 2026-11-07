"""The v2 Start page and the project list (docs/design/v2-spec.md, section 8.1): the decisions of
every project sorted by their validity date (a hard date, never an AI's judgement), the project
tiles, the recent events of the log, and three large cards on the first visit."""

from dataclasses import dataclass
from datetime import date, datetime

from fastapi import APIRouter, Request
from fastapi.responses import Response

from sentinel.app import showcase
from sentinel.app.events import OPEN, Decided, LiveState, parse
from sentinel.app.ui.core import Ui
from sentinel.app.ui.text import MINUS
from sentinel.app.ui.v2.decision import Validity, validity_view
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


@dataclass(frozen=True)
class FeedItem:
    when: datetime
    actor: str
    text: str
    href: str


def effect_of(t: TextsV2, view: ProjectView, seq: int) -> str:
    rec = next((r for r in view.recommendations if r.seq == seq), None)
    if rec is None or rec.with_action is None or rec.without is None:
        return ""
    gain = per_hundred(rec.with_action.p_on_time) - per_hundred(rec.without.p_on_time)
    return t("v2.chance.value", n=f"{gain:+d}".replace("-", MINUS))


def feed(t: TextsV2, view: ProjectView, state: LiveState, rows: list) -> list[FeedItem]:  # type: ignore[type-arg]
    """The project's log as people read it (sections 3 and 8.1): who did what, and when."""
    you, sentinel = t("v2.actor.you"), t("v2.actor.sentinel")
    base = f"{PREFIX}/projects/{view.id}"
    titles = {r.seq: r.title for r in view.recommendations}
    acts = {r.seq for r in view.recommendations if r.acts}
    found: list[FeedItem] = []
    checkin_times = [row.created for row in rows if row.type == "checkin"]
    for row in rows:
        kind = row.type
        name = f"{view.name}: "
        if kind == "created":
            found.append(FeedItem(row.created, you, name + t("v2.event.created"), base))
        elif kind == "baseline":
            found.append(FeedItem(row.created, sentinel, name + t("v2.event.plan"), base))
        elif kind == "checkin":
            day = date.fromisoformat(row.payload["checkin"]["date"])
            found.append(
                FeedItem(row.created, you, name + t("v2.event.report", date=t.date(day)), base)
            )
        elif kind == "recommendation":
            title = titles.get(row.seq, "")
            entry = state.recommendation(row.seq)
            if entry is not None and entry.status == "auto":
                text = t("v2.event.auto", title=title)
            elif row.seq in acts:
                text = t("v2.event.proposal", title=title)
            else:
                text = t("v2.event.no_change")
            found.append(
                FeedItem(
                    row.created,
                    sentinel,
                    name + text,
                    f"{base}/decisions/{row.seq}" if row.seq in acts else base,
                )
            )
            if entry is not None and entry.status == "superseded":
                later = next((when for when in checkin_times if when > row.created), None)
                if later is not None:
                    text = t("v2.event.superseded", title=title)
                    found.append(
                        FeedItem(later, sentinel, name + text, f"{base}/decisions/{row.seq}")
                    )
        elif kind in ("decision", "correction", "expiry", "undo"):
            event = parse(row)
            seq = getattr(event, "recommendation", 0)
            title = titles.get(seq, "")
            href = f"{base}/decisions/{seq}"
            if isinstance(event, Decided):
                if event.verdict == "approve":
                    key = "v2.event.discarded" if event.discarded else "v2.event.approved"
                    text = t(key, title=title)
                elif event.verdict == "reject":
                    if event.reason is not None:
                        text = t(
                            "v2.event.rejected_why",
                            title=title,
                            reason=t(f"v2.reject.{event.reason}").lower(),
                        )
                    else:
                        text = t("v2.event.rejected", title=title)
                else:
                    text = t("v2.event.postponed", title=title)
                found.append(FeedItem(row.created, you, name + text, href))
            elif kind == "correction":
                found.append(
                    FeedItem(row.created, you, name + t("v2.event.adjusted", title=title), href)
                )
            elif kind == "expiry":
                found.append(
                    FeedItem(row.created, sentinel, name + t("v2.event.expired", title=title), href)
                )
            else:
                found.append(
                    FeedItem(row.created, you, name + t("v2.event.undone", title=title), href)
                )
        elif kind == "definition":
            found.append(FeedItem(row.created, you, name + t("v2.event.definition"), base))
    return found


@dataclass(frozen=True)
class Overview:
    tiles: list[Tile]
    todos: list[Todo]
    events: list[FeedItem]


def overview(ui: Ui, request: Request, with_feed: bool = True) -> Overview:
    """The live projects of the session in the order they were created, their pending
    decisions by validity date (unknown dates last) and the latest events of their logs."""
    services = ui.services
    session, language = ui.session(request), ui.language(request)
    t = texts(request)
    today = date.today()
    tiles: list[Tile] = []
    todos: list[Todo] = []
    events: list[FeedItem] = []
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
            events += feed(t, view, state, rows)
    todos.sort(key=lambda todo: todo.order)
    rank = {id(item): i for i, item in enumerate(events)}  # the log's order breaks ties
    events.sort(key=lambda item: (item.when, rank[id(item)]), reverse=True)
    return Overview(tiles, todos, events[:EVENTS_SHOWN])


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
