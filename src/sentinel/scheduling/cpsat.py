"""CP-SAT models (Perron & Didier, Google OR-Tools): the exact minimum-makespan RCPSP and the
residual problem of a running project (spec section 4.1), for minimum makespan or for minimum
deviation from the current plan (Van de Vonder et al. 2007)."""

import math
import time
from collections.abc import Mapping, Sequence
from itertools import pairwise
from typing import Literal

from ortools.sat.python import cp_model
from pydantic import BaseModel, ConfigDict, NonNegativeFloat, NonNegativeInt

from sentinel.model.instance import ProjectInstance
from sentinel.model.schedule import Schedule
from sentinel.scheduling.priority_rules import lft_priorities
from sentinel.scheduling.residual import ResidualProblem, residual_sgs, validate_residual
from sentinel.scheduling.sgs import serial_sgs

SolveStatus = Literal["OPTIMAL", "FEASIBLE", "INFEASIBLE", "UNKNOWN"]
Objective = Literal["makespan", "stable"]  # of the residual problem (spec section 7)

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


class ResidualSolution(BaseModel):
    """Planned starts for a residual problem (spec sections 4.1 and 7), by activity id.

    `status` is CP-SAT's for the last stage it searched. A stage without a solution within its
    limit falls back (`fallbacks` counts the stages, `fallback` says whether any did): stage 1
    to the residual SGS with LFT priority, stage 2 of "stable" to the stage-1 solution.
    `objective` is the makespan, or for "stable" the deviation sum |S_j - S_j^t| from the
    current plan. `deterministic_time` adds up the CP-SAT stages; `wall_time_s` covers the
    whole call.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: SolveStatus
    starts: dict[NonNegativeInt, NonNegativeInt]
    makespan: NonNegativeInt
    objective: NonNegativeInt
    fallback: bool
    fallbacks: NonNegativeInt
    deterministic_time: NonNegativeFloat
    wall_time_s: NonNegativeFloat


def solve_residual(
    problem: ResidualProblem,
    objective: Objective = "makespan",
    *,
    deterministic_time_limit: float,
    seed: int,
    hint: Mapping[int, int] | None = None,
) -> ResidualSolution:
    """Solve the residual problem with CP-SAT (spec sections 4.1 and 7).

    One interval per activity of positive duration, a cumulative per role with capacity R_k in
    which fixed intervals take away the unavailable units of each capacity step, and every start
    in [release, H] for H = the makespan of the residual SGS with LFT priority, a valid bound.
    Stage 1 minimises the makespan (the sink's start) C_1; "stable" then minimises
    sum_j |S_j - S_j^t| over the residual activities subject to makespan <= C_1. Each stage runs
    with one worker, `seed` and `deterministic_time_limit` (no wall-clock limit), so the result
    does not depend on machine load. The hint is `hint` (the current plan) if it is a feasible
    solution within H, else the SGS schedule; stage 2 is hinted with the stage-1 solution.
    """
    began = time.perf_counter()
    sgs = residual_sgs(problem)
    horizon = sgs[problem.sink]
    if hint is not None and not validate_residual(problem, hint) and hint[problem.sink] <= horizon:
        first_hint: Mapping[int, int] = hint
    else:
        first_hint = sgs
    model, starts = _model(problem, horizon)
    sink = problem.activities.index(problem.sink)
    model.minimize(starts[sink])
    ids = problem.activities
    status, values, effort = _search(model, ids, starts, first_hint, deterministic_time_limit, seed)
    fallbacks = 0
    if values is None:
        values, fallbacks = sgs, 1
    makespan = values[problem.sink]
    value = makespan
    if objective == "stable":
        planned = problem.planned
        model, starts = _model(problem, horizon)
        model.add(starts[sink] <= makespan)
        deviations = []
        for i, (start, target) in enumerate(zip(starts, planned, strict=True)):
            deviation = model.new_int_var(0, horizon + abs(target), f"D{ids[i]}")
            model.add(deviation >= start - target)
            model.add(deviation >= target - start)
            deviations.append(deviation)
        model.minimize(sum(deviations))
        status, second, more = _search(model, ids, starts, values, deterministic_time_limit, seed)
        effort += more
        if second is None:
            fallbacks += 1
        else:
            values = second
        makespan = values[problem.sink]
        value = sum(abs(values[j] - target) for j, target in zip(ids, planned, strict=True))
    return ResidualSolution(
        status=status,
        starts=dict(values),
        makespan=makespan,
        objective=value,
        fallback=fallbacks > 0,
        fallbacks=fallbacks,
        deterministic_time=effort,
        wall_time_s=time.perf_counter() - began,
    )


def _model(
    problem: ResidualProblem, horizon: int
) -> tuple[cp_model.CpModel, list[cp_model.IntVar]]:
    """Starts, precedences and the cumulative per role with the capacity profile as fixed
    intervals."""
    model = cp_model.CpModel()
    ids, durations = problem.activities, problem.durations
    starts = [
        model.new_int_var(release, horizon, f"S{j}")
        for j, release in zip(ids, problem.releases(), strict=True)
    ]
    for i, succ in enumerate(problem.successors):
        for q in succ:
            model.add(starts[q] >= starts[i] + durations[i])
    intervals = {
        i: model.new_fixed_size_interval_var(starts[i], p, f"I{ids[i]}")
        for i, p in enumerate(durations)
        if p > 0
    }
    for k, (steps, capacity) in enumerate(zip(problem.profile, problem.capacities, strict=True)):
        users = [i for i in intervals if problem.demands[i][k] > 0]
        if not users:
            continue
        busy = [intervals[i] for i in users]
        demands = [problem.demands[i][k] for i in users]
        for (start, level), (end, _) in pairwise(steps):
            if level < capacity:  # the last step equals the capacity
                busy.append(model.new_fixed_size_interval_var(start, end - start, f"R{k}_{start}"))
                demands.append(capacity - level)
        model.add_cumulative(busy, demands, capacity)
    return model, starts


def _search(
    model: cp_model.CpModel,
    ids: Sequence[int],
    starts: list[cp_model.IntVar],
    hint: Mapping[int, int],
    deterministic_time_limit: float,
    seed: int,
) -> tuple[SolveStatus, dict[int, int] | None, float]:
    """One CP-SAT search from the hint: (status, starts by id or None, deterministic time)."""
    for j, var in zip(ids, starts, strict=True):
        model.add_hint(var, hint[j])
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1
    solver.parameters.random_seed = seed
    solver.parameters.max_deterministic_time = deterministic_time_limit
    solver.parameters.max_time_in_seconds = math.inf  # only the deterministic limit may stop it
    code = solver.solve(model)
    status = _STATUSES.get(code)
    if status is None:
        raise RuntimeError(f"CP-SAT returned {solver.status_name(code)}: {model.validate()}")
    if status not in ("OPTIMAL", "FEASIBLE"):
        return status, None, solver.deterministic_time
    values = {j: solver.value(var) for j, var in zip(ids, starts, strict=True)}
    return status, values, solver.deterministic_time
