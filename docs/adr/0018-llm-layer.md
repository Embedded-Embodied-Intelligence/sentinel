# ADR-0018: LLM layer with standard-library backends and a record/replay cache

- Status: accepted
- Date: 2026-10-23
- WP: WP6a

## Context

Invariant 3: every LLM call goes through `sentinel.llm`, with record/replay caching and
JSON-schema-validated outputs, never inside rollouts or simulation loops (ADR-0002). WP6a
allows no new runtime dependency. Backends: local Ollama 0.40.6 with `qwen2.5:7b` (Q4_K_M,
GTX 1060: 12.4 tok/s at `num_ctx` 12288, 76 % of the model in VRAM) and Groq. Groq's
documentation, read **2026-10-23**: production (generally available) text models
`llama-3.1-8b-instant`, `llama-3.3-70b-versatile` (enterprise pricing, not in the plan limits),
`openai/gpt-oss-120b` and `openai/gpt-oss-20b`; preview models may be withdrawn at short notice.
Free-plan limits of `openai/gpt-oss-120b`: 30 requests/min, 1,000/day, 8,000 tokens/min, 200,000
tokens/day; the owner's key reports 8,000 TPM and 1,000 RPD. Strict structured outputs need
`additionalProperties: false` on every object, which the WP's free-form `crew: {role: n}` map
cannot satisfy; best-effort `json_schema` accepts it (tested). Groq charges the tokens a request
uses, not its completion limit (633 prompt tokens with `max_completion_tokens` 7,900 passed).

## Decision

One `LlmClient` protocol, `complete(messages, *, schema, temperature, seed, max_tokens)`, and a
shared call path in `BaseClient`: the `Request` (backend, model, weights digest, messages,
inlined JSON schema, decoding parameters, backend options) is hashed with SHA-256 into the cache
key; modes `record`, `replay` (miss = error) and `auto`; JSON lines in `data/llm_cache/`, one
file per backend, appends under `flock`; a run's used entries become its gzip replay bundle.
Every answer is parsed and validated with pydantic; problems return as `OutputError`. Backends
use `urllib.request`: `OllamaClient` (`format` = schema, weights digest from `/api/show` pinned
in the config), `GroqClient` with **`openai/gpt-oss-120b`**, the strongest generally available
open model (best-effort `json_schema`, `reasoning_effort` low, retries with backoff honouring
`retry-after`, a sliding-window TPM limiter, `QuotaExhausted` when a wait exceeds a bound), and
`FakeLlmClient` for tests. Keys live in a `Secret` and are redacted from every message.

## Alternatives considered

| Option | Why not |
| --- | --- |
| `openai`, `groq` or `ollama` SDKs, `httpx` | New runtime dependencies; three endpoints need little code |
| Strict `json_schema` on Groq (crew as a list of `{role, count}`) | Changes the WP's binding output schema |
| JSON mode (`json_object`) on Groq | No schema guidance; the schema is available in best-effort mode |
| `llama-3.3-70b-versatile` | Not in the free-plan limits; gpt-oss-120b is Groq's featured production model |
| Cache keyed by prompt text only | Model updates, schema or parameter changes would replay stale answers |
| Cap `max_tokens` so that prompt + limit fit one minute's TPM | Not needed (Groq charges usage); it would only cut off answers |

## Consequences

- Runs are reproducible from code and the bundle without a key or a server (replay mode needs
  no digest lookup when the config pins it, and loads no key).
- A changed model, prompt, schema or parameter is a cache miss, never a stale hit.
- gpt-oss-120b on Groq is a hosted model whose fingerprint may change; replies record
  `system_fingerprint`. The free plan's 200K tokens/day makes the Groq run take days; it stops
  on `QuotaExhausted` and resumes from the cache.
- Groq's schema check is best effort: an answer that fails it (HTTP 400 `json_validate_failed`)
  comes back as an answer with `failed_generation`, so the validator and the repair loop see it.
