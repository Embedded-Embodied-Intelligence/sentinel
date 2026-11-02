"""Exploratory QA of the application through the browser (WP10; docs/qa/raport-qa-pl.md).

Starts `sentinel ui` on a fresh data directory and drives it with Playwright as a manager would:
every action goes through the page; the driver only reads the project's JSON from the same browser
session to know what its simulated team has done. It saves a screenshot at every step and a log
of what the pages showed. The team's real durations come from a seeded generator, so a run can be
repeated. About 2 minutes for run 1, 5 for run 2 and 5 for the wrong-use cases on the server.

    uv run python scripts/qa_run.py run1 [--out docs/qa] [--limit 2]
    uv run python scripts/qa_run.py run2 [--out docs/qa] [--limit 1]
    uv run python scripts/qa_run.py wrong [--out docs/qa]
"""

import argparse
import json
import math
import re
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from ui_screenshots import language_env

ROOT = Path(__file__).resolve().parents[1]
SEED = 20261030  # the simulated team's real durations
COLOURS = 64
WAIT = 240_000  # ms: a recommendation on a project of 30 tasks on a busy machine
START = date(2026, 9, 7)
DEADLINE = date(2026, 11, 27)
CHECKINS = (
    date(2026, 9, 10),
    date(2026, 9, 15),
    date(2026, 9, 21),
    date(2026, 9, 25),
    date(2026, 9, 30),
    date(2026, 10, 5),
    date(2026, 10, 8),
    date(2026, 10, 13),
    date(2026, 10, 16),
)
# What the manager does with the recommendations that wait for a decision, in turn.
DECISIONS = ("approve", "reject", "later", "approve", "approve", "approve", "approve", "approve")


def add_workdays(day: date, n: int) -> date:
    """The working day `n` working days after `day` (Monday to Friday, spec section 11.1)."""
    step = 1 if n >= 0 else -1
    left = abs(n)
    while left:
        day += timedelta(days=step)
        if day.weekday() < 5:
            left -= 1
    return day


def workdays(first: date, last: date) -> int:
    """Working days in [first, last]."""
    count = 0
    day = first
    while day <= last:
        count += day.weekday() < 5
        day += timedelta(days=1)
    return count


def write_log(path: Path, log: list[dict[str, Any]]) -> None:
    """Write a run's log; a project's id is random and says nothing, so it stays out."""
    text = json.dumps(log, ensure_ascii=False, indent=1, default=str)
    path.write_text(re.sub(r"/projects/[\w-]{16}(?![\w-])", "/projects/<id>", text) + "\n", "utf-8")


@contextmanager
def server(data: Path, log: Path, *extra: str) -> Iterator[str]:
    """`sentinel ui` on a free port with a fresh data directory, as a user starts it."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    with log.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(
            ["uv", "run", "sentinel", "ui", "--port", str(port), "--data-dir", str(data), *extra],
            cwd=ROOT,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(240):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.25)
        yield base
    finally:
        process.terminate()
        process.wait(timeout=30)


@dataclass
class Moment:
    """What a manager reads on the overview after a step."""

    step: str
    chance: str = ""
    badge: str = ""
    delta: str = ""
    deadline: str = ""
    likely: str = ""
    bad: str = ""
    budget: str = ""
    pending: list[str] = field(default_factory=list)
    threats: list[str] = field(default_factory=list)
    seconds: float = 0.0


@dataclass
class Task:
    """A task in the driver's books: what really happens to it."""

    key: str
    name: str
    extra: int = 0  # days it really takes beyond its estimate
    grown: int = 0  # days reported as growth
    started: date | None = None
    finished: date | None = None
    worked: float = 0.0


class Driver:
    """A browser page with numbered screenshots, a phone beside it and the run's log."""

    def __init__(self, page: Any, base: str, out: Path, run: str, phone: Any = None) -> None:
        self.page = page
        self.base = base
        self.run = run
        self.out = out / "shots" / run
        self.out.mkdir(parents=True, exist_ok=True)
        self.phones = out / "shots" / "phone"
        self.phones.mkdir(parents=True, exist_ok=True)
        for old in self.out.glob("*.png"):
            old.unlink()  # the driver's own screenshots of an earlier run
        for old in self.phones.glob(f"{run}_*.png"):
            old.unlink()
        self.phone_page = phone
        self.count = 0
        self.log: list[dict[str, Any]] = []

    def phone(self, name: str, path: str, scroll: str | None = None, full: bool = False) -> None:
        """The same screen on a phone (390 x 844), for the report read on one."""
        page = self.phone_page
        page.goto(self.base + path)
        self.settle(page)
        if scroll is not None:
            page.locator(scroll).first.evaluate("e => e.scrollIntoView({block: 'start'})")
            page.evaluate("window.scrollBy(0, -64)")
            page.wait_for_timeout(100)
        target = self.phones / f"{self.run}_{name}.png"
        page.screenshot(path=str(target), full_page=full)
        with Image.open(target) as image:
            reduced = image.convert("RGB").quantize(COLOURS, dither=Image.Dither.NONE)
        reduced.save(target, optimize=True)

    def shot(self, name: str, full: bool = False, page: Any = None) -> str:
        """A numbered screenshot with a reduced palette; its file name."""
        self.count += 1
        target = self.out / f"{self.count:03d}_{name}.png"
        (page or self.page).screenshot(path=str(target), full_page=full)
        with Image.open(target) as image:
            reduced = image.convert("RGB").quantize(COLOURS, dither=Image.Dither.NONE)
        reduced.save(target, optimize=True)
        return target.name

    def note(self, **values: Any) -> None:
        self.log.append(values)
        print(json.dumps(values, ensure_ascii=False, default=str)[:400], flush=True)

    def settle(self, page: Any = None) -> None:
        """Wait for the forecast of an overview, its threat list and any running analysis."""
        page = page or self.page
        page.wait_for_load_state("networkidle")
        page.wait_for_function(
            """() => !document.querySelector('.job') &&
                 !document.querySelector('#forecast .skeleton') &&
                 !document.querySelector('#drivers .loading-line')""",
            timeout=WAIT,
        )
        page.wait_for_load_state("networkidle")

    def moment(self, step: str, began: float = 0.0) -> Moment:
        """The overview as a manager reads it."""
        page = self.page

        def text(selector: str) -> str:
            found = page.locator(selector)
            return " ".join(found.first.inner_text().split()) if found.count() else ""

        def kpi(i: int) -> str:
            found = page.locator("dl.kpis > div").nth(i).locator("dd")
            return " ".join(found.inner_text().split()) if found.count() else ""

        moment = Moment(
            step,
            chance=text("#forecast .headline-number"),
            badge=text("#forecast .badge"),
            delta=text("#forecast .delta"),
            deadline=kpi(0),
            likely=kpi(1),
            bad=kpi(2),
            budget=kpi(3),
            pending=[" ".join(t.split()) for t in page.locator(".rec-card h3").all_inner_texts()],
            threats=[" ".join(t.split()) for t in page.locator("#drivers li").all_inner_texts()],
            seconds=round(time.perf_counter() - began, 1) if began else 0.0,
        )
        self.note(kind="moment", **asdict(moment))
        return moment


def create_project(d: Driver, name: str = "Portal klienta") -> str:
    """Run 1: the wizard with the team by bulk paste and the tasks by CSV."""
    page = d.page
    page.goto(d.base + "/")
    page.wait_for_load_state("networkidle")
    d.shot("start_empty")
    page.get_by_role("link", name="Utwórz projekt").first.click()
    page.wait_for_url("**/new")
    d.shot("wizard_step1_empty")
    page.get_by_label("Nazwa projektu").fill(name)
    page.get_by_label("Data rozpoczęcia").fill(START.isoformat())
    page.get_by_label("Termin", exact=True).fill(DEADLINE.isoformat())
    d.shot("wizard_step1_filled")
    page.get_by_role("button", name="Dalej").click()
    page.wait_for_url("**/setup/team")
    d.shot("wizard_step2_empty")
    page.get_by_text("Wklej listę osób").click()
    page.get_by_label("Jedna osoba w wierszu").fill(
        (ROOT / "docs/qa/zespol-portal.txt").read_text(encoding="utf-8")
    )
    d.shot("wizard_step2_paste")
    page.get_by_role("button", name="Dodaj te osoby").click()
    page.get_by_label("Imię i nazwisko osoby 11").wait_for(state="attached")
    d.shot("wizard_step2_team", full=True)
    page.get_by_role("button", name="Dalej").click()
    page.wait_for_url("**/setup/tasks")
    d.shot("wizard_step3_empty")
    page.get_by_role("link", name="Zaimportuj arkusz").click()
    page.wait_for_url("**tab=import")
    page.get_by_label("Plik arkusza (CSV)").set_input_files(
        str(ROOT / "docs/qa/zadania-portal.csv")
    )
    d.shot("wizard_step3_import")
    page.get_by_role("button", name="Importuj zadania").click()
    page.wait_for_url("**tab=manual**")
    page.wait_for_load_state("networkidle")
    d.shot("wizard_step3_tasks", full=True)
    began = time.perf_counter()
    page.get_by_role("button", name="Utwórz plan").click()
    d.shot("wizard_creating")
    page.wait_for_url(re.compile(r"/projects/[\w-]+\?flash=plan_ready"), timeout=WAIT)
    d.settle()
    d.moment("plan", began)
    d.shot("overview_after_plan", full=True)
    return page.url.split("/projects/")[1].split("?")[0]


def books(d: Driver, project: str) -> dict[str, Any]:
    """The project's JSON, read in the browser's session for the driver's books."""
    response = d.page.request.get(f"{d.base}/api/projects/{project}")
    return dict(response.json())


def move_team(
    view: dict[str, Any],
    team: dict[str, Task],
    last: date,
    when: date,
    away: dict[str, tuple[date, date | None]],
) -> None:
    """The simulated team's working days from `last` to `when`: a task starts when its planned
    start has come, its predecessors are done and its people are free; it works while its people
    are present and ends after its real length."""
    tasks = {t["key"]: t for t in view["tasks"]}
    roster = [p for p in view["people"]]

    def is_away(name: str, day: date) -> bool:
        span = away.get(name)
        return span is not None and span[0] <= day and (span[1] is None or day < span[1])

    day = last
    while day < when:
        day = add_workdays(day, 1)
        free: dict[str, int] = {}
        for person in roster:
            if not is_away(person["name"], day):
                free[person["role"]] = free.get(person["role"], 0) + 1
        running = [
            b
            for b in team.values()
            if b.started is not None and b.finished is None and b.key in tasks
        ]
        for book in running:
            task = tasks[book.key]
            for role, count in task["crew"].items():
                free[role] = free.get(role, 0) - count
            crew = task["crew_names"]
            present = sum(not is_away(name, day) for name in crew)
            book.worked += present / len(crew) if crew else 1  # the crew's present share works
            if book.worked >= max(1, task["duration"] + book.extra + book.grown) - 1e-9:
                book.finished = day
        order = sorted(
            (t for t in tasks.values() if t["state"] == "not_started"),
            key=lambda t: t["planned_start"] or "9",
        )
        for task in order:
            book = team[task["key"]]
            if book.started is not None or task["planned_start"] is None:
                continue
            ready = all(
                team[p].finished is not None and team[p].finished < day
                for p in task["predecessors"]
                if p in team
            )
            fits = all(free.get(role, 0) >= count for role, count in task["crew"].items())
            if date.fromisoformat(task["planned_start"]) <= day and ready and fits:
                book.started = day
                book.worked = 1
                for role, count in task["crew"].items():
                    free[role] = free.get(role, 0) - count
                if book.worked >= max(1, task["duration"] + book.extra + book.grown):
                    book.finished = day


def report_tasks(d: Driver, view: dict[str, Any], team: dict[str, Task]) -> list[str]:
    """Enter what the team did on the check-in form; returns the lines reported."""
    page = d.page
    reported = []
    more = page.locator("details.more-tasks > summary")
    if more.count():
        more.click()
    for task in view["tasks"]:
        book = team[task["key"]]
        if task["state"] in ("done", "removed") or book.started is None:
            continue
        row = page.locator("fieldset.task-row", has_text=task["name"]).first
        if task["state"] == "not_started":
            planned = task["planned_start"]
            if planned != book.started.isoformat():
                row.locator("details.task-more > summary").click()
                row.get_by_label("Rozpoczęte dnia").fill(book.started.isoformat())
        if book.finished is not None:
            row.get_by_label("Gotowe", exact=True).check()
            row.get_by_label("Zakończone dnia").fill(book.finished.isoformat())
            reported.append(f"{task['name']}: gotowe {book.finished}")
        else:
            length = max(1, task["duration"] + book.extra + book.grown)
            percent = min(95, math.floor(100 * book.worked / length))
            row.get_by_label("W toku").check()
            row.get_by_label("Wykonana część").fill(str(percent))
            reported.append(f"{task['name']}: {percent} %")
    return reported


def add_absence(page: Any, person: str, first: date, back: date | None) -> None:
    page.get_by_role("button", name="Dodaj nieobecność").click()
    row = page.locator("#away-list [data-row]").last
    row.get_by_label("Osoba").select_option(label=person)
    row.get_by_label("Nieobecność od").fill(first.isoformat())
    if back is not None:
        row.get_by_label("Powrót").fill(back.isoformat())


def add_growth(page: Any, task: str, days: int) -> None:
    page.get_by_role("button", name="Dodaj zadanie, które urosło").click()
    row = page.locator("#grow-list [data-row]").last
    row.get_by_label("Zadanie").select_option(label=task)
    row.get_by_label("Dodatkowe dni robocze").fill(str(days))


def add_new_task(page: Any, name: str, days: int, role_index: int, after: str, before: str) -> None:
    page.get_by_role("button", name="Dodaj nowe zadanie").click()
    row = page.locator("#new-list [data-row]").last
    row.get_by_label("Nazwa zadania").fill(name)
    row.get_by_label("Dni robocze").fill(str(days))
    row.locator(f'input[name$="_crew_{role_index}"]').fill("1")
    row.get_by_label("Następuje po").select_option(label=after)
    row.get_by_label("Musi być gotowe przed").select_option(label=before)


def decide(d: Driver, project: str, verdict: str, label: str) -> dict[str, Any]:
    """Open the waiting recommendation, read it and decide."""
    page = d.page
    page.get_by_role("link", name="Przejrzyj i zdecyduj").first.click()
    page.wait_for_url("**/recommendations/**")
    page.wait_for_load_state("networkidle")
    title = " ".join(page.locator("#rec-title").inner_text().split())
    rows = [" ".join(r.split()) for r in page.locator(".summary-rows > div").all_inner_texts()]
    why = [" ".join(r.split()) for r in page.locator("ul.bullets li").all_inner_texts()]
    chance = " ".join(page.locator(".rec-chance").first.inner_text().split())
    d.shot(f"{label}_recommendation", full=True)
    page.locator("#compare-disclosure > summary").click()
    table = [" ".join(r.split()) for r in page.locator("table.compare tbody tr").all_inner_texts()]
    d.shot(f"{label}_options", full=True)
    began = time.perf_counter()
    if verdict == "approve":
        page.locator('button[name="verdict"][value="approve"]').click()
    elif verdict == "later":
        page.locator('button[name="verdict"][value="later"]').click()
    else:
        page.get_by_role("button", name="Odrzuć", exact=True).click()
        d.shot(f"{label}_reject_panel")
        page.get_by_role("button", name="Odrzuć propozycję").click()
    page.wait_for_url(re.compile(rf"/projects/{project}\?flash="), timeout=WAIT)
    toast = " ".join(page.locator("#flash").inner_text().split())
    d.settle()
    toast_after = " ".join(page.locator("#flash").inner_text().split())
    d.shot(f"{label}_after_{verdict}", full=True)
    record = {
        "kind": "decision",
        "verdict": verdict,
        "title": title,
        "chance": chance,
        "rows": rows,
        "why": why,
        "options": table,
        "toast": toast,
        "toast_after": toast_after,
        "seconds": round(time.perf_counter() - began, 1),
    }
    d.note(**record)
    return record


def phone_page(browser: Any, base: str) -> Any:
    """A page in a phone-size window on the same (local) projects."""
    phone = browser.new_context(
        viewport={"width": 390, "height": 844},
        locale="pl-PL",
        reduced_motion="reduce",
        has_touch=True,
        is_mobile=True,
    )
    phone.set_default_timeout(60_000)
    phone.add_cookies([{"name": "sentinel_lang", "value": "pl", "url": base}])
    return phone.new_page()


def run1(args: argparse.Namespace, browser: Any) -> None:
    out: Path = args.out
    data = Path(tempfile.mkdtemp(prefix="sentinel-qa1-"))
    with server(data, out / "run1-server.log") as base:
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="pl-PL",
            reduced_motion="reduce",
            accept_downloads=True,
        )
        context.set_default_timeout(60_000)
        context.add_cookies([{"name": "sentinel_lang", "value": "pl", "url": base}])
        d = Driver(context.new_page(), base, out, "run1", phone_page(browser, base))
        d.phone("start_empty", "/")
        d.phone("wizard_basics", "/new")
        project = create_project(d)
        d.phone("overview_plan", f"/projects/{project}")
        rng = np.random.default_rng(SEED)
        team: dict[str, Task] = {}
        keys = [t["key"] for t in books(d, project)["tasks"]]
        names = {t["key"]: t["name"] for t in books(d, project)["tasks"]}
        for key in keys:
            # Most tasks take as long as estimated; some less, some more (estimates "usual").
            extra = int(rng.choice([-1, 0, 0, 0, 1, 1, 2]))
            team[key] = Task(key, names[key], extra=extra)
        decisions = iter(DECISIONS)
        undone = False
        limit = args.limit or len(CHECKINS)
        away: dict[str, tuple[date, date | None]] = {}
        last = add_workdays(START, -1)
        grown = False
        for number, when in enumerate(CHECKINS[:limit], start=1):
            label = f"c{number}"
            page = d.page
            page.goto(f"{base}/projects/{project}/checkin")
            page.wait_for_load_state("networkidle")
            page.get_by_label("Stan na koniec dnia").fill(when.isoformat())
            d.shot(f"{label}_form_empty")
            view = books(d, project)
            for task in view["tasks"]:
                team.setdefault(task["key"], Task(task["key"], task["name"]))
                if task["start"] and team[task["key"]].started is None:
                    team[task["key"]].started = date.fromisoformat(task["start"])
                if task["state"] == "done" and team[task["key"]].finished is None:
                    team[task["key"]].finished = date.fromisoformat(task["finish"])
            move_team(view, team, last, when, away)
            last = when
            reported = report_tasks(d, view, team)
            events = []
            if number == 3:  # the first absence, with a return date
                first_away = add_workdays(when, 1)
                add_absence(
                    page,
                    "Cezary Wójcik (Programista backend)",
                    first_away,
                    date(2026, 10, 2),
                )
                away["Cezary Wójcik"] = (first_away, date(2026, 10, 2))
                events.append("nieobecność: Cezary Wójcik do 2 paź")
            running = [
                t
                for t in view["tasks"]
                if t["state"] in ("in_progress", "paused") and team[t["key"]].finished is None
            ]
            if number >= 4 and not grown and running:  # a task grows, the first time one can
                grower = max(running, key=lambda t: t["duration"])
                add_growth(page, grower["name"], 4)
                team[grower["key"]].grown = 4
                grown = True
                events.append(f"zadanie urosło: {grower['name']} +4 dni")
            if number == 5:  # new work comes up
                add_new_task(
                    page,
                    "Audyt bezpieczeństwa",
                    4,
                    2,
                    "Logowanie i konta",
                    "Testy API",
                )
                events.append("nowe zadanie: Audyt bezpieczeństwa, 4 dni")
            if number == 7:  # the second absence, the return not known yet
                add_absence(page, "Hanna Pawlak (Tester)", add_workdays(when, 1), None)
                away["Hanna Pawlak"] = (add_workdays(when, 1), None)
                events.append("nieobecność: Hanna Pawlak, powrót nieznany")
            d.shot(f"{label}_form_filled", full=True)
            label_text = " ".join(page.locator("button.btn-primary").inner_text().split())
            count_text = page.locator("[data-change-count]").inner_text()
            began = time.perf_counter()
            page.locator("button.btn-primary").click()
            for _ in range(5):
                try:
                    page.wait_for_url(re.compile(r"flash=checkin_saved"), timeout=20_000)
                    break
                except Exception:
                    errors = " | ".join(page.locator("#checkin-form .callout").all_inner_texts())
                    d.shot(f"{label}_refused", full=True)
                    d.note(kind="refused", checkin=str(when), errors=errors)
                    # What a manager does: that task has not started after all.
                    blocked = next((t for t in team.values() if t.name in errors), None)
                    if blocked is None:
                        raise
                    row = page.locator("fieldset.task-row", has_text=blocked.name).first
                    row.get_by_label("Nierozpoczęte").check()
                    blocked.started, blocked.finished, blocked.worked = None, None, 0
                    page.locator("button.btn-primary").click()
            d.settle()
            toast = " ".join(page.locator("#flash").inner_text().split())
            moment = d.moment(f"{label} {when}", began)
            d.note(
                kind="checkin",
                date=str(when),
                reported=reported,
                events=events,
                button=label_text,
                count=count_text,
                toast=toast,
            )
            d.shot(f"{label}_overview", full=True)
            crews = {
                t["name"]: t["crew_names"]
                for t in books(d, project)["tasks"]
                if t["state"] in ("in_progress", "paused")
            }
            d.note(kind="crews", date=str(when), crews=crews)
            if events:
                d.phone(f"{label}_overview", f"/projects/{project}")
            if moment.pending:
                verdict = next(decisions, "approve")
                seq = page.get_by_role("link", name="Przejrzyj i zdecyduj").first.get_attribute(
                    "href"
                )
                d.phone(f"{label}_recommendation", str(seq))
                d.phone(f"{label}_card", f"/projects/{project}", scroll="#pending-title")
                decide(d, project, verdict, label)
                d.moment(f"{label} po decyzji: {verdict}")
                d.phone(f"{label}_after_{verdict}", f"/projects/{project}")
            undo = page.get_by_role("button", name="Cofnij")
            if undo.count() and not undone:
                d.shot(f"{label}_auto_before_undo", full=True)
                d.moment(f"{label} przed cofnięciem")
                undo.first.click()
                page.wait_for_url(re.compile(r"flash=undone"), timeout=WAIT)
                d.settle()
                undone = True
                d.moment(f"{label} po cofnięciu")
                d.shot(f"{label}_after_undo", full=True)
                # After the undo the manager wants to decide everything from now on.
                page.goto(f"{base}/projects/{project}/settings")
                page.wait_for_load_state("networkidle")
                page.get_by_label(re.compile("Tylko doradzaj")).check()
                d.shot(f"{label}_settings_unsaved", full=True)
                page.get_by_role("button", name="Zapisz zmiany").click()
                page.wait_for_url(re.compile(r"flash=settings_saved"), timeout=WAIT)
                page.wait_for_load_state("networkidle")
                toast = " ".join(page.locator("#flash").inner_text().split())
                d.note(kind="settings", autonomy="Tylko doradzaj", toast=toast)
        # the exports and the history
        page = d.page
        page.goto(f"{base}/projects/{project}/settings")
        page.wait_for_load_state("networkidle")
        d.shot("settings", full=True)
        with page.expect_download() as plan:
            page.get_by_role("link", name="Pobierz").first.click()
        path = out / "shots" / "run1" / "plan.csv"
        plan.value.save_as(path)
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        d.note(
            kind="export",
            file=plan.value.suggested_filename,
            bytes=path.stat().st_size,
            rows=len(lines) - 1,
            header=lines[0],
        )
        with context.expect_page() as popup:
            page.get_by_role("link", name="Otwórz").first.click()
        popup.value.wait_for_load_state("load")
        d.shot("report", full=True, page=popup.value)
        d.phone("report", popup.value.url.replace(base, ""))
        d.note(kind="report", title=popup.value.title(), url=popup.value.url.split("/api")[-1])
        popup.value.close()
        page.goto(f"{base}/projects/{project}/history")
        page.wait_for_selector("#chance-history svg", timeout=WAIT)
        page.wait_for_load_state("networkidle")
        d.shot("history", full=True)
        older = page.locator("details.tl-more > summary")
        if older.count():
            older.click()
        entries = [" ".join(t.split()) for t in page.locator(".tl-item").all_inner_texts()]
        text = " ".join(entries)
        wanted = {
            "9 raportów": text.count("Raport statusu za") == limit,
            "zatwierdzenia": "Zatwierdzono:" in text,
            "odrzucenie": "Odrzucono:" in text or limit < 5,
            "odłożenie": "Odłożono:" in text or limit < 6,
            "cofnięcie": "Cofnięto automatyczną zmianę" in text,
            "nieobecności": ("Cezary Wójcik" in text and "Hanna Pawlak" in text) or limit < 7,
            "wydłużenie": "dodatkowe dni robocze" in text or limit < 4,
            "nowe zadanie": "Audyt bezpieczeństwa" in text or limit < 5,
        }
        d.note(kind="history", count=len(entries), found=wanted, entries=entries)
        d.phone("history", f"/projects/{project}/history")
        for name in ("checkins", "recommendations", "changes"):
            page.goto(f"{base}/projects/{project}/history?show={name}")
            page.wait_for_load_state("networkidle")
            d.shot(f"history_{name}", full=True)
        page.goto(f"{base}/projects/{project}")
        d.settle()
        d.moment("koniec przebiegu 1")
        d.shot("overview_final", full=True)
        d.phone("overview_final", f"/projects/{project}")
        d.phone("gantt", f"/projects/{project}", scroll="#plan-title")
        write_log(out / "run1-log.json", d.log)
        context.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run", choices=("run1", "run2", "wrong"))
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "qa")
    parser.add_argument("--limit", type=int, default=0, help="smoke: only the first steps")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(env=language_env("pl"))
        {"run1": run1, "run2": run2, "wrong": wrong}[args.run](args, browser)
        browser.close()
    return 0


def simulator_read(d: Driver, label: str) -> None:
    page = d.page
    d.shot(label, full=True)
    numbers = page.locator(".sim-day")
    d.note(
        kind="simulator",
        step=label,
        day=numbers.first.inner_text() if numbers.count() else "",
        chance=" ".join(page.locator(".sim-numbers > div").last.inner_text().split())
        if page.locator(".sim-numbers").count()
        else "",
        events=page.locator(".sim-timeline .tl-item").count(),
        latest=[
            " ".join(t.split())
            for t in page.locator(".sim-timeline .tl-item").all_inner_texts()[:3]
        ],
    )


def run2(args: argparse.Namespace, browser: Any) -> None:
    """The simulator: the small and the medium example, Sentinel against nobody reacting."""
    out: Path = args.out
    data = Path(tempfile.mkdtemp(prefix="sentinel-qa2-"))
    examples = (("Mały", "small"), ("Średni", "medium"))
    with server(data, out / "run2-server.log") as base:
        context = browser.new_context(
            viewport={"width": 1280, "height": 800}, locale="pl-PL", reduced_motion="reduce"
        )
        context.set_default_timeout(60_000)
        context.add_cookies([{"name": "sentinel_lang", "value": "pl", "url": base}])
        d = Driver(context.new_page(), base, out, "run2", phone_page(browser, base))
        page = d.page
        d.phone("setup", "/simulator")
        for word, name in examples[: args.limit or 2]:
            page.goto(base + "/simulator")
            page.wait_for_load_state("networkidle")
            d.shot(f"{name}_setup")
            page.get_by_label(re.compile(f"{word} przykładowy projekt")).check()
            began = time.perf_counter()
            page.get_by_role("button", name="Rozpocznij symulację").click()
            page.wait_for_url(re.compile(r"/projects/[\w-]+$"), timeout=WAIT)
            page.wait_for_load_state("networkidle")
            d.note(
                kind="timing", step=f"{name} start", seconds=round(time.perf_counter() - began, 1)
            )
            simulator_read(d, f"{name}_day0")
            for button, label in (("+1", "1"), ("+5", "5"), ("+10", "10"), ("Do końca", "end")):
                began = time.perf_counter()
                page.get_by_role("button", name=button, exact=False).first.click()
                if label == "end":
                    page.wait_for_timeout(1500)
                    d.shot(f"{name}_running_to_end")
                    page.get_by_role("heading", name="Jak się skończyło").wait_for(timeout=WAIT * 3)
                else:
                    day = page.locator(".sim-day").inner_text()
                    page.wait_for_function(
                        """text => {
                            const shown = document.querySelector('.sim-day');
                            return shown && shown.textContent !== text
                                && !document.querySelector('.job');
                        }""",
                        arg=day,
                        timeout=WAIT,
                    )
                page.wait_for_load_state("networkidle")
                d.note(
                    kind="timing",
                    step=f"{name} {label}",
                    seconds=round(time.perf_counter() - began, 1),
                )
                simulator_read(d, f"{name}_after_{label}")
                if label == "10":
                    d.phone(f"{name}_running", page.url.replace(base, ""))
            d.phone(f"{name}_result", page.url.replace(base, ""))
            d.note(
                kind="result",
                example=name,
                verdict=" ".join(page.locator(".verdict").inner_text().split()),
                table=[
                    " | ".join(r.split("\t"))
                    for r in page.locator("table.compare tr").all_inner_texts()
                ],
            )
            with context.expect_page() as popup:
                page.get_by_role("link", name="Pokaż raport").click()
            popup.value.wait_for_load_state("load")
            d.shot(f"{name}_report", full=True, page=popup.value)
            d.phone(f"{name}_report", popup.value.url.replace(base, ""))
            d.note(kind="report", example=name, title=popup.value.title())
            popup.value.close()
        write_log(out / "run2-log.json", d.log)
        context.close()


def csv_bytes(*rows: str) -> dict[str, Any]:
    return {"name": "zadania.csv", "mimeType": "text/csv", "buffer": "\n".join(rows).encode()}


def new_project(page: Any, base: str, name: str, team: str, deadline: str = "2026-12-18") -> str:
    """A draft through the wizard up to the tasks step; its id."""
    page.goto(base + "/new")
    page.get_by_label("Nazwa projektu").fill(name)
    page.get_by_label("Data rozpoczęcia").fill("2026-11-02")
    page.get_by_label("Termin", exact=True).fill(deadline)
    page.get_by_role("button", name="Dalej").click()
    page.wait_for_url("**/setup/team")
    project = str(page.url.split("/projects/")[1].split("/")[0])
    if not team:
        return project
    page.get_by_text("Wklej listę osób").click()
    page.get_by_label("Jedna osoba w wierszu").fill(team)
    page.get_by_role("button", name="Dodaj te osoby").click()
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="Dalej").click()
    page.wait_for_url("**/setup/tasks")
    return project


TEAM = "Ala, Programista\nBartek, Programista\nCela, Tester"
GOOD_CSV = (
    "id,name,duration_days,predecessors,optional,crew:Programista,crew:Tester",
    "T1,Analiza,3,,no,1,0",
    "T2,Budowa,6,T1,no,2,0",
    "T3,Testy,4,T2,no,1,1",
    "T4,Dodatki,2,T1,yes,1,0",
)


def planned_project(page: Any, base: str, name: str, deadline: str = "2026-12-18") -> str:
    """A small planned project created through the pages; its id."""
    project = new_project(page, base, name, TEAM, deadline)
    page.get_by_role("link", name="Zaimportuj arkusz").click()
    page.wait_for_url("**tab=import")
    page.get_by_label("Plik arkusza (CSV)").set_input_files(csv_bytes(*GOOD_CSV))
    page.get_by_role("button", name="Importuj zadania").click()
    page.wait_for_url("**tab=manual**")
    page.get_by_role("button", name="Utwórz plan").click()
    page.wait_for_url(re.compile(r"flash=plan_ready"), timeout=WAIT)
    page.wait_for_load_state("networkidle")
    return project


def wrong(args: argparse.Namespace, browser: Any) -> None:
    """What users do wrong: each case records what the page answered."""
    out: Path = args.out
    data = Path(tempfile.mkdtemp(prefix="sentinel-qa3-"))
    with server(data, out / "wrong-server.log") as base:
        context = browser.new_context(
            viewport={"width": 1280, "height": 800}, locale="pl-PL", reduced_motion="reduce"
        )
        context.set_default_timeout(30_000)
        context.add_cookies([{"name": "sentinel_lang", "value": "pl", "url": base}])
        asked: list[str] = []

        def on_dialog(dialog: Any) -> None:
            asked.append(dialog.type)
            dialog.accept()

        context.on("dialog", on_dialog)
        d = Driver(context.new_page(), base, out, "wrong", phone_page(browser, base))
        page = d.page

        def answer(case: str, shot: str, *selectors: str) -> None:
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(400)
            found: list[str] = []
            for _ in range(5):  # the page may still be navigating
                try:
                    found = [
                        " ".join(t.split())
                        for selector in selectors or (".callout", ".error-text")
                        for t in page.locator(selector).all_inner_texts()
                    ]
                    break
                except Exception:
                    page.wait_for_timeout(1000)
            d.note(kind="case", case=case, url=page.url.replace(base, ""), shown=found)
            d.shot(shot, full=True)

        # ---- empty fields and a deadline before the start
        page.goto(base + "/new")
        page.get_by_label("Data rozpoczęcia").fill("")
        page.get_by_role("button", name="Dalej").click()
        answer("empty fields in step 1", "empty_fields")
        page.get_by_label("Nazwa projektu").fill("Zły termin")
        page.get_by_label("Data rozpoczęcia").fill("2026-11-02")
        page.get_by_label("Termin", exact=True).fill("2026-10-01")
        page.wait_for_timeout(200)
        d.note(
            kind="case", case="live rule", shown=page.locator("[data-deadline-rule]").inner_text()
        )
        page.get_by_role("button", name="Dalej").click()
        answer("deadline before the start", "deadline_before_start")
        page.get_by_label("Budżet").fill("-5")
        page.get_by_label("Termin", exact=True).fill("2026-12-01")
        page.get_by_role("button", name="Dalej").click()
        answer("negative budget", "negative_budget")

        # ---- team: empty, a person without a role, names repeated
        project = new_project(page, base, "Bez zespołu", "")
        page.goto(f"{base}/projects/{project}/setup/team")
        page.get_by_role("button", name="Dalej").click()
        answer("no team, next", "team_empty", "#issues .callout", ".callout")
        page.get_by_text("Wklej listę osób").click()
        page.get_by_label("Jedna osoba w wierszu").fill("Ala\nAla, Tester\nAla, Tester")
        page.get_by_role("button", name="Dodaj te osoby").click()
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="Dalej").click()
        answer("repeated names and no role", "team_repeated")
        page.get_by_label("Imię i nazwisko osoby 1").press("Enter")
        answer("Enter in a name field", "team_enter")
        page.goto(f"{base}/projects/{project}/setup/team")
        d.note(kind="case", case="people after Enter", shown=page.locator(".person-row").count())

        # ---- CSV with errors
        project = new_project(page, base, "Zły arkusz", TEAM)
        page.get_by_role("link", name="Zaimportuj arkusz").click()
        page.wait_for_url("**tab=import")
        for case, rows in (
            ("csv missing column", ("id,name", "T1,Analiza")),
            ("csv bad number", ("id,name,duration_days", "T1,Analiza,dużo")),
            (
                "csv unknown predecessor and role",
                ("id,name,duration_days,predecessors,crew:Kucharz", "T1,Analiza,3,T9,1"),
            ),
            ("csv repeated task", ("id,name,duration_days", "T1,Analiza,3", "T1,Analiza,3")),
            ("csv empty", ("",)),
        ):
            page.goto(f"{base}/projects/{project}/setup/tasks?tab=import")
            page.get_by_label("Plik arkusza (CSV)").set_input_files(csv_bytes(*rows))
            page.get_by_role("button", name="Importuj zadania").click()
            page.wait_for_timeout(600)
            answer(case, case.replace(" ", "_"))
        page.goto(f"{base}/projects/{project}/setup/tasks?tab=import")
        page.get_by_label("Plik arkusza (CSV)").set_input_files(
            {
                "name": "zadania.csv",
                "mimeType": "text/csv",
                "buffer": "id,name\nżółć".encode("cp1250"),
            }
        )
        page.get_by_role("button", name="Importuj zadania").click()
        page.wait_for_timeout(600)
        answer("csv in another encoding", "csv_encoding")
        page.goto(f"{base}/projects/{project}/setup/tasks?tab=import")
        page.get_by_role("button", name="Importuj zadania").click()
        page.wait_for_timeout(300)
        answer("import without a file", "csv_no_file")

        # ---- cycles
        rows = (
            "id,name,duration_days,predecessors,crew:Programista",
            "T1,Analiza,3,T3,1",
            "T2,Budowa,3,T1,1",
            "T3,Testy,3,T2,1",
        )
        page.goto(f"{base}/projects/{project}/setup/tasks?tab=import")
        page.get_by_label("Plik arkusza (CSV)").set_input_files(csv_bytes(*rows))
        page.get_by_role("button", name="Importuj zadania").click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)
        answer("csv with a cycle", "cycle_import")
        if "tab=manual" not in page.url:
            page.goto(f"{base}/projects/{project}/setup/tasks?tab=manual")
        page.get_by_role("button", name="Utwórz plan").click()
        page.wait_for_timeout(1000)
        answer("create the plan with a cycle", "cycle_finish", "#issues .callout", ".callout")
        project2 = new_project(page, base, "Cykl ręcznie", TEAM)
        for i in range(2):
            page.get_by_role("button", name="Dodaj zadanie").click()
            page.wait_for_load_state("networkidle")
            page.get_by_label(f"Nazwa zadania {i + 1}").fill(f"Zadanie {i + 1}")
            page.get_by_label(f"Dni robocze zadania {i + 1}").fill("2")
        page.locator('[data-after-picker][data-row="1"] summary').click()
        page.locator('[data-after-picker][data-row="1"]').get_by_label("2. Zadanie 2").check()
        page.keyboard.press("Escape")
        page.locator('[data-after-picker][data-row="2"] summary').click()
        page.locator('[data-after-picker][data-row="2"]').get_by_label("1. Zadanie 1").check()
        page.keyboard.press("Escape")
        page.wait_for_timeout(900)
        answer("a cycle by hand, while typing", "cycle_manual", "#issues .callout", ".callout")
        d.note(kind="case", case="draft project", shown=project2)

        # ---- double clicks
        project = new_project(page, base, "Podwójne kliki", TEAM, "2026-11-20")
        page.get_by_role("link", name="Zaimportuj arkusz").click()
        page.wait_for_url("**tab=import")
        page.get_by_label("Plik arkusza (CSV)").set_input_files(csv_bytes(*GOOD_CSV))
        page.get_by_role("button", name="Importuj zadania").dblclick()
        page.wait_for_url("**tab=manual**")
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="Utwórz plan").dblclick()
        page.wait_for_url(re.compile(r"flash=plan_ready"), timeout=WAIT)
        answer("double click on create the plan", "dbl_plan", ".toast", ".callout")
        page.wait_for_load_state("networkidle")
        page.goto(f"{base}/projects/{project}/checkin")
        page.get_by_label("Stan na koniec dnia").fill("2026-11-04")
        row = page.locator("fieldset.task-row", has_text="Analiza").first
        row.get_by_label("W toku").check()
        row.get_by_label("Wykonana część").fill("50")
        page.locator("button.btn-primary").dblclick()
        page.wait_for_url(re.compile(r"flash=checkin_saved"), timeout=WAIT)
        answer("double click on save the check-in", "dbl_checkin", ".toast", ".callout")
        d.settle()
        page.goto(f"{base}/projects/{project}/history?show=checkins")
        d.note(
            kind="case",
            case="check-ins after a double click",
            shown=page.locator(".tl-item").count(),
        )
        page.goto(f"{base}/projects/{project}/checkin")
        page.get_by_label("Stan na koniec dnia").fill("2026-11-05")
        row = page.locator("fieldset.task-row", has_text="Analiza").first
        row.get_by_label("Gotowe", exact=True).check()
        row.get_by_label("Zakończone dnia").fill("2026-11-04")
        add_absence(page, "Bartek (Programista)", date(2026, 11, 6), date(2026, 11, 20))
        page.locator("button.btn-primary").click()
        page.wait_for_url(re.compile(r"flash=checkin_saved"), timeout=WAIT)
        d.settle()
        answer("a project with an absence", "absence_overview", ".rec-card h3")
        review = page.get_by_role("link", name="Przejrzyj i zdecyduj")
        if review.count():
            review.first.click()
            page.wait_for_url("**/recommendations/**")
            url = page.url
            page.locator('button[name="verdict"][value="approve"]').dblclick()
            page.wait_for_url(re.compile(r"flash="), timeout=WAIT)
            answer("double click on approve", "dbl_approve", ".toast", ".callout")
            d.settle()
            page.goto(f"{base}/projects/{project}/history?show=recommendations")
            d.note(
                kind="case",
                case="decisions after a double click",
                shown=[" ".join(t.split()) for t in page.locator(".tl-title").all_inner_texts()],
            )
            # ---- browser back after the decision: the decided page again
            page.goto(url)
            answer("a decided recommendation opened again", "decided_again", ".callout")

        # ---- two tabs on the same project
        second = context.new_page()
        first_url = f"{base}/projects/{project}/checkin"
        page.goto(first_url)
        second.goto(first_url)
        for tab, day in ((second, "2026-11-10"), (page, "2026-11-09")):
            tab.get_by_label("Stan na koniec dnia").fill(day)
            tab.locator("button.btn-primary").click()
            tab.wait_for_load_state("networkidle")
            tab.wait_for_timeout(800)
            confirm = tab.get_by_label("Tak, ta data jest prawidłowa")
            if confirm.count():  # the dates lie more than a week ahead of today
                confirm.check()
                tab.locator("button.btn-primary").click()
                tab.wait_for_load_state("networkidle")
                tab.wait_for_timeout(1500)
        answer("two tabs: an older check-in after a newer one", "two_tabs_checkin")
        second.close()
        project3 = planned_project(page, base, "Dwie karty")
        other = context.new_page()
        for tab in (page, other):
            tab.goto(f"{base}/projects/{project3}/settings")
        page.get_by_label("Nazwa projektu").fill("Dwie karty A")
        page.get_by_role("button", name="Zapisz zmiany").click()
        page.wait_for_url(re.compile(r"flash=settings_saved"))
        other.get_by_label("Nazwa projektu").fill("Dwie karty B")
        other.get_by_role("button", name="Zapisz zmiany").click()
        other.wait_for_load_state("networkidle")
        other.wait_for_timeout(500)
        shown = other.locator('[role="alert"]').first.inner_text()
        d.note(kind="case", case="two tabs: settings, the second save asks", shown=shown)
        other.close()

        # ---- language in mid-flow
        project4 = new_project(page, base, "Język", TEAM)
        page.get_by_role("link", name="Zaimportuj arkusz").click()
        page.locator('a[hreflang="en"]:visible').first.click()
        page.wait_for_load_state("networkidle")
        answer("language switch on the import tab", "language_import", "h1")
        page.locator('a[hreflang="pl"]:visible').first.click()
        project5 = planned_project(page, base, "Język 2")
        page.goto(f"{base}/projects/{project5}/checkin")
        page.get_by_label("Stan na koniec dnia").fill("2026-11-04")
        row = page.locator("fieldset.task-row", has_text="Analiza").first
        row.get_by_label("W toku").check()
        row.get_by_label("Wykonana część").fill("50")
        page.locator('a[hreflang="en"]:visible').first.click()
        page.wait_for_load_state("networkidle")
        kept = page.locator("#date").input_value()
        answer("language switch on a half-filled check-in", "language_checkin", "h1")
        d.note(kind="case", case="check-in after the switch", shown=kept, browser_asked=asked[-1:])
        page.locator('a[hreflang="pl"]:visible').first.click()
        d.note(kind="case", case="draft kept", shown=project4)

        # ---- browser back during a running job
        page.goto(base + "/simulator")
        if page.get_by_role("button", name="Rozpocznij symulację").count():
            page.get_by_role("button", name="Rozpocznij symulację").click()
            page.wait_for_url(re.compile(r"/projects/[\w-]+$"), timeout=WAIT)
            sim = page.url
            page.get_by_role("button", name="Do końca").click()
            page.wait_for_timeout(1500)
            d.shot("sim_running")
            page.go_back()
            page.wait_for_load_state("networkidle")
            answer("back during a run to the end", "sim_back", "h1", ".callout")
            page.go_forward()
            page.wait_for_load_state("networkidle")
            d.shot("sim_forward")
            page.goto(sim)
            page.wait_for_timeout(1000)
            answer("the run opened again while it works", "sim_again", ".sim-day", ".job")
            page.reload()
            page.wait_for_load_state("networkidle")
            d.shot("sim_reload")
            buttons = page.locator(".sim-steps button")
            if buttons.count():
                buttons.nth(1).click()
                page.wait_for_timeout(1500)
                answer("a second run while the first works", "sim_second", ".callout", ".job")
            page.get_by_role("heading", name="Jak się skończyło").wait_for(timeout=WAIT * 2)
            answer("the run in the end", "sim_end", ".verdict")
            # cancel a run to the end
            page.goto(base + "/simulator")
            page.get_by_role("button", name="Rozpocznij symulację").click()
            page.wait_for_url(re.compile(r"/projects/[\w-]+$"), timeout=WAIT)
            page.get_by_role("button", name="Do końca").click()
            page.get_by_role("button", name="Anuluj").wait_for(timeout=WAIT)
            page.wait_for_timeout(3000)
            d.shot("sim_before_cancel")
            page.get_by_role("button", name="Anuluj").click()
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(1500)
            answer("cancel a run to the end", "sim_cancel", ".sim-day", ".callout")

        # ---- check-in mistakes
        project6 = planned_project(page, base, "Błędy raportu")
        url = f"{base}/projects/{project6}/checkin"
        for case, day, fill in (
            ("check-in without a date", "", None),
            ("check-in before the project starts", "2026-10-01", None),
            ("check-in far in the future", "2030-01-07", None),
            ("finished after the check-in", "2026-11-04", ("Gotowe", "2026-12-24")),
            ("percent above 99", "2026-11-04", ("W toku", "150")),
        ):
            page.goto(url)
            page.get_by_label("Stan na koniec dnia").fill(day)
            if fill is not None:
                row = page.locator("fieldset.task-row", has_text="Analiza").first
                row.get_by_label(fill[0], exact=True).check()
                if fill[0] == "Gotowe":
                    row.get_by_label("Zakończone dnia").fill(fill[1])
                else:
                    row.locator('input[type="number"]').fill(fill[1])
            page.locator("button.btn-primary").click()
            page.wait_for_timeout(1200)
            answer(case, case.replace(" ", "_"))
            if "flash=" in page.url:
                d.settle()
                project6 = planned_project(page, base, f"Błędy raportu {case[:12]}")
                url = f"{base}/projects/{project6}/checkin"
        page.goto(url)
        page.get_by_label("Stan na koniec dnia").fill("2026-11-04")
        page.get_by_role("button", name="Dodaj nieobecność").click()
        row = page.locator("#away-list [data-row]").last
        row.get_by_label("Nieobecność od").fill("2026-11-10")
        row.get_by_label("Powrót").fill("2026-11-05")
        row.get_by_label("Osoba").select_option(index=1)
        page.locator("button.btn-primary").click()
        page.wait_for_timeout(1200)
        answer("an absence that ends before it starts", "absence_backwards")
        page.goto(url)
        page.get_by_role("button", name="Dodaj nowe zadanie").click()
        row = page.locator("#new-list [data-row]").last
        row.get_by_label("Dni robocze").fill("0")
        page.locator("button.btn-primary").click()
        page.wait_for_timeout(1200)
        answer("a new task without a name", "new_task_empty")

        # ---- a name with markup
        project7 = new_project(page, base, "<script>alert(1)</script> <b>Projekt</b>", TEAM)
        page.goto(base + "/")
        page.wait_for_load_state("networkidle")
        d.note(
            kind="case",
            case="a name with markup",
            shown=[" ".join(t.split()) for t in page.locator(".row-title").all_inner_texts()],
            project=project7,
        )
        d.shot("markup_name", full=True)

        # ---- a phone-size window
        phone = browser.new_context(
            viewport={"width": 390, "height": 844},
            locale="pl-PL",
            reduced_motion="reduce",
            has_touch=True,
            is_mobile=True,
        )
        phone.set_default_timeout(30_000)
        phone.add_cookies([{"name": "sentinel_lang", "value": "pl", "url": base}])
        phone.on("dialog", on_dialog)
        mobile = Driver(phone.new_page(), base, out, "wrong_phone")
        tab = mobile.page
        widths = {}

        def visit(path: str, label: str) -> None:
            tab.goto(base + path)
            tab.wait_for_load_state("networkidle")
            widths[label] = tab.evaluate(
                "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
            )
            mobile.shot(label, full=True)

        visit("/", "start")
        tab.get_by_role("button", name="Menu").click()
        mobile.shot("drawer")
        tab.keyboard.press("Escape")
        visit("/new", "wizard1")
        project8 = planned_project(tab, base, "Telefon", "2026-11-20")
        widths["after_wizard"] = tab.evaluate(
            "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        mobile.shot("overview", full=True)
        visit(f"/projects/{project8}/setup/tasks", "structure_frozen")
        visit(f"/projects/{project8}/checkin", "checkin")
        tab.get_by_label("Stan na koniec dnia").fill("2026-11-05")
        row = tab.locator("fieldset.task-row", has_text="Analiza").first
        row.get_by_label("Gotowe", exact=True).check()
        row.get_by_label("Zakończone dnia").fill("2026-11-04")
        tab.get_by_role("button", name="Dodaj nieobecność").click()
        away_row = tab.locator("#away-list [data-row]").last
        away_row.get_by_label("Osoba").select_option(index=2)
        away_row.get_by_label("Nieobecność od").fill("2026-11-06")
        away_row.get_by_label("Powrót").fill("2026-11-20")
        mobile.shot("checkin_filled", full=True)
        tab.locator("button.btn-primary").click()
        tab.wait_for_url(re.compile(r"flash=checkin_saved"), timeout=WAIT)
        mobile.settle()
        mobile.shot("overview_after_checkin", full=True)
        if tab.get_by_role("link", name="Przejrzyj i zdecyduj").count():
            tab.get_by_role("link", name="Przejrzyj i zdecyduj").first.click()
            tab.wait_for_url("**/recommendations/**")
            widths["recommendation"] = tab.evaluate(
                "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
            )
            mobile.shot("recommendation", full=False)
            mobile.shot("recommendation_full", full=True)
            tab.locator('button[name="verdict"][value="approve"]').click()
            tab.wait_for_url(re.compile(r"flash="), timeout=WAIT)
            mobile.settle()
            mobile.shot("after_approve", full=False)
        visit(f"/projects/{project8}/history", "history")
        visit(f"/projects/{project8}/settings", "settings")
        visit("/simulator", "simulator")
        visit("/how-it-works", "how")
        d.note(kind="case", case="phone: sideways scroll in px", shown=widths)
        phone.close()

        write_log(out / "wrong-log.json", d.log)
        context.close()


if __name__ == "__main__":
    sys.exit(main())
