"""Versioned English prompt texts, `<name>.<version>.txt` in this package (CLAUDE.md
invariant 3). A prompt never changes once a run used it: a change is a new version, and the
text is part of every cache key through the messages."""

import functools
import hashlib
import string
from dataclasses import dataclass
from importlib import resources


@dataclass(frozen=True)
class Prompt:
    """A prompt text; `render` fills its `$name` placeholders."""

    name: str
    version: str
    text: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    def render(self, **values: str) -> str:
        return string.Template(self.text).substitute(values)


@functools.cache
def load_prompt(name: str, version: str) -> Prompt:
    """The prompt `<name>.<version>.txt`, without trailing white space."""
    resource = resources.files(__name__).joinpath(f"{name}.{version}.txt")
    if not resource.is_file():
        raise FileNotFoundError(f"no prompt {name!r} in version {version!r}")
    return Prompt(name, version, resource.read_text(encoding="utf-8").rstrip())
