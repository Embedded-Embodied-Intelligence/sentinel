"""The screens of a live project (WP9b; spec section 11): the overview with the chance of meeting
the deadline, the check-in, a recommendation with its decision, the history and the settings.

Every number shown comes from the services' views: the forecast of spec section 11.4 (cached by
the project's last change), the recommendation of spec section 11.5 with the figures of its own
simulated futures, and the event log for the history.
"""

import dataclasses
import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response

from sentinel.app.calendar import WorkCalendar
from sentinel.app.errors import AppError
from sentinel.app.events import (
    BaselineSet,
    CheckinDone,
    Created,
    Decided,
    DefinitionChanged,
    Recommended,
    Undone,
    parse,
)
from sentinel.app.live import LiveProject, role_key
from sentinel.app.models import (
    AbsenceReport,
    CheckIn,
    NewTaskReport,
    ProjectDefinition,
    WorkIncreaseReport,
)
from sentinel.app.planning import half_up
from sentinel.app.services import ChanceStep, JobView
from sentinel.app.ui.charts import chance_points, forecast_strip, live_gantt
from sentinel.app.ui.core import STATIC_DIR, Ui, chance_level, is_htmx
from sentinel.app.ui.forms import Form, read_checkin, read_settings, team_roles
from sentinel.app.ui.pages import job_progress, trend
from sentinel.app.ui.text import Texts
from sentinel.app.views import (
    ForecastSummary,
    ForecastView,
    OutcomeView,
    ProjectView,
    RecommendationView,
    TaskView,
)

HISTORY_FILTERS = ("all", "checkins", "recommendations", "changes")
HISTORY_SHOWN = 20  # entries before "show older"
NEXT_DAYS = 10  # unstarted tasks planned within this many working days are shown at check-in
FUTURE_CHECKIN_DAYS = 7  # a check-in dated further ahead asks for a confirmation
FLASHES_WITH_CHANCE = ("checkin_saved", "approved")  # toasts that add the new chance when known


def why_points(rec: RecommendationView, texts: Texts) -> list[str]:
    """Why Sentinel recommends the action, in short plain sentences from the figures shown with it
    (spec sections 10.4 and 11.5; the template explanation without internal terms)."""
    before = rec.without
    after = rec.with_action
    options = max(rec.options, len(rec.alternatives) + 1)
    if not rec.acts or after is None:
        if before is None:
            return [texts("why.keep_plain")]
        if rec.reason == "needs_met":
            return [texts("why.on_track", p=texts.pct(before.p_on_time))]
        kept = [texts("why.keep", options=options, p=texts.pct(before.p_on_time))]
        return kept if rec.tie is None else [*kept, texts.tie(rec.tie, rec.reason)]
    parts = []
    if before is not None:
        parts.append(
            texts("why.without", p=texts.pct(before.p_on_time), after=texts.pct(after.p_on_time))
        )
    chosen = texts("why.with" if rec.compared else "why.with_own", options=options)
    if rec.tie is None:
        chosen = f"{chosen} {texts('why.reason', reason=rec.reason_text)}"
    parts.append(chosen)
    if after.tardiness >= 0.05 and before is not None:
        parts.append(
            texts(
                "why.delay_from",
                days=texts.decimal(after.tardiness),
                before=texts.decimal(before.tardiness),
            )
        )
    elif after.tardiness >= 0.05:
        parts.append(texts("why.delay", days=texts.decimal(after.tardiness)))
    runner = next((a for a in rec.alternatives if a.runner_up), None)
    if runner is not None:
        title = texts("rec.alt_noop") if runner.label == "NOOP" else runner.title
        parts.append(texts("why.runner", title=title, p=texts.pct(runner.p_on_time)))
    if rec.tie is not None:
        parts.append(texts.tie(rec.tie, rec.reason))
    return parts


def why_text(rec: RecommendationView, texts: Texts) -> str:
    """The reasons of a recommendation as one text."""
    return " ".join(why_points(rec, texts))


@dataclass(frozen=True)
class OptionRow:
    """A row of the comparison table (docs/design/brief.md, section 3.7), its figures as shown."""

    title: str
    short: str | None
    chance: str
    percent: int
    delay: str
    cost: str
    chosen: bool = False
    base: bool = False
    diff: str = ""
    note: str = ""  # a recommendation stored before v2.0.2: racing set this option aside early
    worse: bool = False  # worse than no change: a lower chance, or as likely and later (WP12)


LONG_OPTION = 60  # characters of an option's name before the rest folds behind "More"


def short_name(title: str) -> str | None:
    """An option's name cut at a word near the limit, or None if it fits."""
    if len(title) <= LONG_OPTION:
        return None
    return title[:LONG_OPTION].rsplit(" ", 1)[0].rstrip(",:(") + "…"


def head_and_tail(title: str) -> str:
    """An option's name cut in the middle: its start and its end, which tell apart two options
    whose starts are the same (the WP12 test: two substitutions cut to the same words)."""
    half = LONG_OPTION // 2
    head = title[:half].rsplit(" ", 1)[0].rstrip(",:(")
    tail = title[-half:].split(" ", 1)[-1]
    return f"{head} … {tail}"


def distinct_shorts(rows: list[OptionRow]) -> list[OptionRow]:
    """The rows with every short name that appears twice replaced by its head and tail."""
    seen = [row.short for row in rows if row.short is not None]
    return [
        dataclasses.replace(row, short=head_and_tail(row.title))
        if row.short is not None and seen.count(row.short) > 1
        else row
        for row in rows
    ]


def option_rows(rec: RecommendationView, texts: Texts) -> list[OptionRow]:
    """The options compared: the recommended one first, then the alternatives in the order of the
    recommendation (spec section 11.5, item 6), and "no change" as the reference point, last."""
    after = rec.with_action
    if not rec.alternatives:
        return []
    base = next((a for a in rec.alternatives if a.label == "NOOP"), None)
    reference = rec.without.p_on_time if rec.without is not None else None
    if base is not None:
        reference = base.p_on_time

    def diff(p: float) -> str:
        if reference is None:
            return ""
        change = _whole_percent(p) - _whole_percent(reference)
        if change == 0:
            return ""
        sign = "+" if change > 0 else "\u2212"
        return texts("rec.points", sign=sign, n=abs(change))

    def worse(p: float, delay: float) -> bool:
        """Worse than no change as the table shows it: a lower chance, or the same chance and a
        longer expected delay."""
        if base is None:
            return False
        lower = _whole_percent(p) - _whole_percent(base.p_on_time)
        return lower < 0 or (lower == 0 and half_up(delay, 1) > half_up(base.tardiness, 1))

    rows = []
    if after is not None and rec.acts:
        rows.append(
            OptionRow(
                rec.title,
                short_name(rec.title),
                texts.pct(after.p_on_time),
                _whole_percent(after.p_on_time),
                texts.decimal(after.tardiness),
                texts.cost_short(after.expected_cost),
                chosen=True,
                diff=diff(after.p_on_time),
                worse=worse(after.p_on_time, after.tardiness),
            )
        )
    others = [a for a in rec.alternatives if a.label != "NOOP"]
    for alt in others:
        rows.append(
            OptionRow(
                alt.title,
                short_name(alt.title),
                texts.pct(alt.p_on_time),
                _whole_percent(alt.p_on_time),
                texts.decimal(alt.tardiness),
                texts.cost_short(alt.expected_cost),
                diff=diff(alt.p_on_time),
                note=texts("rec.dropped") if alt.dropped and not rec.compared else "",
                worse=worse(alt.p_on_time, alt.tardiness),
            )
        )
    if base is not None:
        rows.append(
            OptionRow(
                texts("rec.alt_noop"),
                None,
                texts.pct(base.p_on_time),
                _whole_percent(base.p_on_time),
                texts.decimal(base.tardiness),
                texts.cost_short(base.expected_cost),
                base=True,
            )
        )
    return distinct_shorts(rows)


def _whole_percent(p: float) -> int:
    return int(half_up(100 * p))


def approve_label(kind: str) -> str:
    """The key of the approve button: it names what is approved (brief, section 1.7); an action of
    several operations reads as a change."""
    if "_reseq" in kind or kind.startswith("proposal"):
        return "rec.approve"
    for prefix, name in (
        ("subst", "subst"),
        ("ot", "overtime"),
        ("descope", "descope"),
        ("reseq", "reseq"),
        ("shift", "shift"),
    ):
        if kind.startswith(prefix):
            return f"rec.approve.{name}"
    return "rec.approve"


@dataclass(frozen=True)
class Chip:
    """An effect of a recommendation: its label, the change in words and whether it is good."""

    label: str
    text: str
    tone: str = "neutral"  # good, bad, neutral


def finish_of(outcome: OutcomeView) -> date | None:
    """The finish date a card shows: the most likely finish, the overview's (v2.2.0, B4 of the
    WP12 test), or the expected finish of a recommendation stored before it."""
    return outcome.likely_finish or outcome.expected_finish


def finish_label(outcome: OutcomeView, texts: Texts) -> str:
    return texts("chip.likely" if outcome.likely_finish is not None else "chip.finish")


def gain_chip(
    rec: RecommendationView, before: OutcomeView, after: OutcomeView, texts: Texts
) -> Chip:
    """What the action improves when the chance shown does not move ("0 % → 0 %", the WP12
    test): the component that decided (spec section 6) in words, with its figures where it has
    them; the expected delay when the chance itself decided within its rounding."""
    reason = rec.reason
    if reason in ("on_time", "tardiness", "only_candidate"):
        text = texts(
            "chip.gain.tardiness",
            before=texts.decimal(before.tardiness),
            after=texts.decimal(after.tardiness),
        )
    elif reason == "budget":
        text = texts(
            "chip.gain.budget",
            before=texts.share(before.overrun),
            after=texts.share(after.overrun),
        )
    else:
        text = rec.reason_text
    return Chip(texts("chip.gain"), text, "good")


def impact_chips(rec: RecommendationView, texts: Texts) -> list[Chip]:
    """The effect of the action against no change (spec section 11.5): the chance of meeting
    the deadline, the expected finish date, the expected cost and the tasks whose dates move."""
    before, after = rec.without, rec.with_action
    chips: list[Chip] = []
    if before is None:
        return chips
    if after is None or not rec.acts:
        chips.append(Chip(texts("chip.chance"), texts.pct(before.p_on_time)))
        if finish_of(before) is not None:
            chips.append(Chip(finish_label(before, texts), texts.date(finish_of(before))))
        return chips
    delta = after.p_on_time - before.p_on_time
    tone = "good" if delta > 0.005 else "bad" if delta < -0.005 else "neutral"
    chips.append(
        Chip(
            texts("chip.chance"),
            texts(
                "chip.from_to", before=texts.pct(before.p_on_time), after=texts.pct(after.p_on_time)
            ),
            tone,
        )
    )
    if texts.pct(after.p_on_time) == texts.pct(before.p_on_time):
        chips.append(gain_chip(rec, before, after, texts))
    first, then = finish_of(before), finish_of(after)
    if first is not None and then is not None:
        moved = (then - first).days
        tone = "good" if moved < 0 else "bad" if moved > 0 else "neutral"
        text = texts("chip.from_to", before=texts.date(first), after=texts.date(then))
        chips.append(Chip(finish_label(after, texts), text, tone))
    cost = after.expected_cost - before.expected_cost
    tone = "bad" if cost > 0.5 else "good" if cost < -0.5 else "neutral"
    value = texts.cost_change(cost, rec.budget)
    if rec.budget:  # as the overview shows the expected cost (B3 of the WP12 test)
        change = texts.cost_change(cost, None)
        before_share = texts.share(before.expected_cost / rec.budget)
        after_share = texts.share(after.expected_cost / rec.budget)
        value = texts("chip.cost_shares", before=before_share, after=after_share, change=change)
    chips.append(Chip(texts("chip.cost"), value, tone))
    moved_tasks = len(rec.changes)
    chips.append(
        Chip(texts("chip.moved"), texts.plural("chip.tasks", moved_tasks) if moved_tasks else "–")
    )
    return chips


def effect_rows(rec: RecommendationView, texts: Texts) -> list[Chip]:
    """The rows of "what changes" on a recommendation: the chips without the chance, shown large
    above them, and the expected delay, which often is what the action gains (QA-05: "3 % → 3 %"
    alone gives no reason to act)."""
    rows = impact_chips(rec, texts)[1:]
    before, after = rec.without, rec.with_action
    if rec.acts and before is not None and after is not None:
        change = after.tardiness - before.tardiness
        tone = "good" if change <= -0.05 else "bad" if change >= 0.05 else "neutral"
        text = texts(
            "chip.from_to",
            before=texts.decimal(before.tardiness),
            after=texts.decimal(after.tardiness),
        )
        rows.insert(min(1, len(rows)), Chip(texts("chip.delay"), text, tone))
    return rows


@dataclass(frozen=True)
class Gap:
    """How far a forecast finish lies from the deadline, in words, with its status."""

    text: str
    tone: str  # good, warn, bad, neutral
    icon: str


def finish_gap(
    finish: date, deadline: date | None, calendar: WorkCalendar, texts: Texts, worst: bool = False
) -> Gap | None:
    """The sub-line of a finish date's tile: working days before or after the deadline; the bad
    case's lateness counts as a problem, the most likely finish's as a warning."""
    if deadline is None:
        return None
    days = calendar.last(finish) - calendar.last(deadline)
    if days == 0:
        return Gap(texts("overview.gap_on"), "neutral", "minus")
    span = texts.plural("overview.days", abs(days))
    if days < 0:
        return Gap(texts("overview.gap_before", days=span), "good", "check")
    text = texts("overview.gap_after", days=span)
    return Gap(text, "bad", "cross-circle") if worst else Gap(text, "warn", "alert")


@dataclass(frozen=True)
class Threat:
    """A task that threatens the deadline: its sentence (spec sections 11.4, 11.7) and strength."""

    task: str
    text: str
    percent: int


def threats_of(forecast: ForecastView, texts: Texts) -> list[Threat]:
    """The tasks shown as threats: the forecast's ranking, in words (spec section 11.4)."""
    return [
        Threat(d.task, texts("overview.driver", task=d.name), round(100 * d.sensitivity))
        for d in forecast.drivers or ()
    ]


def settings_version(definition: ProjectDefinition) -> str:
    """A fingerprint of what the settings page was opened on, to notice a save from elsewhere."""
    return hashlib.sha256(definition.model_dump_json().encode()).hexdigest()[:16]


def cost_lookup(definition: ProjectDefinition) -> Callable[[str], float]:
    """The daily cost of a role, as the settings page shows it."""
    costs = {role_key(c.role): c.daily_cost for c in definition.roles}
    return lambda role: costs.get(role_key(role), 1.0)


def over_budget(forecast: ForecastView) -> bool:
    """Whether the expected total cost is above the budget (QA-10: approvals add up, and the
    status badge speaks of the deadline only)."""
    expected, budget = forecast.expected_cost, forecast.budget
    return expected is not None and budget is not None and expected > budget


def level_of(summary: ForecastSummary | None) -> str:
    """The status word of a forecast."""
    return chance_level(None if summary is None else summary.forecast.p_on_time)


def checked_key(rec: RecommendationView) -> str:
    """What the overview says when Sentinel keeps the plan (QA-04): "no change is needed" only
    while the deadline is on track; otherwise no option was clearly better, another message."""
    chance = None if rec.without is None else rec.without.p_on_time
    on_track = rec.reason == "needs_met" or chance is None or chance_level(chance) == "good"
    if on_track:
        return "overview.checked"
    return "overview.checked_none_helps" if rec.options > 1 else "overview.checked_no_better"


def stalled(view: ProjectView, checkin: CheckIn) -> bool:
    """Whether a check-in moves the date forward with no progress on any task in progress (the
    WP12 test, B9: a report of a message alone silently meant a week without progress), so the
    page asks first."""
    running = {task.key: task.percent or 0.0 for task in view.tasks if task.state == "in_progress"}
    if not running:
        return False
    last = view.checkins[-1].date if view.checkins else view.definition.start
    if checkin.date <= last:
        return False
    for report in checkin.tasks:
        if report.task not in running:
            continue
        if report.status == "done":
            return False
        if report.status == "in_progress" and (report.percent or 0.0) > running[report.task] + 0.5:
            return False
    return True


def needs_date_confirmation(day: date, confirmed: bool, today: date | None = None) -> bool:
    """Whether a check-in's date is too far ahead to save without asking (QA-06): the log is
    append-only and check-ins follow in date order, so a mistyped year would block every later
    check-in. A check-in reports what is true at the end of its day, so a date ahead of today is
    unusual, and more than a week ahead most likely a typing mistake."""
    return not confirmed and (day - (today or date.today())).days > FUTURE_CHECKIN_DAYS


def split_pending(
    pending: list[RecommendationView],
) -> tuple[list[RecommendationView], list[RecommendationView]]:
    """The decisions in the first layer and those behind "other proposals": what can wait folds
    unless nothing else is waiting (docs/design/brief.md, section 3.6)."""
    urgent = [r for r in pending if not r.can_wait]
    waiting = [r for r in pending if r.can_wait]
    if not urgent and waiting:
        return waiting[:1], waiting[1:]
    return urgent, waiting


def toast_text(kind: str, summary: ForecastSummary | None, texts: Texts) -> str | None:
    """The toast of a saved check-in or an approval once the new forecast is known."""
    if summary is None or summary.forecast.p_on_time is None:
        return None
    now = texts.pct(summary.forecast.p_on_time)
    if kind == "checkin_saved" and summary.previous_p is not None:
        return texts("flash.checkin_chance", before=texts.pct(summary.previous_p), after=now)
    if kind == "approved":
        return texts("flash.approved_chance", after=now)
    return None


@dataclass
class HistoryItem:
    """An entry of the project's history."""

    kind: str  # checkin, recommendation, decision, change
    when: str
    title: str
    day: date
    icon: str = "swap"
    lines: list[str] = field(default_factory=list)
    href: str | None = None
    status: str | None = None
    chip: str | None = None  # the chance before and after, when it is known with the entry
    seq: int | None = None  # a check-in's event: its chip arrives with the chart of the chance
    auto: bool = False
    outcome: str | None = None  # a check-in's "no change", with the link to its analysis
    outcome_href: str | None = None


@dataclass(frozen=True)
class WeekGroup:
    """The entries of one week in the history (docs/design/brief.md, section 3.14)."""

    title: str
    items: list[HistoryItem]


def week_groups(
    items: list[HistoryItem], texts: Texts, today: date | None = None
) -> list[WeekGroup]:
    """Entries under their week's header, in their given order: "This week" or "6–10 Nov"."""
    this_week = (today or date.today()) - timedelta(days=(today or date.today()).weekday())
    groups: list[WeekGroup] = []
    current = None
    for item in items:
        monday = item.day - timedelta(days=item.day.weekday())
        if monday != current:
            title = texts("history.week.this") if monday == this_week else texts.week_range(monday)
            groups.append(WeekGroup(title, []))
            current = monday
        groups[-1].items.append(item)
    return groups


def chance_chip(rec: RecommendationView | None, texts: Texts) -> str | None:
    """A recommendation's effect on the chance as the history shows it."""
    if rec is None or not rec.acts or rec.without is None or rec.with_action is None:
        return None
    return texts(
        "history.chip",
        before=texts.pct(rec.without.p_on_time),
        after=texts.pct(rec.with_action.p_on_time),
    )


def definition_changes(old: ProjectDefinition, new: ProjectDefinition, texts: Texts) -> list[str]:
    """What a change of the definition did, in words (WP12): the autonomy with its old and new
    level, and the corrections of tasks (spec section 11.2, v2.2.0); empty for other changes."""
    parts = []
    if old.settings.autonomy != new.settings.autonomy:
        parts.append(
            texts(
                "history.autonomy",
                before=texts(f"autonomy.{old.settings.autonomy}"),
                after=texts(f"autonomy.{new.settings.autonomy}"),
            )
        )
    earlier = {t.key: t for t in old.tasks}
    for task in new.tasks:
        was = earlier.get(task.key)
        if was is None:
            continue
        changes = []
        if was.duration != task.duration:
            changes.append(texts("history.fix.days", before=was.duration, after=task.duration))
        if was.crew != task.crew:
            changes.append(texts("history.fix.crew"))
        if was.predecessors != task.predecessors:
            changes.append(texts("history.fix.after"))
        if was.optional != task.optional:
            changes.append(
                texts("history.fix.optional" if task.optional else "history.fix.required")
            )
        if changes:
            parts.append(texts("history.fix", task=task.name, changes=", ".join(changes)))
    return parts


def history(ui: Ui, request: Request, project_id: str, view: ProjectView) -> list[HistoryItem]:
    """The project's history from its event log, newest first (spec section 11.5)."""
    texts = ui.texts(request)
    services = ui.services
    session = ui.session(request)
    state = services.state(session, project_id)
    project = state.project
    names = {key: node.name for key, node in project.nodes().items()}
    people = {p.key: p.name for p in project.definition.team}
    titles = {r.seq: r for r in view.recommendations}
    items: list[HistoryItem] = []
    previous = ""
    current: ProjectDefinition | None = None  # the definition as the log has it so far
    before: ProjectDefinition | None = None  # that before a run of edits
    for row in services.store.events(session, project_id):
        stamp = texts.moment(row.created)
        day = row.created.astimezone().date()
        event = parse(row)
        if isinstance(event, Created):
            current = event.definition
        elif isinstance(event, CheckinDone) and current is not None:
            for revision in event.effects.revisions:  # estimates revised at a check-in (11.3)
                tasks = tuple(
                    t.model_copy(update={"duration": revision.duration})
                    if t.key == revision.task
                    else t
                    for t in current.tasks
                )
                current = current.model_copy(update={"tasks": tasks})
        if isinstance(event, DefinitionChanged):
            if previous != "definition":
                before = current
            current = event.definition
            # Consecutive edits (autosave) are one change, said as what changed (WP12).
            parts = [] if before is None else definition_changes(before, current, texts)
            text = "; ".join(parts) if parts else texts("history.definition")
            item = HistoryItem("change", stamp, text, day, "sliders")
            if previous == "definition" and items:
                items[-1] = item
            else:
                items.append(item)
            previous = row.type
            continue
        previous = row.type
        match event:
            case CheckinDone():
                item = checkin_item(event.checkin, project, names, people, texts)
                item.seq = row.seq
                items.append(item)
            case Recommended():
                rec = titles.get(row.seq)
                if rec is None:
                    continue
                if rec.status == "none" and items and items[-1].kind == "checkin":
                    # QA-20: "no change" after a check-in is part of it, not an entry of its own.
                    items[-1].outcome = texts("history.no_change")
                    items[-1].outcome_href = f"/projects/{project_id}/recommendations/{rec.seq}"
                    continue
                title = rec.title
                status = rec.status_text
                auto = rec.status in ("auto", "undone")
                items.append(
                    HistoryItem(
                        "recommendation",
                        texts.date(rec.as_of),
                        texts("history.recommendation", title=title),
                        rec.as_of,
                        "swap" if auto else "clock",
                        [texts("history.status", status=status)],
                        f"/projects/{project_id}/recommendations/{rec.seq}",
                        rec.status,
                        chip=chance_chip(rec, texts),
                        auto=auto,
                    )
                )
            case Decided():
                rec = titles.get(event.recommendation)
                title = rec.title if rec else "?"
                key = (
                    "history.discarded"
                    if event.verdict == "approve" and event.discarded is not None
                    else f"history.verdict.{event.verdict}"
                )
                when = texts.date(rec.as_of) if rec else stamp
                icons = {"approve": "check", "reject": "x", "later": "clock-dashed"}
                items.append(
                    HistoryItem(
                        "decision",
                        when,
                        texts(key, title=title),
                        rec.as_of if rec else day,
                        icons[event.verdict],
                        href=f"/projects/{project_id}/recommendations/{event.recommendation}",
                        chip=chance_chip(rec, texts) if event.verdict == "approve" else None,
                    )
                )
            case Undone():
                rec = titles.get(event.recommendation)
                when = texts.date(rec.as_of) if rec else stamp
                title = rec.title if rec else "?"
                items.append(
                    HistoryItem(
                        "change",
                        when,
                        texts("history.undone", title=title),
                        rec.as_of if rec else day,
                        "arrow-left",
                    )
                )
            case BaselineSet():
                finish = project.calendar.finish_date(event.baseline.makespan)
                items.append(
                    HistoryItem(
                        "change", stamp, texts("history.plan", date=texts.date(finish)), day, "flag"
                    )
                )
            case _:
                if row.type == "created":
                    items.append(
                        HistoryItem("change", stamp, texts("history.created"), day, "plus")
                    )
                elif row.type == "explanation":
                    items.append(
                        HistoryItem(
                            "recommendation", stamp, texts("history.explanation"), day, "document"
                        )
                    )
    items.reverse()
    return items


def chance_values(
    view: ProjectView, steps: list[ChanceStep], current: float | None
) -> list[tuple[date, float]]:
    """The points of the chance over time: the plan, every check-in, and now if it differs."""
    values: list[tuple[date, float]] = []
    if steps:
        first = steps[0].before
        if first is not None:
            values.append((view.definition.start, first))
        values += [(step.date, step.after) for step in steps]
        if current is not None and current != steps[-1].after:
            values.append((view.as_of, current))
    return values


def chance_chips(steps: list[ChanceStep], texts: Texts) -> dict[int, str]:
    """Each check-in's change of the chance, by its event."""
    return {
        step.seq: texts("history.chip", before=texts.pct(step.before), after=texts.pct(step.after))
        for step in steps
        if step.before is not None
    }


def checkin_item(
    checkin: CheckIn,
    project: LiveProject,
    names: dict[str, str],
    people: dict[str, str],
    texts: Texts,
) -> HistoryItem:
    lines = []
    for report in checkin.tasks:
        name = names.get(report.task, report.task)
        if report.status == "done":
            finish = texts.date(report.finish) if report.finish else "?"
            lines.append(texts("history.task_done", task=name, date=finish))
        elif report.status == "in_progress":
            lines.append(
                texts("history.task_progress", task=name, percent=round(report.percent or 0))
            )
    for absence in checkin.absences:
        who = people.get(absence.person, absence.person)
        if absence.return_date is not None:
            lines.append(
                texts(
                    "history.away_back",
                    person=who,
                    first=texts.date(absence.first_day),
                    back=texts.date(absence.return_date),
                )
            )
        else:
            lines.append(texts("history.away", person=who, first=texts.date(absence.first_day)))
    for increase in checkin.increases:
        name = names.get(increase.task, increase.task)
        if increase.extra_days is not None:
            lines.append(
                texts("history.grows_days", task=name, days=texts.decimal(increase.extra_days))
            )
        else:
            percent = round(100 * ((increase.factor or 1.0) - 1))
            lines.append(texts("history.grows_factor", task=name, percent=percent))
    for added in checkin.new_tasks:
        lines.append(texts("history.new_task", task=added.name, days=added.duration))
    if not lines:
        lines.append(texts("history.nothing"))
    return HistoryItem(
        "checkin",
        texts.date(checkin.date),
        texts("history.checkin", date=texts.date(checkin.date)),
        checkin.date,
        "document",
        lines,
    )


def shown_tasks(view: ProjectView) -> tuple[list[TaskView], list[TaskView]]:
    """The tasks a check-in asks about: those in progress and the next ones (unstarted tasks
    whose predecessors are done or in progress, or planned within NEXT_DAYS working days); the
    other unstarted tasks are offered behind "show all"."""
    state = {task.key: task.state for task in view.tasks}
    first: list[TaskView] = []
    rest: list[TaskView] = []
    for task in view.tasks:
        if task.state in ("done", "removed"):
            continue
        if task.state in ("in_progress", "paused"):
            first.append(task)
            continue
        ready = all(state.get(p) in ("done", "in_progress", "paused") for p in task.predecessors)
        soon = (
            task.planned_start is not None
            and (task.planned_start - view.as_of).days <= NEXT_DAYS * 7 // 5
        )
        (first if ready or soon else rest).append(task)
    return first, rest


def router(ui: Ui) -> APIRouter:
    routes = APIRouter()
    services = ui.services

    def live(request: Request, project_id: str) -> ProjectView:
        return services.live(ui.session(request), project_id, ui.language(request))

    def chart_html(
        request: Request, project: LiveProject, forecast: ForecastView | None = None
    ) -> str:
        """The chart of a project; with the forecast also its window and threats."""
        texts = ui.texts(request)
        window = None if forecast is None else (forecast.p50, forecast.p90)
        threats = None
        if forecast is not None and forecast.late:
            threats = {threat.task: threat.text for threat in threats_of(forecast, texts)}
        model = live_gantt(project, texts, date.today(), window, threats)
        return ui.render(request, "_gantt.html", {"g": model})

    def forecast_values(
        request: Request,
        view: ProjectView,
        project: LiveProject,
        summary: ForecastSummary | None,
    ) -> dict[str, Any]:
        """What the overview and the report show of a forecast."""
        texts = ui.texts(request)
        calendar = project.calendar
        f = None if summary is None else summary.forecast
        values: dict[str, Any] = {}
        if f is not None:
            dated = [
                (view.as_of, texts("strip.today")),
                (f.p50, texts("strip.likely", date=texts.day_month(f.p50))),
            ]
            if f.deadline is not None:
                dated.append(
                    (f.deadline, texts("strip.deadline", date=texts.day_month(f.deadline)))
                )
            dated.append((f.p90, texts("strip.bad", date=texts.day_month(f.p90))))
            values = {
                "strip": forecast_strip(view.as_of, f.p50, f.p90, f.deadline, calendar),
                "strip_labels": [label for _, label in sorted(dated, key=lambda item: item[0])],
                "likely_gap": finish_gap(f.p50, f.deadline, calendar, texts),
                "bad_gap": finish_gap(f.p90, f.deadline, calendar, texts, worst=True),
                "threats": threats_of(f, texts) if f.late else [],
                "over_budget": over_budget(f),
                "chart": chart_html(request, project, f),
            }
        checkins = view.checkins
        since = (
            texts("trend.since_checkin", date=texts.date(checkins[-2].date))
            if len(checkins) > 1
            else texts("trend.since_plan")
        )
        return {
            "summary": summary,
            "view": view,
            "failed": None,
            "level": level_of(summary),
            "delta": trend(summary),
            "since": since,
            **values,
        }

    @routes.get("/projects/{project_id}")
    def overview(request: Request, project_id: str) -> Response:
        session = ui.session(request)
        row = services.store.project(session, project_id)
        if row is None:
            raise AppError("project_not_found", "not_found")
        if row.kind == "simulator":
            from sentinel.app.ui.sim import simulation_page

            return simulation_page(ui, request, project_id)
        view = live(request, project_id)
        if not view.has_plan:
            step = "tasks" if view.definition.team else "team"
            return ui.redirect(request, f"/projects/{project_id}/setup/{step}")
        state = services.state(session, project_id)
        flash = request.query_params.get("flash")
        running = services.store.project_jobs(session, project_id)
        job = next((j for j in running if j.kind == "recommend"), None)
        open_recs = [r for r in view.recommendations if r.status in ("open", "later")]
        urgent, waiting = split_pending(open_recs)
        auto = checked = None
        latest = view.recommendations[-1] if view.recommendations else None
        if latest is not None and latest.status == "auto":
            auto = latest
        if latest is not None and latest.status == "none" and view.checkins:
            # After a check-in, said only when the chance is low and no option helps (WP12 test).
            low = checked_key(latest) != "overview.checked"
            checked = latest if low or latest.date > view.checkins[-1].date else None
        away = [p for p in view.people if p.absent]
        late = [t for t in view.tasks if t.late]
        return ui.page(
            request,
            "overview.html",
            title=view.name,
            nav="projects",
            view=view,
            tab="overview",
            pending=open_recs,
            urgent=urgent,
            waiting=waiting,
            flash_key=flash if flash in FLASHES_WITH_CHANCE else None,
            auto=auto,
            checked=checked,
            away=away,
            late=late,
            job=None if job is None else services.job(session, job.id, ui.language(request)),
            chart=chart_html(request, state.project),
            chips=impact_chips,
            checked_message="" if checked is None else checked_key(checked),
        )

    def wait_for_threats(request: Request, project_id: str) -> str | None:
        """The id of the job to wait for while the list of a project's threats or the causes of
        the latest move of its chance are calculated (spec section 11.4), None if they are known
        (or were just calculated, with inline jobs)."""
        session, language = ui.session(request), ui.language(request)
        forecast = services.forecast_now(session, project_id)
        if forecast is None or (forecast.drivers is not None and not forecast.causes_pending):
            return None
        job = services.threats_job(session, project_id, language)
        return None if job.status == "done" else job.id

    @routes.get("/projects/{project_id}/forecast")
    def forecast(request: Request, project_id: str) -> Response:
        """The forecast block of the overview (loaded after the page; spec section 11.4)."""
        view = live(request, project_id)
        try:
            threats_job = wait_for_threats(request, project_id)
            summary = services.forecast_summary(
                ui.session(request), project_id, ui.language(request)
            )
        except AppError as exc:
            texts = ui.texts(request)
            return ui.page(
                request,
                "_forecast.html",
                summary=None,
                view=view,
                failed=texts.error(exc),
                level="neutral",
                delta=None,
            )
        state = services.state(ui.session(request), project_id)
        toast = request.query_params.get("toast", "")
        return ui.page(
            request,
            "_forecast.html",
            **forecast_values(request, view, state.project, summary),
            threats_job=threats_job,
            nav_level="decision" if state.open is not None else level_of(summary),
            toast=toast_text(toast, summary, ui.texts(request)),
        )

    @routes.get("/projects/{project_id}/threats")
    def threats(request: Request, project_id: str) -> Response:
        """The list of what threatens the deadline, for the overview to poll while its job runs
        (spec section 11.4): the list once known, or the job's failure, with a way to try again."""
        session, language = ui.session(request), ui.language(request)
        waited = request.query_params.get("job")
        f = services.forecast_now(session, project_id)
        if f is not None and f.drivers is None and waited:
            job = services.job(session, waited, language)
            if job.status == "failed":
                return ui.page(request, "_threats.html", id=project_id, failed=True)
        threats_job = wait_for_threats(request, project_id)
        f = services.forecast_now(session, project_id)
        found = [] if f is None else threats_of(f, ui.texts(request))
        chart = None
        if f is not None and found:  # the chart flags them; else it stays, scrolled as it is
            chart = chart_html(request, services.state(session, project_id).project, f)
        return ui.page(
            request,
            "_threats.html",
            id=project_id,
            f=f,
            threats=found,
            threats_job=threats_job,
            polled=True,
            chart=chart,
        )

    @routes.post("/projects/{project_id}/ask")
    def ask(request: Request, project_id: str) -> Response:
        job = services.recommend(ui.session(request), project_id, ui.language(request))
        return job_progress(ui, request, job, "job.recommend")

    # ---- check-in

    def checkin_values(request: Request, project_id: str, form: Form | None) -> dict[str, Any]:
        view = live(request, project_id)
        first, rest = shown_tasks(view)
        roles = team_roles(view.definition.team)
        today = date.today()
        last = view.checkins[-1].date if view.checkins else None
        default = max(today, last or today, view.definition.start)

        def fv(name: str, fallback: object = "") -> object:
            """The value the manager entered (after a refused submit), else `fallback`."""
            return form.get(name, str(fallback)) if form is not None else fallback

        # What was confirmed stays confirmed while the report is not saved (the WP12 test).
        typed = None if form is None else form.get("date")
        confirmed_date = (
            typed
            if form is not None
            and (form.flag("confirm_date") or form.get("confirmed_date") == typed)
            else None
        )

        def fl(name: str) -> list[str]:
            return form.getlist(name) if form is not None else []

        def crew_text(task: TaskView) -> str:
            return ", ".join(f"{count} × {role}" for role, count in task.crew.items() if count)

        def role_needed(task: TaskView, role: str) -> bool:
            from sentinel.app.live import role_key

            return any(role_key(r) == role_key(role) and n > 0 for r, n in task.crew.items())

        return {
            "fv": fv,
            "fl": fl,
            "crew_text": crew_text,
            "role_needed": role_needed,
            "title": ui.texts(request)("checkin.title"),
            "nav": "projects",
            "view": view,
            "tab": "checkin",
            "first": first,
            "rest": rest,
            "roles": roles,
            "people": [p for p in view.people if not p.temporary],
            "running": [t for t in view.tasks if t.state in ("in_progress", "paused")],
            "startable": [t for t in (*first, *rest) if t.state not in ("in_progress", "paused")],
            "open_tasks": [t for t in view.tasks if t.state not in ("done", "removed")],
            "default_date": default,
            "report_date": fv("date", default),  # a task's finish date follows it (B16)
            "last": last,
            "form": form,
            "errors": {},
            "issues": [],
            "confirm_date": None,
            "confirmed_date": confirmed_date,
            "confirm_progress": None,
            "no_progress": form is not None and form.flag("no_progress"),
            "message_kept": None if form is None else kept_message(ui, request, project_id, form),
        }

    @routes.get("/projects/{project_id}/checkin")
    def checkin_page(request: Request, project_id: str) -> Response:
        values = checkin_values(request, project_id, None)
        if values["view"].finished:
            return ui.redirect(request, f"/projects/{project_id}")
        return ui.page(request, "checkin.html", **values)

    @routes.post("/projects/{project_id}/checkin")
    async def checkin_save(request: Request, project_id: str) -> Response:
        form = await Form.read(request)
        view = live(request, project_id)
        current = {
            t.key: (t.state if t.state != "paused" else "in_progress", t.percent)
            for t in view.tasks
        }
        read = read_checkin(form, current)
        texts = ui.texts(request)
        if read.checkin is None:
            values = checkin_values(request, project_id, form)
            values["errors"] = {e.name: texts(e.key, **e.values) for e in read.errors}
            return checkin_form(request, values, 422)
        confirmed = form.flag("confirm_date") or form.get("confirmed_date") == str(
            read.checkin.date
        )
        if needs_date_confirmation(read.checkin.date, confirmed):
            values = checkin_values(request, project_id, form)
            values["confirm_date"] = read.checkin.date
            return checkin_form(request, values, 422)
        if not form.flag("no_progress") and stalled(view, read.checkin):
            # The WP12 test (B9): a report of a message alone meant no progress, silently.
            values = checkin_values(request, project_id, form)
            last = view.checkins[-1].date if view.checkins else view.definition.start
            values["confirm_progress"] = last
            return checkin_form(request, values, 422)
        try:
            result = services.checkin(
                ui.session(request), project_id, read.checkin, ui.language(request)
            )
        except AppError as exc:
            values = checkin_values(request, project_id, form)
            values["issues"] = texts.issues(exc)
            return checkin_form(request, values, 422)
        del result
        return ui.redirect(request, f"/projects/{project_id}", flash="checkin_saved")

    def checkin_form(request: Request, values: dict[str, Any], status: int) -> Response:
        if is_htmx(request):
            return ui.page(request, "_checkin_form.html", status, **values)
        return ui.page(request, "checkin.html", status, **values)

    @routes.post("/projects/{project_id}/checkin/message")
    async def read_message(request: Request, project_id: str) -> Response:
        form = await Form.read(request)
        when = form.get("date")
        try:
            day = date.fromisoformat(when)
        except ValueError:
            day = date.today()
        job = services.read_message(
            ui.session(request), project_id, form.get("message"), day, ui.language(request)
        )
        return job_progress(ui, request, job, "job.message", project=project_id, note="job.slow_ai")

    # ---- recommendations

    def recommendation(
        request: Request, project_id: str, seq: int
    ) -> tuple[ProjectView, RecommendationView]:
        view = live(request, project_id)
        rec = next((r for r in view.recommendations if r.seq == seq), None)
        if rec is None:
            raise AppError("recommendation_not_found", "not_found")
        return view, rec

    @routes.get("/projects/{project_id}/recommendations/{seq}")
    def recommendation_page(request: Request, project_id: str, seq: int) -> Response:
        view, rec = recommendation(request, project_id, seq)
        texts = ui.texts(request)
        return ui.page(
            request,
            "recommendation.html",
            title=texts("rec.title"),
            nav="projects",
            view=view,
            tab="overview",
            rec=rec,
            chips=impact_chips(rec, texts),
            rows=effect_rows(rec, texts),
            why=why_points(rec, texts),
            options=option_rows(rec, texts),
            approve_key=approve_label(rec.kind),
            chance_change=(
                _whole_percent(rec.with_action.p_on_time) - _whole_percent(rec.without.p_on_time)
                if rec.with_action is not None and rec.without is not None
                else 0
            ),
        )

    @routes.post("/projects/{project_id}/recommendations/{seq}/decision")
    async def decide(request: Request, project_id: str, seq: int) -> Response:
        form = await Form.read(request)
        verdict = form.get("verdict")
        if verdict not in ("approve", "reject", "later"):
            raise AppError("field_invalid", field="verdict", detail=verdict)
        after = services.decide(ui.session(request), project_id, seq, verdict, ui.language(request))  # type: ignore[arg-type]
        entry = next((r for r in after.recommendations if r.seq == seq), None)
        flash = {"approve": "approved", "reject": "rejected", "later": "later"}[verdict]
        if entry is not None and entry.status == "discarded":
            flash = "discarded"
        return ui.redirect(request, f"/projects/{project_id}", flash=flash)

    @routes.post("/projects/{project_id}/recommendations/{seq}/undo")
    def undo(request: Request, project_id: str, seq: int) -> Response:
        services.undo(ui.session(request), project_id, seq, ui.language(request))
        return ui.redirect(request, f"/projects/{project_id}", flash="undone")

    @routes.post("/projects/{project_id}/recommendations/{seq}/explain")
    def explain(request: Request, project_id: str, seq: int) -> Response:
        job = services.explain(ui.session(request), project_id, seq, ui.language(request))
        return job_progress(
            ui,
            request,
            job,
            "job.explain",
            next=f"/projects/{project_id}/recommendations/{seq}",
            note="job.slow_ai",
        )

    # ---- history

    @routes.get("/projects/{project_id}/history")
    def history_page(request: Request, project_id: str) -> Response:
        view = live(request, project_id)
        show = request.query_params.get("show", "all")
        show = show if show in HISTORY_FILTERS else "all"
        items = history(ui, request, project_id, view)
        kinds = {
            "checkins": ("checkin",),
            "recommendations": ("recommendation", "decision"),
            "changes": ("change",),
        }
        if show != "all":
            items = [i for i in items if i.kind in kinds[show]]
        texts = ui.texts(request)
        return ui.page(
            request,
            "history.html",
            title=texts("history.title"),
            nav="projects",
            view=view,
            tab="history",
            shown=week_groups(items[:HISTORY_SHOWN], texts),
            older=week_groups(items[HISTORY_SHOWN:], texts),
            older_count=len(items[HISTORY_SHOWN:]),
            show=show,
            filters=HISTORY_FILTERS,
        )

    @routes.get("/projects/{project_id}/history/chance")
    def history_chance(request: Request, project_id: str) -> Response:
        """The chart of the chance over time and each check-in's change (loaded after the page,
        a forecast per check-in the first time)."""
        texts = ui.texts(request)
        view = live(request, project_id)
        steps, current = services.chance_history(ui.session(request), project_id)
        return ui.page(
            request,
            "_chance_history.html",
            points=chance_points(chance_values(view, steps, current), texts),
            chips=list(chance_chips(steps, texts).items()),
        )

    # ---- settings, exports, deletion

    def settings_values(request: Request, project_id: str) -> dict[str, Any]:
        view = live(request, project_id)
        roles = team_roles(view.definition.team)
        return {
            "title": ui.texts(request)("psettings.title"),
            "nav": "projects",
            "view": view,
            "tab": "settings",
            "roles": roles,
            "cost_of": cost_lookup(view.definition),
            "settings_version": settings_version(view.definition),  # not the footer's (B23)
            "changed_elsewhere": False,
            "errors": {},
        }

    @routes.get("/projects/{project_id}/settings")
    def settings_page(request: Request, project_id: str) -> Response:
        return ui.page(request, "project_settings.html", **settings_values(request, project_id))

    @routes.post("/projects/{project_id}/settings")
    async def settings_save(request: Request, project_id: str) -> Response:
        form = await Form.read(request)
        values = settings_values(request, project_id)
        view: ProjectView = values["view"]
        read = read_settings(form, view.definition, values["roles"])
        texts = ui.texts(request)
        if read.definition is None:
            values["errors"] = {e.name: texts(e.key, **e.values) for e in read.errors}
            return ui.page(request, "project_settings.html", 422, **values)
        if form.get("seen_version", values["settings_version"]) != values["settings_version"]:
            # QA-18: saved from elsewhere since this form was opened: ask before replacing that.
            values["view"] = view.model_copy(update={"definition": read.definition})
            values["cost_of"] = cost_lookup(read.definition)
            values["changed_elsewhere"] = True
            return ui.page(request, "project_settings.html", 409, **values)
        services.update_definition(
            ui.session(request), project_id, read.definition, ui.language(request)
        )
        level = read.definition.settings.autonomy
        if level != view.definition.settings.autonomy:
            # The WP12 test: "Settings saved" alone did not say what Sentinel now does by itself.
            return ui.redirect(
                request, f"/projects/{project_id}/settings", flash=f"autonomy_{level}"
            )
        return ui.redirect(request, f"/projects/{project_id}/settings", flash="settings_saved")

    @routes.get("/projects/{project_id}/report.html")
    def report(request: Request, project_id: str) -> Response:
        """The project's report for people (QA-08): one self-contained page to read, print, save
        or send, with what the pages show. The research cockpit stays at the API (WP8)."""
        session = ui.session(request)
        row = services.store.project(session, project_id)
        if row is None:
            raise AppError("project_not_found", "not_found")
        if row.kind == "simulator":
            from sentinel.app.ui.sim import simulation_report

            return simulation_report(ui, request, project_id)
        view = live(request, project_id)
        if not view.has_plan:
            return ui.redirect(request, f"/projects/{project_id}")
        texts = ui.texts(request)
        state = services.state(session, project_id)
        language = ui.language(request)
        summary = services.forecast_summary(session, project_id, language, with_threats=True)
        values = forecast_values(request, view, state.project, summary)
        if summary is None:
            values["chart"] = chart_html(request, state.project)
            values["threats"] = []
        steps, current = services.chance_history(session, project_id)
        items = history(ui, request, project_id, view)
        chips = chance_chips(steps, texts)
        for item in items:
            item.href = item.outcome_href = None  # no links back from a page that travels
            if item.seq in chips:
                item.chip = chips[int(item.seq or 0)]
        return ui.page(
            request,
            "report.html",
            **values,
            today=date.today(),
            css=(STATIC_DIR / "sentinel.css").read_text(encoding="utf-8"),
            pending=[r for r in view.recommendations if r.status in ("open", "later")],
            chips=impact_chips,
            away=[p for p in view.people if p.absent],
            points=chance_points(chance_values(view, steps, current), texts),
            groups=week_groups(items, texts),
        )

    @routes.get("/projects/{project_id}/delete")
    def delete_page(request: Request, project_id: str) -> Response:
        row = services.store.project(ui.session(request), project_id)
        if row is None:
            raise AppError("project_not_found", "not_found")
        return ui.page(
            request,
            "delete.html",
            title=ui.texts(request)("delete.title"),
            nav="projects",
            name=row.name,
            project_id=project_id,
        )

    @routes.post("/projects/{project_id}/delete")
    def delete(request: Request, project_id: str) -> Response:
        services.delete(ui.session(request), project_id)
        return ui.redirect(request, "/", flash="deleted")

    return routes


def message_review(ui: Ui, request: Request, view: JobView) -> Response:
    """The events the AI read from a check-in message, each to confirm (spec section 10.2)."""
    from sentinel.app.llm import MessageDraft

    found = MessageDraft.model_validate(view.result or {})
    project_id = request.query_params.get("project", "")
    values = message_values(ui, request, project_id, found)
    values["clauses"] = ui.services.message_clauses(view.id)
    return ui.page(request, "_message_review.html", **values)


def message_values(ui: Ui, request: Request, project_id: str, found: Any) -> dict[str, Any]:
    """What the review of a message shows: its events, the names of their tasks and people, and
    a growth in days of work, which a manager can compare with the message."""
    from sentinel.app.llm import work_left

    project = ui.services.state(ui.session(request), project_id).project
    left = work_left(project)

    def extra_days(item: WorkIncreaseReport) -> float | None:
        if item.factor is None or item.task not in left:
            return None
        return round(left[item.task] * (item.factor - 1), 1)

    def as_absence(question: Any, person: str) -> str:
        """The absence a question about an unknown person becomes once the manager names one."""
        report = AbsenceReport(
            person=person, first_day=question.first_day, return_date=question.return_date
        )
        return report.model_dump_json()

    def as_growth(question: Any, task: str) -> str:
        """The growth a question about an ambiguous task becomes once the manager picks one."""
        report = WorkIncreaseReport(
            task=task, extra_days=question.extra_days, factor=question.factor
        )
        return report.model_dump_json()

    return {
        "found": found,
        "names": {key: node.name for key, node in project.nodes().items()},
        "people": {p.key: p.name for p in project.definition.team},
        "extra_days": extra_days,
        "as_absence": as_absence,
        "as_growth": as_growth,
        "clauses": (),
    }


def kept_message(ui: Ui, request: Request, project_id: str, form: Form) -> dict[str, Any] | None:
    """The events a manager confirmed from a message, for the form after a refused submit: the
    review is shown again, while the message itself is not sent back."""
    from sentinel.app.llm import MessageDraft

    absences = tuple(AbsenceReport.model_validate_json(v) for v in form.getlist("msg_absence") if v)
    increases = tuple(
        WorkIncreaseReport.model_validate_json(v) for v in form.getlist("msg_increase") if v
    )
    new_tasks = tuple(NewTaskReport.model_validate_json(v) for v in form.getlist("msg_new") if v)
    if not (absences or increases or new_tasks):
        return None
    found = MessageDraft(absences=absences, increases=increases, new_tasks=new_tasks)
    return message_values(ui, request, project_id, found)
