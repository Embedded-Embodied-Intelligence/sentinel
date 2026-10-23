"""Sentinel: a one-step rollout policy on the base policy NoReaction (spec sections 4-6;
Bertsekas, Tsitsiklis & Wu 1997), with a permission gate.

At a decision epoch with an event touching a crew (an absence onset or return of a crew member,
D2, D3) or a periodic one, Sentinel deliberates: it evaluates NOOP on the epoch's sampled
worlds and returns it if the needs are met (needs gate, spec section 5); otherwise it generates
the rule candidates, races them on the same worlds (with DESCOPE candidates when enabled and no
candidate reaches theta_D) and takes the choice of its decision rule. The permission gate then
applies the choice at once if its level is below Lambda and it has no DESCOPE; otherwise it
defers (NOOP, deliberate again later) if the urgency exceeds tau_def, else escalates: a
simulated human approves after delta_h days and the approval day becomes a decision epoch. The
human approves the action's intent: there its SUBST, OVERTIME and DESCOPE operations are
re-validated and its plan part is planned again on the current planning view (`approve`), and
the action applies all or nothing; if it is discarded, a fresh deliberation follows. While an
action awaits approval, and at epochs whose only events concern idle workers, Sentinel returns
NOOP without deliberating.
"""

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from sentinel.agent.candidates import Candidate, approve, descopes, generate, noop
from sentinel.agent.decide import (
    CandidateRecord,
    Choice,
    DecisionRecord,
    Gate,
    Reason,
    assess_needs,
    choose,
)
from sentinel.agent.evaluate import Evaluation, Evaluator, race
from sentinel.agent.params import SentinelParams
from sentinel.experiments.runs import derive_seed
from sentinel.policies.base import EMPTY_DECISION, Decision, DecisionStats
from sentinel.policies.urgency import urgencies
from sentinel.simulation.state import PAUSED, RUNNING, UNSTARTED, Observation


@dataclass
class SentinelStats(DecisionStats):
    """`DecisionStats` (with `reseqs`: CP-SAT searches for RESEQ plans, those of approval days
    included) and Sentinel's own counts: deliberations, needs-gate exits, epochs without
    deliberation, candidates evaluated, rollouts, the wall time of each deliberation, the chosen
    candidates by kind (before the permission gate), the decisions by reason
    (`DecisionRecord.reason`), what the gate did: deferrals, escalations, approvals applied and
    approvals discarded (spec section 4), and the plan parts that rollouts planned again on
    their approval days: CP-SAT searches and plan parts reused within an epoch (ADR-0017), and
    the candidates a proposer added (`proposed`, WP6b)."""

    deliberations: int = 0
    gate_exits: int = 0
    skipped: int = 0
    candidates: int = 0
    rollouts: int = 0
    deferrals: int = 0
    escalations: int = 0
    approvals_applied: int = 0
    approvals_discarded: int = 0
    deliberation_s: list[float] = field(default_factory=list)
    chosen: dict[str, int] = field(default_factory=dict)
    reasons: dict[str, int] = field(default_factory=dict)
    replan_solves: int = 0
    replans_reused: int = 0
    proposed: int = 0


class Proposer(Protocol):
    """Candidates proposed at a deliberation that passed the needs gate (spec section 10.3):
    from the observation, the record of the rule candidates and the rule candidates themselves,
    compiled candidates that are valid, no duplicates and labelled uniquely within the epoch
    (WP6b online check)."""

    def __call__(
        self, observation: Observation, record: DecisionRecord, rule: Sequence[Candidate]
    ) -> Sequence[Candidate]:
        """The extra candidates of the deliberation."""
        ...


@dataclass(frozen=True)
class Pending:
    """An escalated candidate awaiting approval on `day`."""

    candidate: Candidate
    day: int


class Sentinel:
    """The Sentinel agent (spec section 6) with `params` (variant `full`, `no_overtime` or
    `scalarised`, autonomy Lambda, DESCOPE). It sees only observations. The rollouts of epoch t
    use the seed derive_seed(`seed`, "sentinel", str(t)), with `seed` the run's seed, so a run
    is deterministic and the exogenous events stay those of the world (common random numbers).
    `records` keeps a `DecisionRecord` per epoch (without `keep_records`, none); a policy object
    serves one run at a time and recognises a new run by its day. After an escalation,
    `requested_epoch` asks the engine for the approval day as a decision epoch.
    A `proposer` (WP6b, spec section 10.3) adds compiled candidates after the rule candidates are
    raced; all are then raced again on the same worlds and the rule chooses among them.
    """

    def __init__(
        self,
        params: SentinelParams | None = None,
        *,
        seed: int = 0,
        keep_records: bool = True,
        proposer: Proposer | None = None,
    ) -> None:
        self.params = SentinelParams() if params is None else params
        self.proposer = proposer
        self.seed = seed
        self.keep_records = keep_records
        self.stats = SentinelStats()
        self.records: list[DecisionRecord] = []
        self.pending: Pending | None = None
        self.requested_epoch: int | None = None
        self._seen: tuple[int, tuple[bool, ...], int, int] | None = None

    @property
    def name(self) -> str:
        return f"sentinel_{self.params.variant}"

    def decide(self, observation: Observation) -> Decision:
        """The decision of the epoch: an approved action, re-planned on its approval day, NOOP
        while one awaits approval or at an epoch with only idle workers' events, else the
        deliberated choice after the gate."""
        began = time.perf_counter()
        stats = self.stats
        t = observation.day
        self.requested_epoch = None
        crew_event = self.deliberates(observation)
        pending = self.pending
        if pending is not None and t < pending.day:
            record = self._quiet(t, "awaiting_approval")
        elif pending is not None:
            self.pending = None
            approval = approve(observation, pending.candidate, self.params)
            stats.reseqs += approval.solves
            stats.fallbacks += approval.fallbacks
            stats.solve_time_s += approval.solve_time_s
            label = pending.candidate.label
            if approval.rejection is not None:
                stats.approvals_discarded += 1
                record = self.deliberate(observation, discarded=label)
            else:
                stats.approvals_applied += 1
                record = DecisionRecord(
                    day=t,
                    deliberated=False,
                    rule=self.params.rule,
                    reason="approved",
                    chosen=label,
                    decision=approval.decision,
                    cp_solves=approval.solves,
                    cp_fallbacks=approval.fallbacks,
                )
        elif crew_event:
            record = self.deliberate(observation)
        else:
            stats.skipped += 1
            record = self._quiet(t, "idle_events")
        stats.decisions += 1
        stats.reasons[record.reason] = stats.reasons.get(record.reason, 0) + 1
        stats.decide_time_s += time.perf_counter() - began
        if self.keep_records:
            self.records.append(record)
        return record.decision

    def _quiet(self, day: int, reason: Reason) -> DecisionRecord:
        return DecisionRecord(
            day=day,
            deliberated=False,
            rule=self.params.rule,
            reason=reason,
            chosen="NOOP",
            decision=EMPTY_DECISION,
        )

    def deliberates(self, observation: Observation) -> bool:
        """Whether the epoch is periodic or has an event touching a crew since the previous
        epoch: a D2 shock, a D3 activity, or an absence onset or return of a worker who is in
        the crew of a started activity (spec section 6, deliberation epochs). A new run, told
        by its day, forgets the previous run, a pending approval included."""
        n_workers = len(observation.instance.workers)
        present = observation.present[:n_workers]
        seen = (
            observation.day,
            present,
            len(observation.work_increases),
            len(observation.inserted),
        )
        before = self._seen
        self._seen = seen
        if before is None or observation.day <= before[0]:  # a new run
            before = (-1, (True,) * n_workers, 0, 0)
            self.pending = None
        if observation.day % self.params.review_period == 0 or seen[2:] != before[2:]:
            return True
        changed = [w for w in range(n_workers) if present[w] != before[1][w]]
        if not changed:
            return False
        status, assigned = observation.status, observation.assigned
        crews = {w for j, s in enumerate(status) if s in (RUNNING, PAUSED) for w in assigned[j]}
        return any(w in crews for w in changed)

    def deliberate(self, observation: Observation, discarded: str | None = None) -> DecisionRecord:
        """Needs gate, candidates, racing, the decision rule and the permission gate at one
        epoch (spec sections 4-6); `discarded` names an approved action no longer valid."""
        began = time.perf_counter()
        params, stats = self.params, self.stats
        t = observation.day
        stats.deliberations += 1
        evaluator = Evaluator(observation, derive_seed(self.seed, "sentinel", str(t)), params)
        base = noop(observation)
        needs = assess_needs(evaluator, base)
        if needs.met:
            stats.gate_exits += 1
            stats.rollouts += evaluator.rollouts
            done = time.perf_counter()
            stats.deliberation_s.append(done - began)
            return DecisionRecord(
                day=t,
                deliberated=True,
                rule=params.rule,
                reason="needs_met",
                chosen=base.label,
                decision=base.decision,
                discarded=discarded,
                needs=needs,
                rollouts=evaluator.rollouts,
                evaluation_s=done - began,
                wall_time_s=done - began,
            )
        generation = generate(observation, params=params)
        candidates: list[Candidate] = list(generation.candidates)
        stats.reseqs += generation.solves
        stats.fallbacks += generation.fallbacks
        stats.solve_time_s += generation.solve_time_s
        evaluated = time.perf_counter()
        reason: Reason = "only_candidate"
        index = 0
        runner: int | None = None
        tied: tuple[int, ...] = (0,)
        records: list[CandidateRecord] = []
        if params.descope and len(candidates) == 1 and needs.p_on_time < params.theta_d:
            candidates += descopes(observation, params)
        if len(candidates) > 1:
            evaluation = race(evaluator, candidates)
            if params.descope and not any(c.kind == "descope" for c in candidates):
                best_p = max(s.p_on_time for s in evaluation.stats if not s.dropped)
                extra = descopes(observation, params) if best_p < params.theta_d else []
                if extra:
                    candidates += extra
                    evaluation = race(evaluator, candidates)
            choice = choose(evaluation.stats, params, evaluation.paired)
            index, reason, runner, tied = choice.index, choice.reason, choice.runner_up, choice.ties
            records = _records(evaluation, candidates, choice)
        if self.proposer is not None:
            rule = DecisionRecord(
                day=t,
                deliberated=True,
                rule=params.rule,
                reason=reason,
                chosen=candidates[index].label,
                decision=candidates[index].decision,
                runner_up=None if runner is None else candidates[runner].label,
                needs=needs,
                candidates=tuple(records),
                tied=tuple(candidates[a].label for a in tied),
                rollouts=evaluator.rollouts,
            )
            extra = list(self.proposer(observation, rule, tuple(candidates)))
            stats.proposed += len(extra)
            if extra:
                candidates += extra
                evaluation = race(evaluator, candidates)
                choice = choose(evaluation.stats, params, evaluation.paired)
                index, reason = choice.index, choice.reason
                runner, tied = choice.runner_up, choice.ties
                records = _records(evaluation, candidates, choice)
        stats.candidates += len(candidates)
        chosen = candidates[index]
        stats.chosen[chosen.kind] = stats.chosen.get(chosen.kind, 0) + 1
        gate, decision = self.gate(observation, chosen)
        stats.rollouts += evaluator.rollouts
        stats.replan_solves += evaluator.replan_solves
        stats.replans_reused += evaluator.replans_reused
        done = time.perf_counter()
        stats.deliberation_s.append(done - began)
        return DecisionRecord(
            day=t,
            deliberated=True,
            rule=params.rule,
            reason=reason,
            chosen=chosen.label,
            decision=decision,
            runner_up=None if runner is None else candidates[runner].label,
            gate=gate,
            approval_day=None if self.pending is None else self.pending.day,
            discarded=discarded,
            needs=needs,
            candidates=tuple(records),
            tied=tuple(candidates[a].label for a in tied),
            rollouts=evaluator.rollouts,
            cp_solves=generation.solves,
            cp_fallbacks=generation.fallbacks,
            generation_s=generation.wall_time_s,
            evaluation_s=done - evaluated,
            wall_time_s=done - began,
        )

    def gate(self, observation: Observation, chosen: Candidate) -> tuple[Gate | None, Decision]:
        """The permission gate (spec section 4): the chosen decision runs at once if it needs
        no approval; otherwise NOOP now, deferred if the urgency exceeds tau_def, else escalated
        with the approval day as the next requested epoch. None for NOOP."""
        params = self.params
        if not params.needs_approval(chosen.decision):
            return ("auto" if chosen.decision.operations else None), chosen.decision
        if self.urgency(observation) > params.tau_def:
            self.stats.deferrals += 1
            return "deferred", EMPTY_DECISION
        day = observation.day + params.approval_delay
        self.pending = Pending(candidate=chosen, day=day)
        self.requested_epoch = day
        self.stats.escalations += 1
        return "escalated", EMPTY_DECISION

    @staticmethod
    def urgency(observation: Observation) -> float:
        """tau_t = min_j tau_j over the unstarted, paused and running activities (spec 5)."""
        unfinished = [
            j for j, s in enumerate(observation.status) if s in (UNSTARTED, RUNNING, PAUSED)
        ]
        return min(urgencies(observation, unfinished).values(), default=float("inf"))


def _records(
    evaluation: Evaluation, candidates: Sequence[Candidate], choice: Choice
) -> list[CandidateRecord]:
    """Every candidate's statistics with its operations and where it left the best set."""
    return [
        CandidateRecord(**s.model_dump(), decision=c.decision, eliminated=out)
        for s, c, out in zip(evaluation.stats, candidates, choice.eliminated, strict=True)
    ]
