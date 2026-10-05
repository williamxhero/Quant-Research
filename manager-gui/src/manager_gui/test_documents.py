"""Focused tests for the S5-T2 approved Source Document index."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from manager_gui import Availability, Derivation, ManagerReadModel, ReadModelStatus, SourceReference
from manager_gui.models import JSONValue
from manager_gui.web.documents import (
    DOCUMENT_SCOPES,
    DOCUMENT_TYPES,
    ApprovedDirectoryBoundary,
    DocumentIndexState,
    SourceDocumentsViewModel,
    build_source_documents_fixture,
    render_source_documents_view,
)
from manager_gui.web.i18n import Locale, Translator
from manager_gui.web.i18n.catalog.l3_method_history import ENTRIES


def _documents_model(
    data: object, status: ReadModelStatus = ReadModelStatus.KNOWN
) -> ManagerReadModel:
    source = SourceReference(
        source_id="documents-source",
        owner="test-owner",
        kind="source-document-index",
        locator="fixture://tests/documents",
        schema="test.documents.v0",
        revision="r1",
    )
    return ManagerReadModel(
        data=cast(JSONValue, data),
        source_refs=(source,),
        as_of="2026-10-03T12:00:00Z",
        snapshot_token="documents-test-v1",
        derivation=Derivation(kind="direct", inputs=(source.source_id,), version="v0"),
        availability=Availability(status=status, complete=status is ReadModelStatus.KNOWN),
    )


def test_document_categories_and_fixture_navigation_are_stable() -> None:
    for scope in DOCUMENT_SCOPES:
        view = SourceDocumentsViewModel.from_read_model(build_source_documents_fixture(scope))
        assert view.state is DocumentIndexState.READY
        assert tuple(view.categories) == DOCUMENT_TYPES
        assert {document.document_type for document in view.documents} == set(DOCUMENT_TYPES)
        assert f'data-document-scope="{scope}"' in view.render()


def test_documents_expose_forward_and_reverse_record_citations() -> None:
    model = _documents_model(
        {
            "documents": [
                {
                    "document_id": "doc-report",
                    "document_type": "report",
                    "version": "v2",
                    "source_locator": "fixture://docs/report-v2",
                    "updated_at": "2026-10-03T10:00:00Z",
                    "record_citations": ["run-1", "publication-1"],
                    "reverse_citations": ["doc-retro"],
                },
                {
                    "document_id": "doc-retro",
                    "document_type": "retrospective",
                    "version": "v1",
                    "source_locator": "fixture://docs/retro-v1",
                    "updated_at": "2026-10-02T10:00:00Z",
                    "record_citations": ["run-1"],
                },
            ]
        }
    )

    view = SourceDocumentsViewModel.from_read_model(model)

    assert view.documents[0].document_id == "doc-report"
    assert view.documents[0].record_citations == ("run-1", "publication-1")
    assert view.documents[0].reverse_citations == ("doc-retro",)
    assert view.reverse_citations["run-1"] == ("doc-report", "doc-retro")
    rendered = view.render(translator=Translator(Locale.EN))
    assert "record citations" in rendered
    assert "reverse citations" in rendered
    assert "doc-report" in rendered and "doc-retro" in rendered


def test_duplicate_versions_are_not_silently_selected() -> None:
    model = _documents_model(
        {
            "documents": [
                {
                    "document_id": "doc-plan",
                    "document_type": "plan",
                    "version": "v1",
                    "source_locator": "fixture://docs/plan-v1",
                    "updated_at": "2026-10-01T10:00:00Z",
                },
                {
                    "document_id": "doc-plan",
                    "document_type": "plan",
                    "version": "v2",
                    "source_locator": "fixture://docs/plan-v2",
                    "updated_at": "2026-10-02T10:00:00Z",
                },
            ]
        }
    )

    view = SourceDocumentsViewModel.from_read_model(model)

    assert view.state is DocumentIndexState.VERSION_CONFLICT
    assert len(view.documents) == 2
    assert "no version is silently selected" in view.render(translator=Translator(Locale.EN))


def test_missing_not_indexed_and_api_unavailable_states_stay_distinct() -> None:
    missing = SourceDocumentsViewModel.from_read_model(
        _documents_model({}, ReadModelStatus.MISSING)
    )
    not_indexed = SourceDocumentsViewModel.from_read_model(_documents_model({"documents": []}))
    unavailable = SourceDocumentsViewModel.from_read_model(
        _documents_model({}, ReadModelStatus.API_UNAVAILABLE)
    )

    assert missing.state is DocumentIndexState.MISSING
    assert not_indexed.state is DocumentIndexState.NOT_INDEXED
    assert unavailable.state is DocumentIndexState.API_UNAVAILABLE
    assert 'data-document-index-state="missing"' in missing.render()
    assert 'data-document-index-state="not-indexed"' in not_indexed.render()
    assert 'data-document-index-state="api-unavailable"' in unavailable.render()


def test_local_locator_requires_explicit_approved_directory_and_never_scans() -> None:
    approved_root = str(Path("D:/approved-documents"))
    model = _documents_model(
        {
            "documents": [
                {
                    "document_id": "doc-inside",
                    "document_type": "raw-evidence",
                    "version": "v1",
                    "source_locator": "D:/approved-documents/evidence.json",
                    "updated_at": "2026-10-01T10:00:00Z",
                },
                {
                    "document_id": "doc-outside",
                    "document_type": "raw-evidence",
                    "version": "v1",
                    "source_locator": "D:/not-approved/secret.json",
                    "updated_at": "2026-10-02T10:00:00Z",
                },
            ]
        }
    )
    boundary = ApprovedDirectoryBoundary((approved_root,))

    view = SourceDocumentsViewModel.from_read_model(model, boundary=boundary)

    assert not boundary.allows("D:/not-approved/secret.json")
    assert view.state is DocumentIndexState.BOUNDARY_BLOCKED
    rendered = view.render()
    assert "boundary" in rendered.lower()
    assert "D:/not-approved/secret.json" not in rendered


def test_documents_catalog_localizes_english_and_chinese_page_copy() -> None:
    model = build_source_documents_fixture("A0")
    zh = render_source_documents_view(model, scope="A0", translator=Translator(Locale.ZH_CN))
    en = render_source_documents_view(model, scope="A0", translator=Translator(Locale.EN))
    assert Translator(Locale.ZH_CN, strict=True, catalog=ENTRIES).t("documents.title") == "来源文档"
    assert "已批准索引" in zh
    assert "approved index" in en
    assert "A0 计划" in zh
    assert "A0 plan" in en


def test_documents_owner_text_is_not_translated_when_provenance_is_not_fixture() -> None:
    model = _documents_model(
        {
            "documents": [
                {
                    "document_id": "doc-owner",
                    "document_type": "report",
                    "title": "Owner Report",
                    "source_locator": "fixture://owner/report",
                }
            ]
        }
    )
    rendered = render_source_documents_view(model, translator=Translator(Locale.ZH_CN))
    assert "Owner Report" in rendered


def test_source_document_hook_reads_public_resource_once() -> None:
    class CountingProvider:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def read(
            self, resource: str = "atlas", *, snapshot_token: str | None = None
        ) -> ManagerReadModel:
            del snapshot_token
            self.calls.append(resource)
            return build_source_documents_fixture("S3")

    provider = CountingProvider()
    rendered = render_source_documents_view(provider, scope="S3")

    assert provider.calls == ["source_documents"]
    assert 'data-integration-hook="source-documents-view"' in rendered
    assert "S3" in rendered
