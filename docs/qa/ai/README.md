# The AI features with real models (WP11)

`scripts/ai_live.py` drives the application through Chromium as a manager would, on a fresh data
directory, and writes here a log (`<provider>-log.json`), the server's log and a screenshot of
every step (`shots/<provider>/`). Results and their reading: `docs/reports/WP11.md`.

| Files | Command | What it shows |
| --- | --- | --- |
| `ollama-*` | `uv run python scripts/ai_live.py ollama` | `qwen2.5:7b` on a 4-core CPU: settings test, a 12-task list and prose, a message with two facts, two explanations |
| `ollama-log-run1.json`, `ollama-log-run3.json` | the same, twice more | how much a small local model varies between runs of the same input |
| `openrouter-*` | `uv run python scripts/ai_live.py openrouter` | `openai/gpt-oss-120b` on Groq through OpenRouter: the same flows, with tokens and cost |
| `openrouter-v2.1.5-*`, `shots/openrouter-v2.1.5/` (the message's three steps) | `uv run python scripts/ai_live.py openrouter --flows list,message` | after spec v2.1.5: "chora do piątku" written on Wednesday 21 Oct is read as back on Monday 26 Oct |
| `groq-*` | `uv run python scripts/ai_live.py groq --flows settings` | the settings page's test of Groq: no key, a wrong key, a wrong model, the right one |
| `errors-*` | `uv run python scripts/ai_live.py errors` | a stand-in model that answers invalid JSON, HTTP 500, an HTML page, nothing in time or is down |

Each log ends with the sweep of the data directory, the caches, the server's log and the served
pages for the absence reason of the message (invariant 7): no match in any run.

## Check-in messages and recordings (WP14)

`messages-pl.jsonl` holds 30 Polish status reports on the usability test's project (as planned,
and after the owner's report of 4 November) and the demo's showcase, each with the items its
review should show; `scripts/messages_eval.py` reads them by the application's own path and
scores each item (type, task or person, dates and values exact; an item the review adds counts
against it; a date shown ticked without a question that is not the expected one is counted
apart). Results and their reading: `docs/reports/WP14.md`.

| Files | Command | What it shows |
| --- | --- | --- |
| `messages-eval-before-*.json` | `uv run python scripts/messages_eval.py openrouter --label before` (`ollama --limit 10`) at 30d9df3 | the parser of 1.4.1 (day numbers, absences, growth and new tasks only) |
| `messages-eval-after1-openrouter.json` | the same on the first reader of 1.5.0 | scored against the first expectations (four "od poniedziałku" as the next Monday) |
| `messages-eval-after-*.json` | `uv run python scripts/messages_eval.py openrouter --label after` (`ollama --limit 10`) | the reader of 1.5.0: dates settled by code, progress, finishes and starts |
| `voice-check.json` | `uv run python scripts/voice_check.py` | the owner's message recorded (Windows' Polish voice, 15 s) written out by Groq's Whisper and read by gpt-oss-120b, through the services and in the browser in demo mode by message and by voice |

`--rescore <file>` scores a stored run again against the current expectations without a call.
The owner's message recording is `tests/fixtures/owner_message_pl.wav` (System.Speech, voice
"Microsoft Paulina Desktop", 16 kHz mono PCM, from the text of m01); gpt-oss-120b's recorded
answer to it is `tests/fixtures/owner_message_answer.json`.
