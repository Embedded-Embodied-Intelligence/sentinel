"""Screenshots of the main screens for the report and the presentation (WP9b).

Seeds a temporary data directory with the showcase project (a live project with two check-ins
and an open recommendation), a draft of the same project for the wizard's task step and a small
example simulator run finished under Sentinel, serves the app in-process and captures the start
page, the wizard's step 3, the overview, the check-in, the recommendation and the simulator's
comparison at 1280x800 with Playwright's Chromium (light mode). About a minute (the simulator
run). The PNGs go to docs/ui/ (committed); their total size is printed and must stay <= 3 MB.

    uv run python scripts/ui_screenshots.py [--lang pl] [--out docs/ui]
"""

import argparse
import os
import socket
import sys
import tempfile
import threading
import time
from datetime import date
from pathlib import Path

import uvicorn

from sentinel.app import showcase
from sentinel.app.api import create_app
from sentinel.app.config import AppConfig
from sentinel.app.services import Services
from sentinel.app.simulator import SimulatorSpec
from sentinel.app.store import LOCAL_SESSION

WIDTH, HEIGHT = 1280, 800
DRAFT = {"pl": "szkic", "en": "draft"}
LIMIT_BYTES = 3 * 1024 * 1024


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


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def seed(services: Services, language: str) -> dict[str, str]:
    """The showcase, a draft of it and a finished simulator run; their project ids."""
    services.local_session()
    showcase.install(services)
    assert services.showcase is not None
    services.showcase(LOCAL_SESSION, language)  # type: ignore[arg-type]
    ids = {"showcase": services.projects(LOCAL_SESSION)[0].id}
    definition = showcase.definition(language)  # type: ignore[arg-type]
    draft = definition.model_copy(update={"name": f"{definition.name} ({DRAFT[language]})"})
    ids["draft"] = services.create(LOCAL_SESSION, draft, language).id  # type: ignore[arg-type]
    name = "Przykładowy projekt (mały)" if language == "pl" else "Example project (small)"
    spec = SimulatorSpec(
        name=name, set_name="j30", instance="j3026_7", scenario=1, start=date(2026, 11, 2)
    )
    job = services.create_simulator(LOCAL_SESSION, spec, language)  # type: ignore[arg-type]
    ids["simulator"] = str(job.project)
    services.advance(LOCAL_SESSION, ids["simulator"], 10_000, language)  # type: ignore[arg-type]
    return ids


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lang", choices=("pl", "en"), default="pl")
    parser.add_argument("--out", type=Path, default=Path("docs/ui"))
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright

    data = Path(tempfile.mkdtemp(prefix="sentinel-ui-"))
    config = AppConfig(data_dir=data, inline_jobs=True)
    services = Services(config)
    began = time.perf_counter()
    ids = seed(services, args.lang)
    rec = services.live(LOCAL_SESSION, ids["showcase"], args.lang).open_recommendation
    print(f"seeded in {time.perf_counter() - began:.1f} s: {ids}, open recommendation {rec}")
    port = free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_app(config, services), port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    base = f"http://127.0.0.1:{port}"
    showcase_id = ids["showcase"]
    shots = [
        ("start", "/", None),
        ("wizard_tasks", f"/projects/{ids['draft']}/setup/tasks", None),
        ("overview", f"/projects/{showcase_id}", "#forecast .headline"),
        ("checkin", f"/projects/{showcase_id}/checkin", None),
        ("recommendation", f"/projects/{showcase_id}/recommendations/{rec}", None),
        ("simulator_comparison", f"/projects/{ids['simulator']}", "#compare-title"),
    ]
    args.out.mkdir(parents=True, exist_ok=True)
    total = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(env=chromium_env())
        context = browser.new_context(
            viewport={"width": WIDTH, "height": HEIGHT},
            locale="pl-PL" if args.lang == "pl" else "en-GB",
            color_scheme="light",
        )
        context.add_cookies([{"name": "sentinel_lang", "value": args.lang, "url": base}])
        page = context.new_page()
        for name, path, ready in shots:
            page.goto(base + path)
            page.wait_for_load_state("networkidle")
            if ready is not None:
                page.wait_for_selector(ready, timeout=30_000)
            if name == "simulator_comparison":
                page.locator("#compare-title").scroll_into_view_if_needed()
                page.evaluate("window.scrollBy(0, -16)")
            target = args.out / f"{args.lang}_{name}.png"
            page.screenshot(path=str(target))
            size = target.stat().st_size
            total += size
            print(f"{target}: {size / 1024:.0f} kB")
        browser.close()
    server.should_exit = True
    thread.join(timeout=10)
    print(f"total {total / 1024:.0f} kB of {LIMIT_BYTES / 1024:.0f} kB")
    return 0 if total <= LIMIT_BYTES else 1


if __name__ == "__main__":
    sys.exit(main())
