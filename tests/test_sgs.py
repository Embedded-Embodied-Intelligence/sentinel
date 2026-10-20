"""Serial SGS and regret-based biased random sampling."""

from collections.abc import Callable, Sequence

import numpy as np
import pytest

from sentinel.model import ProjectInstance, Schedule, validate_schedule
from sentinel.scheduling.bounds import critical_path_lower_bound, earliest_starts
from sentinel.scheduling.priority_rules import PRIORITY_RULES, lft_priorities
from sentinel.scheduling.sgs import _regret_selector, regret_biased_sampling, serial_sgs

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


def reference_serial_sgs(
    instance: ProjectInstance, priorities: Sequence[float], lower_is_better: bool
) -> tuple[int, ...]:
    """Brute-force serial SGS: try every start from the precedence bound upwards."""
    acts = instance.activities
    starts: dict[int, int] = {}

    def fits(j: int, t: int) -> bool:
        for day in range(t, t + acts[j].duration):
            for k, role in enumerate(instance.roles):
                used = sum(
                    acts[i].demands[k] for i, s in starts.items() if s <= day < s + acts[i].duration
                )
                if used + acts[j].demands[k] > role.capacity:
                    return False
        return True

    while len(starts) < len(acts):
        eligible = [
            j
            for j in range(len(acts))
            if j not in starts and all(i in starts for i in instance.predecessors(j))
        ]
        j = min(eligible, key=lambda e: (priorities[e] if lower_is_better else -priorities[e], e))
        t = max((starts[i] + acts[i].duration for i in instance.predecessors(j)), default=0)
        while not fits(j, t):
            t += 1
        starts[j] = t
    return tuple(starts[j] for j in range(len(acts)))


def random_instance(build: Builder, rng: np.random.Generator) -> ProjectInstance:
    """Random valid instance: 6-10 real activities, 1-2 roles, durations 0-5 (milestones too)."""
    n = int(rng.integers(6, 11))
    capacities = [int(c) for c in rng.integers(2, 6, size=int(rng.integers(1, 3)))]
    successors: list[set[int]] = [set() for _ in range(n + 2)]
    for j in range(1, n + 1):
        for i in rng.choice(j, size=min(j, int(rng.integers(1, 3))), replace=False):
            successors[int(i)].add(j)
    for j in range(1, n + 1):
        if not successors[j]:
            successors[j].add(n + 1)
    durations = [0, *(int(d) for d in rng.integers(0, 6, size=n)), 0]
    demands = [[0] * len(capacities)]
    demands += [[int(rng.integers(0, c + 1)) for c in capacities] for _ in range(n)]
    demands += [[0] * len(capacities)]
    return build(durations, demands, [sorted(s) for s in successors], capacities)


def test_matches_brute_force_reference_on_random_instances(build: Builder) -> None:
    rng = np.random.default_rng(2026)
    for _ in range(40):
        inst = random_instance(build, rng)
        vectors = [(r.priorities(inst), r.lower_is_better) for r in PRIORITY_RULES.values()]
        vectors.append((rng.random(inst.n_activities).tolist(), True))
        for priorities, lower in vectors:
            schedule = serial_sgs(inst, priorities, lower_is_better=lower)
            assert schedule.starts == reference_serial_sgs(inst, priorities, lower)
            assert validate_schedule(inst, schedule) == []


def test_regret_weights_follow_lft(tiny: ProjectInstance) -> None:
    # Eligible {1, 2} with LF = (3, 7): regrets (4, 0), weights (5, 1), P(1) = 5/6.
    lf = lft_priorities(tiny)
    picks = [_regret_selector(lf, 1.0, [u])([1, 2], 0) for u in (0.0, 0.83, 0.84, 0.99)]
    assert picks == [1, 1, 2, 2]
    # alpha = 2: weights (25, 1), P(1) = 25/26 ~ 0.9615.
    assert [_regret_selector(lf, 2.0, [u])([1, 2], 0) for u in (0.96, 0.97)] == [1, 2]
