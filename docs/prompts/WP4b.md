# WP4b — Handover model fix, spec answers and the baseline policy study

Fresh session (`/clear`). Read before coding:

<context>
- `CLAUDE.md`, `docs/spec/model.md` (v1.5: §3, §3.1, §4, §4.1, §5.1, §5.2, §7, §7.1, §8),
  `docs/experiments/plan.md`
- `docs/reports/WP4a.md` (spec questions, Numbers), `docs/notes/WP4a.md`, ADR-0012
- `src/sentinel/experiments/{simulation_study,forecast_study}.py` (runner patterns to reuse)
- skills `spec-guard`, `experiment-run`, `adr`, `wp-report`

Architect's review of WP4a. The machinery is sound (0 violations, 0 rejected operations, 0
CP-SAT fallbacks in 1 040 checked runs). Two findings change the model:

1. **The handover cost is mis-scaled — the architect's error in v1.2.**
   `h_j = max(1, ceil(α · e_j · m_j / M_j))` is in *full-crew* days, so replacing one member of
   a ten-person crew costs at least ten crew-member days, while that member's absence (E[L] = 3)
   costs the crew only about three. Every substituting policy therefore loses (on time
   0.05–0.08 vs 0.22). The intended model (Brooks's law) is an onboarding cost *per newcomer*:
   each substitute needs `max(1, ceil(α · e_j))` crew-member days before contributing, so
   `h_j = m_j · max(1, ceil(α · e_j)) / M_j` full-crew days. For a one-person activity this is
   the old formula. Substitution then pays off exactly when the expected remaining absence
   exceeds the onboarding cost — a real trade-off for Sentinel to judge.
2. **CP-SAT deterministic time is 4–13× slower than wall seconds here.** `T_cp = 0.1`.

Answers to the WP4a spec questions (binding):
1. Absence **returns are decision epochs** (§3.1 g: any day with a D1 onset or return). Only the
   `decision_epochs` count of NoReaction changes; makespans and every other result must stay
   bit-identical. Update the regression fixture for that field only and say so in the report.
2. Hint: accepted (whole current plan if feasible, else the residual SGS schedule).
3. Deviation sum of StableResolve and §7.1 nervousness/deviation: only unstarted activities
   with `p_j > 0` that were not inserted on the current day (milestones, the sink and fresh
   D3 activities excluded).
4. Handovers in the belief and the deterministic forecaster: confirmed as implemented, with
   the new `h_j`; write it into §5.1/§5.2.
5. Replaced absent members: increasing id order. Accepted.
6. `FullResolve(subst)` substitutes at event epochs only (now including returns). Confirmed.
7. `T_cp = 0.1` deterministic seconds per stage.
</context>

<task>
0. **Spec v1.6** (commit `spec: per-newcomer handover, return epochs, T_cp (v1.6)`): the new
   `h_j` in §3 and §4 (state it in crew-member days and in full-crew days), answers 1–7,
   `T_cp = 0.1` in §8.
1. **Engine and policies**: implement the new `h_j`, return epochs, the deviation set of
   answer 3. Regression: all NoReaction makespans unchanged; adapt only tests whose expected
   values follow from the spec change (list them in the report).
2. **Test-suite speed chore** (separate commit): mark the WP4a policy data test (and any test
   > 30 s) `@pytest.mark.slow`; default `pytest -q` excludes `slow`; document
   `uv run pytest -q -m "data or slow"` in CLAUDE.md's quality-gate note and in
   `docs/workflow/wp-protocol.md` as the acceptance check. Default `pytest -q` back to ≤ 90 s.
3. **Re-measure the first look** with `scripts/bench_policies.py` (J30 and J60, 20 instances ×
   3 seeds, `λ_A = 0.01`, `T_cp = 0.1`): the same table as in WP4a, plus mean onboarding days
   per substitution. Report it before building the runner (commit the numbers in notes).
4. **Study plan** in `docs/experiments/plan.md`: the RQ4 instance subset, used here and again
   in WP7 for Sentinel with the same seeds — every 4th instance (`stride = 4`, 120 per set) of
   J30 and J60, primary grid `λ_A ∈ {0, 0.005, 0.01, 0.02}`, `E[L] = 3`, `R = 4` (WP2b seeds,
   replications 0–3), deadline evaluated post hoc for `δ_D ∈ {0.2, 0.3}` (no baseline policy
   uses `D`). Sensitivity (`E[L] = 5`, `λ_A ∈ {0.01, 0.02}`) only for J30.
5. **Runner** `src/sentinel/experiments/policy_study.py`, configs
   `configs/wp4_baselines.toml` (primary) and `configs/wp4_sensitivity.toml`
   (`experiment-run` skill): the five policies, CRN seeds as in WP2b with the WP2b makespan
   check for NoReaction (expected 0 mismatches); `results.csv.gz`, one row per
   (set, instance, scenario, replication, policy) with all §7.1 metrics, events, epochs,
   RESEQs, fallbacks, substitutions, onboarding days, cost / B, truncated, runtime.
6. **Summaries** (code-generated, regenerable with `sentinel summarise-policies <run_dir>`):
   per set × `λ_A` × policy: on time for both `δ_D` with Wilson CIs, C / C*, realised
   deviation, nervousness, substitutions, cost / B; **paired differences vs NoReaction** (on
   time, C / C*, deviation) with cluster-bootstrap CIs over instances; `table_wp4.tex`
   (pooled per set × policy, ≤ 9 columns, LNCS width), `fig_wp4_ontime.pdf/.png` (on time vs
   `λ_A`, one line per policy, panels per set) and `fig_wp4_tradeoff.pdf/.png` (on time vs
   realised deviation, one point per policy × `λ_A`, panels per set — the
   performance/stability trade-off that RQ4 is about).
7. **Smoke runs** with `--limit 3`; measured duration estimates for both full studies on 4
   workers; budget for the primary study ≤ 8 h. If it exceeds, report options and stop; do not
   reduce silently. Do not run the full studies in the session.
8. **Tests**: new `h_j` values (one-person, 1 of 10, 3 of 10, `e_j = 0`); a return day is a
   decision epoch; deviation set excludes milestones and fresh D3 activities; runner on
   `tiny.sm` produces the expected columns; summariser on a synthetic CSV.
9. `wp-report` (`docs/reports/WP4b.md`, `docs/notes/WP4b.md`).
</task>

<constraints>
- No OVERTIME, SHIFT, DESCOPE or permission gate (WP5).
- CRN intact; NoReaction makespans bit-identical to WP2b.
- Keep `results/wp4/<run_id>/` < 20 MB.
- Commit after each completed step group.
</constraints>

<acceptance_criteria>
1. Spec v1.6 commit; test-speed chore as a separate commit.
2. Quality gate passes (default `pytest -q` ≤ 90 s) and `-m "data or slow"` passes.
3. First-look table at `T_cp = 0.1` reported with the new `h_j`.
4. Both smoke runs produce every output; NoReaction WP2b check 0 mismatches.
5. Exact full-run commands with measured duration estimates.
6. Report, notes, roadmap (`WP4: in progress: WP4b smoke done`); pushed; clean tree.
</acceptance_criteria>

<report_format>
`docs/reports/WP4b.md` via `wp-report`. "Numbers": the first-look table, smoke summary,
duration estimates.
</report_format>
