"""The forms of the pages (WP9b): what the manager entered becomes a definition, a check-in or
settings, and every field that cannot be read is named with a plain-language message."""

from datetime import date

from app_cases import small

from sentinel.app.models import Person
from sentinel.app.ui.forms import (
    Form,
    after_keys,
    pasted_people,
    read_basics,
    read_checkin,
    read_settings,
    read_tasks,
    read_team,
    team_roles,
)


def _errors(found: list) -> dict[str, str]:  # type: ignore[type-arg]
    return {e.name: e.key for e in found}


def test_basics_need_a_name_and_a_start_and_a_sensible_deadline_and_budget() -> None:
    empty = read_basics(Form({"name": " ", "start": "", "budget": "x"}))
    assert _errors(empty.errors) == {
        "name": "form.name_required",
        "start": "form.start_required",
        "budget": "form.budget_positive",
    }
    early = read_basics(
        Form({"name": "Shop", "start": "2026-11-02", "deadline": "2026-10-30", "budget": "0"})
    )
    assert _errors(early.errors) == {
        "deadline": "form.deadline_before_start",
        "budget": "form.budget_positive",
    }
    good = read_basics(
        Form(
            {
                "name": "  Shop   relaunch ",
                "start": "2026-11-02",
                "deadline": "2026-12-18",
                "budget": "1 250,5",
                "estimation": "uncertain",
                "disruptions": "nonsense",
            }
        )
    )
    assert good.errors == [] and good.name == "Shop relaunch" and good.budget == 1250.5
    assert (good.estimation, good.disruptions) == ("uncertain", "typical")
    assert read_basics(Form({"name": "A", "start": "2026-11-02", "deadline": "13/12"})).errors[
        0
    ].key == ("form.date_invalid")


def test_team_rows_paste_and_roles() -> None:
    team = read_team(
        Form(
            {
                "person_key": ["P1", "P1", "bad key!", "P4"],
                "person_name": ["Ada", "Ben", "Cleo", ""],
                "person_role": ["Developer", "developers", "Tester", ""],
            }
        )
    )
    assert [(p.key, p.name) for p in team] == [("P1", "Ada"), ("P2", "Ben"), ("P3", "Cleo")]
    pasted = pasted_people("Dana, Designer\n\nEli;tester\nFay", team)
    assert [(p.name, p.role) for p in pasted[3:]] == [
        ("Dana", "Designer"),
        ("Eli", "tester"),
        ("Fay", ""),
    ]
    assert len({p.key for p in pasted}) == len(pasted)
    assert team_roles(pasted) == ["Developer", "Tester", "Designer"]  # "developers" = Developer


def test_task_rows_with_people_per_role_and_predecessors_by_row_number() -> None:
    roles = ["Developer", "Tester"]
    rows = read_tasks(
        Form(
            {
                "task_key": ["T1", "T2", "T3", "T4"],
                "task_name": ["Build", "Test", "", "Docs"],
                "task_days": ["5", "2", "", "two"],
                "crew_T1_0": "2",
                "crew_T2_1": "1",
                "crew_T2_0": "-1",
                "after_T2": "1",
                "after_T4": "1, 9",
                "optional_T4": "on",
            }
        ),
        roles,
    )
    assert [t.key for t in rows.tasks] == ["T1", "T2", "T4"]  # the empty row is dropped
    build, test, docs = rows.tasks
    assert build.crew == {"Developer": 2} and build.duration == 5
    assert test.crew == {"Tester": 1} and test.predecessors == ("T1",)
    assert docs.optional and docs.predecessors == ("T1",)
    assert _errors(rows.errors) == {
        "crew_T2_0": "form.people_number",
        "task_days_T4": "form.days_number",
        "after_T4": "form.after_numbers",
    }
    assert after_keys("2;3 and 1", ["A", "B", "C"], 0) == (("B", "C"), True)
    assert after_keys("", ["A"], 0) == ((), False)


def test_checkin_reports_only_changes_and_names_wrong_fields() -> None:
    current = {
        "T1": ("in_progress", 30.0),
        "T2": ("not_started", None),
        "T3": ("not_started", None),
    }
    form = Form(
        {
            "date": "2026-11-04",
            "shown": ["T1", "T2", "T3"],
            "status_T1": "in_progress",
            "percent_T1": "30",  # unchanged: not reported
            "status_T2": "done",
            "finish_T2": "2026-11-04",
            "status_T3": "in_progress",
            "percent_T3": "45",
            "start_T3": "2026-11-03",
            "crew_T3": ["c", "t"],
            "away_rows": ["1", "2"],
            "away_1_person": "a",
            "away_1_from": "2026-11-05",
            "away_1_back": "2026-11-16",
            "away_2_person": "",
            "grow_rows": ["1"],
            "grow_1_task": "T1",
            "grow_1_days": "2,5",
            "new_rows": ["1"],
            "new_1_name": "Fix login",
            "new_1_days": "2",
            "new_1_crew_0": "1",
            "new_1_role_0": "Developer",
            "new_1_after": "T1",
            "new_1_optional": "on",
            "msg_absence": '{"person": "b", "first_day": "2026-11-04", "return_date": null}',
        }
    )
    read = read_checkin(form, current)
    assert read.errors == [] and read.checkin is not None
    checkin = read.checkin
    assert checkin.date == date(2026, 11, 4)
    assert [(r.task, r.status) for r in checkin.tasks] == [("T2", "done"), ("T3", "in_progress")]
    assert checkin.tasks[1].crew == ("c", "t") and checkin.tasks[1].start == date(2026, 11, 3)
    assert [(a.person, a.return_date) for a in checkin.absences] == [
        ("a", date(2026, 11, 16)),
        ("b", None),
    ]
    assert checkin.increases[0].extra_days == 2.5
    new = checkin.new_tasks[0]
    assert (new.name, new.crew, new.after, new.before, new.optional) == (
        "Fix login",
        {"Developer": 1},
        "T1",
        None,
        True,
    )
    wrong = read_checkin(
        Form(
            {
                "date": "",
                "shown": ["T1", "T2"],
                "status_T1": "in_progress",
                "percent_T1": "100",
                "status_T2": "done",
                "away_rows": ["1"],
                "away_1_person": "a",
                "away_1_from": "",
                "grow_rows": ["1"],
                "grow_1_task": "T1",
                "grow_1_days": "0",
                "new_rows": ["1"],
                "new_1_name": "",
                "new_1_days": "3",
            }
        ),
        current,
    )
    assert wrong.checkin is None
    assert _errors(wrong.errors) == {
        "date": "form.checkin_date",
        "percent_T1": "form.percent_range",
        "finish_T2": "form.finish_required",
        "away_1_from": "form.away_from",
        "grow_1_days": "form.extra_days",
        "new_1_name": "form.task_name",
    }


def test_project_settings() -> None:
    definition = small()
    roles = team_roles(definition.team)
    good = read_settings(
        Form(
            {
                "name": "Small v2",
                "deadline": "2026-11-20",
                "budget": "",
                "autonomy": "0",
                "estimation": "confident",
                "disruptions": "calm",
                "cost_0": "2",
                "cost_1": "1",
                "llm_proposals": "on",
            }
        ),
        definition,
        roles,
    )
    changed = good.definition
    assert changed is not None and good.errors == []
    assert (changed.name, changed.deadline, changed.budget) == (
        "Small v2",
        date(2026, 11, 20),
        None,
    )
    assert changed.settings.autonomy == 0 and changed.settings.llm_proposals
    assert [(c.role, c.daily_cost) for c in changed.roles] == [("Developer", 2.0)]
    assert changed.team == definition.team and changed.tasks == definition.tasks
    bad = read_settings(
        Form(
            {"name": "", "deadline": "2026-10-01", "budget": "-5", "autonomy": "7", "cost_1": "x"}
        ),
        definition,
        roles,
    )
    assert bad.definition is None
    assert _errors(bad.errors) == {
        "name": "form.name_required",
        "deadline": "form.deadline_before_start",
        "budget": "form.budget_positive",
        "autonomy": "form.autonomy",
        "cost_1": "form.cost",
    }
    assert Person(key="x", name="X", role="Developer")  # the model the forms build
