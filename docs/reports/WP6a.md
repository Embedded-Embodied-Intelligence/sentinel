# WP6a report — LLM layer and RQ1: WBS extraction with validation and repair

- Date: 2026-10-23
- Commit(s): 7ae3ac5 (WP5 config test, `chore`), 670f260 (`docs: WP5 results and plan`),
  93d2c2a (LLM layer, ADR-0018), 8fa0172 (narrator, extraction, validation, repair loop),
  d042da3 (scores), db40334 (schemas without descriptions, issue wording, 429 stop), 0e2e1e1
  (study runner, summaries, config, CLI); the report, notes and roadmap commit follows them

## Summary
`sentinel.llm` now exists: one client protocol over Ollama, Groq and a scripted fake, with the
standard library only, a record/replay cache keyed by the SHA-256 of the whole request,
pydantic-validated answers whose violations come back as data, and keys that never leave
`.env` (ADR-0018; Groq model `openai/gpt-oss-120b`, chosen on 2026-10-23). The narrator turns a
PSPLIB instance into a structured or narrative project plan whose every fact a template parser
reads back exactly (40 J30 instances × 2 styles). Extraction validates answers (11 issue
kinds, cycles listed) and repairs them in up to 3 rounds, with the single shot as round 0;
scoring measures validity, activity recall and precision, edge F1, durations, crews, team,
exact instances and the CP-SAT makespan error. The RQ1 runner smoke-ran on the oracle (2 × 2),
Ollama (1 × 2) and Groq (1 × 2) with every output, and its bundle replays a run byte for byte.
In the smoke gpt-oss-120b answered both styles validly in one call each (3.9 s and 6.1 s),
qwen2.5:7b took about 100 s per call and, in the narrative, left out 5 of 30 activities and
repeated its answer in every repair round. The full runs go to the owner: Ollama about
3.5–7 h, Groq 2–3.5 days on the free plan.

## Acceptance criteria
| # | Criterion | Command | Result |
| --- | --- | --- | --- |
| 1 | Housekeeping commit; ADR for the LLM layer | `git show --stat 670f260 7ae3ac5 93d2c2a` | PASS (`docs: WP5 results and plan`: roadmap WP5 done with the three run ids, plan with the ablation split and the RQ1 design; the pre-existing failure of the WP5 config test fixed in its own `chore` commit before it; ADR-0018 in 93d2c2a) |
| 2 | Quality gate and `-m "data or slow"` pass; task-6 tests exist and pass | `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy src`; `uv run pytest -q`; `uv run pytest -q -m "data or slow"` | PASS (ruff clean; 208 files formatted; mypy: no issues in 73 source files; `pytest -q`: 357 passed, 7 deselected in 67.5 s, within 75 s; `-m "data or slow"`: 20 passed, 344 deselected in 429.3 s; the task-6 tests are listed under Changes) |
| 3 | Narrator round trip exact on 40 instances × 2 styles | `uv run pytest -q -m data tests/test_wbs_narrate.py` | PASS (`test_the_round_trip_is_exact_on_the_40_study_instances_in_both_styles`: the parser recovers every instance exactly, ids aside, and rejects a fact stated twice; also in both runs of criterion 2) |
| 4 | Smoke run outputs all files; latency measured; full-run commands with estimates | `python -m sentinel.experiments.wbs_study --config configs/wp6_rq1.toml --out results/wp6 --backend fake --limit 2`, the same with `--backend ollama --limit 1` and `--backend groq --limit 1` | PASS (every output of `manifest.json` written in all three; replay from the bundle byte-identical; latency per call and session and token counts under Numbers; commands with estimates under Commands) |
| 5 | Report, notes, roadmap (`WP6: in progress: WP6a smoke done`); pushed; clean tree | `git push`; `git status --short` | PASS (this report, `docs/notes/WP6a.md`, roadmap `WP6: in progress: WP6a smoke done`, plan; pushed to `origin/main`; `git status --short` empty afterwards) |

## Changes
- Housekeeping: `docs/roadmap.md` (WP5 done with the three run ids), `docs/experiments/plan.md`
  (ablation split, WP5 runs, RQ1 design); `tests/test_policy_study.py` (the WP5 config test
  follows the split of commit 4153d07, own `chore` commit).
- `src/sentinel/llm/` (new): `core.py` (Message, Request and its SHA-256 key, Reply,
  LlmResponse, OutputError, LlmClient protocol, errors, `backend_schema`, `validate_reply`),
  `cache.py` (LlmCache, modes, `write_bundle`), `client.py` (BaseClient call path, ClientStats),
  `http.py` (urllib transport), `ollama.py`, `groq.py` (with TokenRateLimiter, `parse_wait`),
  `fake.py`, `secrets.py` (Secret, `.env` parsing, redaction), `prompts/` (`load_prompt`,
  `wbs_extract.v1.txt`, `wbs_repair.v1.txt`), `__init__.py`.
- `src/sentinel/wbs/` (new): `narrate.py` (narrator, vocabulary, template parser), `extract.py`
  (schema, normalisation, issues, `validate_extraction`, `to_instance`, `single_shot`,
  `repair`), `score.py` (lenient reading, matching, metrics, CP-SAT downstream).
- `src/sentinel/experiments/`: `wbs_config.py`, `wbs_study.py` (runner, oracle backend),
  `wbs_summary.py` (statistics, Markdown, LaTeX, figure, provenance) (new); `runs.py`
  (`config_hash` takes an optional selection such as `--backend`; hashes without one are
  unchanged).
- `src/sentinel/cli.py`: `sentinel summarise-wbs <run_dir>`.
- `configs/wp6_rq1.toml` (new).
- Tests (task 6 → test): cache record/replay round trip and replay miss
  (`test_llm.py::test_record_then_replay_returns_the_recorded_reply`, `::test_auto_mode_…`,
  `::test_the_key_covers_…`, `::test_a_cut_off_last_line_…`); schema-violation path
  (`::test_schema_violations_come_back_as_structured_errors`,
  `::test_groq_returns_a_failed_generation_as_an_answer`); Groq backoff on a scripted 429
  (`::test_groq_backs_off_on_a_scripted_429_honouring_retry_after`, `::test_groq_stops_…`,
  `::test_the_token_limiter_…`); redaction (`::test_the_key_never_shows_in_reprs_errors_or_cache_files`,
  `::test_the_key_comes_from_…`, `::test_replaying_needs_neither_a_key_nor_a_server`); import
  boundary (`::test_only_the_wbs_and_experiment_packages_import_the_llm_layer`); validator on
  hand-made cases of every issue type (`test_wbs_extract.py::test_the_validator_catches_every_issue_type_on_hand_made_cases`,
  `::test_issue_messages_…`); repair loop stops on a valid answer and after 3 rounds
  (`::test_the_repair_loop_stops_on_a_valid_answer`, `::test_the_repair_loop_stops_after_three_rounds`,
  `::test_a_repair_round_that_cannot_fit_ends_the_session`); scoring on a perturbed truth
  (`test_wbs_score.py::test_scoring_a_perturbed_truth_gives_the_expected_numbers` and three
  more); narrator round trip (`test_wbs_narrate.py`, with the data test
  `::test_the_round_trip_is_exact_on_the_40_study_instances_in_both_styles`); runner
  (`test_wbs_study.py`: config follows the plan, every output, replay from the bundle
  byte-identical, rate-limit stop and resume, regeneration identical, oracle); `test_runs.py`
  (selection in the config hash).
- Docs: ADR-0018, `docs/notes/WP6a.md`, this report, roadmap (WP6 in progress), plan (RQ1 rows
  refined: backend settings, CP-SAT, `rounds.csv`, the two run commands).

## Decisions
- **LLM layer** (ADR-0018). One `LlmClient` protocol and one call path in `BaseClient`:
  request (backend, model, weights digest, messages, inlined schema, temperature, seed,
  `max_tokens`, backend options) → SHA-256 key → cache (`record`/`replay`/`auto`, JSON lines
  per backend in `data/llm_cache/`, appends under `flock`, a cut-off last line skipped) →
  backend on a miss → pydantic validation. Output problems return as `OutputError` (`empty`,
  `json`, `truncated`, `schema` with every violation); backend failures raise `LlmError`.
  Standard library only (`urllib.request`, `fcntl`, `gzip`); no new dependency.
- **Groq model: `openai/gpt-oss-120b`**, read from Groq's documentation on 2026-10-23: the
  strongest of the production (generally available) models, featured, in the free-plan limits
  (30 RPM, 1K RPD, 8K TPM, 200K TPD; the key reports 8,000 TPM and 1,000 RPD), with structured
  outputs. Best-effort `json_schema`, since strict mode needs `additionalProperties: false`
  everywhere and the WP's `crew: {role: n}` map is free-form; an answer failing Groq's own
  check (HTTP 400 `json_validate_failed`) comes back as an answer (its `failed_generation`) for
  the validator. `reasoning_effort` low, reasoning not returned.
- **No TPM cap on `max_tokens`.** A probe showed Groq charges used tokens (633 prompt tokens
  with `max_completion_tokens` 7,900 passed an 8,000 TPM limit), so the client keeps 4,096 and
  its sliding-window limiter books min(estimate, limit) per request (a large request waits for
  an empty minute) and settles to the real usage. 429/498/5xx: exponential backoff (2 s × 2^k,
  at most 60 s) or `retry-after`/`x-ratelimit-reset-*`; a wait over `max_wait_s` = 900 s, or
  429s past `max_retries`, raises `QuotaExhausted`.
- **Ollama.** `num_ctx` fixed at 12288 (the longest repair prompt, about 5K tokens, plus
  4,096); a fixed value avoids model reloads and is part of the key. The digest is the weights
  blob of the `/api/show` modelfile (`FROM …/sha256-<hex>`; the endpoint has no `digest`
  field), pinned in the config and checked before the first backend call, so replay needs no
  server. A prompt that fills the context raises `RequestTooLarge`.
- **Schema sent without titles and descriptions**, so a docstring edit changes no cache key
  (found when the first smoke's schema carried the models' docstrings).
- **Secrets.** `GROQ_API_KEY` from the environment or `.env`, parsed by `secrets.py` at the
  first backend call; held as `Secret` (repr, str, format masked; not picklable); every error
  message is redacted (the key and anything shaped like `gsk_…`); requests in the cache carry
  no headers. I never read `.env`.
- **Narrator.** Dominant role = most people, ties to the lower role; objects drawn without
  replacement per role, seeded verbs; the instance's seed is shared by both styles. An activity
  without real predecessors is stated to start right away (its edge from the implicit source),
  so the text has a statement for every activity's predecessors. Narrative: dependency form
  with probability 1/2, numbers in words with probability 1/2, 1–3 activities per paragraph.
  The template parser lives in the narrator module (`parse_narration`); the smoke oracle
  reuses it.
- **Validation beyond the WP's list.** `invalid_field` (wrong types), `duplicate_role`,
  `negative_count` and `invalid_json` (unparseable or cut-off answer) are added, so that every
  answer without issues converts with `to_instance`. Issue messages name the place in the
  answer and what to check (see Numbers: the first wording stalled the repair loop).
- **Repair conversation of constant size**: system, description, the previous answer as compact
  JSON, the issue list (at most 40 lines). A repair request that cannot fit ends the session
  (`stopped`). `unchanged_rounds` counts repair rounds that repeated the previous answer.
- **Scoring.** Lenient reading (each entry validated alone), one-to-one first-match by
  normalised name (role names also singular), edges on matched activities, empty-set rates 1
  only for a project without edges, exact = valid and isomorphic under the name matching;
  CP-SAT downstream with the `cpsat_det` settings (5.0 deterministic s), memoised per instance.
- **Runner.** Sessions in (instance, style, backend) order, one at a time (one GPU, one rate
  limit). The run directory is written when every session is done, so a run stopped by
  `QuotaExhausted` (exit status 3) leaves only cached calls and the same command resumes it.
  `--backend` is part of the run hash (`runs.config_hash(…, selection)`): two smoke runs of the
  same config and limit started in the same second got the same run id. Cache-hit columns are
  not in the CSVs (the manifest has the hit rates), so a replay reproduces `results.csv` and
  `rounds.csv` byte for byte. The bundle is gzip without a header timestamp.
- **Smoke oracle backend** (`[backend.fake]`): the template parser's answer with seeded
  mistakes (an omitted activity that others name, a duration one day long, a cycle) in its
  first 0–2 answers; stateless, it recognises its previous answer in the conversation.
- ADRs created: ADR-0018 (LLM layer).

## Deviations
- **Extra housekeeping commit.** `tests/test_policy_study.py` had failed since the owner's
  split commit 4153d07 (it expected Λ = 0/1 in the ablation config); it now follows the split
  and covers `wp5_rq4_autonomy.toml`. Own `chore:` commit before the `docs:` commit, so every
  commit passes the gate.
- **Files beyond the WP's list:** `experiments/runs.py` (selection in the run hash, backward
  compatible), `cli.py` (`summarise-wbs`), `wbs/__init__.py`, `experiments/wbs_config.py`,
  `experiments/wbs_summary.py`, `llm/{core,cache,client,http,secrets,fake}.py`.
- **Smoke runs repeated.** The first Ollama smoke (narrative j301_1) showed the stalled repair
  loop and the schema descriptions; both smokes were rerun on the final code, so the first
  smoke's recordings are stale cache entries (never hit). The second Ollama smoke failed at its
  very end on the run-id collision; rerun from the cache after the fix (every call a cache hit,
  recorded latencies unchanged).
- **Groq smoke** (1 instance × both styles) run as well, since the key is present: 2 calls,
  7.4K tokens of the 200K daily budget, reused by the owner's run.
- `docs/notes/WP6a.md` is longer than 40 lines: the WP asks for the prompt texts.

## Spec questions
1. **`wbs/` in the package layout** (`docs/spec/architecture.md`). The WP places the narrator,
   extraction and scoring in `src/sentinel/wbs/`; the layout lists `llm/` but not `wbs/`.
   Not edited (spec-guard); proposal: add `wbs/  # WP6: narrator, extraction, validation,
   scores (RQ1)` and note that only `wbs/`, `experiments/` and the interpretation layer import
   `llm/` (a test enforces it).
2. **Zero-duration activities** (§1). The spec allows a real activity with `p_j = 0`; the WP's
   validator rejects non-positive durations. Exact for RQ1 (J30 durations are 1–10); for a set
   with zero-duration activities a correct extraction would be rejected. Reading used: the
   WP's rule (`# SPEC-Q` in `wbs/extract.py::_activity_issues`).
3. **IT role names** (§1.1, "an optional display mapping to IT roles may be added later"). The
   narrator maps R1–R4 to backend developer, frontend developer, tester and DevOps engineer;
   the spec could name this mapping as the display mapping.

## Numbers
Environment: Intel i5-6600K (4 cores), WSL2 (Linux 6.18), GTX 1060 6 GB, Ollama 0.40.6,
CPython 3.12, uv 0.13.2; Groq API on 2026-10-23 (free plan). Smoke instance j301_1: 30 real
activities, 42 real precedences, CP-SAT makespan 43 (the optimum); temperature 0, `max_tokens`
4,096.

**Ollama `qwen2.5:7b`** (Q4_K_M, `num_ctx` 12288: 76 % of the model in VRAM; prompt processing
about 400 tok/s, generation 12.4–12.5 tok/s, below the 16.6 tok/s of `environment.md` at the
default context). Smoke run `20261023-074022-7f9ebef0-smoke` at commit 0e2e1e1, from the calls
recorded 07:29–07:33 UTC by the run that met the run-id collision (same results as its first
replay, `20261023-073305-7f9ebef0-smoke`):

| Call | Prompt tok. | Completion tok. | Latency | Outcome |
| --- | ---: | ---: | ---: | --- |
| structured, round 0 | 1,401 | 1,289 | 105.9 s | valid, not exact: one precedence missed (edge F1 0.988), makespan 42 vs 43 |
| narrative, round 0 | 1,350 | 1,209 | 98.1 s | 5 `unknown_name`: 5 of 30 activities left out (recall 0.833, edge F1 0.717) |
| narrative, round 1 | 2,379 | 1,058 | 96.9 s | the round-0 JSON unchanged |
| narrative, rounds 2–3 | (2,379) | (1,058) | (96.9 s) | identical requests, answered from the cache |

Per session: structured 1 call, 105.9 s, 2.7K tokens; narrative 4 calls as recorded (2 backend
calls), 388.7 s and 12.9K tokens at recorded cost, still 5 issues. The first smoke (wording
"…which is not an activity of the project") behaved the same; a review-style repair message
(previous JSON and problems in a user message, probe) changed the answer but left out the
same 5 activities. qwen2.5:7b thus does not repair these omissions in the smoke; the full run
decides how often repair helps it.

**Groq `openai/gpt-oss-120b`** (best-effort schema, reasoning low). Smoke run
`20261023-072753-8cb2732e-smoke`, replayed at commit 0e2e1e1 as `20261023-074004-95e53fd3-smoke`
(identical results, rounds and bundle):

| Call | Prompt tok. | Completion tok. | Latency | Outcome |
| --- | ---: | ---: | ---: | --- |
| structured, round 0 | 1,603 | 1,556 | 3.9 s | exact instance, makespan 43 = 43 |
| narrative, round 0 | 1,555 | 2,686 | 6.1 s | valid, not exact (edge F1 0.923), makespan 43 = 43 |

The limiter spaced the two calls by 56 s (8,000 TPM). The key's headers report 8,000 TPM and
1,000 requests/day; each call reported another `system_fingerprint`. A first Groq smoke on the
same texts (schema then with descriptions) gave another narrative answer (edge F1 0.895,
makespan 42), so answers vary with small request changes: the cache freezes them.

**Oracle (fake) smoke** `20261023-074005-009f9c94-smoke` (commit 0e2e1e1; identical to the
earlier `20261023-072743-38a13734-smoke`), 2 instances × 2 styles: single shot
valid in 1 of 4 sessions, repair in 4 of 4 (1, 2 and 1 repair rounds), every repaired answer
exact with makespan 43 = 43; pooled paired difference valid +75 pp [+50, +100]. Every output
written; a replay from its bundle reproduced `results.csv`, `rounds.csv` and the bundle byte
for byte (also a test). Bundle size: 1.6 KB per recorded call (gzip).

**Tests.** Default `pytest -q`: 357 passed, 7 deselected in 67.5 s (315 in 65.0 s before WP6a).
`-m "data or slow"`: 20 passed, 344 deselected in 429.3 s (19 in 506.3 s in WP5b.1, with
timing workers alongside; the new one is the 40-instance round trip, 0.4 s).

**Duration estimates** (from the smoke calls; prompts of the longest descriptions are about
0.5K tokens longer):

| Run | Calls | Estimate |
| --- | --- | --- |
| Ollama, 80 sessions | 1 call per valid single shot; 2 backend calls per session whose model repeats itself (later rounds come from the cache); up to 4 | 40 structured × 1–2 × 105 s + 40 narrative × 2–4 × 100 s ≈ **3.5–7 h**; bounds 2.2 h (all valid at round 0) and 9.5 h (4 different answers everywhere) |
| Groq, 80 sessions | 3.2K tokens (structured) and 4.2–4.8K (narrative) per single-shot call, about 6–7K per repair call | ≈ 0.31M tokens without repairs (1.5 days of the 200K/day plan), ≈ 0.45–0.7M with 1–3 repair rounds in a quarter of the sessions (**2–3.5 days**), at most 1.9M (9.5 days); about one call per minute (8K TPM), so 45–60 min of calls per day |
| Both backends together (run 2), Ollama part | 80 sessions from the cache | seconds, plus CP-SAT: 40 true instances and the valid answers at 5 deterministic s |

Size of a full run directory: about 0.3 MB of CSVs and a bundle of about 0.5 MB (300 calls
at 1.6 KB), under the 10 MB limit.

## Commands for the owner
Run in `tmux` from `~/projects/sentinel`, one after the other (not in parallel).

1. **Ollama run** (about 3.5–7 h; `ollama serve` running, `qwen2.5:7b` with the pinned digest):

   ```bash
   uv run python -m sentinel.experiments.wbs_study --config configs/wp6_rq1.toml --out results/wp6 --backend ollama
   git add results/wp6/<run_id> && git commit -m "WP6a: RQ1 Ollama run" && git push
   ```

2. **Groq run with both backends** (2–3.5 days on the free plan; `GROQ_API_KEY` in `.env`).
   The Ollama sessions replay from the cache of run 1, so this run holds the comparison:

   ```bash
   uv run python -m sentinel.experiments.wbs_study --config configs/wp6_rq1.toml --out results/wp6
   ```

   The start lines show how many sessions per backend start from the cache (Ollama: 80 of 80
   expected). If the run stops with exit status 3 ("stopped: … run the same command again in
   about N h"), it wrote no run directory; run the same command again after that time, and
   repeat until it prints `done: results/wp6/<run_id>`. Then:

   ```bash
   git add results/wp6/<run_id> && git commit -m "WP6a: RQ1 Groq run (both backends)" && git push
   ```

3. Optional: regenerate summaries with `uv run sentinel summarise-wbs results/wp6/<run_id>`;
   repeat a run without any backend with `uv run python -m sentinel.experiments.wbs_study
   --config configs/wp6_rq1.toml --out <new dir> [--backend ollama] --cache-file
   results/wp6/<run_id>/llm_cache.jsonl.gz` (byte-identical `results.csv`).

## Open issues / next steps
- Owner: the two full runs above; the architect reviews RQ1 on run 2.
- qwen2.5:7b repeated its narrative answer in every repair round of the smoke. If the full run
  confirms it, options for a follow-up: a repair temperature above 0, or asking for the missing
  activities only (both change the WP's protocol).
- Groq answers vary between near-identical requests and fingerprints; the committed bundle is
  the reference, and a rerun in `record` mode would give other answers.
- Spec questions 1–3 (package layout, zero durations, the IT role mapping).
- WP6b: event parser, candidate proposals, explanations (RQ5) on this LLM layer.
