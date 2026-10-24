"""User-facing messages of the application in English and Polish (spec section 11.2).

Every issue and error has a code; `render` formats its message in a language with the issue's
parameters. Messages speak to a project manager: task and person names, dates, no model jargon.
"""

from collections.abc import Mapping

from sentinel.app.models import Language

LANGUAGES: tuple[Language, ...] = ("en", "pl")

MESSAGES: Mapping[Language, Mapping[str, str]] = {
    "en": {
        # project definition (spec section 11.2)
        "empty_project_name": "The project needs a name.",
        "no_tasks": "The project has no tasks yet.",
        "duplicate_person_key": "The person id {key} is used twice.",
        "empty_person_name": "Person {key} needs a name.",
        "duplicate_person_name": "Two people are called “{name}”; names must be unique.",
        "empty_role": "{person} needs a role.",
        "duplicate_role_cost": "Two daily costs are set for the role {role}.",
        "unused_role_cost": "A daily cost is set for the role {role}, but nobody has that role.",
        "duplicate_task_key": "The task id {key} is used twice.",
        "empty_task_name": "Task {key} needs a name.",
        "duplicate_task_name": "Two tasks are called “{name}”; task names must be unique.",
        "duration_too_short": "“{task}” must take at least one working day (it has {duration}).",
        "duplicate_crew_role": "The crew of “{task}” lists the role {role} twice.",
        "negative_crew": "“{task}” cannot need a negative number of {role} people.",
        "unknown_role": "“{task}” needs the role {role}, but nobody in the team has it.",
        "crew_above_team": "“{task}” needs {count} × {role}, but the team has only {capacity}.",
        "self_predecessor": "“{task}” cannot come after itself.",
        "unknown_predecessor": "“{task}” comes after {predecessor}, which is not a task of this "
        "project.",
        "cycle": "These tasks wait for each other in a circle: {cycle}.",
        "optional_with_successors": "“{task}” is optional, but “{successor}” depends on it; only "
        "a task that nothing depends on can be dropped.",
        "deadline_before_start": "The deadline {deadline} is before the project starts ({start}).",
        "deadline_before_critical_path": "The deadline {deadline} is before the earliest "
        "possible finish date, {earliest}.",
        "structure_frozen": "Tracking has started, so the team, the tasks, their estimates, crews "
        "and dependencies can no longer change; report changes at a check-in.",
        # baseline plan and check-ins (spec section 11.3)
        "no_baseline": "Build the plan first.",
        "project_finished": "All tasks are done: the project is finished.",
        "no_deadline": "Set a deadline to see the chance of finishing on time and to get "
        "recommendations.",
        "checkin_out_of_order": "Check-ins must follow each other in time; the last one was for "
        "{date}.",
        "duplicate_report": "Task {task} is reported twice.",
        "unknown_task": "There is no task {task}.",
        "unknown_person": "There is no person {person}.",
        "task_removed": "“{task}” was dropped from the project.",
        "already_started": "“{task}” was already reported as started on {date}.",
        "already_done": "“{task}” was already reported as done on {date}.",
        "percent_required": "Give the share done of “{task}” (0 to 99 %).",
        "percent_range": "The share done of “{task}” must be from 0 to below 100 % (it is "
        "{percent} %); report a finished task as done.",
        "finish_required": "Give the finish date of “{task}”.",
        "finish_after_checkin": "“{task}” cannot have finished on {finish}, after the check-in "
        "date {date}.",
        "start_after_checkin": "“{task}” cannot have started on {start}, after the check-in date "
        "{date}.",
        "finish_before_start": "“{task}” cannot finish on {finish} before it starts on {start}.",
        "start_before_project": "“{task}” cannot start on {start}, before the project starts "
        "({project_start}).",
        "no_work_before_start": "No work on “{task}” can be reported before the project starts.",
        "predecessor_not_done": "“{task}” cannot have started: “{predecessor}” is not done.",
        "start_before_predecessor": "“{task}” cannot start on {start}: “{predecessor}” finished "
        "only on {finish}.",
        "progress_below_change": "“{task}” had {minimum} % done when more work was reported; its "
        "share done cannot be lower now.",
        "no_crew_available": "There are not enough free people with the role {role} on {date} to "
        "start “{task}” (it needs {count}, {free} are free); name the crew.",
        "crew_unknown_member": "There is no person {person} for the crew.",
        "crew_member_busy": "{person} is in the crew of “{other}” on {date}.",
        "crew_not_hired": "{person} is not hired on {date}.",
        "crew_wrong_roles": "The crew of “{task}” must be {expected}.",
        "absence_return_before_start": "The return date of {person} must be after the first day "
        "of the absence.",
        "absence_overlap": "{person} has another absence at that time (from {date}).",
        "increase_not_in_progress": "More work can be reported only for a task in progress; "
        "“{task}” is {state}.",
        "increase_amount": "Give either the extra working days or the factor for “{task}”.",
        "increase_days_positive": "The extra working days of “{task}” must be more than 0.",
        "increase_factor_above_one": "The factor of “{task}” must be more than 1.",
        "new_task_name_used": "A task called “{name}” exists already.",
        "new_task_key_used": "The task id {key} is used already.",
        "new_task_before_started": "“{name}” cannot come before “{before}”, which has already "
        "started.",
        "new_task_after_invalid": "“{name}” cannot come after “{after}”, which itself depends on "
        "“{before}”.",
        "new_task_optional_before": "“{name}” is optional, so it cannot come before another task.",
        "state_not_started": "not started",
        "state_done": "done",
        "state_removed": "dropped",
        # recommendations and decisions (spec section 11.5)
        "recommendation_not_found": "There is no such recommendation.",
        "recommendation_closed": "This recommendation is no longer open ({status}).",
        "nothing_to_decide": "This recommendation keeps the plan; there is nothing to approve.",
        "action_discarded": "The action is no longer possible ({reason}); a new recommendation "
        "follows.",
        # simulator (spec section 11.6)
        "psplib_missing": "The simulator needs the PSPLIB data on the server "
        "(scripts/fetch_psplib.py).",
        "unknown_instance": "There is no simulator project {instance}.",
        "unknown_policy": "There is no policy {policy}.",
        "simulation_finished": "The simulation has finished.",
        "not_a_simulator": "This is not a simulator project.",
        "not_a_live_project": "This is a simulator project; it has no check-ins.",
        "simulation_running": "Both runs must finish before the cockpit can be written.",
        # actions, statuses and reasons shown with recommendations (spec section 11.5)
        "action_noop": "Keep the plan",
        "action_shift": "move the remaining tasks, keeping their order",
        "action_reseq_m": "re-plan the remaining tasks for the earliest finish",
        "action_reseq_s": "re-plan the remaining tasks with as few changes as possible",
        "action_subst": "let {workers} take over for the absent crew of “{task}”",
        "action_overtime": "hire {count} temporary {role} for {days} working days (until {until})",
        "action_descope": "drop the optional task “{task}”",
        "action_then": ", then ",
        "reason_needs_met": "no action is needed: the plan is on track",
        "reason_only_candidate": "no other action was possible",
        "reason_racing": "the other actions were clearly worse in the first simulated futures",
        "reason_on_time": "it gives the best chance to finish on time",
        "reason_tardiness": "it gives the fewest expected days of delay",
        "reason_scope": "it loses the least scope",
        "reason_budget": "it has the lowest expected cost",
        "reason_stability": "it changes the plan the least",
        "reason_level": "it needs the least approval",
        "reason_order": "the actions tie on everything, so the simplest one wins",
        "reason_utility": "it has the best combined score",
        "reason_approved": "the action was approved",
        "reason_idle_events": "nothing changed for the crews",
        "reason_awaiting_approval": "an action is waiting for approval",
        "status_none": "no action needed",
        "status_auto": "applied automatically",
        "status_open": "waiting for your decision",
        "status_later": "postponed",
        "status_approved": "approved and applied",
        "status_rejected": "rejected",
        "status_discarded": "no longer possible",
        "status_superseded": "replaced by a newer recommendation",
        "progress_not_started": "not started",
        "progress_in_progress": "in progress",
        "progress_paused": "paused (the crew is absent)",
        "progress_done": "done",
        "progress_removed": "dropped",
        # the cockpit of a live project (WP8 style)
        "cockpit_title": "Project cockpit",
        "cockpit_subtitle": "Status at the end of {date}; plan, forecasts and Sentinel's "
        "recommendations.",
        "cockpit_plan": "plan",
        "cockpit_deadline": "deadline",
        "cockpit_today": "today",
        "cockpit_kpis": "Key figures",
        "cockpit_gantt": "Plan and progress",
        "cockpit_gantt_note": "Grey: the baseline plan. Coloured: the work reported so far "
        "(striped while part of the crew was absent, outlined while the whole crew was absent).",
        "cockpit_risk": "Chance to finish on time",
        "cockpit_risk_note": "At every recommendation: P(on time) without action and the band of "
        "the finish day (10–90 %) on the simulated futures Sentinel decided on.",
        "cockpit_log": "Recommendations",
        "cockpit_col_date": "Date",
        "cockpit_col_action": "Recommended action",
        "cockpit_col_p": "P(on time)",
        "cockpit_col_reason": "Why",
        "cockpit_col_status": "Status",
        "cockpit_col_explanation": "Explanation",
        "cockpit_kpi_plan": "Finish of the baseline plan",
        "cockpit_kpi_deadline": "Deadline",
        "cockpit_kpi_tasks": "Tasks done",
        "cockpit_kpi_cost": "Cost so far / budget",
        "cockpit_kpi_forecast": "Expected finish without action",
        "cockpit_kpi_p": "P(on time) without action",
        "cockpit_kpi_actions": "Actions applied",
        "cockpit_kpi_temps": "Temporary workers hired",
        "cockpit_llm_invalid": "The language model gave no valid explanation.",
        "cockpit_badge_template": "template explanation",
        "cockpit_badge_faithful": "{model}: faithful",
        "cockpit_badge_unfaithful": "{model}: not faithful",
        "cockpit_badge_invalid": "{model}: no valid answer",
        "cockpit_provenance": "Provenance",
        "cockpit_p_software": "Software",
        "cockpit_p_settings": "Settings",
        "cockpit_p_note": "Note",
        "cockpit_p_note_text": "Every number comes from the project's event log and its seed; "
        "the same log gives the same page.",
        # import and export
        "csv_empty": "The file is empty.",
        "csv_encoding": "The file is not UTF-8 text.",
        "csv_missing_column": "The file has no column “{column}”.",
        "csv_number": "Row {row}: {column} must be a whole number (it is “{value}”).",
        "csv_decimal": "Row {row}: {column} must be a number (it is “{value}”).",
        "csv_flag": "Row {row}: {column} must be yes or no (it is “{value}”).",
        "csv_crew": "Row {row}: the crew “{value}” must look like “Backend developer=2; Tester=1”.",
        "csv_key": "Row {row}: the id “{value}” may hold only letters, digits, “_”, “-” and “.”.",
        "csv_required": "Row {row}: {column} is required.",
        "csv_too_long": "Row {row}: {column} is longer than 120 characters.",
        "csv_row": "Row {row}: {message}",
        "json_invalid": "The file is not a project exported by Sentinel ({detail}).",
        "date_invalid": "{field} must be a date like 2026-11-02 (it is “{value}”).",
        # extraction from text (WP6)
        "extraction_failed": "No usable plan could be read from the text ({detail}).",
        "extraction_issues": "The plan read from the text still has {count} problems; check it "
        "before saving.",
        "text_empty": "Paste a project description first.",
        # API and demo (ADR-0024)
        "not_found": "Not found.",
        "project_not_found": "There is no such project.",
        "job_not_found": "There is no such job.",
        "job_not_done": "The job has not finished yet.",
        "invalid_request": "The request is not valid.",
        "field_required": "{field} is required.",
        "field_invalid": "{field} is not valid: {detail}.",
        "csrf_failed": "The page has expired; reload it and try again.",
        "rate_limited": "Too many requests; please wait a minute.",
        "too_large": "The upload is larger than {limit} kB.",
        "limit_projects": "A demo session can have at most {limit} projects.",
        "limit_tasks": "A demo project can have at most {limit} tasks.",
        "limit_days": "The demo simulator advances at most {limit} days at a time.",
        "limit_jobs": "Please wait until the running computation has finished.",
        "llm_disabled": "No language model is set up.",
        "llm_cap": "The daily limit of language-model calls is reached; try again tomorrow.",
        "llm_failed": "The language model did not answer ({detail}).",
        "demo_forbidden": "This is not available in the demo.",
        "settings_invalid": "The language-model settings are not valid: {detail}.",
        "internal_error": "Something went wrong on the server; the error was logged.",
    },
    "pl": {
        "empty_project_name": "Projekt musi mieć nazwę.",
        "no_tasks": "Projekt nie ma jeszcze zadań.",
        "duplicate_person_key": "Identyfikator osoby {key} występuje dwa razy.",
        "empty_person_name": "Osoba {key} musi mieć imię i nazwisko.",
        "duplicate_person_name": "Dwie osoby nazywają się „{name}”; nazwy osób muszą być unikalne.",
        "empty_role": "{person} musi mieć rolę.",
        "duplicate_role_cost": "Dla roli {role} podano dwa koszty dzienne.",
        "unused_role_cost": "Podano koszt dzienny roli {role}, ale nikt nie ma tej roli.",
        "duplicate_task_key": "Identyfikator zadania {key} występuje dwa razy.",
        "empty_task_name": "Zadanie {key} musi mieć nazwę.",
        "duplicate_task_name": "Dwa zadania nazywają się „{name}”; nazwy zadań muszą być unikalne.",
        "duration_too_short": "„{task}” musi trwać co najmniej jeden dzień roboczy (podano "
        "{duration}).",
        "duplicate_crew_role": "Skład zespołu zadania „{task}” wymienia rolę {role} dwa razy.",
        "negative_crew": "„{task}” nie może potrzebować ujemnej liczby osób z rolą {role}.",
        "unknown_role": "„{task}” potrzebuje roli {role}, ale nikt w zespole jej nie ma.",
        "crew_above_team": "„{task}” potrzebuje {count} × {role}, a zespół ma tylko {capacity}.",
        "self_predecessor": "„{task}” nie może następować po samym sobie.",
        "unknown_predecessor": "„{task}” następuje po {predecessor}, a takiego zadania nie ma w "
        "projekcie.",
        "cycle": "Te zadania czekają na siebie nawzajem w kółko: {cycle}.",
        "optional_with_successors": "„{task}” jest opcjonalne, ale zależy od niego „{successor}”; "
        "zrezygnować można tylko z zadania, od którego nic nie zależy.",
        "deadline_before_start": "Termin {deadline} wypada przed rozpoczęciem projektu ({start}).",
        "deadline_before_critical_path": "Termin {deadline} wypada przed najwcześniejszą możliwą "
        "datą zakończenia, {earliest}.",
        "structure_frozen": "Śledzenie postępu już się zaczęło, więc zespołu, zadań, ich "
        "szacunków, składów i zależności nie można już zmieniać; zmiany zgłaszaj w raporcie "
        "statusu.",
        "no_baseline": "Najpierw zbuduj plan.",
        "project_finished": "Wszystkie zadania są gotowe: projekt jest zakończony.",
        "no_deadline": "Ustaw termin, aby zobaczyć szansę na zakończenie w terminie i otrzymywać "
        "rekomendacje.",
        "checkin_out_of_order": "Raporty statusu muszą następować po sobie w czasie; ostatni "
        "dotyczył dnia {date}.",
        "duplicate_report": "Zadanie {task} zgłoszono dwa razy.",
        "unknown_task": "Nie ma zadania {task}.",
        "unknown_person": "Nie ma osoby {person}.",
        "task_removed": "Z zadania „{task}” zrezygnowano.",
        "already_started": "„{task}” zgłoszono już jako rozpoczęte {date}.",
        "already_done": "„{task}” zgłoszono już jako gotowe {date}.",
        "percent_required": "Podaj, jaka część zadania „{task}” jest wykonana (od 0 do 99 %).",
        "percent_range": "Wykonana część zadania „{task}” musi wynosić od 0 do mniej niż 100 % "
        "(podano {percent} %); ukończone zadanie zgłoś jako gotowe.",
        "finish_required": "Podaj datę zakończenia zadania „{task}”.",
        "finish_after_checkin": "„{task}” nie mogło zakończyć się {finish}, po dacie raportu "
        "{date}.",
        "start_after_checkin": "„{task}” nie mogło rozpocząć się {start}, po dacie raportu {date}.",
        "finish_before_start": "„{task}” nie może zakończyć się {finish}, zanim się rozpocznie "
        "{start}.",
        "start_before_project": "„{task}” nie może rozpocząć się {start}, przed rozpoczęciem "
        "projektu ({project_start}).",
        "no_work_before_start": "Przed rozpoczęciem projektu nie można zgłosić pracy nad „{task}”.",
        "predecessor_not_done": "„{task}” nie mogło się rozpocząć: „{predecessor}” nie jest "
        "gotowe.",
        "start_before_predecessor": "„{task}” nie może rozpocząć się {start}: „{predecessor}” "
        "zakończyło się dopiero {finish}.",
        "progress_below_change": "Zadanie „{task}” miało {minimum} % wykonania, gdy zgłoszono "
        "dodatkową pracę; wykonana część nie może być teraz mniejsza.",
        "no_crew_available": "Dnia {date} brakuje wolnych osób z rolą {role}, aby rozpocząć "
        "„{task}” (potrzeba {count}, wolnych jest {free}); wskaż skład zespołu.",
        "crew_unknown_member": "Nie ma osoby {person}, którą można by przypisać do zespołu.",
        "crew_member_busy": "{person} pracuje {date} w zespole zadania „{other}”.",
        "crew_not_hired": "{person} nie jest zatrudniony(-a) dnia {date}.",
        "crew_wrong_roles": "Zespół zadania „{task}” musi składać się z: {expected}.",
        "absence_return_before_start": "Data powrotu osoby {person} musi być późniejsza niż "
        "pierwszy dzień nieobecności.",
        "absence_overlap": "{person} ma w tym czasie inną nieobecność (od {date}).",
        "increase_not_in_progress": "Dodatkową pracę można zgłosić tylko dla zadania w toku; "
        "„{task}” jest {state}.",
        "increase_amount": "Podaj dla zadania „{task}” albo liczbę dodatkowych dni roboczych, "
        "albo mnożnik.",
        "increase_days_positive": "Liczba dodatkowych dni roboczych zadania „{task}” musi być "
        "większa od 0.",
        "increase_factor_above_one": "Mnożnik zadania „{task}” musi być większy od 1.",
        "new_task_name_used": "Zadanie o nazwie „{name}” już istnieje.",
        "new_task_key_used": "Identyfikator zadania {key} jest już zajęty.",
        "new_task_before_started": "„{name}” nie może poprzedzać zadania „{before}”, które już "
        "się rozpoczęło.",
        "new_task_after_invalid": "„{name}” nie może następować po „{after}”, które samo zależy "
        "od „{before}”.",
        "new_task_optional_before": "„{name}” jest opcjonalne, więc nie może poprzedzać innego "
        "zadania.",
        "state_not_started": "nierozpoczęte",
        "state_done": "gotowe",
        "state_removed": "usunięte z zakresu",
        "recommendation_not_found": "Nie ma takiej rekomendacji.",
        "recommendation_closed": "Ta rekomendacja nie jest już otwarta ({status}).",
        "nothing_to_decide": "Ta rekomendacja zachowuje plan; nie ma czego zatwierdzać.",
        "action_discarded": "Działanie nie jest już możliwe ({reason}); pojawi się nowa "
        "rekomendacja.",
        "psplib_missing": "Symulator potrzebuje danych PSPLIB na serwerze "
        "(scripts/fetch_psplib.py).",
        "unknown_instance": "Nie ma projektu symulacji {instance}.",
        "unknown_policy": "Nie ma strategii {policy}.",
        "simulation_finished": "Symulacja się zakończyła.",
        "not_a_simulator": "To nie jest projekt symulatora.",
        "not_a_live_project": "To jest projekt symulatora; nie ma raportów statusu.",
        "simulation_running": "Obie symulacje muszą się zakończyć, zanim powstanie kokpit.",
        "action_noop": "Zachowaj plan",
        "action_shift": "przesuń pozostałe zadania z zachowaniem ich kolejności",
        "action_reseq_m": "przeplanuj pozostałe zadania na najwcześniejsze zakończenie",
        "action_reseq_s": "przeplanuj pozostałe zadania przy jak najmniejszych zmianach",
        "action_subst": "niech {workers} zastąpi nieobecnych w zespole zadania „{task}”",
        "action_overtime": "zatrudnij tymczasowo: {count} × {role} na {days} dni roboczych "
        "(do {until})",
        "action_descope": "zrezygnuj z opcjonalnego zadania „{task}”",
        "action_then": ", następnie ",
        "reason_needs_met": "działanie nie jest potrzebne: plan jest na dobrej drodze",
        "reason_only_candidate": "żadne inne działanie nie było możliwe",
        "reason_racing": "pozostałe działania wypadły wyraźnie gorzej w pierwszych "
        "symulowanych scenariuszach",
        "reason_on_time": "daje największą szansę na zakończenie w terminie",
        "reason_tardiness": "daje najmniejsze oczekiwane opóźnienie",
        "reason_scope": "najmniej ogranicza zakres",
        "reason_budget": "ma najniższy oczekiwany koszt",
        "reason_stability": "najmniej zmienia plan",
        "reason_level": "wymaga najmniej zatwierdzeń",
        "reason_order": "działania remisują we wszystkim, więc wygrywa najprostsze",
        "reason_utility": "ma najlepszy łączny wynik",
        "reason_approved": "działanie zostało zatwierdzone",
        "reason_idle_events": "w zespołach nic się nie zmieniło",
        "reason_awaiting_approval": "działanie czeka na zatwierdzenie",
        "status_none": "działanie niepotrzebne",
        "status_auto": "zastosowane automatycznie",
        "status_open": "czeka na Twoją decyzję",
        "status_later": "odłożone na później",
        "status_approved": "zatwierdzone i zastosowane",
        "status_rejected": "odrzucone",
        "status_discarded": "już niemożliwe",
        "status_superseded": "zastąpione nowszą rekomendacją",
        "progress_not_started": "nierozpoczęte",
        "progress_in_progress": "w toku",
        "progress_paused": "wstrzymane (zespół nieobecny)",
        "progress_done": "gotowe",
        "progress_removed": "usunięte z zakresu",
        "cockpit_title": "Kokpit projektu",
        "cockpit_subtitle": "Stan na koniec dnia {date}; plan, prognozy i rekomendacje Sentinela.",
        "cockpit_plan": "plan",
        "cockpit_deadline": "termin",
        "cockpit_today": "dziś",
        "cockpit_kpis": "Najważniejsze liczby",
        "cockpit_gantt": "Plan i postęp",
        "cockpit_gantt_note": "Szary: plan bazowy. Kolorowy: praca zgłoszona do tej pory "
        "(w paski, gdy część zespołu była nieobecna; obrys, gdy nieobecny był cały zespół).",
        "cockpit_risk": "Szansa na zakończenie w terminie",
        "cockpit_risk_note": "Przy każdej rekomendacji: P(w terminie) bez działania i przedział "
        "dnia zakończenia (10–90 %) w symulowanych scenariuszach, na których decydował Sentinel.",
        "cockpit_log": "Rekomendacje",
        "cockpit_col_date": "Data",
        "cockpit_col_action": "Rekomendowane działanie",
        "cockpit_col_p": "P(w terminie)",
        "cockpit_col_reason": "Dlaczego",
        "cockpit_col_status": "Status",
        "cockpit_col_explanation": "Wyjaśnienie",
        "cockpit_kpi_plan": "Zakończenie według planu bazowego",
        "cockpit_kpi_deadline": "Termin",
        "cockpit_kpi_tasks": "Gotowe zadania",
        "cockpit_kpi_cost": "Dotychczasowy koszt / budżet",
        "cockpit_kpi_forecast": "Oczekiwane zakończenie bez działania",
        "cockpit_kpi_p": "P(w terminie) bez działania",
        "cockpit_kpi_actions": "Zastosowane działania",
        "cockpit_kpi_temps": "Zatrudnieni pracownicy tymczasowi",
        "cockpit_llm_invalid": "Model językowy nie podał poprawnego wyjaśnienia.",
        "cockpit_badge_template": "wyjaśnienie z szablonu",
        "cockpit_badge_faithful": "{model}: wierne",
        "cockpit_badge_unfaithful": "{model}: niewierne",
        "cockpit_badge_invalid": "{model}: brak poprawnej odpowiedzi",
        "cockpit_provenance": "Pochodzenie danych",
        "cockpit_p_software": "Oprogramowanie",
        "cockpit_p_settings": "Ustawienia",
        "cockpit_p_note": "Uwaga",
        "cockpit_p_note_text": "Każda liczba pochodzi z dziennika zdarzeń projektu i jego "
        "ziarna losowego; ten sam dziennik daje tę samą stronę.",
        "csv_empty": "Plik jest pusty.",
        "csv_encoding": "Plik nie jest tekstem w kodowaniu UTF-8.",
        "csv_missing_column": "W pliku brakuje kolumny „{column}”.",
        "csv_number": "Wiersz {row}: {column} musi być liczbą całkowitą (jest „{value}”).",
        "csv_decimal": "Wiersz {row}: {column} musi być liczbą (jest „{value}”).",
        "csv_flag": "Wiersz {row}: {column} musi mieć wartość tak albo nie (jest „{value}”).",
        "csv_crew": "Wiersz {row}: skład „{value}” musi mieć postać „Backend developer=2; "
        "Tester=1”.",
        "csv_key": "Wiersz {row}: identyfikator „{value}” może zawierać tylko litery, cyfry, „_”, "
        "„-” i „.”.",
        "csv_required": "Wiersz {row}: pole {column} jest wymagane.",
        "csv_too_long": "Wiersz {row}: pole {column} jest dłuższe niż 120 znaków.",
        "csv_row": "Wiersz {row}: {message}",
        "json_invalid": "Plik nie jest projektem wyeksportowanym przez Sentinela ({detail}).",
        "date_invalid": "{field} musi być datą w postaci 2026-11-02 (jest „{value}”).",
        "extraction_failed": "Z tekstu nie udało się odczytać użytecznego planu ({detail}).",
        "extraction_issues": "Plan odczytany z tekstu ma jeszcze {count} problemów; sprawdź go "
        "przed zapisaniem.",
        "text_empty": "Najpierw wklej opis projektu.",
        "not_found": "Nie znaleziono.",
        "project_not_found": "Nie ma takiego projektu.",
        "job_not_found": "Nie ma takiego zadania obliczeniowego.",
        "job_not_done": "Obliczenia jeszcze trwają.",
        "invalid_request": "Żądanie jest nieprawidłowe.",
        "field_required": "Pole {field} jest wymagane.",
        "field_invalid": "Pole {field} jest nieprawidłowe: {detail}.",
        "csrf_failed": "Strona wygasła; odśwież ją i spróbuj ponownie.",
        "rate_limited": "Zbyt wiele żądań; odczekaj minutę.",
        "too_large": "Przesłany plik jest większy niż {limit} kB.",
        "limit_projects": "Sesja demonstracyjna może mieć co najwyżej {limit} projektów.",
        "limit_tasks": "Projekt demonstracyjny może mieć co najwyżej {limit} zadań.",
        "limit_days": "Symulator demonstracyjny przesuwa czas o co najwyżej {limit} dni naraz.",
        "limit_jobs": "Poczekaj, aż zakończą się trwające obliczenia.",
        "llm_disabled": "Nie skonfigurowano modelu językowego.",
        "llm_cap": "Osiągnięto dzienny limit zapytań do modelu językowego; spróbuj jutro.",
        "llm_failed": "Model językowy nie odpowiedział ({detail}).",
        "demo_forbidden": "Ta funkcja nie jest dostępna w wersji demonstracyjnej.",
        "settings_invalid": "Ustawienia modelu językowego są nieprawidłowe: {detail}.",
        "internal_error": "Na serwerze wystąpił błąd; został zapisany w dzienniku.",
    },
}


def render(code: str, language: Language = "en", params: Mapping[str, object] | None = None) -> str:
    """The message of `code` in `language` with its parameters; unknown codes show themselves."""
    template = MESSAGES.get(language, MESSAGES["en"]).get(code)
    if template is None:
        return code
    values = dict(params or {})
    if "state" in values and isinstance(values["state"], str):
        values["state"] = MESSAGES[language].get(f"state_{values['state']}", values["state"])
    try:
        return template.format(**values)
    except (KeyError, IndexError, ValueError):
        return template


def language_of(value: str | None) -> Language:
    """The language of a `lang` parameter or an Accept-Language header: Polish if it asks for
    Polish first, else English."""
    if not value:
        return "en"
    first = value.split(",")[0].strip().lower()
    return "pl" if first.startswith("pl") else "en"
