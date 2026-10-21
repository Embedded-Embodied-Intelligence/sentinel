"""AlwaysSubstitute: replace absent crew members by idle workers at once (spec section 7)."""

import time

from sentinel.policies.base import EMPTY_DECISION, Decision, DecisionStats, Subst
from sentinel.policies.urgency import urgencies
from sentinel.simulation.state import PAUSED, RUNNING, Observation, worker_roles


class AlwaysSubstitute:
    """At every decision epoch, the SUBST operations of `substitutions`; the plan is unchanged
    (spec section 7). `stats` records the decisions of the current run."""

    name = "always_substitute"

    def __init__(self) -> None:
        self.stats = DecisionStats()

    def decide(self, observation: Observation) -> Decision:
        """SUBST for every paused or running activity with absent members, most urgent first."""
        began = time.perf_counter()
        operations = substitutions(observation)
        self.stats.decisions += 1
        self.stats.decide_time_s += time.perf_counter() - began
        return Decision(operations=operations) if operations else EMPTY_DECISION


def substitutions(observation: Observation) -> tuple[Subst, ...]:
    """The SUBST operations of AlwaysSubstitute (spec section 7).

    Paused and running activities with absent members are taken in increasing urgency tau_j
    (spec section 5), ties by id. Each of their absent members, in increasing id order, is
    replaced by the lowest-id idle present worker of its role while one is left; an idle worker
    is present and in no crew, a hired temporary worker included (spec section 4). One SUBST
    per activity lists its substitutes in that order, so the engine pairs them with the same
    absent members (`Subst`).
    """
    status, present, assigned = observation.status, observation.present, observation.assigned
    started = [j for j, state in enumerate(status) if state in (RUNNING, PAUSED)]
    candidates = [j for j in started if not all(present[w] for w in assigned[j])]
    if not candidates:
        return ()
    roles = worker_roles(observation)
    busy = {w for j in started for w in assigned[j]}
    idle: dict[int, list[int]] = {}  # role -> idle present workers, increasing ids
    for w, here in enumerate(present):
        if here and w not in busy:
            idle.setdefault(roles[w], []).append(w)
    if not any(idle.get(roles[w]) for j in candidates for w in assigned[j] if not present[w]):
        return ()
    if len(candidates) > 1:
        tau = urgencies(observation, candidates)
        candidates.sort(key=lambda j: (tau[j], j))
    operations: list[Subst] = []
    for j in candidates:
        chosen: list[int] = []
        for w in sorted(assigned[j]):
            pool = idle.get(roles[w])
            if not present[w] and pool:
                chosen.append(pool.pop(0))
        if chosen:
            operations.append(Subst(activity=j, workers=tuple(chosen)))
    return tuple(operations)
