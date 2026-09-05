from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "tools" / "spec015_installed_wheel_tracer.py"
SPEC = importlib.util.spec_from_file_location(
    "spec015_installed_wheel_tracer", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
tracer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tracer)


class Spec015InstalledWheelTracerTests(unittest.TestCase):
    @staticmethod
    def _valid_transcript() -> list[dict[str, object]]:
        identities = (f"{value:064x}" for value in range(1, 13))
        values = list(identities)
        return [
            {
                "label": "policy",
                "identities": {"campaign_id": values[0], "policy_id": values[1]},
            },
            {
                "label": "qualified-chain",
                "identities": {
                    "candidate_id": values[2],
                    "evidence_id": values[3],
                    "policy_id": values[1],
                    "decision_ids": values[4:9],
                    "terminal_state": "research_qualified",
                },
            },
            {
                "label": "held-successor-retirement",
                "identities": {
                    "candidate_id": values[2],
                    "policy_id": values[1],
                    "held_evaluation_id": values[9],
                    "revised_held_evaluation_id": values[10],
                    "decision_id": values[4],
                    "retirement_id": values[11],
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


if __name__ == "__main__":
    unittest.main()
