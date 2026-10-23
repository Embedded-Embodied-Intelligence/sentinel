"""Deterministic team messages with known events, the inputs of the event-parser study (spec
section 10.2; RQ5).

`generate` writes one English message of the context's day from seeded templates, without an
LLM, so its events are the exact ground truth. A fact is an absence (the author's own or a
colleague's, the return as a weekday, "about N days", "next week" or unknown, with a personal
reason in a share of them), a work increase of a running activity ("about x % more", "twice as
long", "another d days"), a new activity in the style of D3 (the duration and crew of a real
original activity, a fresh name, the activities it follows and precedes) or noise (meeting
moves, praise, questions). A share of the messages has two or three facts. Every absence is of a
present original worker and every work increase of a running activity, so each true event is
valid in its context. `read_message` reads a message back by the templates (the round trip of
the tests and the oracle of the smoke runs).
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from sentinel.interpret.events import (
    REASONS,
    AbsenceEvent,
    Context,
    Event,
    NewActivityEvent,
    TeamMessage,
    WorkIncreaseEvent,
)
from sentinel.interpret.team import WEEKDAYS, fresh_name, next_week, next_weekday, plural
from sentinel.simulation.state import RUNNING, UNSTARTED
from sentinel.wbs.extract import normalise_name, normalise_role
from sentinel.wbs.narrate import number_words, parse_number

FactKind = Literal["absence", "work_increase", "new_activity", "noise"]
FACT_KINDS: tuple[FactKind, ...] = ("absence", "work_increase", "new_activity", "noise")
ReturnForm = Literal["weekday", "days", "next_week", "unknown"]
RETURN_FORMS: tuple[ReturnForm, ...] = ("weekday", "days", "next_week", "unknown")
PERCENTS = (20, 30, 40, 50, 60, 80)  # "about x % more": F in [1.2, 1.8] as D2's U[1.2, 2.0]
WORK_FORMS = ("percent", "twice", "extra")

GREETINGS = ("Hi all.", "Hi team.", "Quick update.", "Morning everyone.")
_ABSENCE_SELF = (
    "I can't come in today{because}.",
    "I'm out from today{because}.",
    "I won't be able to work today{because}.",
)
_ABSENCE_OTHER = (
    "{w} is out from today{because}.",
    "{w} can't come in today{because}.",
    "{w} will be away starting today{because}.",
)
_BECAUSE = ("", " because of {reason}", " ({reason})")
_RETURN_SELF: dict[ReturnForm, tuple[str, ...]] = {
    "weekday": ("I should be back on {day}.", "I'll be back on {day}."),
    "days": ("I'll be out for about {n} days.", "It will take about {n} days."),
    "next_week": ("I'll be back next week.", "See you next week."),
    "unknown": ("I don't know yet when I'll be back.", "No return date yet."),
}
_RETURN_OTHER: dict[ReturnForm, tuple[str, ...]] = {
    "weekday": ("{w} should be back on {day}.", "Back on {day}."),
    "days": ("{w} will be out for about {n} days.", "Expect about {n} days."),
    "next_week": ("{w} returns next week.", "Back next week."),
    "unknown": ("We don't know yet when {w} will be back.", "No return date yet."),
}
_WORK: dict[str, tuple[str, ...]] = {
    "percent": (
        "{a} turned out bigger than planned: about {x} % more work is left.",
        "The remaining work on {a} grew by about {x} %.",
    ),
    "twice": (
        "The rest of {a} will take twice as long as we thought.",
        "{a} needs twice the remaining effort.",
    ),
    "extra": ("{a} needs another {n} {days}.", "We found more work in {a}: another {n} {days}."),
}
_NEW = (
    "We need a new task {name}: {n} {days} with {crew}.",
    "Please add {name}, {n} working {days} for {crew}.",
    "New work came in: {name} takes {n} {days} and needs {crew}.",
)
_START = ("It can start after {a}", "It follows {a}")
_START_FIRST = "It can start right away"
_END = ("must be done before {b}", "has to be finished before {b}")
_END_LAST = "must be done before the release"
_NOISE = (
    "The stand-up moves to {time} on {day}.",
    "Great work on {a}, everyone!",
    "Does anyone know where the staging credentials are kept?",
    "Reminder: the retrospective is on {day} at {time}.",
    "Could someone review my pull request for {a}?",
    "Thanks for the quick fix yesterday!",
    "Pizza for lunch on {day}, who is in?",
    "The demo for the client went well.",
)
_TIMES = ("9:30", "10:00", "11:15", "2 pm", "3:30 pm")


class MessageSettings(BaseModel):
    """Shares of messages with two or three facts, of absences with a reason, of messages that
    open with a greeting, and of numbers written as words."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    multi_fact_share: float = Field(default=0.2, ge=0, le=1)
    reason_share: float = Field(default=0.5, ge=0, le=1)
    greeting_share: float = Field(default=1 / 3, ge=0, le=1)
    words_share: float = Field(default=0.5, ge=0, le=1)


@dataclass(frozen=True)
class Generated:
    """A message with its true events (in message order), its facts in order (noise included)
    and the reasons it states."""

    message: TeamMessage
    events: tuple[Event, ...]
    facts: tuple[FactKind, ...]
    reasons: tuple[str, ...]


class _Writer:
    """Draws the facts of one message from the context with one random stream."""

    def __init__(self, context: Context, rng: np.random.Generator, settings: MessageSettings):
        self.context = context
        self.rng = rng
        self.settings = settings
        observation = context.observation
        self.present = [m.worker for m in context.roster if observation.present[m.worker]]
        self.running = [j for j in context.names if observation.status[j] == RUNNING]
        self.templates = [
            a for a in observation.instance.activities[1:-1] if a.duration > 0 and any(a.demands)
        ]
        self.used_workers: set[int] = set()
        self.used_activities: set[int] = set()
        self.new_names: list[str] = []

    def pick[T](self, options: Sequence[T]) -> T:
        return options[int(self.rng.integers(len(options)))]

    def number(self, n: int) -> str:
        words = self.rng.random() < self.settings.words_share
        return number_words(n) if words and n < 100 else str(n)

    def quoted(self, j: int) -> str:
        return f'"{self.context.names[j]}"'

    def kinds(self) -> list[FactKind]:
        count = 1
        if self.rng.random() < self.settings.multi_fact_share:
            count = int(self.rng.integers(2, 4))
        kinds: list[FactKind] = []
        workers, running = len(self.present), len(self.running)
        for _ in range(count):
            options = [
                kind
                for kind in FACT_KINDS
                if (kind != "absence" or workers > 1)
                and (kind != "work_increase" or running > 0)
                and (kind != "new_activity" or bool(self.templates))
            ]
            kind = self.pick(options)
            workers -= kind == "absence"
            running -= kind == "work_increase"
            kinds.append(kind)
        return kinds

    def absence(self, author: int | None) -> tuple[str, AbsenceEvent, str | None]:
        """An absence sentence pair; `author` is the absent author (self form) or None."""
        t = self.context.day
        if author is None:
            worker = self.pick([w for w in self.present if w not in self.used_workers])
        else:
            worker = author
        self.used_workers.add(worker)
        form: ReturnForm = self.pick(RETURN_FORMS)
        values: dict[str, str] = {"w": self.context.members[worker].name}
        if form == "weekday":
            first = t + int(self.rng.integers(1, 5))
            values["day"] = WEEKDAYS[first % 5]
            back: int | None = first
        elif form == "days":
            n = int(self.rng.integers(2, 11))
            back = t + n
            values["n"] = self.number(n)
        elif form == "next_week":
            back = next_week(t)
        else:
            back = None
        reason = self.pick(REASONS) if self.rng.random() < self.settings.reason_share else None
        because = "" if reason is None else self.pick(_BECAUSE[1:]).format(reason=reason)
        openings = _ABSENCE_SELF if author is not None else _ABSENCE_OTHER
        returns = _RETURN_SELF if author is not None else _RETURN_OTHER
        opening = self.pick(openings).format(because=because, **values)
        text = f"{opening} {self.pick(returns[form]).format(**values)}"
        return text, AbsenceEvent(type="absence", worker=worker, return_day=back), reason

    def work_increase(self) -> tuple[str, WorkIncreaseEvent]:
        j = self.pick([a for a in self.running if a not in self.used_activities])
        self.used_activities.add(j)
        form = self.pick(WORK_FORMS)
        values = {"a": self.quoted(j)}
        if form == "percent":
            x = self.pick(PERCENTS)
            factor = round(1 + x / 100, 2)
            values["x"] = str(x)
        elif form == "twice":
            factor = 2.0
        else:
            d = int(self.rng.integers(1, 6))
            left = self.context.remaining[j]
            factor = round((left + d) / left, 2)
            values |= {"n": self.number(d), "days": "day" if d == 1 else "days"}
        text = self.pick(_WORK[form]).format(**values)
        return text, WorkIncreaseEvent(type="work_increase", activity=j, factor=factor)

    def new_activity(self) -> tuple[str, NewActivityEvent]:
        """A D3-style activity: a real original activity's duration and crew, a fresh name, a
        successor among the unstarted real activities (the sink in a quarter of the messages or
        if none is left) and a valid predecessor (the source in a quarter of the messages)."""
        context = self.context
        observation = context.observation
        template = self.pick(self.templates)  # a crew to name, as every PSPLIB activity has
        name = fresh_name(template.demands, [*context.names.values(), *self.new_names], self.rng)
        self.new_names.append(name)
        unstarted = [j for j in context.names if observation.status[j] == UNSTARTED]
        before = None if not unstarted or self.rng.random() < 0.25 else self.pick(unstarted)
        allowed = [j for j in context.names if context.placement_issue(j, before) is None]
        after = None if not allowed or self.rng.random() < 0.25 else self.pick(allowed)
        crew = {context.roles[k]: n for k, n in enumerate(template.demands) if n > 0}
        n = template.duration
        parts = [f"{self.number(r)} {plural(role, r)}" for role, r in crew.items()]
        crew_text = parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"
        definition = self.pick(_NEW).format(
            name=f'"{name}"', n=self.number(n), days="day" if n == 1 else "days", crew=crew_text
        )
        start = _START_FIRST if after is None else self.pick(_START).format(a=self.quoted(after))
        end = _END_LAST if before is None else self.pick(_END).format(b=self.quoted(before))
        event = NewActivityEvent(
            type="new_activity", name=name, duration=n, crew=crew, after=after, before=before
        )
        return f"{definition} {start} and {end}.", event

    def noise(self) -> str:
        template = self.pick(_NOISE)
        return template.format(
            time=self.pick(_TIMES),
            day=self.pick(WEEKDAYS),
            a=self.quoted(self.pick(list(self.context.names))),
        )


def generate(context: Context, rng: np.random.Generator, settings: MessageSettings) -> Generated:
    """One message of the context's day with its true events (see the module docstring). The
    author of a message with one absence is the absent worker in half of them (self form);
    otherwise it is a present original worker that the message does not report absent."""
    writer = _Writer(context, rng, settings)
    kinds = writer.kinds()
    author: int | None = None
    if kinds == ["absence"] and rng.random() < 0.5:
        author = writer.pick(writer.present)
    sentences: list[str] = []
    events: list[Event] = []
    reasons: list[str] = []
    if rng.random() < settings.greeting_share:
        sentences.append(writer.pick(GREETINGS))
    for kind in kinds:
        if kind == "absence":
            text, absence, reason = writer.absence(author)
            sentences.append(text)
            events.append(absence)
            if reason is not None:
                reasons.append(reason)
        elif kind == "work_increase":
            text, increase = writer.work_increase()
            sentences.append(text)
            events.append(increase)
        elif kind == "new_activity":
            text, new = writer.new_activity()
            sentences.append(text)
            events.append(new)
        else:
            sentences.append(writer.noise())
    if author is None:
        author = writer.pick([w for w in writer.present if w not in writer.used_workers])
    message = TeamMessage(day=context.day, author=author, text=" ".join(sentences))
    return Generated(message, tuple(events), tuple(kinds), tuple(reasons))


_PLACEHOLDERS = {
    "w": r"(?P<w>[A-Z][a-z]+ [A-Z]\.)",
    "a": r'"(?P<a>[^"]+)"',
    "b": r'"(?P<b>[^"]+)"',
    "name": r'"(?P<name>[^"]+)"',
    "n": r"(?P<n>\d+|[a-z]+(?:-[a-z]+)?)",
    "x": r"(?P<x>\d+)",
    "day": "(?P<day>" + "|".join(WEEKDAYS) + ")",
    "days": "days?",
    "time": r"(?P<time>\d{1,2}(?::\d{2})?(?: [ap]m)?)",
    "crew": r"(?P<crew>[A-Za-z0-9 ,-]+?)",
    "reason": "(?P<reason>" + "|".join(re.escape(r) for r in REASONS) + ")",
}


def _compile(template: str) -> re.Pattern[str]:
    parts = re.split(r"(\{[a-z]+\})", template)
    pattern = "".join(
        _PLACEHOLDERS[part[1:-1]] if part.startswith("{") else re.escape(part) for part in parts
    )
    return re.compile(pattern)


def _sentences() -> list[tuple[str, str, re.Pattern[str]]]:
    """(kind, form, pattern) of every sentence template, the absence openings with each way
    of giving a reason."""
    found: list[tuple[str, str, re.Pattern[str]]] = []
    found += [("greeting", "", _compile(g)) for g in GREETINGS]
    for kind, openings in (("self", _ABSENCE_SELF), ("other", _ABSENCE_OTHER)):
        for opening in openings:
            for because in _BECAUSE:
                found.append((f"absence_{kind}", "", _compile(opening.format_map(_Keep(because)))))
    for kind, returns in (("self", _RETURN_SELF), ("other", _RETURN_OTHER)):
        for form, templates in returns.items():
            found += [(f"return_{kind}", form, _compile(t)) for t in templates]
    for work, templates in _WORK.items():
        found += [("work", work, _compile(t)) for t in templates]
    found += [("new", "", _compile(t)) for t in _NEW]
    for start in (*_START, _START_FIRST):
        for end in (*_END, _END_LAST):
            found.append(("placement", "", _compile(f"{start} and {end}.")))
    found += [("noise", "", _compile(t)) for t in _NOISE]
    return found


class _Keep(dict[str, str]):
    """Format map that fills {because} and keeps every other placeholder."""

    def __init__(self, because: str) -> None:
        super().__init__(because=because)

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


_SENTENCES = _sentences()


def read_message(message: TeamMessage, context: Context) -> tuple[Event, ...]:
    """The events of a generated message, read by its templates: sentence by sentence from the
    left, an absence from its opening and return sentences, a new activity from its definition
    and placement sentences. Raises ValueError for text no template matches."""
    text, t = message.text, message.day
    events: list[Event] = []
    absent: int | None = None
    new: tuple[str, int, dict[str, int]] | None = None
    position = 0
    while position < len(text):
        kind, form, match = _sentence_at(text, position)
        position = match.end() + 1
        found = match.groupdict()
        if kind == "absence_self":
            absent = message.author
        elif kind == "absence_other":
            absent = context.by_member_name[found["w"]]
        elif kind.startswith("return_"):
            if absent is None or (found.get("w") and context.by_member_name[found["w"]] != absent):
                raise ValueError(f"a return sentence without its absence in {text!r}")
            back: int | None = None
            if form == "weekday":
                back = next_weekday(t, WEEKDAYS.index(found["day"]))
            elif form == "days":
                back = t + parse_number(found["n"])
            elif form == "next_week":
                back = next_week(t)
            events.append(AbsenceEvent(type="absence", worker=absent, return_day=back))
            absent = None
        elif kind == "work":
            j = context.by_name[normalise_name(found["a"])]
            if form == "percent":
                factor = round(1 + int(found["x"]) / 100, 2)
            elif form == "twice":
                factor = 2.0
            else:
                left = context.remaining[j]
                factor = round((left + parse_number(found["n"])) / left, 2)
            events.append(WorkIncreaseEvent(type="work_increase", activity=j, factor=factor))
        elif kind == "new":
            new = (found["name"], parse_number(found["n"]), _read_crew(found["crew"], context))
        elif kind == "placement":
            if new is None:
                raise ValueError(f"a placement sentence without its task in {text!r}")
            name, duration, crew = new
            after = None if found.get("a") is None else context.by_name[normalise_name(found["a"])]
            before = None if found.get("b") is None else context.by_name[normalise_name(found["b"])]
            events.append(
                NewActivityEvent(
                    type="new_activity",
                    name=name,
                    duration=duration,
                    crew=crew,
                    after=after,
                    before=before,
                )
            )
            new = None
    if absent is not None or new is not None:
        raise ValueError(f"an unfinished fact in {text!r}")
    return tuple(events)


def _sentence_at(text: str, position: int) -> tuple[str, str, re.Match[str]]:
    """The first sentence template that matches `text` at `position` up to a space or the end."""
    for kind, form, pattern in _SENTENCES:
        match = pattern.match(text, position)
        if match and (match.end() == len(text) or text[match.end()] == " "):
            return kind, form, match
    raise ValueError(f"no template matches {text[position : position + 40]!r}")


def _read_crew(text: str, context: Context) -> dict[str, int]:
    crew: dict[str, int] = {}
    for item in re.split(r", | and ", text):
        count, _, role = item.partition(" ")
        k = context.role_index[normalise_role(role)]
        crew[context.roles[k]] = parse_number(count)
    return crew
