"""S3-T2 failure experiences and explicit Derived failure patterns.

This is a page-local read-only projection. Formal Research Memory is admitted
only through the explicit Memory containers parsed by ``web.memory``; ordinary
failure records are kept in a separate layer; and a named pattern container is
shown as Derived rather than promoted to Memory. No LLM, text-similarity
promotion, private storage, SQLite, filesystem scan, or mutation is used.

S3-T3 integration hooks:

* :func:`render_failure_patterns_view` reads ``failure_patterns``;
* :func:`render_memory_failure_view` reads the S3-T1 ``memory`` resource when a
  combined Memory/failure payload is preferred.
"""

# HTML fragments intentionally keep readable markup even when a line is long.
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from html import escape
from typing import TypeAlias, cast
from urllib.parse import parse_qsl, urlencode, urlsplit

from ..models import ManagerReadModel, ReadModelStatus, SourceReference
from ..provider import ManagerDataProvider
from .failure_lineage import (
    LINEAGE_KINDS,
    FailureLineage,
    FailureReference,
    failure_lineage,
    references,
    render_failure_lineage,
    render_references,
)
from .i18n import Translator
from .memory import (
    MemoryEntry,
    MemoryViewModel,
    memory_link,
    render_memory_text,
    render_memory_value,
)
from .navigation import clear_filters_link
from .status import DisplayState, render_operational_state, render_status_block

QueryContext: TypeAlias = str | Mapping[str, object] | None
ProviderOrModel: TypeAlias = ManagerDataProvider | ManagerReadModel

FAILURE_PATTERNS_RESOURCE = "failure_patterns"
MEMORY_FAILURE_RESOURCE = "memory"
FAILURE_PATTERN_HOOK = "failure-patterns-view"
FAILURE_PATTERNS_INTEGRATION_HOOK = "manager_gui.web.failure_patterns.render_failure_patterns_view"
MEMORY_FAILURE_INTEGRATION_HOOK = "manager_gui.web.failure_patterns.render_memory_failure_view"

_FAILURE_KEYS = (
    "failures",
    "failure_experiences",
    "failure_records",
    "failure_events",
    "ordinary_failures",
)
_PATTERN_KEYS = (
    "derived_patterns",
    "failure_patterns",
    "failure_pattern_records",
    "pattern_aggregates",
)
_FAILURE_TYPES = frozenset(
    {
        "failure",
        "failure-record",
        "failure-experience",
        "failure-event",
        "research-failure",
        "failed-run",
    }
)
_PATTERN_TYPES = frozenset(
    {
        "failure-pattern",
        "failure-pattern-v1",
        "derived-failure-pattern",
        "derived-pattern",
        "pattern-aggregate",
    }
)
_FILTER_KEYS = ("failure_category", "stage", "outcome", "campaign")
_QUERY_ORDER = (
    "view",
    "fixture",
    "q",
    *_FILTER_KEYS,
    "failure_id",
    "pattern_id",
    "panel",
)


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


def _mapping(value: object) -> Mapping[str, object] | None:
    return cast(Mapping[str, object], value) if isinstance(value, Mapping) else None


def _sequence(value: object) -> tuple[object, ...]:
    if value is None or isinstance(value, (str, bytes, bytearray)):
        return ()
    if isinstance(value, Mapping):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(value)
    return ()


def _first(item: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        if (value := _text(item.get(key))) is not None:
            return value
    return None


def _norm(value: object) -> str:
    return (_text(value) or "").strip().lower().replace("_", "-").replace(" ", "-")


def _field(item: Mapping[str, object], *keys: str) -> object | None:
    for key in keys:
        if key in item and item[key] is not None:
            return item[key]
    return None


def _record_type(item: Mapping[str, object]) -> str:
    return _norm(_first(item, "record_type", "object_type", "type", "kind"))


def _record_id(item: Mapping[str, object], *, pattern: bool = False) -> str | None:
    if pattern:
        return _first(item, "pattern_id", "record_id", "id", "uid", "key")
    return _first(item, "failure_id", "entry_id", "memory_id", "record_id", "id", "uid", "key")


def _ref_id(value: object) -> str | None:
    item = _mapping(value)
    if item is not None:
        return _first(item, "record_id", "id", "source_id", "source_ref", "document_id")
    return _text(value)


def _compact(value: object) -> str | None:
    if isinstance(value, Mapping):
        parts = [f"{key}={_compact(raw) or str(raw)}" for key, raw in value.items()]
        return ", ".join(parts) if parts else None
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        parts = [_compact(raw) or str(raw) for raw in value]
        return ", ".join(parts) if parts else None
    return _text(value)


def _is_failure(item: Mapping[str, object]) -> bool:
    kind = _record_type(item)
    if kind in _FAILURE_TYPES or "failure" in kind or kind.startswith("apex-research.failure"):
        return True
    if any(key in item for key in ("failure_category", "failure_class", "failure_reason", "failure_outcome")):
        return True
    return _norm(_first(item, "outcome", "outcome_state", "result")) in {
        "failed",
        "failure",
        "rejected",
        "blocked",
        "error",
        "partial",
        "execution-error",
    }


def _explicit_memory_type(item: Mapping[str, object]) -> bool:
    return _norm(_first(item, "record_type", "object_type")) in {
        "apex-research.memory-entry-v1",
        "apex-research.memory-family-v1",
        "apex-research.memory-policy-v1",
        "apex-research.family-memory-v1",
    }


def _failure_items(root: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    values: list[Mapping[str, object]] = []
    for key in _FAILURE_KEYS:
        values.extend(item for raw in _sequence(root.get(key)) if (item := _mapping(raw)) is not None)
    for raw in _sequence(root.get("records")):
        item = _mapping(raw)
        if item is None or _explicit_memory_type(item) or not _is_failure(item):
            continue
        payload = _mapping(item.get("payload"))
        values.append(payload if payload is not None and _is_failure(payload) else item)
    direct = _mapping(root.get("failure"))
    if direct is not None:
        values.append(direct)
    result: list[Mapping[str, object]] = []
    seen: set[str] = set()
    for index, item in enumerate(values):
        identifier = _record_id(item) or f"failure-{index}"
        if identifier not in seen:
            seen.add(identifier)
            result.append(item)
    return tuple(result)


def _pattern_items(root: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    values: list[Mapping[str, object]] = []
    for key in _PATTERN_KEYS:
        values.extend(item for raw in _sequence(root.get(key)) if (item := _mapping(raw)) is not None)
    for raw in _sequence(root.get("patterns")):
        item = _mapping(raw)
        if item is not None and (
            _record_type(item) in _PATTERN_TYPES
            or any(key in item for key in ("pattern_id", "sample_count", "aggregation_rule"))
        ):
            values.append(item)
    for raw in _sequence(root.get("records")):
        item = _mapping(raw)
        if item is None:
            continue
        kind = _record_type(item)
        if kind not in _PATTERN_TYPES and "failure-pattern" not in kind:
            continue
        payload = _mapping(item.get("payload"))
        values.append(payload if payload is not None else item)
    result: list[Mapping[str, object]] = []
    seen: set[str] = set()
    for index, item in enumerate(values):
        identifier = _record_id(item, pattern=True) or f"pattern-{index}"
        if identifier not in seen:
            seen.add(identifier)
            result.append(item)
    return tuple(result)


def _association(trace: FailureLineage, kind: str) -> FailureReference:
    for link in trace.associations:
        if link.kind == kind:
            return link
    return FailureReference(kind=kind, record_id=None, label="Missing", state="missing")


def _memory_item(entry: MemoryEntry) -> Mapping[str, object]:
    item = dict(entry.raw)
    item.setdefault("memory_id", entry.memory_id)
    item.setdefault("title", entry.title)
    item.setdefault("summary", entry.safe_summary)
    item.setdefault("failure_category", entry.failure_category)
    item.setdefault("stage", entry.stage)
    item.setdefault("outcome", entry.outcome)
    item.setdefault("campaign_id", entry.campaign_id)
    if "references" not in item:
        item["references"] = [link.to_dict() for link in entry.references]
    if "conflicts" not in item:
        item["conflicts"] = [link.to_dict() for link in entry.conflicts]
    if "supersedes" not in item:
        item["supersedes"] = [link.to_dict() for link in entry.supersedes]
    if "lineage" not in item:
        item["lineage"] = [link.to_dict() for link in entry.lineage]
    return cast(Mapping[str, object], item)


@dataclass(frozen=True, slots=True)
class FailureExperience:
    """A first-class failure record, formal-memory or ordinary-source owned."""

    failure_id: str
    title: str
    summary: str | None
    failure_category: str | None
    stage: str | None
    outcome: str | None
    memory_id: str | None
    origin: str
    status: str | None
    lineage: FailureLineage
    raw: Mapping[str, object] = field(repr=False, compare=False, default_factory=dict)

    @property
    def category(self) -> str | None:
        return self.failure_category

    @property
    def campaign(self) -> FailureReference:
        return _association(self.lineage, "campaign")

    @property
    def candidate(self) -> FailureReference:
        return _association(self.lineage, "candidate")

    @property
    def run(self) -> FailureReference:
        return _association(self.lineage, "run")

    @property
    def evidence(self) -> FailureReference:
        return _association(self.lineage, "evidence")

    @property
    def artifact(self) -> FailureReference:
        return _association(self.lineage, "artifact")

    @property
    def source_document(self) -> FailureReference:
        return _association(self.lineage, "source_document")

    @property
    def references(self) -> tuple[FailureReference, ...]:
        return self.lineage.sources

    @property
    def source_refs(self) -> tuple[FailureReference, ...]:
        return self.references

    @property
    def conflicts(self) -> tuple[FailureReference, ...]:
        return self.lineage.conflicts

    @property
    def supersedes(self) -> tuple[FailureReference, ...]:
        return self.lineage.supersedes

    def to_dict(self) -> dict[str, object]:
        return {
            "failure_id": self.failure_id,
            "title": self.title,
            "summary": self.summary,
            "failure_category": self.failure_category,
            "stage": self.stage,
            "outcome": self.outcome,
            "memory_id": self.memory_id,
            "origin": self.origin,
            "status": self.status,
            "campaign": self.campaign.to_dict(),
            "candidate": self.candidate.to_dict(),
            "run": self.run.to_dict(),
            "evidence": self.evidence.to_dict(),
            "artifact": self.artifact.to_dict(),
            "source_document": self.source_document.to_dict(),
            "lineage": self.lineage.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class FailurePattern:
    """An explicit Derived aggregation with its reproducibility fields."""

    pattern_id: str
    title: str
    rule: str | None
    input_scope: tuple[str, ...]
    sample_count: int | None
    failure_ids: tuple[str, ...]
    failure_category: str | None
    stage: str | None
    outcome: str | None
    source_refs: tuple[FailureReference, ...]
    lineage: FailureLineage
    status: ReadModelStatus = ReadModelStatus.DERIVED
    raw: Mapping[str, object] = field(repr=False, compare=False, default_factory=dict)

    @property
    def derived(self) -> bool:
        return self.status is ReadModelStatus.DERIVED

    @property
    def conflicts(self) -> tuple[FailureReference, ...]:
        return self.lineage.conflicts

    @property
    def supersedes(self) -> tuple[FailureReference, ...]:
        return self.lineage.supersedes

    def to_dict(self) -> dict[str, object]:
        return {
            "pattern_id": self.pattern_id,
            "title": self.title,
            "status": self.status.value,
            "rule": self.rule,
            "input_scope": list(self.input_scope),
            "sample_count": self.sample_count,
            "failure_ids": list(self.failure_ids),
            "failure_category": self.failure_category,
            "stage": self.stage,
            "outcome": self.outcome,
            "source_refs": [link.to_dict() for link in self.source_refs],
            "conflicts": [link.to_dict() for link in self.conflicts],
            "supersedes": [link.to_dict() for link in self.supersedes],
            "lineage": self.lineage.to_dict(),
        }


def _make_experience(
    item: Mapping[str, object], sources: Mapping[str, SourceReference], *, origin: str
) -> FailureExperience:
    trace = failure_lineage(item, sources)
    identifier = _record_id(item) or "unidentified-failure"
    return FailureExperience(
        failure_id=identifier,
        title=_first(item, "title", "label", "name", "heading") or identifier,
        summary=_first(item, "summary", "description", "detail", "message", "text"),
        failure_category=_first(item, "failure_category", "failure_class", "category", "failure_type"),
        stage=_first(item, "stage", "research_stage", "phase"),
        outcome=_first(item, "outcome", "outcome_state", "result", "failure_outcome"),
        memory_id=_ref_id(item.get("memory")) or _first(item, "memory_id", "memory_ref"),
        origin=origin,
        status=_first(item, "status", "record_status", "state"),
        lineage=trace,
        raw=item,
    )


def _sample_count(item: Mapping[str, object]) -> int | None:
    aggregation = _mapping(_field(item, "aggregation", "derivation", "pattern_aggregation")) or {}
    value = _field(item, "sample_count", "sample_size", "count", "n_samples")
    if value is None:
        value = _field(aggregation, "sample_count", "sample_size", "count", "n_samples")
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _scope(value: object) -> tuple[str, ...]:
    if isinstance(value, str) and value.strip():
        return (value.strip(),)
    if isinstance(value, Mapping):
        return (compact,) if (compact := _compact(value)) else ()
    return tuple(compact for raw in _sequence(value) if (compact := _compact(raw)) is not None)


def _pattern(
    item: Mapping[str, object], sources: Mapping[str, SourceReference], model: ManagerReadModel
) -> FailurePattern | None:
    identifier = _record_id(item, pattern=True)
    if identifier is None:
        return None
    aggregation = _mapping(_field(item, "aggregation", "derivation", "pattern_aggregation")) or {}
    rule = _first(item, "rule", "aggregation_rule", "derivation_rule", "pattern_rule")
    if rule is None:
        rule = _first(aggregation, "rule", "aggregation_rule", "derivation_rule", "pattern_rule")
    scope_value = _field(item, "input_scope", "inputs", "scope", "source_scope")
    if scope_value is None:
        scope_value = _field(aggregation, "input_scope", "inputs", "scope", "source_scope")
    scope = _scope(scope_value)
    if not scope and model.derivation.kind == "derived":
        scope = tuple(model.derivation.inputs)
    if rule is None and model.derivation.kind == "derived":
        rule = model.derivation.rule
    source_refs = references(
        _field(item, "source_refs", "source_references", "sources", "references", "source"),
        sources,
    )
    failure_ids = tuple(
        identifier
        for raw in _sequence(_field(item, "failure_ids", "sample_ids", "members", "failures"))
        if (identifier := _ref_id(raw)) is not None
    )
    return FailurePattern(
        pattern_id=identifier,
        title=_first(item, "title", "label", "name") or identifier,
        rule=rule,
        input_scope=scope,
        sample_count=_sample_count(item),
        failure_ids=tuple(dict.fromkeys(failure_ids)),
        failure_category=_first(item, "failure_category", "failure_class", "category", "failure_type"),
        stage=_first(item, "stage", "research_stage", "phase"),
        outcome=_first(item, "outcome", "outcome_state", "result"),
        source_refs=source_refs,
        lineage=failure_lineage(item, sources),
        raw=item,
    )


@dataclass(frozen=True, slots=True)
class FailureFilters:
    failure_category: str | None = None
    stage: str | None = None
    outcome: str | None = None
    campaign: str | None = None

    def __post_init__(self) -> None:
        for key in _FILTER_KEYS:
            value = getattr(self, key)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{key} must be a non-empty string or None")

    @classmethod
    def from_query(cls, context: QueryContext) -> FailureFilters:
        values = dict(_query_pairs(context))
        return cls(**{key: _text(values.get(key)) for key in _FILTER_KEYS})

    def as_query(self) -> tuple[tuple[str, str], ...]:
        return tuple((key, value) for key in _FILTER_KEYS if (value := getattr(self, key)) is not None)

    def matches(self, entry: FailureExperience) -> bool:
        values = {
            "failure_category": entry.failure_category,
            "stage": entry.stage,
            "outcome": entry.outcome,
            "campaign": entry.campaign.record_id,
        }
        return all(
            getattr(self, key) is None or getattr(self, key) == values[key] for key in _FILTER_KEYS
        )


@dataclass(frozen=True, slots=True)
class FailureViewModel:
    read_model: ManagerReadModel
    memory_entries: tuple[FailureExperience, ...]
    failures: tuple[FailureExperience, ...]
    patterns: tuple[FailurePattern, ...]
    filters: FailureFilters = field(default_factory=FailureFilters)
    selected_failure_id: str | None = None
    selected_pattern_id: str | None = None
    formal_memory_present: bool = False
    explicit_failure_payload: bool = False
    explicit_pattern_payload: bool = False

    @classmethod
    def from_read_model(
        cls,
        model: ManagerReadModel,
        *,
        filters: FailureFilters | None = None,
        failure_id: str | None = None,
        pattern_id: str | None = None,
    ) -> FailureViewModel:
        root = _mapping(model.data) or {}
        sources = {source.source_id: source for source in model.source_refs}
        memory = MemoryViewModel.from_read_model(model)
        formal = tuple(
            _make_experience(_memory_item(entry), sources, origin="formal_memory")
            for entry in memory.entries
        )
        selected_filters = filters or FailureFilters()
        raw_failures = tuple(_make_experience(item, sources, origin="failure_record") for item in _failure_items(root))
        failures = tuple(entry for entry in raw_failures if selected_filters.matches(entry))
        patterns = tuple(
            pattern
            for item in _pattern_items(root)
            if (pattern := _pattern(item, sources, model)) is not None
        )
        return cls(
            read_model=model,
            memory_entries=formal,
            failures=failures,
            patterns=patterns,
            filters=selected_filters,
            selected_failure_id=_text(failure_id),
            selected_pattern_id=_text(pattern_id),
            formal_memory_present=memory.formal_memory_present,
            explicit_failure_payload=bool(_failure_items(root)),
            explicit_pattern_payload=bool(patterns),
        )

    @classmethod
    def parse(
        cls,
        model: ManagerReadModel,
        *,
        filters: FailureFilters | None = None,
        failure_id: str | None = None,
        pattern_id: str | None = None,
    ) -> FailureViewModel:
        return cls.from_read_model(
            model,
            filters=filters,
            failure_id=failure_id,
            pattern_id=pattern_id,
        )

    @property
    def status(self) -> ReadModelStatus:
        return self.read_model.availability.status

    @property
    def source_refs(self) -> tuple[SourceReference, ...]:
        return self.read_model.source_refs

    @property
    def all_failures(self) -> tuple[FailureExperience, ...]:
        return self.memory_entries + self.failures

    @property
    def selected_failure(self) -> FailureExperience | None:
        return next(
            (entry for entry in self.all_failures if entry.failure_id == self.selected_failure_id),
            None,
        ) if self.selected_failure_id else None

    @property
    def selected_pattern(self) -> FailurePattern | None:
        return next(
            (pattern for pattern in self.patterns if pattern.pattern_id == self.selected_pattern_id),
            None,
        ) if self.selected_pattern_id else None

    @property
    def formal_memory_empty(self) -> bool:
        return not self.memory_entries

    @property
    def empty(self) -> bool:
        return not self.all_failures and not self.patterns

    def to_dict(self) -> dict[str, object]:
        return {
            "formal_memory_present": self.formal_memory_present,
            "formal_memory_empty": self.formal_memory_empty,
            "explicit_failure_payload": self.explicit_failure_payload,
            "explicit_pattern_payload": self.explicit_pattern_payload,
            "filters": dict(self.filters.as_query()),
            "selected_failure_id": self.selected_failure_id,
            "selected_pattern_id": self.selected_pattern_id,
            "memory_entries": [entry.to_dict() for entry in self.memory_entries],
            "failures": [entry.to_dict() for entry in self.failures],
            "patterns": [pattern.to_dict() for pattern in self.patterns],
            "availability": self.read_model.availability.to_dict(),
        }


FailureRecord = FailureExperience
FailurePatternView = FailurePattern
FailurePatternViewModel = FailurePattern
FailurePatternsViewModel = FailureViewModel
MemoryFailureViewModel = FailureViewModel


# ------------------------------- query/link ---------------------------------


def _query_pairs(context: QueryContext) -> list[tuple[str, str]]:
    if context is None:
        return []
    if isinstance(context, str):
        query = urlsplit(context).query if "?" in context or "://" in context else context.lstrip("?")
        return [(key, value) for key, value in parse_qsl(query, keep_blank_values=True) if key]
    pairs: list[tuple[str, str]] = []
    for key, value in context.items():
        if not isinstance(key, str) or not key:
            continue
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            pairs.extend((key, str(item)) for item in value)
        elif value is not None:
            pairs.append((key, str(value)))
    return pairs


def _stable_query(pairs: Sequence[tuple[str, str]]) -> str:
    order = {key: index for index, key in enumerate(_QUERY_ORDER)}
    values: dict[str, list[str]] = {}
    for key, value in pairs:
        values.setdefault(key, [])
        if value not in values[key]:
            values[key].append(value)
    keys = sorted(values, key=lambda key: (order.get(key, len(order)), key))
    return urlencode([(key, value) for key in keys for value in values[key]])


def _route_view(context: QueryContext) -> str:
    """Keep catalog/detail/filter links on the currently mounted failure route."""

    value = dict(_query_pairs(context)).get("view")
    return "memory-failures" if value == "memory-failures" else "failure-patterns"


def failure_link(
    failure_id: str | None = None,
    *,
    pattern_id: str | None = None,
    query_context: QueryContext = None,
    filters: FailureFilters | None = None,
    base_path: str = "/",
    view: str = "failure-patterns",
) -> str:
    pairs = [
        (key, value)
        for key, value in _query_pairs(query_context)
        if key not in {"view", "failure_id", "pattern_id", *_FILTER_KEYS}
    ]
    pairs.append(("view", view))
    if filters is not None:
        pairs.extend(filters.as_query())
    if failure_id is not None:
        pairs.append(("failure_id", failure_id))
    if pattern_id is not None:
        pairs.append(("pattern_id", pattern_id))
    query = _stable_query(pairs)
    return base_path if not query else f'{base_path}{"&" if "?" in base_path else "?"}{query}'


build_failure_link = failure_link


def _context_with_filters(view: FailureViewModel, context: QueryContext) -> QueryContext:
    pairs = _query_pairs(context)
    present = {key for key, _ in pairs}
    pairs.extend((key, value) for key, value in view.filters.as_query() if key not in present)
    return "?" + _stable_query(pairs) if pairs else None


# ------------------------------- rendering ----------------------------------


def _explicit_record_id(item: Mapping[str, object], *keys: str) -> str | None:
    """Read an explicitly published cross-layer identity without inventing one."""

    return _first(item, *keys)


def _render_cross_layer_links(entry: FailureExperience, context: QueryContext, *, translator: Translator) -> str:
    memory_id = _explicit_record_id(entry.raw, "memory_id", "memory_ref")
    pattern_id = _explicit_record_id(entry.raw, "pattern_id", "pattern_ref")
    links: list[str] = []
    if memory_id:
        links.append(
            f'<a class="failure-memory-link" href="{escape(memory_link(memory_id, query_context=context), quote=True)}">{translator.html("l4.open_memory")}</a>'
        )
    if pattern_id:
        links.append(
            f'<a class="failure-pattern-link" href="{escape(failure_link(pattern_id=pattern_id, query_context=context, view=_route_view(context)), quote=True)}">{translator.html("l4.open_derived_pattern")}</a>'
        )
    return f'<p class="failure-cross-layer-links">{" · ".join(links)}</p>' if links else ""


def _render_failure_detail(entry: FailureExperience, context: QueryContext, *, translator: Translator, model: ManagerReadModel) -> str:
    associations = "".join(
        f'<div><dt>{translator.label("lineage_kind", kind)}</dt><dd>{render_references((getattr(entry, kind),), translator=translator, query_context=context)}</dd></div>'
        for kind in LINEAGE_KINDS
    )
    facts = "".join(
        f'<div><dt>{translator.html(key)}</dt><dd>{render_memory_value(value, translator, domain)}</dd></div>'
        for key, value, domain in (
            ("l4.failure_category", entry.failure_category, "failure_category"),
            ("l4.stage", entry.stage, "failure_stage"),
            ("l4.outcome", entry.outcome, "failure_outcome"),
            ("l4.record_status", entry.status, "failure_state"),
        )
    )
    return (
        f'<article class="failure-detail" data-failure-id="{escape(entry.failure_id, quote=True)}">'
        f'<p class="eyebrow">{translator.html("l4.origin_" + entry.origin)} · {translator.html("l4.read_only_failure")}</p><h2>{render_memory_text(entry.title, translator, model)}</h2>'
        f'<p><strong>{translator.html("l4.failure_id")}</strong> {render_memory_value(entry.failure_id, translator)} · <strong>{translator.html("l4.memory_id")}</strong> {render_memory_value(entry.memory_id, translator)}</p>'
        f'<dl class="failure-facts">{facts}</dl><p><strong>{translator.html("l4.summary")}</strong> {render_memory_text(entry.summary, translator, model)}</p>'
        f'<section class="failure-associations"><h3>{translator.html("l4.traceability_associations")}</h3><dl>{associations}</dl></section>'
        f'<p><strong>{translator.html("l4.source_refs")}</strong> {render_references(entry.references, translator=translator, query_context=context)}</p>'
        f'{render_failure_lineage(entry.lineage, translator=translator, query_context=context, model=model)}'
        f'{_render_cross_layer_links(entry, context, translator=translator)}'
        f'<p><a href="{escape(failure_link(query_context=context, view=_route_view(context)), quote=True)}">{translator.html("l4.back_failure_catalog")}</a></p></article>'
    )


def _render_failure_row(entry: FailureExperience, context: QueryContext, *, translator: Translator, model: ManagerReadModel) -> str:
    summary = f'<br><span class="failure-summary-inline">{render_memory_text(entry.summary, translator, model)}</span>' if entry.summary else ""
    return (
        f'<tr data-failure-id="{escape(entry.failure_id, quote=True)}" data-outcome="{escape(entry.outcome or "", quote=True)}">'
        f'<th scope="row"><a href="{escape(failure_link(entry.failure_id, query_context=context, view=_route_view(context)), quote=True)}">{render_memory_text(entry.title, translator, model)}</a><br><small translate="no">{translator.source_text(entry.failure_id)}</small>{summary}</th>'
        f'<td>{render_memory_value(entry.failure_category, translator, "failure_category")}</td>'
        f'<td>{render_memory_value(entry.stage, translator, "failure_stage")}</td>'
        f'<td>{render_memory_value(entry.outcome, translator, "failure_outcome")}</td>'
        f'<td>{render_references((entry.campaign,), translator=translator, query_context=context)}</td><td>{translator.label("failure_state", entry.lineage.coverage)}</td></tr>'
    )


def _render_filters(view: FailureViewModel, context: QueryContext, *, translator: Translator) -> str:
    values = {key: getattr(view.filters, key) or "" for key in _FILTER_KEYS}
    hidden = "".join(
        f'<input type="hidden" name="{escape(key, quote=True)}" value="{escape(value, quote=True)}">'
        for key, value in _query_pairs(context)
        if key not in {"view", "failure_id", "pattern_id", *_FILTER_KEYS}
    )
    controls: list[str] = []
    for key in _FILTER_KEYS:
        choice_values: set[str] = set()
        for entry in view.all_failures:
            value = entry.campaign.record_id if key == "campaign" else getattr(entry, key)
            if isinstance(value, str) and value:
                choice_values.add(value)
        choices = sorted(choice_values)
        domains = {"failure_category": "failure_category", "stage": "failure_stage", "outcome": "failure_outcome"}
        options = "".join(
            f'<option value="{escape(choice, quote=True)}"{" selected" if values[key] == choice else ""} translate="no">{render_memory_value(choice, translator, domains.get(key))}</option>'
            for choice in choices
        )
        controls.append(
            f'<label>{translator.html("l4." + key)} <select name="{escape(key, quote=True)}"><option value="">{translator.html("l4.all")}</option>{options}</select></label>'
        )
    clear_href = clear_filters_link(
        context,
        view=_route_view(context),
        filter_keys=_FILTER_KEYS,
        selection_keys=("failure_id", "pattern_id"),
    )
    return (
        f'<form class="failure-filters" action="/" method="get" aria-label="{escape(translator.t("l4.failure_filters_aria"), quote=True)}">'
        f'<input type="hidden" name="view" value="{escape(_route_view(context), quote=True)}">'
        f'{hidden}{"".join(controls)}<button type="submit">{translator.html("l4.apply_filters")}</button>'
        f'<a href="{escape(clear_href, quote=True)}">{translator.html("l4.clear")}</a></form>'
    )


def _render_memory_layer(view: FailureViewModel, context: QueryContext, *, translator: Translator) -> str:
    if view.memory_entries:
        items: list[str] = []
        for entry in view.memory_entries:
            associations = " · ".join(
                f'<strong>{translator.label("lineage_kind", kind)}</strong> {render_references((getattr(entry, kind),), translator=translator, query_context=context)}'
                for kind in LINEAGE_KINDS
            )
            items.append(
                f'<article class="formal-memory-failure" data-failure-id="{escape(entry.failure_id, quote=True)}">'
                f'<h3><a class="memory-failure-link" href="{escape(failure_link(entry.failure_id, query_context=context, view="memory-failures"), quote=True)}">{render_memory_text(entry.title, translator, view.read_model)}</a></h3>'
                f'<p><strong>{translator.html("l4.failure_category")}</strong> {render_memory_value(entry.failure_category, translator, "failure_category")} · '
                f'<strong>{translator.html("l4.stage")}</strong> {render_memory_value(entry.stage, translator, "failure_stage")} · '
                f'<strong>{translator.html("l4.outcome")}</strong> {render_memory_value(entry.outcome, translator, "failure_outcome")}</p><p>{associations}</p>'
                f'<p><strong>{translator.html("l4.conflicts")}</strong> {render_references(entry.conflicts, translator=translator, query_context=context, empty="l4.none_conflicts")} · '
                f'<strong>{translator.html("l4.supersedes")}</strong> {render_references(entry.supersedes, translator=translator, query_context=context, empty="l4.none_supersession")}</p>'
                f'{render_failure_lineage(entry.lineage, translator=translator, query_context=context, model=view.read_model)}{_render_cross_layer_links(entry, context, translator=translator)}</article>'
            )
        return (
            '<section class="formal-memory-failures" data-memory-layer="formal-research-memory">'
            f'<h2>{translator.html("l4.formal_failure_entries")}</h2><p>{translator.html("l4.memory_layer_boundary")}</p>{"".join(items)}</section>'
        )
    if view.status in {ReadModelStatus.MISSING, ReadModelStatus.KNOWN} and (view.status is ReadModelStatus.MISSING or view.read_model.availability.complete):
        return (
            '<section class="formal-memory-empty" data-memory-layer="formal-research-memory" data-memory-state="empty">'
            f'<h2>{translator.html("l4.formal_research_memory")}</h2><p>{translator.html("l4.raw_failure_boundary")}</p></section>'
        )
    return (
        '<section class="formal-memory-undetermined" data-memory-layer="formal-research-memory" data-memory-state="not-determined">'
        f'<h2>{translator.html("l4.formal_research_memory")}</h2><p>{translator.html("l4.memory_not_determined", status=translator.t("label.status." + view.status.value))}</p></section>'
    )


def _render_failure_layer(
    view: FailureViewModel, context: QueryContext, *, translator: Translator
) -> str:
    if not view.failures:
        if view.status in {ReadModelStatus.MISSING, ReadModelStatus.KNOWN} and view.read_model.availability.complete:
            text = translator.html("l4.no_ordinary_failures")
            state = "empty"
        else:
            text = translator.html("l4.failure_not_determined", status=translator.t("label.status." + view.status.value))
            state = "not-determined"
        return f'<section class="failure-catalog" data-failure-state="{state}"><h2>{translator.html("l4.failure_catalog")}</h2><p>{text}</p></section>'
    rows = "".join(_render_failure_row(entry, context, translator=translator, model=view.read_model) for entry in view.failures)
    selected = view.selected_failure
    detail = _render_failure_detail(selected, context, translator=translator, model=view.read_model) if selected else ""
    if view.selected_failure_id is not None and selected is None:
        detail = (
            f'<section class="failure-detail-missing" data-failure-detail="missing">'
            f'<h3>{translator.html("l4.failure_entry_unavailable")}</h3><p>{render_memory_value(view.selected_failure_id, translator)} · {translator.html("l4.failure_snapshot_missing")}</p></section>'
        )
    return (
        f'<section class="failure-catalog" data-failure-state="ready"><h2>{translator.html("l4.failure_catalog")}</h2>'
        f'<p>{translator.html("l4.failure_fields_intro")}</p>'
        f'<table><caption>{translator.html("l4.ordinary_failure_records")}</caption><thead><tr><th>{translator.html("l4.failure")}</th><th>{translator.html("l4.failure_category")}</th><th>{translator.html("l4.stage")}</th><th>{translator.html("l4.outcome")}</th><th>{translator.html("l4.campaign")}</th><th>{translator.html("l4.lineage")}</th></tr></thead>'
        f'<tbody>{rows}</tbody></table>{detail}</section>'
    )


def _render_pattern_cross_layer_links(pattern: FailurePattern, context: QueryContext, *, translator: Translator) -> str:
    memory_id = _explicit_record_id(pattern.raw, "memory_id", "memory_ref")
    if not memory_id:
        return ""
    return (
        f'<p class="pattern-cross-layer-links"><a class="pattern-memory-link" '
        f'href="{escape(memory_link(memory_id, query_context=context), quote=True)}">{translator.html("l4.open_memory")}</a></p>'
    )


def _render_pattern(pattern: FailurePattern, context: QueryContext, *, translator: Translator, model: ManagerReadModel) -> str:
    members = " · ".join(
        f'<a class="pattern-failure-link" href="{escape(failure_link(identifier, query_context=context, view=_route_view(context)), quote=True)}">{render_memory_value(identifier, translator)}</a>'
        for identifier in pattern.failure_ids
    ) or translator.html("l4.missing_unconfirmed")
    return (
        f'<article class="failure-pattern" data-pattern-id="{escape(pattern.pattern_id, quote=True)}" data-pattern-status="derived" data-status="derived">'
        f'<p class="eyebrow">{translator.html("l4.pattern_eyebrow")}</p>'
        f'<h3>{render_memory_text(pattern.title, translator, model)}</h3><p><strong>{translator.html("l4.status")}</strong> <span class="derived-status">{translator.label("group_status", "derived")}</span></p>'
        f'<dl><div><dt>{translator.html("l4.rule")}</dt><dd>{render_memory_value(pattern.rule, translator)}</dd></div>'
        f'<div><dt>{translator.html("l4.input_scope")}</dt><dd>{translator.join(render_memory_value(value, translator) for value in pattern.input_scope) if pattern.input_scope else translator.html("l4.missing_unconfirmed")}</dd></div>'
        f'<div><dt>{translator.html("l4.sample_count")}</dt><dd>{pattern.sample_count if pattern.sample_count is not None else translator.html("l4.missing_unconfirmed")}</dd></div>'
        f'<div><dt>{translator.html("l4.failure_category")}</dt><dd>{render_memory_value(pattern.failure_category, translator, "failure_category")}</dd></div>'
        f'<div><dt>{translator.html("l4.stage")}</dt><dd>{render_memory_value(pattern.stage, translator, "failure_stage")}</dd></div>'
        f'<div><dt>{translator.html("l4.outcome")}</dt><dd>{render_memory_value(pattern.outcome, translator, "failure_outcome")}</dd></div></dl>'
        f'<p><strong>{translator.html("l4.participating_failures")}</strong> {members}</p>'
        f'<p><strong>{translator.html("l4.source_refs")}</strong> {render_references(pattern.source_refs, translator=translator, query_context=context)}</p>'
        f'{render_failure_lineage(pattern.lineage, translator=translator, query_context=context, model=model)}'
        f'{_render_pattern_cross_layer_links(pattern, context, translator=translator)}'
        f'<p><strong>{translator.html("l4.conflicts")}</strong> {render_references(pattern.conflicts, translator=translator, query_context=context, empty="l4.none_conflicts")}</p>'
        f'<p><strong>{translator.html("l4.supersedes")}</strong> {render_references(pattern.supersedes, translator=translator, query_context=context, empty="l4.none_supersession")}</p>'
        f'<p><a href="{escape(failure_link(pattern_id=pattern.pattern_id, query_context=context, view=_route_view(context)), quote=True)}">{translator.html("l4.open_derived_pattern")}</a></p></article>'
    )


def _render_pattern_layer(
    view: FailureViewModel, context: QueryContext, *, translator: Translator
) -> str:
    if not view.patterns:
        if view.status in {ReadModelStatus.MISSING, ReadModelStatus.KNOWN} and view.read_model.availability.complete:
            message, state = translator.html("l4.no_derived_patterns"), "empty"
        else:
            message, state = translator.html("l4.pattern_not_determined", status=translator.t("label.status." + view.status.value)), "not-determined"
        return f'<section class="derived-failure-patterns" data-pattern-state="{state}"><h2>{translator.html("l4.patterns_title")}</h2><p>{message}</p></section>'
    selected = view.selected_pattern
    missing = ""
    if view.selected_pattern_id is not None and selected is None:
        missing = (
            f'<section class="pattern-detail-missing" data-pattern-detail="missing">'
            f'<h3>{translator.html("l4.pattern_unavailable")}</h3><p>{render_memory_value(view.selected_pattern_id, translator)} · {translator.html("l4.failure_snapshot_missing")}</p></section>'
        )
    return (
        f'<section class="derived-failure-patterns" data-pattern-state="ready"><h2>{translator.html("l4.patterns_title")}</h2>'
        f'<p>{translator.html("l4.pattern_boundary")}</p>'
        f'{missing}{_render_pattern(selected, context, translator=translator, model=view.read_model) if selected else ""}{"".join(_render_pattern(pattern, context, translator=translator, model=view.read_model) for pattern in view.patterns if selected is None or pattern.pattern_id != selected.pattern_id)}</section>'
    )


def render_failure_patterns(
    view_or_model: FailureViewModel | ManagerReadModel,
    *,
    query_context: QueryContext = None,
    failure_id: str | None = None,
    pattern_id: str | None = None,
    translator: Translator | None = None,
) -> str:
    """Render a shell-independent S3-T2 fragment."""
    selected_translator = translator or Translator()
    view = view_or_model if isinstance(view_or_model, FailureViewModel) else FailureViewModel.from_read_model(
        view_or_model,
        filters=FailureFilters.from_query(query_context),
        failure_id=failure_id or dict(_query_pairs(query_context)).get("failure_id"),
        pattern_id=pattern_id or dict(_query_pairs(query_context)).get("pattern_id"),
    )
    model = view.read_model
    context = _context_with_filters(view, query_context)
    sources = selected_translator.join(render_memory_value(source.source_id, selected_translator) for source in model.source_refs) or selected_translator.html("l4.none_recorded")
    pieces = [
        f'<section class="failure-patterns-view" data-integration-hook="{FAILURE_PATTERN_HOOK}" data-failure-empty="{"true" if view.empty else "false"}">',
        f'<p class="eyebrow">{selected_translator.html("l4.failures_eyebrow")}</p><h1 class="page-title" data-page-title tabindex="-1">{selected_translator.html("l4.failures_title")}</h1>',
        f'<p class="failure-authority"><strong>{selected_translator.html("l4.layered_read_model")}</strong></p>',
        f'<p class="context-line"><span><strong>{selected_translator.html("l4.observed")}</strong> {render_memory_value(model.as_of, selected_translator, missing="l4.unavailable")}</span><span><strong>{selected_translator.html("l4.snapshot")}</strong> {render_memory_value(model.snapshot_token, selected_translator, missing="l4.unavailable")}</span><span><strong>{selected_translator.html("l4.sources")}</strong> {sources}</span></p>',
        render_status_block(model, translator=selected_translator),
    ]
    if model.availability.status is ReadModelStatus.KNOWN and not model.availability.complete:
        pieces.append(f'<p data-failure-state="partial">{selected_translator.html("l4.partial_failure_scope")}</p>')
    pieces.extend(
        (
            _render_memory_layer(view, context, translator=selected_translator),
            _render_filters(view, context, translator=selected_translator),
            _render_failure_layer(view, context, translator=selected_translator),
            _render_pattern_layer(view, context, translator=selected_translator),
        )
    )
    if view.empty and model.availability.status is ReadModelStatus.MISSING:
        pieces.append(
            render_operational_state(
                DisplayState.EMPTY,
                translator=selected_translator,
                detail=selected_translator.t("l4.no_formal_or_patterns"),
            )
        )
    pieces.append('</section>')
    return "".join(pieces)


def _read_view(
    provider_or_model: ProviderOrModel,
    *,
    resource: str,
    filters: FailureFilters | None,
    query_context: QueryContext,
    failure_id: str | None,
    pattern_id: str | None,
    snapshot_token: str | None,
) -> FailureViewModel:
    model = provider_or_model if isinstance(provider_or_model, ManagerReadModel) else provider_or_model.read(resource, snapshot_token=snapshot_token)
    values = dict(_query_pairs(query_context))
    return FailureViewModel.from_read_model(
        model,
        filters=filters or FailureFilters.from_query(query_context),
        failure_id=failure_id or values.get("failure_id"),
        pattern_id=pattern_id or values.get("pattern_id"),
    )


def failure_patterns_view(
    provider_or_model: ProviderOrModel,
    *,
    filters: FailureFilters | None = None,
    query_context: QueryContext = None,
    failure_id: str | None = None,
    pattern_id: str | None = None,
    snapshot_token: str | None = None,
) -> FailureViewModel:
    return _read_view(
        provider_or_model,
        resource=FAILURE_PATTERNS_RESOURCE,
        filters=filters,
        query_context=query_context,
        failure_id=failure_id,
        pattern_id=pattern_id,
        snapshot_token=snapshot_token,
    )


def memory_failure_view(
    provider_or_model: ProviderOrModel,
    *,
    filters: FailureFilters | None = None,
    query_context: QueryContext = None,
    failure_id: str | None = None,
    pattern_id: str | None = None,
    snapshot_token: str | None = None,
) -> FailureViewModel:
    return _read_view(
        provider_or_model,
        resource=MEMORY_FAILURE_RESOURCE,
        filters=filters,
        query_context=query_context,
        failure_id=failure_id,
        pattern_id=pattern_id,
        snapshot_token=snapshot_token,
    )


def render_failure_patterns_view(
    provider_or_model: ProviderOrModel,
    *,
    filters: FailureFilters | None = None,
    query_context: QueryContext = None,
    failure_id: str | None = None,
    pattern_id: str | None = None,
    snapshot_token: str | None = None,
    translator: Translator | None = None,
) -> str:
    return render_failure_patterns(
        failure_patterns_view(
            provider_or_model,
            filters=filters,
            query_context=query_context,
            failure_id=failure_id,
            pattern_id=pattern_id,
            snapshot_token=snapshot_token,
        ),
        query_context=query_context,
        translator=translator,
    )


def render_memory_failure_view(
    provider_or_model: ProviderOrModel,
    *,
    filters: FailureFilters | None = None,
    query_context: QueryContext = None,
    failure_id: str | None = None,
    pattern_id: str | None = None,
    snapshot_token: str | None = None,
    translator: Translator | None = None,
) -> str:
    return render_failure_patterns(
        memory_failure_view(
            provider_or_model,
            filters=filters,
            query_context=query_context,
            failure_id=failure_id,
            pattern_id=pattern_id,
            snapshot_token=snapshot_token,
        ),
        query_context=query_context,
        translator=translator,
    )


render_failure_pattern_view = render_failure_patterns_view
render_memory_failures_view = render_memory_failure_view
failure_view = failure_patterns_view

__all__ = [
    "FAILURE_PATTERNS_INTEGRATION_HOOK",
    "FAILURE_PATTERNS_RESOURCE",
    "FAILURE_PATTERN_HOOK",
    "MEMORY_FAILURE_INTEGRATION_HOOK",
    "MEMORY_FAILURE_RESOURCE",
    "FailureExperience",
    "FailureFilters",
    "FailureLineage",
    "FailurePattern",
    "FailurePatternView",
    "FailurePatternViewModel",
    "FailurePatternsViewModel",
    "FailureRecord",
    "FailureReference",
    "FailureViewModel",
    "MemoryFailureViewModel",
    "build_failure_link",
    "failure_link",
    "failure_patterns_view",
    "failure_view",
    "memory_failure_view",
    "render_failure_pattern_view",
    "render_failure_patterns",
    "render_failure_patterns_view",
    "render_memory_failure_view",
    "render_memory_failures_view",
]
