"""Record the decision states of RQ5 and draw their stratified sample (WP6b).

Usage:
    uv run python scripts/record_decision_states.py --config configs/wp6_rq5_states.toml
        [--limit N] [--workers W] [--write-sample]

Reruns Sentinel `full` (Lambda = 3) on the worlds of the config (every `stride`-th instance,
each lambda_A, one replication: worlds of the WP5 main study) and stores every deliberation
that passed the needs gate (observation, plan, `DecisionRecord`, the run's seed) in
`<states_dir>/<set>/<instance>_la<lambda_A>_r<r>.jsonl.gz`, with `index.csv` and
`manifest.json` (provenance; every rerun's makespan and deliberation counts against the WP5
results, 0 mismatches expected). Every realised schedule is checked. Then it draws the sample
of `[sample]` (`stratified_sample`) and prints it per stratum; `--write-sample` writes its ids
into the config, below the sample marker. With `--limit N` only the first N instances run, into
`<states_dir>-smoke`, and no sample is drawn. Runs are tasks of a spawn pool, one per (instance,
lambda_A).
"""

import argparse
import csv
import gzip
import json
import multiprocessing
import shlex
import sys
import time
from collections.abc import Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sentinel.experiments import runs
from sentinel.experiments.decision_states import (
    INDEX_FILE,
    StatesConfig,
    id_key,
    read_index,
    record_task,
    stratified_sample,
    stratum_counts,
    worlds,
    write_index,
)
from sentinel.experiments.rcpsp_benchmark import format_duration

SAMPLE_MARKER = "# --- sample ids: written by scripts/record_decision_states.py --write-sample ---"
PROGRESS_INTERVAL_S = 10.0


def wp5_runs(config: StatesConfig) -> dict[tuple[str, float, int], dict[str, str]]:
    """The WP5 rows of `wp5_policy` by (instance, lambda_A, replication)."""
    if config.wp5_results is None:
        return {}
    with gzip.open(config.wp5_results, "rt", encoding="utf-8") as handle:
        return {
            (row["instance"], float(row["lambda_a"]), int(row["replication"])): row
            for row in csv.DictReader(handle)
            if row["policy"] == config.wp5_policy and row["set"] == config.set_name
        }


def write_sample(path: Path, ids: Sequence[str]) -> None:
    """Replace everything after the sample marker of the config with `ids = [...]`."""
    text = path.read_text(encoding="utf-8")
    if SAMPLE_MARKER not in text:
        raise ValueError(f"{path} has no sample marker line {SAMPLE_MARKER!r}")
    head = text[: text.index(SAMPLE_MARKER) + len(SAMPLE_MARKER)]
    lines = "".join(f'  "{state}",\n' for state in ids)
    path.write_text(f"{head}\nids = [\n{lines}]\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--limit", type=int, help="smoke run: only the first N instances")
    parser.add_argument("--workers", type=int, help="processes (default: the config's)")
    parser.add_argument("--write-sample", action="store_true", help="write the ids to the config")
    args = parser.parse_args(args_list)
    raw = runs.load_toml(args.config)
    config = StatesConfig.model_validate(raw)
    started = datetime.now(UTC)
    git = runs.git_state()  # taken before any output of the run exists
    out = config.states_dir if args.limit is None else Path(f"{config.states_dir}-smoke")
    out.mkdir(parents=True, exist_ok=True)
    todo = worlds(config, args.limit)
    reference = wp5_runs(config)
    known = [reference.get((w.instance, w.lambda_a, w.replication)) for w in todo]
    estimate = sum(float(row["runtime_s"]) for row in known if row is not None)
    workers = args.workers or config.max_workers
    print(
        f"{len(todo)} runs on {workers} workers into {out}; the WP5 runs took "
        f"{format_duration(estimate)} of CPU (about {format_duration(estimate / workers)} here)",
        flush=True,
    )
    context = multiprocessing.get_context("spawn")
    done: list[dict[str, Any]] = []
    last = began = time.monotonic()
    with ProcessPoolExecutor(max_workers=workers, mp_context=context) as pool:
        pending: set[Future[dict[str, Any]]] = {
            pool.submit(record_task, config, world, out) for world in todo
        }
        while pending:
            finished, pending = wait(pending, return_when=FIRST_COMPLETED)
            done += [future.result() for future in finished]
            now = time.monotonic()
            if now - last >= PROGRESS_INTERVAL_S or not pending:
                states = sum(item["states"] for item in done)
                print(
                    f"[{format_duration(now - began)}] {len(done)}/{len(todo)} runs, "
                    f"{states} states",
                    flush=True,
                )
                last = now
    rows = sorted((row for item in done for row in item["rows"]), key=lambda r: id_key(r["id"]))
    write_index(out / INDEX_FILE, rows)
    mismatches = []
    for item in done:
        world = item["world"]
        wp5 = reference.get((world.instance, world.lambda_a, world.replication))
        if wp5 is None:
            continue
        gated = int(wp5["deliberations"]) - int(wp5["gate_exits"])
        if int(wp5["makespan"]) != item["makespan"] or gated != item["states"]:
            mismatches.append(f"{world.instance} la{world.lambda_a:g}")
    finished_at = datetime.now(UTC)
    manifest: dict[str, Any] = {
        "name": config.name,
        "command": shlex.join(["python", "scripts/record_decision_states.py", *args_list]),
        "config_path": str(args.config),
        "config": raw,
        "config_hash": runs.config_hash(raw, args.limit),
        "limit": args.limit,
        **git,
        "start_utc": runs.utc_iso(started),
        "end_utc": runs.utc_iso(finished_at),
        "duration_s": round((finished_at - started).total_seconds(), 1),
        **runs.environment(),
        "workers": workers,
        "runs": len(done),
        "states": len(rows),
        "run_cpu_s": round(sum(item["wall_time_s"] for item in done), 1),
        "wp5_checked": sum(
            reference.get((i["world"].instance, i["world"].lambda_a, i["world"].replication))
            is not None
            for i in done
        ),
        "wp5_mismatches": mismatches,
        "seed_rule": "seed of (instance, replication r) = runs.derive_seed(base_seed, set, "
        "instance, str(r)), the WP2b and WP5 seed; the rollouts of epoch t use "
        "derive_seed(seed, 'sentinel', str(t)) as in Sentinel",
    }
    runs.write_json(out / "manifest.json", manifest)
    print(
        f"{len(rows)} states of {len(done)} runs; WP5 check: {manifest['wp5_checked']} runs, "
        f"{len(mismatches)} mismatches {mismatches[:5]}",
        flush=True,
    )
    if mismatches:
        return 1
    if args.limit is None:
        index = read_index(out / INDEX_FILE)
        sample = stratified_sample(index, config.sample.size, config.sample.seed)
        print(json.dumps(stratum_counts(index, sample), indent=1), flush=True)
        if args.write_sample:
            write_sample(args.config, sample)
            print(f"wrote {len(sample)} sample ids to {args.config}", flush=True)
        elif tuple(sample) != config.sample.ids:
            print("the config's sample ids differ from the drawn sample", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
