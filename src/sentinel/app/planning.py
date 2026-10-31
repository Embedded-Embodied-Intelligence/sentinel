"""The computations of a live project (spec sections 11.3-11.5): the baseline plan, the forecast
with the tasks that threaten the deadline, the recommendation (a deliberation whose decision,
display and explanation come from one comparison on the forecast's sampled worlds, `AppSentinel`)
and the approval of a recommended action. All are deterministic for the project's seed; none is
called inside a rollout.
"""

import math
import time
from bisect import bisect_left, bisect_right
from collections.abc import Mapping, Sequence
from fractions import Fraction
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from sentinel.agent.candidates import Candidate, approve, descopes, generate, noop
from sentinel.agent.decide import (
    CandidateRecord,
    Choice,
    DecisionRecord,
    Reason,
    assess_needs,
    choose,
)
from sentinel.agent.evaluate import (
    CandidateStats,
    Evaluator,
    Outcomes,
    PairedErrors,
    dominated,
    instability,
)
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
THREAT_LIMIT = 3  # tasks that threaten the deadline, at most (spec section 11.4)
THREAT_SENSITIVITY = Fraction(1, 5)  # rank correlation with the finish day, at least (11.4)
SHOWN = 5  # alternatives shown with a recommendation besides its action, at most (11.5)
# The deciding components after min(p, theta_D), and the candidate order: the chances tie (11.5).
LATER_COMPONENTS = frozenset(("tardiness", "scope", "budget", "stability", "level", "order"))
Tie = Literal["similar", "target"]


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
    """A task that threatens the deadline (spec section 11.4): the rank correlation `sensitivity`
    of its realised duration with the finish day."""

    task: str
    sensitivity: float


class ForecastResult(_Frozen):
    """The forecast of day `day` (spec section 11.4): P(C <= D) (None without a deadline), the
    10/50/90 % quantiles and the mean of the makespan C, the tasks that threaten the deadline,
    the number of `late` rollouts, and for the budget outlook the mean total cost of the rollouts
    and the share within the budget B."""

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
    "forecast", t), keeping each rollout's final state for the realised durations: the tasks that
    threaten the deadline are the unfinished ones `rank_threats` keeps, none without a late
    rollout."""
    began = time.perf_counter()
    observation = project.observation()
    seed = derive_seed(project.definition.settings.seed, "forecast", str(observation.day))
    makespans, states = forecast_rollouts(observation, rollouts, seed)
    deadline, budget = observation.deadline, observation.budget
    ids = project.activity_ids()
    nodes = project.nodes()
    candidates = {ids[key]: key for key in threat_candidates(project, nodes)}
    late = 0 if deadline is None else sum(c > deadline for c in makespans)
    realised = {j: [realised_days(state, j) for state in states] for j in candidates}
    durations = {j: nodes[key].duration for j, key in candidates.items()}
    ranked = rank_threats(realised, makespans, durations) if late else []
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
        drivers=tuple(Driver(task=candidates[j], sensitivity=rho) for j, rho in ranked),
        late=late,
        mean_cost=float(np.mean(costs)),
        p_within_budget=None if budget is None else sum(c <= budget for c in costs) / rollouts,
        wall_time_s=time.perf_counter() - began,
    )


def realised_days(state: EngineState, j: int) -> float:
    """The realised duration of task j in a rollout's final state (spec section 11.4): its work in
    full-crew days, with all its growth, as `SimulationResult.work`."""
    # SPEC-Q: work, not F_j - S_j: days a task waits or works with part of its crew do not count.
    return (state.done[j] + state.remaining[j]) / state.unit[j]


def signed_squared_spearman(xs: Sequence[float], ys: Sequence[float]) -> Fraction:
    """The square of Spearman's rank correlation with its sign (Spearman 1904), ties sharing their
    mean rank: exact, and in the order of the correlation; 0 if a series does not vary."""

    def doubled_ranks(values: Sequence[float]) -> list[int]:
        ordered = sorted(values)
        return [bisect_left(ordered, v) + bisect_right(ordered, v) + 1 for v in values]

    x, y = doubled_ranks(xs), doubled_ranks(ys)
    n, sum_x, sum_y = len(x), sum(x), sum(y)
    covariance = n * sum(a * b for a, b in zip(x, y, strict=True)) - sum_x * sum_y
    variance_x = n * sum(a * a for a in x) - sum_x * sum_x
    variance_y = n * sum(b * b for b in y) - sum_y * sum_y
    if not variance_x or not variance_y:
        return Fraction(0)
    return Fraction(covariance * abs(covariance), variance_x * variance_y)


def rank_threats(
    realised: Mapping[int, Sequence[float]],
    finishes: Sequence[int],
    durations: Mapping[int, int],
) -> list[tuple[int, float]]:
    """The tasks that threaten the deadline with their sensitivity, highest first (spec section
    11.4; Spearman 1904): a rank correlation of at least 0.2 between the realised duration and the
    finish day, then by duration (longer first) and id, at most three; compared exactly."""
    scores = {j: signed_squared_spearman(days, finishes) for j, days in realised.items()}
    shown = [j for j, score in scores.items() if score >= THREAT_SENSITIVITY**2]
    ranked = sorted(shown, key=lambda j: (-scores[j], -durations[j], j))[:THREAT_LIMIT]
    return [(j, math.sqrt(scores[j])) for j in ranked]


def threat_candidates(project: LiveProject, nodes: Mapping[str, Node]) -> list[str]:
    """The tasks that may be named as threats to the deadline (spec section 11.4): the unfinished
    ones, neither done nor dropped."""
    # SPEC-Q: "each unfinished task" taken literally: tasks every path passes through count too.
    closed = {key for key, tracked in project.tasks.items() if tracked.state in ("done", "removed")}
    return [key for key in nodes if key not in closed]


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
    """The figures shown with a recommendation (spec section 11.5): NOOP, the chosen action and
    the alternatives shown on the `rollouts` sampled worlds of the forecast of the same day (its
    `seed`, section 11.4), so that NOOP has the forecast's chance; `impacts` in the order shown:
    the choice, the runner-up, then the other alternatives by their chance and expected delay.
    `decides`: the decision was taken on these figures (v2.0.3), so the record holds them; before
    it they were computed after a decision on other worlds (v2.0.2)."""

    seed: int
    rollouts: int
    impacts: tuple[Impact, ...]
    decides: bool = False


def half_up(value: float, digits: int = 0) -> float:
    """`value` rounded half up to `digits` decimals, the rounding of every figure shown with a
    recommendation (spec section 11.5); a share of 200 worlds often ends in a 5, so the noise of
    its binary fraction goes first (0.575 is stored just below it and is shown as 58 %)."""
    scale = 10.0**digits
    return math.floor(round(value * scale, 6) + 0.5) / scale


def shown_chance(p: float) -> float:
    """A chance as a page shows it, as a fraction: whole per cent, half up, and 0 % or 100 % only
    when exact (`Texts.pct` writes the others as "<1 %" and ">99 %")."""
    percent = half_up(100 * p)
    return (percent if p in (0.0, 1.0) else min(max(percent, 1.0), 99.0)) / 100


class Recommendation(_Frozen):
    """A recommendation as stored (spec section 11.5): the decision record of the deliberation,
    the comparison shown with it, the urgency tau_t, the seed of racing stage 1 (before v2.0.3,
    of all the deliberation's rollouts) and the planned starts the chosen action moves (deviation
    set, spec 7). `impacts` are the figures
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

    @property
    def as_shown(self) -> DecisionRecord:
        """The record the explanations use (spec section 11.5, v2.0.3): the rows of the comparison
        only, with chances and delays as the page shows them, so that every number they can cite
        is on the page. A recommendation stored before v2.0.3 keeps its record."""
        record, comparison = self.record, self.comparison
        if comparison is None or not comparison.decides:
            return record
        rows = {impact.label for impact in comparison.impacts}
        needs = record.needs
        if needs is not None:
            needs = needs.model_copy(update={"p_on_time": shown_chance(needs.p_on_time)})
        candidates = tuple(
            c.model_copy(
                update={
                    "p_on_time": shown_chance(c.p_on_time),
                    "tardiness": half_up(c.tardiness, 1),
                }
            )
            for c in record.candidates
            if c.label in rows
        )
        return record.model_copy(update={"needs": needs, "candidates": candidates})


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


def stage_one(
    evaluator: Evaluator, candidates: Sequence[Candidate], deviations: Sequence[float]
) -> list[CandidateStats]:
    """Racing stage 1 of spec section 6, as in `race`: every candidate on N_1 rollouts, the
    statistics with `dropped` set for those not tied with the stage's leader in min(p, theta_D)
    and not tied with it in T."""
    params = evaluator.params
    n1 = params.n_stage1
    outcomes = [evaluator.extend(c, n1) for c in candidates]
    stage = [evaluator.stats(c, n1, deviations[a]) for a, c in enumerate(candidates)]
    paired = PairedErrors(outcomes, n1, evaluator.budget)
    leader = min(range(len(stage)), key=lambda a: (-stage[a].capped, stage[a].tardiness, a))
    return [
        s.model_copy(
            update={"dropped": a != leader and dominated(stage, paired, params, leader, a)}
        )
        for a, s in enumerate(stage)
    ]


def comparison_set(stage: Sequence[CandidateStats], limit: int = SHOWN) -> set[int]:
    """The candidates of the comparison (spec section 11.5, v2.0.3): the survivors of stage 1,
    NOOP, and while fewer than the rows of a page (the action and `limit` alternatives) are in,
    the best of those dropped, by min(p, theta_D), T and candidate order on stage 1."""
    # SPEC-Q: "every candidate shown": a page shows what the comparison holds, so the dropped ones
    # that fill its rows join the comparison before the choice is known, and may win it.
    compared = {a for a, s in enumerate(stage) if not s.dropped or s.label == "NOOP"}
    rest = sorted(
        set(range(len(stage))) - compared, key=lambda a: (-stage[a].capped, stage[a].tardiness, a)
    )
    return compared | set(rest[: max(0, limit + 1 - len(compared))])


def contest(
    racing: Evaluator, comparing: Evaluator, candidates: Sequence[Candidate]
) -> tuple[list[CandidateStats], Choice]:
    """Racing stage 1 on the deliberation's worlds, then rule (spec section 6) on the comparison:
    the candidates of `comparison_set` on the forecast's worlds, so every one of them competes;
    the statistics of those outside it stay those of stage 1, dropped."""
    params = comparing.params
    deviations = [instability(comparing.observation, c, params.kappa_h) for c in candidates]
    first = stage_one(racing, candidates, deviations)
    compared = comparison_set(first)
    stats = [
        comparing.stats(c, FORECAST_ROLLOUTS, deviations[a]) if a in compared else first[a]
        for a, c in enumerate(candidates)
    ]
    outcomes = [comparing.outcomes.get(c.label, Outcomes()) for c in candidates]
    paired = PairedErrors(outcomes, FORECAST_ROLLOUTS, comparing.budget)
    return stats, choose(stats, params, paired)


def _candidate_records(
    stats: Sequence[CandidateStats], candidates: Sequence[Candidate], choice: Choice
) -> list[CandidateRecord]:
    return [
        CandidateRecord(**s.model_dump(), decision=c.decision, eliminated=out)
        for s, c, out in zip(stats, candidates, choice.eliminated, strict=True)
    ]


class AppSentinel(Sentinel):
    """Sentinel in the application (spec section 11.5, v2.0.3): a deliberation decides on one
    comparison, the rest (epochs, approvals, the permission gate) is that of `Sentinel`, whose own
    deliberation, racing's stage 2 included, stays that of the research runs (spec section 6). The
    needs of NOOP are read on the N = 200 sampled worlds of the forecast of the day, racing stage
    1 runs with the deliberation's seed as in spec section 6, and the survivors and the candidates
    a page can show are evaluated on those 200 worlds, where rule (spec section 6) chooses. Each
    deliberation leaves its `Comparison` in `comparisons`, by day."""

    def __init__(
        self,
        params: SentinelParams | None = None,
        *,
        seed: int = 0,
        keep_records: bool = True,
        proposer: Proposer | None = None,
    ) -> None:
        super().__init__(params, seed=seed, keep_records=keep_records, proposer=proposer)
        self.comparisons: dict[int, Comparison] = {}

    def deliberate(self, observation: Observation, discarded: str | None = None) -> DecisionRecord:
        """Needs gate, candidates, stage 1, the comparison, the rule and the permission gate at
        one epoch; `discarded` names an approved action no longer valid."""
        began = time.perf_counter()
        params, stats = self.params, self.stats
        t = observation.day
        stats.deliberations += 1
        comparing = Evaluator(observation, derive_seed(self.seed, "forecast", str(t)), params)
        # SPEC-Q: "stage 1 stays as in section 6": also its worlds, the deliberation's seed.
        racing = Evaluator(observation, derive_seed(self.seed, "sentinel", str(t)), params)
        racing.plans = comparing.plans  # a plan part depends on its objective and view only
        base = noop(observation)
        # SPEC-Q: the needs gate is part of the decision, so it reads the same 200 worlds.
        needs = assess_needs(comparing, base, stage1=FORECAST_ROLLOUTS, rollouts=FORECAST_ROLLOUTS)
        if needs.met:
            stats.gate_exits += 1
            stats.rollouts += comparing.rollouts
            done = time.perf_counter()
            stats.deliberation_s.append(done - began)
            record = DecisionRecord(
                day=t,
                deliberated=True,
                rule=params.rule,
                reason="needs_met",
                chosen=base.label,
                decision=base.decision,
                discarded=discarded,
                needs=needs,
                rollouts=comparing.rollouts,
                evaluation_s=done - began,
                wall_time_s=done - began,
            )
            self.comparisons[t] = compare(record, comparing)
            return record
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
            table, choice = contest(racing, comparing, candidates)
            if params.descope and not any(c.kind == "descope" for c in candidates):
                best_p = max(s.p_on_time for s in table if not s.dropped)
                extra = descopes(observation, params) if best_p < params.theta_d else []
                if extra:
                    candidates += extra
                    table, choice = contest(racing, comparing, candidates)
            index, reason, runner, tied = choice.index, choice.reason, choice.runner_up, choice.ties
            records = _candidate_records(table, candidates, choice)
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
                rollouts=racing.rollouts + comparing.rollouts,
            )
            proposed = list(self.proposer(observation, rule, tuple(candidates)))
            stats.proposed += len(proposed)
            if proposed:
                candidates += proposed
                table, choice = contest(racing, comparing, candidates)
                index, reason = choice.index, choice.reason
                runner, tied = choice.runner_up, choice.ties
                records = _candidate_records(table, candidates, choice)
        stats.candidates += len(candidates)
        chosen = candidates[index]
        stats.chosen[chosen.kind] = stats.chosen.get(chosen.kind, 0) + 1
        gate, decision = self.gate(observation, chosen)
        rollouts = racing.rollouts + comparing.rollouts
        stats.rollouts += rollouts
        stats.replan_solves += racing.replan_solves + comparing.replan_solves
        stats.replans_reused += racing.replans_reused + comparing.replans_reused
        done = time.perf_counter()
        stats.deliberation_s.append(done - began)
        record = DecisionRecord(
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
            rollouts=rollouts,
            cp_solves=generation.solves,
            cp_fallbacks=generation.fallbacks,
            generation_s=generation.wall_time_s,
            evaluation_s=done - evaluated,
            wall_time_s=done - began,
        )
        self.comparisons[t] = compare(record, comparing)
        return record


def recommend(project: LiveProject, *, proposer: Proposer | None = None) -> Recommendation:
    """A deliberation on the current observation with its comparison (spec sections 6 and 11.5,
    `AppSentinel`)."""
    observation = project.observation()
    if observation.deadline is None:
        raise LiveError([issue("no_deadline")])
    if project.finished:
        raise LiveError([issue("project_finished")])
    params = sentinel_params(project)
    seed = project.definition.settings.seed
    sentinel = AppSentinel(params, seed=seed, keep_records=False, proposer=proposer)
    record = sentinel.deliberate(observation)
    chosen = next((c for c in record.candidates if c.label == record.chosen), None)
    return Recommendation(
        day=observation.day,
        seed=derive_seed(seed, "sentinel", str(observation.day)),
        record=record,
        urgency=_finite(Sentinel.urgency(observation)),
        changes=() if chosen is None else plan_changes(project, observation, chosen.decision),
        comparison=sentinel.comparisons[observation.day],
    )


def shown_labels(record: DecisionRecord, limit: int = SHOWN) -> list[str]:
    """The candidates a recommendation shows (spec section 11.5), in order: the chosen one, then
    at most `limit` alternatives of the comparison (the runner-up first, then the others by
    min(p, theta_D) and T), NOOP always among them."""
    others = sorted(
        (c for c in record.candidates if c.label != record.chosen and not c.dropped),
        key=lambda c: (c.label != record.runner_up, -c.capped, c.tardiness),
    )
    labels = [c.label for c in others[:limit]]
    if record.chosen != "NOOP" and "NOOP" not in labels:
        labels = [*labels[: limit - 1], "NOOP"]
    return [record.chosen, *labels]


def compare(record: DecisionRecord, evaluator: Evaluator) -> Comparison:
    """The rows of `shown_labels` from the rollouts the decision was taken on, those of
    `evaluator` on the forecast's worlds (spec section 11.5, v2.0.3); NOOP's are the forecast's
    (common random numbers, spec 2.3) and every figure equals the record's."""
    rollouts = FORECAST_ROLLOUTS
    rows = {c.label: c for c in record.candidates}
    impacts: list[Impact] = []
    for label in shown_labels(record):
        row = rows.get(label)
        outcomes = evaluator.outcomes[label]
        mean_cost = math.fsum(outcomes.cost[:rollouts]) / rollouts
        impacts.append(
            Impact(
                label=label,
                kind="noop" if row is None else row.kind,
                p_on_time=sum(outcomes.on_time[:rollouts]) / rollouts,
                tardiness=sum(outcomes.tardiness[:rollouts]) / rollouts,
                mean_cost=mean_cost,
                overrun=evaluator.overrun(mean_cost),
                rollouts=rollouts,
                mean_makespan=float(np.mean(outcomes.makespan[:rollouts])),
            )
        )
    chosen, *others = impacts
    others.sort(key=lambda i: (i.label != record.runner_up, -i.p_on_time, i.tardiness))
    return Comparison(
        seed=evaluator.seed, rollouts=rollouts, impacts=(chosen, *others), decides=True
    )


def tie_kind(record: DecisionRecord, comparison: Comparison, params: SentinelParams) -> Tie | None:
    """Which sentence a page adds (spec sections 11.5 item 7 and 11.7, v2.0.4), None if it adds
    none: only when a row shown has a strictly higher chance than the chosen action's, both in
    whole per cent as shown, which only a component after min(p, theta_D) can leave standing.
    "target" where the chosen action is within epsilon_D of theta_D (the cap of the rule makes
    them tie), else "similar"."""
    if record.reason not in LATER_COMPONENTS:
        return None
    chosen, *others = comparison.impacts
    if all(shown_chance(i.p_on_time) <= shown_chance(chosen.p_on_time) for i in others):
        return None
    return "target" if chosen.p_on_time >= params.theta_d - params.eps_d else "similar"


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
