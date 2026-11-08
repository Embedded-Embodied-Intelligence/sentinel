"""The v2 decisions (docs/design/v2-spec.md, sections 3 and 8.4; spec section 11.8): the decision
page with its effect, the contrastive reasoning written by code from the numbers, who is
affected, the cost of delay, approve, reject with a reason, adjust, postpone and the details;
the project tab "Decyzje" with the pending decisions and the archive."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response
from markupsafe import Markup

from sentinel.app.decisions import Option, parameter_of
from sentinel.app.errors import AppError
from sentinel.app.events import (
    OPEN,
    Brief,
    Decided,
    Expired,
    LiveState,
    RecommendationEntry,
    RejectReason,
    parse,
)
from sentinel.app.live import LiveProject
from sentinel.app.planning import FORECAST_ROLLOUTS
from sentinel.app.ui.core import Ui
from sentinel.app.ui.forms import Form
from sentinel.app.ui.v2.numbers import per_hundred
from sentinel.app.ui.v2.overview import Chip, decision_chips, escape, signed, tag, tone_of
from sentinel.app.ui.v2.shell import GATE, PREFIX, header, page, texts
from sentinel.app.ui.v2.text import TextsV2
from sentinel.app.views import ProjectView, RecommendationView, replaced_members
from sentinel.policies.base import Descope, Overtime, Subst

REASONS: tuple[RejectReason, ...] = ("too_expensive", "unavailable", "no_budget", "other")
NEEDS = {"subst": "people", "overtime": "money", "descope": "scope"}


@dataclass(frozen=True)
class Validity:
    """How long a pending decision stays worth taking (section 3): its validity date, the days
    left, whether it expires tomorrow, and the chance in 100 lost per day of waiting."""

    valid: date | None = None
    left: int | None = None
    expires_tomorrow: bool = False
    delay: int | None = None
    computing: bool = False


def entry_of(ui: Ui, request: Request, project_id: str, seq: int) -> RecommendationEntry | None:
    return ui.services.state(ui.session(request), project_id).recommendation(seq)


def validity_of(
    ui: Ui, request: Request, view: ProjectView, rec: RecommendationView
) -> Validity | None:
    """The validity of a pending decision; its job is started if it is not known yet."""
    state = ui.services.state(ui.session(request), view.id)
    entry = state.recommendation(rec.seq)
    if entry is None:
        return None
    if entry.validity is None:
        if entry.status in OPEN:
            job = ui.services.validity_job(ui.session(request), view.id, ui.language(request))
            if job.status in ("queued", "running"):
                return Validity(computing=True)
            entry = ui.services.state(ui.session(request), view.id).recommendation(rec.seq)
        if entry is None or entry.validity is None:
            return Validity()
    return validity_view(state.project, entry, date.today())


def validity_view(project: LiveProject, entry: RecommendationEntry, today: date) -> Validity:
    found = entry.validity
    if found is None:
        return Validity()
    delay = None if found.delay is None else per_hundred(found.delay)
    if found.valid_day is None:
        return Validity(delay=delay)
    calendar = project.calendar
    valid = calendar.date_of(found.valid_day)
    tomorrow = calendar.date_of(calendar.first(today + timedelta(days=1)))
    return Validity(valid, (valid - today).days, valid == tomorrow, delay)


# --------------------------------------------------------------------------- the brief


@dataclass(frozen=True)
class Effect:
    label: str
    text: str
    tone: str


def kept(text: str) -> str:
    """`text` with no line break inside, so a narrow effect breaks only at its arrow."""
    return text.replace(" ", "\u00a0").replace("-", "\u2011")


def effects(t: TextsV2, rec: RecommendationView, person_days: bool) -> list[Effect]:
    """The three effects (section 8.4): chance, end and budget before → after; green ▲ better.
    Each side of the arrow stays on one line; the value wraps at the arrow (WP16 hotfix)."""
    before, after = rec.without, rec.with_action
    if before is None or after is None:
        return []
    first, then = per_hundred(before.p_on_time), per_hundred(after.p_on_time)
    found = [
        Effect(
            t("v2.options.chance"),
            f"{first} → {kept(f'{then} {t("v2.chance.value", n="").strip()}')}",
            tone_of(then - first),
        )
    ]
    end_before = before.likely_finish or before.expected_finish
    end_after = after.likely_finish or after.expected_finish
    if end_before is not None and end_after is not None:
        tone = tone_of((end_after - end_before).days, better_up=False)
        text = f"{kept(t.date(end_before))} → {kept(t.date(end_after))}"
        found.append(Effect(t("v2.end.title"), text, tone))
    unit = t("v2.workdays", n="").strip() if person_days else t.plural("cost.units", 5, value="")
    cost = after.expected_cost - before.expected_cost
    spent = kept(f"{t.money(after.expected_cost)} {unit.strip()}")
    text = f"{t.money(before.expected_cost)} → {spent}"
    found.append(Effect(t("v2.budget.title"), text, tone_of(cost, better_up=False, eps=0.5)))
    return found


def workdays(t: TextsV2, value: float, person_days: bool) -> str:
    if person_days:
        return t("v2.workdays", n=t.money(value))
    return t.cost(value)


def quoted(t: TextsV2, text: str) -> str:
    """`text` in the language's quotation marks, its own quotes nested (Polish „…«…»…”)."""
    if t.lang == "pl":
        return "„" + text.replace("„", "«").replace("”", "»") + "”"
    return "“" + text.replace("“", "\u2018").replace("”", "\u2019") + "”"


def reasoning(t: TextsV2, rec: RecommendationView, person_days: bool) -> list[str]:
    """The contrastive "Uzasadnienie" (Miller 2019), written by code from the numbers: what the
    chosen option does against no change, then the best option of another kind of action
    (WP16 hotfix: never the same action with a re-plan). Within the materiality threshold of
    the chance (spec section 6, `eps_d`) it gave a similar result, and the choice stands by the
    smaller expected delay or as the simpler option (spec 11.5)."""
    before, after = rec.without, rec.with_action
    if before is None or after is None:
        return []
    first, then = per_hundred(before.p_on_time), per_hundred(after.p_on_time)
    end_before = before.likely_finish or before.expected_finish
    end_after = after.likely_finish or after.expected_finish
    ends = {
        "fromday": t.date(end_before),
        "toend": t.date(end_after),
    }
    same_end = end_before == end_after
    if then > first:
        key = "v2.why.gain_same_end" if same_end else "v2.why.gain"
    else:
        key = "v2.why.even_same_end" if same_end else "v2.why.even"
    lines = [t(key, before=first, after=then, **ends)]
    others = [a for a in rec.alternatives if a.action not in ("noop", rec.action)]
    if not others:
        lines.append(t("v2.why.only", before=first))
        return lines
    alt = max(others, key=lambda a: (a.p_on_time, -a.tardiness))
    option = quoted(t, alt.headline or alt.title)
    if abs(alt.p_on_time - after.p_on_time) < rec.eps_d:
        delay = alt.tardiness - after.tardiness >= rec.eps_t
        part = t("why.tie.by.tardiness") if delay else t("v2.why.simpler")
        lines.append(t("v2.why.alt_close", option=option, part=part))
    elif alt.p_on_time < after.p_on_time:
        price = workdays(t, max(0.0, alt.expected_cost - before.expected_cost), person_days)
        alt_n = per_hundred(alt.p_on_time)
        lines.append(t("v2.why.alt_less", option=option, chance=alt_n, price=price))
    else:
        tie = t.tie(rec.tie, rec.reason) if rec.tie is not None else rec.reason_text
        alt_n = per_hundred(alt.p_on_time)
        lines.append(t("v2.why.alt_similar", option=option, chance=alt_n, tie=tie))
    return lines


def who(
    t: TextsV2, project: LiveProject, entry: RecommendationEntry, rec: RecommendationView
) -> list[str]:
    """Who is affected (section 8.4): the action in full words (WP16 hotfix: the title is its
    short form), substitutes and the people they stand in for, temporary people, the dropped
    task and how many tasks get new dates."""
    chosen = entry.recommendation.chosen
    if chosen is None:
        return []
    from sentinel.app.views import person_names

    names = person_names(project, t.lang)
    keys = {j: key for key, j in project.activity_ids().items()}
    nodes = project.nodes()
    model = project.require_model()
    lines: list[str] = [rec.title] if rec.title != rec.headline else []
    for op in chosen.decision.operations:
        if isinstance(op, Subst):
            task = nodes[keys[op.activity]].name
            for worker, absent in replaced_members(project, op, entry.recommendation.day):
                gone = names.get(absent, absent) if absent is not None else "?"
                person = names.get(worker, worker)
                lines.append(t("v2.who.subst", person=person, task=task, absent=gone))
                lines.append(t("v2.who.absent", absent=gone))
        elif isinstance(op, Overtime):
            role = model.role_names[op.role]
            if op.workers == 1:
                lines.append(t.plural("v2.who.temp", op.days, role=role))
            else:
                lines.append(t("v2.who.temps", u=op.workers, role=role, n=op.days))
        elif isinstance(op, Descope):
            lines.append(t("v2.who.descope", task=nodes[keys[op.activity]].name))
    if rec.changes:
        lines.append(t.plural("v2.who.moved", len(rec.changes)))
    return lines or [t("v2.who.nobody")]


def need_of(entry: RecommendationEntry) -> str:
    chosen = entry.recommendation.chosen
    if chosen is None:
        return "plan"
    for op in chosen.decision.operations:
        if op.kind in NEEDS:
            return NEEDS[op.kind]
    return "plan"


def option_label(t: TextsV2, option: Option) -> str:
    if option.person is not None:
        return option.person
    if option.task is not None:
        return option.task
    return t("v2.adjust.option.temp", u=option.workers, role=option.role, n=option.days)


# --------------------------------------------------------------------------- details


@dataclass(frozen=True)
class Row:
    title: str
    chance: int
    end: date | None
    cost: str
    chosen: bool = False
    noop: bool = False


def option_rows(
    t: TextsV2, project: LiveProject, entry: RecommendationEntry, rec: RecommendationView
) -> list[Row]:
    """Every option of the comparison (section 8.4 "Szczegóły"): the chosen one, the others,
    "Bez zmian" last."""
    comparison = entry.recommendation.comparison
    if comparison is None:
        return []
    titles = {a.label: a.title for a in rec.alternatives} | {rec.label: rec.title}
    calendar = project.calendar
    rows = []
    for impact in comparison.impacts:
        q = impact.quantiles
        end = None if q is None else calendar.finish_date(q[1])
        noop = impact.label == "NOOP"
        rows.append(
            Row(
                t("v2.options.noop") if noop else titles.get(impact.label, impact.label),
                per_hundred(impact.p_on_time),
                end,
                workdays(t, impact.mean_cost, rec.budget is not None),
                impact.label == rec.label,
                noop,
            )
        )
    rows.sort(key=lambda r: (not r.chosen, r.noop))
    return rows


def histogram(
    t: TextsV2,
    project: LiveProject,
    makespans: list[int],
    deadline_day: int,
    title: str,
    span: tuple[int, int, int],
) -> Markup:
    """Finish days of the played futures as bars, on time green, late red, the deadline as a
    dashed line; each bar's count as its title. `span`: the first and last finish shown and the
    tallest bar, shared by the charts compared."""
    calendar = project.calendar
    counts = _day_counts(makespans)
    first, last, scale = span
    count = last - first + 1
    width, height, base, left = 640, 140, 112, 8
    bar = (width - 2 * left) / max(count, 1)
    parts = [tag("title", escape(title))]
    for i in range(count):
        c = first + i
        n = counts.get(c, 0)
        h = 0 if scale == 0 else (base - 16) * n / scale
        label = escape(t("v2.dist.day", date=t.date(calendar.finish_date(c)), n=n))
        parts.append(
            tag(
                "rect",
                tag("title", label),
                class_="bar-late" if c > deadline_day else "bar-on",
                x=round(left + i * bar + 1, 1),
                y=round(base - h, 1),
                width=round(max(bar - 2, 1), 1),
                height=round(h, 1),
            )
        )
        if i % max(1, count // 6) == 0:
            day = escape(t.date(calendar.finish_date(c)))
            parts.append(tag("text", day, x=round(left + i * bar, 1), y=base + 20))
    x = round(left + (deadline_day - first + 1) * bar, 1)
    parts.append(tag("line", class_="deadline", x1=x, y1=4, x2=x, y2=base))
    parts.append(tag("text", escape(t("v2.end.deadline")), x=x + 4, y=14))
    head = f'<svg class="hist" viewBox="0 0 {width} {height}" role="img">'
    return Markup(head + "".join(parts) + "</svg>")


def _day_counts(makespans: list[int]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for c in makespans:
        counts[c] = counts.get(c, 0) + 1
    return counts


# --------------------------------------------------------------------------- the archive


@dataclass(frozen=True)
class Past:
    """A decision of the archive: when, who, what, its fate and the brief as it was."""

    seq: int
    when: datetime
    actor: str
    title: str
    fate: str
    reason: str | None
    note: str | None
    chips: list[Chip]


def lifecycle_state(entry: RecommendationEntry, postponed_on: date | None, today: date) -> str:
    """The lifecycle word of a recommendation (spec section 11.8)."""
    if entry.status == "later":
        return "postponed" if postponed_on is not None and postponed_on >= today else "pending"
    if entry.status == "open":
        return "adjusted" if entry.corrected else "pending"
    return {
        "approved": "approved",
        "rejected": "rejected",
        "expired": "expired",
        "superseded": "superseded",
        "discarded": "discarded",
        "auto": "auto",
        "undone": "undone",
    }.get(entry.status, "pending")


def brief_chips(t: TextsV2, project: LiveProject, brief: Brief, person_days: bool) -> list[Chip]:
    calendar = project.calendar
    first, then = per_hundred(brief.p_before), per_hundred(brief.p_after)
    chips = [Chip(t("v2.effect.chance", before=first, after=then), tone_of(then - first))]
    if brief.finish_before is not None and brief.finish_after is not None:
        a, b = calendar.finish_date(brief.finish_before), calendar.finish_date(brief.finish_after)
        chips.append(
            Chip(
                t("v2.effect.end", before=t.date(a), after=t.date(b)),
                tone_of((b - a).days, better_up=False),
            )
        )
    cost = brief.cost_after - brief.cost_before
    key = "v2.effect.budget" if person_days else "v2.effect.budget_units"
    chips.append(Chip(t(key, change=signed(t, cost)), tone_of(cost, better_up=False, eps=0.5)))
    return chips


def archive(
    ui: Ui, request: Request, view: ProjectView, state: LiveState, today: date
) -> tuple[list[RecommendationView], list[Past]]:
    """The pending decisions and the project's past ones, newest first (a filtered log)."""
    t = texts(request)
    rows = ui.services.store.events(ui.session(request), view.id)
    by_seq = {r.seq: r for r in view.recommendations}
    fates: dict[int, tuple[datetime, Decided | Expired]] = {}
    created: dict[int, datetime] = {}
    for row in rows:
        if row.type == "recommendation":
            created[row.seq] = row.created
        elif row.type in ("decision", "expiry"):
            fate_event = parse(row)
            assert isinstance(fate_event, Decided | Expired)
            fates[fate_event.recommendation] = (row.created, fate_event)
    pending = [r for r in view.recommendations if r.status in OPEN]
    past: list[Past] = []
    for entry in state.recommendations:
        rec = by_seq.get(entry.seq)
        if rec is None or not rec.acts or entry.status in OPEN:
            continue
        found = fates.get(entry.seq)
        when = found[0] if found else created.get(entry.seq, datetime.now())
        event = found[1] if found else None
        fate = lifecycle_state(entry, None, today)
        actor = t("v2.actor.you") if isinstance(event, Decided) else t("v2.actor.sentinel")
        reason = note = None
        chips = decision_chips(t, rec, view.person_days)
        if isinstance(event, Decided):
            if event.reason is not None:
                reason = t(f"v2.reject.{event.reason}")
            note = event.note
            if event.brief is not None:
                chips = brief_chips(t, state.project, event.brief, view.person_days)
        past.append(Past(entry.seq, when, actor, rec.headline, fate, reason, note, chips))
    past.sort(key=lambda p: p.when, reverse=True)
    return pending, past


def router(ui: Ui) -> APIRouter:
    routes = APIRouter()
    services = ui.services

    def back_to(project_id: str, back: str | None, seq: int | None = None) -> str:
        base = f"{PREFIX}/projects/{project_id}"
        if back == "decision" and seq is not None:
            return f"{base}/decisions/{seq}"
        return base + ("/decisions" if back == "decisions" else "")

    def refresh(request: Request, project_id: str) -> None:
        """Expire a pending decision whose validity date passed (spec section 11.8)."""
        services.expire(ui.session(request), project_id, date.today())

    @routes.get(PREFIX + "/projects/{project_id}/decisions/{seq}")
    def decision_page(request: Request, project_id: str, seq: int) -> Response:
        session, language = ui.session(request), ui.language(request)
        refresh(request, project_id)
        view = services.live(session, project_id, language)
        rec = next((r for r in view.recommendations if r.seq == seq), None)
        state = services.state(session, project_id)
        entry = state.recommendation(seq)
        if rec is None or entry is None or not rec.acts:
            raise AppError("recommendation_not_found", "not_found")
        t = texts(request)
        today = date.today()
        pending = entry.status in OPEN
        validity = validity_of(ui, request, view, rec) if pending else None
        postponed_on = (
            postponed_date(ui, request, project_id, seq) if entry.status == "later" else None
        )
        options = services.correction_options(session, project_id, seq) if pending else []
        done = request.query_params.get("done")
        return page(
            ui,
            request,
            "decision.html",
            title=t("v2.dec.title"),
            nav="projects",
            tab="decisions",
            project=header(ui, request, view),
            view=view,
            rec=rec,
            pending=pending,
            life=lifecycle_state(entry, postponed_on, today),
            validity=validity,
            effects=effects(t, rec, view.person_days),
            reasoning=reasoning(t, rec, view.person_days),
            who=who(t, state.project, entry, rec),
            need=need_of(entry),
            parameter=parameter_of(entry.recommendation.chosen.decision)
            if entry.recommendation.chosen is not None
            else "none",
            options=[(o.key, option_label(t, o), o.current) for o in options],
            rows=option_rows(t, state.project, entry, rec),
            notice=decision_notice(t, done),
        )

    @routes.get(PREFIX + "/projects/{project_id}/decisions/{seq}/distribution")
    def distribution(request: Request, project_id: str, seq: int) -> Response:
        """The finish-date distribution with and without the action (loaded on opening)."""
        session = ui.session(request)
        state = services.state(session, project_id)
        entry = state.recommendation(seq)
        t = texts(request)
        charts: list[tuple[str, Markup, int, int]] = []
        if entry is not None and entry.status in OPEN and state.project.definition.deadline:
            found = services.distribution(session, project_id, seq)
            if found is not None:
                deadline = state.project.calendar.deadline(state.project.definition.deadline)
                every = [c for m in found for c in m]
                first = min(*every, deadline) - 1
                last = max(*every, deadline + 1)
                scale = max(max(_day_counts(m).values(), default=0) for m in found)
                for key, makespans in zip(("v2.dist.with", "v2.dist.without"), found, strict=True):
                    on = sum(1 for c in makespans if c <= deadline)
                    chart = histogram(
                        t, state.project, makespans, deadline, t(key), (first, last, scale)
                    )
                    charts.append((t(key), chart, on, len(makespans) - on))
        return page(ui, request, "_distribution.html", charts=charts, worlds=FORECAST_ROLLOUTS)

    @routes.get(PREFIX + "/projects/{project_id}/decisions")
    def decisions_tab(request: Request, project_id: str) -> Response:
        session, language = ui.session(request), ui.language(request)
        refresh(request, project_id)
        view = services.live(session, project_id, language)
        state = services.state(session, project_id)
        t = texts(request)
        pending, past = archive(ui, request, view, state, date.today())
        cards = [
            (rec, decision_chips(t, rec, view.person_days), validity_of(ui, request, view, rec))
            for rec in pending
        ]
        return page(
            ui,
            request,
            "decisions.html",
            title=t("v2.tab.decisions"),
            nav="projects",
            tab="decisions",
            project=header(ui, request, view),
            view=view,
            cards=cards,
            past=past,
            notice=decision_notice(t, request.query_params.get("done")),
        )

    @routes.post(PREFIX + "/projects/{project_id}/decisions/{seq}/approve")
    async def approve(request: Request, project_id: str, seq: int) -> Response:
        form = await Form.read(request)
        session, language = ui.session(request), ui.language(request)
        after = services.decide(session, project_id, seq, "approve", language, autonomy=GATE)
        entry = next((r for r in after.recommendations if r.seq == seq), None)
        back = form.get("back")
        target = back_to(project_id, "overview" if back == "decision" else back)
        if entry is not None and entry.status == "discarded":
            return ui.redirect(request, target, done="discarded")
        return ui.redirect(request, target, done="approved")

    @routes.post(PREFIX + "/projects/{project_id}/decisions/{seq}/reject")
    async def reject(request: Request, project_id: str, seq: int) -> Response:
        form = await Form.read(request)
        reason = next((r for r in REASONS if r == form.get("reason")), None)
        if reason is None:
            raise AppError("field_invalid", field="reason", detail=form.get("reason"))
        note = form.get("note") if reason == "other" else None
        session, language = ui.session(request), ui.language(request)
        services.decide(
            session, project_id, seq, "reject", language, reason=reason, note=note, autonomy=GATE
        )
        back = form.get("back")
        target = back_to(project_id, "overview" if back == "decision" else back)
        return ui.redirect(request, target, done="rejected")

    @routes.post(PREFIX + "/projects/{project_id}/decisions/{seq}/postpone")
    def postpone(request: Request, project_id: str, seq: int) -> Response:
        session, language = ui.session(request), ui.language(request)
        view = services.decide(session, project_id, seq, "later", language, autonomy=GATE)
        rec = next((r for r in view.recommendations if r.seq == seq), None)
        found = None if rec is None else validity_of(ui, request, view, rec)
        query = {"done": "postponed"}
        if found is not None and found.valid is not None:
            query["valid"] = found.valid.isoformat()
        return ui.redirect(request, f"{PREFIX}/projects/{project_id}", **query)

    @routes.post(PREFIX + "/projects/{project_id}/decisions/{seq}/adjust")
    async def adjust(request: Request, project_id: str, seq: int) -> Response:
        form = await Form.read(request)
        key = form.get("option")
        session, language = ui.session(request), ui.language(request)
        current = next(
            (o for o in services.correction_options(session, project_id, seq) if o.current), None
        )
        if current is None or key != current.key:
            services.correct(session, project_id, seq, key, language)
            return ui.redirect(
                request, f"{PREFIX}/projects/{project_id}/decisions/{seq}", done="adjusted"
            )
        return ui.redirect(request, f"{PREFIX}/projects/{project_id}/decisions/{seq}")

    @routes.post(PREFIX + "/projects/{project_id}/decisions/{seq}/explain")
    def explain(request: Request, project_id: str, seq: int) -> Response:
        """The AI explanation on request (section 8.4), polled until it is written."""
        session, language = ui.session(request), ui.language(request)
        job = services.explain(session, project_id, seq, language)
        return page(
            ui,
            request,
            "_explain.html",
            project_id=project_id,
            seq=seq,
            job=job.id,
            text=None,
            failed=None,
        )

    @routes.get(PREFIX + "/projects/{project_id}/decisions/{seq}/explain")
    def explain_poll(request: Request, project_id: str, seq: int) -> Response:
        session, language = ui.session(request), ui.language(request)
        job = services.job(session, request.query_params.get("job", ""), language)
        view = services.live(session, project_id, language)
        rec = next((r for r in view.recommendations if r.seq == seq), None)
        text = None if rec is None or rec.llm_explanation is None else rec.llm_explanation.text
        failed = None
        if job.status == "failed":
            failed = job.error.message if job.error is not None else texts(request)("v2.failed")
        return page(
            ui,
            request,
            "_explain.html",
            project_id=project_id,
            seq=seq,
            job=None if job.status in ("done", "failed") else job.id,
            text=text,
            failed=failed,
        )

    return routes


def postponed_date(ui: Ui, request: Request, project_id: str, seq: int) -> date | None:
    """The day the decision was last postponed, in the server's time zone."""
    found = None
    for row in ui.services.store.events(ui.session(request), project_id):
        if row.type == "decision":
            event = parse(row)
            if (
                isinstance(event, Decided)
                and event.recommendation == seq
                and event.verdict == "later"
            ):
                found = row.created.astimezone().date()
    return found


def decision_notice(t: TextsV2, done: str | None) -> Any:
    from sentinel.app.ui.v2.overview import Notice

    if done == "adjusted":
        return Notice(t("v2.adjust.done"), "info", "pencil")
    if done in ("approved", "rejected", "discarded"):
        return Notice(t(f"v2.done.{done}"), "good" if done == "approved" else "info")
    return None
