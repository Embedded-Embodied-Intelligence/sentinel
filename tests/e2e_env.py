"""The environment of Playwright's Chromium in the end-to-end tests (WP9c): the system libraries
that `scripts/setup_e2e_libs.sh` extracted without root, added to LD_LIBRARY_PATH."""

import os
from pathlib import Path

E2E_LIBS = Path(
    os.environ.get("SENTINEL_E2E_LIBS", Path.home() / ".local" / "share" / "sentinel-e2e-libs")
)


def chromium_env() -> dict[str, str] | None:
    """The environment for Chromium with the extracted libraries first on LD_LIBRARY_PATH;
    None (the process's own environment) if the script has not been run."""
    folders = sorted(str(p) for p in (E2E_LIBS / "usr" / "lib").glob("*-linux-gnu") if p.is_dir())
    if not folders:
        return None
    current = os.environ.get("LD_LIBRARY_PATH")
    path = ":".join([*folders, current] if current else folders)
    return {**os.environ, "LD_LIBRARY_PATH": path}
