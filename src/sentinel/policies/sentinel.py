"""Sentinel: a one-step rollout policy on the base policy NoReaction (spec sections 5 and 6;
Bertsekas, Tsitsiklis & Wu 1997), with full autonomy (every chosen action applies).

At a decision epoch with an event touching a crew (an absence onset or return of a crew member,
D2, D3) or a periodic one, Sentinel deliberates: it evaluates NOOP on the epoch's sampled
worlds and returns it if the needs are met (needs gate, spec section 5); otherwise it generates
the rule candidates, races them on the same worlds and applies the choice of its decision
rule. At epochs whose only events concern idle workers it returns NOOP without deliberating.
"""

import math
import time
from dataclasses import dataclass, field

from sentinel.agent.candidates import Candidate, generate, noop
from sentinel.agent.decide import CandidateRecord, DecisionRecord, Needs, Reason, choose
from sentinel.agent.evaluate import Evaluator, race
from sentinel.agent.params import SentinelParams
from sentinel.experiments.runs import derive_seed
from sentinel.policies.base import EMPTY_DECISION, Decision, DecisionStats
from sentinel.simulation.state import PAUSED, RUNNING, Observation


@dataclass
class SentinelStats(DecisionStats):
    """`DecisionStats` (with `reseqs`: CP-SAT searches for RESEQ plans) and Sentinel's own
    counts: deliberations, needs-gate exits, epochs without deliberation, candidates evaluated,
    rollouts, the wall time of each deliberation and the chosen candidates by kind."""

    deliberations: int = 0
    gate_exits: int = 0
    skipped: int = 0
    candidates: int = 0
    rollouts: int = 0
    deliberation_s: list[float] = field(default_factory=list)
    chosen: dict[str, int] = field(default_factory=dict)


class Sentinel:
    """The Sentinel agent (spec section 6) with `params` (variant `full`, `no_overtime` or
    `scalarised`). It sees only observations. The rollouts of epoch t use the seed
    derive_seed(`seed`, "sentinel", str(t)), with `seed` the run's seed, so a run is
    deterministic and the exogenous events stay those of the world (common random numbers).
    `records` keeps a `DecisionRecord` per epoch (without `keep_records`, none); a policy
    object serves one run at a time and recognises a new run by its day.
    """

    def __init__(
        self, params: SentinelParams | None = None, *, seed: int = 0, keep_records: bool = True
    ) -> None:
        self.params = SentinelParams() if params is None else params
        self.seed = seed
        self.keep_records = keep_records
        self.stats = SentinelStats()
        self.records: list[DecisionRecord] = []
        self._seen: tuple[int, tuple[bool, ...], int, int] | None = None

    @property
    def name(self) -> str:
        return f"sentinel_{self.params.variant}"

    def decide(self, observation: Observation) -> Decision:
        """NOOP at an epoch with only idle workers' events, else the deliberated choice."""
        began = time.perf_counter()
        stats = self.stats
        if self.deliberates(observation):
            record = self.deliberate(observation)
            stats.deliberations += 1
            stats.deliberation_s.append(record.wall_time_s)
        else:
            stats.skipped += 1
            record = DecisionRecord(
                day=observation.day,
                deliberated=False,
                rule=self.params.rule,
                reason="idle_events",
                chosen="NOOP",
                decision=EMPTY_DECISION,
            )
        stats.decisions += 1
        stats.decide_time_s += time.perf_counter() - began
        if self.keep_records:
            self.records.append(record)
        return record.decision

    def deliberates(self, observation: Observation) -> bool:
        """Whether the epoch is periodic or has an event touching a crew since the previous
        epoch: a D2 shock, a D3 activity, or an absence onset or return of a worker who is in
        the crew of a started activity (spec section 6, deliberation epochs)."""
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
        if observation.day % self.params.review_period == 0 or seen[2:] != before[2:]:
            return True
        changed = [w for w in range(n_workers) if present[w] != before[1][w]]
        if not changed:
            return False
        status, assigned = observation.status, observation.assigned
        crews = {w for j, s in enumerate(status) if s in (RUNNING, PAUSED) for w in assigned[j]}
        return any(w in crews for w in changed)

    def deliberate(self, observation: Observation) -> DecisionRecord:
        """Needs gate, candidates, racing and the decision rule at one epoch (spec 5-6)."""
        began = time.perf_counter()
        params, stats = self.params, self.stats
        t = observation.day
        evaluator = Evaluator(observation, derive_seed(self.seed, "sentinel", str(t)), params)
        base = noop(observation)
        needs = self.needs(evaluator, base)
        if needs.met:
            stats.gate_exits += 1
            stats.rollouts += evaluator.rollouts
            return DecisionRecord(
                day=t,
                deliberated=True,
                rule=params.rule,
                reason="needs_met",
                chosen=base.label,
                decision=base.decision,
                needs=needs,
                rollouts=evaluator.rollouts,
                evaluation_s=time.perf_counter() - began,
                wall_time_s=time.perf_counter() - began,
            )
        generation = generate(observation, params=params)
        candidates: list[Candidate] = list(generation.candidates)
        stats.reseqs += generation.solves
        stats.fallbacks += generation.fallbacks
        stats.solve_time_s += generation.solve_time_s
        stats.candidates += len(candidates)
        evaluated = time.perf_counter()
        reason: Reason = "only_candidate"
        index = 0
        tied: tuple[int, ...] = (0,)
        records: list[CandidateRecord] = []
        if len(candidates) > 1:
            evaluation = race(evaluator, candidates)
            choice = choose(evaluation.stats, params)
            index, reason = choice.index, choice.reason
            tied = choice.ties
            records = [
                CandidateRecord(**s.model_dump(), decision=c.decision)
                for s, c in zip(evaluation.stats, candidates, strict=True)
            ]
        chosen = candidates[index]
        stats.chosen[chosen.kind] = stats.chosen.get(chosen.kind, 0) + 1
        stats.rollouts += evaluator.rollouts
        done = time.perf_counter()
        return DecisionRecord(
            day=t,
            deliberated=True,
            rule=params.rule,
            reason=reason,
            chosen=chosen.label,
            decision=chosen.decision,
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

    def needs(self, evaluator: Evaluator, base: Candidate) -> Needs:
        """The needs of NOOP (spec section 5) from N_1 rollouts, or from N where the N_1 ones
        do not show a need beyond `se_factor` standard errors (deadline: theta_D - p -
        epsilon_D; budget: the overrun of the mean cost lowered by that many errors, minus
        epsilon_B). The gate is met only on N rollouts."""
        params = self.params
        k = params.se_factor
        outcomes = evaluator.extend(base, params.n_stage1)
        n = len(outcomes)
        p, se_p = _mean_se([float(x) for x in outcomes.on_time])
        cost, se_cost = _mean_se(outcomes.cost)
        clear = params.theta_d - p - params.eps_d > k * se_p
        clear = clear or evaluator.overrun(cost - k * se_cost) > params.eps_b
        if not clear:
            outcomes = evaluator.extend(base, params.n_rollouts)
            n = len(outcomes)
            p, _ = _mean_se([float(x) for x in outcomes.on_time])
            cost, _ = _mean_se(outcomes.cost)
        deadline = max(0.0, params.theta_d - p)
        budget = evaluator.overrun(cost)
        return Needs(
            deadline=deadline,
            budget=budget,
            p_on_time=p,
            rollouts=n,
            met=deadline <= params.eps_d and budget <= params.eps_b,
        )


def _mean_se(values: list[float]) -> tuple[float, float]:
    """Mean and its standard error (sample standard deviation / sqrt n; 0 for n < 2)."""
    n = len(values)
    mean = math.fsum(values) / n
    if n < 2:
        return mean, 0.0
    variance = math.fsum((v - mean) ** 2 for v in values) / (n - 1)
    return mean, math.sqrt(variance / n)
