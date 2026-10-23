"""LLM extraction of a project model from a description, its validation and the repair loop
(RQ1, WP6a).

The LLM answers with one JSON object of the schema `Extraction`: the team (people per role)
and every activity with its duration in working days, crew per role and immediate
predecessors by name. `validate_extraction` lists the issues of an answer; an answer without
issues becomes a `ProjectInstance` (spec section 1) with `to_instance`. `single_shot` is one
call; `repair` sends the issues and the previous JSON back up to three times and asks for a
corrected full JSON. Its first call is the single-shot call, so one session yields both
conditions of RQ1. Names match after `normalise_name`; role names also lose a plural "s".
"""

import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, ValidationError

from sentinel.llm import LlmClient, LlmResponse, Message, Prompt, RequestTooLarge, load_prompt
from sentinel.model.instance import Activity, ProjectInstance, Role, make_workers

EXTRACT_PROMPT = "wbs_extract"  # system prompt, prompts/wbs_extract.<version>.txt
REPAIR_PROMPT = (
    "wbs_repair"  # follow-up user message with $issues, prompts/wbs_repair.<version>.txt
)
MAX_LISTED_ISSUES = 40  # a repair message lists at most this many issues

IssueKind = Literal[
    "invalid_json",
    "missing_field",
    "invalid_field",
    "duplicate_role",
    "unknown_role",
    "negative_count",
    "duplicate_name",
    "unknown_name",
    "cycle",
    "non_positive_duration",
    "crew_above_capacity",
]
ISSUE_KINDS: tuple[IssueKind, ...] = (
    "invalid_json",
    "missing_field",
    "invalid_field",
    "duplicate_role",
    "unknown_role",
    "negative_count",
    "duplicate_name",
    "unknown_name",
    "cycle",
    "non_positive_duration",
    "crew_above_capacity",
)


class TeamMember(BaseModel):
    """People of one role in the team."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: str
    count: int


class ExtractedActivity(BaseModel):
    """One activity: duration in working days, people per role, immediate predecessors."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    duration_days: int
    crew: dict[str, int]
    predecessors: tuple[str, ...]


class Extraction(BaseModel):
    """The output schema of WBS extraction: the team and every activity of the project."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    team: tuple[TeamMember, ...]
    activities: tuple[ExtractedActivity, ...]


def normalise_name(text: str) -> str:
    """Name used for matching: NFKC, case-folded, every run of other characters one space."""
    return " ".join(re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", text).casefold()))


def normalise_role(text: str) -> str:
    """Role name used for matching: `normalise_name` with a plural last word made singular."""
    words = normalise_name(text).split()
    last = words[-1] if words else ""
    if len(last) > 3 and last.endswith("s") and not last.endswith("ss"):
        words[-1] = last[:-1]
    return " ".join(words)


@dataclass(frozen=True)
class Issue:
    """A problem of an answer, with the English message sent back in a repair round; a cycle
    lists the names along it, the first repeated at the end."""

    kind: IssueKind
    message: str
    activity: str | None = None
    cycle: tuple[str, ...] = ()


def validate_extraction(data: object) -> list[Issue]:
    """Issues of a parsed answer: missing or invalid fields of the schema first; if there are
    none, the model checks of `model_issues`. An empty list means `to_instance` succeeds."""
    try:
        extraction = Extraction.model_validate(data)
    except ValidationError as exc:
        return [_field_issue(error, data) for error in exc.errors()]
    return model_issues(extraction)


def model_issues(extraction: Extraction) -> list[Issue]:
    """Duplicate, negative or unknown roles, duplicate or unknown names, non-positive durations,
    crews above the team's capacity and dependency cycles (each cycle listed)."""
    issues: list[Issue] = []
    capacity: dict[str, int] = {}
    for member in extraction.team:
        key = normalise_role(member.role)
        if not key:
            issues.append(Issue("missing_field", "The team lists a role without a name."))
            continue
        if key in capacity:
            issues.append(
                Issue("duplicate_role", f'The team lists the role "{member.role}" more than once.')
            )
            continue
        if member.count < 0:
            issues.append(
                Issue(
                    "negative_count",
                    f'The team has a negative number of "{member.role}" ({member.count}).',
                )
            )
        capacity[key] = member.count
    spelled: dict[str, str] = {}
    occurrences: dict[str, int] = {}
    for activity in extraction.activities:
        key = normalise_name(activity.name)
        spelled.setdefault(key, activity.name)
        occurrences[key] = occurrences.get(key, 0) + 1
    if "" in occurrences:
        issues.append(Issue("missing_field", "An activity has no name."))
    for key, count in occurrences.items():
        if count > 1 and key:
            name = spelled[key]
            issues.append(
                Issue(
                    "duplicate_name",
                    f'The activity "{name}" appears {count} times; list every activity once.',
                    activity=name,
                )
            )
    for activity in extraction.activities:
        issues.extend(_activity_issues(activity, capacity, occurrences))
    issues.extend(_cycle_issues(extraction, spelled))
    return issues


def _activity_issues(
    activity: ExtractedActivity, capacity: Mapping[str, int], names: Mapping[str, int]
) -> list[Issue]:
    name = activity.name
    issues: list[Issue] = []
    if activity.duration_days <= 0:
        issues.append(
            Issue(
                "non_positive_duration",
                f'The activity "{name}" has duration {activity.duration_days}; a duration is a '
                "positive whole number of working days.",
                activity=name,
            )
        )
    seen: set[str] = set()
    for role, count in activity.crew.items():
        key = normalise_role(role)
        if key in seen:
            issues.append(
                Issue(
                    "duplicate_role",
                    f'The crew of "{name}" lists the role "{role}" more than once.',
                    activity=name,
                )
            )
            continue
        seen.add(key)
        if count < 0:
            issues.append(
                Issue(
                    "negative_count",
                    f'The activity "{name}" needs a negative number of "{role}" ({count}).',
                    activity=name,
                )
            )
        elif count > 0 and key not in capacity:
            issues.append(
                Issue(
                    "unknown_role",
                    f'The activity "{name}" needs the role "{role}", which is not in the team.',
                    activity=name,
                )
            )
        elif count > capacity.get(key, count):
            issues.append(
                Issue(
                    "crew_above_capacity",
                    f'The activity "{name}" needs {count} of the role "{role}", but the team '
                    f"has only {capacity[key]}.",
                    activity=name,
                )
            )
    for predecessor in activity.predecessors:
        if normalise_name(predecessor) not in names:
            issues.append(
                Issue(
                    "unknown_name",
                    f'The activity "{name}" lists the predecessor "{predecessor}", which is not '
                    "an activity of the project.",
                    activity=name,
                )
            )
    return issues


def _cycle_issues(extraction: Extraction, spelled: Mapping[str, str]) -> list[Issue]:
    """One issue per strongly connected component with a cycle (Tarjan 1972), listing a cycle."""
    order = list(spelled)
    successors: dict[str, list[str]] = {key: [] for key in order}
    for activity in extraction.activities:
        target = normalise_name(activity.name)
        for predecessor in activity.predecessors:
            source = normalise_name(predecessor)
            if source in successors and target not in successors[source]:
                successors[source].append(target)
    issues = []
    for component in _strong_components(order, successors):
        members = set(component)
        start = min(component, key=order.index)
        if len(component) == 1 and start not in successors[start]:
            continue
        cycle = [spelled[key] for key in _cycle_through(start, members, successors)]
        path = " -> ".join(f'"{name}"' for name in cycle)
        issues.append(
            Issue(
                "cycle",
                f"The dependencies form a cycle ({path}; A -> B means A must be finished before "
                "B starts).",
                activity=cycle[0],
                cycle=tuple(cycle),
            )
        )
    return issues


def _strong_components(
    order: Sequence[str], successors: Mapping[str, list[str]]
) -> list[list[str]]:
    """Strongly connected components in discovery order (iterative Tarjan 1972)."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[list[str]] = []
    for root in order:
        if root in index:
            continue
        work = [(root, 0)]
        while work:
            node, i = work.pop()
            if i == 0:
                index[node] = low[node] = len(index)
                stack.append(node)
                on_stack.add(node)
            recurse = False
            for k in range(i, len(successors[node])):
                succ = successors[node][k]
                if succ not in index:
                    work.append((node, k + 1))
                    work.append((succ, 0))
                    recurse = True
                    break
                if succ in on_stack:
                    low[node] = min(low[node], index[succ])
            if recurse:
                continue
            if low[node] == index[node]:
                component = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                components.append(component)
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
    return components


def _cycle_through(start: str, members: set[str], successors: Mapping[str, list[str]]) -> list[str]:
    """A shortest cycle start -> ... -> start inside a strongly connected component (BFS)."""
    parent: dict[str, str] = {}
    frontier = [start]
    while frontier:
        following = []
        for node in frontier:
            for succ in successors[node]:
                if succ not in members:
                    continue
                if succ == start:
                    path = [node]
                    while path[-1] != start:
                        path.append(parent[path[-1]])
                    return [*reversed(path), start]
                if succ not in parent:
                    parent[succ] = node
                    following.append(succ)
        frontier = following
    raise AssertionError(f"no cycle through {start!r} in its component")


def _field_issue(error: Mapping[str, Any], data: object) -> Issue:
    loc = tuple(error.get("loc", ()))
    if not loc:
        return Issue(
            "invalid_field",
            'The answer must be one JSON object with the fields "team" and "activities".',
        )
    path = "".join(f"[{part}]" if isinstance(part, int) else f".{part}" for part in loc)[
        1 if isinstance(loc[0], str) else 0 :
    ]
    activity = _activity_name_at(data, loc)
    where = f'In the activity "{activity}", the field' if activity else "The field"
    if error.get("type") == "missing":
        return Issue("missing_field", f'{where} "{path}" is missing.', activity=activity)
    message = str(error.get("msg", "is invalid"))
    return Issue("invalid_field", f'{where} "{path}" is invalid: {message}.', activity=activity)


def _activity_name_at(data: object, loc: Sequence[object]) -> str | None:
    if len(loc) < 2 or loc[0] != "activities" or not isinstance(loc[1], int):
        return None
    if not isinstance(data, Mapping):
        return None
    activities = data.get("activities")
    if not isinstance(activities, list) or not 0 <= loc[1] < len(activities):
        return None
    entry = activities[loc[1]]
    name = entry.get("name") if isinstance(entry, Mapping) else None
    return name if isinstance(name, str) and name.strip() else None


def to_instance(extraction: Extraction, *, name: str) -> ProjectInstance:
    """The extraction as a `ProjectInstance` (spec section 1): roles in team order, activities
    1..n in answer order, the dummy source before every activity without predecessors and the
    dummy sink after every activity without successors. Raises ValueError if it has issues."""
    issues = model_issues(extraction)
    if issues:
        raise ValueError(f"the extraction has {len(issues)} issues, first: {issues[0].message}")
    roles = tuple(
        Role(id=k, name=member.role, capacity=member.count)
        for k, member in enumerate(extraction.team)
    )
    role_of = {normalise_role(member.role): k for k, member in enumerate(extraction.team)}
    n = len(extraction.activities)
    sink = n + 1
    index = {normalise_name(a.name): j for j, a in enumerate(extraction.activities, start=1)}
    successors: list[set[int]] = [set() for _ in range(n + 2)]
    has_predecessor = [False] * (n + 2)
    for j, activity in enumerate(extraction.activities, start=1):
        for predecessor in activity.predecessors:
            successors[index[normalise_name(predecessor)]].add(j)
            has_predecessor[j] = True
    for j in range(1, n + 1):
        if not has_predecessor[j]:
            successors[0].add(j)
        if not successors[j]:
            successors[j].add(sink)
    if not successors[0]:
        successors[0].add(sink)
    nothing = (0,) * len(roles)
    activities = [
        Activity(id=0, duration=0, demands=nothing, successors=tuple(sorted(successors[0])))
    ]
    for j, activity in enumerate(extraction.activities, start=1):
        demands = [0] * len(roles)
        for role, count in activity.crew.items():
            if count:
                demands[role_of[normalise_role(role)]] = count
        activities.append(
            Activity(
                id=j,
                duration=activity.duration_days,
                demands=tuple(demands),
                successors=tuple(sorted(successors[j])),
                name=activity.name,
            )
        )
    activities.append(Activity(id=sink, duration=0, demands=nothing, successors=()))
    return ProjectInstance(
        name=name,
        activities=tuple(activities),
        roles=roles,
        workers=make_workers(roles),
        source="wbs-extraction",
    )


class ExtractionSettings(BaseModel):
    """Prompt version and decoding parameters of an extraction session."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt_version: str = Field(default="v1", min_length=1)
    max_tokens: PositiveInt
    temperature: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    max_repair_rounds: int = Field(default=3, ge=0)


@dataclass(frozen=True)
class Round:
    """One call of a session: round 0 is the single-shot call, round r >= 1 the r-th repair."""

    index: int
    response: LlmResponse[Extraction]
    issues: tuple[Issue, ...]

    @property
    def valid(self) -> bool:
        return not self.issues


@dataclass(frozen=True)
class Session:
    """The rounds of a repair session; its first round is the single-shot answer. `stopped`
    says why a session with issues ended before its last repair round (a repair request that
    cannot fit the backend's limits), else None."""

    rounds: tuple[Round, ...]
    stopped: str | None = None

    @property
    def single_shot(self) -> Round:
        return self.rounds[0]

    @property
    def final(self) -> Round:
        return self.rounds[-1]

    @property
    def repair_rounds(self) -> int:
        return len(self.rounds) - 1


def answer_issues(response: LlmResponse[Extraction]) -> list[Issue]:
    """Issues of an answer: unparseable or cut-off JSON as one issue, else `validate_extraction`."""
    error = response.error
    if error is not None and error.kind in ("empty", "json", "truncated"):
        if error.kind == "truncated":
            message = "The answer was cut off before the JSON object was complete."
        else:
            message = f"The answer is not valid JSON ({error.message})."
        return [Issue("invalid_json", f"{message} Return the complete JSON object only.")]
    return validate_extraction(response.parsed)


def extraction_messages(text: str, prompt: Prompt) -> list[Message]:
    """The single-shot conversation: the system prompt and the project description."""
    return [Message(role="system", content=prompt.text), Message(role="user", content=text)]


def repair_messages(
    text: str,
    previous: LlmResponse[Extraction],
    issues: Sequence[Issue],
    prompt: Prompt,
    repair_prompt: Prompt,
) -> list[Message]:
    """A repair round: the single-shot conversation, the previous answer (compact JSON if it
    parsed, else its text) and the issue list with the request for a corrected full JSON."""
    if previous.parsed is not None:
        answer = json.dumps(previous.parsed, ensure_ascii=False, separators=(",", ":"))
    else:
        answer = previous.text
    return [
        *extraction_messages(text, prompt),
        Message(role="assistant", content=answer),
        Message(role="user", content=repair_prompt.render(issues=format_issues(issues))),
    ]


def format_issues(issues: Sequence[Issue]) -> str:
    """One line `- <message>` per issue, at most MAX_LISTED_ISSUES and a line for the rest."""
    lines = [f"- {issue.message}" for issue in issues[:MAX_LISTED_ISSUES]]
    if len(issues) > MAX_LISTED_ISSUES:
        lines.append(f"- ... and {len(issues) - MAX_LISTED_ISSUES} more issues of these kinds.")
    return "\n".join(lines)


def single_shot(client: LlmClient, text: str, *, seed: int, settings: ExtractionSettings) -> Round:
    """One extraction call and the issues of its answer."""
    prompt = load_prompt(EXTRACT_PROMPT, settings.prompt_version)
    response = client.complete(
        extraction_messages(text, prompt),
        schema=Extraction,
        temperature=settings.temperature,
        seed=seed,
        max_tokens=settings.max_tokens,
    )
    return Round(0, response, tuple(answer_issues(response)))


def repair(client: LlmClient, text: str, *, seed: int, settings: ExtractionSettings) -> Session:
    """The single-shot call, then repair rounds while the answer has issues, at most
    `settings.max_repair_rounds`; every round uses the same seed."""
    prompt = load_prompt(EXTRACT_PROMPT, settings.prompt_version)
    repair_prompt = load_prompt(REPAIR_PROMPT, settings.prompt_version)
    rounds = [single_shot(client, text, seed=seed, settings=settings)]
    while rounds[-1].issues and len(rounds) <= settings.max_repair_rounds:
        last = rounds[-1]
        try:
            response = client.complete(
                repair_messages(text, last.response, last.issues, prompt, repair_prompt),
                schema=Extraction,
                temperature=settings.temperature,
                seed=seed,
                max_tokens=settings.max_tokens,
            )
        except RequestTooLarge as exc:
            return Session(tuple(rounds), stopped=f"request too large: {exc}")
        rounds.append(Round(len(rounds), response, tuple(answer_issues(response))))
    return Session(tuple(rounds))
