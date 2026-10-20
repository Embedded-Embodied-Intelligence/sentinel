"""The simulator on downloaded PSPLIB J30 data; skipped when data/psplib is absent."""

from pathlib import Path

import pytest

from sentinel.data.psplib_loader import instance_path, list_instances, load_psplib
from sentinel.data.reference import load_reference, reference_path
from sentinel.experiments.runs import derive_seed
from sentinel.model import validate_schedule
from sentinel.policies.no_reaction import NoReaction
from sentinel.scheduling.priority_rules import lft_priorities
from sentinel.scheduling.sgs import serial_sgs
from sentinel.simulation.engine import simulate
from sentinel.simulation.events import DisruptionParams
from sentinel.simulation.realised import execution_violations, realised_instance
from sentinel.simulation.uncertainty import PertParams, derive_deadline

pytestmark = pytest.mark.data

DEFAULTS = DisruptionParams(lambda_a=0.01, mean_absence=3, lambda_s=0.01, lambda_n=0.02)


def test_default_disruptions_on_30_j30_instances(psplib_root: Path) -> None:
    if not reference_path("j30", "opt", psplib_root).is_file():
        pytest.skip("j30_opt.sm missing; run scripts/fetch_psplib.py")
    optima = load_reference("j30", "opt", psplib_root)
    stems = list_instances("j30", psplib_root)[::16]  # 30 instances over all parameter groups
    assert len(stems) == 30
    for stem in stems:
        inst = load_psplib(instance_path("j30", stem, psplib_root))
        plan = serial_sgs(inst, lft_priorities(inst), lower_is_better=True)
        deadline = derive_deadline(optima[inst.name], 0.1)
        for replication in range(5):
            seed = derive_seed(2026, "j30", stem, str(replication))
            result = simulate(
                inst,
                plan,
                NoReaction(),
                seed,
                pert=PertParams(),
                disruptions=DEFAULTS,
                deadline=deadline,
            )
            assert not result.truncated, (stem, seed)
            realised, schedule = realised_instance(inst, result)
            assert validate_schedule(realised, schedule) == [], (stem, seed)
            assert execution_violations(inst, result) == [], (stem, seed)
            planned = plan.starts
            assert all(result.starts[j] >= planned[j] for j in range(inst.n_activities))  # type: ignore[operator]
