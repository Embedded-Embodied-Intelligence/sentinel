# syntax=docker/dockerfile:1
# The Sentinel application for a company server (WP9c, ADR-0026; docs/deploy.md).
#
#     docker compose up -d                       # http://localhost:8000
#     docker build -t sentinel:1.2.3 .           # the image alone
#
# Two stages: `build` resolves the locked dependencies with uv into /app/.venv and installs the
# project into it (not editable); `runtime` copies that environment onto a clean Python 3.12
# slim image and runs `sentinel ui` as an unprivileged user. Projects, settings, keys and caches
# live in the /data volume, never in the image.

ARG PYTHON_IMAGE=python:3.12-slim

FROM ghcr.io/astral-sh/uv:0.13.2 AS uv

FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/local/bin/python3 \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /src
# The dependencies first, so that a code change does not download them again.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY README.md LICENSE ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

FROM ${PYTHON_IMAGE} AS runtime
RUN groupadd --system --gid 10001 sentinel \
    && useradd --system --uid 10001 --gid sentinel --home-dir /data --no-create-home \
        --shell /usr/sbin/nologin sentinel \
    && mkdir -p /data \
    && chown sentinel:sentinel /data
COPY --from=build /app/.venv /app/.venv
# The configs the app reads at run time (the server's settings, the simulator's study worlds)
# and the downloader of the simulator's example projects (PSPLIB, fetched into the volume).
COPY configs /app/configs
COPY scripts/fetch_psplib.py /app/scripts/fetch_psplib.py
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp/matplotlib
WORKDIR /app
USER sentinel
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; r = urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4); sys.exit(0 if r.status == 200 else 1)"]
CMD ["sentinel", "ui", "--host", "0.0.0.0", "--port", "8000", "--config", "/app/configs/app_server.toml"]
