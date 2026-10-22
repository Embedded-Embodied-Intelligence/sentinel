"""Racing evaluation of candidate actions on shared sampled worlds (spec sections 5, 5.1, 6).

Rollout i of an epoch uses xi_i = derive_seed(seed, "rollout", str(i)), as the forecaster does:
its belief stream samples the hidden state once, and the world is reused by every candidate;
its future stream drives the disruptions after the observed day (ADR-0009). A candidate is
applied at step 3 of the observed day with the engine's `Run.apply`; one that needs approval
(spec section 4) is applied at step 3 of day t + delta_h instead, and only if it is valid in
that rollout (`Run.apply_valid`). The rollout continues under NoReaction (`Run.resume`), so all
candidates see the same N worlds (common random numbers). Racing (ADR-0015): stage 1 runs N_1
rollouts per candidate and drops those significantly and materially worse than the stage's
leader in min(p, theta_D) and in the expected tardiness T; stage 2 extends the survivors to N.
"""

import math
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import numpy.typing as npt
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

_BASE_POLICY = NoReaction()

# The stochastic components of the rule, whose ties use paired standard errors (spec 6).
Paired = Literal["on_time", "tardiness", "budget"]


@dataclass
class Outcomes:
    """Per-rollout outcomes of one candidate, rollouts 0, 1, ... in order; the tardiness is
    max(0, C - D) in days."""

    on_time: list[bool] = field(default_factory=list)
    cost: list[float] = field(default_factory=list)
    makespan: list[int] = field(default_factory=list)
    tardiness: list[int] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.on_time)


class CandidateStats(BaseModel):
    """What the decision rule knows of a candidate (spec sections 5 and 6): `rollouts` used,
    p = `p_on_time`, `capped` = min(p, theta_D), T = `tardiness` (mean days late), z =
    `mean_cost` (cost so far included), o = `overrun`, Delta = `deviation` (substitutions
    included), the `scope_loss` of a DESCOPE, l = `level`, the approval `delay` its rollouts
    imagined (0: applied at once) and whether racing `dropped` it in stage 1. `utility` is U_a
    of the scalarised ablation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str
    kind: CandidateKind
    level: NonNegativeInt
    delay: NonNegativeInt
    deviation: NonNegativeFloat
    substituted: NonNegativeInt
    scope_loss: NonNegativeFloat
    rollouts: NonNegativeInt
    p_on_time: NonNegativeFloat
    capped: NonNegativeFloat
    tardiness: NonNegativeFloat
    mean_cost: float
    overrun: NonNegativeFloat
    utility: float
    dropped: bool


class PairedErrors:
    """Standard errors of the mean paired (CRN) difference between two candidates over their
    first `n` common rollouts (spec section 6): of the on-time indicators, of the tardiness
    max(0, C - D) and of the total cost divided by B. Indices are candidate positions; the
    differences are computed when first asked for, so candidates with fewer rollouts (dropped
    by racing) may be among the outcomes as long as nobody asks for them."""

    def __init__(self, outcomes: Sequence[Outcomes], n: int, budget: float) -> None:
        self.outcomes = outcomes
        self.n = n
        self.budget = budget
        self._cache: dict[tuple[Paired, int, int], float] = {}

    def _values(self, component: Paired, a: int) -> npt.NDArray[np.float64]:
        outcomes, n = self.outcomes[a], self.n
        if len(outcomes) < n:
            raise ValueError(f"candidate {a} has {len(outcomes)} rollouts, not {n}")
        match component:
            case "on_time":
                return np.asarray(outcomes.on_time[:n], dtype=np.float64)
            case "tardiness":
                return np.asarray(outcomes.tardiness[:n], dtype=np.float64)
            case "budget":
                return np.asarray(outcomes.cost[:n], dtype=np.float64) / self.budget

    def __call__(self, component: Paired, a: int, b: int) -> float:
        """The paired standard error of `component` between candidates a and b."""
        key = (component, min(a, b), max(a, b))
        se = self._cache.get(key)
        if se is None:
            n = self.n
            if n < 2 or a == b:
                se = 0.0
            else:
                differences = self._values(component, a) - self._values(component, b)
                se = float(np.std(differences, ddof=1)) / math.sqrt(n)
            self._cache[key] = se
        return se


@dataclass(frozen=True)
class Evaluation:
    """The statistics of every candidate (in candidate order), the leader of the survivors
    (largest capped on-time estimate, then smallest tardiness, then candidate order), the
    paired standard errors on the final rollouts, the rollouts run in this call and its wall
    time."""

    stats: tuple[CandidateStats, ...]
    best: int
    paired: PairedErrors
    rollouts: int
    wall_time_s: float


class Evaluator:
    """Rollouts of candidates from one observation on the epoch's shared sampled worlds.

    Worlds are sampled once, when first needed, with the engine state they complete and the
    streams of their future; every rollout in world i starts from a copy of that state and
    from the same streams, rewound (ADR-0015). `extend` runs a candidate's rollouts up to a
    count and keeps them by label, so the needs gate's NOOP rollouts serve racing too. A
    candidate is checked once through the engine (`rehearse`); its rollouts then apply it
    without checking plans again, except a candidate that needs approval, which each rollout
    re-validates on the approval day. The deadline D and the budget B come from the
    observation.
    """

    def __init__(self, observation: Observation, seed: int, params: SentinelParams) -> None:
        if observation.deadline is None:
            raise ValueError("Sentinel needs a deadline D (spec section 1.2)")
        if observation.budget is None or observation.budget <= 0:
            raise ValueError("Sentinel needs a positive budget B in the observation (spec 3)")
        self.observation = observation
        self.seed = seed
        self.params = params
        self.deadline = observation.deadline
        self.budget = observation.budget
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
        deadline = self.deadline
        for i in range(len(outcomes), n):
            makespan, truncated, cost = self.rollout(candidate, i)
            outcomes.on_time.append(not truncated and makespan <= deadline)
            outcomes.cost.append(cost)
            outcomes.makespan.append(makespan)
            outcomes.tardiness.append(max(0, makespan - deadline))
            self.rollouts += 1
        return outcomes

    def rollout(self, candidate: Candidate, i: int) -> tuple[int, bool, float]:
        """Rollout i of the candidate: (makespan, truncated, total cost); a truncated rollout
        ends at max_days. A candidate that needs approval is applied on the approval day, if
        the project is still running and the candidate is valid in that rollout."""
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
        delay = self.params.delay(candidate.decision)
        if not delay:
            run.apply(candidate.decision)
            run.resume()
        elif run.resume_to(state.day + delay):
            run.apply_valid(candidate.decision)
            run.carry_on()
        finish = state.start[state.sink]
        if finish is None:
            return state.max_days, True, state.cost
        return finish, False, state.cost

    def overrun(self, mean_cost: float) -> float:
        """o = max(0, z - B) / B (spec section 5)."""
        return max(0.0, mean_cost - self.budget) / self.budget

    def stats(
        self, candidate: Candidate, n: int, deviation: float, *, dropped: bool = False
    ) -> CandidateStats:
        """Statistics of the candidate's first n rollouts."""
        outcomes = self.extend(candidate, n)
        p = sum(outcomes.on_time[:n]) / n
        mean_cost = math.fsum(outcomes.cost[:n]) / n
        overrun = self.overrun(mean_cost)
        params = self.params
        return CandidateStats(
            label=candidate.label,
            kind=candidate.kind,
            level=candidate.level,
            delay=params.delay(candidate.decision),
            deviation=deviation,
            substituted=candidate.substituted,
            scope_loss=candidate.scope_loss,
            rollouts=n,
            p_on_time=p,
            capped=min(p, params.theta_d),
            tardiness=sum(outcomes.tardiness[:n]) / n,
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


def race(
    evaluator: Evaluator,
    candidates: Sequence[Candidate],
    *,
    racing: bool = True,
    stage1: int | None = None,
    rollouts: int | None = None,
) -> Evaluation:
    """Evaluate the candidates by racing (spec section 6): stage 1 on N_1 rollouts each, drop
    those not tied with the stage's leader in min(p, theta_D) and not tied with it in T (ties
    of `SentinelParams.ties`, on the stage-1 rollouts), stage 2 extends the survivors to N.
    Without `racing` every candidate gets N rollouts. `stage1` and `rollouts` replace N_1 and N
    of the parameters, e.g. to decide from rollouts evaluated before (outcomes are cached by
    label). Dropped candidates keep their stage-1 statistics."""
    began = time.perf_counter()
    before = evaluator.rollouts
    params = evaluator.params
    n1 = params.n_stage1 if stage1 is None else stage1
    n = params.n_rollouts if rollouts is None else rollouts
    deviations = [instability(evaluator.observation, c, params.kappa_h) for c in candidates]
    keep = list(range(len(candidates)))
    first: dict[int, CandidateStats] = {}
    if racing and n1 < n and len(candidates) > 1:
        outcomes = [evaluator.extend(c, n1) for c in candidates]
        stage = [evaluator.stats(c, n1, deviations[a]) for a, c in enumerate(candidates)]
        paired = PairedErrors(outcomes, n1, evaluator.budget)
        leader = _leader(stage, keep)
        keep = []
        for a in range(len(candidates)):
            if a != leader and dominated(stage, paired, params, leader, a):
                first[a] = stage[a].model_copy(update={"dropped": True})
            else:
                keep.append(a)
    for a in keep:
        evaluator.extend(candidates[a], n)
    stats = [
        first[a] if a in first else evaluator.stats(c, n, deviations[a])
        for a, c in enumerate(candidates)
    ]
    all_outcomes = [evaluator.outcomes[c.label] for c in candidates]
    return Evaluation(
        stats=tuple(stats),
        best=_leader(stats, keep),
        paired=PairedErrors(all_outcomes, n, evaluator.budget),
        rollouts=evaluator.rollouts - before,
        wall_time_s=time.perf_counter() - began,
    )


def _leader(stats: Sequence[CandidateStats], among: Sequence[int]) -> int:
    """The candidate with the largest capped on-time estimate, then the smallest tardiness,
    then the first in candidate order."""
    return min(among, key=lambda a: (-stats[a].capped, stats[a].tardiness, a))


def dominated(
    stats: Sequence[CandidateStats],
    paired: PairedErrors,
    params: SentinelParams,
    leader: int,
    a: int,
) -> bool:
    """Whether a is significantly and materially worse than the leader in min(p, theta_D) and
    in T (racing, spec section 6)."""
    worse_p = stats[leader].capped - stats[a].capped
    if params.ties("on_time", worse_p, paired("on_time", leader, a)):
        return False
    worse_t = stats[a].tardiness - stats[leader].tardiness
    return not params.ties("tardiness", worse_t, paired("tardiness", leader, a))
