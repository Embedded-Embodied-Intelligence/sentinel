# WP6b — RQ5: what the LLM contributes (event parsing, candidate proposals, explanations)

Fresh session (`/clear`). Read before coding:

<context>
- `CLAUDE.md`, `docs/spec/model.md` (§2.2 events, §4 actions, §6 candidates and rule),
  `docs/spec/architecture.md`, `docs/experiments/plan.md`
- `docs/reports/WP6a.md`, `docs/notes/WP6a.md`, ADR-0018, `src/sentinel/llm/`,
  `src/sentinel/agent/{candidates,evaluate,decide}.py` (`DecisionRecord`)
- skills `spec-guard`, `adr`, `experiment-run`, `wp-report`

**RQ5:** *What does the LLM contribute to the agent?* The LLM has exactly three roles
(architecture): (1) turn unstructured team messages into events, (2) propose candidate actions
in a fixed JSON grammar, (3) explain decisions. Each role is measured **offline against exact
ground truth** with both backends (Ollama `qwen2.5:7b`, Groq `openai/gpt-oss-120b`), and the
proposals are measured against a **random-proposal control** from the same grammar, so the
LLM's value is separated from "any extra candidate helps".

**Concurrency (binding):** the owner may be running the WP6a RQ1 Ollama study while you work.
Do **not** call Ollama in this session (the GPU is busy; use the fake backend and Groq for
smokes), do not touch `results/wp6/` or `data/llm_cache/` files you did not create, and never
`git add` paths outside your own changes. Groq free plan: 8K tokens/min, 200K/day — keep
smokes small.

Answers to the WP6a spec questions (binding): (1) add `wbs/` to the layout as proposed;
(2) extracted *real* activities must have duration ≥ 1 (PSPLIB real activities do); write it
into §1; (3) name the R1–R4 → backend developer, frontend developer, tester, DevOps engineer
display mapping in §1.1.
</context>

<task>
0. **Spec v1.9 and architecture** (commit `spec: interpretation layer (v1.9)`): answers 1–3; new
   §10 **Interpretation layer** with: the team calendar (day 0 = a Monday, working days Mon–Fri,
   one simulation day = one working day), the event-message schema, the action grammar and its
   compilation (task 2), the explanation schema, and the rule that LLM output only ever enters
   the decision layer through validated, compiled objects.
1. **Event parser (role 1)** `src/sentinel/interpret/events.py`:
   - Message generator (deterministic templates, seeded, English): a fictional team roster
     (first names ↔ worker ids, roles), messages dated by weekday and day. Kinds: absence
     (worker; return stated as a weekday, "about N days", "next week", or unknown; *sometimes
     with a personal reason*, e.g. "sick", "family matter"), work increase (activity by name;
     "about 50 % more", "twice as long", "another 2 days"), new activity (name, duration, crew,
     after/before activities by name), and noise (no event: meeting moves, praise, questions).
     Several facts per message in 20 % of messages.
   - Output schema: a list of events `{type: absence | work_increase | new_activity, ...}` with
     worker id, announced return lower bound as a day number, activity id, factor, or the new
     activity's fields; an empty list for noise. **No field can hold a reason** (GDPR Art. 9,
     invariant 7); a test asserts that no output string contains any reason word from the
     generator's list.
   - Validation (unknown worker/activity, impossible days, factor < 1) + the WP6a repair loop.
   - Metrics: message-level exact rate, per-event-type precision/recall, field accuracy, noise
     false-positive rate, return-day accuracy, privacy leak count (expected 0); plus an
     end-to-end check that the parsed events applied to a state give the same `Observation` as
     the true events.
2. **Action grammar and compiler (role 2)** `src/sentinel/interpret/actions.py`: a proposal is
   ≤ 3 operations from `SHIFT`, `RESEQ{objective: makespan | stable}`, `SUBST{activity}` (all
   eligible absent members of that activity, AlwaysSubstitute order), `OVERTIME{role, workers ≤
   floor(γ R_k), days 1–20}` (DESCOPE excluded). `compile(proposal, observation) ->
   Candidate | Issue` reuses the WP5 candidate builders (CP-SAT plans for RESEQ with the
   temporary workers, level `ℓ` from §4). Duplicates of rule candidates (same operations after
   compilation) are flagged.
3. **Decision-state set** `scripts/record_decision_states.py`: rerun Sentinel `full` (Λ = 3) on
   the plan's J30 ablation subset (every 8th instance), `λ_A ∈ {0.01, 0.02}`, replication 0, and
   save every deliberation that passed the needs gate (observation + plan + the rule
   candidates' `DecisionRecord`) to `data/derived/decision_states/` (gitignored; reproducible
   from seeds); pick a stratified sample of **150 states** (by `λ_A`, project progress tercile,
   and whether the chosen rule action was NOOP), sample ids committed in the config.
4. **Proposal study (role 2)** `src/sentinel/experiments/proposal_study.py`, config
   `configs/wp6_rq5_proposals.toml`: for each state render a compact English state summary
   (day, deadline, NOOP forecast p̂ and T̂, at-risk activities with urgency, absent workers by
   role with announced return, idle workers per role, backlog per role, budget status, the rule
   candidates with their statistics) and ask for up to 3 proposals in the grammar. Compile,
   validate, then evaluate **together with the rule candidates on the same worlds** (WP5
   evaluator, N₁ = 25, N = 100, CRN) and apply the §6 rule. Sources: `ollama`, `groq`,
   `random` (3 proposals sampled uniformly from the grammar with a seed per state). Metrics per
   source: validity and compile rate, duplicate rate, **win rate** (share of states where a
   proposal of that source is the §6 choice over all rule candidates), mean gain in
   `min(p̂, θ_D)` and `T̂` over the best rule candidate when it wins (paired SE), tokens and
   latency. Paired comparison LLM − random with bootstrap over states.
5. **Explanations (role 3)** `src/sentinel/interpret/explain.py`: from a `DecisionRecord`, the
   LLM writes `{summary (≤ 80 words, for a project manager), cited_facts: [{kind, value}]}`
   (kinds: chosen_action, p_on_time, tardiness_days, budget_overrun, alternative,
   alternative_p_on_time, deciding_component). Faithfulness checks: every cited fact matches the
   record (numbers within rounding), the chosen action is named, the deciding component is
   right, and every number in the summary text appears among the record's values
   (hallucinated-number count). Study on the same 150 states, both backends; metrics:
   fully-faithful rate, per-kind accuracy, hallucinated numbers per explanation, words.
6. **Optional online check** config `configs/wp6_rq5_online.toml` (Groq only): Sentinel `full`
   with LLM proposals added at each deliberation that passed the needs gate, 20 J30 instances
   (every 24th), `λ_A = 0.01`, R = 1, compared with Sentinel `full` on the same worlds (from the
   WP5 results). Smoke with 1 instance on the fake backend only; give the token estimate.
7. **Smoke** each study on the fake backend (2–3 states / 20 messages) and on Groq (≤ 5 states,
   ≤ 20 messages, within the free limits); measure tokens and latency; give owner commands with
   duration and token estimates for Ollama (after the RQ1 run) and Groq, each committing its
   results, resumable after rate-limit exits as in WP6a. Replay bundles as in WP6a.
8. **Tests** (fake backend): message generator round trip (a template parser recovers the
   events); reason words never reach outputs; grammar compile/validate on hand-made proposals
   (valid, invalid role, too many workers, unknown activity, duplicate of a rule candidate);
   random-proposal sampler deterministic per seed; explanation checker on a faithful and on a
   hallucinating scripted answer; the decision-state recorder reproduces a recorded record.
9. `wp-report` (`docs/reports/WP6b.md`, `docs/notes/WP6b.md` with prompts, grammar and
   metrics); ADR for the interpretation package.
</task>

<constraints>
- LLM never inside rollouts or the simulator; proposals enter only as compiled candidates.
- No Ollama calls in this session; Groq only within the free limits.
- Secrets as in WP6a. No new runtime dependencies. Default `pytest -q` ≤ 75 s.
- Commit after each step group; do not stage `results/wp6/` or caches you did not create.
</constraints>

<acceptance_criteria>
1. Spec v1.9 commit (with §10 and the architecture update).
2. Quality gate and `-m "data or slow"` pass; task-8 tests exist and pass.
3. Decision-state sample recorded and its ids committed; all smokes produce their outputs.
4. Owner commands with duration and token estimates for every full run.
5. Report, notes, roadmap (`WP6: in progress: WP6b smoke done`); pushed; clean tree.
</acceptance_criteria>

<report_format>
`docs/reports/WP6b.md` via `wp-report`. "Numbers": smoke metrics per role and backend, token and
latency figures, duration and token estimates.
</report_format>
