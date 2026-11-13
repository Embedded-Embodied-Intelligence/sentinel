"""Download the open sources of the evidence registry, extract their plain text and check quotes.

Usage:
  uv run python scripts/fetch_evidence.py [--root data/evidence] [--only FILE ...] [--force]
  uv run python scripts/fetch_evidence.py --check            # every quote against its source
  uv run python scripts/fetch_evidence.py --reextract        # the text again, no download
  uv run python scripts/fetch_evidence.py --update-registry  # write SHA-256 and date of checked
                                                             # verified items into the registry

Sources (docs/research/evidence/registry.json, "sources") are saved to <root>/raw/<file>, their
text to <root>/text/<file>.txt and every download is recorded in <root>/MANIFEST.json (URL, time,
size, SHA-256). PDF text comes from pdfminer.six, a development dependency (ADR-0036); HTML,
XHTML and XML text from the standard library (sentinel.evidence.text). The sources are never
committed (CLAUDE.md, invariant 5). A quote is verified when it occurs in the text after the
normalisation of sentinel.evidence.verify only.

A "manual" source (a paywalled article) is not downloaded: the owner saves the PDF from the
university library as <root>/raw/<file> and runs this script again, which extracts and records
it like any other; its item can then get a quote found in that text.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import ssl
import sys
import time
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sentinel.evidence import REGISTRY_PATH, Registry, Source, load_registry, quote_occurs
from sentinel.evidence.text import markup_text
from sentinel.evidence.verify import source_readings

USER_AGENT = (
    "Mozilla/5.0 (compatible; sentinel-fetch-evidence/0.1; "
    "+https://github.com/Embedded-Embodied-Intelligence/sentinel)"
)
TIMEOUT_S = 90
RETRIES = 2
PAUSE_S = 1.0  # between downloads, to be polite to arXiv and the publishers

Manifest = dict[str, Any]


def utc_now() -> str:
    """Current UTC time in ISO 8601 with seconds precision."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def tls_context() -> ssl.SSLContext:
    """Certificates checked against Mozilla's CA bundle (certifi, which the development tools
    bring) when present: some servers (api.sejm.gov.pl) chain to a root the system file lacks."""
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def download(source: Source) -> bytes:
    """GET the source's URL with its headers, retrying up to RETRIES times."""
    headers = {"User-Agent": USER_AGENT, **source.headers}
    request = urllib.request.Request(source.url, headers=headers)
    context = tls_context()
    for attempt in range(RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S, context=context) as response:
                data: bytes = response.read()
                return data
        except (OSError, http.client.HTTPException) as exc:  # URLError is an OSError
            if attempt == RETRIES:
                raise RuntimeError(f"download failed: {source.url}: {exc}") from exc
            wait_s = 2 ** (attempt + 1)
            print(f"  retry {attempt + 1}/{RETRIES} in {wait_s} s: {exc}", file=sys.stderr)
            time.sleep(wait_s)
    raise AssertionError("unreachable")


def pdf_text(path: Path) -> str:
    """Plain text of a PDF by pdfminer.six (a development dependency, imported only here)."""
    from pdfminer.high_level import extract_text

    text: str = extract_text(str(path))
    return text


def extract(source: Source, raw: Path) -> str:
    """Plain text of a downloaded source."""
    if source.format == "pdf":
        if not raw.read_bytes().startswith(b"%PDF"):
            raise RuntimeError(f"{source.file}: the download is not a PDF")
        return pdf_text(raw)
    return markup_text(raw.read_bytes().decode("utf-8", errors="replace"))


def reextract(registry: Registry, root: Path, only: set[str]) -> None:
    """Extract the text of the downloaded sources again, without downloading."""
    for source in registry.sources:
        raw = root / "raw" / source.file
        if (only and source.file not in only) or not raw.exists():
            continue
        (root / "text" / f"{source.file}.txt").write_text(extract(source, raw), encoding="utf-8")
        print(f"extracted {source.file}")


def fetch(registry: Registry, root: Path, only: set[str], force: bool) -> Manifest:
    """Download and extract every selected source; return the updated manifest."""
    (root / "raw").mkdir(parents=True, exist_ok=True)
    (root / "text").mkdir(parents=True, exist_ok=True)
    manifest_path = root / "MANIFEST.json"
    manifest: Manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    files = manifest.setdefault("files", {})
    failures = []
    for source in registry.sources:
        if only and source.file not in only:
            continue
        raw = root / "raw" / source.file
        text = root / "text" / f"{source.file}.txt"
        if source.manual and not raw.exists():
            print(f"missing   {source.file} (the owner supplies it: {source.title}, {source.url})")
            continue
        if raw.exists() and text.exists() and not force:
            print(f"kept      {source.file}")
            continue
        print(f"{'reading' if source.manual else 'fetching':<9} {source.file} <- {source.url}")
        try:
            data = raw.read_bytes() if source.manual else download(source)
            raw.write_bytes(data)
            text.write_text(extract(source, raw), encoding="utf-8")
        except (RuntimeError, ValueError) as exc:
            failures.append(source.file)
            print(f"  FAILED: {exc}", file=sys.stderr)
            continue
        files[source.file] = {
            "url": source.url,
            "fetched_at": utc_now(),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "extractor": "pdfminer.six" if source.format == "pdf" else "sentinel.evidence.text",
            "supplied_by_owner": source.manual,
        }
        if not source.manual:
            time.sleep(PAUSE_S)
    manifest["updated_at"] = utc_now()
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    if failures:
        print(f"{len(failures)} source(s) failed: {', '.join(failures)}", file=sys.stderr)
    return manifest


def check(registry: Registry, root: Path) -> dict[str, list[str]]:
    """Check every verified item's quotes against its source text; return the problems per id
    and print one line per item."""
    manifest_path = root / "MANIFEST.json"
    files = json.loads(manifest_path.read_text())["files"] if manifest_path.exists() else {}
    readings: dict[str, tuple[str, str]] = {}
    problems: dict[str, list[str]] = {}
    for item in registry.items:
        check = item.verification
        if check.status != "verified" or item.kind == "own":
            print(f"{item.id}  {check.status:<12} {item.kind}")
            continue
        issues = []
        for quote, name in ((item.quote, check.source_file), (item.quote_pl, check.source_file_pl)):
            if quote is None or name is None:
                continue
            path = root / "text" / f"{name}.txt"
            if not path.exists():
                issues.append(f"{name} not fetched")
                continue
            if name not in readings:
                readings[name] = source_readings(path.read_text(encoding="utf-8"))
            if not quote_occurs(quote, readings[name]):
                issues.append(f"quote not found in {name}")
        for name, digest in (
            (check.source_file, check.sha256),
            (check.source_file_pl, check.sha256_pl),
        ):
            fetched = files.get(name, {}).get("sha256") if name else None
            if fetched is not None and fetched != digest:
                issues.append(f"{name} changed since the check (SHA-256 {fetched[:12]})")
        problems[item.id] = issues
        print(f"{item.id}  {'ok' if not issues else 'PROBLEM':<12} {'; '.join(issues)}")
    return problems


def update_registry(registry_path: Path, root: Path) -> None:
    """Write the fetched SHA-256 and today's date into every verified item whose quotes occur in
    its source text; items that fail are left as they are."""
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    files = json.loads((root / "MANIFEST.json").read_text())["files"]
    today = date.today().isoformat()
    for item in data["items"]:
        check = item["verification"]
        if check["status"] != "verified" or item["kind"] == "own":
            continue
        pairs = [("quote", "source_file", "sha256"), ("quote_pl", "source_file_pl", "sha256_pl")]
        ok = True
        for quote_key, file_key, _ in pairs:
            quote, name = item.get(quote_key), check.get(file_key)
            if quote is None or name is None:
                continue
            path = root / "text" / f"{name}.txt"
            ok = ok and path.exists() and quote_occurs(quote, path.read_text(encoding="utf-8"))
        if not ok:
            print(f"{item['id']}: not updated (a quote does not occur in its source)")
            continue
        for _, file_key, sha_key in pairs:
            name = check.get(file_key)
            if name is not None:
                check[sha_key] = files[name]["sha256"]
        check["checked_on"] = today
    registry_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8")
    load_registry(registry_path)  # still valid


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path("data/evidence"))
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    parser.add_argument("--only", nargs="*", default=[], help="source files to fetch")
    parser.add_argument("--force", action="store_true", help="download again")
    parser.add_argument("--check", action="store_true", help="only check the quotes")
    parser.add_argument("--reextract", action="store_true", help="extract text, no download")
    parser.add_argument("--update-registry", action="store_true")
    args = parser.parse_args(argv)
    registry = load_registry(args.registry)
    if args.update_registry:
        update_registry(args.registry, args.root)
        return 0
    if args.reextract:
        reextract(registry, args.root, set(args.only))
    elif not args.check:
        fetch(registry, args.root, set(args.only), args.force)
    problems = check(registry, args.root)
    failing = sorted(item for item, issues in problems.items() if issues)
    print(f"{len(problems) - len(failing)} of {len(problems)} verified items pass")
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main())
