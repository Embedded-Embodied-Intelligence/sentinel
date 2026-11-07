"""The decision model of the v2 interface (WP15; spec section 11.8): the gate at Lambda = 0, the
corrections of a pending decision and their promise, the validity date and cost of delay, and
the lifecycle in the project's log."""

from datetime import date
from typing import Any

import pytest
from app_cases import ABSENCE_CHECKIN, DEV, checked_in, planned, small

from sentinel.app import decisions, planning
from sentinel.app.config import AppConfig
from sentinel.app.events import replay
from sentinel.app.models import Person
from sentinel.app.services import Services
from sentinel.app.store import LOCAL_SESSION
from sentinel.app.views import project_view
from sentinel.policies.base import Decision, Reseq, Shift, Subst


def four_developers() -> Any:
    """`small` with a fourth developer, so that an absent one has two possible substitutes."""
    definition = small()
    team = (*definition.team, Person(key="d", name="Dan", role=DEV))
    return definition.model_copy(update={"team": team})


def test_the_v2_gate_asks_for_every_action() -> None:
    project = planned(small(autonomy=3))
    params = planning.sentinel_params(project, decisions.GATE)
    assert params.autonomy == 0
    plan_only = Decision(operations=(Shift(starts={}),))
    assert params.needs_approval(plan_only)
    assert params.needs_approval(Decision(operations=(Reseq(starts={}),)))
    assert not planning.sentinel_params(project).needs_approval(plan_only)  # the project's 3


def test_a_v2_deliberation_is_never_applied_automatically(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every deliberation v2 asks for runs at Lambda = 0 (spec 11.8), whatever the setting."""
    seen: list[int | None] = []
    real = planning.recommend

    def spy(project: Any, **kwargs: Any) -> Any:
        seen.append(kwargs.get("autonomy"))
        return real(project, **kwargs)

    monkeypatch.setattr(planning, "recommend", spy)
    services = Services(AppConfig(data_dir=tmp_path, inline_jobs=True))
    services.local_session()
    row = services.create(LOCAL_SESSION, small(autonomy=3), "en")
    services.plan(LOCAL_SESSION, row.id, "en")
    result = services.checkin(LOCAL_SESSION, row.id, ABSENCE_CHECKIN, "en", autonomy=0)
    assert seen == [0]
    state = services.state(LOCAL_SESSION, row.id)
    assert all(entry.status != "auto" for entry in state.recommendations)
    assert result.project.open_recommendation is not None
    assert state.open is not None and state.open.validity is not None  # computed after it


def test_a_correction_is_evaluated_and_keeps_its_promise(tmp_path: Any) -> None:
    services = Services(AppConfig(data_dir=tmp_path, inline_jobs=True))
    services.local_session()
    row = services.create(LOCAL_SESSION, four_developers(), "en")
    services.plan(LOCAL_SESSION, row.id, "en")
    services.checkin(LOCAL_SESSION, row.id, ABSENCE_CHECKIN, "en", autonomy=0)
    state = services.state(LOCAL_SESSION, row.id)
    entry = state.open
    assert entry is not None and entry.recommendation.chosen is not None
    assert decisions.parameter_of(entry.recommendation.chosen.decision) == "subst"
    options = services.correction_options(LOCAL_SESSION, row.id, entry.seq)
    assert options[0].current and len(options) == 2
    other = next(o for o in options if not o.current)
    assert other.person in ("Cleo", "Dan")
    view = services.correct(LOCAL_SESSION, row.id, entry.seq, other.key, "en")
    state = services.state(LOCAL_SESSION, row.id)
    corrected = state.recommendation(entry.seq)
    assert corrected is not None and corrected.corrected and corrected.status == "open"
    assert corrected.validity is not None  # computed again for the corrected action
    chosen = corrected.recommendation.chosen
    assert chosen is not None and chosen.label.endswith(other.key)
    op = chosen.decision.operations[0]
    assert isinstance(op, Subst) and op.workers == other.operation.workers  # type: ignore[attr-defined]
    rec = next(r for r in view.recommendations if r.seq == entry.seq)
    assert other.person in rec.title
    promised = corrected.recommendation.impact(chosen.label)
    assert promised is not None
    services.decide(LOCAL_SESSION, row.id, entry.seq, "approve", "en", autonomy=0)
    after = services.forecast_now(LOCAL_SESSION, row.id)
    assert after is not None and after.p_on_time == promised.p_on_time
    crew = services.live(LOCAL_SESSION, row.id, "en").tasks[0].crew_names
    assert other.person in crew


def test_validity_stops_where_waiting_no_longer_helps() -> None:
    project = checked_in(planned(small()), ABSENCE_CHECKIN)
    recommendation = planning.recommend(project, autonomy=0)
    found = decisions.validity(project, recommendation)
    noop = recommendation.impact("NOOP")
    assert noop is not None and found.noop == noop.p_on_time  # the forecast's worlds
    chosen = recommendation.impact(recommendation.record.chosen)
    assert chosen is not None and found.chances[0] == chosen.p_on_time  # the card's figure
    eps = planning.sentinel_params(project).eps_d
    assert all(p - found.noop >= eps for p in found.chances[:-1])
    if found.valid_day is not None:
        assert found.valid_day == recommendation.day + len(found.chances) - 2 or (
            len(found.chances) == decisions.VALIDITY_DAYS + 1
        )
        assert found.delay is not None and found.delay >= 0


def test_the_lifecycle_replays_from_the_log(tmp_path: Any) -> None:
    services = Services(AppConfig(data_dir=tmp_path, inline_jobs=True))
    services.local_session()
    row = services.create(LOCAL_SESSION, small(), "en")
    services.plan(LOCAL_SESSION, row.id, "en")
    services.checkin(LOCAL_SESSION, row.id, ABSENCE_CHECKIN, "en", autonomy=0)
    seq = services.state(LOCAL_SESSION, row.id).open.seq  # type: ignore[union-attr]
    services.decide(LOCAL_SESSION, row.id, seq, "reject", "en", reason="too_expensive")
    rows = services.store.events(LOCAL_SESSION, row.id)
    types = [r.type for r in rows]
    assert types[-3:] == ["recommendation", "validity", "decision"]
    assert rows[-1].payload["reason"] == "too_expensive" and rows[-1].payload["brief"] is not None
    state = replay(rows)
    assert state.recommendation(seq).status == "rejected"  # type: ignore[union-attr]
    view = project_view(row.id, state, "en")
    assert view.recommendations[-1].status_text == "rejected"
    expired = replay(rows[:-1])
    assert expired.open is not None
    assert date(2026, 11, 2) == state.project.definition.start
