"""Messages, requests, replies and responses of the LLM layer, its client protocol and errors
(CLAUDE.md invariant 3; ADR-0018).

A `Request` holds everything that shapes an answer (backend, model, model digest, messages,
JSON schema and decoding parameters); the SHA-256 of its canonical JSON is the cache key. A
backend returns a `Reply`, which the cache stores. `validate_reply` turns a reply into an
`LlmResponse`: the answer must parse as JSON and validate against the pydantic schema, and a
violation comes back as a structured `OutputError`, never as an exception.
"""

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    NonNegativeFloat,
    NonNegativeInt,
    ValidationError,
)

ChatRole = Literal["system", "user", "assistant"]
OutputErrorKind = Literal["empty", "json", "truncated", "schema"]
CHARS_PER_TOKEN = 3.0  # conservative token estimate for limits and the fake backend


class LlmError(RuntimeError):
    """A backend could not answer (transport, HTTP status, protocol or cache); never raised for
    an answer that violates its schema."""


class CacheMiss(LlmError):
    """A request is not in the cache and the cache is in replay mode."""


class RequestTooLarge(LlmError):
    """A request can never fit the backend's limits (context or tokens per minute)."""


class QuotaExhausted(LlmError):
    """The backend's rate limit asks for a longer wait than allowed; finished calls are cached,
    so the same run can resume later."""

    def __init__(self, message: str, retry_after_s: float) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class Message(BaseModel):
    """One chat message."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: ChatRole
    content: str


class Request(BaseModel):
    """Everything that shapes an answer; `key` is the SHA-256 of its canonical JSON."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    backend: str = Field(min_length=1)
    model: str = Field(min_length=1)
    digest: str | None
    messages: tuple[Message, ...]
    schema_name: str
    json_schema: dict[str, JsonValue]
    temperature: float = Field(ge=0, allow_inf_nan=False)
    seed: int
    max_tokens: int = Field(gt=0)
    options: dict[str, JsonValue] = Field(default_factory=dict)

    @property
    def key(self) -> str:
        return sha256_json(self.model_dump(mode="json"))


class Reply(BaseModel):
    """What a backend returned for a request, as the cache stores it; `latency_s` is the wall
    time of the call that produced it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    model: str
    prompt_tokens: NonNegativeInt
    completion_tokens: NonNegativeInt
    latency_s: NonNegativeFloat
    finish_reason: str | None = None
    meta: dict[str, JsonValue] = Field(default_factory=dict)


@dataclass(frozen=True)
class ErrorDetail:
    """One schema violation: location (e.g. `activities[3].duration_days`), message, type."""

    loc: str
    message: str
    type: str


@dataclass(frozen=True)
class OutputError:
    """Why an answer is unusable: empty, not JSON, cut off at the token limit, or against the
    schema (then with one detail per violation)."""

    kind: OutputErrorKind
    message: str
    details: tuple[ErrorDetail, ...] = ()


@dataclass(frozen=True)
class LlmResponse[ModelT: BaseModel]:
    """A validated answer: its text, the parsed JSON (None if it does not parse), the schema
    model (None on a violation, then `error` says why), token counts, the recorded latency and
    whether it came from the cache."""

    text: str
    parsed: Any
    value: ModelT | None
    error: OutputError | None
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_s: float
    cache_hit: bool
    finish_reason: str | None
    key: str

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class LlmClient(Protocol):
    """Chat completion constrained to a JSON schema; problems of the answer come back in
    `LlmResponse.error`, while failures of the backend raise `LlmError`."""

    def complete[ModelT: BaseModel](
        self,
        messages: Sequence[Message],
        *,
        schema: type[ModelT],
        temperature: float = 0.0,
        seed: int,
        max_tokens: int,
    ) -> LlmResponse[ModelT]: ...


def canonical_json(data: object) -> str:
    """JSON with sorted keys and no spaces, UTF-8 characters kept."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(data: object) -> str:
    """SHA-256 hex digest of the canonical JSON of `data`."""
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


def estimate_tokens(text: str) -> int:
    """A conservative token count of `text` (CHARS_PER_TOKEN characters per token)."""
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def backend_schema(model: type[BaseModel]) -> dict[str, JsonValue]:
    """The model's JSON schema for a backend: `$ref`s inlined, `$defs`, titles and descriptions
    dropped, so that editing a docstring changes no cache key."""
    schema = model.model_json_schema()
    definitions = schema.pop("$defs", {})
    result = _inline(schema, definitions, ())
    if not isinstance(result, dict):
        raise TypeError(f"the schema of {model.__name__} is not an object schema")
    return result


def _inline(node: JsonValue, definitions: Mapping[str, Any], seen: tuple[str, ...]) -> JsonValue:
    if isinstance(node, list):
        return [_inline(item, definitions, seen) for item in node]
    if not isinstance(node, dict):
        return node
    reference = node.get("$ref")
    if isinstance(reference, str):
        name = reference.removeprefix("#/$defs/")
        if name in seen or name not in definitions:
            raise ValueError(f"cannot inline the schema reference {reference!r}")
        return _inline(definitions[name], definitions, (*seen, name))
    result: dict[str, JsonValue] = {}
    for key, value in node.items():
        if key in ("title", "description"):
            continue
        if key == "properties" and isinstance(value, dict):
            result[key] = {name: _inline(sub, definitions, seen) for name, sub in value.items()}
        else:
            result[key] = _inline(value, definitions, seen)
    return result


def validate_reply[ModelT: BaseModel](
    reply: Reply, schema: type[ModelT], *, key: str, cache_hit: bool
) -> LlmResponse[ModelT]:
    """Parse the reply's text as JSON and validate it against `schema`; problems become the
    response's `OutputError` (kind `truncated` when the backend stopped at the token limit)."""
    parsed: Any = None
    value: ModelT | None = None
    error: OutputError | None = None
    cut_off = reply.finish_reason == "length"
    if not reply.text.strip():
        error = OutputError("truncated" if cut_off else "empty", "the answer is empty")
    else:
        try:
            parsed = json.loads(reply.text)
        except json.JSONDecodeError as exc:
            where = f"{exc.msg} at line {exc.lineno}, column {exc.colno}"
            error = OutputError("truncated" if cut_off else "json", where)
        else:
            try:
                value = schema.model_validate(parsed)
            except ValidationError as exc:
                details = tuple(
                    ErrorDetail(_location(e["loc"]), e["msg"], e["type"]) for e in exc.errors()
                )
                error = OutputError("schema", f"{len(details)} schema violations", details)
    return LlmResponse(
        text=reply.text,
        parsed=parsed,
        value=value,
        error=error,
        model=reply.model,
        prompt_tokens=reply.prompt_tokens,
        completion_tokens=reply.completion_tokens,
        latency_s=reply.latency_s,
        cache_hit=cache_hit,
        finish_reason=reply.finish_reason,
        key=key,
    )


def _location(loc: Sequence[int | str]) -> str:
    path = "".join(f"[{part}]" if isinstance(part, int) else f".{part}" for part in loc)
    return path.removeprefix(".")
