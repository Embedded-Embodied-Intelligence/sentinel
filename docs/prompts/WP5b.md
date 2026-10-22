# WP5b — Decision-rule fixes, permission gate, rollout budget and the Sentinel study configs

Fresh session (`/clear`). Read before coding:

<context>
- `CLAUDE.md`, `docs/spec/model.md` (v1.7: §1.2, §4, §5, §6, §7.1, §8), `docs/experiments/plan.md`
- `docs/reports/WP5a.md` (spec questions, Numbers), `docs/notes/WP5a.md`, ADR-0013–0015
- `src/sentinel/agent/`, `src/sentinel/policies/sentinel.py`,
  `src/sentinel/experiments/policy_study.py`, `configs/wp4_baselines.toml`
- skills `spec-guard`, `experiment-run`, `adr`, `wp-report`

Architect's review of WP5a. The machinery works (deliberation 0.6 s J30 / 1.1 s J60, 0 rejected
operations), but the **decision rule as I specified it decides on noise**: the deadline component
is a capped hit rate, which carries no signal once a project is late in every rollout, and the
budget component is compared exactly, so cost differences of 0.03 % decide 61–74 % of
deliberations. Sentinel then mostly minimises noise instead of lateness. The fixes below make
every component decide only on differences that are statistically and practically material,
and give late projects a lateness signal. Then the permission gate (Λ, deferral, simulated human)
and DESCOPE complete the agent, and the RQ4 study configs are prepared.

Answers to the WP5a spec questions (binding):
1. SHIFT keeps the order strictly (level 0 must never re-sequence). Confirmed.
2. Budget ties: see task 0 (2 paired SE **or** below `ε_B`).
3. Lateness: see task 0 (expected tardiness as second deadline component).
4. Needs-gate sequencing: accepted.
5. Overtime pay (1.5 c_k per hired day, nothing on top): accepted.
6. Overtime cap counting hired temporaries; unpaid window days after project end: accepted.
7. `B`, `c_k`, `c_OT_k` go into the `Observation` (and Sentinel reads them from there).
8. Scalarised ablation racing on the capped on-time estimate: accepted.
9. Sentinel needs one study run per `δ_D`: accepted; `δ_D = 0.2` is primary (plan below).
Also: set the WP4 roadmap row to `done` (both studies are committed).
</context>

<task>
0. **Spec v1.8** (commit `spec: material decision rule, permission gate, descope (v1.8)`):
   - §6 rule: `a* = lexmax ( min(p̂_a, θ_D), −T̂_a, −o_a, −Δ_a, −ℓ(a) )` with expected
     tardiness `T̂_a = (1/N) Σ_i max(0, C_a^(i) − D)`. Two candidates **tie** in a stochastic
     component (`p̂`, `T̂`, `o`) when the paired (CRN) difference is within 2 paired standard
     errors **or** below its materiality threshold: `ε_D` for `p̂`, `ε_T = 0.5` day for `T̂`,
     `ε_B` for `o`. `Δ` ties below `ε_Δ = 0.5` day; `ℓ` exactly. The best set is filtered
     component by component: keep every candidate tied with the best of the current set, then
     move to the next component; final ties by candidate order of §6. Racing drops a candidate
     only if it is significantly and materially worse in `min(p̂, θ_D)` **and** in `T̂`.
   - §5/§3: the `Observation` carries `B`, `c_k`, `c_OT_k`.
   - §4/§6 **permission gate**: an action runs automatically iff `ℓ(a) < Λ` and it has no
     DESCOPE. Otherwise: if urgency `τ_t > τ_def`, Sentinel *defers* (NOOP now, deliberates again
     at its next deliberation epoch); else it *escalates*: the simulated human approves after
     `δ_h` days; day `t + δ_h` becomes a decision epoch, where the action is re-validated against
     the current state (RESEQ plans against the current planning view) and applied if valid,
     otherwise discarded with a fresh deliberation; meanwhile Sentinel takes no other action.
     In rollouts, a candidate that would need approval is applied at day `t + δ_h` (if valid in
     that rollout), so the agent imagines the approval delay. Record deferrals, escalations,
     approvals applied and approvals discarded.
   - §4 **DESCOPE**: optional activities `O` are drawn per instance with a fixed seed
     (`derive_seed(base, "optional", instance)`): a share `φ` of the real activities whose only
     successor is the sink; value `v_j = p_j · Σ_k c_k r_jk`. DESCOPE(j) removes an unstarted
     `j ∈ O` (its precedence edges vanish); level 2*, always needs approval. Candidates: DESCOPE(j)
     for up to 2 unstarted optional activities with the largest `p_j` (ties: smaller `v_j`,
     then id), generated only if no other candidate reaches `θ_D`. Scope loss is an extra rule
     component right after `T̂` (smaller first, exact), so a DESCOPE wins only when it is
     materially better in `min(p̂, θ_D)` or `T̂`. Metric: scope loss `Σ_removed v_j / Σ_O v_j`.
     DESCOPE is **off** in the main RQ4 comparison (baselines cannot descope) and on only in a
     demonstration config.
   - §8: `ε_T = 0.5`, `ε_Δ = 0.5`, rollout budget `N₁`, `N` per task 3; `Λ` default 2.
1. **Implement** the rule, the gate (world and rollouts), DESCOPE and the observation fields.
   Tests: hand-made statistics for every tie case of task 0 (including "significant but
   immaterial" and "material but within 2 SE"); a hopeless epoch (all `p̂ = 0`) chooses the
   lowest-tardiness candidate; with `Λ = 3` nothing is escalated, with `Λ = 0` every non-NOOP
   action is escalated or deferred; an escalated RESEQ that became invalid is discarded and
   re-deliberated; approval delay in rollouts (a SUBST approved after 1 day yields less gain
   than an immediate one on a constructed case); DESCOPE removes only optional unstarted
   activities and the project stays acyclic and feasible; NoReaction regression unchanged.
2. **Deciding component and reasons**: the decision record names the component that decided
   and the runner-up; the bench script reports the deciding-component table as in WP5a.
3. **Rollout budget study** (report; `scripts/bench_rollout_budget.py`): on ≥ 300 deliberations
   from 10 J30 + 5 J60 Sentinel runs (`λ_A = 0.01`), record the choice with
   `(N₁, N) ∈ {(25, 100), (50, 200)}` against a reference choice with `N = 800` on the same
   worlds: agreement rate and the mean reference-`p̂` / `T̂` loss of the cheaper choice. Adopt
   `(25, 100)` as the default if its mean `T̂` loss ≤ 0.25 day and its `p̂` loss ≤ 0.01; otherwise
   keep `(50, 200)`. State the result in the spec §8 commit or a follow-up spec commit.
4. **Re-measure** with the adopted budget (`scripts/bench_sentinel.py`, 20 J30 × 2 seeds and
   10 J60 × 2 seeds, `λ_A = 0.01`, `Λ = 3` and `Λ = 2`): timing, chosen actions, deciding
   components, first look against NoReaction and FullResolve as in WP5a.
5. **Study plan and configs** (record in `docs/experiments/plan.md`): the RQ4 Sentinel subset is
   J30 every 4th instance (120) and J60 **every 8th** (60, a subset of the WP4b instances, so the
   baselines are already run on the same worlds); `λ_A ∈ {0, 0.005, 0.01, 0.02}`, `E[L] = 3`,
   `R = 4`, WP2b seeds, `δ_D = 0.2`.
   - `configs/wp5_rq4_main.toml`: variants `sentinel_full` (Λ = 3), `sentinel_no_ot` (Λ = 3,
     the fair comparison with the baselines), `sentinel_gate` (full, Λ = 2).
   - `configs/wp5_rq4_ablation.toml`: J30 subset, `λ_A ∈ {0.01, 0.02}`: `sentinel_scalarised`
     (Λ = 3), `sentinel_full` with `Λ ∈ {0, 1}`, `sentinel_descope` (Λ = 2, DESCOPE on,
     `φ = 0.1`), and `sentinel_full` at `δ_D = 0.3`.
   - The runner extends `policy_study` (no second runner): Sentinel variants as policies,
     per-run metrics of §7.1 plus overtime cost and share, hires, deferrals, escalations,
     approvals, scope loss, deliberations, gate exits, rollouts and deciding-component counts;
     summaries add **paired differences vs NoReaction and vs FullResolve on the same worlds**,
     reading the WP4b `results.csv.gz` for the baselines (check seeds and NoReaction makespans,
     expected 0 mismatches) instead of rerunning them.
   - Figures: `fig_wp5_tradeoff` (on time vs realised deviation and vs nervousness, Sentinel
     variants and the five baselines, panels per set), `fig_wp5_actions` (chosen-action shares
     per `λ_A`).
6. **Smoke runs** of both configs with `--limit 2`; duration estimates on 4 workers from a
   spread sample as in WP4b. Budget: main ≤ 12 h, ablation ≤ 6 h. If over, report options and
   stop. Do not run the full studies in the session.
7. `wp-report` (`docs/reports/WP5b.md`, `docs/notes/WP5b.md`); ADR for the gate in rollouts.
</task>

<constraints>
- No LLM (WP6). The agent sees only the `Observation`.
- CRN intact; NoReaction makespans bit-identical to WP2b.
- No new runtime dependencies. Commit after each completed step group.
- Anything longer than ~10 minutes goes to the owner as a tmux command, with an estimate.
</constraints>

<acceptance_criteria>
1. Spec v1.8 commit (and the rollout-budget decision recorded in the spec).
2. Quality gate (default `pytest -q` ≤ 90 s) and `-m "data or slow"` pass; task-1 tests exist.
3. Rollout-budget table, re-measured timing, deciding-component table and first look reported.
4. Both smoke runs produce every output; WP4b baseline join 0 mismatches; full commands with
   measured estimates.
5. Report, notes, roadmap (`WP4: done`, `WP5: in progress: WP5b smoke done`); pushed; clean.
</acceptance_criteria>

<report_format>
`docs/reports/WP5b.md` via `wp-report`. "Numbers": rollout-budget table, timing, deciding
components (before/after the fix), first look, duration estimates.
</report_format>
