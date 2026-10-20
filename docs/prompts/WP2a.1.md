# WP2a.1 — Partial crews and answers to the WP2a spec questions

Run before WP2b, in a fresh session (`/clear`).

<context>
Read: `CLAUDE.md`, `docs/spec/model.md` (v1.1), `docs/reports/WP2a.md` (Spec questions and
Open issues), `docs/notes/WP2a.md`, `docs/adr/0007-*.md`, skills `spec-guard`, `wp-report`.

Architect's review of WP2a: the calibration problem is a modelling problem, not a parameter
problem. PSPLIB capacities give 81–113 workers per instance and activities that need up to 10
workers of a role. Rule §3.1 (a) ("an activity resumes only when *all* original workers are
present and idle; present workers are released") makes one absence stop a ten-person activity
and lets released workers drift to other work, so delays cascade (NoReaction ≈ 2.1–2.5× plan).
In real teams, one absent member out of four slows the work; it does not stop it. The fix is
**partial crews**. Decisions below are binding.
</context>

<task>
0. **Spec v1.2** (separate commit `spec: partial crews and WP2a answers (v1.2)`), edit
   `docs/spec/model.md`:
   - Replace §3.1 (a) with **partial crews**: an activity keeps all its assigned workers until
     it completes; nobody is released on absence. Work is measured in *full-crew days*:
     remaining work starts at `P_j`. On each day the activity runs, it progresses by
     `ρ_j = present_assigned_j / M_j`, where `M_j = Σ_k r_jk` is its crew size. It finishes at
     the end of the first day on which remaining work ≤ 0, so `F_j` = that day + 1. If
     `ρ_j = 0` (whole crew absent) it is paused. Absent workers rejoin automatically on return.
     Under NoReaction nobody is reassigned. `e_j` = work done in full-crew days.
   - §3 handover cost becomes `h_j = max(1, ceil(α · e_j · m_j / M_j))` when SUBST replaces
     `m_j ≥ 1` absent members (for a one-person activity this equals the old formula). SUBST
     itself is implemented in WP4; only the spec changes now.
   - §2.2 D2: the Bernoulli for the k-th work day (a day with `ρ_j > 0`) is drawn on that day
     *before* progress, so one-day activities can be hit; remaining work becomes
     `remaining · F` (no rounding).
   - §3.1 (d)/railway: the rule "never start earlier than planned" applies only to activities
     with `p_j > 0`; zero-duration activities, including the sink, complete as soon as all
     predecessors are done. A project can therefore finish earlier than planned.
   - Record the accepted readings of WP2a spec questions 1, 3 and 4 explicitly: no absence draw
     on the return day; activities inserted by D3 receive no work increases (documented
     simplification); D3 predecessor candidates include the source and finished activities.
   - §8: add `λ_A` grid values `0.0025` (see WP2b) and a note that `λ_A` is per worker and day;
     with `E[L] = 3`, `λ_A = 0.01` means about 3 % of worker-days absent.
1. **Engine**: implement partial crews (float remaining work in full-crew days, per-day rate
   `ρ_j`), the D2 timing change and the zero-duration completion rule. Keep the engine fast
   (precompute `M_j`; update `ρ_j` only when presence of an assigned worker changes). Update
   `realised.py` checks: an activity's assigned workers are reserved (counted against capacity)
   while it runs, even when absent; no worker double-booked; nobody works while absent.
   Remove the resolved `SPEC-Q` markers (replace with plain comments citing the spec section).
2. **Tests** (update or add):
   - one-person activity, worker absent: activity pauses and resumes with the same worker; work
     kept;
   - four-person activity (`M_j = 4`, `P_j = 4`), one member absent for the whole run:
     progresses at 0.75/day and finishes after `ceil(4 / 0.75) = 6` days;
   - whole crew absent: paused, no progress, resumes on first return at the reduced rate;
   - D2 with `lambda_s = 1` hits a one-day activity;
   - early finish: with `X ≡ 1`, no disruptions and a plan whose sink is planned later than
     its predecessors finish, the realised makespan is smaller than the planned one;
   - all WP2a tests still pass (adapt expected values only where the spec change requires it,
     and say which ones in the report).
3. **Calibration table** (report only, not a committed run): 30 J30 instances × 5 seeds,
   baseline SGS-LFT (WP2b introduces the CP-SAT baseline), `mean_absence = 3`,
   `lambda_s = 0.01`, `lambda_n = 0.02`, for `lambda_a ∈ {0, 0.0025, 0.005, 0.01, 0.02}`:
   mean realised/planned makespan ratio and share of runs with makespan ≤ `(1+δ)·C*` for
   `δ ∈ {0.1, 0.2, 0.3}` (`C*` = PSPLIB optimum). Same for 30 J60 instances.
4. Re-measure `simulate` timings (J30, J60; mean and p95 over ≥ 200 calls).
5. Finish with the `wp-report` skill (`docs/reports/WP2a.1.md`, update `docs/notes/WP2a.md`
   with a "Partial crews" section; ADR only if you make a design choice beyond these rules).
</task>

<constraints>
- No new policies, no SUBST implementation (WP4).
- Keep CRN intact: the same seed must still give identical exogenous events across policies.
- No new dependencies.
</constraints>

<acceptance_criteria>
1. Spec v1.2 commit with all amendments.
2. Quality gate and `-m data` pass; all tests in task 2 exist and pass.
3. Calibration table reported for J30 and J60.
4. Timings reported; J30 mean ≤ 5 ms and J60 mean ≤ 15 ms, or a profile and plan if missed.
5. Report and notes updated; pushed; tree clean.
</acceptance_criteria>

<report_format>
`docs/reports/WP2a.1.md` via `wp-report`. "Numbers": the calibration table and timings.
</report_format>
