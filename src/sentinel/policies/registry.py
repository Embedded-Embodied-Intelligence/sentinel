"""The policies compared in WP4 (spec section 7), by name."""

from sentinel.policies.always_substitute import AlwaysSubstitute
from sentinel.policies.base import Policy
from sentinel.policies.no_reaction import NoReaction
from sentinel.policies.resolve import T_CP, FullResolve, StableResolve

# "The five policies": NoReaction, AlwaysSubstitute, FullResolve(subst=False),
# FullResolve(subst=True) and StableResolve(subst=True).
COMPARED = (
    "no_reaction",
    "always_substitute",
    "full_resolve",
    "full_resolve_subst",
    "stable_resolve_subst",
)


def make_policy(name: str, *, deterministic_time_limit: float = T_CP, seed: int = 0) -> Policy:
    """A fresh policy by name; the CP-SAT settings apply to the re-solving ones (spec 7)."""
    limit = deterministic_time_limit
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
    raise ValueError(f"unknown policy {name!r}; known: {', '.join(COMPARED)}, stable_resolve")
