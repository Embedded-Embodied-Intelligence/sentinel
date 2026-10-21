# WP4b report — Per-newcomer handover, return epochs and the baseline policy study

- Date: 2026-10-21
- Commit(s): 1f7d5fa (spec v1.6), ec5a198 (engine and policies), 3738844 (test-speed chore),
  c8c4c02 (first look and study plan), f1c65d8 (README test line), 1148d31 (policy study runner,
  configs and summaries), 7272a40 and dde6de4 (figure and start-estimate fixes); the report,
  notes, ADR and roadmap commit follows them

## Summary
Spec v1.6 is implemented. A SUBST now charges each newcomer o_j = max(1, ⌈α e_j⌉) crew-member
days, so h_j = m_j o_j / M_j full-crew days. Absence returns are decision epochs, and
StableResolve, nervousness and the realised deviation use the deviation set of answer 3.
T_cp = 0.1. NoReaction makespans are unchanged: the regression runs differ only in their
epochs, and the WP2b check finds 0 mismatches. `policy_study` runs the RQ4 baseline study from
`configs/wp4_baselines.toml` and `configs/wp4_sensitivity.toml`. `policy_summary` (also
`sentinel summarise-policies`) writes the summaries, `table_wp4.tex` and both figures. Both
smoke runs produced every output. The primary study is estimated at about 4–5 h on 4 workers
(3.6–4.0 h at full use), within the 8 h budget.

## Acceptance criteria
| # | Criterion | Command | Result |
| --- | --- | --- | --- |
| 1 | Spec v1.6 commit; test-speed chore as a separate commit | `git show --stat 1f7d5fa 3738844` | PASS (`spec: per-newcomer handover, return epochs, T_cp (v1.6)` changes only `docs/spec/model.md`. `chore: skip slow tests by default` changes `pyproject.toml`, `tests/test_policies_data.py`, CLAUDE.md and `docs/workflow/wp-protocol.md`. The README line followed in `f1c65d8`) |
| 2 | Quality gate passes (default `pytest -q` ≤ 90 s) and `-m "data or slow"` passes | `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy src`; `uv run pytest -q`; `uv run pytest -q -m "data or slow"` | PASS (ruff clean; 151 files formatted; mypy: no issues in 50 source files; `pytest -q`: 280 passed, 1 deselected in 85.0 s, at most 90 s; `-m "data or slow"`: 16 passed, 265 deselected in 176.0 s) |
| 3 | First-look table at T_cp = 0.1 reported with the new h_j | `uv run python scripts/bench_policies.py --views 0 --runs j30:20:3 --cp-limit 0.1` (then `j60:20:3`) | PASS (`docs/notes/WP4b.md`, committed in c8c4c02 before the runner; also under Numbers. Onboarding: 1.87–1.93 crew-member days per replaced member; WP2b check 0 mismatches in 120 NoReaction runs) |
| 4 | Both smoke runs produce every output; NoReaction WP2b check 0 mismatches | `uv run python -m sentinel.experiments.policy_study --config configs/wp4_baselines.toml --out results/wp4 --limit 3`, and the same with `configs/wp4_sensitivity.toml` | PASS (`20261021-145924-a425d820-smoke`: 480 runs; `20261021-150013-96511d6d-smoke`: 120 runs. Both at commit dde6de4 with a clean tree. Each wrote `results.csv.gz`, `manifest.json`, `summary.md`, `summary_manifest.json`, the table and both figures. WP2b check: 96 and 24 worlds, 0 makespan and 0 seed mismatches. 0 rejected operations, 0 CP-SAT fallbacks in 15,537 and 4,124 stages, 0 truncated runs. Rerun at the final commit, both are identical to the first smoke runs except for timing columns) |
| 5 | Exact full-run commands with measured duration estimates | spread measurement (Numbers) | PASS (primary 14.6–15.9 CPU h: 3.6–4.0 h on 4 workers at full use, about 4–5 h with idle workers, within 8 h; sensitivity 2.6–3.3 CPU h: about 1 h. Commands under Commands for the owner) |
| 6 | Report, notes, roadmap (`WP4: in progress: WP4b smoke done`); pushed; clean tree | `git push`; `git status --short` | PASS (this report, `docs/notes/WP4b.md`, roadmap; pushed to `origin/main`; `git status --short` empty afterwards) |

## Changes
- `docs/spec/model.md` v1.6 as dictated (own commit): per-newcomer handover in §3 and §4 in
  crew-member and full-crew days, returns as epochs (§3, §3.1 g), answers 1–7 (§4, §5.1, §5.2,
  §7, §7.1), `T_cp = 0.1` (§8).
- `simulation/state.py`: `onboarding_days` (o_j); `Observation.handovers` now records the work
  added in crew-member days (m_j o_j = h_j M_j), and `work_history` adds it as recorded.
- `simulation/engine.py`:
  - SUBST adds m_j o_j crew-member days;
  - `Substitution.onboarding` (o_j), and `handover` is h_j in full-crew days (float);
  - `SimulationResult.onboarding_days`; `handover_days` is a float;
  - return days are decision epochs (`_absences`);
  - nervousness counts only changes in the deviation set (`_replanned`).
- `scheduling/residual.py`: `ResidualProblem.inserted_today`, `deviation_positions()`,
  `deviation()`; `planning_view` fills `inserted_today`. `scheduling/cpsat.py`: stage 2 of
  "stable" minimises the deviation over the deviation set, and `objective` reports it.
- `policies/resolve.py`: `T_CP = 0.1`; docstrings for return epochs and FullResolve(subst).
- `experiments/policy_runs.py`: `run_checked` (one checked run, shared by `run_policies` and
  the study); `PolicyRecord.onboarding_days`, `handover_days` is a float;
  `realised_deviation(result, baseline, instance)` runs over J⁺.
- New `experiments/policy_config.py`: `PolicyStudyConfig` and `PolicySummarySettings`.
- New `experiments/policy_study.py`: the runner, one task per (instance, scenario).
- New `experiments/policy_summary.py`: summaries, table, figures, WP2b check, regeneration.
- `cli.py`: `sentinel summarise-policies <run_dir>`.
- New `configs/wp4_baselines.toml` and `configs/wp4_sensitivity.toml`.
- `scripts/bench_policies.py`: onboarding days per substitution; `--cp-limit` defaults to T_CP.
- Test speed (own commit):
  - `pyproject.toml`: marker `slow`, default `-m "not slow"`;
  - `tests/test_policies_data.py`: the policy-run test is marked slow, and the J30 view test
    uses T_CP;
  - CLAUDE.md and `docs/workflow/wp-protocol.md` (and one README line) document
    `uv run pytest -q -m "data or slow"`.
- Docs: `docs/experiments/plan.md` (RQ4 baseline study), ADR-0013, `docs/notes/WP4b.md`, this
  report, roadmap.
- Tests adapted because their expected values follow from v1.6:
  - `test_engine_regression.py` and its fixture: rewritten for the return epochs only (see
    Decisions);
  - `test_simulation.py::test_absent_member_slows_the_crew_and_stays_reserved`: 4 epochs
    instead of 3 (the return on day 3);
  - `test_baseline_policies.py::test_disruption_monitor_tells_disruptions_from_periodic_epochs`:
    the return day 4 is an epoch with a new disruption; the later observation shifts by one;
  - `test_interventions.py::test_subst_on_a_paused_one_person_activity` and
    `::test_invalid_operations_are_rejected_and_the_run_goes_on`: the `Substitution` records
    carry `onboarding = 1`; h stays 1 for one person;
  - `test_interventions.py::test_subst_on_a_running_partial_crew_raises_its_rate`: h = 0.5
    instead of 1, so F_A = 5 instead of 6, work 4.5, cost 9;
  - `test_residual.py::test_residual_plans_are_feasible_on_random_views`: the stable objective
    equals the deviation over the deviation set and is at most that of the FullResolve plan;
  - `test_residual.py::test_solver_falls_back_to_the_residual_sgs`: the expected deviation
    leaves out the sink. Its term was 0, so the value is unchanged;
  - `test_policies_data.py::test_residual_plans_are_feasible_on_j30_planning_views`: CP-SAT at
    T_CP = 0.1 (answer 7) instead of 0.5.
- New tests:
  - `test_interventions.py::test_onboarding_days_per_newcomer` (e_j = 0 and rounding),
    `::test_handover_is_onboarding_per_newcomer[1-1-12, 10-1-11, 10-3-11]` (one person, 1 of
    10, 3 of 10) and `::test_deviation_set_leaves_out_milestones_the_sink_and_fresh_d3_activities`;
  - `test_simulation.py::test_a_return_day_is_a_decision_epoch`;
  - `test_policy_study.py`:
    - the committed configs follow the plan (2 tests), and invalid configs are rejected;
    - the runner on tiny.sm: columns, CRN seeds, checks, every output, byte-identical
      regeneration through the CLI;
    - the summariser on a synthetic CSV: Wilson cells, paired differences and their
      intervals, a table of at most 9 columns;
    - the WP2b check.

## Decisions
- **Handover records.**
  - `Observation.handovers` now holds the work added in crew-member days (m_j o_j, an integer)
    instead of h_j in full-crew days, which is fractional now. The engine, the belief, the
    deterministic forecaster and resumed rollouts therefore add exactly the same work; h_j M_j
    rebuilt from a float could miss by one rounding step.
  - `Substitution` records o_j (`onboarding`) and h_j (`handover`, full-crew days).
  - The ceiling keeps its 1e-9 noise guard (`onboarding_days`).
- **Deviation set in one rule.** The planning view records the D3 activities inserted on its
  day (`inserted_today`, default empty). `ResidualProblem.deviation_positions` gives U'_t to
  CP-SAT's stage 2 and to the reported objective. The engine applies the same rule to its own
  state when it counts nervousness (`_replanned`); a test checks both on one run.
- **Realised deviation** = mean over J⁺, the original activities with p_j > 0 (see Spec
  questions). J30 and J60 have no real activity with p_j = 0 (0 of 14,400 and 28,800), so the
  values equal v1.5's there.
- **Regression fixture.** It was rewritten with the new engine; the WP4a engine's outputs were
  kept for the comparison:
  - with `n_epochs` and the day records' epoch flags removed, all 50 result dumps are
    identical;
  - the 5 affected recorder cases see the same observations on every WP4a epoch day, plus 41
    on return days;
  - makespans, event counts and truncation flags are unchanged;
  - 26 cases gain epochs (1,685 → 1,971), and the fixture diff is 26 result and 5 observation
    digests.
- **Runner** (ADR-0013):
  - one task per (instance, scenario), interleaving the sets instance by instance so that
    progress estimates mix both;
  - every run in debug mode with its realised schedule checked; `results.csv.gz` with a fixed
    gzip mtime;
  - the WP2b check runs in the summariser, so regenerated summaries check again;
  - rejected operations, fallbacks and truncated runs are counted in the manifest and
    `summary.md`;
  - the start estimate times up to three spread instances per set (first, middle, last).
- **Config.** `PolicyStudyConfig` extends the WP2b `StudyConfig` (seeds, deltas, β, PERT,
  scenarios) with strides, policies, T_cp, the CP-SAT seed, the WP2b results file and summary
  settings. It requires one E[L] per study, because the figures plot against λ_A, and requires
  the reference policy among the policies. α stays the spec constant 0.3 and is recorded in the
  manifest.
- **Statistics** (ADR-0013):
  - on-time shares with Wilson intervals over runs, as in WP2b;
  - paired differences against NoReaction over the same worlds with a cluster bootstrap over
    instances, as in WP3b (1,000 resamples, seed 2026, one matrix per set);
  - every cell per set × λ_A × policy, and pooled over λ_A;
  - on regeneration, the `[summary]` settings come from the config file while its run keys are
    unchanged (the ADR-0011 rule).
- **`table_wp4.tex`:**
  - 8 columns: policy; on time for both δ_D; C/C*; deviation; nervousness; substitutions;
    cost/B;
  - sets are group rows, and "(S)" marks substitution;
  - second rows hold the 95 % intervals of the paired differences, whose point values equal
    the differences of the means;
  - the width, estimated with Computer Modern metrics, is about 116 mm against 122 mm. No LaTeX
    is installed to compile it.
- **Figures** (dataviz):
  - categorical slots in registry order plus markers; Wilson error bars dodged sideways;
  - `fig_wp4_ontime`: one row per δ_D with a shared y axis, and a column per set;
  - `fig_wp4_tradeoff`: a row per set and one panel per reactive policy, NoReaction in grey,
    points labelled with λ_A in %.
- **Duration estimates** come from a spread measurement, not from the `--limit 3` smoke runs
  (see Deviations).
- **Smoke runs** are gitignored (`results/**/*-smoke/`), so they are quoted here and not
  committed.
- ADRs created: ADR-0013 (policy study layout and paired statistics).

## Deviations
- **The first look was committed** in the notes (c8c4c02) before the runner (1148d31). I then
  built the runner in the same session; the prompt asks for it, and does not say to wait for
  a review.
- **`fig_wp4_tradeoff`** has a row of panels per set with one panel per reactive policy,
  instead of one panel per set with five colours. The reference palette keeps at most three
  series distinguishable in a scatter, and two of the five slots (orange, yellow) collide.
  Every panel shows NoReaction in grey, so each policy's trade-off is read against the same
  reference.
- **The duration estimates are measured on a spread sample**, not extrapolated from the smoke
  runs. `--limit 3` takes the first three instances of each set, all from parameter group 1,
  where CP-SAT is easy: J60 FullResolve takes 0.35 s per run there, but 5.8 s on the spread
  sample (pooled over λ_A) and 8.8 s in the first look (λ_A = 0.01). The smoke runs alone
  would predict 1.2 CPU h, about 18 minutes on 4 workers, a twelfth of the measured 14.6 CPU h.
  - The sample: every 48th instance (10 per set, a subset of the study's every 4th), all
    scenarios, replication 0, 400 + 100 runs.
  - It ran through the runner with temporary configs; the outputs stayed in the scratchpad.
- **Beyond the listed files:**
  - `experiments/policy_config.py`, `scripts/bench_policies.py`, ADR-0013, one README line;
  - `realised_deviation` now takes the instance;
  - the J30 planning-view data test runs CP-SAT at T_cp = 0.1 instead of 0.5.
- **Default `pytest -q` takes 85 s**, below 90 s but with little margin. The next candidate for
  `slow` is the J30 planning-view data test (9 s), which is under 30 s and so stays.

## Spec questions
1. **Denominator of the realised deviation** (§7.1). Answer 3 names the set, and v1.6 writes
   the mean over J⁺, the original activities with p_j > 0. v1.5 summed over j ≤ n and divided
   by n. Both agree whenever no real activity has p_j = 0, which holds for all of J30 and J60.
   Please confirm.
2. **Return days without a crew.** v1.6 §3.1 (g) states that a return day is an epoch whether
   or not the worker returns to a crew. This reads answer 1 ("any day with a D1 onset or
   return") literally; a return to no crew changes only the idle pool. Please confirm.

## Numbers
Environment: Intel i5-6600K (4 cores), WSL2 (Linux 6.18), uv 0.13.2, CPython 3.12.15, numpy
2.5.4, ortools 9.15.6755, pydantic 2.14.1, matplotlib 3.11.2. Policy runs ran in a pool of 4
workers and were timed inside the workers. The scenario is the primary grid (E[L] = 3,
λ_S = 0.01, λ_N = 0.02, T_r = 5) on `cpsat_det` baselines with the WP2b seeds and max_days of
δ_D = 0.3.

**First look at T_cp = 0.1 with the new h_j** (`scripts/bench_policies.py`, 20 spread
instances × 3 seeds per set, λ_A = 0.01, on time for δ_D = 0.2; means per run; WP4a values in
brackets, J30 at T_cp = 0.5 and J60 at 0.05):

| Set | Policy | On time | C / C* | Deviation d | Nervousness | Substituted | Handover d | Onboarding d / subst. | RESEQs | s / run |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| J30 | NoReaction | 0.217 (0.217) | 1.379 (1.379) | 7.76 | 0 | 0 | 0 | -- | 0 | 0.005 |
| J30 | AlwaysSubstitute | 0.183 (0.050) | 1.386 (1.557) | 7.96 | 0 | 25.2 | 3.4 | 1.93 | 0 | 0.010 |
| J30 | FullResolve | 0.250 (0.233) | 1.339 (1.338) | 8.03 | 210.6 | 0 | 0 | -- | 62.3 | 1.737 |
| J30 | FullResolve(subst) | 0.233 (0.083) | 1.351 (1.485) | 8.45 | 218.8 | 25.0 | 3.5 | 1.93 | 63.1 | 1.774 |
| J30 | StableResolve(subst) | 0.250 (0.067) | 1.347 (1.492) | 8.09 | 187.9 | 24.7 | 3.3 | 1.87 | 62.8 | 2.894 |
| J60 | NoReaction | 0.167 (0.167) | 1.410 (1.410) | 10.56 | 0 | 0 | 0 | -- | 0 | 0.009 |
| J60 | AlwaysSubstitute | 0.150 (0.067) | 1.426 (1.553) | 10.96 | 0 | 45.7 | 6.2 | 1.87 | 0 | 0.019 |
| J60 | FullResolve | 0.217 (0.167) | 1.369 (1.371) | 12.17 | 785.8 | 0 | 0 | -- | 97.6 | 8.824 |
| J60 | FullResolve(subst) | 0.167 (0.083) | 1.369 (1.498) | 12.46 | 807.4 | 44.5 | 6.2 | 1.88 | 97.7 | 9.042 |
| J60 | StableResolve(subst) | 0.167 (0.083) | 1.369 (1.512) | 12.01 | 512.8 | 45.6 | 6.2 | 1.87 | 97.4 | 14.792 |

- 300 runs per set took 163.5 s (J30) and 614.0 s (J60) of wall time.
- WP2b check: 120 NoReaction runs, 0 mismatches. CP-SAT fallbacks: 0 in 38,477 stages.
- NoReaction has 69.0 / 105.6 epochs per run (WP4a: 53.5 / 84.1); the extra ones are returns.
- Substitution no longer lengthens projects: the handovers add 3.4 / 6.2 full-crew days per
  run (WP4a: 26.1 / 47.9).

**Smoke runs** (`--limit 3`; the first three instances per set, all of parameter group 1, which
are easy; pooled over λ_A; 48 runs per policy; Δ: paired difference to NoReaction with its
cluster bootstrap interval). These are not results:

| Run | Set | Policy | On time δ=0.2 [%] | On time δ=0.3 [%] | C / C* | Deviation d | Nervousness | Substituted | Cost / B | Δ on time δ=0.2 [pp] | Δ C / C* |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| primary | J30 | NoReaction | 20.8 | 52.1 | 1.411 | 4.96 | 0 | 0 | 1.010 | | |
| primary | J30 | AlwaysSubstitute | 22.9 | 52.1 | 1.401 | 5.03 | 0 | 6.5 | 1.024 | +2.1 [0.0, 6.2] | −0.010 [−0.022, 0.001] |
| primary | J30 | FullResolve | 31.2 | 56.2 | 1.354 | 5.04 | 103.1 | 0 | 1.012 | +10.4 [0.0, 31.2] | −0.057 [−0.079, −0.029] |
| primary | J30 | FullResolve(subst) | 33.3 | 56.2 | 1.357 | 5.22 | 103.6 | 6.7 | 1.027 | +12.5 [6.2, 25.0] | −0.055 [−0.071, −0.023] |
| primary | J30 | StableResolve(subst) | 29.2 | 56.2 | 1.356 | 5.05 | 88.8 | 6.6 | 1.025 | +8.3 [6.2, 12.5] | −0.056 [−0.080, −0.023] |
| primary | J60 | NoReaction | 29.2 | 56.2 | 1.336 | 7.54 | 0 | 0 | 0.999 | | |
| primary | J60 | AlwaysSubstitute | 31.2 | 60.4 | 1.340 | 7.63 | 0 | 16.4 | 1.016 | +2.1 [−6.2, 12.5] | +0.004 [−0.003, 0.009] |
| primary | J60 | FullResolve | 47.9 | 62.5 | 1.281 | 9.01 | 305.0 | 0 | 0.994 | +18.8 [−12.5, 43.8] | −0.055 [−0.115, −0.015] |
| primary | J60 | FullResolve(subst) | 45.8 | 60.4 | 1.295 | 9.16 | 312.1 | 17.1 | 1.012 | +16.7 [−12.5, 43.8] | −0.040 [−0.097, 0.011] |
| primary | J60 | StableResolve(subst) | 39.6 | 58.3 | 1.299 | 7.83 | 270.3 | 16.3 | 1.010 | +10.4 [−6.2, 25.0] | −0.037 [−0.100, −0.003] |
| sensitivity | J30 | NoReaction | 12.5 | 33.3 | 1.484 | 6.67 | 0 | 0 | 1.023 | | |
| sensitivity | J30 | AlwaysSubstitute | 16.7 | 33.3 | 1.463 | 6.55 | 0 | 12.1 | 1.051 | +4.2 [0.0, 12.5] | −0.021 [−0.044, 0.020] |
| sensitivity | J30 | FullResolve | 20.8 | 45.8 | 1.411 | 6.45 | 152.8 | 0 | 1.023 | +8.3 [0.0, 25.0] | −0.073 [−0.081, −0.056] |
| sensitivity | J30 | FullResolve(subst) | 25.0 | 41.7 | 1.422 | 6.63 | 152.1 | 11.6 | 1.049 | +12.5 [0.0, 25.0] | −0.062 [−0.109, 0.008] |
| sensitivity | J30 | StableResolve(subst) | 25.0 | 45.8 | 1.388 | 6.34 | 128.2 | 12.5 | 1.050 | +12.5 [0.0, 25.0] | −0.095 [−0.115, −0.084] |

- The primary smoke run took 49 s (34.9 s in the pool) and the sensitivity one 14 s (8.2 s).
- The sensitivity cells have 24 runs per policy (2 λ_A × 3 instances × 4 replications).
- With three instances per set, the intervals say little.

**Duration estimates** (4 workers). Per-run means were measured through the runner on every
48th instance (10 per set, a subset of the study's every 4th), replication 0, every scenario and
policy. The primary sample took 6.1 min of wall time for 400 runs and the sensitivity sample
1.7 min for 100:

| Set | Policy | λ_A = 0 | 0.005 | 0.01 | 0.02 | E[L] = 5: 0.01 | E[L] = 5: 0.02 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| J30 | NoReaction / AlwaysSubstitute | 0.006 / 0.003 | 0.009 / 0.007 | 0.009 / 0.009 | 0.010 / 0.020 | 0.013 / 0.010 | 0.013 / 0.022 |
| J30 | FullResolve | 0.106 | 1.481 | 2.283 | 3.938 | 2.817 | 4.020 |
| J30 | FullResolve(subst) | 0.104 | 1.475 | 2.374 | 3.749 | 2.586 | 4.006 |
| J30 | StableResolve(subst) | 0.222 | 2.224 | 3.450 | 5.758 | 4.272 | 6.987 |
| J60 | NoReaction / AlwaysSubstitute | 0.004 / 0.006 | 0.007 / 0.011 | 0.008 / 0.018 | 0.009 / 0.042 | | |
| J60 | FullResolve | 0.169 | 4.593 | 7.608 | 10.645 | | |
| J60 | FullResolve(subst) | 0.163 | 4.817 | 7.771 | 11.128 | | |
| J60 | StableResolve(subst) | 0.503 | 7.888 | 12.108 | 14.584 | | |

| Study | Runs | CPU h, measured means × runs | CPU h, first look × measured λ_A profile | Wall at full use | Wall with idle workers |
| --- | ---: | ---: | ---: | ---: | ---: |
| Primary (J30 + J60) | 19,200 | 14.6 (J30 3.6, J60 10.9) | 15.9 (J30 2.9, J60 13.0) | 3.6–4.0 h | about 4–5 h |
| Sensitivity (J30, E[L] = 5) | 4,800 | 3.3 | 2.6 | 0.65–0.8 h | about 1 h |

- **Full use** means CPU / 4.
- **Idle workers.** The pool kept its workers busy 0.76 of the time in the 80-task sample and
  0.80 in the J60 first look. The study has 960 / 240 tasks, so its idle tail is shorter;
  dividing by 0.76 is the pessimistic bound: 4.8–5.2 h and 0.9–1.1 h. The primary study stays
  within the 8 h budget either way.
- **λ_A = 0** is 15–20 times cheaper than λ_A = 0.01, because only D2 and D3 events trigger
  re-plans there.
- **E[L] = 5** costs 1.19× (λ_A = 0.01) and 1.12× (0.02) the run time of E[L] = 3 on the same
  instances.

| Measurement | Value |
| --- | --- |
| Tests | default `pytest -q`: 280 passed, 1 deselected in 85.0 s (81 s before the WP4b runner tests, 216 s with the slow test before the chore); `-m "data or slow"`: 16 passed, 265 deselected in 176.0 s; the slow WP4a policy data test takes about 145 s (131 s in WP4a, more re-plans at return epochs) |
| Engine regression | 50 runs equal to the WP4a engine without epoch counts and flags; 26 gain epochs (1,685 → 1,971 in total) |
| Measured runs | 300 + 300 first look, 480 + 120 smoke, 400 + 100 duration sample: 0 WP2b mismatches (120 + 120 + 100 worlds) and 0 CP-SAT fallbacks in all; 0 rejected operations and 0 truncated runs in the smoke and duration runs (the first-look script does not report them) |
| LaTeX table width | about 116 mm against the 122 mm LNCS text width (Computer Modern metrics, not compiled) |

## Commands for the owner
```bash
cd ~/projects/sentinel && git pull && uv sync --locked
uv run pytest -q                    # expect 280 passed, 1 deselected, ~85 s
uv run pytest -q -m "data or slow"  # expect 16 passed, 265 deselected, ~3 min
# Primary RQ4 baseline study in tmux: 19,200 runs, about 4-5 h with 4 workers. It first times
# up to three instances per set (~2 min) and then prints progress every 10 s.
uv run python -m sentinel.experiments.policy_study --config configs/wp4_baselines.toml --out results/wp4
# Sensitivity E[L] = 5 on J30: 4,800 runs, about 1 h.
uv run python -m sentinel.experiments.policy_study --config configs/wp4_sensitivity.toml --out results/wp4
# Each run directory is under 2 MB (results.csv.gz about 0.7 MB); commit both:
git add results/wp4/<run_id> && git commit -m "WP4b: RQ4 baseline study results" && git push
# Summaries can be regenerated at any time:
uv run sentinel summarise-policies results/wp4/<run_id>
```

## Open issues / next steps
- **Owner:** run both studies and commit `results/wp4/<run_id>/`. Expect 0 WP2b mismatches,
  0 rejected operations and 0 fallbacks in each `summary.md`.
- **Architect:** the two spec questions; the faceted trade-off figure; whether the J30
  planning-view data test should also be `slow`.
- **WP5/WP7:**
  - Sentinel uses the deadline. A study of it needs one run per δ_D, or a single δ_D, instead
    of the post hoc evaluation (ADR-0013).
  - The first look suggests that substitution alone gains little at E[L] = 3, since onboarding
    costs about two crew-member days per replaced member. Sentinel's SUBST candidates are
    therefore a genuine trade-off, as intended.
- The runner's start estimate is rough, because run times differ by an order of magnitude
  between instances. The progress lines extrapolate from completed runs.
