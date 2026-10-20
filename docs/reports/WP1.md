# WP1 report — Heuristics, CP-SAT and the RQ2 benchmark

- Date: 2026-10-20
- Commit(s): 7389182 (spec, before WP1), b031398, 77bc5a8, f541427 (code, config, tests); the
  report/notes/roadmap commit follows them

## Summary
The four priority rules (LFT, LST, MTS, GRPW) drive a serial SGS on a growing time-indexed
capacity profile. On 40 random instances its schedules match a brute-force implementation.
Regret-based biased random sampling and a CP-SAT model complete the methods. The RQ2 runner
(`configs/wp1_rq2.toml`, 7 methods on J30/J60) validates every schedule and writes
`results.csv`, a manifest, `summary.md`, a booktabs table and the box-plot figure. The smoke run
(10 instances per set) passed every check, including CP-SAT 10 s reaching the J30 optimum on
10/10 instances. The full run is left to the owner; it is estimated at 5–10 min.

## Acceptance criteria
| # | Criterion | Command | Result |
| --- | --- | --- | --- |
| 1 | Quality gate and data tests | `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy src`; `uv run pytest -q`; `uv run pytest -q -m data` | PASS (ruff clean; 61 files formatted; mypy: no issues in 18 source files; 102 passed; data: 7 passed, 95 deselected, 0 skipped) |
| 2 | Smoke run: both sets, all 7 methods, zero invalid schedules, all six outputs | `uv run python -m sentinel.experiments.rcpsp_benchmark --config configs/wp1_rq2.toml --out results/wp1 --limit 10` | PASS (run `20261020-104018-8421d605-smoke` at f541427, clean tree; 140 rows = 2 × 10 × 7; status `completed`, so no schedule failed `validate_schedule` (that aborts the run); `manifest.json`, `results.csv`, `summary.md`, `table_rq2.tex`, `fig_rq2_deviation.pdf`, `.png` present) |
| 3 | J30 smoke: no makespan below the optimum; `cpsat_10s` matches ≥ 9/10 | read from `results.csv` of the smoke run | PASS (0 of 70 J30 rows below `opt`; `cpsat_10s` matches the optimum on **10/10**, all `OPTIMAL`; also 0 of 70 J60 rows below `hrs`) |
| 4 | Runtime of `rbrs_1000` on J60 and of the whole smoke run reported | `uv run python <scratch>/time_rbrs.py` (see Numbers); `/usr/bin/time -p` on the smoke command | PASS (RBRS-1000 on one J60 instance: 0.16–0.31 s; smoke run 2.75 s wall, manifest `duration_s` 2.0) |
| 5 | Report, notes, roadmap updated; commit pushed; clean tree | `git push`; `git status --short` | PASS (this report, `docs/notes/WP1.md`, roadmap WP1 `done`, ADR-0006; pushed to `origin/main`; `git status --short` empty afterwards) |

## Changes
- `scheduling/priority_rules.py`: LFT, LST, MTS, GRPW; `PriorityRule`, `PRIORITY_RULES` with directions.
- `scheduling/sgs.py`: `serial_sgs`, `regret_biased_sampling` (shared inner pass).
- `scheduling/cpsat.py`: `solve_cpsat`, `SolveResult`, `SolveStatus`.
- `experiments/runs.py`: config hash, run id, run dir, `derive_seed`, git state, environment, JSON.
- `experiments/rcpsp_config.py`: pydantic config (sets, `sgs`/`rbrs`/`cpsat` methods).
- `experiments/rcpsp_benchmark.py`: runner (tasks, process pool, validation, CSV, manifest, estimate, progress).
- `experiments/rcpsp_summary.py`: `summary.md`, `table_rq2.tex`, figure; regeneration CLI.
- `configs/wp1_rq2.toml`; `pyproject.toml`/`uv.lock`: `matplotlib>=3.9` (3.11.2).
- Tests: `test_priority_rules.py`, `test_sgs.py`, `test_cpsat.py`, `test_runs.py`,
  `test_rcpsp_benchmark.py`, `test_scheduling_data.py` (data); 35 new tests.
- Docs: `docs/adr/0006-experiment-seeds-and-cpsat-limits.md`, `docs/notes/WP1.md`, this report,
  roadmap. Before WP1, commit 7389182 applied the architect's WP0 decisions (§1 `p_j = 0`
  milestones, §2.1 `P_j = 0` if `p_j = 0`, `n_real` in architecture.md, SPEC-Q marker removed).

## Decisions
- Seeds: one per instance, `derive_seed(2026, set, instance)` (SHA-256 → `SeedSequence`, 31 bits).
  It is independent of `--limit` and order and shared by RBRS and CP-SAT (CRN); SGS rows record
  no seed. CP-SAT uses the wall-clock limit as specified, with one worker and that seed. ADR-0006.
- RBRS draws `n + 2` uniforms per pass (fixed stream use) and stops once a pass reaches LB0; the
  result is the same as without the stop, only faster.
- SGS profile starts at LB0 days and doubles; the next candidate start jumps past the latest
  overloaded day of the window. MTS counts the dummy sink (order unchanged).
- CP-SAT: start domains `[0, H]` (presolve tightens them). Zero-duration activities are left out
  of the cumulatives (§1.3). `lower_bound = ceil(best bound − 1e−6)`, and None if INFEASIBLE
  (CP-SAT then reports 0.0). MODEL_INVALID raises.
- Runner: one task per (instance, method) for load balance, with the `spawn` start method on
  every OS (same behaviour on macOS and Linux). `runtime_s` covers the method call only.
  Heuristic rows have status `FEASIBLE` and an empty `solver_bound`. The `instance` column holds
  the file stem.
- The start estimate is an upper bound: CP-SAT counted at its limit; SGS (1 pass) and RBRS
  (20 passes) timed on each set's first instance. The progress line comes every 10 s.
- Manifest extras: `status` (`running`/`completed`/`aborted` + `error`; an aborted run keeps its
  manifest), `n_tasks`, `outputs`, `platform`, matplotlib version, data provenance (instance and
  reference hashes from `data/psplib/MANIFEST.json`).
- Config uses arrays of tables, so the method order (= table row order) is part of the hash. Each
  method has a `label` and each set has a `dev_lb0` flag.
- Summaries are built from `results.csv` only and can be regenerated with
  `uv run python -m sentinel.experiments.rcpsp_summary <run_dir>`. The table is a bare tabular
  for `\input`. The figure uses matplotlib's object API (no pyplot state), one hue, means as
  diamonds and fixed PDF/PNG metadata.
- mypy needs no `ortools` override: `ortools.sat` ships `py.typed` and stubs (resolves the WP0
  open issue without a change).
- ADRs created: ADR-0006 (experiment seeds and CP-SAT determinism).

## Deviations
- Machine: MacBook Pro M1 (4P + 4E cores, 8 GB, macOS 26.6.2), not the server. `max_workers = 4`
  as on the server; all timings are from the laptop.
- The experiment-run skill words seeds as per (instance, method, replication). They are per
  (set, instance), so that compared methods share them (CLAUDE.md invariant 1, CRN); see ADR-0006.
- Additions not named in the WP: `PriorityRule`/`PRIORITY_RULES`, `RuleName`, the split into
  `runs.py`/`rcpsp_config.py`/`rcpsp_summary.py`, the summary regeneration CLI and the manifest
  extras. WP0 interfaces are unchanged. matplotlib is the only new dependency.
- For the duration estimate, a run on a stratified sample beyond the WP's smoke run was done
  (see Numbers). It used a scratch copy of 96 instances; nothing from it is committed.

## Spec questions
None.

## Numbers
Smoke run `20261020-104018-8421d605-smoke` (10 instances per set; all from parameter group 1:
NC 1.5, RF 0.25, RS 0.2, so not representative of the full sets):

| Set | Method | mean dev_ref % | matches ref | mean dev_lb0 % | mean runtime s |
| --- | --- | ---: | ---: | ---: | ---: |
| J30 | SGS-LFT | 9.23 | 3/10 | 24.90 | 0.0001 |
| J30 | SGS-LST | 6.24 | 2/10 | 21.15 | 0.0001 |
| J30 | SGS-MTS | 9.79 | 2/10 | 25.42 | 0.0001 |
| J30 | SGS-GRPW | 15.60 | 0/10 | 31.65 | 0.0001 |
| J30 | RBRS-1000 | 0.26 | 9/10 | 14.07 | 0.0646 |
| J30 | CP-SAT 1 s | 0.00 | 10/10 (OPTIMAL 10) | 13.75 | 0.0076 |
| J30 | CP-SAT 10 s | 0.00 | 10/10 (OPTIMAL 10) | 13.75 | 0.0065 |
| J60 | SGS-LFT | 4.00 | 4/10 | 14.24 | 0.0003 |
| J60 | SGS-LST | 5.95 | 2/10 | 16.75 | 0.0002 |
| J60 | SGS-MTS | 7.05 | 3/10 | 17.68 | 0.0002 |
| J60 | SGS-GRPW | 20.01 | 0/10 | 31.68 | 0.0002 |
| J60 | RBRS-1000 | 1.26 | 7/10 | 11.36 | 0.1596 |
| J60 | CP-SAT 1 s | 0.00 | 10/10 (OPTIMAL 10) | 9.98 | 0.0095 |
| J60 | CP-SAT 10 s | 0.00 | 10/10 (OPTIMAL 10) | 9.98 | 0.0092 |

| Measurement | Value |
| --- | --- |
| RBRS-1000 (α = 1), one process, `j601_1..10` (RF 0.25) | mean 0.163 s, max 0.172 s (9 full-budget runs; `j601_1` stopped at LB0 after 4 schedules) |
| RBRS-1000, `j6013_1..10` (RF 1.0, RS 0.2, hardest group) | mean 0.289 s, max 0.312 s (all 1000 schedules); target ≤ ~5 s met without optimisation |
| Smoke run (140 tasks, 4 workers) | 2.75 s wall incl. interpreter and pool start; manifest `duration_s` 2.0 |
| Smoke run repeated (runs `…103655…` at 77bc5a8 and `…104018…` at f541427) | identical `results.csv` apart from `runtime_s` |
| Stratified sample: instance 1 of each of the 48 parameter groups per set, all 7 methods (672 tasks) | 30.8 s wall; summed task time 98.5 s, of which J60 CP-SAT 10 s 76%, J60 CP-SAT 1 s 10%, RBRS 7%; 16 CP-SAT runs stopped at the limit; 0 rows below the reference; two repeats identical apart from runtimes |
| Full-run estimate (6720 tasks) | M1: ~5 min (10 × sample); server: 5–10 min expected (Python ~1.5–2× slower per core); upper bound printed at start 44.6 min |
| Tests | 102 passed in 2.9 s (95 offline + 7 data); `-m data` 7 passed in 1.5 s |

Environment: Apple M1, 8 GB, macOS 26.6.2, uv 0.12.2, CPython 3.12.13, numpy 2.5.4, ortools
9.15.6755, pydantic 2.14.1, psplib 0.4.0, matplotlib 3.11.2. Laptop timings, not the server.

## Commands for the owner
On the server, inside tmux (expected 5–10 min; the runner prints an upper bound of ~45 min,
which assumes every CP-SAT run hits its limit):
```bash
cd ~/projects/sentinel && git pull
uv sync --locked          # installs matplotlib 3.11.2 and its dependencies
uv run pytest -q          # expect 102 passed
tmux new -s wp1
uv run python -m sentinel.experiments.rcpsp_benchmark --config configs/wp1_rq2.toml --out results/wp1
git add results/wp1/<run_id> && git commit -m "WP1: add full RQ2 benchmark results" && git push
```
The run directory is about 0.6 MB (`results.csv` ~6720 rows). `table_rq2.tex` and
`fig_rq2_deviation.pdf` in it are the presentation table and figure.

## Open issues / next steps
- Full run on the server, then commit its results and have the architect review the RQ2 table.
- WP4+: CP-SAT inside simulation replications needs a deterministic limit for CRN (ADR-0006).
- On runs that stop at the limit, single-worker CP-SAT bounds are weak. In the sample, 12 of 16
  are above LB0, usually by a few days (e.g. `j6013_1`: C = 121, bound 72, LB0 69).
  `solver_bound` therefore says little about remaining gaps on hard J60 instances.
- `--limit N` takes the first N instances, i.e. parameter group 1 only. A stratified smoke
  option would make smoke runs more representative (not implemented, out of scope).
