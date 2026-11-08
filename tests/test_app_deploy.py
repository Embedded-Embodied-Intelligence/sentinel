"""Packaging and the public demo (WP9c, ADR-0026): client addresses behind the local proxy, the
demo's per-visitor limits, the Docker files and the scripts."""

import re
import socket
import subprocess
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from sentinel.app.api import create_app
from sentinel.app.config import AppConfig, Limits, load_config
from sentinel.app.security import client_address, is_local

ROOT = Path(__file__).resolve().parents[1]
PROXY = ("127.0.0.1", 40000)  # the funnel's proxy connects from the server itself
REMOTE = ("198.51.100.4", 40000)


def test_forwarded_addresses_are_trusted_only_from_the_local_proxy() -> None:
    assert client_address("127.0.0.1", "203.0.113.7", True) == "203.0.113.7"
    # a client's own header comes first; the proxy appends what it saw
    assert client_address("127.0.0.1", "10.0.0.1, 203.0.113.7", True) == "203.0.113.7"
    assert client_address("127.0.0.1", "203.0.113.7, 127.0.0.1", True) == "203.0.113.7"
    assert client_address("198.51.100.4", "203.0.113.7", True) == "198.51.100.4"
    assert client_address("127.0.0.1", "203.0.113.7", False) == "127.0.0.1"
    assert client_address("127.0.0.1", None, True) == "127.0.0.1"
    assert client_address(None, None, True) == "?"


def test_the_demo_limits_each_visitor_by_the_address_the_proxy_saw(tmp_path: Path) -> None:
    config = AppConfig(
        data_dir=tmp_path,
        demo=True,
        trust_proxy=True,
        showcase=False,
        limits=Limits(requests_per_minute=3),
    )
    app = create_app(config)
    with TestClient(app, client=PROXY) as proxy, TestClient(app, client=REMOTE) as remote:
        seen = proxy.get("/api/client-address", headers={"X-Forwarded-For": "203.0.113.7"})
        assert seen.json() == {
            "address": "203.0.113.7",
            "peer": "127.0.0.1",
            "forwarded_for": "203.0.113.7",
            "trusted": True,
            "limited": True,
        }
        first = {"X-Forwarded-For": "203.0.113.7"}
        codes = [proxy.get("/api/health", headers=first).status_code]  # health is never limited
        codes += [proxy.get("/api/session", headers=first).status_code for _ in range(3)]
        assert codes == [200, 200, 200, 429]  # 3 per minute, the check counted once
        other = proxy.get("/api/session", headers={"X-Forwarded-For": "203.0.113.8"})
        assert other.status_code == 200  # another visitor behind the same proxy
        # A remote client cannot pick its address, nor see the check.
        assert remote.get("/api/client-address").status_code == 404
        forged = [
            remote.get("/api/session", headers={"X-Forwarded-For": f"192.0.2.{i}"}).status_code
            for i in range(3)
        ]
        assert forged == [200, 200, 429]  # one bucket: the 404 above counted too


def _own_address() -> str | None:
    """This machine's address towards the outside, if it has a route (nothing is sent)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("192.0.2.1", 9))
        except OSError:
            return None
        return str(probe.getsockname()[0])


def test_the_local_proxy_is_any_address_of_this_machine() -> None:
    assert is_local("127.0.0.1") and is_local("127.0.0.2") and is_local("::1")
    assert is_local("::ffff:127.0.0.1")
    assert not is_local("192.0.2.1") and not is_local("198.51.100.4")
    assert not is_local("0.0.0.0") and not is_local("?") and not is_local(None)
    own = _own_address()
    if own is not None and not own.startswith("127."):
        # Under WSL2 with Docker a connection to 127.0.0.1 arrives from eth0's address.
        assert is_local(own)
        assert client_address(own, "203.0.113.7", True) == "203.0.113.7"
        assert client_address(own, f"203.0.113.7, {own}", True) == "203.0.113.7"


def test_the_running_demo_answers_the_local_proxy_with_the_forwarded_address(
    tmp_path: Path,
) -> None:
    """Through a real socket, as `sentinel ui --demo` serves it (WP16 hotfix: the host
    rewrote 127.0.0.1 to eth0's address, which the in-process test client never shows)."""
    config = load_config(ROOT / "configs" / "app_demo.toml", data_dir=tmp_path, showcase=False)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(  # as `sentinel ui` runs it: uvicorn's proxy handling off
            create_app(config),
            host="127.0.0.1",
            port=port,
            log_level="warning",
            proxy_headers=False,
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 30
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        assert server.started, "the server did not start"
        seen = httpx.get(
            f"http://127.0.0.1:{port}/api/client-address",
            headers={"X-Forwarded-For": "203.0.113.7"},
            timeout=10,
        )
        assert seen.status_code == 200, seen.text
        body = seen.json()
        assert body["address"] == "203.0.113.7" and body["trusted"] and body["limited"]
        assert is_local(body["peer"])
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_every_response_carries_the_security_headers(tmp_path: Path) -> None:
    """WP17: a strict content policy (scripts only from the server, no framing), no MIME
    sniffing, no referrer to other sites, the microphone for this site only; HSTS over HTTPS."""
    config = load_config(ROOT / "configs" / "app_demo.toml", data_dir=tmp_path, showcase=False)
    with TestClient(create_app(config), base_url="https://testserver", client=PROXY) as client:
        for path in ("/v2", "/api/health", "/static/sentinel-v2.css", "/nowhere"):
            headers = client.get(path).headers
            policy = headers["content-security-policy"]
            assert "script-src 'self';" in policy and "frame-ancestors 'none'" in policy, path
            assert headers["x-content-type-options"] == "nosniff"
            assert headers["x-frame-options"] == "DENY"
            assert headers["referrer-policy"] == "same-origin"
            assert "microphone=(self)" in headers["permissions-policy"]
            assert headers["strict-transport-security"].startswith("max-age=")


def test_the_compose_file_and_the_image() -> None:
    yaml = pytest.importorskip("yaml")  # PyYAML comes with the dev tools (pre-commit)
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    app, ollama = compose["services"]["sentinel"], compose["services"]["ollama"]
    assert app["build"] == "." and "sentinel-data:/data" in app["volumes"]
    assert app["ports"] == ["127.0.0.1:${SENTINEL_PORT:-8000}:8000"]  # this host only
    assert "/api/health" in " ".join(app["healthcheck"]["test"])
    assert ollama["profiles"] == ["ollama"] and "profiles" not in app
    assert set(compose["volumes"]) == {"sentinel-data", "ollama-models"}
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    stages = re.findall(r"^FROM (\S+)(?: AS (\w+))?", dockerfile, re.MULTILINE)
    assert [name for _, name in stages] == ["uv", "build", "runtime"]
    assert re.search(r"^ARG PYTHON_IMAGE=python:3\.12-slim$", dockerfile, re.MULTILINE)
    assert "uv sync --frozen --no-dev --no-editable" in dockerfile
    assert re.search(r"^USER sentinel$", dockerfile, re.MULTILINE)
    assert re.search(r'^VOLUME \["/data"\]$', dockerfile, re.MULTILINE)
    assert re.search(r"^HEALTHCHECK .*\n.*/api/health", dockerfile, re.MULTILINE)
    command = re.search(r"^CMD \[(.*)\]$", dockerfile, re.MULTILINE)
    assert command is not None and '"/app/configs/app_server.toml"' in command.group(1)
    server = load_config(ROOT / "configs" / "app_server.toml")
    assert server.data_dir == Path("/data") and not server.demo
    assert server.psplib_root == Path("/data/psplib")
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert ignored[ignored.index("*") + 1 :][:3] == ["!pyproject.toml", "!uv.lock", "!README.md"]
    assert "**/.env" in ignored and "!data/" not in ignored


@pytest.mark.parametrize("script", ["run_demo.sh", "setup_e2e_libs.sh"])
def test_the_scripts_are_executable_bash(script: str) -> None:
    path = ROOT / "scripts" / script
    assert path.stat().st_mode & 0o111
    subprocess.run(["bash", "-n", str(path)], check=True)


def test_the_ollama_address_suggested_in_docker_is_the_containers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Task 15 of WP12: in Docker the compose file sets OLLAMA_HOST to the ollama container, and
    the settings page suggests that address instead of the host's own."""
    from sentinel.app.ui.pages import ollama_placeholder

    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    assert ollama_placeholder() == "http://127.0.0.1:11434"
    monkeypatch.setenv("OLLAMA_HOST", "http://ollama:11434")
    assert ollama_placeholder() == "http://ollama:11434"
    compose = (Path(__file__).parents[1] / "docker-compose.yml").read_text("utf-8")
    assert "OLLAMA_HOST: http://ollama:11434" in compose
