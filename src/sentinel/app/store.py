"""SQLite store of the application (stdlib `sqlite3`; ADR-0023): sessions, projects with their
append-only event log, background jobs and daily usage counters.

A project is its event log: every change (definition, baseline plan, check-in, recommendation,
decision, simulator advance) is one event with a sequence number, and the project's state is
rebuilt from its events (spec section 11.5). Events are never updated (a trigger refuses it);
they go only with their project, when it is deleted or its sandbox expires. Every project
belongs to a session, and every read and write of a project or a job names the session, so one
session cannot reach another's data. The schema is migrated by version number (`PRAGMA
user_version`). Each call opens its own connection (WAL mode), so the store can be used from the
request threads and the job worker; writes are serialised by a lock.
"""

import json
import secrets
import sqlite3
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

ProjectKind = Literal["live", "simulator"]
JobStatus = Literal["queued", "running", "done", "failed"]

# Migration i (0-based) brings the schema from version i to version i + 1.
MIGRATIONS: tuple[str, ...] = (
    """
    CREATE TABLE sessions (
        id TEXT PRIMARY KEY,
        created TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        demo INTEGER NOT NULL
    );
    CREATE TABLE projects (
        id TEXT PRIMARY KEY,
        session TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        kind TEXT NOT NULL CHECK (kind IN ('live', 'simulator')),
        name TEXT NOT NULL,
        created TEXT NOT NULL,
        updated TEXT NOT NULL,
        seq INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX projects_session ON projects(session);
    CREATE TABLE events (
        project TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        seq INTEGER NOT NULL,
        type TEXT NOT NULL,
        payload TEXT NOT NULL,
        created TEXT NOT NULL,
        PRIMARY KEY (project, seq)
    );
    CREATE TRIGGER events_append_only BEFORE UPDATE ON events
    BEGIN
        SELECT RAISE(ABORT, 'the event log is append-only');
    END;
    CREATE TABLE jobs (
        id TEXT PRIMARY KEY,
        session TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        project TEXT REFERENCES projects(id) ON DELETE CASCADE,
        kind TEXT NOT NULL,
        status TEXT NOT NULL,
        progress REAL NOT NULL DEFAULT 0,
        message TEXT NOT NULL DEFAULT '',
        result TEXT,
        error TEXT,
        created TEXT NOT NULL,
        finished TEXT
    );
    CREATE INDEX jobs_session ON jobs(session);
    CREATE TABLE usage (
        day TEXT NOT NULL,
        key TEXT NOT NULL,
        count INTEGER NOT NULL,
        PRIMARY KEY (day, key)
    );
    """,
)
SCHEMA_VERSION = len(MIGRATIONS)
LOCAL_SESSION = "local"  # the one session of a local (non-demo) app


def now() -> datetime:
    return datetime.now(UTC)


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds")


def _parse(text: str) -> datetime:
    return datetime.fromisoformat(text)


def new_id(nbytes: int = 12) -> str:
    """An unguessable URL-safe id."""
    return secrets.token_urlsafe(nbytes)


class ConflictError(RuntimeError):
    """The project changed since it was read (another event was appended first)."""


@dataclass(frozen=True)
class SessionRow:
    id: str
    created: datetime
    last_seen: datetime
    demo: bool


@dataclass(frozen=True)
class ProjectRow:
    id: str
    session: str
    kind: ProjectKind
    name: str
    created: datetime
    updated: datetime
    seq: int


@dataclass(frozen=True)
class EventRow:
    project: str
    seq: int
    type: str
    payload: dict[str, Any]
    created: datetime


@dataclass(frozen=True)
class JobRow:
    id: str
    session: str
    project: str | None
    kind: str
    status: JobStatus
    progress: float
    message: str
    result: dict[str, Any] | None
    error: dict[str, Any] | None
    created: datetime
    finished: datetime | None


class Store:
    """The application's SQLite database at `path` (created and migrated on first use)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            # WAL with NORMAL sync: durable but for the last commits on a power loss (SQLite docs)
            connection.execute("PRAGMA synchronous = NORMAL")
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        """A write transaction under the store's lock."""
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except BaseException:
                connection.execute("ROLLBACK")
                raise
            connection.execute("COMMIT")

    def migrate(self) -> int:
        """Apply the migrations the database lacks; returns the schema version."""
        with self._lock, self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"{self.path} has schema version {version}, newer than {SCHEMA_VERSION}"
                )
            for target in range(version, SCHEMA_VERSION):
                connection.execute("BEGIN IMMEDIATE")
                try:
                    for statement in _statements(MIGRATIONS[target]):
                        connection.execute(statement)
                    connection.execute(f"PRAGMA user_version = {target + 1}")
                except BaseException:
                    connection.execute("ROLLBACK")
                    raise
                connection.execute("COMMIT")
            return SCHEMA_VERSION

    # ---- sessions

    def create_session(self, *, demo: bool, session_id: str | None = None) -> SessionRow:
        moment = _stamp(now())
        sid = session_id or new_id(18)
        with self._write() as db:
            db.execute(
                "INSERT INTO sessions (id, created, last_seen, demo) VALUES (?, ?, ?, ?)",
                (sid, moment, moment, int(demo)),
            )
        session = self.session(sid)
        assert session is not None
        return session

    def ensure_session(self, session_id: str, *, demo: bool) -> SessionRow:
        """The session `session_id`, created if missing (the local session)."""
        found = self.session(session_id)
        return found if found is not None else self.create_session(demo=demo, session_id=session_id)

    def session(self, session_id: str) -> SessionRow | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        return SessionRow(
            row["id"], _parse(row["created"]), _parse(row["last_seen"]), bool(row["demo"])
        )

    def touch(self, session_id: str) -> None:
        with self._write() as db:
            db.execute(
                "UPDATE sessions SET last_seen = ? WHERE id = ?", (_stamp(now()), session_id)
            )

    def expire(self, before: datetime) -> int:
        """Delete the demo sessions created before `before` with all their data; their number."""
        with self._write() as db:
            cursor = db.execute(
                "DELETE FROM sessions WHERE demo = 1 AND created < ?", (_stamp(before),)
            )
            return cursor.rowcount

    # ---- projects and events

    def create_project(
        self,
        session: str,
        kind: ProjectKind,
        name: str,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> ProjectRow:
        """A new project with its first event."""
        project_id = new_id()
        moment = _stamp(now())
        with self._write() as db:
            db.execute(
                "INSERT INTO projects (id, session, kind, name, created, updated, seq) "
                "VALUES (?, ?, ?, ?, ?, ?, 1)",
                (project_id, session, kind, name, moment, moment),
            )
            db.execute(
                "INSERT INTO events (project, seq, type, payload, created) VALUES (?, 1, ?, ?, ?)",
                (project_id, event_type, _dump(payload), moment),
            )
        project = self.project(session, project_id)
        assert project is not None
        return project

    def projects(self, session: str) -> list[ProjectRow]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM projects WHERE session = ? ORDER BY created, id", (session,)
            ).fetchall()
        return [_project(row) for row in rows]

    def count_projects(self, session: str) -> int:
        with self._connect() as db:
            row = db.execute("SELECT COUNT(*) FROM projects WHERE session = ?", (session,))
            return int(row.fetchone()[0])

    def project(self, session: str, project_id: str) -> ProjectRow | None:
        """The project if it belongs to `session`, else None (the same for a missing one)."""
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM projects WHERE id = ? AND session = ?", (project_id, session)
            ).fetchone()
        return None if row is None else _project(row)

    def append(
        self,
        session: str,
        project_id: str,
        event_type: str,
        payload: Mapping[str, Any],
        *,
        expected: int | None = None,
        name: str | None = None,
    ) -> int:
        """Append an event to the session's project; returns its sequence number. With
        `expected`, refuse (ConflictError) if the project's last event is another one."""
        moment = _stamp(now())
        with self._write() as db:
            row = db.execute(
                "SELECT seq FROM projects WHERE id = ? AND session = ?", (project_id, session)
            ).fetchone()
            if row is None:
                raise KeyError(project_id)
            seq = int(row["seq"])
            if expected is not None and seq != expected:
                raise ConflictError(f"project {project_id} is at event {seq}, not {expected}")
            db.execute(
                "INSERT INTO events (project, seq, type, payload, created) VALUES (?, ?, ?, ?, ?)",
                (project_id, seq + 1, event_type, _dump(payload), moment),
            )
            if name is None:
                db.execute(
                    "UPDATE projects SET seq = ?, updated = ? WHERE id = ?",
                    (seq + 1, moment, project_id),
                )
            else:
                db.execute(
                    "UPDATE projects SET seq = ?, updated = ?, name = ? WHERE id = ?",
                    (seq + 1, moment, name, project_id),
                )
            return seq + 1

    def events(self, session: str, project_id: str) -> list[EventRow]:
        """The session's project's events in order (none for another session's project)."""
        with self._connect() as db:
            rows = db.execute(
                "SELECT e.* FROM events e JOIN projects p ON p.id = e.project "
                "WHERE e.project = ? AND p.session = ? ORDER BY e.seq",
                (project_id, session),
            ).fetchall()
        return [
            EventRow(
                row["project"],
                row["seq"],
                row["type"],
                json.loads(row["payload"]),
                _parse(row["created"]),
            )
            for row in rows
        ]

    def delete_project(self, session: str, project_id: str) -> bool:
        with self._write() as db:
            cursor = db.execute(
                "DELETE FROM projects WHERE id = ? AND session = ?", (project_id, session)
            )
            return cursor.rowcount > 0

    # ---- jobs

    def create_job(self, session: str, project: str | None, kind: str) -> JobRow:
        job_id = new_id()
        with self._write() as db:
            db.execute(
                "INSERT INTO jobs (id, session, project, kind, status, created) "
                "VALUES (?, ?, ?, ?, 'queued', ?)",
                (job_id, session, project, kind, _stamp(now())),
            )
        job = self.job(session, job_id)
        assert job is not None
        return job

    def update_job(
        self,
        job_id: str,
        *,
        status: JobStatus | None = None,
        progress: float | None = None,
        message: str | None = None,
        result: Mapping[str, Any] | None = None,
        error: Mapping[str, Any] | None = None,
    ) -> None:
        fields: dict[str, Any] = {}
        if status is not None:
            fields["status"] = status
            if status in ("done", "failed"):
                fields["finished"] = _stamp(now())
        if progress is not None:
            fields["progress"] = min(1.0, max(0.0, progress))
        if message is not None:
            fields["message"] = message
        if result is not None:
            fields["result"] = _dump(result)
        if error is not None:
            fields["error"] = _dump(error)
        if not fields:
            return
        assignments = ", ".join(f"{name} = ?" for name in fields)
        with self._write() as db:
            db.execute(f"UPDATE jobs SET {assignments} WHERE id = ?", (*fields.values(), job_id))

    def job(self, session: str, job_id: str) -> JobRow | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM jobs WHERE id = ? AND session = ?", (job_id, session)
            ).fetchone()
        return None if row is None else _job(row)

    def active_jobs(self, session: str) -> int:
        """Jobs of the session that are queued or running."""
        with self._connect() as db:
            row = db.execute(
                "SELECT COUNT(*) FROM jobs WHERE session = ? AND status IN ('queued', 'running')",
                (session,),
            )
            return int(row.fetchone()[0])

    def fail_unfinished_jobs(self) -> int:
        """Mark the jobs a previous server process left queued or running as failed."""
        with self._write() as db:
            cursor = db.execute(
                "UPDATE jobs SET status = 'failed', error = ?, finished = ? "
                "WHERE status IN ('queued', 'running')",
                (_dump({"code": "internal_error", "params": {}}), _stamp(now())),
            )
            return cursor.rowcount

    # ---- usage counters

    def use(self, key: str, limit: int | None, day: str | None = None) -> bool:
        """Count one use of `key` today; False (and not counted) if `limit` uses were made."""
        today = day or now().date().isoformat()
        with self._write() as db:
            row = db.execute(
                "SELECT count FROM usage WHERE day = ? AND key = ?", (today, key)
            ).fetchone()
            count = 0 if row is None else int(row["count"])
            if limit is not None and count >= limit:
                return False
            db.execute(
                "INSERT INTO usage (day, key, count) VALUES (?, ?, 1) "
                "ON CONFLICT(day, key) DO UPDATE SET count = count + 1",
                (today, key),
            )
            return True


def _statements(script: str) -> list[str]:
    """The statements of a migration script; a trigger body keeps its inner semicolons."""
    statements: list[str] = []
    current: list[str] = []
    in_trigger = False
    for line in script.strip().splitlines():
        current.append(line)
        stripped = line.strip().upper()
        if stripped.startswith("CREATE TRIGGER"):
            in_trigger = True
        if in_trigger:
            if stripped == "END;":
                statements.append("\n".join(current))
                current, in_trigger = [], False
        elif stripped.endswith(";"):
            statements.append("\n".join(current))
            current = []
    if "".join(current).strip():
        statements.append("\n".join(current))
    return statements


def _dump(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _project(row: sqlite3.Row) -> ProjectRow:
    return ProjectRow(
        row["id"],
        row["session"],
        row["kind"],
        row["name"],
        _parse(row["created"]),
        _parse(row["updated"]),
        int(row["seq"]),
    )


def _job(row: sqlite3.Row) -> JobRow:
    return JobRow(
        row["id"],
        row["session"],
        row["project"],
        row["kind"],
        row["status"],
        float(row["progress"]),
        row["message"],
        None if row["result"] is None else json.loads(row["result"]),
        None if row["error"] is None else json.loads(row["error"]),
        _parse(row["created"]),
        None if row["finished"] is None else _parse(row["finished"]),
    )
