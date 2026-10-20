# WP2b report — Baseline plans and the NoReaction scenario study

- Date: 2026-10-20
- Commit(s): a81e5ff (spec v1.3), 7de73a6 (deterministic CP-SAT limit), ce8392d (baselines,
  CLI, config, ADR-0008), e64a3cd (study runner and summaries), 1d71e15 (engine comment); the
  report/notes/roadmap commit follows them

## Summary
Every instance now has a reproducible baseline plan. `cpsat_det` runs CP-SAT with one worker and
a fixed seed, stopped only by a deterministic time limit; `sgs_lft` is the alternative. Plans are
cached per instance, and `sentinel baselines` precomputes a whole set. All 960 J30/J60 plans are
cached on the server: 40 s for J30 and 4.2 min for J60 with 4 workers. The study runner simulates
NoReaction on these plans for 10 scenarios × 20 replications with common random numbers. It
checks every realised schedule and writes the results, `summary.md`, `table_wp2.tex` and the
on-time figure. The smoke run produced all outputs. The owner runs the full study (192,000 runs,
about 6 min measured).

## Acceptance criteria
| # | Criterion | Command | Result |
| --- | --- | --- | --- |
| 1 | Quality gate and `-m data` tests pass | `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy src`; `uv run pytest -q`; `uv run pytest -q -m data` | PASS (ruff clean; 94 files formatted; mypy: no issues in 31 source files; 174 passed; data: 12 passed, 162 deselected) |
| 2 | Deterministic CP-SAT test passes; baseline CLI works on a `--limit` subset | `uv run pytest -q tests/test_cpsat.py tests/test_scheduling_data.py tests/test_cli.py tests/test_baselines.py`; `uv run sentinel baselines --set j30 --method cpsat_det --limit 5` (also j60, and `sgs_lft`) | PASS (33 passed, among them `test_deterministic_time_limit_gives_identical_schedules` and the J60 data test `test_deterministic_limit_does_not_depend_on_machine_load`; CLI: 5 computed, then 5 cached on a rerun; statuses OPTIMAL 5; plan / C* 1.0000) |
| 3 | Smoke run outputs all files of the skill plus `table_wp2.tex` and the figure | `uv run python -m sentinel.experiments.simulation_study --config configs/wp2_noreaction.toml --out results/wp2 --limit 5 --replications 3` | PASS (`results/wp2/20261020-145924-dafd3b7c-smoke`: `manifest.json`, `results.csv`, `summary.md`, `table_wp2.tex`, `fig_wp2_ontime.pdf`, `.png`; 300 rows; status completed, smoke true, commit 1d71e15, not dirty) |
| 4 | Exact commands (baselines, then study) with measured duration estimates | see "Commands for the owner" | PASS (baselines measured in full: 40 s J30, 4.2 min J60; study measured at 548 runs/s with 4 workers: about 6 min) |
| 5 | Report, notes, roadmap (`in progress: WP2b smoke done`); pushed; clean tree | `git push`; `git status --short` | PASS (this report, `docs/notes/WP2b.md`, roadmap; pushed to `origin/main`; `git status --short` empty afterwards) |

## Changes
- `docs/spec/model.md` v1.3 (separate commit), with the owner's four answers to the WP2a.1 questions: §3.1 (g) epochs, §4/§5/§7 SUBST, §3 cost, §3.1 (a) M_j = 0.
- `scheduling/cpsat.py`: `solve_cpsat(..., deterministic_time_limit=None)` sets `max_deterministic_time`; `SolveResult.deterministic_time` reports the work used.
- `simulation/baselines.py`: methods `CpsatDet` and `SgsLft`, `BaselinePlan`, `compute_baseline`, cache (`cache_path`, `read_cached`, `write_cached`, `cached_baseline`), `baseline_plan(instance, method)`, `instance_fingerprint`, `InvalidPlanError`.
- `cli.py`: `sentinel baselines --set S --method {cpsat_det,sgs_lft} [--config --limit --workers --root --cache]`.
- `experiments/simulation_config.py`: `StudyConfig`, `SetConfig`, `BaselineSettings`, `ScenarioGrid` (expansion into scenarios), `Scenario`, `met_column`.
- `experiments/simulation_study.py`: the runner (one pool task per instance, validation, manifest, gzip switch).
- `experiments/simulation_summary.py`: `summary.md`, `table_wp2.tex`, `fig_wp2_ontime.pdf/.png`, Wilson intervals; it can also regenerate the summaries of an existing run.
- `configs/wp2_noreaction.toml`: sets, baseline parameters, grid, R = 20, δ_D, β, PERT.
- `simulation/engine.py`: the SPEC-Q comment on D2 epochs now cites §3.1 (g); comment only.
- Tests (task 5 → test):
  - Deterministic CP-SAT:
    - `test_deterministic_time_limit_gives_identical_schedules` (random 30-activity instance; the limit binds);
    - data test `test_deterministic_limit_does_not_depend_on_machine_load` (j6013_1 alone versus three concurrent solves).
  - Cache round trip:
    - `test_cache_round_trip_keeps_one_entry_per_method`;
    - `test_baseline_plan_without_cache_writes_nothing`.
  - Cache invalidation:
    - `test_changed_parameters_invalidate_the_entry`;
    - `test_changed_instance_invalidates_the_entry`;
    - `test_stale_entries_are_recomputed` (cache version, OR-Tools version, instance name);
    - `test_unreadable_cache_files_are_recomputed`.
    - Also new: provenance, unsafe names and an infeasible plan.
  - Runner on `tiny.sm` (a set of two copies, C* = 7):
    - `test_smoke_run_writes_all_outputs` (expected columns, row order, CRN seeds, manifest);
    - also new: the override counts as smoke, cache reuse between runs, an invalid realised schedule aborts, gzip, regeneration, Wilson interval, config checks.
  - X ≡ 1:
    - `test_durations_only_with_unit_multipliers_reproduces_the_baseline` (tiny, through `run_instance`);
    - data test `test_exact_durations_reproduce_the_baseline_makespan` (5 J30 and 5 J60 instances; OPTIMAL and FEASIBLE CP-SAT plans and SGS-LFT plans; makespan and every start equal).
  - CLI:
    - `test_baselines_on_a_limited_set`;
    - `test_baselines_in_parallel_use_the_config_cache`;
    - `test_baselines_errors`.
  - Data test `test_study_tasks_on_j30`. The `fake_study` fixture moved to `tests/conftest.py`.
- Docs: ADR-0008, `docs/notes/WP2b.md`, this report, roadmap.

## Decisions
- **Deterministic limit 5** (ADR-0008). Probe on four hard J60 instances: limits 2 / 5 / 10 gave 123/117/122/134, 121/115/121/131 and 120/115/120/131. WP1's 10 s wall-clock runs gave 121/117/120/133. Limit 5 matches WP1's quality at half the cost of 10. `cpsat_det` passes `time_limit_s = inf`, so only the deterministic limit stops the search. The seed is 2026.
- **Cache validity:** an entry must also match the instance SHA-256, a cache version and the OR-Tools version, not only the parameters. Otherwise a data or solver change would leave stale plans. There is one JSON file per instance with one entry per method, replaced atomically.
- **CLI parameters** come from the study config (`--config`, default `configs/wp2_noreaction.toml`), so the CLI and the study share cache entries. `--workers 1` runs in-process.
- **Study task = one instance** (all 200 runs, 1–2 s). A missing baseline is computed inside the task and stored. The manifest counts plans taken from the cache and plans computed in the run, and the runner prints the number of missing plans at the start.
- **Validation (invariant 6):** every realised schedule is checked: `validate_schedule` on the segment-split instance and `execution_violations`; truncated runs get the crew checks only. This costs about 1 ms per run (≈ 20 %).
- **Results file:** `results.csv.gz` when the CSV exceeds 15 MB, with gzip mtime 0 so the bytes are reproducible. The smoke CSV has 113 bytes per row and compresses 5.1×. The full study therefore writes about 22 MB plain, i.e. about 4.5 MB as `.gz`.
- **Manifest provenance:** a SHA-256 over the start times of all baseline plans, so two runs can be shown to have used identical plans. It also records the plan statuses and `simulations_per_s`. The 19,200 seeds per instance and replication are listed, as the skill requires (about 0.4 MB).
- **Figure:**
  - x is 100 λ_A (% per worker-day);
  - the λ_A = 0 point appears in both E[L] panels;
  - δ_D is ordinal, so its lines use one hue (blue steps 300/500/700 of the dataviz palette, contrast ≥ 2.5:1 on white) plus distinct markers;
  - the palette was checked in Python because the skill's validator needs Node, which is not installed.
- **Baselines in-session:** the measured total (≈ 5 min) is below the 10-minute rule, so all 960 plans were computed now. The full study was not run, as the prompt requires.
- **Reuse:** `format_duration` comes from the WP1 runner. `data_provenance` is a short copy typed to the new config, to avoid refactoring WP1.
- ADRs created: ADR-0008.

## Deviations
- **Interface additions** (backwards compatible): `solve_cpsat(..., deterministic_time_limit=None)` and `SolveResult.deterministic_time` (default None). Everything else is new. There are no new dependencies.
- **`--replications`** on the runner is not in the prompt. It was needed for the requested R = 3 smoke run; it is hashed with the config, recorded under `overrides` and marks the run as smoke.
- **The baseline CLI** has optional flags (`--config`, `--limit`, `--workers`, `--root`, `--cache`); the prompt's command works with the defaults.
- **Baselines were computed in-session.** The owner's baseline commands are therefore cache hits on this server.
- **No WP2a bug was found;** `engine.py` changed in a comment only.

## Spec questions
1. **§6 SUBST candidates:** §6 still lists "SUBST per paused activity", while §4 (v1.3) also allows SUBST on running activities with absent members. Should the WP5 candidate set contain SUBST for those too? WP2b uses no reading.
2. **§5 urgency for running activities:** τ_t now includes running activities with absent members, but `LS_j` (latest start) is already past once j has started. Suggested reading for WP5: the latest day by which j must be back at full rate so that it still finishes by its LF_j, i.e. LF_j minus its remaining nominal work. WP2b uses no reading.

## Numbers
Smoke run `20261020-145924-dafd3b7c-smoke` covers j301_1–5 and j601_1–5 (all 10 plans OPTIMAL at C*), with R = 3, i.e. 15 runs per cell. With one parameter group per set and 15 runs, it tests the pipeline, not the calibration. 95 % Wilson intervals are in the run's `summary.md`. Abs / D2 / D3 are events per run for
E[L] = 3; those of E[L] = 5 differ by less than 5 %.

| Set | Scenario | C / C* | On time δ=0.1 | δ=0.2 | δ=0.3 | Cost / B | Abs / D2 / D3 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| J30 | durations only | 1.112 | 66.7% | 86.7% | 93.3% | 0.909 | 0 / 0 / 0 |
| J30 | λ_A = 0 | 1.380 | 6.7% | 20.0% | 40.0% | 1.026 | 0 / 2.1 / 2.2 |
| J30 | λ_A = 0.0025, E[L] 3 / 5 | 1.392 / 1.393 | 6.7 / 6.7% | 20.0 / 20.0% | 40.0 / 40.0% | 1.034 / 1.033 | 7.3 / 2.1 / 2.2 |
| J30 | λ_A = 0.005, E[L] 3 / 5 | 1.398 / 1.417 | 6.7 / 6.7% | 20.0 / 20.0% | 46.7 / 46.7% | 1.040 / 1.039 | 13.9 / 2.1 / 2.2 |
| J30 | λ_A = 0.01, E[L] 3 / 5 | 1.402 / 1.431 | 0.0 / 0.0% | 13.3 / 13.3% | 40.0 / 33.3% | 1.048 / 1.045 | 27.5 / 2.1 / 2.2 |
| J30 | λ_A = 0.02, E[L] 3 / 5 | 1.499 / 1.559 | 0.0 / 0.0% | 0.0 / 0.0% | 26.7 / 6.7% | 1.059 / 1.058 | 57.9 / 2.1 / 2.2 |
| J60 | durations only | 1.127 | 40.0% | 93.3% | 100.0% | 0.915 | 0 / 0 / 0 |
| J60 | λ_A = 0 | 1.212 | 20.0% | 60.0% | 80.0% | 0.965 | 0 / 3.0 / 2.0 |
| J60 | λ_A = 0.0025, E[L] 3 / 5 | 1.231 / 1.244 | 13.3 / 13.3% | 40.0 / 33.3% | 80.0 / 80.0% | 0.975 / 0.973 | 13.3 / 3.0 / 2.0 |
| J60 | λ_A = 0.005, E[L] 3 / 5 | 1.257 / 1.262 | 6.7 / 6.7% | 46.7 / 33.3% | 73.3 / 80.0% | 0.983 / 0.980 | 26.3 / 3.0 / 2.0 |
| J60 | λ_A = 0.01, E[L] 3 / 5 | 1.294 / 1.314 | 0.0 / 0.0% | 40.0 / 13.3% | 73.3 / 60.0% | 0.993 / 0.989 | 53.4 / 3.0 / 2.1 |
| J60 | λ_A = 0.02, E[L] 3 / 5 | 1.368 / 1.411 | 0.0 / 0.0% | 6.7 / 6.7% | 40.0 / 20.0% | 1.007 / 1.003 | 105.3 / 3.2 / 2.3 |

No run was truncated. Decision epochs per run range from 11.1 (J30, durations only) to 77.5
(J60, λ_A = 0.02, E[L] = 5).

Baseline computation (`sentinel baselines`, all 480 instances per set, 4 workers). Times are the per-instance wall times inside the workers, read from the cache entries:

| Set | Wall time | Mean s / instance | Median | p95 | Max | OPTIMAL | Stopped by the limit | Their mean | Plan / C* mean (max) | At C* |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| J30 | 40 s | 0.29 | 0.011 | 0.63 | 10.87 | 472 | 8 | 8.9 s | 1.0002 (1.016) | 475 |
| J60 | 4.2 min | 2.03 | 0.017 | 12.09 | 16.53 | 407 | 73 | 11.8 s | 1.0081 (1.141) | 417 |

| Measurement | Value |
| --- | --- |
| Throughput, 4 workers (scratch script calling the runner's `execute` on every 12th instance: 40 J30 + 40 J60, R = 20, all 10 scenarios; not committed) | 16,000 runs in 29.2 s: **548 runs/s**; `simulate` 4.12 ms (J30), 6.92 ms (J60) per run; checks ≈ 1 ms more |
| Full study estimate | 192,000 runs / 548 runs/s ≈ **5.8 min**, plus about 10 s for start-up, results and summaries |
| Runner's own start-up estimate (full config) | 272 s. It times the first instance of each set and assumes perfect scaling, so it is low. |
| Smoke run | 300 runs in 1.6 s (190 runs/s including process start-up); whole run 2.5 s |
| CP-SAT deterministic unit | 2.1–2.7 s of wall time with four parallel solves |
| Tests | 174 passed in about 19 s (134 before, 40 new); `-m data` 12 passed |

Environment: Intel i5-6600K (4 cores), WSL2 Ubuntu 24.04, uv 0.13.2, CPython 3.12.15, numpy
2.5.4, pydantic 2.14.1, ortools 9.15.6755. Deterministic-limit plans are independent of machine
load. The wall times above are specific to this machine.

## Commands for the owner
```bash
cd ~/projects/sentinel && git pull && uv sync --locked
# 1. Baselines: cached on this server by the session, so each command finishes in seconds
#    ("0 computed, 480 cached"); on a fresh checkout J30 takes ~40 s and J60 ~4.2 min.
uv run sentinel baselines --set j30 --method cpsat_det
uv run sentinel baselines --set j60 --method cpsat_det
# 2. Full study in tmux, ~6 min (192,000 runs, 4 workers); writes results/wp2/<run_id>/
#    with results.csv.gz (> 15 MB uncompressed), summary.md, table_wp2.tex, fig_wp2_ontime.*
uv run python -m sentinel.experiments.simulation_study --config configs/wp2_noreaction.toml --out results/wp2
# 3. Check the manifest: status "completed", n_rows 192000, git_dirty false; then commit the run
#    and set WP2 to "done" in docs/roadmap.md
git add results/wp2/<run_id> docs/roadmap.md && git commit -m "WP2b: full NoReaction scenario study" && git push
```

## Open issues / next steps
- **Architect:** pick the WP4–WP7 scenarios from the full run, i.e. where NoReaction is on time often but not always. In the smoke run δ = 0.1 was rarely met even without absences: D2 and D3 alone raise C / C* from 1.11 to 1.38 (J30) and from 1.13 to 1.21 (J60).
- The Wilson intervals pool the correlated runs of one instance. WP7 should use instance-clustered intervals (e.g. a bootstrap over instances).
- Spec questions 1–2 should be answered before WP5.
- WP4: CP-SAT inside replications (RESEQ, FullResolve) can now use `deterministic_time_limit`, as ADR-0006 requires for CRN.
