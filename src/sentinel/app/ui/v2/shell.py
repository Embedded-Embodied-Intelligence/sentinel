"""The frame of the v2 pages (docs/design/v2-spec.md, sections 5 and 7; ADR-0033): the theme
remembered in a cookie, the sidebar, the project header and tabs, the live banner, and the calm
"Wkrótce" placeholder of the screens WP16 builds."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import Response

from sentinel.app.errors import AppError
from sentinel.app.events import Recommended, parse, replay
from sentinel.app.ui.core import Ui, local_path
from sentinel.app.ui.v2.numbers import per_hundred, state_of
from sentinel.app.ui.v2.text import TextsV2
from sentinel.app.views import ProjectView

Theme = Literal["light", "dark", "system"]
THEMES: tuple[Theme, ...] = ("light", "dark", "system")
THEME_COOKIE = "sentinel_theme"
PREFIX = "/v2"
GATE = 0  # every deliberation v2 asks for: every action needs approval (spec section 11.8)
BANNER_POLL_S = 20
BANNER_MOVE = 10  # a change of the chance in 100 the banner reports (section 7)
# The tabs of a project (section 7) and the screens of WP16 that are placeholders for now, with
# the page of the first interface that does their work meanwhile.
TABS = ("overview", "report", "decisions", "log", "plan", "settings")
SOON_TABS = {"settings": "settings"}
SOON_PAGES = {"lab": "/simulator", "settings": "/settings"}


def theme_of(request: Request) -> Theme:
    value = request.cookies.get(THEME_COOKIE)
    return next((theme for theme in THEMES if theme == value), "light")


def texts(request: Request) -> TextsV2:
    return TextsV2(Ui.language(request))


def page(ui: Ui, request: Request, template: str, status: int = 200, **values: Any) -> Response:
    """A v2 page (or a fragment, names starting with "_") with the v2 texts and frame."""
    t = texts(request)
    frame: dict[str, Any] = {
        "t": t,
        "theme": theme_of(request),
        "themes": THEMES,
        "prefix": PREFIX,
        "nav": "",
        "banner_since": datetime.now(UTC).isoformat(timespec="seconds"),
        "banner_poll": BANNER_POLL_S,
        "tab": None,
        "project": None,
        "notice": None,
    }
    frame.update(values)
    return ui.page(request, f"v2/{template}", status, **frame)


@dataclass(frozen=True)
class Header:
    """The header of a project page: its id, name, and the status moment in words."""

    id: str
    name: str
    as_of: str


def header(ui: Ui, request: Request, view: ProjectView) -> Header:
    """The header of a project: "stan na {date}, {time}", the status date with the time the
    project last changed."""
    t = texts(request)
    rows = ui.services.store.events(ui.session(request), view.id)
    moment = rows[-1].created.astimezone() if rows else datetime.now().astimezone()
    day = view.checkins[-1].date if view.checkins else view.as_of  # the latest report's date
    as_of = f"{t.date(day)}, {moment:%H:%M}"
    return Header(view.id, view.name, t("v2.as_of", moment=as_of))


@dataclass(frozen=True)
class BannerItem:
    text: str
    href: str


def banner_items(ui: Ui, request: Request, since: datetime) -> list[BannerItem]:
    """What happened since `since` that the banner reports (section 7): a new decision still
    waiting, and a report that moved the chance by at least 10 in 100 or changed the state."""
    t = texts(request)
    services = ui.services
    session = ui.session(request)
    found: list[BannerItem] = []
    for summary in services.projects(session):
        if summary.kind != "live" or summary.updated < since:
            continue
        rows = services.store.events(session, summary.id)
        fresh = [row for row in rows if row.created > since]
        if not fresh:
            continue
        state = replay(rows)
        base = f"{PREFIX}/projects/{summary.id}"
        for row in fresh:
            if row.type == "recommendation":
                event = parse(row)
                entry = state.recommendation(row.seq)
                if (
                    isinstance(event, Recommended)
                    and entry is not None
                    and entry.status
                    in (
                        "open",
                        "later",
                    )
                ):
                    text = t("v2.banner.decision", project=summary.name)
                    found.append(BannerItem(text, f"{base}/decisions/{row.seq}"))
            elif row.type == "checkin":
                moved = chance_move(ui, summary.id, rows, row.seq)
                if moved is not None:
                    before, after = moved
                    if abs(after - before) >= BANNER_MOVE:
                        key = "v2.banner.fell" if after < before else "v2.banner.rose"
                        text = t(key, project=summary.name, before=before, after=after)
                        found.append(BannerItem(text, base))
                    elif state_of(after) != state_of(before):
                        word = t(f"v2.state.{state_of(after)}")
                        found.append(
                            BannerItem(t("v2.banner.state", project=summary.name, state=word), base)
                        )
    return found


def chance_move(ui: Ui, project_id: str, rows: list[Any], seq: int) -> tuple[int, int] | None:
    """The chance in 100 before and after the check-in at `seq` (forecasts are cached)."""
    services = ui.services
    before = replay([r for r in rows if r.seq < seq])
    after = replay([r for r in rows if r.seq <= seq])
    first, then = services.chance_of(project_id, before), services.chance_of(project_id, after)
    if first is None or then is None:
        return None
    return per_hundred(first), per_hundred(then)


def router(ui: Ui) -> APIRouter:
    routes = APIRouter()

    @routes.get(PREFIX + "/theme/{value}")
    def theme(request: Request, value: str) -> Response:
        """Remember the appearance in a cookie, so the server renders it without a flash."""
        target = local_path(request.query_params.get("next"), PREFIX)
        response = ui.redirect(request, target)
        if value in THEMES:
            response.set_cookie(THEME_COOKIE, value, max_age=365 * 24 * 3600, samesite="lax")
        return response

    @routes.get(PREFIX + "/banner")
    def banner(request: Request) -> Response:
        """The live banner, polled every 20 s by the open page with the moment it last saw."""
        try:
            since = datetime.fromisoformat(request.query_params.get("since", ""))
        except ValueError:
            since = datetime.now(UTC)
        if since.tzinfo is None:
            since = since.replace(tzinfo=UTC)
        now = datetime.now(UTC).isoformat(timespec="seconds")
        items = banner_items(ui, request, since)
        return page(ui, request, "_banner.html", items=items, banner_since=now)

    def soon(request: Request, nav: str, old: str, **values: Any) -> Response:
        return page(
            ui,
            request,
            "soon.html",
            title=texts(request)("v2.soon.title"),
            nav=nav,
            old=old,
            **values,
        )

    @routes.get(PREFIX + "/lab")
    def lab_soon(request: Request) -> Response:
        return soon(request, "lab", SOON_PAGES["lab"])

    @routes.get(PREFIX + "/settings")
    def settings_soon(request: Request) -> Response:
        return soon(request, "settings", SOON_PAGES["settings"])

    @routes.get(PREFIX + "/projects/{project_id}/{tab}")
    def tab_soon(request: Request, project_id: str, tab: str) -> Response:
        if tab not in SOON_TABS:
            raise AppError("project_not_found", "not_found")
        view = ui.services.live(ui.session(request), project_id, ui.language(request))
        old = f"/projects/{project_id}/{SOON_TABS[tab]}"
        return soon(
            request,
            "projects",
            old,
            project=header(ui, request, view),
            tab=tab,
        )

    return routes
