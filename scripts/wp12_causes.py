"""The decomposition of a move of the chance (spec section 11.4, v2.2.0) on a run like the CEO's run
A of the WP12 test (docs/qa/raport-ceo-chrome-pl.md): a website with twelve tasks, a week of
Tomasz's absence and "Migracja treści" without progress, rebuilt from the report's words.

    uv run python scripts/wp12_causes.py

Prints the chance before and after the second check-in and the causes, in the words of the
overview; nothing is written.
"""

from datetime import date

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
from sentinel.app.ui.text import Texts

BACK, FRONT, TEST, UX = "Programista backend", "Programista frontend", "Tester", "Projektant UX"


def portal() -> ProjectDefinition:
    team = (
        Person(key="P1", name="Tomasz Nowak", role=BACK),
        Person(key="P2", name="Paulina Lis", role=BACK),
        Person(key="P3", name="Filip Wójcik", role=FRONT),
        Person(key="P4", name="Ewa Kowalska", role=TEST),
        Person(key="P5", name="Olga Zając", role=UX),
    )

    def task(
        key: str, name: str, days: int, crew: dict[str, int], after: tuple[str, ...] = ()
    ) -> Task:
        return Task(key=key, name=name, duration=days, crew=crew, predecessors=after)

    tasks = (
        task("T1", "Warsztaty i wymagania", 3, {UX: 1}),
        task("T2", "Projekt graficzny", 4, {UX: 1}, ("T1",)),
        task("T3", "Architektura i środowiska", 3, {BACK: 1}, ("T1",)),
        task("T4", "Logowanie i uprawnienia", 5, {BACK: 1}, ("T3",)),
        task("T5", "Płatności online", 5, {BACK: 1}, ("T3",)),
        task("T6", "Integracja z ERP", 4, {BACK: 1}, ("T4",)),
        task("T7", "Szablony stron", 5, {FRONT: 1}, ("T2",)),
        task("T8", "Migracja treści", 4, {FRONT: 1}, ("T7",)),
        task("T9", "Powiadomienia SMS", 2, {BACK: 1}, ("T5",)),
        task("T10", "Testy integracyjne", 4, {TEST: 1, BACK: 1}, ("T6", "T9")),
        task("T11", "Testy funkcjonalne", 4, {TEST: 1}, ("T8", "T10")),
        task("T12", "Uruchomienie", 1, {BACK: 1, FRONT: 1}, ("T11",)),
    )
    return ProjectDefinition(
        name="Nowa strona",
        start=date(2026, 11, 2),
        deadline=date(2026, 12, 18),
        team=team,
        tasks=tasks,
        settings=Settings(language="pl"),
    )


def main() -> int:
    project = LiveProject(portal())
    project.set_baseline(planning.baseline_plan(build_model(project.definition)))
    texts = Texts("pl")
    on_plan = CheckIn(
        date=date(2026, 11, 13),
        tasks=(
            TaskReport(task="T1", status="done", finish=date(2026, 11, 4)),
            TaskReport(task="T2", status="done", finish=date(2026, 11, 10)),
            TaskReport(task="T3", status="done", finish=date(2026, 11, 9)),
            TaskReport(task="T4", status="in_progress", percent=60),
            TaskReport(task="T5", status="in_progress", percent=60),
            TaskReport(task="T7", status="in_progress", percent=40),
        ),
    )
    project.apply_checkin(project.resolve_checkin(on_plan))
    before = project.copy()
    p_before = planning.forecast(before).p_on_time
    week = CheckIn(
        date=date(2026, 11, 20),
        tasks=(
            TaskReport(task="T5", status="done", finish=date(2026, 11, 18)),
            TaskReport(task="T7", status="done", finish=date(2026, 11, 17)),
            TaskReport(task="T8", status="in_progress", percent=5, start=date(2026, 11, 18)),
        ),
        absences=(
            AbsenceReport(
                person="P1", first_day=date(2026, 11, 23), return_date=date(2026, 11, 30)
            ),
        ),
    )
    project.apply_checkin(project.resolve_checkin(week))
    p_after = planning.forecast(project).p_on_time
    assert p_before is not None and p_after is not None
    causes = planning.causes(before, week, p_before, p_after)
    print(
        texts(
            "causes.title",
            date=texts.date(week.date),
            before=texts.pct(p_before),
            after=texts.pct(p_after),
        )
    )
    for cause in causes.causes:
        print(
            "-",
            texts(
                f"causes.{cause.kind}",
                name=cause.name,
                p=texts.pct(cause.p_without),
                date=texts.date(on_plan.date),
            ),
        )
    print(texts("causes.note"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
