"""The v2 Kalendarz (docs/design/v2-spec.md, section 8.9; ADR-0035): a secret link to a project's
calendar feed, made on request, copied, and revoked by a new nonce; the feed itself, which a
calendar fetches without a session, so the link's token is its only key. It holds the deadline,
the plan's task starts and ends, absences as names and dates (never reasons), the validity dates
of the decisions waiting and the weekly report reminder (Thursday 17:00 unless changed). It works
in the demo for as long as the visitor's sandbox lives."""

import secrets
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import Response

from sentinel.app.errors import AppError
from sentinel.app.events import OPEN
from sentinel.app.feed import Entry, calendar, next_weekday
from sentinel.app.models import Language
from sentinel.app.security import calendar_token, calendar_valid, load_key
from sentinel.app.store import CalendarRow
from sentinel.app.ui.core import Ui
from sentinel.app.ui.v2.decision import validity_view
from sentinel.app.ui.v2.plan import end_of
from sentinel.app.ui.v2.shell import PREFIX
from sentinel.app.ui.v2.text import TextsV2
from sentinel.app.views import ProjectView

FEED_PREFIX = "/calendar/"


def feed_path(project_id: str, token: str, language: str) -> str:
    return f"{FEED_PREFIX}{project_id}/{token}.ics?lang={language}"


def entries_of(
    t: TextsV2, view: ProjectView, valid: dict[int, date], row: CalendarRow, today: date
) -> list[Entry]:
    """The events of a project's feed; `valid` holds the validity date of each decision
    waiting, by its recommendation."""
    pid = view.id
    found: list[Entry] = []
    deadline = view.definition.deadline
    if deadline is not None:
        summary = t("v2.cal.deadline", project=view.name)
        found.append(Entry(f"{pid}-deadline@sentinel", summary, deadline, deadline))
    for task in view.tasks:
        if task.state in ("done", "removed"):
            continue
        if task.state == "not_started" and task.planned_start is not None:
            start = task.planned_start
            summary = t("v2.cal.start", task=task.name)
            found.append(Entry(f"{pid}-start-{task.key}@sentinel", summary, start, start))
        end = end_of(task)
        if end is not None:
            summary = t("v2.cal.end", task=task.name)
            found.append(Entry(f"{pid}-end-{task.key}@sentinel", summary, end, end))
    for person in view.people:
        for absence in person.absences:
            first = absence.first_day
            uid = f"{pid}-away-{person.key}-{first:%Y%m%d}@sentinel"
            if absence.return_date is None:
                summary = t("v2.cal.away_open", name=person.name)
                found.append(Entry(uid, summary, first, first))
            else:
                last = max(first, absence.return_date - timedelta(days=1))
                found.append(Entry(uid, t("v2.cal.away", name=person.name), first, last))
    titles = {rec.seq: rec.title for rec in view.recommendations}
    for seq, day in valid.items():
        summary = t("v2.cal.valid", title=titles.get(seq, ""))
        found.append(Entry(f"{pid}-valid-{seq}@sentinel", summary, day, day))
    first_report = next_weekday(max(today, view.definition.start), row.reminder_day)
    found.append(
        Entry(
            f"{pid}-report@sentinel",
            t("v2.cal.report", project=view.name),
            first_report,
            first_report,
            t("v2.cal.report_text"),
            at=row.reminder_time,
            weekly=row.reminder_day,
        )
    )
    return found


def router(ui: Ui) -> APIRouter:
    routes = APIRouter()
    services = ui.services
    key = load_key(ui.config.secret_file)

    def calendar_row(request: Request, project_id: str) -> CalendarRow:
        found = services.store.calendar(ui.session(request), project_id)
        if found is None:
            raise AppError("project_not_found", "not_found")
        return found

    def back(request: Request, project_id: str, done: str) -> Response:
        target = f"{PREFIX}/projects/{project_id}/settings"
        return ui.redirect(request, target, done=done)

    @routes.post(PREFIX + "/projects/{project_id}/calendar")
    def make_link(request: Request, project_id: str) -> Response:
        """A new secret link; any older one stops working."""
        row = calendar_row(request, project_id)
        nonce = secrets.token_urlsafe(18)
        changed = CalendarRow(row.project, row.session, nonce, row.reminder_day, row.reminder_time)
        services.store.save_calendar(ui.session(request), changed)
        return back(request, project_id, "calendar")

    @routes.post(PREFIX + "/projects/{project_id}/calendar/revoke")
    def revoke(request: Request, project_id: str) -> Response:
        """ "Unieważnij link": the nonce goes, so the link's token matches nothing any more."""
        row = calendar_row(request, project_id)
        changed = CalendarRow(row.project, row.session, None, row.reminder_day, row.reminder_time)
        services.store.save_calendar(ui.session(request), changed)
        return back(request, project_id, "revoked")

    @routes.get(FEED_PREFIX + "{project_id}/{token}.ics")
    def feed(request: Request, project_id: str, token: str) -> Response:
        """The feed a calendar subscribes to: no session, only the link's token."""
        row = services.store.calendar_feed(project_id)
        if row is None or not calendar_valid(key, project_id, row.nonce, token):
            return Response("Not found\n", status_code=404, media_type="text/plain")
        language: Language = "en" if request.query_params.get("lang") == "en" else "pl"
        t = TextsV2(language)
        view = services.live(row.session, project_id, language)
        state = services.state(row.session, project_id)
        if any(entry.status in OPEN and entry.validity is None for entry in state.recommendations):
            # The validity is computed after a recommendation (spec 11.8); a later fetch has it.
            services.validity_job(row.session, project_id, language)
            state = services.state(row.session, project_id)
        today = date.today()
        valid = {}
        for entry in state.recommendations:
            if entry.status in OPEN:
                day = validity_view(state.project, entry, today).valid
                if day is not None:
                    valid[entry.seq] = day
        rows = services.store.events(row.session, project_id)
        stamp = rows[-1].created if rows else datetime.now()
        text = calendar(
            t("v2.cal.name", project=view.name),
            entries_of(t, view, valid, row, today),
            stamp,
        )
        headers = {
            "Content-Disposition": 'inline; filename="sentinel.ics"',
            "Cache-Control": "private, max-age=300",
        }
        return Response(text, media_type="text/calendar; charset=utf-8", headers=headers)

    return routes


def link_of(ui: Ui, request: Request, row: CalendarRow) -> str | None:
    """The full address of a project's calendar link, None without one."""
    if row.nonce is None:
        return None
    token = calendar_token(load_key(ui.config.secret_file), row.project, row.nonce)
    base = str(request.base_url).rstrip("/")
    return base + feed_path(row.project, token, ui.language(request))
