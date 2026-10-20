# WP1 notes — priority rules, serial SGS, RBRS, CP-SAT, RQ2 benchmark

**Priority rules** (`scheduling/priority_rules.py`, as compared in Kolisch 1996), one value per
activity id (dummies included); the SGS breaks ties by the smallest id.

| Rule | Value of activity j | Preferred |
| --- | --- | --- |
| LFT | latest finish `LF_j`, backward pass with horizon `T = LB0` (§1.4) | lower |
| LST | latest start `LS_j = LF_j − p_j`, `T = LB0` | lower |
| MTS | number of transitive successors, sink included (+1 for all non-sinks, order unchanged) | higher |
| GRPW | `p_j` + sum of `p_s` over immediate successors `s` | higher |

**Serial SGS** (`scheduling/sgs.py`; Kolisch 1996). In each of `n + 2` stages the chosen
eligible activity (all predecessors scheduled; eligible set in increasing id order) starts at
the earliest `t ≥ max_{i∈pred(j)} F_i` with at least `r_jk` idle units of every role on every
day of `[t, t + p_j)`. Idle capacity is a time-indexed list per role that starts with LB0 days
and doubles when an activity would end beyond it. When a window has days without capacity, the
next candidate start is the latest such day + 1. Zero-duration activities start at their
precedence bound and use no capacity (§1.3). On 40 random instances the schedules equal those of
a brute-force implementation for all four rules and random priorities.

**RBRS** (Drexl 1991; Kolisch 1996). Each pass is a serial SGS that chooses eligible `j` with
probability ∝ `(ρ_j + 1)^α`, `ρ_j = max_{i∈EL} LF_i − LF_j` (LF with `T = LB0`), `α = 1`. A pass
draws `n + 2` uniforms from the given `numpy.random.Generator` (one per stage, so every pass
consumes the same amount of the stream). The result is the best of the passes (minimum makespan,
ties: first found). Sampling stops early once a pass reaches LB0, which no schedule can beat; this
changes runtimes only. 1000 passes on a J60 instance take 0.16–0.31 s on the M1.

**CP-SAT model** (`scheduling/cpsat.py`; OR-Tools 9.15.6755, Perron & Didier). Starts
`S_j ∈ [0, H]`, `S_0 = 0`; one fixed-size interval `[S_j, S_j + p_j)` per activity;
`S_j ≥ S_i + p_i` for `(i, j) ∈ E`; one `AddCumulative` per role (capacity `R_k`, activities
with `p_j > 0`, `r_jk > 0`); objective `min S_{n+1}`. The default `H` is the SGS-LFT makespan, a
valid upper bound because that schedule is feasible. No hints, no redundant constraints.
Parameters: `num_workers = 1`, `random_seed` = instance seed, `max_time_in_seconds ∈ {1, 10}`.
`lower_bound = ceil(best_objective_bound)`. `wall_time_s` covers horizon, model and search.

**Benchmark protocol** (`experiments/rcpsp_benchmark.py`, `configs/wp1_rq2.toml`). J30 is
compared with proven optima (`opt`), J60 with best known upper bounds (`hrs`) plus `dev_lb0`
(§1.5; Kolisch & Hartmann 2006). The instance seed `derive_seed(2026, set, instance)` is shared
by RBRS and CP-SAT (common random numbers, ADR-0006). There is one task per (instance, method), 4
spawn-started worker processes, and `validate_schedule` on every schedule. `runtime_s` is the
wall time of the method call only. A stratified sample (instance 1 of each of the 48 parameter
groups per set) took 30 s; CP-SAT 10 s on J60 used 76% of the summed task time.

**References.** Kolisch 1996 (EJOR 90(2)); Drexl 1991 (Management Science 37(12)); Kolisch &
Hartmann 2006 (EJOR 174(1)); Kolisch & Sprecher 1997 (PSPLIB); Perron & Didier, CP-SAT, OR-Tools.
