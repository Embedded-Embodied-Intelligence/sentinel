# The AI features with real models (WP11)

`scripts/ai_live.py` drives the application through Chromium as a manager would, on a fresh data
directory, and writes here a log (`<provider>-log.json`), the server's log and a screenshot of
every step (`shots/<provider>/`). Results and their reading: `docs/reports/WP11.md`.

| Files | Command | What it shows |
| --- | --- | --- |
| `ollama-*` | `uv run python scripts/ai_live.py ollama` | `qwen2.5:7b` on a 4-core CPU: settings test, a 12-task list and prose, a message with two facts, two explanations |
| `ollama-log-run1.json`, `ollama-log-run3.json` | the same, twice more | how much a small local model varies between runs of the same input |
| `openrouter-*` | `uv run python scripts/ai_live.py openrouter` | `openai/gpt-oss-120b` on Groq through OpenRouter: the same flows, with tokens and cost |
| `groq-*` | `uv run python scripts/ai_live.py groq --flows settings` | the settings page's test of Groq: no key, a wrong key, a wrong model, the right one |
| `errors-*` | `uv run python scripts/ai_live.py errors` | a stand-in model that answers invalid JSON, HTTP 500, an HTML page, nothing in time or is down |

Each log ends with the sweep of the data directory, the caches, the server's log and the served
pages for the absence reason of the message (invariant 7): no match in any run.
