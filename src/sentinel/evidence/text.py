"""Plain text of a fetched HTML, XHTML or XML source (standard library only): the text of the
document without scripts, styles, templates and the head, with a line break at every block
element so that words of adjacent blocks never run together."""

import re
from html.parser import HTMLParser

# A <noscript> element is kept: it holds the page for a client without scripts, like this one.
SKIPPED = frozenset({"script", "style", "head", "svg", "template"})
BLOCKS = frozenset(
    {
        "p",
        "div",
        "br",
        "li",
        "ul",
        "ol",
        "tr",
        "td",
        "th",
        "table",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "section",
        "article",
        "blockquote",
        "dd",
        "dt",
        "pre",
        "header",
        "footer",
        "nav",
        "abstracttext",
        "articletitle",
        "title",
    }
)


class _Collector(HTMLParser):
    """Collects the text outside skipped elements, a newline at every block boundary."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skipping = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIPPED:
            self.skipping += 1
        elif tag in BLOCKS:
            self.parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIPPED:
            self.skipping = max(0, self.skipping - 1)
        elif tag in BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skipping:
            self.parts.append(data)


def markup_text(markup: str) -> str:
    """The plain text of an HTML, XHTML or XML document, one line per block."""
    collector = _Collector()
    collector.feed(markup)
    collector.close()
    text = "".join(collector.parts)
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    return re.sub(r"\n[ \t]*(\n[ \t]*)+", "\n", text).strip() + "\n"
