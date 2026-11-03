"""Browser replays of the faults of the WP12 test (docs/qa/raport-ceo-chrome-pl.md, B1-B19), each
asserting what happens now, and the one try at B20. The AI items (B6-B8) need a model and are
checked with a scripted one in tests/test_app_ai_message.py and live in docs/qa/ai/wp12-*.json.
Run with `uv run pytest -q -m e2e`."""

# ruff: noqa: F811 - the fixtures of test_ui_e2e are imported, and their names are parameters

import re
from datetime import date
from typing import Any

import pytest
from app_cases import ABSENCE_CHECKIN, DEV, small
from e2e_env import Server
from test_ui_e2e import _page, _wait_job, browser, local  # noqa: F401 - the module's fixtures

from sentinel.app.models import CheckIn, Person, ProjectDefinition, Task
from sentinel.app.store import LOCAL_SESSION

sync_api = pytest.importorskip("playwright.sync_api")
expect = sync_api.expect

pytestmark = pytest.mark.e2e


def _planned(local: Server, definition: ProjectDefinition) -> str:
    services = local.services
    pid = services.create(LOCAL_SESSION, definition, "en").id
    _wait_job(services, LOCAL_SESSION, services.plan(LOCAL_SESSION, pid, "en").id)
    return pid


def _checked(local: Server, pid: str, checkin: CheckIn) -> None:
    result = local.services.checkin(LOCAL_SESSION, pid, checkin, "en")
    if result.recommendation_job is not None:
        _wait_job(local.services, LOCAL_SESSION, result.recommendation_job.id)


def _after(text: str) -> str:
    """The value after the arrow of a chip, without the words a screen reader hears after it."""
    after = text.split("→", 1)[1] if "→" in text else text
    return after.strip().splitlines()[0].strip()


def test_b1_the_wizard_keeps_its_fields_across_the_language_switch(
    browser: Any, local: Server
) -> None:
    page = _page(browser, local, language="pl")
    page.goto(local.base + "/new")
    page.locator("#name").fill("Strona sklepu")
    page.locator("#start").fill("2026-11-09")
    page.locator("#deadline").fill("2026-12-18")
    page.locator('a[hreflang="en"]').first.click()
    page.wait_for_url(re.compile(r"/new"))
    expect(page.locator("#name")).to_have_value("Strona sklepu")
    expect(page.locator("#start")).to_have_value("2026-11-09")
    expect(page.locator("#deadline")).to_have_value("2026-12-18")
    page.context.close()


def test_b2_b3_b4_a_card_promises_what_the_overview_then_shows(browser: Any, local: Server) -> None:
    """B4: the card's finish before the change is the overview's; B3: after the approval the
    overview shows the card's chance and finish; B2: the plan CSV has no unfinished task in the
    past."""
    pid = _planned(local, small())
    _checked(local, pid, ABSENCE_CHECKIN)
    page = _page(browser, local)
    page.goto(f"{local.base}/projects/{pid}")
    likely = page.locator("#kpis div", has_text="Most likely finish").locator(".kpi-value")
    expect(likely).to_be_visible()
    card = page.locator(".rec-card").first
    chance = card.locator(".delta-chip", has_text="Chance").inner_text()
    finish = card.locator(".delta-chip", has_text="Most likely finish").inner_text()
    before_finish = finish.split("finish", 1)[1].split("→", 1)[0].strip()
    assert likely.inner_text().strip() == before_finish  # B4
    promised_chance, promised_finish = _after(chance), _after(finish)
    card.get_by_role("link", name="Review and decide").click()
    page.get_by_role("button", name=re.compile("^Approve")).click()
    page.wait_for_url(re.compile(r"flash=approved"))
    headline = page.locator("#forecast .headline-number")
    expect(headline).to_have_text(promised_chance, timeout=60_000)
    expect(likely).to_have_text(promised_finish)  # B3
    csv = page.request.get(f"{local.base}/api/projects/{pid}/plan.csv").text()
    status = "2026-11-04"  # ABSENCE_CHECKIN's date
    for row in csv.splitlines()[1:]:
        cells = row.split(",")
        if cells[2] in ("unstarted", "started"):
            assert cells[4] > status, row  # B2: every unfinished task ends after the report
    page.context.close()


def test_b5_a_plan_across_christmas_skips_the_holidays(browser: Any, local: Server) -> None:
    definition = ProjectDefinition(
        name="Christmas",
        start=date(2026, 12, 21),
        deadline=date(2027, 1, 15),
        team=(Person(key="a", name="Ada", role=DEV),),
        tasks=(Task(key="T1", name="Build", duration=5, crew={DEV: 1}),),
    )
    pid = _planned(local, definition)
    page = _page(browser, local, language="pl")
    page.goto(f"{local.base}/projects/{pid}/history")
    expect(page.get_by_text("Utworzono plan: bez zakłóceń kończy się wt. 29 gru")).to_be_visible()
    page.context.close()


def test_b9_b12_b16_a_report_without_progress_asks_and_keeps_its_count(
    browser: Any, local: Server
) -> None:
    """B16: "finished on" follows the report's date; B12: after a refused save the counter
    still counts the change; B9: a report with no progress on a task in progress asks first."""
    pid = _planned(local, small())
    _checked(local, pid, ABSENCE_CHECKIN)  # Build API in progress at 30 %
    page = _page(browser, local)
    page.goto(f"{local.base}/projects/{pid}/checkin")
    page.locator("#date").fill("2026-11-06")
    test = page.locator("fieldset.task-row", has_text="Test")
    expect(test.locator("input[data-follow-date]")).to_have_value("2026-11-06")  # B16
    test.get_by_label("In progress").check()
    count = page.locator("[data-change-count]")
    expect(count).to_have_text("1 change")
    page.locator("#date").fill("2030-01-07")
    page.get_by_role("button", name="Save the check-in").click()
    expect(page.get_by_text("Status at the end of", exact=False).first).to_be_visible()
    expect(page.locator(".callout-warn").first).to_be_visible()
    expect(count).to_have_text("1 change")  # B12
    test = page.locator("fieldset.task-row", has_text="Test")
    test.get_by_label("Not started").check()
    page.locator("#date").fill("2026-11-06")
    page.get_by_role("button", name="Save the check-in").click()
    expect(page.get_by_text("Has nothing moved on since")).to_be_visible()  # B9
    page.get_by_role("button", name="Yes, no progress").click()
    page.wait_for_url(re.compile(r"flash=checkin_saved"))
    page.context.close()


def test_b10_leaving_during_a_save_is_not_silent(browser: Any, local: Server) -> None:
    pid = _planned(local, small(deadline=None))
    page = _page(browser, local)
    dialogs: list[str] = []
    page.on("dialog", lambda dialog: (dialogs.append(dialog.type), dialog.dismiss()))
    page.goto(f"{local.base}/projects")
    page.goto(f"{local.base}/projects/{pid}/checkin")
    page.locator("fieldset.task-row", has_text="Build API").get_by_label("In progress").check()
    page.get_by_role("button", name="Save the check-in").click()
    page.go_back()
    page.wait_for_timeout(1500)
    saved = local.services.state(LOCAL_SESSION, pid).project.checkins
    assert dialogs or saved, "the report was neither saved nor did the page ask"
    page.context.close()


def test_b11_enter_in_the_role_field_adds_the_role(browser: Any, local: Server) -> None:
    services = local.services
    draft = ProjectDefinition(
        name="Roles", start=date(2026, 11, 2), team=(Person(key="P1", name="Ada", role=DEV),)
    )
    pid = services.create(LOCAL_SESSION, draft, "en").id
    page = _page(browser, local)
    page.goto(f"{local.base}/projects/{pid}/setup/team")
    page.locator("#new_role").fill("Tester")
    page.locator("#new_role").press("Enter")
    expect(page.locator(".role-name", has_text="Tester")).to_be_visible()
    expect(page.locator(".role-name", has_text=DEV)).to_be_visible()  # the first role kept
    page.context.close()


def test_b13_b15_a_share_says_what_it_is_saved_as_and_pickers_are_grouped(
    browser: Any, local: Server
) -> None:
    pid = _planned(local, small())
    page = _page(browser, local)
    page.goto(f"{local.base}/projects/{pid}/checkin")
    ui_row = page.locator("fieldset.task-row", has_text="Build UI")
    ui_row.get_by_label("In progress").check()
    ui_row.locator("input[data-range-for]").fill("60")
    expect(ui_row.locator("[data-saved-as]")).to_contain_text(
        "60 % → saved as 67 %, 2 of 3 days"
    )  # B13
    page.get_by_role("button", name="Add a task that grew").click()
    groups = page.locator("#grow-list select optgroup")
    labels = [groups.nth(i).get_attribute("label") for i in range(groups.count())]
    assert labels == ["Not started: a new estimate"]  # B15: none in progress yet, none done
    page.context.close()


def test_b14_a_postponed_proposal_waits_as_its_message_says(browser: Any, local: Server) -> None:
    pid = _planned(local, small())
    _checked(local, pid, ABSENCE_CHECKIN)
    page = _page(browser, local)
    page.goto(f"{local.base}/projects/{pid}")
    page.locator(".rec-card").first.get_by_role("link", name="Review and decide").click()
    page.get_by_role("button", name="Decide later").click()
    page.wait_for_url(re.compile(r"flash=later"))
    expect(page.locator("#flash")).to_contain_text("until the next check-in")
    expect(page.locator(".rec-card").first).to_be_visible()
    page.context.close()


def test_b17_a_task_at_both_ends_says_so(browser: Any, local: Server) -> None:
    pid = _planned(local, small())
    page = _page(browser, local)
    page.goto(f"{local.base}/projects/{pid}/checkin")
    page.get_by_role("button", name="Add a new task").click()
    page.get_by_label("Task name").fill("Privacy banner")
    page.get_by_label("Working days").fill("1")
    page.get_by_label("Comes after").select_option("T3")
    page.get_by_label("Must be done before").select_option("T3")
    page.get_by_role("button", name="Save the check-in").click()
    expect(page.get_by_text("cannot come both after and before")).to_be_visible()
    page.context.close()


def test_b18_b19_a_long_name_counts_and_the_sidebar_keeps_its_order(
    browser: Any, local: Server
) -> None:
    first = _planned(local, small().model_copy(update={"name": "Alpha"}))
    second = _planned(local, small(deadline=None).model_copy(update={"name": "Beta"}))
    page = _page(browser, local)
    page.goto(local.base + "/new")
    page.locator("#name").fill("x" * 110)
    expect(page.get_by_text("110 of 120 characters")).to_be_visible()  # B18
    orders = []
    for url in (f"/projects/{first}", f"/projects/{second}/history", f"/projects/{first}/checkin"):
        page.goto(local.base + url)
        # The sidebar lists five projects: whichever they are, in the same order on every screen.
        orders.append([a.get_attribute("title") for a in page.locator("a.nav-project").all()])
    assert len(orders[0]) >= 2 and orders[0] == orders[1] == orders[2], orders  # B19
    page.context.close()


def test_b20_ticks_of_the_after_picker_survive_escape(browser: Any, local: Server) -> None:
    """B20 was not reproducible in the test; one try: twelve tasks, the picker of row 12."""
    services = local.services
    tasks = tuple(
        Task(key=f"T{i}", name=f"Task {i}", duration=1, crew={DEV: 1}) for i in range(1, 13)
    )
    draft = ProjectDefinition(
        name="Twelve",
        start=date(2026, 11, 2),
        team=(Person(key="P1", name="Ada", role=DEV),),
        tasks=tasks,
    )
    pid = services.create(LOCAL_SESSION, draft, "en").id
    page = _page(browser, local)
    page.goto(f"{local.base}/projects/{pid}/setup/tasks?tab=manual")
    row = page.locator("tbody tr").nth(11)
    picker = row.locator("td.cell-after details")
    picker.locator("summary").click()
    boxes = picker.locator("input[type=checkbox]")
    boxes.nth(0).check()
    boxes.nth(1).check()
    page.keyboard.press("Escape")
    picker.locator("summary").click()
    expect(boxes.nth(0)).to_be_checked()
    expect(boxes.nth(1)).to_be_checked()
    page.context.close()
