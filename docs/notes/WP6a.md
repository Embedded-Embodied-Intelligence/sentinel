# WP6a notes — LLM layer, WBS narrator and the RQ1 design

**Ground truth without circularity.** RQ1 needs project descriptions whose exact model is
known. They are generated from PSPLIB J30 instances by templates (`sentinel.wbs.narrate`), not
by an LLM, so the instance is the ground truth and the LLM must recover it from the text. Roles
R1–R4 become the backend developer, frontend developer, tester and DevOps engineer; every real
activity gets a unique name, a verb and an object from a vocabulary of its dominant role (most
people, ties to the lower role; e.g. "Implement payment API", "Polish notification center",
"Validate search feature", "Migrate container registry"). Objects are drawn without
replacement per role (a seeded permutation) and verbs at random; no name contains a comma,
"and", a digit or a period. The text states the team (people per role) and, per activity, its
name, duration in working days, crew per role and immediate predecessors by name; the dummy
source and sink are implicit, and an activity without real predecessors is stated to start
right away. The seed of an instance is shared by both styles, so the names agree.

**Styles.** `structured`: one block per activity in topological order (smallest ready id first)
with fixed lines `Duration`, `Crew`, `Predecessors`. `narrative`: prose paragraphs of one to
three activities in a shuffled order; six one-sentence and two two-sentence phrasings of name,
duration and crew; each real precedence is stated once, with probability 1/2 on the successor
("It can only start once "A" and "B" are done.", six phrasings) and otherwise on the
predecessor ("It must be finished before "C" begins.", five phrasings); every number is
written in words with probability 1/2. J30 texts have 4.4–6.7K characters (structured) and
5.2–8.1K (narrative), about 1.4–2.0K tokens with the system prompt. A template parser
(`parse_narration`) reads both styles back; it recovers all 40 study instances exactly and
rejects any fact stated twice, so every fact appears exactly once.

**Output schema** (`Extraction`, sent as JSON schema: Ollama `format`, Groq best-effort
`json_schema`): `{team: [{role, count}], activities: [{name, duration_days, crew: {role: n},
predecessors: [name]}]}`, every field required, no other fields. Titles and descriptions are
dropped from the schema sent, so that a docstring edit changes no cache key.

**Validation** (`validate_extraction`): pydantic structure first (`missing_field`,
`invalid_field`, also for a missing name), then the model: `duplicate_role` (team or crew),
`negative_count`, `unknown_role` (a crew role with people outside the team), `duplicate_name`,
`unknown_name` (a predecessor that is no activity), `cycle` (one per strongly connected
component, Tarjan 1972, with a shortest cycle listed), `non_positive_duration`,
`crew_above_capacity`; plus `invalid_json` for an answer that does not parse or was cut off.
Names match after NFKC, case folding and collapsing every other character run to one space;
role names also lose a plural "s". A valid answer becomes a `ProjectInstance` with roles in
team order, activities in answer order, source and sink added.

**Repair loop.** Round 0 is the single-shot call `[system, description]`. While the answer has
issues and fewer than 3 repair rounds were made, round r sends `[system, description,
assistant: previous answer as compact JSON (its text if it did not parse), user: issue list
(at most 40 lines) + request for the corrected full JSON]`; the conversation does not grow,
every round has the same seed. A repair request that cannot fit the backend's limits ends the
session (recorded in `stopped`). With deterministic decoding a round whose answer repeats the
previous one makes the next request identical, so it repeats again (from the cache, recorded
with the original call's tokens and latency); `unchanged_rounds` counts such rounds.

**Feedback wording matters.** Each issue message names the place in the answer and what to
check, e.g. `The activity "X" lists the predecessor "Y", which is missing from "activities";
add "Y" as the description states it, or correct the name.` A first wording, "…which is not
an activity of the project", contradicted the description (the activity is described there,
only missing from the answer): in the first Ollama smoke qwen2.5:7b returned its narrative
answer unchanged in every repair round.

**Prompts v1** (`src/sentinel/llm/prompts/`). System prompt `wbs_extract.v1.txt`:

> You extract the work breakdown structure of a software project from its description.
> Answer with one JSON object and nothing else. It has two fields:
> - "team": one entry per role, {"role": <the role name in the singular, e.g. "backend
>   developer">, "count": <the number of people with that role>}.
> - "activities": one entry per activity (task) of the project: "name": the activity's name
>   exactly as written in the description, without quotes; "duration_days": its duration in
>   working days, a whole number; "crew": the people it needs per role, {<role name as in
>   "team">: <number of people>}; leave out roles it does not need; "predecessors": the names
>   of the activities that must be finished before it can start (its immediate predecessors),
>   [] if it can start right away.
>
> Rules: List every activity of the description exactly once; add no start or end
> milestones. A dependency belongs to the later activity: "B can only start once A is done"
> and "A must be finished before B begins" both mean that A is a predecessor of B. Numbers may
> be written as words; give them as integers. Use only facts stated in the description.

Repair message `wbs_repair.v1.txt`: "Your JSON answer has these problems: `$issues` Correct
them using the project description. Answer with the corrected JSON object for the whole
project, every activity included, in the same format and nothing else." (Line breaks of the
files are shortened here; the files are the source.)

**Metrics** (`sentinel.wbs.score`). Answers are read leniently: each entry that validates on
its own counts. Extracted activities match true ones one to one by normalised name (first
entry wins; unmatched names are listed in `results.csv`). Activity recall = matched / true,
precision = matched / extracted entries. Precedence edges are scored on matched activities
only (precision, recall, F1); a rate over no edges is 1 only for a project without edges, so an
answer that matches nothing scores 0. Duration and crew accuracy are exact matches on matched
activities, pooled over a cell's matched activities in the summary. Team accuracy is the share
of true roles with the exact count. **Exact instance**: valid and isomorphic to the truth under
the name matching (all activities, durations, crews, edges and the team). Downstream, a valid
answer's instance and the true one are solved by CP-SAT with the `cpsat_det` settings (5.0
deterministic s, one worker, seed 2026; schedules validated); the relative error is
(C_extracted − C_true) / C_true. Tokens and latency are summed over a condition's calls.

**Statistics.** Valid, exact and team-exact rates carry 95 % Wilson intervals over sessions.
Repair − single shot is a paired difference within sessions (one session gives both
conditions) with a 95 % percentile interval of a cluster bootstrap over instances (2,000
resamples; a cell pooled over styles has two sessions per instance; pooled accuracies are
resampled as ratios of sums).

**Smoke measurements** (j301_1, 2026-10-23). qwen2.5:7b on the GTX 1060 (`num_ctx` 12288,
76 % in VRAM): about 400 prompt tok/s and 12.4 generated tok/s, about 100 s per call (1.2–1.3K
completion tokens). Structured: valid in one call but one precedence short (makespan 42 vs 43).
Narrative: 5 of 30 activities left out (those named only as predecessors), and the repair
rounds returned the same JSON; a review-style repair message changed the answer but not the
omissions. gpt-oss-120b on Groq: 3.9 s and 6.1 s per call (1.6K prompt, 1.6K and 2.7K
completion tokens with reasoning); structured exact, narrative valid with edge F1 0.92. So the
valid-but-wrong answers that validation cannot see occur on both backends; RQ1's exact-instance
rate and edge F1 measure them.

**LLM layer** (ADR-0018): one protocol and one call path (request → SHA-256 key → cache →
backend → pydantic validation), standard library only. Backends on 2026-10-23: Ollama 0.40.6
with `qwen2.5:7b` (Q4_K_M, weights `sha256:2bada8a7…` pinned in the config, `num_ctx` 12288),
Groq `openai/gpt-oss-120b` (best-effort `json_schema`, `reasoning_effort` low, reasoning not
returned; free plan 8K tokens/min and 200K tokens/day, 1,000 requests/day).
