# ADR-0029: Model output a person reads may be in the interface language

- Status: accepted
- Date: 2026-11-03
- WP: WP12

## Context

CLAUDE.md invariant 3 says that prompts and LLM data are in English. The CEO/QA test of 1.3.0
(B7) found the AI explanation on a Polish page in English, labelled "(AI, po angielsku)", and in
the model's terms ("stability was the first component where they differed"). The research
explanation prompt, its record, its faithfulness check (spec section 10.4) and the RQ5 studies
are English and must stay so (`reproduce --check` compares their outputs byte for byte).

## Decision

Text that the application shows to a person may be written by the model in the page's language:
the application adds a short English instruction to the English prompt ("write the summary in
Polish, in plain words", `prompts/explain_live.v1.txt`) with the actions as the page names them,
checks the text with the pages' list of internal terms (`app/terms.py`), asks once more on a hit
and otherwise shows only the template explanation. Prompts, cited facts, research data and logs
stay English.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Keep English and translate the page's label | the CEO's point: a Polish manager reads Polish |
| Translate the English answer with a second call | two calls, and the translation is not checked |
| A Polish prompt | a second prompt to keep equal to the research one; invariant 3 |
| Machine translation library | a new dependency, and no faithfulness check of what it writes |

## Consequences

The faithfulness check reads a Polish decimal comma as a point. A cache record of an explanation
differs by the instruction's language, so a Polish and an English page do not share answers. The
research path (`interpret.explain.explain`) is unchanged.
