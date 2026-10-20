# WP2a notes — stochastic simulator core

**Uncertainty** (`simulation/uncertainty.py`). `X ~ PERT(0.8, 1.0, 1.6)`, λ = 4, drawn as
`a + (b − a) Beta(1 + λ(m − a)/(b − a), 1 + λ(b − m)/(b − a))` = `0.8 + 0.8 Beta(2, 4)` (Malcolm
et al. 1959); mean 1.0667. `P_j = max(1, round(p_j X_j))` (half to even); `P_j = 0` for `p_j = 0`.
`D = ceil((1 + δ_D) C*)`; `B = (1 + β) Σ c_k r_jk p̄_j` with `p̄_j = p_j E[X]`.

**Daily semantics** (`simulation/engine.py`, spec v1.2 §3, §3.1). On day t: (1) workers due
back return, then D1 onsets and D3 insertions; (2) crews whose presence changed get a new rate,
pause (nobody present) or resume; (3) on decision epochs (any D1 or D3 event, the day after a
D2 shock, or t ≡ 0 mod T_r) the policy decides; (4) dispatch; (5) each running activity draws
the D2 check of this work day, then progresses by its present crew members at their daily
cost; (6) activities without remaining work finish at F = t + 1. Dispatch first completes the
zero-duration activities whose predecessors are done, whatever their plan, together with the
ones they release (§3.1 c). It then tries eligible unstarted activities (plan start ≤ t) in
order of (plan start, id), each taking the lowest-id idle present workers of every role.
Activities with p_j > 0 never start before their plan ("railway" execution; Herroelen & Leus
2005). Milestones and the sink do, so a project can finish early. Days 0..max_days are
simulated, max_days = 5D (5 Σ p_j without D). A truncated run reports makespan = max_days.

**Data structures.** `EngineState` keeps plain Python lists indexed by activity id (status,
work done and hidden remaining work in crew-member days, rate, plan, starts, finishes, crew,
present crew members, D2 counter) and by worker id (presence, true return day, announced
L_low, crew membership). It also keeps one sorted idle list per role, a set of eligible
unstarted activities, and a sorted list of running activities. D3 appends to all of them.
Hidden fields leave the engine only through `SimulationResult`. `Observation` is a frozen copy
without them, built only for non-passive policies. Work is logged as segments with a constant
set of present crew members.

**Common random numbers** (`simulation/events.py`, §2.3). `SeedSequence(ξ).spawn(4)` gives
streams for (i) durations (one multiplier per activity id), (ii) absences (one child per
worker), (iii) D2 (one child per original activity id) and (iv) D3.
- Worker stream: on each present day one uniform u, with an onset if u < λ_A. An onset reads
  two more uniforms: `L = 1 + ⌊ln(1 − u)/ln(1 − q)⌋` (q = 1/E[L], numpy's geometric(q)) and
  `L_low = 1 + ⌊u L⌋`. No uniform is read on absent days or on the return day.
- D2 stream: the check of the k-th work day reads uniforms 2k − 2 (Bernoulli) and 2k − 1 (F).
- D3 stream, per 128-day chunk: four uniforms per day (occurrence, template, successor,
  predecessor), then 128 multipliers. Uniforms map onto sorted candidate lists as ⌊u n⌋.

Absences and D3 occurrence days, templates and multipliers depend only on ξ, so they are
identical for every policy and plan. D2 shocks depend only on the activity's own work days.

**Partial crews** (WP2a.1, spec v1.2 §3.1 a). Rule (a) of v1.1 stopped a whole crew for one
absence and released the others to other work. PSPLIB crews reach 39–40 workers, so delays
cascaded and NoReaction took 2.3–2.5 times its plan. Under v1.2 a crew stays reserved
from start to finish, and absent members count against R_k. Work is measured in full-crew
days: a day with c of its M_j = Σ_k r_jk members present does ρ_j = c/M_j of them, and the
activity pauses only when nobody is present. Absent members rejoin on return, and nobody is
reassigned under NoReaction. The engine counts work in crew-member days (P_j M_j units at the
start, c units per day), so rates such as 1/10 add up without rounding error and the finish
test "remaining ≤ 0" is exact; only D2 makes remaining work fractional. An activity without
demands (none in PSPLIB) progresses at ρ_j = 1. A day costs Σ c_k over the present members,
so absences delay work but do not raise its cost.
- **D2** is drawn on each work day (ρ_j > 0) before progress, so a one-day activity can be hit;
  remaining work becomes remaining · F without rounding. The shock comes after the day's
  decision, so the next day is a decision epoch.
- **Zero-duration activities**, the sink included, complete as soon as their predecessors are
  done; the railway rule holds only for p_j > 0, so a project can finish before its plan.
- **Checks** (`simulation/realised.py`). `realised_instance` gives every activity its
  reservation [S_j, F_j) for `validate_schedule` (§1.3), so absent members count against
  capacity. `execution_violations` checks crew role counts, no worker in two crews at once,
  and that on each reserved day exactly the present crew members work.
- **Calibration** (`scripts/calibrate_absences.py`; 30 instances × 5 seeds per set, SGS-LFT
  plans, CRN across scenarios). NoReaction takes 1.08× its plan with durations only, 1.21× with
  D2 and D3 at λ_A = 0, and 1.31× (J30) / 1.30× (J60) at λ_A = 0.01. At δ_D = 0.3 the on-time
  share falls from 61 % / 57 % (λ_A = 0) to 26 % / 34 % (λ_A = 0.02). λ_A = 0.01 leaves 2.8 %
  of worker-days absent, as §8 predicts.

**Measured** (i5-6600K, 40 instances × 5 seeds per set, SGS-LFT plan, D = 1.1 C*,
λ_A = 0.01, E[L] = 3, λ_S = 0.01, λ_N = 0.02, spec v1.2):
- `simulate` takes 4.6 ms (J30) and 7.9 ms (J60) on average (v1.1: 4.8 and 8.3).
- NoReaction makespans are 1.35 (J30) and 1.30 (J60) times the plan (v1.1: 2.3 and 2.5).
- A J30 run has ~64 absences, 2.1 work increases and 1.8 new activities.

**References.** Malcolm et al. 1959 (PERT); Herroelen & Leus 2005 (baseline schedules and
reactive execution); Bertsekas et al. 1997 (base policy of rollouts); numpy `SeedSequence`
(O'Neill's PCG family with seed hashing).
