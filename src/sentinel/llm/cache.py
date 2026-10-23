"""Record/replay cache of LLM replies (CLAUDE.md invariant 3; ADR-0018).

Entries are JSON lines keyed by the SHA-256 of their `Request`. Modes: `record` calls the
backend and stores the reply even when the key is cached, `replay` answers from the cache only
(a miss raises `CacheMiss`), `auto` calls the backend on a miss and stores the reply. The
working cache lives under `data/llm_cache/` (gitignored); a run's replay bundle is a gzip file
of exactly the entries it used, from which the run can be repeated without any backend.
"""

import fcntl
import gzip
import io
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue, ValidationError

from sentinel.llm.core import Reply, Request, sha256_json

CacheMode = Literal["record", "replay", "auto"]
CACHE_MODES: tuple[CacheMode, ...] = ("record", "replay", "auto")
DEFAULT_CACHE_DIR = Path("data/llm_cache")


class CacheEntry(BaseModel):
    """A stored reply with its request: messages, schema name and digest, parameters."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    backend: str
    model: str
    digest: str | None
    request: dict[str, JsonValue]
    reply: Reply
    recorded_utc: str


def make_entry(request: Request, reply: Reply, now: datetime | None = None) -> CacheEntry:
    """The cache entry of a request and its reply; the schema is kept as its SHA-256."""
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    return CacheEntry(
        key=request.key,
        backend=request.backend,
        model=request.model,
        digest=request.digest,
        request={
            "messages": [message.model_dump(mode="json") for message in request.messages],
            "schema_name": request.schema_name,
            "schema_sha256": sha256_json(request.json_schema),
            "temperature": request.temperature,
            "seed": request.seed,
            "max_tokens": request.max_tokens,
            "options": request.options,
        },
        reply=reply,
        recorded_utc=moment.isoformat(timespec="seconds"),
    )


class LlmCache:
    """Replies by request key in a JSON-lines file; a `.gz` file is read-only (a bundle).

    The last line of a key wins. A cut-off last line (a crash while writing) is skipped; any
    other bad line is an error. Appends hold an exclusive `flock`, so processes can share a
    file. `used` collects the entries looked up or stored, in first-use order, for a bundle.
    """

    def __init__(self, path: Path, *, readonly: bool = False) -> None:
        self.path = path
        self.readonly = readonly or path.suffix == ".gz"
        self.skipped_lines = 0
        self.used: dict[str, CacheEntry] = {}
        self._entries: dict[str, CacheEntry] = {}
        if path.is_file():
            self._load()
        elif self.readonly:
            raise FileNotFoundError(f"cache file {path} not found")

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, key: object) -> bool:
        return key in self._entries

    def get(self, key: str) -> Reply | None:
        """The stored reply of `key`, or None."""
        entry = self._entries.get(key)
        if entry is None:
            return None
        self.used.setdefault(key, entry)
        return entry.reply

    def entry(self, key: str) -> CacheEntry | None:
        """The stored entry of `key` without marking it used."""
        return self._entries.get(key)

    def entries(self) -> list[CacheEntry]:
        """Every stored entry, last version per key, in file order of first appearance."""
        return list(self._entries.values())

    def put(self, request: Request, reply: Reply) -> CacheEntry:
        """Append the reply of `request` and return its entry."""
        if self.readonly:
            raise PermissionError(f"cache file {self.path} is read-only")
        entry = make_entry(request, reply)
        line = entry.model_dump_json() + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                handle.write(line)
                handle.flush()
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
        self._entries[entry.key] = entry
        self.used[entry.key] = entry
        return entry

    def _load(self) -> None:
        if self.path.suffix == ".gz":
            with gzip.open(self.path, "rt", encoding="utf-8") as handle:
                lines = handle.read().splitlines()
        else:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                entry = CacheEntry.model_validate(json.loads(line))
            except (json.JSONDecodeError, ValidationError) as exc:
                if number == len(lines):
                    self.skipped_lines += 1
                    continue
                raise ValueError(f"{self.path}:{number}: corrupt cache entry ({exc})") from None
            self._entries[entry.key] = entry


def write_bundle(path: Path, entries: Iterable[CacheEntry]) -> int:
    """Write entries as a gzip JSON-lines bundle without a timestamp in its header (same entries,
    same bytes); returns the file size in bytes."""
    text = "".join(entry.model_dump_json() + "\n" for entry in entries)
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, mtime=0) as handle:
        handle.write(text.encode("utf-8"))
    path.write_bytes(buffer.getvalue())
    return path.stat().st_size
