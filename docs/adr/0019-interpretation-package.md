# ADR-0019: Interpretation package with compiled LLM output and a proposer hook

- Status: accepted
- Date: 2026-10-23
- WP: WP6b

## Context

RQ5 measures the LLM's three roles (spec §10): parsing team messages into events, proposing
candidate actions in a fixed JSON grammar, and explaining decisions, each offline against exact
ground truth, and the proposals against a random control from the same grammar. Invariant 3 and
ADR-0002 keep the LLM out of rollouts and the simulator; the decision layer must stay
deterministic and choose by the rule of §6 only. The WP5 builders (`prepare`, `plan_part`,
`rehearse`) already turn operations into checked candidates. The optional online check needs
proposals inside Sentinel's deliberation, and the agent and policy packages must not import the
LLM layer.

## Decision

A package `sentinel.interpret` (team calendar and roster, `events`, `messages`, `actions`,
`describe`, `explain`) is the only bridge: every LLM answer is validated there and enters the
decision layer only as compiled objects: events applied to an observation by `apply_events`,
proposals compiled by `compile_proposal` through the WP5 builders into `Candidate`s (new kinds
`proposal`, `proposal_shift`, `proposal_reseq_m`, `proposal_reseq_s`; the rule kinds `KINDS`
unchanged). Sentinel takes an optional `proposer` callable that receives the observation, the
record of the raced rule candidates and the candidates, and returns compiled ones; they are raced
again with the rule candidates on the same worlds.

## Alternatives considered

| Option | Why not |
| --- | --- |
| LLM proposals as a Sentinel variant inside `agent/` | The agent would import the LLM layer; the boundary test forbids it |
| One proposal kind with the objective stored in the label | `prepare` and `approve` derive the plan part from the kind; a label is no contract |
| Add the proposal kinds to `KINDS` | Changes the columns of the policy studies and the summaries of committed WP5 runs |
| LLM computes factors and day numbers free-form, code trusts them | Unvalidated numbers would enter the observation; validation and the repair loop catch impossible ones |
| Random control over all grammar instances (any activity, any role) | Most draws would be invalid, so the LLM would win on validity alone, not on judgment |

## Consequences

- The LLM never decides: proposals are evaluated by rollouts and chosen by the rule, and
  duplicates of rule candidates (same effect) are not evaluated, so a win is the LLM's own idea.
- A proposal's plan operation is always planned last, whatever its place in the list (§10.3).
- Without a proposer, Sentinel is unchanged (tests compare runs with an empty proposer).
- An online run calls the LLM once per gated deliberation (about 40 per J30 run at
  `λ_A = 0.01`), so it is expensive on rate-limited backends.
