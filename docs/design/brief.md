# Prompt for Claude Desktop (with Claude in Chrome): design brief for Sentinel

Paste everything below the line into Claude Desktop with the Chrome extension connected and
Mobbin open and logged in.

---

You are a senior product designer. I am building **Sentinel**, an open-source web app for project
managers (repository: https://github.com/Embedded-Embodied-Intelligence/sentinel). It tells a
manager the chance of meeting the deadline, what threatens it, and recommends actions (re-plan,
substitute an absent person, add a temporary person) that the manager approves or rejects. Users
are business people, not engineers. The current UI works but looks like an engineering prototype.

Current screens (Polish UI, English switch): Start (project cards) · New-project wizard (3 steps:
basics, team, tasks) · Project overview (headline "Szansa na dotrzymanie terminu: 39 %", deadline,
most-likely and bad-case finish dates, budget, pending recommendation cards, "What threatens the
deadline", Gantt chart) · Check-in (task progress, absences, task growth, new task, or a free-text
message for AI) · Recommendation (impact chips before → after, why, comparison table of options,
Approve / Reject / Decide later) · History · Project settings (autonomy level in words, exports) ·
Simulator (advance 1/5/10 days / to the end, timeline, comparison with "nobody reacts") · App
settings (AI provider) · How it works. Screenshots: `docs/ui/pl_*.png` in the repository.

**Task.** Use Mobbin (I am logged in in this Chrome) to study the web apps of top products with
a calm, trustworthy, data-forward feel. Start with PayPal web
(https://mobbin.com/apps/pay-pal-web-5d6c70a1-e83b-4a81-9126-62fcfc7bd5df/e4b41d38-2007-46e9-be7a-6c7cffa08da7/screens),
then pick 3–4 more that fit "clean, simple, project-manager vibe" — for example Wise, Revolut
Business, Stripe Dashboard, Linear, Asana or Monday — and look at their dashboards, detail pages,
forms/wizards, tables, empty states, confirmation flows and navigation.

**Rules.** Take *patterns and principles* only: layout, hierarchy, spacing, typography scale,
how headline numbers and status are shown, how decisions and confirmations are designed. Do
**not** copy any brand's logo, name, illustrations, icons, exact colour palette or distinctive
trade dress; Sentinel needs its own calm identity (one accent colour, neutral greys, reserved
status colours). Everything must stay accessible (WCAG AA contrast, visible focus, not colour
alone) and work without any external fonts or CDNs (system font stack is fine).

**Deliverable:** one Markdown file `design-brief.md` (English) that a coding agent can implement
without seeing Mobbin:
1. Design principles (5–8 bullet rules, each with the pattern it came from, e.g. "one hero
   number per screen, as on PayPal's balance view").
2. Design tokens: colours (light and dark, with hex and contrast notes), type scale (sizes, weights,
   line heights), spacing scale, radii, shadows, breakpoints.
3. Components: app shell and navigation, page header, hero metric card, KPI tiles, status badge,
   recommendation card, comparison table, form fields, wizard stepper, buttons (primary /
   secondary / destructive), toasts, empty states, timeline, Gantt styling.
4. Screen-by-screen layout for every Sentinel screen listed above (what goes where, what is
   primary, what is hidden behind "details"), with ASCII wireframes.
5. Microcopy tone for Polish (short, calm, no jargon) with 10 before → after examples taken from
   our current screenshots.
6. A short "do not" list.

Show me the brief in the chat and also offer it as a downloadable file.
