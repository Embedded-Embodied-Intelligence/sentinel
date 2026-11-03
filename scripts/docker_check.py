"""The Docker deployment set up as IT would, through docker compose and the browser (WP11 task 2;
docs/deploy.md).

Builds the image with `docker compose build`, reports its size, starts the app with `docker compose
up -d` on a port of this host (`SENTINEL_PORT`) and times it until `/api/health` answers, then
creates a project through the pages in the container (the Polish wizard of `qa_run.py`: the team
pasted, the tasks from a spreadsheet, a plan). It restarts the container, then removes and
recreates it (`docker compose down`, `up -d`; the volume stays), and after each checks in a new
browser that the project, its team, its tasks and its plan are as they were. With `--ollama` it
also starts the `ollama` profile, pulls the default local model in that container and tests it
on the settings page.

    uv run python scripts/docker_check.py [--port 8002] [--out DIR] [--ollama] [--keep]

It runs as its own compose project (`--project sentinel-check`), so a deployment on the same host
keeps its containers and data; `docker compose -p sentinel-check down -v` removes the check's
volumes. A shell started before its user joined the `docker` group needs `sg docker -c "..."`.
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from qa_run import Driver, create_project, write_log
from ui_screenshots import language_env

ROOT = Path(__file__).resolve().parents[1]
NAME = "Portal w kontenerze"
MODEL = "qwen2.5:7b"  # the app's default local model (`sentinel.app.llm.DEFAULT_MODELS`)
KEPT = ("name", "definition", "has_plan", "baseline", "tasks", "people", "checkins")
LIMIT_S = 180.0  # for the app to answer after a start
WAIT_MS = 600_000  # a first answer of a local model on a processor loads it


class Compose:
    """`docker compose` of this checkout as its own project, publishing the app on `port`."""

    def __init__(self, project: str, port: int) -> None:
        self.command = ["docker", "compose", "--project-name", project]
        self.env = {**os.environ, "SENTINEL_PORT": str(port)}

    def __call__(self, *args: str, ollama: bool = False) -> str:
        profile = ["--profile", "ollama"] if ollama else []
        done = subprocess.run(
            [*self.command, *profile, *args],
            cwd=ROOT,
            env=self.env,
            check=True,
            capture_output=True,
            text=True,
        )
        return done.stdout.strip()


def docker(*args: str) -> str:
    return subprocess.run(
        ["docker", *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def since(began: float) -> float:
    return round(time.perf_counter() - began, 1)


def answering(base: str, began: float) -> float:
    """Seconds from `began` until `/api/health` answers 200."""
    while time.perf_counter() - began < LIMIT_S:
        try:
            with urllib.request.urlopen(f"{base}/api/health", timeout=2) as response:
                if response.status == 200:
                    return since(began)
        except OSError:
            pass
        time.sleep(0.1)
    raise TimeoutError(f"{base}/api/health did not answer within {LIMIT_S:.0f} s")


def healthy(compose: Compose, began: float) -> float:
    """Seconds from `began` until Docker's health check calls the app's container healthy."""
    container = compose("ps", "-q", "sentinel")
    while time.perf_counter() - began < LIMIT_S:
        status = docker("inspect", "--format", "{{.State.Health.Status}}", container)
        if status == "healthy":
            return since(began)
        time.sleep(0.5)
    raise TimeoutError(f"the container was not healthy within {LIMIT_S:.0f} s")


def browse(browser: Any, base: str) -> Any:
    """A new browser, as another person on another day: no cookies but the language."""
    context = browser.new_context(
        viewport={"width": 1280, "height": 800}, locale="pl-PL", reduced_motion="reduce"
    )
    context.set_default_timeout(60_000)
    context.add_cookies([{"name": "sentinel_lang", "value": "pl", "url": base}])
    return context


def kept(page: Any, base: str, project: str) -> dict[str, Any]:
    """What of the project a restart must keep, as the API shows it."""
    data = page.request.get(f"{base}/api/projects/{project}").json()
    return {key: data[key] for key in KEPT}


def run(args: argparse.Namespace, browser: Any) -> int:
    compose = Compose(args.project, args.port)
    base = f"http://127.0.0.1:{args.port}"
    args.out.mkdir(parents=True, exist_ok=True)
    log: list[dict[str, Any]] = []

    def note(**values: Any) -> None:
        log.append(values)
        print(json.dumps(values, ensure_ascii=False, default=str)[:400], flush=True)

    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True)
    note(
        kind="versions",
        commit=head.stdout.decode().strip(),
        docker=docker("version", "--format", "{{.Server.Version}}"),
        compose=docker("compose", "version", "--short"),
    )
    began = time.perf_counter()
    compose("build", "sentinel")
    image = compose("config", "--images").splitlines()[0]
    content = int(docker("image", "inspect", "--format", "{{.Size}}", image))
    note(
        kind="image",
        image=image,
        build_s=since(began),
        disk=docker("image", "ls", "--format", "{{.Size}}", image),
        compressed_mb=round(content / 1e6, 1),
    )
    began = time.perf_counter()
    compose("up", "-d")
    note(kind="up", answering_s=answering(base, began), healthy_s=healthy(compose, began))
    failures = 0
    context = browse(browser, base)
    d = Driver(context.new_page(), base, args.out, "docker")
    try:
        project = create_project(d, NAME)
        before = kept(d.page, base, project)
        note(
            kind="project",
            people=len(before["people"]),
            tasks=len(before["tasks"]),
            has_plan=before["has_plan"],
        )
        context.close()
        for step, commands in (
            ("restart", [("restart", "sentinel")]),
            ("recreate", [("down",), ("up", "-d")]),
        ):
            began = time.perf_counter()
            for command in commands:
                compose(*command)
            seconds = answering(base, began)
            context = browse(browser, base)
            page = context.new_page()
            page.goto(base + "/")
            page.wait_for_load_state("networkidle")
            listed = page.get_by_role("link", name=NAME).count() > 0
            d.shot(f"start_after_{step}", page=page)
            same = kept(page, base, project) == before
            note(kind=step, answering_s=seconds, listed=listed, same=same)
            failures += not (listed and same)
            context.close()
        if args.ollama:
            began = time.perf_counter()
            compose("up", "-d", ollama=True)
            note(kind="ollama_up", seconds=since(began))
            began = time.perf_counter()
            compose("exec", "-T", "ollama", "ollama", "pull", MODEL, ollama=True)
            note(kind="ollama_pull", model=MODEL, seconds=since(began))
            context = browse(browser, base)
            page = context.new_page()
            page.goto(base + "/settings")
            page.wait_for_load_state("networkidle")
            page.get_by_label("Model lokalny (Ollama)").check()
            began = time.perf_counter()
            page.get_by_role("button", name="Sprawdź połączenie").click()
            page.locator("#test-result .callout").wait_for(timeout=WAIT_MS)
            text = page.locator("#test-result").inner_text().strip()
            note(kind="ollama_test", text=text, seconds=since(began))
            d.shot("settings_ollama", full=True, page=page)
            memory = docker("stats", "--no-stream", "--format", "{{.Name}} {{.MemUsage}}")
            note(kind="memory", containers=memory.splitlines())
            failures += MODEL not in text
            context.close()
    except Exception as exc:  # the log still matters when a step fails
        note(kind="failure", error=str(exc)[:600])
        failures += 1
    finally:
        if not args.keep:
            compose("down", ollama=args.ollama)
        write_log(args.out / "docker-log.json", log + d.log)
    print("all steps passed" if not failures else f"{failures} step(s) failed")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8002, help="the app's port on this host")
    parser.add_argument("--project", default="sentinel-check", help="the compose project name")
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "qa" / "docker")
    parser.add_argument("--ollama", action="store_true", help="also the local model's container")
    parser.add_argument("--keep", action="store_true", help="leave the containers running")
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(env=language_env("pl"))
        code = run(args, browser)
        browser.close()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
