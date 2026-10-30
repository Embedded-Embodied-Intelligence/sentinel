# ADR-0027: A design system of tokens, partials and focus mode, on the stack of ADR-0025

- Status: accepted
- Date: 2026-10-30
- WP: WP10

## Context

The owner judged the WP9 pages "functional but an engineering prototype". `docs/design/brief.md`
defines principles, tokens, components and every screen's layout. ADR-0025 fixes the stack:
server-rendered Jinja2, HTMX, one hand-written CSS file, no framework, no CDN, system fonts. Spec
§11 fixes the behaviour, the numbers and the wording. Some of the brief's copy and features touch
these (spec questions in `docs/reports/WP10.md`).

## Decision

One stylesheet of custom-property tokens (the brief's values, light and dark), mobile first with
min-width queries; components as Jinja macros (`_ui.html`) and partials (`_sidebar`, `_toast`,
`_gantt`, …); inline SVG icons drawn for this project (`ui/icons.py`); `focus.html` as a shell
without the sidebar for the wizard and a decision. Where the brief's words or features conflict with
§11 or the invariants, §11 and the invariants win and the question goes to the architect.

## Alternatives considered

| Option | Why not |
| --- | --- |
| A CSS framework or utility classes | ADR-0025: tens of kB and a build chain for a dozen screens |
| A vendored icon set | Needs a licence file and a pipeline; about 25 simple line icons are quicker to draw and own |
| A single SVG for the Gantt with names inside | Names cannot stay in view when a phone scrolls, and rows inside `role="img"` cannot take the focus (axe: nested-interactive). So: an HTML column of focusable names beside an SVG whose x positions are percentages and whose row heights are fixed |
| Toasts sent by an `HX-Trigger` header | Most actions end in a full page load (`HX-Redirect`), so a toast rendered from the `flash` parameter covers them; the forecast fragment fills in the new chance out of band |
| Sorting the start page by a blocking forecast of every project | Nothing may block a page: cards sort by the cached chance and fill in after the page |
| A free-text "Ask Sentinel" box and rejection reasons | New LLM role and a new stored field: against the narrow LLM roles, §11.5 and invariant 7 (see the report's spec questions) |

## Consequences

A test (`tests/test_ui_design.py`) holds the tokens and their contrast to the brief and fails on a
style nothing uses or a class no style defines. Own JavaScript grows from 47 to about 400 lines
(drawer, toasts, pickers, change counter), still one file with no dependency. Screenshots are
captured by `scripts/ui_screenshots.py` at 1280×800 and 390×844 in both languages, with a reduced
palette so that `docs/ui/` stays under 5 MB.
