"""Uprawnienia AI and Ludzie of the group "Zasady AI" (docs/design/v3-spec.md, sections 4 and 5;
WP19). Uprawnienia AI: what the model may and may not do, each with its "Dowód" point; "Teraz",
the active model, what leaves the company and the latest calls as metadata only; and "Próba
ataku", a message with a hidden instruction through the real message flow, by default with a
recorded answer, live on request (counted in the demo's cap); nothing is saved. Ludzie: the four
features deliberately absent, and the team's workload in days for the next two weeks."""

from dataclasses import dataclass
from datetime import date
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response

from sentinel.app import attack
from sentinel.app.errors import AppError
from sentinel.app.models import Language
from sentinel.app.ui.core import Ui
from sentinel.app.ui.forms import Form
from sentinel.app.ui.project import checkin_item
from sentinel.app.ui.v2.plan import PersonRow, team_rows
from sentinel.app.ui.v2.settings import choice_of
from sentinel.app.ui.v2.shell import PREFIX, page, texts
from sentinel.app.ui.v2.text import TextsV2

# (line, decision): what the model may and may not do (section 4)
MAY = (("read", "D23"), ("format", "D19"))
MAY_NOT = (
    ("save", "D03"),
    ("send", "D04"),
    ("approve", "D03"),
    ("compute", "D13"),
    ("choose", "D24"),
    ("connect", "D19"),
    ("projects", "D12"),
)
# (card, icon, decision): the features deliberately absent (section 5)
ABSENT = (
    ("performance", "gauge", "D09"),
    ("ranking", "podium", "D18"),
    ("mood", "smile", "D18"),
    ("reasons", "document", "D10"),
)
PROVIDERS = {"openrouter": "OpenRouter", "groq": "Groq", "ollama": "Ollama"}
LOAD_WEEKS = 2


@dataclass(frozen=True)
class Now:
    """The active model in words and what leaves the company."""

    choice: str  # cloud, local, none
    provider: str
    model: str
    voice: bool


@dataclass(frozen=True)
class CallRow:
    time: str
    role: str
    provider: str
    chars: int
    seconds: str


def now_of(ui: Ui) -> Now:
    view = ui.services.llm.view()
    choice = choice_of(view.provider) if view.available else "none"
    return Now(
        choice=choice,
        provider=PROVIDERS.get(view.provider, view.provider),
        model=view.model or "",
        voice=view.voice,
    )


def call_rows(ui: Ui, request: Request, t: TextsV2) -> list[CallRow]:
    """The latest calls of the model, metadata only; in the demo, the visitor's own."""
    session = ui.session(request) if ui.config.demo else None
    rows = []
    for call in ui.services.llm.calls(session):
        seconds = t("v2.perm.cached") if call.cached else f"{t.decimal(round(call.seconds, 1))} s"
        rows.append(
            CallRow(
                time=f"{call.at.astimezone():%H:%M:%S}",
                role=t(f"v2.perm.role.{call.role}"),
                provider=PROVIDERS.get(call.provider, call.provider),
                chars=call.chars,
                seconds=seconds,
            )
        )
    return rows


@dataclass(frozen=True)
class AttackView:
    """The outcome of "Próba ataku" in words."""

    outcome: attack.Outcome
    lines: list[str]
    when: str
    source: str


def attack_view(t: TextsV2, language: Language, outcome: attack.Outcome) -> AttackView:
    project = attack.project(language)
    names = {task.key: task.name for task in project.definition.tasks}
    people = {person.key: person.name for person in project.definition.team}
    checkin = attack.as_checkin(outcome.review)
    lines = [] if checkin is None else checkin_item(checkin, project, names, people, t).lines
    if outcome.recorded:
        provider, model, day = attack.recording_info()
        source = t(
            "v2.perm.attack.recorded",
            model=model,
            provider=PROVIDERS.get(provider, provider),
            date=t.date(day),
        )
    else:
        source = t("v2.perm.attack.live", model=outcome.model)
    return AttackView(outcome, lines, t.date(attack.WHEN), source)


@dataclass(frozen=True)
class TeamLoad:
    """A live project's team for Ludzie: each person's absences and workload in days."""

    id: str
    name: str
    people: list[PersonRow]
    days: list[date]


def team_loads(ui: Ui, request: Request, t: TextsV2) -> list[TeamLoad]:
    services = ui.services
    session, language = ui.session(request), ui.language(request)
    found = []
    for summary in services.projects(session):
        if summary.kind != "live":
            continue
        state = services.state(session, summary.id)
        if state.project.baseline is None:
            continue
        view = services.live(session, summary.id, language)
        people, days = team_rows(t, view, state.project, date.today(), LOAD_WEEKS)
        found.append(TeamLoad(summary.id, view.name, people, days))
    return found


def router(ui: Ui) -> APIRouter:
    routes = APIRouter()
    services = ui.services

    @routes.get(PREFIX + "/permissions")
    def permissions(request: Request) -> Response:
        t = texts(request)
        language = ui.language(request)
        values: dict[str, Any] = {
            "title": t("v2.perm.title"),
            "nav": "permissions",
            "may": MAY,
            "may_not": MAY_NOT,
            "now": now_of(ui),
            "calls": call_rows(ui, request, t),
            "sample": attack.sample(language),
            "live": services.llm.available,
        }
        return page(ui, request, "permissions.html", **values)

    @routes.post(PREFIX + "/permissions/attack")
    async def run_attack(request: Request) -> Response:
        """ "Uruchom": the recorded answer by default, the configured model on request (counted
        in the cap, no cache); the result is shown and forgotten."""
        t = texts(request)
        language = ui.language(request)
        form = await Form.read(request)
        live = form.get("mode", "replay") == "live"
        try:
            if live:
                client = services.llm.client(ui.session(request), role="attack", cached=False)
                outcome = attack.run(client, language, recorded=False)
            else:
                outcome = attack.replay(language)
        except AppError as error:
            reason = "limit" if error.kind == "limit" else "unavailable"
            message = t(f"v2.perm.error.{reason}")
            return page(ui, request, "_attack.html", result=None, error=message)
        except Exception:  # a failed live call: shown, never stored
            return page(ui, request, "_attack.html", result=None, error=t("v2.perm.error.failed"))
        result = attack_view(t, language, outcome)
        return page(ui, request, "_attack.html", result=result, error=None)

    @routes.get(PREFIX + "/people")
    def people(request: Request) -> Response:
        t = texts(request)
        return page(
            ui,
            request,
            "people.html",
            title=t("v2.people.title"),
            nav="people",
            absent=ABSENT,
            teams=team_loads(ui, request, t),
        )

    return routes
