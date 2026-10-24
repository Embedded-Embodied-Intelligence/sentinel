"""Simulator projects (WP9a; spec section 11.6): advancing day by day is deterministic for the
seed and gives the run of `simulate` with the same plan, policy and seed."""

from datetime import date
from pathlib import Path

import pytest

from sentinel.app.simulator import (
    PolicyRun,
    Simulation,
    SimulatorSpec,
    World,
    build_world,
    policy_of,
    simulator_view,
)
from sentinel.model import ProjectInstance
from sentinel.simulation.baselines import SgsLft, compute_baseline
from sentinel.simulation.engine import simulate
from sentinel.simulation.uncertainty import derive_budget

START = date(2026, 11, 2)


def tiny_world(tiny: ProjectInstance, policy: str, autonomy: int = 2) -> World:
    """The tiny fixture as a simulator world (the PSPLIB sets need the downloaded data)."""
    spec = SimulatorSpec(
        instance="j301_1", start=START, policy=policy, autonomy=autonomy, disruptions="turbulent"
    )
    plan = compute_baseline(tiny, SgsLft())
    return World(
        spec=spec,
        instance=tiny,
        plan=plan,
        c_star=plan.makespan,
        reference=None,
        deadline=plan.makespan + 1,
        budget=derive_budget(tiny, 0.1, params=spec.pert),
        roles=("backend developer",),
        people=("Ada K.", "Ben L.", "Chen M."),
    )


def reference(world: World, policy: str):  # type: ignore[no-untyped-def]
    spec = world.spec
    return simulate(
        world.instance,
        world.plan.schedule,
        policy_of(spec, policy),
        spec.seed,
        pert=spec.pert,
        disruptions=spec.disruption_params,
        deadline=world.deadline,
        review_period=5,
        budget=world.budget,
    )


@pytest.mark.parametrize("policy", ["sentinel", "no_reaction", "always_substitute"])
def test_advancing_in_steps_gives_the_run_of_simulate(tiny: ProjectInstance, policy: str) -> None:
    world = tiny_world(tiny, policy)
    run = PolicyRun(world, policy)
    for days in (1, 1, 2, 3, 1000):  # single days and longer steps
        run.advance(days)
    assert run.finished
    assert run.result().model_dump() == reference(world, policy).model_dump()


def test_the_comparison_runs_noreaction_on_the_same_world(tiny: ProjectInstance) -> None:
    simulation = Simulation(tiny_world(tiny, "sentinel", autonomy=3))
    moved = simulation.advance(2)
    view = simulator_view("p", 2, simulation)
    assert moved == 2 and view.days == 2 and view.as_of == date(2026, 11, 4)
    assert view.compare is not None and view.compare.policy == "no_reaction"
    assert [t.name for t in view.main.tasks] == [t.name for t in view.compare.tasks]
    while not simulation.finished:
        simulation.advance(5)
    view = simulator_view("p", 3, simulation)
    assert view.main.makespan is not None and view.main.finish is not None
    assert view.compare is not None
    assert view.compare.makespan == reference(simulation.world, "no_reaction").makespan


@pytest.mark.data
@pytest.mark.slow  # under 2 s, kept out of the 75 s default run
def test_a_j30_world_matches_its_study_seed(psplib_root: Path) -> None:
    spec = SimulatorSpec(instance="j301_1", start=START, policy="full_resolve_subst", scenario=1)
    world = build_world(spec, psplib_root, Path("data/derived/baselines"))
    assert world.reference == "opt" and world.c_star == 43
    run = PolicyRun(world, spec.policy)
    run.advance(10_000)
    assert run.result().model_dump() == reference(world, spec.policy).model_dump()


@pytest.mark.data
@pytest.mark.slow
def test_sentinel_on_a_j30_world_matches_simulate(psplib_root: Path) -> None:
    spec = SimulatorSpec(instance="j301_1", start=START, policy="sentinel", scenario=1)
    world = build_world(spec, psplib_root, Path("data/derived/baselines"))
    run = PolicyRun(world, "sentinel")
    for _ in range(100):
        run.advance(10)
    assert run.finished
    assert run.result().model_dump() == reference(world, "sentinel").model_dump()
