"""The message catalogue of the pages (WP9b; spec section 11.7): both languages for every key
with the same placeholders, every key the templates use, and the formats people read."""

import re
import string
from datetime import date
from pathlib import Path

import pytest
from ui_check import problems

from sentinel.app.messages import MESSAGES, render
from sentinel.app.ui.text import CATALOGUE, Texts, plural_form

UI = Path(__file__).parents[1] / "src/sentinel/app/ui"
# Keys built from a prefix and a value in the templates and the code.
FAMILIES = {
    "setup.step.": ("basics", "team", "tasks"),
    "setup.state.": ("done", "current", "todo"),
    "setup.tab.": ("describe", "import", "manual"),
    "preset.estimation.": ("confident", "typical", "uncertain"),
    "preset.disruptions.": ("calm", "typical", "turbulent"),
    "chance.level.": ("good", "warn", "bad", "neutral"),
    "settings.provider.": ("none", "ollama", "groq", "openrouter"),
    "autonomy.": ("0", "1", "2", "3"),
    "rec.reason.": ("people", "money", "scope", "plan"),
    "rec.badge.": ("faithful", "unfaithful"),
    "history.show.": ("all", "checkins", "recommendations", "changes"),
    "history.kind.": ("checkin", "recommendation", "decision", "change"),
    "history.verdict.": ("approve", "reject", "later"),
    "project.tab.": ("overview", "checkin", "history", "settings"),
    "checkin.status.": ("not_started", "in_progress", "done"),
    "sim.size.": ("j30", "j60"),
    "sim.name.": ("j30", "j60"),
    "sim.example_hint.": ("j30", "j60"),
    "sim.manager.": ("sentinel", "no_reaction"),
    "sim.kind.": ("absence", "grows", "new", "sentinel", "finish"),
    "sim.end_note.": ("j30", "j60"),
    "nav.status.": ("good", "warn", "bad", "decision", "neutral"),
    "sim.days.": ("1", "5", "10", "end"),
}
HINTED = ("preset.estimation.", "preset.disruptions.", "settings.provider.")


def _fields(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_both_languages_have_every_key_with_the_same_placeholders() -> None:
    for key, (english, polish) in CATALOGUE.items():
        assert english.strip() and polish.strip(), key
        assert _fields(english) == _fields(polish), key
    plural = {k.rsplit(".", 1)[0] for k in CATALOGUE if k.endswith((".one", ".few", ".many"))}
    for base in plural:
        assert all(f"{base}.{form}" in CATALOGUE for form in ("one", "few", "many")), base
    assert set(MESSAGES["en"]) == set(MESSAGES["pl"])


def test_every_key_the_pages_use_exists() -> None:
    used: set[str] = set()
    pattern = re.compile(r"""\b(?:t|texts|t\.plural|texts\.plural)\(\s*["']([a-z_.0-9]+)["']""")
    for path in [*UI.glob("templates/*.html"), *UI.glob("*.py")]:
        used |= set(pattern.findall(path.read_text(encoding="utf-8")))
    for prefix, values in FAMILIES.items():
        used |= {prefix + value for value in values}
        if prefix in HINTED:
            used |= {f"{prefix}{value}.hint" for value in values}
    used |= {f"autonomy.{level}.{part}" for level in "0123" for part in ("alone", "asks")}
    used |= {f"setup.tab.{name}.text" for name in FAMILIES["setup.tab."]}
    used |= {f"how.step.{n}.{part}" for n in "123" for part in ("title", "text")}
    plural = {k.rsplit(".", 1)[0] for k in CATALOGUE if k.endswith(".one")}
    missing = sorted(k for k in used if k not in CATALOGUE and k not in plural)
    dynamic = {k for k in missing if k.endswith(".")}
    assert sorted(set(missing) - dynamic) == []


def test_internal_terms_are_not_in_the_catalogue() -> None:
    for key, texts in CATALOGUE.items():
        for text in texts:
            assert problems(f"<p>{text}</p>") == [], key
    shown = ("action_", "status_", "reason_", "progress_", "temporary_person")
    for language in ("en", "pl"):
        for code, text in MESSAGES[language].items():
            if code.startswith(shown):
                assert problems(f"<p>{text}</p>") == [], code


def test_messages_show_dates_in_words() -> None:
    """QA-02: the issues store ISO dates; no page may show one (spec section 11, ui_check)."""
    for language, word in (("pl", "wt. 10\u00a0lis"), ("en", "Tue 10\u00a0Nov")):
        said = render("checkin_out_of_order", language, {"date": "2026-11-10"})  # type: ignore[arg-type]
        assert word in said.replace(" 2026", "") and problems(f"<p>{said}</p>") == []
    assert render("no_tasks", "en", {"date": "not-a-date"}) == render("no_tasks", "en")
    assert "2030" in render("checkin_out_of_order", "en", {"date": "2030-01-07"})
    assert problems(f"<p>{render('checkin_out_of_order', 'en', {'date': '2026-13-45'})}</p>")


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", ["one", "many", "many", "many", "many"]),
        ("pl", ["one", "few", "many", "many", "few"]),
    ],
)
def test_plural_forms(language: str, expected: list[str]) -> None:
    assert [plural_form(language, n) for n in (1, 2, 5, 12, 22)] == expected  # type: ignore[arg-type]


def test_formats_people_read() -> None:
    en, pl = Texts("en"), Texts("pl")
    this_year = date.today().year
    assert en.date(date(this_year, 3, 16)).endswith("16\u00a0Mar")
    assert pl.date(date(this_year, 3, 16)).startswith(
        ("pon.", "wt.", "śr.", "czw.", "pt.", "sob.", "niedz.")
    )
    assert en.date(date(this_year + 1, 1, 4)).endswith(str(this_year + 1))
    assert en.date(None) == "—"
    assert [en.pct(p) for p in (0.0, 0.004, 0.645, 0.996, 1.0)] == [
        "0\u00a0%",
        "<\u00a01\u00a0%",
        "65\u00a0%",
        ">\u00a099\u00a0%",
        "100\u00a0%",
    ]
    assert (en.decimal(1.5), pl.decimal(1.5), en.decimal(2.0)) == ("1.5", "1,5", "2")
    assert (en.money(12345.4), pl.money(12345.4)) == ("12,345", "12\u00a0345")
    # cost units (spec section 11.2; WP9c answer 4)
    assert pl.cost_of(27.4, 84) == "27 z 84 jednostek kosztu"
    assert en.cost_of(27.4, 84) == "27 of 84 cost units"
    assert [pl.cost(v) for v in (1, 3, 5, 22, 1235)] == [
        "1 jednostka kosztu",
        "3 jednostki kosztu",
        "5 jednostek kosztu",
        "22 jednostki kosztu",
        "1\u00a0235 jednostek kosztu",
    ]
    assert (en.cost(1), en.cost(91)) == ("1 cost unit", "91 cost units")
    assert pl.cost_change(1.2, 84) == "+1 jedn., +1\u00a0% budżetu"
    assert en.cost_change(-9.6, 84) == "\u221210 units, \u221211\u00a0% of the budget"
    assert pl.cost_change(1, 500) == "+1 jedn., poniżej 1\u00a0% budżetu"
    assert (en.cost_change(0.2, 84), en.cost_change(3, None)) == ("±0", "+3 units")
    assert [en.tenths(s) for s in (0.04, 0.05, 0.74, 0.95)] == [0, 1, 7, 10]
    assert en("nope") == "⟦nope⟧"
    assert pl.plural("chip.tasks", 3) == "3 zadania" and en.plural("chip.tasks", 1) == "1 task"
