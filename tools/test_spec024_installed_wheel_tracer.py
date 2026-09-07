from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "tools" / "spec024_installed_wheel_tracer.py"
VERIFIER_SCRIPT = ROOT / "tools" / "verify_public_seam_architecture.py"


def _load_verifier():
    spec = importlib.util.spec_from_file_location("spec024_verifier", VERIFIER_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Spec024TracerContractTests(unittest.TestCase):
    def test_admission_freezes_strategy_benchmark_boundaries(self) -> None:
        value = json.loads(
            (ROOT / "docs/architecture-admissions/spec-024.v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(value["canonical_owner"], "apex_research")
        self.assertEqual(value["upstream"]["adoption"], "methodology_only")
        self.assertFalse(value["upstream"]["runtime_dependency"])
        self.assertFalse(value["upstream"]["redistributed_task_text"])
        self.assertIn("denominator", value["fail_closed_behavior"])
        self.assertEqual(value["claims"], [])

    def test_acceptance_records_final_wheel_only_and_external_status(self) -> None:
        value = json.loads(
            (ROOT / "docs/architecture-admissions/spec-024.acceptance.v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(value["spec"], "SPEC-024")
        self.assertEqual(value["installed_wheel_tracer"]["result"], "passed")
        self.assertEqual(value["installed_wheel_tracer"]["semantic_replays"], 2)
        self.assertEqual(value["installed_wheel_tracer"]["pythonpath"], "cleared")
        self.assertEqual(value["external_status"]["production_oci"], "blocked_unconfigured")
        self.assertEqual(value["external_status"]["connected_model"], "not_configured")
        self.assertFalse(value["external_status"]["fallback_used"])
        self.assertEqual(value["validation"]["standards_findings"], 0)
        self.assertEqual(value["validation"]["spec_findings"], 0)

    def test_tracer_is_bounded_nodeized_and_replayed(self) -> None:
        spec = importlib.util.spec_from_file_location("spec024_tracer", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self.assertEqual(module.TIMEOUT_SECONDS, 240)
        self.assertEqual(
            module.REPOSITORIES,
            (
                "strategy-workspace",
                "quant-runtime",
                "apex-research",
                "strategy-reporting",
            ),
        )
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("for replay in (1, 2)", source)
        self.assertIn('"PYTHONPATH"', source)
        self.assertIn("execute_strategy_benchmark", source)
        self.assertIn("strategy-benchmark", source)
        self.assertIn("production_attested_oci", source)
        self.assertNotIn("git add .", source)

    def test_guard_rejects_formal_submission_from_apex_benchmark(self) -> None:
        verifier = _load_verifier()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apex = root / "apex-research/src/apex_research"
            runtime = root / "quant-runtime/src/quant_runtime"
            apex.mkdir(parents=True)
            runtime.mkdir(parents=True)
            (apex / "strategy_benchmark.py").write_text(
                "class StrategyBenchmarkService:\n"
                "    def publish(self, workspace):\n"
                "        workspace.get_record('x')\n"
                "        workspace.verify_artifact('x')\n"
                "        workspace.publish_record({})\n"
                "        workspace.submit_run({})\n"
                "class StrategyBenchmarkSuite: pass\n"
                "class StrategyBenchmarkAggregate: pass\n",
                encoding="utf-8",
            )
            (runtime / "benchmark.py").write_text(
                "class BenchmarkExecutionService: pass\n"
                "WORKLOAD = \"strategy_event_trace\"\n"
                "PHASE = \"benchmark_strategy\"\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "formal submission"
            ):
                verifier._scan_spec024_strategy_benchmark_seams(root, required=True)


if __name__ == "__main__":
    unittest.main()
