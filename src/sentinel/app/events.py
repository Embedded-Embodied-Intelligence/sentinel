"""The events of a project's log and its replay (spec section 11.5; ADR-0023).

A live project's log starts with `created` and holds `definition` changes, the `baseline` plan,
`checkin`s with their resolved effects, `recommendation`s (the decision record, the impacts and
an action applied automatically), `decision`s of the manager (with the action as approved, or
why it was discarded) and `explanation`s by an LLM. `replay` rebuilds the project and the state
of every recommendation from it without any solver call or rollout. A simulator project's log
holds its `simulator` spec and the days it was advanced (`advance`).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict

from sentinel.app.live import AppliedAction, Baseline, CheckinEffects, LiveProject
from sentinel.app.models import CheckIn, ProjectDefinition
from sentinel.app.planning import Recommendation
from sentinel.app.store import EventRow

Source = Literal["new", "csv", "json", "text", "showcase"]
Verdict = Literal["approve", "reject", "later"]
RecommendationStatus = Literal[
    "none", "auto", "open", "later", "approved", "rejected", "discarded", "superseded"
]
OPEN: tuple[RecommendationStatus, ...] = ("open", "later")


class _Event(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Created(_Event):
    definition: ProjectDefinition
    source: Source = "new"


class DefinitionChanged(_Event):
    definition: ProjectDefinition


class BaselineSet(_Event):
    baseline: Baseline


class CheckinDone(_Event):
    checkin: CheckIn
    effects: CheckinEffects


class Recommended(_Event):
    recommendation: Recommendation
    applied: AppliedAction | None = None


class Decided(_Event):
    recommendation: int
    verdict: Verdict
    applied: AppliedAction | None = None
    discarded: str | None = None


class FactCheck(_Event):
    kind: str
    correct: bool


class LlmExplanation(_Event):
    """An LLM explanation of a recommendation (spec section 10.4) with its faithfulness check;
    `text` is empty and `error` set if the answer was not valid."""

    text: str
    model: str
    valid: bool
    facts: tuple[FactCheck, ...] = ()
    chosen_named: bool = False
    component_right: bool = False
    hallucinated: int = 0
    error: str | None = None

    @property
    def fully_faithful(self) -> bool:
        return (
            self.valid
            and all(f.correct for f in self.facts)
            and self.chosen_named
            and self.component_right
            and self.hallucinated == 0
        )


class Explained(_Event):
    recommendation: int
    explanation: LlmExplanation


EVENTS: dict[str, type[_Event]] = {
    "created": Created,
    "definition": DefinitionChanged,
    "baseline": BaselineSet,
    "checkin": CheckinDone,
    "recommendation": Recommended,
    "decision": Decided,
    "explanation": Explained,
}


@dataclass
class RecommendationEntry:
    """A recommendation of the log and what became of it."""

    seq: int
    recommendation: Recommendation
    status: RecommendationStatus
    applied: AppliedAction | None = None
    discarded: str | None = None
    explanation: LlmExplanation | None = None


@dataclass
class LiveState:
    """A live project rebuilt from its log: the project, its recommendations, how it was
    created and the sequence number of its last event."""

    project: LiveProject
    source: Source
    seq: int
    recommendations: list[RecommendationEntry] = field(default_factory=list)

    def recommendation(self, seq: int) -> RecommendationEntry | None:
        return next((r for r in self.recommendations if r.seq == seq), None)

    @property
    def open(self) -> RecommendationEntry | None:
        """The recommendation that waits for the manager, if any."""
        return next((r for r in reversed(self.recommendations) if r.status in OPEN), None)

    @property
    def latest(self) -> RecommendationEntry | None:
        return self.recommendations[-1] if self.recommendations else None


def parse(row: EventRow) -> _Event:
    kind = EVENTS.get(row.type)
    if kind is None:
        raise ValueError(f"unknown event type {row.type!r} at {row.seq}")
    return kind.model_validate(row.payload)


def replay(rows: Sequence[EventRow]) -> LiveState:
    """The live project of an event log (spec section 11.5)."""
    if not rows or rows[0].type != "created":
        raise ValueError("a live project's log starts with a 'created' event")
    first = Created.model_validate(rows[0].payload)
    state = LiveState(LiveProject(first.definition), first.source, rows[0].seq)
    for row in rows[1:]:
        apply(state, row.seq, parse(row))
    return state


def apply(state: LiveState, seq: int, event: _Event) -> None:
    """Apply one event to a live state."""
    project = state.project
    match event:
        case DefinitionChanged():
            project.set_definition(event.definition)
        case BaselineSet():
            project.set_baseline(event.baseline)
        case CheckinDone():
            project.apply_checkin(event.effects)
            _supersede(state)
        case Recommended():
            _supersede(state)
            if event.applied is not None:
                project.apply_action(event.applied)
                status: RecommendationStatus = "auto"
            elif event.recommendation.acts:
                status = "open"
            else:
                status = "none"
            entry = RecommendationEntry(seq, event.recommendation, status, event.applied)
            state.recommendations.append(entry)
        case Decided():
            found = state.recommendation(event.recommendation)
            if found is None:
                raise ValueError(f"decision on unknown recommendation {event.recommendation}")
            if event.verdict == "approve":
                if event.applied is not None:
                    project.apply_action(event.applied)
                    found.status, found.applied = "approved", event.applied
                else:
                    found.status, found.discarded = "discarded", event.discarded
            elif event.verdict == "reject":
                found.status = "rejected"
            else:
                found.status = "later"
        case Explained():
            found = state.recommendation(event.recommendation)
            if found is not None:
                found.explanation = event.explanation
        case _:
            raise ValueError(f"unexpected event {type(event).__name__} in a live project")
    state.seq = seq


def _supersede(state: LiveState) -> None:
    """A newer check-in or recommendation replaces the open ones (spec section 11.5)."""
    for entry in state.recommendations:
        if entry.status in OPEN:
            entry.status = "superseded"
