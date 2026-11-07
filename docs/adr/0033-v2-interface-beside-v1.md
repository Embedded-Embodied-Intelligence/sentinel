# ADR-0033: The v2 interface under /v2 beside the first one, with its own design system

- Status: accepted
- Date: 2026-11-07
- WP: WP15

## Context

The owner judged the interface of WP10–WP14 overwhelming; a design workshop produced
`docs/design/v2-spec.md` (principles, decision model, numbers, visual system, glossary, ten
screens). The owner presents on Monday and needs the current interface as a fallback, and WP15
builds only five of the ten screens. ADR-0025 fixes the stack (FastAPI, Jinja2, HTMX, hand-written
CSS, inline SVG, system fonts, no CDN, no new runtime dependency).

## Decision

v2 is a second set of routes under `/v2` (`app/ui/v2/`, templates `templates/v2/`,
`static/sentinel-v2.css`, `static/sentinel-v2.js`) on the same services, store and sessions; the
pages at `/` are unchanged except for one link "Nowy wygląd (v2)". v2 has its own texts
(`ui/v2/text.py`, falling back to the first catalogue for shared formats), tokens (light default,
dark, system; the choice in the cookie `sentinel_theme`, rendered by the server into
`<html data-theme>` so there is no flash), glass only on the sidebar, and calm placeholders
("Wkrótce") for the WP16 screens that link to the first interface's page doing that work.

## Alternatives considered

| Option | Why not |
| --- | --- |
| Restyle the pages at `/` in place | no fallback for Monday; v1's tests and usability protocol pin its texts and flows |
| A front-end framework or a CSS library | a new runtime dependency and a build step (ADR-0025) |
| One stylesheet for both, themed by a class | v1's tokens and components would leak into v2 and the reverse; two files are simpler to retire one of |
| Theme in `localStorage` only | the server could not render it, so dark pages would flash white on every load |

## Consequences

- Both interfaces work on the same data: a project can be opened in either, and a decision taken
  in one is seen in the other. Their differences in behaviour are only those the v2 decision model
  needs (the gate level of v2's deliberations, spec §11.5 and §11.8).
- Until WP16 the two must be kept working side by side; when the owner switches, `/` can redirect
  to `/v2` and the first interface's files can be removed.
- v2's texts are tested like v1's (both languages, placeholders, keys used, internal terms).
