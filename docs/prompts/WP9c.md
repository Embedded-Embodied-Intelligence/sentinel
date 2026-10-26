# WP9c — UI fixes, Docker, public demo, user guide and usability protocol

Fresh session (`/clear`). Read before coding:

<context>
- `CLAUDE.md`, `docs/spec/model.md` §11, `docs/spec/architecture.md`, `docs/reports/WP9b.md`
  (spec questions), `docs/notes/WP9a.md`, `docs/notes/WP9b.md`, ADR-0022–0025, `docs/ui/`
- skills `adr`, `spec-guard`, `wp-report`

Architect's review of WP9b: the screens are clear and in plain Polish. Four things confuse a
manager and are fixed here; then the app is packaged for a company server, deployed as the public
course demo, documented for users and prepared for a usability test with real people.

Answers to the WP9b questions (binding):
1. **One chance number.** The decision itself keeps the racing procedure (§6). For *display*,
   after the decision Sentinel evaluates NOOP, the recommended action and the alternatives it shows
   on the **same 200 sampled worlds as the overview forecast** (same seed), so "no change" on a
   recommendation always equals the overview's chance, and every number on the page comes from one
   comparison. Remove the "rough figure" note.
2. **Threats.** Exclude structural tasks (every source–sink path passes through them) and
   zero-duration tasks from "What threatens the deadline"; rank the rest by how often they are
   critical in the futures where the project is late, and phrase it as "decides the deadline in
   7 of 10 late scenarios". If nothing remains, say that the risk is spread across the plan.
3. **Simulator vs studies.** Accepted; the simulator page says it uses the application's settings
   (at least one temporary person per role), not the research setup.
4. **Wording seen on the screenshots.** Show money-like values as cost units with their meaning
   ("27 z 84 jednostek kosztu (osobodni)") and cost changes also as a share of the budget ("+1
   jedn., +1 % budżetu"). In Polish, the showcase and simulator projects use Polish project, task
   and person names (English in EN); names come from a vocabulary file per language.
</context>

<task>
0. **Spec v2.0.2 and architecture** (commit `spec: display comparison, threats, wording (v2.0.2)`):
   answers 1–4 in §11; `architecture.md` lists `app/` and `app/ui/` and the deployment options.
1. **Fixes** for answers 1–4 with tests (overview chance == "no change" chance on the same
   project and day; structural tasks never listed; PL vocabulary used in PL; cost labels).
2. **Docker** (ADR): multi-stage `Dockerfile` (uv, Python 3.12 slim, non-root user, `HEALTHCHECK`
   on `/api/health`, data in a volume), `docker-compose.yml` with the app and an optional `ollama`
   profile, `.dockerignore`. If Docker is available on the server, build and smoke-test it (start,
   health, create a project through the API) and report image size and start time; otherwise give
   the owner the exact commands.
3. **Public demo** `docs/deploy.md` and `scripts/run_demo.sh`: run `sentinel ui --demo` on
   127.0.0.1 under tmux (or a user systemd service if available), expose it with
   `tailscale funnel` (HTTPS), and verify that per-visitor limits see the real client address:
   trust `X-Forwarded-For` only from 127.0.0.1, and add a check endpoint (local only) that reports
   the address the app sees; document how to stop the funnel. Seed the demo with the PL showcase.
4. **User guide** `docs/user-guide-pl.md` (and `docs/user-guide-en.md`): for a project manager,
   no technical terms: what Sentinel is; first project (wizard, CSV template, describing in words);
   reading the overview; check-ins; recommendations and autonomy; simulator; privacy (availability
   only, never reasons; local AI option); FAQ; uses the screenshots (regenerate them after the
   fixes). Installation for an IT person: Docker compose, or `uv` on a laptop; LLM options and
   costs (none, local Ollama, free Groq, OpenRouter).
5. **Usability protocol** `docs/usability/protocol-pl.md`: a 20-minute moderated test for 3–5
   participants without training — consent note, five tasks (create a project from the CSV
   template; tell when the project will most likely finish; report an absence; decide on the
   recommendation; run the simulator to the end and say who did better), success criteria per task,
   timing, think-aloud notes, the standard SUS questionnaire in Polish, and a results template
   (`docs/usability/results-template.md`) the owner fills in. Add a short automated "task
   timing" e2e run (Playwright) that performs the five tasks and records clicks and time, as a
   baseline for the report.
6. **Release** `1.1.0`: version bump, `RELEASE.md` mentions the app, Docker and the user guide;
   build `dist/sentinel-1.1.0.zip` from a clean tree (do not tag).
7. **Tests**: as listed in task 1; Docker files lint-free (`hadolint` not required; a test parses
   the compose file); demo address check; user-guide links and image paths exist.
8. `wp-report` (`docs/reports/WP9c.md`), roadmap `WP9: done`.
</task>

<constraints>
- No change to research semantics; `reproduce --check` passes. No new runtime dependencies.
- Default `pytest -q` ≤ 90 s; `e2e` separately. Commit after each step group.
- Do not start the public funnel yourself; give the owner the commands.
</constraints>

<acceptance_criteria>
1. Spec v2.0.2 commit; ADR; quality gate, `-m "data or slow"`, `-m e2e` (where Chromium runs) and
   `reproduce --check` pass.
2. The four fixes are visible on regenerated screenshots.
3. Docker files, deploy guide and demo script; user guides PL/EN; usability protocol and
   template; task-timing baseline in the report.
4. `dist/sentinel-1.1.0.zip` built; report, roadmap; pushed; clean tree.
</acceptance_criteria>

<report_format>
`docs/reports/WP9c.md` via `wp-report`.
</report_format>
