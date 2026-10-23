"""Decision states of RQ5 (WP6b): recording, reproduction, storage and the stratified sample."""

from collections.abc import Callable
from pathlib import Path

import pytest
from test_sentinel import LIVELY, SMALL, lft_plan, random_instance

from sentinel.experiments.decision_states import (
    INDEX_FILE,
    IndexRow,
    World,
    index_rows,
    load_states,
    progress,
    read_states,
    record_run,
    redeliberate,
    same_record,
    stratified_sample,
    write_index,
    write_states,
)
from sentinel.model import ProjectInstance
from sentinel.simulation.uncertainty import PertParams, derive_budget

Builder = Callable[..., ProjectInstance]


@pytest.fixture
def recorded(build: Builder) -> tuple[ProjectInstance, list]:  # type: ignore[type-arg]
    instance = random_instance(build, 103)
    world = World("test", "test", 0.05, 0, 0, 27, derive_budget(instance, 0.1))
    result, states = record_run(
        instance,
        lft_plan(instance),
        world,
        SMALL,
        pert=PertParams(),
        disruptions=LIVELY,
        review_period=5,
    )
    assert not result.truncated
    return instance, states


def test_recorded_states_reproduce_exactly_and_survive_storage(
    recorded: tuple[ProjectInstance, list],  # type: ignore[type-arg]
    tmp_path: Path,
) -> None:
    """The recorder keeps the gated deliberations, each reproduced exactly from its observation
    and the run's seed (not with other parameters), and stored states load back by id."""
    _, states = recorded
    assert states and all(not s.record.needs.met for s in states)
    assert len({s.id for s in states}) == len(states)
    for state in states[:: max(1, len(states) // 3)]:
        assert same_record(redeliberate(state, SMALL), state.record)
    other = SMALL.model_copy(update={"n_rollouts": 12, "n_stage1": 6})
    assert not all(same_record(redeliberate(s, other), s.record) for s in states[:3])
    write_states(tmp_path / "test" / "run.jsonl.gz", states)
    write_index(tmp_path / INDEX_FILE, index_rows(states, "test/run.jsonl.gz"))
    assert read_states(tmp_path / "test" / "run.jsonl.gz") == states
    wanted = [states[-1].id, states[0].id]
    assert [s.id for s in load_states(tmp_path, wanted)] == wanted
    with pytest.raises(KeyError):
        load_states(tmp_path, ["missing"])
    assert 0.0 <= min(s.progress for s in states) <= max(s.progress for s in states) <= 1.0
    assert progress(states[0].observation) == states[0].progress


def test_the_sample_is_stratified_seeded_and_spreads_small_strata() -> None:
    rows = [
        IndexRow(f"s{la}/{i}", la, i / 300, i % 7 != 0, "f")
        for la in (0.01, 0.02)
        for i in range(300)
    ]
    sample = stratified_sample(rows, 150, 1)
    assert len(sample) == len(set(sample)) == 150
    assert sample == stratified_sample(rows, 150, 1) != stratified_sample(rows, 150, 2)
    by_id = {row.id: row for row in rows}
    actions = [s for s in sample if not by_id[s].noop]
    assert len(actions) == 6 * 12 + 3  # equal shares of 12-13 for the 12 strata, remainders first
    few = [*rows[:290], *(IndexRow(f"x{i}", 0.03, 0.9, False, "f") for i in range(3))]
    small = stratified_sample(few, 60, 1)
    assert len(small) == 60 and {f"x{i}" for i in range(3)} <= set(small)
