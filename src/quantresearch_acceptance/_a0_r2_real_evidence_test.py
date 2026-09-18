"""Real evidence checks backing the R2 rollup's A0-E01/E02/E03 corrections.

Each test reads a real, git-committed evidence file (apex-research is a
sibling checkout of this repository, not nested under it) and asserts the
specific real facts the R2 rollup cites. These are not fixtures: the files
are the actual output of a real connected quant-runtime backtest, a real
yosef-server CPA call, and a real isolated-wheel test run.
"""

from __future__ import annotations

import json
from pathlib import Path

_APEX_A0 = Path(__file__).resolve().parents[2] / "apex-research" / "docs" / "research" / "a0"


def _load(name: str) -> dict[str, object]:
    return json.loads((_APEX_A0 / name).read_text(encoding="utf-8"))


def test_a0_e01_real_round1_study_shows_a_real_v0_v1_divergence() -> None:
    study = _load("a0_round1_real_study.json")
    assert study["status"] == "executed"
    assert study["execution"]["fixture_or_mock_used_as_evidence"] is False
    assert study["execution"]["read_method"] == "direct_markethub (all six runs)"
    aggregate = study["aggregate"]
    assert aggregate["v0_total_closed_positions"] == 70
    assert aggregate["v1_total_closed_positions"] == 0
    windows = {w["label"]: w for w in study["windows"]}
    assert set(windows) == {"development", "validation", "holdout"}
    for window in windows.values():
        assert window["v0"]["orders"] > 0
        assert window["v1"]["orders"] == 0


def test_a0_e01_volume_filter_diagnostic_was_independently_spot_checked() -> None:
    study = _load("a0_round1_real_study.json")
    diagnostic = study["volume_filter_diagnostic"]
    assert "bypassing the Nautilus engine" in diagnostic["method"]
    assert "never below the 75%" in diagnostic["finding"]


def test_a0_e02_real_round2_outcome_is_a_delivered_connected_stop() -> None:
    outcome = _load("a0_round2_real_outcome.json")
    result = outcome["outcome"]
    assert result["delivery_state"] == "delivered"
    assert result["delivery_layer"] == "real_connected"
    assert result["proves_model_use"] is True
    assert result["e02_status"] == "passed"
    assert result["review_verdict"] == "stop"
    assert outcome["review_call_model"] == "deepseek-ai/DeepSeek-V4.1-Flash"
    assert outcome["model_response"]["cited_source_ids"] == [
        "a0-round1-real-study-20260918"
    ]


def test_a0_e03_real_installed_environment_run_passed_all_twelve() -> None:
    run = _load("a0_e03_installed_environment_real_run.json")
    assert run["status"] == "executed"
    assert "12 passed, 0 failed" in run["result"]["outcome"]
    assert len(run["result"]["tests"]) == 12
    assert "test_five_wheels_are_imported_without_source_precedence" in run["result"]["tests"]
    wheel_packages = {item["package"] for item in run["method"]["wheels_built"]}
    assert wheel_packages == {
        "apex_research",
        "quant_runtime",
        "strategy_reporting",
        "strategy_workspace",
        "quantresearch_acceptance",
    }


def test_g434_g437_g438_rule_oracle_strategy_artifacts_are_real() -> None:
    """The three tickets #443 found undelivered actually have real content now."""

    index = _load("a0_delivery_index.json")
    by_id = {item["logical_artifact_id"]: item for item in index["artifacts"]}
    for artifact_id in ("a0-rules", "a0-parameters", "a0-variants"):
        assert by_id[artifact_id]["status"] == "frozen-default-approved"
        assert by_id[artifact_id]["commit"]
    assert by_id["a0-fixtures-oracles"]["status"].startswith("delivered")
    assert by_id["a0-reference-strategy-and-package"]["status"].startswith("delivered")

    rules_path = _APEX_A0 / "a0_rules.md"
    assert rules_path.exists()
    assert "frozen-default-approved" in rules_path.read_text(encoding="utf-8")

    strategy_path = (
        _APEX_A0.parents[2].parent
        / "strategy-workspace"
        / "strategies"
        / "equity"
        / "a0-ema-crossback"
        / "formal"
        / "nautilus"
        / "strategy.py"
    )
    assert strategy_path.exists()
    assert "class A0EmaCrossbackStrategy" in strategy_path.read_text(encoding="utf-8")
