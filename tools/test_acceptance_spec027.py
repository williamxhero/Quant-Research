from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_spec027_admission_freezes_owner_and_profile_independence() -> None:
    value = json.loads(
        (ROOT / "docs/architecture-admissions/spec-027.v1.json").read_text(encoding="utf-8")
    )
    assert value["canonical_owner"] == "apex_research"
    assert "GoldenCampaign" in value["public_seam"]
    assert "Runtime preflight/run CLI" in value["public_seam"]
    assert "Reporting verify/rebuild/portal" in value["public_seam"]
    assert "not_evaluated" in value["evidence_level"]
    assert "private paths" in value["fail_closed_behavior"]


def test_spec027_scope_builds_all_impacted_wheels_for_one_replay_step() -> None:
    scope = json.loads(
        (ROOT / "docs/architecture-admissions/spec-027.acceptance-scope.v2.json").read_text(
            encoding="utf-8"
        )
    )
    assert set(scope["owners"]) == {
        "quant-research",
        "apex-research",
        "quant-runtime",
        "strategy-reporting",
        "strategy-workspace",
    }
    assert len(scope["levels"]["L3"]["commands"]) == 1
    assert (
        "quantresearch_acceptance._spec027_installed_test"
        in scope["levels"]["L3"]["commands"][0]["argv"]
    )
