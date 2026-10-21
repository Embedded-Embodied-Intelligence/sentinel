"""Policy study: the compared policies of spec section 7 on baseline plans (WP4b, RQ4).

    uv run python -m sentinel.experiments.policy_study --config configs/wp4_baselines.toml \
        --out results/wp4 [--limit N] [--replications R]

Each (instance, scenario) is one task of a process pool: it takes the instance's cached baseline
plan (computing and storing it if missing) and runs every (replication, policy) with
`policy_runs.run_checked`, in debug mode and with every realised schedule checked, so an
infeasible RESEQ plan or schedule aborts the study. The seed of (instance, replication r) is the
WP2b one, shared by all policies and scenarios (common random numbers, spec section 2.3): the
NoReaction runs are WP2b's worlds, and the summaries check their seeds and makespans against the
WP2b results. A run uses max_days of the largest delta_D. No compared policy uses the deadline
(the urgency order of AlwaysSubstitute does not depend on it), so whether each deadline is met
is evaluated post hoc. results.csv.gz has one row per (set, instance, scenario, replication,
policy) with the metrics of spec section 7.1; the summaries come from `policy_summary` and can
be regenerated with `sentinel summarise-policies <run_dir>`.
"""

import argparse
import csv
import gzip
import io
import multiprocessing
import shlex
import statistics
import sys
import time
from collections import Counter
from collections.abc import Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from itertools import zip_longest
from pathlib import Path
from typing import Any

from sentinel.data.psplib_loader import instance_path, list_instances, load_psplib, natural_key
from sentinel.data.reference import load_reference
from sentinel.experiments import runs
from sentinel.experiments.policy_config import PolicyStudyConfig
from sentinel.experiments.policy_runs import InvalidScheduleError, realised_deviation, run_checked
from sentinel.experiments.policy_summary import RESULTS_FILE, write_summaries
from sentinel.experiments.rcpsp_benchmark import format_duration
from sentinel.experiments.simulation_config import Scenario, met_column
from sentinel.experiments.simulation_study import (
    EVENT_KINDS,
    Baseline,
    data_provenance,
    plans_digest,
)
from sentinel.model import ProjectInstance, Schedule, validate_schedule
from sentinel.policies.base import DecisionStats
from sentinel.scheduling.priority_rules import lft_priorities
from sentinel.scheduling.sgs import serial_sgs
from sentinel.simulation.baselines import InvalidPlanError, cached_baseline, read_cached
from sentinel.simulation.engine import SimulationResult
from sentinel.simulation.state import HANDOVER_FACTOR
from sentinel.simulation.uncertainty import derive_budget, derive_deadline

PROGRESS_INTERVAL_S = 10.0
SEED_RULE = (
    "seed of (instance, replication r) = runs.derive_seed(base_seed, set, instance, str(r)), "
    "shared by all policies and scenarios, as in WP2b (common random numbers, spec section 2.3)"
)

Row = dict[str, Any]


@dataclass(frozen=True)
class Task:
    """One instance and scenario with the reference makespan C* and one seed per replication."""

    set_name: str
    instance: str
    c_star: int
    scenario: Scenario
    seeds: tuple[int, ...]
    config: PolicyStudyConfig


@dataclass(frozen=True)
class Outcome:
    """The rows of one task and its baseline."""

    rows: list[Row]
    baseline: Baseline


def columns(deltas: Sequence[float]) -> tuple[str, ...]:
    """results.csv.gz columns; one `met_<delta>` column per deadline slack."""
    return (
        "set",
        "instance",
        "scenario",
        "lambda_a",
        "mean_absence",
        "replication",
        "seed",
        "policy",
        "baseline_makespan",
        "c_star",
        "makespan",
        "ratio_c_star",
        *(met_column(delta) for delta in deltas),
        "total_cost",
        "cost_ratio",
        "deviation",
        "nervousness",
        "substitutions",
        "onboarding_days",
        "handover_days",
        "reseqs",
        "fallbacks",
        "rejected",
        *(f"n_{kind}" for kind in EVENT_KINDS),
        "n_epochs",
        "decisions",
        "decide_s",
        "solve_s",
        "cpsat_deterministic_s",
        "truncated",
        "runtime_s",
    )


def result_row(
    task: Task,
    instance: ProjectInstance,
    baseline: Schedule,
    baseline_makespan: int,
    replication: int,
    policy: str,
    run: tuple[SimulationResult, DecisionStats, float],
    deadlines: Sequence[int],
    budget: float,
) -> Row:
    """One results row (spec section 7.1); the deadline of delta_D is met iff the run is not
    truncated and C <= D. `substitutions` counts replaced crew members, `onboarding_days` their
    m_j o_j crew-member days and `handover_days` the h_j in full-crew days."""
    result, stats, runtime_s = run
    counts: Counter[str] = Counter(event.kind for event in result.events)
    scenario = task.scenario
    met = {
        met_column(delta): not result.truncated and result.makespan <= deadline
        for delta, deadline in zip(task.config.deltas, deadlines, strict=True)
    }
    return {
        "set": task.set_name,
        "instance": task.instance,
        "scenario": scenario.name,
        "lambda_a": scenario.lambda_a,
        "mean_absence": scenario.mean_absence,
        "replication": replication,
        "seed": result.seed,
        "policy": policy,
        "baseline_makespan": baseline_makespan,
        "c_star": task.c_star,
        "makespan": result.makespan,
        "ratio_c_star": round(result.makespan / task.c_star, 6),
        **met,
        "total_cost": round(result.total_cost, 6),
        "cost_ratio": round(result.total_cost / budget, 6),
        "deviation": round(realised_deviation(result, baseline, instance), 6),
        "nervousness": result.nervousness,
        "substitutions": result.n_substituted,
        "onboarding_days": result.onboarding_days,
        "handover_days": round(result.handover_days, 6),
        "reseqs": result.reseqs,
        "fallbacks": stats.fallbacks,
        "rejected": len(result.rejected),
        **{f"n_{kind}": counts[kind] for kind in EVENT_KINDS},
        "n_epochs": result.n_epochs,
        "decisions": stats.decisions,
        "decide_s": round(stats.decide_time_s, 6),
        "solve_s": round(stats.solve_time_s, 6),
        "cpsat_deterministic_s": round(stats.deterministic_time, 6),
        "truncated": result.truncated,
        "runtime_s": round(runtime_s, 6),
    }


def task_runs(
    task: Task, instance: ProjectInstance, plan: Schedule, seeds: Sequence[int]
) -> list[tuple[int, str, tuple[SimulationResult, DecisionStats, float]]]:
    """Every (replication, policy) of `task` on `plan` for the given seeds, checked."""
    config = task.config
    deadline = derive_deadline(task.c_star, config.deltas[-1])  # max_days of the largest delta_D
    done = []
    for replication, seed in enumerate(seeds):
        for policy in config.policies:
            run = run_checked(
                instance,
                plan,
                policy,
                seed,
                pert=config.pert,
                disruptions=task.scenario.disruptions,
                deadline=deadline,
                review_period=config.review_period,
                deterministic_time_limit=config.deterministic_time_limit,
                cp_seed=config.cp_seed,
            )
            done.append((replication, policy, run))
    return done


def run_task(task: Task) -> Outcome:
    """Every (replication, policy) of one instance and scenario (in a worker process)."""
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
    rows = [
        result_row(task, instance, plan.schedule, plan.makespan, r, policy, run, deadlines, budget)
        for r, policy, run in task_runs(task, instance, plan.schedule, task.seeds)
    ]
    baseline = Baseline(instance.name, plan.makespan, plan.status, cached, plan.schedule.starts)
    return Outcome(rows, baseline)


def build_tasks(
    config: PolicyStudyConfig, limit: int | None
) -> tuple[list[Task], dict[str, list[int]]]:
    """Tasks of every `stride`-th instance (then the first `limit`) and scenario, with the
    replication seeds of every instance. The sets are interleaved instance by instance, so that
    the progress estimate sees all of them from the start."""
    by_set: list[list[Task]] = []
    seeds: dict[str, list[int]] = {}
    scenarios = config.scenarios.expand()
    for set_cfg in config.sets:
        references = load_reference(set_cfg.name, set_cfg.reference, config.data_root)
        stems = list_instances(set_cfg.name, config.data_root)[:: set_cfg.stride][:limit]
        tasks: list[Task] = []
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
            tasks += [
                Task(set_cfg.name, stem, c_star, scenario, instance_seeds, config)
                for scenario in scenarios
            ]
        by_set.append(tasks)
    width = len(scenarios)
    blocks = [[tasks[i : i + width] for i in range(0, len(tasks), width)] for tasks in by_set]
    interleaved = [
        task for group in zip_longest(*blocks, fillvalue=[]) for block in group for task in block
    ]
    return interleaved, seeds


def missing_baselines(config: PolicyStudyConfig, tasks: Sequence[Task]) -> list[str]:
    """Instances whose baseline plan is not cached yet; the run will compute them."""
    missing = []
    for name in dict.fromkeys(f"{t.set_name}/{t.instance}" for t in tasks):
        set_name, stem = name.split("/")
        instance = load_psplib(instance_path(set_name, stem, config.data_root))
        if read_cached(instance, config.baseline_method, config.baseline_cache) is None:
            missing.append(instance.name)
    return missing


def estimate_duration_s(config: PolicyStudyConfig, tasks: Sequence[Task]) -> float:
    """Wall time from one timed replication of every policy in the busiest scenario on the first
    instance of each set (its cached baseline, else SGS-LFT), scaled by the replications of
    every task and divided by the workers. Quieter scenarios take less, so this is an upper
    estimate; missing baselines are not counted."""
    busiest = max(config.scenarios.expand(), key=lambda s: (s.lambda_a, s.mean_absence or 0))
    per_replication: dict[str, float] = {}
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
        probe = Task(first.set_name, first.instance, first.c_star, busiest, first.seeds, config)
        started = time.perf_counter()
        task_runs(probe, instance, plan, first.seeds[:1])
        per_replication[set_cfg.name] = time.perf_counter() - started
    total = sum(per_replication[t.set_name] * len(t.seeds) for t in tasks)
    return total / max(1, min(config.max_workers, len(tasks)))


def execute(tasks: Sequence[Task], max_workers: int, n_runs: int) -> list[Outcome]:
    """Run all tasks in a process pool (spawn start method), with a progress line every ~10 s."""
    outcomes: list[Outcome] = []
    done_runs = 0
    started = last_report = time.monotonic()
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=max_workers, mp_context=context) as pool:
        pending: set[Future[Outcome]] = {pool.submit(run_task, task) for task in tasks}
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
                    if done_runs:
                        rest = elapsed / done_runs * (n_runs - done_runs)
                        remaining = f"~{format_duration(rest)} remaining"
                    else:
                        remaining = "first tasks running"
                    print(
                        f"[{format_duration(elapsed)}] {len(outcomes)}/{len(tasks)} tasks, "
                        f"{done_runs}/{n_runs} runs ({100 * done_runs / n_runs:.1f}%), "
                        f"{remaining}",
                        flush=True,
                    )
                    last_report = now
        except BaseException:
            pool.shutdown(wait=True, cancel_futures=True)
            raise
    return outcomes


def write_results(run_dir: Path, rows: Sequence[Row], fieldnames: Sequence[str]) -> str:
    """Write results.csv.gz (gzip mtime 0, so the bytes are reproducible); returns its name."""
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    data = buffer.getvalue().encode("utf-8")
    (run_dir / RESULTS_FILE).write_bytes(gzip.compress(data, mtime=0))
    return RESULTS_FILE


def policy_timing(rows: Sequence[Row]) -> dict[str, dict[str, float]]:
    """Per set and policy: runs, mean and maximum wall time of a run inside the workers."""
    timing: dict[str, dict[str, float]] = {}
    for key in dict.fromkeys((r["set"], r["policy"]) for r in rows):
        times = [r["runtime_s"] for r in rows if (r["set"], r["policy"]) == key]
        timing["/".join(key)] = {
            "runs": len(times),
            "mean_runtime_s": round(statistics.fmean(times), 4),
            "max_runtime_s": round(max(times), 3),
        }
    return timing


def run_study(
    config_path: Path, out: Path, limit: int | None, replications: int | None, command: str
) -> Path:
    """Execute a policy study config and write the run directory; returns its path.

    `replications` overrides the config's value; the overridden config is hashed and recorded,
    and the run counts as a smoke run, as does any run with `limit`.
    """
    raw_config = runs.load_toml(config_path)
    overrides: dict[str, Any] = {}
    if replications is not None:
        raw_config["replications"] = overrides["replications"] = replications
    config = PolicyStudyConfig.model_validate(raw_config)
    started = datetime.now(UTC)
    digest = runs.config_hash(raw_config, limit)
    run_id = runs.make_run_id(started, digest)
    git = runs.git_state()  # taken before the run directory exists
    tasks, seeds = build_tasks(config, limit)
    scenarios = config.scenarios.expand()
    n_runs = len(tasks) * config.replications * len(config.policies)
    missing = missing_baselines(config, tasks)
    smoke = limit is not None or bool(overrides)
    print(
        f"{config.name}: {len(seeds)} instances x {len(scenarios)} scenarios x "
        f"{config.replications} replications x {len(config.policies)} policies = {n_runs} runs, "
        f"T_cp = {config.deterministic_time_limit:g}, {config.max_workers} workers",
        flush=True,
    )
    estimate = estimate_duration_s(config, tasks)
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
        "n_instances": len(seeds),
        "n_tasks": len(tasks),
        "n_runs": n_runs,
        "policies": list(config.policies),
        "cpsat": {
            "deterministic_time_limit": config.deterministic_time_limit,
            "random_seed": config.cp_seed,
            "num_workers": 1,
        },
        "handover_factor": HANDOVER_FACTOR,
        "scenarios": [{"name": s.name, **s.disruptions.model_dump(mode="json")} for s in scenarios],
        "seeds": {"base_seed": config.base_seed, "rule": SEED_RULE, "per_instance": seeds},
        "data": data_provenance(config),
        "estimated_duration_s": round(estimate, 1),
    }
    print(
        f"run {run_id} -> {run_dir}\nestimated duration: ~{format_duration(estimate)} (one "
        "replication of every policy timed on the first instance of each set, busiest scenario; "
        "an upper estimate)",
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
        outcomes = execute(tasks, config.max_workers, n_runs)
        wall_s = time.monotonic() - executed
        set_order = {s.name: i for i, s in enumerate(config.sets)}
        scenario_order = {s.name: i for i, s in enumerate(scenarios)}
        policy_order = {name: i for i, name in enumerate(config.policies)}
        rows = [row for outcome in outcomes for row in outcome.rows]
        rows.sort(
            key=lambda r: (
                set_order[r["set"]],
                natural_key(r["instance"]),
                scenario_order[r["scenario"]],
                r["replication"],
                policy_order[r["policy"]],
            )
        )
        results_file = write_results(run_dir, rows, columns(config.deltas))
        summaries = write_summaries(run_dir, run_id, config, results_file)
    except BaseException as exc:
        error = f"{type(exc).__name__}: {exc}"
        _finish(manifest, run_dir, started, status="aborted", n_rows=0, error=error)
        raise
    by_instance: dict[str, list[Baseline]] = {}
    for outcome in outcomes:  # several tasks per instance: computed if any task computed it
        by_instance.setdefault(outcome.baseline.instance, []).append(outcome.baseline)
    baselines = [
        replace(group[0], cached=all(b.cached for b in group)) for group in by_instance.values()
    ]
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
        wp2b_check=summaries.seed_check.as_dict(),
        checks={
            "rejected_operations": sum(r["rejected"] for r in rows),
            "cpsat_fallbacks": sum(r["fallbacks"] for r in rows),
            "truncated_runs": sum(r["truncated"] for r in rows),
        },
        run_wall_s=round(wall_s, 1),
        runs_per_s=round(len(rows) / max(wall_s, 1e-9), 3),
        policy_timing=policy_timing(rows),
        outputs=[results_file, *summaries.files],
    )
    print(summaries.seed_check.line().removeprefix("- "), flush=True)
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
        prog="python -m sentinel.experiments.policy_study",
        description="The compared policies of spec section 7 on baseline plans (WP4b, RQ4).",
    )
    parser.add_argument("--config", type=Path, required=True, help="study config (TOML)")
    parser.add_argument(
        "--out", type=Path, required=True, help="results directory, e.g. results/wp4"
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
    command = shlex.join(["python", "-m", "sentinel.experiments.policy_study", *args_list])
    try:
        run_dir = run_study(args.config, args.out, args.limit, args.replications, command)
    except (InvalidScheduleError, InvalidPlanError) as exc:
        print(f"error: invalid schedule, run aborted: {exc}", file=sys.stderr)
        return 1
    print(f"done: {run_dir}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
