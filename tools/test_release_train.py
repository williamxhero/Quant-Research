# ruff: noqa: E402
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantresearch_acceptance import AcceptanceFailure, ReleaseTrain

SPECS = tuple(f"SPEC-{number:03d}" for number in range(1, 33))


class ReleaseTrainContractTests(unittest.TestCase):
    def test_32_spec_train_schedules_incremental_batches_and_one_final_gate(self) -> None:
        train = ReleaseTrain(SPECS, batch_size=6)
        medium_after: list[int] = []
        final_gates: tuple[str, ...] = ()

        for number, spec in enumerate(SPECS, start=1):
            gates = train.record(spec, "sha256:" + f"{number:064x}")
            self.assertEqual(gates[0].kind, "incremental")
            self.assertEqual(gates[0].spec, spec)
            if any(gate.kind == "medium-integration" for gate in gates):
                medium_after.append(number)
            if number == 32:
                final_gates = tuple(gate.kind for gate in gates)

        self.assertEqual(medium_after, [6, 12, 18, 24, 30])
        self.assertEqual(
            final_gates,
            ("incremental", "owner-full-regression", "environment-status"),
        )
        self.assertTrue(train.complete)

    def test_resume_is_idempotent_and_evidence_references_are_immutable(self) -> None:
        train = ReleaseTrain(
            SPECS,
            batch_size=6,
            connected_impacts={"SPEC-002": ("quant-runtime",)},
        )
        first = train.record("SPEC-001", "sha256:" + "1" * 64)
        self.assertEqual(train.record("SPEC-001", "sha256:" + "1" * 64), first)
        with self.assertRaises(AcceptanceFailure):
            train.record("SPEC-001", "sha256:" + "2" * 64)
        impacted = train.record("SPEC-002", "sha256:" + "3" * 64)
        environment_gate = next(gate for gate in impacted if gate.kind == "environment-status")
        self.assertTrue(environment_gate.independent)
        self.assertEqual(environment_gate.owners, ("quant-runtime",))

        restored = ReleaseTrain.restore(copy.deepcopy(train.snapshot()))
        self.assertEqual(restored.snapshot(), train.snapshot())
        self.assertEqual(restored.record("SPEC-002", "sha256:" + "3" * 64), impacted)
        with self.assertRaises(AcceptanceFailure):
            restored.record("SPEC-004", "sha256:" + "4" * 64)

    def test_l5_outcomes_remain_independent_and_never_fallback(self) -> None:
        train = ReleaseTrain(
            SPECS,
            connected_impacts={"SPEC-001": ("quant-runtime",)},
        )
        gate = next(
            item
            for item in train.record("SPEC-001", "sha256:" + "a" * 64)
            if item.kind == "environment-status"
        )
        train.record_environment(
            gate.identity,
            status="failed",
            evidence_ref="sha256:" + "b" * 64,
        )

        self.assertEqual(train.environment_outcomes[0].status, "failed")
        self.assertTrue(train.environment_outcomes[0].independent)
        with self.assertRaises(AcceptanceFailure):
            train.record_environment(
                gate.identity,
                status="passed",
                evidence_ref="sha256:" + "c" * 64,
            )
        self.assertEqual(train.next_spec, "SPEC-002")


if __name__ == "__main__":
    unittest.main()
