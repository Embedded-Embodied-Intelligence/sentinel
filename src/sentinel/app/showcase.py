"""The showcase project of the demo (ADR-0024): a seeded live project, an online shop relaunch
with eight people and twelve tasks, its baseline plan and two check-ins with their
recommendations, built once per server (deterministic) and copied into every new sandbox."""

from datetime import date
from functools import cache
from typing import Any

from pydantic import BaseModel

from sentinel.app import planning
from sentinel.app.events import BaselineSet, CheckinDone, Created, Recommended
from sentinel.app.live import LiveProject, build_model
from sentinel.app.models import (
    AbsenceReport,
    CheckIn,
    NewTaskReport,
    Person,
    ProjectDefinition,
    Task,
    TaskReport,
    WorkIncreaseReport,
)

BACKEND, FRONTEND, TESTER, DEVOPS, DESIGNER = (
    "Backend developer",
    "Frontend developer",
    "Tester",
    "DevOps engineer",
    "Designer",
)


def definition() -> ProjectDefinition:
    """The showcase project as a manager would define it."""
    team = (
        Person(key="ada", name="Ada Nowak", role=BACKEND),
        Person(key="ben", name="Ben Kowalski", role=BACKEND),
        Person(key="cyrus", name="Cyrus Mazur", role=BACKEND),
        Person(key="chloe", name="Chloe Wiśniewska", role=FRONTEND),
        Person(key="dmitri", name="Dmitri Lewandowski", role=FRONTEND),
        Person(key="esra", name="Esra Zielińska", role=TESTER),
        Person(key="felix", name="Felix Wójcik", role=DEVOPS),
        Person(key="grace", name="Grace Kamińska", role=DESIGNER),
    )

    def task(key: str, name: str, days: int, crew: dict[str, int], *after: str) -> Task:
        return Task(key=key, name=name, duration=days, crew=crew, predecessors=after)

    tasks = (
        task("T1", "Requirements workshop", 2, {BACKEND: 1, FRONTEND: 1, DESIGNER: 1}),
        task("T2", "Checkout UX design", 4, {DESIGNER: 1}, "T1"),
        task("T3", "Product catalogue API", 6, {BACKEND: 2}, "T1"),
        task("T4", "Payment integration", 5, {BACKEND: 1}, "T3"),
        task("T5", "Checkout UI", 5, {FRONTEND: 2}, "T2"),
        task("T6", "Catalogue UI", 4, {FRONTEND: 1}, "T2", "T3"),
        task("T7", "Cloud infrastructure", 4, {DEVOPS: 1}, "T1"),
        task("T8", "CI/CD pipeline", 3, {DEVOPS: 1}, "T7"),
        task("T9", "Integration tests", 4, {TESTER: 1, BACKEND: 1}, "T4", "T5", "T6"),
        task("T10", "Performance tests", 3, {TESTER: 1, DEVOPS: 1}, "T8", "T9"),
        Task(
            key="T11",
            name="Gift cards",
            duration=3,
            crew={BACKEND: 1, FRONTEND: 1},
            predecessors=("T4",),
            optional=True,
        ),
        task("T12", "Launch", 2, {DEVOPS: 1, BACKEND: 1}, "T10"),
    )
    return ProjectDefinition(
        name="Online shop relaunch",
        start=date(2026, 11, 2),
        deadline=date(2026, 12, 18),
        team=team,
        tasks=tasks,
    )


def checkins() -> tuple[CheckIn, ...]:
    """Two weeks of the project: progress, an absence, more work and a new task."""
    first = CheckIn(
        date=date(2026, 11, 6),
        tasks=(
            TaskReport(task="T1", status="done", finish=date(2026, 11, 3)),
            TaskReport(task="T2", status="in_progress", percent=60),
            TaskReport(task="T3", status="in_progress", percent=40),
            TaskReport(task="T7", status="in_progress", percent=70),
        ),
    )
    second = CheckIn(
        date=date(2026, 11, 13),
        tasks=(
            TaskReport(task="T2", status="done", finish=date(2026, 11, 9)),
            TaskReport(task="T3", status="in_progress", percent=70),
            TaskReport(task="T7", status="done", finish=date(2026, 11, 9)),
            TaskReport(task="T5", status="in_progress", percent=40),
            TaskReport(task="T8", status="in_progress", percent=30),
        ),
        absences=(
            AbsenceReport(
                person="ben", first_day=date(2026, 11, 12), return_date=date(2026, 11, 23)
            ),
        ),
        increases=(WorkIncreaseReport(task="T3", extra_days=3),),
        new_tasks=(
            NewTaskReport(
                key="N1",
                name="Accessibility review",
                duration=2,
                crew={TESTER: 1},
                after="T5",
                before="T9",
            ),
        ),
    )
    return first, second


def _event(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")


@cache
def events() -> tuple[tuple[str, dict[str, Any]], ...]:
    """The showcase's event log (computed once: a CP-SAT plan and two deliberations)."""
    spec = definition()
    project = LiveProject(spec)
    log: list[tuple[str, dict[str, Any]]] = [
        ("created", _event(Created(definition=spec, source="showcase")))
    ]
    baseline = planning.baseline_plan(build_model(spec))
    project.set_baseline(baseline)
    log.append(("baseline", _event(BaselineSet(baseline=baseline))))
    for checkin in checkins():
        effects = project.resolve_checkin(checkin)
        project.apply_checkin(effects)
        log.append(("checkin", _event(CheckinDone(checkin=checkin, effects=effects))))
        recommendation = planning.recommend(project)
        applied = None
        chosen = recommendation.chosen
        if recommendation.record.gate == "auto" and chosen is not None:
            outcome = project.resolve_action(
                recommendation.record.decision, chosen.label, chosen.kind
            )
            if not isinstance(outcome, str):
                applied = outcome
                project.apply_action(applied)
        log.append(
            ("recommendation", _event(Recommended(recommendation=recommendation, applied=applied)))
        )
    return tuple(log)


def install(services: Any) -> None:
    """Seed the showcase project into every new sandbox of `services`."""
    log = events()
    name = definition().name

    def seed(session: str) -> None:
        store = services.store
        row = store.create_project(session, "live", name, log[0][0], log[0][1])
        for event_type, payload in log[1:]:
            store.append(session, row.id, event_type, payload)

    services.showcase = seed
