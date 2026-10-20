"""Scenario study: NoReaction on baseline plans over disruption scenarios (WP2b, spec 2-3).

    uv run python -m sentinel.experiments.simulation_study --config configs/wp2_noreaction.toml \
        --out results/wp2 [--limit N] [--replications R]

Each instance is one task of a process pool: it takes the instance's baseline plan from the
cache (computing and storing it if missing) and simulates every (scenario, replication). The
seed of (instance, replication) is shared by all scenarios (common random numbers, spec
section 2.3). A run uses max_days of the largest delta_D; whether the deadline of every
delta_D is met is evaluated post hoc, which is exact because NoReaction ignores the deadline.
Baseline plans and realised schedules are checked (validate_schedule, execution_violations);
a violation aborts the run. Run identity, manifest and outputs follow the experiment-run skill;
summaries are generated from the results file by `simulation_summary`.
"""

import argparse
import csv
import gzip
import hashlib
import io
import json
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
from sentinel.experiments.rcpsp_benchmark import format_duration
from sentinel.experiments.simulation_config import Scenario, StudyConfig, met_column
from sentinel.experiments.simulation_summary import write_summaries
from sentinel.model import ProjectInstance, validate_schedule
from sentinel.policies.no_reaction import NoReaction
from sentinel.scheduling.priority_rules import lft_priorities
from sentinel.scheduling.sgs import serial_sgs
from sentinel.simulation.baselines import InvalidPlanError, cached_baseline, read_cached
from sentinel.simulation.engine import SimulationResult, simulate
from sentinel.simulation.realised import execution_violations, realised_instance
from sentinel.simulation.uncertainty import derive_budget, derive_deadline

EVENT_KINDS = ("absence", "work_increase", "new_activity", "new_activity_skipped")
PROGRESS_INTERVAL_S = 10.0
PLAIN_CSV_LIMIT_BYTES = 15_000_000  # larger results are written as results.csv.gz
SEED_RULE = (
    "seed of (instance, replication r) = runs.derive_seed(base_seed, set, instance, str(r)), "
    "shared by all scenarios (common random numbers, spec section 2.3)"
)

Row = dict[str, Any]


class InvalidScheduleError(RuntimeError):
    """A baseline plan or a realised schedule violates spec section 1.3 or 3.1."""


@dataclass(frozen=True)
class Task:
    """One instance with its reference makespan C* and one seed per replication."""

    set_name: str
    instance: str
    c_star: int
    seeds: tuple[int, ...]
    config: StudyConfig


@dataclass(frozen=True)
class Baseline:
    """Provenance of the baseline plan an instance's runs started from."""

    instance: str
    makespan: int
    status: str
    cached: bool
    starts: tuple[int, ...]


@dataclass(frozen=True)
class Outcome:
    """The rows of one task and its baseline."""

    rows: list[Row]
    baseline: Baseline


def columns(deltas: Sequence[float]) -> tuple[str, ...]:
    """results.csv columns; one `met_<delta>` column per deadline slack."""
    return (
        "set",
        "instance",
        "scenario",
        "replication",
        "seed",
        "baseline_makespan",
        "c_star",
        "makespan",
        "ratio_c_star",
        *(met_column(delta) for delta in deltas),
        "total_cost",
        "cost_ratio",
        *(f"n_{kind}" for kind in EVENT_KINDS),
        "n_epochs",
        "truncated",
        "runtime_s",
    )


def check_run(instance: ProjectInstance, result: SimulationResult, where: str) -> None:
    """Raise on a realised schedule that violates spec 1.3 or the crew rules of 3.1 a-b."""
    problems = execution_violations(instance, result)
    if not result.truncated:  # a truncated run has no complete schedule to validate
        realised, schedule = realised_instance(instance, result)
        problems += [v.detail for v in validate_schedule(realised, schedule)]
    if problems:
        raise InvalidScheduleError(f"{where}: {len(problems)} violations, first: {problems[0]}")


def result_row(
    task: Task,
    scenario: Scenario,
    replication: int,
    baseline_makespan: int,
    result: SimulationResult,
    deadlines: Sequence[int],
    budget: float,
    runtime_s: float,
) -> Row:
    """One results.csv row; the deadline D of delta_D is met iff not truncated and C <= D."""
    counts: Counter[str] = Counter(event.kind for event in result.events)
    met = {
        met_column(delta): not result.truncated and result.makespan <= deadline
        for delta, deadline in zip(task.config.deltas, deadlines, strict=True)
    }
    return {
        "set": task.set_name,
        "instance": task.instance,
        "scenario": scenario.name,
        "replication": replication,
        "seed": result.seed,
        "baseline_makespan": baseline_makespan,
        "c_star": task.c_star,
        "makespan": result.makespan,
        "ratio_c_star": round(result.makespan / task.c_star, 6),
        **met,
        "total_cost": round(result.total_cost, 6),
        "cost_ratio": round(result.total_cost / budget, 6),
        **{f"n_{kind}": counts[kind] for kind in EVENT_KINDS},
        "n_epochs": result.n_epochs,
        "truncated": result.truncated,
        "runtime_s": round(runtime_s, 6),
    }


def run_instance(task: Task) -> Outcome:
    """Simulate every (scenario, replication) of one instance (in a worker process)."""
    config = task.config
    instance = load_psplib(instance_path(task.set_name, task.instance, config.data_root))
    plan, cached = cached_baseline(instance, config.baseline_method, config.baseline_cache)
    violations = validate_schedule(instance, plan.schedule)
    if violations:
        raise InvalidScheduleError(
            f"baseline of {instance.name}: {len(violations)} violations, "
            f"first: {violations[0].detail}"
        )
    deadlines = [derive_deadline(task.c_star, delta) for delta in config.deltas]
    budget = derive_budget(instance, config.beta, params=config.pert)
    rows: list[Row] = []
    for scenario in config.scenarios.expand():
        for replication, seed in enumerate(task.seeds):
            started = time.perf_counter()
            result = simulate(
                instance,
                plan.schedule,
                NoReaction(),
                seed,
                pert=config.pert,
                disruptions=scenario.disruptions,
                deadline=deadlines[-1],  # max_days of the largest delta_D
                review_period=config.review_period,
            )
            runtime_s = time.perf_counter() - started
            check_run(instance, result, f"{instance.name}, {scenario.name}, seed {seed}")
            rows.append(
                result_row(
                    task, scenario, replication, plan.makespan, result, deadlines, budget, runtime_s
                )
            )
    baseline = Baseline(instance.name, plan.makespan, plan.status, cached, plan.schedule.starts)
    return Outcome(rows, baseline)


def build_tasks(config: StudyConfig, limit: int | None) -> tuple[list[Task], dict[str, list[int]]]:
    """Tasks in (set, instance) order and the replication seeds of every instance."""
    tasks: list[Task] = []
    seeds: dict[str, list[int]] = {}
    for set_cfg in config.sets:
        references = load_reference(set_cfg.name, set_cfg.reference, config.data_root)
        for stem in list_instances(set_cfg.name, config.data_root)[:limit]:
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


def missing_baselines(config: StudyConfig, tasks: Sequence[Task]) -> list[str]:
    """Instances whose baseline plan is not cached yet; the run will compute them."""
    missing = []
    for task in tasks:
        instance = load_psplib(instance_path(task.set_name, task.instance, config.data_root))
        if read_cached(instance, config.baseline_method, config.baseline_cache) is None:
            missing.append(instance.name)
    return missing


def estimate_duration_s(config: StudyConfig, tasks: Sequence[Task]) -> float:
    """Wall time from one timed replication of every scenario on the first instance of each set
    (its cached baseline, else SGS-LFT), checks included; missing baselines are not counted."""
    scenarios = config.scenarios.expand()
    per_run: dict[str, float] = {}
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
        deadline = derive_deadline(first.c_star, config.deltas[-1])
        started = time.perf_counter()
        for scenario in scenarios:
            result = simulate(
                instance,
                plan,
                NoReaction(),
                first.seeds[0],
                pert=config.pert,
                disruptions=scenario.disruptions,
                deadline=deadline,
                review_period=config.review_period,
            )
            check_run(instance, result, f"estimate on {instance.name}")
        per_run[set_cfg.name] = (time.perf_counter() - started) / len(scenarios)
    total = sum(per_run[t.set_name] * len(scenarios) * len(t.seeds) for t in tasks)
    return total / max(1, min(config.max_workers, len(tasks)))


def execute(tasks: Sequence[Task], max_workers: int, n_runs: int) -> list[Outcome]:
    """Run all tasks in a process pool (spawn start method), with a progress line every ~10 s."""
    outcomes: list[Outcome] = []
    done_runs = 0
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
                    done_runs += len(outcomes[-1].rows)
                now = time.monotonic()
                if pending and now - last_report >= PROGRESS_INTERVAL_S:
                    elapsed = now - started
                    remaining = elapsed / max(1, done_runs) * (n_runs - done_runs)
                    print(
                        f"[{format_duration(elapsed)}] {len(outcomes)}/{len(tasks)} instances, "
                        f"{done_runs}/{n_runs} runs ({100 * done_runs / n_runs:.1f}%), "
                        f"~{format_duration(remaining)} remaining",
                        flush=True,
                    )
                    last_report = now
        except BaseException:
            pool.shutdown(wait=True, cancel_futures=True)
            raise
    return outcomes


def write_results(run_dir: Path, rows: Sequence[Row], fieldnames: Sequence[str]) -> str:
    """Write results.csv, or results.csv.gz (fixed mtime) if the CSV would exceed
    PLAIN_CSV_LIMIT_BYTES; returns the file name."""
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    data = buffer.getvalue().encode("utf-8")
    if len(data) <= PLAIN_CSV_LIMIT_BYTES:
        (run_dir / "results.csv").write_bytes(data)
        return "results.csv"
    (run_dir / "results.csv.gz").write_bytes(gzip.compress(data, mtime=0))
    return "results.csv.gz"


def plans_digest(baselines: Sequence[Baseline]) -> str:
    """SHA-256 over the start times of every baseline plan, in instance-name order."""
    lines = [
        f"{b.instance}:{','.join(map(str, b.starts))}"
        for b in sorted(baselines, key=lambda b: b.instance)
    ]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def data_provenance(config: StudyConfig) -> dict[str, Any]:
    """Content hashes of the instance sets and reference files from the data MANIFEST.json."""
    path = config.data_root / "MANIFEST.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    instances, solutions = data.get("instances", {}), data.get("solutions", {})
    return {
        "root": str(config.data_root),
        "instances_content_sha256": {
            s.name: instances.get(s.name, {}).get("content_sha256") for s in config.sets
        },
        "references_sha256": {
            f"{s.name}_{s.reference}": solutions.get(f"{s.name}_{s.reference}", {}).get("sha256")
            for s in config.sets
        },
    }


def run_study(
    config_path: Path, out: Path, limit: int | None, replications: int | None, command: str
) -> Path:
    """Execute a study config and write the run directory; returns its path.

    `replications` overrides the config's value; the overridden config is hashed and recorded,
    and the run counts as a smoke run, as does any run with `limit`.
    """
    raw_config = runs.load_toml(config_path)
    overrides: dict[str, Any] = {}
    if replications is not None:
        raw_config["replications"] = overrides["replications"] = replications
    config = StudyConfig.model_validate(raw_config)
    started = datetime.now(UTC)
    digest = runs.config_hash(raw_config, limit)
    run_id = runs.make_run_id(started, digest)
    git = runs.git_state()  # taken before the run directory exists
    tasks, seeds = build_tasks(config, limit)
    scenarios = config.scenarios.expand()
    n_runs = len(tasks) * len(scenarios) * config.replications
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
        "n_simulations": n_runs,
        "scenarios": [{"name": s.name, **s.disruptions.model_dump(mode="json")} for s in scenarios],
        "seeds": {"base_seed": config.base_seed, "rule": SEED_RULE, "per_instance": seeds},
        "data": data_provenance(config),
    }
    print(
        f"run {run_id}: {len(tasks)} instances x {len(scenarios)} scenarios x "
        f"{config.replications} replications = {n_runs} simulations, "
        f"{config.max_workers} workers -> {run_dir}",
        flush=True,
    )
    print(
        f"estimated duration: ~{format_duration(estimate)} (one replication of every scenario "
        "timed on the first instance of each set)",
        flush=True,
    )
    if missing:
        print(
            f"note: {len(missing)} baseline plans ({config.baseline}) are not cached and will be "
            "computed in this run; precompute them with `uv run sentinel baselines --set <set> "
            f"--method {config.baseline} --config {config_path}`",
            flush=True,
        )
    try:
        executed = time.monotonic()
        outcomes = execute(tasks, config.max_workers, n_runs)
        simulation_wall_s = time.monotonic() - executed
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
        )
        results_file = write_results(run_dir, rows, columns(config.deltas))
        outputs = [results_file, *write_summaries(run_dir, run_id, config, results_file)]
    except BaseException as exc:
        error = f"{type(exc).__name__}: {exc}"
        _finish(manifest, run_dir, started, status="aborted", n_rows=0, error=error)
        raise
    baselines = [outcome.baseline for outcome in outcomes]
    _finish(
        manifest,
        run_dir,
        started,
        status="completed",
        n_rows=len(rows),
        results_file=results_file,
        baselines={
            "method": config.baseline_method.model_dump(mode="json"),
            "cache_root": str(config.baseline_cache),
            "from_cache": sum(b.cached for b in baselines),
            "computed_in_run": sum(not b.cached for b in baselines),
            "statuses": dict(sorted(Counter(b.status for b in baselines).items())),
            "plans_sha256": plans_digest(baselines),
        },
        simulation_wall_s=round(simulation_wall_s, 1),
        simulations_per_s=round(n_runs / max(simulation_wall_s, 1e-9), 1),
        outputs=outputs,
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
        prog="python -m sentinel.experiments.simulation_study",
        description="NoReaction scenario study on baseline plans (WP2b).",
    )
    parser.add_argument("--config", type=Path, required=True, help="study config (TOML)")
    parser.add_argument(
        "--out", type=Path, required=True, help="results directory, e.g. results/wp2"
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
    command = shlex.join(["python", "-m", "sentinel.experiments.simulation_study", *args_list])
    try:
        run_dir = run_study(args.config, args.out, args.limit, args.replications, command)
    except (InvalidScheduleError, InvalidPlanError) as exc:
        print(f"error: invalid schedule, run aborted: {exc}", file=sys.stderr)
        return 1
    print(f"done: {run_dir}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
