"""The forecaster against the world on a PSPLIB instance (needs downloaded data)."""

from pathlib import Path
from statistics import fmean

import pytest

from sentinel.data.psplib_loader import instance_path, load_psplib
from sentinel.data.reference import load_reference, reference_path
from sentinel.experiments.runs import derive_seed
from sentinel.forecasting.forecast import forecast
from sentinel.policies.no_reaction import NoReaction
from sentinel.scheduling.priority_rules import lft_priorities
from sentinel.scheduling.sgs import serial_sgs
from sentinel.simulation.engine import simulate
from sentinel.simulation.events import DisruptionParams
from sentinel.simulation.state import EngineState, day_limit
from sentinel.simulation.uncertainty import PertParams, derive_deadline, role_costs

pytestmark = pytest.mark.data

# Primary scenario of docs/experiments/plan.md with lambda_A = 0.01, deadline slack 0.2.
PRIMARY = DisruptionParams(lambda_a=0.01, mean_absence=3, lambda_s=0.01, lambda_n=0.02)
RUNS = 2000


def test_day_zero_forecast_agrees_with_the_world(psplib_root: Path) -> None:
    """2000 rollouts from day 0 before any event against 2000 world runs: the rollout layout
    has the distributions of spec section 2.2 (only the events of day 0 itself differ)."""
    if not reference_path("j30", "opt", psplib_root).is_file():
        pytest.skip("j30_opt.sm missing; run scripts/fetch_psplib.py")
    stem = "j301_1"
    instance = load_psplib(instance_path("j30", stem, psplib_root))
    plan = serial_sgs(instance, lft_priorities(instance), lower_is_better=True)
    deadline = derive_deadline(load_reference("j30", "opt", psplib_root)[instance.name], 0.2)
    pert = PertParams()
    world = [
        simulate(
            instance,
            plan,
            NoReaction(),
            derive_seed(2026, "j30", stem, str(r)),
            pert=pert,
            disruptions=PRIMARY,
            deadline=deadline,
        )
        for r in range(RUNS)
    ]
    start = EngineState(
        instance,
        plan,
        [0] * instance.n_activities,  # hidden, not part of the observation
        role_costs(instance, None),
        pert=pert,
        disruptions=PRIMARY,
        deadline=deadline,
        max_days=day_limit(instance, deadline),
    ).observe()
    result = forecast(start, plan, n_rollouts=RUNS, seed=2026)
    world_mean = fmean(r.makespan for r in world)
    world_on_time = fmean(r.makespan <= deadline for r in world)
    print(
        f"\n{instance.name}: forecast mean {result.mean:.3f}, world mean {world_mean:.3f}; "
        f"P(C <= {deadline}) forecast {result.p_on_time(deadline):.3f}, world "
        f"{world_on_time:.3f}; forecast {result.wall_time_s:.2f} s"
    )
    assert abs(result.mean - world_mean) <= 0.02 * world_mean
    assert result.truncated == 0 and not any(r.truncated for r in world)
