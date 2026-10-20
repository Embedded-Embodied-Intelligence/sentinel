# WP3b notes — calibration of the Monte Carlo forecasts (RQ3)

**Design** (spec §5.2, ADR-0010). NoReaction worlds run the `cpsat_det` baseline plan of each
instance: J30 and J60, all 480 instances (misspecification study: J30 every 4th, 120). The
primary grid is λ_A ∈ {0, 0.005, 0.01, 0.02}, E[L] = 3, λ_S = 0.01, λ_N = 0.02, with R = 4
replications. Replication r uses the WP2b seed derive_seed(2026, set, instance, r) in every
scenario, and max_days = 5 D(0.3). Every summary checks the worlds' seeds and makespans
against the WP2b results; the smoke runs and a 320-world sample matched them all. The world
records its step-3 observation on the checkpoint days t_f = floor(f · C_plan),
f ∈ {0, 0.2, 0.4, 0.6, 0.8}. Recording leaves the run unchanged (tested field by field). A
checkpoint with C ≤ t_f is skipped. All forecasters of a checkpoint share the seed
derive_seed(2026, "forecast", set, instance, scenario, r, f). Inside a Monte Carlo forecast,
rollout i uses ξ_i for both its belief sample and its future, so mc_full and mc_no_future
share their sampled hidden states.

**Forecasters.**
- `mc_full`: 200 NoReaction rollouts from belief samples (§5.1).
- `mc_no_future`: the same samples without disruptions after t_f.
- `deterministic`: one NoReaction run from the nominal state, as a classical PM tool shows it:
  - unstarted activities have their nominal p_j;
  - a started activity keeps p_j − e_j, at least one crew-member day, multiplied by F at each
    observed D2 shock (the floor is applied before every shock);
  - absent workers return on day s + max(L_low, t − s + 1).
  It gives a point mass, so P(C ≤ D) ∈ {0, 1}.
- Misspecified priors: `mc_full` with (λ_A, λ_S, λ_N) × κ, κ ∈ {0.5, 1, 2}, or with PERT
  (0.7, 1, 2.0), λ = 4, in both the belief and the future. E[L] and the D2 factor range keep
  their true values.

**Scores as implemented** (`forecasting/metrics.py`, `experiments/forecast_summary.py`).
- The binary event is y = 1[C ≤ D] with D = ceil((1 + δ_D) C*); a truncated world is late.
  δ_D ∈ {0.2, 0.3} are scored from the same samples.
- Brier score BS = mean (p − y)² (Brier 1950). The Murphy (1973) decomposition uses K = 10
  bins [k/10, (k+1)/10), the last one closed. A p on an edge goes to the upper bin (tolerance
  10⁻⁹; p is a multiple of 1/200). REL = Σ n_k (p̄_k − ȳ_k)² / N, RES = Σ n_k (ȳ_k − ȳ)² / N,
  UNC = ȳ(1 − ȳ). The reported binning error BS − (REL − RES + UNC) equals the within-bin
  variance minus twice the within-bin covariance (tested to 10⁻¹²).
- ECE = Σ (n_k / N) |p̄_k − ȳ_k|. Sharpness = population variance of p. Log score =
  −mean[y ln p' + (1 − y) ln(1 − p')] with p' clipped to [0.005, 0.995] (natural log; lower
  is better).
- CRPS of the empirical CDF of the n samples x_i (Gneiting & Raftery 2007):
  (1/n) Σ |x_i − C| − (1/n²) Σ_i (2i − n − 1) x_(i), with x sorted. For integer samples it
  equals Σ_z (F(z) − 1[z ≥ C])² over the integers. A point mass gives |Ĉ − C|. Reported as
  CRPS / C*, with the median error |q_0.5 − C| / C*.
- Quantiles come from the inverted empirical CDF (numpy `inverted_cdf`). The 80 % coverage
  counts q_0.1 ≤ C ≤ q_0.9, both ends included; the summary also reports the width
  (q_0.9 − q_0.1) / C*.
- Randomised PIT u = F(C − 1) + V (F(C) − F(C − 1)) (Czado, Gneiting & Held 2009). V is drawn
  once per row in file order from seed 2026; histograms use 10 bins.
- Early warning, θ ∈ {0.5, 0.8}. A run (one world seen by one forecaster) is warned at its
  first non-skipped checkpoint with p < θ, on day t_w. Reported: the share of late runs warned,
  the mean lead time D − t_w over warned late runs, and the false-alarm share of on-time runs.
- Intervals: a cluster bootstrap over the instances of a set (Davison & Hinkley 1997, §3.8),
  with 1,000 resamples. The resample matrix comes from seed derive_seed(2026, "bootstrap",
  set) and is shared by every statistic. Each statistic is a ratio of per-instance sums, so a
  resample recomputes it exactly. Paired differences are ratios of per-instance sums of
  differences. The 95 % percentile intervals ignore undefined replicates.

**Smoke runs** (5 instances per set, parameter group 1 only, so not results). Pooled over
checkpoints and λ_A at δ_D = 0.2, mc_full had Brier 0.154 (J30) and 0.166 (J60). The
deterministic estimate had 0.555 and 0.522, and mc_no_future 0.413 and 0.359. mc_full's 80 %
interval covered 78 % and 82 % of the outcomes. The misspecified priors behaved as expected:
κ = 0.5 put the PIT mass near 1 (makespans underestimated), κ = 2 near 0 (overestimated).
