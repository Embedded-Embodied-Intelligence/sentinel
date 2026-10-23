# Experiment plan

Scenario selection for WP3b–WP7, made by the architect from the WP2b NoReaction study, run
`results/wp2/20261020-181559-6534a712` (NoReaction on `cpsat_det` baseline plans; 480 instances
per set × 20 replications; common random numbers across scenarios; `summary.md` of the run).
The aim is a region where the base policy is on time often but not always, so that
interventions can help and harm.

## Scenarios

| Role | δ_D | λ_A | E[L] | λ_S | λ_N |
| --- | ---: | --- | ---: | ---: | ---: |
| Primary grid | 0.2 | {0, 0.005, 0.01, 0.02} | 3 | 0.01 | 0.02 |
| Sensitivity: deadline | 0.3 | as primary | 3 | 0.01 | 0.02 |
| Sensitivity: absence length | 0.2 | as primary | 5 | 0.01 | 0.02 |

Deadline `D = ceil((1 + δ_D) C*)` with `C*` = J30 optimum (`opt`), J60 best known (`hrs`)
(spec §1.2); PERT(0.8, 1.0, 1.6), λ = 4; `T_r = 5`; `β = 0.1`. Single-scenario checks (e.g. the
WP3a forecaster tests and timings) use the primary scenario with `λ_A = 0.01`.

## Evidence (run 20261020-181559-6534a712)

NoReaction on time, `C ≤ D`, in % of 9,600 runs per cell, E[L] = 3:

| Set | λ_A | δ_D = 0.1 | δ_D = 0.2 | δ_D = 0.3 | C / C* |
| --- | ---: | ---: | ---: | ---: | ---: |
| J30 | 0 | 21.2 | 51.2 | 72.4 | 1.252 |
| J30 | 0.005 | 8.9 | 33.3 | 58.6 | 1.319 |
| J30 | 0.01 | 4.6 | 22.9 | 48.8 | 1.361 |
| J30 | 0.02 | 1.5 | 12.8 | 35.6 | 1.422 |
| J60 | 0 | 15.5 | 46.5 | 70.5 | 1.257 |
| J60 | 0.005 | 5.4 | 30.0 | 56.3 | 1.321 |
| J60 | 0.01 | 2.3 | 21.0 | 47.2 | 1.361 |
| J60 | 0.02 | 0.7 | 11.3 | 35.6 | 1.415 |

- **δ_D = 0.2 (primary):** on time in 11–51 % of runs, decreasing in λ_A on both sets.
- **δ_D = 0.3 (sensitivity):** 36–72 %, a looser deadline.
- **E[L] = 5 (sensitivity), δ_D = 0.2:** J30 30.4 / 19.6 / 8.3 %, J60 28.1 / 18.1 / 7.8 % for
  λ_A = 0.005 / 0.01 / 0.02 (λ_A = 0 is the same scenario as for E[L] = 3).
- **δ_D = 0.1 excluded:** NoReaction is on time in only 2.3–21.2 % of runs for λ_A ≤ 0.01
  (0.7–1.5 % at λ_A = 0.02): the deadline is mostly missed before any absence, because D2 and D3
  alone raise C / C* from 1.10 (J30) and 1.12 (J60) with durations only to 1.25 and 1.26.
- λ_A = 0.0025 (studied in WP2b) is not in the grid; its cells lie between those of λ_A = 0
  and 0.005 (on time at δ_D = 0.2: J30 41.0 %, J60 37.1 %).

No run of the study was truncated. Intervals and the remaining scenarios are in the run's
`summary.md`.

## RQ4 baseline study (WP4b, reused in WP7)

The five baseline policies of spec §7 (NoReaction, AlwaysSubstitute, FullResolve,
FullResolve(subst), StableResolve(subst)) start from the `cpsat_det` baseline plans of WP2b.
WP7 runs Sentinel on the same instances, scenarios and seeds, so its runs pair with these.

| Item | Value |
| --- | --- |
| Instances | every 4th of J30 and of J60 in natural order (`stride = 4`): 120 per set, `j301_1`, `j301_5`, `j301_9`, `j302_3`, … |
| Primary grid | J30 and J60, λ_A ∈ {0, 0.005, 0.01, 0.02}, E[L] = 3, λ_S = 0.01, λ_N = 0.02 |
| Sensitivity | J30 only, E[L] = 5, λ_A ∈ {0.01, 0.02} |
| Replications | R = 4: the WP2b seeds of replications 0–3, `derive_seed(2026, set, instance, r)`, shared by all policies and scenarios (common random numbers) |
| Deadline | evaluated post hoc for δ_D ∈ {0.2, 0.3}; no baseline policy uses D (the urgency order of AlwaysSubstitute does not depend on it), max_days of δ_D = 0.3 as in WP2b |
| Policy settings | T_r = 5, α = 0.3, T_cp = 0.1 deterministic s per CP-SAT stage, one CP-SAT worker, CP-SAT seed 0 |
| Check | NoReaction reproduces the WP2b seeds and makespans of run `20261020-181559-6534a712` (0 mismatches expected) |
| Size | primary 2 × 120 × 4 × 4 × 5 = 19,200 runs; sensitivity 120 × 2 × 4 × 5 = 4,800 runs |
| Configs | `configs/wp4_baselines.toml` (primary), `configs/wp4_sensitivity.toml`; outputs in `results/wp4/<run_id>/` |

Summaries: per set × λ_A × policy the on-time shares for both δ_D (95 % Wilson intervals), C / C*,
realised deviation and nervousness (§7.1), substitutions and cost / B; paired differences against
NoReaction (on time, C / C*, deviation) with 95 % cluster bootstrap intervals over instances.

## RQ4 Sentinel study (WP5b, run in WP7)

Sentinel variants on worlds of the WP4b baseline study, so every Sentinel run pairs with the
five baselines' runs of the same world (set, instance, scenario, replication; common random
numbers). The baselines are read from the WP4b results instead of being rerun; NoReaction is
rerun as the check (its seeds and makespans must equal those of WP2b and WP4b, 0 mismatches).

| Item | Value |
| --- | --- |
| Instances | main: J30 every 4th (120, the WP4b instances); J60 **every 8th** (60, `j601_1`, `j601_9`, `j602_7`, …, a subset of the WP4b instances); ablation: J30 **every 8th** (60, `j301_1`, `j301_9`, `j302_7`, …, a subset of the main J30 instances) |
| Grid | main: λ_A ∈ {0, 0.005, 0.01, 0.02}; ablation: λ_A ∈ {0.01, 0.02}; autonomy levels: λ_A = 0.01; all E[L] = 3, λ_S = 0.01, λ_N = 0.02, R = 4 with the WP2b seeds of replications 0–3 |
| Deadline | Sentinel works towards δ_D = 0.2 (primary; ADR-0013: a deadline-aware policy needs one run per δ_D), on time for δ_D = 0.3 post hoc; max_days 5 D(δ_D) of its own deadline |
| Sentinel | spec v1.8.1 parameters (§8): N₁ = 25, N = 100 (WP5b rollout-budget study), θ_D = 0.8, ε_D = 0.02, ε_B = 0.01, ε_T = ε_Δ = 0.5 d, T_cp = 0.1, B with β = 0.1 in the observation; behind the gate (Λ < 3), an approved action is planned again on its approval day, in the world and in rollouts (§4, §6) |
| Main variants | `sentinel_full` (Λ = 3), `sentinel_no_ot` (no OVERTIME, Λ = 3: the fair comparison with the baselines, which cannot hire) |
| Ablation | `sentinel_scalarised` (Λ = 3), `sentinel_lambda0`, `sentinel_lambda1` and `sentinel_gate` (full, Λ = 0, 1 and 2: the permission gate), `sentinel_descope` (full, Λ = 2, DESCOPE on, `O` = the three real activities whose only successor is the sink; a demonstration, since the baselines cannot descope), `sentinel_delta03` (full, Λ = 3, δ_D = 0.3) |
| Size | main 2 × (1,920 J30 + 960 J60) = 5,760 Sentinel runs; ablation 4 × 480 = 1,920 and autonomy levels 2 × 240 = 480 Sentinel runs; plus the NoReaction checks |
| Split (WP5b.1) | The autonomy levels Λ = 0 and 1 (`sentinel_lambda0`, `sentinel_lambda1`) run at λ_A = 0.01 only, in their own config `configs/wp5_rq4_autonomy.toml`, for the time budget: an approved action is planned again on its approval day, so gated rollouts run CP-SAT and a run at Λ ≤ 1 costs 2–12 times one at Λ = 3 (`docs/reports/WP5b.1.md`). `configs/wp5_rq4_ablation.toml` keeps `sentinel_scalarised`, `sentinel_gate`, `sentinel_descope` and `sentinel_delta03` at λ_A ∈ {0.01, 0.02} |
| Sizes (WP5b.1) | Set by the architect after WP5b for two reasons. Budget: as first planned (three main variants; five ablation variants on J30 every 4th) the studies needed about 14.4 h and 9.0 h on 4 workers (WP5b measurements), over the 12 h and 6 h budgets. Scope: the permission-gate variants belong to the ablation; the main study compares Sentinel with the baselines, which have no gate, while the autonomy level Λ is a deployment setting compared within Sentinel, on the ablation subset. Measured duration estimates: `docs/reports/WP5b.1.md` |
| Configs | `configs/wp5_rq4_main.toml`, `configs/wp5_rq4_ablation.toml`, `configs/wp5_rq4_autonomy.toml` (`policy_study` runner, outputs in `results/wp5/<run_id>/`) |
| Runs | main `results/wp5/20261022-102609-e9d131b3` (8,640 rows with the NoReaction check, 9.2 h); ablation `20261022-193948-592f7183` (2,400 rows, 4.1 h); autonomy levels `20261022-234437-49965457` (720 rows, 2.8 h); all on 4 workers |
| Metrics | spec §7.1 per run, plus overtime cost and share, temporary workers hired, deferrals, escalations, approvals applied and discarded, scope loss, deliberations, needs-gate exits, rollouts and the chosen candidates and deciding components |

Summaries: the WP4b ones (on time with Wilson intervals, C / C*, realised deviation,
nervousness, cost / B) for the Sentinel variants and the five baselines, and paired differences
**against NoReaction and against FullResolve** on the same worlds with 95 % cluster bootstrap
intervals over instances; Sentinel's per-run counts, chosen actions and deciding components per
λ_A. Figures: `fig_wp5_tradeoff` (on time against realised deviation and against nervousness,
the Sentinel variants and the five baselines, a column of panels per set) and
`fig_wp5_actions` (the share of deliberations choosing each kind of action, per λ_A).

## RQ1 WBS extraction study (WP6a)

RQ1: does validation with a repair loop improve the correctness of an LLM-extracted project
model (WBS with durations, crews and dependencies) compared with single-shot extraction? To
have exact ground truth without circularity, the project descriptions are generated
deterministically from PSPLIB instances by templates (no LLM writes the inputs); the LLM must
recover the instance from the text.

| Item | Value |
| --- | --- |
| Instances | J30 **every 12th** in natural order (`stride = 12`): 40, `j301_1`, `j302_3`, `j303_5`, …, `j3047_9` (includes the CP-SAT-hard `j3029_9`) |
| Narrator | `sentinel.wbs.narrate`, fully deterministic: roles R1–R4 are the backend developer, frontend developer, tester and DevOps engineer; activities get unique names from a seeded vocabulary of their dominant role; the text states the team (capacity per role) and for every real activity its name, duration in working days, crew per role and immediate predecessors by name; source and sink are implicit |
| Styles | `structured` (one block per activity in topological order, fixed phrasing) and `narrative` (prose paragraphs in a shuffled order, varied phrasings, each dependency stated once on the successor or on the predecessor, numbers sometimes in words) |
| Narrator seed | fixed base seed; one seed per instance, shared by both styles, so both styles name the activities identically |
| Backends | local Ollama `qwen2.5:7b` (Ollama 0.40.6, weights digest pinned in the config; project data stay on premises) and Groq (cloud, the strongest generally available open model; choice and date in the LLM-layer ADR) |
| Conditions | `single_shot` (one call) and `repair` (after a call with issues, the issue list and the previous JSON are sent back with a request for a corrected full JSON; at most 3 repair rounds). The single-shot answer is the first call of the repair session, so both conditions come from one session per (instance, style, backend) |
| Decoding | temperature 0, one seed per session shared by the backends, the output JSON schema given to the backend; versioned English prompts in `src/sentinel/llm/prompts/` |
| Validation | missing fields, unknown roles, duplicate or unknown activity names, cycles (listed), non-positive durations, crews above team capacity; a valid answer becomes a `ProjectInstance` with source and sink added |
| Metrics | valid-instance rate; activity recall and precision (match by normalised name, unmatched reported); precedence-edge precision, recall and F1 on matched activities; duration and crew accuracy (exact) on matched activities; team accuracy; exact-instance rate (isomorphic to the truth); downstream CP-SAT makespan of a valid extracted instance against the true one (relative error); tokens and latency per session |
| Statistics | rates with 95 % Wilson intervals; paired differences repair − single-shot over the same sessions with 95 % percentile intervals of a bootstrap over instances |
| Outputs | `results.csv` (one row per instance, style, backend and condition, with rounds used and final issues), `summary.md`, `table_wp6_rq1.tex`, `fig_wp6_rq1.pdf/.png` (validity and edge F1 by round 0–3 per backend and style), `manifest.json` with the cache hit rate, and the replay bundle `llm_cache.jsonl.gz` (< 10 MB) that regenerates the run without an API key |
| Size | 40 instances × 2 styles × 2 backends = 160 sessions of 1–4 calls; 320 result rows |
| Runs | Ollama and Groq as separate commands, each committing its run; the Groq run respects the free-tier limits, possibly over more than one day, and resumes from the record/replay cache |
| Config | `configs/wp6_rq1.toml` (runner `sentinel.experiments.wbs_study`, outputs in `results/wp6/<run_id>/`) |
