# WP6c notes — clean manifests, privacy-safe cache, OpenRouter backend

**Where the LLM may be called (spec v1.9.1, §10).** Never inside the engine (the simulator of
§2–§3) or inside a rollout. In a simulated world only the agent calls it, at a deliberation that
passed the needs gate (the RQ5 online check); the rollouts that evaluate its proposals make no
call. The import boundary enforces it: no simulation, scheduling, forecasting, policy or agent
module imports the LLM layer; the proposer is injected by the experiment runner.

**Privacy-safe cache (§10, invariant 7).** A cache record holds the request key (SHA-256 of the
full request: backend, model, weights digest, messages, schema, decoding parameters), the model
metadata and the reply. With `store_prompts = false` the messages are not stored; record and
replay work by the key alone, because the key is recomputed from the request at call time. Such
a cache refuses to open a file that holds messages, so neither the working cache nor a replay
bundle can mix in message text. It is mandatory for real (non-synthetic) data; the RQ1 and RQ5
runs use synthetic descriptions, messages and fictional rosters and keep full records
(`store_prompts = true` in their configs). Residual risk: the reply is stored, and an answer
that violates its schema (e.g. an extra `reason` field) keeps its raw text.

**Cloud backend.** The cloud model stays `openai/gpt-oss-120b` served by Groq, now reached
through OpenRouter (pay as you go) because Groq's paid plan is unavailable and its free plan
(200K tokens/day) would take about two weeks. Requests pin the provider:
`provider = {order: ["groq"], allow_fallbacks: false, require_parameters: true}`, so no other
endpoint (several serve fp4/int4 quantisations) can answer and no field (seed, JSON schema,
reasoning effort) is silently dropped; the routing is part of the cache key. Decoding as on
Groq: temperature 0, the item's seed, best-effort `json_schema`, `reasoning_effort = low`,
`include_reasoning = false`. Every reply records the provider that served it (OpenRouter's
`provider` field or its router metadata), the generation id and its cost; an answer from a
provider outside the pin is rejected and not cached. Prices on 2026-10-23 (OpenRouter endpoint
list): Groq $0.15 per million prompt tokens and $0.60 per million completion tokens (reasoning
tokens count as completion tokens); fallback Cerebras $0.35 / $0.75.

**Same request, two routes.** One recorded WP6b event request resent through OpenRouter with
Groq's own reasoning fields returned the identical answer text, with 1,401 + 276 tokens against
1,404 + 114 directly on Groq (241 against 79 reasoning tokens); with OpenRouter's `reasoning`
object it returned another answer (a wrong return day). Hosted answers vary between calls and
server fingerprints, so each run's committed replay bundle is its reference.

**Clean provenance.** Every runner takes the git state when it starts, before any output exists,
and the owner's chain commits each run directory before the next run starts, so a run made on a
clean tree reports `git_dirty: false` (the three RQ5 Ollama runs of WP6b reported `true` and are
repeated from the cache).
