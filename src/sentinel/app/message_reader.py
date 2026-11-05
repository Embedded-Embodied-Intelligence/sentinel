"""The application's reader of a check-in message (spec section 11.3, v2.3.0; WP14).

A manager's report in plain words (""Warsztat z klientem" skończył się wczoraj, ...") is read by
the language model into items of the check-in form: a task done on a date, a task in progress
with its share done or its start, an absence with its first day and its return, more work, a new
task. The model names each date as the calendar date its words give, with the words; code settles
the dates (`date_words`), matches the task words to the project's tasks tolerantly (quotes, case,
inflection) and asks where it cannot decide: somebody not in the team, words that fit several
tasks, a weekday that contradicts its date, a day that is not a working day. An answer holds no
words of the message but date words and task words checked against the project (invariant 7).
The research parser of spec section 10.2, its prompt, schema and corpus are unchanged.
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from sentinel.app.calendar import WorkCalendar, polish_holidays
from sentinel.app.date_words import (
    TOKEN,
    Resolved,
    Role,
    Tense,
    foreign_words,
    plain,
    read_words,
    resolve,
    return_after,
    said_in,
    word_set,
)
from sentinel.app.live import LiveProject, role_key
from sentinel.app.models import AbsenceReport, NewTaskReport, TaskReport, WorkIncreaseReport
from sentinel.interpret.events import WITHHELD_HINTS, Context, ParseSettings, read_answer
from sentinel.interpret.team import Member
from sentinel.llm import LlmClient, LlmResponse, Message, RequestTooLarge, load_prompt
from sentinel.llm.core import DomainIssue, ErrorDetail
from sentinel.simulation.state import RUNNING, nominal_activity, nominal_world, successor_lists
from sentinel.wbs.extract import normalise_name, normalise_role

READER_PROMPT = "checkin_message"  # prompts/checkin_message.<version>.txt
READER_REPAIR_PROMPT = "checkin_message_repair"  # its repair message with $issues
READER = ParseSettings(prompt_version="v1", max_tokens=2048, max_repair_rounds=3)
PAST_WEEKS = 2  # weeks of the calendar shown before the report's week (a start, a finish)
NEXT_WEEKS = 8  # and after it (WP14: the working days and holidays of the next 8 weeks)
WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
STATES = {"unstarted": "not started", "started": "in progress", "done": "done"}
MAX_CLAUSES = 20
CONJUNCTIONS = {
    "pl": r",?\s+(?:a|ale|oraz|natomiast)\s+",
    "en": r",\s+(?:and|but|while)\s+",
}
NAME_STEM = 3  # letters of a name a word must start with: "Ani" names Ania, "Tomka" Tomasz
# Words that name no task: joining words and the word "task" itself.
STOP_WORDS = word_set(
    "i z ze w we na do od oraz a zadanie zadania zadaniu zadaniem the and of for task"
)
ISO_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
# Words that set the tense of a clause, for a weekday alone as the first day away (WP14):
# "od poniedziałku będzie" is the next Monday, "od poniedziałku był" or "już od" the last one.
FUTURE_WORDS = word_set(
    "będzie będą bierze weźmie idzie pójdzie wyjeżdża wyjedzie zacznie zaczyna planuje "
    "zaplanował zaplanowała will going takes taking"
)
PAST_WORDS = word_set("był była było byli były już nadal wciąż ciągle was were been still since")
HINTS = {
    "clause_range": "every item and question names a clause number of the numbered list; ",
    "unknown_worker": "use a worker id of the team list, or an unknown_person question for "
    "somebody who is not in it; ",
    "unknown_task": '"task", "after" and "before" hold the words the report uses for one task of '
    "the task list; a clause about something else goes to unparsed; ",
    "day_format": 'a date is {"day": "YYYY-MM-DD", "words": ...} with a real calendar date; ',
    "phrase_words": '"words" holds only the words of the report that name the date, such as '
    '"od jutra", "do piątku" or "wraca w poniedziałek 16 listopada", never other words; ',
    "phrase_not_said": '"words" are copied from the report as written; ',
    "percent_range": '"percent" is the share done, from 0 to 100; ',
    "work_amount": 'give "extra_days" above 0 or a "factor" above 1, one of them; ',
    "duplicate": "give each person's absence once; ",
    "invalid_json": "",
}


def _words_of(text: str) -> list[str]:
    return [plain(m.group()) for m in TOKEN.finditer(text)]


def split_clauses(text: str, language: str = "en") -> tuple[str, ...]:
    """The clauses of a message, numbered from 1 in the prompt (WP12): its sentences, split
    further at a semicolon and at a conjunction that joins two statements ("..., a testy
    potrwają"), at most `MAX_CLAUSES`."""
    parts = re.split(r"(?<=[.!?;])\s+|\n+", text.strip())
    joiner = re.compile(CONJUNCTIONS.get(language, CONJUNCTIONS["en"]), re.IGNORECASE)
    clauses = [c.strip(" ,;") for part in parts for c in joiner.split(part)]
    return tuple(c for c in clauses if c)[:MAX_CLAUSES]


def clause_tense(text: str) -> Tense | None:
    """The tense of a clause if its words decide it: a future or a past marker, not both."""
    words = set(_words_of(text))
    future, past = bool(words & FUTURE_WORDS), bool(words & PAST_WORDS)
    if future != past:
        return "future" if future else "past"
    return None


def named_in(name: str, text: str) -> bool:
    """Whether a message names a person: a word of it starts as a part of the name does (its
    first three letters, so that Polish case forms match: "Ani", "Tomka"); WP12: a small model gave
    Marek's absence to Tomasz, and the review now shows such an absence as one to check."""
    words = [w.casefold() for w in re.findall(r"\w+", text)]
    stems = [part.casefold()[:NAME_STEM] for part in name.split() if len(part) >= 2]
    return any(word.startswith(stem) for stem in stems for word in words)


def work_left(project: LiveProject) -> dict[str, float]:
    """The remaining work of the running tasks in days of a full crew (one decimal), as a growth
    by a factor is shown in days on the review (spec section 10.2)."""
    observation = project.observation()
    world = nominal_world(observation)
    left = {}
    for key, j in project.activity_ids().items():
        if observation.status[j] == RUNNING:
            unit = max(1, sum(nominal_activity(observation, j)[1]))
            left[key] = max(0.1, round(world.remaining[j] / unit, 1))
    return left


# ---------------------------------------------------------------- the answer of the model


class _Answer(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Day(_Answer):
    """A date of the report: the calendar date its words name and the words."""

    day: str = Field(max_length=40)
    words: str = Field(max_length=120)


class DoneItem(_Answer):
    type: Literal["done"]
    clause: int
    task: str = Field(max_length=200)
    day: Day | None = None


class ProgressItem(_Answer):
    type: Literal["progress"]
    clause: int
    task: str = Field(max_length=200)
    percent: float | None = Field(default=None, allow_inf_nan=False)
    started: Day | None = None


class AbsenceItem(_Answer):
    type: Literal["absence"]
    clause: int
    person: int
    since: Day | None = None
    until: Day | None = None
    back: Day | None = None


class MoreWorkItem(_Answer):
    type: Literal["more_work"]
    clause: int
    task: str = Field(max_length=200)
    extra_days: float | None = Field(default=None, allow_inf_nan=False)
    factor: float | None = Field(default=None, allow_inf_nan=False)


class NewTaskItem(_Answer):
    type: Literal["new_task"]
    clause: int
    name: str = Field(max_length=200)
    duration: int
    crew: dict[str, int] = Field(default_factory=dict)
    after: str | None = Field(default=None, max_length=200)
    before: str | None = Field(default=None, max_length=200)


class UnknownPerson(_Answer):
    """Somebody away who is not in the team: only the clause and the dates, never a name."""

    kind: Literal["unknown_person"]
    clause: int
    since: Day | None = None
    until: Day | None = None
    back: Day | None = None


class ReaderAnswer(_Answer):
    """The output schema of the application's reader of a check-in message (WP14)."""

    items: tuple[DoneItem | ProgressItem | AbsenceItem | MoreWorkItem | NewTaskItem, ...] = ()
    unparsed: tuple[int, ...] = ()
    questions: tuple[UnknownPerson, ...] = ()


# ---------------------------------------------------------------- the review


class QuestionDraft(BaseModel):
    """A question for the manager about a clause: who is the absent person ("unknown_person",
    the absence's dates known), which task the words name ("ambiguous_task", the candidates'
    keys), or which date is meant ("date": a weekday that contradicts its date, a day that is
    not a working day, or a weekday that can name two days, about a person or a task).
    `absences`, `tasks` and `increases` are the reports to choose from, one per option; those
    of an unknown person have no person yet (one per first day it can be)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["unknown_person", "ambiguous_task", "date"]
    clause: int
    first_day: date | None = None
    return_date: date | None = None
    candidates: tuple[str, ...] = ()
    extra_days: float | None = None
    factor: float | None = None
    person: str | None = None
    task: str | None = None
    problem: Literal["mismatch", "non_working", "ambiguous"] | None = None
    said: date | None = None  # the date the words give, for "non_working" and "mismatch"
    weekday: int | None = None  # the weekday the words name, for "mismatch"
    absences: tuple[AbsenceReport, ...] = ()
    tasks: tuple[TaskReport, ...] = ()
    increases: tuple[WorkIncreaseReport, ...] = ()


class MessageDraft(BaseModel):
    """The reports read from a check-in message, each to confirm: absences, task reports (done,
    in progress, started), work increases, new tasks; the number of issues the last answer still
    had, the clauses turned into nothing, the questions, the absences whose person the message
    does not name (`doubtful`) and the items whose date nothing in the words could check
    (`unchecked_absences`, `unchecked_tasks`). It holds no text of the message; the page shows
    the clauses from memory."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    absences: tuple[AbsenceReport, ...] = ()
    tasks: tuple[TaskReport, ...] = ()
    increases: tuple[WorkIncreaseReport, ...] = ()
    new_tasks: tuple[NewTaskReport, ...] = ()
    issues: int = 0
    unparsed: tuple[int, ...] = ()
    questions: tuple[QuestionDraft, ...] = ()
    doubtful: tuple[int, ...] = ()
    unchecked_absences: tuple[int, ...] = ()
    unchecked_tasks: tuple[int, ...] = ()


# ---------------------------------------------------------------- the context


def word_match(a: str, b: str) -> bool:
    """Whether two plain words are forms of one word: equal, or (both of four letters or more)
    sharing a beginning of three letters and all but the last three of the shorter one, as
    Polish endings change ("bazy" "baza", "warsztacie" "warsztat", "testów" "testy")."""
    if a == b:
        return True
    if min(len(a), len(b)) < 4:
        return False
    common = 0
    for x, y in zip(a, b, strict=False):
        if x != y:
            break
        common += 1
    return common >= max(3, min(len(a), len(b)) - 3)


class _Placement(Context):
    """The research parser's context of a live project, for the checks of a new task (spec
    section 10.2): the project's role names, capacities, tasks and precedence."""

    def __init__(self, project: LiveProject) -> None:
        observation = project.observation()
        model = project.require_model()
        ids = project.activity_ids()
        nodes = project.nodes()
        self.observation = observation
        self.day = observation.day
        self.names = dict(
            sorted(
                (ids[key], node.name)
                for key, node in nodes.items()
                if project.tasks[key].state != "removed"
            )
        )
        members = [
            Member(worker=w, name=person.name, role=model.role_ids[role_key(person.role)])
            for w, person in enumerate(project.definition.team)
        ]
        self.roster = tuple(members)
        self.members = {member.worker: member for member in members}
        self.by_member_name = {member.name: member.worker for member in members}
        self.roles = model.role_names
        self.role_index = {normalise_role(role): k for k, role in enumerate(self.roles)}
        self.capacities = tuple(role.capacity for role in observation.instance.roles)
        self.sink = observation.instance.sink_id
        self.successors = successor_lists(observation)
        self.by_name = {normalise_name(name): j for j, name in self.names.items()}
        self.remaining = {}


class MessageContext:
    """What the reader is shown with a report dated `when` and checks an answer against: the
    report date, the calendar around it, the team, the tasks and the clauses (kept in memory
    only)."""

    def __init__(
        self, project: LiveProject, when: date, text: str, clauses: Sequence[str] = ()
    ) -> None:
        self.project = project
        self.when = when
        self.text = text
        self.clauses = tuple(clauses) or split_clauses(text, project.definition.settings.language)
        self.calendar: WorkCalendar = project.calendar
        self.team = project.definition.team
        self.tasks = {
            key: node.name
            for key, node in project.nodes().items()
            if project.tasks[key].state != "removed"
        }
        self.states = {key: project.tasks[key].state for key in self.tasks}
        self.roles = project.require_model().role_names
        self.message_words = _words_of(text)
        self._placement: _Placement | None = None

    @property
    def placement(self) -> _Placement:
        if self._placement is None:
            self._placement = _Placement(self.project)
        return self._placement

    def calendar_lines(self) -> list[str]:
        """The weeks around the report date, a line per week from Monday, with the days that
        are not working days marked."""
        calendar = self.calendar
        monday = self.when - timedelta(days=self.when.weekday())
        lines = []
        for week in range(-PAST_WEEKS, NEXT_WEEKS + 1):
            days = []
            for k in range(7):
                day = monday + timedelta(days=7 * week + k)
                label = f"{WEEKDAY_NAMES[k]} {day.isoformat()}"
                if k < 5 and not calendar.is_working(day):
                    holiday = calendar.holidays == "pl" and day in polish_holidays(day.year)
                    label += " (holiday)" if holiday else " (day off)"
                if day == self.when:
                    label += " (report date)"
                days.append(label)
            lines.append("- " + ", ".join(days))
        return lines

    def render(self) -> str:
        """The user message of the reader: the report date, the calendar, the team, the tasks,
        the report and its numbered clauses."""
        when = self.when
        lines = [
            f"Report date: {WEEKDAY_NAMES[when.weekday()]} {when.isoformat()}; the report gives "
            "the state at the end of that day.",
            "",
            'Calendar, a week per line from Monday ("holiday" and "day off" are not working '
            "days; Saturday and Sunday are not either):",
            *self.calendar_lines(),
            "",
            "Team (worker id, name, role; * marks people away on the report date):",
        ]
        day = self.calendar.last(when)
        for w, person in enumerate(self.team):
            away = "*" if self.project.absent(person.key, day) is not None else ""
            lines.append(f"- {w} {person.name}{away} ({person.role})")
        lines += ["", "Tasks (name, state):"]
        for key, name in self.tasks.items():
            lines.append(f'- "{name}": {STATES.get(self.states[key], self.states[key])}')
        lines += ["", "Report:", self.text, "", "The report in numbered clauses:"]
        lines += [f"[{n}] {clause}" for n, clause in enumerate(self.clauses, start=1)]
        return "\n".join(lines)

    def match(self, words: str) -> list[str]:
        """The keys of the tasks the words name, tolerantly (quotes, case, inflection): the
        words of the message among them, every one a form of a word of the task's name; a name
        equal to the words wins; several tasks mean the words are ambiguous."""
        said = [
            w
            for w in _words_of(words)
            if w not in STOP_WORDS and any(word_match(w, m) for m in self.message_words)
        ]
        if not said:
            return []
        found = []
        for key, name in self.tasks.items():
            own = [w for w in _words_of(name) if w not in STOP_WORDS]
            if own == said:
                return [key]
            if all(any(word_match(w, o) for o in own) for w in said):
                found.append(key)
        return found


# ---------------------------------------------------------------- checks of an answer


@dataclass(frozen=True)
class Issue:
    """A problem of an answer: its kind, its place in the answer and the message a repair
    round sends (without values of the answer when the cache withheld it)."""

    kind: str
    loc: tuple[int | str, ...]
    message: str


def _day_issues(
    where: str, loc: tuple[int | str, ...], value: Day | None, text: str
) -> list[Issue]:
    if value is None:
        return []
    issues = []
    try:
        if not ISO_DAY.fullmatch(value.day):
            raise ValueError
        date.fromisoformat(value.day)
    except ValueError:
        issues.append(Issue("day_format", loc, f"{where}: {value.day!r} is not a YYYY-MM-DD date."))
    foreign = foreign_words(value.words)
    if foreign:
        issues.append(
            Issue("phrase_words", loc, f"{where}: the words of a date hold only date words.")
        )
    elif not said_in(read_words(value.words), text):
        issues.append(Issue("phrase_not_said", loc, f"{where}: copy the date's words as written."))
    return issues


def answer_issues(data: object, context: MessageContext) -> list[Issue]:
    """The issues of a schema-valid answer: clause numbers out of range, a worker not in the
    team, task words that fit no task, dates that are no dates or whose words are not date
    words of the message, a share out of range, more work that is none, a person given twice,
    and the checks of a new task of spec section 10.2."""
    try:
        answer = ReaderAnswer.model_validate(data)
    except ValidationError:
        return [Issue("invalid_field", (), "The answer does not match the format.")]
    n = len(context.clauses)
    text = context.text
    issues: list[Issue] = []
    people: set[int] = set()
    for i, item in enumerate(answer.items):
        loc: tuple[int | str, ...] = ("items", i)
        where = f"items[{i}]"
        if not 1 <= item.clause <= n:
            issues.append(Issue("clause_range", loc, f"{where}: clause {item.clause} of 1-{n}."))
        if isinstance(item, AbsenceItem):
            if not 0 <= item.person < len(context.team):
                issues.append(Issue("unknown_worker", loc, f"{where}: no worker {item.person}."))
            elif item.person in people:
                issues.append(Issue("duplicate", loc, f"{where}: worker {item.person} twice."))
            people.add(item.person)
            for value in (item.since, item.until, item.back):
                issues += _day_issues(where, loc, value, text)
        elif isinstance(item, NewTaskItem):
            issues += _new_task_issues(where, loc, item, context)
        else:
            if not context.match(item.task):
                issues.append(Issue("unknown_task", loc, f"{where}: no task fits the words."))
            if isinstance(item, DoneItem):
                issues += _day_issues(where, loc, item.day, text)
            elif isinstance(item, ProgressItem):
                issues += _day_issues(where, loc, item.started, text)
                if item.percent is not None and not 0 <= item.percent <= 100:
                    issues.append(Issue("percent_range", loc, f"{where}: percent out of range."))
            else:
                days, factor = item.extra_days, item.factor
                if (
                    (days is None) == (factor is None)
                    or (days is not None and days <= 0)
                    or (factor is not None and factor <= 1)
                ):
                    issues.append(Issue("work_amount", loc, f"{where}: no more work given."))
    for i, question in enumerate(answer.questions):
        loc = ("questions", i)
        where = f"questions[{i}]"
        if not 1 <= question.clause <= n:
            issues.append(Issue("clause_range", loc, f"{where}: clause {question.clause}."))
        for value in (question.since, question.until, question.back):
            issues += _day_issues(where, loc, value, text)
    for number in answer.unparsed:
        if not 1 <= number <= n:
            issues.append(Issue("clause_range", ("unparsed",), f"unparsed: no clause {number}."))
    return issues


def _new_task_issues(
    where: str, loc: tuple[int | str, ...], item: NewTaskItem, context: MessageContext
) -> list[Issue]:
    """The checks of a new task: its placement words fit one task each, and the research
    parser's checks of a new activity (spec section 10.2) on the project's tasks."""
    issues = []
    ids = context.project.activity_ids()
    placed: dict[str, int | None] = {}
    for side in ("after", "before"):
        words = getattr(item, side)
        found = context.match(words) if words else []
        if words and len(found) != 1:
            issues.append(Issue("unknown_task", loc, f"{where}: {side} fits no single task."))
        placed[side] = ids[found[0]] if len(found) == 1 else None
    event = {
        "type": "new_activity",
        "name": item.name,
        "duration": item.duration,
        "crew": item.crew,
        "after": placed["after"],
        "before": placed["before"],
    }
    for issue in read_answer({"events": [event]}, context.placement).issues:
        issues.append(Issue(issue.kind, loc, f"{where}: {issue.message}"))
    return issues


def withheld_issue(detail: ErrorDetail) -> Issue:
    """An issue of an answer that a cache without prompts withheld (spec section 10), as a
    repair round sends it: its kind, its place and what the kind asks for, no values."""
    kind = detail.type
    hint = HINTS.get(kind, WITHHELD_HINTS.get(kind, ""))
    where = detail.loc or "The answer"
    message = (
        f'{where} has the issue "{kind.replace("_", " ")}"; {hint}give the complete answer again.'
    )
    return Issue(kind, (), message)


# ---------------------------------------------------------------- reading


@dataclass(frozen=True)
class Reading:
    """A round of the reader: the response, its answer if it can be used, and its issues."""

    response: LlmResponse[ReaderAnswer]
    answer: ReaderAnswer | None
    issues: tuple[Issue, ...]
    rounds: int = 0


def _round(response: LlmResponse[ReaderAnswer], context: MessageContext, rounds: int) -> Reading:
    error = response.error
    if error is not None and error.kind in ("domain", "schema"):
        return Reading(response, None, tuple(withheld_issue(d) for d in error.details), rounds)
    if error is not None or response.value is None:
        text = "The answer is not valid JSON or was cut off. Return the JSON object only."
        return Reading(response, None, (Issue("invalid_json", (), text),), rounds)
    issues = tuple(answer_issues(response.parsed, context))
    return Reading(response, None if issues else response.value, issues, rounds)


def read(
    client: LlmClient, context: MessageContext, *, seed: int, settings: ParseSettings = READER
) -> Reading:
    """The reader's call and up to `settings.max_repair_rounds` repair rounds while the answer
    has issues, each with the issues of the last one (kinds and places only when the cache
    withheld the answer)."""
    prompt = load_prompt(READER_PROMPT, settings.prompt_version)
    repair = load_prompt(READER_REPAIR_PROMPT, settings.prompt_version)
    first = [
        Message(role="system", content=prompt.text),
        Message(role="user", content=context.render()),
    ]

    def call(messages: list[Message]) -> LlmResponse[ReaderAnswer]:
        return client.complete(
            messages,
            schema=ReaderAnswer,
            temperature=settings.temperature,
            seed=seed,
            max_tokens=settings.max_tokens,
            validator=lambda data: [
                DomainIssue(issue.kind, issue.loc) for issue in answer_issues(data, context)
            ],
        )

    current = _round(call(first), context, 0)
    while current.issues and current.rounds < settings.max_repair_rounds:
        previous = current.response
        answer = (
            json.dumps(previous.parsed, ensure_ascii=False, separators=(",", ":"))
            if previous.parsed is not None
            else previous.text
        )
        listed = "\n".join(f"- {issue.message}" for issue in current.issues[:40])
        conversation = [
            *first,
            Message(role="assistant", content=answer),
            Message(role="user", content=repair.render(issues=listed)),
        ]
        try:
            response = call(conversation)
        except RequestTooLarge:
            break
        current = _round(response, context, current.rounds + 1)
    return current


# ---------------------------------------------------------------- the draft


def _parse_day(value: Day | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value.day)
    except ValueError:
        return None


def _dates(found: Resolved) -> tuple[date, ...]:
    """The dates a settled phrase allows: its day, or the options of its question."""
    return (found.day,) if found.problem is None and found.day is not None else found.options


@dataclass
class _Builder:
    """The review being built from an accepted answer: its reports, the questions, and the
    clauses that gave something (`used`) or nothing (`unparsed`)."""

    context: MessageContext
    absences: list[AbsenceReport] = field(default_factory=list)
    unchecked_absences: list[int] = field(default_factory=list)
    tasks: dict[str, TaskReport] = field(default_factory=dict)
    unchecked_tasks: set[str] = field(default_factory=set)
    increases: list[WorkIncreaseReport] = field(default_factory=list)
    new_tasks: list[NewTaskReport] = field(default_factory=list)
    questions: list[QuestionDraft] = field(default_factory=list)
    used: set[int] = field(default_factory=set)
    unparsed: set[int] = field(default_factory=set)

    def settle(
        self, value: Day, role: Role, anchor: date | None = None, clause: int = 0
    ) -> Resolved:
        context = self.context
        said = read_words(value.words)
        text = context.clauses[clause - 1] if 1 <= clause <= len(context.clauses) else ""
        tense = clause_tense(f"{text} {value.words}") if role == "since" else None
        return resolve(
            said,
            _parse_day(value),
            role,
            context.when,
            context.calendar,
            anchor=anchor,
            tense=tense,
        )

    def ask(self, question: QuestionDraft) -> None:
        self.questions.append(question)
        self.used.add(question.clause)


def _start(builder: _Builder, value: Day | None, clause: int) -> Resolved:
    """The first day away: its words settled, or the report date if the report gives none."""
    if value is None:
        return Resolved(builder.context.when)
    return builder.settle(value, "since", clause=clause)


def _end(builder: _Builder, item: AbsenceItem | UnknownPerson, first: date) -> Resolved:
    """The return of an absence (spec section 11.3): the day its "back" words name, or the next
    working day after the day its "until" words name; the words decide which ("wraca", "do"),
    else the field. A "do" and a "wraca" that give different returns make a question."""
    calendar = builder.context.calendar
    ends: list[Resolved] = []
    fields: tuple[tuple[Day | None, Role], ...] = ((item.until, "until"), (item.back, "back"))
    for value, given in fields:
        if value is None:
            continue
        said = read_words(value.words)
        role: Role = "back" if said.back else "until" if said.until else given
        found = builder.settle(value, role, first)
        if role == "until" and found.day is not None:
            back = return_after(calendar, found.day)
            found = Resolved(back, named=found.day, unchecked=found.unchecked)
        ends.append(found)
    if not ends:
        return Resolved(None)
    days = {e.day for e in ends if e.day is not None}
    if len(days) > 1:
        return Resolved(None, "mismatch", tuple(sorted(days)))
    problem = next((e for e in ends if e.problem is not None), None)
    if problem is not None:
        return problem
    return Resolved(ends[0].day, unchecked=all(e.unchecked for e in ends))


def _absence(builder: _Builder, item: AbsenceItem) -> None:
    context = builder.context
    person = context.team[item.person].key
    start = _start(builder, item.since, item.clause)
    firsts = _dates(start) or (context.when,)
    end = _end(builder, item, firsts[0])
    backs: tuple[date | None, ...] = _dates(end) if end.day is not None or end.problem else (None,)
    options = [
        AbsenceReport(person=person, first_day=f, return_date=b)
        for f in firsts
        for b in backs
        if b is None or b > f
    ]
    builder.used.add(item.clause)
    wrong = start if start.problem is not None else end if end.problem is not None else None
    if wrong is not None and options:
        builder.ask(
            QuestionDraft(
                kind="date",
                clause=item.clause,
                person=person,
                problem=wrong.problem,
                said=wrong.named,
                weekday=wrong.weekday,
                absences=tuple(options),
            )
        )
        return
    if not options:  # a return on or before the first day away: the dates need a look
        options = [AbsenceReport(person=person, first_day=firsts[0])]
    builder.absences.append(options[0])
    if wrong is not None or start.unchecked or end.unchecked or len(options) > 1:
        builder.unchecked_absences.append(len(builder.absences) - 1)


def _task_reports(builder: _Builder, item: DoneItem | ProgressItem, key: str) -> list[TaskReport]:
    """The reports a task item can become: one, several when its date needs a question, none
    for nothing to report (a finish or a start after the report date, "trwa" of a running
    task)."""
    context = builder.context
    when = context.when
    if isinstance(item, DoneItem) or (item.percent is not None and item.percent >= 100):
        value = item.day if isinstance(item, DoneItem) else None
        found = builder.settle(value, "done") if value is not None else Resolved(when)
        return [TaskReport(task=key, status="done", finish=d) for d in _dates(found) if d <= when]
    percent = round(item.percent) if item.percent is not None else None
    if item.started is None or context.states[key] != "unstarted":
        if context.states[key] == "started" and percent is None:
            return []
        return [TaskReport(task=key, status="in_progress", percent=percent or 0)]
    found = builder.settle(item.started, "start")
    return [
        TaskReport(task=key, status="in_progress", percent=percent or 0, start=d)
        for d in _dates(found)
        if d <= when
    ]


def _task_found(builder: _Builder, item: DoneItem | ProgressItem) -> Resolved | None:
    value = item.day if isinstance(item, DoneItem) else item.started
    if value is None:
        return None
    return builder.settle(value, "done" if isinstance(item, DoneItem) else "start")


def _task(builder: _Builder, item: DoneItem | ProgressItem) -> None:
    context = builder.context
    keys = [k for k in context.match(item.task) if context.states[k] not in ("done", "removed")]
    if len(keys) > 1:
        options = [r for key in keys for r in _task_reports(builder, item, key)[:1]]
        builder.ask(
            QuestionDraft(
                kind="ambiguous_task",
                clause=item.clause,
                candidates=tuple(r.task for r in options),
                tasks=tuple(options),
            )
        )
        return
    reports = _task_reports(builder, item, keys[0]) if keys else []
    if not reports:
        builder.unparsed.add(item.clause)
        return
    builder.used.add(item.clause)
    found = _task_found(builder, item)
    key = keys[0]
    if found is not None and found.problem is not None:
        builder.ask(
            QuestionDraft(
                kind="date",
                clause=item.clause,
                task=key,
                problem=found.problem,
                said=found.named,
                weekday=found.weekday,
                tasks=tuple(reports),
            )
        )
        return
    report = reports[0]
    earlier = builder.tasks.get(key)
    if earlier is not None:  # two items of one task: done wins, a start and a share are kept
        start = report.start or earlier.start
        if "done" in (report.status, earlier.status):
            finish = report.finish if report.status == "done" else earlier.finish
            report = TaskReport(task=key, status="done", finish=finish, start=start)
        else:
            percent = max(report.percent or 0, earlier.percent or 0)
            report = report.model_copy(update={"percent": percent, "start": start})
    builder.tasks[key] = report
    if found is not None and found.unchecked:
        builder.unchecked_tasks.add(key)


def _more_work(builder: _Builder, item: MoreWorkItem) -> None:
    context = builder.context
    keys = [k for k in context.match(item.task) if context.states[k] not in ("done", "removed")]
    reports = [
        WorkIncreaseReport(task=k, extra_days=item.extra_days, factor=item.factor) for k in keys
    ]
    if not reports:
        builder.unparsed.add(item.clause)
    elif len(reports) > 1:
        builder.ask(
            QuestionDraft(
                kind="ambiguous_task",
                clause=item.clause,
                candidates=tuple(keys),
                extra_days=item.extra_days,
                factor=item.factor,
                increases=tuple(reports),
            )
        )
    else:
        builder.used.add(item.clause)
        builder.increases.append(reports[0])


def _new_task(builder: _Builder, item: NewTaskItem) -> None:
    context = builder.context
    after = context.match(item.after) if item.after else []
    before = context.match(item.before) if item.before else []
    builder.used.add(item.clause)
    builder.new_tasks.append(
        NewTaskReport(
            name=" ".join(item.name.split())[:120],
            duration=item.duration,
            crew={role: count for role, count in item.crew.items() if count > 0},
            after=after[0] if len(after) == 1 else None,
            before=before[0] if len(before) == 1 else None,
        )
    )


def _unknown_person(builder: _Builder, question: UnknownPerson) -> None:
    """A question about somebody away who is not in the team, with the absence's dates; if
    they need a choice too, the person's options carry each choice."""
    start = _start(builder, question.since, question.clause)
    firsts = _dates(start) or (builder.context.when,)
    end = _end(builder, question, firsts[0])
    backs: tuple[date | None, ...] = _dates(end) if end.day is not None or end.problem else (None,)
    options = [
        AbsenceReport(person="", first_day=f, return_date=b)
        for f in firsts
        for b in backs
        if b is None or b > f
    ] or [AbsenceReport(person="", first_day=firsts[0])]
    wrong = start if start.problem is not None else end if end.problem is not None else None
    builder.ask(
        QuestionDraft(
            kind="unknown_person",
            clause=question.clause,
            first_day=options[0].first_day,
            return_date=options[0].return_date,
            problem=None if wrong is None else wrong.problem,
            said=None if wrong is None else wrong.named,
            weekday=None if wrong is None else wrong.weekday,
            absences=tuple(options) if len(options) > 1 else (),
        )
    )


def draft(reading: Reading, context: MessageContext) -> MessageDraft:
    """The review of a reading: its items as check-in reports, the questions and the clauses
    turned into nothing; an answer with issues after the last round gives none of its items."""
    builder = _Builder(context)
    answer = reading.answer
    if answer is not None:
        for item in answer.items:
            if isinstance(item, AbsenceItem):
                _absence(builder, item)
            elif isinstance(item, MoreWorkItem):
                _more_work(builder, item)
            elif isinstance(item, NewTaskItem):
                _new_task(builder, item)
            else:
                _task(builder, item)
        for question in answer.questions:
            _unknown_person(builder, question)
        builder.unparsed |= set(answer.unparsed)
    names = {person.key: person.name for person in context.team}
    doubtful = tuple(
        i
        for i, a in enumerate(builder.absences)
        if not named_in(names.get(a.person, ""), context.text)
    )
    tasks = tuple(builder.tasks.values())
    return MessageDraft(
        absences=tuple(builder.absences),
        tasks=tasks,
        increases=tuple(builder.increases),
        new_tasks=tuple(builder.new_tasks),
        issues=len(reading.issues),
        unparsed=tuple(sorted(builder.unparsed - builder.used)),
        questions=tuple(builder.questions),
        doubtful=doubtful,
        unchecked_absences=tuple(builder.unchecked_absences),
        unchecked_tasks=tuple(i for i, t in enumerate(tasks) if t.task in builder.unchecked_tasks),
    )


def read_message(
    client: LlmClient, project: LiveProject, text: str, when: date, *, seed: int
) -> MessageDraft:
    """The review of a manager's check-in message dated `when` (spec section 11.3, v2.3.0)."""
    context = MessageContext(project, when, text)
    return draft(read(client, context, seed=seed), context)
