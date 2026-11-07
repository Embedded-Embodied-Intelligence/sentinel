"""The v2 interface under /v2 (WP15, ADR-0033; docs/design/v2-spec.md): new pages on the same
services as the first interface, which stays at /."""

from fastapi import FastAPI

from sentinel.app.ui.core import Ui


def mount(app: FastAPI, ui: Ui) -> None:
    """Serve the v2 pages; the frame's catch-all project tab comes last."""
    from sentinel.app.ui.v2 import decision, overview, shell, start, voice

    for module in (start, overview, decision, voice, shell):
        app.include_router(module.router(ui))
