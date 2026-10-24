"""The working-day calendar of a live project (spec section 11.1).

Working days are Monday to Friday without holidays (spec section 10.1). Model day t is the t-th
working day on or after the project's start date (t = 0 the first); `first(d)` is the day of
the first working day on or after a date d, `last(d)` that of the last working day on or before
it (-1 before day 0). Starts are shown as their date, finishes F as the date of their last day of
work F - 1, and a check-in dated d is the observation of day last(d) + 1.
"""

from datetime import date, timedelta

WORKING_DAYS = 5  # Monday to Friday


class WorkCalendar:
    """Model days of a project that starts on `start` (spec section 11.1)."""

    def __init__(self, start: date) -> None:
        self.start = start
        weekday = start.weekday()
        # Day 0 is the first working day on or after the start date.
        self.origin = start + timedelta(days=7 - weekday) if weekday >= WORKING_DAYS else start
        self._monday = self.origin - timedelta(days=self.origin.weekday())
        self._offset = self.origin.weekday()  # working days of day 0's week before day 0

    def date_of(self, day: int) -> date:
        """The calendar date of model day `day` (negative days lie before day 0)."""
        weeks, weekday = divmod(day + self._offset, WORKING_DAYS)
        return self._monday + timedelta(days=7 * weeks + weekday)

    def _index(self, value: date) -> tuple[int, bool]:
        """(the day of `value`, or of the Friday before it, and whether it is a weekend day)."""
        weeks, weekday = divmod((value - self._monday).days, 7)
        weekend = weekday >= WORKING_DAYS
        return WORKING_DAYS * weeks + min(weekday, WORKING_DAYS - 1) - self._offset, weekend

    def first(self, value: date) -> int:
        """The day of the first working day on or after `value`."""
        day, weekend = self._index(value)
        return day + 1 if weekend else day

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
