"""Atlas overview and research-object navigation for the Manager GUI.

The module is deliberately page-local.  It consumes the public
``ManagerReadModel`` envelope, normalizes only explicit record fields, and
returns deterministic HTML suitable for the shared T2 shell to embed.  It does
not read private storage or infer conclusions from counts.
"""

# HTML fragments intentionally use long readable lines.
# ruff: noqa: E501

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from html import escape
from typing import TypeAlias, cast
from urllib.parse import parse_qsl, urlencode, urlsplit

from ..models import ManagerReadModel, ReadModelStatus
from ..provider import ManagerDataProvider
from .i18n import Translator
from .i18n.catalog import l3_atlas_story as _l3_atlas_story_catalog  # noqa: F401
from .navigation import clear_filters_link
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
    "campaign": "Campaign",
    "hypothesis": "Hypothesis",
    "candidate": "Candidate",
    "run": "Run",
    "evidence": "Evidence",
    "qualification": "Qualification",
    "replication": "Replication",
    "revalidation": "Revalidation",
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
    unique: dict[str, list[str]] = {}
    for key, value in pairs:
        if key not in unique:
            unique[key] = []
        if value not in unique[key]:
            unique[key].append(value)
    ordered_keys = sorted(unique, key=lambda key: (order.get(key, len(order)), key))
    flattened = [(key, value) for key in ordered_keys for value in unique[key]]
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
        return LIFECYCLE_LABELS.get(self.record_type, self.record_type.replace("_", " ").title())

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
        gaps = _extract_gaps(model.data, records)
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


def _explicit_gaps(item: Mapping[str, object]) -> tuple[str, ...]:
    raw = item.get("research_gaps", item.get("gaps", ()))
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        return ()
    gaps: list[str] = []
    for value in raw:
        if isinstance(value, Mapping):
            text = _first_text(cast(Mapping[str, object], value), "title", "detail", "id")
        else:
            text = _text(value)
        if text is not None:
            gaps.append(text)
    return tuple(gaps)


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


def _extract_gaps(data: object, records: Sequence[AtlasRecord]) -> tuple[AtlasResearchGap, ...]:
    mapping = _mapping(data)
    raw = () if mapping is None else mapping.get("research_gaps", ())
    result: list[AtlasResearchGap] = []
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        for index, value in enumerate(raw, start=1):
            if isinstance(value, Mapping):
                item = cast(Mapping[str, object], value)
                gap_id = _first_text(item, "id", "gap_id") or f"gap-{index}"
                title = _first_text(item, "title", "name", "detail") or gap_id
                detail = _first_text(item, "detail", "description")
                result.append(
                    AtlasResearchGap(
                        gap_id=gap_id,
                        title=title,
                        detail=detail,
                        source=_source(item.get("source", item.get("source_ref"))),
                        record_id=_first_text(item, "record_id", "related_record_id"),
                    )
                )
            elif (text := _text(value)) is not None:
                result.append(AtlasResearchGap(gap_id=f"gap-{index}", title=text))
    for record in records:
        for index, gap in enumerate(record.research_gaps, start=1):
            result.append(
                AtlasResearchGap(
                    gap_id=f"{record.record_id}-gap-{index}",
                    title=gap,
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
        if key not in {"view", "record_id", "mode"}
    ]
    pairs.append(("view", "stories"))
    pairs.append(("record_id", record.record_id))
    if record.record_type in {"campaign", "study", "strategy_family"}:
        pairs.append((record.record_type, record.record_id))
    query = _stable_query(pairs)
    return "/?" + query if query else "/?view=stories"


def _render_record(record: AtlasRecord, *, query_context: QueryContext) -> str:
    state = (
        f'<span class="atlas-record-state">{escape(record.state)}</span>' if record.state else ""
    )
    changed = (
        f'<time datetime="{escape(record.changed_at, quote=True)}">{escape(record.changed_at)}</time>'
        if record.changed_at
        else ""
    )
    source = (
        f'<span class="atlas-record-source">{escape(record.source)}</span>' if record.source else ""
    )
    metadata = " · ".join(part for part in (state, changed, source) if part)
    meta_markup = f'<span class="atlas-record-meta">{metadata}</span>' if metadata else ""
    return (
        f'<li class="atlas-record" data-record-id="{escape(record.record_id, quote=True)}" '
        f'data-record-type="{escape(record.record_type, quote=True)}">'
        f'<a href="{escape(_record_link(record, query_context), quote=True)}">{escape(record.title)}</a>'
        f'<a class="atlas-story-link" data-record-story="{escape(record.record_id, quote=True)}" '
        f'href="{escape(_story_link(record, query_context), quote=True)}">Open Research Story</a>'
        f"{meta_markup}</li>"
    )


def _render_record_list(records: Sequence[AtlasRecord], *, query_context: QueryContext) -> str:
    return (
        '<ul class="atlas-record-list">'
        + "".join(_render_record(record, query_context=query_context) for record in records)
        + "</ul>"
    )


def _render_lifecycle(view: AtlasViewModel, *, query_context: QueryContext) -> str:
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
        count = len(records)
        body = (
            _render_record_list(records, query_context=query_context)
            if records
            else '<p class="atlas-muted">No records in this scope.</p>'
        )
        sections.append(
            f'<article class="atlas-spine-step" data-record-type="{record_type}">'
            f'<div class="atlas-step-heading"><span class="atlas-step-index">{index}</span>'
            f'<h3>{LIFECYCLE_LABELS[record_type]}</h3><span class="atlas-count">{count} records</span></div>{body}</article>'
        )
    if extras:
        sections.append(
            '<article class="atlas-spine-step atlas-extra-records"><div class="atlas-step-heading">'
            '<h3>Other record types</h3><span class="atlas-count">'
            f"{len(extras)} records</span></div>{_render_record_list(extras, query_context=query_context)}</article>"
        )
    return (
        '<section class="atlas-spine" aria-labelledby="atlas-spine-title"><h2 id="atlas-spine-title">Research lifecycle</h2>'
        + "".join(sections)
        + "</section>"
    )


def _render_special_records(
    title: str, records: Sequence[AtlasRecord], *, query_context: QueryContext, section_id: str
) -> str:
    if not records:
        return ""
    return f'<section class="atlas-section" id="{section_id}" aria-labelledby="{section_id}-title"><h2 id="{section_id}-title">{escape(title)}</h2>{_render_record_list(records, query_context=query_context)}</section>'


def _render_filters(view: AtlasViewModel, *, query_context: QueryContext) -> str:
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
                f'<label>Date <input name="date" value="{escape(values[key], quote=True)}" placeholder="YYYY-MM-DD"></label>'
            )
            continue
        choices = "".join(
            f'<option value="{escape(choice, quote=True)}"{(" selected" if values[key] == choice else "")}>{escape(choice)}</option>'
            for choice in options[key]
        )
        label = key.replace("_", " ").title()
        controls.append(
            f'<label>{escape(label)} <select name="{key}"><option value="">All</option>{choices}</select></label>'
        )
    return (
        '<form class="atlas-filters" action="/" method="get" aria-label="Atlas filters">'
        '<input type="hidden" name="view" value="atlas">'
        f"{hidden}{''.join(controls)}"
        '<button type="submit">Apply filters</button>'
        f'<a class="atlas-clear" href="{escape(clear_href, quote=True)}">Clear</a></form>'
    )


def render_atlas(
    view_or_model: AtlasViewModel | ManagerReadModel,
    *,
    query_context: QueryContext = None,
    translator: Translator | None = None,
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
    context = _context_with_filters(view, query_context)
    source_text = ", ".join(source.source_id for source in model.source_refs) or "None recorded"
    observed = model.as_of or "Unavailable"
    snapshot = model.snapshot_token or "Unavailable"
    pieces = [
        '<div class="atlas-page" data-integration-hook="atlas-view">',
        '<p class="eyebrow">Atlas overview · read-only</p>',
        '<h1 class="page-title" data-page-title tabindex="-1">Atlas</h1>',
        '<p class="page-intro">Navigate the research lifecycle from Campaign through Revalidation. '
        "Counts describe recorded objects only; they do not establish success, ranking, or advice.</p>",
        f'<p class="context-line atlas-context"><span><strong>Observed</strong> {escape(observed)}</span>'
        f"<span><strong>Snapshot</strong> {escape(snapshot)}</span><span><strong>Sources</strong> {escape(source_text)}</span></p>",
        render_status_block(model, translator=selected_translator),
    ]
    state = display_state_for(model)
    if state is DisplayState.EMPTY:
        pieces.append(
            render_operational_state(
                DisplayState.EMPTY,
                translator=selected_translator,
                detail="No records are present in this Atlas scope.",
            )
        )
    pieces.append(_render_filters(view, query_context=context))
    if view.records:
        pieces.append(_render_lifecycle(view, query_context=context))
    if view.status_groups:
        rows = "".join(
            f"<li><span>{escape(group.state)}</span><strong>{group.count}</strong></li>"
            for group in view.status_groups
        )
        pieces.append(
            f'<section class="atlas-section" id="status-groups"><h2>Status groups</h2><ul class="atlas-count-list">{rows}</ul></section>'
        )
    pieces.append(
        _render_special_records(
            "Recently changed",
            view.recently_changed,
            query_context=context,
            section_id="recently-changed",
        )
    )
    pieces.append(
        _render_special_records(
            "Blocked or unavailable",
            view.blocked_or_unavailable,
            query_context=context,
            section_id="blocked-unavailable",
        )
    )
    pieces.append(
        _render_special_records(
            "Unresolved conclusions",
            view.unresolved_conclusions,
            query_context=context,
            section_id="unresolved-conclusions",
        )
    )
    if view.research_gaps:
        gaps = "".join(
            f'<li data-gap-id="{escape(gap.gap_id, quote=True)}"><strong>{escape(gap.title)}</strong>'
            f"{f'<span>{escape(gap.detail)}</span>' if gap.detail else ''}</li>"
            for gap in view.research_gaps
        )
        pieces.append(
            f'<section class="atlas-section" id="research-gaps"><h2>Research gaps</h2><ul class="atlas-gap-list">{gaps}</ul></section>'
        )
    pieces.append(
        _render_special_records(
            "Navigable frontier", view.frontier, query_context=context, section_id="frontier"
        )
    )
    pieces.append("</div>")
    return "".join(pieces)


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
