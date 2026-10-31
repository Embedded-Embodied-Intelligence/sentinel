# WP10 QA problem log

Every problem found by the browser runs of 30–31 October 2026 (`scripts/qa_run.py`, Sentinel 1.2.0),
by severity (Nielsen 1994): blocker 0, major 9, minor 12, cosmetic 3. All are fixed, the last eight
in 1.2.1 (spec v2.1.1). The owner's reading copy is [raport-qa-pl.md](raport-qa-pl.md). Screenshots
show the page after the fix unless marked "before".

## Major: all fixed, each with a regression test

**QA-01. The toast of a check-in was lost.** Fixed in 248b8fd.

- Steps: save a check-in on a project with a deadline.
- Expected: "Check-in saved. Chance: 79 % → 51 %" stays readable.
- Actual: the analysis reloaded the page and the toast went with it.
- Screenshot: [after](shots/run1/029_c5_overview.png).
- Test: `test_the_toast_of_a_check_in_survives_the_analysis_that_follows`.

**QA-02. ISO dates in error messages.** Fixed in 4e975fd.

- Steps: report the start of a task whose people are busy.
- Expected: the date in words, as on every page.
- Actual: "On 2026-09-16 there are not enough free people…".
- Screenshot: [before](shots/before/022_c3_refused.png).
- Test: `test_messages_show_dates_in_words`.

**QA-03. A simulation at work blocked its page.** Fixed in bde1954.

- Steps: "To the end", then back and open it again; or open a finished simulation after a restart.
- Expected: the page opens at once.
- Actual: over 30 s of a blank wait, over a minute after a restart.
- Screenshot: [after](shots/wrong/028_sim_again.png).
- Tests: `test_a_simulation_at_work_shows_its_progress_without_waiting_for_it`,
  `test_a_run_can_be_left_reopened_and_cancelled`,
  `test_a_cancelled_run_stops_at_its_next_day_and_only_a_run_can_be_cancelled`.

**QA-04. "No change is needed" at a 9 % chance.** Fixed in 163e88a.

- Steps: a project in trouble for which Sentinel finds no better move.
- Expected: an honest sentence.
- Actual: "No change is needed: the plan is still the best".
- Screenshot: [before](shots/before/053_c9_overview.png).
- Test: `test_keeping_the_plan_says_no_change_is_needed_only_if_the_goals_are_met`.

**QA-05. A recommendation "3 % → 3 %" gave no reason to act.** Fixed in 163e88a.

- Steps: open a recommendation that does not raise the chance.
- Expected: what it gains is visible.
- Actual: only "changes the plan least".
- Screenshot: [before](shots/before/026_c4_recommendation.png).
- Test: `test_a_recommendation_shows_what_it_gains_when_the_chance_does_not_move`.

**QA-06. A typo in a check-in's date damaged the project for good.** Fixed in f6b6ba2.

- Steps: type the year 2030 as the check-in's date.
- Expected: a question before saving.
- Actual: saved at once; every later check-in had to be dated after 2030 (the log is append-only).
- Screenshot: [after](shots/wrong/035_check-in_far_in_the_future.png).
- Tests: `test_only_a_date_far_ahead_needs_a_confirmation`, `test_a_check_in_far_in_the_future_asks_first`.

**QA-07. Leaving a form lost what was typed.** Fixed in 31dbed8.

- Steps: fill half a check-in, then click a tab or switch the language.
- Expected: a question before leaving.
- Actual: the entries were gone without a word.
- Screenshot: none; the question is the browser's own dialog, which a screenshot does not capture.
- Test: `test_leaving_a_half_filled_form_asks_first`.

**QA-08. "Report" opened the research cockpit.** Fixed in 46e4fca.

- Steps: "Show the report", or the export in the project settings.
- Expected: a page for a manager.
- Actual: ISO dates, "0.09" for 9 %, tasks as numbers, NOOP, P(C ≤ D), instance ids.
- Screenshot: [after](shots/run1/056_report.png).
- Test: `test_the_report_is_for_people_and_travels_alone`.

**QA-09. "0 %" for weeks, then a finish on time.** Fixed in 46e4fca.

- Steps: the medium simulator example with Sentinel.
- Expected: what the number means is said.
- Actual: nothing said that the forecast assumes no further changes.
- Screenshot: [after](shots/run2/013_medium_after_10.png).
- Test: `test_the_forecast_says_it_assumes_the_plan_stays_as_it_is`.

## Minor and cosmetic, fixed in passing

**QA-10 (minor). An expected cost above the budget had no warning.** Fixed in 73c0edb.

- Steps: approve temporary people until the expected cost passes the budget.
- Expected: a warning; actual: only the number, 113 %.
- Screenshot: [after](shots/run1/061_overview_final.png).
- Test: `test_the_budget_tile_warns_when_the_expected_cost_is_above_the_budget`.

**QA-11 (minor). A typed 150 % was saved as 99 % without a word.** Fixed in dcfc7b0.

- Steps: type 150 as a task's share done.
- Expected: the page shows what will be saved; actual: the value changed only after saving.
- Screenshot: [after](shots/wrong/037_percent_above_99.png).

**QA-12 (minor). An import without a file said "the file is empty".** Fixed in dcfc7b0.

- Steps: press Import with no file chosen.
- Expected: "choose a file first"; actual: "the file is empty".
- Screenshot: [after](shots/wrong/013_csv_no_file.png).
- Test: `test_an_import_without_a_file_asks_for_one`.

**QA-13 (cosmetic). The overview's Gantt scrolled inside its card and hid threatened tasks.** Fixed in
dcfc7b0. Expected: the whole plan in the page's flow; the inner scroll stays in the simulator.
Screenshot: [after](shots/run1/061_overview_final.png).

**QA-14 (cosmetic). Later lines crossed the Gantt's flags.** Fixed in dcfc7b0: lines are drawn first.
Screenshot: [after](shots/phone/run1_gantt.png).

**QA-15 (cosmetic). An absence on the phone's Gantt had no word.** Fixed in dcfc7b0.
Screenshot: [after](shots/phone/run1_gantt.png).

**QA-24 (minor). A simulation took longer than the page said.** Fixed in the report commit.

- Steps: run the small example to the end, from the first day.
- Expected: about half a minute, as announced; actual: 40–57 s (the medium one 2–3 minutes, not "a
  minute or two").
- Screenshot: [after](../ui/en_simulator.png).

## Minor, fixed in 1.2.1 (WP10 follow-up)

The screenshots of this section are of 1.2.0, before the fix.

**QA-16. A check-in dated before the project's start is saved without a word.** Allowed by §11.1.

- Expected: a mild note; actual: nothing.
- Screenshot: [034](shots/wrong/034_check-in_before_the_project_starts.png).
- Fix: a note under the date, for such a date only; nothing is refused.
- Tests: `test_a_check_in_before_the_start_gets_a_note_and_is_not_refused`, and the browser test
  of the check-in.

**QA-17. CSV errors use raw column names and ids** ("duration_days", "T9").

- Expected: words of the application; actual: the file's own names.
- Screenshot: [009](shots/wrong/009_csv_unknown_predecessor_and_role.png).
- Fix: a column in words with its name in the file ("Wiersz 2: czas trwania w dniach
  (duration_days) musi być…"), and an id called an id. The message on an unknown predecessor names
  the task and not the row, as that check runs after the file is read.
- Test: `test_spreadsheet_columns_are_named_in_words_and_as_in_the_file`.

**QA-18. Two tabs on the settings: the last save won without a warning.**

- Expected: a warning that the settings changed meanwhile; actual: "Settings saved".
- Screenshot: none; the page shows nothing, which is the problem (`wrong-log.json`, "two tabs: settings").
- Fix: the form carries a fingerprint of what it was opened on. A save over other changes keeps
  what was typed and says so; saving again replaces them.
- Test: `test_settings_changed_elsewhere_ask_before_they_are_replaced`.

**QA-19. A recommendation was dated the working day after its check-in.**

- Expected: the check-in's date; actual: a check-in of 30 September, "from Thu 1 Oct".
- Screenshot: [030](shots/run1/030_c5_recommendation.png).
- Fix: "status at the end of <check-in's date>" above the action, "The change applies from <first
  working day>" under What changes; history entries sit on the check-in's date.
- Test: `test_a_recommendation_tells_the_check_in_from_the_first_day_of_the_change`.

**QA-20. A "No change" entry after every check-in cluttered the history.**

- Expected: entries that say something; actual: one more line per check-in.
- Screenshot: [057](shots/run1/057_history.png).
- Fix: a line of the check-in, with a link to the analysis; run 1 went from 27 entries to 23. A
  "No change" that no check-in just preceded, as after asking Sentinel, stays an entry.
- Test: `test_no_change_after_a_check_in_is_folded_into_it`.

**QA-21. Growth could not be reported for a task marked "in progress" in the same check-in.**

- Expected: the task is in the list at once; actual: only tasks started earlier are.
- Screenshot: [037](shots/run1/037_c7_form_filled.png) (the list as shown).
- Fix: marking a task as in progress adds it to the list at once; the server already took it.
- Tests: `test_a_task_started_in_the_check_in_can_grow_in_it`, and the browser test of the check-in.

**QA-22. "The actions tie on everything" read oddly when the chance rose from 46 to 55 %.** The
sentence compares the choice with the next option, not with today's plan.

- Expected: it says what is compared; actual: it seems to contradict the numbers.
- Screenshot: [039](shots/run1/039_c7_recommendation.png).
- Fix: "it ties with the next option on everything but simplicity".
- Test: `test_a_tie_says_what_it_compares`.

**QA-23. Threats named the plan's last tasks when a required task had no successor.** The rule was
implemented as §11.4 wrote it, so this one went to the architect (report, spec question 1).

- Expected: threats a manager can act on; actual: "Uruchomienie produkcyjne" (the go-live) decides the
  deadline in 9 of 10 late scenarios.
- Screenshot: [061](shots/run1/061_overview_final.png).
- Fix: spec v2.1.1, §11.4: tasks ranked by late share minus on-time share, from 10 percentage points.
  See the follow-up in `docs/reports/WP10.md` for what that does to the list on this project.
- Tests: `test_threats_rank_by_how_much_more_often_they_decide_the_late_futures`,
  `test_the_last_task_is_no_threat_though_a_side_task_goes_around_it`.
