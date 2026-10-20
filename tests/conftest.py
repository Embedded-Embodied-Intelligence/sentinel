"""Shared fixtures: the hand-made tiny instance, an instance builder, a fake study set and the
PSPLIB data root."""

import shutil
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


FAKE_STUDY_CONFIG = """
name = "fake_wp2"
base_seed = 11
max_workers = 2
data_root = "{root}"
baseline_cache = "{cache}"
replications = 2
deltas = [0.1, 0.2, 0.3]
baseline = "cpsat_det"

[baselines.cpsat_det]
deterministic_time_limit = 1.0
random_seed = 5

[scenarios]
lambda_a = [0.0, 0.05]
mean_absence = [3, 5]
lambda_s = 0.05
lambda_n = 0.05

[[sets]]
name = "tiny"
reference = "opt"
"""


@pytest.fixture
def fake_study(tmp_path: Path, tiny_path: Path) -> Path:
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
    text = FAKE_STUDY_CONFIG.format(root=root.as_posix(), cache=(tmp_path / "cache").as_posix())
    config.write_text(text, encoding="utf-8")
    return config
