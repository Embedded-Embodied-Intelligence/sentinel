"""Static schedule and its feasibility check (spec section 1.3)."""

from collections import defaultdict
from itertools import pairwise
from typing import Literal

from pydantic import BaseModel, ConfigDict

from sentinel.model.instance import ProjectInstance

ViolationKind = Literal["length", "source_start", "negative_start", "precedence", "resource"]


class Schedule(BaseModel):
    """Start times S_j indexed by activity id; any integers, feasibility is checked separately."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    starts: tuple[int, ...]

    def finish(self, instance: ProjectInstance, j: int) -> int:
        """Finish time F_j = S_j + p_j."""
        self._require_length(instance)
        return self.starts[j] + instance.activities[j].duration

    def makespan(self, instance: ProjectInstance) -> int:
        """Makespan C = S_{n+1}, the start of the dummy sink."""
        self._require_length(instance)
        return self.starts[instance.sink_id]

    def _require_length(self, instance: ProjectInstance) -> None:
        if len(self.starts) != instance.n_activities:
            raise ValueError(
                f"schedule has {len(self.starts)} start times but instance {instance.name} "
                f"has {instance.n_activities} activities"
            )


class Violation(BaseModel):
    """One violated feasibility condition; `time` is a start time or, for resources, the day."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: ViolationKind
    detail: str
    activity: int | None = None
    time: int | None = None
    role: int | None = None


def validate_schedule(instance: ProjectInstance, schedule: Schedule) -> list[Violation]:
    """All violated conditions of spec section 1.3; an empty list means the schedule is feasible.

    A length mismatch is reported alone because the other checks are then undefined. Resource
    overloads are reported once per (role, day).
    """
    starts = schedule.starts
    if len(starts) != instance.n_activities:
        return [
            Violation(
                kind="length",
                detail=f"schedule has {len(starts)} start times, expected {instance.n_activities}",
            )
        ]
    violations: list[Violation] = []
    source = instance.source_id
    if starts[source] != 0:
        violations.append(
            Violation(
                kind="source_start",
                activity=source,
                time=starts[source],
                detail=f"source activity {source} starts at {starts[source]}, expected 0",
            )
        )
    for j, start in enumerate(starts):
        if start < 0:
            violations.append(
                Violation(
                    kind="negative_start",
                    activity=j,
                    time=start,
                    detail=f"activity {j} starts at {start} < 0",
                )
            )
    for i, act in enumerate(instance.activities):
        finish_i = starts[i] + act.duration
        for j in act.successors:
            if starts[j] < finish_i:
                violations.append(
                    Violation(
                        kind="precedence",
                        activity=j,
                        time=starts[j],
                        detail=(
                            f"activity {j} starts at {starts[j]} before its predecessor {i} "
                            f"finishes at {finish_i}"
                        ),
                    )
                )
    violations.extend(_resource_violations(instance, starts))
    return violations


def _resource_violations(instance: ProjectInstance, starts: tuple[int, ...]) -> list[Violation]:
    """Days t with sum of r_jk over activities running on t (S_j <= t < F_j) above R_k."""
    violations: list[Violation] = []
    for role in instance.roles:
        k = role.id
        # Sweep over the days where the usage of role k changes.
        change: defaultdict[int, int] = defaultdict(int)
        for j, act in enumerate(instance.activities):
            if act.demands[k] > 0 and act.duration > 0:
                change[starts[j]] += act.demands[k]
                change[starts[j] + act.duration] -= act.demands[k]
        usage = 0
        for t_from, t_to in pairwise(sorted(change)):
            usage += change[t_from]
            if usage <= role.capacity:
                continue
            running = [
                j
                for j, act in enumerate(instance.activities)
                if act.demands[k] > 0 and starts[j] <= t_from < starts[j] + act.duration
            ]
            for day in range(t_from, t_to):
                violations.append(
                    Violation(
                        kind="resource",
                        time=day,
                        role=k,
                        detail=(
                            f"role {role.name} on day {day}: demand {usage} exceeds capacity "
                            f"{role.capacity} (activities {running})"
                        ),
                    )
                )
    return violations
