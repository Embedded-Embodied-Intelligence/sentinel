"""The v2 decisions (docs/design/v2-spec.md, sections 3 and 8.4): approve, reject with a reason,
postpone, and the validity of a pending decision."""

from dataclasses import dataclass
from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import Response

from sentinel.app.errors import AppError
from sentinel.app.events import RejectReason
from sentinel.app.ui.core import Ui
from sentinel.app.ui.forms import Form
from sentinel.app.ui.v2.shell import GATE, PREFIX
from sentinel.app.views import ProjectView, RecommendationView

REASONS: tuple[RejectReason, ...] = ("too_expensive", "unavailable", "no_budget", "other")


@dataclass(frozen=True)
class Validity:
    """How long a pending decision stays worth taking (section 3): its validity date, the days
    left, whether it expires tomorrow, and the chance in 100 lost per day of waiting."""

    valid: date | None = None
    left: int | None = None
    expires_tomorrow: bool = False
    delay: int | None = None
    computing: bool = False


def validity_of(
    ui: Ui, request: Request, view: ProjectView, rec: RecommendationView
) -> Validity | None:
    """The validity of a pending decision, None until it is known."""
    return None


def router(ui: Ui) -> APIRouter:
    routes = APIRouter()
    services = ui.services

    def back_to(project_id: str, back: str | None) -> str:
        return f"{PREFIX}/projects/{project_id}" + ("/decisions" if back == "decisions" else "")

    @routes.post(PREFIX + "/projects/{project_id}/decisions/{seq}/approve")
    async def approve(request: Request, project_id: str, seq: int) -> Response:
        form = await Form.read(request)
        session, language = ui.session(request), ui.language(request)
        after = services.decide(session, project_id, seq, "approve", language, autonomy=GATE)
        entry = next((r for r in after.recommendations if r.seq == seq), None)
        if entry is not None and entry.status == "discarded":
            return ui.redirect(request, back_to(project_id, form.get("back")), done="discarded")
        return ui.redirect(request, back_to(project_id, form.get("back")), done="approved")

    @routes.post(PREFIX + "/projects/{project_id}/decisions/{seq}/reject")
    async def reject(request: Request, project_id: str, seq: int) -> Response:
        form = await Form.read(request)
        reason = next((r for r in REASONS if r == form.get("reason")), None)
        if reason is None:
            raise AppError("field_invalid", field="reason", detail=form.get("reason"))
        note = form.get("note") if reason == "other" else None
        session, language = ui.session(request), ui.language(request)
        services.decide(
            session, project_id, seq, "reject", language, reason=reason, note=note, autonomy=GATE
        )
        return ui.redirect(request, back_to(project_id, form.get("back")), done="rejected")

    @routes.post(PREFIX + "/projects/{project_id}/decisions/{seq}/postpone")
    def postpone(request: Request, project_id: str, seq: int) -> Response:
        session, language = ui.session(request), ui.language(request)
        view = services.decide(session, project_id, seq, "later", language, autonomy=GATE)
        rec = next((r for r in view.recommendations if r.seq == seq), None)
        found = None if rec is None else validity_of(ui, request, view, rec)
        query = {"done": "postponed"}
        if found is not None and found.valid is not None:
            query["valid"] = found.valid.isoformat()
        return ui.redirect(request, f"{PREFIX}/projects/{project_id}", **query)

    return routes
