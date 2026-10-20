"""PSPLIB single-mode instances as ProjectInstance (spec section 1.1; Kolisch & Sprecher 1997)."""

import re
from pathlib import Path

import psplib

from sentinel.model.instance import Activity, ProjectInstance, Role, make_workers

DEFAULT_ROOT = Path("data/psplib")
FETCH_HINT = "run `uv run python scripts/fetch_psplib.py --sets j30 j60`"


def load_psplib(path: str | Path, name: str | None = None) -> ProjectInstance:
    """Load a PSPLIB .sm file; multi-mode activities and non-renewable resources are rejected.

    The default name is `<parent dir>/<file stem>`, e.g. `j30/j301_1` for
    `data/psplib/j30/j301_1.sm`. Roles are named R1..R|K| with one worker per capacity unit.
    """
    path = Path(path)
    parsed = psplib.parse(path, instance_format="psplib")
    if len(parsed.projects) != 1:
        raise ValueError(f"{path}: {len(parsed.projects)} projects; expected exactly one")
    nonrenewable = [k for k, res in enumerate(parsed.resources) if not res.renewable]
    if nonrenewable:
        raise ValueError(
            f"{path}: non-renewable resources {nonrenewable} are not supported "
            "(only renewable resources, i.e. roles)"
        )
    multi_mode = [j for j, act in enumerate(parsed.activities) if len(act.modes) != 1]
    if multi_mode:
        raise ValueError(
            f"{path}: activities {multi_mode} do not have exactly one mode "
            "(only single-mode instances are supported)"
        )
    roles = tuple(
        Role(id=k, name=f"R{k + 1}", capacity=int(res.capacity))
        for k, res in enumerate(parsed.resources)
    )
    activities = tuple(
        Activity(
            id=j,
            duration=int(act.modes[0].duration),
            demands=tuple(int(d) for d in act.modes[0].demands),
            successors=tuple(int(s) for s in act.successors),
        )
        for j, act in enumerate(parsed.activities)
    )
    return ProjectInstance(
        name=name or f"{path.resolve().parent.name}/{path.stem}",
        activities=activities,
        roles=roles,
        workers=make_workers(roles),
        source="psplib",
    )


def instance_path(set_name: str, instance: str, root: str | Path = DEFAULT_ROOT) -> Path:
    """Path of an instance file, `<root>/<set>/<instance>.sm`."""
    return Path(root) / set_name / f"{instance}.sm"


def list_instances(set_name: str, root: str | Path = DEFAULT_ROOT) -> list[str]:
    """Instance names of a set in natural order: j301_1, j301_2, ..., j301_10, j302_1, ..."""
    directory = Path(root) / set_name
    if not directory.is_dir():
        raise FileNotFoundError(f"{directory} not found; {FETCH_HINT}")
    return sorted((p.stem for p in directory.glob("*.sm")), key=natural_key)


def natural_key(text: str) -> tuple[str | int, ...]:
    """Sort key comparing digit runs as integers ("j3010_1" sorts after "j309_10")."""
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", text))
