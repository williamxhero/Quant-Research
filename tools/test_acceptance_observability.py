# ruff: noqa: E402
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantresearch_acceptance import (
    AcceptanceFailure,
    AcceptanceSelector,
    SubprocessProcess,
    audit_performance,
    historical_timeout,
)
from tools.test_acceptance_selector import diff_literal, scope_literal


class AcceptanceObservabilityContractTests(unittest.TestCase):
    def test_p95_timeout_uses_bounded_margin_and_level_clamp(self) -> None:
        self.assertEqual(
            historical_timeout([1, 2, 3, 10], budget_seconds=60),
            15,
        )
        self.assertEqual(
            historical_timeout([1000, 1100, 1200], budget_seconds=600),
            600,
        )
        for samples in ([], [0, 1], [float("nan")]):
            with self.subTest(samples=samples), self.assertRaises(AcceptanceFailure):
                historical_timeout(samples, budget_seconds=60)

        plan = AcceptanceSelector().select(scope_literal(), diff_literal(), phase="spec")
        self.assertEqual([step.timeout_seconds for step in plan.steps], [15, 38, 69, 60])
        self.assertTrue(
            all(
                "--junitxml=" in " ".join(step.argv) for step in plan.steps if "pytest" in step.argv
            )
        )

    def test_slow_tests_and_files_require_marker_and_explanation(self) -> None:
        valid = [
            {
                "nodeid": "tests/test_fast.py::test_fast",
                "duration_seconds": 1.5,
                "file_duration_seconds": 20,
                "markers": [],
                "explanation": "",
            },
            {
                "nodeid": "tests/test_slow.py::test_deliberate",
                "duration_seconds": 2.1,
                "file_duration_seconds": 61,
                "markers": ["slow"],
                "explanation": "deterministic two-pass replay",
            },
        ]
        self.assertEqual(audit_performance(valid), ())
        for field in ("markers", "explanation"):
            invalid = [dict(valid[1])]
            invalid[0][field] = [] if field == "markers" else ""
            with self.subTest(field=field), self.assertRaises(AcceptanceFailure):
                audit_performance(invalid)

    def test_process_reports_current_test_and_bounded_cpu_io_samples(self) -> None:
        events: list[dict[str, object]] = []
        result = SubprocessProcess(sample_interval_seconds=0.01, max_samples=4).run(
            (
                sys.executable,
                "-c",
                "import time; print('tools/test_demo.py::test_live PASSED', "
                "flush=True); time.sleep(.06)",
            ),
            cwd=ROOT,
            environment={},
            timeout_seconds=2,
            on_event=events.append,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("tools/test_demo.py::test_live", result.current_tests)
        self.assertGreaterEqual(len(result.resource_samples), 1)
        self.assertLessEqual(len(result.resource_samples), 4)
        self.assertTrue(
            all(
                {"cpu_seconds", "read_bytes", "write_bytes"} <= set(sample)
                for sample in result.resource_samples
            )
        )
        self.assertIn("current_test", {event["event"] for event in events})
        self.assertIn("resource_sample", {event["event"] for event in events})


if __name__ == "__main__":
    unittest.main()
