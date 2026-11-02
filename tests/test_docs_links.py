"""The guides of WP9c point to files and sections that exist: the user guides (Polish and
English, with their screenshots), the deployment guide, the usability protocol, the QA report,
and (WP11) the README and the changelog."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUIDES = (
    "docs/user-guide-pl.md",
    "docs/user-guide-en.md",
    "docs/deploy.md",
    "docs/usability/protocol-pl.md",
    "docs/usability/results-template.md",
    "docs/qa/raport-qa-pl.md",
    "README.md",
    "CHANGELOG.md",
)
LINK = re.compile(r"(!?)\[[^\]]*\]\(([^)\s]+)\)")
IMAGE = re.compile(r'<img src="([^"]+)"')


def _headings(path: Path) -> set[str]:
    """The anchors of a Markdown file's headings, as GitHub makes them."""
    anchors, fenced = set(), False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and (found := re.match(r"#{1,6} (.+)", line)):
            anchors.add(re.sub(r"[^\w\- ]", "", found.group(1).strip().lower()).replace(" ", "-"))
    return anchors


@pytest.mark.parametrize("guide", GUIDES)
def test_links_and_images_exist(guide: str) -> None:
    path = ROOT / guide
    text = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.DOTALL)
    broken = []
    for image, target in LINK.findall(text):
        if re.match(r"[a-z]+:", target):  # https:, mailto:
            continue
        file, _, anchor = target.partition("#")
        linked = (path.parent / file).resolve() if file else path
        missing = not (linked.is_file() or (not image and linked.is_dir()))
        unknown = bool(anchor) and linked.suffix == ".md" and anchor not in _headings(linked)
        if missing or unknown or (image and linked.suffix != ".png"):
            broken.append(target)
    assert broken == []


def test_the_qa_report_is_readable_on_a_phone() -> None:
    """The owner reads it on a phone (WP10): at most 15 screenshots, all of phone width, no table
    wider than a phone, and every screenshot there."""
    path = ROOT / "docs/qa/raport-qa-pl.md"
    text = path.read_text(encoding="utf-8")
    images = IMAGE.findall(text)
    assert 0 < len(images) <= 15
    assert all((path.parent / image).is_file() for image in images)
    assert not any(line.startswith("|") for line in text.splitlines())


def test_each_user_guide_shows_its_own_language() -> None:
    for language in ("pl", "en"):
        text = (ROOT / f"docs/user-guide-{language}.md").read_text(encoding="utf-8")
        images = re.findall(r"!\[[^\]]*\]\(ui/([^)]+)\)", text)
        assert len(images) >= 10 and all(name.startswith(f"{language}_") for name in images)
