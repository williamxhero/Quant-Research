"""Source-event history for the Manager GUI S5-T2 surface.

The module is a page-local, read-only adapter.  ``HistoryViewModel`` consumes a
:class:`manager_gui.models.ManagerReadModel` whose ``data`` contains explicit
``events``/``history``/``timeline``/``records`` entries, or category-keyed
sequences.  Each admitted entry must carry an explicit source event time and one
of the supported event categories.  ``changed_at``, ``updated_at``,
``known_at``, and GUI lifecycle assumptions are deliberately never promoted to
a history event.

The public integration seam is :func:`render_history_view`.  It accepts either
an already-read ``ManagerReadModel`` or a ``ManagerDataProvider`` and, in the
latter case, performs exactly one ``read("history")``.  It never reads a path,
scans a filesystem, opens SQLite, or exposes a mutation operation.  ``scope``
is an opaque fixture/read-model context; the deterministic fixture helper
covers ``A0``, ``S3``, ``CPA``, and ``V1.x`` without touching storage.
"""

# HTML fragments intentionally keep readable markup even when a line is long.
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from html import escape
from typing import cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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
from .status import DisplayState, display_state_for, render_operational_state, render_status_block


class HistoryEventType(StrEnum):
    """Source event categories admitted to the S5 history timeline."""

    CAMPAIGN = "campaign"
    STUDY = "study"
    RUN = "run"
    PUBLICATION = "publication"
    ARTIFACT = "artifact"
    GENOME_EVENT = "genome-event"
    REPLICATION = "replication"
    REVALIDATION = "revalidation"
    REPORT_BUILD = "report-build"


HISTORY_EVENT_TYPES: tuple[HistoryEventType, ...] = tuple(HistoryEventType)
HISTORY_SCOPES: tuple[str, ...] = ("A0", "S3", "CPA", "V1.x")

_CATEGORY_ALIASES = {
    "genome_event": HistoryEventType.GENOME_EVENT,
    "genome-event": HistoryEventType.GENOME_EVENT,
    "genome event": HistoryEventType.GENOME_EVENT,
    "report_build": HistoryEventType.REPORT_BUILD,
    "report-build": HistoryEventType.REPORT_BUILD,
    "report build": HistoryEventType.REPORT_BUILD,
}
_EVENT_TIME_KEYS = (
    "source_event_time",
    "source_event_at",
    "event_time",
    "event_at",
    "occurred_at",
    "happened_at",
    "occurred_on",
)


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


def _nested_text(item: Mapping[str, object], keys: Sequence[str]) -> str | None:
    direct = _first_text(item, keys)
    if direct is not None:
        return direct
    for context_key in ("source", "provenance", "event", "temporal"):
        nested = _mapping(item.get(context_key))
        if nested is not None:
            value = _first_text(nested, keys)
            if value is not None:
                return value
    return None


def _normalise(value: object) -> str | None:
    text = _text(value)
    if text is None:
        return None
    return text.strip().lower().replace("_", "-").replace(" ", "-")


def _event_type(item: Mapping[str, object], group: object = None) -> HistoryEventType | None:
    raw = _first_text(item, ("event_type", "event_category", "record_type", "type", "kind", "category"))
    raw = raw or _text(group)
    normalised = _normalise(raw)
    if normalised is None:
        return None
    try:
        return HistoryEventType(normalised)
    except ValueError:
        return _CATEGORY_ALIASES.get(normalised.replace("-", " "), _CATEGORY_ALIASES.get(normalised))


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(value)
    if isinstance(value, Mapping):
        return (value,)
    return ()


def _iter_event_items(data: object) -> tuple[tuple[object, object], ...]:
    """Yield ``(group, item)`` pairs without interpreting arbitrary mappings."""

    pairs: list[tuple[object, object]] = []
    if isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
        pairs.extend((None, value) for value in data)
    else:
        container = _mapping(data)
        if container is None:
            return ()
        if _event_type(container) is not None:
            return ((None, container),)
        consumed: set[str] = set()
        for key in ("events", "history", "timeline", "records", "items"):
            if key in container:
                consumed.add(key)
                pairs.extend((None, value) for value in _sequence(container[key]))
        for key, value in container.items():
            if key in consumed:
                continue
            if _normalise(key) in {
                event_type.value for event_type in HISTORY_EVENT_TYPES
            }:
                pairs.extend((key, value) for value in _sequence(value))
            elif _mapping(value) is not None and _event_type(_mapping(value) or {}) is not None:
                pairs.append((None, value))
    return tuple(pairs)


def _source_ids(item: Mapping[str, object]) -> tuple[str, ...]:
    values: list[str] = []
    for key in ("source_ref", "source_id", "source_ref_id", "sourceRef", "source_refs", "source_ids"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
        elif isinstance(value, Mapping):
            source_id = _first_text(value, ("source_id", "id", "source_ref"))
            if source_id:
                values.append(source_id)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            values.extend(
                source_id
                for entry in value
                for source_id in _source_ids({"source_ref": entry})
            )
    return tuple(dict.fromkeys(values))


def _source_locator(item: Mapping[str, object], source_refs: Mapping[str, SourceReference]) -> tuple[str | None, str | None]:
    source_ids = _source_ids(item)
    explicit = _first_text(item, ("source_locator", "locator", "source_url", "uri", "href"))
    if explicit is not None:
        return (source_ids[0] if source_ids else None, explicit)
    for source_id in source_ids:
        source = source_refs.get(source_id)
        if source is not None:
            return source.source_id, source.locator
    return (source_ids[0] if source_ids else None, None)


def _document_ids(item: Mapping[str, object]) -> tuple[str, ...]:
    values: list[str] = []
    for key in ("document_id", "document_ref", "document_ids", "document_refs", "source_document"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
        elif isinstance(value, Mapping):
            identifier = _first_text(value, ("document_id", "documentId", "id"))
            if identifier:
                values.append(identifier)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for entry in value:
                values.extend(_document_ids({"document_id": entry}))
    return tuple(dict.fromkeys(values))


def _context_url(
    base_path: str,
    query: Mapping[str, object] | str | None,
    *,
    view: str,
    **updates: object,
) -> str:
    return context_link(query if query is not None else base_path, view=view, **updates)


def _record_id(item: Mapping[str, object]) -> str | None:
    return _first_text(item, ("record_id", "recordId", "id", "uid", "key"))


_CATALOG_PREFIX = "__catalog__:"


def _title_and_detail(item: Mapping[str, object]) -> tuple[str, str]:
    title = _first_text(item, ("title", "name", "label", "heading"))
    detail = _first_text(item, ("summary", "description", "detail", "message", "text", "value"))
    if title is None:
        title = detail[:120] if detail else f"{_CATALOG_PREFIX}history.event.fallback_title"
    if detail is None:
        detail = f"{_CATALOG_PREFIX}history.event.fallback_detail"
    return title, detail


def _is_history_fixture(model: ManagerReadModel) -> bool:
    return any(
        source.owner == "manager-gui-fixture"
        and source.kind == "source-event-record"
        and source.schema == "manager-gui.history-fixture.v0"
        and source.revision == "v0"
        and source.locator.startswith("fixture://manager-gui/history/")
        for source in model.source_refs
    )


def _history_fixture_text(
    translator: Translator,
    event: HistoryEvent,
    field: str,
    *,
    fixture: bool,
    scope: str | None = None,
) -> str:
    key = f"history.fixture.{event.event_type.value.replace('-', '_')}.{field}"
    if fixture and key in _l3_method_history_catalog.ENTRIES:
        return translator.t(key, scope=scope or "")
    value = event.title if field == "title" else event.detail
    if value is None:
        return translator.t("history.event.fallback_detail")
    if value.startswith(_CATALOG_PREFIX):
        return translator.t(value.removeprefix(_CATALOG_PREFIX))
    return value


def _event_key(event: HistoryEvent) -> tuple[str, str, str]:
    return (event.source_event_time, event.event_id, event.event_type.value)


@dataclass(frozen=True, slots=True)
class HistoryEvent:
    """One explicit, source-backed event admitted to the history timeline."""

    event_id: str
    event_type: HistoryEventType
    title: str
    source_event_time: str
    record_id: str | None = None
    source_id: str | None = None
    source_locator: str | None = None
    detail: str | None = None
    known_at: str | None = None
    document_ids: tuple[str, ...] = ()
    raw: Mapping[str, object] | None = None

    @property
    def category(self) -> str:
        """String category used by HTML/data clients."""

        return self.event_type.value

    @property
    def event_time(self) -> str:
        """Compatibility alias for clients using the generic timeline name."""

        return self.source_event_time

    def to_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "title": self.title,
            "source_event_time": self.source_event_time,
            "record_id": self.record_id,
            "source_id": self.source_id,
            "source_locator": self.source_locator,
            "detail": self.detail,
            "known_at": self.known_at,
            "document_ids": list(self.document_ids),
        }


@dataclass(frozen=True, slots=True)
class HistoryViewModel:
    """Deterministic history projection retaining only explicit source events."""

    read_model: ManagerReadModel
    events: tuple[HistoryEvent, ...]
    scope: str | None = None

    @classmethod
    def from_read_model(
        cls, model: ManagerReadModel, *, scope: str | None = None
    ) -> HistoryViewModel:
        payload = _mapping(model.data) or {}
        source_refs = {source.source_id: source for source in model.source_refs}
        parsed: list[HistoryEvent] = []
        seen: set[tuple[str, str, str]] = set()
        for index, (group, raw_value) in enumerate(_iter_event_items(model.data), start=1):
            item = _mapping(raw_value)
            if item is None:
                continue
            event_type = _event_type(item, group)
            source_event_time = _nested_text(item, _EVENT_TIME_KEYS)
            if event_type is None or source_event_time is None:
                continue
            title, detail = _title_and_detail(item)
            record_id = _record_id(item)
            source_id, source_locator = _source_locator(item, source_refs)
            event_id = _first_text(item, ("event_id", "eventId", "id", "record_id", "uid"))
            event_id = event_id or f"{event_type.value}:{source_event_time}:{title}:{index}"
            marker = (event_id, source_event_time, event_type.value)
            if marker in seen:
                continue
            seen.add(marker)
            parsed.append(
                HistoryEvent(
                    event_id=event_id,
                    event_type=event_type,
                    title=title,
                    source_event_time=source_event_time,
                    record_id=record_id,
                    source_id=source_id,
                    source_locator=source_locator,
                    detail=detail,
                    known_at=_nested_text(item, ("known_at", "system_known_at", "recorded_at")),
                    document_ids=_document_ids(item),
                    raw=item,
                )
            )
        parsed.sort(key=_event_key)
        selected_scope = scope or _first_text(payload, ("scope", "fixture", "batch"))
        return cls(model, tuple(parsed), selected_scope)

    @property
    def status(self) -> ReadModelStatus:
        return self.read_model.availability.status

    @property
    def event_types(self) -> tuple[HistoryEventType, ...]:
        return tuple(dict.fromkeys(event.event_type for event in self.events))

    def to_dict(self) -> dict[str, object]:
        return {
            "scope": self.scope,
            "events": [event.to_dict() for event in self.events],
            "availability": self.read_model.availability.to_dict(),
        }

    def context_url(
        self,
        *,
        base_path: str = "/?view=history",
        query: Mapping[str, object] | str | None = None,
        scope: str | None = None,
    ) -> str:
        parsed = urlsplit(base_path)
        values = dict(parse_qsl(parsed.query, keep_blank_values=True))
        if isinstance(query, str):
            values.update(parse_qsl(urlsplit(query).query or query.lstrip("?"), keep_blank_values=True))
        elif query is not None:
            values.update((str(key), str(value)) for key, value in query.items() if value is not None)
        values["view"] = "history"
        selected_scope = scope if scope is not None else self.scope
        if selected_scope:
            values["scope"] = selected_scope
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", urlencode(sorted(values.items())), parsed.fragment))

    def render(
        self,
        *,
        base_path: str = "/?view=history",
        query: Mapping[str, object] | str | None = None,
        translator: Translator | None = None,
    ) -> str:
        selected_translator = translator or Translator()
        fixture = _is_history_fixture(self.read_model)
        scope = self.scope or selected_translator.t("method_history.all_scopes")
        scope_links = "".join(
            f'<a class="history-scope-link" data-history-scope="{escape(selected, quote=True)}" '
            f'href="{escape(self.context_url(base_path=base_path, query=query, scope=selected), quote=True)}"'
            f'>{escape(selected_translator.label("method_history.scope", selected))}</a>'
            for selected in HISTORY_SCOPES
        )
        window = PageWindow.from_query(query if query is not None else base_path, total=len(self.events))
        paged_events = self.events[window.start : window.stop]
        related = (
            f'<nav class="history-related-nav" aria-label="History related sources">'
            f'<a class="history-methodology-link" href="{escape(_context_url(base_path, query, view="methodology"), quote=True)}">Methodology</a>'
            f'<a class="history-documents-link" href="{escape(_context_url(base_path, query, view="source-documents"), quote=True)}">Source Documents</a></nav>'
        )
        if not paged_events:
            state = display_state_for(self.read_model)
            if self.read_model.availability.status is ReadModelStatus.KNOWN:
                empty = render_operational_state(
                    DisplayState.EMPTY,
                    translator=selected_translator,
                    detail=selected_translator.t("history.empty_scope"),
                )
            else:
                empty = render_operational_state(
                    state,
                    translator=selected_translator,
                    detail=selected_translator.t("history.unavailable_scope"),
                )
            body = empty
        else:
            rows = "".join(
                _render_event(
                    event,
                    base_path=base_path,
                    query=query,
                    translator=selected_translator,
                    fixture=fixture,
                )
                for event in paged_events
            )
            body = (
                f'<ol class="history-event-list" aria-label="{escape(selected_translator.t("history.timeline_aria"))}">'
                f"{rows}</ol>"
            )
        return (
            f'<section class="history-page" data-integration-hook="history-view" '
            f'data-history-scope="{escape(scope, quote=True)}">'
            f'<p class="eyebrow">{escape(selected_translator.t("history.eyebrow"))}</p>'
            f'<h1 class="page-title" data-page-title tabindex="-1">{escape(selected_translator.t("history.title"))}</h1>'
            f'<p class="page-intro">{escape(selected_translator.t("history.intro"))}</p>'
            f'<p class="boundary-note" data-boundary="canonical-fact">{selected_translator.html("history.boundary")}</p>'
            f'<p class="context-line history-context"><strong>{escape(selected_translator.t("method_history.scope"))}</strong> {escape(scope)}</p>'
            f"{related}"
            f'<nav class="history-scope-nav" aria-label="{escape(selected_translator.t("history.scopes_aria"))}">{scope_links}</nav>'
            f"{render_status_block(self.read_model, translator=selected_translator)}{body}{window.render(query if query is not None else base_path, view='history')}</section>"
        )


def _render_event(
    event: HistoryEvent,
    *,
    base_path: str,
    query: Mapping[str, object] | str | None,
    translator: Translator,
    fixture: bool,
) -> str:
    locator = (
        f'<a class="history-source-link" data-link-kind="source-artifact" href="{escape(event.source_locator, quote=True)}">'
        f"{escape(event.source_locator)}</a>"
        if event.source_locator
        else f'<span class="history-source-missing">{escape(translator.t("history.event.missing_locator"))}</span>'
    )
    document_links = " · ".join(
        f'<a class="history-document-link" data-link-kind="document" href="{escape(_context_url(base_path, query, view="source-documents", document_id=document_id), quote=True)}">'
        f"{escape(document_id)}</a>"
        for document_id in event.document_ids
    ) or f'<span class="history-source-missing">{escape(translator.t("history.event.missing_document"))}</span>'
    record = (
        f'<a class="history-record-link" data-link-kind="record" href="{escape(_context_url(base_path, query, view="history", record_id=event.record_id), quote=True)}">'
        f"{escape(event.record_id)}</a>"
        if event.record_id
        else translator.t("method_history.missing")
    )
    title = _history_fixture_text(translator, event, "title", fixture=fixture, scope=event.raw.get("scope") if event.raw else None)
    detail = _history_fixture_text(translator, event, "detail", fixture=fixture, scope=event.raw.get("scope") if event.raw else None)
    event_type = translator.label("history.event_type", event.event_type.value)
    record_label = translator.t("history.event.record")
    source_label = translator.t("history.event.source")
    document_label = translator.t("history.event.document")
    return (
        f'<li class="history-event" data-event-id="{escape(event.event_id, quote=True)}" '
        f'data-event-type="{escape(event.event_type.value, quote=True)}" '
        f'data-source-event-time="{escape(event.source_event_time, quote=True)}">'
        f'<time datetime="{escape(event.source_event_time, quote=True)}">{escape(event.source_event_time)}</time>'
        f'<span class="history-event-type">{event_type}</span>'
        f'<strong>{title}</strong><p>{detail}</p>'
        f'<p class="history-event-meta">{escape(record_label)}: {record} · {escape(source_label)}: {locator} · {escape(document_label)}: {document_links}</p></li>'
    )


def history_view(
    provider: ManagerDataProvider,
    *,
    scope: str | None = None,
    snapshot_token: str | None = None,
) -> HistoryViewModel:
    """Read the approved ``history`` resource once and build its view model."""

    model = provider.read("history", snapshot_token=snapshot_token)
    return HistoryViewModel.from_read_model(model, scope=scope)


def render_history(
    model: ManagerReadModel,
    *,
    scope: str | None = None,
    base_path: str = "/?view=history",
    query: Mapping[str, object] | str | None = None,
    translator: Translator | None = None,
) -> str:
    """Render an already-read history envelope without a second provider call."""

    return HistoryViewModel.from_read_model(model, scope=scope).render(
        base_path=base_path, query=query, translator=translator
    )


def render_history_view(
    source: ManagerDataProvider | ManagerReadModel,
    *,
    scope: str | None = None,
    base_path: str = "/?view=history",
    query: Mapping[str, object] | str | None = None,
    snapshot_token: str | None = None,
    translator: Translator | None = None,
) -> str:
    """S5-T3 hook accepting either a provider seam or a cached read model."""

    model = (
        source
        if isinstance(source, ManagerReadModel)
        else provider_read(source, snapshot_token=snapshot_token)
    )
    return render_history(
        model, scope=scope, base_path=base_path, query=query, translator=translator
    )


def provider_read(provider: ManagerDataProvider, *, snapshot_token: str | None = None) -> ManagerReadModel:
    """Keep the provider call in one named seam for test doubles and inspection."""

    return provider.read("history", snapshot_token=snapshot_token)


def build_history_fixture(scope: str = "A0") -> ManagerReadModel:
    """Build deterministic S5 history data for A0/S3/CPA/V1.x navigation."""

    if scope not in HISTORY_SCOPES:
        raise ValueError(f"unknown history fixture scope: {scope!r}")
    source = SourceReference(
        source_id=f"fixture-history-{scope}",
        owner="manager-gui-fixture",
        kind="source-event-record",
        locator=f"fixture://manager-gui/history/{scope}",
        schema="manager-gui.history-fixture.v0",
        revision="v0",
    )
    categories = tuple(HistoryEventType)
    events = [
        {
            "event_id": f"{scope.lower()}-{event_type.value}-1",
            "event_type": event_type.value,
            "title": f"{scope} {event_type.value} event",
            "summary": f"Explicit {event_type.value} source event for {scope}.",
            "source_event_time": f"2026-10-{index + 1:02d}T08:00:00Z",
            "record_id": f"{scope.lower()}-record-{index + 1}",
            "source_ref": source.source_id,
            "document_refs": [
                f"{scope.lower()}-{('plan', 'design', 'report', 'retrospective', 'future-idea', 'external-source', 'raw-evidence')[index % 7]}-{index % 7 + 1}"
            ],
        }
        for index, event_type in enumerate(categories)
    ]
    return ManagerReadModel(
        data=cast(JSONValue, {"scope": scope, "events": events}),
        source_refs=(source,),
        as_of="2026-10-03T12:00:00Z",
        snapshot_token=f"fixture-history-{scope}-v0",
        derivation=Derivation(kind="direct", inputs=(source.source_id,), version="v0"),
        availability=Availability(
            status=ReadModelStatus.KNOWN,
            complete=True,
            reason="Deterministic source-event fixture.",
        ),
    )


@dataclass(frozen=True, slots=True)
class HistoryFixtureProvider:
    """Read-only provider for deterministic S5 scope fixtures."""

    scope: str = "A0"

    def __post_init__(self) -> None:
        if self.scope not in HISTORY_SCOPES:
            raise ValueError(f"unknown history fixture scope: {self.scope!r}")

    def read(self, resource: str = "history", *, snapshot_token: str | None = None) -> ManagerReadModel:
        del snapshot_token
        if resource != "history":
            return build_history_fixture(self.scope)
        return build_history_fixture(self.scope)


__all__ = [
    "HISTORY_EVENT_TYPES",
    "HISTORY_SCOPES",
    "HistoryEvent",
    "HistoryEventType",
    "HistoryFixtureProvider",
    "HistoryViewModel",
    "build_history_fixture",
    "history_view",
    "render_history",
    "render_history_view",
]
