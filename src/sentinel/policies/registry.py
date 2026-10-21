"""The policies compared in WP4 (spec section 7) and the Sentinel variants (spec 6), by name."""

from sentinel.agent.params import SentinelParams
from sentinel.policies.always_substitute import AlwaysSubstitute
from sentinel.policies.base import Policy
from sentinel.policies.no_reaction import NoReaction
from sentinel.policies.resolve import T_CP, FullResolve, StableResolve
from sentinel.policies.sentinel import Sentinel

# "The five policies": NoReaction, AlwaysSubstitute, FullResolve(subst=False),
# FullResolve(subst=True) and StableResolve(subst=True).
COMPARED = (
    "no_reaction",
    "always_substitute",
    "full_resolve",
    "full_resolve_subst",
    "stable_resolve_subst",
)


# Sentinel with full autonomy (WP5a): the variants of `SentinelParams.variant`.
SENTINELS = ("sentinel_full", "sentinel_no_overtime", "sentinel_scalarised")


def make_policy(
    name: str,
    *,
    deterministic_time_limit: float = T_CP,
    seed: int = 0,
    run_seed: int = 0,
    sentinel: SentinelParams | None = None,
) -> Policy:
    """A fresh policy by name; the CP-SAT settings (`seed` is CP-SAT's) apply to the re-solving
    ones (spec 7) and to Sentinel, which also takes the run's seed and its other `sentinel`
    parameters (default: spec section 8)."""
    limit = deterministic_time_limit
    if name in SENTINELS:
        params = SentinelParams() if sentinel is None else sentinel
        update = {"variant": name.removeprefix("sentinel_"), "deterministic_time_limit": limit}
        return Sentinel(params.model_copy(update=update | {"cp_seed": seed}), seed=run_seed)
    match name:
        case "no_reaction":
            return NoReaction()
        case "always_substitute":
            return AlwaysSubstitute()
        case "full_resolve" | "full_resolve_subst":
            return FullResolve(name.endswith("_subst"), deterministic_time_limit=limit, seed=seed)
        case "stable_resolve" | "stable_resolve_subst":
            subst = name.endswith("_subst")
            return StableResolve(subst, deterministic_time_limit=limit, seed=seed)
    known = ", ".join((*COMPARED, "stable_resolve", *SENTINELS))
    raise ValueError(f"unknown policy {name!r}; known: {known}")
