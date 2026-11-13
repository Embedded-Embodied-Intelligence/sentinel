"""The events of a project's log and its replay (spec section 11.5; ADR-0023).

A live project's log starts with `created` and holds `definition` changes, the `baseline` plan,
`checkin`s with their resolved effects, `recommendation`s (the decision record, the impacts and
an action applied automatically), `decision`s of the manager (with the action as approved, or
why it was discarded), the `undo` of an automatic plan change (the planned starts restored) and
`explanation`s by an LLM. `replay` rebuilds the project and the state
of every recommendation from it without any solver call or rollout. A simulator project's log
holds its `simulator` spec and the days it was advanced (`advance`).
"""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from sentinel.app.live import AppliedAction, Baseline, CheckinEffects, LiveProject
from sentinel.app.models import CheckIn, ProjectDefinition
from sentinel.app.planning import Recommendation
from sentinel.app.store import EventRow

Source = Literal["new", "csv", "json", "text", "showcase"]
Verdict = Literal["approve", "reject", "later"]
RejectReason = Literal["too_expensive", "unavailable", "no_budget", "other"]
RecommendationStatus = Literal[
    "none",
    "auto",
    "open",
    "later",
    "approved",
    "rejected",
    "discarded",
    "superseded",
    "undone",
    "expired",
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


class Brief(_Event):
    """A decision as the manager saw it (spec section 11.8): the chance, the most likely finish
    (a makespan) and the expected cost without and with the action, its validity day and its
    cost of delay per day; stored with the decision on it."""

    p_before: float
    p_after: float
    finish_before: int | None = None
    finish_after: int | None = None
    cost_before: float
    cost_after: float
    valid_day: int | None = None
    delay: float | None = None


class Assessment(BaseModel):
    """ "Twoja ocena" (spec section 11.8, WP19): the action the manager chose before seeing the
    recommendation (an action label of its comparison, "NOOP" for no change; None: skipped)
    and Sentinel's choice it was then shown."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    choice: str | None = Field(default=None, max_length=200)
    sentinel: str = Field(max_length=200)

    @property
    def agrees(self) -> bool | None:
        """Whether the manager chose as Sentinel did; None when the step was skipped."""
        return None if self.choice is None else self.choice == self.sentinel


class Decided(_Event):
    """The manager's decision on a recommendation; a rejection may give one of the reasons of
    the v2 interface and, for "other", the manager's own words (WP15); the manager's own choice
    made first, if the decision page asked for it (WP19)."""

    recommendation: int
    verdict: Verdict
    applied: AppliedAction | None = None
    discarded: str | None = None
    reason: RejectReason | None = None
    note: str | None = Field(default=None, max_length=300)
    brief: Brief | None = None
    assessment: Assessment | None = None


class Corrected(_Event):
    """A correction of a pending recommendation by the manager (spec section 11.8): the
    recommendation with the corrected action as its choice, and the option chosen."""

    recommendation: int
    replacement: Recommendation
    option: str


class Validity(_Event):
    """The validity of a pending recommendation (spec section 11.8), computed by Sentinel: the
    chance with the action applied 0, 1, ... days later on the forecast's worlds, NOOP's, the
    last day it still helps (None: it never gained enough) and the chance lost per day."""

    recommendation: int
    label: str  # the action evaluated: a validity of an action since corrected is ignored
    chances: tuple[float, ...]
    noop: float
    valid_day: int | None
    delay: float | None


class Expired(_Event):
    """A pending recommendation whose validity date passed (spec section 11.8)."""

    recommendation: int


class Undone(_Event):
    """The undo of an automatic plan change (spec section 11.5): the planned starts it changed
    and the sink's, with their values before it."""

    recommendation: int
    plan: dict[str, int]
    sink_plan: int


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
    "undo": Undone,
    "correction": Corrected,
    "validity": Validity,
    "expiry": Expired,
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
    corrected: bool = False  # the manager changed its parameter (spec section 11.8)
    validity: Validity | None = None


@dataclass
class LiveState:
    """A live project rebuilt from its log: the project, its recommendations, how it was
    created, the sequence number of its last event, of its last event that changed the project
    (every event but an explanation) and of its last event that can change a forecast (without a
    recommendation or a decision that applied nothing either). `fingerprint` and
    `forecast_fingerprint` identify the contents of the log up to those two events, so two
    projects with the same log (every demo visitor's copy of the showcase) share their
    deterministic forecasts (WP17)."""

    project: LiveProject
    source: Source
    seq: int
    recommendations: list[RecommendationEntry] = field(default_factory=list)
    last_change: int = 0
    last_forecast_change: int = 0
    fingerprint: str = ""
    forecast_fingerprint: str = ""

    def recommendation(self, seq: int) -> RecommendationEntry | None:
        return next((r for r in self.recommendations if r.seq == seq), None)

    @property
    def open(self) -> RecommendationEntry | None:
        """The recommendation that waits for the manager, if any."""
        return next((r for r in reversed(self.recommendations) if r.status in OPEN), None)

    def open_seq(self) -> int | None:
        found = self.open
        return None if found is None else found.seq

    @property
    def latest(self) -> RecommendationEntry | None:
        return self.recommendations[-1] if self.recommendations else None

    def can_undo(self, entry: RecommendationEntry) -> bool:
        """Whether an automatic action can be undone (spec section 11.5): it changed only the
        plan and nothing but explanations came after it."""
        action = entry.applied
        return (
            entry.status == "auto"
            and action is not None
            and entry.seq == self.last_change
            and not (action.crews or action.temps or action.handovers or action.removed)
        )


def parse(row: EventRow) -> _Event:
    kind = EVENTS.get(row.type)
    if kind is None:
        raise ValueError(f"unknown event type {row.type!r} at {row.seq}")
    return kind.model_validate(stored_calendar(row.payload))


def stored_calendar(payload: dict[str, Any]) -> dict[str, Any]:
    """A definition stored before v2.2.0 has no holidays in its settings: its days were counted
    Monday to Friday, so it keeps that calendar (spec section 11.1) instead of the default."""
    definition = payload.get("definition")
    if not isinstance(definition, dict):
        return payload
    settings = definition.get("settings", {})
    if not isinstance(settings, dict) or "holidays" in settings:
        return payload
    settings = {**settings, "holidays": "none"}
    return {**payload, "definition": {**definition, "settings": settings}}


def replay(rows: Sequence[EventRow]) -> LiveState:
    """The live project of an event log (spec section 11.5)."""
    if not rows or rows[0].type != "created":
        raise ValueError("a live project's log starts with a 'created' event")
    first = Created.model_validate(rows[0].payload)
    state = LiveState(LiveProject(first.definition), first.source, rows[0].seq)
    state.last_change = state.last_forecast_change = rows[0].seq
    state.fingerprint = state.forecast_fingerprint = _digest("", rows[0])
    for row in rows[1:]:
        apply(state, row.seq, parse(row))
        if state.last_change == row.seq:
            state.fingerprint = _digest(state.fingerprint, row)
        if state.last_forecast_change == row.seq:
            state.forecast_fingerprint = state.fingerprint
    return state


def _digest(before: str, row: EventRow) -> str:
    """The fingerprint of a log after `row`: its type and payload, not its ids or times."""
    text = json.dumps(row.payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(f"{before}|{row.type}|{text}".encode()).hexdigest()


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
        case Undone():
            found = state.recommendation(event.recommendation)
            if found is None or found.applied is None:
                raise ValueError(f"undo of unknown action {event.recommendation}")
            for key, start in event.plan.items():
                project.tasks[key].planned = start
            project.sink_plan = event.sink_plan
            project.actions = [a for a in project.actions if a is not found.applied]
            found.status = "undone"
        case Explained():
            found = state.recommendation(event.recommendation)
            if found is not None:
                found.explanation = event.explanation
            state.seq = seq
            return
        case Corrected() | Validity() | Expired():
            # The v2 lifecycle (spec section 11.8): none of them changes the project.
            found = state.recommendation(event.recommendation)
            if found is None:
                raise ValueError(f"{type(event).__name__} of unknown recommendation")
            if isinstance(event, Corrected):
                found.recommendation, found.corrected, found.validity = (
                    event.replacement,
                    True,
                    None,
                )
            elif isinstance(event, Validity):
                if event.label == found.recommendation.record.chosen:
                    found.validity = event
            elif found.status in OPEN:
                found.status = "expired"
            state.seq = seq
            return
        case _:
            raise ValueError(f"unexpected event {type(event).__name__} in a live project")
    state.seq = state.last_change = seq
    if not isinstance(event, Recommended | Decided) or event.applied is not None:
        state.last_forecast_change = seq


def _supersede(state: LiveState) -> None:
    """A newer check-in or recommendation replaces the open ones (spec section 11.5)."""
    for entry in state.recommendations:
        if entry.status in OPEN:
            entry.status = "superseded"
