# WP5b.1 report — re-plan on approval, spec answers, study sizes

- Date: 2026-10-22
- Commit(s): 564415c (spec v1.8.1), 8c62509 (re-plan on approval, O without φ, tests), dafa16d
  (test speed), 3ff2f31 (study sizes); the report, notes, ADR and roadmap commit follows them

## Summary
Spec v1.8.1 holds the answers to the WP5b questions. An escalated action is now approved as an
intent: on its approval day its SUBST, OVERTIME and DESCOPE operations are re-validated and its
plan part is planned again with its candidate's objective. Sentinel and the rollouts do this
with the same code that builds candidates, and every escalation in the smoke runs was applied.
`O` is the three real activities before the sink alone. Λ = 3 runs are bit-identical to before
(identity test; 96 main-smoke runs equal to WP5b's in every non-timing column), and the default
test run takes 65.5 s. Both configs have the binding sizes and their smoke runs pass. The main
study needs about 9.4–11.8 h. Re-planning inside rollouts makes a gated run 1.3–3 times as
costly at Λ = 2 and 2–12 times at Λ ≤ 1, so the ablation as configured needs about 19–24 h on
4 workers, three to four times its 6 h budget; options are under Numbers.

## Acceptance criteria
| # | Criterion | Command | Result |
| --- | --- | --- | --- |
| 1 | Spec v1.8.1 commit; test-speed chore separate | `git show --stat 564415c dafa16d` | PASS (`spec: re-plan on approval, optional activities (v1.8.1)` touches only `docs/spec/model.md`; `chore: keep the default test run within 75 s` only test markers, `pyproject.toml` and `README.md`) |
| 2 | Quality gate (default `pytest -q` ≤ 75 s) and `-m "data or slow"` pass; task-1 tests and the Λ = 3 identity test exist and pass | `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy src`; `uv run pytest -q`; `uv run pytest -q -m "data or slow"` | PASS (ruff clean; formatted; mypy: no issues in 56 source files; `pytest -q`: 314 passed, 7 deselected in 65.5 s, 91.7 s before the chore; `-m "data or slow"`: 19 passed, 302 deselected in 506.3 s, with two timing workers running alongside; tests under Changes) |
| 3 | Configs and plan updated; smoke runs complete; estimates and the single command line given | `python -m sentinel.experiments.policy_study --config configs/wp5_rq4_main.toml --out results/wp5 --limit 1`, the same for `wp5_rq4_ablation.toml`; timing runs on identical worlds | PASS, with the ablation budget exceeded (both smoke runs complete with every output, 0 WP2b and 0 join mismatches, 0 rejected operations, fallbacks or truncated runs; estimates extrapolated from WP5b's spread sample with ratios measured on identical runs, as the prompt allows; main 9.4–11.8 h, ablation 18.9–23.6 h against 6 h; command under Commands) |
| 4 | Report, roadmap; pushed; clean tree | `git push`; `git status --short` | PASS (this report, `docs/notes/WP5b.1.md`, ADR-0017, roadmap `WP5: in progress: WP5b.1 done, studies pending`; pushed to `origin/main`; `git status --short` empty afterwards) |

## Changes
- `docs/spec/model.md` v1.8.1 (own commit): §4 permission gate (approval of the intent:
  re-validation, re-plan with the candidate's objective, all or nothing; deferred actions are
  not remembered), optional activities without `φ`; §6 rollouts approve exactly as the world,
  paired SE of `o`; §7.1 removed activities out of `J⁺`; §8 `φ` removed; version line.
- Agent: `candidates.py` (`PLAN_PARTS`, `plan_part`, `prepare`, `approve`, `PlanCache`;
  `generate` builds every candidate with `prepare`); `evaluate.py` (`Evaluator.play` approves
  gated candidates on the approval day of each rollout, per-epoch plan cache, re-plan counts;
  `rollout` uses `play`); `decide.py` (docstring of the approval record).
- Policy: `policies/sentinel.py` (`Pending` holds the candidate; the approval day re-plans with
  `approve`, counts its CP-SAT effort; `SentinelStats.replan_solves`, `replans_reused`).
- Engine: `simulation/engine.py` (`plan_rejection(view, op)` factored out of the plan check;
  `Run.apply_valid` removed); `simulation/uncertainty.py` (`optional_activities(instance)`).
- Experiments: `policy_runs.py` (`SentinelVariant` without `optional_share`, `optional_set` by
  variant, `PolicyTask.base_seed` removed); `policy_config.py` (variant keys); `policy_study.py`
  (O by variant, manifest `optional_rule`); `policy_summary.py` (no φ in the variant lines).
- Configs: `wp5_rq4_main.toml` (`sentinel_full`, `sentinel_no_ot`), `wp5_rq4_ablation.toml`
  (J30 every 8th; `sentinel_gate` added; no `optional_share`); `docs/experiments/plan.md`.
- Tests (task 1 → test):
  - stale RESEQ-M re-planned and applied:
    `test_gate_descope.py::test_an_approved_reseq_with_a_stale_plan_is_replanned_and_applied`;
  - SUBST with a substitute who fell ill discarded and re-deliberated:
    `::test_an_approved_subst_whose_worker_became_absent_is_discarded_and_redeliberated`;
  - rollout and world agree (same approved RESEQ, starts, finishes, cost; plan part reused):
    `::test_a_rollout_imagines_the_approval_the_world_applies`;
  - OT + RESEQ-M re-planned with the temporary worker:
    `::test_an_approved_overtime_replans_with_the_temporary_workers`;
  - approval on the epoch day gives back every kind of candidate:
    `::test_approval_on_the_epoch_day_rebuilds_every_candidate`;
  - `O`: `::test_optional_activities_are_the_real_activities_before_the_sink_alone` (tiny.sm-like
    instance: three; tiny.sm: two) and `::test_every_j30_and_j60_instance_has_three_optional_activities`
    (data, all 960 instances);
  - Λ = 3 identity: `test_sentinel_identity.py` with `tests/fixtures/sentinel_identity.json`,
    written with commit fee0ce1 before any change: three seeds on a synthetic instance (default
    run) and three WP2b seeds of j301_1 at λ_A = 0.02 with (25, 100) (data, slow);
  - updated: `test_policy_study.py::test_the_wp5_configs_follow_the_study_plan`; removed the
    v1.8 tests of a discarded stale RESEQ and of the φ draw.
- Test speed (own commit): four data tests marked `slow`; marker text in `pyproject.toml` and
  `README.md`. `.pre-commit-config.yaml`: the digest fixture joins the detect-secrets exclusion.
- Docs: ADR-0017; ADR-0016 status; `docs/notes/WP5b.1.md`; this report; roadmap.

## Decisions
- **One builder for actions** (ADR-0017). `prepare(observation, kind, operations)` rehearses
  the operations through the engine and plans the kind's plan part on the view they leave,
  checked there by `plan_rejection`, the engine's own check. Generation and `approve` use it,
  so approving a candidate on its own epoch reproduces it (tested on every kind).
- **World and rollouts share `approve`.** Sentinel calls it on the approval day's observation; a
  rollout calls it on the observation of its state at step 3 of the approval day and applies the
  result unchecked (it was checked on that observation, as candidates are). `Run.apply_valid`
  is gone.
- **Exact plan cache.** Within an epoch, rollouts share plan parts keyed by the objective and
  every field of the planning view. CP-SAT (one worker, seed, deterministic limit) and the SGS
  are functions of the view, so results equal those without the cache (the agreement test
  checks a reused part). 45–74 % of the parts were reused at Λ = 0.
- **What is re-validated.** SUBST, OVERTIME and DESCOPE operations unchanged; the OVERTIME
  window starts on the approval day, when the hire happens. A CP-SAT stage without a solution
  falls back as in generation and is no failure.
- **Records and counts.** The approval record carries the re-planned decision and its CP-SAT
  effort; approval searches count in `reseqs` and `fallbacks`; rollout re-plans in the new
  `SentinelStats` fields (not in `results.csv`, whose columns are unchanged).
- **O.** `optional_activities(instance)`; only DESCOPE variants get O, so the observations of
  every other run are unchanged. A config key `optional_share` now fails validation.
- **Identity fixture.** Digests of the result, of the decision records without wall times
  and of the counts, by explicit field lists, so later added fields do not break it.
- **Test speed.** The four slowest default tests were data tests that the acceptance run runs
  anyway; marking them `slow` loses no acceptance coverage.
- **Configs.** The Λ = 2 variant keeps its name `sentinel_gate` (labels, scripts, WP5b numbers).
- ADRs created: ADR-0017 (approved actions re-planned by the code that builds candidates);
  ADR-0016's status notes the superseded re-validation.

## Deviations
- **Timing runs over the 10-minute guidance.** The new-code timing batch (16 runs) took
  24.4 min instead of the ~7 min predicted from cheaper instances: j3029_9 at λ_A = 0.02 took
  23–24 min per run at Λ ≤ 1. Its results arrive only at the end of the batch, so it was left
  to finish. The acceptance run overlapped its last 8 min (six processes on four cores), which
  inflates those two wall times by at most about 3 min. The smoke runs took 4.3 and 7.5 min.
- **Estimates extrapolated, not a new spread sample.** The WP5b spread sample with the gated
  variants would take over an hour now. Following the prompt, the estimates scale WP5b's spread
  means by new/old ratios measured on identical runs (Numbers).
- **Spec text beyond the dictated words:** DESCOPE is re-validated with SUBST and OVERTIME
  (answer 1 names those two; DESCOPE has no plan part); "the re-plan fails" is defined as the
  engine rejecting the new plan; "three in every J30 and J60 instance" (checked on all 960);
  the wording of answers 3–7.
- **Beyond the listed files:** engine, evaluator, `decide.py`, the policy-study modules,
  `pyproject.toml`, `README.md`, `.pre-commit-config.yaml` and the test modules named above.

## Spec questions
1. **The cost of imagining the re-plan exactly** (§6; ADR-0017). Rollouts of gated candidates
   now run CP-SAT once per distinct approval-day view and objective. On hard instances each
   search uses 0.3–0.5 s of wall time for its 0.1 deterministic seconds (j3029_9, also in
   generation), so a run at Λ ≤ 1 cost 12 times its v1.8 time there (24 min). The ablation as
   configured then needs about 19–24 h. Options: keep the semantics and cut the ablation
   (Numbers); or, a spec change, imagine the re-plan more cheaply in rollouts (residual SGS with
   LFT, or SHIFT along the candidate's plan) while the world keeps CP-SAT. Rollouts would then
   no longer be exactly the world. Implemented: exactly as in the world.
2. **Δ of an escalated candidate** (§5, §6). `Δ_a` compares the candidate's plan of day t with
   the current plan, but what applies is the plan re-planned on the approval day, different in
   each rollout. Reading used: Δ of the day-t plan, as §5 defines `S^a` (`# SPEC-Q` in
   `agent/evaluate.py::instability`). Alternative: the mean deviation of the plans the rollouts
   approve.

## Numbers
Environment: Intel i5-6600K (4 cores), WSL2 (Linux 6.18), uv 0.13.2, CPython 3.12.15, numpy
2.5.4, ortools 9.15.6755, pydantic 2.14.1. Scenario grid of `docs/experiments/plan.md`, WP2b
seeds, `cpsat_det` baseline plans, D = ⌈1.2 C*⌉, T_cp = 0.1, (N₁, N) = (25, 100), 4 workers.

**Λ = 3 unchanged.** The identity test's six runs are bit-identical to commit fee0ce1. The 96
runs of the main smoke (j301_1 and j601_1, four λ_A, R = 4) equal WP5b's smoke runs of the
same worlds in all 72 non-timing columns; the 64 Sentinel runs took 0.92–1.01 times their old
time (scalarised and δ_D = 0.3 in the ablation smoke: 0.89–0.97).

**Approvals** on identical runs (escalations / applied / discarded, totals):

| Runs | v1.8 (WP5b) | v1.8.1 |
| --- | --- | --- |
| j301_1, λ_A ∈ {0.01, 0.02}, R = 4, Λ0, Λ1, gate, DESCOPE (32 runs) | 25 / 21 / 4 | 49 / 49 / 0 |
| j3010_7 and j3029_9 at 0.02, j3020_3 and j3039_5 at 0.01, replication 0, same variants (16 runs) | 22 / 17 / 5 | 26 / 25 / 1 |

- Plan candidates now win under the gate: at Λ = 0 on j301_1, λ_A = 0.02, 2.0 escalations
  per run (0.25 before), 28.5 plan changes per run (4.0) and a mean makespan of 65.75 (67.25).
- The one discard (DESCOPE variant, j3029_9): an operation of the approved action was no longer
  valid on its approval day.

**Cost of gated runs** (s per run, v1.8 → v1.8.1, identical worlds; j301_1 replication 0 from
the smoke runs, the others from the timing batches):

| Run | Λ = 0 | Λ = 1 | Λ = 2 (gate) | DESCOPE (Λ = 2) |
| --- | --- | --- | --- | --- |
| j301_1, 0.01 | 8.2 → 15.3 (1.86) | 7.5 → 14.8 (1.97) | 7.2 → 10.0 (1.40) | 7.6 → 10.4 (1.36) |
| j301_1, 0.02 | 13.9 → 33.6 (2.43) | 13.4 → 32.6 (2.43) | 10.2 → 13.7 (1.34) | 13.2 → 17.7 (1.34) |
| j3020_3, 0.01 | 9.6 → 19.7 (2.06) | 8.9 → 19.8 (2.24) | 8.3 → 13.2 (1.59) | 9.1 → 14.6 (1.60) |
| j3039_5, 0.01 | 12.3 → 25.0 (2.03) | 11.4 → 24.3 (2.12) | 11.0 → 19.0 (1.73) | 12.1 → 19.7 (1.63) |
| j3010_7, 0.02 | 23.8 → 75.1 (3.16) | 23.2 → 82.8 (3.57) | 20.8 → 32.8 (1.58) | 23.0 → 36.3 (1.58) |
| j3029_9, 0.02 | 122.6 → 1,463.8 (11.9) | 113.3 → 1,384.1 (12.2) | 104.3 → 291.5 (2.79) | 110.7 → 335.1 (3.03) |
| Ratio of sums, 0.01 / 0.02 | 1.99 / 9.82 | 2.12 / 10.00 | 1.59 / 2.50 | 1.55 / 2.65 |

- Rollout re-plans per run at Λ = 0: 5,515 CP-SAT searches with 4,424 plan parts reused
  (j3010_7, 0.02), 6,898 with 19,483 reused (j3029_9, 0.02), 2,935 with 4,125 (j3020_3, 0.01).
- CP-SAT wall time per search, at most 0.1 deterministic s: 8–14 ms on j3010_7; 0.26–0.54 s
  on j3029_9, in generation as in rollouts (90 s instrumented sample). Of a 13.6 ms search on
  j3010_7, 12.3 ms is the native search; model building is 0.8 ms.

**Smoke runs** (gitignored, quoted here):

| Config | Run | Runs | Wall | Outputs | WP2b check | WP4b join | Rejected / fallbacks / truncated |
| --- | --- | ---: | ---: | --- | --- | --- | --- |
| `wp5_rq4_main.toml --limit 1` | 20261022-090932-1f2099ad-smoke | 96 (j301_1, j601_1; 4 λ_A; R = 4; NoReaction + 2 variants) | 4.3 min | results.csv.gz, summary.md, table_wp5_main.tex, table_wp5_main_vs_full_resolve.tex, fig_wp5_tradeoff, fig_wp5_actions (PDF, PNG), manifests | 32 worlds, 0 mismatches | 128 rows, 0 mismatches, 0 missing | 0 / 0 / 0 |
| `wp5_rq4_ablation.toml --limit 1` | 20261022-091404-43270e82-smoke | 56 (j301_1; 2 λ_A; R = 4; NoReaction + 6 variants) | 7.5 min | the same with `table_wp5_ablation*`, `fig_wp5_ablation_*` (two groups of three variants) | 8 worlds, 0 mismatches | 32 rows, 0 mismatches, 0 missing | 0 / 0 / 0 |

Both manifests record commit 3ff2f31 with a clean tree.

**Duration estimates.** Means per run of WP5b's spread sample (J30 and J60 every 96th
instance, replication 0) times the ratios above (per λ_A; 1.0 for the Λ = 3 variants, whose
cost is unchanged). Main: 120 J30 and 60 J60 instances × 4 λ_A × R = 4; ablation: 60 J30
instances × 2 λ_A × R = 4.

| Study (budget) | Option | CPU h | Wall h at full use of 4 workers | Wall h at 0.80 busy |
| --- | --- | ---: | ---: | ---: |
| Main (12 h) | **as configured** (`sentinel_full`, `sentinel_no_ot`) | 37.7 | **9.4** | 11.8 |
| Ablation (6 h) | **as configured** | 75.7 | **18.9** | 23.6 |
| Ablation | the same with one ratio pooled over λ_A | 91.1 | 22.8 | 28.5 |
| Ablation | without `sentinel_lambda1` | 49.5 | 12.4 | 15.5 |
| Ablation | without `sentinel_lambda0` and `sentinel_lambda1` | 22.0 | 5.5 | 6.9 |
| Ablation | Λ = 0 and 1 at λ_A = 0.01 only | 28.1 | 7.0 | 8.8 |
| Ablation | R = 2 | 37.8 | 9.5 | 11.8 |

- Per variant (CPU h, as configured): Λ = 0 27.6, Λ = 1 26.1, DESCOPE 7.9, gate 7.5,
  scalarised 3.6, δ_D = 0.3 3.0.
- The task of one (instance, λ_A) runs its 28 runs in one worker, and the runner starts tasks
  in natural order. A task like j3029_9 at λ_A = 0.02 takes about 4.1 h, so the ablation can
  end well after CPU h / 4. j3029_9 is in the ablation subset.
- The estimate rests on two λ_A = 0.02 pairs. j3029_9 holds about two thirds of WP5b's
  λ_A = 0.02 mean for Λ = 0, so it weighs as one instance in five, as in that sample.

| Measurement | Value |
| --- | --- |
| Tests | default `pytest -q`: 314 passed, 7 deselected in 65.5 s (312 passed in 89.0 s in WP5b); `-m "data or slow"`: 19 passed, 302 deselected in 506.3 s, alongside two timing workers (285.3 s in WP5b; the Sentinel data test runs Λ = 2, now with re-plans, 257 s) |
| Λ = 3 identity | 6 fixture runs bit-identical; 96 smoke runs equal in all non-timing columns |
| Measured runs | 152 smoke runs (0 rejected operations, 0 CP-SAT fallbacks, 0 truncated runs) and 36 timing runs, all checked in debug mode (`run_checked`) |

## Commands for the owner
```bash
cd ~/projects/sentinel && git pull && uv sync --locked
uv run pytest -q                    # expect 314 passed, 7 deselected, ~66 s
uv run pytest -q -m "data or slow"  # expect 19 passed, 302 deselected, ~7-8 min
# RQ4 Sentinel studies, one line in tmux: main (~9.4-11.8 h), commit, ablation (~19-24 h as
# configured, over its 6 h budget: see Spec questions 1 and the options), commit, push.
uv run python -m sentinel.experiments.policy_study --config configs/wp5_rq4_main.toml --out results/wp5 && git add results/wp5 && git commit -m "WP5b.1: RQ4 Sentinel main study" && uv run python -m sentinel.experiments.policy_study --config configs/wp5_rq4_ablation.toml --out results/wp5 && git add results/wp5 && git commit -m "WP5b.1: RQ4 Sentinel ablation study" && git push
```
The smoke directories are gitignored, so `git add results/wp5` adds only the full run, and the
second manifest records the commit of the first run's results with a clean tree. The commit
hooks pass on the generated outputs (checked on a copy of a smoke run).

## Open issues / next steps
- **Architect: the ablation and the cost of exact re-plans** (Spec question 1): keep the
  configured ablation (~19–24 h), cut it (options under Numbers), or let rollouts imagine the
  re-plan more cheaply.
- **Architect: Δ of escalated candidates** (Spec question 2).
- **Runner:** scheduling the longest tasks first would shorten the ablation's tail without
  changing a result (not done: outside this WP).
- **Docs:** `CLAUDE.md` and `docs/workflow/wp-protocol.md` still describe `slow` as "over
  30 s"; the marker now also covers data tests over 3 s (`pyproject.toml`).
- **WP6/WP7** as planned: LLM candidates go through `prepare`, so their approvals re-plan too;
  the RQ4 figures follow the studies.
