# WP5b.1 — Re-plan on approval, spec answers, study sizes

Fresh session (`/clear`). Small WP: one semantic fix, spec answers, config sizes, test speed.

<context>
- `CLAUDE.md`, `docs/spec/model.md` (v1.8: §4, §6, §8), `docs/reports/WP5b.md`,
  `docs/notes/WP5b.md`, ADR-0016, `configs/wp5_rq4_main.toml`, `configs/wp5_rq4_ablation.toml`
- skills `spec-guard`, `experiment-run`, `wp-report`

Architect's review of WP5b: accepted. The material rule works (budget noise decides ≤ 2 %),
Sentinel (Λ = 3) has the lowest C/C* and a quarter to a fifth of FullResolve's plan changes.

Answers to the WP5b spec questions (binding):
1. **Re-plan on approval.** A human approves the *intent* of an action, not a stale schedule.
   On the approval day the plan parts are recomputed on the current planning view with the same
   objective (RESEQ-M: minimum makespan; RESEQ-S: minimum deviation subject to the makespan of
   the current SHIFT; SHIFT: recomputed; with temporary workers included for OT+RESEQ-M); SUBST
   and OVERTIME parts are re-validated; the action applies all-or-nothing and is discarded
   (with a fresh deliberation) only if a SUBST/OT part is invalid or the re-plan fails. Rollouts
   imagine exactly this.
2. **Optional activities:** `O` = all real activities whose only successor is the sink (three
   per PSPLIB instance); drop `φ` from §4 and §8.
3.–6. Accepted as implemented and written into the spec.
7. **Repeated DESCOPE deferrals:** intended (re-deliberation each epoch; escalation once the
   urgency drops to `τ_def`). No memory of deferred actions.
</context>

<task>
0. **Spec v1.8.1** (commit `spec: re-plan on approval, optional activities (v1.8.1)`):
   answers 1–7.
1. **Implement** answer 1 (world and rollouts share the code) and answer 2. Tests: an approved
   RESEQ-M whose original plan became stale is re-planned and applied; an approved SUBST whose
   worker became absent is discarded and re-deliberated; rollout and world agree on a
   constructed case; `O` has three activities on `tiny.sm`-like and PSPLIB instances.
2. **Test speed** (separate commit): default `pytest -q` ≤ 75 s (mark the slowest tests
   `slow`, or make them cheaper); `-m "data or slow"` still covers them.
3. **Study sizes** (binding):
   - `configs/wp5_rq4_main.toml`: variants `sentinel_full` and `sentinel_no_ot` only (Λ = 3);
     subset unchanged (J30 every 4th, J60 every 8th, 4 `λ_A`, R = 4, δ_D = 0.2).
   - `configs/wp5_rq4_ablation.toml`: J30 **every 8th** instance (60), `λ_A ∈ {0.01, 0.02}`,
     R = 4; variants `sentinel_scalarised` (Λ = 3), `sentinel_full` with `Λ ∈ {0, 1, 2}`,
     `sentinel_descope` (Λ = 2), and `sentinel_full` at `δ_D = 0.3`.
   - Record both in `docs/experiments/plan.md` with the reasons (budget; the gate variants
     belong to the ablation).
4. **Smoke** both configs with `--limit 1` and give measured duration estimates (spread sample
   as in WP5b, but at most 10 minutes in session; otherwise extrapolate from WP5b's sample and
   say so). Give **one** tmux command line that runs main, commits it, runs the ablation,
   commits it and pushes (commit between runs, so the second manifest is clean).
5. `wp-report` (`docs/reports/WP5b.1.md`); roadmap `WP5: in progress: WP5b.1 done, studies
   pending`.
</task>

<constraints>
- Λ = 3 behaviour must not change (no gate involved): add a test that a Λ = 3 Sentinel run is
  bit-identical before and after this WP on 3 seeds.
- NoReaction makespans bit-identical. No new dependencies. Commit after each step group.
</constraints>

<acceptance_criteria>
1. Spec v1.8.1 commit; test-speed chore separate.
2. Quality gate (default `pytest -q` ≤ 75 s) and `-m "data or slow"` pass; task-1 tests and the
   Λ = 3 identity test exist and pass.
3. Configs and plan updated; smoke runs complete; estimates and the single command line given.
4. Report, roadmap; pushed; clean tree.
</acceptance_criteria>

<report_format>
`docs/reports/WP5b.1.md` via `wp-report`.
</report_format>
