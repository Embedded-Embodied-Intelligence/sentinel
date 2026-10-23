"""RQ5 role 1: the LLM as event parser of team messages (WP6b; spec section 10.2).

    uv run python -m sentinel.experiments.event_study --config configs/wp6_rq5_events.toml \
        --out results/wp6 [--backend ollama] [--limit N] [--cache-file <bundle>]

For every `stride`-th instance of the set, `messages_per_instance` days are drawn among the
working days of a NoReaction world (the WP2b seed of replication 0, the scenario of the config,
the cpsat_det baseline plan); the observation of each day (step 3) is the state a message is
written in (`messages.generate`, seeded). Each message is parsed by each selected backend in a
WP6a repair session (`events.parse`): its first round is the single-shot condition, its last
the repair condition. Per message and condition, `results.csv` holds the accepted events
against the truth (`compare_events`): per type counts, field checks, message exactness, the
end-to-end check (`apply_events` of the parsed and of the true events give the same observation),
noise false positives, reason words in the accepted events and in the raw answer, tokens and
latency. Outputs: `results.csv`, `messages.jsonl` (the messages with their true events),
`summary.md`, the LaTeX table, `manifest.json` and the replay bundle.
"""

import csv
import json
import sys
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import Field, PositiveInt

from sentinel.data.psplib_loader import instance_path, list_instances, load_psplib, natural_key
from sentinel.data.reference import ReferenceKind, load_reference
from sentinel.experiments import runs
from sentinel.experiments.rcpsp_benchmark import format_duration
from sentinel.experiments.rq5_common import (
    PROGRESS_INTERVAL_S,
    Answer,
    Clients,
    FakeBackend,
    LlmStudyConfig,
    item_seed,
    manifest,
    mean_interval,
    open_clients,
    resamples,
    run_main,
    text_rng_seed,
    write_run_bundle,
)
from sentinel.experiments.simulation_summary import wilson_interval
from sentinel.interpret.events import (
    EVENT_FIELDS,
    EVENT_TYPES,
    EVENTS_PROMPT,
    EVENTS_REPAIR_PROMPT,
    Comparison,
    Context,
    ParseRound,
    ParseSettings,
    apply_events,
    compare_events,
    leaks,
    parse,
    parse_messages,
    same_observation,
)
from sentinel.interpret.messages import Generated, MessageSettings, generate
from sentinel.interpret.team import names_of, roster
from sentinel.llm import load_prompt
from sentinel.model import ProjectInstance, Schedule, validate_schedule
from sentinel.policies.no_reaction import NoReaction
from sentinel.simulation.baselines import CpsatDet, cached_baseline
from sentinel.simulation.engine import SimulationResult, simulate
from sentinel.simulation.events import DisruptionParams
from sentinel.simulation.uncertainty import PertParams, derive_budget, derive_deadline

RESULTS_FILE = "results.csv"
MESSAGES_FILE = "messages.jsonl"
SUMMARY_FILE = "summary.md"
CONDITIONS = ("single_shot", "repair")
FIELD_NAMES = [f"{kind}.{name}" for kind in EVENT_TYPES for name in EVENT_FIELDS[kind]]
COLUMNS = (
    "set",
    "instance",
    "day",
    "message",
    "backend",
    "model",
    "condition",
    "facts",
    "reasons",
    "n_true",
    "noise",
    "rounds_used",
    "calls",
    "valid",
    "n_issues",
    "issues",
    *(f"{part}_{kind}" for kind in EVENT_TYPES for part in ("true", "pred", "matched")),
    *(f"{name}_{part}" for name in FIELD_NAMES for part in ("right", "total")),
    "exact",
    "end_to_end",
    "noise_false_positive",
    "leaks",
    "raw_leaks",
    "prompt_tokens",
    "completion_tokens",
    "latency_s",
)
SEED_RULE = (
    "world seed of an instance = runs.derive_seed(base_seed, set, instance, '0') (WP2b, "
    "replication 0); message days, names, roster and messages from runs.derive_seed("
    "message_seed, <part>, set, instance[, day]); LLM seed of a message = runs.derive_seed("
    "base_seed, 'llm', 'events', set, instance, day), shared by the backends and the rounds"
)
Row = dict[str, Any]


class EventStudyConfig(LlmStudyConfig):
    """The RQ5 event-parser study (configs/wp6_rq5_events.toml)."""

    message_seed: int = Field(ge=0)
    data_root: Path
    baseline_cache: Path
    set_name: str = "j30"
    reference: ReferenceKind = "opt"
    stride: PositiveInt = 12
    messages_per_instance: PositiveInt = 5
    lambda_a: float = 0.01
    mean_absence: float = 3.0
    lambda_s: float = 0.01
    lambda_n: float = 0.02
    delta_d: float = 0.2
    beta: float = 0.1
    review_period: PositiveInt = 5
    baseline_time_limit: float = 5.0
    baseline_seed: int = 2026
    pert: PertParams = PertParams()
    messages: MessageSettings = MessageSettings()
    parsing: ParseSettings


@dataclass(frozen=True)
class Item:
    """A message with its context and truth."""

    set_name: str
    instance: str
    context: Context
    generated: Generated

    @property
    def key(self) -> str:
        return f"{self.set_name}/{self.instance}/d{self.context.day}"


@dataclass(frozen=True)
class _World:
    """The NoReaction world of an instance whose observations are the messages' states."""

    config: "EventStudyConfig"
    instance: ProjectInstance
    plan: Schedule
    seed: int
    disruptions: DisruptionParams
    deadline: int
    budget: float

    def simulate(self, days: Sequence[int]) -> SimulationResult:
        return simulate(
            self.instance,
            self.plan,
            NoReaction(),
            self.seed,
            pert=self.config.pert,
            disruptions=self.disruptions,
            deadline=self.deadline,
            review_period=self.config.review_period,
            budget=self.budget,
            observe_days=days,
        )


def build_items(config: EventStudyConfig, limit: int | None) -> list[Item]:
    """The study's messages: per instance, the observations of the drawn days of its world."""
    stems = list_instances(config.set_name, config.data_root)[:: config.stride][:limit]
    references = load_reference(config.set_name, config.reference, config.data_root)
    method = CpsatDet(
        deterministic_time_limit=config.baseline_time_limit, random_seed=config.baseline_seed
    )
    disruptions = DisruptionParams(
        lambda_a=config.lambda_a,
        mean_absence=config.mean_absence,
        lambda_s=config.lambda_s,
        lambda_n=config.lambda_n,
    )
    items: list[Item] = []
    for stem in stems:
        instance = load_psplib(instance_path(config.set_name, stem, config.data_root))
        plan = cached_baseline(instance, method, config.baseline_cache)[0]
        if validate_schedule(instance, plan.schedule):
            raise ValueError(f"the baseline plan of {instance.name} is infeasible")
        seed = runs.derive_seed(config.base_seed, config.set_name, stem, "0")
        deadline = derive_deadline(references[f"{config.set_name}/{stem}"], config.delta_d)
        budget = derive_budget(instance, config.beta, params=config.pert)

        run = _World(config, instance, plan.schedule, seed, disruptions, deadline, budget)
        makespan = run.simulate(()).makespan
        rng = np.random.default_rng(
            runs.derive_seed(config.message_seed, "days", config.set_name, stem)
        )
        count = min(config.messages_per_instance, makespan - 1)
        days = sorted(int(d) for d in rng.choice(np.arange(1, makespan), count, replace=False))
        result = run.simulate(days)
        members = roster(
            instance, runs.derive_seed(config.message_seed, "roster", config.set_name, stem)
        )
        names_seed = runs.derive_seed(config.message_seed, "names", config.set_name, stem)
        for observation in result.observations:
            context = Context(observation, names_of(observation, names_seed), members)
            message_rng = np.random.default_rng(
                runs.derive_seed(
                    config.message_seed, "message", config.set_name, stem, str(observation.day)
                )
            )
            generated = generate(context, message_rng, config.messages)
            items.append(Item(config.set_name, stem, context, generated))
    return items


def oracle_answer(item: Item, error_rate: float, user_content: str) -> Answer:
    """The fake backend's answers for an item: the true events; with probability `error_rate`
    a mistake validation catches in the first answer (an unknown worker, a factor below 1, an
    impossible return day or an unknown event type) and with probability `error_rate` / 2 a
    lasting one it cannot see (a return day off by one, or an event left out)."""
    rng = np.random.default_rng(text_rng_seed("oracle", user_content))
    truth = [event.model_dump() for event in item.generated.events]
    caught = rng.random() < error_rate
    lasting = rng.random() < error_rate / 2
    if lasting and truth:
        position = int(rng.integers(len(truth)))
        if truth[position]["type"] == "absence" and truth[position]["return_day"] is not None:
            truth[position] = {**truth[position], "return_day": truth[position]["return_day"] + 1}
        else:
            truth = truth[:position] + truth[position + 1 :]
    first = [dict(event) for event in truth]
    if caught:
        position = int(rng.integers(len(first))) if first else -1
        if position < 0:
            first.append({"type": "meeting", "detail": "moved"})
        elif first[position]["type"] == "absence":
            first[position]["worker"] = 9999
        elif first[position]["type"] == "work_increase":
            first[position]["factor"] = 0.5
        else:
            first[position]["duration"] = 0

    def answer(round_index: int) -> str:
        return json.dumps({"events": first if round_index == 0 else truth})

    return answer


def round_row(item: Item, step: ParseRound) -> Row:
    """The measurements of one round's accepted events against the truth."""
    truth = item.generated.events
    accepted = step.reading.events
    comparison: Comparison = compare_events(truth, accepted)
    true_state = apply_events(item.context, truth)
    parsed_state = apply_events(item.context, accepted)
    row: Row = {
        "valid": step.reading.valid,
        "n_issues": len(step.reading.issues),
        "issues": ";".join(
            f"{kind}:{n}"
            for kind, n in sorted(Counter(i.kind for i in step.reading.issues).items())
        ),
        "exact": comparison.exact,
        "end_to_end": same_observation(true_state, parsed_state),
        "noise_false_positive": bool(accepted) if not truth else None,
        "leaks": leaks([event.model_dump() for event in accepted]),
        "raw_leaks": leaks(step.response.parsed),
    }
    for kind in EVENT_TYPES:
        counts = comparison.counts[kind]
        row |= {f"true_{kind}": counts.true, f"pred_{kind}": counts.predicted}
        row[f"matched_{kind}"] = counts.matched
    for name in FIELD_NAMES:
        right, total = comparison.fields[name]
        row |= {f"{name}_right": right, f"{name}_total": total}
    return row


def session_rows(item: Item, backend: str, model: str, rounds: Sequence[ParseRound]) -> list[Row]:
    """The rows of a session: the single shot (round 0) and the repair condition (last round),
    tokens and latency summed over the rounds each condition used."""
    base: Row = {
        "set": item.set_name,
        "instance": item.instance,
        "day": item.context.day,
        "message": item.generated.message.text,
        "backend": backend,
        "model": model,
        "facts": "+".join(item.generated.facts),
        "reasons": len(item.generated.reasons),
        "n_true": len(item.generated.events),
        "noise": not item.generated.events,
    }
    rows = []
    for condition, used in (("single_shot", rounds[:1]), ("repair", rounds)):
        final = used[-1]
        rows.append(
            {
                **base,
                "condition": condition,
                "rounds_used": len(used) - 1,
                "calls": len(used),
                **round_row(item, final),
                "prompt_tokens": sum(r.response.prompt_tokens for r in used),
                "completion_tokens": sum(r.response.completion_tokens for r in used),
                "latency_s": round(sum(r.response.latency_s for r in used), 3),
            }
        )
    return rows


def execute(config: EventStudyConfig, items: Sequence[Item], clients: Clients) -> list[Row]:
    """Parse every message with every selected backend, one call after the other."""
    prompt = load_prompt(EVENTS_PROMPT, config.parsing.prompt_version)
    rows: list[Row] = []
    started = last = time.monotonic()
    total = len(items) * len(clients.clients)
    done = 0
    for item in items:
        for name, client in clients.clients.items():
            if name in clients.oracles:
                backend = config.backend[name]
                assert isinstance(backend, FakeBackend)
                content = parse_messages(item.context, item.generated.message, prompt)[1].content
                clients.oracles[name].register(
                    content, oracle_answer(item, backend.error_rate, content)
                )
            session = parse(
                client,
                item.generated.message,
                item.context,
                seed=item_seed(config.base_seed, "events", item.key),
                settings=config.parsing,
            )
            rows += session_rows(item, name, client.model, session.rounds)
            done += 1
            now = time.monotonic()
            if now - last >= PROGRESS_INTERVAL_S or done == total:
                print(
                    f"[{format_duration(now - started)}] {done}/{total} sessions; last: {name} "
                    f"{item.key}, {session.repair_rounds} repair rounds",
                    flush=True,
                )
                last = now
    return rows


def write_csv(path: Path, rows: Sequence[Row]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: int(v) if isinstance(v, bool) else v for k, v in row.items()})


def _share(rows: Sequence[Row], column: str) -> str:
    values = [row[column] for row in rows if row[column] is not None]
    if not values:
        return "-"
    hits = sum(bool(v) for v in values)
    low, high = wilson_interval(hits, len(values))
    return f"{100 * hits / len(values):.1f} [{100 * low:.1f}, {100 * high:.1f}] (n = {len(values)})"


def _ratio(numerator: float, denominator: float) -> str:
    return "-" if not denominator else f"{numerator / denominator:.3f}"


def summary_markdown(run_id: str, rows: Sequence[Row], config: EventStudyConfig) -> str:
    """Per backend and condition: valid, exact and end-to-end shares, noise false positives,
    per-type precision and recall, field accuracies, leaks, rounds, tokens and latency; and the
    paired differences repair - single shot with cluster-bootstrap intervals over instances."""
    backends = [
        b for b in [*config.backends, *config.backend] if any(r["backend"] == b for r in rows)
    ]
    backends = list(dict.fromkeys(backends))
    lines = [
        f"# RQ5 event parser — run {run_id}",
        "",
        f"{len({(r['set'], r['instance'], r['day']) for r in rows})} messages, backends "
        f"{', '.join(backends)}. Shares in % with 95 % Wilson intervals.",
        "",
        "| Backend | Condition | Valid | Exact | End to end | Noise false positives | Leaks | "
        "Raw leaks | Rounds | Tokens / msg | Latency / msg (s) |",
        "| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for backend in backends:
        for condition in CONDITIONS:
            mine = [r for r in rows if r["backend"] == backend and r["condition"] == condition]
            if not mine:
                continue
            n = len(mine)
            tokens = sum(r["prompt_tokens"] + r["completion_tokens"] for r in mine) / n
            latency = sum(r["latency_s"] for r in mine) / n
            lines.append(
                f"| {backend} | {condition} | {_share(mine, 'valid')} | {_share(mine, 'exact')} | "
                f"{_share(mine, 'end_to_end')} | {_share(mine, 'noise_false_positive')} | "
                f"{sum(r['leaks'] for r in mine)} | {sum(r['raw_leaks'] for r in mine)} | "
                f"{sum(r['rounds_used'] for r in mine) / n:.2f} | {tokens:.0f} | {latency:.1f} |"
            )
    lines += [
        "",
        "Per event type (pooled counts): precision = matched / accepted, recall = matched / true.",
        "",
        "| Backend | Condition | " + " | ".join(f"{k} P | {k} R" for k in EVENT_TYPES) + " |",
        "| --- | --- |" + " ---: | ---: |" * len(EVENT_TYPES),
    ]
    for backend in backends:
        for condition in CONDITIONS:
            mine = [r for r in rows if r["backend"] == backend and r["condition"] == condition]
            if not mine:
                continue
            cells = []
            for kind in EVENT_TYPES:
                matched = sum(r[f"matched_{kind}"] for r in mine)
                cells += [
                    _ratio(matched, sum(r[f"pred_{kind}"] for r in mine)),
                    _ratio(matched, sum(r[f"true_{kind}"] for r in mine)),
                ]
            lines.append(f"| {backend} | {condition} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "Field accuracy on matched events (pooled; absence.return_day is the return-day accuracy).",
        "",
        "| Backend | Condition | " + " | ".join(FIELD_NAMES) + " |",
        "| --- | --- |" + " ---: |" * len(FIELD_NAMES),
    ]
    for backend in backends:
        for condition in CONDITIONS:
            mine = [r for r in rows if r["backend"] == backend and r["condition"] == condition]
            if not mine:
                continue
            cells = [
                _ratio(sum(r[f"{f}_right"] for r in mine), sum(r[f"{f}_total"] for r in mine))
                for f in FIELD_NAMES
            ]
            lines.append(f"| {backend} | {condition} | " + " | ".join(cells) + " |")
    lines += _differences(rows, backends, config)
    return "\n".join(lines) + "\n"


def _differences(
    rows: Sequence[Row], backends: Sequence[str], config: EventStudyConfig
) -> list[str]:
    instances = sorted({(r["set"], r["instance"]) for r in rows}, key=lambda k: natural_key(k[1]))
    codes = {name: c for c, name in enumerate(instances)}
    weights = resamples(len(instances), config.summary, config.name)
    lines = [
        "",
        "Repair - single shot, paired by message (percentage points, 95 % cluster bootstrap "
        "over instances).",
        "",
        "| Backend | Exact | End to end |",
        "| --- | --- | --- |",
    ]
    for backend in backends:
        pairs: dict[tuple[str, str, int], dict[str, Row]] = {}
        for row in rows:
            if row["backend"] == backend:
                key = (row["set"], row["instance"], row["day"])
                pairs.setdefault(key, {})[row["condition"]] = row
        keys = [k for k, v in pairs.items() if len(v) == 2]
        clusters = [codes[(k[0], k[1])] for k in keys]
        cells = []
        for column in ("exact", "end_to_end"):
            diffs = [
                100.0 * (pairs[k]["repair"][column] - pairs[k]["single_shot"][column]) for k in keys
            ]
            estimate = mean_interval(clusters, diffs, weights)
            cells.append(f"{estimate.value:+.1f} [{estimate.low:+.1f}, {estimate.high:+.1f}]")
        lines.append(f"| {backend} | " + " | ".join(cells) + " |")
    return lines


def latex_table(run_id: str, rows: Sequence[Row], config: EventStudyConfig) -> str:
    """Exact and end-to-end shares, per-type recall, return-day accuracy and leaks per backend
    and condition (booktabs)."""
    lines = [
        f"% Generated by sentinel.experiments.event_study from run {run_id}; do not edit.",
        "\\begin{tabular}{llrrrrrrr}",
        "\\toprule",
        "Backend & Condition & Exact & End to end & R(abs.) & R(work) & R(new) & Return day & "
        "Leaks \\\\",
        "\\midrule",
    ]
    for backend in dict.fromkeys(r["backend"] for r in rows):
        for condition in CONDITIONS:
            mine = [r for r in rows if r["backend"] == backend and r["condition"] == condition]
            if not mine:
                continue
            n = len(mine)
            recall = [
                _ratio(sum(r[f"matched_{k}"] for r in mine), sum(r[f"true_{k}"] for r in mine))
                for k in EVENT_TYPES
            ]
            day = _ratio(
                sum(r["absence.return_day_right"] for r in mine),
                sum(r["absence.return_day_total"] for r in mine),
            )
            lines.append(
                f"{backend} & {condition.replace('_', ' ')} & "
                f"{100 * sum(r['exact'] for r in mine) / n:.1f} & "
                f"{100 * sum(r['end_to_end'] for r in mine) / n:.1f} & "
                + " & ".join(recall)
                + f" & {day} & {sum(r['leaks'] for r in mine)} \\\\"
            )
    lines += ["\\bottomrule", "\\end{tabular}", ""]
    return "\n".join(lines)


def run(args: Any, command: str) -> Path:
    """Parse the messages with the selected backends and write the run directory."""
    raw = runs.load_toml(args.config)
    config = EventStudyConfig.model_validate(raw)
    selected = config.selected(args.backend)
    started = datetime.now(UTC)
    git = runs.git_state()  # taken before any output of the run exists
    digest = runs.config_hash(raw, args.limit, {"backends": selected})
    run_id = runs.make_run_id(started, digest)
    clients = open_clients(config, selected, args.cache_mode, args.cache_file, args.replay)
    items = build_items(config, args.limit)
    print(
        f"run {run_id}: {len(items)} messages x {len(selected)} backends, cache mode "
        f"{clients.mode}",
        flush=True,
    )
    rows = execute(config, items, clients)
    run_dir = runs.create_run_dir(args.out, run_id, smoke=args.limit is not None)
    write_csv(run_dir / RESULTS_FILE, rows)
    with (run_dir / MESSAGES_FILE).open("w", encoding="utf-8") as handle:
        for item in items:
            record = {
                "key": item.key,
                "author": item.generated.message.author,
                "text": item.generated.message.text,
                "facts": list(item.generated.facts),
                "events": [event.model_dump() for event in item.generated.events],
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    bundle = write_run_bundle(run_dir, clients)
    table = f"{config.summary.table}.tex"
    (run_dir / SUMMARY_FILE).write_text(summary_markdown(run_id, rows, config), encoding="utf-8")
    (run_dir / table).write_text(latex_table(run_id, rows, config), encoding="utf-8")
    outputs = [RESULTS_FILE, MESSAGES_FILE, SUMMARY_FILE, table, "llm_cache.jsonl.gz"]
    data = manifest(
        run_id=run_id,
        started=started,
        git=git,
        command=command,
        config_path=args.config,
        raw_config=raw,
        digest=digest,
        limit=args.limit,
        selected=selected,
        clients=clients,
        cache_file=args.cache_file,
        bundle=bundle,
        outputs=outputs,
        extra={
            "prompts": {
                name: {
                    "version": config.parsing.prompt_version,
                    "sha256": load_prompt(name, config.parsing.prompt_version).sha256,
                }
                for name in (EVENTS_PROMPT, EVENTS_REPAIR_PROMPT)
            },
            "seeds": {"base_seed": config.base_seed, "message_seed": config.message_seed},
            "seed_rule": SEED_RULE,
            "n_messages": len(items),
            "n_rows": len(rows),
        },
    )
    runs.write_json(run_dir / "manifest.json", data)
    return run_dir


def main(argv: Sequence[str] | None = None) -> int:
    """Command line entry point; returns the exit status (3: stopped by a rate limit)."""
    return run_main(
        "sentinel.experiments.event_study",
        "RQ5 role 1: LLM event parsing of team messages.",
        argv,
        run,
    )


if __name__ == "__main__":
    sys.exit(main())
