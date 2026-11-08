"""The calendar feed of a project (WP16; docs/design/v2-spec.md, section 8.9; ADR-0035): text
folded and escaped by RFC 5545, and in the demo a feed that needs no session and lives as long as
the visitor's sandbox. The feed of the showcase, read by a standard parser, is tested with the
other v2 pages (tests/test_v2_pages.py), whose showcase is already set up."""

import sqlite3
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_v2_pages import link_of

from sentinel.app import planning
from sentinel.app.api import create_app
from sentinel.app.config import AppConfig
from sentinel.app.feed import escape, fold
from sentinel.app.services import Services


@pytest.fixture(scope="module", autouse=True)
def fewer_futures() -> Iterator[None]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(planning, "THREAT_ROLLOUTS", 50)
        yield


def test_folding_and_escaping() -> None:
    assert escape("a;b,c\\d\ne") == "a\\;b\\,c\\\\d\\ne"
    line = "SUMMARY:" + "ż" * 60
    parts = fold(line)
    assert (
        all(len(part.encode()) <= 75 for part in parts)
        and "".join(part[1:] if i else part for i, part in enumerate(parts)) == line
    )


@pytest.mark.slow  # a demo app with the showcase (about 2 s)
def test_the_feed_needs_no_session_and_lives_with_the_sandbox(tmp_path: Path) -> None:
    config = AppConfig(data_dir=tmp_path, demo=True, inline_jobs=True)
    services = Services(config)

    def rows(sql: str) -> list[tuple[object, ...]]:
        with sqlite3.connect(services.store.path) as db:
            return db.execute(sql).fetchall()

    with TestClient(create_app(config, services)) as visitor:
        visitor.get("/v2")
        token = visitor.get("/api/session").json()["csrf_token"]
        headers = {"X-CSRF-Token": token, "HX-Request": "true"}
        visitor.post("/v2/example", headers=headers)  # "Otwórz projekt przykładowy"
        project = str(rows("SELECT id FROM projects WHERE kind = 'live'")[0][0])
        path = link_of(visitor, project, headers)
        shown = visitor.get(f"/v2/projects/{project}/settings").text
        assert 'value="http://testserver/calendar/' in shown  # served over HTTP: as it came
    sessions = rows("SELECT COUNT(*) FROM sessions")
    with TestClient(create_app(config, services)) as calendar_app:  # no cookie at all
        assert calendar_app.get(path).status_code == 200
    assert rows("SELECT COUNT(*) FROM sessions") == sessions  # no sandbox for a calendar
    services.store.expire(datetime.now().astimezone() + timedelta(days=1))
    with TestClient(create_app(config, services)) as calendar_app:
        assert calendar_app.get(path).status_code == 404  # gone with its sandbox


def test_behind_an_https_proxy_the_link_is_https(tmp_path: Path) -> None:
    """WP17: the demo is served over HTTPS (secure cookies) by a proxy that speaks HTTP to the
    app; the link a calendar fetches must be https, not the app's own http."""
    config = AppConfig(data_dir=tmp_path, demo=True, inline_jobs=True, secure_cookies=True)
    services = Services(config)
    with TestClient(create_app(config, services), base_url="https://demo.example") as visitor:
        visitor.get("/v2")
        token = visitor.get("/api/session").json()["csrf_token"]
        headers = {"X-CSRF-Token": token, "HX-Request": "true"}
        visitor.post("/v2/example", headers=headers)
        with sqlite3.connect(services.store.path) as db:
            project = str(db.execute("SELECT id FROM projects WHERE kind = 'live'").fetchone()[0])
        visitor.post(f"/v2/projects/{project}/calendar", headers=headers)
        session = visitor.cookies["sentinel_session"]  # the proxy passes it over plain HTTP
    with TestClient(create_app(config, services), base_url="http://demo.example") as proxied:
        cookie = {"cookie": f"sentinel_session={session}"}
        page = proxied.get(f"/v2/projects/{project}/settings", headers=cookie).text
    assert 'value="https://demo.example/calendar/' in page
