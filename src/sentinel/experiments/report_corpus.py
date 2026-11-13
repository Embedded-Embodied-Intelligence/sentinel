"""The RQ6 corpus (WP20): synthetic Polish project reports generated from templates, each with
the list of its facts as ground truth.

A report is a weekly status report of one project: a title, the state of the work, the budget,
the risks, a decision asked for and the plan, with sentences that repeat earlier ones and
filler that an editor would remove. Its slots are filled from the project's names (people,
tasks, the project) and from seeded figures written in the forms people use: "1,5 mln zł",
"250 000 zł", "3 tys. zł", "15 %", "12,5 proc.", "16 listopada", "do 20 listopada",
"30.11.2026", "jutro", "za dwa tygodnie", "w przyszłym tygodniu", a weekday, a time. The facts
are recorded as the generator wrote them, in the canonical values of the fact guard
(`sentinel.interpret.facts`), and `check_report` confirms that the guard finds exactly them.
The corpus is synthetic; `scripts/make_rq6_corpus.py` writes it from the showcase project and
from projects named as the simulator names them (`configs/wp20_rq6_corpus.json`), and reports
a person adds by hand use the same format (`load_corpus`).
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from sentinel.interpret.facts import Fact, Names, distinct, extract, same

MONTH_GENITIVE = (
    "stycznia",
    "lutego",
    "marca",
    "kwietnia",
    "maja",
    "czerwca",
    "lipca",
    "sierpnia",
    "września",
    "października",
    "listopada",
    "grudnia",
)
WEEKDAY_ACCUSATIVE = ("poniedziałek", "wtorek", "środę", "czwartek", "piątek")
FUTURES = ("tomorrow", "weekday", "two_weeks", "next_week", "date", "end")
MEETING = ("tomorrow", "weekday", "date")  # a day with a time
PEOPLE_WORDS = {1: "1 osobę", 2: "2 osoby", 3: "3 osoby"}


@dataclass(frozen=True)
class ProjectNames:
    """The names a report may use: the project, its people and its tasks; `source` is
    "showcase" or "simulator"."""

    project: str
    people: tuple[str, ...]
    tasks: tuple[str, ...]
    source: str


@dataclass(frozen=True)
class TruthFact:
    """A fact of the ground truth: its kind and canonical value, and how it was written."""

    kind: str
    value: str
    text: str


@dataclass(frozen=True)
class Report:
    """A report of the corpus with its ground truth."""

    id: str
    source: str  # showcase, simulator, own
    project: str
    day: date  # the report's date: relative dates name days from it
    text: str
    names: Names
    facts: tuple[TruthFact, ...]


def _thousands(value: int) -> str:
    """An integer with a space between groups of three digits ("250 000")."""
    return f"{value:,}".replace(",", " ")


class _Writer:
    """Fills the templates of one report and records each fact as written."""

    def __init__(self, rng: np.random.Generator, day: date) -> None:
        self.rng = rng
        self.day = day
        self.facts: list[TruthFact] = []

    def pick[T](self, options: Sequence[T]) -> T:
        return options[int(self.rng.integers(len(options)))]

    def fact(self, kind: str, value: str, text: str) -> str:
        self.facts.append(TruthFact(kind, value, text))
        return text

    def amount(self, value: int) -> str:
        """An amount in złoty in one of the forms people write."""
        if value >= 1_000_000 and value % 100_000 == 0:
            millions = value / 1_000_000
            shown = f"{millions:.1f}".replace(".", ",").replace(",0", "")
            return self.fact("amount", f"{value} PLN", f"{shown} mln zł")
        if value % 1000 == 0 and value < 100_000 and self.rng.random() < 0.5:
            return self.fact("amount", f"{value} PLN", f"{value // 1000} tys. zł")
        return self.fact("amount", f"{value} PLN", f"{_thousands(value)} zł")

    def percent(self, value: float) -> str:
        whole = float(value).is_integer()
        number = f"{int(value)}" if whole else f"{value:.1f}".replace(".", ",")
        canonical = f"{int(value)}%" if whole else f"{value:.1f}%"
        written = self.pick((f"{number} %", f"{number}%", f"{number} proc."))
        return self.fact("percent", canonical, written)

    def days(self, value: int, unit: str = "dni") -> str:
        return self.fact("number", str(value), f"{value} {unit}")

    def absolute(self, value: date, *, year: bool | None = None, until: bool = False) -> str:
        """A calendar date: "16 listopada", "16 listopada 2026 r.", "16.11.2026" or ISO."""
        style = self.pick(("words", "words_year", "dotted", "iso")) if year is None else None
        if year is True:
            style = "words_year"
        if year is False:
            style = "words"
        month = MONTH_GENITIVE[value.month - 1]
        match style:
            case "words":
                text, canonical = f"{value.day} {month}", f"--{value.month:02d}-{value.day:02d}"
            case "words_year":
                text, canonical = f"{value.day} {month} {value.year} r.", value.isoformat()
            case "dotted":
                text, canonical = (
                    f"{value.day:02d}.{value.month:02d}.{value.year}",
                    value.isoformat(),
                )
            case _:
                text, canonical = value.isoformat(), value.isoformat()
        written = self.fact("date", canonical, text)
        return f"do {written}" if until else written

    def future(self, choices: Sequence[str] = FUTURES) -> str:
        """A date ahead, often in relative words."""
        choice = self.pick(choices)
        if choice == "tomorrow":
            return self.fact("date", "day:+1", "jutro")
        if choice == "weekday":
            weekday = int(self.rng.integers(5))
            word = WEEKDAY_ACCUSATIVE[weekday]
            prefix = "we" if word == "wtorek" else "w"
            return f"{prefix} " + self.fact("date", f"weekday:{weekday}", word)
        if choice == "two_weeks":
            return self.fact("date", "in:14d", "za dwa tygodnie")
        if choice == "next_week":
            return self.fact("date", "week:+1", "w przyszłym tygodniu")
        if choice == "end":
            return self.fact("date", "end:2:+0", "do końca miesiąca")
        return self.absolute(self.day + timedelta(days=int(self.rng.integers(3, 20))), year=False)


def _sentences(w: _Writer, names: ProjectNames, day: date) -> list[list[str]]:
    """The paragraphs of a report: its sections' sentences (state, budget, risks, decision and
    plan), with repetitions and filler mixed in."""
    people = list(names.people)
    tasks = list(names.tasks)
    w.rng.shuffle(people)
    w.rng.shuffle(tasks)
    p1, p2, p3 = people[0], people[1 % len(people)], people[2 % len(people)]
    t = tasks + tasks
    budget = int(w.pick((180, 240, 320, 450, 600, 1200, 1500, 2400))) * 1000
    spent_share = int(w.rng.integers(25, 75))
    spent = budget * spent_share // 100 // 1000 * 1000
    deviation = int(w.pick((4, 6, 8, 12, 15)))
    forecast = budget * (100 + deviation) // 100 // 1000 * 1000
    done_day = day - timedelta(days=int(w.rng.integers(1, 6)))
    state = [
        f"Zadanie „{t[0]}” zakończyliśmy {w.absolute(done_day, year=False)}.",
        f"Zadanie „{t[1]}” jest gotowe w {w.percent(float(w.pick((30, 45, 60, 75, 80, 90))))}.",
        f"Do końca zadania „{t[2]}” zostało {w.days(int(w.rng.integers(3, 15)))} pracy.",
        f"{p1} przejmuje zadanie „{t[3]}” {w.future()}.",
        "Ogólnie rzecz biorąc, prace idą zgodnie z planem, choć są pewne kwestie, które wymagają "
        "uwagi i które warto omówić.",
        f"Jak wspomniano wcześniej, zadanie „{t[0]}” jest już zakończone.",
    ]
    money = [
        f"Budżet projektu to {w.amount(budget)}; do tej pory wydaliśmy {w.amount(spent)}, czyli "
        f"{w.percent(float(spent_share))} budżetu.",
        f"Prognoza kosztu na koniec wynosi {w.amount(forecast)}, czyli o "
        f"{w.percent(float(deviation))} więcej niż budżet.",
        f"Na licencje potrzebujemy dodatkowo {w.amount(int(w.pick((3, 5, 8, 12))) * 1000)}.",
        f"Warto jeszcze raz podkreślić, że budżet projektu to {w.amount(budget)}.",
    ]
    delay = int(w.rng.integers(2, 8))
    soon = day + timedelta(days=int(w.rng.integers(4, 10)))
    workers = int(w.pick((1, 2, 3)))
    risks = [
        f"{p2} wraca {w.future()}, więc zadanie „{t[4]}” może się przesunąć o {w.days(delay)}.",
        f"Ryzyko: zadanie „{t[5]}” jest opóźnione o "
        f"{w.days(int(w.rng.integers(2, 5)), 'dni robocze')}.",
        f"Proponuję dodać {w.fact('number', str(workers), PEOPLE_WORDS[workers])} "
        f"do zadania „{t[4]}” "
        f"na {w.days(int(w.pick((5, 10, 15))))}; koszt to około "
        f"{w.amount(int(w.pick((9, 14, 18, 22))) * 1000)}.",
        f"Decyzję potrzebujemy {w.absolute(soon, year=False, until=True)}.",
    ]
    hour = int(w.pick((9, 10, 11, 13, 14)))
    minute = w.pick(("00", "30"))
    final = day + timedelta(days=int(w.rng.integers(20, 60)))
    when = w.future(MEETING)
    time = w.fact("date", f"time:{hour:02d}:{minute}", f"{hour}:{minute}")
    final_text = w.absolute(final, year=True if w.rng.random() < 0.3 else None)
    plan = [
        f"Odbiór projektu planujemy na {final_text}.",
        f"Spotkanie zespołu odbędzie się {when} o {time}.",
        f"Zadaniem „{t[6]}” zajmie się {p3}, a {p1} pomoże przy zadaniu „{t[7]}”.",
        "Na koniec chciałoby się dodać, że współpraca w zespole przebiega dobrze, a wszystkie "
        "osoby są zaangażowane w realizację celów projektu.",
    ]
    return [state, money, risks, plan]


def generate(
    projects: Sequence[ProjectNames], per_project: Sequence[int], seed: int
) -> list[Report]:
    """`per_project[i]` reports of project `i`, on Fridays counted back from 13 November 2026,
    from one seeded generator per report (`SeedSequence(seed).spawn`)."""
    reports: list[Report] = []
    count = sum(per_project)
    seeds = np.random.SeedSequence(seed).spawn(count)
    index = 0
    for names, n in zip(projects, per_project, strict=True):
        for k in range(n):
            day = date(2026, 11, 13) - timedelta(weeks=k)
            w = _Writer(np.random.default_rng(seeds[index]), day)
            title = f"Raport tygodniowy: {w.fact('project', names.project, names.project)}"
            stamp = f"Stan na {w.absolute(day, year=True)}"  # the date ends with "r."
            paragraphs = [title, stamp] + [" ".join(p) for p in _sentences(w, names, day)]
            text = "\n\n".join(paragraphs)
            people = tuple(names.people)
            guard_names = Names(people=people, tasks=tuple(names.tasks), projects=(names.project,))
            for fact in _mentioned(text, guard_names, day):
                if not any(t.kind == fact.kind and t.value == fact.value for t in w.facts):
                    w.facts.append(TruthFact(fact.kind, fact.value, fact.text))
            reports.append(
                Report(
                    id=f"R{index + 1:02d}",
                    source=names.source,
                    project=names.project,
                    day=day,
                    text=text,
                    names=guard_names,
                    facts=_unique(w.facts),
                )
            )
            index += 1
    return reports


def _mentioned(text: str, names: Names, day: date) -> list[Fact]:
    """The people and tasks a report names (the templates name them in quotes or as subjects;
    they are facts like the figures)."""
    return [f for f in extract(text, names=names, when=day) if f.kind in ("person", "task")]


def _unique(facts: Sequence[TruthFact]) -> tuple[TruthFact, ...]:
    seen: list[TruthFact] = []
    for fact in facts:
        if not any(f.kind == fact.kind and f.value == fact.value for f in seen):
            seen.append(fact)
    return tuple(seen)


def check_report(report: Report) -> list[str]:
    """The differences between a report's ground truth and the facts the guard finds in it:
    empty when the guard sees exactly the recorded facts (each once, by meaning)."""
    found = distinct(extract(report.text, names=report.names, when=report.day))
    issues = []
    for group in found:
        fact = group.fact
        recorded = any(t.kind == fact.kind and t.value == fact.value for t in report.facts)
        if not recorded and not any(
            t.kind == fact.kind and same(fact, _as_fact(t, report)) for t in report.facts
        ):
            issues.append(f"{report.id}: found {fact.kind} {fact.value} ({fact.text!r})")
    for truth in report.facts:
        if not any(
            g.fact.kind == truth.kind and same(g.fact, _as_fact(truth, report)) for g in found
        ):
            issues.append(f"{report.id}: missed {truth.kind} {truth.value} ({truth.text!r})")
    return issues


def _as_fact(truth: TruthFact, report: Report) -> Fact:
    """A ground-truth fact as the guard reads its written form in the report."""
    (fact, *_) = extract(truth.text, names=report.names, when=report.day) or [
        Fact(truth.kind, truth.value, truth.text, 0, len(truth.text))  # type: ignore[arg-type]
    ]
    return fact


def to_json(reports: Sequence[Report]) -> list[dict[str, Any]]:
    return [
        {
            "id": r.id,
            "source": r.source,
            "project": r.project,
            "day": r.day.isoformat(),
            "people": list(r.names.people),
            "tasks": list(r.names.tasks),
            "projects": list(r.names.projects),
            "text": r.text,
            "facts": [{"kind": f.kind, "value": f.value, "text": f.text} for f in r.facts],
        }
        for r in reports
    ]


def from_json(data: Sequence[dict[str, Any]], source: str | None = None) -> list[Report]:
    return [
        Report(
            id=str(item["id"]),
            source=source or str(item.get("source", "own")),
            project=str(item.get("project", "")),
            day=date.fromisoformat(str(item["day"])),
            text=str(item["text"]),
            names=Names(
                people=tuple(item.get("people", ())),
                tasks=tuple(item.get("tasks", ())),
                projects=tuple(item.get("projects", ())),
            ),
            facts=tuple(TruthFact(**fact) for fact in item.get("facts", ())),
        )
        for item in data
    ]


def load_corpus(path: Path, source: str | None = None) -> list[Report]:
    """The reports of a corpus file (a JSON list in the format of `to_json`)."""
    return from_json(json.loads(path.read_text(encoding="utf-8")), source)


def write_corpus(path: Path, reports: Sequence[Report]) -> None:
    text = json.dumps(to_json(reports), ensure_ascii=False, indent=1) + "\n"
    path.write_text(text, encoding="utf-8")
