# ADR-0014: Layout of the agent package

- Status: accepted
- Date: 2026-10-21
- WP: WP5a

## Context

WP5a builds Sentinel (spec sections 5 and 6): rule candidates, their rollout evaluation, the
decision rule and a policy the engine consults at decision epochs. WP5b adds the permission
gate, deferral, the simulated human and DESCOPE; WP6 adds LLM-proposed candidates and
explanations; WP8 shows decisions in a dashboard. `docs/spec/architecture.md` reserves `agent/`
for needs, candidates, rollout selector and gate, and `policies/` holds every compared policy,
which the study runners create by name (`policies/registry.py`). Operations act only through
the engine (`Run.apply`), in the world and in rollouts.

## Decision

`sentinel.agent` holds the decision layer in four modules with one-way imports: `params`
(`SentinelParams`), `candidates` (`Candidate`: label, kind, `Decision` in the operation grammar,
resulting plan; `generate`), `evaluate` (`Evaluator`, `race`, `CandidateStats`) and `decide`
(`choose`, `Needs`, `DecisionRecord`). `sentinel.policies.sentinel.Sentinel` is a thin policy
(deliberation epochs, needs gate, orchestration, statistics, one `DecisionRecord` per epoch),
registered with its variants next to the baselines.

## Alternatives considered

| Option | Why not |
| --- | --- |
| One module `agent/sentinel.py` | About 700 lines mixing generation, simulation and the rule; each part is tested alone |
| The policy class inside `agent/` | Breaks the convention that `policies/` holds what runners compare; the registry would import from two places |
| Candidates as callables (rules applied in each rollout) | Not serialisable: LLM proposals (WP6) and decision records need the operations as data |
| Evaluation inside `forecasting/` | `forecast` evaluates one plan; candidates need an action applied before the rollout resumes, shared worlds and racing |

## Consequences

- The engine stays the only place where operations act: `generate` keeps a candidate only if
  `rehearse` (the engine's `Run.apply` on the observed state) rejects none of its operations,
  and rollouts apply it with the same `Run.apply`.
- WP5b's gate fits between `choose` and the returned decision, WP6's proposals become
  `Candidate`s before `race`, and the `DecisionRecord` (pydantic, JSON) feeds explanations
  and the dashboard.
- `run_checked` and `run_policies` run Sentinel like any baseline (`make_policy` passes the
  run's seed), so the WP4b machinery and its checks serve WP5 measurements and studies.
