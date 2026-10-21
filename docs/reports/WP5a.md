# WP5a report — Sentinel core: overtime, candidates, rollout evaluation and the decision rule

- Date: 2026-10-21
- Commit(s): 81b8f33 (spec v1.7), 2d9a678 (OVERTIME and SHIFT in the engine), afeb1e7 (agent:
  candidates, racing evaluation, decision rule, policy, tests), 67f9e7b (measurement script,
  decision reasons); the report, notes, ADR and roadmap commit follows them

## Summary
Sentinel now runs: a one-step rollout policy on NoReaction that deliberates at crew-touching
and periodic epochs, stops at the needs gate, generates the eight rule candidates of spec v1.7,
races them on shared sampled worlds and applies the lexicographic choice, leaving a decision
record per epoch. The engine has OVERTIME (temporary workers, paid 1.5 c_k per hired day) and
SHIFT (the order-preserving repair) as operations, in the world and in rollouts, with
NoReaction results unchanged. Mean deliberation takes 0.60 s on J30 and 1.09 s on J60 (targets
1.5 s and 3 s), 25 s and 71 s per run at λ_A = 0.01. The RQ4 study of both variants on the
plan's subset would take about 91 CPU h, 23–30 h on 4 workers per δ_D. The first look shows
lower C / C* than NoReaction and FullResolve with fewer plan changes than FullResolve, but the
budget component decides most choices on cost differences of about 0.03 % (Spec questions).

## Acceptance criteria
| # | Criterion | Command | Result |
| --- | --- | --- | --- |
| 1 | Spec v1.7 commit | `git show --stat 81b8f33` | PASS (`spec: Sentinel core, overtime and candidates (v1.7)`, only `docs/spec/model.md`: §4 SHIFT and OVERTIME, §4.1 temporary workers, §5 Δ and needs gate, §6 candidates, evaluation, racing, deliberation epochs, §8 parameters) |
| 2 | Quality gate (default `pytest -q` ≤ 90 s) and `-m "data or slow"` pass; all task-6 tests exist and pass | `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy src`; `uv run pytest -q`; `uv run pytest -q -m "data or slow"` | PASS (ruff clean; 168 files formatted; mypy: no issues in 56 source files; `pytest -q`: 297 passed, 2 deselected in 87.5 s; `-m "data or slow"`: 17 passed, 282 deselected in 328.2 s; task-6 mapping under Changes) |
| 3 | Measurements, first look and duration estimate reported; deliberation targets met or a profile plus plan | `uv run python scripts/bench_sentinel.py --runs j30:20:1 --profile j30:j3013_1`, `--runs j60:10:1`, `--lambdas j30:5 --lambdas j60:3` | PASS with a smaller sample: targets met (mean deliberation 0.595 s J30, 1.089 s J60); tables under Numbers. The prompt's 20 instances × 3 seeds per set take about 1.5–2 h, so the session measured 20 × 1 (J30) and 10 × 1 (J60); the full command is under Commands for the owner |
| 4 | ADRs for the package layout and racing | `docs/adr/0014-agent-package-layout.md`, `docs/adr/0015-racing-on-shared-worlds.md` | PASS (both accepted) |
| 5 | Report, notes, roadmap (`WP5: in progress: WP5a done`); pushed; clean tree | `git push`; `git status --short` | PASS (this report, `docs/notes/WP5a.md`, roadmap; pushed to `origin/main`; `git status --short` empty afterwards) |

## Changes
- `docs/spec/model.md` v1.7 (own commit): the binding decisions of the prompt in §4, §4.1, §5,
  §6, §8; the stale sentence "Rollouts decode plans with the serial SGS" gave way to the
  evaluation paragraph.
- `policies/base.py`: `Shift(starts)` (level 0) and `Overtime(role, workers, days)` (level 2)
  in the operation union; `LEVELS`; `Decision.level`.
- `simulation/state.py`: `OVERTIME_CAP` (γ), `OVERTIME_RATE` (1.5), `overtime_cap`,
  `TemporaryWorker`, `Observation.temporary` (left out of dumps while empty), `worker_roles`;
  `EngineState` with temporary workers (`hire`, `leave`, `count_hired`, `release` sending them
  home after their window, `wage`, temporary-worker pay counters) and `copy()`;
  `state_from_observation` rebuilds temporary workers; `nominal_world` treats only original
  workers as absent.
- `simulation/engine.py`: `Run.apply` for SHIFT (checked by `validate_shift`) and OVERTIME
  (`_hire`, cap ⌊γ R_k⌋ hired at a time); idle temporary workers leave at the start of the day
  after their window (`_window_end`); their pay in step 5; crews cost only their original
  members' c_k; result fields `shifts`, `temporary`, `temporary_days` and `overtime_cost`
  (left out of dumps while unset) and the property `hired`; `rehearse` (preview plus
  rejections);
  `Run(check_plans=False)` for decisions checked on the same observation; `_update_crew` with
  `compress`/`map` (same arithmetic).
- `simulation/realised.py`: realised instances count temporary workers; `execution_violations`
  checks that they are never absent, in crews only while hired, join only in their window, and
  the daily capacity R_k plus the temporary workers hired that day.
- `scheduling/residual.py`: temporary workers in the planning view; profiles may exceed R_k
  before their last step; `shift_order`, `shift_sgs` (and its `railway` variant),
  `validate_shift`; the serial SGS split into `_list_order` and `_serial_sgs` (same output).
- `scheduling/cpsat.py`: cumulative capacity at the profile's peak; objective "deviation"
  (minimum deviation within a makespan bound, hinted and falling back to a given solution);
  `_deviation_model` shared with stage 2 of "stable" (models unchanged without temporary
  workers).
- `model/schedule.py`: violation kind `order`.
- `forecasting/forecast.py`: `rollout_streams` (absences of original workers only);
  `forecasting/streams.py`: `RolloutStreams.rewind`; `forecasting/beliefs.py`: absences of
  original workers only; `policies/always_substitute.py`: roles of temporary workers.
- New `agent/`: `params.py` (`SentinelParams`), `candidates.py` (`Candidate`, `generate`,
  `single_substitutions`, `most_backlogged_role`), `evaluate.py` (`Evaluator`, `race`,
  `CandidateStats`, `paired_se`, `instability`), `decide.py` (`choose`, `Needs`,
  `DecisionRecord`).
- New `policies/sentinel.py` (`Sentinel`, `SentinelStats`); `policies/registry.py`:
  `SENTINELS` and `make_policy(run_seed=..., sentinel=...)`.
- `experiments/policy_runs.py`: `PolicyTask.agent_delta` and `.sentinel`; Sentinel gets the
  deadline of `agent_delta`; `PolicyRecord.shifts`, `.hired`, `.overtime_cost`;
  `run_checked` passes the run seed.
- New `scripts/bench_sentinel.py`.
- Tests (task 6 → test):
  - OVERTIME:
    - `test_overtime_shift.py::test_temporary_workers_are_dispatched_paid_and_stay_in_their_crew`
      (dispatched, in the crew past the window, 3 days × 1.5 paid, leaves when its activity ends);
    - `::test_an_idle_temporary_worker_leaves_when_its_window_ends` (present for H days, then
      gone);
    - `::test_a_temporary_worker_substitutes_with_onboarding_and_stays_after_its_window`;
    - `::test_overtime_is_capped_at_floor_gamma_r_k`;
    - `::test_absences_of_the_original_workers_do_not_depend_on_overtime` (same absences with
      and without hiring; no temporary worker absent);
    - `::test_rebuilt_state_and_perfect_information_rollout_with_temporary_workers`.
  - SHIFT: `::test_shift_keeps_the_order_and_never_ends_later_than_the_railway_decode` (240+
    views), `::test_shift_keeps_an_order_that_the_plain_decode_changes`,
    `::test_the_engine_applies_a_shift_and_rejects_one_that_changes_the_order`.
  - Candidates: `test_sentinel.py::test_generated_candidates_are_valid_distinct_and_within_the_limits`
    (every candidate rehearsed without rejection, SUBST only for eligible activities, at most
    3 single SUBSTs and 10 candidates, `no_overtime` without OVERTIME).
  - Evaluator: `::test_a_duplicated_candidate_gets_identical_statistics` (also equal to the
    forecaster's rollouts with the same seed), `::test_racing_keeps_the_best_candidate_by_n`.
  - Decision rule: `::test_the_decision_rule_caps_ties_and_ranks_budget_stability_and_level`.
  - Policy: `::test_sentinel_is_deterministic_feasible_and_no_overtime_never_hires`,
    `::test_sentinel_deliberates_only_at_crew_events_and_periodic_epochs`,
    `::test_the_needs_gate_returns_noop_without_candidates`,
    `::test_perfect_information_rollout_after_overtime_subst_and_reseq` (a Sentinel run that
    hired, substituted and re-planned).
  - Data, slow: `test_sentinel_data.py::test_sentinel_runs_on_j30_are_feasible` (5 J30 × 2
    WP2b seeds, Sentinel `full` with spec parameters; every run checked, no rejection).
  - Regression: `test_engine_regression.py::test_fifty_runs_are_unchanged` passes with the
    fixture unchanged; one expectation in `test_interventions.py` names SHIFT in the
    infeasible-plan message.
- Docs: ADR-0014, ADR-0015, `docs/notes/WP5a.md`, this report, roadmap.

## Decisions
- **Temporary workers.** Ids follow the original workers in hiring order; the observation's
  per-worker tuples include them (present while hired), and `temporary` records (id, role,
  hired, until, left). An idle one leaves at the start of day `until`; one in a crew leaves
  when its activity completes at the end of a day ≥ until − 1. Pay accrues in step 5 for each
  hired day the run simulates. Rollout streams draw absences for the original workers only.
- **SHIFT carries its plan** (`Shift(starts)`), like RESEQ; the engine accepts it only if it is
  a feasible residual solution whose starts are non-decreasing along `shift_order`.
- **Candidate filter.** Each candidate is rehearsed with the engine's own `Run.apply` on the
  observed state; a candidate is dropped on any rejection or if its effect (operations other
  than RESEQ/SHIFT, and the planned starts left for activities with p_j > 0) repeats an earlier
  one, so a SHIFT equal to the current plan never costs rollouts.
- **RESEQ-S** is one CP-SAT stage: minimum deviation over U'_t with makespan ≤ SHIFT's, horizon
  max(SGS-LFT makespan, SHIFT's), hinted with and falling back to the SHIFT plan.
- **OT(k*)**: ties of the backlog go to the smaller role id; no candidate if every backlog is 0
  or ⌊γ R_k*⌋ = 0. SUBST(j) uses the full idle pool for j alone; SUBST-ALL is AlwaysSubstitute's.
- **Evaluation** (ADR-0015): one sampled world per rollout index and epoch, a copy of its
  rebuilt state per candidate, its streams rewound; outcomes kept by label (NOOP's gate
  rollouts reused). Dropped candidates keep their stage-1 statistics.
- **Decision rule.** Ties: within `se_factor` = 2 paired SE of the best (≤, so identical
  candidates tie). After o, Δ and ℓ, the larger capped estimate, then the earlier candidate.
  A deliberation with NOOP as the only valid candidate returns it without further rollouts.
- **Deliberation epochs**: compared with the previous epoch's observation: D2 count, D3 count,
  and presence changes of original workers who are in a started activity's crew now.
- **Seeds**: epoch t uses s_t = derive_seed(run seed, "sentinel", str(t)); rollout i uses
  derive_seed(s_t, "rollout", str(i)), the forecaster's layout.
- **Budget.** B = 1.1 Σ r_jk p̄_j (β = 0.1, c_k = 1) from the observation's instance and PERT.
- **Runner integration.** `make_policy("sentinel_full" | "sentinel_no_overtime" |
  "sentinel_scalarised", run_seed=...)`; in `run_policies` Sentinel works towards D(δ_D =
  `agent_delta` = 0.2), so its max_days is 5 D(0.2), while baselines keep 5 D(0.3).
- **Speed** (cheap wins of task 7, applied before the measurement): state copies, rewound
  streams and skipped plan re-checks cut a J30 deliberation from 1.363 s to 0.832 s with
  identical decisions; `_update_crew` with `compress`/`map` to 0.806 s (Numbers).
- ADRs created: ADR-0014 (agent package layout), ADR-0015 (racing on shared worlds).

## Deviations
- **Measurement size.** 20 × 1 (J30) and 10 × 1 (J60) instead of 20 × 3 per set, and λ_A
  samples of 5 (J30) and 3 (J60) instances: the full measurement takes about 1.5–2 h and runs
  over ~10 min go to the owner. The sample runs took 5.4 + 7.8 + 8.4 min, and a rerun of
  Sentinel `full` (5.7 min) collected the deciding reasons; decisions were identical.
- **Spec text beyond the dictated words**: the §4.1 bullet on temporary workers spells out
  "the planning view extended by the temporary workers"; the §6 sentence "Rollouts decode plans
  with the serial SGS" was replaced by the evaluation paragraph (rollouts execute the candidate's
  plan by dispatch under NoReaction).
- **Beyond the listed files**: `policies/registry.py`, `experiments/policy_runs.py`,
  `forecasting/{forecast,streams,beliefs}.py`, `policies/always_substitute.py`,
  `model/schedule.py`, `scheduling/cpsat.py`, `EngineState.copy`, `rehearse`, `check_plans`.
- **Sentinel's max_days** is 5 D(0.2) in the runner, against 5 D(0.3) for the baselines (no run
  was truncated in the samples).

## Spec questions
1. **SHIFT's order** (§4; `shift_sgs`, `# SPEC-Q`). The serial SGS with the planned starts as
   priority list can start a later activity first: on day 10 with one free unit until day 13,
   B (planned 14, released 12) starts on day 12, before A (planned 13)
   (`test_shift_keeps_an_order_that_the_plain_decode_changes`). Reading used: every activity
   with p_j > 0 starts no earlier than the one before it in the list (ties by id), so the order
   never changes; the test's "current plan's SGS decode" is the same list decoded under the
   railway rule (nothing before its planned start), which equals the current plan where that
   is feasible, and SHIFT is never later than it (argument in the `shift_sgs` docstring). Consequence: a
   delayed activity holds back every later-planned one; on 204 NoReaction views SHIFT equalled
   the railway decode, and it moved activities earlier only with early finishes. Without the
   constraint, a level-0 action could re-sequence. Confirm, or allow the plain decode?
2. **Budget decides on noise.** o is compared exactly. Under NoReaction cost / B is 1.02–1.05
   (B allows 10 % over the nominal cost, D2 and D3 add more), so o > 0 at most epochs and
   decides 61–74 % of deliberations, before stability (11–26 %) and the deadline (2–4 %). In
   622 budget-decided deliberations of 20 J30 runs, the chosen candidate's ẑ was below the
   runner-up's by a median 0.03 % (90th percentile 0.13 %); in 301 of them every candidate had
   p̂ = 0. Should differences of o within 2 paired standard errors (or below ε_B) be ties too?
3. **Hopeless and certain epochs.** When every candidate is late in all rollouts (or above
   θ_D), the deadline component carries no signal and racing drops nothing. Should a lateness
   measure (E[C] or E[max(0, C − D)]) break that tie, so that late projects still aim to finish
   earlier?
4. **Needs gate sequencing** (§5 "N₁ rollouts, then up to N"). Reading used: stop at N₁ only
   when the N₁ rollouts show a need beyond 2 standard errors; else extend NOOP to N, so NOOP is
   returned only on N rollouts.
5. **Overtime pay while working** (§4, §3 cost). Reading used: a temporary worker costs
   1.5 c_k per hired day, idle or working; its crew work adds no c_k on top.
6. **Overtime cap and window end.** Readings used: at most ⌊γ R_k⌋ temporary workers of a role
   are hired at a time (those past their window but still in a crew count), so OT(k*) is
   invalid while k*'s are hired; window days after the project ends are not paid.
7. **B and c_k are not in the observation.** Sentinel derives B with β = 0.1 and c_k = 1, as
   all studies use. Should the observation carry B (and c_k)?
8. **Scalarised ablation and racing.** Reading used: racing on the capped on-time estimate as
   for the lexicographic rule, U_a among the survivors.
9. **Deadline per study run.** Sentinel works towards one D; the first look used δ_D = 0.2 and
   evaluated δ_D = 0.3 post hoc. A study of both needs one run per δ_D (ADR-0013).

## Numbers
Environment: Intel i5-6600K (4 cores), WSL2 (Linux 6.18), uv 0.13.2, CPython 3.12.15, numpy
2.5.4, ortools 9.15.6755, pydantic 2.14.1. Primary scenario at λ_A = 0.01 (E[L] = 3,
λ_S = 0.01, λ_N = 0.02, T_r = 5), `cpsat_det` baselines, WP2b seeds of replication 0,
D = ⌈1.2 C*⌉ for Sentinel; T_cp = 0.1, N₁ = 50, N = 200. Runs in a spawn pool of 4 workers,
timed inside the workers.

**Timing** (J30: 20 spread instances, every 24th; J60: 10, every 48th):

| Set | Variant | Runs | Deliberation mean s | p95 s | max s | Deliberations / run | Gate exits / run | Skipped epochs / run | Candidates / deliberation | Rollouts / deliberation | CP-SAT s / deliberation | s / run | p95 s / run |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| J30 | full | 20 | **0.595** (target 1.5) | 1.311 | 3.082 | 41.9 | 0.7 | 25.2 | 4.18 | 804 | 0.074 | 25.1 | 44.4 |
| J30 | no_overtime | 20 | 0.544 | 1.287 | 3.166 | 42.4 | 0.5 | 24.9 | 3.65 | 699 | 0.070 | 23.3 | 42.8 |
| J60 | full | 10 | **1.089** (target 3.0) | 2.769 | 4.620 | 65.1 | 3.1 | 29.8 | 4.95 | 921 | 0.211 | 71.4 | 158.2 |
| J60 | no_overtime | 10 | 1.002 | 2.630 | 4.448 | 65.8 | 3.0 | 29.9 | 4.54 | 840 | 0.200 | 66.4 | 142.0 |

Candidates per deliberation count NOOP and exclude gate exits; rollouts per deliberation
include them. 0 rejected operations and 0 WP2b mismatches (30 NoReaction runs); CP-SAT
fallbacks and truncated runs were not printed in these runs (the script prints them now).

**Speed-ups** (j30/j3013_1, replication 0, one process; decisions identical, makespan 75 and
cost 3837 in all three):

| Code | Deliberation mean s | p95 s | Run s |
| --- | ---: | ---: | ---: |
| fresh state and streams for every rollout | 1.363 | 3.425 | 54.6 |
| shared worlds: state copies, rewound streams, no plan re-check | 0.832 | 2.270 | 33.5 |
| and `_update_crew` with `compress`/`map` | 0.806 | 2.211 | 32.4 |

**Profile** (j30/j3013_1 under cProfile, 58.4 s): candidate rollouts 47.3 s (81 %), of which
the engine's day loop (`Run.resume`) 36.8 s, sampling worlds with their state and streams
5.2 s, state copies 3.2 s; in the day loop `close_day` 15.9 s, `_absences` 8.4 s, `_finish`
6.6 s, `_dispatch` 6.3 s, `_update_crew` 4.6 s. CP-SAT takes 0.07 s (J30) and 0.21 s (J60) per
deliberation. The remaining cost is the engine's day loop: about 800–900 rollouts per
deliberation.

**First look** (not a study; λ_A = 0.01; means per run; on time δ_D = 0.3 post hoc):

| Set | Policy | Runs | On time δ=0.2 | On time δ=0.3 | C / C* | Deviation d | Nervousness | Cost / B | Overtime share | Substituted | Hired | RESEQs | SHIFTs | s / run |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| J30 | NoReaction | 20 | 0.200 | 0.400 | 1.388 | 7.50 | 0 | 1.038 | 0 | 0 | 0 | 0 | 0 | 0.01 |
| J30 | FullResolve | 20 | 0.200 | 0.450 | 1.351 | 7.58 | 208.4 | 1.039 | 0 | 0 | 0 | 62.8 | 0 | 1.83 |
| J30 | Sentinel full | 20 | 0.200 | 0.500 | 1.343 | 7.54 | 148.2 | 1.048 | 0.0129 | 0.6 | 2.3 | 7.0 | 7.0 | 25.14 |
| J30 | Sentinel no_overtime | 20 | 0.150 | 0.500 | 1.351 | 7.76 | 148.3 | 1.037 | 0 | 0.4 | 0 | 6.3 | 7.2 | 23.31 |
| J60 | NoReaction | 10 | 0.300 | 0.400 | 1.359 | 8.86 | 0 | 1.020 | 0 | 0 | 0 | 0 | 0 | 0.01 |
| J60 | FullResolve | 10 | 0.400 | 0.500 | 1.341 | 11.07 | 690.2 | 1.019 | 0 | 0 | 0 | 93.0 | 0 | 7.52 |
| J60 | Sentinel full | 10 | 0.400 | 0.400 | 1.315 | 10.54 | 384.9 | 1.021 | 0.0063 | 1.2 | 1.8 | 11.6 | 8.0 | 71.44 |
| J60 | Sentinel no_overtime | 10 | 0.300 | 0.400 | 1.325 | 10.67 | 377.3 | 1.017 | 0 | 1.3 | 0 | 10.7 | 7.9 | 66.45 |

- One run is 5 pp (J30) or 10 pp (J60) of on-time share, so the on-time columns cannot
  separate the policies here.
- Sentinel has the lowest C / C* of the four on both sets. It changes fewer planned starts than
  FullResolve (148 vs 208 on J30, 385 vs 690 on J60) with about a tenth of its RESEQs; a SHIFT
  re-times many starts at once.
- `full` hires 2.3 (J30) and 1.8 (J60) temporary workers per run; overtime is 1.3 % and 0.6 % of
  the cost.

**Chosen actions** (share of deliberations in %; `full` and `no_overtime` on the same runs):

| Set | Variant | Deliberations | Gate exit | NOOP | SHIFT | RESEQ-M | RESEQ-S | SUBST(j) | SUBST-ALL | SUBST-ALL+RESEQ-M | OT+RESEQ-M |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| J30 | full | 837 | 1.6 | 63.7 | 16.8 | 11.1 | 3.8 | 1.0 | 0.1 | 0.2 | 1.7 |
| J30 | no_overtime | 848 | 1.2 | 66.2 | 16.9 | 11.2 | 3.7 | 0.8 | 0.0 | 0.1 | 0.0 |
| J60 | full | 651 | 4.8 | 63.9 | 12.3 | 10.6 | 6.0 | 1.2 | 0.0 | 0.5 | 0.8 |
| J60 | no_overtime | 658 | 4.6 | 65.8 | 12.0 | 10.2 | 5.8 | 1.4 | 0.0 | 0.3 | 0.0 |

**Deciding component** (`full`, same runs, % of deliberations):

| Set | Needs met | Only candidate | On time | Budget | Stability | Level | Order |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| J30 | 1.6 | 8.4 | 4.1 | 74.3 | 11.6 | 0.1 | 0.0 |
| J60 | 4.8 | 4.8 | 2.2 | 61.4 | 26.3 | 0.6 | 0.0 |

**Duration estimate**, RQ4 study on the plan's subset (120 instances per set, λ_A ∈ {0, 0.005,
0.01, 0.02}, R = 4, one δ_D): 1,920 runs per set and variant. The λ_A profile comes from the
λ sample (replication 0; J30 5, J60 3 spread instances); it is scaled to the larger samples at
λ_A = 0.01 above, because the 3 J60 instances are cheaper than the 10 (36.7 vs 71.4 s per run):

| Set | Variant | s / run @ 0 | @ 0.005 | @ 0.01 | @ 0.02 (λ sample) | λ factor | s / run @ 0.01 (timing table) | Mean s / run | CPU h |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| J30 | full | 6.1 | 15.8 | 25.9 | 40.8 | 0.855 | 25.1 | 21.5 | 11.5 |
| J30 | no_overtime | 5.5 | 14.0 | 23.5 | 37.7 | 0.858 | 23.3 | 20.0 | 10.7 |
| J60 | full | 10.9 | 25.1 | 36.7 | 64.7 | 0.936 | 71.4 | 66.8 | 35.6 |
| J60 | no_overtime | 9.6 | 23.1 | 33.3 | 59.7 | 0.944 | 66.4 | 62.7 | 33.4 |
| | **Total** | | | | | | | | **91.2** |

- At full use of 4 workers this is 22.8 h; with the pool's idle share of WP4b (0.76 busy),
  about 30 h. Both δ_D take twice as long.
- The λ sample alone, without the scaling, gives 57.7 CPU h.
- For comparison, the five baselines took 14.6 CPU h (WP4b).
- Rollouts are about 80 % of the time, so N₁ = 25, N = 100 would roughly halve it.
  Restricting J60 (69 CPU h of the 91) to 60 instances halves its share.

| Measurement | Value |
| --- | --- |
| Tests | default `pytest -q`: 297 passed, 2 deselected in 87.5 s (280 before WP5a, 17 new and 1 new deselected); `-m "data or slow"`: 17 passed, 282 deselected in 328.2 s; new slow data test 151 s (10 Sentinel runs on 4 workers) |
| Measured runs | 120 runs of the timing and first look, 64 of the λ sample, 30 of the reasons rerun and 4 of a format check, all in debug mode with every realised schedule checked: 0 rejected operations, 0 WP2b mismatches; the slow data test also finds 0 CP-SAT fallbacks in its 10 Sentinel runs |
| Engine regression | 50 runs unchanged (fixture unchanged) |

## Commands for the owner
```bash
cd ~/projects/sentinel && git pull && uv sync --locked
uv run pytest -q                    # expect 297 passed, 2 deselected, ~88 s
uv run pytest -q -m "data or slow"  # expect 17 passed, 282 deselected, ~5.5 min
# Full WP5a measurement in tmux, about 1.5-2 h on 4 workers: timing, first look, chosen
# actions and reasons on 20 x 3 per set, the lambda_A sample on 10 instances per set with the
# duration estimate:
uv run python scripts/bench_sentinel.py --runs j30:20:3 --runs j60:20:3 --lambdas j30:10 --lambdas j60:10
```

## Open issues / next steps
- **Architect:** spec questions 1–9; above all the budget component (2) and late projects
  (3), which decide how Sentinel behaves in most deliberations; and the study size: about
  91 CPU h per δ_D for `full` and `no_overtime`, or about half with N₁ = 25, N = 100.
- **WP5b:** the permission gate goes between `choose` and the returned decision (levels are in
  every `DecisionRecord`); deferral needs τ_t (`policies/urgency.py`); DESCOPE becomes another
  `Candidate` kind; the study runner can reuse `run_policies` with `agent_delta` per δ_D.
- **WP6:** LLM proposals become `Candidate`s and pass `rehearse` like the rule candidates;
  explanations read `DecisionRecord` (reason, ties, statistics).
- The roadmap row of WP4 still reads "in progress: WP4b smoke done", although both studies
  are committed; left for the architect.
