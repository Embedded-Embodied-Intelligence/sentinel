# ADR-0032: The dates of a check-in message are named by the model and settled by code

- Status: accepted
- Date: 2026-11-05
- WP: WP14

## Context

In the owner's rehearsal of the usability test the application's message parser (the research
parser of spec section 10.2 with prompt aids) turned a report of three facts into one absence
with both dates wrong: it was asked for working-day numbers and counted them across the 11
November holiday, and progress and finishes were outside its event types. The WP14 prompt fixes
the approach (calendar dates with the words they came from, resolved by code, questions instead
of silent shifts; spec section 11.3, v2.3.0); this records how the code does it.

## Decision

The application has its own reader (`app/message_reader.py`, prompt `checkin_message.v1`): items
of the check-in form with clause numbers, each date as `{"day": "YYYY-MM-DD", "words": ...}`.
`app/date_words.py` reads the words (Polish and English: weekdays and months in every case,
"jutro", "wczoraj", "Wigilia", "do końca tygodnia", "przyszły") and keeps the model's date only
if the words allow it; contradictions, two possible days ("od poniedziałku" in the present
tense, unless the clause's tense decides) and non-working days become questions. The words of a
date must be words of a closed date vocabulary that occur in the message; any other word is an
issue, so a cache without prompts keeps only the issue list and no reason for an absence can be
stored. Task words are matched to the project's tasks by word forms (a common beginning), words
that fit several tasks ask.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Better prompt aids for day numbers | The model still counts; the rehearsal failed with them |
| Dates parsed by code alone | Free speech ("po świętach", "za tydzień") needs the model; code checks what it can |
| A blacklist of reason words | It misses every reason not listed ("w szpitalu", "L4"); a whitelist cannot |
| Task ids from the model | A model picks one of two "testy" silently; words let code see the ambiguity |
| Accept the model's choice of "od poniedziałku" | It took the Monday past in 3 of 4 cases where the next one was as likely |

## Consequences

The evaluation set `docs/qa/ai/messages-pl.jsonl` measures the reader per provider
(`scripts/messages_eval.py`). A phrase with a word outside the vocabulary costs a repair round,
which a small local model does not always win (qwen2.5:7b failed 2 of 10 readings). The research
parser, its prompt, schema and corpus are unchanged; `reproduce --check` is not affected.
