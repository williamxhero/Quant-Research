from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "tools" / "verify_public_seam_architecture.py"
SPEC = importlib.util.spec_from_file_location("public_seam_verifier", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


class PublicSeamArchitectureTests(unittest.TestCase):
    def test_fixture_plan_uses_only_existing_public_module_seams(self) -> None:
        plan = verifier.fixture_plan(ROOT)
        self.assertEqual([item.owner for item in plan], [
            "strategy_workspace",
            "quant_runtime",
            "apex_research",
            "strategy_reporting",
        ])
        command_by_owner = {item.owner: item.command[:5] for item in plan}
        self.assertEqual(
            command_by_owner["strategy_workspace"],
            ("uv", "run", "--extra", "dev", "pytest"),
        )
        self.assertEqual(
            command_by_owner["quant_runtime"],
            ("uv", "run", "--extra", "dev", "pytest"),
        )
        self.assertEqual(
            command_by_owner["apex_research"],
            ("uv", "run", "--group", "dev", "pytest"),
        )
        self.assertEqual(
            command_by_owner["strategy_reporting"],
            ("uv", "run", "--extra", "dev", "pytest"),
        )
        workspace = next(item for item in plan if item.owner == "strategy_workspace")
        runtime = next(item for item in plan if item.owner == "quant_runtime")
        self.assertIn(
            "tests/test_schemas_and_package.py::test_preflight_request_requires_verified_data_semantics",
            workspace.command,
        )
        self.assertIn("tests/test_preflight.py", runtime.command)
        self.assertIn("tests/test_preflight_run_order.py", runtime.command)
        apex = next(item for item in plan if item.owner == "apex_research")
        self.assertIn(
            "tests/test_candidate_closure.py::test_semantic_deduplication_preserves_each_publication_lineage",
            apex.command,
        )

    def test_source_scan_rejects_private_cross_repository_access(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source_root = Path(temporary)
            source = source_root / "apex-research" / "src" / "apex_research"
            source.mkdir(parents=True)
            (source / "bad.py").write_text("from strategy_workspace.storage import secret\n")
            with self.assertRaisesRegex(verifier.ArchitectureViolation, "private Workspace access"):
                verifier.scan_sources(source_root)


if __name__ == "__main__":
    unittest.main()
