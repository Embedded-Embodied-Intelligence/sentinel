"""CP-SAT model for the RCPSP."""

import math
from collections.abc import Callable

import numpy as np

from sentinel.model import ProjectInstance, validate_schedule
from sentinel.scheduling.cpsat import solve_cpsat

Builder = Callable[..., ProjectInstance]


def test_tiny_is_solved_to_optimality(tiny: ProjectInstance) -> None:
    result = solve_cpsat(tiny, time_limit_s=10)
    assert result.status == "OPTIMAL"
    assert result.makespan == 7
    assert result.lower_bound == 7
    assert result.schedule is not None
    assert result.schedule.makespan(tiny) == 7
    assert validate_schedule(tiny, result.schedule) == []
    assert result.wall_time_s >= 0


def test_resource_conflicts_are_resolved_optimally(build: Builder) -> None:
    # Capacity 3; earliest starts overload day 0; the optimum is 6 (energy bound 5).
    inst = build(
        [0, 2, 3, 2, 1, 0],
        [[0], [2], [2], [1], [3], [0]],
        [[1, 2, 3], [4], [5], [5], [5], []],
    )
    result = solve_cpsat(inst, time_limit_s=10, random_seed=3)
    assert (result.status, result.makespan, result.lower_bound) == ("OPTIMAL", 6, 6)
    assert result.schedule is not None
    assert validate_schedule(inst, result.schedule) == []
    assert solve_cpsat(inst, time_limit_s=10, random_seed=3).schedule == result.schedule


def test_horizon_bounds_the_makespan(tiny: ProjectInstance) -> None:
    assert solve_cpsat(tiny, time_limit_s=10, horizon=7).makespan == 7
    infeasible = solve_cpsat(tiny, time_limit_s=10, horizon=6)  # below LB0 = 7
    assert infeasible.status == "INFEASIBLE"
    assert (infeasible.schedule, infeasible.makespan, infeasible.lower_bound) == (None, None, None)


def _random_instance(build: Builder, n: int, seed: int) -> ProjectInstance:
    """n real activities on 4 roles of capacity 10, each with up to two later successors."""
    rng = np.random.default_rng(seed)
    successors: list[set[int]] = [set() for _ in range(n + 2)]
    for j in range(1, n):
        later = np.arange(j + 1, n + 1)
        successors[j].update(rng.choice(later, size=min(2, later.size), replace=False).tolist())
    has_predecessor = set().union(*successors)
    successors[0] = {j for j in range(1, n + 1) if j not in has_predecessor}
    for j in range(1, n + 1):
        successors[j] = successors[j] or {n + 1}
    durations = [0, *rng.integers(1, 11, size=n).tolist(), 0]
    demands = [[0] * 4, *rng.integers(0, 8, size=(n, 4)).tolist(), [0] * 4]
    return build(durations, demands, [sorted(s) for s in successors], capacities=(10,) * 4)


def test_deterministic_time_limit_gives_identical_schedules(build: Builder) -> None:
    # Proving optimality here takes CP-SAT seconds, so the deterministic limit stops the search.
    inst = _random_instance(build, 30, seed=1)
    first, second = (
        solve_cpsat(inst, time_limit_s=math.inf, random_seed=7, deterministic_time_limit=0.05)
        for _ in range(2)
    )
    assert first.status == "FEASIBLE"
    assert first.schedule is not None
    assert validate_schedule(inst, first.schedule) == []
    assert (first.schedule, first.makespan, first.lower_bound) == (
        second.schedule,
        second.makespan,
        second.lower_bound,
    )
    assert first.deterministic_time is not None and first.deterministic_time >= 0.04
