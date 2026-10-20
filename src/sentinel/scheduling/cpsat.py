"""Exact minimum-makespan RCPSP model for OR-Tools CP-SAT (Perron & Didier, Google OR-Tools)."""

import math
import time
from typing import Literal

from ortools.sat.python import cp_model
from pydantic import BaseModel, ConfigDict

from sentinel.model.instance import ProjectInstance
from sentinel.model.schedule import Schedule
from sentinel.scheduling.priority_rules import lft_priorities
from sentinel.scheduling.sgs import serial_sgs

SolveStatus = Literal["OPTIMAL", "FEASIBLE", "INFEASIBLE", "UNKNOWN"]

_STATUSES: dict[cp_model.CpSolverStatus, SolveStatus] = {
    cp_model.OPTIMAL: "OPTIMAL",
    cp_model.FEASIBLE: "FEASIBLE",
    cp_model.INFEASIBLE: "INFEASIBLE",
    cp_model.UNKNOWN: "UNKNOWN",
}


class SolveResult(BaseModel):
    """Outcome of a solve; `lower_bound` is the best objective bound (None if infeasible) and
    `deterministic_time` the search effort in CP-SAT's machine-independent units."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: SolveStatus
    schedule: Schedule | None
    makespan: int | None
    lower_bound: int | None
    wall_time_s: float
    deterministic_time: float | None = None


def solve_cpsat(
    instance: ProjectInstance,
    *,
    time_limit_s: float,
    num_workers: int = 1,
    random_seed: int = 0,
    horizon: int | None = None,
    deterministic_time_limit: float | None = None,
) -> SolveResult:
    """Minimise the sink start with CP-SAT: one interval per activity, a cumulative per role.

    All start times lie in [0, horizon]; the default horizon is the makespan of the serial SGS
    with the LFT rule, a valid upper bound. No solution hints are given. `wall_time_s` covers
    the whole call (horizon, model building and search). `deterministic_time_limit` also sets
    CP-SAT's `max_deterministic_time`, a limit in machine-independent work units: with one
    worker and a fixed seed, a search stopped by it returns the same schedule whatever the
    machine load, provided the wall-clock limit does not stop it first (`math.inf` disables
    that limit).
    """
    started = time.perf_counter()
    if horizon is None:
        lft = lft_priorities(instance)
        horizon = serial_sgs(instance, lft, lower_is_better=True).makespan(instance)
    acts = instance.activities
    model = cp_model.CpModel()
    starts = [model.new_int_var(0, horizon, f"S{j}") for j in range(len(acts))]
    intervals = [
        model.new_fixed_size_interval_var(starts[j], act.duration, f"I{j}")
        for j, act in enumerate(acts)
    ]
    model.add(starts[instance.source_id] == 0)
    for i, act in enumerate(acts):
        for j in act.successors:
            model.add(starts[j] >= starts[i] + act.duration)
    for role in instance.roles:
        # Zero-duration activities occupy no day (spec section 1.3), so they are left out.
        users = [j for j, act in enumerate(acts) if act.duration > 0 and act.demands[role.id] > 0]
        if users:
            model.add_cumulative(
                [intervals[j] for j in users],
                [acts[j].demands[role.id] for j in users],
                role.capacity,
            )
    model.minimize(starts[instance.sink_id])

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    if deterministic_time_limit is not None:
        solver.parameters.max_deterministic_time = deterministic_time_limit
    solver.parameters.num_workers = num_workers
    solver.parameters.random_seed = random_seed
    code = solver.solve(model)
    status = _STATUSES.get(code)
    if status is None:
        raise RuntimeError(
            f"CP-SAT returned {solver.status_name(code)} on {instance.name}: {model.validate()}"
        )
    schedule = None
    if status in ("OPTIMAL", "FEASIBLE"):
        schedule = Schedule(starts=tuple(solver.value(start) for start in starts))
    # The objective is integral, so its bound is an integer up to floating-point noise.
    bound = None if status == "INFEASIBLE" else math.ceil(solver.best_objective_bound - 1e-6)
    return SolveResult(
        status=status,
        schedule=schedule,
        makespan=None if schedule is None else schedule.makespan(instance),
        lower_bound=bound,
        wall_time_s=time.perf_counter() - started,
        deterministic_time=solver.deterministic_time,
    )
