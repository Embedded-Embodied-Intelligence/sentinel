# WP2a report — Stochastic simulator core

- Date: 2026-10-20
- Commit(s): e179b2d (spec v1.1), 6dc2208 (uncertainty, events), f226d5b (state, policies,
  engine, tests); the report/notes/ADR/benchmark-script commit follows them

## Summary
`simulate` executes a plan day by day under hidden PERT durations and D1–D3 disruptions,
following spec §3 and the v1.1 execution details (§3.1). Only `NoReaction` decides; a Noop
hook in step 3 is ready for the WP4 operations. Every random draw comes from the
common-random-number streams of §2.3, so a seed gives identical absences and D3 draws for
every policy and plan. Realised schedules pass `validate_schedule` after splitting activities
into their work segments, and they pass a worker-level check. Calls take 4.8 ms on J30 and
8.3 ms on J60, within both targets.

## Acceptance criteria
| # | Criterion | Command | Result |
| --- | --- | --- | --- |
| 1 | Spec commit with all amendments, v1.1 | `git show --stat e179b2d` | PASS (`spec: WP2 simulator semantics (v1.1)`: header v1.1 and ADR rule for approved clarifications, §1.2 `p̄_j`, §2.2 D1–D3, new §2.3 and §3.1 (a)–(g); experiment-run skill seeds per (instance, replication)) |
| 2 | Quality gate; data tests | `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy src`; `uv run pytest -q`; `uv run pytest -q -m data` | PASS (ruff clean; 80 files formatted; mypy: no issues in 27 source files; 127 passed; data: 8 passed, 119 deselected) |
| 3 | All task-6 tests exist and pass | `uv run pytest -q tests/test_uncertainty_events.py tests/test_simulation.py tests/test_policies.py tests/test_simulation_data.py` | PASS (25 new tests; mapping under Changes) |
| 4 | `simulate` timings J30/J60 (mean, p95), ≥ 200 calls each; targets 5 / 15 ms | `uv run python scripts/bench_simulate.py` | PASS (J30 mean 4.84 ms, p95 6.91 ms; J60 mean 8.32 ms, p95 12.87 ms; 200 calls each; a repeat gave 4.79 / 8.59 ms) |
| 5 | Report, notes, roadmap (`in progress: WP2a done`); pushed; clean tree | `git push`; `git status --short` | PASS (this report, `docs/notes/WP2a.md`, ADR-0007, roadmap; pushed to `origin/main`; `git status --short` empty afterwards) |

## Changes
- `docs/spec/model.md` v1.1 and `.claude/skills/experiment-run/SKILL.md` (Randomness), as the WP prompt specified.
- `simulation/uncertainty.py`: `PertParams` (+ `mean`), `pert_multipliers`, `realised_duration`, `realise_durations`, `expected_durations`, `role_costs`, `derive_deadline`, `derive_budget`.
- `simulation/events.py`: `DisruptionParams` (+ `none()`), frozen `Absence`, `WorkIncrease`, `NewActivity`, `NewActivitySkipped`, `Event` union, `ScenarioStreams` with per-day queries.
- `simulation/state.py`: `EngineState` (plain lists, hidden fields), frozen `Observation`, `InsertedActivity`, `WorkSegment`.
- `simulation/engine.py`: `simulate`, `SimulationResult`, `DayRecord` (optional trace).
- `simulation/realised.py`: `project_graph`, `realised_instance` (segment-split instance for `validate_schedule`), `execution_violations`.
- `policies/base.py`: `Policy` protocol (optional `passive` hint), `Decision`, `Noop`, `Operation` union (extension point), `EMPTY_DECISION`; `policies/no_reaction.py`: `NoReaction`.
- `scripts/bench_simulate.py`: the timing and summary measurements of this report.
- Tests (task 6 → test):
  - PERT: `test_pert_sample_mean_and_support`.
  - Exact replay: `test_exact_replay_of_the_cpsat_optimum_of_tiny`, `test_exact_replay_of_an_sgs_schedule_with_resource_delays`.
  - Feasibility: `test_stochastic_durations_give_feasible_schedules`.
  - Determinism: `test_same_seed_same_result_and_different_seeds_differ`.
  - CRN: `test_common_random_numbers_across_policies_and_plans`.
  - D1: `test_absence_pauses_and_resumes_with_the_same_workers`, `test_random_absences_respect_the_announced_bound`.
  - D2: `test_forced_work_increase_extends_the_duration`, `test_random_work_increases_follow_the_ceil_rule`.
  - D3: `test_new_activities_keep_the_graph_acyclic`.
  - Truncation: `test_truncation_at_max_days`.
  - Hidden fields: `test_observation_hides_hidden_quantities`, `test_observations_do_not_depend_on_true_durations`.
  - Data: `test_default_disruptions_on_30_j30_instances`.
  - Further tests: stream rules and query-order independence, deadline/budget, milestones, result round trip, policies.
- Docs: `docs/adr/0007-simulator-streams-and-engine-shortcuts.md`, `docs/notes/WP2a.md`, this report, roadmap.

## Decisions
- **D1 sampling:** absences and D2 use one uniform per variate. L is drawn by inversion (numpy's geometric(q) distribution), and streams are read by position from blocks. D3 draws come per 128-day chunk: uniforms first, then the PERT multipliers. ADR-0007.
- **Durations:** `realise_durations` draws one multiplier per activity id, dummies included. `round` is half to even. `PertParams.mean = (a + λm + b)/(λ + 2)`, which is the spec's `(a + 4m + b)/6` at λ = 4.
- **Zero-duration activities** need no workers to start. This matches §1.3, where they use no capacity, and it is what makes exact replay possible. It only matters for milestones with demands, which PSPLIB does not have.
- **D2 timing:** a shock is checked at step 1 for activities still running from the previous day, with counter k = e_j. The window [e_j + 1, e_j + remaining − 1] is precomputed, so the daily check is one integer comparison. `ceil(R·F − 1e−9)` keeps products like 5 × 1.2 integral; `derive_deadline` uses the same tolerance (1.1 × 10 = 11.000000000000002).
- **Plan start of a D3 activity:** `max(t + 1, F_pred)`. F_pred is the realised finish if the predecessor is done, otherwise its plan start plus its nominal p. No other plan entry changes (§3.1 e).
- **Truncation:** days 0..max_days are simulated. A truncated run reports `makespan = max_days` (right-censored) and `deadline_met = False`.
- **Feasibility check:** a paused activity is not contiguous, so `realised_instance` turns every work segment into an activity and chains the segments. `validate_schedule` (§1.3) then applies, and `execution_violations` adds the worker-level rules.
- **Observation:** day, the original instance, inserted activities (nominal data only), plan, statuses, e_j, starts, finishes, assigned workers, observed D2 factors with e_j at each shock, worker presence, absence onset and announced L_low, cost so far, deadline and priors (PERT and disruption parameters).
- **Performance:** dispatch tries only today's planned starts when no worker was freed and no activity became eligible since the last dispatch. Passive policies are not called. Observations and results use `model_construct`. All three leave results unchanged, which I checked on 200 runs (ADR-0007).
- **Seeds** in the data test and the benchmark: `derive_seed(2026, set, instance, replication)`, one per (instance, replication) as in ADR-0006 and §2.3.
- ADRs created: ADR-0007.

## Deviations
- Interfaces beyond the WP prompt, all additions:
  - `ScenarioStreams` takes `pert` as well, because durations and D3 multipliers need it.
  - New types and helpers: `NewActivitySkipped` (for the logged skip), `WorkSegment`, `DayRecord`, `InsertedActivity`, the `passive` hint, `realised.py`, `role_costs`, `realised_duration`.
  - Extra `SimulationResult` fields: `seed`, `n_original`, `work`, `segments`, `deadline`, `max_days`.
  - `scripts/bench_simulate.py`.
- WP0/WP1 interfaces are unchanged. There are no new dependencies.
- L uses inversion of a uniform rather than a call to numpy's `geometric`. The distribution is the same (ADR-0007).
- The CRN test also compares two different plans for the same seed. Absence events, D3 days and D3 templates are identical up to the shorter run's end.

## Spec questions
All five are marked `SPEC-Q` in the code; each line gives the reading used.
1. **D1 return day** (`events.py`): a worker absent on days t..t+L−1 is back on day t+L, where no Bernoulli is drawn ("not drawn again until the day after their return"). So §2.3's "one Bernoulli per present day" excludes return days. Alternative: draw on the return day too.
2. **D2 timing** (`engine.py`): the check is at step 1 with k = e_j, for activities running since the previous day. A shock never hits an activity's first work day, and a one-day activity is never shocked. Alternative: draw on the k-th work day itself, before progress.
3. **D2 for inserted activities** (`events.py`): §2.3 (iii) has streams for original activities only, so activities inserted by D3 get no work increases. Alternative: one child stream per insertion.
4. **D3 predecessor candidates** (`engine.py`): "activities" read literally, so the source and finished activities count. The source is always valid, so "no valid predecessor" never occurs; only instances without real activities skip. Alternative: unfinished real activities only.
5. **Railway sink** (`engine.py`): "never start earlier than planned" also holds for the sink, so realised makespan ≥ planned makespan and early completion is never rewarded. Alternative: the sink completes as soon as its predecessors are done.

## Numbers
`scripts/bench_simulate.py` (i5-6600K, WSL2; 40 instances spread over each set × 5 seeds; SGS-LFT plan; D = ceil(1.1 C*), C* = J30 opt / J60 hrs; PERT(0.8, 1, 1.6); λ_A = 0.01, E[L] = 3, λ_S = 0.01, λ_N = 0.02; NoReaction):

| Set | Calls | Mean ms | p95 ms | Max ms | Mean workers | Realised / planned makespan | On time (D) | Truncated |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| J30 | 200 | 4.84 | 6.91 | 30.31 | 81.0 | 2.304 | 1.0% | 0 |
| J60 | 200 | 8.32 | 12.87 | 40.26 | 112.6 | 2.533 | 0.0% | 1 (`j6031_1`, 198 workers) |

| 30 × 5 data run (J30 every 16th instance) | Value |
| --- | --- |
| Realised / nominal (SGS-LFT) makespan, mean | 2.100 |
| Runs on time at D = 1.1 C*; truncated | 0 of 150; 0 |
| Events | absence 14 914 (99.4 per run), work increase 234 (1.56), new activity 404 (2.69) |
| Decision epochs per run | 83.8 |

| Measurement | Value |
| --- | --- |
| Tests | 127 passed (119 offline + 8 data) in 4.9 s; `-m data` 8 passed in 3.3 s (30 × 5 test 0.9 s); 25 tests new in WP2a |
| Slowest calls of the repeat run | J30 32 ms (`j3047_9`, 291 days against a 65-day plan); J60 55 ms (`j6039_5`); all are long runs with many epochs |
| Cost per J30 call (instrumented, before the last fixes) | Stream setup 1.2 ms (about 110 `SeedSequence` children and PCG64 generators at about 11 µs each); absence walks 0.9 ms; dispatch 1.1 ms; D2 lookups 0.5 ms |
| Stream identity after optimising | Same answers as commit 6dc2208 for 60 seed/parameter combinations, 700 days and random D2 queries |

Environment: Intel i5-6600K (4 cores), WSL2 Ubuntu 24.04, uv 0.13.2, CPython 3.12.15, numpy
2.5.4, pydantic 2.14.1, ortools 9.15.6755. Timings vary by about ±5% between repeats.

## Commands for the owner
None required: there is no long run in WP2a. To reproduce the numbers (about 10 s):
```bash
cd ~/projects/sentinel && git pull && uv sync --locked
uv run pytest -q          # expect 127 passed
uv run python scripts/bench_simulate.py
```

## Open issues / next steps
- **Calibration for WP2b (architect):** λ_A is per worker and day, and PSPLIB capacities give 81 (J30) to 113 (J60) workers on average, so about 0.8–1.1 absences start every day. Combined with §3.1 (a), where an activity resumes only when all its original workers (r_jk up to 10 per role) are present and idle, NoReaction takes 2.1–2.5 times its plan and meets D = 1.1 C* in at most 1% of runs. WP2b's grid (λ_A ∈ {0, 0.005, 0.01, 0.02}) may therefore leave almost no "often but not always" region. Options: lower rates, rates per role or per activity, or shorter absences.
- Spec questions 1–5 above.
- WP5 speed: setting up the streams is about a quarter of a J30 call. `ScenarioStreams` answers do not depend on query order, so it can be built once per seed and reused across candidates and epochs.
- WP4: `Operation` gains SUBST, RESEQ and the others. `_apply` must set `state.changed` whenever an operation frees workers or changes eligibility, so that the dispatch shortcut stays exact.
