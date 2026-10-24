"""RQ5 role 2: candidate actions proposed by the LLM against a random-proposal control (WP6b;
spec section 10.3).

    uv run python -m sentinel.experiments.proposal_study --config configs/wp6_rq5_proposals.toml \
        --out results/wp6 [--backend ollama] [--limit N] [--cache-file <bundle>]

For every sampled decision state (`configs/wp6_rq5_states.toml`; `experiments.decision_states`)
the rule candidates are generated again and raced on the epoch's worlds (the seed of the
recorded deliberation, N_1 = 25, N = 100, common random numbers), which reproduces the recorded
choice (checked). Every source then proposes up to three actions: each selected LLM backend from
the English state summary (`describe.state_summary`), and the `random` control, drawn uniformly
from the grammar over the operations valid in the state with a seed per state. Proposals are
compiled (`actions.Compiler`: invalid ones become issues, duplicates of a rule candidate or an
earlier proposal are flagged) and the source's usable ones are raced together with the rule
candidates on the same worlds; the rule of spec section 6 chooses. A source wins a state if one
of its proposals is the choice; its gain is the chosen proposal's min(p, theta_D) and expected
tardiness T against those of the rule's own choice on the same N worlds; a win can lose in them
where the source's race dropped the rule's choice in stage 1 (`rule_dropped`). Outputs:
`results.csv` (state x source), `proposals.csv` (one row per proposal), `summary.md`, the LaTeX
table, `manifest.json` and the replay bundle.
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
from pydantic import Field

from sentinel.agent.candidates import Candidate, generate
from sentinel.agent.decide import Choice, DecisionRecord, choose
from sentinel.agent.evaluate import Evaluation, Evaluator, race
from sentinel.agent.params import SentinelParams
from sentinel.experiments import runs
from sentinel.experiments.decision_states import DecisionState, load_sample
from sentinel.experiments.forecast_summary import Estimate
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
    mean_interval,
    open_clients,
    read_rows,
    resamples,
    run_main,
    text_rng_seed,
    write_run_bundle,
)
from sentinel.experiments.simulation_summary import wilson_interval
from sentinel.interpret.actions import (
    PROPOSALS_PROMPT,
    Compiled,
    Compiler,
    Proposal,
    ProposalSettings,
    answer_entries,
    ask,
    proposal_messages,
    proposal_text,
    random_proposals,
)
from sentinel.interpret.describe import state_summary
from sentinel.interpret.team import names_of
from sentinel.llm import BaseClient, LlmResponse, load_prompt
from sentinel.simulation.state import Observation

RESULTS_FILE = "results.csv"
PROPOSALS_FILE = "proposals.csv"
SUMMARY_FILE = "summary.md"
RANDOM = "random"
COLUMNS = (
    "state",
    "set",
    "instance",
    "lambda_a",
    "day",
    "progress",
    "rule_noop",
    "rule_choice",
    "rule_reason",
    "rule_candidates",
    "source",
    "model",
    "answer_valid",
    "n_proposals",
    "compiled",
    "duplicates",
    "evaluated",
    "issues",
    "chosen",
    "win",
    "reason",
    "rule_dropped",
    "gain_capped",
    "gain_tardiness",
    "se_capped",
    "se_tardiness",
    "rollouts",
    "prompt_tokens",
    "completion_tokens",
    "latency_s",
)
PROPOSAL_COLUMNS = (
    "state",
    "source",
    "label",
    "proposal",
    "compiled",
    "issue",
    "issue_detail",
    "duplicate_of",
    "kind",
    "level",
    "p_on_time",
    "tardiness",
    "overrun",
    "deviation",
    "dropped",
    "chosen",
)
SEED_RULE = (
    "rollouts of a state: derive_seed(run seed, 'sentinel', str(day)), as in the recorded "
    "deliberation; LLM seed: runs.derive_seed(base_seed, 'llm', 'proposals', state id), shared "
    "by the backends; random source: runs.derive_seed(random_seed, 'random', state id); "
    "activity names: runs.derive_seed(names_seed, 'names', set, instance)"
)
Row = dict[str, Any]


class ProposalStudyConfig(LlmStudyConfig):
    """The RQ5 proposal study (configs/wp6_rq5_proposals.toml); `states` is the config of the
    decision states and their sample."""

    random_seed: int = Field(ge=0)
    names_seed: int = Field(ge=0)
    states: Path
    proposals: ProposalSettings


@dataclass(frozen=True)
class RuleRace:
    """The rule candidates of a state raced again on its worlds, and the rule's choice."""

    evaluator: Evaluator
    candidates: tuple[Candidate, ...]
    evaluation: Evaluation | None
    choice: Choice | None

    @property
    def index(self) -> int:
        return 0 if self.choice is None else self.choice.index


def rule_race(state: DecisionState, params: SentinelParams) -> RuleRace:
    """Generate and race the rule candidates as the recorded deliberation did (spec section 6)
    and check that the choice and the candidates are the recorded ones."""
    observation = state.observation
    evaluator = Evaluator(
        observation, runs.derive_seed(state.seed, "sentinel", str(observation.day)), params
    )
    candidates = generate(observation, params=params).candidates
    evaluation = choice = None
    if len(candidates) > 1:
        evaluation = race(evaluator, candidates)
        choice = choose(evaluation.stats, params, evaluation.paired)
    labels = [c.label for c in candidates]
    recorded = [c.label for c in state.record.candidates] or ["NOOP"]
    chosen = candidates[0 if choice is None else choice.index].label
    if labels != recorded or chosen != state.record.chosen:
        raise RuntimeError(
            f"state {state.id} does not reproduce: {chosen} vs {state.record.chosen}"
        )
    return RuleRace(evaluator, candidates, evaluation, choice)


@dataclass(frozen=True)
class SourceResult:
    """A source's proposals at a state: the compiled proposals, the LLM response (None for the
    random source), whether the answer fitted the schema, and the race with the rule
    candidates (None if no proposal was usable)."""

    source: str
    model: str
    compiled: tuple[Compiled, ...]
    response: LlmResponse[Any] | None
    answer_valid: bool
    evaluation: Evaluation | None = None
    choice: Choice | None = None


def compile_entries(
    source: str,
    entries: Sequence[Proposal | Any],
    observation: Observation,
    rule: Sequence[Candidate],
    params: SentinelParams,
) -> tuple[Compiled, ...]:
    """Compile a source's entries with labels "<source>#<n>: <proposal>"."""
    compiler = Compiler(observation, rule, params)
    found = []
    for n, entry in enumerate(entries, start=1):
        text = proposal_text(entry) if isinstance(entry, Proposal) else "invalid"
        found.append(compiler.compile(entry, f"{source}#{n}: {text}"))
    return tuple(found)


def llm_source(
    name: str,
    client: BaseClient,
    summary: str,
    *,
    seed: int,
    settings: ProposalSettings,
    observation: Observation,
    rule: Sequence[Candidate],
    params: SentinelParams,
) -> SourceResult:
    """Ask a backend for proposals on the summary and compile them."""
    response = ask(client, summary, seed=seed, settings=settings)
    entries = answer_entries(response)
    compiled = compile_entries(name, entries, observation, rule, params)
    return SourceResult(name, client.model, compiled, response, response.value is not None)


def random_source(
    observation: Observation, rule: Sequence[Candidate], params: SentinelParams, seed: int
) -> SourceResult:
    """The random control: proposals drawn uniformly from the grammar, compiled."""
    proposals = random_proposals(observation, np.random.default_rng(seed))
    compiled = compile_entries(RANDOM, proposals, observation, rule, params)
    return SourceResult(RANDOM, "uniform", compiled, None, True)


def with_race(result: SourceResult, race_: RuleRace, params: SentinelParams) -> SourceResult:
    """Race the source's usable proposals with the rule candidates; the rule chooses."""
    usable = [c.candidate for c in result.compiled if c.usable and c.candidate is not None]
    if not usable:
        return result
    candidates = [*race_.candidates, *usable]
    evaluation = race(race_.evaluator, candidates)
    choice = choose(evaluation.stats, params, evaluation.paired)
    return SourceResult(
        result.source,
        result.model,
        result.compiled,
        result.response,
        result.answer_valid,
        evaluation,
        choice,
    )


def oracle_answer(observation: Observation, error_rate: float, content: str) -> Answer:
    """The fake backend's answer at a state: three proposals drawn as the random source draws
    them (another seed), and with probability `error_rate` a fourth one with an unknown role,
    beyond the third (so an answer the schema rejects)."""
    rng = np.random.default_rng(text_rng_seed("oracle", content))
    proposals = [p.model_dump() for p in random_proposals(observation, rng)]
    if rng.random() < error_rate:
        proposals[-1] = {
            "operations": [{"op": "OVERTIME", "role": "designer", "workers": 1, "days": 5}]
        }

    def answer(round_index: int) -> str:
        return json.dumps({"proposals": proposals})

    return answer


def result_rows(
    state: DecisionState, race_: RuleRace, result: SourceResult, params: SentinelParams
) -> tuple[Row, list[Row]]:
    """The state x source row and the proposal rows. A win's gain compares the chosen proposal
    with the rule's own choice on the same N worlds (the evaluator's rollouts of that choice,
    even if racing dropped it in the source's race)."""
    rule = race_.candidates[race_.index]
    base: Row = {
        "state": state.id,
        "set": state.set_name,
        "instance": state.instance,
        "lambda_a": state.lambda_a,
        "day": state.day,
        "progress": round(state.progress, 4),
        "rule_noop": state.noop,
        "rule_choice": rule.label,
        "rule_reason": state.record.reason,
        "rule_candidates": len(race_.candidates),
        "source": result.source,
        "model": result.model,
    }
    response = result.response
    compiled = [c for c in result.compiled if c.candidate is not None]
    issues = Counter(c.issue.kind for c in result.compiled if c.issue is not None)
    row: Row = {
        **base,
        "answer_valid": result.answer_valid,
        "n_proposals": len(result.compiled),
        "compiled": len(compiled),
        "duplicates": sum(c.duplicate_of is not None for c in compiled),
        "evaluated": sum(c.usable for c in result.compiled),
        "issues": ";".join(f"{k}:{n}" for k, n in sorted(issues.items())),
        "chosen": rule.label,
        "win": False,
        "reason": state.record.reason,
        "rule_dropped": False,
        "gain_capped": 0.0,
        "gain_tardiness": 0.0,
        "se_capped": None,
        "se_tardiness": None,
        "rollouts": 0,
        "prompt_tokens": 0 if response is None else response.prompt_tokens,
        "completion_tokens": 0 if response is None else response.completion_tokens,
        "latency_s": 0.0 if response is None else round(response.latency_s, 3),
    }
    stats_by_label: dict[str, Any] = {}
    chosen_label = rule.label
    if result.evaluation is not None and result.choice is not None:
        evaluation, choice = result.evaluation, result.choice
        stats_by_label = {s.label: s for s in evaluation.stats}
        chosen = evaluation.stats[choice.index]
        chosen_label = chosen.label
        win = choice.index >= len(race_.candidates)
        row |= {
            "chosen": chosen.label,
            "win": win,
            "reason": choice.reason,
            "rule_dropped": evaluation.stats[race_.index].dropped,
        }
        if win:
            mine = race_.evaluator.stats(rule, params.n_rollouts, 0.0)
            row |= {
                "gain_capped": round(chosen.capped - mine.capped, 6),
                "gain_tardiness": round(mine.tardiness - chosen.tardiness, 6),
                "se_capped": round(evaluation.paired("on_time", choice.index, race_.index), 6),
                "se_tardiness": round(evaluation.paired("tardiness", choice.index, race_.index), 6),
            }
        row["rollouts"] = evaluation.rollouts
    proposals = []
    for c in result.compiled:
        stats = stats_by_label.get(c.label)
        proposals.append(
            {
                "state": state.id,
                "source": result.source,
                "label": c.label,
                "proposal": "" if c.proposal is None else c.proposal.model_dump_json(),
                "compiled": c.candidate is not None,
                "issue": "" if c.issue is None else c.issue.kind,
                "issue_detail": "" if c.issue is None else c.issue.message,
                "duplicate_of": c.duplicate_of or "",
                "kind": "" if c.candidate is None else c.candidate.kind,
                "level": None if c.candidate is None else c.candidate.level,
                "p_on_time": None if stats is None else stats.p_on_time,
                "tardiness": None if stats is None else stats.tardiness,
                "overrun": None if stats is None else stats.overrun,
                "deviation": None if stats is None else round(stats.deviation, 4),
                "dropped": None if stats is None else stats.dropped,
                "chosen": c.label == chosen_label,
            }
        )
    return row, proposals


def summary_for(
    observation: Observation,
    record: DecisionRecord,
    state: DecisionState,
    config: ProposalStudyConfig,
    params: SentinelParams,
) -> str:
    """The state summary a proposal call is given."""
    seed = runs.derive_seed(config.names_seed, "names", state.set_name, state.instance)
    return state_summary(observation, record, names_of(observation, seed), params)


def execute(
    config: ProposalStudyConfig,
    states: Sequence[DecisionState],
    params: SentinelParams,
    clients: Clients,
) -> tuple[list[Row], list[Row]]:
    """Every state with the random source and every selected backend, one after the other."""
    prompt = load_prompt(PROPOSALS_PROMPT, config.proposals.prompt_version)
    rows: list[Row] = []
    proposal_rows: list[Row] = []
    started = last = time.monotonic()
    for done, state in enumerate(states, start=1):
        race_ = rule_race(state, params)
        observation = state.observation
        summary = summary_for(observation, state.record, state, config, params)
        results = [
            random_source(
                observation,
                race_.candidates,
                params,
                runs.derive_seed(config.random_seed, "random", state.id),
            )
        ]
        for name, client in clients.clients.items():
            if name in clients.oracles:
                backend = config.backend[name]
                assert isinstance(backend, FakeBackend)
                content = proposal_messages(summary, prompt)[1].content
                clients.oracles[name].register(
                    content, oracle_answer(observation, backend.error_rate, content)
                )
            results.append(
                llm_source(
                    name,
                    client,
                    summary,
                    seed=item_seed(config.base_seed, "proposals", state.id),
                    settings=config.proposals,
                    observation=observation,
                    rule=race_.candidates,
                    params=params,
                )
            )
        for result in results:
            row, mine = result_rows(state, race_, with_race(result, race_, params), params)
            rows.append(row)
            proposal_rows += mine
        now = time.monotonic()
        if now - last >= PROGRESS_INTERVAL_S or done == len(states):
            wins = ", ".join(
                f"{r['source']} {'win' if r['win'] else '-'}" for r in rows[-len(results) :]
            )
            print(
                f"[{format_duration(now - started)}] {done}/{len(states)} states; last: {wins}",
                flush=True,
            )
            last = now
    return rows, proposal_rows


def write_csv(path: Path, columns: Sequence[str], rows: Sequence[Row]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: int(v) if isinstance(v, bool) else v for k, v in row.items()})


def _share(hits: int, n: int) -> str:
    if not n:
        return "-"
    low, high = wilson_interval(hits, n)
    return f"{100 * hits / n:.1f} [{100 * low:.1f}, {100 * high:.1f}]"


def _mean_se(values: Sequence[float]) -> str:
    if not values:
        return "-"
    mean = float(np.mean(values))
    se = float(np.std(values, ddof=1) / np.sqrt(len(values))) if len(values) > 1 else 0.0
    return f"{mean:+.3f} ± {se:.3f}"


def paired_difference(
    rows: Sequence[Row], source: str, control: str, column: str, settings: Any, key: str
) -> Estimate | None:
    """Mean over states of `column` for `source` minus `control` (paired by state), with a
    bootstrap interval over states."""
    by_state: dict[str, dict[str, float]] = {}
    for row in rows:
        by_state.setdefault(row["state"], {})[row["source"]] = float(row[column])
    states = [s for s, v in by_state.items() if source in v and control in v]
    if not states:
        return None
    weights = resamples(len(states), settings, key)
    diffs = [by_state[s][source] - by_state[s][control] for s in states]
    return mean_interval(list(range(len(states))), diffs, weights)


def summary_markdown(
    run_id: str, rows: Sequence[Row], proposal_rows: Sequence[Row], config: ProposalStudyConfig
) -> str:
    """Per source: answer validity, compile and duplicate rates, win rate, mean gains when it
    wins, tokens and latency; per source and stratum the win rate; LLM - random paired by state."""
    sources = list(dict.fromkeys(r["source"] for r in rows))
    lines = [
        f"# RQ5 proposals — run {run_id}",
        "",
        f"{len({r['state'] for r in rows})} decision states; sources {', '.join(sources)}. "
        "Shares in % with 95 % Wilson intervals; gains as mean ± standard error over the states "
        "a source wins (min(p, theta_D) higher and expected tardiness lower are positive).",
        "",
        "| Source | Model | Valid answers | Proposals | Compile rate | Duplicate rate | Win rate | "
        "Gain min(p, θ) | Gain T (days) | Tokens / state | Latency / state (s) |",
        "| --- | --- | --- | ---: | --- | --- | --- | --- | --- | ---: | ---: |",
    ]
    for source in sources:
        mine = [r for r in rows if r["source"] == source]
        n = len(mine)
        proposals = sum(r["n_proposals"] for r in mine)
        compiled = sum(r["compiled"] for r in mine)
        wins = [r for r in mine if r["win"]]
        tokens = sum(r["prompt_tokens"] + r["completion_tokens"] for r in mine) / n
        latency = sum(r["latency_s"] for r in mine) / n
        lines.append(
            f"| {source} | {mine[0]['model']} | {_share(sum(r['answer_valid'] for r in mine), n)} "
            f"| {proposals} | {_share(compiled, proposals)} | "
            f"{_share(sum(r['duplicates'] for r in mine), compiled)} | {_share(len(wins), n)} | "
            f"{_mean_se([r['gain_capped'] for r in wins])} | "
            f"{_mean_se([r['gain_tardiness'] for r in wins])} | {tokens:.0f} | {latency:.1f} |"
        )
    lines += [
        "",
        "Win rate by stratum of the rule's own choice (NOOP or an action).",
        "",
        "| Source | Rule chose NOOP | Rule chose an action |",
        "| --- | --- | --- |",
    ]
    for source in sources:
        mine = [r for r in rows if r["source"] == source]
        cells = []
        for noop in (True, False):
            part = [r for r in mine if bool(r["rule_noop"]) == noop]
            cells.append(f"{_share(sum(r['win'] for r in part), len(part))} (n = {len(part)})")
        lines.append(f"| {source} | " + " | ".join(cells) + " |")
    issues: Counter[str] = Counter()
    for r in proposal_rows:
        if r["issue"]:
            issues[f"{r['source']}:{r['issue']}"] += 1
    if issues:
        lines += ["", "Issues: " + ", ".join(f"{k} {n}" for k, n in sorted(issues.items())) + "."]
    dropped = {
        s: sum(r["win"] and r["rule_dropped"] for r in rows if r["source"] == s) for s in sources
    }
    lines += [
        "",
        "Wins where the source's race dropped the rule's own choice in stage 1 (racing on N_1 "
        "rollouts, spec section 6): " + ", ".join(f"{s} {n}" for s, n in dropped.items()) + ".",
    ]
    llms = [s for s in sources if s != RANDOM]
    if RANDOM in sources and llms:
        lines += [
            "",
            "LLM - random, paired by state (95 % bootstrap interval over states): win rate in "
            "percentage points, and the mean improvement per state (0 where the source does not "
            "win) in min(p, theta_D) and in T.",
            "",
            "| Source | Win rate | Improvement min(p, θ) | Improvement T (days) |",
            "| --- | --- | --- | --- |",
        ]
        enriched = [dict(r, win_pp=100.0 * bool(r["win"])) for r in rows]
        for source in llms:
            cells = []
            for column, digits in (("win_pp", 1), ("gain_capped", 4), ("gain_tardiness", 3)):
                estimate = paired_difference(
                    enriched, source, RANDOM, column, config.summary, f"{config.name}/{column}"
                )
                cells.append(
                    "-"
                    if estimate is None
                    else f"{estimate.value:+.{digits}f} [{estimate.low:+.{digits}f}, "
                    f"{estimate.high:+.{digits}f}]"
                )
            lines.append(f"| {source} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def latex_table(run_id: str, rows: Sequence[Row]) -> str:
    """Validity, compile, duplicate and win rates and the mean gains per source (booktabs)."""
    lines = [
        f"% Generated by sentinel.experiments.proposal_study from run {run_id}; do not edit.",
        "\\begin{tabular}{lrrrrrr}",
        "\\toprule",
        "Source & Valid & Compiled & Duplicates & Wins & Gain $\\min(\\hat p, \\theta_D)$ & "
        "Gain $\\hat T$ \\\\",
        "\\midrule",
    ]
    for source in dict.fromkeys(r["source"] for r in rows):
        mine = [r for r in rows if r["source"] == source]
        n = len(mine)
        proposals = sum(r["n_proposals"] for r in mine) or 1
        compiled = sum(r["compiled"] for r in mine)
        wins = [r for r in mine if r["win"]]
        gain_p = np.mean([r["gain_capped"] for r in wins]) if wins else float("nan")
        gain_t = np.mean([r["gain_tardiness"] for r in wins]) if wins else float("nan")
        lines.append(
            f"{source} & {100 * sum(r['answer_valid'] for r in mine) / n:.1f} & "
            f"{100 * compiled / proposals:.1f} & "
            f"{100 * sum(r['duplicates'] for r in mine) / max(compiled, 1):.1f} & "
            f"{100 * len(wins) / n:.1f} & {gain_p:.3f} & {gain_t:.2f} \\\\"
        )
    lines += ["\\bottomrule", "\\end{tabular}", ""]
    return "\n".join(lines)


def run(args: Any, command: str) -> Path:
    """Evaluate the proposals of every source on the sampled states; write the run directory."""
    raw = runs.load_toml(args.config)
    config = ProposalStudyConfig.model_validate(raw)
    selected = config.selected(args.backend)
    states_config, states, states_raw = load_sample(config.states, args.limit)
    params = states_config.sentinel
    started = datetime.now(UTC)
    git = runs.git_state()  # taken before any output of the run exists
    digest = runs.config_hash(raw, args.limit, {"backends": selected, "states": states_raw})
    run_id = runs.make_run_id(started, digest)
    clients = open_clients(config, selected, args.cache_mode, args.cache_file, args.replay)
    print(
        f"run {run_id}: {len(states)} states x ({len(selected)} backends + random), cache mode "
        f"{clients.mode}",
        flush=True,
    )
    rows, proposal_rows = execute(config, states, params, clients)
    run_dir = runs.create_run_dir(args.out, run_id, smoke=args.limit is not None)
    write_csv(run_dir / RESULTS_FILE, COLUMNS, rows)
    write_csv(run_dir / PROPOSALS_FILE, PROPOSAL_COLUMNS, proposal_rows)
    bundle = write_run_bundle(run_dir, clients)
    table = f"{config.summary.table}.tex"
    (run_dir / SUMMARY_FILE).write_text(
        summary_markdown(run_id, rows, proposal_rows, config), encoding="utf-8"
    )
    (run_dir / table).write_text(latex_table(run_id, rows), encoding="utf-8")
    prompt = load_prompt(PROPOSALS_PROMPT, config.proposals.prompt_version)
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
        outputs=[RESULTS_FILE, PROPOSALS_FILE, SUMMARY_FILE, table, BUNDLE_FILE],
        extra={
            "states_config": {"path": str(config.states), "config": states_raw},
            "prompts": {PROPOSALS_PROMPT: {"version": prompt.version, "sha256": prompt.sha256}},
            "sentinel": params.model_dump(mode="json"),
            "seeds": {
                "base_seed": config.base_seed,
                "random_seed": config.random_seed,
                "names_seed": config.names_seed,
            },
            "seed_rule": SEED_RULE,
            "n_states": len(states),
            "n_rows": len(rows),
            "n_proposal_rows": len(proposal_rows),
        },
    )
    runs.write_json(run_dir / "manifest.json", data)
    return run_dir


def regenerate(run_dir: Path) -> list[str]:
    """Regenerate summary.md and the LaTeX table of a run from its manifest, results.csv and
    proposals.csv (`sentinel reproduce --check`; no race is run again)."""
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    config = ProposalStudyConfig.model_validate(manifest["config"])
    rows = read_rows(run_dir / RESULTS_FILE)
    proposal_rows = read_rows(run_dir / PROPOSALS_FILE)
    table = f"{config.summary.table}.tex"
    (run_dir / SUMMARY_FILE).write_text(
        summary_markdown(manifest["run_id"], rows, proposal_rows, config), encoding="utf-8"
    )
    (run_dir / table).write_text(latex_table(manifest["run_id"], rows), encoding="utf-8")
    return [SUMMARY_FILE, table]


def main(argv: Sequence[str] | None = None) -> int:
    """Command line entry point; returns the exit status (3: stopped by a rate limit)."""
    return run_main(
        "sentinel.experiments.proposal_study",
        "RQ5 role 2: LLM proposals against a random control on recorded decision states.",
        argv,
        run,
    )


if __name__ == "__main__":
    sys.exit(main())
