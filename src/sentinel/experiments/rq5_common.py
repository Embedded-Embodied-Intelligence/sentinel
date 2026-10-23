"""What the RQ5 studies of WP6b share: backend settings, clients over the record/replay cache,
the scripted oracle of the smoke runs, the replay bundle, the manifest and the exit status of a
run stopped by a rate limit (as in WP6a; ADR-0018).

Each study (events, proposals, explanations, the online check) runs its LLM calls one after the
other through `<cache_dir>/<backend>.jsonl` (mode `auto` by default), or answers from a run's
replay bundle only (`--cache-file`, replay mode, no backend). A run stopped by `QuotaExhausted`
writes no run directory and exits with status 3; the same command resumes from the cache.
"""

import argparse
import hashlib
import shlex
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveInt

from sentinel.experiments import runs
from sentinel.experiments.forecast_summary import Estimate
from sentinel.experiments.wbs_config import GroqBackend, OllamaBackend
from sentinel.experiments.wbs_study import llm_provenance
from sentinel.experiments.wbs_study import make_client as make_real_client
from sentinel.forecasting.metrics import (
    FloatArray,
    cluster_resamples,
    percentile_interval,
    resampled_ratio,
)
from sentinel.llm import (
    CACHE_MODES,
    BaseClient,
    CacheEntry,
    CacheMode,
    FakeLlmClient,
    LlmCache,
    Message,
    QuotaExhausted,
)
from sentinel.llm.cache import write_bundle

BUNDLE_FILE = "llm_cache.jsonl.gz"
BUNDLE_LIMIT_BYTES = 10_000_000
EXIT_QUOTA = 3
PROGRESS_INTERVAL_S = 10.0
DEFAULT_RQ5_CACHE = Path("data/llm_cache/rq5")


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FakeBackend(_Frozen):
    """The scripted oracle of smoke runs: the true answer, with a seeded mistake in a share
    `error_rate` of the first answers (a study chooses the mistakes)."""

    kind: Literal["fake"]
    model: str = "oracle"
    error_rate: float = Field(default=0.3, ge=0, le=1)


Backend = Annotated[OllamaBackend | GroqBackend | FakeBackend, Field(discriminator="kind")]


class BootstrapSettings(_Frozen):
    """Resamples and seed of the bootstrap intervals and the name of the LaTeX table."""

    bootstrap_resamples: PositiveInt = 2000
    bootstrap_seed: NonNegativeInt = 2026
    table: str = Field(min_length=1)


class LlmStudyConfig(_Frozen):
    """Settings every RQ5 LLM study has: name, seed, cache directory, the study's backends in
    table order and the settings of every backend a run may select, the fake one included."""

    name: str = Field(min_length=1)
    base_seed: NonNegativeInt
    cache_dir: Path = DEFAULT_RQ5_CACHE
    backends: tuple[str, ...] = Field(min_length=1)
    backend: dict[str, Backend]
    summary: BootstrapSettings

    def selected(self, names: Sequence[str]) -> list[str]:
        chosen = list(names) or list(self.backends)
        unknown = [name for name in chosen if name not in self.backend]
        if unknown:
            raise ValueError(f"unknown backends {unknown}; the config has {sorted(self.backend)}")
        return chosen


Answer = Callable[[int], str]  # round index -> answer text


@dataclass
class Oracle:
    """Scripted backend of the RQ5 smoke runs: the runner registers, before each call, how the
    item's user message is answered in each round (repair rounds counted by the assistant
    messages of the conversation)."""

    answers: dict[str, Answer] = field(default_factory=dict)

    def register(self, content: str, answer: Answer) -> None:
        self.answers[content] = answer

    def __call__(self, messages: Sequence[Message]) -> str:
        first = next(m.content for m in messages if m.role == "user")
        if first not in self.answers:
            raise KeyError("the oracle has no answer registered for this message")
        return self.answers[first](sum(m.role == "assistant" for m in messages))


@dataclass
class Clients:
    """The clients, caches and oracles of a run's selected backends."""

    clients: dict[str, BaseClient]
    caches: dict[str, LlmCache | None]
    oracles: dict[str, Oracle]
    mode: CacheMode


def open_clients(
    config: LlmStudyConfig,
    selected: Sequence[str],
    cache_mode: CacheMode,
    cache_file: Path | None,
) -> Clients:
    """A client per selected backend over `<cache_dir>/<backend>.jsonl`, or over the replay
    bundle `cache_file` (replay mode)."""
    shared = None if cache_file is None else LlmCache(cache_file, readonly=True)
    mode: CacheMode = "replay" if cache_file is not None else cache_mode
    caches: dict[str, LlmCache | None] = {
        name: shared if shared is not None else LlmCache(config.cache_dir / f"{name}.jsonl")
        for name in selected
    }
    clients: dict[str, BaseClient] = {}
    oracles: dict[str, Oracle] = {}
    for name in selected:
        backend = config.backend[name]
        if isinstance(backend, FakeBackend):
            oracles[name] = Oracle()
            clients[name] = FakeLlmClient(
                oracles[name], model=backend.model, cache=caches[name], mode=mode
            )
        else:
            clients[name] = make_real_client(name, backend, caches[name], mode)
    return Clients(clients, caches, oracles, mode)


def item_seed(base_seed: int, *keys: str) -> int:
    """The LLM seed of an item, shared by the backends."""
    return runs.derive_seed(base_seed, "llm", *keys)


def text_rng_seed(*parts: str) -> int:
    """A seed from text (the oracle's mistakes): the first 8 bytes of a SHA-256."""
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "little")


def write_run_bundle(run_dir: Path, clients: Clients) -> tuple[int, int]:
    """The replay bundle of the entries the run used; returns (entries, bytes)."""
    used: dict[str, CacheEntry] = {}
    for cache in clients.caches.values():
        if cache is not None:
            used.update(cache.used)
    size = write_bundle(run_dir / BUNDLE_FILE, used.values())
    if size > BUNDLE_LIMIT_BYTES:
        print(f"warning: the replay bundle has {size} bytes, over {BUNDLE_LIMIT_BYTES}", flush=True)
    return len(used), size


def manifest(
    *,
    run_id: str,
    started: datetime,
    git: Mapping[str, Any],
    command: str,
    config_path: Path,
    raw_config: Mapping[str, Any],
    digest: str,
    limit: int | None,
    selected: Sequence[str],
    clients: Clients,
    cache_file: Path | None,
    bundle: tuple[int, int],
    outputs: Sequence[str],
    extra: Mapping[str, Any],
) -> dict[str, Any]:
    """The manifest fields every RQ5 LLM study writes, then the study's own `extra`; `git` is
    `runs.git_state()` taken when the run started, before any of its outputs existed."""
    finished = datetime.now(UTC)
    stats = [client.stats for client in clients.clients.values()]
    calls = sum(s.calls for s in stats)
    return {
        "run_id": run_id,
        "status": "completed",
        "smoke": limit is not None,
        "command": command,
        "config_path": str(config_path),
        "config": dict(raw_config),
        "config_hash": digest,
        "limit": limit,
        "backends": list(selected),
        "cache_mode": clients.mode,
        "cache_file": None if cache_file is None else str(cache_file),
        "git_commit": git["commit"],
        "git_dirty": git["dirty"],
        "start_utc": runs.utc_iso(started),
        "end_utc": runs.utc_iso(finished),
        "duration_s": round((finished - started).total_seconds(), 1),
        **runs.environment(),
        "llm": llm_provenance(clients.clients, clients.caches),
        "cache_hit_rate": None if not calls else round(sum(s.cache_hits for s in stats) / calls, 4),
        "bundle": {"file": BUNDLE_FILE, "entries": bundle[0], "bytes": bundle[1]},
        **extra,
        "outputs": list(outputs),
    }


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    """--config, --out, --limit, --backend, --cache-mode and --cache-file."""
    parser.add_argument("--config", type=Path, required=True, help="study config (TOML)")
    parser.add_argument(
        "--out", type=Path, required=True, help="results directory, e.g. results/wp6"
    )
    parser.add_argument("--limit", type=int, help="smoke run: only the first N items")
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


def run_main(
    prog: str,
    description: str,
    argv: Sequence[str] | None,
    run: Callable[[argparse.Namespace, str], Path],
) -> int:
    """Parse the common arguments, run, and map a rate-limit stop to exit status 3."""
    args_list = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog=f"python -m {prog}", description=description)
    add_common_arguments(parser)
    args = parser.parse_args(args_list)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.cache_file is not None and args.cache_mode != "auto":
        parser.error("--cache-file replays a bundle; it takes no --cache-mode")
    command = shlex.join(["python", "-m", prog, *args_list])
    try:
        run_dir = run(args, command)
    except QuotaExhausted as exc:
        hours = exc.retry_after_s / 3600
        print(
            f"stopped: {exc}\nEvery finished call is in the cache; run the same command again in "
            f"about {hours:.1f} h to resume (no run directory was written).",
            file=sys.stderr,
        )
        return EXIT_QUOTA
    print(f"done: {run_dir}", flush=True)
    return 0


def mean_interval(
    clusters: Sequence[int], values: Sequence[float], weights: FloatArray
) -> Estimate:
    """The mean of per-row values with a cluster-bootstrap 95 % interval (`weights` from
    `cluster_resamples` over the cluster ids 0 .. C - 1)."""
    size = weights.shape[1]
    codes = np.asarray(clusters, dtype=np.int64)
    total = np.bincount(codes, weights=np.asarray(values, dtype=np.float64), minlength=size)
    count = np.bincount(codes, minlength=size).astype(np.float64)
    value = float(total.sum() / count.sum()) if count.sum() else float("nan")
    return Estimate(value, *percentile_interval(resampled_ratio(weights, total, count)))


def resamples(n_clusters: int, settings: BootstrapSettings, key: str) -> FloatArray:
    """The cluster-bootstrap multiplicities of a run (seeded by the settings and `key`)."""
    rng = np.random.default_rng(runs.derive_seed(settings.bootstrap_seed, "bootstrap", key))
    return cluster_resamples(max(1, n_clusters), settings.bootstrap_resamples, rng)
