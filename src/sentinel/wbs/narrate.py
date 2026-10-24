"""Deterministic project descriptions of PSPLIB instances, the inputs of RQ1 (WP6a).

`narrate(instance, style=..., seed=...)` writes a software project's plan from an instance
without any LLM, so the instance is the exact ground truth of what an LLM extracts from the
text. Roles R1-R4 are the backend developer, frontend developer, tester and DevOps engineer.
Every real activity gets a unique name from a seeded vocabulary of its dominant role (most
people, ties to the lower role). The text states the team (people per role) and, for every
real activity, its name, duration in working days, crew per role and immediate predecessors by
name; the dummy source and sink are implicit. Each fact appears exactly once.

- `structured`: one block per activity in topological order, fixed phrasing, numbers in digits;
- `narrative`: prose paragraphs in a shuffled order with seeded phrasings; each dependency is
  stated once, either with the successor ("It can only start once A and B are done.") or with
  the predecessor ("It must be finished before C begins."); numbers are sometimes words.

The seed fixes the names, the same for both styles, and the narrative's choices.
`edge_phrasings` tells, per true precedence edge, how the text states it (on which side, the
number form of the stating block, the paragraph distance of the two activities; the RQ1 error
analysis, WP7). `parse_narration` reads both styles back by their templates (it recovers the
instance exactly and rejects a fact stated twice); it checks the narrator and serves as an
oracle.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np

from sentinel.model.instance import Activity, ProjectInstance
from sentinel.wbs.extract import ExtractedActivity, Extraction, TeamMember

Style = Literal["structured", "narrative"]
STYLES: tuple[Style, ...] = ("structured", "narrative")
EdgeSide = Literal["successor", "predecessor"]
NumberForm = Literal["digits", "words"]
ROLE_NAMES = ("backend developer", "frontend developer", "tester", "DevOps engineer")
WORDS_PROBABILITY = 0.5  # narrative: a number is written as words with this probability
SUCCESSOR_FORM_PROBABILITY = 0.5  # narrative: a dependency is stated with its successor
STRUCTURED_TITLE = "Project plan"
_NAMES_STREAM, _NARRATIVE_STREAM = 0, 1  # spawn keys of the seed's two random streams

# Verbs and objects per role; every verb fits every object of its role. No name contains a
# comma, "and", a digit or a period, so lists of quoted names read unambiguously.
VOCABULARY: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("Implement", "Build", "Design", "Refactor", "Extend", "Optimize"),
        (
            "payment API",
            "order service",
            "authentication service",
            "search backend",
            "notification service",
            "reporting module",
            "inventory service",
            "billing engine",
            "data import job",
            "caching layer",
            "invoice generator",
            "audit log",
            "recommendation engine",
            "session store",
            "rate limiter",
            "export service",
            "webhook handler",
            "pricing engine",
            "user database schema",
            "message queue consumer",
        ),
    ),
    (
        ("Build", "Design", "Implement", "Redesign", "Polish", "Prototype"),
        (
            "checkout page",
            "login screen",
            "product catalog view",
            "user profile page",
            "admin dashboard",
            "search results page",
            "shopping cart widget",
            "onboarding wizard",
            "settings panel",
            "order history view",
            "notification center",
            "landing page",
            "help center",
            "navigation menu",
            "invoice viewer",
            "report charts",
            "signup form",
            "contact form",
            "pricing page",
            "error pages",
        ),
    ),
    (
        ("Test", "Verify", "Validate", "Review", "Audit", "Check"),
        (
            "payment flow",
            "login flow",
            "checkout process",
            "search feature",
            "user registration",
            "order workflow",
            "invoice export",
            "notification delivery",
            "admin permissions",
            "data migration",
            "mobile layout",
            "API contracts",
            "release candidate",
            "security settings",
            "report accuracy",
            "password reset",
            "shopping cart",
            "accessibility",
            "performance budget",
            "error handling",
        ),
    ),
    (
        ("Set up", "Configure", "Automate", "Harden", "Upgrade", "Migrate"),
        (
            "CI pipeline",
            "staging environment",
            "production cluster",
            "database backups",
            "log aggregation",
            "container registry",
            "load balancer",
            "secrets vault",
            "alerting rules",
            "deployment scripts",
            "CDN cache",
            "DNS records",
            "TLS certificates",
            "test environment",
            "metrics dashboards",
            "disaster recovery",
            "build servers",
            "network firewall",
            "artifact storage",
            "autoscaling policies",
        ),
    ),
)

# Narrative templates. Placeholders: {N} the activity's quoted name, {D} its duration, {C} its
# crew, {L} a list of quoted names, {T} the team; {is}, {has} and {begins} agree with {L}.
_OPENINGS = (
    "This brief describes the work for the next release of our web platform.",
    "Here is the plan for the upcoming release of the customer portal.",
    "The following notes describe the work planned for the new online shop.",
    "This document outlines the tasks of the mobile banking project.",
)
_TEAM = (
    "The team consists of {T}.",
    "We have {T} on the team.",
    "Available staff: {T}.",
    "The project can draw on {T}.",
)
_FULL = (
    "{N} takes {D} and needs {C}.",
    "{N} is estimated at {D} and requires {C}.",
    "For {N} we plan {D} with {C}.",
    "The task {N} occupies {C} for {D}.",
    "{N} will keep {C} busy for {D}.",
    "We expect {N} to last {D}; it needs {C}.",
)
_NAME_DURATION = ("{N} takes {D}.", "There is also {N}, which lasts {D}.")
_CREW = ("It needs {C}.", "The work calls for {C}.", "It requires {C}.")
_AFTER = (
    "It can only start once {L} {is} done.",
    "It cannot begin until {L} {is} finished.",
    "Work on it starts after {L} {has} been completed.",
    "It depends on {L}.",
    "Before it can begin, {L} must be complete.",
    "{N} has to wait for {L}.",
)
_BEFORE = (
    "It must be finished before {L} {begins}.",
    "{L} cannot start until it is complete.",
    "Once it is done, {L} can start.",
    "Its completion is a prerequisite for {L}.",
    "{N} must be finished before {L} {begins}.",
)
_FIRST = (
    "It can start right away.",
    "It has no prerequisites.",
    "It can begin as soon as the project starts.",
)

_UNITS = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
_TENS = ["_", "_", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def number_words(n: int) -> str:
    """English words of 0 <= n <= 99, e.g. 59 -> "fifty-nine"."""
    if not 0 <= n <= 99:
        raise ValueError(f"number words cover 0..99, got {n}")
    if n < 20:
        return _UNITS[n]
    tens, units = divmod(n, 10)
    return _TENS[tens] if units == 0 else f"{_TENS[tens]}-{_UNITS[units]}"


_NUMBERS = {number_words(n): n for n in range(100)}


def parse_number(token: str) -> int:
    """Digits or the words of `number_words`."""
    if token.isdigit():
        return int(token)
    if token in _NUMBERS:
        return _NUMBERS[token]
    raise ValueError(f"not a number: {token!r}")


def role_names(instance: ProjectInstance) -> tuple[str, ...]:
    """The IT role names of the instance's roles R1..R|K| (at most four)."""
    if len(instance.roles) > len(ROLE_NAMES):
        raise ValueError(f"the narrator names {len(ROLE_NAMES)} roles, got {len(instance.roles)}")
    return ROLE_NAMES[: len(instance.roles)]


def dominant_role(activity: Activity) -> int:
    """The role with the most people in the activity's crew, ties to the lower role."""
    return max(range(len(activity.demands)), key=lambda k: (activity.demands[k], -k))


def activity_names(instance: ProjectInstance, seed: int) -> dict[int, str]:
    """Unique names of the real activities: verb and object of the dominant role's vocabulary.

    Objects of a role are drawn without replacement (a seeded permutation) and get a seeded
    verb; once a role's objects are used up, they come back with verbs not yet paired with
    them. Activities are named in id order.
    """
    role_names(instance)  # at most four roles, one vocabulary each
    rng = _stream(seed, _NAMES_STREAM)
    queues = [[objects[i] for i in rng.permutation(len(objects))] for _, objects in VOCABULARY]
    used: set[str] = set()
    names: dict[int, str] = {}
    for activity in instance.activities[1:-1]:
        k = dominant_role(activity) if activity.demands else 0
        verbs, objects = VOCABULARY[k]
        queue = queues[k]
        for _ in range(len(objects)):
            thing = queue.pop(0)
            queue.append(thing)
            free = [verb for verb in verbs if f"{verb} {thing}" not in used]
            if free:
                name = f"{free[int(rng.integers(len(free)))]} {thing}"
                break
        else:
            raise ValueError(f"the vocabulary of role {k} is exhausted")
        used.add(name)
        names[activity.id] = name
    return names


def truth(instance: ProjectInstance, seed: int) -> Extraction:
    """The instance in the extraction schema with the narrator's names: the team in role order,
    activities in id order, crews without zero entries, real predecessors in id order."""
    return _project(instance, activity_names(instance, seed))


def _project(instance: ProjectInstance, names: Mapping[int, str]) -> Extraction:
    roles = role_names(instance)
    real = set(names)
    return Extraction(
        team=tuple(TeamMember(role=roles[r.id], count=r.capacity) for r in instance.roles),
        activities=tuple(
            ExtractedActivity(
                name=names[a.id],
                duration_days=a.duration,
                crew={roles[k]: d for k, d in enumerate(a.demands) if d},
                predecessors=tuple(names[i] for i in instance.predecessors(a.id) if i in real),
            )
            for a in instance.activities[1:-1]
        ),
    )


@dataclass(frozen=True)
class EdgePhrasing:
    """How a description states the true edge `predecessor` -> `successor`: the side whose
    block states it, how that block writes its duration, and the number of paragraphs between
    the blocks of the two activities (structured: one paragraph per activity)."""

    predecessor: str
    successor: str
    side: EdgeSide
    numbers: NumberForm
    distance: int


def narrate(instance: ProjectInstance, *, style: Style, seed: int) -> str:
    """The project description of `instance` in `style`; the same seed gives the same text."""
    return _describe(instance, style, seed)[0]


def edge_phrasings(
    instance: ProjectInstance, *, style: Style, seed: int
) -> tuple[EdgePhrasing, ...]:
    """The phrasing of every true edge in the text `narrate` writes with the same arguments, in
    the order of the activities and their predecessors in `truth`."""
    return _describe(instance, style, seed)[1]


def _describe(
    instance: ProjectInstance, style: Style, seed: int
) -> tuple[str, tuple[EdgePhrasing, ...]]:
    names = activity_names(instance, seed)
    project = _project(instance, names)
    if style == "structured":
        by_name = {a.name: a for a in project.activities}
        topological = [by_name[names[j]] for j in instance.topological_order() if j in names]
        position = {activity.name: k for k, activity in enumerate(topological)}
        phrasings = tuple(
            EdgePhrasing(p, a.name, "successor", "digits", abs(position[a.name] - position[p]))
            for a in project.activities
            for p in a.predecessors
        )
        return _structured(project, topological), phrasings
    if style == "narrative":
        return _narrative(project, _stream(seed, _NARRATIVE_STREAM))
    raise ValueError(f"unknown style {style!r}; expected one of {STYLES}")


def _stream(seed: int, key: int) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence(seed, spawn_key=(key,)))


def _people(count: int, role: str) -> str:
    return f"{role}s" if count != 1 else role


def _structured(project: Extraction, activities: Sequence[ExtractedActivity]) -> str:
    lines = [STRUCTURED_TITLE, "", "Team (people per role):"]
    lines += [f"- {member.role}: {member.count}" for member in project.team]
    lines += ["", "Activities (durations in working days):"]
    roles = [member.role for member in project.team]
    for activity in activities:
        crew = ", ".join(
            f"{activity.crew[role]} {_people(activity.crew[role], role)}"
            for role in roles
            if role in activity.crew
        )
        predecessors = ", ".join(f'"{name}"' for name in activity.predecessors) or "none"
        lines += [
            "",
            f'Activity "{activity.name}"',
            f"- Duration: {activity.duration_days} working "
            f"{'day' if activity.duration_days == 1 else 'days'}",
            f"- Crew: {crew or 'nobody'}",
            f"- Predecessors: {predecessors}",
        ]
    return "\n".join(lines) + "\n"


def _narrative(
    project: Extraction, rng: np.random.Generator
) -> tuple[str, tuple[EdgePhrasing, ...]]:
    def say(n: int) -> str:
        return number_words(n) if n <= 99 and rng.random() < WORDS_PROBABILITY else str(n)

    def pick(options: Sequence[str]) -> str:
        return options[int(rng.integers(len(options)))]

    roles = [member.role for member in project.team]
    team = _join([f"{say(m.count)} {_people(m.count, m.role)}" for m in project.team])
    opening = f"{pick(_OPENINGS)} {pick(_TEAM).format(T=team)}"
    after: dict[str, list[str]] = {a.name: [] for a in project.activities}
    before: dict[str, list[str]] = {a.name: [] for a in project.activities}
    for activity in project.activities:
        for predecessor in activity.predecessors:
            if rng.random() < SUCCESSOR_FORM_PROBABILITY:
                after[activity.name].append(predecessor)
            else:
                before[predecessor].append(activity.name)
    blocks = []
    order: list[str] = []
    numbers: dict[str, NumberForm] = {}
    for index in rng.permutation(len(project.activities)):
        activity = project.activities[int(index)]
        name = f'"{activity.name}"'
        days = activity.duration_days
        duration = f"{say(days)} working {'day' if days == 1 else 'days'}"
        order.append(activity.name)
        numbers[activity.name] = "digits" if duration[0].isdigit() else "words"
        crew = (
            _join(
                [
                    f"{say(activity.crew[role])} {_people(activity.crew[role], role)}"
                    for role in roles
                    if role in activity.crew
                ]
            )
            or "nobody"
        )
        if rng.random() < 0.75:
            sentences = [pick(_FULL).format(N=name, D=duration, C=crew)]
        else:
            sentences = [
                pick(_NAME_DURATION).format(N=name, D=duration),
                pick(_CREW).format(C=crew),
            ]
        statements = []
        if not activity.predecessors:
            statements.append(pick(_FIRST))
        if after[activity.name]:
            statements.append(_dependency(pick(_AFTER), name, after[activity.name], rng))
        if before[activity.name]:
            statements.append(_dependency(pick(_BEFORE), name, before[activity.name], rng))
        sentences += [statements[int(i)] for i in rng.permutation(len(statements))]
        blocks.append(" ".join(sentences))
    paragraphs = [opening]
    paragraph: dict[str, int] = {}
    while blocks:
        size = 1 + int(rng.integers(3))
        for placed in order[:size]:
            paragraph[placed] = len(paragraphs)
        paragraphs.append(" ".join(blocks[:size]))
        blocks, order = blocks[size:], order[size:]
    phrasings = []
    for activity in project.activities:
        for predecessor in activity.predecessors:
            stated_after = predecessor in after[activity.name]
            phrasings.append(
                EdgePhrasing(
                    predecessor,
                    activity.name,
                    "successor" if stated_after else "predecessor",
                    numbers[activity.name if stated_after else predecessor],
                    abs(paragraph[activity.name] - paragraph[predecessor]),
                )
            )
    return "\n\n".join(paragraphs) + "\n", tuple(phrasings)


def _dependency(template: str, name: str, others: Sequence[str], rng: np.random.Generator) -> str:
    listed = [f'"{other}"' for other in (others[int(i)] for i in rng.permutation(len(others)))]
    many = len(listed) > 1
    sentence = template.format(
        N=name,
        L=_join(listed),
        **{"is": "are" if many else "is", "has": "have" if many else "has"},
        begins="begin" if many else "begins",
    )
    return sentence[0].upper() + sentence[1:]


def _join(items: Sequence[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} and {items[-1]}"


# --- Template parser -------------------------------------------------------------------------

_NAME = r'"([^"]+)"'
_LIST = r'("[^"]+"(?:(?:, | and )"[^"]+")*)'
_PLACEHOLDERS = {
    "N": r'"(?P<N>[^"]+)"',
    "D": r"(?P<D>[a-z]+(?:-[a-z]+)?|\d+) working days?",
    "C": r"(?P<C>[^\".;]+?)",
    "L": f"(?P<L>{_LIST})",
    "T": r"(?P<T>[^\".;]+?)",
    "is": "(?:is|are)",
    "has": "(?:has|have)",
    "begins": "(?:begins|begin)",
}


def _compile(template: str) -> re.Pattern[str]:
    parts = re.split(r"\{(\w+)\}", template)
    pattern = "".join(
        re.escape(part) if i % 2 == 0 else _PLACEHOLDERS[part] for i, part in enumerate(parts)
    )
    return re.compile(pattern)


_SENTENCES: tuple[tuple[str, re.Pattern[str]], ...] = (
    *(("opening", re.compile(re.escape(t))) for t in _OPENINGS),
    *(("team", _compile(t)) for t in _TEAM),
    *(("full", _compile(t)) for t in _FULL),
    *(("name_duration", _compile(t)) for t in _NAME_DURATION),
    *(("crew", _compile(t)) for t in _CREW),
    *(("after", _compile(t)) for t in _AFTER),
    *(("before", _compile(t)) for t in _BEFORE),
    *(("first", re.compile(re.escape(t))) for t in _FIRST),
)


class _Facts:
    """Facts read from a description; every fact may be set once."""

    def __init__(self) -> None:
        self.team: dict[str, int] = {}
        self.durations: dict[str, int] = {}
        self.crews: dict[str, dict[str, int]] = {}
        self.edges: set[tuple[str, str]] = set()
        self.first: set[str] = set()
        self.order: list[str] = []

    def add_team(self, phrase: str) -> None:
        if self.team:
            raise ValueError("the team is stated twice")
        self.team = _counts(phrase)

    def add_activity(self, name: str, duration: int) -> None:
        if name in self.durations:
            raise ValueError(f'the activity "{name}" is introduced twice')
        self.durations[name] = duration
        self.order.append(name)

    def add_crew(self, name: str, phrase: str) -> None:
        if name in self.crews:
            raise ValueError(f'the crew of "{name}" is stated twice')
        self.crews[name] = _counts(phrase) if phrase != "nobody" else {}

    def add_edge(self, before: str, after: str) -> None:
        if (before, after) in self.edges:
            raise ValueError(f'the dependency "{before}" -> "{after}" is stated twice')
        self.edges.add((before, after))

    def add_first(self, name: str) -> None:
        if name in self.first:
            raise ValueError(f'"{name}" is stated twice to have no predecessors')
        self.first.add(name)

    def extraction(self) -> Extraction:
        if not self.team:
            raise ValueError("the team is not stated")
        for name in self.order:
            if name not in self.crews:
                raise ValueError(f'the crew of "{name}" is not stated')
        predecessors: dict[str, list[str]] = {name: [] for name in self.order}
        for before, after in sorted(self.edges, key=lambda e: (self.order.index(e[1]), e[0])):
            if before not in predecessors or after not in predecessors:
                raise ValueError(
                    f'the dependency "{before}" -> "{after}" names an unknown activity'
                )
            predecessors[after].append(before)
        for name in self.order:
            if bool(predecessors[name]) == (name in self.first):
                raise ValueError(f'"{name}" must have predecessors or be stated to have none')
        return Extraction(
            team=tuple(TeamMember(role=role, count=count) for role, count in self.team.items()),
            activities=tuple(
                ExtractedActivity(
                    name=name,
                    duration_days=self.durations[name],
                    crew=self.crews[name],
                    predecessors=tuple(predecessors[name]),
                )
                for name in self.order
            ),
        )


def _counts(phrase: str) -> dict[str, int]:
    """`two backend developers, 1 tester and three testers` -> people per singular role."""
    counts: dict[str, int] = {}
    for item in re.split(r", | and ", phrase):
        number, _, role = item.strip().partition(" ")
        singular = _singular(role)
        if singular in counts:
            raise ValueError(f"the role {singular!r} is listed twice in {phrase!r}")
        counts[singular] = parse_number(number)
    return counts


def _singular(role: str) -> str:
    for name in ROLE_NAMES:
        if role in (name, f"{name}s"):
            return name
    raise ValueError(f"unknown role {role!r}")


def _names(listed: str) -> list[str]:
    return re.findall(_NAME, listed)


def parse_narration(text: str) -> Extraction:
    """Read a description of either style back into the extraction schema, by the narrator's
    templates. Raises ValueError for text outside the templates or for a fact stated twice."""
    if text.startswith(STRUCTURED_TITLE + "\n"):
        return _parse_structured(text)
    return _parse_narrative(text)


def _parse_structured(text: str) -> Extraction:
    facts = _Facts()
    team: list[str] = []
    current: str | None = None
    section = ""
    for line in text.splitlines()[1:]:
        if not line.strip():
            continue
        if line == "Team (people per role):":
            section = "team"
        elif line == "Activities (durations in working days):":
            section = "activities"
        elif section == "team" and (match := re.fullmatch(r"- (.+): (\d+)", line)):
            team.append(f"{match.group(2)} {match.group(1)}")
        elif section == "activities" and (match := re.fullmatch(f"Activity {_NAME}", line)):
            current = match.group(1)
        elif current and (match := re.fullmatch(r"- Duration: (\d+) working days?", line)):
            facts.add_activity(current, int(match.group(1)))
        elif current and (match := re.fullmatch(r"- Crew: (.+)", line)):
            facts.add_crew(current, match.group(1).replace(", ", " and "))
        elif current and line == "- Predecessors: none":
            facts.add_first(current)
        elif current and (match := re.fullmatch(f"- Predecessors: {_LIST}", line)):
            for before in _names(match.group(1)):
                facts.add_edge(before, current)
        else:
            raise ValueError(f"line outside the structured template: {line!r}")
    facts.add_team(" and ".join(team))
    return facts.extraction()


def _parse_narrative(text: str) -> Extraction:
    facts = _Facts()
    current: str | None = None
    paragraphs = text.strip().split("\n\n")
    sentences = [s for p in paragraphs for s in re.split(r"(?<=\.)\s+", p.strip())]
    for sentence in sentences:
        kind, match = _match(sentence)
        fields: Mapping[str, str | None] = match.groupdict()
        if kind == "opening":
            continue
        if kind == "team":
            facts.add_team(str(fields["T"]))
            continue
        named = fields.get("N")
        if kind in ("full", "name_duration"):
            current = str(named)
            facts.add_activity(current, parse_number(str(fields["D"])))
            if kind == "full":
                facts.add_crew(current, str(fields["C"]))
            continue
        if current is None or (named is not None and named != current):
            raise ValueError(f"the sentence does not refer to the current activity: {sentence!r}")
        if kind == "crew":
            facts.add_crew(current, str(fields["C"]))
        elif kind == "after":
            for before in _names(str(fields["L"])):
                facts.add_edge(before, current)
        elif kind == "before":
            for after in _names(str(fields["L"])):
                facts.add_edge(current, after)
        else:
            facts.add_first(current)
    return facts.extraction()


def _match(sentence: str) -> tuple[str, re.Match[str]]:
    found = [(kind, m) for kind, p in _SENTENCES if (m := p.fullmatch(sentence)) is not None]
    if len(found) != 1:
        raise ValueError(f"{len(found)} templates match the sentence {sentence!r}")
    return found[0]
