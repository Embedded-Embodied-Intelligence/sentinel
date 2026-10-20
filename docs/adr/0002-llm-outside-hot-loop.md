# ADR-0002: LLM outside the hot loop, with record/replay caching

- Status: accepted
- Date: 2026-10-19
- WP: design (implemented in WP6)

## Context

Rollouts require thousands of evaluations per decision. The local GPU (GTX 1060 6 GB) runs a
7B model at ~17 tokens/s; the cloud API has rate limits. LLM outputs are non-deterministic,
which would break reproducibility.

## Decision

The LLM is called only at decision epochs (event parsing, candidate proposals, explanations),
never inside rollouts. Every call goes through a cache keyed by (model, prompt, parameters);
experiments replay cached responses. Outputs are validated against JSON schemas (pydantic).
Prompts are in English.

## Alternatives considered

| Option | Why not |
| --- | --- |
| LLM scores candidates inside rollouts | infeasible compute; irreproducible |
| No cache, live calls | irreproducible; costly; blocked by rate limits |

## Consequences

Experiments are reproducible without API access. The cache is committed (small text).
The LLM's contribution is measurable by ablation (RQ5).
