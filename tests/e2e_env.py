"""Helpers of the end-to-end tests (WP9b, WP9c): the app served by uvicorn in a thread, and the
environment of Playwright's Chromium with the system libraries that `scripts/setup_e2e_libs.sh`
extracted without root on LD_LIBRARY_PATH."""

import os
import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import uvicorn

from sentinel.app.api import create_app
from sentinel.app.config import AppConfig
from sentinel.app.llm import ClientFactory, TranscriberFactory
from sentinel.app.services import Services

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


@dataclass
class Server:
    base: str
    services: Services
    config: AppConfig


def serve(
    config: AppConfig,
    llm_factory: ClientFactory | None = None,
    transcriber: TranscriberFactory | None = None,
) -> Iterator[Server]:
    """The app of `config` on a free port of 127.0.0.1 until the generator is closed."""
    services = Services(config, llm_factory=llm_factory, transcriber=transcriber)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(create_app(config, services), port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started, "the server did not start"
    yield Server(f"http://127.0.0.1:{port}", services, config)
    server.should_exit = True
    thread.join(timeout=10)
