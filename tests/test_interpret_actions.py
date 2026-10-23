"""Role 2 of the interpretation layer (spec section 10.3): the action grammar, its compilation
into candidates, duplicates, the random-proposal control and Sentinel with a proposer."""

from collections.abc import Callable, Sequence

import numpy as np
import pytest
from pydantic import ValidationError
from test_sentinel import (
    LIVELY,
    SMALL,
    assert_feasible,
    lft_plan,
    lively_observations,
    random_instance,
)

from sentinel.agent.candidates import Candidate, generate, single_substitutions
from sentinel.agent.decide import DecisionRecord
from sentinel.interpret.actions import (
    ActionIssue,
    Compiler,
    OvertimeOp,
    Proposal,
    ProposalAnswer,
    ReseqOp,
    ShiftOp,
    SubstOp,
    compile_proposal,
    proposal_text,
    random_proposals,
    read_proposals,
)
from sentinel.model import ProjectInstance
from sentinel.policies.base import Overtime, Reseq, Subst
from sentinel.policies.sentinel import Sentinel
from sentinel.simulation.engine import simulate
from sentinel.simulation.state import UNSTARTED, Observation, overtime_cap
from sentinel.simulation.uncertainty import PertParams
from sentinel.wbs.narrate import role_names

Builder = Callable[..., ProjectInstance]


@pytest.fixture
def observation(build: Builder) -> Observation:
    """An epoch observation with an eligible SUBST and a role that OVERTIME may hire for."""
    return next(o for o in lively_observations(build, count=3) if single_substitutions(o))


def proposal(*ops: ShiftOp | ReseqOp | SubstOp | OvertimeOp) -> Proposal:
    return Proposal(operations=ops)


def test_a_valid_proposal_compiles_with_its_plan_operation_last(observation: Observation) -> None:
    j = single_substitutions(observation)[0].activity
    role = role_names(observation.instance)[1]
    proposed = proposal(
        ReseqOp(op="RESEQ", objective="makespan"),
        SubstOp(op="SUBST", activity=j),
        OvertimeOp(op="OVERTIME", role=role.upper() + "S", workers=1, days=5),
    )
    candidate = compile_proposal(proposed, observation, SMALL, label="p")
    assert isinstance(candidate, Candidate), candidate
    kinds = [type(op) for op in candidate.decision.operations]
    assert kinds == [Subst, Overtime, Reseq]
    assert candidate.kind == "proposal_reseq_m" and candidate.level == 2
    assert candidate.substituted == len(single_substitutions(observation)[0].workers)
    assert proposal_text(proposed) == f"SUBST({j})+OT({role.upper()}S,1,5)+RESEQ-M"


def test_invalid_proposals_compile_to_issues(observation: Observation) -> None:
    roles = role_names(observation.instance)
    cap = overtime_cap(observation.instance.roles[1].capacity)
    j = single_substitutions(observation)[0].activity
    unstarted = next(k for k, s in enumerate(observation.status) if s == UNSTARTED and k)
    cases = {
        "unknown_role": proposal(OvertimeOp(op="OVERTIME", role="designer", workers=1, days=5)),
        "out_of_range": proposal(OvertimeOp(op="OVERTIME", role=roles[1], workers=cap + 1, days=5)),
        "unknown_activity": proposal(SubstOp(op="SUBST", activity=999)),
        "not_eligible": proposal(SubstOp(op="SUBST", activity=unstarted)),
        "two_plan_operations": proposal(
            ShiftOp(op="SHIFT"), ReseqOp(op="RESEQ", objective="stable")
        ),
        "repeated_operation": proposal(
            SubstOp(op="SUBST", activity=j), SubstOp(op="SUBST", activity=j)
        ),
    }
    for kind, case in cases.items():
        result = compile_proposal(case, observation, SMALL, label=kind)
        assert isinstance(result, ActionIssue) and result.kind == kind, (kind, result)
    days = proposal(OvertimeOp(op="OVERTIME", role=roles[1], workers=1, days=21))
    assert compile_proposal(days, observation, SMALL, label="d").kind == "out_of_range"  # type: ignore[union-attr]
    with pytest.raises(ValidationError):
        Proposal(operations=(ShiftOp(op="SHIFT"),) * 4)
    with pytest.raises(ValidationError):
        ProposalAnswer.model_validate({"proposals": [{"operations": [{"op": "SHIFT"}]}] * 4})


def test_duplicates_of_rule_candidates_and_earlier_proposals_are_flagged(
    observation: Observation,
) -> None:
    rule = generate(observation, params=SMALL).candidates
    compiler = Compiler(observation, rule, SMALL)
    labels = {c.label for c in rule}
    shift = compiler.compile(proposal(ShiftOp(op="SHIFT")), "a")
    assert shift.candidate is not None and shift.duplicate_of in labels and not shift.usable
    first = single_substitutions(observation)[0]
    subst = compiler.compile(proposal(SubstOp(op="SUBST", activity=first.activity)), "b")
    assert subst.duplicate_of == f"SUBST({first.activity})"
    role = role_names(observation.instance)[1]
    new = proposal(
        SubstOp(op="SUBST", activity=first.activity),
        OvertimeOp(op="OVERTIME", role=role, workers=1, days=3),
    )
    fresh = compiler.compile(new, "c")
    again = compiler.compile(new, "d")
    assert fresh.usable and again.duplicate_of == "c"


def test_answers_are_read_proposal_by_proposal() -> None:
    entries = read_proposals(
        {
            "proposals": [
                {"operations": [{"op": "SHIFT"}]},
                {"operations": [{"op": "TELEPORT"}]},
                {"operations": []},
                {"operations": [{"op": "RESEQ", "objective": "makespan"}]},
            ]
        }
    )
    kinds = [e.kind if isinstance(e, ActionIssue) else "ok" for e in entries]
    assert kinds == ["ok", "invalid_proposal", "invalid_proposal", "too_many_proposals"]
    assert read_proposals([])[0].kind == "invalid_answer"  # type: ignore[union-attr]


def test_the_random_sampler_is_deterministic_per_seed_and_stays_in_the_grammar(
    build: Builder,
) -> None:
    observations = lively_observations(build, count=2)[:6]
    for observation in observations:
        first = random_proposals(observation, np.random.default_rng(5))
        assert first == random_proposals(observation, np.random.default_rng(5))
        eligible = {s.activity for s in single_substitutions(observation)}
        for drawn in first:
            plans = [op for op in drawn.operations if isinstance(op, ShiftOp | ReseqOp)]
            assert 1 <= len(drawn.operations) <= 3 and len(plans) <= 1
            assert all(
                op.activity in eligible for op in drawn.operations if isinstance(op, SubstOp)
            )
    draws = {random_proposals(observations[0], np.random.default_rng(s)) for s in range(8)}
    assert len(draws) > 1


class RandomProposer:
    """A proposer for tests: the random control's proposals, compiled against the rule."""

    def __init__(self) -> None:
        self.calls = 0
        self.added: list[str] = []

    def __call__(
        self, observation: Observation, record: DecisionRecord, rule: Sequence[Candidate]
    ) -> Sequence[Candidate]:
        self.calls += 1
        assert record.chosen in {c.label for c in rule}
        compiler = Compiler(observation, rule, SMALL)
        rng = np.random.default_rng(observation.day)
        found = []
        for n, drawn in enumerate(random_proposals(observation, rng)):
            compiled = compiler.compile(drawn, f"r{observation.day}-{n}")
            if compiled.usable and compiled.candidate is not None:
                found.append(compiled.candidate)
        self.added += [c.label for c in found]
        return found


def test_sentinel_races_proposals_with_the_rule_candidates(build: Builder) -> None:
    instance = random_instance(build, 103)

    params = SMALL.model_copy(update={"n_rollouts": 6, "n_stage1": 3})

    def run(proposer: RandomProposer | None) -> tuple[object, Sentinel]:
        agent = Sentinel(params, seed=0, proposer=proposer)
        result = simulate(
            instance,
            lft_plan(instance),
            agent,
            0,
            pert=PertParams(),
            disruptions=LIVELY,
            deadline=27,
            debug=True,
        )
        assert_feasible(instance, result)
        return result, agent

    proposer = RandomProposer()
    _, agent = run(proposer)
    gated = agent.stats.deliberations - agent.stats.gate_exits
    assert proposer.calls == gated > 0 and agent.stats.proposed == len(proposer.added) > 0
    labels = {c.label for r in agent.records for c in r.candidates}
    assert set(proposer.added) <= labels
    plain, quiet = run(None)
    nothing, idle = run(_Empty())  # type: ignore[arg-type]
    assert nothing == plain
    timing = {"generation_s", "evaluation_s", "wall_time_s"}
    assert [r.model_dump(exclude=timing) for r in idle.records] == [
        r.model_dump(exclude=timing) for r in quiet.records
    ]


class _Empty:
    """A proposer that never proposes: Sentinel then decides as without one."""

    def __call__(
        self, observation: Observation, record: DecisionRecord, rule: Sequence[Candidate]
    ) -> Sequence[Candidate]:
        return ()
