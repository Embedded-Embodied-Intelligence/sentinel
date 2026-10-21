# WP4a notes — interventions, the planning view and the baseline policies

**Operations** (`Run.apply`, spec §4). Step 3 applies a decision's operations in order, each
checked against the state the previous ones left; an invalid one is logged and skipped. Rollouts
use the same `Run.apply` on a rebuilt state before `Run.resume()`.
- SUBST(j, W'): j is paused or running with absent members; each substitute is present and in
  no crew, and a role needs as many absent members as substitutes. Within a role the
  substitutes, in the given order, replace the absent members in increasing id order and keep
  their slots. Replaced members leave at once and are idle on return. h_j = max(1, ⌈α e_j m_j /
  M_j⌉) (α = 0.3) is added to the remaining work, ρ_j is recomputed, and the substitute works
  that day.
- RESEQ(π'): a start for every unstarted activity that passes `validate_residual` on the
  planning view of the current state; otherwise rejected and counted. Dispatch is unchanged.
- Nervousness: per epoch, the activities whose planned start the decision changed.

**Handovers are observable**: (activity, e_j, h_j). The deterministic forecaster and the belief
(§5.1) replay shocks and handovers in order of work done, a handover first at equal work; a
handover adds h_j M_j crew-member days, and the belief excludes durations that would have
finished before it.

**Planning view** (§4.1, ADR-0012). F̂_j uses the nominal remaining work; present members work
from day t, absent ones from s + max(L_low, t − s + 1). The engine's daily subtraction is
reused, so F̂_j equals the deterministic forecast's finish. Crew members reserve their role on
[t, F̂_j) and absent idle workers until their return. Each role's capacity is a step function
ending at R_k. Unstarted activities, D3 ones included, keep nominal p_j and r_jk, with fixed
finishes from finished and started predecessors.

**Solvers.** Residual SGS: Kolisch's serial SGS with release times and free capacity per day,
LFT on the residual network, ties by id. Decoding a feasible plan by its own starts never starts
an activity later. CP-SAT: intervals and one cumulative per role, capacity dips as fixed
intervals, starts in [release, H], H = SGS-LFT makespan. Stage 2 of StableResolve minimises
Σ|S_j − S_j^t| subject to S_sink ≤ C₁ (Van de Vonder et al. 2007). One worker, seed 0, only a
deterministic limit (T_cp = 0.5); the hint is the current plan if feasible, else the SGS schedule.
A stage without a solution falls back to the SGS (stage 1) or to stage 1 (stage 2); in 38,000+
measured stages none did.

**Policies.** AlwaysSubstitute serves activities in increasing τ_j: LS_j − t, or LF_j − t −
E[remaining_j] for running ones, with E[remaining_j] exact under the belief. FullResolve and
StableResolve re-plan at epochs whose observation shows a new disruption since the previous
epoch: absences (worker, first day), D2 shocks or D3 activities. A return is seen at the next
epoch, since returns are not epochs (§3.1 g). They plan on the state their own SUBSTs leave
(`preview`).

**Measured** (i5-6600K). 0.5 deterministic s of CP-SAT took 2.2–2.5 s wall on hard J60 views.
At λ_A = 0.01 a J60 run takes 20 s (FullResolve) and 39 s (StableResolve(subst)) at T_cp = 0.5.
In the first look, substitution lengthens projects: a handover of ≥ 1 full-crew day outweighs
an absence of E[L] = 3 days, during which a partial crew keeps working (Brooks 1995).

**References.** Kolisch 1996; Van de Vonder et al. 2007; Herroelen & Leus 2005; Brooks 1995;
Perron & Didier, OR-Tools CP-SAT.
