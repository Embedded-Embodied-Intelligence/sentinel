"""Time `forecast` on PSPLIB J30/J60 and compare day-0 forecasts with the world (WP3a).

Usage: `uv run python scripts/bench_forecast.py [--per-set 20] [--rollouts 100 200]
[--agreement 2]`. Instances are spread over each set (every 24th of 480) and start from their
`cpsat_det` baseline plans (configs/wp2_noreaction.toml, cache in data/derived/baselines), with
D = ceil(1.2 C*) (C* = j30 opt, j60 hrs) and the primary scenario of docs/experiments/plan.md at
lambda_A = 0.01. One NoReaction world run per instance (seed derive_seed(2026, set, instance,
"wp3a")) gives the observations of days 0, 25, 50 and 75 % of the planned makespan; each is
forecast once per rollout count, with seed derive_seed(2026, set, instance, "forecast"). The
agreement check runs 2000 world runs and 2000 rollouts from day 0 before any event on the first
`--agreement` instances of each set. Prints Markdown; runs in one process.
"""

import argparse
import statistics
import time
from pathlib import Path

from sentinel.data.psplib_loader import instance_path, list_instances, load_psplib
from sentinel.data.reference import load_reference
from sentinel.experiments.runs import derive_seed, load_toml
from sentinel.experiments.simulation_config import StudyConfig
from sentinel.forecasting.forecast import Forecast, forecast
from sentinel.model import ProjectInstance, Schedule
from sentinel.policies.base import EMPTY_DECISION, Decision
from sentinel.policies.no_reaction import NoReaction
from sentinel.simulation.baselines import baseline_plan
from sentinel.simulation.engine import simulate
from sentinel.simulation.events import DisruptionParams
from sentinel.simulation.state import EngineState, Observation, day_limit
from sentinel.simulation.uncertainty import PertParams, derive_deadline, role_costs

PRIMARY = DisruptionParams(lambda_a=0.01, mean_absence=3, lambda_s=0.01, lambda_n=0.02)
SHARES = (0.0, 0.25, 0.5, 0.75)
DELTA = 0.2
TARGET_S = {"j30": 1.0, "j60": 2.0}  # mean wall time per forecast with 200 rollouts
CONFIG = Path("configs/wp2_noreaction.toml")


class Snapshots:
    """Policy that keeps the observations of chosen days and never intervenes."""

    def __init__(self, days: set[int]) -> None:
        self.days = days
        self.seen: dict[int, Observation] = {}

    def decide(self, observation: Observation) -> Decision:
        if observation.day in self.days:
            self.seen[observation.day] = observation
        return EMPTY_DECISION


def initial_observation(
    instance: ProjectInstance, plan: Schedule, pert: PertParams, deadline: int
) -> Observation:
    """Day 0 before any event; the durations are hidden, so any will do."""
    return EngineState(
        instance,
        plan,
        [0] * instance.n_activities,
        role_costs(instance, None),
        pert=pert,
        disruptions=PRIMARY,
        deadline=deadline,
        max_days=day_limit(instance, deadline),
    ).observe()


def time_set(
    config: StudyConfig, set_name: str, stems: list[str], rollouts: list[int]
) -> list[tuple[str, float, int, Forecast]]:
    """(instance, day share, n_rollouts, forecast) for every observation and rollout count."""
    root = config.data_root
    reference = next(s.reference for s in config.sets if s.name == set_name)
    optima = load_reference(set_name, reference, root)
    rows = []
    for stem in stems:
        instance = load_psplib(instance_path(set_name, stem, root))
        plan = baseline_plan(instance, config.baseline_method, config.baseline_cache).schedule
        deadline = derive_deadline(optima[instance.name], DELTA)
        days = {round(share * plan.makespan(instance)): share for share in SHARES}
        snapshots = Snapshots(set(days))
        simulate(
            instance,
            plan,
            snapshots,
            derive_seed(2026, set_name, stem, "wp3a"),
            pert=config.pert,
            disruptions=PRIMARY,
            deadline=deadline,
            review_period=1,  # every day is an epoch, so every day is observed
        )
        seed = derive_seed(2026, set_name, stem, "forecast")
        for day, obs in sorted(snapshots.seen.items()):
            for n in rollouts:
                result = forecast(obs, Schedule(starts=obs.plan), n_rollouts=n, seed=seed)
                rows.append((stem, days[day], n, result))
    return rows


def agreement(config: StudyConfig, set_name: str, stem: str, runs: int = 2000) -> str:
    """Day-0 forecast against `runs` world runs on one instance (Markdown table row)."""
    root = config.data_root
    reference = next(s.reference for s in config.sets if s.name == set_name)
    instance = load_psplib(instance_path(set_name, stem, root))
    plan = baseline_plan(instance, config.baseline_method, config.baseline_cache).schedule
    deadline = derive_deadline(load_reference(set_name, reference, root)[instance.name], DELTA)
    world = [
        simulate(
            instance,
            plan,
            NoReaction(),
            derive_seed(2026, set_name, stem, str(r)),
            pert=config.pert,
            disruptions=PRIMARY,
            deadline=deadline,
        ).makespan
        for r in range(runs)
    ]
    start = initial_observation(instance, plan, config.pert, deadline)
    result = forecast(start, plan, n_rollouts=runs, seed=2026)
    world_mean = statistics.fmean(world)
    gap = 100 * (result.mean - world_mean) / world_mean
    world_on_time = statistics.fmean(c <= deadline for c in world)
    return (
        f"| {instance.name} | {plan.makespan(instance)} | {deadline} | {world_mean:.2f} | "
        f"{result.mean:.2f} | {gap:+.2f} | {world_on_time:.3f} | "
        f"{result.p_on_time(deadline):.3f} | {result.wall_time_s:.2f} |"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--per-set", type=int, default=20)
    parser.add_argument("--rollouts", type=int, nargs="+", default=[100, 200])
    parser.add_argument("--agreement", type=int, default=2)
    args = parser.parse_args()
    config = StudyConfig.model_validate(load_toml(CONFIG))
    began = time.perf_counter()
    print("| Set | Day | n | Forecasts | Mean s | p95 s | Max s | Fallbacks | Truncated |")
    print("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    overall = []
    for set_name in ("j30", "j60"):
        stems = list_instances(set_name, config.data_root)
        stems = stems[:: max(1, len(stems) // args.per_set)][: args.per_set]
        rows = time_set(config, set_name, stems, args.rollouts)
        for n in args.rollouts:
            for share in (*SHARES, None):
                cell = [r for _, s, m, r in rows if m == n and (share is None or s == share)]
                times = sorted(r.wall_time_s for r in cell)
                p95 = times[min(len(times) - 1, round(0.95 * (len(times) - 1)))]
                label = "all" if share is None else f"{100 * share:.0f} %"
                print(
                    f"| {set_name.upper()} | {label} | {n} | {len(cell)} | "
                    f"{statistics.fmean(times):.3f} | {p95:.3f} | {times[-1]:.3f} | "
                    f"{sum(r.fallbacks for r in cell)} | {sum(r.truncated for r in cell)} |"
                )
                if share is None:
                    overall.append((set_name, n, statistics.fmean(times)))
    print()
    for set_name, n, mean in overall:
        if n == 200:
            verdict = "met" if mean <= TARGET_S[set_name] else "missed"
            print(
                f"- {set_name.upper()} n = 200: mean {mean:.3f} s, target "
                f"{TARGET_S[set_name]} s: {verdict}"
            )
    if args.agreement:
        print(
            "\n| Instance | Plan | D | World mean | Forecast mean | Gap % | World P(C <= D) |"
            " Forecast P(C <= D) | Forecast s |"
        )
        print("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
        for set_name in ("j30", "j60"):
            stems = list_instances(set_name, config.data_root)
            for stem in stems[:: len(stems) // args.agreement][: args.agreement]:
                print(agreement(config, set_name, stem))
    print(f"\nTotal {time.perf_counter() - began:.0f} s")


if __name__ == "__main__":
    main()
