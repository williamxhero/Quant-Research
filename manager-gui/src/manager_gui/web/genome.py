"""Read-only Strategy Genome catalog, detail, and lifecycle surface.

The module consumes an already-published :class:`~manager_gui.models.ManagerReadModel`
whose ``data`` is JSON-compatible.  The expected payload is either a mapping with a
``genomes``/``records``/``items`` array or one Genome object with ``genome_id`` and
``behavior``.  A Genome object may contain ``behavior`` (the fourteen explicit
projection fields), ``candidate_revision``, ``provenance``, ``validation`` (with
``validator``, ``test_suite``, ``dependencies``, ``environment``, ``policy`` and
``result``), ``events`` and ``lineage``.  ``render_genome_view`` accepts either a
ManagerDataProvider (read resource ``"genomes"``) or an already-read envelope.

Only fields and source references present in the public envelope are displayed.  The
module never reads SQLite/private storage, infers a current lifecycle state from
history, or exposes mutation methods.  ``render_genome_view`` is the T3 integration
hook; the shared shell can mount its returned HTML at
``data-integration-hook="strategy-genome-view"`` without performing another read.
"""

# HTML fragments intentionally keep readable markup even when a line is long.
# ruff: noqa: E501

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from html import escape
from typing import TypeAlias, cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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
from .status import DisplayState, render_operational_state, render_status_block

GENOME_RESOURCE = "genomes"
GENOME_ROUTE = "strategies"
GENOME_INTEGRATION_HOOK = "strategy-genome-view"

BEHAVIOR_PROJECTION_FIELDS: tuple[str, ...] = (
    "schema",
    "signals",
    "composition",
    "universe",
    "portfolio",
    "sizing",
    "timing",
    "state",
    "risk_controls",
    "entry",
    "exit",
    "costs",
    "data_requirements",
    "required_capabilities",
)

VALIDATION_BINDING_FIELDS: tuple[str, ...] = (
    "validator",
    "test_suite",
    "dependencies",
    "environment",
    "policy",
    "result",
)

LINEAGE_ENTRY_KINDS: tuple[str, ...] = (
    "candidate",
    "hypothesis",
    "family",
    "context",
    "package",
    "run",
    "evidence",
)

LIFECYCLE_EVENT_KINDS: tuple[str, ...] = (
    "proposed",
    "validated",
    "published",
    "revoked",
    "tombstoned",
)

GENOME_BEHAVIOR_FIELDS = BEHAVIOR_PROJECTION_FIELDS
GENOME_VALIDATION_FIELDS = VALIDATION_BINDING_FIELDS
GENOME_EVENT_KINDS = LIFECYCLE_EVENT_KINDS
GENOME_LINEAGE_KINDS = LINEAGE_ENTRY_KINDS

_FILTER_KEYS: tuple[str, ...] = (
    "schema",
    "content_hash",
    "candidate_revision",
    "lifecycle_state",
    "q",
)
_CONTEXT_ORDER: tuple[str, ...] = (
    "view",
    "fixture",
    "panel",
    "q",
    "schema",
    "content_hash",
    "candidate_revision",
    "lifecycle_state",
    "genome_id",
)

QueryContext: TypeAlias = str | Mapping[str, object] | None
JSONMapping: TypeAlias = Mapping[str, JSONValue]


class GenomeFixtureState(StrEnum):
    """Deterministic fixture states used by focused tests and local previews."""

    COMPLETE = "complete"
    EMPTY = "empty"
    MISSING_FIELDS = "missing_fields"
    BLOCKED = "blocked"
    STALE = "stale"
    INTEGRITY_FAILURE = "integrity_failure"


FIXTURE_STATES: tuple[str, ...] = tuple(state.value for state in GenomeFixtureState)


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _mapping(value: object) -> Mapping[str, object] | None:
    if isinstance(value, Mapping):
        return cast(Mapping[str, object], value)
    return None


def _sequence(value: object) -> tuple[object, ...]:
    if value is None or isinstance(value, (str, bytes, bytearray)):
        return ()
    if isinstance(value, Sequence):
        return tuple(value)
    return ()


def _first_text(item: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        value = _text(item.get(key))
        if value is not None:
            return value
    return None


def _normalise(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _json_value(value: object) -> JSONValue | None:
    """Return a JSON-compatible value while preserving the owner payload exactly."""

    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        return None
    return cast(JSONValue, value)


def _json_mapping(value: object) -> JSONMapping:
    item = _mapping(value)
    if item is None:
        return {}
    return cast(JSONMapping, {str(key): _json_value(child) for key, child in item.items()})


def _value_state(value: object) -> str:
    if value is None:
        return "missing"
    if value == "" or value == [] or value == {}:
        return "empty"
    return "known"


def _display_value(value: object) -> str:
    state = _value_state(value)
    if state == "missing":
        return "Missing"
    if state == "empty":
        return "Empty"
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return "Missing"


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
    order = {key: index for index, key in enumerate(_CONTEXT_ORDER)}
    values: dict[str, list[str]] = {}
    for key, value in pairs:
        if key not in values:
            values[key] = []
        if value not in values[key]:
            values[key].append(value)
    keys = sorted(values, key=lambda key: (order.get(key, len(order)), key))
    return urlencode([(key, value) for key in keys for value in values[key]])


def _candidate_revision_text(value: object) -> str | None:
    if isinstance(value, str):
        return _text(value)
    if isinstance(value, Mapping):
        revision = value.get("revision")
        if type(revision) is int:
            return str(revision)
        return _first_text(value, "revision", "id", "record_id", "semantic_id")
    return None


def _raw_genome_items(data: object) -> tuple[Mapping[str, object], ...]:
    """Extract only explicit Genome objects from common catalog envelopes."""

    if isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
        return tuple(item for value in data if (item := _mapping(value)) is not None)
    item = _mapping(data)
    if item is None:
        return ()
    if _first_text(item, "genome_id", "genomeId") is not None:
        return (item,)
    for key in ("genomes", "items", "records", "objects"):
        values = _sequence(item.get(key))
        if values:
            return tuple(entry for value in values if (entry := _mapping(value)) is not None)
    for key in ("catalog", "data"):
        nested = _mapping(item.get(key))
        if nested is not None:
            found = _raw_genome_items(nested)
            if found:
                return found
    for key in ("genome", "detail", "selected"):
        nested = _mapping(item.get(key))
        if nested is not None and _first_text(nested, "genome_id", "genomeId") is not None:
            return (nested,)
    return ()


@dataclass(frozen=True, slots=True)
class GenomeField:
    """One explicit value in a Genome projection or validation binding."""

    name: str
    value: JSONValue | None
    state: str

    @property
    def available(self) -> bool:
        return self.state == "known"

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "value": self.value, "state": self.state}


@dataclass(frozen=True, slots=True)
class GenomeSourceRef:
    """A source or lineage pointer with no guessed locator."""

    source_id: str
    label: str
    locator: str | None = None
    owner: str | None = None
    kind: str | None = None
    record_type: str | None = None
    record_id: str | None = None
    schema: str | None = None
    revision: str | None = None
    raw: JSONMapping = field(default_factory=dict, repr=False, compare=False)

    @property
    def available(self) -> bool:
        return self.locator is not None

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "label": self.label,
            "locator": self.locator,
            "owner": self.owner,
            "kind": self.kind,
            "record_type": self.record_type,
            "record_id": self.record_id,
            "schema": self.schema,
            "revision": self.revision,
        }


@dataclass(frozen=True, slots=True)
class GenomeValidation:
    """The separate validation binding; it never changes Genome identity."""

    validator: JSONValue | None = None
    test_suite: JSONValue | None = None
    dependencies: JSONValue | None = None
    environment: JSONValue | None = None
    policy: JSONValue | None = None
    result: str | None = None
    present: bool = False
    raw: JSONMapping = field(default_factory=dict, repr=False, compare=False)

    def field(self, name: str) -> GenomeField:
        if name not in VALIDATION_BINDING_FIELDS:
            raise KeyError(name)
        value = getattr(self, name)
        return GenomeField(name, cast(JSONValue | None, value), _value_state(value))

    @property
    def fields(self) -> tuple[GenomeField, ...]:
        return tuple(self.field(name) for name in VALIDATION_BINDING_FIELDS)

    def to_dict(self) -> dict[str, object]:
        return {
            "validator": self.validator,
            "test_suite": self.test_suite,
            "dependencies": self.dependencies,
            "environment": self.environment,
            "policy": self.policy,
            "result": self.result,
        }


@dataclass(frozen=True, slots=True)
class GenomeLifecycleEvent:
    """One explicit source lifecycle event; no current state is inferred."""

    event_kind: str
    occurred_at: str | None
    actor: str | None = None
    reason: str | None = None
    source_refs: tuple[GenomeSourceRef, ...] = ()
    event_id: str | None = None
    raw: JSONMapping = field(default_factory=dict, repr=False, compare=False)

    def to_dict(self) -> dict[str, object]:
        return {
            "event_kind": self.event_kind,
            "occurred_at": self.occurred_at,
            "actor": self.actor,
            "reason": self.reason,
            "event_id": self.event_id,
            "source_refs": [item.to_dict() for item in self.source_refs],
        }


@dataclass(frozen=True, slots=True)
class GenomeLineageEntry:
    """One typed entry point into the owner-published Genome lineage."""

    kind: str
    record_id: str | None
    label: str | None = None
    source_refs: tuple[GenomeSourceRef, ...] = ()
    locator: str | None = None
    raw: JSONMapping = field(default_factory=dict, repr=False, compare=False)

    @property
    def available(self) -> bool:
        return self.record_id is not None or bool(self.source_refs)

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "record_id": self.record_id,
            "label": self.label,
            "locator": self.locator,
            "source_refs": [item.to_dict() for item in self.source_refs],
        }


@dataclass(frozen=True, slots=True)
class GenomeFilters:
    """Stable, explicit catalog filters that never synthesize lifecycle state."""

    schema: str | None = None
    content_hash: str | None = None
    candidate_revision: str | None = None
    lifecycle_state: str | None = None
    q: str | None = None

    def __post_init__(self) -> None:
        for name in _FILTER_KEYS:
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be a non-empty string or None")

    @classmethod
    def from_query(cls, context: QueryContext) -> GenomeFilters:
        values = dict(_query_pairs(context))
        return cls(**{key: _text(values.get(key)) for key in _FILTER_KEYS})

    def as_query(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (key, value) for key in _FILTER_KEYS if (value := getattr(self, key)) is not None
        )

    def matches(self, genome: GenomeRecord) -> bool:
        if self.schema is not None and genome.schema != self.schema:
            return False
        if self.content_hash is not None and genome.content_hash != self.content_hash:
            return False
        if (
            self.candidate_revision is not None
            and genome.candidate_revision_text != self.candidate_revision
        ):
            return False
        if self.lifecycle_state is not None:
            desired = _normalise(self.lifecycle_state)
            if desired != _normalise(genome.state or "") and desired not in genome.lifecycle_states:
                return False
        if self.q is None:
            return True
        haystack = json.dumps(genome.raw, ensure_ascii=False, sort_keys=True).lower()
        return self.q.lower() in haystack


@dataclass(frozen=True, slots=True)
class GenomeRecord:
    """Typed catalog/detail projection of one owner-published Genome object."""

    genome_id: str | None
    schema: str | None
    content_hash: str | None
    candidate_revision: JSONValue | None
    provenance: JSONMapping
    behavior: JSONMapping
    validation: GenomeValidation
    events: tuple[GenomeLifecycleEvent, ...]
    lineage: tuple[GenomeLineageEntry, ...]
    source_refs: tuple[GenomeSourceRef, ...] = ()
    state: str | None = None
    raw: JSONMapping = field(default_factory=dict, repr=False, compare=False)

    @property
    def candidate_revision_text(self) -> str | None:
        return _candidate_revision_text(self.candidate_revision)

    @property
    def behavior_fields(self) -> tuple[GenomeField, ...]:
        return tuple(
            GenomeField(name, self.behavior.get(name), _value_state(self.behavior.get(name)))
            for name in BEHAVIOR_PROJECTION_FIELDS
        )

    @property
    def behavior_projection(self) -> JSONMapping:
        return self.behavior

    @property
    def lifecycle_states(self) -> tuple[str, ...]:
        return tuple(event.event_kind for event in self.events)

    @property
    def source_lineage(self) -> tuple[GenomeLineageEntry, ...]:
        return self.lineage

    def to_dict(self) -> dict[str, object]:
        return {
            "genome_id": self.genome_id,
            "schema": self.schema,
            "content_hash": self.content_hash,
            "candidate_revision": self.candidate_revision,
            "provenance": self.provenance,
            "behavior": {field.name: field.value for field in self.behavior_fields},
            "validation": self.validation.to_dict(),
            "events": [event.to_dict() for event in self.events],
            "lineage": [entry.to_dict() for entry in self.lineage],
            "source_refs": [source.to_dict() for source in self.source_refs],
            "state": self.state,
            "raw": self.raw,
        }


@dataclass(frozen=True, slots=True)
class GenomeViewModel:
    """Catalog plus optional detail, ready for a deterministic page renderer."""

    read_model: ManagerReadModel
    genomes: tuple[GenomeRecord, ...]
    filters: GenomeFilters = field(default_factory=GenomeFilters)
    selected_genome_id: str | None = None

    @classmethod
    def from_read_model(
        cls,
        model: ManagerReadModel,
        *,
        filters: GenomeFilters | None = None,
        selected_genome_id: str | None = None,
    ) -> GenomeViewModel:
        selected_filters = filters or GenomeFilters()
        all_genomes = tuple(
            _parse_genome(item, model.source_refs) for item in _raw_genome_items(model.data)
        )
        genomes = tuple(genome for genome in all_genomes if selected_filters.matches(genome))
        selected = selected_genome_id
        if selected is None and len(genomes) == 1:
            selected = genomes[0].genome_id
        if selected is not None and not any(genome.genome_id == selected for genome in genomes):
            selected = None
        return cls(model, genomes, selected_filters, selected)

    @classmethod
    def parse(
        cls,
        model: ManagerReadModel,
        *,
        filters: GenomeFilters | None = None,
        selected_genome_id: str | None = None,
    ) -> GenomeViewModel:
        return cls.from_read_model(model, filters=filters, selected_genome_id=selected_genome_id)

    @property
    def catalog(self) -> tuple[GenomeRecord, ...]:
        return self.genomes

    @property
    def selected(self) -> GenomeRecord | None:
        if self.selected_genome_id is None:
            return None
        return next(
            (genome for genome in self.genomes if genome.genome_id == self.selected_genome_id), None
        )

    @property
    def detail(self) -> GenomeRecord | None:
        return self.selected

    @property
    def as_of(self) -> str | None:
        return self.read_model.as_of

    @property
    def snapshot_token(self) -> str | None:
        return self.read_model.snapshot_token

    def context_url(
        self,
        genome_id: str | None = None,
        *,
        base_path: str = "/",
        query: QueryContext = None,
    ) -> str:
        return genome_link(
            genome_id,
            query_context=query,
            filters=self.filters,
            base_path=base_path,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "view": GENOME_ROUTE,
            "filters": dict(self.filters.as_query()),
            "selected_genome_id": self.selected_genome_id,
            "genomes": [genome.to_dict() for genome in self.genomes],
            "detail": None if self.selected is None else self.selected.to_dict(),
            "availability": self.read_model.availability.to_dict(),
            "as_of": self.read_model.as_of,
            "snapshot_token": self.read_model.snapshot_token,
        }


def _source_ref_from_value(
    value: object,
    source_index: Mapping[str, SourceReference],
) -> GenomeSourceRef | None:
    if isinstance(value, str):
        source_id = _text(value)
        if source_id is None:
            return None
        source = source_index.get(source_id)
        if source is None:
            return GenomeSourceRef(source_id=source_id, label=source_id)
        return GenomeSourceRef(
            source_id=source.source_id,
            label=source.source_id,
            locator=source.locator,
            owner=source.owner,
            kind=source.kind,
            schema=source.schema,
            revision=source.revision,
            raw=cast(JSONMapping, source.to_dict()),
        )
    item = _mapping(value)
    if item is None:
        return None
    source_id = _first_text(item, "source_id", "sourceId", "id", "record_id")
    record_type = _first_text(item, "record_type", "recordType", "type")
    record_id = _first_text(item, "record_id", "recordId")
    if source_id is None and record_type is not None and record_id is not None:
        source_id = f"{record_type}:{record_id}"
    if source_id is None:
        return None
    source = source_index.get(source_id)
    locator = _first_text(item, "locator", "href", "url", "uri")
    if locator is None and source is not None:
        locator = source.locator
    return GenomeSourceRef(
        source_id=source_id,
        label=_first_text(item, "label", "title", "name") or source_id,
        locator=locator,
        owner=_first_text(item, "owner") or (source.owner if source else None),
        kind=_first_text(item, "kind", "source_kind") or (source.kind if source else None),
        record_type=record_type,
        record_id=record_id,
        schema=_first_text(item, "schema") or (source.schema if source else None),
        revision=_first_text(item, "revision") or (source.revision if source else None),
        raw=_json_mapping(item),
    )


def _source_values(item: Mapping[str, object]) -> tuple[object, ...]:
    values: list[object] = []
    for key in (
        "source_ref",
        "source_id",
        "sourceRef",
        "source_refs",
        "source_ids",
        "sources",
    ):
        value = item.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            values.extend(value)
        elif value is not None:
            values.append(value)
    return tuple(values)


def _source_refs(
    item: Mapping[str, object], source_index: Mapping[str, SourceReference]
) -> tuple[GenomeSourceRef, ...]:
    result: list[GenomeSourceRef] = []
    seen: set[tuple[str, str | None, str | None, str | None]] = set()
    for value in _source_values(item):
        source = _source_ref_from_value(value, source_index)
        if source is None:
            continue
        marker = (source.source_id, source.record_type, source.record_id, source.locator)
        if marker not in seen:
            seen.add(marker)
            result.append(source)
    return tuple(result)


def _merge_source_refs(*groups: Sequence[GenomeSourceRef]) -> tuple[GenomeSourceRef, ...]:
    result: list[GenomeSourceRef] = []
    seen: set[tuple[str, str | None, str | None, str | None]] = set()
    for group in groups:
        for source in group:
            marker = (source.source_id, source.record_type, source.record_id, source.locator)
            if marker not in seen:
                seen.add(marker)
                result.append(source)
    return tuple(result)


def _lineage_values(item: Mapping[str, object]) -> list[tuple[str, object]]:
    values: list[tuple[str, object]] = []
    lineage = item.get("lineage", item.get("lineage_entries"))
    lineage_mapping = _mapping(lineage)
    if lineage_mapping is not None:
        for kind in LINEAGE_ENTRY_KINDS:
            if kind in lineage_mapping:
                values.extend((kind, value) for value in _sequence_or_one(lineage_mapping[kind]))
    else:
        for value in _sequence(lineage):
            if isinstance(value, Mapping):
                explicit_kind = _first_text(
                    cast(Mapping[str, object], value), "kind", "record_type", "type"
                )
                if explicit_kind is not None:
                    values.append((_normalise(explicit_kind), value))
    provenance = _mapping(item.get("provenance"))
    for kind in LINEAGE_ENTRY_KINDS:
        if provenance is not None and kind in provenance:
            values.extend((kind, value) for value in _sequence_or_one(provenance[kind]))
    for kind in LINEAGE_ENTRY_KINDS:
        if kind in item:
            values.extend((kind, value) for value in _sequence_or_one(item[kind]))
    return values


def _sequence_or_one(value: object) -> tuple[object, ...]:
    sequence = _sequence(value)
    return sequence if sequence else (() if value is None else (value,))


def _parse_lineage(
    item: Mapping[str, object], source_index: Mapping[str, SourceReference]
) -> tuple[GenomeLineageEntry, ...]:
    result: list[GenomeLineageEntry] = []
    seen: set[tuple[str, str | None, str | None]] = set()
    for kind, value in _lineage_values(item):
        normalized_kind = _normalise(kind)
        if normalized_kind not in LINEAGE_ENTRY_KINDS:
            continue
        raw = _mapping(value)
        raw_item = raw if raw is not None else {"record_id": _text(value)}
        record_id = _first_text(raw_item, "record_id", "recordId", "id", "uid", "ref")
        label = _first_text(raw_item, "label", "title", "name", "display_name")
        locator = _first_text(raw_item, "locator", "href", "url", "uri")
        refs = _source_refs(raw_item, source_index)
        if not refs and raw is not None:
            refs = _source_refs({"source_ref": raw_item}, source_index)
        marker = (normalized_kind, record_id, locator)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(
            GenomeLineageEntry(
                kind=normalized_kind,
                record_id=record_id,
                label=label,
                source_refs=refs,
                locator=locator,
                raw=_json_mapping(raw_item),
            )
        )
    return tuple(result)


def _parse_events(
    item: Mapping[str, object], source_index: Mapping[str, SourceReference]
) -> tuple[GenomeLifecycleEvent, ...]:
    raw_events = item.get("events", item.get("lifecycle_events", item.get("timeline")))
    result: list[GenomeLifecycleEvent] = []
    for value in _sequence_or_one(raw_events):
        raw = _mapping(value)
        if raw is None:
            continue
        kind = _first_text(raw, "event_kind", "eventKind", "lifecycle_event", "kind", "type")
        if kind is None:
            continue
        normalized_kind = _normalise(kind)
        if normalized_kind not in LIFECYCLE_EVENT_KINDS:
            continue
        occurred_at = _first_text(
            raw, "occurred_at", "occurredAt", "event_time", "source_event_time", "timestamp"
        )
        result.append(
            GenomeLifecycleEvent(
                event_kind=normalized_kind,
                occurred_at=occurred_at,
                actor=_first_text(raw, "actor", "by", "principal"),
                reason=_first_text(raw, "reason", "message", "purpose"),
                source_refs=_source_refs(raw, source_index),
                event_id=_first_text(raw, "event_id", "eventId", "id"),
                raw=_json_mapping(raw),
            )
        )
    result.sort(key=lambda event: event.occurred_at or "")
    return tuple(result)


def _parse_validation(item: Mapping[str, object]) -> GenomeValidation:
    raw = _mapping(item.get("validation", item.get("validation_binding")))
    if raw is None:
        if any(key in item for key in VALIDATION_BINDING_FIELDS):
            raw = item
        else:
            return GenomeValidation()
    aliases: dict[str, tuple[str, ...]] = {
        "validator": ("validator",),
        "test_suite": ("test_suite", "testSuite", "tests"),
        "dependencies": ("dependencies", "behavior_dependencies"),
        "environment": ("environment", "configuration"),
        "policy": ("policy",),
        "result": ("result", "validation_result", "status"),
    }
    values: dict[str, object] = {
        name: next((raw[key] for key in keys if key in raw), None) for name, keys in aliases.items()
    }
    return GenomeValidation(
        validator=_json_value(values["validator"]),
        test_suite=_json_value(values["test_suite"]),
        dependencies=_json_value(values["dependencies"]),
        environment=_json_value(values["environment"]),
        policy=_json_value(values["policy"]),
        result=_text(values["result"]),
        present=True,
        raw=_json_mapping(raw),
    )


def _parse_genome(
    item: Mapping[str, object], source_references: Sequence[SourceReference]
) -> GenomeRecord:
    source_index = {source.source_id: source for source in source_references}
    behavior = _mapping(item.get("behavior", item.get("behavior_projection"))) or {}
    provenance = _json_mapping(item.get("provenance"))
    item_sources = _source_refs(item, source_index)
    provenance_sources = _source_refs(provenance, source_index)
    return GenomeRecord(
        genome_id=_first_text(item, "genome_id", "genomeId", "id", "record_id"),
        schema=_first_text(item, "schema", "genome_schema"),
        content_hash=_first_text(
            item, "content_hash", "contentHash", "behavior_hash", "behaviorHash"
        ),
        candidate_revision=_json_value(
            item.get("candidate_revision", item.get("candidateRevision"))
        ),
        provenance=provenance,
        behavior=_json_mapping(behavior),
        validation=_parse_validation(item),
        events=_parse_events(item, source_index),
        lineage=_parse_lineage(item, source_index),
        source_refs=_merge_source_refs(item_sources, provenance_sources),
        state=_first_text(item, "state", "status"),
        raw=_json_mapping(item),
    )


def genome_link(
    genome_id: str | None = None,
    *,
    query_context: QueryContext = None,
    filters: GenomeFilters | None = None,
    base_path: str = "/",
) -> str:
    """Build a stable Genome URL while retaining unrelated shell context."""

    if genome_id is not None and not isinstance(genome_id, str):
        raise TypeError("genome_id must be a string or None")
    pairs = [
        (key, value)
        for key, value in _query_pairs(query_context)
        if key not in {"view", "genome_id"}
    ]
    if filters is not None:
        pairs = [
            (key, value)
            for key, value in pairs
            if not (key in _FILTER_KEYS and getattr(filters, key) is not None)
        ]
        pairs.extend(filters.as_query())
    pairs.append(("view", GENOME_ROUTE))
    if genome_id is not None:
        pairs.append(("genome_id", genome_id))
    query = _stable_query(pairs)
    if not query:
        return base_path
    parsed = urlsplit(base_path)
    existing = parsed.query
    query = f"{existing}&{query}" if existing else query
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", query, parsed.fragment))


build_genome_link = genome_link
genome_detail_link = genome_link


def _context_with_filters(view: GenomeViewModel, context: QueryContext) -> QueryContext:
    pairs = _query_pairs(context)
    present = {key for key, _ in pairs}
    pairs.extend((key, value) for key, value in view.filters.as_query() if key not in present)
    return "?" + _stable_query(pairs) if pairs else None


def _render_sources(sources: Sequence[GenomeSourceRef]) -> str:
    if not sources:
        return '<span class="genome-missing">Missing source ref</span>'
    rendered: list[str] = []
    for source in sources:
        label = source.label or source.source_id
        if source.locator:
            rendered.append(
                f'<a class="genome-source-link" data-source-id="{escape(source.source_id, quote=True)}" '
                f'href="{escape(source.locator, quote=True)}">{escape(label)}</a>'
            )
        else:
            rendered.append(
                f'<span class="genome-source-unconfirmed" data-source-id="{escape(source.source_id, quote=True)}">'
                f"{escape(label)} — Missing locator</span>"
            )
    return " · ".join(rendered)


def _render_value(value: object, *, state_class: bool = True) -> str:
    state = _value_state(value)
    markup = escape(_display_value(value))
    return f'<span class="genome-value genome-value-{state if state_class else "known"}" data-value-state="{state}">{markup}</span>'


def _render_identity(genome: GenomeRecord) -> str:
    rows = (
        ("Genome ID", genome.genome_id),
        ("Schema", genome.schema),
        ("Content hash", genome.content_hash),
        ("Candidate revision", genome.candidate_revision),
        ("Provenance", genome.provenance),
        ("Explicit state", genome.state),
    )
    return (
        '<dl class="genome-identity">'
        + "".join(
            f'<div data-identity-field="{escape(label.lower().replace(" ", "_"), quote=True)}"><dt>{escape(label)}</dt><dd>{_render_value(value)}</dd></div>'
            for label, value in rows
        )
        + "</dl>"
    )


def _render_catalog(view: GenomeViewModel, context: QueryContext) -> str:
    if not view.genomes:
        return '<p class="genome-catalog-empty">No Genome records are present in this scope. Missing.</p>'
    rows = []
    for genome in view.genomes:
        detail_link = genome_link(genome.genome_id, query_context=context, filters=view.filters)
        rows.append(
            f'<li class="genome-catalog-row" data-genome-id="{escape(genome.genome_id or "", quote=True)}">'
            f'<a class="genome-detail-link" href="{escape(detail_link, quote=True)}">{escape(genome.genome_id or "Missing")}</a>'
            f'<span data-catalog-field="schema">{_render_value(genome.schema)}</span>'
            f'<span data-catalog-field="content-hash">{_render_value(genome.content_hash)}</span>'
            f'<span data-catalog-field="candidate-revision">{_render_value(genome.candidate_revision)}</span>'
            f'<span data-catalog-field="state">{_render_value(genome.state)}</span></li>'
        )
    return (
        '<ul class="genome-catalog" aria-label="Strategy Genome catalog">' + "".join(rows) + "</ul>"
    )


def _render_behavior(genome: GenomeRecord) -> str:
    rows = "".join(
        f'<tr data-behavior-field="{escape(field.name, quote=True)}"><th scope="row">{escape(field.name)}</th><td>{_render_value(field.value)}</td></tr>'
        for field in genome.behavior_fields
    )
    return (
        '<section class="genome-section genome-behavior" aria-labelledby="genome-behavior-title">'
        '<h3 id="genome-behavior-title">Behavior projection</h3>'
        "<p>All fourteen behavior fields are shown from the published read model; missing fields are not inferred.</p>"
        '<table><thead><tr><th scope="col">Field</th><th scope="col">Value</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></section>"
    )


def _render_validation(genome: GenomeRecord) -> str:
    rows = "".join(
        f'<tr data-validation-field="{escape(field.name, quote=True)}"><th scope="row">{escape(field.name.replace("_", " ").title())}</th><td>{_render_value(field.value)}</td></tr>'
        for field in genome.validation.fields
    )
    return (
        '<section class="genome-section genome-validation" aria-labelledby="genome-validation-title">'
        '<h3 id="genome-validation-title">Validation binding</h3>'
        "<p>Validation is a separate binding and does not change Genome content identity.</p>"
        '<table><thead><tr><th scope="col">Binding</th><th scope="col">Value</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></section>"
    )


def _render_events(genome: GenomeRecord) -> str:
    if not genome.events:
        body = (
            '<p class="genome-events-empty">No explicit lifecycle events are recorded. Missing.</p>'
        )
    else:
        items = []
        for event in genome.events:
            items.append(
                f'<li class="genome-event" data-event-kind="{escape(event.event_kind, quote=True)}">'
                f'<time datetime="{escape(event.occurred_at or "", quote=True)}">{escape(event.occurred_at or "Missing")}</time>'
                f"<strong>{escape(event.event_kind)}</strong>"
                f'<span class="genome-event-actor">{escape(event.actor or "Missing")}</span>'
                f'<span class="genome-event-reason">{escape(event.reason or "Missing")}</span>'
                f'<span class="genome-event-sources">{_render_sources(event.source_refs)}</span></li>'
            )
        body = f'<ol class="genome-event-timeline" aria-label="Genome lifecycle event timeline">{"".join(items)}</ol>'
    return (
        '<section class="genome-section genome-lifecycle" aria-labelledby="genome-lifecycle-title">'
        '<h3 id="genome-lifecycle-title">Lifecycle timeline</h3>'
        "<p>Only explicit proposed, validated, published, revoked, and tombstoned source events are shown; no state is inferred.</p>"
        f"{body}</section>"
    )


def _render_lineage(genome: GenomeRecord) -> str:
    sections: list[str] = []
    for kind in LINEAGE_ENTRY_KINDS:
        entries = tuple(entry for entry in genome.lineage if entry.kind == kind)
        if not entries:
            body = f'<p class="genome-lineage-empty">No {escape(kind)} lineage entry recorded. Missing.</p>'
        else:
            body = (
                "<ul>"
                + "".join(
                    f'<li data-lineage-kind="{escape(entry.kind, quote=True)}" data-record-id="{escape(entry.record_id or "", quote=True)}">'
                    f"<strong>{escape(entry.label or entry.record_id or 'Missing')}</strong>"
                    f'<span class="genome-lineage-record">{escape(entry.record_id or "Missing")}</span>'
                    f'<span class="genome-lineage-sources">{_render_sources(entry.source_refs)}</span></li>'
                    for entry in entries
                )
                + "</ul>"
            )
        sections.append(
            f'<section class="genome-lineage-group" data-lineage-group="{kind}"><h4>{escape(kind.title())}</h4>{body}</section>'
        )
    return (
        '<section class="genome-section genome-lineage" aria-labelledby="genome-lineage-title">'
        '<h3 id="genome-lineage-title">Lineage entry points</h3>'
        "<p>These candidate, hypothesis, family, context, package, run, and evidence refs are source-backed entry points.</p>"
        + "".join(sections)
        + "</section>"
    )


def _render_raw(genome: GenomeRecord) -> str:
    raw = json.dumps(genome.raw, ensure_ascii=False, sort_keys=True, indent=2)
    return f'<details class="genome-raw"><summary>Raw JSON</summary><pre data-raw-json>{escape(raw)}</pre></details>'


def _render_filters(view: GenomeViewModel, context: QueryContext) -> str:
    values = {key: getattr(view.filters, key) or "" for key in _FILTER_KEYS}
    hidden = "".join(
        f'<input type="hidden" name="{escape(key, quote=True)}" value="{escape(value, quote=True)}">'
        for key, value in _query_pairs(context)
        if key not in {"view", "genome_id", *_FILTER_KEYS}
    )
    controls = []
    for key in _FILTER_KEYS:
        label = key.replace("_", " ").title()
        controls.append(
            f'<label>{escape(label)} <input name="{escape(key, quote=True)}" value="{escape(values[key], quote=True)}"></label>'
        )
    return (
        '<form class="genome-filters" action="/" method="get" aria-label="Genome filters">'
        f'<input type="hidden" name="view" value="{GENOME_ROUTE}">{hidden}{"".join(controls)}'
        '<button type="submit">Apply filters</button>'
        f'<a class="genome-clear" href="/?view={GENOME_ROUTE}">Clear</a></form>'
    )


def render_genome(
    view_or_model: GenomeViewModel | ManagerReadModel,
    *,
    query_context: QueryContext = None,
    genome_id: str | None = None,
) -> str:
    """Render a mountable Genome catalog/detail fragment for the shared shell."""

    if isinstance(view_or_model, GenomeViewModel):
        view = view_or_model
        selected_id = genome_id or dict(_query_pairs(query_context)).get("genome_id")
        if selected_id != view.selected_genome_id:
            view = GenomeViewModel.from_read_model(
                view.read_model, filters=view.filters, selected_genome_id=selected_id
            )
    else:
        selected_id = genome_id
        if selected_id is None:
            selected_id = dict(_query_pairs(query_context)).get("genome_id")
        view = GenomeViewModel.from_read_model(
            view_or_model,
            filters=GenomeFilters.from_query(query_context),
            selected_genome_id=selected_id,
        )
    model = view.read_model
    context = _context_with_filters(view, query_context)
    source_text = ", ".join(source.source_id for source in model.source_refs) or "None recorded"
    pieces = [
        f'<section class="genome-page" data-integration-hook="{GENOME_INTEGRATION_HOOK}" data-genome-route="{GENOME_ROUTE}">',
        '<p class="eyebrow">Strategies / Genomes · read-only</p>',
        '<h1 class="page-title" data-page-title tabindex="-1">Strategy Genomes</h1>',
        '<p class="page-intro">Inspect published Genome identity, behavior projection, validation binding, lifecycle events, and lineage without inferring owner facts.</p>',
        f'<p class="context-line genome-context"><span><strong>Observed</strong> {escape(model.as_of or "Unavailable")}</span><span><strong>Snapshot</strong> {escape(model.snapshot_token or "Unavailable")}</span><span><strong>Sources</strong> {escape(source_text)}</span></p>',
        render_status_block(model),
    ]
    if not view.genomes and (
        model.availability.status is ReadModelStatus.MISSING
        or model.availability.status is ReadModelStatus.KNOWN
    ):
        pieces.append(
            render_operational_state(
                DisplayState.EMPTY, detail="No Genome records are present in this scope."
            )
        )
    pieces.append(_render_filters(view, context))
    pieces.append(
        '<section class="genome-catalog-section" aria-labelledby="genome-catalog-title"><h2 id="genome-catalog-title">Genome catalog</h2>'
    )
    pieces.append(_render_catalog(view, context))
    pieces.append("</section>")
    selected = view.selected
    if selected is not None:
        pieces.extend(
            (
                f'<article class="genome-detail" data-genome-id="{escape(selected.genome_id or "", quote=True)}" aria-labelledby="genome-detail-title">',
                f'<h2 id="genome-detail-title">Genome detail: {escape(selected.genome_id or "Missing")}</h2>',
                f'<p class="genome-detail-context"><a href="{escape(genome_link(None, query_context=context, filters=view.filters), quote=True)}">Back to catalog</a></p>',
                _render_identity(selected),
                _render_behavior(selected),
                _render_validation(selected),
                _render_events(selected),
                _render_lineage(selected),
                _render_raw(selected),
                "</article>",
            )
        )
    else:
        pieces.append(
            '<p class="genome-detail-empty">Select a Genome for detail; if no Genome is available, detail is Missing.</p>'
        )
    pieces.append("</section>")
    return "".join(pieces)


def genome_view(
    provider: ManagerDataProvider,
    *,
    filters: GenomeFilters | None = None,
    query_context: QueryContext = None,
    snapshot_token: str | None = None,
    genome_id: str | None = None,
) -> GenomeViewModel:
    """Read the Genome resource once through the public provider seam."""

    selected_filters = filters or GenomeFilters.from_query(query_context)
    selected_id = genome_id or dict(_query_pairs(query_context)).get("genome_id")
    return GenomeViewModel.from_read_model(
        provider.read(GENOME_RESOURCE, snapshot_token=snapshot_token),
        filters=selected_filters,
        selected_genome_id=selected_id,
    )


def render_genome_view(
    provider_or_model: ManagerDataProvider | ManagerReadModel,
    *,
    filters: GenomeFilters | None = None,
    query_context: QueryContext = None,
    snapshot_token: str | None = None,
    genome_id: str | None = None,
) -> str:
    """T3 hook: read/render one Genome surface without shell or storage logic."""

    if isinstance(provider_or_model, ManagerReadModel):
        selected_id = genome_id or dict(_query_pairs(query_context)).get("genome_id")
        view = GenomeViewModel.from_read_model(
            provider_or_model,
            filters=filters or GenomeFilters.from_query(query_context),
            selected_genome_id=selected_id,
        )
        return render_genome(view, query_context=query_context)
    return render_genome(
        genome_view(
            provider_or_model,
            filters=filters,
            query_context=query_context,
            snapshot_token=snapshot_token,
            genome_id=genome_id,
        ),
        query_context=query_context,
    )


render_genome_page = render_genome
render_strategy_genome = render_genome_view
GENOME_INTEGRATION_HOOK_PATH = "manager_gui.web.genome.render_genome_view"

Genome = GenomeRecord
GenomeDetail = GenomeRecord
GenomeEvent = GenomeLifecycleEvent
GenomeValidationBinding = GenomeValidation
GenomeCatalogViewModel = GenomeViewModel


def _fixture_source(source_id: str, locator: str) -> SourceReference:
    return SourceReference(
        source_id=source_id,
        owner="strategy-workspace",
        kind="public-record",
        locator=locator,
        schema="manager-genome.fixture.v0",
        revision="fixture-v0",
    )


def _complete_fixture_data(source_ids: Sequence[str]) -> dict[str, object]:
    behavior: dict[str, object] = {
        "schema": "apex-research.strategy-genome.v1",
        "signals": [{"signal_name": "price_ratio", "revision": "r1"}],
        "composition": {"operator": "and"},
        "universe": {"scope": "cn-equity"},
        "portfolio": {"max_positions": 20},
        "sizing": {"method": "equal_weight"},
        "timing": {"decision_lag_bars": 1},
        "state": {"holding_period": "daily"},
        "risk_controls": {"max_drawdown": 0.2},
        "entry": {"rule": "signal_positive"},
        "exit": {"rule": "signal_negative"},
        "costs": {"commission_bps": 5},
        "data_requirements": {"frequency": "1d"},
        "required_capabilities": ["market_data.read"],
    }
    events = [
        {
            "event_kind": kind,
            "occurred_at": f"2026-10-03T0{index}:00:00Z",
            "actor": "fixture",
            "reason": kind,
            "source_ref": source_ids[0],
        }
        for index, kind in enumerate(LIFECYCLE_EVENT_KINDS, start=1)
    ]
    lineage = {
        kind: {
            "record_id": f"{kind}-fixture-1",
            "label": f"Fixture {kind.title()}",
            "source_ref": source_ids[index % len(source_ids)],
        }
        for index, kind in enumerate(LINEAGE_ENTRY_KINDS)
    }
    return {
        "genomes": [
            {
                "genome_id": "genome-fixture-1",
                "schema": "apex-research.strategy-genome.v1",
                "content_hash": "sha256:fixture-content-1",
                "candidate_revision": {
                    "record_type": "strategy-candidate",
                    "record_id": "candidate-revision-1",
                    "revision": 1,
                },
                "provenance": {
                    "source_refs": list(source_ids),
                    "candidate": {"record_id": "candidate-fixture-1"},
                },
                "behavior": behavior,
                "validation": {
                    "validator": {"id": "genome-validator", "version": "v1"},
                    "test_suite": {"id": "behavior-suite", "version": "v1"},
                    "dependencies": [{"id": "factor-fixture-1", "version": "v1"}],
                    "environment": {"python": "3.11", "sandbox": "fixture"},
                    "policy": {"id": "validation-policy-v1"},
                    "result": "accepted",
                },
                "events": events,
                "lineage": lineage,
                "source_refs": list(source_ids),
                "state": "published",
            }
        ]
    }


def build_genome_fixture(state: GenomeFixtureState | str) -> ManagerReadModel:
    """Build a fresh, deterministic ManagerReadModel v0 Genome fixture."""

    selected = GenomeFixtureState(state)
    source = _fixture_source("fixture-genome-source", "fixture://manager-gui/genomes")
    source_ids = (source.source_id,)
    if selected is GenomeFixtureState.EMPTY:
        return ManagerReadModel(
            data={"genomes": []},
            source_refs=(),
            as_of=None,
            snapshot_token=None,
            derivation=Derivation(kind="direct", version="v0"),
            availability=Availability(
                ReadModelStatus.MISSING, False, "No Genome records are present in this scope."
            ),
        )
    if selected is GenomeFixtureState.COMPLETE:
        data = _complete_fixture_data(source_ids)
        return ManagerReadModel(
            data=cast(JSONValue, data),
            source_refs=(source,),
            as_of="2026-10-03T10:00:00Z",
            snapshot_token="genome-fixture-complete-v0",
            derivation=Derivation(kind="direct", inputs=source_ids, version="v0"),
            availability=Availability(ReadModelStatus.KNOWN, True, "Complete Genome fixture."),
        )
    if selected is GenomeFixtureState.MISSING_FIELDS:
        data = {
            "genomes": [
                {
                    "genome_id": "genome-missing-1",
                    "schema": "apex-research.strategy-genome.v1",
                    "behavior": {"signals": []},
                }
            ]
        }
        return ManagerReadModel(
            data=cast(JSONValue, data),
            source_refs=(source,),
            as_of="2026-10-03T10:00:00Z",
            snapshot_token="genome-fixture-missing-v0",
            derivation=Derivation(kind="direct", inputs=source_ids, version="v0"),
            availability=Availability(
                ReadModelStatus.KNOWN, False, "Genome fields are missing from the fixture."
            ),
            errors=(
                ReadModelError(
                    "genome_fields_missing",
                    "The fixture omits identity, validation, event, and lineage fields.",
                    source.source_id,
                ),
            ),
        )
    status_by_state = {
        GenomeFixtureState.BLOCKED: (
            ReadModelStatus.BLOCKED,
            "The approved Genome read seam is blocked.",
            "genome_read_blocked",
        ),
        GenomeFixtureState.STALE: (
            ReadModelStatus.STALE,
            "The Genome source is stale.",
            "genome_source_stale",
        ),
        GenomeFixtureState.INTEGRITY_FAILURE: (
            ReadModelStatus.INTEGRITY_FAILURE,
            "The Genome artifact failed integrity validation.",
            "genome_integrity_failure",
        ),
    }
    status, reason, code = status_by_state[selected]
    data = (
        {"genomes": []}
        if selected in {GenomeFixtureState.BLOCKED, GenomeFixtureState.INTEGRITY_FAILURE}
        else _complete_fixture_data(source_ids)
    )
    return ManagerReadModel(
        data=cast(JSONValue, data),
        source_refs=(source,),
        as_of="2025-01-01T00:00:00Z"
        if selected is GenomeFixtureState.STALE
        else "2026-10-03T10:00:00Z",
        snapshot_token=f"genome-fixture-{selected.value}-v0",
        derivation=Derivation(kind="direct", inputs=source_ids, version="v0"),
        availability=Availability(status, False, reason),
        errors=(ReadModelError(code, reason, source.source_id),),
    )


@dataclass(frozen=True, slots=True)
class GenomeFixtureProvider:
    """Read-only provider for deterministic Genome fixtures."""

    state: GenomeFixtureState

    def __init__(self, state: GenomeFixtureState | str) -> None:
        object.__setattr__(self, "state", GenomeFixtureState(state))

    def read(
        self, resource: str = GENOME_RESOURCE, *, snapshot_token: str | None = None
    ) -> ManagerReadModel:
        del snapshot_token
        if resource not in {GENOME_RESOURCE, GENOME_ROUTE, "genome"}:
            raise ValueError(f"unsupported Genome fixture resource: {resource!r}")
        return build_genome_fixture(self.state)


def genome_fixture_provider(state: GenomeFixtureState | str) -> GenomeFixtureProvider:
    return GenomeFixtureProvider(state)


__all__ = [
    "BEHAVIOR_PROJECTION_FIELDS",
    "FIXTURE_STATES",
    "GENOME_BEHAVIOR_FIELDS",
    "GENOME_EVENT_KINDS",
    "GENOME_INTEGRATION_HOOK",
    "GENOME_INTEGRATION_HOOK_PATH",
    "GENOME_LINEAGE_KINDS",
    "GENOME_RESOURCE",
    "GENOME_ROUTE",
    "GENOME_VALIDATION_FIELDS",
    "LIFECYCLE_EVENT_KINDS",
    "LINEAGE_ENTRY_KINDS",
    "VALIDATION_BINDING_FIELDS",
    "Genome",
    "GenomeCatalogViewModel",
    "GenomeDetail",
    "GenomeEvent",
    "GenomeField",
    "GenomeFilters",
    "GenomeFixtureProvider",
    "GenomeFixtureState",
    "GenomeLifecycleEvent",
    "GenomeLineageEntry",
    "GenomeRecord",
    "GenomeSourceRef",
    "GenomeValidation",
    "GenomeValidationBinding",
    "GenomeViewModel",
    "build_genome_fixture",
    "build_genome_link",
    "genome_detail_link",
    "genome_fixture_provider",
    "genome_link",
    "genome_view",
    "render_genome",
    "render_genome_page",
    "render_genome_view",
    "render_strategy_genome",
]
