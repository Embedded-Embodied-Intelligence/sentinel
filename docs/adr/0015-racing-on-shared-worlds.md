# ADR-0015: Racing evaluation on shared sampled worlds

- Status: accepted
- Date: 2026-10-21
- WP: WP5a

## Context

Spec v1.7 section 6: every candidate is applied at step 3 of day t in each rollout, which then
continues under NoReaction; rollout i uses xi_i for all candidates; stage 1 runs N_1 = 50
rollouts per candidate and drops those whose capped on-time estimate min(p, theta_D) is below
the best by more than 2 paired standard errors; stage 2 extends the survivors to N = 200. The
needs gate evaluates NOOP first ("N_1 rollouts, then up to N"). Each world is to be sampled once
per epoch. Profiling a J30 deliberation: of the rollout time, rebuilding the state from the
observation took 12 %, the absence draws of the rollout streams 15 % and re-checking RESEQ plans
in every rollout 10 %; all three repeat identically for every candidate in the same world.

## Decision

An `Evaluator` per epoch samples world i once (belief stream of xi_i, as `forecast`) and keeps
the engine state it completes and the rollout streams of xi_i's future. A rollout of a
candidate in world i runs on a copy of that state (`EngineState.copy`) and on the same streams,
rewound (D2 cursors reset; absences and D3 draws are reused). A candidate is checked once with
`rehearse` and then applied without re-checking plans, as the check depends on the observation
only. Paired standard errors are sd(differences of on-time indicators, ddof 1) / sqrt(n). The
needs gate stops at N_1 only when those rollouts show a need beyond 2 standard errors;
otherwise NOOP is extended to N, so NOOP is returned only on N rollouts.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Fresh state and streams per candidate and rollout (`forecast`'s loop) | Same outcomes, about 40 % slower |
| One stream object per world without rewinding | D2 shocks of the second candidate would be skipped (the per-activity cursor only moves forward) |
| Racing on the whole lexicographic key | Not the rule of spec section 6; budget and stability are compared on all N rollouts |
| Successive halving or bandit allocation | More stages, harder to explain; the binding rule has two |
| The gate on N_1 rollouts only | NOOP would be returned on the evidence of 50 rollouts |

## Consequences

- NOOP's outcomes equal those of `forecast` with the same seed, and a duplicated candidate gets
  identical statistics (tests).
- When every candidate is late (or on time) in all stage-1 rollouts nothing can be dropped, so
  stage 2 evaluates all of them; hopeless epochs therefore cost the most.
- Copying a state and rewinding streams are the evaluator's only shortcuts; the engine runs
  unchanged, so a perfect-information rollout reproduces a Sentinel run.
