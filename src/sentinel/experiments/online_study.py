"""RQ5 online check: Sentinel `full` with LLM proposals at every deliberation that passed the
needs gate, against Sentinel `full` on the same worlds (WP6b; spec section 10.3).

    uv run python -m sentinel.experiments.online_study --config configs/wp6_rq5_online.toml \
        --out results/wp6 [--backend groq] [--limit N] [--cache-file <bundle>]

The worlds are those of the WP5 main study (`configs/wp6_rq5_states.toml` gives the data,
scenario, baseline plans, D, B and the Sentinel settings; this config the instance stride,
lambda_A and replication). At every gated deliberation the proposer renders the state summary,
asks the backend for proposals (one call, `actions.ask`), compiles them against the rule
candidates and adds the usable ones; Sentinel races all on the epoch's worlds and its rule
chooses (`Sentinel(proposer=...)`). The LLM is never called inside a rollout. Every realised
schedule is checked. Each run is paired with the WP5 `sentinel_full` run of its world (read
from the WP5 results, not rerun). Outputs: `results.csv` (one row per world), `summary.md`,
`manifest.json` and the replay bundle.
"""

import csv
import gzip
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import Field, PositiveInt

from sentinel.agent.candidates import Candidate
from sentinel.agent.decide import DecisionRecord
from sentinel.agent.params import SentinelParams
from sentinel.data.psplib_loader import instance_path, list_instances, load_psplib
from sentinel.data.reference import load_reference
from sentinel.experiments import runs
from sentinel.experiments.decision_states import StatesConfig
from sentinel.experiments.policy_runs import check_run, realised_deviation
from sentinel.experiments.proposal_study import compile_entries, oracle_answer
from sentinel.experiments.rcpsp_benchmark import format_duration
from sentinel.experiments.rq5_common import (
    BUNDLE_FILE,
    Clients,
    FakeBackend,
    LlmStudyConfig,
    item_seed,
    manifest,
    open_clients,
    run_main,
    write_run_bundle,
)
from sentinel.interpret.actions import (
    PROPOSALS_PROMPT,
    ProposalSettings,
    answer_entries,
    ask,
    proposal_messages,
)
from sentinel.interpret.describe import state_summary
from sentinel.interpret.team import names_of
from sentinel.llm import BaseClient, load_prompt
from sentinel.model import validate_schedule
from sentinel.policies.sentinel import Sentinel
from sentinel.simulation.baselines import CpsatDet, cached_baseline
from sentinel.simulation.engine import simulate
from sentinel.simulation.state import Observation
from sentinel.simulation.uncertainty import derive_budget, derive_deadline

RESULTS_FILE = "results.csv"
SUMMARY_FILE = "summary.md"
COLUMNS = (
    "set",
    "instance",
    "lambda_a",
    "replication",
    "seed",
    "backend",
    "model",
    "c_star",
    "deadline",
    "makespan",
    "on_time",
    "truncated",
    "cost_ratio",
    "deviation",
    "nervousness",
    "deliberations",
    "gated",
    "calls",
    "proposals",
    "compiled",
    "added",
    "chosen",
    "prompt_tokens",
    "completion_tokens",
    "latency_s",
    "wall_time_s",
    "wp5_makespan",
    "wp5_on_time",
    "wp5_cost_ratio",
    "wp5_deviation",
)
SEED_RULE = (
    "world seed = runs.derive_seed(base seed of the states config, set, instance, str(r)) (WP2b "
    "and WP5); LLM seed of a deliberation = runs.derive_seed(base_seed, 'llm', 'online', set, "
    "instance, str(day)); activity names from runs.derive_seed(names_seed, 'names', set, instance)"
)
Row = dict[str, Any]


class OnlineStudyConfig(LlmStudyConfig):
    """The online check (configs/wp6_rq5_online.toml): every `stride`-th instance of the states
    config's set at `lambda_a`, `replications` replications from 0."""

    states: Path
    names_seed: int = Field(ge=0)
    stride: PositiveInt = 24
    lambda_a: float = 0.01
    replications: PositiveInt = 1
    proposals: ProposalSettings


@dataclass
class LlmProposer:
    """The proposer of a run (`policies.sentinel.Proposer`): one proposal call per gated
    deliberation on its state summary, compiled against the rule candidates; it counts the
    calls, proposals, compiled and usable ones, and tokens."""

    name: str
    client: BaseClient
    names_seed: int
    params: SentinelParams
    settings: ProposalSettings
    seed_keys: tuple[str, ...]
    base_seed: int
    oracle_rate: float | None = None
    clients: Clients | None = None
    calls: int = 0
    proposals: int = 0
    compiled: int = 0
    added: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0
    labels: set[str] = field(default_factory=set)

    def __call__(
        self, observation: Observation, record: DecisionRecord, rule: Sequence[Candidate]
    ) -> Sequence[Candidate]:
        names = names_of(observation, self.names_seed)  # D3 activities get names as they come
        summary = state_summary(observation, record, names, self.params)
        if self.oracle_rate is not None and self.clients is not None:
            prompt = load_prompt(PROPOSALS_PROMPT, self.settings.prompt_version)
            content = proposal_messages(summary, prompt)[1].content
            self.clients.oracles[self.name].register(
                content, oracle_answer(observation, self.oracle_rate, content)
            )
        seed = item_seed(self.base_seed, "online", *self.seed_keys, str(observation.day))
        response = ask(self.client, summary, seed=seed, settings=self.settings)
        compiled = compile_entries(
            f"{self.name}-d{observation.day}",
            answer_entries(response),
            observation,
            rule,
            self.params,
        )
        usable = [c.candidate for c in compiled if c.usable and c.candidate is not None]
        self.calls += 1
        self.proposals += len(compiled)
        self.compiled += sum(c.candidate is not None for c in compiled)
        self.added += len(usable)
        self.prompt_tokens += response.prompt_tokens
        self.completion_tokens += response.completion_tokens
        self.latency_s += response.latency_s
        self.labels |= {c.label for c in usable}
        return usable


def wp5_rows(states: StatesConfig) -> dict[tuple[str, float, int], dict[str, str]]:
    """The WP5 rows of the states config's policy by (instance, lambda_A, replication)."""
    if states.wp5_results is None:
        return {}
    with gzip.open(states.wp5_results, "rt", encoding="utf-8") as handle:
        return {
            (row["instance"], float(row["lambda_a"]), int(row["replication"])): row
            for row in csv.DictReader(handle)
            if row["policy"] == states.wp5_policy and row["set"] == states.set_name
        }


def execute(
    config: OnlineStudyConfig, states: StatesConfig, clients: Clients, limit: int | None
) -> list[Row]:
    """Every world with every selected backend, one run after the other."""
    stems = list_instances(states.set_name, states.data_root)[:: config.stride][:limit]
    references = load_reference(states.set_name, states.reference, states.data_root)
    method = CpsatDet(
        deterministic_time_limit=states.baseline_time_limit, random_seed=states.baseline_seed
    )
    reference = wp5_rows(states)
    params = states.sentinel
    rows: list[Row] = []
    started = time.monotonic()
    for stem in stems:
        instance = load_psplib(instance_path(states.set_name, stem, states.data_root))
        plan = cached_baseline(instance, method, states.baseline_cache)[0]
        if validate_schedule(instance, plan.schedule):
            raise ValueError(f"the baseline plan of {instance.name} is infeasible")
        c_star = references[f"{states.set_name}/{stem}"]
        deadline = derive_deadline(c_star, states.delta_d)
        budget = derive_budget(instance, states.beta, params=states.pert)
        names_seed = runs.derive_seed(config.names_seed, "names", states.set_name, stem)
        for replication in range(config.replications):
            seed = runs.derive_seed(states.base_seed, states.set_name, stem, str(replication))
            for name, client in clients.clients.items():
                began = time.perf_counter()
                backend = config.backend[name]
                proposer = LlmProposer(
                    name,
                    client,
                    names_seed,
                    params,
                    config.proposals,
                    (states.set_name, stem, str(replication)),
                    config.base_seed,
                    oracle_rate=backend.error_rate if isinstance(backend, FakeBackend) else None,
                    clients=clients,
                )
                agent = Sentinel(params, seed=seed, proposer=proposer)
                result = simulate(
                    instance,
                    plan.schedule,
                    agent,
                    seed,
                    pert=states.pert,
                    disruptions=states.disruptions(config.lambda_a),
                    deadline=deadline,
                    review_period=states.review_period,
                    debug=True,
                    budget=budget,
                )
                check_run(instance, result, f"{instance.name}, online {name}, seed {seed}")
                stats = agent.stats
                chosen = sum(r.chosen in proposer.labels for r in agent.records if r.deliberated)
                wp5 = reference.get((stem, config.lambda_a, replication), {})
                rows.append(
                    {
                        "set": states.set_name,
                        "instance": stem,
                        "lambda_a": config.lambda_a,
                        "replication": replication,
                        "seed": seed,
                        "backend": name,
                        "model": client.model,
                        "c_star": c_star,
                        "deadline": deadline,
                        "makespan": result.makespan,
                        "on_time": not result.truncated and result.makespan <= deadline,
                        "truncated": result.truncated,
                        "cost_ratio": round(result.total_cost / budget, 6),
                        "deviation": round(realised_deviation(result, plan.schedule, instance), 6),
                        "nervousness": result.nervousness,
                        "deliberations": stats.deliberations,
                        "gated": stats.deliberations - stats.gate_exits,
                        "calls": proposer.calls,
                        "proposals": proposer.proposals,
                        "compiled": proposer.compiled,
                        "added": proposer.added,
                        "chosen": chosen,
                        "prompt_tokens": proposer.prompt_tokens,
                        "completion_tokens": proposer.completion_tokens,
                        "latency_s": round(proposer.latency_s, 3),
                        "wall_time_s": round(time.perf_counter() - began, 2),
                        "wp5_makespan": wp5.get("makespan"),
                        "wp5_on_time": wp5.get("met_0.2"),
                        "wp5_cost_ratio": wp5.get("cost_ratio"),
                        "wp5_deviation": wp5.get("deviation"),
                    }
                )
                elapsed = format_duration(time.monotonic() - started)
                print(
                    f"[{elapsed}] {name} {stem} r{replication}: makespan {result.makespan} "
                    f"(WP5 {wp5.get('makespan')}), {proposer.calls} calls, {chosen} proposals "
                    "chosen",
                    flush=True,
                )
    return rows


def _mean_difference(rows: Sequence[Row], column: str, wp5: str) -> str:
    """Mean of `column` minus its WP5 value over the rows paired with a WP5 run."""
    paired = [r for r in rows if r[wp5] not in (None, "")]
    if not paired:
        return "-"
    return f"{np.mean([float(r[column]) - float(r[wp5]) for r in paired]):+.3f}"


def summary_markdown(run_id: str, rows: Sequence[Row]) -> str:
    """Per backend: runs, on time against WP5's Sentinel `full` on the same worlds, the mean
    differences in makespan, deviation and cost / B, proposals added and chosen, tokens."""
    lines = [
        f"# RQ5 online check — run {run_id}",
        "",
        "| Backend | Runs | On time | On time WP5 | Makespan - WP5 | Deviation - WP5 | "
        "Cost/B - WP5 | Gated deliberations | Proposals added | Chosen | Tokens / run |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for backend in dict.fromkeys(r["backend"] for r in rows):
        mine = [r for r in rows if r["backend"] == backend]
        wp5_on_time = sum(str(r["wp5_on_time"]) in ("1", "True") for r in mine)
        tokens = sum(r["prompt_tokens"] + r["completion_tokens"] for r in mine) / len(mine)
        cells = [
            backend,
            str(len(mine)),
            str(sum(r["on_time"] for r in mine)),
            str(wp5_on_time),
            _mean_difference(mine, "makespan", "wp5_makespan"),
            _mean_difference(mine, "deviation", "wp5_deviation"),
            _mean_difference(mine, "cost_ratio", "wp5_cost_ratio"),
            str(sum(r["gated"] for r in mine)),
            str(sum(r["added"] for r in mine)),
            str(sum(r["chosen"] for r in mine)),
            f"{tokens:.0f}",
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def run(args: Any, command: str) -> Path:
    """Run the worlds with the selected backends' proposers; write the run directory."""
    raw = runs.load_toml(args.config)
    config = OnlineStudyConfig.model_validate(raw)
    selected = config.selected(args.backend)
    states_raw = runs.load_toml(config.states)
    states = StatesConfig.model_validate(states_raw)
    started = datetime.now(UTC)
    digest = runs.config_hash(raw, args.limit, {"backends": selected, "states": states_raw})
    run_id = runs.make_run_id(started, digest)
    clients = open_clients(config, selected, args.cache_mode, args.cache_file)
    print(f"run {run_id}: backends {', '.join(selected)}, cache mode {clients.mode}", flush=True)
    rows = execute(config, states, clients, args.limit)
    run_dir = runs.create_run_dir(args.out, run_id, smoke=args.limit is not None)
    with (run_dir / RESULTS_FILE).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: int(v) if isinstance(v, bool) else v for k, v in row.items()})
    bundle = write_run_bundle(run_dir, clients)
    (run_dir / SUMMARY_FILE).write_text(summary_markdown(run_id, rows), encoding="utf-8")
    prompt = load_prompt(PROPOSALS_PROMPT, config.proposals.prompt_version)
    data = manifest(
        run_id=run_id,
        started=started,
        command=command,
        config_path=args.config,
        raw_config=raw,
        digest=digest,
        limit=args.limit,
        selected=selected,
        clients=clients,
        cache_file=args.cache_file,
        bundle=bundle,
        outputs=[RESULTS_FILE, SUMMARY_FILE, BUNDLE_FILE],
        extra={
            "states_config": {"path": str(config.states), "config": states_raw},
            "prompts": {PROPOSALS_PROMPT: {"version": prompt.version, "sha256": prompt.sha256}},
            "seeds": {"base_seed": config.base_seed, "names_seed": config.names_seed},
            "seed_rule": SEED_RULE,
            "n_rows": len(rows),
        },
    )
    runs.write_json(run_dir / "manifest.json", data)
    return run_dir


def main(argv: Sequence[str] | None = None) -> int:
    """Command line entry point; returns the exit status (3: stopped by a rate limit)."""
    return run_main(
        "sentinel.experiments.online_study",
        "RQ5 online check: Sentinel full with LLM proposals against Sentinel full.",
        argv,
        run,
    )


if __name__ == "__main__":
    sys.exit(main())
