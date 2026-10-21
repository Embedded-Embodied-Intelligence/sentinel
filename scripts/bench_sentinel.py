"""Time Sentinel and take a first look at it against the WP4b policies (WP5a measurements).

Usage:
    uv run python scripts/bench_sentinel.py [--runs j30:20:3 --runs j60:20:3]
        [--policies no_reaction full_resolve sentinel_full sentinel_no_overtime]
        [--lambdas j30:5 --lambdas j60:5] [--profile j30:j3013_1] [--workers 4]

1. Runs (`--runs set:instances:seeds`): the policies at lambda_A = 0.01 on the same worlds
   (WP2b seeds of replications 0 .. seeds - 1, every (480 / instances)-th instance), every run
   checked in debug mode (`run_policies`). Sentinel works towards D = ceil(1.2 C*) (delta_D =
   0.2); on time for delta_D = 0.3 is evaluated post hoc on the same runs, as for the baselines.
   Prints the timing table of the Sentinel variants (deliberation times, deliberations,
   needs-gate exits, candidates and rollouts per deliberation, time per run), the first-look
   table of every policy (spec section 7.1 metrics, cost / B with B of spec section 1.2 for
   beta = 0.1, overtime share of the cost), how often each candidate type was chosen and which
   component of the decision rule decided.
2. lambda_A sample (`--lambdas set:instances`, replication 0): the Sentinel variants at every
   lambda_A of the plan's primary grid, and the duration estimate of the RQ4 study on its
   subset (120 instances per set, 4 lambda_A, R = 4) on `--workers` workers.
3. Profile (`--profile set:instance`): cProfile of one Sentinel `full` run (replication 0,
   lambda_A = 0.01) in this process; the functions with the most own and cumulative time.

Scenario: E[L] = 3, lambda_S = 0.01, lambda_N = 0.02, T_r = 5, T_cp = 0.1, `cpsat_det` baseline
plans; runs are tasks of a spawn pool (one instance each), timed inside the workers. Prints
Markdown.
"""

import argparse
import cProfile
import io
import multiprocessing
import pstats
import statistics
import time
from collections import Counter, defaultdict
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from bench_policies import REFERENCE, p95, parse_sizes, spread, wp2b_check

from sentinel.agent.candidates import KINDS
from sentinel.data.psplib_loader import DEFAULT_ROOT, instance_path, load_psplib
from sentinel.data.reference import load_reference
from sentinel.experiments.policy_runs import (
    WP2B_BASELINE,
    PolicyRecord,
    PolicyTask,
    run_checked,
    run_policies,
)
from sentinel.experiments.runs import derive_seed
from sentinel.policies.registry import SENTINELS
from sentinel.policies.sentinel import SentinelStats
from sentinel.simulation.baselines import DEFAULT_CACHE_ROOT, cached_baseline
from sentinel.simulation.events import DisruptionParams
from sentinel.simulation.uncertainty import PertParams, derive_budget, derive_deadline

LAMBDAS = (0.0, 0.005, 0.01, 0.02)  # primary grid of docs/experiments/plan.md
POLICIES = ("no_reaction", "full_resolve", "sentinel_full", "sentinel_no_overtime")
STUDY_INSTANCES = 120  # per set: every 4th instance (docs/experiments/plan.md)
STUDY_REPLICATIONS = 4


def scenario(lambda_a: float) -> DisruptionParams:
    return DisruptionParams(lambda_a=lambda_a, mean_absence=3, lambda_s=0.01, lambda_n=0.02)


def tasks(
    set_name: str, count: int, seeds: int, lambda_a: float, policies: Sequence[str], root: Path
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


def sentinel_stats(record: PolicyRecord) -> SentinelStats:
    stats = record.stats
    assert isinstance(stats, SentinelStats)
    return stats


def timing_table(records: Sequence[PolicyRecord]) -> None:
    """Deliberation timings of the Sentinel variants per set."""
    print(
        "| Set | Variant | Runs | Deliberation mean s | p95 s | max s | Deliberations / run "
        "| Gate exits / run | Skipped epochs / run | Candidates / deliberation "
        "| Rollouts / deliberation | CP-SAT s / deliberation | s / run | p95 s / run |"
    )
    print("| --- | --- |" + " ---: |" * 12)
    groups = grouped(records, SENTINELS)
    for (set_name, policy), group in groups.items():
        stats = [sentinel_stats(r) for r in group]
        times = [t for s in stats for t in s.deliberation_s]
        deliberations = sum(s.deliberations for s in stats)
        evaluated = deliberations - sum(s.gate_exits for s in stats)
        runs = [r.wall_time_s for r in group]
        n = len(group)
        print(
            f"| {set_name.upper()} | {policy} | {n} | {statistics.mean(times):.3f} | "
            f"{p95(times):.3f} | {max(times):.3f} | {deliberations / n:.1f} | "
            f"{sum(s.gate_exits for s in stats) / n:.1f} | {sum(s.skipped for s in stats) / n:.1f}"
            f" | {sum(s.candidates for s in stats) / max(1, evaluated):.2f} | "
            f"{sum(s.rollouts for s in stats) / deliberations:.0f} | "
            f"{sum(s.solve_time_s for s in stats) / deliberations:.3f} | "
            f"{statistics.mean(runs):.1f} | {p95(runs):.1f} |"
        )


def grouped(
    records: Sequence[PolicyRecord], policies: Sequence[str]
) -> dict[tuple[str, str], list[PolicyRecord]]:
    groups: dict[tuple[str, str], list[PolicyRecord]] = defaultdict(list)
    for record in records:
        if record.policy in policies:
            groups[record.set_name, record.policy].append(record)
    return dict(
        sorted(groups.items(), key=lambda item: (item[0][0], list(policies).index(item[0][1])))
    )


def budgets(records: Sequence[PolicyRecord], root: Path) -> dict[tuple[str, str], float]:
    """B = 1.1 sum_j sum_k r_jk p-bar_j of every instance (spec section 1.2, c_k = 1)."""
    found: dict[tuple[str, str], float] = {}
    for record in records:
        key = (record.set_name, record.instance)
        if key not in found:
            instance = load_psplib(instance_path(record.set_name, record.instance, root))
            found[key] = derive_budget(instance, 0.1, params=PertParams())
    return found


def first_look(records: Sequence[PolicyRecord], policies: Sequence[str], root: Path) -> None:
    """Spec section 7.1 metrics per set and policy (means per run)."""
    budget = budgets(records, root)
    print(
        "| Set | Policy | Runs | On time δ=0.2 | On time δ=0.3 (post hoc) | C / C* "
        "| Deviation d | Nervousness | Cost / B | Overtime share of cost | Substituted "
        "| Hired | RESEQs | SHIFTs | s / run |"
    )
    print("| --- | --- |" + " ---: |" * 13)
    for (set_name, policy), group in grouped(records, policies).items():
        cost = sum(r.total_cost for r in group)
        print(
            f"| {set_name.upper()} | {policy} | {len(group)} | "
            f"{statistics.mean(r.on_time[0] for r in group):.3f} | "
            f"{statistics.mean(r.on_time[-1] for r in group):.3f} | "
            f"{statistics.mean(r.makespan / r.c_star for r in group):.3f} | "
            f"{statistics.mean(r.deviation for r in group):.2f} | "
            f"{statistics.mean(r.nervousness for r in group):.1f} | "
            f"{statistics.mean(r.total_cost / budget[r.set_name, r.instance] for r in group):.3f}"
            f" | {sum(r.overtime_cost for r in group) / cost:.4f} | "
            f"{statistics.mean(r.substituted for r in group):.1f} | "
            f"{statistics.mean(r.hired for r in group):.1f} | "
            f"{statistics.mean(r.reseqs for r in group):.1f} | "
            f"{statistics.mean(r.shifts for r in group):.1f} | "
            f"{statistics.mean(r.wall_time_s for r in group):.2f} |"
        )


def chosen_table(records: Sequence[PolicyRecord]) -> None:
    """Share of the deliberations of each Sentinel variant by outcome: needs-gate exit or the
    chosen candidate type."""
    print("| Set | Variant | Deliberations | Gate exit | " + " | ".join(KINDS) + " |")
    print("| --- | --- |" + " ---: |" * (2 + len(KINDS)))
    for (set_name, policy), group in grouped(records, SENTINELS).items():
        stats = [sentinel_stats(r) for r in group]
        total = sum(s.deliberations for s in stats)
        chosen: Counter[str] = Counter()
        for s in stats:
            chosen.update(s.chosen)
        exits = sum(s.gate_exits for s in stats)
        cells = " | ".join(f"{100 * chosen[kind] / total:.1f}" for kind in KINDS)
        print(f"| {set_name.upper()} | {policy} | {total} | {100 * exits / total:.1f} | {cells} |")


def reasons_table(records: Sequence[PolicyRecord]) -> None:
    """Share of the deliberations of each Sentinel variant by the reason of the decision."""
    names = ("needs_met", "only_candidate", "on_time", "budget", "stability", "level", "order")
    names += ("utility",)
    print("| Set | Variant | Deliberations | " + " | ".join(names) + " |")
    print("| --- | --- |" + " ---: |" * (1 + len(names)))
    for (set_name, policy), group in grouped(records, SENTINELS).items():
        stats = [sentinel_stats(r) for r in group]
        total = sum(s.deliberations for s in stats)
        reasons: Counter[str] = Counter()
        for s in stats:
            reasons.update(s.reasons)
        cells = " | ".join(f"{100 * reasons[name] / total:.1f}" for name in names)
        print(f"| {set_name.upper()} | {policy} | {total} | {cells} |")


def estimate(by_lambda: dict[float, list[PolicyRecord]], workers: int) -> None:
    """CPU and wall hours of the RQ4 study on the plan's subset for each Sentinel variant."""
    print(
        "| Set | Variant | "
        + " | ".join(f"s / run @ λ_A = {lam:g}" for lam in by_lambda)
        + " | Runs | CPU h | Wall h on "
        + f"{workers} workers |"
    )
    print("| --- | --- |" + " ---: |" * (len(by_lambda) + 3))
    total = 0.0
    sets = sorted({r.set_name for done in by_lambda.values() for r in done})
    for set_name in sets:
        for policy in SENTINELS:
            means = []
            for done in by_lambda.values():
                group = [r for r in done if (r.set_name, r.policy) == (set_name, policy)]
                means.append(statistics.mean(r.wall_time_s for r in group) if group else None)
            if any(m is None for m in means):
                continue
            per_lambda = STUDY_INSTANCES * STUDY_REPLICATIONS
            cpu = sum(per_lambda * m for m in means if m is not None) / 3600
            total += cpu
            cells = " | ".join(f"{m:.1f}" for m in means if m is not None)
            print(
                f"| {set_name.upper()} | {policy} | {cells} | {per_lambda * len(means)} | "
                f"{cpu:.1f} | {cpu / workers:.1f} |"
            )
    print(f"\n- total {total:.1f} CPU h, {total / workers:.1f} h wall at full use")


def profile(set_name: str, stem: str, root: Path) -> None:
    """cProfile of one Sentinel run (replication 0, lambda_A = 0.01) in this process."""
    references = load_reference(set_name, REFERENCE[set_name], root)  # type: ignore[arg-type]
    instance = load_psplib(instance_path(set_name, stem, root))
    plan = cached_baseline(instance, WP2B_BASELINE, DEFAULT_CACHE_ROOT)[0]
    deadline = derive_deadline(references[f"{set_name}/{stem}"], 0.2)
    profiler = cProfile.Profile()
    profiler.enable()
    result, stats, wall = run_checked(
        instance,
        plan.schedule,
        "sentinel_full",
        derive_seed(2026, set_name, stem, "0"),
        pert=PertParams(),
        disruptions=scenario(0.01),
        deadline=deadline,
        review_period=5,
        deterministic_time_limit=0.1,
    )
    profiler.disable()
    assert isinstance(stats, SentinelStats)
    print(
        f"- profile of {set_name}/{stem}: {wall:.1f} s under cProfile, "
        f"{stats.deliberations} deliberations, makespan {result.makespan}, D {deadline}\n"
    )
    for key in ("tottime", "cumulative"):
        text = io.StringIO()
        pstats.Stats(profiler, stream=text).sort_stats(key).print_stats(14)
        lines = [line for line in text.getvalue().splitlines() if line.strip()]
        start = next(i for i, line in enumerate(lines) if line.lstrip().startswith("ncalls"))
        print(f"Top by {key}:\n```")
        for line in lines[start : start + 15]:
            print(line.replace(str(Path.cwd()) + "/", "")[:150])
        print("```\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", action="append", default=[], help="set:instances:seeds")
    parser.add_argument("--policies", nargs="+", default=list(POLICIES))
    parser.add_argument("--lambdas", action="append", default=[], help="set:instances")
    parser.add_argument("--profile", default=None, help="set:instance")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()

    if args.runs:
        work = [
            task
            for set_name, count, seeds in parse_sizes(args.runs)
            for task in tasks(set_name, count, seeds, 0.01, args.policies, args.root)
        ]
        records, wall = execute(work, args.workers)
        timing_table(records)
        print()
        first_look(records, args.policies, args.root)
        print()
        chosen_table(records)
        print()
        reasons_table(records)
        print(
            f"\n- {len(records)} runs in {wall:.1f} s wall with {args.workers} workers "
            f"({sum(r.wall_time_s for r in records):.1f} s of run time); "
            f"{sum(r.rejected for r in records)} rejected operations; {wp2b_check(records)}\n"
        )
    if args.lambdas:
        by_lambda: dict[float, list[PolicyRecord]] = {}
        for lam in LAMBDAS:
            work = [
                task
                for set_name, count, _ in parse_sizes(args.lambdas)
                for task in tasks(set_name, count, 1, lam, SENTINELS[:2], args.root)
            ]
            by_lambda[lam], wall = execute(work, args.workers)
            print(f"- λ_A = {lam:g}: {len(by_lambda[lam])} runs in {wall:.1f} s wall")
        print()
        estimate(by_lambda, args.workers)
    if args.profile:
        set_name, stem = args.profile.split(":")
        profile(set_name, stem, args.root)


if __name__ == "__main__":
    main()
