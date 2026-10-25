# ADR-0025: Server-rendered pages with Jinja2, vendored HTMX and one CSS file

- Status: accepted
- Date: 2026-10-25
- WP: WP9b

## Context

WP9b gives the WP9a API pages for project managers and business people: create a project,
see the deadline risk, report a check-in and act on a recommendation without training or a
technical term. The owner fixed the stack (ADR-0022): FastAPI, Jinja2, HTMX, no build chain, no
CDN or other external request at runtime, Polish by default with English, WCAG AA, small pages.
Long operations (plan, recommendation, simulator days) already run as jobs with progress.

## Decision

`sentinel.app.ui` serves the pages from the WP9a app: Jinja2 templates rendered on the server
from the services' views (no second API client), HTMX 2.0.11 (0BSD; vendored and pinned as
`static/htmx-2.0.11.min.js` with its licence, npm integrity checked) for partial updates, forms
and job polling, a few lines of own JavaScript (adding form rows, the CSRF header), and one
hand-written CSS file with design tokens for light and dark mode (WCAG AA contrast). Charts are
server-side SVG built from the cockpit's data assembly. Every string comes from the message
catalogues (`ui/text.py`, `app/messages.py`) in Polish and English; the wording of actions and
terms follows spec section 11.7. axe-core 4.14.0 (MPL-2.0) is vendored under `tests/vendor/` for
the accessibility scan of the end-to-end tests (Playwright, a dev dependency) only.

## Alternatives considered

| Option | Why not |
| --- | --- |
| A single-page app (React, Vue, Svelte) | A build chain, a second language for the views and a much heavier page; ADR-0022 |
| HTMX or a CSS framework from a CDN | External requests at runtime; the demo must work offline and leak no visitor data |
| Tailwind or Bootstrap vendored | Tens of kB of CSS for a dozen screens; design tokens in one file are enough |
| Client-side charts (Chart.js, D3) | JavaScript dependencies and a second rendering of data the server already has |
| gettext `.po` catalogues with Babel | A new dependency; dictionaries checked by a test give the same guarantees |

## Consequences

Pages work without any external request and stay small (HTMX is the only library, 52 kB). The
views are rendered where the data are, so the pages and the JSON API show the same numbers.
Interactivity needs JavaScript for HTMX; forms post through HTMX so that the CSRF header of
ADR-0024 covers them. Updating HTMX means replacing one file and its licence, checking the npm
integrity and running the end-to-end tests. Vendored files are excluded from the whitespace
hooks so that they stay byte-identical to their releases.
