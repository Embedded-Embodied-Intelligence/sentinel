# WP9d — One comparison for decision, display and explanation in the app

Fresh session (`/clear`). Small WP (≤ 1 h).

<context>
- `docs/spec/model.md` §6, §11, `docs/reports/WP9c.md` (spec questions), `src/sentinel/app/`
- skills `spec-guard`, `wp-report`

Architect's answers to the WP9c questions (binding):
1. Optional tasks excluded when finding structural tasks: accepted.
2. Finished tasks excluded from threats: accepted.
3. and 4. In the **application** (live and simulator modes, §11 only; research semantics §6
   unchanged), the decision, the display and the explanation must come from **one** comparison, so
   a manager never sees an alternative ranked above the recommended action or an explanation whose
   numbers differ from the page. Rule: racing stage 1 stays as in §6; the survivors and every
   candidate shown on the page are then evaluated on the **200 overview worlds** (same seed as the
   overview forecast); rule (6) with its materiality ties is applied to that comparison; the
   decision record, the comparison table, the template explanation and the optional AI explanation
   all use this record. When an alternative has a higher chance but the choice is decided by a later
   component (tie within the materiality threshold), the page says so in one sentence ("Podobna
   szansa (różnica w granicach niepewności); wybrano wariant, który zmienia mniej terminów").
</context>

<task>
0. Spec v2.0.3 (commit `spec: one comparison for app decisions (v2.0.3)`): §11 text for answers 1–4.
1. Implement answer 3/4 in the app services; the research `Sentinel` policy is untouched
   (`reproduce --check` passes; the WP5 regression tests unchanged).
2. Fix the footer version (shows 1.0.0) to read the package version.
3. Tests: on the showcase and on 5 simulator projects, the recommended action's chance equals its
   row in the comparison, no displayed alternative is ranked above it by rule (6), the template and
   (with a scripted fake LLM) the AI explanation cite only numbers from the record; the tie
   sentence appears exactly when a later component decides.
4. Regenerate the screenshots; rebuild `dist/sentinel-1.1.0.zip` as 1.1.1 (version bump).
5. `wp-report` (`docs/reports/WP9d.md`).
</task>

<constraints>
- App only; no change to research results. Default `pytest -q` ≤ 90 s. No new dependencies.
</constraints>

<acceptance_criteria>
1. Spec commit; quality gate, `-m "data or slow"`, `-m e2e`, `reproduce --check` pass.
2. Task-3 tests exist and pass; screenshots regenerated; 1.1.1 zip built; pushed; clean tree.
</acceptance_criteria>

<report_format>
`docs/reports/WP9d.md` via `wp-report`.
</report_format>
