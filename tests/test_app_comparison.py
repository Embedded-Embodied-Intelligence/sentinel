"""One comparison in the application (WP9d, spec v2.0.3 sections 11.5-11.7): the decision, the
display and both explanations come from one record on the forecast's 200 sampled worlds, racing
stage 1 stays that of spec section 6, and the page says so when a later component decides."""

import re
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any

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
from sentinel.app.models import Language
from sentinel.app.planning import (
    LATER_COMPONENTS,
    Comparison,
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
from sentinel.app.views import recommendation_view
from sentinel.dashboard.explain import _percent, checkable, template_explanation
from sentinel.experiments.runs import derive_seed
from sentinel.interpret.explain import check, explain, render_record
from sentinel.llm import FakeLlmClient
from sentinel.model import ProjectInstance
from sentinel.policies.base import Decision
from sentinel.simulation.state import Observation

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


def check_run(run: PolicyRun, evaluators: dict[int, Evaluator], seed: int) -> dict[str, int]:
    """Every deliberation of a simulator run: one comparison, explanations citing the record, NOOP
    on the forecaster's rollouts, and on the timeline the sentence exactly when a later component
    decides; the deliberations by their deciding component."""
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
            kind = tie_kind(record, params)
            assert (kind is not None) == (record.reason in LATER_COMPONENTS)
            if entry is not None and kind is not None:
                assert texts.tie(kind, record.reason) in entry.text
            elif entry is not None:
                assert " uncertainty)" not in entry.text and "niepewności)" not in entry.text
                assert "target chance" not in entry.text and "docelową szansę" not in entry.text
    for record in records:
        reasons[record.reason] = reasons.get(record.reason, 0) + 1
        comparison = sentinel.comparisons[record.day]
        check_one_comparison(record, comparison, evaluators[record.day], params, seed)
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
        makespans = planning.forecast_rollouts(observation, 200, comparison.seed)[0]
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


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_tie_sentence_appears_exactly_when_a_later_component_decides(
    language: Language,
) -> None:
    texts = Texts(language)
    base = absence_recommendation()
    params = SentinelParams()
    sentences = {}
    for reason in ("on_time", "only_candidate", "needs_met", *sorted(LATER_COMPONENTS)):
        record = base.record.model_copy(update={"reason": reason})
        view = _view(base.model_copy(update={"record": record}), language)
        said = why_text(view, texts)
        later = reason in LATER_COMPONENTS
        assert (view.tie is not None) == later
        assert (" uncertainty)" in said or "niepewności)" in said) == later
        assert (texts("why.reason", reason=view.reason_text) in said) == (not later)
        if later:
            sentence = texts.tie("similar", reason)
            assert sentence in said and tie_kind(record, params) == "similar"
            sentences[reason] = sentence
        assert problems(said) == []
    assert len(set(sentences.values())) == len(LATER_COMPONENTS)
    if language == "pl":
        assert sentences["stability"] == f"{THE_SENTENCE}mniej terminów."
    # An action kept out on a later component: the plan is kept, and the page still says why.
    noop = next(c for c in base.record.candidates if c.label == "NOOP")
    other = next(c for c in base.record.candidates if c.label == base.record.chosen)
    kept = decided("stability", noop, other)
    view = _view(base.model_copy(update={"record": kept}), language)
    assert not view.acts and view.tie == "similar"
    assert texts.tie("similar", "stability") in why_text(view, texts)


def test_above_the_target_the_sentence_says_so_instead_of_uncertainty() -> None:
    params = SentinelParams()  # theta_D 0.8, epsilon_D 0.02
    texts = Texts("pl")
    assert tie_kind(decided("stability", row("A", 0.82), row("B", 0.95)), params) == "target"
    assert tie_kind(decided("stability", row("A", 0.78), row("B", 0.79)), params) == "target"
    assert tie_kind(decided("stability", row("A", 0.70), row("B", 0.72)), params) == "similar"
    assert tie_kind(decided("on_time", row("A", 0.82), row("B", 0.60)), params) is None
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
            evaluator = Evaluator(observation, comparison.seed, params)
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
            later = record.reason in LATER_COMPONENTS
            kind = tie_kind(record, params)
            assert (kind is not None) == later
            assert (kind is not None and texts.tie(kind, record.reason) in shown) == later
            later_seen += later
            first = comparison.impacts[0]
            assert texts.pct(first.p_on_time) in shown
            for impact in comparison.impacts:
                assert texts.pct(impact.p_on_time) in shown
            if language == "pl" and later:
                assert THE_SENTENCE in shown
        assert later_seen == 1  # the substitution beats the re-plan on plan stability


@pytest.mark.data
@pytest.mark.slow  # five projects for a quarter of a run each (about 1 min)
def test_five_simulator_projects_decide_on_one_comparison(
    psplib_root: Path, evaluators: dict[int, Evaluator]
) -> None:
    reasons: dict[str, int] = {}
    for instance, scenario in PROJECTS:
        evaluators.clear()
        spec = SimulatorSpec(instance=instance, scenario=scenario, start=START)
        simulation = Simulation(build_world(spec, psplib_root, Path("data/derived/baselines")))
        simulation.advance(DAYS)
        for reason, count in check_run(simulation.main, evaluators, spec.seed).items():
            reasons[reason] = reasons.get(reason, 0) + count
    # The rule was exercised on both sides of the sentence.
    assert reasons.get("on_time", 0) > 0
    assert sum(reasons.get(reason, 0) for reason in LATER_COMPONENTS) > 0


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
