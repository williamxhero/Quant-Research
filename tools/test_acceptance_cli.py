# ruff: noqa: E402
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantresearch_acceptance import (
    AcceptanceSelector,
    migrate_legacy_scope,
    validate_test001_admission,
)
from tools.test_acceptance_selector import diff_literal, scope_literal


class AcceptanceCliContractTests(unittest.TestCase):
    def test_select_cli_emits_the_same_canonical_plan_as_module(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scope = root / "scope.json"
            diff = root / "diff.json"
            scope.write_text(json.dumps(scope_literal()), encoding="utf-8")
            diff.write_text(json.dumps(diff_literal()), encoding="utf-8")
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(ROOT / "src")
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "quantresearch_acceptance",
                    "select",
                    "--scope",
                    str(scope),
                    "--diff",
                    str(diff),
                    "--phase",
                    "spec",
                ],
                cwd=root,
                env=environment,
                check=True,
                text=True,
                capture_output=True,
            )

        actual = json.loads(completed.stdout)
        expected = AcceptanceSelector().select(scope_literal(), diff_literal(), phase="spec")
        self.assertEqual(actual, expected.as_dict())

    def test_architecture_admission_and_scope_schema_are_machine_verified(self) -> None:
        admission = validate_test001_admission(
            ROOT / "docs/architecture-admissions/test-001.v1.json"
        )
        schema = json.loads(
            (ROOT / "docs/contracts/acceptance-scope.schema.v2.json").read_text(encoding="utf-8")
        )

        self.assertEqual(admission["canonical_owner"], "quant_research")
        self.assertIn("AcceptanceSelector", admission["public_seam"])
        self.assertEqual(schema["$id"], "quant-research.acceptance-scope.v2")
        self.assertFalse(schema["additionalProperties"])
        scope = json.loads(
            (ROOT / "docs/architecture-admissions/test-001.acceptance-scope.v2.json").read_text(
                encoding="utf-8"
            )
        )
        fixed_bases = {owner: config["fixed_base"] for owner, config in scope["owners"].items()}
        fingerprints = {
            owner: config["source_fingerprint"] for owner, config in scope["owners"].items()
        }
        plan = AcceptanceSelector().select(
            scope,
            {
                "schema": "quant-research.fixed-base-diff.v1",
                "fixed_bases": fixed_bases,
                "source_fingerprints": fingerprints,
                "changed_sources": [
                    {
                        "path": "src/quantresearch_acceptance/core.py",
                        "fingerprint": "sha256:" + "e" * 64,
                    }
                ],
            },
            phase="spec",
        )
        self.assertEqual(plan.levels, ("L0", "L1", "L2", "L3"))

    def test_spec026a_v1_migration_preserves_all_recorded_layers_and_tracers(self) -> None:
        legacy = json.loads(
            (ROOT / "docs/architecture-admissions/spec-026a.acceptance-scope.v1.json").read_text(
                encoding="utf-8"
            )
        )

        migration = migrate_legacy_scope(legacy)

        self.assertEqual(migration.schema, "quant-research.acceptance-scope-migration.v1")
        self.assertEqual(migration.source_schema, legacy["schema"])
        self.assertEqual(migration.spec, "SPEC-026A")
        self.assertEqual(
            set(migration.migrated_scope["levels"]), set(legacy["test_protocol"]["levels"])
        )
        self.assertEqual(
            migration.required_installed_tracers,
            tuple(legacy["required_installed_tracers"]),
        )
        self.assertEqual(len(migration.source_digest), 64)
        self.assertEqual(migration.source_document, legacy)
        self.assertEqual(
            migration.deferred_release_tracers,
            tuple(legacy["deferred_release_tracers"]),
        )

    def test_review_fix_selection_uses_only_the_new_impact_set(self) -> None:
        scope = scope_literal()
        scope["source_to_direct_tests"]["src/quantresearch_acceptance/runner.py"] = [
            "tools/test_acceptance_runner.py"
        ]
        scope["owners"]["quant-research"]["diff_prefixes"] = ["src/"]
        repair = diff_literal()
        repair["changed_sources"] = [
            {
                "path": "src/quantresearch_acceptance/runner.py",
                "fingerprint": "sha256:" + "d" * 64,
            }
        ]

        plan = AcceptanceSelector().select(scope, repair, phase="spec")

        self.assertEqual(
            {test for step in plan.steps for test in step.direct_tests},
            {"tools/test_acceptance_runner.py"},
        )


if __name__ == "__main__":
    unittest.main()
