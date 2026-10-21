# ADR-0012: Representation of the residual problem

- Status: accepted
- Date: 2026-10-21
- WP: WP4a

## Context

FullResolve and StableResolve plan the rest of a running project at a decision epoch (spec
§4.1): unstarted activities with nominal durations, started ones holding their whole crew until
the estimated finish F̂_j of the deterministic forecast (§5.2), absent idle workers away until
their nominal return. The engine must check every RESEQ plan against the same problem, and WP5
will decode candidate plans with a residual SGS inside rollouts, so building and decoding must
take well under a millisecond. The static `ProjectInstance` (§1) has constant capacities, no
release dates and ids `0..n+1`; D3 activities break topological id order.

## Decision

`ResidualProblem` (frozen pydantic) holds only the unstarted activities, by position in
increasing id order: ids, p_j, r_jk, successor positions, the fixed finish of finished
(realised) and started (F̂_j) predecessors, and the planned start. Started activities and absent
idle workers enter only through a per-role piecewise-constant capacity profile, steps
`(first day, capacity)` from day t that end at R_k. F̂_j is computed directly from the nominal
state with the engine's own daily subtraction. The module is pure Python; CP-SAT
(`cpsat.solve_residual`) turns each capacity dip into a fixed interval of the role's cumulative.

## Alternatives considered

| Option | Why not |
| --- | --- |
| A derived `ProjectInstance` with dummy activities for reservations | Needs fixed starts and release dates that §1 has not, renumbering of ids and of D3 activities; validation messages would name dummies |
| Day-indexed capacity arrays | The horizon is not known before planning; steps are exact and short, and the SGS expands them to arrays itself |
| Activity-id dictionaries throughout | Easier to read, slower in the SGS loop; ids are kept in `activities` and used at the interface (`Reseq`, `validate_residual`) |
| F̂_j from a full deterministic rollout | One source of truth, but about 0.5 ms per view instead of 0.1 ms; the direct computation is tested equal on 100+ started activities |
| CP-SAT in `residual.py` | The engine imports the module for RESEQ checks; loading OR-Tools alone makes NoReaction `simulate` 2-5 % slower (larger heap) |

## Consequences

A planning view takes 0.13 ms (J30) and 0.19 ms (J60), and a residual SGS decode 0.10 / 0.18 ms
(medians over 40 views each, WP4a report), which leaves room for decoding plans in WP5 rollouts.
Positions must be mapped to ids at the boundary. The CP-SAT horizon is the residual SGS-LFT
makespan, so CP-SAT is never worse than the SGS and the SGS schedule is always a feasible hint.
OVERTIME (WP5) would add steps above R_k; the profile check and the cumulative capacity would
then use the profile's maximum instead of R_k.
