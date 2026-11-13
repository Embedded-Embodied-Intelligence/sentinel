"""The v2 interface under /v2 (WP15, ADR-0033; docs/design/v2-spec.md): new pages on the same
services as the first interface, which stays at /."""

from datetime import date

from fastapi import FastAPI
from markupsafe import Markup, escape

from sentinel.app.ui.core import Ui


def breaks(text: str) -> Markup:
    """A text escaped, its paragraph breaks as line breaks (the tracked view keeps the flow)."""
    return Markup("<br><br>").join(escape(part) for part in text.split("\n\n"))


def mount(app: FastAPI, ui: Ui) -> None:
    """Serve the v2 pages (the frame's routes last)."""
    from sentinel.app.ui.v2 import (
        calendar,
        decision,
        evidence,
        finance,
        lab,
        log,
        overview,
        plan,
        report,
        reports,
        rules,
        settings,
        shell,
        start,
        voice,
        wizard,
    )

    ui.env.globals["evidence_count"] = evidence.evidence_count  # the "Dowód" points (v3)
    ui.env.filters["breaks"] = breaks  # Raporty's tracked view: a blank line as a break (WP20)
    ui.env.filters["iso_date"] = date.fromisoformat
    for module in (
        start,
        wizard,
        overview,
        decision,
        report,
        reports,
        finance,
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
