"""Direct behavior test for the G0 execution-failure task."""

from __future__ import annotations

from .research_decision import RunContract


def test_an_execution_failure_is_terminal_and_never_reusable() -> None:
    run = RunContract.parse(
        {
            "package_id": "reference-package",
            "genome_id": "reference-genome",
            "parameter_digest": "sha256:" + "a" * 64,
            "data_snapshot_id": "reference-snapshot",
            "data_range": "2020-01-01/2020-12-31",
            "cost_environment": "declared-costs",
            "execution_environment": "formal-runtime",
            "randomness": {"seed_policy": "fixed", "seed_ref": "seed-1", "replicates": 1},
            "terminal_state": "failed",
        }
    )

    assert run.terminal_state == "failed"
    assert run.qualifies_for_reuse is False
