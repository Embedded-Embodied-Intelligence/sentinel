"""Forecast study: forecasts at checkpoints of NoReaction worlds, scored post hoc (WP3b, spec 5.2).

    uv run python -m sentinel.experiments.forecast_study --config configs/wp3_calibration.toml \
        --out results/wp3 [--limit N] [--replications R]

Each instance is one task of a process pool. Its worlds are the WP2b runs: NoReaction on the
cached baseline plan, seed derive_seed(base_seed, set, instance, r) in every scenario and max_days
of the largest delta_D. A world records its observations on the checkpoint days
t_f = floor(f C_plan). Every forecaster receives the observation and its current plan, with one
forecast seed per (set, instance, scenario, replication, f), and its forecast is scored against
the realised makespan after it has been returned. Checkpoints with C <= t_f are skipped.
Realised schedules are checked as in WP2b; a violation aborts the run. forecasts.csv.gz keeps
summary statistics, the PIT pair and the CRPS of every forecast, never its samples. Summaries
come from `forecast_summary` and can be regenerated with `sentinel summarise-forecasts`.
"""

import argparse
import csv
import gzip
import io
import math
import multiprocessing
import shlex
import sys
import time
from collections import Counter
from collections.abc import Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sentinel.data.psplib_loader import instance_path, list_instances, load_psplib, natural_key
from sentinel.data.reference import load_reference
from sentinel.experiments import runs
from sentinel.experiments.forecast_config import ForecasterSpec, ForecastStudyConfig
from sentinel.experiments.forecast_summary import (
    FORECASTS_FILE,
    QUANTILE_COLUMNS,
    QUANTILE_LEVELS,
    write_summaries,
)
from sentinel.experiments.rcpsp_benchmark import format_duration
from sentinel.experiments.simulation_config import Scenario
from sentinel.experiments.simulation_study import (
    Baseline,
    InvalidScheduleError,
    check_run,
    data_provenance,
    plans_digest,
)
from sentinel.forecasting.deterministic import deterministic_forecast
from sentinel.forecasting.forecast import Forecast, forecast
from sentinel.forecasting.metrics import sample_scores
from sentinel.model import ProjectInstance, Schedule, validate_schedule
from sentinel.policies.no_reaction import NoReaction
from sentinel.scheduling.priority_rules import lft_priorities
from sentinel.scheduling.sgs import serial_sgs
from sentinel.simulation.baselines import InvalidPlanError, cached_baseline, read_cached
from sentinel.simulation.engine import SimulationResult, simulate
from sentinel.simulation.state import Observation
from sentinel.simulation.uncertainty import derive_deadline

PROGRESS_INTERVAL_S = 10.0
WORLD_SEED_RULE = (
    "world seed of (instance, replication r) = runs.derive_seed(base_seed, set, instance, str(r)), "
    "shared by all scenarios, as in WP2b"
)
FORECAST_SEED_RULE = (
    "forecast seed of a checkpoint = runs.derive_seed(base_seed, 'forecast', set, instance, "
    "scenario, str(r), f'{f:g}'), shared by all forecasters (common random numbers)"
)

Row = dict[str, Any]


@dataclass(frozen=True)
class Task:
    """One instance with its reference makespan C* and one world seed per replication."""

    set_name: str
    instance: str
    c_star: int
    seeds: tuple[int, ...]
    config: ForecastStudyConfig


@dataclass(frozen=True)
class Outcome:
    """The rows of one task and its baseline."""

    rows: list[Row]
    baseline: Baseline


def checkpoint_day(share: float, plan_makespan: int) -> int:
    """t_f = floor(f C_plan) (spec section 5.2); the tolerance keeps integral products integral."""
    return math.floor(share * plan_makespan + 1e-9)


def forecast_seed(
    base_seed: int, set_name: str, instance: str, scenario: str, replication: int, share: float
) -> int:
    """The seed shared by all forecasters of one checkpoint (spec section 5.2)."""
    keys = ("forecast", set_name, instance, scenario, str(replication), f"{share:g}")
    return runs.derive_seed(base_seed, *keys)


def columns(deltas: Sequence[float]) -> tuple[str, ...]:
    """forecasts.csv.gz columns; one deadline and one p_on_time column per deadline slack."""
    return (
        "set",
        "instance",
        "scenario",
        "lambda_a",
        "replication",
        "seed",
        "forecast_seed",
        "f",
        "checkpoint_day",
        "skipped",
        "forecaster",
        "c_plan",
        "c_star",
        "makespan",
        "truncated",
        *(f"deadline_{delta:g}" for delta in deltas),
        *(f"p_on_time_{delta:g}" for delta in deltas),
        "mean",
        *QUANTILE_COLUMNS,
        "pit_lower",
        "pit_upper",
        "crps",
        "fallbacks",
        "rollouts_truncated",
        "wall_s",
    )


def run_forecaster(spec: ForecasterSpec, observation: Observation, seed: int) -> Forecast:
    """The forecast of `spec` from an observation and its current plan (spec section 5.2)."""
    plan = Schedule(starts=observation.plan)
    if spec.kind == "deterministic":
        return deterministic_forecast(observation, plan, seed=seed)
    return forecast(
        observation,
        plan,
        n_rollouts=spec.n_rollouts,
        seed=seed,
        include_future_disruptions=spec.future_disruptions,
        priors=spec.priors(observation),
    )


def forecast_fields(
    result: Forecast, makespan: int, deltas: Sequence[float], deadlines: Sequence[int]
) -> Row:
    """Scores of one forecast against the realised makespan, computed after it was returned."""
    scores = sample_scores(result.makespans, makespan, QUANTILE_LEVELS)
    return {
        **{
            f"p_on_time_{delta:g}": round(result.p_on_time(deadline), 6)
            for delta, deadline in zip(deltas, deadlines, strict=True)
        },
        "mean": round(scores.mean, 4),
        **dict(zip(QUANTILE_COLUMNS, scores.quantiles, strict=True)),
        "pit_lower": round(scores.cdf_below, 6),
        "pit_upper": round(scores.cdf_at, 6),
        "crps": round(scores.crps, 6),
        "fallbacks": result.fallbacks,
        "rollouts_truncated": result.truncated,
        "wall_s": round(result.wall_time_s, 5),
    }


def world_run(
    task: Task,
    instance: ProjectInstance,
    plan: Schedule,
    scenario: Scenario,
    seed: int,
    days: Sequence[int],
) -> SimulationResult:
    """The WP2b world of one (scenario, seed) with the observations of the checkpoint days."""
    config = task.config
    world = simulate(
        instance,
        plan,
        NoReaction(),
        seed,
        pert=config.pert,
        disruptions=scenario.disruptions,
        deadline=derive_deadline(task.c_star, config.deltas[-1]),  # max_days as in WP2b
        review_period=config.review_period,
        observe_days=days,
    )
    check_run(instance, world, f"{instance.name}, {scenario.name}, seed {seed}")
    return world


def checkpoint_rows(
    task: Task, scenario: Scenario, replication: int, plan_makespan: int, world: SimulationResult
) -> list[Row]:
    """One row per (checkpoint, forecaster) of one world; skipped checkpoints keep empty scores."""
    config = task.config
    deadlines = [derive_deadline(task.c_star, delta) for delta in config.deltas]
    seen = {obs.day: obs for obs in world.observations}
    rows: list[Row] = []
    for share in config.checkpoints:
        day = checkpoint_day(share, plan_makespan)
        seed = forecast_seed(
            config.base_seed, task.set_name, task.instance, scenario.name, replication, share
        )
        common = {
            "set": task.set_name,
            "instance": task.instance,
            "scenario": scenario.name,
            "lambda_a": scenario.lambda_a,
            "replication": replication,
            "seed": world.seed,
            "forecast_seed": seed,
            "f": share,
            "checkpoint_day": day,
            "c_plan": plan_makespan,
            "c_star": task.c_star,
            "makespan": world.makespan,
            "truncated": world.truncated,
            **{
                f"deadline_{delta:g}": deadline
                for delta, deadline in zip(config.deltas, deadlines, strict=True)
            },
        }
        skipped = world.makespan <= day  # complete by day t_f (spec section 5.2)
        for spec in config.forecasters:
            row = common | {"skipped": skipped, "forecaster": spec.name}
            if not skipped:
                result = run_forecaster(spec, seen[day], seed)
                row |= forecast_fields(result, world.makespan, config.deltas, deadlines)
            rows.append(row)
    return rows


def run_instance(task: Task) -> Outcome:
    """Worlds, checkpoint forecasts and scores of one instance (in a worker process)."""
    config = task.config
    instance = load_psplib(instance_path(task.set_name, task.instance, config.data_root))
    plan, cached = cached_baseline(instance, config.baseline_method, config.baseline_cache)
    violations = validate_schedule(instance, plan.schedule)
    if violations:
        raise InvalidScheduleError(
            f"baseline of {instance.name}: {len(violations)} violations, "
            f"first: {violations[0].detail}"
        )
    days = [checkpoint_day(share, plan.makespan) for share in config.checkpoints]
    rows: list[Row] = []
    for scenario in config.scenarios.expand():
        for replication, seed in enumerate(task.seeds):
            world = world_run(task, instance, plan.schedule, scenario, seed, days)
            rows += checkpoint_rows(task, scenario, replication, plan.makespan, world)
    baseline = Baseline(instance.name, plan.makespan, plan.status, cached, plan.schedule.starts)
    return Outcome(rows, baseline)


def build_tasks(
    config: ForecastStudyConfig, limit: int | None
) -> tuple[list[Task], dict[str, list[int]]]:
    """Tasks in (set, instance) order: every `stride`-th instance, then the first `limit`."""
    tasks: list[Task] = []
    seeds: dict[str, list[int]] = {}
    for set_cfg in config.sets:
        references = load_reference(set_cfg.name, set_cfg.reference, config.data_root)
        stems = list_instances(set_cfg.name, config.data_root)[:: set_cfg.stride][:limit]
        for stem in stems:
            name = f"{set_cfg.name}/{stem}"
            c_star = references.get(name)
            if c_star is None or c_star <= 0:
                raise ValueError(f"no positive {set_cfg.reference} reference makespan for {name}")
            instance_seeds = tuple(
                runs.derive_seed(config.base_seed, set_cfg.name, stem, str(r))
                for r in range(config.replications)
            )
            seeds[name] = list(instance_seeds)
            tasks.append(Task(set_cfg.name, stem, c_star, instance_seeds, config))
    return tasks, seeds


def missing_baselines(config: ForecastStudyConfig, tasks: Sequence[Task]) -> list[str]:
    """Instances whose baseline plan is not cached yet; the run will compute them."""
    missing = []
    for task in tasks:
        instance = load_psplib(instance_path(task.set_name, task.instance, config.data_root))
        if read_cached(instance, config.baseline_method, config.baseline_cache) is None:
            missing.append(instance.name)
    return missing


def estimate_duration_s(config: ForecastStudyConfig, tasks: Sequence[Task]) -> float:
    """Wall time from one timed world with all its checkpoint forecasts per set (the busiest
    scenario, replication 0, first instance; its cached baseline, else SGS-LFT), scaled by the
    number of worlds and divided by the workers; missing baselines are not counted."""
    scenario = max(config.scenarios.expand(), key=lambda s: s.lambda_a)
    worlds = len(config.scenarios.expand()) * config.replications
    per_world: dict[str, float] = {}
    for set_cfg in config.sets:
        first = next((t for t in tasks if t.set_name == set_cfg.name), None)
        if first is None:
            continue
        instance = load_psplib(instance_path(first.set_name, first.instance, config.data_root))
        cached = read_cached(instance, config.baseline_method, config.baseline_cache)
        plan = (
            cached.schedule
            if cached is not None
            else serial_sgs(instance, lft_priorities(instance), lower_is_better=True)
        )
        makespan = plan.makespan(instance)
        days = [checkpoint_day(share, makespan) for share in config.checkpoints]
        started = time.perf_counter()
        world = world_run(first, instance, plan, scenario, first.seeds[0], days)
        checkpoint_rows(first, scenario, 0, makespan, world)
        per_world[set_cfg.name] = time.perf_counter() - started
    total = sum(per_world[t.set_name] * worlds for t in tasks)
    return total / max(1, min(config.max_workers, len(tasks)))


def execute(tasks: Sequence[Task], max_workers: int, n_rows: int) -> list[Outcome]:
    """Run all tasks in a process pool (spawn start method), with a progress line every ~10 s."""
    outcomes: list[Outcome] = []
    done_rows = 0
    started = last_report = time.monotonic()
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=max_workers, mp_context=context) as pool:
        pending: set[Future[Outcome]] = {pool.submit(run_instance, task) for task in tasks}
        try:
            while pending:
                due_in = max(0.0, last_report + PROGRESS_INTERVAL_S - time.monotonic())
                done, pending = wait(pending, timeout=due_in, return_when=FIRST_COMPLETED)
                for future in done:
                    outcomes.append(future.result())
                    done_rows += len(outcomes[-1].rows)
                now = time.monotonic()
                if pending and now - last_report >= PROGRESS_INTERVAL_S:
                    elapsed = now - started
                    if done_rows:
                        rest = elapsed / done_rows * (n_rows - done_rows)
                        remaining = f"~{format_duration(rest)} remaining"
                    else:  # an instance takes up to a minute: nothing to extrapolate yet
                        remaining = "first instances running"
                    print(
                        f"[{format_duration(elapsed)}] {len(outcomes)}/{len(tasks)} instances, "
                        f"{done_rows}/{n_rows} forecasts ({100 * done_rows / n_rows:.1f}%), "
                        f"{remaining}",
                        flush=True,
                    )
                    last_report = now
        except BaseException:
            pool.shutdown(wait=True, cancel_futures=True)
            raise
    return outcomes


def write_forecasts(run_dir: Path, rows: Sequence[Row], fieldnames: Sequence[str]) -> str:
    """Write forecasts.csv.gz (gzip mtime 0, so the bytes are reproducible); returns its name."""
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, restval="")
    writer.writeheader()
    writer.writerows(rows)
    data = buffer.getvalue().encode("utf-8")
    (run_dir / FORECASTS_FILE).write_bytes(gzip.compress(data, mtime=0))
    return FORECASTS_FILE


def forecaster_timing(rows: Sequence[Row], workers: int) -> dict[str, dict[str, float]]:
    """Per forecaster: forecasts, mean wall time per forecast inside the workers, and the rate
    of `workers` processes at that time per forecast."""
    timing: dict[str, dict[str, float]] = {}
    for name in dict.fromkeys(r["forecaster"] for r in rows):
        times = [r["wall_s"] for r in rows if r["forecaster"] == name and not r["skipped"]]
        mean = sum(times) / len(times) if times else 0.0
        timing[name] = {
            "forecasts": len(times),
            "mean_wall_s": round(mean, 5),
            "forecasts_per_s": round(workers / mean, 1) if mean > 0 else 0.0,
        }
    return timing


def run_study(
    config_path: Path, out: Path, limit: int | None, replications: int | None, command: str
) -> Path:
    """Execute a forecast study config and write the run directory; returns its path.

    `replications` overrides the config's value; the overridden config is hashed and recorded,
    and the run counts as a smoke run, as does any run with `limit`.
    """
    raw_config = runs.load_toml(config_path)
    overrides: dict[str, Any] = {}
    if replications is not None:
        raw_config["replications"] = overrides["replications"] = replications
    config = ForecastStudyConfig.model_validate(raw_config)
    started = datetime.now(UTC)
    digest = runs.config_hash(raw_config, limit)
    run_id = runs.make_run_id(started, digest)
    git = runs.git_state()  # taken before the run directory exists
    tasks, seeds = build_tasks(config, limit)
    scenarios = config.scenarios.expand()
    n_worlds = len(tasks) * len(scenarios) * config.replications
    n_checkpoints = n_worlds * len(config.checkpoints)
    n_rows = n_checkpoints * len(config.forecasters)
    missing = missing_baselines(config, tasks)
    estimate = estimate_duration_s(config, tasks)
    smoke = limit is not None or bool(overrides)
    run_dir = runs.create_run_dir(out, run_id, smoke=smoke)
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "status": "running",
        "smoke": smoke,
        "command": command,
        "config_path": str(config_path),
        "config": raw_config,
        "config_hash": digest,
        "limit": limit,
        "overrides": overrides,
        "git_commit": git["commit"],
        "git_dirty": git["dirty"],
        "start_utc": runs.utc_iso(started),
        **runs.environment(),
        "max_workers": config.max_workers,
        "n_instances": len(tasks),
        "n_worlds": n_worlds,
        "n_checkpoints": n_checkpoints,
        "forecasters": [f.model_dump(mode="json") for f in config.forecasters],
        "scenarios": [{"name": s.name, **s.disruptions.model_dump(mode="json")} for s in scenarios],
        "seeds": {
            "base_seed": config.base_seed,
            "world_rule": WORLD_SEED_RULE,
            "forecast_rule": FORECAST_SEED_RULE,
            "per_instance": seeds,
        },
        "data": data_provenance(config),
    }
    print(
        f"run {run_id}: {len(tasks)} instances x {len(scenarios)} scenarios x "
        f"{config.replications} replications = {n_worlds} worlds, {len(config.checkpoints)} "
        f"checkpoints x {len(config.forecasters)} forecasters = {n_rows} forecasts, "
        f"{config.max_workers} workers -> {run_dir}",
        flush=True,
    )
    print(
        f"estimated duration: ~{format_duration(estimate)} (one world with its forecasts timed "
        "on the first instance of each set, busiest scenario)",
        flush=True,
    )
    if missing:
        print(
            f"note: {len(missing)} baseline plans ({config.baseline}) are not cached and will be "
            "computed in this run; precompute them with `uv run sentinel baselines --set <set> "
            f"--method {config.baseline}`",
            flush=True,
        )
    try:
        executed = time.monotonic()
        outcomes = execute(tasks, config.max_workers, n_rows)
        wall_s = time.monotonic() - executed
        set_order = {s.name: i for i, s in enumerate(config.sets)}
        scenario_order = {s.name: i for i, s in enumerate(scenarios)}
        rows = [row for outcome in outcomes for row in outcome.rows]
        rows.sort(
            key=lambda r: (
                set_order[r["set"]],
                natural_key(r["instance"]),
                scenario_order[r["scenario"]],
                r["replication"],
            )
        )  # stable: checkpoints and forecasters keep their order within a world
        results_file = write_forecasts(run_dir, rows, columns(config.deltas))
        summaries = write_summaries(run_dir, run_id, config, results_file)
    except BaseException as exc:
        error = f"{type(exc).__name__}: {exc}"
        _finish(manifest, run_dir, started, status="aborted", n_rows=0, error=error)
        raise
    baselines = [outcome.baseline for outcome in outcomes]
    skipped = sum(r["skipped"] for r in rows) // len(config.forecasters)
    _finish(
        manifest,
        run_dir,
        started,
        status="completed",
        n_rows=len(rows),
        results_file=results_file,
        skipped_checkpoints=skipped,
        baselines={
            "method": config.baseline_method.model_dump(mode="json"),
            "cache_root": str(config.baseline_cache),
            "from_cache": sum(b.cached for b in baselines),
            "computed_in_run": sum(not b.cached for b in baselines),
            "statuses": dict(sorted(Counter(b.status for b in baselines).items())),
            "plans_sha256": plans_digest(baselines),
        },
        wp2b_check=summaries.seed_check.as_dict(),
        forecast_wall_s=round(wall_s, 1),
        forecasts_per_s=round(len(rows) / max(wall_s, 1e-9), 2),
        forecaster_timing=forecaster_timing(rows, config.max_workers),
        outputs=[results_file, *summaries.files],
    )
    return run_dir


def _finish(
    manifest: dict[str, Any], run_dir: Path, started: datetime, *, status: str, **fields: Any
) -> None:
    """Complete the manifest with status, end time and duration, then write it."""
    finished = datetime.now(UTC)
    manifest.update(
        status=status,
        end_utc=runs.utc_iso(finished),
        duration_s=round((finished - started).total_seconds(), 1),
        **fields,
    )
    runs.write_json(run_dir / "manifest.json", manifest)


def main(argv: Sequence[str] | None = None) -> int:
    """Command line entry point; returns the exit status."""
    args_list = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="python -m sentinel.experiments.forecast_study",
        description="Forecasts at checkpoints of NoReaction worlds, scored post hoc (WP3b).",
    )
    parser.add_argument("--config", type=Path, required=True, help="study config (TOML)")
    parser.add_argument(
        "--out", type=Path, required=True, help="results directory, e.g. results/wp3"
    )
    parser.add_argument("--limit", type=int, help="smoke run: only the first N instances per set")
    parser.add_argument(
        "--replications", type=int, help="smoke run: override the replications per instance"
    )
    args = parser.parse_args(args_list)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.replications is not None and args.replications < 1:
        parser.error("--replications must be at least 1")
    command = shlex.join(["python", "-m", "sentinel.experiments.forecast_study", *args_list])
    try:
        run_dir = run_study(args.config, args.out, args.limit, args.replications, command)
    except (InvalidScheduleError, InvalidPlanError) as exc:
        print(f"error: invalid schedule, run aborted: {exc}", file=sys.stderr)
        return 1
    print(f"done: {run_dir}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
