"""Write the RQ6 corpus (WP20): 30 synthetic Polish project reports with their facts, from the
showcase project of the demo and four projects named as the simulator names them (the Polish
vocabulary of `sentinel.app.names`), into configs/wp20_rq6_corpus.json. Deterministic: the same
seed writes the same file. The script checks that the fact guard finds exactly the recorded
facts in every report and stops otherwise.

    uv run python scripts/make_rq6_corpus.py [--out configs/wp20_rq6_corpus.json] [--seed 2026]
"""

import argparse
import sys
from pathlib import Path

import numpy as np

from sentinel.app import showcase
from sentinel.app.names import vocabulary
from sentinel.experiments.report_corpus import ProjectNames, check_report, generate, write_corpus

# The simulator's projects get a name of their domain (simulator projects have no name of
# their own beyond the instance); people and tasks are drawn from the simulator's words.
SIMULATOR_PROJECTS = (
    "Platforma rezerwacji wizyt",
    "System rozliczeń hurtowni",
    "Portal klienta ubezpieczyciela",
    "Aplikacja mobilna banku spółdzielczego",
)
PER_PROJECT = (10, 5, 5, 5, 5)


def simulator_names(name: str, seed: int) -> ProjectNames:
    """Six people and eight tasks drawn from the simulator's Polish vocabulary."""
    words = vocabulary("pl").simulator
    rng = np.random.default_rng(seed)
    people = tuple(str(p) for p in rng.choice(words.first_names, size=6, replace=False))
    tasks: list[str] = []
    while len(tasks) < 8:
        group = words.tasks[int(rng.integers(len(words.tasks)))]
        task = f"{rng.choice(group.verbs)} {rng.choice(group.objects)}"
        if task not in tasks:
            tasks.append(task)
    return ProjectNames(name, people, tuple(tasks), "simulator")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("configs/wp20_rq6_corpus.json"))
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    shop = showcase.definition("pl")
    projects = [
        ProjectNames(
            shop.name,
            tuple(p.name for p in shop.team),
            tuple(t.name for t in shop.tasks),
            "showcase",
        )
    ]
    projects += [simulator_names(name, args.seed + i) for i, name in enumerate(SIMULATOR_PROJECTS)]
    reports = generate(projects, PER_PROJECT, args.seed)
    issues = [issue for report in reports for issue in check_report(report)]
    if issues:
        print("\n".join(issues), file=sys.stderr)
        return 1
    write_corpus(args.out, reports)
    facts = sum(len(r.facts) for r in reports)
    words = sum(len(r.text.split()) for r in reports)
    print(f"{args.out}: {len(reports)} reports, {facts} facts, {words} words")
    return 0


if __name__ == "__main__":
    sys.exit(main())
