# WP2a.1 report — Partial crews and answers to the WP2a spec questions

- Date: 2026-10-20
- Commit(s): 4b4ae55 (spec v1.2), 7c1c04b (engine, checks, tests), 4d36190 (calibration
  script); the report/notes/roadmap commit follows them

## Summary
The simulator now follows spec v1.2. Crews stay reserved until their activity completes, a day
with c of M_j members present does c/M_j full-crew days of work, and an activity pauses only
when its whole crew is absent. D2 is drawn on each work day before progress without rounding.
Milestones and the sink complete as soon as their predecessors are done, so projects can finish
early. NoReaction now takes 1.30–1.35 times its plan instead of 2.3–2.5. The calibration table
over λ_A ∈ {0, …, 0.02} is under Numbers. `simulate` takes 4.7 ms (J30) and 8.0 ms (J60) per
call.

## Acceptance criteria
| # | Criterion | Command | Result |
| --- | --- | --- | --- |
| 1 | Spec v1.2 commit with all amendments | `git show --stat 4b4ae55` | PASS (`spec: partial crews and WP2a answers (v1.2)`: §3.1 (a) partial crews; §3 steps 1–6 and h_j = max(1, ceil(α e_j m_j / M_j)); §2.2 D2 on the k-th work day before progress, remaining · F; §3.1 (c)–(d) zero-duration completion, railway only for p_j > 0; §2.2 readings of WP2a questions 1, 3, 4; §8 λ_A grid with 0.0025 and the worker-days note; §2.1, §2.3 wording) |
| 2 | Quality gate and `-m data` pass; all task-2 tests exist and pass | `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy src`; `uv run pytest -q`; `uv run pytest -q -m data` | PASS (ruff clean; 84 files formatted; mypy: no issues in 27 source files; 134 passed; data: 8 passed, 126 deselected; task-2 mapping under Changes) |
| 3 | Calibration table for J30 and J60 | `uv run python scripts/calibrate_absences.py` | PASS (8 scenarios × 150 runs per set, table under Numbers; 7.5 s) |
| 4 | Timings, J30 mean ≤ 5 ms and J60 mean ≤ 15 ms | `uv run python scripts/bench_simulate.py` | PASS (J30 mean 4.67 ms, p95 6.54 ms; J60 mean 8.00 ms, p95 10.68 ms; 200 calls each; a repeat gave 4.56 / 7.83 ms) |
| 5 | Report and notes updated; pushed; clean tree | `git push`; `git status --short` | PASS (this report, `docs/notes/WP2a.md` with a "Partial crews" section, roadmap; pushed to `origin/main`; `git status --short` empty afterwards) |

## Changes
- `docs/spec/model.md` v1.2, as the WP prompt specified (separate commit).
- `simulation/state.py`: `EngineState` counts work in crew-member days (`unit` = M_j, `done`, `remaining`), keeps per activity the crew (`assigned`), present members (`working`), `rate`, `work_cost` and the D2 counter `work_days`; takes `max_days`. `Observation.work_done` and the e_j in `work_increases` are floats (full-crew days).
- `simulation/engine.py`: step 2 `_update_crew` (rate, cost, pause, resume, segment split) replaces `_pause`; D2 in step 5 before progress (`_work_increase`, window by remaining units and days left); `_dispatch` completes milestones first, whatever their plan, then starts activities in (plan, id) order; `SimulationResult` gains `crews`, `work` is float; SPEC-Q markers 2 and 5 removed, 4 turned into a comment.
- `simulation/events.py`: `WorkIncrease` gains `work_day` (k); `work_done` (e_j before the shock) and the remaining work are floats; SPEC-Q markers 1 and 3 turned into comments citing §2.2.
- `simulation/realised.py`: `realised_instance` gives each activity its reservation [S_j, F_j); `execution_violations` checks crew role counts, no worker in two crews at once, and that on each reserved day exactly the present crew members work.
- `scripts/calibrate_absences.py`: the calibration table of this report.
- Tests, task 2 → test (`tests/test_simulation.py`):
  - one-person pause and resume: `test_one_person_activity_pauses_and_resumes_with_the_same_worker`;
  - four-person crew at 0.75/day: `test_partial_crew_progresses_at_the_present_share[4-5]` and `[5-7]` (see Deviations);
  - whole crew absent: `test_whole_crew_absent_pauses_and_resumes_at_the_reduced_rate`;
  - D2 with λ_S = 1 on a one-day activity: `test_work_increase_can_hit_a_one_day_activity`;
  - early finish: `test_zero_duration_activities_complete_early_so_projects_can_finish_early`;
  - also new: `test_feasibility_checks_count_reserved_absent_members` (tampered runs are flagged).
- WP2a tests adapted to v1.2 (all others unchanged):
  - `test_absence_pauses_and_resumes_with_the_same_workers` → `test_absent_member_slows_the_crew_and_stays_reserved`. Same scenario, but A now runs at ρ = 1/2 with worker 0, who is no longer released to B. A finishes on day 6 (was 7), B runs on days 6–7 (was 1–2), makespan 8 (was 7); crew, cost and trace are also asserted.
  - `test_forced_work_increase_extends_the_duration`: the forced check k = 2 now comes on day 1 before progress (5 → 7.5) instead of after two days (4 → ceil 6). Work 8.5 (was 8), F = 9 (was 8); the epoch count is asserted.
  - `test_random_work_increases_follow_the_ceil_rule` → `test_random_work_increases_scale_the_remaining_work`: remaining · F instead of ceil.
  - `test_stochastic_durations_give_feasible_schedules` and the data test `test_default_disruptions_on_30_j30_instances`: the railway assertion covers p_j > 0 only. The first test also rounds the now-float `work` for `with_durations`.
  - `test_new_activities_keep_the_graph_acyclic`: a zero-duration D3 copy may complete on its insertion day.
- Docs: this report, `docs/notes/WP2a.md` (daily semantics updated, "Partial crews" section, measurements), roadmap.

## Decisions
- **Work units:** the engine counts crew-member days, P_j M_j units at the start and c units on a day with c present members. That is ρ_j = c/M_j without floating-point drift: float steps of 1/10 would leave 1.4e-16 after ten days and finish a day late. Only D2 makes remaining work fractional; subtracting integers from it stays exact.
- **Cost:** a day costs Σ c_k over the present members (WP2a: "each worker-day of work costs c_k"), so absences delay work without raising its cost. See spec question 3.
- **No demands (M_j = 0, p_j > 0):** ρ_j = 1, one unit per day. PSPLIB has no such activity (checked: 0 of 43 200 real activities in J30/J60).
- **Dispatch:** milestones need no workers, so completing them first changes no allocation, and the activities they release join one sorted pass. Starts release nothing, so the heap became a sorted list.
- **D2 lookup:** every work day does at least one unit, so after k work days the checks k + 1 .. k + min(ceil(remaining units), days left) cover every possible next shock. The days-left bound also keeps `ceil` finite if λ_S near 1 makes remaining work explode. Answers do not depend on the window, because streams are read by position.
- **`changed` shortcut (ADR-0007):** a returning crew member rejoins the crew and does not set `changed`, because no worker became idle.
- **Interfaces:** `WorkIncrease.work_day` was added because k ≠ e_j now, and e_j can be 0 at a shock. `SimulationResult.crews` was added because a member absent for a whole activity appears in no segment. Segments split at every change of present members, and zero-duration activities have none.
- **Calibration:** on time means makespan ≤ D = ceil((1 + δ) C*), the §1.2 deadline, not the real-valued (1 + δ) C*. C* is J30 opt and J60 hrs (best known, as in WP2a). Seeds are `derive_seed(2026, set, instance, replication)`, shared by all scenarios. max_days comes from δ = 0.3.
- ADRs created: none (local engine details, recorded here and in the notes).

## Deviations
- **Test 2 expected value:** the prompt expects M_j = P_j = 4 with one member absent for the whole run to finish after ceil(4 / 0.75) = 6 days. Dispatch assigns only present workers (§3.1 b), so a crew always starts complete and the absence can begin on day 2 of the activity at the earliest. Then e_j = 1, 1.75, 2.5, 3.25, 4 and the activity finishes after 5 days. The test is parametrised: P_j = 4 gives 5 days, and P_j = 5 gives 1 + ceil(4 / 0.75) = 7 days (the prompt's 6 days at 0.75 after the full first day).
- **Interface changes** required by v1.2: `SimulationResult.work` is float and `crews` is new; `WorkIncrease` has `work_day` and float fields; `Observation.work_done` and `work_increases` hold floats; `EngineState` takes `max_days`; `WorkSegment` now means a constant set of present members. WP0/WP1 interfaces are unchanged. There are no new dependencies.
- **Calibration table extras:** reference rows without disruptions, D2 only and D3 only, and the share of absent worker-days. They separate the causes of delay and check the §8 note.
- `scripts/bench_simulate.py` is unchanged, so the timings use the WP2a parameters.

## Spec questions
1. **D2 decision epoch** (`engine.py`, `SPEC-Q`): D2 is now drawn in step 5, after step 3's decision, so it cannot trigger a decision on its own day. Reading used: the day after a shock is a decision epoch (§3: "after every D1–D3 event"). Alternative: D2 triggers no epoch. Suggested §3.1 (g): "any day with a D1 or D3 event, the day after a D2 event, and every day t with t % T_r == 0".
2. **SUBST under partial crews (needed for WP4):** §4 SUBST, §5 urgency, §6 candidates and §7 AlwaysSubstitute still speak of *paused* activities. Under v1.2 an activity with some absent members runs at a reduced rate, and the m_j / M_j in h_j suggests that SUBST may replace members of such a running activity. Open points:
   - Does SUBST apply to running activities?
   - Does AlwaysSubstitute replace every absent member, or act only on whole-crew pauses?
   - Does a replaced member who returns become idle, i.e. leave the crew?
   - Should urgency τ_t include activities with absent members?
3. **Cost of a partial-crew day:** only present members cost c_k. Alternative: the reserved crew is paid while absent. Costs would then rise with absences, which matters for the budget goal G3 (§5). The budget B is based on full-crew work, so the current reading keeps absences budget-neutral.
4. **Activities without demands** (M_j = 0, p_j > 0): ρ_j is undefined in §3.1 (a); the reading used is ρ_j = 1. This is only relevant beyond PSPLIB.

## Numbers
Calibration (`scripts/calibrate_absences.py`). For each set, every 16th instance (30) × 5 replications, SGS-LFT plan, NoReaction, default PERT. The λ_A rows use E[L] = 3, λ_S = 0.01 and λ_N = 0.02. "On time" means makespan ≤ ceil((1 + δ) C*). "Absent" is the share of the run's worker-days on which the worker was absent:

| Set | Scenario | Runs | Realised / planned | On time δ=0.1 | On time δ=0.2 | On time δ=0.3 | Truncated | Absent |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| J30 | none | 150 | 1.083 | 35.3% | 66.0% | 90.0% | 0 | 0.00% |
| J30 | D2 only | 150 | 1.127 | 21.3% | 55.3% | 76.0% | 0 | 0.00% |
| J30 | D3 only | 150 | 1.161 | 20.0% | 45.3% | 71.3% | 0 | 0.00% |
| J30 | λ_A = 0.0 | 150 | 1.209 | 12.0% | 34.0% | 61.3% | 0 | 0.00% |
| J30 | λ_A = 0.0025 | 150 | 1.245 | 8.7% | 28.7% | 54.0% | 0 | 0.75% |
| J30 | λ_A = 0.005 | 150 | 1.269 | 7.3% | 23.3% | 47.3% | 0 | 1.41% |
| J30 | λ_A = 0.01 | 150 | 1.310 | 4.7% | 15.3% | 38.0% | 0 | 2.83% |
| J30 | λ_A = 0.02 | 150 | 1.364 | 0.7% | 11.3% | 26.0% | 0 | 5.52% |
| J60 | none | 150 | 1.087 | 43.3% | 68.7% | 88.0% | 0 | 0.00% |
| J60 | D2 only | 150 | 1.134 | 21.3% | 53.3% | 77.3% | 0 | 0.00% |
| J60 | D3 only | 150 | 1.170 | 27.3% | 49.3% | 63.3% | 0 | 0.00% |
| J60 | λ_A = 0.0 | 150 | 1.215 | 14.7% | 38.7% | 56.7% | 0 | 0.00% |
| J60 | λ_A = 0.0025 | 150 | 1.239 | 8.0% | 37.3% | 55.3% | 0 | 0.72% |
| J60 | λ_A = 0.005 | 150 | 1.266 | 6.0% | 30.7% | 47.3% | 0 | 1.44% |
| J60 | λ_A = 0.01 | 150 | 1.295 | 2.7% | 23.3% | 45.3% | 0 | 2.82% |
| J60 | λ_A = 0.02 | 150 | 1.355 | 2.0% | 12.7% | 34.0% | 0 | 5.56% |

The SGS-LFT plans average 1.084 C* (J30; 10 of 30 at C*) and 1.074 C* (J60; 14 of 30). δ = 0.1 therefore leaves about 1.5–2.5 % slack over the plan.

Timings (`scripts/bench_simulate.py`, same set-up as WP2a: 40 instances spread over each set × 5 seeds, SGS-LFT plan, D = ceil(1.1 C*), λ_A = 0.01, E[L] = 3, λ_S = 0.01, λ_N = 0.02, NoReaction):

| Set | Calls | Mean ms | p95 ms | Max ms | Repeat mean / p95 ms | Realised / planned | On time (D) | Events per run (absence / D2 / D3) | Epochs per run |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| J30 | 200 | 4.67 | 6.54 | 22.55 | 4.56 / 6.36 | 1.345 (WP2a 2.304) | 3.5% (WP2a 1.0%) | 64.0 / 2.06 / 1.77 | 53.0 |
| J60 | 200 | 8.00 | 10.68 | 48.95 | 7.83 / 10.69 | 1.304 (WP2a 2.533) | 3.5% (WP2a 0.0%) | 120.4 / 4.04 / 2.28 | 81.8 |

| Measurement | Value |
| --- | --- |
| Tests | 134 passed in 4.8 s (127 before; 7 new incl. one parametrised twice); `-m data` 8 passed in 3.3 s |
| J30 30 × 5 data-test runs (λ_A = 0.01) | realised / planned 1.310 (WP2a 2.100); 0 truncated; 58.9 absences, 2.0 work increases, 1.7 new activities, 52.0 epochs per run |
| Cost per J30 call (cProfile, 200 calls) | Mostly fixed costs, as in WP2a: setting up ~110 `SeedSequence` children and PCG64 generators, plus walking the absence streams. Crew updates (`_update_crew`) take about 6 % of the profiled time. |
| Extra check (scratch script, not committed) | 660 runs on `tiny` and every 24th J30 / 48th J60 instance with heavy disruptions (λ_A ∈ {0.02, 0.05}, λ_S ∈ {0.05, 0.1}, λ_N ∈ {0.05, 0.1}). All complete runs pass `validate_schedule` and `execution_violations` and finish on the first day with remaining work ≤ 0. Milestones complete exactly when their last predecessor finishes, and a non-passive empty policy gives the same results. The 95 runs truncated under these extreme rates also pass the worker checks. |

Environment: Intel i5-6600K (4 cores), WSL2 Ubuntu 24.04, uv 0.13.2, CPython 3.12.15, numpy
2.5.4, pydantic 2.14.1, ortools 9.15.6755. Three runs on the final engine code gave 4.56–4.67 ms
(J30) and 7.83–8.00 ms (J60).

## Commands for the owner
None required: there is no long run in WP2a.1. To reproduce the numbers (about 15 s):
```bash
cd ~/projects/sentinel && git pull && uv sync --locked
uv run pytest -q                              # expect 134 passed
uv run python scripts/calibrate_absences.py   # calibration table, ~8 s
uv run python scripts/bench_simulate.py       # timings, ~4 s
```

## Open issues / next steps
- **Calibration for WP2b (architect):**
  - D2 and D3 at their default rates already cost NoReaction as much as λ_A = 0.01: at λ_A = 0 the realised/planned ratio is 1.21, and D3 alone gives 1.16.
  - With SGS-LFT plans the "often but not always" region lies at δ_D = 0.2–0.3 for λ_A ≤ 0.01: 15–61 % on time.
  - WP2b's CP-SAT baseline starts nearer C* (SGS-LFT is 7–8 % above it), which should raise every on-time share.
- Spec questions 1–4, especially 2 before WP4.
- **WP4 (SUBST):**
  - Changing a crew must update `assigned`, `working`, `rate` and `work_cost`, close the current segment as `_update_crew` does, and set `changed` when workers become idle.
  - `SimulationResult.crews` and `execution_violations` assume one crew per activity, so a crew history will be needed.
