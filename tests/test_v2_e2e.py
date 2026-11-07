"""The v2 interface in a real browser (WP15; docs/design/v2-spec.md, section 10): the demo path in
demo mode, from Start through the showcase's overview, a report dictated into Chromium's fake
microphone with its live preview, the cards confirmed, their effect, the save, the decision and
its approval, after which the overview shows exactly the promised numbers; and the accessibility
scan (axe-core) of every v2 screen in the light and the dark theme. The reader and Whisper are
scripted, so the test makes no AI call.

    uv run pytest -q -m e2e tests/test_v2_e2e.py
"""

import json
import re
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from e2e_env import Server, chromium_env, serve

import sentinel.app.messages
import sentinel.app.ui.text
import sentinel.app.ui.v2.decision
import sentinel.app.ui.v2.overview
import sentinel.app.ui.v2.report
import sentinel.app.ui.v2.start
from sentinel.app.config import DEMO_CONFIG, load_config

sync_api = pytest.importorskip("playwright.sync_api")
expect = sync_api.expect

pytestmark = pytest.mark.e2e
ROOT = Path(__file__).resolve().parents[1]
AXE = Path(__file__).parent / "vendor/axe-core-4.14.0/axe.min.js"
RECORDING = ROOT / "tests" / "fixtures" / "owner_message_pl.wav"
TODAY = date(2026, 11, 16)  # the Monday after the showcase's second report
SAID = (
    "Interfejs procesu zakupu skończony w poniedziałek 16 listopada. "
    "API katalogu produktów zrobione w połowie."
)
ANSWER = {
    "items": [
        {
            "type": "done",
            "clause": 1,
            "task": "Interfejs procesu zakupu",
            "day": {"day": "2026-11-16", "words": "w poniedziałek 16 listopada"},
        },
        {
            "type": "progress",
            "clause": 2,
            "task": "API katalogu produktów",
            "percent": 50,
            "started": None,
        },
    ],
    "unparsed": [],
    "questions": [],
}


class Today(date):
    @classmethod
    def today(cls) -> "Today":
        return cls(TODAY.year, TODAY.month, TODAY.day)


class Whisper:
    """Groq's Whisper as scripted: every recording, and every part of one, reads SAID."""

    model = "scripted"

    def __init__(self) -> None:
        self.calls = 0

    def transcribe(
        self, audio: bytes, content_type: str, *, language: str | None, prompt: str = ""
    ) -> Any:
        from sentinel.llm.whisper import Transcript

        assert audio and content_type.startswith("audio/") and language == "pl"
        self.calls += 1
        return Transcript(SAID, 6.0, self.model)


def reader(messages: Any) -> str:
    clauses = len(re.findall(r"^\[\d+\] ", messages[1].content, re.M))
    items = [{**item, "clause": min(item["clause"], clauses)} for item in ANSWER["items"]]
    return json.dumps({**ANSWER, "items": items}, ensure_ascii=False)


WHISPER = Whisper()


@pytest.fixture(scope="module")
def demo(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Server]:
    """The demo with its showcase, AI and recordings, the reader and Whisper scripted."""
    from sentinel.llm import FakeLlmClient

    data = tmp_path_factory.mktemp("v2-demo")
    settings = {"llm": {"provider": "ollama", "groq_key": "test-key-for-recordings"}}
    (data / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    config = load_config(ROOT / DEMO_CONFIG, data_dir=data, secure_cookies=False)

    def factory(settings: Any, cache: Any) -> Any:
        client = FakeLlmClient(reader, cache=cache)
        client.model = "scripted"
        return client

    with pytest.MonkeyPatch.context() as patch:
        for module in (
            sentinel.app.messages,
            sentinel.app.ui.v2.decision,
            sentinel.app.ui.v2.overview,
            sentinel.app.ui.v2.report,
            sentinel.app.ui.v2.start,
        ):
            patch.setattr(module, "date", Today)
        patch.setattr(sentinel.app.ui.text, "Day", Today)
        yield from serve(config, llm_factory=factory, transcriber=lambda key: WHISPER)


def browser(playwright: Any, *, microphone: bool = False) -> Any:
    args = []
    if microphone:
        fake = f"--use-file-for-fake-audio-capture={RECORDING}%noloop"
        args = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", fake]
    try:
        return playwright.chromium.launch(env=chromium_env(), args=args)
    except sync_api.Error:  # pragma: no cover - depends on the machine
        pytest.skip("Chromium for Playwright cannot start (docs/deploy.md, section 4)")


def number(text: str, pattern: str) -> str:
    found = re.search(pattern, text)
    assert found is not None, (pattern, text)
    return found.group(1)


def test_the_demo_path(demo: Server) -> None:
    """Start → Pulpit → Raport by voice → Do potwierdzenia → Wpływ → Zapisz → Pulpit →
    Decyzja → Zatwierdź → Pulpit with exactly the promised numbers (section 10)."""
    with sync_api.sync_playwright() as playwright:
        chromium = browser(playwright, microphone=True)
        context = chromium.new_context(viewport={"width": 1280, "height": 800}, locale="pl-PL")
        context.set_default_timeout(60_000)
        page = context.new_page()
        page.goto(demo.base + "/v2")
        expect(page.get_by_role("heading", level=1)).to_contain_text("Projekty")
        page.locator(".tile", has_text="Nowa odsłona sklepu internetowego").click()
        expect(page.locator(".verdict")).to_contain_text("Nie zdążymy bez zmian")
        expect(page.locator(".hero")).to_contain_text("39")
        page.locator(".v2-head").get_by_role("link", name="Raport").click()
        expect(page.get_by_role("heading", name="Zdarzenia od ostatniego raportu")).to_be_visible()
        page.get_by_role("button", name="Podyktuj").click()
        expect(page.locator("[data-voice-rec]")).to_be_visible()
        expect(page.locator(".voice-preview")).to_contain_text("Interfejs", timeout=15_000)
        page.keyboard.press("Enter")  # ✓: the whole recording once more, as ordinary text
        expect(page.locator("#message")).to_have_value(SAID)
        expect(page.locator("[data-voice-status]")).to_contain_text("Przepisane")
        page.get_by_role("button", name="Rozpoznaj zmiany").click()
        cards = page.locator("#cards-message [data-card]")
        expect(cards).to_have_count(2)
        expect(page.locator("#cards-message")).to_contain_text(
            "„Interfejs procesu zakupu” skończone"
        )
        expect(page.locator("#cards-message")).to_contain_text("wykonano 50 %")
        for checkbox in cards.locator("input[type=checkbox]").all():
            assert not checkbox.is_checked()  # unchecked by default (8.3)
        save = page.get_by_role("button", name="Zapisz raport")
        expect(save).to_be_disabled()
        page.get_by_role("button", name="Zaznacz wszystkie").click()
        expect(page.locator("#impact .chips")).to_contain_text("Szansa 39 →")
        expect(save).to_be_enabled()
        save.click()
        page.wait_for_url(re.compile(r"done=report"))
        expect(page.locator(".notice")).to_contain_text("Raport zapisany.")
        pending = page.locator("#pending")
        expect(pending).to_contain_text("Zastępstwo", timeout=120_000)
        pending.get_by_role("link", name=re.compile("Szczegóły")).click()
        effect = page.locator(".effects")
        expect(effect).to_contain_text("→")
        chance = number(effect.inner_text(), r"\d+ → (\d+) na 100")
        end = number(effect.inner_text(), r"Koniec projektu\s+\S+ \d+\s\S+ → (\S+ \d+\s\S+)")
        page.get_by_role("button", name="Zatwierdź").click()
        page.wait_for_url(re.compile(r"done=approved"))
        expect(page.locator(".notice")).to_contain_text("Zatwierdzono")
        expect(page.locator(".hero")).to_contain_text(chance)
        expect(page.locator("#fig-end").locator("..")).to_contain_text(end.replace("\xa0", " "))
        context.close()
        chromium.close()
    assert WHISPER.calls >= 2  # a preview and the final transcription


def _axe(page: Any) -> list[str]:
    page.add_script_tag(path=str(AXE))
    found = page.evaluate(
        """async () => (await axe.run(document, {resultTypes: ['violations']})).violations
              .filter(v => v.impact === 'serious' || v.impact === 'critical')
              .map(v => v.id + ': '
                + v.nodes.map(n => n.target.join(' ')).slice(0, 3).join(', '))"""
    )
    return list(found)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_v2_screens_have_no_serious_accessibility_violations(demo: Server, theme: str) -> None:
    with sync_api.sync_playwright() as playwright:
        chromium = browser(playwright)
        context = chromium.new_context(viewport={"width": 1440, "height": 900}, locale="pl-PL")
        context.set_default_timeout(60_000)
        page = context.new_page()
        page.goto(demo.base + "/v2")
        context.add_cookies([{"name": "sentinel_theme", "value": theme, "url": demo.base}])
        page.goto(demo.base + "/v2")
        href = page.locator(".tile").first.get_attribute("href")
        assert href is not None
        decision = page.locator(".todo").first.get_attribute("href")
        screens: list[tuple[str, str, str | None]] = [
            ("start", "/v2", None),
            ("overview", href, None),
            ("report", href + "/report", "[data-planned]"),
            ("decisions", href + "/decisions", None),
            ("wizard", "/v2/new", None),
            ("soon", href + "/plan", None),
        ]
        if decision is not None:
            screens.append(("decision", decision, "[data-toggle^='reject']"))
        problems = {}
        for name, path, click in screens:
            page.goto(demo.base + path)
            page.wait_for_load_state("networkidle")
            assert page.locator("html").get_attribute("data-theme") == theme
            if click is not None:
                page.locator(click).first.click()
                page.wait_for_load_state("networkidle")
            found = _axe(page)
            if found:
                problems[name] = found
        context.close()
        chromium.close()
    assert problems == {}
