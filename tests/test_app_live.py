"""Live project mode (WP9a; spec section 11): calendar, definition mapping and validation,
check-ins mapped onto the observation, recommendations and decisions, and the event log."""

import re
from datetime import date
from pathlib import Path

import pytest
from app_cases import (
    ABSENCE_CHECKIN,
    DEV,
    MONDAY,
    TESTER,
    absence_recommendation,
    checked_in,
    planned,
    small,
)

from sentinel.agent.params import SentinelParams
from sentinel.app import planning
from sentinel.app.calendar import WorkCalendar
from sentinel.app.events import Created, LiveState, apply, replay
from sentinel.app.live import LiveError, LiveProject, build_model, validate_definition
from sentinel.app.messages import LANGUAGES, MESSAGES, render
from sentinel.app.models import (
    AbsenceReport,
    CheckIn,
    NewTaskReport,
    ProjectDefinition,
    Task,
    TaskReport,
    WorkIncreaseReport,
)
from sentinel.app.store import EventRow, now
from sentinel.model import Activity, ProjectInstance, Role, Worker
from sentinel.policies.sentinel import Sentinel
from sentinel.simulation.events import DisruptionParams
from sentinel.simulation.state import Observation, nominal_world, state_from_observation
from sentinel.simulation.uncertainty import PertParams, derive_budget

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_calendar_counts_working_days_and_shows_dates() -> None:
    calendar = WorkCalendar(date(2026, 11, 4))  # a Wednesday
    assert [calendar.date_of(t).isoformat() for t in range(4)] == [
        "2026-11-04",
        "2026-11-05",
        "2026-11-06",
        "2026-11-09",
    ]
    assert calendar.first(date(2026, 11, 7)) == 3  # Saturday -> the next Monday
    assert calendar.last(date(2026, 11, 7)) == 2  # Saturday -> the Friday before
    assert calendar.last(date(2026, 11, 3)) == -1  # before day 0
    assert calendar.checkin_day(date(2026, 11, 6)) == 3  # the end of Friday: Monday
    assert calendar.checkin_day(date(2026, 10, 1)) == 0
    assert calendar.deadline(date(2026, 11, 9)) == 4  # work done by the end of day 3
    assert calendar.finish_date(4) == date(2026, 11, 9)  # C = 4: last day of work, day 3
    weekend = WorkCalendar(date(2026, 11, 7))  # a Saturday: day 0 is the Monday after
    assert weekend.date_of(0) == date(2026, 11, 9)
    assert weekend.first(date(2026, 11, 7)) == 0


def test_definition_maps_onto_an_instance_and_back() -> None:
    definition = small()
    model = build_model(definition)
    instance = model.instance
    assert [(r.name, r.capacity) for r in instance.roles] == [(DEV, 3), (TESTER, 1)]
    assert [w.role for w in instance.workers] == [0, 0, 0, 1]
    assert [w.name for w in instance.workers] == ["Ada", "Ben", "Cleo", "Tom"]
    assert instance.activities[0].successors == (1, 2)
    assert instance.activities[3].demands == (1, 1)
    assert instance.predecessors(3) == (1, 2)
    assert instance.activities[3].successors == (4,)
    # Round trip: the definition's tasks read back from the instance and its maps.
    names = {j: key for key, j in model.task_ids.items()}
    back = [
        (
            names[a.id],
            a.name,
            a.duration,
            {model.role_names[k]: n for k, n in enumerate(a.demands) if n},
            tuple(names[i] for i in instance.predecessors(a.id) if i in names),
        )
        for a in instance.activities[1:-1]
    ]
    assert back == [(t.key, t.name, t.duration, t.crew, t.predecessors) for t in definition.tasks]
    assert model.deadline == WorkCalendar(MONDAY).deadline(date(2026, 11, 17)) == 12
    pert = PertParams()
    assert model.budget == pytest.approx(derive_budget(instance, 0.1, None, pert))


def _codes(definition: ProjectDefinition) -> list[str]:
    return [i.code for i in validate_definition(definition)]


def test_validation_explains_every_issue_in_english_and_polish() -> None:
    base = small()
    tasks = list(base.tasks)
    tasks[0] = tasks[0].model_copy(update={"predecessors": ("T3",), "crew": {DEV: 4}})
    tasks[1] = tasks[1].model_copy(update={"predecessors": ("T9",), "duration": 0})
    tasks.append(Task(key="T4", name="Docs", duration=2, crew={"Writer": 1}, optional=True))
    tasks.append(Task(key="T5", name="build api", duration=1, predecessors=("T4",)))
    definition = base.model_copy(update={"tasks": tuple(tasks)})
    issues = validate_definition(definition)
    codes = [i.code for i in issues]
    assert "crew_above_team" in codes and "unknown_predecessor" in codes
    assert "duration_too_short" in codes and "unknown_role" in codes
    assert "duplicate_task_name" in codes and "optional_with_successors" in codes
    cycle = next(i for i in issues if i.code == "cycle")
    assert render("cycle", "en", cycle.values) == (
        "These tasks wait for each other in a circle: Build API → Test → Build API."
    )
    above = next(i for i in issues if i.code == "crew_above_team")
    assert render(above.code, "en", above.values) == (
        "“Build API” needs 4 × Developer, but the team has only 3."
    )
    assert render(above.code, "pl", above.values) == (
        "„Build API” potrzebuje 4 × Developer, a zespół ma tylko 3."
    )
    with pytest.raises(LiveError):
        build_model(definition)
    late = small(deadline=date(2026, 11, 5))
    issue = next(i for i in validate_definition(late) if i.code == "deadline_before_critical_path")
    assert issue.values["earliest"] == "2026-11-12"  # 9 working days: LB0 = 9
    assert _codes(small()) == []


def test_every_message_exists_in_both_languages_with_the_same_placeholders() -> None:
    assert set(MESSAGES["en"]) == set(MESSAGES["pl"])
    placeholder = re.compile(r"\{(\w+)\}")
    for code, text in MESSAGES["en"].items():
        assert set(placeholder.findall(text)) == set(placeholder.findall(MESSAGES["pl"][code])), (
            code
        )
    used: set[str] = set()
    pattern = re.compile(
        r"""(?:issue|warning|AppError|render|LiveError\(\[issue)\(\s*f?"([a-z_]+)["{]"""
    )
    for path in (REPO_ROOT / "src" / "sentinel" / "app").glob("*.py"):
        used |= set(pattern.findall(path.read_text(encoding="utf-8")))
    missing = sorted(code for code in used if code not in MESSAGES["en"] and not code.endswith("_"))
    assert missing == []
    assert LANGUAGES == ("en", "pl")


def test_checkin_maps_progress_absences_and_crews_onto_the_observation() -> None:
    project = checked_in(planned(small()), ABSENCE_CHECKIN)
    observation = project.observation()
    assert observation.day == 3
    # T1: 30 % of 6 days with 2 people = 3.6 crew-member days, rounded half up to 4 (e = 2.0).
    assert observation.work_done[1] == 2.0
    assert observation.status[1:4] == ("running", "done", "unstarted")
    assert observation.start[1] == 0 and observation.finish[2] == 3
    assert observation.assigned[1] == (0, 1) and observation.assigned[2] == (2,)
    assert observation.present == (False, True, True, True)
    assert observation.absent_since[0] == 3 and observation.announced[0] == 7
    assert observation.cost == pytest.approx(2.0 * 2 + 3.0)
    project.check()
    # Ben absent too: T1 has no present member, so it is paused (spec section 3.1 a).
    both = checked_in(
        project.copy(),
        CheckIn(
            date=date(2026, 11, 5),
            absences=(AbsenceReport(person="b", first_day=date(2026, 11, 6)),),
        ),
    )
    paused = both.observation()
    assert paused.status[1] == "paused" and paused.announced[1] == 1
    # After the announced return date Ada is present again.
    later = checked_in(
        project.copy(),
        CheckIn(
            date=date(2026, 11, 16),
            tasks=(TaskReport(task="T1", status="in_progress", percent=60),),
        ),
    )
    assert later.observation().present[0] is True


def test_plus_n_days_becomes_the_factor_of_the_remaining_work() -> None:
    project = checked_in(
        planned(small()),
        CheckIn(
            date=date(2026, 11, 4),
            tasks=(TaskReport(task="T1", status="in_progress", percent=50),),
            increases=(WorkIncreaseReport(task="T1", extra_days=2),),
        ),
    )
    observation = project.observation()
    # 3 of 6 full-crew days are done, R = 3, F = (3 + 2) / 3.
    assert observation.work_increases == ((1, 3.0, pytest.approx(5 / 3)),)
    remaining = nominal_world(observation).remaining[1] / 2
    assert remaining == pytest.approx(5.0)
    # The share done now refers to the new total of 10 days: 50 % is 5 days of work.
    again = checked_in(
        project.copy(),
        CheckIn(
            date=date(2026, 11, 5), tasks=(TaskReport(task="T1", status="in_progress", percent=50),)
        ),
    )
    assert again.observation().work_done[1] == 5.0
    with pytest.raises(LiveError) as below:
        project.copy().resolve_checkin(
            CheckIn(
                date=date(2026, 11, 5),
                tasks=(TaskReport(task="T1", status="in_progress", percent=10),),
            )
        )
    assert [i.code for i in below.value.issues] == ["progress_below_change"]


def test_new_task_is_inserted_as_a_d3_activity() -> None:
    project = checked_in(
        planned(small()),
        CheckIn(
            date=date(2026, 11, 4),
            tasks=(TaskReport(task="T1", status="in_progress", percent=10),),
            new_tasks=(
                NewTaskReport(
                    name="Security review", duration=2, crew={TESTER: 1}, after="T1", before="T3"
                ),
            ),
        ),
    )
    observation = project.observation()
    assert len(observation.inserted) == 1
    added = observation.inserted[0]
    assert (added.id, added.predecessor, added.successor, added.day) == (5, 1, 3, 3)
    assert added.demands == (0, 1)
    # Planned start (spec 3.1 e): after T1's planned finish 0 + 6, and not before t + 1 = 4.
    assert observation.plan[5] == 6
    with pytest.raises(LiveError) as invalid:
        project.copy().resolve_checkin(
            CheckIn(
                date=date(2026, 11, 5),
                new_tasks=(
                    NewTaskReport(name="Build API", duration=1, before="T1"),
                    NewTaskReport(name="Loop", duration=1, after="T3", before="T3"),
                ),
            )
        )
    codes = [i.code for i in invalid.value.issues]
    assert codes == ["new_task_name_used", "new_task_before_started", "new_task_after_invalid"]


def test_crews_follow_the_dispatch_rule_unless_named() -> None:
    project = checked_in(
        planned(small()),
        CheckIn(
            date=date(2026, 11, 4),
            tasks=(
                TaskReport(task="T1", status="in_progress", percent=10, crew=("c", "b")),
                TaskReport(task="T2", status="in_progress", percent=10),
            ),
        ),
    )
    observation = project.observation()
    assert observation.assigned[1] == (2, 1)  # as named
    assert observation.assigned[2] == (0,)  # the lowest-id idle developer (3.1 b)
    with pytest.raises(LiveError) as busy:
        planned(small()).resolve_checkin(
            CheckIn(
                date=date(2026, 11, 4),
                tasks=(
                    TaskReport(task="T1", status="in_progress", percent=10),
                    TaskReport(task="T2", status="in_progress", percent=10, crew=("a",)),
                ),
            )
        )
    message = render(busy.value.issues[0].code, "en", busy.value.issues[0].values)
    assert message == "Ada is in the crew of “Build API” on 2026-11-02."


def test_checkin_problems_are_reported_in_plain_language() -> None:
    project = checked_in(planned(small()), ABSENCE_CHECKIN)
    cases = {
        "checkin_out_of_order": CheckIn(date=date(2026, 11, 2)),
        "predecessor_not_done": CheckIn(
            date=date(2026, 11, 5), tasks=(TaskReport(task="T3", status="in_progress", percent=5),)
        ),
        "percent_range": CheckIn(
            date=date(2026, 11, 5),
            tasks=(TaskReport(task="T1", status="in_progress", percent=100),),
        ),
        "already_done": CheckIn(
            date=date(2026, 11, 5), tasks=(TaskReport(task="T2", status="in_progress", percent=5),)
        ),
        "unknown_person": CheckIn(
            date=date(2026, 11, 5), absences=(AbsenceReport(person="zed", first_day=MONDAY),)
        ),
        "increase_not_in_progress": CheckIn(
            date=date(2026, 11, 5), increases=(WorkIncreaseReport(task="T3", factor=1.5),)
        ),
    }
    for code, checkin in cases.items():
        with pytest.raises(LiveError) as error:
            project.copy().resolve_checkin(checkin)
        issue = error.value.issues[0]
        assert issue.code == code
        assert render(issue.code, "en", issue.values) != render(issue.code, "pl", issue.values)
    with pytest.raises(LiveError) as unplanned:
        LiveProject(small()).resolve_checkin(ABSENCE_CHECKIN)
    assert unplanned.value.issues[0].code == "no_baseline"


def _hand_made_observation() -> Observation:
    """The observation of ABSENCE_CHECKIN written out by hand from spec section 11.3."""
    roles = (Role(id=0, name=DEV, capacity=3), Role(id=1, name=TESTER, capacity=1))
    workers = tuple(
        Worker(id=w, role=k, name=n)
        for w, (k, n) in enumerate([(0, "Ada"), (0, "Ben"), (0, "Cleo"), (1, "Tom")])
    )
    activities = (
        Activity(id=0, duration=0, demands=(0, 0), successors=(1, 2)),
        Activity(id=1, duration=6, demands=(2, 0), successors=(3,), name="Build API"),
        Activity(id=2, duration=3, demands=(1, 0), successors=(3,), name="Build UI"),
        Activity(id=3, duration=3, demands=(1, 1), successors=(4,), name="Test"),
        Activity(id=4, duration=0, demands=(0, 0), successors=()),
    )
    instance = ProjectInstance(name="Small", activities=activities, roles=roles, workers=workers)
    return Observation(
        day=3,
        instance=instance,
        inserted=(),
        plan=(0, 0, 0, 6, 9),
        status=("done", "running", "done", "unstarted", "unstarted"),
        work_done=(0.0, 2.0, 3.0, 0.0, 0.0),
        start=(0, 0, 0, None, None),
        finish=(0, None, 3, None, None),
        assigned=((), (0, 1), (2,), (), ()),
        work_increases=(),
        present=(False, True, True, True),
        absent_since=(3, None, None, None),
        announced=(7, None, None, None),
        cost=7.0,
        deadline=12,
        pert=PertParams(),
        disruptions=DisruptionParams(lambda_a=0.01, mean_absence=3.0, lambda_s=0.01, lambda_n=0.02),
        budget=derive_budget(instance, 0.1, None, PertParams()),
        costs=(1.0, 1.0),
        overtime_costs=(1.5, 1.5),
    )


def test_recommendation_is_the_sentinel_decision_on_the_equivalent_observation() -> None:
    project = checked_in(planned(small()), ABSENCE_CHECKIN)
    hand = _hand_made_observation()
    assert project.observation() == hand
    state_from_observation(hand, nominal_world(hand))
    recommendation = absence_recommendation()
    direct = Sentinel(SentinelParams(autonomy=2), seed=2026, keep_records=False).deliberate(hand)
    timing = {"generation_s", "evaluation_s", "wall_time_s"}
    assert recommendation.record.model_dump(exclude=timing) == direct.model_dump(exclude=timing)
    assert recommendation.record.chosen == "SUBST(1)" and recommendation.record.gate == "escalated"
    noop, chosen = recommendation.impact("NOOP"), recommendation.impact("SUBST(1)")
    assert noop is not None and chosen is not None
    assert chosen.p_on_time > noop.p_on_time and chosen.mean_makespan is not None


def _rows(events: list[tuple[str, dict[str, object]]]) -> list[EventRow]:
    return [EventRow("p", i + 1, t, p, now()) for i, (t, p) in enumerate(events)]  # type: ignore[misc]


def test_approve_and_reject_change_the_state_as_specified_and_are_logged() -> None:
    from sentinel.app.events import BaselineSet, CheckinDone, Decided, Recommended

    definition = small()
    project = planned(definition)
    assert project.baseline is not None
    effects = project.resolve_checkin(ABSENCE_CHECKIN)
    project.apply_checkin(effects)
    recommendation = absence_recommendation()
    log: list[tuple[str, dict[str, object]]] = [
        ("created", Created(definition=definition).model_dump(mode="json")),
        ("baseline", BaselineSet(baseline=project.baseline).model_dump(mode="json")),
        ("checkin", CheckinDone(checkin=ABSENCE_CHECKIN, effects=effects).model_dump(mode="json")),
        ("recommendation", Recommended(recommendation=recommendation).model_dump(mode="json")),
    ]
    state = replay(_rows(log))
    assert state.open is not None and state.open.seq == 4
    before = state.project.observation()
    # Reject: recorded, nothing changes.
    rejected = replay(_rows(log))
    apply(rejected, 5, Decided(recommendation=4, verdict="reject"))
    assert rejected.recommendations[0].status == "rejected" and rejected.open is None
    assert rejected.project.observation() == before
    # Approve: Cleo replaces the absent Ada in T1's crew, with the SUBST handover (spec 3, 4).
    approved, rejection = planning.approval(state.project, recommendation)
    assert rejection is None
    action = state.project.resolve_action(approved.decision, approved.label, approved.kind)
    assert not isinstance(action, str)
    apply(state, 5, Decided(recommendation=4, verdict="approve", applied=action))
    after = state.project.observation()
    assert state.recommendations[0].status == "approved"
    assert after.assigned[1] == (2, 1)
    assert after.handovers == ((1, 2.0, 1),)  # o_j = max(1, ceil(0.3 * 2)) = 1 per substitute
    assert after.status[1] == "running" and after.plan == before.plan
    # The log replays to the same state (spec section 11.5).
    log.append(
        (
            "decision",
            Decided(recommendation=4, verdict="approve", applied=action).model_dump(mode="json"),
        )
    )
    rebuilt = replay(_rows(log))
    assert rebuilt.project.observation() == after
    assert [r.status for r in rebuilt.recommendations] == ["approved"]


@pytest.mark.slow  # under 2 s, kept out of the 75 s default run
def test_actions_below_the_autonomy_level_apply_automatically() -> None:
    project = checked_in(planned(small(autonomy=3)), ABSENCE_CHECKIN)
    recommendation = planning.recommend(project)
    assert recommendation.record.gate == "auto"
    chosen = recommendation.chosen
    assert chosen is not None
    action = project.resolve_action(recommendation.record.decision, chosen.label, chosen.kind)
    assert not isinstance(action, str)
    state = LiveState(project, "new", 3)
    from sentinel.app.events import Recommended

    apply(state, 4, Recommended(recommendation=recommendation, applied=action))
    assert state.recommendations[0].status == "auto"
    assert state.project.observation().assigned[1] == (2, 1)
