"""The texts of the v2 interface in English and Polish (WP15; docs/design/v2-spec.md, section 6).

`CATALOGUE` holds the v2 keys (key -> (English, Polish)); the labels of the spec's glossary are
quoted exactly. `TextsV2` looks a key up here first and then in the catalogue of the first
interface, whose formats (dates, plural forms) it shares. A test checks both languages, the
placeholders, the keys the v2 templates use and that no text holds an internal term.
"""

from collections.abc import Mapping

from sentinel.app.ui.text import CATALOGUE as V1_CATALOGUE
from sentinel.app.ui.text import Texts

CATALOGUE: Mapping[str, tuple[str, str]] = {
    # ---- frame (section 7)
    "v2.skip": ("Skip to content", "Przejdź do treści"),
    "v2.nav.label": ("Main menu", "Menu główne"),
    "v2.nav.start": ("Start", "Start"),
    "v2.nav.projects": ("Projects", "Projekty"),
    "v2.nav.log": ("Log", "Dziennik"),
    "v2.nav.lab": ("Lab", "Laboratorium"),
    "v2.nav.settings": ("Settings", "Ustawienia"),
    "v2.nav.language": ("Language", "Język"),
    "v2.nav.old": ("Previous look", "Poprzedni wygląd"),
    "v2.theme": ("Appearance", "Wygląd"),
    "v2.theme.light": ("Light", "Jasny"),
    "v2.theme.dark": ("Dark", "Ciemny"),
    "v2.theme.system": ("System", "Systemowy"),
    "v2.version": ("Version {version}", "Wersja {version}"),
    "v2.tabs": ("Project sections", "Sekcje projektu"),
    "v2.tab.overview": ("Overview", "Pulpit"),
    "v2.tab.report": ("Report", "Raport"),
    "v2.tab.decisions": ("Decisions", "Decyzje"),
    "v2.tab.log": ("Log", "Dziennik"),
    "v2.tab.plan": ("Plan", "Plan"),
    "v2.tab.settings": ("Project settings", "Ustawienia projektu"),
    "v2.as_of": ("status at {moment}", "stan na {moment}"),
    "v2.report_button": ("Report", "Raport"),
    "v2.soon.title": ("Coming soon", "Wkrótce"),
    "v2.soon.text": (
        "This part of the new look is being built. Until then it works in the previous look.",
        "Ta część nowego wyglądu jest w budowie. Do tego czasu działa w poprzednim wyglądzie.",
    ),
    "v2.soon.open": ("Open in the previous look", "Otwórz w poprzednim wyglądzie"),
    "v2.banner.label": ("New events", "Nowe zdarzenia"),
    "v2.banner.decision": (
        "{project}: a new decision to make",
        "{project}: nowa decyzja do podjęcia",
    ),
    "v2.banner.fell": (
        "{project}: the chance fell from {before} to {after} in 100",
        "{project}: szansa spadła z {before} do {after} na 100",
    ),
    "v2.banner.rose": (
        "{project}: the chance rose from {before} to {after} in 100",
        "{project}: szansa wzrosła z {before} do {after} na 100",
    ),
    "v2.banner.state": ("{project}: now “{state}”", "{project}: teraz „{state}”"),
    "v2.banner.see": ("See", "Zobacz"),
    "v2.banner.close": ("Close", "Zamknij"),
    "v2.not_found": ("This page does not exist.", "Ta strona nie istnieje."),
    # ---- states and numbers (section 4)
    "v2.state.good": ("On track", "Na dobrej drodze"),
    "v2.state.warn": ("At risk", "Zagrożony"),
    "v2.state.bad": ("Late without changes", "Nie zdążymy bez zmian"),
    "v2.state.none": ("No forecast yet", "Brak prognozy"),
    "v2.state.draft": ("Plan not ready", "Plan niegotowy"),
    "v2.state.finished": ("Finished", "Zakończony"),
    "v2.verdict.good.one": (
        "We will make it with about {n} working day to spare.",
        "Zdążymy z zapasem ok. {n} dnia roboczego.",
    ),
    "v2.verdict.good.few": (
        "We will make it with about {n} working days to spare.",
        "Zdążymy z zapasem ok. {n} dni roboczych.",
    ),
    "v2.verdict.good.many": (
        "We will make it with about {n} working days to spare.",
        "Zdążymy z zapasem ok. {n} dni roboczych.",
    ),
    "v2.verdict.good_zero": (
        "We will make it, but with no time to spare.",
        "Zdążymy, ale bez zapasu czasu.",
    ),
    "v2.verdict.warn.one": (
        "We will probably make it, but the reserve is small (about {n} working day).",
        "Raczej zdążymy, ale zapas jest mały (ok. {n} dnia roboczego).",
    ),
    "v2.verdict.warn.few": (
        "We will probably make it, but the reserve is small (about {n} working days).",
        "Raczej zdążymy, ale zapas jest mały (ok. {n} dni roboczych).",
    ),
    "v2.verdict.warn.many": (
        "We will probably make it, but the reserve is small (about {n} working days).",
        "Raczej zdążymy, ale zapas jest mały (ok. {n} dni roboczych).",
    ),
    "v2.verdict.warn_zero": (
        "We will probably make it, but with no time to spare.",
        "Raczej zdążymy, ale bez zapasu czasu.",
    ),
    "v2.verdict.bad.one": (
        "We will be about {n} working day late.",
        "Spóźnimy się o ok. {n} dzień roboczy.",
    ),
    "v2.verdict.bad.few": (
        "We will be about {n} working days late.",
        "Spóźnimy się o ok. {n} dni robocze.",
    ),
    "v2.verdict.bad.many": (
        "We will be about {n} working days late.",
        "Spóźnimy się o ok. {n} dni roboczych.",
    ),
    "v2.verdict.none": (
        "Set a deadline to see the chance of meeting it.",
        "Ustaw termin, aby zobaczyć szansę na jego dotrzymanie.",
    ),
    "v2.verdict.finished": ("The project is finished.", "Projekt jest zakończony."),
    "v2.verdict.cause": ("Main cause: {cause}.", "Główna przyczyna: {cause}."),
    "v2.cause.absence": ("{name} away until {date}", "{name} — nieobecność do {date}"),
    "v2.cause.absence_open": ("{name} away", "{name} — nieobecność"),
    "v2.cause.growth": ("“{name}” takes longer", "„{name}” potrwa dłużej"),
    "v2.cause.new_task": ("the new task “{name}”", "nowe zadanie „{name}”"),
    "v2.cause.progress": ("work slower than planned", "prace wolniej niż w planie"),
    "v2.cause.risk": (
        "“{name}”: the longer it takes, the later the project ends",
        "„{name}”: im dłużej trwa, tym później koniec projektu",
    ),
    "v2.chance.title": ("Chance of the deadline", "Szansa na termin"),
    "v2.chance.value": ("{n} in 100", "{n} na 100"),
    "v2.chance.help": ("Where does this number come from?", "Skąd ta liczba?"),
    "v2.chance.explain": (
        "Sentinel played this project {w} times, each time with different random events "
        "(absences, tasks shorter or longer than planned), in line with what the reports tell "
        "us. In {k} of them — that is {n} in 100 — the project finished by the deadline.",
        "Sentinel rozegrał ten projekt {w} razy, za każdym razem z innymi losowymi zdarzeniami "
        "(choroby, zadania krótsze lub dłuższe niż w planie), zgodnie z tym, co wiemy z "
        "raportów. W {k} z nich — czyli {n} na 100 — projekt skończył się przed terminem.",
    ),
    "v2.dots": ("{n} of 100 dots filled", "{n} ze 100 kropek wypełnionych"),
    "v2.end.title": ("Project end", "Koniec projektu"),
    "v2.end.likely": ("most likely", "najpewniej"),
    "v2.end.deadline": ("deadline", "termin"),
    "v2.end.bad": ("in a bad case", "w złym razie"),
    "v2.budget.title": ("Budget", "Budżet"),
    "v2.budget.spent": ("spent {a} of {b} work-days", "wydane {a} z {b} dni pracy"),
    "v2.budget.spent_units": ("spent {a} of {b} cost units", "wydane {a} z {b} jednostek kosztu"),
    "v2.budget.end": ("by the end about {c} ({p})", "na koniec ok. {c} ({p})"),
    "v2.workdays": ("{n} work-days", "{n} dni pracy"),
    # ---- the pending decision on the overview (section 8.2)
    "v2.decision.title": ("Decision to make", "Decyzja do podjęcia"),
    "v2.decision.valid": ("valid until {date}", "ważna do {date}"),
    "v2.decision.expires": ("expires tomorrow", "wygasa jutro"),
    "v2.decision.computing": ("validity being calculated", "ważność w trakcie liczenia"),
    "v2.decision.none": (
        "Nothing waits for your decision. Next report: {day}",
        "Nic nie czeka na Twoją decyzję. Następny raport: {day}",
    ),
    "v2.decision.thinking": (
        "Sentinel is analysing the latest report…",
        "Sentinel analizuje ostatni raport…",
    ),
    "v2.effect.chance": ("Chance {before} → {after} in 100", "Szansa {before} → {after} na 100"),
    "v2.effect.end": ("End {before} → {after}", "Koniec {before} → {after}"),
    "v2.effect.budget": ("Budget {change} work-days", "Budżet {change} dni pracy"),
    "v2.effect.budget_units": ("Budget {change} cost units", "Budżet {change} jednostek kosztu"),
    "v2.effect.budget_total": (
        "Budget {before} → {after} work-days",
        "Budżet {before} → {after} dni pracy",
    ),
    "v2.effect.better": ("better", "lepiej"),
    "v2.effect.worse": ("worse", "gorzej"),
    "v2.effect.same": ("no change", "bez zmian"),
    "v2.approve": ("Approve", "Zatwierdź"),
    "v2.reject": ("Reject", "Odrzuć"),
    "v2.adjust": ("Adjust", "Popraw"),
    "v2.postpone": ("Postpone", "Odłóż decyzję"),
    "v2.details": ("Details", "Szczegóły"),
    "v2.done.approved": (
        "Approved. The project now has the new plan.",
        "Zatwierdzono. Projekt ma nowy plan.",
    ),
    "v2.done.rejected": (
        "Rejected. Nothing in the project changed.",
        "Odrzucono. Projekt bez zmian.",
    ),
    "v2.done.postponed": (
        "I will remind you on your next visit. The decision is valid until {date}.",
        "Przypomnę przy następnej wizycie. Decyzja ważna do {date}.",
    ),
    "v2.done.postponed_open": (
        "I will remind you on your next visit.",
        "Przypomnę przy następnej wizycie.",
    ),
    "v2.done.discarded": (
        "The change was no longer possible, so nothing changed; Sentinel is analysing again.",
        "Tej zmiany nie dało się już wprowadzić, więc nic nie zmieniono; Sentinel analizuje "
        "projekt ponownie.",
    ),
    "v2.done.report": ("Report saved.", "Raport zapisany."),
    "v2.promise_note": (
        "The figures differ from the decision's because {why}.",
        "Liczby różnią się od tych z decyzji, ponieważ {why}.",
    ),
    "v2.promise.deadline": ("the deadline changed", "zmienił się termin"),
    "v2.promise.budget": ("the budget changed", "zmienił się budżet"),
    "v2.promise.settings": ("the settings changed", "zmieniły się ustawienia"),
    "v2.promise.replanned": (
        "the plan was laid out again on approval",
        "plan ułożono ponownie przy zatwierdzeniu",
    ),
    # ---- below the fold of the overview
    "v2.buffer.title": ("Time reserve", "Zapas czasu"),
    "v2.buffer.subtitle": (
        "How much reserve we used compared with the progress of work",
        "Ile zapasu zjedliśmy w stosunku do postępu prac",
    ),
    "v2.buffer.none": (
        "The plan had no time reserve from the start",
        "Plan od początku nie miał zapasu czasu",
    ),
    "v2.buffer.x": ("Work done", "Wykonana praca"),
    "v2.buffer.y": ("Reserve used", "Zużyty zapas"),
    "v2.buffer.zone.good": ("safe", "bezpiecznie"),
    "v2.buffer.zone.warn": ("watch", "uwaga"),
    "v2.buffer.zone.bad": ("act", "trzeba działać"),
    "v2.buffer.point": (
        "{date}: {work} of the work done, {used} of the reserve used ({zone})",
        "{date}: wykonano {work} pracy, zużyto {used} zapasu ({zone})",
    ),
    "v2.buffer.start": ("plan", "plan"),
    "v2.buffer.summary": (
        "Reserve: {reserve}. Latest: {work} of the work done, {used} of the reserve used.",
        "Zapas: {reserve}. Ostatnio: wykonano {work} pracy, zużyto {used} zapasu.",
    ),
    "v2.week.title": ("Next 7 days", "Najbliższe 7 dni"),
    "v2.week.absence_start": ("{name}: away from this day", "{name}: początek nieobecności"),
    "v2.week.absence_end": ("{name}: back", "{name}: powrót"),
    "v2.week.task_start": ("“{name}”: starts", "„{name}”: początek"),
    "v2.week.task_end": ("“{name}”: ends", "„{name}”: koniec"),
    "v2.week.deadline": ("Project deadline", "Termin projektu"),
    "v2.week.empty": (
        "Nothing is planned in the next 7 days.",
        "W najbliższych 7 dniach nic nie jest zaplanowane.",
    ),
    "v2.causes.title": ("Causes of the change", "Przyczyny zmiany"),
    "v2.causes.since": (
        "since the report of {date} ({before} → {after} in 100)",
        "od raportu z {date} ({before} → {after} na 100)",
    ),
    "v2.causes.absence": (
        "Without the absence of {name} the chance would be {n} in 100.",
        "Bez nieobecności osoby {name} szansa byłaby {n} na 100.",
    ),
    "v2.causes.growth": (
        "Had “{name}” not grown, the chance would be {n} in 100.",
        "Bez wydłużenia „{name}” szansa byłaby {n} na 100.",
    ),
    "v2.causes.new_task": (
        "Without the new task “{name}” the chance would be {n} in 100.",
        "Bez nowego zadania „{name}” szansa byłaby {n} na 100.",
    ),
    "v2.causes.progress": (
        "Had the work gone as planned since {date}, the chance would be {n} in 100.",
        "Gdyby od {date} prace szły zgodnie z planem, szansa byłaby {n} na 100.",
    ),
    "v2.causes.note": (
        "Each line changes one thing, so the effects do not add up exactly.",
        "Każda linia zmienia jedną rzecz, więc skutki nie sumują się dokładnie.",
    ),
    "v2.causes.none": (
        "No report has moved the chance by much yet.",
        "Żaden raport nie zmienił jeszcze wyraźnie szansy.",
    ),
    "v2.causes.wait": ("Finding the causes…", "Ustalam przyczyny…"),
    "v2.risks.title": ("Main risks", "Główne ryzyka"),
    "v2.risks.item": (
        "“{name}”: the longer it takes, the later the project ends.",
        "„{name}”: im dłużej trwa, tym później koniec projektu.",
    ),
    "v2.risks.spread": ("The risk is spread across the plan.", "Ryzyko rozkłada się na cały plan."),
    "v2.risks.none": (
        "In none of the played futures is the project late.",
        "W żadnym z rozegranych wariantów projekt się nie spóźnia.",
    ),
    "v2.risks.wait": ("Finding the main risks…", "Ustalam główne ryzyka…"),
    "v2.retry": ("Try again", "Spróbuj ponownie"),
    "v2.failed": ("This could not be calculated.", "Nie udało się tego policzyć."),
    # ---- decision (section 8.4)
    "v2.dec.title": ("Decision to make", "Decyzja do podjęcia"),
    "v2.dec.back": ("Overview", "Pulpit"),
    "v2.dec.left.one": ("{n} day left", "został {n} dzień"),
    "v2.dec.left.few": ("{n} days left", "zostały {n} dni"),
    "v2.dec.left.many": ("{n} days left", "zostało {n} dni"),
    "v2.dec.today": ("last day today", "ostatni dzień dziś"),
    "v2.dec.need.people": (
        "It affects people, so it needs your approval.",
        "Dotyczy ludzi, dlatego wymaga Twojej zgody.",
    ),
    "v2.dec.need.money": (
        "It costs money, so it needs your approval.",
        "Kosztuje, dlatego wymaga Twojej zgody.",
    ),
    "v2.dec.need.scope": (
        "It changes the scope, so it needs your approval.",
        "Zmienia zakres, dlatego wymaga Twojej zgody.",
    ),
    "v2.dec.need.plan": (
        "It changes the plan, so it needs your approval.",
        "Zmienia plan, dlatego wymaga Twojej zgody.",
    ),
    "v2.dec.effect": ("Effect", "Skutek"),
    "v2.dec.reasoning": ("Reasoning", "Uzasadnienie"),
    "v2.dec.who": ("Who is affected", "Kogo dotyczy"),
    "v2.dec.delay": ("Cost of delay", "Koszt zwłoki"),
    "v2.dec.delay_text": (
        "Each day of waiting costs about {n} in 100.",
        "Każdy dzień czekania to ok. \u2212{n} na 100.",
    ),
    "v2.dec.delay_small": (
        "A few days of waiting change little.",
        "Kilka dni czekania niewiele zmienia.",
    ),
    "v2.dec.delay_wait": ("Calculating…", "Liczę…"),
    "v2.dec.state": ("State: {state}", "Stan: {state}"),
    "v2.why.gain": (
        "This change raises the chance from {before} to {after} in 100 and moves the most likely "
        "end from {fromday} to {toend}.",
        "Ta zmiana podnosi szansę z {before} do {after} na 100, a najpewniejszy koniec przesuwa "
        "z {fromday} na {toend}.",
    ),
    "v2.why.gain_same_end": (
        "This change raises the chance from {before} to {after} in 100; the most likely end "
        "stays {toend}.",
        "Ta zmiana podnosi szansę z {before} do {after} na 100; najpewniejszy koniec zostaje "
        "{toend}.",
    ),
    "v2.why.even": (
        "This change keeps the chance at {after} in 100 and moves the most likely end from "
        "{fromday} to {toend}.",
        "Ta zmiana utrzymuje szansę {after} na 100, a najpewniejszy koniec przesuwa z "
        "{fromday} na {toend}.",
    ),
    "v2.why.even_same_end": (
        "This change keeps the chance at {after} in 100 and the most likely end at {toend}; "
        "it lowers the expected delay.",
        "Ta zmiana utrzymuje szansę {after} na 100 i najpewniejszy koniec {toend}; "
        "zmniejsza oczekiwane opóźnienie.",
    ),
    "v2.why.alt_less": (
        "The next best option, “{option}”, would give less ({chance} in 100) at a cost of {price}.",
        "Następna możliwość, „{option}”, dałaby mniej ({chance} na 100) przy koszcie {price}.",
    ),
    "v2.why.alt_dearer": (
        "The next best option, “{option}”, would give a similar chance ({chance} in 100) but cost "
        "more ({price} against {cost}).",
        "Następna możliwość, „{option}”, dałaby podobną szansę ({chance} na 100), ale kosztowałaby "
        "więcej ({price} wobec {cost}).",
    ),
    "v2.why.alt_similar": (
        "The next best option, “{option}”, would give {chance} in 100; {tie}.",
        "Następna możliwość, „{option}”, dałaby {chance} na 100; {tie}.",
    ),
    "v2.why.only": (
        "Without a change the chance stays {before} in 100; no other option helps as much.",
        "Bez zmian szansa zostaje {before} na 100; żadna inna możliwość nie pomaga tak bardzo.",
    ),
    "v2.who.subst": (
        "{person}: takes over “{task}” in place of {absent}",
        "{person}: przejmuje „{task}” w zastępstwie, za osobę {absent}",
    ),
    "v2.who.absent": (
        "{absent}: back to their own tasks after returning",
        "{absent}: po powrocie wraca do swoich zadań",
    ),
    "v2.who.temp.one": (
        "A temporary person: {role} for {n} day",
        "Osoba tymczasowa: {role} na {n} dzień",
    ),
    "v2.who.temp.few": (
        "A temporary person: {role} for {n} days",
        "Osoba tymczasowa: {role} na {n} dni",
    ),
    "v2.who.temp.many": (
        "A temporary person: {role} for {n} days",
        "Osoba tymczasowa: {role} na {n} dni",
    ),
    "v2.who.temps": (
        "{u} temporary people: {role} for {n} days",
        "{u} osoby tymczasowe: {role} na {n} dni",
    ),
    "v2.who.descope": (
        "“{task}”: dropped, nobody works on it",
        "„{task}”: rezygnujemy, nikt nad nim nie pracuje",
    ),
    "v2.who.moved.one": ("{n} task gets new dates", "{n} zadanie dostaje nowe terminy"),
    "v2.who.moved.few": ("{n} tasks get new dates", "{n} zadania dostają nowe terminy"),
    "v2.who.moved.many": ("{n} tasks get new dates", "{n} zadań dostaje nowe terminy"),
    "v2.who.nobody": ("Nobody's tasks change.", "Niczyje zadania się nie zmieniają."),
    "v2.reject.title": ("Why do you reject it?", "Dlaczego odrzucasz?"),
    "v2.reject.too_expensive": ("Too expensive", "Za drogo"),
    "v2.reject.unavailable": ("Person unavailable", "Osoba niedostępna"),
    "v2.reject.no_budget": ("No budget", "Brak środków"),
    "v2.reject.other": ("Other reason", "Inny powód"),
    "v2.reject.confirm": ("Confirm rejection", "Potwierdź odrzucenie"),
    "v2.reject.cancel": ("Cancel", "Anuluj"),
    "v2.reject.note": ("Your reason", "Twój powód"),
    "v2.reject.note_hint": (
        "A few words for the log. Do not give reasons for anyone's absence.",
        "Kilka słów do dziennika. Nie podawaj powodów niczyjej nieobecności.",
    ),
    "v2.reject.pick": ("Choose a reason first.", "Najpierw wybierz powód."),
    "v2.adjust.title": ("Adjust the decision", "Popraw decyzję"),
    "v2.adjust.subst": ("Who takes over?", "Kto przejmuje?"),
    "v2.adjust.overtime": ("Who and for how long?", "Kogo i na ile?"),
    "v2.adjust.descope": (
        "Which optional task to drop?",
        "Z którego zadania opcjonalnego zrezygnować?",
    ),
    "v2.adjust.apply": ("Recalculate", "Przelicz"),
    "v2.adjust.none": (
        "This change cannot be adjusted: it only re-orders the plan.",
        "Tej zmiany nie da się poprawić: ona tylko porządkuje plan.",
    ),
    "v2.adjust.no_choice": (
        "There is nothing else to choose here.",
        "Nie ma tu innej możliwości do wyboru.",
    ),
    "v2.adjust.option.temp": ("{u} × {role} for {n} days", "{u} × {role} na {n} dni"),
    "v2.adjust.working": ("Recalculating the effect…", "Przeliczam skutek…"),
    "v2.adjust.done": (
        "Adjusted. The effect above is recalculated; approve it if it is right.",
        "Poprawiono. Skutek powyżej jest przeliczony; zatwierdź, jeśli się zgadza.",
    ),
    "v2.options.title": ("All options considered", "Wszystkie rozważone możliwości"),
    "v2.options.option": ("Option", "Możliwość"),
    "v2.options.chance": ("Chance", "Szansa"),
    "v2.options.end": ("End", "Koniec"),
    "v2.options.budget": ("Budget", "Budżet"),
    "v2.options.chosen": ("proposed", "proponowana"),
    "v2.options.noop": ("No change", "Bez zmian"),
    "v2.dist.title": ("Where these numbers come from", "Skąd te liczby"),
    "v2.dist.text": (
        "Each bar counts the played futures that end on that day; bars after the deadline line "
        "are late. Out of {w}: by the deadline {k}, later {late}.",
        "Każdy słupek liczy rozegrane warianty, które kończą się danego dnia; słupki za linią "
        "terminu są spóźnione. Na {w}: w terminie {k}, później {late}.",
    ),
    "v2.dist.with": ("With the change", "Ze zmianą"),
    "v2.dist.without": ("Without a change", "Bez zmian"),
    "v2.dist.day": ("{date}: {n}", "{date}: {n}"),
    "v2.ai.title": ("Explanation in plain words (AI)", "Wyjaśnienie prostymi słowami (AI)"),
    "v2.ai.ask": ("Explain", "Wyjaśnij"),
    "v2.ai.off": (
        "An explanation needs an AI provider (Settings).",
        "Wyjaśnienie wymaga dostawcy AI (Ustawienia).",
    ),
    "v2.decisions.pending": ("Decisions to make", "Decyzje do podjęcia"),
    "v2.decisions.archive": ("Earlier decisions", "Wcześniejsze decyzje"),
    "v2.decisions.none_pending": ("No decisions to make", "Brak decyzji do podjęcia"),
    "v2.decisions.none": ("No earlier decisions yet.", "Nie ma jeszcze wcześniejszych decyzji."),
    "v2.decisions.reason": ("Reason: {reason}", "Powód: {reason}"),
    "v2.decisions.brief": ("The brief as it was", "Decyzja w chwili zdarzenia"),
    "v2.life.pending": ("pending", "oczekuje"),
    "v2.life.approved": ("approved", "zatwierdzona"),
    "v2.life.rejected": ("rejected", "odrzucona"),
    "v2.life.postponed": ("postponed", "odłożona"),
    "v2.life.adjusted": ("adjusted", "poprawiona"),
    "v2.life.expired": ("expired", "wygasła"),
    "v2.life.superseded": ("replaced", "zastąpiona"),
    "v2.life.discarded": ("no longer possible", "nieaktualna"),
    "v2.life.auto": ("applied automatically", "zastosowana automatycznie"),
    "v2.life.undone": ("undone", "cofnięta"),
    "v2.actor.you": ("You", "Ty"),
    "v2.actor.sentinel": ("Sentinel", "Sentinel"),
    # ---- report (section 8.3)
    "v2.report.title": ("Report", "Raport"),
    "v2.report.of": ("Report · {date}", "Raport · {date}"),
    "v2.report.change_date": ("change date", "zmień datę"),
    "v2.report.date": ("Date of the report", "Data raportu"),
    "v2.report.last": ("last report: {date}", "ostatni raport: {date}"),
    "v2.report.first": ("first report", "pierwszy raport"),
    "v2.report.step1": ("Events since the last report", "Zdarzenia od ostatniego raportu"),
    "v2.report.message": ("What happened", "Co się wydarzyło"),
    "v2.report.example": (
        "E.g. “Bart is away from tomorrow until Monday. API finished, mock-ups half done.”",
        "Np. „Bartek od jutra nieobecny do poniedziałku. API skończone, makiety w połowie.”",
    ),
    "v2.report.hints": ("Hints:", "Podpowiedzi:"),
    "v2.hint.absent": ("Someone will be away", "Ktoś będzie nieobecny"),
    "v2.hint.absent.text": ("Away will be ", "Nieobecny będzie "),
    "v2.hint.done": ("Task finished", "Zadanie skończone"),
    "v2.hint.done.text": ("Finished: “", "Skończone jest zadanie „"),
    "v2.hint.longer": ("Task will take longer", "Zadanie potrwa dłużej"),
    "v2.hint.longer.text": ("Will take longer: “", "Dłużej potrwa zadanie „"),
    "v2.hint.new": ("New task", "Nowe zadanie"),
    "v2.hint.new.text": ("New task: “", "Nowe zadanie: „"),
    "v2.report.read": ("Recognise the changes", "Rozpoznaj zmiany"),
    "v2.report.reading": ("Reading the report…", "Czytam raport…"),
    "v2.report.planned": ("Progress as planned", "Postęp zgodny z planem"),
    "v2.report.no_ai": (
        "Recognising a written report needs an AI provider; use “Progress as planned” or the form.",
        "Rozpoznawanie opisu wymaga dostawcy AI; użyj „Postęp zgodny z planem” albo formularza.",
    ),
    "v2.report.step2": ("To confirm", "Do potwierdzenia"),
    "v2.report.step2_hint": (
        "Tick the changes that are right.",
        "Zaznacz zmiany, które się zgadzają.",
    ),
    "v2.report.all": ("Tick all", "Zaznacz wszystkie"),
    "v2.report.empty": (
        "Write or dictate what happened, then recognise the changes.",
        "Opisz lub podyktuj, co się wydarzyło, a potem rozpoznaj zmiany.",
    ),
    "v2.report.edit": ("Edit", "Edytuj"),
    "v2.report.remove": ("Remove", "Usuń"),
    "v2.report.save_edit": ("Done", "Gotowe"),
    "v2.report.unparsed": ("Unrecognised parts", "Nierozpoznane fragmenty"),
    "v2.report.add_by_hand": ("Add manually", "Dodaj ręcznie"),
    "v2.report.question_skip": ("Skip", "Pomiń"),
    "v2.report.step3": ("Effect on the project", "Wpływ na projekt"),
    "v2.report.computing": ("Calculating…", "Liczę…"),
    "v2.report.tick_some": (
        "Tick changes to see their effect.",
        "Zaznacz zmiany, aby zobaczyć ich wpływ.",
    ),
    "v2.report.save": ("Save report", "Zapisz raport"),
    "v2.report.blocked": ("Answer the questions first.", "Najpierw odpowiedz na pytania."),
    "v2.report.form": ("Fill in the form", "Wypełnij formularz"),
    "v2.report.stalled.one": (
        "{n} task in progress without news — has nothing changed since {date}?",
        "{n} zadanie w toku bez wieści — czy od {date} nic się nie zmieniło?",
    ),
    "v2.report.stalled.few": (
        "{n} tasks in progress without news — has nothing changed since {date}?",
        "{n} zadania w toku bez wieści — czy od {date} nic się nie zmieniło?",
    ),
    "v2.report.stalled.many": (
        "{n} tasks in progress without news — has nothing changed since {date}?",
        "{n} zadań w toku bez wieści — czy od {date} nic się nie zmieniło?",
    ),
    "v2.report.finished": ("The project is finished.", "Projekt jest zakończony."),
    "v2.card.done": ("“{task}” finished on {date}", "„{task}” skończone {date}"),
    "v2.card.progress": ("“{task}”: {percent} % done", "„{task}”: wykonano {percent} %"),
    "v2.card.started": (
        "“{task}”: started {date}, {percent} % done",
        "„{task}”: rozpoczęte {date}, wykonano {percent} %",
    ),
    "v2.card.absence": (
        "{name}: away from {first}, back {back}",
        "{name}: nieobecność od {first}, wraca {back}",
    ),
    "v2.card.absence_open": (
        "{name}: away from {first}, return not known",
        "{name}: nieobecność od {first}, powrót nieznany",
    ),
    "v2.card.more": ("“{task}” takes {n} more days", "„{task}” potrwa o {n} dni dłużej"),
    "v2.card.factor": ("“{task}” grows ×{f}", "„{task}” rośnie ×{f}"),
    "v2.card.new": ("New task “{name}”, {n} days", "Nowe zadanie „{name}”, {n} dni"),
    "v2.card.planned": (
        "“{task}”: {percent} % done, as planned",
        "„{task}”: wykonano {percent} %, zgodnie z planem",
    ),
    "v2.card.planned_done": (
        "“{task}” finished on {date}, as planned",
        "„{task}” skończone {date}, zgodnie z planem",
    ),
    "v2.edit.percent": ("Share done (%)", "Wykonana część (%)"),
    "v2.edit.finish": ("Finished on", "Skończone dnia"),
    "v2.edit.first": ("Away from", "Nieobecność od"),
    "v2.edit.back": ("Back on", "Wraca"),
    "v2.edit.days": ("More days", "Dodatkowe dni"),
    "v2.edit.duration": ("Days of work", "Dni pracy"),
    # ---- voice (section 9)
    "v2.voice.start": ("Dictate", "Podyktuj"),
    "v2.voice.recording": ("Recording", "Nagrywanie"),
    "v2.voice.accept": ("Finish recording (Enter)", "Zakończ nagrywanie (Enter)"),
    "v2.voice.cancel": ("Cancel recording (Esc)", "Anuluj nagranie (Esc)"),
    "v2.voice.level": ("Sound level", "Poziom dźwięku"),
    "v2.voice.preview_off": ("Preview unavailable for a moment", "Podgląd chwilowo niedostępny"),
    "v2.voice.cap_soon": ("The recording stops in 30 s.", "Nagranie zakończy się za 30 s."),
    "v2.voice.writing": ("Writing it out…", "Przepisuję…"),
    "v2.voice.done": (
        "Written out — read it and correct it if needed.",
        "Przepisane — przeczytaj i popraw, jeśli trzeba.",
    ),
    "v2.voice.denied": (
        "Allow the microphone in the browser to dictate.",
        "Zezwól przeglądarce na użycie mikrofonu, aby dyktować.",
    ),
    "v2.voice.failed": (
        "The recording could not be written out. Type the text instead.",
        "Nie udało się przepisać nagrania. Wpisz tekst ręcznie.",
    ),
    # ---- start (section 8.1)
    "v2.start.title": ("Projects", "Projekty"),
    "v2.start.new": ("New project", "Nowy projekt"),
    "v2.start.decisions": ("Decisions to make", "Decyzje do podjęcia"),
    "v2.start.sorted": ("sorted by validity date", "posortowane wg daty ważności"),
    "v2.start.no_decisions": ("No decisions to make", "Brak decyzji do podjęcia"),
    "v2.start.projects": ("Projects", "Projekty"),
    "v2.start.events": ("Recent events", "Ostatnie zdarzenia"),
    "v2.start.all_events": ("Whole log", "Cały dziennik"),
    "v2.start.no_events": ("No events yet.", "Nie ma jeszcze zdarzeń."),
    "v2.start.pending.one": ("{n} decision", "{n} decyzja"),
    "v2.start.pending.few": ("{n} decisions", "{n} decyzje"),
    "v2.start.pending.many": ("{n} decisions", "{n} decyzji"),
    "v2.start.draft": ("Finish setting it up", "Dokończ zakładanie"),
    "v2.start.reserve": ("Reserve about {n} working days", "Zapas ok. {n} dni roboczych"),
    "v2.start.first": ("Start with your first project", "Zacznij od pierwszego projektu"),
    "v2.start.first.import": ("Import a spreadsheet", "Zaimportuj arkusz"),
    "v2.start.first.import_text": (
        "Tasks, durations and dependencies from a CSV file.",
        "Zadania, czasy i zależności z pliku CSV.",
    ),
    "v2.start.first.voice": ("Describe the project by voice", "Opisz projekt głosem"),
    "v2.start.first.voice_text": (
        "Say what has to be done; Sentinel lists the tasks for you to check.",
        "Powiedz, co trzeba zrobić; Sentinel wypisze zadania do sprawdzenia.",
    ),
    "v2.start.first.example": ("Open the example project", "Otwórz projekt przykładowy"),
    "v2.start.first.example_text": (
        "An online shop relaunch with eight people and two reports.",
        "Nowa odsłona sklepu internetowego: osiem osób i dwa raporty.",
    ),
    "v2.event.created": ("Project created", "Utworzono projekt"),
    "v2.event.plan": ("Plan ready", "Plan gotowy"),
    "v2.event.definition": ("Project details changed", "Zmieniono dane projektu"),
    "v2.event.report": ("Report of {date} saved", "Zapisano raport z {date}"),
    "v2.event.proposal": ("New proposal: {title}", "Nowa propozycja: {title}"),
    "v2.event.auto": ("Applied automatically: {title}", "Zastosowano automatycznie: {title}"),
    "v2.event.no_change": ("Analysis: no change needed", "Analiza: zmiana niepotrzebna"),
    "v2.event.approved": ("Approved: {title}", "Zatwierdzono: {title}"),
    "v2.event.rejected": ("Rejected: {title}", "Odrzucono: {title}"),
    "v2.event.rejected_why": ("Rejected: {title} ({reason})", "Odrzucono: {title} ({reason})"),
    "v2.event.postponed": ("Postponed: {title}", "Odłożono: {title}"),
    "v2.event.adjusted": ("Adjusted: {title}", "Poprawiono: {title}"),
    "v2.event.expired": ("Expired: {title}", "Wygasła: {title}"),
    "v2.event.superseded": (
        "Replaced after a new report: {title}",
        "Zastąpiona po nowym raporcie: {title}",
    ),
    "v2.event.discarded": ("No longer possible: {title}", "Nieaktualna: {title}"),
    "v2.event.undone": ("Undone: {title}", "Cofnięto: {title}"),
    "v2.event.explained": ("Explanation written", "Napisano wyjaśnienie"),
    # ---- new project (section 8.5)
    "v2.new.title": ("New project", "Nowy projekt"),
    "v2.new.steps": ("Steps", "Kroki"),
    "v2.new.step.basics": ("Basics", "Podstawy"),
    "v2.new.step.team": ("Team", "Zespół"),
    "v2.new.step.tasks": ("Tasks", "Zadania"),
    "v2.new.step.ready": ("Ready", "Gotowe"),
    "v2.new.name": ("Project name", "Nazwa projektu"),
    "v2.new.name_example": ("E.g. “Booking app”", "Np. „Aplikacja rezerwacji”"),
    "v2.new.start": ("Start", "Początek"),
    "v2.new.start_hint": (
        "The first working day of the project.",
        "Pierwszy dzień pracy nad projektem.",
    ),
    "v2.new.deadline": ("Deadline", "Termin"),
    "v2.new.deadline_hint": (
        "By the end of this day everything should be done.",
        "Do końca tego dnia wszystko powinno być gotowe.",
    ),
    "v2.new.more": ("More", "Więcej"),
    "v2.new.days_off": ("Company days off", "Dni wolne w firmie"),
    "v2.new.days_off_hint": (
        "One date per line, e.g. 31.12.2026. Public holidays are counted already.",
        "Jedna data w wierszu, np. 31.12.2026. Święta ustawowe są już uwzględnione.",
    ),
    "v2.new.next": ("Next", "Dalej"),
    "v2.new.back": ("Back", "Wstecz"),
    "v2.new.team_text": (
        "Paste a list or dictate it: one person per line, name and role.",
        "Wklej listę albo ją podyktuj: jedna osoba w wierszu, imię i rola.",
    ),
    "v2.new.team": ("People and roles", "Osoby i role"),
    "v2.new.team_example": (
        "Anna, developer\nBart, developer\nCelina, tester",
        "Anna, programistka\nBartek, programista\nCelina, testerka",
    ),
    "v2.new.team_hint": (
        "Roles group people who can stand in for each other.",
        "Role łączą osoby, które mogą się zastępować.",
    ),
    "v2.new.absence_note": (
        "Sentinel does not ask how often anyone is away. It assumes the Polish average: about "
        "{share} of working days absent, for everyone alike.",
        "Sentinel nie pyta, jak często ktoś bywa nieobecny. Przyjmuje średnią dla Polski: ok. "
        "{share} dni roboczych nieobecności, dla wszystkich jednakowo.",
    ),
    "v2.new.tasks_text": ("How do you want to add the tasks?", "Jak chcesz dodać zadania?"),
    "v2.new.tasks.import": ("Import a spreadsheet", "Zaimportuj arkusz"),
    "v2.new.tasks.import_text": (
        "A CSV file: task, days, people, after which task.",
        "Plik CSV: zadanie, dni, osoby, po jakim zadaniu.",
    ),
    "v2.new.tasks.template": ("Download the example spreadsheet", "Pobierz przykładowy arkusz"),
    "v2.new.tasks.describe": ("Describe in words or by voice", "Opisz słowami lub głosem"),
    "v2.new.tasks.describe_text": (
        "Say what has to be done; the tasks appear for you to confirm.",
        "Powiedz, co trzeba zrobić; zadania pojawią się do potwierdzenia.",
    ),
    "v2.new.tasks.describe_example": (
        "E.g. “First a two-day workshop with the client, then the database and API, about six "
        "days for two developers…”",
        "Np. „Najpierw dwudniowy warsztat z klientem, potem baza danych i API, ok. sześciu dni "
        "dla dwóch programistów…”",
    ),
    "v2.new.tasks.table": ("Type them in a table", "Wpisz w tabeli"),
    "v2.new.tasks.table_text": (
        "Name, days of work, people per role, what it waits for.",
        "Nazwa, dni pracy, osoby z ról, na co czeka.",
    ),
    "v2.new.tasks.file": ("Spreadsheet file (CSV)", "Plik arkusza (CSV)"),
    "v2.new.tasks.upload": ("Import", "Importuj"),
    "v2.new.tasks.read": ("Recognise the tasks", "Rozpoznaj zadania"),
    "v2.new.tasks.reading": ("Listing the tasks…", "Wypisuję zadania…"),
    "v2.new.tasks.confirm": ("Use the ticked tasks", "Użyj zaznaczonych zadań"),
    "v2.new.tasks.add_row": ("Add a task", "Dodaj zadanie"),
    "v2.new.tasks.save_table": ("Use these tasks", "Użyj tych zadań"),
    "v2.new.task.name": ("Task", "Zadanie"),
    "v2.new.task.days": ("Days", "Dni"),
    "v2.new.task.crew": ("People", "Osoby"),
    "v2.new.task.after": ("After", "Po"),
    "v2.new.task.optional": ("Optional", "Opcjonalne"),
    "v2.new.task.card": (
        "“{name}”: {days} days, {crew}{after}",
        "„{name}”: {days} dni, {crew}{after}",
    ),
    "v2.new.task.card_after": ("; after {after}", "; po: {after}"),
    "v2.new.current_tasks": ("Tasks so far", "Dotychczasowe zadania"),
    "v2.new.no_tasks": ("No tasks yet.", "Nie ma jeszcze zadań."),
    "v2.new.make_plan": ("Make the plan", "Ułóż plan"),
    "v2.new.planning": ("Laying out the plan…", "Układam plan…"),
    "v2.new.ready": ("Plan ready: we make it in {n} in 100", "Plan gotowy: zdążymy w {n} na 100"),
    "v2.new.ready_no_deadline": ("Plan ready", "Plan gotowy"),
    "v2.new.budget": ("Budget from the plan: {b} work-days", "Budżet z planu: {b} dni pracy"),
    "v2.new.budget_units": (
        "Budget from the plan: {b} cost units",
        "Budżet z planu: {b} jednostek kosztu",
    ),
    "v2.new.budget_change": ("Change", "Zmień"),
    "v2.new.budget_field": ("Budget (work-days)", "Budżet (dni pracy)"),
    "v2.new.budget_save": ("Save the budget", "Zapisz budżet"),
    "v2.new.open": ("Go to the overview", "Przejdź do pulpitu"),
    "v2.new.saved": ("Saved.", "Zapisano."),
    # ---- the report's form (section 8.3, WP16)
    "v2.form.title": ("Form", "Formularz"),
    "v2.form.hint": (
        "Change what is different from the plan. “Add to report” puts it in step 2, ticked.",
        "Zmień to, co różni się od planu. „Dodaj do raportu” umieści to w kroku 2, zaznaczone.",
    ),
    "v2.form.close": ("Close the form", "Zamknij formularz"),
    "v2.form.tasks": ("Tasks in progress and next", "Zadania w toku i najbliższe"),
    "v2.form.no_tasks": (
        "No task is in progress or about to start.",
        "Żadne zadanie nie trwa ani nie zaczyna się wkrótce.",
    ),
    "v2.form.percent": ("Share done (%)", "Wykonana część (%)"),
    "v2.form.start_hint": (
        "Leave it empty if it started on the report's date.",
        "Zostaw puste, jeśli zaczęło się w dniu raportu.",
    ),
    "v2.form.fix": ("Correct the marked fields.", "Popraw zaznaczone pola."),
    "v2.form.nothing": (
        "The form changes nothing yet: set a task's state or fill in a row.",
        "Formularz jeszcze niczego nie zmienia: ustaw stan zadania albo wypełnij wiersz.",
    ),
    # ---- scenarios: the form's rows and "Co jeśli?" (sections 8.3 and 8.8, WP16)
    "v2.scenario.absence": ("Person absent", "Osoba nieobecna"),
    "v2.scenario.who": ("Who", "Kto"),
    "v2.scenario.pick": ("Choose…", "Wybierz…"),
    "v2.scenario.from": ("From", "Od"),
    "v2.scenario.back": ("Back on", "Wraca"),
    "v2.scenario.back_hint": (
        "The first day back at work; leave it empty if nobody knows yet.",
        "Pierwszy dzień z powrotem w pracy; zostaw puste, jeśli jeszcze nie wiadomo.",
    ),
    "v2.scenario.longer": ("Task takes longer", "Zadanie potrwa dłużej"),
    "v2.scenario.which": ("Which task", "Które zadanie"),
    "v2.scenario.more_days": ("Working days longer", "O ile dni roboczych dłużej"),
    "v2.scenario.more_days_example": ("e.g. 3", "np. 3"),
    "v2.scenario.new": ("New task", "Nowe zadanie"),
    "v2.scenario.name": ("Name", "Nazwa"),
    "v2.scenario.name_example": ("e.g. Payment tests", "np. Testy płatności"),
    "v2.scenario.days": ("Working days", "Dni robocze"),
    "v2.scenario.days_example": ("e.g. 4", "np. 4"),
    "v2.scenario.after": ("After", "Po czym"),
    "v2.scenario.after_none": ("Can start at once", "Może zacząć się od razu"),
    "v2.scenario.role": ("Who (role)", "Kto (rola)"),
    "v2.scenario.role_none": ("Nobody from the team", "Nikt z zespołu"),
    "v2.lab.add": ("Add to report", "Dodaj do raportu"),
}


class TextsV2(Texts):
    """The texts of the v2 pages: a v2 key, else a key of the first interface."""

    def __call__(self, key: str, **params: object) -> str:
        entry = CATALOGUE.get(key) or V1_CATALOGUE.get(key)
        if entry is None:
            return f"⟦{key}⟧"
        text = entry[self._index]
        try:
            return text.format(**params) if params else text
        except (KeyError, IndexError, ValueError):
            return f"⟦{key}⟧"

    def hundred(self, n: int) -> str:
        """A chance as a natural frequency: "39 in 100" ("39 na 100")."""
        return self("v2.chance.value", n=n)
