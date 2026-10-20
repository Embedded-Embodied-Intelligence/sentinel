# WP3a — Beliefs, mid-project rollouts and the Monte Carlo forecaster

Fresh session (`/clear`). Read before coding:

<context>
- `CLAUDE.md`, `docs/spec/model.md` (v1.3: §2, §2.3, §3, §3.1, §5, §6, §8),
  `docs/spec/architecture.md`
- `docs/reports/WP2a.md`, `docs/reports/WP2a.1.md`, `docs/reports/WP2b.md`,
  `docs/notes/WP2a.md`, ADR-0007 and ADR-0008
- `results/wp2/20261020-181559-6534a712/summary.md` (the full NoReaction study)
- skills `spec-guard`, `adr`, `experiment-run`, `wp-report`

WP3 gives Sentinel its "imagination": from what the agent can observe at day `t`
(`Observation`), sample the hidden quantities (true remaining work, true absence lengths) and
future disruptions, simulate the rest of the project many times, and report the distribution of
the makespan and `P(C ≤ D)`. WP3a builds and validates this machinery; WP3b measures its
calibration (RQ3). WP5 will reuse exactly the same rollouts to evaluate candidate actions, so
correctness, CRN and speed matter.

The architect's decisions below are binding.
</context>

<task>
0. **Experiment plan and spec v1.4** (two separate commits).
   a. Create `docs/experiments/plan.md` recording the scenario selection made from the WP2b
      study: primary grid `δ_D = 0.2`, `λ_A ∈ {0, 0.005, 0.01, 0.02}`, `E[L] = 3`,
      `λ_S = 0.01`, `λ_N = 0.02`; sensitivity `δ_D = 0.3` and `E[L] = 5`; `δ_D = 0.1`
      excluded because NoReaction is on time in only 2–21 % of runs there (quote the WP2b
      numbers with the run id). Commit `docs: experiment plan from the WP2b study`.
   b. `docs/spec/model.md` → v1.4 (commit `spec: beliefs and rollouts (v1.4)`), adding a new
      §5.1 **Beliefs** and amending §5/§6 as follows:
      - Durations: the pmf of `P_j` is the distribution of the existing sampler of §2.1
        (`P_j = 0` if `p_j = 0`, else `max(1, round(p_j · X))`, `X ~ PERT`; ties have
        probability zero); work is measured in full-crew days (v1.3), `e_j` included. For an
        activity with observed work and shocks
        `(e_1, F_1), …, (e_m, F_m)` (work done at each shock, factor), the belief samples
        `P_j` from this pmf conditioned on the activity not being finished: with
        `R_0 = P_j`, `R_i = (R_{i-1} − (e_i − e_{i-1})) · F_i` (`e_0 = 0`), require
        `R_i > 0` for all shocks and current remaining `R_m − (e_j − e_m) > 0`; the sampled
        remaining work is that last value. Unstarted original activities sample `P_j` from the
        unconditional pmf; inserted activities use their nominal duration as `p_j`.
      - Absences: for an absent worker with absence start `s`, announced bound `L_low`, today
        `t`, the posterior of `L` is `∝ q(1−q)^{L−1} · (1/L)` (geometric prior with
        `q = 1/E[L]`, likelihood of a uniform announcement) on
        `L ≥ max(L_low, t − s + 1)`, truncated at `L ≤ 365`. Return day `s + L`.
      - Future: disruptions after day `t` follow the priors of §2.2 with fresh random numbers.
      - Rollout: from a sampled state, the remaining project is simulated with the base policy
        `NoReaction` (§6) exactly by the engine semantics of §3/§3.1.
      - §5 urgency: for unstarted and paused activities `τ_j = LS_j − t`; for running
        activities `τ_j = LF_j − t − E[remaining_j]` under the belief; `τ_t = min_j τ_j`.
      - §6 candidates: SUBST candidates exist for paused activities and for running
        activities with absent members (v1.3 rule).
      - Rollout CRN: rollout `i` uses seed `ξ_i` for both the belief sample and the future, so
        every candidate sees the same `N` sampled worlds.
1. **Duration pmf** `src/sentinel/forecasting/durations.py`: exact pmf of `P_j` for given
   `p_j` and `PertParams` without scipy. For integer `α, β` (the default `α = 2, β = 4`) use the
   closed-form regularised incomplete beta `I_x(α, β) = Σ_{k=α}^{α+β−1} C(α+β−1, k) x^k
   (1−x)^{α+β−1−k}`; otherwise integrate the Beta density numerically (composite Simpson,
   ≥ 20 000 intervals). Cache per `(p_j, params)`. Sample conditionals by inverse CDF.
2. **Beliefs** `src/sentinel/forecasting/beliefs.py`: `sample_world(observation, rng)
   -> SampledWorld` implementing §5.1 (remaining work per started activity, `P_j` for unstarted
   ones, return day per absent worker). If a duration condition has zero probability under the
   prior (possible after large shocks), fall back to the smallest feasible remaining work
   (one crew-member day, i.e. `1 / M_j` full-crew days) and count these fallbacks. The shocks
   come from `Observation.work_increases` = (activity, `e_j` before the shock, `F`).
3. **Mid-project start in the engine.** Refactor `simulate` into state initialisation plus a
   run loop that can start from a given `EngineState` at day `t + 1`, without changing any
   result of the existing API (all WP2 tests must pass unchanged; add a regression test that
   compares 50 full runs before/after the refactor bit for bit). Add
   `state_from_observation(observation, world) -> EngineState`.
4. **Rollout streams.** Rollouts may use a faster, vectorised random layout than the "world"
   streams of §2.3 (e.g. draw the absence matrix for all workers and the remaining horizon in
   one call), provided that (i) the same rollout seed gives bit-identical rollouts regardless of
   which candidate plan is simulated, wherever the event does not depend on the state, and (ii)
   the event distributions equal §2.2. Record the layout in an ADR. The true-world simulator
   keeps the §2.3 layout.
5. **Forecaster** `src/sentinel/forecasting/forecast.py`:
   `forecast(observation, plan, *, n_rollouts, seed, include_future_disruptions=True)
   -> Forecast` with makespan samples, `p_on_time(deadline)`, quantiles (10/50/90 %), mean,
   number of fallbacks and wall time. Rollout `i` uses seed `derive_seed(seed, "rollout",
   str(i))`.
6. **Tests**:
   - pmf sums to 1; its mean matches `E[P_j]` from 10^6 samples of the existing sampler within
     0.01; conditional sampling never returns `P_j ≤ e_j`.
   - absence posterior: support starts at `max(L_low, t − s + 1)`; with `L_low = 1` and
     `t = s` it equals the size-biased-then-truncated geometric (check normalisation and mean
     against direct enumeration).
   - perfect-information check: if the forecaster is given the true hidden state (test hook)
     and future disruptions are off in both world and forecast, every rollout reproduces the
     true remaining makespan exactly.
   - at day 0 with no events yet, the forecast's mean makespan (`n_rollouts = 2000`) agrees
     with the mean of 2 000 true-world NoReaction runs on the same instance within 2 % (J30
     instance, primary scenario `λ_A = 0.01`); this checks that the rollout random layout has
     the §2.2 distributions. Mark it `@pytest.mark.data` if it needs PSPLIB and keep it < 60 s.
   - CRN: two forecasts with the same seed but different plans share identical absence
     samples.
   - observations never expose hidden fields (existing test still passes).
7. **Speed** (report): wall time of `forecast` with `n_rollouts = 100` and `200` at days
   0 %, 25 %, 50 %, 75 % of the planned makespan, on 20 J30 and 20 J60 instances, primary
   scenario `λ_A = 0.01`. Targets: J30 `n = 200` ≤ 1.0 s mean, J60 ≤ 2.0 s mean. If missed,
   profile and implement the cheap wins (vectorised streams, skipping trace and validation in
   rollouts, reusing the pmf cache); report the remaining gap and a plan.
8. Finish with `wp-report` (`docs/reports/WP3a.md`, `docs/notes/WP3a.md`).
</task>

<constraints>
- The forecaster sees only the `Observation` (plus the instance and priors it contains); add a
  test that `forecast` cannot be called with hidden state except through the explicit test hook.
- No policy beyond NoReaction; no candidate generation (WP5).
- No new runtime dependencies.
- Commit after each completed step group so a partial session leaves a consistent history.
</constraints>

<acceptance_criteria>
1. Commits for `plan.md` and spec v1.4 present.
2. Quality gate and `-m data` pass; all task-6 tests exist and pass; the refactor regression
   test passes.
3. Speed table reported; targets met or a profile plus plan given.
4. ADR for the rollout random layout.
5. Report, notes, roadmap (`WP3: in progress: WP3a done`); pushed; clean tree.
</acceptance_criteria>

<report_format>
`docs/reports/WP3a.md` via `wp-report`. "Numbers": speed table, day-0 agreement test values,
fallback counts observed in the speed runs.
</report_format>
