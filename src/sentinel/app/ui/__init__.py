"""The pages of the application (WP9b; spec section 11; ADR-0025): server-rendered Jinja2
templates with HTMX for partial updates and job polling, served by the WP9a FastAPI app.

The pages speak to project managers in Polish (the default) or English, with the wording of spec
section 11.7: dates instead of day numbers, percentages instead of probabilities, no internal
term. They call the services directly (`app/services.py`), so the pages and the JSON API show
the same views; every state change goes through HTMX with the session's CSRF header (ADR-0024).
"""

from sentinel.app.ui.core import mount

__all__ = ["mount"]
