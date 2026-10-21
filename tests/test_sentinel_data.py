"""Sentinel on PSPLIB J30 (data, slow): checked runs of the full variant (spec sections 5-6)."""

import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pytest

from sentinel.data.psplib_loader import list_instances
from sentinel.data.reference import load_reference
from sentinel.experiments.policy_runs import PolicyTask, run_policies
from sentinel.experiments.runs import derive_seed
from sentinel.policies.sentinel import SentinelStats
from sentinel.simulation.events import DisruptionParams

pytestmark = [pytest.mark.data, pytest.mark.slow]

# The primary scenario at lambda_A = 0.01 (docs/experiments/plan.md).
SCENARIO = DisruptionParams(lambda_a=0.01, mean_absence=3, lambda_s=0.01, lambda_n=0.02)


def test_sentinel_runs_on_j30_are_feasible(psplib_root: Path) -> None:
    """Five spread J30 instances x two WP2b seeds with Sentinel `full` (spec section 8
    parameters) and NoReaction on the same worlds: every run passes the feasibility checks in
    debug mode (`run_checked`), the engine rejects none of Sentinel's actions, and every
    epoch is either a deliberation or skipped."""
    references = load_reference("j30", "opt", psplib_root)
    stems = list_instances("j30", psplib_root)[::96][:5]
    tasks = [
        PolicyTask(
            set_name="j30",
            stem=stem,
            c_star=references[f"j30/{stem}"],
            policies=("no_reaction", "sentinel_full"),
            seeds=tuple(derive_seed(2026, "j30", stem, str(r)) for r in range(2)),
            disruptions=SCENARIO,
            data_root=psplib_root,
        )
        for stem in stems
    ]
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=4, mp_context=context) as pool:
        records = [record for done in pool.map(run_policies, tasks) for record in done]
    sentinel = [r for r in records if r.policy == "sentinel_full"]
    assert len(sentinel) == 10 and len(records) == 20
    for record in sentinel:
        stats = record.stats
        assert isinstance(stats, SentinelStats)
        assert record.rejected == 0 and stats.fallbacks == 0
        assert stats.deliberations + stats.skipped == stats.decisions == record.epochs
        assert stats.deliberations > 0 and len(stats.deliberation_s) == stats.deliberations
        assert sum(stats.chosen.values()) == stats.deliberations - stats.gate_exits
    times = [t for r in sentinel for t in r.stats.deliberation_s]  # type: ignore[attr-defined]
    on_time = {
        p: sum(r.on_time[0] for r in records if r.policy == p)
        for p in ("sentinel_full", "no_reaction")
    }
    print(f"\n{len(times)} deliberations, mean {sum(times) / len(times):.3f} s; on time {on_time}")
