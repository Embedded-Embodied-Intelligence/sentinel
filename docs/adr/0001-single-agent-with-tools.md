# ADR-0001: One agent with tools instead of a multi-agent system

- Status: accepted
- Date: 2026-10-19
- WP: design

## Context

Recent work on agentic project management proposes collectives of specialised agents
(e.g. nine agents in three layers). Multi-agent coordination adds failure modes and makes it
hard to attribute outcomes to components. Our research questions concern decision quality,
not agent count.

## Decision

Sentinel is a single agent whose tools are a solver (CP-SAT), a scheduler (SGS), a simulator
(Monte Carlo rollouts) and a narrowly scoped LLM.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Multi-agent (planner, risk, resource agents) | more coordination complexity; no evidence it improves decisions; harder ablations |
| LLM as central decision maker | non-deterministic, unverifiable decisions; hard to evaluate |

## Consequences

Every decision is traceable to goals, rollout estimates and permission rules. Ablations
(with/without LLM) are clean. Multi-agent designs remain future work.
