"""OVERTIME with temporary workers and SHIFT, the order-preserving repair (spec section 4)."""

from collections.abc import Callable, Sequence
from itertools import pairwise

import numpy as np
import pytest

from sentinel.forecasting.forecast import forecast
from sentinel.model import ProjectInstance, Schedule, validate_schedule
from sentinel.policies.base import EMPTY_DECISION, Decision, Overtime, Shift, Subst
from sentinel.policies.no_reaction import NoReaction
from sentinel.scheduling.cpsat import solve_residual
from sentinel.scheduling.priority_rules import lft_priorities
from sentinel.scheduling.residual import (
    ResidualProblem,
    planning_view,
    residual_sgs,
    shift_order,
    shift_sgs,
    validate_residual,
    validate_shift,
)
from sentinel.scheduling.sgs import serial_sgs
from sentinel.simulation import engine
from sentinel.simulation.engine import SimulationResult, simulate
from sentinel.simulation.events import Absence, AbsenceDraw, DisruptionParams, ScenarioStreams
from sentinel.simulation.realised import execution_violations, realised_instance
from sentinel.simulation.state import (
    Observation,
    TemporaryWorker,
    nominal_world,
    state_from_observation,
)
from sentinel.simulation.uncertainty import PertParams

Builder = Callable[..., ProjectInstance]

EXACT = PertParams(a=1.0, m=1.0, b=1.0)  # X = 1, so P_j = p_j
NONE = DisruptionParams.none()
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


def overtime(role: int, workers: int, days: int) -> Overtime:
    return Overtime(role=role, workers=workers, days=days)


def test_temporary_workers_are_dispatched_paid_and_stay_in_their_crew(build: Builder) -> None:
    # Role 0 has five workers, so floor(0.2 * 5) = 1 may be hired. A (p 4) needs all five, B
    # (p 3, r 1) is planned beside it and C (p 1, r 1) on day 3. On day 0 a temporary worker is
    # hired for H = 2 days: B starts on day 0 with it and runs past the window, so it stays in
    # B's crew until B completes at the end of day 2 and then leaves. C finds no idle worker on
    # day 3 and waits for A's crew. Costs: A 5 x 4, C 1, the temporary worker 3 x 1.5.
    inst = build(
        [0, 4, 3, 1, 0], [[0], [5], [1], [1], [0]], [[1, 2, 3], [4], [4], [4], []], capacities=(5,)
    )
    plan = Schedule(starts=(0, 0, 0, 3, 4))
    policy = Scripted({0: Decision(operations=(overtime(0, 1, 2),))})
    result = simulate(inst, plan, policy, 0, pert=EXACT, disruptions=NONE, debug=True)
    assert result.temporary == (TemporaryWorker(id=5, role=0, hired=0, until=2, left=3),)
    assert result.hired == 1 and result.temporary_days == 3
    assert result.overtime_cost == 4.5 and result.total_cost == 20 + 1 + 4.5
    assert segments_of(result, 2) == [(0, 3, (5,))] and result.crews[2] == (5,)
    assert result.starts[3] == 4 and result.makespan == 5
    seen = {obs.day: obs for obs in policy.seen}
    assert len(seen[0].present) == 5  # the observation before the decision
    assert_feasible(inst, result)
    # Without overtime B waits for A's crew.
    alone = simulate(inst, plan, NoReaction(), 0, pert=EXACT, disruptions=NONE)
    assert alone.starts[2] == 4 and alone.makespan == 7 and alone.total_cost == 20 + 3 + 1


def test_an_idle_temporary_worker_leaves_when_its_window_ends(build: Builder) -> None:
    # Nothing needs the temporary worker hired on day 1 for 2 days: it is idle on days 1-2,
    # paid 1.5 per day, and gone on day 3, when B (r 1) would need it; B waits for A's crew.
    inst = build([0, 4, 1, 0], [[0], [5], [1], [0]], [[1, 2], [3], [3], []], capacities=(5,))
    plan = Schedule(starts=(0, 0, 3, 4))
    policy = Scripted({1: Decision(operations=(overtime(0, 1, 2),))})
    result = simulate(
        inst, plan, policy, 0, pert=EXACT, disruptions=NONE, review_period=1, debug=True
    )
    assert result.temporary == (TemporaryWorker(id=5, role=0, hired=1, until=3, left=3),)
    assert result.temporary_days == 2 and result.overtime_cost == 3.0
    assert result.starts[2] == 4 and result.crews[2] != (5,)
    seen = {obs.day: obs for obs in policy.seen}
    assert seen[2].present[5] and seen[2].temporary[0].left is None
    assert not seen[3].present[5] and seen[3].temporary[0].left == 3
    assert seen[3].absent_since[5] is None and seen[3].announced[5] is None
    assert_feasible(inst, result)


def test_a_temporary_worker_substitutes_with_onboarding_and_stays_after_its_window(
    build: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A (p 6, r 5) runs with role 0's five workers; worker 0 is out on days 1-3. On day 1 the
    # agent hires one temporary worker for 4 days and puts it in worker 0's slot: onboarding
    # o = max(1, ceil(0.3 * 1)) = 1 crew-member day. A then has 25 + 1 crew-member days left,
    # 5 per day from day 1, and completes at the end of day 6, after the window [1, 5): the
    # temporary worker stays until then. Worker 0 returns on day 4 as an idle worker.
    inst = build([0, 6, 0], [[0], [5], [0]], [[1], [2], []], capacities=(5,))
    plan = Schedule(starts=(0, 0, 6))
    onsets = {1: [AbsenceDraw(worker=0, length=3, announced=1)]}
    monkeypatch.setattr(engine, "ScenarioStreams", forced_absences(onsets))
    decision = Decision(operations=(overtime(0, 1, 4), Subst(activity=1, workers=(5,))))
    policy = Scripted({1: decision})
    result = simulate(inst, plan, policy, 0, pert=EXACT, disruptions=NONE, debug=True)
    (sub,) = result.substitutions
    assert (sub.day, sub.replaced, sub.workers, sub.onboarding) == (1, (0,), (5,), 1)
    assert result.temporary == (TemporaryWorker(id=5, role=0, hired=1, until=5, left=7),)
    assert result.temporary_days == 6 and result.overtime_cost == 9.0
    assert segments_of(result, 1) == [(0, 1, (0, 1, 2, 3, 4)), (1, 7, (5, 1, 2, 3, 4))]
    assert result.makespan == 7 and result.total_cost == 5 + 4 * 6 + 9.0
    assert_feasible(inst, result)


def test_overtime_is_capped_at_floor_gamma_r_k(build: Builder) -> None:
    # floor(0.2 * 10) = 2 temporary workers of a role at a time; floor(0.2 * 4) = 0.
    inst = build([0, 2, 2, 0], [[0, 0], [10, 0], [0, 4], [0, 0]], [[1, 2], [3], [3], []], (10, 4))
    plan = Schedule(starts=(0, 0, 0, 2))
    decision = Decision(
        operations=(
            overtime(0, 3, 5),  # too many
            overtime(0, 2, 5),
            overtime(0, 1, 5),  # two are hired already
            overtime(1, 1, 5),  # none allowed
            overtime(2, 1, 5),  # no such role
        )
    )
    result = simulate(inst, plan, Scripted({0: decision}), 0, pert=EXACT, disruptions=NONE)
    assert [r.operation for r in result.rejected] == [
        overtime(0, 3, 5),
        overtime(0, 1, 5),
        overtime(1, 1, 5),
        overtime(2, 1, 5),
    ]
    assert [temp.id for temp in result.temporary] == [14, 15]


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


class HireAndReplan:
    """Test-only policy: hires the cap of role 0 for 4 days on its first epoch from `day` on,
    then re-plans with RESEQ on the planning view that counts the temporary workers."""

    def __init__(self, day: int) -> None:
        self.day = day
        self.done = False

    def decide(self, observation: Observation) -> Decision:
        if self.done or observation.day < self.day:
            return EMPTY_DECISION
        self.done = True
        hire = overtime(0, 1, 4)
        hired = engine.preview(observation, Decision(operations=(hire,)))
        view = planning_view(hired)
        solution = solve_residual(view, deterministic_time_limit=0.05, seed=0)
        from sentinel.policies.base import Reseq

        return Decision(operations=(hire, Reseq(starts=solution.starts)))


def test_absences_of_the_original_workers_do_not_depend_on_overtime(build: Builder) -> None:
    """Temporary workers have no absence stream: the same seed gives the same absences of the
    original workers with and without hiring, and no temporary worker is ever absent."""
    checked = 0
    for i in range(3):
        instance = random_instance(build, 70 + i)
        plan = lft_plan(instance)
        deadline = plan.makespan(instance) + 5
        for seed in range(2):
            runs = [
                simulate(
                    instance,
                    plan,
                    policy,
                    seed,
                    pert=PertParams(),
                    disruptions=LIVELY,
                    deadline=deadline,
                    review_period=3,
                    debug=True,
                )
                for policy in (NoReaction(), HireAndReplan(2))
            ]
            hired = runs[1]
            assert hired.temporary and hired.reseqs == 1
            assert_feasible(instance, hired)
            end = min(run.makespan for run in runs)
            absences = [
                [
                    (e.day, e.worker, e.length, e.announced)
                    for e in run.events
                    if e.kind == "absence"
                ]
                for run in runs
            ]
            assert [a for a in absences[0] if a[0] < end] == [a for a in absences[1] if a[0] < end]
            first = len(instance.workers)
            assert all(e.worker < first for e in hired.events if isinstance(e, Absence))
            checked += 1
    assert checked == 6


def test_rebuilt_state_and_perfect_information_rollout_with_temporary_workers(
    build: Builder,
) -> None:
    """An observation with temporary workers, completed by the true hidden state, rebuilds the
    engine state; a rollout without future disruptions then ends when the world does."""
    instance = random_instance(build, 80)
    plan = lft_plan(instance)
    deadline = plan.makespan(instance) + 5
    for day in (3, 5):
        result = simulate(
            instance,
            plan,
            HireAndReplan(2),
            1,
            pert=PertParams(),
            disruptions=NONE,
            deadline=deadline,
            review_period=1,
            observe_days=[day],
        )
        (observation,) = result.observations
        assert observation.temporary
        # The hidden state of a run without disruptions: no absences, remaining work from the
        # true durations, which the world's result records as total work.
        work = [w * max(1, sum(d)) for w, d in zip(result.work, demands(instance), strict=True)]
        done = [
            e * max(1, sum(d))
            for e, d in zip(observation.work_done, demands(instance), strict=True)
        ]
        remaining = tuple(max(0.0, w - e) for w, e in zip(work, done, strict=True))
        state = state_from_observation(
            observation,
            nominal_world(observation)._replace(remaining=remaining),
        )
        assert state.observe() == observation
        assert state.first_temporary == len(instance.workers) and state.hired >= 1
        truth = nominal_world(observation)._replace(remaining=remaining)
        rolled = forecast(
            observation,
            Schedule(starts=observation.plan),
            n_rollouts=2,
            seed=0,
            include_future_disruptions=False,
            _true_world=truth,
        )
        assert rolled.makespans == (result.makespan,) * 2


def demands(instance: ProjectInstance) -> list[tuple[int, ...]]:
    return [act.demands for act in instance.activities]


# SHIFT -------------------------------------------------------------------------------------


# Durations mostly shorter than nominal, so that successors could start before their plan.
EARLY = PertParams(a=0.4, m=0.7, b=1.3)


def shift_views(build: Builder) -> list[ResidualProblem]:
    """Planning views of NoReaction runs under frequent disruptions every other day, with the
    default durations and with mostly early finishes."""
    found = []
    for i in range(4):
        instance = random_instance(build, 90 + i)
        plan = lft_plan(instance)
        deadline = plan.makespan(instance) + 5
        for seed, pert in enumerate((PertParams(), EARLY, PertParams(), EARLY)):
            result = simulate(
                instance,
                plan,
                NoReaction(),
                seed,
                pert=pert,
                disruptions=LIVELY,
                deadline=deadline,
                observe_days=range(0, 3 * plan.makespan(instance), 2),
            )
            found += [planning_view(obs) for obs in result.observations]
    return found


def test_shift_keeps_the_order_and_never_ends_later_than_the_railway_decode(
    build: Builder,
) -> None:
    """SHIFT is a valid plan whose starts never change the order of the planned starts; its
    residual makespan is never later than that of the current plan decoded by the same list
    without starting anything earlier than planned (railway rule), which is the current plan
    itself where that is feasible. SHIFT does start activities earlier than planned."""
    earlier = shorter = feasible = 0
    views = shift_views(build)
    assert len(views) >= 200
    for view in views:
        shift = shift_sgs(view)
        assert validate_shift(view, shift) == []
        planned = view.planned_starts()
        order = [view.activities[i] for i in shift_order(view) if view.durations[i] > 0]
        starts = [shift[j] for j in order]
        assert starts == sorted(starts)
        for i, j in pairwise(order):
            if planned[i] < planned[j]:  # where the plan respects precedence, its order
                assert shift[i] <= shift[j]
        railway = shift_sgs(view, railway=True)
        assert validate_shift(view, railway) == []
        assert all(shift[j] <= railway[j] for j in view.activities)
        shorter += shift[view.sink] < railway[view.sink]
        if not validate_residual(view, planned):
            feasible += 1
            assert railway == planned
        earlier += any(shift[j] < planned[j] for j in order if planned[j] >= view.day)
    assert feasible >= 10 and earlier >= 5 and shorter >= 5, (feasible, earlier, shorter)


def test_shift_keeps_an_order_that_the_plain_decode_changes() -> None:
    # On day 10 the role has one free unit until day 13, then three. A (p 3, r 2) is planned on
    # day 13 and B (p 2, r 1, released on day 12) on day 14. Decoding the plan by the serial SGS
    # starts B on day 12, before A; SHIFT starts it with A on day 13, in the planned order.
    view = ResidualProblem(
        day=10,
        activities=(5, 6, 7),
        durations=(3, 2, 0),
        demands=((2,), (1,), (0,)),
        successors=((2,), (2,), ()),
        fixed_finish=(0, 12, 0),
        planned=(13, 14, 16),
        capacities=(3,),
        profile=(((10, 1), (13, 3)),),
        estimated_finish=(),
        sink=7,
    )
    assert residual_sgs(view, view.planned_starts()) == {5: 13, 6: 12, 7: 16}
    assert shift_sgs(view) == {5: 13, 6: 13, 7: 16}
    [violation] = validate_shift(view, {5: 13, 6: 12, 7: 16})
    assert (violation.kind, violation.activity) == ("order", 6)


def test_the_engine_applies_a_shift_and_rejects_one_that_changes_the_order(build: Builder) -> None:
    # A (p 2) and B (p 2) share one worker and are planned on days 0 and 2; C (p 1) follows A
    # and is planned on day 6, D (p 1) follows B on day 7. On day 2, before B starts, a SHIFT
    # pulls C and D to the earliest days the order allows; one that starts D before C, though
    # feasible, is rejected.
    inst = build(
        [0, 2, 2, 1, 1, 0],
        [[0], [1], [1], [1], [1], [0]],
        [[1, 2], [3], [4], [5], [5], []],
        capacities=(1,),
    )
    plan = Schedule(starts=(0, 0, 2, 6, 7, 8))
    swapped = Shift(starts={2: 2, 3: 5, 4: 4, 5: 6})
    good = Shift(starts={2: 2, 3: 4, 4: 5, 5: 6})
    policy = Scripted({2: Decision(operations=(swapped, good))})
    result = simulate(
        inst, plan, policy, 0, pert=EXACT, disruptions=NONE, review_period=1, debug=False
    )
    assert [r.operation for r in result.rejected] == [swapped]
    assert result.shifts == 1 and result.reseqs == 0 and result.nervousness == 2
    assert result.starts[3:] == (4, 5, 6) and result.makespan == 6
    view = planning_view(policy.seen[2])
    assert shift_sgs(view) == good.starts
    with pytest.raises(AssertionError, match="SHIFT on day 2"):
        simulate(inst, plan, Scripted({2: Decision(operations=(swapped,))}), 0, pert=EXACT,
                 disruptions=NONE, review_period=1, debug=True)  # fmt: skip
