# WP6a — LLM layer and RQ1: WBS extraction with validation and repair

Fresh session (`/clear`). Read before coding:

<context>
- `CLAUDE.md` (invariants 3 and 4: LLM isolation, secrets), `docs/spec/model.md` §1 (instance,
  role names), `docs/spec/architecture.md` (Interpretation layer, `llm/`), `docs/infra/environment.md`
- `docs/experiments/plan.md`, `docs/roadmap.md`
- skills `adr`, `experiment-run`, `spec-guard`, `wp-report`

WP5 is complete: the RQ4 studies are committed (`results/wp5/20261022-102609-e9d131b3` main,
`20261022-193948-592f7183` ablation, `20261022-234437-49965457` autonomy levels). Sentinel is on
time in 37.1 % (J30) and 34.3 % (J60) of runs vs 31.3 % / 29.0 % for FullResolve, with about a
quarter of its plan changes. The LLM layer is now added; it never decides (architecture).

**RQ1:** *Does validation with a repair loop improve the correctness of an LLM-extracted project
model (WBS with durations, crews and dependencies) compared with single-shot extraction?* To have
exact ground truth without circularity, the project descriptions are **generated
deterministically from PSPLIB instances by templates** (no LLM writes the inputs); the LLM must
recover the instance from the text. WP6b covers RQ5 (event parsing, candidate proposals,
explanations).

Backends: local **Ollama** `qwen2.5:7b` (pinned 0.40.6, ~16.6 tok/s on the GTX 1060; keeps
project data on premises) and **Groq** (cloud, larger model). The owner puts `GROQ_API_KEY` into
`.env`; you never read, print or log it (settings deny `Read(./.env)`); code loads it at runtime
from the environment or by parsing `.env` itself.

The decisions below are binding.
</context>

<task>
0. **Housekeeping** (commit `docs: WP5 results and plan`): roadmap `WP5: done` with the three
   run ids; `plan.md` records the ablation split (Λ = 0/1 at `λ_A = 0.01` in
   `wp5_rq4_autonomy.toml`, for the time budget) and the RQ1 design below.
1. **`sentinel.llm` package** (ADR for its design):
   - `LlmClient` protocol: `complete(messages, *, schema, temperature=0, seed, max_tokens)
     -> LlmResponse` (text, parsed JSON, model id, token counts, latency, cache hit).
   - Backends with the **standard library only** (`urllib.request`, no new runtime
     dependency): `OllamaClient` (`/api/chat`, `format` = JSON schema, `options.seed`,
     `temperature`, `num_ctx` large enough for the prompt; record the model digest from
     `/api/show`), `GroqClient` (OpenAI-compatible chat completions; JSON mode or schema as
     the model supports; retries with exponential backoff on 429/5xx honouring `retry-after`;
     a client-side token-per-minute limiter from config). Check Groq's current model list and
     limits in its documentation; choose the strongest generally available open model and record
     the choice and the date in the ADR.
   - **Record/replay cache** (invariant 3): key = SHA-256 of (backend, model, model digest if
     known, messages, schema, parameters); stored as JSON lines under `data/llm_cache/`
     (gitignored); modes `record` (call and store), `replay` (cache only; a miss is an error),
     `auto`. Experiments default to `auto` and record the cache hit rate in the manifest. A
     committed, small **replay bundle** per result run (`results/<wp>/<run_id>/llm_cache.jsonl.gz`,
     < 10 MB) lets anyone regenerate the tables without an API key.
   - Pydantic validation of every JSON output; a schema violation is returned as a structured
     error (for the repair loop), never raised into the decision layer.
   - Tests use a `FakeLlmClient` (scripted responses); no network in tests.
2. **Narrator** `src/sentinel/wbs/narrate.py`: `narrate(instance, *, style, seed) -> str`, fully
   deterministic. Roles get IT names (R1 backend developer, R2 frontend developer, R3 tester,
   R4 DevOps engineer); activities get unique, plausible names from a seeded vocabulary per
   dominant role (e.g. "Implement payment API"). The text states the team (capacity per role),
   and for every real activity its name, duration in working days, crew per role and immediate
   predecessors **by name**; source and sink are implicit. Two styles:
   - `structured`: one block per activity in topological order, fixed phrasing;
   - `narrative`: prose paragraphs in a shuffled order, varied seeded phrasings, dependencies
     stated sometimes on the successor ("can only start once A and B are done") and sometimes on
     the predecessor ("A must be finished before C begins"), numbers sometimes in words.
   Tests: every fact of the instance appears exactly once (a parser for the templates recovers
   the instance exactly from both styles); same seed → same text.
3. **Extraction and validation** `src/sentinel/wbs/extract.py`: output schema `{team: [{role,
   count}], activities: [{name, duration_days, crew: {role: n}, predecessors: [name]}]}`;
   `validate_extraction(...) -> list[Issue]` (unknown role, duplicate or unknown names, cycles
   with the cycle listed, non-positive duration, crew above team capacity, missing fields);
   `to_instance(...)` builds a `ProjectInstance` (adds source and sink) when valid. Prompts in
   English under `src/sentinel/llm/prompts/` as versioned files.
   - `single_shot`: one call.
   - `repair`: after a call, if issues exist, send them back (issue list + the previous JSON) and
     ask for a corrected full JSON; at most 3 repair rounds. The single-shot result is the first
     call of the repair session (shared), so both conditions cost one session.
4. **Matching and metrics** `src/sentinel/wbs/score.py`: match extracted to true activities by
   normalised name (exact after normalisation; report unmatched); valid-instance rate; activity
   recall/precision; precedence-edge precision/recall/F1 on matched activities; duration and crew
   accuracy (exact) on matched activities; team accuracy; **exact-instance rate** (isomorphic to
   the truth); downstream: CP-SAT makespan of the extracted instance vs the true one (relative
   error) when valid; tokens and latency per session.
5. **RQ1 study** runner `src/sentinel/experiments/wbs_study.py`, config
   `configs/wp6_rq1.toml`: 40 J30 instances (every 12th), both styles, both backends, both
   conditions (from shared sessions), narrator seed fixed; `results.csv` one row per (instance,
   style, backend, condition) with all metrics, rounds used, final issues; summary with Wilson CIs
   for rates, **paired** differences repair − single-shot (bootstrap over instances),
   `table_wp6_rq1.tex`, `fig_wp6_rq1.pdf/.png` (validity and edge F1 by round 0–3, per backend
   and style). Smoke: 2 instances × both styles on the FakeLlmClient and, if the owner has
   started Ollama, 1 real instance on Ollama; measure latency and give duration estimates; full
   runs go to the owner (Ollama run and Groq run as separate commands, each committing its
   results; the Groq run must respect the free-tier limits, possibly over more than one day,
   resumable from the cache).
6. **Tests**: cache record/replay round trip and miss in replay mode; schema-violation path;
   Groq backoff on a scripted 429; validator catches every issue type on hand-made cases; repair
   loop stops on a valid answer and after 3 rounds; scoring on a perturbed truth (one edge removed,
   one duration changed, one name changed) gives the expected numbers; narrator round trip.
7. `wp-report` (`docs/reports/WP6a.md`, `docs/notes/WP6a.md` with prompt texts, schema, metrics).
</task>

<constraints>
- No LLM call in any simulation or rollout path; `sentinel.llm` is imported only by `wbs/`,
  `experiments/` and later the interpretation layer.
- Secrets: never read or print `.env`; the key never appears in logs, manifests, cache files or
  exceptions (add a test that the client's repr and error messages redact it).
- No new runtime dependencies. Default `pytest -q` ≤ 75 s. Commit after each step group.
- Anything longer than ~10 minutes goes to the owner as a tmux command with an estimate.
</constraints>

<acceptance_criteria>
1. Housekeeping commit; ADR for the LLM layer.
2. Quality gate and `-m "data or slow"` pass; task-6 tests exist and pass.
3. Narrator round trip exact on 40 instances × 2 styles.
4. Smoke run outputs all files; latency measured; full-run commands with estimates.
5. Report, notes, roadmap (`WP6: in progress: WP6a smoke done`); pushed; clean tree.
</acceptance_criteria>

<report_format>
`docs/reports/WP6a.md` via `wp-report`. "Numbers": smoke metrics, latency per call and per
session (Ollama; Groq if the key is present), token counts, duration estimates.
</report_format>
