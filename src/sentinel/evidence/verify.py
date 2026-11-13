"""The quote check of the evidence registry: a quote is verified when it occurs in the plain
text extracted from its fetched source after this normalisation only, applied to both sides:

1. Unicode canonical composition (NFC), which changes no character, only its encoding;
2. ligatures written out (ﬁ → fi, ﬂ → fl, ﬀ → ff, ﬃ → ffi, ﬄ → ffl, ﬅ/ﬆ → st);
3. curly quotes made straight (single U+2018 to U+201B become ', double U+201C to
   U+201F become ");
4. line-break hyphenation: a soft hyphen is dropped, and a hyphen that ends a line between two
   letters either joins the word (deci-/sion → decision) or stays (human-/centric →
   human-centric); the quote may match either reading;
5. whitespace: every run of white space (line breaks, non-breaking and zero-width spaces
   included) becomes one space.

Nothing else is changed: no case folding, no dashes, no punctuation, no spelling."""

import re
import unicodedata

LIGATURES = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\ufb05": "st",
    "\ufb06": "st",
}
QUOTES = {
    "\u2018": "'",
    "\u2019": "'",
    "\u201a": "'",
    "\u201b": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u201e": '"',
    "\u201f": '"',
}
CHARACTERS = str.maketrans({**LIGATURES, **QUOTES, "\u00ad": "", "\u200b": " ", "\ufeff": " "})
LINE_BREAK_HYPHEN = re.compile(r"(\w)-[ \t]*\r?\n\s*(\w)")
WHITE_SPACE = re.compile(r"\s+")
# A sentence ends at . ! or ? followed by space and a capital letter, a digit or an opening
# quote, unless the word before is a known abbreviation.
SENTENCE_END = re.compile(r"(?<=[.!?])[\"')\]]?\s+(?=[\"'(\[]?[A-ZĄĆĘŁŃÓŚŹŻ0-9])")
ABBREVIATIONS = (
    "e.g.",
    "i.e.",
    "et al.",
    "cf.",
    "vs.",
    "No.",
    "Art.",
    "art.",
    "pp.",
    "p.",
    "Fig.",
    "ust.",
    "lit.",
    "pkt.",
    "Dz.U.",
    "Dz. U.",
    "U.S.",
    "Inc.",
    "Mr.",
    "Dr.",
)


def _characters(text: str) -> str:
    """Steps 1 to 3 and the soft hyphen of step 4."""
    return unicodedata.normalize("NFC", text).translate(CHARACTERS)


def normalise(text: str) -> str:
    """A quote (or a highlight) in the comparable form: steps 1 to 3 and 5."""
    return WHITE_SPACE.sub(" ", _characters(text)).strip()


def source_readings(text: str) -> tuple[str, str]:
    """A source text in the comparable form, with line-break hyphens joined and kept."""
    plain = _characters(text)
    joined = LINE_BREAK_HYPHEN.sub(r"\1\2", plain)
    kept = LINE_BREAK_HYPHEN.sub(r"\1-\2", plain)
    return WHITE_SPACE.sub(" ", joined), WHITE_SPACE.sub(" ", kept)


def quote_occurs(quote: str, source_text: str | tuple[str, str]) -> bool:
    """Whether the quote occurs in the source text after the documented normalisation; the
    source may be given as its two readings (`source_readings`) to check many quotes."""
    readings = source_readings(source_text) if isinstance(source_text, str) else source_text
    wanted = normalise(quote)
    return bool(wanted) and any(wanted in reading for reading in readings)


def sentence_count(text: str) -> int:
    """The number of sentences of a quote, by a punctuation rule that skips abbreviations."""
    count = 1
    flat = normalise(text)
    for match in SENTENCE_END.finditer(flat):
        before = flat[: match.start()]
        if not before.endswith(ABBREVIATIONS):
            count += 1
    return count
