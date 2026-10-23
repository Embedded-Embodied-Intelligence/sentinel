"""Events from team messages, role 1 of the interpretation layer (spec section 10.2; RQ5).

The parser, an LLM, reads one dated team message together with the team roster and the
activities of the day's observation (`Context.render`) and answers in the schema
`MessageEvents`: absences (worker, announced earliest return day or null), work increases
(activity, factor) and new activities (name, duration, crew per role, the activities it follows
and precedes), an empty list for a message without an event. No field can hold the reason of an
absence (CLAUDE.md invariant 7, GDPR Art. 9). `read_answer` checks an answer entry by entry
against the observation and keeps the valid events; `parse` runs the WP6a repair loop on its
issues. `apply_events` changes the observation by accepted events as the engine would, so that
parsed and true events can be compared on the state they lead to (`same_observation`), and
`compare_events` compares them event by event.
"""

import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, ValidationError

from sentinel.interpret.team import Member, weekday_name
from sentinel.llm import LlmClient, LlmResponse, Message, Prompt, RequestTooLarge, load_prompt
from sentinel.simulation.state import (
    PAUSED,
    REMOVED,
    RUNNING,
    UNSTARTED,
    InsertedActivity,
    Observation,
    nominal_activity,
    nominal_world,
    successor_lists,
)
from sentinel.wbs.extract import normalise_name, normalise_role
from sentinel.wbs.narrate import role_names

EVENTS_PROMPT = "events_parse"  # system prompt, prompts/events_parse.<version>.txt
EVENTS_REPAIR_PROMPT = "events_repair"  # repair message with $issues
MAX_LISTED_ISSUES = 40
MAX_ABSENCE_DAYS = 365  # an announced return beyond a year is impossible (spec sections 5.1, 10.2)
FACTOR_TOLERANCE = 0.01  # factors have two decimals (spec section 10.2)
EventType = Literal["absence", "work_increase", "new_activity"]
EVENT_TYPES: tuple[EventType, ...] = ("absence", "work_increase", "new_activity")
STATUS_TEXT = {
    UNSTARTED: "not started",
    RUNNING: "running",
    PAUSED: "paused",
    "done": "done",
    REMOVED: "removed",
}
# Reasons a message may give for an absence; none of their words may reach a parsed event
# (invariant 7). REASON_WORDS adds common paraphrases.
REASONS = (
    "the flu",
    "a migraine",
    "a doctor's appointment",
    "a family matter",
    "a family emergency",
    "a funeral",
    "childcare duties",
    "a hospital visit",
    "a dental appointment",
    "an illness",
    "minor surgery",
    "a medical check-up",
)
REASON_WORDS = (
    "flu",
    "migraine",
    "doctor",
    "family",
    "funeral",
    "childcare",
    "hospital",
    "dental",
    "illness",
    "surgery",
    "medical",
    "sick",
    "ill",
)
_REASON_PATTERN = re.compile(r"\b(?:" + "|".join(REASON_WORDS) + r")\b", re.IGNORECASE)

IssueKind = Literal[
    "invalid_json",
    "missing_field",
    "invalid_field",
    "unknown_type",
    "unknown_worker",
    "already_absent",
    "impossible_day",
    "unknown_activity",
    "not_running",
    "factor_below_one",
    "non_positive_duration",
    "unknown_role",
    "crew_above_capacity",
    "name_in_use",
    "invalid_placement",
    "duplicate",
]
ISSUE_KINDS: tuple[IssueKind, ...] = (
    "invalid_json",
    "missing_field",
    "invalid_field",
    "unknown_type",
    "unknown_worker",
    "already_absent",
    "impossible_day",
    "unknown_activity",
    "not_running",
    "factor_below_one",
    "non_positive_duration",
    "unknown_role",
    "crew_above_capacity",
    "name_in_use",
    "invalid_placement",
    "duplicate",
)


class AbsenceEvent(BaseModel):
    """D1 onset today: `worker` is absent; `return_day` is the announced earliest return day,
    None if the message gives none (L_low = 1). There is no field for a reason."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["absence"]
    worker: int
    return_day: int | None


class WorkIncreaseEvent(BaseModel):
    """D2 observed today: the remaining work of the running `activity` times `factor`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["work_increase"]
    activity: int
    factor: float


class NewActivityEvent(BaseModel):
    """D3 today: a new activity with its nominal duration and people per role, inserted after
    `after` (None: the source) and before `before` (None: the sink)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["new_activity"]
    name: str
    duration: int
    crew: dict[str, int]
    after: int | None
    before: int | None


Event = AbsenceEvent | WorkIncreaseEvent | NewActivityEvent
EVENT_MODELS: dict[str, type[Event]] = {
    "absence": AbsenceEvent,
    "work_increase": WorkIncreaseEvent,
    "new_activity": NewActivityEvent,
}


class MessageEvents(BaseModel):
    """The output schema of the parser: the events of one message, in message order."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    events: tuple[AbsenceEvent | WorkIncreaseEvent | NewActivityEvent, ...]


class TeamMessage(BaseModel):
    """A team message of `day` written by the original worker `author`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    day: int = Field(ge=0)
    author: int = Field(ge=0)
    text: str = Field(min_length=1)


class Context:
    """What the parser is shown with a message: the day's observation, the names of its real
    activities (D3 ones included) and the roster of its original workers. Running activities are
    shown with their remaining work, the deterministic estimate of spec section 5.2 in full-crew
    days with one decimal (at least 0.1), which "another d days" refers to."""

    def __init__(
        self, observation: Observation, names: Mapping[int, str], members: Sequence[Member]
    ) -> None:
        self.observation = observation
        self.day = observation.day
        self.names = dict(sorted(names.items()))
        self.roster = tuple(members)
        self.members = {member.worker: member for member in members}
        self.by_member_name = {member.name: member.worker for member in members}
        self.roles = role_names(observation.instance)
        self.role_index = {normalise_role(role): k for k, role in enumerate(self.roles)}
        self.capacities = tuple(role.capacity for role in observation.instance.roles)
        self.sink = observation.instance.sink_id
        self.successors = successor_lists(observation)
        self.by_name = {normalise_name(name): j for j, name in self.names.items()}
        world = nominal_world(observation)
        self.remaining: dict[int, float] = {}
        for j, status in enumerate(observation.status):
            if status == RUNNING and j in self.names:
                unit = max(1, sum(nominal_activity(observation, j)[1]))
                self.remaining[j] = max(0.1, round(world.remaining[j] / unit, 1))

    def descendants(self, j: int) -> set[int]:
        """Every activity reachable from j by precedence edges, j excluded."""
        seen: set[int] = set()
        stack = list(self.successors[j])
        while stack:
            i = stack.pop()
            if i not in seen:
                seen.add(i)
                stack.extend(self.successors[i])
        return seen

    def placement_issue(self, after: int | None, before: int | None) -> str | None:
        """Why a new activity cannot be inserted after `after` and before `before` (spec
        sections 2.2 and 10.2), or None."""
        status = self.observation.status
        if before is not None:
            if before not in self.names:
                return f'"before" names activity {before}, which is not in the activity list'
            if status[before] != UNSTARTED:
                return (
                    f'"before" must be an activity that has not started (or null for the '
                    f"release), but activity {before} is {STATUS_TEXT[status[before]]}"
                )
        if after is not None:
            if after not in self.names:
                return f'"after" names activity {after}, which is not in the activity list'
            if status[after] == REMOVED:
                return f'"after" names activity {after}, which was removed from the project'
            if after == before:
                return '"after" and "before" name the same activity'
            if before is not None and after in self.descendants(before):
                return (
                    f"activity {after} comes after activity {before} in the plan, so a task "
                    f"cannot follow {after} and precede {before}"
                )
        return None

    def render(self, message: TeamMessage) -> str:
        """The user message of the parser: today, the roster per role (absent people marked),
        the activities with their status and the message."""
        observation, t = self.observation, self.day
        lines = [
            f"Today is day {t}, a {weekday_name(t)}.",
            "",
            "Team roster (worker id and name per role; * marks people absent today):",
        ]
        for k, role in enumerate(self.roles):
            people = [
                f"{m.worker} {m.name}{'' if observation.present[m.worker] else '*'}"
                for m in self.roster
                if m.role == k
            ]
            lines.append(f"- {role}: {', '.join(people)}")
        lines += ["", "Activities (id, name, status; running ones with their remaining work):"]
        for j, name in self.names.items():
            entry = f'{j} "{name}": {STATUS_TEXT[observation.status[j]]}'
            if j in self.remaining:
                entry += f", {self.remaining[j]:.1f} days of work left"
            lines.append(entry)
        author = self.members[message.author].name
        lines += ["", f"Message from {author} on day {t} ({weekday_name(t)}):", message.text]
        return "\n".join(lines)


@dataclass(frozen=True)
class EventIssue:
    """A problem of an answer, with the English message sent back in a repair round."""

    kind: IssueKind
    message: str


@dataclass(frozen=True)
class Reading:
    """An answer read against its context: the accepted events (each valid on its own; of a
    worker, activity or name given twice the first) and the issues."""

    events: tuple[Event, ...]
    issues: tuple[EventIssue, ...]

    @property
    def valid(self) -> bool:
        return not self.issues


def read_answer(data: object, context: Context) -> Reading:
    """The accepted events and the issues of a parsed answer (spec section 10.2)."""
    if not isinstance(data, dict):
        return Reading((), (EventIssue("invalid_field", _OBJECT),))
    issues = [
        EventIssue(
            "invalid_field",
            f'The answer has the field "{key}", which the format does not allow; remove it.',
        )
        for key in sorted(set(data) - {"events"})
    ]
    entries = data.get("events")
    if "events" not in data:
        issues.append(EventIssue("missing_field", _OBJECT))
    if not isinstance(entries, list):
        if "events" in data:
            issues.append(EventIssue("invalid_field", '"events" must be a list of events.'))
        return Reading((), tuple(issues))
    accepted: list[Event] = []
    seen: dict[tuple[str, object], int] = {}
    for index, entry in enumerate(entries):
        event, problems = _read_event(index, entry, context)
        issues += problems
        if event is None:
            continue
        key = _key(event)
        if key in seen:
            what = {"absence": "worker", "work_increase": "activity", "new_activity": "task"}
            issues.append(
                EventIssue(
                    "duplicate",
                    f"events[{index}] repeats the {what[event.type]} of events[{seen[key]}]; "
                    "report each event once.",
                )
            )
            continue
        seen[key] = index
        accepted.append(event)
    return Reading(tuple(accepted), tuple(issues))


_OBJECT = 'The answer must be a JSON object with the field "events", a list of events.'


def _key(event: Event) -> tuple[str, object]:
    """What identifies an event of a message: its worker, activity or normalised name."""
    match event:
        case AbsenceEvent():
            return "absence", event.worker
        case WorkIncreaseEvent():
            return "work_increase", event.activity
        case NewActivityEvent():
            return "new_activity", normalise_name(event.name)


def _read_event(
    index: int, entry: object, context: Context
) -> tuple[Event | None, list[EventIssue]]:
    where = f"events[{index}]"
    if not isinstance(entry, dict):
        message = f'{where} is not a JSON object; give each event as an object with a "type".'
        return None, [EventIssue("invalid_field", message)]
    kind = entry.get("type")
    model = EVENT_MODELS.get(kind) if isinstance(kind, str) else None
    if model is None:
        types = '"absence", "work_increase" or "new_activity"'
        if kind is None:
            return None, [EventIssue("missing_field", f'{where} has no "type"; use {types}.')]
        message = (
            f"{where} has a type that is not an event type; use {types}, or leave out what "
            "the message does not report as an event."
        )
        return None, [EventIssue("unknown_type", message)]
    try:
        event = model.model_validate(entry)
    except ValidationError as exc:
        return None, [_field_issue(where, str(kind), error) for error in exc.errors()]
    issues = _event_issues(where, event, context)
    return (None, issues) if issues else (event, [])


def _field_issue(where: str, kind: str, error: Mapping[str, object]) -> EventIssue:
    loc = error.get("loc", ())
    name = ".".join(str(part) for part in loc) if isinstance(loc, tuple) else str(loc)
    if error.get("type") == "missing":
        return EventIssue("missing_field", f'{where} ({kind}) lacks the field "{name}".')
    if error.get("type") == "extra_forbidden":
        message = f'{where} ({kind}) has the field "{name}", which this event type does not have.'
        if kind == "absence":
            message += " An absence records only the worker and the return day."
        return EventIssue("invalid_field", f"{message} Remove it.")
    return EventIssue("invalid_field", f'{where} ({kind}): "{name}": {error.get("msg")}.')


def _event_issues(where: str, event: Event, context: Context) -> list[EventIssue]:
    """The checks of spec section 10.2 for one event of the right shape."""
    observation, t = context.observation, context.day
    issues: list[EventIssue] = []
    match event:
        case AbsenceEvent(worker=w, return_day=r):
            member = context.members.get(w)
            if member is None:
                issues.append(
                    EventIssue(
                        "unknown_worker",
                        f"{where} (absence) names worker {w}, who is not in the roster; use the "
                        "id of the person the message is about.",
                    )
                )
            elif not observation.present[w]:
                issues.append(
                    EventIssue(
                        "already_absent",
                        f"{where} (absence): worker {w} ({member.name}) is absent already; "
                        "report only absences that start today.",
                    )
                )
            if r is not None and not t < r <= t + MAX_ABSENCE_DAYS:
                when = "is not after today" if r <= t else "is more than a year away"
                issues.append(
                    EventIssue(
                        "impossible_day",
                        f"{where} (absence): the return day {r} {when} (day {t}); give the first "
                        "day the person is back, or null if the message does not say.",
                    )
                )
        case WorkIncreaseEvent(activity=j, factor=factor):
            if j not in context.names:
                issues.append(
                    EventIssue(
                        "unknown_activity",
                        f"{where} (work_increase) names activity {j}, which is not in the "
                        "activity list; use the id of the activity the message names.",
                    )
                )
            elif observation.status[j] != RUNNING:
                issues.append(
                    EventIssue(
                        "not_running",
                        f"{where} (work_increase): activity {j} is "
                        f"{STATUS_TEXT[observation.status[j]]}, not running; only running "
                        "activities get more work, so check the activity the message names.",
                    )
                )
            if not math.isfinite(factor) or factor < 1:
                issues.append(
                    EventIssue(
                        "factor_below_one",
                        f"{where} (work_increase): the factor {factor:g} is below 1; it "
                        "multiplies the remaining work, e.g. 1.5 for 50 % more.",
                    )
                )
        case NewActivityEvent():
            issues += _new_activity_issues(where, event, context)
    return issues


def _new_activity_issues(where: str, event: NewActivityEvent, context: Context) -> list[EventIssue]:
    issues: list[EventIssue] = []
    if not event.name.strip():
        issues.append(EventIssue("invalid_field", f'{where} (new_activity) needs a "name".'))
    elif normalise_name(event.name) in context.by_name:
        issues.append(
            EventIssue(
                "name_in_use",
                f'{where} (new_activity): "{event.name}" is already an activity of the project; '
                "give the new task's name as the message states it.",
            )
        )
    if event.duration < 1:
        issues.append(
            EventIssue(
                "non_positive_duration",
                f"{where} (new_activity): the duration {event.duration} must be at least one "
                "working day.",
            )
        )
    seen: set[int] = set()
    for role, count in event.crew.items():
        k = context.role_index.get(normalise_role(role))
        if k is None:
            roles = ", ".join(context.roles)
            issues.append(
                EventIssue(
                    "unknown_role",
                    f'{where} (new_activity): "{role}" is not a role of the team; use {roles}.',
                )
            )
        elif k in seen:
            issues.append(
                EventIssue("invalid_field", f'{where} (new_activity) names "{role}" twice.')
            )
        elif count < 0:
            issues.append(
                EventIssue(
                    "invalid_field",
                    f'{where} (new_activity): the crew of "{role}" must be a whole number of '
                    "people, at least 0.",
                )
            )
        elif count > context.capacities[k]:
            issues.append(
                EventIssue(
                    "crew_above_capacity",
                    f"{where} (new_activity) needs {count} people as {context.roles[k]}, more "
                    f"than the {context.capacities[k]} of the team.",
                )
            )
        if k is not None:
            seen.add(k)
    placement = context.placement_issue(event.after, event.before)
    if placement is not None:
        issues.append(EventIssue("invalid_placement", f"{where} (new_activity): {placement}."))
    return issues


def demands_of(event: NewActivityEvent, context: Context) -> tuple[int, ...]:
    """r_jk of a valid new activity, by role."""
    demands = [0] * len(context.roles)
    for role, count in event.crew.items():
        demands[context.role_index[normalise_role(role)]] = count
    return tuple(demands)


def apply_events(context: Context, events: Iterable[Event]) -> Observation:
    """The observation of the context's day after the accepted `events` (spec section 10.2):
    absences in worker order (present false, absence start today, announced bound L_low =
    return day - today, 1 without one; a running activity without a present crew member is
    paused), work increases in activity order (the shock (j, e_j, F) with F to two decimals),
    new activities by name (the next ids, unstarted, planned at the earliest
    precedence-feasible day >= t + 1 from planned starts and realised finishes, spec 3.1 e).
    The order makes the result independent of the order of the answer."""
    observation, t = context.observation, context.day
    events = list(events)
    absences = sorted((e for e in events if isinstance(e, AbsenceEvent)), key=lambda e: e.worker)
    increases = sorted(
        (e for e in events if isinstance(e, WorkIncreaseEvent)), key=lambda e: e.activity
    )
    news = sorted(
        (e for e in events if isinstance(e, NewActivityEvent)),
        key=lambda e: (normalise_name(e.name), e.duration, e.after or 0, e.before or -1),
    )
    present, since, announced = (
        list(observation.present),
        list(observation.absent_since),
        list(observation.announced),
    )
    for absence in absences:
        present[absence.worker] = False
        since[absence.worker] = t
        announced[absence.worker] = 1 if absence.return_day is None else absence.return_day - t
    status = list(observation.status)
    for j, state in enumerate(status):
        crew = observation.assigned[j]
        if state == RUNNING and crew and not any(present[w] for w in crew):
            status[j] = PAUSED
    shocks = observation.work_increases + tuple(
        (e.activity, observation.work_done[e.activity], round(e.factor, 2)) for e in increases
    )
    inserted = list(observation.inserted)
    plan = list(observation.plan)
    extra = 0
    for event in news:
        new = len(status)
        predecessor = 0 if event.after is None else event.after
        ready = observation.finish[predecessor]
        if ready is None:
            ready = plan[predecessor] + nominal_activity(observation, predecessor)[0]
        inserted.append(
            InsertedActivity(
                id=new,
                day=t,
                duration=event.duration,
                demands=demands_of(event, context),
                predecessor=predecessor,
                successor=context.sink if event.before is None else event.before,
            )
        )
        plan.append(max(t + 1, ready))
        status.append(UNSTARTED)
        extra += 1
    return observation.model_copy(
        update={
            "present": tuple(present),
            "absent_since": tuple(since),
            "announced": tuple(announced),
            "status": tuple(status),
            "work_increases": shocks,
            "inserted": tuple(inserted),
            "plan": tuple(plan),
            "work_done": observation.work_done + (0.0,) * extra,
            "start": observation.start + (None,) * extra,
            "finish": observation.finish + (None,) * extra,
            "assigned": observation.assigned + ((),) * extra,
        }
    )


def same_observation(a: Observation, b: Observation, tolerance: float = FACTOR_TOLERANCE) -> bool:
    """Whether two observations agree, the factors of their D2 shocks within `tolerance`."""
    if len(a.work_increases) != len(b.work_increases):
        return False
    for (j, e, f), (k, g, h) in zip(a.work_increases, b.work_increases, strict=True):
        if j != k or e != g or abs(f - h) > tolerance + 1e-9:
            return False
    plain = {"work_increases": ()}
    return a.model_copy(update=plain) == b.model_copy(update=plain)


@dataclass(frozen=True)
class TypeCounts:
    """Events of one type: in the truth, accepted from the answer, and matched one to one (same
    worker, activity or normalised name)."""

    true: int = 0
    predicted: int = 0
    matched: int = 0


@dataclass(frozen=True)
class Comparison:
    """Parsed against true events of a message: counts per type, (correct, compared) per field
    of the matched events (e.g. "absence.return_day") and whether all of it is exact."""

    counts: dict[EventType, TypeCounts]
    fields: dict[str, tuple[int, int]] = field(default_factory=dict)

    @property
    def exact(self) -> bool:
        counts_equal = all(c.true == c.predicted == c.matched for c in self.counts.values())
        return counts_equal and all(right == total for right, total in self.fields.values())


EVENT_FIELDS: dict[EventType, tuple[str, ...]] = {
    "absence": ("return_day",),
    "work_increase": ("factor",),
    "new_activity": ("duration", "crew", "after", "before"),
}


def compare_events(
    truth: Sequence[Event], predicted: Sequence[Event], tolerance: float = FACTOR_TOLERANCE
) -> Comparison:
    """Match predicted to true events one to one by type and key (`_key`, first match) and
    compare the fields of the matched ones: return days and new activities exactly (crews
    after role normalisation, without zero entries), factors within `tolerance`."""
    counts: dict[EventType, TypeCounts] = {}
    fields: dict[str, tuple[int, int]] = {
        f"{kind}.{name}": (0, 0) for kind in EVENT_TYPES for name in EVENT_FIELDS[kind]
    }
    for kind in EVENT_TYPES:
        mine = [e for e in truth if e.type == kind]
        theirs = [e for e in predicted if e.type == kind]
        free = list(mine)
        matched = 0
        for event in theirs:
            partner = next((e for e in free if _key(e) == _key(event)), None)
            if partner is None:
                continue
            free.remove(partner)
            matched += 1
            for name, right in _field_checks(partner, event, tolerance):
                good, total = fields[f"{kind}.{name}"]
                fields[f"{kind}.{name}"] = (good + right, total + 1)
        counts[kind] = TypeCounts(len(mine), len(theirs), matched)
    return Comparison(counts, fields)


def _field_checks(true: Event, parsed: Event, tolerance: float) -> list[tuple[str, bool]]:
    if isinstance(true, AbsenceEvent) and isinstance(parsed, AbsenceEvent):
        return [("return_day", true.return_day == parsed.return_day)]
    if isinstance(true, WorkIncreaseEvent) and isinstance(parsed, WorkIncreaseEvent):
        return [("factor", abs(true.factor - parsed.factor) <= tolerance + 1e-9)]
    if isinstance(true, NewActivityEvent) and isinstance(parsed, NewActivityEvent):
        return [
            ("duration", true.duration == parsed.duration),
            ("crew", _crew(true.crew) == _crew(parsed.crew)),
            ("after", true.after == parsed.after),
            ("before", true.before == parsed.before),
        ]
    raise TypeError(f"cannot compare {true.type} with {parsed.type}")


def _crew(crew: Mapping[str, int]) -> dict[str, int]:
    return {normalise_role(role): n for role, n in crew.items() if n}


def leaks(data: object) -> int:
    """The strings (keys included) in a parsed answer that contain a reason word."""
    match data:
        case str():
            return int(bool(_REASON_PATTERN.search(data)))
        case dict():
            return sum(leaks(key) + leaks(value) for key, value in data.items())
        case list() | tuple():
            return sum(leaks(item) for item in data)
    return 0


class ParseSettings(BaseModel):
    """Prompt version and decoding parameters of a parsing session."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt_version: str = Field(default="v1", min_length=1)
    max_tokens: PositiveInt
    temperature: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    max_repair_rounds: int = Field(default=3, ge=0)


@dataclass(frozen=True)
class ParseRound:
    """One call of a parsing session: round 0 is the single-shot call, round r the r-th repair."""

    index: int
    response: LlmResponse[MessageEvents]
    reading: Reading


@dataclass(frozen=True)
class ParseSession:
    """The rounds of a parsing session and why it stopped early (None: it did not)."""

    rounds: tuple[ParseRound, ...]
    stopped: str | None = None

    @property
    def single_shot(self) -> ParseRound:
        return self.rounds[0]

    @property
    def final(self) -> ParseRound:
        return self.rounds[-1]

    @property
    def repair_rounds(self) -> int:
        return len(self.rounds) - 1


def answer_reading(response: LlmResponse[MessageEvents], context: Context) -> Reading:
    """The reading of an answer: unparseable or cut-off JSON as one issue, else `read_answer`."""
    error = response.error
    if error is not None and error.kind in ("empty", "json", "truncated"):
        if error.kind == "truncated":
            message = "The answer was cut off before the JSON object was complete."
        else:
            message = f"The answer is not valid JSON ({error.message})."
        return Reading((), (EventIssue("invalid_json", f"{message} Return the JSON only."),))
    return read_answer(response.parsed, context)


def parse_messages(context: Context, message: TeamMessage, prompt: Prompt) -> list[Message]:
    """The single-shot conversation: the system prompt and the rendered context and message."""
    return [
        Message(role="system", content=prompt.text),
        Message(role="user", content=context.render(message)),
    ]


def repair_messages(
    context: Context,
    message: TeamMessage,
    previous: LlmResponse[MessageEvents],
    issues: Sequence[EventIssue],
    prompt: Prompt,
    repair_prompt: Prompt,
) -> list[Message]:
    """A repair round: the single-shot conversation, the previous answer (compact JSON if it
    parsed, else its text) and the issues with the request for a corrected answer."""
    if previous.parsed is not None:
        answer = json.dumps(previous.parsed, ensure_ascii=False, separators=(",", ":"))
    else:
        answer = previous.text
    lines = [f"- {issue.message}" for issue in issues[:MAX_LISTED_ISSUES]]
    if len(issues) > MAX_LISTED_ISSUES:
        lines.append(f"- ... and {len(issues) - MAX_LISTED_ISSUES} more issues of these kinds.")
    return [
        *parse_messages(context, message, prompt),
        Message(role="assistant", content=answer),
        Message(role="user", content=repair_prompt.render(issues="\n".join(lines))),
    ]


def parse(
    client: LlmClient,
    message: TeamMessage,
    context: Context,
    *,
    seed: int,
    settings: ParseSettings,
) -> ParseSession:
    """The single-shot call, then repair rounds while the answer has issues, at most
    `settings.max_repair_rounds`, every round with the same seed (the WP6a loop)."""
    prompt = load_prompt(EVENTS_PROMPT, settings.prompt_version)
    repair_prompt = load_prompt(EVENTS_REPAIR_PROMPT, settings.prompt_version)

    def call(messages: list[Message]) -> LlmResponse[MessageEvents]:
        return client.complete(
            messages,
            schema=MessageEvents,
            temperature=settings.temperature,
            seed=seed,
            max_tokens=settings.max_tokens,
        )

    first = call(parse_messages(context, message, prompt))
    rounds = [ParseRound(0, first, answer_reading(first, context))]
    while rounds[-1].reading.issues and len(rounds) <= settings.max_repair_rounds:
        last = rounds[-1]
        conversation = repair_messages(
            context, message, last.response, last.reading.issues, prompt, repair_prompt
        )
        try:
            response = call(conversation)
        except RequestTooLarge as exc:
            return ParseSession(tuple(rounds), stopped=f"request too large: {exc}")
        rounds.append(ParseRound(len(rounds), response, answer_reading(response, context)))
    return ParseSession(tuple(rounds))
