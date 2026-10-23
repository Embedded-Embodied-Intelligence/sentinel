"""Candidate actions proposed in a fixed JSON grammar, role 2 of the interpretation layer
(spec section 10.3; RQ5).

An answer holds up to three proposals of up to three operations each: SHIFT, RESEQ with the
objective makespan or stable, SUBST of an activity and OVERTIME of a role (`ProposalAnswer`).
`read_proposals` reads an answer proposal by proposal. `compile_proposal` turns one proposal
into a `Candidate` with the WP5 builders, or into an `ActionIssue`: its operations other than
SHIFT and RESEQ apply in the order given, each validated through the engine on the state the
previous ones leave, a SUBST choosing its substitutes there as AlwaysSubstitute would; the plan
operation is then planned on the state they leave (`prepare`: CP-SAT plans for RESEQ on the
planning view with the temporary workers), whatever its place in the list. `Compiler` compiles
the proposals of one state and flags those with the effect of a rule candidate or of an earlier
proposal as duplicates. `random_proposals` is the control source: proposals drawn uniformly
from the grammar over the operations valid in the state.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, PositiveInt, ValidationError

from sentinel.agent.candidates import (
    Candidate,
    CandidateKind,
    PlanCache,
    effect,
    prepare,
    single_substitutions,
    timed_activities,
)
from sentinel.agent.params import SentinelParams
from sentinel.llm import LlmClient, LlmResponse, Message, Prompt, load_prompt
from sentinel.policies.base import Decision, Operation, Overtime, Subst
from sentinel.simulation.engine import rehearse
from sentinel.simulation.state import Observation, overtime_cap
from sentinel.wbs.extract import normalise_role
from sentinel.wbs.narrate import role_names

PROPOSALS_PROMPT = "proposals"  # system prompt, prompts/proposals.<version>.txt
MAX_PROPOSALS = 3
MAX_OPERATIONS = 3
MAX_OVERTIME_DAYS = 20  # H of a proposed OVERTIME: 1..20 days (spec section 10.3)
ActionIssueKind = Literal[
    "invalid_json",
    "invalid_answer",
    "invalid_proposal",
    "too_many_proposals",
    "two_plan_operations",
    "unknown_role",
    "unknown_activity",
    "out_of_range",
    "not_eligible",
    "repeated_operation",
    "rejected",
]
ACTION_ISSUE_KINDS: tuple[ActionIssueKind, ...] = (
    "invalid_json",
    "invalid_answer",
    "invalid_proposal",
    "too_many_proposals",
    "two_plan_operations",
    "unknown_role",
    "unknown_activity",
    "out_of_range",
    "not_eligible",
    "repeated_operation",
    "rejected",
)


class ShiftOp(BaseModel):
    """SHIFT: the order-preserving repair (spec section 4)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    op: Literal["SHIFT"]


class ReseqOp(BaseModel):
    """RESEQ for minimum residual makespan, or for minimum deviation within SHIFT's makespan."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    op: Literal["RESEQ"]
    objective: Literal["makespan", "stable"]


class SubstOp(BaseModel):
    """SUBST of every absent member of the activity that an idle worker can replace."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    op: Literal["SUBST"]
    activity: int


class OvertimeOp(BaseModel):
    """OVERTIME: `workers` temporary workers of the role named `role` for `days` days."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    op: Literal["OVERTIME"]
    role: str
    workers: int
    days: int


GrammarOp = ShiftOp | ReseqOp | SubstOp | OvertimeOp


class Proposal(BaseModel):
    """One proposed action: one to three operations."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    operations: tuple[ShiftOp | ReseqOp | SubstOp | OvertimeOp, ...] = Field(
        min_length=1, max_length=MAX_OPERATIONS
    )


class ProposalAnswer(BaseModel):
    """The output schema of a proposal call: at most three proposals."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    proposals: tuple[Proposal, ...] = Field(max_length=MAX_PROPOSALS)


@dataclass(frozen=True)
class ActionIssue:
    """Why an answer or a proposal yields no candidate."""

    kind: ActionIssueKind
    message: str


def read_proposals(data: object) -> list[Proposal | ActionIssue]:
    """The proposals of a parsed answer, each read on its own: a `Proposal`, or an
    `ActionIssue` for an entry that does not fit the grammar or comes after the third; an answer
    without a "proposals" list gives a single issue."""
    if not isinstance(data, dict) or not isinstance(data.get("proposals"), list):
        return [ActionIssue("invalid_answer", 'the answer has no list "proposals"')]
    found: list[Proposal | ActionIssue] = []
    for index, entry in enumerate(data["proposals"]):
        if index >= MAX_PROPOSALS:
            found.append(ActionIssue("too_many_proposals", f"proposal {index} is beyond the third"))
            continue
        try:
            found.append(Proposal.model_validate(entry))
        except ValidationError as exc:
            found.append(
                ActionIssue("invalid_proposal", f"proposal {index}: {exc.error_count()} errors")
            )
    return found


def proposal_text(proposal: Proposal) -> str:
    """A compact label of a proposal in compiled order, the plan operation last, e.g.
    "SUBST(12)+OT(tester,1,10)+RESEQ-M"."""
    parts: list[str] = []
    plan: list[str] = []
    for op in proposal.operations:
        match op:
            case ShiftOp():
                plan.append("SHIFT")
            case ReseqOp(objective=objective):
                plan.append("RESEQ-M" if objective == "makespan" else "RESEQ-S")
            case SubstOp(activity=j):
                parts.append(f"SUBST({j})")
            case OvertimeOp():
                parts.append(f"OT({op.role},{op.workers},{op.days})")
    return "+".join([*parts, *plan])


def _plan_kind(proposal: Proposal) -> CandidateKind | ActionIssue:
    plans = [op for op in proposal.operations if isinstance(op, ShiftOp | ReseqOp)]
    if len(plans) > 1:
        return ActionIssue(
            "two_plan_operations", "a proposal may have one SHIFT or RESEQ, it has more"
        )
    if not plans:
        return "proposal"
    match plans[0]:
        case ShiftOp():
            return "proposal_shift"
        case ReseqOp(objective="makespan"):
            return "proposal_reseq_m"
    return "proposal_reseq_s"


def compile_proposal(
    proposal: Proposal,
    observation: Observation,
    params: SentinelParams,
    *,
    label: str,
    plans: PlanCache | None = None,
) -> Candidate | ActionIssue:
    """The candidate of a proposal on the observed state (spec section 10.3), or why there is
    none: two plan operations, an activity that is not real, an ineligible or repeated SUBST,
    an unknown role, OVERTIME outside 1..floor(gamma R_k) workers or 1..20 days, or an operation
    the engine would reject (`rehearse`, then `prepare` for the plan operation)."""
    kind = _plan_kind(proposal)
    if isinstance(kind, ActionIssue):
        return kind
    instance = observation.instance
    roles = role_names(instance)
    by_role = {normalise_role(role): k for k, role in enumerate(roles)}
    operations: list[Operation] = []
    current = observation
    substituted: set[int] = set()
    for op in proposal.operations:
        engine_op: Subst | Overtime
        match op:
            case ShiftOp() | ReseqOp():
                continue
            case SubstOp(activity=j):
                if not 0 < j < len(current.status) or j == instance.sink_id:
                    return ActionIssue("unknown_activity", f"activity {j} does not exist")
                if j in substituted:
                    return ActionIssue("repeated_operation", f"SUBST({j}) appears twice")
                substituted.add(j)
                found = next((s for s in single_substitutions(current) if s.activity == j), None)
                if found is None:
                    return ActionIssue(
                        "not_eligible",
                        f"activity {j} is not paused or running with an absent member that an "
                        "idle worker of the same role can replace",
                    )
                engine_op = found
            case OvertimeOp():
                k = by_role.get(normalise_role(op.role))
                if k is None:
                    return ActionIssue("unknown_role", f'"{op.role}" is not a role of the team')
                cap = overtime_cap(instance.roles[k].capacity)
                if not 1 <= op.workers <= cap or not 1 <= op.days <= MAX_OVERTIME_DAYS:
                    return ActionIssue(
                        "out_of_range",
                        f"OVERTIME of {roles[k]} needs 1..{cap} workers and 1.."
                        f"{MAX_OVERTIME_DAYS} days, got {op.workers} and {op.days}",
                    )
                engine_op = Overtime(role=k, workers=op.workers, days=op.days)
        alpha = params.handover_factor
        current, rejected = rehearse(
            current, Decision(operations=(engine_op,)), handover_factor=alpha
        )
        if rejected:
            return ActionIssue("rejected", rejected[0].reason)
        operations.append(engine_op)
    prepared = prepare(observation, kind, tuple(operations), params, plans)
    if prepared.rejection is not None:
        return ActionIssue("rejected", prepared.rejection)
    return Candidate(
        label=label,
        kind=kind,
        decision=prepared.decision,
        plan=prepared.after.plan,
        substituted=sum(len(op.workers) for op in operations if isinstance(op, Subst)),
        fallbacks=prepared.fallbacks,
    )


@dataclass(frozen=True)
class Compiled:
    """A proposal of a source with its label: the candidate (None if it did not compile), the
    issue that stopped it, and the label of the rule candidate or earlier proposal it
    duplicates (then it is not evaluated)."""

    label: str
    proposal: Proposal | None
    candidate: Candidate | None
    issue: ActionIssue | None = None
    duplicate_of: str | None = None

    @property
    def usable(self) -> bool:
        """A compiled proposal that is no duplicate: it joins the candidates."""
        return self.candidate is not None and self.duplicate_of is None


class Compiler:
    """Compiles the proposals of one state (spec section 10.3) and flags duplicates of the rule
    candidates and of earlier proposals; the plan parts are shared through one `PlanCache`."""

    def __init__(
        self,
        observation: Observation,
        rule_candidates: Sequence[Candidate],
        params: SentinelParams,
    ) -> None:
        self.observation = observation
        self.params = params
        self.timed = timed_activities(observation)
        self.effects = {effect(c, self.timed): c.label for c in rule_candidates}
        self.plans: PlanCache = {}

    def compile(self, entry: Proposal | ActionIssue, label: str) -> Compiled:
        if isinstance(entry, ActionIssue):
            return Compiled(label, None, None, issue=entry)
        result = compile_proposal(
            entry, self.observation, self.params, label=label, plans=self.plans
        )
        if isinstance(result, ActionIssue):
            return Compiled(label, entry, None, issue=result)
        key = effect(result, self.timed)
        if key in self.effects:
            return Compiled(label, entry, result, duplicate_of=self.effects[key])
        self.effects[key] = label
        return Compiled(label, entry, result)


def random_proposals(
    observation: Observation, rng: np.random.Generator, count: int = MAX_PROPOSALS
) -> tuple[Proposal, ...]:
    """The control source of RQ5: `count` proposals drawn uniformly from the grammar over the
    operations valid in the state. A proposal has 1..3 operations (uniform); each operation's
    type is uniform among those still available (a plan operation at most once, SUBST of an
    eligible activity not yet used, OVERTIME of a role with floor(gamma R_k) >= 1 not yet used),
    and its parameters are uniform: SHIFT, RESEQ-M or RESEQ-S; the activity; the role, 1..floor(
    gamma R_k) workers and 1..20 days."""
    instance = observation.instance
    roles = role_names(instance)
    eligible = sorted(s.activity for s in single_substitutions(observation))
    hireable = [k for k, role in enumerate(instance.roles) if overtime_cap(role.capacity) >= 1]
    proposals: list[Proposal] = []
    for _ in range(count):
        size = int(rng.integers(1, MAX_OPERATIONS + 1))
        operations: list[GrammarOp] = []
        planned = False
        activities, hire = list(eligible), list(hireable)
        for _ in range(size):
            types = [
                name
                for name, available in (
                    ("plan", not planned),
                    ("subst", bool(activities)),
                    ("overtime", bool(hire)),
                )
                if available
            ]
            if not types:
                break
            match types[int(rng.integers(len(types)))]:
                case "plan":
                    planned = True
                    choice = int(rng.integers(3))
                    if choice == 0:
                        operations.append(ShiftOp(op="SHIFT"))
                    else:
                        objective: Literal["makespan", "stable"] = (
                            "makespan" if choice == 1 else "stable"
                        )
                        operations.append(ReseqOp(op="RESEQ", objective=objective))
                case "subst":
                    j = activities.pop(int(rng.integers(len(activities))))
                    operations.append(SubstOp(op="SUBST", activity=j))
                case _:
                    k = hire.pop(int(rng.integers(len(hire))))
                    cap = overtime_cap(instance.roles[k].capacity)
                    operations.append(
                        OvertimeOp(
                            op="OVERTIME",
                            role=roles[k],
                            workers=int(rng.integers(1, cap + 1)),
                            days=int(rng.integers(1, MAX_OVERTIME_DAYS + 1)),
                        )
                    )
        proposals.append(Proposal(operations=tuple(operations)))
    return tuple(proposals)


class ProposalSettings(BaseModel):
    """Prompt version and decoding parameters of a proposal call."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt_version: str = Field(default="v1", min_length=1)
    max_tokens: PositiveInt
    temperature: float = Field(default=0.0, ge=0, allow_inf_nan=False)


def proposal_messages(summary: str, prompt: Prompt) -> list[Message]:
    """The conversation of a proposal call: the system prompt and the state summary."""
    return [Message(role="system", content=prompt.text), Message(role="user", content=summary)]


def ask(
    client: LlmClient, summary: str, *, seed: int, settings: ProposalSettings
) -> LlmResponse[ProposalAnswer]:
    """One proposal call on a state summary (`describe.state_summary`)."""
    prompt = load_prompt(PROPOSALS_PROMPT, settings.prompt_version)
    return client.complete(
        proposal_messages(summary, prompt),
        schema=ProposalAnswer,
        temperature=settings.temperature,
        seed=seed,
        max_tokens=settings.max_tokens,
    )


def answer_entries(response: LlmResponse[ProposalAnswer]) -> list[Proposal | ActionIssue]:
    """The proposals of an answer (`read_proposals`); unparseable JSON is one issue."""
    if response.error is not None and response.error.kind in ("empty", "json", "truncated"):
        return [ActionIssue("invalid_json", f"{response.error.kind}: {response.error.message}")]
    return read_proposals(response.parsed)
