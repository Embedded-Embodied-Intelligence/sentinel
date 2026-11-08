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
from datetime import date
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from sentinel.agent.candidates import Candidate
from sentinel.agent.decide import DecisionRecord
from sentinel.agent.params import SentinelParams
from sentinel.app.errors import AppError
from sentinel.app.events import FactCheck, LlmExplanation
from sentinel.app.live import LiveProject
from sentinel.app.message_reader import (
    MessageContext,
    MessageDraft,
    draft,
    read,
)
from sentinel.app.store import Store
from sentinel.app.terms import internal_terms
from sentinel.experiments.proposal_study import compile_entries
from sentinel.interpret.actions import ProposalSettings, answer_entries, ask
from sentinel.interpret.describe import state_summary
from sentinel.interpret.explain import (
    EXPLAIN_PROMPT,
    ExplainSettings,
    Explanation,
    check,
    render_record,
)
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
from sentinel.llm.whisper import GroqWhisper, Transcriber, Transcript, silent_wav
from sentinel.simulation.state import (
    Observation,
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
USAGE_KEY = "llm"
VOICE_KEY = "voice_s"  # seconds of audio sent to Whisper
VOICE_MIN_S = 10  # the shortest request a provider bills (Groq)
EXPLAIN_LIVE_PROMPT = "explain_live"  # the explanation in the page's language (WP12, ADR-0029)
LANGUAGE_NAMES = {"en": "English", "pl": "Polish"}
WBS_LIVE_PROMPT = "wbs_live"  # the application's addendum to the extraction prompt (WP12)
# A person waits for these calls: a limit on one call of a local model (a first load, a slow CPU)
# and of a cloud model, with fewer retries than a study's (config `llm_timeout_s`; docs/deploy.md).
OLLAMA_TIMEOUT_S = 600.0
CLOUD_TIMEOUT_S = 90.0
CLOUD_RETRIES = 2
CLOUD_MAX_WAIT_S = 60.0


class LlmSettings(BaseModel):
    """The provider settings as stored (the keys only in the file); `groq_key` is Groq's key for
    recordings when the provider is another one (WP14, ADR-0031)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: Provider = "none"
    model: str | None = Field(default=None, max_length=200)
    host: str | None = Field(default=None, max_length=300)
    api_key: str | None = Field(default=None, max_length=500)
    groq_key: str | None = Field(default=None, max_length=500)


class LlmSettingsView(BaseModel):
    """What the API shows of the settings: everything but the key."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: Provider
    model: str | None
    host: str | None
    has_key: bool
    available: bool
    has_groq_key: bool = False
    voice: bool = False  # recordings can be written out (WP14)


class LlmSettingsUpdate(BaseModel):
    """A change of the settings; a missing key keeps the stored one, "" removes it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: Provider
    model: str | None = Field(default=None, max_length=200)
    host: str | None = Field(default=None, max_length=300)
    api_key: str | None = Field(default=None, max_length=500)
    groq_key: str | None = Field(default=None, max_length=500)


ClientFactory = Callable[[LlmSettings, LlmCache], LlmClient]
TranscriberFactory = Callable[[Secret], Transcriber]


def make_transcriber(key: Secret) -> Transcriber:
    """Groq's Whisper with the key for recordings (ADR-0031)."""
    return GroqWhisper(key)


def voice_failure(error: LlmError) -> AppError:
    """A failed transcription as a manager reads it (WP14)."""
    code = "voice_failed"
    if isinstance(error, TransportTimeout):
        code = "voice_timeout"
    elif isinstance(error, TransportError):
        code = "voice_unreachable"
    elif error.status in (401, 403):
        code = "voice_key"
    elif error.status in (400, 413, 415, 422):
        code = "voice_audio"
    elif error.status == 429:
        code = "voice_quota"
    return AppError(code, "unavailable", detail=type(error).__name__)


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
        session_cap: int | None = None,
        voice_cap: int | None = None,
        voice_session_cap: int | None = None,
        factory: ClientFactory = make_client,
        transcriber: TranscriberFactory = make_transcriber,
    ) -> None:
        self.settings_file = settings_file
        self.cache_dir = cache_dir
        self.store = store
        self.mode = mode
        self.daily_cap = daily_cap
        self.session_cap = session_cap
        self.voice_cap = voice_cap
        self.voice_session_cap = voice_session_cap
        self.factory = factory
        self.transcriber = transcriber

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
            has_groq_key=bool(settings.groq_key),
            voice=self.voice,
        )

    @property
    def available(self) -> bool:
        settings = self.settings()
        if self.mode == "off" or settings.provider == "none":
            return False
        return settings.provider == "ollama" or bool(settings.api_key)

    @property
    def voice(self) -> bool:
        """Whether recordings can be written out: the AI is set up (the text is read by it) and
        a Groq key is there, the provider's own or the one for recordings (WP14)."""
        return self.available and _voice_key(self.settings()) is not None

    def update(self, change: LlmSettingsUpdate) -> LlmSettingsView:
        """Store new settings in the settings file (mode 0600)."""
        current = self.settings()
        key = current.api_key if change.api_key is None else (change.api_key or None)
        if change.provider in ("groq", "openrouter") and not key:
            raise AppError("settings_key_needed")
        groq = current.groq_key if change.groq_key is None else (change.groq_key or None)
        settings = LlmSettings(
            provider=change.provider,
            model=change.model or None,
            host=change.host or None,
            api_key=key if change.provider in ("groq", "openrouter") else None,
            groq_key=groq,
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

    def _limits(
        self, key: str, cap: int | None, session_cap: int | None, session: str | None
    ) -> list[tuple[str, int | None]]:
        """The usage keys of a request with their caps: server-wide, and per visitor when
        capped (the public demo, WP17: one visitor cannot use up everyone's AI)."""
        capped = self.mode == "capped"
        limits = [(key, cap if capped else None)]
        if capped and session is not None and session_cap is not None:
            limits.append((f"{key}:{session}", session_cap))
        return limits

    def client(self, session: str | None = None) -> LlmClient:
        """The client for one feature request, counted against the daily caps."""
        if not self.available:
            raise AppError("llm_disabled", "unavailable")
        if not self.store.use_all(
            self._limits(USAGE_KEY, self.daily_cap, self.session_cap, session)
        ):
            raise AppError("llm_cap", "limit")
        settings = self.settings()
        cache = RequestCache(self.cache_dir / f"{settings.provider}.jsonl", store_prompts=False)
        return self.factory(settings, cache)

    def transcribe(
        self,
        audio: bytes,
        content_type: str,
        *,
        language: str | None,
        vocabulary: str = "",
        preview: bool = False,
        session: str | None = None,
    ) -> Transcript:
        """A recording written out by Groq's Whisper (ADR-0031), counted against the daily cap
        as a feature request, except a live preview of a recording still running (v2, WP15);
        every request, previews too, counts its seconds of audio against the voice caps (at
        least the 10 s a request is billed; WP17). Neither the audio nor the text is kept."""
        key = _voice_key(self.settings())
        if not self.available or key is None:
            raise AppError("voice_disabled", "unavailable")
        if not preview and not self.store.use_all(
            self._limits(USAGE_KEY, self.daily_cap, self.session_cap, session)
        ):
            raise AppError("llm_cap", "limit")
        seconds = self._limits(VOICE_KEY, self.voice_cap, self.voice_session_cap, session)
        if not self.store.use_all(seconds, amount=VOICE_MIN_S):
            raise AppError("voice_cap", "limit")
        try:
            found = self.transcriber(key).transcribe(
                audio, content_type, language=language, prompt=vocabulary
            )
        except LlmError as exc:
            raise voice_failure(exc) from exc
        if found.seconds is not None and found.seconds > VOICE_MIN_S:
            extra = int(found.seconds - VOICE_MIN_S + 0.999)
            self.store.use_all([(k, None) for k, _ in seconds], amount=extra)
        return found

    def test_voice(self) -> str:
        """Write out a second of a quiet tone (a connection test of recordings); the model's
        name, or AppError with the reason."""
        return self.transcribe(silent_wav(), "audio/wav", language="en").model

    def extract(
        self,
        text: str,
        seed: int,
        roles: Mapping[str, int] | None = None,
        session: str | None = None,
    ) -> Session:
        """WP6a extraction with up to three repair rounds (spec section 10); the roles of the
        project's team, if it has one, follow the description."""
        client = self.client(session)
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
        session: str | None = None,
    ) -> LlmExplanation:
        """An LLM explanation of a recommendation with its faithfulness check (10.4), in the
        page's `language` with the actions named as the page names them (`names` by label) and
        no internal term (WP12, B7): a text with one is asked for once more, and if the second
        has one too, the page keeps the template explanation alone. The prompts stay English
        (ADR-0029)."""
        rendered = render_record(record, observation, params, roles)
        client = self.client(session)
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
        self,
        project: LiveProject,
        text: str,
        when: date,
        seed: int,
        session: str | None = None,
    ) -> MessageDraft:
        """The reports of a manager's check-in message dated `when` (spec section 11.3, v2.3.0:
        the application's reader with its repair rounds, dates settled by code), for the manager
        to confirm one by one; never a reason for an absence (invariant 7)."""
        context = MessageContext(project, when, text)
        client = self.client(session)
        try:
            reading = read(client, context, seed=seed)
        except LlmError as exc:
            raise failure(exc) from exc
        if reading.answer is None:
            error = reading.response.error
            detail = "no answer" if error is None else error.kind
            raise AppError("parse_failed", "invalid", detail=detail)
        return draft(reading, context)

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


def _voice_key(settings: LlmSettings) -> Secret | None:
    """The key for recordings: Groq's key for them, else the provider's if it is Groq."""
    if settings.groq_key:
        return Secret(settings.groq_key)
    if settings.provider == "groq" and settings.api_key:
        return Secret(settings.api_key)
    return None


class Ping(BaseModel):
    """The answer of a connection test."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ok: bool
