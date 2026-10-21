"""SUBST and RESEQ in the engine's step 3 (spec sections 3, 4 and 4.1)."""

from collections.abc import Callable, Sequence

import numpy as np
import pytest

from sentinel.forecasting.beliefs import Belief
from sentinel.forecasting.durations import duration_pmf
from sentinel.model import ProjectInstance, Schedule, validate_schedule
from sentinel.policies.base import EMPTY_DECISION, Decision, Reseq, Subst
from sentinel.policies.no_reaction import NoReaction
from sentinel.policies.resolve import FullResolve
from sentinel.scheduling.cpsat import solve_residual
from sentinel.scheduling.priority_rules import lft_priorities
from sentinel.scheduling.residual import planning_view
from sentinel.scheduling.sgs import serial_sgs
from sentinel.simulation import engine
from sentinel.simulation.engine import Run, SimulationResult, Substitution, preview, simulate
from sentinel.simulation.events import (
    AbsenceDraw,
    DisruptionParams,
    NewActivityDraw,
    ScenarioStreams,
)
from sentinel.simulation.realised import execution_violations, realised_instance
from sentinel.simulation.state import (
    EngineState,
    Observation,
    day_limit,
    nominal_world,
    onboarding_days,
)
from sentinel.simulation.uncertainty import PertParams, role_costs

Builder = Callable[..., ProjectInstance]

EXACT = PertParams(a=1.0, m=1.0, b=1.0)  # X = 1, so P_j = p_j
NONE = DisruptionParams.none()
BUSY = DisruptionParams(lambda_a=0.05, mean_absence=3, lambda_s=0.1, lambda_n=0.1)
# Frequent absences and arrivals, few D2 shocks: runs stay short with a policy at every epoch.
LIVELY = DisruptionParams(lambda_a=0.05, mean_absence=3, lambda_s=0.02, lambda_n=0.05)


class Scripted:
    """Test-only policy: a fixed decision on given days, nothing otherwise; keeps observations."""

    def __init__(self, decisions: dict[int, Decision]) -> None:
        self.decisions = decisions
        self.seen: list[Observation] = []

    def decide(self, observation: Observation) -> Decision:
        self.seen.append(observation)
        return self.decisions.get(observation.day, EMPTY_DECISION)


def forced_absences(onsets: dict[int, list[AbsenceDraw]]) -> type[ScenarioStreams]:
    """Streams with real durations, no D2 or D3 and the given absences."""

    class Forced(ScenarioStreams):
        def absence_onsets(self, day: int) -> Sequence[AbsenceDraw]:
            return onsets.get(day, [])

    return Forced


def segments_of(result: SimulationResult, j: int) -> list[tuple[int, int, tuple[int, ...]]]:
    return [(s.start, s.end, s.workers) for s in result.segments if s.activity == j]


def assert_feasible(instance: ProjectInstance, result: SimulationResult) -> None:
    realised, schedule = realised_instance(instance, result)
    assert validate_schedule(realised, schedule) == []
    assert execution_violations(instance, result) == []


def subst(activity: int, *workers: int) -> Decision:
    return Decision(operations=(Subst(activity=activity, workers=workers),))


def test_subst_on_a_paused_one_person_activity(
    build: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A (p 4) and B (p 2) need one worker each of a role with two; C (p 1) follows B and is
    # planned for day 4. A's worker 0 is out on days 1-3. On day 2 worker 1, idle since B ended,
    # replaces it: o = max(1, ceil(0.3 * 1)) = 1 crew-member day, h = 1 * 1 / 1 = 1, so A has
    # 3 + 1 days of work left and does them on days 2-5 with worker 1. Worker 0 returns on day 4
    # as an idle worker and does C.
    inst = build(
        [0, 4, 2, 1, 0], [[0], [1], [1], [1], [0]], [[1, 2], [4], [3], [4], []], capacities=(2,)
    )
    plan = Schedule(starts=(0, 0, 0, 4, 7))
    onsets = {1: [AbsenceDraw(worker=0, length=3, announced=1)]}
    monkeypatch.setattr(engine, "ScenarioStreams", forced_absences(onsets))
    policy = Scripted({2: subst(1, 1)})
    result = simulate(
        inst, plan, policy, 0, pert=EXACT, disruptions=NONE, review_period=1, debug=True
    )
    assert result.substitutions == (
        Substitution(day=2, activity=1, replaced=(0,), workers=(1,), onboarding=1, handover=1.0),
    )
    assert segments_of(result, 1) == [(0, 1, (0,)), (2, 6, (1,))]  # works on the same day
    assert segments_of(result, 3) == [(4, 5, (0,))]  # the replaced worker is idle on return
    assert result.crews[1] == (1,) and result.crews[3] == (0,)
    assert result.work[1] == 5 and result.handover_days == 1 and result.n_substituted == 1
    assert result.onboarding_days == 1
    assert result.finishes[1] == 6 and result.makespan == 6
    assert result.total_cost == 1 + 4 + 2 + 1
    assert (result.rejected, result.reseqs, result.nervousness) == ((), 0, 0)
    seen = {obs.day: obs for obs in policy.seen}
    assert seen[2].status[1] == "paused" and seen[3].status[1] == "running"
    assert seen[3].assigned[1] == (1,) and seen[3].handovers == ((1, 1.0, 1),)
    assert seen[4].present[0] and all(0 not in crew for crew in seen[4].assigned[:3])
    assert_feasible(inst, result)
    # Without the substitution A waits for worker 0 and ends on day 7.
    assert simulate(inst, plan, NoReaction(), 0, pert=EXACT, disruptions=NONE).makespan == 7


def test_onboarding_days_per_newcomer() -> None:
    # o_j = max(1, ceil(0.3 e_j)) crew-member days (spec section 3): one day at e_j = 0, the
    # ceiling ignores rounding noise (0.3 * 10 / 3 is 1.0000000000000002).
    assert onboarding_days(0.0) == 1 and onboarding_days(1.5) == 1
    assert onboarding_days(10 / 3) == 1 and onboarding_days(3.4) == 2 and onboarding_days(4.0) == 2
    assert onboarding_days(4.0, handover_factor=1.0) == 4 and onboarding_days(0.0, 1.0) == 1


@pytest.mark.parametrize(("crew", "replaced", "finish"), [(1, 1, 12), (10, 1, 11), (10, 3, 11)])
def test_handover_is_onboarding_per_newcomer(
    build: Builder, monkeypatch: pytest.MonkeyPatch, crew: int, replaced: int, finish: int
) -> None:
    # A (p 10) needs `crew` workers of a role with crew + 3; its members 0 .. replaced - 1 are
    # out from day 4 for 30 days, and on day 4 (e_A = 4) as many idle workers replace them. Each
    # needs o = max(1, ceil(0.3 * 4)) = 2 crew-member days, so 2 m crew-member days are added:
    # h = 2 m / M full-crew days, 2 for one person, 0.2 for 1 of 10, 0.6 for 3 of 10 (the v1.5
    # formula max(1, ceil(0.3 e m / M)) gave 2, 1 and 1). One person: 6 + 2 days left, F = 12;
    # 10 present on 60 + 2 m crew-member days: F = 11.
    inst = build([0, 10, 0], [[0], [crew], [0]], [[1], [2], []], capacities=(crew + 3,))
    plan = Schedule(starts=(0, 0, 10))
    onsets = {4: [AbsenceDraw(worker=w, length=30, announced=30) for w in range(replaced)]}
    monkeypatch.setattr(engine, "ScenarioStreams", forced_absences(onsets))
    substitutes = tuple(range(crew, crew + replaced))
    policy = Scripted({4: subst(1, *substitutes)})
    result = simulate(
        inst, plan, policy, 0, pert=EXACT, disruptions=NONE, review_period=1, debug=True
    )
    (done,) = result.substitutions
    assert (done.day, done.replaced, done.workers) == (4, tuple(range(replaced)), substitutes)
    assert done.onboarding == 2 and done.handover == 2 * replaced / crew
    assert result.onboarding_days == 2 * replaced and result.handover_days == 2 * replaced / crew
    assert result.work[1] == pytest.approx(10 + 2 * replaced / crew)
    seen = {obs.day: obs for obs in policy.seen}
    assert seen[5].handovers == ((1, 4.0, 2 * replaced),)  # work added in crew-member days
    assert nominal_world(seen[5]).remaining[1] == 10 * crew - 5 * crew + 2 * replaced
    assert result.finishes[1] == finish
    assert_feasible(inst, result)


def test_subst_on_a_running_partial_crew_raises_its_rate(
    build: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A (p 4) needs two of three workers; member 1 is out from day 1 for 30 days, so A runs at
    # rho = 1/2. On day 2 the idle worker 2 takes its slot: e_A = 1.5, o = max(1, ceil(0.3 *
    # 1.5)) = 1 crew-member day and h = 1 * 1 / 2 = 0.5, so 2.5 + 0.5 full-crew days remain,
    # done at rho = 1 on days 2-4: F = 5 instead of 7.
    inst = build([0, 4, 0], [[0], [2], [0]], [[1], [2], []], capacities=(3,))
    plan = Schedule(starts=(0, 0, 4))
    onsets = {1: [AbsenceDraw(worker=1, length=30, announced=30)]}
    monkeypatch.setattr(engine, "ScenarioStreams", forced_absences(onsets))
    policy = Scripted({2: subst(1, 2)})
    result = simulate(
        inst, plan, policy, 0, pert=EXACT, disruptions=NONE, review_period=1, debug=True
    )
    assert [obs.work_done[1] for obs in policy.seen] == [0, 1, 1.5, 2.5, 3.5, 4.5]
    assert segments_of(result, 1) == [(0, 1, (0, 1)), (1, 2, (0,)), (2, 5, (0, 2))]
    assert result.substitutions[0].onboarding == 1 and result.substitutions[0].handover == 0.5
    assert result.crews[1] == (0, 2) and result.onboarding_days == 1
    assert result.finishes[1] == 5 and result.work[1] == 4.5
    assert result.total_cost == 2 + 1 + 2 * 3
    assert_feasible(inst, result)
    slow = simulate(inst, plan, NoReaction(), 0, pert=EXACT, disruptions=NONE)
    assert slow.finishes[1] == 7


def rejection_case(
    build: Builder,
) -> tuple[ProjectInstance, Schedule, dict[int, list[AbsenceDraw]]]:
    """Role 0 has workers 0-2 and role 1 worker 3; A (p 4) and B (p 6) need one role-0 worker
    each and start on day 0 with workers 0 and 1; worker 0 is out on days 1-3."""
    inst = build(
        [0, 4, 6, 0],
        [[0, 0], [1, 0], [1, 0], [0, 0]],
        [[1, 2], [3], [3], []],
        capacities=(3, 1),
    )
    return inst, Schedule(starts=(0, 0, 0, 6)), {1: [AbsenceDraw(worker=0, length=3, announced=1)]}


INVALID = (
    (Subst(activity=1, workers=(1,)), "worker 1 is in the crew of activity 2"),
    (
        Subst(activity=1, workers=(3,)),
        "activity 1 has no absent member of role 1 left for worker 3",
    ),
    (Subst(activity=2, workers=(2,)), "activity 2 has no absent member"),
    (Subst(activity=3, workers=(2,)), "activity 3 is unstarted, not running or paused"),
    (Subst(activity=1, workers=(0,)), "worker 0 is absent"),
    (Subst(activity=9, workers=(2,)), "activity 9 does not exist"),
    # On day 2 only the sink is unstarted; A and B are estimated to finish on day 6.
    (
        Reseq(starts={3: 5}),
        "1 residual violations, first: activity 3 starts on day 5 before its release 6",
    ),
    (Reseq(starts={1: 3, 3: 6}), "1 residual violations, first: activity 1 is not in the residual"),
)


def test_invalid_operations_are_rejected_and_the_run_goes_on(
    build: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    inst, plan, onsets = rejection_case(build)
    monkeypatch.setattr(engine, "ScenarioStreams", forced_absences(onsets))
    operations = (*(op for op, _ in INVALID), Subst(activity=1, workers=(2,)))
    policy = Scripted({2: Decision(operations=operations)})
    result = simulate(inst, plan, policy, 0, pert=EXACT, disruptions=NONE, review_period=1)
    assert [r.day for r in result.rejected] == [2] * len(INVALID)
    for rejection, (op, reason) in zip(result.rejected, INVALID, strict=True):
        assert rejection.operation == op
        assert rejection.reason.startswith(reason), rejection.reason
    assert result.infeasible_reseqs == 2 and result.reseqs == 0 and result.nervousness == 0
    # The valid substitution after the rejected operations still applies: e_A = 1, o = h = 1.
    assert result.substitutions == (
        Substitution(day=2, activity=1, replaced=(0,), workers=(2,), onboarding=1, handover=1.0),
    )
    assert result.finishes[1] == 6 and result.makespan == 6
    realised, schedule = realised_instance(inst, result)
    assert validate_schedule(realised, schedule) == []
    assert execution_violations(inst, result) == ["2 RESEQ plans failed validate_residual"]


def test_debug_mode_raises_on_an_infeasible_reseq(
    build: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    inst, plan, onsets = rejection_case(build)
    monkeypatch.setattr(engine, "ScenarioStreams", forced_absences(onsets))
    policy = Scripted({2: Decision(operations=(Reseq(starts={3: 5}),))})
    with pytest.raises(AssertionError, match="before its release 6"):
        simulate(inst, plan, policy, 0, pert=EXACT, disruptions=NONE, review_period=1, debug=True)


def test_reseq_replaces_the_plan_and_counts_nervousness(tiny: ProjectInstance) -> None:
    # tiny: 1 (p 3, r 2) -> 3 (p 4, r 1) -> sink 4, and 2 (p 2, r 2) -> sink; capacity 3. On day
    # 0 everything is unstarted, the source included; activity 2 moves from day 3 to day 5. On
    # day 3 it moves back; activity 3 keeps its start. Each move changes one planned start.
    plan = Schedule(starts=(0, 0, 3, 3, 7))
    later = Reseq(starts={0: 0, 1: 0, 2: 5, 3: 3, 4: 7})
    back = Reseq(starts={2: 3, 3: 3, 4: 7})
    policy = Scripted({0: Decision(operations=(later,)), 3: Decision(operations=(back,))})
    result = simulate(
        tiny, plan, policy, 0, pert=EXACT, disruptions=NONE, review_period=1, debug=True
    )
    assert (result.reseqs, result.nervousness, result.rejected) == (2, 2, ())
    assert {obs.day: obs.plan[2] for obs in policy.seen}[1] == 5
    assert result.starts == (0, 0, 3, 3, 7) and result.makespan == 7
    once = Scripted({0: Decision(operations=(later,))})
    moved = simulate(tiny, plan, once, 0, pert=EXACT, disruptions=NONE, review_period=1, debug=True)
    assert moved.starts == (0, 0, 5, 3, 7) and moved.nervousness == 1


def test_deviation_set_leaves_out_milestones_the_sink_and_fresh_d3_activities(
    build: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A (p 3) -> milestone M -> B (p 2) -> sink, one worker each of a role with two. On day 1 a
    # D3 copy N of A (id 5, p 3) arrives between the source and B, planned for day 2 (spec 3.1
    # e). A RESEQ on day 1 moves M 3 -> 4, B 3 -> 5, the sink 5 -> 7 and N 2 -> 1; only B is in
    # the deviation set U'_1 (spec section 7), so the nervousness is 1. On day 2 N is no longer
    # fresh and counts.
    inst = build([0, 3, 0, 2, 0], [[0], [1], [0], [1], [0]], [[1], [2], [3], [4], []], (2,))
    plan = Schedule(starts=(0, 0, 3, 3, 5))

    class Arrival(ScenarioStreams):
        def new_activity(self, day: int) -> NewActivityDraw | None:
            # template A, PERT multiplier 1, successor B (of M, B), predecessor the source
            return NewActivityDraw(0.0, 1.0, 0.99, 0.0) if day == 1 else None

    monkeypatch.setattr(engine, "ScenarioStreams", Arrival)
    quiet = simulate(inst, plan, NoReaction(), 0, pert=EXACT, disruptions=NONE, observe_days=[1, 2])
    first, second = quiet.observations
    assert [(a.id, a.day, a.successor, a.predecessor) for a in first.inserted] == [(5, 1, 3, 0)]
    view = planning_view(first)
    assert view.activities == (2, 3, 4, 5) and view.inserted_today == (5,)
    assert [view.activities[i] for i in view.deviation_positions()] == [3]
    moved = {2: 4, 3: 5, 4: 7, 5: 1}
    assert view.deviation(moved) == 2  # B only; M, the sink and N would add 1 + 2 + 1
    stable = solve_residual(view, "stable", deterministic_time_limit=0.1, seed=0, hint=moved)
    assert stable.objective == view.deviation(stable.starts)
    later = planning_view(second)
    assert later.inserted_today == () and 5 in [
        later.activities[i] for i in later.deviation_positions()
    ]
    policy = Scripted({1: Decision(operations=(Reseq(starts=moved),))})
    result = simulate(inst, plan, policy, 0, pert=EXACT, disruptions=NONE, debug=True)
    assert (result.reseqs, result.nervousness, result.rejected) == (1, 1, ())
    assert result.starts[5] == 1 and result.starts[3] == 5
    assert_feasible(inst, result)


def test_results_without_interventions_serialise_as_before(tiny: ProjectInstance) -> None:
    """The new result and observation fields are left out of dumps while unset, so runs and
    observations without interventions keep their WP3 form (the engine regression digests)."""
    plan = Schedule(starts=(0, 0, 3, 3, 7))
    result = simulate(tiny, plan, NoReaction(), 1, pert=PertParams(), disruptions=BUSY)
    dumped = result.model_dump(mode="json")
    new = {"substitutions", "rejected", "reseqs", "nervousness", "infeasible_reseqs"}
    assert not new & set(dumped)
    assert SimulationResult.model_validate(dumped) == result
    recorder = Scripted({})
    simulate(tiny, plan, recorder, 1, pert=PertParams(), disruptions=BUSY)
    assert all("handovers" not in obs.model_dump(mode="json") for obs in recorder.seen)


def test_interventions_round_trip_through_validation(
    build: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    inst, plan, onsets = rejection_case(build)
    monkeypatch.setattr(engine, "ScenarioStreams", forced_absences(onsets))
    operations = (Reseq(starts={3: 5}), Subst(activity=1, workers=(2,)))
    policy = Scripted({2: Decision(operations=operations)})
    result = simulate(inst, plan, policy, 0, pert=EXACT, disruptions=NONE, review_period=1)
    assert result.substitutions and result.rejected
    assert SimulationResult.model_validate_json(result.model_dump_json()) == result
    seen = policy.seen[-1]
    assert seen.handovers and Observation.model_validate_json(seen.model_dump_json()) == seen


def random_instance(build: Builder, seed: int, n: int = 15) -> ProjectInstance:
    """n real activities on three roles, each with up to two later successors."""
    rng = np.random.default_rng(seed)
    capacities = (3, 4, 5)
    successors: list[set[int]] = [set() for _ in range(n + 2)]
    for j in range(1, n):
        later = np.arange(j + 1, n + 1)
        successors[j].update(rng.choice(later, size=min(2, later.size), replace=False).tolist())
    has_predecessor = set().union(*successors)
    successors[0] = {j for j in range(1, n + 1) if j not in has_predecessor}
    for j in range(1, n + 1):
        successors[j] = successors[j] or {n + 1}
    durations = [0, *rng.integers(0, 8, size=n).tolist(), 0]
    demands = [[0] * 3, *([int(rng.integers(0, c + 1)) for c in capacities] for _ in range(n))]
    return build(
        durations, [*demands, [0] * 3], [sorted(s) for s in successors], capacities=capacities
    )


class Capture:
    """Test-only wrapper: records (observation, decision) of every epoch of a policy."""

    def __init__(self, policy: FullResolve) -> None:
        self.policy = policy
        self.last: tuple[Observation, Decision] | None = None

    def decide(self, observation: Observation) -> Decision:
        decision = self.policy.decide(observation)
        self.last = (observation, decision)
        return decision


def world(instance: ProjectInstance, plan: Schedule, seed: int, policy: object) -> Run:
    streams = ScenarioStreams(seed, instance, LIVELY, PertParams())
    deadline = plan.makespan(instance) + 5
    state = EngineState(
        instance,
        plan,
        streams.durations,
        role_costs(instance, None),
        pert=PertParams(),
        disruptions=LIVELY,
        deadline=deadline,
        max_days=day_limit(instance, deadline),
    )
    return Run(state, streams, policy, review_period=3, debug=True)  # type: ignore[arg-type]


def test_preview_shows_the_state_the_engine_leaves(build: Builder) -> None:
    """At every epoch of FullResolve(subst=True) runs, `preview` of the observation and the
    decision equals what the engine shows after applying that decision."""
    checked = {"subst": 0, "reseq": 0}
    for i in range(3):
        instance = random_instance(build, seed=10 + i)
        plan = serial_sgs(instance, lft_priorities(instance), lower_is_better=True)
        for seed in range(3):
            capture = Capture(FullResolve(True, deterministic_time_limit=0.05))
            run = world(instance, plan, 50 * i + seed, capture)
            for t in range(run.state.max_days + 1):
                capture.last = None
                epoch = run.open_day(t)
                if capture.last is not None:
                    observation, decision = capture.last
                    assert preview(observation, decision) == run.state.observe()
                    kinds = {op.kind for op in decision.operations}
                    checked["subst"] += "subst" in kinds
                    checked["reseq"] += "reseq" in kinds
                if run.close_day(t, epoch):
                    break
    assert checked["subst"] > 0 and checked["reseq"] > 0, checked


def test_nominal_world_adds_handovers_at_the_observed_work(
    build: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A (p 4, one worker) works on days 0-2 (e = 3); its worker is out on days 3-5 and worker 1
    # replaces it on day 3: h = max(1, ceil(0.3 * 3)) = 1. The deterministic forecaster then
    # keeps 4 - 3 = 1 crew-member day before the handover and adds 1: 2 days remain.
    inst = build([0, 4, 0], [[0], [1], [0]], [[1], [2], []], capacities=(2,))
    plan = Schedule(starts=(0, 0, 4))
    onsets = {3: [AbsenceDraw(worker=0, length=3, announced=3)]}
    monkeypatch.setattr(engine, "ScenarioStreams", forced_absences(onsets))
    policy = Scripted({3: subst(1, 1)})
    result = simulate(
        inst, plan, policy, 0, pert=EXACT, disruptions=NONE, review_period=1, observe_days=[3]
    )
    observation = result.observations[0]
    assert observation.handovers == ((1, 3.0, 1),) and observation.work_done[1] == 3
    assert nominal_world(observation).remaining[1] == 2.0
    assert result.finishes[1] == 5  # days 3 and 4 with worker 1
    # Under the default PERT, P_A is in {3, 4, 5, 6}. P_A = 3 would have finished before the
    # handover, so the belief keeps {4, 5, 6} and samples remaining work P_A - 3 + 1.
    loose = observation.model_copy(update={"pert": PertParams()})
    pmf = duration_pmf(4, PertParams())
    assert (pmf.first, pmf.last) == (3, 6)
    conditional = pmf.at_least(4)
    assert conditional is not None
    belief = Belief(loose)
    rng = np.random.default_rng(1)
    samples = {belief.sample(rng).remaining[1] for _ in range(300)}
    assert samples == {2.0, 3.0, 4.0}
    expected = sum(p * (4 + i - 2) for i, p in enumerate(conditional.probs))
    assert belief.expected_remaining()[1] == pytest.approx(expected)
