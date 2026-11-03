"""The working-day calendar of a live project (spec section 11.1).

Working days are Monday to Friday without holidays (spec section 10.1); a live project also skips
the Polish public holidays and its own days off (v2.2.0), while the simulator and projects stored
before it keep Monday to Friday. Model day t is the t-th working day on or after the project's
start date (t = 0 the first); `first(d)` is the day of the first working day on or after a date
d, `last(d)` that of the last working day on or before it (-1 before day 0). Starts are shown as
their date, finishes F as the date of their last day of work F - 1, and a check-in dated d is the
observation of day last(d) + 1. Every date a page shows comes from `date_of`.
"""

from bisect import bisect_right
from collections.abc import Iterable
from datetime import date, timedelta
from functools import cache
from typing import Literal

WORKING_DAYS = 5  # Monday to Friday
CHRISTMAS_EVE_FROM = 2025  # 24 December is a public holiday in Poland from 2025 on

Holidays = Literal["pl", "none"]

# Fixed-date public holidays in Poland (Ustawa o dniach wolnych od pracy, 1951, as amended).
FIXED_HOLIDAYS = ((1, 1), (1, 6), (5, 1), (5, 3), (8, 15), (11, 1), (11, 11), (12, 25), (12, 26))


def easter_sunday(year: int) -> date:
    """Easter Sunday of the Gregorian calendar (the anonymous algorithm; Meeus 1991)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741 - the algorithm's name
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


@cache
def polish_holidays(year: int) -> frozenset[date]:
    """The public holidays of a year in Poland that can fall on a working day: the fixed dates
    (24 December from 2025), Easter Monday and Corpus Christi (Easter + 1 and + 60 days)."""
    days = {date(year, month, day) for month, day in FIXED_HOLIDAYS}
    if year >= CHRISTMAS_EVE_FROM:
        days.add(date(year, 12, 24))
    easter = easter_sunday(year)
    days.add(easter + timedelta(days=1))
    days.add(easter + timedelta(days=60))
    return frozenset(days)


class WorkCalendar:
    """Model days of a project that starts on `start` (spec section 11.1): Monday to Friday,
    without the Polish public holidays with `holidays="pl"` and without the dates `days_off`."""

    def __init__(
        self, start: date, *, holidays: Holidays = "none", days_off: Iterable[date] = ()
    ) -> None:
        self.start = start
        self.holidays = holidays
        self.days_off = frozenset(days_off)
        self.plain = holidays == "none" and not self.days_off
        weekday = start.weekday()
        # Day 0 is the first working day on or after the start date.
        origin = start + timedelta(days=7 - weekday) if weekday >= WORKING_DAYS else start
        while not self.is_working(origin):
            origin += timedelta(days=1)
        self.origin = origin
        self._monday = self.origin - timedelta(days=self.origin.weekday())
        self._offset = self.origin.weekday()  # working days of day 0's week before day 0
        self._after = [origin]  # the working days 0, 1, 2, ... found so far
        self._before: list[date] = []  # the working days -1, -2, ... found so far

    def is_working(self, value: date) -> bool:
        """Whether `value` is a working day of this calendar."""
        if value.weekday() >= WORKING_DAYS or value in self.days_off:
            return False
        return self.holidays == "none" or value not in polish_holidays(value.year)

    def _step(self, value: date, step: int) -> date:
        value += timedelta(days=step)
        while not self.is_working(value):
            value += timedelta(days=step)
        return value

    def date_of(self, day: int) -> date:
        """The calendar date of model day `day` (negative days lie before day 0)."""
        if self.plain:
            weeks, weekday = divmod(day + self._offset, WORKING_DAYS)
            return self._monday + timedelta(days=7 * weeks + weekday)
        if day >= 0:
            while len(self._after) <= day:
                self._after.append(self._step(self._after[-1], 1))
            return self._after[day]
        while len(self._before) < -day:
            self._before.append(self._step(self._before[-1] if self._before else self.origin, -1))
        return self._before[-day - 1]

    def _index(self, value: date) -> tuple[int, bool]:
        """(the day of `value`, or of the working day before it, and whether it is not one)."""
        if self.plain:
            weeks, weekday = divmod((value - self._monday).days, 7)
            weekend = weekday >= WORKING_DAYS
            return WORKING_DAYS * weeks + min(weekday, WORKING_DAYS - 1) - self._offset, weekend
        if value >= self.origin:
            while self._after[-1] < value:
                self.date_of(len(self._after))
            day = bisect_right(self._after, value) - 1
            return day, self._after[day] != value
        day = -1
        while self.date_of(day) > value:
            day -= 1
        return day, self.date_of(day) != value

    def first(self, value: date) -> int:
        """The day of the first working day on or after `value`."""
        day, off = self._index(value)
        return day + 1 if off else day

    def last(self, value: date) -> int:
        """The day of the last working day on or before `value` (-1 before day 0)."""
        return self._index(value)[0]

    def finish_date(self, finish: int) -> date:
        """The date of the last day of work of a finish F (or a makespan C): date(F - 1)."""
        return self.date_of(finish - 1)

    def checkin_day(self, value: date) -> int:
        """The observation day of a check-in dated `value`: the end of that date, so the next
        working day last(value) + 1 (0 before the project starts)."""
        return max(0, self.last(value) + 1)

    def deadline(self, value: date) -> int:
        """D of a deadline date: all work done by the end of `value`, so last(value) + 1."""
        return self.last(value) + 1

    def workdays(self, first: date, last: date) -> int:
        """Working days in [first, last], 0 if `last` is before `first`."""
        return max(0, self.last(last) - self.first(first) + 1)
