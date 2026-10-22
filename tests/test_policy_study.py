"""Policy study runner, its configs and its summaries (WP4b, spec sections 7 and 7.1)."""

import csv
import dataclasses
import gzip
import io
import json
import math
import re
import tomllib
from pathlib import Path
from typing import Any

import pytest

from sentinel import cli
from sentinel.experiments import policy_study as study
from sentinel.experiments import policy_summary as summary
from sentinel.experiments.policy_config import PolicyStudyConfig
from sentinel.experiments.simulation_summary import wilson_interval
from sentinel.policies.registry import COMPARED

REPO_ROOT = Path(__file__).resolve().parents[1]

FAKE_POLICY_CONFIG = """
name = "fake_wp4"
base_seed = 11
max_workers = 1
data_root = "{root}"
baseline_cache = "{cache}"
replications = 2
deltas = [0.2, 0.3]
baseline = "cpsat_det"
policies = {policies}
deterministic_time_limit = 0.05

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
"""


def write_config(fake_study: Path, policies: tuple[str, ...] = COMPARED) -> Path:
    """A policy study on the set `tiny` of the `fake_study` fixture (two copies of tiny.sm)."""
    root = fake_study.parent
    config = root / "fake_wp4.toml"
    text = FAKE_POLICY_CONFIG.format(
        root=(root / "psplib").as_posix(),
        cache=(root / "cache").as_posix(),
        policies=json.dumps(list(policies)),
    )
    config.write_text(text, encoding="utf-8")
    return config


def read_rows(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@pytest.mark.parametrize("name", ["wp4_baselines", "wp4_sensitivity"])
def test_the_committed_configs_follow_the_study_plan(name: str) -> None:
    raw = tomllib.loads((REPO_ROOT / "configs" / f"{name}.toml").read_text(encoding="utf-8"))
    config = PolicyStudyConfig.model_validate(raw)
    assert config.policies == COMPARED and config.deterministic_time_limit == 0.1
    assert (config.base_seed, config.replications, config.deltas) == (2026, 4, (0.2, 0.3))
    assert [s.stride for s in config.sets] == [4] * len(config.sets)
    assert config.wp2b_results is not None and config.summary.reference_policy == "no_reaction"
    scenarios = [s.name for s in config.scenarios.expand()]
    if name == "wp4_baselines":
        assert [s.name for s in config.sets] == ["j30", "j60"]
        assert scenarios == ["la0_L3", "la0.005_L3", "la0.01_L3", "la0.02_L3"]
    else:
        assert [s.name for s in config.sets] == ["j30"]
        assert scenarios == ["la0.01_L5", "la0.02_L5"]


def test_configs_reject_unknown_policies_and_a_missing_reference(fake_study: Path) -> None:
    raw = tomllib.loads(write_config(fake_study).read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="unknown policy"):
        PolicyStudyConfig.model_validate({**raw, "policies": ["no_reaction", "oracle"]})
    with pytest.raises(ValueError, match="reference policy"):
        PolicyStudyConfig.model_validate({**raw, "policies": ["full_resolve"]})
    with pytest.raises(ValueError, match="one mean_absence"):
        scenarios = {**raw["scenarios"], "mean_absence": [3, 5]}
        PolicyStudyConfig.model_validate({**raw, "scenarios": scenarios})


def test_runner_on_tiny_writes_every_output(
    fake_study: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two tiny instances x two scenarios x two replications x the five policies: one row per
    run with the expected columns, common seeds, checked runs, summaries that regenerate."""
    config_path = write_config(fake_study)
    out = tmp_path / "results"
    assert study.main(["--config", str(config_path), "--out", str(out)]) == 0
    (run_dir,) = out.iterdir()
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "completed" and manifest["smoke"] is False
    assert manifest["n_runs"] == manifest["n_rows"] == 2 * 2 * 2 * 5
    assert manifest["cpsat"] == {
        "deterministic_time_limit": 0.05,
        "random_seed": 0,
        "num_workers": 1,
    }
    assert manifest["checks"] == {
        "rejected_operations": 0,
        "cpsat_fallbacks": 0,
        "truncated_runs": 0,
    }
    assert manifest["baselines"]["computed_in_run"] + manifest["baselines"]["from_cache"] == 2
    rows = read_rows(run_dir / "results.csv.gz")
    assert tuple(rows[0]) == study.columns((0.2, 0.3)) and len(rows) == 40
    assert [r["policy"] for r in rows[:5]] == list(COMPARED)
    worlds: dict[tuple[str, str, str], set[str]] = {}
    for row in rows:
        worlds.setdefault((row["instance"], row["scenario"], row["replication"]), set()).add(
            row["seed"]
        )
    assert len(worlds) == 8 and all(len(seeds) == 1 for seeds in worlds.values())  # CRN
    quiet = [r for r in rows if r["policy"] == "no_reaction"]
    assert all(r["substitutions"] == r["reseqs"] == r["nervousness"] == "0" for r in quiet)
    assert any(int(r["reseqs"]) > 0 for r in rows if r["policy"] == "full_resolve")
    expected = {
        "summary.md",
        "table_wp4.tex",
        "fig_wp4_ontime.pdf",
        "fig_wp4_ontime.png",
        "fig_wp4_tradeoff.pdf",
        "fig_wp4_tradeoff.png",
        "summary_manifest.json",
    }
    assert set(manifest["outputs"]) == {"results.csv.gz", *expected}
    assert {p.name for p in run_dir.iterdir()} == {"manifest.json", "results.csv.gz", *expected}
    text = (run_dir / "summary.md").read_text(encoding="utf-8")
    assert "WP2b seed check: not run" in text and "0 rejected operations" in text
    stamped = summary.SUMMARY_MANIFEST_FILE
    before = {p.name: p.read_bytes() for p in run_dir.iterdir() if p.name != stamped}
    capsys.readouterr()
    assert cli.main(["summarise-policies", str(run_dir)]) == 0
    assert "summary.md" in capsys.readouterr().out
    assert {p.name: p.read_bytes() for p in run_dir.iterdir() if p.name != stamped} == before
    record = json.loads((run_dir / stamped).read_text(encoding="utf-8"))
    assert record["summary_settings_source"] == config_path.as_posix()
    assert cli.main(["summarise-policies", str(tmp_path / "missing")]) == 1


SYNTHETIC_POLICIES = ("no_reaction", "full_resolve", "always_substitute")


def synthetic_rows() -> list[dict[str, Any]]:
    """Three instances x two scenarios x two replications x three policies with known values.

    NoReaction is on time (delta 0.2) in replication 0 only, with C / C* = 1.2 and deviation 2.
    FullResolve is always on time, C / C* lower by 0.1 * (instance number), deviation + 1;
    AlwaysSubstitute is never on time, otherwise like NoReaction, with 3 substitutions and 6
    onboarding days per run. The deadline of 0.3 is always met.
    """
    rows = []
    for i, instance in enumerate(("t1_1", "t1_2", "t1_10")):
        for scenario, lambda_a in (("la0_L3", 0.0), ("la0.05_L3", 0.05)):
            for replication in (0, 1):
                for policy in SYNTHETIC_POLICIES:
                    on_time = {
                        "no_reaction": replication == 0,
                        "full_resolve": True,
                        "always_substitute": False,
                    }[policy]
                    ratio = round(1.2 - (0.1 * (i + 1) if policy == "full_resolve" else 0.0), 6)
                    subst = 3 if policy == "always_substitute" else 0
                    row = {column: 0 for column in study.columns((0.2, 0.3))}
                    row |= {
                        "set": "tiny",
                        "instance": instance,
                        "scenario": scenario,
                        "lambda_a": lambda_a,
                        "mean_absence": 3,
                        "replication": replication,
                        "seed": 100 + 10 * i + replication,
                        "policy": policy,
                        "c_star": 10,
                        "makespan": round(10 * ratio),
                        "ratio_c_star": ratio,
                        "met_0.2": on_time,
                        "met_0.3": True,
                        "cost_ratio": 0.9,
                        "deviation": 2.0 + (1.0 if policy == "full_resolve" else 0.0),
                        "substitutions": subst,
                        "onboarding_days": 2 * subst,
                        "handover_days": 0.5 * subst,
                        "truncated": False,
                    }
                    rows.append(row)
    return rows


def synthetic_config(tmp_path: Path) -> PolicyStudyConfig:
    return PolicyStudyConfig.model_validate(
        {
            "name": "synthetic",
            "base_seed": 1,
            "max_workers": 1,
            "data_root": str(tmp_path),
            "baseline": "cpsat_det",
            "baselines": {"cpsat_det": {"deterministic_time_limit": 1.0, "random_seed": 1}},
            "sets": [{"name": "tiny", "reference": "opt"}],
            "replications": 2,
            "deltas": [0.2, 0.3],
            "policies": list(SYNTHETIC_POLICIES),
            "scenarios": {
                "lambda_a": [0.0, 0.05],
                "mean_absence": [3],
                "lambda_s": 0.0,
                "lambda_n": 0.0,
                "durations_only": False,
            },
            "summary": {"bootstrap_resamples": 200, "table": "table_x", "figure_prefix": "fig_x"},
        }
    )


def write_synthetic(run_dir: Path, rows: list[dict[str, Any]]) -> None:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=study.columns((0.2, 0.3)))
    writer.writeheader()
    writer.writerows(rows)
    (run_dir / "results.csv.gz").write_bytes(gzip.compress(buffer.getvalue().encode(), mtime=0))


def test_summariser_on_a_synthetic_csv(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    write_synthetic(run_dir, synthetic_rows())
    config = synthetic_config(tmp_path)
    outputs = summary.write_summaries(run_dir, "synthetic-run", config, "results.csv.gz")
    assert set(outputs.files) == {
        "summary.md",
        "table_x.tex",
        "fig_x_ontime.pdf",
        "fig_x_ontime.png",
        "fig_x_tradeoff.pdf",
        "fig_x_tradeoff.png",
        "summary_manifest.json",
    }
    rows = summary.read_results(run_dir / "results.csv.gz", config.deltas)
    analysis = summary.Analysis(rows, config)
    pooled = analysis.cell("tiny", None, "no_reaction")
    assert pooled is not None and pooled.n == 12 and pooled.on_time == (6, 12)
    assert pooled.interval(0) == wilson_interval(6, 12)
    substituting = analysis.cell("tiny", "la0_L3", "always_substitute")
    assert substituting is not None and substituting.onboarding_per_substitution == 2.0
    assert substituting.handover_days == 1.5 and substituting.share(0) == 0.0
    # Paired differences: on time +50 pp in every instance, so the interval is a point; C / C*
    # by -0.1, -0.2, -0.3 per instance: mean -0.2, the interval within the instance values.
    resolve = analysis.difference("tiny", None, "full_resolve")
    assert resolve is not None and resolve.n == 12
    assert (resolve.on_time[0].value, resolve.on_time[0].low, resolve.on_time[0].high) == (
        50.0,
        50.0,
        50.0,
    )
    assert resolve.on_time[1].value == 0.0 and resolve.deviation.value == pytest.approx(1.0)
    assert resolve.ratio.value == pytest.approx(-0.2)
    assert -0.3 - 1e-9 <= resolve.ratio.low < -0.2 < resolve.ratio.high <= -0.1 + 1e-9
    by_scenario = analysis.difference("tiny", "la0.05_L3", "always_substitute")
    assert by_scenario is not None and by_scenario.on_time[0].value == -50.0
    assert analysis.difference("tiny", None, "no_reaction") is None
    again = summary.Analysis(rows, config).difference("tiny", None, "full_resolve")
    assert again == resolve  # fixed bootstrap seed
    text = (run_dir / "summary.md").read_text(encoding="utf-8")
    assert "| all | -- | FullResolve | 12 | +50.0 [50.0, 50.0] | 0.0 [0.0, 0.0] |" in text
    table = (run_dir / "table_x.tex").read_text(encoding="utf-8")
    assert r"\begin{tabular}{@{}lrrrrrrr@{}}" in table
    body = [line for line in table.splitlines() if line.endswith(r"\\") and "&" in line]
    assert body and all(line.count("&") + 1 <= 9 for line in body)
    assert r"FullResolve & 100.0 & 100.0 & 1.000 & 3.0 & 0.0 & 0.0 & 0.900 \\" in table
    assert re.search(r"\{\\scriptsize\[\$-\$\.\d{3}, \$-\$\.\d{3}\]\}", table)
    record = json.loads((run_dir / "summary_manifest.json").read_text(encoding="utf-8"))
    assert record["wp2b_check"]["available"] is False
    assert [entry["path"] for entry in record["inputs"]] == ["results.csv.gz"]


def test_wp2b_check_compares_the_noreaction_worlds(tmp_path: Path) -> None:
    rows = summary.read_results(write_and_return(tmp_path), (0.2, 0.3))
    quiet = [r for r in rows if r.policy == "no_reaction"]
    wp2b = tmp_path / "wp2b.csv"
    with wp2b.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["set", "instance", "scenario", "replication", "seed", "makespan"])
        for k, r in enumerate(quiet[:-1]):  # the last world has no WP2b row
            makespan = r.makespan + (1 if k == 0 else 0)  # one makespan differs
            writer.writerow([r.set_name, r.instance, r.scenario, r.replication, r.seed, makespan])
    check = summary.wp2b_check(rows, wp2b)
    assert (check.checked, check.makespan_mismatches, check.seed_mismatches, check.missing) == (
        11,
        1,
        0,
        1,
    )
    assert not summary.wp2b_check(rows, tmp_path / "absent.csv").available
    assert math.isnan(summary.Cell(1, (0,), *([0.0] * 10), 0, 0, 0).onboarding_per_substitution)


def write_and_return(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    write_synthetic(run_dir, synthetic_rows())
    return run_dir / "results.csv.gz"


@pytest.mark.parametrize("name", ["wp5_rq4_main", "wp5_rq4_ablation"])
def test_the_wp5_configs_follow_the_study_plan(name: str) -> None:
    """The RQ4 Sentinel subset of docs/experiments/plan.md: J30 every 4th, J60 every 8th, WP2b
    seeds, delta_D = 0.2 unless a variant says otherwise, the WP4b baselines joined, paired
    differences against NoReaction and FullResolve."""
    raw = tomllib.loads((REPO_ROOT / "configs" / f"{name}.toml").read_text(encoding="utf-8"))
    config = PolicyStudyConfig.model_validate(raw)
    assert (config.base_seed, config.replications, config.deltas) == (2026, 4, (0.2, 0.3))
    assert config.policies[0] == "no_reaction" and set(config.joined) == set(COMPARED[1:])
    assert config.wp4b_results is not None and config.wp4b_results.name == "results.csv.gz"
    assert config.summary.reference_policies == ("no_reaction", "full_resolve")
    assert config.scenarios.mean_absence == (3,) and not config.start_estimate
    variants = config.sentinel_variants
    shape = {
        name: (v.params.variant, v.params.autonomy, v.delta_d, v.params.descope, v.optional_share)
        for name, v in variants.items()
    }
    assert {(v.params.n_stage1, v.params.n_rollouts) for v in variants.values()} == {(25, 100)}
    if name == "wp5_rq4_main":
        assert [(s.name, s.stride) for s in config.sets] == [("j30", 4), ("j60", 8)]
        assert config.scenarios.lambda_a == (0.0, 0.005, 0.01, 0.02)
        assert shape == {
            "sentinel_full": ("full", 3, 0.2, False, 0.0),
            "sentinel_no_ot": ("no_overtime", 3, 0.2, False, 0.0),
            "sentinel_gate": ("full", 2, 0.2, False, 0.0),
        }
    else:
        assert [(s.name, s.stride) for s in config.sets] == [("j30", 4)]
        assert config.scenarios.lambda_a == (0.01, 0.02)
        assert shape == {
            "sentinel_scalarised": ("scalarised", 3, 0.2, False, 0.0),
            "sentinel_lambda0": ("full", 0, 0.2, False, 0.0),
            "sentinel_lambda1": ("full", 1, 0.2, False, 0.0),
            "sentinel_descope": ("full", 2, 0.2, True, 0.1),
            "sentinel_delta03": ("full", 3, 0.3, False, 0.0),
        }


def test_runner_with_a_sentinel_variant_joins_the_baselines_of_an_earlier_run(
    fake_study: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A baseline run (NoReaction, FullResolve) on the tiny worlds, then a Sentinel run that
    reads FullResolve from it: the join finds every world with 0 mismatches, the Sentinel rows
    carry their counts, and the summaries compare against both references. The tasks run in
    this process (the pool is tested above)."""
    monkeypatch.setattr(
        study, "execute", lambda tasks, workers, n_runs: [study.run_task(t) for t in tasks]
    )
    base = write_config(fake_study, ("no_reaction", "full_resolve"))
    text = base.read_text(encoding="utf-8").replace("replications = 2", "replications = 1")
    earlier = tmp_path / "first"
    earlier.mkdir()
    baseline_config = PolicyStudyConfig.model_validate(tomllib.loads(text))
    tasks, _ = study.build_tasks(baseline_config, None)
    found = [row for task in tasks for row in study.run_task(task).rows]
    study.write_results(earlier, found, study.columns(baseline_config.deltas))
    raw = tomllib.loads(text)
    raw |= {
        "name": "fake_wp5",
        "policies": ["no_reaction", "sentinel_gate"],
        "wp4b_results": str(earlier / "results.csv.gz"),
        "joined": ["full_resolve"],
        "start_estimate": False,
        "sentinel": {"n_rollouts": 8, "n_stage1": 4},
        "variants": {"sentinel_gate": {"autonomy": 2, "delta_d": 0.2}},
        "summary": {
            "bootstrap_resamples": 100,
            "references": ["full_resolve"],
            "table": "table_y",
            "figure_prefix": "fig_y",
        },
    }
    config_path = tmp_path / "fake_wp5.toml"
    config_path.write_text(_toml(raw), encoding="utf-8")
    out = tmp_path / "second"
    assert study.main(["--config", str(config_path), "--out", str(out)]) == 0
    (run_dir,) = out.iterdir()
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["wp4b_check"] == {
        "path": (earlier / "results.csv.gz").as_posix(),
        "policies": ["full_resolve"],
        "worlds": 4,
        "rows": 4,
        "seed_mismatches": 0,
        "makespan_mismatches": 0,
        "missing": 0,
    }
    assert manifest["sentinel_variants"]["sentinel_gate"]["params"]["autonomy"] == 2
    rows = read_rows(run_dir / "results.csv.gz")
    sentinel = [r for r in rows if r["policy"] == "sentinel_gate"]
    assert len(sentinel) == 4 and all(int(r["deliberations"]) > 0 for r in sentinel)
    assert all(r["agent_delta"] == "0.2" for r in sentinel)
    assert {r["agent_delta"] for r in rows if r["policy"] == "no_reaction"} == {""}
    assert {
        "table_y.tex",
        "table_y_vs_full_resolve.tex",
        "fig_y_tradeoff.png",
        "fig_y_actions.png",
    } <= set(manifest["outputs"])
    text = (run_dir / "summary.md").read_text(encoding="utf-8")
    assert "Paired differences against NoReaction:" in text
    assert "Paired differences against FullResolve:" in text
    assert "**0 NoReaction makespan mismatches**" in text and "Sentinel Λ=2" in text
    config = PolicyStudyConfig.model_validate(raw)
    own = summary.read_results(run_dir / "results.csv.gz", config.deltas)
    changed = [
        r if r.policy != "no_reaction" or k else dataclasses.replace(r, makespan=r.makespan + 1)
        for k, r in enumerate(own)
    ]
    joined, check = summary.join_baselines(changed, config)
    assert len(joined) == 4 and check is not None and check.makespan_mismatches == 1


def _toml(data: dict[str, Any]) -> str:
    """A minimal TOML writer for the nested config dictionaries of these tests."""
    lines: list[str] = []
    tables: list[tuple[str, dict[str, Any]]] = []
    arrays: list[tuple[str, list[dict[str, Any]]]] = []

    def value(v: Any) -> str:
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, str):
            return json.dumps(v)
        if isinstance(v, list):
            return "[" + ", ".join(value(x) for x in v) + "]"
        return repr(v)

    def emit(prefix: str, table: dict[str, Any]) -> None:
        for key, v in table.items():
            name = f"{prefix}.{key}" if prefix else key
            if isinstance(v, dict):
                tables.append((name, v))
            elif isinstance(v, list) and v and isinstance(v[0], dict):
                arrays.append((name, v))
            else:
                lines.append(f"{key} = {value(v)}")

    emit("", data)
    while tables:
        name, table = tables.pop(0)
        lines.append(f"\n[{name}]")
        emit(name, table)
    for name, items in arrays:
        for item in items:
            lines.append(f"\n[[{name}]]")
            emit(name, item)
    return "\n".join(lines) + "\n"
