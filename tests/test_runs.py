"""Run identity, seed derivation and manifest helpers (experiment-run skill)."""

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from sentinel.experiments import runs


def test_config_hash_ignores_key_order_but_not_limit() -> None:
    a = {"name": "x", "sets": [{"name": "j30", "reference": "opt"}], "base_seed": 1}
    b = {"base_seed": 1, "sets": [{"reference": "opt", "name": "j30"}], "name": "x"}
    assert runs.config_hash(a, None) == runs.config_hash(b, None)
    assert runs.config_hash(a, None) != runs.config_hash(a, 10)
    assert len(runs.config_hash(a, None)) == 64


def test_a_selection_of_the_config_changes_the_hash_and_none_keeps_it() -> None:
    a = {"name": "x", "backends": ["ollama", "groq"]}
    assert runs.config_hash(a, 1, None) == runs.config_hash(a, 1) == runs.config_hash(a, 1, {})
    ollama = runs.config_hash(a, 1, {"backends": ["ollama"]})
    assert ollama != runs.config_hash(a, 1) and ollama != runs.config_hash(
        a, 1, {"backends": ["groq"]}
    )


def test_run_id_uses_utc_time_and_hash_prefix() -> None:
    moment = datetime(2026, 10, 20, 14, 5, 9, tzinfo=timezone(timedelta(hours=2)))
    assert runs.make_run_id(moment, "0123456789abcdef") == "20261020-120509-01234567"
    assert runs.utc_iso(moment) == "2026-10-20T12:05:09+00:00"


def test_run_dirs_are_never_reused(tmp_path: Path) -> None:
    smoke = runs.create_run_dir(tmp_path / "wp1", "20261020-120509-01234567", smoke=True)
    assert smoke.name == "20261020-120509-01234567-smoke"
    assert smoke.is_dir()
    with pytest.raises(FileExistsError):
        runs.create_run_dir(tmp_path / "wp1", "20261020-120509-01234567", smoke=True)


def test_derive_seed_is_stable_and_fits_31_bits() -> None:
    # Pinned values: changing the derivation would silently change every recorded seed.
    assert runs.derive_seed(2026, "j30", "j301_1") == 960881505
    assert runs.derive_seed(2026, "j60", "j601_1") == 1281801886
    seeds = {runs.derive_seed(base, "j30", f"j301_{i}") for base in (1, 2) for i in range(50)}
    assert len(seeds) == 100
    assert all(0 <= seed < 2**31 for seed in seeds)


def test_environment_records_versions_and_machine() -> None:
    env = runs.environment()
    assert set(env) == {"python", "packages", "platform", "cpu", "cpu_count", "hostname"}
    assert set(env["packages"]) == set(runs.KEY_PACKAGES)
    assert env["packages"]["numpy"]
    assert env["cpu"]


def test_git_state_reports_commit_and_dirty_flag() -> None:
    state = runs.git_state()
    assert set(state) == {"commit", "dirty"}
    assert state["commit"] is None or len(state["commit"]) == 40


def test_write_json_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    runs.write_json(path, {"run_id": "r", "when": runs.utc_iso(datetime(2026, 1, 1, tzinfo=UTC))})
    assert path.read_text(encoding="utf-8").endswith("}\n")
