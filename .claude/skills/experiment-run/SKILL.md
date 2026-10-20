---
name: experiment-run
description: Rules for implementing and running experiments reproducibly (configs, seeds, run ids, manifests, outputs, long runs). Use when building or executing any benchmark, simulation study or evaluation that produces results for the papers.
---

# Reproducible experiment runs

## Configuration

- One TOML file per experiment in `configs/` (e.g. `configs/wp1_rq2.toml`). It lists instance
  sets, methods and their parameters, seeds, time limits, worker counts.
- The runner takes `--config <path>` and optional `--limit N` (first N instances per set,
  for smoke tests) and `--out results/<wp>`.
- `config_hash` = SHA-256 of the canonicalised config content (sorted keys) plus the `--limit`
  value.

## Run identity and outputs

`run_id = <UTC yyyymmdd-HHMMSS>-<config_hash[:8]>`, output directory
`results/<wp>/<run_id>/`, never overwritten. Contents:

- `manifest.json`: run_id, command line, config path and full config, config_hash, limit,
  git commit and dirty flag, start/end time (UTC ISO), duration, Python version, versions of
  key packages (numpy, ortools, pydantic, psplib), CPU model and core count, hostname,
  number of result rows, seeds used.
- `results.csv`: one row per (instance, method[, replication]); raw measurements only, no
  aggregates.
- Generated summaries: `summary.md` (human-readable tables), LaTeX tables (`*.tex`, booktabs,
  no hand edits), figures (`*.pdf` and `*.png`).
- Smoke runs (with `--limit`) are marked `"smoke": true` in the manifest and their directory
  name ends with `-smoke`.

## Randomness

- Derive one seed per (instance, replication), shared by all methods (common random numbers),
  deterministically from a base seed with `numpy.random.SeedSequence(base).spawn(...)` or a
  stable hash; record them in `results.csv`.
- Never use global random state. For OR-Tools CP-SAT set `random_seed` and
  `num_workers` explicitly and record them.

## Execution

- Parallelise over instances with `concurrent.futures.ProcessPoolExecutor`
  (`max_workers` from config, default 4 on this server). Solvers inside a process use one
  thread unless the config says otherwise.
- Validate every schedule with `validate_schedule`; an invalid schedule aborts the run.
- Print a progress line at most every ~10 seconds and an estimated total duration at start.
- If the expected duration exceeds ~10 minutes, do not run it in the Claude Code session:
  run a smoke test (`--limit`), then put the full command in the WP report for the owner to run
  in tmux, e.g.:
  `uv run python -m sentinel.experiments.<runner> --config configs/x.toml --out results/wpN`

## Committing results

Commit `results/<wp>/<run_id>/` for full runs (keep total size small, < 20 MB). Smoke-run
directories may be deleted or committed only if useful as evidence. Never commit raw per-step
traces; they are reproducible from code and seeds.
