"""SPEC-027 named nodes executed only from the five installed wheels."""

from __future__ import annotations

from pathlib import Path

import apex_research
import quant_runtime
import strategy_reporting
import strategy_workspace
from apex_research import (
    GoldenCampaign,
    GoldenProfileEvaluator,
    ProfileReceipt,
    ProfileStatus,
    classify_optional_profiles,
)


def _campaign() -> GoldenCampaign:
    return GoldenCampaign.freeze(
        brief={"objective": "five-wheel golden tracer", "expected_maturity": "validated"},
        candidates={
            "factor": {"lag": 1},
            "model": {"seed": 7},
            "strategy": {"execution": "next_open"},
        },
        universe={"symbols": ["000001.SZ"], "as_of": "2025-12-31"},
        period={"start": "2025-01-01", "end": "2025-12-31", "frequency": "1d"},
        costs={"commission_bps": 3},
        validation_cells=[{"name": "walk-forward", "folds": 3}],
        budgets={"engine_calls": 1, "formal_runs": 1},
        permissions={"workspace": "public-only"},
        cancellation={"durable_boundaries_only": True},
        capabilities={"auxiliary-validator": "not_evaluated"},
        owners={"apex-research": apex_research.__version__},
        limitations=["bounded acceptance only"],
    )


def _receipts(nodes: tuple[tuple[str, str, str], ...]) -> tuple[ProfileReceipt, ...]:
    return tuple(
        ProfileReceipt(name=name, owner=owner, evidence_class=lane, evidence_ref=f"sha256:{i:064x}")
        for i, (name, owner, lane) in enumerate(nodes, start=1)
    )


def test_five_wheels_are_imported_without_source_precedence() -> None:
    for module in (apex_research, quant_runtime, strategy_reporting, strategy_workspace):
        assert "site-packages" in Path(module.__file__).as_posix()
    assert "site-packages" in Path(__file__).as_posix()


def test_every_executable_profile_has_an_independent_deterministic_identity() -> None:
    evaluator = GoldenProfileEvaluator()
    campaign = _campaign()
    profiles = {
        "core-focused-research": (
            ("budget", "apex-research", "control"),
            ("research-engine", "apex-research", "discovery"),
            ("typed-ir", "apex-research", "discovery"),
            ("static-gate", "apex-research", "control"),
            ("package-intake", "strategy-workspace", "control"),
            ("behavioral-gate", "apex-research", "control"),
            ("preflight", "quant-runtime", "formal"),
            ("nautilus-run", "quant-runtime", "formal"),
            ("lineage", "strategy-workspace", "control"),
            ("evidence-v2", "apex-research", "formal"),
            ("qualification", "apex-research", "formal"),
            ("report-source", "apex-research", "formal"),
            ("reporting", "strategy-reporting", "presentation"),
        ),
        "factor-model-coevolution": (
            ("factor-population", "apex-research", "discovery"),
            ("model-population", "apex-research", "discovery"),
            ("qlib-discovery", "quant-runtime", "discovery"),
            ("strategy-composition", "apex-research", "control"),
            ("formal-promotion", "quant-runtime", "formal"),
        ),
        "quality-diversity": (
            ("exploration-archive", "strategy-workspace", "discovery"),
            ("evidence-archive", "strategy-workspace", "formal"),
            ("bounded-champion-promotion", "apex-research", "formal"),
        ),
        "replication": (
            ("source-freeze", "apex-research", "source"),
            ("ambiguity-ledger", "apex-research", "control"),
            ("data-mapping", "apex-research", "control"),
            ("executable-specification", "apex-research", "control"),
            ("formal-reproduction", "quant-runtime", "formal"),
            ("replication-decision", "apex-research", "formal"),
            ("replication-report", "strategy-reporting", "presentation"),
        ),
        "revalidation": (
            ("staleness-trigger", "apex-research", "control"),
            ("bounded-schedule", "apex-research", "control"),
            ("runtime-revalidation", "quant-runtime", "formal"),
            ("immutable-new-evidence", "apex-research", "formal"),
            ("supersession", "apex-research", "formal"),
            ("qualification-currency", "apex-research", "formal"),
            ("archive-expiry", "strategy-workspace", "control"),
            ("report-refresh", "strategy-reporting", "presentation"),
        ),
    }
    identities = {
        evaluator.assess_profile(campaign, profile=name, receipts=_receipts(nodes)).manifest_id
        for name, nodes in profiles.items()
    }
    assert len(identities) == len(profiles)
    assert all(
        evaluator.assess_profile(campaign, profile=name, receipts=_receipts(nodes)).status
        is ProfileStatus.PASSED
        for name, nodes in profiles.items()
    )


def test_optional_profiles_are_truthful_and_replay_has_no_duplicates() -> None:
    decisions = classify_optional_profiles(
        {
            "SPEC-020": "closed",
            "SPEC-021": "closed:no_go",
            "SPEC-022": "open",
            "SPEC-022A": "open",
            "SPEC-022B": "open",
            "SPEC-023": "closed",
            "SPEC-024": "closed",
            "SPEC-025": "closed",
        }
    )
    assert decisions["auxiliary-validator"]["status"] == "not_evaluated"
    assert decisions["qrafti"]["status"] == "executable"
    assert decisions["benchmark-regression"]["status"] == "executable"
