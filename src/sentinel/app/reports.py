"""Raporty (v3 spec section 7; spec section 11.9): a person's report edited for audiences by the
model, the tracked changes and the fact guard computed by code, and the report stored only when
the person saves it.

A *draft* holds the text, its audiences and per audience the model's version and the changes the
person rejected; it lives in this process's memory only (at most `MAX_DRAFTS`, the oldest
forgotten first; none after a restart). The editing job stores no text in the database (the
job's result names the draft). Saving writes the draft into the session's reports; a saved
report can be opened as a draft again.
"""

import re
import threading
from collections import OrderedDict
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sentinel.app.models import Language
from sentinel.interpret.facts import Guard, Names, check
from sentinel.interpret.redaction import MAX_CHARS, REPORT_AUDIENCES, Audience
from sentinel.interpret.tracked import Diff, diff

MAX_DRAFTS = 50
MAX_TITLE = 120
POLISH_LETTERS = re.compile(r"[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]")


def text_language(text: str, fallback: Language) -> Language:
    """The language the fact guard reads a text in: Polish when it has Polish letters, else the
    page's (a decimal comma or point decides the numbers)."""
    return "pl" if POLISH_LETTERS.search(text) else fallback


@dataclass
class Version:
    """The model's version of the text for one audience (or why there is none) and the changes
    the person rejected (every other change is accepted, as the model proposed it)."""

    audience: Audience
    model_text: str | None = None
    error: str | None = None  # the code of the failure
    model: str = ""
    rejected: set[int] = field(default_factory=set)


@dataclass
class Draft:
    """A report being edited: in memory only until it is saved."""

    id: str
    session: str
    title: str
    day: date
    original: str
    audiences: tuple[Audience, ...]
    language: Language
    names: Names
    versions: dict[str, Version] = field(default_factory=dict)
    report_id: str | None = None  # the saved report it came from, or was saved as


class Drafts:
    """The drafts of the server, by session and id (the oldest forgotten first)."""

    def __init__(self, limit: int = MAX_DRAFTS) -> None:
        self.limit = limit
        self._drafts: OrderedDict[str, Draft] = OrderedDict()
        self._guard = threading.Lock()

    def put(self, draft: Draft) -> None:
        with self._guard:
            self._drafts[draft.id] = draft
            self._drafts.move_to_end(draft.id)
            while len(self._drafts) > self.limit:
                self._drafts.popitem(last=False)

    def get(self, session: str, draft_id: str) -> Draft | None:
        with self._guard:
            found = self._drafts.get(draft_id)
        return found if found is not None and found.session == session else None


@dataclass(frozen=True)
class VersionView:
    """One audience's version as the page shows it: the diff, the text with the person's
    decisions, its fact guard and that of the model's whole version."""

    audience: Audience
    diff: Diff
    text: str
    guard: Guard
    model_guard: Guard
    rejected: frozenset[int]

    @property
    def accepted(self) -> int:
        return len(self.diff.changes) - len(self.rejected)


def version_view(draft: Draft, audience: str) -> VersionView | None:
    """The version of `audience` with the person's decisions, None while it has no text."""
    version = draft.versions.get(audience)
    if version is None or version.model_text is None:
        return None
    found = diff(draft.original, version.model_text)
    rejected = frozenset(i for i in version.rejected if i < len(found.changes))
    accepted = {c.id for c in found.changes} - rejected
    text = found.apply(accepted)
    language = text_language(draft.original, draft.language)
    guard = check(draft.original, text, language=language, names=draft.names, when=draft.day)
    model_guard = check(
        draft.original,
        version.model_text,
        language=language,
        names=draft.names,
        when=draft.day,
        changes=found,
    )
    return VersionView(version.audience, found, text, guard, model_guard, rejected)


def decide(draft: Draft, audience: str, change: int | None, accept: bool) -> None:
    """Accept or reject one change (or, with `change` None, all of them)."""
    version = draft.versions.get(audience)
    if version is None or version.model_text is None:
        return
    if change is None:
        count = len(diff(draft.original, version.model_text).changes)
        version.rejected = set() if accept else set(range(count))
    elif accept:
        version.rejected.discard(change)
    else:
        version.rejected.add(change)


def validate(
    title: str, text: str, audiences: Iterable[str]
) -> tuple[str, str, tuple[Audience, ...]]:
    """The title, text and audiences of a new report, or ValueError with the code of the page's
    message."""
    text = text.strip()
    if not text:
        raise ValueError("empty")
    if len(text) > MAX_CHARS:
        raise ValueError("too_long")
    chosen = tuple(a for a in REPORT_AUDIENCES if a in set(audiences))
    if not chosen:
        raise ValueError("no_audience")
    title = " ".join(title.split())[:MAX_TITLE]
    return title, text, chosen


def payload(draft: Draft) -> dict[str, Any]:
    """What a saved report keeps: its text, day, language, audiences and per audience the
    model's version, the rejected changes and the version with the person's decisions."""
    versions: dict[str, Any] = {}
    for audience in draft.audiences:
        version = draft.versions.get(audience)
        if version is None:
            continue
        view = version_view(draft, audience)
        versions[audience] = {
            "model_text": version.model_text,
            "error": version.error,
            "model": version.model,
            "rejected": sorted(version.rejected),
            "text": None if view is None else view.text,
        }
    return {
        "day": draft.day.isoformat(),
        "language": draft.language,
        "original": draft.original,
        "audiences": list(draft.audiences),
        "versions": versions,
    }


def from_payload(
    draft_id: str, session: str, report_id: str, title: str, data: Mapping[str, Any], names: Names
) -> Draft:
    """A saved report as a draft again (its decisions as saved)."""
    audiences = tuple(a for a in REPORT_AUDIENCES if a in data.get("audiences", ()))
    draft = Draft(
        id=draft_id,
        session=session,
        title=title,
        day=date.fromisoformat(str(data["day"])),
        original=str(data["original"]),
        audiences=audiences,
        language="en" if data.get("language") == "en" else "pl",
        names=names,
        report_id=report_id,
    )
    for audience, saved in dict(data.get("versions", {})).items():
        if audience in audiences:
            draft.versions[audience] = Version(
                audience=audience,
                model_text=saved.get("model_text"),
                error=saved.get("error"),
                model=str(saved.get("model", "")),
                rejected=set(saved.get("rejected", ())),
            )
    return draft


def warnings(draft: Draft, audiences: Collection[str] | None = None) -> list[str]:
    """The audiences whose version has a changed or a new fact (a confirmation is asked)."""
    found: list[str] = []
    for audience in draft.audiences:
        if audiences is not None and audience not in audiences:
            continue
        view = version_view(draft, audience)
        if view is not None and view.guard.warning:
            found.append(audience)
    return found


def markdown(title: str, day: str, audience: str, text: str) -> str:
    """A version as a Markdown document: the title, a line with its date and audience, the
    text."""
    heading = title or audience
    return f"# {heading}\n\n_{day} · {audience}_\n\n{text.strip()}\n"


def paragraphs(text: str) -> list[str]:
    """The paragraphs of a text (split at blank lines)."""
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def session_names(people: Sequence[str], tasks: Sequence[str], projects: Sequence[str]) -> Names:
    """The names the fact guard looks for in a session's reports."""
    return Names(
        people=tuple(dict.fromkeys(people)),
        tasks=tuple(dict.fromkeys(tasks)),
        projects=tuple(dict.fromkeys(projects)),
    )
