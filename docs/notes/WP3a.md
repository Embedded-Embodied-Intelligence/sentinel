# WP3a notes — beliefs, mid-project rollouts and the forecaster

**Scenario selection** (`docs/experiments/plan.md`, from WP2b run `20261020-181559-6534a712`).
Primary grid δ_D = 0.2, λ_A ∈ {0, 0.005, 0.01, 0.02}, E[L] = 3, λ_S = 0.01, λ_N = 0.02, where
NoReaction is on time in 11–51 % of runs. Sensitivity runs use δ_D = 0.3 and E[L] = 5. δ_D = 0.1
is excluded: NoReaction is on time in only 2.3–21.2 % of runs for λ_A ≤ 0.01.

**Duration pmf** (`forecasting/durations.py`, spec §2.1, §5.1). P_j = max(1, round(p_j X)) with
X = a + (b − a) B, B ~ Beta(α, β), α = 1 + λ(m − a)/(b − a), β = 1 + λ(b − m)/(b − a) (Malcolm
et al. 1959). Value k collects p_j X ∈ (k − ½, k + ½); k = 1 also collects p_j X < ½. For integer
shapes, the default α = 2 and β = 4 included, the Beta CDF is the closed form
I_x(α, β) = Σ_{k=α}^{α+β−1} C(α+β−1, k) x^k (1 − x)^{α+β−1−k}. Upper bins use the complement for
accuracy. Other shapes use composite Simpson with 20,000 intervals per bin. The tests check
the mean against 10⁶ draws of the sampler (within 0.01) for p ∈ {1, 3, 10} with both methods.

**Belief** (`forecasting/beliefs.py`, §5.1). Unstarted activities sample P_j from the pmf; D3
activities use their nominal duration as p_j. A started activity with work e_j and observed
shocks (e_i, F_i) replays R_0 = P_j, R_i = (R_{i−1} − (e_i − e_{i−1})) F_i and needs
R_m − (e_j − e_m) > 0. Every F ≥ 1, so this keeps a top range of P_j values, and P_j is drawn by
inverse CDF from the renormalised tail. If no value remains (only possible when the observation
contradicts the prior), one crew-member day is left and counted as a fallback; no fallback
occurred in 320 forecasts. An absent worker has posterior L ∝ q(1 − q)^{L−1} · 1/L on
max(L_low, t − s + 1) ≤ L ≤ 365. This is the geometric prior times the likelihood of a uniform
announcement; for L_low = 1 and t = s its mean is (1 − q)/(−q ln q) ≈ 1.82 at E[L] = 3. All
posteriors are computed once per observation, so a sample needs one uniform per activity and
per worker.

**Mid-project rollouts** (`simulation/engine.py`, `simulation/state.py`). The day loop is a `Run`
with `open_day` (steps 1–3) and `close_day` (steps 4–6). An observation describes step 3 of day
t. `state_from_observation(observation, world)` rebuilds the engine state from it and a sampled
world: statuses, crews with their present members and rates, idle workers, eligibility, inserted
activities, and return days. The rollout then closes day t and runs days t + 1, … under
NoReaction until the sink completes or max_days = 5 D. Verification:
- 50 recorded runs of `simulate` are unchanged bit for bit after the refactor.
- A rebuilt state equals the true one field by field.
- With the world's own streams, a rebuilt state finishes exactly like the world.
- With the true hidden state and no future disruptions, every rollout reproduces the true
  makespan.

**Rollout random layout** (`forecasting/streams.py`, ADR-0009). Each process jumps from event to
event with geometric gaps G = 1 + ⌊ln(1 − u)/ln(1 − p)⌋, the waiting time of a Bernoulli
sequence, so the distributions are those of §2.2:
- D1 per worker: draws resume on day t + 1, or the day after a sampled return.
- D2 per original activity: work days are counted from the rollout start.
- D3 per day: arrivals start on day t + 1.
Draws come in blocks over all workers or activities, so the k-th event of a worker or activity
reads the same uniforms for every candidate plan. Rollout i uses
ξ_i = derive_seed(seed, "rollout", i) for its belief sample and its future (rollout CRN, §5.1).
From day 0, 2000 rollouts and 2000 world runs differ in mean makespan by −0.38 % to +0.37 % on
four instances, and in P(C ≤ D) by at most 0.014.

**Forecast** (`forecasting/forecast.py`): makespan samples, P(C ≤ D), the inverted-CDF 10/50/90 %
quantiles, the mean, fallbacks and wall time. 200 rollouts take 0.24 s on J30 and 0.35 s on J60
on average (i5-6600K, one process), 0.19–0.45 s depending on the day. 75 % of the time is the
day loop and 14 % rebuilding states.

**References.** Malcolm et al. 1959 (PERT); Bertsekas, Tsitsiklis & Wu 1997 (rollouts on a base
policy); common random numbers as in WP2 (§2.3).
