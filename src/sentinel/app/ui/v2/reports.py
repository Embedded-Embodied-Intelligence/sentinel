"""Raporty of the group "Praca" (docs/design/v3-spec.md, section 7; spec section 11.9; WP20):
the saved reports; "Nowy raport" (paste or dictate, the audiences as chips, "Redaguj"); per
audience a tab with the tracked changes computed by code, each accepted or rejected on its own
or all at once, beside the fact guard; saving and exporting (Markdown, a page for printing, the
clipboard), with a confirmation when a version has a changed or a new fact. A report is stored
only when the person saves it."""

from dataclasses import dataclass
from datetime import date
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response

from sentinel.app import reports
from sentinel.app.errors import AppError
from sentinel.app.messages import render
from sentinel.app.store import new_id
from sentinel.app.ui.core import Ui
from sentinel.app.ui.forms import Form, parse_date, parse_int
from sentinel.app.ui.v2.shell import PREFIX, page, texts
from sentinel.app.ui.v2.text import TextsV2
from sentinel.interpret.facts import Fact, FactCheck
from sentinel.interpret.redaction import REPORT_AUDIENCES
from sentinel.interpret.tracked import Segment

BASE = PREFIX + "/reports"
ORDER = {"changed": 0, "omitted": 1, "unchanged": 2}  # the guard's list: what needs a look first


@dataclass(frozen=True)
class Tab:
    audience: str
    label: str
    href: str
    current: bool
    warning: bool
    failed: bool


@dataclass(frozen=True)
class Piece:
    """A run of the tracked view: equal text, or a change with its state and number."""

    kind: str  # equal, change
    original: str
    version: str
    change: int | None
    accepted: bool


@dataclass(frozen=True)
class FactRow:
    kind: str
    text: str
    state: str  # unchanged, changed, omitted
    after: str | None
    count: int


@dataclass(frozen=True)
class Editor:
    """One audience's tab: the tracked changes, the fact guard and the version's text."""

    audience: str
    label: str
    pieces: list[Piece]
    changes: int
    accepted: int
    facts: list[FactRow]
    new: list[FactRow]
    counts: dict[str, int]
    model_changed: int
    model_new: int
    warning: bool
    text: str
    paragraphs: list[str]
    error: str | None
    working: bool


def label(t: TextsV2, audience: str) -> str:
    return t(f"v2.rep.aud.{audience}")


def working_on(t: TextsV2, message: str) -> str:
    """The audience the editing job is on, as a label; empty while the job waits to start."""
    return label(t, message) if message in REPORT_AUDIENCES else ""


def _pieces(segments: list[Segment], rejected: frozenset[int]) -> list[Piece]:
    return [
        Piece(s.kind, s.original, s.version, s.change, s.change not in rejected) for s in segments
    ]


def _fact(t: TextsV2, check: FactCheck) -> FactRow:
    after = None if check.replaced_by is None else check.replaced_by.text
    return FactRow(
        t(f"v2.rep.kind.{check.fact.kind}"), check.fact.text, check.state, after, check.count
    )


def _new(t: TextsV2, fact: Fact) -> FactRow:
    return FactRow(t(f"v2.rep.kind.{fact.kind}"), fact.text, "new", None, 1)


def editor(t: TextsV2, draft: reports.Draft, audience: str, working: bool = False) -> Editor:
    """The tab of `audience`: its changes with the person's decisions and its fact guard."""
    version = draft.versions.get(audience)
    error = None
    if version is not None and version.error is not None:
        reason = "" if version.error == "parse_failed" else render(version.error, t.lang)
        error = t("v2.rep.failed", reason=reason)
    view = reports.version_view(draft, audience)
    if view is None:
        return Editor(
            audience, label(t, audience), [], 0, 0, [], [], {}, 0, 0, False, "", [], error, working
        )
    guard = view.guard
    counts = {state: guard.count(state) for state in ("unchanged", "changed", "omitted")}
    return Editor(
        audience=audience,
        label=label(t, audience),
        pieces=_pieces(view.diff.segments(), view.rejected),
        changes=len(view.diff.changes),
        accepted=view.accepted,
        facts=[_fact(t, c) for c in sorted(guard.checks, key=lambda c: ORDER[c.state])],
        new=[_new(t, f) for f in guard.new],
        counts=counts,
        model_changed=view.model_guard.count("changed"),
        model_new=len(view.model_guard.new),
        warning=guard.warning,
        text=view.text,
        paragraphs=reports.paragraphs(view.text),
        error=None,
        working=False,
    )


def tabs(t: TextsV2, draft: reports.Draft, current: str, base: str) -> list[Tab]:
    found = []
    for audience in draft.audiences:
        view = reports.version_view(draft, audience)
        version = draft.versions.get(audience)
        found.append(
            Tab(
                audience,
                label(t, audience),
                f"{base}?a={audience}",
                audience == current,
                view is not None and view.guard.warning,
                version is not None and version.error is not None,
            )
        )
    return found


def current_audience(request: Request, draft: reports.Draft) -> str:
    wanted = request.query_params.get("a", "")
    return wanted if wanted in draft.audiences else draft.audiences[0]


def router(ui: Ui) -> APIRouter:
    routes = APIRouter()
    services = ui.services

    def session(request: Request) -> str:
        return ui.session(request)

    def draft_page(
        request: Request, draft: reports.Draft, job: str | None = None, now: str = ""
    ) -> Response:
        t = texts(request)
        audience = current_audience(request, draft)
        base = f"{BASE}/draft/{draft.id}"
        working = job is not None
        values: dict[str, Any] = {
            "title": draft.title or t("v2.rep.untitled"),
            "nav": "reports",
            "draft": draft,
            "base": base,
            "job": job,
            "now": now,
            "tabs": tabs(t, draft, audience, base),
            "editor": editor(t, draft, audience, working),
            "readonly": False,
            "saved": None,
        }
        return page(ui, request, "report_draft.html", **values)

    @routes.get(BASE)
    def report_list(request: Request) -> Response:
        t = texts(request)
        rows = services.saved_reports(session(request))
        return page(
            ui,
            request,
            "reports.html",
            title=t("v2.rep.title"),
            nav="reports",
            rows=rows,
            labels={a: label(t, a) for a in REPORT_AUDIENCES},
            notice=t("v2.rep.deleted") if request.query_params.get("deleted") else None,
        )

    @routes.get(BASE + "/new")
    def new_report(request: Request) -> Response:
        t = texts(request)
        return page(
            ui,
            request,
            "report_new.html",
            title=t("v2.rep.new"),
            nav="reports",
            audiences=REPORT_AUDIENCES,
            available=services.llm.available,
            today=date.today(),
            error=None,
            values={},
        )

    @routes.post(BASE + "/new")
    async def start(request: Request) -> Response:
        t = texts(request)
        form = await Form.read(request)
        day = parse_date(form.get("date")) or date.today()
        try:
            draft, job = services.new_draft(
                session(request),
                form.get("title"),
                form.get("text"),
                form.getlist("audience"),
                day,
                ui.language(request),
            )
        except AppError as error:
            message = t(f"v2.rep.error.{error.code}") if error.code.startswith("report_") else None
            return page(
                ui,
                request,
                "report_new.html",
                title=t("v2.rep.new"),
                nav="reports",
                audiences=REPORT_AUDIENCES,
                available=services.llm.available,
                today=day,
                error=message or render(error.code, ui.language(request), error.params),
                values={
                    "title": form.get("title"),
                    "text": form.get("text"),
                    "audience": form.getlist("audience"),
                },
            )
        return ui.redirect(request, f"{BASE}/draft/{draft.id}", job=job.id)

    @routes.get(BASE + "/draft/{draft_id}")
    def draft_view(request: Request, draft_id: str) -> Response:
        draft = services.draft(session(request), draft_id)
        job_id = request.query_params.get("job")
        now = ""
        if job_id:
            job = services.job(session(request), job_id, ui.language(request))
            if job.status in ("queued", "running"):
                now = working_on(texts(request), job.message)
            else:
                job_id = None
        return draft_page(request, draft, job_id or None, now)

    @routes.get(BASE + "/draft/{draft_id}/wait")
    def wait(request: Request, draft_id: str) -> Response:
        """The editing job's progress, polled; when it is done, the editor."""
        draft = services.draft(session(request), draft_id)
        job = services.job(
            session(request), request.query_params.get("job", ""), ui.language(request)
        )
        if job.status in ("queued", "running"):
            return page(
                ui,
                request,
                "_report_wait.html",
                base=f"{BASE}/draft/{draft.id}",
                job=job.id,
                now=working_on(texts(request), job.message),
            )
        return ui.redirect(request, f"{BASE}/draft/{draft.id}")

    @routes.post(BASE + "/draft/{draft_id}/decide")
    async def decide(request: Request, draft_id: str) -> Response:
        """Accept or reject one change, or all of them; the tab again."""
        t = texts(request)
        draft = services.draft(session(request), draft_id)
        form = await Form.read(request)
        audience = form.get("a")
        if audience not in draft.audiences:
            raise AppError("report_no_audience")
        change = parse_int(form.get("change"))
        reports.decide(draft, audience, change, form.get("accept") == "1")
        base = f"{BASE}/draft/{draft.id}"
        return page(
            ui,
            request,
            "_report_editor.html",
            draft=draft,
            base=base,
            editor=editor(t, draft, audience),
            tabs=tabs(t, draft, audience, base),
            readonly=False,
            saved=None,
        )

    @routes.post(BASE + "/draft/{draft_id}/save")
    async def save(request: Request, draft_id: str) -> Response:
        t = texts(request)
        draft = services.draft(session(request), draft_id)
        form = await Form.read(request)
        risky = reports.warnings(draft)
        if risky and form.get("confirm") != "1":
            return page(
                ui,
                request,
                "_report_confirm.html",
                base=f"{BASE}/draft/{draft.id}",
                audiences=", ".join(label(t, a) for a in risky),
                action="save",
            )
        report_id = services.save_draft(session(request), draft.id)
        return ui.redirect(request, f"{BASE}/{report_id}")

    def export(request: Request, draft: reports.Draft, base: str) -> Response:
        t = texts(request)
        audience = current_audience(request, draft)
        view = reports.version_view(draft, audience)
        if view is None:
            raise AppError("draft_not_found", "not_found")
        fmt = request.query_params.get("fmt", "md")
        if view.guard.warning and request.query_params.get("confirm") != "1":
            return page(
                ui,
                request,
                "report_confirm.html",
                title=t("v2.rep.confirm.title"),
                nav="reports",
                base=base,
                audience=audience,
                fmt=fmt,
                audiences=label(t, audience),
            )
        title = draft.title or t("v2.rep.untitled")
        if fmt == "html":
            return page(
                ui,
                request,
                "report_print.html",
                title=title,
                day=t.date(draft.day),
                audience=label(t, audience),
                paragraphs=reports.paragraphs(view.text),
            )
        text = reports.markdown(title, t.date(draft.day), label(t, audience), view.text)
        name = f"raport-{draft.day.isoformat()}-{audience}.md"
        return Response(
            text,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    @routes.get(BASE + "/draft/{draft_id}/export")
    def export_draft(request: Request, draft_id: str) -> Response:
        draft = services.draft(session(request), draft_id)
        return export(request, draft, f"{BASE}/draft/{draft.id}")

    def saved_draft(request: Request, report_id: str) -> tuple[reports.Draft, Any]:
        row = services.saved_report(session(request), report_id)
        draft = reports.from_payload(
            new_id(),
            session(request),
            row.id,
            row.title,
            row.payload,
            services.report_names(session(request)),
        )
        return draft, row

    @routes.get(BASE + "/{report_id}")
    def saved(request: Request, report_id: str) -> Response:
        t = texts(request)
        draft, row = saved_draft(request, report_id)
        audience = current_audience(request, draft)
        base = f"{BASE}/{report_id}"
        values: dict[str, Any] = {
            "title": draft.title or t("v2.rep.untitled"),
            "nav": "reports",
            "draft": draft,
            "base": base,
            "job": None,
            "tabs": tabs(t, draft, audience, base),
            "editor": editor(t, draft, audience),
            "readonly": True,
            "saved": row,
        }
        return page(ui, request, "report_draft.html", **values)

    @routes.get(BASE + "/{report_id}/export")
    def export_saved(request: Request, report_id: str) -> Response:
        draft, _ = saved_draft(request, report_id)
        return export(request, draft, f"{BASE}/{report_id}")

    @routes.post(BASE + "/{report_id}/edit")
    def edit_again(request: Request, report_id: str) -> Response:
        draft = services.reopen(session(request), report_id)
        return ui.redirect(request, f"{BASE}/draft/{draft.id}")

    @routes.post(BASE + "/{report_id}/delete")
    def delete(request: Request, report_id: str) -> Response:
        services.delete_report(session(request), report_id)
        return ui.redirect(request, BASE, deleted="1")

    return routes
