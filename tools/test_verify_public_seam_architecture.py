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
        self.assertTrue(all(item.command[:3] == ("uv", "run", "pytest") for item in plan))

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
