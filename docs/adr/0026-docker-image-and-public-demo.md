# ADR-0026: A multi-stage uv image for company servers, the public demo behind Tailscale Funnel

- Status: accepted
- Date: 2026-10-26
- WP: WP9c

## Context

The application (spec section 11) must run for a team on a company server that IT runs, on a
manager's laptop, and as the public course demo on the owner's server (4 cores, WSL2, no root,
Tailscale). The dependencies are locked in `uv.lock`; the app keeps its database, settings, the
AI key and caches in one data directory; PSPLIB data may not be committed or redistributed
casually (invariant 5); the demo limits count requests per client address (ADR-0024), and the
funnel's proxy connects from 127.0.0.1, so every visitor looks local unless the app reads
`X-Forwarded-For`, which a client could forge.

## Decision

A two-stage `Dockerfile`: uv 0.13.2 installs the locked dependencies and the project (not
editable) into `/app/.venv` on `python:3.12-slim`; the runtime stage copies the environment, the
configs and `fetch_psplib.py`, runs `sentinel ui --config configs/app_server.toml` as user 10001
with `/data` a volume and a `HEALTHCHECK` on `/api/health`. `docker-compose.yml` publishes it on
127.0.0.1:8000 with a named volume and an optional `ollama` profile. The demo runs
`sentinel ui --demo` on 127.0.0.1 under tmux or a user systemd service (`scripts/run_demo.sh`),
published by `tailscale funnel`; uvicorn's own proxy-header handling is off and the app trusts
`X-Forwarded-For` only from 127.0.0.1 (the last hop that is not the proxy), with a local-only
`/api/client-address` to check what it sees.

## Alternatives considered

| Option | Why not |
| --- | --- |
| A single-stage image with `uv` and the build cache | Larger, ships the build tool; the runtime needs only the environment |
| `pip install` from the wheel instead of `uv sync --frozen` | Would not use the lock file, so versions could drift from the tested ones |
| Alpine or distroless base | musl breaks the manylinux wheels of numpy, OR-Tools and matplotlib; distroless has no shell for the health check's Python |
| PSPLIB baked into the image | Redistributes benchmark data; fetched into the volume on demand instead (simulator only) |
| uvicorn's `--proxy-headers` with `--forwarded-allow-ips` | Works, but the rule would live in a start flag; the app's guard states it, tests it and reports it |
| A reverse proxy (Caddy, nginx) in front of the demo | Tailscale Funnel already terminates HTTPS; one more service to run without root |

## Consequences

The image holds no secret and no data; upgrading is `docker compose up -d --build` with the
volume kept. The app has no accounts, so a company deployment must stay inside the network or
behind a signing-in proxy (the user guide and `docs/deploy.md` say so). The simulator needs the
PSPLIB download into the volume once. Docker was not available on the build server in WP9c:
the recipe was checked by replaying its steps (a non-editable install from the build context
into a fresh environment, started with the server config: health, a project created and
planned through the API), and the owner builds the image (`docs/deploy.md`).
