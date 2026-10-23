"""The team calendar, the fictional team roster and activity names of the interpretation layer
(spec sections 1.1 and 10.1).

Day 0 is a Monday and every simulation day is a working day, Monday to Friday without holidays,
so day t is weekday t mod 5 of week t // 5. The roster gives every original worker a unique
name, a first name and an initial such as "Ada K.", drawn without replacement by a seeded
permutation; roles carry the IT names of spec section 1.1. Real activities are named by the
WP6a narrator's vocabulary; D3 activities get fresh names from the same vocabulary.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import numpy as np

from sentinel.model.instance import ProjectInstance
from sentinel.simulation.state import Observation
from sentinel.wbs.extract import normalise_name
from sentinel.wbs.narrate import VOCABULARY, activity_names

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
FIRST_NAMES = (
    "Ada",
    "Ben",
    "Chen",
    "Dana",
    "Emil",
    "Farah",
    "Gita",
    "Hugo",
    "Ines",
    "Jonas",
    "Kofi",
    "Lena",
    "Mateo",
    "Nora",
    "Omar",
    "Priya",
    "Quinn",
    "Rosa",
    "Sven",
    "Tara",
    "Umar",
    "Vera",
    "Wei",
    "Xavi",
    "Yara",
    "Zoe",
    "Aiko",
    "Bruno",
    "Carla",
    "Dmitri",
    "Elif",
    "Felix",
    "Grace",
    "Hamid",
    "Ivo",
    "Julia",
    "Kenji",
    "Lucia",
    "Malik",
    "Nadia",
    "Oskar",
    "Paula",
    "Rafael",
    "Sara",
    "Tomasz",
    "Uma",
    "Viktor",
    "Wanda",
    "Yusuf",
    "Zofia",
    "Amara",
    "Bogdan",
    "Chloe",
    "Diego",
    "Esra",
    "Filip",
    "Hana",
    "Igor",
    "Jana",
    "Kamal",
)
INITIALS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def weekday(day: int) -> int:
    """The weekday of a day, 0 (Monday) to 4 (Friday) (spec section 10.1)."""
    return day % 5


def weekday_name(day: int) -> str:
    return WEEKDAYS[weekday(day)]


def next_weekday(day: int, target: int) -> int:
    """The first day after `day` whose weekday is `target`: 1 to 5 days later (10.1)."""
    return day + (target - weekday(day) - 1) % 5 + 1


def next_week(day: int) -> int:
    """The Monday of the week after the week of `day` (spec section 10.1)."""
    return 5 * (day // 5 + 1)


@dataclass(frozen=True)
class Member:
    """A worker of the roster: its id, its unique name and its role."""

    worker: int
    name: str
    role: int


def roster(instance: ProjectInstance, seed: int) -> tuple[Member, ...]:
    """A unique name per original worker, in worker order: the combinations of FIRST_NAMES and
    INITIALS in a seeded random order."""
    total = len(FIRST_NAMES) * len(INITIALS)
    if len(instance.workers) > total:
        raise ValueError(f"the roster names {total} workers, got {len(instance.workers)}")
    order = np.random.default_rng(seed).permutation(total)
    members = []
    for worker, code in zip(instance.workers, order, strict=False):
        first, initial = divmod(int(code), len(INITIALS))
        members.append(Member(worker.id, f"{FIRST_NAMES[first]} {INITIALS[initial]}.", worker.role))
    return tuple(members)


def fresh_name(demands: tuple[int, ...], used: Iterable[str], rng: np.random.Generator) -> str:
    """A verb and object of the vocabulary of the dominant role of `demands` (most people, ties
    to the lower role; role 0 without demands) that no name in `used` has."""
    taken = {normalise_name(name) for name in used}
    role = max(range(len(demands)), key=lambda k: (demands[k], -k)) if any(demands) else 0
    verbs, objects = VOCABULARY[role]
    free = [f"{v} {o}" for o in objects for v in verbs if normalise_name(f"{v} {o}") not in taken]
    if not free:
        raise ValueError(f"the vocabulary of role {role} is exhausted")
    return free[int(rng.integers(len(free)))]


def names_of(observation: Observation, seed: int) -> dict[int, str]:
    """Names of the real activities of an observation: the narrator's names of the instance's
    activities (`activity_names` with `seed`) and fresh names for its D3 activities, drawn in
    id order from a stream of `seed`."""
    names = activity_names(observation.instance, seed)
    rng = np.random.default_rng([seed, 1])
    for inserted in observation.inserted:
        names[inserted.id] = fresh_name(inserted.demands, names.values(), rng)
    return names


def plural(role: str, count: int) -> str:
    """`role` in the plural if `count` is not 1."""
    return role if count == 1 else f"{role}s"


def describe_crew(demands: Mapping[int, int], roles: tuple[str, ...]) -> str:
    """People per role as text, e.g. "2 backend developers and 1 tester"."""
    parts = [f"{n} {plural(roles[k], n)}" for k, n in sorted(demands.items()) if n > 0]
    if not parts:
        return "nobody"
    return parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"
