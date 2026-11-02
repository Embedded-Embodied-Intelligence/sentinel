"""The names of roles in a description (WP11; the live runs: "analityczka" and "backend developer"
for a team's "Analityk" and "Programista", and those people gone from the plan)."""

from datetime import date

import pytest

from sentinel.app.llm import with_team_roles
from sentinel.app.models import Person
from sentinel.app.services import draft_definition, role_counts, roles_outside, team_role
from sentinel.app.ui.forms import Form, read_tasks
from sentinel.wbs.extract import Extraction

ROLES = ("Programista", "Tester", "Analityk")


@pytest.mark.parametrize(
    ("written", "team"),
    [
        ("programista", "Programista"),
        ("Programiści", "Programista"),
        ("programistów", "Programista"),
        ("programistka", "Programista"),
        ("testerk", "Tester"),
        ("testerka", "Tester"),
        ("analityczka", "Analityk"),
        ("Analitycy", "Analityk"),
        ("backend developer", "backend developer"),  # another role: the manager decides
    ],
)
def test_a_role_written_in_a_description_takes_the_teams_name(written: str, team: str) -> None:
    assert team_role(written, ROLES) == team


def test_a_role_that_could_be_two_of_the_team_stays_as_written() -> None:
    roles = ("Programista backend", "Programista frontend")
    assert team_role("programista", roles) == "programista"
    assert team_role("Programista frontend", roles) == "Programista frontend"
    assert team_role("test", ("Tester",)) == "test"  # a short word is no stem


def test_the_draft_uses_the_teams_roles_and_names_those_it_has_not() -> None:
    extraction = Extraction.model_validate(
        {
            "team": [{"role": "analityczka", "count": 1}, {"role": "kierowca", "count": 1}],
            "activities": [
                {
                    "name": "Wywiady",
                    "duration_days": 2,
                    "crew": {"analityczka": 1, "Analityk": 1},
                    "predecessors": [],
                },
                {
                    "name": "Dostawa",
                    "duration_days": 1,
                    "crew": {"kierowca": 1},
                    "predecessors": [],
                },
            ],
        }
    )
    draft = draft_definition(extraction, date(2026, 11, 2), "pl", ROLES)
    assert draft.tasks[0].crew == {"Analityk": 2}  # two names of one role add up
    assert roles_outside(draft, ROLES) == ["kierowca"]
    assert roles_outside(draft, ()) == []  # no team yet: the draft brings its own


def test_the_description_is_sent_with_the_teams_roles_and_never_its_people() -> None:
    team = (
        Person(key="a", name="Ania Nowak", role="Programista"),
        Person(key="b", name="Bartek", role="PROGRAMISTA"),
        Person(key="c", name="Dorota", role="Tester"),
    )
    roles = role_counts(team)
    assert roles == {"Programista": 2, "Tester": 1}
    text = with_team_roles("Opis.", roles)
    assert text.startswith("Opis.\n\n") and '"Programista" (2), "Tester" (1)' in text
    assert "Ania" not in text and "Bartek" not in text
    assert with_team_roles("Opis.", {}) == "Opis."


def test_a_role_outside_the_team_stays_in_the_crew_until_it_is_changed() -> None:
    fields: dict[str, str | list[str]] = {
        "task_key": "T1",
        "task_name": "Wywiady",
        "task_days": "2",
        "crew_T1_0": "",
        "other_role_T1": "analityczka",
        "other_count_T1": "1",
    }
    assert read_tasks(Form(fields), ["Programista"]).tasks[0].crew == {"analityczka": 1}
    cleared = {**fields, "other_count_T1": "0"}
    assert read_tasks(Form(cleared), ["Programista"]).tasks[0].crew == {}
    wrong = {**fields, "other_count_T1": "x"}
    assert read_tasks(Form(wrong), ["Programista"]).errors
