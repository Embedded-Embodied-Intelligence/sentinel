# WP9d report — One comparison for decision, display and explanation in the app

- Date: 2026-10-30
- Commit(s): 9816a95 (spec v2.0.3), b286bf9 (one comparison), e735803 (version 1.1.1, footer
  test, guides), d38424d (screenshots), 6fbb9bb (bench, timing baseline, README, a test out of the
  default run); the report commit adds this report, the notes and the roadmap
- Follow-up: spec v2.0.4 and release 1.1.2, in the last section; it changes when the sentence
  appears, which the sections before it describe for 1.1.1

## Summary
In project and simulator modes the decision, the display and both explanations now come from one
record on the forecast's 200 simulated futures, so a page never ranks an alternative above the
recommended action by rule (6) and an explanation cites only figures the page shows. The research
`Sentinel` is untouched (`reproduce --check`: 117 of 117 identical). On the showcase the page reads
39 % → 55 %, runner-up 53 %, with the sentence "Podobna szansa (różnica w granicach niepewności);
wybrano wariant, który zmienia mniej terminów". Version 1.1.1 is built and the screenshots show it.
The cost is that a simulator run takes twice as long (small example 25 s → 50 s).

## Acceptance criteria
| # | Criterion | Command | Result |
| --- | --- | --- | --- |
| 1 | Spec commit | `git show --stat 9816a95` | PASS (`spec: one comparison for app decisions (v2.0.3)`, `docs/spec/model.md` only) |
| 1 | Quality gate | `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy src`; `uv run pytest -q` | PASS (ruff clean, 350 files formatted, mypy: no issues in 134 source files; 502 passed, 37 deselected in 82.2 s, budget 90 s) |
| 1 | Data and slow tests | `uv run pytest -q -m "data or slow"` | PASS (43 passed, 496 deselected in 690.9 s at d38424d; `src/` is unchanged since; the test moved to this set in 6fbb9bb passes in it, 7.9 s) |
| 1 | Browser tests | `uv run pytest -q -m e2e` | PASS (7 passed in 165.4 s at 6fbb9bb) |
| 1 | Research results unchanged | `uv run sentinel reproduce --check`; `git diff 7dbeae9 HEAD -- src/sentinel/agent src/sentinel/policies src/sentinel/simulation` | PASS (117 of 117 files identical; empty diff; the WP5 regression tests are unchanged and pass) |
| 2 | Task-3 tests exist and pass | `uv run pytest -q tests/test_app_comparison.py -m "data or slow or not slow"` | PASS (15 tests: the showcase in both languages, five J30 simulator projects for 20 working days each, the tiny project; 11 of them in the default run; plus `test_the_ai_explanation_is_checked_against_the_page` in `tests/test_app_api.py`) |
| 2 | Screenshots regenerated | `uv run python scripts/ui_screenshots.py --lang pl` (and `--lang en`); `ls docs/ui` | PASS (22 PNGs: `pl_recommendation.png` shows the sentence, `pl_recommendation_options.png` the table and "wersja 1.1.1") |
| 2 | 1.1.1 zip built | `uv run sentinel release --version 1.1.1` | PASS (20.0 MB, 628 files of commit 6fbb9bb, byte-identical on a second build, no top-level `data/`, no `.env` but `.env.example`; not tagged; rebuilt from the report commit afterwards, which `dist/` holds) |
| 2 | Pushed, clean tree | `git push`; `git status --short` | PASS (the commits up to 6fbb9bb were pushed before this report was written; this report commit is pushed the same way; tree clean) |

What the task-3 tests check, on every deliberation of those projects: the recommended action's
chance equals its row, every row equals the record's and is on 200 worlds with the forecast's seed;
rule (6) recomputed from the rollouts gives the record's choice, reason and runner-up, and no
alternative shown is ranked above the choice; an alternative with a higher chance occurs only when
a later component decided; the template (both languages) and a scripted fake LLM pass the
faithfulness check of §10.4 against the record as shown, and a figure from anywhere else counts as
hallucinated; the sentence appears exactly when a later component decides (on the showcase's pages
and on the simulator's timeline, for each component in both languages by test).

## Changes
- `docs/spec/model.md` — v2.0.3: §11 introduction, §11.5 (the recommendation and "One comparison",
  items 1–7), §11.6 (the simulator decides the same way), §11.7 (the sentence's wording).
- `src/sentinel/app/planning.py` — `AppSentinel`, `stage_one`, `comparison_set`, `contest`;
  `compare` from the decision's own rollouts; `shown_labels` (at most five alternatives, NOOP among
  them); `tie_kind`, `LATER_COMPONENTS`; `half_up`, `shown_chance`; `Recommendation.as_shown`;
  `Comparison.decides`.
- `src/sentinel/app/views.py` — `RecommendationView.tie`, the template explanation from `as_shown`.
- `src/sentinel/app/services.py` — the AI explanation from `as_shown`.
- `src/sentinel/app/cockpit.py` — the detailed report: figures as shown, the simulator's forecasts
  on the forecast's worlds.
- `src/sentinel/app/simulator.py` — `policy_of` uses `AppSentinel`.
- `src/sentinel/app/ui/text.py` — `Texts.tie`, `why.tie.*`; `pct` and `decimal` half up; `why.keep`
  and the simulator's settings note. `ui/project.py` — `why_text`. `ui/sim.py` — the sentence on
  the timeline.
- `src/sentinel/dashboard/world.py` — `forecasts(..., stream="sentinel")`, default unchanged.
- `pyproject.toml`, `uv.lock`, `Dockerfile`, `docker-compose.yml`, `docs/deploy.md`,
  `docs/usability/results-template.md`, `README.md` — version 1.1.1.
- `docs/user-guide-pl.md`, `docs/user-guide-en.md` — what the sentence means. `docs/ui/` — 22 PNGs.
  `docs/usability/baseline-timing.json` — run again.
- `scripts/bench_app_rule.py` (new); `scripts/ui_screenshots.py` (take them after a bump).
- Tests: `tests/test_app_comparison.py` (new); `app_cases.py` (`answer_from`); `test_app_api.py`
  (the AI test, version, the scripted reason); `test_app_live.py` and `test_app_display.py` (the new
  rule); `test_ui_pages.py` (the footer); `test_baseline_policies.py` (one test marked slow).
- `docs/notes/WP9d.md`, `docs/roadmap.md`.

## Decisions
- **A subclass, not a change to the policy.** `AppSentinel(Sentinel)` overrides `deliberate` only,
  so epochs, approvals and the gate stay shared. It repeats about 100 lines of the research
  `deliberate` (and `stage_one` ten lines of `race`), the price of leaving that code untouched; a
  test checks that `stage_one` drops what `race` drops.
- **One rounding.** With 200 worlds half of all chances end in a half per cent, and the old page and
  template rounded them differently: 46 of the 201 values `k/200` differed by a point (0.585: 59 %
  on the page, 58 % in the template). `half_up` now serves the page, the template and the AI's input.
- **The explanations read the record as shown** (`as_shown`): the rows on the page, chances in whole
  per cent, delays in tenths. A stage 1 figure the page does not show therefore counts as made up.
- **The sentence replaces "It was chosen because…"** and follows the runner-up's sentence, so it
  explains the number just read. A kept plan gets it too.
- **At most five alternatives**, as the spec says: the fifth gives way to NOOP (before, NOOP could
  be a sixth).
- **The simulator's sentence is on its timeline**, the page that shows its decisions; a kept plan
  has no timeline entry, so none there. The WP8 report keeps its own wording from the same record.
- **Stage 1 shares the plan cache** with the comparison: a plan part depends only on its objective
  and view (ADR-0017).
- **`scripts/bench_app_rule.py`** is committed so that the comparison of the rules under Numbers
  comes from code; it is informal, writes nothing and is not for the papers.
- ADRs created: none.

## Deviations
- **The footer's code was already right.** It read the installed package's version; "1.0.0" came
  from screenshots taken at 889c1e8, before the bump to 1.1.0 at c485ec9 (`pl_recommendation_options.png`
  showed it), and a running server also keeps the version it started with. So task 2 is a test
  against `pyproject.toml`, a note in the screenshot script and new screenshots, with no change to
  how the version is read.
- **The simulator projects of task 3 run 20 working days each**, not to the end, to keep the test
  to 76 s; the bench runs 16 worlds to the end.
- **The one 7 s test moved out of the default run** (`test_policies_are_deterministic_and_share_the_exogenous_events`,
  WP4, body unchanged). The default run had reached 89–90 s on this machine: 87.7 and 89.9 s before
  this WP's change, 89.0–90.1 s after it, so the change itself did not add to it. It still runs in
  the data-or-slow check, and `test_common_random_numbers_across_policies_and_plans` stays in the
  default run.
- **Two app tests were changed to the new rule**: `test_recommendation_is_the_app_decision_on_the_equivalent_observation`
  pinned the record to the research deliberation, which v2.0.3 reverses; `test_extraction_and_explanations_use_the_configured_model`
  scripted the old deciding component (the absence project is now decided on the chance).
- **Beyond the prompt, because the change makes them stale:** the user guides' paragraph, the
  usability baseline, and README's status (it still said 1.0.0).
- **`-m "data or slow"` now takes 11.5 min**, over the ~10 min guidance of CLAUDE.md; it ran in the
  background. It was run at d38424d and not repeated for the later commits, which leave `src/` as it
  was.
- **Stored data.** A recommendation stored before v2.0.3 keeps its figures and gets no sentence. A
  simulator project replays its advances, so one created before 1.1.1 gives a different run now.

## Spec questions
Readings written into v2.0.3 and marked `# SPEC-Q`; the prompt did not settle them.
1. **The needs gate.** Reading: part of the decision, so it reads the 200 worlds (otherwise a page
   could say "on track" at a chance below the target). It therefore always uses 200 rollouts, not
   `N₁` where the need is clear.
2. **"Stage 1 stays as in §6": also its worlds?** Reading: yes, the seed `derive_seed(project seed,
   "sentinel", t)`, the literal one. Using the first 25 of the 200 worlds instead would save the 25
   rollouts per candidate and leave a single set of worlds in the record; it is one line
   (`racing = comparing`).
3. **"Every candidate shown" before the choice is known.** Reading: the survivors, NOOP and the best
   of the dropped until six are in, all competing, so a dropped one may win. It never did in 704
   deliberations.
4. **The sentence above the target.** Two options at 82 % and 95 % tie because of the cap, and
   "within the uncertainty" would be false. Reading: a second opening, "Both options reach the
   target chance", where both have `p ≥ θ_D − ε_D`.
5. **The rule filters against the best of the set, not pair by pair**, so a choice tied with the
   best could be significantly behind another alternative shown. Reading: rule (6) as written. Of 270
   alternatives shown with a higher chance in the bench, none was.
6. **The sentence is the common case.** A later component decided in 630 of 704 deliberations, so
   under the rule's thresholds the best chances usually tie. Worth a look with the usability test:
   does a sentence that nearly always appears still inform? Answered in the Follow-up below: it now
   appears in 113 of the 704.

## Numbers
Environment: i5-6600K, WSL2, load about 1 unless noted. This machine is slower than during WP9c: the
same default tests took 83.8 s then and 87.7–89.9 s today.

| Quantity | Value |
| --- | --- |
| default `pytest -q` | 502 passed, 37 deselected in 82.2 s (before moving the 7 s test: 503 in 89.0–90.1 s; before this WP's change, same conditions: 490 in 87.7 and 89.9 s) |
| `pytest -q -m "data or slow"` | 43 passed in 690.9 s (WP9c: 38 in 538.9 s); the five simulator projects 75.6 s, `test_sentinel_on_a_j30_world_matches_simulate` 40.8 s |
| `pytest -q -m e2e` | 7 passed in 165.4 s (WP9c: 93.4 s): simulator to the end 77.1 s (37.4 s), the usability tasks 66.4 s (34.9 s) |
| `sentinel reproduce --check` | 117 of 117 files identical |
| showcase (Polish) | first recommendation: on track at 94 %; second: 39 % → 55 %, runner-up 53 %, 6 candidates, decided on plan stability, 1,350 rollouts; the showcase log 0.68 s (WP9c: 0.84 s) |
| small simulator example (idle, one process) | 25.2 s → 50.2 s, 21,250 → 49,650 rollouts |
| rule bench, 15 J30 worlds to the end | on time 2 of 15 under both; mean days late 13.27 (application), 12.87 (research); the application earlier in 2, the same in 10, later in 3; 865 s against 433 s, 646,150 against 278,225 rollouts (3 workers) |
| rule bench, J60 example `j6010_7/1` | finish 81 against 85 (deadline 83); 180.3 s against 83.6 s |
| the small example's run | 8 working days late (2 under the research rule, 18 with nobody reacting); one world, the largest such gap in the bench |
| deliberations in the bench | 704: a later component decided 630; alternatives shown with a higher chance 270, significantly better in a pair 0; a dropped candidate won 0 |
| chances `k/200` where the old page and template differed | 46 of 201 |
| screenshots `docs/ui/` | Polish 11 files, 1,332 kB; English 11 files, 1,199 kB (limit 3 MB per language) |
| `dist/sentinel-1.1.1.zip` | 20.0 MB, 628 files of commit 6fbb9bb (1.1.0: 19.9 MB, 625 files), byte-identical on a second build |

Task-timing baseline (`docs/usability/baseline-timing.json`, machine time, Polish pages; only
task 5 changed):

| # | Task | Clicks | Fields | Seconds (WP9c) |
| --- | --- | ---: | ---: | ---: |
| 1 | Utwórz projekt z szablonu CSV | 9 | 4 | 2.3 (2.2) |
| 2 | Kiedy projekt najprawdopodobniej się skończy? | 0 | 0 | 0.0 (0.0) |
| 3 | Zgłoś nieobecność | 6 | 5 | 0.5 (0.4) |
| 4 | Zdecyduj o rekomendacji | 2 | 0 | 1.6 (1.6) |
| 5 | Symulator do końca: kto poradził sobie lepiej? | 3 | 0 | 59.7 (29.8) |

## Commands for the owner
```bash
# A running server keeps the version it started with: restart the demo to show 1.1.1
scripts/run_demo.sh stop && scripts/run_demo.sh start

# The release (built, not tagged): dist/sentinel-1.1.1.zip; prints the tag command
uv run sentinel release --version 1.1.1
# git tag -a v1.1.1 -m "Sentinel 1.1.1" <commit> && git push origin v1.1.1

# Docker (not installed on this server); the WP9c commands in docs/deploy.md use the 1.1.1 tag
docker build -t sentinel:1.1.1 .

# The comparison of the rules (informal; about 8 min, then 3 min for the J60 example)
uv run python scripts/bench_app_rule.py --workers 3
uv run python scripts/bench_app_rule.py --workers 2 j60/j6010_7/1
```

## Open issues / next steps
- Spec questions 1–6.
- A simulator run takes twice as long: about 50 s for the small example and 3 min for the medium one
  on this machine, and a restart replays a project's advances at that cost. If that is too slow for
  the public demo, spec question 2 saves about a tenth; a smaller `N` for the simulator would need
  an architect's decision.
- The default run has about 8 s of margin; the machine's speed alone moved it by 4–6 s since WP9c.
- From WP9c: the Docker image is not built, the usability test with people has not run, and the
  simulator's detailed report names tasks in English on Polish pages.

## Follow-up
The owner's answer to spec question 6 above: show the sentence only when a displayed alternative has
a strictly higher rounded on-time percentage than the recommended action, otherwise omit it.

- Date: 2026-10-30
- Commit(s): 8086bf5 (spec v2.0.4), 40bfe12 (the rule), afcdcf5 (version 1.1.2, guides), b64cb83
  (screenshots), e3621af (the rule in `CLAUDE.md`); the report commit adds this section, the notes
  and the roadmap

### Summary
The sentence now appears only when an alternative shown has a strictly higher chance than the
recommended action, both in whole per cent as the page shows them; otherwise it is omitted and the
page names the deciding component, as for any other decision. In the bench it is due in 113 of 704
deliberations, where the rule of 1.1.1 gave it in 630. Only text changes: the bench's 16 worlds run
exactly as before, and the research results reproduce (117 of 117). On the showcase, 55 % against
53 % no longer carries the sentence; the page reads "Wybrano ją, ponieważ najmniej zmienia plan."
Version 1.1.2 is built and the screenshots show it.

### Acceptance criteria
| # | Criterion | Command | Result |
| --- | --- | --- | --- |
| 1 | Spec §11, v2.0.4 | `git show --stat 8086bf5` | PASS (`docs/spec/model.md` only: the versions paragraph, §11.5 item 7, §11.6, §11.7) |
| 2 | Quality gate | `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy src`; `uv run pytest -q` | PASS (ruff clean, 352 files formatted, mypy: no issues in 134 source files; 509 passed, 37 deselected in 78.0 s at e3621af, budget 90 s) |
| 2 | Data and slow tests | `uv run pytest -q -m "data or slow"` | PASS (44 passed, 502 deselected in 835.9 s at b64cb83; only `CLAUDE.md` and this report's files changed since) |
| 2 | Browser tests | `uv run pytest -q -m e2e` | PASS (7 passed, 539 deselected in 158.8 s at b64cb83) |
| 3 | Screenshots | `uv run python scripts/ui_screenshots.py --lang pl` (and `--lang en`); `ls docs/ui` | PASS (22 PNGs, 6 changed: the recommendation with and without its options, and the start page, in each language; viewed: no sentence on the showcase's recommendation, footer 1.1.2) |
| 4 | User guides | `git show --stat afcdcf5` | PASS (the paragraph on the sentence in `docs/user-guide-pl.md` and `docs/user-guide-en.md`) |
| 5 | Research results unchanged | `uv run sentinel reproduce --check`; `git diff 7dbeae9 HEAD -- src/sentinel/agent src/sentinel/policies src/sentinel/simulation` | PASS (117 of 117 files identical at e3621af; empty diff) |
| 6 | 1.1.2 zip built | `uv run sentinel release --version 1.1.2` | PASS (20.0 MB, 630 files of commit e3621af, byte-identical on a second build, no top-level `data/`, no `.env` but `.env.example`; not tagged; rebuilt from the report commit afterwards, which `dist/` holds) |
| 7 | Pushed, clean tree | `git push`; `git status --short` | PASS (the commits up to e3621af were pushed before this section was written; the report commit is pushed the same way; tree clean) |

What the tests now check: the boundaries of the rounding in both languages (55 % and 56 %; 54.4 % and
54.5 %, half up; 57.5 % and 58.5 %; 54.5 % and 54.9 %, both shown as 55 %, no sentence; equal; the
choice higher), that any row shown counts and not only the runner-up, and that `why.reason` is on the
page exactly when the sentence is not. On every deliberation of the five J30 simulator projects: the
condition against the rows of the comparison, no sentence on the timeline, and both cases occurring
(`0 < sentence < later`). On the showcase: no sentence at 55 % against 53 %, and the sentence in
Polish once a row shows a higher chance.

### Changes
- `docs/spec/model.md` — v2.0.4: the versions paragraph, §11.5 item 7 (the condition), §11.6 (none on
  the simulator's timeline), §11.7 (the rows' labels).
- `src/sentinel/app/planning.py` — `tie_kind`: the new condition; nothing else in the file changes.
  `views.py` — asks `tie_kind` with the comparison. `ui/text.py` — a docstring. `ui/sim.py` — back to
  its form before WP9d.
- `tests/test_app_comparison.py` — the new condition; `tests/test_app_api.py` — the version.
- `scripts/bench_app_rule.py` — counts the deliberations where the sentence is due.
- `pyproject.toml`, `uv.lock`, `Dockerfile`, `docker-compose.yml`, `docs/deploy.md`,
  `docs/usability/results-template.md`, `README.md` — version 1.1.2.
- `docs/user-guide-pl.md`, `docs/user-guide-en.md` — when the sentence appears. `docs/ui/` — 6 PNGs.
- `CLAUDE.md` — the owner's rule on waiting for a process.
- `docs/reports/WP9d.md` — this section, a pointer in the header, the answer under question 6.
  `docs/notes/WP9d.md` — the sentence's paragraph. `docs/roadmap.md`.

### Decisions
Readings of the owner's wording, all written into v2.0.4.
- **"Rounded" is what the page shows:** `shown_chance`, whole per cent half up, the one rounding of
  WP9d. 58.0 % and 58.5 % read 58 and 59, so the sentence appears; 57.5 % and 58.0 % both read 58, so
  it does not.
- **Both openings follow the condition.** "Both options reach the target chance" is the same sentence
  above the target; left unconditional, it would still appear where no alternative shows a higher
  chance. Its test is now the chosen action alone, `p ≥ θ_D − ε_D`: an alternative with a higher
  chance then reaches it too.
- **Omitting the sentence leaves the usual line.** `why.reason` names the deciding component ("It was
  chosen because it changes the plan the least"), as on a decision made on the chance, so the page
  still says why; a kept plan shows `why.keep` alone.
- **Read at display time.** `RecommendationView.tie` comes from the view and is not stored, so a
  recommendation stored under 1.1.1 follows the new rule and one stored before v2.0.3 still has none.
  There is nothing to migrate, and a simulator project created under 1.1.1 replays the same run.
- ADRs created: none (the owner's decision, entered in the spec).

### Deviations
- **One count added to the bench**, not requested, to measure the effect; the bench stays informal
  and writes nothing.
- **A rule added to `CLAUDE.md`** at the owner's request, in its own commit. My wait for the bench was
  a shell loop on `pgrep -f`, which matched its own command line and never ended; the owner killed it.
  No result is affected: the bench had finished and its output was complete.
- **The data-or-slow run overlapped the bench** (two workers), so its 835.9 s does not compare with
  the 690.9 s above. It and the browser tests were not repeated for e3621af and the report commit,
  which change no code.

### Spec questions
Both are written into v2.0.4 as read here; each is a small change if the owner reads it otherwise.
1. **The simulator's timeline.** It shows no alternatives, so taken literally it never has the
   sentence, and it loses the one it had under 1.1.1. Restoring it would be one call of `tie_kind` in
   `ui/sim.py`, but it would refer to a row the reader cannot see.
2. **Any row shown, not only the runner-up.** The sentence can therefore follow a runner-up with a
   lower chance and explain a row further down the table. The bench does not count how often.

### Numbers
Environment as above.

| Quantity | Value |
| --- | --- |
| the sentence due in the bench | 113 of 704 deliberations, 16 % (the rule of 1.1.1: 630, 89 %) |
| the bench again, the same 16 worlds | finish, days late and deliberations identical in every world under both rules, compared with the saved output of the run above; 730,275 and 313,675 rollouts, as in that run; 704 deliberations, 270 alternatives shown with a higher chance, 0 significantly better in a pair, 0 dropped candidates won |
| default `pytest -q` | 509 passed, 37 deselected in 78.0 s (81.7–82.4 s earlier in this follow-up; 1.1.1: 502 in 82.2 s) |
| `pytest -q -m "data or slow"` | 44 passed, 502 deselected in 835.9 s, the bench alongside (1.1.1: 43 in 690.9 s without it) |
| `pytest -q -m e2e` | 7 passed in 158.8 s (1.1.1: 165.4 s) |
| `sentinel reproduce --check` | 117 of 117 files identical, 40.6 s |
| screenshots `docs/ui/` | Polish 11 files, 1,325 kB; English 11 files, 1,192 kB (limit 3 MB per language) |
| `dist/sentinel-1.1.2.zip` | 20.0 MB, 630 files of commit e3621af, the same file list as `dist/sentinel-1.1.1.zip`; byte-identical on a second build |

### Commands for the owner
```bash
# The demo is not running at the moment (scripts/run_demo.sh status); started, it shows 1.1.2.
# A server already running elsewhere keeps the version it started with: restart it.
scripts/run_demo.sh start

# The release (built, not tagged): dist/sentinel-1.1.2.zip; prints the tag command
uv run sentinel release --version 1.1.2
# git tag -a v1.1.2 -m "Sentinel 1.1.2" <commit> && git push origin v1.1.2

# Docker (not installed on this server); docs/deploy.md uses the 1.1.2 tag
docker build -t sentinel:1.1.2 .
```

### Open issues / next steps
- Spec questions 1–5 above and 1–2 here.
- Whether the shorter explanation is enough is for the usability test with people, which has not run.
- The other open issues above stand; this follow-up does not change a simulator run's cost.
