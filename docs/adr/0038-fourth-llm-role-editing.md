# ADR-0038: A fourth narrow LLM role, editing a person's text ("redakcja")

- Status: accepted
- Date: 2026-11-13
- WP: WP20

## Context

CLAUDE.md gave the LLM three narrow roles (parse events, propose actions, explain decisions).
The v3 modules Raporty and Finanse (`docs/design/v3-spec.md`, sections 7 and 8) need a model to
edit a report a person wrote for an audience (Zarząd, Finanse, Zespół, or editing only) and to
write a board summary from a fact sheet that code computed. The supervisor's example is exactly
that: AI edits a person's report, removes repetitions, marks the changes and adapts it per
department. Evidence for the design: D14–D17 (`docs/research/decisions.md`).

## Decision

Add role 4, "redakcja": the model gets the text and one audience's style (English, versioned
prompt files `redact*.v1.txt`) and answers `{"text": ...}` only, validated by the schema
`Redaction`, through the record/replay cache without prompts in the application, with no tools
(`sentinel.interpret.redaction`). Its changes are computed by a word-level diff in code and its
facts checked by the fact guard in code; a person accepts or rejects every change, and nothing
of it enters the decision layer or a figure of a project.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Let the model mark its own changes (a list or inline marks) | A model's account of its edits is not verified; the diff is the truth (spec §7), and RQ6 measures how far such an account can be trusted |
| Generate the board summary from a template only | No model needed, but the summary would not show how "AI summarises, never approves" works with a fact guard; the template fact sheet is kept as the source the guard checks against |
| One prompt per audience with the rules repeated | The rules would drift between audiences; one system prompt with a style file per audience keeps them in one place |
| Allow the model to call a function to save or send | Contradicts D19 (no tools); saving, exporting and approving are a person's buttons |

## Consequences

- CLAUDE.md lists four roles; spec §10 points to §11.9 for the fourth, which never runs in the
  engine or a rollout (the same isolation as roles 1–3).
- The edited text of a real report reaches the provider; the application keeps no prompt in its
  cache, and a report is stored only when the person saves it.
- RQ6 (`configs/wp20_rq6.toml`) measures changed, invented and omitted facts per audience and
  model and compares the model's own list of changes with the code diff.
