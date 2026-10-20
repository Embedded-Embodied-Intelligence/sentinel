"""RQ2 benchmark: priority-rule SGS, RBRS and CP-SAT on PSPLIB sets (spec section 1.5).

    uv run python -m sentinel.experiments.rcpsp_benchmark --config configs/wp1_rq2.toml \
        --out results/wp1 [--limit N]

Every (instance, method) pair is one task of a process pool. Every schedule is checked with
`validate_schedule`; an invalid one aborts the run. Run identity, manifest and outputs follow
the experiment-run skill; summaries are generated from results.csv by `rcpsp_summary`.
"""

import argparse
import csv
import json
import multiprocessing
import shlex
import sys
import time
from collections.abc import Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, assert_never

import numpy as np

from sentinel.data.psplib_loader import instance_path, list_instances, load_psplib, natural_key
from sentinel.data.reference import load_reference
from sentinel.experiments import runs
from sentinel.experiments.rcpsp_config import (
    BenchmarkConfig,
    CpsatMethod,
    Method,
    RbrsMethod,
    SgsMethod,
)
from sentinel.experiments.rcpsp_summary import write_summaries
from sentinel.model import ProjectInstance, Schedule, validate_schedule
from sentinel.scheduling.bounds import critical_path_lower_bound
from sentinel.scheduling.cpsat import solve_cpsat
from sentinel.scheduling.priority_rules import PRIORITY_RULES
from sentinel.scheduling.sgs import regret_biased_sampling, serial_sgs

COLUMNS = (
    "set",
    "instance",
    "method",
    "makespan",
    "lb0",
    "c_ref",
    "dev_ref_pct",
    "dev_lb0_pct",
    "matches_ref",
    "status",
    "solver_bound",
    "runtime_s",
    "seed",
)
PROGRESS_INTERVAL_S = 10.0
CALIBRATION_SCHEDULES = 20
SEED_RULE = (
    "seed of an instance = runs.derive_seed(base_seed, set, instance), shared by all randomized "
    "methods on that instance (common random numbers); deterministic methods record no seed"
)

Row = dict[str, Any]


class InvalidScheduleError(RuntimeError):
    """A method returned a schedule that violates spec section 1.3."""


@dataclass(frozen=True)
class Task:
    """One method on one instance, with the instance's seed and reference makespan."""

    set_name: str
    instance: str
    data_root: Path
    method: Method
    seed: int
    c_ref: int | None


@dataclass(frozen=True)
class Outcome:
    """A method's schedule (None if none was found), status, solver bound and seed used."""

    schedule: Schedule | None
    status: str
    solver_bound: int | None = None
    seed: int | None = None


def run_method(instance: ProjectInstance, method: Method, seed: int) -> Outcome:
    """Run one configured method; deterministic methods ignore `seed`."""
    match method:
        case SgsMethod():
            rule = PRIORITY_RULES[method.rule]
            priorities = rule.priorities(instance)
            schedule = serial_sgs(instance, priorities, lower_is_better=rule.lower_is_better)
            return Outcome(schedule, "FEASIBLE")
        case RbrsMethod():
            rng = np.random.default_rng(seed)
            schedule, _ = regret_biased_sampling(instance, method.n_schedules, rng, method.alpha)
            return Outcome(schedule, "FEASIBLE", seed=seed)
        case CpsatMethod():
            result = solve_cpsat(
                instance,
                time_limit_s=method.time_limit_s,
                num_workers=method.num_workers,
                random_seed=seed,
            )
            return Outcome(result.schedule, result.status, result.lower_bound, seed)
        case _:
            assert_never(method)


def deviation_pct(makespan: int | None, reference: int | None) -> float | None:
    """100 (C - ref) / ref in % (spec section 1.5), 4 decimals; None if undefined."""
    if makespan is None or reference is None or reference <= 0:
        return None
    return round(100 * (makespan - reference) / reference, 4)


def run_task(task: Task) -> Row:
    """Run one task (in a worker process), validate its schedule and return its CSV row."""
    instance = load_psplib(instance_path(task.set_name, task.instance, task.data_root))
    started = time.perf_counter()
    outcome = run_method(instance, task.method, task.seed)
    runtime_s = time.perf_counter() - started
    makespan = None
    if outcome.schedule is not None:
        violations = validate_schedule(instance, outcome.schedule)
        if violations:
            raise InvalidScheduleError(
                f"{instance.name} with {task.method.name}: {len(violations)} violations, "
                f"first: {violations[0].detail}"
            )
        makespan = outcome.schedule.makespan(instance)
    lb0 = critical_path_lower_bound(instance)
    return {
        "set": task.set_name,
        "instance": task.instance,
        "method": task.method.name,
        "makespan": makespan,
        "lb0": lb0,
        "c_ref": task.c_ref,
        "dev_ref_pct": deviation_pct(makespan, task.c_ref),
        "dev_lb0_pct": deviation_pct(makespan, lb0),
        "matches_ref": None if makespan is None or task.c_ref is None else makespan == task.c_ref,
        "status": outcome.status,
        "solver_bound": outcome.solver_bound,
        "runtime_s": round(runtime_s, 6),
        "seed": outcome.seed,
    }


def build_tasks(config: BenchmarkConfig, limit: int | None) -> tuple[list[Task], dict[str, int]]:
    """Tasks in (set, instance, method) order and the seed of every instance."""
    tasks: list[Task] = []
    seeds: dict[str, int] = {}
    for set_cfg in config.sets:
        references = load_reference(set_cfg.name, set_cfg.reference, config.data_root)
        for stem in list_instances(set_cfg.name, config.data_root)[:limit]:
            name = f"{set_cfg.name}/{stem}"
            seeds[name] = runs.derive_seed(config.base_seed, set_cfg.name, stem)
            tasks += [
                Task(
                    set_cfg.name, stem, config.data_root, method, seeds[name], references.get(name)
                )
                for method in config.methods
            ]
    return tasks, seeds


def estimate_duration_s(config: BenchmarkConfig, tasks: Sequence[Task]) -> float:
    """Upper-bound wall time: heuristics timed on each set's first instance, CP-SAT at its limit."""
    rng = np.random.default_rng(config.base_seed)  # calibration only; tasks use their own seeds
    cost: dict[tuple[str, str], float] = {}
    for set_cfg in config.sets:
        first = next((t.instance for t in tasks if t.set_name == set_cfg.name), None)
        if first is None:
            continue
        instance = load_psplib(instance_path(set_cfg.name, first, config.data_root))
        for method in config.methods:
            started = time.perf_counter()
            match method:
                case SgsMethod():
                    run_method(instance, method, 0)
                    seconds = time.perf_counter() - started
                case RbrsMethod():
                    _, n = regret_biased_sampling(
                        instance, CALIBRATION_SCHEDULES, rng, method.alpha
                    )
                    seconds = (time.perf_counter() - started) / n * method.n_schedules
                case CpsatMethod():
                    seconds = method.time_limit_s
                case _:
                    assert_never(method)
            cost[(set_cfg.name, method.name)] = seconds
    total = sum(cost[(t.set_name, t.method.name)] for t in tasks)
    return total / max(1, min(config.max_workers, len(tasks)))


def execute(tasks: Sequence[Task], max_workers: int) -> list[Row]:
    """Run all tasks in a process pool (spawn start method), with a progress line every ~10 s."""
    rows: list[Row] = []
    started = last_report = time.monotonic()
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=max_workers, mp_context=context) as pool:
        pending: set[Future[Row]] = {pool.submit(run_task, task) for task in tasks}
        try:
            while pending:
                due_in = max(0.0, last_report + PROGRESS_INTERVAL_S - time.monotonic())
                done, pending = wait(pending, timeout=due_in, return_when=FIRST_COMPLETED)
                rows.extend(future.result() for future in done)
                now = time.monotonic()
                if pending and now - last_report >= PROGRESS_INTERVAL_S:
                    elapsed = now - started
                    remaining = elapsed / max(1, len(rows)) * (len(tasks) - len(rows))
                    print(
                        f"[{format_duration(elapsed)}] {len(rows)}/{len(tasks)} tasks "
                        f"({100 * len(rows) / len(tasks):.1f}%), "
                        f"~{format_duration(remaining)} remaining",
                        flush=True,
                    )
                    last_report = now
        except BaseException:
            pool.shutdown(wait=True, cancel_futures=True)
            raise
    return rows


def write_results(path: Path, rows: Sequence[Row]) -> None:
    """results.csv with the columns of COLUMNS; None becomes an empty cell."""
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def data_provenance(config: BenchmarkConfig) -> dict[str, Any]:
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


def format_duration(seconds: float) -> str:
    """Seconds as `42 s`, `12.5 min` or `1.3 h`."""
    if seconds < 90:
        return f"{seconds:.0f} s"
    if seconds < 90 * 60:
        return f"{seconds / 60:.1f} min"
    return f"{seconds / 3600:.1f} h"


def run_benchmark(config_path: Path, out: Path, limit: int | None, command: str) -> Path:
    """Execute a benchmark config and write the run directory; returns its path."""
    raw_config = runs.load_toml(config_path)
    config = BenchmarkConfig.model_validate(raw_config)
    started = datetime.now(UTC)
    digest = runs.config_hash(raw_config, limit)
    run_id = runs.make_run_id(started, digest)
    git = runs.git_state()  # taken before the run directory exists
    tasks, seeds = build_tasks(config, limit)
    estimate = estimate_duration_s(config, tasks)
    run_dir = runs.create_run_dir(out, run_id, smoke=limit is not None)
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "status": "running",
        "smoke": limit is not None,
        "command": command,
        "config_path": str(config_path),
        "config": raw_config,
        "config_hash": digest,
        "limit": limit,
        "git_commit": git["commit"],
        "git_dirty": git["dirty"],
        "start_utc": runs.utc_iso(started),
        **runs.environment(),
        "max_workers": config.max_workers,
        "n_tasks": len(tasks),
        "seeds": {"base_seed": config.base_seed, "rule": SEED_RULE, "per_instance": seeds},
        "data": data_provenance(config),
    }
    print(
        f"run {run_id}: {len(tasks)} tasks ({len(seeds)} instances x {len(config.methods)} "
        f"methods), {config.max_workers} workers -> {run_dir}",
        flush=True,
    )
    print(
        f"estimated duration: <= {format_duration(estimate)} (CP-SAT counted at its full time "
        "limit, heuristics timed on the first instance of each set)",
        flush=True,
    )
    try:
        rows = execute(tasks, config.max_workers)
        set_order = {s.name: i for i, s in enumerate(config.sets)}
        method_order = {m.name: i for i, m in enumerate(config.methods)}
        rows.sort(
            key=lambda r: (
                set_order[r["set"]],
                natural_key(r["instance"]),
                method_order[r["method"]],
            )
        )
        write_results(run_dir / "results.csv", rows)
        outputs = ["results.csv", *write_summaries(run_dir, run_id, config)]
    except BaseException as exc:
        error = f"{type(exc).__name__}: {exc}"
        _finish(manifest, run_dir, started, status="aborted", n_rows=0, error=error)
        raise
    _finish(manifest, run_dir, started, status="completed", n_rows=len(rows), outputs=outputs)
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
        prog="python -m sentinel.experiments.rcpsp_benchmark",
        description="RCPSP benchmark of SGS priority rules, RBRS and CP-SAT (RQ2).",
    )
    parser.add_argument("--config", type=Path, required=True, help="benchmark config (TOML)")
    parser.add_argument(
        "--out", type=Path, required=True, help="results directory, e.g. results/wp1"
    )
    parser.add_argument("--limit", type=int, help="smoke run: only the first N instances per set")
    args = parser.parse_args(args_list)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    command = shlex.join(["python", "-m", "sentinel.experiments.rcpsp_benchmark", *args_list])
    try:
        run_dir = run_benchmark(args.config, args.out, args.limit, command)
    except InvalidScheduleError as exc:
        print(f"error: invalid schedule, run aborted: {exc}", file=sys.stderr)
        return 1
    print(f"done: {run_dir}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
