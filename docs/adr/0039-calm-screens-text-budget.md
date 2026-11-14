# ADR-0039: Calm screens: a tested text budget, one evidence point per block, a short panel

- Status: accepted
- Date: 2026-11-14
- WP: WP21

## Context

The owner's review of 2.0.2: too much on every screen, AI-style dash pauses everywhere, and the
"Dowód" panel cut off at the bottom while the page behind scrolled. v2 spec section 2 already asks
for one screen at a glance and about four blocks above the fold, but nothing checked it, and the
v3 spec put a point on every line of a list. The live demo is the defence's presentation.

## Decision

The budget is written as rules (v3 spec section 10) and tested where a test can see it: the dash
rule on every rendered page and on all our texts at their source, the heading and helper limits
on the catalogue texts the templates use as such, lines and blocks in the browser at 1280×800. A
block has at most one point; its decisions merge into one point (`D05+D24`) whose panel lists
them and their evidence once. The panel opens short (a one-line count, the first item of each
stance, details one click away) and only its body scrolls.

## Alternatives considered

| Option | Why not |
| --- | --- |
| A one-off rewrite reviewed by eye | The next WP would add the long sentences back; the owner asked for a test for the dashes |
| Shorten the registry's titles to six words | They are claims of the research; shortening 90 titles risks their meaning; the budget treats them as content |
| Hide the points until hover | Evidence would no longer be visible; the spec wants it always one click away |
| Collapse whole panels behind one "show all" | It would hide the counter-evidence; the first challenging item stays visible |
| Pulpit's sections remembered on the server | A per-person setting needs accounts; the browser's storage is enough and fails safe to the default |

## Consequences

- A text that breaks the budget fails the default test run (catalogues) or the e2e run (layout).
- A heading or helper produced in Python is not covered by the source test; the e2e line check
  still sees what it renders.
- A point's N is the number of distinct items of its decisions; the point test checks that sum.
- The running demo, started before 2.1.0, renders the new templates with its old code until it
  is restarted (merged points then have no panel route).
