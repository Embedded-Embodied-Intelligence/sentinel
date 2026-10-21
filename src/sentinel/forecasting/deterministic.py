"""Deterministic plan-based makespan forecast, as classical PM tools show it (spec section 5.2)."""

import time

import numpy as np

from sentinel.forecasting.forecast import Forecast, check_plan, rollout
from sentinel.model.schedule import Schedule
from sentinel.simulation.events import DisruptionParams
from sentinel.simulation.state import Observation, nominal_world


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
