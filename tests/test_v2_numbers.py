"""The numbers and states of the v2 interface (WP15; spec section 11.8): "N na 100", the three
states, the verdict's days, the points and zones of the "Zapas czasu" chart, the next 7 days
and the next report day."""

from datetime import date

import pytest

from sentinel.app.ui.v2.numbers import (
    BufferPoint,
    buffer_point,
    hits,
    per_hundred,
    reserve_of,
    state_of,
    verdict,
    work_share,
    zone_of,
)


@pytest.mark.parametrize(
    ("p", "n"),
    [
        (0.0, 0),
        (1.0, 100),
        (0.39, 39),
        (0.395, 40),  # half up, as every figure of a recommendation (spec 11.5)
        (0.575, 58),  # stored just below 0.575: still 58
        (0.004, 1),  # never "0 na 100" unless exact
        (0.996, 99),  # never "100 na 100" unless exact
        (78 / 200, 39),
    ],
)
def test_per_hundred(p: float, n: int) -> None:
    assert per_hundred(p) == n


def test_hits_are_the_worlds_on_time() -> None:
    assert hits(0.39, 200) == 78
    assert hits(0.575, 200) == 115
    assert hits(1.0, 200) == 200


@pytest.mark.parametrize(
    ("n", "state"),
    [(100, "good"), (80, "good"), (79, "warn"), (50, "warn"), (49, "bad"), (0, "bad")],
)
def test_states_at_80_and_50(n: int, state: str) -> None:
    assert state_of(n) == state


def test_verdict_days() -> None:
    assert verdict(0.9, 6) == verdict(0.9, 6)
    good = verdict(0.81, 6)
    assert (good.state, good.n, good.days) == ("good", 81, 6)
    warn = verdict(0.6, 2)
    assert (warn.state, warn.days) == ("warn", 2)
    bad = verdict(0.39, -2)
    assert (bad.state, bad.n, bad.days) == ("bad", 39, 2)
    # 99 of 200 rounds up to 50 while the median can be a day late: no negative reserve
    edge = verdict(99 / 200, -1)
    assert (edge.state, edge.n, edge.days) == ("warn", 50, 0)


def test_buffer_points_and_zones() -> None:
    reserve = reserve_of(deadline_day=40, baseline_end=30)
    assert reserve == 10
    start = buffer_point(0.0, 100.0, likely_end=28, baseline_end=30, reserve=reserve)
    assert start == BufferPoint(0.0, 0.0) and zone_of(start) == "good"
    half = buffer_point(50.0, 100.0, likely_end=33, baseline_end=30, reserve=reserve)
    assert half == BufferPoint(0.5, 0.3) and zone_of(half) == "good"  # 0.3 <= 1/3
    amber = buffer_point(50.0, 100.0, likely_end=35, baseline_end=30, reserve=reserve)
    assert zone_of(amber) == "warn"  # 0.5 between 1/3 and 2/3
    red = buffer_point(50.0, 100.0, likely_end=37, baseline_end=30, reserve=reserve)
    assert zone_of(red) == "bad"  # 0.7 above 2/3
    late = buffer_point(29.0, 100.0, likely_end=42, baseline_end=30, reserve=reserve)
    assert late.used == pytest.approx(1.2) and zone_of(late) == "bad"
    assert zone_of(BufferPoint(1.0, 1.0)) == "warn"  # all work done on the deadline
    assert zone_of(BufferPoint(0.0, 0.2)) == "warn"  # early use of the reserve is a warning


def test_work_share_counts_done_and_started_tasks() -> None:
    tasks = [
        ("done", None, 4.0),
        ("in_progress", 50.0, 12.0),
        ("paused", 25.0, 4.0),
        ("not_started", None, 10.0),
        ("removed", None, 6.0),
    ]
    assert work_share(tasks) == (4.0 + 6.0 + 1.0, 30.0)
    assert work_share([]) == (0.0, 0.0)
    assert buffer_point(0.0, 0.0, 30, 30, 10).work == 0.0


def test_next_report_day() -> None:
    from types import SimpleNamespace

    from sentinel.app.ui.v2.overview import next_report

    view = SimpleNamespace(
        checkins=[SimpleNamespace(date=date(2026, 11, 13))],  # a Friday
        definition=SimpleNamespace(start=date(2026, 11, 2)),
    )
    assert next_report(view, date(2026, 11, 9)) == date(2026, 11, 19)  # type: ignore[arg-type]
    assert next_report(view, date(2026, 11, 25)) == date(2026, 11, 26)  # type: ignore[arg-type]
