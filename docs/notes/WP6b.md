# WP6b notes — RQ5: what the LLM contributes (events, proposals, explanations)

**Design principle.** The LLM has three narrow roles (spec §10) and never decides: its answers
are validated and enter the decision layer only as compiled objects. Each role is measured
offline against exact ground truth that no LLM wrote (templates, recorded decisions), with both
backends of WP6a (Ollama `qwen2.5:7b`, Groq `openai/gpt-oss-120b`, temperature 0, schema-guided
JSON, record/replay cache), and the proposals against a random control from the same grammar.

**Team calendar** (§10.1). Day 0 is a Monday; working days Monday–Friday, no holidays; one
simulation day = one working day, so day `t` is weekday `t mod 5` of week `⌊t/5⌋`. "On
<weekday>" names the first such day after today (1–5 days later), "next week" the Monday
`5(⌊t/5⌋ + 1)`.

**Role 1: event parser.** A fictional roster gives every original worker a unique name, a first
name and an initial ("Ada K."; 60 first names × 26 initials, seeded permutation; J30 teams have
36–219 workers), activities carry the WP6a narrator's names. Messages are written from seeded
templates in the state of a NoReaction world: the author and day are given ("Message from Ada
K. on day 23 (Wednesday)"). Facts, uniform over four kinds: an *absence* of a present original
worker (the author's own in half of the single-absence messages: "I can't come in today"), its
return as a weekday (L_low ∈ 1..4, so the weekday is unambiguous), "about N days" (N ∈ 2..10),
"next week" or unknown (`return_day = null`, L_low = 1), with a personal reason in half of them
("the flu", "a family matter", "a doctor's appointment", … 12 phrases); a *work increase* of a
running activity: "about x % more" (x ∈ {20, 30, 40, 50, 60, 80}, F = 1 + x/100), "twice as
long" (F = 2) or "another d days" (d ∈ 1..5, F = (r + d)/r with the remaining work r shown to
the parser, one decimal; F to two decimals); a *new activity* in the style of D3: duration and
crew of a real original activity with a crew, a fresh vocabulary name, successor an unstarted
real activity (the release in a quarter of the messages), predecessor valid by the D3 rules (the
start in a quarter); *noise*: stand-up moves, praise, questions, lunch. 20 % of the messages have
2–3 facts; a third opens with a greeting; numbers are words with probability 1/2. A template
parser reads every message back exactly (tested on 650 messages of three J30 instances and in
the test suite).

**Output schema** `{"events": [...]}` with `absence {worker, return_day}`, `work_increase
{activity, factor}`, `new_activity {name, duration, crew {role: n}, after, before}` (null:
source / release), extra fields forbidden. **No field can hold a reason** (invariant 7): an
answer that adds one ("reason": "flu") is rejected with an issue that names the field but not
its value, and repaired. Validation (16 issue kinds): JSON, missing/invalid fields, unknown type,
unknown or already absent worker, return day `≤ t` or more than a year away, unknown activity,
work increase of an activity that is not running, factor < 1, new activity with duration < 1,
unknown role, crew above `R_k`, name in use, invalid placement (successor not unstarted,
predecessor removed, equal to or a descendant of the successor), a repeated worker, activity or
name. Events are accepted one by one; the WP6a repair loop (≤ 3 rounds, previous answer and
issues sent back, same seed) runs while issues remain. `apply_events` applies accepted events to
the observation as the engine would (absences in worker order, a running activity without a
present crew member paused; shocks `(j, e_j, F)`; new activities by name with the next ids,
planned at the earliest precedence-feasible day ≥ t + 1), so the result does not depend on the
order of the answer.

**Role 2: action grammar** (§10.3). `{"proposals": [{"operations": [...]}]}`, ≤ 3 proposals of
1–3 operations: `SHIFT`, `RESEQ {objective: makespan | stable}`, `SUBST {activity}` (every absent
member that an idle worker of its role can replace, AlwaysSubstitute order), `OVERTIME {role,
workers ≤ ⌊γ R_k⌋, days 1–20}`; no DESCOPE. Compilation reuses the WP5 builders: the non-plan
operations apply in the given order through the engine (`rehearse`), each SUBST choosing its
substitutes on the state the earlier ones leave (an earlier OVERTIME's temporary workers may
substitute, a combination no rule candidate has); the single plan operation is planned last on
the state they leave (`prepare`; RESEQ by CP-SAT on the planning view with the temporary
workers), with the candidate kinds `proposal`, `proposal_shift`, `proposal_reseq_m`,
`proposal_reseq_s`. A compiled proposal with the effect of a rule candidate or an earlier
proposal (equal non-plan operations and planned starts of the activities with p_j > 0, the
rule candidates' own duplicate test) is flagged and not evaluated.

**Random control.** Three proposals per state, seeded per state: 1–3 operations (uniform), each
operation's type uniform among those still available (a plan operation at most once, SUBST of an
eligible activity not yet used, OVERTIME of a role with ⌊γ R_k⌋ ≥ 1 not yet used), parameters
uniform. Drawing over the operations *valid in the state* (not over all grammar instances) makes
the control strong: a win of the LLM over it is judgment, not validity.

**Decision states.** Sentinel `full` rerun on the 120 worlds of the WP5 J30 ablation subset at
λ_A ∈ {0.01, 0.02} (replication 0): every rerun reproduces the WP5 makespan and number of gated
deliberations. The 5,469 deliberations that passed the needs gate are stored (observation with
plan, `DecisionRecord`, run seed; 0.45 KB per state compressed) and reproduce exactly from the
observation and the seed. Sample: 150 states, 12 strata (λ_A × tercile of the duration-weighted
share of nominal work done × rule chose NOOP), equal shares (12–13), seeded choice within strata.

**Proposal study.** Per state the rule candidates are regenerated and raced on the recorded
epoch's worlds (seed `derive_seed(run seed, "sentinel", day)`, N₁ = 25, N = 100), reproducing the
recorded choice (checked); each source's usable proposals are raced with them on the same worlds
and the §6 rule chooses. Win: a proposal of the source is the choice; gain: its min(p̂, θ_D) and
T̂ against the rule's own choice on the same N worlds.

**Role 3: explanations** (§10.4). The record is rendered with a plain description per candidate,
its statistics and where it left the comparison, the choice, runner-up and deciding component.
Answer `{summary ≤ 80 words, cited_facts [{kind, value}]}`. Faithfulness: each cited fact equals
the record (numbers within the rounding of the written value; probabilities and the overrun as
fractions or percentages); the chosen action cited; the deciding component cited and right;
every number in digits in the summary matches a number of the rendered record within its
rounding (else hallucinated). Number words ("three") are not checked.

**Prompts v1** (`src/sentinel/llm/prompts/`): `events_parse` (types, return-day, factor and
placement rules, the calendar, "I" is the author, never record why someone is absent),
`events_repair` (the WP6a repair message), `proposals` (the rule's order, the grammar with one
line per operation, plan operation computed last, repeat nothing), `explain` (the components of
the rule, the answer format and the seven kinds, cite chosen action and component, no numbers
beyond the record). The files are the source.

**Smoke measurements** (2026-10-23; no Ollama call, the GPU served the RQ1 run). gpt-oss-120b on
Groq: 20 of 20 messages exact in one call (1,471 prompt + 115 completion tokens, 0.77 s); 15 of
15 proposals compiled, none duplicates, every one with OVERTIME (two workers per role), 1 of 5
states won (+0.18 in min(p̂, θ_D), −2.07 days of T̂), as many as the random control, whose win
tied in p̂ and T̂ and came from stability; 5 of 5 explanations fully faithful (28 cited facts
correct, 0 hallucinated numbers, 28 words). Groq once answered a noise message with plain "No
events." (HTTP 400 `output_parse_failed`), now returned as an answer for the repair loop.
