"""The release package (WP8): `git archive` of HEAD plus RELEASE.md and the deliverables, built
only from a clean tree, without data, secrets or caches other than committed replay bundles."""

import subprocess
import zipfile
from pathlib import Path

import pytest

from sentinel import cli
from sentinel.release import ReleaseError, build, forbidden

TRACKED = {
    "pyproject.toml": '[project]\nname = "sentinel"\nversion = "1.0.0"\n',
    "README.md": "# Sentinel\n",
    ".gitignore": "/data/\n.env\n.env.*\n!.env.example\n/dist/\n__pycache__/\n",
    ".env.example": "# names only\nGROQ_API_KEY=\nOLLAMA_HOST=http://127.0.0.1:11434\n",
    "src/sentinel/core.py": "X = 1\n",
    "results/wp6/run1/llm_cache.jsonl.gz": "bundle\n",
    "results/wp6/run1/messages.jsonl": "{}\n",
    "docs/dashboard/j30_example.html": "<!doctype html>\n",
}
IGNORED = {
    "data/psplib/j30/j301_1.sm": "instance\n",
    "data/llm_cache/rq5/ollama.jsonl": "{}\n",
    ".env": "GROQ_API_KEY=not-a-real-key\n",  # pragma: allowlist secret
    "src/sentinel/__pycache__/core.cpython-312.pyc": "bytecode\n",
}


def git(repo: Path, *args: str) -> None:
    settings = ["-c", "user.name=Test", "-c", "user.email=test@invalid"]
    settings += ["-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null"]
    subprocess.run(["git", *settings, *args], cwd=repo, check=True, capture_output=True)


def put(repo: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A committed checkout with ignored data, a secret file and caches next to it."""
    root = tmp_path / "repo"
    root.mkdir()
    put(root, TRACKED)
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init")
    put(root, IGNORED)
    return root


def names(path: Path) -> set[str]:
    with zipfile.ZipFile(path) as archive:
        return {n for n in archive.namelist() if not n.endswith("/")}


def test_a_release_holds_the_tracked_files_its_notes_and_the_deliverables(
    repo: Path, tmp_path: Path
) -> None:
    report = tmp_path / "report.pdf"
    report.write_bytes(b"%PDF-1.7\n")
    release = build("1.0.0", repo=repo, includes=[report])
    assert release.path == repo / "dist" / "sentinel-1.0.0.zip"
    prefix = "sentinel-1.0.0/"
    expected = {*TRACKED, "RELEASE.md", "docs/deliverables/report.pdf"}
    assert names(release.path) == {prefix + name for name in expected}
    assert all(forbidden(name.removeprefix(prefix)) is None for name in names(release.path))
    with zipfile.ZipFile(release.path) as archive:
        notes = archive.read(prefix + "RELEASE.md").decode("utf-8")
        assert archive.read(prefix + "docs/deliverables/report.pdf") == b"%PDF-1.7\n"
    assert release.commit in notes and "`docs/dashboard/j30_example.html`" in notes
    assert "`docs/deliverables/report.pdf`" in notes and "reproduce --check" in notes
    assert release.tag_command().startswith('git tag -a v1.0.0 -m "Sentinel 1.0.0" ')
    first = release.path.read_bytes()
    assert build("1.0.0", repo=repo, includes=[report]).path.read_bytes() == first


def test_a_release_refuses_a_dirty_tree_or_another_version(repo: Path) -> None:
    (repo / "README.md").write_text("# Changed\n", encoding="utf-8")
    with pytest.raises(ReleaseError, match="not clean"):
        build("1.0.0", repo=repo)
    git(repo, "checkout", "--", "README.md")
    (repo / "notes.txt").write_text("untracked\n", encoding="utf-8")
    with pytest.raises(ReleaseError, match="not clean"):
        build("1.0.0", repo=repo)
    (repo / "notes.txt").unlink()
    with pytest.raises(ReleaseError, match=r"differs from the project version 1\.0\.0"):
        build("1.0.1", repo=repo)
    with pytest.raises(ReleaseError, match="not a version"):
        build("latest", repo=repo)
    with pytest.raises(ReleaseError, match="not a file"):
        build("1.0.0", repo=repo, includes=[repo / "missing.pdf"])
    assert not (repo / "dist").exists()


@pytest.mark.parametrize(
    ("files", "reason"),
    [
        ({"data/psplib/j30/j301_1.sm": "x\n"}, "benchmark data"),
        ({".env.local": "KEY=x\n"}, "secret file"),
        ({"results/wp6/run1/llm_cache.jsonl": "{}\n"}, "LLM cache"),
        ({"tools/__pycache__/a.pyc": "x\n"}, "cache directory"),
        ({".env.example": "GROQ_API_KEY=gsk_value\n"}, "GROQ_API_KEY has a value"),
    ],
)
def test_a_release_refuses_data_secrets_and_caches(
    repo: Path, files: dict[str, str], reason: str
) -> None:
    put(repo, files)
    git(repo, "add", "-f", *files)
    git(repo, "commit", "-q", "-m", "add")
    with pytest.raises(ReleaseError, match=reason):
        build("1.0.0", repo=repo)


def test_forbidden_paths() -> None:
    assert forbidden("results/wp6/20261023-215350-f5aad526/llm_cache.jsonl.gz") is None
    assert forbidden("results/wp6/20261023-220452-f8a335f4/messages.jsonl") is None
    assert forbidden(".env.example") is None and forbidden("src/sentinel/llm/cache.py") is None
    assert forbidden("data/derived/baselines/x.json") is not None
    assert forbidden(".env") is not None and forbidden("docs/.env.prod") is not None
    assert forbidden("data/llm_cache/rq5/ollama.jsonl") is not None
    assert forbidden("llm_cache.jsonl.gz") is not None


def test_the_command_builds_and_prints_the_tag_command_without_tagging(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(repo)
    assert cli.main(["release", "--version", "1.0.0"]) == 0
    out = capsys.readouterr().out
    assert "sentinel-1.0.0.zip" in out and "Not tagged or published" in out
    assert "git tag -a v1.0.0" in out
    tags = subprocess.run(["git", "tag"], cwd=repo, check=True, capture_output=True, text=True)
    assert tags.stdout == ""
    assert cli.main(["release", "--version", "2.0.0"]) == 2
    assert "differs from the project version" in capsys.readouterr().err
