# Decision catalogue (v3)

Every design decision a user of Sentinel sees, with the evidence for and against it from the
registry (`src/sentinel/evidence/data/registry.json`, WP18). The same table as data, with the
sentences the interface shows in Polish and English (`text_pl`, `text_en`), is
`src/sentinel/evidence/data/decisions.json` (WP19, ADR-0037); a test checks that both agree. The
interface's "Dowód" points and the presentation read the same ids.

- **Evidence**: registry ids with the stance: `+` supports (wspiera), `−` challenges (podważa),
  `~` nuances (niuansuje); `*` marks an item without a verified quote (`summary_only`). The list
  is derived from the items' `decisions` field, and a test checks that both agree.
- **Status**: `current` (in v2, or a v3 module being built) or `proposed` (not decided yet).
- **Basis**: the strongest kind among the decision's *verified* evidence, for or against it:
  `empirical` (a study with data, ours included), `normative` (a law or a standard),
  `theoretical` (theory, a review of ideas, a vision or a vendor's text). A decision whose basis
  is `theoretical` would have no verified study and no norm behind it.

| Id | Decision | Screen and feature | Evidence | Status | Basis |
| --- | --- | --- | --- | --- | --- |
| D01 | The chance of meeting the deadline is a natural frequency, "N na 100" with a 10×10 dot grid, never a percentage or a probability. | Pulpit · Szansa na termin; Start · project tiles | E36+, E37+, E49+ | current | empirical |
| D02 | The project state is shown by colour, icon and word together, with fixed thresholds (≥ 80 "Na dobrej drodze", 50–79 "Zagrożony", < 50 "Nie zdążymy bez zmian"); the thresholds are a convention, not a finding. | Pulpit · verdict; Start · project tiles | E38+ | current | normative |
| D03 | Every change to a project, even a pure re-ordering of the plan, happens only after the manager approves it. | Decyzja · Zatwierdź; "Jak Sentinel podejmuje decyzje" | E08+, E11+, E28+*, E30+*, E40+, E44−, E45+, E50+, E52~ | current | empirical |
| D04 | A proposal is never executed by silence: it shows its validity date ("ważna do") and the chance lost per day of waiting. | Decyzja · ważna do, Koszt zwłoki; Start · Decyzje do podjęcia | E40+, E52~ | current | empirical |
| D05 | The justification of a proposal is written by code from the numbers and is contrastive (the chosen option against the best alternative); the AI explanation is an optional extra. | Decyzja · Uzasadnienie, Szczegóły | E06−, E13+, E29+, E51+ | current | empirical |
| D06 | "Popraw" lets the manager change the one parameter the model can evaluate, and the effects are recomputed before approval. | Decyzja · Popraw | E04+, E41+ | current | empirical |
| D07 | Rejecting a proposal takes one of four reasons or a free text, and the reason is kept in the archive. | Decyzja · Odrzuć | E12+, E41+ | current | normative |
| D08 | Every proposal, decision, correction and reason is recorded with its time and actor ("Ty" or "Sentinel"). | Dziennik; project tab Decyzje | E12+, E26+ | current | normative |
| D09 | There are no per-person performance metrics; the team view shows workload only. | Plan · Zespół | E18+, E20+, E21+*, E22+* | current | normative |
| D10 | There is no question about how often a person is absent: one team-wide default from public Polish absence statistics, and absences are stored as availability only. | Nowy projekt · Zespół; Raport | E32+ | current | normative |
| D11 | Speech is transcribed into a draft whose recognised items appear as "Do potwierdzenia" cards, unchecked by default. | Raport · 🎤 and the cards | E03+, E39+, E47~ | current | empirical |
| D12 | The language model is local (Ollama) or in the cloud (Groq, OpenRouter) by the user's choice, with no tools in either case; caches of real messages keep no prompts. | Ustawienia · Model AI | E32+, E42+ | current | normative |
| D13 | Every number the manager sees (chance, finish date, budget, effect of a decision) comes from the schedule code and the Monte Carlo simulation, never from the language model. | Pulpit; Raport · Wpływ na projekt; Decyzja · Skutek | E14+, E15+, E48+, E49+, E50+ | current | empirical |
| D14 | Raporty: AI edits a report a person wrote in tracked-changes mode, and each change is accepted or rejected on its own. | Raporty · Śledzenie zmian (v3) | E01+, E04+, E05~, E43−, E53+ | current | empirical |
| D15 | Raporty: a fact guard in code checks that numbers, dates and names survive the edit and marks every one that changed. | Raporty · Strażnik faktów (v3) | E03+, E14+, E15+, E53+ | current | empirical |
| D16 | Raporty: versions of a report for different audiences are tracked-changes edits of the person's text, each reviewed like the first. | Raporty · Wersje dla odbiorców (v3) | E01+, E02~, E05~, E43−, E54~ | current | empirical |
| D17 | Finanse: AI summarises the budget and its deviations from numbers computed by code and has no right to approve or change a figure. | Finanse · Podsumowanie (v3) | E02~, E14+, E15+, E16~*, E17+ | current | empirical |
| D18 | Ludzie: features deliberately absent, each named with its reason: performance scores, a ranking of people for substitution, mood or emotion analysis, reasons for absence. | Ludzie · Czego tu celowo nie ma (v3) | E18+, E19+, E20+, E22+*, E32+, E46~ | current | normative |
| D19 | Uprawnienia AI: the language model has no tools and no permissions; it returns JSON validated against a schema, which code compiles and a person approves. | Uprawnienia AI (v3) | E09−, E23+, E24+, E25~, E33+* | current | normative |
| D20 | Mapa granic: twelve company processes are placed in three zones by six criteria instead of the single criterion "AI only where it saves time". | Mapa granic (v3) | E02~, E08+, E17+, E26+, E27~, E28+*, E31~, E44−, E45+ | current | empirical |
| D21 | Projekty: a "Twoja ocena" step asks for the manager's own estimate before Sentinel's recommendation is shown (cognitive forcing). | Projekty · Decyzja (v3) | E06−, E07+, E11+, E29+, E30+* | current | empirical |
| D22 | A "Dowód" point at every feature opens a short verified quote with its stance, a summary of the study and one sentence on what follows for Sentinel. | every v3 module | E06−, E34~, E35+ | current | empirical |
| D23 | Check-in messages are turned into progress data by the language model and count only after a person confirms them. | Raport · Do potwierdzenia | E47~, E51+ | current | empirical |
| D24 | The language model never chooses the action: candidate actions are evaluated by simulation and the best is proposed to the manager. | Decyzja · Wszystkie rozważone możliwości | E09−, E10~, E51+ | current | empirical |

## Notes

- No decision rests on theory alone. Eight rest on laws and standards rather than on studies:
  D02 (states; its thresholds, 80 and 50 in 100, are a convention), D07 (rejection reasons),
  D08 (archive), D09, D10 and D18 (what Sentinel deliberately does not do; the field study E22
  would make D09 and D18 empirical once its quote is verified), D12 (model choice) and D19 (no
  tools). D22 ("Dowód") is empirical only through evidence against it (E06).
- Evidence against a decision is kept on purpose: E06 (explanations raise acceptance regardless
  of correctness) challenges D05 and D22, E43 (co-writing shifts opinions) challenges D14 and
  D16, E44 (human–AI teams are on average worse than the better of the two) challenges D03 and
  D20, and our own E52 (waiting for approval costs on-time finishes in simulation) nuances D03.
- Our own RQ6 (WP20, one run, two items): E53 supports D14 and D15 (the models rarely change a
  fact, and their own lists of changes miss real changes and name ones that did not happen, so
  code computes the changes and the guard checks the facts); E54 nuances D16 (the cloud model
  added a fact in some versions, and the shorter versions leave out more facts).
- D21 is current since WP19: E07 shows that cognitive forcing reduces over-reliance but is rated
  worst by its users, so the step can be skipped ("Pokaż od razu") and switched off in the
  project settings ("Najpierw moja ocena", on by default); a usability test is still open.
