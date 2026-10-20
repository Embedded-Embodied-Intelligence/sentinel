"""RCPSP benchmark runner: config, rows, abort on invalid schedules, outputs of a full run."""

import csv
import json
import shutil
from pathlib import Path

import pytest

from sentinel.experiments import rcpsp_benchmark as bench
from sentinel.experiments import runs
from sentinel.experiments.rcpsp_config import BenchmarkConfig, SgsMethod
from sentinel.model import Schedule

REPO_ROOT = Path(__file__).resolve().parents[1]

FAKE_CONFIG = """
name = "fake_rq2"
base_seed = 7
max_workers = 2
data_root = "{root}"

[[sets]]
name = "tiny"
reference = "opt"
dev_lb0 = true

[[methods]]
name = "sgs_lft"
label = "SGS-LFT"
kind = "sgs"
rule = "lft"

[[methods]]
name = "rbrs_5"
label = "RBRS-5"
kind = "rbrs"
n_schedules = 5

[[methods]]
name = "cpsat_1s"
label = "CP-SAT 1 s"
kind = "cpsat"
time_limit_s = 1.0
"""


@pytest.fixture
def fake_set(tmp_path: Path, tiny_path: Path) -> Path:
    """Config file for a set `tiny` of two copies of the tiny fixture with optimum 7."""
    root = tmp_path / "psplib"
    (root / "tiny").mkdir(parents=True)
    (root / "solutions").mkdir()
    for stem in ("tiny1_1", "tiny1_2"):
        shutil.copy(tiny_path, root / "tiny" / f"{stem}.sm")
    (root / "solutions" / "tiny_opt.sm").write_text(
        "Paramter Instance Makespan CPU-Time[sec.]\n1 1 7 0.0\n1 2 7 0.0\n", encoding="utf-8"
    )
    config = tmp_path / "fake.toml"
    config.write_text(FAKE_CONFIG.format(root=root.as_posix()), encoding="utf-8")
    return config


def test_wp1_config_matches_the_work_package() -> None:
    config = BenchmarkConfig.model_validate(runs.load_toml(REPO_ROOT / "configs" / "wp1_rq2.toml"))
    assert (config.base_seed, config.max_workers) == (2026, 4)
    assert [(s.name, s.reference, s.dev_lb0) for s in config.sets] == [
        ("j30", "opt", False),
        ("j60", "hrs", True),
    ]
    assert [m.name for m in config.methods] == [
        "sgs_lft",
        "sgs_lst",
        "sgs_mts",
        "sgs_grpw",
        "rbrs_1000",
        "cpsat_1s",
        "cpsat_10s",
    ]
    cpsat = [m for m in config.methods if m.kind == "cpsat"]
    assert [(m.time_limit_s, m.num_workers) for m in cpsat] == [(1.0, 1), (10.0, 1)]


def test_config_rejects_duplicate_method_names(fake_set: Path) -> None:
    raw = runs.load_toml(fake_set)
    raw["methods"].append(dict(raw["methods"][0]))
    with pytest.raises(ValueError, match="duplicate method names"):
        BenchmarkConfig.model_validate(raw)


def test_deviation_pct() -> None:
    assert bench.deviation_pct(45, 43) == 4.6512
    assert bench.deviation_pct(43, 43) == 0.0
    assert bench.deviation_pct(None, 43) is None
    assert bench.deviation_pct(45, None) is None


def test_invalid_schedule_raises(
    fake_set: Path, tiny_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_: object) -> bench.Outcome:
        return bench.Outcome(Schedule(starts=(0, 0, 0, 3, 7)), "FEASIBLE")  # overloads day 0

    monkeypatch.setattr(bench, "run_method", broken)
    method = SgsMethod(kind="sgs", name="sgs_lft", label="SGS-LFT", rule="lft")
    task = bench.Task("tiny", "tiny1_1", fake_set.parent / "psplib", method, 1, 7)
    with pytest.raises(bench.InvalidScheduleError, match="violations"):
        bench.run_task(task)


def test_aborted_run_writes_manifest_and_fails(
    fake_set: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing(*_: object) -> list[bench.Row]:
        raise bench.InvalidScheduleError("tiny/tiny1_1 with sgs_lft: 2 violations")

    monkeypatch.setattr(bench, "execute", failing)
    out = tmp_path / "results"
    assert bench.main(["--config", str(fake_set), "--out", str(out)]) == 1
    (run_dir,) = out.iterdir()
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "aborted"
    assert "2 violations" in manifest["error"]
    assert not (run_dir / "results.csv").exists()


def test_smoke_run_writes_all_outputs(fake_set: Path, tmp_path: Path) -> None:
    out = tmp_path / "results"
    assert bench.main(["--config", str(fake_set), "--out", str(out), "--limit", "2"]) == 0
    (run_dir,) = out.iterdir()
    assert run_dir.name.endswith("-smoke")
    assert {p.name for p in run_dir.iterdir()} == {
        "manifest.json",
        "results.csv",
        "summary.md",
        "table_rq2.tex",
        "fig_rq2_deviation.pdf",
        "fig_rq2_deviation.png",
    }

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    required = {
        "run_id", "command", "config_path", "config", "config_hash", "limit", "git_commit",
        "git_dirty", "start_utc", "end_utc", "duration_s", "python", "packages", "cpu",
        "cpu_count", "hostname", "n_rows", "seeds", "smoke",
    }  # fmt: skip
    assert required <= manifest.keys()
    assert manifest["status"] == "completed"
    assert (manifest["smoke"], manifest["limit"], manifest["n_rows"]) == (True, 2, 6)
    assert run_dir.name == f"{manifest['run_id']}-smoke"
    assert manifest["config_hash"] == runs.config_hash(runs.load_toml(fake_set), 2)
    assert set(manifest["seeds"]["per_instance"]) == {"tiny/tiny1_1", "tiny/tiny1_2"}

    with (run_dir / "results.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert tuple(reader.fieldnames or ()) == bench.COLUMNS
        rows = list(reader)
    assert [(r["instance"], r["method"]) for r in rows] == [
        (stem, method)
        for stem in ("tiny1_1", "tiny1_2")
        for method in ("sgs_lft", "rbrs_5", "cpsat_1s")
    ]
    assert {(r["makespan"], r["lb0"], r["c_ref"], r["matches_ref"]) for r in rows} == {
        ("7", "7", "7", "True")
    }
    by_method = {(r["instance"], r["method"]): r for r in rows}
    seed = str(manifest["seeds"]["per_instance"]["tiny/tiny1_1"])
    assert by_method[("tiny1_1", "sgs_lft")]["seed"] == ""
    assert by_method[("tiny1_1", "rbrs_5")]["seed"] == seed  # common random numbers
    assert by_method[("tiny1_1", "cpsat_1s")]["seed"] == seed
    assert by_method[("tiny1_1", "cpsat_1s")]["status"] == "OPTIMAL"
    assert by_method[("tiny1_1", "cpsat_1s")]["solver_bound"] == "7"

    table = (run_dir / "table_rq2.tex").read_text(encoding="utf-8")
    assert r"\toprule" in table
    assert r"CP-SAT 1 s & 0.00 & 0.00 & 100.0 &" in table
    assert "| SGS-LFT | 2 | 2 | 0.00 | 2 (100.0%) | 0 |" in (run_dir / "summary.md").read_text(
        encoding="utf-8"
    )
    assert (run_dir / "fig_rq2_deviation.png").stat().st_size > 0
