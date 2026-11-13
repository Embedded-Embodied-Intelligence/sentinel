"""The word-level diff of tracked changes and the fact guard (v3 spec section 7; spec 11.9)."""

from datetime import date

import pytest

from sentinel.interpret.facts import Names, check, extract, fold, same, to_decimal
from sentinel.interpret.tracked import diff, tokenize

DAY = date(2026, 11, 13)  # a Friday
TEAM = Names(
    people=("Anna Nowak", "Ewa Zielińska", "Bartosz Kowalski", "Dawid Lewandowski"),
    tasks=("Testy integracyjne", "Integracja płatności", "Potok CI/CD", "API katalogu produktów"),
    projects=("Nowa odsłona sklepu internetowego",),
)


def values(text: str, language: str = "pl") -> list[tuple[str, str]]:
    return [(f.kind, f.value) for f in extract(text, language=language, names=TEAM, when=DAY)]  # type: ignore[arg-type]


# ---- the diff


def test_the_diff_finds_word_changes_and_applies_decisions() -> None:
    original = "Projekt kończy się 16 listopada. Budżet wynosi 1,5 mln zł.\n\nAnna prowadzi testy."
    version = "Projekt zakończy się 20 listopada. Budżet to 1,5 mln zł.\n\nAnna prowadzi testy."
    found = diff(original, version)
    assert [(c.deleted, c.inserted) for c in found.changes] == [
        ("kończy", "zakończy"),
        ("16", "20"),
        ("wynosi", "to"),
    ]
    assert found.apply(set()) == original
    assert found.apply({c.id for c in found.changes}) == version
    assert found.apply({1}) == original.replace("16", "20")
    start, end = found.original_span(found.changes[1])
    assert original[start:end] == "16"


def test_the_diff_merges_a_rewritten_phrase_and_keeps_paragraphs() -> None:
    found = diff("Zespół zrobił to i tamto.", "Zespół wykonał wszystko i więcej.")
    assert [(c.deleted, c.inserted) for c in found.changes] == [
        ("zrobił to i tamto", "wykonał wszystko i więcej")
    ]
    split = diff("Pierwszy akapit. Drugi akapit.", "Pierwszy akapit.\n\nDrugi akapit.")
    assert len(split.changes) == 1 and split.changes[0].deleted == ""
    assert split.apply({0}) == "Pierwszy akapit.\n\nDrugi akapit."
    tokens, _ = tokenize("1,5 mln zł, a 3.5% więcej")
    assert [t.text for t in tokens] == ["1,5", "mln", "zł", ",", "a", "3.5", "%", "więcej"]


def test_an_unchanged_text_has_no_changes_and_an_empty_one_is_all_new() -> None:
    assert diff("Bez zmian.", "Bez  zmian.").changes == ()
    found = diff("", "Nowy tekst.")
    assert len(found.changes) == 1 and found.apply({0}) == "Nowy tekst."


# ---- extraction: the tricky Polish forms


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("wzrost o 15 %", [("percent", "15%")]),
        ("wzrost o 15% i 12,5 proc.", [("percent", "15%"), ("percent", "12.5%")]),
        ("budżet 1,5 mln zł", [("amount", "1500000 PLN")]),
        ("rezerwa 3 tys. na licencje", [("number", "3000")]),
        ("rezerwa 3 tys. zł", [("amount", "3000 PLN")]),
        ("koszt 200 000 zł", [("amount", "200000 PLN")]),
        ("koszt 1.200.000 PLN", [("amount", "1200000 PLN")]),
        ("odchylenie 2,5 p.p.", [("percent", "2.5pp")]),
        ("testy do 16 listopada", [("date", "--11-16")]),
        ("start 16 listopada 2026 r.", [("date", "2026-11-16")]),
        ("odbiór 2026-11-30", [("date", "2026-11-30")]),
        ("odbiór 30.11.2026", [("date", "2026-11-30")]),
        ("odbiór 30.11", [("date", "--11-30")]),
        ("szesnastego listopada", [("date", "--11-16")]),
        ("audyt w październiku", [("date", "--10")]),
        ("zostało 12 dni roboczych", [("number", "12")]),
        ("od 3 do 5 dni", [("number", "3"), ("number", "5")]),
        ("w 2027 r. druga faza", [("date", "2027")]),
        ("spotkanie o 10:30", [("date", "time:10:30")]),
        ("wraca jutro", [("date", "day:+1")]),
        ("demo w piątek", [("date", "weekday:4")]),
        ("przegląd za dwa tygodnie", [("date", "in:14d")]),
        ("za 3 dni", [("date", "in:3d")]),
        ("w przyszłym tygodniu", [("date", "week:+1")]),
        ("do końca miesiąca", [("date", "end:2:+0")]),
        ("do końca listopada", [("date", "end:--11")]),
    ],
)
def test_polish_numbers_amounts_and_dates(text: str, expected: list[tuple[str, str]]) -> None:
    assert values(text) == expected


def test_a_year_or_unit_is_part_of_the_fact_and_digits_inside_names_are_not_numbers() -> None:
    facts = extract("Zostało 12 dni, 3 osoby i 4 godz. pracy w T12 i RQ6.", when=DAY)
    assert [(f.value, f.unit, f.text) for f in facts] == [
        ("12", "d", "12 dni"),
        ("3", "people", "3 osoby"),
        ("4", "h", "4 godz."),
    ]


def test_english_numbers_amounts_and_dates() -> None:
    text = "15% done, $1.5 million, 2,500 hours, €3k, due November 16, 2026, on Friday, next week"
    assert values(text, "en") == [
        ("percent", "15%"),
        ("amount", "1500000 USD"),
        ("number", "2500"),
        ("amount", "3000 EUR"),
        ("date", "2026-11-16"),
        ("date", "weekday:4"),
        ("date", "week:+1"),
    ]
    assert to_decimal("1.500", "pl") == 1500 and to_decimal("1.5", "en") == pytest.approx(1.5)


def test_names_are_found_in_their_inflected_forms() -> None:
    text = (
        "Annie zostały Testy integracyjne, Ewie Integracja płatności. Potok CI/CD robi Dawid "
        "Lewandowski; Lewandowskiego wspiera Bartosz. Nowa odsłona sklepu internetowego rusza."
    )
    found = [(f.kind, f.value, f.text) for f in extract(text, names=TEAM)]
    assert found == [
        ("person", "Anna Nowak", "Annie"),
        ("task", "Testy integracyjne", "Testy integracyjne"),
        ("person", "Ewa Zielińska", "Ewie"),
        ("task", "Integracja płatności", "Integracja płatności"),
        ("task", "Potok CI/CD", "Potok CI/CD"),
        ("person", "Dawid Lewandowski", "Dawid Lewandowski"),
        ("person", "Dawid Lewandowski", "Lewandowskiego"),
        ("person", "Bartosz Kowalski", "Bartosz"),
        ("project", "Nowa odsłona sklepu internetowego", "Nowa odsłona sklepu internetowego"),
    ]
    assert extract("ewentualnie adam", names=TEAM) == []
    assert len(fold("Łódź żółć")) == len("Łódź żółć") and fold("Łódź") == "lodz"


def test_facts_compare_by_meaning() -> None:
    def one(text: str) -> object:
        (fact,) = extract(text, names=TEAM, when=DAY)
        return fact

    assert same(one("1,5 mln zł"), one("1 500 000 zł"))  # type: ignore[arg-type]
    assert same(one("15 %"), one("15 procent"))  # type: ignore[arg-type]
    assert same(one("16 listopada"), one("16.11.2026"))  # type: ignore[arg-type]
    assert same(one("jutro"), one("14 listopada"))  # type: ignore[arg-type]
    assert same(one("12 dni"), one("12"))  # type: ignore[arg-type]
    assert not same(one("12 dni"), one("12 osób"))  # type: ignore[arg-type]
    assert not same(one("16.11.2025"), one("16.11.2026"))  # type: ignore[arg-type]
    assert same(one("3 tys. zł"), one("3000"))  # type: ignore[arg-type]


# ---- the check


def test_the_guard_marks_unchanged_changed_omitted_and_new_facts() -> None:
    original = (
        "Projekt Nowa odsłona sklepu internetowego: 15 % zadań gotowe, budżet 1,5 mln zł. "
        "Testy integracyjne skończymy do 16 listopada; Integracją płatności zajmie się Ewa. "
        "Spotkanie o 10:30."
    )
    version = (
        "Projekt Nowa odsłona sklepu internetowego: 20 % zadań gotowe, budżet 1 500 000 zł. "
        "Testy integracyjne skończymy do 18 listopada; Integracją płatności zajmie się Bartosz. "
        "Ryzyko: 3 dni opóźnienia."
    )
    guard = check(original, version, names=TEAM, when=DAY)
    states = {
        c.fact.text: (c.state, c.replaced_by.text if c.replaced_by else None) for c in guard.checks
    }
    assert states == {
        "Nowa odsłona sklepu internetowego": ("unchanged", None),
        "15 %": ("changed", "20 %"),
        "1,5 mln zł": ("unchanged", None),
        "Testy integracyjne": ("unchanged", None),
        "16 listopada": ("changed", "18 listopada"),
        "Integracją płatności": ("unchanged", None),
        "Ewa": ("changed", "Bartosz"),
        "10:30": ("omitted", None),
    }
    assert [f.text for f in guard.new] == ["3 dni"]
    assert guard.warning and guard.count("changed") == 3 and guard.count("omitted") == 1


def test_a_repetition_removed_is_no_omission_and_a_clean_edit_has_no_warning() -> None:
    original = "Budżet to 120 dni. Powtarzam: budżet to 120 dni. Termin 30.11.2026."
    version = "Budżet to 120 dni, termin 30 listopada 2026 r."
    guard = check(original, version, when=DAY)
    assert [c.state for c in guard.checks] == ["unchanged", "unchanged"]
    assert guard.checks[0].count == 2 and not guard.new and not guard.warning
