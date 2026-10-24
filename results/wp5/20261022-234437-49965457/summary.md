# wp5_rq4_autonomy: run 20261022-234437-49965457

Generated from `results.csv.gz` by `sentinel.experiments.policy_summary` at commit `d07a0992953fae5969eea0b5bfabe12d54b72c7b`; do not edit.

- Policies on `cpsat_det` baseline plans: NoReaction, AlwaysSubstitute, FullResolve, FullResolve(subst), StableResolve(subst), Sentinel Λ=0, Sentinel Λ=1. CP-SAT: T_cp = 0.1 deterministic s per stage, seed 0, one worker; T_r = 5.
- Instances: every 8th of J30 in natural order; 4 replications per instance with the WP2b seeds, shared by all policies and scenarios (common random numbers). Scenarios: λ_S = 0.01, λ_N = 0.02.
- On time for δ: C ≤ D = ceil((1 + δ) C*) (spec section 1.2), evaluated post hoc; truncated runs are late. In % with 95 % Wilson intervals over the runs of a cell, which understate the uncertainty across instances.
- Deviation: realised deviation from the baseline plan in days; nervousness: changes of a planned start in the deviation set per run (spec section 7.1); substitutions: replaced crew members per run; onboarding: crew-member days o_j per replaced member; cost / B with β = 0.1. Means per run.
- Paired differences against NoReaction and FullResolve on the same worlds (set, instance, scenario, replication), means over the runs with 95 % percentile intervals of a cluster bootstrap over the instances of a set (1000 resamples, seed 2026); on time in percentage points.
- WP2b seed check against `results/wp2/20261020-181559-6534a712/results.csv.gz`: 240 worlds compared, **0 makespan mismatches** (expected 0), 0 seed mismatches, 0 without a WP2b row.
- Baselines joined from `results/wp4/20261021-152439-8892ea21/results.csv.gz`: 960 rows of AlwaysSubstitute, FullResolve, FullResolve(subst), StableResolve(subst) on the run's 240 worlds, not rerun; **0 NoReaction makespan mismatches** and 0 seed mismatches against the run's own rows (expected 0), 0 rows missing.
- Sentinel Λ=0 (`sentinel_lambda0`): Sentinel with Λ = 0, rule lexicographic, N₁ = 25, N = 100, working towards δ_D = 0.2; differs from spec section 8 in autonomy = 0.
- Sentinel Λ=1 (`sentinel_lambda1`): Sentinel with Λ = 1, rule lexicographic, N₁ = 25, N = 100, working towards δ_D = 0.2; differs from spec section 8 in autonomy = 1.
- Checks: 0 rejected operations, 0 CP-SAT fallbacks in 515 stages, 0 truncated runs.

## J30 (C*: optimum, `opt`), 60 instances

| λ_A | E[L] | Policy | Runs | On time δ=0.2 [%] | On time δ=0.3 [%] | C / C* | Deviation [d] | Nervousness | Substitutions | Onboarding [d] / subst. | Handover [d] | Cost / B | RESEQs | Fallbacks | Epochs | s / run |
| ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.01 | 3 | NoReaction | 240 | 21.2 [16.5, 26.9] | 44.2 [38.0, 50.5] | 1.365 | 7.15 | 0.0 | 0.0 | -- | 0.0 | 1.036 | 0.0 | 0 | 66.3 | 0.006 |
| 0.01 | 3 | AlwaysSubstitute | 240 | 19.2 [14.7, 24.6] | 44.2 [38.0, 50.5] | 1.374 | 7.46 | 0.0 | 23.4 | 1.88 | 3.1 | 1.055 | 0.0 | 0 | 66.7 | 0.010 |
| 0.01 | 3 | FullResolve | 240 | 24.6 [19.6, 30.4] | 54.2 [47.8, 60.4] | 1.318 | 7.59 | 193.4 | 0.0 | -- | 0.0 | 1.033 | 59.4 | 0 | 63.9 | 1.105 |
| 0.01 | 3 | FullResolve(subst) | 240 | 25.0 [19.9, 30.8] | 49.2 [42.9, 55.5] | 1.328 | 7.97 | 201.0 | 23.1 | 1.87 | 3.1 | 1.052 | 59.8 | 0 | 64.4 | 1.155 |
| 0.01 | 3 | StableResolve(subst) | 240 | 24.2 [19.2, 30.0] | 49.2 [42.9, 55.5] | 1.330 | 7.65 | 175.6 | 23.1 | 1.84 | 3.0 | 1.054 | 59.9 | 0 | 64.4 | 1.934 |
| 0.01 | 3 | Sentinel Λ=0 | 240 | 22.5 [17.7, 28.2] | 54.6 [48.3, 60.8] | 1.327 | 6.89 | 9.6 | 0.0 | 2.00 | 0.0 | 1.042 | 1.1 | 0 | 64.6 | 86.279 |
| 0.01 | 3 | Sentinel Λ=1 | 240 | 23.3 [18.4, 29.1] | 54.2 [47.8, 60.4] | 1.324 | 6.95 | 27.4 | 0.0 | 1.62 | 0.0 | 1.043 | 1.1 | 0 | 64.5 | 78.735 |
| all | -- | NoReaction | 240 | 21.2 [16.5, 26.9] | 44.2 [38.0, 50.5] | 1.365 | 7.15 | 0.0 | 0.0 | -- | 0.0 | 1.036 | 0.0 | 0 | 66.3 | 0.006 |
| all | -- | AlwaysSubstitute | 240 | 19.2 [14.7, 24.6] | 44.2 [38.0, 50.5] | 1.374 | 7.46 | 0.0 | 23.4 | 1.88 | 3.1 | 1.055 | 0.0 | 0 | 66.7 | 0.010 |
| all | -- | FullResolve | 240 | 24.6 [19.6, 30.4] | 54.2 [47.8, 60.4] | 1.318 | 7.59 | 193.4 | 0.0 | -- | 0.0 | 1.033 | 59.4 | 0 | 63.9 | 1.105 |
| all | -- | FullResolve(subst) | 240 | 25.0 [19.9, 30.8] | 49.2 [42.9, 55.5] | 1.328 | 7.97 | 201.0 | 23.1 | 1.87 | 3.1 | 1.052 | 59.8 | 0 | 64.4 | 1.155 |
| all | -- | StableResolve(subst) | 240 | 24.2 [19.2, 30.0] | 49.2 [42.9, 55.5] | 1.330 | 7.65 | 175.6 | 23.1 | 1.84 | 3.0 | 1.054 | 59.9 | 0 | 64.4 | 1.934 |
| all | -- | Sentinel Λ=0 | 240 | 22.5 [17.7, 28.2] | 54.6 [48.3, 60.8] | 1.327 | 6.89 | 9.6 | 0.0 | 2.00 | 0.0 | 1.042 | 1.1 | 0 | 64.6 | 86.279 |
| all | -- | Sentinel Λ=1 | 240 | 23.3 [18.4, 29.1] | 54.2 [47.8, 60.4] | 1.324 | 6.95 | 27.4 | 0.0 | 1.62 | 0.0 | 1.043 | 1.1 | 0 | 64.5 | 78.735 |

Paired differences against NoReaction:

| λ_A | E[L] | Policy | Pairs | Δ on time δ=0.2 [pp] | Δ on time δ=0.3 [pp] | Δ C / C* | Δ deviation [d] |
| ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 0.01 | 3 | AlwaysSubstitute | 240 | -2.1 [-5.0, 0.0] | 0.0 [-3.8, 3.8] | +0.009 [0.001, 0.018] | +0.32 [0.19, 0.45] |
| 0.01 | 3 | FullResolve | 240 | +3.3 [-0.4, 7.5] | +10.0 [5.4, 14.6] | -0.047 [-0.060, -0.034] | +0.44 [0.16, 0.76] |
| 0.01 | 3 | FullResolve(subst) | 240 | +3.8 [0.4, 7.5] | +5.0 [0.4, 9.6] | -0.037 [-0.050, -0.023] | +0.82 [0.46, 1.20] |
| 0.01 | 3 | StableResolve(subst) | 240 | +2.9 [-1.2, 7.5] | +5.0 [0.0, 9.6] | -0.035 [-0.047, -0.023] | +0.50 [0.17, 0.89] |
| 0.01 | 3 | Sentinel Λ=0 | 240 | +1.2 [-0.4, 3.3] | +10.4 [5.0, 15.8] | -0.038 [-0.049, -0.027] | -0.25 [-0.36, -0.15] |
| 0.01 | 3 | Sentinel Λ=1 | 240 | +2.1 [-0.4, 4.6] | +10.0 [5.0, 15.0] | -0.040 [-0.052, -0.029] | -0.20 [-0.30, -0.09] |
| all | -- | AlwaysSubstitute | 240 | -2.1 [-5.0, 0.0] | 0.0 [-3.8, 3.8] | +0.009 [0.001, 0.018] | +0.32 [0.19, 0.45] |
| all | -- | FullResolve | 240 | +3.3 [-0.4, 7.5] | +10.0 [5.4, 14.6] | -0.047 [-0.060, -0.034] | +0.44 [0.16, 0.76] |
| all | -- | FullResolve(subst) | 240 | +3.8 [0.4, 7.5] | +5.0 [0.4, 9.6] | -0.037 [-0.050, -0.023] | +0.82 [0.46, 1.20] |
| all | -- | StableResolve(subst) | 240 | +2.9 [-1.2, 7.5] | +5.0 [0.0, 9.6] | -0.035 [-0.047, -0.023] | +0.50 [0.17, 0.89] |
| all | -- | Sentinel Λ=0 | 240 | +1.2 [-0.4, 3.3] | +10.4 [5.0, 15.8] | -0.038 [-0.049, -0.027] | -0.25 [-0.36, -0.15] |
| all | -- | Sentinel Λ=1 | 240 | +2.1 [-0.4, 4.6] | +10.0 [5.0, 15.0] | -0.040 [-0.052, -0.029] | -0.20 [-0.30, -0.09] |

Paired differences against FullResolve:

| λ_A | E[L] | Policy | Pairs | Δ on time δ=0.2 [pp] | Δ on time δ=0.3 [pp] | Δ C / C* | Δ deviation [d] |
| ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 0.01 | 3 | NoReaction | 240 | -3.3 [-7.5, 0.4] | -10.0 [-14.6, -5.4] | +0.047 [0.034, 0.060] | -0.44 [-0.76, -0.16] |
| 0.01 | 3 | AlwaysSubstitute | 240 | -5.4 [-9.6, -1.2] | -10.0 [-15.4, -5.0] | +0.056 [0.043, 0.069] | -0.13 [-0.46, 0.14] |
| 0.01 | 3 | FullResolve(subst) | 240 | +0.4 [-0.8, 1.7] | -5.0 [-9.2, -1.2] | +0.010 [0.005, 0.015] | +0.38 [0.22, 0.56] |
| 0.01 | 3 | StableResolve(subst) | 240 | -0.4 [-3.8, 2.9] | -5.0 [-9.6, -0.8] | +0.012 [0.005, 0.018] | +0.06 [-0.21, 0.36] |
| 0.01 | 3 | Sentinel Λ=0 | 240 | -2.1 [-6.7, 2.1] | +0.4 [-5.4, 6.2] | +0.009 [-0.003, 0.020] | -0.70 [-1.04, -0.38] |
| 0.01 | 3 | Sentinel Λ=1 | 240 | -1.2 [-5.4, 2.5] | 0.0 [-5.0, 5.8] | +0.006 [-0.005, 0.017] | -0.64 [-0.98, -0.33] |
| all | -- | NoReaction | 240 | -3.3 [-7.5, 0.4] | -10.0 [-14.6, -5.4] | +0.047 [0.034, 0.060] | -0.44 [-0.76, -0.16] |
| all | -- | AlwaysSubstitute | 240 | -5.4 [-9.6, -1.2] | -10.0 [-15.4, -5.0] | +0.056 [0.043, 0.069] | -0.13 [-0.46, 0.14] |
| all | -- | FullResolve(subst) | 240 | +0.4 [-0.8, 1.7] | -5.0 [-9.2, -1.2] | +0.010 [0.005, 0.015] | +0.38 [0.22, 0.56] |
| all | -- | StableResolve(subst) | 240 | -0.4 [-3.8, 2.9] | -5.0 [-9.6, -0.8] | +0.012 [0.005, 0.018] | +0.06 [-0.21, 0.36] |
| all | -- | Sentinel Λ=0 | 240 | -2.1 [-6.7, 2.1] | +0.4 [-5.4, 6.2] | +0.009 [-0.003, 0.020] | -0.70 [-1.04, -0.38] |
| all | -- | Sentinel Λ=1 | 240 | -1.2 [-5.4, 2.5] | 0.0 [-5.0, 5.8] | +0.006 [-0.005, 0.017] | -0.64 [-0.98, -0.33] |

Sentinel per run: deliberations, needs-gate exits, rollouts and seconds per deliberation, temporary workers hired, overtime share of the cost, the permission gate's deferrals, escalations and approvals applied / discarded, scope loss:

| λ_A | E[L] | Policy | Runs | Deliberations | Gate exits | Rollouts / del. | s / del. | Hired | Overtime share | Deferrals | Escalations | Applied | Discarded | Scope loss |
| ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.01 | 3 | Sentinel Λ=0 | 240 | 40.5 | 1.0 | 463 | 2.127 | 2.17 | 0.0122 | 8.01 | 1.25 | 1.25 | 0.00 | 0.000 |
| 0.01 | 3 | Sentinel Λ=1 | 240 | 40.7 | 1.1 | 456 | 1.931 | 2.05 | 0.0117 | 5.74 | 1.10 | 1.10 | 0.00 | 0.000 |
| all | -- | Sentinel Λ=0 | 240 | 40.5 | 1.0 | 463 | 2.127 | 2.17 | 0.0122 | 8.01 | 1.25 | 1.25 | 0.00 | 0.000 |
| all | -- | Sentinel Λ=1 | 240 | 40.7 | 1.1 | 456 | 1.931 | 2.05 | 0.0117 | 5.74 | 1.10 | 1.10 | 0.00 | 0.000 |

Chosen candidates (before the permission gate) and deciding components, % of deliberations; RESEQ: RESEQ-M and RESEQ-S, SUBST: SUBST(j), SUBST-ALL and SUBST-ALL+RESEQ-M, OVERTIME: OT+RESEQ-M:

| λ_A | E[L] | Policy | Deliberations | Needs met | NOOP | SHIFT | RESEQ | SUBST | OVERTIME | DESCOPE | only_candidate | racing | on_time | tardiness | scope | budget | stability | level | order | utility |
| ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.01 | 3 | Sentinel Λ=0 | 9718 | 2.5 | 74.6 | 4.5 | 12.7 | 0.3 | 5.3 | 0.0 | 5.1 | 0.5 | 3.3 | 7.5 | 0.0 | 2.6 | 68.9 | 4.5 | 5.2 | 0.0 |
| 0.01 | 3 | Sentinel Λ=1 | 9766 | 2.6 | 77.3 | 3.3 | 11.4 | 0.3 | 5.1 | 0.0 | 5.4 | 0.5 | 3.2 | 7.5 | 0.0 | 2.5 | 68.9 | 3.4 | 5.9 | 0.0 |
| all | -- | Sentinel Λ=0 | 9718 | 2.5 | 74.6 | 4.5 | 12.7 | 0.3 | 5.3 | 0.0 | 5.1 | 0.5 | 3.3 | 7.5 | 0.0 | 2.6 | 68.9 | 4.5 | 5.2 | 0.0 |
| all | -- | Sentinel Λ=1 | 9766 | 2.6 | 77.3 | 3.3 | 11.4 | 0.3 | 5.1 | 0.0 | 5.4 | 0.5 | 3.2 | 7.5 | 0.0 | 2.5 | 68.9 | 3.4 | 5.9 | 0.0 |
