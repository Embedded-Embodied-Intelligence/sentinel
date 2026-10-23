"""HTTP for the LLM backends with the standard library only (`urllib.request`).

A `Transport` sends one request and returns status, lower-case headers and body; any HTTP
status comes back as an `HttpReply`, while an unreachable server or a timeout raises
`TransportError`. Tests replace the transport with a scripted one, so they need no network.
"""

import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from email.message import Message as EmailMessage
from typing import Any, Protocol

from sentinel.llm.core import LlmError


class TransportError(LlmError):
    """The server could not be reached or did not answer in time."""


@dataclass(frozen=True)
class HttpReply:
    """Status, headers (lower-case names) and body of an HTTP response."""

    status: int
    body: bytes = b""
    headers: Mapping[str, str] = field(default_factory=dict)

    def json(self) -> Any:
        """The body parsed as JSON; LlmError if it is not JSON."""
        try:
            return json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LlmError(f"HTTP {self.status}: the body is not JSON ({exc})") from None

    def snippet(self, limit: int = 300) -> str:
        """The start of the body as text, for error messages."""
        text = self.body.decode("utf-8", errors="replace").strip()
        return text if len(text) <= limit else text[:limit] + "..."


class Transport(Protocol):
    """Send one HTTP request."""

    def __call__(
        self,
        method: str,
        url: str,
        *,
        body: bytes | None,
        headers: Mapping[str, str],
        timeout: float,
    ) -> HttpReply: ...


def urllib_transport(
    method: str, url: str, *, body: bytes | None, headers: Mapping[str, str], timeout: float
) -> HttpReply:
    """`Transport` with `urllib.request`; the message of a TransportError has no headers."""
    request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return HttpReply(response.status, response.read(), _lower(response.headers))
    except urllib.error.HTTPError as exc:
        with exc:
            return HttpReply(exc.code, exc.read(), _lower(exc.headers))
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        reason = getattr(exc, "reason", exc)
        raise TransportError(f"{method} {url} failed: {reason}") from None


def _lower(headers: EmailMessage | Mapping[str, str] | None) -> dict[str, str]:
    if headers is None:
        return {}
    return {name.lower(): value for name, value in headers.items()}
