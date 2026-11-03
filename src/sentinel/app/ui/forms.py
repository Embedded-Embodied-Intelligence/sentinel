"""Reading the forms of the pages (WP9b): the project's basics, team and tasks, the check-in and
the project settings, with plain-language messages for every field the manager got wrong.

The functions are pure (a `Form` in, a definition, a check-in or the field errors out), so the
validation is tested without HTTP. Field errors are message keys of the catalogue (`ui/text.py`)
with their parameters; the project's own issues come from `live.validate_definition`.
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

from starlette.datastructures import FormData
from starlette.requests import Request

from sentinel.app.models import (
    MAX_DAYS_OFF,
    AbsenceReport,
    CheckIn,
    NewTaskReport,
    Person,
    ProjectDefinition,
    RoleCost,
    Settings,
    Task,
    TaskReport,
    WorkIncreaseReport,
)

ESTIMATIONS = ("confident", "typical", "uncertain")
DISRUPTIONS = ("calm", "typical", "turbulent")
MAX_ROWS = 200
PASTE_SPLIT = re.compile(r"\s*[,;\t]\s*")


@dataclass(frozen=True)
class FieldError:
    """A field the manager has to correct: the field's name and a message key with values."""

    name: str
    key: str
    values: Mapping[str, object] = field(default_factory=dict)


class Form:
    """A submitted form: single values, lists and checkboxes."""

    def __init__(self, data: FormData | Mapping[str, str | list[str]]) -> None:
        self._data: dict[str, list[str]] = {}
        if isinstance(data, FormData):
            for key, item in data.multi_items():
                if isinstance(item, str):
                    self._data.setdefault(key, []).append(item)
        else:
            for key, value in data.items():
                self._data[key] = [value] if isinstance(value, str) else list(value)

    @classmethod
    async def read(cls, request: Request) -> "Form":
        return cls(await request.form())

    def get(self, name: str, default: str = "") -> str:
        values = self._data.get(name)
        return values[0] if values else default

    def getlist(self, name: str) -> list[str]:
        return list(self._data.get(name, []))[:MAX_ROWS]

    def flag(self, name: str) -> bool:
        return self.get(name) in ("on", "1", "true", "yes")

    def names(self) -> list[str]:
        return list(self._data)


def text_of(form: Form, name: str, limit: int = 120) -> str:
    return " ".join(form.get(name).split())[:limit]


def parse_date(text: str) -> date | None:
    """A date of an `<input type="date">` (ISO), None if empty or invalid."""
    try:
        return date.fromisoformat(text.strip()) if text.strip() else None
    except ValueError:
        return None


def parse_int(text: str) -> int | None:
    try:
        return int(text.strip())
    except ValueError:
        return None


def parse_number(text: str) -> float | None:
    """A number written with a dot or a decimal comma, None if it is not one."""
    cleaned = text.strip().replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return value if value == value and abs(value) != float("inf") else None


# --------------------------------------------------------------------------- basics (step 1)


@dataclass
class Basics:
    """The first step of a new project: name, dates, budget and the two presets."""

    name: str = ""
    start: date | None = None
    deadline: date | None = None
    budget: float | None = None
    estimation: str = "typical"
    disruptions: str = "typical"
    errors: list[FieldError] = field(default_factory=list)


def read_basics(form: Form) -> Basics:
    basics = Basics(
        name=text_of(form, "name"),
        estimation=form.get("estimation", "typical"),
        disruptions=form.get("disruptions", "typical"),
    )
    errors = basics.errors
    if not basics.name:
        errors.append(FieldError("name", "form.name_required"))
    start_text, deadline_text = form.get("start"), form.get("deadline")
    basics.start = parse_date(start_text)
    if basics.start is None:
        errors.append(FieldError("start", "form.start_required"))
    basics.deadline = parse_date(deadline_text)
    if deadline_text.strip() and basics.deadline is None:
        errors.append(FieldError("deadline", "form.date_invalid"))
    elif basics.start and basics.deadline and basics.deadline < basics.start:
        errors.append(FieldError("deadline", "form.deadline_before_start"))
    budget_text = form.get("budget")
    if budget_text.strip():
        basics.budget = parse_number(budget_text)
        if basics.budget is None or basics.budget <= 0:
            basics.budget = None
            errors.append(FieldError("budget", "form.budget_positive"))
    if basics.estimation not in ESTIMATIONS:
        basics.estimation = "typical"
    if basics.disruptions not in DISRUPTIONS:
        basics.disruptions = "typical"
    return basics


def apply_basics(definition: ProjectDefinition | None, basics: Basics) -> ProjectDefinition:
    """A definition with the basics of step 1 (a new one, or `definition` changed)."""
    assert basics.start is not None
    settings = Settings() if definition is None else definition.settings
    settings = settings.model_copy(
        update={"estimation": basics.estimation, "disruptions": basics.disruptions}
    )
    values = {
        "name": basics.name,
        "start": basics.start,
        "deadline": basics.deadline,
        "budget": basics.budget,
        "settings": settings,
    }
    if definition is None:
        return ProjectDefinition.model_validate(values)
    return definition.model_copy(update=values)


# --------------------------------------------------------------------------- team (step 2)


def next_key(prefix: str, used: Iterable[str]) -> str:
    """The first free key prefix1, prefix2, ..."""
    taken = set(used)
    number = 1
    while f"{prefix}{number}" in taken:
        number += 1
    return f"{prefix}{number}"


def read_team(form: Form) -> list[Person]:
    """The team table: a row per person (name and role); empty rows are dropped."""
    people: list[Person] = []
    keys = form.getlist("person_key")
    names = form.getlist("person_name")
    roles = form.getlist("person_role")
    for key, name, role in zip(keys, names, roles, strict=False):
        name, role = " ".join(name.split())[:120], " ".join(role.split())[:120]
        if not name and not role:
            continue
        valid = re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,39}", key)
        if not valid or key in {p.key for p in people}:
            key = next_key("P", [p.key for p in people] + keys)
        people.append(Person(key=key, name=name, role=role))
    return people


def pasted_people(text: str, team: Sequence[Person]) -> list[Person]:
    """People pasted as lines "Name, role" (comma, semicolon or tab), appended to `team`."""
    people = list(team)
    for line in text.splitlines()[:MAX_ROWS]:
        parts = [p for p in PASTE_SPLIT.split(line.strip(), maxsplit=1) if p]
        if not parts:
            continue
        name = " ".join(parts[0].split())[:120]
        role = " ".join(parts[1].split())[:120] if len(parts) > 1 else ""
        people.append(Person(key=next_key("P", [p.key for p in people]), name=name, role=role))
    return people


def read_role_costs(
    form: Form, roles: Sequence[str], current: Sequence[RoleCost]
) -> tuple[RoleCost, ...]:
    """The daily costs of the team step, by role in the order shown: a cost left empty or not a
    number stays as it was; the default 1 is not stored (spec section 11.2)."""
    from sentinel.app.live import role_key

    known = {role_key(c.role): c.daily_cost for c in current}
    costs = []
    for k, role in enumerate(roles):
        value = parse_number(form.get(f"cost_{k}"))
        cost = value if value is not None and value >= 0 else known.get(role_key(role), 1.0)
        if cost != 1.0:
            costs.append(RoleCost(role=role, daily_cost=cost))
    return tuple(costs)


# --------------------------------------------------------------------------- tasks (step 3)


@dataclass
class TaskRows:
    """The task table: the tasks as entered and the cells that are not numbers."""

    tasks: list[Task]
    errors: list[FieldError] = field(default_factory=list)


def read_tasks(form: Form, roles: Sequence[str]) -> TaskRows:
    """The task table: name, days, people per role, the tasks it comes after, optional."""
    tasks: list[Task] = []
    errors: list[FieldError] = []
    keys = form.getlist("task_key")
    names = form.getlist("task_name")
    days = form.getlist("task_days")
    seen: set[str] = set()
    for i, key in enumerate(keys):
        name = " ".join((names[i] if i < len(names) else "").split())[:120]
        days_text = days[i] if i < len(days) else ""
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,39}", key) or key in seen:
            continue
        seen.add(key)
        crew_values = {k: form.get(f"crew_{key}_{k}") for k in range(len(roles))}
        if not name and not days_text.strip() and not any(v.strip() for v in crew_values.values()):
            continue  # an empty row
        duration = parse_int(days_text)
        if duration is None:
            errors.append(FieldError(f"task_days_{key}", "form.days_number", {"task": name or key}))
            duration = 0
        crew: dict[str, int] = {}
        for k, role in enumerate(roles):
            text = crew_values[k].strip()
            if not text:
                continue
            count = parse_int(text)
            if count is None or count < 0:
                errors.append(
                    FieldError(f"crew_{key}_{k}", "form.people_number", {"task": name or key})
                )
            elif count > 0:
                crew[role] = count
        # A role outside the team (from a description or a spreadsheet) stays in the crew until
        # the manager changes it, so that the definition's check names it (spec section 11.2).
        counts = form.getlist(f"other_count_{key}")
        for role, text in zip(form.getlist(f"other_role_{key}"), counts, strict=False):
            count = parse_int(text) if text.strip() else 0
            if count is None or count < 0:
                errors.append(
                    FieldError(f"other_count_{key}", "form.people_number", {"task": name or key})
                )
            elif count > 0:
                crew[role] = count
        after, bad = after_keys(form.get(f"after_{key}"), keys, i)
        if bad:
            errors.append(FieldError(f"after_{key}", "form.after_numbers", {"task": name or key}))
        optional = form.flag(f"optional_{key}")
        tasks.append(
            Task(
                key=key,
                name=name,
                duration=duration,
                crew=crew,
                predecessors=after,
                optional=optional,
            )
        )
    known = {t.key for t in tasks}
    tasks = [
        t.model_copy(update={"predecessors": tuple(p for p in t.predecessors if p in known)})
        for t in tasks
    ]
    return TaskRows(tasks, errors)


def after_keys(text: str, keys: Sequence[str], row: int) -> tuple[tuple[str, ...], bool]:
    """The tasks a row comes after, written as row numbers ("1, 3"), and whether a number is
    not that of another row."""
    found: list[str] = []
    bad = False
    for part in re.split(r"[^0-9]+", text):
        if not part:
            continue
        number = int(part)
        if 1 <= number <= len(keys) and number - 1 != row:
            if keys[number - 1] not in found:
                found.append(keys[number - 1])
        else:
            bad = True
    bad = bad or bool(re.search(r"[^0-9,;\s]", text))
    return tuple(found), bad


def team_roles(team: Sequence[Person]) -> list[str]:
    """The roles of a team in the order of their first person (spec section 11.2), each named as
    it was first written; case, spacing and a final plural "s" are ignored when matching."""
    from sentinel.app.live import role_key

    roles: dict[str, str] = {}
    for person in team:
        if person.role.strip():
            roles.setdefault(role_key(person.role), person.role)
    return list(roles.values())


# --------------------------------------------------------------------------- check-in


@dataclass
class CheckinForm:
    """A check-in as entered: the report and the fields that need a correction."""

    checkin: CheckIn | None
    errors: list[FieldError] = field(default_factory=list)


def read_checkin(form: Form, current: Mapping[str, tuple[str, float | None]]) -> CheckinForm:
    """The check-in form: its date, the status of the tasks shown (only changes are reported),
    absences, work increases, new tasks and the events confirmed from a message. `current` is
    the state ("not_started", "in_progress" or "done") and the percentage of every task."""
    errors: list[FieldError] = []
    when = parse_date(form.get("date"))
    if when is None:
        errors.append(FieldError("date", "form.checkin_date"))
    reports: list[TaskReport] = []
    for key in form.getlist("shown"):
        if key not in current:
            continue
        state, percent_now = current[key]
        status = form.get(f"status_{key}", state)
        if status not in ("not_started", "in_progress", "done"):
            continue
        start = parse_date(form.get(f"start_{key}"))
        crew = tuple(form.getlist(f"crew_{key}")) or None
        if status == "not_started":
            continue
        if status == "in_progress":
            percent = parse_number(form.get(f"percent_{key}", "0"))
            if percent is None or not 0 <= percent < 100:
                errors.append(FieldError(f"percent_{key}", "form.percent_range"))
                continue
            unchanged = percent_now is not None and abs(percent - percent_now) < 0.05
            if state == "in_progress" and start is None and crew is None and unchanged:
                continue
            reports.append(
                TaskReport(task=key, status="in_progress", percent=percent, start=start, crew=crew)
            )
        else:
            finish = parse_date(form.get(f"finish_{key}"))
            if finish is None:
                errors.append(FieldError(f"finish_{key}", "form.finish_required"))
                continue
            reports.append(
                TaskReport(task=key, status="done", finish=finish, start=start, crew=crew)
            )
    absences: list[AbsenceReport] = []
    for i in form.getlist("away_rows"):
        person = form.get(f"away_{i}_person")
        first = parse_date(form.get(f"away_{i}_from"))
        back_text = form.get(f"away_{i}_back")
        back = parse_date(back_text)
        if not person:
            continue
        if first is None:
            errors.append(FieldError(f"away_{i}_from", "form.away_from"))
            continue
        if back_text.strip() and back is None:
            errors.append(FieldError(f"away_{i}_back", "form.date_invalid"))
            continue
        absences.append(AbsenceReport(person=person, first_day=first, return_date=back))
    increases: list[WorkIncreaseReport] = []
    for i in form.getlist("grow_rows"):
        task = form.get(f"grow_{i}_task")
        days_text = form.get(f"grow_{i}_days")
        if not task:
            continue
        extra = parse_number(days_text)
        if extra is None or extra <= 0:
            errors.append(FieldError(f"grow_{i}_days", "form.extra_days"))
            continue
        increases.append(WorkIncreaseReport(task=task, extra_days=extra))
    new_tasks: list[NewTaskReport] = []
    for i in form.getlist("new_rows"):
        name = text_of(form, f"new_{i}_name")
        days_text = form.get(f"new_{i}_days")
        if not name and not days_text.strip():
            continue
        duration = parse_int(days_text)
        if not name:
            errors.append(FieldError(f"new_{i}_name", "form.task_name"))
            continue
        if duration is None or duration < 1:
            errors.append(FieldError(f"new_{i}_days", "form.days_number", {"task": name}))
            continue
        needs: dict[str, int] = {}
        for role_field in form.names():
            prefix = f"new_{i}_crew_"
            if role_field.startswith(prefix):
                count = parse_int(form.get(role_field))
                role = form.get(f"new_{i}_role_{role_field[len(prefix) :]}")
                if count is not None and count > 0 and role:
                    needs[role] = count
        new_tasks.append(
            NewTaskReport(
                name=name,
                duration=duration,
                crew=needs,
                after=form.get(f"new_{i}_after") or None,
                before=form.get(f"new_{i}_before") or None,
                optional=form.flag(f"new_{i}_optional"),
            )
        )
    for value in form.getlist("msg_absence"):
        absences.append(AbsenceReport.model_validate_json(value))
    for value in form.getlist("msg_increase"):
        increases.append(WorkIncreaseReport.model_validate_json(value))
    for value in form.getlist("msg_new"):
        new_tasks.append(NewTaskReport.model_validate_json(value))
    if errors or when is None:
        return CheckinForm(None, errors)
    checkin = CheckIn(
        date=when,
        tasks=tuple(reports),
        absences=tuple(absences),
        increases=tuple(increases),
        new_tasks=tuple(new_tasks),
    )
    return CheckinForm(checkin, errors)


# --------------------------------------------------------------------------- project settings


@dataclass
class SettingsForm:
    definition: ProjectDefinition | None
    errors: list[FieldError] = field(default_factory=list)


def read_settings(form: Form, definition: ProjectDefinition, roles: Sequence[str]) -> SettingsForm:
    """The project settings: name, deadline, budget, autonomy, presets, daily costs per role and
    the optional AI features."""
    errors: list[FieldError] = []
    name = text_of(form, "name")
    if not name:
        errors.append(FieldError("name", "form.name_required"))
    deadline_text = form.get("deadline")
    deadline = parse_date(deadline_text)
    if deadline_text.strip() and deadline is None:
        errors.append(FieldError("deadline", "form.date_invalid"))
    elif deadline is not None and deadline < definition.start:
        errors.append(FieldError("deadline", "form.deadline_before_start"))
    budget = None
    if form.get("budget").strip():
        budget = parse_number(form.get("budget"))
        if budget is None or budget <= 0:
            errors.append(FieldError("budget", "form.budget_positive"))
            budget = None
    autonomy = parse_int(form.get("autonomy", "2"))
    if autonomy is None or not 0 <= autonomy <= 3:
        errors.append(FieldError("autonomy", "form.autonomy"))
        autonomy = definition.settings.autonomy
    estimation = form.get("estimation", definition.settings.estimation)
    disruptions = form.get("disruptions", definition.settings.disruptions)
    days_off = list(definition.settings.days_off)
    if "days_off" in form.names():  # the calendar's fields (spec section 11.1, v2.2.0)
        days_off = []
        for word in re.split(r"[\s,;]+", form.get("days_off").strip()):
            if not word:
                continue
            day = parse_date(word)
            if day is None:
                errors.append(FieldError("days_off", "form.days_off_invalid", {"value": word}))
                break
            days_off.append(day)
    holidays = definition.settings.holidays
    if "calendar_shown" in form.names():
        holidays = "pl" if form.flag("holidays") else "none"
    costs: list[RoleCost] = []
    for k, role in enumerate(roles):
        text = form.get(f"cost_{k}").strip()
        if not text:
            continue
        value = parse_number(text)
        if value is None or value < 0:
            errors.append(FieldError(f"cost_{k}", "form.cost", {"role": role}))
        elif value != 1.0:
            costs.append(RoleCost(role=role, daily_cost=value))
    if errors:
        return SettingsForm(None, errors)
    settings = definition.settings.model_copy(
        update={
            "autonomy": autonomy,
            "estimation": estimation if estimation in ESTIMATIONS else "typical",
            "disruptions": disruptions if disruptions in DISRUPTIONS else "typical",
            "llm_explanations": form.flag("llm_explanations"),
            "llm_proposals": form.flag("llm_proposals"),
            "holidays": holidays,
            "days_off": tuple(sorted(set(days_off)))[:MAX_DAYS_OFF],
        }
    )
    changed = definition.model_copy(
        update={
            "name": name,
            "deadline": deadline,
            "budget": budget,
            "roles": tuple(costs),
            "settings": settings,
        }
    )
    return SettingsForm(changed, errors)
