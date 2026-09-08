from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import validate_architecture_constitution as validator
import verify_public_seam_architecture as verifier


class Spec026AAcceptanceTests(unittest.TestCase):
    def test_machine_admission_keeps_campaign_interpretation_in_apex(self) -> None:
        policy = validator.read_json(ROOT / "docs/architecture-constitution.v1.json")
        candidate = validator.read_json(
            ROOT / "docs/architecture-admissions/spec-026a.v1.json"
        )

        validator.validate_candidate(candidate, policy)
        self.assertEqual(candidate["canonical_owner"], "apex_research")
        self.assertIn("CampaignReportSourceService", candidate["public_seam"])
        self.assertIn("WorkspaceClient", candidate["public_seam"])
        self.assertIn("wall-clock", candidate["identity_impact"])
        self.assertIn("Reporting", candidate["evidence_level"])
        self.assertIn("fail closed", candidate["fail_closed_behavior"])
        self.assertEqual(candidate["claims"], [])
        self.assertEqual(candidate["lifecycle_states"], [])

    def test_acceptance_scope_freezes_owner_bounds_and_one_current_tracer(self) -> None:
        scope = verifier.load_acceptance_scope(
            ROOT / "docs/architecture-admissions/spec-026a.acceptance-scope.v1.json"
        )

        self.assertEqual(scope.spec, "SPEC-026A")
        self.assertEqual(scope.required_installed_tracers, ("SPEC-026A",))
        self.assertEqual(
            scope.baseline_heads["apex-research"],
            "30d88ebbc4ff8fb2ebafea5aa343b1fb4d25419d",
        )
        self.assertFalse(
            any(
                path.startswith(
                    (
                        "strategy-workspace/src/",
                        "quant-runtime/src/",
                        "strategy-reporting/src/",
                    )
                )
                for path in scope.product_changed_paths
            )
        )

    def test_installed_tracer_is_bounded_replayed_and_wheel_only(self) -> None:
        script = ROOT / "tools/spec026a_installed_wheel_tracer.py"
        module_spec = importlib.util.spec_from_file_location("spec026a_tracer", script)
        self.assertIsNotNone(module_spec)
        assert module_spec is not None and module_spec.loader is not None
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)

        self.assertEqual(module.TIMEOUT_SECONDS, 240)
        self.assertGreaterEqual(len(module.NODES), 8)
        self.assertEqual(module.REPLAYS, 2)
        source = script.read_text(encoding="utf-8")
        self.assertIn("run_installed_pytest", source)
        self.assertIn("source_roots", source)
        self.assertIn("sanitized_environment", source)
        self.assertNotIn("PYTHONPATH =", source)


if __name__ == "__main__":
    unittest.main()
