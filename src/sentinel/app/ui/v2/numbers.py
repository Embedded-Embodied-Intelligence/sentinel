"""The numbers and states of the v2 pages (docs/design/v2-spec.md, section 4; spec section 11.8):
a chance as a natural frequency "N na 100" (Gigerenzer & Hoffrage 1995), the three states with
their verdict, the working days to the deadline, and the points of the "Zapas czasu" chart, a
buffer-consumption (fever) chart (Goldratt 1997; Leach 2014). Pure functions only."""

from dataclasses import dataclass
from typing import Literal

from sentinel.app.planning import half_up

State = Literal["good", "warn", "bad"]
GOOD_FROM = 80  # P80, the target theta_D of spec section 8 in 100
WARN_FROM = 50  # below it the most likely finish is after the deadline


def per_hundred(p: float) -> int:
    """A chance as "N na 100": whole, half up, 0 or 100 only when exact (as `shown_chance`, so a
    page never says "100 na 100" of a future in which the project can still be late)."""
    n = int(half_up(100 * p))
    if p in (0.0, 1.0):
        return n
    return min(max(n, 1), 99)


def hits(p: float, worlds: int) -> int:
    """K of "W ilu z nich": the played futures on time out of `worlds` (p = K / W)."""
    return int(half_up(p * worlds))


def state_of(n: int) -> State:
    """The state of a chance in 100: "Na dobrej drodze" from 80, "Zagrożony" from 50."""
    if n >= GOOD_FROM:
        return "good"
    return "warn" if n >= WARN_FROM else "bad"


@dataclass(frozen=True)
class Verdict:
    """The verdict of a project: its state, the chance in 100 and the working days of reserve
    (`days` before the deadline in the good and warn states, after it in the bad one)."""

    state: State
    n: int
    days: int


def verdict(p: float, slack: int) -> Verdict:
    """The verdict of chance `p` with the most likely finish `slack` working days before the
    deadline (negative: after it). In the good and warn states the days are clamped at 0: a
    chance rounded up to 50 can sit on a median one day late, and the page then says "no
    reserve" instead of a negative one (spec 11.8); in the bad state the median is late."""
    n = per_hundred(p)
    state = state_of(n)
    days = max(0, -slack) if state == "bad" else max(0, slack)
    return Verdict(state, n, days)


# --------------------------------------------------------------------------- "Zapas czasu"

Zone = Literal["good", "warn", "bad"]


@dataclass(frozen=True)
class BufferPoint:
    """A report on the chart: the share of the work done and of the time reserve used."""

    work: float  # 0..1
    used: float  # 0.. (above 1 when the most likely finish is after the deadline)


def reserve_of(deadline_day: int, baseline_end: int) -> int:
    """The time reserve of the plan in working days: D minus the makespan of the original plan."""
    return deadline_day - baseline_end


def buffer_point(
    work_done: float, work_total: float, likely_end: int, baseline_end: int, reserve: int
) -> BufferPoint:
    """The point of one report: the share of the work done (in crew-member days) and the share
    of the reserve used, used = most likely finish - end of the original plan, clamped at 0."""
    work = 0.0 if work_total <= 0 else min(1.0, max(0.0, work_done / work_total))
    used = max(0, likely_end - baseline_end) / reserve
    return BufferPoint(work, used)


def zone_of(point: BufferPoint) -> Zone:
    """The zone of a point: the band between the lines y = 2x/3 and y = 1/3 + 2x/3 is amber,
    below it green, above it red, so at half the work each zone is a third of the reserve."""
    low = 2 * point.work / 3
    if point.used <= low:
        return "good"
    return "warn" if point.used <= low + 1 / 3 else "bad"


def work_share(tasks: list[tuple[str, float | None, float | None]]) -> tuple[float, float]:
    """(work done, total work) in crew-member days from (state, percent, work total) of the
    tasks: a done task counts in full, a running one by its share, a removed one not at all."""
    done = total = 0.0
    for state, percent, work in tasks:
        if state == "removed" or work is None:
            continue
        total += work
        if state == "done":
            done += work
        elif state in ("in_progress", "paused") and percent is not None:
            done += work * percent / 100
    return done, total
