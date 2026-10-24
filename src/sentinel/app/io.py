"""Import and export of live projects (WP9a): CSV templates for tasks and the team, the JSON
export of a whole project (its event log) and the plan as CSV.

Tasks CSV, one row per task (a header row first; comma, semicolon or tab separated; UTF-8):

| column | meaning |
| --- | --- |
| `id` | short id of the task (letters, digits, `_`, `-`, `.`); optional, default T1, T2, ... |
| `name` | task name (required, unique) |
| `duration_days` | estimated duration in working days (whole number, at least 1) |
| `predecessors` | ids of the tasks it waits for, separated by spaces, commas or semicolons |
| `optional` | yes/no (also true/false, 1/0, tak/nie): may the task be dropped |
| `crew:<role>` | people of that role the task needs, one column per role (e.g. `crew:Tester`) |
| `crew` | instead of the `crew:` columns: `Backend developer=2; Tester=1` |

Team CSV: `name` and `role` per person, optionally `id` (default P1, P2, ...). Every problem is
reported with its row number (the header is row 1) in the user's language.
"""

import csv
import io
import re
from collections.abc import Sequence
from datetime import date
from typing import Any

from pydantic import ValidationError

from sentinel.app.calendar import WorkCalendar
from sentinel.app.errors import AppError
from sentinel.app.events import Created
from sentinel.app.live import Issue, LiveProject, issue
from sentinel.app.models import Person, ProjectDefinition, Settings, Task
from sentinel.app.store import EventRow

EXPORT_FORMAT = "sentinel-project"
EXPORT_VERSION = 1
TASK_COLUMNS = ("id", "name", "duration_days", "predecessors", "optional")
TEAM_COLUMNS = ("id", "name", "role")
KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,39}$")
YES = {"yes", "y", "true", "1", "tak", "t", "x"}
NO = {"no", "n", "false", "0", "nie", ""}
MAX_TEXT = 120

TASKS_TEMPLATE = (
    "id,name,duration_days,predecessors,optional,crew:Backend developer,crew:Tester\n"
    "T1,Design the payment API,3,,no,1,0\n"
    "T2,Build the payment API,5,T1,no,2,0\n"
    "T3,Test the payment API,2,T2,no,0,1\n"
)
TEAM_TEMPLATE = "id,name,role\nP1,Ada,Backend developer\nP2,Ben,Backend developer\nP3,Cleo,Tester\n"


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AppError("csv_encoding") from exc


def _rows(data: bytes) -> tuple[list[str], list[dict[str, str]]]:
    """Header (stripped) and rows of a CSV file with a sniffed separator."""
    text = _decode(data)
    if not text.strip():
        raise AppError("csv_empty")
    first = text.splitlines()[0]
    separator = max((",", ";", "\t"), key=first.count)
    reader = csv.reader(io.StringIO(text), delimiter=separator)
    lines = [row for row in reader]
    header = [cell.strip() for cell in lines[0]]
    rows: list[dict[str, str]] = []
    for line in lines[1:]:
        if not any(cell.strip() for cell in line):
            rows.append({})
            continue
        rows.append(
            {name: (line[i].strip() if i < len(line) else "") for i, name in enumerate(header)}
        )
    return header, rows


def _lower(header: Sequence[str]) -> dict[str, str]:
    return {name.casefold(): name for name in header}


def parse_team(data: bytes) -> tuple[list[Person], list[Issue]]:
    """The people of a team CSV and the problems of its rows."""
    header, rows = _rows(data)
    columns = _lower(header)
    found: list[Issue] = []
    for required in ("name", "role"):
        if required not in columns:
            found.append(issue("csv_missing_column", column=required))
    if found:
        return [], found
    people: list[Person] = []
    for i, row in enumerate(rows):
        number = i + 2
        if not row:
            continue
        name = row.get(columns["name"], "")
        role = row.get(columns["role"], "")
        key = row.get(columns["id"], "") if "id" in columns else ""
        key = key or f"P{len(people) + 1}"
        problems = _text_issues(number, {"name": name, "role": role})
        if not KEY.match(key):
            problems.append(issue("csv_key", f"row {number}", row=number, value=key))
        if problems:
            found += problems
            continue
        people.append(Person(key=key, name=name, role=role))
    return people, found


def parse_tasks(data: bytes) -> tuple[list[Task], list[Issue]]:
    """The tasks of a tasks CSV and the problems of its rows."""
    header, rows = _rows(data)
    columns = _lower(header)
    found: list[Issue] = []
    for required in ("name", "duration_days"):
        if required not in columns:
            found.append(issue("csv_missing_column", column=required))
    if found:
        return [], found
    crew_columns = {
        name: name.split(":", 1)[1].strip()
        for name in header
        if name.casefold().startswith("crew:") and name.split(":", 1)[1].strip()
    }
    tasks = []
    for i, row in enumerate(rows):
        number = i + 2
        if not row:
            continue
        where = f"row {number}"
        problems: list[Issue] = []
        name = row.get(columns["name"], "")
        problems += _text_issues(number, {"name": name})
        key = (row.get(columns["id"], "") if "id" in columns else "") or f"T{i + 1}"
        if not KEY.match(key):
            problems.append(issue("csv_key", where, row=number, value=key))
        raw_duration = row.get(columns["duration_days"], "")
        duration = _integer(raw_duration)
        if duration is None:
            problems.append(
                issue("csv_number", where, row=number, column="duration_days", value=raw_duration)
            )
        crew: dict[str, int] = {}
        for column, role in crew_columns.items():
            value = row.get(column, "")
            if not value:
                continue
            count = _integer(value)
            if count is None:
                problems.append(issue("csv_number", where, row=number, column=column, value=value))
            elif count:
                crew[role] = count
        if "crew" in columns and row.get(columns["crew"], ""):
            parsed = _crew(row[columns["crew"]])
            if parsed is None:
                problems.append(issue("csv_crew", where, row=number, value=row[columns["crew"]]))
            else:
                crew.update(parsed)
        predecessors: tuple[str, ...] = ()
        if "predecessors" in columns:
            predecessors = tuple(p for p in re.split(r"[\s,;]+", row[columns["predecessors"]]) if p)
        optional = False
        if "optional" in columns:
            flag = row[columns["optional"]].casefold()
            if flag in YES:
                optional = True
            elif flag not in NO:
                problems.append(
                    issue(
                        "csv_flag",
                        where,
                        row=number,
                        column="optional",
                        value=row[columns["optional"]],
                    )
                )
        if problems:
            found += problems
            continue
        assert duration is not None
        tasks.append(
            Task(
                key=key,
                name=name,
                duration=duration,
                crew=crew,
                predecessors=predecessors,
                optional=optional,
            )
        )
    return tasks, found


def _text_issues(number: int, values: dict[str, str]) -> list[Issue]:
    found = []
    for column, value in values.items():
        if not value:
            found.append(issue("csv_required", f"row {number}", row=number, column=column))
        elif len(value) > MAX_TEXT:
            found.append(issue("csv_too_long", f"row {number}", row=number, column=column))
    return found


def _integer(text: str) -> int | None:
    try:
        value = float(text.replace(",", "."))
    except ValueError:
        return None
    return int(value) if value.is_integer() else None


def _crew(text: str) -> dict[str, int] | None:
    """`Role=2; Role 2=1` (also with commas) as a crew, None if malformed."""
    crew: dict[str, int] = {}
    for part in re.split(r"[;,]", text):
        if not part.strip():
            continue
        if "=" not in part:
            return None
        role, _, count = part.partition("=")
        number = _integer(count.strip())
        if not role.strip() or number is None or number < 0:
            return None
        if number:
            crew[role.strip()] = number
    return crew


def definition_from_csv(
    tasks_csv: bytes,
    team_csv: bytes | None,
    *,
    name: str,
    start: date,
    deadline: date | None = None,
    budget: float | None = None,
    settings: Settings | None = None,
) -> ProjectDefinition:
    """A definition from a tasks CSV and an optional team CSV; AppError lists every row's
    problems."""
    tasks, found = parse_tasks(tasks_csv)
    people: list[Person] = []
    if team_csv is not None:
        people, team_issues = parse_team(team_csv)
        found += team_issues
    if found:
        raise AppError(found[0].code, "invalid", found, **found[0].values)
    return ProjectDefinition(
        name=name,
        start=start,
        deadline=deadline,
        budget=budget,
        team=tuple(people),
        tasks=tuple(tasks),
        settings=settings or Settings(),
    )


def export_project(kind: str, name: str, rows: Sequence[EventRow]) -> dict[str, Any]:
    """The JSON export of a whole project: its event log."""
    return {
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "kind": kind,
        "name": name,
        "events": [{"type": row.type, "payload": row.payload} for row in rows],
    }


def read_export(data: Any) -> tuple[str, str, list[tuple[str, dict[str, Any]]]]:
    """(kind, name, events) of an export, or AppError json_invalid."""
    if not isinstance(data, dict) or data.get("format") != EXPORT_FORMAT:
        raise AppError("json_invalid", detail="not a Sentinel project export")
    if data.get("version") != EXPORT_VERSION:
        raise AppError("json_invalid", detail=f"unknown version {data.get('version')!r}")
    kind = data.get("kind")
    events = data.get("events")
    if kind not in ("live", "simulator") or not isinstance(events, list) or not events:
        raise AppError("json_invalid", detail="no events")
    parsed = []
    for event in events:
        if not isinstance(event, dict) or not isinstance(event.get("payload"), dict):
            raise AppError("json_invalid", detail="an event is not an object")
        parsed.append((str(event.get("type")), event["payload"]))
    name = data.get("name")
    if kind == "live":
        try:
            first = Created.model_validate(parsed[0][1])
        except ValidationError as exc:
            raise AppError("json_invalid", detail="the first event is not a project") from exc
        name = name or first.definition.name
    return str(kind), str(name or "project"), parsed


def plan_csv(project: LiveProject, names: dict[str, str]) -> str:
    """The plan and the progress of every task as CSV (dates ISO 8601)."""
    calendar: WorkCalendar = project.calendar
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(
        [
            "id",
            "name",
            "status",
            "planned_start",
            "planned_finish",
            "start",
            "finish",
            "work_done_days",
            "crew",
        ]
    )
    nodes = project.nodes()
    for key, tracked in project.tasks.items():
        node = nodes[key]
        planned = tracked.planned if tracked.state == "unstarted" else None
        writer.writerow(
            [
                key,
                node.name,
                tracked.state,
                "" if planned is None else calendar.date_of(planned).isoformat(),
                ""
                if planned is None
                else calendar.finish_date(planned + node.duration).isoformat(),
                "" if tracked.start is None else calendar.date_of(tracked.start).isoformat(),
                "" if tracked.finish is None else calendar.finish_date(tracked.finish).isoformat(),
                f"{tracked.work / node.unit:g}",
                " ".join(names.get(member, member) for member in tracked.crew),
            ]
        )
    return out.getvalue()
