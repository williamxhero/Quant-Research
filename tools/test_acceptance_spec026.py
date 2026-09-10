# ruff: noqa: E402
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantresearch_acceptance import AcceptanceSelector
from quantresearch_acceptance.local import _run

VERIFIER_PATH = ROOT / "tools" / "verify_public_seam_architecture.py"
VERIFIER_SPEC = importlib.util.spec_from_file_location("public_seam_verifier", VERIFIER_PATH)
assert VERIFIER_SPEC is not None and VERIFIER_SPEC.loader is not None
VERIFIER = importlib.util.module_from_spec(VERIFIER_SPEC)
VERIFIER_SPEC.loader.exec_module(VERIFIER)


class Spec026AcceptanceContractTests(unittest.TestCase):
    def test_windows_process_adapter_decodes_utf8_tool_output(self) -> None:
        output = _run(
            [
                sys.executable,
                "-c",
                "import os; os.write(1, '固定证据'.encode('utf-8'))",
            ],
            cwd=ROOT,
            timeout_seconds=10,
            environment={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )

        self.assertEqual(output, "固定证据")

    def test_tracer_counts_completed_l3_replays_from_resumable_evidence(self) -> None:
        tracer = _load(ROOT / "tools/spec026_installed_wheel_tracer.py", "spec026_resume")
        with tempfile.TemporaryDirectory() as temporary:
            events = Path(temporary) / "events.jsonl"
            events.write_text(
                "\n".join(
                    json.dumps(
                        {
                            "event": "step_finished",
                            "level": "L3",
                            "plan_identity": "plan-1",
                            "step_id": "l3-strategy-reporting-1",
                            "replay": replay,
                        },
                        sort_keys=True,
                    )
                    for replay in (1, 2)
                ),
                encoding="utf-8",
            )

            self.assertEqual(tracer._completed_l3_replays(events, "plan-1"), 2)

    def test_machine_admission_freezes_reporting_only_ownership(self) -> None:
        admission = json.loads(
            (ROOT / "docs/architecture-admissions/spec-026.v1.json").read_text(encoding="utf-8")
        )

        self.assertEqual(admission["canonical_owner"], "strategy_reporting")
        self.assertIn("CampaignReportSourceAdapter", admission["public_seam"])
        self.assertIn("presentation", admission["evidence_level"])
        self.assertIn("campaign graph", admission["fail_closed_behavior"])
        self.assertEqual(admission["claims"], [])
        self.assertEqual(admission["lifecycle_states"], [])

    def test_v2_scope_selects_named_wheel_nodes_and_freezes_unchanged_owners(self) -> None:
        scope = json.loads(
            (ROOT / "docs/architecture-admissions/spec-026.acceptance-scope.v2.json").read_text(
                encoding="utf-8"
            )
        )
        tracer = _load(ROOT / "tools/spec026_installed_wheel_tracer.py", "spec026_tracer")

        self.assertEqual(scope["schema"], "quant-research.acceptance-scope.v2")
        self.assertEqual(scope["spec"], "SPEC-026")
        self.assertEqual(
            tracer.UNCHANGED_SOURCE_BASELINES,
            {
                "apex-research": "4582fa6407366c56f4b31138dfdebf5da8c1e839",
                "quant-runtime": "9f513c02ce2e1180a2b8fe5c1ea96ff4592b4860",
                "strategy-workspace": "f5e186dc4a88a86e8df39d86daaba2844d08c44b",
            },
        )
        l3 = scope["levels"]["L3"]["commands"]
        self.assertEqual(len(l3), 1)
        self.assertEqual(l3[0]["owner"], "strategy-reporting")
        argv = l3[0]["argv"]
        self.assertIn("--pyargs", argv)
        for node in tracer.NODES:
            self.assertIn(node, argv)
        self.assertTrue(scope["levels"]["L4"]["commands"])
        self.assertTrue(scope["levels"]["L5"]["commands"])

        changed_sources = [
            {"path": path, "fingerprint": "sha256:" + "a" * 64}
            for path in sorted(scope["source_to_direct_tests"])
            if path.startswith("strategy-reporting/src/strategy_reporting/")
            or path
            in {
                ".gitignore",
                "docs/architecture-admissions/spec-026.v1.json",
                "docs/architecture-admissions/spec-026.acceptance-scope.v2.json",
                "src/quantresearch_acceptance/local.py",
                "src/quantresearch_acceptance/runner.py",
                "tools/spec026_installed_wheel_tracer.py",
                "tools/test_acceptance_cache_fixtures.py",
                "tools/test_acceptance_runner.py",
                "tools/test_acceptance_spec026.py",
                "tools/test_validate_architecture_constitution.py",
                "tools/test_verify_public_seam_architecture.py",
                "tools/verify_public_seam_architecture.py",
            }
        ]
        diff = {
            "schema": "quant-research.fixed-base-diff.v1",
            "fixed_bases": {owner: value["fixed_base"] for owner, value in scope["owners"].items()},
            "source_fingerprints": {
                owner: value["source_fingerprint"] for owner, value in scope["owners"].items()
            },
            "changed_sources": changed_sources,
        }
        plan = AcceptanceSelector().select(scope, diff, phase="spec")
        self.assertEqual(plan.levels, ("L0", "L1", "L2", "L3"))
        self.assertFalse(any(step.level in {"L4", "L5"} for step in plan.steps))
        self.assertEqual(sum(step.replay_count for step in plan.steps if step.level == "L3"), 2)
        self.assertEqual(
            {proof.owner for proof in plan.owner_proofs},
            {"apex-research", "quant-runtime", "strategy-workspace"},
        )

    def test_constitution_guard_requires_campaign_reporting_seams(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary,
            self.assertRaisesRegex(
                VERIFIER.ArchitectureViolation,
                "SPEC-026 public campaign reporting seams are incomplete",
            ),
        ):
            VERIFIER._scan_spec026_campaign_reporting_seams(Path(temporary), required=True)


def _load(path: Path, name: str):  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
