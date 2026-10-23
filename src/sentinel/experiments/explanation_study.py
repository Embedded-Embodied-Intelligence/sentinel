"""RQ5 role 3: LLM explanations of Sentinel's decisions, checked for faithfulness (WP6b; spec
section 10.4).

    uv run python -m sentinel.experiments.explanation_study \
        --config configs/wp6_rq5_explanations.toml --out results/wp6 [--backend ollama] \
        [--limit N] [--cache-file <bundle>]

For every sampled decision state (`configs/wp6_rq5_states.toml`) its recorded `DecisionRecord`
is rendered as English text (`explain.render_record`) and each selected backend writes one
explanation: a summary of at most 80 words and the facts it cites. `explain.check` compares the
answer with the record: every cited fact, the chosen action, the deciding component, and every
number written in digits in the summary (hallucinated numbers). Outputs: `results.csv` (one row
per state and backend, the summary included), `summary.md`, the LaTeX table, `manifest.json`
and the replay bundle.
"""

import csv
import json
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from sentinel.agent.decide import DecisionRecord
from sentinel.agent.params import SentinelParams
from sentinel.experiments import runs
from sentinel.experiments.decision_states import DecisionState, load_sample
from sentinel.experiments.rcpsp_benchmark import format_duration
from sentinel.experiments.rq5_common import (
    BUNDLE_FILE,
    PROGRESS_INTERVAL_S,
    Answer,
    Clients,
    FakeBackend,
    LlmStudyConfig,
    item_seed,
    manifest,
    open_clients,
    run_main,
    text_rng_seed,
    write_run_bundle,
)
from sentinel.experiments.simulation_summary import wilson_interval
from sentinel.interpret.explain import (
    EXPLAIN_PROMPT,
    FACT_KINDS,
    MAX_WORDS,
    ExplainSettings,
    Explanation,
    RenderedRecord,
    check,
    explain,
    explain_messages,
    render_record,
)
from sentinel.llm import LlmResponse, load_prompt

RESULTS_FILE = "results.csv"
SUMMARY_FILE = "summary.md"
COLUMNS = (
    "state",
    "set",
    "instance",
    "lambda_a",
    "day",
    "rule_noop",
    "chosen",
    "reason",
    "runner_up",
    "backend",
    "model",
    "valid",
    "n_facts",
    "facts_correct",
    *(f"{kind}_{part}" for kind in FACT_KINDS for part in ("cited", "correct")),
    "chosen_named",
    "component_right",
    "numbers",
    "hallucinated",
    "words",
    "over_limit",
    "fully_faithful",
    "prompt_tokens",
    "completion_tokens",
    "latency_s",
    "summary",
)
SEED_RULE = (
    "LLM seed of a state: runs.derive_seed(base_seed, 'llm', 'explanations', state id), "
    "shared by the backends"
)
Row = dict[str, Any]


class ExplanationStudyConfig(LlmStudyConfig):
    """The RQ5 explanation study (configs/wp6_rq5_explanations.toml); `states` is the config of
    the decision states and their sample."""

    states: Path
    explanation: ExplainSettings


def oracle_answer(record: DecisionRecord, rendered: RenderedRecord, error_rate: float) -> Answer:
    """The fake backend's explanation: faithful facts and summary of the record; with
    probability `error_rate` a number the record does not show in the summary, and with the
    same probability a wrong deciding component."""
    rng = np.random.default_rng(text_rng_seed("oracle", rendered.text))
    chosen = next((c for c in record.candidates if c.label == record.chosen), None)
    if chosen is not None:
        p = chosen.p_on_time
    else:  # only NOOP was valid: the record has the p of the needs only
        p = 0.0 if record.needs is None else record.needs.p_on_time
    facts: list[dict[str, Any]] = [
        {"kind": "chosen_action", "value": record.chosen},
        {"kind": "p_on_time", "value": round(p, 2)},
    ]
    text = f'The agent chose "{record.chosen}", which finishes on time with probability {p:.2f}.'
    if chosen is not None:
        facts.append({"kind": "tardiness_days", "value": round(chosen.tardiness, 2)})
        text += f" Its expected tardiness is {chosen.tardiness:.2f} days."
    if record.runner_up is not None:
        facts.append({"kind": "alternative", "value": record.runner_up})
    component = record.reason
    if rng.random() < error_rate:
        text += " That is 97 % better than planned."
    if rng.random() < error_rate:
        component = "budget" if component != "budget" else "stability"
    facts.append({"kind": "deciding_component", "value": component})
    text += f" The decisive criterion was {component}."
    answer = json.dumps({"summary": text, "cited_facts": facts})

    def respond(round_index: int) -> str:
        return answer

    return respond


def result_row(
    state: DecisionState,
    backend: str,
    model: str,
    response: LlmResponse[Explanation],
    rendered: RenderedRecord,
) -> Row:
    """The faithfulness checks of one explanation."""
    record = state.record
    faith = check(response.parsed, record, rendered)
    summary = response.parsed.get("summary") if isinstance(response.parsed, dict) else None
    row: Row = {
        "state": state.id,
        "set": state.set_name,
        "instance": state.instance,
        "lambda_a": state.lambda_a,
        "day": state.day,
        "rule_noop": state.noop,
        "chosen": record.chosen,
        "reason": record.reason,
        "runner_up": record.runner_up or "",
        "backend": backend,
        "model": model,
        "valid": faith.valid,
        "n_facts": len(faith.facts),
        "facts_correct": sum(f.correct for f in faith.facts),
        "chosen_named": faith.chosen_named,
        "component_right": faith.component_right,
        "numbers": faith.numbers,
        "hallucinated": faith.hallucinated,
        "words": faith.words,
        "over_limit": faith.words > MAX_WORDS,
        "fully_faithful": faith.fully_faithful,
        "prompt_tokens": response.prompt_tokens,
        "completion_tokens": response.completion_tokens,
        "latency_s": round(response.latency_s, 3),
        "summary": summary if isinstance(summary, str) else "",
    }
    for kind in FACT_KINDS:
        mine = [f for f in faith.facts if f.kind == kind]
        row |= {f"{kind}_cited": len(mine), f"{kind}_correct": sum(f.correct for f in mine)}
    return row


def execute(
    config: ExplanationStudyConfig,
    states: Sequence[DecisionState],
    params: SentinelParams,
    clients: Clients,
) -> list[Row]:
    """Explain every state with every selected backend, one call after the other."""
    rows: list[Row] = []
    started = last = time.monotonic()
    total = len(states) * len(clients.clients)
    done = 0
    for state in states:
        rendered = render_record(state.record, state.observation, params)
        for name, client in clients.clients.items():
            if name in clients.oracles:
                backend = config.backend[name]
                assert isinstance(backend, FakeBackend)
                content = explain_messages(rendered, config.explanation.prompt_version)[1].content
                clients.oracles[name].register(
                    content, oracle_answer(state.record, rendered, backend.error_rate)
                )
            response = explain(
                client,
                rendered,
                seed=item_seed(config.base_seed, "explanations", state.id),
                settings=config.explanation,
            )
            rows.append(result_row(state, name, client.model, response, rendered))
            done += 1
            now = time.monotonic()
            if now - last >= PROGRESS_INTERVAL_S or done == total:
                verdict = "faithful" if rows[-1]["fully_faithful"] else "not faithful"
                print(
                    f"[{format_duration(now - started)}] {done}/{total} explanations; last: "
                    f"{name} {state.id}, {verdict}",
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


def _share(hits: int, n: int) -> str:
    if not n:
        return "-"
    low, high = wilson_interval(hits, n)
    return f"{100 * hits / n:.1f} [{100 * low:.1f}, {100 * high:.1f}]"


def summary_markdown(run_id: str, rows: Sequence[Row]) -> str:
    """Per backend: valid answers, fully faithful explanations, the chosen action cited, the
    deciding component right, hallucinated numbers per explanation, words, tokens and latency;
    and per fact kind how often it is cited and how often correctly."""
    backends = list(dict.fromkeys(r["backend"] for r in rows))
    lines = [
        f"# RQ5 explanations — run {run_id}",
        "",
        f"{len({r['state'] for r in rows})} decision states; shares in % with 95 % Wilson "
        "intervals.",
        "",
        "| Backend | Model | Valid | Fully faithful | Chosen cited | Component right | "
        "Hallucinated numbers / expl. | Words (mean) | Over 80 words | Tokens / expl. | "
        "Latency (s) |",
        "| --- | --- | --- | --- | --- | --- | ---: | ---: | --- | ---: | ---: |",
    ]
    for backend in backends:
        mine = [r for r in rows if r["backend"] == backend]
        n = len(mine)
        lines.append(
            f"| {backend} | {mine[0]['model']} | {_share(sum(r['valid'] for r in mine), n)} | "
            f"{_share(sum(r['fully_faithful'] for r in mine), n)} | "
            f"{_share(sum(r['chosen_named'] for r in mine), n)} | "
            f"{_share(sum(r['component_right'] for r in mine), n)} | "
            f"{sum(r['hallucinated'] for r in mine) / n:.2f} | "
            f"{sum(r['words'] for r in mine) / n:.1f} | "
            f"{_share(sum(r['over_limit'] for r in mine), n)} | "
            f"{sum(r['prompt_tokens'] + r['completion_tokens'] for r in mine) / n:.0f} | "
            f"{sum(r['latency_s'] for r in mine) / n:.1f} |"
        )
    lines += [
        "",
        "Cited facts per kind: correct / cited (share of explanations citing the kind).",
        "",
        "| Backend | " + " | ".join(FACT_KINDS) + " |",
        "| --- |" + " --- |" * len(FACT_KINDS),
    ]
    for backend in backends:
        mine = [r for r in rows if r["backend"] == backend]
        cells = []
        for kind in FACT_KINDS:
            cited = sum(r[f"{kind}_cited"] for r in mine)
            correct = sum(r[f"{kind}_correct"] for r in mine)
            citing = sum(r[f"{kind}_cited"] > 0 for r in mine)
            cells.append(f"{correct}/{cited} ({100 * citing / len(mine):.0f} %)")
        lines.append(f"| {backend} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def latex_table(run_id: str, rows: Sequence[Row]) -> str:
    """Fully faithful, chosen cited, component right, hallucinated numbers and words per
    backend (booktabs)."""
    lines = [
        f"% Generated by sentinel.experiments.explanation_study from run {run_id}; do not edit.",
        "\\begin{tabular}{lrrrrr}",
        "\\toprule",
        "Backend & Fully faithful & Chosen cited & Component right & Halluc./expl. & Words \\\\",
        "\\midrule",
    ]
    for backend in dict.fromkeys(r["backend"] for r in rows):
        mine = [r for r in rows if r["backend"] == backend]
        n = len(mine)
        lines.append(
            f"{backend} & {100 * sum(r['fully_faithful'] for r in mine) / n:.1f} & "
            f"{100 * sum(r['chosen_named'] for r in mine) / n:.1f} & "
            f"{100 * sum(r['component_right'] for r in mine) / n:.1f} & "
            f"{sum(r['hallucinated'] for r in mine) / n:.2f} & "
            f"{sum(r['words'] for r in mine) / n:.1f} \\\\"
        )
    lines += ["\\bottomrule", "\\end{tabular}", ""]
    return "\n".join(lines)


def run(args: Any, command: str) -> Path:
    """Explain every sampled state with the selected backends; write the run directory."""
    raw = runs.load_toml(args.config)
    config = ExplanationStudyConfig.model_validate(raw)
    selected = config.selected(args.backend)
    states_config, states, states_raw = load_sample(config.states, args.limit)
    started = datetime.now(UTC)
    git = runs.git_state()  # taken before any output of the run exists
    digest = runs.config_hash(raw, args.limit, {"backends": selected, "states": states_raw})
    run_id = runs.make_run_id(started, digest)
    clients = open_clients(config, selected, args.cache_mode, args.cache_file, args.replay)
    print(f"run {run_id}: {len(states)} states x {len(selected)} backends", flush=True)
    rows = execute(config, states, states_config.sentinel, clients)
    run_dir = runs.create_run_dir(args.out, run_id, smoke=args.limit is not None)
    write_csv(run_dir / RESULTS_FILE, rows)
    bundle = write_run_bundle(run_dir, clients)
    table = f"{config.summary.table}.tex"
    (run_dir / SUMMARY_FILE).write_text(summary_markdown(run_id, rows), encoding="utf-8")
    (run_dir / table).write_text(latex_table(run_id, rows), encoding="utf-8")
    prompt = load_prompt(EXPLAIN_PROMPT, config.explanation.prompt_version)
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
        outputs=[RESULTS_FILE, SUMMARY_FILE, table, BUNDLE_FILE],
        extra={
            "states_config": {"path": str(config.states), "config": states_raw},
            "prompts": {EXPLAIN_PROMPT: {"version": prompt.version, "sha256": prompt.sha256}},
            "seeds": {"base_seed": config.base_seed},
            "seed_rule": SEED_RULE,
            "n_states": len(states),
            "n_rows": len(rows),
        },
    )
    runs.write_json(run_dir / "manifest.json", data)
    return run_dir


def main(argv: Sequence[str] | None = None) -> int:
    """Command line entry point; returns the exit status (3: stopped by a rate limit)."""
    return run_main(
        "sentinel.experiments.explanation_study",
        "RQ5 role 3: LLM explanations of decisions, checked for faithfulness.",
        argv,
        run,
    )


if __name__ == "__main__":
    sys.exit(main())
