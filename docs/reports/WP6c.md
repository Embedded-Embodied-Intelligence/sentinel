# WP6c report — clean RQ5 manifests, privacy-safe cache, OpenRouter backend, overnight chain

- Date: 2026-10-23
- Commit(s): 77f74e6 (`spec: LLM calls at deliberations, privacy-safe cache (v1.9.1)`), 36bb1a3
  (git state at run start), 9db1234 (`WP6c: remove RQ5 Ollama runs with wrong git state (rerun
  from cache)`), 271f320 (cache without prompts, OpenRouter backend, per-backend replay), f864c7d
  (overnight chain, Groq's reasoning fields); the report, notes and roadmap commit follows them

## Summary
Spec v1.9.1 answers the WP6b questions: LLM calls only by the agent at a deliberation, never in
the engine or a rollout; cache records without messages (`store_prompts = false`), mandatory for
real data; "about N days" as an announced lower bound. Every RQ5 runner now takes the git state
when it starts, so runs in a clean repository report `git_dirty: false`, and the three dirty RQ5
Ollama runs were removed for a replay that reproduces them row for row. The Groq client is now
an OpenAI-compatible client with a second backend, `openrouter`, pinned to Groq, which records
and checks the serving provider and stops with exit status 3 when credits run out; three live
calls were served by Groq at about $0.0003 each. `scripts/wp6_overnight.sh`, started by one tmux
line, runs and commits the eight remaining WP6 runs in about 1 h for about $0.6–1.1.

## Acceptance criteria
| # | Criterion | Command | Result |
| --- | --- | --- | --- |
| 1 | Spec v1.9.1 commit; the removal commit; quality gate and `-m "data or slow"` pass | `git show --stat 77f74e6 9db1234`; `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy src`; `uv run pytest -q`; `uv run pytest -q -m "data or slow"` | PASS (77f74e6: `docs/spec/model.md` §10 and §10.2, `CLAUDE.md` invariant 7; 9db1234 removes the three directories, 17 files; ruff clean, 237 files formatted, mypy: no issues in 88 source files; `pytest -q`: 393 passed, 8 deselected in 70.7 s, idle; `-m "data or slow"`: 22 passed, 379 deselected in 438.3 s) |
| 2 | Clean-manifest and privacy-cache tests exist and pass | `uv run pytest -q -m "data or slow" tests/test_rq5_studies.py`; `uv run pytest -q tests/test_llm.py tests/test_rq5_common.py` | PASS (2 passed; 27 passed. Clean manifest: `test_rq5_studies.py::test_the_event_study_writes_every_output_and_replays_from_its_bundle` and `::test_recorded_states_feed_the_proposal_explanation_and_online_studies` run every RQ5 runner on the fake backend in a clean temporary git repository and assert `git_dirty: false`; both fail on the code before 36bb1a3; privacy: `test_llm.py::test_a_cache_without_prompts_replays_by_key_and_holds_no_message_text`, `test_rq5_common.py::test_one_backend_replays_from_a_file_and_no_cache_holds_the_messages`) |
| 3 | The single command line with per-step estimates and resume instructions | this report | PASS (Commands for the owner; estimates under Numbers; the chain's commit, stop and resume logic exercised on a scratch clone with a stub `uv`) |
| 4 | Report and roadmap; pushed; clean tree | `git push`; `git status --short` | PASS (this report, `docs/notes/WP6c.md`, roadmap `WP6: in progress: WP6c done, runs pending`; pushed to `origin/main`; `git status --short` empty afterwards) |

## Changes
- `docs/spec/model.md` v1.9.1 (versions, §10 LLM calls and cache records, §10.2 "about N
  days"); `CLAUDE.md` invariant 7 (caches of real data without messages).
- `src/sentinel/experiments/rq5_common.py`: `manifest` takes the git state from the runner;
  `store_prompts`, `OpenRouterBackend`, `--replay`, `Clients.replay`, the stop message.
  `event_study.py`, `proposal_study.py`, `explanation_study.py`, `online_study.py`: git state at
  run start, `--replay`. `scripts/record_decision_states.py`: git state at run start.
- `src/sentinel/llm/cache.py`: `store_prompts` (entries without messages; refuses files with
  messages). `core.py`: `CreditsExhausted`, `QuotaExhausted.resume_hint`. `openai_compat.py`
  (new): `OpenAICompatibleClient`, `TokenRateLimiter`, `parse_wait`. `groq.py`: a thin
  subclass. `openrouter.py` (new): `OpenRouterClient`. `secrets.py`: OpenRouter key shape.
  `__init__.py`: exports.
- `src/sentinel/experiments/wbs_config.py`: `ProviderRouting`, `OpenRouterBackend`,
  `store_prompts`. `wbs_study.py`: the OpenRouter client, provenance (routing, providers,
  recorded cost, `store_prompts`), `open_caches`, `parse_replay`, `--replay`, `stop_message`.
- `configs/wp6_rq1.toml`, `wp6_rq5_{events,proposals,explanations,online}.toml`: backend
  `openrouter` as the cloud backend (Groq kept), `store_prompts = true`.
- `scripts/wp6_overnight.sh` (new): the owner's chain. `.env.example`: `OPENROUTER_API_KEY`.
- Tests: `test_rq5_studies.py` (clean temporary repository, absolute config paths),
  `test_llm.py` (+9: Groq key and body pinned, limiter from headers, OpenRouter routing and
  provider, foreign provider rejected, 402 credits and in-flight wait, 429 and an error inside a
  200, failed generation, OpenRouter key redaction, cache without prompts),
  `test_wbs_study.py` (+3: credits stop, `--replay`, OpenRouter provenance; config test),
  `test_rq5_common.py` (new, 2).
- Docs: ADR-0018 amendment, `docs/experiments/plan.md` (cloud route through OpenRouter, the
  both-backend runs with `--replay`), `docs/notes/WP6c.md`, this report, roadmap.
- Results: `results/wp6/20261023-143419-97e5d945`, `…-145842-9acf6e1d`, `…-151739-9d9075b6`
  removed (in the history at cbe6849).

## Decisions
- **Git state at run start**, before the run directory or any cache append exists, as the
  other runners do. The tests run every RQ5 runner in a clean temporary repository with the run
  directory inside it, assert `git_dirty: false` and commit the directory before the next run,
  as the chain does.
- **Cache records without prompts.** An entry keeps key, backend, model, digest, schema name and
  hash, decoding parameters, options and the reply, plus `store_prompts: false`. Full records
  are byte-identical to before. A no-prompts cache refuses a file that holds messages, so neither
  the working cache nor a bundle can mix them in. `store_prompts` is a study config field
  (default and RQ1/RQ5 value `true`), recorded per backend in the manifest.
- **One OpenAI-compatible client** with service hooks (URL, key variable, completion-limit
  field, wait headers, failed generations, stops, reply checks). Groq's requests are unchanged:
  a test pins the key and body bytes of a fixed request computed before the refactor.
- **OpenRouter routing** `{order: ["groq"], allow_fallbacks: false, require_parameters: true}`
  as a request field and part of the cache key. `require_parameters` makes sure no field (seed,
  schema, reasoning) is silently dropped. The `X-OpenRouter-Metadata: enabled` header makes the
  reply name its endpoint. The served provider (`provider`, else the router metadata) goes into
  every reply's meta and the manifest. With fallbacks off, an answer of another provider raises
  `LlmError` and is not cached.
- **Errors** (OpenRouter docs): an error inside a 200 counts with its own code; 408, 429 and
  5xx are retried; a 429 waits for `Retry-After`, else `X-RateLimit-Reset` (epoch ms or s),
  else backoff. A 402 of the in-flight budget waits like a 429. Any other 402, or a 403 with a
  budget `limit_source`, raises `CreditsExhausted`: exit status 3 and "add credits (or raise the
  key's limit), then run the same command again". A provider's failed JSON check in
  `error.metadata.raw` comes back as an answer, as on Groq.
- **Limiter.** It takes `x-ratelimit-limit-tokens` from a reply when present (Groq), and a
  limiter started that way books the reply that reported it. Otherwise it uses the configured
  limit. OpenRouter sends no rate-limit headers and its config sets no limit.
- **Reasoning fields.** OpenRouter sends Groq's own `reasoning_effort = low` and
  `include_reasoning = false`, the same options as the `groq` backend, not OpenRouter's
  `reasoning` object. A recorded WP6b request resent with Groq's fields returned the
  direct-Groq answer; with the object it did not (Numbers).
- **`--replay BACKEND=FILE`** answers one backend from a bundle or cache file (read-only,
  replay mode: a miss is an error) while the others use `--cache-mode`. This is how the
  both-backend runs replay Ollama without calling it.
- **The chain is a committed script** started by one tmux line, not a raw one-liner. That
  avoids nested quoting, and it gives a resume from step N and a dry run. Each step commits its
  run directory with `git add -- results/wp6 && git commit -- results/wp6`, skipping the
  `end-of-file-fixer` and `trailing-whitespace` hooks: they would rewrite generated results
  (invariant 2) and abort the commit, for example on an LLM summary ending in a space. The
  large-file and secret checks still run.
- ADRs created: none (ADR-0018 amended).

## Deviations
- **Three live calls instead of one** (about $0.001 in total). The first one used 329 reasoning
  tokens for a short message, so two more resent one recorded WP6b request, with each kind of
  reasoning field, to check that the reasoning setting reaches Groq. The outcome changed the
  options (Decisions).
- **Provider slug `groq`** (OpenRouter documents lowercase slugs) instead of the WP's `"Groq"`.
  The served provider is reported as `Groq` and matched case-insensitively. Added
  `require_parameters: true` to the WP's routing.
- **Additions the chain needs**: `--replay BACKEND=FILE`, `scripts/wp6_overnight.sh`, and
  skipping the two fixer hooks in its commits.
- **Files beyond the WP's list**: `llm/core.py`, `llm/secrets.py`, `llm/__init__.py`,
  `experiments/wbs_config.py`, `scripts/record_decision_states.py` (git state at start; its
  outputs are gitignored, so its manifests did not change), `.env.example`, tests.
- `tests/test_llm.py::test_the_token_limiter_spaces_requests_within_a_minute` now has its
  scripted replies report the configured limit (1,000). With the old 8,000 header the reported
  limit now wins, and the new limiter test covers that case.

## Spec questions
1. **Reply text in a cache without prompts.** `store_prompts = false` keeps the reply. An answer
   that violates its schema keeps its raw text, for example an extra `reason` field, or a
   failed generation that echoes the message. For real data a reason could then be stored.
   Proposal: for real data, store invalid answers only as their issue list, or redact their
   text.
2. **Invariant 3 wording.** `CLAUDE.md` still says "No LLM calls in rollouts or simulation
   loops", while §10 now allows the agent's calls at deliberations of a simulated world. Reading
   used: "simulation loops" means the engine. Proposal: reword invariant 3 like §10.
3. `docs/spec/architecture.md` still says "client (Ollama/Groq)". It is not edited (the WP asks
   only for model.md).

## Numbers
Environment: Intel i5-6600K (4 cores), WSL2, CPython 3.12, uv 0.13.2; idle machine (load
0.1–0.2), no Ollama run; OpenRouter API on 2026-10-23.

**Tests.** Default `pytest -q`: 393 passed, 8 deselected in 70.7 s (WP6c start: 379 in 69.8 s,
same machine). The 14 new default tests take about 1 s. `-m "data or slow"`: 22 passed, 379
deselected in 438.3 s on f864c7d (442.9 s on 271f320; 593.5 s in WP6b under load).

**Replays (smoke size, Ollama answers from the cache, no Ollama call).** Every row of the replay
equals a committed row, with no column excluded (latencies are the recorded ones):

| Study | Replay | Rows equal to the committed run | Wall |
| --- | --- | --- | ---: |
| events `--limit 4` | `--cache-mode replay` | 40 of 40 (`results.csv`) | 1.2 s |
| proposals `--limit 3` | `--cache-mode replay` | 6 of 6, `proposals.csv` 14 of 14 | 1.7 s |
| explanations `--limit 3` | `--cache-mode replay` | 3 of 3 | 1.1 s |
| RQ1 `--limit 4` | `--replay ollama=<RQ1 bundle>` | 16 of 16, `rounds.csv` 32 of 32 | 1.6 s |

The three dirty runs had all 542 bundle entries in `data/llm_cache/rq5/ollama.jsonl`,
identical, with no duplicate keys. The RQ1 bundle (139 entries) is in git.

**Live OpenRouter calls** (all served by Groq, `openai/gpt-oss-120b`; cost = 0.15 $/M × prompt
+ 0.60 $/M × completion exactly):

| Call | Fields | Tokens | Reasoning | Latency | Cost | Answer |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| probe (short message, event schema) | `reasoning` object | 424 + 377 | 329 | 1.63 s | $0.00029 | valid; return day 17 (true: 15) |
| WP6b event request, resent | `reasoning` object | 1,401 + 201 | 154 | 0.93 s | $0.00033 | valid; return day 17, pretty-printed |
| same request | Groq's `reasoning_effort` | 1,401 + 276 | 241 | 0.84 s | $0.00038 | identical to the direct-Groq answer |
| (direct Groq, WP6b) | Groq's `reasoning_effort` | 1,404 + 114 | 79 | – | – | return day 15 |

**Estimates per step** (calls and tokens per call from the WP6a/WP6b Groq smokes; prices of the
Groq endpoint on OpenRouter, $0.15 / $0.60 per million prompt / completion tokens; Ollama
replay steps from the replay timings and the WP6b CPU share):

| Step | Run | OpenRouter calls | Tokens (prompt + completion) | Cost | Duration |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | RQ5 events, Ollama replay | 0 (246 replayed) | – | – | < 1 min |
| 2 | RQ5 proposals, Ollama replay | 0 (150) | – | – | about 2 min (rollouts; 93 s in WP6b) |
| 3 | RQ5 explanations, Ollama replay | 0 (150) | – | – | < 1 min |
| 4 | RQ1, both backends | 80 + 0–60 repairs | 0.13–0.41M + 0.17–0.29M | $0.12–0.23 | 10–20 min |
| 5 | RQ5 events, both | 200 (+ repairs; none in the smoke) | 0.29M + 0.02M | $0.06 | 3–5 min |
| 6 | RQ5 proposals, both | 150 | 0.22M + 0.04M | $0.06 | 5–8 min |
| 7 | RQ5 explanations, both | 150 | 0.13M + 0.03M | $0.04 | 2–4 min |
| 8 | RQ5 online check | ≈ 819 | 1.18M + 0.24M | $0.32 | 20–30 min |
| | **Total** | ≈ 1,400–1,460 | 2.5–2.9M | **$0.60–0.71** | **about 1 h** |

The single-shot RQ1 calls measured 3.9–6.1 s on Groq, and RQ5 calls 0.8–1.1 s. CP-SAT is
negligible (8 replayed RQ1 sessions in 1.6 s). The online check makes the 819 gated
deliberations of WP5's 20 worlds; WP5 spent 324 s of CPU on those worlds, and the fake online
smoke ran 1.15× WP5's time on its world. Sensitivity: through OpenRouter the resent request used
1.8–2.4× the completion tokens of the direct-Groq answer. With 2× completion tokens everywhere,
the total is about $0.9–1.1. Bundles stay small: about 0.45 KB per RQ5 call and 1.6 KB per RQ1
call, under 0.4 MB per run.

## Commands for the owner
Before the chain: `git pull` on the server, `git status --short` empty, and at least $3 of
OpenRouter credit (the estimate is ≤ $1.1). `OPENROUTER_API_KEY` is in `.env` (presence
checked, value never read). Ollama and the GPU are not needed. `data/llm_cache/rq5/ollama.jsonl`
and `data/derived/decision_states/` must be present; they are on the server.

**The one tmux line** (it works inside tmux too; follow it with `tmux attach -t wp6`, or
`tmux switch-client -t wp6` from inside tmux):

```bash
tmux new-session -d -s wp6 -c ~/projects/sentinel 'bash scripts/wp6_overnight.sh 2>&1 | tee -a wp6_overnight.log; exec bash'
```

It runs steps 1–8 of the table above in order and commits each run directory right after its
run (`WP6c: <step>`, a pathspec commit of `results/wp6`). It stops at the first non-zero exit
and pushes at the end (about 1 h). `bash scripts/wp6_overnight.sh --dry-run` prints the eight
commands. The log is `~/projects/sentinel/wp6_overnight.log` (gitignored).

**Resume from the step that failed.** The last `step N:` line in the log names it. Every
earlier step is committed, and a study that stopped wrote no run directory, so the tree is
clean.
- Exit status 3 (`stopped: …`): a rate limit (wait the time printed) or missing credits (add
  credits). Then resume from step N:
  `tmux new-session -d -s wp6 -c ~/projects/sentinel 'bash scripts/wp6_overnight.sh N 2>&1 | tee -a wp6_overnight.log; exec bash'`.
  Finished calls are in `data/llm_cache/`, so nothing is paid twice.
- Any other error (traceback): fix the cause, then resume from step N. If OpenRouter keeps
  answering 503 ("no available provider") because Groq is unavailable, the agreed fallback is
  `order = ["cerebras"]` in `[backend.openrouter.provider]` of the remaining steps' configs
  ($0.35 / $0.75 per million; new cache keys): commit that, then resume from step N.
- The study printed `done: results/wp6/<run_id>` but the commit failed (a hook): check the hook
  output, then commit by hand:
  `git add -- results/wp6 && SKIP=end-of-file-fixer,trailing-whitespace git commit -m "WP6c: <step>" -- results/wp6`.
  Add `,detect-secrets` to `SKIP` only for a checked false positive. Then resume from step N+1.
- The final push failed: `git push`.

## Open issues / next steps
- Owner: the chain. Architect: review RQ1 and RQ5 on the committed both-backend runs.
- OpenRouter-served answers are not identical to the direct-Groq smokes: one resent request used
  about 2× the completion tokens. In RQ1 (limit 4,096 completion tokens, reasoning included)
  watch for `truncated` issues in the OpenRouter rows. The committed bundles are the reference.
- Spec questions 1–2 (reply text without prompts for real data, invariant 3 wording) and the
  `architecture.md` layout line.
