# The survey and its import (WP20)

The opinion poll of `docs/research/v3-evidence-report.md`, section D (Google Forms, Polish, about
five minutes, closing on 22 November 2026), lets Mapa granic compare Sentinel's map with what
people answered (v3 spec section 3). It is a convenience sample: the application and every text
say "Sondaż opinii, próba wygodna, bez wniosków statystycznych".

## Owner's steps

1. In Google Forms: *Odpowiedzi* → *⋮* → *Pobierz odpowiedzi (.csv)*. Put the file into
   `data/survey/` (gitignored; the export is never committed, it contains the open answers).
2. Optional: write the quotes from the open question that may be shown, one per line, into
   `data/survey/quotes.txt`, after removing anything that could identify a person or a company.
   Only this file's lines reach the summary; the open answers themselves are never read.
3. Run `uv run python scripts/import_survey.py data/survey/<export>.csv [--quotes
   data/survey/quotes.txt]`. It prints N and the agreement with the map, and writes
   `src/sentinel/evidence/data/survey.json`. It refuses an export in which it cannot find all
   twelve processes.
4. Check `survey.json` (counts only), commit it, and restart the application: Mapa granic shows
   the switch "Nasza mapa" / "Co odpowiedzieli ludzie (N = …)".

## What the summary keeps

| Part | Kept |
| --- | --- |
| Respondents | N with at least one answer in the matrix; N of those who work in an organisation (the filter question) |
| Matrix of the twelve processes | per process the count of "AI samodzielnie", "AI z człowiekiem", "Tylko człowiek", "Nie wiem" |
| Weights of the six criteria | per criterion the count of each value 1–5 and the mean |
| The two questions on Sentinel's mechanisms | the same, 1–5 |
| Demographics (role, tenure, company size, AI use) | the count of each answer; answers given fewer than three times are merged into one cell "<3" (dropped if that is under three too); no cross-tabulation |
| Open question | nothing, except the owner's approved quotes |
| Timestamps, e-mail, any other column | nothing |

The columns are recognised by words of their labels (`sentinel.evidence.survey`): the grid
rows by the process ("redakcja raportu", "prognoza dotrzymania", …) and the criteria by
"odwracalność", "łatwość sprawdzenia", "praca językowa", "wpływ na ludzi", "smak",
"wrażliwość danych". A process's most frequent answer is its zone in the survey ("nie wiem"
does not count; a tie has none), and the agreement is the number of processes where it equals
the map's zone.

`tests/test_survey.py` checks the import on a synthetic export of seven responses.
