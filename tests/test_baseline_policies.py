"""The baseline policies of spec section 7: AlwaysSubstitute, FullResolve and StableResolve."""

import copy
from collections.abc import Callable, Sequence

import numpy as np
import pytest

from sentinel.forecasting.forecast import forecast
from sentinel.model import ProjectInstance, Schedule, validate_schedule
from sentinel.policies.always_substitute import AlwaysSubstitute, substitutions
from sentinel.policies.base import EMPTY_DECISION, Decision, Policy, Subst
from sentinel.policies.no_reaction import NoReaction
from sentinel.policies.registry import COMPARED, make_policy
from sentinel.policies.resolve import DisruptionMonitor, FullResolve, StableResolve
from sentinel.policies.urgency import urgencies
from sentinel.scheduling.cpsat import solve_cpsat
from sentinel.scheduling.priority_rules import lft_priorities
from sentinel.scheduling.sgs import serial_sgs
from sentinel.simulation import engine
from sentinel.simulation.engine import Run, SimulationResult, simulate
from sentinel.simulation.events import (
    Absence,
    AbsenceDraw,
    DisruptionParams,
    NewActivity,
    ScenarioStreams,
)
from sentinel.simulation.realised import execution_violations, realised_instance
from sentinel.simulation.state import EngineState, Observation, day_limit, state_from_observation
from sentinel.simulation.uncertainty import PertParams, role_costs

Builder = Callable[..., ProjectInstance]

EXACT = PertParams(a=1.0, m=1.0, b=1.0)
NONE = DisruptionParams.none()
LIVELY = DisruptionParams(lambda_a=0.05, mean_absence=3, lambda_s=0.02, lambda_n=0.05)


def forced_absences(onsets: dict[int, list[AbsenceDraw]]) -> type[ScenarioStreams]:
    class Forced(ScenarioStreams):
        def absence_onsets(self, day: int) -> Sequence[AbsenceDraw]:
            return onsets.get(day, [])

    return Forced


class Recorder:
    """Test-only wrapper that keeps the observations and decisions of a policy."""

    def __init__(self, policy: Policy) -> None:
        self.policy = policy
        self.seen: list[tuple[Observation, Decision]] = []

    def decide(self, observation: Observation) -> Decision:
        decision = self.policy.decide(observation)
        self.seen.append((observation, decision))
        return decision


class EveryEpoch(DisruptionMonitor):
    """Test-only monitor that treats every epoch as one with a new disruption."""

    def new_disruption(self, observation: Observation) -> bool:
        return True


def assert_feasible(instance: ProjectInstance, result: SimulationResult) -> None:
    realised, schedule = realised_instance(instance, result)
    assert validate_schedule(realised, schedule) == []
    assert execution_violations(instance, result) == []


def lft_plan(instance: ProjectInstance) -> Schedule:
    return serial_sgs(instance, lft_priorities(instance), lower_is_better=True)


def random_instance(build: Builder, seed: int, n: int = 12) -> ProjectInstance:
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


def test_always_substitute_with_no_idle_worker_changes_nothing(
    build: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A (p 5) needs both workers of the role; worker 1 is out on days 1-2 and B (p 2), planned
    # for day 1, waits. Nobody is idle, so AlwaysSubstitute does exactly what NoReaction does.
    inst = build([0, 5, 2, 0], [[0], [2], [1], [0]], [[1, 2], [3], [3], []], capacities=(2,))
    plan = Schedule(starts=(0, 0, 1, 5))
    onsets = {1: [AbsenceDraw(worker=1, length=2, announced=1)]}
    monkeypatch.setattr(engine, "ScenarioStreams", forced_absences(onsets))
    recorder = Recorder(AlwaysSubstitute())
    kwargs = {"pert": EXACT, "disruptions": NONE, "review_period": 1, "record_trace": True}
    substituting = simulate(inst, plan, recorder, 0, debug=True, **kwargs)  # type: ignore[arg-type]
    passive = simulate(inst, plan, NoReaction(), 0, **kwargs)  # type: ignore[arg-type]
    assert substituting == passive
    assert recorder.seen and all(d is EMPTY_DECISION for _, d in recorder.seen)
    assert any(not all(obs.present) for obs, _ in recorder.seen)


def urgent_case(
    build: Builder, monkeypatch: pytest.MonkeyPatch
) -> tuple[ProjectInstance, Schedule]:
    """A (p 5) -> C (p 6) -> sink and B (p 2) -> sink, one worker each of a role with three;
    A and B start on day 0 with workers 0 and 1, and both are out on days 1-4."""
    inst = build(
        [0, 5, 2, 6, 0], [[0], [1], [1], [1], [0]], [[1, 2], [3], [4], [4], []], capacities=(3,)
    )
    onsets = {1: [AbsenceDraw(worker=w, length=4, announced=1) for w in (0, 1)]}
    monkeypatch.setattr(engine, "ScenarioStreams", forced_absences(onsets))
    return inst, Schedule(starts=(0, 0, 0, 5, 11))


def test_always_substitute_serves_the_most_urgent_activity_first(
    build: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    # D = 20: LS_C = 14, LF_A = 14, LS_A = 9 and LS_B = 18, so on day 1 tau_A = 8 < tau_B = 17
    # and the only idle worker, 2, replaces A's worker 0.
    inst, plan = urgent_case(build, monkeypatch)
    recorder = Recorder(AlwaysSubstitute())
    result = simulate(
        inst, plan, recorder, 0, pert=EXACT, disruptions=NONE, deadline=20, debug=True
    )
    first, decision = recorder.seen[1]
    assert first.day == 1 and first.status[1:3] == ("paused", "paused")
    assert urgencies(first, [1, 2]) == {1: 8.0, 2: 17.0}
    assert decision.operations == (Subst(activity=1, workers=(2,)),)
    assert substitutions(first) == decision.operations
    assert [(s.day, s.activity, s.workers) for s in result.substitutions] == [(1, 1, (2,))]
    assert_feasible(inst, result)


def test_urgency_of_running_and_unstarted_activities(build: Builder) -> None:
    # Without disruptions and with X = 1, on day 2 A has 5 - 2 = 3 days left: tau_A = LF_A - 2
    # - 3 = 9; C waits for A: tau_C = LS_C - 2 = 12. B is done.
    inst = build(
        [0, 5, 2, 6, 0], [[0], [1], [1], [1], [0]], [[1, 2], [3], [4], [4], []], capacities=(3,)
    )
    plan = Schedule(starts=(0, 0, 0, 5, 11))
    result = simulate(
        inst, plan, NoReaction(), 0, pert=EXACT, disruptions=NONE, deadline=20, observe_days=[2]
    )
    observation = result.observations[0]
    assert observation.status[1:4] == ("running", "done", "unstarted")
    assert urgencies(observation, [1, 3]) == {1: 9.0, 3: 12.0}
    without = observation.model_copy(update={"deadline": None})  # D = planned makespan 11
    assert urgencies(without, [1, 3]) == {1: 0.0, 3: 3.0}
    with pytest.raises(ValueError, match="done"):
        urgencies(observation, [2])


@pytest.mark.parametrize("policy_class", [FullResolve, StableResolve])
@pytest.mark.parametrize("subst", [False, True])
def test_resolving_without_disruptions_reproduces_the_cpsat_baseline_of_tiny(
    tiny: ProjectInstance, policy_class: type[FullResolve], subst: bool
) -> None:
    """X = 1, no disruptions: no epoch has a new disruption, so the run is the baseline's
    (makespan 7). Re-solving at every day keeps makespan 7, and StableResolve keeps every start."""
    solved = solve_cpsat(tiny, time_limit_s=10)
    assert solved.schedule is not None and solved.makespan == 7
    plan = solved.schedule
    baseline = simulate(tiny, plan, NoReaction(), 3, pert=EXACT, disruptions=NONE)
    policy = policy_class(subst)
    quiet = simulate(tiny, plan, policy, 3, pert=EXACT, disruptions=NONE, debug=True)
    assert quiet == baseline and quiet.makespan == 7 and policy.stats.reseqs == 0
    forced = policy_class(subst)
    forced.monitor = EveryEpoch()
    result = simulate(
        tiny, plan, forced, 3, pert=EXACT, disruptions=NONE, review_period=1, debug=True
    )
    assert result.makespan == 7 and result.reseqs == forced.stats.reseqs == 8  # days 0-7
    assert result.rejected == () and forced.stats.fallbacks == 0
    if policy_class is StableResolve:
        assert result.starts == plan.starts and result.nervousness == 0
    assert_feasible(tiny, result)


def test_disruption_monitor_tells_disruptions_from_periodic_epochs(
    build: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Worker 0 is out on days 2-3 and back on day 4. With T_r = 3 the epochs are days 0, 2
    # (onset), 3, 4 (return), 6, ...: day 2 has the onset, day 4 the return (spec 3.1 g).
    inst = build([0, 9, 0], [[0], [1], [0]], [[1], [2], []], capacities=(2,))
    plan = Schedule(starts=(0, 0, 9))
    onsets = {2: [AbsenceDraw(worker=0, length=2, announced=1)]}
    monkeypatch.setattr(engine, "ScenarioStreams", forced_absences(onsets))
    recorder = Recorder(NoReaction())
    simulate(inst, plan, recorder, 0, pert=EXACT, disruptions=NONE, review_period=3)
    monitor = DisruptionMonitor()
    seen = [(obs.day, monitor.new_disruption(obs)) for obs, _ in recorder.seen]
    assert seen[:5] == [(0, False), (2, True), (3, False), (4, True), (6, False)]
    first = recorder.seen[0][0]
    assert monitor.new_disruption(first) is False  # a new run starts from scratch
    shocked = first.model_copy(update={"day": 1, "work_increases": ((1, 0.0, 1.5),)})
    assert monitor.new_disruption(shocked) is True  # D2
    later = recorder.seen[4][0]
    assert monitor.new_disruption(later) is True  # the absence seen in between ended


def test_the_registry_makes_the_five_policies() -> None:
    made = [make_policy(name) for name in COMPARED]
    assert [type(p).__name__ for p in made] == [
        "NoReaction",
        "AlwaysSubstitute",
        "FullResolve",
        "FullResolve",
        "StableResolve",
    ]
    assert [getattr(p, "name", None) for p in made[1:]] == list(COMPARED[1:])
    assert isinstance(made[2], FullResolve) and not made[2].subst and made[3].subst  # type: ignore[attr-defined]
    resolve = make_policy("stable_resolve", deterministic_time_limit=0.1, seed=4)
    assert isinstance(resolve, StableResolve) and (resolve.seed, resolve.subst) == (4, False)
    with pytest.raises(ValueError, match="unknown policy"):
        make_policy("oracle")


def runs_of_all_policies(
    instance: ProjectInstance, seed: int, plan: Schedule
) -> dict[str, SimulationResult]:
    return {
        name: simulate(
            instance,
            plan,
            make_policy(name),
            seed,
            pert=PertParams(),
            disruptions=LIVELY,
            deadline=plan.makespan(instance) + 5,
            review_period=3,
            debug=True,
        )
        for name in COMPARED
    }


def test_policies_are_deterministic_and_share_the_exogenous_events(build: Builder) -> None:
    """Same seed, same result for each of the five policies; absence onsets and D3 arrivals
    (day and template) are identical across them up to the shortest run (CRN, spec 2.3)."""
    used = {"subst": 0, "reseq": 0}
    for i in range(2):
        instance = random_instance(build, seed=40 + i)
        plan = lft_plan(instance)
        for seed in range(2):
            first = runs_of_all_policies(instance, 9 * i + seed, plan)
            assert runs_of_all_policies(instance, 9 * i + seed, plan) == first
            horizon = min(result.makespan for result in first.values())
            onsets = {
                name: [e for e in r.events if isinstance(e, Absence) and e.day < horizon]
                for name, r in first.items()
            }
            arrivals = {
                name: [
                    (e.day, e.template)
                    for e in r.events
                    if isinstance(e, NewActivity) and e.day < horizon
                ]
                for name, r in first.items()
            }
            assert all(o == onsets["no_reaction"] for o in onsets.values())
            assert all(a == arrivals["no_reaction"] for a in arrivals.values())
            assert onsets["no_reaction"]
            for result in first.values():
                assert_feasible(instance, result)
                assert result.rejected == ()
            used["subst"] += first["always_substitute"].n_substituted
            used["reseq"] += first["full_resolve"].reseqs
    assert used["subst"] > 0 and used["reseq"] > 0


def test_policies_see_only_the_observation(build: Builder) -> None:
    """A policy decides the same on a JSON copy of the observation: its decision depends on
    the observation's content (and its own memory) only."""
    instance = random_instance(build, seed=43)
    plan = lft_plan(instance)
    for name in COMPARED[1:]:
        recorder = Recorder(make_policy(name))
        simulate(instance, plan, recorder, 5, pert=PertParams(), disruptions=LIVELY, debug=True)
        twin = make_policy(name)
        for observation, decision in recorder.seen:
            copied = Observation.model_validate_json(observation.model_dump_json())
            assert twin.decide(copied) == decision


def world(instance: ProjectInstance, plan: Schedule, seed: int, policy: Policy) -> Run:
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
    return Run(state, streams, policy, review_period=3, debug=True)


class Snapshot:
    """Test-only wrapper: before deciding on `day` it keeps the observation, the true hidden
    state, the D2 work-day counters and a copy of the policy with its memory."""

    def __init__(self, policy: FullResolve, day: int) -> None:
        self.policy = policy
        self.day = day
        self.run: Run | None = None
        self.taken: tuple[Observation, object, list[int], FullResolve] | None = None

    def decide(self, observation: Observation) -> Decision:
        if observation.day == self.day:
            assert self.run is not None
            state = self.run.state
            policy = copy.deepcopy(self.policy)
            self.taken = (observation, state.hidden(), list(state.work_days), policy)
        return self.policy.decide(observation)


def intervention_day(instance: ProjectInstance, plan: Schedule, seed: int) -> int | None:
    """An epoch of a FullResolve(subst=True) run after its first SUBST and its first RESEQ."""
    recorder = Recorder(FullResolve(True))
    run = world(instance, plan, seed, recorder)
    run.days(0)
    days = [s.day for s in run.substitutions]
    if not days or run.reseqs == 0:
        return None
    later = [obs.day for obs, _ in recorder.seen if obs.day > days[0]]
    return later[len(later) // 2] if later else None


def test_operations_act_alike_in_a_resumed_run_and_in_the_world(build: Builder) -> None:
    """A run rebuilt at an epoch from the observation and the true hidden state, continued with
    a copy of the policy, the world's streams and its D2 counters, applies the same SUBST and
    RESEQ operations and ends exactly as the world does."""
    checked = 0
    for i in range(3):
        instance = random_instance(build, seed=50 + i)
        plan = lft_plan(instance)
        for seed in range(3):
            day = intervention_day(instance, plan, 11 * i + seed)
            if day is None:
                continue
            snapshot = Snapshot(FullResolve(True), day)
            whole = world(instance, plan, 11 * i + seed, snapshot)  # type: ignore[arg-type]
            snapshot.run = whole
            whole.days(0)
            assert snapshot.taken is not None
            observation, hidden, work_days, policy = snapshot.taken
            state = state_from_observation(observation, hidden)  # type: ignore[arg-type]
            state.work_days = work_days
            streams = ScenarioStreams(11 * i + seed, instance, LIVELY, PertParams())
            resumed = Run(state, streams, policy, review_period=3, debug=True)
            resumed.apply(policy.decide(observation))
            resumed.resume()
            assert state.start == whole.state.start and state.finish == whole.state.finish
            assert state.cost == whole.state.cost and state.plan == whole.state.plan
            assert resumed.substitutions == [s for s in whole.substitutions if s.day >= day]
            assert resumed.reseqs > 0
            checked += 1
    assert checked >= 3


def test_perfect_information_rollout_after_subst_and_reseq_reproduces_the_makespan(
    build: Builder,
) -> None:
    """The world uses SUBST and RESEQ up to an epoch and goes on without interventions and
    disruptions: rollouts from its observation with the true hidden state end when it does."""
    checked = 0
    for i in range(3):
        instance = random_instance(build, seed=60 + i)
        plan = lft_plan(instance)
        for seed in range(3):
            day = intervention_day(instance, plan, 13 * i + seed)
            if day is None:
                continue
            run = world(instance, plan, 13 * i + seed, FullResolve(True))
            for t in range(day):
                run.close_day(t, run.open_day(t))
            run.open_day(day)
            state = run.state
            assert run.substitutions and run.reseqs > 0
            observation, truth = state.observe(), state.hidden()
            run.policy, run.passive = NoReaction(), True
            run.streams = ScenarioStreams(0, instance, NONE, PertParams())
            run.shocks = False
            state.next_shock = [0] * len(state.next_shock)
            if not run.close_day(day, True):
                run.days(day + 1)
            makespan = state.start[state.sink]
            result = forecast(
                observation,
                Schedule(starts=observation.plan),
                n_rollouts=3,
                seed=seed,
                include_future_disruptions=False,
                _true_world=truth,
            )
            assert result.makespans == (makespan,) * 3
            checked += 1
    assert checked >= 3
