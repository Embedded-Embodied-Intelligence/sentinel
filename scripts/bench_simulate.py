"""Time `simulate` on PSPLIB J30/J60 and summarise NoReaction runs (WP2a measurements).

Usage: `uv run python scripts/bench_simulate.py [--per-set 40] [--seeds 5]`. Every run uses the
SGS-LFT plan, deadline D = ceil(1.1 C*) (C* = j30 opt, j60 hrs), default PERT and the WP2a
default disruptions; seeds are `derive_seed(2026, set, instance, replication)`. Prints Markdown.
"""

import argparse
import statistics
import time
from collections import Counter
from pathlib import Path

from sentinel.data.psplib_loader import DEFAULT_ROOT, instance_path, list_instances, load_psplib
from sentinel.data.reference import load_reference
from sentinel.experiments.runs import derive_seed
from sentinel.policies.no_reaction import NoReaction
from sentinel.scheduling.priority_rules import lft_priorities
from sentinel.scheduling.sgs import serial_sgs
from sentinel.simulation.engine import SimulationResult, simulate
from sentinel.simulation.events import DisruptionParams
from sentinel.simulation.uncertainty import PertParams, derive_deadline

DEFAULTS = DisruptionParams(lambda_a=0.01, mean_absence=3, lambda_s=0.01, lambda_n=0.02)
REFERENCE = {"j30": "opt", "j60": "hrs"}


def run_set(
    set_name: str, stems: list[str], seeds: int, root: Path
) -> tuple[list[float], list[SimulationResult], list[int], list[int]]:
    """Simulate every (instance, replication); returns call times, results, plan makespans, |W|."""
    reference = load_reference(set_name, REFERENCE[set_name], root)  # type: ignore[arg-type]
    times: list[float] = []
    results: list[SimulationResult] = []
    planned: list[int] = []
    workers: list[int] = []
    for stem in stems:
        inst = load_psplib(instance_path(set_name, stem, root))
        plan = serial_sgs(inst, lft_priorities(inst), lower_is_better=True)
        deadline = derive_deadline(reference[inst.name], 0.1)
        for replication in range(seeds):
            seed = derive_seed(2026, set_name, stem, str(replication))
            started = time.perf_counter()
            result = simulate(
                inst,
                plan,
                NoReaction(),
                seed,
                pert=PertParams(),
                disruptions=DEFAULTS,
                deadline=deadline,
            )
            times.append(time.perf_counter() - started)
            results.append(result)
            planned.append(plan.makespan(inst))
            workers.append(len(inst.workers))
    return times, results, planned, workers


def describe(results: list[SimulationResult], planned: list[int]) -> str:
    """Mean makespan ratio, on-time share, truncations and events per type and run."""
    ratio = statistics.mean(r.makespan / p for r, p in zip(results, planned, strict=True))
    on_time = sum(bool(r.deadline_met) for r in results) / len(results)
    events = Counter(e.kind for r in results for e in r.events)
    n = len(results)
    per_run = ", ".join(f"{kind} {count / n:.2f}" for kind, count in sorted(events.items()))
    return (
        f"runs {len(results)}; realised/planned makespan {ratio:.3f}; on time (D = 1.1 C*) "
        f"{on_time:.3f}; truncated {sum(r.truncated for r in results)}; events {dict(events)} "
        f"(per run: {per_run}); mean epochs {statistics.mean(r.n_epochs for r in results):.1f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--per-set", type=int, default=40, help="instances per set (spread)")
    parser.add_argument("--seeds", type=int, default=5, help="replications per instance")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()

    warm = load_psplib(instance_path("j30", "j301_1", args.root))
    simulate(
        warm,
        serial_sgs(warm, lft_priorities(warm), lower_is_better=True),
        NoReaction(),
        0,
        pert=PertParams(),
        disruptions=DEFAULTS,
        deadline=50,
    )
    print("| Set | Calls | Mean ms | p95 ms | Max ms | Mean workers |")
    print("| --- | ---: | ---: | ---: | ---: | ---: |")
    summaries = []
    for set_name in ("j30", "j60"):
        stems = list_instances(set_name, args.root)
        step = max(1, len(stems) // args.per_set)
        times, results, planned, workers = run_set(
            set_name, stems[::step][: args.per_set], args.seeds, args.root
        )
        ms = sorted(t * 1e3 for t in times)
        p95 = ms[min(len(ms) - 1, round(0.95 * (len(ms) - 1)))]
        print(
            f"| {set_name.upper()} | {len(ms)} | {statistics.mean(ms):.2f} | {p95:.2f} | "
            f"{ms[-1]:.2f} | {statistics.mean(workers):.1f} |"
        )
        summaries.append(f"- {set_name.upper()} timing runs: {describe(results, planned)}")
    print()
    print("\n".join(summaries))
    stems = list_instances("j30", args.root)[::16]
    _, results, planned, _ = run_set("j30", stems, 5, args.root)
    print(f"- J30 30x5 data-test runs (every 16th instance): {describe(results, planned)}")


if __name__ == "__main__":
    main()
