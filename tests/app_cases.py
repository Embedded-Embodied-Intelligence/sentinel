"""Shared live projects of the application tests (WP9a)."""

import json
from datetime import date
from functools import cache
from typing import Any

from sentinel.agent.decide import DecisionRecord
from sentinel.app import planning
from sentinel.app.live import LiveProject, build_model
from sentinel.app.models import (
    AbsenceReport,
    CheckIn,
    Person,
    ProjectDefinition,
    Settings,
    Task,
    TaskReport,
)

DEV, TESTER = "Developer", "Tester"
MONDAY = date(2026, 11, 2)


def small(deadline: date | None = date(2026, 11, 17), autonomy: int = 2) -> ProjectDefinition:
    """Three developers and a tester; a 2-developer task, a 1-developer task, a test task."""
    team = (
        Person(key="a", name="Ada", role=DEV),
        Person(key="b", name="Ben", role="developers"),  # matched as "Developer" (11.2)
        Person(key="c", name="Cleo", role=DEV),
        Person(key="t", name="Tom", role=TESTER),
    )
    tasks = (
        Task(key="T1", name="Build API", duration=6, crew={DEV: 2}),
        Task(key="T2", name="Build UI", duration=3, crew={DEV: 1}),
        Task(
            key="T3", name="Test", duration=3, crew={TESTER: 1, DEV: 1}, predecessors=("T1", "T2")
        ),
    )
    return ProjectDefinition(
        name="Small",
        start=MONDAY,
        deadline=deadline,
        team=team,
        tasks=tasks,
        settings=Settings(autonomy=autonomy),
    )


def planned(definition: ProjectDefinition) -> LiveProject:
    project = LiveProject(definition)
    project.set_baseline(planning.baseline_plan(build_model(definition)))
    return project


def checked_in(project: LiveProject, checkin: CheckIn) -> LiveProject:
    project.apply_checkin(project.resolve_checkin(checkin))
    project.check()
    return project


# Wednesday 2026-11-04 ends day 2, so its observation is of day 3 (Thursday); Ada is absent
# from Thursday and announced back on Monday 2026-11-16 (day 10).
ABSENCE_CHECKIN = CheckIn(
    date=date(2026, 11, 4),
    tasks=(
        TaskReport(task="T1", status="in_progress", percent=30),
        TaskReport(task="T2", status="done", finish=date(2026, 11, 4)),
    ),
    absences=(
        AbsenceReport(person="a", first_day=date(2026, 11, 5), return_date=date(2026, 11, 16)),
    ),
)


@cache
def absence_recommendation() -> planning.Recommendation:
    """The recommendation after ABSENCE_CHECKIN (SUBST(1) escalated), computed once."""
    return planning.recommend(checked_in(planned(small()), ABSENCE_CHECKIN))


def answer_from(record: DecisionRecord, extra: str = "") -> str:
    """A scripted model's answer (spec section 10.4): the choice with the figures of `record`,
    the record as the page shows it, and `extra`."""
    rows = {c.label: c for c in record.candidates}
    assert record.needs is not None
    found = rows.get(record.chosen)
    p = record.needs.p_on_time if found is None else found.p_on_time
    summary = f"{record.chosen} gives a {p * 100:.0f} % chance of meeting the deadline. {extra}"
    facts: list[dict[str, Any]] = [
        {"kind": "chosen_action", "value": record.chosen},
        {"kind": "p_on_time", "value": f"{p:.2f}"},
        {"kind": "deciding_component", "value": record.reason},
    ]
    if found is not None and record.runner_up is not None:
        runner = rows[record.runner_up]
        summary += f" The next option, {runner.label}, reaches {runner.p_on_time * 100:.0f} %."
        facts += [
            {"kind": "alternative", "value": runner.label},
            {"kind": "alternative_p_on_time", "value": f"{runner.p_on_time:.2f}"},
        ]
    return json.dumps({"summary": summary.strip(), "cited_facts": facts})
