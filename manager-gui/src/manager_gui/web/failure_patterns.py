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
from .memory import MemoryEntry, MemoryViewModel, memory_link
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


def _render_cross_layer_links(entry: FailureExperience, context: QueryContext) -> str:
    memory_id = _explicit_record_id(entry.raw, "memory_id", "memory_ref")
    pattern_id = _explicit_record_id(entry.raw, "pattern_id", "pattern_ref")
    links: list[str] = []
    if memory_id:
        links.append(
            f'<a class="failure-memory-link" href="{escape(memory_link(memory_id, query_context=context), quote=True)}">Open Memory</a>'
        )
    if pattern_id:
        links.append(
            f'<a class="failure-pattern-link" href="{escape(failure_link(pattern_id=pattern_id, query_context=context, view=_route_view(context)), quote=True)}">Open derived pattern</a>'
        )
    return f'<p class="failure-cross-layer-links">{" · ".join(links)}</p>' if links else ""


def _render_failure_detail(entry: FailureExperience, context: QueryContext) -> str:
    associations = "".join(
        f'<div><dt>{kind.replace("_", " ").title()}</dt><dd>{render_references((getattr(entry, kind),))}</dd></div>'
        for kind in LINEAGE_KINDS
    )
    return (
        f'<article class="failure-detail" data-failure-id="{escape(entry.failure_id, quote=True)}">'
        f'<p class="eyebrow">{escape(entry.origin)} · read-only failure</p><h2>{escape(entry.title)}</h2>'
        f'<p><strong>Failure ID</strong> {escape(entry.failure_id)} · <strong>Memory ID</strong> {escape(entry.memory_id or "Missing / Unconfirmed")}</p>'
        f'<dl class="failure-facts"><div><dt>Failure category</dt><dd>{escape(entry.failure_category or "Missing / Unconfirmed")}</dd></div>'
        f'<div><dt>Stage</dt><dd>{escape(entry.stage or "Missing / Unconfirmed")}</dd></div>'
        f'<div><dt>Outcome</dt><dd>{escape(entry.outcome or "Missing / Unconfirmed")}</dd></div>'
        f'<div><dt>Record status</dt><dd>{escape(entry.status or "Missing / Unconfirmed")}</dd></div></dl>'
        f'<p><strong>Summary</strong> {escape(entry.summary or "Missing / Unconfirmed")}</p>'
        f'<section class="failure-associations"><h3>Traceability associations</h3><dl>{associations}</dl></section>'
        f'<p><strong>Source refs</strong> {render_references(entry.references)}</p>'
        f'{render_failure_lineage(entry.lineage)}'
        f'{_render_cross_layer_links(entry, context)}'
        f'<p><a href="{escape(failure_link(query_context=context, view=_route_view(context)), quote=True)}">Back to failure catalog</a></p>'
        '</article>'
    )


def _render_failure_row(entry: FailureExperience, context: QueryContext) -> str:
    summary = (
        f'<br><span class="failure-summary-inline">{escape(entry.summary)}</span>'
        if entry.summary
        else ""
    )
    return (
        f'<tr data-failure-id="{escape(entry.failure_id, quote=True)}">'
        f'<th scope="row"><a href="{escape(failure_link(entry.failure_id, query_context=context, view=_route_view(context)), quote=True)}">{escape(entry.title)}</a><br><small>{escape(entry.failure_id)}</small>{summary}</th>'
        f'<td>{escape(entry.failure_category or "Missing / Unconfirmed")}</td>'
        f'<td>{escape(entry.stage or "Missing / Unconfirmed")}</td>'
        f'<td>{escape(entry.outcome or "Missing / Unconfirmed")}</td>'
        f'<td>{render_references((entry.campaign,))}</td><td>{escape(entry.lineage.coverage)}</td></tr>'
    )


def _render_filters(view: FailureViewModel, context: QueryContext) -> str:
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
        options = "".join(
            f'<option value="{escape(choice, quote=True)}"{" selected" if values[key] == choice else ""}>{escape(choice)}</option>'
            for choice in choices
        )
        controls.append(
            f'<label>{escape(key.replace("_", " ").title())} <select name="{escape(key, quote=True)}"><option value="">All</option>{options}</select></label>'
        )
    return (
        '<form class="failure-filters" action="/" method="get" aria-label="Failure filters">'
        f'<input type="hidden" name="view" value="{escape(_route_view(context), quote=True)}">'
        f'{hidden}{"".join(controls)}<button type="submit">Apply filters</button>'
        f'<a href="/?view={escape(_route_view(context), quote=True)}">Clear</a></form>'
    )


def _render_memory_layer(view: FailureViewModel, context: QueryContext) -> str:
    if view.memory_entries:
        entries = "".join(
            f'<article class="formal-memory-failure" data-failure-id="{escape(entry.failure_id, quote=True)}">'
            f'<h3><a class="memory-failure-link" href="{escape(failure_link(entry.failure_id, query_context=context, view="memory-failures"), quote=True)}">{escape(entry.title)}</a></h3>'
            f'<p><strong>Failure category</strong> {escape(entry.failure_category or "Missing / Unconfirmed")} · '
            f'<strong>Stage</strong> {escape(entry.stage or "Missing / Unconfirmed")} · '
            f'<strong>Outcome</strong> {escape(entry.outcome or "Missing / Unconfirmed")}</p>'
            f'<p><strong>Campaign</strong> {render_references((entry.campaign,))} · '
            f'<strong>Candidate</strong> {render_references((entry.candidate,))} · '
            f'<strong>Run</strong> {render_references((entry.run,))}</p>'
            f'<p><strong>Evidence</strong> {render_references((entry.evidence,))} · '
            f'<strong>Artifact</strong> {render_references((entry.artifact,))} · '
            f'<strong>Source document</strong> {render_references((entry.source_document,))}</p>'
            f'<p><strong>Conflicts</strong> {render_references(entry.conflicts, empty="None recorded; not proof of no conflicts")} · '
            f'<strong>Supersedes</strong> {render_references(entry.supersedes, empty="None recorded; no supersession inferred")}</p>'
            f'{render_failure_lineage(entry.lineage)}{_render_cross_layer_links(entry, context)}</article>'
            for entry in view.memory_entries
        )
        return (
            '<section class="formal-memory-failures" data-memory-layer="formal-research-memory">'
            '<h2>Formal Research Memory failure entries</h2>'
            '<p>Owner-published Memory remains distinct from GUI-derived aggregation.</p>'
            f'{entries}</section>'
        )
    if view.status in {ReadModelStatus.MISSING, ReadModelStatus.KNOWN} and (
        view.status is ReadModelStatus.MISSING or view.read_model.availability.complete
    ):
        return (
            '<section class="formal-memory-empty" data-memory-layer="formal-research-memory" data-memory-state="empty">'
            '<h2>Formal Research Memory</h2><p>No formal Research Memory entries are recorded. Raw failure records remain a separate layer.</p></section>'
        )
    return (
        f'<section class="formal-memory-undetermined" data-memory-layer="formal-research-memory" data-memory-state="not-determined">'
        f'<h2>Formal Research Memory</h2><p>Formal Memory is not determined while read-model status is {escape(view.status.value)}; this is not evidence of an empty Memory store.</p></section>'
    )


def _render_failure_layer(view: FailureViewModel, context: QueryContext) -> str:
    if not view.failures:
        if view.status in {ReadModelStatus.MISSING, ReadModelStatus.KNOWN} and view.read_model.availability.complete:
            text = "No ordinary failure records are recorded in this scope."
            state = "empty"
        else:
            text = f"Failure records are not determined while read-model status is {view.status.value}; failures are not relabeled as success."
            state = "not-determined"
        return f'<section class="failure-catalog" data-failure-state="{state}"><h2>Failure experiences</h2><p>{escape(text)}</p></section>'
    rows = "".join(_render_failure_row(entry, context) for entry in view.failures)
    selected = view.selected_failure
    detail = _render_failure_detail(selected, context) if selected else ""
    if view.selected_failure_id is not None and selected is None:
        detail = (
            f'<section class="failure-detail-missing" data-failure-detail="missing">'
            f'<h3>Failure entry unavailable</h3><p>{escape(view.selected_failure_id)} — Missing / Unconfirmed in this snapshot.</p></section>'
        )
    return (
        '<section class="failure-catalog" data-failure-state="ready"><h2>Failure experiences</h2>'
        '<p>Failure category, stage, and outcome remain first-class fields.</p>'
        '<table><caption>Ordinary failure records</caption><thead><tr><th>Failure</th><th>Failure category</th><th>Stage</th><th>Outcome</th><th>Campaign</th><th>Lineage</th></tr></thead>'
        f'<tbody>{rows}</tbody></table>{detail}</section>'
    )


def _render_pattern_cross_layer_links(pattern: FailurePattern, context: QueryContext) -> str:
    memory_id = _explicit_record_id(pattern.raw, "memory_id", "memory_ref")
    if not memory_id:
        return ""
    return (
        f'<p class="pattern-cross-layer-links"><a class="pattern-memory-link" '
        f'href="{escape(memory_link(memory_id, query_context=context), quote=True)}">Open Memory</a></p>'
    )


def _render_pattern(pattern: FailurePattern, context: QueryContext) -> str:
    members = " · ".join(
        f'<a class="pattern-failure-link" href="{escape(failure_link(identifier, query_context=context, view=_route_view(context)), quote=True)}">{escape(identifier)}</a>'
        for identifier in pattern.failure_ids
    ) or "Missing / Unconfirmed"
    return (
        f'<article class="failure-pattern" data-pattern-id="{escape(pattern.pattern_id, quote=True)}" data-pattern-status="derived" data-status="derived">'
        '<p class="eyebrow">Derived · GUI aggregation · not formal Research Memory</p>'
        f'<h3>{escape(pattern.title)}</h3><p><strong>Status</strong> <span class="derived-status">Derived</span></p>'
        f'<dl><div><dt>Rule</dt><dd>{escape(pattern.rule or "Missing / Unconfirmed")}</dd></div>'
        f'<div><dt>Input scope</dt><dd>{escape(", ".join(pattern.input_scope) or "Missing / Unconfirmed")}</dd></div>'
        f'<div><dt>Sample count</dt><dd>{escape(str(pattern.sample_count) if pattern.sample_count is not None else "Missing / Unconfirmed")}</dd></div>'
        f'<div><dt>Failure category</dt><dd>{escape(pattern.failure_category or "Missing / Unconfirmed")}</dd></div>'
        f'<div><dt>Stage</dt><dd>{escape(pattern.stage or "Missing / Unconfirmed")}</dd></div>'
        f'<div><dt>Outcome</dt><dd>{escape(pattern.outcome or "Missing / Unconfirmed")}</dd></div></dl>'
        f'<p><strong>Participating failure records</strong> {members}</p>'
        f'<p><strong>Source refs</strong> {render_references(pattern.source_refs)}</p>'
        f'{render_failure_lineage(pattern.lineage)}'
        f'{_render_pattern_cross_layer_links(pattern, context)}'
        f'<p><strong>Conflicts</strong> {render_references(pattern.conflicts, empty="None recorded; no conflicts inferred")}</p>'
        f'<p><strong>Supersedes</strong> {render_references(pattern.supersedes, empty="None recorded; no supersession inferred")}</p>'
        f'<p><a href="{escape(failure_link(pattern_id=pattern.pattern_id, query_context=context, view=_route_view(context)), quote=True)}">Open derived pattern</a></p>'
        '</article>'
    )


def _render_pattern_layer(view: FailureViewModel, context: QueryContext) -> str:
    if not view.patterns:
        if view.status in {ReadModelStatus.MISSING, ReadModelStatus.KNOWN} and view.read_model.availability.complete:
            message, state = "No explicitly published Derived failure patterns are recorded.", "empty"
        else:
            message, state = f"Derived failure patterns are not determined while read-model status is {view.status.value}.", "not-determined"
        return f'<section class="derived-failure-patterns" data-pattern-state="{state}"><h2>Derived failure patterns</h2><p>{escape(message)}</p></section>'
    selected = view.selected_pattern
    missing = ""
    if view.selected_pattern_id is not None and selected is None:
        missing = (
            f'<section class="pattern-detail-missing" data-pattern-detail="missing">'
            f'<h3>Derived pattern unavailable</h3><p>{escape(view.selected_pattern_id)} — Missing / Unconfirmed in this snapshot.</p></section>'
        )
    return (
        '<section class="derived-failure-patterns" data-pattern-state="ready"><h2>Derived failure patterns</h2>'
        '<p>Only explicitly named aggregations are shown; these are not formal Memory publications.</p>'
        f'{missing}{_render_pattern(selected, context) if selected else ""}{"".join(_render_pattern(pattern, context) for pattern in view.patterns if selected is None or pattern.pattern_id != selected.pattern_id)}</section>'
    )


def render_failure_patterns(
    view_or_model: FailureViewModel | ManagerReadModel,
    *,
    query_context: QueryContext = None,
    failure_id: str | None = None,
    pattern_id: str | None = None,
) -> str:
    """Render a shell-independent S3-T2 fragment."""
    view = view_or_model if isinstance(view_or_model, FailureViewModel) else FailureViewModel.from_read_model(
        view_or_model,
        filters=FailureFilters.from_query(query_context),
        failure_id=failure_id or dict(_query_pairs(query_context)).get("failure_id"),
        pattern_id=pattern_id or dict(_query_pairs(query_context)).get("pattern_id"),
    )
    model = view.read_model
    context = _context_with_filters(view, query_context)
    sources = ", ".join(source.source_id for source in model.source_refs) or "None recorded"
    pieces = [
        f'<section class="failure-patterns-view" data-integration-hook="{FAILURE_PATTERN_HOOK}" data-failure-empty="{"true" if view.empty else "false"}">',
        '<p class="eyebrow">Failures · read-only traceability</p><h1 class="page-title" data-page-title tabindex="-1">Failure experiences &amp; derived patterns</h1>',
        '<p class="failure-authority"><strong>Layered read model</strong> Formal Research Memory, ordinary failure records, and GUI-derived patterns are separate.</p>',
        f'<p class="context-line"><span><strong>Observed</strong> {escape(model.as_of or "Unavailable")}</span><span><strong>Snapshot</strong> {escape(model.snapshot_token or "Unavailable")}</span><span><strong>Sources</strong> {escape(sources)}</span></p>',
        render_status_block(model),
    ]
    if model.availability.status is ReadModelStatus.KNOWN and not model.availability.complete:
        pieces.append('<p data-failure-state="partial">Partial failure scope: unavailable entries are not filled in.</p>')
    pieces.extend((_render_memory_layer(view, context), _render_filters(view, context), _render_failure_layer(view, context), _render_pattern_layer(view, context)))
    if view.empty and model.availability.status is ReadModelStatus.MISSING:
        pieces.append(render_operational_state(DisplayState.EMPTY, detail="No formal Memory or failure-pattern records are present in this scope."))
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
    )


def render_memory_failure_view(
    provider_or_model: ProviderOrModel,
    *,
    filters: FailureFilters | None = None,
    query_context: QueryContext = None,
    failure_id: str | None = None,
    pattern_id: str | None = None,
    snapshot_token: str | None = None,
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
