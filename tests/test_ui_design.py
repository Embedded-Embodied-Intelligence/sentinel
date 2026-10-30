"""The design system (WP10, ADR-0027, docs/design/brief.md): the tokens and their contrast, styles
that exist and are used, and the logic of the components: what sorts first, what folds, what a
button says, where a chart's flags go."""

import re
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from app_cases import ABSENCE_CHECKIN, checked_in, planned, small

from sentinel.app.ui.charts import (
    Line,
    chance_points,
    flags_in_tiers,
    forecast_strip,
    live_gantt,
)
from sentinel.app.ui.core import chance_level, nav_rank
from sentinel.app.ui.forms import Form, read_role_costs
from sentinel.app.ui.icons import PATHS, icon
from sentinel.app.ui.pages import Card, project_cards
from sentinel.app.ui.project import (
    HistoryItem,
    approve_label,
    finish_gap,
    option_rows,
    short_name,
    split_pending,
    toast_text,
    week_groups,
    why_points,
)
from sentinel.app.ui.setup import fewer_of_role, more_of_role, role_rows
from sentinel.app.ui.sim import compare_rows, verdict
from sentinel.app.ui.text import Texts

UI = Path(__file__).parents[1] / "src/sentinel/app/ui"
CSS = (UI / "static/sentinel.css").read_text(encoding="utf-8")
EN, PL = Texts("en"), Texts("pl")
# Classes that only hook a template to a script or to the table's layout; no style needs them.
HOOKS = {"cell-days", "cell-menu", "pop-value"}


def _tokens(block: str) -> dict[str, str]:
    return {k: v.strip().lower() for k, v in re.findall(r"(--[\w-]+):\s*([^;]+);", block)}


def _light_and_dark() -> tuple[dict[str, str], dict[str, str]]:
    light = _tokens(CSS[CSS.index(":root {") : CSS.index("@media (prefers-color-scheme: dark)")])
    start = CSS.index(":root:not([data-theme")
    dark = _tokens(CSS[start : CSS.index("}", start)])
    return light, {**light, **dark}


def _luminance(colour: str) -> float:
    channels = [int(colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize("theme", [0, 1])
def test_the_tokens_keep_their_contrast(theme: int) -> None:
    tokens = _light_and_dark()[theme]
    for text in (
        "--text",
        "--text-2",
        "--muted",
        "--primary",
        "--link",
        "--good",
        "--warn",
        "--bad",
    ):
        for surface in ("--surface", "--surface-2", "--bg"):
            assert _contrast(tokens[text], tokens[surface]) >= 4.5, (text, surface)
    for text, background in (
        ("--primary-ink", "--primary"),
        ("--good", "--good-bg"),
        ("--warn", "--warn-bg"),
        ("--bad", "--bad-bg"),
        ("--neutral", "--neutral-bg"),
        ("--primary", "--primary-soft"),
        ("--danger-ink", "--danger"),
        ("--toast-ink", "--toast-bg"),
    ):
        assert _contrast(tokens[text], tokens[background]) >= 4.5, (text, background)
    # UI components: input borders and the chart's lines against the card (WCAG 1.4.11)
    assert _contrast(tokens["--border-strong"], tokens["--surface"]) >= 3
    assert _contrast(tokens["--focus"], tokens["--surface"]) >= 3


def test_the_tokens_are_those_of_the_brief() -> None:
    light, dark = _light_and_dark()
    assert (light["--primary"], light["--bg"], light["--bad"]) == ("#0b6872", "#f6f7f9", "#b3261e")
    assert (dark["--primary"], dark["--surface"], dark["--good"]) == (
        "#5cc3cc",
        "#171b20",
        "#6fd08e",
    )


def _template_classes() -> set[str]:
    found: set[str] = set()
    for path in UI.glob("templates/*.html"):
        text = re.sub(r"\{%.*?%\}|\{\{.*?\}\}", " ", path.read_text(encoding="utf-8"), flags=re.S)
        for value in re.findall(r'class="([^"]*)"', text):
            found |= {name for name in value.split() if re.fullmatch(r"[a-z][\w-]*[a-z0-9]", name)}
    return found


def test_every_style_is_used_and_every_class_has_a_style() -> None:
    rules = re.sub(r"/\*.*?\*/|url\([^)]*\)|\d*\.\d+", "", CSS, flags=re.S)
    defined = set(re.findall(r"\.(-?[a-zA-Z_][\w-]*)", rules))
    used = _template_classes()
    code = " ".join(
        p.read_text(encoding="utf-8")
        for p in [*UI.glob("*.py"), UI / "static/sentinel.js", *UI.glob("templates/*.html")]
    )
    built = re.compile(r"(badge|callout|hint|delta)-[a-z]+|is-[a-z]+")
    unused = sorted(
        name
        for name in defined
        if not built.fullmatch(name)
        and not re.search(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", code)
    )
    assert unused == []
    assert sorted(used - defined - HOOKS) == []


def test_the_pages_load_nothing_from_the_network() -> None:
    assert "http" not in re.sub(r"https://[^ ]*brief", "", CSS.split("*/", 1)[1])
    for path in UI.glob("templates/*.html"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r'<(script|link|img)\b[^>]*(src|href)="https?:', text), path.name


def test_icons_are_decoration() -> None:
    for name in PATHS:
        svg = str(icon(name, 16))
        assert 'aria-hidden="true"' in svg and 'width="16"' in svg and "<title" not in svg


def test_the_status_words_keep_the_code_s_thresholds() -> None:
    assert [chance_level(p) for p in (None, 0.2, 0.49, 0.5, 0.79, 0.8, 1.0)] == [
        "neutral",
        "bad",
        "bad",
        "warn",
        "warn",
        "good",
        "good",
    ]
    assert PL("chance.level.bad") == "Termin zagrożony" and EN("chance.level.warn")


def test_projects_with_a_decision_come_first_then_the_lowest_chance() -> None:
    cards = [
        Card("a", "live", "calm", "/", planned=True, chance=0.9),
        Card("b", "live", "late", "/", planned=True, chance=0.2),
        Card("c", "live", "waiting", "/", planned=True, chance=0.95, pending=1),
        Card("d", "live", "new", "/", planned=True),
        Card("e", "live", "draft", "/"),
        Card("f", "simulator", "example", "/"),
    ]
    assert [c.name for c in project_cards(cards)] == ["waiting", "late", "calm", "new"]
    assert nav_rank("decision", 0.99) < nav_rank("bad", 0.01) < nav_rank("good", None)


def _rec(**values: Any) -> Any:
    base = {
        "can_wait": False,
        "acts": True,
        "title": "Do it",
        "tie": None,
        "reason": "on_time",
        "reason_text": "it is best",
        "options": 3,
        "compared": True,
        "without": SimpleNamespace(p_on_time=0.39, tardiness=3.0, expected_cost=91.0),
        "with_action": SimpleNamespace(p_on_time=0.55, tardiness=2.0, expected_cost=92.0),
        "alternatives": [],
        "changes": [],
        "budget": 84.0,
    }
    return SimpleNamespace(**{**base, **values})


def test_what_can_wait_folds_unless_nothing_else_is_waiting() -> None:
    urgent, later = _rec(title="now"), _rec(can_wait=True, title="later")
    assert split_pending([later, urgent]) == ([urgent], [later])
    assert split_pending([later]) == ([later], [])
    assert split_pending([]) == ([], [])


def test_the_comparison_has_the_choice_first_and_no_change_last() -> None:
    def alternative(label: str, p: float) -> Any:
        return SimpleNamespace(
            label=label,
            title=label,
            p_on_time=p,
            tardiness=1.0,
            expected_cost=90.0,
            runner_up=False,
            dropped=False,
        )

    long = "Substitute: somebody with a rather long name takes over a part in a task"
    rec = _rec(
        title=long,
        alternatives=[alternative("NOOP", 0.39), alternative("A", 0.53), alternative("B", 0.36)],
    )
    rows = option_rows(rec, EN)
    assert [r.title for r in rows] == [long, "A", "B", EN("rec.alt_noop")]
    assert rows[0].chosen and rows[-1].base and not rows[1].chosen
    assert (rows[0].diff, rows[1].diff, rows[2].diff, rows[3].diff) == (
        "+16 pts",
        "+14 pts",
        "\u22123 pts",
        "",
    )
    assert rows[0].short is not None and rows[0].short.endswith("…") and len(rows[0].short) <= 61
    assert rows[1].short is None and short_name("x" * 60) is None
    assert option_rows(_rec(), EN) == []


def test_the_reasons_are_short_sentences_from_the_figures_shown() -> None:
    points = why_points(_rec(), PL)
    assert points[0] == "Bez zmian: 39\u00a0%. Z tą zmianą: 55\u00a0%."
    assert "daje" not in points[0] and "it is best" in points[1]
    assert any("2" in point for point in points[2:])


@pytest.mark.parametrize(
    ("kind", "key"),
    [
        ("subst", "rec.approve.subst"),
        ("subst_all", "rec.approve.subst"),
        ("subst_all_reseq_m", "rec.approve"),
        ("ot", "rec.approve.overtime"),
        ("ot_reseq_m", "rec.approve"),
        ("descope", "rec.approve.descope"),
        ("reseq_s", "rec.approve.reseq"),
        ("shift", "rec.approve.shift"),
        ("proposal_reseq_m", "rec.approve"),
    ],
)
def test_the_approve_button_names_what_is_approved(kind: str, key: str) -> None:
    assert approve_label(kind) == key


def test_a_finish_date_reads_against_the_deadline() -> None:
    calendar = planned(small()).calendar
    deadline = date(2026, 11, 17)
    assert finish_gap(date(2026, 11, 13), None, calendar, PL) is None
    early = finish_gap(date(2026, 11, 13), deadline, calendar, PL)
    assert early is not None and early.tone == "good" and "2 dni robocze przed" in early.text
    late = finish_gap(date(2026, 11, 18), deadline, calendar, PL)
    assert late is not None and late.tone == "warn" and "1 dzień roboczy po" in late.text
    worst = finish_gap(date(2026, 11, 18), deadline, calendar, PL, worst=True)
    assert worst is not None and worst.tone == "bad"
    same = finish_gap(deadline, deadline, calendar, EN)
    assert same is not None and same.tone == "neutral"


def test_the_toast_adds_the_new_chance_when_it_is_known() -> None:
    forecast = SimpleNamespace(p_on_time=0.42)
    summary: Any = SimpleNamespace(forecast=forecast, previous_p=0.39)
    assert (
        toast_text("checkin_saved", summary, PL)
        == "Raport zapisany. Szansa: 39\u00a0% → 42\u00a0%."
    )
    assert toast_text("approved", summary, EN) is not None and "42" in str(
        toast_text("approved", summary, EN)
    )
    assert toast_text("rejected", summary, EN) is None and toast_text("approved", None, EN) is None


def test_history_groups_by_week_in_the_order_given() -> None:
    def item(day: date) -> HistoryItem:
        return HistoryItem("change", "", "", day)

    today = date(2026, 11, 18)
    items = [item(date(2026, 11, 18)), item(date(2026, 11, 16)), item(date(2026, 11, 13))]
    groups = week_groups(items, PL, today)
    assert [g.title for g in groups] == ["Ten tydzień", "9–13\u00a0lis"]
    assert [len(g.items) for g in groups] == [2, 1]
    assert EN.week_range(date(2026, 11, 30)) == "30\u00a0Nov – 4\u00a0Dec"


def test_chart_flags_never_overlap_and_turn_at_the_end() -> None:
    lines = [
        Line(10, "line-today", "Status · 13 Nov", 20.0),
        Line(12, "line-deadline", "Deadline · 18 Dec", 22.0),
        Line(50, "line-window", "Bad case · 31 Dec", 95.0),
    ]
    placed = flags_in_tiers(lines, 600)
    assert [flag.tier for flag in placed][:2] == [0, 1]
    assert placed[2].flip and not placed[0].flip
    spans: dict[int, list[tuple[float, float]]] = {}
    for flag in placed:
        width = flag.width / 600 * 100
        left, right = (flag.x - width, flag.x) if flag.flip else (flag.x, flag.x + width)
        assert all(right <= a or left >= b for a, b in spans.get(flag.tier, []))
        spans.setdefault(flag.tier, []).append((left, right))


def test_the_chart_shows_status_deadline_window_threats_and_absence() -> None:
    project = checked_in(planned(small()), ABSENCE_CHECKIN)
    chart = live_gantt(
        project,
        EN,
        date(2026, 11, 5),
        (date(2026, 11, 18), date(2026, 11, 24)),
        {"T1": "The task decides"},
    )
    rows = {item.row.key: item for item in chart.rows}
    assert "T1" in rows and rows["T1"].row.threat == "The task decides"
    assert rows["T2"].row.state == "done" and rows["T2"].bars[-1].cls == "bar-done"
    assert any(item.row.state == "absence" for item in chart.rows)
    assert any(bar.cls == "bar-rest" for bar in rows["T1"].bars)
    classes = [line.cls for line in chart.lines]
    assert classes.count("line-window") == 2 and "line-deadline" in classes
    assert chart.window is not None and chart.window[1] > 0
    assert all(0 <= bar.x <= 100 for item in chart.rows for bar in item.bars)
    assert chart.height == chart.top + 32 * len(chart.rows) + 4
    assert "3 tasks" in chart.desc


def test_the_strip_runs_from_today_to_the_later_of_bad_case_and_deadline() -> None:
    calendar = planned(small()).calendar
    strip = forecast_strip(
        date(2026, 11, 2), date(2026, 11, 6), date(2026, 11, 13), date(2026, 11, 20), calendar
    )
    assert strip.deadline == 100.0 and 0 < strip.likely < strip.bad < 100
    no_deadline = forecast_strip(
        date(2026, 11, 2), date(2026, 11, 6), date(2026, 11, 13), None, calendar
    )
    assert no_deadline.deadline is None and no_deadline.bad == 100.0


def test_the_chart_of_the_chance_has_one_point_per_report() -> None:
    values = [(date(2026, 11, 2), 0.94), (date(2026, 11, 6), 0.5), (date(2026, 11, 13), 0.0)]
    points = chance_points(values, EN)
    assert [p.x for p in points] == [3.0, 50.0, 97.0]
    assert points[0].y < points[1].y < points[2].y == 80.0
    assert points[1].value == "50\u00a0%" and chance_points(values[:1], EN)[0].x == 50.0


def test_roles_grow_and_shrink_with_names_until_the_manager_gives_some() -> None:
    team = more_of_role([], "Tester", 2)
    assert [p.name for p in team] == ["Tester 1", "Tester 2"] and len({p.key for p in team}) == 2
    team = more_of_role(team, "Developer")
    rows = role_rows(None, team)
    assert [(r.name, r.count, r.cost) for r in rows] == [("Tester", 2, 1.0), ("Developer", 1, 1.0)]
    assert [p.name for p in fewer_of_role(team, "tester")] == ["Tester 1", "Developer 1"]
    assert [p.name for p in more_of_role(fewer_of_role(team, "Tester"), "Tester")][-1] == "Tester 2"


def test_a_daily_cost_of_the_team_step_keeps_the_old_value_when_it_is_not_a_number() -> None:
    from sentinel.app.models import RoleCost

    current = (RoleCost(role="Tester", daily_cost=2.0),)
    form = Form({"cost_0": "x", "cost_1": "1,5"})
    assert read_role_costs(form, ["Tester", "Developer"], current) == (
        RoleCost(role="Tester", daily_cost=2.0),
        RoleCost(role="Developer", daily_cost=1.5),
    )
    assert read_role_costs(Form({"cost_0": "1"}), ["Tester"], current) == ()


def _side(policy: str, finish: date, makespan: int, late: int, cost: float, on_time: bool) -> Any:
    return SimpleNamespace(
        policy=policy,
        finish=finish,
        makespan=makespan,
        late_days=late,
        on_time=on_time,
        cost=cost,
        cost_ratio=cost / 100,
        plan_changes=3,
        hired=0,
        substituted=1,
    )


def test_a_finished_simulation_tells_its_story_in_one_sentence() -> None:
    main = _side("sentinel", date(2027, 2, 15), 80, 8, 103.0, False)
    other = _side("no_reaction", date(2027, 3, 1), 90, 18, 102.0, False)
    assert verdict([main, other], PL) == (
        "Z Sentinelem projekt skończył się 10 dni roboczych wcześniej niż bez reakcji, ale wciąż "
        "8 dni roboczych po terminie."
    )
    rows = compare_rows([main, other], EN)
    assert (rows[0].tone, rows[1].tone, rows[2].tone) == ("good", "good", "bad")
    assert rows[0].difference == "10 working days earlier" and rows[2].difference == "+1 unit"
    on_time = _side("sentinel", date(2027, 2, 1), 70, 0, 100.0, True)
    assert "met the deadline" in verdict([on_time, other], EN)
    assert "later" in verdict([_side("sentinel", date(2027, 3, 5), 95, 23, 1.0, False), other], EN)
    assert verdict([on_time], EN) == EN("sim.verdict.single_on_time")


def test_formats_of_the_new_components() -> None:
    today = date(2026, 11, 18)
    assert (PL.ago(today, today), PL.ago(date(2026, 11, 17), today)) == ("dziś", "wczoraj")
    assert PL.ago(date(2026, 11, 16), today) == "2 dni temu"
    assert EN.ago(date(2026, 11, 19), today).endswith("19\u00a0Nov")
    assert PL.date_long(date(2026, 11, 13)) == "pt. 13\u00a0lis 2026"
    assert PL.cost_of_parts(27.4, 84) == ("27 z 84", "jednostek kosztu")
    assert EN.cost_of_parts(1200, 1500) == ("1,200 of 1,500", "cost units")
    assert EN.reasons(["people", "money"]) == "affects people, costs money"
    assert len(PL.weekdays.split(",")) == 7 and len(EN.months.split(",")) == 12
