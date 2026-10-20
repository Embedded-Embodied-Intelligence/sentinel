"""Serial SGS and regret-based biased random sampling."""

from collections.abc import Callable

import numpy as np
import pytest

from sentinel.model import ProjectInstance, Schedule, validate_schedule
from sentinel.scheduling.bounds import critical_path_lower_bound, earliest_starts
from sentinel.scheduling.priority_rules import PRIORITY_RULES, lft_priorities
from sentinel.scheduling.sgs import regret_biased_sampling, serial_sgs

Builder = Callable[..., ProjectInstance]


@pytest.fixture
def crowded(build: Builder) -> ProjectInstance:
    """Capacity 3; 0 -> {1, 2, 3}, 1 -> 4, {2, 3, 4} -> 5. Earliest starts overload day 0.

    p = (0, 2, 3, 2, 1, 0), r = (0, 2, 2, 1, 3, 0); LB0 = 3, optimum 6.
    """
    return build(
        [0, 2, 3, 2, 1, 0],
        [[0], [2], [2], [1], [3], [0]],
        [[1, 2, 3], [4], [5], [5], [5], []],
    )


def lft_schedule(instance: ProjectInstance) -> Schedule:
    return serial_sgs(instance, lft_priorities(instance), lower_is_better=True)


def test_every_rule_gives_feasible_schedule_on_tiny(tiny: ProjectInstance) -> None:
    for rule in PRIORITY_RULES.values():
        schedule = serial_sgs(tiny, rule.priorities(tiny), lower_is_better=rule.lower_is_better)
        assert validate_schedule(tiny, schedule) == [], rule.name
        assert schedule.makespan(tiny) >= 7, rule.name


def test_lft_reaches_optimum_on_tiny(tiny: ProjectInstance) -> None:
    schedule = lft_schedule(tiny)
    assert schedule.starts == (0, 0, 3, 3, 7)
    assert schedule.makespan(tiny) == 7


def test_respects_precedence_and_capacity_where_earliest_starts_overload(
    crowded: ProjectInstance,
) -> None:
    naive = Schedule(starts=earliest_starts(crowded))
    assert {v.kind for v in validate_schedule(crowded, naive)} == {"resource"}

    schedule = lft_schedule(crowded)
    starts = schedule.starts
    assert starts == (0, 0, 2, 0, 5, 6)
    for i, act in enumerate(crowded.activities):
        assert all(starts[j] >= starts[i] + act.duration for j in act.successors)
    for day in range(schedule.makespan(crowded)):
        usage = sum(
            act.demands[0]
            for j, act in enumerate(crowded.activities)
            if starts[j] <= day < starts[j] + act.duration
        )
        assert usage <= crowded.roles[0].capacity, day
    assert validate_schedule(crowded, schedule) == []


def test_priorities_never_override_precedence(tiny: ProjectInstance) -> None:
    # The sink has the best priority but only becomes eligible after all its predecessors.
    schedule = serial_sgs(tiny, [4, 3, 2, 1, 0], lower_is_better=True)
    assert validate_schedule(tiny, schedule) == []


def test_ties_are_broken_by_smallest_id(tiny: ProjectInstance) -> None:
    # All equal: after 0 the order is 1 before 2, then 2 before 3.
    for lower_is_better in (True, False):
        schedule = serial_sgs(tiny, [0] * 5, lower_is_better=lower_is_better)
        assert schedule.starts == (0, 0, 3, 3, 7)


def test_profile_grows_beyond_initial_horizon(build: Builder) -> None:
    # Three parallel activities each needing the whole capacity: makespan 3 * LB0.
    inst = build([0, 4, 4, 4, 0], [[0], [3], [3], [3], [0]], [[1, 2, 3], [4], [4], [4], []])
    schedule = lft_schedule(inst)
    assert critical_path_lower_bound(inst) == 4
    assert schedule.makespan(inst) == 12
    assert validate_schedule(inst, schedule) == []


def test_zero_duration_activity_needs_no_capacity(build: Builder) -> None:
    # Milestone 2 (p = 0, r = 3) is scheduled after 1, which uses all capacity on days 0-1.
    inst = build([0, 2, 0, 0], [[0], [3], [3], [0]], [[1, 2], [3], [3], []])
    schedule = serial_sgs(inst, [0, 0, 1, 2], lower_is_better=True)
    assert schedule.starts == (0, 0, 0, 2)
    assert validate_schedule(inst, schedule) == []


def test_rejects_priority_vector_of_wrong_length(tiny: ProjectInstance) -> None:
    with pytest.raises(ValueError, match="5 activities"):
        serial_sgs(tiny, [0, 1, 2], lower_is_better=True)


def test_rbrs_is_reproducible_with_same_seed(tiny: ProjectInstance) -> None:
    first = regret_biased_sampling(tiny, 50, np.random.default_rng(2026))
    second = regret_biased_sampling(tiny, 50, np.random.default_rng(2026))
    assert first == second
    schedule, generated = first
    assert schedule.makespan(tiny) == 7
    assert 1 <= generated <= 50  # stops once LB0 = 7 is reached
    assert validate_schedule(tiny, schedule) == []


def test_rbrs_generates_full_budget_when_lb0_is_unreachable(crowded: ProjectInstance) -> None:
    schedule, generated = regret_biased_sampling(crowded, 30, np.random.default_rng(1))
    assert generated == 30  # LB0 = 3 < optimum 6
    assert schedule.makespan(crowded) == 6
    assert validate_schedule(crowded, schedule) == []


def test_rbrs_draws_n_plus_two_uniforms_per_schedule(crowded: ProjectInstance) -> None:
    rng = np.random.default_rng(7)
    _, generated = regret_biased_sampling(crowded, 12, rng)
    reference = np.random.default_rng(7)
    reference.random(generated * crowded.n_activities)
    assert rng.random() == reference.random()


def test_rbrs_rejects_empty_budget(tiny: ProjectInstance) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        regret_biased_sampling(tiny, 0, np.random.default_rng(0))
