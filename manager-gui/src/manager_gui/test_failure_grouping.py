"""Focused S4-T3 tests for Derived success/failure grouping."""

from __future__ import annotations

from functools import partial

from manager_gui.models import ReadModelStatus
from manager_gui.provider import FORBIDDEN_PROVIDER_METHODS, public_provider_methods
from manager_gui.web.failure_grouping import (
    FailureGroupingViewModel,
    GroupingFixtureState,
    GroupOutcome,
    build_failure_grouping_fixture,
    derive_success_failure_groupings,
    failure_grouping_fixture_provider,
)
from manager_gui.web.failure_grouping import (
    render_failure_grouping as _render_failure_grouping,
)
from manager_gui.web.failure_grouping import (
    render_failure_grouping_view as _render_failure_grouping_view,
)
from manager_gui.web.i18n import Translator
from manager_gui.web.i18n.catalog import CATALOG, merge
from manager_gui.web.i18n.catalog.l4_memory import ENTRIES

EN_TRANSLATOR = Translator("en", strict=True, catalog=merge(CATALOG, ENTRIES))
render_failure_grouping = partial(_render_failure_grouping, translator=EN_TRANSLATOR)
render_failure_grouping_view = partial(_render_failure_grouping_view, translator=EN_TRANSLATOR)


def test_complete_fixture_keeps_rule_scope_count_participants_and_source_refs() -> None:
    view = FailureGroupingViewModel.from_read_model(build_failure_grouping_fixture("complete"))

    assert [group.outcome for group in view.groups] == [GroupOutcome.SUCCESS, GroupOutcome.FAILURE]
    success, failure = view.groups
    assert success.derived is True
    assert success.rule == "bucket explicit terminal outcome by outcome and protocol"
    assert success.input_scope == ("study-fixture-1", "runs:fixture-2026-Q3")
    assert success.sample_count == 2
    assert success.participant_ids == ("run-success-1", "run-success-2")
    assert success.source_refs[0].source_id == "grouping-fixture-runs"
    assert failure.outcome is GroupOutcome.FAILURE

    rendered = render_failure_grouping(view)
    assert 'data-integration-hook="failure-grouping-view"' in rendered
    assert 'data-group-status="derived"' in rendered
    for text in (
        "Named Derived groups",
        "not an owner fact",
        "bucket explicit terminal outcome by outcome and protocol",
        "runs:fixture-2026-Q3",
        "Sample count",
        "run-success-1",
        "run-failure-1",
        "fixture://manager-gui/runs",
    ):
        assert text in rendered


def test_grouping_is_derived_and_never_promoted_to_owner_fact_or_metric() -> None:
    view = FailureGroupingViewModel.from_read_model(build_failure_grouping_fixture("complete"))
    assert all(group.status is ReadModelStatus.DERIVED for group in view.groups)
    assert all(group.denominator is None for group in view.groups)
    rendered = render_failure_grouping(view)
    assert 'data-statistics="not-generated"' in rendered
    assert "does not recalculate metrics" in rendered
    assert 'data-status="known"' not in rendered
    assert 'data-status="published"' not in rendered


def test_structural_derivation_excludes_missing_blocked_and_incomparable_records() -> None:
    groups = derive_success_failure_groupings(
        [
            {"record_id": "success-1", "outcome": "success"},
            {"record_id": "failure-1", "outcome": "failed"},
            {"record_id": "blocked-1", "outcome": "blocked"},
            {"record_id": "missing-1"},
            {"record_id": "incomparable-1", "outcome": "incomparable"},
        ],
        rule="bucket terminal outcomes",
        input_scope=("runs:fixture",),
    )
    assert [group.outcome for group in groups] == [GroupOutcome.SUCCESS, GroupOutcome.FAILURE]
    assert groups[0].sample_count == 1
    assert groups[1].participant_ids == ("failure-1",)
    assert "blocked-1" not in groups[1].participant_ids
    assert "missing-1" not in groups[1].participant_ids


def test_missing_blocked_and_incompatible_fixtures_remain_undetermined() -> None:
    expected = {
        GroupingFixtureState.MISSING: ReadModelStatus.MISSING,
        GroupingFixtureState.BLOCKED: ReadModelStatus.BLOCKED,
        GroupingFixtureState.INCOMPARABLE: ReadModelStatus.INCOMPARABLE,
    }
    for fixture, status in expected.items():
        model = build_failure_grouping_fixture(fixture)
        view = FailureGroupingViewModel.from_read_model(model)
        assert model.availability.status is status
        assert view.groups == ()
        rendered = render_failure_grouping(view)
        assert f'data-grouping-status="{status.value}"' in rendered
        assert 'data-group-outcome="failure"' not in rendered
        assert model.availability.reason is not None
        assert model.availability.reason in rendered


def test_provider_hook_reads_grouping_resource_once_and_is_read_only() -> None:
    class CountingProvider:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None]] = []

        def read(self, resource: str = "atlas", *, snapshot_token: str | None = None):
            self.calls.append((resource, snapshot_token))
            return build_failure_grouping_fixture("complete")

    provider = CountingProvider()
    rendered = render_failure_grouping_view(provider, snapshot_token="grouping-request")
    assert provider.calls == [("failure_grouping", "grouping-request")]
    assert "Derived success/failure grouping" in rendered

    fixture_provider = failure_grouping_fixture_provider("complete")
    assert fixture_provider.read().availability.status is ReadModelStatus.DERIVED
    methods = public_provider_methods(fixture_provider)
    assert set(methods) <= {"read"}
    assert FORBIDDEN_PROVIDER_METHODS.isdisjoint(methods)
    try:
        fixture_provider.read("atlas")
    except ValueError as error:
        assert "does not serve resource" in str(error)
    else:  # pragma: no cover - the provider must keep the resource boundary
        raise AssertionError("grouping fixture provider served an unrelated resource")


def test_unnamed_records_never_become_a_group_and_modules_stay_read_only() -> None:
    from pathlib import Path

    from manager_gui import Availability, Derivation, ManagerReadModel

    model = ManagerReadModel(
        data={"records": [{"record_id": "run-1", "outcome": "failed"}]},
        source_refs=(),
        as_of="2026-10-03T13:30:00Z",
        snapshot_token="unnamed-records",
        derivation=Derivation(kind="direct", version="v0"),
        availability=Availability(status=ReadModelStatus.KNOWN, complete=True),
    )
    view = FailureGroupingViewModel.from_read_model(model)
    assert view.groups == ()
    assert 'data-grouping-empty="true"' in render_failure_grouping(view)

    web = Path(__file__).parent / "web"
    for name in ("failure_grouping.py", "evidence_comparison.py"):
        source = (web / name).read_text(encoding="utf-8")
        for forbidden in (
            "sqlite3",
            "subprocess",
            "open(",
            ".write_text(",
            "from .comparison",
            "from . import comparison",
        ):
            assert forbidden not in source, f"{name} must stay read-only: {forbidden}"
