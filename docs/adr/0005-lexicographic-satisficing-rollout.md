# ADR-0005: Lexicographic, satisficing rollout decision rule

- Status: accepted
- Date: 2026-10-19
- WP: design (implemented in WP5)

## Context

Goals have a natural priority (feasibility > deadline > budget > stability). A weighted sum
needs arbitrary weights and keeps buying deadline probability at any cost.

## Decision

One-step rollout policy on base policy NoReaction (spec §6), lexicographic order with the
deadline probability capped at `θ_D` (satisficing, Simon 1955). NOOP is always a candidate.
A scalarised rule is kept as an ablation.

## Consequences

Decisions are explainable by goal level. The cap prevents over-reaction. Ties are judged with
paired standard errors under common random numbers.
