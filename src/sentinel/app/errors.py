"""Errors of the application's services: a message code with its parameters, the kind that
the API maps to an HTTP status, and the issues behind it (rendered in the user's language)."""

from collections.abc import Sequence
from typing import Literal

from sentinel.app.live import Issue, LiveError

ErrorKind = Literal[
    "invalid", "not_found", "conflict", "forbidden", "limit", "too_large", "unavailable"
]


class AppError(Exception):
    """A request the services refuse, with a user-readable reason (`messages`)."""

    def __init__(
        self,
        code: str,
        kind: ErrorKind = "invalid",
        issues: Sequence[Issue] = (),
        **params: str | int | float,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.kind: ErrorKind = kind
        self.issues = tuple(issues)
        self.params = params

    @classmethod
    def of(cls, error: LiveError) -> "AppError":
        """The error of a refused operation on a live project: its first issue's message, every
        issue in the details."""
        first = error.issues[0] if error.issues else Issue("invalid_request")
        return cls(first.code, "invalid", error.issues, **first.values)
