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
        "The best option of another kind, {option}, would give less ({chance} in 100) at a cost "
        "of {price}.",
        "Najlepsza możliwość innego rodzaju, {option}, dałaby mniej ({chance} na 100) przy "
        "koszcie {price}.",
    ),
    "v2.why.alt_close": (
        "{option} would give a similar result too; {part}.",
        "Podobny wynik dałoby też {option}; {part}.",
    ),
    "v2.why.simpler": ("the simpler option was chosen", "wybrano prostsze rozwiązanie"),
    "v2.why.alt_similar": (
        "The best option of another kind, {option}, would give {chance} in 100; {tie}.",
        "Najlepsza możliwość innego rodzaju, {option}, dałaby {chance} na 100; {tie}.",
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
    "v2.card.absence_later": (
        "This absence will start to count in the report of {date}.",
        "Ta nieobecność zacznie się liczyć w raporcie {date}.",
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
    # ---- Laboratorium (section 8.8, WP16)
    "v2.lab.title": ("Lab", "Laboratorium"),
    "v2.lab.tabs": ("Parts of the lab", "Części laboratorium"),
    "v2.lab.whatif": ("What if?", "Co jeśli?"),
    "v2.lab.sim": ("Simulator", "Symulator"),
    "v2.lab.whatif_intro": (
        "Try what a change would do to a project. Nothing is saved until you add it to a report.",
        "Sprawdź, co zmiana zrobiłaby z projektem. Nic się nie zapisze, dopóki nie dodasz tego "
        "do raportu.",
    ),
    "v2.lab.project": ("Project", "Projekt"),
    "v2.lab.no_project": ("No project with a plan", "Brak projektu z planem"),
    "v2.lab.no_project_text": (
        "“What if?” works on a project with a plan. Start one, or open the example project.",
        "„Co jeśli?” działa na projekcie z planem. Utwórz projekt albo otwórz przykładowy.",
    ),
    "v2.lab.as_of": ("as at the report of {date}", "według raportu z {date}"),
    "v2.lab.whatif_hint": (
        "Fill in one or more rows, then check the effect.",
        "Wypełnij jeden lub więcej wierszy, potem sprawdź wpływ.",
    ),
    "v2.lab.check": ("Check the effect", "Sprawdź wpływ"),
    "v2.lab.impact_empty": (
        "The effect on the chance, the end and the budget appears here.",
        "Tu pojawi się wpływ na szansę, koniec i budżet.",
    ),
    "v2.lab.nothing": (
        "Fill in at least one row: who is absent, which task takes longer or a new task.",
        "Wypełnij co najmniej jeden wiersz: kto będzie nieobecny, które zadanie potrwa dłużej "
        "albo nowe zadanie.",
    ),
    "v2.lab.later": (
        "An absence counts in the forecast from its first day, so one from {date} shows in the "
        "report of that day. To see its effect now, set “From” to {first}.",
        "Nieobecność liczy się w prognozie od swojego pierwszego dnia, więc ta od {date} pojawi "
        "się w raporcie z tego dnia. Aby zobaczyć jej wpływ teraz, ustaw „Od” na {first}.",
    ),
    "v2.lab.not_saved": (
        "Nothing was saved. “Add to report” opens the report with these changes ticked.",
        "Nic nie zostało zapisane. „Dodaj do raportu” otworzy raport z tymi zmianami zaznaczonymi.",
    ),
    "v2.lab.sim_intro": (
        "Watch Sentinel run an example project day by day, next to the same project where nobody "
        "reacts. Both meet the same events.",
        "Zobacz, jak Sentinel prowadzi przykładowy projekt dzień po dniu, obok tego samego "
        "projektu, w którym nikt nie reaguje. Oba spotykają te same zdarzenia.",
    ),
    "v2.lab.runs": ("Your simulations", "Twoje symulacje"),
    "v2.lab.finished": ("finished", "zakończona"),
    "v2.lab.new_sim": ("New simulation", "Nowa symulacja"),
    "v2.lab.level": ("Disruptions", "Zakłócenia"),
    "v2.lab.level.low": ("Few disruptions", "Mało zakłóceń"),
    "v2.lab.level.high": ("Many disruptions", "Dużo zakłóceń"),
    "v2.lab.level_hint": (
        "Absences, tasks longer than planned and new work, drawn at random but the same for "
        "both runs.",
        "Nieobecności, zadania dłuższe niż w planie i nowa praca, losowane, ale te same dla obu "
        "przebiegów.",
    ),
    "v2.lab.pair": (
        "Sentinel runs the project; beside it the same project runs with no reaction.",
        "Sentinel prowadzi projekt; obok ten sam projekt toczy się bez reakcji.",
    ),
    "v2.lab.pair_short": ("Sentinel against no reaction", "Sentinel wobec braku reakcji"),
    "v2.lab.start": ("Start the simulation", "Uruchom symulację"),
    "v2.lab.preparing": ("Preparing the simulation…", "Przygotowuję symulację…"),
    "v2.lab.running": ("Simulating the days…", "Symuluję kolejne dni…"),
    "v2.lab.result": ("Result", "Wynik"),
    "v2.lab.same_events": (
        "Both runs met the same events: the difference is what Sentinel's decisions did.",
        "Oba przebiegi spotkały te same zdarzenia: różnica to skutek decyzji Sentinela.",
    ),
    "v2.lab.chance": (
        "Sentinel: {n} in 100 of meeting the deadline ({date})",
        "Sentinel: {n} na 100, że zdążymy ({date})",
    ),
    "v2.lab.step.1": ("+1 day", "+1 dzień"),
    "v2.lab.step.5": ("+5 days", "+5 dni"),
    "v2.lab.step.end": ("To the end", "Do końca"),
    "v2.lab.side.sentinel": ("Sentinel", "Sentinel"),
    "v2.lab.side.no_reaction": ("No reaction", "Bez reakcji"),
    "v2.lab.tasks": ("Tasks done", "Zadania skończone"),
    "v2.lab.late": ("late", "po terminie"),
    "v2.lab.cost": ("{cost} ({share} of the budget)", "{cost} ({share} budżetu)"),
    "v2.lab.events": ("What happened", "Co się wydarzyło"),
    "v2.lab.no_events": ("Nothing has happened yet.", "Jeszcze nic się nie wydarzyło."),
    # ---- Ustawienia (section 8.10, WP16)
    "v2.settings.title": ("Settings", "Ustawienia"),
    "v2.settings.saved": ("Settings saved.", "Zapisano ustawienia."),
    "v2.settings.default": ("default", "domyślny"),
    "v2.settings.theme_hint": (
        "Remembered in this browser.",
        "Zapamiętany w tej przeglądarce.",
    ),
    "v2.settings.ai": ("AI model", "Model AI"),
    "v2.settings.ai_demo": (
        "In the demo the AI model is set by its owner; your own copy lets you choose it here.",
        "W pokazie model AI ustawia jego właściciel; we własnej kopii wybierzesz go tutaj.",
    ),
    "v2.settings.ai_now.cloud": ("Now: the cloud ({model}).", "Teraz: chmura ({model})."),
    "v2.settings.ai_now.local": (
        "Now: a local model ({model}).",
        "Teraz: model lokalny ({model}).",
    ),
    "v2.settings.ai_now.none": (
        "Now: no AI. Reports are read from the form; the rest works as usual.",
        "Teraz: bez AI. Raporty wypełniasz formularzem; reszta działa jak zwykle.",
    ),
    "v2.settings.ai_choose": ("Which model reads the reports?", "Który model czyta raporty?"),
    "v2.settings.cloud": ("Cloud (recommended)", "Chmura (zalecany)"),
    "v2.settings.cloud_text": ("More accurate", "Dokładniejszy"),
    "v2.settings.local": ("Local", "Lokalny"),
    "v2.settings.local_text": (
        "The data stay in the company; slower",
        "Dane nie wychodzą z firmy; wolniejszy",
    ),
    "v2.settings.none": ("No AI", "Bez AI"),
    "v2.settings.none_text": ("Reports by the form only", "Raporty tylko formularzem"),
    "v2.settings.key": ("Cloud key", "Klucz do chmury"),
    "v2.settings.key_example": ("e.g. sk-or-…", "np. sk-or-…"),
    "v2.settings.key_saved": ("saved, hidden", "zapisany, ukryty"),
    "v2.settings.key_hint": (
        "Stored only on this computer and never shown again. Leave it empty to keep the saved one.",
        "Zapisany tylko na tym komputerze i nigdy więcej niepokazywany. Zostaw puste, by zachować "
        "zapisany.",
    ),
    "v2.settings.forget": ("Remove the saved key", "Usuń zapisany klucz"),
    "v2.settings.host": ("Address of the local model", "Adres modelu lokalnego"),
    "v2.settings.host_hint": (
        "Only for “Local”; empty means this computer.",
        "Tylko dla „Lokalny”; puste oznacza ten komputer.",
    ),
    "v2.settings.voice_key": ("Key for dictation (Groq)", "Klucz do dyktowania (Groq)"),
    "v2.settings.voice_hint": (
        "Turns the microphone on; recordings are written out and never stored.",
        "Włącza mikrofon; nagrania są zamieniane na tekst i nigdy nie zapisywane.",
    ),
    "v2.settings.save": ("Save settings", "Zapisz ustawienia"),
    "v2.psettings.basics": ("Basics", "Podstawy"),
    "v2.psettings.name": ("Project name", "Nazwa projektu"),
    "v2.psettings.deadline": ("Deadline", "Termin"),
    "v2.psettings.budget": ("Budget (work-days)", "Budżet (dni pracy)"),
    "v2.psettings.budget_hint": (
        "Empty: the budget follows from the plan.",
        "Puste: budżet wynika z planu.",
    ),
    "v2.psettings.start": ("Start", "Start"),
    "v2.psettings.save": ("Save", "Zapisz"),
    "v2.psettings.team": ("Team", "Zespół"),
    "v2.psettings.team_fixed": (
        "The team is fixed from the first report on; report absences in the report.",
        "Zespół jest stały od pierwszego raportu; nieobecności zgłaszasz w raporcie.",
    ),
    "v2.psettings.team_edit": (
        "Until the first report the team can still change.",
        "Do pierwszego raportu zespół możesz jeszcze zmienić.",
    ),
    "v2.psettings.team_link": ("Change the team", "Zmień zespół"),
    "v2.psettings.days_off": ("Company days off", "Dni wolne w firmie"),
    "v2.psettings.holidays": (
        "Polish public holidays are already left out of the working days.",
        "Polskie święta są już pominięte w dniach roboczych.",
    ),
    "v2.psettings.days_off_none": ("None.", "Brak."),
    "v2.psettings.days_off_fixed": (
        "The project's calendar is fixed from the first report on.",
        "Kalendarz projektu jest stały od pierwszego raportu.",
    ),
    "v2.psettings.days_off_field": ("Day off", "Dzień wolny"),
    "v2.psettings.days_off_add": ("Add the day off", "Dodaj dzień wolny"),
    "v2.psettings.days_off_remove": ("Remove {date}", "Usuń {date}"),
    "v2.psettings.days_off_full": ("At most {n} days off.", "Najwyżej {n} dni wolnych."),
    "v2.psettings.days_off_hint": (
        "Nobody works on these days; they can change until the first report.",
        "W te dni nikt nie pracuje; można je zmieniać do pierwszego raportu.",
    ),
    "v2.psettings.calendar": ("Calendar", "Kalendarz"),
    "v2.psettings.reminder": ("Weekly report reminder", "Przypomnienie o raporcie"),
    "v2.psettings.reminder_day": ("Day", "Dzień"),
    "v2.psettings.reminder_time": ("Hour", "Godzina"),
    "v2.psettings.reminder_hint": (
        "Thursday 17:00 by default; it appears in the calendar and as the next report's day.",
        "Domyślnie czwartek 17:00; pojawia się w kalendarzu i jako dzień następnego raportu.",
    ),
    "v2.psettings.reminder_error": (
        "Choose a working day and an hour such as 17:00.",
        "Wybierz dzień roboczy i godzinę, np. 17:00.",
    ),
    "v2.psettings.exports": ("Exports", "Eksport"),
    "v2.psettings.export_json": ("Download the project (JSON)", "Pobierz projekt (JSON)"),
    "v2.psettings.print": ("Report to print", "Raport do druku"),
    "v2.psettings.how": ("How Sentinel makes decisions", "Jak Sentinel podejmuje decyzje"),
    "v2.psettings.how_text": (
        "Sentinel gathers information, analyses the project and prepares decisions. You approve "
        "every change.",
        "Sentinel zbiera informacje, analizuje projekt i przygotowuje decyzje. Każdą zmianę "
        "zatwierdzasz Ty.",
    ),
    "v2.psettings.delete": ("Delete project", "Usuń projekt"),
    "v2.psettings.delete_text": (
        "The project, its log and its calendar link are deleted for good.",
        "Projekt, jego dziennik i link do kalendarza zostaną usunięte na zawsze.",
    ),
    "v2.psettings.delete_sure": (
        "Delete “{name}”? This cannot be undone.",
        "Usunąć „{name}”? Tego nie da się cofnąć.",
    ),
    "v2.psettings.delete_confirm": ("Delete for good", "Usuń na zawsze"),
    "v2.psettings.deleted": ("Project deleted.", "Usunięto projekt."),
    "v2.psettings.saved.basics": ("Basics saved.", "Zapisano podstawy."),
    "v2.psettings.saved.days_off": ("Days off saved.", "Zapisano dni wolne."),
    "v2.psettings.saved.reminder": ("Reminder saved.", "Zapisano przypomnienie."),
    "v2.psettings.saved.calendar": ("Calendar link ready.", "Link do kalendarza gotowy."),
    "v2.psettings.saved.revoked": (
        "Calendar link revoked: it no longer works.",
        "Unieważniono link do kalendarza: już nie działa.",
    ),
    # ---- Kalendarz (section 8.9, WP16; ADR-0035)
    "v2.cal.intro": (
        "Add the project to your calendar: the deadline, the starts and ends of tasks, absences, "
        "the validity dates of decisions and the report reminder.",
        "Dodaj projekt do swojego kalendarza: termin, początki i końce zadań, nieobecności, daty "
        "ważności decyzji i przypomnienie o raporcie.",
    ),
    "v2.cal.warning": (
        "Whoever has this link sees people's names and the dates of their absences.",
        "Kto ma ten link, widzi imiona osób i daty nieobecności.",
    ),
    "v2.cal.make": ("Create the calendar link", "Utwórz link do kalendarza"),
    "v2.cal.link": ("Calendar link", "Link do kalendarza"),
    "v2.cal.copy": ("Copy the calendar link", "Kopiuj link do kalendarza"),
    "v2.cal.copied": ("Copied.", "Skopiowano."),
    "v2.cal.revoke": ("Revoke the link", "Unieważnij link"),
    "v2.cal.google": ("Google Calendar", "Kalendarz Google"),
    "v2.cal.google.1": (
        "Open calendar.google.com on a computer.",
        "Otwórz calendar.google.com na komputerze.",
    ),
    "v2.cal.google.2": (
        "Next to “Other calendars” click “+” and choose “From URL”.",
        "Przy „Inne kalendarze” kliknij „+” i wybierz „Z adresu URL”.",
    ),
    "v2.cal.google.3": (
        "Paste the link and click “Add calendar”.",
        "Wklej link i kliknij „Dodaj kalendarz”.",
    ),
    "v2.cal.icloud": ("iCloud (Mac, iPhone)", "iCloud (Mac, iPhone)"),
    "v2.cal.icloud.1": (
        "On a Mac open Calendar, then File → New Calendar Subscription.",
        "Na Macu otwórz Kalendarz, potem Plik → Nowa subskrypcja kalendarza.",
    ),
    "v2.cal.icloud.2": (
        "Paste the link and click “Subscribe”.",
        "Wklej link i kliknij „Subskrybuj”.",
    ),
    "v2.cal.icloud.3": (
        "Under “Location” choose iCloud to see it on the iPhone too, then click OK.",
        "W polu „Położenie” wybierz iCloud, by widzieć go też na iPhonie, i kliknij OK.",
    ),
    "v2.cal.refresh": (
        "Calendars refresh such a link every few hours, so changes show up later.",
        "Kalendarze odświeżają taki link co kilka godzin, więc zmiany pojawią się później.",
    ),
    "v2.cal.demo": (
        "In the demo the link works while your demo session lasts.",
        "W pokazie link działa, dopóki trwa Twoja sesja pokazu.",
    ),
    "v2.cal.name": ("Sentinel: {project}", "Sentinel: {project}"),
    "v2.cal.deadline": ("Deadline: {project}", "Termin: {project}"),
    "v2.cal.start": ("Start: {task}", "Start: {task}"),
    "v2.cal.end": ("End: {task}", "Koniec: {task}"),
    "v2.cal.away": ("Away: {name}", "Nieobecność: {name}"),
    "v2.cal.away_open": ("Away: {name} (return unknown)", "Nieobecność: {name} (powrót nieznany)"),
    "v2.cal.valid": ("Decision valid until today: {title}", "Decyzja ważna do dziś: {title}"),
    "v2.cal.report": ("Weekly report: {project}", "Raport tygodniowy: {project}"),
    "v2.cal.report_text": (
        "Open Sentinel and save the report: what has changed since the last one.",
        "Otwórz Sentinel i zapisz raport: co się zmieniło od ostatniego.",
    ),
    "v2.weekday.0": ("Monday", "poniedziałek"),
    "v2.weekday.1": ("Tuesday", "wtorek"),
    "v2.weekday.2": ("Wednesday", "środa"),
    "v2.weekday.3": ("Thursday", "czwartek"),
    "v2.weekday.4": ("Friday", "piątek"),
    # ---- Dziennik (section 8.6, WP16)
    "v2.log.title": ("Log", "Dziennik"),
    "v2.log.filters": ("Kinds of entries", "Rodzaje wpisów"),
    "v2.log.filter.all": ("Everything", "Wszystko"),
    "v2.log.filter.decisions": ("Decisions", "Decyzje"),
    "v2.log.filter.reports": ("Reports", "Raporty"),
    "v2.log.filter.plan": ("Plan changes", "Zmiany planu"),
    "v2.log.download": ("Download the log (CSV)", "Pobierz dziennik (CSV)"),
    "v2.log.projects": ("Projects in the log", "Projekty w dzienniku"),
    "v2.log.all_projects": ("All projects", "Wszystkie projekty"),
    "v2.log.chart.title": ("Chance over time", "Szansa w czasie"),
    "v2.log.chart.hint": (
        "Click a dot to see its entry.",
        "Kliknij kropkę, aby zobaczyć jej wpis.",
    ),
    "v2.log.chart.plan": ("plan", "plan"),
    "v2.log.chart.pick": (
        "Choose a project to see its chance over time.",
        "Wybierz projekt, aby zobaczyć jego szansę w czasie.",
    ),
    "v2.log.chart.dot": ("{what}: {n} in 100", "{what}: {n} na 100"),
    "v2.log.entries": ("Entries", "Wpisy"),
    "v2.log.today": ("Today", "Dziś"),
    "v2.log.brief": ("The decision at that moment", "Decyzja w tamtej chwili"),
    "v2.log.fate": ("Decision status", "Stan decyzji"),
    "v2.log.open_decision": ("Open the decision", "Otwórz decyzję"),
    "v2.log.none_shown": ("No entries of this kind.", "Brak wpisów tego rodzaju."),
    "v2.log.empty": (
        "The log is empty: every report, decision and plan change will appear here.",
        "Dziennik jest pusty: pojawi się tu każdy raport, decyzja i zmiana planu.",
    ),
    "v2.log.csv.file": ("log.csv", "dziennik.csv"),
    "v2.log.csv.date": ("date", "data"),
    "v2.log.csv.time": ("time", "godzina"),
    "v2.log.csv.project": ("project", "projekt"),
    "v2.log.csv.who": ("who", "kto"),
    "v2.log.csv.kind": ("kind", "rodzaj"),
    "v2.log.csv.event": ("event", "zdarzenie"),
    "v2.log.csv.before": ("chance before (in 100)", "szansa przed (na 100)"),
    "v2.log.csv.after": ("chance after (in 100)", "szansa po (na 100)"),
    "v2.log.csv.fate": ("decision status", "stan decyzji"),
    "v2.log.csv.reason": ("reason", "powód"),
    "v2.log.csv.words": ("words", "słowa"),
    # ---- Plan (section 8.7, WP16)
    "v2.plan.title": ("Plan", "Plan"),
    "v2.plan.views": ("Views of the plan", "Widoki planu"),
    "v2.plan.view.schedule": ("Schedule", "Harmonogram"),
    "v2.plan.view.tasks": ("Tasks", "Zadania"),
    "v2.plan.view.team": ("Team", "Zespół"),
    "v2.plan.download": ("Download the plan (CSV)", "Pobierz plan (CSV)"),
    "v2.plan.none": ("No plan yet", "Brak planu"),
    "v2.plan.none_text": (
        "Add the team and the tasks, then Sentinel lays out the plan.",
        "Dodaj zespół i zadania, a Sentinel ułoży plan.",
    ),
    "v2.plan.make": ("Finish the project", "Dokończ projekt"),
    "v2.plan.band": (
        "Forecast: most likely {likely}, in a bad case {bad}",
        "Prognoza: najpewniej {likely}, w złym razie {bad}",
    ),
    "v2.plan.risks_wait": ("Looking for the main risks…", "Szukam głównych ryzyk…"),
    "v2.plan.risk": ("risk", "ryzyko"),
    "v2.plan.risk_tip": (
        "“{name}” is one of the main risks: the longer it takes, the later the project ends.",
        "„{name}” to jedno z głównych ryzyk: im dłużej trwa, tym później koniec projektu.",
    ),
    "v2.plan.legend": ("Legend", "Legenda"),
    "v2.plan.legend.running": ("In progress", "W toku"),
    "v2.plan.legend.band": (
        "Forecast: most likely to bad case",
        "Prognoza: od najpewniej do złego razu",
    ),
    "v2.plan.crew": ("{n} × {role}", "{n} × {role}"),
    "v2.plan.col.task": ("Task", "Zadanie"),
    "v2.plan.col.state": ("State", "Stan"),
    "v2.plan.col.end": ("End", "Koniec"),
    "v2.plan.col.people": ("Who", "Kto"),
    "v2.plan.col.after": ("Depends on", "Zależy od"),
    "v2.plan.col.fix": ("Correction", "Poprawka"),
    "v2.plan.fix_hint": (
        "A task not started yet can be corrected.",
        "Zadanie, które się jeszcze nie zaczęło, możesz poprawić.",
    ),
    "v2.plan.fix_later": (
        "Tasks not started yet can be corrected here after the first report.",
        "Zadania, które się jeszcze nie zaczęły, poprawisz tu po pierwszym raporcie.",
    ),
    "v2.plan.days": ("Working days", "Dni robocze"),
    "v2.plan.people_of": ("People: {role}", "Osoby: {role}"),
    "v2.plan.after_which": ("Starts after", "Zaczyna się po"),
    "v2.plan.optional": (
        "Optional (can be dropped if time runs short)",
        "Opcjonalne (można z niego zrezygnować, gdy zabraknie czasu)",
    ),
    "v2.plan.save_fix": ("Save the correction", "Zapisz poprawkę"),
    "v2.plan.days_error": (
        "Give whole working days, 1 or more.",
        "Podaj liczbę dni roboczych: 1 lub więcej.",
    ),
    "v2.plan.crew_error": (
        "Give a whole number, 0 or more.",
        "Podaj liczbę całkowitą: 0 lub więcej.",
    ),
    "v2.plan.corrected": (
        "Correction saved. The forecast follows it.",
        "Zapisano poprawkę. Prognoza ją uwzględnia.",
    ),
    "v2.plan.week": ("Next week: {first} – {last}", "Przyszły tydzień: {first} – {last}"),
    "v2.plan.team_hint": (
        "“Next week”: on how many working days the plan needs the person's role, per person "
        "present. Workload comes from the plan; Sentinel measures nobody's performance.",
        "„Przyszły tydzień”: w ilu dniach roboczych plan potrzebuje roli tej osoby, na osobę "
        "obecną. Obciążenie wynika z planu; Sentinel nie mierzy niczyjej wydajności.",
    ),
    "v2.plan.col.person": ("Person", "Osoba"),
    "v2.plan.col.away": ("Absences", "Nieobecności"),
    "v2.plan.col.now": ("Now", "Teraz"),
    "v2.plan.col.next": ("Next for the role", "Następne dla roli"),
    "v2.plan.col.load": ("Next week", "Przyszły tydzień"),
    "v2.plan.temporary": ("temporary", "tymczasowo"),
    "v2.plan.away": ("{first} – back {back}", "{first} – wraca {back}"),
    "v2.plan.away_open": ("from {first}, return unknown", "od {first}, powrót nieznany"),
    "v2.plan.load_away": ("absent all week", "nieobecność cały tydzień"),
    "v2.plan.load.one": ("about {busy} of {n} day", "ok. {busy} z {n} dnia"),
    "v2.plan.load.few": ("about {busy} of {n} days", "ok. {busy} z {n} dni"),
    "v2.plan.load.many": ("about {busy} of {n} days", "ok. {busy} z {n} dni"),
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
