from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "tools" / "spec023_installed_wheel_tracer.py"


class Spec023TracerContractTests(unittest.TestCase):
    def test_admission_freezes_external_benchmark_boundaries(self) -> None:
        value = json.loads(
            (ROOT / "docs/architecture-admissions/spec-023.v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(value["canonical_owner"], "apex_research")
        self.assertEqual(value["upstream"]["adoption"], "methodology_and_task_definitions_only")
        self.assertFalse(value["upstream"]["runtime_dependency"])
        self.assertIn("all_declared_samples", value["fail_closed_behavior"])
        self.assertEqual(value["claims"], [])

    def test_tracer_is_bounded_nodeized_and_replayed(self) -> None:
        spec = importlib.util.spec_from_file_location("spec023_tracer", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self.assertEqual(module.TIMEOUT_SECONDS, 240)
        self.assertEqual(module.REPOSITORIES, (
            "strategy-workspace",
            "quant-runtime",
            "apex-research",
            "strategy-reporting",
        ))
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("for replay in (1, 2)", source)
        self.assertIn('"PYTHONPATH"', source)
        self.assertIn("adapter.execute_benchmark", source)
        self.assertIn("production_attested_oci", source)
        self.assertNotIn("git add .", source)


if __name__ == "__main__":
    unittest.main()
