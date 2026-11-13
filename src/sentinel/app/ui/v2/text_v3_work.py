"""The texts of v3's Raporty and Finanse and of Mapa granic's survey view (WP20;
docs/design/v3-spec.md, sections 7, 8 and 3), merged into the v2 catalogue (key -> (English,
Polish)). The labels the spec quotes are exact."""

from collections.abc import Mapping

CATALOGUE_V3_WORK: Mapping[str, tuple[str, str]] = {
    # ---- navigation (section 1)
    "v2.nav.reports": ("Reports", "Raporty"),
    "v2.nav.finance": ("Finance", "Finanse"),
    "v2.perm.role.edit": ("editing a text", "redakcja tekstu"),
    # ---- Raporty (section 7)
    "v2.rep.title": ("Reports", "Raporty"),
    "v2.rep.lead": (
        "Write or dictate a report and AI edits it for the people who will read it. You see "
        "every change and decide on each; code checks that numbers, dates and names survive.",
        "Napisz lub podyktuj raport, a AI zredaguje go dla odbiorców. Widzisz każdą zmianę i o "
        "każdej decydujesz; kod sprawdza, czy liczby, daty i nazwy przetrwały.",
    ),
    "v2.rep.new": ("New report", "Nowy raport"),
    "v2.rep.list": ("Saved reports", "Zapisane raporty"),
    "v2.rep.none": (
        "No saved reports yet. A report is kept only when you save it.",
        "Nie ma jeszcze zapisanych raportów. Raport zostaje tylko wtedy, gdy go zapiszesz.",
    ),
    "v2.rep.col.title": ("Report", "Raport"),
    "v2.rep.col.date": ("Date", "Data"),
    "v2.rep.col.audiences": ("Versions", "Wersje"),
    "v2.rep.col.saved": ("Saved", "Zapisano"),
    "v2.rep.untitled": ("Untitled report", "Raport bez tytułu"),
    "v2.rep.form.title": ("Title", "Tytuł"),
    "v2.rep.form.date": ("Date of the report", "Data raportu"),
    "v2.rep.form.text": ("Your text", "Twój tekst"),
    "v2.rep.form.text_hint": (
        "Paste or dictate the report, at most 20 000 characters.",
        "Wklej lub podyktuj raport, najwyżej 20 000 znaków.",
    ),
    "v2.rep.form.audiences": ("Audiences", "Odbiorcy"),
    "v2.rep.form.audiences_hint": (
        "For each audience AI writes a version that you review change by change.",
        "Dla każdego odbiorcy AI przygotuje wersję, którą przejrzysz zmiana po zmianie.",
    ),
    "v2.rep.form.submit": ("Edit", "Redaguj"),
    "v2.rep.aud.edit": ("Editing only", "Tylko redakcja"),
    "v2.rep.aud.board": ("Board", "Zarząd"),
    "v2.rep.aud.finance": ("Finance", "Finanse"),
    "v2.rep.aud.team": ("Team", "Zespół"),
    "v2.rep.aud_hint.edit": (
        "repetitions and clarity, nothing added",
        "powtórzenia i jasność, nic nie dodaje",
    ),
    "v2.rep.aud_hint.board": (
        "decisions, risks and money first, at most one page",
        "decyzje, ryzyka i pieniądze na początku, najwyżej strona",
    ),
    "v2.rep.aud_hint.finance": (
        "budget, costs and deviations first",
        "budżet, koszty i odchylenia na początku",
    ),
    "v2.rep.aud_hint.team": (
        "tasks, dates and who does what",
        "zadania, terminy i kto co robi",
    ),
    "v2.rep.privacy": (
        "Your text goes to the AI provider chosen in Settings. Sentinel keeps it only if you "
        "save the report.",
        "Tekst trafia do dostawcy AI wybranego w Ustawieniach. Sentinel zachowa go tylko "
        "wtedy, gdy zapiszesz raport.",
    ),
    "v2.rep.no_ai": (
        "Editing needs AI. Turn it on in Settings.",
        "Redakcja wymaga AI. Włącz je w Ustawieniach.",
    ),
    "v2.rep.working": ("AI is editing the report…", "AI redaguje raport…"),
    "v2.rep.working_for": ("Now: {audience}", "Teraz: {audience}"),
    "v2.rep.memory": (
        "Not saved yet: this draft is kept only until the server restarts.",
        "Jeszcze nie zapisano: ten szkic przetrwa tylko do ponownego uruchomienia serwera.",
    ),
    "v2.rep.versions": ("Versions", "Wersje"),
    "v2.rep.version_of": ("Version: {audience}", "Wersja: {audience}"),
    "v2.rep.tracked": ("Tracked changes", "Śledzenie zmian"),
    "v2.rep.tracked_hint": (
        "Deleted text is red and struck through, added text green and underlined. Code "
        "compares your text with AI's version word by word; AI does not describe its changes.",
        "Usunięty tekst jest czerwony i przekreślony, dodany zielony i podkreślony. Kod "
        "porównuje Twój tekst z wersją AI słowo po słowie; AI nie opisuje swoich zmian.",
    ),
    "v2.rep.count.one": ("{accepted} of {n} change accepted", "przyjęte: {accepted} z {n} zmiany"),
    "v2.rep.count.few": (
        "{accepted} of {n} changes accepted",
        "przyjęte: {accepted} z {n} zmian",
    ),
    "v2.rep.count.many": (
        "{accepted} of {n} changes accepted",
        "przyjęte: {accepted} z {n} zmian",
    ),
    "v2.rep.accept_all": ("Accept all", "Przyjmij wszystkie"),
    "v2.rep.reject_all": ("Reject all", "Odrzuć wszystkie"),
    "v2.rep.accept": ("Accept change {n}", "Przyjmij zmianę {n}"),
    "v2.rep.reject": ("Reject change {n}", "Odrzuć zmianę {n}"),
    "v2.rep.change": ("Change {n}", "Zmiana {n}"),
    "v2.rep.state.accepted": ("accepted", "przyjęta"),
    "v2.rep.state.rejected": ("rejected", "odrzucona"),
    "v2.rep.no_changes": ("AI changed nothing.", "AI niczego nie zmieniło."),
    "v2.rep.failed": (
        "AI could not edit the text for this audience. {reason}",
        "AI nie zredagowało tekstu dla tego odbiorcy. {reason}",
    ),
    "v2.rep.result": ("The version with your decisions", "Wersja z Twoimi decyzjami"),
    "v2.rep.original": ("Your text", "Twój tekst"),
    "v2.rep.guard": ("Fact guard", "Strażnik faktów"),
    "v2.rep.guard_hint": (
        "Code finds the numbers, percentages, amounts, dates, people, tasks and projects of "
        "your text and checks each of them in this version.",
        "Kod znajduje w Twoim tekście liczby, procenty, kwoty, daty, osoby, zadania i projekty "
        "i sprawdza każde z nich w tej wersji.",
    ),
    "v2.rep.guard_counts": (
        "{unchanged} unchanged · {changed} changed · {omitted} omitted",
        "bez zmian: {unchanged} · zmienione: {changed} · pominięte: {omitted}",
    ),
    "v2.rep.fact.unchanged": ("unchanged", "bez zmian"),
    "v2.rep.fact.changed": ("changed", "zmienione"),
    "v2.rep.fact.omitted": ("omitted", "pominięte"),
    "v2.rep.fact.was": ("{before} → {after}", "{before} → {after}"),
    "v2.rep.kind.number": ("number", "liczba"),
    "v2.rep.kind.percent": ("percentage", "procent"),
    "v2.rep.kind.amount": ("amount", "kwota"),
    "v2.rep.kind.date": ("date", "data"),
    "v2.rep.kind.person": ("person", "osoba"),
    "v2.rep.kind.task": ("task", "zadanie"),
    "v2.rep.kind.project": ("project", "projekt"),
    "v2.rep.times": ("×{n}", "×{n}"),
    "v2.rep.new_facts": ("New in this version", "Nowe w tej wersji"),
    "v2.rep.new_hint": (
        "Not in your text: check that AI did not make them up.",
        "Nie ma ich w Twoim tekście: sprawdź, czy AI ich nie wymyśliło.",
    ),
    "v2.rep.no_facts": (
        "No numbers, dates or names found in your text.",
        "W Twoim tekście nie ma liczb, dat ani nazw.",
    ),
    "v2.rep.words_note": (
        "Numbers written in words are not checked.",
        "Liczby zapisane słownie nie są sprawdzane.",
    ),
    "v2.rep.model_all": (
        "AI's whole version: {changed} changed, {new} new",
        "Cała wersja AI: zmienione {changed}, nowe {new}",
    ),
    "v2.rep.save": ("Save", "Zapisz"),
    "v2.rep.saved_at": ("Saved {when}", "Zapisano {when}"),
    "v2.rep.export_md": ("Export Markdown", "Eksportuj Markdown"),
    "v2.rep.export_html": ("Page for printing", "Strona do druku"),
    "v2.rep.copy": ("Copy to clipboard", "Kopiuj do schowka"),
    "v2.rep.copied": ("Copied", "Skopiowano"),
    "v2.rep.print": ("Print", "Drukuj"),
    "v2.rep.confirm.title": ("Some facts changed", "Niektóre fakty się zmieniły"),
    "v2.rep.confirm.text": (
        "{audiences}: the version has a changed or a new fact (⚠). Check it before you go on.",
        "{audiences}: wersja ma zmieniony lub nowy fakt (⚠). Sprawdź ją, zanim przejdziesz dalej.",
    ),
    "v2.rep.confirm.save": ("Save anyway", "Zapisz mimo to"),
    "v2.rep.confirm.export": ("Export anyway", "Eksportuj mimo to"),
    "v2.rep.confirm.back": ("Back to the changes", "Wróć do zmian"),
    "v2.rep.edit_again": ("Edit again", "Edytuj ponownie"),
    "v2.rep.delete": ("Delete the report", "Usuń raport"),
    "v2.rep.delete_ask": ("Delete this report?", "Usunąć ten raport?"),
    "v2.rep.deleted": ("The report was deleted.", "Raport został usunięty."),
    "v2.rep.back": ("All reports", "Wszystkie raporty"),
    "v2.rep.error.report_empty": (
        "Write or paste the report first.",
        "Najpierw wpisz lub wklej raport.",
    ),
    "v2.rep.error.report_too_long": (
        "The report is longer than 20 000 characters.",
        "Raport jest dłuższy niż 20 000 znaków.",
    ),
    "v2.rep.error.report_no_audience": (
        "Choose at least one audience.",
        "Wybierz co najmniej jednego odbiorcę.",
    ),
    "v2.rep.error.draft_not_found": (
        "This draft is no longer here (the server was restarted or many drafts came after it).",
        "Tego szkicu już nie ma (serwer uruchomiono ponownie albo powstało po nim wiele innych).",
    ),
    "v2.rep.error.report_not_found": ("There is no such report.", "Nie ma takiego raportu."),
    # ---- Finanse (section 8)
    "v2.fin.title": ("Finance", "Finanse"),
    "v2.fin.lead": (
        "Your projects' budgets, computed by code from the plan and the forecast. AI may "
        "summarise them; it has no right to approve or change a figure.",
        "Budżety Twoich projektów, policzone przez kod z planu i prognozy. AI może je "
        "streścić; nie ma prawa zatwierdzić ani zmienić żadnej liczby.",
    ),
    "v2.fin.portfolio": ("Portfolio", "Portfel projektów"),
    "v2.fin.unit": ("in work-days (person-days)", "w dniach pracy (osobodniach)"),
    "v2.fin.unit_other": (
        "in cost units (a project with its own daily costs)",
        "w jednostkach kosztu (projekt ma własne stawki dzienne)",
    ),
    "v2.fin.col.project": ("Project", "Projekt"),
    "v2.fin.col.budget": ("Budget", "Budżet"),
    "v2.fin.col.spent": ("Spent", "Wydano"),
    "v2.fin.col.forecast": ("Forecast at the end", "Prognoza na koniec"),
    "v2.fin.col.deviation": ("Deviation", "Odchylenie"),
    "v2.fin.col.state": ("State", "Stan"),
    "v2.fin.col.bar": ("Against the budget", "Wobec budżetu"),
    "v2.fin.bar": (
        "spent {spent}, forecast {forecast} of a budget of {budget}",
        "wydano {spent}, prognoza {forecast} przy budżecie {budget}",
    ),
    "v2.fin.days": ("{n} d", "{n} dni"),
    "v2.fin.share": ("{sign}{n} %", "{sign}{n} %"),
    "v2.fin.state.within": ("Within budget", "W budżecie"),
    "v2.fin.state.at_risk": ("At risk", "Zagrożony"),
    "v2.fin.state.over": ("Over budget without changes", "Przekroczenie bez zmian"),
    "v2.fin.state.overrun": ("Over budget", "Budżet przekroczony"),
    "v2.fin.chance": ("{n} in 100 within budget", "{n} na 100 w budżecie"),
    "v2.fin.total": ("All projects", "Wszystkie projekty"),
    "v2.fin.none": (
        "No project with a plan yet. Finance shows the projects that have one.",
        "Nie ma jeszcze projektu z planem. Finanse pokazują projekty, które go mają.",
    ),
    "v2.fin.legend": (
        "Bar: spent (dark), forecast at the end (light), the line is the budget.",
        "Pasek: wydano (ciemny), prognoza na koniec (jasny), kreska to budżet.",
    ),
    "v2.fin.summary": ("Summary for the board (AI)", "Streszczenie dla zarządu (AI)"),
    "v2.fin.summary_hint": (
        "AI writes it from the fact sheet that code computed; the fact guard checks every "
        "figure against the sheet.",
        "AI pisze je z arkusza faktów policzonego przez kod; strażnik faktów sprawdza każdą "
        "liczbę z arkuszem.",
    ),
    "v2.fin.summary_make": ("Write the summary", "Napisz streszczenie"),
    "v2.fin.summary_wait": ("AI is writing the summary…", "AI pisze streszczenie…"),
    "v2.fin.summary_note": (
        "Shown only, never stored; it changes no figure.",
        "Tylko do wglądu, nie jest zapisywane i nie zmienia żadnej liczby.",
    ),
    "v2.fin.summary_failed": (
        "AI could not write the summary. {reason}",
        "AI nie napisało streszczenia. {reason}",
    ),
    "v2.fin.sheet": ("Fact sheet (computed by code)", "Arkusz faktów (policzony przez kod)"),
    "v2.fin.sheet_line": (
        "{project}: budget {budget} work-days, spent {spent}, forecast at the end {forecast}, "
        "deviation {deviation} work-days ({share} % of the budget), {chance} in 100 within "
        "budget.",
        "{project}: budżet {budget} dni pracy, wydano {spent}, prognoza na koniec {forecast}, "
        "odchylenie {deviation} dni pracy ({share} % budżetu), {chance} na 100 w budżecie.",
    ),
    "v2.fin.sheet_total": (
        "All projects: budget {budget} work-days, spent {spent}, forecast at the end "
        "{forecast}, deviation {deviation} work-days.",
        "Wszystkie projekty: budżet {budget} dni pracy, wydano {spent}, prognoza na koniec "
        "{forecast}, odchylenie {deviation} dni pracy.",
    ),
    "v2.fin.move": ("Move budget", "Przesuń budżet"),
    "v2.fin.move_hint": (
        "This creates a request. Only a person approves it.",
        "To tworzy wniosek. Zatwierdza go tylko człowiek.",
    ),
    "v2.fin.move_two": (
        "Moving a budget needs two projects with a plan.",
        "Do przesunięcia budżetu potrzebne są dwa projekty z planem.",
    ),
    "v2.fin.from": ("From project", "Z projektu"),
    "v2.fin.to": ("To project", "Do projektu"),
    "v2.fin.amount": ("Work-days", "Dni pracy"),
    "v2.fin.reason": ("Reason", "Powód"),
    "v2.fin.file": ("File the request", "Złóż wniosek"),
    "v2.fin.requests": ("Requests", "Wnioski"),
    "v2.fin.no_requests": ("No requests yet.", "Nie ma jeszcze wniosków."),
    "v2.fin.no_ai_right": ("AI has no right to approve", "AI nie ma prawa zatwierdzać"),
    "v2.fin.line": (
        "{amount} work-days from {source} to {target}",
        "{amount} dni pracy: {source} → {target}",
    ),
    "v2.fin.filed": ("filed {when} by you", "złożony {when}, Ty"),
    "v2.fin.decided": ("decided {when} by you", "decyzja {when}, Ty"),
    "v2.fin.approve": ("Approve the request", "Zatwierdź wniosek"),
    "v2.fin.reject": ("Reject the request", "Odrzuć wniosek"),
    "v2.fin.confirm": (
        "Move {amount} work-days from {source} to {target}? The budgets change at once.",
        "Przesunąć {amount} dni pracy: {source} → {target}? Budżety zmienią się od razu.",
    ),
    "v2.fin.confirm_yes": ("Yes, approve", "Tak, zatwierdzam"),
    "v2.fin.cancel": ("Cancel", "Anuluj"),
    "v2.fin.status.pending": ("waiting for a person", "czeka na decyzję człowieka"),
    "v2.fin.status.approved": ("approved and applied", "zatwierdzony i zastosowany"),
    "v2.fin.status.rejected": ("rejected", "odrzucony"),
    "v2.fin.status.not_applied": ("approved, not applied", "zatwierdzony, nie zastosowany"),
    "v2.fin.why.missing": ("a project no longer exists", "projekt już nie istnieje"),
    "v2.fin.why.no_plan": ("a project has no plan", "projekt nie ma planu"),
    "v2.fin.why.simulator": (
        "a simulator project's budget belongs to its generated world",
        "budżet projektu symulatora należy do jego wygenerowanego świata",
    ),
    "v2.fin.why.below_spent": (
        "{source} has already spent {spent} work-days",
        "projekt {source} wydał już {spent} dni pracy",
    ),
    "v2.fin.error.budget_same": (
        "Choose two different projects.",
        "Wybierz dwa różne projekty.",
    ),
    "v2.fin.error.budget_amount": (
        "Give a positive number of work-days.",
        "Podaj dodatnią liczbę dni pracy.",
    ),
    "v2.fin.error.budget_unknown": ("Choose the projects again.", "Wybierz projekty jeszcze raz."),
    "v2.fin.error.budget_decided": (
        "This request has been decided already.",
        "O tym wniosku już zdecydowano.",
    ),
    "v2.event.budget_request": (
        "Budget moved by an approved request ({amount} work-days, {source} → {target}): {reason}",
        "Budżet przesunięty zatwierdzonym wnioskiem ({amount} dni pracy, {source} → {target}): "
        "{reason}",
    ),
    # ---- Mapa granic: the survey's answers (section 3)
    "v2.map.view": ("View", "Widok"),
    "v2.map.ours": ("Our map", "Nasza mapa"),
    "v2.map.survey": ("What people answered (N = {n})", "Co odpowiedzieli ludzie (N = {n})"),
    "v2.map.agree": (
        "Agreement with our map: {k} of 12 processes",
        "Zgodność z naszą mapą: {k} z 12 procesów",
    ),
    "v2.map.survey_note": (
        "Opinion poll, convenience sample, no statistical conclusions",
        "Sondaż opinii, próba wygodna, bez wniosków statystycznych",
    ),
    "v2.map.survey_table": ("Answers per process", "Odpowiedzi dla procesów"),
    "v2.map.answers": ("Answers", "Odpowiedzi"),
    "v2.map.most": ("Most often", "Najczęściej"),
    "v2.map.ours_zone": ("Our map", "Nasza mapa"),
    "v2.map.match": ("Same?", "Zgodnie?"),
    "v2.map.agrees": ("agrees", "zgodne"),
    "v2.map.differs": ("differs", "różne"),
    "v2.map.dont_know": ("don't know", "nie wiem"),
    "v2.map.share": ("{zone}: {n} of {total}", "{zone}: {n} z {total}"),
    "v2.map.weights": (
        "How much each criterion matters (1–5, mean of the answers)",
        "Waga kryteriów (1–5, średnia odpowiedzi)",
    ),
    "v2.map.tie": ("tie", "remis"),
}
