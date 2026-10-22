# ADR-0016: The permission gate in the world and in rollouts

- Status: accepted
- Date: 2026-10-22
- WP: WP5b

## Context

Spec v1.8 sections 4 and 6: an action with level l(a) >= Lambda or with a DESCOPE needs
approval. Sentinel defers it (urgency above tau_def) or escalates it; the simulated human
approves after delta_h days, that day becomes a decision epoch, and the action is re-validated
against the current state and applied if valid, else discarded with a fresh deliberation. In
rollouts a candidate that needs approval is applied at day t + delta_h if valid in that
rollout, so the agent imagines the delay. The engine already validates every operation
(`Run.apply` rejects invalid ones and the others still apply); RESEQ and SHIFT plans are
checked against the planning view, and `rehearse` decides validity from an observation alone.

## Decision

Sentinel keeps the escalated action and asks the engine for the approval day through the
policy attribute `requested_epoch`; there it re-validates with `rehearse` and applies the
action only if no operation would be rejected. A rollout of such a candidate runs NoReaction to
step 3 of day t + delta_h (`Run.resume_to`), tries the candidate on a copy of that state with
every plan checked and applies it only if nothing is rejected (`Run.apply_valid`), then
continues (`Run.carry_on`).

## Alternatives considered

| Option | Why not |
| --- | --- |
| Approval queue inside the engine | Puts agent logic into the world; the agent could not re-deliberate when an approved action turned invalid |
| Rollouts apply gated candidates at once | Contradicts spec section 6 and overstates actions the human approves late |
| Per-operation validity (the valid part applies) | Would apply the OVERTIME of OT+RESEQ-M without its plan; spec: "applied if valid, otherwise discarded" |
| Re-plan a stale RESEQ on its approval day | Beyond the spec, which re-validates the approved plan |
| Validate rollouts through `rehearse` on an observation of the rollout | Same verdict, but rebuilds the state from an observation in every rollout |

## Consequences

- World and rollouts share one notion of validity, the engine's own checks; NoReaction runs
  are unchanged, as passive policies request no epochs.
- A RESEQ or SHIFT plan made on day t can be stale on day t + delta_h: it lists activities
  that started on day t, or starts some before the approval day, and the engine then rejects
  it. In the WP5b measurements 3 of 13 (J30) and 0 of 9 (J60) escalations were discarded at
  Lambda = 2, and about 40 % at Lambda <= 1 (ablation smoke run); the rollouts imagine the
  same, so plan candidates win less often under a low Lambda (SHIFT was never chosen at
  Lambda = 0 there). Raised as a spec question in the WP5b report.
- Rollouts of gated candidates cost a state copy and a planning-view check on the approval day.
