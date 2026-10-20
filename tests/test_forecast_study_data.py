"""The forecast study on PSPLIB instances: its worlds are the WP2b runs (needs downloaded data)."""

from pathlib import Path

import pytest

from sentinel.experiments import forecast_study as study
from sentinel.experiments import forecast_summary as summary
from sentinel.experiments import runs
from sentinel.experiments.forecast_config import ForecastStudyConfig

pytestmark = pytest.mark.data

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_worlds_reproduce_the_wp2b_makespans(psplib_root: Path, tmp_path: Path) -> None:
    """Replications 0-1 of j301_1 and j601_1 in all four scenarios have the WP2b seeds and
    makespans (committed WP2b results); forecasts use 10 rollouts to keep the test short."""
    raw = runs.load_toml(REPO_ROOT / "configs" / "wp3_calibration.toml")
    wp2b = REPO_ROOT / raw["wp2b_results"]
    if not wp2b.is_file():
        pytest.skip(f"{wp2b} not found")
    raw |= {
        "replications": 2,
        "data_root": str(psplib_root),
        "baseline_cache": str(REPO_ROOT / raw["baseline_cache"]),
        "wp2b_results": str(wp2b),
    }
    for spec in raw["forecasters"]:
        if spec["kind"] == "monte_carlo":
            spec["n_rollouts"] = 10
    config = ForecastStudyConfig.model_validate(raw)
    tasks, _ = study.build_tasks(config, 1)
    assert [t.instance for t in tasks] == ["j301_1", "j601_1"]
    rows = [row for task in tasks for row in study.run_instance(task).rows]
    assert len(rows) == 2 * 4 * 2 * 5 * 3
    name = study.write_forecasts(tmp_path, rows, study.columns(config.deltas))
    check = summary.wp2b_check(summary.read_forecasts(tmp_path / name), config.wp2b_results)
    assert check.available and check.checked == 16 and check.missing == 0
    assert (check.makespan_mismatches, check.seed_mismatches) == (0, 0)
