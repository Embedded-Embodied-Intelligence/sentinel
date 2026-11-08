"""The v2 Dziennik (docs/design/v2-spec.md, section 8.6; spec section 11.8): a project's log, or
every project's, as people read it: when, who ("Ty" / "Sentinel"), one sentence and the effect on
the chance, grouped by day with the newest first; each decision's brief as it was and its fate
one click away; the chance over time with a dot per report and approved decision; and the log as
CSV (the record of a human-overseen system, AI Act Art. 12). Start shows its latest entries."""

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response

from sentinel.app.errors import AppError
from sentinel.app.events import (
    Created,
    Decided,
    DefinitionChanged,
    LiveState,
    RecommendationEntry,
    parse,
)
from sentinel.app.models import CheckIn, ProjectDefinition
from sentinel.app.services import ChanceStep
from sentinel.app.store import EventRow
from sentinel.app.ui.core import Ui
from sentinel.app.ui.project import checkin_item, definition_changes
from sentinel.app.ui.v2.decision import brief_chips, lifecycle_state, validity_view
from sentinel.app.ui.v2.numbers import per_hundred, state_of
from sentinel.app.ui.v2.overview import Chip, decision_chips, tone_of
from sentinel.app.ui.v2.shell import PREFIX, header, page, texts
from sentinel.app.ui.v2.text import TextsV2
from sentinel.app.views import ProjectView

FILTERS = ("all", "decisions", "reports", "plan")
KINDS = {
    "created": "plan",
    "baseline": "plan",
    "definition": "plan",
    "undo": "plan",
    "checkin": "reports",
    "recommendation": "decisions",
    "decision": "decisions",
    "correction": "decisions",
    "expiry": "decisions",
}
CSV_COLUMNS = (
    *("date", "time", "project", "who", "kind", "event"),
    *("before", "after", "fate", "reason", "words"),
)
FORMULA = ("=", "+", "-", "@", "\t", "\r")  # a CSV cell starting so is read as a formula


@dataclass(frozen=True)
class Detail:
    """What an entry expands to: a report's items or a change in words, the brief of a decision
    as it was (the chance, the end and the budget without and with it, its validity and cost of
    delay) and its fate with the reason and the manager's words."""

    lines: list[str] = field(default_factory=list)
    chips: list[Chip] = field(default_factory=list)
    valid: date | None = None
    delay: int | None = None
    fate: str | None = None
    reason: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class LogItem:
    """An entry of the log: when, who, the sentence and where it leads; for the Dziennik also
    the event it comes from, its kind (a filter), anchor, project, effect chip, details, the
    chance in 100 before and after and the project day it belongs to (a report's date)."""

    when: datetime
    actor: str
    text: str
    href: str
    event: str = ""
    kind: str = "plan"
    anchor: str = ""
    project: str = ""
    chip: Chip | None = None
    detail: Detail | None = None
    before: int | None = None
    after: int | None = None
    day: date | None = None


def entries(
    t: TextsV2,
    view: ProjectView,
    state: LiveState,
    rows: list[EventRow],
    steps: dict[int, ChanceStep] | None = None,
    with_name: bool = True,
) -> list[LogItem]:
    """The project's log as people read it (sections 3, 8.1 and 8.6), in the log's order; with
    `steps` (the chance before and after each report) a report has its effect chip."""
    you, sentinel = t("v2.actor.you"), t("v2.actor.sentinel")
    base = f"{PREFIX}/projects/{view.id}"
    recs = {r.seq: r for r in view.recommendations}
    acts = {r.seq for r in view.recommendations if r.acts}
    by_seq = {entry.seq: entry for entry in state.recommendations}
    project = state.project
    names = {task.key: task.name for task in view.tasks}  # a draft without tasks has no network
    people = {p.key: p.name for p in project.definition.team}
    decided: dict[int, Decided] = {}
    for row in rows:
        if row.type == "decision":
            event = parse(row)
            assert isinstance(event, Decided)
            decided[event.recommendation] = event
    checkin_times = [row.created for row in rows if row.type == "checkin"]
    prefix = f"{view.name}: " if with_name else ""
    found: list[LogItem] = []
    current: ProjectDefinition | None = None
    chances: tuple[int | None, int | None]

    def add(
        row: EventRow,
        actor: str,
        text: str,
        href: str = base,
        chip: Chip | None = None,
        detail: Detail | None = None,
        chances: tuple[int | None, int | None] = (None, None),
        day: date | None = None,
    ) -> None:
        anchor = f"e-{view.id}-{row.seq}"
        kind = KINDS.get(row.type, "plan")
        before, after = chances
        found.append(
            LogItem(
                row.created,
                actor,
                prefix + text,
                href,
                row.type,
                kind,
                anchor,
                view.name,
                chip,
                detail,
                before,
                after,
                day,
            )
        )

    for row in rows:
        kind = row.type
        if kind == "created":
            event = parse(row)
            assert isinstance(event, Created)
            current = event.definition
            add(row, you, t("v2.event.created"), day=current.start)
        elif kind == "baseline":
            add(row, sentinel, t("v2.event.plan"), day=project.definition.start)
        elif kind == "definition":
            event = parse(row)
            assert isinstance(event, DefinitionChanged)
            lines = [] if current is None else definition_changes(current, event.definition, t)
            current = event.definition
            add(row, you, "; ".join(lines) if lines else t("v2.event.definition"))
        elif kind == "checkin":
            checkin = CheckIn.model_validate(row.payload["checkin"])
            lines = checkin_item(checkin, project, names, people, t).lines
            step = (steps or {}).get(row.seq)
            chip, chances = None, (None, None)
            if step is not None:
                after = per_hundred(step.after)
                before = None if step.before is None else per_hundred(step.before)
                chances = (before, after)
                if before is not None:
                    text = t("v2.effect.chance", before=before, after=after)
                    chip = Chip(text, tone_of(after - before))
            text = t("v2.event.report", date=t.date(checkin.date))
            add(row, you, text, chip=chip, detail=Detail(lines), chances=chances, day=checkin.date)
        elif kind == "recommendation":
            rec, entry = recs.get(row.seq), by_seq.get(row.seq)
            title = rec.title if rec is not None else ""
            href = f"{base}/decisions/{row.seq}" if row.seq in acts else base
            if entry is not None and entry.status == "auto":
                text = t("v2.event.auto", title=title)
            elif row.seq in acts:
                text = t("v2.event.proposal", title=title)
            else:
                text = t("v2.event.no_change")
            if rec is not None and entry is not None and row.seq in acts:
                chips = decision_chips(t, rec, view.person_days)
                detail = proposal_detail(t, state, entry, chips, decided.get(row.seq))
                chances = (None, None)
                if rec.without is not None and rec.with_action is not None:
                    chances = (
                        per_hundred(rec.without.p_on_time),
                        per_hundred(rec.with_action.p_on_time),
                    )
                chip = chips[0] if chips else None
                add(row, sentinel, text, href, chip, detail, chances, rec.as_of)
            else:
                add(row, sentinel, text, href, day=None if rec is None else rec.as_of)
            if entry is not None and entry.status == "superseded":
                later = next((when for when in checkin_times if when > row.created), None)
                if later is not None:
                    gone = prefix + t("v2.event.superseded", title=title)
                    kind_of = ("superseded", "decisions", "", view.name)
                    found.append(LogItem(later, sentinel, gone, href, *kind_of))
        elif kind in ("decision", "correction", "expiry", "undo"):
            event = parse(row)
            seq = int(getattr(event, "recommendation", 0))
            rec = recs.get(seq)
            title = rec.title if rec is not None else ""
            href = f"{base}/decisions/{seq}"
            day = None if rec is None else rec.as_of
            if isinstance(event, Decided):
                text, detail, chances = decision_words(t, view, state, event, title)
                chip = detail.chips[0] if detail.chips and detail.fate == "approved" else None
                add(row, you, text, href, chip, detail, chances, day)
            elif kind == "correction":
                add(row, you, t("v2.event.adjusted", title=title), href, day=day)
            elif kind == "expiry":
                add(row, sentinel, t("v2.event.expired", title=title), href, day=day)
            else:
                add(row, you, t("v2.event.undone", title=title), href, day=day)
    return merged(found)


def merged(items: list[LogItem]) -> list[LogItem]:
    """Consecutive saves of the project's details (autosave) are one entry, the latest."""
    out: list[LogItem] = []
    for entry in items:
        if out and entry.event == out[-1].event == "definition" and entry.text == out[-1].text:
            out[-1] = entry
            continue
        out.append(entry)
    return out


def proposal_detail(
    t: TextsV2,
    state: LiveState,
    entry: RecommendationEntry,
    chips: list[Chip],
    decided: Decided | None,
) -> Detail:
    """A proposal's brief (its effect against no change, validity, cost of delay) and its fate
    now: still waiting, or what the manager or time made of it."""
    today = date.today()
    valid = validity_view(state.project, entry, today)
    reason = note = None
    if decided is not None:
        if decided.reason is not None:
            reason = t(f"v2.reject.{decided.reason}")
        note = decided.note
    fate = lifecycle_state(entry, None, today)
    return Detail([], chips, valid.valid, valid.delay, fate, reason, note)


def decision_words(
    t: TextsV2, view: ProjectView, state: LiveState, event: Decided, title: str
) -> tuple[str, Detail, tuple[int | None, int | None]]:
    """The manager's decision in words, with the brief as it was at that moment (section 3)."""
    if event.verdict == "approve":
        fate = "discarded" if event.discarded else "approved"
        text = t(f"v2.event.{fate}", title=title)
    elif event.verdict == "reject":
        fate = "rejected"
        if event.reason is not None:
            word = t(f"v2.reject.{event.reason}").lower()
            text = t("v2.event.rejected_why", title=title, reason=word)
        else:
            text = t("v2.event.rejected", title=title)
    else:
        fate = "postponed"
        text = t("v2.event.postponed", title=title)
    chips: list[Chip] = []
    valid = delay = None
    chances: tuple[int | None, int | None] = (None, None)
    brief = event.brief
    if brief is not None:
        chips = brief_chips(t, state.project, brief, view.person_days)
        if brief.valid_day is not None:
            valid = state.project.calendar.date_of(brief.valid_day)
        delay = None if brief.delay is None else per_hundred(brief.delay)
        chances = (per_hundred(brief.p_before), per_hundred(brief.p_after))
    reason = None if event.reason is None else t(f"v2.reject.{event.reason}")
    return text, Detail([], chips, valid, delay, fate, reason, event.note), chances


# --------------------------------------------------------------------------- the chart


@dataclass(frozen=True)
class Point:
    """A dot of "Szansa w czasie": its place, chance in 100, state, date label, the entry it
    leads to and what it is in words (its link's name)."""

    x: float
    y: float
    n: int
    state: str
    label: str
    anchor: str
    name: str


@dataclass(frozen=True)
class Chart:
    points: list[Point]
    path: str
    width: int
    height: int
    top: float
    bottom: float
    left: float
    right: float
    lines: list[tuple[int, float]]  # the thresholds of the states (80, 50) and their y


WIDTH, HEIGHT = 880, 232
LEFT, RIGHT, TOP, BOTTOM = 44.0, 28.0, 30.0, 192.0


def chance_chart(t: TextsV2, items: list[LogItem], plan: float | None) -> Chart | None:
    """The chance of the deadline over the log (section 8.6): the plan's, then one dot per
    report and per approved decision in the log's order, each linked to its entry."""
    marks: list[tuple[int, str, str, str]] = []  # n, label, anchor, name
    first = next((i for i in items if i.event == "baseline"), None)
    if plan is not None and first is not None:
        n = per_hundred(plan)
        name = t("v2.log.chart.dot", what=first.text, n=n)
        marks.append((n, t("v2.log.chart.plan"), first.anchor, name))
    for entry in items:
        if entry.after is None or entry.day is None:
            continue
        approved = entry.event == "decision" and (entry.detail or Detail()).fate == "approved"
        if entry.event == "checkin" or approved:
            name = t("v2.log.chart.dot", what=entry.text, n=entry.after)
            marks.append((entry.after, t.day_month(entry.day), entry.anchor, name))
    if not marks:
        return None
    span = WIDTH - LEFT - RIGHT
    count = len(marks)

    def y_of(n: int) -> float:
        return round(TOP + (100 - n) / 100 * (BOTTOM - TOP), 1)

    points = []
    for i, (n, label, anchor, name) in enumerate(marks):
        x = round(LEFT + (span / 2 if count == 1 else i * span / (count - 1)), 1)
        points.append(Point(x, y_of(n), n, state_of(n), label, anchor, name))
    path = " ".join(f"{'M' if i == 0 else 'L'}{p.x},{p.y}" for i, p in enumerate(points))
    lines = [(n, y_of(n)) for n in (80, 50)]
    return Chart(points, path, WIDTH, HEIGHT, TOP, BOTTOM, LEFT, WIDTH - RIGHT, lines)


# --------------------------------------------------------------------------- pages


@dataclass(frozen=True)
class Day:
    day: date
    items: list[LogItem]


def by_day(items: list[LogItem]) -> list[Day]:
    """Entries under the day they were recorded, the newest first (the log's order breaks
    ties of one moment)."""
    rank = {id(entry): i for i, entry in enumerate(items)}
    days: list[Day] = []
    for entry in sorted(items, key=lambda i: (i.when, rank[id(i)]), reverse=True):
        day = entry.when.astimezone().date()
        if not days or days[-1].day != day:
            days.append(Day(day, []))
        days[-1].items.append(entry)
    return days


def project_log(
    ui: Ui, request: Request, project_id: str, with_name: bool
) -> tuple[list[LogItem], Chart | None]:
    """A project's entries and its chart; the chance of each report from its forecasts, which
    are deterministic for the log's states and cached."""
    services = ui.services
    session, language = ui.session(request), ui.language(request)
    t = texts(request)
    services.expire(session, project_id, date.today())
    view = services.live(session, project_id, language)
    state = services.state(session, project_id)
    rows = services.store.events(session, project_id)
    steps: list[ChanceStep] = []
    plan = None
    if view.has_plan:
        steps, _ = services.chance_history(session, project_id)
        plan = steps[0].before if steps else services.chance_of(project_id, state)
    items = entries(t, view, state, rows, {s.seq: s for s in steps}, with_name)
    return items, chance_chart(t, items, plan)


def csv_of(t: TextsV2, items: list[LogItem]) -> str:
    """The log as CSV, oldest first: dates ISO 8601, chances in 100, headers in the page's
    language, plain spaces; a cell a spreadsheet would read as a formula starts with an
    apostrophe."""

    def cell(value: object) -> str:
        text = "" if value is None else str(value).replace("\xa0", " ").replace("\u202f", " ")
        return "'" + text if text.startswith(FORMULA) else text

    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow([t(f"v2.log.csv.{column}") for column in CSV_COLUMNS])
    rank = {id(entry): i for i, entry in enumerate(items)}
    for entry in sorted(items, key=lambda i: (i.when, rank[id(i)])):
        local = entry.when.astimezone()
        detail = entry.detail or Detail()
        fate = t(f"v2.life.{detail.fate}") if detail.fate else ""
        values = (
            local.date().isoformat(),
            local.strftime("%H:%M"),
            entry.project,
            entry.actor,
            t(f"v2.log.filter.{entry.kind}"),
            entry.text,
            entry.before,
            entry.after,
            fate,
            detail.reason,
            detail.note,
        )
        writer.writerow([cell(value) for value in values])
    return out.getvalue()


def router(ui: Ui) -> APIRouter:
    routes = APIRouter()
    services = ui.services

    def shown(request: Request) -> str:
        value = request.query_params.get("show", "all")
        return value if value in FILTERS else "all"

    def live_projects(request: Request) -> list[tuple[str, str]]:
        session = ui.session(request)
        return [(s.id, s.name) for s in services.projects(session) if s.kind == "live"]

    def gather(request: Request, one: str | None) -> tuple[list[LogItem], Chart | None]:
        """The entries of one project or of every live project; the chart of the one shown, or
        of the only project there is."""
        projects = live_projects(request)
        chosen = one if one is not None else projects[0][0] if len(projects) == 1 else None
        items: list[LogItem] = []
        chart = None
        for pid, _ in projects:
            if one is not None and pid != one:
                continue
            found, project_chart = project_log(ui, request, pid, with_name=one is None)
            items += found
            if pid == chosen:
                chart = project_chart
        return items, chart

    def known(request: Request, project_id: str) -> str:
        if project_id not in {pid for pid, _ in live_projects(request)}:
            raise AppError("project_not_found", "not_found")
        return project_id

    def log_page(request: Request, project_id: str | None, picked: str | None) -> Response:
        t = texts(request)
        show = shown(request)
        items, chart = gather(request, project_id or picked)
        values: dict[str, Any]
        if project_id is not None:
            view = services.live(ui.session(request), project_id, ui.language(request))
            values = {
                "nav": "projects",
                "tab": "log",
                "project": header(ui, request, view),
                "base": f"{PREFIX}/projects/{project_id}/log",
                "projects": [],
                "picked": None,
            }
        else:
            values = {
                "nav": "log",
                "base": f"{PREFIX}/log",
                "projects": live_projects(request),
                "picked": picked,
            }
        total = len(items)
        if show != "all":
            items = [entry for entry in items if entry.kind == show]
        return page(
            ui,
            request,
            "log.html",
            title=t("v2.log.title"),
            days=by_day(items),
            chart=chart,
            show=show,
            filters=FILTERS,
            total=total,
            today=date.today(),
            **values,
        )

    def csv_response(request: Request, items: list[LogItem]) -> Response:
        t = texts(request)
        show = shown(request)
        if show != "all":
            items = [entry for entry in items if entry.kind == show]
        name = t("v2.log.csv.file")
        headers = {"Content-Disposition": f'attachment; filename="{name}"'}
        return Response(csv_of(t, items), media_type="text/csv; charset=utf-8", headers=headers)

    def picked_of(request: Request) -> str | None:
        pick = request.query_params.get("project") or None
        return pick if pick in {pid for pid, _ in live_projects(request)} else None

    @routes.get(PREFIX + "/log")
    def global_log(request: Request) -> Response:
        return log_page(request, None, picked_of(request))

    @routes.get(PREFIX + "/log.csv")
    def global_csv(request: Request) -> Response:
        return csv_response(request, gather(request, picked_of(request))[0])

    @routes.get(PREFIX + "/projects/{project_id}/log")
    def project_page(request: Request, project_id: str) -> Response:
        return log_page(request, known(request, project_id), None)

    @routes.get(PREFIX + "/projects/{project_id}/log.csv")
    def project_csv(request: Request, project_id: str) -> Response:
        return csv_response(request, gather(request, known(request, project_id))[0])

    return routes
