"""ProjectInstance construction and validity conditions (spec section 1)."""

from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError

from sentinel.model import Activity, ProjectInstance, Role, Worker, make_workers

Builder = Callable[..., ProjectInstance]


def test_tiny_fixture_loads(tiny: ProjectInstance) -> None:
    assert tiny.n_activities == 5
    assert tiny.n_real == 3
    assert (tiny.source_id, tiny.sink_id) == (0, 4)
    assert [(r.name, r.capacity) for r in tiny.roles] == [("R1", 3)]
    assert len(tiny.workers) == 3
    assert all(w.role == 0 for w in tiny.workers)
    assert [a.duration for a in tiny.activities] == [0, 3, 2, 4, 0]


def test_tiny_topological_order_is_valid(tiny: ProjectInstance) -> None:
    order = tiny.topological_order()
    assert sorted(order) == list(range(tiny.n_activities))
    position = {j: i for i, j in enumerate(order)}
    for act in tiny.activities:
        for succ in act.successors:
            assert position[act.id] < position[succ]


def test_predecessors(tiny: ProjectInstance) -> None:
    assert tiny.predecessors(0) == ()
    assert tiny.predecessors(3) == (1,)
    assert tiny.predecessors(4) == (2, 3)


def test_topological_order_when_ids_are_not_topological(build: Builder) -> None:
    inst = build([0, 2, 3, 0], [[0], [1], [1], [0]], [[2], [3], [1], []])
    assert inst.topological_order() == (0, 2, 1, 3)


def test_make_workers_one_per_capacity_unit() -> None:
    roles = (
        Role(id=0, name="dev", capacity=2),
        Role(id=1, name="qa", capacity=0),
        Role(id=2, name="ops", capacity=1),
    )
    workers = make_workers(roles)
    assert [(w.id, w.role, w.name) for w in workers] == [
        (0, 0, "dev-0"),
        (1, 0, "dev-1"),
        (2, 2, "ops-0"),
    ]


def test_instance_is_frozen(tiny: ProjectInstance) -> None:
    with pytest.raises(ValidationError):
        tiny.name = "other"  # type: ignore[misc]


def test_rejects_cycle(build: Builder) -> None:
    with pytest.raises(ValueError, match="cyclic"):
        build([0, 1, 1, 0], [[0], [1], [1], [0]], [[1], [2], [1, 3], []])


def test_rejects_demand_above_capacity(build: Builder) -> None:
    with pytest.raises(ValueError, match="capacity is 3"):
        build([0, 1, 0], [[0], [4], [0]], [[1], [2], []])


@pytest.mark.parametrize(
    ("durations", "demands", "successors", "message"),
    [
        ([0], [[0]], [[]], "at least the dummy source and sink"),
        ([0, 1, 0], [[0], [1, 1], [0]], [[1], [2], []], "expected 1"),
        ([0, 1, 0], [[0], [1], [0]], [[1], [5], []], "unknown successor"),
        ([0, 1, 0], [[0], [1], [0]], [[1], [0, 2], []], "source activity 0"),
        ([0, 1, 0], [[0], [1], [0]], [[1], [2, 2], []], "more than once"),
        ([0, 1, 0], [[0], [1], [0]], [[1], [2], [1]], "sink activity 2"),
        ([1, 1, 0], [[0], [1], [0]], [[1], [2], []], "dummy activity 0"),
        ([0, 1, 0], [[0], [1], [1]], [[1], [2], []], "dummy activity 2"),
        ([0, 1, 1, 0], [[0], [1], [1], [0]], [[1], [3], [3], []], "not reachable from 0"),
        ([0, 1, 1, 0], [[0], [1], [1], [0]], [[1, 2], [3], [], []], "does not reach 3"),
    ],
)
def test_rejects_invalid_structure(
    build: Builder,
    durations: list[int],
    demands: list[list[int]],
    successors: list[list[int]],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        build(durations, demands, successors)


def _tiny_kwargs(tiny: ProjectInstance) -> dict[str, Any]:
    return {"name": "x", "activities": tiny.activities, "roles": tiny.roles}


def test_rejects_workers_inconsistent_with_capacity(tiny: ProjectInstance) -> None:
    with pytest.raises(ValueError, match="capacity 3 but 2 workers"):
        ProjectInstance(**_tiny_kwargs(tiny), workers=tiny.workers[:2])
    with pytest.raises(ValueError, match="unknown role"):
        ProjectInstance(**_tiny_kwargs(tiny), workers=(Worker(id=0, role=1, name="w"),))


def test_rejects_ids_out_of_order(tiny: ProjectInstance) -> None:
    swapped = (tiny.activities[0], tiny.activities[2], tiny.activities[1], *tiny.activities[3:])
    with pytest.raises(ValueError, match=r"activity ids must be 0\.\.4 in order"):
        ProjectInstance(name="x", activities=swapped, roles=tiny.roles, workers=tiny.workers)


def test_rejects_negative_values() -> None:
    with pytest.raises(ValidationError):
        Activity(id=1, duration=-1, demands=(0,), successors=())
    with pytest.raises(ValidationError):
        Activity(id=1, duration=1, demands=(-1,), successors=())
    with pytest.raises(ValidationError):
        Role(id=0, name="R1", capacity=-1)


def test_optional_deadline_and_budget(tiny: ProjectInstance) -> None:
    assert (tiny.deadline, tiny.budget) == (None, None)
    with_goals = ProjectInstance(**_tiny_kwargs(tiny), workers=tiny.workers, deadline=10, budget=30)
    assert (with_goals.deadline, with_goals.budget) == (10, 30.0)
    with pytest.raises(ValidationError):
        ProjectInstance(**_tiny_kwargs(tiny), workers=tiny.workers, budget=float("nan"))
    with pytest.raises(ValidationError):
        ProjectInstance(**_tiny_kwargs(tiny), workers=tiny.workers, deadline=-1)
