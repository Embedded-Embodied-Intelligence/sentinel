"""The v2 interface in a real browser (WP15, WP16; docs/design/v2-spec.md, section 10): the demo
path in demo mode, from Start through the showcase's overview, a report dictated into Chromium's
fake microphone with its live preview, the cards confirmed, their effect, the save, the decision
and its approval, after which the overview shows exactly the promised numbers; a rejection and
its fate in the Dziennik; "Co jeśli?" added to a report; the calendar feed read without a
session and revoked; and the accessibility scan (axe-core) of every v2 screen in the light and
the dark theme. The reader and Whisper are scripted, so the test makes no AI call.

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
        expect(pending).to_contain_text("zastępuje", timeout=120_000)
        pending.get_by_role("link", name=re.compile("Szczegóły")).click()
        # "Twoja ocena" (WP19): choose first, then the recommendation with both choices
        expect(page.get_by_role("heading", name="Co byś zrobił?")).to_be_visible()
        page.get_by_role("link", name="Bez zmian", exact=True).click()
        expect(page.locator(".own-line")).to_contain_text("Twój wybór: Bez zmian · Sentinel:")
        effect = page.locator(".effects")
        expect(effect).to_contain_text("→")
        chance = number(effect.inner_text(), r"\d+ → (\d+)\sna\s100")  # no break in "57 na 100"
        end = number(effect.inner_text(), r"Koniec projektu\s+\S+\s\d+\s\S+\s+→\s+(\S+\s\d+\s\S+)")
        page.get_by_role("button", name="Zatwierdź").click()
        page.wait_for_url(re.compile(r"done=approved"))
        expect(page.locator(".notice")).to_contain_text("Zatwierdzono")
        expect(page.locator(".hero")).to_contain_text(chance)
        expect(page.locator("section[aria-labelledby='fig-end']")).to_contain_text(
            end.replace("\xa0", " ")
        )
        context.close()
        chromium.close()
    assert WHISPER.calls >= 2  # a preview and the final transcription


def showcase_page(demo: Server, playwright: Any, **context_args: Any) -> tuple[Any, Any, str]:
    """A new visitor (a sandbox with the showcase) on the showcase's overview; its address."""
    chromium = browser(playwright)
    context = chromium.new_context(
        viewport={"width": 1440, "height": 900}, locale="pl-PL", **context_args
    )
    context.set_default_timeout(60_000)
    page = context.new_page()
    page.goto(demo.base + "/v2")
    page.locator(".tile", has_text="Nowa odsłona sklepu internetowego").click()
    expect(page.locator(".verdict")).to_contain_text("Nie zdążymy bez zmian")
    return chromium, page, page.url


def test_the_log_shows_a_decision_and_its_fate(demo: Server) -> None:
    """Dziennik (8.6): a rejection with its reason, the proposal's fate one click away, a dot of
    "Szansa w czasie" that opens its entry, and the CSV."""
    with sync_api.sync_playwright() as playwright:
        chromium, page, overview = showcase_page(demo, playwright)
        page.locator("#pending").get_by_role("link", name=re.compile("Szczegóły")).click()
        page.get_by_role("link", name="Pokaż od razu").click()  # "Twoja ocena" skipped
        page.locator("[data-toggle^='reject']").first.click()
        page.locator(".reason-chips label", has_text="Za drogo").click()
        page.get_by_role("button", name="Potwierdź odrzucenie").click()
        page.wait_for_url(re.compile(r"done=rejected"))
        page.goto(overview + "/log")
        log = page.locator(".log")
        expect(log).to_contain_text(re.compile(r"Odrzucono: \w+ zastępuje"))
        expect(log).to_contain_text("(za drogo)")
        proposal = page.locator("details.log-entry", has_text="Nowa propozycja")
        proposal.locator("summary").click()
        expect(proposal).to_contain_text("Stan decyzji")
        expect(proposal.locator(".life")).to_have_text("odrzucona")
        expect(proposal).to_contain_text("Powód: Za drogo")
        dot = page.locator(".chance-time a").nth(1)  # the report of 6 November
        dot.click()
        target = dot.get_attribute("href")
        assert target is not None
        expect(page.locator(f"{target} details")).to_have_attribute("open", "")
        href = page.get_by_role("link", name="Pobierz dziennik (CSV)").get_attribute("href")
        assert href is not None
        table = page.request.get(demo.base + href)
        assert table.ok and re.search(r"Odrzucono: \w+ zastępuje", table.text())
        chromium.close()


def test_what_if_then_add_to_the_report(demo: Server) -> None:
    """Laboratorium (8.8): "Co jeśli?" shows "Wpływ na projekt", saves nothing, and "Dodaj do
    raportu" opens the Raport with the scenario as ticked cards and their effect."""
    with sync_api.sync_playwright() as playwright:
        chromium, page, _ = showcase_page(demo, playwright)
        page.get_by_role("link", name="Laboratorium").click()
        expect(page.get_by_role("link", name="Co jeśli?")).to_have_attribute("aria-current", "true")
        page.select_option("#away-person", label="Anna Nowak")
        expect(page.locator("#away-from")).to_have_value("2026-11-16")  # the first day counted
        page.fill("#away-back", "2026-11-24")
        page.get_by_role("button", name="Sprawdź wpływ").click()
        impact = page.locator("#whatif-impact")
        expect(impact.locator(".chips")).to_contain_text("Szansa 39 →")
        assert int(number(impact.inner_text(), r"Szansa 39 → (\d+) na 100")) < 39
        expect(impact).to_contain_text("Nic nie zostało zapisane.")
        page.get_by_role("link", name="Dodaj do raportu").click()
        page.wait_for_url(re.compile(r"/report\?"))
        card = page.locator("#cards-lab [data-card]")
        expect(card).to_have_count(1)
        expect(card).to_contain_text("Anna Nowak: nieobecność od pon. 16 lis")
        assert card.locator("input[type=checkbox]").is_checked()
        expect(page.locator("#impact .chips")).to_contain_text("Szansa 39 →")
        expect(page.get_by_role("button", name="Zapisz raport")).to_be_enabled()
        chromium.close()


def test_the_calendar_feed(demo: Server) -> None:
    """Kalendarz (8.9): a link made on request, copied, read by a calendar without the
    visitor's session, and revoked."""
    from icalendar import Calendar

    with sync_api.sync_playwright() as playwright:
        chromium, page, overview = showcase_page(demo, playwright)
        page.context.grant_permissions(["clipboard-read", "clipboard-write"])
        page.goto(overview + "/settings")
        expect(page.locator("#calendar")).to_contain_text(
            "Kto ma ten link, widzi imiona osób i daty nieobecności."
        )
        page.get_by_role("button", name="Utwórz link do kalendarza").click()
        page.wait_for_url(re.compile(r"done=calendar"))
        link = page.locator("#calendar-link").input_value()
        assert link.startswith(demo.base + "/calendar/") and ".ics" in link
        page.get_by_role("button", name="Kopiuj link do kalendarza").click()
        expect(page.locator("[data-copy-status]")).to_have_text("Skopiowano.")
        assert page.evaluate("navigator.clipboard.readText()") == link
        outsider = playwright.request.new_context()  # a calendar: no cookie, no session
        feed = outsider.get(link)
        assert feed.ok and feed.headers["content-type"].startswith("text/calendar")
        parsed = Calendar.from_ical(feed.text())
        names = {str(event.get("SUMMARY")) for event in parsed.walk("VEVENT")}
        assert "Termin: Nowa odsłona sklepu internetowego" in names
        assert "Nieobecność: Bartosz Kowalski" in names
        page.get_by_role("button", name="Unieważnij link").click()
        page.wait_for_url(re.compile(r"done=revoked"))
        assert outsider.get(link).status == 404
        outsider.dispose()
        chromium.close()


def test_the_presentation_path(demo: Server) -> None:
    """WP19 (docs/design/v3-spec.md): Pulpit → ⓘ on "N na 100" → the panel (verified quotes
    with highlights, Esc closes, focus back on the point) → Mapa granic → a cell → Uprawnienia
    AI → "Próba ataku" → Ludzie; and a deep link opens a panel with its page."""
    with sync_api.sync_playwright() as playwright:
        chromium, page, _ = showcase_page(demo, playwright)
        point = page.locator("[data-decision='D01']")
        expect(point).to_have_attribute("aria-label", "Dowody dla tej decyzji (3)")
        point.click()
        panel = page.locator("#dowod")
        expect(panel).to_be_visible()
        expect(panel.get_by_role("heading", name="Decyzja")).to_be_visible()
        expect(panel).to_contain_text("Szansę na termin pokazujemy jako „N na 100”")
        expect(panel.locator("blockquote mark").first).to_be_visible()
        expect(panel.locator(".ev-wspiera")).to_have_count(3)
        inside = "() => document.getElementById('dowod').contains(document.activeElement)"
        for _ in range(6):  # the page behind is inert: Tab stays in the panel
            page.keyboard.press("Tab")
            assert page.evaluate(inside)
        page.keyboard.press("Escape")
        expect(panel).to_be_hidden()
        assert page.evaluate("() => document.activeElement.dataset.decision") == "D01"
        page.get_by_role("link", name="Mapa granic").click()
        expect(page.get_by_role("heading", level=1)).to_contain_text("Mapa granic")
        page.locator(".map-cell[data-dowod$='/P09/4']").click()
        expect(panel).to_contain_text("Ocena wydajności pracownika")
        expect(panel).to_contain_text("tylko człowiek")
        expect(panel.locator(".ev").first).to_be_visible()
        panel.get_by_role("button", name="Zamknij dowody").click()
        expect(panel).to_be_hidden()
        page.locator("summary", has_text="Prognoza dotrzymania terminu").click()
        expect(page.locator(".proc[open]")).to_contain_text("Pulpit")
        page.get_by_role("link", name="Uprawnienia AI").click()
        expect(page.locator(".perm-may-not")).to_contain_text("Zatwierdzić zmiany")
        page.get_by_role("button", name="Uruchom").click()
        result = page.locator("#attack-result")
        expect(result).to_contain_text("Polecenie zostało zignorowane")
        expect(result).to_contain_text("Sentinel nie ma funkcji, którą AI mogłoby to zrobić.")
        page.get_by_role("link", name="Ludzie").click()
        expect(page.locator(".absent-card")).to_have_count(4)
        expect(page.locator("main")).to_contain_text(
            "Sentinel planuje według ról i dostępności, nie ocenia ludzi."
        )
        page.goto(demo.base + "/v2/sources?dowod=D22")
        expect(panel).to_be_visible()
        expect(panel).to_contain_text("Punkt „Dowód” przy każdej funkcji")
        chromium.close()


def _axe(page: Any) -> list[str]:
    # Through the DevTools protocol: the page's content policy allows no inline script (WP17).
    page.evaluate("() => {" + AXE.read_text(encoding="utf-8") + "\n}")
    found = page.evaluate(
        """async () => (await axe.run(document, {resultTypes: ['violations']})).violations
              .filter(v => v.impact === 'serious' || v.impact === 'critical')
              .map(v => v.id + ': '
                + v.nodes.map(n => n.target.join(' ')).slice(0, 3).join(', '))"""
    )
    return list(found)


def test_a_phone_and_a_small_laptop_never_scroll_sideways(demo: Server) -> None:
    """WP17: below 900 px the sidebar is a bar on top and every grid one column; at 1024 px
    the layout narrows. No screen of the demo path scrolls sideways at 390 or 1024 px."""
    with sync_api.sync_playwright() as playwright:
        chromium = browser(playwright)
        for width, height in ((390, 844), (1024, 768)):
            context = chromium.new_context(viewport={"width": width, "height": height})
            page = context.new_page()
            page.goto(demo.base + "/v2")
            project = page.locator("a.tile", has_text="Nowa odsłona").first.get_attribute("href")
            assert project is not None
            for path in (
                "/v2",
                project,
                f"{project}/decisions",
                f"{project}/report",
                f"{project}/log",
                f"{project}/plan?view=tasks",
                "/v2/lab",
                "/v2/new",
                "/v2/map",
                "/v2/permissions",
                "/v2/people",
                "/v2/sources",
            ):
                page.goto(demo.base + path)
                page.wait_for_load_state("networkidle")
                wide = page.evaluate("document.documentElement.scrollWidth")
                assert wide <= width, (width, path, wide)
            context.close()
        chromium.close()


def test_a_wide_window_scales_the_layout_up(demo: Server) -> None:
    """WP16 hotfix: a wide window (here 2096 px, a retina screen at 80 % zoom) scales the
    layout of 1440 up instead of pinning it to the left; 1440 stays as designed; no horizontal
    scroll and the sidebar's foot stays in the window."""
    with sync_api.sync_playwright() as playwright:
        chromium = browser(playwright)
        measured = {}
        for width, height in ((1440, 900), (2096, 1165)):
            context = chromium.new_context(viewport={"width": width, "height": height})
            page = context.new_page()
            page.goto(demo.base + "/v2")
            measured[width] = page.evaluate(
                """() => ({
                  zoom: getComputedStyle(document.documentElement).getPropertyValue('--zoom'),
                  scroll: document.documentElement.scrollWidth,
                  foot: document.querySelector('.v2-side-foot').getBoundingClientRect().bottom,
                  right: document.querySelector('.v2-main').getBoundingClientRect().right,
                })"""
            )
            context.close()
        chromium.close()
    assert measured[1440]["zoom"].strip() == "1" and measured[1440]["right"] == 1440
    wide = measured[2096]
    assert wide["zoom"].strip() == "1.4" and wide["scroll"] == 2096
    assert wide["right"] > 2096 - 48 and wide["foot"] <= 1165


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
            ("report_form", href + "/report", "[data-toggle='form-panel']"),
            ("decisions", href + "/decisions", None),
            ("log", href + "/log", "details.log-entry > summary"),
            ("all_log", "/v2/log", None),
            ("plan", href + "/plan", None),
            ("plan_tasks", href + "/plan?view=tasks", "[data-toggle^='fix-']"),
            ("plan_team", href + "/plan?view=team", None),
            ("lab", "/v2/lab", None),
            ("simulator", "/v2/lab?tab=sim", None),
            ("settings", "/v2/settings", None),
            ("project_settings", href + "/settings", "[data-toggle='delete-confirm']"),
            ("wizard", "/v2/new", None),
        ]
        screens += [  # v3 (WP19), with the "Dowód" panel open
            ("overview_panel", href, "[data-decision='D01']"),
            ("map", "/v2/map", None),
            ("map_panel", "/v2/map", ".map-cell"),
            ("permissions", "/v2/permissions", "[data-attack-run]"),
            ("people", "/v2/people", None),
            ("sources", "/v2/sources", "details.src-item > summary"),
        ]
        if decision is not None:
            screens.append(("decision_assessment", decision, None))
            screens.append(("decision", decision + "?own=skip", "[data-toggle^='reject']"))
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
        page.goto(demo.base + "/v2/lab?tab=sim")
        start = page.get_by_role("button", name="Uruchom symulację")
        if start.count():  # the example projects are installed: a run's own page too
            start.click()
            page.wait_for_url(re.compile(r"/v2/lab/sim/"), timeout=120_000)
            page.get_by_role("button", name="+1 dzień").click()
            page.wait_for_url(re.compile(r"/v2/lab/sim/"), timeout=120_000)
            expect(page.locator(".sim-day")).to_contain_text("Dzień 1", timeout=120_000)
            found = _axe(page)
            if found:
                problems["simulation"] = found
        context.close()
        chromium.close()
    assert problems == {}
