# ADR-0028: AI calls a person waits for: limits, plain failures, retries and prompt aids

- Status: accepted; the prompt aids of a check-in message superseded by ADR-0032 (WP14)
- Date: 2026-11-02
- WP: WP11

## Context

The application's three AI features (a project from a description, a check-in from a message,
an explanation) were first run end to end with real models in WP11 (`scripts/ai_live.py`,
`docs/qa/ai/`). The LLM layer was built for studies: 1800 s per local call, 300 s and six
retries per cloud call, failures as exceptions, a cache that replays every recorded answer,
prompts in the study's terms. On the pages every failure read "the AI did not answer"; an
invalid answer was replayed when the manager asked again; `qwen2.5:7b` got the weekday
arithmetic and the factor of "3 more days" wrong; both models invented role names and repeated
action labels ("SUBST(4)"); and the explanation held the project's lock for the minute a local
model writes.

## Decision

The application keeps the study semantics of spec section 10 and adapts only its own calls: a
limit per call for a person waiting (600 s for Ollama, 90 s and two retries for a cloud model,
`llm_timeout_s` in the app config), every failure mapped to a plain message by its kind, a
request-scoped cache that forgets answers withheld as invalid, prompt aids that do the
arithmetic the rules ask for (the next working days with their weekday, the factors of 1–10
more days, the team's role names), and display-only rewording of labels in an AI text.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Use the study's limits and retries | a manager could wait 30 min (local) or over 35 min (cloud) for "try later" |
| One generic error message | cannot tell a wrong key from a model that is down; the manager cannot act on it |
| Replay withheld answers as studies do | asking again would always show the same failure |
| Validate and repair only (no prompt aids) | a repair round of a withheld answer cannot show the values, so the model repeats them |
| Change the explanation record to use names | changes the §10.4 record and its faithfulness check, which the studies fix |
| A larger local model | needs more than the 6 GB GPU and 4 cores of the target machines |

## Consequences

The research code paths are unchanged (`reproduce --check` identical); the prompt aids exist
only in `app.llm.LiveContext` and `with_team_roles`. The text shown under "In other words (AI)"
is not byte for byte the logged answer; the log keeps the original. A role the AI names that is
not in the team stays visible in the task table until the manager changes it.
