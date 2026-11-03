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
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from sentinel.agent.candidates import Candidate
from sentinel.agent.decide import DecisionRecord
from sentinel.agent.params import SentinelParams
from sentinel.app.errors import AppError
from sentinel.app.events import FactCheck, LlmExplanation
from sentinel.app.live import LiveProject, role_key
from sentinel.app.models import AbsenceReport, NewTaskReport, WorkIncreaseReport
from sentinel.app.store import Store
from sentinel.app.terms import internal_terms
from sentinel.experiments.proposal_study import compile_entries
from sentinel.interpret.actions import ProposalSettings, answer_entries, ask
from sentinel.interpret.describe import state_summary
from sentinel.interpret.events import (
    EVENTS_PROMPT,
    EVENTS_REPAIR_PROMPT,
    STATUS_TEXT,
    AbsenceEvent,
    Context,
    EventIssue,
    MessageEvents,
    NewActivityEvent,
    ParseSettings,
    Reading,
    TeamMessage,
    WorkIncreaseEvent,
    parse_messages,
    read_answer,
    repair_messages,
    withheld_issue,
)
from sentinel.interpret.explain import (
    EXPLAIN_PROMPT,
    ExplainSettings,
    Explanation,
    check,
    render_record,
)
from sentinel.interpret.team import WEEKDAYS, Member
from sentinel.llm import (
    BaseClient,
    GroqClient,
    LlmCache,
    LlmClient,
    LlmError,
    LlmResponse,
    Message,
    OllamaClient,
    OpenRouterClient,
    Prompt,
    QuotaExhausted,
    RequestTooLarge,
    Secret,
    load_prompt,
)
from sentinel.llm.core import WITHHELD, DomainIssue
from sentinel.llm.http import TransportError, TransportTimeout
from sentinel.simulation.state import (
    RUNNING,
    Observation,
    nominal_activity,
    nominal_world,
    successor_lists,
)
from sentinel.wbs.extract import (
    EXTRACT_PROMPT,
    REPAIR_PROMPT,
    ExtractedActivity,
    Extraction,
    ExtractionSettings,
    Round,
    Session,
    answer_issues,
    extraction_messages,
    normalise_name,
    normalise_role,
    validate_extraction,
)
from sentinel.wbs.extract import Issue as WbsIssue
from sentinel.wbs.extract import domain_issues as wbs_domain_issues
from sentinel.wbs.extract import repair_messages as wbs_repair_messages

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
EVENTS_LIVE_PROMPT = "events_live"  # the application's addendum to the parser's prompt (WP12)
EXPLAIN_LIVE_PROMPT = "explain_live"  # the explanation in the page's language (WP12, ADR-0029)
LANGUAGE_NAMES = {"en": "English", "pl": "Polish"}
WBS_LIVE_PROMPT = "wbs_live"  # the application's addendum to the extraction prompt (WP12)
# A person waits for these calls: a limit on one call of a local model (a first load, a slow CPU)
# and of a cloud model, with fewer retries than a study's (config `llm_timeout_s`; docs/deploy.md).
OLLAMA_TIMEOUT_S = 600.0
CLOUD_TIMEOUT_S = 90.0
CLOUD_RETRIES = 2
CLOUD_MAX_WAIT_S = 60.0
NEXT_DAYS = 5  # working days written out for a message of a check-in: every weekday once
DATED_DAYS = 20  # working days written out with their calendar dates (WP12: "do 26 listopada")
MONTH_WORDS = {
    "pl": (
        "stycznia",
        "lutego",
        "marca",
        "kwietnia",
        "maja",
        "czerwca",
        "lipca",
        "sierpnia",
        "września",
        "października",
        "listopada",
        "grudnia",
    )
}
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
            return extract_live(
                client, with_team_roles(text, roles), seed=seed, settings=EXTRACTION
            )
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
        *,
        language: str = "en",
        names: Mapping[str, str] | None = None,
        reason: str = "",
    ) -> LlmExplanation:
        """An LLM explanation of a recommendation with its faithfulness check (10.4), in the
        page's `language` with the actions named as the page names them (`names` by label) and
        no internal term (WP12, B7): a text with one is asked for once more, and if the second
        has one too, the page keeps the template explanation alone. The prompts stay English
        (ADR-0029)."""
        rendered = render_record(record, observation, params, roles)
        client = self.client()
        base = load_prompt(EXPLAIN_PROMPT, EXPLANATION.prompt_version)
        addendum = load_prompt(EXPLAIN_LIVE_PROMPT, EXPLANATION.prompt_version)
        system = f"{base.text}\n\n{addendum.render(language=LANGUAGE_NAMES[language])}"
        user = rendered.text
        if names:
            listed = "\n".join(f"- {label}: {name}" for label, name in names.items())
            user += (
                f"\n\nThe actions as the page names them in {LANGUAGE_NAMES[language]}:\n{listed}"
            )
        if reason:
            user += f"\n\nWhy the choice stands, as the page says it: {reason}"
        messages = [Message(role="system", content=system), Message(role="user", content=user)]
        try:
            response = self._explain(client, messages, seed)
            terms = _terms_of(response)
            if terms:
                again = f"The summary uses {', '.join(dict.fromkeys(terms))}, which the page "
                again += "does not show. Write the complete answer again without them."
                retry = [
                    *messages,
                    Message(role="assistant", content=response.text),
                    Message(role="user", content=again),
                ]
                response = self._explain(client, retry, seed + 1)
                terms = _terms_of(response)
        except LlmError as exc:
            raise failure(exc) from exc
        model = getattr(client, "model", "?")
        if terms:
            return LlmExplanation(text="", model=model, valid=False, error="internal_terms")
        parsed = response.parsed
        if isinstance(parsed, dict) and isinstance(parsed.get("summary"), str):
            # A decimal comma is a decimal point to the check of the numbers (10.4).
            parsed = {**parsed, "summary": re.sub(r"(\d),(\d)", r"\1.\2", parsed["summary"])}
        faith = check(parsed, record, rendered)
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

    def _explain(
        self, client: LlmClient, messages: list[Message], seed: int
    ) -> LlmResponse[Explanation]:
        return client.complete(
            messages,
            schema=Explanation,
            temperature=EXPLANATION.temperature,
            seed=seed,
            max_tokens=EXPLANATION.max_tokens,
        )

    def read_message(
        self, project: LiveProject, text: str, when: date, seed: int
    ) -> "MessageDraft":
        """The events of a manager's check-in message dated `when` (spec section 10.2, the WP6b
        parser with its repair rounds), as check-in reports for the manager to confirm one by
        one; never a reason for an absence (invariant 7)."""
        context = LiveContext(
            project, when, split_clauses(text, project.definition.settings.language)
        )
        client = self.client()
        message = TeamMessage(day=context.day, author=0, text=text)
        try:
            final = parse_live(client, message, context, seed=seed, settings=EVENTS)
        except LlmError as exc:
            raise failure(exc) from exc
        if final.response.value is None and not final.reading.events:
            detail = "no answer" if final.response.error is None else final.response.error.kind
            raise AppError("parse_failed", "invalid", detail=detail)
        draft = context.draft(
            final.reading.events, len(final.reading.issues), final.unparsed, final.questions
        )
        names = {person.key: person.name for person in project.definition.team}
        doubtful = tuple(
            i for i, a in enumerate(draft.absences) if not named_in(names.get(a.person, ""), text)
        )
        return draft.model_copy(update={"doubtful": doubtful})

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


class LiveActivity(ExtractedActivity):
    """An activity as the application reads it (WP12): a short name, the sentence it comes
    from and whether the project can do without it."""

    optional: bool = False
    description: str = ""


class LiveExtraction(Extraction):
    """The application's extraction schema: that of RQ1 with the two fields of `LiveActivity`;
    the research schema and prompt are unchanged."""

    activities: tuple[LiveActivity, ...]


MAX_NAME_WORDS = 6
RESEARCH_FIELDS = ("name", "duration_days", "crew", "predecessors")


def research_view(data: object) -> object:
    """An answer of the application's schema as the RQ1 schema sees it: without its fields."""
    if not isinstance(data, dict) or not isinstance(data.get("activities"), list):
        return data
    activities = [
        {k: a[k] for k in RESEARCH_FIELDS if k in a} if isinstance(a, dict) else a
        for a in data["activities"]
    ]
    return {**data, "activities": activities}


def live_extraction_issues(data: object) -> list[WbsIssue]:
    """The issues of an answer: those of RQ1 (`validate_extraction`) and the application's."""
    return validate_extraction(research_view(data)) + application_issues(data)


def application_issues(data: object) -> list[WbsIssue]:
    """A name of more than six words, and an optional activity that another one comes after
    (as "invalid_field" issues, whose messages say what to change)."""
    found: list[WbsIssue] = []
    if not isinstance(data, dict) or not isinstance(data.get("activities"), list):
        return found
    entries = [a for a in data["activities"] if isinstance(a, dict)]
    after = {
        normalise_name(p)
        for a in entries
        for p in a.get("predecessors") or ()
        if isinstance(p, str)
    }
    for a in entries:
        name = a.get("name")
        if not isinstance(name, str):
            continue
        if len(name.split()) > MAX_NAME_WORDS:
            found.append(
                WbsIssue(
                    "invalid_field",
                    f'"{name}" is not a short name; give at most six words and keep the sentence '
                    'in "description".',
                    activity=name,
                )
            )
        if a.get("optional") is True and normalise_name(name) in after:
            found.append(
                WbsIssue(
                    "invalid_field",
                    f'"{name}" is optional, but another activity comes after it.',
                    activity=name,
                )
            )
    return found


def live_extraction_domain(data: object) -> list[DomainIssue]:
    """The issues a cache without prompts keeps (spec section 10): those of RQ1 and the two of
    the application, as kinds and places."""
    found = wbs_domain_issues(research_view(data))
    return found + [DomainIssue(issue.kind, ("activities",)) for issue in application_issues(data)]


def extract_live(
    client: LlmClient, text: str, *, seed: int, settings: ExtractionSettings
) -> Session:
    """The extraction of RQ1 (`wbs.extract.repair`) with the application's two fields: its
    prompt with the addendum `wbs_live`, its schema and its issues in the repair rounds."""
    base = load_prompt(EXTRACT_PROMPT, settings.prompt_version)
    addendum = load_prompt(WBS_LIVE_PROMPT, settings.prompt_version)
    prompt = Prompt(WBS_LIVE_PROMPT, settings.prompt_version, f"{base.text}\n\n{addendum.text}")
    repair_prompt = load_prompt(REPAIR_PROMPT, settings.prompt_version)

    def call(messages: list[Message]) -> LlmResponse[LiveExtraction]:
        return client.complete(
            messages,
            schema=LiveExtraction,
            temperature=settings.temperature,
            seed=seed,
            max_tokens=settings.max_tokens,
            validator=live_extraction_domain,
        )

    def issues_of(response: LlmResponse[LiveExtraction]) -> tuple[WbsIssue, ...]:
        if response.error is not None:
            return tuple(answer_issues(cast(LlmResponse[Extraction], response)))
        return tuple(live_extraction_issues(response.parsed))

    first = call(extraction_messages(text, prompt))
    rounds = [Round(0, cast(LlmResponse[Extraction], first), issues_of(first))]
    while rounds[-1].issues and len(rounds) <= settings.max_repair_rounds:
        last = rounds[-1]
        try:
            response = call(
                wbs_repair_messages(text, last.response, last.issues, prompt, repair_prompt)
            )
        except RequestTooLarge as exc:
            return Session(tuple(rounds), stopped=f"request too large: {exc}")
        rounds.append(
            Round(len(rounds), cast(LlmResponse[Extraction], response), issues_of(response))
        )
    return Session(tuple(rounds))


def _terms_of(response: LlmResponse[Explanation]) -> list[str]:
    """The internal terms in the summary of an answer (none without one)."""
    value = response.value
    return [] if value is None else internal_terms(value.summary)


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


class Question(BaseModel):
    """What the parser could not decide alone about a clause of a message (WP12): somebody not
    in the team is absent, or a task that grew fits several activities."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["unknown_person", "ambiguous_task"]
    clause: int = Field(ge=1)
    return_day: int | None = None
    candidates: tuple[int, ...] = ()
    extra_days: float | None = Field(default=None, allow_inf_nan=False)
    factor: float | None = Field(default=None, allow_inf_nan=False)


class LiveMessageEvents(BaseModel):
    """The output schema of the application's parser (WP12): the events of spec section 10.2,
    the numbers of the clauses turned into no event, and the questions; no text of the
    message, so that a cache without prompts holds none (invariant 7)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    events: tuple[AbsenceEvent | WorkIncreaseEvent | NewActivityEvent, ...]
    unparsed: tuple[int, ...] = ()
    questions: tuple[Question, ...] = ()


class QuestionDraft(BaseModel):
    """A question for the manager about a clause of the message: who is the absent person (the
    absence's dates are known), or which task grew (the candidates' keys and the growth)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["unknown_person", "ambiguous_task"]
    clause: int
    first_day: date | None = None
    return_date: date | None = None
    candidates: tuple[str, ...] = ()
    extra_days: float | None = None
    factor: float | None = None


class MessageDraft(BaseModel):
    """The events read from a check-in message, as check-in reports to confirm, the number of
    issues the parser's last answer still had, the numbers of the clauses it turned into
    nothing and its questions (WP12: nothing is dropped silently). It holds no text of the
    message; the page shows the clauses from `clauses`, kept in memory only."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    absences: tuple[AbsenceReport, ...] = ()
    increases: tuple[WorkIncreaseReport, ...] = ()
    new_tasks: tuple[NewTaskReport, ...] = ()
    issues: int = 0
    unparsed: tuple[int, ...] = ()
    questions: tuple[QuestionDraft, ...] = ()
    doubtful: tuple[int, ...] = ()  # absences whose person the message does not name (WP12)


MAX_CLAUSES = 20
CONJUNCTIONS = {
    "pl": r",?\s+(?:a|ale|oraz|natomiast)\s+",
    "en": r",\s+(?:and|but|while)\s+",
}


NAME_STEM = 3  # letters of a name a word must start with: "Ani" names Ania, "Tomka" Tomasz


def named_in(name: str, text: str) -> bool:
    """Whether a message names a person: a word of it starts as a part of the name does (its
    first three letters, so that Polish case forms match: "Ani", "Tomka"); WP12: a small model gave
    Marek's absence to Tomasz, and the review now shows such an absence as one to check."""
    words = [w.casefold() for w in re.findall(r"\w+", text)]
    stems = [part.casefold()[:NAME_STEM] for part in name.split() if len(part) >= 2]
    return any(word.startswith(stem) for stem in stems for word in words)


def split_clauses(text: str, language: str = "en") -> tuple[str, ...]:
    """The clauses of a message, numbered from 1 in the prompt (WP12): its sentences, split
    further at a semicolon and at a conjunction that joins two statements ("..., a testy
    potrwają"), at most `MAX_CLAUSES`."""
    parts = re.split(r"(?<=[.!?;])\s+|\n+", text.strip())
    joiner = re.compile(CONJUNCTIONS.get(language, CONJUNCTIONS["en"]), re.IGNORECASE)
    clauses = [c.strip(" ,;") for part in parts for c in joiner.split(part)]
    return tuple(c for c in clauses if c)[:MAX_CLAUSES]


@dataclass(frozen=True)
class LiveRound:
    """A round of the application's parser: the answer, the reading of its events, and its
    valid clause numbers and questions."""

    response: LlmResponse[LiveMessageEvents]
    reading: Reading
    unparsed: tuple[int, ...]
    questions: tuple[Question, ...]


def parse_live(
    client: LlmClient,
    message: TeamMessage,
    context: "LiveContext",
    *,
    seed: int,
    settings: ParseSettings,
) -> LiveRound:
    """The parser of spec section 10.2 (`interpret.events.parse`) with the application's two
    more fields: its prompt with the addendum `events_live`, its schema, and the issues of the
    clause numbers and questions in its repair rounds; the research parser is unchanged."""
    base = load_prompt(EVENTS_PROMPT, settings.prompt_version)
    addendum = load_prompt(EVENTS_LIVE_PROMPT, settings.prompt_version)
    prompt = Prompt(EVENTS_LIVE_PROMPT, settings.prompt_version, f"{base.text}\n\n{addendum.text}")
    repair_prompt = load_prompt(EVENTS_REPAIR_PROMPT, settings.prompt_version)

    def call(messages: list[Message]) -> LlmResponse[LiveMessageEvents]:
        return client.complete(
            messages,
            schema=LiveMessageEvents,
            temperature=settings.temperature,
            seed=seed,
            max_tokens=settings.max_tokens,
            validator=lambda data: live_domain_issues(data, context),
        )

    response = call(parse_messages(context, message, prompt))
    current = live_round(response, context)
    rounds = 0
    while current.reading.issues and rounds < settings.max_repair_rounds:
        rounds += 1
        previous = cast(LlmResponse[MessageEvents], current.response)  # reads .parsed, .text
        conversation = repair_messages(
            context, message, previous, current.reading.issues, prompt, repair_prompt
        )
        try:
            response = call(conversation)
        except RequestTooLarge:
            break
        current = live_round(response, context)
    return current


def live_round(response: LlmResponse[LiveMessageEvents], context: "LiveContext") -> LiveRound:
    """The events (`read_answer`), the clause numbers and the questions of an answer, with
    every issue of either for the repair round; an answer withheld or not JSON as one issue."""
    error = response.error
    if error is not None and error.kind == "domain":
        withheld = tuple(withheld_issue(detail) for detail in error.details)
        return LiveRound(response, Reading((), withheld), (), ())
    if error is not None and error.kind in ("empty", "json", "truncated"):
        text = "The answer is not valid JSON or was cut off. Return the JSON object only."
        return LiveRound(response, Reading((), (EventIssue("invalid_json", text),)), (), ())
    data = response.parsed
    if not isinstance(data, dict):
        return LiveRound(response, read_answer(data, context), (), ())
    reading = read_answer({"events": data.get("events")}, context)
    unparsed, questions, issues = context.extras(data)
    found = Reading(reading.events, (*reading.issues, *issues))
    return LiveRound(response, found, unparsed, questions)


def _items(value: object) -> list[object]:
    return list(value) if isinstance(value, list | tuple) else []


def live_domain_issues(data: object, context: "LiveContext") -> list[DomainIssue]:
    """The issues a cache without prompts keeps of an answer (spec section 10): those of its
    events and of its clause numbers and questions, as kinds and places only."""
    if not isinstance(data, dict):
        return [DomainIssue("invalid_field")]
    issues = [
        DomainIssue(issue.kind, () if issue.event is None else ("events", issue.event))
        for issue in read_answer({"events": data.get("events")}, context).issues
    ]
    return issues + [DomainIssue(issue.kind, ("questions",)) for issue in context.extras(data)[2]]


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

    def __init__(self, project: LiveProject, when: date, clauses: Sequence[str] = ()) -> None:
        # The fields of `Context` are set here, with the live project's roles (the base class
        # takes the narrator's role names, which a live project does not use).
        observation = project.observation()
        model = project.require_model()
        calendar = project.calendar
        ids = project.activity_ids()
        nodes = project.nodes()
        self.project = project
        self.when = when
        self.clauses = tuple(clauses)
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

    def weekday_name(self, d: int) -> str:
        """The weekday of the prompt's day `d` in the project's calendar (spec section 11.1,
        v2.2.0): after a holiday it is not `d mod 5` of section 10.1."""
        return WEEKDAYS[self.project.calendar.date_of(d - self.offset).weekday()]

    def render(self, message: TeamMessage) -> str:
        """As `Context.render`, the author being the project manager, not a team member, and
        with the next days, the return days and the factors of more work worked out: the rules
        of the prompt ask for this arithmetic, which a small local model gets wrong (the WP11
        runs: day 4 for the Friday of day 14, 1.3 for 3 more of 5 days), and its repair rounds
        cannot see why. A weekday reads as in the application (spec section 11.3, v2.1.5):
        "until Friday" is absent through Friday, "back on Friday" is back that day."""
        observation, t = self.observation, self.day
        words = WEEKDAY_WORDS.get(self.project.definition.settings.language, {})
        weekday_name = self.weekday_name

        def said(before: str, d: int, form: int) -> str:
            name = weekday_name(d)
            return f"{before} {name}" + (f" ({words[name][form]})" if name in words else "")

        days = range(t + 1, t + NEXT_DAYS + 1)
        coming = ", ".join(said(f"day {d}", d, 0) for d in days)
        returns = "; ".join(
            f"{said('until', d, 1)} → {d + 1}, {said('back on', d, 2)} → {d}" for d in days
        )
        calendar = self.project.calendar
        months = MONTH_WORDS.get(self.project.definition.settings.language)

        def on(d: int) -> str:
            day = calendar.date_of(d - self.offset)
            text = f"{day.day} {day.strftime('%B')} {day.year}"
            return text + (f" ({day.day} {months[day.month - 1]})" if months else "")

        dated = "; ".join(
            f"until {on(d)} → {d + 1}, back on {on(d)} → {d}"
            for d in range(t + 1, t + DATED_DAYS + 1)
        )
        lines = [
            f"Today is day {t}, a {weekday_name(t)}. The next working days: {coming}.",
            f"The return_day by date (holidays left out; a date is not a day number): {dated}.",
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
        if self.clauses:
            lines += ["", "The message in numbered clauses:"]
            lines += [f"[{n}] {clause}" for n, clause in enumerate(self.clauses, start=1)]
        return "\n".join(lines)

    def extras(
        self, data: Mapping[str, object]
    ) -> tuple[tuple[int, ...], tuple[Question, ...], list[EventIssue]]:
        """The valid clause numbers and questions of an answer, and the issues of the others:
        a clause out of range, an unknown activity, fewer than two candidates, a growth that is
        not one, a return day outside the bounds of spec section 10.2."""
        n, t = len(self.clauses), self.day
        issues: list[EventIssue] = []
        unparsed: list[int] = []
        for value in _items(data.get("unparsed")):
            if isinstance(value, int) and 1 <= value <= n and value not in unparsed:
                unparsed.append(value)
            else:
                issues.append(
                    EventIssue("invalid_field", f"unparsed: {value!r} is no clause number 1-{n}.")
                )
        questions: list[Question] = []
        for i, raw in enumerate(_items(data.get("questions"))):
            where = f"questions[{i}]"
            try:
                question = Question.model_validate(raw)
            except ValueError:
                issues.append(EventIssue("invalid_field", f"{where} does not match the format."))
                continue
            problem = None
            if question.clause > n:
                problem = f"{where} names clause {question.clause}; there are {n}."
            elif question.kind == "unknown_person":
                r = question.return_day
                if r is not None and not t < r <= t + 365:
                    problem = f"{where} has a return_day that is not after today (day {t})."
            else:
                known = [j for j in dict.fromkeys(question.candidates) if j in self.names]
                if len(known) < 2:
                    problem = f"{where} needs two or more candidate activity ids."
                elif (
                    (question.extra_days is None) == (question.factor is None)
                    or (question.extra_days is not None and question.extra_days <= 0)
                    or (question.factor is not None and question.factor <= 1)
                ):
                    problem = f"{where} needs extra_days above 0 or a factor above 1."
                else:
                    question = question.model_copy(update={"candidates": tuple(known)})
            if problem is None:
                questions.append(question)
            else:
                issues.append(EventIssue("invalid_field", problem))
        return tuple(unparsed), tuple(questions), issues

    def draft(
        self,
        events: Sequence[object],
        issues: int,
        unparsed: Sequence[int] = (),
        questions: Sequence[Question] = (),
    ) -> MessageDraft:
        """The accepted events as check-in reports (person and task keys, calendar dates), the
        clauses turned into nothing and the questions for the manager."""
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
        drafts = []
        for question in questions:
            if question.kind == "unknown_person":
                r = question.return_day
                back = None if r is None else calendar.date_of(r - self.offset)
                drafts.append(
                    QuestionDraft(
                        kind=question.kind,
                        clause=question.clause,
                        first_day=self.when,
                        return_date=back,
                    )
                )
            else:
                drafts.append(
                    QuestionDraft(
                        kind=question.kind,
                        clause=question.clause,
                        candidates=tuple(keys[j] for j in question.candidates if j in keys),
                        extra_days=question.extra_days,
                        factor=question.factor,
                    )
                )
        return MessageDraft(
            absences=tuple(absences),
            increases=tuple(increases),
            new_tasks=tuple(new_tasks),
            issues=issues,
            unparsed=tuple(unparsed),
            questions=tuple(drafts),
        )
