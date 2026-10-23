# WP6b report — RQ5: what the LLM contributes (event parsing, candidate proposals, explanations)

- Date: 2026-10-23
- Commit(s): dcaa25a (`spec: interpretation layer (v1.9)`), 774cb37 (interpretation package),
  5e1cc2f (decision states and sample), c6413ec (Groq `output_parse_failed`), 9bc1f51 (RQ5
  runners and configs); the report, notes and roadmap commit follows them

## Summary
Spec v1.9 answers the WP6a questions and adds §10, the interpretation layer: team calendar,
event messages, the action grammar and its compilation, explanations, and the rule that LLM
output enters the decision layer only as validated, compiled objects. `sentinel.interpret`
implements the three roles: a seeded message generator with a template parser (exact round
trip), an event schema without any reason field, validation with the WP6a repair loop and
`apply_events`; a grammar of SHIFT/RESEQ/SUBST/OVERTIME compiled through the WP5 builders, with
duplicate flags and a random control; explanation rendering and faithfulness checks. The 5,469
deliberations of Sentinel `full` that passed the needs gate on the 120 WP5 ablation worlds are
recorded (every rerun reproduces WP5) and a stratified sample of 150 is committed. All four
studies smoke-ran on the fake backend and the three offline ones on Groq: gpt-oss-120b parsed 20
of 20 messages exactly in one call, its 15 proposals all compiled (1 of 5 states won, +0.18 in
min(p̂, θ_D)), and 5 of 5 explanations were fully faithful. Full runs go to the owner: Ollama
about 2–3 h, Groq about 3.7 days of the free plan (online check about 7 days more, optional).

## Acceptance criteria
| # | Criterion | Command | Result |
| --- | --- | --- | --- |
| 1 | Spec v1.9 commit (with §10 and the architecture update) | `git show --stat dcaa25a` | PASS (`docs/spec/model.md`: answers 1–3 in §1 and §1.1, §6 points to §10.3, new §10.1–§10.4; `docs/spec/architecture.md`: `wbs/` and `interpret/` in the layout, the import boundary, the compiled-objects rule, data paths) |
| 2 | Quality gate and `-m "data or slow"` pass; task-8 tests exist and pass | `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy src`; `uv run pytest -q`; `uv run pytest -q -m "data or slow"` | PASS (ruff clean; 231 files formatted; mypy: no issues in 86 source files; `pytest -q`: 379 passed, 8 deselected in 76.5 s at load 5–6 from the owner's Ollama run, over the 75 s budget by 1.5 s (Deviations); `-m "data or slow"`: 22 passed, 365 deselected in 593.5 s; the task-8 tests are listed under Changes) |
| 3 | Decision-state sample recorded and its ids committed; all smokes produce their outputs | `uv run python scripts/record_decision_states.py --config configs/wp6_rq5_states.toml --workers 2 --write-sample`; the smoke commands under Numbers | PASS (5,469 states of 120 runs, 0 mismatches against the WP5 main study; 150 ids in `configs/wp6_rq5_states.toml`, committed in 5e1cc2f; every listed output of the 4 fake and 3 Groq smokes written; the Groq event smoke replays byte-identically from its bundle) |
| 4 | Owner commands with duration and token estimates for every full run | this report | PASS (Commands for the owner; estimates under Numbers) |
| 5 | Report, notes, roadmap (`WP6: in progress: WP6b smoke done`); pushed; clean tree | `git push`; `git status --short` | PASS (this report, `docs/notes/WP6b.md`, roadmap `WP6: in progress: WP6b smoke done`, plan; pushed to `origin/main`; `git status --short` empty afterwards) |

## Changes
- `docs/spec/model.md` (v1.9: §1, §1.1, §6, new §10), `docs/spec/architecture.md` (layout,
  boundary, interfaces, data paths); `docs/experiments/plan.md` (RQ5 design).
- `src/sentinel/interpret/` (new): `team.py` (calendar, roster, names), `events.py` (schema,
  context, validation, repair loop, `apply_events`, comparison, leak counter), `messages.py`
  (generator, template parser), `actions.py` (grammar, reading, `compile_proposal`, `Compiler`,
  random control, proposal call), `describe.py` (state summary), `explain.py` (record rendering,
  explanation call, faithfulness checks).
- `src/sentinel/llm/prompts/`: `events_parse.v1.txt`, `events_repair.v1.txt`, `proposals.v1.txt`,
  `explain.v1.txt`; `src/sentinel/llm/groq.py`: `output_parse_failed` returns as an answer.
- `src/sentinel/agent/candidates.py`: proposal kinds (`KINDS` unchanged), `timed_activities`,
  `effect`, `backlogs`; `src/sentinel/policies/sentinel.py`: optional `proposer`, `proposed` count.
- `src/sentinel/experiments/` (new): `decision_states.py`, `rq5_common.py`, `event_study.py`,
  `proposal_study.py`, `explanation_study.py`, `online_study.py`; `scripts/record_decision_states.py`.
- `configs/` (new): `wp6_rq5_states.toml` (with the sample), `wp6_rq5_events.toml`,
  `wp6_rq5_proposals.toml`, `wp6_rq5_explanations.toml`, `wp6_rq5_online.toml`.
- Tests (task 8 → test): message round trip (`test_interpret_events.py::test_the_message_generator_round_trips_through_the_template_parser`);
  reason words never reach outputs (`::test_no_reason_word_reaches_a_parsed_event`,
  `::test_the_leak_counter_finds_a_reason_in_any_string`); grammar on hand-made proposals: valid,
  invalid role, too many workers, unknown activity, ineligible, two plan operations, days, repeated
  SUBST (`test_interpret_actions.py::test_a_valid_proposal_compiles_with_its_plan_operation_last`,
  `::test_invalid_proposals_compile_to_issues`), duplicates of a rule candidate
  (`::test_duplicates_of_rule_candidates_and_earlier_proposals_are_flagged`); random sampler
  deterministic per seed (`::test_the_random_sampler_is_deterministic_per_seed_and_stays_in_the_grammar`);
  explanation checker on a faithful and a hallucinating answer
  (`test_interpret_explain.py::test_a_faithful_explanation_passes_every_check`,
  `::test_a_hallucinating_explanation_fails_the_right_checks`); the recorder reproduces a
  recorded record (`test_decision_states.py::test_recorded_states_reproduce_exactly_and_survive_storage`).
  Also: every validation issue type, `apply_events`, the repair loop, observation tolerance, an
  only-NOOP record, the stratified sample, Sentinel with a proposer (an empty proposer changes
  nothing), Groq `output_parse_failed` (`test_llm.py`), the import boundary with `interpret`, and
  the runners on the oracle (`test_rq5_studies.py`, data; the states-fed studies also slow).
- Docs: ADR-0019, `docs/notes/WP6b.md`, this report, roadmap.

## Decisions
- **Interpretation package and proposer hook** (ADR-0019). LLM answers become events applied by
  code or `Candidate`s compiled through `prepare`; four proposal kinds by plan operation, so
  `prepare` and `approve` work unchanged; `KINDS` keeps the rule kinds, so the policy-study
  columns and committed WP5 summaries are unchanged. Sentinel's optional `proposer` gets the
  observation, the rule record and the rule candidates; without one Sentinel is unchanged.
- **Compilation** (written into §10.3): one plan operation at most, always planned last on the
  state the other operations leave; SUBST substitutes are chosen on the state left by the
  operations before it; a duplicate is a proposal with the *effect* of a rule candidate or an
  earlier proposal (the rule candidates' own test: equal non-plan operations and planned starts
  of the activities with p_j > 0), a little wider than "same operations".
- **Random control** over the operations valid in the state (eligible SUBSTs, roles with
  ⌊γ R_k⌋ ≥ 1, one plan operation), uniform at each level, three proposals per state seeded by
  state: a strong control, so an LLM win is judgment rather than validity.
- **Win and gain.** A win is the §6 choice being a proposal (racing included); the gain compares
  it with the rule's own choice on the same N = 100 worlds. A win may lose in min(p̂, θ_D) where
  that difference is a tie within noise and a later component decided; `rule_dropped` marks wins
  where racing dropped the rule's choice in stage 1 (none in the smokes).
- **Messages** in states of NoReaction worlds (WP2b seeds, λ_A = 0.01), not in the decision
  states, so role 1 does not depend on the recording; work increases only of running
  activities (D2); new activities copy real activities that have a crew; return weekdays only
  for L_low ≤ 4; "unknown" is `null` with L_low = 1; factors to two decimals, compared within 0.01.
- **Roster names** "First I." from 60 × 26 combinations, since J30 teams have up to 219 people.
- **Privacy.** No event field can hold a reason; an extra "reason" field is rejected with an
  issue naming the field, never its value; leaks are counted in accepted events (expected 0)
  and, for information, in raw answers.
- **Progress terciles** of the duration-weighted share of nominal work done, cut at the 1/3 and
  2/3 quantiles over all 5,469 states; equal shares per stratum (12 or 13).
- **Own cache directory** `data/llm_cache/rq5/` for every RQ5 study (the WP6a files untouched).
- **Groq `output_parse_failed`** (HTTP 400 when gpt-oss writes non-JSON under `json_schema`, e.g.
  "No events.") now returns as an answer like `json_validate_failed`, so the validator and the
  repair loop see it; other 400s still raise.
- ADRs created: ADR-0019.

## Deviations
- **The decision-state recording ran in the session** (20.6 min on 2 workers next to the owner's
  RQ1 Ollama run): acceptance criterion 3 needs the sample. It ran on the working tree before
  commit 5e1cc2f (its manifest records `dcaa25a`, dirty); the committed code differs only by
  moving two functions into the module, and every rerun reproduced WP5 (0 mismatches).
- **Files beyond the WP's list:** `llm/groq.py` (the fix above), `agent/candidates.py`,
  `policies/sentinel.py`, `experiments/{decision_states,rq5_common,event_study,explanation_study,
  online_study}.py`, `interpret/{team,messages,describe}.py`, `tests/test_llm.py`.
- **First Groq event smoke stopped** on the `output_parse_failed` 400 after 11 calls; after the
  fix the same command resumed from the cache, and Groq answered the re-sent request with valid
  JSON this time, so the smoke has no such answer (the new test covers the path).
- **Default test time over the budget under load.** `pytest -q` took 76.5 s (budget 75 s) while
  the owner's Ollama run held all four cores (load 5–6); the suite took 73.6 s under similar load
  before WP6b and 67.5 s idle in WP6a, and the new default tests add about 2.5 s, so it should
  stay within 75 s on an idle machine (not measurable in this session). Owner: `uv run pytest -q`
  once the GPU runs are over.
- `docs/notes/WP6b.md` is longer than 40 lines: the WP asks for the prompts, grammar and metrics.
- No Ollama call was made (GPU busy, as instructed).

## Spec questions
1. **"No LLM call … in the simulator" (§10) and the online check.** The online check calls the
   LLM from Sentinel's deliberation of a world run (`policy.decide`), never in a rollout or in the
   engine. Proposal: "no LLM call is made in a rollout; in a simulated run only the agent calls it,
   at a deliberation (online check)".
2. **Invariant 7 and the record/replay cache.** The cache and the committed bundles store the full
   request, so a real message that gives a reason would be stored (RQ5 uses synthetic messages and
   a fictional roster only). Proposal: for real messages, do not commit parser bundles and keep the
   cache local, or redact reason phrases before the call.
3. **"About N days"** is read as the announced bound L_low = N (exact), as §10.2 now states; a
   softer reading (e.g. L_low = N − 1) would change the ground truth.

## Numbers
Environment: Intel i5-6600K (4 cores), WSL2, CPython 3.12, uv 0.13.2; the owner's RQ1 Ollama run
used the GPU and all cores (load 4–6) throughout; Groq API on 2026-10-23 (free plan, the key
reports 8,000 TPM).

**Decision states** (`data/derived/decision_states/`, 3.4 MB): 120 reruns (60 J30 instances ×
λ_A ∈ {0.01, 0.02}, replication 0) in 20.6 min on 2 workers (WP5 measured 38 CPU-min for the
same runs); 5,469 gated deliberations (2,327 at 0.01, 3,142 at 0.02; NOOP chosen in 4,925),
exactly WP5's count, with 0 makespan or count mismatches; a recorded record reproduces exactly
from its observation and seed (e.g. 0.06–0.26 s per deliberation). Sample: 150 states, 13 per
stratum at λ_A = 0.01 and 12 at 0.02.

**Role 1, events** (20 messages: 4 instances × 5; 19 true events: 5 absences, 8 work increases,
6 new activities; 4 noise messages, 3 with several facts, 2 reasons):

| Backend | Run | Condition | Valid | Exact | End to end | Noise FP | Leaks | Tokens / msg | Latency / msg |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| gpt-oss-120b | `20261023-114605-99707064-smoke` | single shot | 20/20 | 20/20 | 20/20 | 0/4 | 0 | 1,471 + 115 | 0.77 s |
| gpt-oss-120b | same | repair | 20/20 | 20/20 | 20/20 | 0/4 | 0 | (no repairs) | |
| oracle (fake) | `20261023-114852-4ead0087-smoke` | single shot | 12/20 | 11/20 | 11/20 | 0/4 | 0 | | |
| oracle (fake) | same | repair | 20/20 | 17/20 | 17/20 | 0/4 | 0 | | |

gpt-oss-120b recovered every return day (weekday arithmetic included), factor (also "another d
days") and new-activity field; the oracle's seeded mistakes were all caught and repaired (0.4
rounds per message), its unseen ones remained (exact 85 %). A first attempt met one
`output_parse_failed` answer ("No events." for a noise message).

**Role 2, proposals** (Groq run `20261023-114819-e7f2cc99-smoke`, 5 states; fake
`20261023-114854-98390b08-smoke`, 3 states):

| Source | Valid answers | Proposals | Compiled | Duplicates | Wins | Gain min(p̂, θ_D) | Gain T̂ (days) | Tokens / state | Latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| gpt-oss-120b | 5/5 | 15 | 15 | 0 | 1/5 | +0.18 | +2.07 | 1,440 + 293 | 1.11 s |
| random | 5/5 | 15 | 15 | 1 | 1/5 | 0.00 | −0.25 | – | – |
| oracle (fake) | 3/3 | 9 | 8 | 2 | 1/3 | −0.11 | +0.50 | – | – |

Every gpt-oss proposal hires temporary workers (two per role, mostly with RESEQ); its win
(state j301_9, λ_A = 0.01, day 35) hires backend and DevOps workers for 5 days with RESEQ-M:
p̂ 0.63 against 0.45, T̂ 1.94 against 4.01 days of the rule's OT(0)+RESEQ-M. The random win
(j302_7, day 13: OT(tester, 1, 19 days) + RESEQ-S) ties the rule's RESEQ-M in p̂ and T̂ and wins
on stability (a smaller plan change). LLM − random,
paired over the 5 states: win rate +0 pp [−60, +60], improvement in min(p̂, θ_D) +0.036 [0,
+0.108], in T̂ +0.46 days [0, +1.29]. Evaluation is cheap: about 0.4 s of CPU per state.

**Role 3, explanations** (Groq run `20261023-114923-3b325d9f-smoke`, 5 states; fake
`20261023-114856-422a0949-smoke`, 3 states): gpt-oss-120b 5/5 valid and fully faithful, 28 facts
cited, all correct, 0 hallucinated numbers, 27.8 words on average (none over 80), 883 + 232 tokens
and 0.88 s per explanation; the oracle 2/3 fully faithful (one seeded hallucinated number found).

**Online check** (fake, `20261023-114857-416aac98-smoke`, j301_1 at λ_A = 0.01): 30 gated
deliberations, 30 proposal calls, 90 proposals, 68 compiled, 48 raced, 2 chosen; makespan 73 as
WP5's Sentinel `full`, cost/B +0.036, deviation −0.1; 7.2 s.

**Tests.** Default `pytest -q`: 379 passed, 8 deselected in 76.5 s (wall 77.3 s, user 79.1 s) at load 5–6 from the RQ1 Ollama run; before WP6b the suite (357 tests) took 73.6 s at load 4, and 67.5 s idle in WP6a. The 22 new default tests take about 2.5 s. `-m "data or slow"`: 22 passed in 593.5 s (20 in 429.3 s in WP6a); new: the event runner with its replay (0.3 s) and the runners fed by recorded states (15 s, slow).

**Estimates.** Groq tokens per call from the smokes: events 1,586, proposals 1,733,
explanations 1,115; Ollama from the WP6a speeds (about 400 prompt tok/s, 12.4 generated tok/s)
and assumed answer lengths (qwen2.5:7b writes no hidden reasoning).

| Run | Calls | Groq tokens (free plan 200K/day) | Ollama duration |
| --- | ---: | ---: | ---: |
| Events, 200 messages | 200 (+ repairs) | ≈ 0.32M, 1.6 days | 35–90 min (8–14 s per call, 200–400 calls) |
| Proposals, 150 states | 150 | ≈ 0.26M, 1.3 days | 35–60 min (14–24 s per call) + about 2 min of rollouts |
| Explanations, 150 states | 150 | ≈ 0.17M, 0.85 days | 25–45 min (10–18 s per call) |
| Online check, 20 runs (Groq only) | about 819 (the gated deliberations of WP5's runs) | ≈ 1.4M, 7.1 days | – |

At 8K TPM the client paces about 3.5 calls a minute, so a Groq day of 200K tokens takes about
35–40 min of calls; the daily quota sets the duration. Bundles: about 0.45 KB per call (events
smoke 9.3 KB for 20 calls), so full runs stay under 0.2 MB.

## Commands for the owner
Run in `tmux` from `~/projects/sentinel`, one after the other. The Ollama runs need the GPU, so
start them after the RQ1 Ollama run; the Groq runs share the daily quota with the RQ1 Groq run.
The proposal and explanation studies read `data/derived/decision_states/` (present here; if it
is missing: `uv run python scripts/record_decision_states.py --config configs/wp6_rq5_states.toml`,
about 10 min on 4 workers, which checks that the drawn sample equals the committed ids).

1. **Ollama runs** (about 2–3 h in total; `ollama serve` with `qwen2.5:7b` of the pinned digest):

   ```bash
   uv run python -m sentinel.experiments.event_study --config configs/wp6_rq5_events.toml --out results/wp6 --backend ollama
   uv run python -m sentinel.experiments.proposal_study --config configs/wp6_rq5_proposals.toml --out results/wp6 --backend ollama
   uv run python -m sentinel.experiments.explanation_study --config configs/wp6_rq5_explanations.toml --out results/wp6 --backend ollama
   git add results/wp6/<run_id_1> results/wp6/<run_id_2> results/wp6/<run_id_3> && git commit -m "WP6b: RQ5 Ollama runs" && git push
   ```

2. **Groq runs with both backends** (about 3.7 days of the free plan; Ollama replays from the
   cache of step 1, so these runs hold the comparison):

   ```bash
   uv run python -m sentinel.experiments.event_study --config configs/wp6_rq5_events.toml --out results/wp6
   uv run python -m sentinel.experiments.proposal_study --config configs/wp6_rq5_proposals.toml --out results/wp6
   uv run python -m sentinel.experiments.explanation_study --config configs/wp6_rq5_explanations.toml --out results/wp6
   ```

   A run that stops with exit status 3 ("stopped: … run the same command again in about N h")
   wrote no run directory; run the same command again after that time until it prints
   `done: results/wp6/<run_id>`, then `git add results/wp6/<run_id> && git commit -m "WP6b: RQ5
   <study> run (both backends)" && git push`.

3. **Optional online check** (Groq only, about 1.4M tokens, 7 days of the free plan; resumable
   the same way, each resume re-simulates the 20 runs, about 10 min of CPU):

   ```bash
   uv run python -m sentinel.experiments.online_study --config configs/wp6_rq5_online.toml --out results/wp6
   ```

4. Replay any run without a backend: add `--cache-file results/wp6/<run_id>/llm_cache.jsonl.gz`
   (and the run's `--backend` options); `results.csv` is reproduced byte for byte.

## Open issues / next steps
- Owner: the runs above; the architect reviews RQ5 on the both-backend runs.
- gpt-oss-120b proposes OVERTIME in every proposal of the smoke; the full run shows whether it
  wins beyond the random control, which also wins (1 of 5 states) by ties in later components.
- The online check is expensive on the free plan (7 days); a cheaper variant would call the LLM
  only where the rule's choice is not NOOP (about 10 % of the gated deliberations).
- Spec questions 1–3 (online LLM calls and §10 wording, reasons in caches, "about N days").
- Groq answers vary between identical requests (one `output_parse_failed`, later valid JSON);
  the committed bundles are the reference.
