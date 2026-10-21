"""Time the five compared policies and the residual solvers on PSPLIB J30/J60 (WP4a measurements).

Usage:
    uv run python scripts/bench_policies.py [--views 10] [--view-limits 0.5 0.05]
        [--runs j30:20:3 --runs j60:20:3] [--cp-limit 0.5] [--policies ...]
        [--lambdas j30:10 --lambdas j60:10] [--lambda-cp-limit 0.05] [--workers 4]

1. Planning views (this process): NoReaction worlds of every (480 / views)-th instance (seed of
   replication 0) at f = 0, 0.25, 0.5, 0.75 of the plan; times of `planning_view`,
   `residual_sgs` (medians: CP-SAT runs in between, so means catch garbage-collection pauses)
   and CP-SAT (both objectives, means) at each CP-SAT limit, with the number of searches that
   did not prove optimality and the mean change of the makespan and the deviation found.
2. Policy runs (`--runs set:instances:seeds`): the five policies at lambda_A = 0.01 with T_cp =
   `--cp-limit`, every run checked in debug mode (`run_policies`); NoReaction makespans are
   compared with the committed WP2b results.
3. lambda_A sample (`--lambdas set:instances`, one seed): the five policies at every lambda_A of
   spec section 8 with T_cp = `--lambda-cp-limit`, for the duration estimate.

Scenario: E[L] = 3, lambda_S = 0.01, lambda_N = 0.02, T_r = 5, cpsat_det baseline plans, seeds
derive_seed(2026, set, instance, r) as in WP2b, max_days of delta_D = 0.3 and on-time for
delta_D = 0.2. Policy runs are tasks of a spawn pool (one instance each) and are timed inside
the workers. Prints Markdown.
"""

import argparse
import csv
import gzip
import multiprocessing
import statistics
import time
from collections import defaultdict
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from sentinel.data.psplib_loader import DEFAULT_ROOT, instance_path, list_instances, load_psplib
from sentinel.data.reference import load_reference
from sentinel.experiments.policy_runs import WP2B_BASELINE, PolicyRecord, PolicyTask, run_policies
from sentinel.experiments.runs import derive_seed
from sentinel.policies.no_reaction import NoReaction
from sentinel.policies.registry import COMPARED
from sentinel.scheduling.cpsat import solve_residual
from sentinel.scheduling.residual import planning_view, residual_sgs
from sentinel.simulation.baselines import DEFAULT_CACHE_ROOT, cached_baseline
from sentinel.simulation.engine import simulate
from sentinel.simulation.events import DisruptionParams
from sentinel.simulation.uncertainty import PertParams, derive_deadline

REFERENCE = {"j30": "opt", "j60": "hrs"}
WP2B_RESULTS = Path("results/wp2/20261020-181559-6534a712/results.csv.gz")
LAMBDAS = (0.0025, 0.005, 0.01, 0.02)


def scenario(lambda_a: float) -> DisruptionParams:
    return DisruptionParams(lambda_a=lambda_a, mean_absence=3, lambda_s=0.01, lambda_n=0.02)


def spread(set_name: str, count: int, root: Path) -> list[str]:
    """`count` instances spread over the set: every (480 / count)-th."""
    return list_instances(set_name, root)[:: max(1, 480 // count)][:count]


def tasks(
    set_name: str,
    count: int,
    seeds: int,
    lambda_a: float,
    limit: float,
    root: Path,
    policies: Sequence[str] = COMPARED,
) -> list[PolicyTask]:
    references = load_reference(set_name, REFERENCE[set_name], root)  # type: ignore[arg-type]
    return [
        PolicyTask(
            set_name=set_name,
            stem=stem,
            c_star=references[f"{set_name}/{stem}"],
            policies=tuple(policies),
            seeds=tuple(derive_seed(2026, set_name, stem, str(r)) for r in range(seeds)),
            disruptions=scenario(lambda_a),
            deterministic_time_limit=limit,
            data_root=root,
        )
        for stem in spread(set_name, count, root)
    ]


def execute(work: Sequence[PolicyTask], workers: int) -> tuple[list[PolicyRecord], float]:
    began = time.perf_counter()
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=workers, mp_context=context) as pool:
        records = [record for done in pool.map(run_policies, work) for record in done]
    return records, time.perf_counter() - began


def p95(values: Sequence[float]) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]


def policy_table(records: Sequence[PolicyRecord]) -> None:
    print(
        "| Set | Policy | Runs | Mean s | p95 s | Max s | Epochs | Decision ms / epoch "
        "| RESEQs | Fallbacks / CP-SAT stages | On time δ=0.2 | Deviation | Nervousness "
        "| Substituted | Handover days | C / C* |"
    )
    print("| --- | --- |" + " ---: |" * 14)
    groups: dict[tuple[str, str], list[PolicyRecord]] = defaultdict(list)
    for record in records:
        groups[record.set_name, record.policy].append(record)
    for set_name, policy in sorted(groups, key=lambda key: (key[0], COMPARED.index(key[1]))):
        group = groups[set_name, policy]
        times = [r.wall_time_s for r in group]
        decisions = sum(r.stats.decisions for r in group)
        decide = sum(r.stats.decide_time_s for r in group)
        reseqs = sum(r.stats.reseqs for r in group)
        stages = reseqs * (2 if policy.startswith("stable") else 1)
        fallbacks = sum(r.stats.fallbacks for r in group)
        n = len(group)
        print(
            f"| {set_name.upper()} | {policy} | {n} | {statistics.mean(times):.3f} | "
            f"{p95(times):.3f} | {max(times):.3f} | {statistics.mean(r.epochs for r in group):.1f}"
            f" | {1e3 * decide / decisions if decisions else 0:.2f} | {reseqs / n:.1f} | "
            f"{fallbacks} / {stages} | {statistics.mean(r.on_time[0] for r in group):.3f} | "
            f"{statistics.mean(r.deviation for r in group):.2f} | "
            f"{statistics.mean(r.nervousness for r in group):.1f} | "
            f"{statistics.mean(r.substituted for r in group):.1f} | "
            f"{statistics.mean(r.handover_days for r in group):.1f} | "
            f"{statistics.mean(r.makespan / r.c_star for r in group):.3f} |"
        )


def wp2b_check(records: Sequence[PolicyRecord]) -> str:
    """NoReaction seeds and makespans against the committed WP2b rows of scenario la0.01_L3."""
    if not WP2B_RESULTS.is_file():
        return f"WP2b check skipped: {WP2B_RESULTS} not found"
    rows = {}
    with gzip.open(WP2B_RESULTS, "rt", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["scenario"] == "la0.01_L3":
                key = (row["set"], row["instance"], int(row["replication"]))
                rows[key] = (int(row["seed"]), int(row["makespan"]))
    mine = [r for r in records if r.policy == "no_reaction"]
    mismatches = sum(
        rows.get((r.set_name, r.instance, r.replication)) != (r.seed, r.makespan) for r in mine
    )
    return f"WP2b check: {len(mine)} NoReaction runs, {mismatches} seed or makespan mismatches"


def views_table(count: int, limits: Sequence[float], root: Path) -> None:
    """Times of the planning view, the residual SGS and CP-SAT on NoReaction views."""
    head = " | ".join(
        f"CP-SAT {kind} ms @{lim:g} | stopped @{lim:g}"
        for lim in limits
        for kind in ("C", "stable")
    )
    print(
        "| Set | Views | Activities | planning_view ms (median) | residual_sgs ms (median) | "
        f"{head} | ΔC vs first limit | Δdeviation vs first limit |"
    )
    print("| --- |" + " ---: |" * (6 + 4 * len(limits)))
    for set_name in ("j30", "j60"):
        references = load_reference(set_name, REFERENCE[set_name], root)  # type: ignore[arg-type]
        view_ms: list[float] = []
        sgs_ms: list[float] = []
        sizes: list[int] = []
        solve_ms: dict[tuple[float, str], list[float]] = defaultdict(list)
        stopped: dict[tuple[float, str], int] = defaultdict(int)
        values: dict[tuple[float, str], list[int]] = defaultdict(list)
        for stem in spread(set_name, count, root):
            instance = load_psplib(instance_path(set_name, stem, root))
            plan = cached_baseline(instance, WP2B_BASELINE, DEFAULT_CACHE_ROOT)[0]
            result = simulate(
                instance,
                plan.schedule,
                NoReaction(),
                derive_seed(2026, set_name, stem, "0"),
                pert=PertParams(),
                disruptions=scenario(0.01),
                deadline=derive_deadline(references[instance.name], 0.3),
                observe_days=[int(f * plan.makespan) for f in (0.0, 0.25, 0.5, 0.75)],
            )
            if not sizes:  # one untimed call first: the first view pays one-off costs
                residual_sgs(planning_view(result.observations[0]))
            for observation in result.observations:
                began = time.perf_counter()
                view = planning_view(observation)
                view_ms.append(1e3 * (time.perf_counter() - began))
                began = time.perf_counter()
                for _ in range(10):
                    residual_sgs(view)
                sgs_ms.append(1e2 * (time.perf_counter() - began))
                sizes.append(len(view.activities))
                hint = view.planned_starts()
                for limit in limits:
                    for kind in ("C", "stable"):
                        objective = "makespan" if kind == "C" else "stable"
                        solution = solve_residual(
                            view, objective, deterministic_time_limit=limit, seed=0, hint=hint
                        )
                        solve_ms[limit, kind].append(1e3 * solution.wall_time_s)
                        stopped[limit, kind] += solution.status != "OPTIMAL"
                        values[limit, kind].append(solution.objective)
        n = len(sizes)
        cells = " | ".join(
            f"{statistics.mean(solve_ms[lim, kind]):.1f} | {stopped[lim, kind]}"
            for lim in limits
            for kind in ("C", "stable")
        )
        first = limits[0]
        last = limits[-1]
        delta_c = statistics.mean(
            b - a for a, b in zip(values[first, "C"], values[last, "C"], strict=True)
        )
        delta_dev = statistics.mean(
            b - a for a, b in zip(values[first, "stable"], values[last, "stable"], strict=True)
        )
        print(
            f"| {set_name.upper()} | {n} | {statistics.mean(sizes):.1f} | "
            f"{statistics.median(view_ms):.3f} | {statistics.median(sgs_ms):.3f} | {cells} | "
            f"{delta_c:+.3f} | {delta_dev:+.2f} |"
        )


def lambda_table(by_lambda: dict[float, list[PolicyRecord]]) -> None:
    """Mean wall time, RESEQs and epochs per run by lambda_A, set and policy."""
    print(
        "| Set | Policy | "
        + " | ".join(f"λ_A = {lam:g}: s / RESEQs / epochs" for lam in by_lambda)
        + " |"
    )
    print("| --- | --- |" + " ---: |" * len(by_lambda))
    for set_name in ("j30", "j60"):
        for policy in COMPARED:
            cells = []
            for done in by_lambda.values():
                group = [r for r in done if (r.set_name, r.policy) == (set_name, policy)]
                if not group:
                    cells.append("")
                    continue
                cells.append(
                    f"{statistics.mean(r.wall_time_s for r in group):.3f} / "
                    f"{statistics.mean(r.reseqs for r in group):.1f} / "
                    f"{statistics.mean(r.epochs for r in group):.1f}"
                )
            if any(cells):
                print(f"| {set_name.upper()} | {policy} | " + " | ".join(cells) + " |")


def parse_sizes(values: Sequence[str]) -> list[tuple[str, int, int]]:
    """`set:instances[:seeds]` options; seeds default to 1."""
    sizes = []
    for value in values:
        parts = value.split(":")
        sizes.append((parts[0], int(parts[1]), int(parts[2]) if len(parts) > 2 else 1))
    return sizes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--views", type=int, default=10, help="instances per set, 0 to skip")
    parser.add_argument("--view-limits", type=float, nargs="+", default=[0.5, 0.05])
    parser.add_argument("--runs", action="append", default=[], help="set:instances:seeds")
    parser.add_argument("--cp-limit", type=float, default=0.5, help="T_cp of the policy runs")
    parser.add_argument("--policies", nargs="+", default=list(COMPARED), choices=COMPARED)
    parser.add_argument("--lambdas", action="append", default=[], help="set:instances")
    parser.add_argument("--lambda-cp-limit", type=float, default=0.05)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()

    if args.views:
        began = time.perf_counter()
        views_table(args.views, args.view_limits, args.root)
        print(f"\n- planning views measured in {time.perf_counter() - began:.1f} s\n")
    if args.runs:
        work = [
            task
            for set_name, count, seeds in parse_sizes(args.runs)
            for task in tasks(set_name, count, seeds, 0.01, args.cp_limit, args.root, args.policies)
        ]
        records, wall = execute(work, args.workers)
        policy_table(records)
        print(
            f"\n- {len(records)} runs at T_cp = {args.cp_limit:g} in {wall:.1f} s wall with "
            f"{args.workers} workers ({sum(r.wall_time_s for r in records):.1f} s of run time); "
            f"{wp2b_check(records)}\n"
        )
    if args.lambdas:
        by_lambda: dict[float, list[PolicyRecord]] = {}
        for lam in LAMBDAS:
            work = [
                task
                for set_name, count, _ in parse_sizes(args.lambdas)
                for task in tasks(set_name, count, 1, lam, args.lambda_cp_limit, args.root)
            ]
            by_lambda[lam], wall = execute(work, args.workers)
            print(f"- λ_A = {lam:g}: {len(by_lambda[lam])} runs in {wall:.1f} s wall")
        print()
        lambda_table(by_lambda)


if __name__ == "__main__":
    main()
