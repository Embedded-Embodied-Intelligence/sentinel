# WP3b.1 notes — forecast summaries: early warning, discrimination and skill

**Early warning and plan-stage risk** (spec §5.2, v1.4.2).
- A run (one world seen by one forecaster) is warned at its first non-skipped checkpoint with
  f ≥ 0.2 and p < θ, θ ∈ {0.5, 0.8}. The lead time is D − t_w.
- f = 0 is reported separately as plan-stage risk: the shares of late and of on-time runs with
  p < θ on day 0.
- Reason: at δ_D = 0.2, 70 % (J30) and 72 % (J60) of the worlds are late. A calibrated day-0
  forecast sits near that base rate, so under v1.4.1 `mc_full` "warned" 68 % / 62 % of the
  on-time runs at θ = 0.5.
- With f ≥ 0.2 this falls only to 57 % / 52 %. At δ_D = 0.3 (47 % late) it is 24 % / 19 %,
  with 85–87 % of the late runs warned.

**Skill and discrimination.**
- BSS = 1 − BS / UNC (Murphy 1988), with UNC = ȳ(1 − ȳ) of the same cell (set, f, λ_A). The
  reference knows the cell's on-time frequency, so the score is in-sample and favours the
  reference.
- AUC in the Mann–Whitney form: the share of (on-time, late) forecast pairs in which the
  on-time one has the higher p, ties counting ½ (Hanley & McNeil 1982). AUC measures ranking
  only. A point mass (`deterministic`, p ∈ {0, 1}) gives (1 + TPR − FPR) / 2, hence 0.50 at
  f = 0, when it nearly always says p = 1.

**Coverage.**
- The quantile interval [q_0.1, q_0.9] includes both bounds with their whole mass. A
  calibrated integer forecast therefore covers C with probability F(q_0.9) − F(q_0.1 − 1) > 0.8;
  for Poisson(4) this is [2, 7] and 0.857.
- PIT coverage, the share of randomised PIT values in [0.1, 0.9], is exactly 0.8 when the
  forecast is calibrated (Czado et al. 2009).
- `mc_full`: quantile coverage 0.81–0.85, PIT coverage 0.79–0.81. Every PIT interval contains
  0.8.

**Intervals.**
- Cluster bootstrap over instances, as in WP3b (1,000 resamples).
- BSS uses the resampled Brier score and UNC.
- AUC uses the per-instance counts of on-time and late forecasts per distinct p, weighted by
  the cluster multiplicities. This equals the AUC of the replicated rows, pairs across copies
  of an instance included.

**References in the misspecification study.**
- Its worlds and forecast seeds equal the main run's. The `mc_no_future` and `deterministic`
  rows of the same (set, instance, scenario, replication, f) are therefore added to its tables
  after a check: 4,800 rows, 0 seed and 0 makespan mismatches.
- `mc_k1` equals main `mc_full` on all 2,400 shared checkpoints.

**Results to quote** (δ_D = 0.2, f = 0 → 0.8):
- `mc_full`:
  - Brier 0.174 → 0.096 (J30) and 0.149 → 0.086 (J60);
  - BSS 0.17 → 0.54 and 0.26 → 0.57;
  - AUC 0.76 → 0.93 and 0.83 → 0.94;
  - ECE ≤ 0.015 at all three shares.
- `deterministic`: BSS −2.3 (J30) and −2.5 (J60) → −0.4, AUC 0.50 → 0.78–0.80, with 1 % false
  alarms but only 59–61 % of the late runs warned.
- Misspecified priors: AUC 0.83–0.85 for every variant, so misspecification hurts calibration,
  not ranking. ΔBrier against κ = 1 is +0.041 (κ = 0.5), +0.028 (κ = 2) and +0.012 (wide PERT).

**Headline table** (`table_wp3_headline.tex`):
- Set, f ∈ {0, 0.4, 0.8} and forecaster, with Brier, BSS, ECE, AUC, CRPS / C* and PIT coverage.
- The intervals of Brier, AUC and CRPS / C* are in a second `\scriptsize` row.
- 9 columns with `\tabcolsep` = 3 pt: about 115 mm with `\small`, inside the 122 mm LNCS text
  width (estimated from Computer Modern metrics).
