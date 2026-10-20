"""Forecast study runner, its configs and its summaries (WP3b, spec section 5.2)."""

import csv
import gzip
import io
import json
import tomllib
from pathlib import Path
from typing import Any

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
    before = {p.name: p.read_bytes() for p in run_dir.iterdir()}
    capsys.readouterr()
    assert cli.main(["summarise-forecasts", str(run_dir)]) == 0
    printed = capsys.readouterr().out
    assert "WP2b seed check: not run" in printed and "summary.md" in printed
    assert {p.name: p.read_bytes() for p in run_dir.iterdir()} == before
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


def synthetic_rows() -> list[dict[str, object]]:
    """C* = 10, C_plan = 10, D = 12 (delta 0.2) and 13 (0.3). Instance 1 finishes on day 8, on
    time, so its checkpoint f = 0.8 (day 8) is skipped; instance 2 finishes on day 14, late.
    `sharp` forecasts the outcome exactly (p = 1 or 0, every quantile = C); `vague` says
    p = 0.5 with quantiles 8, 9, 10, 12, 14, 15, 16 and CRPS 1.5."""
    rows: list[dict[str, object]] = []
    for stem, makespan in (("tiny1_1", 8), ("tiny1_2", 14)):
        for f, day in ((0.0, 0), (0.4, 4), (0.8, 8)):
            for name in ("sharp", "vague"):
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
                    sharp = name == "sharp"
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


@pytest.fixture
def synthetic_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "synthetic-run"
    run_dir.mkdir()
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=study.columns((0.2, 0.3)), restval="")
    writer.writeheader()
    writer.writerows(synthetic_rows())
    (run_dir / "forecasts.csv.gz").write_bytes(gzip.compress(buffer.getvalue().encode()))
    wp2b = tmp_path / "wp2b.csv"  # instance 2's makespan differs from the synthetic world
    wp2b.write_text(
        "set,instance,scenario,replication,seed,makespan\n"
        "tiny,tiny1_1,la0_L3,0,108,8\ntiny,tiny1_2,la0_L3,0,114,15\n",
        encoding="utf-8",
    )
    config = tomllib.loads(SYNTHETIC_CONFIG.format(wp2b=wp2b.as_posix()))
    manifest = {"run_id": "synthetic", "config": config, "results_file": "forecasts.csv.gz"}
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return run_dir


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
    REL = 0.01, RES = 0, UNC = 0.24, ECE = 0.1; coverage 3/5 (instance 1 at C = 8 < q10 = 9);
    sharp warns instance 2 on day 0 (lead 12 days), vague only at theta = 0.8."""
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
    assert (warned.late, warned.warned.value, warned.lead.value) == (1, 1.0, 12.0)
    assert (warned.on_time, warned.false_alarms.value) == (1, 0.0)
    calm = cells.warnings[(0, 0, 1, 0.5, None)]
    assert (calm.warned.value, calm.false_alarms.value) == (0.0, 0.0)
    alarmed = cells.warnings[(0, 0, 1, 0.8, None)]
    assert (alarmed.warned.value, alarmed.lead.value, alarmed.false_alarms.value) == (1, 12, 1)
    pit = cells.distribution[(0, 0, None, None)].pit  # sharp: (0, 1) pairs, uniform draws
    assert int(pit.sum()) == 5
