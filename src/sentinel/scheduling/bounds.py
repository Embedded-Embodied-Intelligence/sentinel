"""Critical-path bounds of spec section 1.4, resources ignored (CPM; Kelley & Walker 1959)."""

from sentinel.model.instance import ProjectInstance


def earliest_starts(instance: ProjectInstance) -> tuple[int, ...]:
    """Earliest start times ES_j by a forward pass in topological order (Kelley & Walker 1959)."""
    es = [0] * instance.n_activities
    for j in instance.topological_order():
        finish_j = es[j] + instance.activities[j].duration
        for succ in instance.activities[j].successors:
            es[succ] = max(es[succ], finish_j)
    return tuple(es)


def critical_path_lower_bound(instance: ProjectInstance) -> int:
    """LB0: longest source-to-sink path with weights p_j, i.e. ES of the sink (p_{n+1} = 0)."""
    return earliest_starts(instance)[instance.sink_id]


def latest_finishes(instance: ProjectInstance, horizon: int | None = None) -> tuple[int, ...]:
    """Latest finish times LF_j by a backward pass from horizon T = LB0 (Kelley & Walker 1959).

    A horizon below LB0 is allowed and yields negative slack for critical activities.
    """
    t_end = critical_path_lower_bound(instance) if horizon is None else horizon
    lf = [t_end] * instance.n_activities
    for j in reversed(instance.topological_order()):
        for succ in instance.activities[j].successors:
            lf[j] = min(lf[j], lf[succ] - instance.activities[succ].duration)
    return tuple(lf)


def latest_starts(instance: ProjectInstance, horizon: int | None = None) -> tuple[int, ...]:
    """Latest start times LS_j = LF_j - p_j for horizon T, default LB0 (Kelley & Walker 1959)."""
    lf = latest_finishes(instance, horizon)
    return tuple(f - act.duration for f, act in zip(lf, instance.activities, strict=True))
