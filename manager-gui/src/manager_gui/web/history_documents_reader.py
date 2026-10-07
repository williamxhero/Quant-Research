"""Reader-mode adapters for source History and Source Documents.

The existing ``history`` and ``documents`` modules remain the Expert views.
This module adds only a typed, UI-owned explanation layer over their public
``ManagerReadModel`` envelopes.  It never infers a timeline from GUI times,
turns a plan or report into a canonical fact, opens a document, scans a
filesystem, or writes to an owner surface.
"""

# HTML fragments intentionally remain readable at the call site.
# ruff: noqa: E501

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from html import escape
from typing import TypeAlias, cast

from ..models import Derivation, JSONValue, ManagerReadModel, ReadModelStatus, SourceReference
from ..reader import (
    ClaimKind,
    FrozenJSON,
    ProjectionMode,
    ReaderAvailability,
    ReaderAvailabilityStatus,
    ReaderClaim,
    ReaderProjection,
    ReaderSummary,
    SampleData,
    project_read_model,
)
from ..reader.mode import ReaderURLState
from .documents import (
    DOCUMENT_SCOPES,
    DOCUMENTS_RESOURCE,
    ApprovedDirectoryBoundary,
    DocumentIndexState,
    SourceDocument,
    SourceDocumentsFixtureProvider,
    SourceDocumentsViewModel,
    _document_fixture_text,
    build_source_documents_fixture,
    render_source_documents,
)
from .history import (
    HISTORY_SCOPES,
    HistoryEvent,
    HistoryFixtureProvider,
    HistoryViewModel,
    _is_history_fixture,
    build_history_fixture,
    render_history,
)
from .i18n import Translator
from .locators import public_locator
from .navigation import PageWindow, ViewId, context_link
from .reader_surface import ReaderPage, render_reader_surface
from .source_support import source_support_entry
from .status import render_status_block

QueryContext: TypeAlias = str | Mapping[str, object] | None

HISTORY_READER_RESOURCE = "history"
DOCUMENTS_READER_RESOURCE = DOCUMENTS_RESOURCE
HISTORY_READER_RULE = "manager-gui.reader.history.v1"
DOCUMENTS_READER_RULE = "manager-gui.reader.documents.v1"
HISTORY_READER_VERSION = "v1"
DOCUMENTS_READER_VERSION = "v1"
HISTORY_READER_HOOK = "history-reader-view"
DOCUMENTS_READER_HOOK = "source-documents-reader-view"
HISTORY_READER_INTEGRATION_HOOK = "history-view"
DOCUMENTS_READER_INTEGRATION_HOOK = "source-documents-view"
HISTORY_DOCUMENTS_SCOPES: tuple[str, ...] = tuple(dict.fromkeys((*HISTORY_SCOPES, *DOCUMENT_SCOPES)))


def _mapping(value: object) -> Mapping[str, object] | None:
    return cast(Mapping[str, object], value) if isinstance(value, Mapping) else None


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


def _json_value(value: object) -> JSONValue:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        return None
    return cast(JSONValue, value)


def _scope(model: ManagerReadModel, selected: str | None) -> str | None:
    payload = _mapping(model.data) or {}
    return selected or _text(payload.get("scope")) or _text(payload.get("fixture"))


def _source_availability(model: ManagerReadModel) -> ReaderAvailability:
    selected = ReaderAvailability.from_v0(model.availability)
    if selected.status is ReaderAvailabilityStatus.KNOWN and any(
        error.code == "not_evaluated" for error in model.errors
    ):
        return ReaderAvailability(
            ReaderAvailabilityStatus.NOT_EVALUATED,
            False,
            selected.reason,
            selected.retryable,
        )
    return selected


def _claim_availability(model: ManagerReadModel) -> ReaderAvailability:
    selected = _source_availability(model)
    # A direct field in a derived/interpreted v0 envelope is still a known
    # owner field; the envelope status describes the acquisition boundary.
    if selected.status in {ReaderAvailabilityStatus.DERIVED, ReaderAvailabilityStatus.INTERPRETED}:
        return ReaderAvailability(ReaderAvailabilityStatus.KNOWN, selected.complete, selected.reason, selected.retryable)
    return selected


def _gap_availability(model: ManagerReadModel, reason: str) -> ReaderAvailability:
    selected = _source_availability(model)
    status = selected.status
    if status in {ReaderAvailabilityStatus.KNOWN, ReaderAvailabilityStatus.DERIVED, ReaderAvailabilityStatus.INTERPRETED}:
        status = ReaderAvailabilityStatus.MISSING
    return ReaderAvailability(status, False, reason or selected.reason, selected.retryable)


def _gap_kind(status: ReaderAvailabilityStatus) -> ClaimKind:
    if status in {ReaderAvailabilityStatus.BLOCKED, ReaderAvailabilityStatus.INTEGRITY_FAILURE}:
        return ClaimKind.BLOCKED
    if status is ReaderAvailabilityStatus.STALE:
        return ClaimKind.STALE
    if status is ReaderAvailabilityStatus.INCOMPARABLE:
        return ClaimKind.INCOMPARABLE
    return ClaimKind.MISSING


def _refs(model: ManagerReadModel, source_id: str | None = None) -> tuple[SourceReference, ...]:
    if source_id:
        selected = tuple(ref for ref in model.source_refs if ref.source_id == source_id)
        if selected:
            return selected
    return tuple(model.source_refs)


def _direct_claim(
    claim_id: str,
    value: JSONValue,
    model: ManagerReadModel,
    *,
    source_id: str | None = None,
) -> ReaderClaim | None:
    refs = _refs(model, source_id)
    if not refs or model.availability.status not in {
        ReadModelStatus.KNOWN,
        ReadModelStatus.DERIVED,
        ReadModelStatus.INTERPRETED,
    }:
        return None
    availability = _claim_availability(model)
    if availability.status is not ReaderAvailabilityStatus.KNOWN:
        return None
    return ReaderClaim(
        claim_id,
        ClaimKind.KNOWN,
        refs,
        Derivation("direct", inputs=tuple(ref.source_id for ref in refs), version="v0"),
        availability,
        cast(FrozenJSON, value),
    )


def _gap_claim(
    claim_id: str,
    value: JSONValue,
    model: ManagerReadModel,
    reason: str,
    *,
    source_id: str | None = None,
) -> ReaderClaim | None:
    refs = _refs(model, source_id)
    if not refs:
        return None
    availability = _gap_availability(model, reason)
    return ReaderClaim(
        claim_id,
        _gap_kind(availability.status),
        refs,
        Derivation("direct", inputs=tuple(ref.source_id for ref in refs), version="v0"),
        availability,
        cast(FrozenJSON, value),
    )


def _projection(
    model: ManagerReadModel,
    *,
    page: ReaderPage,
    sample: bool,
    sample_state: str | None,
) -> ReaderProjection:
    claims: list[ReaderClaim] = []
    gaps: list[ReaderClaim] = []
    if page is ReaderPage.HISTORY:
        view = HistoryViewModel.from_read_model(model)
        if view.events:
            index = _direct_claim(
                "history.events",
                cast(JSONValue, {"event_ids": [event.event_id for event in view.events], "count": len(view.events)}),
                model,
            )
            if index is not None:
                claims.append(index)
            for event in view.events:
                claim = _direct_claim(
                    f"history.event.{event.event_id}",
                    _json_value(event.to_dict()),
                    model,
                    source_id=event.source_id,
                )
                if claim is not None:
                    claims.append(claim)
        else:
            gap = _gap_claim(
                "history.events",
                cast(JSONValue, {"count": 0}),
                model,
                "No explicit source event is recorded in the current scope.",
            )
            if gap is not None:
                gaps.append(gap)
        if view.events and (
            not model.availability.complete
            or _claim_availability(model).status is not ReaderAvailabilityStatus.KNOWN
        ):
            gap = _gap_claim(
                "history.scope",
                cast(JSONValue, {"complete": False}),
                model,
                model.availability.reason or "The source-event history scope is incomplete.",
            )
            if gap is not None:
                gaps.append(gap)
        rule = HISTORY_READER_RULE
        resource = HISTORY_READER_RESOURCE
    else:
        view = SourceDocumentsViewModel.from_read_model(model)
        if view.documents:
            index = _direct_claim(
                "documents.index",
                cast(JSONValue, {"state": view.state.value, "count": len(view.documents)}),
                model,
            )
            if index is not None:
                claims.append(index)
            entries = _direct_claim(
                "documents.entries",
                cast(JSONValue, {"document_ids": [document.document_id for document in view.documents]}),
                model,
            )
            if entries is not None:
                claims.append(entries)
        else:
            gap = _gap_claim(
                "documents.index",
                cast(JSONValue, {"state": view.state.value}),
                model,
                "No approved Source Document index entry is available in the current scope.",
            )
            if gap is not None:
                gaps.append(gap)
        if view.documents and view.state is not DocumentIndexState.READY:
            gap = _gap_claim(
                "documents.usability",
                cast(JSONValue, {"state": view.state.value}),
                model,
                f"Source Document index state is {view.state.value}; no stronger conclusion is available.",
            )
            if gap is not None:
                gaps.append(gap)
        if view.documents and (
            not model.availability.complete
            or _claim_availability(model).status is not ReaderAvailabilityStatus.KNOWN
        ):
            gap = _gap_claim(
                "documents.scope",
                cast(JSONValue, {"complete": False}),
                model,
                model.availability.reason or "The Source Document scope is incomplete.",
            )
            if gap is not None:
                gaps.append(gap)
        rule = DOCUMENTS_READER_RULE
        resource = DOCUMENTS_READER_RESOURCE
    all_claims = (*claims, *gaps)
    summary = (
        ReaderSummary(f"reader.{page.value}.summary", tuple(claim.claim_id for claim in all_claims), {"n": len(all_claims)})
        if all_claims
        else None
    )
    projection = project_read_model(
        model,
        summary=summary,
        claims=tuple(claims),
        unknowns=tuple(gaps),
    )
    # Replace the generic identity rule with the page-owned, versioned rule;
    # this changes only the UI projection envelope, never the v0 source.
    projection = replace(
        projection,
        derivation=Derivation(
            "derived",
            rule,
            tuple(ref.source_id for ref in model.source_refs),
            "v1",
        ),
    )
    if sample:
        projection = replace(projection, sample_data=SampleData(sample_state or "complete", resource))
    return projection


@dataclass(frozen=True, slots=True)
class HistoryReaderViewModel:
    """Typed History Reader view over one unchanged v0 envelope."""

    read_model: ManagerReadModel
    history: HistoryViewModel
    scope: str | None = None

    @classmethod
    def from_read_model(cls, model: ManagerReadModel, *, scope: str | None = None) -> HistoryReaderViewModel:
        return cls(model, HistoryViewModel.from_read_model(model, scope=scope), _scope(model, scope))

    @property
    def events(self) -> tuple[HistoryEvent, ...]:
        return self.history.events

    @property
    def source_refs(self) -> tuple[SourceReference, ...]:
        return self.read_model.source_refs

    def to_dict(self) -> dict[str, object]:
        return {
            "view": HISTORY_READER_RESOURCE,
            "scope": self.scope,
            "history": self.history.to_dict(),
            "source_refs": [ref.to_dict() for ref in self.source_refs],
            "as_of": self.read_model.as_of,
            "snapshot_token": self.read_model.snapshot_token,
            "availability": self.read_model.availability.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class SourceDocumentsReaderViewModel:
    """Typed Source Documents Reader view over one unchanged v0 envelope."""

    read_model: ManagerReadModel
    documents: SourceDocumentsViewModel
    scope: str | None = None
    approved_directories: tuple[str, ...] = ()

    @classmethod
    def from_read_model(
        cls,
        model: ManagerReadModel,
        *,
        scope: str | None = None,
        approved_directories: tuple[str, ...] = (),
        boundary: ApprovedDirectoryBoundary | None = None,
    ) -> SourceDocumentsReaderViewModel:
        selected_boundary = boundary or ApprovedDirectoryBoundary(approved_directories)
        documents = SourceDocumentsViewModel.from_read_model(
            model,
            scope=scope,
            approved_directories=approved_directories,
            boundary=selected_boundary,
        )
        return cls(model, documents, _scope(model, scope), tuple(approved_directories))

    @property
    def source_documents(self) -> tuple[SourceDocument, ...]:
        return self.documents.documents

    @property
    def source_refs(self) -> tuple[SourceReference, ...]:
        return self.read_model.source_refs

    @property
    def index_state(self) -> DocumentIndexState:
        return self.documents.state

    def to_dict(self) -> dict[str, object]:
        return {
            "view": DOCUMENTS_READER_RESOURCE,
            "scope": self.scope,
            "documents": self.documents.to_dict(),
            "source_refs": [ref.to_dict() for ref in self.source_refs],
            "as_of": self.read_model.as_of,
            "snapshot_token": self.read_model.snapshot_token,
            "availability": self.read_model.availability.to_dict(),
        }


# Short compatibility names make both page-oriented and resource-oriented
# integrations discoverable without creating a second projection contract.
DocumentsReaderViewModel = SourceDocumentsReaderViewModel
HistoryDocumentsReaderView = HistoryReaderViewModel


def project_history_reader(model: ManagerReadModel, *, sample: bool = False, sample_state: str | None = None) -> ReaderProjection:
    return _projection(model, page=ReaderPage.HISTORY, sample=sample, sample_state=sample_state)


def project_source_documents_reader(model: ManagerReadModel, *, sample: bool = False, sample_state: str | None = None) -> ReaderProjection:
    return _projection(model, page=ReaderPage.DOCUMENTS, sample=sample, sample_state=sample_state)


project_documents_reader = project_source_documents_reader
project_reader_history = project_history_reader
project_reader_source_documents = project_source_documents_reader


def _machine(value: object, translator: Translator) -> str:
    text = _text(value)
    if text is None:
        return escape(translator.t("reader.history.missing"))
    return f'<span translate="no">{escape(text)}</span>'


def _owner(value: object, translator: Translator) -> str:
    text = _text(value)
    if text is None:
        return escape(translator.t("reader.history.missing"))
    return f'<span data-owner-text="true" translate="no">{escape(text)}</span>'


def _pagination(context: QueryContext, *, view: ViewId, total: int, translator: Translator) -> str:
    return PageWindow.from_query(context, total=total).render(context, view=view, translator=translator)


def _scope_links(context: QueryContext, *, view: ViewId, translator: Translator, key_prefix: str) -> str:
    links = "".join(
        f'<a class="{view.value}-reader-scope-link" data-scope="{escape(scope, quote=True)}" '
        f'href="{escape(context_link(context, view=view, scope=scope), quote=True)}"><span translate="no">{escape(scope)}</span></a>'
        for scope in HISTORY_DOCUMENTS_SCOPES
    )
    return f'<nav class="{view.value}-reader-scopes" aria-label="{escape(translator.t(key_prefix), quote=True)}">{links}</nav>'


def _source_links(view: HistoryReaderViewModel | SourceDocumentsReaderViewModel, context: QueryContext, translator: Translator, *, page: str) -> str:
    if not view.source_refs:
        return f'<p class="{page}-reader-no-source">{escape(translator.t(f"reader.{page}.no_source"))}</p>'
    items: list[str] = []
    for source in view.source_refs:
        if support := source_support_entry(source.source_id):
            items.append(f"<li>{support}</li>")
            continue
        locator = public_locator(source.locator)
        source_id = f'<span translate="no">{escape(source.source_id)}</span>'
        if locator:
            source_id = f'<a href="{escape(locator, quote=True)}" translate="no">{escape(source.source_id)}</a>'
        evidence = context_link(context, view=ViewId.EVIDENCE, source_id=source.source_id)
        items.append(f'<li>{source_id} · <a href="{escape(evidence, quote=True)}">{escape(translator.t(f"reader.{page}.open_evidence"))}</a></li>')
    return f'<ul class="{page}-reader-sources">{"".join(items)}</ul>'


def _history_fixture_text(translator: Translator, event: HistoryEvent, field: str, *, fixture: bool, scope: str | None) -> str:
    if fixture:
        event_type = translator.label("history.event_type", event.event_type.value)
        return translator.t("reader.history.fixture.title" if field == "title" else "reader.history.fixture.detail", scope=scope or "", event_type=event_type)
    return event.title if field == "title" else (event.detail or translator.t("reader.history.missing"))


def _fixture_markup(value: str, scope: str | None) -> str:
    rendered = escape(value)
    if scope:
        escaped_scope = escape(scope)
        rendered = rendered.replace(escaped_scope, f'<span translate="no">{escaped_scope}</span>', 1)
    return rendered


def _event_markup(view: HistoryReaderViewModel, context: QueryContext, translator: Translator) -> str:
    fixture = _is_history_fixture(view.read_model)
    rows: list[str] = []
    window = PageWindow.from_query(context, total=len(view.events))
    for event in view.events[window.start : window.stop]:
        title = _history_fixture_text(translator, event, "title", fixture=fixture, scope=view.scope)
        detail = _history_fixture_text(translator, event, "detail", fixture=fixture, scope=view.scope)
        if fixture:
            title_markup, detail_markup = _fixture_markup(title, view.scope), _fixture_markup(detail, view.scope)
        else:
            title_markup, detail_markup = _owner(title, translator), _owner(detail, translator)
        record = (
            f'<a href="{escape(context_link(context, view=ViewId.HISTORY, record_id=event.record_id), quote=True)}" translate="no">{escape(event.record_id)}</a>'
            if event.record_id else escape(translator.t("reader.history.missing"))
        )
        documents = " · ".join(
            f'<a data-link-kind="document" href="{escape(context_link(context, view=ViewId.SOURCE_DOCUMENTS, document_id=document_id), quote=True)}" translate="no">{escape(document_id)}</a>'
            for document_id in event.document_ids
        ) or escape(translator.t("reader.history.missing"))
        source = escape(translator.t("reader.history.no_source"))
        if event.source_id:
            evidence = context_link(context, view=ViewId.EVIDENCE, source_id=event.source_id)
            source = f'<a href="{escape(evidence, quote=True)}" translate="no">{escape(event.source_id)}</a>'
        locator = public_locator(event.source_locator)
        if locator:
            source += f' · <a data-link-kind="source-artifact" href="{escape(locator, quote=True)}" translate="no">{escape(event.source_locator or "")}</a>'
        rows.append(
            f'<li class="history-reader-event" data-event-id="{escape(event.event_id, quote=True)}" data-event-type="{escape(event.event_type.value, quote=True)}" data-reader-state="{view.read_model.availability.status.value}">'
            f'<time datetime="{escape(event.source_event_time, quote=True)}" translate="no">{escape(event.source_event_time)}</time>'
            f'<span class="history-reader-event-type">{escape(translator.label("history.event_type", event.event_type.value))}</span>'
            f'<strong>{title_markup}</strong><p>{detail_markup}</p>'
            f'<p class="history-reader-event-meta">{escape(translator.t("reader.history.record"))}: {record} · {escape(translator.t("reader.history.source"))}: {source} · {escape(translator.t("reader.history.document"))}: {documents}</p></li>'
        )
    return (
        f'<ol class="history-reader-events" aria-label="{escape(translator.t("reader.history.events"), quote=True)}">{"".join(rows)}</ol>'
        if rows else f'<p class="history-reader-empty" data-reader-state="missing">{escape(translator.t("reader.history.no_events"))}</p>'
    )


def _document_title(document: SourceDocument, view: SourceDocumentsReaderViewModel, translator: Translator) -> str:
    fixture = any(source.owner == "manager-gui-fixture" for source in view.source_refs)
    if fixture:
        return _document_fixture_text(translator, document, "title", fixture=True)
    return document.title or translator.t("reader.documents.missing")


def _document_markup(view: SourceDocumentsReaderViewModel, context: QueryContext, translator: Translator) -> str:
    sections: list[str] = []
    window = PageWindow.from_query(context, total=len(view.source_documents))
    paged_documents = view.source_documents[window.start : window.stop]
    for document_type in view.documents.categories:
        documents = tuple(document for document in paged_documents if document.document_type is document_type)
        if not documents:
            continue
        rows: list[str] = []
        for document in documents:
            title = _document_title(document, view, translator)
            title_markup = _fixture_markup(title, view.scope) if any(source.owner == "manager-gui-fixture" for source in view.source_refs) else _owner(title, translator)
            locator = public_locator(document.source_locator) if document.approved else None
            locator_markup = (
                f'<a href="{escape(locator, quote=True)}" translate="no">{escape(document.source_locator or "")}</a>'
                if locator else escape(translator.t("reader.documents.no_source"))
            )
            records = " · ".join(
                f'<a data-link-kind="record" href="{escape(context_link(context, view=ViewId.HISTORY, record_id=record_id), quote=True)}" translate="no">{escape(record_id)}</a>'
                for record_id in document.record_citations
            ) or escape(translator.t("reader.documents.missing"))
            reverse = " · ".join(
                f'<a data-link-kind="document" href="{escape(context_link(context, view=ViewId.SOURCE_DOCUMENTS, document_id=document_id), quote=True)}" translate="no">{escape(document_id)}</a>'
                for document_id in document.reverse_citations
            ) or escape(translator.t("reader.documents.missing"))
            rows.append(
                f'<li class="documents-reader-document" data-document-id="{escape(document.document_id, quote=True)}" data-document-type="{escape(document.document_type.value, quote=True)}" data-reader-state="{view.index_state.value}">'
                f'<h3>{title_markup}</h3><dl><div><dt>{escape(translator.t("reader.documents.document_id"))}</dt><dd><span translate="no">{escape(document.document_id)}</span></dd></div>'
                f'<div><dt>{escape(translator.t("reader.documents.type"))}</dt><dd>{escape(translator.label("documents.type", document.document_type.value))}</dd></div>'
                f'<div><dt>{escape(translator.t("reader.documents.version"))}</dt><dd>{_machine(document.version, translator)}</dd></div>'
                f'<div><dt>{escape(translator.t("reader.documents.locator"))}</dt><dd>{locator_markup}</dd></div>'
                f'<div><dt>{escape(translator.t("reader.documents.updated"))}</dt><dd>{_machine(document.updated_at, translator)}</dd></div>'
                f'<div><dt>{escape(translator.t("reader.documents.citations"))}</dt><dd>{records}</dd></div>'
                f'<div><dt>{escape(translator.t("reader.documents.reverse_citations"))}</dt><dd>{reverse}</dd></div></dl></li>'
            )
        heading_id = f"documents-reader-{document_type.value}"
        sections.append(
            f'<section class="documents-reader-category" data-document-type="{escape(document_type.value, quote=True)}" aria-labelledby="{heading_id}">'
            f'<h3 id="{heading_id}">{escape(translator.label("documents.type", document_type.value))}</h3><ul>{"".join(rows)}</ul></section>'
        )
    return "".join(sections) or f'<p class="documents-reader-empty" data-reader-state="{escape(view.index_state.value, quote=True)}">{escape(translator.t("reader.documents.no_documents"))}</p>'


def _raw_markup(projection: ReaderProjection, *, heading: str, translator: Translator, page: str) -> str:
    raw = projection.raw_source.raw_bytes.decode("utf-8")
    return (
        f'<section class="{page}-reader-raw"><h2>{escape(heading)}</h2>'
        f'<pre data-v0-schema="manager-gui.manager-read-model.v0" translate="no">{escape(raw)}</pre>'
        f'<p translate="no" data-raw-sha256="{escape(projection.raw_source.sha256, quote=True)}">{projection.raw_source.sha256}</p></section>'
    )


def _context_markup(model: ManagerReadModel, scope: str | None, translator: Translator, *, page: str) -> str:
    return (
        f'<p class="{page}-reader-context"><strong>{escape(translator.t(f"reader.{page}.as_of"))}</strong> {_machine(model.as_of, translator)} · '
        f'<strong>{escape(translator.t(f"reader.{page}.snapshot"))}</strong> {_machine(model.snapshot_token, translator)} · '
        f'<strong>{escape(translator.t(f"reader.{page}.scope"))}</strong> {_machine(scope, translator)}</p>'
    )


def _related_links(context: QueryContext, translator: Translator, *, page: str) -> str:
    if page == "history":
        links = ((ViewId.SOURCE_DOCUMENTS, "reader.history.open_documents"), (ViewId.METHODOLOGY, "reader.history.open_methodology"))
    else:
        links = ((ViewId.HISTORY, "reader.documents.open_history"), (ViewId.METHODOLOGY, "reader.documents.open_methodology"))
    return '<nav class="reader-related-links">' + "".join(
        f'<a href="{escape(context_link(context, view=view), quote=True)}">{escape(translator.t(key))}</a>' for view, key in links
    ) + "</nav>"


def render_history_reader(
    view_or_model: HistoryReaderViewModel | ManagerReadModel,
    *,
    query_context: QueryContext = None,
    translator: Translator | None = None,
    projection: ReaderProjection | None = None,
    mode: ProjectionMode | str | None = None,
    scope: str | None = None,
) -> str:
    selected = translator or Translator()
    view = view_or_model if isinstance(view_or_model, HistoryReaderViewModel) else HistoryReaderViewModel.from_read_model(view_or_model, scope=scope)
    reader_projection = projection or project_history_reader(view.read_model)
    state = ReaderURLState.from_url(query_context) if isinstance(query_context, str) else ReaderURLState(pairs=tuple((str(k), str(v)) for k, v in (query_context or {}).items() if v is not None))
    selected_mode = ProjectionMode(mode) if mode is not None else state.mode
    if selected_mode is ProjectionMode.RAW:
        body = _raw_markup(reader_projection, heading=selected.t("reader.history.raw_heading"), translator=selected, page="history")
    elif selected_mode is ProjectionMode.EXPERT:
        base = query_context if isinstance(query_context, str) else "/?view=history"
        body = f'<section class="history-reader-expert"><h2>{escape(selected.t("reader.history.expert_heading"))}</h2>{render_history(view.read_model, scope=view.scope, base_path=base, query=query_context, translator=selected)}</section>'
    else:
        body = (
            render_reader_surface(reader_projection, page=ReaderPage.HISTORY, query_context=query_context, translator=selected)
            + f'<section class="history-reader-scope"><h2>{escape(selected.t("reader.history.scope"))}</h2><p>{escape(selected.t("reader.history.scope_intro"))}</p>{_scope_links(query_context, view=ViewId.HISTORY, translator=selected, key_prefix="reader.history.scope")}</section>'
            + f'<section class="history-reader-events-section"><h2>{escape(selected.t("reader.history.events"))}</h2>{_event_markup(view, query_context, selected)}{_pagination(query_context, view=ViewId.HISTORY, total=len(view.events), translator=selected)}</section>'
            + f'<section class="history-reader-boundary" data-boundary="canonical-fact"><h2>{escape(selected.t("reader.history.canonical_heading"))}</h2><p>{escape(selected.t("reader.history.canonical_copy"))}</p></section>'
            + f'<p class="history-reader-read-only">{escape(selected.t("reader.history.read_only"))}</p>'
        )
    return (
        f'<section class="history-reader-page" data-reader-hook="{HISTORY_READER_HOOK}" data-reader-contract="v1" data-integration-hook="{HISTORY_READER_INTEGRATION_HOOK}" data-reader-mode="{selected_mode.value}" data-status="{view.read_model.availability.status.value}" data-history-scope="{escape(view.scope or "", quote=True)}">'
        f'<p class="eyebrow">{escape(selected.t("reader.history.eyebrow"))}</p><h1 data-page-title tabindex="-1">{escape(selected.t("reader.history.title"))}</h1><p class="page-intro">{escape(selected.t("reader.history.confirmed_intro"))}</p>{render_status_block(view.read_model, translator=selected)}{_context_markup(view.read_model, view.scope, selected, page="history")}{body}{_source_links(view, query_context, selected, page="history")}{_related_links(query_context, selected, page="history")}</section>'
    )


def render_source_documents_reader(
    view_or_model: SourceDocumentsReaderViewModel | ManagerReadModel,
    *,
    query_context: QueryContext = None,
    translator: Translator | None = None,
    projection: ReaderProjection | None = None,
    mode: ProjectionMode | str | None = None,
    scope: str | None = None,
    approved_directories: tuple[str, ...] = (),
    boundary: ApprovedDirectoryBoundary | None = None,
) -> str:
    selected = translator or Translator()
    view = view_or_model if isinstance(view_or_model, SourceDocumentsReaderViewModel) else SourceDocumentsReaderViewModel.from_read_model(view_or_model, scope=scope, approved_directories=approved_directories, boundary=boundary)
    reader_projection = projection or project_source_documents_reader(view.read_model)
    state = ReaderURLState.from_url(query_context) if isinstance(query_context, str) else ReaderURLState(pairs=tuple((str(k), str(v)) for k, v in (query_context or {}).items() if v is not None))
    selected_mode = ProjectionMode(mode) if mode is not None else state.mode
    if selected_mode is ProjectionMode.RAW:
        body = _raw_markup(reader_projection, heading=selected.t("reader.documents.raw_heading"), translator=selected, page="documents")
    elif selected_mode is ProjectionMode.EXPERT:
        base = query_context if isinstance(query_context, str) else "/?view=source-documents"
        body = f'<section class="documents-reader-expert"><h2>{escape(selected.t("reader.documents.expert_heading"))}</h2>{render_source_documents(view.read_model, scope=view.scope, approved_directories=view.approved_directories, boundary=ApprovedDirectoryBoundary(view.approved_directories), base_path=base, query=query_context, translator=selected)}</section>'
    else:
        body = (
            render_reader_surface(reader_projection, page=ReaderPage.DOCUMENTS, query_context=query_context, translator=selected)
            + f'<section class="documents-reader-scope"><h2>{escape(selected.t("reader.documents.scope"))}</h2><p>{escape(selected.t("reader.documents.scope_intro"))}</p>{_scope_links(query_context, view=ViewId.SOURCE_DOCUMENTS, translator=selected, key_prefix="reader.documents.scope")}</section>'
            + f'<section class="documents-reader-layers" data-boundary="document-interpretation"><h2>{escape(selected.t("reader.documents.categories"))}</h2><h3>{escape(selected.t("reader.documents.canonical_heading"))}</h3><p>{escape(selected.t("reader.documents.canonical_copy"))}</p><h3>{escape(selected.t("reader.documents.interpretation_heading"))}</h3><p>{escape(selected.t("reader.documents.interpretation_copy"))}</p></section>'
            + f'<section class="documents-reader-index"><h2>{escape(selected.t("reader.documents.index_state"))}</h2><p data-reader-state="{escape(view.index_state.value, quote=True)}">{escape(selected.t(f"documents.state.{view.index_state.value}"))}</p>{_document_markup(view, query_context, selected)}{_pagination(query_context, view=ViewId.SOURCE_DOCUMENTS, total=len(view.source_documents), translator=selected)}</section>'
            + f'<p class="documents-reader-read-only">{escape(selected.t("reader.documents.read_only"))}</p>'
        )
    return (
        f'<section class="documents-reader-page" data-reader-hook="{DOCUMENTS_READER_HOOK}" data-reader-contract="v1" data-integration-hook="{DOCUMENTS_READER_INTEGRATION_HOOK}" data-reader-mode="{selected_mode.value}" data-status="{view.read_model.availability.status.value}" data-document-index-state="{view.index_state.value}" data-document-scope="{escape(view.scope or "", quote=True)}">'
        f'<p class="eyebrow">{escape(selected.t("reader.documents.eyebrow"))}</p><h1 data-page-title tabindex="-1">{escape(selected.t("reader.documents.title"))}</h1><p class="page-intro">{escape(selected.t("reader.documents.confirmed_intro"))}</p>{render_status_block(view.read_model, translator=selected)}{_context_markup(view.read_model, view.scope, selected, page="documents")}{body}{_source_links(view, query_context, selected, page="documents")}{_related_links(query_context, selected, page="documents")}</section>'
    )


def history_reader_view(provider, *, scope: str | None = None, snapshot_token: str | None = None) -> HistoryReaderViewModel:
    return HistoryReaderViewModel.from_read_model(provider.read(HISTORY_READER_RESOURCE, snapshot_token=snapshot_token), scope=scope)


def source_documents_reader_view(provider, *, scope: str | None = None, approved_directories: tuple[str, ...] = (), boundary: ApprovedDirectoryBoundary | None = None, snapshot_token: str | None = None) -> SourceDocumentsReaderViewModel:
    return SourceDocumentsReaderViewModel.from_read_model(provider.read(DOCUMENTS_READER_RESOURCE, snapshot_token=snapshot_token), scope=scope, approved_directories=approved_directories, boundary=boundary)


def render_history_reader_view(source, **kwargs: object) -> str:
    if isinstance(source, HistoryReaderViewModel):
        view = source
    elif isinstance(source, ManagerReadModel):
        view = HistoryReaderViewModel.from_read_model(source, scope=cast(str | None, kwargs.get("scope")))
    else:
        view = history_reader_view(source, scope=cast(str | None, kwargs.get("scope")), snapshot_token=cast(str | None, kwargs.get("snapshot_token")))
    return render_history_reader(view, **{key: value for key, value in kwargs.items() if key not in {"scope", "snapshot_token"}})


def render_source_documents_reader_view(source, **kwargs: object) -> str:
    if isinstance(source, SourceDocumentsReaderViewModel):
        view = source
    elif isinstance(source, ManagerReadModel):
        view = SourceDocumentsReaderViewModel.from_read_model(source, scope=cast(str | None, kwargs.get("scope")), approved_directories=cast(tuple[str, ...], kwargs.get("approved_directories", ())), boundary=cast(ApprovedDirectoryBoundary | None, kwargs.get("boundary")))
    else:
        view = source_documents_reader_view(source, scope=cast(str | None, kwargs.get("scope")), approved_directories=cast(tuple[str, ...], kwargs.get("approved_directories", ())), boundary=cast(ApprovedDirectoryBoundary | None, kwargs.get("boundary")), snapshot_token=cast(str | None, kwargs.get("snapshot_token")))
    return render_source_documents_reader(view, **{key: value for key, value in kwargs.items() if key not in {"scope", "snapshot_token", "approved_directories", "boundary"}})


render_reader_history = render_history_reader
render_reader_source_documents = render_source_documents_reader
project_reader_documents = project_source_documents_reader

build_history_reader_fixture = build_history_fixture
build_source_documents_reader_fixture = build_source_documents_fixture
history_reader_fixture_provider = HistoryFixtureProvider
source_documents_reader_fixture_provider = SourceDocumentsFixtureProvider

__all__ = [
    "DOCUMENTS_READER_HOOK",
    "DOCUMENTS_READER_INTEGRATION_HOOK",
    "DOCUMENTS_READER_RESOURCE",
    "DOCUMENTS_READER_RULE",
    "DOCUMENTS_READER_VERSION",
    "HISTORY_DOCUMENTS_SCOPES",
    "HISTORY_READER_HOOK",
    "HISTORY_READER_INTEGRATION_HOOK",
    "HISTORY_READER_RESOURCE",
    "HISTORY_READER_RULE",
    "HISTORY_READER_VERSION",
    "DocumentsReaderViewModel",
    "HistoryDocumentsReaderView",
    "HistoryReaderViewModel",
    "SourceDocumentsReaderViewModel",
    "build_history_reader_fixture",
    "build_source_documents_reader_fixture",
    "history_reader_fixture_provider",
    "history_reader_view",
    "project_documents_reader",
    "project_history_reader",
    "project_reader_documents",
    "project_reader_history",
    "project_reader_source_documents",
    "project_source_documents_reader",
    "render_history_reader",
    "render_history_reader_view",
    "render_reader_history",
    "render_reader_source_documents",
    "render_source_documents_reader",
    "render_source_documents_reader_view",
    "source_documents_reader_fixture_provider",
    "source_documents_reader_view",
]
