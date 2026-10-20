# ADR-0008: Deterministic CP-SAT baseline plans and their cache

- Status: accepted
- Date: 2026-10-20
- WP: WP2b

## Context

Every policy of WP2–WP7 starts from one baseline plan per instance, and compared policies must
start from the same plan (common random numbers, §2.3). WP1 runs CP-SAT with a wall-clock limit
(ADR-0006); 75 of 480 J60 instances still hit it at 10 s, so their plans depend on CPU speed and
load. CP-SAT's `max_deterministic_time` counts machine-independent work units instead. Probed on
the i5-6600K with four solves in parallel: one unit takes 2.1–2.7 s of wall time; on four hard
J60 instances, limits 2 / 5 / 10 give makespans 123 / 121 / 120 (j6013_1, best known 112),
117 / 115 / 115, 122 / 121 / 120 and 134 / 131 / 131 (WP1 CP-SAT 10 s: 121, 117, 120, 133).
Plans take minutes to compute for a whole set and are reused by later WPs.

## Decision

`cpsat_det` runs CP-SAT with one worker, a fixed seed (2026) and `max_deterministic_time = 5`
without a wall-clock limit. Plans are cached in `data/derived/baselines/<set>/<instance>.json`
(gitignored), one entry per method with the instance's SHA-256, method parameters, status,
bound, deterministic time, runtime and package versions; an entry is reused only if parameters,
instance hash, cache version and, for CP-SAT, the OR-Tools version match.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Wall-clock limit as in WP1 | Plans of instances that hit the limit depend on machine load. |
| Deterministic limit 10 | About twice the time; at most one day shorter on the probed instances. |
| Deterministic limit 2 | Up to 10 % above the best known makespan (j6013_1: 123 vs 112). |
| SGS-LFT solution hint for CP-SAT | Changes the WP1 model; not needed for quality. |
| Committing the plans | Derived data is reproducible from code; data policy keeps it out of git. |
| Reusing entries across OR-Tools versions | A solver upgrade would silently mix plans of two versions. |

## Consequences

A plan does not depend on machine load; across machines it needs the same OR-Tools version
(enforced by the cache check) and is expected to match on the same platform. Deterministic units
are not seconds, so the cost of a set must be measured (WP2b report). Two processes writing
different methods of the same instance at once could lose one entry; files are replaced
atomically, so they are never torn.
