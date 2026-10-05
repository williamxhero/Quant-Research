"""Focused S4-T3 tests for general Evidence/object comparison."""

from __future__ import annotations

from manager_gui import ManagerReadModel
from manager_gui.models import ReadModelStatus
from manager_gui.provider import FORBIDDEN_PROVIDER_METHODS, public_provider_methods
from manager_gui.web.i18n import Locale, Translator
from manager_gui.web.evidence_comparison import (
    AxisComparisonState,
    ComparisonAxis,
    ComparisonOutcome,
    EvidenceComparisonFixtureState,
    EvidenceComparisonViewModel,
    build_evidence_comparison_fixture,
    compare_objects,
    evidence_comparison_fixture_provider,
    render_evidence_comparison,
    render_evidence_comparison_view,
)


def _render_evidence_comparison_en(
    view_or_model: EvidenceComparisonViewModel | ManagerReadModel,
    *,
    query_context: str | None = None,
) -> str:
    return render_evidence_comparison(
        view_or_model,
        query_context=query_context,
        translator=Translator(Locale.EN),
    )


def test_general_comparison_covers_all_declared_axes_and_is_not_s2_genome_comparison() -> None:
    view = EvidenceComparisonViewModel.from_read_model(build_evidence_comparison_fixture("equal"))

    assert view.result is ComparisonOutcome.EQUAL
    assert tuple(axis.axis for axis in view.axes) == tuple(ComparisonAxis)
    document = _render_evidence_comparison_en(view)
    assert 'data-integration-hook="evidence-comparison-view"' in document
    assert 'data-comparison-kind="general-object"' in document
    assert "not the S2 Strategy Genome comparison" in document
    assert "Genome comparison" not in document.split("not the S2 Strategy Genome comparison", 1)[1]


def test_different_and_missing_axes_are_explicit_without_defaults() -> None:
    different = EvidenceComparisonViewModel.from_read_model(
        build_evidence_comparison_fixture(EvidenceComparisonFixtureState.DIFFERENT)
    )
    assert different.result is ComparisonOutcome.DIFFERENT
    assert different.comparison is not None
    assert different.comparison.changed_axes == ("costs", "metric_definition")
    assert different.comparison.missing_axes == ()

    missing = EvidenceComparisonViewModel.from_read_model(
        build_evidence_comparison_fixture(EvidenceComparisonFixtureState.MISSING)
    )
    assert missing.comparison is None
    assert _render_evidence_comparison_en(missing).count("Result: equal") == 0

    partial = EvidenceComparisonViewModel.from_read_model(
        build_evidence_comparison_fixture(EvidenceComparisonFixtureState.PARTIAL)
    )
    assert partial.result is ComparisonOutcome.MISSING
    assert partial.comparison is not None
    assert partial.comparison.missing_axes == ("fills", "evidence_sections")
    rendered = _render_evidence_comparison_en(partial)
    assert 'data-axis="fills" data-axis-state="missing"' in rendered
    assert 'data-axis="evidence_sections" data-axis-state="missing"' in rendered


def test_protocol_and_data_version_incompatibility_never_become_different_or_failure() -> None:
    for state, axis in (
        (EvidenceComparisonFixtureState.PROTOCOL_INCOMPATIBLE, "protocol"),
        (EvidenceComparisonFixtureState.DATA_VERSION_INCONSISTENT, "data_version"),
    ):
        view = EvidenceComparisonViewModel.from_read_model(build_evidence_comparison_fixture(state))
        assert view.result is ComparisonOutcome.INCOMPARABLE
        assert view.comparison is not None
        assert view.comparison.incompatible_axes == (axis,)
        rendered = _render_evidence_comparison_en(view)
        assert f'data-axis="{axis}" data-axis-state="incomparable"' in rendered
        assert 'data-comparison-result="fail"' not in rendered


def test_blocked_integrity_and_api_unavailable_are_not_comparison_results() -> None:
    expected = {
        EvidenceComparisonFixtureState.BLOCKED: ReadModelStatus.BLOCKED,
        EvidenceComparisonFixtureState.INTEGRITY_FAILURE: ReadModelStatus.INTEGRITY_FAILURE,
        EvidenceComparisonFixtureState.API_UNAVAILABLE: ReadModelStatus.API_UNAVAILABLE,
    }
    for fixture, status in expected.items():
        model = build_evidence_comparison_fixture(fixture)
        view = EvidenceComparisonViewModel.from_read_model(model)
        assert model.availability.status is status
        assert view.comparison is None
        rendered = _render_evidence_comparison_en(view)
        assert f'data-read-status="{status.value}"' in rendered
        assert 'data-comparison-result="different"' not in rendered
        assert 'data-comparison-result="fail"' not in rendered
        assert model.availability.reason is not None
        assert model.availability.reason in rendered


def test_comparison_does_not_generate_metrics_or_rankings_without_denominator() -> None:
    view = EvidenceComparisonViewModel.from_read_model(
        build_evidence_comparison_fixture("different")
    )
    assert view.comparison is not None
    assert view.comparison.success_rate is None
    assert view.comparison.ranking is None
    rendered = _render_evidence_comparison_en(view)
    assert 'data-statistics="not-generated"' in rendered
    assert "does not recalculate metrics" in rendered
    assert 'name="success_rate"' not in rendered
    assert 'name="ranking"' not in rendered


def test_compare_objects_preserves_explicit_axis_state_and_source_refs() -> None:
    result = compare_objects(
        {"object_type": "package", "object_id": "left", "axes": {"identity": "same"}},
        {"object_type": "package", "object_id": "right", "axes": {"identity": "same"}},
        axis_results={"identity": {"state": "equal", "reason": "Owner declaration"}},
    )
    assert result.axis("identity").state is AxisComparisonState.EQUAL
    assert result.axis("identity").reason == "Owner declaration"
    assert len(result.axes) == len(ComparisonAxis)


def test_provider_hook_reads_only_comparison_resource_and_fixture_is_read_only() -> None:
    class CountingProvider:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None]] = []

        def read(self, resource: str = "atlas", *, snapshot_token: str | None = None):
            self.calls.append((resource, snapshot_token))
            return build_evidence_comparison_fixture("different")

    provider = CountingProvider()
    rendered = render_evidence_comparison_view(
        provider, snapshot_token="comparison-request", translator=Translator(Locale.EN)
    )
    assert provider.calls == [("evidence_comparison", "comparison-request")]
    assert 'data-comparison-result="different"' in rendered

    fixture_provider = evidence_comparison_fixture_provider("complete")
    assert fixture_provider.read().availability.status is ReadModelStatus.DERIVED
    assert tuple(
        name
        for name in public_provider_methods(fixture_provider)
        if name in {"write", "update", "delete"}
    ) == ()
    assert FORBIDDEN_PROVIDER_METHODS.isdisjoint(public_provider_methods(fixture_provider))
    try:
        fixture_provider.read("atlas")
    except ValueError as error:
        assert "does not serve resource" in str(error)
    else:  # pragma: no cover - the provider must keep the resource boundary
        raise AssertionError("comparison fixture provider served an unrelated resource")
