"""SUS scores of the usability test's answer cards (WP13; docs/usability/README.md).

A card is the tester's code and the ten answers (1-5) in the questionnaire's order
(docs/usability/protocol-pl.md, section 7), on the command line or one card per line of a file
(`#` starts a comment; any separator between the numbers):

    uv run python scripts/sus_score.py P1 4 2 4 1 5 2 4 2 4 1
    uv run python scripts/sus_score.py --file sus.txt

It prints the rows of the SUS table of `results-template.md` (Polish decimal comma) and, for
several cards, their mean with the minimum and maximum.
"""

import argparse
import math
import re
import sys
from collections.abc import Sequence
from pathlib import Path

ITEMS = 10


def sus_score(answers: Sequence[int]) -> float:
    """The SUS score 0-100: odd items count the answer minus 1, even items 5 minus the answer,
    the sum times 2.5 (Brooke 1996)."""
    if len(answers) != ITEMS or any(a not in (1, 2, 3, 4, 5) for a in answers):
        raise ValueError(f"a SUS card has {ITEMS} answers from 1 to 5, not {list(answers)}")
    total = sum(a - 1 if i % 2 == 0 else 5 - a for i, a in enumerate(answers))
    return total * 2.5


def read_card(text: str, position: int) -> tuple[str, list[int]]:
    """A card's code (`P<position>` if it has none) and answers, from "P1: 4 2 4 …"."""
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_-]*|\d+", text)
    code = tokens.pop(0) if tokens and not tokens[0].isdigit() else f"P{position}"
    if not all(t.isdigit() for t in tokens):
        raise ValueError(f"card {code}: the answers are numbers, not {tokens}")
    return code, [int(t) for t in tokens]


def number(value: float) -> str:
    """One decimal, half up, with a decimal comma: 66.25 reads 66,3."""
    return f"{math.floor(value * 10 + 0.5) / 10:.1f}".replace(".", ",")


def table(cards: Sequence[tuple[str, list[int]]]) -> list[str]:
    """The SUS table's rows, with the mean (min–max) row for several cards."""
    scores = [sus_score(answers) for _, answers in cards]
    lines = [
        f"| {code} | " + " | ".join(map(str, answers)) + f" | {number(score)} |"
        for (code, answers), score in zip(cards, scores, strict=True)
    ]
    if len(scores) > 1:
        mean = sum(scores) / len(scores)
        summary = f"{number(mean)} ({number(min(scores))}–{number(max(scores))})"
        lines.append("| **Średnia (min–max)** |" + " |" * ITEMS + f" {summary} |")
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SUS scores of answer cards (Brooke 1996).")
    parser.add_argument(
        "card", nargs="*", help="a code and ten answers, e.g. P1 4 2 4 1 5 2 4 2 4 1"
    )
    parser.add_argument("--file", type=Path, help="one card per line")
    args = parser.parse_args(argv)
    lines = [" ".join(args.card)] if args.card else []
    if args.file is not None:
        lines += args.file.read_text("utf-8").splitlines()
    texts = [line.split("#")[0].strip() for line in lines]
    texts = [text for text in texts if text]
    if not texts:
        parser.error("give a card or --file")
    try:
        cards = [read_card(text, i) for i, text in enumerate(texts, 1)]
        print("\n".join(table(cards)))
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
