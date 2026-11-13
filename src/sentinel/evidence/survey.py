"""The survey's answers as an aggregate (WP20; docs/research/survey.md, v3 spec section 3): the
Google Forms CSV export mapped to the twelve processes and the six criteria of the boundary map,
summarised as counts and shares only.

The summary keeps no row of the export and no free text: the open question's answers are never
read, and only quotes the owner selected, anonymised and approved by hand (a file of their own)
are added. Demographic answers are kept as counts per answer with every count below
`MIN_CELL` merged into one cell, and no cross-tabulation is made (a combination of rare
answers could identify a person). The summary lives beside the map
(`data/survey.json`) and Mapa granic shows its view when it exists.
"""

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from sentinel.evidence.load import DATA
from sentinel.evidence.model import BoundaryMap

SURVEY_PATH = DATA / "survey.json"


def plain(text: str) -> str:
    """Text in lower case without Polish diacritics ("Łatwość" -> "latwosc")."""
    text = text.casefold().replace("ł", "l")
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


MIN_CELL = 3  # no published count of a demographic answer below this
SMALL = "<3"
ANSWERS = ("ai_samodzielnie", "ai_z_czlowiekiem", "tylko_czlowiek", "dont_know")
# Distinctive words of each process and criterion in the form's labels (without diacritics).
PROCESS_WORDS = {
    "P01": "redakcja raportu",
    "P02": "wersje raportu",
    "P03": "protokolu",
    "P04": "wiadomosci statusowych",
    "P05": "prognoza dotrzymania",
    "P06": "dzialania naprawczego",
    "P07": "streszczenie budzetu",
    "P08": "zatwierdzenie przesuniecia",
    "P09": "oceny wydajnosci|ocena wydajnosci",
    "P10": "zastepstwo",
    "P11": "komunikat do zespolu",
    "P12": "decyzja strategiczna",
}
CRITERION_WORDS = {
    1: "odwracalnosc",
    2: "latwosc sprawdzenia|weryfikowalnosc",
    3: "praca jezykowa",
    4: "wplyw na ludzi",
    5: "smak|wartosci, relacje",
    6: "wrazliwosc danych",
}
MECHANISMS = {"tracked_changes": "sledzenia zmian", "explanation": "wyjasnienie ai"}
DEMOGRAPHICS = {
    "role": r"^rola|twoja rola",
    "tenure": r"staz",
    "size": r"wielkosc firmy|wielkosc organizacji",
    "ai_use": r"uzywasz ai|uzywania ai|korzystasz z ai",
}
FILTER = "czy pracujesz"
FREE_TEXT = "nie powinna byc uzywana"  # the open question: never read


class Weight(BaseModel):
    """The answers to a 1–5 question: the count per value and their mean."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    n: int
    mean: float | None
    counts: dict[str, int]


class Survey(BaseModel):
    """The survey's aggregate: respondents, per process the count of each answer, per criterion
    its weight, the two questions on Sentinel's mechanisms, the demographic counts (small ones
    merged) and the approved quotes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int = 1
    imported: date
    n: int = Field(ge=0)
    n_working: int = Field(ge=0)
    processes: dict[str, dict[str, int]]
    criteria: dict[str, Weight]
    mechanisms: dict[str, Weight]
    demographics: dict[str, dict[str, int]]
    quotes: list[str] = Field(default_factory=list)


def _label(header: str) -> str:
    """The plain text of a header, the grid's row in brackets if any ("Pytanie [Wiersz]")."""
    found = re.search(r"\[([^\]]+)\]\s*$", header)
    return plain(found[1] if found else header)


def _match[K](text: str, words: Mapping[K, str]) -> list[K]:
    return [key for key, pattern in words.items() if re.search(pattern, text)]


def answer_of(text: str) -> str | None:
    """The zone of a matrix answer ("AI samodzielnie", "AI z człowiekiem", "Tylko człowiek",
    "Nie wiem"), None when empty or unknown."""
    value = plain(text)
    if "nie wiem" in value or "don't know" in value:
        return "dont_know"
    if "samodziel" in value or value == "ai alone":
        return "ai_samodzielnie"
    if "z czlowiek" in value or "with a person" in value:
        return "ai_z_czlowiekiem"
    if "tylko czlowiek" in value or "only a person" in value:
        return "tylko_czlowiek"
    return None


def _weight(values: Iterable[str]) -> Weight:
    numbers = [int(v) for v in (x.strip() for x in values) if v.isdigit() and 1 <= int(v) <= 5]
    counts = {str(k): sum(n == k for n in numbers) for k in range(1, 6)}
    mean = round(sum(numbers) / len(numbers), 2) if numbers else None
    return Weight(n=len(numbers), mean=mean, counts=counts)


def suppressed(values: Iterable[str]) -> dict[str, int]:
    """The count of each answer, the answers given fewer than `MIN_CELL` times merged into one
    cell `SMALL` (itself shown only when it reaches `MIN_CELL`, else dropped)."""
    counts = Counter(v.strip() for v in values if v.strip())
    kept = {answer: n for answer, n in counts.items() if n >= MIN_CELL}
    small = sum(n for n in counts.values() if n < MIN_CELL)
    if small >= MIN_CELL:
        kept[SMALL] = small
    return dict(sorted(kept.items()))


def aggregate(
    rows: Sequence[Mapping[str, str]], quotes: Sequence[str] = (), today: date | None = None
) -> Survey:
    """The aggregate of the export's rows (one per response, by header); a response counts when
    it answered at least one process of the matrix."""
    headers = list(rows[0]) if rows else []
    process_columns: dict[str, str] = {}
    criterion_columns: dict[int, str] = {}
    mechanism_columns: dict[str, str] = {}
    demographic_columns: dict[str, str] = {}
    filter_column = None
    for header in headers:
        label, whole = _label(header), plain(header)
        if FREE_TEXT in whole:
            continue  # never read
        if FILTER in whole:
            filter_column = header
            continue
        found = _match(label, PROCESS_WORDS)
        criteria = _match(label, CRITERION_WORDS)
        mechanisms = _match(whole, MECHANISMS)
        demographics = [k for k, p in DEMOGRAPHICS.items() if re.search(p, whole)]
        if len(found) == 1 and "[" in header:
            process_columns[found[0]] = header
        elif len(criteria) == 1 and "[" in header:
            criterion_columns[criteria[0]] = header
        elif len(mechanisms) == 1:
            mechanism_columns[mechanisms[0]] = header
        elif len(demographics) == 1:
            demographic_columns[demographics[0]] = header
    answered = [r for r in rows if any(answer_of(r.get(c, "")) for c in process_columns.values())]
    working = [
        r for r in answered if filter_column and plain(r.get(filter_column, "")).startswith("tak")
    ]
    processes = {
        pid: {a: sum(answer_of(r.get(column, "")) == a for r in answered) for a in ANSWERS}
        for pid, column in sorted(process_columns.items())
    }
    return Survey(
        imported=today or date.today(),
        n=len(answered),
        n_working=len(working) if filter_column else len(answered),
        processes=processes,
        criteria={
            str(cid): _weight(r.get(column, "") for r in answered)
            for cid, column in sorted(criterion_columns.items())
        },
        mechanisms={
            key: _weight(r.get(column, "") for r in answered)
            for key, column in sorted(mechanism_columns.items())
        },
        demographics={
            key: suppressed(r.get(column, "") for r in answered)
            for key, column in sorted(demographic_columns.items())
        },
        quotes=[" ".join(q.split()) for q in quotes if q.strip()],
    )


def majority(counts: Mapping[str, int]) -> str | None:
    """The zone answered most often (not "don't know"), None without answers or on a tie."""
    zones = {zone: counts.get(zone, 0) for zone in ANSWERS[:3]}
    best = max(zones.values(), default=0)
    if best == 0:
        return None
    leaders = [zone for zone, n in zones.items() if n == best]
    return leaders[0] if len(leaders) == 1 else None


def agreement(survey: Survey, boundary: BoundaryMap) -> int:
    """The number of processes whose most frequent answer is the map's zone."""
    return sum(majority(survey.processes.get(p.id, {})) == p.zone for p in boundary.processes)


def load_survey(path: Path = SURVEY_PATH) -> Survey | None:
    """The survey's aggregate, None before it is imported."""
    if not path.is_file():
        return None
    return Survey.model_validate_json(path.read_text(encoding="utf-8"))


def write_survey(path: Path, survey: Survey) -> None:
    path.write_text(survey.model_dump_json(indent=1) + "\n", encoding="utf-8")
