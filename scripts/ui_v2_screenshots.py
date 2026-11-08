"""Screenshots of the v2 screens (WP15; docs/design/v2-spec.md, section 10).

Seeds a data directory with the showcase project in the chosen language (two reports and a
pending decision) and a draft for the wizard, serves the app in-process and captures each v2
screen at 1440x900 and 1280x800, in the light and the dark theme, with Playwright's Chromium.
The PNGs go to docs/ui/v2/ as `<lang>_<theme>_<screen>_<width>.png` with a reduced palette.
Take them after a version bump: the sidebar shows the installed package's version.

    uv run python scripts/ui_v2_screenshots.py [--lang pl en] [--theme light dark] [--only overview]
"""

import argparse
import json
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from ui_screenshots import LOCALES, language_env, serving

from sentinel.app import showcase
from sentinel.app.config import AppConfig
from sentinel.app.services import Services
from sentinel.app.store import LOCAL_SESSION

SIZES = ((1440, 900), (1280, 800))
THEMES = ("light", "dark")
COLOURS = 64
DRAFT = {"pl": "szkic", "en": "draft"}


@dataclass(frozen=True)
class Shot:
    """A screen: its name, path, an element to wait for, one to click first, one to scroll to."""

    name: str
    path: str
    ready: str | None = None
    clicks: tuple[str, ...] = ()
    scroll: str | None = None
    wait: str | None = None


def seed(services: Services, language: Any) -> dict[str, str]:
    """The showcase and a draft of it (team only, for the wizard); their ids."""
    services.local_session()
    showcase.install(services)
    assert services.showcase is not None
    services.showcase(LOCAL_SESSION, language)
    ids = {"showcase": services.projects(LOCAL_SESSION)[0].id}
    definition = showcase.definition(language)
    draft = definition.model_copy(
        update={"name": f"{definition.name} ({DRAFT[language]})", "tasks": ()}
    )
    ids["draft"] = services.create(LOCAL_SESSION, draft, language).id
    return ids


def shots_of(ids: dict[str, str], rec: int | None) -> list[Shot]:
    live = f"/v2/projects/{ids['showcase']}"
    decision = f"{live}/decisions/{rec}"
    return [
        Shot("start", "/v2"),
        Shot("overview", live),
        Shot("overview_below", live, scroll="#buffer-title", wait="#insights .bullets"),
        Shot("report", f"{live}/report"),
        Shot(
            "report_cards",
            f"{live}/report",
            clicks=("[data-planned]", "[data-tick-all]"),
            wait="#impact .chips",
            scroll="#step2-title",
        ),
        Shot("decision", decision),
        Shot("decision_reject", decision, clicks=("[data-toggle^='reject']",)),
        Shot(
            "decision_details",
            decision,
            clicks=("#details > summary",),
            scroll="#details",
            wait="#distribution svg",
        ),
        Shot("decisions", f"{live}/decisions"),
        Shot(
            "report_form",
            f"{live}/report",
            clicks=("[data-toggle='form-panel']",),
            scroll="#form-title",
        ),
        Shot("log", "/v2/log"),
        Shot("project_log", f"{live}/log", clicks=("details.log-entry > summary",)),
        Shot("wizard_basics", "/v2/new"),
        Shot("wizard_team", f"/v2/new/{ids['draft']}/team"),
        Shot("wizard_tasks", f"/v2/new/{ids['draft']}/tasks"),
    ]


def save(page: Any, target: Path) -> int:
    page.screenshot(path=str(target))
    with Image.open(target) as image:
        reduced = image.convert("RGB").quantize(COLOURS, dither=Image.Dither.NONE)
    reduced.save(target, optimize=True)
    return target.stat().st_size


def capture(
    browser: Any, base: str, shots: list[Shot], language: str, theme: str, out: Path
) -> None:
    for width, height in SIZES:
        context = browser.new_context(
            viewport={"width": width, "height": height},
            locale=LOCALES[language],
            reduced_motion="reduce",
        )
        context.add_cookies(
            [
                {"name": "sentinel_lang", "value": language, "url": base},
                {"name": "sentinel_theme", "value": theme, "url": base},
            ]
        )
        context.set_default_timeout(60_000)
        page = context.new_page()
        for shot in shots:
            page.goto(base + shot.path)
            page.wait_for_load_state("networkidle")
            if shot.ready is not None:
                page.wait_for_selector(shot.ready)
            for click in shot.clicks:
                page.locator(click).first.click()
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(200)
            if shot.wait is not None:
                page.wait_for_selector(shot.wait)
            if shot.scroll is not None:
                page.locator(shot.scroll).evaluate("e => e.scrollIntoView({block: 'start'})")
                page.evaluate("window.scrollBy(0, -24)")
            page.wait_for_timeout(300)
            target = out / f"{language}_{theme}_{shot.name}_{width}.png"
            print(f"{target}: {save(page, target) / 1024:.0f} kB")
        context.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lang", nargs="+", choices=("pl", "en"), default=["pl", "en"])
    parser.add_argument("--theme", nargs="+", choices=THEMES, default=list(THEMES))
    parser.add_argument("--out", type=Path, default=Path("docs/ui/v2"))
    parser.add_argument("--only", nargs="*", default=None, help="only these screens")
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright

    args.out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        for language in args.lang:
            browser = playwright.chromium.launch(env=language_env(language))
            data = Path(tempfile.mkdtemp(prefix="sentinel-v2-ui-"))
            # An AI provider and a key for recordings, so that the pages show the microphone
            # and "Rozpoznaj zmiany"; no screenshot calls either.
            settings = {"llm": {"provider": "ollama", "groq_key": "screenshots-only"}}
            (data / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
            config = AppConfig(data_dir=data, inline_jobs=True)
            services = Services(config)
            began = time.perf_counter()
            ids = seed(services, language)
            rec = services.live(LOCAL_SESSION, ids["showcase"], language).open_recommendation
            print(f"seeded in {time.perf_counter() - began:.1f} s: {ids}, decision {rec}")
            shots = shots_of(ids, rec)
            if args.only:
                shots = [s for s in shots if s.name in args.only]
            with serving(config, services) as base:
                for theme in args.theme:
                    capture(browser, base, shots, language, theme, args.out)
                if not args.only or "start_first" in args.only:
                    empty = AppConfig(data_dir=Path(tempfile.mkdtemp(prefix="sentinel-v2-ui-")))
                    with serving(empty, Services(empty)) as other:
                        for theme in args.theme:
                            first = [Shot("start_first", "/v2")]
                            capture(browser, other, first, language, theme, args.out)
            browser.close()
    total = sum(p.stat().st_size for p in args.out.glob("*.png"))
    print(f"total {total / 1024:.0f} kB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
