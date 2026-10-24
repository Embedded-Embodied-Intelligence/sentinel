# ADR-0022: FastAPI, server-rendered HTML and SQLite for the application

- Status: accepted
- Date: 2026-10-24
- WP: WP9a

## Context

WP9 turns the engine into a web application for project managers who never open a terminal: a
local app (`sentinel ui` on a laptop, or Docker on a company server) and a public demo behind
Tailscale Funnel. The owner fixed the stack: open source (MIT), free to run, FastAPI with
server-rendered HTML and HTMX (WP9b), SQLite from the standard library, the LLM optional. The
research code is pure Python with pydantic v2 models; a deliberation takes 0.4–0.7 s and a
simulator run up to a minute, so long operations must not block a request.

## Decision

Runtime dependencies `fastapi`, `uvicorn`, `jinja2` (WP9b templates) and `python-multipart`
(CSV and JSON uploads), and `httpx` for FastAPI's test client in the dev group; nothing else
(transitively: starlette, anyio, h11, click, markupsafe, annotated-doc, opentelemetry-api). The
app lives in `sentinel.app`: services without HTTP, a JSON API with typed pydantic request and
response models, and a background worker (threads) for long operations. Only `sentinel.app` and
`cli.py` import the web stack, and no research package imports `sentinel.app` (a test enforces
both), so the simulation, agent, policy and forecasting code stay free of web imports.

## Alternatives considered

| Option | Why not |
| --- | --- |
| A single-page JavaScript front end (React, Vue) | A build chain and a second language for a course prototype; HTMX fragments need none |
| Flask or Django | Owner's decision; FastAPI validates pydantic models, which the domain already uses |
| Streamlit or Dash | Hard to make multi-user with per-visitor sandboxes, limits and CSRF tokens |
| A process pool for jobs | Pickled states and a second database connection per process; threads suffice at 1–2 workers (CP-SAT releases the GIL) |
| `itsdangerous` (Starlette sessions) for signed cookies | Not on the dependency list; HMAC-SHA256 from the standard library signs the session id |

## Consequences

`uv sync` installs the web stack also for research-only use (about 4 MB). Starlette's test client
warns that `httpx` is deprecated in favour of `httpx2`; the warning is filtered in the pytest
configuration until the WP prompt allows the switch. The API is the contract for WP9b: every
response model is typed, and errors share one format with user-readable messages in English and
Polish.
