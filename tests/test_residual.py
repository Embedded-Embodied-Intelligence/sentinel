"""Planning view, residual problem, residual SGS and residual CP-SAT (spec section 4.1)."""

from collections.abc import Callable, Sequence

import numpy as np
import pytest

from sentinel.forecasting.streams import RolloutStreams
from sentinel.model import ProjectInstance, Schedule
from sentinel.policies.always_substitute import AlwaysSubstitute
from sentinel.policies.base import Policy
from sentinel.policies.no_reaction import NoReaction
from sentinel.scheduling import cpsat
from sentinel.scheduling.cpsat import solve_residual
from sentinel.scheduling.priority_rules import lft_priorities
from sentinel.scheduling.residual import (
    ResidualProblem,
    planning_view,
    residual_sgs,
    validate_residual,
)
from sentinel.scheduling.sgs import serial_sgs
from sentinel.simulation import engine
from sentinel.simulation.engine import Run, simulate
from sentinel.simulation.events import AbsenceDraw, DisruptionParams, ScenarioStreams
from sentinel.simulation.state import Observation, nominal_world, state_from_observation
from sentinel.simulation.uncertainty import PertParams

Builder = Callable[..., ProjectInstance]

EXACT = PertParams(a=1.0, m=1.0, b=1.0)
NONE = DisruptionParams.none()
BUSY = DisruptionParams(lambda_a=0.05, mean_absence=3, lambda_s=0.1, lambda_n=0.1)
LIMIT = 0.5  # T_cp


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


def lft_plan(instance: ProjectInstance) -> Schedule:
    return serial_sgs(instance, lft_priorities(instance), lower_is_better=True)


def observations(
    instance: ProjectInstance, policy: Policy, seed: int, every: int = 3
) -> Sequence[Observation]:
    """Observations of a run under BUSY disruptions on every `every`-th day of the plan."""
    plan = lft_plan(instance)
    days = range(0, 2 * plan.makespan(instance), every)
    deadline = plan.makespan(instance) + 5
    result = simulate(
        instance,
        plan,
        policy,
        seed,
        pert=PertParams(),
        disruptions=BUSY,
        deadline=deadline,
        observe_days=days,
    )
    return result.observations


def views(build: Builder, tiny: ProjectInstance) -> list[ResidualProblem]:
    """Planning views of NoReaction and AlwaysSubstitute runs (the latter with handovers)."""
    found = []
    for i in range(3):
        instance = random_instance(build, seed=20 + i)
        for seed in range(3):
            policy: Policy = NoReaction() if seed % 2 else AlwaysSubstitute()
            found += [planning_view(obs) for obs in observations(instance, policy, 7 * i + seed)]
    for seed in range(4):
        found += [planning_view(obs) for obs in observations(tiny, NoReaction(), seed, every=1)]
    return found


def hand_view(
    build: Builder, monkeypatch: pytest.MonkeyPatch
) -> tuple[Observation, ResidualProblem]:
    """Role 0 has workers 0-3. A (p 4, r 2) and B (p 3, r 1) start on day 0 with workers 0, 1
    and 2; C (p 2, r 2) follows A, D (p 1, r 1) follows B. On day 1 crew member 1 leaves for
    5 days announced as 2 (nominal return day 3) and idle worker 3 for 4 days announced as 1.
    The view of day 2."""
    inst = build(
        [0, 4, 3, 2, 1, 0],
        [[0], [2], [1], [2], [1], [0]],
        [[1, 2], [3], [4], [5], [5], []],
        capacities=(4,),
    )
    plan = Schedule(starts=(0, 0, 0, 4, 3, 7))
    onsets = {
        1: [
            AbsenceDraw(worker=1, length=5, announced=2),
            AbsenceDraw(worker=3, length=4, announced=1),
        ]
    }

    class Forced(ScenarioStreams):
        def absence_onsets(self, day: int) -> Sequence[AbsenceDraw]:
            return onsets.get(day, [])

    monkeypatch.setattr(engine, "ScenarioStreams", Forced)
    result = simulate(inst, plan, NoReaction(), 0, pert=EXACT, disruptions=NONE, observe_days=[2])
    observation = result.observations[0]
    return observation, planning_view(observation)


def test_planning_view_by_hand(build: Builder, monkeypatch: pytest.MonkeyPatch) -> None:
    # A has done 2 + 1 crew-member days of 8: 5 remain. Worker 0 does one on day 2 and both on
    # days 3 and 4 (worker 1 nominally back on day 3): F-hat_A = 5. B has one day left: F-hat_B
    # = 3. Worker 3's bound has passed, so it is expected back tomorrow, day 3. Capacity of the
    # role: day 2: 4 - 2 (A) - 1 (B) - 1 (worker 3) = 0; day 3: 2; from day 5: 4.
    observation, view = hand_view(build, monkeypatch)
    assert observation.status[1:3] == ("running", "running")
    assert view.day == 2 and view.activities == (3, 4, 5)
    assert view.durations == (2, 1, 0) and view.demands == ((2,), (1,), (0,))
    assert view.successors == ((2,), (2,), ())
    assert view.fixed_finish == (5, 3, 0) and view.releases() == [5, 3, 2]
    assert view.planned == (4, 3, 7) and view.planned_starts() == {3: 4, 4: 3, 5: 7}
    assert view.capacities == (4,) and view.profile == (((2, 0), (3, 2), (5, 4)),)
    assert view.estimated_finish == ((1, 5), (2, 3)) and view.sink == 5
    assert ResidualProblem.model_validate(view.model_dump()) == view
    # Serial SGS: C and D tie on LFT, so C (id 3) first at its release 5, D at 3, sink at 7.
    assert residual_sgs(view) == {3: 5, 4: 3, 5: 7}
    assert residual_sgs(view, {3: 1.0, 4: 0.0, 5: 2.0}) == {3: 5, 4: 3, 5: 7}


def test_validate_residual_finds_every_kind_of_violation(
    build: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, view = hand_view(build, monkeypatch)
    assert validate_residual(view, {3: 5, 4: 3, 5: 7}) == []

    def kinds(starts: dict[int, int]) -> list[tuple[str, int | None]]:
        return [(v.kind, v.activity or v.time) for v in validate_residual(view, starts)]

    assert kinds({3: 5, 4: 3}) == [("length", 5)]
    assert kinds({3: 5, 4: 3, 5: 7, 1: 0}) == [("length", 1)]
    assert kinds({3: 4, 4: 3, 5: 7}) == [("release", 3)]
    assert kinds({3: 5, 4: 3, 5: 6}) == [("precedence", 5)]
    # D on day 2 is before its release and finds no free unit on that day.
    assert kinds({3: 5, 4: 2, 5: 7}) == [("release", 4), ("resource", 2)]
    # C on days 3-4 overloads them (capacity 2, with D on day 3 a demand of 3).
    found = validate_residual(view, {3: 3, 4: 3, 5: 7})
    assert [(v.kind, v.time) for v in found if v.kind == "resource"] == [("resource", 3)]


def test_residual_sgs_and_cpsat_respect_a_capacity_dip() -> None:
    # On day 10 the role has one free unit until day 13, then three. A (p 3, r 2) must wait for
    # day 13; B (p 2, r 1) is released on day 12 and fits beside A. The makespan 16 is optimal.
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
    assert residual_sgs(view) == {5: 13, 6: 12, 7: 16}
    full = solve_residual(view, deterministic_time_limit=LIMIT, seed=0)
    assert (full.status, full.makespan, full.objective, full.fallback) == ("OPTIMAL", 16, 16, False)
    assert full.starts[5] == 13 and validate_residual(view, full.starts) == []
    # The current plan is feasible and optimal, so the stable solution keeps it.
    stable = solve_residual(
        view, "stable", deterministic_time_limit=LIMIT, seed=0, hint=view.planned_starts()
    )
    assert stable.starts == {5: 13, 6: 14, 7: 16} and stable.objective == 0
    with pytest.raises(ValueError, match="start on day 10"):
        ResidualProblem.model_validate(view.model_dump() | {"profile": (((11, 1), (13, 3)),)})


def test_estimated_finishes_are_those_of_the_deterministic_forecast(build: Builder) -> None:
    """F-hat_j of the planning view equals the finish of j in the deterministic forecast (one
    NoReaction run from the nominal state without future disruptions), handovers included."""
    checked = handovers = 0
    for i in range(3):
        instance = random_instance(build, seed=30 + i)
        for seed in range(3):
            policy: Policy = AlwaysSubstitute() if seed else NoReaction()
            for obs in observations(instance, policy, 5 * i + seed, every=2):
                world = nominal_world(obs)
                state = state_from_observation(obs, world)
                streams = RolloutStreams(
                    np.random.SeedSequence(0),
                    NONE,
                    obs.pert,
                    day=obs.day,
                    n_original=instance.n_activities,
                    return_day=world.return_day,
                )
                Run(state, streams, NoReaction(), record_events=False).resume()
                for j, finish in planning_view(obs).estimated_finish:
                    assert finish == state.finish[j], (obs.day, j)
                    checked += 1
                handovers += bool(obs.handovers)
    assert checked > 100 and handovers > 0, (checked, handovers)


def test_residual_plans_are_feasible_on_random_views(build: Builder, tiny: ProjectInstance) -> None:
    """At least 50 planning views of tiny.sm and random-instance runs: the residual SGS and both
    CP-SAT objectives give feasible plans, CP-SAT is never longer than the SGS, the stable plan
    keeps the makespan and deviates no more than the minimum-makespan plan, and decoding a
    feasible plan by its own starts never starts an activity later."""
    found = views(build, tiny)
    assert len(found) >= 50
    for view in found:
        sgs = residual_sgs(view)
        assert validate_residual(view, sgs) == []
        hint = view.planned_starts()
        full = solve_residual(view, deterministic_time_limit=LIMIT, seed=0, hint=hint)
        stable = solve_residual(view, "stable", deterministic_time_limit=LIMIT, seed=0, hint=hint)
        for solution in (full, stable):
            assert validate_residual(view, solution.starts) == []
            assert not solution.fallback
        assert full.makespan <= sgs[view.sink]
        assert full.status == "OPTIMAL"  # small problems
        assert stable.makespan == full.makespan
        planned = dict(zip(view.activities, view.planned, strict=True))
        deviation = sum(abs(full.starts[j] - planned[j]) for j in view.activities)
        assert stable.objective <= deviation
        decoded = residual_sgs(view, {j: float(s) for j, s in full.starts.items()})
        assert all(decoded[j] <= full.starts[j] for j in view.activities)


def test_solver_falls_back_to_the_residual_sgs(
    build: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, view = hand_view(build, monkeypatch)
    monkeypatch.setattr(cpsat, "_search", lambda *args: ("UNKNOWN", None, 0.0))
    full = solve_residual(view, deterministic_time_limit=LIMIT, seed=0)
    assert (full.status, full.fallback, full.fallbacks) == ("UNKNOWN", True, 1)
    assert full.starts == residual_sgs(view) and full.makespan == 7
    stable = solve_residual(view, "stable", deterministic_time_limit=LIMIT, seed=0)
    assert (stable.fallbacks, stable.starts) == (2, residual_sgs(view))
    assert stable.objective == sum(abs(stable.starts[j] - p) for j, p in [(3, 4), (4, 3), (5, 7)])


def test_the_residual_solver_is_deterministic(build: Builder, tiny: ProjectInstance) -> None:
    for view in views(build, tiny)[::10]:
        first = solve_residual(view, "stable", deterministic_time_limit=LIMIT, seed=3)
        again = solve_residual(view, "stable", deterministic_time_limit=LIMIT, seed=3)
        assert first.starts == again.starts and first.objective == again.objective
