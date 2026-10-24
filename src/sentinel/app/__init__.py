"""The application (WP9; spec section 11): live projects that a project manager updates at
check-ins, simulator projects with a hidden world, an SQLite store with an append-only event log,
services without HTTP and a FastAPI app (`sentinel ui`). No research package imports it, and only
it and the command line import the web stack (ADR-0022).
"""
