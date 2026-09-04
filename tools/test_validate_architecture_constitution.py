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

    def test_spec_002_orchestrator_admission_is_valid(self) -> None:
        candidate = validator.read_json(
            ROOT / "docs" / "architecture-admissions" / "spec-002.v1.json"
        )

        validator.validate_candidate(candidate, self.policy)
        self.assertEqual(candidate["canonical_owner"], "apex_research")
        self.assertEqual(candidate["public_seam"], "ResearchOrchestrator / WorkspaceClient")
        self.assertEqual(
            candidate["lifecycle_states"],
            ["created", "running", "paused", "completed", "exhausted", "failed", "cancelled"],
        )
        self.assertIn("reconciliation_required blocker", candidate["fail_closed_behavior"])

    def test_spec_003_package_intake_admission_is_valid(self) -> None:
        candidate = validator.read_json(
            ROOT / "docs" / "architecture-admissions" / "spec-003.v1.json"
        )

        validator.validate_candidate(candidate, self.policy)
        self.assertEqual(candidate["canonical_owner"], "strategy_workspace")
        self.assertEqual(candidate["public_seam"], "WorkspaceClient package registration")
        self.assertIn("deterministic bundle", candidate["identity_impact"])
        self.assertIn("without execution", candidate["evidence_level"])

    def test_spec_004_preflight_admission_is_valid(self) -> None:
        candidate = validator.read_json(
            ROOT / "docs" / "architecture-admissions" / "spec-004.v1.json"
        )

        validator.validate_candidate(candidate, self.policy)
        self.assertEqual(candidate["canonical_owner"], "quant_runtime")
        self.assertEqual(candidate["public_seam"], "quant-runtime preflight / WorkspaceClient")

    def test_spec_005_sandbox_admission_is_valid(self) -> None:
        candidate = validator.read_json(
            ROOT / "docs" / "architecture-admissions" / "spec-005.v1.json"
        )

        validator.validate_candidate(candidate, self.policy)
        self.assertEqual(candidate["canonical_owner"], "quant_runtime")
        self.assertIn("behavioral-conformance", candidate["identity_impact"])
        self.assertIn("NautilusTrader", candidate["evidence_level"])

    def test_spec_006_governance_admission_is_valid(self) -> None:
        candidate = validator.read_json(
            ROOT / "docs" / "architecture-admissions" / "spec-006.v1.json"
        )

        validator.validate_candidate(candidate, self.policy)
        self.assertEqual(candidate["canonical_owner"], "apex_research")
        self.assertEqual(candidate["public_seam"], "WorkspaceClient publication/query")
        self.assertIn("reservation", candidate["identity_impact"])

    def test_spec_011a_lineage_admission_is_valid(self) -> None:
        candidate = validator.read_json(
            ROOT / "docs" / "architecture-admissions" / "spec-011a.v1.json"
        )

        validator.validate_candidate(candidate, self.policy)
        self.assertEqual(candidate["canonical_owner"], "strategy_workspace")
        self.assertEqual(candidate["public_seam"], "WorkspaceClient lineage query")

    def test_spec_028_candidate_ir_admission_is_valid(self) -> None:
        candidate = validator.read_json(
            ROOT / "docs" / "architecture-admissions" / "spec-028.v1.json"
        )

        validator.validate_candidate(candidate, self.policy)
        self.assertEqual(candidate["canonical_owner"], "apex_research")
        self.assertEqual(candidate["public_seam"], "WorkspaceClient publication/query")
        self.assertIn("semantic identity", candidate["identity_impact"])

    def test_spec_029_external_runner_admission_is_valid(self) -> None:
        candidate = validator.read_json(
            ROOT / "docs" / "architecture-admissions" / "spec-029.v1.json"
        )

        validator.validate_candidate(candidate, self.policy)
        self.assertEqual(candidate["canonical_owner"], "apex_research")
        self.assertEqual(candidate["public_seam"], "ExternalResearchRunner / WorkspaceClient")
        self.assertIn("runner policy", candidate["identity_impact"])
        self.assertIn("zero launch", candidate["fail_closed_behavior"])

    def test_spec_007_research_engine_port_admission_is_valid(self) -> None:
        candidate = validator.read_json(
            ROOT / "docs" / "architecture-admissions" / "spec-007.v1.json"
        )

        validator.validate_candidate(candidate, self.policy)
        self.assertEqual(candidate["canonical_owner"], "apex_research")
        self.assertIn("ResearchEnginePort", candidate["public_seam"])
        self.assertIn("budget ceiling", candidate["identity_impact"])
        self.assertIn("unpublished", candidate["evidence_level"])
        self.assertIn("partial", candidate["fail_closed_behavior"])

    def test_spec_009_candidate_gate_admission_is_valid(self) -> None:
        candidate = validator.read_json(
            ROOT / "docs" / "architecture-admissions" / "spec-009.v1.json"
        )

        validator.validate_candidate(candidate, self.policy)
        self.assertEqual(candidate["canonical_owner"], "apex_research")
        self.assertIn("CandidateGate", candidate["public_seam"])
        self.assertIn("not formal", candidate["evidence_level"])
        self.assertIn("fail closed", candidate["fail_closed_behavior"])
        self.assertEqual(
            candidate["stage_owners"],
            {
                "policy_orchestration_assessment": "apex_research",
                "package_artifact_lineage": "strategy_workspace",
                "preflight_sandbox_execution": "quant_runtime",
                "formal_semantic_truth": "quant_runtime",
                "presentation": "strategy_reporting",
            },
        )
        self.assertEqual(
            set(candidate["forbidden_additions"]),
            {
                "candidate-schema",
                "sandbox-or-backtester",
                "governance-ledger",
                "lifecycle",
                "artifact-or-evidence-truth",
                "private-cross-repository-access",
                "adapter-gate-bypass",
                "formal-or-qualification-masquerade",
            },
        )
        self.assertIn("spec-003-package-intake", candidate["compatibility"])
        self.assertIn("spec-029-external-runner", candidate["compatibility"])
        self.assertEqual(candidate["claims"], [])
        self.assertEqual(candidate["lifecycle_states"], [])

    def test_spec_008_rdagent_adapter_admission_is_valid(self) -> None:
        candidate = validator.read_json(
            ROOT / "docs" / "architecture-admissions" / "spec-008.v1.json"
        )

        validator.validate_candidate(candidate, self.policy)
        self.assertEqual(candidate["canonical_owner"], "apex_research")
        self.assertIn("ResearchEnginePort", candidate["public_seam"])
        self.assertIn("ExternalResearchRunner", candidate["public_seam"])
        self.assertIn("discovery-only", candidate["evidence_level"])
        self.assertIn("zero launch", candidate["fail_closed_behavior"])
        self.assertEqual(candidate["native_capabilities"], ["factor", "model"])
        self.assertEqual(candidate["conditional_capabilities"], ["strategy"])
        self.assertIn("fin_quant", candidate["forbidden_operations"])
        self.assertEqual(candidate["claims"], [])
        self.assertEqual(candidate["lifecycle_states"], [])

    def test_spec_010_focused_research_admission_is_valid(self) -> None:
        candidate = validator.read_json(
            ROOT / "docs" / "architecture-admissions" / "spec-010.v1.json"
        )

        validator.validate_candidate(candidate, self.policy)
        self.assertEqual(candidate["canonical_owner"], "apex_research")
        self.assertIn("ResearchOrchestrator", candidate["public_seam"])
        self.assertIn("CandidateGate", candidate["public_seam"])
        self.assertIn("focused policy", candidate["evidence_level"])
        self.assertIn("reconciliation_required", candidate["fail_closed_behavior"])
        self.assertIn("factor-model-static-only", candidate["compatibility"])
        self.assertEqual(candidate["claims"], [])
        self.assertEqual(candidate["lifecycle_states"], [])

    def test_spec_011_research_memory_admission_is_valid(self) -> None:
        candidate = validator.read_json(
            ROOT / "docs" / "architecture-admissions" / "spec-011.v1.json"
        )

        validator.validate_candidate(candidate, self.policy)
        self.assertEqual(candidate["canonical_owner"], "apex_research")
        self.assertIn("WorkspaceClient", candidate["public_seam"])
        self.assertIn("ResearchEnginePort", candidate["public_seam"])
        self.assertIn("ResearchOrchestrator", candidate["public_seam"])
        self.assertIn("meaning-bearing", candidate["identity_impact"])
        self.assertIn("reconciliation_required", candidate["fail_closed_behavior"])
        self.assertEqual(candidate["claims"], [])
        self.assertEqual(candidate["lifecycle_states"], [])

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
