"""Racing evaluation of candidate actions on shared sampled worlds (spec sections 5, 5.1, 6).

Rollout i of an epoch uses xi_i = derive_seed(seed, "rollout", str(i)), as the forecaster does:
its belief stream samples the hidden state once, and the world is reused by every candidate;
its future stream drives the disruptions after the observed day (ADR-0009). A candidate is
applied at step 3 of the observed day with the engine's `Run.apply`, and the rollout continues
under NoReaction (`Run.resume`), so all candidates see the same N worlds (common random
numbers). Racing (ADR-0015): stage 1 runs N_1 rollouts per candidate and drops those whose
capped on-time estimate min(p, theta_D) is below the best by more than `se_factor` paired
standard errors; stage 2 extends the survivors to N.
"""

import math
import time
from dataclasses import dataclass, field

import numpy as np
from pydantic import BaseModel, ConfigDict, NonNegativeFloat, NonNegativeInt

from sentinel.agent.candidates import Candidate, CandidateKind
from sentinel.agent.params import SentinelParams
from sentinel.experiments.runs import derive_seed
from sentinel.forecasting.beliefs import Belief
from sentinel.forecasting.forecast import rollout_streams
from sentinel.forecasting.streams import RolloutStreams
from sentinel.policies.no_reaction import NoReaction
from sentinel.simulation.engine import Run, rehearse
from sentinel.simulation.state import (
    UNSTARTED,
    EngineState,
    Observation,
    SampledWorld,
    nominal_activity,
    state_from_observation,
)
from sentinel.simulation.uncertainty import derive_budget

_BASE_POLICY = NoReaction()


@dataclass
class Outcomes:
    """Per-rollout outcomes of one candidate, rollouts 0, 1, ... in order."""

    on_time: list[bool] = field(default_factory=list)
    cost: list[float] = field(default_factory=list)
    makespan: list[int] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.on_time)


class CandidateStats(BaseModel):
    """What the decision rule knows of a candidate (spec sections 5 and 6): `rollouts` used,
    p = `p_on_time`, `capped` = min(p, theta_D), `se_vs_best` the standard error of the paired
    on-time differences against the best candidate of its stage, z = `mean_cost` (cost so far
    included), o = `overrun`, Delta = `deviation` (substitutions included), l = `level`, and
    whether racing `dropped` it in stage 1. `utility` is U_a of the scalarised ablation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str
    kind: CandidateKind
    level: NonNegativeInt
    deviation: NonNegativeFloat
    substituted: NonNegativeInt
    rollouts: NonNegativeInt
    p_on_time: NonNegativeFloat
    capped: NonNegativeFloat
    se_vs_best: NonNegativeFloat
    mean_cost: float
    overrun: NonNegativeFloat
    utility: float
    dropped: bool


class Evaluation(BaseModel):
    """The statistics of every candidate (in candidate order), the final best by capped on-time
    estimate, the rollouts run in this call and its wall time."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stats: tuple[CandidateStats, ...]
    best: NonNegativeInt
    rollouts: NonNegativeInt
    wall_time_s: NonNegativeFloat


class Evaluator:
    """Rollouts of candidates from one observation on the epoch's shared sampled worlds.

    Worlds are sampled once, when first needed, with the engine state they complete and the
    streams of their future; every rollout in world i starts from a copy of that state and
    from the same streams, rewound (ADR-0015). `extend` runs a candidate's rollouts up to a
    count and keeps them by label, so the needs gate's NOOP rollouts serve racing too. A
    candidate is checked once through the engine (`rehearse`); its rollouts then apply it
    without checking plans again. The deadline D comes from the observation; the budget B is
    the instance's, or derived with beta = `budget_reserve` and c_k = 1 (spec section 1.2), as
    the observation carries neither.
    """

    def __init__(self, observation: Observation, seed: int, params: SentinelParams) -> None:
        if observation.deadline is None:
            raise ValueError("Sentinel needs a deadline D (spec section 1.2)")
        self.observation = observation
        self.seed = seed
        self.params = params
        self.deadline = observation.deadline
        instance = observation.instance
        self.budget = (
            instance.budget
            if instance.budget is not None
            else derive_budget(instance, params.budget_reserve, params=observation.pert)
        )
        self.belief = Belief(observation)
        self.worlds: list[SampledWorld] = []
        self.templates: list[EngineState] = []
        self.streams: list[RolloutStreams] = []
        self.outcomes: dict[str, Outcomes] = {}  # by candidate label, unique in an epoch
        self.rollouts = 0

    def seeds(self, i: int) -> tuple[np.random.SeedSequence, np.random.SeedSequence]:
        """The belief and future streams of rollout i (forecaster layout, ADR-0009)."""
        root = np.random.SeedSequence(derive_seed(self.seed, "rollout", str(i)))
        belief, future = root.spawn(2)
        return belief, future

    def world(self, i: int) -> SampledWorld:
        """Sampled world i, with its engine state and future streams."""
        observation, alpha = self.observation, self.params.handover_factor
        while len(self.worlds) <= i:
            belief, future = self.seeds(len(self.worlds))
            world = self.belief.sample(np.random.Generator(np.random.PCG64(belief)))
            self.worlds.append(world)
            self.templates.append(state_from_observation(observation, world, handover_factor=alpha))
            self.streams.append(
                rollout_streams(observation, world, observation.disruptions, future)
            )
        return self.worlds[i]

    def extend(self, candidate: Candidate, n: int) -> Outcomes:
        """The candidate's outcomes on rollouts 0 .. n - 1, running those not run yet."""
        outcomes = self.outcomes.get(candidate.label)
        if outcomes is None:
            alpha = self.params.handover_factor
            rejected = rehearse(self.observation, candidate.decision, handover_factor=alpha)[1]
            if rejected:
                raise ValueError(f"candidate {candidate.label} is invalid: {rejected[0].reason}")
            outcomes = self.outcomes[candidate.label] = Outcomes()
        for i in range(len(outcomes), n):
            makespan, truncated, cost = self.rollout(candidate, i)
            outcomes.on_time.append(not truncated and makespan <= self.deadline)
            outcomes.cost.append(cost)
            outcomes.makespan.append(makespan)
            self.rollouts += 1
        return outcomes

    def rollout(self, candidate: Candidate, i: int) -> tuple[int, bool, float]:
        """Rollout i of the candidate: (makespan, truncated, total cost); a truncated rollout
        ends at max_days."""
        self.world(i)
        state = self.templates[i].copy()
        streams = self.streams[i]
        streams.rewind()
        run = Run(
            state,
            streams,
            _BASE_POLICY,
            review_period=self.params.review_period,
            record_events=False,
            check_plans=False,
        )
        run.apply(candidate.decision)
        run.resume()
        finish = state.start[state.sink]
        if finish is None:
            return state.max_days, True, state.cost
        return finish, False, state.cost

    def overrun(self, mean_cost: float) -> float:
        """o = max(0, z - B) / B (spec section 5)."""
        return max(0.0, mean_cost - self.budget) / self.budget if self.budget > 0 else 0.0

    def stats(
        self,
        candidate: Candidate,
        n: int,
        best: Outcomes | None,
        deviation: float,
        *,
        dropped: bool = False,
    ) -> CandidateStats:
        """Statistics of the candidate's first n rollouts; `best` gives the paired SE."""
        outcomes = self.extend(candidate, n)
        on_time = outcomes.on_time[:n]
        p = sum(on_time) / n
        mean_cost = math.fsum(outcomes.cost[:n]) / n
        overrun = self.overrun(mean_cost)
        params = self.params
        se = 0.0 if best is None else paired_se(best.on_time[:n], on_time)
        return CandidateStats(
            label=candidate.label,
            kind=candidate.kind,
            level=candidate.level,
            deviation=deviation,
            substituted=candidate.substituted,
            rollouts=n,
            p_on_time=p,
            capped=min(p, params.theta_d),
            se_vs_best=se,
            mean_cost=mean_cost,
            overrun=overrun,
            utility=p - params.lambda_b * overrun - params.lambda_delta * deviation,
            dropped=dropped,
        )


def paired_se(first: list[bool], second: list[bool]) -> float:
    """Standard error of the mean of the paired differences first_i - second_i (CRN)."""
    n = len(first)
    if n < 2:
        return 0.0
    differences = [float(a) - float(b) for a, b in zip(first, second, strict=True)]
    mean = math.fsum(differences) / n
    variance = math.fsum((d - mean) ** 2 for d in differences) / (n - 1)
    return math.sqrt(variance / n)


def instability(observation: Observation, candidate: Candidate, kappa_h: float) -> float:
    """Delta_a of spec section 5: the mean |S_j^a - S_j^t| over the deviation set U'_t (the
    unstarted activities with p_j > 0 not inserted today; 0 if empty) plus kappa_h per
    replaced crew member."""
    t = observation.day
    fresh = {act.id for act in observation.inserted if act.day == t}
    current, plan = observation.plan, candidate.plan
    moved = [
        abs(plan[j] - current[j])
        for j, state in enumerate(observation.status)
        if state == UNSTARTED and nominal_activity(observation, j)[0] > 0 and j not in fresh
    ]
    mean = sum(moved) / len(moved) if moved else 0.0
    return mean + kappa_h * candidate.substituted


def race(evaluator: Evaluator, candidates: list[Candidate], *, racing: bool = True) -> Evaluation:
    """Evaluate the candidates by racing (spec section 6): stage 1 on N_1 rollouts each, drop
    those whose capped on-time estimate is below the stage's best by more than `se_factor`
    paired standard errors, stage 2 extends the survivors to N. Without `racing` every candidate
    gets N rollouts. The best is the first candidate with the largest capped estimate; dropped
    candidates keep their stage-1 statistics."""
    began = time.perf_counter()
    before = evaluator.rollouts
    params = evaluator.params
    deviations = [instability(evaluator.observation, c, params.kappa_h) for c in candidates]
    keep = list(range(len(candidates)))
    first: dict[int, CandidateStats] = {}
    if racing and params.n_stage1 < params.n_rollouts:
        n1 = params.n_stage1
        outcomes = [evaluator.extend(c, n1) for c in candidates]
        capped = [min(sum(o.on_time[:n1]) / n1, params.theta_d) for o in outcomes]
        top = max(range(len(candidates)), key=lambda a: (capped[a], -a))
        keep = []
        for a, candidate in enumerate(candidates):
            se = paired_se(outcomes[top].on_time[:n1], outcomes[a].on_time[:n1])
            if capped[top] - capped[a] > params.se_factor * se:
                first[a] = evaluator.stats(
                    candidate, n1, outcomes[top], deviations[a], dropped=True
                )
            else:
                keep.append(a)
    n = params.n_rollouts
    finals = [evaluator.extend(candidates[a], n) for a in keep]
    capped = [min(sum(o.on_time[:n]) / n, params.theta_d) for o in finals]
    top = keep[max(range(len(keep)), key=lambda b: (capped[b], -b))]
    best = evaluator.extend(candidates[top], n)
    stats = [
        first[a] if a in first else evaluator.stats(c, n, best, deviations[a])
        for a, c in enumerate(candidates)
    ]
    return Evaluation(
        stats=tuple(stats),
        best=top,
        rollouts=evaluator.rollouts - before,
        wall_time_s=time.perf_counter() - began,
    )
