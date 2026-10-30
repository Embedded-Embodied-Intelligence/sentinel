"""Screenshots of every screen for the report, the user guides and the visual review (WP9b, WP10).

Seeds a data directory with the showcase project in the chosen language (a live project with two
check-ins and an open recommendation), a draft of the same project for the wizard, a small example
simulator run in progress and one finished under Sentinel, serves the app in-process and captures
each screen at 1280x800 and 390x844 (phone) with Playwright's Chromium in light mode. About a
minute per language (the simulator runs; `--data DIR` keeps the seeded directory for the next
call). The PNGs go to docs/ui/ as `<lang>_<screen>.png` and `<lang>_<screen>_phone.png` with a
reduced palette (committed, used by the user guides); the total of docs/ui must stay <= 5 MB. Take
them after a version bump: the sidebar shows the installed package's version.

    uv run python scripts/ui_screenshots.py [--lang pl en] [--out docs/ui] [--only start overview]
"""

import argparse
import os
import socket
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import uvicorn
from PIL import Image

from sentinel.app import showcase
from sentinel.app.api import create_app
from sentinel.app.config import AppConfig
from sentinel.app.services import Services
from sentinel.app.simulator import SimulatorSpec
from sentinel.app.store import LOCAL_SESSION

SIZES = {"": (1280, 800), "_phone": (390, 844)}
DRAFT = {"pl": "szkic", "en": "draft"}
LIMIT_BYTES = 5 * 1024 * 1024
COLOURS = 96  # the palette of a saved screenshot
LOCALES = {"pl": "pl-PL", "en": "en-GB"}


@dataclass(frozen=True)
class Shot:
    """A screen: its name, path, an element to wait for, one to scroll to, one to open first."""

    name: str
    path: str
    ready: str | None = None
    scroll: str | None = None
    click: str | None = None


def chromium_env() -> dict[str, str] | None:
    """Chromium's libraries of scripts/setup_e2e_libs.sh on LD_LIBRARY_PATH (as tests/e2e_env.py),
    or None for the process's own environment."""
    default = Path.home() / ".local" / "share" / "sentinel-e2e-libs"
    root = Path(os.environ.get("SENTINEL_E2E_LIBS", default)) / "usr" / "lib"
    folders = sorted(str(p) for p in root.glob("*-linux-gnu") if p.is_dir())
    if not folders:
        return None
    current = os.environ.get("LD_LIBRARY_PATH")
    return {**os.environ, "LD_LIBRARY_PATH": ":".join([*folders, current] if current else folders)}


def language_env(language: str) -> dict[str, str]:
    """The browser's environment in `language`: a date field shows "13.11.2026" in Polish."""
    name = LOCALES[language].replace("-", "_")
    return {**(chromium_env() or dict(os.environ)), "LANGUAGE": name, "LC_ALL": f"{name}.UTF-8"}


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def seed(services: Services, language: Any) -> dict[str, str]:
    """The showcase, a draft of it, a simulator run in progress and a finished one; their ids.
    A directory seeded earlier is used as it is."""
    services.local_session()
    found = services.projects(LOCAL_SESSION)
    if len(found) >= 4:
        lives = [p for p in found if p.kind == "live"]
        sims = [p for p in found if p.kind == "simulator"]
        draft = next(p for p in lives if p.name.endswith(f"({DRAFT[language]})"))
        main = next(p for p in lives if p.id != draft.id)
        return {
            "showcase": main.id,
            "draft": draft.id,
            "running": sims[-2 if sims[0].updated < sims[-1].updated else -1].id,
            "simulator": sims[-1 if sims[0].updated < sims[-1].updated else -2].id,
        }
    showcase.install(services)
    assert services.showcase is not None
    services.showcase(LOCAL_SESSION, language)
    ids = {"showcase": services.projects(LOCAL_SESSION)[0].id}
    definition = showcase.definition(language)
    draft_definition = definition.model_copy(
        update={"name": f"{definition.name} ({DRAFT[language]})"}
    )
    ids["draft"] = services.create(LOCAL_SESSION, draft_definition, language).id
    name = "Przykładowy projekt (mały)" if language == "pl" else "Example project (small)"
    spec = SimulatorSpec(
        name=name, set_name="j30", instance="j3026_7", scenario=1, start=date(2026, 11, 2)
    )
    job = services.create_simulator(LOCAL_SESSION, spec, language)
    ids["running"] = str(job.project)
    services.advance(LOCAL_SESSION, ids["running"], 34, language)
    job = services.create_simulator(LOCAL_SESSION, spec, language)
    ids["simulator"] = str(job.project)
    services.advance(LOCAL_SESSION, ids["simulator"], 10_000, language)
    return ids


@contextmanager
def serving(config: AppConfig, services: Services) -> Iterator[str]:
    """The app on a free port of 127.0.0.1 while the context lasts."""
    port = free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_app(config, services), port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


def shots_of(ids: dict[str, str], rec: int | None) -> list[Shot]:
    live = f"/projects/{ids['showcase']}"
    draft = f"/projects/{ids['draft']}/setup"
    recommendation = f"{live}/recommendations/{rec}"
    return [
        Shot("start", "/", ".project-card .card-number:not(.skeleton)"),
        Shot("wizard_basics", "/new"),
        Shot("wizard_team", f"{draft}/team"),
        Shot("wizard_tasks", f"{draft}/tasks"),
        Shot("wizard_import", f"{draft}/tasks?tab=import"),
        Shot("overview", live, "#forecast .headline-number"),
        Shot("overview_threats", live, "#drivers .threats, #drivers p", "#threats-title"),
        Shot("checkin", f"{live}/checkin"),
        Shot("recommendation", recommendation),
        Shot(
            "recommendation_options",
            recommendation,
            None,
            "#compare-disclosure",
            "#compare-disclosure > summary",
        ),
        Shot("history", f"{live}/history", "#chance-history svg, #chance-history p"),
        Shot("settings", f"{live}/settings", None, "#autonomy-title"),
        Shot("simulator", "/simulator"),
        Shot("simulator_running", f"/projects/{ids['running']}"),
        Shot("simulator_comparison", f"/projects/{ids['simulator']}", None, "#compare-title"),
        Shot("app_settings", "/settings"),
        Shot("how", "/how-it-works"),
        Shot("error", "/projects/none"),
    ]


def save(page: Any, target: Path, full: bool = False) -> int:
    """A screenshot with a reduced palette; its size in bytes."""
    page.screenshot(path=str(target), full_page=full)
    with Image.open(target) as image:
        reduced = image.convert("RGB").quantize(COLOURS, dither=Image.Dither.NONE)
    reduced.save(target, optimize=True)
    return target.stat().st_size


def capture(
    browser: Any, base: str, shots: list[Shot], language: str, out: Path, full: bool = False
) -> None:
    for suffix, (width, height) in SIZES.items():
        context = browser.new_context(
            viewport={"width": width, "height": height},
            locale=LOCALES[language],
            color_scheme="light",
            reduced_motion="reduce",
        )
        context.add_cookies([{"name": "sentinel_lang", "value": language, "url": base}])
        page = context.new_page()
        for shot in shots:
            page.goto(base + shot.path)
            page.wait_for_load_state("networkidle")
            if shot.ready is not None:
                page.wait_for_selector(shot.ready, timeout=30_000)
                page.wait_for_load_state("networkidle")
            if shot.click is not None:
                page.locator(shot.click).click()
            if shot.scroll is not None:  # the element at the top, with a little space above it
                page.locator(shot.scroll).evaluate("e => e.scrollIntoView({block: 'start'})")
                page.evaluate("window.scrollBy(0, -72)")
            target = out / f"{language}_{shot.name}{suffix}.png"
            print(f"{target}: {save(page, target, full) / 1024:.0f} kB")
        context.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lang", nargs="+", choices=("pl", "en"), default=["pl", "en"])
    parser.add_argument("--out", type=Path, default=Path("docs/ui"))
    parser.add_argument("--data", type=Path, default=None, help="keep the seeded data here")
    parser.add_argument("--only", nargs="*", default=None, help="only these screens")
    parser.add_argument("--full", action="store_true", help="whole pages, for a visual review")
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright

    args.out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        for language in args.lang:
            browser = playwright.chromium.launch(env=language_env(language))
            folder = args.data / language if args.data else None
            data = folder or Path(tempfile.mkdtemp(prefix="sentinel-ui-"))
            data.mkdir(parents=True, exist_ok=True)
            config = AppConfig(data_dir=data, inline_jobs=True)
            services = Services(config)
            began = time.perf_counter()
            ids = seed(services, language)
            rec = services.live(LOCAL_SESSION, ids["showcase"], language).open_recommendation
            print(f"seeded in {time.perf_counter() - began:.1f} s: {ids}, recommendation {rec}")
            shots = shots_of(ids, rec)
            if args.only:
                shots = [s for s in shots if s.name in args.only]
            with serving(config, services) as base:
                capture(browser, base, shots, language, args.out, args.full)
            if not args.only or "start_empty" in args.only:
                empty = AppConfig(data_dir=Path(tempfile.mkdtemp(prefix="sentinel-ui-")))
                with serving(empty, Services(empty)) as base:
                    capture(browser, base, [Shot("start_empty", "/")], language, args.out)
            browser.close()
    total = sum(p.stat().st_size for p in args.out.glob("*.png"))
    print(f"total {total / 1024:.0f} kB of {LIMIT_BYTES / 1024:.0f} kB")
    return 0 if total <= LIMIT_BYTES else 1


if __name__ == "__main__":
    sys.exit(main())
