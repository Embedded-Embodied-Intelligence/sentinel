"""Import isolation of the application (WP9a; ADR-0022): the research packages never import
`sentinel.app`, and only the application and the command line import the web stack."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPO_ROOT / "src" / "sentinel"
RESEARCH = ("simulation", "agent", "policies", "forecasting", "scheduling", "model", "data")
WEB = ("fastapi", "starlette", "uvicorn", "jinja2", "multipart", "python_multipart", "httpx")


def _modules(pattern: str) -> dict[str, set[str]]:
    """The modules matched by `pattern` in each source file, by path relative to the package."""
    imports = re.compile(pattern, re.MULTILINE)
    return {
        str(path.relative_to(SOURCE)): set(imports.findall(path.read_text(encoding="utf-8")))
        for path in sorted(SOURCE.rglob("*.py"))
    }


def test_research_packages_never_import_the_application() -> None:
    found = _modules(r"^\s*(?:from|import)\s+sentinel\.(app)\b")
    offenders = [path for path, names in found.items() if names and path.split("/")[0] in RESEARCH]
    assert offenders == []


def test_only_the_application_and_the_command_line_import_the_web_stack() -> None:
    pattern = r"^\s*(?:from|import)\s+(" + "|".join(WEB) + r")\b"
    found = _modules(pattern)
    offenders = [
        path
        for path, names in found.items()
        if names and path.split("/")[0] not in ("app", "cli.py")
    ]
    assert offenders == []
