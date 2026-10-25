"""Checks of what the pages show (WP9b; spec section 11.7): no internal term, no missing
translation, no raw message code, dates in words and whole percentages."""

import html
import re

# Labels and symbols of the formal model (case-sensitive: "shift dates" is plain English).
LABELS = re.compile(r"\b(NOOP|SHIFT|RESEQ|SUBST|OVERTIME|DESCOPE)\b|\bOT\(|[ΛλτδγθΔ]|p̂|P\(")
# Words of the model and of the research code (any case).
WORDS = re.compile(
    r"\b(makespans?|rollouts?|deliberat\w*|epochs?|observations?|baselines?|seeds?|pert|"
    r"cp-sat|sgs|psplib|rcpsp|noreaction|llm|monte carlo|j[36]0\d*_\d+)\b|plan\w* bazow|ziarn",
    re.IGNORECASE,
)
SNAKE = re.compile(r"\b[a-z]+_[a-z_]+\b")
ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
DECIMAL_PERCENT = re.compile(r"\d[.,]\d+\s?%")
ATTRIBUTES = re.compile(r'\s(?:title|aria-label|placeholder|alt)="([^"]*)"')


def visible_text(page: str) -> str:
    """The text a person can see or hear: text nodes, chart titles and labelling attributes."""
    page = re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S | re.I)
    labels = ATTRIBUTES.findall(page)
    text = re.sub(r"<[^>]+>", " ", page)
    return html.unescape(" ".join([text, *labels]))


def problems(page: str) -> list[str]:
    """Everything a page must not show; empty if it is clean."""
    text = visible_text(page)
    found = []
    if "⟦" in text:
        found += [f"missing text {m}" for m in re.findall(r"⟦([^⟧]*)⟧", text)]
    found += [f"internal label {m.group(0)!r}" for m in LABELS.finditer(text)]
    found += [f"internal word {m.group(0)!r}" for m in WORDS.finditer(text)]
    found += [f"raw code {m!r}" for m in SNAKE.findall(text)]
    found += [f"ISO date {m!r}" for m in ISO_DATE.findall(text)]
    found += [f"decimal percentage {m!r}" for m in DECIMAL_PERCENT.findall(text)]
    return found
