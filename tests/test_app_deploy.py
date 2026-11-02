"""Packaging and the public demo (WP9c, ADR-0026): client addresses behind the local proxy, the
demo's per-visitor limits, the Docker files and the scripts."""

import re
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentinel.app.api import create_app
from sentinel.app.config import AppConfig, Limits, load_config
from sentinel.app.security import client_address

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
