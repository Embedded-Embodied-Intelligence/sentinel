"""What the v2 pages say about a live project at a glance (docs/design/v2-spec.md, section 4):
its state, chance in 100, verdict sentence and main cause, from the services' forecast."""

from dataclasses import dataclass

from fastapi import Request

from sentinel.app.errors import AppError
from sentinel.app.ui.core import Ui
from sentinel.app.ui.v2.numbers import Verdict, hits, verdict
from sentinel.app.ui.v2.text import TextsV2
from sentinel.app.views import CauseView, ForecastSummary, ProjectView


@dataclass(frozen=True)
class Status:
    """A project's status: `state` is good/warn/bad, or none (no forecast), draft or finished."""

    state: str
    n: int | None = None
    sentence: str = ""
    cause: str | None = None
    worlds: int = 0
    on_time: int = 0
    summary: ForecastSummary | None = None


def slack(summary: ForecastSummary, view: ProjectView, ui: Ui, request: Request) -> int:
    """Working days from the most likely finish to the deadline (negative: after it)."""
    f = summary.forecast
    assert f.deadline is not None
    calendar = ui.services.state(ui.session(request), view.id).project.calendar
    return calendar.last(f.deadline) - calendar.last(f.p50)


def sentence(t: TextsV2, v: Verdict) -> str:
    if v.days == 0 and v.state != "bad":
        return t(f"v2.verdict.{v.state}_zero")
    return t.plural(f"v2.verdict.{v.state}", v.days)


def cause_text(t: TextsV2, cause: CauseView, view: ProjectView) -> str:
    """A cause of the latest change as the verdict's second line names it."""
    if cause.kind == "absence":
        person = next((p for p in view.people if p.name == cause.name), None)
        back = None
        if person is not None and person.absences:
            back = person.absences[-1].return_date
        if back is not None:
            return t("v2.cause.absence", name=cause.name, date=t.date(back))
        return t("v2.cause.absence_open", name=cause.name)
    if cause.kind == "growth":
        return t("v2.cause.growth", name=cause.name)
    if cause.kind == "new_task":
        return t("v2.cause.new_task", name=cause.name)
    return t("v2.cause.progress")


def main_cause(t: TextsV2, summary: ForecastSummary, view: ProjectView) -> str | None:
    """The first cause of the last change, else the first main risk (section 4)."""
    f = summary.forecast
    if f.causes is not None and f.causes.lines:
        return cause_text(t, f.causes.lines[0], view)
    if f.drivers:
        return t("v2.cause.risk", name=f.drivers[0].name)
    return None


def status(ui: Ui, request: Request, view: ProjectView, t: TextsV2) -> Status:
    """The status of a live project; a forecast that fails leaves it without a state."""
    if not view.has_plan:
        return Status("draft")
    if view.finished:
        return Status("finished", sentence=t("v2.verdict.finished"))
    try:
        summary = ui.services.forecast_summary(ui.session(request), view.id, ui.language(request))
    except AppError:
        return Status("none")
    if summary is None or summary.forecast.p_on_time is None or summary.forecast.deadline is None:
        return Status("none", sentence=t("v2.verdict.none"), summary=summary)
    f = summary.forecast
    p = f.p_on_time
    assert p is not None
    v = verdict(p, slack(summary, view, ui, request))
    return Status(
        v.state,
        v.n,
        sentence(t, v),
        main_cause(t, summary, view),
        f.rollouts,
        hits(p, f.rollouts),
        summary,
    )
