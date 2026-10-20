# ADR-0007: Simulator random streams and engine shortcuts

- Status: accepted
- Date: 2026-10-20
- WP: WP2a

## Context

Spec §2.3 fixes one `SeedSequence` child stream per worker (absences), per original activity
(D2), and one each for durations and D3. WP3 and WP5 call `simulate` thousands of times per
decision; WP2a targets 5 ms (J30) and 15 ms (J60) per call. numpy's `geometric`, `integers` and
`beta` consume a varying number of raw draws. J30 instances have 81 workers on average, and a
NoReaction run lasts about 2.3 times its plan with a decision epoch on ~60% of its days.

## Decision

Absence and D2 variates are functions of single uniforms read by position, so streams can be
drawn in blocks: `L = 1 + floor(ln(1-u) / ln(1-q))` (geometric(q) by inversion),
`L_low = 1 + floor(u L)` and `F = f_low + (f_high - f_low) u`. D3 draws come in 128-day chunks
(four uniforms per day, then one PERT multiplier per day). The engine also takes three
shortcuts that leave results unchanged:
- dispatch tries only today's planned starts when no worker was freed and no activity became
  eligible since the last dispatch;
- a policy marked `passive` (NoReaction) is not called, so no observation is built for it;
- observations and results are built with `model_construct`.

## Alternatives considered

| Option | Why not |
| --- | --- |
| numpy `geometric` and `integers` at each onset | Same distributions, but the varying number of raw draws rules out reading a block by position. |
| One scalar draw per worker and day | About 0.3 µs per call times workers times days: more than 10 ms per J30 run. |
| Validated pydantic observations and results | 5 µs per epoch plus 0.25 ms per result. Tests validate round trips instead. |
| One stream shared by all workers | Violates §2.3, and absences would shift when the worker set changes. |

## Consequences

Results are identical to the straightforward version. The streams give the same answers as
the first implementation (commit 6dc2208) for 60 seed/parameter combinations, and the
dispatch shortcut leaves 200 runs unchanged. Calls take 4.8 ms (J30) and 8.3 ms (J60) on
average. About 1.2 ms of that is creating ~110 seed sequences and PCG64 generators. Answers
of `ScenarioStreams` do not depend on query order, so WP5 can reuse one per seed across
candidates. A passive policy that returned operations would be ignored silently, so
`passive` is a documented promise on `Policy`.
