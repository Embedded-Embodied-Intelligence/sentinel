"""The optional language model of the application (spec section 10; CLAUDE.md invariants 3, 4
and 7): the provider settings, the client, and the features that use it: the extraction of
tasks from a text (WP6a), the explanation of a recommendation (spec section 10.4), the proposals
of the action grammar (spec section 10.3), the events of a manager's check-in message (spec
section 10.2) and a connection test.

The settings (provider, model, Ollama host, API key) live in `settings.json` in the data
directory, outside the repository, readable by the owner only; the API reports whether a key is
set but never the key, and no log holds it (`Secret`). Every call goes through a record/replay
cache without prompts (`store_prompts = false`, mandatory for real data, spec section 10). A
server-wide daily cap counts the feature requests (an extraction with its repair rounds, or an
explanation, counts once).
"""

import json
import os
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from sentinel.agent.candidates import Candidate
from sentinel.agent.decide import DecisionRecord
from sentinel.agent.params import SentinelParams
from sentinel.app.errors import AppError
from sentinel.app.events import FactCheck, LlmExplanation
from sentinel.app.live import LiveProject, role_key
from sentinel.app.models import AbsenceReport, NewTaskReport, WorkIncreaseReport
from sentinel.app.store import Store
from sentinel.experiments.proposal_study import compile_entries
from sentinel.interpret.actions import ProposalSettings, answer_entries, ask
from sentinel.interpret.describe import state_summary
from sentinel.interpret.events import (
    STATUS_TEXT,
    AbsenceEvent,
    Context,
    NewActivityEvent,
    ParseSettings,
    TeamMessage,
    WorkIncreaseEvent,
    parse,
)
from sentinel.interpret.explain import ExplainSettings, check, explain, render_record
from sentinel.interpret.team import Member, weekday_name
from sentinel.llm import (
    BaseClient,
    GroqClient,
    LlmCache,
    LlmClient,
    LlmError,
    Message,
    OllamaClient,
    OpenRouterClient,
    QuotaExhausted,
    RequestTooLarge,
    Secret,
)
from sentinel.llm.core import WITHHELD
from sentinel.llm.http import TransportError, TransportTimeout
from sentinel.simulation.state import (
    RUNNING,
    Observation,
    nominal_activity,
    nominal_world,
    successor_lists,
)
from sentinel.wbs.extract import ExtractionSettings, Session, normalise_name, normalise_role, repair

Provider = Literal["none", "ollama", "groq", "openrouter"]
DEFAULT_MODELS: dict[str, str] = {
    "ollama": "qwen2.5:7b",
    "groq": "openai/gpt-oss-120b",
    "openrouter": "openai/gpt-oss-120b",
}
# Groq's own options of the WP6 studies (configs/wp6_rq1.toml), also through OpenRouter.
GROQ_OPTIONS: dict[str, JsonValue] = {"reasoning_effort": "low", "include_reasoning": False}
OPENROUTER_PROVIDER: dict[str, JsonValue] = {
    "order": ["groq"],
    "allow_fallbacks": False,
    "require_parameters": True,
}
EXTRACTION = ExtractionSettings(prompt_version="v1", max_tokens=4096, max_repair_rounds=3)
EXPLANATION = ExplainSettings(prompt_version="v1", max_tokens=2048)
PROPOSALS = ProposalSettings(prompt_version="v1", max_tokens=2048)
EVENTS = ParseSettings(prompt_version="v1", max_tokens=2048, max_repair_rounds=3)
USAGE_KEY = "llm"
# A person waits for these calls: a limit on one call of a local model (a first load, a slow CPU)
# and of a cloud model, with fewer retries than a study's (config `llm_timeout_s`; docs/deploy.md).
OLLAMA_TIMEOUT_S = 600.0
CLOUD_TIMEOUT_S = 90.0
CLOUD_RETRIES = 2
CLOUD_MAX_WAIT_S = 60.0
NEXT_DAYS = 5  # working days written out for a message of a check-in: every weekday once
MORE_DAYS = (1, 2, 3, 5, 10)  # more days of work whose factor is written out for a running task
# A weekday in a check-in message, by the project's language: its name, "until" it, "back on" it.
WEEKDAY_WORDS = {
    "pl": {
        "Monday": ("poniedziałek", "do poniedziałku", "wraca w poniedziałek"),
        "Tuesday": ("wtorek", "do wtorku", "wraca we wtorek"),
        "Wednesday": ("środa", "do środy", "wraca w środę"),
        "Thursday": ("czwartek", "do czwartku", "wraca w czwartek"),
        "Friday": ("piątek", "do piątku", "wraca w piątek"),
    }
}


class LlmSettings(BaseModel):
    """The provider settings as stored (`api_key` only in the file)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: Provider = "none"
    model: str | None = Field(default=None, max_length=200)
    host: str | None = Field(default=None, max_length=300)
    api_key: str | None = Field(default=None, max_length=500)


class LlmSettingsView(BaseModel):
    """What the API shows of the settings: everything but the key."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: Provider
    model: str | None
    host: str | None
    has_key: bool
    available: bool


class LlmSettingsUpdate(BaseModel):
    """A change of the settings; a missing `api_key` keeps the stored one, "" removes it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: Provider
    model: str | None = Field(default=None, max_length=200)
    host: str | None = Field(default=None, max_length=300)
    api_key: str | None = Field(default=None, max_length=500)


ClientFactory = Callable[[LlmSettings, LlmCache], LlmClient]


def make_client(
    settings: LlmSettings, cache: LlmCache, *, timeout_s: float | None = None
) -> LlmClient:
    """The client of the configured provider over `cache` (`auto`: replay a cached answer, else
    call), with the limits of a person waiting (`timeout_s` replaces the limit on one call); the
    key is passed as a `Secret`, never read from `.env` here."""
    model = settings.model or DEFAULT_MODELS[settings.provider]
    key = Secret(settings.api_key) if settings.api_key else None
    match settings.provider:
        case "ollama":
            return OllamaClient(
                model,
                num_ctx=12288,
                host=settings.host,
                timeout_s=timeout_s or OLLAMA_TIMEOUT_S,
                cache=cache,
                mode="auto",
                env_file=None,
            )
        case "groq":
            return GroqClient(
                model,
                tokens_per_minute=8000,
                extra=GROQ_OPTIONS,
                api_key=key,
                env_file=None,
                max_retries=CLOUD_RETRIES,
                cache=cache,
                mode="auto",
                timeout_s=timeout_s or CLOUD_TIMEOUT_S,
                max_wait_s=CLOUD_MAX_WAIT_S,
            )
        case "openrouter":
            return OpenRouterClient(
                model,
                tokens_per_minute=None,
                extra={"provider": OPENROUTER_PROVIDER, **GROQ_OPTIONS},
                api_key=key,
                env_file=None,
                max_retries=CLOUD_RETRIES,
                cache=cache,
                mode="auto",
                timeout_s=timeout_s or CLOUD_TIMEOUT_S,
                max_wait_s=CLOUD_MAX_WAIT_S,
            )
    raise AppError("llm_disabled", "unavailable")


def failure(error: LlmError) -> AppError:
    """A failed call as a manager reads it: what went wrong and what can be done about it."""
    code = "llm_failed"
    if isinstance(error, QuotaExhausted):
        code = "llm_quota"
    elif isinstance(error, RequestTooLarge):
        code = "llm_too_long"
    elif isinstance(error, TransportTimeout):
        code = "llm_timeout"
    elif isinstance(error, TransportError):
        code = "llm_unreachable"
    elif error.status in (401, 403):
        code = "llm_key"
    elif error.status in (400, 404):
        code = "llm_model"
    return AppError(code, "unavailable", detail=type(error).__name__)


class RequestCache(LlmCache):
    """The application's cache: an answer stored as invalid (`withhold_invalid`) is known only to
    the request that got it, so that asking again reaches the model, which a retry of a study
    must not do. Within a request its repair rounds replay it as usual."""

    def _load(self) -> None:
        super()._load()
        self._entries = {
            key: entry for key, entry in self._entries.items() if WITHHELD not in entry.reply.meta
        }


class LlmService:
    """The configured language model of a server: settings, cap and the two features."""

    def __init__(
        self,
        settings_file: Path,
        cache_dir: Path,
        store: Store,
        *,
        mode: Literal["on", "capped", "off"] = "on",
        daily_cap: int | None = None,
        factory: ClientFactory = make_client,
    ) -> None:
        self.settings_file = settings_file
        self.cache_dir = cache_dir
        self.store = store
        self.mode = mode
        self.daily_cap = daily_cap
        self.factory = factory

    def settings(self) -> LlmSettings:
        try:
            data = json.loads(self.settings_file.read_text(encoding="utf-8"))
            return LlmSettings.model_validate(data.get("llm", {}))
        except (OSError, ValueError, ValidationError, AttributeError):
            return LlmSettings()

    def view(self) -> LlmSettingsView:
        settings = self.settings()
        return LlmSettingsView(
            provider=settings.provider,
            model=settings.model or DEFAULT_MODELS.get(settings.provider),
            host=settings.host,
            has_key=bool(settings.api_key),
            available=self.available,
        )

    @property
    def available(self) -> bool:
        settings = self.settings()
        if self.mode == "off" or settings.provider == "none":
            return False
        return settings.provider == "ollama" or bool(settings.api_key)

    def update(self, change: LlmSettingsUpdate) -> LlmSettingsView:
        """Store new settings in the settings file (mode 0600)."""
        current = self.settings()
        key = current.api_key if change.api_key is None else (change.api_key or None)
        if change.provider in ("groq", "openrouter") and not key:
            raise AppError("settings_key_needed")
        settings = LlmSettings(
            provider=change.provider,
            model=change.model or None,
            host=change.host or None,
            api_key=key if change.provider in ("groq", "openrouter") else None,
        )
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads(self.settings_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except (OSError, ValueError):
            data = {}
        data["llm"] = settings.model_dump(exclude_none=True)
        temporary = self.settings_file.with_suffix(".tmp")
        handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2)
        os.replace(temporary, self.settings_file)
        os.chmod(self.settings_file, 0o600)
        return self.view()

    def client(self) -> LlmClient:
        """The client for one feature request, counted against the daily cap."""
        if not self.available:
            raise AppError("llm_disabled", "unavailable")
        cap = self.daily_cap if self.mode == "capped" else None
        if not self.store.use(USAGE_KEY, cap):
            raise AppError("llm_cap", "limit")
        settings = self.settings()
        cache = RequestCache(self.cache_dir / f"{settings.provider}.jsonl", store_prompts=False)
        return self.factory(settings, cache)

    def extract(self, text: str, seed: int, roles: Mapping[str, int] | None = None) -> Session:
        """WP6a extraction with up to three repair rounds (spec section 10); the roles of the
        project's team, if it has one, follow the description."""
        client = self.client()
        try:
            return repair(client, with_team_roles(text, roles), seed=seed, settings=EXTRACTION)
        except LlmError as exc:
            raise failure(exc) from exc

    def propose(
        self,
        observation: Observation,
        record: DecisionRecord,
        rule: Sequence[Candidate],
        names: Mapping[int, str],
        roles: Sequence[str],
        params: SentinelParams,
        seed: int,
    ) -> list[Candidate]:
        """Proposals of the action grammar (spec section 10.3) for a deliberation that passed
        the needs gate, compiled against the rule candidates: the valid, distinct ones. A
        failed call, a reached cap or an invalid answer adds none."""
        try:
            client = self.client()
            summary = state_summary(observation, record, names, params, roles)
            response = ask(client, summary, seed=seed, settings=PROPOSALS)
        except (AppError, LlmError, ValueError):
            return []
        compiled = compile_entries("llm", answer_entries(response), observation, rule, params)
        return [c.candidate for c in compiled if c.usable and c.candidate is not None]

    def explain(
        self,
        record: DecisionRecord,
        observation: Observation,
        params: SentinelParams,
        roles: Sequence[str],
        seed: int,
    ) -> LlmExplanation:
        """An LLM explanation of a recommendation with its faithfulness check (10.4)."""
        rendered = render_record(record, observation, params, roles)
        client = self.client()
        try:
            response = explain(client, rendered, seed=seed, settings=EXPLANATION)
        except LlmError as exc:
            raise failure(exc) from exc
        faith = check(response.parsed, record, rendered)
        model = getattr(client, "model", "?")
        facts = tuple(FactCheck(kind=f.kind, correct=f.correct) for f in faith.facts)
        if response.value is None:
            reason = "no answer" if response.error is None else response.error.kind
            return LlmExplanation(text="", model=model, valid=False, facts=facts, error=reason)
        return LlmExplanation(
            text=response.value.summary,
            model=model,
            valid=faith.valid,
            facts=facts,
            chosen_named=faith.chosen_named,
            component_right=faith.component_right,
            hallucinated=faith.hallucinated,
        )

    def read_message(
        self, project: LiveProject, text: str, when: date, seed: int
    ) -> "MessageDraft":
        """The events of a manager's check-in message dated `when` (spec section 10.2, the WP6b
        parser with its repair rounds), as check-in reports for the manager to confirm one by
        one; never a reason for an absence (invariant 7)."""
        context = LiveContext(project, when)
        client = self.client()
        message = TeamMessage(day=context.day, author=0, text=text)
        try:
            session = parse(client, message, context, seed=seed, settings=EVENTS)
        except LlmError as exc:
            raise failure(exc) from exc
        final = session.final
        if final.response.value is None and not final.reading.events:
            detail = "no answer" if final.response.error is None else final.response.error.kind
            raise AppError("parse_failed", "invalid", detail=detail)
        return context.draft(final.reading.events, len(final.reading.issues))

    def test(self) -> str:
        """Ask the configured model for a fixed answer, past the cache's replay (a connection
        test); the model's name, or AppError with the reason."""
        client = self.client()
        if isinstance(client, BaseClient):
            client.mode = "record"  # a test must reach the provider, not the cache
        messages = [
            Message(role="system", content='Answer with the JSON object {"ok": true} only.'),
            Message(role="user", content="Connection test."),
        ]
        try:
            response = client.complete(messages, schema=Ping, seed=0, max_tokens=512)
        except LlmError as exc:
            raise failure(exc) from exc
        if response.value is None:
            reason = "no answer" if response.error is None else response.error.kind
            raise AppError("llm_failed", "unavailable", detail=reason)
        return str(getattr(client, "model", "?"))


def with_team_roles(text: str, roles: Mapping[str, int] | None) -> str:
    """A description with the roles the project's team has, so that the answer uses their names:
    without them a model invents its own (the WP11 runs: "analityczka", "backend developer")."""
    if not roles:
        return text
    names = ", ".join(f'"{role}" ({count})' for role, count in roles.items())
    return (
        f"{text}\n\nThe team has these roles (people in brackets): {names}. Use exactly these "
        'role names in "team" and "crew".'
    )


class Ping(BaseModel):
    """The answer of a connection test."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ok: bool


class MessageDraft(BaseModel):
    """The events read from a check-in message, as check-in reports to confirm, and the number
    of issues the parser's last answer still had."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    absences: tuple[AbsenceReport, ...] = ()
    increases: tuple[WorkIncreaseReport, ...] = ()
    new_tasks: tuple[NewTaskReport, ...] = ()
    issues: int = 0


def work_left(project: LiveProject) -> dict[str, float]:
    """The remaining work of the running tasks in days of a full crew (one decimal), as the
    parser is shown it (spec section 10.2)."""
    observation = project.observation()
    world = nominal_world(observation)
    left = {}
    for key, j in project.activity_ids().items():
        if observation.status[j] == RUNNING:
            unit = max(1, sum(nominal_activity(observation, j)[1]))
            left[key] = max(0.1, round(world.remaining[j] / unit, 1))
    return left


class LiveContext(Context):
    """The parser's context (spec section 10.2) for a live project's check-in message: the
    project's own role names, task names and team, and today the check-in date. The prompt
    numbers working days from a Monday, so a day is shown shifted by the weekday of the
    project's first working day (`offset`) and shifted back when read."""

    def __init__(self, project: LiveProject, when: date) -> None:
        # The fields of `Context` are set here, with the live project's roles (the base class
        # takes the narrator's role names, which a live project does not use).
        observation = project.observation()
        model = project.require_model()
        calendar = project.calendar
        ids = project.activity_ids()
        nodes = project.nodes()
        self.project = project
        self.when = when
        self.offset = calendar.origin.weekday()
        self.observation = observation
        self.day = max(0, calendar.last(when)) + self.offset
        self.names = dict(
            sorted(
                (ids[key], node.name)
                for key, node in nodes.items()
                if project.tasks[key].state != "removed"
            )
        )
        members = [
            Member(worker=w, name=person.name, role=model.role_ids[role_key(person.role)])
            for w, person in enumerate(project.definition.team)
        ]
        self.roster = tuple(members)
        self.members = {member.worker: member for member in members}
        self.by_member_name = {member.name: member.worker for member in members}
        self.roles = model.role_names
        self.role_index = {normalise_role(role): k for k, role in enumerate(self.roles)}
        self.capacities = tuple(role.capacity for role in observation.instance.roles)
        self.sink = observation.instance.sink_id
        self.successors = successor_lists(observation)
        self.by_name = {normalise_name(name): j for j, name in self.names.items()}
        left = work_left(project)
        self.remaining = {ids[key]: days for key, days in left.items() if ids[key] in self.names}

    def render(self, message: TeamMessage) -> str:
        """As `Context.render`, the author being the project manager, not a team member, and
        with the next days, the return days and the factors of more work worked out: the rules
        of the prompt ask for this arithmetic, which a small local model gets wrong (the WP11
        runs: day 4 for the Friday of day 14, 1.3 for 3 more of 5 days), and its repair rounds
        cannot see why. A weekday reads as in the application (spec section 11.3, v2.1.5):
        "until Friday" is absent through Friday, "back on Friday" is back that day."""
        observation, t = self.observation, self.day
        words = WEEKDAY_WORDS.get(self.project.definition.settings.language, {})

        def said(before: str, d: int, form: int) -> str:
            name = weekday_name(d)
            return f"{before} {name}" + (f" ({words[name][form]})" if name in words else "")

        days = range(t + 1, t + NEXT_DAYS + 1)
        coming = ", ".join(said(f"day {d}", d, 0) for d in days)
        returns = "; ".join(
            f"{said('until', d, 1)} → {d + 1}, {said('back on', d, 2)} → {d}" for d in days
        )
        lines = [
            f"Today is day {t}, a {weekday_name(t)}. The next working days: {coming}.",
            'In these messages "until <weekday>" means absent through that day, so return_day is '
            'the next working day; "back on <weekday>" means return_day is that day. The '
            f"return_day by weekday: {returns}.",
            "",
            "Team roster (worker id and name per role; * marks people absent today):",
        ]
        for k, role in enumerate(self.roles):
            people = [
                f"{m.worker} {m.name}{'' if observation.present[m.worker] else '*'}"
                for m in self.roster
                if m.role == k
            ]
            lines.append(f"- {role}: {', '.join(people)}")
        lines += ["", "Activities (id, name, status; running ones with their remaining work):"]
        for j, name in self.names.items():
            entry = f'{j} "{name}": {STATUS_TEXT[observation.status[j]]}'
            if j in self.remaining:
                left = self.remaining[j]
                factors = ", ".join(
                    f"{d} day{'s' if d > 1 else ''} {(left + d) / left:.2f}" for d in MORE_DAYS
                )
                entry += (
                    f", {left:.1f} days of work left; if it takes N days longer, the factor is: "
                    f"{factors}"
                )
            lines.append(entry)
        author = f"the project manager on day {t} ({weekday_name(t)})"
        lines += ["", f"Message from {author}:", message.text]
        return "\n".join(lines)

    def draft(self, events: Sequence[object], issues: int) -> MessageDraft:
        """The accepted events as check-in reports (person and task keys, calendar dates)."""
        project = self.project
        calendar = project.calendar
        keys = {j: key for key, j in project.activity_ids().items()}
        people = [person.key for person in project.definition.team]
        absences, increases, new_tasks = [], [], []
        for event in events:
            match event:
                case AbsenceEvent(worker=w, return_day=r) if w < len(people):
                    back = None if r is None else calendar.date_of(r - self.offset)
                    absences.append(
                        AbsenceReport(person=people[w], first_day=self.when, return_date=back)
                    )
                case WorkIncreaseEvent(activity=j, factor=factor) if j in keys and factor > 1:
                    increases.append(WorkIncreaseReport(task=keys[j], factor=round(factor, 2)))
                case NewActivityEvent() if event.duration >= 1:
                    new_tasks.append(
                        NewTaskReport(
                            name=event.name.strip()[:120],
                            duration=event.duration,
                            crew={role: count for role, count in event.crew.items() if count > 0},
                            after=None if event.after is None else keys.get(event.after),
                            before=None if event.before is None else keys.get(event.before),
                        )
                    )
        return MessageDraft(
            absences=tuple(absences),
            increases=tuple(increases),
            new_tasks=tuple(new_tasks),
            issues=issues,
        )
