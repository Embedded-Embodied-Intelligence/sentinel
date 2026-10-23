"""Decision states of RQ5 (WP6b): Sentinel's deliberations that passed the needs gate, recorded
from reruns of WP5 worlds, and the stratified sample the proposal and explanation studies use.

`record_run` reruns Sentinel `full` (Lambda = 3) on one world of the WP5 main study (instance,
lambda_A, replication, the WP2b seed, the cpsat_det baseline plan, D for delta_D = 0.2, B with
beta = 0.1) and keeps every deliberation whose NOOP showed a need (`needs.met` false): the
observation (with its plan), the `DecisionRecord` of the rule candidates and the run's seed,
from which the deliberation is reproduced exactly (`redeliberate`). Every realised schedule is
checked (`policy_runs.check_run`). States are stored as gzip JSON lines, one file per run, under
`data/derived/decision_states/` (gitignored; reproducible from the seeds), with an index.
`stratified_sample` draws the study sample by lambda_A, project-progress tercile and whether the
rule chose NOOP, in equal shares per stratum where the strata are large enough.
"""

import csv
import gzip
import io
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveInt

from sentinel.agent.decide import DecisionRecord
from sentinel.agent.params import SentinelParams
from sentinel.data.psplib_loader import instance_path, list_instances, load_psplib, natural_key
from sentinel.data.reference import ReferenceKind, load_reference
from sentinel.experiments.policy_runs import InvalidScheduleError, check_run
from sentinel.experiments.runs import derive_seed, load_toml
from sentinel.model import ProjectInstance, Schedule, validate_schedule
from sentinel.policies.sentinel import Sentinel
from sentinel.simulation.baselines import CpsatDet, cached_baseline
from sentinel.simulation.engine import SimulationResult, simulate
from sentinel.simulation.events import DisruptionParams
from sentinel.simulation.state import DONE, REMOVED, UNSTARTED, Observation, nominal_activity
from sentinel.simulation.uncertainty import PertParams, derive_budget, derive_deadline

INDEX_FILE = "index.csv"
INDEX_COLUMNS = (
    "id",
    "set",
    "instance",
    "lambda_a",
    "replication",
    "seed",
    "day",
    "progress",
    "chosen",
    "kind",
    "reason",
    "noop",
    "n_candidates",
    "file",
)
TIMING_FIELDS = frozenset({"generation_s", "evaluation_s", "wall_time_s"})


class DecisionState(BaseModel):
    """One recorded deliberation: where it comes from (set, instance, lambda_A, replication,
    the run's seed), its day, the project progress (`progress`), the observation and the
    record of the rule candidates."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    set_name: str
    instance: str
    lambda_a: float
    replication: NonNegativeInt
    seed: NonNegativeInt
    day: NonNegativeInt
    progress: float = Field(ge=0, le=1)
    observation: Observation
    record: DecisionRecord

    @property
    def noop(self) -> bool:
        """Whether the rule chose NOOP."""
        return self.record.chosen == "NOOP"

    @property
    def chosen_kind(self) -> str:
        found = next((c for c in self.record.candidates if c.label == self.record.chosen), None)
        return "noop" if found is None else found.kind


def state_id(set_name: str, instance: str, lambda_a: float, replication: int, day: int) -> str:
    """The id of a state, e.g. "j30/j301_1/la0.01/r0/d23"."""
    return f"{set_name}/{instance}/la{lambda_a:g}/r{replication}/d{day}"


def progress(observation: Observation) -> float:
    """Project progress: the duration-weighted share of the nominal work done, sum over the
    real activities of p_j if done, else min(e_j, p_j), over sum p_j (removed ones left out)."""
    sink = observation.instance.sink_id
    done = total = 0.0
    for j, status in enumerate(observation.status):
        if j in (0, sink) or status == REMOVED:
            continue
        duration = nominal_activity(observation, j)[0]
        total += duration
        if status == DONE:
            done += duration
        elif status != UNSTARTED:
            done += min(observation.work_done[j], duration)
    return done / total if total > 0 else 1.0


class Recorder(Sentinel):
    """Sentinel that keeps the observation and record of every deliberation that passed the
    needs gate; it decides exactly as Sentinel does."""

    def __init__(self, params: SentinelParams, *, seed: int) -> None:
        super().__init__(params, seed=seed, keep_records=False)
        self.captured: list[tuple[Observation, DecisionRecord]] = []

    def deliberate(self, observation: Observation, discarded: str | None = None) -> DecisionRecord:
        record = super().deliberate(observation, discarded)
        if record.needs is not None and not record.needs.met:
            self.captured.append((observation, record))
        return record


@dataclass(frozen=True)
class World:
    """One world of the WP5 main study: instance, scenario, replication and its seed, the
    deadline D and budget B that Sentinel sees."""

    set_name: str
    instance: str
    lambda_a: float
    replication: int
    seed: int
    deadline: int
    budget: float


def record_run(
    instance: ProjectInstance,
    plan: Schedule,
    world: World,
    params: SentinelParams,
    *,
    pert: PertParams,
    disruptions: DisruptionParams,
    review_period: int,
) -> tuple[SimulationResult, list[DecisionState]]:
    """Rerun Sentinel on `world` (checked) and return the run and its gated deliberations."""
    recorder = Recorder(params, seed=world.seed)
    result = simulate(
        instance,
        plan,
        recorder,
        world.seed,
        pert=pert,
        disruptions=disruptions,
        deadline=world.deadline,
        review_period=review_period,
        debug=True,
        budget=world.budget,
    )
    check_run(instance, result, f"{instance.name}, decision states, seed {world.seed}")
    states = [
        DecisionState(
            id=state_id(world.set_name, world.instance, world.lambda_a, world.replication, o.day),
            set_name=world.set_name,
            instance=world.instance,
            lambda_a=world.lambda_a,
            replication=world.replication,
            seed=world.seed,
            day=o.day,
            progress=progress(o),
            observation=o,
            record=record,
        )
        for o, record in recorder.captured
    ]
    return result, states


def redeliberate(state: DecisionState, params: SentinelParams) -> DecisionRecord:
    """The deliberation of a state again, from its observation and the run's seed."""
    return Sentinel(params, seed=state.seed).deliberate(state.observation)


def same_record(a: DecisionRecord, b: DecisionRecord) -> bool:
    """Whether two records agree apart from their wall times."""
    return a.model_dump(exclude=set(TIMING_FIELDS)) == b.model_dump(exclude=set(TIMING_FIELDS))


def run_file(set_name: str, instance: str, lambda_a: float, replication: int) -> str:
    """The file of a run's states relative to the states directory."""
    return f"{set_name}/{instance}_la{lambda_a:g}_r{replication}.jsonl.gz"


def write_states(path: Path, states: Sequence[DecisionState]) -> None:
    """The states of one run as gzip JSON lines (no timestamp in the header)."""
    text = "".join(state.model_dump_json() + "\n" for state in states)
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, mtime=0) as handle:
        handle.write(text.encode("utf-8"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buffer.getvalue())


def read_states(path: Path) -> list[DecisionState]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [DecisionState.model_validate_json(line) for line in handle if line.strip()]


def index_rows(states: Iterable[DecisionState], file: str) -> list[dict[str, Any]]:
    """The index rows of a run's states."""
    return [
        {
            "id": s.id,
            "set": s.set_name,
            "instance": s.instance,
            "lambda_a": s.lambda_a,
            "replication": s.replication,
            "seed": s.seed,
            "day": s.day,
            "progress": round(s.progress, 6),
            "chosen": s.record.chosen,
            "kind": s.chosen_kind,
            "reason": s.record.reason,
            "noop": int(s.noop),
            "n_candidates": len(s.record.candidates),
            "file": file,
        }
        for s in states
    ]


def write_index(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(INDEX_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)


@dataclass(frozen=True)
class IndexRow:
    """A state of the index: what the sample is stratified by and where it is stored."""

    id: str
    lambda_a: float
    progress: float
    noop: bool
    file: str


def read_index(path: Path) -> list[IndexRow]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [
            IndexRow(
                row["id"],
                float(row["lambda_a"]),
                float(row["progress"]),
                row["noop"] == "1",
                row["file"],
            )
            for row in csv.DictReader(handle)
        ]


def id_key(state: str) -> tuple[object, ...]:
    """Natural order of state ids (instance, lambda_A, replication, day)."""
    return natural_key(state)


class SampleSettings(BaseModel):
    """The stratified sample of the studies: `size` states with `seed`; `ids` is the sample as
    drawn by `scripts/record_decision_states.py`, committed in the config."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    size: PositiveInt = 150
    seed: NonNegativeInt = 2026
    ids: tuple[str, ...] = ()


class StatesConfig(BaseModel):
    """Worlds, Sentinel settings and sample of the decision states (configs/wp6_rq5_states.toml):
    every `stride`-th instance of `set_name`, each lambda_A of `lambda_a`, replication
    `replication` with the WP2b seed derive_seed(base_seed, set, instance, str(r)), the
    cpsat_det baseline plan, D for `delta_d` and B with `beta` (spec section 1.2); `sentinel`
    holds the parameters of Sentinel full of the WP5 main study (spec section 8 otherwise).
    `wp5_results` is that study's results file: the reruns must reproduce its makespans and
    deliberation counts of `wp5_policy`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    base_seed: NonNegativeInt
    data_root: Path
    baseline_cache: Path
    states_dir: Path
    max_workers: PositiveInt = 2
    set_name: str = "j30"
    reference: ReferenceKind = "opt"
    stride: PositiveInt = 8
    lambda_a: tuple[float, ...] = Field(min_length=1)
    mean_absence: float = 3.0
    lambda_s: float = 0.01
    lambda_n: float = 0.02
    replication: NonNegativeInt = 0
    delta_d: float = 0.2
    beta: float = 0.1
    review_period: PositiveInt = 5
    baseline_time_limit: float = 5.0
    baseline_seed: NonNegativeInt = 2026
    pert: PertParams = PertParams()
    sentinel: SentinelParams
    wp5_results: Path | None = None
    wp5_policy: str = "sentinel_full"
    sample: SampleSettings

    def disruptions(self, lambda_a: float) -> DisruptionParams:
        return DisruptionParams(
            lambda_a=lambda_a,
            mean_absence=self.mean_absence,
            lambda_s=self.lambda_s,
            lambda_n=self.lambda_n,
        )


def worlds(config: StatesConfig, limit: int | None) -> list[World]:
    """The worlds of the config in (instance, lambda_A) order."""
    references = load_reference(config.set_name, config.reference, config.data_root)
    stems = list_instances(config.set_name, config.data_root)[:: config.stride][:limit]
    found = []
    for stem in stems:
        instance = load_psplib(instance_path(config.set_name, stem, config.data_root))
        c_star = references[f"{config.set_name}/{stem}"]
        seed = derive_seed(config.base_seed, config.set_name, stem, str(config.replication))
        budget = derive_budget(instance, config.beta, params=config.pert)
        deadline = derive_deadline(c_star, config.delta_d)
        found += [
            World(config.set_name, stem, la, config.replication, seed, deadline, budget)
            for la in config.lambda_a
        ]
    return found


def record_task(config: StatesConfig, world: World, out: Path) -> dict[str, Any]:
    """One world (in a worker process): its states file and index rows, and its run."""
    began = time.perf_counter()
    instance = load_psplib(instance_path(world.set_name, world.instance, config.data_root))
    method = CpsatDet(
        deterministic_time_limit=config.baseline_time_limit, random_seed=config.baseline_seed
    )
    plan = cached_baseline(instance, method, config.baseline_cache)[0]
    violations = validate_schedule(instance, plan.schedule)
    if violations:
        raise InvalidScheduleError(f"baseline of {instance.name}: {violations[0].detail}")
    result, states = record_run(
        instance,
        plan.schedule,
        world,
        config.sentinel,
        pert=config.pert,
        disruptions=config.disruptions(world.lambda_a),
        review_period=config.review_period,
    )
    file = run_file(world.set_name, world.instance, world.lambda_a, world.replication)
    write_states(out / file, states)
    return {
        "world": world,
        "rows": index_rows(states, file),
        "makespan": result.makespan,
        "truncated": result.truncated,
        "states": len(states),
        "wall_time_s": time.perf_counter() - began,
    }


def terciles(values: Sequence[float]) -> tuple[float, float]:
    """The 1/3 and 2/3 quantiles (linear interpolation) of the values."""
    low, high = np.quantile(np.asarray(values, dtype=np.float64), [1 / 3, 2 / 3])
    return float(low), float(high)


def stratum_of(row: IndexRow, cuts: tuple[float, float]) -> tuple[float, int, bool]:
    """(lambda_A, progress tercile 0-2, NOOP chosen) of a state."""
    tercile = 0 if row.progress <= cuts[0] else (1 if row.progress <= cuts[1] else 2)
    return row.lambda_a, tercile, row.noop


def stratified_sample(rows: Sequence[IndexRow], size: int, seed: int) -> list[str]:
    """`size` state ids drawn by stratum (lambda_A, progress tercile over all states, whether
    the rule chose NOOP): equal shares, a stratum smaller than its share entirely and its rest
    spread over the others, remainders to the first strata in key order; within a stratum a
    seeded random choice. Returned in natural id order."""
    if size > len(rows):
        raise ValueError(f"cannot sample {size} of {len(rows)} states")
    cuts = terciles([row.progress for row in rows])
    strata: dict[tuple[float, int, bool], list[str]] = {}
    for row in rows:
        strata.setdefault(stratum_of(row, cuts), []).append(row.id)
    quota: dict[tuple[float, int, bool], int] = {}
    open_ = sorted(strata)
    left = size
    while open_:
        share, extra = divmod(left, len(open_))
        small = [key for key in open_ if len(strata[key]) < share + (extra > 0)]
        if not small:
            for position, key in enumerate(open_):
                quota[key] = share + (position < extra)
            break
        for key in small:
            quota[key] = len(strata[key])
            left -= quota[key]
            open_.remove(key)
    chosen: list[str] = []
    for key, ids in strata.items():
        lambda_a, tercile, noop = key
        rng = np.random.default_rng(
            derive_seed(seed, "sample", f"{lambda_a:g}", str(tercile), str(int(noop)))
        )
        ordered = sorted(ids, key=id_key)
        picks = rng.choice(len(ordered), size=quota.get(key, 0), replace=False)
        chosen += [ordered[int(i)] for i in picks]
    return sorted(chosen, key=id_key)


def load_states(directory: Path, ids: Sequence[str]) -> list[DecisionState]:
    """The states with the given ids, in that order, from the index of `directory`."""
    rows = {row.id: row for row in read_index(directory / INDEX_FILE)}
    missing = [state for state in ids if state not in rows]
    if missing:
        raise KeyError(f"{len(missing)} states not in {directory / INDEX_FILE}: {missing[:3]}")
    files = sorted({rows[state].file for state in ids})
    found: dict[str, DecisionState] = {}
    wanted = set(ids)
    for file in files:
        for state in read_states(directory / file):
            if state.id in wanted:
                found[state.id] = state
    return [found[state] for state in ids]


def stratum_counts(rows: Sequence[IndexRow], ids: Iterable[str]) -> dict[str, int]:
    """Sampled states per stratum, as "la<lambda_A>/t<tercile>/noop|act"."""
    cuts = terciles([row.progress for row in rows])
    by_id = {row.id: row for row in rows}
    counts: dict[str, int] = {}
    for state in ids:
        lambda_a, tercile, noop = stratum_of(by_id[state], cuts)
        key = f"la{lambda_a:g}/t{tercile}/{'noop' if noop else 'act'}"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def load_sample(
    path: Path, limit: int | None
) -> tuple[StatesConfig, list[DecisionState], dict[str, Any]]:
    """The states config at `path`, its sampled states (the first `limit`) and its raw content
    (part of a study's run hash and manifest)."""
    raw = load_toml(path)
    config = StatesConfig.model_validate(raw)
    ids = list(config.sample.ids)[:limit]
    if not ids:
        raise ValueError(f"{path} has no sample ids; run scripts/record_decision_states.py")
    return config, load_states(config.states_dir, ids), raw
