# WP2b notes — baseline plans and the NoReaction scenario study

**Baseline plans** (`simulation/baselines.py`, ADR-0008). Every policy starts from the `cpsat_det`
plan: the WP1 CP-SAT model (one interval per activity, one cumulative per role, minimise S_{n+1},
horizon = SGS-LFT makespan, no hints) with one worker, seed 2026 and `max_deterministic_time = 5`
without a wall-clock limit, so the plan does not depend on machine load. One deterministic unit
took 2.1–2.7 s on the i5-6600K with four parallel solves. `sgs_lft` (serial SGS with the LFT rule;
Kolisch 1996) remains available. Plans are cached in `data/derived/baselines/<set>/<instance>.json`
and reused only if method parameters, instance SHA-256, cache version and OR-Tools version match.
All 960 plans took 40 s (J30) and 4.2 min (J60) with 4 workers. J30: 472 OPTIMAL, 8 stopped by
the limit, plan / C* mean 1.0002, 475 at the optimum. J60: 407 OPTIMAL, 73 stopped, mean 1.0081
(max 1.141), 417 at the best known makespan. WP1's CP-SAT 10 s: 1.0001 / 477 and 1.0085 / 417.

**Scenario grid** (`configs/wp2_noreaction.toml`). `durations_only` (PERT durations, no
disruptions) and λ_A ∈ {0, 0.0025, 0.005, 0.01, 0.02} × E[L] ∈ {3, 5} (only E[L] = 3 at λ_A = 0,
where it has no effect) with λ_S = 0.01, λ_N = 0.02: ten scenarios. PERT (0.8, 1.0, 1.6), λ = 4,
T_r = 5, c_k = 1, β = 0.10; all 480 + 480 instances, R = 20: 192,000 runs.

**Deadlines and cost.** C* = J30 `opt` or J60 `hrs`; D_δ = ceil((1 + δ) C*), δ ∈ {0.1, 0.2, 0.3}.
NoReaction never reads the deadline, so each run is simulated once with max_days = 5 D_0.3 and is
on time for δ iff not truncated and C ≤ D_δ, which equals a run with D_δ (a run truncated at 5 D_δ
also misses D_δ). B = 1.1 Σ c_k r_jk p̄_j covers the original activities; D3 work adds cost only.

**Common random numbers.** Replication r of an instance has the seed
`derive_seed(2026, set, instance, r)` (ADR-0006) in every scenario; the §2.3 child streams give
durations, absences per worker, D2 per activity and D3. All ten scenarios of one (instance, r)
share the true durations. In the nine with λ_S = 0.01 and λ_N = 0.02, an activity's D2 shocks
depend only on its own work days, and D3 days, templates and multipliers are identical up to the
end of the shorter run (the insertion point depends on the state). Absences for different λ_A or
E[L] come from the same per-worker streams.

**Checks.** Every baseline plan passes `validate_schedule`; every complete realised schedule passes
`validate_schedule` (segment-split instance) and `execution_violations`; truncated runs get the
crew checks. They cost about 1 ms per run (≈ 20 %).

**Measured** (i5-6600K, 4 workers). Baselines: J30 0.29 s per instance (median 0.011 s, max
10.9 s), J60 2.03 s (median 0.017 s, p95 12.1 s, max 16.5 s); limit-bound ones 8.9 s and 11.8 s.
Study: 548 runs/s on a spread sample of 80 instances (16,000 runs; `simulate` 4.1 ms J30, 6.9 ms
J60), so the full study takes about 6 min.

**Statistics.** P(on time) per (set, scenario) pools the 9,600 runs of a cell in a 95 % Wilson
interval (Wilson 1927); runs of one instance are correlated, so it understates the uncertainty
across instances (WP7: instance-clustered intervals). References: Kolisch 1996; Perron & Didier
(OR-Tools CP-SAT); Herroelen & Leus 2005; Van de Vonder et al. 2007; Wilson 1927, JASA 22(158).
