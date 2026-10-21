"""FullResolve and StableResolve: re-plan the rest of the project after disruptions (spec 7).

At an epoch with a new disruption the policy optionally substitutes absent crew members as
AlwaysSubstitute does, then plans the residual problem of the resulting state (spec section
4.1) with CP-SAT: for minimum makespan (FullResolve) or lexicographically for minimum deviation
from the current plan without a longer makespan (StableResolve; Van de Vonder et al. 2007).
"""

import time
from typing import ClassVar

from sentinel.policies.always_substitute import substitutions
from sentinel.policies.base import EMPTY_DECISION, Decision, DecisionStats, Reseq
from sentinel.scheduling.cpsat import Objective, solve_residual
from sentinel.scheduling.residual import planning_view
from sentinel.simulation.engine import preview
from sentinel.simulation.state import HANDOVER_FACTOR, Observation

T_CP = 0.1  # CP-SAT deterministic time limit per stage in policies (spec section 8)


class DisruptionMonitor:
    """Tells epochs with a new disruption from purely periodic ones (spec section 7).

    It keeps what the previous epoch showed: the absences (worker, first day), the number of D2
    shocks and of D3 activities. Absence onsets and returns, D3 insertions and the days after
    D2 shocks are decision epochs (spec section 3.1 g), so each of them is seen on its own
    epoch. An epoch has a new disruption iff any of these changed since the previous epoch; the
    first epoch of a run (an earlier or the same day as the last one seen) compares with a
    project without any.
    """

    __slots__ = ("_day", "_seen")

    def __init__(self) -> None:
        self._day = -1
        self._seen: tuple[tuple[int | None, ...], int, int] | None = None

    def new_disruption(self, observation: Observation) -> bool:
        seen = (
            observation.absent_since,
            len(observation.work_increases),
            len(observation.inserted),
        )
        before = self._seen
        if before is None or observation.day <= self._day:
            before = ((None,) * len(observation.absent_since), 0, 0)
        self._seen, self._day = seen, observation.day
        return seen != before


class FullResolve:
    """FullResolve(subst) of spec section 7: at every decision epoch with a new disruption (D1
    onset or return, D2, D3; `DisruptionMonitor`), first the SUBST operations of
    AlwaysSubstitute if `subst`, then a RESEQ with minimum residual makespan. It substitutes at
    these epochs only; AlwaysSubstitute does at every epoch.

    CP-SAT runs with one worker, `seed` and `deterministic_time_limit` per stage, hinted with
    the current plan where it is feasible; a stage without a solution falls back
    (`solve_residual`) and is counted in `stats.fallbacks`. The residual problem is planned on
    the observation as the policy's own SUBST operations leave it (`preview`, with
    `handover_factor`), which is the state the engine checks the RESEQ against. `monitor`
    decides which epochs have a new disruption; a policy object serves one run at a time.
    """

    objective: ClassVar[Objective] = "makespan"
    label: ClassVar[str] = "full_resolve"

    def __init__(
        self,
        subst: bool,
        *,
        deterministic_time_limit: float = T_CP,
        seed: int = 0,
        handover_factor: float = HANDOVER_FACTOR,
    ) -> None:
        self.subst = subst
        self.deterministic_time_limit = deterministic_time_limit
        self.seed = seed
        self.handover_factor = handover_factor
        self.stats = DecisionStats()
        self.monitor = DisruptionMonitor()

    @property
    def name(self) -> str:
        return f"{self.label}_subst" if self.subst else self.label

    def decide(self, observation: Observation) -> Decision:
        """SUBST (optionally) and RESEQ at an epoch with a new disruption, else nothing."""
        began = time.perf_counter()
        decision = EMPTY_DECISION
        if self.monitor.new_disruption(observation):
            operations = substitutions(observation) if self.subst else ()
            seen = observation
            if operations:
                substituted = Decision(operations=operations)
                seen = preview(observation, substituted, handover_factor=self.handover_factor)
            decision = Decision(operations=(*operations, self.reseq(seen)))
        self.stats.decisions += 1
        self.stats.decide_time_s += time.perf_counter() - began
        return decision

    def reseq(self, observation: Observation) -> Reseq:
        """The RESEQ of this policy's objective for the residual problem of `observation`."""
        problem = planning_view(observation)
        solution = solve_residual(
            problem,
            self.objective,
            deterministic_time_limit=self.deterministic_time_limit,
            seed=self.seed,
            hint=problem.planned_starts(),
        )
        stats = self.stats
        stats.reseqs += 1
        stats.fallbacks += solution.fallbacks
        stats.solve_time_s += solution.wall_time_s
        stats.deterministic_time += solution.deterministic_time
        return Reseq(starts=solution.starts)


class StableResolve(FullResolve):
    """StableResolve(subst) of spec section 7: as FullResolve, but the RESEQ is lexicographic,
    minimum residual makespan C_1 first, then minimum sum_j |S_j - S_j^t| from the current plan
    subject to makespan <= C_1 (Van de Vonder et al. 2007 style robust repair)."""

    objective: ClassVar[Objective] = "stable"
    label: ClassVar[str] = "stable_resolve"
