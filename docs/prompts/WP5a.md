# WP5a — Sentinel core: overtime, candidates, rollout evaluation and the decision rule

Fresh session (`/clear`). Read before coding:

<context>
- `CLAUDE.md`, `docs/spec/model.md` (v1.6: §1.2, §3, §3.1, §4, §4.1, §5, §5.1, §6, §7, §7.1,
  §8), `docs/spec/architecture.md`, `docs/experiments/plan.md`
- `docs/reports/WP3a.md`, `docs/reports/WP4a.md`, `docs/reports/WP4b.md`, `docs/notes/WP4a.md`,
  ADR-0009, ADR-0012
- `results/wp4/20261021-152439-8892ea21/summary.md` (baseline study, pooled tables only)
- skills `spec-guard`, `adr`, `wp-report`

This WP builds the agent itself (goal B): a one-step **rollout policy** (Bertsekas et al. 1997)
on the base policy NoReaction. At a decision epoch Sentinel generates candidate actions, imagines
each one in the same `N` sampled worlds (WP3 beliefs, common random numbers), and picks by the
lexicographic goal rule of §6. WP5b adds the permission gate, deferral, the simulated human,
DESCOPE and the study runner; WP6 adds LLM-proposed candidates.

What the baseline study (WP4b, 120 instances per set, R = 4, δ_D = 0.2) shows, and why this
design: FullResolve is the best classical policy, +4.3 pp on time (J30) and +6.7 pp (J60) over
NoReaction, at the price of 150–530 plan changes per run; substituting blindly gains nothing
(−0.4 / −0.1 pp); even the best baseline is on time in only 31–34 % of runs. WP2 showed that
work increases and new activities cause more delay than absences, and no baseline can add
capacity. Sentinel therefore gets three levers the baselines lack: *selective* substitution
(only where the imagined gain beats onboarding), re-planning only when it pays for its
instability, and **overtime** — a budget-for-deadline trade.

Answers to the WP4b spec questions (binding): (1) realised deviation divides by the number of
activities with `p_j > 0` — accepted; (2) a return to no crew is an epoch — accepted.

The decisions below are binding.
</context>

<task>
0. **Spec v1.7** (commit `spec: Sentinel core, overtime and candidates (v1.7)`):
   - §4 **OVERTIME(k, u, H)** made precise: hires `u ≤ floor(γ R_k)` *temporary workers* of
     role `k` (overtime/agency capacity), present every day of the window `[t, t + H)`, never
     absent, idle until assigned. During the window they can be dispatched or used in SUBST like
     any idle worker (SUBST onboarding applies; starting a new activity has no onboarding). A
     temporary worker assigned to a crew stays until that activity completes; after the window
     it takes no new assignment and leaves when idle. Cost `c_OT_k = 1.5 c_k` per temporary
     worker and day while hired (window days, plus any days after the window while still in a
     crew). Temporary workers have ids after the original workers; they have no absence stream
     (CRN of the original workers unchanged).
   - §4 **SHIFT**: the order-preserving repair — residual SGS (§4.1) with the current plan's
     planned starts as priority list (ties by id). Level 0. It may start activities earlier
     than the current plan (left-justification under the railway rule) and never changes the
     order of planned starts.
   - §6 candidates `C(s_t)`, at most these (each filtered for validity):
     `NOOP`; `SHIFT`; `RESEQ-M` (CP-SAT, minimum residual makespan); `RESEQ-S` (minimum
     deviation subject to residual makespan ≤ that of SHIFT); `SUBST(j)` for the up to 3 most
     urgent eligible activities; `SUBST-ALL` (every eligible substitution, AlwaysSubstitute
     order); `SUBST-ALL + RESEQ-M`; `OT(k*) + RESEQ-M` with `k*` the most backlogged role,
     `u = floor(γ R_k*)`, `H = 2 T_r`; where backlog of role `k` = `Σ r_jk · p_j / R_k` over
     unstarted and paused activities with `LS_j ≤ t + 2 T_r` (nominal durations). RESEQ plans
     with added capacity use the planning view extended by the temporary workers.
   - §6 **evaluation**: each candidate is applied at step 3 of day `t` in every rollout; the
     rollout then continues under NoReaction (WP3 machinery, rollout `i` seed `ξ_i` shared by
     all candidates). **Racing**: stage 1 evaluates every candidate on `N₁ = 50` rollouts;
     candidates whose capped on-time estimate is below the best by more than 2 paired standard
     errors are dropped; stage 2 extends the survivors to `N = 200`. Ties and the lexicographic
     order exactly as in §6 (`min(p̂, θ_D)`, then `−o`, then `−Δ`, then `−ℓ`); `ẑ` is mean total
     project cost including cost so far; `Δ` from the candidate's plan against the current plan
     over the §7.1 deviation set plus `κ_h · n_subst`.
   - §5 **needs gate**: NOOP is evaluated first (`N₁` rollouts, then up to `N`); if
     `n_D ≤ ε_D` and `n_B ≤ ε_B`, return NOOP without generating candidates.
   - §6 **deliberation epochs**: Sentinel deliberates at decision epochs that have an event
     touching a crew (absence onset or return of a crew member, D2, D3) and at periodic epochs;
     at epochs whose only events concern idle workers it returns NOOP. (The agent's own choice
     of when to think; record it.)
   - §8: `c_OT_k = 1.5 c_k`, `N₁ = 50`, `H = 2 T_r`, max 3 single-activity SUBST candidates.
1. **Engine**: OVERTIME with temporary workers and SHIFT as operations (discriminated union),
   shared by the world and resumed rollouts; result records hires, temporary worker-days and
   overtime cost. Feasibility checks of `realised.py` extended (temporary workers counted only
   while hired, never absent). NoReaction makespans unchanged (regression test).
2. **Candidate generation** `src/sentinel/agent/candidates.py`: `generate(observation, plan,
   params) -> list[Candidate]` (operations, level `ℓ`, plan for `Δ`, label); CP-SAT with
   `T_cp`, hint and SGS fallback as in WP4; SHIFT and the SUBST variants cheap.
3. **Evaluator** `src/sentinel/agent/evaluate.py`: racing evaluation of candidates on shared
   sampled worlds; returns per candidate `p̂`, its paired SE vs the best, `ẑ`, `o`, `Δ`, `ℓ`,
   rollouts used. Reuse beliefs, rollout streams and `Run.resume` (no duplicate engine logic).
   Sample each world once per epoch and reuse it for all candidates.
4. **Decision rule** `src/sentinel/agent/decide.py`: lexicographic rule with paired-SE ties,
   plus the scalarised ablation `U_a = p̂_a − λ_B o_a − λ_Δ Δ_a` (`λ_B = 1`, `λ_Δ = 0.01` per
   day; parameters in config) — returns the choice and a structured **decision record**
   (epoch, needs, candidates with their statistics, chosen action, reason) for the later
   explanation layer (WP6) and the dashboard (WP8).
5. **Policy** `src/sentinel/policies/sentinel.py`: `Sentinel(params)` with variants via
   params: `full`, `no_overtime` (fair comparison with the baselines), `scalarised`. Full
   autonomy in WP5a (every action applies; the gate comes in WP5b). It sees only the
   `Observation`; its internal RNG seed derives from the run seed and the day
   (`derive_seed(seed, "sentinel", str(t))`), so runs are deterministic and CRN with other
   policies holds for exogenous events.
6. **Tests**:
   - OVERTIME: temporary workers appear for `H` days, can be dispatched and substituted, stay
     in their crew after the window, cost `1.5 c_k` per day, never absent; absence events of
     original workers are identical with and without overtime for the same seed;
   - SHIFT never changes the order of planned starts and never yields a later residual
     makespan than the current plan's SGS decode;
   - candidate generator on a planning view: all candidates valid; SUBST candidates only for
     eligible activities; at most the configured numbers;
   - evaluator: with one candidate equal to NOOP twice (duplicated), both get identical
     statistics (CRN); racing never drops the best-by-`N` candidate on a constructed case;
   - decision rule on hand-made statistics: cap at `θ_D`, SE ties, budget then stability then
     level;
   - Sentinel is deterministic per seed; `no_overtime` never hires;
   - a world run with Sentinel passes all feasibility checks; perfect-information rollout of
     a Sentinel run that used OT, SUBST and RESEQ reproduces its makespan;
   - `@pytest.mark.slow` data test: 5 J30 instances × 2 seeds, Sentinel `full`.
7. **Measurements** (report; `scripts/bench_sentinel.py`): per set (J30, J60), 20 spread
   instances × 3 WP2b seeds, `λ_A = 0.01`: mean and p95 deliberation time, deliberations and
   NOOP-gate exits per run, candidates and rollouts per deliberation, time per run; profile the
   top hotspots. Targets: mean deliberation ≤ 1.5 s (J30) and ≤ 3 s (J60). If missed, implement
   cheap wins (vectorisation, avoiding re-sampling, skipping traces) and report the gap.
8. **First look** (not a study; same runs, plus the WP4b policies on the same worlds from the
   bench script): on time (δ_D = 0.2, 0.3), C/C*, realised deviation, nervousness, cost / B,
   overtime cost share, substitutions, and how often each candidate type was chosen — for
   Sentinel `full`, `no_overtime`, NoReaction and FullResolve.
9. **Duration estimate** for the RQ4 study on the plan's subset (120 + 120 instances,
   4 `λ_A`, R = 4) for Sentinel `full` and `no_overtime` on 4 workers.
10. `wp-report` (`docs/reports/WP5a.md`, `docs/notes/WP5a.md`: agent architecture, candidate
    list, racing, decision record format). ADRs for the agent package layout and the racing
    procedure.
</task>

<constraints>
- No permission gate, deferral, simulated human or DESCOPE (WP5b). No LLM (WP6).
- The agent sees only the `Observation`; hidden state only via the explicit test hook.
- CRN intact; NoReaction makespans bit-identical to WP2b (regression test).
- No new runtime dependencies. Commit after each completed step group.
- Anything longer than ~10 minutes goes to the owner as a tmux command.
</constraints>

<acceptance_criteria>
1. Spec v1.7 commit.
2. Quality gate (default `pytest -q` ≤ 90 s) and `-m "data or slow"` pass; all task-6 tests
   exist and pass.
3. Measurements, first look and duration estimate reported; deliberation targets met or a
   profile plus plan.
4. ADRs for the package layout and racing.
5. Report, notes, roadmap (`WP5: in progress: WP5a done`); pushed; clean tree.
</acceptance_criteria>

<report_format>
`docs/reports/WP5a.md` via `wp-report`. "Numbers": timing table, first-look table, chosen-action
frequencies, duration estimate.
</report_format>
