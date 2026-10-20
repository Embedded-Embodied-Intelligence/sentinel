"""PSPLIB loading (spec section 1.1), paths and natural ordering of instance names."""

from pathlib import Path

import pytest

from sentinel.data.psplib_loader import instance_path, list_instances, load_psplib, natural_key
from sentinel.model import ProjectInstance

Job = tuple[list[int], list[tuple[int, list[int]]]]  # (1-based successors, [(duration, demands)])


def psplib_text(jobs: list[Job], kinds: list[str], capacities: list[int]) -> str:
    """Minimal PSPLIB-format file with the sections that psplib.parse reads."""
    resources = "  ".join(f"{kind} {i + 1}" for i, kind in enumerate(kinds))
    lines = ["PRECEDENCE RELATIONS:", "jobnr. #modes #successors successors"]
    for j, (successors, modes) in enumerate(jobs, start=1):
        lines.append(" ".join(map(str, [j, len(modes), len(successors), *successors])))
    lines += ["*" * 72, "REQUESTS/DURATIONS:", f"jobnr. mode duration {resources}", "-" * 72]
    for j, (_, modes) in enumerate(jobs, start=1):
        for m, (duration, demands) in enumerate(modes, start=1):
            job = [j] if m == 1 else []  # PSPLIB omits the job number on further mode lines
            lines.append(" ".join(map(str, [*job, m, duration, *demands])))
    lines += ["*" * 72, "RESOURCEAVAILABILITIES:", resources, " ".join(map(str, capacities))]
    return "\n".join([*lines, "*" * 72]) + "\n"


def test_tiny_maps_to_project_instance(tiny: ProjectInstance) -> None:
    assert tiny.name == "fixtures/tiny"
    assert tiny.source == "psplib"
    assert [a.successors for a in tiny.activities] == [(1, 2), (3,), (4,), (4,), ()]
    assert [a.demands for a in tiny.activities] == [(0,), (2,), (2,), (1,), (0,)]
    assert [w.name for w in tiny.workers] == ["R1-0", "R1-1", "R1-2"]


def test_name_override(tiny_path: Path) -> None:
    assert load_psplib(tiny_path, name="custom/tiny").name == "custom/tiny"


def test_loads_several_renewable_resources(tmp_path: Path) -> None:
    jobs: list[Job] = [([2], [(0, [0, 0])]), ([3], [(4, [2, 1])]), ([], [(0, [0, 0])])]
    path = tmp_path / "set" / "two_roles.sm"
    path.parent.mkdir()
    path.write_text(psplib_text(jobs, ["R", "R"], [3, 2]))
    inst = load_psplib(path)
    assert inst.name == "set/two_roles"
    assert [(r.name, r.capacity) for r in inst.roles] == [("R1", 3), ("R2", 2)]
    assert [w.role for w in inst.workers] == [0, 0, 0, 1, 1]
    assert inst.activities[1].demands == (2, 1)


def test_rejects_multi_mode(tmp_path: Path) -> None:
    jobs: list[Job] = [([2], [(0, [0])]), ([3], [(3, [2]), (2, [3])]), ([], [(0, [0])])]
    path = tmp_path / "multi.sm"
    path.write_text(psplib_text(jobs, ["R"], [3]))
    with pytest.raises(ValueError, match=r"activities \[1\] do not have exactly one mode"):
        load_psplib(path)


def test_rejects_nonrenewable_resource(tmp_path: Path) -> None:
    jobs: list[Job] = [([2], [(0, [0, 0])]), ([3], [(3, [2, 4])]), ([], [(0, [0, 0])])]
    path = tmp_path / "nonrenewable.sm"
    path.write_text(psplib_text(jobs, ["R", "N"], [3, 10]))
    with pytest.raises(ValueError, match=r"non-renewable resources \[1\]"):
        load_psplib(path)


def test_instance_path() -> None:
    assert instance_path("j30", "j301_1", "root") == Path("root/j30/j301_1.sm")


def test_list_instances_natural_order(tmp_path: Path) -> None:
    (tmp_path / "j30").mkdir()
    for stem in ["j3010_1", "j301_10", "j302_1", "j301_2", "j309_10", "j301_1"]:
        (tmp_path / "j30" / f"{stem}.sm").write_text("")
    (tmp_path / "j30" / "README.txt").write_text("")
    assert list_instances("j30", tmp_path) == [
        "j301_1",
        "j301_2",
        "j301_10",
        "j302_1",
        "j309_10",
        "j3010_1",
    ]


def test_list_instances_missing_set(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match=r"fetch_psplib\.py"):
        list_instances("j30", tmp_path)


def test_natural_key() -> None:
    assert sorted(["a10", "a9", "b1", "a10_2"], key=natural_key) == ["a9", "a10", "a10_2", "b1"]
