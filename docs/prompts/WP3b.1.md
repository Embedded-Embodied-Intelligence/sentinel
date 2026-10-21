# WP3b.1 — Forecast summaries: early-warning rule, discrimination and skill (no rerun)

Fresh session (`/clear`). Small WP: summary code and spec only. **No forecast or world is
recomputed**; everything is derived from the committed `forecasts.csv.gz` files.

<context>
- `CLAUDE.md`, `docs/spec/model.md` §5.2, `docs/reports/WP3b.md`, `docs/notes/WP3b.md`
- full runs: `results/wp3/20261021-062709-2a8ba557/` (main) and
  `results/wp3/20261021-091408-f3e5892e/` (misspecification)
- skills `experiment-run`, `wp-report`

Architect's review of the full runs (binding decisions below):
- `mc_full` is calibrated (REL ≤ 0.001, ECE ≈ 0.01) and its Brier falls from 0.174 (f = 0) to
  0.096 (f = 0.8) on J30; `deterministic` is worse than the base rate at every checkpoint.
- The early-warning rule counts f = 0. Because most runs are late at `δ_D = 0.2`, a calibrated
  forecaster "warns" on day 0 for nearly every run, so false alarms are 68–100 %. Day 0 is
  plan-stage risk, not early warning of a deviation.
- The 80 % interval covers 81–85 %: integer makespans with inclusive quantile bounds over-cover.
  PIT-based coverage is the exact check.
- The misspecified-prior runs share their worlds with the main run (same seeds), so the
  `deterministic` and `mc_no_future` scores for the same worlds already exist.
</context>

<task>
0. **Spec v1.4.2** (commit `spec: forecast summary metrics (v1.4.2)`), §5.2:
   - early warning counts checkpoints `f ≥ 0.2` only; f = 0 is reported separately as
     *plan-stage risk*: share of runs with `p_on_time < θ` at f = 0, split by outcome;
   - add AUC (ROC) of `p_on_time` for separating on-time from late runs (ties count ½);
   - add Brier skill score `BSS = 1 − Brier / UNC` against the in-sample base rate of the same
     cell (state that it is in-sample);
   - add PIT coverage of the central 80 % interval: share of randomised PIT values in
     `[0.1, 0.9]`; keep the quantile coverage and note why it over-covers.
1. **Summary code**: implement the above in `forecast_summary` with cluster-bootstrap CIs as for
   the other metrics; AUC and BSS in the calibration tables, PIT coverage in the makespan tables,
   the plan-stage-risk table next to the early-warning table.
2. **Misspecification references**: when summarising the misspecification run, read the main
   run's `forecasts.csv.gz` (path in the misspec config, e.g. `reference_run`), take the
   `deterministic` and `mc_no_future` rows for the same (set, instance, scenario, replication,
   f), check that seeds and true makespans match (report mismatches, expected 0), and add them
   as reference rows in every misspec table.
3. **Headline table** `table_wp3_headline.tex` for the article, per set and
   `f ∈ {0, 0.4, 0.8}` × forecaster: Brier [CI], BSS, ECE, AUC [CI], CRPS / C* [CI], PIT
   coverage 80 %. Keep it ≤ 9 columns so it fits one LNCS column width with `\small`.
4. **Regenerate** both run summaries in place with `sentinel summarise-forecasts <run_dir>`
   (code-generated, so allowed); record the generating commit in the `summary.md` header and in
   a small `summary_manifest.json` (commit, timestamp, input file SHA-256). Do not touch
   `forecasts.csv.gz` or `manifest.json`; add a test that the summariser never writes them.
5. **Tests**: AUC against a hand-computed example with ties; BSS of the base-rate forecaster
   is 0; PIT coverage of samples from the true distribution ≈ 0.8; plan-stage table on a
   synthetic CSV; misspec reference join on a synthetic pair of CSVs (including a mismatch).
6. `wp-report` (`docs/reports/WP3b.1.md`); in "Numbers" give the headline table as markdown and
   the early-warning table (θ = 0.5, 0.8; f ≥ 0.2) for both sets, plus the misspec table with
   references. Roadmap: `WP3: done`.
</task>

<constraints>
- No change to forecasts, worlds, engine or forecasters. Summary regeneration only.
- Keep each run directory < 20 MB.
</constraints>

<acceptance_criteria>
1. Spec v1.4.2 commit.
2. Quality gate and `-m data` pass; task-5 tests exist and pass.
3. Both run summaries regenerated; `forecasts.csv.gz` and `manifest.json` unchanged
   (`git diff --stat` shows only summary files); misspec reference join reports 0 mismatches.
4. Report, notes, roadmap (`WP3: done`); pushed; clean tree.
</acceptance_criteria>

<report_format>
`docs/reports/WP3b.1.md` via `wp-report`.
</report_format>
