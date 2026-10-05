"""Focused S5-T1 tests for the methodology archive and renderer."""

from __future__ import annotations

from typing import cast

from manager_gui import Availability, Derivation, ManagerReadModel, ReadModelStatus, SourceReference
from manager_gui.models import JSONValue
from manager_gui.web.i18n import Locale, Translator
from manager_gui.web.i18n.catalog.l3_method_history import ENTRIES
from manager_gui.web.methodology import (
    CATEGORY_ORDER,
    MethodologyFixtureState,
    MethodologyIndexState,
    MethodologyViewModel,
    build_methodology_fixture,
    methodology_fixture_provider,
    render_methodology,
    render_methodology_view,
)


def test_complete_fixture_keeps_five_categories_and_required_entries_separate() -> None:
    model = build_methodology_fixture(MethodologyFixtureState.COMPLETE)
    view = MethodologyViewModel.from_read_model(model)

    assert tuple(group.category for group in view.groups) == CATEGORY_ORDER
    assert all(group.category in CATEGORY_ORDER for group in view.groups)
    assert {method.category for method in view.methods} == set(CATEGORY_ORDER)
    assert {method.title for method in view.methods} >= {
        "G0",
        "Golden Genome Flow",
        "Qualification policy",
        "Memory policy",
        "Visibility policy",
        "Currency policy",
    }
    g0 = next(method for method in view.methods if method.method_id == "g0")
    assert g0.version == "g0-v1"
    assert g0.usage_count == 12
    assert len(g0.usage_records) == 1
    assert len(g0.associated_results) == 1
    assert len(g0.validity_evidence) == 1
    assert g0.usage_count != len(g0.validity_evidence)
    assert view.as_of == "2026-10-03T09:00:00Z"
    assert view.snapshot_token == "methodology-complete-v0"

    document = render_methodology(view, translator=Translator(Locale.EN))
    for label in (
        "Workflow / process",
        "Statistical protocol",
        "Policy",
        "Benchmark",
        "Operational constraint",
        "G0",
        "Golden Genome Flow",
        "Qualification policy",
        "Memory policy",
        "Visibility policy",
        "Currency policy",
    ):
        assert label in document
    assert "Usage count" in document
    assert "Validity evidence" in document
    assert "methodology-complete-v0" in document
    assert 'data-integration-hook="methodology-view"' in document


def test_superseded_method_is_explicit_and_not_collapsed_into_usage_or_validity() -> None:
    view = MethodologyViewModel.from_read_model(build_methodology_fixture("complete"))
    method = next(item for item in view.methods if item.method_id == "golden-genome-flow")

    assert method.superseded is True
    assert method.superseded_by == "golden-genome-flow-v3"
    assert method.superseded_label == "Superseded"
    assert method.usage_count == 4
    assert method.validity_evidence == ()
    rendered = render_methodology(view, translator=Translator(Locale.EN))
    assert 'data-method-id="golden-genome-flow"' in rendered
    assert 'data-superseded="true"' in rendered
    assert "Superseded" in rendered
    assert 'superseded by <span translate="no">golden-genome-flow-v3</span>' in rendered
    assert "Usage count" in rendered
    assert "Validity evidence" in rendered
    assert "Missing / Unconfirmed" in rendered


def test_missing_source_document_and_record_refs_are_not_invented() -> None:
    source = SourceReference(
        source_id="known-source",
        owner="owner",
        kind="record",
        locator="fixture://known-source",
    )
    model = ManagerReadModel(
        data=cast(
            JSONValue,
            {
                "index_state": "indexed",
                "methods": [
                    {
                        "method_id": "missing-refs",
                        "title": "Missing references",
                        "category": "benchmark",
                        "definition": "A record with incomplete provenance.",
                        "source_refs": ["unknown-source", "known-source"],
                        "document_refs": ["missing-document"],
                        "record_refs": ["missing-record"],
                    }
                ],
            },
        ),
        source_refs=(source,),
        as_of="2026-10-03T00:00:00Z",
        snapshot_token="missing-ref-snapshot",
        derivation=Derivation(kind="direct", inputs=(source.source_id,), version="v0"),
        availability=Availability(status=ReadModelStatus.KNOWN, complete=True),
    )

    method = MethodologyViewModel.from_read_model(model).methods[0]
    assert method.source_refs[0].source_id == "unknown-source"
    assert method.source_refs[0].available is False
    assert method.source_refs[1].locator == "fixture://known-source"
    assert method.document_refs[0].available is False
    assert method.record_refs[0].available is False

    rendered = render_methodology(model, translator=Translator(Locale.EN))
    assert '<span translate="no">unknown-source</span> — Missing / Unconfirmed' in rendered
    assert '<span translate="no">missing-document</span> — Missing / Unconfirmed' in rendered
    assert '<span translate="no">missing-record</span> — Missing / Unconfirmed' in rendered
    assert "fixture://known-source" in rendered


def test_empty_partial_stale_and_not_indexed_states_remain_distinct() -> None:
    expected = {
        MethodologyFixtureState.EMPTY: ('data-status="missing"', 'data-display-state="empty"'),
        MethodologyFixtureState.PARTIAL: ('data-status="known"', 'data-display-state="partial"'),
        MethodologyFixtureState.STALE: ('data-status="stale"', 'data-display-state="error"'),
        MethodologyFixtureState.NOT_INDEXED: (
            'data-status="api_unavailable"',
            'data-index-state="not_indexed"',
        ),
    }
    for state, markers in expected.items():
        rendered = render_methodology(
            build_methodology_fixture(state), translator=Translator(Locale.EN)
        )
        for marker in markers:
            assert marker in rendered

    assert "No methodology methods are recorded in this scope." in render_methodology(
        build_methodology_fixture("empty"), translator=Translator(Locale.EN)
    )
    assert "The approved methodology document index is not indexed." in render_methodology(
        build_methodology_fixture("not_indexed"), translator=Translator(Locale.EN)
    )
    partial = MethodologyViewModel.from_read_model(build_methodology_fixture("partial"))
    assert partial.read_model.availability.complete is False
    assert partial.index_state is MethodologyIndexState.INDEXED
    stale = MethodologyViewModel.from_read_model(build_methodology_fixture("stale"))
    assert stale.read_model.availability.status is ReadModelStatus.STALE
    assert stale.snapshot_token == "methodology-stale-v0"


def test_provider_hook_reads_only_methodology_resource_and_preserves_snapshot() -> None:
    class CountingProvider:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None]] = []

        def read(
            self,
            resource: str = "atlas",
            *,
            snapshot_token: str | None = None,
        ) -> ManagerReadModel:
            self.calls.append((resource, snapshot_token))
            return build_methodology_fixture("complete")

    provider = CountingProvider()
    document = render_methodology_view(
        provider, snapshot_token="requested-snapshot", translator=Translator(Locale.EN)
    )

    assert provider.calls == [("methodology", "requested-snapshot")]
    assert "G0" in document
    assert "read-only" in document


def test_methodology_catalog_has_bilingual_entries_and_localizes_page_chrome() -> None:
    model = build_methodology_fixture("complete")
    zh = render_methodology(model, translator=Translator(Locale.ZH_CN))
    en = render_methodology(model, translator=Translator(Locale.EN))

    assert (
        Translator(Locale.ZH_CN, strict=True, catalog=ENTRIES).t("methodology.title")
        == "研究方法库"
    )
    assert "研究方法库" in zh
    assert "Methodology" in en
    assert "研究方法库 · 只读" in zh
    assert "Methodology archive · read-only" in en


def test_fixture_provider_is_read_only_and_rejects_other_resources() -> None:
    provider = methodology_fixture_provider("complete")
    assert provider.read().availability.status is ReadModelStatus.KNOWN
    try:
        provider.read("atlas")
    except ValueError as error:
        assert "does not serve resource" in str(error)
    else:  # pragma: no cover - the provider must keep its resource boundary
        raise AssertionError("methodology fixture provider served an unrelated resource")
