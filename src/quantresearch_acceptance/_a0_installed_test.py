"""Small installed tracer for the versioned A0 batch contract."""

from __future__ import annotations

from pathlib import Path

from .batch import A0BatchConfig, A0BatchSelector, A0EvidenceLedger
from .core import AcceptanceFailure

_A0_R2_FIXTURE_COMMIT = "b42f1576e41828e5f420c685afea4d4833922695"
_A0_R2_MANIFEST_DIGEST = (
    "sha256:a0a1359e575a79a619f09f4cc365b0f11fef8007989c25e8a91c93a0ee805ab7"
)


def _scope() -> dict[str, object]:
    command = {
        "owner": "quant-research",
        "argv": ["python", "-c", "pass"],
        "markers": [],
        "history_samples_seconds": [1, 2, 3],
    }
    return {
        "schema": "quant-research.acceptance-scope.v2",
        "spec": "TEST-001",
        "owners": {
            "quant-research": {
                "fixed_base": "1" * 40,
                "repository": ".",
                "diff_prefixes": ["src/"],
                "source_patterns": ["src/"],
                "import_names": ["quantresearch_acceptance"],
                "build_argv": ["uv", "build"],
                "source_fingerprint": "sha256:" + "2" * 64,
            }
        },
        "public_contract_sources": ["src/quantresearch_acceptance/batch.py"],
        "source_to_direct_tests": {
            "src/quantresearch_acceptance/batch.py": [
                "quantresearch_acceptance/_a0_installed_test.py"
            ]
        },
        "levels": {
            name: {"budget_seconds": budget, "commands": [dict(command)]}
            for name, budget in (("L0", 60), ("L1", 180), ("L2", 600), ("L3", 300))
        },
        "marker_policy": {
            "allowed": ["connected", "oci", "release", "slow"],
            "ordinary_exclusion": "not slow and not oci and not connected and not release",
        },
        "evidence": {
            "artifact_root": "artifacts/acceptance/{plan_id}",
            "event_log": "events.jsonl",
            "plan": "plan.json",
        },
    }


def _diff() -> dict[str, object]:
    return {
        "schema": "quant-research.fixed-base-diff.v1",
        "fixed_bases": {"quant-research": "1" * 40},
        "source_fingerprints": {"quant-research": "sha256:" + "2" * 64},
        "changed_sources": [
            {
                "path": "src/quantresearch_acceptance/batch.py",
                "fingerprint": "sha256:" + "3" * 64,
            }
        ],
    }


def _batch() -> dict[str, object]:
    return {
        "schema": "quant-research.acceptance-batch.v1",
        "batch_id": "A0",
        "revision": 2,
        "scope_schema": "quant-research.acceptance-scope.v2",
        "scope_revision": "acceptance-scope.v2",
        "required_cases": ["A0-Q01", "A0-Q02"],
        "scenario_to_direct_tests": {
            "A0-Q01": ["quantresearch_acceptance/_a0_installed_test.py"],
            "A0-Q02": ["quantresearch_acceptance/_a0_installed_test.py"],
        },
        "fixture_binding": {
            "fixture_revision": "a0-t04-oracle.v2",
            "fixture_digest": _A0_R2_MANIFEST_DIGEST,
            "fixture_commit": _A0_R2_FIXTURE_COMMIT,
            "role": "synthetic-test-only",
        },
    }


def test_a0_installed_tracer_is_not_source_preferred() -> None:
    assert "site-packages" in Path(__file__).resolve().as_posix()
    assert not (Path.cwd() / "src/quantresearch_acceptance").exists()


def test_a0_batch_reuses_the_existing_selector_contract() -> None:
    selection = A0BatchSelector().select(_batch(), _scope(), _diff(), phase="spec")
    assert selection.batch_id == "A0"
    assert selection.plan.levels == ("L0", "L1", "L2", "L3")
    assert selection.selected_cases == ("A0-Q01", "A0-Q02")
    assert A0BatchConfig.parse(_batch()).as_dict() == _batch()


def test_a0_batch_rejects_missing_required_case() -> None:
    missing = _batch()
    missing["required_cases"] = ["A0-Q01"]
    try:
        A0BatchSelector().select(missing, _scope(), _diff(), phase="spec")
    except AcceptanceFailure:
        pass
    else:
        raise AssertionError("missing required A0-Q02 mapping must be rejected")


def test_a0_batch_rejects_invalid_fixture_commit_and_scope_escape() -> None:
    invalid_commit = _batch()
    invalid_commit["fixture_binding"] = dict(
        invalid_commit["fixture_binding"], fixture_commit="b" * 39
    )
    try:
        A0BatchConfig.parse(invalid_commit)
    except AcceptanceFailure:
        pass
    else:
        raise AssertionError("fixture commit must be a full immutable SHA-1")

    outside_scope = _batch()
    outside_scope["scenario_to_direct_tests"] = {
        "A0-Q01": ["quantresearch_acceptance/_a0_installed_test.py"],
        "A0-Q02": ["not-owned-by-scope.py"],
    }
    try:
        A0BatchSelector().select(outside_scope, _scope(), _diff(), phase="spec")
    except AcceptanceFailure:
        pass
    else:
        raise AssertionError("scenario mapping outside the strict scope must be rejected")


def test_a0_batch_ledger_preserves_all_non_pass_statuses_and_rejects_drift() -> None:
    batch = _batch()
    batch["required_cases"] = ["A0-G01", "A0-G02", "A0-G03", "A0-Q01", "A0-Q02"]
    batch["scenario_to_direct_tests"] = {
        case_id: ["quantresearch_acceptance/_a0_installed_test.py"]
        for case_id in batch["required_cases"]
    }
    selection = A0BatchSelector().select(batch, _scope(), _diff(), phase="spec")
    ledger = A0EvidenceLedger(selection)
    statuses = ("pass", "fail", "expected-deny", "blocked", "not_run")
    for case_id, status in zip(selection.selected_cases, statuses, strict=True):
        ledger.record(
            case_id,
            status=status,
            evidence_ref="sha256:" + case_id[-1].lower() * 64,
            plan_identity=selection.plan.identity,
            fixture_digest=_A0_R2_MANIFEST_DIGEST,
        )
    assert ledger.summary()["counts"] == {
        "pass": 1,
        "fail": 1,
        "expected-deny": 1,
        "blocked": 1,
        "not_run": 1,
    }
    assert ledger.summary()["pass_count"] == 1
    try:
        ledger.record(
            "A0-Q01",
            status="not_run",
            evidence_ref="sha256:" + "a" * 64,
            plan_identity=selection.plan.identity,
            fixture_digest="sha256:" + "b" * 64,
        )
    except AcceptanceFailure:
        pass
    else:
        raise AssertionError("stale fixture digest must be rejected")
    try:
        ledger.record(
            "A0-Q01",
            status="pass",
            evidence_ref="sha256:" + "f" * 64,
            plan_identity=selection.plan.identity,
            fixture_digest=_A0_R2_MANIFEST_DIGEST,
        )
    except AcceptanceFailure:
        pass
    else:
        raise AssertionError("immutable evidence drift must be rejected")
