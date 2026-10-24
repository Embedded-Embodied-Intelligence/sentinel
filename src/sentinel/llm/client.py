"""The call path shared by every backend: build the request, look it up in the record/replay
cache, call the backend on a miss, store the reply and validate it against the schema
(CLAUDE.md invariant 3; ADR-0018)."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, ClassVar

from pydantic import BaseModel, JsonValue

from sentinel.llm.cache import CACHE_MODES, CacheMode, LlmCache
from sentinel.llm.core import (
    CacheMiss,
    DomainValidator,
    LlmResponse,
    Message,
    Reply,
    Request,
    backend_schema,
    validate_reply,
    withhold_invalid,
)


@dataclass
class ClientStats:
    """Calls of a client: cache hits, backend calls, and tokens and recorded latency over all
    responses (cached ones with the values of their recording)."""

    calls: int = 0
    cache_hits: int = 0
    backend_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0

    @property
    def hit_rate(self) -> float | None:
        return self.cache_hits / self.calls if self.calls else None

    def add(self, reply: Reply, cache_hit: bool) -> None:
        self.calls += 1
        self.cache_hits += cache_hit
        self.backend_calls += not cache_hit
        self.prompt_tokens += reply.prompt_tokens
        self.completion_tokens += reply.completion_tokens
        self.latency_s += reply.latency_s

    def as_dict(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "cache_hits": self.cache_hits,
            "backend_calls": self.backend_calls,
            "hit_rate": None if self.hit_rate is None else round(self.hit_rate, 4),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "latency_s": round(self.latency_s, 3),
        }


class BaseClient(ABC):
    """An `LlmClient` over one backend and model; subclasses implement `_send`."""

    backend: ClassVar[str]

    def __init__(self, model: str, *, cache: LlmCache | None = None, mode: CacheMode = "auto"):
        if mode not in CACHE_MODES:
            raise ValueError(f"unknown cache mode {mode!r}; expected one of {CACHE_MODES}")
        if mode == "replay" and cache is None:
            raise ValueError("replay mode needs a cache")
        self.model = model
        self.cache = cache
        self.mode: CacheMode = mode
        self.stats = ClientStats()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(model={self.model!r}, mode={self.mode!r})"

    @property
    def digest(self) -> str | None:
        """Digest of the model's weights if the backend reports one (part of the cache key)."""
        return None

    def options(self) -> dict[str, JsonValue]:
        """Backend parameters that shape answers (part of the cache key)."""
        return {}

    def max_tokens_for(
        self, messages: Sequence[Message], json_schema: dict[str, JsonValue], max_tokens: int
    ) -> int:
        """The completion limit actually requested; a backend may lower `max_tokens` so that
        a request fits its limits (a deterministic function of the request)."""
        return max_tokens

    def request[ModelT: BaseModel](
        self,
        messages: Sequence[Message],
        *,
        schema: type[ModelT],
        temperature: float,
        seed: int,
        max_tokens: int,
    ) -> Request:
        """The request `complete` would send (and the cache key it would use)."""
        json_schema = backend_schema(schema)
        return Request(
            backend=self.backend,
            model=self.model,
            digest=self.digest,
            messages=tuple(messages),
            schema_name=schema.__name__,
            json_schema=json_schema,
            temperature=temperature,
            seed=seed,
            max_tokens=self.max_tokens_for(messages, json_schema, max_tokens),
            options=self.options(),
        )

    def complete[ModelT: BaseModel](
        self,
        messages: Sequence[Message],
        *,
        schema: type[ModelT],
        temperature: float = 0.0,
        seed: int,
        max_tokens: int,
        validator: DomainValidator | None = None,
    ) -> LlmResponse[ModelT]:
        """Answer from the cache or the backend (by mode) and validate it against `schema`. A
        cache without prompts stores an invalid answer, and a schema-valid one in which the
        domain `validator` finds issues, as its issue list only, and the answer comes back as
        stored, so that a replay sees what the recording saw (spec section 10)."""
        request = self.request(
            messages, schema=schema, temperature=temperature, seed=seed, max_tokens=max_tokens
        )
        key = request.key
        reply = None
        if self.cache is not None and self.mode != "record":
            reply = self.cache.get(key)
        cache_hit = reply is not None
        if reply is None:
            if self.mode == "replay":
                raise CacheMiss(f"{self.backend} request {key[:12]} is not in the cache (replay)")
            reply = self._send(request)
            if self.cache is not None:
                if not self.cache.store_prompts:
                    reply = withhold_invalid(reply, schema, validator)
                self.cache.put(request, reply)
        self.stats.add(reply, cache_hit)
        return validate_reply(reply, schema, key=key, cache_hit=cache_hit)

    @abstractmethod
    def _send(self, request: Request) -> Reply:
        """Call the backend once (with its own retries) and return its reply."""
