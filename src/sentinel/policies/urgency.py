"""Urgency of the activities at a decision epoch: their slack against the deadline (spec 5)."""

from collections.abc import Iterable

from sentinel.forecasting.beliefs import Belief
from sentinel.simulation.state import (
    PAUSED,
    RUNNING,
    UNSTARTED,
    Observation,
    nominal_activity,
    successor_lists,
)


def latest_finishes(observation: Observation, horizon: int) -> list[int]:
    """LF_j of every activity for `horizon`, by a backward pass over the current network (the
    instance with its D3 activities and without those DESCOPE removed) with nominal durations
    (spec section 1.4)."""
    n = len(observation.status)
    successors = successor_lists(observation)
    durations = [nominal_activity(observation, j)[0] for j in range(n)]
    waiting = [0] * n
    for succ in successors:
        for s in succ:
            waiting[s] += 1
    order = [j for j in range(n) if waiting[j] == 0]
    for j in order:  # Kahn's algorithm; `order` grows while it is walked
        for s in successors[j]:
            waiting[s] -= 1
            if waiting[s] == 0:
                order.append(s)
    latest = [horizon] * n
    for j in reversed(order):
        for s in successors[j]:
            latest[j] = min(latest[j], latest[s] - durations[s])
    return latest


def urgencies(observation: Observation, activities: Iterable[int]) -> dict[int, float]:
    """tau_j of spec section 5 for the given unstarted, paused or running activities.

    tau_j = LS_j - t for unstarted and paused activities and LF_j - t - E[remaining_j] for
    running ones, with LS_j = LF_j - p_j, LF_j for the deadline D and E[remaining_j] in
    full-crew days under the belief of spec section 5.1. Without a deadline the planned
    makespan takes the place of D; it shifts every tau_j by the same amount.
    """
    activities = list(activities)
    t = observation.day
    sink = observation.instance.sink_id
    deadline = observation.deadline
    latest = latest_finishes(observation, observation.plan[sink] if deadline is None else deadline)
    status = observation.status
    expected: tuple[float, ...] = ()
    if any(status[j] == RUNNING for j in activities):
        expected = Belief(observation).expected_remaining()
    tau: dict[int, float] = {}
    for j in activities:
        duration, demands = nominal_activity(observation, j)
        if status[j] == RUNNING:
            tau[j] = latest[j] - t - expected[j] / max(1, sum(demands))
        elif status[j] in (UNSTARTED, PAUSED):
            tau[j] = latest[j] - duration - t
        else:
            raise ValueError(f"activity {j} is {status[j]}; urgency needs an unfinished activity")
    return tau
