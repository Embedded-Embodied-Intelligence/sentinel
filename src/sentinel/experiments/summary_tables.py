"""Tables of a generated `summary.md`, addressed by section, caption, row and column (WP7).

The paper generator takes every number it cites from a cell of a summary table, as printed, so
that the article, the course report and the summaries agree. A table belongs to the headings
above it (`section`, outermost first) and has the caption of the text line just above it, if
any; a row is found by the values of its key columns. Cells keep their text and the line of the
file they are on, for the source comment of each macro. `parse_cell` splits a printed cell into
its parts: value, interval, count, share, standard error or fraction.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


class TableError(LookupError):
    """A table, row or column is missing or ambiguous."""


@dataclass(frozen=True)
class Cell:
    """A printed cell with its location: file, line, section, caption, row and column."""

    text: str
    path: str
    line: int
    section: tuple[str, ...]
    caption: str | None
    row: Mapping[str, str]
    column: str

    def source(self, key: Sequence[str]) -> str:
        """`file:line | section | row k=v, ... | column "c"` for a macro comment."""
        where = " / ".join(self.section)
        label = ", ".join(f"{name}={self.row[name]}" for name in key)
        caption = f" | {self.caption}" if self.caption else ""
        return f'{self.path}:{self.line} | {where}{caption} | row {label} | column "{self.column}"'


@dataclass(frozen=True)
class Table:
    """A Markdown table: its headings, caption, header, rows and the line of each row."""

    path: str
    section: tuple[str, ...]
    caption: str | None
    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    lines: tuple[int, ...]

    def row(self, **key: str) -> int:
        """The index of the one row whose cells equal `key` (column name: text)."""
        missing = [name for name in key if name not in self.header]
        if missing:
            raise TableError(f"{self.path}: no column {missing} in {self.header}")
        found = [
            i
            for i, row in enumerate(self.rows)
            if all(row[self.header.index(name)] == text for name, text in key.items())
        ]
        if len(found) != 1:
            raise TableError(f"{self.path}: {len(found)} rows match {key} in {self.section}")
        return found[0]

    def cell(self, column: str, **key: str) -> Cell:
        """The cell of `column` in the row matching `key`."""
        if column not in self.header:
            raise TableError(f"{self.path}: no column {column!r} in {self.header}")
        index = self.row(**key)
        row = self.rows[index]
        values = dict(zip(self.header, row, strict=True))
        return Cell(
            row[self.header.index(column)],
            self.path,
            self.lines[index],
            self.section,
            self.caption,
            values,
            column,
        )

    def column(self, column: str) -> list[str]:
        """Every cell of a column, in row order."""
        if column not in self.header:
            raise TableError(f"{self.path}: no column {column!r} in {self.header}")
        return [row[self.header.index(column)] for row in self.rows]


class SummaryTables:
    """Every table of a summary file."""

    def __init__(self, path: Path, shown: str | None = None) -> None:
        self.path = shown or path.as_posix()
        self.tables = _read(path.read_text(encoding="utf-8").splitlines(), self.path)

    def table(
        self,
        *section: str,
        caption: str | None = None,
        header: str | None = None,
        columns: Sequence[str] = (),
    ) -> Table:
        """The one table under headings that end with `section` (each heading matched by its
        start), with a caption starting with `caption`, a first header cell `header` and every
        header cell of `columns`."""
        found = [
            t
            for t in self.tables
            if _ends_with(t.section, section)
            and (caption is None or (t.caption or "").startswith(caption))
            and (header is None or t.header[0] == header)
            and all(column in t.header for column in columns)
        ]
        if len(found) != 1:
            raise TableError(
                f"{self.path}: {len(found)} tables under {section} with caption {caption!r}"
            )
        return found[0]


def _ends_with(headings: tuple[str, ...], wanted: tuple[str, ...]) -> bool:
    if len(wanted) > len(headings):
        return False
    tail = headings[len(headings) - len(wanted) :]
    return all(have.startswith(want) for have, want in zip(tail, wanted, strict=True))


def _cells(line: str) -> tuple[str, ...]:
    """The cells of a table line; `\\|` is a literal bar."""
    inner = line.strip()
    inner = inner[1:] if inner.startswith("|") else inner
    inner = inner[:-1] if inner.endswith("|") and not inner.endswith("\\|") else inner
    return tuple(part.replace("\\|", "|").strip() for part in re.split(r"(?<!\\)\|", inner))


def _read(lines: Sequence[str], path: str) -> list[Table]:
    tables: list[Table] = []
    headings: list[tuple[int, str]] = []
    caption: str | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        heading = re.match(r"^(#+)\s+(.*)$", line)
        if heading:
            level = len(heading.group(1))
            headings = [(lv, text) for lv, text in headings if lv < level]
            headings.append((level, heading.group(2).strip()))
            caption = None
            i += 1
            continue
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|\s*:?-", lines[i + 1]):
            header = _cells(line)
            rows, numbers = [], []
            j = i + 2
            while j < len(lines) and lines[j].startswith("|"):
                cells = _cells(lines[j])
                if len(cells) != len(header):
                    raise TableError(
                        f"{path}:{j + 1}: {len(cells)} cells, header has {len(header)}"
                    )
                rows.append(cells)
                numbers.append(j + 1)
                j += 1
            section = tuple(text for _, text in headings[1:]) or tuple(t for _, t in headings)
            tables.append(Table(path, section, caption, header, tuple(rows), tuple(numbers)))
            caption = None
            i = j
            continue
        if line.strip():
            caption = line.strip()
        i += 1
    return tables


_NUMBER = r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)"


@dataclass(frozen=True)
class Parts:
    """A printed cell split into its parts (None where the cell has no such part)."""

    value: str
    low: str | None = None
    high: str | None = None
    n: str | None = None
    share: str | None = None
    se: str | None = None
    denominator: str | None = None


def parse_cell(text: str) -> Parts:
    """Split `97.5 [87.1, 99.6] (n = 200)`, `+0.036 ± 0.021`, `240 (50.0%)`, `0.902 (765)`,
    `150/150 (100 %)` or a plain number into its parts."""
    patterns = (
        (rf"^({_NUMBER})%? \[({_NUMBER}), ({_NUMBER})\](?: \(n = (\d+)\))?$", "interval"),
        (rf"^({_NUMBER}) ± ({_NUMBER})$", "se"),
        (rf"^(\d+)/(\d+) \(({_NUMBER}) ?%\)$", "fraction"),
        (rf"^({_NUMBER}) \(({_NUMBER}) ?%\)$", "share"),
        (rf"^({_NUMBER}) \((\d+)\)$", "count"),
        (rf"^({_NUMBER})$", "plain"),
    )
    for pattern, kind in patterns:
        match = re.match(pattern, text.strip())
        if match is None:
            continue
        groups = match.groups()
        if kind == "interval":
            return Parts(groups[0], groups[1], groups[2], groups[3])
        if kind == "se":
            return Parts(groups[0], se=groups[1])
        if kind == "fraction":
            return Parts(groups[0], denominator=groups[1], share=groups[2])
        if kind == "share":
            return Parts(groups[0], share=groups[1])
        if kind == "count":
            return Parts(groups[0], n=groups[1])
        return Parts(groups[0])
    raise ValueError(f"cannot read the cell {text!r}")
