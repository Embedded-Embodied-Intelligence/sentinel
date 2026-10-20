---
name: wp-report
description: Write the end-of-work-package report docs/reports/WPx.md, update notes and roadmap, then commit and push. Use at the end of every work package (WP), after the quality gate and acceptance checks have been run.
---

# Work package report

Run this only after executing the quality gate and every acceptance check. Report what
actually happened, with evidence. Never mark a criterion PASS without having run it.

## 1. Write `docs/reports/WPx.md` (x = the WP id, e.g. `WP0`, `WP1.1`)

Use exactly these sections:

```markdown
# WPx report — <short title>

- Date: YYYY-MM-DD
- Commit(s): <short hashes>

## Summary
Two to four sentences: what now exists and works.

## Acceptance criteria
| # | Criterion | Command | Result |
| --- | --- | --- | --- |
| 1 | ... | `uv run pytest -q` | PASS (42 passed, 3 skipped) |

## Changes
Files added/modified, grouped by package, one line each.

## Decisions
Choices made within scope, each with a one-line rationale. ADRs created: list or "none".

## Deviations
Anything that differs from the WP prompt or the spec, and why. "None" if none.

## Spec questions
Ambiguities found (see spec-guard skill), with the interpretation used. "None" if none.

## Numbers
Key measurements (runtimes, counts, metrics) in a table. Include environment caveats.

## Commands for the owner
Exact commands the owner must run (e.g. full benchmark in tmux), with expected duration.

## Open issues / next steps
Short list.
```

## 2. Write `docs/notes/WPx.md`

Material for the article/report: method details as implemented, parameter values, design
reasons, references used. Plain prose and tables, 10–40 lines.

## 3. Update `docs/roadmap.md`

Set the WP status to `done` (all PASS) or `blocked: <reason>`.

## 4. Commit and push

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q
git add -A
git status --short
git commit -m "WPx: <summary>"
git push
```

Check `git status --short` before committing: no `.env`, no files under `data/`, no large
binaries. Finally print the report's Summary and Acceptance criteria table to the terminal.
