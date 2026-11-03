# The remote usability test: the owner's steps

Two or three testers do the [protocol](protocol-pl.md)'s five tasks on the public demo, on their
own computer, unmoderated. Each gets a written instruction in Polish, the spreadsheet
[projekt-testowy.csv](projekt-testowy.csv) and the team list of [zespol-testowy.txt](zespol-testowy.txt),
and sends back an answer card: the clock time at the start and end of each task, the answers to
tasks 2, 4 and 5, the ease of each task (1–5) and the ten SUS answers. The app records the rest;
`scripts/usability_logs.py` turns it into one log per tester. The story stays the protocol's:
project from Mon 2 Nov 2026 to Fri 4 Dec 2026, "today" Wed 4 Nov 2026 (the report of task 3 is
dated 4 Nov whatever the real date is).

## Before the test

1. Run the demo on 1.4.1 or later (the request log came with it; ADR-0030), from the repository:
   ```bash
   git pull
   scripts/run_demo.sh stop && scripts/run_demo.sh start
   scripts/run_demo.sh check && scripts/run_demo.sh funnel && scripts/run_demo.sh status
   ```
   `https://<machine>.<tailnet>.ts.net/api/health` answers `"version":"1.4.1"`;
   `configs/app_demo.toml` has `request_log = true`; the simulator's data are fetched
   (`docs/deploy.md`, troubleshooting).
2. A dry run as tester `P0`: the five tasks in a private window, then
   `uv run python scripts/usability_logs.py --data-dir ~/.local/share/sentinel-demo --code P0`
   and read `docs/usability/logs/P0.md` (delete it afterwards).
3. The instruction for each tester, besides the protocol's five task cards, says:
   - the link, to be opened in a **private window** (a fresh sandbox), in **one tab**, on a
     computer with a window at least 1280 px wide; the whole test in one sitting;
   - to name the project with their code, e.g. **"P1 Aplikacja rezerwacji wizyt"** (P2, P3 for
     the others; the log export finds the project by it);
   - to write the clock time (HH:MM) at the start and end of every task on the answer card;
   - that the story's "today" is Wednesday 4 November while the app shows the real date as
     today (the chart's "Dziś" line, "Raport: 8 dni temu" on the start page): the status report
     is dated 4 November all the same;
   - that the data are fictional, the demo deletes its sandbox 24 hours after the first visit,
     and it notes which pages were opened, when, and refused forms (no address, no form
     content).
4. Give the testers different time slots if you can: the demo has two job workers, and a
   simulation to the end takes about a minute of one, so two testers at task 5 together wait.

## After each tester (within 24 hours of their start)

The demo deletes a sandbox 24 hours after its first request, with its log. Export it first:

```bash
uv run python scripts/usability_logs.py --data-dir ~/.local/share/sentinel-demo --code P1
# Wrote .../docs/usability/logs/P1.md
```

- The export reads the database read-only; the demo keeps running. It finds every sandbox with a
  project whose name starts with the code (any case, "P1" but not "P10"). A tester who opened
  the demo twice has two sandboxes, each a section; use the one with the tasks.
- "No demo sandbox holds a project …": ask the tester for the name they typed and use its first
  word as the code (e.g. `--code Aplikacja` if they left the code out), then rename the file.
- The log holds no address, cookie, key or id; free text only as typed into the project (the
  names of the project, people and tasks, fictional by the instruction) and absences only as
  dates. Read it before committing it. Keep the answer cards outside git: they may carry the
  tester's name or e-mail; the results use the codes only.

What a log has: per sandbox, the **durations** of tasks 1, 3, 4 and 5 (each from the end of the
one before; task 1 from the sandbox's first request; task 3 includes task 2, which leaves no
trace) with the **page requests** and **refused forms** (an error or a question to confirm)
between them; and the **timeline** of the pages opened, the forms sent, the project's creation
and setup, the plan with the forecast the overview showed, each status report with its content,
the recommendations with their chance before and after, the decisions, the simulations to their
end, and failed jobs.

## Filling the results template

Copy [results-template.md](results-template.md) to `docs/usability/results-<yyyy-mm-dd>.md`.

| Template field | From |
| --- | --- |
| Dane testu | version 1.4.1; moderator: none (remote, unmoderated); deviations: no thinking aloud, no observation, times from the cards and the logs |
| Wynik (S / C / N) | the card's answers against the protocol's success criteria (section 5), checked in the log: task 1 "Plan made" with 5 people and 7 tasks; task 3 the status report's content; task 4 the decision row; task 5 "Simulation finished" against the tester's answer |
| Czas [s] | the log's durations for tasks 1, 4 and 5; task 3 minus task 2's time from the card (start and end clock times); a card time that differs from the log by more than a minute goes in the notes |
| Pomoc | 0 (nobody helps in an unmoderated test) |
| Błędy | the log's refused forms of the task, plus wrong turns in its timeline (e.g. the showcase project opened instead of the tester's own) |
| Uwagi i cytaty | the card's comments and its ease (1–5) for the task |
| Skrypt: kliknięcia / pola / s | [baseline-timing.json](baseline-timing.json): the same tasks by a script on 1.4.1 in demo mode |
| SUS | the script below |
| Znalezione problemy | the timelines (refused forms, long gaps, pages opened again and again) and the cards' comments, with the protocol's severity scale |

SUS scores (Brooke 1996), one card on the command line or all cards in a file, one per line:

```bash
uv run python scripts/sus_score.py P1 4 2 4 1 5 2 4 2 4 1
# | P1 | 4 | 2 | 4 | 1 | 5 | 2 | 4 | 2 | 4 | 1 | 82,5 |
uv run python scripts/sus_score.py --file sus.txt    # lines such as "P2: 3 3 4 2 4 2 3 2 4 2"
```

The rows paste into the template's SUS table; with several cards the last row is the mean with
the minimum and maximum.

## Where things land

| What | Where | In git |
| --- | --- | --- |
| A tester's log | `docs/usability/logs/<code>.md` | yes, after reading it |
| The results | `docs/usability/results-<yyyy-mm-dd>.md` | yes |
| Answer cards (e-mails, files) | outside the repository | no; delete them with the course's other raw data |
| The demo's sandboxes and request log | `~/.local/share/sentinel-demo/sentinel.db` | no; deleted after 24 hours |

After the last tester, set `request_log = false` in `configs/app_demo.toml` and restart the demo.
