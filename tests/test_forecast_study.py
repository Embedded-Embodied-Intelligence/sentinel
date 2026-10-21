"""Forecast study runner, its configs and its summaries (WP3b, spec section 5.2)."""

import csv
import gzip
import hashlib
import io
import json
import math
import re
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from sentinel import cli
from sentinel.experiments import forecast_study as study
from sentinel.experiments import forecast_summary as summary
from sentinel.experiments import runs, simulation_study
from sentinel.experiments.forecast_config import ForecasterSpec, ForecastStudyConfig
from sentinel.experiments.simulation_config import StudyConfig
from sentinel.model import Schedule
from sentinel.simulation.events import DisruptionParams
from sentinel.simulation.state import Observation
from sentinel.simulation.uncertainty import PertParams

REPO_ROOT = Path(__file__).resolve().parents[1]

FAKE_FORECAST_CONFIG = """
name = "fake_wp3"
base_seed = 11
max_workers = 2
data_root = "{root}"
baseline_cache = "{cache}"
replications = 2
deltas = [0.2, 0.3]
checkpoints = [0.0, 0.4, 0.8]
baseline = "cpsat_det"
wp2b_results = "{wp2b}"

[baselines.cpsat_det]
deterministic_time_limit = 1.0
random_seed = 5

[scenarios]
lambda_a = [0.0, 0.05]
mean_absence = [3]
lambda_s = 0.05
lambda_n = 0.05
durations_only = false

[[sets]]
name = "tiny"
reference = "opt"

[[forecasters]]
name = "mc_full"
kind = "monte_carlo"
n_rollouts = 20

[[forecasters]]
name = "mc_no_future"
kind = "monte_carlo"
n_rollouts = 20
future_disruptions = false

[[forecasters]]
name = "deterministic"
kind = "deterministic"

[summary]
bootstrap_resamples = 50
differences = [["mc_full", "deterministic"], ["mc_full", "mc_no_future"]]
reliability_checkpoints = [0.0, 0.4]
"""

OUTPUTS = {
    "manifest.json",
    "forecasts.csv.gz",
    "summary.md",
    "table_wp3_calibration.tex",
    "table_wp3_warning.tex",
    "table_wp3_calibration_delta0.3.tex",
    "table_wp3_warning_delta0.3.tex",
    "table_wp3_plan_stage.tex",
    "table_wp3_plan_stage_delta0.3.tex",
    "table_wp3_headline.tex",
    "table_wp3_headline_delta0.3.tex",
    "summary_manifest.json",
    "fig_wp3_reliability.pdf",
    "fig_wp3_reliability.png",
    "fig_wp3_brier.pdf",
    "fig_wp3_brier.png",
    "fig_wp3_pit.pdf",
    "fig_wp3_pit.png",
}


def load(path: Path) -> ForecastStudyConfig:
    return ForecastStudyConfig.model_validate(runs.load_toml(path))


def write_config(path: Path, fake_study: Path, wp2b: Path) -> Path:
    """Forecast study config on the same tiny set, data and cache as `fake_study`."""
    wp2 = StudyConfig.model_validate(runs.load_toml(fake_study))
    text = FAKE_FORECAST_CONFIG.format(
        root=wp2.data_root.as_posix(), cache=wp2.baseline_cache.as_posix(), wp2b=wp2b.as_posix()
    )
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def fake_forecasts(fake_study: Path, tmp_path: Path) -> Path:
    """The config without WP2b results, so its seed check reports that it was not run."""
    return write_config(tmp_path / "fake_wp3.toml", fake_study, tmp_path / "no-wp2b.csv")


@pytest.fixture
def fake_wp2b(fake_study: Path, tmp_path: Path) -> Path:
    """The WP2b study on the tiny set (base seed 11, max_days of delta_D = 0.3); its results."""
    out = tmp_path / "wp2"
    assert simulation_study.main(["--config", str(fake_study), "--out", str(out)]) == 0
    (run_dir,) = out.iterdir()
    return run_dir / "results.csv"


def read_rows(run_dir: Path) -> list[dict[str, str]]:
    with gzip.open(run_dir / "forecasts.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_wp3_configs_match_the_work_package() -> None:
    main = load(REPO_ROOT / "configs" / "wp3_calibration.toml")
    wp2 = StudyConfig.model_validate(runs.load_toml(REPO_ROOT / "configs" / "wp2_noreaction.toml"))
    assert [(s.name, s.reference, s.stride) for s in main.sets] == [
        ("j30", "opt", 1),
        ("j60", "hrs", 1),
    ]
    assert (main.base_seed, main.replications, main.deltas) == (wp2.base_seed, 4, (0.2, 0.3))
    assert main.baseline_method == wp2.baseline_method and main.pert == wp2.pert == PertParams()
    assert main.review_period == wp2.review_period
    assert main.checkpoints == (0.0, 0.2, 0.4, 0.6, 0.8)
    assert [s.name for s in main.scenarios.expand()] == [
        "la0_L3",
        "la0.005_L3",
        "la0.01_L3",
        "la0.02_L3",
    ]
    assert (main.scenarios.lambda_s, main.scenarios.lambda_n) == (0.01, 0.02)
    assert [(f.name, f.kind) for f in main.forecasters] == [
        ("mc_full", "monte_carlo"),
        ("mc_no_future", "monte_carlo"),
        ("deterministic", "deterministic"),
    ]
    mc_full, mc_no_future, _ = main.forecasters
    assert (mc_full.future_disruptions, mc_no_future.future_disruptions) == (True, False)
    assert (mc_full.n_rollouts, mc_no_future.n_rollouts) == (200, 200)
    assert main.wp2b_results is not None and (REPO_ROOT / main.wp2b_results).is_file()
    settings = main.summary
    assert (settings.bins, settings.thresholds, settings.bootstrap_resamples) == (
        10,
        (0.5, 0.8),
        1000,
    )
    assert settings.differences == (("mc_full", "deterministic"), ("mc_full", "mc_no_future"))
    assert (settings.warning_from, settings.headline_checkpoints) == (0.2, (0.0, 0.4, 0.8))
    assert settings.reference_run is None and settings.headline_table == "table_wp3_headline"

    misspec = load(REPO_ROOT / "configs" / "wp3_misspec.toml")
    assert [(s.name, s.stride) for s in misspec.sets] == [("j30", 4)]
    assert misspec.replications == 4 and misspec.base_seed == wp2.base_seed
    (world,) = misspec.scenarios.expand()
    assert world.disruptions == DisruptionParams(
        lambda_a=0.01, mean_absence=3, lambda_s=0.01, lambda_n=0.02
    )
    assert [(f.name, f.prior_scale, f.prior_pert) for f in misspec.forecasters] == [
        ("mc_k0.5", 0.5, None),
        ("mc_k1", 1.0, None),
        ("mc_k2", 2.0, None),
        ("mc_pert_wide", 1.0, PertParams(a=0.7, m=1.0, b=2.0)),
    ]
    assert misspec.summary.table == "table_wp3_misspec"
    assert misspec.summary.headline_table == "table_wp3_misspec_headline"
    assert misspec.summary.reference_forecasters == ("mc_no_future", "deterministic")
    reference = misspec.summary.reference_run  # the main run: same seeds, same worlds
    assert reference is not None and (REPO_ROOT / reference / "forecasts.csv.gz").is_file()
    manifest = json.loads((REPO_ROOT / reference / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["config"]["name"] == "wp3_calibration" and not manifest["smoke"]


def test_checkpoint_days_and_seeds() -> None:
    assert [study.checkpoint_day(f, 45) for f in (0.0, 0.2, 0.4, 0.6, 0.8)] == [0, 9, 18, 27, 36]
    assert study.checkpoint_day(0.6, 5) == 3 and study.checkpoint_day(0.8, 43) == 34
    seed = study.forecast_seed(2026, "j30", "j301_1", "la0_L3", 0, 0.2)
    assert seed == study.forecast_seed(2026, "j30", "j301_1", "la0_L3", 0, 0.2)
    others = {
        study.forecast_seed(2026, "j30", "j301_1", "la0_L3", 0, 0.4),
        study.forecast_seed(2026, "j30", "j301_1", "la0.01_L3", 0, 0.2),
        study.forecast_seed(2026, "j30", "j301_1", "la0_L3", 1, 0.2),
        runs.derive_seed(2026, "j30", "j301_1", "0"),  # the world seed
    }
    assert seed not in others and len(others) == 4


def test_forecaster_priors() -> None:
    observation = Observation.model_construct(
        pert=PertParams(),
        disruptions=DisruptionParams(lambda_a=0.01, mean_absence=3, lambda_s=0.01, lambda_n=0.02),
    )
    assert ForecasterSpec(name="a", kind="monte_carlo").priors(observation) is None
    doubled = ForecasterSpec(name="b", kind="monte_carlo", prior_scale=2.0).priors(observation)
    assert doubled is not None and doubled.pert == PertParams()
    rates = doubled.disruptions
    assert (rates.lambda_a, rates.lambda_s, rates.lambda_n, rates.mean_absence) == pytest.approx(
        (0.02, 0.02, 0.04, 3)
    )
    wide = PertParams(a=0.7, m=1.0, b=2.0)
    widened = ForecasterSpec(name="c", kind="monte_carlo", prior_pert=wide).priors(observation)
    assert widened is not None and widened.pert == wide
    assert widened.disruptions == observation.disruptions
    with pytest.raises(ValueError):
        ForecasterSpec(name="d", kind="monte_carlo", prior_scale=200.0).priors(observation)
    with pytest.raises(ValueError, match="no priors"):
        ForecasterSpec(name="e", kind="deterministic", prior_scale=2.0)


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("checkpoints", [0.4, 0.0], "ascending"),
        ("checkpoints", [0.0, 1.0], "less than 1"),
        ("forecasters", [{"name": "a", "kind": "deterministic"}] * 2, "duplicate"),
        ("summary", {"differences": [["mc_full", "nope"]]}, "unknown forecasters"),
        ("summary", {"reliability_checkpoints": [0.5]}, "not checkpoints"),
        ("summary", {"headline_checkpoints": [0.5]}, "not checkpoints"),
        ("summary", {"reference_forecasters": ["deterministic"]}, "given together"),
        ("summary", {"reference_run": "x", "reference_forecasters": ["mc_full"]}, "of this run"),
        ("summary", {"warning_from": 1.0}, "less than 1"),
    ],
)
def test_config_rejects_invalid_values(
    fake_forecasts: Path, key: str, value: object, message: str
) -> None:
    raw = runs.load_toml(fake_forecasts) | {key: value}
    with pytest.raises(ValueError, match=message):
        ForecastStudyConfig.model_validate(raw)


def test_smoke_run_writes_all_outputs_and_reproduces_wp2b(
    fake_study: Path, fake_wp2b: Path, tmp_path: Path
) -> None:
    config = write_config(tmp_path / "with_wp2b.toml", fake_study, fake_wp2b)
    out = tmp_path / "results"
    assert study.main(["--config", str(config), "--out", str(out), "--limit", "2"]) == 0
    (run_dir,) = out.iterdir()
    assert run_dir.name.endswith("-smoke")
    assert {p.name for p in run_dir.iterdir()} == OUTPUTS

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    required = {
        "run_id", "command", "config_path", "config", "config_hash", "limit", "git_commit",
        "git_dirty", "start_utc", "end_utc", "duration_s", "python", "packages", "cpu",
        "cpu_count", "hostname", "n_rows", "seeds", "smoke", "baselines", "results_file",
        "forecaster_timing", "wp2b_check", "skipped_checkpoints", "outputs",
    }  # fmt: skip
    assert required <= manifest.keys()
    assert manifest["status"] == "completed"
    # 2 instances x 2 scenarios x 2 replications x 3 checkpoints x 3 forecasters
    assert (manifest["smoke"], manifest["limit"], manifest["n_rows"]) == (True, 2, 72)
    check = manifest["wp2b_check"]
    assert (check["worlds_checked"], check["makespan_mismatches"]) == (8, 0)
    assert (check["seed_mismatches"], check["missing"]) == (0, 0)
    assert "**0 makespan mismatches**" in (run_dir / "summary.md").read_text(encoding="utf-8")

    rows = read_rows(run_dir)
    with gzip.open(run_dir / "forecasts.csv.gz", "rt", encoding="utf-8") as handle:
        assert tuple(next(csv.reader(handle))) == study.columns((0.2, 0.3))
    seeds = manifest["seeds"]["per_instance"]
    by_checkpoint: dict[tuple[str, ...], set[str]] = {}
    for row in rows:
        key = (row["instance"], row["scenario"], row["replication"], row["f"])
        by_checkpoint.setdefault(key, set()).add(row["forecast_seed"])
        assert int(row["seed"]) == seeds[f"tiny/{row['instance']}"][int(row["replication"])]
        expected = study.forecast_seed(
            11, "tiny", row["instance"], row["scenario"], int(row["replication"]), float(row["f"])
        )
        assert int(row["forecast_seed"]) == expected
        assert int(row["checkpoint_day"]) == study.checkpoint_day(float(row["f"]), 7)
        if row["skipped"] == "True":
            assert int(row["makespan"]) <= int(row["checkpoint_day"])
            assert row["p_on_time_0.2"] == row["crps"] == ""
            continue
        assert 0 <= float(row["p_on_time_0.2"]) <= float(row["p_on_time_0.3"]) <= 1
        assert 0 <= float(row["pit_lower"]) <= float(row["pit_upper"]) <= 1
        quantiles = [int(row[c]) for c in summary.QUANTILE_COLUMNS]
        assert quantiles == sorted(quantiles)
        if row["forecaster"] == "deterministic":
            assert len(set(quantiles)) == 1 and float(row["p_on_time_0.2"]) in (0.0, 1.0)
            assert float(row["crps"]) == abs(quantiles[0] - int(row["makespan"]))
    assert all(len(s) == 1 for s in by_checkpoint.values())  # one seed for all forecasters
    assert len(by_checkpoint) == 24


def test_summaries_can_be_regenerated_through_the_cli(
    fake_forecasts: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "results"
    argv = ["--config", str(fake_forecasts), "--out", str(out), "--limit", "1"]
    assert study.main([*argv, "--replications", "1"]) == 0
    (run_dir,) = out.iterdir()
    stamped = summary.SUMMARY_MANIFEST_FILE  # records the time of generation
    before = {p.name: p.read_bytes() for p in run_dir.iterdir() if p.name != stamped}
    capsys.readouterr()
    assert cli.main(["summarise-forecasts", str(run_dir)]) == 0
    printed = capsys.readouterr().out
    assert "WP2b seed check: not run" in printed and "summary.md" in printed
    assert {p.name: p.read_bytes() for p in run_dir.iterdir() if p.name != stamped} == before
    record = json.loads((run_dir / stamped).read_text(encoding="utf-8"))
    # --replications 1 is in the manifest's config, not in the file: the manifest's settings.
    assert record["summary_settings_source"] == "manifest.json"
    assert [entry["path"] for entry in record["inputs"]] == ["forecasts.csv.gz", "manifest.json"]
    assert record["git_commit"] is None or len(record["git_commit"]) == 40
    assert cli.main(["summarise-forecasts", str(tmp_path / "missing")]) == 1


def test_runner_passes_only_the_observation_and_its_plan(
    fake_forecasts: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Forecasters see an Observation and a Schedule only; the realised makespan comes later."""
    seen: list[tuple[str, type, type]] = []
    real_forecast, real_deterministic = study.forecast, study.deterministic_forecast

    def spy_forecast(observation: Any, plan: Any, **kwargs: Any) -> Any:
        seen.append(("mc", type(observation), type(plan)))
        assert set(kwargs) == {"n_rollouts", "seed", "include_future_disruptions", "priors"}
        return real_forecast(observation, plan, **kwargs)

    def spy_deterministic(observation: Any, plan: Any, **kwargs: Any) -> Any:
        seen.append(("deterministic", type(observation), type(plan)))
        assert set(kwargs) == {"seed"}
        return real_deterministic(observation, plan, **kwargs)

    monkeypatch.setattr(study, "forecast", spy_forecast)
    monkeypatch.setattr(study, "deterministic_forecast", spy_deterministic)
    config = load(fake_forecasts)
    tasks, _ = study.build_tasks(config, 1)
    rows = study.run_instance(tasks[0]).rows
    forecasts = [r for r in rows if not r["skipped"]]
    assert len(seen) == len(forecasts) > 0
    assert {(o, p) for _, o, p in seen} == {(Observation, Schedule)}


def test_invalid_realised_schedule_aborts(
    fake_forecasts: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_: object) -> list[str]:
        return ["worker 0 works on two activities on day 1"]

    monkeypatch.setattr(simulation_study, "execution_violations", broken)
    tasks, _ = study.build_tasks(load(fake_forecasts), 1)
    with pytest.raises(simulation_study.InvalidScheduleError, match="two activities"):
        study.run_instance(tasks[0])


def test_stride_selects_every_kth_instance(fake_forecasts: Path) -> None:
    raw = runs.load_toml(fake_forecasts)
    raw["sets"] = [{"name": "tiny", "reference": "opt", "stride": 2}]
    tasks, seeds = study.build_tasks(ForecastStudyConfig.model_validate(raw), None)
    assert [t.instance for t in tasks] == ["tiny1_1"] and list(seeds) == ["tiny/tiny1_1"]


# --- Summaries of a tiny synthetic forecasts file -----------------------------------------------

SYNTHETIC_CONFIG = """
name = "synthetic"
base_seed = 1
max_workers = 1
data_root = "data/psplib"
baseline = "cpsat_det"
replications = 1
deltas = [0.2, 0.3]
checkpoints = [0.0, 0.4, 0.8]
wp2b_results = "{wp2b}"

[baselines.cpsat_det]
deterministic_time_limit = 1.0
random_seed = 1

[scenarios]
lambda_a = [0.0]
mean_absence = [3]
lambda_s = 0.01
lambda_n = 0.02
durations_only = false

[[sets]]
name = "tiny"
reference = "opt"

[[forecasters]]
name = "sharp"
kind = "monte_carlo"

[[forecasters]]
name = "vague"
kind = "monte_carlo"

[summary]
bootstrap_resamples = 20
differences = [["sharp", "vague"]]
reliability_checkpoints = [0.0, 0.4]
"""


def synthetic_rows(names: Sequence[str] = ("sharp", "vague")) -> list[dict[str, object]]:
    """C* = 10, C_plan = 10, D = 12 (delta 0.2) and 13 (0.3). Instance 1 finishes on day 8, on
    time, so its checkpoint f = 0.8 (day 8) is skipped; instance 2 finishes on day 14, late.
    `vague` says p = 0.5 with quantiles 8, 9, 10, 12, 14, 15, 16 and CRPS 1.5; every other
    forecaster, e.g. `sharp`, forecasts the outcome exactly (p = 1 or 0, every quantile = C)."""
    rows: list[dict[str, object]] = []
    for stem, makespan in (("tiny1_1", 8), ("tiny1_2", 14)):
        for f, day in ((0.0, 0), (0.4, 4), (0.8, 8)):
            for name in names:
                row: dict[str, object] = {
                    "set": "tiny",
                    "instance": stem,
                    "scenario": "la0_L3",
                    "lambda_a": 0.0,
                    "replication": 0,
                    "seed": 100 + makespan,
                    "forecast_seed": 7,
                    "f": f,
                    "checkpoint_day": day,
                    "skipped": makespan <= day,
                    "forecaster": name,
                    "c_plan": 10,
                    "c_star": 10,
                    "makespan": makespan,
                    "truncated": False,
                    "deadline_0.2": 12,
                    "deadline_0.3": 13,
                }
                if makespan > day:
                    sharp = name != "vague"
                    p = float(makespan <= 12) if sharp else 0.5
                    quantiles = [makespan] * 7 if sharp else [8, 9, 10, 12, 14, 15, 16]
                    row |= {
                        "p_on_time_0.2": p,
                        "p_on_time_0.3": p,
                        "mean": makespan if sharp else 12,
                        **dict(zip(summary.QUANTILE_COLUMNS, quantiles, strict=True)),
                        "pit_lower": 0.0 if sharp else 0.25,
                        "pit_upper": 1.0 if sharp else 0.5,
                        "crps": 0.0 if sharp else 1.5,
                        "fallbacks": 0,
                        "rollouts_truncated": 0,
                        "wall_s": 0.01,
                    }
                rows.append(row)
    return rows


def write_run(run_dir: Path, rows: list[dict[str, object]], config_text: str) -> Path:
    """A run directory with the forecasts file of `rows` and a manifest holding the config."""
    run_dir.mkdir()
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=study.columns((0.2, 0.3)), restval="")
    writer.writeheader()
    writer.writerows(rows)
    (run_dir / "forecasts.csv.gz").write_bytes(gzip.compress(buffer.getvalue().encode()))
    config = tomllib.loads(config_text)
    manifest = {"run_id": run_dir.name, "config": config, "results_file": "forecasts.csv.gz"}
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return run_dir


@pytest.fixture
def synthetic_run(tmp_path: Path) -> Path:
    wp2b = tmp_path / "wp2b.csv"  # instance 2's makespan differs from the synthetic world
    wp2b.write_text(
        "set,instance,scenario,replication,seed,makespan\n"
        "tiny,tiny1_1,la0_L3,0,108,8\ntiny,tiny1_2,la0_L3,0,114,15\n",
        encoding="utf-8",
    )
    config_text = SYNTHETIC_CONFIG.format(wp2b=wp2b.as_posix())
    return write_run(tmp_path / "synthetic", synthetic_rows(), config_text)


def test_summary_cli_on_a_tiny_synthetic_csv(
    synthetic_run: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["summarise-forecasts", str(synthetic_run)]) == 0
    printed = capsys.readouterr().out
    assert "2 worlds compared, **1 makespan mismatches**" in printed
    names = {p.name for p in synthetic_run.iterdir()}
    assert OUTPUTS - {"manifest.json", "forecasts.csv.gz"} <= names
    text = (synthetic_run / "summary.md").read_text(encoding="utf-8")
    assert "| all | sharp | 5 | 0.400 | 0.000 [0.000, 0.000] |" in text
    assert "| all | vague | 5 | 0.400 | 0.250 [0.250, 0.250] |" in text
    assert "| all | sharp - vague | -0.2500 [-0.2500, -0.2500] |" in text
    table = (synthetic_run / "table_wp3_calibration.tex").read_text(encoding="utf-8")
    assert r"\toprule" in table and r"sharp" in table


def test_synthetic_scores_by_hand(synthetic_run: Path) -> None:
    """Hand-computed cells: vague has one bin (p = 0.5, outcome frequency 2/5 = 0.4), so
    REL = 0.01, RES = 0, UNC = 0.24, ECE = 0.1; coverage 3/5 (instance 1 at C = 8 < q10 = 9).
    Early warning counts f >= 0.2: sharp warns instance 2 at f = 0.4, on day 4 (lead
    12 - 4 = 8 days); vague warns only at theta = 0.8, both instances on day 4."""
    manifest = json.loads((synthetic_run / "manifest.json").read_text(encoding="utf-8"))
    config = ForecastStudyConfig.model_validate(manifest["config"])
    table = summary.read_forecasts(synthetic_run / "forecasts.csv.gz")
    assert table.n_rows == 12 and int(table.flags["skipped"].sum()) == 2
    cells = summary.compute_cells(summary.Analysis(table, config), config)
    sharp, vague = cells.binary[(0, 0, 0, None, None)], cells.binary[(0, 0, 1, None, None)]
    assert (sharp.n, sharp.brier.value, sharp.ece.value) == (5, 0.0, 0.0)
    assert vague.brier.value == pytest.approx(0.25)
    assert vague.reliability.value == pytest.approx(0.01)
    assert vague.resolution.value == pytest.approx(0.0)
    assert vague.uncertainty == pytest.approx(0.24)
    assert vague.ece.value == pytest.approx(0.1)
    assert vague.binning_error == pytest.approx(0.0, abs=1e-12)
    assert cells.distribution[(0, 1, None, None)].coverage.value == pytest.approx(0.6)
    assert cells.distribution[(0, 1, None, None)].crps.value == pytest.approx(0.15)
    assert cells.distribution[(0, 0, None, None)].crps.value == 0.0
    assert cells.differences[(0, 0, 0, None, None)].brier.value == pytest.approx(-0.25)
    warned = cells.warnings[(0, 0, 0, 0.5, None)]
    assert (warned.late, warned.warned.value, warned.lead.value) == (1, 1.0, 8.0)
    assert (warned.on_time, warned.false_alarms.value) == (1, 0.0)
    calm = cells.warnings[(0, 0, 1, 0.5, None)]
    assert (calm.warned.value, calm.false_alarms.value) == (0.0, 0.0)
    alarmed = cells.warnings[(0, 0, 1, 0.8, None)]
    assert (alarmed.warned.value, alarmed.lead.value, alarmed.false_alarms.value) == (1, 8, 1)
    pit = cells.distribution[(0, 0, None, None)].pit  # sharp: (0, 1) pairs, uniform draws
    assert int(pit.sum()) == 5


def test_synthetic_skill_discrimination_coverage_and_plan_stage(synthetic_run: Path) -> None:
    """At f = 0 and f = 0.4 one of the two forecasts is on time, so vague (p = 0.5) is the
    base-rate forecaster of those cells: BSS 0. Pooled over checkpoints (base rate 0.4) its BSS
    is 1 - 0.25 / 0.24. Sharp separates on-time from late forecasts (AUC 1), vague only ties
    (AUC 0.5). Vague's PIT values lie in [0.25, 0.5], all inside [0.1, 0.9]. Plan stage (f = 0):
    sharp has p = 0 for the late run and p = 1 for the on-time run; vague has p = 0.5 < 0.8."""
    manifest = json.loads((synthetic_run / "manifest.json").read_text(encoding="utf-8"))
    config = ForecastStudyConfig.model_validate(manifest["config"])
    table = summary.read_forecasts(synthetic_run / "forecasts.csv.gz")
    cells = summary.compute_cells(summary.Analysis(table, config), config)
    sharp, vague = 0, 1
    for share in (0.0, 0.4):
        assert cells.binary[(0, 0, vague, share, None)].bss.value == pytest.approx(0, abs=1e-12)
        assert cells.binary[(0, 0, sharp, share, None)].bss.value == 1.0
        assert cells.binary[(0, 0, sharp, share, None)].auc.value == 1.0
        assert cells.binary[(0, 0, vague, share, None)].auc.value == 0.5
    late_only = cells.binary[(0, 0, vague, 0.8, None)]  # instance 1's f = 0.8 is skipped
    assert math.isnan(late_only.bss.value) and math.isnan(late_only.auc.value)
    pooled = cells.binary[(0, 0, vague, None, None)]
    assert pooled.bss.value == pytest.approx(1 - 0.25 / 0.24)
    assert (pooled.auc.value, cells.binary[(0, 0, sharp, None, None)].auc.value) == (0.5, 1.0)
    assert cells.distribution[(0, vague, None, None)].pit_coverage.value == 1.0
    # Sharp's PIT pairs are (0, 1), so u = V: V is drawn once per row in file order.
    draws = np.random.default_rng(config.summary.pit_seed).random(table.n_rows)
    rows = [i for i, r in enumerate(synthetic_rows()) if r["forecaster"] == "sharp" and "crps" in r]
    expected = np.mean([0.1 <= draws[i] <= 0.9 for i in rows])
    assert cells.distribution[(0, sharp, None, None)].pit_coverage.value == expected

    plan = cells.plan_stage[(0, 0, sharp, 0.5, None)]
    assert (plan.late, plan.late_below.value, plan.on_time, plan.on_time_below.value) == (
        1,
        1.0,
        1,
        0.0,
    )
    calm, alarmed = (
        cells.plan_stage[(0, 0, vague, 0.5, None)],
        cells.plan_stage[(0, 0, vague, 0.8, None)],
    )
    assert (calm.late_below.value, calm.on_time_below.value) == (0.0, 0.0)
    assert (alarmed.late_below.value, alarmed.on_time_below.value) == (1.0, 1.0)

    assert cli.main(["summarise-forecasts", str(synthetic_run)]) == 0
    text = (synthetic_run / "summary.md").read_text(encoding="utf-8")
    assert "### Plan-stage risk" in text and "at some checkpoint f ≥ 0.2" in text
    assert "| all | vague | 0.8 | 1 | 1.000 [1.000, 1.000] | 1 | 1.000 [1.000, 1.000] |" in text
    tex = (synthetic_run / "table_wp3_plan_stage.tex").read_text(encoding="utf-8")
    assert r"TINY & sharp & 0.5 & 1 & 100.0 & {\scriptsize[100.0, 100.0]} & 1 & 0.0 &" in tex
    headline = (synthetic_run / "table_wp3_headline.tex").read_text(encoding="utf-8")
    assert r"TINY & 0 & sharp & 0.000 & 1.000 & 0.000 & 1.000 & 0.000 &" in headline
    assert headline.count(r"\\") == 2 * 6 + 1  # header + value and interval rows per forecast


def test_latex_tables_typeset_negative_numbers(synthetic_run: Path) -> None:
    """Negative values in LaTeX tables carry a math minus, `$-$0.425`, never a hyphen; "--"
    (no value) and the Markdown formatting stay as they were."""
    assert summary._tex_num(-0.425) == "$-$0.425"
    assert summary._tex_num(0.425) == "0.425"
    assert summary._tex_num(-0.0001) == "0.000"
    assert summary._tex_num(math.nan) == "--"
    assert summary._num(-0.425) == "-0.425"
    estimate = summary.Estimate(value=0.0, low=-0.1234, high=0.05)
    assert summary._tex_ci(estimate) == r"{\scriptsize[$-$0.123, 0.050]}"
    assert summary._tex_short_ci(estimate) == r"{\scriptsize[$-$.123, .050]}"
    hyphen_minus = re.compile(r"(?<![\w$-])-\.?\d")
    for path in synthetic_run.glob("*.tex"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.startswith("%"):
                assert not hyphen_minus.search(line), (path.name, line)


REFERENCED_CONFIG = """
name = "referenced"
base_seed = 1
max_workers = 1
data_root = "data/psplib"
baseline = "cpsat_det"
replications = 2
deltas = [0.2, 0.3]
checkpoints = [0.0, 0.4, 0.8]

[baselines.cpsat_det]
deterministic_time_limit = 1.0
random_seed = 1

[scenarios]
lambda_a = [0.0]
mean_absence = [3]
lambda_s = 0.01
lambda_n = 0.02
durations_only = false

[[sets]]
name = "tiny"
reference = "opt"

[[forecasters]]
name = "solo"
kind = "monte_carlo"

[summary]
bootstrap_resamples = 20
reliability_checkpoints = [0.0, 0.4]
reference_run = "{reference}"
reference_forecasters = ["vague"]
"""


def input_state(paths: Sequence[Path]) -> list[tuple[bytes, int]]:
    return [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]


def test_reference_rows_are_joined_checked_and_marked(
    synthetic_run: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`solo` sees the worlds of the synthetic run; `vague` of that run is its reference. Of the
    9 checkpoints of `solo`, 6 have a reference row (replication 1 of instance 1 has none); one
    has another forecast seed and one another makespan. The inputs are only read."""
    rows = synthetic_rows(("solo",))
    for row in rows:
        if (row["instance"], row["f"]) == ("tiny1_2", 0.4):
            row["forecast_seed"] = 8
        if (row["instance"], row["f"]) == ("tiny1_2", 0.8):
            row["makespan"] = 15
    rows += [row | {"replication": 1} for row in rows if row["instance"] == "tiny1_1"]
    config_text = REFERENCED_CONFIG.format(reference=synthetic_run.as_posix())
    run_dir = write_run(tmp_path / "referenced", rows, config_text)
    inputs = [
        d / name for d in (run_dir, synthetic_run) for name in ("forecasts.csv.gz", "manifest.json")
    ]
    before = input_state(inputs)
    for path in inputs:
        path.chmod(0o444)

    assert cli.main(["summarise-forecasts", str(run_dir)]) == 0
    printed = capsys.readouterr().out
    assert (
        f"Reference rows of `vague` from run `synthetic` (`{synthetic_run.as_posix()}`): 6 rows "
        "joined on (set, instance, scenario, replication, f), **1 seed mismatches** (world or "
        "forecast seed) and **1 makespan mismatches** (expected 0), 3 missing."
    ) in printed
    assert input_state(inputs) == before
    record = json.loads((run_dir / "summary_manifest.json").read_text(encoding="utf-8"))
    check = record["reference_check"]
    assert (check["rows_joined"], check["seed_mismatches"], check["makespan_mismatches"]) == (
        6,
        1,
        1,
    )
    assert check["missing"] == 3
    digests = {entry["path"]: entry["sha256"] for entry in record["inputs"]}
    for path in inputs:
        shown = path.name if path.parent == run_dir else path.as_posix()
        assert digests[shown] == hashlib.sha256(path.read_bytes()).hexdigest()

    text = (run_dir / "summary.md").read_text(encoding="utf-8")
    assert "| all | vague (ref.) | 5 | 0.400 | 0.250 [0.250, 0.250] |" in text  # 1 skipped
    assert "| all | solo | 7 |" in text  # 9 checkpoints, 2 skipped
    assert r"vague$^\dagger$" in (run_dir / "table_wp3_headline.tex").read_text(encoding="utf-8")
    # Reference rows keep the randomised PIT values they have in their own run.
    config = ForecastStudyConfig.model_validate(tomllib.loads(config_text))
    own = summary.read_forecasts(run_dir / "forecasts.csv.gz")
    reference = summary.load_reference(own, config.summary)
    assert reference is not None and reference.table is not None
    expected = summary.table_pit(reference.table, 2026)[reference.rows]
    assert np.array_equal(reference.pit, expected, equal_nan=True)
    assert [r["instance"] for r in synthetic_rows()[1::2]] == [
        reference.table.names["instance"][c]
        for c in reference.table.codes["instance"][reference.rows]
    ]


def test_summariser_never_writes_its_inputs(synthetic_run: Path) -> None:
    """forecasts.csv.gz and manifest.json stay byte-identical with their modification times,
    even when read-only, and the summary manifest records their SHA-256."""
    inputs = [synthetic_run / "forecasts.csv.gz", synthetic_run / "manifest.json"]
    before = input_state(inputs)
    for path in inputs:
        path.chmod(0o444)
    outputs = summary.regenerate(synthetic_run)
    outputs = summary.regenerate(synthetic_run)
    assert input_state(inputs) == before
    assert not {"forecasts.csv.gz", "manifest.json"} & set(outputs.files)
    record = json.loads((synthetic_run / "summary_manifest.json").read_text(encoding="utf-8"))
    recorded = {entry["path"]: entry["sha256"] for entry in record["inputs"]}
    for path in inputs:
        assert recorded[path.name] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert record["summary_settings_source"] == "manifest.json"  # no config file recorded
    assert record["outputs"] == outputs.files[:-1] and outputs.files[-1] == "summary_manifest.json"


def test_summary_settings_come_from_the_config_file_while_it_describes_the_run(
    synthetic_run: Path, tmp_path: Path
) -> None:
    manifest = json.loads((synthetic_run / "manifest.json").read_text(encoding="utf-8"))
    wp2b = manifest["config"]["wp2b_results"]
    path = tmp_path / "synthetic.toml"
    path.write_text(SYNTHETIC_CONFIG.format(wp2b=wp2b) + "thresholds = [0.6]\n", encoding="utf-8")
    config, source = summary.run_config(manifest | {"config_path": str(path)})
    assert (config.summary.thresholds, source) == ((0.6,), path)
    changed = SYNTHETIC_CONFIG.format(wp2b=wp2b).replace("replications = 1", "replications = 2")
    path.write_text(changed + "thresholds = [0.6]\n", encoding="utf-8")
    config, source = summary.run_config(manifest | {"config_path": str(path)})
    assert (config.summary.thresholds, source) == ((0.5, 0.8), None)  # not the same run
    config, source = summary.run_config(manifest | {"config_path": str(tmp_path / "gone.toml")})
    assert source is None
