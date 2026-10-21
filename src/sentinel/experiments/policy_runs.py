"""Checked runs of the compared policies on one PSPLIB instance (WP4a; spec sections 7, 7.1).

`run_policies` takes the instance's cached baseline plan (computing and storing it if missing)
and simulates every (replication, policy) with `run_checked`: in debug mode, so a RESEQ plan
that fails `validate_residual` raises, and with every realised schedule checked (spec sections
1.3, 3.1 and 4), a violation raising `InvalidScheduleError`. The seed of (instance, replication
r) is the WP2b one, derive_seed(base_seed, set, instance, str(r)), shared by all policies
(common random numbers, spec section 2.3), so the NoReaction runs are WP2b's worlds. A run uses
max_days of the largest deadline slack; whether each deadline is met is evaluated post hoc, as
in WP2b. Sentinel, which uses the deadline, gets the one of `PolicyTask.agent_delta` (and its
max_days); its on-time flags for the other slacks are post hoc.
"""

import time
from dataclasses import dataclass, field
from pathlib import Path

from sentinel.agent.params import SentinelParams
from sentinel.data.psplib_loader import DEFAULT_ROOT, instance_path, load_psplib
from sentinel.model import ProjectInstance, Schedule, validate_schedule
from sentinel.policies.base import DecisionStats
from sentinel.policies.registry import SENTINELS, make_policy
from sentinel.policies.resolve import T_CP
from sentinel.simulation.baselines import DEFAULT_CACHE_ROOT, CpsatDet, cached_baseline
from sentinel.simulation.engine import SimulationResult, simulate
from sentinel.simulation.events import DisruptionParams
from sentinel.simulation.realised import execution_violations, realised_instance
from sentinel.simulation.uncertainty import PertParams, derive_deadline

WP2B_BASELINE = CpsatDet(deterministic_time_limit=5.0, random_seed=2026)  # cpsat_det of WP2b


class InvalidScheduleError(RuntimeError):
    """A realised schedule violates spec sections 1.3, 3.1 or 4."""


@dataclass(frozen=True)
class PolicyTask:
    """One instance and its runs: every policy on every replication seed."""

    set_name: str
    stem: str
    c_star: int
    policies: tuple[str, ...]
    seeds: tuple[int, ...]
    disruptions: DisruptionParams
    deltas: tuple[float, ...] = (0.2, 0.3)
    pert: PertParams = field(default_factory=PertParams)
    review_period: int = 5
    deterministic_time_limit: float = T_CP
    baseline: CpsatDet = WP2B_BASELINE
    data_root: Path = DEFAULT_ROOT
    baseline_cache: Path = DEFAULT_CACHE_ROOT
    agent_delta: float = 0.2  # delta_D of the deadline Sentinel works towards
    sentinel: SentinelParams | None = None  # Sentinel's parameters (default: spec section 8)


@dataclass(frozen=True)
class PolicyRecord:
    """One checked run: the metrics of spec section 7.1, the policy's decision statistics
    (`DecisionStats`) and the wall time of the whole `simulate` call."""

    set_name: str
    instance: str
    policy: str
    replication: int
    seed: int
    c_star: int
    baseline_makespan: int
    makespan: int
    truncated: bool
    on_time: tuple[bool, ...]  # per deadline slack of the task
    total_cost: float
    deviation: float
    substituted: int
    onboarding_days: int
    handover_days: float
    reseqs: int
    nervousness: int
    rejected: int
    epochs: int
    stats: DecisionStats
    wall_time_s: float
    shifts: int = 0
    hired: int = 0
    overtime_cost: float = 0.0


def run_policies(task: PolicyTask) -> list[PolicyRecord]:
    """Simulate and check every (replication, policy) of one instance (in a worker process)."""
    instance = load_psplib(instance_path(task.set_name, task.stem, task.data_root))
    plan = cached_baseline(instance, task.baseline, task.baseline_cache)[0]
    violations = validate_schedule(instance, plan.schedule)
    if violations:
        raise InvalidScheduleError(f"baseline of {instance.name}: {violations[0].detail}")
    deadlines = [derive_deadline(task.c_star, delta) for delta in task.deltas]
    target = derive_deadline(task.c_star, task.agent_delta)
    records: list[PolicyRecord] = []
    for replication, seed in enumerate(task.seeds):
        for name in task.policies:
            result, stats, wall_time_s = run_checked(
                instance,
                plan.schedule,
                name,
                seed,
                pert=task.pert,
                disruptions=task.disruptions,
                # max_days of the largest delta_D, or Sentinel's own deadline
                deadline=target if name in SENTINELS else deadlines[-1],
                review_period=task.review_period,
                deterministic_time_limit=task.deterministic_time_limit,
                sentinel=task.sentinel,
            )
            records.append(
                PolicyRecord(
                    set_name=task.set_name,
                    instance=task.stem,
                    policy=name,
                    replication=replication,
                    seed=seed,
                    c_star=task.c_star,
                    baseline_makespan=plan.makespan,
                    makespan=result.makespan,
                    truncated=result.truncated,
                    on_time=tuple(
                        not result.truncated and result.makespan <= deadline
                        for deadline in deadlines
                    ),
                    total_cost=result.total_cost,
                    deviation=realised_deviation(result, plan.schedule, instance),
                    substituted=result.n_substituted,
                    onboarding_days=result.onboarding_days,
                    handover_days=result.handover_days,
                    reseqs=result.reseqs,
                    nervousness=result.nervousness,
                    rejected=len(result.rejected),
                    epochs=result.n_epochs,
                    stats=stats,
                    wall_time_s=wall_time_s,
                    shifts=result.shifts,
                    hired=result.hired,
                    overtime_cost=result.overtime_cost,
                )
            )
    return records


def run_checked(
    instance: ProjectInstance,
    plan: Schedule,
    policy_name: str,
    seed: int,
    *,
    pert: PertParams,
    disruptions: DisruptionParams,
    deadline: int,
    review_period: int,
    deterministic_time_limit: float,
    cp_seed: int = 0,
    sentinel: SentinelParams | None = None,
) -> tuple[SimulationResult, DecisionStats, float]:
    """One run of a fresh policy in debug mode with its realised schedule checked: the result,
    the policy's decision statistics (empty for NoReaction) and the wall time of `simulate`.
    Sentinel gets the run's seed and `sentinel` parameters (`make_policy`)."""
    policy = make_policy(
        policy_name,
        deterministic_time_limit=deterministic_time_limit,
        seed=cp_seed,
        run_seed=seed,
        sentinel=sentinel,
    )
    began = time.perf_counter()
    result = simulate(
        instance,
        plan,
        policy,
        seed,
        pert=pert,
        disruptions=disruptions,
        deadline=deadline,
        review_period=review_period,
        debug=True,
    )
    wall_time_s = time.perf_counter() - began
    check_run(instance, result, f"{instance.name}, {policy_name}, seed {seed}")
    stats = getattr(policy, "stats", None)
    return result, stats if isinstance(stats, DecisionStats) else DecisionStats(), wall_time_s


def check_run(instance: ProjectInstance, result: SimulationResult, where: str) -> None:
    """Raise on a realised schedule that violates spec 1.3 or the crew rules of 3.1 and 4."""
    problems = execution_violations(instance, result)
    if not result.truncated:  # a truncated run has no complete schedule to validate
        realised, schedule = realised_instance(instance, result)
        problems += [v.detail for v in validate_schedule(realised, schedule)]
    if problems:
        raise InvalidScheduleError(f"{where}: {len(problems)} violations, first: {problems[0]}")


def realised_deviation(
    result: SimulationResult, baseline: Schedule, instance: ProjectInstance
) -> float:
    """(1/|J+|) sum_{j in J+} |S_j^real - S_j^0| against the baseline plan (spec section 7.1).

    J+ holds the original activities with p_j > 0: the dummies, milestones and D3 activities are
    left out. An activity that a truncated run never started counts with S_j^real = max_days.
    """
    total = count = 0
    for act in instance.activities:
        if act.duration > 0:
            start = result.starts[act.id]
            total += abs((result.max_days if start is None else start) - baseline.starts[act.id])
            count += 1
    return total / count if count else 0.0
