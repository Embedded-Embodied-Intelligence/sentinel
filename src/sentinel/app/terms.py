"""The internal terms of the formal model that no page shows (spec section 11.7): the action
labels and symbols, the words of the model and of the research code, and raw codes. The pages'
tests check every page with them, and the application checks a text an AI wrote (WP12)."""

import re

# Labels and symbols of the formal model (case-sensitive: "shift dates" is plain English).
LABELS = re.compile(r"\b(NOOP|SHIFT|RESEQ|SUBST|OVERTIME|DESCOPE)\b|\bOT\(|[ΛλτδγθΔ]|p̂|P\(")
# Words of the model and of the research code (any case).
WORDS = re.compile(
    r"\b(makespans?|rollouts?|deliberat\w*|epochs?|observations?|baselines?|seeds?|pert|"
    r"cp-sat|sgs|psplib|rcpsp|noreaction|llm|monte carlo|stability|components?|tardiness|"
    r"j[36]0\d*_\d+)\b|plan\w* bazow|ziarn",
    re.IGNORECASE,
)
SNAKE = re.compile(r"\b[a-z]+_[a-z_]+\b")


def internal_terms(text: str) -> list[str]:
    """The internal labels, words and raw codes in `text`, in order; empty if it is plain."""
    found = [m.group(0) for m in LABELS.finditer(text)]
    found += [m.group(0) for m in WORDS.finditer(text)]
    found += SNAKE.findall(text)
    return found
