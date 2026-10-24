"""The release package (WP8): `sentinel release --version 1.0.0` writes
`dist/sentinel-<version>.zip` from `git archive` of HEAD (tracked files only: code, configs,
docs, committed results and replay bundles, `paper/generated/`, the example cockpits) with a
generated `RELEASE.md` at its root and, with `--include PATH`, extra files under
`docs/deliverables/` (the final PDFs).

It refuses a working tree with uncommitted changes or untracked files, a version other than the
project's (`pyproject.toml`), and any path that is benchmark data (`data/`), a secret file
(`.env*` other than `.env.example`, whose secret-like variables must be empty) or a cache other
than a committed replay bundle (`results/<wp>/<run>/llm_cache.jsonl.gz`); the archive is checked
again after it is written (CLAUDE.md invariants 4 and 5). Entries carry the commit's time, so
the same commit and files give the same zip. It never tags or publishes: it prints the tag
command for the owner.
"""

import re
import subprocess
import tempfile
import tomllib
import zipfile
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath

CACHE_DIRS = frozenset(
    {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv", "llm_cache"}
)
BUNDLE = re.compile(r"results/[^/]+/[^/]+/llm_cache\.jsonl\.gz")
SECRET_NAME = re.compile(r"[A-Z0-9_]*(KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*")
DELIVERABLES = PurePosixPath("docs/deliverables")
VERSION = re.compile(r"\d+\.\d+\.\d+(?:[-.+][0-9A-Za-z.-]+)?")


class ReleaseError(RuntimeError):
    """The release cannot be built from this checkout as asked."""


def forbidden(path: str) -> str | None:
    """Why a path must not be in the release (None if it may): benchmark data, a secret file or
    a cache other than a committed replay bundle."""
    parts = PurePosixPath(path).parts
    name = parts[-1] if parts else ""
    if parts and parts[0] == "data":
        return "benchmark data are downloaded, never redistributed (data/)"
    if name.startswith(".env") and name != ".env.example":
        return "a secret file (.env*)"
    if CACHE_DIRS.intersection(parts[:-1]):
        return "a cache directory"
    if name.startswith("llm_cache") and not BUNDLE.fullmatch(path):
        return "an LLM cache that is not a committed replay bundle"
    return None


def _git(repo: Path, *args: str) -> str:
    try:
        done = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise ReleaseError(f"git {' '.join(args)} failed: {detail.strip()}") from exc
    return done.stdout


def _secret_values(text: str) -> list[str]:
    """The secret-like variables of an env example that have a value."""
    found = []
    for line in text.splitlines():
        name, sep, value = line.strip().partition("=")
        if sep and not name.startswith("#") and SECRET_NAME.fullmatch(name) and value.strip():
            found.append(name)
    return found


@dataclass(frozen=True)
class Release:
    """A written release: the zip, its version and commit, the archived paths (without the
    prefix) and the paths it added (RELEASE.md and the deliverables)."""

    path: Path
    version: str
    commit: str
    files: tuple[str, ...]
    added: tuple[str, ...]

    @property
    def prefix(self) -> str:
        return f"sentinel-{self.version}/"

    def summary(self) -> list[tuple[str, int]]:
        """Files per top-level directory (or file at the root), in name order."""
        counts = Counter(PurePosixPath(p).parts[0] for p in (*self.files, *self.added))
        return sorted(counts.items())

    def tag_command(self) -> str:
        return (
            f'git tag -a v{self.version} -m "Sentinel {self.version}" {self.commit[:12]} && '
            f"git push origin v{self.version}"
        )


def build(
    version: str,
    *,
    repo: Path = Path("."),
    out_dir: Path | None = None,
    includes: Sequence[Path] = (),
) -> Release:
    """Write `<out_dir>/sentinel-<version>.zip` (default out_dir: `<repo>/dist`)."""
    if not VERSION.fullmatch(version):
        raise ReleaseError(f"--version {version!r} is not a version such as 1.0.0")
    changes = _git(repo, "status", "--porcelain")
    if changes.strip():
        shown = ", ".join(line[3:] for line in changes.splitlines()[:5])
        raise ReleaseError(f"the working tree is not clean ({shown}); commit or stash first")
    project = tomllib.loads(_git(repo, "show", "HEAD:pyproject.toml"))["project"]["version"]
    if project != version:
        raise ReleaseError(
            f"--version {version} differs from the project version {project} in pyproject.toml"
        )
    commit = _git(repo, "rev-parse", "HEAD").strip()
    stamp = datetime.fromisoformat(_git(repo, "show", "-s", "--format=%cI", "HEAD").strip())
    files = tuple(_git(repo, "ls-tree", "-r", "--name-only", "HEAD").splitlines())
    problems = [f"{path}: {reason}" for path in files if (reason := forbidden(path))]
    if ".env.example" in files:
        problems += [
            f".env.example: {name} has a value"
            for name in _secret_values(_git(repo, "show", "HEAD:.env.example"))
        ]
    extra: dict[str, Path] = {}
    for source in includes:
        target = (DELIVERABLES / source.name).as_posix()
        if not source.is_file():
            problems.append(f"--include {source}: not a file")
        elif target in files or target in extra:
            problems.append(f"--include {source}: {target} exists already")
        elif reason := forbidden(target):
            problems.append(f"--include {source}: {reason}")
        else:
            extra[target] = source
    if problems:
        raise ReleaseError("refused: " + "; ".join(problems))
    out = (repo / "dist" if out_dir is None else out_dir) / f"sentinel-{version}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    prefix = f"sentinel-{version}/"
    notes = release_notes(version, commit, stamp, files, tuple(extra))
    with tempfile.TemporaryDirectory(dir=out.parent) as scratch:
        draft = Path(scratch) / out.name
        target = str(draft.resolve())
        _git(repo, "archive", "--format=zip", f"--prefix={prefix}", "-o", target, "HEAD")
        when = stamp.timetuple()[:6]
        with zipfile.ZipFile(draft, "a", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in [("RELEASE.md", notes.encode("utf-8"))] + [
                (target, source.read_bytes()) for target, source in extra.items()
            ]:
                info = zipfile.ZipInfo(prefix + name, date_time=when)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, data)
        draft.replace(out)
    release = Release(out, version, commit, files, ("RELEASE.md", *extra))
    check(release)
    return release


def check(release: Release) -> None:
    """The written zip holds exactly the release's files under its prefix, none forbidden."""
    with zipfile.ZipFile(release.path) as archive:
        names = [n for n in archive.namelist() if not n.endswith("/")]
    outside = [n for n in names if not n.startswith(release.prefix)]
    inner = [n.removeprefix(release.prefix) for n in names]
    bad = [f"{n}: {reason}" for n in inner if (reason := forbidden(n))]
    if outside or bad or sorted(inner) != sorted((*release.files, *release.added)):
        raise ReleaseError(f"the archive does not match the release: {(outside + bad)[:3]}")


def release_notes(
    version: str,
    commit: str,
    stamp: datetime,
    files: Sequence[str],
    deliverables: Sequence[str],
) -> str:
    """RELEASE.md: what the package holds and how to install, test, check and read it."""
    counts = Counter(PurePosixPath(p).parts[0] for p in files)
    rows = "\n".join(f"| `{name}` | {n} |" for name, n in sorted(counts.items()))
    cockpits = sorted(p for p in files if p.startswith("docs/dashboard/") and p.endswith(".html"))
    cockpit_lines = "\n".join(f"- `{p}`" for p in cockpits) or "- (none)"
    delivered = (
        "\n".join(f"- `{p}`" for p in deliverables)
        if deliverables
        else "- none yet: the owner adds them with "
        f"`uv run sentinel release --version {version} --include <file.pdf>`"
    )
    return f"""# Sentinel {version}

Research prototype of a goal-driven project management agent (course project, Rzeszów
University of Technology, 2026). This package is `git archive` of commit `{commit}`
({stamp.date().isoformat()}) with this file added; it holds tracked files only.

## Contents

| Path | Files |
| --- | ---: |
{rows}

The formal model is `docs/spec/model.md`, the architecture `docs/spec/architecture.md`, the
decisions `docs/adr/`, the work package reports `docs/reports/`. Committed results are under
`results/` (raw outputs, summaries, LLM replay bundles), the generated tables, figures and
macros of the papers under `paper/generated/`. PSPLIB benchmark data are not included: they are
downloaded by a script and never redistributed. No secrets and no LLM caches other than the
committed replay bundles are included.

## Install

Requires [uv](https://docs.astral.sh/uv/); it installs Python 3.12 if missing.

```bash
cd sentinel-{version}
uv sync                                               # environment from uv.lock
uv run python scripts/fetch_psplib.py --sets j30 j60  # PSPLIB into data/psplib
```

## Test and check the results

```bash
uv run pytest -q                    # unit tests (about 75 s); data tests skip without data/
uv run pytest -q -m "data or slow"  # tests that need PSPLIB and the slow ones (about 10 min)
uv run sentinel reproduce --check   # every summary and paper/generated/ regenerated and compared
```

`reproduce --check` recomputes nothing and calls no LLM; `uv run sentinel reproduce --commands`
prints how to recompute each run (about 23 h on 4 cores).

## Example cockpits

One self-contained HTML page per simulated project (plan and execution, risk, the agent's
decisions); open them in a browser, no network needed:

{cockpit_lines}

Any other world: `uv run sentinel dashboard --set j30 --instance j301_1 --replication 0`.

## Deliverables

The article (English, LNCS) and the course report (Polish) are added under `docs/deliverables/`:

{delivered}
"""
