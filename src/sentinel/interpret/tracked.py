"""Tracked changes between a person's text and an edited version, computed by code (v3 spec
section 7; spec section 11.9): a word-level diff, each change accepted or rejected on its own.

The texts are split into tokens: words (letters and digits, with inner hyphens, apostrophes and
decimal marks), single punctuation marks and paragraph breaks (a blank line); other white space
separates tokens and is not compared. `difflib.SequenceMatcher` (Ratcliff and Obershelp 1988,
without its junk heuristic) aligns the token sequences, and every maximal run of differing
tokens is one change; two changes separated by one short token (a punctuation mark or a word of
at most two letters) are merged, so that a rewritten phrase is one decision. `apply` builds the
text from the decisions: an accepted change takes the version's words, a rejected one keeps the
original's, and everything else is the original. The model never reports its changes: this
diff is the truth.
"""

import difflib
import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass

# A paragraph break (a blank line), a word (inner - ' . , between letters or digits), or one
# other non-space character.
_TOKEN = re.compile(r"\n[ \t]*\n\s*|[^\W_]+(?:[-'\u2019.,/][^\W_]+)*|[^\w\s]|_")
PARAGRAPH = "\n\n"
MERGE_GAP_LETTERS = 2  # a gap word of at most this many letters does not split a change


@dataclass(frozen=True)
class Token:
    """A token of a text and the white space after it, as written."""

    text: str
    space: str

    @property
    def key(self) -> str:
        """What the diff compares: the token, a paragraph break as one mark."""
        return PARAGRAPH if self.text.startswith("\n") else self.text


@dataclass(frozen=True)
class Segment:
    """A run of the merged view: equal text, or change `change` (deleted and inserted text)."""

    kind: str  # "equal" or "change"
    original: str
    version: str
    change: int | None = None


@dataclass(frozen=True)
class Change:
    """One change: the original's tokens `a0:a1` replaced by the version's `b0:b1`."""

    id: int
    a0: int
    a1: int
    b0: int
    b1: int
    deleted: str
    inserted: str


@dataclass(frozen=True)
class Diff:
    """The word-level diff of an original and a version."""

    original: tuple[Token, ...]
    version: tuple[Token, ...]
    changes: tuple[Change, ...]
    original_offsets: tuple[int, ...]
    version_offsets: tuple[int, ...]

    def segments(self) -> list[Segment]:
        """The texts as alternating equal runs and changes, in the original's order."""
        out: list[Segment] = []
        at = 0
        for change in self.changes:
            if change.a0 > at:
                same = join(self.original[at : change.a0])
                out.append(Segment("equal", same, same))
            out.append(Segment("change", change.deleted, change.inserted, change.id))
            at = change.a1
        if at < len(self.original):
            same = join(self.original[at:])
            out.append(Segment("equal", same, same))
        return out

    def apply(self, accepted: Collection[int]) -> str:
        """The text with the changes in `accepted` taken from the version, the others kept."""
        parts: list[Token] = []
        at = 0
        for change in self.changes:
            parts.extend(self.original[at : change.a0])
            if change.id in accepted:
                parts.extend(self.version[change.b0 : change.b1])
            else:
                parts.extend(self.original[change.a0 : change.a1])
            at = change.a1
        parts.extend(self.original[at:])
        return join(parts).strip()

    def original_span(self, change: Change) -> tuple[int, int]:
        """The character span of a change in the original text."""
        return _span(change.a0, change.a1, self.original_offsets, self.original)

    def version_span(self, change: Change) -> tuple[int, int]:
        """The character span of a change in the version's text."""
        return _span(change.b0, change.b1, self.version_offsets, self.version)


def tokenize(text: str) -> tuple[tuple[Token, ...], tuple[int, ...]]:
    """The tokens of a text with the white space after each, and each token's offset."""
    tokens: list[Token] = []
    offsets: list[int] = []
    matches = list(_TOKEN.finditer(text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        word = match.group()
        if word.startswith("\n"):  # a paragraph break: the break is the token, not space
            tokens.append(Token(PARAGRAPH, ""))
        else:
            tokens.append(Token(word, text[match.end() : end]))
        offsets.append(match.start())
    return tuple(tokens), tuple(offsets)


def join(tokens: Sequence[Token]) -> str:
    """Tokens back to text with their white space (none before a paragraph break)."""
    out: list[str] = []
    for token in tokens:
        if token.key == PARAGRAPH and out:
            out[-1] = out[-1].rstrip(" \t")
        out.append(token.text + token.space)
    return "".join(out)


def _span(i0: int, i1: int, offsets: Sequence[int], tokens: Sequence[Token]) -> tuple[int, int]:
    if i0 >= i1:  # an insertion point
        if i0 < len(offsets):
            return offsets[i0], offsets[i0]
        at = offsets[-1] + len(tokens[-1].text) if tokens else 0
        return at, at
    return offsets[i0], offsets[i1 - 1] + len(tokens[i1 - 1].text)


def _short(tokens: Sequence[Token]) -> bool:
    """Whether a gap between two changes is one punctuation mark or a word of two letters."""
    if len(tokens) != 1 or tokens[0].key == PARAGRAPH:
        return False
    word = tokens[0].text
    return not word.isalnum() or (word.isalpha() and len(word) <= MERGE_GAP_LETTERS)


def diff(original: str, version: str) -> Diff:
    """The word-level diff of `version` against `original` (see the module docstring)."""
    a, a_at = tokenize(original)
    b, b_at = tokenize(version)
    matcher = difflib.SequenceMatcher(None, [t.key for t in a], [t.key for t in b], autojunk=False)
    blocks = [list(op[1:]) for op in matcher.get_opcodes() if op[0] != "equal"]
    merged: list[list[int]] = []
    for block in blocks:
        if merged and _short(a[merged[-1][1] : block[0]]) and block[2] - merged[-1][3] == 1:
            merged[-1][1], merged[-1][3] = block[1], block[3]
        else:
            merged.append(block)
    changes = tuple(
        Change(
            id=index,
            a0=a0,
            a1=a1,
            b0=b0,
            b1=b1,
            deleted=join(a[a0:a1]).strip(),
            inserted=join(b[b0:b1]).strip(),
        )
        for index, (a0, a1, b0, b1) in enumerate(merged)
    )
    return Diff(a, b, changes, a_at, b_at)
