"""The calendar of a live project (spec section 11.1, v2.2.0; B5 of the WP12 test): Polish public
holidays and company days off are not working days."""

from datetime import UTC, date, datetime

import pytest
from app_cases import DEV, small

from sentinel.app import planning
from sentinel.app.calendar import WorkCalendar, easter_sunday, polish_holidays
from sentinel.app.events import Created, parse
from sentinel.app.live import LiveError, LiveProject, build_model
from sentinel.app.models import CheckIn, Person, ProjectDefinition, Settings, Task, TaskReport
from sentinel.app.store import EventRow


def test_the_polish_public_holidays_of_2026_and_2027() -> None:
    assert easter_sunday(2026) == date(2026, 4, 5) and easter_sunday(2027) == date(2027, 3, 28)
    fixed = ((1, 1), (1, 6), (5, 1), (5, 3), (8, 15), (11, 1), (11, 11), (12, 24), (12, 25))
    for year, easter_monday, corpus_christi in (
        (2026, date(2026, 4, 6), date(2026, 6, 4)),
        (2027, date(2027, 3, 29), date(2027, 5, 27)),
    ):
        expected = {date(year, m, d) for m, d in fixed} | {date(year, 12, 26)}
        assert polish_holidays(year) == expected | {easter_monday, corpus_christi}
    assert date(2024, 12, 24) not in polish_holidays(2024)  # a holiday from 2025 on


def test_a_project_across_christmas_skips_the_holidays() -> None:
    """Five days from Monday 21 December 2026 end on Tuesday 29 December, not on Friday 25th."""
    calendar = WorkCalendar(date(2026, 12, 21), holidays="pl")
    days = [calendar.date_of(d) for d in range(6)]
    assert days == [
        date(2026, 12, 21),
        date(2026, 12, 22),
        date(2026, 12, 23),
        date(2026, 12, 28),
        date(2026, 12, 29),
        date(2026, 12, 30),
    ]
    assert calendar.date_of(7) == date(2027, 1, 4)  # 1 January is a holiday too
    assert calendar.first(date(2026, 12, 24)) == 3 and calendar.last(date(2026, 12, 26)) == 2
    assert calendar.checkin_day(date(2026, 12, 24)) == 3  # the status at the end of the 23rd
    definition = ProjectDefinition(
        name="Christmas",
        start=date(2026, 12, 21),
        deadline=date(2026, 12, 29),
        team=(Person(key="a", name="Ada", role=DEV),),
        tasks=(Task(key="T1", name="Build", duration=5, crew={DEV: 1}),),
    )
    model = build_model(definition)
    project = LiveProject(definition)
    project.set_baseline(planning.baseline_plan(model))
    assert model.deadline == 5 and project.calendar.finish_date(project.sink_plan) == date(
        2026, 12, 29
    )
    checkin = CheckIn(
        date=date(2026, 12, 24), tasks=(TaskReport(task="T1", status="in_progress", percent=60),)
    )
    project.apply_checkin(project.resolve_checkin(checkin))
    assert project.day == 3


def test_company_days_off_are_skipped_and_the_calendar_is_fixed_once_tracking_starts() -> None:
    definition = small(deadline=date(2026, 11, 20))
    off = definition.settings.model_copy(update={"days_off": (date(2026, 11, 3),)})
    calendar = WorkCalendar(definition.start, days_off=off.days_off)
    assert calendar.date_of(1) == date(2026, 11, 4)
    project = LiveProject(definition)
    project.set_baseline(planning.baseline_plan(build_model(definition)))
    project.apply_checkin(project.resolve_checkin(CheckIn(date=date(2026, 11, 2))))
    with pytest.raises(LiveError) as error:
        project.set_definition(definition.model_copy(update={"settings": off}))
    assert error.value.issues[0].code == "calendar_frozen"
    project.set_definition(definition.model_copy(update={"name": "Renamed"}))  # names still may


def test_a_project_stored_before_the_holidays_keeps_its_days() -> None:
    """A definition without the holidays setting was counted Monday to Friday (11 November
    included), so its stored days keep their dates; a new one has the holidays."""
    stored = small().model_dump(mode="json")
    del stored["settings"]["holidays"]
    payload = {"definition": stored, "source": "new"}
    row = EventRow(project="p", seq=1, type="created", payload=payload, created=datetime.now(UTC))
    event = parse(row)
    assert isinstance(event, Created) and event.definition.settings.holidays == "none"
    assert Settings().holidays == "pl"
