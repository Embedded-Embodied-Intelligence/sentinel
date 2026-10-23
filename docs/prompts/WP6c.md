# WP6c — Clean RQ5 manifests, privacy-safe cache, OpenRouter backend, overnight run chain

Fresh session (`/clear`). Small WP (target ≤ 1.5 h): a bug fix, a privacy option, a cloud backend, spec answers,
and the exact command chain for the owner's overnight runs.

<context>
- `CLAUDE.md`, `docs/spec/model.md` §10, `docs/reports/WP6b.md` (spec questions),
  `src/sentinel/experiments/{rq5_common,event_study,proposal_study,explanation_study,online_study,wbs_study,runs}.py`,
  `src/sentinel/llm/` (cache, Groq client), ADR-0018
- skills `spec-guard`, `experiment-run`, `wp-report`

**Bug (architect's review):** the three committed RQ5 Ollama runs
(`results/wp6/20261023-143419-97e5d945`, `…-145842-9acf6e1d`, `…-151739-9d9075b6`) have
`git_dirty: true` although the owner's tree was clean: `rq5_common` calls `runs.git_state()`
when the manifest is written, i.e. after the run's own outputs exist in the tree. Every other
runner takes it before the run directory exists. The LLM answers are in `data/llm_cache/`, so
the runs can be repeated in replay mode at the cost of their rollouts only.

Groq's paid Developer plan is temporarily unavailable, and the free plan (8K tokens/min,
200K/day) would block the repository for about two weeks. **Decision:** the cloud runs use the
same model, `openai/gpt-oss-120b`, through **OpenRouter** (pay as you go, OpenAI-compatible),
with provider routing pinned to Groq (`provider: {order: ["Groq"], allow_fallbacks: false}`), so
model and serving hardware stay those of the WP6a/WP6b Groq smokes. The owner puts
`OPENROUTER_API_KEY` into `.env` (never read or print it). If Groq is unavailable on OpenRouter,
the fallback is Cerebras as the pinned provider; record which provider served each call (from
the response) in the cache and the manifest.

Answers to the WP6b spec questions (binding):
1. LLM calls are forbidden inside the engine and inside rollouts; the agent may call the LLM at
   a deliberation in a simulated world (online check), always through the record/replay cache.
   Reword §10 accordingly.
2. Privacy: add a cache mode `store_prompts = false` that stores only the request key (hash),
   model metadata and the response — never the messages. It is **mandatory for real
   (non-synthetic) data**; research runs on synthetic messages keep the full records. Write it
   into §10 and invariant 7's notes.
3. "About N days" means an announced lower bound of N days: accepted.
</context>

<task>
0. **Spec v1.9.1** (commit `spec: LLM calls at deliberations, privacy-safe cache (v1.9.1)`):
   answers 1–3.
1. **Fix**: every runner (including `online_study`) takes `git_state()` before any output of
   the run is written. Test: on a clean temporary git repository a fake-backend smoke run of each
   RQ5 runner reports `git_dirty: false`. Remove the three dirty run directories in a separate
   commit (`WP6c: remove RQ5 Ollama runs with wrong git state (rerun from cache)`).
2. **Privacy-safe cache**: implement `store_prompts = false` (record and replay work by key;
   no message text in the file); tests: a record/replay round trip works and the file contains no
   message text.
3. **OpenRouter backend** (ADR-0018 amendment): generalise the Groq client into an
   OpenAI-compatible client (base URL, key variable, extra request fields) and add backend
   `openrouter` with the provider pinning above, `temperature 0`, fixed seed, JSON mode as the
   provider supports; keep `groq` working. Check OpenRouter's documentation for provider routing,
   error codes and limits; the rate limiter uses response headers when present, config values as
   fallback; keep the exit-status-3 resume behaviour (also for 402 "insufficient credits", with a
   clear message). The study configs get backend `openrouter` as the cloud backend (Groq stays
   available as an option). Tests with scripted HTTP responses (routing fields sent, provider
   recorded, 402 and 429 paths, key redacted). One live smoke call if the key is present.
4. **Overnight chain**: give the owner **one tmux command line**, to be started on a clean
   tree, that runs in order and commits each run directory right after it finishes (pathspec
   commits, `-- results/wp6`), then pushes at the end:
   1. the three RQ5 Ollama runs again in replay mode (no Ollama calls; a cache miss is an error);
   2. the RQ1 run with both backends (Ollama replays from the committed RQ1 run's cache;
      cloud = OpenRouter);
   3. the three RQ5 runs with both backends;
   4. the online check (OpenRouter).
   Estimate each step's duration, tokens and cost (OpenRouter price of the pinned provider)
   from the WP6a/WP6b measurements. The chain stops
   on the first non-zero exit; say how to resume from the step that failed.
5. `wp-report` (`docs/reports/WP6c.md`); roadmap `WP6: in progress: WP6c done, runs pending`.
</task>

<constraints>
- No change to study semantics or metrics; results of a replayed run must equal the committed
  ones in every column except timing and git fields (check it on one smoke-sized replay).
- Secrets as before. No new dependencies. Default `pytest -q` ≤ 75 s on an idle machine.
- Do not start the chain yourself.
</constraints>

<acceptance_criteria>
1. Spec v1.9.1 commit; the removal commit; quality gate and `-m "data or slow"` pass.
2. Clean-manifest and privacy-cache tests exist and pass.
3. The single command line with per-step estimates and resume instructions.
4. Report and roadmap; pushed; clean tree.
</acceptance_criteria>

<report_format>
`docs/reports/WP6c.md` via `wp-report`.
</report_format>
