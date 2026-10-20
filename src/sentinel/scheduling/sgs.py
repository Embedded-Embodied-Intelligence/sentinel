"""Serial schedule generation scheme and regret-based biased random sampling (Kolisch 1996).

At each of the n + 2 stages the serial SGS takes one eligible activity (all predecessors
scheduled) and starts it at the earliest precedence- and resource-feasible time. Free capacity
is kept per role and day in a time-indexed profile that starts at LB0 days and doubles when an
activity would end beyond it.
"""

from bisect import insort
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from sentinel.model.instance import ProjectInstance
from sentinel.model.schedule import Schedule
from sentinel.scheduling.bounds import critical_path_lower_bound, latest_finishes

# Chooses the activity of a stage from the eligible ids (increasing order) and the stage index.
Selector = Callable[[list[int], int], int]


@dataclass(frozen=True)
class _SgsData:
    """Instance data as plain tuples for the inner loop, built once per instance."""

    durations: tuple[int, ...]
    demands: tuple[tuple[tuple[int, int], ...], ...]  # per activity: (role, r_jk) with r_jk > 0
    predecessors: tuple[tuple[int, ...], ...]
    successors: tuple[tuple[int, ...], ...]
    capacities: tuple[int, ...]
    initial_horizon: int


def _sgs_data(instance: ProjectInstance) -> _SgsData:
    acts = instance.activities
    return _SgsData(
        durations=tuple(act.duration for act in acts),
        demands=tuple(tuple((k, r) for k, r in enumerate(act.demands) if r > 0) for act in acts),
        predecessors=tuple(instance.predecessors(j) for j in range(len(acts))),
        successors=tuple(act.successors for act in acts),
        capacities=tuple(role.capacity for role in instance.roles),
        initial_horizon=critical_path_lower_bound(instance),
    )


def _serial_pass(data: _SgsData, select: Selector) -> list[int]:
    """One serial SGS pass; returns the start time of every activity (Kolisch 1996)."""
    n = len(data.durations)
    starts = [0] * n
    finishes = [0] * n
    waiting_for = [len(preds) for preds in data.predecessors]  # unscheduled predecessors
    eligible = [j for j in range(n) if waiting_for[j] == 0]
    horizon = data.initial_horizon
    free = [[cap] * horizon for cap in data.capacities]  # free[k][t]: idle units of role k on t
    for stage in range(n):
        j = select(eligible, stage)
        eligible.remove(j)
        duration = data.durations[j]
        demands = data.demands[j]
        t = max((finishes[i] for i in data.predecessors[j]), default=0)
        if duration > 0 and demands:
            while True:
                end = t + duration
                if end > horizon:
                    horizon = max(end, 2 * horizon)
                    for profile, cap in zip(free, data.capacities, strict=True):
                        profile.extend([cap] * (horizon - len(profile)))
                conflict = t - 1  # latest day in [t, end) without enough idle units
                for k, r in demands:
                    profile = free[k]
                    for day in range(end - 1, conflict, -1):
                        if profile[day] < r:
                            conflict = day
                            break
                if conflict < t:
                    break
                t = conflict + 1  # every start up to `conflict` would overlap that day
            for k, r in demands:
                profile = free[k]
                for day in range(t, t + duration):
                    profile[day] -= r
        starts[j] = t
        finishes[j] = t + duration
        for succ in data.successors[j]:
            waiting_for[succ] -= 1
            if waiting_for[succ] == 0:
                insort(eligible, succ)
    return starts


def serial_sgs(
    instance: ProjectInstance, priorities: Sequence[float], *, lower_is_better: bool
) -> Schedule:
    """Serial SGS taking the highest-priority eligible activity, ties by smallest id (Kolisch 1996).

    `priorities` has one value per activity id; `lower_is_better` gives its direction.
    """
    if len(priorities) != instance.n_activities:
        raise ValueError(f"got {len(priorities)} priorities for {instance.n_activities} activities")
    keys = [(value if lower_is_better else -value, j) for j, value in enumerate(priorities)]

    def select(eligible: list[int], stage: int) -> int:
        return min(eligible, key=keys.__getitem__)

    return Schedule(starts=tuple(_serial_pass(_sgs_data(instance), select)))


def _regret_selector(lf: Sequence[int], alpha: float, draws: Sequence[float]) -> Selector:
    """Choice with probability proportional to (rho_j + 1)^alpha, one uniform draw per stage."""

    def select(eligible: list[int], stage: int) -> int:
        if len(eligible) == 1:
            return eligible[0]
        worst = max(lf[i] for i in eligible)
        weights = [(worst - lf[j] + 1) ** alpha for j in eligible]
        u = draws[stage] * sum(weights)
        for j, weight in zip(eligible, weights, strict=True):
            u -= weight
            if u < 0:
                return j
        return eligible[-1]  # only reached through rounding in the cumulative sum

    return select


def regret_biased_sampling(
    instance: ProjectInstance, n_schedules: int, rng: np.random.Generator, alpha: float = 1.0
) -> tuple[Schedule, int]:
    """Best of up to n serial SGS passes with regret-based biased sampling on LFT.

    Eligible activity j is chosen with probability proportional to (rho_j + 1)^alpha, where
    rho_j = max_{i in EL} LF_i - LF_j and LF uses horizon LB0 (Drexl 1991; Kolisch 1996). Each
    pass draws n + 2 uniforms from `rng`, the only source of randomness. Sampling stops early
    once a schedule reaches LB0, which no schedule can beat. Returns the best schedule (minimum
    makespan, ties: first found) and the number of schedules generated.
    """
    if n_schedules < 1:
        raise ValueError(f"n_schedules must be at least 1, got {n_schedules}")
    data = _sgs_data(instance)
    lf = latest_finishes(instance)
    lb0 = critical_path_lower_bound(instance)
    sink = instance.sink_id
    best: list[int] = []
    generated = 0
    while generated < n_schedules:
        draws: list[float] = rng.random(instance.n_activities).tolist()
        starts = _serial_pass(data, _regret_selector(lf, alpha, draws))
        generated += 1
        if not best or starts[sink] < best[sink]:
            best = starts
            if best[sink] == lb0:
                break
    return Schedule(starts=tuple(best)), generated
