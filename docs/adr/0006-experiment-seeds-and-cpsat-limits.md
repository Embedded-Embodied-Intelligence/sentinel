# ADR-0006: Experiment seeds and CP-SAT determinism

- Status: accepted
- Date: 2026-10-20
- WP: WP1

## Context

Invariant 1 requires explicit seeds and common random numbers (CRN) for compared methods. The
experiment-run skill asks for seeds derived per (instance, method, replication). CP-SAT with
`num_workers = 1` and a fixed `random_seed` searches deterministically, but
`max_time_in_seconds` is a wall-clock limit: a run that stops at the limit depends on CPU speed
and load. CP-SAT also offers `max_deterministic_time` (machine-independent work units). WP1
defines the CP-SAT methods by seconds (`cpsat_1s`, `cpsat_10s`) and compares runtimes.

## Decision

Each instance (and later each replication) gets one seed, `derive_seed(base_seed, *keys)`: a
SHA-256 of the keys as `SeedSequence` entropy, 31 bits, shared by all randomized methods on it
(CRN); deterministic methods record no seed. Benchmarks run CP-SAT with one worker, that seed
and the configured wall-clock limit.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Seeds per (instance, method) | Breaks CRN; `cpsat_10s` would no longer continue the `cpsat_1s` search. |
| `SeedSequence(base).spawn()` by position | Seeds change with `--limit` or the instance list. |
| `max_deterministic_time` as the limit | Machine-independent, but no longer a time budget in seconds comparable with heuristic runtimes, as WP1 specifies. |

## Consequences

Smoke and full runs give identical rows for the same instances; on the M1, repeated runs were
identical apart from runtimes, including 16 CP-SAT runs that stopped at the limit. Rows with
status FEASIBLE/UNKNOWN may differ on another machine; `results.csv` marks them and the manifest
records CPU and cores. CP-SAT inside simulation replications (WP4+: FullResolve, RESEQ) must be
deterministic for CRN, so WP4 must choose a deterministic-time limit or none.
