"""What the application shows (WP9c, spec v2.0.2 sections 11.2, 11.4-11.6): one comparison on
the forecast's simulated futures, the tasks that threaten the deadline, and the names of the
example projects from a vocabulary file per language."""

import re
from datetime import date

import numpy as np
from app_cases import ABSENCE_CHECKIN, absence_recommendation, checked_in, planned, small

from sentinel.app import names, planning, showcase
from sentinel.app.live import LiveProject
from sentinel.app.models import CheckIn, Task
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


def test_threats_decide_half_of_the_late_futures_but_not_nearly_all_futures() -> None:
    durations = dict.fromkeys(range(1, 6), 1)
    late = {1: 50, 2: 49, 3: 90, 4: 90, 5: 60}
    on_time = {3: 99, 4: 100, 5: 100}
    # Exactly half of the late futures counts and 49 % does not; 189 of 200 futures stays, exactly
    # 190 of 200 (95 %) is always critical; the order is the late share alone.
    assert planning.rank_threats(late, 100, on_time, 100, durations) == [3, 5, 1]
    # Equal late shares: the longer task, then the id; and at most three.
    equal = {1: 5, 2: 5, 3: 5, 4: 5}
    assert planning.rank_threats(equal, 10, {}, 10, {1: 2, 2: 7, 3: 2, 4: 2}) == [2, 1, 3]
    # At a chance of 0 % nothing is always critical; nothing late, nothing to name.
    assert planning.rank_threats({1: 50, 2: 100, 3: 49}, 100, {}, 0, durations) == [2, 1]
    assert planning.rank_threats({}, 0, {}, 200, {}) == []


def test_the_last_task_is_no_threat_though_a_side_task_goes_around_it() -> None:
    """QA-23: a required task without a successor made the plan's last task non-structural, and it
    topped the list with nothing for a manager to do. It decides nearly every future."""
    base = small()
    side = Task(key="T4", name="Docs", duration=1, crew={"Tester": 1}, predecessors=("T2",))
    definition = base.model_copy(update={"tasks": (*base.tasks, side)})
    project = planned(definition)
    nodes = project.nodes()
    assert planning.structural(nodes, set()) == set()
    assert "T3" in planning.threat_candidates(project, nodes)
    forecast = planning.forecast(project)
    assert forecast.p_on_time is not None and 0 < forecast.p_on_time < 1
    assert forecast.drivers == ()
    # No future can finish on time, so nothing shows that it decides on-time futures too.
    too_late = checked_in(planned(definition), CheckIn(date=date(2026, 11, 13)))
    zero = planning.forecast(too_late)
    assert zero.p_on_time == 0 and [d.task for d in zero.drivers] == ["T3", "T1"]
    assert zero.drivers[0].share >= 0.95 and zero.drivers[0].on_time_share == 0


def test_threats_leave_out_structural_and_finished_tasks() -> None:
    project = checked_in(planned(small()), ABSENCE_CHECKIN)
    nodes = project.nodes()
    assert planning.structural(nodes, set()) == {"T3"}  # the test task follows both others
    assert planning.threat_candidates(project, nodes) == ["T1"]  # T2 is done
    forecast = planning.forecast(project)
    assert forecast.p_on_time is not None
    assert forecast.late == round((1 - forecast.p_on_time) * 200) - forecast.truncated
    assert [d.task for d in forecast.drivers] == ["T1"]
    assert 0.5 <= forecast.drivers[0].share <= 1
    shown = forecast_view(project, forecast).drivers[0]  # what the API and the pages read
    assert (shown.name, shown.share) == ("Build API", forecast.drivers[0].share)
    assert shown.on_time_share == forecast.drivers[0].on_time_share
    # The showcase: the first task, the performance tests and the launch are on every path of
    # the required tasks; the optional gift cards are left out of the paths.
    nodes = LiveProject(showcase.definition("pl")).nodes()
    optional = {key for key, node in nodes.items() if node.optional}
    assert optional == {"T11"}
    assert planning.structural(nodes, optional) == {"T1", "T10", "T12"}


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
