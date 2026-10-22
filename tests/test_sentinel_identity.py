"""Regression: Sentinel with full autonomy (Lambda = 3, so no permission gate) runs bit for bit
as before WP5b.1, which changed only what happens to actions that need approval (spec v1.8.1
sections 4 and 6) and the optional activities of DESCOPE.

`tests/fixtures/sentinel_identity.json` holds, for three seeds on a synthetic instance (with a
smaller rollout budget) and on the PSPLIB instance j301_1 (the WP2b seeds of replications 0-2
at lambda_A = 0.02, D for delta_D = 0.2, B with beta = 0.1 and (N_1, N) = (25, 100), as in the
RQ4 study), the SHA-256 of the run's result, of Sentinel's decision records (without wall
times) and of its counts. It was written with the code of commit fee0ce1 (spec v1.8), before
WP5b.1. Regenerate it only for an intended change of Sentinel's behaviour at Lambda = 3:
`uv run python tests/test_sentinel_identity.py`.
"""

import dataclasses
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from sentinel.agent.params import SentinelParams
from sentinel.data.psplib_loader import instance_path, load_psplib
from sentinel.data.reference import load_reference
from sentinel.experiments.policy_runs import check_run
from sentinel.experiments.runs import derive_seed
from sentinel.model import Activity, ProjectInstance, Role, Schedule, make_workers
from sentinel.policies.sentinel import Sentinel
from sentinel.scheduling.priority_rules import lft_priorities
from sentinel.scheduling.sgs import serial_sgs
from sentinel.simulation.engine import simulate
from sentinel.simulation.events import DisruptionParams
from sentinel.simulation.uncertainty import PertParams, derive_budget, derive_deadline

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sentinel_identity.json"
DATA_ROOT = Path(__file__).resolve().parents[1] / "data" / "psplib"
PERT = PertParams()
FULL = SentinelParams(autonomy=3)  # spec section 8 otherwise: (N_1, N) = (25, 100)
QUICK = SentinelParams(autonomy=3, n_stage1=10, n_rollouts=40)  # racing on fewer rollouts
SYNTHETIC = DisruptionParams(lambda_a=0.03, mean_absence=3, lambda_s=0.02, lambda_n=0.03)
PRIMARY = DisruptionParams(lambda_a=0.02, mean_absence=3, lambda_s=0.01, lambda_n=0.02)
# Fields of the decision records and their candidates as of spec v1.8, wall times left out.
RECORD_FIELDS = {
    "day",
    "deliberated",
    "rule",
    "reason",
    "chosen",
    "decision",
    "runner_up",
    "gate",
    "approval_day",
    "discarded",
    "needs",
    "candidates",
    "tied",
    "rollouts",
    "cp_solves",
    "cp_fallbacks",
}
CANDIDATE_FIELDS = {
    "label",
    "kind",
    "level",
    "delay",
    "deviation",
    "substituted",
    "scope_loss",
    "rollouts",
    "p_on_time",
    "capped",
    "tardiness",
    "mean_cost",
    "overrun",
    "utility",
    "dropped",
    "decision",
    "eliminated",
}
STATS_FIELDS = (
    "decisions",
    "reseqs",
    "fallbacks",
    "deterministic_time",
    "deliberations",
    "gate_exits",
    "skipped",
    "candidates",
    "rollouts",
    "deferrals",
    "escalations",
    "approvals_applied",
    "approvals_discarded",
    "chosen",
    "reasons",
)


def _synthetic() -> ProjectInstance:
    """16 real activities with up to two later successors each on two roles of 5 and 10."""
    rng = np.random.default_rng(51)
    n, capacities = 16, (5, 10)
    successors: list[set[int]] = [set() for _ in range(n + 2)]
    for j in range(1, n):
        later = np.arange(j + 1, n + 1)
        successors[j].update(rng.choice(later, size=min(2, later.size), replace=False).tolist())
    has_predecessor = set().union(*successors)
    successors[0] = {j for j in range(1, n + 1) if j not in has_predecessor}
    for j in range(1, n + 1):
        successors[j] = successors[j] or {n + 1}
    durations = [0, *rng.integers(1, 8, size=n).tolist(), 0]
    demands = [[0, 0], *([int(rng.integers(0, c // 2 + 1)) for c in capacities] for _ in range(n))]
    roles = tuple(Role(id=k, name=f"R{k + 1}", capacity=c) for k, c in enumerate(capacities))
    activities = tuple(
        Activity(id=j, duration=p, demands=tuple(r), successors=tuple(sorted(s)))
        for j, (p, r, s) in enumerate(zip(durations, [*demands, [0, 0]], successors, strict=True))
    )
    return ProjectInstance(
        name="synthetic", activities=activities, roles=roles, workers=make_workers(roles)
    )


Setup = tuple[ProjectInstance, Schedule, DisruptionParams, int, list[int], SentinelParams]


def _setup(case: str) -> Setup:
    """Instance, plan (serial SGS with LFT), scenario, deadline, the three seeds and Sentinel's
    parameters of a case: the synthetic one with a smaller rollout budget, to stay quick."""
    if case == "synthetic":
        instance = _synthetic()
        plan = serial_sgs(instance, lft_priorities(instance), lower_is_better=True)
        deadline = math.ceil(1.15 * plan.makespan(instance))
        return instance, plan, SYNTHETIC, deadline, [11, 12, 13], QUICK
    instance = load_psplib(instance_path("j30", case, DATA_ROOT))
    plan = serial_sgs(instance, lft_priorities(instance), lower_is_better=True)
    c_star = load_reference("j30", "opt", DATA_ROOT)[f"j30/{case}"]
    seeds = [derive_seed(2026, "j30", case, str(r)) for r in range(3)]
    return instance, plan, PRIMARY, derive_deadline(c_star, 0.2), seeds, FULL


def _digest(data: Any) -> str:
    text = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _run(case: str) -> list[dict[str, Any]]:
    """Digests of the case's three checked runs of Sentinel with Lambda = 3."""
    instance, plan, disruptions, deadline, seeds, params = _setup(case)
    budget = derive_budget(instance, 0.1, params=PERT)
    outcomes = []
    for seed in seeds:
        policy = Sentinel(params, seed=seed)
        result = simulate(
            instance,
            plan,
            policy,
            seed,
            pert=PERT,
            disruptions=disruptions,
            deadline=deadline,
            debug=True,
            budget=budget,
        )
        check_run(instance, result, f"{case}, seed {seed}")
        fields = {**dict.fromkeys(RECORD_FIELDS, True), "candidates": {"__all__": CANDIDATE_FIELDS}}
        records = [r.model_dump(mode="json", include=fields) for r in policy.records]
        stats = dataclasses.asdict(policy.stats)
        outcomes.append(
            {
                "seed": seed,
                "result": _digest(result.model_dump(mode="json")),
                "records": _digest(records),
                "stats": _digest({key: stats[key] for key in STATS_FIELDS}),
                "makespan": result.makespan,
                "deliberations": policy.stats.deliberations,
                "rollouts": policy.stats.rollouts,
            }
        )
    return outcomes


def _expected(case: str) -> list[dict[str, Any]]:
    data: dict[str, Any] = json.loads(FIXTURE.read_text())
    outcomes: list[dict[str, Any]] = data["cases"][case]
    return outcomes


def test_full_autonomy_runs_are_unchanged_on_a_synthetic_instance() -> None:
    """Three seeds on the synthetic instance: result, decision records and counts unchanged."""
    assert _run("synthetic") == _expected("synthetic")


@pytest.mark.data
@pytest.mark.slow
def test_full_autonomy_runs_are_unchanged_on_j30(psplib_root: Path) -> None:
    """Three WP2b seeds of j301_1 at lambda_A = 0.02: result, records and counts unchanged."""
    assert _run("j301_1") == _expected("j301_1")


def _write() -> None:
    """Write the fixture with the current code (see the module docstring)."""
    cases = {case: _run(case) for case in ("synthetic", "j301_1")}
    data = {"written_with": "commit fee0ce1 (spec v1.8, before WP5b.1)", "cases": cases}
    FIXTURE.write_text(json.dumps(data, indent=1) + "\n")
    for case, outcomes in cases.items():
        print(case, [(o["makespan"], o["deliberations"], o["rollouts"]) for o in outcomes])


if __name__ == "__main__":
    _write()
