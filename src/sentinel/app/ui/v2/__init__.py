"""The v2 interface under /v2 (WP15, ADR-0033; docs/design/v2-spec.md): new pages on the same
services as the first interface, which stays at /."""

from fastapi import FastAPI

from sentinel.app.ui.core import Ui


def mount(app: FastAPI, ui: Ui) -> None:
    """Serve the v2 pages (the frame's routes last)."""
    from sentinel.app.ui.v2 import (
        calendar,
        decision,
        evidence,
        lab,
        log,
        overview,
        plan,
        report,
        rules,
        settings,
        shell,
        start,
        voice,
        wizard,
    )

    ui.env.globals["evidence_count"] = evidence.evidence_count  # the "Dowód" points (v3)
    for module in (
        start,
        wizard,
        overview,
        decision,
        report,
        log,
        plan,
        lab,
        settings,
        calendar,
        voice,
        evidence,
        rules,
        shell,
    ):
        app.include_router(module.router(ui))
