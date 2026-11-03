"""One comparison in the application (WP9d, spec v2.0.4 sections 11.5-11.7): the decision, the
display and both explanations come from one record on the forecast's 200 sampled worlds, racing
stage 1 stays that of spec section 6, and the page says why when an alternative shown has a higher
rounded chance than the recommended action."""

import re
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from app_cases import (
    ABSENCE_CHECKIN,
    absence_recommendation,
    answer_from,
    checked_in,
    planned,
    small,
)
from fastapi.testclient import TestClient
from test_app_simulator import tiny_world
from ui_check import problems, visible_text

from sentinel.agent.candidates import generate, noop
from sentinel.agent.decide import CandidateRecord, DecisionRecord, Needs, choose
from sentinel.agent.evaluate import Evaluator, PairedErrors, instability, race
from sentinel.agent.params import SentinelParams
from sentinel.app import planning, showcase
from sentinel.app.api import create_app
from sentinel.app.config import AppConfig
from sentinel.app.events import RecommendationEntry, Recommended, replay
from sentinel.app.live import LiveProject
from sentinel.app.llm import EXPLANATION
from sentinel.app.messages import render
from sentinel.app.models import Language
from sentinel.app.planning import (
    LATER_COMPONENTS,
    Comparison,
    Impact,
    Recommendation,
    half_up,
    shown_chance,
    tie_kind,
)
from sentinel.app.services import Services
from sentinel.app.simulator import PolicyRun, Simulation, SimulatorSpec, build_world
from sentinel.app.store import LOCAL_SESSION
from sentinel.app.ui.project import why_text
from sentinel.app.ui.sim import timeline
from sentinel.app.ui.text import NBSP, Texts
from sentinel.app.views import forecast_view, recommendation_view
from sentinel.dashboard.explain import _percent, checkable, template_explanation
from sentinel.experiments.runs import derive_seed
from sentinel.forecasting.beliefs import Belief
from sentinel.interpret.explain import check, explain, render_record
from sentinel.llm import FakeLlmClient
from sentinel.model import ProjectInstance
from sentinel.policies.base import Decision
from sentinel.policies.no_reaction import NoReaction
from sentinel.simulation.engine import Run
from sentinel.simulation.state import Observation, state_from_observation, work_history

LANGUAGES: tuple[Language, ...] = ("pl", "en")
START = date(2026, 11, 2)
# Instance, scenario: the small example of the simulator and four others of the J30 set.
PROJECTS = (("j3026_7", 1), ("j301_1", 1), ("j3010_3", 2), ("j3019_5", 3), ("j3037_9", 4))
DAYS = 20  # working days of each project: about a quarter of a run
THE_SENTENCE = "Podobna szansa (różnica w granicach niepewności); wybrano wariant, który zmienia "


@cache
def absence_project() -> LiveProject:
    """The project of `absence_recommendation`; only read here."""
    return checked_in(planned(small()), ABSENCE_CHECKIN)


@pytest.fixture
def evaluators(monkeypatch: pytest.MonkeyPatch) -> dict[int, Evaluator]:
    """The evaluator of every deliberation run in a test, by day: what its rule read."""
    kept: dict[int, Evaluator] = {}
    real = planning.compare

    def keeping(record: DecisionRecord, evaluator: Evaluator) -> Comparison:
        kept[record.day] = evaluator
        return real(record, evaluator)

    monkeypatch.setattr(planning, "compare", keeping)
    return kept


def row(label: str, p: float, tardiness: float = 1.0, **extra: object) -> CandidateRecord:
    values: dict[str, object] = {
        "label": label,
        "kind": "noop" if label == "NOOP" else "shift",
        "level": 0,
        "delay": 0,
        "deviation": 0.0,
        "substituted": 0,
        "scope_loss": 0.0,
        "rollouts": 200,
        "p_on_time": p,
        "capped": min(p, 0.8),
        "tardiness": tardiness,
        "mean_cost": 100.0,
        "overrun": 0.0,
        "utility": p,
        "dropped": False,
        "decision": Decision(),
        "eliminated": None,
    }
    return CandidateRecord.model_validate(values | extra)


def decided(reason: str, *rows: CandidateRecord) -> DecisionRecord:
    """A record choosing the first row, the second being the runner-up."""
    return DecisionRecord(
        day=3,
        deliberated=True,
        rule="lexicographic",
        reason=reason,  # type: ignore[arg-type]
        chosen=rows[0].label,
        decision=Decision(),
        runner_up=rows[1].label if len(rows) > 1 else None,
        needs=Needs(deadline=0.2, budget=0.0, p_on_time=0.6, rollouts=200, met=False),
        candidates=rows,
    )


def check_rows(record: DecisionRecord, comparison: Comparison, project_seed: int) -> None:
    """The recommended action's chance equals its row and every row equals the record's, on the
    worlds of the forecast's seed."""
    assert comparison.decides and comparison.rollouts == 200
    assert comparison.seed == derive_seed(project_seed, "forecast", str(record.day))
    rows = {c.label: c for c in record.candidates}
    first = comparison.impacts[0]
    assert first.label == record.chosen
    assert record.needs is not None and record.needs.rollouts == 200
    noop_row = next(i for i in comparison.impacts if i.label == "NOOP")
    assert noop_row.p_on_time == record.needs.p_on_time
    for impact in comparison.impacts:
        assert impact.rollouts == 200
        found = rows.get(impact.label)
        if found is not None:
            assert not found.dropped and found.rollouts == 200
            figures = (found.p_on_time, found.tardiness, found.mean_cost, found.overrun)
            assert (impact.p_on_time, impact.tardiness, impact.mean_cost, impact.overrun) == figures
    assert len(comparison.impacts) <= 6
    if not record.candidates:
        assert [i.label for i in comparison.impacts] == ["NOOP"]
    assert all(c.rollouts == (25 if c.dropped else 200) for c in record.candidates)


def check_one_comparison(
    record: DecisionRecord,
    comparison: Comparison,
    evaluator: Evaluator,
    params: SentinelParams,
    project_seed: int,
) -> None:
    """`check_rows`, and rule (spec section 6) on the comparison, recomputed from the rollouts,
    gives the record's choice, so no alternative shown is ranked above it."""
    check_rows(record, comparison, project_seed)
    assert comparison.seed == evaluator.seed
    if not record.candidates:
        return
    first = comparison.impacts[0]
    compared = [c for c in record.candidates if not c.dropped]
    paired = PairedErrors([evaluator.outcomes[c.label] for c in compared], 200, evaluator.budget)
    choice = choose(compared, params, paired)
    labels = [c.label for c in compared]
    assert labels[choice.index] == record.chosen and choice.reason == record.reason
    assert (labels[choice.runner_up] if choice.runner_up is not None else None) == record.runner_up
    for impact in comparison.impacts[1:]:
        at = labels.index(impact.label)
        assert choice.eliminated[at] is not None or at > choice.index
        # A higher chance than the choice's can only have left the best set after the chance.
        if impact.p_on_time > first.p_on_time:
            assert record.reason in LATER_COMPONENTS


def check_explanations(
    recommendation: Recommendation,
    observation: Observation,
    params: SentinelParams,
    roles: tuple[str, ...] | None = None,
) -> None:
    """The template and a scripted model cite only numbers of the record the page shows; a figure
    from anywhere else counts as made up."""
    record = recommendation.as_shown
    rendered = render_record(record, observation, params, roles)
    for language in LANGUAGES:
        template = template_explanation(record, language)
        cited = [fact.model_dump() for fact in template.cited_facts]
        written = {"summary": checkable(template.summary, language), "cited_facts": cited}
        assert check(written, record, rendered).fully_faithful
    client = FakeLlmClient([answer_from(record)])
    response = explain(client, rendered, seed=1, settings=EXPLANATION)
    assert response.value is not None
    assert check(response.parsed, record, rendered).fully_faithful
    # A chance the record does not show: the first whole per cent far from all of its values.
    absent = next(n for n in range(101, 999) if all(abs(n - 100 * v) > 1 for v in rendered.values))
    wrong = FakeLlmClient([answer_from(record, f"Another option reaches {absent} %.")])
    response = explain(wrong, rendered, seed=1, settings=EXPLANATION)
    faith = check(response.parsed, record, rendered)
    assert faith.hallucinated == 1 and not faith.fully_faithful


def said_tie(text: str) -> bool:
    """Whether a text holds the sentence, in either opening and either language."""
    return any(
        opening in text
        for language in LANGUAGES
        for kind in ("similar", "target")
        for opening in [Texts(language).tie(kind, "stability").split(";")[0]]
    )


def check_run(run: PolicyRun, evaluators: dict[int, Evaluator], seed: int) -> dict[str, int]:
    """Every deliberation of a simulator run: one comparison, explanations citing the record, NOOP
    on the forecaster's rollouts, the sentence's condition on the rows of the comparison, and no
    sentence on the timeline, which shows no alternatives; the deliberations by their deciding
    component, and under "sentence" those whose rows would get it."""
    sentinel = run.sentinel
    assert sentinel is not None
    params = sentinel.params
    records = [r for r in sentinel.records if r.deliberated]
    reasons: dict[str, int] = {}
    for language in LANGUAGES:
        texts = Texts(language)
        entries = {e.day: e for e in timeline(run, texts) if e.kind == "sentinel"}
        for record in records:
            entry = entries.get(record.day)
            assert (entry is not None) == (record.chosen != "NOOP")
            if entry is not None:
                assert not said_tie(entry.text)
    reasons["sentence"] = 0
    for record in records:
        reasons[record.reason] = reasons.get(record.reason, 0) + 1
        comparison = sentinel.comparisons[record.day]
        check_one_comparison(record, comparison, evaluators[record.day], params, seed)
        first, *others = comparison.impacts
        due = any(shown_chance(i.p_on_time) > shown_chance(first.p_on_time) for i in others)
        assert (tie_kind(record, comparison, params) is not None) == due
        assert record.reason in LATER_COMPONENTS or not due
        reasons["sentence"] += due
        observation = run.observations[record.day]
        recommendation = Recommendation(
            day=record.day,
            seed=derive_seed(seed, "sentinel", str(record.day)),
            record=record,
            urgency=None,
            comparison=comparison,
        )
        check_explanations(recommendation, observation, params)
        assert observation.deadline is not None
        rollouts = planning.forecast_rollouts(observation, 200, comparison.seed)
        makespans = [planning.makespan_of(state) for state in rollouts]
        first = next(i for i in comparison.impacts if i.label == "NOOP")
        assert first.p_on_time == sum(c <= observation.deadline for c in makespans) / 200
    return reasons


# --------------------------------------------------------------------------- the decision


def test_the_decision_and_every_figure_are_those_of_one_comparison() -> None:
    project = absence_project()
    recommendation = absence_recommendation()
    record, comparison = recommendation.record, recommendation.comparison
    assert comparison is not None
    check_rows(record, comparison, project.definition.settings.seed)
    day = project.observation().day
    assert recommendation.seed == derive_seed(2026, "sentinel", str(day))  # stage 1 (spec 11.5)
    assert record.chosen == "SUBST(1)" and record.reason == "on_time"


def test_stage_one_is_that_of_racing_on_the_deliberations_worlds() -> None:
    project = absence_project()
    observation = project.observation()
    params = planning.sentinel_params(project)
    candidates = list(generate(observation, params=params).candidates)
    assert len(candidates) > 3
    seed = derive_seed(2026, "sentinel", str(observation.day))
    deviations = [instability(observation, c, params.kappa_h) for c in candidates]
    stage = planning.stage_one(Evaluator(observation, seed, params), candidates, deviations)
    # `race` of spec section 6, its stage 2 cut to one more rollout.
    raced = race(Evaluator(observation, seed, params), candidates, rollouts=params.n_stage1 + 1)
    assert [s.dropped for s in stage] == [s.dropped for s in raced.stats]
    for ours, theirs in zip(stage, raced.stats, strict=True):
        if theirs.dropped:
            assert ours == theirs


def test_the_comparison_holds_the_survivors_noop_and_what_a_page_can_show() -> None:
    def stage(*dropped: bool) -> list[CandidateRecord]:
        rows = [row("NOOP", 0.1, dropped=dropped[0])]
        rows += [row(f"A{a}", 0.5 - a / 100, dropped=d) for a, d in enumerate(dropped[1:], start=1)]
        return rows

    compared = planning.comparison_set
    # NOOP dropped stays; the best of the dropped fill the six rows of a page, no more.
    assert compared(stage(True, False, *[True] * 7)) == {0, 1, 2, 3, 4, 5}
    assert compared(stage(False, *[False] * 8)) == set(range(9))  # every survivor stays
    assert compared(stage(True, True)) == {0, 1}
    # What is shown: the runner-up first, at most five alternatives, NOOP always among them.
    rows = [row(f"A{a}", 0.5 - a / 100) for a in range(8)] + [row("NOOP", 0.1)]
    record = decided("on_time", rows[0], rows[7], *rows[1:7], rows[8])
    assert planning.shown_labels(record) == ["A0", "A7", "A1", "A2", "A3", "NOOP"]
    assert planning.shown_labels(decided("needs_met", row("NOOP", 0.9))) == ["NOOP"]
    outside = decided("on_time", rows[0], rows[1], row("A9", 0.9, dropped=True), rows[8])
    assert planning.shown_labels(outside) == ["A0", "A1", "NOOP"]  # dropped: not in the comparison


# --------------------------------------------------------------------------- what is shown


def test_every_figure_is_rounded_one_way() -> None:
    texts = {language: Texts(language) for language in LANGUAGES}
    for n in (25, 100, 200):
        for k in range(n + 1):
            p = k / n
            shown = shown_chance(p)
            whole = _percent(shown)
            assert f"{shown:.2f}" == f"{int(whole) / 100:.2f}"
            assert re.sub(r"\D", "", texts["en"].pct(p)) == whole, (k, n)
    assert texts["pl"].pct(0.575) == f"58{NBSP}%" and texts["pl"].pct(0.585) == f"59{NBSP}%"
    assert shown_chance(0.998) == 0.99 and shown_chance(0.002) == 0.01  # as ">99 %", "<1 %"
    assert shown_chance(1.0) == 1.0 and shown_chance(0.0) == 0.0
    assert half_up(1.25, 1) == 1.3 and half_up(1.35, 1) == 1.4 and half_up(0.04, 1) == 0.0
    assert texts["pl"].decimal(1.25) == "1,3" and texts["en"].decimal(1.45) == "1.5"


def _view(recommendation: Recommendation, language: Language) -> Any:
    entry = RecommendationEntry(4, recommendation, "open", None)
    return recommendation_view(absence_project(), entry, language)


def shown_as(reason: str, *chances: float) -> Recommendation:
    """The absence recommendation decided by `reason`, its first rows shown with `chances` (the
    choice first) and the rest far below them."""
    base = absence_recommendation()
    comparison = base.comparison
    assert comparison is not None and len(comparison.impacts) >= len(chances)
    rows = tuple(
        impact.model_copy(update={"p_on_time": chances[a] if a < len(chances) else 0.01})
        for a, impact in enumerate(comparison.impacts)
    )
    return base.model_copy(
        update={
            "record": base.record.model_copy(update={"reason": reason}),
            "comparison": comparison.model_copy(update={"impacts": rows}),
        }
    )


def kept_plan(chance: float, alternative: float) -> Recommendation:
    """The plan kept on plan stability, with the absence recommendation's action as the only
    alternative shown."""
    base = absence_recommendation()
    comparison = base.comparison
    assert comparison is not None
    rows = {c.label: c for c in base.record.candidates}
    keep, other = base.impact("NOOP"), base.impact(base.record.chosen)
    assert keep is not None and other is not None
    impacts = (
        keep.model_copy(update={"p_on_time": chance}),
        other.model_copy(update={"p_on_time": alternative}),
    )
    return base.model_copy(
        update={
            "record": decided("stability", rows["NOOP"], rows[base.record.chosen]),
            "comparison": comparison.model_copy(update={"impacts": impacts}),
        }
    )


@pytest.mark.parametrize(
    ("chances", "due"),
    [
        ((0.545, 0.555), True),  # 55 % and 56 %
        ((0.544, 0.545), True),  # 54 % and 55 %, half up
        ((0.575, 0.585), True),  # 58 % and 59 %, whatever their binary fractions round to
        ((0.545, 0.549), False),  # a higher chance, but both are shown as 55 %
        ((0.55, 0.55), False),
        ((0.55, 0.53), False),  # the showcase's case: the choice is shown higher
        ((0.55, 0.53, 0.60), True),  # not only the runner-up counts
    ],
)
def test_the_sentence_needs_an_alternative_shown_with_a_higher_rounded_chance(
    chances: tuple[float, ...], due: bool
) -> None:
    for language in LANGUAGES:
        texts = Texts(language)
        view = _view(shown_as("stability", *chances), language)
        said = why_text(view, texts)
        assert (view.tie is not None) == due
        assert (texts.tie("similar", "stability") in said) == due
        assert said_tie(said) == due
        # Without the sentence the page names the deciding component, as for any decision.
        assert (texts("why.reason", reason=view.reason_text) in said) == (not due)
        assert problems(said) == []


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_sentence_names_the_component_that_decided(language: Language) -> None:
    texts = Texts(language)
    sentences = {}
    for reason in sorted(LATER_COMPONENTS):
        view = _view(shown_as(reason, 0.5, 0.6), language)
        sentences[reason] = texts.tie("similar", reason)
        assert view.tie == "similar" and sentences[reason] in why_text(view, texts)
    assert len(set(sentences.values())) == len(LATER_COMPONENTS)
    if language == "pl":
        assert sentences["stability"] == f"{THE_SENTENCE}mniej terminów."
    # A later component is needed; these leave no room for a higher chance in real records.
    for reason in ("on_time", "only_candidate", "needs_met"):
        view = _view(shown_as(reason, 0.5, 0.6), language)
        assert view.tie is None and not said_tie(why_text(view, texts))
    # A kept plan follows the same condition, with its own text.
    view = _view(kept_plan(0.5, 0.6), language)
    assert not view.acts and view.tie == "similar"
    assert texts.tie("similar", "stability") in why_text(view, texts)
    view = _view(kept_plan(0.5, 0.5), language)
    assert not view.acts and view.tie is None and not said_tie(why_text(view, texts))


def test_above_the_target_the_sentence_says_so_instead_of_uncertainty() -> None:
    params = SentinelParams()  # theta_D 0.8, epsilon_D 0.02
    texts = Texts("pl")
    record = decided("stability", row("A", 0.5))

    def table(*chances: float) -> Comparison:
        rows = tuple(
            Impact(
                label=f"A{a}",
                kind="shift",
                p_on_time=p,
                tardiness=1.0,
                mean_cost=100.0,
                overrun=0.0,
                rollouts=200,
            )
            for a, p in enumerate(chances)
        )
        return Comparison(seed=1, rollouts=200, impacts=rows, decides=True)

    assert tie_kind(record, table(0.82, 0.95), params) == "target"
    assert tie_kind(record, table(0.78, 0.79), params) == "target"
    assert tie_kind(record, table(0.70, 0.72), params) == "similar"
    assert tie_kind(record, table(0.82, 0.82), params) is None
    assert tie_kind(record, table(0.95, 0.82), params) is None
    assert tie_kind(decided("on_time", row("A", 0.5)), table(0.82, 0.95), params) is None
    # Only the rows shown count: the record may hold a higher candidate that is not in the table.
    other = decided("stability", row("A", 0.5), row("B", 0.9))
    assert tie_kind(other, table(0.5, 0.4), params) is None
    assert texts.tie("target", "stability").startswith("Oba warianty osiągają docelową szansę;")


def test_a_recommendation_stored_before_this_version_keeps_its_figures() -> None:
    base = absence_recommendation()
    assert base.comparison is not None
    stored = base.comparison.model_dump(mode="json")
    del stored["decides"]
    old = Comparison.model_validate(stored)
    assert old.decides is False
    record = base.record.model_copy(update={"reason": "stability"})
    before = base.model_copy(update={"comparison": old, "record": record})
    assert before.as_shown == record
    assert _view(before, "pl").tie is None


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_template_and_the_ai_cite_only_numbers_from_the_record(language: Language) -> None:
    project = absence_project()
    recommendation = absence_recommendation()
    roles = project.require_model().role_names
    check_explanations(
        recommendation, project.observation(), planning.sentinel_params(project), roles
    )
    # The figures they see are those the page shows, row for row.
    record, view = recommendation.as_shown, _view(recommendation, language)
    rows = {c.label: c for c in record.candidates}
    assert view.with_action is not None
    texts = Texts(language)
    shown = rows[record.chosen]
    assert texts.pct(view.with_action.p_on_time).startswith(f"{_percent(shown.p_on_time)}{NBSP}")
    assert texts.decimal(view.with_action.tardiness) == texts.decimal(shown.tardiness)
    for alternative in view.alternatives:
        assert alternative.label in rows
        percent = _percent(rows[alternative.label].p_on_time)
        assert texts.pct(alternative.p_on_time).startswith(f"{percent}{NBSP}")
    comparison = recommendation.comparison
    assert comparison is not None and set(rows) == {i.label for i in comparison.impacts}


# --------------------------------------------------------------------------- whole projects


@pytest.mark.slow  # the showcase's pages in both languages (about 3 s), out of the default run
@pytest.mark.parametrize("language", LANGUAGES)
def test_the_showcase_shows_one_comparison(tmp_path: Path, language: Language) -> None:
    config = AppConfig(data_dir=tmp_path / "show", inline_jobs=True)
    services = Services(config)
    with TestClient(create_app(config, services)) as client:
        services.local_session()
        showcase.install(services)
        assert services.showcase is not None
        services.showcase(LOCAL_SESSION, language)
        pid = services.projects(LOCAL_SESSION)[0].id
        rows = services.store.events(LOCAL_SESSION, pid)
        state = replay(rows)
        texts = Texts(language)
        later_seen = 0
        for entry in state.recommendations:
            recommendation = entry.recommendation
            record, comparison = recommendation.record, recommendation.comparison
            assert comparison is not None
            before = replay([r for r in rows if r.seq < entry.seq]).project
            observation = before.observation()
            params = planning.sentinel_params(before)
            # A live project's comparison applies each action now, as approving it (v2.2.0).
            evaluator = planning.ApprovalEvaluator(before, observation, comparison.seed, params)
            evaluator.extend(noop(observation), 200)
            for c in record.candidates:
                if not c.dropped:  # evaluated again, independently of the deliberation
                    evaluator.extend(planning.candidate_of(c, observation), 200)
            seed = before.definition.settings.seed
            check_one_comparison(record, comparison, evaluator, params, seed)
            check_explanations(
                recommendation, observation, params, before.require_model().role_names
            )
            assert record.needs is not None
            assert planning.forecast(before).p_on_time == record.needs.p_on_time
            page = client.get(
                f"/projects/{pid}/recommendations/{entry.seq}", params={"lang": language}
            )
            assert page.status_code == 200 and problems(page.text) == []
            shown = visible_text(page.text)
            # The choice has the highest chance shown at both recommendations: no sentence.
            assert tie_kind(record, comparison, params) is None and not said_tie(shown)
            if record.reason in LATER_COMPONENTS:
                later_seen += 1
                reason = render(f"reason_{record.reason}", language)
                assert texts("why.reason", reason=reason) in shown
            for impact in comparison.impacts:
                assert texts.pct(impact.p_on_time) in shown
        # Which component decides depends on the showcase's calendar and on applying actions
        # now (v2.2.0); a later component is named whenever it decides (checked above).
        assert later_seen <= 1
        # The same recommendation decided by plan stability with another option shown higher:
        # now the page says why.
        latest = state.recommendations[-1].recommendation
        comparison = latest.comparison
        assert comparison is not None
        first, second, *rest = comparison.impacts
        higher = second.model_copy(update={"p_on_time": first.p_on_time + 0.02})
        impacts = (first, higher, *rest)
        changed = latest.model_copy(
            update={
                "comparison": comparison.model_copy(update={"impacts": impacts}),
                "record": latest.record.model_copy(update={"reason": "stability"}),
            }
        )
        event = Recommended(recommendation=changed).model_dump(mode="json")
        seq = services.store.append(LOCAL_SESSION, pid, "recommendation", event)
        page = client.get(f"/projects/{pid}/recommendations/{seq}", params={"lang": language})
        shown = visible_text(page.text)
        assert page.status_code == 200 and problems(page.text) == []
        assert texts.tie("similar", "stability") in shown
        assert texts.pct(higher.p_on_time) in shown
        if language == "pl":
            assert THE_SENTENCE in shown


@pytest.mark.data
@pytest.mark.slow  # five projects for a quarter of a run each (about 1 min)
def test_five_simulator_projects_decide_on_one_comparison(
    psplib_root: Path, evaluators: dict[int, Evaluator]
) -> None:
    counts: dict[str, int] = {}
    for instance, scenario in PROJECTS:
        evaluators.clear()
        spec = SimulatorSpec(instance=instance, scenario=scenario, start=START)
        simulation = Simulation(build_world(spec, psplib_root, Path("data/derived/baselines")))
        simulation.advance(DAYS)
        for key, count in check_run(simulation.main, evaluators, spec.seed).items():
            counts[key] = counts.get(key, 0) + count
    # Every side of the sentence was exercised: the chance decided, a later component decided
    # with no alternative shown higher, and with one.
    later = sum(counts.get(reason, 0) for reason in LATER_COMPONENTS)
    assert counts.get("on_time", 0) > 0
    assert 0 < counts["sentence"] < later


@pytest.mark.slow  # 0.5 s, kept out of the default run's budget
def test_a_tiny_simulator_project_decides_on_one_comparison(
    tiny: ProjectInstance, evaluators: dict[int, Evaluator]
) -> None:
    world = tiny_world(tiny, "sentinel")
    run = PolicyRun(world, "sentinel")
    run.advance(1000)
    assert run.finished
    assert check_run(run, evaluators, world.spec.seed)


def test_a_recommendation_survives_the_event_log() -> None:
    recommendation = absence_recommendation()
    event = Recommended(recommendation=recommendation)
    again = Recommended.model_validate(event.model_dump(mode="json")).recommendation
    assert again.comparison is not None and again.comparison.decides
    assert again.as_shown == recommendation.as_shown


# --------------------------------------------------------------------------- promise = result


def approve_now(project: LiveProject, recommendation: Recommendation) -> planning.ForecastResult:
    """Approve the recommended action as the page does (`Services.decide`) and forecast."""
    approved, rejection = planning.approval(project, recommendation)
    assert rejection is None
    outcome = project.resolve_action(approved.decision, approved.label, approved.kind)
    assert not isinstance(outcome, str)
    project.apply_action(outcome)
    return planning.forecast(project)


def check_promise(project: LiveProject, recommendation: Recommendation) -> None:
    """The overview after the approval shows what the card promised: the chance, the most likely
    finish and the bad case, the expected cost (spec 11.5, v2.2.0)."""
    assert recommendation.comparison is not None
    assert recommendation.record.gate in ("escalated", "deferred")  # waits for the manager
    promised = recommendation.comparison.impacts[0]
    entry = RecommendationEntry(seq=1, recommendation=recommendation, status="open")
    card = recommendation_view(project, entry, "pl").with_action
    shown = approve_now(project, recommendation)
    assert (shown.p_on_time, shown.quantiles) == (promised.p_on_time, promised.quantiles)
    assert shown.mean_cost == promised.mean_cost
    overview = forecast_view(project, shown)
    assert card is not None and (card.likely_finish, card.bad_finish) == (
        overview.p50,
        overview.p90,
    )
    assert card.expected_cost == overview.expected_cost


def test_approving_shows_what_the_card_promised() -> None:
    """B3 of the WP12 test: a substitute for an absent developer (a fresh project: approving
    changes it, and `absence_project` is shared)."""
    check_promise(checked_in(planned(small()), ABSENCE_CHECKIN), absence_recommendation())


def test_approving_after_a_task_grew_shows_what_the_card_promised() -> None:
    """B3 of the WP12 test, its second example: in the showcase, the task that grew by 150 %
    and then stopped with its developer away gets a substitute; the card promised 55 % and
    109 % of the budget, the overview showed 46 % and 113 %. Since v2.2.1 the growth reported
    before the substitute does not multiply the onboarding: it stays 2 crew-member days (it read
    5), and every world rebuilt after the approval is the one the card applied the action to."""
    spec = showcase.definition("pl")
    project = planned(spec)
    for checkin in showcase.checkins("pl")[:2]:
        project.apply_checkin(project.resolve_checkin(checkin))
    recommendation = planning.recommend(project)
    assert recommendation.record.chosen == "SUBST(3)"
    before = project.observation()
    approved, _ = planning.approval(project, recommendation)
    check_promise(project, recommendation)
    after = project.observation()
    ((j, _, added),) = after.handovers
    assert added == 2 and after.handover_positions == (1,)  # after the growth reported (5.1)
    assert work_history(after)[j][-1] == (work_history(before)[j][-1][0], 1.0, 2.0)
    seed = planning.forecast_seed(project, before.day)
    evaluator = Evaluator(before, seed, planning.sentinel_params(project))
    belief = Belief(after)
    for i in range(3):
        evaluator.world(i)
        applied = evaluator.templates[i].copy()
        streams = evaluator.streams[i]
        streams.rewind()
        Run(applied, streams, NoReaction(), record_events=False, check_plans=False).apply(
            approved.decision
        )
        belief_seq, _ = np.random.SeedSequence(derive_seed(seed, "rollout", str(i))).spawn(2)
        world = belief.sample(np.random.Generator(np.random.PCG64(belief_seq)))
        rebuilt = state_from_observation(after, world, plan=after.plan)
        assert rebuilt.remaining[j] == applied.remaining[j]  # the onboarding added once, as 2


def test_a_handover_without_an_earlier_growth_keeps_the_engines_order() -> None:
    """Spec 5.1 (v2.2.1): with no work increase before it at its work done, a handover's position
    is not reported, so such an observation, as every research one, is as it was."""
    project = checked_in(planned(small()), ABSENCE_CHECKIN)
    approve_now(project, absence_recommendation())
    after = project.observation()
    assert after.handovers and after.handover_positions == ()
    assert "handover_positions" not in after.model_dump()
