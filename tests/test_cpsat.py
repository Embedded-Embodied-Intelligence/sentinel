"""CP-SAT model for the RCPSP."""

from collections.abc import Callable

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
