"""Import the survey (WP20): read the Google Forms CSV export that the owner put in
data/survey/ (gitignored, never committed) and write its aggregate, counts and shares only, to
src/sentinel/evidence/data/survey.json, where Mapa granic finds it (docs/research/survey.md).

The open question's answers are never read. Quotes from them enter the summary only from a
file the owner wrote by hand (one anonymised, approved quote per line, `--quotes`).
Demographic answers given fewer than three times are merged; no cross-tabulation is made.

    uv run python scripts/import_survey.py data/survey/<export>.csv \
        [--quotes data/survey/quotes.txt]
"""

import argparse
import csv
import sys
from pathlib import Path

from sentinel.evidence import load_boundary_map
from sentinel.evidence.survey import SURVEY_PATH, aggregate, agreement, write_survey


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("export", type=Path, help="the Google Forms CSV export")
    parser.add_argument("--quotes", type=Path, help="approved anonymised quotes, one per line")
    parser.add_argument("--out", type=Path, default=SURVEY_PATH)
    args = parser.parse_args(argv)
    with args.export.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    quotes = []
    if args.quotes is not None:
        quotes = args.quotes.read_text(encoding="utf-8").splitlines()
    survey = aggregate(rows, quotes)
    if survey.n == 0 or len(survey.processes) != 12:
        print(
            f"refused: {survey.n} responses, {len(survey.processes)} of 12 processes found in "
            "the export's columns (see docs/research/survey.md)",
            file=sys.stderr,
        )
        return 1
    write_survey(args.out, survey)
    agree = agreement(survey, load_boundary_map())
    print(f"{args.out}: N = {survey.n} ({survey.n_working} working), agreement {agree} of 12")
    return 0


if __name__ == "__main__":
    sys.exit(main())
