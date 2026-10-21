# Work package protocol

Roles: **architect** (Claude in chat) writes specs and WP prompts and reviews results;
**implementer** (Claude Code on the server) implements; **owner** (Kamil) runs prompts,
long experiments and makes final decisions.

## Lifecycle of a WP

1. Owner starts a fresh Claude Code session (`/clear`) in `~/projects/sentinel` inside `tmux`
   and pastes the WP prompt.
2. Implementer reads `CLAUDE.md` and the files listed in `<context>`, then implements only
   the `<task>` within `<constraints>`.
3. Implementer runs the quality gate and every check in `<acceptance_criteria>`. The gate's
   `uv run pytest -q` skips tests marked `slow` (over 30 s); every WP's acceptance check also
   runs `uv run pytest -q -m "data or slow"`, the tests that need the downloaded PSPLIB data
   (`data`) and the slow ones.
4. Long runs (> ~10 min) are not executed in-session: a smoke run is executed and the full
   command is written to the report.
5. Implementer writes `docs/reports/WPx.md` (skill `wp-report`), adds `docs/notes/WPx.md`
   with decisions useful for the papers, updates `docs/roadmap.md`, commits and pushes.
6. Architect reviews the pushed repository and either approves or issues a follow-up prompt
   (`WPx.1`, `WPx.2`, …).

## Gate

A WP is done only when every acceptance criterion is PASS. A FAIL is reported honestly with
evidence; it is never hidden or worked around by weakening a test.

## Prompt format

```xml
<context>files to read, background</context>
<task>numbered steps</task>
<constraints>what not to do</constraints>
<acceptance_criteria>commands and expected results</acceptance_criteria>
<report_format>sections required in docs/reports/WPx.md</report_format>
```
