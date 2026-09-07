from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
ADMISSIONS = ROOT / "docs" / "architecture-admissions"


class Spec021CompatibilityTests(unittest.TestCase):
    def test_pinned_upstream_manifest_records_real_install_and_removal(self) -> None:
        manifest = json.loads(
            (ADMISSIONS / "spec-021.upstream-manifest.v1.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(manifest["schema"], "quant-research.finsaber-upstream.v1")
        self.assertEqual(manifest["repository"], "https://github.com/waylonli/FINSABER")
        self.assertEqual(manifest["release_tag"], "v2.0.1")
        self.assertEqual(
            manifest["release_commit"],
            "4d3be1e0168224d678151eb7aee72bee3c7930d1",
        )
        self.assertEqual(
            manifest["pypi_wheel"]["sha256"],
            "ed2d1dcad2785daa1a89ab4bfc089f71d685e7fa7148466d3fdbba6f6fe96140",
        )
        self.assertEqual(manifest["license"]["spdx"], "Apache-2.0")
        self.assertEqual(manifest["python"]["requires"], ">=3.10")
        self.assertEqual(manifest["isolated_observation"]["python"], "3.12.13")
        self.assertTrue(manifest["isolated_observation"]["installed"])
        self.assertTrue(manifest["isolated_observation"]["public_imports"])
        self.assertTrue(manifest["isolated_observation"]["removed"])
        self.assertFalse(manifest["isolated_observation"]["pythonpath_present"])
        self.assertNotEqual(
            manifest["main_drift"]["observed_commit"], manifest["release_commit"]
        )
        self.assertNotIn("main", manifest["stable_contract"])


if __name__ == "__main__":
    unittest.main()
