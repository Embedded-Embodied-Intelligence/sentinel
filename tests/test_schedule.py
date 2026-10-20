"""Schedule feasibility check (spec section 1.3)."""

from collections.abc import Callable

import pytest

from sentinel.model import ProjectInstance, Schedule, validate_schedule

Builder = Callable[..., ProjectInstance]


def test_known_optimal_schedule_is_feasible(tiny: ProjectInstance) -> None:
    schedule = Schedule(starts=(0, 0, 3, 3, 7))
    assert validate_schedule(tiny, schedule) == []
    assert schedule.makespan(tiny) == 7
    assert [schedule.finish(tiny, j) for j in range(5)] == [0, 3, 5, 7, 7]


def test_detects_precedence_violation(tiny: ProjectInstance) -> None:
    violations = validate_schedule(tiny, Schedule(starts=(0, 0, 3, 2, 7)))
    assert [(v.kind, v.activity, v.time) for v in violations] == [("precedence", 3, 2)]
    assert "predecessor 1 finishes at 3" in violations[0].detail


def test_detects_resource_overload_with_day_and_role(tiny: ProjectInstance) -> None:
    violations = validate_schedule(tiny, Schedule(starts=(0, 0, 0, 3, 7)))
    assert [(v.kind, v.role, v.time) for v in violations] == [
        ("resource", 0, 0),
        ("resource", 0, 1),
    ]
    assert "demand 4 exceeds capacity 3" in violations[0].detail


def test_detects_negative_start(tiny: ProjectInstance) -> None:
    violations = validate_schedule(tiny, Schedule(starts=(0, -1, 3, 3, 7)))
    assert ("negative_start", 1, -1) in [(v.kind, v.activity, v.time) for v in violations]


def test_detects_source_not_starting_at_zero(tiny: ProjectInstance) -> None:
    violations = validate_schedule(tiny, Schedule(starts=(1, 1, 4, 4, 8)))
    assert [(v.kind, v.activity, v.time) for v in violations] == [("source_start", 0, 1)]


def test_detects_wrong_length(tiny: ProjectInstance) -> None:
    schedule = Schedule(starts=(0, 0, 3, 3))
    violations = validate_schedule(tiny, schedule)
    assert [v.kind for v in violations] == ["length"]
    with pytest.raises(ValueError, match="4 start times"):
        schedule.makespan(tiny)


def test_resource_check_per_role(build: Builder) -> None:
    # Activities 1 and 2 overlap on day 1: role 0 is fine (1 + 1 <= 2), role 1 is not (2 > 1).
    inst = build([0, 2, 2, 0], [[0, 0], [1, 1], [1, 1], [0, 0]], [[1, 2], [3], [3], []], (2, 1))
    violations = validate_schedule(inst, Schedule(starts=(0, 0, 1, 3)))
    assert [(v.kind, v.role, v.time) for v in violations] == [("resource", 1, 1)]


def test_zero_duration_activity_uses_no_capacity(build: Builder) -> None:
    inst = build([0, 0, 2, 0], [[0], [3], [3], [0]], [[1, 2], [3], [3], []])
    assert validate_schedule(inst, Schedule(starts=(0, 0, 0, 2))) == []
