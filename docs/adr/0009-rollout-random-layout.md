# ADR-0009: Random layout of the rollout disruptions

- Status: accepted
- Date: 2026-10-20
- WP: WP3a

## Context

A forecast runs N = 200 rollouts from an observation of day t (spec §5.1), and WP5 repeats them
for every candidate with the same seeds. The world streams of §2.3 spawn one `SeedSequence` child
per worker and per original activity (about 110 per J30 run, about 1.2 ms per run, ADR-0007)
and draw one Bernoulli per worker and day. WP3a allows a faster layout for rollouts if (i) a
rollout seed gives the same state-independent events for every candidate plan and (ii) the
events have the distributions of §2.2. The world keeps the §2.3 layout.

## Decision

Rollout i draws from `SeedSequence(derive_seed(seed, "rollout", i)).spawn(2)`: the first child
samples the belief (one uniform per activity and worker), the second spawns one stream each for
D1, D2 and D3 after day t. Each process jumps from event to event with geometric gaps,
`G = 1 + floor(ln(1 − u) / ln(1 − p))`, the waiting time of its Bernoulli sequence:
- D1: block rows `(round r, worker w)` hold (gap, L, L_low) of the r-th absence of w; draws
  resume on day t + 1, or the day after a sampled return; L and L_low as in the world.
- D2: block rows `(round r, activity j)` hold (gap, F) of the r-th shock of original activity j;
  work days are counted from the start of the rollout.
- D3: blocks of 8 arrivals hold (gap, template, successor, predecessor uniforms), then 8 PERT
  multipliers; arrivals start on day t + 1.

Blocks cover every worker or activity and are drawn in order when needed (4 rounds, 32-day
chunks of onsets), so the k-th event of a worker or activity always reads the same uniforms.

## Alternatives considered

| Option | Why not |
| --- | --- |
| World streams (`ScenarioStreams`) per rollout | 1.2 ms of stream set-up per rollout, 0.24 s per J30 forecast of 200 rollouts |
| One (horizon × workers) Bernoulli matrix per rollout | The horizon is unknown before the run; rows up to `max_days` = 5 D waste about 4× the draws |
| One generator for all processes | Lazy draws would interleave in a state-dependent order and break (i) |
| Re-using the world's absolute D2 work-day counter | Not observable; the counter only indexes the stream, so restarting it changes no distribution |

## Consequences

Absence onsets, lengths, announcements and D3 arrival days, templates and multipliers depend only
on the rollout seed and the observation, so every candidate sees the same sampled world (spec
§5.1 rollout CRN); D2 shocks of an activity are the same for the same work days. A rollout and
the world with the same seed are not comparable event by event, only in distribution: the
day-0 test compares 2000 rollouts with 2000 world runs, and `tests/test_rollouts.py` checks the
gap, length and factor means. Unused rows of a block cost a few hundred uniforms per rollout.
