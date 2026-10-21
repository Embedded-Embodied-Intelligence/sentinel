# WP4a report — Interventions in the engine, residual rescheduling and the baseline policies

- Date: 2026-10-21
- Commit(s): ed1537f (spec v1.5), 0812643 and 208c254 (formatting chore: code, then the
  regenerated WP3 tables), 1258235 (operations, planning view, residual SGS and CP-SAT,
  policies), 22540c7 (checked policy runs, data tests, measurement script); the report, notes,
  ADR and roadmap commit follows them

## Summary
The engine's step 3 now applies SUBST and RESEQ (`Run.apply`), shared by `simulate` and by
resumed rollouts. It validates every operation, logs rejections and records substitutions,
handover days, RESEQs and nervousness. A RESEQ must solve the residual problem of the current
planning view. `planning_view` builds that problem from an observation under the deterministic
forecaster's assumptions. It is solved by a serial SGS with release times and a time-varying
capacity, or by CP-SAT for minimum makespan or for minimum deviation subject to the minimum
makespan. On top of these sit `AlwaysSubstitute`, `FullResolve(subst)` and
`StableResolve(subst)`. NoReaction results are unchanged bit for bit; `simulate` is 0.9–1.5 %
slower.

The main finding concerns cost. CP-SAT's deterministic time runs 4–13 times slower than wall
time on these models: T_cp = 0.5 means up to about 2.4 s per search on hard J60 views. The
five-policy study of the prompt would therefore take about 45 h on 4 workers, or about 12 h at
T_cp = 0.05.

## Acceptance criteria
| # | Criterion | Command | Result |
| --- | --- | --- | --- |
| 1 | Spec v1.5 and the formatting chore are separate commits | `git show --stat ed1537f 0812643 208c254` | PASS (`spec: interventions, residual planning and baselines (v1.5)`: §4 SUBST details and RESEQ, new §4.1, §7 baselines, new §7.1, `T_cp` in §8. `chore: typeset negative numbers in LaTeX tables` changes code and test. `chore: regenerate the WP3 LaTeX tables with minus signs (no rerun)` regenerates both runs: 8 `.tex` files, each identical to the old one with `$-$` → `-`, 99 signs; inputs unchanged by SHA-256; figures byte-identical) |
| 2 | Quality gate and `-m data` pass; all task-8 tests exist and pass; engine regression passes | `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy src`; `uv run pytest -q`; `uv run pytest -q -m data` | PASS (ruff clean; 143 files formatted, Markdown included; mypy: no issues in 47 source files; 269 passed; data: 16 passed, 253 deselected; mapping under Changes; `test_fifty_runs_are_unchanged` passes with the fixture unchanged) |
| 3 | Measurements reported; NoReaction timing within 5 % of WP3a | `scripts/bench_simulate.py` (old and new code interleaved); `scripts/bench_policies.py` | PASS. NoReaction `simulate` takes J30 4.65 ms and J60 8.04 ms, against 4.61 / 7.96 ms in WP3a (+0.9 % / +1.0 %); interleaved with the pre-WP4a engine it is +1.5 % / +0.9 %. All task-9 numbers are under Numbers. One gap: J60 at T_cp = 0.5 was measured for FullResolve and StableResolve(subst) on 20 instances × 1 seed; the J60 table for all five policies (20 × 3) uses T_cp = 0.05. The full T_cp = 0.5 run (≈ 30 min) is under Commands for the owner, because runs over ~10 min are not made in the session (CLAUDE.md) |
| 4 | ADR for the residual representation | `docs/adr/0012-residual-problem-representation.md` | PASS (ADR-0012, accepted) |
| 5 | Report, notes, roadmap (`WP4: in progress: WP4a done`); pushed; clean tree | `git push`; `git status --short` | PASS (this report, `docs/notes/WP4a.md`, roadmap; pushed to `origin/main`; `git status --short` empty afterwards) |

## Changes
- `docs/spec/model.md` v1.5 as dictated (separate commit).
- `experiments/forecast_summary.py`: `_tex_num`, `_tex_minus`. LaTeX numbers use a math minus and Markdown keeps the hyphen. Both WP3 summaries were regenerated (`results/wp3/*/`: 8 `.tex` files; `summary.md` and `summary_manifest.json` change only in commit stamp and time).
- `policies/base.py`: `Subst(activity, workers)` (substitutes distinct, at least one), `Reseq(starts)`, the union `Noop | Subst | Reseq`, `DecisionStats`.
- `simulation/engine.py`:
  - `Run.apply` (step 3), `_substitute`, `_infeasible_plan`, `preview`;
  - `Substitution`, `Rejection`, and the result fields `substitutions`, `rejected`, `reseqs`, `nervousness`, `infeasible_reseqs` (left out of dumps while unset), with `n_substituted` and `handover_days`;
  - the `simulate`/`Run` parameters `handover_factor` and `debug`;
  - `_update_crew` adds no empty segment when a crew changes twice in one day.
- `simulation/state.py`:
  - `HANDOVER_FACTOR` (0.3), `Observation.handovers` (left out of dumps while empty), `EngineState.handovers` and `handover_factor`, and `state_from_observation(handover_factor=...)`;
  - `nominal_world`, moved here from `forecasting/deterministic.py` (still importable there) and extended with handovers, plus `nominal_activity` and `work_history`.
- `forecasting/beliefs.py`: the replay includes handovers (`work_history`); `Belief.expected_remaining()`.
- `scheduling/residual.py` (new): `ResidualProblem`, `planning_view`, `validate_residual`, `residual_sgs`. `scheduling/cpsat.py`: `ResidualSolution`, `solve_residual`, `Objective`. `model/schedule.py`: violation kind `release`.
- `simulation/realised.py`: `execution_violations` follows crews through substitutions (slots, roles, absence of the replaced member, presence of the substitute) and reports failed RESEQ plans.
- `policies/urgency.py` (τ_j of §5), `policies/always_substitute.py` (`AlwaysSubstitute`, `substitutions`), `policies/resolve.py` (`DisruptionMonitor`, `FullResolve`, `StableResolve`, `T_CP`), `policies/registry.py` (`COMPARED`, `make_policy`).
- `experiments/policy_runs.py` (new): `PolicyTask`, `PolicyRecord`, `run_policies` (debug mode, every run checked), `check_run`, `realised_deviation` (§7.1).
- `scripts/bench_policies.py` (new): planning-view, policy-run and λ_A timings for this report.
- Tests (task 8 → test):
  - SUBST on a paused one-person activity: `test_interventions.py::test_subst_on_a_paused_one_person_activity`. The substitute works the same day, h = 1 is added, and the replaced worker returns idle and does another activity.
  - SUBST raises ρ_j of a running partial crew: `::test_subst_on_a_running_partial_crew_raises_its_rate`.
  - Non-idle, wrong-role and other invalid operations are rejected and the run goes on: `::test_invalid_operations_are_rejected_and_the_run_goes_on` (8 cases, the valid operation after them applies) and `::test_debug_mode_raises_on_an_infeasible_reseq`.
  - AlwaysSubstitute without an idle worker changes nothing: `test_baseline_policies.py::test_always_substitute_with_no_idle_worker_changes_nothing` (equal results).
  - Residual SGS and CP-SAT plans are feasible on ≥ 50 views and CP-SAT ≤ SGS: `test_residual.py::test_residual_plans_are_feasible_on_random_views` (tiny.sm and random-instance runs), `test_policies_data.py::test_residual_plans_are_feasible_on_j30_planning_views` (60+ J30 views at T_cp = 0.5).
  - X ≡ 1, no disruptions, CP-SAT baseline of tiny.sm: makespan 7, and StableResolve keeps every start: `test_baseline_policies.py::test_resolving_without_disruptions_reproduces_the_cpsat_baseline_of_tiny`. Both policies × subst ∈ {False, True}; besides the plain run, it re-solves on all 8 days and checks nervousness 0 for StableResolve.
  - StableResolve deviation ≤ FullResolve deviation with equal makespan: asserted on every view of `test_residual_plans_are_feasible_on_random_views`, and by hand in `::test_residual_sgs_and_cpsat_respect_a_capacity_dip`.
  - Determinism and CRN for the five policies: `test_baseline_policies.py::test_policies_are_deterministic_and_share_the_exogenous_events` (absence onsets and D3 arrivals identical up to the shortest run).
  - Operations act alike in a resumed rollout and in the world:
    - `::test_operations_act_alike_in_a_resumed_run_and_in_the_world`: rebuilt at an epoch after SUBST and RESEQ, continued with a policy copy, the world's streams and D2 counters, with identical starts, finishes, cost, plan and later substitutions;
    - `::test_perfect_information_rollout_after_subst_and_reseq_reproduces_the_makespan`: `forecast(_true_world=...)` from an observation after SUBST and RESEQ;
    - `test_interventions.py::test_preview_shows_the_state_the_engine_leaves`.
  - Data: `test_policies_data.py::test_reactive_policies_keep_every_realised_schedule_feasible`. 360 runs (20 J30 + 10 J60 × 3 seeds × 4 policies) in debug mode, every realised schedule checked, nothing rejected.
  - Further tests:
    - `test_reseq_replaces_the_plan_and_counts_nervousness`, `test_results_without_interventions_serialise_as_before`, `test_interventions_round_trip_through_validation`, `test_nominal_world_adds_handovers_at_the_observed_work` (the belief excludes P_j = 3, which would have finished before the handover);
    - `test_planning_view_by_hand`, `test_validate_residual_finds_every_kind_of_violation`, `test_estimated_finishes_are_those_of_the_deterministic_forecast` (100+ started activities, handovers included), `test_solver_falls_back_to_the_residual_sgs`, `test_the_residual_solver_is_deterministic`;
    - `test_always_substitute_serves_the_most_urgent_activity_first`, `test_urgency_of_running_and_unstarted_activities`, `test_disruption_monitor_tells_disruptions_from_periodic_epochs`, `test_the_registry_makes_the_five_policies`, `test_policies_see_only_the_observation` (decisions equal on JSON copies of the observations);
    - `test_forecast_study.py::test_latex_tables_typeset_negative_numbers`.
- Docs: ADR-0012, `docs/notes/WP4a.md`, this report, roadmap.

## Decisions
- **SUBST grammar.** `Subst` lists the substitutes only, a simple JSON form for WP6. Within a role, the substitutes in the given order replace the absent members in increasing id order and take their slots in the crew tuple. The engine checks the operation's own fields again, whatever its origin.
- **Handover.** The ceiling ignores rounding noise below 10⁻⁹. h_j counts the substitutes of one operation. The next D2 shock is looked up again, because more work can reach further into the shock stream.
- **RESEQ check in the engine.** Every RESEQ is validated on `planning_view(state.observe())` at the moment it is applied. A failing plan is rejected and counted in `infeasible_reseqs`; with `debug=True` (tests, `run_policies`) it raises AssertionError. 0 occurred.
- **Serialisation.** The new result and observation fields use pydantic's `exclude_if` and are left out while empty or zero. Runs without interventions therefore dump exactly as in WP3, and the 50-run regression fixture is unchanged.
- **α** is a parameter of the world (`simulate`) and of the policies' `preview`, with default 0.3 from §8. It is not part of the observation, like c_k.
- **Planning view** (ADR-0012):
  - F̂_j is computed directly with the engine's subtraction and tested equal to the deterministic rollout;
  - the planning view module needs no OR-Tools. Importing OR-Tools into the engine made NoReaction 2–5 % slower through the larger heap, which was measured with the old engine as well. The CP-SAT model therefore lives in `cpsat.py`.
- **CP-SAT details:**
  - horizon = the residual SGS-LFT makespan;
  - the hint is the current plan if it is a feasible solution within that horizon, else the SGS schedule (see Spec questions), so every stage starts from a complete feasible solution;
  - stage 2 is a fresh model hinted with stage 1;
  - fallbacks: stage 1 to the SGS and stage 2 to stage 1, both counted;
  - seed 0 and `max_time_in_seconds = inf`.
- **Disruption detection** (`DisruptionMonitor`). An epoch counts as event-driven if its absences (worker, first day), D2 count or D3 count differ from the previous epoch's. A policy object therefore serves one run at a time; a new run is recognised by its day.
- **Urgency.** E[remaining_j] is the exact conditional expectation from the belief's pmf. It is computed only when two or more activities compete. Without a deadline the planned makespan replaces D; the order does not change.
- **`preview`** applies a decision through the engine's own `Run.apply` to a state rebuilt from the observation with nominal hidden values. The policies use it to plan their RESEQ on the state their SUBSTs leave.
- **Data test limit.** The data test runs the policies with T_cp = 0.01. At 0.5, a hard J60 run takes minutes and the test would take over 30 min; the checks do not depend on the limit. T_cp = 0.5 runs are checked the same way by the measurement script (340 such runs here).
- **Seeds and deadlines of the measurements follow WP2b.** The 120 NoReaction runs reproduce WP2b's seeds and makespans with 0 mismatches.
- ADRs created: ADR-0012 (representation of the residual problem).

## Deviations
- **Beyond the listed files:**
  - `policies/urgency.py`, `policies/registry.py` and `experiments/policy_runs.py`;
  - the observation field `handovers`;
  - handovers in `nominal_world` and in the belief: without them the deterministic forecaster and the belief would ignore work the agent itself added;
  - `nominal_world` moved to `simulation/state.py` to avoid an import cycle (engine → planning view → forecasting → engine).
- **The formatting chore** is two commits, the code and then the regenerated tables, so the summaries are generated from committed code. `summary.md` and `summary_manifest.json` changed besides the `.tex` files, but only in commit stamp and time, as every regeneration records them.
- **The data test uses T_cp = 0.01** (see Decisions).
- **J60 at T_cp = 0.5** was measured for two policies on 20 × 1 runs instead of all five on 20 × 3 (criterion 3; the command is under Commands for the owner).

## Spec questions
1. **Returns are not decision epochs** (§3.1 g: D1 onsets, D3, the day after D2, periodic). §7 reacts to a D1 "onset or return". Reading used: a return is seen at the next epoch, which then counts as event-driven. Making returns epochs would change NoReaction's epoch count and the WP2b results.
2. **"Hint = the current plan where feasible."** Reading used: the whole current plan if it is a feasible residual solution within the SGS horizon, otherwise the SGS schedule; no partial hints. The current plan is usually infeasible after a delay, because its stale starts lie before t.
3. **"Inserted activities without a planned start are excluded."** Every D3 activity gets a planned start on insertion (§3.1 e), so the exclusion is empty: all unstarted activities enter the deviation sum, the sink and milestones included. Should D3 activities inserted at the current epoch be excluded instead?
4. **Handovers in §5.1 and §5.2.** Reading used: a handover adds h_j M_j crew-member days at the observed work level, after the one-crew-member-day floor of §5.2. The belief requires the activity unfinished before the handover. Please confirm and add it to the spec.
5. **Which absent members does a SUBST replace** when a role has more of them than substitutes? Reading used: increasing id order, which is AlwaysSubstitute's own order.
6. **FullResolve(subst = True) substitutes only at event epochs**, as §7 is written. AlwaysSubstitute substitutes at every epoch. Confirm.
7. **T_cp in deterministic seconds** (§8): 0.5 deterministic seconds took 2.2–2.5 s of wall time on hard J60 views, and an optimal J60 solve takes 62 ms for 0.0047 deterministic seconds. Is a smaller limit intended (Numbers: duration estimate)?

## Numbers
Environment: Intel i5-6600K (4 cores), WSL2 Ubuntu 24.04, uv 0.13.2, CPython 3.12.15, numpy
2.5.4, pydantic 2.14.1, ortools 9.15.6755. Policy runs ran in a pool of 4 workers, times
measured inside the workers. Scenario: λ_A = 0.01 unless stated, E[L] = 3, λ_S = 0.01,
λ_N = 0.02, T_r = 5, `cpsat_det` baseline plans, WP2b seeds, max_days of δ_D = 0.3; on-time is
for D = ⌈1.2 C*⌉.

**NoReaction `simulate`** (`scripts/bench_simulate.py`, 200 calls per set):

| Code | J30 ms | J60 ms |
| --- | ---: | ---: |
| WP3a report | 4.61 | 7.96 |
| Before WP4a (208c254), 3 runs | 4.53 / 4.53 / 4.56 | 7.86 / 7.93 / 7.96 |
| Interleaved, pre-WP4a engine | 4.56 / 4.65 / 4.54 (mean 4.58) | 7.96 / 8.08 / 7.88 (7.97) |
| Interleaved, WP4a engine | 4.72 / 4.61 / 4.63 (mean 4.65, +1.5 %) | 8.13 / 7.98 / 8.02 (8.04, +0.9 %) |
| Pre-WP4a engine + `import ortools` (heap effect, avoided) | 4.56–4.70 | 8.14–8.41 |

One J30 instance on its own: `simulate` 2.99 ms (WP4a) vs 3.01 ms (before); `Run.result()` takes 16.6 µs vs 15.4 µs.

**Planning views and residual solvers** (NoReaction worlds of 10 instances per set at f = 0,
0.25, 0.5, 0.75; this process; medians for the view and the SGS, means for CP-SAT;
"not optimal" counts searches stopped by the limit):

| Set | Views | Activities | planning_view ms | residual_sgs ms | C @0.5 ms | not optimal | stable @0.5 ms | not optimal | C @0.05 ms | not optimal | stable @0.05 ms | not optimal | ΔC @0.05 | Δdeviation @0.05 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| J30 | 40 | 20.2 | 0.132 | 0.099 | 85.3 | 1 | 143.4 | 0 | 33.6 | 3 | 66.5 | 3 | +0.175 d | +1.68 d |
| J60 | 40 | 39.9 | 0.190 | 0.175 | 284.4 | 6 | 567.5 | 5 | 56.2 | 6 | 124.3 | 7 | +0.250 d | +11.43 d |

On the hard J60 instance j6025_1 every search on a view runs to the limit, 2.2–2.5 s per stage
at 0.5. In an ad-hoc check, hinted with the current plan decoded by the residual SGS, it improved
that hint on one of three views (131 → 127 days; 115 and 121 stayed).

**Policy runs, J30, T_cp = 0.5** (20 instances × 3 seeds, 60 runs per policy; 300 runs in 306.7 s
wall; WP2b check: 60 NoReaction runs, 0 mismatches):

| Policy | Mean s | p95 s | Max s | Epochs | Decision ms / epoch | RESEQs | Fallbacks / stages | On time | Deviation d | Nervousness | Substituted | Handover d | C / C* |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| no_reaction | 0.006 | 0.008 | 0.028 | 53.5 | 0 | 0 | 0 / 0 | 0.217 | 7.76 | 0 | 0 | 0 | 1.379 |
| always_substitute | 0.010 | 0.017 | 0.024 | 61.0 | 0.05 | 0 | 0 / 0 | 0.050 | 11.15 | 0 | 28.4 | 26.1 | 1.557 |
| full_resolve | 2.482 | 14.166 | 29.616 | 51.5 | 47.8 | 49.1 | 0 / 2,949 | 0.233 | 8.04 | 211.4 | 0 | 0 | 1.338 |
| full_resolve_subst | 2.893 | 12.379 | 33.979 | 57.7 | 49.7 | 55.3 | 0 / 3,320 | 0.083 | 11.45 | 307.6 | 27.3 | 25.2 | 1.485 |
| stable_resolve_subst | 4.831 | 28.722 | 47.489 | 58.2 | 82.5 | 55.8 | 0 / 6,696 | 0.067 | 11.29 | 275.7 | 27.6 | 25.6 | 1.492 |

**Policy runs, J60, T_cp = 0.05** (20 instances × 3 seeds; 300 runs in 335.3 s wall; WP2b check:
60 NoReaction runs, 0 mismatches):

| Policy | Mean s | p95 s | Max s | Epochs | Decision ms / epoch | RESEQs | Fallbacks / stages | On time | Deviation d | Nervousness | Substituted | Handover d | C / C* |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| no_reaction | 0.009 | 0.013 | 0.032 | 84.1 | 0 | 0 | 0 / 0 | 0.167 | 10.56 | 0 | 0 | 0 | 1.410 |
| always_substitute | 0.021 | 0.042 | 0.058 | 93.3 | 0.09 | 0 | 0 / 0 | 0.067 | 14.89 | 0 | 51.9 | 47.9 | 1.553 |
| full_resolve | 4.464 | 17.821 | 20.132 | 81.5 | 54.3 | 78.6 | 0 / 4,715 | 0.167 | 12.30 | 748.7 | 0 | 0 | 1.371 |
| full_resolve_subst | 5.025 | 20.158 | 23.056 | 89.7 | 55.5 | 86.7 | 0 / 5,201 | 0.083 | 16.03 | 990.3 | 50.7 | 46.9 | 1.498 |
| stable_resolve_subst | 9.529 | 37.005 | 44.320 | 91.0 | 104.2 | 87.9 | 0 / 10,550 | 0.083 | 16.26 | 688.5 | 52.4 | 48.1 | 1.512 |

**Policy runs, J60, T_cp = 0.5** (the same 20 instances, seed of replication 0):

| Policy | Mean s | p95 s | Max s | Decision ms / epoch | RESEQs | Fallbacks / stages | On time | Deviation d | Nervousness | C / C* |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| full_resolve | 19.709 | 87.962 | 94.604 | 238.4 | 79.8 | 0 / 1,595 | 0.250 | 11.16 | 729.9 | 1.355 |
| stable_resolve_subst | 39.347 | 160.507 | 176.042 | 430.0 | 88.3 | 0 / 3,532 | 0.050 | 14.94 | 675.1 | 1.497 |

**CP-SAT fallback rate: 0** in 38,558 stages of the measured policy runs (J30 at 0.5, J60 at
0.05 and at 0.5). Every stage starts from a complete feasible hint.

**First look** (not a study; no intervals; λ_A = 0.01). FullResolve is the only policy that
beats NoReaction:
- J30: on time 0.233 vs 0.217, C / C* 1.338 vs 1.379;
- J60: equal on-time share at T_cp = 0.05, C / C* 1.371 vs 1.410.
Every substituting policy is worse: on time 0.05–0.08, C / C* about 1.49–1.56. A handover costs
at least one full-crew day, more than an absence of E[L] = 3 days during which a partial crew
keeps working. StableResolve(subst) is less nervous than FullResolve(subst), 276 vs 308 changes
(J30) and 689 vs 990 (J60), but no closer to the baseline plan: deviation 11.3 vs 11.5 and 16.3
vs 16.0 days.

**λ_A dependence** (T_cp = 0.05; 10 instances per set × 1 seed; mean s / RESEQs per run):

| Set | Policy | λ_A = 0.0025 | 0.005 | 0.01 | 0.02 |
| --- | --- | ---: | ---: | ---: | ---: |
| J30 | full_resolve | 0.845 / 21.3 | 0.877 / 31.9 | 1.320 / 47.3 | 2.122 / 63.9 |
| J30 | full_resolve_subst | 0.853 / 21.4 | 0.998 / 31.5 | 1.703 / 52.4 | 3.037 / 81.4 |
| J30 | stable_resolve_subst | 1.014 / 21.8 | 1.566 / 32.2 | 2.981 / 52.1 | 5.575 / 81.8 |
| J60 | full_resolve | 1.456 / 33.1 | 2.337 / 50.5 | 3.872 / 74.7 | 5.896 / 97.5 |
| J60 | full_resolve_subst | 1.424 / 33.7 | 2.490 / 50.9 | 3.979 / 83.7 | 7.160 / 124.7 |
| J60 | stable_resolve_subst | 2.821 / 33.5 | 4.187 / 51.6 | 8.203 / 82.3 | 14.367 / 130.9 |

NoReaction and AlwaysSubstitute stay below 0.05 s per run at every λ_A.

**Duration estimate** for 480 instances × 2 sets × 4 λ_A × 4 replications × 5 policies (76,800
runs, 7,680 per set and policy). CPU hours = 7,680 × mean run time at λ_A = 0.01 × the λ_A
factor (mean over the grid / value at 0.01, from the table above):

| Set | Policy | s / run @0.5 | λ factor | CPU h @0.5 | s / run @0.05 | CPU h @0.05 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| J30 | no_reaction, always_substitute | 0.006, 0.010 | 0.92, 1.05 | 0.03 | same | 0.03 |
| J30 | full_resolve | 2.482 | 0.98 | 5.2 | 1.320 | 2.8 |
| J30 | full_resolve_subst | 2.893 | 0.97 | 6.0 | 1.703 | 3.5 |
| J30 | stable_resolve_subst | 4.831 | 0.93 | 9.6 | 2.981 | 5.9 |
| J60 | no_reaction, always_substitute | 0.009, 0.021 | 1.06, 1.13 | 0.07 | same | 0.07 |
| J60 | full_resolve | 19.709 | 0.88 | 36.8 | 4.464 | 8.3 |
| J60 | full_resolve_subst | 22.19 (estimated) | 0.95 | 44.8 | 5.025 | 10.1 |
| J60 | stable_resolve_subst | 39.347 | 0.90 | 75.7 | 9.529 | 18.3 |
| | **Total** | | | **178 h → ≈ 45 h on 4 workers** | | **49 h → ≈ 12 h** |

Sources and assumptions:
- J30 at 0.5 and J60 at 0.05 are 20 × 3 means. J60 at 0.5 are 20 × 1 means, with
  full_resolve_subst scaled from full_resolve by their ratio at 0.05.
- The J30 column at 0.05 comes from the λ sample (10 × 1).
- J60 is 88 % of the total.
- With every 4th instance (120 per set) the study takes ≈ 11 h at T_cp = 0.5 and ≈ 3 h at 0.05.
- The slowest J60 runs take up to 3 min each at 0.5.

| Measurement | Value |
| --- | --- |
| Tests | 269 passed in 216 s (238 before WP4a, 31 new); `-m data` 16 passed, 253 deselected in 167 s; the WP4a data test takes 131 s |
| Data test runs | 360 policy runs (T_cp = 0.01) and 60+ J30 views (T_cp = 0.5), 0 violations, 0 rejections |
| Measured runs | 640 checked policy runs (340 at T_cp = 0.5, 300 at 0.05) and 400 in the λ sample: 0 violations, 0 rejected operations, 0 infeasible RESEQs |
| WP3 tables | 8 regenerated `.tex` files, 99 minus signs |

## Commands for the owner
```bash
cd ~/projects/sentinel && git pull && uv sync --locked
uv run pytest -q                    # expect 269 passed, ~3.6 min (data tests included)
uv run pytest -q -m data            # expect 16 passed, ~2.8 min
# Full WP4a measurement at T_cp = 0.5 in tmux, ~30 min with 4 workers. The slowest J60
# instance alone takes ~20 min. Prints the views table and the 20 x 3 tables of both sets.
uv run python scripts/bench_policies.py --views 10 --runs j30:20:3 --runs j60:20:3 --cp-limit 0.5
# The lambda_A sample of this report (~6 min):
uv run python scripts/bench_policies.py --views 0 --lambdas j30:10 --lambdas j60:10 --lambda-cp-limit 0.05
```

## Open issues / next steps
- **Architect, before WP4b:**
  - T_cp and the study size: ≈ 45 h at T_cp = 0.5 against ≈ 12 h at 0.05, which costs +0.25 days of residual makespan per J60 view; every 4th instance takes ≈ 11 h / 3 h;
  - spec questions 1–7.
- **WP4b:** a config-driven study runner on top of `run_policies` (manifest, results.csv with the §7.1 columns, summaries); `realised_deviation` and the counts are ready.
- **WP5:**
  - a candidate is applied to a rebuilt state with `Run.apply` before `Run.resume()`;
  - SUBST and RESEQ operations exist; the residual SGS decodes a plan in 0.1–0.2 ms;
  - the belief and the deterministic forecaster handle handovers;
  - the substitution result of the first look matters for Sentinel's SUBST candidates.
- `pytest -q` now takes 3.6 min instead of 1.2 min because of the WP4a data test (131 s).
