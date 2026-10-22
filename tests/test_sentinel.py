"""Sentinel (spec sections 5 and 6): candidates, racing evaluation, decision rule and policy."""

from collections.abc import Callable, Sequence

import numpy as np
import pytest

from sentinel.agent.candidates import (
    KINDS,
    Candidate,
    CandidateKind,
    generate,
    most_backlogged_role,
    noop,
    single_substitutions,
)
from sentinel.agent.decide import PairedSE, choose
from sentinel.agent.evaluate import CandidateStats, Evaluator, dominated, race
from sentinel.agent.params import SentinelParams
from sentinel.forecasting.forecast import forecast
from sentinel.model import ProjectInstance, Schedule, validate_schedule
from sentinel.policies.base import Decision, Reseq, Subst
from sentinel.policies.no_reaction import NoReaction
from sentinel.policies.sentinel import Sentinel
from sentinel.scheduling.priority_rules import lft_priorities
from sentinel.scheduling.sgs import serial_sgs
from sentinel.simulation import engine
from sentinel.simulation.engine import Run, SimulationResult, rehearse, simulate
from sentinel.simulation.events import AbsenceDraw, DisruptionParams, ScenarioStreams
from sentinel.simulation.realised import execution_violations, realised_instance
from sentinel.simulation.state import (
    PAUSED,
    RUNNING,
    EngineState,
    Observation,
    day_limit,
    worker_roles,
)
from sentinel.simulation.uncertainty import PertParams, derive_budget, role_costs

Builder = Callable[..., ProjectInstance]

EXACT = PertParams(a=1.0, m=1.0, b=1.0)  # X = 1, so P_j = p_j
NONE = DisruptionParams.none()
LIVELY = DisruptionParams(lambda_a=0.05, mean_absence=3, lambda_s=0.02, lambda_n=0.05)
# Few rollouts keep the tests fast; full autonomy (Lambda = 3) applies every choice at once, so
# these tests see the mechanics of WP5a without the permission gate (tests/test_gate_descope.py).
SMALL = SentinelParams(n_rollouts=16, n_stage1=8, autonomy=3)


def random_instance(build: Builder, seed: int, n: int = 12) -> ProjectInstance:
    """n real activities on two roles of five and ten workers, up to two successors each."""
    rng = np.random.default_rng(seed)
    capacities = (5, 10)
    successors: list[set[int]] = [set() for _ in range(n + 2)]
    for j in range(1, n):
        later = np.arange(j + 1, n + 1)
        successors[j].update(rng.choice(later, size=min(2, later.size), replace=False).tolist())
    has_predecessor = set().union(*successors)
    successors[0] = {j for j in range(1, n + 1) if j not in has_predecessor}
    for j in range(1, n + 1):
        successors[j] = successors[j] or {n + 1}
    durations = [0, *rng.integers(1, 7, size=n).tolist(), 0]
    demands = [[0, 0], *([int(rng.integers(0, c // 2 + 1)) for c in capacities] for _ in range(n))]
    return build(
        durations, [*demands, [0, 0]], [sorted(s) for s in successors], capacities=capacities
    )


def lft_plan(instance: ProjectInstance) -> Schedule:
    return serial_sgs(instance, lft_priorities(instance), lower_is_better=True)


def assert_feasible(instance: ProjectInstance, result: SimulationResult) -> None:
    realised, schedule = realised_instance(instance, result)
    assert validate_schedule(realised, schedule) == []
    assert execution_violations(instance, result) == []


class Recorder:
    """Test-only wrapper that keeps every observation a policy decides on."""

    def __init__(self) -> None:
        self.seen: list[Observation] = []

    def decide(self, observation: Observation) -> Decision:
        self.seen.append(observation)
        return Decision()


def lively_observations(build: Builder, count: int = 3) -> list[Observation]:
    """Epoch observations of NoReaction runs with frequent absences on random instances."""
    found: list[Observation] = []
    for i in range(count):
        instance = random_instance(build, 110 + i)
        plan = lft_plan(instance)
        recorder = Recorder()
        deadline = plan.makespan(instance) + 3
        simulate(
            instance, plan, recorder, i, pert=PertParams(), disruptions=LIVELY, deadline=deadline
        )
        found += recorder.seen[1::2]
    return found


def eligible(observation: Observation) -> set[int]:
    """Paused or running activities with an absent member for which an idle worker exists."""
    status, present, assigned = observation.status, observation.present, observation.assigned
    roles = worker_roles(observation)
    started = [j for j, s in enumerate(status) if s in (RUNNING, PAUSED)]
    busy = {w for j in started for w in assigned[j]}
    idle = {roles[w] for w, here in enumerate(present) if here and w not in busy}
    return {j for j in started for w in assigned[j] if not present[w] and roles[w] in idle}


def test_generated_candidates_are_valid_distinct_and_within_the_limits(build: Builder) -> None:
    """Every candidate passes the engine's checks, effects are distinct, SUBST candidates
    concern only eligible activities (the three most urgent), and there are at most the
    candidates of spec section 6; `no_overtime` has no OVERTIME and `max_single_subst` caps
    the single SUBSTs."""
    kinds: set[str] = set()
    observations = lively_observations(build)
    assert len(observations) >= 20
    for observation in observations:
        generation = generate(observation, params=SMALL)
        candidates = generation.candidates
        assert candidates[0].label == "NOOP" and candidates[0].decision == Decision()
        assert len({c.label for c in candidates}) == len(candidates) <= 10
        assert len({(c.decision.model_dump_json(), c.plan) for c in candidates}) == len(candidates)
        singles = [c for c in candidates if c.kind == "subst"]
        assert len(singles) <= 3
        targets = eligible(observation)
        urgent = [op.activity for op in single_substitutions(observation)]
        assert set(urgent) == targets and [c.decision.operations[0].activity for c in singles] == [
            j for j in urgent[:3] if f"SUBST({j})" in {c.label for c in candidates}
        ]
        for candidate in candidates:
            after, rejected = rehearse(observation, candidate.decision)
            assert rejected == () and after.plan == candidate.plan
            assert candidate.level == max(
                (Decision(operations=(op,)).level for op in candidate.decision.operations),
                default=0,
            )
            for op in candidate.decision.operations:
                if isinstance(op, Subst):
                    assert op.activity in targets
            kinds.add(candidate.kind)
        overtime = [c for c in candidates if c.kind == "ot_reseq_m"]
        if overtime:
            hire = overtime[0].decision.operations[0]
            assert hire.kind == "overtime" and hire.days == 2 * SMALL.review_period
            assert hire.role == most_backlogged_role(observation, 2 * SMALL.review_period)
        quiet = SMALL.model_copy(update={"variant": "no_overtime", "max_single_subst": 1})
        fewer = generate(observation, params=quiet).candidates
        assert all(c.kind != "ot_reseq_m" for c in fewer)
        assert sum(c.kind == "subst" for c in fewer) <= 1
    assert kinds >= {"noop", "shift", "reseq_m", "subst", "subst_all", "ot_reseq_m"}
    assert kinds <= set(KINDS)


def candidate(
    observation: Observation, label: str, kind: CandidateKind, decision: Decision
) -> Candidate:
    """A hand-made candidate with the plan its decision leaves."""
    after, rejected = rehearse(observation, decision)
    assert rejected == ()
    subst = sum(len(op.workers) for op in decision.operations if isinstance(op, Subst))
    return Candidate(label=label, kind=kind, decision=decision, plan=after.plan, substituted=subst)


def test_a_duplicated_candidate_gets_identical_statistics(build: Builder) -> None:
    """Common random numbers: NOOP evaluated twice, under two labels, has the same rollouts,
    which are those of the forecaster with the same seed."""
    observation = lively_observations(build, 1)[3]
    params = SMALL
    twice = [noop(observation), noop(observation).model_copy(update={"label": "NOOP again"})]
    evaluator = Evaluator(observation, 7, params)
    evaluation = race(evaluator, twice, racing=False)
    first, second = evaluation.stats
    assert first.model_dump(exclude={"label"}) == second.model_dump(exclude={"label"})
    assert evaluator.outcomes["NOOP"] == evaluator.outcomes["NOOP again"]
    plan = Schedule(starts=observation.plan)
    reference = forecast(observation, plan, n_rollouts=params.n_rollouts, seed=7)
    assert tuple(evaluator.outcomes["NOOP"].makespan) == reference.makespans
    assert first.p_on_time == reference.p_on_time(observation.deadline or 0)


def racing_case(build: Builder, monkeypatch: pytest.MonkeyPatch) -> Observation:
    """Role 0 has two workers, role 1 one. A (p 6) and B (p 2) start on day 0 with workers 0
    and 1; C (p 1, role 1) follows B and is planned on day 2; D = 8. Worker 0 is out from day 1
    (announced 1 day). The observation of day 2: A is paused with 5 days of work left, B is
    done and worker 1 idle."""
    inst = build(
        [0, 6, 2, 1, 0],
        [[0, 0], [1, 0], [1, 0], [0, 1], [0, 0]],
        [[1, 2], [4], [3], [4], []],
        capacities=(2, 1),
    )
    plan = Schedule(starts=(0, 0, 0, 2, 6))
    onsets = {1: [AbsenceDraw(worker=0, length=6, announced=1)]}

    class Forced(ScenarioStreams):
        def absence_onsets(self, day: int) -> Sequence[AbsenceDraw]:
            return onsets.get(day, [])

    monkeypatch.setattr(engine, "ScenarioStreams", Forced)
    # No disruptions after day 2, but E[L] = 3 for the posterior of the absence (spec 5.1).
    quiet = DisruptionParams(lambda_a=0.0, mean_absence=3, lambda_s=0.0, lambda_n=0.0)
    result = simulate(
        inst, plan, NoReaction(), 0, pert=EXACT, disruptions=quiet, deadline=8, observe_days=[2]
    )
    return result.observations[0]


def test_racing_keeps_the_best_candidate_by_n(
    build: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Constructed case: substituting A's absent member meets the deadline in every rollout
    (A ends on day 8 after one day of onboarding), waiting for the member only if it is back
    on day 3, and a plan that delays C to day 8 never.
    Racing drops the late plan in stage 1, keeps the best candidate by N rollouts and gives it
    the statistics it has without racing."""
    observation = racing_case(build, monkeypatch)
    late = Decision(operations=(Reseq(starts={3: 8, 4: 9}),))
    substitute = Decision(operations=(Subst(activity=1, workers=(1,)),))
    candidates = [
        noop(observation),
        candidate(observation, "late", "reseq_m", late),
        candidate(observation, "SUBST(1)", "subst", substitute),
    ]
    params = SentinelParams(n_rollouts=40, n_stage1=10, autonomy=3)
    full = race(Evaluator(observation, 3, params), candidates, racing=False)
    assert [s.p_on_time for s in full.stats][1:] == [0.0, 1.0]
    assert 0 < full.stats[0].p_on_time < 1
    raced = race(Evaluator(observation, 3, params), candidates)
    assert raced.best == full.best == 2
    assert raced.stats[2] == full.stats[2] and not raced.stats[2].dropped
    assert raced.stats[1].dropped and raced.stats[1].rollouts == 10
    assert raced.rollouts < full.rollouts
    choice = choose(raced.stats, params, raced.paired)
    assert (choice.index, choice.reason, choice.runner_up) == (2, "on_time", 0)


def stats(
    label: str,
    p: float,
    *,
    tardiness: float = 0.0,
    overrun: float = 0.0,
    deviation: float = 0.0,
    level: int = 0,
    scope: float = 0.0,
    dropped: bool = False,
    theta: float = 0.8,
) -> CandidateStats:
    """Hand-made statistics of a candidate."""
    return CandidateStats(
        label=label,
        kind="noop",
        level=level,
        delay=0,
        deviation=deviation,
        substituted=0,
        scope_loss=scope,
        rollouts=200,
        p_on_time=p,
        capped=min(p, theta),
        tardiness=tardiness,
        mean_cost=100 * (1 + overrun),
        overrun=overrun,
        utility=p - overrun - 0.01 * deviation,
        dropped=dropped,
    )


def paired(table: dict[tuple[str, int, int], float] | None = None) -> PairedSE:
    """Hand-made paired standard errors by (component, a, b) with a < b; 0 elsewhere."""
    errors = table or {}
    return lambda component, a, b: errors.get((component, min(a, b), max(a, b)), 0.0)


def pick(
    candidates: list[CandidateStats],
    se: dict[tuple[str, int, int], float] | None = None,
    params: SentinelParams | None = None,
) -> tuple[int, str, int | None]:
    choice = choose(candidates, params or SentinelParams(), paired(se))
    return choice.index, choice.reason, choice.runner_up


def test_the_rule_ties_on_the_deadline_component_unless_significant_and_material() -> None:
    """min(p, theta_D) with eps_D = 0.02 and 2 paired SE; tardiness decides the ties."""
    two = [stats("a", 0.50, tardiness=2.0), stats("b", 0.49, tardiness=1.0)]
    # Significant (0.01 > 2 x 0.001) but immaterial (< eps_D): a tie.
    assert pick(two, {("on_time", 0, 1): 0.001}) == (1, "tardiness", 0)
    apart = [stats("a", 0.50, tardiness=2.0), stats("b", 0.40, tardiness=1.0)]
    # Material (0.10 >= eps_D) but within 2 SE (<= 2 x 0.06): a tie.
    assert pick(apart, {("on_time", 0, 1): 0.06}) == (1, "tardiness", 0)
    # Significant and material: the better estimate wins, b leaves at the first component.
    choice = choose(apart, SentinelParams(), paired({("on_time", 0, 1): 0.03}))
    assert (choice.index, choice.reason, choice.runner_up) == (0, "on_time", 1)
    assert choice.eliminated == (None, "on_time") and choice.ties == (0,)
    # Above theta_D = 0.8 the component is capped, so the budget decides.
    assert pick([stats("a", 0.95, overrun=0.03), stats("b", 0.85)]) == (1, "budget", 0)


def test_the_rule_ties_tardiness_budget_and_stability_by_their_thresholds() -> None:
    # A hopeless epoch (all p = 0): T decides once its difference is significant and material.
    late = [stats("a", 0.0, tardiness=3.0, deviation=2.0), stats("b", 0.0, tardiness=4.0)]
    assert pick(late, {("tardiness", 0, 1): 0.2}) == (0, "tardiness", 1)
    assert pick(late, {("tardiness", 0, 1): 0.6}) == (1, "stability", 0)  # 1.0 <= 2 x 0.6
    near = [stats("a", 0.0, tardiness=3.0, deviation=2.0), stats("b", 0.0, tardiness=3.3)]
    assert pick(near, {("tardiness", 0, 1): 0.05}) == (1, "stability", 0)  # 0.3 < eps_T
    # Budget: eps_B = 0.01 against the paired SE of cost / B.
    cheap = [stats("a", 0.3, overrun=0.02, deviation=3.0), stats("b", 0.3, overrun=0.05)]
    assert pick(cheap, {("budget", 0, 1): 0.005}) == (0, "budget", 1)
    assert pick(cheap, {("budget", 0, 1): 0.02}) == (1, "stability", 0)  # 0.03 <= 2 x 0.02
    close = [stats("a", 0.3, overrun=0.020, deviation=3.0), stats("b", 0.3, overrun=0.025)]
    assert pick(close, {("budget", 0, 1): 0.0001}) == (1, "stability", 0)  # 0.005 < eps_B
    # Delta ties below eps_Delta = 0.5 day, the level only when equal, then the order.
    assert pick([stats("a", 0.3, deviation=1.4, level=1), stats("b", 0.3, deviation=1.0)]) == (
        1,
        "level",
        0,
    )
    assert pick([stats("a", 0.3, deviation=1.5), stats("b", 0.3, deviation=1.0, level=1)]) == (
        1,
        "stability",
        0,
    )
    assert pick([stats("a", 0.3), stats("b", 0.3)]) == (0, "order", 1)


def test_the_rule_filters_against_the_best_of_the_current_set() -> None:
    """Ties are not transitive: c ties with b but not with the best a, so it leaves at the
    first component even though its tardiness is the lowest; then T decides between a and b."""
    three = [
        stats("a", 0.500, tardiness=2.0),
        stats("b", 0.485, tardiness=1.0),
        stats("c", 0.470, tardiness=0.0),
    ]
    choice = choose(three, SentinelParams(), paired({("tardiness", 0, 1): 0.1}))
    assert choice.eliminated == ("tardiness", None, "on_time")
    assert (choice.index, choice.reason, choice.runner_up) == (1, "tardiness", 0)
    # A DESCOPE ties with NOOP on p and T (0.2 < eps_T), so the scope loss removes it; one
    # materially and significantly earlier wins on T.
    descope = [stats("NOOP", 0.0, tardiness=5.0), stats("DESCOPE", 0.0, tardiness=4.8, scope=0.3)]
    assert pick(descope) == (0, "scope", 1)
    earlier = [stats("NOOP", 0.0, tardiness=5.0), stats("DESCOPE", 0.0, tardiness=3.0, scope=0.3)]
    assert pick(earlier, {("tardiness", 0, 1): 0.1}) == (1, "tardiness", 0)
    # Dropped candidates do not compete: racing decided, the best dropped one is the runner-up.
    assert pick([stats("a", 0.9, dropped=True), stats("b", 0.1)]) == (1, "racing", 0)
    # The scalarised ablation maximises U.
    scalar = SentinelParams(variant="scalarised")
    utility = [stats("a", 0.70, overrun=0.10), stats("b", 0.65, deviation=2.0)]
    assert pick(utility, params=scalar) == (1, "utility", 0)
    assert pick(utility, {("on_time", 0, 1): 0.01}) == (0, "on_time", 1)


def test_racing_drops_only_candidates_worse_in_both_deadline_components() -> None:
    params = SentinelParams()
    worse = [stats("lead", 0.5, tardiness=1.0), stats("other", 0.3, tardiness=3.0)]
    tight = paired({("on_time", 0, 1): 0.01, ("tardiness", 0, 1): 0.1})
    assert dominated(worse, tight, params, 0, 1)
    # Material in p but within 2 SE: kept, as is one worse in p but tied in T.
    assert not dominated(worse, paired({("on_time", 0, 1): 0.15}), params, 0, 1)
    tied_t = [stats("lead", 0.5, tardiness=1.0), stats("other", 0.3, tardiness=1.4)]
    assert not dominated(tied_t, tight, params, 0, 1)
    # Hopeless: equal p, so nobody is dropped however late.
    hopeless = [stats("lead", 0.0, tardiness=1.0), stats("other", 0.0, tardiness=9.0)]
    assert not dominated(hopeless, tight, params, 0, 1)


def run_sentinel(
    instance: ProjectInstance, seed: int, deadline: int, params: SentinelParams = SMALL
) -> tuple[SimulationResult, Sentinel]:
    policy = Sentinel(params, seed=seed)
    result = simulate(
        instance,
        lft_plan(instance),
        policy,
        seed,
        pert=PertParams(),
        disruptions=LIVELY,
        deadline=deadline,
        debug=True,
    )
    return result, policy


def test_sentinel_is_deterministic_feasible_and_no_overtime_never_hires(build: Builder) -> None:
    instance = random_instance(build, 103)
    first, policy = run_sentinel(instance, 0, 27)
    again, twin = run_sentinel(instance, 0, 27)
    timing = {"generation_s", "evaluation_s", "wall_time_s"}
    assert first.model_dump() == again.model_dump()
    assert [r.model_dump(exclude=timing) for r in policy.records] == [
        r.model_dump(exclude=timing) for r in twin.records
    ]
    assert first.hired and first.n_substituted and first.reseqs
    assert_feasible(instance, first)
    assert (
        policy.stats.deliberations + policy.stats.skipped == first.n_epochs == len(policy.records)
    )
    plain, quiet = run_sentinel(
        instance, 0, 27, SMALL.model_copy(update={"variant": "no_overtime"})
    )
    assert plain.temporary == () and plain.overtime_cost == 0
    assert all(c.kind != "ot_reseq_m" for r in quiet.records for c in r.candidates)
    assert_feasible(instance, plain)


def test_sentinel_deliberates_only_at_crew_events_and_periodic_epochs(build: Builder) -> None:
    # Role 0 has workers 0-2: A (p 4) and B (p 4) start on day 0 with workers 0 and 1, worker 2
    # stays idle. Worker 2 is out on day 1 (idle: no deliberation), worker 0 on day 2 (a crew
    # member: deliberation) and both are back on days 3 and 4 (idle return: none; return to
    # A's crew: deliberation). T_r = 10, so day 0 is the only periodic epoch before the end.
    inst = build([0, 4, 4, 0], [[0], [1], [1], [0]], [[1, 2], [3], [3], []], capacities=(3,))
    plan = Schedule(starts=(0, 0, 0, 4))
    onsets = {
        1: [AbsenceDraw(worker=2, length=2, announced=2)],
        2: [AbsenceDraw(worker=0, length=2, announced=2)],
    }

    class Forced(ScenarioStreams):
        def absence_onsets(self, day: int) -> Sequence[AbsenceDraw]:
            return onsets.get(day, [])

    streams = Forced(0, inst, NONE, EXACT)
    params = SMALL.model_copy(update={"review_period": 10})
    policy = Sentinel(params, seed=1)
    state = EngineState(
        inst,
        plan,
        streams.durations,
        role_costs(inst, None),
        pert=EXACT,
        disruptions=NONE,
        deadline=6,
        max_days=day_limit(inst, 6),
        budget=derive_budget(inst, params=EXACT),
    )
    run = Run(state, streams, policy, review_period=10, debug=True)
    run.days(0)
    flags = {r.day: (r.deliberated, r.reason) for r in policy.records}
    assert {day: deliberated for day, (deliberated, _) in flags.items()} == {
        0: True,
        1: False,
        2: True,
        3: False,
        4: True,
    }
    assert flags[1][1] == "idle_events" and flags[3][1] == "idle_events"


def test_the_needs_gate_returns_noop_without_candidates(build: Builder) -> None:
    """With exact durations, no disruptions and a loose deadline NOOP is on time in every
    rollout and within budget, so each deliberation stops at the needs gate."""
    instance = random_instance(build, 104)
    plan = lft_plan(instance)
    policy = Sentinel(SMALL, seed=2)
    deadline = plan.makespan(instance) + 10
    result = simulate(instance, plan, policy, 2, pert=EXACT, disruptions=NONE, deadline=deadline)
    assert result.makespan == plan.makespan(instance)
    assert policy.stats.gate_exits == policy.stats.deliberations > 0
    assert policy.stats.candidates == 0
    for record in policy.records:
        assert record.reason == "needs_met" and record.candidates == ()
        assert record.needs is not None and record.needs.p_on_time == 1.0
        assert record.needs.rollouts == SMALL.n_rollouts and record.needs.met


def test_perfect_information_rollout_after_overtime_subst_and_reseq(build: Builder) -> None:
    """A Sentinel run that hired temporary workers, substituted and re-planned: from an
    observation after all three, with the true hidden state and no future disruptions, a
    rollout ends exactly when the world does once the world, too, stops intervening."""
    instance = random_instance(build, 103)
    whole, policy = run_sentinel(instance, 0, 27)
    first = {
        "overtime": min(temp.hired for temp in whole.temporary),
        "subst": min(sub.day for sub in whole.substitutions),
        "reseq": min(
            r.day for r in policy.records if any(op.kind == "reseq" for op in r.decision.operations)
        ),
    }
    plan = lft_plan(instance)
    streams = ScenarioStreams(0, instance, LIVELY, PertParams())
    state = EngineState(
        instance,
        plan,
        streams.durations,
        role_costs(instance, None),
        pert=PertParams(),
        disruptions=LIVELY,
        deadline=27,
        max_days=day_limit(instance, 27),
        budget=derive_budget(instance),
    )
    run = Run(state, streams, Sentinel(SMALL, seed=0), debug=True)
    day = max(first.values()) + 1
    for t in range(day):
        run.close_day(t, run.open_day(t))
    run.open_day(day)
    assert run.substitutions and run.reseqs and state.temporary
    observation, truth = state.observe(), state.hidden()
    run.policy, run.passive = NoReaction(), True
    run.streams = ScenarioStreams(0, instance, NONE, PertParams())
    run.shocks = False
    state.next_shock = [0] * len(state.next_shock)
    if not run.close_day(day, True):
        run.days(day + 1)
    rolled = forecast(
        observation,
        Schedule(starts=observation.plan),
        n_rollouts=3,
        seed=0,
        include_future_disruptions=False,
        _true_world=truth,
    )
    assert rolled.makespans == (state.start[state.sink],) * 3
