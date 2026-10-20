"""Baseline plans that every policy starts from (WP2b), cached per instance on disk.

`cpsat_det` runs CP-SAT with one worker, a fixed seed and only a deterministic time limit, so
that the plan does not depend on machine load (ADR-0008); `sgs_lft` is one serial SGS pass with
the LFT rule (Kolisch 1996). Plans are cached in `<cache root>/<set>/<instance>.json` with one
entry per method. An entry is reused only if its method parameters, the instance content, the
cache version and, for CP-SAT, the OR-Tools version match; otherwise it is recomputed.
"""

import hashlib
import json
import math
import os
import platform
import tempfile
import time
from importlib import metadata
from pathlib import Path
from typing import Annotated, Any, Literal, assert_never

from pydantic import BaseModel, ConfigDict, Field, NonNegativeFloat, NonNegativeInt

from sentinel.model import ProjectInstance, Schedule, validate_schedule
from sentinel.scheduling.cpsat import SolveStatus, solve_cpsat
from sentinel.scheduling.priority_rules import lft_priorities
from sentinel.scheduling.sgs import serial_sgs

DEFAULT_CACHE_ROOT = Path("data/derived/baselines")
CACHE_VERSION = 1  # bump when the computation of a baseline plan changes
BaselineName = Literal["cpsat_det", "sgs_lft"]
BASELINE_NAMES: tuple[BaselineName, ...] = ("cpsat_det", "sgs_lft")


class CpsatDet(BaseModel):
    """CP-SAT with one worker, a fixed seed and a deterministic time limit (no wall clock)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["cpsat_det"] = "cpsat_det"
    deterministic_time_limit: float = Field(gt=0, allow_inf_nan=False)
    random_seed: NonNegativeInt = Field(lt=2**31)  # CP-SAT seeds are int32
    num_workers: Literal[1] = 1


class SgsLft(BaseModel):
    """One serial SGS pass with the LFT priority rule (Kolisch 1996)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["sgs_lft"] = "sgs_lft"


BaselineMethod = Annotated[CpsatDet | SgsLft, Field(discriminator="kind")]


class BaselinePlan(BaseModel):
    """A baseline plan with its provenance. `status` is CP-SAT's (OPTIMAL or FEASIBLE), FEASIBLE
    for SGS; `lower_bound` and `deterministic_time` exist for CP-SAT only."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    instance: str
    instance_sha256: str
    method: BaselineMethod
    schedule: Schedule
    makespan: NonNegativeInt
    status: SolveStatus
    lower_bound: NonNegativeInt | None
    deterministic_time: NonNegativeFloat | None
    runtime_s: NonNegativeFloat
    versions: dict[str, str | None]
    cache_version: int


class InvalidPlanError(RuntimeError):
    """A baseline method returned no plan or one that violates spec section 1.3."""


def instance_fingerprint(instance: ProjectInstance) -> str:
    """SHA-256 of the instance's JSON form; any change of the instance changes it."""
    return hashlib.sha256(instance.model_dump_json().encode("utf-8")).hexdigest()


def compute_baseline(instance: ProjectInstance, method: BaselineMethod) -> BaselinePlan:
    """Compute a baseline plan without the cache; it must pass `validate_schedule`."""
    started = time.perf_counter()
    lower_bound: int | None = None
    deterministic_time: float | None = None
    match method:
        case CpsatDet():
            result = solve_cpsat(
                instance,
                time_limit_s=math.inf,  # only the deterministic limit may stop the search
                num_workers=method.num_workers,
                random_seed=method.random_seed,
                deterministic_time_limit=method.deterministic_time_limit,
            )
            if result.schedule is None:
                raise InvalidPlanError(f"CP-SAT found no plan for {instance.name}: {result.status}")
            schedule, status = result.schedule, result.status
            lower_bound, deterministic_time = result.lower_bound, result.deterministic_time
        case SgsLft():
            schedule = serial_sgs(instance, lft_priorities(instance), lower_is_better=True)
            status = "FEASIBLE"
        case _:
            assert_never(method)
    runtime_s = time.perf_counter() - started
    violations = validate_schedule(instance, schedule)
    if violations:
        raise InvalidPlanError(
            f"{method.kind} plan of {instance.name}: {len(violations)} violations, "
            f"first: {violations[0].detail}"
        )
    return BaselinePlan(
        instance=instance.name,
        instance_sha256=instance_fingerprint(instance),
        method=method,
        schedule=schedule,
        makespan=schedule.makespan(instance),
        status=status,
        lower_bound=lower_bound,
        deterministic_time=deterministic_time,
        runtime_s=runtime_s,
        versions=_versions(),
        cache_version=CACHE_VERSION,
    )


def cache_path(instance_name: str, cache_root: Path = DEFAULT_CACHE_ROOT) -> Path:
    """Cache file of an instance, `<cache root>/<set>/<instance>.json` for `<set>/<instance>`."""
    relative = Path(f"{instance_name}.json")
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"instance name {instance_name!r} is not a relative path")
    return cache_root / relative


def read_cached(
    instance: ProjectInstance, method: BaselineMethod, cache_root: Path = DEFAULT_CACHE_ROOT
) -> BaselinePlan | None:
    """The cached plan of `method` if its entry is valid and current, else None."""
    raw = _read_entries(cache_path(instance.name, cache_root)).get(method.kind)
    if raw is None:
        return None
    try:
        plan = BaselinePlan.model_validate(raw)
    except ValueError:  # an entry from an incompatible format is recomputed
        return None
    current = (
        plan.method == method
        and plan.instance == instance.name
        and plan.instance_sha256 == instance_fingerprint(instance)
        and plan.cache_version == CACHE_VERSION
    )
    if isinstance(method, CpsatDet):
        current = current and plan.versions.get("ortools") == _package_version("ortools")
    return plan if current else None


def write_cached(plan: BaselinePlan, cache_root: Path = DEFAULT_CACHE_ROOT) -> Path:
    """Store `plan` under its method, keeping the other methods' entries; atomic replace."""
    path = cache_path(plan.instance, cache_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = _read_entries(path)
    entries[plan.method.kind] = plan.model_dump(mode="json")
    text = json.dumps(dict(sorted(entries.items())), indent=2) + "\n"
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}.", suffix=".tmp")
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        stream.write(text)
    os.replace(temporary, path)
    return path


def cached_baseline(
    instance: ProjectInstance, method: BaselineMethod, cache_root: Path = DEFAULT_CACHE_ROOT
) -> tuple[BaselinePlan, bool]:
    """(plan, True) from a valid cache entry, else (plan computed and stored now, False)."""
    plan = read_cached(instance, method, cache_root)
    if plan is not None:
        return plan, True
    plan = compute_baseline(instance, method)
    write_cached(plan, cache_root)
    return plan, False


def baseline_plan(
    instance: ProjectInstance,
    method: BaselineMethod,
    cache_root: Path | None = DEFAULT_CACHE_ROOT,
) -> BaselinePlan:
    """The baseline plan of `instance` by `method`; `cache_root=None` bypasses the cache."""
    if cache_root is None:
        return compute_baseline(instance, method)
    return cached_baseline(instance, method, cache_root)[0]


def _read_entries(path: Path) -> dict[str, Any]:
    """Entries of a cache file by method; a missing or unreadable file has none."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _versions() -> dict[str, str | None]:
    return {
        "python": platform.python_version(),
        "numpy": _package_version("numpy"),
        "ortools": _package_version("ortools"),
    }


def _package_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None
