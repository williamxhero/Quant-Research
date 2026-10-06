"""Focused R4-T3 Comparison Reader contract tests."""

from __future__ import annotations

from html import unescape
from urllib.parse import parse_qsl, urlsplit

import pytest

from manager_gui import ReadModelStatus
from manager_gui.provider import FORBIDDEN_PROVIDER_METHODS, public_provider_methods
from manager_gui.reader import ClaimKind, ProjectionMode
from manager_gui.web.comparison_reader import (
    COMPARISON_READER_RESOURCE,
    ComparisonReaderAxis,
    ComparisonReaderAxisState,
    ComparisonReaderFixtureState,
    ComparisonReaderOutcome,
    ComparisonReaderViewModel,
    build_comparison_reader_fixture,
    compare_reader_objects,
    comparison_reader_fixture_provider,
    project_comparison_reader,
    render_comparison_reader,
    render_comparison_reader_view,
)
from manager_gui.web.i18n import Locale, Translator
from manager_gui.web.i18n.catalog import CATALOG

EN = Translator(Locale.EN, strict=True, catalog=CATALOG)
ZH = Translator(Locale.ZH_CN, strict=True, catalog=CATALOG)


def test_all_axes_are_explicit_and_gate_mismatch_refuses_comparison() -> None:
    equal = ComparisonReaderViewModel.from_read_model(build_comparison_reader_fixture("equal"))
    assert equal.result is ComparisonReaderOutcome.EQUAL
    assert tuple(axis.axis for axis in equal.axes) == tuple(ComparisonReaderAxis)
    assert all(axis.state is ComparisonReaderAxisState.EQUAL for axis in equal.axes)

    refused = ComparisonReaderViewModel.from_read_model(
        build_comparison_reader_fixture(ComparisonReaderFixtureState.NOT_COMPARABLE)
    )
    assert refused.result is ComparisonReaderOutcome.NOT_COMPARABLE
    assert refused.comparison is not None
    assert refused.comparison.axis("snapshot").state is ComparisonReaderAxisState.NOT_COMPARABLE
    assert refused.comparison.not_comparable_axes == ("snapshot",)
    assert refused.comparison.success_rate is None
    assert refused.comparison.ranking is None
    assert refused.comparison.denominator is None


def test_missing_ordinary_axis_is_missing_but_missing_gate_is_not_comparable() -> None:
    model = build_comparison_reader_fixture("missing")
    view = ComparisonReaderViewModel.from_read_model(model)
    assert view.result is ComparisonReaderOutcome.MISSING
    assert view.comparison is not None
    assert view.comparison.axis("currency").state is ComparisonReaderAxisState.MISSING

    left = {"axes": {"identity": "same", "snapshot": "one"}}
    right = {"axes": {"identity": "same"}}
    result = compare_reader_objects(left, right)
    assert result.axis("snapshot").state is ComparisonReaderAxisState.NOT_COMPARABLE
    assert result.result is ComparisonReaderOutcome.NOT_COMPARABLE


def test_explicit_axis_declaration_wins_without_inference() -> None:
    result = compare_reader_objects(
        {"object_type": "package", "object_id": "left", "axes": {"identity": "same"}},
        {"object_type": "package", "object_id": "right", "axes": {"identity": "same"}},
        axis_results={
            "identity": {"state": "equal", "reason": "Owner declaration <keep>"},
            "costs": {"state": "missing"},
        },
    )
    assert result.axis("identity").state is ComparisonReaderAxisState.EQUAL
    assert result.axis("identity").reason == "Owner declaration <keep>"
    assert result.axis("costs").state is ComparisonReaderAxisState.MISSING


def test_projection_preserves_v0_data_and_exact_transport_bytes() -> None:
    model = build_comparison_reader_fixture("different")
    raw_bytes = model.to_json().encode("utf-8")
    projection = project_comparison_reader(model, raw_bytes=raw_bytes, sample=True)
    assert projection.raw_source.raw_bytes == raw_bytes
    assert projection.to_dict()["data"] == model.data
    assert projection.sample_data is not None
    assert projection.sample_data.fixture_state == "complete"  # fixture URL provenance is explicit
    assert any(claim.kind is ClaimKind.DERIVED for claim in projection.claims)
    assert projection.snapshot_token == model.snapshot_token


def test_reader_expert_raw_modes_keep_context_and_no_statistics() -> None:
    model = build_comparison_reader_fixture("not_comparable")
    context = "/?view=comparison&lang=en&filter=a&filter=b&filter="
    reader = render_comparison_reader(model, query_context=context, translator=EN)
    expert = render_comparison_reader(
        model, query_context=context, translator=EN, mode=ProjectionMode.EXPERT
    )
    raw = render_comparison_reader(
        model, query_context=context, translator=EN, mode=ProjectionMode.RAW
    )
    for document in (reader, expert, raw):
        assert 'data-reader-hook="comparison-reader-view"' in document
        assert "filter=a" in document and "filter=b" in document
        assert "Comparison was refused" in document or "refused" in document.lower()
    assert 'data-comparison-result="not_comparable"' in reader
    assert 'data-axis="snapshot" data-axis-state="not_comparable"' in reader
    assert 'data-statistics="not-generated"' in reader
    assert 'name="success_rate"' not in reader
    assert 'name="ranking"' not in reader
    assert 'name="denominator"' not in reader
    assert 'data-v0-schema="manager-gui.manager-read-model.v0"' in raw
    assert 'data-expert-axis="snapshot"' in expert


def test_owner_values_are_escaped_once_and_machine_values_are_not_translated() -> None:
    model = build_comparison_reader_fixture("different")
    document = render_comparison_reader(model, translator=EN)
    assert 'data-owner-text="true"' in document
    assert 'data-owner-text="true"' in document
    assert "Owner comparison note &lt;keep exactly&gt;" in document
    assert 'translate="no">strategy-left</span>' in document
    assert 'translate="no">strategy-right</span>' in document
    assert "strategy-left" in document and "strategy-right" in document
    assert "&amp;lt;" not in document


def test_source_links_retain_repeated_context_and_related_context_links_are_stable() -> None:
    context = "/?view=comparison&fixture=equal&filter=a&filter=b&filter="
    document = render_comparison_reader(
        build_comparison_reader_fixture("equal"), query_context=context, translator=EN
    )
    links = [
        unescape(part.split('href="', 1)[1].split('"', 1)[0])
        for part in document.split("<a ")
        if "comparison-evidence-link" in part
    ]
    assert links
    query = parse_qsl(urlsplit(links[0]).query, keep_blank_values=True)
    assert query.count(("filter", "a")) == 1
    assert query.count(("filter", "b")) == 1
    assert query.count(("filter", "")) == 1
    assert "view=evidence" in links[0]
    assert "comparison-lineage-link" in document


def test_bilingual_axis_labels_and_dom_shape() -> None:
    model = build_comparison_reader_fixture("different")
    en = render_comparison_reader(model, translator=EN)
    zh = render_comparison_reader(model, translator=ZH)
    assert en.count("data-axis=") == len(ComparisonReaderAxis)
    assert zh.count("data-axis=") == len(ComparisonReaderAxis)
    assert "Comparison Reader" in en
    assert "比较阅读器" in zh
    assert "Different" in en and "不同" in zh
    assert 'data-axis="costs" data-axis-state="different"' in en
    assert 'data-axis="costs" data-axis-state="different"' in zh
    assert 'data-comparison-result="different"' in en
    assert 'data-comparison-result="different"' in zh


def test_provider_hook_is_read_only_and_uses_comparison_resource() -> None:
    class CountingProvider:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None]] = []

        def read(self, resource: str = "atlas", *, snapshot_token: str | None = None):
            self.calls.append((resource, snapshot_token))
            return build_comparison_reader_fixture("different")

    provider = CountingProvider()
    rendered = render_comparison_reader_view(
        provider, snapshot_token="reader-request", translator=EN
    )
    assert provider.calls == [(COMPARISON_READER_RESOURCE, "reader-request")]
    assert 'data-comparison-result="different"' in rendered

    fixture_provider = comparison_reader_fixture_provider("equal")
    assert fixture_provider.read().availability.status is ReadModelStatus.DERIVED
    assert FORBIDDEN_PROVIDER_METHODS.isdisjoint(public_provider_methods(fixture_provider))
    with pytest.raises(ValueError, match="does not serve resource"):
        fixture_provider.read("atlas")


def test_read_model_status_gaps_are_not_comparison_results() -> None:
    model = build_comparison_reader_fixture("blocked")
    view = ComparisonReaderViewModel.from_read_model(model)
    assert view.comparison is None
    rendered = render_comparison_reader(view, translator=EN)
    assert 'data-status="blocked"' in rendered
    assert 'data-comparison-result="different"' not in rendered
    assert "comparison read seam is blocked" in rendered


def test_catalog_rendering_does_not_mutate_v0_envelope() -> None:
    model = build_comparison_reader_fixture("equal")
    before = model.to_json()
    render_comparison_reader(model, translator=EN)
    render_comparison_reader(model, translator=ZH)
    assert model.to_json() == before


@pytest.mark.parametrize(
    "state", ["equal", "different", "missing", "not_comparable", "incomparable"]
)
def test_fixture_states_are_public_and_deterministic(state: str) -> None:
    first = build_comparison_reader_fixture(state)
    second = build_comparison_reader_fixture(state)
    assert first.to_json() == second.to_json()
    assert ComparisonReaderViewModel.from_read_model(first).result is not None
