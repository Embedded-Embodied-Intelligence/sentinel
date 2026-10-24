# wp4_sensitivity: run 20261021-182437-f25fdded

Generated from `results.csv.gz` by `sentinel.experiments.policy_summary` at commit `d07a0992953fae5969eea0b5bfabe12d54b72c7b`; do not edit.

- Policies on `cpsat_det` baseline plans: NoReaction, AlwaysSubstitute, FullResolve, FullResolve(subst), StableResolve(subst). CP-SAT: T_cp = 0.1 deterministic s per stage, seed 0, one worker; T_r = 5.
- Instances: every 4th of J30 in natural order; 4 replications per instance with the WP2b seeds, shared by all policies and scenarios (common random numbers). Scenarios: λ_S = 0.01, λ_N = 0.02.
- On time for δ: C ≤ D = ceil((1 + δ) C*) (spec section 1.2), evaluated post hoc; truncated runs are late. In % with 95 % Wilson intervals over the runs of a cell, which understate the uncertainty across instances.
- Deviation: realised deviation from the baseline plan in days; nervousness: changes of a planned start in the deviation set per run (spec section 7.1); substitutions: replaced crew members per run; onboarding: crew-member days o_j per replaced member; cost / B with β = 0.1. Means per run.
- Paired differences against NoReaction on the same worlds (set, instance, scenario, replication), means over the runs with 95 % percentile intervals of a cluster bootstrap over the instances of a set (1000 resamples, seed 2026); on time in percentage points.
- WP2b seed check against `results/wp2/20261020-181559-6534a712/results.csv.gz`: 960 worlds compared, **0 makespan mismatches** (expected 0), 0 seed mismatches, 0 without a WP2b row.
- Checks: 0 rejected operations, 0 CP-SAT fallbacks in 269,702 stages, 2 truncated runs.

## J30 (C*: optimum, `opt`), 120 instances

| λ_A | E[L] | Policy | Runs | On time δ=0.2 [%] | On time δ=0.3 [%] | C / C* | Deviation [d] | Nervousness | Substitutions | Onboarding [d] / subst. | Handover [d] | Cost / B | RESEQs | Fallbacks | Epochs | s / run |
| ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.01 | 5 | NoReaction | 480 | 18.5 [15.3, 22.3] | 39.4 [35.1, 43.8] | 1.405 | 7.85 | 0.0 | 0.0 | -- | 0.0 | 1.039 | 0.0 | 0 | 66.8 | 0.006 |
| 0.01 | 5 | AlwaysSubstitute | 480 | 18.1 [14.9, 21.8] | 37.7 [33.5, 42.1] | 1.410 | 8.08 | 0.0 | 23.4 | 1.86 | 3.1 | 1.062 | 0.0 | 0 | 67.0 | 0.010 |
| 0.01 | 5 | FullResolve | 480 | 21.0 [17.6, 24.9] | 44.4 [40.0, 48.8] | 1.361 | 8.28 | 202.6 | 0.0 | -- | 0.0 | 1.037 | 60.3 | 0 | 64.7 | 1.019 |
| 0.01 | 5 | FullResolve(subst) | 480 | 21.2 [17.8, 25.1] | 43.3 [39.0, 47.8] | 1.369 | 8.58 | 209.4 | 23.4 | 1.86 | 3.1 | 1.059 | 60.8 | 0 | 65.2 | 1.036 |
| 0.01 | 5 | StableResolve(subst) | 480 | 20.4 [17.1, 24.3] | 43.5 [39.2, 48.0] | 1.371 | 8.29 | 179.8 | 23.2 | 1.87 | 3.1 | 1.059 | 60.7 | 0 | 65.2 | 1.804 |
| 0.02 | 5 | NoReaction | 480 | 8.3 [6.2, 11.1] | 22.3 [18.8, 26.2] | 1.504 | 10.07 | 0.0 | 0.0 | -- | 0.0 | 1.053 | 0.0 | 0 | 83.7 | 0.007 |
| 0.02 | 5 | AlwaysSubstitute | 480 | 9.4 [7.1, 12.3] | 22.1 [18.6, 26.0] | 1.528 | 10.69 | 0.0 | 48.6 | 2.01 | 7.3 | 1.099 | 0.0 | 0 | 85.1 | 0.019 |
| 0.02 | 5 | FullResolve | 480 | 10.6 [8.2, 13.7] | 28.5 [24.7, 32.7] | 1.444 | 10.36 | 278.8 | 0.0 | -- | 0.0 | 1.050 | 78.6 | 0 | 80.2 | 1.450 |
| 0.02 | 5 | FullResolve(subst) | 480 | 11.5 [8.9, 14.6] | 26.0 [22.3, 30.1] | 1.462 | 10.96 | 288.8 | 47.9 | 1.90 | 6.5 | 1.093 | 79.7 | 0 | 81.4 | 1.541 |
| 0.02 | 5 | StableResolve(subst) | 480 | 11.0 [8.5, 14.2] | 25.0 [21.3, 29.1] | 1.477 | 10.94 | 251.5 | 48.2 | 2.00 | 7.3 | 1.096 | 80.6 | 0 | 82.2 | 2.611 |
| all | -- | NoReaction | 960 | 13.4 [11.4, 15.7] | 30.8 [28.0, 33.8] | 1.455 | 8.96 | 0.0 | 0.0 | -- | 0.0 | 1.046 | 0.0 | 0 | 75.2 | 0.006 |
| all | -- | AlwaysSubstitute | 960 | 13.8 [11.7, 16.1] | 29.9 [27.1, 32.9] | 1.469 | 9.38 | 0.0 | 36.0 | 1.96 | 5.2 | 1.080 | 0.0 | 0 | 76.1 | 0.014 |
| all | -- | FullResolve | 960 | 15.8 [13.7, 18.3] | 36.5 [33.5, 39.6] | 1.402 | 9.32 | 240.7 | 0.0 | -- | 0.0 | 1.043 | 69.4 | 0 | 72.4 | 1.234 |
| all | -- | FullResolve(subst) | 960 | 16.4 [14.1, 18.8] | 34.7 [31.7, 37.8] | 1.416 | 9.77 | 249.1 | 35.7 | 1.89 | 4.8 | 1.076 | 70.2 | 0 | 73.3 | 1.288 |
| all | -- | StableResolve(subst) | 960 | 15.7 [13.6, 18.2] | 34.3 [31.3, 37.3] | 1.424 | 9.61 | 215.6 | 35.7 | 1.96 | 5.2 | 1.078 | 70.7 | 0 | 73.7 | 2.208 |

Paired differences against NoReaction:

| λ_A | E[L] | Policy | Pairs | Δ on time δ=0.2 [pp] | Δ on time δ=0.3 [pp] | Δ C / C* | Δ deviation [d] |
| ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 0.01 | 5 | AlwaysSubstitute | 480 | -0.4 [-2.1, 1.0] | -1.7 [-4.4, 0.8] | +0.005 [-0.001, 0.011] | +0.23 [0.14, 0.33] |
| 0.01 | 5 | FullResolve | 480 | +2.5 [0.0, 5.0] | +5.0 [1.5, 8.3] | -0.044 [-0.056, -0.032] | +0.43 [0.22, 0.64] |
| 0.01 | 5 | FullResolve(subst) | 480 | +2.7 [0.2, 5.0] | +4.0 [0.4, 7.3] | -0.036 [-0.047, -0.025] | +0.73 [0.49, 0.98] |
| 0.01 | 5 | StableResolve(subst) | 480 | +1.9 [-0.4, 4.2] | +4.2 [0.6, 7.5] | -0.034 [-0.045, -0.024] | +0.44 [0.24, 0.67] |
| 0.02 | 5 | AlwaysSubstitute | 480 | +1.0 [-0.8, 3.1] | -0.2 [-2.7, 2.3] | +0.024 [0.009, 0.048] | +0.62 [0.40, 0.89] |
| 0.02 | 5 | FullResolve | 480 | +2.3 [0.6, 4.0] | +6.2 [3.5, 8.8] | -0.060 [-0.073, -0.047] | +0.29 [0.09, 0.52] |
| 0.02 | 5 | FullResolve(subst) | 480 | +3.1 [0.8, 5.4] | +3.8 [0.2, 7.3] | -0.042 [-0.055, -0.027] | +0.89 [0.60, 1.21] |
| 0.02 | 5 | StableResolve(subst) | 480 | +2.7 [0.6, 4.8] | +2.7 [-0.4, 5.8] | -0.027 [-0.046, -0.002] | +0.87 [0.55, 1.23] |
| all | -- | AlwaysSubstitute | 960 | +0.3 [-1.1, 1.8] | -0.9 [-3.1, 0.9] | +0.014 [0.005, 0.028] | +0.43 [0.29, 0.57] |
| all | -- | FullResolve | 960 | +2.4 [0.7, 4.1] | +5.6 [3.2, 7.7] | -0.052 [-0.063, -0.042] | +0.36 [0.17, 0.56] |
| all | -- | FullResolve(subst) | 960 | +2.9 [0.9, 4.8] | +3.9 [0.8, 6.6] | -0.039 [-0.049, -0.028] | +0.81 [0.56, 1.07] |
| all | -- | StableResolve(subst) | 960 | +2.3 [0.5, 4.0] | +3.4 [0.7, 6.0] | -0.031 [-0.043, -0.016] | +0.66 [0.42, 0.92] |
