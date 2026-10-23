"""RQ1 study: LLM extraction of project models from descriptions generated from PSPLIB
instances, single-shot against validation with repair (WP6a; docs/experiments/plan.md).

    uv run python -m sentinel.experiments.wbs_study --config configs/wp6_rq1.toml \
        --out results/wp6 --backend ollama [--backend openrouter] [--limit N] \
        [--cache-mode auto|record|replay] [--cache-file <run_dir>/llm_cache.jsonl.gz] \
        [--replay ollama=<run_dir>/llm_cache.jsonl.gz]

For every instance (every `stride`-th of a set), style and selected backend one repair
session runs (`sentinel.wbs.extract.repair`); its first round is the single-shot condition and
its last round the repair condition, so both come from one session. Every LLM call goes
through the record/replay cache `<cache_dir>/<backend>.jsonl` (mode `auto` by default); with
`--cache-file` a run's replay bundle answers instead, without any backend, and with `--replay
<backend>=<file>` that file answers for that backend only (replay mode). Sessions run one
after the other (one GPU, one rate limit). The run directory is written once every session is
done: a run stopped by a rate limit or by missing credits (`QuotaExhausted`, exit status 3)
keeps its finished calls in the cache and the same command resumes it. Every CP-SAT schedule
is checked with `validate_schedule`. Outputs: `results.csv`, `rounds.csv`, `manifest.json`
(with the cache hit rates), the replay bundle `llm_cache.jsonl.gz` and the summaries of
`wbs_summary`.
"""

import argparse
import csv
import hashlib
import json
import shlex
import sys
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, assert_never

import numpy as np

from sentinel.data.psplib_loader import instance_path, list_instances, load_psplib
from sentinel.experiments import runs
from sentinel.experiments.rcpsp_benchmark import format_duration
from sentinel.experiments.wbs_config import (
    Backend,
    FakeBackend,
    GroqBackend,
    OllamaBackend,
    OpenRouterBackend,
    WbsStudyConfig,
)
from sentinel.experiments.wbs_summary import write_summaries
from sentinel.llm import (
    CACHE_MODES,
    BaseClient,
    CacheEntry,
    CacheMode,
    FakeLlmClient,
    GroqClient,
    LlmCache,
    LlmError,
    Message,
    OllamaClient,
    OpenAICompatibleClient,
    OpenRouterClient,
    QuotaExhausted,
    load_prompt,
)
from sentinel.llm.cache import write_bundle
from sentinel.model import ProjectInstance
from sentinel.wbs.extract import (
    EXTRACT_PROMPT,
    ISSUE_KINDS,
    REPAIR_PROMPT,
    Extraction,
    Issue,
    Round,
    Session,
    extraction_messages,
    repair,
    to_instance,
)
from sentinel.wbs.narrate import Style, narrate, parse_narration, truth
from sentinel.wbs.score import (
    InvalidScheduleError,
    Makespan,
    Scores,
    cpsat_makespan,
    makespan_error,
    score,
)

RESULTS_FILE = "results.csv"
ROUNDS_FILE = "rounds.csv"
BUNDLE_FILE = "llm_cache.jsonl.gz"
BUNDLE_LIMIT_BYTES = 10_000_000
CONDITIONS = ("single_shot", "repair")
EXIT_QUOTA = 3
PROGRESS_INTERVAL_S = 10.0
SEED_RULE = (
    "narrator seed of an instance = runs.derive_seed(narrator_seed, 'narrate', set, instance), "
    "shared by both styles; LLM seed of a session = runs.derive_seed(base_seed, 'llm', set, "
    "instance, style), shared by the backends and by every round of the session"
)
COLUMNS = (
    "set",
    "instance",
    "style",
    "backend",
    "model",
    "condition",
    "narrator_seed",
    "llm_seed",
    "rounds_used",
    "calls",
    "unchanged_rounds",
    "stopped",
    "valid",
    "n_issues",
    "issues",
    "n_true",
    "n_extracted",
    "n_matched",
    "activity_recall",
    "activity_precision",
    "unmatched_true",
    "unmatched_extracted",
    "all_true_edges",
    "true_edges",
    "extracted_edges",
    "correct_edges",
    "edge_precision",
    "edge_recall",
    "edge_f1",
    "durations_correct",
    "crews_correct",
    "duration_accuracy",
    "crew_accuracy",
    "team_roles",
    "team_correct",
    "team_accuracy",
    "team_exact",
    "exact",
    "makespan_true",
    "makespan_extracted",
    "makespan_rel_error",
    "cpsat_status_true",
    "cpsat_status_extracted",
    "prompt_tokens",
    "completion_tokens",
    "latency_s",
    "finish_reasons",
)
ROUND_COLUMNS = (
    "set",
    "instance",
    "style",
    "backend",
    "model",
    "round",
    "executed",
    "same_as_previous",
    "valid",
    "n_issues",
    "issues",
    "n_matched",
    "activity_recall",
    "activity_precision",
    "edge_precision",
    "edge_recall",
    "edge_f1",
    "duration_accuracy",
    "crew_accuracy",
    "team_accuracy",
    "exact",
    "prompt_tokens",
    "completion_tokens",
    "latency_s",
    "finish_reason",
    "output_error",
)

Row = dict[str, Any]


@dataclass(frozen=True)
class Subject:
    """A study instance: its narrator seed, the truth in the extraction schema and its texts."""

    set_name: str
    stem: str
    instance: ProjectInstance
    narrator_seed: int
    truth: Extraction
    texts: Mapping[Style, str]


def build_subjects(config: WbsStudyConfig, limit: int | None) -> list[Subject]:
    """The study's instances in (set, natural) order, the first `limit` per set if given."""
    subjects = []
    for set_cfg in config.sets:
        stems = list_instances(set_cfg.name, config.data_root)[:: set_cfg.stride][:limit]
        for stem in stems:
            instance = load_psplib(instance_path(set_cfg.name, stem, config.data_root))
            seed = runs.derive_seed(config.narrator_seed, "narrate", set_cfg.name, stem)
            texts = {style: narrate(instance, style=style, seed=seed) for style in config.styles}
            subjects.append(
                Subject(set_cfg.name, stem, instance, seed, truth(instance, seed), texts)
            )
    return subjects


def llm_seed(config: WbsStudyConfig, subject: Subject, style: Style) -> int:
    """The seed of a session (SEED_RULE)."""
    return runs.derive_seed(config.base_seed, "llm", subject.set_name, subject.stem, style)


class OracleResponder:
    """The fake backend of smoke runs: answers with the template parser's reading of the
    description, with seeded mistakes in the first k answers of a session (k uniform on
    0..max_faulty_rounds, drawn from the description): an activity left out although others
    name it as a predecessor, a duration one day too long and a dependency cycle. It finds the
    round by recognising its previous answer in the conversation (the latest of equal answers,
    so every round moves on), and keeps no state."""

    def __init__(self, max_faulty_rounds: int, seed: int) -> None:
        self.max_faulty_rounds = max_faulty_rounds
        self.seed = seed

    def __call__(self, messages: Sequence[Message]) -> str:
        text = messages[1].content
        index = 0
        if len(messages) > 2:
            previous = json.loads(messages[2].content)
            index = 1 + max(
                (i for i in range(self.max_faulty_rounds + 1) if self.answer(text, i) == previous),
                default=self.max_faulty_rounds,
            )
        return json.dumps(self.answer(text, index), indent=2)

    def answer(self, text: str, index: int) -> dict[str, Any]:
        """The oracle's answer number `index` (0: single shot) of a session on `text`."""
        words = np.frombuffer(hashlib.sha256(text.encode("utf-8")).digest(), dtype=np.uint32)
        session = np.random.SeedSequence([self.seed, *words.tolist()])
        faulty = int(np.random.default_rng(session).integers(self.max_faulty_rounds + 1))
        data: dict[str, Any] = json.loads(parse_narration(text).model_dump_json())
        if index < faulty:
            stream = np.random.SeedSequence(session.entropy, spawn_key=(index,))
            data = _with_mistakes(data, np.random.default_rng(stream))
        return data


def _with_mistakes(data: dict[str, Any], rng: np.random.Generator) -> dict[str, Any]:
    activities: list[dict[str, Any]] = data["activities"]
    named = sorted({p for a in activities for p in a["predecessors"]})
    if named:
        dropped = named[int(rng.integers(len(named)))]
        activities = [a for a in activities if a["name"] != dropped]
    longer = activities[int(rng.integers(len(activities)))]
    longer["duration_days"] += 1
    later = [a for a in activities if a["predecessors"]]
    if later:
        follower = later[int(rng.integers(len(later)))]
        leader = next((a for a in activities if a["name"] in follower["predecessors"]), None)
        if leader is not None:
            leader["predecessors"] = [*leader["predecessors"], follower["name"]]
    return {**data, "activities": activities}


def make_client(name: str, backend: Backend, cache: LlmCache | None, mode: CacheMode) -> BaseClient:
    """The client of a configured backend over its cache."""
    match backend:
        case OllamaBackend():
            return OllamaClient(
                backend.model,
                num_ctx=backend.num_ctx,
                digest=backend.digest,
                keep_alive=backend.keep_alive,
                timeout_s=backend.timeout_s,
                cache=cache,
                mode=mode,
            )
        case GroqBackend():
            return GroqClient(
                backend.model,
                tokens_per_minute=backend.tokens_per_minute,
                response_format=backend.response_format,
                extra=backend.options,
                max_wait_s=backend.max_wait_s,
                max_retries=backend.max_retries,
                timeout_s=backend.timeout_s,
                cache=cache,
                mode=mode,
            )
        case OpenRouterBackend():
            return OpenRouterClient(
                backend.model,
                tokens_per_minute=backend.tokens_per_minute,
                response_format=backend.response_format,
                extra={"provider": backend.provider.model_dump(mode="json"), **backend.options},
                max_wait_s=backend.max_wait_s,
                max_retries=backend.max_retries,
                timeout_s=backend.timeout_s,
                cache=cache,
                mode=mode,
            )
        case FakeBackend():
            responder = OracleResponder(
                backend.max_faulty_rounds, runs.derive_seed(0, "fake", name)
            )
            return FakeLlmClient(responder, model=backend.model, cache=cache, mode=mode)
        case _:
            assert_never(backend)


class Downstream:
    """CP-SAT makespans of the true instances and of valid extractions, each solved once."""

    def __init__(self, config: WbsStudyConfig) -> None:
        self.settings = config.cpsat
        self._true: dict[str, Makespan] = {}
        self._extracted: dict[str, Makespan] = {}

    def true(self, subject: Subject) -> Makespan:
        key = f"{subject.set_name}/{subject.stem}"
        if key not in self._true:
            self._true[key] = cpsat_makespan(subject.instance, self.settings)
        return self._true[key]

    def extracted(self, extraction: Extraction, name: str) -> Makespan:
        key = hashlib.sha256(extraction.model_dump_json().encode("utf-8")).hexdigest()
        if key not in self._extracted:
            self._extracted[key] = cpsat_makespan(to_instance(extraction, name=name), self.settings)
        return self._extracted[key]


def issue_counts(issues: Sequence[Issue]) -> str:
    """`kind:count` per issue kind, in the order of ISSUE_KINDS, `;`-separated."""
    counts = Counter(issue.kind for issue in issues)
    return ";".join(f"{kind}:{counts[kind]}" for kind in ISSUE_KINDS if counts[kind])


def _round(value: float) -> float | None:
    return None if value != value else round(value, 6)  # NaN (undefined) -> empty cell


def score_round(subject: Subject, step: Round) -> Scores:
    return score(step.response.parsed, subject.truth, step.issues)


def score_columns(scores: Scores) -> Row:
    """The metric columns shared by results.csv and rounds.csv."""
    return {
        "valid": scores.valid,
        "n_issues": scores.n_issues,
        "n_matched": scores.n_matched,
        "activity_recall": _round(scores.activity_recall),
        "activity_precision": _round(scores.activity_precision),
        "edge_precision": _round(scores.edge_precision),
        "edge_recall": _round(scores.edge_recall),
        "edge_f1": _round(scores.edge_f1),
        "duration_accuracy": _round(scores.duration_accuracy),
        "crew_accuracy": _round(scores.crew_accuracy),
        "team_accuracy": _round(scores.team_accuracy),
        "exact": scores.exact,
    }


def session_rows(
    config: WbsStudyConfig,
    subject: Subject,
    style: Style,
    backend: str,
    model: str,
    session: Session,
    downstream: Downstream,
) -> tuple[list[Row], list[Row]]:
    """The two condition rows of a session and its rows for rounds 0..max_repair_rounds (a
    round after the session's last carries its last answer, `executed` 0). A repair round is
    unchanged if its answer parses to the previous round's answer."""
    seed = llm_seed(config, subject, style)
    unchanged = [False] + [
        now.response.parsed is not None and now.response.parsed == before.response.parsed
        for before, now in zip(session.rounds, session.rounds[1:], strict=False)
    ]
    base = {"set": subject.set_name, "instance": subject.stem, "style": style}
    base |= {"backend": backend, "model": model}
    round_rows = []
    for index in range(config.extraction.max_repair_rounds + 1):
        step = session.rounds[min(index, len(session.rounds) - 1)]
        executed = index < len(session.rounds)
        response = step.response
        round_rows.append(
            {
                **base,
                "round": index,
                "executed": int(executed),
                "same_as_previous": int(unchanged[index]) if executed else None,
                "issues": issue_counts(step.issues),
                **score_columns(score_round(subject, step)),
                "prompt_tokens": response.prompt_tokens if executed else None,
                "completion_tokens": response.completion_tokens if executed else None,
                "latency_s": response.latency_s if executed else None,
                "finish_reason": response.finish_reason if executed else None,
                "output_error": response.error.kind if executed and response.error else None,
            }
        )
    rows = []
    for condition, used in (("single_shot", session.rounds[:1]), ("repair", session.rounds)):
        final = used[-1]
        scores = score_round(subject, final)
        makespan_true = makespan = error = None
        status_true = status = None
        if final.valid and final.response.value is not None:
            true_run = downstream.true(subject)
            extracted = downstream.extracted(final.response.value, f"{subject.stem}-extracted")
            makespan_true, status_true = true_run.makespan, true_run.status
            makespan, status = extracted.makespan, extracted.status
            error = round(makespan_error(makespan, makespan_true), 6)
        rows.append(
            {
                **base,
                "condition": condition,
                "narrator_seed": subject.narrator_seed,
                "llm_seed": seed,
                "rounds_used": len(used) - 1,
                "calls": len(used),
                "unchanged_rounds": sum(unchanged[1 : len(used)]),
                "stopped": session.stopped if condition == "repair" else None,
                **score_columns(scores),
                "issues": issue_counts(final.issues),
                "n_true": scores.n_true,
                "n_extracted": scores.n_extracted,
                "unmatched_true": " | ".join(scores.unmatched_true),
                "unmatched_extracted": " | ".join(scores.unmatched_extracted),
                "all_true_edges": scores.all_true_edges,
                "true_edges": scores.true_edges,
                "extracted_edges": scores.extracted_edges,
                "correct_edges": scores.correct_edges,
                "durations_correct": scores.durations_correct,
                "crews_correct": scores.crews_correct,
                "team_roles": scores.team_roles,
                "team_correct": scores.team_correct,
                "team_exact": scores.team_exact,
                "makespan_true": makespan_true,
                "makespan_extracted": makespan,
                "makespan_rel_error": error,
                "cpsat_status_true": status_true,
                "cpsat_status_extracted": status,
                "prompt_tokens": sum(r.response.prompt_tokens for r in used),
                "completion_tokens": sum(r.response.completion_tokens for r in used),
                "latency_s": round(sum(r.response.latency_s for r in used), 3),
                "finish_reasons": "|".join(str(r.response.finish_reason) for r in used),
            }
        )
    return rows, round_rows


@dataclass(frozen=True)
class Planned:
    """A session to run: subject, style and backend name."""

    subject: Subject
    style: Style
    backend: str


def plan_sessions(
    config: WbsStudyConfig, subjects: Sequence[Subject], backends: Sequence[str]
) -> list[Planned]:
    """Sessions in (instance, style, backend) order."""
    return [
        Planned(subject, style, backend)
        for subject in subjects
        for style in config.styles
        for backend in backends
    ]


def first_call_cached(config: WbsStudyConfig, planned: Planned, client: BaseClient) -> bool:
    """Whether the session's single-shot request would be answered from the client's cache."""
    if client.cache is None or client.mode == "record":
        return False
    request = client.request(
        extraction_messages(
            planned.subject.texts[planned.style],
            load_prompt(EXTRACT_PROMPT, config.extraction.prompt_version),
        ),
        schema=Extraction,
        temperature=config.extraction.temperature,
        seed=llm_seed(config, planned.subject, planned.style),
        max_tokens=config.extraction.max_tokens,
    )
    return request.key in client.cache


def recorded_call(cache: LlmCache | None, client: BaseClient) -> tuple[float, float] | None:
    """Mean recorded latency and tokens per call of the client's model in its cache."""
    if cache is None:
        return None
    entries = [
        e for e in cache.entries() if e.backend == client.backend and e.model == client.model
    ]
    if not entries:
        return None
    latency = sum(e.reply.latency_s for e in entries) / len(entries)
    tokens = sum(e.reply.prompt_tokens + e.reply.completion_tokens for e in entries) / len(entries)
    return latency, tokens


def print_plan(
    config: WbsStudyConfig,
    planned: Sequence[Planned],
    clients: Mapping[str, BaseClient],
    caches: Mapping[str, LlmCache | None],
) -> None:
    """Per backend: sessions, sessions starting from the cache and a duration estimate from
    the recorded calls (1 to 1 + max_repair_rounds calls per new session)."""
    most = 1 + config.extraction.max_repair_rounds
    for name, client in clients.items():
        mine = [p for p in planned if p.backend == name]
        cached = sum(first_call_cached(config, p, client) for p in mine)
        new = len(mine) - cached
        line = f"{name} ({client.model}): {len(mine)} sessions, {cached} start from the cache"
        recorded = recorded_call(caches[name], client)
        if new and recorded is not None:
            latency, tokens = recorded
            line += (
                f"; {new} new sessions at {latency:.1f} s per recorded call: "
                f"{format_duration(new * latency)} to {format_duration(new * most * latency)}"
            )
            backend = config.backend[name]
            if isinstance(backend, GroqBackend) and backend.tokens_per_day:
                days = (
                    new * tokens / backend.tokens_per_day,
                    new * most * tokens / backend.tokens_per_day,
                )
                line += f", {days[0]:.1f} to {days[1]:.1f} days at {tokens:.0f} tokens per call"
        elif new:
            line += f"; {new} new sessions, no recorded calls to estimate from"
        print(line, flush=True)


def execute(
    config: WbsStudyConfig, planned: Sequence[Planned], clients: Mapping[str, BaseClient]
) -> tuple[list[Row], list[Row]]:
    """Run the sessions in order, with a progress line at most every ~10 s."""
    downstream = Downstream(config)
    rows: list[Row] = []
    round_rows: list[Row] = []
    started = last = time.monotonic()
    busy = 0.0
    live_sessions = 0
    for done, item in enumerate(planned, start=1):
        client = clients[item.backend]
        calls_before = client.stats.backend_calls
        begun = time.monotonic()
        session = repair(
            client,
            item.subject.texts[item.style],
            seed=llm_seed(config, item.subject, item.style),
            settings=config.extraction,
        )
        if client.stats.backend_calls > calls_before:
            busy += time.monotonic() - begun
            live_sessions += 1
        new_rows, new_round_rows = session_rows(
            config, item.subject, item.style, item.backend, client.model, session, downstream
        )
        rows += new_rows
        round_rows += new_round_rows
        now = time.monotonic()
        if now - last >= PROGRESS_INTERVAL_S or done == len(planned):
            final = session.final
            pace = f", {busy / live_sessions:.0f} s per new session" if live_sessions else ""
            print(
                f"[{format_duration(now - started)}] {done}/{len(planned)} sessions{pace}; last: "
                f"{item.backend} {item.style} {item.subject.stem}, {session.repair_rounds} repair "
                f"rounds, {'valid' if final.valid else f'{len(final.issues)} issues'}",
                flush=True,
            )
            last = now
    return rows, round_rows


def write_csv(path: Path, columns: Sequence[str], rows: Sequence[Row]) -> None:
    """CSV with the given columns; None becomes an empty cell, booleans 0/1."""
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: int(v) if isinstance(v, bool) else v for k, v in row.items()})


def data_provenance(config: WbsStudyConfig) -> dict[str, Any]:
    """Content hashes of the instance sets from the data MANIFEST.json."""
    path = config.data_root / "MANIFEST.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    instances = data.get("instances", {})
    return {
        "root": str(config.data_root),
        "instances_content_sha256": {
            s.name: instances.get(s.name, {}).get("content_sha256") for s in config.sets
        },
    }


def llm_provenance(
    clients: Mapping[str, BaseClient], caches: Mapping[str, LlmCache | None]
) -> dict[str, Any]:
    """Per backend: model, digest, cache file and stats, and what its replies report (for
    OpenRouter the routing, the providers that served the answers and their recorded cost)."""
    result: dict[str, Any] = {}
    for name, client in clients.items():
        cache = caches[name]
        used = [
            e
            for e in ([] if cache is None else cache.used.values())
            if (e.backend, e.model) == (client.backend, client.model)
        ]
        meta = [e.reply.meta for e in used]
        record: dict[str, Any] = {
            "kind": client.backend,
            "model": client.model,
            "reported_models": sorted({e.reply.model for e in used}),
            "digest": client.digest if isinstance(client, OllamaClient) else None,
            "cache_file": None if cache is None else str(cache.path),
            "cache_mode": client.mode,
            "store_prompts": None if cache is None else cache.store_prompts,
            "stats": client.stats.as_dict(),
            "recorded_utc": [
                min((e.recorded_utc for e in used), default=None),
                max((e.recorded_utc for e in used), default=None),
            ],
        }
        if isinstance(client, OllamaClient) and client.stats.backend_calls:
            try:
                record["server_version"] = client.server_version()
            except LlmError:
                record["server_version"] = None
        if isinstance(client, OpenAICompatibleClient):
            record["retries"] = client.retries
            record["rate_limit_wait_s"] = (
                None if client.limiter is None else round(client.limiter.waited_s, 1)
            )
            record["system_fingerprints"] = sorted(
                {str(m["system_fingerprint"]) for m in meta if "system_fingerprint" in m}
            )
            for header in ("limit_tokens", "limit_requests"):
                record[f"reported_{header}"] = sorted({str(m[header]) for m in meta if header in m})
        if isinstance(client, OpenRouterClient):
            record["provider_routing"] = dict(client.routing)
            record["providers"] = dict(
                sorted(Counter(str(m.get("provider", "unreported")) for m in meta).items())
            )
            costs = [cost for m in meta if isinstance(cost := m.get("cost"), int | float)]
            record["recorded_cost"] = round(sum(costs), 6)  # OpenRouter credits (USD)
        result[name] = record
    return result


def add_replay_argument(parser: argparse.ArgumentParser) -> None:
    """--replay BACKEND=FILE (repeatable)."""
    parser.add_argument(
        "--replay",
        action="append",
        default=[],
        metavar="BACKEND=FILE",
        help="answer this backend from FILE only, a replay bundle or cache file (replay mode: a "
        "miss is an error); the other backends use --cache-mode (repeatable)",
    )


def stop_message(exc: QuotaExhausted) -> str:
    """What a run stopped by a rate limit or by missing credits prints (exit status 3)."""
    return (
        f"stopped: {exc}\nEvery finished call is in the cache; {exc.resume_hint} to resume (no "
        "run directory was written)."
    )


def parse_replay(values: Sequence[str]) -> dict[str, Path]:
    """The `--replay BACKEND=FILE` values as {backend: file}; a malformed value or a backend
    named twice is a ValueError."""
    replay: dict[str, Path] = {}
    for value in values:
        name, sep, file = value.partition("=")
        if not sep or not name or not file:
            raise ValueError(f"--replay takes BACKEND=FILE, got {value!r}")
        if name in replay:
            raise ValueError(f"--replay names the backend {name!r} twice")
        replay[name] = Path(file)
    return replay


def open_caches(
    selected: Sequence[str],
    cache_dir: Path,
    cache_mode: CacheMode,
    cache_file: Path | None,
    replay: Mapping[str, Path],
    *,
    store_prompts: bool,
) -> tuple[dict[str, LlmCache | None], dict[str, CacheMode]]:
    """The cache and mode of every selected backend: its working cache
    `<cache_dir>/<backend>.jsonl` in `cache_mode`; with `cache_file` that bundle for every
    backend (replay mode); with `replay` the given file for that backend only (read-only,
    replay mode, so a miss is an error)."""
    unknown = sorted(set(replay) - set(selected))
    if unknown:
        raise ValueError(f"--replay names backends the run does not select: {unknown}")
    if cache_file is not None and replay:
        raise ValueError("--cache-file replays every backend; it takes no --replay")
    shared = (
        None
        if cache_file is None
        else LlmCache(cache_file, readonly=True, store_prompts=store_prompts)
    )
    caches: dict[str, LlmCache | None] = {}
    modes: dict[str, CacheMode] = {}
    for name in selected:
        if shared is not None:
            caches[name], modes[name] = shared, "replay"
        elif name in replay:
            caches[name] = LlmCache(replay[name], readonly=True, store_prompts=store_prompts)
            modes[name] = "replay"
        else:
            caches[name] = LlmCache(cache_dir / f"{name}.jsonl", store_prompts=store_prompts)
            modes[name] = cache_mode
    return caches, modes


def run_study(
    config_path: Path,
    out: Path,
    limit: int | None,
    backends: Sequence[str],
    cache_mode: CacheMode,
    cache_file: Path | None,
    command: str,
    replay: Mapping[str, Path] | None = None,
) -> Path:
    """Run the selected backends' sessions and write the run directory; returns its path."""
    raw_config = runs.load_toml(config_path)
    config = WbsStudyConfig.model_validate(raw_config)
    selected = list(backends) or list(config.backends)
    unknown = [name for name in selected if name not in config.backend]
    if unknown:
        raise ValueError(f"unknown backends {unknown}; the config has {sorted(config.backend)}")
    started = datetime.now(UTC)
    digest = runs.config_hash(raw_config, limit, {"backends": selected})
    run_id = runs.make_run_id(started, digest)
    git = runs.git_state()
    subjects = build_subjects(config, limit)
    replay = dict(replay or {})
    caches, modes = open_caches(
        selected,
        config.cache_dir,
        cache_mode,
        cache_file,
        replay,
        store_prompts=config.store_prompts,
    )
    mode: CacheMode = "replay" if cache_file is not None else cache_mode
    clients = {
        name: make_client(name, config.backend[name], caches[name], modes[name])
        for name in selected
    }
    planned = plan_sessions(config, subjects, selected)
    print(
        f"run {run_id}: {len(planned)} sessions ({len(subjects)} instances x "
        f"{len(config.styles)} styles x {len(selected)} backends), cache mode {mode}",
        flush=True,
    )
    print_plan(config, planned, clients, caches)
    rows, round_rows = execute(config, planned, clients)
    run_dir = runs.create_run_dir(out, run_id, smoke=limit is not None)
    write_csv(run_dir / RESULTS_FILE, COLUMNS, rows)
    write_csv(run_dir / ROUNDS_FILE, ROUND_COLUMNS, round_rows)
    used: dict[str, CacheEntry] = {}
    for cache in caches.values():
        if cache is not None:
            used.update(cache.used)
    bundle_bytes = write_bundle(run_dir / BUNDLE_FILE, used.values())
    if bundle_bytes > BUNDLE_LIMIT_BYTES:
        print(
            f"warning: the replay bundle has {bundle_bytes} bytes, over {BUNDLE_LIMIT_BYTES}",
            flush=True,
        )
    summaries = write_summaries(run_dir, run_id, config)
    stats = [client.stats for client in clients.values()]
    calls = sum(s.calls for s in stats)
    finished = datetime.now(UTC)
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "status": "completed",
        "smoke": limit is not None,
        "command": command,
        "config_path": str(config_path),
        "config": raw_config,
        "config_hash": digest,
        "limit": limit,
        "backends": selected,
        "cache_mode": mode,
        "cache_file": None if cache_file is None else str(cache_file),
        "replay": {name: str(path) for name, path in replay.items()},
        "git_commit": git["commit"],
        "git_dirty": git["dirty"],
        "start_utc": runs.utc_iso(started),
        "end_utc": runs.utc_iso(finished),
        "duration_s": round((finished - started).total_seconds(), 1),
        **runs.environment(),
        "llm": llm_provenance(clients, caches),
        "cache_hit_rate": None if not calls else round(sum(s.cache_hits for s in stats) / calls, 4),
        "prompts": {
            name: {
                "version": config.extraction.prompt_version,
                "sha256": load_prompt(name, config.extraction.prompt_version).sha256,
            }
            for name in (EXTRACT_PROMPT, REPAIR_PROMPT)
        },
        "seeds": {
            "base_seed": config.base_seed,
            "narrator_seed": config.narrator_seed,
            "rule": SEED_RULE,
            "narrator": {f"{s.set_name}/{s.stem}": s.narrator_seed for s in subjects},
        },
        "n_sessions": len(planned),
        "n_rows": len(rows),
        "n_round_rows": len(round_rows),
        "bundle": {"file": BUNDLE_FILE, "entries": len(used), "bytes": bundle_bytes},
        "data": data_provenance(config),
        "results_file": RESULTS_FILE,
        "outputs": [RESULTS_FILE, ROUNDS_FILE, BUNDLE_FILE, *summaries],
    }
    runs.write_json(run_dir / "manifest.json", manifest)
    return run_dir


def main(argv: Sequence[str] | None = None) -> int:
    """Command line entry point; returns the exit status (3: stopped by a rate limit)."""
    args_list = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="python -m sentinel.experiments.wbs_study",
        description="RQ1: LLM extraction of WBS models, single-shot against repair.",
    )
    parser.add_argument("--config", type=Path, required=True, help="study config (TOML)")
    parser.add_argument(
        "--out", type=Path, required=True, help="results directory, e.g. results/wp6"
    )
    parser.add_argument("--limit", type=int, help="smoke run: only the first N instances per set")
    parser.add_argument(
        "--backend",
        action="append",
        default=[],
        help="backend of the config to run (repeatable; default: the config's backends)",
    )
    parser.add_argument("--cache-mode", choices=CACHE_MODES, default="auto")
    parser.add_argument(
        "--cache-file", type=Path, help="answer from this replay bundle only (replay mode)"
    )
    add_replay_argument(parser)
    args = parser.parse_args(args_list)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.cache_file is not None and args.cache_mode != "auto":
        parser.error("--cache-file replays a bundle; it takes no --cache-mode")
    if args.cache_file is not None and args.replay:
        parser.error("--cache-file replays every backend; it takes no --replay")
    try:
        replay = parse_replay(args.replay)
    except ValueError as exc:
        parser.error(str(exc))
    command = shlex.join(["python", "-m", "sentinel.experiments.wbs_study", *args_list])
    try:
        run_dir = run_study(
            args.config,
            args.out,
            args.limit,
            args.backend,
            args.cache_mode,
            args.cache_file,
            command,
            replay,
        )
    except QuotaExhausted as exc:
        print(stop_message(exc), file=sys.stderr)
        return EXIT_QUOTA
    except InvalidScheduleError as exc:
        print(f"error: invalid schedule, run aborted: {exc}", file=sys.stderr)
        return 1
    print(f"done: {run_dir}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
