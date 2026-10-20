"""Baseline plans and the study runner on downloaded PSPLIB data; skipped without data/psplib."""

from pathlib import Path

import pytest

from sentinel.data.psplib_loader import instance_path, list_instances, load_psplib
from sentinel.experiments import runs
from sentinel.experiments import simulation_study as study
from sentinel.experiments.simulation_config import DURATIONS_ONLY, StudyConfig
from sentinel.policies.no_reaction import NoReaction
from sentinel.simulation.baselines import CpsatDet, SgsLft, baseline_plan
from sentinel.simulation.engine import simulate
from sentinel.simulation.events import DisruptionParams
from sentinel.simulation.uncertainty import PertParams

pytestmark = pytest.mark.data

REPO_ROOT = Path(__file__).resolve().parents[1]
UNIT = PertParams(a=1.0, m=1.0, b=1.0)  # X = 1: true durations equal nominal ones


def _sets(psplib_root: Path) -> list[str]:
    sets = [s for s in ("j30", "j60") if (psplib_root / s).is_dir()]
    if not sets:
        pytest.skip("J30/J60 instances missing; run scripts/fetch_psplib.py")
    return sets


# A short limit keeps the test fast and leaves non-optimal (FEASIBLE) CP-SAT plans among them.
@pytest.mark.parametrize(
    "method", [CpsatDet(deterministic_time_limit=0.5, random_seed=2026), SgsLft()]
)
def test_exact_durations_reproduce_the_baseline_makespan(
    psplib_root: Path, tmp_path: Path, method: CpsatDet | SgsLft
) -> None:
    statuses = set()
    for set_name in _sets(psplib_root):
        for stem in list_instances(set_name, psplib_root)[::96]:  # 5 instances per set
            inst = load_psplib(instance_path(set_name, stem, psplib_root))
            plan = baseline_plan(inst, method, tmp_path)
            statuses.add(plan.status)
            result = simulate(
                inst, plan.schedule, NoReaction(), 1, pert=UNIT, disruptions=DisruptionParams.none()
            )
            assert result.makespan == plan.makespan, (inst.name, method.kind)
            assert result.starts[: inst.n_activities] == plan.schedule.starts, inst.name
    assert statuses == ({"OPTIMAL", "FEASIBLE"} if isinstance(method, CpsatDet) else {"FEASIBLE"})


def test_study_tasks_on_j30(psplib_root: Path, tmp_path: Path) -> None:
    raw = runs.load_toml(REPO_ROOT / "configs" / "wp2_noreaction.toml")
    raw |= {"data_root": str(psplib_root), "baseline_cache": str(tmp_path), "replications": 2}
    raw |= {"sets": [{"name": "j30", "reference": "opt"}]}
    config = StudyConfig.model_validate(raw)
    _sets(psplib_root)
    tasks, seeds = study.build_tasks(config, 2)
    assert [t.instance for t in tasks] == ["j301_1", "j301_2"]
    assert seeds["j30/j301_1"] == [runs.derive_seed(2026, "j30", "j301_1", str(r)) for r in (0, 1)]
    outcome = study.run_instance(tasks[0])
    assert len(outcome.rows) == 10 * 2
    assert outcome.baseline.makespan == tasks[0].c_star == 43  # j301_1 is solved to optimality
    assert all(r["baseline_makespan"] == 43 and not r["truncated"] for r in outcome.rows)
    quiet = [r for r in outcome.rows if r["scenario"] == DURATIONS_ONLY]
    assert all(r["n_absence"] == r["n_work_increase"] == r["n_new_activity"] == 0 for r in quiet)
    heavy = [r for r in outcome.rows if r["scenario"] == "la0.02_L5"]
    assert all(r["n_absence"] > 0 for r in heavy)
