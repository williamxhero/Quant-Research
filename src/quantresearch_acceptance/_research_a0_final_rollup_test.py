"""Consistency checks for the #443 A0 final rollup.

These tests do not re-prove any scenario.  Every scenario's proof belongs to
the ticket that produced it.  What these tests do is make the *index* unable to
drift or to lie:

* a cited test that is renamed or deleted breaks the rollup loudly,
* a cited commit SHA that does not exist in this repository breaks it,
* a cited evidence document that is missing breaks it,
* a scenario dropped from the catalogue breaks it,
* and, most importantly, a `not_run`, `pending`, `cited` or type-mismatched
  scenario can never reach the passed list, whatever a future edit does to the
  record.
"""

from __future__ import annotations

import ast
import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from .research_a0_final_rollup import (
    A0_ROLLUP_SCHEMA,
    A0_SCENARIOS,
    A0_TICKETS,
    ALL_TICKETS,
    BASELINE_COMMIT,
    EVIDENCE_CLASSES,
    EVIDENCE_TYPES,
    GAPS,
    JOINT_SCENARIOS,
    NATIVE_RELATIONSHIP_READBACK,
    OLD_TICKETS,
    ROLLUP_PROVENANCE,
    SCENARIO_STATUSES,
    commit_refs,
    engineering_report,
    evidence_refs,
    final_rollup_readback,
    passed_scenario_ids,
    research_findings_report,
    research_qualification_report,
    rule_implementation_report,
    scenario,
    scenario_ids,
    scenario_ids_with_status,
    type_mismatched_scenario_ids,
    uncovered_scenario_ids,
)

_PACKAGE = "quantresearch_acceptance"
_PACKAGE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _PACKAGE_DIR.parents[1]

#: #431's catalogue, in its published order.  Written out rather than derived,
#: so that deleting a scenario from the module fails here instead of silently
#: shrinking the denominator.
_PUBLISHED_SCENARIO_IDS = (
    "A0-G01", "A0-G02", "A0-G03", "A0-G04",
    "A0-X01", "A0-X02",
    "A0-L01", "A0-L02", "A0-L03",
    "A0-V01", "A0-V02",
    "A0-M01", "A0-M02", "A0-M03",
    "A0-P01", "A0-P02",
    "A0-C01", "A0-C02",
    "A0-R01", "A0-R02",
    "A0-H01", "A0-H02",
    "A0-E01", "A0-E02", "A0-E03",
    "A0-Q01", "A0-Q02",
)


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


# ---------------------------------------------------------------------------
# The catalogue is complete and nothing is silently dropped.
# ---------------------------------------------------------------------------


def test_all_twenty_seven_scenarios_are_present_in_the_published_order() -> None:
    """#431 enumerates twenty-seven scenarios.  All twenty-seven are here."""

    assert scenario_ids() == _PUBLISHED_SCENARIO_IDS
    assert len(A0_SCENARIOS) == 27
    assert len(set(scenario_ids())) == 27


def test_all_thirty_three_tickets_are_recorded() -> None:
    """#431's twenty-four old tickets plus the nine A0 implementation tickets."""

    assert len(OLD_TICKETS) == 24
    assert len(A0_TICKETS) == 9
    assert len(ALL_TICKETS) == 33
    tickets = [record.ticket for record in ALL_TICKETS]
    assert len(set(tickets)) == 33


def test_no_scenario_is_silently_dropped_by_the_ticket_map() -> None:
    """Every scenario is claimed by at least one ticket other than #443 itself."""

    assert uncovered_scenario_ids() == ()


def test_every_ticket_names_only_real_scenarios() -> None:
    known = set(scenario_ids())
    for record in ALL_TICKETS:
        assert record.scenario_ids, f"{record.ticket} claims no scenario"
        assert set(record.scenario_ids) <= known, record.ticket


def test_all_six_joint_scenarios_map_onto_real_a0_scenarios() -> None:
    assert tuple(item.scenario_id for item in JOINT_SCENARIOS) == (
        "U1", "U2", "U3", "U4", "U5", "U6",
    )
    known = set(scenario_ids())
    for item in JOINT_SCENARIOS:
        assert item.a0_scenario_ids, f"{item.scenario_id} maps to nothing"
        assert set(item.a0_scenario_ids) <= known
        assert item.evidence, f"{item.scenario_id} has no evidence"


# ---------------------------------------------------------------------------
# Every citation resolves.  This is what makes the index checkable.
# ---------------------------------------------------------------------------


def test_every_named_test_in_the_rollup_actually_exists() -> None:
    """A renamed or deleted test breaks the rollup instead of leaving a hole."""

    missing: list[str] = []
    for ref in evidence_refs((*A0_SCENARIOS, *JOINT_SCENARIOS)):
        module = importlib.import_module(f"{_PACKAGE}.{ref.module}")
        if not callable(getattr(module, ref.test, None)):
            missing.append(f"{ref.module}::{ref.test}")
    assert missing == []


def test_every_cited_commit_exists_in_this_repository() -> None:
    """A fabricated or mistyped SHA is caught here, not by a later reader."""

    if _git("rev-parse", "--git-dir").returncode != 0:
        pytest.skip("not a git checkout")
    missing: list[str] = []
    for ref in commit_refs():
        result = _git("cat-file", "-t", ref.sha)
        if result.returncode != 0 or result.stdout.strip() != "commit":
            missing.append(ref.sha)
    assert missing == []
    assert len(commit_refs()) >= 12


def test_every_cited_commit_subject_matches_the_real_commit() -> None:
    """The SHA existing is not enough; it must be the commit the index claims."""

    if _git("rev-parse", "--git-dir").returncode != 0:
        pytest.skip("not a git checkout")
    wrong: list[str] = []
    for ref in commit_refs():
        result = _git("log", "-1", "--format=%s", ref.sha)
        if result.returncode != 0 or result.stdout.strip() != ref.subject:
            wrong.append(f"{ref.sha}: {result.stdout.strip()!r} != {ref.subject!r}")
    assert wrong == []


def test_the_baseline_commit_exists() -> None:
    if _git("rev-parse", "--git-dir").returncode != 0:
        pytest.skip("not a git checkout")
    result = _git("cat-file", "-t", BASELINE_COMMIT)
    assert result.stdout.strip() == "commit"


def test_every_cited_evidence_document_exists() -> None:
    """`/docs` is git-ignored here apart from the force-added evidence files."""

    docs = [record.evidence_doc for record in ALL_TICKETS if record.evidence_doc]
    assert len(docs) >= 10
    missing = [doc for doc in docs if not (_REPO_ROOT / doc).exists()]
    # The rollup's own document does not exist until it is written.
    missing = [doc for doc in missing if "issue-443" not in doc]
    assert missing == []


# ---------------------------------------------------------------------------
# A pass cannot be manufactured.  These are the honesty invariants.
# ---------------------------------------------------------------------------


def test_a_not_run_or_pending_scenario_can_never_reach_the_passed_list() -> None:
    passed = set(passed_scenario_ids())
    for status in ("not_run", "pending"):
        for scenario_id in scenario_ids_with_status(status):
            assert scenario_id not in passed, scenario_id


def test_a_type_mismatched_scenario_can_never_reach_the_passed_list() -> None:
    """Executed with the wrong evidence type is not a pass.

    This is #431's acceptance criterion 1 made structural: a fixture, a stub or
    a contract-level proof cannot stand in for a required connected, installed,
    real-sandbox or independent-golden evidence type.
    """

    passed = set(passed_scenario_ids())
    for scenario_id in type_mismatched_scenario_ids():
        assert scenario_id not in passed, scenario_id


def test_cited_owner_evidence_is_never_counted_as_a_pass() -> None:
    """#419's measurement is real, but it is the owner's, not this rollup's."""

    cited = scenario_ids_with_status("cited_owner_evidence")
    assert cited == ("A0-L03",)
    assert "A0-L03" not in set(passed_scenario_ids())
    record = scenario("A0-L03")
    assert any("NOT re-measured" in text for text in record.limitations)


def test_the_three_e_scenarios_never_appear_in_the_passed_list() -> None:
    """E01, E02 and E03 are the ones it would be most damaging to launder."""

    passed = set(passed_scenario_ids())
    for scenario_id in ("A0-E01", "A0-E02", "A0-E03"):
        record = scenario(scenario_id)
        assert scenario_id not in passed
        assert record.satisfied_evidence_types == ()
        assert record.evidence_type_matches is False


def test_e01_is_owner_reported_and_never_counted_as_executed_or_not_run() -> None:
    """A0-E01 gets its own status because neither existing one is truthful.

    ``not_run`` would ignore #441's closure receipt.  ``executed`` would claim
    something this repository cannot check.  The third status says exactly what
    is true and is excluded from the passed list either way.
    """

    record = scenario("A0-E01")
    assert record.status == "owner_reported_unverifiable"
    assert record.evidence_class == "owner_reported_unverifiable_here"
    assert record.owner_issue == "#441"
    assert record.passed is False
    assert "#441 closed 2026-09-14" in record.note
    assert any("inconclusive" in text for text in record.limitations)
    assert any("do not exist on this checkout" in text for text in record.limitations)


def test_the_e01_receipt_artifacts_are_absent_from_this_checkout() -> None:
    """The basis for the `owner_reported_unverifiable` status, re-checked.

    If someone later publishes #441's assets into this repository, this test
    fails and forces the status to be revisited rather than left stale -- which
    is exactly the failure mode this rollup exists to correct.
    """

    claimed = (
        "runtime/q441/evidence-index.md",
        "runtime/q441/a0-study-report.md",
    )
    present = [path for path in claimed if (_REPO_ROOT / path).exists()]
    assert present == []


def test_e02_and_e03_are_not_run_and_say_why() -> None:
    for scenario_id in ("A0-E02", "A0-E03"):
        record = scenario(scenario_id)
        assert record.status == "not_run"
        assert record.evidence_class == "absent"
        assert record.limitations, scenario_id
        assert "re-verified at this baseline" in record.limitations[0]
    assert "NOT evidence that the criterion is satisfied" in scenario("A0-E02").note


def test_the_engine_and_wheel_absences_are_still_true_at_this_baseline() -> None:
    """Re-probe rather than inherit #442's and #429's findings."""

    for module_name in ("apex_research", "strategy_workspace"):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module_name)
    assert not (_REPO_ROOT / ".env").exists()


def test_every_executed_scenario_has_evidence() -> None:
    for record in A0_SCENARIOS:
        if record.status == "executed":
            assert record.evidence, record.scenario_id


def test_every_scenario_without_satisfied_types_is_not_passed() -> None:
    for record in A0_SCENARIOS:
        if not record.satisfied_evidence_types:
            assert record.passed is False, record.scenario_id


def test_the_pass_count_is_nineteen_of_twenty_seven() -> None:
    """Pinned, so a silent change to any status is visible in review."""

    passed = passed_scenario_ids()
    assert len(passed) == 19
    assert set(passed) == {
        "A0-G02", "A0-G03", "A0-G04",
        "A0-L01", "A0-L02",
        "A0-V02",
        "A0-M01", "A0-M02", "A0-M03",
        "A0-P01", "A0-P02",
        "A0-C01", "A0-C02",
        "A0-R01", "A0-R02",
        "A0-H01", "A0-H02",
        "A0-Q01", "A0-Q02",
    }


def test_the_eight_unpassed_scenarios_each_have_a_declared_reason() -> None:
    unpassed = [r for r in A0_SCENARIOS if not r.passed]
    assert len(unpassed) == 8
    for record in unpassed:
        assert record.limitations or record.note, record.scenario_id


# ---------------------------------------------------------------------------
# Vocabulary, determinism and separation of the four reports.
# ---------------------------------------------------------------------------


def test_every_status_and_evidence_class_is_from_the_published_vocabulary() -> None:
    for record in A0_SCENARIOS:
        assert record.status in SCENARIO_STATUSES, record.scenario_id
        assert record.evidence_class in EVIDENCE_CLASSES, record.scenario_id


def test_every_evidence_type_is_from_the_published_vocabulary() -> None:
    for record in A0_SCENARIOS:
        assert record.required_evidence_types, record.scenario_id
        for name in (*record.required_evidence_types, *record.satisfied_evidence_types):
            assert name in EVIDENCE_TYPES, f"{record.scenario_id}: {name}"


def test_satisfied_types_are_always_a_subset_of_required_types() -> None:
    """Nobody may claim credit for an evidence type the scenario never asked for."""

    for record in A0_SCENARIOS:
        assert set(record.satisfied_evidence_types) <= set(record.required_evidence_types)


def test_the_readback_is_deterministic_and_json_serialisable() -> None:
    first = json.dumps(final_rollup_readback(), sort_keys=True, ensure_ascii=False)
    second = json.dumps(final_rollup_readback(), sort_keys=True, ensure_ascii=False)
    assert first == second


def test_the_readback_publishes_its_provenance_baseline_and_schema() -> None:
    readback = final_rollup_readback()
    assert readback["schema"] == A0_ROLLUP_SCHEMA
    assert readback["provenance"] == ROLLUP_PROVENANCE
    assert "sourced_from_issue_431_catalogue" in str(readback["provenance"])
    assert "Nothing is reconstructed" in str(readback["provenance"])
    assert readback["baseline"] == BASELINE_COMMIT
    assert readback["sign_off"] == "partial"


def test_the_passed_and_unpassed_id_lists_are_disjoint_in_the_readback() -> None:
    readback = final_rollup_readback()
    passed = set(readback["passed_scenario_ids"])  # type: ignore[arg-type]
    for key in (
        "not_run_scenario_ids",
        "pending_scenario_ids",
        "cited_scenario_ids",
        "owner_reported_scenario_ids",
        "type_mismatched_scenario_ids",
    ):
        assert passed.isdisjoint(set(readback[key])), key  # type: ignore[arg-type]


def test_the_four_reports_are_separate_and_reach_different_conclusions() -> None:
    """#431 requires engineering, rule implementation, research findings and
    research qualification to be reported separately.  They are, and they do
    not agree with each other -- which is the point."""

    reports = {
        "engineering": engineering_report(),
        "rule_implementation": rule_implementation_report(),
        "research_findings": research_findings_report(),
        "research_qualification": research_qualification_report(),
    }
    conclusions = {name: report["conclusion"] for name, report in reports.items()}
    assert conclusions == {
        "engineering": "pass_with_declared_gaps",
        "rule_implementation": "cannot_be_concluded",
        "research_findings": "no_research_finding",
        "research_qualification": "not_qualified",
    }
    readback = final_rollup_readback()
    for name in reports:
        assert f"{name}_report" in readback


def test_no_report_claims_a_research_finding_or_a_profit_threshold() -> None:
    findings = research_findings_report()
    assert findings["answer"] == "unanswered"
    assert findings["v1_better_than_v0"] == "unknown"
    assert findings["profitability_claimed"] is False
    assert findings["statistical_significance_claimed"] is False
    assert findings["causal_claim"] is False
    qualification = research_qualification_report()
    assert qualification["undeclared_profit_or_significance_threshold"] is False
    assert qualification["lookahead_or_future_information_leak_found"] is False
    assert qualification["holdout_consumed"] is False


def test_the_engineering_pass_never_implies_a_research_pass() -> None:
    """The distinction this rollup most needs to keep."""

    engineering = engineering_report()
    assert engineering["conclusion"] == "pass_with_declared_gaps"
    assert research_findings_report()["conclusion"] == "no_research_finding"
    assert "does not mean any research was performed" in str(
        research_findings_report()["engineering_success_is_not_research_success"]
    )


def test_the_known_suite_failures_are_declared_rather_than_silenced() -> None:
    engineering = engineering_report()
    failures = engineering["known_suite_failures"]
    assert failures == (
        "_a0_installed_test.py::test_a0_installed_tracer_is_not_source_preferred",
        "_installed_test.py::test_installed_wheel_has_no_source_checkout_precedence",
    )
    assert "no wheel is installed" in str(engineering["known_suite_failures_reason"])


# ---------------------------------------------------------------------------
# Gaps and native relationships.
# ---------------------------------------------------------------------------


def test_every_gap_has_an_owner_and_names_only_real_scenarios() -> None:
    known = set(scenario_ids())
    assert len(GAPS) >= 8
    ids = [gap.gap_id for gap in GAPS]
    assert len(set(ids)) == len(ids)
    for gap in GAPS:
        assert gap.owner, gap.gap_id
        assert gap.remediation, gap.gap_id
        assert set(gap.blocks) <= known, gap.gap_id


def test_every_unpassed_scenario_is_reachable_from_a_gap_or_is_cited() -> None:
    """Nothing is left unexplained: each failure has somewhere to go next."""

    blocked: set[str] = set()
    for gap in GAPS:
        blocked.update(gap.blocks)
    for record in A0_SCENARIOS:
        if record.passed or record.status == "cited_owner_evidence":
            continue
        assert record.scenario_id in blocked, record.scenario_id


def test_the_native_relationship_state_is_pending_and_claims_no_verified_tree() -> None:
    """Step 8 was actually performed; the result was an empty tree."""

    state = NATIVE_RELATIONSHIP_READBACK
    assert state["performed"] is True
    assert state["state"] == "pending-native-link"
    assert state["native_parents_found"] == 0
    assert state["native_sub_issues_found"] == 0
    assert state["cycles_found"] == 0
    assert state["old_relationships_disturbed"] == 0
    assert state["repair_performed"] is False
    assert "does NOT claim the planned native edges exist" in str(state["claim"])
    # A positive control is recorded, so the empty result cannot be mistaken
    # for a broken or unsupported query.
    assert "#402" in str(state["positive_control"])


def test_the_markethub_exception_is_recorded_as_accepted_not_repaired() -> None:
    """#435's real, user-accepted exception must not be smoothed over."""

    gap = next(item for item in GAPS if item.gap_id == "G-435-FUTURES")
    assert "explicitly accepted" in gap.remediation
    assert "stays authoritative" in gap.remediation
    assert "rather than being closed as" in gap.remediation
    ticket = next(item for item in ALL_TICKETS if item.ticket == "#435")
    assert ticket.github_state == "OPEN"
    assert "225 day-gap rows" in ticket.note


# ---------------------------------------------------------------------------
# The rollup obeys the package's own repo-wide invariants.
# ---------------------------------------------------------------------------


def test_the_published_index_file_matches_the_module_exactly() -> None:
    """`a0_acceptance_evidence_index.json` is generated, never hand-edited.

    If the two ever disagree, the published index is stale and this fails
    rather than letting a reader trust it.  `/docs` is git-ignored apart from
    force-added files, so the test skips on a checkout that lacks it.
    """

    path = _REPO_ROOT / "docs" / "research" / "a0" / "a0_acceptance_evidence_index.json"
    if not path.exists():
        pytest.skip("published index not present on this checkout")
    published = json.loads(path.read_text(encoding="utf-8"))
    assert published == json.loads(
        json.dumps(final_rollup_readback(), ensure_ascii=False)
    )


def test_the_rollup_module_depends_on_the_standard_library_only() -> None:
    path = _PACKAGE_DIR / "research_a0_final_rollup.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    assert roots <= set(sys.stdlib_module_names) | {_PACKAGE}


def test_the_rollup_adds_no_product_logic_and_reaches_no_service() -> None:
    """It is an index. It must not acquire an engine, a client or a store."""

    source = (_PACKAGE_DIR / "research_a0_final_rollup.py").read_text(encoding="utf-8")
    for forbidden in ("import subprocess", "import socket", "import urllib", "requests"):
        assert forbidden not in source
