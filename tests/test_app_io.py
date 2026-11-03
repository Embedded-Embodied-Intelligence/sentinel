"""CSV templates and imports with per-row messages in Polish and English, the JSON export and
import of a whole project, and the plan CSV (WP9a)."""

from datetime import date

import pytest

from sentinel.app import io, planning
from sentinel.app.errors import AppError
from sentinel.app.live import LiveProject, build_model
from sentinel.app.messages import render


def _messages(error: AppError, language: str) -> list[str]:
    return [render(i.code, language, i.values) for i in error.issues]  # type: ignore[arg-type]


def test_the_templates_import_into_a_valid_project() -> None:
    definition = io.definition_from_csv(
        io.TASKS_TEMPLATE.encode(), io.TEAM_TEMPLATE.encode(), name="Shop", start=date(2026, 11, 2)
    )
    assert [t.key for t in definition.tasks] == ["T1", "T2", "T3"]
    assert definition.tasks[1].crew == {"Backend developer": 2}
    assert definition.tasks[2].predecessors == ("T2",)
    assert [p.name for p in definition.team] == ["Ada", "Ben", "Cleo"]
    project = LiveProject(definition)
    project.set_baseline(planning.baseline_plan(build_model(definition)))
    assert project.baseline is not None and project.baseline.makespan == 10


def test_semicolons_crew_column_and_flags_are_read() -> None:
    tasks = (
        "﻿id;name;duration_days;predecessors;optional;crew\n"
        "A;Design;2;;nie;Designer=1\n"
        "B;Build;3;A;no;Developer=2, Designer=1\n"
        "C;Extras;1;B;tak;\n"
    ).encode()
    found, issues = io.parse_tasks(tasks)
    assert issues == []
    assert [(t.key, t.crew, t.predecessors, t.optional) for t in found] == [
        ("A", {"Designer": 1}, (), False),
        ("B", {"Developer": 2, "Designer": 1}, ("A",), False),
        ("C", {}, ("B",), True),
    ]


def test_csv_errors_are_reported_per_row_in_both_languages() -> None:
    tasks = (
        b"id,name,duration_days,predecessors,optional,crew:Developer\n"
        b"T1,Design,two,,no,1\n"
        b"T 2,,3,T1,maybe,x\n"
        b"T3,Test,1,T1,no,1\n"
    )
    team = b"name,role\nAda,Developer\n,Tester\n"
    with pytest.raises(AppError) as error:
        io.definition_from_csv(tasks, team, name="P", start=date(2026, 11, 2))
    english = _messages(error.value, "en")
    polish = _messages(error.value, "pl")
    assert english == [
        "Row 2: duration in days (duration_days) must be a whole number (it is “two”).",
        "Row 3: name is required.",
        "Row 3: the id “T 2” may hold only letters, digits, “_”, “-” and “.”.",
        "Row 3: people as Developer (crew:Developer) must be a whole number (it is “x”).",
        "Row 3: optional must be yes or no (it is “maybe”).",
        "Row 3: name is required.",
    ]
    assert polish[0] == (
        "Wiersz 2: czas trwania w dniach (duration_days) musi być liczbą całkowitą (jest „two”)."
    )
    assert polish[-1] == "Wiersz 3: pole nazwa (name) jest wymagane."
    with pytest.raises(AppError) as missing:
        io.definition_from_csv(b"id,title\n", None, name="P", start=date(2026, 11, 2))
    assert _messages(missing.value, "en") == [
        "The file has no column: name.",
        "The file has no column: duration in days (duration_days).",
    ]
    with pytest.raises(AppError) as empty:
        io.definition_from_csv(b"  \n", None, name="P", start=date(2026, 11, 2))
    assert empty.value.code == "csv_empty"
    with pytest.raises(AppError) as binary:
        io.definition_from_csv(b"\xff\xfe\x00", None, name="P", start=date(2026, 11, 2))
    assert binary.value.code == "csv_encoding"


def test_json_exports_are_checked_on_import() -> None:
    for data, detail in (
        ({"format": "other"}, "not a Sentinel project export"),
        ({"format": "sentinel-project", "version": 9}, "unknown version 9"),
        ({"format": "sentinel-project", "version": 1, "kind": "live", "events": []}, "no events"),
    ):
        with pytest.raises(AppError) as error:
            io.read_export(data)
        assert error.value.params["detail"] == detail
        assert "Sentinel" in render(error.value.code, "en", error.value.params)


def test_the_plan_shown_is_the_current_plan() -> None:
    """B2 of the WP12 test: after a check-in without progress that adds a task before "Test",
    the CSV and the chart show the current plan: no unfinished task in the past, the new task
    finished before "Test" starts (checked by `validate_residual` in `residual_plan`), the
    original plan in its own columns."""
    from app_cases import DEV, checked_in, planned, small

    from sentinel.app.models import CheckIn, NewTaskReport
    from sentinel.app.ui.charts import rows_of
    from sentinel.app.ui.text import Texts

    added = NewTaskReport(key="N1", name="Privacy banner", duration=2, crew={DEV: 1}, after="T2")
    project = checked_in(
        planned(small()),
        CheckIn(date=date(2026, 11, 6), new_tasks=(added.model_copy(update={"before": "T3"}),)),
    )
    t = project.day
    lines = io.plan_csv(project, {}, "pl").splitlines()
    assert lines[0].startswith("id,nazwa,stan,plan_start,plan_koniec,plan_poczatkowy_start")
    rows = {row.split(",")[0]: row.split(",") for row in lines[1:]}
    status = project.checkins[-1][0].isoformat()
    for key, row in rows.items():
        if project.tasks[key].state != "done":
            assert row[4] > status, key  # finishes after the status date
    assert rows["N1"][4] < rows["T3"][3]  # the new task ends before "Test" starts
    assert rows["T3"][5] != "" and rows["N1"][5] == ""  # original plan: not for new tasks
    chart = {row.key: row for row in rows_of(project, Texts("pl")) if row.key in project.tasks}
    assert all(row.planned is None or row.planned[0] >= t for row in chart.values())
    assert chart["N1"].planned is not None and chart["T3"].planned is not None
    assert chart["N1"].planned[1] <= chart["T3"].planned[0]
