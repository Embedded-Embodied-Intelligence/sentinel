# WP10: state of the work and QA findings so far (handoff; delete when the report exists)

The session stopped at the usage limit. WP10 is **not done**; nothing is pushed.

## Done
- Task A: tokens, icons, partials, focus mode; all screens rebuilt; ADR-0027; `tests/test_ui_design.py`;
  axe in PL/EN, light/dark, 1280/390; no sideways scroll at 320/390/768. Version 1.2.0 in the files.
- QA driver `scripts/qa_run.py` (`run1`, `run2`, `wrong`), inputs `docs/qa/zespol-portal.txt`,
  `docs/qa/zadania-portal.csv`. Runs `run1` and `wrong` completed into a scratch folder, not docs/qa.

## Fixed (each with a regression test)
- QA-01 major: toast lost when the analysis job reloads the page.
- QA-02 major: ISO dates in error messages.
- QA-03 major: opening a simulation during a run, or after a restart, blocked the page.
- QA-04 major: "no change is needed" shown at a 9 % chance.
- QA-05 major: "3 % → 3 %" with the reason "changes the plan least" gave no reason to act.

## Open findings (severities are proposals)
- major: a check-in dated by a typo (2030-01-01) is saved, and later check-ins must then be later
  still; the log is append-only. Needs a confirmation or a spec question.
- major: leaving a half-filled check-in (language switch, tab, sidebar) loses it silently; proposal:
  `beforeunload` guard for a dirty check-in and settings form (tests then need a dialog handler).
- minor: check-in before the project start saved without a word (allowed by spec 11.1).
- minor: a typed percent of 150 is silently saved as 99.
- minor: import without a file says "file is empty"; CSV errors name the raw column `duration_days`.
- minor: an unknown predecessor shows the raw id (T9) after an import.
- minor: two tabs on the settings: the last save wins without a warning.
- minor: a recommendation is dated the working day after its check-in (day t).
- minor: every check-in adds a "no change" recommendation entry to the history (noise).
- cosmetic: overview Gantt of over 16 rows scrolls inside its card and hides threat rows; keep
  `gantt-tall` for the simulator only. Flags can be crossed by later lines: draw lines first.

## Analysis notes for the report (first run, log in scratch, to be redone)
- Forecast moved sensibly: 70 % at plan; 66 → 3 % at the check-in where "Architektura systemu" grew
  by 4 days on the critical path with one of its people away (likely finish 25 Nov → 14 Dec).
- Approvals: 0 → 9 % as promised; a substitution promised 3 % → 3 % and the forecast then read 1 %.
- Threats named the last tasks in the plan: "Mapa procesów" has no successor, so the "structural"
  rule of spec 11.4 stops filtering them. Actionless for a manager: raise as a spec question.
- Driver: `move_team` treats any absent crew member as a full stop (the engine lets the rest work),
  and "Architektura" stayed at 75 % after the approved substitution: check `crew_names` first.

## Spec questions and deviations for the report
§11.7 kept over the brief: finish and bad-case labels, "jednostki kosztu", action titles (no Kto / Za
kogo), threat sentence, presets, autonomy names, "Stan na koniec dnia", "symulowane scenariusze".
Not built: free-text "Zapytaj Sentinela" (new LLM role) and rejection reasons (new stored field,
invariant 7). "No change" pinned last in the comparison against §11.5 item 6 (the WP allows arranging).
History: a check-in's detail is inline, there is no snapshot page. Team step: names are generated
("Tester 1"), an emptied name is still an error.

## Left to do
1. Fix the two open majors with tests; list the rest. 2. `qa_run.py run2`, never run yet. 3. Final
`run1`, `run2`, `wrong` into `docs/qa`. 4. `scripts/ui_screenshots.py` into `docs/ui` (the PNGs there
are still the old design); before/after note per screen. 5. Update both user guides, the usability
protocol and `baseline-timing.json` to the new labels. 6. `docs/qa/raport-qa-pl.md`,
`docs/reports/WP10.md`, `docs/notes/WP10.md`, roadmap. 7. Gate, `-m "data or slow"`, `-m e2e`,
`reproduce --check`, release zip 1.2.0 (no tag), push, delete this file.
