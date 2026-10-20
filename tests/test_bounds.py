"""Critical-path bounds (spec section 1.4)."""

from collections.abc import Callable

from sentinel.model import ProjectInstance
from sentinel.scheduling.bounds import (
    critical_path_lower_bound,
    earliest_starts,
    latest_finishes,
    latest_starts,
)

Builder = Callable[..., ProjectInstance]


def test_tiny_lb0_is_seven(tiny: ProjectInstance) -> None:
    assert critical_path_lower_bound(tiny) == 7


def test_tiny_forward_and_backward_pass(tiny: ProjectInstance) -> None:
    assert earliest_starts(tiny) == (0, 0, 0, 3, 7)
    assert latest_finishes(tiny) == (0, 3, 7, 7, 7)
    assert latest_starts(tiny) == (0, 0, 5, 3, 7)


def test_critical_activities_have_zero_slack(tiny: ProjectInstance) -> None:
    slack = [ls - es for es, ls in zip(earliest_starts(tiny), latest_starts(tiny), strict=True)]
    assert slack == [0, 0, 5, 0, 0]  # critical path 0 -> 1 -> 3 -> 4


def test_explicit_horizon(tiny: ProjectInstance) -> None:
    assert latest_finishes(tiny, horizon=10) == (3, 6, 10, 10, 10)
    assert latest_starts(tiny, horizon=10) == (3, 3, 8, 6, 10)
    assert latest_starts(tiny, horizon=5)[0] == -2  # horizon below LB0: negative slack


def test_bounds_follow_topological_order_not_ids(build: Builder) -> None:
    # 0 -> 2 -> 1 -> 3 with p = (0, 2, 3, 0): id order is not a topological order.
    inst = build([0, 2, 3, 0], [[0], [1], [1], [0]], [[2], [3], [1], []])
    assert earliest_starts(inst) == (0, 3, 0, 5)
    assert critical_path_lower_bound(inst) == 5
    assert latest_starts(inst) == (0, 3, 0, 5)
