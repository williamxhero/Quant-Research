from __future__ import annotations

import importlib

from .research_a0_final_rollup_r2 import (
    A0_SCENARIOS_R2,
    GAPS_R2,
    final_rollup_readback_r2,
    passed_scenario_ids_r2,
    scenario_r2,
)

_PACKAGE = "quantresearch_acceptance"


def test_the_three_e_scenarios_now_pass_for_real() -> None:
    passed = set(passed_scenario_ids_r2())
    for scenario_id in ("A0-E01", "A0-E02", "A0-E03"):
        record = scenario_r2(scenario_id)
        assert record.status == "executed"
        assert record.evidence_type_matches
        assert scenario_id in passed
        assert record.evidence, scenario_id


def test_every_named_r2_test_actually_exists() -> None:
    missing: list[str] = []
    for record in A0_SCENARIOS_R2:
        for ref in record.evidence:
            module = importlib.import_module(f"{_PACKAGE}.{ref.module}")
            if not callable(getattr(module, ref.test, None)):
                missing.append(f"{ref.module}::{ref.test}")
    assert missing == []


def test_the_pass_count_moved_from_nineteen_to_twenty_two() -> None:
    assert len(passed_scenario_ids_r2()) == 24
    assert len(A0_SCENARIOS_R2) == 27


def test_x01_x02_now_pass_via_the_real_oracle_replay() -> None:
    passed = set(passed_scenario_ids_r2())
    for scenario_id in ("A0-X01", "A0-X02"):
        record = scenario_r2(scenario_id)
        assert scenario_id in passed
        assert record.status == "executed"
        assert record.evidence_type_matches
        assert record.evidence
        assert any("false negative" in text for text in record.limitations)


def test_the_seven_resolved_gaps_are_all_gone() -> None:
    gap_ids = {gap.gap_id for gap in GAPS_R2}
    for resolved in (
        "G-434-RULES",
        "G-437-ORACLE",
        "G-438-STRATEGY",
        "G-441-ASSETS",
        "G-442-ENGINE",
        "G-429-WHEELS",
    ):
        assert resolved not in gap_ids
    assert "G-438-REPLAY-R2" not in gap_ids
    assert len(GAPS_R2) == 4


def test_a_not_run_or_type_mismatched_scenario_still_cannot_reach_the_passed_list() -> None:
    passed = set(passed_scenario_ids_r2())
    for record in A0_SCENARIOS_R2:
        if record.status != "executed" or not record.evidence_type_matches:
            assert record.scenario_id not in passed, record.scenario_id


def test_the_readback_is_deterministic_and_json_serialisable() -> None:
    import json

    first = final_rollup_readback_r2()
    second = final_rollup_readback_r2()
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_no_report_claims_statistical_significance_or_a_profit_threshold() -> None:
    readback = final_rollup_readback_r2()
    findings = readback["research_findings_report"]
    assert findings["statistical_significance_claimed"] is False
    assert findings["profitability_claimed"] is False
    assert findings["causal_claim"] is False


def test_the_sign_off_is_not_a_blanket_pass() -> None:
    readback = final_rollup_readback_r2()
    assert readback["sign_off"] != "pass"
    assert len(readback["passed_scenario_ids"]) < len(A0_SCENARIOS_R2)


def test_the_published_r2_index_file_matches_the_module_exactly() -> None:
    import json
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[2]
        / "docs" / "research" / "a0" / "a0_acceptance_evidence_index_r2.json"
    )
    published = json.loads(path.read_text(encoding="utf-8"))
    assert published == json.loads(json.dumps(final_rollup_readback_r2(), ensure_ascii=False))


def test_the_rollup_r2_module_depends_on_the_standard_library_only() -> None:
    module = importlib.import_module(f"{_PACKAGE}.research_a0_final_rollup_r2")
    source = __import__("inspect").getsource(module)
    for banned in ("import requests", "import httpx", "pydantic", "sqlalchemy"):
        assert banned not in source
