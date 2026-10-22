# WP5b.1 notes — re-plan on approval, optional activities, study sizes

**Re-plan on approval** (spec v1.8.1 §4, §6; ADR-0017). The simulated human approves the
*intent* of an escalated action, not a schedule made `δ_h` days earlier. On the approval day
the action's SUBST, OVERTIME and DESCOPE operations are re-validated unchanged against the
current state, and its plan part is planned again on the planning view they leave, with the
objective of its candidate: SHIFT is recomputed, RESEQ-M minimises the residual makespan,
RESEQ-S the deviation within the makespan of the current SHIFT, and the RESEQ-M of
OT + RESEQ-M sees the temporary workers. The action applies all or nothing; it is discarded,
with a fresh deliberation, only if one of those operations would be rejected or the new plan
fails the engine's check. Rollouts imagine exactly this: in every rollout that reaches the
approval day, the action is rebuilt on that rollout's observation by the same code as in the
world. One function builds every action (candidate generation on the epoch day, approval on
the approval day), so approving a candidate on its own epoch reproduces it. Within an epoch,
rollouts share plan parts by objective and planning view, which is exact because CP-SAT runs
with one worker, a fixed seed and a deterministic limit.

**Effect.** Under v1.8 a plan made on day t was usually stale on day t + 1 (it listed
activities that had started), so about 40 % of the escalations at `Λ ≤ 1` were discarded and
rollouts made plan candidates look useless under the gate. On the identical j301_1 runs of the
ablation smoke (λ_A ∈ {0.01, 0.02}, R = 4) all 49 escalations were applied; at `Λ = 0` and
λ_A = 0.02 Sentinel escalated 2.0 actions per run (0.25 before) and finished 1.5 days earlier
on average. Runs at `Λ = 3` never wait for an approval and are bit-identical to v1.8.

**Cost.** Behind the gate CP-SAT now runs inside rollouts, once per distinct approval-day view
and objective in an epoch (45–74 % of the plan parts reused at `Λ = 0`). On identical J30
runs a gated run costs 1.3–1.7 times its v1.8 time at `Λ = 2` and 1.9–3.6 times at `Λ ≤ 1` on
four instances, but 2.8–3.0 and 12 times on j3029_9 at λ_A = 0.02, where each CP-SAT search
needs 0.3–0.5 s of wall time for its 0.1 deterministic seconds (24 min per run at `Λ = 0`).
The deterministic limit makes results reproducible, not cheap: hard instances dominate.

**Optional activities** (§4). `O` is every real activity whose only successor is the sink:
three in each of the 480 J30 and 480 J60 instances. The share `φ` and its seeded draw are gone;
for PSPLIB the set is the one used before (round(φ n) capped at three gave all three).

**Deferrals** (§4). A deferred action is not remembered; every deliberation starts afresh, so
an action may be deferred repeatedly until the urgency falls to `τ_def` and it is escalated.

**Study sizes.** Main: Sentinel at full autonomy with and without OVERTIME (J30 every 4th, J60
every 8th, four λ_A, R = 4); the autonomy levels `Λ ∈ {0, 1, 2}`, DESCOPE, the scalarised rule
and δ_D = 0.3 form the ablation on J30 every 8th at λ_A ∈ {0.01, 0.02}.

**References.** Bertsekas, Tsitsiklis & Wu 1997 (rollout); Van de Vonder et al. 2007
(predictive-reactive repair).
