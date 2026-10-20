# ADR-0010: Forecast study layout: checkpoint observations, seeds and stored scores

- Status: accepted
- Date: 2026-10-20
- WP: WP3b

## Context

RQ3 scores forecasts made from mid-run observations of NoReaction worlds against the realised
makespan (spec §5.2). The worlds must be the WP2b runs, so that both studies describe the same
outcomes. A policy saw observations only at decision epochs, and a recording policy with review
period 1 (the WP3a benchmark) changes `n_epochs` and hence the results. The main study has
76,800 checkpoints with three forecasters; storing 200 makespans per forecast would mean 46
million numbers, while CRPS and the PIT need the whole forecast CDF.

## Decision

`simulate(..., observe_days)` keeps the step-3 observation of each listed day in
`SimulationResult.observations`, a field excluded from serialisation. Worlds use the WP2b seed
rule and max_days of δ_D = 0.3, and every summary compares their seeds and makespans with the
WP2b results file. One forecast seed per (set, instance, scenario, replication, f) is shared by
all forecasters. Each forecast is stored as p for every δ_D, mean, seven quantiles, the PIT
pair, CRPS, fallbacks and wall time, all computed in the worker from the samples. Everything
else (bins, ECE, warnings, randomised PIT, intervals) is recomputed from that file. Intervals
come from one cluster-bootstrap resample matrix per set, shared by all statistics.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Recording policy with review period 1 | Changes `n_epochs`, so results would differ from WP2b |
| Callback argument to `simulate` | More plumbing for the same by-product |
| Storing every sample | 46 M makespans; CRPS and PIT are exact from the worker instead |
| Storing only p and quantiles | CRPS and the PIT could not be recovered without a rerun |
| A seed per forecaster | Loses common random numbers; paired differences get noisier |
| Intervals over rows (Wilson) | Rows of an instance are correlated (CRN across scenarios); WP2b flagged it |
| A resample matrix per cell | Paired differences would mix different resamples |

## Consequences

Bins, thresholds, clipping and bootstrap settings can change without a rerun:
`sentinel summarise-forecasts` takes about 10 s for the full study. New forecasters,
checkpoints, rollout counts or quantile levels need a rerun. WP2b identity holds only while
the engine and the seed rule stay unchanged; the summary reports any mismatch. Observations
stay in memory until the world ends, which is cheap for five checkpoints.
