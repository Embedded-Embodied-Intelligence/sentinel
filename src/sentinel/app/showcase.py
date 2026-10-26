"""The showcase project of the demo (ADR-0024): a seeded live project, an online shop relaunch
with eight people and twelve tasks, its baseline plan and two check-ins with their
recommendations, built once per server and language (deterministic) and copied into every new
sandbox in the visitor's language. Its names come from the vocabulary file of the language
(`sentinel.app.names`, WP9c answer 4); the project is the same in every language."""

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
    Language,
    NewTaskReport,
    Person,
    ProjectDefinition,
    Settings,
    Task,
    TaskReport,
    WorkIncreaseReport,
)
from sentinel.app.names import vocabulary

# (person key, role key) in the order listed; the names come from the vocabulary
TEAM = (
    ("ada", "backend"),
    ("ben", "backend"),
    ("cyrus", "backend"),
    ("chloe", "frontend"),
    ("dmitri", "frontend"),
    ("esra", "tester"),
    ("felix", "devops"),
    ("grace", "designer"),
)


def definition(language: Language = "pl") -> ProjectDefinition:
    """The showcase project as a manager would define it, named in `language`."""
    names = vocabulary(language).showcase
    role = names.roles
    backend, frontend, tester, devops, designer = (
        role["backend"],
        role["frontend"],
        role["tester"],
        role["devops"],
        role["designer"],
    )
    team = tuple(Person(key=key, name=names.people[key], role=role[k]) for key, k in TEAM)

    def task(
        key: str, days: int, crew: dict[str, int], *after: str, optional: bool = False
    ) -> Task:
        return Task(
            key=key,
            name=names.tasks[key],
            duration=days,
            crew=crew,
            predecessors=after,
            optional=optional,
        )

    tasks = (
        task("T1", 2, {backend: 1, frontend: 1, designer: 1}),
        task("T2", 4, {designer: 1}, "T1"),
        task("T3", 6, {backend: 2}, "T1"),
        task("T4", 5, {backend: 1}, "T3"),
        task("T5", 5, {frontend: 2}, "T2"),
        task("T6", 4, {frontend: 1}, "T2", "T3"),
        task("T7", 4, {devops: 1}, "T1"),
        task("T8", 3, {devops: 1}, "T7"),
        task("T9", 4, {tester: 1, backend: 1}, "T4", "T5", "T6"),
        task("T10", 3, {tester: 1, devops: 1}, "T8", "T9"),
        task("T11", 3, {backend: 1, frontend: 1}, "T4", optional=True),
        task("T12", 2, {devops: 1, backend: 1}, "T10"),
    )
    return ProjectDefinition(
        name=names.project,
        start=date(2026, 11, 2),
        deadline=date(2026, 12, 18),
        team=team,
        tasks=tasks,
        settings=Settings(language=language),
    )


def checkins(language: Language = "pl") -> tuple[CheckIn, ...]:
    """Two weeks of the project: progress, an absence, more work and a new task."""
    names = vocabulary(language).showcase
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
                name=names.tasks["N1"],
                duration=2,
                crew={names.roles["tester"]: 1},
                after="T5",
                before="T9",
            ),
        ),
    )
    return first, second


def _event(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")


@cache
def events(language: Language = "pl") -> tuple[tuple[str, dict[str, Any]], ...]:
    """The showcase's event log in `language` (computed once per language: a CP-SAT plan and
    two deliberations)."""
    spec = definition(language)
    project = LiveProject(spec)
    log: list[tuple[str, dict[str, Any]]] = [
        ("created", _event(Created(definition=spec, source="showcase")))
    ]
    baseline = planning.baseline_plan(build_model(spec))
    project.set_baseline(baseline)
    log.append(("baseline", _event(BaselineSet(baseline=baseline))))
    for checkin in checkins(language):
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
    """Seed the showcase project into every new sandbox of `services`, in the language of the
    request that created the sandbox (Polish unless the visitor chose English)."""

    def seed(session: str, language: Language = "pl") -> None:
        log = events(language)
        store = services.store
        name = definition(language).name
        row = store.create_project(session, "live", name, log[0][0], log[0][1])
        for event_type, payload in log[1:]:
            store.append(session, row.id, event_type, payload)

    services.showcase = seed
