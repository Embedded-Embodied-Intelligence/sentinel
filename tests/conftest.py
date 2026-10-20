"""Shared fixtures: the hand-made tiny instance, an instance builder and the PSPLIB data root."""

from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from sentinel.data.psplib_loader import load_psplib
from sentinel.model import Activity, ProjectInstance, Role, make_workers

REPO_ROOT = Path(__file__).resolve().parents[1]

Builder = Callable[..., ProjectInstance]


@pytest.fixture(scope="session")
def tiny_path() -> Path:
    return REPO_ROOT / "tests" / "fixtures" / "tiny.sm"


@pytest.fixture(scope="session")
def tiny(tiny_path: Path) -> ProjectInstance:
    return load_psplib(tiny_path)


@pytest.fixture
def build() -> Builder:
    """Build an instance from per-activity durations, demands and successors."""

    def _build(
        durations: Sequence[int],
        demands: Sequence[Sequence[int]],
        successors: Sequence[Sequence[int]],
        capacities: Sequence[int] = (3,),
    ) -> ProjectInstance:
        roles = tuple(Role(id=k, name=f"R{k + 1}", capacity=c) for k, c in enumerate(capacities))
        activities = tuple(
            Activity(id=j, duration=p, demands=tuple(r), successors=tuple(s))
            for j, (p, r, s) in enumerate(zip(durations, demands, successors, strict=True))
        )
        return ProjectInstance(
            name="test", activities=activities, roles=roles, workers=make_workers(roles)
        )

    return _build


@pytest.fixture(scope="session")
def psplib_root() -> Path:
    """Root of the downloaded PSPLIB data; skips the test cleanly if it was not fetched."""
    root = REPO_ROOT / "data" / "psplib"
    if not root.is_dir():
        pytest.skip("PSPLIB data not found in data/psplib; run scripts/fetch_psplib.py")
    return root
