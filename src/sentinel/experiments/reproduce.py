"""`sentinel reproduce` (WP7, ADR-0020): check that the committed results regenerate, and say
how to recompute them.

- `--check`: every run of `configs/paper.toml` is verified as by `sentinel paper`; its
  summaries are regenerated from its committed data files in a temporary copy, with the
  provenance (commit, time) of its committed summary manifest, and compared byte for byte with
  the committed summaries; then `paper/generated/` (English and Polish) is regenerated in a
  temporary directory with the provenance of the committed `MANIFEST.json` and compared. No
  experiment is recomputed and no LLM is called (the RQ1 error analysis replays its sessions
  from the run's bundle and narrates the texts from `data/psplib`). Exit status 0 when every
  file is identical, 1 otherwise.
- `--commands`: the commands that recompute each run, as its manifest recorded them, in
  dependency order with the prerequisites and the recorded durations; LLM runs also get the
  replay from their committed bundle, which needs no key.

    uv run sentinel reproduce --check
"""

import filecmp
import json
import shlex
import shutil
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from sentinel.experiments.paper import (
    MANIFEST_NAME,
    ROLES,
    PaperConfig,
    RunRefused,
    generate,
    load_runs,
)
from sentinel.experiments.runs import load_toml

SUMMARY_MANIFEST = "summary_manifest.json"
LLM_RUNNERS = (
    "sentinel.experiments.wbs_study",
    "sentinel.experiments.event_study",
    "sentinel.experiments.proposal_study",
    "sentinel.experiments.explanation_study",
    "sentinel.experiments.online_study",
)
PREREQUISITES = (
    ("uv sync", "environment from uv.lock"),
    ("uv run python scripts/fetch_psplib.py --sets j30 j60", "PSPLIB data into data/psplib"),
    ("uv run sentinel baselines --set j30 --method cpsat_det", "baseline plans (WP2b)"),
    ("uv run sentinel baselines --set j60 --method cpsat_det", "baseline plans (WP2b)"),
    (
        "uv run python scripts/record_decision_states.py --config configs/wp6_rq5_states.toml",
        "RQ5 decision states (WP6b), after the RQ4 runs",
    ),
)


def runner(manifest: Mapping[str, Any]) -> str:
    """The module a run was started with (`python -m <module> ...`)."""
    words = shlex.split(str(manifest.get("command", "")))
    if "-m" not in words or words.index("-m") + 1 >= len(words):
        raise ValueError(f"the manifest's command names no module: {manifest.get('command')!r}")
    return words[words.index("-m") + 1]


def summary_files(run_dir: Path) -> set[str]:
    """The committed summaries of a run directory: summary.md, its manifest, tables, figures."""
    return {
        p.name
        for p in run_dir.iterdir()
        if p.name in ("summary.md", SUMMARY_MANIFEST) or p.suffix in (".tex", ".pdf", ".png")
    }


def regenerate_summaries(run_dir: Path, pinned: Mapping[str, Any] | None) -> list[str]:
    """Regenerate the summaries of a run directory in place with the code of its runner."""
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    run_id = str(manifest["run_id"])
    module = runner(manifest)
    # Imported per runner so that a check loads only what it needs.
    if module == "sentinel.experiments.rcpsp_benchmark":
        from sentinel.experiments import rcpsp_summary
        from sentinel.experiments.rcpsp_config import BenchmarkConfig

        config = BenchmarkConfig.model_validate(manifest["config"])
        return rcpsp_summary.write_summaries(run_dir, run_id, config)
    if module == "sentinel.experiments.simulation_study":
        from sentinel.experiments import simulation_summary
        from sentinel.experiments.simulation_config import StudyConfig

        study = StudyConfig.model_validate(manifest["config"])
        return simulation_summary.write_summaries(
            run_dir, run_id, study, str(manifest["results_file"])
        )
    if module == "sentinel.experiments.forecast_study":
        from sentinel.experiments import forecast_summary

        return forecast_summary.regenerate(run_dir, pinned=pinned).files
    if module == "sentinel.experiments.policy_study":
        from sentinel.experiments import policy_summary

        return policy_summary.regenerate(run_dir, pinned=pinned).files
    if module == "sentinel.experiments.wbs_study":
        from sentinel.experiments import wbs_summary

        return wbs_summary.regenerate(run_dir, pinned=pinned)
    if module == "sentinel.experiments.event_study":
        from sentinel.experiments import event_study

        return event_study.regenerate(run_dir)
    if module == "sentinel.experiments.proposal_study":
        from sentinel.experiments import proposal_study

        return proposal_study.regenerate(run_dir)
    if module == "sentinel.experiments.explanation_study":
        from sentinel.experiments import explanation_study

        return explanation_study.regenerate(run_dir)
    if module == "sentinel.experiments.online_study":
        from sentinel.experiments import online_study

        return online_study.regenerate(run_dir)
    raise ValueError(f"no summary generator for runs of {module}")


def differing(expected: Path, actual: Path, names: Sequence[str]) -> list[str]:
    """The names whose files differ in bytes, or exist on one side only."""
    result = []
    for name in names:
        left, right = expected / name, actual / name
        if not (left.is_file() and right.is_file() and filecmp.cmp(left, right, shallow=False)):
            result.append(name)
    return result


def check_run(run_dir: Path, scratch: Path) -> tuple[int, list[str]]:
    """Regenerate a run's summaries in a copy; the number of summary files and those that
    differ from the committed ones."""
    copy = scratch / run_dir.name
    shutil.copytree(run_dir, copy)
    recorded = run_dir / SUMMARY_MANIFEST
    pinned = json.loads(recorded.read_text(encoding="utf-8")) if recorded.is_file() else None
    written = set(regenerate_summaries(copy, pinned))
    names = sorted(summary_files(run_dir) | written)
    return len(names), differing(run_dir, copy, names)


def tree_files(root: Path) -> set[str]:
    """Every file under `root`, as a relative POSIX path."""
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def check(config_path: Path) -> int:
    """`--check`: regenerate and compare; prints one line per run and a total."""
    config = PaperConfig.model_validate(load_toml(config_path))
    try:
        runs = load_runs(config)
    except RunRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    failures = 0
    total = 0
    with tempfile.TemporaryDirectory(prefix="sentinel-reproduce-") as name:
        scratch = Path(name)
        for role in ROLES:
            run = runs[role]
            count, bad = check_run(run.path, scratch / role)
            total += count
            failures += len(bad)
            state = "identical" if not bad else f"DIFFERS: {', '.join(bad)}"
            print(f"{role:<17} {run.path.as_posix()}: {count} summary files {state}", flush=True)
        committed = config.out_dir
        recorded = committed / MANIFEST_NAME
        if not recorded.is_file():
            print(f"paper: {recorded} is missing", file=sys.stderr)
            return 1
        pinned = json.loads(recorded.read_text(encoding="utf-8"))
        out = scratch / "paper"
        generate(config_path, out, pinned=pinned)
        names = sorted(tree_files(committed) | tree_files(out))
        bad = differing(committed, out, names)
        total += len(names)
        failures += len(bad)
        state = "identical" if not bad else f"DIFFERS: {', '.join(bad)}"
        print(f"{'paper':<17} {committed.as_posix()}: {len(names)} files {state}")
    print(f"reproduce --check: {total - failures} of {total} files identical")
    return 0 if failures == 0 else 1


def _duration(seconds: float) -> str:
    if seconds >= 3600:
        return f"{seconds / 3600:.1f} h"
    return f"{seconds / 60:.0f} min" if seconds >= 60 else f"{seconds:.0f} s"


def replay_command(manifest: Mapping[str, Any], run_dir: Path) -> str:
    """The recorded command of an LLM run answering every backend from the run's bundle."""
    words = shlex.split(str(manifest["command"]))
    kept: list[str] = []
    skip = False
    for word in words:
        if skip:
            skip = False
            continue
        if word in ("--replay", "--cache-file", "--cache-mode"):
            skip = True
            continue
        if word.startswith(("--replay=", "--cache-file=", "--cache-mode=")):
            continue
        kept.append(word)
    kept += ["--cache-file", (run_dir / "llm_cache.jsonl.gz").as_posix()]
    return "uv run " + shlex.join(kept)


def commands(config_path: Path) -> int:
    """`--commands`: print the prerequisites and, per run, the command that recomputes it."""
    config = PaperConfig.model_validate(load_toml(config_path))
    runs = load_runs(config)
    machine = runs["rq4_main"].manifest
    print(
        f"# Recompute the paper's runs; recorded on {machine['cpu']} ({machine['cpu_count']} "
        "logical cores). A recomputed run gets a new directory; configs that join earlier runs "
        "read the committed ones."
    )
    print("# Prerequisites:")
    for command, what in PREREQUISITES:
        print(f"{command}  # {what}")
    total = 0.0
    for role in ROLES:
        run = runs[role]
        manifest = run.manifest
        seconds = float(manifest["duration_s"])
        total += seconds
        print(f"\n# {role}: {run.path.as_posix()} ({_duration(seconds)} recorded)")
        print(f"uv run {manifest['command']}")
        if runner(manifest) in LLM_RUNNERS:
            print(f"# replay without keys or Ollama: {replay_command(manifest, run.path)}")
    print(f"\n# total recorded duration: {_duration(total)}")
    return 0
