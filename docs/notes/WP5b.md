# WP5b notes — material decision rule, permission gate, DESCOPE, rollout budget

**Decision rule** (spec v1.8 §6). Sentinel maximises lexicographically min(p̂, θ_D), −T̂, −o,
−Δ, −ℓ, with the expected tardiness T̂ = (1/N) Σ max(0, C − D); with DESCOPE candidates the
scope loss (v_j / Σ_O v_i) follows T̂. Every component decides only on material differences:
two candidates tie in min(p̂, θ_D), T̂ or o when their paired (common-random-number) difference
is within 2 paired standard errors *or* below ε_D = 0.02, ε_T = 0.5 day or ε_B = 0.01; in Δ
below ε_Δ = 0.5 day; in ℓ only when equal. The paired standard errors are those of the mean
per-rollout differences of the on-time indicators, the tardiness and the total cost over B.
The best set is filtered component by component against the best of the current set; the
component that removes the last competitor is the deciding component, that competitor the
runner-up. Racing (N₁ then N rollouts) drops a candidate only if it is significantly and
materially worse than the stage leader in both min(p̂, θ_D) and T̂. Measured effect
(λ_A = 0.01): the budget decided 61–74 % of deliberations before (on cost differences of
about 0.03 %) and decides 1–2 % now; NOOP wins whenever nothing is materially better (stability
72–74 %); T̂ decides 3–4 %, mostly in hopeless epochs. Sentinel chooses NOOP in 86–87 % of
deliberations (64 % before) and reaches the lowest C / C* of the policies measured (J30 1.297
against 1.362 for NoReaction and 1.328 for FullResolve; J60 1.347 against 1.402 and 1.375)
with a quarter (J30) or a fifth (J60) of FullResolve's plan changes.

**Permission gate** (§4; ADR-0016). An action other than NOOP runs at once iff ℓ(a) < Λ and it
has no DESCOPE. Otherwise Sentinel defers it (NOOP, deliberate again later) when the urgency
τ_t = min_j τ_j exceeds τ_def = 3 days, else escalates it: a simulated human approves after
δ_h = 1 day, the approval day becomes a decision epoch (the policy requests it from the
engine), and the action applies there if the engine would reject none of its operations,
otherwise it is discarded and Sentinel deliberates afresh. In rollouts a candidate that needs
approval is applied at step 3 of day t + δ_h if valid in that rollout, so the agent imagines
the delay. At Λ = 2 every level-2 choice was deferred (21 J30, 7 J60) or escalated (13, 9), and
10 of 13 and 9 of 9 escalations applied; the gate cost 0.02 (J30) and 0.007 (J60) in C / C*,
mostly by fewer hires. A plan approved a day late can be stale (about 40 % of escalations
discarded at Λ ≤ 1 in the ablation smoke run).

**DESCOPE** (§4, §6). Optional activities O: round(φ · n) of the real activities whose only
successor is the sink (all three such activities of every PSPLIB instance for φ = 0.1), drawn
with derive_seed(2026, "optional", instance); value v_j = p_j Σ_k c_k r_jk. DESCOPE(j) removes
an unstarted j ∈ O: its edges vanish, predecessors left without successors precede the sink.
At most two DESCOPE candidates (largest p_j) join only when no other candidate reaches θ_D, and
DESCOPE always needs approval. Scope loss = Σ_removed v_j / Σ_O v_j.

**Rollout budget.** (N₁, N) = (25, 100) replaces (50, 200): on 722 deliberations its choice
agreed with an N = 800 reference in 90.3 % and lost 0.0014 in p̂ and 0.023 day in T̂ on
average, at half the rollouts; a deliberation takes 0.40 s (J30) and 0.74 s (J60).

**Study size.** The RQ4 Sentinel study as planned needs about 58 CPU h (main) and 36 CPU h
(ablation), 14.4 h and 9.0 h on 4 workers, above the 12 h and 6 h budgets.

**References.** Bertsekas, Tsitsiklis & Wu 1997 (rollout); Simon 1955 (satisficing); Brooks
1995 (handover); Van de Vonder et al. 2007 (stability); Herroelen & Leus 2005.
