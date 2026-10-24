"""The world and the runs of a cockpit (WP8; ADR-0021): one PSPLIB instance, replication and
absence rate lambda_A simulated under two policies on the same world seed (common random
numbers, spec section 2.3).

The world settings (base seed, PERT, E[L], lambda_S, lambda_N, T_r, T_cp, CP-SAT seed, budget
reserve beta, baseline plan) are those of `configs/wp5_rq4_main.toml`; replication r of an
instance uses the WP2b seed derive_seed(base_seed, set, instance, str(r)). The policies are the
WP4 baselines of the registry and the Sentinel variants of the three WP5 study configs with their
parameters, so that the cockpit of a study's world reproduces that study's row. Every Sentinel
works towards the cockpit's deadline D(delta_D); a baseline runs with the day limit of the
studies' largest slack, and on time is judged against D(delta_D) for both, as in the studies.
Each realised schedule is checked (`check_run`, CLAUDE.md invariant 6).

For its forecasts the cockpit keeps the observation Sentinel saw at each epoch (before its
decision), and repeats NOOP's rollouts of every deliberation on the agent's own worlds:
seed derive_seed(run seed, "sentinel", str(t)), the rollout count the agent used, so the
forecast P(C <= D) equals the record's (checked). A policy without forecasts gets the same
estimate every T_r days, from the observation after its decision, on N rollouts.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from sentinel.agent.candidates import noop
from sentinel.agent.decide import DecisionRecord
from sentinel.agent.evaluate import Evaluator
from sentinel.agent.params import SentinelParams
from sentinel.data.psplib_loader import instance_path, load_psplib
from sentinel.data.reference import ReferenceKind, load_reference, reference_path
from sentinel.experiments.policy_config import PolicyStudyConfig
from sentinel.experiments.policy_runs import SentinelVariant, check_run, optional_set, run_policy
from sentinel.experiments.runs import derive_seed, load_toml
from sentinel.model import ProjectInstance
from sentinel.policies.base import Decision, DecisionStats, Policy
from sentinel.policies.registry import COMPARED
from sentinel.policies.sentinel import Sentinel
from sentinel.simulation.baselines import BaselinePlan, cached_baseline
from sentinel.simulation.engine import SimulationResult, simulate
from sentinel.simulation.events import DisruptionParams
from sentinel.simulation.state import Observation, day_limit
from sentinel.simulation.uncertainty import derive_budget, derive_deadline

WORLD_CONFIG = Path("configs/wp5_rq4_main.toml")
WP5_CONFIGS = (
    WORLD_CONFIG,
    Path("configs/wp5_rq4_ablation.toml"),
    Path("configs/wp5_rq4_autonomy.toml"),
)
WP4_POLICIES = (*COMPARED, "stable_resolve")
REFERENCES: tuple[ReferenceKind, ...] = ("opt", "hrs")  # C* of a set the config does not list
DEFAULT_DELTA = 0.2


class CockpitError(ValueError):
    """The cockpit cannot be built as asked (unknown policy, missing data or reference)."""


@dataclass(frozen=True)
class Catalogue:
    """The world settings and the policies a cockpit can run: the WP4 baselines by registry
    name and the WP5 Sentinel variants by study name."""

    world: PolicyStudyConfig
    variants: Mapping[str, SentinelVariant]

    @property
    def names(self) -> tuple[str, ...]:
        return (*WP4_POLICIES, *self.variants)

    def variant(self, name: str) -> SentinelVariant | None:
        """The Sentinel variant of `name`, None for a baseline; unknown names raise."""
        if name in self.variants:
            return self.variants[name]
        if name in WP4_POLICIES:
            return None
        raise CockpitError(f"unknown policy {name!r}; known: {', '.join(self.names)}")


def load_catalogue(configs: Sequence[Path] = WP5_CONFIGS) -> Catalogue:
    """The world of the first config and the Sentinel variants of all of them (a name defined
    twice must have the same parameters)."""
    studies = [PolicyStudyConfig.model_validate(load_toml(path)) for path in configs]
    variants: dict[str, SentinelVariant] = {}
    for study in studies:
        for name, variant in study.sentinel_variants.items():
            if variants.setdefault(name, variant) != variant:
                raise CockpitError(f"variant {name!r} has different parameters in two configs")
    return Catalogue(studies[0], variants)


@dataclass(frozen=True)
class World:
    """One instance, replication and scenario with its baseline plan, C*, deadline D(delta_D)
    and budget B (spec sections 1.2, 2.3)."""

    set_name: str
    stem: str
    replication: int
    seed: int
    lambda_a: float
    disruptions: DisruptionParams
    instance: ProjectInstance
    plan: BaselinePlan
    c_star: int
    reference: ReferenceKind
    delta_d: float
    deadline: int
    budget: float
    config: PolicyStudyConfig

    @property
    def name(self) -> str:
        return f"{self.set_name}/{self.stem}"


def build_world(
    catalogue: Catalogue,
    set_name: str,
    stem: str,
    *,
    replication: int = 0,
    lambda_a: float = 0.01,
    delta_d: float | None = None,
    policies: Sequence[str] = (),
    root: Path | None = None,
    cache: Path | None = None,
) -> World:
    """The world of an instance; delta_D defaults to that of the first Sentinel variant among
    `policies`, else 0.2. The baseline plan comes from the cache (computed if missing)."""
    config = catalogue.world
    if replication < 0:
        raise CockpitError(f"replication must be non-negative, got {replication}")
    if not 0 <= lambda_a <= 1:
        raise CockpitError(f"lambda_A must be a probability, got {lambda_a}")
    data_root = config.data_root if root is None else root
    path = instance_path(set_name, stem, data_root)
    if not path.is_file():
        raise CockpitError(f"{path} not found; run scripts/fetch_psplib.py")
    instance = load_psplib(path)
    c_star, reference = _reference(config, set_name, stem, data_root)
    if delta_d is None:
        own = [v.delta_d for v in map(catalogue.variant, policies) if v is not None]
        delta_d = own[0] if own else DEFAULT_DELTA
    grid = config.scenarios
    disruptions = DisruptionParams(
        lambda_a=lambda_a,
        mean_absence=grid.mean_absence[0],
        lambda_s=grid.lambda_s,
        lambda_n=grid.lambda_n,
    )
    method = config.baseline_method
    plan = cached_baseline(instance, method, config.baseline_cache if cache is None else cache)[0]
    return World(
        set_name=set_name,
        stem=stem,
        replication=replication,
        seed=derive_seed(config.base_seed, set_name, stem, str(replication)),
        lambda_a=lambda_a,
        disruptions=disruptions,
        instance=instance,
        plan=plan,
        c_star=c_star,
        reference=reference,
        delta_d=delta_d,
        deadline=derive_deadline(c_star, delta_d),
        budget=derive_budget(instance, config.beta, params=config.pert),
        config=config,
    )


def _reference(
    config: PolicyStudyConfig, set_name: str, stem: str, root: Path
) -> tuple[int, ReferenceKind]:
    """C* of the instance: the reference of its set in the config, else the first file found."""
    listed = [s.reference for s in config.sets if s.name == set_name]
    for kind in listed or REFERENCES:
        if reference_path(set_name, kind, root).is_file():
            value = load_reference(set_name, kind, root).get(f"{set_name}/{stem}")
            if value is not None and value > 0:
                return value, kind
    raise CockpitError(f"no reference makespan for {set_name}/{stem} in {root / 'solutions'}")


class Observed:
    """A policy that keeps the observation of every epoch it is consulted at (step 3 of spec
    section 3, before its decision) and passes on its requested epochs (approval days)."""

    def __init__(self, policy: Policy) -> None:
        self.policy = policy
        self.observations: dict[int, Observation] = {}
        self.requested_epoch: int | None = None

    def decide(self, observation: Observation) -> Decision:
        self.observations[observation.day] = observation
        decision = self.policy.decide(observation)
        self.requested_epoch = getattr(self.policy, "requested_epoch", None)
        return decision


@dataclass(frozen=True)
class PolicyRun:
    """One checked run: the result, the decision statistics, Sentinel's records (none for a
    baseline), the observations kept (before Sentinel's decisions; after a baseline's, every
    T_r days), the parameters of the forecasts and the run's simulation deadline."""

    name: str
    variant: SentinelVariant | None
    result: SimulationResult
    stats: DecisionStats
    records: tuple[DecisionRecord, ...]
    observations: Mapping[int, Observation]
    params: SentinelParams
    sim_deadline: int

    @property
    def is_sentinel(self) -> bool:
        return self.variant is not None


def run(world: World, catalogue: Catalogue, name: str) -> PolicyRun:
    """Simulate policy `name` on the world (debug mode) and check the realised schedule."""
    config = world.config
    variant = catalogue.variant(name)
    if variant is not None:
        variant = variant.model_copy(update={"delta_d": world.delta_d})
        sim_deadline = world.deadline
    else:
        sim_deadline = derive_deadline(world.c_star, max(world.delta_d, *config.deltas))
    policy = run_policy(
        name,
        variant,
        deterministic_time_limit=config.deterministic_time_limit,
        cp_seed=config.cp_seed,
        run_seed=world.seed,
    )
    observed = Observed(policy) if isinstance(policy, Sentinel) else None
    periodic = range(0, day_limit(world.instance, sim_deadline) + 1, config.review_period)
    result = simulate(
        world.instance,
        world.plan.schedule,
        policy if observed is None else observed,
        world.seed,
        pert=config.pert,
        disruptions=world.disruptions,
        deadline=sim_deadline,
        review_period=config.review_period,
        observe_days=() if observed is not None else periodic,
        debug=True,
        budget=world.budget,
        optional=optional_set(world.instance, variant),
    )
    check_run(world.instance, result, f"{world.name}, {name}, seed {world.seed}")
    stats = getattr(policy, "stats", None)
    if observed is not None and isinstance(policy, Sentinel):
        records: tuple[DecisionRecord, ...] = tuple(policy.records)
        observations: Mapping[int, Observation] = observed.observations
        params = policy.params
    else:
        records = ()
        observations = {o.day: o for o in result.observations}
        params = SentinelParams.model_validate(config.sentinel)
    return PolicyRun(
        name=name,
        variant=variant,
        result=result,
        stats=stats if isinstance(stats, DecisionStats) else DecisionStats(),
        records=records,
        observations=observations,
        params=params,
        sim_deadline=sim_deadline,
    )


@dataclass(frozen=True)
class Forecast:
    """The forecast of one day: NOOP's P(C <= D) and makespan quantiles P10, P50, P90 on
    `rollouts` rollouts (a rollout cut at max_days counts C = max_days), and at a deliberation
    the chosen candidate with its p and what the permission gate did (None for NOOP)."""

    day: int
    rollouts: int
    p_on_time: float
    p10: float
    p50: float
    p90: float
    chosen: str | None = None
    p_chosen: float | None = None
    gate: str | None = None


def forecasts(world: World, policy_run: PolicyRun) -> list[Forecast]:
    """Sentinel: NOOP's rollouts of every deliberation, repeated on the agent's worlds with its
    rollout count, so P(C <= D) equals the record's (else RuntimeError). Other policies: NOOP
    every T_r days from the observation after the decision, on N rollouts of the same seeds."""
    found: list[Forecast] = []
    if policy_run.is_sentinel:
        for record in policy_run.records:
            if not record.deliberated or record.needs is None:
                continue
            noop_record = next((c for c in record.candidates if c.label == "NOOP"), None)
            n = record.needs.rollouts if noop_record is None else noop_record.rollouts
            expected = record.needs.p_on_time if noop_record is None else noop_record.p_on_time
            chosen = next((c for c in record.candidates if c.label == record.chosen), None)
            forecast = _noop_forecast(world, policy_run, record.day, n)
            if abs(forecast.p_on_time - expected) > 1e-12:
                raise RuntimeError(
                    f"the forecast of day {record.day} gives P(on time) {forecast.p_on_time}, "
                    f"the agent's record {expected}"
                )
            if record.chosen != "NOOP":
                p_chosen = None if chosen is None else chosen.p_on_time
                forecast = replace(
                    forecast, chosen=record.chosen, p_chosen=p_chosen, gate=record.gate
                )
            found.append(forecast)
        return found
    for day in sorted(policy_run.observations):
        found.append(_noop_forecast(world, policy_run, day, policy_run.params.n_rollouts))
    return found


def _noop_forecast(world: World, policy_run: PolicyRun, day: int, n: int) -> Forecast:
    observation = policy_run.observations[day]
    seed = derive_seed(world.seed, "sentinel", str(day))
    evaluator = Evaluator(observation, seed, policy_run.params)
    makespans = evaluator.extend(noop(observation), n).makespan[:n]
    # A rollout cut at max_days has C = max_days = ceil(5 D') > D, so C <= D decides on time.
    on_time = sum(c <= world.deadline for c in makespans)
    p10, p50, p90 = (float(q) for q in np.quantile(np.asarray(makespans), [0.1, 0.5, 0.9]))
    return Forecast(day, n, on_time / n, p10, p50, p90)
