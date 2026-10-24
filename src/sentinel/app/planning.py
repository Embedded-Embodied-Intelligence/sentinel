"""The computations of a live project (spec sections 11.3-11.5): the baseline plan, the forecast
with its risk drivers, the recommendation (a Sentinel deliberation with the effect of its main
candidates) and the approval of a recommended action. All are deterministic for the project's
seed; none is called inside a rollout.
"""

import math
import time
from collections import defaultdict

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from sentinel.agent.candidates import Candidate, approve, noop
from sentinel.agent.decide import CandidateRecord, DecisionRecord
from sentinel.agent.evaluate import Evaluator
from sentinel.agent.params import SentinelParams
from sentinel.app.live import Baseline, LiveError, LiveProject, Model, issue
from sentinel.experiments.runs import derive_seed
from sentinel.forecasting.beliefs import Belief
from sentinel.forecasting.forecast import QUANTILES, REVIEW_PERIOD, rollout_streams
from sentinel.model import Schedule, validate_schedule
from sentinel.policies.base import Decision, Reseq, Shift
from sentinel.policies.no_reaction import NoReaction
from sentinel.policies.sentinel import Proposer, Sentinel
from sentinel.scheduling.cpsat import solve_cpsat
from sentinel.scheduling.priority_rules import lft_priorities
from sentinel.scheduling.sgs import serial_sgs
from sentinel.simulation.engine import Run
from sentinel.simulation.state import EngineState, Observation, state_from_observation

T_CP = 0.1  # deterministic seconds of CP-SAT per plan (spec section 8)
CP_SEED = 0  # CP-SAT seed, as in the policies (spec section 7)
FORECAST_ROLLOUTS = 200  # N of the forecast (spec sections 5.2 and 11.4)
DRIVERS = 5  # risk drivers shown


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def baseline_plan(model: Model, *, deterministic_time_limit: float = T_CP) -> Baseline:
    """The baseline plan (spec section 11.3): CP-SAT with one worker, a fixed seed and the
    deterministic limit T_cp, else one serial SGS pass with the LFT rule (Kolisch 1996);
    checked by `validate_schedule` (CLAUDE.md invariant 6)."""
    began = time.perf_counter()
    instance = model.instance
    result = solve_cpsat(
        instance,
        time_limit_s=math.inf,  # only the deterministic limit stops the search
        num_workers=1,
        random_seed=CP_SEED,
        deterministic_time_limit=deterministic_time_limit,
    )
    if result.schedule is not None:
        schedule, method, status = result.schedule, "cpsat", result.status
        lower_bound = result.lower_bound
    else:
        schedule = serial_sgs(instance, lft_priorities(instance), lower_is_better=True)
        method, status, lower_bound = "sgs_lft", "FEASIBLE", None
    violations = validate_schedule(instance, schedule)
    if violations:
        raise RuntimeError(f"the baseline plan violates spec 1.3: {violations[0].detail}")
    starts = {key: schedule.starts[j] for key, j in model.task_ids.items()}
    return Baseline(
        starts=starts,
        makespan=schedule.makespan(instance),
        method="cpsat" if method == "cpsat" else "sgs_lft",
        status=status,
        lower_bound=lower_bound,
        wall_time_s=time.perf_counter() - began,
    )


# --------------------------------------------------------------------------- forecast


class Driver(_Frozen):
    """A task on the critical chain of `share` of the rollouts (spec section 11.4)."""

    task: str
    share: float


class ForecastResult(_Frozen):
    """The forecast of day `day` (spec section 11.4): P(C <= D) (None without a deadline), the
    10/50/90 % quantiles and the mean of the makespan C, and the risk drivers."""

    day: int
    seed: int
    rollouts: int
    p_on_time: float | None
    quantiles: tuple[int, int, int]
    mean: float
    truncated: int
    drivers: tuple[Driver, ...]
    wall_time_s: float = Field(default=0.0, exclude=True)


def forecast(project: LiveProject, *, rollouts: int = FORECAST_ROLLOUTS) -> ForecastResult:
    """NoReaction rollouts from the current observation (spec sections 5.1 and 11.4), exactly
    those of `sentinel.forecasting.forecast.forecast` with the seed derive_seed(project seed,
    "forecast", t), keeping each rollout's final state for its critical chain."""
    began = time.perf_counter()
    observation = project.observation()
    seed = derive_seed(project.definition.settings.seed, "forecast", str(observation.day))
    makespans, states = forecast_rollouts(observation, rollouts, seed)
    counts: defaultdict[int, int] = defaultdict(int)
    for state in states:
        if state.start[state.sink] is not None:
            for j in critical_chain(state):
                counts[j] += 1
    ids = project.activity_ids()
    keys = {j: key for key, j in ids.items()}
    nodes = project.nodes()
    ranked = sorted(
        (j for j in counts if j in keys),
        key=lambda j: (-counts[j], -nodes[keys[j]].duration, j),
    )
    deadline = observation.deadline
    q10, q50, q90 = (int(np.quantile(makespans, q, method="inverted_cdf")) for q in QUANTILES)
    return ForecastResult(
        day=observation.day,
        seed=seed,
        rollouts=rollouts,
        p_on_time=None if deadline is None else sum(c <= deadline for c in makespans) / rollouts,
        quantiles=(q10, q50, q90),
        mean=float(np.mean(makespans)),
        truncated=sum(state.start[state.sink] is None for state in states),
        drivers=tuple(Driver(task=keys[j], share=counts[j] / rollouts) for j in ranked[:DRIVERS]),
        wall_time_s=time.perf_counter() - began,
    )


def forecast_rollouts(
    observation: Observation, rollouts: int, seed: int
) -> tuple[list[int], list[EngineState]]:
    """The makespans and final states of the forecaster's rollouts (spec 5.1; ADR-0009)."""
    belief = Belief(observation)
    plan = Schedule(starts=observation.plan)
    params = observation.disruptions
    makespans: list[int] = []
    states: list[EngineState] = []
    for i in range(rollouts):
        root = np.random.SeedSequence(derive_seed(seed, "rollout", str(i)))
        belief_seq, future_seq = root.spawn(2)
        world = belief.sample(np.random.Generator(np.random.PCG64(belief_seq)))
        state = state_from_observation(observation, world, plan=plan.starts)
        streams = rollout_streams(observation, world, params, future_seq)
        Run(state, streams, NoReaction(), review_period=REVIEW_PERIOD, record_events=False).resume()
        finish = state.start[state.sink]
        makespans.append(state.max_days if finish is None else finish)
        states.append(state)
    return makespans, states


def critical_chain(state: EngineState) -> set[int]:
    """The activities of a completed run from which tight links lead to the sink (spec section
    11.4): i -> j is tight if i precedes j and F_i = S_j, or, for a j without such a
    predecessor, if F_i = S_j and i and j need a common role."""
    n = len(state.status)
    predecessors: list[list[int]] = [[] for _ in range(n)]
    for i, successors in enumerate(state.successors):
        for j in successors:
            predecessors[j].append(i)
    finishing: defaultdict[int, list[int]] = defaultdict(list)
    for i, finish in enumerate(state.finish):
        if finish is not None:
            finishing[finish].append(i)
    critical: set[int] = set()
    stack = [state.sink]
    while stack:
        j = stack.pop()
        start = state.start[j]
        if start is None:
            continue
        tight = [i for i in predecessors[j] if state.finish[i] == start]
        if not tight:
            roles = {k for k, _ in state.demands[j]}
            tight = [
                i
                for i in finishing.get(start, ())
                if i != j and any(k in roles for k, _ in state.demands[i])
            ]
        for i in tight:
            if i not in critical:
                critical.add(i)
                stack.append(i)
    return critical


# --------------------------------------------------------------------------- recommendations


class Impact(_Frozen):
    """A candidate's statistics on its rollouts (spec sections 5 and 11.5): p, T, the expected
    total cost z and the overrun o, and the mean makespan C-bar (None if not computed)."""

    label: str
    kind: str
    p_on_time: float
    tardiness: float
    mean_cost: float
    overrun: float
    rollouts: int
    mean_makespan: float | None = None


class PlanChange(_Frozen):
    """A planned start the recommended action moves, by task key (spec section 11.5)."""

    task: str
    old: int
    new: int


class Recommendation(_Frozen):
    """A recommendation as stored (spec section 11.5): the decision record of the deliberation,
    the impacts of NOOP, the choice and the runner-up, the urgency tau_t, the seed of the
    epoch's rollouts and the planned starts the chosen action moves (deviation set, spec 7)."""

    day: int
    seed: int
    record: DecisionRecord
    impacts: tuple[Impact, ...]
    urgency: float | None
    changes: tuple[PlanChange, ...] = ()

    @property
    def chosen(self) -> CandidateRecord | None:
        return next((c for c in self.record.candidates if c.label == self.record.chosen), None)

    @property
    def acts(self) -> bool:
        """Whether it recommends an action other than NOOP."""
        return self.record.chosen != "NOOP" and self.chosen is not None

    def impact(self, label: str) -> Impact | None:
        return next((i for i in self.impacts if i.label == label), None)


def sentinel_params(project: LiveProject) -> SentinelParams:
    """Sentinel's parameters for the project: spec section 8, the project's autonomy Lambda and
    DESCOPE candidates if it has optional tasks (spec section 11.5)."""
    observation_optional = any(
        node.optional
        for key, node in project.nodes().items()
        if project.tasks[key].state == "unstarted"
    )
    return SentinelParams(
        autonomy=project.definition.settings.autonomy, descope=observation_optional
    )


def recommend(project: LiveProject, *, proposer: Proposer | None = None) -> Recommendation:
    """A Sentinel deliberation on the current observation (spec sections 6 and 11.5) and the
    impacts of NOOP, the chosen candidate and the runner-up, whose rollouts are those of the
    deliberation (the same seed and worlds; checked against the record)."""
    observation = project.observation()
    if observation.deadline is None:
        raise LiveError([issue("no_deadline")])
    if project.finished:
        raise LiveError([issue("project_finished")])
    params = sentinel_params(project)
    seed = project.definition.settings.seed
    sentinel = Sentinel(params, seed=seed, keep_records=False, proposer=proposer)
    record = sentinel.deliberate(observation)
    epoch_seed = derive_seed(seed, "sentinel", str(observation.day))
    evaluator = Evaluator(observation, epoch_seed, params)
    impacts = []
    wanted = [label for label in ("NOOP", record.chosen, record.runner_up) if label is not None]
    for label in dict.fromkeys(wanted):
        stats = next((c for c in record.candidates if c.label == label), None)
        if stats is None and label == "NOOP" and record.needs is not None:
            impacts.append(_noop_impact(evaluator, observation, record))
            continue
        if stats is None:
            continue
        outcomes = evaluator.extend(candidate_of(stats, observation), stats.rollouts)
        on_time = sum(outcomes.on_time[: stats.rollouts]) / stats.rollouts
        if abs(on_time - stats.p_on_time) > 1e-12:
            raise RuntimeError(f"{label}: P(on time) {on_time} differs from the record's")
        impacts.append(
            Impact(
                label=label,
                kind=stats.kind,
                p_on_time=stats.p_on_time,
                tardiness=stats.tardiness,
                mean_cost=stats.mean_cost,
                overrun=stats.overrun,
                rollouts=stats.rollouts,
                mean_makespan=float(np.mean(outcomes.makespan[: stats.rollouts])),
            )
        )
    chosen = next((c for c in record.candidates if c.label == record.chosen), None)
    return Recommendation(
        day=observation.day,
        seed=epoch_seed,
        record=record,
        impacts=tuple(impacts),
        urgency=_finite(Sentinel.urgency(observation)),
        changes=() if chosen is None else plan_changes(project, observation, chosen.decision),
    )


def plan_changes(
    project: LiveProject, observation: Observation, decision: Decision
) -> tuple[PlanChange, ...]:
    """The planned starts a decision's RESEQ or SHIFT moves, over the deviation set U'_t
    (unstarted tasks not added on the day; spec sections 7 and 7.1)."""
    keys = {j: key for key, j in project.activity_ids().items()}
    fresh = {act.id for act in observation.inserted if act.day == observation.day}
    moved: dict[int, int] = {}
    for op in decision.operations:
        if isinstance(op, Reseq | Shift):
            moved.update(op.starts)
    return tuple(
        PlanChange(task=keys[j], old=observation.plan[j], new=start)
        for j, start in sorted(moved.items())
        if j in keys and j not in fresh and start != observation.plan[j]
    )


def _noop_impact(evaluator: Evaluator, observation: Observation, record: DecisionRecord) -> Impact:
    """NOOP's impact when the needs gate stopped the deliberation (no candidate statistics)."""
    assert record.needs is not None
    n = record.needs.rollouts
    outcomes = evaluator.extend(noop(observation), n)
    cost = float(np.mean(outcomes.cost[:n]))
    return Impact(
        label="NOOP",
        kind="noop",
        p_on_time=record.needs.p_on_time,
        tardiness=float(np.mean(outcomes.tardiness[:n])),
        mean_cost=cost,
        overrun=evaluator.overrun(cost),
        rollouts=n,
        mean_makespan=float(np.mean(outcomes.makespan[:n])),
    )


def _finite(value: float) -> float | None:
    return value if math.isfinite(value) else None


def candidate_of(stats: CandidateRecord, observation: Observation) -> Candidate:
    """The candidate of a record entry: its label, kind and decision, which is all that its
    rollouts and its approval use (`Evaluator.play`, `approve`)."""
    return Candidate(
        label=stats.label,
        kind=stats.kind,
        decision=stats.decision,
        plan=observation.plan,
        substituted=stats.substituted,
        scope_loss=stats.scope_loss,
    )


def approval(project: LiveProject, recommendation: Recommendation) -> tuple[Candidate, str | None]:
    """The recommended action approved on the current observation (spec sections 4 and 11.5):
    its operations re-validated and its plan part planned again; (the action as approved, None)
    or (the candidate, the reason it is no longer valid)."""
    chosen = recommendation.chosen
    if chosen is None:
        raise LiveError([issue("nothing_to_decide")])
    observation = project.observation()
    candidate = candidate_of(chosen, observation)
    prepared = approve(observation, candidate, sentinel_params(project))
    if prepared.rejection is not None:
        return candidate, prepared.rejection
    approved = candidate.model_copy(update={"decision": prepared.decision})
    return approved, None
