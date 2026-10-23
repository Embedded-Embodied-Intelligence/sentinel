"""API keys and settings from the environment or `.env` (CLAUDE.md invariant 4).

A key is held as a `Secret`, whose repr, str and format never show the value; `redact`
removes it (and anything shaped like a Groq or OpenRouter key) from text before it reaches a log, a
manifest, a cache file or an exception. `.env` is parsed here at run time, so nothing else
reads it; the environment takes precedence.
"""

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import NoReturn

DEFAULT_ENV_FILE = Path(".env")
REDACTED = "[REDACTED]"
_KEY_SHAPE = re.compile(r"gsk_[A-Za-z0-9]{8,}|sk-or-[A-Za-z0-9_-]{8,}")
_ASSIGNMENT = re.compile(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*")


class Secret:
    """A secret string that never shows itself; `reveal()` returns the value."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        if not value:
            raise ValueError("a secret must not be empty")
        self._value = value

    def reveal(self) -> str:
        return self._value

    def redact(self, text: str) -> str:
        """`text` without the value and without anything shaped like a Groq or OpenRouter key."""
        return _KEY_SHAPE.sub(REDACTED, text.replace(self._value, REDACTED))

    def __repr__(self) -> str:
        return "Secret('**********')"

    def __str__(self) -> str:
        return repr(self)

    def __format__(self, spec: str) -> str:
        return repr(self)

    def __reduce__(self) -> NoReturn:
        raise TypeError("a Secret cannot be pickled")


def redact(text: str, secret: Secret | None = None) -> str:
    """`text` without `secret` (if given) and without anything shaped like a Groq or OpenRouter
    key."""
    if secret is not None:
        return secret.redact(text)
    return _KEY_SHAPE.sub(REDACTED, text)


def load_setting(
    name: str,
    *,
    env_file: Path | None = DEFAULT_ENV_FILE,
    environ: Mapping[str, str] | None = None,
) -> str | None:
    """The value of `name` from the environment, else from `env_file`; None if unset or empty."""
    value = (os.environ if environ is None else environ).get(name)
    if value:
        return value
    if env_file is None or not env_file.is_file():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _ASSIGNMENT.fullmatch(line)
        if match is None or match.group(1) != name:
            continue
        raw = match.group(2)
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
            raw = raw[1:-1]
        else:
            raw = raw.split(" #", 1)[0].strip()
        return raw or None
    return None


def load_secret(
    name: str,
    *,
    env_file: Path | None = DEFAULT_ENV_FILE,
    environ: Mapping[str, str] | None = None,
) -> Secret | None:
    """`load_setting` as a `Secret`."""
    value = load_setting(name, env_file=env_file, environ=environ)
    return None if value is None else Secret(value)
