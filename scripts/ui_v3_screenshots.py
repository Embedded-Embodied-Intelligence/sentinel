"""Screenshots of the v3 screens and of an open "Dowód" panel (WP19; docs/design/v3-spec.md).

Seeds a data directory with the showcase project in the chosen language, serves the app
in-process and captures Mapa granic, Uprawnienia AI (with "Próba ataku" run on the recorded
answer), Ludzie, Źródła, the panel opened from Pulpit's "Szansa na termin" and from a cell of
the map, and the decision page with "Twoja ocena", at 1440x900 and 1280x800 in the light theme
(the dark one on request), with Playwright's Chromium. The PNGs go to docs/ui/v3/ as
`<lang>_<theme>_<screen>_<width>.png` with a reduced palette (the v2 script's `save`).

    uv run python scripts/ui_v3_screenshots.py [--lang pl en] [--theme light] [--only map]
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from ui_screenshots import language_env, serving
from ui_v2_screenshots import SIZES, Shot, capture

from sentinel.app import showcase
from sentinel.app.config import AppConfig
from sentinel.app.services import Services
from sentinel.app.store import LOCAL_SESSION


def seed(services: Services, language: Any) -> dict[str, str]:
    """The showcase project (two reports and a decision waiting); its id."""
    services.local_session()
    showcase.install(services)
    assert services.showcase is not None
    services.showcase(LOCAL_SESSION, language)
    return {"showcase": services.projects(LOCAL_SESSION)[0].id}


def shots_of(ids: dict[str, str], rec: int | None) -> list[Shot]:
    live = f"/v2/projects/{ids['showcase']}"
    return [
        Shot("map", "/v2/map"),
        Shot(
            "map_cell", "/v2/map", clicks=(".map-cell[data-dowod$='/P06/3']",), wait="#dowod[open]"
        ),
        Shot("permissions", "/v2/permissions"),
        Shot(
            "permissions_attack",
            "/v2/permissions",
            clicks=("[data-attack-run]",),
            wait="#attack-result .attack-out",
            scroll="#attack-title",
        ),
        Shot("people", "/v2/people"),
        Shot("sources", "/v2/sources"),
        Shot("sources_open", "/v2/sources?stance=podwaza", clicks=("details.src-item > summary",)),
        Shot(
            "overview_panel",
            live,
            clicks=("[data-decision='D01']",),
            wait="#dowod[open] .ev",
        ),
        Shot("decision_assessment", f"{live}/decisions/{rec}"),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lang", nargs="+", choices=("pl", "en"), default=["pl", "en"])
    parser.add_argument("--theme", nargs="+", choices=("light", "dark"), default=["light"])
    parser.add_argument("--out", type=Path, default=Path("docs/ui/v3"))
    parser.add_argument("--only", nargs="*", default=None, help="only these screens")
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright

    args.out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        for language in args.lang:
            browser = playwright.chromium.launch(env=language_env(language))
            data = Path(tempfile.mkdtemp(prefix="sentinel-v3-ui-"))
            # An AI provider, so that "Teraz" names a model; no screenshot calls it.
            settings = {"llm": {"provider": "ollama"}}
            (data / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
            config = AppConfig(data_dir=data, inline_jobs=True)
            services = Services(config)
            ids = seed(services, language)
            rec = services.live(LOCAL_SESSION, ids["showcase"], language).open_recommendation
            shots = shots_of(ids, rec)
            if args.only:
                shots = [s for s in shots if s.name in args.only]
            with serving(config, services) as base:
                for theme in args.theme:
                    capture(browser, base, shots, language, theme, args.out, SIZES)
            browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
