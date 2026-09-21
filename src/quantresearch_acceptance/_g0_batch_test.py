"""Contract tests for the G0 acceptance batch revision (ticket #499).

This module is also the *direct test* that the G0 batch names for every task
whose catalog row does not reuse an A0 scenario.  That makes the binding real
rather than decorative: the tests below assert that each such catalog row is
well formed and that the batch still reports ``not_run`` for it, because the
task itself is executed for real in S4 and no run exists yet.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from .batch import A0BatchConfig, A0BatchSelector, A0EvidenceLedger
from .core import AcceptanceFailure
from .research_g0_batch import (
    G0_BEHAVIOURS,
    G0_CATALOG_ID,
    G0_FIXTURE_COMMIT,
    G0_TASKS,
    g0_batch_config,
    g0_fixture_digest,
    g0_reported_statuses,
    g0_task,
)
from .train import ReleaseTrain

_PACKAGE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _PACKAGE_DIR.parents[1]
_STATUSES = ("pass", "fail", "expected-deny", "blocked", "not_run")

#: Catalog rows whose direct test is this module rather than reused A0 evidence.
_CONTRACT_BACKED = (
    "G0-T02",
    "G0-T04",
    "G0-T06",
    "G0-T07",
    "G0-T08",
    "G0-T09",
    "G0-T10",
    "G0-T11",
    "G0-T12",
)


def _scope() -> dict[str, object]:
    command = {
        "owner": "quant-research",
        "argv": ["python", "-c", "pass"],
        "markers": [],
        "history_samples_seconds": [1, 2, 3],
    }
    tests = sorted({test for task in G0_TASKS for test in task.direct_tests})
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
        "source_to_direct_tests": {"src/quantresearch_acceptance/batch.py": tests},
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


def _selection():
    return A0BatchSelector().select(g0_batch_config(), _scope(), _diff(), phase="spec")


# ---------------------------------------------------------------------------
# The batch revision itself.
# ---------------------------------------------------------------------------


def test_the_g0_batch_is_parsed_and_selected_by_the_existing_selector() -> None:
    config = g0_batch_config()
    assert A0BatchConfig.parse(config).as_dict() == config
    selection = _selection()
    assert selection.batch_id == "G0"
    assert selection.batch_revision == 1
    assert selection.selected_cases == tuple(task.task_id for task in G0_TASKS)
    assert len(selection.selected_cases) == 15
    assert dict(selection.fixture_binding) == {
        "fixture_revision": G0_CATALOG_ID,
        "fixture_digest": g0_fixture_digest(),
        "fixture_commit": G0_FIXTURE_COMMIT,
        "role": "synthetic-test-only",
    }


def test_the_g0_case_ids_and_the_a0_case_ids_stay_in_their_own_families() -> None:
    borrowed = g0_batch_config()
    borrowed["required_cases"] = ["A0-X01"]
    borrowed["scenario_to_direct_tests"] = {
        "A0-X01": ["quantresearch_acceptance/_g0_batch_test.py"]
    }
    with pytest.raises(AcceptanceFailure):
        A0BatchConfig.parse(borrowed)

    a0_borrowing_g0 = dict(borrowed, batch_id="A0")
    a0_borrowing_g0["required_cases"] = ["G0-T01"]
    a0_borrowing_g0["scenario_to_direct_tests"] = {
        "G0-T01": ["quantresearch_acceptance/_g0_batch_test.py"]
    }
    with pytest.raises(AcceptanceFailure):
        A0BatchConfig.parse(a0_borrowing_g0)


def test_the_g0_batch_is_never_appended_to_the_32_spec_release_ledger() -> None:
    train = ReleaseTrain(tuple(f"SPEC-{index:03d}" for index in range(1, 33)))
    with pytest.raises(AcceptanceFailure):
        train.record("G0-T01", "sha256:" + "a" * 64)
    assert train.next_spec == "SPEC-001"


def test_the_published_g0_batch_file_matches_the_module_exactly() -> None:
    """The tracked JSON is generated from the module, never hand-edited.

    ``/docs`` is git-ignored apart from force-added files, so this skips on a
    checkout that does not carry it.
    """

    path = _REPO_ROOT / "docs" / "research" / "g0" / "g0_acceptance_batch.json"
    if not path.exists():
        pytest.skip("published G0 batch config not present on this checkout")
    published = json.loads(path.read_text(encoding="utf-8"))
    assert published == json.loads(json.dumps(g0_batch_config(), ensure_ascii=False))


# ---------------------------------------------------------------------------
# Catalog rows: well-formedness and the honest `not_run` reading.
# ---------------------------------------------------------------------------


def test_every_g0_catalog_row_declares_a_well_formed_expected_status() -> None:
    assert len(G0_TASKS) == 15
    assert len(G0_BEHAVIOURS) == 12
    for task in G0_TASKS:
        assert task.expected_batch_status in _STATUSES, task.task_id
        assert task.behaviour, task.task_id
        assert task.input_kind in ("fixture", "real_data"), task.task_id
        assert task.evidence_role in (
            "process_behaviour_only",
            "research_evidence",
        ), task.task_id
        if task.input_kind == "fixture":
            assert task.evidence_role == "process_behaviour_only", task.task_id
        if task.behaviour == "leaked_input":
            assert task.expected_batch_status == "expected-deny", task.task_id


def test_the_contract_backed_tasks_report_not_run_until_the_s4_run_exists() -> None:
    reported = g0_reported_statuses()
    assert set(reported) == {task.task_id for task in G0_TASKS}
    for task_id in _CONTRACT_BACKED:
        task = g0_task(task_id)
        assert task.a0_scenarios == (), task_id
        assert task.direct_tests == ("quantresearch_acceptance/_g0_batch_test.py",)
        assert reported[task_id] == "not_run", task_id
    # The reused-A0 rows are equally unrun: A0 evidence backs the scenario, it
    # does not stand in for the G0 task's own S4 run.
    assert set(reported.values()) == {"not_run"}


def test_the_reused_a0_rows_cite_scenarios_that_exist_in_the_a0_rollup() -> None:
    from .research_a0_final_rollup_r2 import A0_SCENARIOS_R2

    known = {record.scenario_id for record in A0_SCENARIOS_R2}
    cited = {scenario for task in G0_TASKS for scenario in task.a0_scenarios}
    assert cited
    assert cited <= known


def test_the_g0_ledger_reports_no_pass_before_any_task_has_run() -> None:
    selection = _selection()
    ledger = A0EvidenceLedger(selection)
    for index, (task_id, status) in enumerate(sorted(g0_reported_statuses().items())):
        ledger.record(
            task_id,
            status=status,
            evidence_ref="sha256:" + f"{index:064x}",
            plan_identity=selection.plan.identity,
            fixture_digest=g0_fixture_digest(),
        )
    summary = ledger.summary()
    assert summary["batch_id"] == "G0"
    assert summary["complete"] is True
    assert summary["missing_cases"] == []
    assert summary["pass_count"] == 0
    assert summary["non_pass_cases"] == 15
    assert summary["counts"]["not_run"] == 15


# ---------------------------------------------------------------------------
# No scenario counts as a pass without a direct test.
# ---------------------------------------------------------------------------


def test_every_named_direct_test_file_actually_exists() -> None:
    missing = [
        test
        for task in G0_TASKS
        for test in task.direct_tests
        if not (_PACKAGE_DIR.parent / test).exists()
    ]
    assert missing == []


def test_a_scenario_without_a_direct_test_cannot_be_declared_at_all() -> None:
    unmapped = g0_batch_config()
    unmapped["required_cases"] = [*unmapped["required_cases"], "G0-T16"]  # type: ignore[misc]
    with pytest.raises(AcceptanceFailure):
        A0BatchConfig.parse(unmapped)

    empty = g0_batch_config()
    empty["scenario_to_direct_tests"]["G0-T09"] = []  # type: ignore[index]
    with pytest.raises(AcceptanceFailure):
        A0BatchConfig.parse(empty)

    outside_scope = g0_batch_config()
    outside_scope["scenario_to_direct_tests"]["G0-T09"] = [  # type: ignore[index]
        "quantresearch_acceptance/_not_a_real_test.py"
    ]
    with pytest.raises(AcceptanceFailure):
        A0BatchSelector().select(outside_scope, _scope(), _diff(), phase="spec")


def test_a_scenario_without_a_direct_test_can_never_be_recorded_as_pass() -> None:
    selection = _selection()
    ledger = A0EvidenceLedger(selection)
    with pytest.raises(AcceptanceFailure):
        ledger.record(
            "G0-T16",
            status="pass",
            evidence_ref="sha256:" + "a" * 64,
            plan_identity=selection.plan.identity,
            fixture_digest=g0_fixture_digest(),
        )
    assert ledger.summary()["pass_count"] == 0
    assert "G0-T16" not in ledger.summary()["missing_cases"]  # type: ignore[operator]
