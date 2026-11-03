"""The owner's log of one tester of the remote usability test (WP13; docs/usability/README.md).

Finds the demo sandboxes holding a project whose name starts with the tester's code (e.g. "P1
Aplikacja rezerwacji wizyt") and writes `docs/usability/logs/<code>.md`: the timeline of each
sandbox with wall-clock times (projects, plan, status reports with their content,
recommendations, decisions, simulations, failed jobs, and from the demo's request log, ADR-0030,
the pages opened and the forms sent or refused) and the durations of the protocol's tasks with
the page requests and refused forms between them. It reads the demo's database read-only, so
the demo keeps running, and writes no address, cookie, key or id; free text only as the tester
typed it into the project (names of the project, people and tasks), absences only as dates.

    uv run python scripts/usability_logs.py --data-dir ~/.local/share/sentinel-demo --code P1
"""

import argparse
import json
import re
import sqlite3
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, tzinfo
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from sentinel.app import planning
from sentinel.app.events import replay
from sentinel.app.models import Language
from sentinel.app.store import EventRow
from sentinel.app.ui.text import Texts
from sentinel.app.views import RecommendationView, forecast_view, project_view

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "usability" / "logs"
SEEDED_S = 5  # the showcase's events are written with the sandbox, before the tester acts
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
VERDICTS = {"approve": "approved", "reject": "rejected", "later": "decide later"}
STATES = {"not_started": "not started", "in_progress": "in progress", "done": "done"}
SOURCES = {"csv": "from a spreadsheet", "json": "from a JSON file", "text": "by the AI"}
POLICIES = {"sentinel": "Sentinel", "no_reaction": "no reaction"}
PAGES = {  # a route (method, path template) in words
    ("GET", "/"): "the start page",
    ("GET", "/new"): "the new project form",
    ("POST", "/new"): "sent the project's basics",
    ("GET", "/projects/{project_id}/setup/{step}"): "a setup step",
    ("POST", "/projects/{project_id}/setup/basics"): "saved the basics",
    ("POST", "/projects/{project_id}/setup/team"): "saved the team",
    ("POST", "/projects/{project_id}/setup/tasks"): "saved the tasks",
    ("POST", "/projects/{project_id}/setup/import"): "imported a spreadsheet",
    ("POST", "/projects/{project_id}/setup/describe"): "sent a description to the AI",
    ("POST", "/projects/{project_id}/setup/use-extraction"): "took the AI's tasks",
    ("GET", "/projects/{project_id}"): "the project's page",
    ("GET", "/projects/{project_id}/checkin"): "the status report form",
    ("POST", "/projects/{project_id}/checkin"): "sent the status report",
    ("POST", "/projects/{project_id}/checkin/message"): "sent a message to the AI",
    ("POST", "/projects/{project_id}/ask"): "asked Sentinel for a proposal",
    ("GET", "/projects/{project_id}/recommendations/{seq}"): "a recommendation",
    ("POST", "/projects/{project_id}/recommendations/{seq}/decision"): "sent a decision",
    ("POST", "/projects/{project_id}/recommendations/{seq}/undo"): "sent an undo",
    ("POST", "/projects/{project_id}/recommendations/{seq}/explain"): "asked for an explanation",
    ("GET", "/projects/{project_id}/history"): "the history",
    ("GET", "/projects/{project_id}/settings"): "the project's settings",
    ("POST", "/projects/{project_id}/settings"): "saved the project's settings",
    ("GET", "/projects/{project_id}/report.html"): "the HTML report",
    ("GET", "/projects/{project_id}/delete"): "the delete page",
    ("POST", "/projects/{project_id}/delete"): "deleted a project",
    ("GET", "/simulator"): "the simulator",
    ("POST", "/simulator"): "started a simulation",
    ("POST", "/projects/{project_id}/advance"): "advanced the simulation",
    ("GET", "/jobs/{job_id}"): "a job's progress",
    ("POST", "/jobs/{job_id}/cancel"): "stopped a running job",
    ("GET", "/how-it-works"): "How it works",
    ("GET", "/settings"): "the settings",
    ("GET", "/lang/{code}"): "switched the language",
}
TASKS = (  # the protocol's tasks that leave a trace: number, name, what ends it
    (1, "Project from the spreadsheet", "the plan"),
    (3, "Absence (with task 2)", "the saved status report"),
    (4, "Recommendation", "the decision"),
    (5, "Simulator", "the end of the simulation"),
)
ACTION, EVENT, JOB, PAGE = range(4)  # the order of rows in one second
FORMATS = Texts("en")  # chances and shares rounded as the pages round them


@dataclass
class Project:
    id: str
    kind: str
    name: str
    events: list[EventRow]
    label: str = ""
    seeded: int = 0  # the showcase's events written with the sandbox
    recommendations: dict[int, RecommendationView] = field(default_factory=dict)


@dataclass(frozen=True)
class Request:
    at: datetime
    method: str
    path: str
    project: str | None
    partial: bool
    status: int

    @property
    def page(self) -> bool:
        """A page the browser opened: not a part a page loads, not the JSON API."""
        return self.method == "GET" and not self.partial and not self.path.startswith("/api/")

    @property
    def refused(self) -> bool:
        return self.method != "GET" and self.status >= 400


@dataclass
class Sandbox:
    created: datetime
    projects: list[Project]
    jobs: list[sqlite3.Row]
    requests: list[Request] | None  # None: the demo kept no request log


@dataclass(frozen=True)
class Row:
    at: datetime
    rank: int
    what: str
    details: str = ""


def connect(database: Path) -> sqlite3.Connection:
    """The demo's database, read-only."""
    if not database.is_file():
        raise SystemExit(f"no database at {database}")
    connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def matches(name: str, code: str) -> bool:
    """Whether a project's name starts with the code as a word ("P1 …", not "P10 …")."""
    return re.match(rf"\s*{re.escape(code)}(?![0-9A-Za-z])", name, re.IGNORECASE) is not None


def stamp(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone(UTC)


def find_sandboxes(db: sqlite3.Connection, code: str) -> list[Sandbox]:
    """The demo sandboxes with a project named with `code`, oldest first."""
    rows = db.execute(
        "SELECT s.id, s.created, p.name FROM sessions s JOIN projects p ON p.session = s.id "
        "WHERE s.demo = 1 ORDER BY s.created, s.id"
    ).fetchall()
    found = {r["id"]: stamp(r["created"]) for r in rows if matches(r["name"], code)}
    logged = db.execute("SELECT 1 FROM sqlite_master WHERE name = 'requests'").fetchone()
    return [load(db, sid, created, logged is not None) for sid, created in found.items()]


def load(db: sqlite3.Connection, sid: str, created: datetime, logged: bool) -> Sandbox:
    projects = []
    for row in db.execute("SELECT * FROM projects WHERE session = ? ORDER BY created, id", (sid,)):
        events = [
            EventRow(row["id"], e["seq"], e["type"], json.loads(e["payload"]), stamp(e["created"]))
            for e in db.execute("SELECT * FROM events WHERE project = ? ORDER BY seq", (row["id"],))
        ]
        projects.append(Project(row["id"], row["kind"], row["name"], events))
    jobs = db.execute(
        "SELECT * FROM jobs WHERE session = ? ORDER BY created, rowid", (sid,)
    ).fetchall()
    requests = None
    if logged:
        requests = [
            Request(
                stamp(r["at"]),
                r["method"],
                r["path"],
                r["project"],
                bool(r["partial"]),
                r["status"],
            )
            for r in db.execute("SELECT * FROM requests WHERE session = ? ORDER BY id", (sid,))
        ]
    # A sandbox made while the log was off has no row, not even its first request.
    return Sandbox(created, projects, jobs, requests or None)


def prepare(sandbox: Sandbox, language: Language) -> None:
    """Label the projects and read their recommendations as the pages show them."""
    simulations = 0
    for project in sandbox.projects:
        first = project.events[0].payload if project.events else {}
        if project.kind == "simulator":
            simulations += 1
            project.label = f"simulation {simulations}"
            continue
        if first.get("source") == "showcase":
            project.label = "the showcase project"
            limit = sandbox.created.timestamp() + SEEDED_S
            project.seeded = sum(1 for e in project.events if e.created.timestamp() <= limit)
        else:
            project.label = f"“{project.name}”"
        try:
            view = project_view(project.id, replay(project.events), language, project.name)
        except Exception:  # a log the code cannot replay still has its timeline
            continue
        project.recommendations = {r.seq: r for r in view.recommendations}


def main_project(sandbox: Sandbox, code: str) -> Project | None:
    """The tester's project: of those named with the code, the first with a status report,
    else the first with a plan, else the latest."""
    named = [p for p in sandbox.projects if p.kind == "live" and matches(p.name, code)]
    for kind in ("checkin", "baseline"):
        for project in named:
            if any(e.type == kind for e in project.events):
                return project
    return named[-1] if named else None


# ---- words


def day(value: date | str) -> str:
    when = date.fromisoformat(value) if isinstance(value, str) else value
    return f"{WEEKDAYS[when.weekday()]} {when.day} {MONTHS[when.month - 1]} {when.year}"


def short_day(value: str) -> str:
    when = date.fromisoformat(value)
    return f"{when.day} {MONTHS[when.month - 1]}"


def percent(value: float | None) -> str:
    return FORMATS.pct(value).replace("\xa0", " ")


def share(value: float | None) -> str:
    return "–" if value is None else FORMATS.share(value).replace("\xa0", " ")


def duration(seconds: float) -> str:
    total = round(seconds)
    hours, rest = divmod(total, 3600)
    clock = (
        f"{hours}:{rest // 60:02d}:{rest % 60:02d}" if hours else f"{rest // 60}:{rest % 60:02d}"
    )
    return f"{total} s ({clock})"


def names(project: Project) -> tuple[dict[str, str], dict[str, str]]:
    """The names of the project's people and tasks by key, from every definition in its log."""
    people: dict[str, str] = {}
    tasks: dict[str, str] = {}
    for event in project.events:
        definition = event.payload.get("definition")
        if isinstance(definition, dict):
            people.update({p["key"]: p["name"] for p in definition.get("team", [])})
            tasks.update({t["key"]: t["name"] for t in definition.get("tasks", [])})
        report = event.payload.get("checkin")
        if isinstance(report, dict):
            tasks.update({t["key"]: t["name"] for t in report.get("new_tasks", []) if t.get("key")})
    return people, tasks


def checkin_words(payload: dict[str, Any], project: Project) -> str:
    """A status report's content: dates, states, shares done, people and their absence dates."""
    people, tasks = names(project)
    report = payload.get("checkin", {})
    parts = [f"as of {day(report['date'])}"]
    for task in report.get("tasks", []):
        text = f"{tasks.get(task['task'], task['task'])}: {STATES.get(task['status'], '')}"
        if task.get("status") == "in_progress" and task.get("percent") is not None:
            text += f" {task['percent']:g} %"
        if task.get("finish"):
            text += f" on {short_day(task['finish'])}"
        parts.append(text)
    for absence in report.get("absences", []):
        back = absence.get("return_date")
        who = people.get(absence["person"], absence["person"])
        text = f"{who} absent from {short_day(absence['first_day'])}"
        parts.append(text + (f", back {short_day(back)}" if back else ", return unknown"))
    for increase in report.get("increases", []):
        extra = increase.get("extra_days")
        more = f"+{extra:g} days" if extra is not None else f"×{increase.get('factor', 1):g}"
        parts.append(f"{tasks.get(increase['task'], increase['task'])}: more work ({more})")
    for task in report.get("new_tasks", []):
        parts.append(f"new task {task['name']} ({task['duration']} days)")
    return "; ".join(parts)


def recommendation_words(project: Project, seq: int) -> str:
    view = project.recommendations.get(seq)
    if view is None:
        return f"recommendation {seq}"
    if view.kind == "noop" or view.status == "none":
        return "no change proposed"
    effect = ""
    if view.with_action is not None and view.without is not None:
        effect = f" ({percent(view.without.p_on_time)} → {percent(view.with_action.p_on_time)})"
    return view.title + effect


def event_rows(project: Project) -> list[Row]:
    """The rows of a project's events; of the definitions saved one after another (the setup's
    autosave), the last; after the first plan, the forecast the overview showed."""
    rows = []
    events = project.events[project.seeded :]
    for index, event in enumerate(events):
        following = events[index + 1].type if index + 1 < len(events) else None
        if event.type == "definition" and following == "definition":
            continue
        row = event_row(project, event)
        if row is not None:
            rows.append(row)
        if event.type == "baseline" and not project.seeded and project.kind == "live":
            rows += plan_forecast(project, project.events.index(event))
    return rows


def plan_forecast(project: Project, index: int) -> list[Row]:
    """The overview's forecast right after the plan of event `index`, computed again: it is
    deterministic for the project's state (spec section 11.4), and the first plan's only."""
    if any(e.type == "baseline" for e in project.events[:index]):
        return []
    try:
        state = replay(project.events[: index + 1])
        view = forecast_view(state.project, planning.forecast(state.project))
    except Exception:  # the timeline goes on without it
        return []
    details = f"chance {percent(view.p_on_time)}, most likely finish {day(view.p50)}, "
    details += f"bad case {day(view.p90)}"
    return [Row(project.events[index].created, EVENT, f"Overview shows: {project.label}", details)]


def event_row(project: Project, event: EventRow) -> Row | None:
    payload, where, at = event.payload, project.label, event.created
    if event.type == "created" and project.kind == "live":
        definition = payload["definition"]
        source = SOURCES.get(payload.get("source", "new"))
        deadline = definition.get("deadline")
        details = f"start {day(definition['start'])}"
        details += f", deadline {day(deadline)}" if deadline else ", no deadline"
        what = f"Project created{f' {source}' if source else ''}: {where}"
        return Row(at, EVENT, what, details)
    if event.type == "definition":
        definition = payload["definition"]
        team, tasks = len(definition.get("team", [])), len(definition.get("tasks", []))
        return Row(at, EVENT, f"Project saved: {where}", f"{team} people, {tasks} tasks")
    if event.type == "baseline":
        return Row(at, EVENT, f"Plan made: {where}")
    if event.type == "checkin":
        return Row(at, EVENT, f"Status report saved: {where}", checkin_words(payload, project))
    if event.type == "recommendation":
        view = project.recommendations.get(event.seq)
        what = "Plan changed by Sentinel" if view and view.status == "auto" else "Recommendation"
        return Row(at, EVENT, f"{what}: {where}", recommendation_words(project, event.seq))
    if event.type == "decision":
        verdict = VERDICTS.get(payload.get("verdict", ""), str(payload.get("verdict")))
        if payload.get("discarded"):
            verdict += ", not applied: the project had changed"
        words = recommendation_words(project, int(payload["recommendation"]))
        return Row(at, EVENT, f"Decision ({verdict}): {where}", words)
    if event.type == "undo":
        return Row(at, EVENT, f"Automatic change undone: {where}")
    if event.type == "explanation":
        valid = payload.get("explanation", {}).get("valid")
        return Row(at, EVENT, f"AI explanation: {where}", "shown" if valid else "failed")
    if event.type == "simulator":
        spec = payload.get("spec", {})
        policy = POLICIES.get(spec.get("policy", ""), spec.get("policy", ""))
        details = f"{spec.get('instance', '')}, {spec.get('disruptions', '')} disruptions, {policy}"
        return Row(at, EVENT, f"Simulation created: {where}", details)
    if event.type == "advance":
        return Row(at, EVENT, f"Simulation advanced: {where}", f"{payload.get('days')} days")
    return None


def side_words(side: dict[str, Any]) -> str:
    policy = POLICIES.get(side.get("policy", ""), side.get("policy", ""))
    text = f"{policy}: finish {day(side['finish']) if side.get('finish') else 'none'}"
    if side.get("late_days"):
        text += f", {side['late_days']} working days late"
    elif side.get("on_time"):
        text += ", on time"
    return text + f", cost {share(side.get('cost_ratio'))} of the budget"


def job_row(job: sqlite3.Row, labels: dict[str, str]) -> Row | None:
    where = labels.get(job["project"] or "", "")
    suffix = f": {where}" if where else ""
    finished = stamp(job["finished"]) if job["finished"] else None
    if job["status"] == "failed":
        error = json.loads(job["error"] or "{}").get("code", "unknown")
        return Row(finished or stamp(job["created"]), JOB, f"Job failed{suffix}", error)
    if job["status"] != "done" or finished is None:
        return None
    result = json.loads(job["result"] or "{}")
    if job["kind"] == "forecast" and result.get("p50"):
        details = f"chance {percent(result.get('p_on_time'))}, most likely finish "
        details += f"{day(result['p50'])}, bad case {day(result['p90'])}"
        details += f" (status as of {day(result['as_of'])})"
        return Row(finished, JOB, f"Forecast ready{suffix}", details)
    if job["kind"] == "advance" and result.get("finished"):
        sides = [result["main"], *([result["compare"]] if result.get("compare") else [])]
        return Row(finished, JOB, f"Simulation finished{suffix}", "; ".join(map(side_words, sides)))
    if job["kind"] in ("message", "extract"):
        return Row(
            finished, JOB, f"The AI read the {'message' if job['kind'] == 'message' else 'text'}"
        )
    return None


def request_row(request: Request, labels: dict[str, str]) -> Row | None:
    """A page opened or a form sent; the parts a page loads only when they failed."""
    if request.partial and request.method == "GET" and request.status < 400:
        return None
    words = PAGES.get((request.method, request.path))
    if words is None:
        words = f"{request.method} {request.path or '(no such page)'}"
    where = labels.get(request.project or "", "a deleted project" if request.project else "")
    what = f"Opened {words}" if request.method == "GET" else words[0].upper() + words[1:]
    what += f" ({where})" if where else ""
    rank = PAGE if request.method == "GET" else ACTION
    if request.status >= 500:
        return Row(request.at, rank, what, f"server error ({request.status})")
    if request.status >= 400:
        return Row(request.at, rank, what, f"refused ({request.status})")
    return Row(request.at, rank, what)


# ---- the tasks


def first_after(times: Sequence[datetime], after: datetime | None) -> datetime | None:
    return next((t for t in sorted(times) if after is None or t > after), None)


def milestones(sandbox: Sandbox, project: Project | None) -> list[datetime | None]:
    """The ends of tasks 1, 3, 4 and 5: the plan, the saved status report, the decision
    (approved or rejected) and the end of a simulation, each the first after the last reached."""
    events = project.events if project is not None else []
    plan = first_after([e.created for e in events if e.type == "baseline"], None)
    checkin = first_after([e.created for e in events if e.type == "checkin"], plan)
    verdicts = ("approve", "reject")
    decided = [
        e.created for e in events if e.type == "decision" and e.payload.get("verdict") in verdicts
    ]
    decision = first_after(decided, checkin or plan)
    ends = [
        stamp(j["finished"])
        for j in sandbox.jobs
        if j["kind"] == "advance"
        and j["status"] == "done"
        and json.loads(j["result"] or "{}").get("finished")
    ]
    return [plan, checkin, decision, first_after(ends, decision or checkin or plan)]


def task_table(sandbox: Sandbox, project: Project | None, zone: tzinfo) -> list[str]:
    lines = [
        "| Task | From | To | Duration | Page requests | Refused forms |",
        "| --- | --- | --- | ---: | ---: | ---: |",
    ]
    begin, begin_name = sandbox.created, "the first request"
    for (number, name, end_name), end in zip(TASKS, milestones(sandbox, project), strict=True):
        start = f"{begin_name} {clock(begin, zone)}"
        if end is None:
            lines.append(f"| {number}. {name} | {start} | {end_name}: not reached | – | – | – |")
            continue
        pages = refused = "–"
        if sandbox.requests is not None:
            inside = [
                r
                for r in sandbox.requests
                if (begin <= r.at if number == 1 else begin < r.at) and r.at <= end
            ]
            pages, refused = str(sum(r.page for r in inside)), str(sum(r.refused for r in inside))
        seconds = duration((end - begin).total_seconds())
        lines.append(
            f"| {number}. {name} | {start} | {end_name} {clock(end, zone)} | {seconds} | "
            f"{pages} | {refused} |"
        )
        begin, begin_name = end, end_name
    return lines


def clock(moment: datetime, zone: tzinfo) -> str:
    return moment.astimezone(zone).strftime("%H:%M:%S")


# ---- the document


def timeline(sandbox: Sandbox, zone: tzinfo) -> list[str]:
    """The sandbox's rows in time order; rows repeated one after another are counted once."""
    labels = {p.id: p.label for p in sandbox.projects}
    rows = [Row(sandbox.created, ACTION, "First request: the sandbox starts")]
    for project in sandbox.projects:
        rows += event_rows(project)
    rows += [r for job in sandbox.jobs if (r := job_row(job, labels)) is not None]
    for request in sandbox.requests or []:
        if (row := request_row(request, labels)) is not None:
            rows.append(row)
    rows.sort(key=lambda r: (r.at, r.rank))
    merged: list[tuple[datetime, str, str, int]] = []
    for row in rows:
        local = row.at.astimezone(zone)
        if (
            merged
            and merged[-1][1:3] == (row.what, row.details)
            and merged[-1][0].date() == local.date()
        ):
            merged[-1] = (*merged[-1][:3], merged[-1][3] + 1)
        else:
            merged.append((local, row.what, row.details, 1))
    lines = ["| Time | What | Details |", "| --- | --- | --- |"]
    shown: date | None = None
    for local, what, details, count in merged:
        if local.date() != shown:
            shown = local.date()
            lines.append(f"| **{day(shown)}** | | |")
        times = f" (×{count})" if count > 1 else ""
        lines.append(f"| {local:%H:%M:%S} | {cell(what)}{times} | {cell(details)} |")
    return lines


def cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def sandbox_section(sandbox: Sandbox, number: int, total: int, code: str, zone: tzinfo) -> str:
    project = main_project(sandbox, code)
    local = sandbox.created.astimezone(zone)
    listed = [
        f"{p.label} ({p.kind}, {len(p.events) - p.seeded} events of the tester)"
        for p in sandbox.projects
    ]
    lines = [
        f"## Sandbox {number} of {total}: started {day(local.date())}, {local:%H:%M:%S}",
        "",
        "Projects: " + "; ".join(listed) + ".",
    ]
    if project is not None:
        lines.append(f"The tasks are measured on {project.label}.")
    if sandbox.requests is None:
        lines.append("The demo kept no request log: no page requests and no refused forms.")
    lines += [
        "",
        "### Durations of the tasks",
        "",
        *task_table(sandbox, project, zone),
        "",
        "Each task runs from the end of the one before. Task 2 leaves no trace: its time is in "
        "task 3. Page requests are the pages opened (not the parts a page loads by itself); "
        "refused forms are those the app answered with an error or a question to confirm.",
        "",
        "### Timeline",
        "",
        *timeline(sandbox, zone),
        "",
    ]
    return "\n".join(lines)


def export(database: Path, code: str, zone: tzinfo, language: Language = "pl") -> str | None:
    """The Markdown log of the tester `code`, or None if no sandbox holds their project."""
    with connect(database) as db:
        sandboxes = find_sandboxes(db, code)
    if not sandboxes:
        return None
    for sandbox in sandboxes:
        prepare(sandbox, language)
    try:
        release = version("sentinel")
    except PackageNotFoundError:  # pragma: no cover - the script runs in the project
        release = "unknown"
    header = [
        f"# Usability test log {code}",
        "",
        f"Exported by `scripts/usability_logs.py` (Sentinel {release}) from the demo's database; "
        f"wall-clock times in {datetime.now(zone):%Z (UTC%z)}. No address, cookie, key or id.",
        "",
    ]
    total = len(sandboxes)
    sections = [sandbox_section(s, i, total, code, zone) for i, s in enumerate(sandboxes, 1)]
    return "\n".join(header + sections)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The owner's log of one usability tester.")
    parser.add_argument("--data-dir", type=Path, required=True, help="the demo's data directory")
    parser.add_argument("--code", required=True, help="the tester's code, e.g. P1")
    parser.add_argument("--out", type=Path, default=OUT, help="the folder of the logs")
    parser.add_argument("--language", choices=("pl", "en"), default="pl", help="of the app's texts")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,16}", args.code):
        parser.error("the code is a short word such as P1")
    zone = datetime.now().astimezone().tzinfo
    assert zone is not None
    text = export(args.data_dir.expanduser() / "sentinel.db", args.code, zone, args.language)
    if text is None:
        print(f"No demo sandbox holds a project whose name starts with {args.code}.")
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    target = args.out / f"{args.code}.md"
    target.write_text(text, "utf-8")
    print(f"Wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
