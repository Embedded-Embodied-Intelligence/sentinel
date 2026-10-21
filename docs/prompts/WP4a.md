# WP4a — Interventions in the engine, residual rescheduling and the baseline policies

Fresh session (`/clear`). Read before coding:

<context>
- `CLAUDE.md`, `docs/spec/model.md` (v1.4.2: §3, §3.1, §4, §5.2 deterministic forecaster, §6,
  §7, §8), `docs/spec/architecture.md`
- `docs/reports/WP3a.md`, `docs/reports/WP3b.md`, `docs/notes/WP3a.md`, ADR-0006, ADR-0009
- `src/sentinel/policies/base.py`, `src/sentinel/simulation/engine.py`,
  `src/sentinel/scheduling/{sgs,cpsat}.py`, `src/sentinel/forecasting/deterministic.py`
- skills `spec-guard`, `adr`, `wp-report`

WP4 gives the world its classical *reactive* competitors (§7), against which Sentinel (WP5) is
judged in RQ4. WP4a builds the machinery: the SUBST and RESEQ operations in the engine, a
**residual** scheduling problem (the rest of the project as seen from day `t`) solved by CP-SAT
and by a serial SGS with time-varying capacity, and the policies `AlwaysSubstitute`,
`FullResolve` and `StableResolve`. WP4b runs the comparison study. WP5 will reuse every piece:
SUBST and RESEQ are Sentinel's candidate actions, and its rollouts decode plans with the
residual SGS. So operations must work identically in the true world and in rollouts
(`Run.resume`).

Architect's decision on the WP3b.1 question: the early-warning rule stays as implemented.
False alarms at `δ_D = 0.2` reflect a 70 % base rate of late runs, not a forecaster flaw; the
article uses AUC as the discrimination metric and the `δ_D = 0.3` warning table. No change to
WP3 results.

The decisions below are binding.
</context>

<task>
0. **Spec v1.5** (commit `spec: interventions, residual planning and baselines (v1.5)`):
   - §4 SUBST details: an *idle* worker is present and in no crew. SUBST(j, W') takes, per
     replaced member, an idle present worker of the same role; the replaced member leaves the
     crew at once (on return they are idle); `h_j` full-crew days are added to `j`'s remaining
     work; `ρ_j` is recomputed immediately, so the new crew can progress on the same day.
     Operations are applied in step 3 in the order given, each validated against the state
     left by the previous one; an invalid operation is rejected (logged, counted), the others
     still apply.
   - new §4.1 **Planning view** (what a planner assumes at day `t`, the same assumptions as the
     deterministic forecaster of §5.2): started activities (running or paused) keep their whole
     crew reserved until their *estimated finish* `F̂_j` = their finish in the deterministic
     forecast from the current observation; absent idle workers are unavailable until their
     announced return (`s + L_low`, or `t + 1` if that has passed); unstarted activities take
     their nominal duration `p_j` (inserted ones: their nominal duration); the capacity of role
     `k` on day `τ ≥ t` is `R_k` minus reserved crew members minus unavailable idle workers.
     The **residual problem** schedules all unstarted activities on days `≥ t` under this
     capacity profile and precedence (finished predecessors: realised finish; started ones:
     `F̂_j`).
   - RESEQ(π') replaces the planned starts of all unstarted activities by a feasible solution
     of the residual problem. Dispatch semantics (§3 step 4) are unchanged.
   - §7 baselines, precisely:
     - `AlwaysSubstitute`: at every decision epoch, for paused and running activities with
       absent members, in increasing `τ_j` (§5 urgency, ties by id), substitute every absent
       member for which an idle present worker of the same role exists (lowest ids first).
       Plan unchanged.
     - `FullResolve(subst)`: at every decision epoch that has a D1 (onset or return), D2 or D3
       event (not purely periodic epochs): if `subst`, first the SUBST operations of
       `AlwaysSubstitute`; then RESEQ with minimum residual makespan.
     - `StableResolve(subst)`: as FullResolve, but RESEQ is lexicographic: stage 1 minimum
       residual makespan `C₁`; stage 2 minimum `Σ_j |S_j − S_j^t|` over unstarted activities
       (`S_j^t` the current plan; inserted activities without a planned start are excluded from
       the sum) subject to makespan `≤ C₁` (Van de Vonder et al. 2007 style robust repair).
     - CP-SAT in policies: 1 worker, fixed seed, deterministic limit `T_cp` per stage
       (default 0.5), solution hint = the current plan where feasible; if no feasible solution
       is found within the limit, fall back to the residual SGS with LFT priority and count it.
   - new §7.1 **Evaluation metrics** (WP4b, WP7): on-time for each `δ_D`, makespan / `C*`,
     cost / `B`; *realised deviation* `(1/n) Σ_{j ≤ n} |S_j^real − S_j^0|` against the baseline
     plan; *nervousness* = total number of (epoch, activity) pairs whose planned start changed;
     number of substitutions and handover days; number of RESEQs and CP-SAT fallbacks.
   - §8: `T_cp = 0.5` deterministic seconds.
1. **Formatting chore** (separate commit `chore: typeset negative numbers in LaTeX tables`):
   generated `.tex` tables write negatives as `$-$0.425` (or `\textminus`), not a hyphen.
   Regenerate the WP3 summaries with the existing command (no rerun); only `.tex` files may
   change.
2. **Operations** in `policies/base.py`: extend the discriminated union with
   `Subst(activity, workers)` and `Reseq(starts: mapping activity → day)`; keep `Noop`.
   Engine step 3 applies them as specified (shared by `simulate` and `Run.resume`); the
   `SimulationResult` records applied/rejected operations, substitutions, handover days,
   RESEQ count and nervousness. Engine fast path for empty decisions must stay as fast as now
   (re-measure `simulate` timings with NoReaction; ≤ 5 % slower).
3. **Planning view and residual problem** `src/sentinel/scheduling/residual.py`:
   `planning_view(observation) -> ResidualProblem` (frozen; activities, durations, demands,
   release day `t`, fixed predecessor finishes, capacity profile per role as piecewise-constant
   steps, current planned starts) built from the deterministic forecast; `validate_residual`.
4. **Residual SGS** `residual_sgs(problem, priority="lft") -> dict[int, int]`: serial SGS with
   release times and a time-varying capacity profile (Kolisch 1996 generalised). Must also be
   fast enough for WP5 rollouts: report mean time on J30/J60 planning views.
5. **Residual CP-SAT** `solve_residual(problem, objective="makespan" | "stable", *,
   deterministic_time_limit, seed, hint) -> ResidualSolution` (status, starts, makespan,
   objective, fallback flag). Model the capacity profile by fixed intervals in the cumulative
   constraints.
6. **Policies** `src/sentinel/policies/{always_substitute,resolve}.py`: `AlwaysSubstitute`,
   `FullResolve(subst: bool)`, `StableResolve(subst: bool)`; they see only the `Observation`.
   The compared set ("the five policies") is `NoReaction`, `AlwaysSubstitute`,
   `FullResolve(subst=False)`, `FullResolve(subst=True)`, `StableResolve(subst=True)`.
7. **Feasibility checks** (`realised.py`): with substitutions, no worker is in two crews on the
   same day, nobody works while absent, crew size never exceeds `M_j`, role capacities hold
   every day; every RESEQ plan passes `validate_residual` (assert in debug/test mode, counted in
   the result otherwise).
8. **Tests**:
   - SUBST on a paused one-person activity: substitute works the same day, `h_j` added,
     replaced worker idle after return; SUBST on a running partial crew raises `ρ_j`; SUBST
     with a non-idle or wrong-role worker is rejected and the run continues;
   - `AlwaysSubstitute` with no idle worker changes nothing;
   - residual SGS and CP-SAT plans are feasible on random planning views (property test, ≥ 50
     views from J30/`tiny.sm` runs); CP-SAT makespan ≤ SGS makespan;
   - with `X ≡ 1` and no disruptions, FullResolve and StableResolve on the CP-SAT baseline of
     `tiny.sm` reproduce makespan 7; StableResolve keeps every start unchanged;
   - StableResolve deviation ≤ FullResolve deviation on the same planning view, with equal
     makespan;
   - determinism (same seed → identical result for each policy) and CRN (absence onsets
     identical across all five policies for one seed);
   - operations behave identically in a resumed rollout and in the world (perfect-information
     rollout of a run that used SUBST and RESEQ reproduces its makespan);
   - `@pytest.mark.data`: 20 J30 + 10 J60 instances × 3 seeds × the four reactive policies at
     `λ_A = 0.01`, all
     realised schedules pass the checks of task 7.
9. **Measurements** (report): mean and p95 wall time per run for each policy (J30, J60,
   `λ_A = 0.01`, 20 instances × 3 seeds); mean decision time per epoch; CP-SAT fallback rate;
   and a first look (not a study): on-time share at `δ_D = 0.2` and mean realised deviation
   per policy on those runs.
10. `wp-report` (`docs/reports/WP4a.md`, `docs/notes/WP4a.md` with the planning view and the
    operation semantics as implemented). ADR for the residual-problem representation.
</task>

<constraints>
- No OVERTIME, SHIFT or DESCOPE yet (WP5). No permission gate yet.
- Policies see only the `Observation`; no hidden state.
- CRN intact; the NoReaction results of WP2b must not change (the WP3a regression test passes).
- No new runtime dependencies.
- Commit after each completed step group.
</constraints>

<acceptance_criteria>
1. Spec v1.5 and the formatting chore are separate commits.
2. Quality gate and `-m data` pass; all task-8 tests exist and pass; engine regression passes.
3. Measurements reported; NoReaction timing within 5 % of WP3a.
4. ADR for the residual representation.
5. Report, notes, roadmap (`WP4: in progress: WP4a done`); pushed; clean tree.
</acceptance_criteria>

<report_format>
`docs/reports/WP4a.md` via `wp-report`. "Numbers": timing table per policy, residual SGS and
CP-SAT times, fallback rate, the first-look table, and a duration estimate for a study of
480 instances × 2 sets × 4 `λ_A` × 4 replications × 5 policies on 4 workers.
</report_format>
