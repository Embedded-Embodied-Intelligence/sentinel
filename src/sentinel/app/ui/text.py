"""The message catalogue of the pages in English and Polish (WP9b; spec section 11.7) and the
formats people read: dates as "Mon 14 Mar", whole percentages, numbers with separators.

Every string of the pages comes from `CATALOGUE` (key -> (English, Polish)) or from the
application's messages (`app/messages.py`); a test checks that both languages have every key
with the same placeholders and that no page shows an internal term. A missing key renders as
"⟦key⟧", which the test finds.
"""

import math
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta

from sentinel.app.errors import AppError
from sentinel.app.messages import MONTHS, NBSP, WEEKDAYS, date_text, render
from sentinel.app.models import Language
from sentinel.app.planning import half_up
from sentinel.app.views import issue_views

Day = date  # the type, for the methods of `Texts` (one of them is called `date`)
MINUS = "\u2212"

# key -> (English, Polish); plural keys end in .one, .few and .many (English uses "many" for
# every number but 1).
CATALOGUE: Mapping[str, tuple[str, str]] = {
    # ---- frame
    "nav.skip": ("Skip to content", "Przejdź do treści"),
    "nav.label": ("Main menu", "Menu główne"),
    "nav.projects": ("Projects", "Projekty"),
    "nav.simulator": ("Simulator", "Symulator"),
    "nav.how": ("How it works", "Jak to działa"),
    "nav.settings": ("Settings", "Ustawienia"),
    "nav.language": ("Language", "Język"),
    "nav.menu": ("Menu", "Menu"),
    "nav.your_projects": ("Your projects", "Twoje projekty"),
    "nav.status.good": ("On track", "Na dobrej drodze"),
    "nav.status.warn": ("Needs attention", "Wymaga uwagi"),
    "nav.status.bad": ("Deadline at risk", "Termin zagrożony"),
    "nav.status.decision": ("Waiting for your decision", "Czeka na Twoją decyzję"),
    "nav.status.neutral": ("Status not known yet", "Stan jeszcze nieznany"),
    "toast.close": ("Close", "Zamknij"),
    "toast.see_history": ("See in the history", "Zobacz w historii"),
    "demo.note.one": (
        "Demo: your projects are visible only to you and are deleted {n} hour after your first "
        "visit.",
        "Wersja demonstracyjna: Twoje projekty widzisz tylko Ty; usuwamy je {n} godzinę po "
        "Twojej pierwszej wizycie.",
    ),
    "demo.note.few": (
        "Demo: your projects are visible only to you and are deleted {n} hours after your first "
        "visit.",
        "Wersja demonstracyjna: Twoje projekty widzisz tylko Ty; usuwamy je {n} godziny po "
        "Twojej pierwszej wizycie.",
    ),
    "demo.note.many": (
        "Demo: your projects are visible only to you and are deleted {n} hours after your first "
        "visit.",
        "Wersja demonstracyjna: Twoje projekty widzisz tylko Ty; usuwamy je {n} godzin po "
        "Twojej pierwszej wizycie.",
    ),
    "footer.version": ("version {version}", "wersja {version}"),
    "error.title": ("Something went wrong", "Coś poszło nie tak"),
    "error.reference": (
        "Reference: {reference}. Quote it if you report the problem.",
        "Numer zgłoszenia: {reference}. Podaj go, jeśli zgłaszasz problem.",
    ),
    "error.home": ("Back to the projects", "Wróć do projektów"),
    "common.cancel": ("Cancel", "Anuluj"),
    "common.retry": ("Try again", "Spróbuj ponownie"),
    "common.optional": ("(optional)", "(opcjonalnie)"),
    "flash.checkin_saved": (
        "Check-in saved. Calculating the new forecast…",
        "Raport zapisany. Liczę nową prognozę…",
    ),
    "flash.checkin_chance": (
        "Check-in saved. Chance: {before} → {after}.",
        "Raport zapisany. Szansa: {before} → {after}.",
    ),
    "flash.approved_chance": (
        "Approved: the plan has been updated. Chance now {after}.",
        "Zatwierdzone. Plan zaktualizowany. Szansa teraz {after}.",
    ),
    "flash.approved": (
        "Approved: the plan has been updated.",
        "Zatwierdzone. Plan zaktualizowany.",
    ),
    "flash.rejected": (
        "Rejected. The plan stays as it was.",
        "Odrzucone. Plan pozostaje bez zmian.",
    ),
    "flash.later": (
        "Postponed. We will come back to it at the next check-in.",
        "Propozycja odłożona. Wrócimy do niej przy następnym raporcie.",
    ),
    "flash.undone": ("The automatic change was undone.", "Automatyczna zmiana została cofnięta."),
    "flash.deleted": ("The project was deleted.", "Projekt został usunięty."),
    "flash.settings_saved": ("Settings saved.", "Ustawienia zapisane."),
    "flash.plan_ready": ("Project created.", "Projekt utworzony."),
    "flash.discarded": (
        "The action is no longer possible; Sentinel is preparing a new recommendation.",
        "To działanie nie jest już możliwe; Sentinel przygotowuje nową rekomendację.",
    ),
    "flash.no_change": ("No change is needed.", "Zmiana nie jest potrzebna."),
    "flash.imported": (
        "The tasks were imported — please check them below.",
        "Zadania zostały zaimportowane — sprawdź je poniżej.",
    ),
    "job.plan": (
        "Calculating the chance of meeting the deadline… usually a few seconds.",
        "Liczę szansę na dotrzymanie terminu… zwykle kilka sekund.",
    ),
    "job.recommend": ("Sentinel is analysing the project…", "Sentinel analizuje projekt…"),
    "job.advance": ("Simulating the next days…", "Symuluję kolejne dni…"),
    "job.simulator": ("Preparing the example project…", "Przygotowuję przykładowy projekt…"),
    "job.extract": ("The AI is reading the description…", "AI czyta opis…"),
    "job.slow_ai": (
        "A local model can take a few minutes; the page will update by itself.",
        "Model lokalny może potrzebować kilku minut; strona odświeży się sama.",
    ),
    "job.message": ("The AI is reading the message…", "AI czyta wiadomość…"),
    "job.llm_test": ("Testing the connection…", "Sprawdzam połączenie…"),
    "job.explain": ("The AI is writing an explanation…", "AI pisze wyjaśnienie…"),
    # ---- start page
    "start.title": ("Your projects", "Twoje projekty"),
    "start.what": (
        "Sentinel watches the deadline and the budget. The decisions are yours.",
        "Sentinel pilnuje terminu i budżetu. Decyzje należą do Ciebie.",
    ),
    "start.new": ("New project", "Nowy projekt"),
    "start.create": ("Create a project", "Utwórz projekt"),
    "start.see_example": ("See an example", "Zobacz przykład"),
    "start.drafts": ("Drafts", "Szkice"),
    "start.examples": ("Examples", "Przykłady"),
    "start.open": ("Open", "Otwórz"),
    "start.card.describe": ("Describe the project in words", "Opisz projekt słowami"),
    "start.card.describe_text": (
        "The AI turns your description into a list of tasks, if one is connected.",
        "AI zamieni opis na listę zadań, jeśli jest podłączone.",
    ),
    "start.card.import": ("Import a spreadsheet", "Zaimportuj arkusz"),
    "start.card.import_text": (
        "Download the template, fill it in and upload it.",
        "Pobierz szablon, wypełnij go i wgraj.",
    ),
    "start.card.simulator": ("Try the simulator", "Wypróbuj symulator"),
    "start.card.simulator_text": (
        "Watch Sentinel manage an example project day by day.",
        "Zobacz, jak Sentinel prowadzi przykładowy projekt dzień po dniu.",
    ),
    "start.today": ("today", "dziś"),
    "start.yesterday": ("yesterday", "wczoraj"),
    "start.days_ago.one": ("{n} day ago", "{n} dzień temu"),
    "start.days_ago.few": ("{n} days ago", "{n} dni temu"),
    "start.days_ago.many": ("{n} days ago", "{n} dni temu"),
    "start.list": ("Projects", "Projekty"),
    "start.simulator_badge": ("Simulator", "Symulator"),
    "start.sim_days": ("Days simulated: {days}", "Zasymulowane dni: {days}"),
    "start.draft": ("Draft · step {n} of 3", "Szkic · krok {n} z 3"),
    "start.draft_hint": (
        "Add the team and the tasks, and we will work out the chance of meeting the deadline.",
        "Dodaj zespół i zadania, a policzymy szansę na termin.",
    ),
    "start.draft_hint_tasks": (
        "Add the tasks, and we will work out the chance of meeting the deadline.",
        "Dodaj zadania, a policzymy szansę na termin.",
    ),
    "start.continue": ("Finish", "Dokończ"),
    "start.deadline": ("Deadline {date}", "Termin {date}"),
    "start.no_deadline": ("No deadline set", "Bez terminu"),
    "start.finished": ("Finished", "Zakończony"),
    "start.calculating": ("Calculating the chance…", "Obliczam szansę…"),
    "start.pending.one": ("{n} decision waiting", "{n} decyzja czeka"),
    "start.pending.few": ("{n} decisions waiting", "{n} decyzje czekają"),
    "start.pending.many": ("{n} decisions waiting", "{n} decyzji czeka"),
    "start.as_of": ("Check-in: {when}", "Raport: {when}"),
    "start.not_tracked": ("No check-in yet", "Jeszcze bez raportu"),
    "start.empty_title": ("Start with your first project", "Zacznij od pierwszego projektu"),
    "start.empty": (
        "Give the deadline, the team and the tasks, and Sentinel works out whether you will "
        "make it.",
        "Podaj termin, zespół i zadania — Sentinel policzy, czy zdążysz.",
    ),
    "start.chance_failed": (
        "The chance could not be calculated.",
        "Nie udało się obliczyć szansy.",
    ),
    "start.chance": ("chance of meeting the deadline", "szansa na termin"),
    "start.no_chance": (
        "Set a deadline to see the chance of meeting it.",
        "Ustaw termin, aby zobaczyć szansę na jego dotrzymanie.",
    ),
    "chance.level.good": ("On track", "Na dobrej drodze"),
    "chance.level.warn": ("Needs attention", "Wymaga uwagi"),
    "chance.level.bad": ("Deadline at risk", "Termin zagrożony"),
    "chance.level.neutral": ("Unknown", "Nieznana"),
    "trend.up.one": ("up {n} percentage point", "wzrost o {n} punkt procentowy"),
    "trend.up.few": ("up {n} percentage points", "wzrost o {n} punkty procentowe"),
    "trend.up.many": ("up {n} percentage points", "wzrost o {n} punktów procentowych"),
    "trend.down.one": ("down {n} percentage point", "spadek o {n} punkt procentowy"),
    "trend.down.few": ("down {n} percentage points", "spadek o {n} punkty procentowe"),
    "trend.down.many": ("down {n} percentage points", "spadek o {n} punktów procentowych"),
    "trend.flat": ("no change", "bez zmian"),
    "trend.points": (
        '{n} <abbr title="percentage points">pts</abbr>',
        'o {n} <abbr title="punkty procentowe">pkt proc.</abbr>',
    ),
    "trend.since_checkin": ("since the check-in of {date}", "od raportu z {date}"),
    "trend.since_plan": ("since the original plan", "od planu początkowego"),
    # ---- how it works
    "how.title": ("How it works", "Jak to działa"),
    "how.lead": (
        "Sentinel does not run the project for you. It works out whether you will make it and "
        "suggests what to change.",
        "Sentinel nie zarządza projektem za Ciebie. Liczy, czy zdążysz, i podpowiada, co zmienić.",
    ),
    "how.simulate.title": ("It simulates before it acts", "Najpierw symuluje, potem działa"),
    "how.simulate.text": (
        "Tasks take longer or shorter than planned, people are sometimes away and new work comes "
        "up. Sentinel plays the rest of your project out hundreds of times with such surprises, "
        "once for every option it has — keep the plan, move dates, change the order of tasks, "
        "bring in a substitute or a temporary person, or drop an optional task — and compares "
        "the results.",
        "Zadania trwają dłużej lub krócej, niż planowano, ludzie bywają nieobecni, pojawia się "
        "nowa praca. Sentinel rozgrywa resztę projektu setki razy z takimi niespodziankami, dla "
        "każdej możliwości osobno — zachowanie planu, przesunięcie terminów, zmiana kolejności "
        "zadań, zastępstwo, osoba tymczasowa albo rezygnacja z zadania opcjonalnego — i "
        "porównuje wyniki.",
    ),
    "how.goals.title": ("Your goals decide", "Decydują Twoje cele"),
    "how.goals.text": (
        "The deadline comes first: Sentinel aims for a chance of meeting it of at least 80 %. "
        "Then come the expected delay, the budget and a calm plan: it never changes more than "
        "it has to.",
        "Najważniejszy jest termin: Sentinel dąży do co najmniej 80 % szansy na jego "
        "dotrzymanie. Potem liczą się oczekiwane opóźnienie, budżet i spokojny plan: Sentinel "
        "nie zmienia więcej, niż musi.",
    ),
    "how.ai.title": ("What the AI does and does not do", "Co robi AI, a czego nie robi"),
    "how.ai.text": (
        "If you switch it on, an AI model can turn a project description or a message into "
        "tasks and events, and explain a recommendation in its own words; every explanation is "
        "checked against the numbers. The AI never decides: every recommendation comes from the "
        "simulations, and you approve every change that affects people, money or scope.",
        "Jeśli je włączysz, model AI może zamienić opis projektu lub wiadomość na zadania i "
        "zdarzenia oraz wyjaśnić rekomendację własnymi słowami; każde wyjaśnienie jest "
        "sprawdzane z liczbami. AI nigdy nie decyduje: każda rekomendacja pochodzi z symulacji, "
        "a każdą zmianę dotyczącą ludzi, pieniędzy lub zakresu zatwierdzasz Ty.",
    ),
    "how.privacy.title": ("Privacy", "Prywatność"),
    "how.privacy.text": (
        "Sentinel stores only when a person is away, never why: there is no field for a reason, "
        "and no AI is ever asked for one. In the demo your projects are visible only to you and "
        "are deleted after a day.",
        "Sentinel zapisuje tylko, kiedy ktoś jest nieobecny, nigdy dlaczego: nie ma pola na "
        "powód i żadne AI nie jest o niego pytane. W wersji demonstracyjnej Twoje projekty "
        "widzisz tylko Ty, a po dobie są usuwane.",
    ),
    "how.numbers.title": ("What the numbers mean", "Co oznaczają liczby"),
    "how.numbers.text": (
        "A 64 % chance of meeting the deadline means that in 64 of 100 simulated futures all work "
        "is done by the deadline. The most likely finish is the date by which half of them are "
        "done; in the bad case only one in ten finishes later. When a task gets a substitute, "
        "its estimate stays a little pessimistic until the task is marked done.",
        "64 % szansy na dotrzymanie terminu oznacza, że w 64 na 100 symulowanych scenariuszy "
        "cała praca jest gotowa w terminie. Najbardziej prawdopodobny koniec to data, do której "
        "kończy się połowa z nich; w złym scenariuszu tylko jeden na dziesięć kończy się "
        "później. Gdy zadanie dostaje zastępstwo, jego szacunek pozostaje nieco pesymistyczny, "
        "dopóki zadanie nie zostanie oznaczone jako gotowe.",
    ),
    "how.more.title": ("Learn more", "Więcej informacji"),
    "how.more.repository": (
        "The source code (open source, MIT licence)",
        "Kod źródłowy (otwarte oprogramowanie, licencja MIT)",
    ),
    "how.more.paper": (
        "The research paper behind Sentinel",
        "Artykuł naukowy, na którym opiera się Sentinel",
    ),
    "how.toc.title": ("On this page", "Na tej stronie"),
    "how.toc.steps": ("Three steps", "Trzy kroki"),
    "how.toc.chance": ("Where does the chance come from?", "Skąd bierze się szansa?"),
    "how.toc.alone": (
        "What Sentinel does alone and what it asks",
        "Co Sentinel robi sam, a o co pyta",
    ),
    "how.toc.not": ("What Sentinel does not do", "Czego Sentinel nie robi"),
    "how.toc.faq": ("Frequent questions", "Najczęstsze pytania"),
    "how.step.1.title": ("You report progress", "Zgłaszasz postęp"),
    "how.step.1.text": (
        "About once a week: what is done, who is away, what grew.",
        "Mniej więcej raz w tygodniu: co gotowe, kto nieobecny, co urosło.",
    ),
    "how.step.2.title": ("Sentinel simulates", "Sentinel symuluje"),
    "how.step.2.text": (
        "200 simulated futures from today's status, for every option.",
        "200 symulowanych scenariuszy od dzisiejszego stanu, dla każdej możliwości.",
    ),
    "how.step.3.title": ("You decide", "Ty decydujesz"),
    "how.step.3.text": (
        "Approve or reject the proposal; the plan changes only then.",
        "Zatwierdzasz albo odrzucasz propozycję; dopiero wtedy plan się zmienia.",
    ),
    "how.strip.likely": ("most likely finish", "najbardziej prawdopodobny koniec"),
    "how.strip.deadline": ("deadline", "termin"),
    "how.strip.bad": ("bad case", "zły scenariusz"),
    "how.levels.level": ("Setting", "Ustawienie"),
    "how.not.1": (
        "It does not drop a task on its own: that always waits for you.",
        "Nie rezygnuje z zadania samodzielnie: to zawsze czeka na Ciebie.",
    ),
    "how.not.2": (
        "It does not ask why someone is away and does not store it.",
        "Nie pyta, dlaczego ktoś jest nieobecny, i tego nie zapisuje.",
    ),
    "how.not.3": (
        "The AI does not decide: every recommendation comes from the simulations.",
        "AI nie podejmuje decyzji: każda rekomendacja pochodzi z symulacji.",
    ),
    # ---- app settings
    "settings.title": ("Settings", "Ustawienia"),
    "settings.ai_title": ("AI assistant", "Asystent AI"),
    "settings.save": ("Save the settings", "Zapisz ustawienia"),
    "settings.key_show": ("Show", "Pokaż"),
    "settings.key_hide": ("Hide", "Ukryj"),
    "settings.lang_title": ("Language and format", "Język i format"),
    "settings.format_preview": (
        "Dates and numbers look like this: {date} · {number} · {chance}",
        "Tak wyglądają daty i liczby: {date} · {number} · {chance}",
    ),
    "settings.about_title": ("About the application", "O aplikacji"),
    "settings.about.version": ("Version", "Wersja"),
    "settings.about.licence": ("Licence", "Licencja"),
    "settings.about.code": ("Source code", "Kod źródłowy"),
    "settings.about.repository": ("Repository", "Repozytorium"),
    "settings.about.what": (
        "Sentinel is a research prototype for project managers.",
        "Sentinel to prototyp badawczy dla kierowników projektów.",
    ),
    "settings.lead": (
        "Without AI Sentinel works as usual; only reading texts in your own words and AI "
        "explanations are off.",
        "Bez AI Sentinel działa normalnie; wyłączone są tylko wiadomości pisane własnymi "
        "słowami i wyjaśnienia AI.",
    ),
    "settings.advice": (
        "A cloud model (gpt-oss-120b with Groq or OpenRouter) reads messages and writes "
        "explanations more accurately than the local one. For messages about real people's "
        "absences, use the local model or a provider that does not retain data.",
        "Model w chmurze (gpt-oss-120b przez Groq lub OpenRouter) dokładniej niż lokalny czyta "
        "wiadomości i pisze wyjaśnienia. Do wiadomości o nieobecnościach prawdziwych osób używaj "
        "modelu lokalnego albo dostawcy, który nie przechowuje danych.",
    ),
    "settings.demo": (
        "In the demo the settings are fixed by the owner of the server.",
        "W wersji demonstracyjnej ustawienia ustala właściciel serwera.",
    ),
    "settings.provider": ("AI provider", "Dostawca AI"),
    "settings.status": ("Status", "Stan"),
    "settings.available": ("Ready to use", "Gotowy do użycia"),
    "settings.unavailable": ("Not set up", "Nie skonfigurowano"),
    "settings.provider.none": ("No AI", "Bez AI"),
    "settings.provider.none.hint": (
        "Everything works; only reading texts and AI explanations are not available.",
        "Wszystko działa; niedostępne są tylko czytanie tekstów i wyjaśnienia AI.",
    ),
    "settings.provider.ollama": ("Local model (Ollama)", "Model lokalny (Ollama)"),
    "settings.provider.ollama.hint": (
        "Runs on your own computer; nothing leaves it.",
        "Działa na Twoim komputerze; nic go nie opuszcza.",
    ),
    "settings.provider.groq": ("Groq (cloud)", "Groq (chmura)"),
    "settings.provider.groq.hint": (
        "Fast cloud models; needs an API key.",
        "Szybkie modele w chmurze; wymaga klucza API.",
    ),
    "settings.provider.openrouter": ("OpenRouter (cloud)", "OpenRouter (chmura)"),
    "settings.provider.openrouter.hint": (
        "Many cloud models behind one API key.",
        "Wiele modeli w chmurze za jednym kluczem API.",
    ),
    "settings.model": ("Model", "Model"),
    "settings.model_hint": (
        "Leave empty for the recommended model.",
        "Pozostaw puste, aby użyć zalecanego modelu.",
    ),
    "settings.host": ("Address of the local model server", "Adres lokalnego serwera modelu"),
    "settings.host_hint": (
        "Only for a local model; empty means this computer.",
        "Tylko dla modelu lokalnego; puste oznacza ten komputer.",
    ),
    "settings.key": ("API key", "Klucz API"),
    "settings.key_hint": (
        "Stored only on this server and never shown again.",
        "Przechowywany tylko na tym serwerze i nigdy więcej nie wyświetlany.",
    ),
    "settings.key_saved": (
        "A key is saved. Type a new one to replace it.",
        "Klucz jest zapisany. Wpisz nowy, aby go zastąpić.",
    ),
    "settings.forget_key": ("Remove the saved key", "Usuń zapisany klucz"),
    "settings.test": ("Test the connection", "Sprawdź połączenie"),
    "settings.test_ok": (
        "The model {model} answered. The connection works.",
        "Model {model} odpowiedział. Połączenie działa.",
    ),
    "report.open": ("Open", "Otwórz"),
    "report.title": ("Project report", "Raport projektu"),
    "report.made": ("prepared {date}", "przygotowano {date}"),
    "report.file": ("report.html", "raport.html"),
    # ---- new-project wizard
    "setup.title": ("New project", "Nowy projekt"),
    "setup.exit": ("Save and exit", "Zapisz i wyjdź"),
    "setup.next_to": ("Next: {step}", "Dalej: {step}"),
    "setup.more": (
        "More settings (how sure the estimates are, absences)",
        "Więcej ustawień (pewność szacunków, nieobecności)",
    ),
    "setup.name_example": (
        "for example Online shop relaunch",
        "np. Nowa odsłona sklepu internetowego",
    ),
    "setup.budget_unit": ("cost units (person-days)", "jednostek kosztu (osobodni)"),
    "setup.basics.question": (
        "What is the project called and when must it finish?",
        "Jak nazywa się projekt i kiedy ma się skończyć?",
    ),
    "setup.basics.helper": (
        "The deadline is the day by which everything must be ready. You can change it later.",
        "Termin to dzień, do którego wszystko ma być gotowe. Możesz go później zmienić.",
    ),
    "setup.rule.ok": (
        "The deadline is after the start ({weeks}).",
        "Termin jest po dacie startu ({weeks}).",
    ),
    "setup.rule.weeks.one": ("{n} week", "{n} tydzień"),
    "setup.rule.weeks.few": ("{n} weeks", "{n} tygodnie"),
    "setup.rule.weeks.many": ("{n} weeks", "{n} tygodni"),
    "setup.team.question": ("Who works on the project?", "Kto pracuje nad projektem?"),
    "setup.team.helper": (
        "Roles decide who can do which task. You can add names later.",
        "Role decydują o tym, kto może wykonać które zadanie. Imiona możesz dopisać później.",
    ),
    "setup.team.roles": ("Roles in the team", "Role w zespole"),
    "setup.team.less": ("One person fewer: {role}", "O jedną osobę mniej: {role}"),
    "setup.team.more": ("One person more: {role}", "O jedną osobę więcej: {role}"),
    "setup.team.count": ("People: {role}", "Liczba osób: {role}"),
    "setup.team.cost": ("Daily cost: {cost}", "Koszt dnia pracy: {cost}"),
    "setup.team.new_role": ("Role", "Rola"),
    "setup.team.new_count": ("People", "Osoby"),
    "setup.team.add_role": ("Add a role", "Dodaj rolę"),
    "setup.team.role_example": ("for example Tester", "np. Tester"),
    "setup.team.names": ("Names of people", "Imiona i nazwiska"),
    "setup.team.names_hint": (
        "Without names we call people after their role, for example “Tester 1”.",
        "Bez imion nazwiemy osoby od roli, np. „Tester 1”.",
    ),
    "setup.tasks.question": ("What tasks have to be done?", "Jakie zadania trzeba wykonać?"),
    "setup.tasks.helper": (
        "Give each task its length in working days, the people it needs and what it waits for. "
        "You can change everything until the first check-in.",
        "Podaj czas trwania zadań w dniach roboczych, potrzebne osoby i to, na co czekają. "
        "Wszystko możesz zmienić do pierwszego raportu.",
    ),
    "setup.tab.describe.text": (
        "The AI turns a description into a list of tasks.",
        "AI zamieni opis na listę zadań.",
    ),
    "setup.tab.import.text": (
        "A template to fill in, then upload it.",
        "Szablon do wypełnienia, potem wgraj plik.",
    ),
    "setup.tab.manual.text": (
        "Add the tasks one by one in a table.",
        "Dodaj zadania po kolei w tabeli.",
    ),
    "setup.tasks.people_row": ("People in task {n}", "Osoby w zadaniu {n}"),
    "setup.tasks.menu": ("More for task {n}", "Więcej: zadanie {n}"),
    "setup.review.title": ("Check before creating", "Sprawdź przed utworzeniem"),
    "setup.review.change": ("Change", "Zmień"),
    "setup.review.roles.one": ("{n} role", "{n} rola"),
    "setup.review.roles.few": ("{n} roles", "{n} role"),
    "setup.review.roles.many": ("{n} roles", "{n} ról"),
    "setup.review.people.one": ("{n} person", "{n} osoba"),
    "setup.review.people.few": ("{n} people", "{n} osoby"),
    "setup.review.people.many": ("{n} people", "{n} osób"),
    "setup.review.days.one": ("{n} working day in total", "łącznie {n} dzień roboczy"),
    "setup.review.days.few": ("{n} working days in total", "łącznie {n} dni robocze"),
    "setup.review.days.many": ("{n} working days in total", "łącznie {n} dni roboczych"),
    "setup.describe.check": (
        "Check that everything is right; you can correct it in the table.",
        "Sprawdź, czy wszystko się zgadza; poprawisz to w tabeli.",
    ),
    "setup.progress": ("Setup steps", "Kroki konfiguracji"),
    "setup.step.basics": ("Basics", "Podstawy"),
    "setup.step.team": ("Team", "Zespół"),
    "setup.step.tasks": ("Tasks", "Zadania"),
    "setup.state.done": ("completed", "ukończony"),
    "setup.state.current": ("current step", "bieżący krok"),
    "setup.state.todo": ("not started", "do zrobienia"),
    "setup.step_of": ("Step {n} of {total}", "Krok {n} z {total}"),
    "setup.name": ("Project name", "Nazwa projektu"),
    "setup.start": ("Start date", "Data rozpoczęcia"),
    "setup.deadline": ("Deadline", "Termin"),
    "setup.deadline_hint": (
        "Needed to see the chance of meeting it.",
        "Potrzebny, aby zobaczyć szansę na jego dotrzymanie.",
    ),
    "setup.budget": ("Budget", "Budżet"),
    "setup.budget_hint": (
        "Empty = we estimate it from the tasks. One cost unit is one person-day (one person "
        "working for a day).",
        "Puste = oszacujemy z zadań. Jedna jednostka kosztu to jeden osobodzień (dzień pracy "
        "jednej osoby).",
    ),
    "setup.estimation": ("How sure are the time estimates?", "Jak pewne są szacunki czasu?"),
    "setup.disruptions": (
        "How turbulent is the team? (absences, surprises)",
        "Jak burzliwy jest zespół? (nieobecności, niespodzianki)",
    ),
    "preset.estimation.confident": ("Quite sure", "Dość pewne"),
    "preset.estimation.confident.hint": (
        "Tasks rarely take more than a third longer than estimated.",
        "Zadania rzadko trwają o ponad jedną trzecią dłużej, niż oszacowano.",
    ),
    "preset.estimation.typical": ("Usual", "Typowe"),
    "preset.estimation.typical.hint": (
        "Some tasks take up to 60 % longer, a few finish early.",
        "Niektóre zadania trwają do 60 % dłużej, kilka kończy się wcześniej.",
    ),
    "preset.estimation.uncertain": ("Rough", "Zgrubne"),
    "preset.estimation.uncertain.hint": (
        "A task may take up to twice as long as estimated.",
        "Zadanie może potrwać nawet dwa razy dłużej, niż oszacowano.",
    ),
    "preset.disruptions.calm": ("Calm", "Spokojny"),
    "preset.disruptions.calm.hint": (
        "A person is away about once a year.",
        "Osoba jest nieobecna mniej więcej raz w roku.",
    ),
    "preset.disruptions.typical": ("Usual", "Typowy"),
    "preset.disruptions.typical.hint": (
        "A person is away about twice a year; now and then a task grows or a new one comes up.",
        "Osoba jest nieobecna mniej więcej dwa razy w roku; od czasu do czasu zadanie się "
        "wydłuża lub pojawia się nowe.",
    ),
    "preset.disruptions.turbulent": ("Turbulent", "Burzliwy"),
    "preset.disruptions.turbulent.hint": (
        "A person is away about five times a year.",
        "Osoba jest nieobecna mniej więcej pięć razy w roku.",
    ),
    "setup.back": ("Back", "Wstecz"),
    "setup.finish": ("Create the plan and calculate the chance", "Utwórz plan i policz szansę"),
    "setup.remove": ("Remove", "Usuń"),
    "setup.saved": ("Draft saved · {time}", "Szkic zapisany · {time}"),
    "setup.unsaved": ("Not saved yet", "Jeszcze nie zapisano"),
    "setup.issues_title": ("Please check:", "Sprawdź proszę:"),
    "setup.team.caption": ("Team", "Zespół"),
    "setup.team.name": ("Name", "Imię i nazwisko"),
    "setup.team.role": ("Role", "Rola"),
    "setup.team.name_of": ("Name of person {n}", "Imię i nazwisko osoby {n}"),
    "setup.team.role_of": ("Role of person {n}", "Rola osoby {n}"),
    "setup.team.empty": (
        "No one yet. Add a role below or paste a list.",
        "Nikogo jeszcze nie ma. Dodaj rolę poniżej albo wklej listę.",
    ),
    "setup.team.add": ("Add a person", "Dodaj osobę"),
    "setup.team.paste": ("Paste a list of people", "Wklej listę osób"),
    "setup.team.paste_label": (
        "One person per line: name, role",
        "Jedna osoba w wierszu: imię, rola",
    ),
    "setup.team.paste_hint": (
        "For example “Anna, backend developer”. A comma, semicolon or tab separates the name from "
        "the role.",
        "Na przykład „Anna, programistka backend”. Imię od roli oddziela przecinek, średnik lub "
        "tabulator.",
    ),
    "setup.team.paste_add": ("Add these people", "Dodaj te osoby"),
    "setup.tasks.ways": ("Ways to add tasks", "Sposoby dodawania zadań"),
    "setup.tab.describe": ("Describe in words", "Opisz słowami"),
    "setup.tab.import": ("Import a spreadsheet", "Zaimportuj arkusz"),
    "setup.tab.manual": ("Enter by hand", "Wpisz ręcznie"),
    "setup.describe.label": (
        "Describe the project in your own words",
        "Opisz projekt własnymi słowami",
    ),
    "setup.describe.hint": (
        "What has to be done, how long it takes, who is needed and what waits for what. The AI "
        "turns it into a task list for you to check.",
        "Co trzeba zrobić, ile to potrwa, kto jest potrzebny i co na co czeka. AI zamieni to na "
        "listę zadań do sprawdzenia.",
    ),
    "setup.describe.read": ("Read the description", "Odczytaj opis"),
    "setup.describe.no_ai": (
        "This needs an AI model, and none is set up.",
        "Do tego potrzebny jest model AI, a żaden nie jest skonfigurowany.",
    ),
    "setup.describe.found": ("Tasks found: {count}", "Znalezione zadania: {count}"),
    "setup.describe.issues": (
        "Problems left: {count}. You can correct them in the table afterwards.",
        "Pozostałe problemy: {count}. Poprawisz je potem w tabeli.",
    ),
    "setup.describe.caption": ("Tasks read from the description", "Zadania odczytane z opisu"),
    "setup.describe.people": ("People", "Osoby"),
    "setup.describe.team": ("Suggested team: {people}", "Proponowany zespół: {people}"),
    "setup.describe.use": ("Use these tasks", "Użyj tych zadań"),
    "setup.describe.outside": (
        "Roles nobody in the team has: {roles}",
        "Role, których nikt w zespole nie ma: {roles}",
    ),
    "setup.describe.outside_text": (
        "After “Use these tasks”, change the people of these tasks in the table or add the role "
        "to the team; the plan waits until then.",
        "Po „Użyj tych zadań” zmień osoby przy tych zadaniach w tabeli albo dodaj rolę do zespołu; "
        "do tego czasu plan nie powstanie.",
    ),
    "setup.tasks.role_outside": (" (nobody in the team)", " (nikt w zespole)"),
    "setup.import.step1": ("Download the template:", "Pobierz szablon:"),
    "setup.import.template": ("tasks template (CSV)", "szablon zadań (CSV)"),
    "setup.import.step2": (
        "Fill in one row per task. In the “crew:” columns use your team's roles: {roles}.",
        "Wypełnij po jednym wierszu na zadanie. W kolumnach „crew:” użyj ról zespołu: {roles}.",
    ),
    "setup.import.step3": (
        "Save it as CSV and upload it here. Problems are listed with their row numbers.",
        "Zapisz jako CSV i wgraj tutaj. Problemy zostaną wypisane z numerami wierszy.",
    ),
    "setup.import.file": ("Spreadsheet file (CSV)", "Plik arkusza (CSV)"),
    "setup.import.button": ("Import the tasks", "Importuj zadania"),
    "setup.import.failed": ("The file could not be imported:", "Nie udało się zaimportować pliku:"),
    "setup.tasks.caption": ("Tasks", "Zadania"),
    "setup.tasks.name": ("Task", "Zadanie"),
    "setup.tasks.days": ("Days", "Dni"),
    "setup.tasks.people": ("{role} (people)", "{role} (osoby)"),
    "setup.tasks.after": ("After tasks", "Po zadaniach"),
    "setup.tasks.optional": ("Optional", "Opcjonalne"),
    "setup.tasks.name_of": ("Name of task {n}", "Nazwa zadania {n}"),
    "setup.tasks.days_of": ("Working days of task {n}", "Dni robocze zadania {n}"),
    "setup.tasks.people_of": ("{role}: people in task {n}", "{role}: liczba osób w zadaniu {n}"),
    "setup.tasks.after_of": ("Task {n} comes after", "Zadanie {n} następuje po"),
    "setup.tasks.optional_of": ("Task {n} is optional", "Zadanie {n} jest opcjonalne"),
    "setup.tasks.after_hint": (
        "“After tasks”: the tasks that must finish first. An optional task can be dropped if "
        "time runs short; no task may wait for it.",
        "„Po zadaniach”: zadania, które muszą się najpierw zakończyć. Z zadania opcjonalnego "
        "można zrezygnować, gdy brakuje czasu; żadne zadanie nie może na nie czekać.",
    ),
    "setup.tasks.empty": (
        "No tasks yet. Add them here, import a spreadsheet or describe the project.",
        "Nie ma jeszcze zadań. Dodaj je tutaj, zaimportuj arkusz albo opisz projekt.",
    ),
    "setup.tasks.add": ("Add a task", "Dodaj zadanie"),
    "form.fix_below": ("Please correct the fields marked below.", "Popraw pola oznaczone poniżej."),
    "form.name_required": ("Give the project a name.", "Podaj nazwę projektu."),
    "form.start_required": ("Give the start date.", "Podaj datę rozpoczęcia."),
    "form.date_invalid": ("This is not a valid date.", "To nie jest poprawna data."),
    "form.deadline_before_start": (
        "The deadline cannot be before the start date.",
        "Termin nie może wypadać przed datą rozpoczęcia.",
    ),
    "form.budget_positive": (
        "The budget must be a number above 0, or empty.",
        "Budżet musi być liczbą większą od 0 albo pozostać pusty.",
    ),
    "form.days_number": (
        "“{task}”: the days must be a whole number.",
        "„{task}”: liczba dni musi być liczbą całkowitą.",
    ),
    "form.people_number": (
        "“{task}”: the number of people must be a whole number, 0 or more.",
        "„{task}”: liczba osób musi być liczbą całkowitą, co najmniej 0.",
    ),
    "form.after_numbers": (
        "“{task}”: “after tasks” must list the numbers of other rows, e.g. “1, 3”.",
        "„{task}”: w polu „po zadaniach” wpisz numery innych wierszy, np. „1, 3”.",
    ),
    "form.team_empty": ("Add at least one person.", "Dodaj co najmniej jedną osobę."),
    "form.person_name_missing": (
        "Row {row}: the person needs a name.",
        "Wiersz {row}: osoba musi mieć imię i nazwisko.",
    ),
    "form.task_name_missing": (
        "Row {row}: the task needs a name.",
        "Wiersz {row}: zadanie musi mieć nazwę.",
    ),
    "form.checkin_date": ("Give the date of the check-in.", "Podaj datę raportu."),
    "form.percent_range": (
        "The share done must be from 0 to 99 %; a finished task is “done”.",
        "Wykonana część musi wynosić od 0 do 99 %; ukończone zadanie oznacz jako „gotowe”.",
    ),
    "form.finish_required": (
        "Give the date the task was finished.",
        "Podaj datę zakończenia zadania.",
    ),
    "form.away_from": ("Give the first day of the absence.", "Podaj pierwszy dzień nieobecności."),
    "form.extra_days": (
        "Give the extra working days as a number above 0.",
        "Podaj dodatkowe dni robocze jako liczbę większą od 0.",
    ),
    "form.task_name": ("The new task needs a name.", "Nowe zadanie musi mieć nazwę."),
    "form.autonomy": ("Choose one of the four options.", "Wybierz jedną z czterech opcji."),
    "form.cost": (
        "The daily cost of {role} must be a number, 0 or more.",
        "Dzienny koszt roli {role} musi być liczbą nie mniejszą niż 0.",
    ),
    # ---- a project
    "project.as_of": ("Status at the end of {date}", "Stan na koniec dnia {date}"),
    "project.not_started": (
        "Starts on {date}; no check-in yet",
        "Start {date}; jeszcze bez raportu statusu",
    ),
    "project.sections": ("Project sections", "Sekcje projektu"),
    "project.tab.overview": ("Overview", "Przegląd"),
    "project.tab.checkin": ("Check-in", "Raport statusu"),
    "project.tab.history": ("History", "Historia"),
    "project.tab.settings": ("Settings", "Ustawienia"),
    "overview.chance_title": ("Chance of meeting the deadline", "Szansa na dotrzymanie terminu"),
    "overview.finished": (
        "All tasks are done — the project is finished.",
        "Wszystkie zadania są gotowe — projekt jest zakończony.",
    ),
    "overview.calculating": (
        "Calculating the forecast… usually a few seconds.",
        "Liczę prognozę… zwykle kilka sekund.",
    ),
    "overview.ask": ("Ask Sentinel", "Zapytaj Sentinela"),
    "overview.checkin": ("New check-in", "Nowy raport statusu"),
    "overview.pending_title": ("Waiting for your decision", "Czeka na Twoją decyzję"),
    "overview.nothing_pending": (
        "Nothing is waiting for your decision.",
        "Nic nie czeka na Twoją decyzję.",
    ),
    "overview.other_proposals": ("Other proposals ({n})", "Inne propozycje ({n})"),
    "overview.how": ("How do we calculate this?", "Jak liczymy?"),
    "overview.drivers_how": ("How to read this", "Jak to czytać"),
    "overview.budget": ("Budget", "Budżet"),
    "overview.spent_share": ("Spent {share}", "Wydano {share}"),
    "overview.expected_share": (
        "Expected cost: {share} of the budget",
        "Oczekiwany koszt: {share} budżetu",
    ),
    "overview.gap_before": ("{days} before the deadline", "{days} przed terminem"),
    "overview.gap_after": ("{days} after the deadline", "{days} po terminie"),
    "overview.gap_on": ("On the deadline", "W dniu terminu"),
    "overview.days.one": ("{n} working day", "{n} dzień roboczy"),
    "overview.days.few": ("{n} working days", "{n} dni robocze"),
    "overview.days.many": ("{n} working days", "{n} dni roboczych"),
    "strip.today": ("today", "dziś"),
    "strip.likely": ("most likely {date}", "najbardziej prawdopodobny koniec {date}"),
    "strip.deadline": ("deadline {date}", "termin {date}"),
    "strip.bad": ("bad case {date}", "zły scenariusz {date}"),
    "overview.auto_title": ("Applied automatically", "Zastosowane automatycznie"),
    "overview.auto_text": (
        "Sentinel applied this on {date} because your settings allow it.",
        "Sentinel zastosował to {date}, bo pozwalają na to Twoje ustawienia.",
    ),
    "overview.details": ("Details", "Szczegóły"),
    "overview.undo": ("Undo", "Cofnij"),
    "overview.threats_title": ("What threatens the deadline", "Co zagraża terminowi"),
    "overview.drivers_wait": ("Waiting for the forecast…", "Czekam na prognozę…"),
    "overview.threats_calculating": (
        "Working out which tasks threaten the deadline…",
        "Sprawdzam, które zadania zagrażają terminowi…",
    ),
    "overview.threats_failed": (
        "The list of tasks could not be calculated.",
        "Nie udało się obliczyć listy zadań.",
    ),
    "overview.away_back": (
        "{person}: away, back on {date}.",
        "{person}: nieobecność, powrót {date}.",
    ),
    "overview.away_open": (
        "{person}: away, return date not known yet.",
        "{person}: nieobecność, data powrotu jeszcze nieznana.",
    ),
    "overview.late": (
        "“{task}” was planned to start on {date} and has not started.",
        "„{task}” miało się rozpocząć {date} i jeszcze się nie rozpoczęło.",
    ),
    "overview.plan_title": ("Plan and progress", "Plan i postęp"),
    "overview.forecast_failed": (
        "The forecast could not be calculated.",
        "Nie udało się obliczyć prognozy.",
    ),
    "overview.no_forecast": ("No forecast yet.", "Brak prognozy."),
    "overview.no_deadline": (
        "No deadline is set, so there is no chance to show.",
        "Nie ustawiono terminu, więc nie ma szansy do pokazania.",
    ),
    "overview.set_deadline": ("Set a deadline", "Ustaw termin"),
    "overview.deadline": ("Deadline", "Termin"),
    "overview.likely": ("Most likely finish", "Najbardziej prawdopodobny koniec"),
    "overview.bad_case": ("Bad case (1 in 10 later)", "Zły scenariusz (1 na 10 później)"),
    "overview.expected_cost": ("Expected total cost", "Oczekiwany koszt całkowity"),
    "overview.promise.deadline": (
        "The deadline changed after the recommendation, so these figures differ from its card.",
        "Termin zmieniono po rekomendacji, więc te liczby różnią się od obiecanych na karcie.",
    ),
    "overview.promise.budget": (
        "The budget changed after the recommendation, so these figures differ from its card.",
        "Budżet zmieniono po rekomendacji, więc te liczby różnią się od obiecanych na karcie.",
    ),
    "overview.promise.settings": (
        "The settings changed after the recommendation, so these figures differ from its card.",
        "Ustawienia zmieniono po rekomendacji, więc te liczby różnią się od obiecanych na karcie.",
    ),
    "overview.promise.replanned": (
        "The plan was made again when you approved, so these figures differ from the card.",
        "Przy zatwierdzeniu plan ułożono ponownie, więc te liczby różnią się od obiecanych "
        "na karcie.",
    ),
    "overview.within_budget": (
        "Chance of staying within the budget: {p}",
        "Szansa na zmieszczenie się w budżecie: {p}",
    ),
    "overview.forecast_note": (
        "Calculated on {futures} simulated futures from today's status, if the plan stays as "
        "it is. The chance is the share of them that finish by the deadline.",
        "Policzone na {futures} symulowanych scenariuszach od dzisiejszego stanu, gdyby plan "
        "się już nie zmieniał. Szansa to odsetek scenariuszy, które kończą się przed terminem.",
    ),
    "overview.driver": (
        "Task “{task}”. The longer this task takes, the later the project usually finishes.",
        "Zadanie „{task}”. Im dłużej trwa to zadanie, tym później zwykle kończy się projekt.",
    ),
    "overview.spread": (
        "No single task decides the deadline: the risk is spread across the plan.",
        "Żadne pojedyncze zadanie nie przesądza o terminie: ryzyko rozkłada się na cały plan.",
    ),
    "overview.no_late": (
        "Nothing threatens the deadline for now: the project is late in none of the simulated "
        "futures.",
        "Na razie nic nie zagraża terminowi: w żadnym symulowanym scenariuszu projekt się nie "
        "spóźnia.",
    ),
    "overview.threats_no_deadline": (
        "Set a deadline to see what threatens it.",
        "Ustaw termin, aby zobaczyć, co mu zagraża.",
    ),
    "overview.drivers_note": (
        "For every unfinished task we compare, across {futures} simulated futures (the first "
        "{first} are those behind the chance), how long it takes, growth included, with the "
        "project's finish date. Listed are the tasks where a longer duration goes most clearly "
        "with a later finish (a rank correlation of at least 0.2), at most three, the strongest "
        "first; the bar shows that strength. A task that varies little, such as a short go-live, "
        "is rarely listed, even if it sets the finish date in most futures. A value close to 0.2 "
        "remains uncertain, so such a task can leave the list at the next check-in though nothing "
        "changed in the project.",
        "Dla każdego niezakończonego zadania porównujemy w {futures} symulowanych scenariuszach "
        "(pierwsze {first} to te, z których liczymy szansę) czas jego trwania, razem z "
        "wydłużeniami, z datą zakończenia projektu. Wymieniamy zadania, dla których dłuższy czas "
        "trwania najwyraźniej idzie w parze z późniejszym końcem (korelacja rang co najmniej 0,2), "
        "najwyżej trzy, od najsilniejszego związku; pasek pokazuje jego siłę. Zadanie o małej "
        "zmienności, np. krótkie uruchomienie produkcyjne, rzadko trafia na listę, nawet jeśli w "
        "większości scenariuszy wyznacza datę zakończenia. Wartość bliska 0,2 pozostaje niepewna, "
        "więc takie zadanie może zniknąć z listy przy następnym raporcie, choć w projekcie nic się "
        "nie zmieniło.",
    ),
    "overview.checked_title": ("Sentinel checked the new status", "Sentinel sprawdził nowy stan"),
    "overview.checked": (
        "No change is needed: the plan is still the best.",
        "Zmiana nie jest potrzebna: plan wciąż jest najlepszy.",
    ),
    "overview.checked_no_better": (
        "No option checked is clearly better than the current plan, so the plan stays.",
        "Żadna sprawdzona możliwość nie jest wyraźnie lepsza od obecnego planu, więc plan "
        "pozostaje.",
    ),
    "chart.title": ("Plan and progress of the tasks", "Plan i postęp zadań"),
    "chart.desc": (
        "{tasks} tasks: {done} done, {running} in progress, {planned} planned. Status at the "
        "end of {status}.",
        "Zadania: {tasks}; gotowe: {done}, w toku: {running}, zaplanowane: {planned}. Stan na "
        "koniec dnia {status}.",
    ),
    "chart.away": ("away from {first}, back on {back}", "nieobecność od {first}, powrót {back}"),
    "chart.away_open": (
        "away from {first}, return not known",
        "nieobecność od {first}, powrót nieznany",
    ),
    "chart.tip_removed": ("{task}: dropped", "{task}: usunięte z zakresu"),
    "chart.tip_done": ("{task}: done, {start} – {finish}", "{task}: gotowe, {start} – {finish}"),
    "chart.tip_running": (
        "{task}: in progress since {start}, {percent} % done",
        "{task}: w toku od {start}, wykonano {percent} %",
    ),
    "chart.tip_planned": (
        "{task}: planned {start} – {finish}",
        "{task}: zaplanowane {start} – {finish}",
    ),
    "chart.new": ("(new)", "(nowe)"),
    "chart.flag.today": ("Today · {date}", "Dziś · {date}"),
    "chart.flag.status": ("Status at {date}", "Stan na {date}"),
    "chart.flag.deadline": ("Deadline · {date}", "Termin · {date}"),
    "chart.flag.likely": (
        "Most likely finish · {date}",
        "Najbardziej prawdopodobny koniec · {date}",
    ),
    "chart.flag.bad": ("Bad case · {date}", "Zły scenariusz · {date}"),
    "chart.view": ("Show the plan as", "Pokaż plan jako"),
    "chart.view.chart": ("Chart", "Wykres"),
    "chart.view.table": ("Table", "Tabela"),
    "chart.legend.window": ("Forecast window", "Okno prognozy"),
    "chart.gap": (
        "Without disruptions the plan finishes on {plan}; the forecast window starts later "
        "(most likely finish {likely}) because it counts on the usual overruns and absences.",
        "Plan bez zakłóceń kończy się {plan}; okno prognozy zaczyna się później (najbardziej "
        "prawdopodobny koniec {likely}), bo uwzględnia typowe wydłużenia zadań i nieobecności.",
    ),
    "chart.legend.deadline": ("Deadline", "Termin"),
    "chart.col.people": ("People", "Osoby"),
    "chart.legend": ("Legend", "Legenda"),
    "chart.legend.original": ("Original plan", "Plan początkowy"),
    "chart.legend.done": ("Done", "Gotowe"),
    "chart.legend.running": (
        "In progress (dashed: work left)",
        "W toku (przerywana: pozostała praca)",
    ),
    "chart.legend.planned": ("Planned", "Zaplanowane"),
    "chart.legend.away": ("Someone away", "Nieobecność"),
    "chart.col.task": ("Task", "Zadanie"),
    "chart.col.state": ("State", "Stan"),
    "chart.col.dates": ("Dates", "Daty"),
    "chart.since": ("since {date}", "od {date}"),
    # ---- check-in
    "checkin.title": ("Check-in", "Raport statusu"),
    "checkin.not_saved": (
        "The check-in could not be saved. Correct the fields below.",
        "Nie udało się zapisać raportu. Popraw pola oznaczone poniżej.",
    ),
    "checkin.since": ("What has changed since {date}?", "Co się zmieniło od {date}?"),
    "checkin.since_start": ("What has changed since the start?", "Co się zmieniło od startu?"),
    "checkin.future_title": (
        "This check-in is dated {date}, more than a week from today.",
        "Ten raport ma datę {date}, ponad tydzień od dziś.",
    ),
    "checkin.future_text": (
        "Check-ins follow each other in time, so every later one would have to be dated after "
        "it, and it cannot be undone. Correct the date, or confirm it.",
        "Raporty następują po sobie w czasie, więc każdy kolejny musiałby mieć późniejszą "
        "datę, a tego nie da się cofnąć. Popraw datę albo ją potwierdź.",
    ),
    "checkin.future_confirm": ("Yes, this date is right", "Tak, ta data jest prawidłowa"),
    "checkin.help": ("How to fill in a check-in", "Jak wypełnić raport"),
    "checkin.share_hint": (
        "The share done is the part of the task's own work that is finished; mark a finished "
        "task as done.",
        "Wykonana część to ukończona część pracy nad samym zadaniem; zadanie skończone oznacz "
        "jako gotowe.",
    ),
    "checkin.add": ("Add", "Dodaj"),
    "checkin.percent": ("Percent", "Procent"),
    "checkin.was_due": ("was due to start on {date}", "miało ruszyć {date}"),
    "checkin.or_by_hand": ("or fill it in by hand:", "albo uzupełnij ręcznie:"),
    "checkin.message_placeholder": (
        "For example: Bartek is away until Monday, the API will take 2 more days.",
        "np. Bartka nie będzie do poniedziałku, a API zajmie jeszcze 2 dni dłużej.",
    ),
    "checkin.changes.zero": ("No changes", "Bez zmian"),
    "checkin.changes.one": ("{n} change", "{n} zmiana"),
    "checkin.changes.few": ("{n} changes", "{n} zmiany"),
    "checkin.changes.many": ("{n} changes", "{n} zmian"),
    "checkin.save_none": ("Save the check-in (no changes)", "Zapisz raport (bez zmian)"),
    "checkin.date": ("Status at the end of", "Stan na koniec dnia"),
    "checkin.before_start": (
        "This date is before the project starts ({date}). You can still save it.",
        "Ta data jest przed startem projektu ({date}). Raport i tak można zapisać.",
    ),
    "checkin.date_hint": (
        "Report what is true at the end of this day.",
        "Zgłoś stan na koniec tego dnia.",
    ),
    "checkin.tasks_title": ("Tasks in progress and next", "Zadania w toku i najbliższe"),
    "checkin.no_active": (
        "No task is in progress or about to start.",
        "Żadne zadanie nie jest w toku ani nie zaczyna się wkrótce.",
    ),
    "checkin.more_tasks.one": ("Show {n} more task", "Pokaż jeszcze {n} zadanie"),
    "checkin.more_tasks.few": ("Show {n} more tasks", "Pokaż jeszcze {n} zadania"),
    "checkin.more_tasks.many": ("Show {n} more tasks", "Pokaż jeszcze {n} zadań"),
    "checkin.done_share": ("{percent} % done", "wykonano {percent} %"),
    "checkin.planned": ("planned from {date}", "zaplanowane od {date}"),
    "checkin.status.not_started": ("Not started", "Nierozpoczęte"),
    "checkin.status.in_progress": ("In progress", "W toku"),
    "checkin.status.done": ("Done", "Gotowe"),
    "checkin.share": ("Share done", "Wykonana część"),
    "checkin.finished_on": ("Finished on", "Zakończone dnia"),
    "checkin.more": (
        "Start date and people (optional)",
        "Data rozpoczęcia i osoby (opcjonalnie)",
    ),
    "checkin.started_on": ("Started on", "Rozpoczęte dnia"),
    "checkin.started_hint": (
        "Leave empty to use the planned start.",
        "Pozostaw puste, aby przyjąć planowany start.",
    ),
    "checkin.who": ("Who works on it", "Kto nad nim pracuje"),
    "checkin.who_hint": (
        "Needs {crew}. Leave empty and Sentinel picks free people.",
        "Potrzeba: {crew}. Pozostaw puste, a Sentinel wybierze wolne osoby.",
    ),
    "checkin.away_title": ("Absences", "Nieobecności"),
    "checkin.away_hint": (
        "Only when, never why: there is no place for reasons.",
        "Tylko kiedy, nigdy dlaczego: nie ma tu miejsca na powody.",
    ),
    "checkin.away_add": ("an absence", "nieobecność"),
    "checkin.away.who": ("Person", "Osoba"),
    "checkin.away.choose": ("Choose a person", "Wybierz osobę"),
    "checkin.away.from": ("Away from", "Nieobecność od"),
    "checkin.away.back": ("Back on (if known)", "Powrót (jeśli wiadomo)"),
    "checkin.grow_title": ("Tasks that grew", "Zadania, które urosły"),
    "checkin.grow_hint": (
        "A task in progress needs more working days than planned.",
        "Zadanie w toku potrzebuje więcej dni roboczych, niż planowano.",
    ),
    "checkin.grow_add": ("a task that grew", "zadanie, które urosło"),
    "checkin.grow.task": ("Task", "Zadanie"),
    "checkin.grow.choose": ("Choose a task in progress", "Wybierz zadanie w toku"),
    "checkin.grow.days": ("Extra working days", "Dodatkowe dni robocze"),
    "checkin.grow_none": ("No task is in progress.", "Żadne zadanie nie jest w toku."),
    "checkin.new_title": ("New task", "Nowe zadanie"),
    "checkin.new_add": ("a new task", "nowe zadanie"),
    "checkin.new.name": ("Task name", "Nazwa zadania"),
    "checkin.new.days": ("Working days", "Dni robocze"),
    "checkin.new.after": ("Comes after", "Następuje po"),
    "checkin.new.after_none": ("Nothing (can start now)", "Niczym (może zacząć się od razu)"),
    "checkin.new.before": ("Must be done before", "Musi być gotowe przed"),
    "checkin.new.before_none": ("The end of the project", "Końcem projektu"),
    "checkin.new.optional": (
        "Optional (can be dropped)",
        "Opcjonalne (można z niego zrezygnować)",
    ),
    "checkin.message_title": ("Write in your own words", "Napisz własnymi słowami"),
    "checkin.message_label": (
        "What happened? Describe it in plain words.",
        "Co się wydarzyło? Opisz to zwykłymi słowami.",
    ),
    "checkin.message_hint": (
        "The AI turns it into absences, growing tasks and new tasks; you confirm each one before "
        "saving.",
        "AI zamieni to na nieobecności, wydłużone i nowe zadania; każde z nich potwierdzasz "
        "przed zapisaniem.",
    ),
    "checkin.message_read": ("Process the message", "Przetwórz wiadomość"),
    "checkin.message_days.one": ("about {n} more day", "ok. {n} dzień więcej"),
    "checkin.message_days.few": ("about {n} more days", "ok. {n} dni więcej"),
    "checkin.message_days.many": ("about {n} more days", "ok. {n} dni więcej"),
    "checkin.message_days_part": ("about {days} more days", "ok. {days} dnia więcej"),
    "checkin.message_nothing": (
        "The AI found nothing to report in this message.",
        "AI nie znalazło w tej wiadomości nic do zgłoszenia.",
    ),
    "checkin.message_found": ("This is how I read it:", "Tak to rozumiem:"),
    "checkin.message_issues": (
        "Some parts could not be read; check the message and add them by hand.",
        "Części nie udało się odczytać; sprawdź wiadomość i dodaj je ręcznie.",
    ),
    "checkin.message_confirm": (
        "Untick what is wrong; the ticked items are saved with the check-in.",
        "Odznacz to, co się nie zgadza; zaznaczone pozycje zapiszą się razem z raportem.",
    ),
    "checkin.save": ("Save the check-in", "Zapisz raport"),
    # ---- recommendation
    "rec.title": ("Recommendation", "Rekomendacja"),
    "rec.as_of": ("status at the end of {date}", "stan na koniec dnia {date}"),
    "rec.applies_from": ("The change applies from {date}.", "Zmiana obejmuje dni od {date}."),
    "rec.alt_noop": ("No change", "Bez zmian"),
    "rec.can_wait": ("can wait", "może poczekać"),
    "rec.what_changes": ("What changes", "Co się zmieni"),
    "rec.decided.approved": ("Approved · {date}", "Zatwierdzone · {date}"),
    "rec.decided.rejected": (
        "Rejected · {date}. The plan stayed as it was.",
        "Odrzucone · {date}. Plan pozostał bez zmian.",
    ),
    "rec.compare_all": ("Compare all the options ({n})", "Porównaj wszystkie możliwości ({n})"),
    "rec.how": ("How we calculated this", "Jak to policzyliśmy"),
    "rec.more": ("More", "Więcej"),
    "rec.baseline_note": ("reference point", "punkt odniesienia"),
    "rec.points": ("{sign}{n} pts", "{sign}{n} pkt"),
    "rec.approve.subst": ("Approve the substitute", "Zatwierdź zastępstwo"),
    "rec.approve.overtime": ("Approve the extra person", "Zatwierdź dodatkową osobę"),
    "rec.approve.descope": ("Approve dropping the task", "Zatwierdź rezygnację z zadania"),
    "rec.approve.reseq": ("Approve the new order", "Zatwierdź nową kolejność"),
    "rec.approve.shift": ("Approve the moved dates", "Zatwierdź przesunięcie terminów"),
    "rec.reject_confirm": (
        "Reject this proposal? The plan stays as it is, and Sentinel will suggest again after "
        "the next check-in.",
        "Odrzucić tę propozycję? Plan pozostaje bez zmian, a Sentinel zaproponuje znowu po "
        "następnym raporcie.",
    ),
    "rec.reject_yes": ("Reject the proposal", "Odrzuć propozycję"),
    "rec.reject_back": ("Back", "Wróć"),
    "rec.parked": (
        "Postponed · we will come back to it at the next check-in",
        "Odłożone · wrócimy przy następnym raporcie",
    ),
    "rec.effect": ("Effect compared with no change", "Efekt w porównaniu z brakiem zmian"),
    "rec.needs_approval": ("Needs your approval: {reasons}.", "Wymaga Twojej zgody: {reasons}."),
    "rec.reason.people": ("affects people", "dotyczy ludzi"),
    "rec.reason.money": ("costs money", "kosztuje"),
    "rec.reason.scope": ("changes scope", "zmienia zakres"),
    "rec.reason.plan": (
        "changes the plan more than your setting allows",
        "zmienia plan bardziej, niż pozwala Twoje ustawienie",
    ),
    "rec.was_auto": (
        "Sentinel applied this automatically because your settings allow it.",
        "Sentinel zastosował to automatycznie, bo pozwalają na to Twoje ustawienia.",
    ),
    "rec.no_undo": ("It can no longer be undone.", "Nie można już tego cofnąć."),
    "rec.discarded": (
        "When you approved it, this action was no longer possible, so the plan did not change.",
        "W chwili zatwierdzenia to działanie nie było już możliwe, więc plan się nie zmienił.",
    ),
    "rec.why": ("Why this proposal", "Dlaczego ta propozycja"),
    "rec.ai_title": ("In other words (AI):", "Innymi słowy (AI, po angielsku):"),
    "rec.badge.faithful": ("checked against the data", "sprawdzone z danymi"),
    "rec.badge.unfaithful": ("not confirmed by the data", "niepotwierdzone przez dane"),
    "rec.ai_invalid": (
        "The AI gave no usable explanation.",
        "AI nie podało użytecznego wyjaśnienia.",
    ),
    "rec.ask_ai": ("Explain in other words (AI)", "Wyjaśnij innymi słowami (AI)"),
    "rec.changes_title": ("Tasks whose dates move", "Zadania, których terminy się zmieniają"),
    "rec.change": ("“{task}”: {old} → {new}", "„{task}”: {old} → {new}"),
    "rec.more_changes.one": ("and {n} more task", "i jeszcze {n} zadanie"),
    "rec.more_changes.few": ("and {n} more tasks", "i jeszcze {n} zadania"),
    "rec.more_changes.many": ("and {n} more tasks", "i jeszcze {n} zadań"),
    "rec.alternatives": ("Options compared", "Porównane możliwości"),
    "rec.col.option": ("Option", "Możliwość"),
    "rec.col.chance": ("Chance of meeting the deadline", "Szansa na dotrzymanie terminu"),
    "rec.col.delay": ("Expected delay (working days)", "Oczekiwane opóźnienie (dni robocze)"),
    "rec.col.cost": ("Expected cost", "Oczekiwany koszt"),
    "rec.chosen": ("Recommended", "Polecana"),
    "rec.dropped": ("(set aside early)", "(odrzucona na wstępie)"),
    "rec.alt_note": (
        "Every option was tried on the same {futures} simulated futures as the forecast on the "
        "overview, so “No change (keep the plan)” has the overview's chance.",
        "Każdą możliwość sprawdzono na tych samych {futures} symulowanych scenariuszach co "
        "prognozę na stronie przeglądu, więc „Bez zmian (zachowaj plan)” ma tę samą szansę.",
    ),
    "rec.alt_note_own": (
        "Every option was tried on the same simulated futures. Options set aside early were "
        "clearly worse in the first ones, so fewer futures were simulated for them.",
        "Każdą możliwość sprawdzono na tych samych symulowanych scenariuszach. Możliwości "
        "odrzucone na wstępie wypadły wyraźnie gorzej w pierwszych z nich, więc zasymulowano dla "
        "nich mniej scenariuszy.",
    ),
    "rec.reject": ("Reject", "Odrzuć"),
    "rec.later": ("Decide later", "Zdecyduj później"),
    "rec.approve": ("Approve the change", "Zatwierdź zmianę"),
    "rec.back": ("Back to the overview", "Wróć do przeglądu"),
    "rec.open": ("Review and decide", "Przejrzyj i zdecyduj"),
    "chip.chance": ("Chance", "Szansa"),
    "chip.from_to": ("{before} → {after}", "{before} → {after}"),
    "chip.finish": ("Finish", "Koniec"),
    "chip.likely": ("Most likely finish", "Najbardziej prawdopodobny koniec"),
    "chip.cost": ("Cost", "Koszt"),
    "chip.cost_shares": (
        "{before} → {after} of the budget ({change})",
        "{before} → {after} budżetu ({change})",
    ),
    "chip.moved": ("Tasks moved", "Przesunięte zadania"),
    "chip.delay": ("Expected delay (working days)", "Oczekiwane opóźnienie (dni robocze)"),
    "chip.better": ("better", "lepiej"),
    "chip.worse": ("worse", "gorzej"),
    "chip.tasks.one": ("{n} task", "{n} zadanie"),
    "chip.tasks.few": ("{n} tasks", "{n} zadania"),
    "chip.tasks.many": ("{n} tasks", "{n} zadań"),
    "why.keep_plain": ("No change is needed.", "Zmiana nie jest potrzebna."),
    "why.on_track": (
        "The project is on track: without any change the chance of meeting the deadline is {p}, "
        "so Sentinel recommends keeping the plan.",
        "Projekt jest na dobrej drodze: bez żadnej zmiany szansa na dotrzymanie terminu wynosi "
        "{p}, więc Sentinel zaleca zachowanie planu.",
    ),
    "why.keep": (
        "Sentinel compared {options} options on simulated futures; none is clearly better than "
        "keeping the plan, with a {p} chance of meeting the deadline.",
        "Sentinel porównał możliwości ({options}) na symulowanych scenariuszach; żadna nie jest "
        "wyraźnie lepsza niż zachowanie planu, przy którym szansa na dotrzymanie terminu wynosi "
        "{p}.",
    ),
    "why.without": (
        "No change: {p}. With this change: {after}.",
        "Bez zmian: {p}. Z tą zmianą: {after}.",
    ),
    "why.with": (
        "Sentinel checked {options} options.",
        "Sentinel sprawdził możliwości: {options}.",
    ),
    "why.with_own": (
        "Sentinel checked {options} options.",
        "Sentinel sprawdził możliwości: {options}.",
    ),
    "why.delay": (
        "The expected delay is {days} working days.",
        "Oczekiwane opóźnienie w dniach roboczych: {days}.",
    ),
    "why.delay_from": (
        "The expected delay is {days} working days (no change: {before}).",
        "Oczekiwane opóźnienie w dniach roboczych: {days} (bez zmian: {before}).",
    ),
    "why.reason": ("It was chosen because {reason}.", "Wybrano ją, ponieważ {reason}."),
    "why.runner": ("Next best: {title} ({p}).", "Następna w kolejności: {title} ({p})."),
    "why.tie.similar": (
        "Similar chance (the difference is within the uncertainty); {part}.",
        "Podobna szansa (różnica w granicach niepewności); {part}.",
    ),
    "why.tie.target": (
        "Both options reach the target chance; {part}.",
        "Oba warianty osiągają docelową szansę; {part}.",
    ),
    "why.tie.by.tardiness": (
        "the option with the smaller expected delay was chosen",
        "wybrano wariant z mniejszym oczekiwanym opóźnieniem",
    ),
    "why.tie.by.scope": (
        "the option that gives up less scope was chosen",
        "wybrano wariant, który mniej ogranicza zakres",
    ),
    "why.tie.by.budget": (
        "the option with the smaller expected budget overrun was chosen",
        "wybrano wariant z mniejszym oczekiwanym przekroczeniem budżetu",
    ),
    "why.tie.by.stability": (
        "the option that changes fewer dates was chosen",
        "wybrano wariant, który zmienia mniej terminów",
    ),
    "why.tie.by.level": (
        "the option that needs less approval was chosen",
        "wybrano wariant, który wymaga mniej zatwierdzeń",
    ),
    "why.tie.by.order": (
        "the options are equal on the rest, so the simplest was chosen",
        "warianty są równorzędne także pod innymi względami, więc wybrano najprostszy",
    ),
    # ---- history
    "history.title": ("History", "Historia"),
    "history.chance_title": ("Chance over time", "Szansa w czasie"),
    "history.chance_note": (
        "One point per check-in; the dashed line is the target of 80 %.",
        "Jeden punkt na raport; linia przerywana to cel 80 %.",
    ),
    "history.chance_desc": (
        "Chance of meeting the deadline: from {first} to {last}.",
        "Szansa na dotrzymanie terminu: od {first} do {last}.",
    ),
    "history.older": ("Show older ({n})", "Pokaż starsze ({n})"),
    "history.empty_title": (
        "Your check-ins and decisions will appear here.",
        "Tu zobaczysz raporty i decyzje.",
    ),
    "history.first": ("Add the first check-in", "Dodaj pierwszy raport"),
    "history.week.this": ("This week", "Ten tydzień"),
    "history.chip": ("{before} → {after}", "{before} → {after}"),
    "history.filter": ("Show", "Pokaż"),
    "history.show.all": ("Everything", "Wszystko"),
    "history.show.checkins": ("Check-ins", "Raporty"),
    "history.show.recommendations": ("Decisions", "Decyzje"),
    "history.show.changes": ("Plan changes", "Zmiany planu"),
    "history.kind.checkin": ("Check-in", "Raport statusu"),
    "history.kind.recommendation": ("Recommendation", "Rekomendacja"),
    "history.kind.decision": ("Decision", "Decyzja"),
    "history.kind.change": ("Change", "Zmiana"),
    "history.empty": ("Nothing to show yet.", "Na razie nic tu nie ma."),
    "history.recommendation": ("Recommended: {title}", "Rekomendacja: {title}"),
    "history.status": ("Status: {status}", "Status: {status}"),
    "history.discarded": (
        "Approved, but no longer possible: {title}",
        "Zatwierdzone, ale już niemożliwe: {title}",
    ),
    "history.verdict.approve": ("You approved: {title}", "Zatwierdzono: {title}"),
    "history.verdict.reject": ("You rejected: {title}", "Odrzucono: {title}"),
    "history.verdict.later": ("You postponed: {title}", "Odłożono: {title}"),
    "history.undone": ("Automatic change undone: {title}", "Cofnięto automatyczną zmianę: {title}"),
    "history.plan": (
        "Plan created: without disruptions it finishes on {date}",
        "Utworzono plan: bez zakłóceń kończy się {date}",
    ),
    "history.created": ("Project created", "Utworzono projekt"),
    "history.definition": ("Project details changed", "Zmieniono dane projektu"),
    "history.explanation": ("AI explanation added", "Dodano wyjaśnienie AI"),
    "history.checkin": ("Check-in for {date}", "Raport statusu za {date}"),
    "history.task_done": ("“{task}” done on {date}", "„{task}” gotowe {date}"),
    "history.task_progress": (
        "“{task}” in progress, {percent} % done",
        "„{task}” w toku, wykonano {percent} %",
    ),
    "history.away_back": (
        "{person} away from {first}, back on {back}",
        "{person}: nieobecność od {first}, powrót {back}",
    ),
    "history.away": ("{person} away from {first}", "{person}: nieobecność od {first}"),
    "history.grows_days": (
        "“{task}” needs {days} more working days",
        "„{task}”: dodatkowe dni robocze: {days}",
    ),
    "history.grows_factor": (
        "“{task}” needs {percent} % more of the work left",
        "„{task}” potrzebuje o {percent} % więcej pozostałej pracy",
    ),
    "history.new_task": (
        "New task “{task}” ({days} working days)",
        "Nowe zadanie „{task}” (dni robocze: {days})",
    ),
    "history.nothing": ("No changes reported", "Bez zgłoszonych zmian"),
    "history.no_change": ("Sentinel proposes no change", "Sentinel nie proponuje zmian"),
    # ---- project settings
    "psettings.title": ("Project settings", "Ustawienia projektu"),
    "psettings.basics": ("Name, deadline and budget", "Nazwa, termin i budżet"),
    "psettings.budget_hint": (
        "Leave empty to use the estimate from the tasks ({budget}).",
        "Pozostaw puste, aby użyć szacunku na podstawie zadań ({budget}).",
    ),
    "psettings.autonomy": ("What may Sentinel do on its own?", "Co Sentinel może robić sam?"),
    "psettings.recommended": ("Recommended", "Zalecane"),
    "psettings.alone": ("On its own:", "Sam:"),
    "psettings.asks": ("Asks about:", "Pyta o:"),
    "psettings.cost_unit": ("cost units (person-days)", "jednostek kosztu (osobodni)"),
    "psettings.costs_how": ("How to count the cost", "Jak liczyć koszt"),
    "psettings.unsaved": ("You have unsaved changes", "Masz niezapisane zmiany"),
    "psettings.changed_title": (
        "These settings changed after you opened this page",
        "Te ustawienia zmieniły się po otwarciu tej strony",
    ),
    "psettings.changed_text": (
        "Probably in another tab. What you entered is below and is not saved yet. Save again to "
        "replace those changes, or reload the page to see them.",
        "Pewnie w innej karcie. To, co wpisano, jest poniżej i nie jest jeszcze zapisane. Zapisz "
        "ponownie, żeby zastąpić tamte zmiany, albo odśwież stronę, żeby je zobaczyć.",
    ),
    "psettings.reset": ("Undo the changes", "Cofnij zmiany"),
    "psettings.save": ("Save the changes", "Zapisz zmiany"),
    "psettings.download": ("Download", "Pobierz"),
    "psettings.report_row": (
        "Report for the team (HTML, one page to print or send)",
        "Raport dla zespołu (HTML, jedna strona do druku lub wysłania)",
    ),
    "autonomy.0.alone": ("nothing.", "nic."),
    "autonomy.0.asks": ("every change.", "każdą zmianę."),
    "autonomy.1.alone": ("task dates.", "daty zadań."),
    "autonomy.1.asks": ("everything else.", "wszystko inne."),
    "autonomy.2.alone": ("task dates and order.", "daty i kolejność zadań."),
    "autonomy.2.asks": ("people, budget, scope.", "ludzi, budżet, zakres."),
    "autonomy.3.alone": (
        "also substitutes and temporary people.",
        "także zastępstwa i osoby tymczasowe.",
    ),
    "autonomy.3.asks": ("dropping tasks.", "rezygnacje z zadań."),
    "autonomy.0": ("Only advise me", "Tylko doradzaj"),
    "autonomy.1": ("May shift dates", "Może przesuwać terminy"),
    "autonomy.2": ("May re-plan the order", "Może zmieniać kolejność zadań"),
    "autonomy.3": ("May also add people and substitutes", "Może też dodawać osoby i zastępstwa"),
    "psettings.presets": ("Estimates and absences", "Szacunki i nieobecności"),
    "psettings.costs": ("Cost of a working day", "Koszt dnia pracy"),
    "psettings.costs_hint": (
        "One person's working day in cost units: 1 by default, so a cost unit is a person-day; "
        "you may use your own unit, e.g. a currency. A temporary person costs one and a half "
        "times as much.",
        "Dzień pracy jednej osoby w jednostkach kosztu: domyślnie 1, więc jednostka to osobodzień; "
        "możesz użyć własnej jednostki, np. waluty. Osoba tymczasowa kosztuje półtora raza "
        "więcej.",
    ),
    "psettings.cost_of": ("Daily cost: {role}", "Koszt dzienny: {role}"),
    "psettings.ai": ("AI features", "Funkcje AI"),
    "psettings.ai_proposals": (
        "Let the AI suggest extra options for Sentinel to test",
        "Pozwól AI proponować dodatkowe możliwości do sprawdzenia przez Sentinela",
    ),
    "psettings.export": ("Export", "Eksport"),
    "psettings.export_plan": ("Task plan (CSV)", "Plan zadań (CSV)"),
    "psettings.export_project": (
        "The whole project (JSON, to import later)",
        "Cały projekt (JSON, do późniejszego importu)",
    ),
    "psettings.delete": ("Delete the project", "Usuń projekt"),
    "psettings.delete_text": (
        "This removes the plan, the check-ins and the history. It cannot be undone.",
        "Usuwa plan, raporty i historię. Nie da się tego cofnąć.",
    ),
    "psettings.delete_button": ("Delete the project…", "Usuń projekt…"),
    "delete.title": ("Delete the project?", "Usunąć projekt?"),
    "delete.text": (
        "Delete “{name}”? The plan, the check-ins and the history will be gone. This cannot be "
        "undone.",
        "Usunąć „{name}”? Plan, raporty i historia znikną. Tego nie da się cofnąć.",
    ),
    "delete.confirm": ("Delete for good", "Usuń projekt na zawsze"),
    # ---- simulator
    "sim.title": ("Simulator", "Symulator"),
    "sim.moving_title": ("The simulation is working", "Symulacja pracuje"),
    "sim.moving_note": (
        "You can leave this page; the run goes on.",
        "Możesz opuścić tę stronę; przebieg trwa dalej.",
    ),
    "sim.replay_note": (
        "Restoring the run after a restart of the server takes as long as simulating it.",
        "Odtworzenie przebiegu po restarcie serwera trwa tyle co jego symulacja.",
    ),
    "sim.day_of": ("Day {day} of about {total}", "Dzień {day} z ok. {total}"),
    "sim.chance_from": (
        "from Sentinel's analysis of {date}, if the plan stayed as it was",
        "z analizy Sentinela z {date}, gdyby plan się już nie zmieniał",
    ),
    "sim.chance_none": (
        "Sentinel has not analysed this project yet.",
        "Sentinel jeszcze nie analizował tego projektu.",
    ),
    "sim.tasks_short": ("{done} of {total} tasks", "{done} z {total} zadań"),
    "sim.differs": (
        "How does this differ from the research results?",
        "Czym to się różni od wyników badań?",
    ),
    "sim.restart": ("Run it again", "Uruchom ponownie"),
    "sim.col.difference": ("Difference", "Różnica"),
    "sim.col.late": ("After the deadline", "Po terminie"),
    "sim.diff.earlier": ("{days} earlier", "{days} wcześniej"),
    "sim.diff.later": ("{days} later", "{days} później"),
    "sim.diff.none": ("no difference", "bez różnicy"),
    "sim.end_note.j30": ("This takes under a minute.", "To potrwa poniżej minuty."),
    "sim.end_note.j60": ("This takes two or three minutes.", "To potrwa 2–3 minuty."),
    "sim.verdict.earlier": (
        "With Sentinel the project finished {days} earlier than with nobody reacting, but "
        "still {late} after the deadline.",
        "Z Sentinelem projekt skończył się {days} wcześniej niż bez reakcji, ale wciąż {late} "
        "po terminie.",
    ),
    "sim.verdict.later": (
        "With Sentinel the project finished {days} later than with nobody reacting; chance "
        "plays a part.",
        "Z Sentinelem projekt skończył się {days} później niż bez reakcji; przypadek też ma "
        "znaczenie.",
    ),
    "sim.lead": (
        "See how Sentinel runs an example project day by day, and compare it with nobody reacting.",
        "Zobacz, jak Sentinel prowadzi przykładowy projekt dzień po dniu, i porównaj z "
        "sytuacją, w której nikt nie reaguje.",
    ),
    "sim.settings_note": (
        "The simulator uses the application's settings, not the setup of the research studies: "
        "at least one temporary person per role can always be added, and each decision is taken "
        "on the same 200 simulated futures as its figures, so a run can differ from the studies' "
        "results.",
        "Symulator używa ustawień aplikacji, a nie ustawień badań: zawsze można dodać co najmniej "
        "jedną osobę tymczasową w każdej roli, a każda decyzja zapada na tych samych 200 "
        "symulowanych scenariuszach co jej liczby, więc przebieg może się różnić od wyników badań.",
    ),
    "sim.unavailable": (
        "The example projects are not installed on this server.",
        "Na tym serwerze nie zainstalowano przykładowych projektów.",
    ),
    "sim.example": ("Example project", "Przykładowy projekt"),
    "sim.size.j30": ("Small example project (30 tasks)", "Mały przykładowy projekt (30 zadań)"),
    "sim.size.j60": ("Medium example project (60 tasks)", "Średni przykładowy projekt (60 zadań)"),
    "sim.example_hint.j30": (
        "30 tasks and 4 roles. Running it to the end takes under a minute.",
        "30 zadań i 4 role. Symulacja do końca trwa poniżej minuty.",
    ),
    "sim.example_hint.j60": (
        "60 tasks and 4 roles. Running it to the end takes two or three minutes.",
        "60 zadań i 4 role. Symulacja do końca trwa 2–3 minuty.",
    ),
    "sim.manager": ("Who manages the project?", "Kto zarządza projektem?"),
    "sim.manager.sentinel": ("Sentinel", "Sentinel"),
    "sim.manager.sentinel.hint": (
        "Sentinel reacts to events; a simulated manager approves the changes that need approval "
        "after a short delay.",
        "Sentinel reaguje na zdarzenia; zmiany wymagające zgody zatwierdza po krótkiej chwili "
        "symulowany kierownik.",
    ),
    "sim.manager.no_reaction": ("Nobody reacts", "Nikt nie reaguje"),
    "sim.manager.no_reaction.hint": (
        "The plan is followed as it is, whatever happens.",
        "Plan jest realizowany bez zmian, cokolwiek się stanie.",
    ),
    "sim.start": ("Start the simulation", "Rozpocznij symulację"),
    "sim.name.j30": ("Example project (small)", "Przykładowy projekt (mały)"),
    "sim.name.j60": ("Example project (medium)", "Przykładowy projekt (średni)"),
    "sim.managed_by": ("managed by: {manager}", "zarządza: {manager}"),
    "sim.state_title": ("Status on {date}", "Stan na {date}"),
    "sim.original_finish": (
        "Original plan without disruptions finishes",
        "Plan początkowy bez zakłóceń kończy się",
    ),
    "sim.cost_so_far": ("Cost: {cost} ({share} of the budget)", "Koszt: {cost} ({share} budżetu)"),
    "sim.advance_by": ("Move on:", "Przewiń:"),
    "sim.days.1": ("+1 day", "+1 dzień"),
    "sim.days.5": ("+5 days", "+5 dni"),
    "sim.days.10": ("+10 days", "+10 dni"),
    "sim.days.end": ("To the end", "Do końca"),
    "sim.compare_title": ("How it ended", "Jak się skończyło"),
    "sim.col.measure": ("Measure", "Miara"),
    "sim.col.finish": ("Finish", "Zakończenie"),
    "sim.col.cost": ("Cost", "Koszt"),
    "sim.col.changes": ("Plan changes", "Zmiany planu"),
    "sim.col.hired": ("Temporary people", "Osoby tymczasowe"),
    "sim.col.substituted": ("Substitutions", "Zastępstwa"),
    "sim.on_time": ("on time", "w terminie"),
    "sim.late.one": ("{n} working day late", "{n} dzień roboczy po terminie"),
    "sim.late.few": ("{n} working days late", "{n} dni robocze po terminie"),
    "sim.late.many": ("{n} working days late", "{n} dni roboczych po terminie"),
    "sim.report": ("Show the report", "Pokaż raport"),
    "sim.timeline_title": ("What happened", "Co się wydarzyło"),
    "sim.timeline_empty": (
        "Nothing yet — simulate a few days.",
        "Jeszcze nic — zasymuluj kilka dni.",
    ),
    "sim.kind.absence": ("Absence", "Nieobecność"),
    "sim.kind.grows": ("A task grows", "Zadanie się wydłuża"),
    "sim.kind.new": ("New task", "Nowe zadanie"),
    "sim.kind.sentinel": ("Sentinel", "Sentinel"),
    "sim.kind.finish": ("End", "Koniec"),
    "sim.event.away.one": (
        "{person} is away; expected back in {n} working day",
        "{person}: nieobecność, zapowiedziany powrót za {n} dzień roboczy",
    ),
    "sim.event.away.few": (
        "{person} is away; expected back in {n} working days",
        "{person}: nieobecność, zapowiedziany powrót za {n} dni robocze",
    ),
    "sim.event.away.many": (
        "{person} is away; expected back in {n} working days",
        "{person}: nieobecność, zapowiedziany powrót za {n} dni roboczych",
    ),
    "sim.event.grows": (
        "“{task}” needs {percent} % more of the work left",
        "„{task}” potrzebuje o {percent} % więcej pozostałej pracy",
    ),
    "sim.event.new.one": (
        "New task “{task}” ({n} working day)",
        "Nowe zadanie „{task}” ({n} dzień roboczy)",
    ),
    "sim.event.new.few": (
        "New task “{task}” ({n} working days)",
        "Nowe zadanie „{task}” ({n} dni robocze)",
    ),
    "sim.event.new.many": (
        "New task “{task}” ({n} working days)",
        "Nowe zadanie „{task}” ({n} dni roboczych)",
    ),
    "sim.event.auto": ("Sentinel applied: {action}", "Sentinel zastosował: {action}"),
    "sim.event.asked": (
        "Sentinel asked the manager: {action}",
        "Sentinel poprosił kierownika o zgodę: {action}",
    ),
    "sim.event.deferred": (
        "Sentinel postponed (it can wait): {action}",
        "Sentinel odłożył (może poczekać): {action}",
    ),
    "sim.event.approved": ("The manager approved: {action}", "Kierownik zatwierdził: {action}"),
    "sim.event.finished": ("Finished on {date}:", "Zakończono {date}:"),
    "sim.verdict.single_on_time": (
        "The project finished on time.",
        "Projekt zakończył się w terminie.",
    ),
    "sim.verdict.single_late.one": (
        "The project finished {n} working day late.",
        "Projekt zakończył się {n} dzień roboczy po terminie.",
    ),
    "sim.verdict.single_late.few": (
        "The project finished {n} working days late.",
        "Projekt zakończył się {n} dni robocze po terminie.",
    ),
    "sim.verdict.single_late.many": (
        "The project finished {n} working days late.",
        "Projekt zakończył się {n} dni roboczych po terminie.",
    ),
    "sim.verdict.both_on_time": (
        "Both finished on time on the same events.",
        "Przy tych samych zdarzeniach oba przebiegi zakończyły się w terminie.",
    ),
    "sim.verdict.saved.one": (
        "Sentinel met the deadline; with nobody reacting, the same events made the project {n} "
        "working day late.",
        "Sentinel dotrzymał terminu; bez reakcji te same zdarzenia opóźniły projekt o {n} dzień "
        "roboczy.",
    ),
    "sim.verdict.saved.few": (
        "Sentinel met the deadline; with nobody reacting, the same events made the project {n} "
        "working days late.",
        "Sentinel dotrzymał terminu; bez reakcji te same zdarzenia opóźniły projekt o {n} dni "
        "robocze.",
    ),
    "sim.verdict.saved.many": (
        "Sentinel met the deadline; with nobody reacting, the same events made the project {n} "
        "working days late.",
        "Sentinel dotrzymał terminu; bez reakcji te same zdarzenia opóźniły projekt o {n} dni "
        "roboczych.",
    ),
    "sim.verdict.worse.one": (
        "This time Sentinel finished {n} working day late while nobody reacting was on time; "
        "chance plays a part.",
        "Tym razem Sentinel zakończył {n} dzień roboczy po terminie, a bez reakcji projekt "
        "zmieścił się w terminie; przypadek też ma znaczenie.",
    ),
    "sim.verdict.worse.few": (
        "This time Sentinel finished {n} working days late while nobody reacting was on time; "
        "chance plays a part.",
        "Tym razem Sentinel zakończył {n} dni robocze po terminie, a bez reakcji projekt "
        "zmieścił się w terminie; przypadek też ma znaczenie.",
    ),
    "sim.verdict.worse.many": (
        "This time Sentinel finished {n} working days late while nobody reacting was on time; "
        "chance plays a part.",
        "Tym razem Sentinel zakończył {n} dni roboczych po terminie, a bez reakcji projekt "
        "zmieścił się w terminie; przypadek też ma znaczenie.",
    ),
    "sim.verdict.both_late": (
        "Both finished late: with Sentinel {main}, with nobody reacting {other} after the "
        "deadline.",
        "Oba przebiegi skończyły się po terminie: z Sentinelem {main}, bez reakcji {other}.",
    ),
    "sim.delete": ("Delete this simulation", "Usuń tę symulację"),
    # ---- cost units (spec section 11.2): values, values of a budget, short forms, changes
    "cost.units.one": ("{value} cost unit", "{value} jednostka kosztu"),
    "cost.units.few": ("{value} cost units", "{value} jednostki kosztu"),
    "cost.units.many": ("{value} cost units", "{value} jednostek kosztu"),
    "cost.of.one": ("{spent} of {budget} cost unit", "{spent} z {budget} jednostki kosztu"),
    "cost.of.few": ("{spent} of {budget} cost units", "{spent} z {budget} jednostek kosztu"),
    "cost.of.many": ("{spent} of {budget} cost units", "{spent} z {budget} jednostek kosztu"),
    "cost.short.one": ("{value} unit", "{value} jedn."),
    "cost.short.few": ("{value} units", "{value} jedn."),
    "cost.short.many": ("{value} units", "{value} jedn."),
    "cost.change": ("{units}, {share} of the budget", "{units}, {share} budżetu"),
    "cost.change_small": (
        "{units}, under 1\u00a0% of the budget",
        "{units}, poniżej 1\u00a0% budżetu",
    ),
    "cost.person_days": ("(person-days)", "(osobodni)"),
    "cost.note.person_days": (
        "Costs are in cost units: one cost unit is one person-day.",
        "Koszty podano w jednostkach kosztu: jedna jednostka to jeden osobodzień.",
    ),
    "cost.note.custom": (
        "Costs are in cost units, as set by the daily costs in the project settings.",
        "Koszty podano w jednostkach kosztu, zgodnie z dziennymi kosztami w ustawieniach projektu.",
    ),
}


def plural_form(language: Language, n: int) -> str:
    """The plural form of a number: "one", "few" or "many" (Polish rules; English has no
    "few")."""
    n = abs(n)
    if n == 1:
        return "one"
    if language == "pl" and n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "few"
    return "many"


class Texts:
    """The texts and formats of one language for the templates (`t`)."""

    def __init__(self, language: Language) -> None:
        self.lang: Language = language
        self._index = 0 if language == "en" else 1

    def __call__(self, key: str, **params: object) -> str:
        entry = CATALOGUE.get(key)
        if entry is None:
            return f"⟦{key}⟧"
        text = entry[self._index]
        try:
            return text.format(**params) if params else text
        except (KeyError, IndexError, ValueError):
            return f"⟦{key}⟧"

    def plural(self, key: str, n: int, **params: object) -> str:
        return self(f"{key}.{plural_form(self.lang, n)}", n=n, **params)

    def msg(self, code: str, **params: object) -> str:
        """A message of the application's catalogue (errors, statuses, actions)."""
        return render(code, self.lang, params)

    def error(self, error: AppError) -> str:
        return render(error.code, self.lang, error.params)

    def issues(self, error: AppError) -> list[str]:
        """The messages of an error and of every issue behind it."""
        found = [view.message for view in issue_views(error.issues, self.lang)]
        return found or [self.error(error)]

    # ---- formats

    def date(self, value: Day | None) -> str:
        """A date as "Mon 14 Mar" ("pon. 14 mar"), with the year if it is not this year's."""
        return "—" if value is None else date_text(value, self.lang)

    def date_long(self, value: Day) -> str:
        """A date with its year: "Fri 13 Nov 2026" ("pt. 13 lis 2026")."""
        weekday = WEEKDAYS[self.lang][value.weekday()]
        return f"{weekday} {value.day}{NBSP}{MONTHS[self.lang][value.month - 1]} {value.year}"

    def ago(self, value: Day, today: Day | None = None) -> str:
        """A past date in a list, relative to today: "2 days ago"; a future one in full."""
        days = ((today or Day.today()) - value).days
        if days < 0:
            return self.date(value)
        if days == 0:
            return self("start.today")
        if days == 1:
            return self("start.yesterday")
        return self.plural("start.days_ago", days)

    @property
    def weekdays(self) -> str:
        """The weekdays' short names for the page's script, Monday first."""
        return ",".join(WEEKDAYS[self.lang])

    @property
    def months(self) -> str:
        return ",".join(MONTHS[self.lang])

    def day_month(self, value: Day) -> str:
        return f"{value.day}{NBSP}{MONTHS[self.lang][value.month - 1]}"

    def week_range(self, monday: Day) -> str:
        """A working week from its Monday: "6–10 Nov", "30 Nov – 4 Dec" ("6–10 lis")."""
        friday = monday + timedelta(days=4)
        if monday.month == friday.month:
            return f"{monday.day}\u2013{self.day_month(friday)}"
        return f"{self.day_month(monday)} \u2013 {self.day_month(friday)}"

    def moment(self, value: datetime) -> str:
        """A point in time in the server's time zone: "Mon 14 Mar, 14:05"."""
        local = value.astimezone()
        return f"{self.date(local.date())}, {local:%H:%M}"

    def pct(self, value: float | None) -> str:
        """A probability as a whole percentage; never "0 %" or "100 %" unless it is exact."""
        if value is None or math.isnan(value):
            return "—"
        percent = int(half_up(100 * value))
        if value > 0 and percent == 0:
            return f"<{NBSP}1{NBSP}%"
        if value < 1 and percent == 100:
            return f">{NBSP}99{NBSP}%"
        return f"{percent}{NBSP}%"

    def share(self, value: float) -> str:
        """A share of the budget as a whole percentage, half up; unlike a chance it may read
        0 %, 100 % or more (the overview and a card show the same, B3 of the WP12 test)."""
        return f"{int(half_up(100 * value))}{NBSP}%"

    def decimal(self, value: float) -> str:
        """A number with at most one decimal, half up (a decimal comma in Polish)."""
        text = f"{half_up(value, 1):.1f}"
        if text.endswith(".0"):
            text = text[:-2]
        if text == "-0":
            text = "0"
        return text.replace(".", ",") if self.lang == "pl" else text

    def money(self, value: float) -> str:
        """A cost as a whole number with thousands separators."""
        number = math.floor(abs(value) + 0.5)
        separator = NBSP if self.lang == "pl" else ","
        text = f"{number:,}".replace(",", separator)
        return f"{MINUS}{text}" if value < -0.5 else text

    def cost(self, value: float) -> str:
        """A cost in cost units: "84 cost units" ("84 jednostki kosztu")."""
        return self.plural("cost.units", _whole(value), value=self.money(value))

    def cost_of(self, spent: float, budget: float) -> str:
        """Spent of a budget: "27 of 84 cost units" ("27 z 84 jednostek kosztu")."""
        form = f"cost.of.{plural_form(self.lang, _whole(budget))}"
        return self(form, spent=self.money(spent), budget=self.money(budget))

    def cost_of_parts(self, spent: float, budget: float) -> tuple[str, str]:
        """`cost_of` in two parts for a tile: ("27 of 84", "cost units")."""
        text = self.cost_of(spent, budget)
        number = self.money(budget)
        head, _, unit = text.partition(number)
        return f"{head}{number}", unit.strip()

    def cost_short(self, value: float) -> str:
        """A cost in short: "92 units" ("92 jedn.")."""
        return self.plural("cost.short", _whole(value), value=self.money(value))

    def cost_change(self, value: float, budget: float | None) -> str:
        """A change of cost in units and as a share of the budget: "+1 unit, +1 % of the
        budget" ("+1 jedn., +1 % budżetu"); "±0" when it rounds to nothing."""
        number = _whole(value)
        if number == 0:
            return "±0"
        units = ("+" if value > 0 else MINUS) + self.cost_short(abs(value))
        if not budget:
            return units
        percent = math.floor(100 * abs(value) / budget + 0.5)
        if percent == 0:
            return self("cost.change_small", units=units)
        share = f"{'+' if value > 0 else MINUS}{percent}{NBSP}%"
        return self("cost.change", units=units, share=share)

    def reasons(self, reasons: Sequence[str]) -> str:
        """Why an action needs approval, in the wording of spec section 11.7."""
        return ", ".join(self(f"rec.reason.{reason}") for reason in reasons)

    def tie(self, kind: str, reason: str) -> str:
        """The sentence shown when an alternative has a higher chance (spec 11.5 item 7, 11.7)."""
        return self(f"why.tie.{kind}", part=self(f"why.tie.by.{reason}"))


def _whole(value: float) -> int:
    """A cost as the whole number shown (rounded half up, as `Texts.money`)."""
    return math.floor(abs(value) + 0.5)
