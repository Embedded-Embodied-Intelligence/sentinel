"""The fact guard, "Strażnik faktów" (v3 spec section 7; spec section 11.9): the facts code
extracts from a text, and their check in an edited version of it.

**Facts.** Numbers written in digits (a Polish text groups thousands with a space or a full stop
and writes decimals with a comma, an English one groups with a comma and writes decimals with a
full stop), with a multiplier ("3 tys.", "1,5 mln", "2 million") and the unit that follows, if
any (days, weeks, months, hours, people, tasks, cost units); percentages ("15 %", "15 proc.",
"12.5 percent") and percentage points; amounts with a currency before or after ("1,5 mln zł",
"PLN 200 000", "€3k"); dates: ISO, "16.11.2026", "16.11", "16 listopada [2026]", "November 16",
an ordinal day ("szesnastego listopada"), a month ("w listopadzie"), the end of a week, month or
year ("do końca miesiąca"), weekdays ("w piątek"), the shifts of today ("jutro", "pojutrze"),
"za 3 dni", "za dwa tygodnie", "w przyszłym tygodniu", a year ("w 2026 r.") and a time of day;
and the names of the team's people, the tasks and the projects given, in any inflected form
(each word of the name a form of the text's word). A span of the text is one fact: a date wins
over the numbers inside it, an amount over its number.

**Check.** The facts are compared by meaning, not by writing: "1,5 mln zł" equals "1 500 000 zł",
"15 %" equals "15 procent", "16 listopada" equals "16.11.2026" (a missing year matches any),
a number without a unit equals the same number with one, an amount equals the same number
without its currency, and a relative date equals the date it names on the text's day. Each
distinct fact of the original is *unchanged* when the version has an equal fact; else *changed*
when a change of the word-level diff (`sentinel.interpret.tracked`) replaced it by a fact of the
same kind that the original lacks (both values are shown); else *omitted*. The facts of the
version that equal no fact of the original, and replace none, are *new* (possible inventions).
Numbers written as words ("piętnaście") are not facts; the guard's report says so.
"""

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Literal

from sentinel.interpret.tracked import Diff
from sentinel.interpret.tracked import diff as word_diff

FactKind = Literal["number", "percent", "amount", "date", "person", "task", "project"]
FACT_KINDS: tuple[FactKind, ...] = (
    "number",
    "percent",
    "amount",
    "date",
    "person",
    "task",
    "project",
)
FactState = Literal["unchanged", "changed", "omitted"]
Language = Literal["pl", "en"]


def plain(word: str) -> str:
    """A word lower case without Polish diacritics ("Łódź" -> "lodz")."""
    word = word.casefold().replace("ł", "l")
    return "".join(c for c in unicodedata.normalize("NFKD", word) if not unicodedata.combining(c))


def fold(text: str) -> str:
    """A text in lower case without diacritics, character for character (the patterns run on
    it, so that their offsets are the text's)."""
    out = []
    for char in text:
        low = char.lower()
        if len(low) != 1:
            low = char
        base = "l" if low == "ł" else unicodedata.normalize("NFKD", low)[:1] or low
        out.append(base)
    return "".join(out)


def _alternation(words: Iterable[str]) -> str:
    """A regex alternation of the plain forms of words, longest first (run on `fold`ed text)."""
    forms = sorted({plain(word) for word in words}, key=len, reverse=True)
    return "|".join(re.escape(w) for w in forms)


def _table(groups: Iterable[tuple[int, str]]) -> dict[str, int]:
    return {plain(form): value for value, forms in groups for form in forms.split()}


MONTHS = _table(
    (
        (1, "styczeń stycznia styczniu january jan"),
        (2, "luty lutego lutym february feb"),
        (3, "marzec marca marcu march mar"),
        (4, "kwiecień kwietnia kwietniu april apr"),
        (5, "maj maja maju may"),
        (6, "czerwiec czerwca czerwcu june jun"),
        (7, "lipiec lipca lipcu july jul"),
        (8, "sierpień sierpnia sierpniu august aug"),
        (9, "wrzesień września wrześniu september sep sept"),
        (10, "październik października październiku october oct"),
        (11, "listopad listopada listopadzie november nov"),
        (12, "grudzień grudnia grudniu december dec"),
    )
)
# Abbreviations only after a day ("16 lis"): alone they are ordinary words ("lis", "mar").
MONTH_ABBREVIATIONS = _table(
    (
        (1, "sty"),
        (2, "lut"),
        (4, "kwi"),
        (6, "cze"),
        (7, "lip"),
        (8, "sie"),
        (9, "wrz"),
        (10, "paź"),
        (11, "lis"),
        (12, "gru"),
    )
)
WEEKDAYS = _table(
    (
        (0, "poniedziałek poniedziałku poniedziałkiem monday"),
        (1, "wtorek wtorku wtorkiem tuesday"),
        (2, "środa środy środę środzie środą wednesday"),
        (3, "czwartek czwartku czwartkiem thursday"),
        (4, "piątek piątku piątkiem friday"),
        (5, "sobota soboty sobotę sobocie sobotą saturday"),
        (6, "niedziela niedzieli niedzielę niedzielą sunday"),
    )
)
SHIFTS = _table(
    (
        (0, "dziś dzisiaj today"),
        (1, "jutro jutra tomorrow"),
        (2, "pojutrze"),
        (-1, "wczoraj yesterday"),
        (-2, "przedwczoraj"),
    )
)
ORDINALS = _table(
    (
        (1, "pierwszego first"),
        (2, "drugiego second"),
        (3, "trzeciego third"),
        (4, "czwartego"),
        (5, "piątego"),
        (6, "szóstego"),
        (7, "siódmego"),
        (8, "ósmego"),
        (9, "dziewiątego"),
        (10, "dziesiątego"),
        (11, "jedenastego"),
        (12, "dwunastego"),
        (13, "trzynastego"),
        (14, "czternastego"),
        (15, "piętnastego"),
        (16, "szesnastego"),
        (17, "siedemnastego"),
        (18, "osiemnastego"),
        (19, "dziewiętnastego"),
        (20, "dwudziestego"),
        (30, "trzydziestego"),
        (31, "trzydziestego pierwszego"),
    )
)
# Small numbers in words, only inside a relative date ("za dwa tygodnie", "in three days").
COUNT_WORDS = _table(
    (
        (1, "jeden jedną jedna jednego one a"),
        (2, "dwa dwie dwóch two"),
        (3, "trzy trzech three"),
        (4, "cztery czterech four"),
        (5, "pięć pięciu five"),
        (6, "sześć sześciu six"),
        (7, "siedem siedmiu seven"),
        (8, "osiem ośmiu eight"),
        (9, "dziewięć dziewięciu nine"),
        (10, "dziesięć dziesięciu ten"),
    )
)
PERIODS = _table(
    (
        (1, "dzień dni dnia day days"),
        (7, "tydzień tygodnie tygodni tygodnia week weeks"),
        (30, "miesiąc miesiące miesięcy miesiąca month months"),
    )
)
MULTIPLIERS = _table(
    (
        (1_000, "tys. tys tysiąc tysiące tysięcy tysiąca thousand k"),
        (1_000_000, "mln milion miliona miliony milionów million millions m"),
        (1_000_000_000, "mld miliard miliarda miliardy miliardów billion billions bn"),
    )
)
CURRENCIES = {
    **{plain(w): "PLN" for w in ["zł", "złotych", "złote", "złoty", "złotego", "pln"]},
    **{plain(w): "EUR" for w in ["eur", "euro", "€"]},
    **{plain(w): "USD" for w in ["usd", "$", "dolarów", "dolary", "dollars", "dollar"]},
}
PERCENT_WORDS = ["%", "proc.", "proc", "procent", "procenta", "procentów", "procentach", "percent"]
POINT_WORDS = (
    "p.p.",
    "pp",
    "pkt proc.",
    "punktów procentowych",
    "punkty procentowe",
    "punktu procentowego",
    "percentage points",
    "percentage point",
)
UNITS = _table(
    (
        (1, "dzień dni dnia dniach osobodni osobodzień osobodnia day days person-days"),
        (2, "tydzień tygodnie tygodni tygodniach week weeks"),
        (3, "miesiąc miesiące miesięcy miesiącach month months"),
        (4, "godzina godziny godzin godz. hour hours h"),
        (5, "osoba osoby osób osobę osobami ludzi people person persons"),
        (6, "zadanie zadania zadań zadaniach task tasks"),
        (7, "jednostka jednostki jednostek unit units"),
    )
)
UNIT_NAMES = {1: "d", 2: "w", 3: "mo", 4: "h", 5: "people", 6: "tasks", 7: "units"}
WEEK_OFFSETS = _table(
    (
        (1, "przyszłym przyszłego next"),
        (0, "tym this"),
        (-1, "zeszłym zeszłego ubiegłym ubiegłego poprzednim last previous"),
    )
)
END_UNITS = _table(
    ((1, "tygodnia week"), (2, "miesiąca month"), (3, "roku year"), (4, "kwartału quarter"))
)

_NB = r"[ \u00a0\u202f]"  # a space inside a number or before its unit
_WORD_END = r"(?![\w%])"


def _grouped(language: Language) -> str:
    """A number in digits as `language` writes it: thousands groups and decimals."""
    if language == "pl":
        return rf"\d{{1,3}}(?:(?:{_NB}|\.)\d{{3}})+(?:,\d+)?(?!\d)|\d+(?:[,.]\d+)?"
    return r"\d{1,3}(?:,\d{3})+(?:\.\d+)?(?!\d)|\d+(?:\.\d+)?"


def to_decimal(text: str, language: Language) -> Decimal | None:
    """The value of a number as written in `language` ("1 500,5" -> 1500.5 in Polish)."""
    digits = re.sub(_NB, "", text)
    if language == "pl":
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", digits):
            digits = digits.replace(".", "")
        digits = digits.replace(",", ".")
    else:
        digits = digits.replace(",", "")
    try:
        return Decimal(digits)
    except InvalidOperation:
        return None


def _number(value: Decimal) -> str:
    """A decimal without exponent or trailing zeros ("1500000", "1.5")."""
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


@dataclass(frozen=True)
class Fact:
    """A fact of a text: its kind, its canonical value (what the check compares), the text as
    written and where it is. A date may also carry the calendar date it names on the text's day
    (`resolved`) and its parts (`year`, `month`, `day`; 0 when not given)."""

    kind: FactKind
    value: str
    text: str
    start: int
    end: int
    unit: str = ""
    resolved: date | None = None
    year: int = 0
    month: int = 0
    day: int = 0


def same(a: Fact, b: Fact) -> bool:
    """Whether two facts mean the same (see the module docstring)."""
    if a.kind == b.kind == "date":
        if a.resolved is not None and b.resolved is not None:
            return a.resolved == b.resolved
        if a.month and b.month and (a.day or b.day):
            years = not a.year or not b.year or a.year == b.year
            return years and a.month == b.month and a.day == b.day
        return a.value == b.value
    kinds = {a.kind, b.kind}
    if kinds == {"number"}:
        return a.value == b.value and (not a.unit or not b.unit or a.unit == b.unit)
    if kinds == {"amount", "number"}:  # an amount with its currency dropped
        number = a if a.kind == "number" else b
        amount = b if number is a else a
        return number.value == amount.value.split(" ")[0] and not number.unit
    return a.kind == b.kind and a.value == b.value


def comparable(a: Fact, b: Fact) -> bool:
    """Whether a fact can stand for another as its changed value: the same kind, or an amount
    and a number."""
    return a.kind == b.kind or {a.kind, b.kind} == {"amount", "number"}


@dataclass(frozen=True)
class Names:
    """The names the guard looks for: the team's people, the tasks and the projects."""

    people: tuple[str, ...] = ()
    tasks: tuple[str, ...] = ()
    projects: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Candidate:
    fact: Fact
    priority: int  # lower wins on an overlap of equal length


class _Patterns:
    """The compiled patterns of a language."""

    def __init__(self, language: Language) -> None:
        number = _grouped(language)
        months = _alternation(MONTHS)
        short_months = _alternation({**MONTHS, **MONTH_ABBREVIATIONS})
        mult = _alternation(MULTIPLIERS)
        currency_after = _alternation(CURRENCIES)
        currency_before = r"pln|eur|usd|\$|€"
        percent = "|".join(re.escape(w) for w in sorted(PERCENT_WORDS, key=len, reverse=True))
        points = "|".join(re.escape(w) for w in sorted(POINT_WORDS, key=len, reverse=True))
        units = _alternation(UNITS)
        self.language = language
        flags = re.IGNORECASE
        self.iso = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
        self.dotted = re.compile(
            r"(?<![\d.,])(\d{1,2})\.(\d{1,2})\.(\d{4})(?!\d)"
            rf"|(?<![\d.,])(\d{{1,2}})\.(\d{{2}})(?![\d,]|\.\d|{_NB}?(?:{mult}|{currency_after}|%))",
            flags,
        )
        year = r"(?:,?\s+(\d{4})(?:\s*r\.|\s+roku|\s+r\b)?)?"
        self.day_month = re.compile(
            rf"(?<![\d.,])(\d{{1,2}})(?:\.|-go)?\s+({short_months})\b{year}", flags
        )
        self.month_day = re.compile(
            rf"\b({months})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?!\d|[.,]\d){year}", flags
        )
        self.ordinal_month = re.compile(
            rf"\b({_alternation(ORDINALS)})\s+({months})\b{year}", flags
        )
        self.end_of = re.compile(
            r"\b(?:do|na|pod|przed|by|at|before)?\s*(?:the\s+)?"
            r"(?:koniec|końca|końcu|konca|koncu|end)(?:\s+of)?(?:\s+the)?\s+"
            r"(?:(this|next|tego|przyszłego|przyszlego)\s+)?"
            rf"({_alternation(END_UNITS)}|{months})\b{year}",
            flags,
        )
        self.month_alone = re.compile(rf"\b({months})\b{year}", flags)
        self.weekday = re.compile(rf"\b({_alternation(WEEKDAYS)})\b", flags)
        self.shift = re.compile(rf"\b({_alternation(SHIFTS)})\b", flags)
        self.within = re.compile(
            rf"\b(?:za|in|w\s+ciągu|w\s+ciagu|within)\s+(\d+|{_alternation(COUNT_WORDS)})?\s*"
            rf"({_alternation(PERIODS)})\b",
            flags,
        )
        self.week = re.compile(
            rf"\b(?:w|we|in)?\s*({_alternation(WEEK_OFFSETS)})\s+(?:tygodniu|week)\b", flags
        )
        self.year_alone = re.compile(r"(?<![\d.,])((?:19|20)\d{2})\s*(?:r\.|roku\b|r\b)", flags)
        self.time = re.compile(r"(?<![\d.,:])([01]?\d|2[0-3]):([0-5]\d)(?![\d:])")
        self.amount_before = re.compile(
            rf"(?<![\w.,])({currency_before}){_NB}?({number})(?:{_NB}?({mult})\b\.?)?{_WORD_END}",
            flags,
        )
        self.amount_after = re.compile(
            rf"(?<![\w.,])({number})(?:{_NB}?({mult})(?:\b|(?<=\.)))?{_NB}?({currency_after})"
            r"(?:(?<=\.)|(?![\w]))",
            flags,
        )
        self.percent = re.compile(
            rf"(?<![\w.,])({number}){_NB}?(?:({points})|({percent}))(?:(?<=[.%])|(?![\w]))",
            flags,
        )
        self.number = re.compile(
            rf"(?<![\w.,])({number})(?:{_NB}?({mult})(?:\b|(?<=\.)))?"
            rf"(?:{_NB}?({units})(?:(?<=\.)|\b))?{_WORD_END}",
            flags,
        )


_PATTERNS: dict[Language, _Patterns] = {}


def _patterns(language: Language) -> _Patterns:
    if language not in _PATTERNS:
        _PATTERNS[language] = _Patterns(language)
    return _PATTERNS[language]


def _year(text: str | None) -> int:
    return int(text) if text else 0


def _nearest(month: int, day: int, when: date) -> date | None:
    """The date of a day and month without a year: in the year that puts it nearest `when`."""
    options = []
    for year in (when.year - 1, when.year, when.year + 1):
        try:
            options.append(date(year, month, day))
        except ValueError:
            continue
    return min(options, key=lambda d: abs((d - when).days)) if options else None


def _date_fact(
    match: re.Match[str], year: int, month: int, day: int, when: date | None
) -> Fact | None:
    """A date of a match: a day (0: the whole month) of a month of a year (0: not given)."""
    if not 1 <= month <= 12 or not 0 <= day <= 31:
        return None
    resolved = None
    if day:
        try:
            resolved = date(year, month, day) if year else None
        except ValueError:
            return None
        if not year and when is not None:
            resolved = _nearest(month, day, when)
    if day:
        value = f"{year:04d}-{month:02d}-{day:02d}" if year else f"--{month:02d}-{day:02d}"
    else:
        value = f"{year:04d}-{month:02d}" if year else f"--{month:02d}"
    written = match.group().strip()
    start = match.start() + (len(match.group()) - len(match.group().lstrip()))
    return Fact(
        "date",
        value,
        written,
        start,
        start + len(written),
        resolved=resolved,
        year=year,
        month=month,
        day=day,
    )


def _relative(match: re.Match[str], value: str, resolved: date | None) -> Fact:
    stripped = match.group().strip()
    start = match.start() + (len(match.group()) - len(match.group().lstrip()))
    return Fact("date", value, stripped, start, start + len(stripped), resolved=resolved)


def _dates(text: str, written: str, p: _Patterns, when: date | None) -> list[_Candidate]:
    found: list[_Candidate] = []

    def add(fact: Fact | None, priority: int = 0) -> None:
        if fact is not None:
            found.append(_Candidate(fact, priority))

    for m in p.iso.finditer(text):
        add(_date_fact(m, int(m[1]), int(m[2]), int(m[3]), when))
    for m in p.dotted.finditer(text):
        if m[1]:
            add(_date_fact(m, int(m[3]), int(m[2]), int(m[1]), when))
        elif int(m[4]) >= 1:
            add(_date_fact(m, 0, int(m[5]), int(m[4]), when))
    for m in p.day_month.finditer(text):
        month = {**MONTHS, **MONTH_ABBREVIATIONS}[plain(m[2])]
        add(_date_fact(m, _year(m[3]), month, int(m[1]), when))
    for m in p.month_day.finditer(text):
        add(_date_fact(m, _year(m[3]), MONTHS[plain(m[1])], int(m[2]), when))
    for m in p.ordinal_month.finditer(text):
        add(_date_fact(m, _year(m[3]), MONTHS[plain(m[2])], ORDINALS[plain(m[1])], when))
    for m in p.end_of.finditer(text):
        target = plain(m[2])
        offset = 1 if m[1] and plain(m[1]) in ("next", "przyszlego") else 0
        if target in MONTHS:
            value = f"end:--{MONTHS[target]:02d}" + (f":{m[3]}" if m[3] else "")
        else:
            value = f"end:{END_UNITS[target]}:+{offset}"
        add(_relative(m, value, None), 1)
    for m in p.month_alone.finditer(text):
        word = plain(m[1])
        if word == "may" and p.language == "en" and written[m.start(1) : m.end(1)] != "May":
            continue
        if word in ("mar", "jan", "feb", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec"):
            continue  # abbreviations alone are other words ("mar")
        add(_date_fact(m, _year(m[2]), MONTHS[word], 0, when), 2)
    for m in p.weekday.finditer(text):
        weekday = WEEKDAYS[plain(m[1])]
        resolved = None
        if when is not None:
            resolved = when + timedelta(days=(weekday - when.weekday() - 1) % 7 + 1)
        add(_relative(m, f"weekday:{weekday}", resolved), 2)
    for m in p.shift.finditer(text):
        shift = SHIFTS[plain(m[1])]
        resolved = None if when is None else when + timedelta(days=shift)
        add(_relative(m, f"day:{shift:+d}", resolved), 2)
    for m in p.within.finditer(text):
        count = 1 if not m[1] else (int(m[1]) if m[1].isdigit() else COUNT_WORDS[plain(m[1])])
        days = count * PERIODS[plain(m[2])]
        resolved = None if when is None else when + timedelta(days=days)
        add(_relative(m, f"in:{days}d", resolved), 1)
    for m in p.week.finditer(text):
        add(_relative(m, f"week:{WEEK_OFFSETS[plain(m[1])]:+d}", None), 1)
    for m in p.year_alone.finditer(text):
        add(Fact("date", m[1], m.group().strip(), m.start(), m.end(), year=int(m[1])), 3)
    for m in p.time.finditer(text):
        add(Fact("date", f"time:{int(m[1]):02d}:{m[2]}", m[0], m.start(), m.end()), 3)
    return found


def _lookup[T](table: Mapping[str, T], word: str) -> T:
    """A word's entry in a table of plain forms, with or without its final full stop."""
    key = plain(word)
    return table[key] if key in table else table[key.rstrip(".")]


def _scaled(number: str, multiplier: str | None, language: Language) -> Decimal | None:
    value = to_decimal(number, language)
    if value is not None and multiplier:
        value *= _lookup(MULTIPLIERS, multiplier)
    return value


def _amounts(text: str, p: _Patterns) -> list[_Candidate]:
    found = []
    for m in p.amount_before.finditer(text):
        value = _scaled(m[2], m[3], p.language)
        currency = CURRENCIES.get(plain(m[1]), m[1].upper())
        if value is not None:
            fact = Fact("amount", f"{_number(value)} {currency}", m[0], m.start(), m.end())
            found.append(_Candidate(fact, 4))
    for m in p.amount_after.finditer(text):
        value = _scaled(m[1], m[2], p.language)
        if value is not None:
            fact = Fact(
                "amount", f"{_number(value)} {_lookup(CURRENCIES, m[3])}", m[0], m.start(), m.end()
            )
            found.append(_Candidate(fact, 4))
    for m in p.percent.finditer(text):
        value = to_decimal(m[1], p.language)
        if value is not None:
            kind_mark = "pp" if m[2] else "%"
            fact = Fact("percent", f"{_number(value)}{kind_mark}", m[0], m.start(), m.end())
            found.append(_Candidate(fact, 5))
    for m in p.number.finditer(text):
        value = _scaled(m[1], m[2], p.language)
        if value is None:
            continue
        unit = UNIT_NAMES[_lookup(UNITS, m[3])] if m[3] else ""
        written = m[0].rstrip()
        fact = Fact("number", _number(value), written, m.start(), m.start() + len(written), unit)
        found.append(_Candidate(fact, 6))
    return found


_NAME_WORD = re.compile(r"[^\W\d_]+(?:[-/][^\W_]+)*|\w+(?:[-/]\w+)*")


# The case endings of Polish names (without diacritics): "Anna" "Annie", "Ewa" "Ewy", "Jan"
# "Janem", "Zielińska" "Zielińskiej", "Lewandowski" "Lewandowskiego".
NAME_ENDINGS = frozenset(
    ("a", "y", "i", "e", "u", "ie", "em", "om", "owi", "ej", "ego", "emu", "iej", "iego", "iemu")
)


def word_form(name: str, word: str, *, proper: bool = False) -> bool:
    """Whether the plain text word `word` is a form of the plain name word `name`: equal, or (a
    proper name) the name, or the name without its final vowel, followed by a case ending
    ("anna" "annie", "jan" "janem", "lewandowski" "lewandowskiego"; not "jan" "jak"), or (other
    words of four letters or more) sharing a beginning of three letters and all but the last
    three of the shorter one ("integracja" "integracji", "testy" "testów")."""
    if name == word:
        return True
    if proper:
        stems = [name] + ([name[:-1]] if name[-1:] in "aeiouy" and len(name) > 2 else [])
        return any(word.startswith(s) and word[len(s) :] in NAME_ENDINGS for s in stems)
    if min(len(name), len(word)) < 4:
        return False
    common = 0
    for x, y in zip(name, word, strict=False):
        if x != y:
            break
        common += 1
    return common >= max(3, min(len(name), len(word)) - 3)


def _name_facts(text: str, names: Names) -> list[_Candidate]:
    words = [(m.start(), m.end(), m.group()) for m in _NAME_WORD.finditer(text)]
    plains = [plain(w) for _, _, w in words]
    found: list[_Candidate] = []

    def scan(name: str, parts: Sequence[str], kind: FactKind, proper: bool, priority: int) -> None:
        size = len(parts)
        for i in range(len(words) - size + 1):
            if proper and not words[i][2][:1].isupper():
                continue
            if all(word_form(parts[k], plains[i + k], proper=proper) for k in range(size)):
                start, end = words[i][0], words[i + size - 1][1]
                found.append(_Candidate(Fact(kind, name, text[start:end], start, end), priority))

    groups: tuple[tuple[FactKind, tuple[str, ...], bool], ...] = (
        ("project", names.projects, False),
        ("task", names.tasks, False),
        ("person", names.people, True),
    )
    for kind, group, proper in groups:
        for name in group:
            parts = [plain(w) for w in _NAME_WORD.findall(name)]
            if not parts:
                continue
            base = {"project": 7, "task": 8, "person": 9}[kind]
            scan(name, parts, kind, proper, base - len(parts) * 10)  # longer names first
            if kind == "person" and len(parts) > 1:
                for part in parts:  # the first name or the surname alone
                    scan(name, [part], kind, proper, base)
    return found


def extract(
    text: str, *, language: Language = "pl", names: Names | None = None, when: date | None = None
) -> list[Fact]:
    """The facts of a text in order of appearance; `when` is the text's day, for the dates that
    relative words name."""
    p = _patterns(language)
    folded = fold(text)
    candidates = _dates(folded, text, p, when) + _amounts(folded, p)
    candidates += _name_facts(text, names or Names())
    candidates.sort(key=lambda c: (c.fact.start, -(c.fact.end - c.fact.start), c.priority))
    taken: list[Fact] = []
    covered: list[tuple[int, int]] = []
    for candidate in sorted(
        candidates, key=lambda c: (-(c.fact.end - c.fact.start), c.priority, c.fact.start)
    ):
        fact = candidate.fact
        if fact.end <= fact.start:
            continue
        if any(fact.start < e and s < fact.end for s, e in covered):
            continue
        covered.append((fact.start, fact.end))
        taken.append(replace(fact, text=text[fact.start : fact.end]))
    return sorted(taken, key=lambda f: f.start)


@dataclass(frozen=True)
class Distinct:
    """A distinct fact of a text: its first writing and every place it occurs."""

    fact: Fact
    occurrences: tuple[Fact, ...]


def distinct(facts: Sequence[Fact]) -> list[Distinct]:
    """The facts grouped by meaning, in order of first appearance."""
    groups: list[list[Fact]] = []
    for fact in facts:
        for group in groups:
            if same(group[0], fact):
                group.append(fact)
                break
        else:
            groups.append([fact])
    return [Distinct(g[0], tuple(g)) for g in groups]


@dataclass(frozen=True)
class FactCheck:
    """A fact of the original and what became of it; `replaced_by` for a changed one."""

    fact: Fact
    state: FactState
    replaced_by: Fact | None = None
    count: int = 1
    mentions: tuple[Fact, ...] = ()  # every place it occurs in the original


@dataclass(frozen=True)
class Guard:
    """The check of a version: the original's facts and the version's new ones."""

    checks: tuple[FactCheck, ...]
    new: tuple[Fact, ...]
    version_facts: tuple[Fact, ...] = field(default=())

    def count(self, state: FactState) -> int:
        return sum(c.state == state for c in self.checks)

    @property
    def warning(self) -> bool:
        """Whether saving or exporting asks for a confirmation: a changed or a new fact."""
        return self.count("changed") > 0 or bool(self.new)


def check(
    original: str,
    version: str,
    *,
    language: Language = "pl",
    names: Names | None = None,
    when: date | None = None,
    changes: Diff | None = None,
) -> Guard:
    """The fact guard of `version` against `original` (see the module docstring)."""
    before = distinct(extract(original, language=language, names=names, when=when))
    after_facts = extract(version, language=language, names=names, when=when)
    after = distinct(after_facts)
    kept = [any(same(b.fact, a.fact) for a in after) for b in before]
    unmatched_after = [a for a in after if not any(same(a.fact, b.fact) for b in before)]
    paired: dict[int, Fact] = {}
    used: set[int] = set()
    found = changes if changes is not None else word_diff(original, version)
    for change in found.changes:
        a0, a1 = found.original_span(change)
        b0, b1 = found.version_span(change)
        olds = [
            i
            for i, b in enumerate(before)
            if i not in paired and any(o.start < a1 and a0 < o.end for o in b.occurrences)
        ]
        news = [
            j
            for j, a in enumerate(unmatched_after)
            if j not in used and any(o.start < b1 and b0 < o.end for o in a.occurrences)
        ]
        for i in olds:
            for j in news:
                if j not in used and comparable(before[i].fact, unmatched_after[j].fact):
                    paired[i] = unmatched_after[j].fact
                    used.add(j)
                    break
    checks = []
    for i, b in enumerate(before):
        state: FactState = "changed" if i in paired else ("unchanged" if kept[i] else "omitted")
        checks.append(FactCheck(b.fact, state, paired.get(i), len(b.occurrences), b.occurrences))
    new = tuple(a.fact for j, a in enumerate(unmatched_after) if j not in used)
    return Guard(tuple(checks), new, tuple(after_facts))


def fact_values(facts: Iterable[Fact]) -> Mapping[FactKind, list[str]]:
    """The canonical values per kind (for tables and tests)."""
    out: dict[FactKind, list[str]] = {}
    for fact in facts:
        out.setdefault(fact.kind, []).append(fact.value)
    return out
