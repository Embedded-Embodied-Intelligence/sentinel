# ADR-0017: Approved actions re-planned by the code that builds candidates

- Status: accepted
- Date: 2026-10-22
- WP: WP5b.1

## Context

Spec v1.8.1 sections 4 and 6: on its approval day an escalated action keeps its SUBST,
OVERTIME and DESCOPE operations, re-validated, and its plan part is planned again on the current
planning view with its candidate's objective (SHIFT; RESEQ-M; RESEQ-S within the current SHIFT's
makespan; OT + RESEQ-M with the temporary workers); it applies all or nothing, and rollouts
imagine exactly this. Under ADR-0016 the plan of day t was re-validated as it was and was often
stale. A plan part depends on the planning view alone: CP-SAT runs with one worker, a fixed seed
and a deterministic limit, and SHIFT is a serial SGS.

## Decision

One function, `prepare(observation, kind, operations)`, builds every action: its operations are
rehearsed through the engine, and the plan part of its kind is planned on the view they leave
and checked there with the engine's own `plan_rejection`. Generation uses it on the epoch's
observation, `approve` on the approval day's observation, in Sentinel and in each rollout (on
the observation of the rollout's state at step 3 of that day). The rollouts of one epoch share
plan parts in a cache keyed by the objective and every field of the planning view.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Residual SGS (or a smaller CP-SAT limit) for the re-plan in rollouts, CP-SAT in the world | Rollouts would not imagine what the world does; spec section 6 says "exactly as in the world" |
| Approve on a copy of the rollout state (`Run.apply_valid` with a new plan) | A second code path beside Sentinel's; the observation is all the world's Sentinel sees |
| No cache | Every rollout that reaches the approval day would search again (about 45 % of the plan parts at Lambda = 0 were reused on j3010_7) |
| Cache by observation | Fewer hits: observations also differ where the views agree |

## Consequences

- Generation and approval cannot drift apart: approving a candidate on its own epoch gives back
  its decision (test). Runs at Lambda = 3 never wait for an approval and are bit-identical to
  before (six runs in a test; 64 main-smoke runs in every non-timing column), and slightly
  faster, as plan-only kinds skip a rehearsal.
- `Run.apply_valid` is gone; `approve` checks everything on the observation, which holds for
  every state with that observation (`rehearse`).
- Behind the gate CP-SAT runs inside rollouts, once per distinct approval-day view and plan
  objective of an epoch. On identical J30 runs a run at Lambda <= 1 cost 1.9-3.6 times its
  v1.8 time on four instances and 12 times on j3029_9 (lambda_A = 0.02, 24 min), where every
  CP-SAT search takes 0.3-0.5 s of wall time for its 0.1 deterministic seconds; at Lambda = 2
  1.3-1.7 times, and 2.8-3.0 times on j3029_9. This sets the size of the ablation study
  (WP5b.1 report).
