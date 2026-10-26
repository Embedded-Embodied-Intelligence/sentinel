"""The usability test's five tasks done by a script (WP9c; docs/usability/protocol-pl.md): create
a project from the CSV template, tell when it will most likely finish, report an absence, decide
on the recommendation, and run the simulator to the end. It counts the clicks and the form
fields of each task in the Polish pages and times it: the baseline the participants are compared
with (no reading, no thinking; the server's work included).

    uv run pytest -q -m e2e -k usability -s     # prints the table
    SENTINEL_TASK_TIMING=timing.json uv run pytest -q -m e2e -k usability   # also keeps it
"""

import json
import os
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pytest
from e2e_env import Server, chromium_env, serve

from sentinel.app.config import AppConfig

sync_api = pytest.importorskip("playwright.sync_api")
expect = sync_api.expect

pytestmark = pytest.mark.e2e
CSV = Path(__file__).resolve().parents[1] / "docs" / "usability" / "projekt-testowy.csv"
TEAM = (
    "Anna Nowak, Programista\n"
    "Bartosz Kowalski, Programista\n"
    "Celina Wiśniewska, Programista\n"
    "Dawid Lewandowski, Tester\n"
    "Ewa Zielińska, Projektant"
)
SLOW = 180_000  # ms: a simulator run to the end on a busy machine


@dataclass
class Task:
    """A task of the protocol: clicks (also choices and file picks), form fields filled and the
    seconds from its first action to its visible result."""

    number: int
    name: str
    clicks: int = 0
    fields: int = 0
    seconds: float = 0.0
    done: bool = False


class Recorder:
    def __init__(self) -> None:
        self.tasks: list[Task] = []

    @contextmanager
    def task(self, name: str) -> Iterator[Task]:
        task = Task(len(self.tasks) + 1, name)
        began = time.perf_counter()
        yield task
        task.seconds = round(time.perf_counter() - began, 1)
        task.done = True
        self.tasks.append(task)


def click(task: Task, locator: Any) -> None:
    locator.click()
    task.clicks += 1


def fill(task: Task, locator: Any, value: str) -> None:
    locator.fill(value)
    task.fields += 1


@pytest.fixture(scope="module")
def server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Server]:
    yield from serve(AppConfig(data_dir=tmp_path_factory.mktemp("usability"), workers=1))


def test_the_five_tasks_of_the_usability_protocol(server: Server) -> None:
    with sync_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(env=chromium_env())
        except sync_api.Error:  # pragma: no cover - depends on the machine
            pytest.skip("Chromium for Playwright cannot start (docs/deploy.md, section 4)")
        context = browser.new_context(viewport={"width": 1280, "height": 800}, locale="pl-PL")
        context.set_default_timeout(30_000)
        page = context.new_page()
        recorder = Recorder()
        page.goto(server.base + "/")

        with recorder.task("Utwórz projekt z szablonu CSV") as task:
            click(task, page.get_by_role("link", name="Nowy projekt").first)
            fill(task, page.get_by_label("Nazwa projektu"), "Aplikacja rezerwacji wizyt")
            fill(task, page.get_by_label("Data rozpoczęcia"), "2026-11-02")
            fill(task, page.get_by_label("Termin", exact=True), "2026-12-04")
            click(task, page.get_by_role("button", name="Dalej"))
            page.wait_for_url(re.compile(r"/setup/team$"))
            click(task, page.get_by_text("Wklej listę osób"))
            fill(task, page.get_by_label("Jedna osoba w wierszu: imię, rola"), TEAM)
            click(task, page.get_by_role("button", name="Dodaj te osoby"))
            expect(page.get_by_label("Imię i nazwisko osoby 5")).to_have_value("Ewa Zielińska")
            click(task, page.get_by_role("button", name="Dalej"))
            page.wait_for_url(re.compile(r"/setup/tasks$"))
            click(task, page.get_by_role("link", name="Importuj arkusz"))
            page.get_by_label("Plik arkusza (CSV)").set_input_files(str(CSV))
            task.clicks += 1  # choosing the file
            click(task, page.get_by_role("button", name="Importuj zadania"))
            page.wait_for_url(re.compile(r"tab=manual"))
            click(task, page.get_by_role("button", name="Utwórz plan"))
            page.wait_for_url(re.compile(r"flash=plan_ready"))
            expect(page.locator("#forecast .headline")).to_contain_text("Szansa")

        with recorder.task("Kiedy projekt najprawdopodobniej się skończy?") as task:
            likely = page.locator("dl.kpis > div", has_text="Najbardziej prawdopodobny koniec")
            expect(likely.locator("dd")).to_have_text(re.compile(r"\d+\s\w+"))

        with recorder.task("Zgłoś nieobecność") as task:
            click(task, page.get_by_role("link", name="Raport statusu").first)
            fill(task, page.get_by_label("Stan na koniec dnia"), "2026-11-04")
            workshop = page.locator("fieldset.task-row", has_text="Warsztat z klientem")
            click(task, workshop.get_by_label("Gotowe", exact=True))
            fill(task, workshop.get_by_label("Zakończone dnia"), "2026-11-03")
            api = page.locator("fieldset.task-row", has_text="Baza danych i API")
            click(task, api.get_by_label("W toku"))
            fill(task, api.get_by_label("Wykonana część"), "15")
            click(task, page.get_by_role("button", name="Dodaj nieobecność"))
            page.get_by_label("Osoba", exact=True).select_option(
                label="Bartosz Kowalski (Programista)"
            )
            task.clicks += 1  # choosing the person
            fill(task, page.get_by_label("Nieobecność od"), "2026-11-05")
            fill(task, page.get_by_label("Powrót (jeśli wiadomo)"), "2026-11-16")
            click(task, page.get_by_role("button", name="Zapisz raport"))
            page.wait_for_url(re.compile(r"flash=checkin_saved"))

        with recorder.task("Zdecyduj o rekomendacji") as task:
            waiting = page.get_by_role("heading", name="Czeka na Twoją decyzję")
            expect(waiting).to_be_visible(timeout=60_000)
            click(task, page.get_by_role("link", name="Zobacz rekomendację"))
            expect(page.locator("#rec-title")).to_contain_text("Zastępstwo: Celina Wiśniewska")
            click(task, page.get_by_role("button", name="Zatwierdź"))
            page.wait_for_url(re.compile(r"flash=approved"))

        if server.services.instances("j30"):
            with recorder.task("Symulator do końca: kto poradził sobie lepiej?") as task:
                click(task, page.get_by_role("link", name="Symulator", exact=True))
                click(task, page.get_by_role("button", name="Rozpocznij symulację"))
                page.wait_for_url(re.compile(r"/projects/[\w-]+$"), timeout=60_000)
                click(task, page.get_by_role("button", name="Do końca"))
                title = page.get_by_role("heading", name="Jak się skończyło")
                expect(title).to_be_visible(timeout=SLOW)
                expect(page.locator("table.compare")).to_contain_text("Nikt nie reaguje")
        browser.close()

    rows = [asdict(t) for t in recorder.tasks]
    print("\n| # | Task | Clicks | Fields | Seconds |\n| --- | --- | ---: | ---: | ---: |")
    for row in rows:
        print(
            f"| {row['number']} | {row['name']} | {row['clicks']} | {row['fields']} | "
            f"{row['seconds']} |"
        )
    target = os.environ.get("SENTINEL_TASK_TIMING")
    if target:
        Path(target).write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", "utf-8")
    assert len(recorder.tasks) >= 4 and all(t.done for t in recorder.tasks)  # 5 with PSPLIB
