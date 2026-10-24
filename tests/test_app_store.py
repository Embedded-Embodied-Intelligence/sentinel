"""The SQLite store of the application (WP9a; ADR-0023): migrations, the append-only event
log, ownership by session, sandbox expiry, jobs and usage counters."""

import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest

from sentinel.app.store import SCHEMA_VERSION, ConflictError, Store, now


def test_schema_is_migrated_by_version_and_reopened_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "app.db"
    store = Store(path)
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    session = store.create_session(demo=False)
    store.create_project(session.id, "live", "P", "created", {"x": 1})
    reopened = Store(path)  # a second start applies nothing
    assert reopened.migrate() == SCHEMA_VERSION
    assert [p.name for p in reopened.projects(session.id)] == ["P"]
    with sqlite3.connect(path) as db:
        db.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    with pytest.raises(RuntimeError, match="newer"):
        Store(path)


def test_events_are_append_only_and_owned_by_their_session(tmp_path: Path) -> None:
    store = Store(tmp_path / "app.db")
    mine, other = store.create_session(demo=True), store.create_session(demo=True)
    project = store.create_project(mine.id, "live", "P", "created", {"n": 1})
    assert store.append(mine.id, project.id, "checkin", {"n": 2}, expected=1) == 2
    with pytest.raises(ConflictError):
        store.append(mine.id, project.id, "checkin", {"n": 3}, expected=1)
    assert [e.payload["n"] for e in store.events(mine.id, project.id)] == [1, 2]
    # Another session sees nothing and cannot write.
    assert store.project(other.id, project.id) is None
    assert store.events(other.id, project.id) == []
    with pytest.raises(KeyError):
        store.append(other.id, project.id, "checkin", {})
    assert not store.delete_project(other.id, project.id)
    with sqlite3.connect(store.path) as db, pytest.raises(sqlite3.DatabaseError, match="append"):
        db.execute("UPDATE events SET payload = '{}'")
    assert store.delete_project(mine.id, project.id)
    assert store.events(mine.id, project.id) == []


def test_sandboxes_expire_with_their_projects_and_jobs(tmp_path: Path) -> None:
    store = Store(tmp_path / "app.db")
    demo, local = store.create_session(demo=True), store.ensure_session("local", demo=False)
    project = store.create_project(demo.id, "live", "P", "created", {})
    store.create_job(demo.id, project.id, "plan")
    store.create_project(local.id, "live", "Q", "created", {})
    assert store.expire(now() - timedelta(hours=1)) == 0
    assert store.expire(now() + timedelta(seconds=1)) == 1  # only the demo session
    assert store.session(demo.id) is None and store.projects(demo.id) == []
    assert [p.name for p in store.projects(local.id)] == ["Q"]


@pytest.mark.slow  # under 2 s; the default run has no room left (75 s)
def test_jobs_and_daily_usage(tmp_path: Path) -> None:
    store = Store(tmp_path / "app.db")
    session = store.create_session(demo=True)
    job = store.create_job(session.id, None, "extract")
    assert store.active_jobs(session.id) == 1
    store.update_job(job.id, status="done", progress=1.0, result={"ok": True})
    done = store.job(session.id, job.id)
    assert done is not None and done.status == "done" and done.result == {"ok": True}
    assert store.active_jobs(session.id) == 0
    assert store.job(store.create_session(demo=True).id, job.id) is None
    running = store.create_job(session.id, None, "plan")
    assert store.fail_unfinished_jobs() == 1  # left by a previous server process
    failed = store.job(session.id, running.id)
    assert failed is not None and failed.status == "failed"
    assert [store.use("llm", 2, day="2026-11-02") for _ in range(3)] == [True, True, False]
    assert store.use("llm", 2, day="2026-11-03")
