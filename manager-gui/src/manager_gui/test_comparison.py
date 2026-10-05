"""Focused S2-T2 tests for deterministic Genome comparison."""

from __future__ import annotations

from manager_gui.models import ReadModelStatus
from manager_gui.web.comparison import (
    ComparisonFixtureState,
    ComparisonResult,
    ComparisonViewModel,
    build_genome_comparison_fixture,
    compare_genomes,
    comparison_fixture_provider,
    genome_comparison_link,
    render_genome_comparison,
    render_genome_comparison_view,
)
from manager_gui.web.i18n import Locale, Translator


def test_equal_and_different_comparisons_keep_changed_paths_explicit() -> None:
    equal = compare_genomes(
        {"genome_id": "left", "behavior": {"entry": {"rule": "same"}}},
        {"genome_id": "right", "behavior": {"entry": {"rule": "same"}}},
    )
    different = compare_genomes(
        {"genome_id": "left", "behavior": {"entry": {"rule": "same"}}},
        {"genome_id": "right", "behavior": {"entry": {"rule": "changed"}}},
    )

    assert equal.result is ComparisonResult.EQUAL
    assert equal.changed_paths == ()
    assert different.result is ComparisonResult.DIFFERENT
    assert different.changed_paths == ("behavior.entry.rule",)
    assert different.missing_axes == ()
    assert different.incompatible_axes == ()


def test_missing_and_incompatible_axes_are_incomparable_without_defaults() -> None:
    missing = compare_genomes(
        {"genome_id": "left", "axes": {"schema": "v1", "data_snapshot": "s1"}},
        {"genome_id": "right", "axes": {"schema": "v1"}},
    )
    incompatible = compare_genomes(
        {"genome_id": "left", "axes": {"data_snapshot": {"id": "s1", "compatible": False}}},
        {"genome_id": "right", "axes": {"data_snapshot": {"id": "s2", "compatible": False}}},
    )

    assert missing.result is ComparisonResult.INCOMPARABLE
    assert missing.missing_axes == ("data_snapshot",)
    assert missing.changed_paths == ()
    assert incompatible.result is ComparisonResult.INCOMPARABLE
    assert incompatible.incompatible_axes == ("data_snapshot",)
    assert incompatible.changed_paths == ()


def test_comparison_fixture_preserves_provenance_as_of_snapshot_and_axis_lists() -> None:
    view = ComparisonViewModel.from_read_model(build_genome_comparison_fixture("incomparable"))
    assert view.comparison is not None
    comparison = view.comparison
    assert comparison.result is ComparisonResult.INCOMPARABLE
    assert comparison.incompatible_axes == ("data_requirements.version",)
    assert comparison.left_provenance["candidate"] == "candidate-genome-left"
    assert comparison.right_provenance["candidate"] == "candidate-genome-right"
    assert comparison.left_as_of == "2026-10-03T10:00:00Z"
    assert comparison.left_snapshot == "snapshot-left-v1"
    assert view.as_of == "2026-10-03T10:00:00Z"
    assert view.snapshot_token == "comparison-fixture-incomparable-v0"

    document = render_genome_comparison(view, translator=Translator(Locale.EN))
    chinese_document = render_genome_comparison(view)
    assert "不兼容轴" in chinese_document
    assert "不可比较" in chinese_document
    assert 'data-integration-hook="strategy-genome-comparison-view"' in document
    assert 'class="comparison-context-link"' in document
    assert 'data-comparison-result="incomparable"' in document
    assert "Incompatible axes" in document
    assert "data_requirements.version" in document
    assert "candidate-genome-left" in document
    assert "snapshot-left-v1" in document


def test_comparison_missing_does_not_claim_equal_or_different() -> None:
    model = build_genome_comparison_fixture(ComparisonFixtureState.MISSING)
    view = ComparisonViewModel.from_read_model(model)
    assert view.comparison is None
    document = render_genome_comparison(view, translator=Translator(Locale.EN))
    chinese_document = render_genome_comparison(view)
    assert "没有明确比较记录，不能声称相等或不同" in chinese_document
    assert 'data-status="missing"' in document
    assert 'data-comparison-result="not recorded"' in document
    assert "No explicit Genome comparison is recorded" in document
    assert "Result: equal" not in document
    assert "Result: different" not in document


def test_blocked_stale_integrity_and_api_unavailable_are_not_comparison_results() -> None:
    expected = {
        ComparisonFixtureState.BLOCKED: ReadModelStatus.BLOCKED,
        ComparisonFixtureState.STALE: ReadModelStatus.STALE,
        ComparisonFixtureState.INTEGRITY_FAILURE: ReadModelStatus.INTEGRITY_FAILURE,
        ComparisonFixtureState.API_UNAVAILABLE: ReadModelStatus.API_UNAVAILABLE,
    }
    for fixture, status in expected.items():
        model = build_genome_comparison_fixture(fixture)
        document = render_genome_comparison(model, translator=Translator(Locale.EN))
        assert model.availability.status is status
        assert f'data-status="{status.value}"' in document
        assert 'data-display-state="error"' in document
        assert 'data-comparison-result="not recorded"' in document
        assert model.availability.reason is not None
        assert model.availability.reason in document


def test_comparison_context_link_and_provider_hook_are_stable_and_read_only() -> None:
    first = genome_comparison_link(
        "left", "right", query_context="/?fixture=diff&panel=compare&q=signal"
    )
    second = genome_comparison_link(
        "left", "right", query_context="/?q=signal&panel=compare&fixture=diff"
    )
    assert first == second
    assert "view=strategy-genome-comparison" in first
    assert "left_genome_id=left" in first
    assert "right_genome_id=right" in first
    assert "fixture=diff" in first

    class CountingProvider:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None]] = []

        def read(self, resource: str = "atlas", *, snapshot_token: str | None = None):
            self.calls.append((resource, snapshot_token))
            return build_genome_comparison_fixture("different")

    provider = CountingProvider()
    document = render_genome_comparison_view(
        provider,
        snapshot_token="comparison-request",
        query_context="/?fixture=diff&panel=compare",
        translator=Translator(Locale.EN),
    )
    assert provider.calls == [("genome_comparison", "comparison-request")]
    assert 'data-comparison-result="different"' in document
    assert "fixture=diff" in document
    assert "panel=compare" in document
    fixture_provider = comparison_fixture_provider("equal")
    assert fixture_provider.read().availability.status is ReadModelStatus.DERIVED
    assert (
        tuple(name for name in dir(fixture_provider) if name in {"write", "update", "delete"}) == ()
    )
