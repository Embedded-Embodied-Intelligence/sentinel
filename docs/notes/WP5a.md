# WP5a notes — Sentinel core: overtime, candidates, rollout evaluation, decision rule

**Agent** (spec v1.7 §5–§6; ADR-0014). A one-step rollout policy on NoReaction (Bertsekas,
Tsitsiklis & Wu 1997), with full autonomy in WP5a and the variants `full`, `no_overtime` (the
fair comparison with the baselines) and `scalarised`. It deliberates at periodic epochs and at
epochs with an event touching a crew (D2, D3, or an absence onset or return of a crew member);
at epochs with only idle workers' events it keeps NOOP. A deliberation evaluates NOOP first
(needs gate: N₁ = 50 rollouts, extended to N = 200 unless they show a need beyond two standard
errors; NOOP is returned if n_D ≤ 0.02 and n_B ≤ 0.01), then generates the candidates, races
them and applies the lexicographic choice. Every epoch leaves a JSON decision record: day,
reason, NOOP needs, every candidate with operations, level, Δ, rollouts, p̂, capped p̂, paired
SE against the best, ẑ, o and whether racing dropped it, the tied candidates and timings.

| Candidate | Operations | ℓ |
| --- | --- | ---: |
| NOOP | none | 0 |
| SHIFT | serial SGS on the planned-start list, each activity with p_j > 0 starting no earlier than the one before it | 0 |
| RESEQ-M / RESEQ-S | CP-SAT: minimum residual makespan / minimum deviation within SHIFT's makespan | 1 |
| SUBST(j) (≤ 3), SUBST-ALL | the most urgent eligible activities (τ_j); AlwaysSubstitute's set | 2 |
| SUBST-ALL+RESEQ-M | then RESEQ-M on the state the substitutions leave | 2 |
| OT(k*)+RESEQ-M | ⌊γ R_k*⌋ temporary workers of the most backlogged role (Σ r_jk p_j / R_k over activities with LS_j ≤ t + 2 T_r) for 2 T_r days, then RESEQ-M | 2 |

Each candidate is rehearsed through the engine's `Run.apply` and dropped if an operation would
be rejected or its effect repeats an earlier candidate. **OVERTIME**: temporary workers are
present every day of the window, never absent, idle until dispatched or substituted, stay in
their crew after the window and leave when idle; each costs 1.5 c_k per hired day; at most
⌊0.2 R_k⌋ per role at a time; they have no absence stream, so the world's events stay the same.

**Evaluation** (ADR-0015). Epoch t uses s_t = derive_seed(run seed, "sentinel", t) and rollout
i the forecaster's ξ_i = derive_seed(s_t, "rollout", i): world i is sampled once, and every
candidate runs on a copy of its rebuilt state and on its rewound disruption streams. Racing:
50 rollouts per candidate, drop those whose min(p̂, θ_D) is more than 2 paired SE below the
best, extend the rest to 200. The rule ties capped estimates within 2 paired SE, then prefers
the smallest o, Δ (mean planned-start change over U'_t plus κ_h = 2 per replaced member) and ℓ;
the ablation maximises U = p̂ − o − 0.01 Δ.

**Measured** (λ_A = 0.01; 20 J30 and 10 J60 spread instances, one seed). A deliberation takes
0.60 s (J30) and 1.09 s (J60) on average with about 800–900 rollouts; 42 and 65 deliberations
make a run take 25 s and 71 s. Sharing the sampled worlds cut a J30 deliberation from 1.36 s
to 0.83 s with identical decisions. First look: C / C* 1.343 (J30) and 1.315 (J60) against
1.388 / 1.359 for NoReaction and 1.351 / 1.341 for FullResolve, with 148 / 385 planned-start
changes per run against FullResolve's 208 / 690. NOOP is chosen in about 64 % of
deliberations, SHIFT in 12–17 %, RESEQ-M in 11 %, OVERTIME in 1–2 %. The budget component
decides 61–74 % of them on cost differences of about 0.03 %: runs end over budget (cost / B
1.02–1.05) and o is compared exactly. The RQ4 study of both variants needs about 91 CPU h per
δ_D.

**References.** Bertsekas, Tsitsiklis & Wu 1997; Kolisch 1996; Van de Vonder et al. 2007;
Herroelen & Leus 2005; Brooks 1995; Perron & Didier, OR-Tools CP-SAT.
