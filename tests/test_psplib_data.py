"""Checks on the downloaded PSPLIB J30/J60 data; skipped when data/psplib is absent."""

from collections.abc import Callable
from functools import cache
from pathlib import Path

import pytest

from sentinel.data.psplib_loader import instance_path, list_instances, load_psplib
from sentinel.data.reference import ReferenceKind, load_reference, reference_path
from sentinel.model import ProjectInstance
from sentinel.scheduling.bounds import critical_path_lower_bound

pytestmark = pytest.mark.data

LoadSet = Callable[[str], dict[str, ProjectInstance]]


@pytest.fixture(scope="module")
def load_set(psplib_root: Path) -> LoadSet:
    """All instances of a set keyed by name, loaded once per module."""

    @cache
    def _load(set_name: str) -> dict[str, ProjectInstance]:
        if not (psplib_root / set_name).is_dir():
            pytest.skip(f"data/psplib/{set_name} missing; run scripts/fetch_psplib.py")
        return {
            f"{set_name}/{stem}": load_psplib(instance_path(set_name, stem, psplib_root))
            for stem in list_instances(set_name, psplib_root)
        }

    return _load


def require_reference(psplib_root: Path, set_name: str, kind: ReferenceKind) -> None:
    if not reference_path(set_name, kind, psplib_root).is_file():
        pytest.skip(f"solution file {set_name}_{kind}.sm missing; run scripts/fetch_psplib.py")


@pytest.mark.parametrize(("set_name", "n_real"), [("j30", 30), ("j60", 60)])
def test_all_instances_load(load_set: LoadSet, set_name: str, n_real: int) -> None:
    instances = load_set(set_name)
    assert len(instances) == 480
    for name, inst in instances.items():
        assert inst.name == name
        assert inst.n_real == n_real
        assert len(inst.roles) == 4
        assert len(inst.workers) == sum(role.capacity for role in inst.roles)


def test_j30_optima_cover_all_instances_and_respect_lb0(
    load_set: LoadSet, psplib_root: Path
) -> None:
    require_reference(psplib_root, "j30", "opt")
    optima = load_reference("j30", "opt", psplib_root)
    instances = load_set("j30")
    assert len(optima) == 480
    assert optima.keys() == instances.keys()
    below = [n for n, opt in optima.items() if opt < critical_path_lower_bound(instances[n])]
    assert below == []


def test_j60_upper_bounds_not_below_lower_bounds(psplib_root: Path) -> None:
    require_reference(psplib_root, "j60", "hrs")
    require_reference(psplib_root, "j60", "lb")
    upper = load_reference("j60", "hrs", psplib_root)
    lower = load_reference("j60", "lb", psplib_root)
    common = upper.keys() & lower.keys()
    assert len(upper) == 480
    assert common
    assert [n for n in sorted(common) if upper[n] < lower[n]] == []
