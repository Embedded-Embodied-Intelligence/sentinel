"""The computations of a live project (spec sections 11.3-11.5): the baseline plan, the forecast
with the tasks that threaten the deadline, the recommendation (a Sentinel deliberation, then the
comparison shown with it on the forecast's sampled worlds) and the approval of a recommended
action. All are deterministic for the project's seed; none is called inside a rollout.
"""

import math
import time
from collections import Counter, defaultdict
from collections.abc import Mapping

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from sentinel.agent.candidates import Candidate, approve, noop
from sentinel.agent.decide import CandidateRecord, DecisionRecord
from sentinel.agent.evaluate import Evaluator
from sentinel.agent.params import SentinelParams
from sentinel.app.live import Baseline, LiveError, LiveProject, Model, Node, issue
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
FORECAST_ROLLOUTS = 200  # N of the forecast and of the comparison shown (spec 5.2, 11.4, 11.5)
DRIVERS = 5  # tasks that threaten the deadline, at most
SHOWN = 5  # alternatives shown with a recommendation besides its action, at most (11.5)


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
    """A task that threatens the deadline (spec section 11.4): on the critical chain of `share`
    of the late rollouts."""

    task: str
    share: float


class ForecastResult(_Frozen):
    """The forecast of day `day` (spec section 11.4): P(C <= D) (None without a deadline), the
    10/50/90 % quantiles and the mean of the makespan C, the tasks that threaten the deadline
    with the number of `late` rollouts they are counted over, and for the budget outlook the
    mean total cost of the rollouts and the share within the budget B."""

    day: int
    seed: int
    rollouts: int
    p_on_time: float | None
    quantiles: tuple[int, int, int]
    mean: float
    truncated: int
    drivers: tuple[Driver, ...]
    late: int = 0
    mean_cost: float = 0.0
    p_within_budget: float | None = None
    wall_time_s: float = Field(default=0.0, exclude=True)


def forecast(project: LiveProject, *, rollouts: int = FORECAST_ROLLOUTS) -> ForecastResult:
    """NoReaction rollouts from the current observation (spec sections 5.1 and 11.4), exactly
    those of `sentinel.forecasting.forecast.forecast` with the seed derive_seed(project seed,
    "forecast", t), keeping each rollout's final state for its critical chain: the tasks that
    threaten the deadline are ranked by their share of the completed late rollouts (C > D)
    whose chain holds them, structural, zero-duration and finished tasks left out."""
    began = time.perf_counter()
    observation = project.observation()
    seed = derive_seed(project.definition.settings.seed, "forecast", str(observation.day))
    makespans, states = forecast_rollouts(observation, rollouts, seed)
    deadline, budget = observation.deadline, observation.budget
    ids = project.activity_ids()
    nodes = project.nodes()
    candidates = {ids[key]: key for key in threat_candidates(project, nodes)}
    late = [
        state
        for state, makespan in zip(states, makespans, strict=True)
        if deadline is not None and makespan > deadline and state.start[state.sink] is not None
    ]
    counts: Counter[int] = Counter()
    for state in late:
        counts.update(j for j in critical_chain(state) if j in candidates)
    ranked = sorted(counts, key=lambda j: (-counts[j], -nodes[candidates[j]].duration, j))
    costs = [state.cost for state in states]
    q10, q50, q90 = (int(np.quantile(makespans, q, method="inverted_cdf")) for q in QUANTILES)
    return ForecastResult(
        day=observation.day,
        seed=seed,
        rollouts=rollouts,
        p_on_time=None if deadline is None else sum(c <= deadline for c in makespans) / rollouts,
        quantiles=(q10, q50, q90),
        mean=float(np.mean(makespans)),
        truncated=sum(state.start[state.sink] is None for state in states),
        drivers=tuple(
            Driver(task=candidates[j], share=counts[j] / len(late)) for j in ranked[:DRIVERS]
        ),
        late=len(late),
        mean_cost=float(np.mean(costs)),
        p_within_budget=None if budget is None else sum(c <= budget for c in costs) / rollouts,
        wall_time_s=time.perf_counter() - began,
    )


def threat_candidates(project: LiveProject, nodes: Mapping[str, Node]) -> list[str]:
    """The tasks that may be named as threats to the deadline (spec section 11.4): not
    structural, of positive duration, and neither done nor dropped."""
    dropped = {key for key, tracked in project.tasks.items() if tracked.state == "removed"}
    done = {key for key, tracked in project.tasks.items() if tracked.state == "done"}
    optional = {key for key, node in nodes.items() if node.optional}
    skeleton = structural(nodes, optional | dropped)
    return [
        key
        for key, node in nodes.items()
        if key not in skeleton and key not in done | dropped and node.duration > 0
    ]


def structural(nodes: Mapping[str, Node], left_out: set[str]) -> set[str]:
    """The tasks that every source-sink path passes through (spec section 11.4) in the network
    of the required tasks, without the tasks `left_out` (the optional ones and those dropped,
    which have no edges any more): a task is structural if no path reaches the sink without
    it."""
    graph = {
        key: [s for s in node.successors if s not in left_out]
        for key, node in nodes.items()
        if key not in left_out
    }
    firsts = [key for key in graph if not any(p in graph for p in nodes[key].predecessors)]

    def bypassed(avoid: str) -> bool:
        """Whether a path from the source reaches the sink without `avoid`."""
        stack = [key for key in firsts if key != avoid]
        seen = set(stack)
        while stack:
            key = stack.pop()
            if not graph[key]:
                return True
            for successor in graph[key]:
                if successor != avoid and successor not in seen:
                    seen.add(successor)
                    stack.append(successor)
        return False

    return {key for key in graph if not bypassed(key)}


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


class Comparison(_Frozen):
    """The figures shown with a recommendation (spec section 11.5, v2.0.2): NOOP, the chosen
    action and the alternatives shown, evaluated after the deliberation on the `rollouts`
    sampled worlds of the forecast of the same day (its `seed`, section 11.4), so that NOOP has
    the forecast's chance; `impacts` in the order shown: the choice, the runner-up, then the
    other alternatives by their chance and expected delay."""

    seed: int
    rollouts: int
    impacts: tuple[Impact, ...]


class Recommendation(_Frozen):
    """A recommendation as stored (spec section 11.5): the decision record of the deliberation,
    the comparison shown with it, the urgency tau_t, the seed of the epoch's rollouts and the
    planned starts the chosen action moves (deviation set, spec 7). `impacts` are the figures
    of recommendations stored before v2.0.2 (NOOP, the choice and the runner-up on their own
    rollouts of the deliberation), shown when there is no comparison."""

    day: int
    seed: int
    record: DecisionRecord
    impacts: tuple[Impact, ...] = ()
    urgency: float | None
    changes: tuple[PlanChange, ...] = ()
    comparison: Comparison | None = None

    @property
    def chosen(self) -> CandidateRecord | None:
        return next((c for c in self.record.candidates if c.label == self.record.chosen), None)

    @property
    def acts(self) -> bool:
        """Whether it recommends an action other than NOOP."""
        return self.record.chosen != "NOOP" and self.chosen is not None

    @property
    def shown(self) -> tuple[Impact, ...]:
        """The figures shown: the comparison's, else those stored before v2.0.2."""
        return self.impacts if self.comparison is None else self.comparison.impacts

    def impact(self, label: str) -> Impact | None:
        return next((i for i in self.shown if i.label == label), None)


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
    """A Sentinel deliberation on the current observation (spec sections 6 and 11.5), then the
    comparison shown with it: NOOP, the chosen candidate and the alternatives shown on the
    sampled worlds of the forecast of the day (`compare`)."""
    observation = project.observation()
    if observation.deadline is None:
        raise LiveError([issue("no_deadline")])
    if project.finished:
        raise LiveError([issue("project_finished")])
    params = sentinel_params(project)
    seed = project.definition.settings.seed
    sentinel = Sentinel(params, seed=seed, keep_records=False, proposer=proposer)
    record = sentinel.deliberate(observation)
    chosen = next((c for c in record.candidates if c.label == record.chosen), None)
    return Recommendation(
        day=observation.day,
        seed=derive_seed(seed, "sentinel", str(observation.day)),
        record=record,
        urgency=_finite(Sentinel.urgency(observation)),
        changes=() if chosen is None else plan_changes(project, observation, chosen.decision),
        comparison=compare(observation, record, params, seed),
    )


def shown_labels(record: DecisionRecord, limit: int = SHOWN) -> list[str]:
    """The candidates a recommendation shows (spec section 11.5), in order: the chosen one,
    then at most `limit` alternatives (the runner-up first, then those racing kept, then the
    rest by min(p, theta_D) and T), and NOOP last if it is not among them."""
    others = sorted(
        (c for c in record.candidates if c.label != record.chosen),
        key=lambda c: (c.label != record.runner_up, c.dropped, -c.capped, c.tardiness),
    )
    labels = [record.chosen, *(c.label for c in others[:limit])]
    return labels if "NOOP" in labels else [*labels, "NOOP"]


def compare(
    observation: Observation,
    record: DecisionRecord,
    params: SentinelParams,
    project_seed: int,
    rollouts: int = FORECAST_ROLLOUTS,
) -> Comparison:
    """The comparison shown with a recommendation (spec section 11.5, v2.0.2): the candidates
    of `shown_labels` on the sampled worlds of the forecast of the observed day, its seed
    derive_seed(project seed, "forecast", t) and `rollouts` (N = 200), so that NOOP's rollouts
    are the forecast's (common random numbers, spec 2.3). The decision is not revisited."""
    seed = derive_seed(project_seed, "forecast", str(observation.day))
    evaluator = Evaluator(observation, seed, params)
    records = {c.label: c for c in record.candidates}
    impacts: list[Impact] = []
    for label in shown_labels(record):
        stats = records.get(label)
        if stats is None and label != "NOOP":
            continue
        candidate = noop(observation) if stats is None else candidate_of(stats, observation)
        outcomes = evaluator.extend(candidate, rollouts)
        mean_cost = math.fsum(outcomes.cost) / rollouts
        impacts.append(
            Impact(
                label=label,
                kind=candidate.kind,
                p_on_time=sum(outcomes.on_time) / rollouts,
                tardiness=sum(outcomes.tardiness) / rollouts,
                mean_cost=mean_cost,
                overrun=evaluator.overrun(mean_cost),
                rollouts=rollouts,
                mean_makespan=float(np.mean(outcomes.makespan)),
            )
        )
    chosen, *others = impacts
    others.sort(key=lambda i: (i.label != record.runner_up, -i.p_on_time, i.tardiness))
    return Comparison(seed=seed, rollouts=rollouts, impacts=(chosen, *others))


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
