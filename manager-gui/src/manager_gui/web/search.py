"""Deterministic, read-only global Search read model for Manager GUI S6-T1.

The search surface consumes one approved ``ManagerReadModel v0`` resource named
``search``.  The source payload is an explicit index of records and documents;
this module never scans paths, opens SQLite, dereferences a private locator,
uses semantic ranking, calls an LLM, or exposes a mutation operation.

Search is deliberately explainable: every hit retains its stable identity,
canonical searchable fields, source references, matched fields, and a stable
URL built from the caller's opaque query context.  Matching is case-insensitive
literal substring matching for every whitespace-delimited query term.  Terms
must all be present, and result ordering is a fixed key rather than relevance.
An incomplete source page remains ``partial`` even when it has no local hits;
it therefore never makes a global no-match claim until the approved index is
complete.
"""

# HTML fragments intentionally keep readable markup.
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from html import escape
from typing import cast

from ..models import (
    Availability,
    Derivation,
    JSONValue,
    ManagerReadModel,
    ReadModelError,
    ReadModelStatus,
    SourceReference,
)
from ..provider import ManagerDataProvider
from .navigation import PageWindow, context_link, query_values
from .status import DisplayState, render_operational_state, render_status_block

SEARCH_RESOURCE = "search"
SEARCH_INTEGRATION_HOOK = "search-view"

# These are the only owner fields searched by the deterministic index.  The
# record/document kind and source are filters/provenance, not hidden content.
SEARCH_FIELDS: tuple[str, ...] = (
    "record_id",
    "schema",
    "hash",
    "revision",
    "campaign",
    "strategy",
    "run",
    "family",
    "status",
    "date",
    "title",
    "statement",
    "safe_summary",
    "document_title",
)


class SearchState(StrEnum):
    """Search completeness states independent of source status."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    EMPTY = "empty"
    API_UNAVAILABLE = "api_unavailable"
    ERROR = "error"


# Friendly aliases make the boundary discoverable without duplicating enums.
SearchResultState = SearchState
SearchCompleteness = SearchState


class SearchFixtureState(StrEnum):
    """Deterministic source states needed to test the S6-T1 boundary."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    EMPTY = "empty"
    API_UNAVAILABLE = "api_unavailable"


SEARCH_FIXTURE_STATES: tuple[str, ...] = tuple(state.value for state in SearchFixtureState)


_FIELD_ALIASES: Mapping[str, tuple[str, ...]] = {
    "record_id": ("record_id", "recordId", "id", "uid", "key", "document_id", "documentId"),
    "schema": ("schema", "schema_id", "schemaId", "schema_name"),
    "hash": ("hash", "content_hash", "contentHash", "digest", "sha256", "sha_256"),
    "revision": ("revision", "version", "record_revision", "recordRevision"),
    "campaign": ("campaign", "campaign_id", "campaignId"),
    "strategy": ("strategy", "strategy_id", "strategyId"),
    "run": ("run", "run_id", "runId"),
    "family": (
        "family",
        "family_id",
        "familyId",
        "strategy_family",
        "strategy_family_id",
        "strategyFamily",
    ),
    "status": ("status", "state", "outcome", "verification_status", "verify_status"),
    "date": (
        "date",
        "record_date",
        "recordDate",
        "occurred_at",
        "created_at",
        "updated_at",
        "published_at",
        "changed_at",
    ),
    "title": ("title", "name", "label", "heading"),
    "statement": ("statement", "claim", "thesis", "assertion"),
    "safe_summary": ("safe_summary", "safeSummary", "summary", "description"),
    "document_title": ("document_title", "documentTitle"),
}

_ID_KEYS = _FIELD_ALIASES["record_id"]


def _mapping(value: object) -> Mapping[str, object] | None:
    if isinstance(value, Mapping):
        return cast(Mapping[str, object], value)
    return None


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(value)
    if isinstance(value, Mapping):
        return (value,)
    return ()


def _text(value: object) -> str | None:
    """Turn an explicitly named field/reference into deterministic text."""

    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, Mapping):
        # References are intentionally limited to identity/display keys.  We do
        # not recursively index arbitrary payload keys.
        for key in ("id", "record_id", "recordId", "document_id", "documentId", "title", "name", "label", "value"):
            candidate = _text(value.get(key))
            if candidate is not None:
                return candidate
        return None
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        values = tuple(candidate for item in value if (candidate := _text(item)) is not None)
        return ", ".join(values) or None
    return None


def _first_text(item: Mapping[str, object], keys: Sequence[str]) -> str | None:
    for key in keys:
        candidate = _text(item.get(key))
        if candidate is not None:
            return candidate
    return None


def _field_value(item: Mapping[str, object], field_name: str) -> str | None:
    return _first_text(item, _FIELD_ALIASES[field_name])


def _source_ids(item: Mapping[str, object]) -> tuple[str, ...]:
    values: list[str] = []
    for key in ("source_ref", "source_id", "sourceRef", "sourceId", "source_refs", "source_ids", "sources"):
        raw = item.get(key)
        if isinstance(raw, str) and raw.strip():
            values.append(raw.strip())
        elif isinstance(raw, Mapping):
            source_id = _first_text(raw, ("source_id", "sourceId", "id", "ref"))
            if source_id is not None:
                values.append(source_id)
        elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
            for entry in raw:
                if isinstance(entry, str) and entry.strip():
                    values.append(entry.strip())
                elif isinstance(entry, Mapping):
                    source_id = _first_text(entry, ("source_id", "sourceId", "id", "ref"))
                    if source_id is not None:
                        values.append(source_id)
    return tuple(dict.fromkeys(values))


def _source_locator(item: Mapping[str, object], refs: Mapping[str, SourceReference], source_ids: Sequence[str]) -> str | None:
    direct = _first_text(item, ("source_locator", "sourceLocator", "locator", "source_url", "sourceUrl", "url", "uri", "href"))
    if direct is not None:
        return direct
    for source_id in source_ids:
        source = refs.get(source_id)
        if source is not None:
            return source.locator
    return None


def _document_title(item: Mapping[str, object]) -> str | None:
    direct = _field_value(item, "document_title")
    if direct is not None:
        return direct
    document = _mapping(item.get("document"))
    if document is not None:
        return _first_text(document, ("title", "name", "label", "document_title", "documentTitle"))
    return None


def _record_type(item: Mapping[str, object], *, kind: str) -> str:
    selected = _first_text(item, ("record_type", "recordType", "document_type", "documentType", "type", "kind", "category"))
    if selected is None:
        return "document" if kind == "document" else "record"
    return selected.casefold().replace("_", "-").replace(" ", "-")


def _iter_index_items(data: object) -> tuple[tuple[str, Mapping[str, object]], ...]:
    """Read only declared index containers, preserving record/document kind."""

    payload = _mapping(data)
    if payload is None:
        if isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
            return tuple(
                ("record", item)
                for value in data
                if (item := _mapping(value)) is not None
            )
        return ()

    pairs: list[tuple[str, Mapping[str, object]]] = []
    consumed: set[str] = set()

    def add_container(raw: object, kind: str) -> None:
        for value in _sequence(raw):
            item = _mapping(value)
            if item is not None:
                pairs.append((kind, item))

    for key in ("records", "record_index", "search_records"):
        if key in payload:
            consumed.add(key)
            add_container(payload[key], "record")
    for key in ("documents", "document_index", "source_documents", "search_documents"):
        if key in payload:
            consumed.add(key)
            add_container(payload[key], "document")

    # ``items``/``entries``/``results`` are valid only as declared search-index
    # entries. Their own kind/type selects record versus document.
    for key in ("items", "entries", "results"):
        if key not in payload:
            continue
        consumed.add(key)
        for value in _sequence(payload[key]):
            item = _mapping(value)
            if item is None:
                continue
            raw_kind = _first_text(item, ("result_kind", "resultKind", "kind"))
            pairs.append(("document" if raw_kind == "document" else "record", item))

    search_index = _mapping(payload.get("search_index"))
    if search_index is not None:
        for key in ("records", "record_index"):
            add_container(search_index.get(key), "record")
        for key in ("documents", "document_index", "source_documents"):
            add_container(search_index.get(key), "document")
        for key in ("items", "entries", "results"):
            for value in _sequence(search_index.get(key)):
                item = _mapping(value)
                if item is None:
                    continue
                raw_kind = _first_text(item, ("result_kind", "resultKind", "kind"))
                pairs.append(("document" if raw_kind == "document" else "record", item))

    # A single explicitly typed item is useful for small public reads and does
    # not turn an arbitrary mapping into a recursive filesystem/index scan.
    if not pairs and any(key in payload for key in (*_ID_KEYS, "record_type", "document_type", "type")):
        kind = "document" if any(key in payload for key in ("document_id", "documentId", "document_type", "documentType")) else "record"
        pairs.append((kind, payload))
    del consumed  # documents the explicit-container boundary above
    return tuple(pairs)


def _pagination_metadata(data: object) -> Mapping[str, object]:
    payload = _mapping(data)
    if payload is None:
        return {}
    for key in ("pagination", "page", "paging", "search_pagination"):
        candidate = _mapping(payload.get(key))
        if candidate is not None:
            return candidate
    return {}


def _bool_value(item: Mapping[str, object], keys: Sequence[str]) -> bool | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, bool):
            return value
    return None


def _canonical_query(value: object) -> str:
    text = _text(value) or ""
    return " ".join(text.split())


def _query_terms(query: str) -> tuple[str, ...]:
    return tuple(term.casefold() for term in query.split() if term)


def _search_values(item: Mapping[str, object], *, kind: str, source_refs: Mapping[str, SourceReference], source_ids: Sequence[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for field_name in SEARCH_FIELDS:
        value = _field_value(item, field_name)
        if field_name == "record_id" and value is None:
            value = _first_text(item, _ID_KEYS)
        if field_name == "document_title" and value is None:
            value = _document_title(item)
        if field_name in {"schema", "revision"} and value is None:
            # A source's declared schema/revision is provenance for the item,
            # not a guessed owner field, but remains searchable as that field.
            for source_id in source_ids:
                source = source_refs.get(source_id)
                if source is None:
                    continue
                value = source.schema if field_name == "schema" else source.revision
                if value is not None:
                    break
        if value is not None:
            values[field_name] = value
    if kind == "document" and "document_title" not in values:
        values["document_title"] = values.get("title", "")
    return {field_name: values[field_name] for field_name in SEARCH_FIELDS if values.get(field_name)}


def _stable_key(values: Mapping[str, str], *, kind: str, record_type: str, source_ids: Sequence[str]) -> tuple[str, ...]:
    return (
        kind,
        record_type,
        values.get("record_id", ""),
        values.get("revision", ""),
        values.get("title", values.get("document_title", "")),
        "|".join(source_ids),
    )


def _matching_fields(values: Mapping[str, str], query: str) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    terms = _query_terms(query)
    if not terms:
        return (), ()
    matched: list[str] = []
    reasons: list[str] = []
    for term in terms:
        fields = tuple(field_name for field_name in SEARCH_FIELDS if term in values.get(field_name, "").casefold())
        if not fields:
            return None
        for field_name in fields:
            if field_name not in matched:
                matched.append(field_name)
        reasons.append(f"{term!r} matched {', '.join(fields)}")
    ordered = tuple(field_name for field_name in SEARCH_FIELDS if field_name in matched)
    return ordered, tuple(reasons)


@dataclass(frozen=True, slots=True)
class SearchHit:
    """One deterministic hit with explainable fields and source provenance."""

    result_id: str
    result_kind: str
    record_type: str
    record_id: str
    schema: str | None = None
    hash: str | None = None
    revision: str | None = None
    campaign: str | None = None
    strategy: str | None = None
    run: str | None = None
    family: str | None = None
    status: str | None = None
    date: str | None = None
    title: str | None = None
    statement: str | None = None
    safe_summary: str | None = None
    document_title: str | None = None
    source_ids: tuple[str, ...] = ()
    source_refs: tuple[SourceReference, ...] = ()
    source_locator: str | None = None
    matched_fields: tuple[str, ...] = ()
    match_reasons: tuple[str, ...] = ()
    stable_url: str | None = None

    def __post_init__(self) -> None:
        if not self.result_id.strip() or not self.record_id.strip():
            raise ValueError("search hit identity must be non-empty")
        if self.result_kind not in {"record", "document"}:
            raise ValueError("result_kind must be record or document")
        if not self.record_type.strip():
            raise ValueError("record_type must be non-empty")
        if tuple(field for field in self.matched_fields if field not in SEARCH_FIELDS):
            raise ValueError("matched_fields contains an unknown search field")
        if not all(isinstance(source, SourceReference) for source in self.source_refs):
            raise ValueError("source_refs must contain SourceReference values")

    @property
    def id(self) -> str:
        """Compatibility alias for clients that call every result ``id``."""

        return self.record_id

    @property
    def kind(self) -> str:
        return self.result_kind

    @property
    def reason(self) -> str:
        """Human-readable deterministic explanation of the hit."""

        if not self.match_reasons:
            return "No query terms were supplied; this entry is indexed."
        return "; ".join(self.match_reasons)

    @property
    def match_reason(self) -> str:
        """Singular compatibility alias for :attr:`reason`."""

        return self.reason

    @property
    def url(self) -> str | None:
        """Stable local URL alias used by simple result consumers."""

        return self.stable_url

    @property
    def matched_field_names(self) -> tuple[str, ...]:
        return self.matched_fields

    @property
    def source(self) -> tuple[SourceReference, ...]:
        return self.source_refs

    def to_dict(self) -> dict[str, object]:
        return {
            "result_id": self.result_id,
            "result_kind": self.result_kind,
            "record_type": self.record_type,
            "record_id": self.record_id,
            "schema": self.schema,
            "hash": self.hash,
            "revision": self.revision,
            "campaign": self.campaign,
            "strategy": self.strategy,
            "run": self.run,
            "family": self.family,
            "status": self.status,
            "date": self.date,
            "title": self.title,
            "statement": self.statement,
            "safe_summary": self.safe_summary,
            "document_title": self.document_title,
            "source_ids": list(self.source_ids),
            "source_refs": [source.to_dict() for source in self.source_refs],
            "source_locator": self.source_locator,
            "matched_fields": list(self.matched_fields),
            "matched_field_names": list(self.matched_fields),
            "match_reasons": list(self.match_reasons),
            "match_reason": self.match_reason,
            "reason": self.reason,
            "stable_url": self.stable_url,
            "url": self.url,
        }


@dataclass(frozen=True, slots=True)
class SearchPagination:
    """Pagination integrity metadata; it never pretends a partial page is global."""

    complete: bool
    has_more: bool
    indexed_count: int | None = None
    next_cursor: str | None = None
    page: int = 1
    page_size: int = 20

    @property
    def global_no_match_is_proven(self) -> bool:
        return self.complete and not self.has_more

    @property
    def is_partial(self) -> bool:
        return not self.complete or self.has_more

    def to_dict(self) -> dict[str, object]:
        return {
            "complete": self.complete,
            "has_more": self.has_more,
            "indexed_count": self.indexed_count,
            "next_cursor": self.next_cursor,
            "page": self.page,
            "page_size": self.page_size,
            "global_no_match_is_proven": self.global_no_match_is_proven,
        }


@dataclass(frozen=True, slots=True)
class SearchViewModel:
    """Typed deterministic projection of a ``search`` read-model envelope."""

    read_model: ManagerReadModel
    query: str
    hits: tuple[SearchHit, ...]
    state: SearchState
    record_type: str | None = None
    source: str | None = None
    pagination: SearchPagination = field(default_factory=lambda: SearchPagination(True, False))

    @classmethod
    def from_read_model(
        cls,
        model: ManagerReadModel,
        *,
        query: str = "",
        record_type: str | None = None,
        source: str | None = None,
        source_id: str | None = None,
        query_context: str | Mapping[str, object] | None = None,
    ) -> SearchViewModel:
        selected_query = _canonical_query(query)
        selected_type = _canonical_query(record_type) or None
        selected_source = _canonical_query(source if source is not None else source_id) or None
        source_map = {source_ref.source_id: source_ref for source_ref in model.source_refs}
        parsed: list[SearchHit] = []
        seen: set[tuple[str, str, str, tuple[str, ...]]] = set()
        for kind, item in _iter_index_items(model.data):
            source_ids = _source_ids(item)
            values = _search_values(item, kind=kind, source_refs=source_map, source_ids=source_ids)
            record_id = values.get("record_id")
            if record_id is None:
                continue
            result_type = _record_type(item, kind=kind)
            if selected_type is not None and selected_type.casefold() not in {kind, result_type.casefold()}:
                continue
            if selected_source is not None:
                source_candidates = set(source_ids)
                for source_id in source_ids:
                    ref = source_map.get(source_id)
                    if ref is not None:
                        source_candidates.update(
                            value for value in (ref.owner, ref.kind, ref.locator) if value is not None
                        )
                if not any(selected_source.casefold() in candidate.casefold() for candidate in source_candidates):
                    continue
            matches = _matching_fields(values, selected_query)
            if matches is None:
                continue
            matched_fields, reasons = matches
            marker = (kind, record_id, values.get("revision", ""), source_ids)
            if marker in seen:
                continue
            seen.add(marker)
            refs = tuple(source_map[source_id] for source_id in source_ids if source_id in source_map)
            parsed.append(
                SearchHit(
                    result_id=record_id,
                    result_kind=kind,
                    record_type=result_type,
                    record_id=record_id,
                    schema=values.get("schema"),
                    hash=values.get("hash"),
                    revision=values.get("revision"),
                    campaign=values.get("campaign"),
                    strategy=values.get("strategy"),
                    run=values.get("run"),
                    family=values.get("family"),
                    status=values.get("status"),
                    date=values.get("date"),
                    title=values.get("title"),
                    statement=values.get("statement"),
                    safe_summary=values.get("safe_summary"),
                    document_title=values.get("document_title"),
                    source_ids=source_ids,
                    source_refs=refs,
                    source_locator=_source_locator(item, source_map, source_ids),
                    matched_fields=matched_fields,
                    match_reasons=reasons,
                )
            )
        parsed.sort(key=lambda hit: _stable_key(
            {field_name: getattr(hit, field_name) or "" for field_name in SEARCH_FIELDS},
            kind=hit.result_kind,
            record_type=hit.record_type,
            source_ids=hit.source_ids,
        ))
        source_complete = model.availability.complete
        pagination_data = _pagination_metadata(model.data)
        explicit_complete = _bool_value(pagination_data, ("complete", "is_complete", "global_complete"))
        # A source envelope marked incomplete cannot be made globally complete
        # by optimistic page metadata from an adapter.
        complete = source_complete and (explicit_complete is not False)
        has_more = _bool_value(pagination_data, ("has_more", "hasMore", "more"))
        if has_more is None:
            has_more = not complete
        indexed_count: int | None = None
        for key in ("indexed_count", "total", "total_indexed", "count"):
            raw_count = pagination_data.get(key)
            if isinstance(raw_count, int) and not isinstance(raw_count, bool) and raw_count >= 0:
                indexed_count = raw_count
                break
        next_cursor = _text(pagination_data.get("next_cursor", pagination_data.get("nextCursor")))
        if model.availability.status is ReadModelStatus.API_UNAVAILABLE:
            state = SearchState.API_UNAVAILABLE
        elif model.availability.status not in {ReadModelStatus.KNOWN, ReadModelStatus.MISSING}:
            state = SearchState.ERROR
        elif model.availability.status is ReadModelStatus.MISSING:
            # Missing means the approved scope has no recorded index; it is an
            # explicit empty state, not evidence that a partial page was searched.
            state = SearchState.EMPTY
        elif not complete or has_more:
            state = SearchState.PARTIAL
        elif not parsed:
            state = SearchState.EMPTY
        else:
            state = SearchState.COMPLETE
        pagination = SearchPagination(
            complete=complete,
            has_more=has_more,
            indexed_count=indexed_count,
            next_cursor=next_cursor,
        )
        view = cls(
            read_model=model,
            query=selected_query,
            hits=tuple(parsed),
            state=state,
            record_type=selected_type,
            source=selected_source,
            pagination=pagination,
        )
        if query_context is not None:
            context_values = query_values(query_context)
            if selected_query:
                context_values["q"] = selected_query
            view = view.with_context(context_values)
        return view

    @property
    def results(self) -> tuple[SearchHit, ...]:
        return self.hits

    @property
    def status(self) -> ReadModelStatus:
        return self.read_model.availability.status

    @property
    def source_refs(self) -> tuple[SourceReference, ...]:
        return self.read_model.source_refs

    @property
    def as_of(self) -> str | None:
        return self.read_model.as_of

    @property
    def snapshot_token(self) -> str | None:
        return self.read_model.snapshot_token

    @property
    def complete(self) -> bool:
        return self.pagination.complete and self.state is SearchState.COMPLETE

    @property
    def partial(self) -> bool:
        return self.state is SearchState.PARTIAL

    @property
    def global_no_match(self) -> bool:
        """True only when an approved complete known index returned no hits."""

        return (
            self.state is SearchState.EMPTY
            and self.pagination.global_no_match_is_proven
            and self.read_model.availability.status is ReadModelStatus.KNOWN
        )

    @property
    def pagination_complete(self) -> bool:
        return self.pagination.complete

    @property
    def indexed_count(self) -> int:
        return self.pagination.indexed_count if self.pagination.indexed_count is not None else len(self.hits)

    def with_context(self, context: str | Mapping[str, object] | None) -> SearchViewModel:
        """Return a copy whose hit URLs preserve opaque shell context."""

        if context is None:
            return self
        updated: list[SearchHit] = []
        for hit in self.hits:
            updates: dict[str, object] = {
                "result_id": hit.result_id,
                "record_type": hit.record_type,
            }
            if hit.result_kind == "document":
                updates["document_id"] = hit.record_id
            else:
                updates["record_id"] = hit.record_id
            updated.append(replace(hit, stable_url=context_link(context, view="search", **updates)))
        return replace(self, hits=tuple(updated))

    def to_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "state": self.state.value,
            "record_type": self.record_type,
            "source": self.source,
            "hits": [hit.to_dict() for hit in self.hits],
            "results": [hit.to_dict() for hit in self.hits],
            "pagination": self.pagination.to_dict(),
            "global_no_match": self.global_no_match,
            "source_refs": [source.to_dict() for source in self.read_model.source_refs],
            "as_of": self.read_model.as_of,
            "snapshot_token": self.read_model.snapshot_token,
            "availability": self.read_model.availability.to_dict(),
            "errors": [error.to_dict() for error in self.read_model.errors],
        }

    def render(
        self,
        *,
        base_path: str = "/?view=search",
        query_context: str | Mapping[str, object] | None = None,
    ) -> str:
        context: str | Mapping[str, object] = query_context or base_path
        values = query_values(context)
        if self.query:
            values["q"] = self.query
        values["view"] = "search"
        context = values
        contextual = self.with_context(context)
        window = PageWindow(
            page=PageWindow.from_query(context, total=len(self.hits)).page,
            page_size=PageWindow.from_query(context, total=len(self.hits)).page_size,
            total=len(self.hits),
        )
        paged_hits = contextual.hits[window.start : window.stop]
        filter_type = self.record_type or "all"
        filter_source = self.source or "all"
        observed = self.as_of or "Unavailable"
        snapshot = self.snapshot_token or "Unavailable"
        source_summary = ", ".join(source.source_id for source in self.source_refs) or "None recorded"
        pieces = [
            f'<section class="search-page" data-integration-hook="{SEARCH_INTEGRATION_HOOK}" '
            f'data-search-state="{self.state.value}" data-search-complete="{str(self.pagination.complete).lower()}" '
            f'data-pagination-complete="{str(self.pagination.complete).lower()}" '
            f'data-search-query="{escape(self.query, quote=True)}" '
            f'data-search-record-type="{escape(filter_type, quote=True)}" '
            f'data-search-source="{escape(filter_source, quote=True)}">',
            '<p class="eyebrow">Search · deterministic approved index</p>',
            '<h1 class="page-title" data-page-title tabindex="-1">Search</h1>',
            '<p class="page-intro">Literal, case-insensitive matching across approved records and document metadata; no semantic or LLM ranking is used.</p>',
            f'<p class="context-line search-context"><span><strong>Query</strong> {escape(self.query or "None")}</span>'
            f'<span><strong>Observed</strong> {escape(observed)}</span><span><strong>Snapshot</strong> {escape(snapshot)}</span>'
            f'<span><strong>Sources</strong> {escape(source_summary)}</span></p>',
            f'<p class="search-pagination-integrity" data-pagination-integrity="{"complete" if self.pagination.complete else "partial"}">'
            + (
                "The approved index is complete; an empty result is a global no-match only for this known snapshot."
                if self.pagination.complete
                else "Only the indexed page is available; an empty page is not a global no-match."
            )
            + "</p>",
            render_status_block(self.read_model),
        ]
        if self.state is SearchState.EMPTY:
            detail = (
                "No approved record or document matches this query in the complete snapshot."
                if self.global_no_match
                else "No matching entry is currently indexed in this scope."
                if self.query
                else "Enter a query to search the approved record and document index."
            )
            pieces.append(render_operational_state(DisplayState.EMPTY, detail=detail))
        elif self.state is SearchState.PARTIAL:
            pieces.append(
                render_operational_state(
                    DisplayState.PARTIAL,
                    detail=(
                        "The current indexed page has no matching entry; global no-match is not established."
                        if not self.hits
                        else "Search results cover only the current indexed page; more records may match."
                    ),
                )
            )
        elif self.state is SearchState.API_UNAVAILABLE:
            pieces.append(
                render_operational_state(
                    DisplayState.ERROR,
                    detail="The approved Search API is unavailable; no private-storage fallback is used.",
                )
            )
        elif self.state is SearchState.ERROR:
            pieces.append(
                render_operational_state(
                    DisplayState.ERROR,
                    detail="The approved Search read model cannot be used as complete current truth.",
                )
            )
        elif not paged_hits:
            pieces.append(render_operational_state(DisplayState.EMPTY, detail="No indexed entries are visible on this page."))
        else:
            pieces.append(
                '<ol class="search-result-list" aria-label="Deterministic search results">'
                + "".join(_render_hit(hit) for hit in paged_hits)
                + "</ol>"
            )
        pieces.append(window.render(context, view="search"))
        pieces.append("</section>")
        return "".join(pieces)


def _safe_source_link(source: SourceReference) -> str:
    """Render approved public/fixture locators without dereferencing paths."""

    locator = source.locator
    lowered = locator.casefold()
    if lowered.startswith(("file:", "\\\\")) or (len(locator) > 2 and locator[1] == ":"):
        return f'<span class="search-source-locator">{escape(locator)}</span>'
    return f'<a class="search-source-link" data-source-id="{escape(source.source_id, quote=True)}" href="{escape(locator, quote=True)}">{escape(locator)}</a>'


def _render_hit(hit: SearchHit) -> str:
    target = hit.stable_url or context_link(None, view="search", result_id=hit.result_id, record_type=hit.record_type)
    title = hit.title or hit.document_title or hit.record_id
    fields = ", ".join(hit.matched_fields) or "none (browse entry)"
    source_markup = (
        '<ul class="search-source-list">'
        + "".join(
            f'<li data-source-id="{escape(source.source_id, quote=True)}"><strong>{escape(source.source_id)}</strong> · '
            f'{escape(source.owner)} · { _safe_source_link(source) }</li>'
            for source in hit.source_refs
        )
        + "</ul>"
        if hit.source_refs
        else '<span class="search-source-missing">Missing / Unconfirmed source reference</span>'
    )
    values = (
        ("record id", hit.record_id),
        ("type", hit.record_type),
        ("schema", hit.schema),
        ("hash", hit.hash),
        ("revision", hit.revision),
        ("campaign", hit.campaign),
        ("strategy", hit.strategy),
        ("run", hit.run),
        ("family", hit.family),
        ("status", hit.status),
        ("date", hit.date),
        ("title", hit.title),
        ("statement", hit.statement),
        ("safe summary", hit.safe_summary),
        ("document title", hit.document_title),
    )
    details = "".join(
        f'<div><dt>{escape(label)}</dt><dd>{escape(value) if value is not None else "Missing / Unconfirmed"}</dd></div>'
        for label, value in values
    )
    return (
        f'<li class="search-result" data-result-id="{escape(hit.result_id, quote=True)}" '
        f'data-result-kind="{escape(hit.result_kind, quote=True)}" data-record-type="{escape(hit.record_type, quote=True)}">'
        f'<h2><a class="search-result-link" data-link-kind="{escape(hit.result_kind, quote=True)}" '
        f'href="{escape(target, quote=True)}">{escape(title)}</a></h2>'
        f'<p class="search-hit-reason"><strong>Matched fields</strong> {escape(fields)} · '
        f'<strong>Reason</strong> {escape(hit.reason)}</p>'
        f'<dl class="search-result-details">{details}</dl>'
        f'<div class="search-result-sources"><strong>Source</strong>{source_markup}</div>'
        "</li>"
    )


def search_view(
    provider: ManagerDataProvider,
    *,
    query: str = "",
    record_type: str | None = None,
    source: str | None = None,
    source_id: str | None = None,
    snapshot_token: str | None = None,
) -> SearchViewModel:
    """Read the approved Search resource exactly once and build its view model."""

    model = provider.read(SEARCH_RESOURCE, snapshot_token=snapshot_token)
    return SearchViewModel.from_read_model(
        model,
        query=query,
        record_type=record_type,
        source=source,
        source_id=source_id,
    )


def render_search(
    model: ManagerReadModel,
    *,
    query: str = "",
    record_type: str | None = None,
    source: str | None = None,
    source_id: str | None = None,
    base_path: str = "/?view=search",
    query_context: str | Mapping[str, object] | None = None,
) -> str:
    """Render an already-read Search envelope without a second provider call."""

    view = SearchViewModel.from_read_model(
        model,
        query=query,
        record_type=record_type,
        source=source,
        source_id=source_id,
    )
    return view.render(base_path=base_path, query_context=query_context)


def _query_from_context(context: str | Mapping[str, object] | None) -> str:
    return _canonical_query(query_values(context).get("q", ""))


def render_search_view(
    source: ManagerDataProvider | ManagerReadModel,
    *,
    query: str | None = None,
    record_type: str | None = None,
    source_filter: str | None = None,
    source_id: str | None = None,
    base_path: str = "/?view=search",
    query_context: str | Mapping[str, object] | None = None,
    snapshot_token: str | None = None,
) -> str:
    """S6-T1 hook accepting a provider seam or an already-cached v0 envelope."""

    selected_query = _query_from_context(query_context or base_path) if query is None else query
    selected_source = source_filter if source_filter is not None else source_id
    model = (
        source
        if isinstance(source, ManagerReadModel)
        else source.read(SEARCH_RESOURCE, snapshot_token=snapshot_token)
    )
    return render_search(
        model,
        query=selected_query,
        record_type=record_type,
        source=selected_source,
        base_path=base_path,
        query_context=query_context,
    )


# Naming aliases for integrations that call the page "global search".
global_search_view = search_view
render_global_search_view = render_search_view
search_hook = render_search_view


def _fixture_source(source_id: str, locator: str) -> SourceReference:
    return SourceReference(
        source_id=source_id,
        owner="manager-gui-fixture",
        kind="approved-search-index",
        locator=locator,
        schema="manager-gui.search-fixture.v0",
        revision="fixture-v0",
    )


def build_search_fixture(state: SearchFixtureState | str = SearchFixtureState.COMPLETE) -> ManagerReadModel:
    """Build deterministic records/documents without reading any storage."""

    selected = SearchFixtureState(state)
    source_records = _fixture_source("fixture-search-records", "fixture://manager-gui/search/records")
    source_documents = _fixture_source("fixture-search-documents", "fixture://manager-gui/search/documents")
    if selected is SearchFixtureState.EMPTY:
        return ManagerReadModel(
            data={"records": [], "documents": [], "pagination": {"complete": False, "has_more": False, "indexed_count": 0}},
            source_refs=(),
            as_of=None,
            snapshot_token=None,
            derivation=Derivation(kind="direct", version="search-fixture-v0"),
            availability=Availability(
                status=ReadModelStatus.MISSING,
                complete=False,
                reason="No approved Search records are present in this fixture scope.",
            ),
        )
    if selected is SearchFixtureState.API_UNAVAILABLE:
        source = _fixture_source("fixture-search-api", "fixture://manager-gui/search/api")
        return ManagerReadModel(
            data={},
            source_refs=(source,),
            as_of=None,
            snapshot_token=None,
            derivation=Derivation(kind="direct", inputs=(source.source_id,), version="v0"),
            availability=Availability(
                status=ReadModelStatus.API_UNAVAILABLE,
                complete=False,
                reason="The approved Search API is unavailable in this environment.",
                retryable=True,
            ),
            errors=(
                ReadModelError(
                    code="search_api_unavailable",
                    message="No private-storage fallback is permitted for global Search.",
                    source_ref=source.source_id,
                    retryable=True,
                ),
            ),
        )
    records: list[dict[str, object]] = [
        {
            "record_id": "campaign-fixture-1",
            "record_type": "campaign",
            "schema": "workspace.campaign.v1",
            "hash": "sha256:campaign-fixture-1",
            "revision": "r3",
            "campaign": "campaign-fixture-1",
            "status": "active",
            "date": "2026-10-01",
            "title": "Fixture campaign",
            "statement": "Validate the deterministic research path.",
            "safe_summary": "Approved fixture campaign for read-only search.",
            "source_ref": source_records.source_id,
        },
        {
            "record_id": "strategy-fixture-1",
            "record_type": "strategy",
            "schema": "apex.strategy.v2",
            "hash": "sha256:strategy-fixture-1",
            "revision": "v2",
            "campaign": "campaign-fixture-1",
            "strategy": "strategy-fixture-1",
            "family": "family-fixture-1",
            "status": "validated",
            "date": "2026-10-02",
            "title": "Fixture strategy",
            "statement": "A deterministic strategy statement.",
            "safe_summary": "Strategy metadata from an approved read model.",
            "source_ref": source_records.source_id,
        },
        {
            "record_id": "run-fixture-1",
            "record_type": "run",
            "schema": "runtime.run.v1",
            "hash": "sha256:run-fixture-1",
            "revision": "run-r1",
            "campaign": "campaign-fixture-1",
            "strategy": "strategy-fixture-1",
            "run": "run-fixture-1",
            "family": "family-fixture-1",
            "status": "completed",
            "date": "2026-10-03",
            "title": "Fixture run",
            "safe_summary": "Completed deterministic fixture run.",
            "source_ref": source_records.source_id,
        },
    ]
    documents: list[dict[str, object]] = [
        {
            "document_id": "document-fixture-1",
            "document_type": "report",
            "schema": "manager.document.v1",
            "hash": "sha256:document-fixture-1",
            "revision": "doc-r1",
            "status": "published",
            "date": "2026-10-03",
            "title": "Fixture research report",
            "document_title": "Fixture research report",
            "statement": "Documented evidence statement.",
            "safe_summary": "Approved document title is searchable metadata only.",
            "source_ref": source_documents.source_id,
        }
    ]
    if selected is SearchFixtureState.PARTIAL:
        records = records[:2]
        documents = []
    pagination = {
        "complete": selected is SearchFixtureState.COMPLETE,
        "has_more": selected is SearchFixtureState.PARTIAL,
        "indexed_count": len(records) + len(documents),
        "next_cursor": "fixture-search-next-v0" if selected is SearchFixtureState.PARTIAL else None,
    }
    errors: tuple[ReadModelError, ...] = ()
    availability = Availability(
        status=ReadModelStatus.KNOWN,
        complete=selected is SearchFixtureState.COMPLETE,
        reason=(
            "The complete fixture contains all approved record and document search entries."
            if selected is SearchFixtureState.COMPLETE
            else "Only the current approved Search page is indexed; more entries may exist."
        ),
    )
    if selected is SearchFixtureState.PARTIAL:
        errors = (
            ReadModelError(
                code="search_page_partial",
                message="The approved Search index has more pages; no global no-match claim is allowed.",
                source_ref=source_records.source_id,
                details={"has_more": True},
            ),
        )
    return ManagerReadModel(
        data=cast(JSONValue, {"records": records, "documents": documents, "pagination": pagination}),
        source_refs=(source_records, source_documents),
        as_of="2026-10-03T12:00:00Z",
        snapshot_token=f"fixture-search-{selected.value}-v0",
        derivation=Derivation(
            kind="direct",
            inputs=(source_records.source_id, source_documents.source_id),
            version="v0",
        ),
        availability=availability,
        errors=errors,
    )


@dataclass(frozen=True, slots=True)
class SearchFixtureProvider:
    """Read-only provider for deterministic S6-T1 Search fixtures."""

    state: SearchFixtureState

    def __init__(self, state: SearchFixtureState | str = SearchFixtureState.COMPLETE) -> None:
        object.__setattr__(self, "state", SearchFixtureState(state))

    def read(self, resource: str = SEARCH_RESOURCE, *, snapshot_token: str | None = None) -> ManagerReadModel:
        if resource != SEARCH_RESOURCE:
            raise ValueError(f"Search fixture does not serve resource {resource!r}")
        del snapshot_token
        return build_search_fixture(self.state)


def search_fixture_provider(state: SearchFixtureState | str = SearchFixtureState.COMPLETE) -> SearchFixtureProvider:
    """Return a deterministic provider suitable for focused page tests."""

    return SearchFixtureProvider(state)


# Additional discoverable aliases matching the existing fixture conventions.
SearchFixture = SearchFixtureState
GlobalSearchViewModel = SearchViewModel
SearchResult = SearchHit
build_global_search_fixture = build_search_fixture
fixture_search_provider = search_fixture_provider


__all__ = [
    "SEARCH_FIELDS",
    "SEARCH_FIXTURE_STATES",
    "SEARCH_INTEGRATION_HOOK",
    "SEARCH_RESOURCE",
    "GlobalSearchViewModel",
    "SearchCompleteness",
    "SearchFixture",
    "SearchFixtureProvider",
    "SearchFixtureState",
    "SearchHit",
    "SearchPagination",
    "SearchResult",
    "SearchResultState",
    "SearchState",
    "SearchViewModel",
    "build_global_search_fixture",
    "build_search_fixture",
    "fixture_search_provider",
    "global_search_view",
    "render_global_search_view",
    "render_search",
    "render_search_view",
    "search_fixture_provider",
    "search_hook",
    "search_view",
]
