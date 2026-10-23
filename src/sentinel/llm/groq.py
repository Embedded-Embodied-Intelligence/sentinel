"""Groq cloud backend: OpenAI-compatible chat completions with a JSON schema (best effort; the
schema's free-form crew map rules out strict mode) or JSON mode, retries with exponential
backoff on 429, 498 and 5xx that honour `retry-after` and Groq's reset headers, and a
client-side tokens-per-minute limit (Groq API documentation, read 2026-10-23; ADR-0018).

The API key comes from `GROQ_API_KEY` in the environment or `.env` and is loaded only for a
backend call, so replaying from the cache needs no key. It never appears in a repr, a log, a
cache entry or an exception message.
"""

from collections.abc import Mapping

from sentinel.llm.core import LlmError
from sentinel.llm.http import HttpReply
from sentinel.llm.openai_compat import OpenAICompatibleClient, parse_wait

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
API_KEY_VARIABLE = "GROQ_API_KEY"  # the variable's name  # pragma: allowlist secret
# HTTP 400 codes of an answer that failed Groq's own JSON check (schema or parsing); its text
# comes back as an answer for the validator, with the code as its finish reason.
FAILED_GENERATION_CODES = frozenset({"json_validate_failed", "output_parse_failed"})
WAIT_HEADERS = ("retry-after", "x-ratelimit-reset-tokens", "x-ratelimit-reset-requests")


class GroqClient(OpenAICompatibleClient):
    """A Groq model; `tokens_per_minute` (None: no client-side limit until Groq reports one)
    spaces the requests. Groq charges the tokens a request uses, not its completion limit (a
    request of 633 prompt tokens with a limit of 7,900 completion tokens passed an 8,000 TPM
    limit on 2026-10-23)."""

    backend = "groq"
    service = "Groq"
    default_url = GROQ_URL
    key_variable = API_KEY_VARIABLE
    token_field = "max_completion_tokens"

    def _header_wait(self, headers: Mapping[str, str]) -> float | None:
        for header in WAIT_HEADERS:
            seconds = parse_wait(headers.get(header))
            if seconds is not None:
                return seconds
        return None

    def _failed_generation(self, reply: HttpReply) -> tuple[str, str] | None:
        try:
            error = reply.json().get("error") or {}
        except (LlmError, AttributeError):
            return None
        return failed_generation(error)


def failed_generation(error: object) -> tuple[str, str] | None:
    """The code and text of an answer that failed Groq's own JSON check (schema or parsing,
    `FAILED_GENERATION_CODES`), if the Groq error object `error` is that error."""
    code = error.get("code") if isinstance(error, dict) else None
    if not isinstance(error, dict) or code not in FAILED_GENERATION_CODES:
        return None
    failed = error.get("failed_generation")
    return str(code), failed if isinstance(failed, str) else ""
