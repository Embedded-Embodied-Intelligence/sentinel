"""Baseline plans and their on-disk cache."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from sentinel.model import ProjectInstance, Schedule, validate_schedule
from sentinel.simulation import baselines
from sentinel.simulation.baselines import (
    CpsatDet,
    InvalidPlanError,
    SgsLft,
    baseline_plan,
    cache_path,
    cached_baseline,
    compute_baseline,
    read_cached,
)

Builder = Callable[..., ProjectInstance]

CPSAT = CpsatDet(deterministic_time_limit=1.0, random_seed=3)


@pytest.mark.parametrize(("method", "status"), [(CPSAT, "OPTIMAL"), (SgsLft(), "FEASIBLE")])
def test_compute_baseline_records_plan_and_provenance(
    tiny: ProjectInstance, method: CpsatDet | SgsLft, status: str
) -> None:
    plan = compute_baseline(tiny, method)
    assert (plan.instance, plan.method, plan.makespan, plan.status) == (
        "fixtures/tiny",
        method,
        7,
        status,
    )
    assert validate_schedule(tiny, plan.schedule) == []
    assert plan.instance_sha256 == baselines.instance_fingerprint(tiny)
    assert plan.cache_version == baselines.CACHE_VERSION
    assert {"python", "numpy", "ortools"} <= plan.versions.keys()
    if isinstance(method, CpsatDet):
        assert plan.lower_bound == 7 and plan.deterministic_time is not None
    else:
        assert plan.lower_bound is None and plan.deterministic_time is None


def test_cache_round_trip_keeps_one_entry_per_method(tiny: ProjectInstance, tmp_path: Path) -> None:
    first, cached = cached_baseline(tiny, SgsLft(), tmp_path)
    assert not cached
    path = tmp_path / "fixtures" / "tiny.json"
    assert cache_path(tiny.name, tmp_path) == path and path.is_file()
    again, cached = cached_baseline(tiny, SgsLft(), tmp_path)
    assert cached and again == first
    cpsat, cached = cached_baseline(tiny, CPSAT, tmp_path)
    assert not cached
    assert set(json.loads(path.read_text(encoding="utf-8"))) == {"cpsat_det", "sgs_lft"}
    assert read_cached(tiny, SgsLft(), tmp_path) == first
    assert read_cached(tiny, CPSAT, tmp_path) == cpsat
    assert baseline_plan(tiny, CPSAT, tmp_path) == cpsat
    assert not list(tmp_path.rglob("*.tmp"))  # atomic writes leave no temporary files


def test_baseline_plan_without_cache_writes_nothing(tiny: ProjectInstance, tmp_path: Path) -> None:
    assert baseline_plan(tiny, SgsLft(), cache_root=None).makespan == 7
    assert not any(tmp_path.iterdir())


def test_changed_parameters_invalidate_the_entry(tiny: ProjectInstance, tmp_path: Path) -> None:
    cached_baseline(tiny, CPSAT, tmp_path)
    for changed in (
        CpsatDet(deterministic_time_limit=2.0, random_seed=3),
        CpsatDet(deterministic_time_limit=1.0, random_seed=4),
    ):
        assert read_cached(tiny, changed, tmp_path) is None
        plan, cached = cached_baseline(tiny, changed, tmp_path)
        assert not cached and plan.method == changed
        assert read_cached(tiny, changed, tmp_path) == plan  # the entry was replaced
        assert read_cached(tiny, CPSAT, tmp_path) is None


def test_changed_instance_invalidates_the_entry(
    tiny: ProjectInstance, tmp_path: Path, build: Builder
) -> None:
    cached_baseline(tiny, SgsLft(), tmp_path)
    longer = build([0, 3, 2, 5, 0], [[0], [2], [2], [1], [0]], [[1, 2], [3], [4], [4], []])
    longer = longer.model_copy(update={"name": tiny.name})  # same cache file, other content
    assert read_cached(longer, SgsLft(), tmp_path) is None
    plan, cached = cached_baseline(longer, SgsLft(), tmp_path)
    assert not cached and plan.makespan == 8


@pytest.mark.parametrize(
    ("field", "value"),
    [("cache_version", 0), ("versions", {"ortools": "0.0"}), ("instance", "other/name")],
)
def test_stale_entries_are_recomputed(
    tiny: ProjectInstance, tmp_path: Path, field: str, value: object
) -> None:
    cached_baseline(tiny, CPSAT, tmp_path)
    path = cache_path(tiny.name, tmp_path)
    entries = json.loads(path.read_text(encoding="utf-8"))
    entries["cpsat_det"][field] = value
    path.write_text(json.dumps(entries), encoding="utf-8")
    assert read_cached(tiny, CPSAT, tmp_path) is None
    assert not cached_baseline(tiny, CPSAT, tmp_path)[1]
    assert read_cached(tiny, CPSAT, tmp_path) is not None


@pytest.mark.parametrize("text", ["{not json", "[1, 2]", '{"sgs_lft": {"makespan": 7}}'])
def test_unreadable_cache_files_are_recomputed(
    tiny: ProjectInstance, tmp_path: Path, text: str
) -> None:
    path = cache_path(tiny.name, tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
    assert read_cached(tiny, SgsLft(), tmp_path) is None
    plan, cached = cached_baseline(tiny, SgsLft(), tmp_path)
    assert not cached and read_cached(tiny, SgsLft(), tmp_path) == plan


@pytest.mark.parametrize("name", ["/abs/tiny", "../escape", "j30/../../escape"])
def test_cache_path_rejects_names_outside_the_root(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError, match="relative path"):
        cache_path(name, tmp_path)


def test_infeasible_plans_are_rejected(
    tiny: ProjectInstance, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def overlapping(*_: object, **__: object) -> Schedule:
        return Schedule(starts=(0, 0, 0, 3, 7))  # activities 1 and 2 need 4 > 3 workers

    monkeypatch.setattr(baselines, "serial_sgs", overlapping)
    with pytest.raises(InvalidPlanError, match="violations"):
        cached_baseline(tiny, SgsLft(), tmp_path)
    assert not cache_path(tiny.name, tmp_path).exists()
