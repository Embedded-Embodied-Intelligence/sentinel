"""Checks of what the pages show (WP9b; spec section 11.7): no internal term, no missing
translation, no raw message code, dates in words and whole percentages. WP19: a verified quote,
a citation and the model's raw answer are shown verbatim (`<!--verbatim-->`) and skipped; the
figures of a study keep their decimals (`<!--research-->`, no other rule relaxed). WP21: no em
dash and no spaced en dash used as a pause; an en dash stays only in a range of numbers or
dates ("1–5", "pt. 13 lis – pt. 20 lis")."""

import html
import re

from sentinel.app.terms import LABELS, SNAKE, WORDS  # one list of internal terms (WP12)

ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
DECIMAL_PERCENT = re.compile(r"\d[.,]\d+\s?%")
ATTRIBUTES = re.compile(r'\s(?:title|aria-label|placeholder|alt|data-tip)="([^"]*)"')
VERBATIM = re.compile(r"<!--verbatim-->.*?<!--/verbatim-->", re.S)
PAUSE = re.compile(r"—|\s–\s")
MONTHS = "sty|lut|mar|kwi|maj|cze|lip|sie|wrz|paź|lis|gru|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct"
MONTHS += "|Nov|Dec"
DAYS = "pon|wt|śr|czw|pt|sob|niedz|Mon|Tue|Wed|Thu|Fri|Sat|Sun"
RANGE_FROM = re.compile(rf"(?:\d|\b(?:{MONTHS})\.?|\}})$")  # "}": a placeholder in a catalogue
RANGE_TO = re.compile(rf"(?:(?:{DAYS})\.?\s)?[\d{{]")
RESEARCH = re.compile(r"<!--research-->.*?<!--/research-->", re.S)


def visible_text(page: str) -> str:
    """The text a person can see or hear: text nodes, chart titles and labelling attributes."""
    page = re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S | re.I)
    labels = ATTRIBUTES.findall(page)
    text = re.sub(r"<[^>]+>", " ", page)
    return html.unescape(" ".join([text, *labels]))


def pauses(text: str) -> list[str]:
    """Every em dash, and every spaced en dash that is not a range of numbers or dates."""
    found = []
    for match in PAUSE.finditer(text):
        before, after = text[: match.start()].rstrip(), text[match.end() :].lstrip()
        if match.group() != "—" and RANGE_FROM.search(before) and RANGE_TO.match(after):
            continue
        found.append(text[max(0, match.start() - 30) : match.end() + 30].strip())
    return found


def problems(page: str) -> list[str]:
    """Everything a page must not show; empty if it is clean."""
    page = VERBATIM.sub(" ", page)
    text = visible_text(page)
    plain = visible_text(RESEARCH.sub(" ", page))
    found = []
    if "⟦" in text:
        found += [f"missing text {m}" for m in re.findall(r"⟦([^⟧]*)⟧", text)]
    found += [f"internal label {m.group(0)!r}" for m in LABELS.finditer(text)]
    found += [f"internal word {m.group(0)!r}" for m in WORDS.finditer(text)]
    found += [f"raw code {m!r}" for m in SNAKE.findall(text)]
    found += [f"ISO date {m!r}" for m in ISO_DATE.findall(text)]
    found += [f"decimal percentage {m!r}" for m in DECIMAL_PERCENT.findall(plain)]
    found += [f"dash as a pause {m!r}" for m in pauses(re.sub(r"\s+", " ", text))]
    return found
