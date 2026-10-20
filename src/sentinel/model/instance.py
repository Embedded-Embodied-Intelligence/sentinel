"""Static project instance P = (J, E, K, W, p, r, D, B) of spec section 1."""

import heapq
from collections.abc import Sequence
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PrivateAttr, model_validator


class Role(BaseModel):
    """Role k: renewable resource type with nominal capacity R_k = number of its workers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: NonNegativeInt
    name: str = Field(min_length=1)
    capacity: NonNegativeInt


class Worker(BaseModel):
    """Worker w with exactly one role; only availability is ever modelled (GDPR Art. 9)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: NonNegativeInt
    role: NonNegativeInt
    name: str = Field(min_length=1)


class Activity(BaseModel):
    """Activity j: duration p_j, demands r_jk (one per role), finish-to-start successors."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: NonNegativeInt
    # p_j = 0 is allowed for real activities too (zero-duration milestones, spec section 1).
    duration: NonNegativeInt
    demands: tuple[NonNegativeInt, ...]
    successors: tuple[NonNegativeInt, ...]
    name: str = ""


class ProjectInstance(BaseModel):
    """Project instance with every validity condition of spec section 1 checked at construction.

    Activity 0 is the dummy source and activity n+1 the dummy sink. Derived data (predecessors,
    topological order) is computed once during validation; `model_copy(update=...)` skips
    validation (pydantic semantics) and must not be used to change activities or roles.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    activities: tuple[Activity, ...]
    roles: tuple[Role, ...]
    workers: tuple[Worker, ...]
    deadline: NonNegativeInt | None = None
    budget: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    source: str | None = None

    _predecessors: tuple[tuple[int, ...], ...] = PrivateAttr(default=())
    _topological_order: tuple[int, ...] = PrivateAttr(default=())

    @model_validator(mode="after")
    def _check_validity(self) -> Self:
        self._check_roles_and_workers()
        self._check_activities()
        predecessors: list[list[int]] = [[] for _ in self.activities]
        for act in self.activities:
            for succ in act.successors:
                predecessors[succ].append(act.id)
        self._predecessors = tuple(tuple(sorted(p)) for p in predecessors)
        self._topological_order = self._kahn_order()
        self._check_reachability()
        return self

    def _check_roles_and_workers(self) -> None:
        for k, role in enumerate(self.roles):
            if role.id != k:
                raise ValueError(
                    f"role ids must be 0..{len(self.roles) - 1} in order, got {role.id}"
                )
        n_workers = [0] * len(self.roles)
        for w, worker in enumerate(self.workers):
            if worker.id != w:
                raise ValueError(
                    f"worker ids must be 0..{len(self.workers) - 1} in order, got {worker.id}"
                )
            if worker.role >= len(self.roles):
                raise ValueError(f"worker {w} has unknown role {worker.role}")
            n_workers[worker.role] += 1
        for role in self.roles:
            if n_workers[role.id] != role.capacity:
                raise ValueError(
                    f"role {role.name} has capacity {role.capacity} but {n_workers[role.id]} "
                    "workers; R_k must equal the number of workers with role k"
                )

    def _check_activities(self) -> None:
        n_act = len(self.activities)
        if n_act < 2:
            raise ValueError("an instance needs at least the dummy source and sink activities")
        sink = n_act - 1
        for j, act in enumerate(self.activities):
            if act.id != j:
                raise ValueError(f"activity ids must be 0..{sink} in order, got {act.id}")
            if len(act.demands) != len(self.roles):
                raise ValueError(
                    f"activity {j} has {len(act.demands)} demands, expected {len(self.roles)}"
                )
            if len(set(act.successors)) != len(act.successors):
                raise ValueError(f"activity {j} lists a successor more than once")
            for succ in act.successors:
                if succ >= n_act:
                    raise ValueError(f"activity {j} has unknown successor {succ}")
                if succ == 0:
                    raise ValueError(f"source activity 0 must have no predecessors, got {j}")
            for demand, role in zip(act.demands, self.roles, strict=True):
                if demand > role.capacity:
                    raise ValueError(
                        f"activity {j} demands {demand} of role {role.name} "
                        f"but its capacity is {role.capacity}"
                    )
        for j in (0, sink):
            if self.activities[j].duration != 0 or any(self.activities[j].demands):
                raise ValueError(f"dummy activity {j} must have duration 0 and zero demands")
        if self.activities[sink].successors:
            raise ValueError(f"sink activity {sink} must have no successors")

    def _kahn_order(self) -> tuple[int, ...]:
        """Topological order, smallest ready id first; raises if the graph is cyclic (Kahn 1962)."""
        indegree = [len(p) for p in self._predecessors]
        ready = [j for j, d in enumerate(indegree) if d == 0]
        heapq.heapify(ready)
        order: list[int] = []
        while ready:
            j = heapq.heappop(ready)
            order.append(j)
            for succ in self.activities[j].successors:
                indegree[succ] -= 1
                if indegree[succ] == 0:
                    heapq.heappush(ready, succ)
        if len(order) < len(self.activities):
            stuck = sorted(set(range(len(self.activities))) - set(order))
            raise ValueError(f"precedence graph is cyclic; activities on or after a cycle: {stuck}")
        return tuple(order)

    def _check_reachability(self) -> None:
        # In a DAG whose only source is 0 and only sink is n+1, every activity is reachable
        # from 0 and reaches n+1 (walk predecessors/successors until 0/n+1 is hit).
        sink = self.sink_id
        for j, act in enumerate(self.activities):
            if j != 0 and not self._predecessors[j]:
                raise ValueError(f"activity {j} has no predecessors: not reachable from 0")
            if j != sink and not act.successors:
                raise ValueError(f"activity {j} has no successors: does not reach {sink}")

    @property
    def n_activities(self) -> int:
        """Number of activities including both dummies (n + 2)."""
        return len(self.activities)

    @property
    def n_real(self) -> int:
        """Number of real (non-dummy) activities n."""
        return len(self.activities) - 2

    @property
    def source_id(self) -> int:
        """Id of the dummy start activity (0)."""
        return 0

    @property
    def sink_id(self) -> int:
        """Id of the dummy end activity (n + 1)."""
        return len(self.activities) - 1

    def predecessors(self, j: int) -> tuple[int, ...]:
        """Immediate predecessors of activity j, in increasing id order."""
        return self._predecessors[j]

    def topological_order(self) -> tuple[int, ...]:
        """All activity ids in a topological order (deterministic: smallest ready id first)."""
        return self._topological_order


def make_workers(roles: Sequence[Role]) -> tuple[Worker, ...]:
    """One worker w = (k, i) per capacity unit i = 0..R_k-1 of every role k (spec section 1.1)."""
    workers: list[Worker] = []
    for role in roles:
        for i in range(role.capacity):
            workers.append(Worker(id=len(workers), role=role.id, name=f"{role.name}-{i}"))
    return tuple(workers)
