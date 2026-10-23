"""The compact English state summary that a proposal call is given (spec section 10.3; RQ5).

`state_summary` renders a deliberation that passed the needs gate: the day and deadline, the
forecast without action (NOOP's p and T on the epoch's rollouts), the budget status, the team
with the temporary workers OVERTIME may hire, the most urgent activities with their urgency
tau_j (spec section 5), the absent workers by role with their announced return, the idle
workers and the backlog per role (spec section 6), the activities a SUBST can serve, and the
rule candidates with their statistics from the `DecisionRecord`. Every number comes from the
observation or the record.
"""

from collections.abc import Mapping

from sentinel.agent.candidates import backlogs, single_substitutions
from sentinel.agent.decide import DecisionRecord
from sentinel.agent.params import SentinelParams
from sentinel.interpret.team import plural, weekday_name
from sentinel.policies.urgency import urgencies
from sentinel.simulation.state import (
    PAUSED,
    RUNNING,
    UNSTARTED,
    Observation,
    nominal_activity,
    nominal_world,
    overtime_cap,
    worker_roles,
)
from sentinel.wbs.narrate import role_names

AT_RISK = 8  # activities listed with their urgency


def state_summary(
    observation: Observation,
    record: DecisionRecord,
    names: Mapping[int, str],
    params: SentinelParams,
) -> str:
    """The summary of the deliberation `record` on `observation` (module docstring); `names`
    names the real activities."""
    t, deadline, budget = observation.day, observation.deadline, observation.budget
    if deadline is None or budget is None or record.needs is None:
        raise ValueError("a state summary needs a deadline, a budget and the needs of NOOP")
    roles = role_names(observation.instance)
    capacities = [role.capacity for role in observation.instance.roles]
    noop = next((c for c in record.candidates if c.kind == "noop"), None)
    lines = [
        f"Day {t} ({weekday_name(t)}). Deadline: day {deadline}, {deadline - t} working days "
        f"from today. Target: finish by the deadline with probability at least "
        f"{params.theta_d:.2f}.",
    ]
    if noop is not None:
        lines.append(
            f"Without action (NOOP, {noop.rollouts} simulated futures): P(on time) "
            f"{noop.p_on_time:.2f}, expected tardiness {noop.tardiness:.2f} days, expected total "
            f"cost {noop.mean_cost:.1f}."
        )
    else:
        lines.append(
            f"Without action (NOOP, {record.needs.rollouts} simulated futures): P(on time) "
            f"{record.needs.p_on_time:.2f}."
        )
    lines.append(f"Budget: {budget:.1f}, spent so far {observation.cost:.1f}.")
    caps = [overtime_cap(c) for c in capacities]
    team = ", ".join(
        f"{role} {c} (up to {cap})" for role, c, cap in zip(roles, capacities, caps, strict=True)
    )
    lines.append(
        f"Team, people per role (temporary workers OVERTIME may hire per role, at 1.5 times the "
        f"daily cost): {team}."
    )
    hired = [temp for temp in observation.temporary if temp.left is None]
    if hired:
        lines.append(
            "Temporary workers hired: "
            + ", ".join(f"{roles[temp.role]} until day {temp.until}" for temp in hired)
            + "."
        )
    lines += ["", "Most urgent activities (urgency = days of slack before the deadline):"]
    lines += _at_risk(observation, names, roles)
    lines += ["", *_people(observation, roles)]
    backlog = backlogs(observation, 2 * params.review_period)
    lines.append(
        f"Backlog of the next {2 * params.review_period} days (person-days of work due to start, "
        "per person of the role): "
        + ", ".join(f"{role} {value:.1f}" for role, value in zip(roles, backlog, strict=True))
        + "."
    )
    eligible = sorted(s.activity for s in single_substitutions(observation))
    lines.append(
        "Activities a SUBST can serve: "
        + (", ".join(str(j) for j in eligible) if eligible else "none")
        + "."
    )
    lines += ["", *_candidates(record)]
    return "\n".join(lines)


def _at_risk(
    observation: Observation, names: Mapping[int, str], roles: tuple[str, ...]
) -> list[str]:
    status = observation.status
    open_ = [j for j in names if status[j] in (UNSTARTED, RUNNING, PAUSED)]
    tau = urgencies(observation, open_)
    world = nominal_world(observation)
    lines: list[str] = []
    for j in sorted(open_, key=lambda j: (tau[j], j))[:AT_RISK]:
        duration, demands = nominal_activity(observation, j)
        crew = {k: r for k, r in enumerate(demands) if r}
        crew_text = ", ".join(f"{r} {plural(roles[k], r)}" for k, r in crew.items()) or "nobody"
        if status[j] == UNSTARTED:
            detail = f"not started, planned start day {observation.plan[j]}, {duration} days"
        else:
            unit = max(1, sum(demands))
            absent = sum(not observation.present[w] for w in observation.assigned[j])
            left = world.remaining[j] / unit
            detail = f"{status[j]}, about {left:.1f} days of work left"
            if absent:
                detail += f", {absent} of its crew absent"
        lines.append(f'- {j} "{names[j]}": {detail}; crew {crew_text}; urgency {tau[j]:.1f}')
    return lines or ["- none"]


def _people(observation: Observation, roles: tuple[str, ...]) -> list[str]:
    t = observation.day
    status, assigned, present = observation.status, observation.assigned, observation.present
    crew_of = {w: j for j, s in enumerate(status) if s in (RUNNING, PAUSED) for w in assigned[j]}
    absent: list[str] = []
    for w in range(len(observation.instance.workers)):
        if present[w]:
            continue
        start, bound = observation.absent_since[w], observation.announced[w]
        back = t + 1 if start is None or bound is None else start + max(bound, t - start + 1)
        where = f"in the crew of {crew_of[w]}" if w in crew_of else "idle"
        absent.append(
            f"{roles[observation.instance.workers[w].role]} {w} ({where}, back on day "
            f"{back} at the earliest)"
        )
    idle = [0] * len(roles)
    for w, role in enumerate(worker_roles(observation)):
        if present[w] and w not in crew_of:
            idle[role] += 1
    return [
        "Absent workers: " + ("; ".join(absent) if absent else "none") + ".",
        "Idle present workers: "
        + ", ".join(f"{role} {n}" for role, n in zip(roles, idle, strict=True))
        + ".",
    ]


def _candidates(record: DecisionRecord) -> list[str]:
    if not record.candidates:
        return ["Candidates already evaluated: only NOOP was valid."]
    lines = [
        "Candidates already evaluated on the same futures (P(on time) / expected tardiness in "
        "days / budget overrun / plan instability in days / approval level; * = the rule's "
        "choice, ~ = dropped early on fewer futures):"
    ]
    for c in record.candidates:
        mark = "*" if c.label == record.chosen else ("~" if c.dropped else " ")
        lines.append(
            f"{mark} {c.label}: {c.p_on_time:.2f} / {c.tardiness:.2f} / {c.overrun:.3f} / "
            f"{c.deviation:.2f} / {c.level}"
        )
    return lines
