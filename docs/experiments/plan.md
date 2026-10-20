# Experiment plan

Scenario selection for WP3b–WP7, made by the architect from the WP2b NoReaction study, run
`results/wp2/20261020-181559-6534a712` (NoReaction on `cpsat_det` baseline plans; 480 instances
per set × 20 replications; common random numbers across scenarios; `summary.md` of the run).
The aim is a region where the base policy is on time often but not always, so that
interventions can help and harm.

## Scenarios

| Role | δ_D | λ_A | E[L] | λ_S | λ_N |
| --- | ---: | --- | ---: | ---: | ---: |
| Primary grid | 0.2 | {0, 0.005, 0.01, 0.02} | 3 | 0.01 | 0.02 |
| Sensitivity: deadline | 0.3 | as primary | 3 | 0.01 | 0.02 |
| Sensitivity: absence length | 0.2 | as primary | 5 | 0.01 | 0.02 |

Deadline `D = ceil((1 + δ_D) C*)` with `C*` = J30 optimum (`opt`), J60 best known (`hrs`)
(spec §1.2); PERT(0.8, 1.0, 1.6), λ = 4; `T_r = 5`; `β = 0.1`. Single-scenario checks (e.g. the
WP3a forecaster tests and timings) use the primary scenario with `λ_A = 0.01`.

## Evidence (run 20261020-181559-6534a712)

NoReaction on time, `C ≤ D`, in % of 9,600 runs per cell, E[L] = 3:

| Set | λ_A | δ_D = 0.1 | δ_D = 0.2 | δ_D = 0.3 | C / C* |
| --- | ---: | ---: | ---: | ---: | ---: |
| J30 | 0 | 21.2 | 51.2 | 72.4 | 1.252 |
| J30 | 0.005 | 8.9 | 33.3 | 58.6 | 1.319 |
| J30 | 0.01 | 4.6 | 22.9 | 48.8 | 1.361 |
| J30 | 0.02 | 1.5 | 12.8 | 35.6 | 1.422 |
| J60 | 0 | 15.5 | 46.5 | 70.5 | 1.257 |
| J60 | 0.005 | 5.4 | 30.0 | 56.3 | 1.321 |
| J60 | 0.01 | 2.3 | 21.0 | 47.2 | 1.361 |
| J60 | 0.02 | 0.7 | 11.3 | 35.6 | 1.415 |

- **δ_D = 0.2 (primary):** on time in 11–51 % of runs, decreasing in λ_A on both sets.
- **δ_D = 0.3 (sensitivity):** 36–72 %, a looser deadline.
- **E[L] = 5 (sensitivity), δ_D = 0.2:** J30 30.4 / 19.6 / 8.3 %, J60 28.1 / 18.1 / 7.8 % for
  λ_A = 0.005 / 0.01 / 0.02 (λ_A = 0 is the same scenario as for E[L] = 3).
- **δ_D = 0.1 excluded:** NoReaction is on time in only 2.3–21.2 % of runs for λ_A ≤ 0.01
  (0.7–1.5 % at λ_A = 0.02): the deadline is mostly missed before any absence, because D2 and D3
  alone raise C / C* from 1.10 (J30) and 1.12 (J60) with durations only to 1.25 and 1.26.
- λ_A = 0.0025 (studied in WP2b) is not in the grid; its cells lie between those of λ_A = 0
  and 0.005 (on time at δ_D = 0.2: J30 41.0 %, J60 37.1 %).

No run of the study was truncated. Intervals and the remaining scenarios are in the run's
`summary.md`.
