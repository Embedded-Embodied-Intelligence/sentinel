"""The names the application shows for its example projects in the user's language (spec
sections 11.2 and 11.6; WP9c answer 4): the showcase project of the demo, and the roles, people
and tasks of a simulator project, from a vocabulary file per language (`vocabulary/<lang>.toml`).

The simulator draws the names as the studies do (the research narrator and roster, WP6) with the
language's words; the English words are the narrator's, so the English names are the studies'.
"""

import tomllib
from functools import cache
from importlib import resources

from pydantic import BaseModel, ConfigDict

from sentinel.app.models import Language
from sentinel.interpret.team import names_of, roster
from sentinel.model.instance import ProjectInstance
from sentinel.simulation.state import Observation
from sentinel.wbs.narrate import Vocabulary


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ShowcaseNames(_Frozen):
    """The showcase project's name, its roles, people (by key) and tasks (by key)."""

    project: str
    roles: dict[str, str]
    people: dict[str, str]
    tasks: dict[str, str]


class TaskWords(_Frozen):
    """The verbs and objects of the task names of one role."""

    verbs: tuple[str, ...]
    objects: tuple[str, ...]


class SimulatorNames(_Frozen):
    """The simulator's role names (in role order), first names of the roster and task words
    per role."""

    roles: tuple[str, ...]
    first_names: tuple[str, ...]
    tasks: tuple[TaskWords, ...]

    @property
    def vocabulary(self) -> Vocabulary:
        return tuple((words.verbs, words.objects) for words in self.tasks)


class Names(_Frozen):
    showcase: ShowcaseNames
    simulator: SimulatorNames


@cache
def vocabulary(language: Language) -> Names:
    """The vocabulary file of a language."""
    text = (
        resources.files("sentinel.app")
        .joinpath(f"vocabulary/{language}.toml")
        .read_text(encoding="utf-8")
    )
    return Names.model_validate(tomllib.loads(text))


def role_names(instance: ProjectInstance, language: Language) -> tuple[str, ...]:
    """The role names of a simulator instance's roles R1..R|K| (at most four)."""
    roles = vocabulary(language).simulator.roles
    if len(instance.roles) > len(roles):
        raise ValueError(f"the vocabulary names {len(roles)} roles, got {len(instance.roles)}")
    return roles[: len(instance.roles)]


def people(instance: ProjectInstance, seed: int, language: Language) -> tuple[str, ...]:
    """The name of every original worker, in worker order (the roster of WP6 with the
    language's first names)."""
    first_names = vocabulary(language).simulator.first_names
    return tuple(member.name for member in roster(instance, seed, first_names))


def task_names(observation: Observation, seed: int, language: Language) -> dict[int, str]:
    """The names of the real activities of an observation, new ones included (`names_of` with
    the language's task words)."""
    return names_of(observation, seed, vocabulary(language).simulator.vocabulary)
