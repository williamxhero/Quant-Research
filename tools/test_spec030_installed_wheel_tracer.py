from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "tools" / "spec030_installed_wheel_tracer.py"


class Spec030TracerContractTests(unittest.TestCase):
    def test_tracer_is_bounded_nodeized_replayed_and_wheel_only(self) -> None:
        spec = importlib.util.spec_from_file_location("spec030_tracer", SCRIPT)
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
        self.assertIn("run_installed_pytest", source)
        self.assertIn("candidate-discovery.v1", source)
        self.assertNotIn("git add .", source)


if __name__ == "__main__":
    unittest.main()
