# The Docker deployment checked (WP11)

`scripts/docker_check.py --ollama` (Docker 29.1.3, Compose 2.40.3, the 4-core server without a
GPU, 2026-11-02) built the image with `docker compose build`, started the app with `docker compose
up -d` on port 8002 as its own compose project (`sentinel-check`), created a project through the
Polish wizard in the container, restarted the container, then removed and recreated it, and
finally started the `ollama` profile, pulled `qwen2.5:7b` and tested it on the settings page.

- `docker-log.json`: every step with its time (build, image size, start, the project, restart,
  recreate, the `ollama` profile, memory).
- `shots/`: the project's overview after its plan, the start page after the container was
  recreated (the project is listed), and the settings page's test of the local model.

Results and their reading: `docs/deploy.md` ("Measured in WP11") and `docs/reports/WP11.md`.
