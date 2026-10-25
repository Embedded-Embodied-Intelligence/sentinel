"""The message catalogue of the pages in English and Polish (WP9b; spec section 11.7) and the
formats people read: dates as "Mon 14 Mar", whole percentages, numbers with separators.

Every string of the pages comes from `CATALOGUE` (key -> (English, Polish)) or from the
application's messages (`app/messages.py`); a test checks that both languages have every key
with the same placeholders and that no page shows an internal term. A missing key renders as
"⟦key⟧", which the test finds.
"""

import math
from collections.abc import Mapping
from datetime import date, datetime

from sentinel.app.errors import AppError
from sentinel.app.messages import render
from sentinel.app.models import Language
from sentinel.app.views import issue_views

Day = date  # the type, for the methods of `Texts` (one of them is called `date`)
NBSP = "\u00a0"
MINUS = "\u2212"
WEEKDAYS = {
    "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
    "pl": ("pon.", "wt.", "śr.", "czw.", "pt.", "sob.", "niedz."),
}
MONTHS = {
    "en": ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
    "pl": ("sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"),
}

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
    "footer.text": (
        "Sentinel — a research prototype for project managers",
        "Sentinel — prototyp badawczy dla kierowników projektów",
    ),
    "footer.version": ("version {version}", "wersja {version}"),
    "error.title": ("Something went wrong", "Coś poszło nie tak"),
    "error.reference": (
        "Reference: {reference}. Quote it if you report the problem.",
        "Numer zgłoszenia: {reference}. Podaj go, jeśli zgłaszasz problem.",
    ),
    "error.home": ("Back to the projects", "Wróć do projektów"),
    "common.cancel": ("Cancel", "Anuluj"),
    "common.save": ("Save", "Zapisz"),
    "common.retry": ("Try again", "Spróbuj ponownie"),
    "flash.checkin_saved": (
        "Check-in saved. The forecast has been updated.",
        "Raport zapisany. Prognoza została zaktualizowana.",
    ),
    "flash.approved": (
        "Approved: the plan has been changed.",
        "Zatwierdzone: plan został zmieniony.",
    ),
    "flash.rejected": (
        "Rejected. The plan stays as it was.",
        "Odrzucone. Plan pozostaje bez zmian.",
    ),
    "flash.later": (
        "Postponed. You can decide later on the project overview.",
        "Odłożone. Możesz zdecydować później na stronie przeglądu projektu.",
    ),
    "flash.undone": ("The automatic change was undone.", "Automatyczna zmiana została cofnięta."),
    "flash.deleted": ("The project was deleted.", "Projekt został usunięty."),
    "flash.settings_saved": ("Settings saved.", "Ustawienia zapisane."),
    "flash.plan_ready": ("The plan is ready.", "Plan jest gotowy."),
    "flash.discarded": (
        "The action is no longer possible; Sentinel is preparing a new recommendation.",
        "To działanie nie jest już możliwe; Sentinel przygotowuje nową rekomendację.",
    ),
    "flash.no_change": ("No change is needed.", "Zmiana nie jest potrzebna."),
    "flash.imported": (
        "The tasks were imported — please check them below.",
        "Zadania zostały zaimportowane — sprawdź je poniżej.",
    ),
    "job.plan": ("Building the plan…", "Układam plan…"),
    "job.recommend": ("Sentinel is analysing the project…", "Sentinel analizuje projekt…"),
    "job.advance": ("Simulating the next days…", "Symuluję kolejne dni…"),
    "job.simulator": ("Preparing the example project…", "Przygotowuję przykładowy projekt…"),
    "job.cockpit": ("Writing the report…", "Przygotowuję raport…"),
    "job.extract": ("The AI is reading the description…", "AI czyta opis…"),
    "job.message": ("The AI is reading the message…", "AI czyta wiadomość…"),
    "job.llm_test": ("Testing the connection…", "Sprawdzam połączenie…"),
    "job.explain": ("The AI is writing an explanation…", "AI pisze wyjaśnienie…"),
    # ---- start page
    "start.title": ("Your projects", "Twoje projekty"),
    "start.what": (
        "Sentinel watches your project's deadline and budget. After every check-in it plays the "
        "rest of the project out hundreds of times, tells you how likely you are to finish on "
        "time and, when the deadline is at risk, recommends what to do. You decide.",
        "Sentinel pilnuje terminu i budżetu Twojego projektu. Po każdym raporcie statusu "
        "rozgrywa resztę projektu setki razy, mówi, jak duża jest szansa na dotrzymanie terminu, "
        "a gdy termin jest zagrożony — poleca, co zrobić. Decyzja należy do Ciebie.",
    ),
    "start.new": ("New project", "Nowy projekt"),
    "start.try_simulator": ("Try the simulator", "Wypróbuj symulator"),
    "start.list": ("Projects", "Projekty"),
    "start.simulator_badge": ("Simulator", "Symulator"),
    "start.sim_days": ("Days simulated: {days}", "Zasymulowane dni: {days}"),
    "start.draft": ("Setup not finished", "Konfiguracja niedokończona"),
    "start.draft_hint": (
        "Add the team and the tasks to get a plan.",
        "Dodaj zespół i zadania, aby powstał plan.",
    ),
    "start.continue": ("Continue the setup", "Dokończ konfigurację"),
    "start.deadline": ("Deadline: {date}", "Termin: {date}"),
    "start.no_deadline": ("No deadline set", "Bez terminu"),
    "start.finished": ("Finished", "Zakończony"),
    "start.calculating": ("Calculating the chance…", "Obliczam szansę…"),
    "start.pending.one": ("{n} decision waiting", "{n} decyzja czeka"),
    "start.pending.few": ("{n} decisions waiting", "{n} decyzje czekają"),
    "start.pending.many": ("{n} decisions waiting", "{n} decyzji czeka"),
    "start.no_pending": ("No decisions waiting", "Brak decyzji do podjęcia"),
    "start.as_of": ("Last check-in: {date}", "Ostatni raport: {date}"),
    "start.not_tracked": ("No check-in yet", "Jeszcze bez raportu statusu"),
    "start.empty_title": ("No projects yet", "Nie masz jeszcze projektów"),
    "start.empty": (
        "Create your first project in three short steps, or try the simulator to watch Sentinel "
        "at work on an example project.",
        "Utwórz pierwszy projekt w trzech krótkich krokach albo wypróbuj symulator, aby "
        "zobaczyć Sentinela przy pracy na przykładowym projekcie.",
    ),
    "start.chance_failed": (
        "The chance could not be calculated.",
        "Nie udało się obliczyć szansy.",
    ),
    "start.chance": ("{p} chance of meeting the deadline", "{p} szansy na dotrzymanie terminu"),
    "start.no_chance": (
        "Set a deadline to see the chance of meeting it.",
        "Ustaw termin, aby zobaczyć szansę na jego dotrzymanie.",
    ),
    "chance.level.good": ("On track", "Na dobrej drodze"),
    "chance.level.warn": ("At risk", "Zagrożony"),
    "chance.level.bad": ("Unlikely", "Mało prawdopodobny"),
    "chance.level.neutral": ("Unknown", "Nieznana"),
    "trend.up.one": (
        "up {n} point since before the last check-in",
        "o {n} punkt procentowy więcej niż przed ostatnim raportem",
    ),
    "trend.up.few": (
        "up {n} points since before the last check-in",
        "o {n} punkty procentowe więcej niż przed ostatnim raportem",
    ),
    "trend.up.many": (
        "up {n} points since before the last check-in",
        "o {n} punktów procentowych więcej niż przed ostatnim raportem",
    ),
    "trend.down.one": (
        "down {n} point since before the last check-in",
        "o {n} punkt procentowy mniej niż przed ostatnim raportem",
    ),
    "trend.down.few": (
        "down {n} points since before the last check-in",
        "o {n} punkty procentowe mniej niż przed ostatnim raportem",
    ),
    "trend.down.many": (
        "down {n} points since before the last check-in",
        "o {n} punktów procentowych mniej niż przed ostatnim raportem",
    ),
    "trend.flat": (
        "about the same as before the last check-in",
        "mniej więcej tyle samo co przed ostatnim raportem",
    ),
    # ---- how it works
    "how.title": ("How it works", "Jak to działa"),
    "how.lead": (
        "Sentinel is a project assistant that thinks before it acts: it tries every option on "
        "simulated futures and recommends the one that best protects your goals.",
        "Sentinel to asystent projektu, który myśli, zanim zadziała: sprawdza każdą możliwość na "
        "symulowanych scenariuszach i poleca tę, która najlepiej chroni Twoje cele.",
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
    # ---- app settings
    "settings.title": ("Settings", "Ustawienia"),
    "settings.lead": (
        "Sentinel works without AI. If you connect a model, it can read project descriptions and "
        "messages and explain recommendations in its own words.",
        "Sentinel działa bez AI. Jeśli podłączysz model, będzie on mógł czytać opisy projektów i "
        "wiadomości oraz wyjaśniać rekomendacje własnymi słowami.",
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
    "report.ready": ("The report is ready.", "Raport jest gotowy."),
    "report.open": ("Open the report (new tab)", "Otwórz raport (nowa karta)"),
    # ---- new-project wizard
    "setup.eyebrow": ("New project", "Nowy projekt"),
    "setup.title": ("New project", "Nowy projekt"),
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
        "The last day by which all work should be done. Needed to see the chance of meeting it.",
        "Ostatni dzień, do którego cała praca powinna być gotowa. Potrzebny, aby zobaczyć "
        "szansę na jego dotrzymanie.",
    ),
    "setup.budget": ("Budget (optional)", "Budżet (opcjonalnie)"),
    "setup.budget_hint": (
        "In the unit of the daily costs of the roles (by default one person-day is 1). Leave it "
        "empty and Sentinel estimates it from the tasks.",
        "W jednostce dziennych kosztów ról (domyślnie jeden osobodzień to 1). Pozostaw puste, a "
        "Sentinel oszacuje go na podstawie zadań.",
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
    "setup.next": ("Next", "Dalej"),
    "setup.back": ("Back", "Wstecz"),
    "setup.finish": ("Create the plan", "Utwórz plan"),
    "setup.remove": ("Remove", "Usuń"),
    "setup.saved": ("Saved", "Zapisano"),
    "setup.unsaved": ("Not saved yet", "Jeszcze nie zapisano"),
    "setup.issues_title": ("Please check:", "Sprawdź proszę:"),
    "setup.team.lead": (
        "Who works on the project? Give each person a role, e.g. “Developer” or “Tester”. The "
        "roles decide who can do which task.",
        "Kto pracuje nad projektem? Nadaj każdej osobie rolę, np. „Programista” lub „Tester”. "
        "Role decydują o tym, kto może wykonać które zadanie.",
    ),
    "setup.team.caption": ("Team", "Zespół"),
    "setup.team.name": ("Name", "Imię i nazwisko"),
    "setup.team.role": ("Role", "Rola"),
    "setup.team.name_of": ("Name of person {n}", "Imię i nazwisko osoby {n}"),
    "setup.team.role_of": ("Role of person {n}", "Rola osoby {n}"),
    "setup.team.empty": (
        "No one yet. Add people one by one or paste a list.",
        "Nikogo jeszcze nie ma. Dodaj osoby pojedynczo albo wklej listę.",
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
    "setup.tab.describe": ("Describe the project", "Opisz projekt"),
    "setup.tab.import": ("Import a spreadsheet", "Importuj arkusz"),
    "setup.tab.manual": ("Add manually", "Dodaj ręcznie"),
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
    "setup.tasks.lead": (
        "List the tasks with their length in working days, the people of each role they need and "
        "the tasks they wait for.",
        "Wypisz zadania z czasem trwania w dniach roboczych, liczbą osób z każdej roli i "
        "zadaniami, na które czekają.",
    ),
    "setup.tasks.caption": ("Tasks", "Zadania"),
    "setup.tasks.name": ("Task", "Zadanie"),
    "setup.tasks.days": ("Days", "Dni"),
    "setup.tasks.people": ("{role} (people)", "{role} (osoby)"),
    "setup.tasks.after": ("After tasks (no.)", "Po zadaniach (nr)"),
    "setup.tasks.optional": ("Optional", "Opcjonalne"),
    "setup.tasks.name_of": ("Name of task {n}", "Nazwa zadania {n}"),
    "setup.tasks.days_of": ("Working days of task {n}", "Dni robocze zadania {n}"),
    "setup.tasks.people_of": ("{role}: people in task {n}", "{role}: liczba osób w zadaniu {n}"),
    "setup.tasks.after_of": (
        "Task {n} comes after the tasks numbered",
        "Zadanie {n} następuje po zadaniach o numerach",
    ),
    "setup.tasks.optional_of": ("Task {n} is optional", "Zadanie {n} jest opcjonalne"),
    "setup.tasks.after_hint": (
        "“After tasks”: the numbers of the tasks that must be finished first, e.g. “1, 3”. An "
        "optional task can be dropped if time runs short; no task may wait for it.",
        "„Po zadaniach”: numery zadań, które muszą się najpierw zakończyć, np. „1, 3”. Z zadania "
        "opcjonalnego można zrezygnować, gdy brakuje czasu; żadne zadanie nie może na nie "
        "czekać.",
    ),
    "setup.tasks.empty": (
        "No tasks yet. Add them here, import a spreadsheet or describe the project.",
        "Nie ma jeszcze zadań. Dodaj je tutaj, zaimportuj arkusz albo opisz projekt.",
    ),
    "setup.tasks.add": ("Add a task", "Dodaj zadanie"),
    "form.fix_below": (
        "Please correct the fields marked below.",
        "Popraw zaznaczone poniżej pola.",
    ),
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
    "overview.calculating": ("Calculating the forecast…", "Obliczam prognozę…"),
    "overview.ask": ("Ask Sentinel", "Zapytaj Sentinela"),
    "overview.checkin": ("Check-in", "Raport statusu"),
    "overview.working_title": ("Sentinel is working", "Sentinel pracuje"),
    "overview.pending_title": ("Waiting for your decision", "Czeka na Twoją decyzję"),
    "overview.auto_title": ("Changed automatically", "Zmienione automatycznie"),
    "overview.auto_text": (
        "Sentinel applied this on {date} because your settings allow it.",
        "Sentinel zastosował to {date}, bo pozwalają na to Twoje ustawienia.",
    ),
    "overview.details": ("Details", "Szczegóły"),
    "overview.undo": ("Undo", "Cofnij"),
    "overview.threats_title": ("What threatens the deadline", "Co zagraża terminowi"),
    "overview.drivers_wait": ("Waiting for the forecast…", "Czekam na prognozę…"),
    "overview.away_badge": ("Away", "Nieobecność"),
    "overview.away_back": (
        "{person}: away, back on {date}.",
        "{person}: nieobecność, powrót {date}.",
    ),
    "overview.away_open": (
        "{person}: away, return date not known yet.",
        "{person}: nieobecność, data powrotu jeszcze nieznana.",
    ),
    "overview.late_badge": ("Late start", "Opóźniony start"),
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
    "overview.chance": ("Chance of meeting the deadline:", "Szansa na dotrzymanie terminu:"),
    "overview.no_deadline": (
        "No deadline is set, so there is no chance to show.",
        "Nie ustawiono terminu, więc nie ma szansy do pokazania.",
    ),
    "overview.set_deadline": ("Set a deadline", "Ustaw termin"),
    "overview.deadline": ("Deadline", "Termin"),
    "overview.likely": ("Most likely finish", "Najbardziej prawdopodobny koniec"),
    "overview.bad_case": ("Bad case (1 in 10 later)", "Zły scenariusz (1 na 10 później)"),
    "overview.spent": ("Spent so far", "Wydano do tej pory"),
    "overview.spent_of": ("{spent} of {budget}", "{spent} z {budget}"),
    "overview.expected_cost": ("Expected total cost", "Oczekiwany koszt całkowity"),
    "overview.within_budget": (
        "{p} chance to stay within the budget",
        "{p} szansy na zmieszczenie się w budżecie",
    ),
    "overview.forecast_note": (
        "Based on {futures} simulated futures of the project from its current status.",
        "Na podstawie {futures} symulowanych scenariuszy projektu od obecnego stanu.",
    ),
    "overview.driver": (
        "“{task}” is on the critical path in {count} of 10 simulated futures.",
        "„{task}” leży na ścieżce krytycznej w {count} na 10 symulowanych scenariuszy.",
    ),
    "overview.no_drivers": ("No single task stands out.", "Żadne zadanie się nie wyróżnia."),
    "overview.driver_all": (
        "“{task}” is on the critical path in every simulated future.",
        "„{task}” leży na ścieżce krytycznej w każdym symulowanym scenariuszu.",
    ),
    "overview.drivers_note": (
        "The critical path is the chain of tasks that sets the finish date: any delay on it "
        "delays the project.",
        "Ścieżka krytyczna to łańcuch zadań wyznaczający datę zakończenia: każde opóźnienie na "
        "niej opóźnia projekt.",
    ),
    "rec.rough": (
        "“Without a change” was set aside early and simulated fewer times, so its chance is a "
        "rougher figure than the forecast on the overview.",
        "Wariant „bez zmian” odrzucono na wstępie i zasymulowano rzadziej, więc jego szansa jest "
        "mniej dokładna niż prognoza na stronie przeglądu.",
    ),
    "overview.checked_title": ("Sentinel checked the new status", "Sentinel sprawdził nowy stan"),
    "overview.checked": (
        "No change is needed: the plan is still the best.",
        "Zmiana nie jest potrzebna: plan wciąż jest najlepszy.",
    ),
    "chart.title": ("Plan and progress of the tasks", "Plan i postęp zadań"),
    "chart.desc": (
        "{tasks} tasks: {done} done, {running} in progress. Status at the end of {status}.",
        "Zadania: {tasks}; gotowe: {done}, w toku: {running}. Stan na koniec dnia {status}.",
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
    "chart.tip_original": ("{task}: original plan", "{task}: plan początkowy"),
    "chart.new": ("(new)", "(nowe)"),
    "chart.status": ("Status {date}", "Stan {date}"),
    "chart.deadline": ("Deadline {date}", "Termin {date}"),
    "chart.today": ("Today", "Dziś"),
    "chart.legend": ("Legend", "Legenda"),
    "chart.legend.original": ("Original plan", "Plan początkowy"),
    "chart.legend.done": ("Done", "Gotowe"),
    "chart.legend.running": ("In progress (outline: work left)", "W toku (obrys: pozostała praca)"),
    "chart.legend.planned": ("Planned", "Zaplanowane"),
    "chart.legend.away": ("Someone away", "Nieobecność"),
    "chart.as_table": ("Show the tasks as a table", "Pokaż zadania w tabeli"),
    "chart.col.task": ("Task", "Zadanie"),
    "chart.col.state": ("State", "Stan"),
    "chart.col.dates": ("Dates", "Daty"),
    "chart.since": ("since {date}", "od {date}"),
    # ---- check-in
    "checkin.title": ("Check-in", "Raport statusu"),
    "checkin.not_saved": ("The check-in was not saved:", "Raport nie został zapisany:"),
    "checkin.when": ("When", "Kiedy"),
    "checkin.date": ("Status at the end of", "Stan na koniec dnia"),
    "checkin.date_hint": (
        "Report what is true at the end of this day.",
        "Zgłoś stan na koniec tego dnia.",
    ),
    "checkin.last": ("The last check-in was for {date}.", "Ostatni raport dotyczył dnia {date}."),
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
    "checkin.away_title": ("Someone is away", "Ktoś jest nieobecny"),
    "checkin.away_hint": (
        "Only when, never why: there is no place for reasons.",
        "Tylko kiedy, nigdy dlaczego: nie ma tu miejsca na powody.",
    ),
    "checkin.away_add": ("Add an absence", "Dodaj nieobecność"),
    "checkin.away.who": ("Person", "Osoba"),
    "checkin.away.choose": ("Choose a person", "Wybierz osobę"),
    "checkin.away.from": ("Away from", "Nieobecność od"),
    "checkin.away.back": ("Back on (if known)", "Powrót (jeśli wiadomo)"),
    "checkin.grow_title": ("A task grows", "Zadanie się wydłuża"),
    "checkin.grow_hint": (
        "A task in progress needs more working days than planned.",
        "Zadanie w toku potrzebuje więcej dni roboczych, niż planowano.",
    ),
    "checkin.grow_add": ("Add a growing task", "Dodaj wydłużone zadanie"),
    "checkin.grow.task": ("Task", "Zadanie"),
    "checkin.grow.choose": ("Choose a task in progress", "Wybierz zadanie w toku"),
    "checkin.grow.days": ("Extra working days", "Dodatkowe dni robocze"),
    "checkin.grow_none": ("No task is in progress.", "Żadne zadanie nie jest w toku."),
    "checkin.new_title": ("New task", "Nowe zadanie"),
    "checkin.new_add": ("Add a new task", "Dodaj nowe zadanie"),
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
    "checkin.message_title": ("Or write a message", "Albo napisz wiadomość"),
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
    "checkin.message_read": ("Read the message", "Odczytaj wiadomość"),
    "checkin.message_nothing": (
        "The AI found nothing to report in this message.",
        "AI nie znalazło w tej wiadomości nic do zgłoszenia.",
    ),
    "checkin.message_found": ("The AI found:", "AI znalazło:"),
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
    "rec.from": ("Recommendation for {date}", "Rekomendacja na {date}"),
    "rec.alt_noop": ("No change (keep the plan)", "Bez zmian (zachowaj plan)"),
    "rec.can_wait": ("can wait", "może poczekać"),
    "rec.effect": ("Effect compared with no change", "Efekt w porównaniu z brakiem zmian"),
    "rec.needs_approval": (
        "This needs your approval because it",
        "To wymaga Twojej zgody, ponieważ",
    ),
    "rec.needs_approval_short": ("Needs your approval:", "Wymaga Twojej zgody:"),
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
    "rec.why": ("Why", "Dlaczego"),
    "rec.ai_title": ("In other words (AI):", "Innymi słowy (AI):"),
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
    "rec.chosen": ("recommended", "polecana"),
    "rec.dropped": ("(set aside early)", "(odrzucona na wstępie)"),
    "rec.alt_note": (
        "Every option was tried on the same simulated futures. Options set aside early were "
        "clearly worse in the first ones, so fewer futures were simulated for them.",
        "Każdą możliwość sprawdzono na tych samych symulowanych scenariuszach. Możliwości "
        "odrzucone na wstępie wypadły wyraźnie gorzej w pierwszych z nich, więc zasymulowano dla "
        "nich mniej scenariuszy.",
    ),
    "rec.reject": ("Reject", "Odrzuć"),
    "rec.later": ("Decide later", "Zdecyduj później"),
    "rec.approve": ("Approve", "Zatwierdź"),
    "rec.back": ("Back to the overview", "Wróć do przeglądu"),
    "rec.open": ("See the recommendation", "Zobacz rekomendację"),
    "chip.chance": ("Chance of meeting the deadline", "Szansa na dotrzymanie terminu"),
    "chip.from_to": ("{before} → {after}", "{before} → {after}"),
    "chip.finish": ("Expected finish", "Oczekiwany koniec"),
    "chip.cost": ("Cost", "Koszt"),
    "chip.moved": ("Dates moved", "Przesunięte terminy"),
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
        "Sentinel compared {options} options on simulated futures; none does better than keeping "
        "the plan, with a {p} chance of meeting the deadline.",
        "Sentinel porównał możliwości ({options}) na symulowanych scenariuszach; żadna nie "
        "wypada lepiej niż zachowanie planu, przy którym szansa na dotrzymanie terminu wynosi "
        "{p}.",
    ),
    "why.without": (
        "Without a change, the chance of meeting the deadline is {p}.",
        "Bez zmian szansa na dotrzymanie terminu wynosi {p}.",
    ),
    "why.with": (
        "Sentinel tried {options} options, each on up to {futures} simulated futures; with this "
        "one the chance is {p}.",
        "Sentinel sprawdził możliwości ({options}), każdą na maksymalnie {futures} symulowanych "
        "scenariuszach; z tą szansa wynosi {p}.",
    ),
    "why.delay": (
        "The expected delay is {days} working days.",
        "Oczekiwane opóźnienie w dniach roboczych: {days}.",
    ),
    "why.reason": ("It was chosen because {reason}.", "Wybrano ją, ponieważ {reason}."),
    "why.runner": (
        "The next best option reaches {p}: {title}.",
        "Następna w kolejności możliwość osiąga {p}: {title}.",
    ),
    # ---- history
    "history.title": ("History", "Historia"),
    "history.filter": ("Show", "Pokaż"),
    "history.show.all": ("Everything", "Wszystko"),
    "history.show.checkins": ("Check-ins", "Raporty statusu"),
    "history.show.recommendations": ("Recommendations and decisions", "Rekomendacje i decyzje"),
    "history.show.changes": ("Project changes", "Zmiany projektu"),
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
    "history.plan": ("Plan created: finish on {date}", "Utworzono plan: zakończenie {date}"),
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
    # ---- project settings
    "psettings.title": ("Project settings", "Ustawienia projektu"),
    "psettings.basics": ("Name, deadline and budget", "Nazwa, termin i budżet"),
    "psettings.budget_hint": (
        "Leave empty to use the estimate from the tasks ({budget}).",
        "Pozostaw puste, aby użyć szacunku na podstawie zadań ({budget}).",
    ),
    "psettings.autonomy": (
        "What may Sentinel do without asking you?",
        "Co Sentinel może zrobić bez pytania Cię o zgodę?",
    ),
    "autonomy.0": ("Only advise me", "Tylko doradzaj"),
    "autonomy.0.hint": (
        "Every change waits for your approval.",
        "Każda zmiana czeka na Twoją zgodę.",
    ),
    "autonomy.1": ("May shift dates", "Może przesuwać terminy"),
    "autonomy.1.hint": (
        "Moving task dates without changing their order happens automatically; every other "
        "change waits for you.",
        "Przesunięcie terminów zadań bez zmiany kolejności dzieje się automatycznie; każda inna "
        "zmiana czeka na Ciebie.",
    ),
    "autonomy.2": ("May re-plan the order", "Może zmieniać kolejność zadań"),
    "autonomy.2.hint": (
        "Changing the order of tasks also happens automatically; changes that affect people, "
        "money or scope wait for you (recommended).",
        "Także zmiana kolejności zadań dzieje się automatycznie; zmiany dotyczące ludzi, "
        "pieniędzy lub zakresu czekają na Ciebie (zalecane).",
    ),
    "autonomy.3": ("May also add people and substitutes", "Może też dodawać osoby i zastępstwa"),
    "autonomy.3.hint": (
        "Substitutes and temporary people are also added automatically; dropping a task always "
        "waits for you.",
        "Także zastępstwa i osoby tymczasowe są dodawane automatycznie; rezygnacja z zadania "
        "zawsze czeka na Ciebie.",
    ),
    "psettings.presets": ("Estimates and turbulence", "Szacunki i burzliwość"),
    "psettings.costs": ("Daily cost of one person", "Dzienny koszt jednej osoby"),
    "psettings.costs_hint": (
        "In your own unit, e.g. a currency. A temporary person costs one and a half times as much.",
        "W Twojej jednostce, np. walucie. Osoba tymczasowa kosztuje półtora raza więcej.",
    ),
    "psettings.cost_of": ("Daily cost: {role}", "Koszt dzienny: {role}"),
    "psettings.ai": ("AI features", "Funkcje AI"),
    "psettings.ai_proposals": (
        "Let the AI suggest extra options for Sentinel to test",
        "Pozwól AI proponować dodatkowe możliwości do sprawdzenia przez Sentinela",
    ),
    "psettings.export": ("Download", "Pobierz"),
    "psettings.export_plan": (
        "The plan with progress (CSV, for spreadsheets)",
        "Plan z postępem (CSV, do arkusza)",
    ),
    "psettings.export_project": (
        "The whole project (JSON file, to import later)",
        "Cały projekt (plik JSON do późniejszego importu)",
    ),
    "psettings.report": ("Prepare the detailed report", "Przygotuj szczegółowy raport"),
    "psettings.delete": ("Delete the project", "Usuń projekt"),
    "psettings.delete_text": (
        "Deleting removes the project and its whole history for good.",
        "Usunięcie trwale kasuje projekt i całą jego historię.",
    ),
    "psettings.delete_button": ("Delete the project…", "Usuń projekt…"),
    "delete.title": ("Delete the project?", "Usunąć projekt?"),
    "delete.text": (
        "“{name}” and its whole history will be deleted for good. This cannot be undone.",
        "„{name}” i cała jego historia zostaną trwale usunięte. Tego nie można cofnąć.",
    ),
    "delete.confirm": ("Delete for good", "Usuń trwale"),
    # ---- simulator
    "sim.title": ("Simulator", "Symulator"),
    "sim.lead": (
        "Watch Sentinel manage an example project day by day — absences, growing tasks and new "
        "work included — and compare it with nobody reacting to the same events.",
        "Zobacz, jak Sentinel prowadzi przykładowy projekt dzień po dniu — z nieobecnościami, "
        "wydłużającymi się zadaniami i nową pracą — i porównaj to z brakiem reakcji na te same "
        "zdarzenia.",
    ),
    "sim.unavailable": (
        "The example projects are not installed on this server.",
        "Na tym serwerze nie zainstalowano przykładowych projektów.",
    ),
    "sim.example": ("Example project", "Przykładowy projekt"),
    "sim.size.j30": ("Small example project (30 tasks)", "Mały przykładowy projekt (30 zadań)"),
    "sim.size.j60": ("Medium example project (60 tasks)", "Średni przykładowy projekt (60 zadań)"),
    "sim.example_hint.j30": (
        "30 tasks and 4 roles. Running it to the end takes about half a minute.",
        "30 zadań i 4 role. Symulacja do końca trwa około pół minuty.",
    ),
    "sim.example_hint.j60": (
        "60 tasks and 4 roles. Running it to the end takes a minute or two.",
        "60 zadań i 4 role. Symulacja do końca trwa minutę lub dwie.",
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
    "sim.original_finish": ("Original plan finishes", "Koniec według planu początkowego"),
    "sim.days_done": ("Days simulated", "Zasymulowane dni"),
    "sim.budget": ("Budget", "Budżet"),
    "sim.tasks_done": ("{done} of {total} tasks done", "Gotowe zadania: {done} z {total}"),
    "sim.cost_so_far": (
        "Cost so far: {cost} ({share} of the budget)",
        "Koszt do tej pory: {cost} ({share} budżetu)",
    ),
    "sim.advance_by": ("Simulate the next:", "Zasymuluj kolejne:"),
    "sim.days.1": ("1 day", "1 dzień"),
    "sim.days.5": ("5 days", "5 dni"),
    "sim.days.10": ("10 days", "10 dni"),
    "sim.days.end": ("To the end", "Do końca"),
    "sim.compare_title": ("How it ended", "Jak się skończyło"),
    "sim.col.measure": ("Measure", "Miara"),
    "sim.col.finish": ("Finish", "Zakończenie"),
    "sim.col.on_time": ("Deadline", "Termin"),
    "sim.col.cost": ("Cost (share of the budget)", "Koszt (część budżetu)"),
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
        "Both finished late (working days of delay: with Sentinel {main}, with nobody reacting "
        "{other}).",
        "Oba przebiegi zakończyły się po terminie (dni robocze opóźnienia: z Sentinelem {main}, "
        "bez reakcji {other}).",
    ),
    "sim.delete": ("Delete this simulation", "Usuń tę symulację"),
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
        if value is None:
            return "—"
        weekday = WEEKDAYS[self.lang][value.weekday()]
        month = MONTHS[self.lang][value.month - 1]
        text = f"{weekday} {value.day}{NBSP}{month}"
        return f"{text} {value.year}" if value.year != Day.today().year else text

    def day_month(self, value: Day) -> str:
        return f"{value.day}{NBSP}{MONTHS[self.lang][value.month - 1]}"

    def moment(self, value: datetime) -> str:
        """A point in time in the server's time zone: "Mon 14 Mar, 14:05"."""
        local = value.astimezone()
        return f"{self.date(local.date())}, {local:%H:%M}"

    def pct(self, value: float | None) -> str:
        """A probability as a whole percentage; never "0 %" or "100 %" unless it is exact."""
        if value is None or math.isnan(value):
            return "—"
        percent = math.floor(100 * value + 0.5)
        if value > 0 and percent == 0:
            return f"<{NBSP}1{NBSP}%"
        if value < 1 and percent == 100:
            return f">{NBSP}99{NBSP}%"
        return f"{percent}{NBSP}%"

    def decimal(self, value: float) -> str:
        """A number with at most one decimal (a decimal comma in Polish)."""
        text = f"{value:.1f}"
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

    def signed_money(self, value: float) -> str:
        number = math.floor(abs(value) + 0.5)
        if number == 0:
            return "±0"
        return ("+" if value > 0 else MINUS) + self.money(abs(value))
