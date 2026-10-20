"""Download PSPLIB single-mode instances and reference solutions (stdlib only).

Usage: uv run python scripts/fetch_psplib.py --sets j30 j60 [--root data/psplib] [--force]

Instances are extracted to <root>/<set>/*.sm, solutions saved to
<root>/solutions/<set>_<type>.sm and every download is recorded in <root>/MANIFEST.json.
Existing files are kept unless --force is given. Source: Kolisch & Sprecher 1997 (PSPLIB).
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import io
import json
import shutil
import sys
import tempfile
import time
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

BASE_URL = "https://www.om-db.wi.tum.de/psplib"
DATASET_URL = BASE_URL + "/download_dataset.php?set={set}&mode=sm&format=zip"
SOLUTION_URL = BASE_URL + "/download_solution.php?set={set}&mode=sm&type={type}"
# Solution types verified to exist per set (opt = proven optima, hrs = best known upper
# bounds from heuristics, lb = lower bounds).
SOLUTION_TYPES: dict[str, tuple[str, ...]] = {"j30": ("opt", "hrs"), "j60": ("hrs", "lb")}
USER_AGENT = (
    "sentinel-fetch-psplib/0.1 (+https://github.com/Embedded-Embodied-Intelligence/sentinel)"
)
TIMEOUT_S = 60
RETRIES = 3

Manifest = dict[str, Any]


def utc_now() -> str:
    """Current UTC time in ISO 8601 with seconds precision."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def download(url: str) -> bytes:
    """GET url with a User-Agent header and a timeout, retrying up to RETRIES times."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
                data: bytes = response.read()
                return data
        except (OSError, http.client.HTTPException) as exc:  # URLError is an OSError
            if attempt == RETRIES:
                raise RuntimeError(f"download failed after {attempt + 1} attempts: {url}") from exc
            wait_s = 2**attempt
            print(f"  retry {attempt + 1}/{RETRIES} in {wait_s} s: {exc}", file=sys.stderr)
            time.sleep(wait_s)
    raise AssertionError("unreachable")


def extract_sm_files(archive: zipfile.ZipFile, dest: Path) -> list[str]:
    """Extract every *.sm member (flattened to its base name) into dest; return sorted names."""
    names: list[str] = []
    for member in archive.infolist():
        name = PurePosixPath(member.filename).name  # base name only: no path traversal
        if member.is_dir() or not name.lower().endswith(".sm"):
            continue
        if name in names:
            raise RuntimeError(f"archive contains {name} twice")
        (dest / name).write_bytes(archive.read(member))
        names.append(name)
    return sorted(names)


def content_sha256(directory: Path) -> str:
    """SHA-256 over (name, content) of all *.sm files, independent of archive metadata."""
    digest = hashlib.sha256()
    for path in sorted(directory.glob("*.sm")):
        digest.update(path.name.encode())
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def fetch_instances(set_name: str, root: Path, force: bool, manifest: Manifest) -> None:
    """Download and extract the instance archive of one set unless it is already present."""
    target = root / set_name
    url = DATASET_URL.format(set=set_name)
    n_present = len(list(target.glob("*.sm"))) if target.is_dir() else 0
    if n_present and not force:
        print(f"{set_name}: {n_present} instances present, skipped (use --force to refresh)")
        manifest["instances"].setdefault(  # present on disk but not recorded: describe it
            set_name,
            {
                "url": url,
                "downloaded_utc": None,
                "content_sha256": content_sha256(target),
                "n_files": n_present,
                "dir": set_name,
            },
        )
        return
    data = download(url)
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise RuntimeError(f"{url} did not return a zip archive") from exc
    staging = Path(tempfile.mkdtemp(prefix=f".{set_name}-", dir=root))
    try:
        names = extract_sm_files(archive, staging)
        if not names:
            raise RuntimeError(f"{url}: archive contains no .sm files")
        if target.exists():
            shutil.rmtree(target)
        staging.rename(target)  # atomic on the same file system: no half-extracted set
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    manifest["instances"][set_name] = {
        "url": url,
        "downloaded_utc": utc_now(),
        "archive_bytes": len(data),
        "archive_sha256": hashlib.sha256(data).hexdigest(),
        "content_sha256": content_sha256(target),
        "n_files": len(names),
        "dir": set_name,
    }
    print(f"{set_name}: {len(names)} instances extracted ({len(data) / 1024:.0f} KiB archive)")


def solution_record(url: str, data: bytes, downloaded_utc: str | None, name: str) -> Manifest:
    """Manifest entry of one solution file."""
    return {
        "url": url,
        "downloaded_utc": downloaded_utc,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "n_lines": len(data.splitlines()),
        "path": f"solutions/{name}",
    }


def fetch_solution(set_name: str, kind: str, root: Path, force: bool, manifest: Manifest) -> None:
    """Download one PSPLIB solution file unless it is already present."""
    target = root / "solutions" / f"{set_name}_{kind}.sm"
    url = SOLUTION_URL.format(set=set_name, type=kind)
    key = f"{set_name}_{kind}"
    if target.is_file() and not force:
        print(f"{target.name}: present, skipped")
        manifest["solutions"].setdefault(
            key, solution_record(url, target.read_bytes(), None, target.name)
        )
        return
    data = download(url)
    head = data.lstrip()[:200].lower()
    if not data.strip() or head.startswith(b"<") or b"<html" in head:
        raise RuntimeError(f"{url} returned no solution data (empty or HTML)")
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    partial.write_bytes(data)
    partial.replace(target)  # atomic: never a truncated solution file
    manifest["solutions"][key] = solution_record(url, data, utc_now(), target.name)
    print(f"{target.name}: saved ({len(data) / 1024:.0f} KiB)")


def load_manifest(path: Path) -> Manifest:
    """Read an existing manifest or start an empty one."""
    if path.is_file():
        manifest: Manifest = json.loads(path.read_text(encoding="utf-8"))
    else:
        manifest = {"source": "PSPLIB (Kolisch & Sprecher 1997), " + BASE_URL}
    manifest.setdefault("instances", {})
    manifest.setdefault("solutions", {})
    return manifest


def main(argv: list[str] | None = None) -> int:
    """Fetch the requested sets; exit status 1 on any download or format error."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sets", nargs="+", required=True, choices=sorted(SOLUTION_TYPES))
    parser.add_argument("--root", type=Path, default=Path("data/psplib"))
    parser.add_argument("--force", action="store_true", help="re-download existing files")
    args = parser.parse_args(argv)

    root: Path = args.root
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "MANIFEST.json"
    manifest = load_manifest(manifest_path)
    before = json.dumps(manifest, sort_keys=True)
    try:
        for set_name in dict.fromkeys(args.sets):  # de-duplicate, keep order
            fetch_instances(set_name, root, args.force, manifest)
            for kind in SOLUTION_TYPES[set_name]:
                fetch_solution(set_name, kind, root, args.force, manifest)
    except RuntimeError as exc:
        cause = f" ({exc.__cause__})" if exc.__cause__ else ""
        print(f"error: {exc}{cause}", file=sys.stderr)
        return 1
    finally:  # record whatever was fetched, also after an error
        if json.dumps(manifest, sort_keys=True) != before or not manifest_path.is_file():
            manifest["updated_utc"] = utc_now()
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
