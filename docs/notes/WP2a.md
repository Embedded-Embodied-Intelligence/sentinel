# WP2a notes — stochastic simulator core

**Uncertainty** (`simulation/uncertainty.py`). `X ~ PERT(0.8, 1.0, 1.6)`, λ = 4, drawn as
`a + (b − a) Beta(1 + λ(m − a)/(b − a), 1 + λ(b − m)/(b − a))` = `0.8 + 0.8 Beta(2, 4)` (Malcolm
et al. 1959); mean 1.0667. `P_j = max(1, round(p_j X_j))` (half to even); `P_j = 0` for `p_j = 0`.
`D = ceil((1 + δ_D) C*)`; `B = (1 + β) Σ c_k r_jk p̄_j` with `p̄_j = p_j E[X]`.

**Daily semantics** (`simulation/engine.py`, spec §3, §3.1). On day t: (1) workers due back
return, then D1 onsets, D2 shocks of activities still running from day t − 1, and D3 insertions;
(2) activities with an absent worker are paused and release their present workers; (3) on
decision epochs (any D1–D3 event, or t ≡ 0 mod T_r) the policy decides; (4) dispatch;
(5) each running activity does one unit of work at cost Σ_k c_k r_jk; (6) activities without
remaining work finish at F = t + 1. Dispatch goes through eligible activities (all
predecessors done, plan start ≤ t) in order of (plan start, id) with a heap. A paused
activity resumes only when all its original workers are present and idle; an unstarted one
takes the lowest-id idle workers of each role. Zero-duration activities need no workers and
complete at once, and the successors they release join the same pass (§3.1 c). No activity
starts before its plan, the sink included ("railway" execution; Herroelen & Leus 2005).
Days 0..max_days are simulated, max_days = 5D (5 Σ p_j without D). A truncated run reports
makespan = max_days.

**Data structures.** `EngineState` keeps plain Python lists indexed by activity id (status,
e_j, hidden remaining work, plan, starts, finishes, assigned workers) and by worker id
(presence, true return day, announced L_low, current activity). It also keeps one sorted
idle list per role, a set of eligible activities, and a sorted list of running activities.
D3 appends to all of them. Hidden fields leave the engine only through `SimulationResult`.
`Observation` is a frozen copy without them, built only for non-passive policies. Work is
logged as segments of uninterrupted progress. `realised_instance` turns each segment into an
activity, chained per original activity, so that `validate_schedule` (§1.3) checks runs with
pauses. `execution_violations` checks role counts, double bookings and work while absent.

**Common random numbers** (`simulation/events.py`, §2.3). `SeedSequence(ξ).spawn(4)` gives
streams for (i) durations (one multiplier per activity id), (ii) absences (one child per
worker), (iii) D2 (one child per original activity id) and (iv) D3.
- Worker stream: on each present day one uniform u, with an onset if u < λ_A. An onset reads
  two more uniforms: `L = 1 + ⌊ln(1 − u)/ln(1 − q)⌋` (q = 1/E[L], numpy's geometric(q)) and
  `L_low = 1 + ⌊u L⌋`. No uniform is read on absent days or on the return day.
- D2 stream: check k (at e_j = k) reads uniforms 2k − 2 (Bernoulli) and 2k − 1 (F).
- D3 stream, per 128-day chunk: four uniforms per day (occurrence, template, successor,
  predecessor), then 128 multipliers. Uniforms map onto sorted candidate lists as ⌊u n⌋.

Absences and D3 occurrence days, templates and multipliers depend only on ξ, so they are
identical for every policy and plan. D2 shocks depend only on the activity's progress.

**Measured** (i5-6600K, 40 instances × 5 seeds per set, SGS-LFT plan, D = 1.1 C*,
λ_A = 0.01, E[L] = 3, λ_S = 0.01, λ_N = 0.02):
- `simulate` takes 4.8 ms (J30) and 8.3 ms (J60) on average.
- NoReaction makespans are 2.3 (J30) and 2.5 (J60) times the plan; ≤ 1% of runs meet D.
- A J30 run has ~115 absences, 1.7 work increases and 3.0 new activities.

**References.** Malcolm et al. 1959 (PERT); Herroelen & Leus 2005 (baseline schedules and
reactive execution); Bertsekas et al. 1997 (base policy of rollouts); numpy `SeedSequence`
(O'Neill's PCG family with seed hashing).
