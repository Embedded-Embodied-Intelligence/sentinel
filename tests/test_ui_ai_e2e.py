"""The AI features in a real browser with a scripted model (WP11; with real models:
`scripts/ai_live.py`): a description to a plan, a check-in message read twice, refused and saved,
an explanation with its badge, and every form still working after the model has failed. The live
runs found these broken: a job's polling replaced the whole check-in form, a second read did
nothing, and a role outside the team disappeared from the plan."""

import json
import re
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from e2e_env import Server, chromium_env, serve

from sentinel.app.config import AppConfig
from sentinel.app.llm import LlmSettings
from sentinel.llm import FakeLlmClient, LlmCache, LlmClient, LlmError, Message

sync_api = pytest.importorskip("playwright.sync_api")
expect = sync_api.expect

pytestmark = pytest.mark.e2e
WAIT = 120_000  # ms: a recommendation behind the threat lists of the projects before it
TEAM = "Ania Nowak, Programista\nBartek Zieliński, Programista\nCela Lis, Tester\nDarek Wit, Tester"
ACTIVITIES = [
    {"name": "Analiza", "duration_days": 2, "crew": {"testerka": 1}, "predecessors": []},
    {"name": "Logowanie", "duration_days": 6, "crew": {"programista": 1}, "predecessors": []},
    {"name": "Testy", "duration_days": 2, "crew": {"testerka": 1}, "predecessors": ["Logowanie"]},
]
EXTRACTION = {
    "team": [{"role": "programista", "count": 2}, {"role": "testerka", "count": 1}],
    "activities": ACTIVITIES,
}
WITH_DRIVER = {
    "team": [{"role": "kierowca", "count": 1}],
    "activities": [
        {"name": "Dostawa", "duration_days": 2, "crew": {"kierowca": 1}, "predecessors": []}
    ],
}


class Model:
    """What the scripted model does next: `fail` raises its error once."""

    def __init__(self) -> None:
        self.fail: LlmError | None = None
        self.invalid = False
        self.asked: list[str] = []

    def answer(self, messages: Sequence[Message]) -> str:
        system, user = messages[0].content, messages[1].content
        self.asked.append(user)
        if self.fail is not None:
            error, self.fail = self.fail, None
            raise error
        if self.invalid:
            return "to nie jest JSON"
        if system.startswith("You extract"):
            return json.dumps(WITH_DRIVER if "kierowca" in user else EXTRACTION)
        if system.startswith("You turn"):
            worker = re.search(r"(\d+) Ania", user)
            running = re.search(r'(\d+) "Logowanie": running', user)
            return json.dumps(
                {
                    "events": [
                        {
                            "type": "absence",
                            "worker": int(worker[1]) if worker else 0,
                            "return_day": None,
                        },
                        {"type": "work_increase", "activity": int(running[1]), "factor": 1.5}
                        if running
                        else {"type": "absence", "worker": 2, "return_day": None},
                    ]
                }
            )
        record = re.search(r"Chosen action: (\S+)", user)
        return json.dumps(
            {
                "summary": "The plan stays (NOOP).",
                "cited_facts": [
                    {"kind": "chosen_action", "value": record[1] if record else "NOOP"},
                    {"kind": "deciding_component", "value": "on_time"},
                ],
            }
        )


@pytest.fixture(scope="module")
def browser() -> Iterator[Any]:
    with sync_api.sync_playwright() as playwright:
        try:
            chromium = playwright.chromium.launch(env=chromium_env())
        except sync_api.Error:  # pragma: no cover - depends on the machine
            pytest.skip("Chromium for Playwright cannot start: see docs/deploy.md, section 4")
        yield chromium
        chromium.close()


@pytest.fixture(scope="module")
def model() -> Model:
    return Model()


@pytest.fixture(scope="module")
def local(tmp_path_factory: pytest.TempPathFactory, model: Model) -> Iterator[Server]:
    def factory(settings: LlmSettings, cache: LlmCache) -> LlmClient:
        assert cache.store_prompts is False
        client = FakeLlmClient(model.answer, cache=cache)
        client.model = "scripted"
        return client

    data: Path = tmp_path_factory.mktemp("ai-e2e")
    config = AppConfig(data_dir=data, workers=3)
    settings = data / "settings.json"
    settings.write_text(json.dumps({"llm": {"provider": "ollama"}}), encoding="utf-8")
    yield from serve(config, llm_factory=factory)


def _page(browser: Any, base: str) -> Any:
    context = browser.new_context(viewport={"width": 1280, "height": 900}, locale="pl-PL")
    context.add_cookies([{"name": "sentinel_lang", "value": "pl", "url": base}])
    context.set_default_timeout(WAIT)
    return context.new_page()


def _draft(page: Any, base: str, name: str) -> str:
    page.goto(base + "/new")
    page.get_by_label("Nazwa projektu").fill(name)
    page.get_by_label("Data rozpoczęcia").fill("2026-10-05")
    page.get_by_label("Termin", exact=True).fill("2026-11-20")
    page.get_by_role("button", name="Dalej").click()
    page.wait_for_url("**/setup/team")
    page.get_by_text("Wklej listę osób").click()
    page.get_by_label("Jedna osoba w wierszu").fill(TEAM)
    page.get_by_role("button", name="Dodaj te osoby").click()
    page.get_by_label("Imię i nazwisko osoby 4").wait_for(state="attached")
    page.get_by_role("button", name="Dalej").click()
    page.wait_for_url("**/setup/tasks")
    project = page.url.split("/projects/")[1].split("/")[0]
    page.goto(f"{base}/projects/{project}/setup/tasks?tab=describe")
    return str(project)


def _planned(page: Any, base: str, name: str) -> str:
    project = _draft(page, base, name)
    page.locator("#text").fill("Analiza, logowanie, testy.")
    page.get_by_role("button", name="Odczytaj opis").click()
    page.get_by_role("button", name="Użyj tych zadań").click()
    page.wait_for_url("**tab=manual**")
    page.get_by_role("button", name="Utwórz plan").click()
    page.wait_for_url(re.compile(r"flash=plan_ready"))
    page.wait_for_load_state("networkidle")
    return project


def _to_message_form(page: Any, base: str, project: str) -> None:
    page.goto(f"{base}/projects/{project}/checkin")
    page.wait_for_load_state("networkidle")
    page.get_by_label("Stan na koniec dnia").fill("2026-10-08")
    row = page.locator("fieldset.task-row", has_text="Logowanie").first
    row.get_by_label("W toku").check()


def test_a_description_becomes_a_plan_with_the_teams_roles(browser: Any, local: Server) -> None:
    page = _page(browser, local.base)
    project = _draft(page, local.base, "Opis")
    page.locator("#text").fill("Analiza, logowanie, testy.")
    page.get_by_role("button", name="Odczytaj opis").click()
    table = page.locator("#describe-result table")
    expect(table).to_contain_text("1 × Tester")  # "testerka" of the answer
    expect(table).to_contain_text("1 × Programista")
    expect(page.locator("#describe-result")).not_to_contain_text("Proponowany zespół")
    page.get_by_role("button", name="Użyj tych zadań").click()
    page.wait_for_url("**tab=manual**")
    page.get_by_role("button", name="Utwórz plan").click()
    page.wait_for_url(re.compile(r"flash=plan_ready"))
    view = page.request.get(f"{local.base}/api/projects/{project}").json()
    assert {t["name"]: t["crew"] for t in view["tasks"]}["Analiza"] == {"Tester": 1}
    page.context.close()


def test_a_role_outside_the_team_stops_the_plan_until_it_is_changed(
    browser: Any, local: Server
) -> None:
    page = _page(browser, local.base)
    project = _draft(page, local.base, "Rola spoza zespołu")
    page.locator("#text").fill("Dostawa, kierowca.")
    page.get_by_role("button", name="Odczytaj opis").click()
    expect(page.locator("#describe-result .callout-warn")).to_contain_text("kierowca")
    page.get_by_role("button", name="Użyj tych zadań").click()
    page.wait_for_url("**tab=manual**")
    page.get_by_role("button", name="Utwórz plan").click()
    expect(page.locator("#step")).to_contain_text("kierowca")
    assert "flash=plan_ready" not in page.url
    view = page.request.get(f"{local.base}/api/projects/{project}").json()
    assert view["tasks"][0]["crew"] == {"kierowca": 1}  # nothing is lost on the way
    page.locator("td.cell-people summary").first.click()
    page.locator('input[name="other_count_T1"]').fill("0")
    page.get_by_label("Tester — ", exact=False).first.fill("1")
    page.get_by_role("button", name="Utwórz plan").click()
    page.wait_for_url(re.compile(r"flash=plan_ready"))
    page.context.close()


def test_a_message_is_read_twice_refused_with_its_items_kept_and_saved(
    browser: Any, local: Server
) -> None:
    page = _page(browser, local.base)
    project = _planned(page, local.base, "Wiadomość")
    _to_message_form(page, local.base, project)
    page.locator("button.btn-primary").click()
    page.wait_for_url(re.compile(r"flash=checkin_saved"))
    page.goto(f"{local.base}/projects/{project}/checkin")
    page.wait_for_load_state("networkidle")
    page.get_by_label("Stan na koniec dnia").fill("2026-10-09")
    page.locator("#message").fill("Ani nie będzie, logowanie potrwa dłużej.")
    read = page.get_by_role("button", name="Przetwórz wiadomość")
    read.click()
    items = page.locator("#message-result .confirm-list li")
    expect(items).to_have_count(2)
    expect(items.first).to_contain_text("Ania Nowak")
    expect(items.nth(1)).to_contain_text("więcej")
    expect(page.locator("button.btn-primary")).to_be_visible()  # the form is still here
    page.evaluate("document.querySelector('#message-result').innerHTML = ''")
    read.click()  # a second read answers again in the same place
    expect(items).to_have_count(2)
    # A refused save: the items the manager has confirmed are still there; the message itself is
    # not sent back.
    row = page.locator("fieldset.task-row", has_text="Testy").first
    row.get_by_label("Gotowe", exact=True).check()
    row.get_by_label("Zakończone dnia").fill("")
    page.locator("button.btn-primary").click()
    expect(page.locator("#checkin-form .callout-bad")).to_be_visible()
    expect(page.locator("#message-result .confirm-list li")).to_have_count(2)
    expect(page.locator("#message")).to_have_value("")
    row = page.locator("fieldset.task-row", has_text="Testy").first
    row.get_by_label("Nierozpoczęte").check()
    page.locator("button.btn-primary").click()
    page.wait_for_url(re.compile(r"flash=checkin_saved"))
    page.goto(f"{local.base}/projects/{project}/history")
    expect(page.locator("main")).to_contain_text("Ania Nowak")
    expect(page.locator("main")).to_contain_text("Logowanie")
    page.context.close()


def test_every_form_says_when_the_model_fails_and_works_again(
    browser: Any, local: Server, model: Model
) -> None:
    page = _page(browser, local.base)
    project = _planned(page, local.base, "Awaria")
    _to_message_form(page, local.base, project)
    page.locator("#message").fill("Ani nie będzie.")
    read = page.get_by_role("button", name="Przetwórz wiadomość")
    failed = "#message-result .callout-bad"
    model.fail = LlmError("no", status=500)
    read.click()
    expect(page.locator(failed)).to_contain_text("AI nie odpowiedziało")
    model.invalid = True
    read.click()
    expect(page.locator(failed)).to_contain_text("Nie udało się odczytać wiadomości")
    model.invalid = False
    read.click()
    expect(page.locator("#message-result .confirm-list li").first).to_contain_text("Ania Nowak")
    # The same answer is not replayed: the model was asked again after its invalid answers.
    page.locator("button.btn-primary").click()
    page.wait_for_url(re.compile(r"flash=checkin_saved"))
    # The explanation: a failure, an invalid answer, then a good one.
    page.goto(f"{local.base}/projects/{project}")
    page.wait_for_load_state("networkidle")
    page.wait_for_function("!document.querySelector('.job')", timeout=WAIT)  # the analysis
    page.wait_for_load_state("networkidle")
    waiting = page.get_by_role("link", name="Przejrzyj i zdecyduj")
    if waiting.count():
        waiting.first.click()
    else:
        page.get_by_role("button", name="Przelicz teraz").first.click()
    page.wait_for_url("**/recommendations/**", timeout=WAIT)
    ask = page.get_by_role("button", name="Wyjaśnij innymi słowami (AI)")
    model.fail = LlmError("no", status=401)
    ask.click()
    expect(page.locator("#explain-area .callout-bad")).to_contain_text("klucz API")
    model.invalid = True
    ask.click()
    expect(page.locator(".review-block")).to_contain_text("nie podało użytecznego wyjaśnienia")
    model.invalid = False
    page.get_by_role("button", name="Wyjaśnij innymi słowami (AI)").click()
    expect(page.locator(".review-block")).to_contain_text("The plan stays (no change).")
    expect(page.locator(".review-block .badge")).to_be_visible()
    page.context.close()
