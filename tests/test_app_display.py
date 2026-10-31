"""What the application shows (WP9c, spec v2.0.2 sections 11.2, 11.4-11.6): one comparison on
the forecast's simulated futures, the tasks that threaten the deadline, and the names of the
example projects from a vocabulary file per language."""

import math
import re
from datetime import date

import numpy as np
import pytest
from app_cases import ABSENCE_CHECKIN, absence_recommendation, checked_in, planned, small

from sentinel.app import names, planning, showcase
from sentinel.app.live import LiveProject
from sentinel.app.models import CheckIn, TaskReport, WorkIncreaseReport
from sentinel.app.views import forecast_view
from sentinel.interpret.team import FIRST_NAMES, INITIALS, roster
from sentinel.model import ProjectInstance
from sentinel.wbs.narrate import ROLE_NAMES, VOCABULARY, activity_names


def test_no_change_on_a_recommendation_is_the_overview_forecast() -> None:
    project = checked_in(planned(small()), ABSENCE_CHECKIN)
    forecast = planning.forecast(project)
    recommendation = absence_recommendation()
    comparison = recommendation.comparison
    assert comparison is not None
    assert comparison.seed == forecast.seed
    assert comparison.rollouts == forecast.rollouts == 200
    noop = recommendation.impact("NOOP")
    assert noop is not None and noop.p_on_time == forecast.p_on_time
    assert recommendation.record.needs is not None  # the decision reads the same chance (v2.0.3)
    assert recommendation.record.needs.p_on_time == forecast.p_on_time
    assert noop.mean_makespan == forecast.mean
    labels = [impact.label for impact in comparison.impacts]
    assert labels[0] == recommendation.record.chosen == "SUBST(1)"
    assert set(labels) == set(planning.shown_labels(recommendation.record))
    assert all(impact.rollouts == 200 for impact in comparison.impacts)
    assert recommendation.impacts == ()  # the figures of v2.0.1 are not stored any more


def test_threats_are_the_tasks_whose_duration_goes_with_the_finish_day() -> None:
    """Spec section 11.4: duration sensitivity from 0.2, compared exactly, highest first."""
    finishes = [1, 2, 3, 4, 5]
    realised = {
        1: [1, 4, 5, 2, 3],  # exactly 0.2
        2: [3, 2, 5, 1, 4],  # 0.1
        3: [1, 2, 3, 5, 4],  # 0.9
        4: [5, 4, 3, 2, 1],  # -1: shorter goes with later, no threat
        5: [3, 3, 3, 3, 3],  # does not vary, no correlation
    }
    ranked = planning.rank_threats(realised, finishes, dict.fromkeys(range(1, 6), 1))
    assert ranked == [(3, pytest.approx(0.9)), (1, pytest.approx(0.2))]
    # Still exactly on the line over 200 futures, with ties sharing their mean rank.
    line = planning.rank_threats({1: realised[1] * 40}, finishes * 40, {1: 1})
    assert [j for j, _ in line] == [1]
    # Equal correlations: the longer task, then the id; and at most three.
    same = dict.fromkeys(range(1, 5), finishes)
    ties = planning.rank_threats(same, finishes, {1: 2, 2: 7, 3: 2, 4: 2})
    assert [j for j, _ in ties] == [2, 1, 3]
    # A finish day that does not vary correlates with nothing.
    assert planning.rank_threats({1: finishes}, [9] * 5, {1: 1}) == []


def test_spearman_is_pearson_on_mean_ranks() -> None:
    """Spearman 1904; the value is that of scipy.stats.spearmanr, not a dependency here."""
    squared = planning.signed_squared_spearman([1, 2, 2, 3, 5], [2, 1, 3, 3, 9])
    assert math.sqrt(squared) == pytest.approx(0.7631578947368421)
    assert planning.signed_squared_spearman([1, 2, 3], [3, 2, 1]) == -1


def test_a_realised_duration_holds_the_growth_of_its_rollout() -> None:
    """Spec section 11.4: sampled durations are whole, so growth alone (D2) makes a fraction."""
    project = planned(small())
    j = project.activity_ids()["T1"]
    states = list(planning.forecast_rollouts(project.observation(), 200, 7))
    grown = [any(i == j for i, *_ in state.work_increases) for state in states]
    assert any(grown) and not all(grown)
    assert [planning.realised_days(state, j) % 1 != 0 for state in states] == grown


def test_growth_at_a_check_in_raises_the_realised_duration() -> None:
    """Spec section 11.4: the growth already reported counts, not only that of the rollouts."""
    report = TaskReport(task="T1", status="in_progress", percent=30)
    before = checked_in(planned(small()), CheckIn(date=date(2026, 11, 3), tasks=(report,)))
    grown = checked_in(
        planned(small()),
        CheckIn(
            date=date(2026, 11, 3),
            tasks=(report,),
            increases=(WorkIncreaseReport(task="T1", extra_days=4),),
        ),
    )
    j = before.activity_ids()["T1"]

    def mean_days(project: LiveProject) -> float:
        states = planning.forecast_rollouts(project.observation(), 200, 7)
        return float(np.mean([planning.realised_days(state, j) for state in states]))

    assert mean_days(grown) - mean_days(before) > 3


def test_threats_are_the_unfinished_tasks_and_need_a_late_future() -> None:
    project = checked_in(planned(small()), ABSENCE_CHECKIN)
    nodes = project.nodes()
    # T2 is done; T3, which every path passes through, is unfinished like any other.
    assert planning.threat_candidates(project, nodes) == ["T1", "T3"]
    forecast = planning.forecast(project)
    assert forecast.p_on_time is not None
    assert forecast.late == round((1 - forecast.p_on_time) * 200)
    found = planning.threats(project, rollouts=200)
    assert [d.task for d in found.drivers] == ["T1", "T3"]
    assert found.drivers[0].sensitivity > found.drivers[1].sensitivity >= 0.2
    shown = forecast_view(project, forecast, found).drivers  # what the API and the pages read
    assert shown is not None
    assert (shown[0].name, shown[0].sensitivity) == ("Build API", found.drivers[0].sensitivity)
    assert forecast_view(project, forecast).drivers is None  # still being calculated
    project.tasks["T3"].state = "removed"
    assert planning.threat_candidates(project, nodes) == ["T1"]
    # A chance of 0 % follows the same rule; without a late future or a deadline, no list is due.
    too_late = checked_in(planned(small()), CheckIn(date=date(2026, 11, 13)))
    assert planning.forecast(too_late).p_on_time == 0
    assert [d.task for d in planning.threats(too_late, rollouts=200).drivers] == ["T1", "T3"]
    calm_project = planned(small(deadline=date(2026, 12, 18)))
    calm = planning.forecast(calm_project)
    assert calm.p_on_time == 1 and calm.late == 0
    assert forecast_view(calm_project, calm).drivers == []
    undated_project = planned(small(deadline=None))
    undated = planning.forecast(undated_project)
    assert undated.p_on_time is None and undated.late == 0
    assert forecast_view(undated_project, undated).drivers == []


def test_the_threat_list_adds_to_the_forecasts_worlds_and_changes_none() -> None:
    """Spec section 11.4: M = 1000 with the forecast's seed and layout, its N = 200 worlds first."""
    assert (planning.THREAT_ROLLOUTS, planning.FORECAST_ROLLOUTS) == (1000, 200)
    project = checked_in(planned(small()), ABSENCE_CHECKIN)
    forecast = planning.forecast(project)
    found = planning.threats(project, rollouts=210)
    assert (found.day, found.seed, found.rollouts) == (forecast.day, forecast.seed, 210)
    first = list(planning.forecast_rollouts(project.observation(), 210, forecast.seed))
    makespans = [planning.makespan_of(state) for state in first]
    assert float(np.mean(makespans[:200])) == forecast.mean
    deadline = project.observation().deadline
    assert sum(c > deadline for c in makespans[:200]) == forecast.late
    fewer = planning.forecast_rollouts(project.observation(), 200, forecast.seed)
    assert [planning.makespan_of(state) for state in fewer] == makespans[:200]


def test_the_vocabularies_have_one_shape_and_english_is_the_studies() -> None:
    en, pl = names.vocabulary("en"), names.vocabulary("pl")
    for part in ("roles", "people", "tasks"):
        assert getattr(en.showcase, part).keys() == getattr(pl.showcase, part).keys()
    assert en.simulator.roles == ROLE_NAMES
    assert en.simulator.first_names == FIRST_NAMES
    assert en.simulator.vocabulary == VOCABULARY
    assert len(pl.simulator.roles) == len(ROLE_NAMES)
    assert len(set(pl.simulator.first_names)) == len(FIRST_NAMES)
    assert [(len(v), len(o)) for v, o in pl.simulator.vocabulary] == [
        (len(v), len(o)) for v, o in VOCABULARY
    ]
    words = [w for verbs, objects in pl.simulator.vocabulary for w in (*verbs, *objects)]
    assert not [w for w in words if re.search(r"[,.0-9]", w)]
    for verbs, objects in pl.simulator.vocabulary:
        assert len(set(verbs)) == len(verbs) and len(set(objects)) == len(objects)


def test_the_example_projects_are_named_in_the_users_language(tiny: ProjectInstance) -> None:
    definition = {lang: showcase.definition(lang) for lang in ("pl", "en")}
    assert definition["pl"].name == "Nowa odsłona sklepu internetowego"
    assert definition["en"].name == "Online shop relaunch"
    tasks = {lang: {t.key: t.name for t in d.tasks} for lang, d in definition.items()}
    assert (tasks["pl"]["T3"], tasks["en"]["T3"]) == (
        "API katalogu produktów",
        "Product catalogue API",
    )
    assert definition["pl"].team[1].name == "Bartosz Kowalski"
    shape = [
        (t.key, t.duration, sorted(t.crew.values()), t.predecessors) for t in definition["pl"].tasks
    ]
    assert shape == [
        (t.key, t.duration, sorted(t.crew.values()), t.predecessors) for t in definition["en"].tasks
    ]
    assert names.role_names(tiny, "pl") == ("programista backendu",)
    seed = 7
    assert names.people(tiny, seed, "en") == tuple(m.name for m in roster(tiny, seed))
    polish = names.vocabulary("pl").simulator
    for person in names.people(tiny, seed, "pl"):
        first, initial = person.split(" ")
        assert first in polish.first_names and initial[0] in INITIALS
    # The same seed gives the Polish translation of every English task name.
    english = activity_names(tiny, seed)
    translated = activity_names(tiny, seed, polish.vocabulary)
    for j, name in english.items():
        k = next(
            k
            for k, (verbs, objects) in enumerate(VOCABULARY)
            if any(name.endswith(o) for o in objects)
        )
        verbs, objects = VOCABULARY[k]
        v = next(i for i, verb in enumerate(verbs) if name.startswith(f"{verb} "))
        o = objects.index(name[len(verbs[v]) + 1 :])
        pl_verbs, pl_objects = polish.vocabulary[k]
        assert translated[j] == f"{pl_verbs[v]} {pl_objects[o]}"
    assert np.unique(list(translated.values())).size == len(translated)
