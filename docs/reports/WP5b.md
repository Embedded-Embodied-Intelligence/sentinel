# WP5b report — material decision rule, permission gate, rollout budget, Sentinel study configs

- Date: 2026-10-22
- Commit(s): d467a53 (spec v1.8), a815bcd (rule, gate and DESCOPE in the agent and engine),
  6af2ea0 (spec: rollout budget), 3ee9ef4 (study runner, configs, summaries, scripts), 96bdb95
  (trade-off figure); the report, notes, ADR and roadmap commit follows them

## Summary
Sentinel now decides by the material rule of spec v1.8: expected tardiness is the second
deadline component, and ties come within 2 paired standard errors or below each threshold. The
budget therefore decides at most 2 % of deliberations instead of 61–74 %. The permission gate
(deferral, escalation, approval days as decision epochs, re-validation, imagined delays in
rollouts) and DESCOPE work in the world and in rollouts, and NoReaction is bit-identical to
WP2b/WP4b. The rollout-budget study adopted (N₁, N) = (25, 100): 90.3 % agreement with N = 800,
losses 0.0014 in p̂ and 0.023 day in T̂. With it a deliberation takes 0.40 s (J30) and 0.74 s
(J60), and Sentinel has the lowest C / C* of the first look with a quarter to a fifth of
FullResolve's plan changes. Both study configs smoke-ran with every output and 0 join
mismatches, but as planned they need 14.4 h (main) and 9.0 h (ablation) on 4 workers, over the
12 h and 6 h budgets, so options are reported and the studies wait for a decision.

## Acceptance criteria
| # | Criterion | Command | Result |
| --- | --- | --- | --- |
| 1 | Spec v1.8 commit and the rollout-budget decision recorded in the spec | `git show --stat d467a53 6af2ea0` | PASS (`spec: material decision rule, permission gate, descope (v1.8)`; follow-up `spec: rollout budget N1 = 25, N = 100 from the WP5b study (v1.8)`; both touch only `docs/spec/model.md`) |
| 2 | Quality gate (default `pytest -q` ≤ 90 s) and `-m "data or slow"` pass; task-1 tests exist | `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy src`; `uv run pytest -q`; `uv run pytest -q -m "data or slow"` | PASS (ruff clean; formatted; mypy: no issues in 56 source files; `pytest -q`: 312 passed, 2 deselected in 89.0 s (88.9 s in an earlier run); `-m "data or slow"`: 17 passed, 297 deselected in 285.3 s; task-1 tests under Changes) |
| 3 | Rollout-budget table, re-measured timing, deciding-component table and first look reported | `scripts/bench_rollout_budget.py --runs j30:10 --runs j60:5`; `scripts/bench_sentinel.py --runs j30:20:2 --runs j60:10:2 --policies no_reaction full_resolve sentinel_full sentinel_gate` | PASS (722 deliberations; tables under Numbers) |
| 4 | Both smoke runs produce every output; WP4b baseline join 0 mismatches; full commands with measured estimates | `python -m sentinel.experiments.policy_study --config configs/wp5_rq4_main.toml --out results/wp5 --limit 2`, same for `wp5_rq4_ablation.toml`; spread samples through the runner | PASS with the budget reported as exceeded (both runs completed with every output, 0 WP2b and 0 WP4b-join mismatches, 0 rejected operations, fallbacks or truncated runs; estimates 14.4 h main and 9.0 h ablation at full use of 4 workers, over the 12 h and 6 h budgets: options under Numbers, studies not started) |
| 5 | Report, notes, roadmap (`WP4: done`, `WP5: in progress: WP5b smoke done`); pushed; clean | `git push`; `git status --short` | PASS (this report, `docs/notes/WP5b.md`, ADR-0016, roadmap; pushed to `origin/main`; `git status --short` empty afterwards) |

## Changes
- `docs/spec/model.md` v1.8 (own commits d467a53 and 6af2ea0): §3 removed status, B, c_k,
  c_OT_k and O in the observation, approval days as decision epochs (§3.1 g); §4 SHIFT order,
  overtime pay and cap, DESCOPE and optional activities, the permission gate; §4.1 removed
  activities; §5 T̂, B from the observation, needs-gate sequencing; §6 the material rule, ties,
  filtering, scope loss, DESCOPE candidates, delayed application in rollouts, racing on both
  deadline components; §7.1 new metrics; §8 ε_T, ε_Δ, DESCOPE candidates, (N₁, N) = (25, 100)
  with the study result.
- Agent (`agent/`): `params.py` (autonomy Λ, τ_def, δ_h, ε_T, ε_Δ, DESCOPE; `ties`,
  `needs_approval`, `delay`; `COMPONENTS`; default (25, 100); B no longer a parameter);
  `candidates.py` (DESCOPE kind, `descopes`, `optional_values`, scope loss); `evaluate.py`
  (tardiness, `PairedErrors`, delayed application in rollouts, racing on both deadline
  components with `dominated`, `Evaluation` as a dataclass with the paired SEs); `decide.py`
  (component-wise material rule, runner-up, `eliminated`, `assess_needs` moved here, decision
  record with runner-up, gate, approval day, discarded action).
- `policies/sentinel.py`: permission gate (deferral, escalation, approval days through
  `requested_epoch`, re-validation, discard and fresh deliberation), DESCOPE candidates when
  nothing reaches θ_D, gate statistics; `policies/base.py`: `Descope` operation (level 2),
  `Decision.descopes`, the `requested_epoch` protocol note; `policies/urgency.py`: current
  graph with removals.
- Engine (`simulation/`): `state.py` (status `removed`, observation fields `budget`, `costs`,
  `overtime_costs`, `optional`; `EngineState.remove`, `cut_activity`, `successor_lists`;
  rebuilt states apply removals and take the observation's c_k); `engine.py` (DESCOPE in
  `Run.apply`, `Descoped` records, requested epochs, `Run.resume_to`, `Run.carry_on`,
  `Run.apply_valid`, B and O in `simulate`, D3 never after a removed activity);
  `realised.py` (removals in the realised graph and instance); `uncertainty.py`
  (`optional_activities`); `forecasting/beliefs.py`, `scheduling/residual.py`: removed
  activities skipped.
- Experiments: `policy_runs.py` (`SentinelVariant`, `optional_set`, `run_policy`,
  `scope_loss`, B and O passed to the engine, removed activities out of J⁺);
  `policy_config.py` (variants, shared `[sentinel]` table, `wp4b_results`, `joined`, further
  references, `start_estimate`); `policy_study.py` (Sentinel columns, per-variant deadlines,
  manifest records the variants and the join check); `policy_summary.py` (WP4b join and check,
  several references, Sentinel tables, `fig_wp5_tradeoff`, `fig_wp5_actions`, LaTeX table per
  reference); `cli.py` prints the join check.
- Configs: `configs/wp5_rq4_main.toml`, `configs/wp5_rq4_ablation.toml`;
  `docs/experiments/plan.md`: the RQ4 Sentinel study.
- Scripts: new `scripts/bench_rollout_budget.py`; `scripts/bench_sentinel.py` (variants with
  Λ = 3 and 2, deciding components, gate table).
- Tests (task 1 → test):
  - material rule, hand-made statistics: `test_sentinel.py::test_the_rule_ties_on_the_deadline_component_unless_significant_and_material`
    (significant but immaterial, material but within 2 SE, significant and material, capped),
    `::test_the_rule_ties_tardiness_budget_and_stability_by_their_thresholds` (T̂, o, Δ, ℓ,
    order; a hopeless epoch decided by T̂), `::test_the_rule_filters_against_the_best_of_the_current_set`
    (non-transitive ties, scope loss of DESCOPE, racing reason, scalarised),
    `::test_racing_drops_only_candidates_worse_in_both_deadline_components`;
  - hopeless epoch on a constructed case: `test_gate_descope.py::test_a_hopeless_epoch_chooses_the_lowest_tardiness`;
  - Λ = 3 / Λ = 0: `::test_full_autonomy_escalates_nothing_and_zero_autonomy_gates_every_action`
    (escalation, approval, deferral, approval days as epochs), `::test_the_gate_exempts_noop_and_always_stops_descope`;
  - invalid escalated RESEQ: `::test_an_escalated_reseq_that_became_invalid_is_discarded_and_redeliberated`;
  - approval delay in rollouts: `::test_rollouts_imagine_the_approval_delay` (SUBST approved a
    day later: p̂ 1.0 → NOOP's, T̂ 0 → between);
  - DESCOPE: `::test_descope_removes_only_unstarted_optional_activities` (rejections, orphan
    linked to the sink, realised schedule valid and acyclic, rebuilt graph and planning view),
    `::test_sentinel_descopes_only_when_no_candidate_reaches_theta`,
    `::test_optional_activities_are_drawn_among_the_sink_predecessors`;
  - observation fields: `::test_observations_carry_the_budget_and_the_costs`;
  - runner: `test_policy_study.py::test_the_wp5_configs_follow_the_study_plan`,
    `::test_runner_with_a_sentinel_variant_joins_the_baselines_of_an_earlier_run`;
  - NoReaction regression: `test_engine_regression.py::test_fifty_runs_are_unchanged` with the
    fixture unchanged (digests without the three v1.8 observation fields);
  - updated: the racing test asserts reason and runner-up; `test_sentinel_data.py` counts
    approval days among the epochs.
- Docs: ADR-0016, `docs/notes/WP5b.md`, this report, roadmap (WP4 done, WP5 in progress).

## Decisions
- **Ties against the best of the current set.** The rule filters component by component: the
  best of the current set (largest capped estimate, smallest T, o, Delta, level; ties by
  candidate order) and every candidate tied with it stay. Ties in a stochastic component use
  `difference <= 2 SE or difference < epsilon` (identical candidates tie); Delta ties when
  `difference < eps_Delta`, scope and level only when equal. The tie test lives in
  `SentinelParams.ties`, shared by racing and the rule.
- **Paired standard errors.** Per pair of candidates and component, from the per-rollout
  differences on their N common rollouts: on-time indicators, tardiness max(0, C - D) (a
  truncated rollout counts C = max_days), and total cost / B for o (the delta-method SE of
  o_a - o_b, exact where both are over budget). `PairedErrors` computes them lazily.
- **Racing leader.** The stage-1 leader is the candidate with the largest capped estimate, then
  the smallest T, then the first; a candidate is dropped iff it is not tied with the leader in
  min(p, theta_D) and not tied with it in T (both on the N_1 rollouts).
- **Deciding component and runner-up.** The component that removed the last competitor decides;
  that competitor (the best of those removed there) is the runner-up. If every other candidate
  was dropped in stage 1 the reason is `racing` and the best dropped candidate is the runner-up;
  equal candidates after all components: `order`. Each candidate record says where it left the
  best set.
- **Gate in the world** (ADR-0016). Sentinel keeps the escalated action, sets
  `requested_epoch`, which the engine turns into a decision epoch; on that day it re-validates
  with `rehearse` (all or nothing) and applies it, or discards it and deliberates afresh.
  While an approval is pending (none with delta_h = 1) it returns NOOP without deliberating.
  NOOP never needs approval, also with Lambda = 0. tau_t is min_j tau_j over the unstarted,
  paused and running activities (`policies/urgency.py`).
- **Gate in rollouts** (ADR-0016). `Run.resume_to(t + delta_h)` stops at step 3 of the
  approval day, `Run.apply_valid` tries the candidate on a state copy with every plan checked
  and applies it only if nothing is rejected, `Run.carry_on` continues; a project that ends
  before the approval day never sees the action.
- **DESCOPE in the engine.** Removed activities get the status `removed`; `cut_activity`
  removes their edges and links predecessors left without successors to the sink (needed for
  the validity of section 1). The observation carries O (`optional`); the rebuilt state,
  planning view, urgency, beliefs, nominal world and realised schedules apply the removals;
  D3 never picks a removed activity as predecessor. The realised deviation leaves removed
  activities out of J+ (they left the project).
- **Optional activities.** `optional_activities(instance, phi, seed)` draws round(phi n_real)
  of the real activities whose only successor is the sink (at most all), with
  derive_seed(base_seed, "optional", "set/instance"); DESCOPE candidates need the sink as the
  current only successor, so an optional activity that gained a D3 successor cannot be removed.
- **Observation fields.** `budget` (B: the instance's, else section 1.2 with beta = 0.1 and the
  run's c_k, or the study's B passed by the runner), `costs` (c_k) and `overtime_costs`
  (1.5 c_k) are always set by the engine and serialised; `optional` only when non-empty.
  Sentinel reads B from the observation and refuses an observation without it.
- **Engine regression.** The fixture is unchanged; its observation digests leave out the three
  fields added in v1.8 (`V18_FIELDS`), so every field of the WP2b-WP5a observations is still
  checked bit for bit.
- **Runner** (`policy_study`): Sentinel variants are named config tables merged over a shared
  `[sentinel]` table, with `delta_d` and `optional_share`; results gain Sentinel columns (zero
  for other policies). The summaries read the `joined` baselines from `wp4b_results` on the
  run's worlds after checking seeds (every row read) and NoReaction makespans against the run's
  own NoReaction rows; paired differences are taken against every reference policy with runs.
  `start_estimate = false` skips the up-front probe (minutes for Sentinel).
- **Figures** (dataviz method; emphasis form). `fig_wp5_tradeoff`: pooled points per policy, the
  Sentinel variants in categorical slots 1-3 with their own marker shapes, direct-labelled where
  no other variant point is close, the baselines in grey with one marker shape each; more than
  three variants (ablation) are split into groups of three, each with its own legend. The
  δ_D = 0.3 variant appears on the δ_D = 0.2 axis (post hoc for it); the tables give both. `fig_wp5_actions`: stacked columns of the action groups (SHIFT, RESEQ,
  SUBST, OVERTIME, DESCOPE; fixed slots 1-5, only those present) in % of deliberations per
  lambda_A, the total on the cap. The palette is the reference palette in its fixed order, whose
  documented validation covers these uses; the validator could not run (no node), the summary
  tables are the table view.
- ADRs created: ADR-0016 (permission gate in the world and in rollouts).

## Deviations
- **Budgets exceeded.** As configured, the main study needs about 14.4 h and the ablation 9.0 h
  on 4 workers (budgets 12 h and 6 h). Following the prompt, options are reported under Numbers
  and the studies are not started; the configs stay as specified.
- **Long runs in the session.** The measurements the prompt asks for ran in the background of
  the session: the budget study took 9.9 min, the re-measurement 18.4 min (estimated 12), the
  smoke runs 10.6 and 3.6 min, and the spread samples 17.6 and 10.3 min. Two runs exceeded the
  ~10-minute guidance of CLAUDE.md.
- **Spread sample size.** Five instances per set (J30 and J60 every 96th, subsets of the study
  instances), replication 0, every scenario, instead of WP4b's ten per set. This kept the main
  sample under 18 min. Its λ_A = 0.01 means agree with the 40- and 20-run re-measurement within
  5 %.
- **Re-measurement variants.** Λ = 3 and Λ = 2 as asked. `sentinel_no_ot` was not re-measured,
  but the spread sample timed it.
- **Spec text beyond the dictated words:**
  - the racing leader (largest capped estimate, then smallest T̂, then order);
  - the paired standard errors (on-time indicators, tardiness, cost / B);
  - approval validity as "none of its operations would be rejected";
  - predecessors left without successors after a DESCOPE precede `n+1`;
  - the removed status, O in the observation, removed activities in §4.1 and the §7.1 metric
    list;
  - the WP5a answers entered as text (SHIFT order, overtime pay and cap, needs-gate
    sequencing);
  - the §8 paragraph on the budget study.
- **Engine regression.** The fixture is unchanged. The test's observation digests now leave out
  the three fields added in v1.8, so every older field is still checked.
- **Beyond the listed files:** the engine layer (`state`, `engine`, `realised`, `uncertainty`),
  `residual`, `urgency`, `beliefs`, `policy_runs`, `policy_config`, `policy_summary`, `cli`,
  `test_engine_regression.py` and `test_sentinel_data.py` (approval days among the epochs).
- **No start probe.** The WP5 configs set `start_estimate = false`: a Sentinel probe would take
  minutes, and the progress lines give a running estimate.

## Spec questions
1. **Approved RESEQ and SHIFT plans can be stale** (§4 permission gate, §6 evaluation;
   `Sentinel.decide`, `Run.apply_valid`). A plan made on day t lists the activities that start
   on day t and may start others on day t. On day t + δ_h those are no longer residual
   activities, or start before the release, so the engine rejects the plan and with it the
   whole approved action. Measured:
   - at Λ = 2, 3 of 13 (J30) and 0 of 9 (J60) escalations were discarded;
   - at Λ ≤ 1 about 40 % were (ablation smoke run: Λ = 0 0.31 of 0.81, Λ = 1 0.25 of 0.62 per
     run).

   The rollouts imagine the same, so plan candidates win less often under a low Λ; at Λ = 0
   SHIFT was never chosen in that run. Options: re-plan the RESEQ part on the approval day with
   the same objective; re-time the approved plan along its order (SHIFT); keep the literal
   reading (used).
2. **Share φ of optional activities** (§4; `optional_activities`, `# SPEC-Q`). Every J30 and J60
   instance has exactly three activities whose only successor is the sink, so "a share φ = 0.1
   of those" gives round(0.3) = 0 optional activities. Reading used: round(φ n_real) of them, at
   most all, i.e. all three in every PSPLIB instance (round(3) on J30, round(6) capped on J60).
   The fixed-seed draw then matters only on other instances.
3. **Racing reference** (§6). "Significantly and materially worse in min(p̂, θ_D) and in T̂" is
   read against one stage leader (largest capped estimate, then smallest T̂, then order), not
   against each component's own best; written into the spec text.
4. **Paired SE of o** (§6). Taken as the SE of the paired cost differences divided by B: exact
   where both candidates are over budget, conservative where o is clipped at 0.
5. **Approval validity** (§4). "Applied if valid" is read as all or nothing: valid iff the
   engine would reject none of the operations. A partly valid action (e.g. the hire of
   OT+RESEQ-M with a stale plan) is discarded; written into the spec text.
6. **Removed activities and J⁺** (§7.1). Activities removed by DESCOPE are left out of the
   realised deviation, since they never start.
7. **Repeated DESCOPE deferrals** (§4, §6). In the ablation smoke run (2 J30 instances,
   λ_A ∈ {0.01, 0.02}, Λ = 2, φ = 0.1), DESCOPE was the choice in 37 % of deliberations. While
   the urgency exceeded τ_def it was deferred, 8.6 times per run, before 1.75 escalations per run
   applied it: scope loss 0.44, on time +25 pp over NoReaction. Is the repeated proposal and
   deferral of the same action intended? Alternatives: remember deferred actions, or give
   DESCOPE its own threshold.

## Numbers
Environment: Intel i5-6600K (4 cores), WSL2 (Linux 6.18), uv 0.13.2, CPython 3.12.15, numpy
2.5.4, ortools 9.15.6755, pydantic 2.14.1. Primary scenario at λ_A = 0.01 (E[L] = 3,
λ_S = 0.01, λ_N = 0.02, T_r = 5), `cpsat_det` baseline plans, WP2b seeds, D = ⌈1.2 C*⌉ for
Sentinel, T_cp = 0.1; runs in a spawn pool of 4 workers, timed inside the workers.

**Rollout budget** (`scripts/bench_rollout_budget.py --runs j30:10 --runs j60:5`, task 3;
Sentinel `full`, Λ = 3; the world follows the (50, 200) choice). At every deliberation NOOP and
all rule candidates ran on the same 800 sampled worlds; each budget's choice is the one a fresh
Sentinel with that budget makes on the first N of them (needs gate, racing, rule), the
reference is the rule on all candidates with N = 800 and no racing. Losses are those of the
budget's choice in the reference statistics: p = p̂_ref(reference choice) − p̂_ref(choice),
T = T̂_ref(choice) − T̂_ref(reference choice).

| Set | (N₁, N) | Deliberations | Agreement % | Mean p loss | Mean T loss [d] | p loss > 0 % | T loss > 0.5 d % | Max T loss [d] | Rollouts / deliberation |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| J30 | (25, 100) | 417 | 92.3 | 0.0010 | 0.022 | 5.3 | 2.4 | 1.95 | 442 |
| J30 | (50, 200) | 417 | 93.3 | 0.0006 | 0.013 | 3.8 | 1.7 | 1.12 | 875 |
| J60 | (25, 100) | 305 | 87.5 | 0.0019 | 0.025 | 7.5 | 3.0 | 2.11 | 489 |
| J60 | (50, 200) | 305 | 90.8 | 0.0011 | 0.024 | 4.9 | 3.0 | 1.96 | 956 |
| All | **(25, 100)** | 722 | 90.3 | **0.0014** | **0.023** | 6.2 | 2.6 | 2.11 | 462 |
| All | (50, 200) | 722 | 92.2 | 0.0008 | 0.018 | 4.3 | 2.2 | 1.96 | 909 |

- 661 of the 722 deliberations generated candidates (5.04 per deliberation with NOOP); the
  others met every needs gate.
- Decision: (25, 100) is within both limits (T loss 0.023 ≤ 0.25 d, p loss 0.0014 ≤ 0.01) and
  is adopted (spec commit 6af2ea0). 15 runs, 594 s wall on 4 workers (2,214 s of run time).

**Timing** with the adopted budget (`scripts/bench_sentinel.py --runs j30:20:2 --runs
j60:10:2`, task 4; J30 every 24th, J60 every 48th instance, WP2b seeds of replications 0-1):

| Set | Variant | Runs | Deliberation mean s | p95 s | max s | Deliberations / run | Gate exits / run | Skipped epochs / run | Candidates / deliberation | Rollouts / deliberation | CP-SAT s / deliberation | s / run | p95 s / run |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| J30 | Sentinel Λ = 3 | 40 | **0.395** | 1.145 | 2.391 | 42.6 | 1.3 | 21.9 | 4.64 | 446 | 0.099 | 16.9 | 37.8 |
| J30 | Sentinel Λ = 2 | 40 | 0.425 | 1.142 | 2.402 | 43.0 | 1.2 | 22.2 | 4.76 | 460 | 0.097 | 18.4 | 39.4 |
| J60 | Sentinel Λ = 3 | 20 | **0.743** | 2.401 | 3.326 | 64.6 | 2.8 | 32.8 | 5.24 | 501 | 0.272 | 48.3 | 122.8 |
| J60 | Sentinel Λ = 2 | 20 | 0.783 | 2.463 | 3.467 | 65.2 | 2.5 | 32.2 | 5.29 | 508 | 0.271 | 51.3 | 122.0 |

- WP5a (N₁ = 50, N = 200, one seed): 0.595 s and 25.1 s per run on J30, 1.089 s and 71.4 s on
  J60, with 804 and 921 rollouts per deliberation. The rollouts halved; the deliberation time
  fell by a third (generation and CP-SAT do not shrink).

**Deciding component** (% of deliberations; WP5a: old rule, (50, 200), full autonomy; WP5b:
material rule, (25, 100), Λ = 3; "racing": every other candidate dropped in stage 1):

| Set | Rule | Deliberations | Needs met | Only candidate | Racing | On time | Tardiness | Budget | Stability | Level | Order |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| J30 | WP5a | 837 | 1.6 | 8.4 | — | 4.1 | — | **74.3** | 11.6 | 0.1 | 0.0 |
| J30 | WP5b | 1,703 | 3.1 | 5.9 | 0.1 | 1.9 | 3.6 | **1.9** | 71.6 | 3.5 | 8.2 |
| J60 | WP5a | 651 | 4.8 | 4.8 | — | 2.2 | — | **61.4** | 26.3 | 0.6 | 0.0 |
| J60 | WP5b | 1,292 | 4.3 | 4.7 | 0.1 | 0.5 | 3.4 | **0.9** | 73.6 | 6.3 | 6.2 |

- With material ties, NOOP (Δ = 0, ℓ = 0) wins whenever no candidate is materially and
  significantly better in min(p̂, θ_D), T̂ or o: stability, level and order then pick it. The
  budget decides only on differences of at least 1 % of B; T̂ decides 3–4 % of deliberations.

**Chosen candidates** (% of deliberations, before the gate):

| Set | Variant | Deliberations | Needs met | NOOP | SHIFT | RESEQ-M | RESEQ-S | SUBST(j) | SUBST-ALL | SUBST-ALL+RESEQ-M | OT+RESEQ-M |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| J30 | Λ = 3 | 1,703 | 3.1 | 87.4 | 2.2 | 3.0 | 1.1 | 0.4 | 0.0 | 0.0 | 2.8 |
| J30 | Λ = 2 | 1,721 | 2.8 | 88.4 | 2.8 | 3.0 | 1.0 | 0.0 | 0.0 | 0.1 | 1.9 |
| J60 | Λ = 3 | 1,292 | 4.3 | 85.7 | 3.4 | 2.7 | 1.3 | 0.8 | 0.0 | 0.2 | 1.7 |
| J60 | Λ = 2 | 1,303 | 3.8 | 85.9 | 4.4 | 3.2 | 1.5 | 0.5 | 0.0 | 0.1 | 0.6 |

(WP5a, full: NOOP 63.7 / 63.9 %, SHIFT 16.8 / 12.3 %, RESEQ-M 11.1 / 10.6 %.)

**Permission gate** at Λ = 2 (per run; counts in brackets):

| Set | Runs | Actions chosen | Deferrals | Escalations | Approvals applied | Approvals discarded |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| J30 | 40 | 3.80 | 0.53 (21) | 0.33 (13) | 0.25 (10) | 0.07 (3) |
| J60 | 20 | 6.75 | 0.35 (7) | 0.45 (9) | 0.45 (9) | 0 |

- Every level-2 choice (OT+RESEQ-M, SUBST-ALL+RESEQ-M, SUBST(j)) was deferred or escalated;
  level 0-1 choices applied at once.

**First look** (not a study; means per run; on time δ_D = 0.3 post hoc):

| Set | Policy | Runs | On time δ=0.2 | On time δ=0.3 | C / C* | Deviation d | Nervousness | Cost / B | Overtime share | Substituted | Hired | RESEQs | SHIFTs | s / run |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| J30 | NoReaction | 40 | 0.250 | 0.450 | 1.362 | 7.38 | 0 | 1.039 | 0 | 0 | 0 | 0 | 0 | 0.01 |
| J30 | FullResolve | 40 | 0.250 | 0.550 | 1.328 | 7.60 | 208.1 | 1.038 | 0 | 0 | 0 | 61.7 | 0 | 1.83 |
| J30 | Sentinel Λ = 3 | 40 | 0.300 | 0.625 | **1.297** | 6.90 | 49.4 | 1.054 | 0.0219 | 0.2 | 3.7 | 2.9 | 0.9 | 16.95 |
| J30 | Sentinel Λ = 2 | 40 | 0.250 | 0.550 | 1.317 | 7.17 | 43.0 | 1.041 | 0.0043 | 0.0 | 0.7 | 2.0 | 1.2 | 18.41 |
| J60 | NoReaction | 20 | 0.250 | 0.400 | 1.402 | 9.91 | 0 | 1.029 | 0 | 0 | 0 | 0 | 0 | 0.01 |
| J60 | FullResolve | 20 | 0.300 | 0.450 | 1.375 | 11.59 | 750.5 | 1.028 | 0 | 0 | 0 | 94.7 | 0 | 7.76 |
| J60 | Sentinel Λ = 3 | 20 | 0.300 | 0.450 | **1.347** | 10.36 | 146.6 | 1.038 | 0.0130 | 0.8 | 4.0 | 3.8 | 2.2 | 48.31 |
| J60 | Sentinel Λ = 2 | 20 | 0.250 | 0.400 | 1.354 | 10.46 | 147.6 | 1.031 | 0.0024 | 0.2 | 0.8 | 3.4 | 2.9 | 51.32 |

- 240 runs, 1,107 s wall on 4 workers (3,636 s of run time); 0 rejected operations, 0 CP-SAT
  fallbacks, 0 truncated runs, 60 NoReaction runs with 0 WP2b seed or makespan mismatches.
- One run is 2.5 pp (J30) or 5 pp (J60) of on-time share.
- Sentinel (Λ = 3) has the lowest C / C* on both sets, with a quarter (J30) and a fifth (J60) of
  FullResolve's plan changes and 2.9 / 3.8 RESEQs per run against 62 / 95; WP5a's Sentinel
  changed 148 / 385 planned starts per run for C / C* 1.343 / 1.315 (the same instances, replication 0 only).
- The gate (Λ = 2) costs 0.02 / 0.007 of C / C*, mostly through fewer hires (0.7 / 0.8 against
  3.7 / 4.0 per run).

**Smoke runs** (task 6; gitignored, quoted here):

| Config | Run | Runs | Wall | Outputs | WP2b check | WP4b join | Rejected / fallbacks / truncated |
| --- | --- | ---: | ---: | --- | --- | --- | --- |
| `wp5_rq4_main.toml --limit 2` | 20261022-072315-230e5e63-smoke | 256 (J30 j301_1, j301_5; J60 j601_1, j601_9; 4 λ_A; R = 4; NoReaction + 3 variants) | 10.6 min | results.csv.gz, summary.md, table_wp5_main.tex, table_wp5_main_vs_full_resolve.tex, fig_wp5_tradeoff, fig_wp5_actions (PDF, PNG), manifests | 64 worlds, 0 mismatches | 256 rows of the 4 joined baselines, 0 seed / makespan mismatches, 0 missing | 0 / 0 / 0 |
| `wp5_rq4_ablation.toml --limit 2` | 20261022-073407-3bff2218-smoke | 96 (J30 j301_1, j301_5; 2 λ_A; R = 4; NoReaction + 5 variants) | 3.6 min | the same with `table_wp5_ablation*`, `fig_wp5_ablation_*` | 16 worlds, 0 mismatches | 64 rows, 0 mismatches, 0 missing | 0 / 0 / 0 |

- The first two instances of each set are cheap: 4.4 s (J30) and 15.7 s (J60) per Sentinel `full`
  run, against 17.8 and 48.4 s on the spread sample at λ_A = 0.01. So the estimates come from
  the spread sample, as in WP4b.

**Duration estimates** (task 6), from spread samples run through the runner with temporary
configs: J30 and J60 every 96th instance (`j301_1`, `j3010_7`, `j3020_3`, `j3029_9`, `j3039_5`
and the same J60 numbers), replication 0, every scenario. The main sample had 160 runs, 1,055 s
wall, pool busy 0.80; the ablation sample 60 runs, 620 s, busy 0.54 (10 tasks on 4 workers).
Both had 0 WP2b and 0 join mismatches and 0 rejected operations.

| Set | Variant | s / run @ λ_A = 0 | 0.005 | 0.01 | 0.02 | CPU h (study) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| J30 | Sentinel | 4.03 | 10.85 | 17.77 | 30.37 | 8.4 |
| J30 | Sentinel no OT | 3.69 | 10.38 | 17.03 | 30.22 | 8.2 |
| J30 | Sentinel Λ = 2 | 4.27 | 11.66 | 18.94 | 32.90 | 9.0 |
| J60 | Sentinel | 9.12 | 25.70 | 48.41 | 77.31 | 10.7 |
| J60 | Sentinel no OT | 8.82 | 25.12 | 47.41 | 74.95 | 10.4 |
| J60 | Sentinel Λ = 2 | 9.05 | 27.02 | 50.51 | 76.63 | 10.9 |
| J30 | scalarised (ablation) | | | 20.25 | 34.08 | 7.2 |
| J30 | Λ = 0 | | | 23.32 | 37.39 | 8.1 |
| J30 | Λ = 1 | | | 21.81 | 34.58 | 7.5 |
| J30 | DESCOPE (Λ = 2, φ = 0.1) | | | 19.62 | 33.05 | 7.0 |
| J30 | δ_D = 0.3 | | | 16.57 | 28.32 | 6.0 |

- CPU h = per-run means × 120 J30 or 60 J60 instances × R = 4 per λ_A; NoReaction is about
  0.01 s per run.
- The λ_A = 0.01 means of the main sample are within 5 % of the re-measurement (16.9 / 18.4 s
  J30, 48.3 / 51.3 s J60 for Λ = 3 / 2). Scaling the sample to it changes the main total by −2 %.

| Study (budget) | Option | CPU h | Wall h at full use of 4 workers | Wall h at the sample's 0.80 busy share |
| --- | --- | ---: | ---: | ---: |
| Main (12 h) | **as configured** | 57.6 | **14.4** | 18.0 |
| Main | without `sentinel_gate` | 37.7 | 9.4 | 11.8 |
| Main | J60 every 16th (30 instances) | 41.6 | 10.4 | 13.0 |
| Main | R = 3 | 43.2 | 10.8 | 13.5 |
| Main | without λ_A = 0.02 | 29.9 | 7.5 | 9.3 |
| Ablation (6 h) | **as configured** | 35.9 | **9.0** | 11.2 |
| Ablation | J30 every 8th (60 instances) | 17.9 | 4.5 | 5.6 |
| Ablation | R = 2 | 17.9 | 4.5 | 5.6 |
| Ablation | λ_A = 0.02 only | 22.3 | 5.6 | 7.0 |
| Ablation | without Λ = 1 and scalarised | 21.1 | 5.3 | 6.6 |

- Moving `sentinel_gate` from the main study to the ablation (J30, λ_A ∈ {0.01, 0.02}) adds
  6.9 CPU h there. The studies have 720 (main) and 240 (ablation) tasks, so their idle tail is
  shorter than the samples'; the wall time lies between the two columns, closer to full use.
- WP4b's five baselines took 14.6 CPU h. Halving the rollouts cut a deliberation by a third
  (0.595 → 0.395 s on J30), since candidate generation and CP-SAT do not shrink. Further savings
  would need a smaller budget, which the rollout-budget study did not test.

| Measurement | Value |
| --- | --- |
| Tests | default `pytest -q`: 312 passed, 2 deselected in 89.0 s (297 and 87.5 s in WP5a; the new runner test runs its tasks in-process to stay within 90 s); `-m "data or slow"`: 17 passed, 297 deselected in 285.3 s (328.2 s in WP5a; the Sentinel data test, now with the gate at Λ = 2 and (25, 100), 107 s against 151 s) |
| Measured runs | 240 re-measurement runs, 352 smoke and 220 sample runs: all checked in debug mode, 0 rejected operations, 0 CP-SAT fallbacks, 0 truncated runs, 0 WP2b mismatches (60 + 80 + 50 NoReaction worlds); the 15 budget-probe runs (722 deliberations, each on 800 worlds) passed the same feasibility checks (rejections not counted there) |
| Engine regression | 50 runs unchanged (fixture unchanged; digests without the v1.8 observation fields) |

## Commands for the owner
```bash
cd ~/projects/sentinel && git pull && uv sync --locked
uv run pytest -q                    # expect 312 passed, 2 deselected, ~89 s
uv run pytest -q -m "data or slow"  # expect 17 passed, 297 deselected, ~5 min
# The RQ4 Sentinel studies exceed their budgets as configured: run them only after the
# architect picks an option (Numbers). Measured: main ~58 CPU h, 14.4 h on 4 workers (up to
# ~18 h with idle workers); ablation ~36 CPU h, 9.0 h (up to ~11 h). In tmux:
uv run python -m sentinel.experiments.policy_study --config configs/wp5_rq4_main.toml --out results/wp5
uv run python -m sentinel.experiments.policy_study --config configs/wp5_rq4_ablation.toml --out results/wp5
# Measurements of this report (about 10 and 18 min on 4 workers):
uv run python scripts/bench_rollout_budget.py --runs j30:10 --runs j60:5
uv run python scripts/bench_sentinel.py --runs j30:20:2 --runs j60:10:2 --policies no_reaction full_resolve sentinel_full sentinel_gate
```

## Open issues / next steps
- **Architect: study size.** Pick the options that fit the budgets (Numbers), e.g. main without
  `sentinel_gate`, with the gate on J30 at λ_A ∈ {0.01, 0.02} in the ablation, and the ablation
  on J30 every 8th or with R = 2. Or allow the longer runs (main 14.4 h, ablation 9.0 h).
- **Architect: spec questions 1–7**, above all stale approved plans (1) and the share φ (2).
- **WP6:** LLM proposals become `Candidate`s that pass `rehearse`. Explanations can read the
  deciding component, the runner-up and each candidate's `eliminated` entry in the
  `DecisionRecord`.
- **WP7:** run the studies, then finalise the paper figures (`fig_wp5_tradeoff` pools over λ_A;
  per-λ_A trade-offs are in the tables).
