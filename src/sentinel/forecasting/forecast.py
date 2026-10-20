"""Monte Carlo forecast of the makespan from an observation (spec sections 5 and 5.1)."""

import time

import numpy as np
from pydantic import BaseModel, ConfigDict, NonNegativeFloat, NonNegativeInt, PositiveInt

from sentinel.experiments.runs import derive_seed
from sentinel.forecasting.beliefs import Belief
from sentinel.forecasting.streams import RolloutStreams
from sentinel.model.schedule import Schedule
from sentinel.policies.no_reaction import NoReaction
from sentinel.simulation.engine import Run
from sentinel.simulation.events import DisruptionParams
from sentinel.simulation.state import Observation, SampledWorld, state_from_observation
from sentinel.simulation.uncertainty import PertParams

QUANTILES = (0.1, 0.5, 0.9)
# T_r of the rollouts; decision epochs do not change a NoReaction rollout (spec section 8).
REVIEW_PERIOD = 5
_BASE_POLICY = NoReaction()


class Priors(BaseModel):
    """The forecaster's assumptions: duration multiplier and disruption rates (spec 2.1, 2.2).

    A forecast uses the observation's own `pert` and `disruptions` unless told otherwise;
    other priors model a misspecified forecaster while the world keeps its parameters (5.2).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pert: PertParams
    disruptions: DisruptionParams


class Forecast(BaseModel):
    """Makespan distribution of `n_rollouts` NoReaction rollouts from one observation.

    `makespans[i]` is the makespan of rollout i; a rollout cut at max_days counts max_days, which
    exceeds the deadline (`truncated` counts them). `fallbacks` is the number of belief conditions
    with probability zero, the same in every sampled world (spec section 5.1). The deterministic
    forecast of spec section 5.2 is one rollout without future disruptions.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    day: NonNegativeInt
    seed: NonNegativeInt
    n_rollouts: PositiveInt
    include_future_disruptions: bool
    makespans: tuple[NonNegativeInt, ...]
    truncated: NonNegativeInt
    fallbacks: NonNegativeInt
    wall_time_s: NonNegativeFloat

    @property
    def mean(self) -> float:
        return float(np.mean(self.makespans))

    def quantile(self, q: float) -> int:
        """Empirical q-quantile: the smallest makespan C with a share >= q of rollouts <= C."""
        return int(np.quantile(self.makespans, q, method="inverted_cdf"))

    @property
    def quantiles(self) -> tuple[int, int, int]:
        """The 10 %, 50 % and 90 % quantiles."""
        q10, q50, q90 = (self.quantile(q) for q in QUANTILES)
        return q10, q50, q90

    def p_on_time(self, deadline: int) -> float:
        """Share of rollouts with makespan <= deadline (spec section 5, p-hat)."""
        return sum(c <= deadline for c in self.makespans) / len(self.makespans)


def forecast(
    observation: Observation,
    plan: Schedule,
    *,
    n_rollouts: int,
    seed: int,
    include_future_disruptions: bool = True,
    priors: Priors | None = None,
    _true_world: SampledWorld | None = None,
) -> Forecast:
    """Forecast the makespan of `plan` from `observation` by NoReaction rollouts (spec 5.1).

    Rollout i uses the seed xi_i = derive_seed(seed, "rollout", str(i)) for both its sample of
    the hidden state and its future disruptions (rollout CRN): xi_i spawns a belief stream and
    the streams of D1-D3 after the observed day (ADR-0009), which are off without
    `include_future_disruptions`. The rollout continues the observed day at step 4 and runs to
    the end of the project. `priors` replace the observation's PERT and disruption rates in the
    belief and the future (default: the observation's own). The forecaster sees only the
    observation; `_true_world` is the test hook that replaces the belief by the true hidden
    state (perfect information).
    """
    began = time.perf_counter()
    check_plan(observation, plan)
    if n_rollouts < 1:
        raise ValueError(f"n_rollouts must be positive, got {n_rollouts}")
    if seed < 0:
        raise ValueError(f"seed must be non-negative, got {seed}")
    if priors is not None:
        update = {"pert": priors.pert, "disruptions": priors.disruptions}
        observation = observation.model_copy(update=update)
    belief = Belief(observation) if _true_world is None else None
    params = observation.disruptions if include_future_disruptions else DisruptionParams.none()
    makespans: list[int] = []
    truncated = 0
    fallbacks = 0
    for i in range(n_rollouts):
        root = np.random.SeedSequence(derive_seed(seed, "rollout", str(i)))
        belief_seq, future_seq = root.spawn(2)
        if belief is None:
            assert _true_world is not None
            world = _true_world
        else:
            world = belief.sample(np.random.Generator(np.random.PCG64(belief_seq)))
        fallbacks = world.fallbacks
        finish, cut = rollout(observation, world, plan, params, future_seq)
        truncated += cut
        makespans.append(finish)
    return Forecast(
        day=observation.day,
        seed=seed,
        n_rollouts=n_rollouts,
        include_future_disruptions=include_future_disruptions,
        makespans=tuple(makespans),
        truncated=truncated,
        fallbacks=fallbacks,
        wall_time_s=time.perf_counter() - began,
    )


def check_plan(observation: Observation, plan: Schedule) -> None:
    """Reject anything but an observation and a plan with one start per observed activity."""
    if not isinstance(observation, Observation):
        raise TypeError(f"forecast needs an Observation, got {type(observation).__name__}")
    if not isinstance(plan, Schedule):
        raise TypeError(f"forecast needs a Schedule, got {type(plan).__name__}")
    if len(plan.starts) != len(observation.status):
        raise ValueError(
            f"plan has {len(plan.starts)} starts for {len(observation.status)} activities"
        )


def rollout(
    observation: Observation,
    world: SampledWorld,
    plan: Schedule,
    params: DisruptionParams,
    seq: np.random.SeedSequence,
) -> tuple[int, bool]:
    """Makespan of one NoReaction rollout of `plan` from `observation` completed by `world`, with
    the disruptions `params` after the observed day drawn from `seq` (ADR-0009), and whether it
    was cut at max_days (then the makespan is max_days)."""
    state = state_from_observation(observation, world, plan=plan.starts)
    streams = RolloutStreams(
        seq,
        params,
        observation.pert,
        day=observation.day,
        n_original=observation.instance.n_activities,
        return_day=world.return_day,
    )
    Run(state, streams, _BASE_POLICY, review_period=REVIEW_PERIOD, record_events=False).resume()
    finish = state.start[state.sink]
    if finish is None:
        return state.max_days, True
    return finish, False
