"""SGS and CP-SAT on the downloaded PSPLIB J30 data; skipped when data/psplib is absent."""

import math
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pytest

from sentinel.data.psplib_loader import instance_path, list_instances, load_psplib
from sentinel.data.reference import load_reference, reference_path
from sentinel.model import validate_schedule
from sentinel.scheduling.cpsat import solve_cpsat
from sentinel.scheduling.priority_rules import lft_priorities
from sentinel.scheduling.sgs import serial_sgs

pytestmark = pytest.mark.data


@pytest.fixture(scope="module")
def j30_optima(psplib_root: Path) -> dict[str, int]:
    if (
        not (psplib_root / "j30").is_dir()
        or not reference_path("j30", "opt", psplib_root).is_file()
    ):
        pytest.skip("J30 instances or j30_opt.sm missing; run scripts/fetch_psplib.py")
    return load_reference("j30", "opt", psplib_root)


def test_sgs_lft_is_feasible_on_all_j30_instances(
    psplib_root: Path, j30_optima: dict[str, int]
) -> None:
    stems = list_instances("j30", psplib_root)
    assert len(stems) == 480
    for stem in stems:
        inst = load_psplib(instance_path("j30", stem, psplib_root))
        schedule = serial_sgs(inst, lft_priorities(inst), lower_is_better=True)
        assert validate_schedule(inst, schedule) == [], inst.name
        assert schedule.makespan(inst) >= j30_optima[inst.name], inst.name


def test_cpsat_reaches_the_optimum_of_j301_1(psplib_root: Path, j30_optima: dict[str, int]) -> None:
    inst = load_psplib(instance_path("j30", "j301_1", psplib_root))
    result = solve_cpsat(inst, time_limit_s=10, num_workers=1, random_seed=0)
    assert result.status == "OPTIMAL"
    assert result.makespan == j30_optima["j30/j301_1"] == 43
    assert result.schedule is not None
    assert validate_schedule(inst, result.schedule) == []


def _solve_j6013_1(root: Path) -> tuple[str, tuple[int, ...] | None]:
    inst = load_psplib(instance_path("j60", "j6013_1", root))
    result = solve_cpsat(
        inst, time_limit_s=math.inf, random_seed=2026, deterministic_time_limit=0.5
    )
    return result.status, None if result.schedule is None else result.schedule.starts


@pytest.mark.slow  # about 5 s
def test_deterministic_limit_does_not_depend_on_machine_load(psplib_root: Path) -> None:
    # j6013_1 is not solved to optimality within the limit, so the limit stops the search.
    if not (psplib_root / "j60").is_dir():
        pytest.skip("J60 instances missing; run scripts/fetch_psplib.py")
    alone = _solve_j6013_1(psplib_root)
    assert alone[0] == "FEASIBLE"
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=3, mp_context=context) as pool:
        loaded = list(pool.map(_solve_j6013_1, [psplib_root] * 3))  # three solves at once
    assert loaded == [alone] * 3
