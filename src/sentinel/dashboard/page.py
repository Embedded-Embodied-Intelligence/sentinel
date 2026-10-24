"""The cockpit page (WP8; ADR-0021): one self-contained HTML file, inline CSS, the inline SVG
charts of `svg` and a little vanilla JavaScript (tooltips, filtering of the decision log,
collapsed sections opened before printing). It loads nothing and links nowhere outside itself;
labels are English or Polish (`labels`)."""

from collections.abc import Sequence
from html import escape

from sentinel.agent.decide import DecisionRecord
from sentinel.dashboard import svg
from sentinel.dashboard.assemble import Kpis, LogRow, Trigger
from sentinel.dashboard.cockpit import Cockpit, Side
from sentinel.dashboard.explain import Shown
from sentinel.dashboard.labels import (
    AXIS,
    DEADLINE,
    HOWTO,
    INK,
    INK_2,
    POLICY_NAMES,
    Text,
    policy_colors,
)

CSS = """
:root{--ink:#0b0b0b;--ink2:#52514e;--grid:#e1e0d9;--axis:#c3c2b7;--paper:#fff;--panel:#f6f5f1}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
header,main{max-width:1240px;margin:0 auto;padding:0 16px}
header{padding-top:18px}
h1{font-size:24px;margin:0 0 4px}
h2{font-size:18px;margin:28px 0 8px;border-bottom:1px solid var(--grid);padding-bottom:4px}
h3{font-size:15px;margin:16px 0 4px}
.subtitle{margin:2px 0;color:var(--ink2)}
nav{margin:10px 0 0;display:flex;flex-wrap:wrap;gap:6px 14px}
nav a{color:var(--ink)}
table{border-collapse:collapse}
.scroll{overflow-x:auto}
.kpis th,.kpis td{border-bottom:1px solid var(--grid);padding:5px 14px 5px 0;text-align:left}
.kpis td{font-variant-numeric:tabular-nums}
.swatch{display:inline-block;width:12px;height:12px;border-radius:2px;vertical-align:-1px;
margin-right:6px}
svg.chart{width:100%;height:auto;display:block}
svg.chart text{font-size:10px;fill:var(--ink)}
svg.chart text.tick,svg.chart text.lane{font-size:9px;fill:var(--ink2)}
svg.chart text.row{font-size:9px}
svg.chart text.vlabel{font-size:10px;font-weight:600}
svg.chart text.panel{font-size:11px;font-weight:600}
.legend{list-style:none;padding:0;margin:6px 0 10px;display:flex;flex-wrap:wrap;gap:4px 16px;
font-size:12px;color:var(--ink2)}
.legend li{display:flex;align-items:center;gap:6px}
.note{color:var(--ink2);font-size:13px;margin:4px 0}
details{margin-top:14px}
summary{cursor:pointer;font-weight:600}
.filters{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;margin:6px 0 10px;
font-size:13px}
.filters input[type=search]{padding:4px 6px;min-width:220px}
.log{width:100%;font-size:12px}
.log th{position:sticky;top:0;background:var(--panel);text-align:left;padding:5px 6px;
border-bottom:1px solid var(--axis)}
.log td{vertical-align:top;padding:5px 6px;border-bottom:1px solid var(--grid)}
.log td.num{white-space:nowrap;font-variant-numeric:tabular-nums}
.log td.expl{min-width:260px}
.ev{display:inline-block;border:1px solid var(--axis);border-radius:3px;padding:0 4px;
margin:0 3px 3px 0;white-space:nowrap}
.badge{display:inline-block;margin-top:3px;border:1px solid var(--axis);border-radius:3px;
padding:0 5px;font-size:11px;color:var(--ink2)}
.badge.ok{border-color:#1baf7a}
.badge.bad{border-color:#e34948}
.strong{font-weight:600}
.prov th{text-align:left;vertical-align:top;padding:4px 14px 4px 0;white-space:nowrap}
.prov td{padding:4px 0}
code{font-size:12px;word-break:break-all}
#tip{position:fixed;z-index:10;max-width:340px;background:var(--ink);color:#fff;font-size:12px;
padding:5px 8px;border-radius:4px;pointer-events:none}
@media print{@page{size:A4 landscape;margin:10mm}body{font-size:10pt}
nav,.filters,#tip{display:none!important}.log th{position:static}tr{break-inside:avoid}
h2,h3{break-after:avoid}}
"""

SCRIPT = """
(function () {
  "use strict";
  var tip = document.getElementById("tip");
  document.querySelectorAll("svg.chart title").forEach(function (title) {
    var mark = title.parentNode;
    if (mark.tagName.toLowerCase() === "svg") { return; }
    mark.setAttribute("data-tip", title.textContent);
    mark.removeChild(title);
  });
  function place(event) {
    var box = tip.getBoundingClientRect();
    var x = event.clientX + 14, y = event.clientY + 14;
    if (x + box.width > window.innerWidth - 8) { x = event.clientX - box.width - 14; }
    if (y + box.height > window.innerHeight - 8) { y = event.clientY - box.height - 14; }
    tip.style.left = Math.max(4, x) + "px";
    tip.style.top = Math.max(4, y) + "px";
  }
  document.addEventListener("mouseover", function (event) {
    var mark = event.target.closest ? event.target.closest("[data-tip]") : null;
    if (!mark) { tip.hidden = true; return; }
    tip.textContent = mark.getAttribute("data-tip");
    tip.hidden = false;
    place(event);
  });
  document.addEventListener("mousemove", function (event) {
    if (!tip.hidden) { place(event); }
  });
  var text = document.getElementById("log-text");
  if (text) {
    var gate = document.getElementById("log-gate");
    var actions = document.getElementById("log-actions");
    var count = document.getElementById("log-count");
    var rows = Array.prototype.slice.call(document.querySelectorAll("#log-table tbody tr"));
    var filter = function () {
      var words = text.value.trim().toLowerCase(), shown = 0;
      rows.forEach(function (row) {
        var show = (!words || row.textContent.toLowerCase().indexOf(words) >= 0) &&
          (gate.value === "all" || row.getAttribute("data-gate") === gate.value) &&
          (!actions.checked || row.getAttribute("data-action") === "1");
        row.hidden = !show;
        shown += show ? 1 : 0;
      });
      count.textContent = shown + " / " + rows.length;
    };
    [text, gate, actions].forEach(function (input) {
      input.addEventListener("input", filter);
      input.addEventListener("change", filter);
    });
    filter();
  }
  window.addEventListener("beforeprint", function () {
    document.querySelectorAll("details").forEach(function (box) { box.open = true; });
  });
})();
"""


def policy_name(name: str) -> str:
    return POLICY_NAMES.get(name, name)


def render(cockpit: Cockpit) -> str:
    """The page of a cockpit."""
    t = Text(cockpit.options.language)
    world, first, second = cockpit.world, cockpit.first, cockpit.second
    names = (policy_name(first.run.name), policy_name(second.run.name))
    colors = policy_colors(first.run.name, second.run.name)
    axis = svg.Axis(
        svg.horizon(
            world.plan.makespan,
            first.run.result.makespan,
            second.run.result.makespan,
            world.deadline,
        )
    )
    title = f"{t['title']}: {world.name}, r{world.replication}"
    sections = [
        _kpis(cockpit, names, colors, t),
        _gantt(cockpit, names, colors, axis, t),
        _risk(cockpit, names, colors, axis, t),
        _log(cockpit, names[0], t),
        _howto(t),
        _provenance(cockpit, names, t),
    ]
    reference = t[f"ref_{world.reference}"]
    header = (
        f"<header><h1>{escape(t['title'])}</h1>"
        f'<p class="subtitle">'
        + escape(
            t.format(
                "subtitle",
                instance=world.name,
                replication=world.replication,
                lambda_a=_plain(world.lambda_a, t),
                first=names[0],
                second=names[1],
            )
        )
        + '</p><p class="subtitle">'
        + escape(
            t.format(
                "deadline_line",
                deadline=world.deadline,
                delta=_plain(world.delta_d, t),
                c_star=world.c_star,
                reference=reference,
                budget=t.num(world.budget, 1),
            )
        )
        + "</p><nav>"
        + "".join(
            f'<a href="#{key}">{escape(t[f"nav_{key}"])}</a>'
            for key in ("kpis", "gantt", "risk", "log", "howto", "provenance")
        )
        + "</nav></header>"
    )
    return (
        "<!doctype html>\n"
        f'<html lang="{t.language}">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escape(title)}</title>\n<style>{CSS}</style>\n</head>\n<body>\n"
        f"{header}\n<main>\n" + "\n".join(sections) + "\n</main>\n"
        '<div id="tip" role="tooltip" hidden></div>\n'
        f"<script>{SCRIPT}</script>\n</body>\n</html>\n"
    )


def _plain(value: float, t: Text) -> str:
    """A parameter as written in the config (0.01, 0.2), with a decimal comma in Polish."""
    text = f"{value:g}"
    return text.replace(".", ",") if t.language == "pl" else text


def _swatch(inner: str, width: int = 26, height: int = 12) -> str:
    return (
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'aria-hidden="true">{inner}</svg>'
    )


def _legend(items: Sequence[tuple[str, str]]) -> str:
    return (
        '<ul class="legend">'
        + "".join(f"<li>{_swatch(mark)}{escape(label)}</li>" for mark, label in items)
        + "</ul>"
    )


def _kpis(cockpit: Cockpit, names: tuple[str, str], colors: tuple[str, str], t: Text) -> str:
    a, b = cockpit.first.kpis, cockpit.second.kpis
    deadline = t.format("day_n", day=cockpit.world.deadline)
    rows: list[tuple[str, str, str]] = [
        (t["kpi_deadline"], deadline, deadline),
        (
            t["kpi_makespan"],
            t.format("days_n", days=a.makespan),
            t.format("days_n", days=b.makespan),
        ),
        (t["kpi_on_time"], _on_time(a, t), _on_time(b, t)),
        (t["kpi_cost"], t.num(a.cost_ratio, 3), t.num(b.cost_ratio, 3)),
        (t["kpi_changes"], f"{a.plan_changes} ({a.moved})", f"{b.plan_changes} ({b.moved})"),
        (
            t["kpi_overtime"],
            f"{a.hired} ({t.num(a.overtime_cost, 1)})",
            f"{b.hired} ({t.num(b.overtime_cost, 1)})",
        ),
        (t["kpi_subst"], str(a.substituted), str(b.substituted)),
        (t["kpi_escalations"], _escalations(a, t), _escalations(b, t)),
        (t["kpi_deliberations"], _maybe(a.deliberations, t), _maybe(b.deliberations, t)),
    ]
    if a.descoped or b.descoped:
        rows.append((t["kpi_descoped"], str(a.descoped), str(b.descoped)))
    head = "".join(
        f'<th scope="col"><span class="swatch" style="background:{color}"></span>'
        f"{escape(name)}</th>"
        for name, color in zip(names, colors, strict=True)
    )
    body = "".join(
        f'<tr><th scope="row">{escape(label)}</th><td>{escape(x)}</td><td>{escape(y)}</td></tr>'
        for label, x, y in rows
    )
    return (
        f'<section id="kpis"><h2>{escape(t["nav_kpis"])}</h2><div class="scroll">'
        f'<table class="kpis"><thead><tr><th scope="col">{escape(t["measure"])}</th>{head}'
        f"</tr></thead><tbody>{body}</tbody></table></div></section>"
    )


def _on_time(k: Kpis, t: Text) -> str:
    if k.on_time:
        return t["yes"]
    if k.truncated:
        return t["truncated"]
    return t["no_late_1"] if k.late_days == 1 else t.format("no_late", days=k.late_days)


def _escalations(k: Kpis, t: Text) -> str:
    if k.escalations is None:
        return t["none"]
    return f"{k.escalations} ({k.approvals}, {k.deferrals})"


def _maybe(value: int | None, t: Text) -> str:
    return t["none"] if value is None else str(value)


def _lines(cockpit: Cockpit, side: Side, name: str, color: str, t: Text) -> list[svg.VLine]:
    world = cockpit.world
    return [
        svg.VLine(
            world.plan.makespan,
            t.format("plan_line", makespan=world.plan.makespan),
            INK_2,
            "1.5 2",
        ),
        svg.VLine(world.deadline, t.deadline_label(world.deadline), DEADLINE, "4 2", 1.4),
        svg.VLine(
            side.run.result.makespan,
            t.format("realised_line", policy=name, makespan=side.run.result.makespan),
            color,
            "",
            1.6,
        ),
    ]


def _gantt(
    cockpit: Cockpit, names: tuple[str, str], colors: tuple[str, str], axis: svg.Axis, t: Text
) -> str:
    first, second = cockpit.first, cockpit.second
    stripes = "url(#stripes-g1)"
    items = [
        (f'<rect x="1" y="4" width="24" height="3.5" fill="{AXIS}"/>', t["legend_plan"]),
        (f'<rect x="1" y="3" width="24" height="6.5" fill="{colors[0]}"/>', t["legend_full"]),
        (
            f'<rect x="1" y="3" width="24" height="6.5" fill="{stripes}" stroke="{colors[0]}" '
            'stroke-width="0.6"/>',
            t["legend_partial"],
        ),
        (
            f'<rect x="1.5" y="3" width="23" height="6" fill="none" stroke="{colors[0]}" '
            'stroke-dasharray="2 1.5"/>',
            t["legend_paused"],
        ),
        (f'<path d="{svg.diamond(13, 6, 3.6)}" fill="{INK}"/>', t["legend_subst"]),
        (
            f'<circle cx="13" cy="6" r="2.6" fill="white" stroke="{INK}"/>',
            t["legend_temp"],
        ),
        (f'<path d="{svg.triangle(13, 6, 3.2, False)}" fill="{INK}"/>', t["legend_shock"]),
        (
            f'<path d="{svg.diamond(13, 6, 4)}" fill="white" stroke="{INK}"/>',
            t["legend_new"],
        ),
        (f'<path d="{svg.triangle(13, 6, 3.6, True)}" fill="{INK}"/>', t["legend_absence"]),
        (
            f'<path d="{svg.triangle(13, 6, 3.6, True)}" fill="white" stroke="{INK}"/>',
            t["legend_idle"],
        ),
        (
            f'<line x1="2" y1="6" x2="24" y2="6" stroke="{DEADLINE}" stroke-width="1.4" '
            'stroke-dasharray="4 2"/>',
            t["legend_deadline"],
        ),
    ]
    if any(r.descoped_day is not None for side in (first, second) for r in side.rows):
        items.append(
            (
                f'<path d="M10 3L16 9M16 3L10 9" stroke="{INK}" stroke-width="1.4"/>',
                t["legend_descoped"],
            )
        )
    charts = []
    for side, name, color, key in (
        (first, names[0], colors[0], "g1"),
        (second, names[1], colors[1], "g2"),
    ):
        chart = svg.gantt(
            side.rows,
            side.events,
            axis,
            _lines(cockpit, side, name, color, t),
            color=color,
            key=key,
            title=t.format("gantt_title", policy=name),
            t=t,
        )
        charts.append(chart)
    return (
        f'<section id="gantt"><h2>{escape(t.format("gantt_title", policy=names[0]))}</h2>'
        f'<p class="note">{escape(t["gantt_note"])}</p>{_legend(items)}{charts[0]}'
        f"<details><summary>{escape(t.format('gantt_compare', policy=names[1]))}</summary>"
        f"{charts[1]}</details></section>"
    )


def _risk(
    cockpit: Cockpit, names: tuple[str, str], colors: tuple[str, str], axis: svg.Axis, t: Text
) -> str:
    first, second, world = cockpit.first, cockpit.second, cockpit.world
    forecasts = cockpit.forecasts
    if first.run.is_sentinel:
        note = t.format("risk_note_agent", n=len(forecasts))
    else:
        note = t.format(
            "risk_note_policy",
            policy=names[0],
            period=world.config.review_period,
            n=len(forecasts),
        )
    outcomes = [
        svg.Outcome(
            t.format("realised_line", policy=names[0], makespan=first.run.result.makespan),
            first.run.result.makespan,
            colors[0],
            "",
        ),
        svg.Outcome(
            t.format("realised_line", policy=names[1], makespan=second.run.result.makespan),
            second.run.result.makespan,
            colors[1],
            "5 3",
        ),
    ]
    chart = svg.risk(
        forecasts,
        axis,
        deadline=world.deadline,
        target=first.run.params.theta_d,
        outcomes=outcomes,
        color=colors[0],
        key="risk",
        title=t.format("risk_title", policy=names[0]),
        t=t,
    )
    items = [
        (
            f'<line x1="1" y1="6" x2="25" y2="6" stroke="{colors[0]}" stroke-width="1.4"/>'
            f'<circle cx="13" cy="6" r="2.6" fill="{colors[0]}" stroke="white"/>',
            t["legend_noop"],
        ),
        (f'<path d="{svg.triangle(13, 6, 3.6, False)}" fill="{INK}"/>', t["legend_chosen_auto"]),
        (
            f'<path d="{svg.triangle(13, 6, 3.6, False)}" fill="white" stroke="{INK}"/>',
            t["legend_chosen_wait"],
        ),
        (
            f'<line x1="1" y1="6" x2="25" y2="6" stroke="{INK_2}" stroke-dasharray="5 3"/>',
            t["legend_target"],
        ),
        (
            f'<rect x="1" y="2" width="24" height="8" fill="{colors[0]}" fill-opacity="0.18" '
            f'stroke="{colors[0]}" stroke-dasharray="2 2" stroke-width="0.6"/>',
            t["legend_band"],
        ),
        (
            f'<line x1="1" y1="6" x2="25" y2="6" stroke="{colors[0]}"/>'
            f'<rect x="11" y="4" width="4" height="4" fill="{colors[0]}"/>',
            t["legend_median"],
        ),
        (
            f'<line x1="1" y1="6" x2="25" y2="6" stroke="{DEADLINE}" stroke-width="1.3" '
            'stroke-dasharray="4 2"/>',
            t["legend_deadline"],
        ),
    ]
    return (
        f'<section id="risk"><h2>{escape(t.format("risk_title", policy=names[0]))}</h2>'
        f'<p class="note">{escape(note)}</p>{_legend(items)}{chart}</section>'
    )


def _trigger(trigger: Trigger, t: Text) -> str:
    match trigger.kind:
        case "absence" | "return":
            text = t.format(f"ev_{trigger.kind}", worker=trigger.worker, activity=trigger.activity)
        case "idle_absences":
            text = t.format("ev_idle", count=trigger.count)
        case "work_increase":
            factor = t.num(trigger.factor or 0.0, 2)
            text = t.format("ev_work", factor=factor, activity=trigger.activity)
        case "new_activity":
            text = t.format("ev_new", activity=trigger.activity)
        case "review" | "approval":
            text = t[f"ev_{trigger.kind}"]
    return f'<span class="ev">{escape(text)}</span>'


def _badge(shown: Shown, t: Text) -> str:
    if shown.source == "template":
        return f'<span class="badge">{escape(t["badge_template"])}</span>'
    model = shown.model or "?"
    faith = shown.faithfulness
    if shown.error is not None or faith is None:
        text = t.format("badge_invalid", model=model, error=shown.error or "?")
        return f'<span class="badge bad">{escape(text)}</span>'
    if faith.fully_faithful:
        return f'<span class="badge ok">{escape(t.format("badge_faithful", model=model))}</span>'
    details = t.format(
        "faith_details",
        right=sum(f.correct for f in faith.facts),
        facts=len(faith.facts),
        chosen="✓" if faith.chosen_named else "✗",
        component="✓" if faith.component_right else "✗",
        numbers=faith.hallucinated,
    )
    text = t.format("badge_unfaithful", model=model, details=details)
    return f'<span class="badge bad">{escape(text)}</span>'


def _p_t(p: float | None, tardiness: float | None, t: Text) -> str:
    if p is None:
        return t["none"]
    return f"{t.num(p, 2)} / " + (t["none"] if tardiness is None else t.num(tardiness, 1))


def _gate(row: LogRow, t: Text) -> str:
    record: DecisionRecord = row.record
    gate = row.gate
    if gate == "escalated" and record.approval_day is not None:
        text = t.format("escalated_to", day=record.approval_day)
    else:
        text = t[f"gate_{gate}"]
    strong = gate in ("escalated", "approved")
    cell = f'<span class="strong">{escape(text)}</span>' if strong else escape(text)
    if record.discarded is not None:
        cell += "<br>" + escape(t.format("discarded", label=record.discarded))
    return cell


def _log_row(row: LogRow, shown: Shown, t: Text) -> str:
    record = row.record
    by_label = {c.label: c for c in record.candidates}
    chosen = by_label.get(record.chosen)
    runner = None if record.runner_up is None else by_label.get(record.runner_up)
    level = chosen.level if chosen is not None else record.decision.level
    if chosen is not None:
        chosen_pt = _p_t(chosen.p_on_time, chosen.tardiness, t)
    elif record.needs is not None:
        chosen_pt = _p_t(record.needs.p_on_time, None, t)
    else:
        chosen_pt = t["none"]
    needs = (
        t["none"]
        if record.needs is None
        else f"{t.num(record.needs.deadline, 2)} / {t.num(record.needs.budget, 3)}"
    )
    runner_label = t["none"] if record.runner_up is None else record.runner_up
    runner_pt = t["none"] if runner is None else _p_t(runner.p_on_time, runner.tardiness, t)
    triggers = "".join(_trigger(trigger, t) for trigger in row.triggers)
    action = "0" if record.chosen == "NOOP" else "1"
    return (
        f'<tr data-gate="{row.gate}" data-action="{action}"><td class="num">{row.day}</td>'
        f'<td>{triggers}</td><td class="num">{escape(needs)}</td>'
        f'<td>{escape(record.chosen)} ({level})</td><td class="num">{escape(chosen_pt)}</td>'
        f'<td>{escape(runner_label)}</td><td class="num">{escape(runner_pt)}</td>'
        f"<td>{escape(t[f'c_{record.reason}'])}</td><td>{_gate(row, t)}</td>"
        f'<td class="expl">{escape(shown.text)}<br>{_badge(shown, t)}</td></tr>'
    )


def _log(cockpit: Cockpit, name: str, t: Text) -> str:
    title = f"<h2>{escape(t.format('log_title', policy=name))}</h2>"
    if not cockpit.log:
        note = escape(t.format("log_none", policy=name))
        return f'<section id="log">{title}<p class="note">{note}</p></section>'
    gates = ("auto", "deferred", "escalated", "approved", "none")
    options = f'<option value="all">{escape(t["filter_all"])}</option>' + "".join(
        f'<option value="{g}">{escape(t[f"gate_{g}"])}</option>' for g in gates
    )
    n = len(cockpit.log)
    filters = (
        '<div class="filters">'
        f'<label>{escape(t["filter_text"])} <input type="search" id="log-text" '
        f'placeholder="{escape(t["filter_placeholder"])}"></label>'
        f'<label>{escape(t["filter_gate"])} <select id="log-gate">{options}</select></label>'
        f'<label><input type="checkbox" id="log-actions"> {escape(t["filter_actions"])}</label>'
        f'<span>{escape(t["rows_shown"])}: <span id="log-count">{n} / {n}</span></span></div>'
    )
    head = "".join(
        f'<th scope="col">{escape(t[key])}</th>'
        for key in (
            "col_day",
            "col_events",
            "col_needs",
            "col_chosen",
            "col_p",
            "col_runner",
            "col_p",
            "col_component",
            "col_gate",
            "col_explanation",
        )
    )
    rows = zip(cockpit.log, cockpit.explanations, strict=True)
    body = "".join(_log_row(row, shown, t) for row, shown in rows)
    return (
        f'<section id="log">{title}{filters}<div class="scroll"><table class="log" '
        f'id="log-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'
        "</section>"
    )


def _howto(t: Text) -> str:
    items = "".join(f"<li>{escape(text)}</li>" for text in HOWTO[t.language])
    return f'<section id="howto"><h2>{escape(t["howto_title"])}</h2><ol>{items}</ol></section>'


def _policy_text(cockpit: Cockpit, side: Side, t: Text) -> str:
    config, policy_run = cockpit.world.config, side.run
    if policy_run.variant is None:
        return t.format(
            "p_baseline",
            policy=policy_run.name,
            tcp=_plain(config.deterministic_time_limit, t),
            cp_seed=config.cp_seed,
            delta=_plain(max(cockpit.world.delta_d, *config.deltas), t),
        )
    p = policy_run.params
    return t.format(
        "p_sentinel",
        rule=p.rule,
        variant=p.variant,
        n1=p.n_stage1,
        n=p.n_rollouts,
        theta=_plain(p.theta_d, t),
        eps_d=_plain(p.eps_d, t),
        eps_t=_plain(p.eps_t, t),
        eps_b=_plain(p.eps_b, t),
        eps_delta=_plain(p.eps_delta, t),
        autonomy=p.autonomy,
        tau=_plain(p.tau_def, t),
        delay=p.approval_delay,
        descope=t["on"] if p.descope else t["off"],
        tcp=_plain(p.deterministic_time_limit, t),
        cp_seed=p.cp_seed,
    )


def _provenance(cockpit: Cockpit, names: tuple[str, str], t: Text) -> str:
    world, prov, config = cockpit.world, cockpit.provenance, cockpit.world.config
    if prov.commit is None:
        code = t["p_nogit"]
    else:
        code = t.format("p_dirty" if prov.dirty else "p_clean", commit=prov.commit)
    method = world.plan.method
    settings = ", ".join(f"{k}={v}" for k, v in method.model_dump().items() if k != "kind")
    if cockpit.explain_source == "template":
        explain_text = t["p_explain_template"]
    else:
        backend, model, cache = cockpit.explain_source.split("|")
        explain_text = t.format("p_explain_llm", backend=backend, model=model, cache=cache)
    pert = config.pert
    rows = [
        (t["p_command"], f"<code>{escape(prov.command)}</code>"),
        (t["p_code"], escape(code)),
        (
            t["p_seeds"],
            escape(
                t.format(
                    "p_seeds_text",
                    seed=world.seed,
                    base=config.base_seed,
                    set=world.set_name,
                    instance=world.stem,
                    replication=world.replication,
                )
            ),
        ),
        (
            t["p_world"],
            escape(
                t.format(
                    "p_world_text",
                    instance=world.name,
                    activities=world.instance.n_real,
                    workers=len(world.instance.workers),
                    lambda_a=_plain(world.lambda_a, t),
                    mean_absence=_plain(world.disruptions.mean_absence, t),
                    lambda_s=_plain(world.disruptions.lambda_s, t),
                    lambda_n=_plain(world.disruptions.lambda_n, t),
                    a=_plain(pert.a, t),
                    m=_plain(pert.m, t),
                    b=_plain(pert.b, t),
                    lam=_plain(pert.lam, t),
                    period=config.review_period,
                )
            ),
        ),
        (
            t["p_plan"],
            escape(
                t.format(
                    "p_plan_text",
                    method=f"{method.kind} ({settings})",
                    makespan=world.plan.makespan,
                    status=world.plan.status,
                )
            ),
        ),
        (
            t["p_goals"],
            escape(
                t.format(
                    "p_goals_text",
                    deadline=world.deadline,
                    delta=_plain(world.delta_d, t),
                    c_star=world.c_star,
                    reference=t[f"ref_{world.reference}"],
                    budget=t.num(world.budget, 1),
                    beta=_plain(config.beta, t),
                )
            ),
        ),
        *(
            (t.format("p_policy", policy=name), escape(_policy_text(cockpit, side, t)))
            for name, side in zip(names, (cockpit.first, cockpit.second), strict=True)
        ),
        (t["p_explain"], escape(explain_text)),
        (t["p_software"], escape(", ".join(f"{k} {v}" for k, v in prov.software))),
    ]
    body = "".join(f'<tr><th scope="row">{escape(k)}</th><td>{v}</td></tr>' for k, v in rows)
    return (
        f'<section id="provenance"><h2>{escape(t["provenance_title"])}</h2><div class="scroll">'
        f'<table class="prov"><tbody>{body}</tbody></table></div>'
        f'<p class="note">{escape(t["p_note"])}</p></section>'
    )
