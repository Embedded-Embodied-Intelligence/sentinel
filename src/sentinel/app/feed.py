"""A project's calendar feed (docs/design/v2-spec.md, section 8.9; ADR-0035): an iCalendar file
(RFC 5545) that a calendar subscribes to by a secret link. It holds the deadline, the plan's task
starts and ends, the absences as dates and names only (no reason is ever known, let alone
written: invariant 7), the validity dates of the decisions waiting and the weekly report
reminder. Written by hand with the standard library: all-day events as dates, the reminder at a
floating local time, lines folded at 75 octets, text escaped."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

PRODID = "-//Sentinel//Project calendar//EN"
WEEKDAYS = ("MO", "TU", "WE", "TH", "FR")
REMINDER_MINUTES = 15


@dataclass(frozen=True)
class Entry:
    """An event of the feed: a stable id, its words and its days; `last` is the last day of an
    all-day span (equal to `first` for one day); `at` makes it a timed event."""

    uid: str
    summary: str
    first: date
    last: date
    description: str = ""
    at: str | None = None  # "HH:MM", a floating local time
    weekly: int | None = None  # the weekday of a weekly repetition (0 Monday)


def escape(text: str) -> str:
    """A TEXT value (RFC 5545, 3.3.11): backslash, semicolon, comma and newline escaped."""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def fold(line: str) -> list[str]:
    """A content line folded at 75 octets (RFC 5545, 3.1), never inside a UTF-8 character."""
    parts: list[str] = []
    current, size, limit = "", 0, 75
    for char in line:
        width = len(char.encode("utf-8"))
        if size + width > limit:
            parts.append(current)
            current, size, limit = " ", 1, 75
        current += char
        size += width
    parts.append(current)
    return parts


def _day(value: date) -> str:
    return value.strftime("%Y%m%d")


def event_lines(entry: Entry, stamp: datetime) -> list[str]:
    lines = [
        "BEGIN:VEVENT",
        f"UID:{entry.uid}",
        f"DTSTAMP:{stamp.astimezone(UTC).strftime('%Y%m%dT%H%M%SZ')}",
    ]
    if entry.at is None:
        lines += [
            f"DTSTART;VALUE=DATE:{_day(entry.first)}",
            f"DTEND;VALUE=DATE:{_day(entry.last + timedelta(days=1))}",
            "TRANSP:TRANSPARENT",
        ]
    else:
        hour, minute = entry.at.split(":")
        start = f"{_day(entry.first)}T{hour}{minute}00"
        lines += [f"DTSTART:{start}", f"DURATION:PT{REMINDER_MINUTES}M"]
        if entry.weekly is not None:
            lines.append(f"RRULE:FREQ=WEEKLY;BYDAY={WEEKDAYS[entry.weekly]}")
    lines.append(f"SUMMARY:{escape(entry.summary)}")
    if entry.description:
        lines.append(f"DESCRIPTION:{escape(entry.description)}")
    if entry.at is not None:
        lines += [
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{escape(entry.summary)}",
            "TRIGGER:PT0M",
            "END:VALARM",
        ]
    lines.append("END:VEVENT")
    return lines


def calendar(name: str, entries: Iterable[Entry], stamp: datetime) -> str:
    """The iCalendar text of a project's feed, CRLF line ends (RFC 5545, 3.1)."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape(name)}",
        "X-WR-TIMEZONE:Europe/Warsaw",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
        "X-PUBLISHED-TTL:PT1H",
    ]
    for entry in sorted(entries, key=lambda entry: (entry.first, entry.uid)):
        lines += event_lines(entry, stamp)
    lines.append("END:VCALENDAR")
    return "".join(part + "\r\n" for line in lines for part in fold(line))


def next_weekday(after: date, weekday: int) -> date:
    """The first `weekday` (0 Monday) on or after `after`."""
    return after + timedelta(days=(weekday - after.weekday()) % 7)
