"""OpenRouter backend (WP6c): OpenAI-compatible chat completions with the provider routing in
the request (`provider: {order, allow_fallbacks: false, require_parameters: true}`), so that
the model and its serving hardware stay those of one provider (Groq for gpt-oss-120b in WP6),
and the provider that served each answer recorded and checked (OpenRouter documentation on
provider routing, errors, limits and router metadata, read 2026-10-23; ADR-0018, amendment).

Errors: an answer that failed the provider's JSON check (Groq's `json_validate_failed` and
`output_parse_failed`, passed on in `error.metadata.raw`) comes back as an answer; an error
inside an HTTP 200 body counts with its own code; 408, 429 and 5xx are retried, a 429 after
`Retry-After` or `X-RateLimit-Reset`; a 402 of the in-flight budget waits for `Retry-After`
like a 429, while any other 402 (no credits, a key limit) and a budget 403 stop the run with
`CreditsExhausted`, which resumes from the cache once credits are added. Answers carry no
rate-limit headers, so the client-side limit is the configured one, if any.

The API key comes from `OPENROUTER_API_KEY` in the environment or `.env` and is loaded only for
a backend call.
"""

import json
import re
import time
from collections.abc import Mapping
from typing import Any

from pydantic import JsonValue

from sentinel.llm.core import CreditsExhausted, LlmError
from sentinel.llm.groq import failed_generation
from sentinel.llm.http import HttpReply
from sentinel.llm.openai_compat import OpenAICompatibleClient, parse_wait
from sentinel.llm.secrets import Secret

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
API_KEY_VARIABLE = "OPENROUTER_API_KEY"  # the variable's name  # pragma: allowlist secret
CREDITS_URL = "https://openrouter.ai/settings/credits"
RETRYABLE = frozenset({408, 429, 500, 502, 503, 504})
IN_FLIGHT = "openrouter_in_flight_budget"  # error.metadata.limit_source of a transient 402


class OpenRouterClient(OpenAICompatibleClient):
    """A model on OpenRouter; the routing is the `provider` field of `extra`, and with
    `allow_fallbacks: false` an answer served by a provider outside `order` is an error (it is
    not cached)."""

    backend = "openrouter"
    service = "OpenRouter"
    default_url = OPENROUTER_URL
    key_variable = API_KEY_VARIABLE
    token_field = "max_tokens"
    retryable = RETRYABLE

    @property
    def routing(self) -> Mapping[str, Any]:
        """The request's provider routing (empty: OpenRouter's default routing)."""
        provider = self.extra.get("provider")
        return provider if isinstance(provider, dict) else {}

    def request_headers(self, key: Secret) -> dict[str, str]:
        # router metadata names the endpoint that served the answer
        return {**super().request_headers(key), "X-OpenRouter-Metadata": "enabled"}

    def status_of(self, reply: HttpReply) -> int:
        """The HTTP status; the code of an error inside a 200 body (502 for an error finish);
        429 for a 402 of the in-flight budget, which asks for a wait rather than credits."""
        if reply.status == 402 and limit_source(reply) == IN_FLIGHT:
            return 429
        if reply.status != 200:
            return reply.status
        try:
            data = reply.json()
        except LlmError:
            return 200  # reported as an unexpected body
        if not isinstance(data, dict):
            return 200
        error, choices = data.get("error"), data.get("choices")
        if isinstance(error, dict) and not choices:
            code = error.get("code")
            return code if isinstance(code, int) and code != 200 else 502
        first = choices[0] if isinstance(choices, list) and choices else None
        if isinstance(first, dict) and first.get("finish_reason") == "error":
            return 502
        return 200

    def served_by_pinned(self, provider: str) -> bool:
        """Whether `provider` (a display name such as `Groq`) is one of the routing's `order`
        (slugs such as `groq` or `cerebras/fp16`)."""
        pinned = {slug(str(name).split("/")[0]) for name in self.routing.get("order") or ()}
        return slug(provider) in pinned

    def _header_wait(self, headers: Mapping[str, str]) -> float | None:
        seconds = parse_wait(headers.get("retry-after"))
        return seconds if seconds is not None else reset_wait(headers.get("x-ratelimit-reset"))

    def _failed_generation(self, reply: HttpReply) -> tuple[str, str] | None:
        metadata = error_metadata(reply)
        raw: object = metadata.get("raw")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                return None
        if not isinstance(raw, dict):
            return None
        return failed_generation(raw.get("error", raw))

    def _error_meta(self, reply: HttpReply) -> dict[str, JsonValue]:
        provider = error_metadata(reply).get("provider_name")
        return {"provider": provider} if isinstance(provider, str) else {}

    def _stop(self, reply: HttpReply, status: int | None, message: str) -> None:
        source = limit_source(reply)
        if status == 402 or (status == 403 and source is not None):
            raise CreditsExhausted(
                f"{message}; OpenRouter cannot pay for the request ({source or 'credits'}): add "
                f"credits at {CREDITS_URL} or raise the key's limit"
            )

    def _check_reply(self, data: Mapping[str, Any]) -> None:
        provider = served_provider(data)
        if (
            provider is not None
            and self.routing.get("order")
            and self.routing.get("allow_fallbacks") is False
            and not self.served_by_pinned(provider)
        ):
            raise LlmError(
                f"OpenRouter served the request by {provider!r}, not by the pinned "
                f"{list(self.routing['order'])}; the answer is not used"
            )

    def _reply_meta(
        self, data: Mapping[str, Any], choice: Mapping[str, Any], usage: Mapping[str, Any]
    ) -> dict[str, JsonValue]:
        return {
            "provider": served_provider(data),
            "generation_id": data.get("id"),
            "cost": usage.get("cost"),  # OpenRouter credits (USD)
            "native_finish_reason": choice.get("native_finish_reason"),
        }


def served_provider(data: Mapping[str, Any]) -> str | None:
    """The provider that served a reply: its `provider` field, else the selected endpoint of
    its router metadata; None if the reply names none."""
    provider = data.get("provider")
    if isinstance(provider, str) and provider:
        return provider
    metadata = data.get("openrouter_metadata")
    endpoints = metadata.get("endpoints") if isinstance(metadata, dict) else None
    available = endpoints.get("available") if isinstance(endpoints, dict) else None
    for endpoint in available if isinstance(available, list) else ():
        if isinstance(endpoint, dict) and endpoint.get("selected"):
            name = endpoint.get("provider")
            return str(name) if name else None
    return None


def slug(name: str) -> str:
    """A provider's name in slug form: `Amazon Bedrock` -> `amazon-bedrock`."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def error_metadata(reply: HttpReply) -> dict[str, Any]:
    """The `error.metadata` object of an error reply ({} if there is none)."""
    try:
        data = reply.json()
    except LlmError:
        return {}
    error = data.get("error") if isinstance(data, dict) else None
    metadata = error.get("metadata") if isinstance(error, dict) else None
    return metadata if isinstance(metadata, dict) else {}


def limit_source(reply: HttpReply) -> str | None:
    """The `error.metadata.limit_source` of a 402 or 403 (which credit or budget limit)."""
    source = error_metadata(reply).get("limit_source")
    return source if isinstance(source, str) else None


def reset_wait(value: str | None, now: float | None = None) -> float | None:
    """Seconds until an `X-RateLimit-Reset` time: epoch milliseconds or seconds, else a wait
    as `parse_wait` reads it; None if absent or unreadable."""
    seconds = parse_wait(value)
    if seconds is None:
        return None
    moment = time.time() if now is None else now
    if seconds > 1e11:  # epoch milliseconds
        return max(0.0, seconds / 1000 - moment)
    if seconds > 1e9:  # epoch seconds
        return max(0.0, seconds - moment)
    return seconds
