"""End-to-end tests of the pages in a real browser (WP9b; Playwright with Chromium, axe-core
4.14.0 vendored under tests/vendor): a project created from a spreadsheet, a check-in with an
absence and the approved recommendation in the history; the simulator run to the end with its
comparison; the isolation of two demo visitors; a check-in by keyboard only; and an
accessibility scan of the main screens with no serious or critical violation.

The app is served by uvicorn in a thread with real background jobs. Run with
`uv run pytest -q -m e2e` (Chromium as installed by `uv run playwright install chromium`; its
system libraries without root by `scripts/setup_e2e_libs.sh`, found through `e2e_env`).
"""

import re
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from app_cases import small
from e2e_env import Server, chromium_env, serve

from sentinel.app import showcase
from sentinel.app.config import AppConfig, Limits
from sentinel.app.services import Services
from sentinel.app.store import LOCAL_SESSION

sync_api = pytest.importorskip("playwright.sync_api")
expect = sync_api.expect

pytestmark = pytest.mark.e2e
AXE = Path(__file__).parent / "vendor/axe-core-4.14.0/axe.min.js"
TASKS_CSV = (
    "id,name,duration_days,predecessors,optional,crew:Developer,crew:Tester\n"
    "T1,Build API,6,,no,2,0\n"
    "T2,Build UI,3,,no,1,0\n"
    "T3,Test,3,T1 T2,no,1,1\n"
)
SLOW = 180_000  # ms: a simulator run to the end on a busy machine


@pytest.fixture(scope="module")
def browser() -> Iterator[Any]:
    with sync_api.sync_playwright() as playwright:
        try:
            chromium = playwright.chromium.launch(env=chromium_env())
        except sync_api.Error:  # pragma: no cover - depends on the machine
            pytest.skip(
                "Chromium for Playwright cannot start: run `uv run playwright install chromium` "
                "(on Linux also scripts/setup_e2e_libs.sh, or "
                "`sudo apt-get install libnss3 libnspr4 libasound2t64`)"
            )
        yield chromium
        chromium.close()


@pytest.fixture(scope="module")
def local(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Server]:
    yield from serve(AppConfig(data_dir=tmp_path_factory.mktemp("local"), workers=1))


def _page(
    browser: Any,
    server: Server,
    language: str = "en",
    scheme: str = "light",
    width: int = 1280,
    height: int = 800,
) -> Any:
    context = browser.new_context(
        viewport={"width": width, "height": height}, color_scheme=scheme, locale="en-GB"
    )
    context.add_cookies([{"name": "sentinel_lang", "value": language, "url": server.base}])
    context.set_default_timeout(30_000)
    return context.new_page()


def _wait_job(services: Services, session: str, job_id: str) -> None:
    for _ in range(600):
        if services.job(session, job_id, "en").status in ("done", "failed"):
            return
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish")


def test_a_project_from_a_spreadsheet_to_an_approved_recommendation(
    browser: Any, local: Server
) -> None:
    page = _page(browser, local)
    page.goto(local.base + "/")
    page.get_by_role("link", name="Create a project").first.click()
    page.get_by_label("Project name").fill("Shop relaunch")
    page.get_by_label("Start date").fill("2026-11-02")
    page.get_by_label("Deadline").fill("2026-11-17")
    page.get_by_role("button", name="Next").click()
    page.wait_for_url(re.compile(r"/setup/team$"))
    page.get_by_text("Paste a list of people").click()
    page.get_by_label("One person per line: name, role").fill(
        "Ada, Developer\nBen, Developer\nCleo, Developer\nTom, Tester"
    )
    page.get_by_role("button", name="Add these people").click()
    expect(page.get_by_label("Name of person 4")).to_have_value("Tom")
    page.get_by_role("button", name="Next").click()
    page.wait_for_url(re.compile(r"/setup/tasks$"))
    page.get_by_role("link", name="Import a spreadsheet").click()
    page.get_by_label("Spreadsheet file (CSV)").set_input_files(
        files=[{"name": "tasks.csv", "mimeType": "text/csv", "buffer": TASKS_CSV.encode()}]
    )
    page.get_by_role("button", name="Import the tasks").click()
    page.wait_for_url(re.compile(r"tab=manual"))
    expect(page.get_by_label("Name of task 3")).to_have_value("Test")
    page.get_by_role("button", name="Create the plan").click()
    page.wait_for_url(re.compile(r"flash=plan_ready"))
    expect(page.locator("#forecast .headline")).to_contain_text("Chance of meeting the deadline")
    page.get_by_role("link", name="Check-in").first.click()
    page.get_by_label("Status at the end of").fill("2026-11-04")
    api = page.locator("fieldset.task-row", has_text="Build API")
    api.get_by_label("In progress").check()
    api.get_by_label("Share done").fill("30")
    build_ui = page.locator("fieldset.task-row", has_text="Build UI")
    build_ui.get_by_label("Done", exact=True).check()
    build_ui.get_by_label("Finished on").fill("2026-11-04")
    page.get_by_role("button", name="Add an absence").click()
    page.get_by_label("Person", exact=True).select_option(label="Ada (Developer)")
    page.get_by_label("Away from").fill("2026-11-05")
    page.get_by_label("Back on (if known)").fill("2026-11-16")
    page.get_by_role("button", name="Save the check-in").click()
    page.wait_for_url(re.compile(r"flash=checkin_saved"))
    expect(page.get_by_role("heading", name="Waiting for your decision")).to_be_visible(
        timeout=60_000
    )
    page.get_by_role("link", name="Review and decide").click()
    expect(page.locator("#rec-title")).to_have_text(
        "Substitute: Cleo takes over Ada's part in “Build API”"
    )
    page.get_by_role("button", name="Approve").click()
    page.wait_for_url(re.compile(r"flash=approved"))
    expect(page.locator("#flash")).to_contain_text("Approved")
    page.get_by_role("link", name="History", exact=True).click()
    expect(page.get_by_text("You approved: Substitute: Cleo takes over")).to_be_visible()
    page.context.close()


def test_the_simulator_runs_to_the_end_and_compares(browser: Any, local: Server) -> None:
    if not local.services.instances("j30"):
        pytest.skip("PSPLIB data not available (run scripts/fetch_psplib.py)")
    page = _page(browser, local)
    page.goto(local.base + "/simulator")
    page.get_by_role("button", name="Start the simulation").click()
    page.wait_for_url(re.compile(r"/projects/[\w-]+$"), timeout=60_000)
    page.get_by_role("button", name="5 days").click()
    expect(page.locator(".sim-day")).to_contain_text("Day 5 of about", timeout=SLOW)
    page.wait_for_url(re.compile(r"/projects/[\w-]+$"), timeout=60_000)
    page.get_by_role("button", name="To the end").click()
    expect(page.get_by_role("heading", name="How it ended")).to_be_visible(timeout=SLOW)
    table = page.locator("table.compare")
    expect(table).to_contain_text("Nobody reacts")
    expect(table).to_contain_text("Sentinel")
    expect(page.locator(".timeline")).to_contain_text("Finished on")
    page.get_by_role("button", name="Show the report").click()
    report = page.get_by_role("link", name="Open the report (new tab)")
    expect(report).to_be_visible(timeout=60_000)
    assert "/cockpit.html" in (report.get_attribute("href") or "")
    page.context.close()


def test_a_run_can_be_left_reopened_and_cancelled(browser: Any, local: Server) -> None:
    """QA-03: back and forward during a run to the end, the page reopened at once, and Cancel."""
    if not local.services.instances("j30"):
        pytest.skip("PSPLIB data not available (run scripts/fetch_psplib.py)")
    page = _page(browser, local)
    page.goto(local.base + "/simulator")
    page.get_by_role("button", name="Start the simulation").click()
    page.wait_for_url(re.compile(r"/projects/[\w-]+$"), timeout=60_000)
    url = page.url
    page.get_by_role("button", name="To the end").click()
    expect(page.get_by_text("This takes about half a minute")).to_be_visible(timeout=30_000)
    page.goto(local.base + "/simulator")
    began = time.perf_counter()
    page.goto(url)
    assert time.perf_counter() - began < 5  # the page does not wait for the run
    cancel = page.get_by_role("button", name="Cancel")
    expect(cancel).to_be_visible()
    cancel.click()
    expect(page.locator(".sim-day")).to_be_visible(timeout=60_000)
    expect(page.get_by_role("heading", name="How it ended")).to_have_count(0)
    page.context.close()


def test_two_demo_visitors_see_only_their_own_projects(
    browser: Any, tmp_path_factory: pytest.TempPathFactory
) -> None:
    config = AppConfig(
        data_dir=tmp_path_factory.mktemp("demo"),
        demo=True,
        workers=1,
        showcase=False,
        limits=Limits(projects_per_session=5, requests_per_minute=600),
    )
    for server in serve(config):
        first, second = _page(browser, server), _page(browser, server)
        first.goto(server.base + "/new")
        first.get_by_label("Project name").fill("Secret plan")
        first.get_by_label("Start date").fill("2026-11-02")
        first.get_by_role("button", name="Next").click()
        first.wait_for_url(re.compile(r"/setup/team$"))
        project = first.url.split("/projects/")[1].split("/")[0]
        first.goto(server.base + "/")
        expect(first.get_by_role("link", name="Secret plan")).to_be_visible()
        second.goto(server.base + "/")
        expect(second.get_by_role("heading", name="Start with your first project")).to_be_visible()
        response = second.goto(f"{server.base}/projects/{project}/setup/team")
        assert response is not None and response.status == 404
        expect(second.get_by_text("There is no such project.")).to_be_visible()
        api = second.request.get(f"{server.base}/api/projects/{project}")
        assert api.status == 404
        cookies = {c["name"]: c["value"] for c in first.context.cookies()}
        others = {c["name"]: c["value"] for c in second.context.cookies()}
        assert cookies["sentinel_session"] != others["sentinel_session"]
        first.context.close()
        second.context.close()


def _tab_to(page: Any, selector: str, limit: int = 120) -> None:
    """Press Tab until the element matching `selector` has the focus; check it is visible."""
    for _ in range(limit):
        page.keyboard.press("Tab")
        if page.evaluate(
            "s => document.activeElement && document.activeElement.matches(s)", selector
        ):
            outline = page.evaluate("() => getComputedStyle(document.activeElement).outlineStyle")
            assert outline != "none", f"no visible focus on {selector}"
            return
    raise AssertionError(f"Tab never reached {selector}")


def test_a_check_in_by_keyboard_only(browser: Any, local: Server) -> None:
    services = local.services
    pid = services.create(LOCAL_SESSION, small(), "en").id
    _wait_job(services, LOCAL_SESSION, services.plan(LOCAL_SESSION, pid, "en").id)
    page = _page(browser, local)
    page.goto(f"{local.base}/projects/{pid}/checkin")
    _tab_to(page, 'input[name="status_T1"]')  # a radio group is one Tab stop
    page.keyboard.press("ArrowRight")  # "Not started" -> "In progress"
    expect(page.locator('input[name="status_T1"][value="in_progress"]')).to_be_checked()
    _tab_to(page, "#percent-T1")
    for _ in range(25):
        page.keyboard.press("ArrowRight")
    expect(page.locator("#percent-T1-num")).to_have_value("25")
    _tab_to(page, 'button[data-add-row="away"]')
    page.keyboard.press("Enter")
    assert page.evaluate("() => document.activeElement.tagName") == "SELECT"
    page.keyboard.press("ArrowDown")  # the first person: Ada
    _tab_to(page, "button.btn-primary")
    page.keyboard.press("Enter")
    page.wait_for_url(re.compile(r"flash=checkin_saved"))
    view = services.live(LOCAL_SESSION, pid, "en")
    task = next(t for t in view.tasks if t.key == "T1")
    assert task.state in ("in_progress", "paused") and task.percent is not None
    assert [a.person for a in services.state(LOCAL_SESSION, pid).project.absences] == ["a"]
    page.context.close()


def _axe(page: Any) -> list[str]:
    page.add_script_tag(path=str(AXE))
    found = page.evaluate(
        """async () => (await axe.run(document, {resultTypes: ['violations']})).violations
            .map(v => ({id: v.id, impact: v.impact, nodes: v.nodes.length, help: v.help}))"""
    )
    return [
        f"{v['id']} ({v['impact']}, {v['nodes']} elements): {v['help']}"
        for v in found
        if v["impact"] in ("serious", "critical")
    ]


def _showcase(local: Server) -> tuple[str, int | None, str]:
    """The showcase project, its open recommendation and a draft of it."""
    services = local.services
    name = showcase.definition("pl").name
    if not any(p.name == name for p in services.projects(LOCAL_SESSION)):
        showcase.install(services)
        assert services.showcase is not None
        services.showcase(LOCAL_SESSION, "pl")
    pid = next(p.id for p in services.projects(LOCAL_SESSION) if p.name == name)
    seq = services.live(LOCAL_SESSION, pid, "pl").open_recommendation
    found = [p.id for p in services.projects(LOCAL_SESSION) if p.name == "Draft"]
    draft = (
        found[0]
        if found
        else services.create(
            LOCAL_SESSION, showcase.definition("pl").model_copy(update={"name": "Draft"}), "pl"
        ).id
    )
    return pid, seq, draft


@pytest.mark.parametrize("language", ["pl", "en"])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_the_main_screens_have_no_serious_accessibility_violations(
    browser: Any, local: Server, scheme: str, language: str
) -> None:
    pid, seq, draft = _showcase(local)
    paths = [
        "/",
        "/new",
        f"/projects/{draft}/setup/team",
        f"/projects/{draft}/setup/tasks",
        f"/projects/{draft}/setup/tasks?tab=import",
        f"/projects/{draft}/setup/tasks?tab=describe",
        f"/projects/{pid}",
        f"/projects/{pid}/checkin",
        f"/projects/{pid}/recommendations/{seq}",
        f"/projects/{pid}/history",
        f"/projects/{pid}/settings",
        f"/projects/{pid}/delete",
        "/simulator",
        "/how-it-works",
        "/settings",
        "/projects/none",
    ]
    violations = {}
    for width in (1280, 390):
        page = _page(browser, local, language, scheme, width=width, height=844)
        for path in paths:
            page.goto(local.base + path)
            page.wait_for_load_state("networkidle")
            found = _axe(page)
            if found:
                violations[f"{width} {path}"] = found
        page.context.close()
    assert violations == {}


@pytest.mark.parametrize("width", [320, 390, 768])
def test_only_the_chart_scrolls_sideways_on_a_small_screen(
    browser: Any, local: Server, width: int
) -> None:
    """docs/design/brief.md, section 7: no horizontal page scroll down to 320 px."""
    pid, seq, draft = _showcase(local)
    paths = [
        "/",
        "/new",
        f"/projects/{draft}/setup/team",
        f"/projects/{draft}/setup/tasks",
        f"/projects/{pid}",
        f"/projects/{pid}/checkin",
        f"/projects/{pid}/recommendations/{seq}",
        f"/projects/{pid}/history",
        f"/projects/{pid}/settings",
        "/simulator",
        "/how-it-works",
        "/settings",
    ]
    wide = {}
    page = _page(browser, local, "pl", width=width, height=700)
    for path in paths:
        page.goto(local.base + path)
        page.wait_for_load_state("networkidle")
        overflow = page.evaluate(
            "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        if overflow > 0:
            wide[path] = overflow
    assert wide == {}
    page.context.close()


def test_the_drawer_traps_the_focus_and_closes_on_escape(browser: Any, local: Server) -> None:
    page = _page(browser, local, "en", width=390, height=844)
    page.goto(local.base + "/how-it-works")
    expect(page.locator("#sidebar")).to_be_hidden()
    page.get_by_role("button", name="Menu").click()
    expect(page.locator("#sidebar")).to_be_visible()
    inside = "() => document.getElementById('sidebar').contains(document.activeElement)"
    for _ in range(14):
        page.keyboard.press("Tab")
        assert page.evaluate(inside)
    page.keyboard.press("Escape")
    expect(page.locator("#sidebar")).to_be_hidden()
    assert page.evaluate("() => document.activeElement.hasAttribute('data-drawer-open')")
    page.context.close()


def test_a_toast_tells_the_result_and_can_be_closed(browser: Any, local: Server) -> None:
    pid, _, _ = _showcase(local)
    page = _page(browser, local, "en")
    page.goto(f"{local.base}/projects/{pid}?flash=rejected")
    toast = page.locator("#flash [data-toast]")
    expect(toast).to_contain_text("Rejected")
    expect(toast.get_by_role("link", name="See in the history")).to_be_visible()
    assert page.locator("#flash").get_attribute("role") == "status"
    page.get_by_role("button", name="Close").first.click()
    expect(toast).to_have_count(0)
    page.context.close()


def test_the_check_in_counts_its_changes_and_its_button_says_so(
    browser: Any, local: Server
) -> None:
    services = local.services
    pid = services.create(LOCAL_SESSION, small(), "en").id
    _wait_job(services, LOCAL_SESSION, services.plan(LOCAL_SESSION, pid, "en").id)
    page = _page(browser, local)
    page.goto(f"{local.base}/projects/{pid}/checkin")
    save = page.locator("button.btn-primary")
    expect(save).to_have_text("Save the check-in (no changes)")
    expect(page.locator("[data-change-count]")).to_have_text("No changes")
    page.locator("fieldset.task-row", has_text="Build API").get_by_label("In progress").check()
    expect(save).to_have_text("Save the check-in")
    expect(page.locator("[data-change-count]")).to_have_text("1 change")
    page.get_by_role("button", name="Add an absence").click()
    expect(page.locator("[data-change-count]")).to_have_text("2 changes")
    expect(page.locator("#away-count")).to_have_text("(1)")
    page.locator("#percent-T1-num").fill("40")
    assert page.locator("#percent-T1").input_value() == "40"
    page.get_by_role("button", name="Remove").first.click()
    expect(page.locator("#away-count")).to_have_text("(0)")
    page.context.close()


def test_leaving_a_half_filled_form_asks_first(browser: Any, local: Server) -> None:
    """QA-07: a tab, the sidebar or the language switch used to drop a half-filled check-in."""
    services = local.services
    pid = services.create(LOCAL_SESSION, small(deadline=None), "en").id
    _wait_job(services, LOCAL_SESSION, services.plan(LOCAL_SESSION, pid, "en").id)
    page = _page(browser, local)
    asked: list[str] = []
    answer = {"leave": False}

    def on_dialog(dialog: Any) -> None:
        asked.append(dialog.type)
        dialog.accept() if answer["leave"] else dialog.dismiss()

    page.on("dialog", on_dialog)
    url = f"{local.base}/projects/{pid}/checkin"
    page.goto(url)
    history = page.get_by_role("link", name="History", exact=True)
    history.click()  # nothing entered: no question
    page.wait_for_url(re.compile(r"/history$"))
    assert asked == []
    page.goto(url)
    row = page.locator("fieldset.task-row", has_text="Build API")
    row.get_by_label("In progress").check()
    history.click()  # stay
    page.wait_for_timeout(500)
    assert asked == ["beforeunload"] and page.url == url
    expect(row.get_by_label("In progress")).to_be_checked()
    page.get_by_role("link", name="Cancel").click()  # the way out asks nothing
    page.wait_for_url(re.compile(rf"/projects/{pid}$"))
    assert asked == ["beforeunload"]
    page.goto(url)
    row.get_by_label("In progress").check()
    page.locator("button.btn-primary").click()  # saving asks nothing
    page.wait_for_url(re.compile(r"flash=checkin_saved"))
    assert asked == ["beforeunload"]
    page.goto(f"{local.base}/projects/{pid}/settings")
    page.get_by_label("Project name").fill("Changed")
    answer["leave"] = True
    page.get_by_role("link", name="History", exact=True).click()
    page.wait_for_url(re.compile(r"/history$"))
    assert asked == ["beforeunload", "beforeunload"]
    page.context.close()


def test_the_task_pickers_and_the_wizards_live_hints(browser: Any, local: Server) -> None:
    services = local.services
    pid = services.create(LOCAL_SESSION, small(), "en").id
    page = _page(browser, local)
    page.goto(f"{local.base}/projects/{pid}/setup/basics")
    rule = page.locator("[data-deadline-rule]")
    page.get_by_label("Deadline").fill("2026-12-14")
    expect(rule).to_contain_text("6 weeks")
    page.get_by_label("Deadline").fill("2026-10-01")
    expect(rule).to_contain_text("cannot be before")
    expect(page.locator("#deadline-echo")).to_contain_text("1\u00a0Oct 2026")
    page.goto(f"{local.base}/projects/{pid}/setup/tasks")
    after = page.locator('[data-after-picker][data-row="2"]')
    after.locator("summary").click()
    after.get_by_label("1. Build API").check()
    expect(after.locator(".pop-value")).to_have_text("Build API")
    assert after.locator("input[data-after-value]").input_value() == "1"
    page.keyboard.press("Escape")
    expect(after.locator("[data-after-body]")).to_be_hidden()
    expect(page.locator("#save-status")).to_contain_text("Draft saved", timeout=10_000)
    tasks = {t.key: t for t in services.state(LOCAL_SESSION, pid).project.definition.tasks}
    assert tasks["T2"].predecessors == ("T1",)
    page.context.close()


def test_the_plan_can_be_read_as_a_table_and_settings_warn_of_unsaved_changes(
    browser: Any, local: Server
) -> None:
    pid, _, _ = _showcase(local)
    page = _page(browser, local, "en")
    page.goto(f"{local.base}/projects/{pid}")
    expect(page.locator(".gantt-plot")).to_be_visible()
    expect(page.locator(".view-table table")).to_be_hidden()
    page.get_by_label("Table").check()
    expect(page.locator(".view-table table")).to_be_visible()
    expect(page.locator(".gantt-plot")).to_be_hidden()
    page.goto(f"{local.base}/projects/{pid}/settings")
    bar = page.locator("[data-unsaved-bar]")
    expect(bar).to_be_hidden()
    page.get_by_label("Project name").fill("Renamed")
    expect(bar).to_be_visible()
    page.get_by_role("button", name="Undo the changes").click()
    expect(bar).to_be_hidden()
    expect(page.get_by_label("Project name")).not_to_have_value("Renamed")
    page.context.close()
