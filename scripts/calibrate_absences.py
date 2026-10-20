"""Calibration table of WP2a.1: NoReaction on SGS-LFT plans over a grid of lambda_A.

Usage: `uv run python scripts/calibrate_absences.py [--per-set 30] [--seeds 5]`. Per set, every
16th instance (30 of 480), replications 0 .. seeds-1 with seeds `derive_seed(2026, set,
instance, replication)` shared by all scenarios (common random numbers) and the default PERT.
The lambda_A grid uses E[L] = 3, lambda_S = 0.01 and lambda_N = 0.02; reference rows have no
disruption, D2 only or D3 only. C* is the PSPLIB optimum (j30 opt) or best known makespan (j60
hrs). A run is on time for delta if its makespan is at most D = ceil((1 + delta) C*) (spec
section 1.2); max_days comes from the largest delta. Prints Markdown.
"""

import argparse
import statistics
from pathlib import Path

from sentinel.data.psplib_loader import DEFAULT_ROOT, instance_path, list_instances, load_psplib
from sentinel.data.reference import load_reference
from sentinel.experiments.runs import derive_seed
from sentinel.policies.no_reaction import NoReaction
from sentinel.scheduling.priority_rules import lft_priorities
from sentinel.scheduling.sgs import serial_sgs
from sentinel.simulation.engine import SimulationResult, simulate
from sentinel.simulation.events import Absence, DisruptionParams
from sentinel.simulation.uncertainty import PertParams, derive_deadline

LAMBDA_A = (0.0, 0.0025, 0.005, 0.01, 0.02)
SCENARIOS = {
    "none": DisruptionParams.none(),
    "D2 only": DisruptionParams(lambda_a=0, mean_absence=1, lambda_s=0.01, lambda_n=0),
    "D3 only": DisruptionParams(lambda_a=0, mean_absence=1, lambda_s=0, lambda_n=0.02),
    **{
        f"λ_A = {a}": DisruptionParams(lambda_a=a, mean_absence=3, lambda_s=0.01, lambda_n=0.02)
        for a in LAMBDA_A
    },
}
DELTAS = (0.1, 0.2, 0.3)
REFERENCE = {"j30": "opt", "j60": "hrs"}


def absent_share(result: SimulationResult, n_workers: int) -> float:
    """Share of the run's worker-days (days 0 .. makespan - 1) on which the worker was absent."""
    end = result.makespan
    days = sum(
        max(0, min(e.day + e.length, end) - e.day) for e in result.events if isinstance(e, Absence)
    )
    return days / (n_workers * end) if end else 0.0


def calibrate(set_name: str, per_set: int, seeds: int, root: Path) -> list[str]:
    """Markdown rows (one per scenario) and a footnote line on the plans of one set."""
    reference = load_reference(set_name, REFERENCE[set_name], root)  # type: ignore[arg-type]
    stems = list_instances(set_name, root)
    stems = stems[:: max(1, len(stems) // per_set)][:per_set]
    rows: dict[str, list[tuple[float, list[bool], bool, float]]] = {s: [] for s in SCENARIOS}
    plan_ratio: list[float] = []
    for stem in stems:
        inst = load_psplib(instance_path(set_name, stem, root))
        plan = serial_sgs(inst, lft_priorities(inst), lower_is_better=True)
        planned, c_star = plan.makespan(inst), reference[inst.name]
        plan_ratio.append(planned / c_star)
        deadlines = [derive_deadline(c_star, delta) for delta in DELTAS]
        for replication in range(seeds):
            seed = derive_seed(2026, set_name, stem, str(replication))
            for scenario, params in SCENARIOS.items():
                result = simulate(
                    inst,
                    plan,
                    NoReaction(),
                    seed,
                    pert=PertParams(),
                    disruptions=params,
                    deadline=deadlines[-1],
                )
                on_time = [not result.truncated and result.makespan <= d for d in deadlines]
                share = absent_share(result, len(inst.workers))
                rows[scenario].append((result.makespan / planned, on_time, result.truncated, share))
    lines = []
    for scenario, runs in rows.items():
        ratio = statistics.mean(r[0] for r in runs)
        shares = [100 * sum(r[1][i] for r in runs) / len(runs) for i in range(len(DELTAS))]
        on_time = " | ".join(f"{s:.1f}%" for s in shares)
        truncated = sum(r[2] for r in runs)
        absent = 100 * statistics.mean(r[3] for r in runs)
        lines.append(
            f"| {set_name.upper()} | {scenario} | {len(runs)} | {ratio:.3f} | {on_time} | "
            f"{truncated} | {absent:.2f}% |"
        )
    lines.append(
        f"- {set_name.upper()}: {len(stems)} instances x {seeds} seeds; SGS-LFT plan / C* mean "
        f"{statistics.mean(plan_ratio):.3f}, plans at C* {sum(r == 1 for r in plan_ratio)}"
    )
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--per-set", type=int, default=30, help="instances per set (spread)")
    parser.add_argument("--seeds", type=int, default=5, help="replications per instance")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    header = " | ".join(f"On time δ={d}" for d in DELTAS)
    print(f"| Set | Scenario | Runs | Realised / planned | {header} | Truncated | Absent |")
    print("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    notes = []
    for set_name in ("j30", "j60"):
        lines = calibrate(set_name, args.per_set, args.seeds, args.root)
        print("\n".join(lines[:-1]))
        notes.append(lines[-1])
    print()
    print("\n".join(notes))


if __name__ == "__main__":
    main()
