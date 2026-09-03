from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "tools" / "validate_architecture_constitution.py"
SPEC = importlib.util.spec_from_file_location("constitution_validator", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class ConstitutionValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = validator.read_json(ROOT / "docs" / "architecture-constitution.v1.json")

    def test_committed_policy_is_valid(self) -> None:
        validator.validate_policy(self.policy)

    def test_spec_001_campaign_admission_is_valid(self) -> None:
        candidate = validator.read_json(
            ROOT / "docs" / "architecture-admissions" / "spec-001.v1.json"
        )

        validator.validate_candidate(candidate, self.policy)
        self.assertEqual(candidate["canonical_owner"], "apex_research")
        self.assertEqual(candidate["public_seam"], "WorkspaceClient publication/query")

    def test_spec_004_preflight_admission_is_valid(self) -> None:
        candidate = validator.read_json(
            ROOT / "docs" / "architecture-admissions" / "spec-004.v1.json"
        )

        validator.validate_candidate(candidate, self.policy)
        self.assertEqual(candidate["canonical_owner"], "quant_runtime")
        self.assertEqual(candidate["public_seam"], "quant-runtime preflight / WorkspaceClient")

    def test_spec_011a_lineage_admission_is_valid(self) -> None:
        candidate = validator.read_json(
            ROOT / "docs" / "architecture-admissions" / "spec-011a.v1.json"
        )

        validator.validate_candidate(candidate, self.policy)
        self.assertEqual(candidate["canonical_owner"], "strategy_workspace")
        self.assertEqual(candidate["public_seam"], "WorkspaceClient lineage query")

    def test_future_spec_requires_all_machine_readable_declarations(self) -> None:
        with self.assertRaisesRegex(validator.ConstitutionError, "missing required declarations"):
            validator.validate_candidate({"canonical_owner": "quant_runtime"}, self.policy)

    def test_future_spec_rejects_parallel_formal_truth_and_production_lifecycle(self) -> None:
        candidate = {
            "canonical_owner": "quant_runtime",
            "public_seam": "quant-runtime-cli",
            "identity_impact": "none",
            "evidence_level": "formal",
            "fail_closed_behavior": "reject",
            "claims": ["alternate-formal-truth"],
            "lifecycle_states": ["live-trading"],
        }
        with self.assertRaisesRegex(validator.ConstitutionError, "forbidden claims"):
            validator.validate_candidate(candidate, self.policy)
        candidate["claims"] = []
        with self.assertRaisesRegex(validator.ConstitutionError, "forbidden lifecycle states"):
            validator.validate_candidate(candidate, self.policy)

    def test_cli_rejects_invalid_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            candidate = Path(temporary) / "candidate.json"
            candidate.write_text(json.dumps({"canonical_owner": "unknown"}), encoding="utf-8")
            self.assertEqual(validator.main(["--candidate", str(candidate)]), 1)


if __name__ == "__main__":
    unittest.main()
