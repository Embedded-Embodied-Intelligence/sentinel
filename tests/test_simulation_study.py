"""Scenario study runner, its config and its summaries (WP2b)."""

import csv
import gzip
import json
from pathlib import Path

import pytest

from sentinel.experiments import runs
from sentinel.experiments import simulation_study as study
from sentinel.experiments import simulation_summary as summary
from sentinel.experiments.simulation_config import DURATIONS_ONLY, StudyConfig
from sentinel.simulation.baselines import CpsatDet
from sentinel.simulation.uncertainty import PertParams

REPO_ROOT = Path(__file__).resolve().parents[1]


def load(path: Path) -> StudyConfig:
    return StudyConfig.model_validate(runs.load_toml(path))


def test_wp2_config_matches_the_work_package() -> None:
    config = load(REPO_ROOT / "configs" / "wp2_noreaction.toml")
    assert [(s.name, s.reference) for s in config.sets] == [("j30", "opt"), ("j60", "hrs")]
    assert config.baseline_method == CpsatDet(
        deterministic_time_limit=config.baselines.cpsat_det.deterministic_time_limit,
        random_seed=config.baselines.cpsat_det.random_seed,
    )
    assert (config.replications, config.deltas, config.beta) == (20, (0.1, 0.2, 0.3), 0.10)
    assert config.pert == PertParams()
    grid = config.scenarios
    assert (grid.lambda_s, grid.lambda_n) == (0.01, 0.02)
    assert [s.name for s in grid.expand()] == [
        DURATIONS_ONLY,
        "la0_L3",
        "la0.0025_L3",
        "la0.0025_L5",
        "la0.005_L3",
        "la0.005_L5",
        "la0.01_L3",
        "la0.01_L5",
        "la0.02_L3",
        "la0.02_L5",
    ]


def test_scenario_grid_expansion(fake_study: Path) -> None:
    scenarios = load(fake_study).scenarios.expand()
    assert [(s.name, s.lambda_a, s.mean_absence) for s in scenarios] == [
        (DURATIONS_ONLY, 0.0, None),
        ("la0_L3", 0.0, 3),
        ("la0.05_L3", 0.05, 3),
        ("la0.05_L5", 0.05, 5),
    ]
    off = scenarios[0].disruptions
    assert (off.lambda_a, off.lambda_s, off.lambda_n) == (0, 0, 0)
    on = scenarios[3].disruptions
    assert (on.lambda_a, on.mean_absence, on.lambda_s, on.lambda_n) == (0.05, 5, 0.05, 0.05)


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("deltas", [0.3, 0.1], "ascending"),
        ("deltas", [0.1, 0.1], "ascending"),
        ("deltas", [-0.1, 0.1], "non-negative"),
        ("baseline", "rbrs", "baseline"),
    ],
)
def test_config_rejects_invalid_values(
    fake_study: Path, key: str, value: object, message: str
) -> None:
    raw = runs.load_toml(fake_study) | {key: value}
    with pytest.raises(ValueError, match=message):
        StudyConfig.model_validate(raw)


def test_smoke_run_writes_all_outputs(fake_study: Path, tmp_path: Path) -> None:
    out = tmp_path / "results"
    assert study.main(["--config", str(fake_study), "--out", str(out), "--limit", "2"]) == 0
    (run_dir,) = out.iterdir()
    assert run_dir.name.endswith("-smoke")
    assert {p.name for p in run_dir.iterdir()} == {
        "manifest.json",
        "results.csv",
        "summary.md",
        "table_wp2.tex",
        "fig_wp2_ontime.pdf",
        "fig_wp2_ontime.png",
    }

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    required = {
        "run_id", "command", "config_path", "config", "config_hash", "limit", "git_commit",
        "git_dirty", "start_utc", "end_utc", "duration_s", "python", "packages", "cpu",
        "cpu_count", "hostname", "n_rows", "seeds", "smoke", "baselines", "results_file",
        "simulations_per_s",
    }  # fmt: skip
    assert required <= manifest.keys()
    assert manifest["status"] == "completed"
    assert (manifest["smoke"], manifest["limit"], manifest["n_rows"]) == (True, 2, 16)
    assert manifest["config_hash"] == runs.config_hash(runs.load_toml(fake_study), 2)
    assert manifest["baselines"]["computed_in_run"] == 2
    assert manifest["baselines"]["statuses"] == {"OPTIMAL": 2}
    seeds = manifest["seeds"]["per_instance"]
    assert set(seeds) == {"tiny/tiny1_1", "tiny/tiny1_2"}

    with (run_dir / "results.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert tuple(reader.fieldnames or ()) == study.columns((0.1, 0.2, 0.3))
        rows = list(reader)
    scenarios = [DURATIONS_ONLY, "la0_L3", "la0.05_L3", "la0.05_L5"]
    assert [(r["instance"], r["scenario"], r["replication"]) for r in rows] == [
        (stem, scenario, str(replication))
        for stem in ("tiny1_1", "tiny1_2")
        for scenario in scenarios
        for replication in range(2)
    ]
    for row in rows:  # common random numbers: one seed per (instance, replication)
        assert int(row["seed"]) == seeds[f"tiny/{row['instance']}"][int(row["replication"])]
        assert (row["baseline_makespan"], row["c_star"]) == ("7", "7")
        met = [row[f"met_{delta}"] == "True" for delta in ("0.1", "0.2", "0.3")]
        assert met == sorted(met)  # a larger slack is met whenever a smaller one is
        assert float(row["ratio_c_star"]) == pytest.approx(int(row["makespan"]) / 7, abs=1e-6)
    quiet = [r for r in rows if r["scenario"] == DURATIONS_ONLY]
    assert all(r[f"n_{kind}"] == "0" for r in quiet for kind in study.EVENT_KINDS)

    table = (run_dir / "table_wp2.tex").read_text(encoding="utf-8")
    assert r"\toprule" in table and "durations only" in table
    assert "## TINY" in (run_dir / "summary.md").read_text(encoding="utf-8")


def test_replications_override_counts_as_smoke(fake_study: Path, tmp_path: Path) -> None:
    out = tmp_path / "results"
    argv = ["--config", str(fake_study), "--out", str(out), "--replications", "1"]
    assert study.main(argv) == 0
    (run_dir,) = out.iterdir()
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert (manifest["smoke"], manifest["overrides"], manifest["n_rows"]) == (
        True,
        {"replications": 1},
        8,
    )
    assert manifest["config"]["replications"] == 1


def test_durations_only_with_unit_multipliers_reproduces_the_baseline(fake_study: Path) -> None:
    raw = runs.load_toml(fake_study) | {"pert": {"a": 1.0, "m": 1.0, "b": 1.0}}
    config = StudyConfig.model_validate(raw)
    tasks, _ = study.build_tasks(config, None)
    for task in tasks:
        outcome = study.run_instance(task)
        quiet = [r for r in outcome.rows if r["scenario"] == DURATIONS_ONLY]
        assert len(quiet) == config.replications
        assert {(r["makespan"], r["baseline_makespan"]) for r in quiet} == {(7, 7)}
        assert all(r["met_0.1"] and r["n_epochs"] > 0 for r in quiet)


def test_invalid_realised_schedule_aborts(
    fake_study: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_: object) -> list[str]:
        return ["worker 0 works on two activities on day 1"]

    monkeypatch.setattr(study, "execution_violations", broken)
    config = load(fake_study)
    tasks, _ = study.build_tasks(config, 1)
    with pytest.raises(study.InvalidScheduleError, match="two activities"):
        study.run_instance(tasks[0])


def test_large_results_are_gzipped(
    tmp_path: Path, fake_study: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = load(fake_study)
    tasks, _ = study.build_tasks(config, 1)
    rows = study.run_instance(tasks[0]).rows
    monkeypatch.setattr(study, "PLAIN_CSV_LIMIT_BYTES", 100)
    name = study.write_results(tmp_path, rows, study.columns(config.deltas))
    assert name == "results.csv.gz" and not (tmp_path / "results.csv").exists()
    with gzip.open(tmp_path / name, "rt", encoding="utf-8") as handle:
        assert handle.readline().startswith("set,instance,scenario,replication,seed,")
    parsed = summary.read_results(tmp_path / name, config.deltas)
    assert [r.scenario for r in parsed] == [r["scenario"] for r in rows]


def test_baselines_are_cached_between_runs(fake_study: Path) -> None:
    config = load(fake_study)
    tasks, _ = study.build_tasks(config, None)
    assert study.missing_baselines(config, tasks) == ["tiny/tiny1_1", "tiny/tiny1_2"]
    assert not study.run_instance(tasks[0]).baseline.cached
    assert study.run_instance(tasks[0]).baseline.cached
    assert study.missing_baselines(config, tasks) == ["tiny/tiny1_2"]


@pytest.mark.parametrize(
    ("successes", "n", "expected"),
    [(0, 10, (0.0, 0.2775)), (5, 10, (0.2366, 0.7634)), (10, 10, (0.7225, 1.0))],
)
def test_wilson_interval(successes: int, n: int, expected: tuple[float, float]) -> None:
    low, high = summary.wilson_interval(successes, n)
    assert (low, high) == pytest.approx(expected, abs=1e-4)


def test_summaries_can_be_regenerated(fake_study: Path, tmp_path: Path) -> None:
    out = tmp_path / "results"
    assert study.main(["--config", str(fake_study), "--out", str(out), "--limit", "1"]) == 0
    (run_dir,) = out.iterdir()
    before = {p.name: p.read_bytes() for p in run_dir.iterdir()}
    assert summary.main([str(run_dir)]) == 0
    after = {p.name: p.read_bytes() for p in run_dir.iterdir()}
    assert after == before
