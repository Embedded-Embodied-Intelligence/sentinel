"""Scores of an extracted project model against the instance it describes (RQ1, WP6a).

An answer is read leniently: each team entry and each activity entry that validates on its own
counts, the others are unmatched. Extracted activities match true ones one to one by
normalised name, the first entry of a name winning; unmatched names are reported. On the
matched activities the scores are the precedence edges (precision, recall, F1), durations and
crews (exact); a rate over no edges is 1 only if the true project has no edges at all, so an
answer that matches nothing scores 0. The team is scored per true role. An answer is **exact**
if it is valid and isomorphic to the truth under the name matching: every activity matched,
every duration, crew and edge equal and the team the same. Downstream, a valid answer's
instance and the true one are solved by CP-SAT with the same settings; every schedule is
checked with `validate_schedule`.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, PositiveInt, ValidationError

from sentinel.model import ProjectInstance, validate_schedule
from sentinel.scheduling.cpsat import solve_cpsat
from sentinel.wbs.extract import (
    ExtractedActivity,
    Extraction,
    Issue,
    TeamMember,
    normalise_name,
    normalise_role,
)


@dataclass(frozen=True)
class Reading:
    """What an answer states: people per normalised role (first entry of a role) and its
    activity entries in order, None for an entry that does not validate."""

    team: dict[str, int]
    activities: tuple[ExtractedActivity | None, ...]


def read_answer(answer: object) -> Reading:
    """The lenient reading of a parsed answer (anything that is not an object reads as empty)."""
    if not isinstance(answer, Mapping):
        return Reading({}, ())
    team: dict[str, int] = {}
    members = answer.get("team")
    for entry in members if isinstance(members, list) else []:
        try:
            member = TeamMember.model_validate(entry)
        except ValidationError:
            continue
        team.setdefault(normalise_role(member.role), member.count)
    activities: list[ExtractedActivity | None] = []
    entries = answer.get("activities")
    for entry in entries if isinstance(entries, list) else []:
        try:
            activities.append(ExtractedActivity.model_validate(entry))
        except ValidationError:
            activities.append(None)
    return Reading(team, tuple(activities))


@dataclass(frozen=True)
class Scores:
    """Counts behind every RQ1 metric of one answer; the rates are properties."""

    valid: bool
    n_issues: int
    n_true: int
    n_extracted: int
    n_matched: int
    unmatched_true: tuple[str, ...]
    unmatched_extracted: tuple[str, ...]
    all_true_edges: int
    true_edges: int
    extracted_edges: int
    correct_edges: int
    durations_correct: int
    crews_correct: int
    team_roles: int
    team_correct: int
    team_exact: bool
    exact: bool

    @property
    def activity_recall(self) -> float:
        return _ratio(self.n_matched, self.n_true, empty=1.0)

    @property
    def activity_precision(self) -> float:
        return _ratio(self.n_matched, self.n_extracted, empty=1.0 if not self.n_true else 0.0)

    @property
    def edge_precision(self) -> float:
        return _ratio(self.correct_edges, self.extracted_edges, empty=self._no_edges)

    @property
    def edge_recall(self) -> float:
        return _ratio(self.correct_edges, self.true_edges, empty=self._no_edges)

    @property
    def _no_edges(self) -> float:
        """A rate over no edges: 1 if the project has none and none were claimed, else 0."""
        return 1.0 if self.all_true_edges == 0 and self.extracted_edges == 0 else 0.0

    @property
    def edge_f1(self) -> float:
        p, r = self.edge_precision, self.edge_recall
        return 2 * p * r / (p + r) if p + r > 0 else 0.0

    @property
    def duration_accuracy(self) -> float:
        return _ratio(self.durations_correct, self.n_matched, empty=math.nan)

    @property
    def crew_accuracy(self) -> float:
        return _ratio(self.crews_correct, self.n_matched, empty=math.nan)

    @property
    def team_accuracy(self) -> float:
        return _ratio(self.team_correct, self.team_roles, empty=1.0)


def _ratio(numerator: int, denominator: int, *, empty: float) -> float:
    return numerator / denominator if denominator else empty


def match_activities(
    reading: Reading, truth: Extraction
) -> tuple[dict[str, ExtractedActivity], list[str]]:
    """The answer's entries matched one to one to true activities by normalised name (the
    first entry of a name wins) and the unmatched entries' names."""
    true_names = {normalise_name(a.name) for a in truth.activities}
    matched: dict[str, ExtractedActivity] = {}
    unmatched: list[str] = []
    for position, entry in enumerate(reading.activities):
        if entry is None:
            unmatched.append(f"#{position} (invalid entry)")
            continue
        key = normalise_name(entry.name)
        if key in true_names and key not in matched:
            matched[key] = entry
        else:
            unmatched.append(entry.name)
    return matched, unmatched


def stated_edges(matched: Mapping[str, ExtractedActivity]) -> set[tuple[str, str]]:
    """The precedence edges an answer states between matched activities, by normalised name."""
    return {
        (normalise_name(p), key)
        for key, entry in matched.items()
        for p in entry.predecessors
        if normalise_name(p) in matched
    }


def score(answer: object, truth: Extraction, issues: Sequence[Issue]) -> Scores:
    """Scores of a parsed answer (None if it did not parse) with its validation issues."""
    reading = read_answer(answer)
    true_by_name = {normalise_name(a.name): a for a in truth.activities}
    matched, unmatched_extracted = match_activities(reading, truth)
    true_edges = {
        (normalise_name(p), normalise_name(a.name))
        for a in truth.activities
        for p in a.predecessors
        if normalise_name(a.name) in matched and normalise_name(p) in matched
    }
    extracted_edges = stated_edges(matched)
    durations = sum(e.duration_days == true_by_name[k].duration_days for k, e in matched.items())
    crews = sum(_crew(e.crew) == _crew(true_by_name[k].crew) for k, e in matched.items())
    true_team = {normalise_role(member.role): member.count for member in truth.team}
    team_correct = sum(reading.team.get(role) == count for role, count in true_team.items())
    team_exact = team_correct == len(true_team) and all(
        count == 0 for role, count in reading.team.items() if role not in true_team
    )
    n_true = len(truth.activities)
    all_edges = sum(len(a.predecessors) for a in truth.activities)
    exact = (
        not issues
        and len(matched) == n_true == len(reading.activities)
        and true_edges == extracted_edges
        and len(true_edges) == all_edges
        and durations == crews == n_true
        and team_exact
    )
    return Scores(
        valid=not issues,
        n_issues=len(issues),
        n_true=n_true,
        n_extracted=len(reading.activities),
        n_matched=len(matched),
        unmatched_true=tuple(
            a.name for a in truth.activities if normalise_name(a.name) not in matched
        ),
        unmatched_extracted=tuple(unmatched_extracted),
        all_true_edges=all_edges,
        true_edges=len(true_edges),
        extracted_edges=len(extracted_edges),
        correct_edges=len(true_edges & extracted_edges),
        durations_correct=durations,
        crews_correct=crews,
        team_roles=len(true_team),
        team_correct=team_correct,
        team_exact=team_exact,
        exact=exact,
    )


def _crew(crew: Mapping[str, int]) -> dict[str, int]:
    return {normalise_role(role): count for role, count in crew.items() if count}


class CpsatSettings(BaseModel):
    """CP-SAT for the downstream makespans: one worker, a seed and a deterministic limit (the
    `cpsat_det` settings of WP2b), so a solve is reproducible whatever the machine load."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    deterministic_time_limit: PositiveFloat = 5.0
    time_limit_s: PositiveFloat = 600.0
    random_seed: int = Field(default=2026, ge=0)
    num_workers: PositiveInt = 1


@dataclass(frozen=True)
class Makespan:
    """A CP-SAT makespan, its status (OPTIMAL or FEASIBLE) and its wall time."""

    makespan: int
    status: str
    wall_time_s: float


class InvalidScheduleError(RuntimeError):
    """CP-SAT returned a schedule that violates spec section 1.3."""


def cpsat_makespan(instance: ProjectInstance, settings: CpsatSettings) -> Makespan:
    """Solve the instance with CP-SAT and check the schedule (CLAUDE.md invariant 6)."""
    result = solve_cpsat(
        instance,
        time_limit_s=settings.time_limit_s,
        num_workers=settings.num_workers,
        random_seed=settings.random_seed,
        deterministic_time_limit=settings.deterministic_time_limit,
    )
    if result.schedule is None or result.makespan is None:
        raise RuntimeError(f"CP-SAT found no schedule for {instance.name} ({result.status})")
    violations = validate_schedule(instance, result.schedule)
    if violations:
        raise InvalidScheduleError(
            f"{instance.name}: {len(violations)} violations, first: {violations[0].detail}"
        )
    return Makespan(result.makespan, result.status, round(result.wall_time_s, 3))


def makespan_error(extracted: int, true: int) -> float:
    """Relative error (C_extracted - C_true) / C_true of a downstream makespan."""
    if true <= 0:
        raise ValueError(f"the true makespan must be positive, got {true}")
    return (extracted - true) / true
