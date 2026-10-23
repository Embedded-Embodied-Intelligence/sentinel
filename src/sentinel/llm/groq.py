"""Groq cloud backend: OpenAI-compatible chat completions with a JSON schema (best effort; the
schema's free-form crew map rules out strict mode) or JSON mode, retries with exponential
backoff on 429, 498 and 5xx that honour `retry-after`, and a client-side tokens-per-minute
limit (Groq API documentation, read 2026-10-23; ADR-0018).

The API key comes from `GROQ_API_KEY` in the environment or `.env` and is loaded only for a
backend call, so replaying from the cache needs no key. It never appears in a repr, a log, a
cache entry or an exception message.
"""

import json
import math
import re
import time
from collections.abc import Callable, Mapping, Sequence
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import JsonValue

from sentinel.llm.cache import CacheMode, LlmCache
from sentinel.llm.client import BaseClient
from sentinel.llm.core import (
    LlmError,
    Message,
    QuotaExhausted,
    Reply,
    Request,
    RequestTooLarge,
    canonical_json,
    estimate_tokens,
)
from sentinel.llm.http import HttpReply, Transport, TransportError, urllib_transport
from sentinel.llm.secrets import DEFAULT_ENV_FILE, Secret, load_secret, redact

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
API_KEY_VARIABLE = "GROQ_API_KEY"  # the variable's name  # pragma: allowlist secret
ResponseFormat = Literal["json_schema", "json_object"]
RETRYABLE = frozenset({429, 498, 500, 502, 503, 504})
MAX_BACKOFF_S = 60.0
_DURATION = re.compile(r"(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m(?!s))?(?:(\d+(?:\.\d+)?)s)?")


class TokenRateLimiter:
    """At most `tokens_per_minute` tokens in any sliding window of `window_s` seconds: a
    request waits until its estimate (at most the whole limit) fits, and its booking is then
    corrected to the real usage."""

    def __init__(
        self,
        tokens_per_minute: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        window_s: float = 60.0,
    ) -> None:
        if tokens_per_minute < 1:
            raise ValueError(f"tokens_per_minute must be positive, got {tokens_per_minute}")
        self.limit = tokens_per_minute
        self.window_s = window_s
        self.clock = clock
        self.sleep = sleep
        self.waited_s = 0.0
        self._entries: list[list[float]] = []  # [time, tokens]

    def used(self) -> int:
        """Tokens of the current window."""
        self._expire(self.clock())
        return int(sum(tokens for _, tokens in self._entries))

    def acquire(self, tokens: int) -> list[float]:
        """Wait until `tokens` (capped at the limit) fit the window, then book them; returns
        the booking."""
        tokens = min(tokens, self.limit)
        while True:
            now = self.clock()
            self._expire(now)
            if sum(booked for _, booked in self._entries) + tokens <= self.limit:
                booking = [now, float(tokens)]
                self._entries.append(booking)
                return booking
            pause = max(0.01, self._entries[0][0] + self.window_s - now)
            self.waited_s += pause
            self.sleep(pause)

    def settle(self, booking: list[float], tokens: int) -> None:
        """Replace a booking's estimate with the tokens actually used."""
        booking[1] = float(tokens)

    def _expire(self, now: float) -> None:
        self._entries = [entry for entry in self._entries if entry[0] + self.window_s > now]


class GroqClient(BaseClient):
    """A Groq model; `tokens_per_minute` (None: no client-side limit) spaces the requests.
    Groq charges the tokens a request uses, not its completion limit (a request of 633 prompt
    tokens with a limit of 7,900 completion tokens passed an 8,000 TPM limit on 2026-10-23)."""

    backend = "groq"

    def __init__(
        self,
        model: str,
        *,
        tokens_per_minute: int | None,
        response_format: ResponseFormat = "json_schema",
        extra: Mapping[str, JsonValue] | None = None,
        api_key: Secret | None = None,
        env_file: Path | None = DEFAULT_ENV_FILE,
        url: str = GROQ_URL,
        timeout_s: float = 300.0,
        max_retries: int = 6,
        max_wait_s: float = 900.0,
        backoff_s: float = 2.0,
        cache: LlmCache | None = None,
        mode: CacheMode = "auto",
        transport: Transport = urllib_transport,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        super().__init__(model, cache=cache, mode=mode)
        self.tokens_per_minute = tokens_per_minute
        self.response_format: ResponseFormat = response_format
        self.extra: dict[str, JsonValue] = dict(extra or {})
        self.url = url
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.max_wait_s = max_wait_s
        self.backoff_s = backoff_s
        self.transport = transport
        self.sleep = sleep
        self.retries = 0
        self.limiter = (
            None
            if tokens_per_minute is None
            else TokenRateLimiter(tokens_per_minute, clock=clock, sleep=sleep)
        )
        self._key = api_key
        self._env_file = env_file
        self._clock = clock

    def __repr__(self) -> str:
        return f"GroqClient(model={self.model!r}, mode={self.mode!r}, api_key=<redacted>)"

    def options(self) -> dict[str, JsonValue]:
        return {"response_format": self.response_format, **self.extra}

    def prompt_estimate(
        self, messages: Sequence[Message], json_schema: Mapping[str, JsonValue]
    ) -> int:
        """Conservative prompt tokens: messages plus the schema (sent in the request)."""
        text = "".join(message.content for message in messages)
        return (
            estimate_tokens(text)
            + estimate_tokens(canonical_json(json_schema))
            + 16 * len(messages)
        )

    def _send(self, request: Request) -> Reply:
        key = self._api_key()
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [message.model_dump(mode="json") for message in request.messages],
            "temperature": request.temperature,
            "seed": request.seed,
            "max_completion_tokens": request.max_tokens,
            "response_format": self._response_format(request),
            **self.extra,
        }
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {key.reveal()}",
            "Content-Type": "application/json",
            "User-Agent": "sentinel-research/0.1",
        }
        estimate = self.prompt_estimate(request.messages, request.json_schema) + request.max_tokens
        booking = None if self.limiter is None else self.limiter.acquire(estimate)
        attempt = 0
        while True:
            started = self._clock()
            try:
                reply: HttpReply | None = self.transport(
                    "POST", self.url, body=body, headers=headers, timeout=self.timeout_s
                )
                failure = f"HTTP {reply.status}: {reply.snippet()}" if reply else ""
            except TransportError as exc:
                reply, failure = None, str(exc)
            latency = self._clock() - started
            if reply is not None and reply.status == 200:
                result = self._reply(reply, latency, attempt)
                if booking is not None and self.limiter is not None:
                    self.limiter.settle(booking, result.prompt_tokens + result.completion_tokens)
                return result
            if reply is not None and reply.status == 400:
                failed = self._failed_generation(reply)
                if failed is not None:
                    return Reply(
                        text=failed,
                        model=request.model,
                        prompt_tokens=estimate - request.max_tokens,
                        completion_tokens=estimate_tokens(failed),
                        latency_s=round(latency, 3),
                        finish_reason="json_validate_failed",
                        meta={"tokens_estimated": True, "retries": attempt},
                    )
            message = key.redact(f"Groq request failed: {failure}")
            if reply is not None and reply.status == 413:
                raise RequestTooLarge(message)
            if reply is not None and reply.status not in RETRYABLE:
                raise LlmError(message)
            wait = self._wait(reply, attempt)
            if reply is not None and reply.status == 429 and wait > self.max_wait_s:
                raise QuotaExhausted(
                    f"{message}; the rate limit asks for {wait:.0f} s, more than the allowed "
                    f"{self.max_wait_s:.0f} s",
                    wait,
                )
            if attempt >= self.max_retries:
                if reply is not None and reply.status == 429:
                    raise QuotaExhausted(
                        f"{message}; still rate limited after {attempt + 1} attempts", wait
                    )
                raise LlmError(f"{message}; gave up after {attempt + 1} attempts")
            attempt += 1
            self.retries += 1
            self.sleep(wait)

    def _api_key(self) -> Secret:
        if self._key is None:
            self._key = load_secret(API_KEY_VARIABLE, env_file=self._env_file)
        if self._key is None:
            raise LlmError(
                f"{API_KEY_VARIABLE} is not set: put it into .env (see .env.example) or the "
                "environment"
            )
        return self._key

    def _response_format(self, request: Request) -> dict[str, JsonValue]:
        if self.response_format == "json_object":
            return {"type": "json_object"}
        return {
            "type": "json_schema",
            "json_schema": {
                "name": request.schema_name,
                "schema": request.json_schema,
                "strict": False,
            },
        }

    def _reply(self, reply: HttpReply, latency: float, attempt: int) -> Reply:
        data = reply.json()
        try:
            choice = data["choices"][0]
            text = choice["message"].get("content") or ""
            usage = data.get("usage") or {}
        except (KeyError, IndexError, TypeError, AttributeError):
            raise LlmError(f"Groq returned an unexpected body: {redact(reply.snippet())}") from None
        details = usage.get("completion_tokens_details") or {}
        prompt_details = usage.get("prompt_tokens_details") or {}
        meta: dict[str, JsonValue] = {
            "retries": attempt,
            "system_fingerprint": data.get("system_fingerprint"),
            "reasoning_tokens": details.get("reasoning_tokens"),
            "cached_tokens": prompt_details.get("cached_tokens"),
            "queue_time_s": usage.get("queue_time"),
            "server_total_s": usage.get("total_time"),
            **{
                name.removeprefix("x-ratelimit-").replace("-", "_"): value
                for name, value in sorted(reply.headers.items())
                if name.startswith("x-ratelimit-limit-")
                or name.startswith("x-ratelimit-remaining-")
            },
        }
        return Reply(
            text=str(text),
            model=str(data.get("model") or ""),
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            latency_s=round(latency, 3),
            finish_reason=choice.get("finish_reason"),
            meta={name: value for name, value in meta.items() if value is not None},
        )

    @staticmethod
    def _failed_generation(reply: HttpReply) -> str | None:
        """The text of an answer that failed Groq's own schema check, if this is that error."""
        try:
            error = reply.json().get("error") or {}
        except (LlmError, AttributeError):
            return None
        if not isinstance(error, dict) or error.get("code") != "json_validate_failed":
            return None
        failed = error.get("failed_generation")
        return failed if isinstance(failed, str) else ""

    def _wait(self, reply: HttpReply | None, attempt: int) -> float:
        backoff = min(MAX_BACKOFF_S, self.backoff_s * 2.0**attempt)
        if reply is None or reply.status != 429:
            return backoff
        for header in ("retry-after", "x-ratelimit-reset-tokens", "x-ratelimit-reset-requests"):
            seconds = parse_wait(reply.headers.get(header))
            if seconds is not None:
                return max(seconds, 0.0)
        return backoff


def parse_wait(value: str | None) -> float | None:
    """Seconds in a `retry-after` (seconds or an HTTP date) or a Groq reset header such as
    `2m59.56s` or `350ms`; None if absent or unreadable."""
    if value is None or not value.strip():
        return None
    text = value.strip()
    try:
        return float(text)
    except ValueError:
        pass
    if text.endswith("ms"):
        try:
            return float(text[:-2]) / 1000
        except ValueError:
            return None
    match = _DURATION.fullmatch(text)
    if match is not None and any(match.groups()):
        hours, minutes, seconds = (float(group) if group else 0.0 for group in match.groups())
        return 3600 * hours + 60 * minutes + seconds
    try:
        moment = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    return max(0.0, moment.timestamp() - time.time()) if math.isfinite(moment.timestamp()) else None
