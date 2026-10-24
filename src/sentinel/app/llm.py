"""The optional language model of the application (spec section 10; CLAUDE.md invariants 3, 4
and 7): the provider settings, the client, and the two features that use it, the extraction of
tasks from a text (WP6a) and the explanation of a recommendation (spec section 10.4).

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
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from sentinel.agent.candidates import Candidate
from sentinel.agent.decide import DecisionRecord
from sentinel.agent.params import SentinelParams
from sentinel.app.errors import AppError
from sentinel.app.events import FactCheck, LlmExplanation
from sentinel.app.store import Store
from sentinel.experiments.proposal_study import compile_entries
from sentinel.interpret.actions import ProposalSettings, answer_entries, ask
from sentinel.interpret.describe import state_summary
from sentinel.interpret.explain import ExplainSettings, check, explain, render_record
from sentinel.llm import (
    GroqClient,
    LlmCache,
    LlmClient,
    LlmError,
    OllamaClient,
    OpenRouterClient,
    Secret,
)
from sentinel.simulation.state import Observation
from sentinel.wbs.extract import ExtractionSettings, Session, repair

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


def make_client(settings: LlmSettings, cache: LlmCache) -> LlmClient:
    """The client of the configured provider over `cache` (`auto`: replay a cached answer, else
    call); the key is passed as a `Secret`, never read from `.env` here."""
    model = settings.model or DEFAULT_MODELS[settings.provider]
    key = Secret(settings.api_key) if settings.api_key else None
    match settings.provider:
        case "ollama":
            return OllamaClient(
                model, num_ctx=12288, host=settings.host, cache=cache, mode="auto", env_file=None
            )
        case "groq":
            return GroqClient(
                model,
                tokens_per_minute=8000,
                extra=GROQ_OPTIONS,
                api_key=key,
                env_file=None,
                cache=cache,
                mode="auto",
            )
        case "openrouter":
            return OpenRouterClient(
                model,
                tokens_per_minute=None,
                extra={"provider": OPENROUTER_PROVIDER, **GROQ_OPTIONS},
                api_key=key,
                env_file=None,
                cache=cache,
                mode="auto",
            )
    raise AppError("llm_disabled", "unavailable")


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
            raise AppError("settings_invalid", detail="this provider needs an API key")
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
        cache = LlmCache(self.cache_dir / f"{settings.provider}.jsonl", store_prompts=False)
        return self.factory(settings, cache)

    def extract(self, text: str, seed: int) -> Session:
        """WP6a extraction with up to three repair rounds (spec section 10)."""
        client = self.client()
        try:
            return repair(client, text, seed=seed, settings=EXTRACTION)
        except LlmError as exc:
            raise AppError("llm_failed", "unavailable", detail=type(exc).__name__) from exc

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
            raise AppError("llm_failed", "unavailable", detail=type(exc).__name__) from exc
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
