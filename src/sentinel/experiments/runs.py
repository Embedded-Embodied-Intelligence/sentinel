"""Run identity, seed derivation and manifest data shared by experiment runners.

Implements the conventions of the `experiment-run` skill: config hash over the canonical
config plus `--limit`, run ids `<UTC yyyymmdd-HHMMSS>-<hash[:8]>`, never-reused output
directories (suffix `-smoke` for smoke runs) and the provenance fields of `manifest.json`.
"""

import hashlib
import json
import os
import platform
import socket
import subprocess
import sys
import tomllib
from collections.abc import Mapping
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

import numpy as np

KEY_PACKAGES = ("numpy", "ortools", "pydantic", "psplib", "matplotlib")


def load_toml(path: Path) -> dict[str, Any]:
    """Parse a TOML config file."""
    with path.open("rb") as handle:
        return tomllib.load(handle)


def config_hash(config: Mapping[str, Any], limit: int | None) -> str:
    """SHA-256 of the canonical JSON (sorted keys) of the config together with `--limit`."""
    canonical = json.dumps(
        {"config": config, "limit": limit}, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def make_run_id(start: datetime, digest: str) -> str:
    """Run id `<UTC yyyymmdd-HHMMSS>-<config hash[:8]>`."""
    return f"{start.astimezone(UTC):%Y%m%d-%H%M%S}-{digest[:8]}"


def create_run_dir(out: Path, run_id: str, *, smoke: bool) -> Path:
    """Create `<out>/<run_id>`, with suffix `-smoke` for smoke runs; an existing one is an error."""
    path = out / (f"{run_id}-smoke" if smoke else run_id)
    path.mkdir(parents=True, exist_ok=False)
    return path


def derive_seed(base_seed: int, *keys: str) -> int:
    """Stable 31-bit seed for (base seed, keys): SeedSequence entropy from a SHA-256 of the keys.

    Independent of run order and `--limit`; 31 bits fit both NumPy and CP-SAT (int32) seeds.
    """
    digest = hashlib.sha256("/".join(keys).encode("utf-8")).digest()
    words = [int.from_bytes(digest[i : i + 4], "little") for i in range(0, len(digest), 4)]
    state = np.random.SeedSequence([base_seed, *words]).generate_state(1)
    return int(state[0]) >> 1


def git_state() -> dict[str, Any]:
    """Current commit and whether the working tree has uncommitted changes (None without git)."""
    try:
        commit = _run(["git", "rev-parse", "HEAD"])
        changes = _run(["git", "status", "--porcelain"])
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}
    return {"commit": commit, "dirty": bool(changes)}


def environment() -> dict[str, Any]:
    """Python and key package versions, platform, CPU model, logical core count and hostname."""
    return {
        "python": platform.python_version(),
        "packages": {name: _package_version(name) for name in KEY_PACKAGES},
        "platform": platform.platform(),
        "cpu": cpu_model(),
        "cpu_count": os.cpu_count(),
        "hostname": socket.gethostname(),
    }


def cpu_model() -> str:
    """CPU model name from /proc/cpuinfo (Linux) or sysctl (macOS), else `platform.processor`."""
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("model name"):
                return line.partition(":")[2].strip()
    if sys.platform == "darwin":
        try:
            return _run(["sysctl", "-n", "machdep.cpu.brand_string"])
        except (OSError, subprocess.CalledProcessError):
            pass
    return platform.processor() or "unknown"


def utc_iso(moment: datetime) -> str:
    """ISO 8601 UTC timestamp with second precision, e.g. `2026-10-20T12:00:00+00:00`."""
    return moment.astimezone(UTC).isoformat(timespec="seconds")


def write_json(path: Path, data: Mapping[str, Any]) -> None:
    """Write indented UTF-8 JSON with a trailing newline."""
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _run(command: list[str]) -> str:
    return subprocess.run(command, capture_output=True, text=True, check=True).stdout.strip()


def _package_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None
