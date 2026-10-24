# WP9b — The user interface: simple, plain-language project control for business users

Fresh session (`/clear`). Read before coding:

<context>
- `CLAUDE.md`, `docs/spec/model.md` §11, `docs/reports/WP9a.md` (API list, spec questions),
  `docs/notes/WP9a.md`, ADR-0022–0024, `src/sentinel/app/`, `src/sentinel/dashboard/` (SVG charts)
- skills `adr`, `spec-guard`, `wp-report`

The users are project managers and business people, not engineers. Success = a first-time user
can create a project, see whether the deadline is at risk, report what happened and act on a
recommendation **without any training and without seeing a single technical term**. Design for
clarity and speed: one primary action per screen, plain language, dates instead of day numbers,
percentages instead of probabilities, progressive disclosure for details.

Answers to the WP9a questions (binding):
1. Onboarding work after a substitution not counting as progress: accepted as a slightly
   pessimistic estimate; document it in §11 and in the user guide ("the estimate improves when the
   task is marked done").
2. Live projects allow at least one temporary worker per role: `u_max = max(1, ⌊γ R_k⌋)` in live
   and simulator modes only (§11); research semantics (§4) unchanged.
3. Deviations (`--config`, disabled Swagger page, calendar convention): accepted.
4. Test budget: the default `pytest -q` limit becomes **90 s** (update CLAUDE.md and the WP
   protocol); end-to-end browser tests are marked `e2e` and run separately.
</context>

<task>
0. **Spec v2.0.1** (commit `spec: live overtime minimum and UI wording (v2.0.1)`): answers 1–2,
   and a §11 table mapping every internal action/term to its user-facing wording in PL and EN
   (e.g. RESEQ-M → "Ułóż zadania na nowo, aby skończyć jak najszybciej" / "Re-plan to finish as
   early as possible"; SHIFT → "Przesuń terminy zadań bez zmiany kolejności"; SUBST → "Zastępstwo:
   <osoba> przejmuje udział <nieobecnej osoby> w <zadanie>"; OVERTIME → "Dodatkowa osoba
   (tymczasowo): <rola> na N dni"; DESCOPE → "Zrezygnuj z zadania opcjonalnego <zadanie>"; NOOP →
   "Bez zmian — plan wciąż jest najlepszy"). No internal term may appear in the UI.
1. **Front end stack** (ADR): Jinja2 templates served by the WP9a FastAPI app, HTMX (vendored,
   pinned, licence file included) for partial updates and job polling, one hand-written CSS file
   with design tokens (light and dark, WCAG AA contrast), no CDN or external request at runtime,
   server-side SVG charts reusing the cockpit code. PL default, EN switch; all strings in message
   catalogues.
2. **Screens** (each with empty, loading and error states):
   - **Start**: project cards (name, deadline, on-time chance with a coloured badge and trend
     arrow, pending decisions), buttons *New project* and *Try the simulator*; a one-paragraph
     "what this is".
   - **New project wizard** (3 steps, progress indicator, back/next, autosave): (1) name, start
     date, deadline, optional budget, how sure the estimates are, how turbulent the team is;
     (2) team: add people quickly (name + role with suggestions, bulk paste "Anna, backend");
     (3) tasks via three tabs — *Describe the project* (text → AI extraction → review table, only
     if an LLM is configured), *Import a spreadsheet* (CSV template download, per-row errors),
     *Add manually* (editable table: name, days, people per role, after which tasks, optional).
     Plain-language validation inline. Finish → baseline plan → project overview.
   - **Project overview** (the main screen): headline "Chance of meeting the deadline: 64 %"
     with the deadline date, most likely finish date and a bad-case date (P90); budget outlook;
     "What threatens the deadline" (top risk tasks in words); pending recommendations as cards;
     Gantt (plan vs actual, today line, absences marked); primary buttons *Check-in* and *Ask
     Sentinel*.
   - **Check-in**: date; the active and next tasks with status controls (not started / in
     progress with a % slider / done with date); *Someone is away* (person, back on date — no
     reason field), *A task grows* (+ days), *New task*; or *Write a message* (AI turns it into
     the same events, the user confirms each). Submit → updated forecast and, if needed, a
     recommendation.
   - **Recommendation**: plain-language title; impact chips (on-time chance before → after,
     expected finish date change, cost change, number of tasks whose dates move); "Why" (template
     explanation, or LLM text with a "checked against the data" badge); alternatives compared in
     a small table; *Approve*, *Reject*, *Decide later*; a note when approval is required and
     why ("affects people" / "costs money" / "changes scope"). Actions applied automatically
     because of the autonomy setting appear as an info card with *Undo* where undo is possible
     (plan changes), otherwise as a log entry.
   - **History**: timeline of check-ins, events, recommendations and decisions, filterable.
   - **Project settings**: autonomy in words (four options: "Only advise me", "May shift dates",
     "May re-plan the order", "May also add people and substitutes"), presets, costs, exports
     (plan CSV, project JSON, report = WP8 cockpit HTML), delete project with confirmation.
   - **Simulator**: pick an example project (small/medium), turbulence, who manages it
     (*Sentinel* or *Nobody reacts*); buttons *1 day*, *5 days*, *10 days*, *To the end*;
     a live timeline of what happened and what Sentinel did; at the end a side-by-side comparison
     with "nobody reacts" on the same events; a *Show the report* link (cockpit).
   - **Settings (app)**: AI provider (none, local Ollama, Groq, OpenRouter) with *Test connection*;
     keys entered once, stored server-side, shown masked; in demo mode read-only.
   - **How it works**: one page in plain language (simulate before acting, goals, what the AI
     does and does not do, privacy: availability only, never reasons) with links to the
     repository and the paper.
3. **UX rules** (check every screen): no internal terms (task 0 table); numbers rounded for humans
   (percent without decimals, dates as "Mon 14 Mar"); one primary button per screen; destructive
   actions confirmed; every long operation shows progress and never blocks the page; keyboard
   navigation and visible focus; labels on all inputs; colour never the only signal; works at
   1280 px and on a tablet (≥ 768 px); page weight small (no frameworks).
4. **Tests**: template rendering tests for every screen and state (PL and EN), a checker that
   fails on any internal term or missing translation, form validation tests; end-to-end tests
   with Playwright (dev dependency; Chromium as installed for Playwright on the server), marked
   `e2e`: (a) create a project by CSV, check-in with an absence, get and approve a
   recommendation, see it in history; (b) simulator to the end with the comparison; (c) demo mode
   isolation in two browser contexts; (d) keyboard-only path through the check-in; automated
   accessibility scan of the main screens (axe-core vendored for tests only) with no serious
   violations.
5. **Screenshots** for the report and the presentation: a script captures the main screens in PL
   at 1280×800 (start, wizard step 3, overview, check-in, recommendation, simulator comparison)
   into `docs/ui/` (committed, PNG, total ≤ 3 MB).
6. `wp-report` (`docs/reports/WP9b.md`, `docs/notes/WP9b.md` with the screen map and UX rules),
   roadmap `WP9: in progress: WP9b done`; ADR for the front-end stack.
</task>

<constraints>
- No change to research semantics; `reproduce --check` passes. The app never shows a stack
  trace to users (friendly error page with a reference id; details in the server log).
- No new runtime dependencies beyond WP9a's; dev: `playwright` only. Vendored JS: HTMX (and
  axe-core for tests) with pinned versions and licences.
- Default `pytest -q` ≤ 90 s; `e2e` separately. Commit after each step group.
</constraints>

<acceptance_criteria>
1. Spec v2.0.1 commit; ADR; quality gate, `-m "data or slow"`, `-m e2e` and `reproduce --check`
   pass.
2. All screens exist in PL and EN; the internal-term checker passes; accessibility scan has no
   serious violations.
3. Screenshots committed; report lists them.
4. Report, notes, roadmap; pushed; clean tree.
</acceptance_criteria>

<report_format>
`docs/reports/WP9b.md` via `wp-report`; include the e2e timings and the page weights.
</report_format>
