"""Atlas overview and research-object navigation for the Manager GUI.

The module is deliberately page-local.  It consumes the public
``ManagerReadModel`` envelope, normalizes only explicit record fields, and
returns deterministic HTML suitable for the shared T2 shell to embed.  It does
not read private storage or infer conclusions from counts.
"""

# HTML fragments intentionally use long readable lines.
# ruff: noqa: E501

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from html import escape
from typing import TypeAlias, cast
from urllib.parse import parse_qsl, urlencode, urlsplit

from ..fixtures import FixtureState, build_fixture
from ..models import ManagerReadModel, ReadModelStatus
from ..provider import ManagerDataProvider
from ..reader import ReaderProjection, project_read_model
from .i18n import Translator
from .i18n.catalog import l3_atlas_story as _l3_atlas_story_catalog
from .locators import public_locator
from .navigation import clear_filters_link, context_link, query_values
from .reader_surface import ReaderPage, render_reader_surface
from .research_story import ResearchStoryViewModel, StoryEntry
from .source_support import source_support_computation, source_support_entry
from .status import DisplayState, display_state_for, render_operational_state, render_status_block

LIFECYCLE_SPINE: tuple[str, ...] = (
    "campaign",
    "hypothesis",
    "candidate",
    "run",
    "evidence",
    "qualification",
    "replication",
    "revalidation",
)

LIFECYCLE_LABELS: Mapping[str, str] = {
    record_type: f"label.atlas.lifecycle.{record_type}"
    for record_type in LIFECYCLE_SPINE
}

_FILTER_KEYS: tuple[str, ...] = (
    "record_type",
    "state",
    "date",
    "source",
    "availability",
)
_CONTEXT_ORDER: tuple[str, ...] = (
    "view",
    "fixture",
    "panel",
    "q",
    "record_type",
    "state",
    "date",
    "source",
    "availability",
    "campaign",
    "study",
    "strategy_family",
    "mode",
    "record_id",
)

QueryContext: TypeAlias = str | Mapping[str, object] | None


def _is_fixture(model: ManagerReadModel) -> bool:
    """Only localize owner prose for an exact shipped synthetic envelope."""

    if not (model.snapshot_token or "").startswith("fixture-") and model.data != {}:
        return False
    return any(model == build_fixture(state, resource="atlas") for state in FixtureState)


def _is_complete_atlas_fixture(model: ManagerReadModel) -> bool:
    if model.snapshot_token != "fixture-complete-v0":
        return False
    return model == build_fixture(FixtureState.COMPLETE, resource="atlas")


def _atlas_presentation_model(model: ManagerReadModel, *, sample: bool) -> ManagerReadModel:
    if sample and _is_complete_atlas_fixture(model):
        return build_fixture(FixtureState.COMPLETE, resource="stories")
    return model


def _fixture_text(value: str | None, *, translator: Translator, fixture: bool) -> str:
    if value is None:
        return ""
    key = _l3_atlas_story_catalog.FIXTURE_KEYS.get(value) if fixture else None
    if key is not None:
        return escape(translator.t(key))
    return f'<span data-owner-text="true">{translator.source_text(value)}</span>'


def _fixture_status_model(model: ManagerReadModel, translator: Translator) -> ManagerReadModel:
    def localize(value: str | None) -> str | None:
        key = _l3_atlas_story_catalog.FIXTURE_KEYS.get(value or "")
        return translator.t(key) if key is not None else value

    return replace(
        model,
        availability=replace(model.availability, reason=localize(model.availability.reason)),
        errors=tuple(replace(error, message=localize(error.message) or "") for error in model.errors),
    )


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _mapping(value: object) -> Mapping[str, object] | None:
    if isinstance(value, Mapping):
        return cast(Mapping[str, object], value)
    return None


def _first_text(item: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        value = _text(item.get(key))
        if value is not None:
            return value
    return None


def _record_type(value: object) -> str | None:
    selected = _text(value)
    if selected is None:
        return None
    normalized = selected.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized.endswith("ies"):
        normalized = normalized[:-3] + "y"
    else:
        plural_lifecycle_types = {f"{record_type}s": record_type for record_type in LIFECYCLE_SPINE}
        normalized = plural_lifecycle_types.get(normalized, normalized)
    return normalized


def _availability(value: object) -> str | None:
    if isinstance(value, Mapping):
        value = value.get("status")
    return _text(value)


def _source(value: object) -> str | None:
    if isinstance(value, Mapping):
        return _first_text(cast(Mapping[str, object], value), "source_id", "id", "locator", "owner")
    return _text(value)


def _query_pairs(context: QueryContext) -> list[tuple[str, str]]:
    if context is None:
        return []
    if isinstance(context, str):
        query = (
            urlsplit(context).query if "?" in context or "://" in context else context.lstrip("?")
        )
        return [(key, value) for key, value in parse_qsl(query, keep_blank_values=True) if key]
    pairs: list[tuple[str, str]] = []
    for key, value in context.items():
        if not isinstance(key, str) or not key:
            continue
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            pairs.extend((key, str(entry)) for entry in value)
        elif value is not None:
            pairs.append((key, str(value)))
    return pairs


def _stable_query(pairs: Sequence[tuple[str, str]]) -> str:
    """Encode query pairs in a deterministic order while retaining context."""

    order = {key: index for index, key in enumerate(_CONTEXT_ORDER)}
    grouped: dict[str, list[str]] = {}
    for key, value in pairs:
        grouped.setdefault(key, []).append(value)
    ordered_keys = sorted(grouped, key=lambda key: (order.get(key, len(order)), key))
    flattened = [(key, value) for key in ordered_keys for value in grouped[key]]
    return urlencode(flattened)


@dataclass(frozen=True, slots=True)
class AtlasFilters:
    """Explicit, bookmarkable Atlas filters.

    ``date`` is an exact ISO-date prefix match against an explicit record
    ``changed_at``/``updated_at`` value.  No date is invented for records that
    do not carry one.
    """

    record_type: str | None = None
    state: str | None = None
    date: str | None = None
    source: str | None = None
    availability: str | None = None

    def __post_init__(self) -> None:
        for name in _FILTER_KEYS:
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be a non-empty string or None")

    @classmethod
    def from_query(cls, context: QueryContext) -> AtlasFilters:
        values = dict(_query_pairs(context))
        return cls(**{key: _text(values.get(key)) for key in _FILTER_KEYS})

    def as_query(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (key, value) for key in _FILTER_KEYS if (value := getattr(self, key)) is not None
        )

    def matches(self, record: AtlasRecord) -> bool:
        if self.record_type is not None and record.record_type != _record_type(self.record_type):
            return False
        if self.state is not None and record.state != self.state:
            return False
        if self.date is not None and not (
            record.changed_at is not None and record.changed_at.startswith(self.date)
        ):
            return False
        if self.source is not None and record.source != self.source:
            return False
        return self.availability is None or record.availability == self.availability


AtlasFilter = AtlasFilters


@dataclass(frozen=True, slots=True)
class AtlasRecord:
    """A display-safe projection of one explicit lifecycle record."""

    record_id: str
    record_type: str
    title: str
    state: str | None = None
    changed_at: str | None = None
    source: str | None = None
    availability: str | None = None
    conclusion_state: str | None = None
    research_gaps: tuple[str, ...] = ()
    frontier: bool = False
    payload: Mapping[str, object] = field(default_factory=dict, repr=False, compare=False)

    @property
    def lifecycle_label(self) -> str:
        return LIFECYCLE_LABELS.get(self.record_type, self.record_type)

    @property
    def is_blocked_or_unavailable(self) -> bool:
        return self.availability in {
            ReadModelStatus.BLOCKED.value,
            ReadModelStatus.API_UNAVAILABLE.value,
        } or (self.state or "").lower() in {"blocked", "unavailable", "api_unavailable"}

    @property
    def is_unresolved(self) -> bool:
        if self.conclusion_state is None:
            return False
        return self.conclusion_state.lower() in {
            "unresolved",
            "open",
            "pending",
            "unknown",
            "missing",
            "not_resolved",
        }


@dataclass(frozen=True, slots=True)
class AtlasStatusGroup:
    """A count of records sharing an explicitly recorded state."""

    state: str
    count: int


@dataclass(frozen=True, slots=True)
class AtlasResearchGap:
    """An explicitly published research gap, kept separate from missing data."""

    gap_id: str
    title: str
    detail: str | None = None
    source: str | None = None
    record_id: str | None = None


@dataclass(frozen=True, slots=True)
class AtlasViewModel:
    """Deterministic Atlas data ready for a page renderer."""

    read_model: ManagerReadModel
    records: tuple[AtlasRecord, ...]
    filters: AtlasFilters = field(default_factory=AtlasFilters)
    status_groups: tuple[AtlasStatusGroup, ...] = ()
    recently_changed: tuple[AtlasRecord, ...] = ()
    blocked_or_unavailable: tuple[AtlasRecord, ...] = ()
    unresolved_conclusions: tuple[AtlasRecord, ...] = ()
    research_gaps: tuple[AtlasResearchGap, ...] = ()
    frontier: tuple[AtlasRecord, ...] = ()

    @classmethod
    def from_read_model(
        cls,
        model: ManagerReadModel,
        *,
        filters: AtlasFilters | None = None,
        recent_limit: int | None = 8,
    ) -> AtlasViewModel:
        if recent_limit is not None and recent_limit < 0:
            raise ValueError("recent_limit must be non-negative or None")
        selected_filters = filters or AtlasFilters()
        all_records = _extract_records(model.data)
        records = tuple(record for record in all_records if selected_filters.matches(record))
        explicit_states = Counter(record.state for record in records if record.state is not None)
        groups = tuple(
            AtlasStatusGroup(state=state, count=explicit_states[state])
            for state in sorted(explicit_states)
        )
        with_dates = sorted(
            (record for record in records if record.changed_at is not None),
            key=lambda record: (record.changed_at or "", record.record_id),
            reverse=True,
        )
        recently_changed = tuple(with_dates if recent_limit is None else with_dates[:recent_limit])
        blocked = tuple(record for record in records if record.is_blocked_or_unavailable)
        unresolved = tuple(record for record in records if record.is_unresolved)
        gaps = _extract_gaps(model.data, records, filters=selected_filters)
        frontier = tuple(record for record in records if record.frontier)
        return cls(
            read_model=model,
            records=records,
            filters=selected_filters,
            status_groups=groups,
            recently_changed=recently_changed,
            blocked_or_unavailable=blocked,
            unresolved_conclusions=unresolved,
            research_gaps=gaps,
            frontier=frontier,
        )

    @property
    def status_counts(self) -> tuple[tuple[str, int], ...]:
        """Compatibility-friendly tuple form for clients that do not import groups."""

        return tuple((group.state, group.count) for group in self.status_groups)

    @property
    def lifecycle_counts(self) -> tuple[tuple[str, int], ...]:
        counts = Counter(record.record_type for record in self.records)
        return tuple(
            (record_type, counts[record_type])
            for record_type in LIFECYCLE_SPINE
            if counts[record_type]
        )

    @property
    def as_of(self) -> str | None:
        return self.read_model.as_of

    @property
    def snapshot_token(self) -> str | None:
        return self.read_model.snapshot_token

    @property
    def source_refs(self):
        return self.read_model.source_refs


def _iter_record_items(data: object) -> list[tuple[str | None, Mapping[str, object]]]:
    result: list[tuple[str | None, Mapping[str, object]]] = []
    if isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
        for value in data:
            item = _mapping(value)
            if item is not None:
                result.append((None, item))
        return result
    container = _mapping(data)
    if container is None:
        return result
    raw_records = container.get("records", container.get("items", container.get("objects")))
    if isinstance(raw_records, Sequence) and not isinstance(raw_records, (str, bytes, bytearray)):
        for value in raw_records:
            item = _mapping(value)
            if item is not None:
                result.append((None, item))
    for key, value in container.items():
        if key in {"records", "items", "objects", "research_gaps"}:
            continue
        if key == "frontier":
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                for entry in value:
                    item = _mapping(entry)
                    if item is not None:
                        result.append(("frontier", item))
            continue
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            group_type = _record_type(key)
            for entry in value:
                item = _mapping(entry)
                if item is not None:
                    result.append((group_type, item))
        elif (item := _mapping(value)) is not None and _first_text(
            item, "id", "record_id", "object_id", "uid"
        ):
            result.append((_record_type(key), item))
    return result


def _explicit_conclusion_state(item: Mapping[str, object]) -> str | None:
    direct = _first_text(item, "conclusion_state", "conclusion_status")
    if direct is not None:
        return direct
    conclusion = _mapping(item.get("conclusion"))
    if conclusion is not None:
        return _first_text(conclusion, "state", "status")
    resolved = item.get("conclusion_resolved")
    if resolved is False:
        return "unresolved"
    return None


def _explicit_gap_items(item: Mapping[str, object]) -> tuple[tuple[str, str | None], ...]:
    raw = item.get("research_gaps", item.get("gaps", ()))
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        return ()
    gaps: list[tuple[str, str | None]] = []
    for value in raw:
        if isinstance(value, Mapping):
            mapping = cast(Mapping[str, object], value)
            title = _first_text(mapping, "title", "name", "id", "detail")
            detail = _first_text(mapping, "detail", "description")
        else:
            title = _text(value)
            detail = None
        if title is not None:
            gaps.append((title, detail))
    return tuple(gaps)


def _explicit_gaps(item: Mapping[str, object]) -> tuple[str, ...]:
    return tuple(title for title, _ in _explicit_gap_items(item))


def _record_from_item(item: Mapping[str, object], group_type: str | None) -> AtlasRecord | None:
    record_id = _first_text(item, "id", "record_id", "object_id", "uid")
    if record_id is None:
        return None
    record_type = _record_type(_first_text(item, "record_type", "type", "kind")) or group_type
    if record_type is None:
        return None
    title = _first_text(item, "title", "name", "label") or record_id
    return AtlasRecord(
        record_id=record_id,
        record_type=record_type,
        title=title,
        state=_first_text(item, "state", "status"),
        changed_at=_first_text(item, "changed_at", "updated_at", "modified_at"),
        source=_source(item.get("source", item.get("source_ref", item.get("source_id")))),
        availability=_availability(item.get("availability")),
        conclusion_state=_explicit_conclusion_state(item),
        research_gaps=_explicit_gaps(item),
        frontier=group_type == "frontier"
        or item.get("frontier") is True
        or item.get("is_frontier") is True,
        payload=item,
    )


def _extract_records(data: object) -> tuple[AtlasRecord, ...]:
    records: list[AtlasRecord] = []
    for group_type, item in _iter_record_items(data):
        record = _record_from_item(item, group_type)
        if record is not None:
            records.append(record)
    return tuple(records)


def _extract_gaps(
    data: object,
    records: Sequence[AtlasRecord],
    *,
    filters: AtlasFilters,
) -> tuple[AtlasResearchGap, ...]:
    mapping = _mapping(data)
    raw = () if mapping is None else mapping.get("research_gaps", ())
    result: list[AtlasResearchGap] = []
    selected_ids = {record.record_id for record in records}
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        for index, value in enumerate(raw, start=1):
            if isinstance(value, Mapping):
                item = cast(Mapping[str, object], value)
                gap_id = _first_text(item, "id", "gap_id") or f"gap-{index}"
                title = _first_text(item, "title", "name", "detail") or gap_id
                detail = _first_text(item, "detail", "description")
                record_id = _first_text(item, "record_id", "related_record_id")
                if filters.as_query() and record_id is not None and record_id not in selected_ids:
                    continue
                result.append(
                    AtlasResearchGap(
                        gap_id=gap_id,
                        title=title,
                        detail=detail,
                        source=_source(item.get("source", item.get("source_ref"))),
                        record_id=record_id,
                    )
                )
            elif (text := _text(value)) is not None:
                result.append(AtlasResearchGap(gap_id=f"gap-{index}", title=text))
    for record in records:
        for index, (title, detail) in enumerate(_explicit_gap_items(record.payload), start=1):
            result.append(
                AtlasResearchGap(
                    gap_id=f"{record.record_id}-gap-{index}",
                    title=title,
                    detail=detail,
                    record_id=record.record_id,
                    source=record.source,
                )
            )
    return tuple(result)


def atlas_link(
    record_id: str | None = None,
    *,
    query_context: QueryContext = None,
    filters: AtlasFilters | None = None,
    base_path: str = "/",
) -> str:
    """Build a stable Atlas URL while retaining the caller's query context."""

    if not isinstance(record_id, str) and record_id is not None:
        raise TypeError("record_id must be a string or None")
    pairs = _query_pairs(query_context)
    pairs = [(key, value) for key, value in pairs if key not in {"view", "record_id"}]
    if filters is not None:
        pairs = [(key, value) for key, value in pairs if key not in _FILTER_KEYS]
    pairs.append(("view", "atlas"))
    if filters is not None:
        pairs.extend(filters.as_query())
    if record_id is not None:
        pairs.append(("record_id", record_id))
    query = _stable_query(pairs)
    if not query:
        return base_path
    separator = "&" if "?" in base_path else "?"
    return f"{base_path}{separator}{query}"


build_atlas_link = atlas_link


def _context_with_filters(view: AtlasViewModel, context: QueryContext) -> QueryContext:
    pairs = _query_pairs(context)
    present = {key for key, _ in pairs}
    pairs.extend((key, value) for key, value in view.filters.as_query() if key not in present)
    return "?" + _stable_query(pairs) if pairs else None


def _record_link(record: AtlasRecord, query_context: QueryContext) -> str:
    return atlas_link(record.record_id, query_context=query_context)


def _story_link(record: AtlasRecord, query_context: QueryContext) -> str:
    """Link an Atlas object into the shared Research Story route."""

    pairs = [
        (key, value)
        for key, value in _query_pairs(query_context)
        if key not in {"view", "record_id"}
    ]
    pairs.append(("view", "stories"))
    pairs.append(("record_id", record.record_id))
    if record.record_type in {"campaign", "study", "strategy_family"}:
        pairs.append((record.record_type, record.record_id))
    query = _stable_query(pairs)
    return "/?" + query if query else "/?view=stories"


def _render_record(
    record: AtlasRecord,
    *,
    query_context: QueryContext,
    translator: Translator,
    fixture: bool,
) -> str:
    state = (
        f'<span class="atlas-record-state">{translator.label("atlas.state", record.state)}</span>'
        if record.state
        else ""
    )
    changed = (
        f'<time translate="no" datetime="{escape(record.changed_at, quote=True)}">'
        f'{translator.source_text(record.changed_at)}</time>'
        if record.changed_at
        else ""
    )
    source = (
        f'<span class="atlas-record-source" translate="no">'
        f'{translator.source_text(record.source)}</span>'
        if record.source
        else ""
    )
    metadata = " · ".join(part for part in (state, changed, source) if part)
    meta_markup = f'<span class="atlas-record-meta">{metadata}</span>' if metadata else ""
    return (
        f'<li class="atlas-record" data-record-id="{escape(record.record_id, quote=True)}" '
        f'data-record-type="{escape(record.record_type, quote=True)}">'
        f'<a href="{escape(_record_link(record, query_context), quote=True)}">'
        f'{_fixture_text(record.title, translator=translator, fixture=fixture)}</a>'
        f'<a class="atlas-story-link" data-record-story="{escape(record.record_id, quote=True)}" '
        f'href="{escape(_story_link(record, query_context), quote=True)}">'
        f'{escape(translator.t("atlas.record.open_story"))}</a>'
        f"{meta_markup}</li>"
    )


def _render_record_list(
    records: Sequence[AtlasRecord],
    *,
    query_context: QueryContext,
    translator: Translator,
    fixture: bool,
) -> str:
    return (
        '<ul class="atlas-record-list">'
        + "".join(
            _render_record(
                record, query_context=query_context, translator=translator, fixture=fixture
            )
            for record in records
        )
        + "</ul>"
    )


def _render_lifecycle(
    view: AtlasViewModel,
    *,
    query_context: QueryContext,
    translator: Translator,
    fixture: bool,
) -> str:
    by_type: dict[str, list[AtlasRecord]] = {record_type: [] for record_type in LIFECYCLE_SPINE}
    extras: list[AtlasRecord] = []
    for record in view.records:
        if record.record_type in by_type:
            by_type[record.record_type].append(record)
        else:
            extras.append(record)
    sections: list[str] = []
    for index, record_type in enumerate(LIFECYCLE_SPINE, start=1):
        records = by_type[record_type]
        body = (
            _render_record_list(
                records, query_context=query_context, translator=translator, fixture=fixture
            )
            if records
            else f'<p class="atlas-muted">{escape(translator.t("atlas.lifecycle.empty"))}</p>'
        )
        sections.append(
            f'<article class="atlas-spine-step" data-record-type="{record_type}">'
            f'<div class="atlas-step-heading"><span class="atlas-step-index">{index}</span>'
            f'<h3>{translator.label("atlas.lifecycle", record_type)}</h3>'
            f'<span class="atlas-count">{escape(translator.count("atlas.count.records", len(records)))}'
            f'</span></div>{body}</article>'
        )
    if extras:
        sections.append(
            '<article class="atlas-spine-step atlas-extra-records"><div class="atlas-step-heading">'
            f'<h3>{escape(translator.t("atlas.lifecycle.other"))}</h3>'
            f'<span class="atlas-count">{escape(translator.count("atlas.count.records", len(extras)))}</span>'
            f'</div>{_render_record_list(extras, query_context=query_context, translator=translator, fixture=fixture)}</article>'
        )
    return (
        '<section class="atlas-spine" aria-labelledby="atlas-spine-title">'
        f'<h2 id="atlas-spine-title">{escape(translator.t("atlas.lifecycle.title"))}</h2>'
        + "".join(sections)
        + "</section>"
    )


def _render_special_records(
    title_key: str,
    records: Sequence[AtlasRecord],
    *,
    query_context: QueryContext,
    section_id: str,
    translator: Translator,
    fixture: bool,
) -> str:
    if not records:
        return ""
    return (
        f'<section class="atlas-section" id="{section_id}" aria-labelledby="{section_id}-title">'
        f'<h2 id="{section_id}-title">{escape(translator.t(title_key))}</h2>'
        f'{_render_record_list(records, query_context=query_context, translator=translator, fixture=fixture)}</section>'
    )


def _filter_option_label(key: str, value: str, translator: Translator) -> tuple[str, bool]:
    domains = {"record_type": "atlas.lifecycle", "state": "atlas.state", "availability": "status"}
    if key not in domains:
        return translator.source_text(value), True
    label = translator.label(domains[key], value)
    if label.startswith("<code>") and label.endswith("</code>"):
        # Native option elements accept text, not the <code> wrapper used for
        # unknown open vocabulary elsewhere.
        return label.removeprefix("<code>").removesuffix("</code>"), True
    return label, False


def _render_filter_option(
    key: str, value: str, *, selected: bool, translator: Translator
) -> str:
    label, owner_text = _filter_option_label(key, value, translator)
    selected_attr = " selected" if selected else ""
    owner_attr = ' data-owner-text="true"' if owner_text else ""
    return (
        f'<option value="{escape(value, quote=True)}"{selected_attr}{owner_attr}>'
        f'{label}</option>'
    )


def _render_filters(
    view: AtlasViewModel, *, query_context: QueryContext, translator: Translator
) -> str:
    values = {key: getattr(view.filters, key) or "" for key in _FILTER_KEYS}
    context_pairs = [
        (key, value)
        for key, value in _query_pairs(query_context)
        if key not in {"view", "record_id", *_FILTER_KEYS}
    ]
    hidden = "".join(
        f'<input type="hidden" name="{escape(key, quote=True)}" value="{escape(value, quote=True)}">'
        for key, value in context_pairs
    )
    options = {
        "record_type": sorted(
            {record.record_type for record in view.records} | set(LIFECYCLE_SPINE)
        ),
        "state": sorted({record.state for record in view.records if record.state is not None}),
        "availability": sorted(
            {record.availability for record in view.records if record.availability is not None}
        ),
        "date": sorted({record.changed_at[:10] for record in view.records if record.changed_at}),
        "source": sorted({record.source for record in view.records if record.source is not None}),
    }
    clear_href = clear_filters_link(
        query_context, view="atlas", filter_keys=_FILTER_KEYS, selection_keys=("record_id",)
    )
    controls: list[str] = []
    for key in _FILTER_KEYS:
        if key == "date":
            controls.append(
                f'<label>{escape(translator.t("atlas.filters.date"))} '
                f'<input name="date" value="{escape(values[key], quote=True)}" '
                f'placeholder="{escape(translator.t("atlas.filters.date_placeholder"), quote=True)}"></label>'
            )
            continue
        choices = "".join(
            _render_filter_option(
                key, choice, selected=values[key] == choice, translator=translator
            )
            for choice in options[key]
        )
        label = translator.t(f"atlas.filters.{key}")
        controls.append(
            f'<label>{escape(label)} <select name="{key}">'
            f'<option value="">{escape(translator.t("atlas.filters.all"))}</option>'
            f'{choices}</select></label>'
        )
    return (
        f'<form class="atlas-filters" action="/" method="get" '
        f'aria-label="{escape(translator.t("atlas.filters.aria"), quote=True)}">'
        '<input type="hidden" name="view" value="atlas">'
        f"{hidden}{''.join(controls)}"
        f'<button type="submit">{escape(translator.t("atlas.filters.apply"))}</button>'
        f'<a class="atlas-clear" href="{escape(clear_href, quote=True)}">'
        f'{escape(translator.t("atlas.filters.clear"))}</a></form>'
    )


def render_atlas(
    view_or_model: AtlasViewModel | ManagerReadModel,
    *,
    query_context: QueryContext = None,
    translator: Translator | None = None,
    reader_projection: ReaderProjection | None = None,
    include_reader_surface: bool = True,
) -> str:
    """Render an Atlas page fragment; the shared shell owns the document chrome."""

    selected_translator = translator or Translator()
    view = (
        view_or_model
        if isinstance(view_or_model, AtlasViewModel)
        else AtlasViewModel.from_read_model(
            view_or_model, filters=AtlasFilters.from_query(query_context)
        )
    )
    model = view.read_model
    fixture = _is_fixture(model)
    projection = reader_projection or project_read_model(model)
    context = _context_with_filters(view, query_context)
    source_ids = [source.source_id for source in model.source_refs]
    source_text = (
        f'<span translate="no">{selected_translator.source_text(selected_translator.join(source_ids))}</span>'
        if source_ids
        else escape(selected_translator.t("atlas.none_recorded"))
    )
    observed = (
        f'<span translate="no">{selected_translator.source_text(model.as_of)}</span>'
        if model.as_of
        else escape(selected_translator.t("atlas.unavailable"))
    )
    snapshot = (
        f'<span translate="no">{selected_translator.source_text(model.snapshot_token)}</span>'
        if model.snapshot_token
        else escape(selected_translator.t("atlas.unavailable"))
    )
    intro = selected_translator.html(
        "atlas.intro",
        start=selected_translator.t("label.atlas.lifecycle.campaign"),
        end=selected_translator.t("label.atlas.lifecycle.revalidation"),
    )
    reader_surface = (
        render_reader_surface(
            projection,
            page=ReaderPage.ATLAS,
            query_context=query_context,
            translator=selected_translator,
        )
        if include_reader_surface
        else ""
    )
    expert_sample = _is_complete_atlas_fixture(model)
    expert_model = _atlas_presentation_model(model, sample=fixture)
    expert_payload = _mapping(expert_model.data) or {}
    expert_story = ""
    if "chapters" in expert_payload or any(
        key in expert_payload
        for key in (
            "research_object", "research_topic", "research_question", "research_process",
            "research_result", "research_scope",
        )
    ):
        expert_story = (
            f'<section class="atlas-expert-research-content" '
            f'aria-labelledby="atlas-expert-research-title">'
            f'<h2 id="atlas-expert-research-title">'
            f'{escape(selected_translator.t("reader.atlas.expert_heading"))}</h2>'
            + (
                f'<p class="sample-note">{escape(selected_translator.t("reader.atlas.sample"))}</p>'
                if expert_sample else ""
            )
            + _render_atlas_reading_story(
                expert_model,
                view,
                query_context=query_context,
                translator=selected_translator,
                sample=expert_sample,
            )
            + '</section>'
        )
    pieces = [
        '<div class="atlas-page" data-integration-hook="atlas-view">',
        f'<p class="eyebrow">{escape(selected_translator.t("atlas.eyebrow"))}</p>',
        f'<h1 class="page-title" data-page-title tabindex="-1">'
        f'{escape(selected_translator.t("atlas.title"))}</h1>',
        f'<p class="page-intro">{intro}</p>',
        f'<p class="context-line atlas-context"><span><strong>'
        f'{escape(selected_translator.t("atlas.observed"))}</strong> {observed}</span>'
        f'<span><strong>{escape(selected_translator.t("atlas.snapshot"))}</strong> {snapshot}</span>'
        f'<span><strong>{escape(selected_translator.t("atlas.sources"))}</strong> '
        f'{source_text}</span></p>',
        expert_story,
        reader_surface,
        render_status_block(
            _fixture_status_model(model, selected_translator) if fixture else model,
            translator=selected_translator,
        ),
    ]
    state = display_state_for(model)
    if state is DisplayState.EMPTY:
        pieces.append(render_operational_state(DisplayState.EMPTY, translator=selected_translator))
    pieces.append(_render_filters(view, query_context=context, translator=selected_translator))
    if view.records:
        pieces.append(
            _render_lifecycle(
                view, query_context=context, translator=selected_translator, fixture=fixture
            )
        )
    if view.status_groups:
        rows = "".join(
            f'<li><span>{translator_label}</span><strong>{group.count}</strong></li>'
            for group in view.status_groups
            if (translator_label := selected_translator.label("atlas.state", group.state))
        )
        pieces.append(
            f'<section class="atlas-section" id="status-groups">'
            f'<h2>{escape(selected_translator.t("atlas.section.status_groups"))}</h2>'
            f'<ul class="atlas-count-list">{rows}</ul></section>'
        )
    pieces.append(
        _render_special_records(
            "atlas.section.recently_changed",
            view.recently_changed,
            query_context=context,
            section_id="recently-changed",
            translator=selected_translator,
            fixture=fixture,
        )
    )
    pieces.append(
        _render_special_records(
            "atlas.section.blocked_or_unavailable",
            view.blocked_or_unavailable,
            query_context=context,
            section_id="blocked-unavailable",
            translator=selected_translator,
            fixture=fixture,
        )
    )
    pieces.append(
        _render_special_records(
            "atlas.section.unresolved_conclusions",
            view.unresolved_conclusions,
            query_context=context,
            section_id="unresolved-conclusions",
            translator=selected_translator,
            fixture=fixture,
        )
    )
    if view.research_gaps:
        gap_markup: list[str] = []
        for gap in view.research_gaps:
            detail = (
                _fixture_text(gap.detail, translator=selected_translator, fixture=fixture)
                if gap.detail
                else ""
            )
            gap_markup.append(
                f'<li data-gap-id="{escape(gap.gap_id, quote=True)}">'
                f'<strong>{_fixture_text(gap.title, translator=selected_translator, fixture=fixture)}</strong>'
                f"{detail}</li>"
            )
        gaps = "".join(gap_markup)
        pieces.append(
            f'<section class="atlas-section" id="research-gaps">'
            f'<h2>{escape(selected_translator.t("atlas.section.research_gaps"))}</h2>'
            f'<ul class="atlas-gap-list">{gaps}</ul></section>'
        )
    pieces.append(
        _render_special_records(
            "atlas.section.frontier",
            view.frontier,
            query_context=context,
            section_id="frontier",
            translator=selected_translator,
            fixture=fixture,
        )
    )
    pieces.append("</div>")
    return "".join(pieces)


def _atlas_reading_owner_text(
    value: str | None, *, translator: Translator, sample: bool
) -> str:
    if value is None:
        return ""
    return _fixture_text(value, translator=translator, fixture=sample)


def _atlas_reading_payload_values(
    payload: Mapping[str, object], *keys: str
) -> tuple[str, ...]:
    values: list[str] = []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, Mapping):
            text = _first_text(value, "summary", "description", "text", "detail", "value", "title", "name")
            if text is not None:
                values.append(text)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for item in value:
                if isinstance(item, Mapping):
                    text = _first_text(
                        item, "summary", "description", "text", "detail", "value", "title", "name"
                    )
                else:
                    text = _text(item)
                if text is not None:
                    values.append(text)
        elif (text := _text(value)) is not None:
            values.append(text)
    return tuple(dict.fromkeys(values))


def _atlas_reading_entries(story: ResearchStoryViewModel, *keys: str) -> tuple[StoryEntry, ...]:
    selected = set(keys)
    return tuple(entry for chapter in story.chapters if chapter.key in selected for entry in chapter.entries)


def _atlas_reading_gap_values(view: AtlasViewModel) -> tuple[str, ...]:
    values: list[str] = []
    for gap in view.research_gaps:
        values.append(gap.title)
        if gap.detail is not None and gap.detail != gap.title:
            values.append(gap.detail)
    return tuple(values)


def _render_atlas_reading_entry(
    entry: StoryEntry,
    *,
    query_context: QueryContext,
    translator: Translator,
    sample: bool,
) -> str:
    content: list[str] = []
    if entry.title is not None:
        content.append(
            f'<h4>{_atlas_reading_owner_text(entry.title, translator=translator, sample=sample)}</h4>'
        )
    if entry.summary is not None and entry.summary != entry.title:
        content.append(
            f'<p>{_atlas_reading_owner_text(entry.summary, translator=translator, sample=sample)}</p>'
        )
    links: list[str] = []
    for link in entry.links:
        if link.source_id:
            support = source_support_entry(
                link.source_id,
                record=entry.raw,
                record_id=entry.record_id,
                fabricated_example=sample,
                display_name=entry.title,
            )
            if support:
                links.append(support)
            evidence_href = context_link(query_context, view="evidence", source_id=link.source_id)
            links.append(
                f'<a class="atlas-reading-evidence-link" href="{escape(evidence_href, quote=True)}">'
                f'{escape(translator.t("reader.evidence_entry"))}</a>'
            )
        elif link.target:
            target = public_locator(link.target)
            label = link.label or translator.t("reader.source")
            if target is not None:
                links.append(
                    f'<a class="atlas-reading-source-link" href="{escape(target, quote=True)}">'
                    f'{escape(label)}</a>'
                )
            else:
                links.append(
                    f'<span class="atlas-reading-source-unavailable">{escape(label)}</span>'
                )
    if links:
        content.append(f'<p class="atlas-reading-entry-links">{" · ".join(links)}</p>')
    return f'<article class="atlas-reading-entry">{"".join(content)}</article>'


def _render_atlas_reading_section(
    section_id: str,
    heading_key: str,
    *,
    entries: Sequence[StoryEntry] = (),
    values: Sequence[str] = (),
    query_context: QueryContext,
    translator: Translator,
    sample: bool,
    unavailable_key: str = "reader.atlas.content_unavailable",
) -> str:
    body: list[str] = []
    for value in values:
        body.append(
            f'<p>{_atlas_reading_owner_text(value, translator=translator, sample=sample)}</p>'
        )
    body.extend(
        _render_atlas_reading_entry(
            entry, query_context=query_context, translator=translator, sample=sample
        )
        for entry in entries
    )
    if not body:
        body.append(
            f'<p class="atlas-reading-unavailable" data-reader-availability="missing">'
            f'{escape(translator.t(unavailable_key))}</p>'
        )
    return (
        f'<section class="atlas-reading-section" id="{section_id}" '
        f'aria-labelledby="{section_id}-title">'
        f'<h3 id="{section_id}-title">{escape(translator.t(heading_key))}</h3>'
        f'{"".join(body)}</section>'
    )


def _render_atlas_story_links(
    view: AtlasViewModel,
    *,
    model: ManagerReadModel,
    query_context: QueryContext,
    translator: Translator,
    fixture: bool,
) -> str:
    links: list[str] = []
    requested = query_values(query_context)
    selected_snapshot = requested.get("snapshot_token") or requested.get("snapshot")
    for record in view.records:
        if record.record_type not in {"campaign", "study", "strategy_family"}:
            continue
        target = _story_link(record, query_context)
        if model.snapshot_token is not None and not selected_snapshot:
            target = context_link(target, view="stories", snapshot_token=model.snapshot_token)
        name = _fixture_text(record.title, translator=translator, fixture=fixture)
        label = escape(translator.t("pipeline.open_story", name=record.title))
        label = label.replace(escape(record.title), name, 1)
        links.append(
            f'<article data-research-object="{escape(record.record_id, quote=True)}">'
            f'<h3>{name}</h3><a class="atlas-story-link" '
            f'data-record-story="{escape(record.record_id, quote=True)}" '
            f'href="{escape(target, quote=True)}">{label}</a></article>'
        )
    if not links:
        return ""
    return (
        f'<section class="atlas-reading-links" aria-labelledby="atlas-reading-links-title">'
        f'<h2 id="atlas-reading-links-title">{escape(translator.t("reader.atlas.related_stories"))}</h2>'
        f'{"".join(links)}</section>'
    )


def _render_atlas_reading_story(
    model: ManagerReadModel,
    view: AtlasViewModel,
    *,
    query_context: QueryContext,
    translator: Translator,
    sample: bool,
) -> str:
    payload = _mapping(model.data) or {}
    story = ResearchStoryViewModel.from_read_model(model)
    filtered = bool(view.filters.as_query())
    selected_ids = {record.record_id for record in view.records}

    def allowed(entry: StoryEntry) -> bool:
        return not filtered or entry.record_id in selected_ids

    root_values = (
        story.root.strategy_family_label,
        story.root.study_label,
        story.root.campaign_label,
    )
    topic_values = () if filtered else tuple(value for value in root_values if value)
    if not topic_values and not filtered:
        topic_values = _atlas_reading_payload_values(
            payload, "research_object", "research_topic", "topic"
        )
    question_entries = tuple(
        entry for entry in _atlas_reading_entries(story, "intent", "initial_hypothesis")
        if allowed(entry)
    )
    question_values = () if filtered else _atlas_reading_payload_values(
        payload, "research_question", "question"
    )
    process_entries = tuple(
        entry for entry in _atlas_reading_entries(story, "research_design", "attempts")
        if allowed(entry)
    )
    process_values = () if filtered else _atlas_reading_payload_values(
        payload, "research_process", "process", "method"
    )
    result_entries = tuple(
        entry for entry in _atlas_reading_entries(story, "conclusions") if allowed(entry)
    )
    result_values = () if filtered else _atlas_reading_payload_values(
        payload, "research_result", "result", "conclusion"
    )
    scope_values = () if filtered else _atlas_reading_payload_values(
        payload, "research_scope", "scope", "coverage", "time_range"
    )
    unknown_entries = tuple(
        entry for entry in _atlas_reading_entries(story, "failures") if allowed(entry)
    )
    unknown_values = _atlas_reading_gap_values(view) + (
        () if filtered else _atlas_reading_payload_values(payload, "unknowns", "limitations")
    )
    evidence_entries = tuple(
        entry for entry in _atlas_reading_entries(story, "evidence") if allowed(entry)
    )
    return (
        '<section class="atlas-reading-story" data-reader-main-story '
        'aria-labelledby="atlas-reading-story-title">'
        f'<h2 id="atlas-reading-story-title">{escape(translator.t("reader.atlas.object_heading"))}</h2>'
        f'{_render_atlas_reading_section("atlas-reading-object", "reader.atlas.object", values=topic_values, query_context=query_context, translator=translator, sample=sample)}'
        f'{_render_atlas_reading_section("atlas-reading-question", "reader.atlas.question_heading", entries=question_entries, values=question_values, query_context=query_context, translator=translator, sample=sample)}'
        f'{_render_atlas_reading_section("atlas-reading-process", "reader.atlas.process_heading", entries=process_entries, values=process_values, query_context=query_context, translator=translator, sample=sample)}'
        f'{_render_atlas_reading_section("atlas-reading-result", "reader.atlas.result_heading", entries=result_entries, values=result_values, query_context=query_context, translator=translator, sample=sample)}'
        f'{_render_atlas_reading_section("atlas-reading-scope", "reader.atlas.scope_heading", values=scope_values, query_context=query_context, translator=translator, sample=sample, unavailable_key="reader.atlas.scope_unknown")}'
        f'{_render_atlas_reading_section("atlas-reading-unknowns", "reader.atlas.unknowns_heading", entries=unknown_entries, values=unknown_values, query_context=query_context, translator=translator, sample=sample)}'
        f'{_render_atlas_reading_section("atlas-reading-evidence", "reader.atlas.evidence_heading", entries=evidence_entries, query_context=query_context, translator=translator, sample=sample, unavailable_key="reader.atlas.evidence_unavailable")}'
        '</section>'
    )


def render_atlas_reading(
    model: ManagerReadModel, *, query_context: QueryContext, translator: Translator, sample: bool
) -> str:
    """Render a plain-language projection of explicit Atlas research content."""
    view = AtlasViewModel.from_read_model(model, filters=AtlasFilters.from_query(query_context))
    records = view.records
    count = len({(record.record_type, record.record_id) for record in records})
    payload = _mapping(model.data) or {}
    pagination = _mapping(payload.get("pagination")) or {}
    complete = model.availability.complete and not model.errors and not (
        pagination.get("has_more") is True or pagination.get("next_cursor")
    )
    filters = json.dumps({
        "applied": dict(view.filters.as_query()),
        "retained_query": _query_pairs(query_context),
    }, ensure_ascii=False)
    computation = source_support_computation(
        tuple(record.payload for record in records), filters=filters, complete=bool(complete)
    )
    presentation_model = _atlas_presentation_model(model, sample=sample)
    sample_markup = (
        f'<p class="sample-note">{escape(translator.t("reader.atlas.sample"))}</p>' if sample else ""
    )
    pointers = "".join(
        f'<p>{source_support_entry(ref.source_id) or ""}</p>' for ref in model.source_refs
    )
    metadata = (
        f'<div class="atlas-reading-metadata" hidden aria-hidden="true" aria-label="{escape(translator.t("reader.atlas.metadata"), quote=True)}">'
        f'{_render_filters(view, query_context=query_context, translator=translator)}'
        f'<p>{escape(translator.t("support.count", n=count))}</p>'
        f'<p>{escape(translator.t("support.count_unit"))}</p>'
        f'<p>{escape(translator.t("support.count_complete" if complete else "support.count_partial"))}</p>'
        f'<p>{computation}</p>{pointers}</div>'
    )
    return (
        '<section class="plain-result atlas-reading" data-integration-hook="atlas-view">'
        f'<h1 data-page-title tabindex="-1">{escape(translator.t("pipeline.atlas_title"))}</h1>'
        f'{sample_markup}{_render_atlas_reading_story(presentation_model, view, query_context=query_context, translator=translator, sample=sample)}'
        f'{_render_atlas_story_links(view, model=model, query_context=query_context, translator=translator, fixture=sample)}'
        f'{metadata}</section>'
    )


def atlas_view(
    provider: ManagerDataProvider,
    *,
    filters: AtlasFilters | None = None,
    query_context: QueryContext = None,
    snapshot_token: str | None = None,
) -> AtlasViewModel:
    """Read Atlas through the public provider seam and build its view model."""

    selected_filters = filters or AtlasFilters.from_query(query_context)
    return AtlasViewModel.from_read_model(
        provider.read("atlas", snapshot_token=snapshot_token), filters=selected_filters
    )


def render_atlas_view(
    provider: ManagerDataProvider,
    *,
    filters: AtlasFilters | None = None,
    query_context: QueryContext = None,
    snapshot_token: str | None = None,
    translator: Translator | None = None,
    reader_projection: ReaderProjection | None = None,
    include_reader_surface: bool = True,
) -> str:
    """T5 integration hook: read and render the Atlas view without shell logic."""

    return render_atlas(
        atlas_view(
            provider,
            filters=filters,
            query_context=query_context,
            snapshot_token=snapshot_token,
        ),
        query_context=query_context,
        translator=translator,
        reader_projection=reader_projection,
        include_reader_surface=include_reader_surface,
    )


ATLAS_INTEGRATION_HOOK = "manager_gui.web.atlas.render_atlas_view"


__all__ = [
    "ATLAS_INTEGRATION_HOOK",
    "LIFECYCLE_LABELS",
    "LIFECYCLE_SPINE",
    "AtlasFilter",
    "AtlasFilters",
    "AtlasRecord",
    "AtlasResearchGap",
    "AtlasStatusGroup",
    "AtlasViewModel",
    "atlas_link",
    "atlas_view",
    "build_atlas_link",
    "render_atlas",
    "render_atlas_view",
]
