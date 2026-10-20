"""Deterministic plan-based makespan forecast, as classical PM tools show it (spec section 5.2)."""

import time

import numpy as np

from sentinel.forecasting.forecast import Forecast, check_plan, rollout
from sentinel.model.schedule import Schedule
from sentinel.simulation.events import DisruptionParams
from sentinel.simulation.state import (
    DONE,
    UNSTARTED,
    Observation,
    SampledWorld,
    crew_member_days,
)


def nominal_world(observation: Observation) -> SampledWorld:
    """The hidden state with nominal values (spec section 5.2), in crew-member days.

    An unstarted activity has remaining work p_j M_j (inserted ones: their nominal duration).
    A started one starts from p_j M_j, loses the work done, keeps at least one crew-member day
    and is multiplied by F at each observed D2 shock. An absent worker returns on day
    s + max(L_low, t - s + 1): after the announced bound, or tomorrow once it has passed.
    """
    instance = observation.instance
    n_original = instance.n_activities
    shocks: dict[int, list[tuple[float, float]]] = {}
    for j, work_done, factor in observation.work_increases:
        shocks.setdefault(j, []).append((work_done, factor))
    remaining = [0.0] * len(observation.status)
    for j, status in enumerate(observation.status):
        if status == DONE:
            continue
        if j < n_original:
            act = instance.activities[j]
            nominal, demands = act.duration, act.demands
        else:
            inserted = observation.inserted[j - n_original]
            nominal, demands = inserted.duration, inserted.demands
        unit = max(1, sum(demands))  # M_j crew-member days per full-crew day
        units = float(nominal * unit)
        if status != UNSTARTED:
            before = 0
            for work_done, factor in shocks.get(j, ()):
                at_shock = crew_member_days(work_done, unit)
                units = max(units - (at_shock - before), 1.0) * factor
                before = at_shock
            done = crew_member_days(observation.work_done[j], unit)
            units = max(units - (done - before), 1.0)
        remaining[j] = units
    t = observation.day
    return_day = [-1] * len(observation.present)
    for w, present in enumerate(observation.present):
        if present:
            continue
        start, announced = observation.absent_since[w], observation.announced[w]
        if start is None or announced is None:
            raise ValueError(f"absent worker {w} has no absence start or announced bound")
        return_day[w] = start + max(announced, t - start + 1)
    return SampledWorld(tuple(remaining), tuple(return_day))


def deterministic_forecast(observation: Observation, plan: Schedule, *, seed: int) -> Forecast:
    """Point forecast of the makespan of `plan`: one NoReaction run from `observation` with the
    nominal hidden state and no disruptions after the observed day (spec section 5.2).

    The result is a one-rollout `Forecast`, i.e. a point mass, so P(C <= D) is 0 or 1. Nothing
    is random; `seed` is recorded only, so that it matches the other forecasters of a checkpoint.
    """
    began = time.perf_counter()
    check_plan(observation, plan)
    if seed < 0:
        raise ValueError(f"seed must be non-negative, got {seed}")
    world = nominal_world(observation)
    quiet = DisruptionParams.none()
    finish, cut = rollout(observation, world, plan, quiet, np.random.SeedSequence(seed))
    return Forecast(
        day=observation.day,
        seed=seed,
        n_rollouts=1,
        include_future_disruptions=False,
        makespans=(finish,),
        truncated=int(cut),
        fallbacks=0,
        wall_time_s=time.perf_counter() - began,
    )
