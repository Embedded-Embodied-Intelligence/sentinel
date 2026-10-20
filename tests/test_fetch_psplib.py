"""scripts/fetch_psplib.py without network: downloads are replaced by in-memory data."""

import importlib.util
import io
import json
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fetch_psplib.py"


@pytest.fixture
def fetch(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """The script as a module whose `download` serves fake archives and solution files."""
    spec = importlib.util.spec_from_file_location("fetch_psplib", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls: list[str] = []

    def fake_download(url: str) -> bytes:
        calls.append(url)
        if "download_dataset" in url:
            return make_zip({"j301_1.sm": b"a", "nested/j301_2.sm": b"b", "readme.txt": b"c"})
        return b"Par Inst Makespan\n1 1 43\n"

    monkeypatch.setattr(module, "download", fake_download)
    module.calls = calls  # type: ignore[attr-defined]
    return module


def make_zip(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def test_extract_flattens_and_filters(fetch: ModuleType, tmp_path: Path) -> None:
    archive = zipfile.ZipFile(io.BytesIO(make_zip({"a/x.sm": b"1", "../y.sm": b"2", "z.bas": b""})))
    assert fetch.extract_sm_files(archive, tmp_path) == ["x.sm", "y.sm"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["x.sm", "y.sm"]


def test_main_downloads_then_skips(fetch: ModuleType, tmp_path: Path) -> None:
    assert fetch.main(["--sets", "j30", "--root", str(tmp_path)]) == 0
    assert sorted(p.name for p in (tmp_path / "j30").iterdir()) == ["j301_1.sm", "j301_2.sm"]
    assert (tmp_path / "solutions" / "j30_opt.sm").read_bytes().endswith(b"1 1 43\n")
    assert (tmp_path / "solutions" / "j30_hrs.sm").is_file()
    manifest = json.loads((tmp_path / "MANIFEST.json").read_text())
    assert manifest["instances"]["j30"]["n_files"] == 2
    assert len(manifest["solutions"]["j30_opt"]["sha256"]) == 64
    assert len(fetch.calls) == 3
    assert not list(tmp_path.glob(".j30-*"))  # staging directory cleaned up

    assert fetch.main(["--sets", "j30", "--root", str(tmp_path)]) == 0
    assert len(fetch.calls) == 3  # idempotent: nothing downloaded again
    assert fetch.main(["--sets", "j30", "--root", str(tmp_path), "--force"]) == 0
    assert len(fetch.calls) == 6

    (tmp_path / "MANIFEST.json").unlink()  # lost manifest: rebuilt from disk, no download
    assert fetch.main(["--sets", "j30", "--root", str(tmp_path)]) == 0
    assert len(fetch.calls) == 6
    rebuilt = json.loads((tmp_path / "MANIFEST.json").read_text())
    assert rebuilt["instances"]["j30"]["n_files"] == 2
    assert rebuilt["solutions"]["j30_hrs"]["sha256"] == manifest["solutions"]["j30_hrs"]["sha256"]


def test_rejects_html_instead_of_solution(
    fetch: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fetch, "download", lambda url: b"<!DOCTYPE html><html></html>")
    manifest = fetch.load_manifest(tmp_path / "MANIFEST.json")
    with pytest.raises(RuntimeError, match="empty or HTML"):
        fetch.fetch_solution("j30", "opt", tmp_path, False, manifest)
    assert not (tmp_path / "solutions" / "j30_opt.sm").exists()
