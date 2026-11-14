"""The texts of the v2 interface (WP15; docs/design/v2-spec.md, section 6): both languages with
the same placeholders, every key the v2 templates and code use, no internal term, and the
glossary's labels exactly as the spec quotes them. WP21 (docs/design/v3-spec.md, section 10):
no dash as a pause in any of our texts, and the text budget of headings and helper sentences."""

import re
import string
from pathlib import Path

from ui_check import pauses, problems

from sentinel.app.messages import MESSAGES
from sentinel.app.ui.text import CATALOGUE as V1
from sentinel.app.ui.v2.text import CATALOGUE, TextsV2
from sentinel.evidence import research

UI = Path(__file__).parents[1] / "src/sentinel/app/ui"
# Keys built from a prefix and a value in the v2 templates and code.
FAMILIES = {
    "v2.nav.": ("start", "projects", "log", "lab", "settings", "map", "permissions", "people"),
    "v2.nav.group.": ("work", "rules", "other"),
    "v2.theme.": ("light", "dark", "system"),
    "v2.tab.": ("overview", "report", "decisions", "log", "plan", "settings"),
    "v2.state.": ("good", "warn", "bad", "none", "draft", "finished"),
    "v2.verdict.": ("good_zero", "warn_zero"),
    "v2.buffer.zone.": ("good", "warn", "bad"),
    "v2.life.": (
        "pending",
        "approved",
        "rejected",
        "postponed",
        "adjusted",
        "expired",
        "superseded",
        "discarded",
        "auto",
        "undone",
    ),
    "v2.reject.": ("too_expensive", "unavailable", "no_budget", "other"),
    "v2.dec.need.": ("people", "money", "scope", "plan"),
    "v2.causes.": ("absence", "growth", "new_task", "progress"),
    "v2.hint.": ("absent", "done", "longer", "new"),
    "v2.new.step.": ("basics", "team", "tasks", "ready"),
    "v2.promise.": ("deadline", "budget", "settings", "replanned"),
    "v2.log.filter.": ("all", "decisions", "reports", "plan"),
    "v2.log.csv.": (
        *("date", "time", "project", "who", "kind", "event"),
        *("before", "after", "fate", "reason", "words"),
    ),
    "v2.plan.view.": ("schedule", "tasks", "team"),
    "v2.lab.level.": ("low", "high"),
    "v2.lab.side.": ("sentinel", "no_reaction"),
    "v2.lab.step.": ("1", "5", "end"),
    "v2.settings.ai_now.": ("cloud", "local", "none"),
    "v2.psettings.saved.": ("basics", "days_off", "reminder", "calendar", "revoked", "assessment"),
    # v3 (WP19)
    "v2.zone.": ("ai_samodzielnie", "ai_z_czlowiekiem", "tylko_czlowiek"),
    "v2.zone.short.": ("ai_samodzielnie", "ai_z_czlowiekiem", "tylko_czlowiek"),
    "v2.ev.stance.": ("wspiera", "podwaza", "niuansuje"),
    "v2.ev.basis.": ("empirical", "normative", "theoretical"),
    "v2.module.": ("projekty", "raporty", "finanse", "ludzie", "uprawnienia", "mapa"),
    "v2.kind.": ("empirical", "theoretical", "law", "standard", "industry", "own"),
    "v2.perm.may.": ("read", "format"),
    "v2.perm.not.": ("save", "send", "approve", "compute", "choose", "connect", "projects"),
    "v2.perm.role.": ("extract", "propose", "explain", "read", "test", "attack"),
    "v2.perm.error.": ("limit", "unavailable", "failed"),
    "v2.perm.model.": ("cloud", "local", "none"),
    "v2.perm.leaves.": ("cloud", "local", "none", "voice"),
    "v2.people.absent.": ("performance", "ranking", "mood", "reasons"),
    "v2.people.why.": ("performance", "ranking", "mood", "reasons"),
    "v2.weekday.": ("0", "1", "2", "3", "4"),
    "v2.cal.google.": ("1", "2", "3"),
    "v2.cal.icloud.": ("1", "2", "3"),
}
# The labels of the glossary (section 6), Polish and English, exactly.
GLOSSARY = {
    "v2.start.title": ("Projects", "Projekty"),
    "v2.start.decisions": ("Decisions to make", "Decyzje do podjęcia"),
    "v2.start.events": ("Recent events", "Ostatnie zdarzenia"),
    "v2.tab.overview": ("Overview", "Pulpit"),
    "v2.tab.report": ("Report", "Raport"),
    "v2.tab.decisions": ("Decisions", "Decyzje"),
    "v2.tab.log": ("Log", "Dziennik"),
    "v2.tab.plan": ("Plan", "Plan"),
    "v2.tab.settings": ("Project settings", "Ustawienia projektu"),
    "v2.chance.title": ("Chance of the deadline", "Szansa na termin"),
    "v2.chance.help": ("Where does this number come from?", "Skąd ta liczba?"),
    "v2.end.title": ("Project end", "Koniec projektu"),
    "v2.end.likely": ("most likely", "najpewniej"),
    "v2.end.bad": ("in a bad case", "w złym razie"),
    "v2.budget.title": ("Budget", "Budżet"),
    "v2.decision.title": ("Decision to make", "Decyzja do podjęcia"),
    "v2.decision.valid": ("valid until {date}", "ważna do {date}"),
    "v2.buffer.title": ("Time reserve", "Zapas czasu"),
    "v2.week.title": ("Next 7 days", "Najbliższe 7 dni"),
    "v2.causes.title": ("Causes of the change", "Przyczyny zmiany"),
    "v2.risks.title": ("Main risks", "Główne ryzyka"),
    "v2.report.step1": ("Events since the last report", "Zdarzenia od ostatniego raportu"),
    "v2.report.planned": ("Progress as planned", "Postęp zgodny z planem"),
    "v2.report.step2": ("To confirm", "Do potwierdzenia"),
    "v2.report.step2_hint": (
        "Tick the changes that are right.",
        "Zaznacz zmiany, które się zgadzają.",
    ),
    "v2.report.unparsed": ("Unrecognised parts", "Nierozpoznane fragmenty"),
    "v2.report.step3": ("Effect on the project", "Wpływ na projekt"),
    "v2.report.save": ("Save report", "Zapisz raport"),
    "v2.report.form": ("Fill in the form", "Wypełnij formularz"),
    "v2.approve": ("Approve", "Zatwierdź"),
    "v2.reject": ("Reject", "Odrzuć"),
    "v2.adjust": ("Adjust", "Popraw"),
    "v2.postpone": ("Postpone", "Odłóż decyzję"),
    "v2.dec.effect": ("Effect", "Skutek"),
    "v2.dec.reasoning": ("Reasoning", "Uzasadnienie"),
    "v2.dec.who": ("Who is affected", "Kogo dotyczy"),
    "v2.dec.delay": ("Cost of delay", "Koszt zwłoki"),
    "v2.details": ("Details", "Szczegóły"),
    "v2.reject.too_expensive": ("Too expensive", "Za drogo"),
    "v2.reject.unavailable": ("Person unavailable", "Osoba niedostępna"),
    "v2.reject.no_budget": ("No budget", "Brak środków"),
    "v2.reject.other": ("Other reason", "Inny powód"),
    "v2.reject.confirm": ("Confirm rejection", "Potwierdź odrzucenie"),
    "v2.dec.need.people": (
        "It affects people, so it needs your approval.",
        "Dotyczy ludzi, dlatego wymaga Twojej zgody.",
    ),
    "v2.theme": ("Appearance", "Wygląd"),
    "v2.theme.light": ("Light", "Jasny"),
    "v2.theme.dark": ("Dark", "Ciemny"),
    "v2.theme.system": ("System", "Systemowy"),
    "v2.nav.log": ("Log", "Dziennik"),
    "v2.nav.lab": ("Lab", "Laboratorium"),
    # WP16: sections 6 and 8.6-8.10
    "v2.lab.title": ("Lab", "Laboratorium"),
    "v2.lab.whatif": ("What if?", "Co jeśli?"),
    "v2.lab.sim": ("Simulator", "Symulator"),
    "v2.lab.level.low": ("Few disruptions", "Mało zakłóceń"),
    "v2.lab.level.high": ("Many disruptions", "Dużo zakłóceń"),
    "v2.lab.add": ("Add to report", "Dodaj do raportu"),
    "v2.lab.side.sentinel": ("Sentinel", "Sentinel"),
    "v2.lab.side.no_reaction": ("No reaction", "Bez reakcji"),
    "v2.lab.step.1": ("+1 day", "+1 dzień"),
    "v2.lab.step.5": ("+5 days", "+5 dni"),
    "v2.lab.step.end": ("To the end", "Do końca"),
    "v2.scenario.absence": ("Person absent", "Osoba nieobecna"),
    "v2.scenario.longer": ("Task takes longer", "Zadanie potrwa dłużej"),
    "v2.scenario.new": ("New task", "Nowe zadanie"),
    "v2.log.filter.all": ("Everything", "Wszystko"),
    "v2.log.filter.decisions": ("Decisions", "Decyzje"),
    "v2.log.filter.reports": ("Reports", "Raporty"),
    "v2.log.filter.plan": ("Plan changes", "Zmiany planu"),
    "v2.log.chart.title": ("Chance over time", "Szansa w czasie"),
    "v2.log.download": ("Download the log (CSV)", "Pobierz dziennik (CSV)"),
    "v2.plan.view.schedule": ("Schedule", "Harmonogram"),
    "v2.plan.view.tasks": ("Tasks", "Zadania"),
    "v2.plan.view.team": ("Team", "Zespół"),
    "v2.plan.download": ("Download the plan (CSV)", "Pobierz plan (CSV)"),
    "v2.cal.copy": ("Copy the calendar link", "Kopiuj link do kalendarza"),
    "v2.cal.revoke": ("Revoke the link", "Unieważnij link"),
    "v2.cal.warning": (
        "Whoever has this link sees people's names and the dates of their absences.",
        "Kto ma ten link, widzi imiona osób i daty nieobecności.",
    ),
    "v2.settings.ai": ("AI model", "Model AI"),
    "v2.settings.cloud": ("Cloud (recommended)", "Chmura (zalecany)"),
    "v2.settings.local": ("Local", "Lokalny"),
    "v2.psettings.calendar": ("Calendar", "Kalendarz"),
    "v2.psettings.how": ("How Sentinel makes decisions", "Jak Sentinel podejmuje decyzje"),
    "v2.psettings.how_text": (
        "Sentinel gathers information, analyses the project and prepares decisions. You approve "
        "every change.",
        "Sentinel zbiera informacje, analizuje projekt i przygotowuje decyzje. Każdą zmianę "
        "zatwierdzasz Ty.",
    ),
    "v2.psettings.delete": ("Delete project", "Usuń projekt"),
    # WP19: docs/design/v3-spec.md, sections 1 to 6
    "v2.nav.group.work": ("Work", "Praca"),
    "v2.nav.group.rules": ("AI rules", "Zasady AI"),
    "v2.nav.group.other": ("Other", "Inne"),
    "v2.nav.map": ("Boundary map", "Mapa granic"),
    "v2.nav.permissions": ("AI permissions", "Uprawnienia AI"),
    "v2.nav.people": ("People", "Ludzie"),
    "v2.nav.sources": ("Sources", "Źródła"),
    "v2.ev.point": ("Evidence for this decision ({n})", "Dowody dla tej decyzji ({n})"),
    "v2.ev.decision": ("Decision", "Decyzja"),
    "v2.ev.basis.empirical": ("research", "badania"),
    "v2.ev.basis.normative": ("law and standards", "prawo i normy"),
    "v2.ev.basis.theoretical": ("theory", "teoria"),
    "v2.ev.stance.wspiera": ("supports", "wspiera"),
    "v2.ev.stance.podwaza": ("challenges", "podważa"),
    "v2.ev.stance.niuansuje": ("nuances", "niuansuje"),
    "v2.ev.did": ("What the researchers did", "Co zrobili badacze"),
    "v2.ev.means": ("What follows for Sentinel", "Co z tego wynika dla Sentinela"),
    "v2.ev.open_access": ("open access", "otwarty dostęp"),
    "v2.ev.unverified": (
        "Quote not verified: summary only",
        "Cytat niezweryfikowany: tylko streszczenie",
    ),
    "v2.map.thesis": (
        "Not “AI where it saves time”, but six questions decide whether AI works alone, with a "
        "person or never.",
        "Nie jedno kryterium »AI tam, gdzie oszczędza czas«, lecz sześć pytań decyduje, czy AI "
        "pracuje sama, z człowiekiem, czy wcale.",
    ),
    "v2.map.normative": ("normative criterion", "kryterium normatywne"),
    "v2.zone.ai_samodzielnie": ("AI alone", "AI samodzielnie"),
    "v2.zone.ai_z_czlowiekiem": ("AI with a person", "AI z człowiekiem"),
    "v2.zone.tylko_czlowiek": ("only a person", "tylko człowiek"),
    "v2.perm.may": ("What AI may do", "Co AI może"),
    "v2.perm.may_not": ("What AI may not do", "Czego AI nie może"),
    "v2.perm.now": ("Now", "Teraz"),
    "v2.perm.leaves.local": ("Nothing leaves this server.", "Nic nie wychodzi poza ten serwer."),
    "v2.perm.attack": ("Attack test", "Próba ataku"),
    "v2.perm.attack.run": ("Run", "Uruchom"),
    "v2.perm.attack.live_option": ("Live", "Na żywo"),
    "v2.perm.attack.no_function": (
        "Sentinel has no function through which AI could do this.",
        "Sentinel nie ma funkcji, którą AI mogłoby to zrobić.",
    ),
    "v2.people.absent": ("What is not here, on purpose", "Czego tu celowo nie ma"),
    "v2.people.absent.performance": ("Performance scores", "Ocena wydajności"),
    "v2.people.absent.ranking": (
        "Ranking of people for substitutions",
        "Ranking ludzi do zastępstw",
    ),
    "v2.people.absent.mood": ("Mood and emotion analysis", "Analiza nastroju i emocji"),
    "v2.people.absent.reasons": ("Reasons for absence", "Powody nieobecności"),
    "v2.people.principle": (
        "Sentinel plans by roles and availability; it does not rate people.",
        "Sentinel planuje według ról i dostępności, nie ocenia ludzi.",
    ),
    "v2.own.title": ("What would you do?", "Co byś zrobił?"),
    "v2.own.skip": ("Show it now", "Pokaż od razu"),
    "v2.psettings.assessment": ("My assessment first", "Najpierw moja ocena"),
}


def _fields(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_both_languages_with_the_same_placeholders() -> None:
    for key, (english, polish) in CATALOGUE.items():
        assert key.startswith("v2."), key
        assert english.strip() and polish.strip(), key
        assert _fields(english) == _fields(polish), key
    plural = {k.rsplit(".", 1)[0] for k in CATALOGUE if k.endswith((".one", ".few", ".many"))}
    for base in plural:
        assert all(f"{base}.{form}" in CATALOGUE for form in ("one", "few", "many")), base


def test_every_key_the_v2_pages_use_exists() -> None:
    used: set[str] = set()
    pattern = re.compile(r"""\b(?:t|texts|t\.plural|plural)\(\s*f?["']([a-z_.0-9]+)["']""")
    for path in [*UI.glob("templates/v2/*.html"), *UI.glob("v2/*.py")]:
        used |= set(pattern.findall(path.read_text(encoding="utf-8")))
    for prefix, values in FAMILIES.items():
        used |= {prefix + value for value in values}
    plural = {k.rsplit(".", 1)[0] for k in CATALOGUE if k.endswith(".one")}
    plural |= {k.rsplit(".", 1)[0] for k in V1 if k.endswith(".one")}
    missing = sorted(
        k
        for k in used
        if k not in CATALOGUE and k not in V1 and k not in plural and not k.endswith(".")
    )
    assert missing == []


def test_no_internal_term_in_the_v2_texts() -> None:
    for key, texts in CATALOGUE.items():
        for text in texts:
            assert problems(f"<p>{text}</p>") == [], key


def test_the_glossary_labels_exactly() -> None:
    for key, (english, polish) in GLOSSARY.items():
        assert CATALOGUE[key] == (english, polish), key
    pl = TextsV2("pl")
    assert pl("v2.chance.value", n=39) == "39 na 100"
    assert pl("v2.decision.title") == "Decyzja do podjęcia"
    assert pl("nav.skip") == "Przejdź do treści"  # a key of the first catalogue
    assert pl("v2.nope") == "⟦v2.nope⟧"


def test_verdict_sentences_follow_polish_numbers() -> None:
    pl = TextsV2("pl")
    assert pl.plural("v2.verdict.bad", 2) == "Spóźnimy się o ok. 2 dni robocze."
    assert pl.plural("v2.verdict.bad", 5) == "Spóźnimy się o ok. 5 dni roboczych."
    assert pl.plural("v2.verdict.bad", 1) == "Spóźnimy się o ok. 1 dzień roboczy."
    assert pl.plural("v2.verdict.good", 6) == "Zdążymy z zapasem ok. 6 dni roboczych."
    assert pl.plural("v2.verdict.warn", 2) == (
        "Raczej zdążymy, ale zapas jest mały (ok. 2 dni roboczych)."
    )


# ---- WP21: no dash as a pause; the text budget (docs/design/v3-spec.md, section 10)

ROOT = Path(__file__).parents[1]
OWN_FIELDS = (  # the registry's own texts; a quote, its highlights and a citation are verbatim
    *("title_pl", "title_en", "gloss_pl", "gloss_en", "summary_pl", "summary_en"),
    *("implication_pl", "implication_en", "caveats_pl", "caveats_en"),
)
KEY = r"""{{ *t(?:\.plural)?\(\s*["']([a-z0-9_.]+)["']"""
LEAD_IN = r"(?:<[^>]+>|\s|{{[^}]*icon[^}]*}})*"  # tags, spaces and icons before the text
HEADING = re.compile(r"<h[1-3][^>]*>" + LEAD_IN + KEY)
HELPER = re.compile(
    r"""<(?:p|span|div)[^>]*class="[^"]*\b(?:lead|hint|muted)\b[^"]*"[^>]*>""" + LEAD_IN + KEY
)
SENTENCE_END = re.compile(r"(?<=[.!?…])\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ„“«])")


def _our_texts() -> list[tuple[str, str]]:
    """Every text we wrote that a person reads: the catalogues, the messages, the registry's own
    fields, the decisions, the map and the user guides (a quoted line of a guide skipped)."""
    texts = [(k, v) for c in (CATALOGUE, V1) for k, pair in c.items() for v in pair]
    texts += [(f"{lang}:{k}", v) for lang, m in MESSAGES.items() for k, v in m.items()]
    registry, decisions, boundary = research()
    for item in registry.items:
        texts += [(f"{item.id}.{f}", getattr(item, f) or "") for f in OWN_FIELDS]
        texts += [(f"{item.id}.figure", g.label_pl + " " + g.label_en) for g in item.figures]
    texts += [(d.id, t) for d in decisions for t in (d.text, d.text_pl, d.text_en)]
    for c in boundary.criteria:
        texts += [(f"criterion {c.id}", t) for t in c.model_dump().values() if isinstance(t, str)]
    for process in boundary.processes:
        texts += [(process.id, t) for t in process.model_dump().values() if isinstance(t, str)]
        texts += [(process.id, t) for c in process.cells for t in (c.reason_pl, c.reason_en)]
    for guide in ("docs/user-guide-pl.md", "docs/user-guide-en.md"):
        lines = (ROOT / guide).read_text(encoding="utf-8").splitlines()
        texts += [(guide, line) for line in lines if not line.lstrip().startswith(">")]
    return texts


def test_no_dash_as_a_pause_in_our_texts() -> None:
    """No em dash and no spaced en dash as a pause in our texts; an en dash only in a range
    ("1–5", "{first} – {last}"); quotes and citations are verbatim and not ours to change."""
    found = [(where, p) for where, text in _our_texts() for p in pauses(text)]
    assert found == []


def _words(text: str) -> int:
    return len(re.sub(r"\{[a-z_]+\}", "X", text).split())


def _entries(key: str) -> list[tuple[str, str]]:
    keys = [f"{key}.{form}" for form in ("one", "few", "many")]
    keys = keys if keys[0] in CATALOGUE or keys[0] in V1 else [key]
    return [(k, text) for k in keys for text in (CATALOGUE.get(k) or V1[k])]


def test_the_text_budget_of_headings_and_helpers() -> None:
    """A heading of the interface has at most 6 words; a helper (a lead, a hint, a muted line)
    is one sentence of at most 20 words (a project's, a person's or a source's own name is
    content, not a heading of ours)."""
    headings, helpers = set(), set()
    for path in (ROOT / "src/sentinel/app/ui/templates/v2").glob("*.html"):
        source = path.read_text(encoding="utf-8")
        headings |= {k for k in HEADING.findall(source) if not k.endswith(".")}
        helpers |= {k for k in HELPER.findall(source) if not k.endswith(".")}
    assert len(headings) > 40 and len(helpers) > 60
    long_headings = [(k, text) for key in headings for k, text in _entries(key) if _words(text) > 6]
    long_helpers = [
        (k, text)
        for key in helpers
        for k, text in _entries(key)
        if _words(text) > 20 or len(SENTENCE_END.split(text.strip())) > 1
    ]
    assert long_headings == [] and long_helpers == []
