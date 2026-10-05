"""Approved Source Document index for the Manager GUI S5-T2 surface.

The module consumes only a ``ManagerReadModel`` v0 envelope or the public
``ManagerDataProvider.read`` seam.  The expected payload is an explicit
``documents``/``source_documents``/``index`` sequence containing stable
``document_id``, ``document_type``, ``version`` (or ``revision``), a source
``locator``, ``updated_at``, and optional ``record_citations`` and
``reverse_citations``.  The six approved categories are ``plan``, ``design``,
``report``, ``retrospective``, ``future-idea``, ``external-source``, and
``raw-evidence``.

No filename is used as identity.  No module function scans a directory, reads
SQLite, opens a document, or mutates an owner record.  Local ``file:`` locators
are rendered only when they are beneath an explicitly supplied
``ApprovedDirectoryBoundary``; URI locators from an approved public source are
not dereferenced.  Missing, version-conflict, not-indexed, API-unavailable,
and boundary-blocked states remain explicit.  The S5-T3 integration hook is
:func:`render_source_documents_view`.
"""

# HTML fragments intentionally keep readable markup even when a line is long.
# ruff: noqa: E501

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from html import escape
from pathlib import Path
from typing import cast
from urllib.parse import unquote, urlsplit

from ..models import (
    Availability,
    Derivation,
    JSONValue,
    ManagerReadModel,
    ReadModelStatus,
    SourceReference,
)
from ..provider import ManagerDataProvider
from .i18n import Translator
from .i18n.catalog import l3_method_history as _l3_method_history_catalog
from .navigation import PageWindow, context_link
from .status import DisplayState, render_operational_state, render_status_block


class DocumentType(StrEnum):
    """Document categories approved by the historical-document seam."""

    PLAN = "plan"
    DESIGN = "design"
    REPORT = "report"
    RETROSPECTIVE = "retrospective"
    FUTURE_IDEA = "future-idea"
    EXTERNAL_SOURCE = "external-source"
    RAW_EVIDENCE = "raw-evidence"


class DocumentIndexState(StrEnum):
    """Index and boundary states shown independently of read-model status."""

    READY = "ready"
    MISSING = "missing"
    VERSION_CONFLICT = "version-conflict"
    NOT_INDEXED = "not-indexed"
    API_UNAVAILABLE = "api-unavailable"
    BOUNDARY_BLOCKED = "boundary-blocked"
    OUTSIDE_APPROVED_DIRECTORY = "boundary-blocked"


DOCUMENT_TYPES: tuple[DocumentType, ...] = tuple(DocumentType)
DOCUMENT_SCOPES: tuple[str, ...] = ("A0", "S3", "CPA", "V1.x")
DOCUMENTS_RESOURCE = "source_documents"

_TYPE_ALIASES = {
    "future_idea": DocumentType.FUTURE_IDEA,
    "future-idea": DocumentType.FUTURE_IDEA,
    "future idea": DocumentType.FUTURE_IDEA,
    "external_source": DocumentType.EXTERNAL_SOURCE,
    "external-source": DocumentType.EXTERNAL_SOURCE,
    "external source": DocumentType.EXTERNAL_SOURCE,
    "raw_evidence": DocumentType.RAW_EVIDENCE,
    "raw-evidence": DocumentType.RAW_EVIDENCE,
    "raw evidence": DocumentType.RAW_EVIDENCE,
}
_INDEX_STATE_ALIASES = {
    "known": DocumentIndexState.READY,
    "ready": DocumentIndexState.READY,
    "missing": DocumentIndexState.MISSING,
    "version_conflict": DocumentIndexState.VERSION_CONFLICT,
    "version-conflict": DocumentIndexState.VERSION_CONFLICT,
    "conflict": DocumentIndexState.VERSION_CONFLICT,
    "not_indexed": DocumentIndexState.NOT_INDEXED,
    "not-indexed": DocumentIndexState.NOT_INDEXED,
    "unindexed": DocumentIndexState.NOT_INDEXED,
    "api_unavailable": DocumentIndexState.API_UNAVAILABLE,
    "api-unavailable": DocumentIndexState.API_UNAVAILABLE,
    "boundary_blocked": DocumentIndexState.BOUNDARY_BLOCKED,
    "boundary-blocked": DocumentIndexState.BOUNDARY_BLOCKED,
    "outside_approved_directory": DocumentIndexState.BOUNDARY_BLOCKED,
    "outside-approved-directory": DocumentIndexState.BOUNDARY_BLOCKED,
}


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


def _mapping(value: object) -> Mapping[str, object] | None:
    return cast(Mapping[str, object], value) if isinstance(value, Mapping) else None


def _first_text(item: Mapping[str, object], keys: Sequence[str]) -> str | None:
    for key in keys:
        value = _text(item.get(key))
        if value is not None:
            return value
    return None


def _normalise(value: object) -> str | None:
    text = _text(value)
    if text is None:
        return None
    return text.lower().strip().replace(" ", "-")


def _document_type(value: object) -> DocumentType | None:
    normalised = _normalise(value)
    if normalised is None:
        return None
    try:
        return DocumentType(normalised)
    except ValueError:
        return _TYPE_ALIASES.get(normalised.replace("-", " "), _TYPE_ALIASES.get(normalised))


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(value)
    if isinstance(value, Mapping):
        return (value,)
    return ()


def _iter_document_items(data: object) -> tuple[Mapping[str, object], ...]:
    if isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
        return tuple(item for value in data if (item := _mapping(value)) is not None)
    container = _mapping(data)
    if container is None:
        return ()
    for key in ("documents", "source_documents", "document_index", "index", "items", "records"):
        if key not in container:
            continue
        nested = _mapping(container[key])
        if nested is not None:
            nested_items = _iter_document_items(nested)
            if nested_items:
                return nested_items
        items = tuple(item for value in _sequence(container[key]) if (item := _mapping(value)) is not None)
        if items:
            return items
    return ()


def _citation_ids(value: object) -> tuple[str, ...]:
    if isinstance(value, str) and value.strip():
        return (value.strip(),)
    if isinstance(value, Mapping):
        identifier = _first_text(
            value,
            ("record_id", "recordId", "document_id", "documentId", "id", "target_id", "target"),
        )
        if identifier:
            return (identifier,)
        return tuple(str(key) for key in value if str(key).strip())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        values: list[str] = []
        for entry in value:
            values.extend(_citation_ids(entry))
        return tuple(dict.fromkeys(values))
    return ()


def _source_locator(item: Mapping[str, object], source_refs: Mapping[str, SourceReference]) -> str | None:
    direct = _first_text(item, ("source_locator", "locator", "source_url", "url", "href", "uri"))
    if direct is not None:
        return direct
    source = item.get("source_ref", item.get("source_id"))
    source_id = _first_text(source, ("source_id", "id")) if isinstance(source, Mapping) else _text(source)
    if source_id and source_id in source_refs:
        return source_refs[source_id].locator
    return None


def _scope(payload: Mapping[str, object], item: Mapping[str, object], selected: str | None) -> str | None:
    return selected or _first_text(item, ("scope", "fixture", "batch")) or _first_text(payload, ("scope", "fixture", "batch"))


def _explicit_state(model: ManagerReadModel, payload: Mapping[str, object]) -> DocumentIndexState | None:
    raw = _first_text(payload, ("document_index_state", "index_state", "index_status"))
    if raw is None:
        index = _mapping(payload.get("document_index")) or _mapping(payload.get("index"))
        if index is not None:
            raw = _first_text(index, ("state", "status"))
    if raw is not None:
        selected = _INDEX_STATE_ALIASES.get(_normalise(raw) or "")
        if selected is not None:
            return selected
    if model.availability.status is ReadModelStatus.API_UNAVAILABLE:
        return DocumentIndexState.API_UNAVAILABLE
    if model.availability.status is ReadModelStatus.MISSING:
        return DocumentIndexState.MISSING
    for error in model.errors:
        code = _normalise(error.code) or ""
        if code in {"version-conflict", "version_conflict", "document-version-conflict"}:
            return DocumentIndexState.VERSION_CONFLICT
        if code in {"not-indexed", "not_indexed", "document-not-indexed"}:
            return DocumentIndexState.NOT_INDEXED
    return None


@dataclass(frozen=True, slots=True)
class ApprovedDirectoryBoundary:
    """Explicit local-directory allowlist; it performs no filesystem traversal."""

    directories: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not all(isinstance(directory, str) and directory.strip() for directory in self.directories):
            raise ValueError("directories must contain non-empty path strings")

    def allows(self, locator: str | None) -> bool:
        """Return whether a locator is public/fixture URI or inside an approved path."""

        if locator is None or not locator.strip():
            return False
        parsed = urlsplit(locator)
        is_windows_drive = len(parsed.scheme) == 1 and len(locator) > 2 and locator[1] == ":"
        if parsed.scheme and parsed.scheme.lower() not in {"file"} and not is_windows_drive:
            return True
        if parsed.scheme.lower() == "file":
            path_text = unquote(parsed.path)
            if parsed.netloc and parsed.netloc.lower() != "localhost":
                path_text = f"//{parsed.netloc}{path_text}"
        else:
            path_text = locator
            # Windows drive paths are parsed as a one-character URL scheme.
            if len(parsed.scheme) == 1 and len(locator) > 2 and locator[1] == ":":
                path_text = locator
        if not self.directories:
            return False
        try:
            candidate = Path(path_text).resolve(strict=False)
            roots = tuple(Path(directory).resolve(strict=False) for directory in self.directories)
        except (OSError, ValueError):
            return False
        for root in roots:
            try:
                candidate.relative_to(root)
            except ValueError:
                continue
            else:
                return True
        return False


@dataclass(frozen=True, slots=True)
class SourceDocument:
    """One approved index entry with forward and reverse relation metadata."""

    document_id: str
    document_type: DocumentType
    version: str | None
    source_locator: str | None
    updated_at: str | None
    record_citations: tuple[str, ...] = ()
    reverse_citations: tuple[str, ...] = ()
    title: str | None = None
    scope: str | None = None
    approved: bool = True

    @property
    def category(self) -> str:
        return self.document_type.value

    @property
    def is_versioned(self) -> bool:
        return self.version is not None

    def to_dict(self) -> dict[str, object]:
        return {
            "document_id": self.document_id,
            "document_type": self.document_type.value,
            "version": self.version,
            "source_locator": self.source_locator,
            "updated_at": self.updated_at,
            "record_citations": list(self.record_citations),
            "reverse_citations": list(self.reverse_citations),
            "title": self.title,
            "scope": self.scope,
            "approved": self.approved,
        }


@dataclass(frozen=True, slots=True)
class SourceDocumentsViewModel:
    """Typed document index projection with deterministic categories and citations."""

    read_model: ManagerReadModel
    documents: tuple[SourceDocument, ...]
    state: DocumentIndexState
    scope: str | None = None
    approved_directories: tuple[str, ...] = ()
    reverse_citations: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    @classmethod
    def from_read_model(
        cls,
        model: ManagerReadModel,
        *,
        scope: str | None = None,
        approved_directories: Sequence[str] = (),
        boundary: ApprovedDirectoryBoundary | None = None,
    ) -> SourceDocumentsViewModel:
        payload = _mapping(model.data) or {}
        source_refs = {source.source_id: source for source in model.source_refs}
        configured = tuple(approved_directories)
        raw_configured = payload.get("approved_directories")
        if not configured and isinstance(raw_configured, Sequence) and not isinstance(raw_configured, (str, bytes, bytearray)):
            configured = tuple(value for value in raw_configured if isinstance(value, str) and value.strip())
        selected_boundary = boundary or ApprovedDirectoryBoundary(configured)
        parsed: list[SourceDocument] = []
        invalid_count = 0
        for item in _iter_document_items(model.data):
            document_id = _first_text(item, ("document_id", "documentId", "id"))
            document_type = _document_type(_first_text(item, ("document_type", "type", "category")))
            if document_id is None or document_type is None:
                invalid_count += 1
                continue
            locator = _source_locator(item, source_refs)
            parsed.append(
                SourceDocument(
                    document_id=document_id,
                    document_type=document_type,
                    version=_first_text(item, ("version", "revision", "document_version")),
                    source_locator=locator,
                    updated_at=_first_text(item, ("updated_at", "updated_time", "modified_at", "published_at")),
                    record_citations=_citation_ids(item.get("record_citations", item.get("citations", item.get("records")))),
                    reverse_citations=_citation_ids(item.get("reverse_citations", item.get("cited_by", item.get("backlinks")))),
                    title=_first_text(item, ("title", "name", "label")),
                    scope=_scope(payload, item, scope),
                    approved=selected_boundary.allows(locator),
                )
            )
        parsed.sort(key=lambda document: (document.document_id, document.version or ""))
        parsed.sort(key=lambda document: document.updated_at or "", reverse=True)
        parsed_by_id: dict[str, list[SourceDocument]] = defaultdict(list)
        for document in parsed:
            parsed_by_id[document.document_id].append(document)
        version_conflicts = {
            document_id
            for document_id, versions in parsed_by_id.items()
            if len({document.version for document in versions}) > 1
        }
        boundary_blocked = any(not document.approved for document in parsed)
        explicit_state = _explicit_state(model, payload)
        selected_state: DocumentIndexState
        if explicit_state is not None and explicit_state is not DocumentIndexState.READY:
            selected_state = explicit_state
        elif boundary_blocked:
            selected_state = DocumentIndexState.BOUNDARY_BLOCKED
        elif version_conflicts:
            selected_state = DocumentIndexState.VERSION_CONFLICT
        elif not parsed:
            selected_state = DocumentIndexState.NOT_INDEXED if invalid_count == 0 and model.availability.status is not ReadModelStatus.MISSING else DocumentIndexState.MISSING
        else:
            selected_state = DocumentIndexState.NOT_INDEXED if invalid_count else DocumentIndexState.READY
        reverse: dict[str, set[str]] = defaultdict(set)
        for document in parsed:
            for record_id in document.record_citations:
                reverse[record_id].add(document.document_id)
            for record_id in document.reverse_citations:
                reverse[record_id].add(document.document_id)
        raw_reverse = payload.get("reverse_citations")
        if isinstance(raw_reverse, Mapping):
            for record_id, document_ids in raw_reverse.items():
                reverse[str(record_id)].update(_citation_ids(document_ids))
        selected_scope = scope or _first_text(payload, ("scope", "fixture", "batch"))
        return cls(
            model,
            tuple(parsed),
            selected_state,
            selected_scope,
            configured,
            {key: tuple(sorted(values)) for key, values in sorted(reverse.items())},
        )

    @property
    def categories(self) -> Mapping[DocumentType, tuple[SourceDocument, ...]]:
        grouped: dict[DocumentType, tuple[SourceDocument, ...]] = {}
        for document_type in DOCUMENT_TYPES:
            grouped[document_type] = tuple(document for document in self.documents if document.document_type is document_type)
        return grouped

    @property
    def status(self) -> ReadModelStatus:
        return self.read_model.availability.status

    def to_dict(self) -> dict[str, object]:
        return {
            "scope": self.scope,
            "state": self.state.value,
            "documents": [document.to_dict() for document in self.documents],
            "reverse_citations": {key: list(value) for key, value in self.reverse_citations.items()},
            "availability": self.read_model.availability.to_dict(),
        }

    def render(
        self,
        *,
        base_path: str = "/?view=source-documents",
        query: Mapping[str, object] | str | None = None,
        translator: Translator | None = None,
    ) -> str:
        selected_translator = translator or Translator()
        fixture = _is_documents_fixture(self.read_model)
        scope = self.scope or selected_translator.t("method_history.all_scopes")
        nav = "".join(
            f'<a class="document-scope-link" data-document-scope="{escape(selected, quote=True)}" '
            f'href="{escape(_scope_url(base_path, query, selected), quote=True)}" '
            f'translate="no">{escape(selected_translator.label("method_history.scope", selected))}</a>'
            for selected in DOCUMENT_SCOPES
        )
        window = PageWindow.from_query(query if query is not None else base_path, total=len(self.documents))
        paged_documents = self.documents[window.start : window.stop]
        paged_categories = {
            document_type: tuple(
                document for document in paged_documents if document.document_type is document_type
            )
            for document_type in DOCUMENT_TYPES
        }
        if not paged_documents:
            body = render_operational_state(
                DisplayState.EMPTY if self.state is DocumentIndexState.MISSING else DisplayState.ERROR,
                translator=selected_translator,
                detail=_state_detail(self.state, selected_translator),
            )
        else:
            sections: list[str] = []
            for document_type in DOCUMENT_TYPES:
                documents = paged_categories[document_type]
                if documents:
                    rows = "".join(
                        _render_document(
                            document,
                            base_path=base_path,
                            query=query,
                            translator=selected_translator,
                            fixture=fixture,
                        )
                        for document in documents
                    )
                    sections.append(
                        f'<section class="document-category" data-document-type="{document_type.value}" '
                        f'aria-labelledby="documents-{document_type.value}"><h2 id="documents-{document_type.value}">{escape(selected_translator.label("documents.type", document_type.value))}</h2>'
                        f'<ul class="document-list">{rows}</ul></section>'
                    )
            body = "".join(sections)
        reverse_rows = "".join(
            f'<li data-record-id="{escape(record_id, quote=True)}"><strong translate="no">{escape(record_id)}</strong>: '
            + ", ".join(
                f'<a class="document-reverse-link" href="{escape(_context_url(base_path, query, view="source-documents", document_id=document_id), quote=True)}" translate="no">'
                f"{escape(document_id)}</a>"
                for document_id in document_ids
            )
            + "</li>"
            for record_id, document_ids in self.reverse_citations.items()
        )
        reverse = (
            f'<section class="document-reverse-citations"><h2>{escape(selected_translator.t("documents.reverse_title"))}</h2><ul>{reverse_rows}</ul></section>'
            if reverse_rows
            else ""
        )
        return (
            f'<section class="source-documents-page" data-integration-hook="source-documents-view" '
            f'data-document-index-state="{self.state.value}" data-document-scope="{escape(scope, quote=True)}">'
            f'<p class="eyebrow">{escape(selected_translator.t("documents.eyebrow"))}</p>'
            f'<h1 class="page-title" data-page-title tabindex="-1">{escape(selected_translator.t("documents.title"))}</h1>'
            f'<p class="page-intro">{escape(selected_translator.t("documents.intro"))}</p>'
            f'<p class="boundary-note" data-boundary="document-interpretation">{selected_translator.html("documents.boundary")}</p>'
            f'<p class="context-line document-context"><strong>{escape(selected_translator.t("method_history.scope"))}</strong> <span translate="no">{escape(scope)}</span> · '
            f'<strong>{escape(selected_translator.t("documents.index_state"))}</strong> {escape(selected_translator.label("documents.index_state", self.state.value))}</p>'
            f'<nav class="document-scope-nav" aria-label="{escape(selected_translator.t("documents.scopes_aria"))}">{nav}</nav>'
            f"{render_status_block(self.read_model, translator=selected_translator)}"
            f'<div class="document-index-state" data-state="{self.state.value}">{escape(_state_detail(self.state, selected_translator))}</div>'
            f'{body}{reverse}{window.render(query if query is not None else base_path, view="source-documents", translator=selected_translator)}</section>'
        )


def _is_documents_fixture(model: ManagerReadModel) -> bool:
    return any(
        source.owner == "manager-gui-fixture"
        and source.kind == "source-document-index"
        and source.schema == "manager-gui.source-documents-fixture.v0"
        and source.revision == "v0"
        and source.locator.startswith("fixture://manager-gui/source-documents/")
        for source in model.source_refs
    )


def _document_fixture_text(translator: Translator, document: SourceDocument, field: str, *, fixture: bool) -> str:
    if field == "title":
        key = f"documents.fixture.{document.document_type.value.replace('-', '_')}.title"
    else:
        key = ""
    if fixture and key in _l3_method_history_catalog.ENTRIES:
        return translator.t(key, scope=document.scope or "")
    value = document.title if field == "title" else None
    return translator.source_text(value or document.document_id)


def _state_detail(state: DocumentIndexState, translator: Translator) -> str:
    return translator.t(f"documents.state.{state.value}")


def _scope_in_text(value: str, scope: str | None) -> str:
    rendered = escape(value)
    if scope:
        escaped_scope = escape(scope)
        rendered = rendered.replace(
            escaped_scope, f'<span translate="no">{escaped_scope}</span>', 1
        )
    return rendered


def _context_url(
    base_path: str,
    query: Mapping[str, object] | str | None,
    *,
    view: str,
    **updates: object,
) -> str:
    return context_link(query if query is not None else base_path, view=view, **updates)


def _render_document(
    document: SourceDocument,
    *,
    base_path: str,
    query: Mapping[str, object] | str | None,
    translator: Translator,
    fixture: bool,
) -> str:
    locator = (
        f'<a class="document-source-link" href="{escape(document.source_locator, quote=True)}" translate="no">{escape(document.source_locator)}</a>'
        if document.approved and document.source_locator
        else f'<span class="document-source-missing">{escape(translator.t("documents.boundary_blocked"))}</span>'
        if not document.approved
        else f'<span class="document-source-missing">{escape(translator.t("method_history.missing"))}</span>'
    )
    citations = " · ".join(
        f'<a class="document-record-link" data-link-kind="record" href="{escape(_context_url(base_path, query, view="history", record_id=record_id), quote=True)}" translate="no">'
        f"{escape(record_id)}</a>"
        for record_id in document.record_citations
    ) or translator.t("method_history.missing")
    reverse = " · ".join(
        f'<a class="document-reverse-link" data-link-kind="document" href="{escape(_context_url(base_path, query, view="source-documents", document_id=document_id), quote=True)}" translate="no">'
        f"{escape(document_id)}</a>"
        for document_id in document.reverse_citations
    ) or translator.t("method_history.missing")
    missing = translator.t("method_history.missing")
    title = _document_fixture_text(translator, document, "title", fixture=fixture)
    title_markup = _scope_in_text(title, document.scope)
    document_type = translator.label("documents.type", document.document_type.value)
    return (
        f'<li class="source-document" data-document-id="{escape(document.document_id, quote=True)}">'
        f'<h3>{title_markup}</h3>'
        f'<dl><div><dt>{escape(translator.t("documents.document_id"))}</dt><dd><span translate="no">{escape(document.document_id)}</span></dd></div>'
        f'<div><dt>{escape(translator.t("documents.type"))}</dt><dd>{document_type}</dd></div>'
        f'<div><dt>{escape(translator.t("documents.version"))}</dt><dd><span translate="no">{escape(document.version or missing)}</span></dd></div>'
        f'<div><dt>{escape(translator.t("documents.locator"))}</dt><dd>{locator}</dd></div>'
        f'<div><dt>{escape(translator.t("documents.updated"))}</dt><dd><span translate="no">{escape(document.updated_at or missing)}</span></dd></div>'
        f'<div><dt>{escape(translator.t("documents.citations"))}</dt><dd>{citations}</dd></div>'
        f'<div><dt>{escape(translator.t("documents.reverse_citations"))}</dt><dd>{reverse}</dd></div></dl></li>'
    )


def _scope_url(base_path: str, query: Mapping[str, object] | str | None, scope: str) -> str:
    return context_link(query if query is not None else base_path, view="source-documents", scope=scope)


def source_documents_view(
    provider: ManagerDataProvider,
    *,
    scope: str | None = None,
    approved_directories: Sequence[str] = (),
    boundary: ApprovedDirectoryBoundary | None = None,
    snapshot_token: str | None = None,
) -> SourceDocumentsViewModel:
    """Read the approved Source Document index once and build its view model."""

    model = provider.read(DOCUMENTS_RESOURCE, snapshot_token=snapshot_token)
    return SourceDocumentsViewModel.from_read_model(
        model,
        scope=scope,
        approved_directories=approved_directories,
        boundary=boundary,
    )


def render_source_documents(
    model: ManagerReadModel,
    *,
    scope: str | None = None,
    approved_directories: Sequence[str] = (),
    boundary: ApprovedDirectoryBoundary | None = None,
    base_path: str = "/?view=source-documents",
    query: Mapping[str, object] | str | None = None,
    translator: Translator | None = None,
) -> str:
    """Render an already-read Source Document envelope without a second read."""

    return SourceDocumentsViewModel.from_read_model(
        model,
        scope=scope,
        approved_directories=approved_directories,
        boundary=boundary,
    ).render(base_path=base_path, query=query, translator=translator)


def render_source_documents_view(
    source: ManagerDataProvider | ManagerReadModel,
    *,
    scope: str | None = None,
    approved_directories: Sequence[str] = (),
    boundary: ApprovedDirectoryBoundary | None = None,
    base_path: str = "/?view=source-documents",
    query: Mapping[str, object] | str | None = None,
    snapshot_token: str | None = None,
    translator: Translator | None = None,
) -> str:
    """S5-T3 hook accepting a provider seam or a cached read model."""

    model = (
        source
        if isinstance(source, ManagerReadModel)
        else source.read(DOCUMENTS_RESOURCE, snapshot_token=snapshot_token)
    )
    return render_source_documents(
        model,
        scope=scope,
        approved_directories=approved_directories,
        boundary=boundary,
        base_path=base_path,
        query=query,
        translator=translator,
    )


# Short aliases make the seam discoverable for integrations that call the page "documents".
render_documents_view = render_source_documents_view
source_documents_hook = render_source_documents_view


def build_source_documents_fixture(scope: str = "A0") -> ManagerReadModel:
    """Build deterministic category/citation data for the four S5 fixture scopes."""

    if scope not in DOCUMENT_SCOPES:
        raise ValueError(f"unknown Source Document fixture scope: {scope!r}")
    source = SourceReference(
        source_id=f"fixture-documents-{scope}",
        owner="manager-gui-fixture",
        kind="source-document-index",
        locator=f"fixture://manager-gui/source-documents/{scope}",
        schema="manager-gui.source-documents-fixture.v0",
        revision="v0",
    )
    documents = [
        {
            "document_id": f"{scope.lower()}-{document_type.value}-1",
            "document_type": document_type.value,
            "version": "v1",
            "source_ref": source.source_id,
            "updated_at": f"2026-10-{index + 1:02d}T09:00:00Z",
            "record_citations": [f"{scope.lower()}-record-{index + 1}"],
            "reverse_citations": [],
            "title": f"{scope} {document_type.value}",
        }
        for index, document_type in enumerate(DOCUMENT_TYPES)
    ]
    return ManagerReadModel(
        data=cast(JSONValue, {"scope": scope, "documents": documents}),
        source_refs=(source,),
        as_of="2026-10-03T12:00:00Z",
        snapshot_token=f"fixture-documents-{scope}-v0",
        derivation=Derivation(kind="direct", inputs=(source.source_id,), version="v0"),
        availability=Availability(status=ReadModelStatus.KNOWN, complete=True, reason="Deterministic Source Document fixture."),
    )


@dataclass(frozen=True, slots=True)
class SourceDocumentsFixtureProvider:
    """Read-only provider for deterministic Source Document scope fixtures."""

    scope: str = "A0"

    def __post_init__(self) -> None:
        if self.scope not in DOCUMENT_SCOPES:
            raise ValueError(f"unknown Source Document fixture scope: {self.scope!r}")

    def read(self, resource: str = DOCUMENTS_RESOURCE, *, snapshot_token: str | None = None) -> ManagerReadModel:
        del resource, snapshot_token
        return build_source_documents_fixture(self.scope)


__all__ = [
    "DOCUMENTS_RESOURCE",
    "DOCUMENT_SCOPES",
    "DOCUMENT_TYPES",
    "ApprovedDirectoryBoundary",
    "DocumentIndexState",
    "DocumentType",
    "SourceDocument",
    "SourceDocumentsFixtureProvider",
    "SourceDocumentsViewModel",
    "build_source_documents_fixture",
    "render_documents_view",
    "render_source_documents",
    "render_source_documents_view",
    "source_documents_hook",
    "source_documents_view",
]
