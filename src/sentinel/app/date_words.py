"""The dates of a check-in message, resolved by code (spec section 11.3, v2.3.0; WP14).

The application's reader asks the model for the calendar date each date phrase names and for the
phrase itself, e.g. {"day": "2026-11-16", "words": "wraca w poniedziałek 16 listopada"}; this
module reads the phrase (Polish and English) and settles the date. What the words fix (a weekday,
a day and month, "jutro", "Wigilia", "do końca tygodnia") gives the candidate dates in the
direction of the phrase's role; the model's date is kept if it is one of them, the only candidate
replaces it, and a weekday that contradicts its date ("poniedziałek 17 listopada") becomes a
question, as does a day that is not a working day where a person comes back or a task starts or
finishes. The words of a phrase must all be date words (`VOCABULARY`), so that a phrase cannot
carry a reason for an absence into the answer the cache keeps (invariant 7).
"""

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from sentinel.app.calendar import WorkCalendar

Role = Literal["since", "until", "back", "done", "start"]
Problem = Literal["mismatch", "non_working", "ambiguous"]
Tense = Literal["past", "future"]
FUTURE: frozenset[Role] = frozenset({"until", "back"})
PAST: frozenset[Role] = frozenset({"done", "start"})
WEEK = 7


def plain(word: str) -> str:
    """A word as the vocabulary holds it: lower case, without Polish diacritics."""
    word = word.casefold().replace("ł", "l")
    return "".join(c for c in unicodedata.normalize("NFKD", word) if not unicodedata.combining(c))


def _forms(groups: Iterable[tuple[int, str]]) -> dict[str, int]:
    return {plain(form): value for value, forms in groups for form in forms.split()}


def word_set(text: str) -> set[str]:
    """The plain forms of the words of `text`."""
    return {plain(word) for word in text.split()}


WEEKDAYS = _forms(
    (
        (0, "poniedziałek poniedziałku poniedziałkiem pon monday mon"),
        (1, "wtorek wtorku wtorkiem wt tuesday tue tues"),
        (2, "środa środy środę środzie środą śr wednesday wed"),
        (3, "czwartek czwartku czwartkiem czw thursday thu thur thurs"),
        (4, "piątek piątku piątkiem pt friday fri"),
        (5, "sobota soboty sobotę sobocie sobotą sob saturday sat"),
        (6, "niedziela niedzieli niedzielę niedzielą niedz ndz sunday sun"),
    )
)
MONTHS = _forms(
    (
        (1, "styczeń stycznia styczniu sty january jan"),
        (2, "luty lutego lutym lut february feb"),
        (3, "marzec marca marcu mar march"),
        (4, "kwiecień kwietnia kwietniu kwi april apr"),
        (5, "maj maja maju may"),
        (6, "czerwiec czerwca czerwcu cze june jun"),
        (7, "lipiec lipca lipcu lip july jul"),
        (8, "sierpień sierpnia sierpniu august aug"),  # not "sie": "się" without diacritics
        (9, "wrzesień września wrześniu wrz september sep sept"),
        (10, "październik października październiku paź october oct"),
        (11, "listopad listopada listopadzie lis november nov"),
        (12, "grudzień grudnia grudniu gru december dec"),
    )
)
SHIFTS = _forms(
    (
        (0, "dziś dzisiaj today tonight"),
        (1, "jutro jutra tomorrow"),
        (2, "pojutrze"),
        (-1, "wczoraj yesterday"),
        (-2, "przedwczoraj"),
    )
)
ORDINALS = _forms(
    (
        (1, "pierwszego pierwszy first"),
        (2, "drugiego drugi second"),
        (3, "trzeciego trzeci third"),
        (4, "czwartego czwarty"),
        (5, "piątego piąty"),
        (6, "szóstego szósty"),
        (7, "siódmego siódmy"),
        (8, "ósmego ósmy"),
        (9, "dziewiątego dziewiąty"),
        (10, "dziesiątego dziesiąty"),
        (11, "jedenastego jedenasty"),
        (12, "dwunastego dwunasty"),
        (13, "trzynastego trzynasty"),
        (14, "czternastego czternasty"),
        (15, "piętnastego piętnasty"),
        (16, "szesnastego szesnasty"),
        (17, "siedemnastego siedemnasty"),
        (18, "osiemnastego osiemnasty"),
        (19, "dziewiętnastego dziewiętnasty"),
        (20, "dwudziestego dwudziesty"),
        (30, "trzydziestego trzydziesty"),
    )
)
NEXT_WEEK = word_set("przyszły przyszłego przyszłą przyszłym przyszła przyszłej next")
THIS_WEEK = word_set(
    "ten ta tę tym tego tej najbliższy najbliższego najbliższą najbliższym this coming"
)
LAST_WEEK = word_set(
    "zeszły zeszłego zeszłą zeszłym zeszłej ostatni ostatniego ostatnią ostatnim poprzedni "
    "poprzedniego last previous"
)
UNTIL = word_set("do until till til through thru włącznie inclusive")
BACK = word_set(
    "wraca wróci wrócą wracają wrócił wróciła wróciło wrócili powrót powrotu powrotem back "
    "return returns returning returned"
)
SINCE = word_set("od from since starting")
WEEK_WORDS = word_set("tydzień tygodnia tygodniu tygodnie tygodni tygodniem week weeks")
MONTH_WORDS = word_set("miesiąc miesiąca miesiącu month")
END_WORDS = word_set("koniec końca końcu end")
# Named days: Wigilia (24 December), Christmas Day, New Year's Eve and Day, Epiphany.
HOLIDAY_WORDS = {w: (12, 24) for w in word_set("wigilia wigilii wigilię wigilią")} | {
    w: (12, 31) for w in word_set("sylwester sylwestra sylwestrze")
}
HOLIDAY_PAIRS = {
    ("boze", "narodzenie"): (12, 25),
    ("bozego", "narodzenia"): (12, 25),
    ("nowy", "rok"): (1, 1),
    ("nowego", "roku"): (1, 1),
    ("trzech", "kroli"): (1, 6),
}
# Words a phrase may hold besides those above: they carry no date and no reason.
FILLERS = word_set(
    "w we z ze na po przed o za i a oraz to the on in at of by is be will and or around "
    "about ok około koło rano rana wieczorem wieczór południe południu popołudniu "
    "dopiero już jeszcze najpóźniej najwcześniej się jest będzie będą był była było byli "
    "są ma mają nie go jej ich pracy pracuje pracować nieobecny nieobecna nieobecni obecny "
    "obecna dnia dzień dni dniu roboczy roboczych roboczego roboczym roku rok r day days "
    "working business morning evening st nd rd th "
    "skończył skończyła skończyło skończyli skończyły skończone skończony skończona "
    "skończyliśmy zakończył zakończyła zakończyło zakończony zakończona zakończone "
    "zakończyliśmy gotowy gotowa gotowe ruszył ruszyła ruszyło ruszyły ruszyliśmy zaczął "
    "zaczęła zaczęło zaczęły zaczęliśmy zaczyna rozpoczął rozpoczęła rozpoczęło started "
    "start began begun finished finish ended done completed święta świąt świętach "
    "jeden jedna jedno dwa dwie trzy cztery pięć sześć siedem osiem dziewięć dziesięć "
    "kilka one two three four five six seven eight nine ten an"
)
VOCABULARY = (
    set(WEEKDAYS)
    | set(MONTHS)
    | set(SHIFTS)
    | set(ORDINALS)
    | NEXT_WEEK
    | THIS_WEEK
    | LAST_WEEK
    | UNTIL
    | BACK
    | SINCE
    | WEEK_WORDS
    | MONTH_WORDS
    | END_WORDS
    | set(HOLIDAY_WORDS)
    | {w for pair in HOLIDAY_PAIRS for w in pair}
    | FILLERS
)
TOKEN = re.compile(
    r"(?P<iso>\d{4}-\d{1,2}-\d{1,2})|(?P<dotted>\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?)"
    r"|(?P<number>\d+)|(?P<word>[^\W\d_]+)"
)


@dataclass(frozen=True)
class Said:
    """What the words of a phrase fix about its date; `unknown` are the words outside the
    vocabulary, `keys` the words that carry a date (they must occur in the message)."""

    weekday: int | None = None
    days: tuple[int, ...] = ()  # days of the month written without a month
    dates: tuple[tuple[int, int, int | None], ...] = ()  # (day, month, year or None)
    shift: int | None = None
    week: Literal["this", "next", "last"] | None = None
    end: Literal["week", "month"] | None = None
    until: bool = False
    back: bool = False
    since: bool = False
    unknown: tuple[str, ...] = ()
    keys: tuple[str, ...] = ()

    @property
    def understood(self) -> bool:
        """Whether the words fix anything about the date."""
        return bool(
            self.weekday is not None
            or self.days
            or self.dates
            or self.shift is not None
            or self.end is not None
        )


def read_words(text: str) -> Said:
    """What a date phrase says (Polish or English), word by word."""
    weekday: int | None = None
    days: list[int] = []
    dates: list[tuple[int, int, int | None]] = []
    shift: int | None = None
    week: Literal["this", "next", "last"] | None = None
    end: Literal["week", "month"] | None = None
    until = back = since = False
    unknown: list[str] = []
    keys: list[str] = []
    tokens = [(m.lastgroup or "", m.group()) for m in TOKEN.finditer(text)]
    words = [plain(value) if kind == "word" else value for kind, value in tokens]
    numbers: list[int] = []
    month: int | None = None
    year: int | None = None
    ordinal = 0
    for i, (kind, value) in enumerate(tokens):
        word = words[i]
        if kind == "iso":
            y, m, d = (int(part) for part in value.split("-"))
            dates.append((d, m, y))
            keys.append(value)
        elif kind == "dotted":
            parts = [int(part) for part in re.split(r"[./]", value)]
            full = parts[2] + (2000 if parts[2] < 100 else 0) if len(parts) == 3 else None
            dates.append((parts[0], parts[1], full))
            keys.append(value)
        elif kind == "number":
            n = int(value)
            if 1900 < n < 2200:
                year = n
            elif 1 <= n <= 31:
                numbers.append(n)
            keys.append(value)
        elif word in WEEKDAYS:
            weekday = WEEKDAYS[word]
            keys.append(word)
        elif word in MONTHS and (numbers or ordinal or any(t == "number" for t, _ in tokens)):
            month = MONTHS[word]
            keys.append(word)
        elif word in SHIFTS:
            shift = SHIFTS[word]
            keys.append(word)
        elif word in ORDINALS:
            ordinal += ORDINALS[word]
            keys.append(word)
        elif word in HOLIDAY_WORDS:
            m, d = HOLIDAY_WORDS[word]
            dates.append((d, m, None))
            keys.append(word)
        elif i + 1 < len(words) and (word, words[i + 1]) in HOLIDAY_PAIRS:
            m, d = HOLIDAY_PAIRS[(word, words[i + 1])]
            dates.append((d, m, None))
            keys.append(word)
        elif word in WEEK_WORDS or word in MONTH_WORDS:
            after_end = i > 0 and words[i - 1] in END_WORDS
            after_end_of = (
                i > 1 and words[i - 2] in END_WORDS and words[i - 1] in NEXT_WEEK | THIS_WEEK
            )
            if after_end or after_end_of:
                end = "week" if word in WEEK_WORDS else "month"
        if kind == "word":
            if word in NEXT_WEEK:
                week = "next"
            elif word in LAST_WEEK:
                week = "last"
            elif word in THIS_WEEK and week is None:
                week = "this"
            until = until or (word in UNTIL or (word == "to" and not back))
            back = back or word in BACK
            since = since or word in SINCE
            if word not in VOCABULARY and not (i > 0 and (words[i - 1], word) in HOLIDAY_PAIRS):
                unknown.append(value)
    if ordinal:
        numbers.append(ordinal)
    if month is not None:
        dates += [(n, month, year) for n in numbers]
    else:
        days += numbers
    return Said(
        weekday=weekday,
        days=tuple(days),
        dates=tuple(dates),
        shift=shift,
        week=week,
        end=end,
        until=until and not back,
        back=back,
        since=since,
        unknown=tuple(unknown),
        keys=tuple(keys),
    )


def foreign_words(text: str) -> tuple[str, ...]:
    """The words of a phrase that are not date words (spec section 11.3, invariant 7)."""
    return read_words(text).unknown


def _meaning(word: str) -> tuple[str, int] | None:
    """What a date word stands for, whatever its form: ("weekday", 0) for "poniedziałek" and
    "poniedziałku", a month, a shift, an ordinal."""
    for kind, forms in (
        ("weekday", WEEKDAYS),
        ("month", MONTHS),
        ("shift", SHIFTS),
        ("ordinal", ORDINALS),
    ):
        if word in forms:
            return kind, forms[word]
    return None


def said_in(said: Said, message: str) -> bool:
    """Whether the words that carry the phrase's date occur in the message: numbers as written,
    date words in any of their forms ("do poniedziałku" for "poniedziałek")."""
    tokens = {
        plain(m.group()) if m.lastgroup == "word" else m.group() for m in TOKEN.finditer(message)
    }
    meanings = {_meaning(token) for token in tokens} - {None}
    return all(key in tokens or (_meaning(key) or ("", -1)) in meanings for key in said.keys)


@dataclass(frozen=True)
class Resolved:
    """A phrase's date settled by code: `day`, or a question (`problem`) with its `options`; the
    date the words name (`named`: one that is not a working day, or the date written beside a
    weekday it contradicts), the weekday they name, and whether nothing in the words could be
    checked (`unchecked`)."""

    day: date | None
    problem: Problem | None = None
    options: tuple[date, ...] = ()
    named: date | None = None
    weekday: int | None = None
    unchecked: bool = False


def _nearest_year(day: int, month: int, around: date) -> date | None:
    best: date | None = None
    for year in (around.year - 1, around.year, around.year + 1):
        try:
            value = date(year, month, day)
        except ValueError:
            continue
        if best is None or abs((value - around).days) < abs((best - around).days):
            best = value
    return best


def _monday(value: date) -> date:
    return value - timedelta(days=value.weekday())


def _weekday_dates(
    weekday: int,
    week: str | None,
    role: Role,
    report: date,
    anchor: date | None,
    tense: Tense | None = None,
) -> set[date]:
    """The dates a weekday alone can name in a phrase of `role` said on `report`: the next one
    after the report (after `anchor`, the first day away, for a return), the last one on or
    before it for a task that started or finished; for the first day away the one the tense of
    the clause gives, else either ("od poniedziałku jest na urlopie" is since the Monday past
    or from the next one); "przyszły" the one of next week, "zeszły" the one of last week."""
    if week == "next":
        return {_monday(report) + timedelta(days=WEEK + weekday)}
    if week == "last":
        return {_monday(report) - timedelta(days=WEEK - weekday)}
    ahead = (weekday - report.weekday()) % WEEK or WEEK
    after = report + timedelta(days=ahead)
    before = report - timedelta(days=(report.weekday() - weekday) % WEEK)
    if role in PAST:
        return {before}
    if role == "since":
        if week == "this" or tense == "future":
            return {after}
        return {before} if tense == "past" else {before, after}
    start = anchor if anchor is not None and anchor > report else report
    if anchor is not None and anchor > report:
        gap = (weekday - start.weekday()) % WEEK
        if role == "back" and gap == 0:
            gap = WEEK
        return {start + timedelta(days=gap)}
    return {after}


def _end_date(end: str, week: str | None, report: date) -> date:
    if end == "week":
        friday = _monday(report) + timedelta(days=4)
        if week == "next" or report.weekday() >= 5:
            friday += timedelta(days=WEEK)
        return friday
    following = date(report.year + report.month // 12, report.month % 12 + 1, 1)
    return following - timedelta(days=1)


def _days_dates(days: tuple[int, ...], role: Role, report: date) -> set[date]:
    """The date of each day of the month written without its month: in the month before, of or
    after the report, the next one after the report for a return, the last one on or before it
    for a start or a finish, the nearest for the first day away."""
    found: set[date] = set()
    firsts = [report.replace(day=1) + timedelta(days=31 * k) for k in (-1, 0, 1)]
    for d in days:
        options = []
        for first in firsts:
            try:
                options.append(date(first.year, first.month, d))
            except ValueError:
                continue
        if role in FUTURE:
            options = [o for o in options if o > report] or options
            found.add(min(options))
        elif role in PAST:
            options = [o for o in options if o <= report] or options
            found.add(max(options))
        elif options:
            found.add(min(options, key=lambda o: abs((o - report).days)))
    return found


def explicit(said: Said, role: Role, report: date) -> list[set[date]]:
    """The sets of dates the explicit words allow: the dates written (any of them), the days of
    the month, the end of a week or month, a shift ("jutro"); a weekday only checks them."""
    sets: list[set[date]] = []
    written = set()
    for d, m, y in said.dates:
        try:
            value = date(y, m, d) if y is not None else _nearest_year(d, m, report)
        except ValueError:
            value = None
        if value is not None:
            written.add(value)
    if written:
        sets.append(written)
    if said.days:
        sets.append(_days_dates(said.days, role, report))
    if said.end is not None:
        sets.append({_end_date(said.end, said.week, report)})
    if said.shift is not None:
        sets.append({report + timedelta(days=said.shift)})
    return [s for s in sets if s]


def _next_working(calendar: WorkCalendar, value: date) -> date:
    return calendar.date_of(calendar.first(value))


def _previous_working(calendar: WorkCalendar, value: date) -> date:
    return calendar.date_of(calendar.last(value))


def resolve(
    said: Said,
    given: date | None,
    role: Role,
    report: date,
    calendar: WorkCalendar,
    *,
    anchor: date | None = None,
    tense: Tense | None = None,
) -> Resolved:
    """The date of a phrase of `role` said on the date `report`, from the model's date `given`
    and what the words fix. "Jutro" as the first day away or the day of a return is the next
    working day after the report; the explicit words (a date, a day of the month, "do końca
    tygodnia", "wczoraj") must agree with each other and with a weekday they name, a weekday
    alone gives the dates of `_weekday_dates`; the model's date is kept if the words allow it,
    the only date they allow replaces it. A contradiction, and a return, a first day away, a
    start or a finish on a day that is not a working day, become questions, as do the two days a
    weekday alone can name as the first day away when the clause's `tense` does not decide."""
    if said.shift == 1 and role in ("since", "back") and not said.dates and not said.days:
        return Resolved(_next_working(calendar, report + timedelta(days=1)))
    sets = explicit(said, role, report)
    if sets:
        allowed = set.intersection(*sets)
        if not allowed:  # e.g. "wczoraj, 5 listopada" said on 4 November
            options = {min(s, key=lambda d: abs((d - report).days)) for s in sets}
            return Resolved(None, "mismatch", tuple(sorted(options)), weekday=said.weekday)
        if said.weekday is not None:
            matching = {d for d in allowed if d.weekday() == said.weekday}
            if not matching:  # "poniedziałek 17 listopada": 17 November is a Tuesday
                near = given if given is not None else report
                written = min(allowed, key=lambda d: abs((d - near).days))
                gap = (said.weekday - written.weekday()) % WEEK
                other = written + timedelta(days=gap if gap <= 3 else gap - WEEK)
                choices = tuple(sorted({written, other}))
                return Resolved(None, "mismatch", choices, written, said.weekday)
            allowed = matching
    elif said.weekday is not None:
        allowed = _weekday_dates(said.weekday, said.week, role, report, anchor, tense)
        if len(allowed) > 1:
            return Resolved(None, "ambiguous", tuple(sorted(allowed)), given, said.weekday)
    else:
        return Resolved(given, unchecked=True)
    if given is not None and given in allowed:
        day = given
    elif len(allowed) == 1:
        day = next(iter(allowed))
    else:
        return Resolved(None, "mismatch", tuple(sorted(allowed)), given, said.weekday)
    if role != "until" and not calendar.is_working(day):
        moved = _previous_working(calendar, day) if role == "done" else _next_working(calendar, day)
        return Resolved(None, "non_working", (moved,), day, said.weekday)
    return Resolved(day, weekday=said.weekday)


def return_after(calendar: WorkCalendar, last_day: date) -> date:
    """The return date of an absence "until" a date (spec section 11.3): absent through it, back
    on the next working day after it."""
    return calendar.date_of(calendar.last(last_day) + 1)
