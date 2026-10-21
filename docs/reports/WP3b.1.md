# WP3b.1 report — Forecast summaries: early-warning rule, discrimination and skill (no rerun)

- Date: 2026-10-21
- Commit(s): 8a8c9d9 (spec v1.4.2), 443d076 (metrics), e81584c (summaries, configs, tests),
  6955c44 (secret-scan exclusion), bfdf1f3 (regenerated summaries); the report, notes, ADR and
  roadmap commit follows them

## Summary
Spec v1.4.2 (§5.2) adds the Brier skill score against the in-sample base rate, the AUC with
ties counted ½ and the PIT coverage of the central 80 % interval. It also notes why the
quantile coverage over-covers, and early warning now counts only checkpoints f ≥ 0.2, with
f = 0 reported as plan-stage risk.

`forecast_summary` computes all of these with cluster-bootstrap intervals. It writes a
plan-stage table and a 9-column headline table for the article. In the misspecification
tables, the main run's `mc_no_future` and `deterministic` rows for the same worlds appear as
references (4,800 rows, 0 seed and 0 makespan mismatches).

Both run summaries were regenerated in place at e81584c from the committed forecasts.
Forecasts, manifests and figures are unchanged, and `summary_manifest.json` records the
commit, the time and the SHA-256 of every input.

## Acceptance criteria
| # | Criterion | Command | Result |
| --- | --- | --- | --- |
| 1 | Spec v1.4.2 commit | `git show --stat 8a8c9d9` | PASS (`spec: forecast summary metrics (v1.4.2)`: §5.2 BSS, AUC, PIT coverage, quantile over-coverage, early warning from f ≥ 0.2, plan-stage risk, BSS/AUC recomputed per resample; references Murphy 1988, Hanley & McNeil 1982) |
| 2 | Quality gate and `-m data` pass; task-5 tests exist and pass | `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy src`; `uv run pytest -q`; `uv run pytest -q -m data` | PASS (ruff clean; 128 files formatted, Markdown included; mypy: no issues in 41 source files; 237 passed; data: 14 passed, 223 deselected; mapping under Changes) |
| 3 | Both summaries regenerated; `forecasts.csv.gz` and `manifest.json` unchanged; misspec reference join 0 mismatches | `uv run sentinel summarise-forecasts results/wp3/20261021-062709-2a8ba557`, the same for `results/wp3/20261021-091408-f3e5892e`; `sha256sum -c` on the four input files; `git diff --stat e81584c bfdf1f3` | PASS (both at e81584c, `git_dirty` false; all four SHA-256 sums OK; the diff lists only `summary.md`, `*.tex` and `summary_manifest.json` in the run directories (20 files) and `.pre-commit-config.yaml` in the chore commit; figures byte-identical; join: 4,800 rows, **0 seed and 0 makespan mismatches**, 0 missing; WP2b check still 0 mismatches in 15,360 and 480 worlds) |
| 4 | Report, notes, roadmap (`WP3: done`); pushed; clean tree | `git push`; `git status --short` | PASS (this report, `docs/notes/WP3b.1.md`, ADR-0011, roadmap `WP3: done`; pushed to `origin/main`; `git status --short` empty afterwards) |

## Changes
- `docs/spec/model.md` v1.4.2, a separate commit:
  - §5.2 adds BSS (in-sample base rate), AUC (Mann–Whitney form, ties ½) and PIT coverage, and explains why the quantile coverage over-covers;
  - early warning counts f ≥ 0.2, and plan-stage risk at f = 0 is reported separately;
  - BSS and AUC are recomputed on every bootstrap resample;
  - two references are added.
- `forecasting/metrics.py`: `brier_skill_score`, `auc_from_counts` (accepts resample axes), `value_counts`, `auc`, `pit_covered`, `PIT_CENTRAL`.
- `experiments/forecast_config.py`:
  - new `SummarySettings` fields: `warning_from` (0.2), `headline_checkpoints`, `reference_run`, `reference_forecasters`, `plan_stage_table`, `headline_table`;
  - validation: the reference settings come together; reference names must not be forecasters of the run; headline shares must be checkpoints.
- `experiments/forecast_summary.py`:
  - BSS and AUC per binary cell, PIT coverage per distribution cell;
  - early warning from `warning_from`; plan-stage cells;
  - reference join (`join_reference`, `load_reference`, `append_rows`, `checkpoint_keys`, `table_pit`);
  - `run_config`; plan-stage and headline LaTeX tables; new columns in Markdown and in the calibration `.tex`;
  - the commit in the `summary.md` header, and `summary_manifest.json`.
- `experiments/runs.py`: `git_state(exclude=...)`, backwards compatible.
- `cli.py`: `summarise-forecasts` also prints the reference check.
- `configs/wp3_calibration.toml`, `configs/wp3_misspec.toml`: new `[summary]` keys. The misspec config adds `reference_run = "results/wp3/20261021-062709-2a8ba557"`, the reference forecasters and its own table names.
- `.pre-commit-config.yaml`: `detect-secrets` skips `results/*/summary_manifest.json`, as it already skips run manifests.
- `results/wp3/20261021-062709-2a8ba557/`, `results/wp3/20261021-091408-f3e5892e/`: regenerated `summary.md` and tables; new headline and plan-stage tables (also `_delta0.3`) and `summary_manifest.json`.
- Tests (task 5 → test):
  - AUC by hand with ties: `test_forecast_metrics.py::test_auc_by_hand_with_ties` (2/3 with two ties; a point-mass case; leading axes); also `test_auc_matches_the_pairwise_count_and_ignores_monotone_transforms` and `test_resampled_auc_matches_replicated_rows`.
  - BSS of the base-rate forecaster is 0: `test_brier_skill_score_of_the_base_rate_forecaster_is_zero`. In summary cells: `test_forecast_study.py::test_synthetic_skill_discrimination_coverage_and_plan_stage`, where `vague` (p = 0.5) is the base rate at f = 0 and 0.4.
  - PIT coverage ≈ 0.8 for the true distribution: `test_pit_coverage_of_the_true_distribution_is_eighty_percent` (exact CDF within 5 SE; 200-sample ensembles within 0.035; a biased ensemble < 0.6; the quantile coverage is 0.857).
  - Plan-stage table on a synthetic CSV: `test_synthetic_skill_discrimination_coverage_and_plan_stage` (cells, the `summary.md` row, `table_wp3_plan_stage.tex`, the headline row count).
  - Misspec reference join on a synthetic pair with mismatches: `test_reference_rows_are_joined_checked_and_marked` (6 joined, 1 seed and 1 makespan mismatch, 3 missing; `(ref.)`/† marks; reference PIT values as in their own run; all four input files unchanged).
  - The summariser never writes its inputs (task 4): `test_summariser_never_writes_its_inputs` (read-only inputs; bytes and mtimes unchanged after two regenerations; SHA-256 recorded).
  - Further:
    - `test_summary_settings_come_from_the_config_file_while_it_describes_the_run`;
    - four new cases in `test_config_rejects_invalid_values`; `test_wp3_configs_match_the_work_package` checks the new settings and that the reference run exists;
    - `test_synthetic_scores_by_hand` now expects a lead time of 8 days, because f = 0 no longer counts;
    - `test_summaries_can_be_regenerated_through_the_cli`: byte-identical except the summary manifest; with `--replications 1` the summariser falls back to the manifest's settings.

## Decisions
- **Settings on regeneration** (ADR-0011): run parameters come from the manifest. `[summary]` comes from the config file in `config_path` if every other key equals the manifest's config, and from the manifest otherwise. This lets the misspecification config name its reference run without editing `manifest.json`. `summary_manifest.json` records the source and the full settings.
- **Reference rows:**
  - Rows are joined on (set, instance, scenario, replication, f), checked on world seed, forecast seed and makespan, and appended as further forecasters. They are marked `(ref.)` in Markdown and † in LaTeX, ordered `mc_no_future`, `deterministic` as in the main run.
  - They keep the randomised PIT values of their own run, so a row scores the same in both summaries.
  - Rows that mismatch are still added; the count is shown in bold.
  - Figures show only the run's own forecasters, so they stay byte-identical.
- **Provenance:**
  - The `summary.md` header names the generating commit.
  - The dirty flag ignores changes under `results/`: those are outputs, and the inputs there are hashed. Regenerating one run therefore does not mark the next as dirty.
  - `summary_manifest.json` holds the run id, time, commit, dirty flag, settings and their source, the size and SHA-256 of every file read (forecasts, manifest, config file, WP2b results, reference manifest, forecasts and config), the checks and the outputs. Only its timestamp changes between regenerations at one commit.
- **Intervals:** AUC is recomputed on every resample from per-cluster counts of on-time and late forecasts per distinct p, weighted by the cluster multiplicities. This equals the AUC of the replicated rows, pairs across copies included (tested). BSS uses the resampled Brier score and UNC. Brier values and intervals are unchanged from WP3b.
- **PIT coverage:** u ∈ [0.1, 0.9], both ends included, with the existing PIT draws (seed 2026, file order). Headline: a share with 3 decimals; calibration `.tex`: %.
- **Headline table:**
  - 9 columns, with each forecast's three intervals in a second `\scriptsize` row without leading zeros.
  - `\tabcolsep` is 3 pt inside a group, with `@{}` at both ends. Estimated width 115.0 mm (misspec 116.0 mm) against the 122 mm LNCS text width; 132 mm with the default 6 pt.
  - No TeX on the server: widths come from Computer Modern metrics (matplotlib's cmr10, scaled to cmr9 and cmr7).
  - Also written for δ_D = 0.3, as the other tables are; the misspec run gets `table_wp3_misspec_headline.tex`.
- **Early-warning rule:** `warning_from` is a summary setting (default 0.2, the spec value), so the v1.4.1 rule (0.0) can be reproduced. Plan-stage risk is the f = 0 checkpoint. In `summary.md` it follows the early-warning section; in LaTeX it is a separate `table_wp3_plan_stage.tex`.
- ADRs created: ADR-0011 (summary settings on regeneration, reference rows, summary provenance).

## Deviations
- `.pre-commit-config.yaml` is not named in the WP. `detect-secrets` blocked the commit of `summary_manifest.json` because of its SHA-256 digests (false positives). It now skips these files like the run manifests since WP1 (separate `chore:` commit).
- `runs.git_state` takes an optional `exclude` argument (backwards compatible).
- The configs' `[summary]` sections gained keys, so new runs from them get other config hashes than the committed runs. The run parts are unchanged; regeneration depends on that.
- Additions beyond the prompt:
  - headline and plan-stage tables for δ_D = 0.3 as well, and for the misspec run;
  - BSS, AUC and PIT coverage also in the by-λ_A tables;
  - references in the warning, plan-stage and PIT sections of the misspec summary;
  - the summary column "Coverage 80 %" is now "Quantile cov. 80 %".

## Spec questions
1. **Early warning still alarms on most on-time runs at δ_D = 0.2** (§5.2 v1.4.2). With f ≥ 0.2, `mc_full` at θ = 0.5 warns 95.5 % / 96.6 % of late runs (J30 / J60) but also 56.6 % / 51.6 % of on-time runs. Counting f = 0 gave 68.3 % / 61.6 %. At θ = 0.8 the false alarms are 99.1 % / 96.3 %.
   - Cause: 70 % (J30) and 72 % (J60) of the runs are late at δ_D = 0.2, so a calibrated p stays below 0.5 for many on-time runs at f = 0.2.
   - At δ_D = 0.3 (47 % late) the same rule gives 85.2 % / 86.6 % warned with 24.3 % / 19.4 % false alarms.
   - Implemented as written. Should warnings be relative to the plan-stage forecast (e.g. p falls by Δ below its f = 0 value)? Or should the article report early warning at δ_D = 0.3 and leave discrimination to the AUC?

## Numbers
Main run `20261021-062709-2a8ba557` (J30 and J60, 480 instances each, 15,360 worlds, 230,400 forecasts) and misspecification run `20261021-091408-f3e5892e`. All values: δ_D = 0.2, pooled over λ_A, with 95 % cluster-bootstrap intervals over instances (1,000 resamples).

**Headline table** (`table_wp3_headline.tex`; 7,680 forecasts per row; skipped checkpoints: 0):

| Set | f | Forecaster | Brier | BSS | ECE | AUC | CRPS / C* | PIT cov. 80 % |
| --- | --- | --- | --- | ---: | ---: | --- | --- | ---: |
| J30 | 0 | mc_full | 0.174 [0.168, 0.181] | 0.171 | 0.015 | 0.762 [0.748, 0.776] | 0.094 [0.090, 0.098] | 0.788 |
| J30 | 0 | mc_no_future | 0.653 [0.634, 0.669] | -2.112 | 0.665 | 0.589 [0.568, 0.611] | 0.218 [0.210, 0.226] | 0.167 |
| J30 | 0 | deterministic | 0.695 [0.675, 0.713] | -2.313 | 0.695 | 0.504 [0.502, 0.507] | 0.337 [0.328, 0.345] | 0.001 |
| J30 | 0.4 | mc_full | 0.136 [0.130, 0.142] | 0.351 | 0.008 | 0.865 [0.855, 0.876] | 0.071 [0.068, 0.073] | 0.798 |
| J30 | 0.4 | mc_no_future | 0.356 [0.340, 0.370] | -0.695 | 0.405 | 0.829 [0.816, 0.842] | 0.138 [0.132, 0.144] | 0.284 |
| J30 | 0.4 | deterministic | 0.559 [0.541, 0.578] | -1.666 | 0.559 | 0.601 [0.591, 0.610] | 0.220 [0.213, 0.226] | 0.007 |
| J30 | 0.8 | mc_full | 0.096 [0.091, 0.102] | 0.541 | 0.009 | 0.933 [0.926, 0.940] | 0.050 [0.048, 0.053] | 0.805 |
| J30 | 0.8 | mc_no_future | 0.155 [0.145, 0.166] | 0.261 | 0.173 | 0.926 [0.918, 0.933] | 0.080 [0.076, 0.084] | 0.430 |
| J30 | 0.8 | deterministic | 0.299 [0.283, 0.313] | -0.425 | 0.299 | 0.784 [0.773, 0.794] | 0.125 [0.120, 0.129] | 0.035 |
| J60 | 0 | mc_full | 0.149 [0.141, 0.158] | 0.264 | 0.011 | 0.826 [0.812, 0.840] | 0.075 [0.072, 0.078] | 0.804 |
| J60 | 0 | mc_no_future | 0.595 [0.576, 0.615] | -1.942 | 0.634 | 0.714 [0.691, 0.734] | 0.197 [0.190, 0.205] | 0.139 |
| J60 | 0 | deterministic | 0.716 [0.693, 0.737] | -2.536 | 0.716 | 0.502 [0.500, 0.504] | 0.326 [0.317, 0.335] | 0.000 |
| J60 | 0.4 | mc_full | 0.120 [0.113, 0.128] | 0.407 | 0.012 | 0.892 [0.881, 0.903] | 0.055 [0.053, 0.058] | 0.795 |
| J60 | 0.4 | mc_no_future | 0.312 [0.295, 0.328] | -0.542 | 0.359 | 0.862 [0.848, 0.876] | 0.121 [0.117, 0.126] | 0.247 |
| J60 | 0.4 | deterministic | 0.532 [0.512, 0.552] | -1.627 | 0.532 | 0.629 [0.616, 0.643] | 0.200 [0.195, 0.206] | 0.005 |
| J60 | 0.8 | mc_full | 0.086 [0.081, 0.093] | 0.573 | 0.009 | 0.944 [0.937, 0.950] | 0.040 [0.039, 0.042] | 0.794 |
| J60 | 0.8 | mc_no_future | 0.143 [0.134, 0.154] | 0.291 | 0.162 | 0.937 [0.929, 0.944] | 0.071 [0.068, 0.075] | 0.371 |
| J60 | 0.8 | deterministic | 0.288 [0.273, 0.304] | -0.424 | 0.288 | 0.797 [0.785, 0.810] | 0.115 [0.111, 0.119] | 0.024 |

**Coverage of `mc_full`.** The quantile coverage over-covers as expected; every PIT interval contains 0.8.

| Set | Quantile coverage, per f | PIT coverage, per f | PIT coverage, all checkpoints |
| --- | --- | --- | --- |
| J30 | 0.812–0.847 | 0.788–0.805 | 0.798 [0.787, 0.810] |
| J60 | 0.820–0.830 | 0.794–0.804 | 0.799 [0.787, 0.810] |

**Early warning** (f ≥ 0.2; runs pooled over λ_A; J30: 5,381 late and 2,299 on-time runs; J60: 5,516 and 2,164). The last column applies the v1.4.1 rule (f = 0 counted) to the same forecasts:

| Set | Forecaster | θ | Warned (late runs) | Lead time [d] | False alarms (on-time runs) | v1.4.1: warned / false alarms |
| --- | --- | ---: | --- | --- | --- | --- |
| J30 | mc_full | 0.5 | 0.955 [0.948, 0.963] | 59.3 [57.8, 60.8] | 0.566 [0.542, 0.592] | 0.970 / 0.683 |
| J30 | mc_full | 0.8 | 1.000 [0.999, 1.000] | 60.9 [59.5, 62.4] | 0.991 [0.986, 0.995] | 1.000 / 1.000 |
| J30 | mc_no_future | 0.5 | 0.745 [0.725, 0.763] | 43.4 [42.1, 44.7] | 0.052 [0.041, 0.064] | 0.745 / 0.052 |
| J30 | mc_no_future | 0.8 | 0.865 [0.851, 0.878] | 47.3 [46.0, 48.7] | 0.207 [0.185, 0.231] | 0.865 / 0.207 |
| J30 | deterministic | 0.5 / 0.8 | 0.587 [0.564, 0.608] | 39.1 [37.9, 40.3] | 0.011 [0.007, 0.016] | 0.587 / 0.011 |
| J60 | mc_full | 0.5 | 0.966 [0.959, 0.972] | 80.5 [78.6, 82.4] | 0.516 [0.493, 0.542] | 0.975 / 0.616 |
| J60 | mc_full | 0.8 | 0.999 [0.998, 1.000] | 82.3 [80.5, 84.0] | 0.963 [0.953, 0.972] | 1.000 / 0.997 |
| J60 | mc_no_future | 0.5 | 0.762 [0.741, 0.782] | 66.0 [63.2, 68.9] | 0.054 [0.043, 0.067] | 0.762 / 0.054 |
| J60 | mc_no_future | 0.8 | 0.875 [0.860, 0.889] | 69.7 [67.1, 72.3] | 0.183 [0.159, 0.208] | 0.875 / 0.187 |
| J60 | deterministic | 0.5 / 0.8 | 0.610 [0.584, 0.636] | 58.6 [56.1, 61.1] | 0.008 [0.004, 0.013] | 0.610 / 0.008 |

**Plan-stage risk** (f = 0; share of runs with p < θ):

| Set | Forecaster | θ | Late runs | On-time runs |
| --- | --- | ---: | --- | --- |
| J30 | mc_full | 0.5 | 0.868 [0.853, 0.883] | 0.599 [0.570, 0.626] |
| J30 | mc_full | 0.8 | 0.999 [0.999, 1.000] | 0.999 [0.998, 1.000] |
| J30 | mc_no_future | 0.5 / 0.8 | 0.017 / 0.033 | 0.002 / 0.008 |
| J30 | deterministic | 0.5 / 0.8 | 0.008 [0.004, 0.014] | 0.000 [0.000, 0.000] |
| J60 | mc_full | 0.5 | 0.892 [0.877, 0.907] | 0.528 [0.500, 0.557] |
| J60 | mc_full | 0.8 | 0.999 [0.998, 1.000] | 0.993 [0.987, 0.998] |
| J60 | mc_no_future | 0.5 / 0.8 | 0.063 / 0.180 | 0.001 / 0.015 |
| J60 | deterministic | 0.5 / 0.8 | 0.004 [0.001, 0.007] | 0.000 [0.000, 0.000] |

**Misspecified priors with references.** J30, every 4th instance (120), λ_A = 0.01, 2,400 forecasts per row, pooled over checkpoints. `(ref.)` marks rows of the main run on the same worlds (same world and forecast seeds). Differences are paired against `mc_k1`.

| Forecaster | Brier | BSS | ECE | AUC | CRPS / C* | Quantile cov. | PIT cov. | ΔBrier | ΔCRPS / C* |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| mc_k0.5 | 0.161 [0.144, 0.179] | 0.015 | 0.163 | 0.843 | 0.095 | 0.694 | 0.676 | +0.041 [0.026, 0.054] | +0.018 [0.014, 0.022] |
| mc_k1 | 0.121 [0.104, 0.138] | 0.263 | 0.017 | 0.848 | 0.077 | 0.820 | 0.791 | | |
| mc_k2 | 0.149 [0.121, 0.177] | 0.092 | 0.129 | 0.829 | 0.124 | 0.628 | 0.586 | +0.028 [0.014, 0.043] | +0.047 [0.040, 0.055] |
| mc_pert_wide | 0.133 [0.109, 0.157] | 0.188 | 0.085 | 0.841 | 0.085 | 0.766 | 0.726 | +0.012 [0.003, 0.023] | +0.008 [0.005, 0.011] |
| mc_no_future (ref.) | 0.408 [0.380, 0.435] | -1.493 | 0.452 | 0.777 | 0.164 | 0.266 | 0.240 | | |
| deterministic (ref.) | 0.590 [0.556, 0.621] | -2.604 | 0.590 | 0.627 | 0.253 | 0.011 | 0.009 | | |

All four prior variants keep an AUC of 0.83–0.85: misspecification costs calibration and sharpness, not ranking. A check outside the summariser (scratch script) found misspec `mc_k1` identical to main `mc_full` on all 2,400 shared checkpoints (p, CRPS, quantiles), as expected with equal seeds and priors.

| Measurement | Value |
| --- | --- |
| `sentinel summarise-forecasts`, main run | 12.1 s wall, 263 MB peak (WP3b: ≈ 10 s) |
| `sentinel summarise-forecasts`, misspec run | 6.3 s wall, 243 MB peak (reads the 230,400-row main file for the references) |
| Run directory sizes | 6.3 MB and 0.76 MB (limit 20 MB) |
| Cross-checks | brute-force pairwise AUC of J30, f = 0, `mc_full`: 0.761902 vs 0.762 in the summary |
| Tests | 237 passed in 49 s (224 before, 13 new); `-m data` 14 passed in 23 s |

Environment: Intel i5-6600K (4 cores), WSL2 Ubuntu 24.04, CPython 3.12.15, numpy 2.5.4,
matplotlib 3.11.2. No TeX distribution is installed on the server. The headline width is
therefore estimated, not typeset.

## Commands for the owner
No long runs. To regenerate a summary (≈ 12 s and ≈ 6 s):
```bash
uv run sentinel summarise-forecasts results/wp3/20261021-062709-2a8ba557
uv run sentinel summarise-forecasts results/wp3/20261021-091408-f3e5892e
```
Article: `\begin{table}\centering\small\input{table_wp3_headline}\end{table}` (needs
`booktabs`); please check the width once in the LNCS template.

## Open issues / next steps
- Architect: spec question 1 (the early-warning rule at δ_D = 0.2).
- Typeset the headline table once in the LNCS template to confirm the estimated 115 mm.
- WP3 is done; next is WP4 (baseline reactive policies).
