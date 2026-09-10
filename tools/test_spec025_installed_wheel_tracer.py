from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "tools" / "spec025_installed_wheel_tracer.py"
VERIFIER = ROOT / "tools" / "verify_public_seam_architecture.py"
VERIFIER_SPEC = importlib.util.spec_from_file_location("spec025_verifier", VERIFIER)
assert VERIFIER_SPEC is not None and VERIFIER_SPEC.loader is not None
verifier = importlib.util.module_from_spec(VERIFIER_SPEC)
VERIFIER_SPEC.loader.exec_module(verifier)


class Spec025TracerContractTests(unittest.TestCase):
    def test_acceptance_scope_freezes_impact_only_execution(self) -> None:
        scope = json.loads(
            (ROOT / "docs/architecture-admissions/spec-025.acceptance-scope.v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(scope["spec"], "SPEC-025")
        self.assertEqual(scope["required_installed_tracers"], ["SPEC-025"])
        self.assertIn("SPEC-015", scope["deferred_release_tracers"])
        loaded = verifier.load_acceptance_scope(
            ROOT / "docs/architecture-admissions/spec-025.acceptance-scope.v1.json"
        )
        self.assertEqual(loaded.spec, "SPEC-025")

    def test_tracer_is_bounded_installed_only_and_never_executes_benchmarks(self) -> None:
        spec = importlib.util.spec_from_file_location("spec025_tracer", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self.assertEqual(module.TIMEOUT_SECONDS, 240)
        self.assertEqual(module.TEST, "tests/test_regression_gate.py")
        help_result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(help_result.returncode, 0)
        self.assertIn("--repository-root", help_result.stdout)
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("for replay in (1, 2)", source)
        self.assertIn('"PYTHONPATH"', source)
        self.assertIn('"-I"', source)
        for forbidden in (
            "execute_benchmark",
            "execute_sample",
            "QuantRuntimeAdapter",
            "MarketHub",
            "external_runner",
            "production_attested_oci",
        ):
            self.assertNotIn(forbidden, source)

    def test_admission_has_no_operational_or_research_truth_claim(self) -> None:
        value = json.loads(
            (ROOT / "docs/architecture-admissions/spec-025.v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(value["canonical_owner"], "apex_research")
        self.assertEqual(value["claims"], [])
        self.assertIn("benchmark governance", value["evidence_level"])
        self.assertIn("zero benchmark execution", value["fail_closed_behavior"])

    def test_architecture_guard_rejects_execution_from_the_regression_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "apex-research" / "src" / "apex_research"
            package.mkdir(parents=True)
            module = package / "regression_gate.py"
            module.write_text(
                "\n".join(
                    (
                        "from apex_research.benchmark import FactorResearchBenchmarkService",
                        "from apex_research.strategy_benchmark import StrategyBenchmarkService",
                        "from apex_research.workspace import WorkspaceClientProtocol",
                        "class RegressionGatePolicy: pass",
                        "class RegressionComparisonSnapshot: pass",
                        "class RegressionDecision: pass",
                        "class RegressionWaiver: pass",
                        "class AutomationDisposition: pass",
                        "class AIResearcherRegressionGateService: pass",
                    )
                ),
                encoding="utf-8",
            )
            (package / "cli.py").write_text(
                "def _regression_gate_command(args):\n    return {'status': 'ok'}\n",
                encoding="utf-8",
            )
            (package / "__init__.py").write_text(
                '__all__ = ["AIResearcherRegressionGateService"]\n',
                encoding="utf-8",
            )
            verifier._scan_spec025_regression_gate_seam(root, required=True)

            module.write_text(module.read_text(encoding="utf-8") + "\nimport subprocess\n")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "runner or benchmark execution"
            ):
                verifier._scan_spec025_regression_gate_seam(root, required=True)


if __name__ == "__main__":
    unittest.main()
