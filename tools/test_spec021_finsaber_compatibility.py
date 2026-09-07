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


if __name__ == "__main__":
    unittest.main()
