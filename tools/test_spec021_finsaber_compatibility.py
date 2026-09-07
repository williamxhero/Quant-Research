from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
ADMISSIONS = ROOT / "docs" / "architecture-admissions"


class Spec021CompatibilityTests(unittest.TestCase):
    ALLOWED_CLASSIFICATIONS = {
        "exact",
        "transformable",
        "auxiliary_only",
        "incompatible",
    }

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

    def test_frozen_equity_data_maps_adjusted_bars_but_rejects_intraday_semantics(
        self,
    ) -> None:
        transcript = json.loads(
            (ADMISSIONS / "spec-021.prototype-transcript.v1.json").read_text(
                encoding="utf-8"
            )
        )
        data = transcript["data_probe"]

        self.assertEqual(data["wheel_sha256"], transcript["wheel_sha256"])
        self.assertEqual(data["daily"]["tickers"], ["AAPL.XNAS"])
        self.assertEqual(
            data["daily"]["adjusted_rows"],
            [
                {
                    "close": 51.0,
                    "date": "2024-01-02",
                    "high": 51.5,
                    "low": 49.5,
                    "open": 50.0,
                    "symbol": "AAPL.XNAS",
                    "volume": 1000,
                },
                {
                    "close": 53.0,
                    "date": "2024-01-03",
                    "high": 54.0,
                    "low": 51.0,
                    "open": 52.0,
                    "symbol": "AAPL.XNAS",
                    "volume": 1200,
                },
            ],
        )
        edge = data["unsupported_intraday"]
        self.assertTrue(edge["loader_accepted"])
        self.assertFalse(edge["frequency_contract_field"])
        self.assertEqual(edge["classification"], "incompatible")
        self.assertEqual(edge["fallback_or_substitution"], "none")

    def test_representative_candidate_replays_signal_fill_and_equity_path(self) -> None:
        transcript = json.loads(
            (ADMISSIONS / "spec-021.prototype-transcript.v1.json").read_text(
                encoding="utf-8"
            )
        )
        probe = transcript["strategy_probe"]

        self.assertEqual(probe["candidate"]["kind"], "long_only_fixed_shares")
        self.assertEqual(probe["sessions"], 22)
        self.assertEqual(
            probe["trades"],
            [
                {
                    "commission": 0.0,
                    "execution_date": "2024-01-03",
                    "price": 101.0,
                    "quantity": 10,
                    "side": "buy",
                    "signal_date": "2024-01-02",
                    "slippage_cost": 0.0,
                },
                {
                    "commission": 0.0,
                    "execution_date": "2024-01-31",
                    "price": 121.5,
                    "quantity": 10,
                    "side": "sell",
                    "signal_date": "2024-01-31",
                    "slippage_cost": 0.0,
                },
            ],
        )
        self.assertEqual(probe["equity"][0]["equity"], 10000.0)
        self.assertEqual(probe["equity"][1]["equity"], 10005.0)
        self.assertEqual(probe["equity"][-1]["equity"], 10205.0)
        self.assertAlmostEqual(probe["metrics"]["final_value"], 10205.0)
        self.assertAlmostEqual(probe["metrics"]["total_return"], 0.0205)
        self.assertEqual(probe["rejected_orders"], [])
        self.assertEqual(probe["classifications"]["next_open"]["classification"], "exact")
        self.assertEqual(
            probe["classifications"]["strategy_interface"]["classification"],
            "transformable",
        )
        self.assertEqual(
            probe["classifications"]["forced_terminal_exit"]["classification"],
            "incompatible",
        )

    def test_cost_probe_is_worked_and_margin_rounding_edge_is_incompatible(self) -> None:
        transcript = json.loads(
            (ADMISSIONS / "spec-021.prototype-transcript.v1.json").read_text(
                encoding="utf-8"
            )
        )
        probe = transcript["execution_probe"]
        cost = probe["cost_liquidity"]

        self.assertEqual(cost["entry"]["requested_quantity"], 1000)
        self.assertEqual(cost["entry"]["executed_quantity"], 100)
        self.assertAlmostEqual(cost["entry"]["average_volume"], 1000.0)
        self.assertAlmostEqual(cost["entry"]["participation_rate"], 0.1)
        self.assertAlmostEqual(cost["entry"]["fill_price"], 106.212)
        self.assertAlmostEqual(cost["entry"]["commission"], 1.0)
        self.assertAlmostEqual(cost["entry"]["slippage_cost"], 21.2)
        self.assertAlmostEqual(cost["metrics"]["total_commission"], 2.0)
        self.assertAlmostEqual(cost["metrics"]["total_slippage"], 45.5)
        self.assertAlmostEqual(cost["metrics"]["total_trading_cost"], 47.5)
        self.assertEqual(
            probe["insufficient_history"]["rejection_reason"],
            "insufficient_liquidity_history",
        )

        edge = probe["incompatible_margin_rounding_edge"]
        self.assertEqual(edge["margin"]["requested_quantity"], 200)
        self.assertEqual(edge["margin"]["executed_quantity"], 100)
        self.assertEqual(edge["board_lot"]["requested_quantity"], 150)
        self.assertEqual(edge["board_lot"]["executed_quantity"], 150)
        self.assertEqual(edge["tick_size"]["observed_fill"], 100.003)
        self.assertEqual(edge["classification"], "incompatible")
        self.assertEqual(edge["mock_or_fallback"], "none")

    def test_artifact_metric_probe_replays_semantics_and_exposes_nondeterminism(
        self,
    ) -> None:
        transcript = json.loads(
            (ADMISSIONS / "spec-021.prototype-transcript.v1.json").read_text(
                encoding="utf-8"
            )
        )
        probe = transcript["artifact_metric_probe"]

        self.assertEqual(probe["replays"], 2)
        self.assertTrue(probe["pythonpath_cleared"])
        self.assertTrue(probe["installed_wheel_only"])
        self.assertEqual(probe["semantic_sha256"][0], probe["semantic_sha256"][1])
        self.assertNotEqual(
            probe["artifact_manifest_sha256"][0],
            probe["artifact_manifest_sha256"][1],
        )
        self.assertEqual(probe["metric_units"]["total_return"], "fraction")
        self.assertEqual(probe["metric_units"]["max_drawdown"], "percentage_points")
        self.assertEqual(
            probe["classifications"]["metric_bundle"]["classification"],
            "auxiliary_only",
        )
        self.assertEqual(
            probe["classifications"]["artifact_identity"]["classification"],
            "incompatible",
        )

        source = (ROOT / "tools" / "spec021_finsaber_compatibility.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("SPEC021_PROGRESS", source)
        self.assertIn("NODE_TIMEOUT_SECONDS", source)
        self.assertIn("PYTHONPATH", source)
        self.assertIn("replays", source)
        self.assertIn("--upstream-python", source)
        self.assertIn("--wheel", source)

    def test_decision_matrix_is_evidence_bound_and_keeps_spec_022_blocked(
        self,
    ) -> None:
        matrix = json.loads(
            (ADMISSIONS / "spec-021.compatibility-matrix.v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            set(matrix["dimensions"]),
            {
                "data",
                "strategy",
                "timing_order_fill",
                "cost_slippage_liquidity_margin_rounding",
                "artifact_metric",
                "environment_license_security_operations",
            },
        )
        classifications: set[str] = set()
        for dimension, conclusions in matrix["dimensions"].items():
            self.assertGreater(len(conclusions), 0, dimension)
            for seam, conclusion in conclusions.items():
                label = conclusion["classification"]
                classifications.add(label)
                self.assertIn(label, self.ALLOWED_CLASSIFICATIONS)
                self.assertGreater(len(conclusion["evidence"]), 0, f"{dimension}.{seam}")
                for evidence in conclusion["evidence"]:
                    self.assertIn("#", evidence, f"{dimension}.{seam}: {evidence}")
        self.assertEqual(classifications, self.ALLOWED_CLASSIFICATIONS)

        decision = json.loads(
            (ADMISSIONS / "spec-021.v1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(decision["decision"], "no_go")
        self.assertEqual(decision["adoption_category"], "rejected-dependency")
        self.assertEqual(decision["spec_022_status"], "blocked")
        self.assertIsNone(decision["independent_validator_port"])
        self.assertEqual(decision["formal_truth_namespace"], "formal.nautilus")
        self.assertNotIn("finsaber", decision["formal_truth_namespace"].lower())
        self.assertGreater(len(decision["blocking_findings"]), 0)
        self.assertEqual(decision["claims"], [])
        self.assertEqual(decision["lifecycle_states"], [])


if __name__ == "__main__":
    unittest.main()
