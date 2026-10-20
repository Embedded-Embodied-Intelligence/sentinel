# WP3a report — Beliefs, mid-project rollouts and the Monte Carlo forecaster

- Date: 2026-10-20
- Commit(s): c4297ed (experiment plan), 68ba82a (spec v1.4), 3acb1ce (regression fixture,
  recorded before the refactor), 6d53e57 (engine refactor, `state_from_observation`), b5f58a4
  (duration pmf, belief), 939c50c (rollout streams, forecaster, ADR-0009), 9665d28 (benchmark
  script); the report/notes/roadmap commit follows them

## Summary
`forecast(observation, plan, ...)` samples the hidden state from the observation (§5.1). It
continues each sample with NoReaction rollouts and returns the makespan distribution,
`P(C ≤ D)`, the 10/50/90 % quantiles, the mean, the fallback count and the wall time. `simulate`
is now state initialisation plus a resumable run loop (`Run`), and its results are unchanged:
50 recorded runs match bit for bit. With the true hidden state and no future disruptions, every
rollout reproduces the world's makespan exactly. From day 0, 2000 rollouts agree with 2000 world
runs within 0.4 % in five checks on four instances. A forecast with 200 rollouts takes 0.24 s on J30 and
0.35 s on J60 on average, against targets of 1.0 s and 2.0 s.

## Acceptance criteria
| # | Criterion | Command | Result |
| --- | --- | --- | --- |
| 1 | Commits for `plan.md` and spec v1.4 present | `git show --stat c4297ed 68ba82a` | PASS (`docs: experiment plan from the WP2b study`: `docs/experiments/plan.md`; `spec: beliefs and rollouts (v1.4)`: new §5.1, §5 urgency, §6 SUBST candidates, rollout CRN, §3 cross-reference) |
| 2 | Quality gate and `-m data` pass; all task-6 tests exist and pass; refactor regression test passes | `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy src`; `uv run pytest -q`; `uv run pytest -q -m data` | PASS (ruff clean; 108 files formatted; mypy: no issues in 36 source files; 193 passed; data: 13 passed, 180 deselected; mapping under Changes; `test_fifty_runs_are_unchanged` passes) |
| 3 | Speed table reported; targets met or profile plus plan | `uv run python scripts/bench_forecast.py` | PASS (targets met: J30 n = 200 mean 0.237 s ≤ 1.0 s, J60 0.353 s ≤ 2.0 s; table under Numbers; a profile is included for WP5) |
| 4 | ADR for the rollout random layout | `docs/adr/0009-rollout-random-layout.md` | PASS (ADR-0009, accepted) |
| 5 | Report, notes, roadmap (`WP3: in progress: WP3a done`); pushed; clean tree | `git push`; `git status --short` | PASS (this report, `docs/notes/WP3a.md`, roadmap; pushed to `origin/main`; `git status --short` empty afterwards) |

## Changes
- `docs/experiments/plan.md`: scenario selection from WP2b run `20261020-181559-6534a712`.
- `docs/spec/model.md` v1.4 as dictated by the prompt.
- `simulation/engine.py`: `simulate` builds the state and runs `Run.days(0)`. New `Run`:
  - `open_day` runs steps 1–3, `close_day` steps 4–6, and `days(first)` loops from a given day;
  - `resume()` continues a state observed at step 3 of its day;
  - `result()` builds the `SimulationResult`;
  - `record_events=False` skips event models in rollouts.
- `simulation/events.py`: `DisruptionStreams` protocol, which `ScenarioStreams` and the rollout streams implement.
- `simulation/state.py`: `SampledWorld` (the hidden part of a state), `EngineState.hidden()` (test hook), `state_from_observation(observation, world, *, plan=None, costs=None)`, `day_limit`, `crew_member_days`.
- `forecasting/durations.py`: `IntegerPmf` (inverse CDF, conditioning) and the cached `duration_pmf(p, pert)`.
- `forecasting/beliefs.py`: `Belief` (precomputed posterior, `sample(rng)`), `sample_world`, `absence_posterior`.
- `forecasting/streams.py`: `RolloutStreams`, `geometric` (ADR-0009).
- `forecasting/forecast.py`: `Forecast` (`mean`, `quantile`, `quantiles`, `p_on_time`) and `forecast`.
- `scripts/bench_forecast.py`: timings, fallbacks and day-0 agreement for this report.
- `.pre-commit-config.yaml`: the regression fixture (SHA-256 digests only) is excluded from `detect-secrets`, as the run manifests are.
- Tests (task 6 → test):
  - pmf sums to 1 and its mean is within 0.01 of 10⁶ sampler draws: `test_duration_pmf_matches_the_sampler[closed-form]` and `[simpson]`.
  - Conditional sampling never returns P_j ≤ e_j: `test_conditional_durations_exceed_the_work_done`. Also `test_shocked_activity_follows_the_replayed_condition` (a D2 shock and a fallback) and `test_integer_pmf_inverse_cdf_and_conditioning`.
  - Absence posterior: `test_absence_posterior_support_and_moments`, which checks the support, normalisation and mean by enumeration and in closed form; also `test_absent_workers_return_after_today`.
  - Perfect information: `test_perfect_information_rollouts_reproduce_the_true_makespan`.
  - Day 0 against the world: `test_day_zero_forecast_agrees_with_the_world` (data, 8.6 s).
  - CRN: `test_forecasts_with_the_same_seed_share_samples_across_plans`. It checks the sampled return days, absence onsets and D3 arrivals per rollout for two plans.
  - Hidden fields: `test_observation_hides_hidden_quantities` (unchanged, passes) and the constraint test `test_forecast_sees_only_the_observation`.
  - Refactor regression: `test_fifty_runs_are_unchanged`, using `tests/fixtures/engine_regression.json`.
  - Further tests: `test_state_from_observation_rebuilds_the_engine_state`, `test_resumed_state_continues_like_the_world`, `test_rollout_streams_do_not_depend_on_query_order`, `test_rollout_streams_follow_the_event_distributions`, `test_forecast_statistics_and_determinism`, `test_sampled_worlds_are_the_only_hidden_input`, `test_duration_pmf_edge_cases`.
- Docs: ADR-0009, `docs/notes/WP3a.md`, this report, roadmap.

## Decisions
- **Rollout start.** An observation is taken at step 3 of day t. `state_from_observation` rebuilds that state. `Run.resume()` first closes day t with its dispatch and progress, then runs the loop from day t + 1. Starting directly at t + 1 would drop the observed day's work, and the perfect-information test would fail.
- **Hidden state in crew-member days.** `SampledWorld.remaining` uses the engine's unit (M_j per full-crew day). Converting full-crew days back and forth can add one ulp, and the activity would then need an extra day. `crew_member_days` recovers e_j M_j as an integer and rejects non-integral work.
- **Belief.**
  - Remaining work rises with P_j (F ≥ 1), so the feasible durations form the top of the pmf's range.
  - A replayed remaining work ≤ 1e−9 crew-member days counts as finished.
  - Zero probability falls back to 1 crew-member day. An empty absence support (L ≥ 366, or E[L] = 1 with L ≥ 2) falls back to the smallest L. Both kinds are counted in `fallbacks`.
  - A sample reads one uniform per activity and per worker in a single draw.
- **pmf.**
  - Shapes within 1e−9 of an integer use the closed form; the default gives α = 1.9999999999999998.
  - Upper values are computed via the survival function for accuracy.
  - Non-integer shapes use Simpson with 20,000 intervals per value.
  - Masses are normalised by their sum, and end values without mass are dropped.
  - Results are cached with `functools.cache`.
  - Cost per value of p, measured once: 0.1 ms closed form, 2–15 ms Simpson.
- **Rollout random layout** (ADR-0009). Each process jumps from event to event with geometric gaps. Blocks hold round r of every worker or activity, so the k-th event always reads the same uniforms. D2 counts work days from the rollout start. Rollout i spawns a belief stream and a future stream from ξ_i.
- **Forecast.**
  - Quantiles use the inverted empirical CDF, so each quantile is an observed makespan.
  - A truncated rollout counts `max_days` and is late.
  - `fallbacks` is per sampled world; it depends on the observation only.
  - Rollouts use T_r = 5, since epochs do not change NoReaction.
  - `Forecast` also records `day`, `seed`, `n_rollouts`, `include_future_disruptions` and `truncated`.
- **Hidden-state guard.** `forecast` rejects anything but an `Observation` and a `Schedule` with `TypeError`. The only way to pass hidden state is `_true_world`, which uses `EngineState.hidden()`.
- **Regression.** The 50-run digests were recorded with the pre-refactor engine (commit 3acb1ce, before 6d53e57) and stored as a fixture instead of a copy of the old engine. The runs cover 4 instances, 4 disruption settings, recording and passive policies, traces, deadlines including truncation, review periods 3 and 5, and custom costs. `simulate` still takes 4.61 ms (J30) and 7.96 ms (J60) in `scripts/bench_simulate.py`, against 4.6 / 7.9 ms before.
- ADRs created: ADR-0009.

## Deviations
- **Interface additions** (backwards compatible): `Run`, `DisruptionStreams`, `SampledWorld` (in `simulation/state.py`, so the simulation layer does not import forecasting), `EngineState.hidden`, `day_limit`, `crew_member_days`, `Belief`, `absence_posterior`, `IntegerPmf`, and the optional `plan` and `costs` of `state_from_observation`. The observation carries no c_k, so costs default to 1.0. The `simulate` signature and results are unchanged, and there are no new dependencies.
- `forecast` imports `derive_seed` from `sentinel.experiments.runs`, as the prompt prescribes, although forecasting sits below the experiments layer.
- **plan.md:** the prompt quotes 2–21 % on time at δ_D = 0.1. The run gives 2.3–21.2 % for λ_A ≤ 0.01 and 0.7–1.5 % at λ_A = 0.02; the plan quotes the exact values.
- **The day-0 data test** uses the SGS-LFT plan of j301_1 so that tests need no CP-SAT. The benchmark uses the `cpsat_det` baseline plans of WP2b.
- `.pre-commit-config.yaml` was changed (see Changes).

## Spec questions
1. **§5 urgency scope** (WP5): v1.4, as dictated, defines τ_j = LF_j − t − E[remaining_j] for *all* running activities. v1.3 counted only running activities with absent members. The text was transcribed literally; which scope is meant?
2. **Absence posterior with empty support** (`beliefs.py`): if t − s + 1 > 365, or E[L] = 1 and L_low > 1, §5.1 leaves no admissible L. Reading used: L = the smallest admissible length, counted as a fallback. It never occurred in the measurements.
3. **Prompt wording "size-biased":** the task-6 text calls the L_low = 1, t = s posterior a "size-biased-then-truncated geometric". The §5.1 formula q(1−q)^{L−1}/L divides by L, which is the opposite of size-biasing (L · p(L)). The test checks the §5.1 formula. Its untruncated mean is (1 − q)/(−q ln q), i.e. 1.82 at E[L] = 3.

## Numbers
`scripts/bench_forecast.py` uses 20 instances per set (every 24th), `cpsat_det` baseline plans, D = ceil(1.2 C*) and the primary scenario: λ_A = 0.01, E[L] = 3, λ_S = 0.01, λ_N = 0.02. One world run per instance gives the observations at 0/25/50/75 % of the planned makespan. Wall time is per `forecast` call on one process; the whole script took 122 s.

| Set | Day | n | Forecasts | Mean s | p95 s | Max s | Fallbacks | Truncated |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| J30 | 0 % | 100 | 20 | 0.141 | 0.170 | 0.199 | 0 | 0 |
| J30 | 25 % | 100 | 20 | 0.128 | 0.155 | 0.176 | 0 | 0 |
| J30 | 50 % | 100 | 20 | 0.111 | 0.130 | 0.156 | 0 | 0 |
| J30 | 75 % | 100 | 20 | 0.093 | 0.114 | 0.132 | 0 | 0 |
| J30 | all | 100 | 80 | 0.118 | 0.169 | 0.199 | 0 | 0 |
| J30 | 0 % | 200 | 20 | 0.283 | 0.341 | 0.398 | 0 | 0 |
| J30 | 25 % | 200 | 20 | 0.257 | 0.315 | 0.351 | 0 | 0 |
| J30 | 50 % | 200 | 20 | 0.224 | 0.261 | 0.310 | 0 | 0 |
| J30 | 75 % | 200 | 20 | 0.186 | 0.235 | 0.261 | 0 | 0 |
| J30 | **all** | **200** | 80 | **0.237** (target 1.0) | 0.338 | 0.398 | 0 | 0 |
| J60 | 0 % | 100 | 20 | 0.223 | 0.293 | 0.309 | 0 | 0 |
| J60 | 25 % | 100 | 20 | 0.193 | 0.257 | 0.261 | 0 | 0 |
| J60 | 50 % | 100 | 20 | 0.161 | 0.213 | 0.222 | 0 | 0 |
| J60 | 75 % | 100 | 20 | 0.131 | 0.174 | 0.183 | 0 | 0 |
| J60 | all | 100 | 80 | 0.177 | 0.261 | 0.309 | 0 | 0 |
| J60 | 0 % | 200 | 20 | 0.449 | 0.600 | 0.607 | 0 | 0 |
| J60 | 25 % | 200 | 20 | 0.383 | 0.520 | 0.524 | 0 | 0 |
| J60 | 50 % | 200 | 20 | 0.320 | 0.424 | 0.435 | 0 | 0 |
| J60 | 75 % | 200 | 20 | 0.259 | 0.348 | 0.367 | 0 | 0 |
| J60 | **all** | **200** | 80 | **0.353** (target 2.0) | 0.524 | 0.607 | 0 | 0 |

Fallbacks: 0 in all 320 forecasts (160 observations), and no rollout was truncated.

Day-0 agreement compares 2000 rollouts from day 0 before any event with 2000 world runs (seeds `derive_seed(2026, set, instance, r)`) and the same D. The rollouts start their disruptions on day 1, while the world also draws on day 0.

| Source | Instance (plan) | Plan | D | World mean | Forecast mean | Gap | World P(C ≤ D) | Forecast P(C ≤ D) | Forecast s |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| data test | j30/j301_1 (SGS-LFT) | 49 | 52 | 62.029 | 62.168 | +0.22 % | 0.056 | 0.050 | 2.04 |
| benchmark | j30/j301_1 (`cpsat_det`) | 43 | 52 | 58.53 | 58.75 | +0.37 % | 0.265 | 0.255 | 2.03 |
| benchmark | j30/j3025_1 | 93 | 112 | 136.62 | 136.10 | −0.38 % | 0.025 | 0.025 | 3.40 |
| benchmark | j60/j601_1 | 77 | 93 | 104.01 | 103.64 | −0.36 % | 0.226 | 0.240 | 3.27 |
| benchmark | j60/j6025_1 | 115 | 137 | 172.60 | 172.26 | −0.20 % | 0.001 | 0.000 | 4.98 |

Profile of a J60 day-0 forecast with 200 rollouts (j601_1, cProfile, cumulative shares):

| Part | Share |
| --- | ---: |
| Run loop (`Run.resume`) | 75 % |
| ↳ dispatch | 17 % |
| ↳ absence onsets of the rollout streams | 19 % |
| Rebuilding states (`state_from_observation`, mostly `EngineState.__init__`) | 14 % |

| Measurement | Value |
| --- | --- |
| Tests | 193 passed in 31.6 s (174 before WP3a; 19 new, among them 1 data test); `-m data` 13 passed in 20.5 s |
| `simulate` after the refactor (`scripts/bench_simulate.py`, WP2a parameters) | J30 4.61 ms, J60 7.96 ms mean (4.6 / 7.9 ms before) |
| Regression fixture | 50 runs, 1,904 events, 12 truncated, 37.9 KB |

Environment: Intel i5-6600K (4 cores), WSL2 Ubuntu 24.04, uv 0.13.2, CPython 3.12.15, numpy
2.5.4, pydantic 2.14.1, ortools 9.15.6755. The timings are specific to this machine and vary by a
few percent between repeats.

## Commands for the owner
None required: WP3a has no long run. To reproduce the numbers (about 2.5 min):
```bash
cd ~/projects/sentinel && git pull && uv sync --locked
uv run pytest -q                              # expect 193 passed
uv run pytest -q -s -m data tests/test_forecasting_data.py   # day-0 agreement values
uv run python scripts/bench_forecast.py      # speed table and agreement, ~2 min
```

## Open issues / next steps
- WP3b: calibration of `forecast` (RQ3) on the primary grid of `docs/experiments/plan.md`. `scripts/bench_forecast.py` shows how to take observations from world runs.
- WP5: a candidate action must be applied to the rebuilt state between `state_from_observation` and `Run.resume()`. Sampled worlds and seeds can be shared across candidates. Costs Z_a^(i) are in `state.cost` after a rollout but not yet in `Forecast`.
- WP5 speed headroom: 200 J60 rollouts take 0.35 s on average, so each candidate adds about that much per decision epoch. If that is too slow, cloning a template state instead of rebuilding it saves up to 14 %.
- Spec questions 1–3 above.
