"""The reactive policies and the residual solvers on PSPLIB J30 and J60 (needs downloaded data)."""

import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pytest

from sentinel.data.psplib_loader import instance_path, list_instances, load_psplib
from sentinel.data.reference import load_reference
from sentinel.experiments.policy_runs import WP2B_BASELINE, PolicyTask, run_policies
from sentinel.experiments.runs import derive_seed
from sentinel.policies.no_reaction import NoReaction
from sentinel.policies.resolve import T_CP
from sentinel.scheduling.cpsat import solve_residual
from sentinel.scheduling.residual import planning_view, residual_sgs, validate_residual
from sentinel.simulation.baselines import cached_baseline
from sentinel.simulation.engine import simulate
from sentinel.simulation.events import DisruptionParams
from sentinel.simulation.uncertainty import PertParams, derive_deadline

pytestmark = pytest.mark.data

REPO_ROOT = Path(__file__).resolve().parents[1]
CACHE = REPO_ROOT / "data" / "derived" / "baselines"
PRIMARY = DisruptionParams(lambda_a=0.01, mean_absence=3, lambda_s=0.01, lambda_n=0.02)
REACTIVE = ("always_substitute", "full_resolve", "full_resolve_subst", "stable_resolve_subst")
# CP-SAT limit of the policies in this test. At T_cp = 0.5 a search on a hard J60 view runs for
# about 2.4 s, so one run takes minutes; the checks do not depend on the limit, and runs at
# T_cp = 0.5 are checked the same way by scripts/bench_policies.py.
TEST_LIMIT = 0.01


def tasks(root: Path, set_name: str, reference: str, count: int) -> list[PolicyTask]:
    """`count` instances spread over the set (every 480 / count-th), three WP2b seeds each."""
    references = load_reference(set_name, reference, root)  # type: ignore[arg-type]
    stems = list_instances(set_name, root)[:: 480 // count][:count]
    return [
        PolicyTask(
            set_name=set_name,
            stem=stem,
            c_star=references[f"{set_name}/{stem}"],
            policies=REACTIVE,
            seeds=tuple(derive_seed(2026, set_name, stem, str(r)) for r in range(3)),
            disruptions=PRIMARY,
            deterministic_time_limit=TEST_LIMIT,
            data_root=root,
            baseline_cache=CACHE,
        )
        for stem in stems
    ]


@pytest.mark.slow
def test_reactive_policies_keep_every_realised_schedule_feasible(psplib_root: Path) -> None:
    """20 J30 + 10 J60 instances x 3 seeds x the four reactive policies at lambda_A = 0.01 (CP-SAT
    limit TEST_LIMIT): in debug mode every RESEQ plan passes validate_residual, every realised
    schedule passes the checks of spec 1.3, 3.1 and 4 (`run_policies` raises otherwise), and
    nothing is rejected."""
    work = tasks(psplib_root, "j30", "opt", 20) + tasks(psplib_root, "j60", "hrs", 10)
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=4, mp_context=context) as pool:
        records = [record for done in pool.map(run_policies, work) for record in done]
    assert len(records) == (20 + 10) * 3 * 4
    assert all(record.rejected == 0 and not record.truncated for record in records)
    for name in REACTIVE:
        mine = [record for record in records if record.policy == name]
        if name.endswith("subst") or name == "always_substitute":
            assert sum(record.substituted for record in mine) > 0, name
        if "resolve" in name:
            assert sum(record.reseqs for record in mine) > 0, name


def test_residual_plans_are_feasible_on_j30_planning_views(psplib_root: Path) -> None:
    """At least 50 planning views of NoReaction J30 runs: the residual SGS and both CP-SAT
    objectives at the policies' limit T_cp give feasible plans and CP-SAT is never longer than
    the SGS."""
    references = load_reference("j30", "opt", psplib_root)
    found = 0
    for stem in list_instances("j30", psplib_root)[::40]:
        instance = load_psplib(instance_path("j30", stem, psplib_root))
        plan = cached_baseline(instance, WP2B_BASELINE, CACHE)[0]
        deadline = derive_deadline(references[instance.name], 0.3)
        days = [int(f * plan.makespan) for f in (0.0, 0.2, 0.4, 0.6, 0.8)]
        seed = derive_seed(2026, "j30", stem, "0")
        result = simulate(
            instance,
            plan.schedule,
            NoReaction(),
            seed,
            pert=PertParams(),
            disruptions=PRIMARY,
            deadline=deadline,
            observe_days=days,
        )
        for observation in result.observations:
            view = planning_view(observation)
            sgs = residual_sgs(view)
            assert validate_residual(view, sgs) == []
            hint = view.planned_starts()
            for objective in ("makespan", "stable"):
                solution = solve_residual(
                    view, objective, deterministic_time_limit=T_CP, seed=0, hint=hint
                )
                assert validate_residual(view, solution.starts) == []
                assert solution.makespan <= sgs[view.sink]
            found += 1
    assert found >= 50
