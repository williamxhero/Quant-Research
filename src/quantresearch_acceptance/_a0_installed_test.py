"""Small installed tracer for the versioned A0 batch contract."""

from __future__ import annotations

from pathlib import Path

from .batch import A0BatchConfig, A0BatchSelector


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
        "revision": 1,
        "scope_schema": "quant-research.acceptance-scope.v2",
        "scope_revision": "acceptance-scope.v2",
        "required_cases": ["A0-Q01", "A0-Q02"],
        "scenario_to_direct_tests": {
            "A0-Q01": ["quantresearch_acceptance/_a0_installed_test.py"],
            "A0-Q02": ["quantresearch_acceptance/_a0_installed_test.py"],
        },
        "fixture_binding": {
            "fixture_revision": "a0-t04-oracle.v1",
            "fixture_digest": "sha256:" + "4" * 64,
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
