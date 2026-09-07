from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "tools" / "spec015_installed_wheel_tracer.py"
SPEC = importlib.util.spec_from_file_location(
    "spec015_installed_wheel_tracer", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
tracer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tracer)


class Spec015InstalledWheelTracerTests(unittest.TestCase):
    def test_historical_tracer_does_not_freeze_future_reporting_modules(self) -> None:
        self.assertEqual(
            set(tracer.UNCHANGED_SOURCE_BASELINES),
            {"quant-runtime", "strategy-workspace"},
        )
        self.assertIn(
            ("strategy-reporting", ("tests/test_workspace_roundtrip.py",)),
            tracer.INSTALLED_TESTS,
        )

    def test_cli_preserves_validated_replays_when_identity_comparison_fails(
        self,
    ) -> None:
        first = self._valid_transcript()
        second = self._valid_transcript()
        second[0]["identities"]["reservation_id"] = "f" * 64
        error = tracer.TracerFailure(
            "stable installed identity transcripts drifted",
            transcripts=[first, second],
        )
        captured = io.StringIO()
        with (
            patch.object(tracer, "build_and_run", side_effect=error),
            contextlib.redirect_stderr(captured),
        ):
            status = tracer.main(["--repository-root", str(ROOT)])
        self.assertEqual(status, 1)
        payload = json.loads(captured.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(
            payload["stable_identity_transcripts"],
            [
                tracer._validated_identity_transcript(first),
                tracer._validated_identity_transcript(second),
            ],
        )

    @staticmethod
    def _valid_transcript() -> list[dict[str, object]]:
        values = [f"{value:064x}" for value in range(1, 40)]
        return [
            {
                "label": "policy",
                "identities": {
                    "campaign_id": values[0],
                    "policy_id": values[1],
                    "reservation_id": values[2],
                    "settlement_id": values[3],
                },
            },
            {
                "label": "qualified-chain",
                "identities": {
                    "candidate_id": values[4],
                    "evidence_id": values[5],
                    "policy_id": values[1],
                    "decision_ids": values[6:11],
                    "decision_reservation_ids": values[11:16],
                    "decision_settlement_ids": values[16:21],
                    "terminal_state": "research_qualified",
                },
            },
            {
                "label": "held-successor-retirement",
                "identities": {
                    "candidate_id": values[4],
                    "policy_id": values[1],
                    "held_evaluation_id": values[21],
                    "held_reservation_id": values[22],
                    "held_settlement_id": values[23],
                    "revised_held_evaluation_id": values[24],
                    "revised_held_reservation_id": values[25],
                    "revised_held_settlement_id": values[26],
                    "decision_id": values[27],
                    "decision_reservation_id": values[28],
                    "decision_settlement_id": values[29],
                    "retirement_id": values[30],
                    "retirement_reservation_id": values[31],
                    "retirement_settlement_id": values[32],
                    "terminal_state": "retired",
                },
            },
        ]

    def test_transcript_requires_exact_labels_fields_and_identity_formats(self) -> None:
        transcript = self._valid_transcript()

        validated = tracer._validated_identity_transcript(transcript)

        self.assertEqual(
            [item["label"] for item in validated],
            ["held-successor-retirement", "policy", "qualified-chain"],
        )

    def test_transcript_rejects_extra_fields_short_ids_and_wrong_cardinality(
        self,
    ) -> None:
        for mutation in ("extra", "short-id", "short-chain"):
            transcript = self._valid_transcript()
            policy = transcript[0]["identities"]
            qualified = transcript[1]["identities"]
            assert isinstance(policy, dict) and isinstance(qualified, dict)
            if mutation == "extra":
                policy["authority"] = "forbidden"
            elif mutation == "short-id":
                policy["policy_id"] = "abc"
            else:
                qualified["decision_ids"] = [f"{value:064x}" for value in range(4)]
            with (
                self.subTest(mutation=mutation),
                self.assertRaises(tracer.TracerFailure),
            ):
                tracer._validated_identity_transcript(transcript)

    def test_transcript_preserves_independent_fixture_scopes(self) -> None:
        transcript = self._valid_transcript()
        qualified = transcript[1]["identities"]
        held = transcript[2]["identities"]
        assert isinstance(qualified, dict)
        assert isinstance(held, dict)
        qualified["policy_id"] = f"{90:064x}"
        held["policy_id"] = f"{91:064x}"
        held["candidate_id"] = f"{92:064x}"

        validated = tracer._validated_identity_transcript(transcript)

        self.assertEqual(validated[0]["identities"]["policy_id"], f"{91:064x}")
        self.assertEqual(validated[0]["identities"]["candidate_id"], f"{92:064x}")
        self.assertEqual(validated[2]["identities"]["policy_id"], f"{90:064x}")

    def test_transcript_rejects_colliding_identities(self) -> None:
        for mutation in (
            "domain-collision",
            "governance-collision",
        ):
            transcript = self._valid_transcript()
            policy = transcript[0]["identities"]
            qualified = transcript[1]["identities"]
            held = transcript[2]["identities"]
            assert isinstance(policy, dict)
            assert isinstance(qualified, dict)
            assert isinstance(held, dict)
            if mutation == "domain-collision":
                held["decision_id"] = qualified["evidence_id"]
            else:
                held["decision_settlement_id"] = policy["reservation_id"]
            with (
                self.subTest(mutation=mutation),
                self.assertRaises(tracer.TracerFailure),
            ):
                tracer._validated_identity_transcript(transcript)

    def test_snapshot_tree_identity_detects_added_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "source.py").write_text("VALUE = 1\n", encoding="utf-8")
            before = tracer._snapshot_tree_identity(root)
            (root / "generated.py").write_text("VALUE = 2\n", encoding="utf-8")

            self.assertNotEqual(before, tracer._snapshot_tree_identity(root))

    def test_snapshot_attestation_fails_after_a_test_mutates_the_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "quant-research"
            repository.mkdir()
            (repository / "tool.py").write_text("before\n", encoding="utf-8")
            expected = {"quant-research": tracer._snapshot_tree_identity(repository)}
            (repository / "created-by-test.py").write_text("after\n", encoding="utf-8")

            with self.assertRaisesRegex(
                tracer.TracerFailure, "snapshot mutated during installed tests"
            ):
                tracer._assert_snapshot_trees(
                    root,
                    {"quant-research": repository},
                    expected,
                    phase="installed tests",
                )


if __name__ == "__main__":
    unittest.main()
