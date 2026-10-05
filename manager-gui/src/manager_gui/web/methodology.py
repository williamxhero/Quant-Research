"""Read-only Methodology archive and versioned-method renderer.

S5-T3 can mount :func:`render_methodology_view` at the shared
``methodology-view`` surface.  The hook accepts any ``ManagerDataProvider``
that returns a ``ManagerReadModel v0`` for the ``methodology`` resource, or a
pre-built :class:`MethodologyViewModel` can be rendered directly.  The payload
must contain explicit methodology records; this module does not scan paths,
open private storage, infer validity from usage counts/results, or mutate an
owner system.  Deterministic fixtures in this module are for tests and local
read-only demonstrations only.
"""

# HTML fragments intentionally use readable long lines.
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
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
from .i18n import Translator
from .i18n.catalog import l3_method_history as _l3_method_history_catalog
from .navigation import PageWindow, context_link
from .status import DisplayState, display_state_for, render_operational_state, render_status_block

METHODOLOGY_INTEGRATION_HOOK = "manager_gui.web.methodology.render_methodology_view"
METHODOLOGY_RESOURCE = "methodology"


class MethodologyCategory(StrEnum):
    """The five non-overlapping categories in the methodology archive."""

    WORKFLOW_PROCESS = "workflow_process"
    WORKFLOW = "workflow_process"
    STATISTICAL_PROTOCOL = "statistical_protocol"
    STATISTICAL = "statistical_protocol"
    POLICY = "policy"
    BENCHMARK = "benchmark"
    OPERATIONAL_CONSTRAINT = "operational_constraint"
    OPERATIONAL = "operational_constraint"


MethodologyKind = MethodologyCategory
CATEGORY_ORDER: tuple[MethodologyCategory, ...] = tuple(MethodologyCategory)
CATEGORY_LABELS: Mapping[MethodologyCategory, str] = {
    MethodologyCategory.WORKFLOW_PROCESS: "Workflow / process",
    MethodologyCategory.STATISTICAL_PROTOCOL: "Statistical protocol",
    MethodologyCategory.POLICY: "Policy",
    MethodologyCategory.BENCHMARK: "Benchmark",
    MethodologyCategory.OPERATIONAL_CONSTRAINT: "Operational constraint",
}
_CATEGORY_ALIASES: Mapping[str, MethodologyCategory] = {
    "workflow": MethodologyCategory.WORKFLOW_PROCESS,
    "workflows": MethodologyCategory.WORKFLOW_PROCESS,
    "workflow_process": MethodologyCategory.WORKFLOW_PROCESS,
    "workflow/process": MethodologyCategory.WORKFLOW_PROCESS,
    "process": MethodologyCategory.WORKFLOW_PROCESS,
    "processes": MethodologyCategory.WORKFLOW_PROCESS,
    "statistical": MethodologyCategory.STATISTICAL_PROTOCOL,
    "statistical_protocol": MethodologyCategory.STATISTICAL_PROTOCOL,
    "statistical_protocols": MethodologyCategory.STATISTICAL_PROTOCOL,
    "protocol": MethodologyCategory.STATISTICAL_PROTOCOL,
    "protocols": MethodologyCategory.STATISTICAL_PROTOCOL,
    "policy": MethodologyCategory.POLICY,
    "policies": MethodologyCategory.POLICY,
    "benchmark": MethodologyCategory.BENCHMARK,
    "benchmarks": MethodologyCategory.BENCHMARK,
    "operational": MethodologyCategory.OPERATIONAL_CONSTRAINT,
    "operational_constraint": MethodologyCategory.OPERATIONAL_CONSTRAINT,
    "operational_constraints": MethodologyCategory.OPERATIONAL_CONSTRAINT,
    "constraint": MethodologyCategory.OPERATIONAL_CONSTRAINT,
    "constraints": MethodologyCategory.OPERATIONAL_CONSTRAINT,
}


class MethodologyIndexState(StrEnum):
    """Explicit index state, distinct from the v0 source availability status."""

    INDEXED = "indexed"
    NOT_INDEXED = "not_indexed"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class MethodologySourceRef:
    """A source reference resolved from the v0 envelope, or explicitly missing."""

    source_id: str
    owner: str | None = None
    kind: str | None = None
    locator: str | None = None
    schema: str | None = None
    revision: str | None = None
    available: bool = True

    def __post_init__(self) -> None:
        _require_text(self.source_id, "source_id")
        for name in ("owner", "kind", "locator", "schema", "revision"):
            _optional_text(getattr(self, name), name)
        if not isinstance(self.available, bool):
            raise ValueError("available must be a boolean")

    @property
    def label(self) -> str:
        return self.source_id

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "owner": self.owner,
            "kind": self.kind,
            "locator": self.locator,
            "schema": self.schema,
            "revision": self.revision,
            "available": self.available,
        }


@dataclass(frozen=True, slots=True)
class MethodologyDocumentRef:
    """An explicit approved document-index reference."""

    document_id: str
    title: str | None = None
    locator: str | None = None
    revision: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.document_id, "document_id")
        for name in ("title", "locator", "revision"):
            _optional_text(getattr(self, name), name)

    @property
    def available(self) -> bool:
        return self.locator is not None

    def to_dict(self) -> dict[str, object]:
        return {
            "document_id": self.document_id,
            "title": self.title,
            "locator": self.locator,
            "revision": self.revision,
            "available": self.available,
        }


@dataclass(frozen=True, slots=True)
class MethodologyRecordRef:
    """An explicit owner-record reference; it is never inferred from a title."""

    record_id: str
    label: str | None = None
    locator: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.record_id, "record_id")
        _optional_text(self.label, "label")
        _optional_text(self.locator, "locator")

    @property
    def available(self) -> bool:
        return self.locator is not None

    def to_dict(self) -> dict[str, object]:
        return {
            "record_id": self.record_id,
            "label": self.label,
            "locator": self.locator,
            "available": self.available,
        }


@dataclass(frozen=True, slots=True)
class MethodologyUsage:
    """One explicit use record, kept separate from validity evidence."""

    usage_id: str
    summary: str | None = None
    used_at: str | None = None
    record_refs: tuple[MethodologyRecordRef, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.usage_id, "usage_id")
        _optional_text(self.summary, "summary")
        _optional_text(self.used_at, "used_at")

    def to_dict(self) -> dict[str, object]:
        return {
            "usage_id": self.usage_id,
            "summary": self.summary,
            "used_at": self.used_at,
            "record_refs": [ref.to_dict() for ref in self.record_refs],
        }


@dataclass(frozen=True, slots=True)
class MethodologyResult:
    """An explicitly associated result, not a validity conclusion."""

    result_id: str
    title: str | None = None
    summary: str | None = None
    status: str | None = None
    record_refs: tuple[MethodologyRecordRef, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.result_id, "result_id")
        for name in ("title", "summary", "status"):
            _optional_text(getattr(self, name), name)

    def to_dict(self) -> dict[str, object]:
        return {
            "result_id": self.result_id,
            "title": self.title,
            "summary": self.summary,
            "status": self.status,
            "record_refs": [ref.to_dict() for ref in self.record_refs],
        }


@dataclass(frozen=True, slots=True)
class MethodologyValidityEvidence:
    """Evidence explicitly labelled as validity evidence by an owner source."""

    evidence_id: str
    label: str | None = None
    summary: str | None = None
    status: str | None = None
    source_refs: tuple[MethodologySourceRef, ...] = ()
    document_refs: tuple[MethodologyDocumentRef, ...] = ()
    record_refs: tuple[MethodologyRecordRef, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.evidence_id, "evidence_id")
        for name in ("label", "summary", "status"):
            _optional_text(getattr(self, name), name)

    def to_dict(self) -> dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "label": self.label,
            "summary": self.summary,
            "status": self.status,
            "source_refs": [ref.to_dict() for ref in self.source_refs],
            "document_refs": [ref.to_dict() for ref in self.document_refs],
            "record_refs": [ref.to_dict() for ref in self.record_refs],
        }


@dataclass(frozen=True, slots=True)
class MethodologyMethod:
    """A versioned methodology entry with explicit evidence boundaries."""

    method_id: str
    title: str
    category: MethodologyCategory
    definition: str | None = None
    version: str | None = None
    usage_count: int | None = None
    usage_records: tuple[MethodologyUsage, ...] = ()
    associated_results: tuple[MethodologyResult, ...] = ()
    validity_evidence: tuple[MethodologyValidityEvidence, ...] = ()
    limitations: tuple[str, ...] = ()
    failure_cases: tuple[str, ...] = ()
    superseded: bool | None = None
    superseded_by: str | None = None
    source_refs: tuple[MethodologySourceRef, ...] = ()
    document_refs: tuple[MethodologyDocumentRef, ...] = ()
    record_refs: tuple[MethodologyRecordRef, ...] = ()
    raw: Mapping[str, object] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        _require_text(self.method_id, "method_id")
        _require_text(self.title, "title")
        if not isinstance(self.category, MethodologyCategory):
            raise ValueError("category must be a MethodologyCategory")
        for name in ("definition", "version", "superseded_by"):
            _optional_text(getattr(self, name), name)
        if self.usage_count is not None and (
            not isinstance(self.usage_count, int) or isinstance(self.usage_count, bool)
        ):
            raise ValueError("usage_count must be a non-negative integer or None")
        if self.usage_count is not None and self.usage_count < 0:
            raise ValueError("usage_count must be a non-negative integer or None")
        if self.superseded is not None and not isinstance(self.superseded, bool):
            raise ValueError("superseded must be a boolean or None")
        if not all(isinstance(item, str) and item.strip() for item in self.limitations):
            raise ValueError("limitations must contain non-empty strings")
        if not all(isinstance(item, str) and item.strip() for item in self.failure_cases):
            raise ValueError("failure_cases must contain non-empty strings")

    @property
    def category_label(self) -> str:
        return CATEGORY_LABELS[self.category]

    @property
    def superseded_label(self) -> str:
        if self.superseded is True:
            return "Superseded"
        if self.superseded is False:
            return "Current / not superseded"
        return "Superseded status not recorded"

    @property
    def has_validity_evidence(self) -> bool:
        """Whether validity evidence was explicitly recorded, not whether valid."""

        return bool(self.validity_evidence)

    def to_dict(self) -> dict[str, object]:
        return {
            "method_id": self.method_id,
            "title": self.title,
            "category": self.category.value,
            "definition": self.definition,
            "version": self.version,
            "usage_count": self.usage_count,
            "usage_records": [record.to_dict() for record in self.usage_records],
            "associated_results": [result.to_dict() for result in self.associated_results],
            "validity_evidence": [evidence.to_dict() for evidence in self.validity_evidence],
            "limitations": list(self.limitations),
            "failure_cases": list(self.failure_cases),
            "superseded": self.superseded,
            "superseded_by": self.superseded_by,
            "source_refs": [ref.to_dict() for ref in self.source_refs],
            "document_refs": [ref.to_dict() for ref in self.document_refs],
            "record_refs": [ref.to_dict() for ref in self.record_refs],
        }


@dataclass(frozen=True, slots=True)
class MethodologyCategoryGroup:
    """One fixed category section, including an explicitly empty section."""

    category: MethodologyCategory
    methods: tuple[MethodologyMethod, ...]

    @property
    def label(self) -> str:
        return CATEGORY_LABELS[self.category]


@dataclass(frozen=True, slots=True)
class MethodologyViewModel:
    """Deterministic, typed projection of a methodology ``ManagerReadModel``."""

    read_model: ManagerReadModel
    methods: tuple[MethodologyMethod, ...]
    groups: tuple[MethodologyCategoryGroup, ...]
    index_state: MethodologyIndexState = MethodologyIndexState.UNKNOWN

    @classmethod
    def from_read_model(cls, model: ManagerReadModel) -> MethodologyViewModel:
        payload = _mapping(model.data) or {}
        methods = _extract_methods(payload, model.source_refs)
        groups = tuple(
            MethodologyCategoryGroup(
                category=category,
                methods=tuple(method for method in methods if method.category is category),
            )
            for category in CATEGORY_ORDER
        )
        return cls(
            read_model=model,
            methods=methods,
            groups=groups,
            index_state=_index_state(payload),
        )

    @property
    def as_of(self) -> str | None:
        return self.read_model.as_of

    @property
    def snapshot_token(self) -> str | None:
        return self.read_model.snapshot_token

    @property
    def source_refs(self) -> tuple[SourceReference, ...]:
        return self.read_model.source_refs

    @property
    def methods_by_category(self) -> Mapping[MethodologyCategory, tuple[MethodologyMethod, ...]]:
        return {group.category: group.methods for group in self.groups}

    def category(self, category: MethodologyCategory | str) -> MethodologyCategoryGroup:
        selected = _category(category)
        return next(group for group in self.groups if group.category is selected)

    def to_dict(self) -> dict[str, object]:
        return {
            "index_state": self.index_state.value,
            "methods": [method.to_dict() for method in self.methods],
            "categories": [
                {"category": group.category.value, "methods": [m.method_id for m in group.methods]}
                for group in self.groups
            ],
            "availability": self.read_model.availability.to_dict(),
            "as_of": self.read_model.as_of,
            "snapshot_token": self.read_model.snapshot_token,
        }


# --- explicit parsing helpers -------------------------------------------------


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, field_name)


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
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


def _sequence(value: object) -> tuple[object, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, bytearray)):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(value)
    if isinstance(value, Mapping):
        for key in ("items", "entries", "records", "values", "methods"):
            candidate = value.get(key)
            if isinstance(candidate, Sequence) and not isinstance(
                candidate, (str, bytes, bytearray)
            ):
                return tuple(candidate)
        return (value,)
    return (value,)


def _normalise(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _category(value: object) -> MethodologyCategory:
    text = _text(value)
    if text is None:
        raise ValueError("methodology category is required")
    normalised = _normalise(text)
    try:
        return MethodologyCategory(normalised)
    except ValueError:
        try:
            return _CATEGORY_ALIASES[normalised]
        except KeyError as exc:
            raise ValueError(f"unknown methodology category: {text!r}") from exc


def _index_state(payload: Mapping[str, object]) -> MethodologyIndexState:
    raw = _first_text(payload, "index_state", "index_status", "catalog_state")
    if raw is None:
        return MethodologyIndexState.UNKNOWN
    try:
        return MethodologyIndexState(_normalise(raw))
    except ValueError:
        return MethodologyIndexState.UNKNOWN


def _ref_values(item: Mapping[str, object], *keys: str) -> tuple[object, ...]:
    values: list[object] = []
    for key in keys:
        raw = item.get(key)
        if raw is None:
            continue
        values.extend(_sequence(raw))
    return tuple(values)


def _source_refs(
    item: Mapping[str, object], envelope: Sequence[SourceReference]
) -> tuple[MethodologySourceRef, ...]:
    available = {source.source_id: source for source in envelope}
    raw_values = _ref_values(
        item, "source_refs", "source_ref", "source_ids", "source_id", "sources"
    )
    refs: list[MethodologySourceRef] = []
    seen: set[str] = set()
    for raw in raw_values:
        mapping = _mapping(raw)
        source_id = _first_text(mapping, "source_id", "sourceId", "id") if mapping else _text(raw)
        if source_id is None or source_id in seen:
            continue
        seen.add(source_id)
        source = available.get(source_id)
        if source is None:
            refs.append(MethodologySourceRef(source_id=source_id, available=False))
        else:
            refs.append(
                MethodologySourceRef(
                    source_id=source.source_id,
                    owner=source.owner,
                    kind=source.kind,
                    locator=source.locator,
                    schema=source.schema,
                    revision=source.revision,
                )
            )
    return tuple(refs)


def _document_refs(item: Mapping[str, object]) -> tuple[MethodologyDocumentRef, ...]:
    refs: list[MethodologyDocumentRef] = []
    seen: set[str] = set()
    for raw in _ref_values(item, "document_refs", "document_ref", "document_ids", "documents"):
        mapping = _mapping(raw)
        document_id = (
            _first_text(mapping, "document_id", "documentId", "id", "ref")
            if mapping
            else _text(raw)
        )
        if document_id is None or document_id in seen:
            continue
        seen.add(document_id)
        refs.append(
            MethodologyDocumentRef(
                document_id=document_id,
                title=_first_text(mapping, "title", "name", "label") if mapping else None,
                locator=_first_text(mapping, "locator", "url", "uri", "href") if mapping else None,
                revision=_first_text(mapping, "revision", "version") if mapping else None,
            )
        )
    return tuple(refs)


def _record_refs(item: Mapping[str, object]) -> tuple[MethodologyRecordRef, ...]:
    refs: list[MethodologyRecordRef] = []
    seen: set[str] = set()
    for raw in _ref_values(item, "record_refs", "record_ref", "record_ids"):
        mapping = _mapping(raw)
        record_id = (
            _first_text(mapping, "record_id", "recordId", "id", "ref") if mapping else _text(raw)
        )
        if record_id is None or record_id in seen:
            continue
        seen.add(record_id)
        refs.append(
            MethodologyRecordRef(
                record_id=record_id,
                label=_first_text(mapping, "title", "name", "label") if mapping else None,
                locator=_first_text(mapping, "locator", "url", "uri", "href") if mapping else None,
            )
        )
    return tuple(refs)


def _strings(item: Mapping[str, object], *keys: str) -> tuple[str, ...]:
    values: list[str] = []
    for raw in _ref_values(item, *keys):
        text = _text(raw)
        if text is not None:
            values.append(text)
        elif (mapping := _mapping(raw)) is not None:
            nested = _first_text(mapping, "summary", "detail", "description", "text", "message")
            if nested is not None:
                values.append(nested)
    return tuple(dict.fromkeys(values))


def _usage_records(
    item: Mapping[str, object], envelope: Sequence[SourceReference]
) -> tuple[MethodologyUsage, ...]:
    del envelope
    records: list[MethodologyUsage] = []
    for index, raw in enumerate(_sequence(item.get("usage_records", item.get("usages"))), start=1):
        mapping = _mapping(raw)
        if mapping is None:
            usage_id = _text(raw) or f"usage-{index}"
            records.append(MethodologyUsage(usage_id=usage_id))
            continue
        usage_id = (
            _first_text(mapping, "usage_id", "usageId", "id", "record_id") or f"usage-{index}"
        )
        records.append(
            MethodologyUsage(
                usage_id=usage_id,
                summary=_first_text(mapping, "summary", "description", "detail", "text"),
                used_at=_first_text(mapping, "used_at", "usedAt", "as_of", "date"),
                record_refs=_record_refs(mapping),
            )
        )
    return tuple(records)


def _results(item: Mapping[str, object]) -> tuple[MethodologyResult, ...]:
    results: list[MethodologyResult] = []
    for index, raw in enumerate(
        _sequence(item.get("associated_results", item.get("results"))), start=1
    ):
        mapping = _mapping(raw)
        if mapping is None:
            result_id = _text(raw) or f"result-{index}"
            results.append(MethodologyResult(result_id=result_id))
            continue
        result_id = (
            _first_text(mapping, "result_id", "resultId", "id", "record_id") or f"result-{index}"
        )
        results.append(
            MethodologyResult(
                result_id=result_id,
                title=_first_text(mapping, "title", "name", "label"),
                summary=_first_text(mapping, "summary", "description", "detail", "text"),
                status=_first_text(mapping, "status", "state", "outcome"),
                record_refs=_record_refs(mapping),
            )
        )
    return tuple(results)


def _validity_evidence(
    item: Mapping[str, object], envelope: Sequence[SourceReference]
) -> tuple[MethodologyValidityEvidence, ...]:
    evidence: list[MethodologyValidityEvidence] = []
    for index, raw in enumerate(_sequence(item.get("validity_evidence")), start=1):
        mapping = _mapping(raw)
        if mapping is None:
            evidence_id = _text(raw) or f"validity-evidence-{index}"
            evidence.append(MethodologyValidityEvidence(evidence_id=evidence_id))
            continue
        evidence_id = (
            _first_text(mapping, "evidence_id", "evidenceId", "id", "record_id")
            or f"validity-evidence-{index}"
        )
        evidence.append(
            MethodologyValidityEvidence(
                evidence_id=evidence_id,
                label=_first_text(mapping, "title", "name", "label"),
                summary=_first_text(mapping, "summary", "description", "detail", "text"),
                status=_first_text(mapping, "status", "state"),
                source_refs=_source_refs(mapping, envelope),
                document_refs=_document_refs(mapping),
                record_refs=_record_refs(mapping),
            )
        )
    return tuple(evidence)


def _explicit_superseded(item: Mapping[str, object]) -> bool | None:
    value = item.get("superseded")
    if isinstance(value, bool):
        return value
    status = _first_text(item, "superseded_status", "supersededState")
    if status is None:
        return None
    normalized = _normalise(status)
    if normalized in {"superseded", "retired"}:
        return True
    if normalized in {"current", "not_superseded", "active"}:
        return False
    return None


def _method_from_item(
    item: Mapping[str, object],
    category_hint: MethodologyCategory | None,
    envelope: Sequence[SourceReference],
) -> MethodologyMethod | None:
    method_id = _first_text(item, "method_id", "methodId", "id", "record_id", "uid")
    if method_id is None:
        return None
    category_value = _first_text(item, "category", "methodology_category", "kind", "type")
    selected_category = _category(category_value) if category_value is not None else category_hint
    if selected_category is None:
        return None
    usage_count: int | None = None
    raw_count = item.get(
        "usage_count",
        item.get("usageCount", item.get("usage_record_count", item.get("use_count"))),
    )
    if isinstance(raw_count, int) and not isinstance(raw_count, bool) and raw_count >= 0:
        usage_count = raw_count
    elif raw_count is not None:
        raise ValueError(f"usage_count for {method_id!r} must be a non-negative integer")
    return MethodologyMethod(
        method_id=method_id,
        title=_first_text(item, "title", "name", "label") or method_id,
        category=selected_category,
        definition=_first_text(item, "definition", "description", "summary"),
        version=_first_text(item, "version", "method_version", "revision"),
        usage_count=usage_count,
        usage_records=_usage_records(item, envelope),
        associated_results=_results(item),
        validity_evidence=_validity_evidence(item, envelope),
        limitations=_strings(item, "limitations", "limits"),
        failure_cases=_strings(item, "failure_cases", "failures", "failure_modes"),
        superseded=_explicit_superseded(item),
        superseded_by=_first_text(item, "superseded_by", "supersededBy"),
        source_refs=_source_refs(item, envelope),
        document_refs=_document_refs(item),
        record_refs=_record_refs(item),
        raw=item,
    )


def _method_items(
    payload: Mapping[str, object],
) -> tuple[tuple[MethodologyCategory | None, Mapping[str, object]], ...]:
    values: list[tuple[MethodologyCategory | None, Mapping[str, object]]] = []
    for key in ("methods", "methodologies", "entries"):
        raw = payload.get(key)
        if raw is None:
            continue
        for value in _sequence(raw):
            if (item := _mapping(value)) is not None:
                values.append((None, item))
    for key, category in _CATEGORY_ALIASES.items():
        if key not in payload:
            continue
        for value in _sequence(payload[key]):
            if (item := _mapping(value)) is not None:
                values.append((category, item))
    return tuple(values)


def _extract_methods(
    payload: Mapping[str, object], envelope: Sequence[SourceReference]
) -> tuple[MethodologyMethod, ...]:
    methods: list[MethodologyMethod] = []
    seen: set[str] = set()
    for category_hint, item in _method_items(payload):
        method = _method_from_item(item, category_hint, envelope)
        if method is not None and method.method_id not in seen:
            seen.add(method.method_id)
            methods.append(method)
    return tuple(methods)


# --- rendering ----------------------------------------------------------------


def _context_url(
    query_context: str | Mapping[str, object] | None,
    *,
    view: str,
    **updates: object,
) -> str:
    """Build a shell URL while retaining opaque query context."""

    return context_link(query_context, view=view, **updates)


def _is_methodology_fixture(model: ManagerReadModel) -> bool:
    """Recognize only the deterministic fixture provenance for display localization."""

    return any(
        source.owner == "methodology-catalog"
        and source.kind == "public-methodology-record"
        and source.locator == "fixture://methodology/catalog"
        and source.schema == "methodology.v0"
        and source.revision == "fixture-v0"
        for source in model.source_refs
    )


def _methodology_value(
    translator: Translator,
    key: str,
    value: str | None,
    *,
    fixture: bool,
) -> str:
    """Translate an authored fixture value, otherwise preserve owner text."""

    if value is None:
        return translator.t("methodology.missing")
    return translator.t(key) if fixture else value


def _fixture_methodology_text(
    translator: Translator,
    method_id: str,
    field: str,
    value: str | None,
    *,
    fixture: bool,
) -> str:
    """Translate only content from the exact deterministic methodology fixture."""

    if value is None:
        return translator.t("methodology.missing")
    key = f"methodology.fixture.{method_id.replace('-', '_')}.{field}"
    if fixture and key in _l3_method_history_catalog.ENTRIES:
        return translator.t(key)
    return value


def _methodology_status(
    translator: Translator, value: str | None, *, fixture: bool
) -> str:
    if value is None:
        return translator.t("methodology.missing")
    if fixture and value == "recorded":
        return translator.t("label.methodology.evidence_status.recorded")
    if fixture and value == "known":
        return translator.t("label.methodology.evidence_status.known")
    return value


def _render_ref_list(
    title: str,
    refs: Sequence[MethodologySourceRef | MethodologyDocumentRef | MethodologyRecordRef],
    *,
    translator: Translator,
    query_context: str | Mapping[str, object] | None = None,
    fixture: bool = False,
) -> str:
    if not refs:
        return f'<div class="methodology-ref-group"><dt>{escape(title)}</dt><dd>{escape(translator.t("methodology.missing"))}</dd></div>'
    items: list[str] = []
    for ref in refs:
        if isinstance(ref, MethodologySourceRef):
            label, target = ref.source_id, ref.locator
            link_kind = "source"
        elif isinstance(ref, MethodologyDocumentRef):
            label = ref.title or ref.document_id
            if fixture:
                key = f"methodology.fixture.{ref.document_id.replace('-', '_')}.title"
                if key in _l3_method_history_catalog.ENTRIES:
                    label = translator.t(key)
            target = (
                _context_url(
                    query_context,
                    view="source-documents",
                    document_id=ref.document_id,
                )
                if ref.available
                else None
            )
            link_kind = "document"
        else:
            label = ref.label or ref.record_id
            target = (
                _context_url(query_context, view="history", record_id=ref.record_id)
                if ref.available
                else None
            )
            link_kind = "record"
        if target:
            items.append(
                f'<li><a class="methodology-ref-link" data-link-kind="{link_kind}" '
                f'href="{escape(target, quote=True)}">{escape(label)}</a></li>'
            )
        else:
            items.append(f'<li>{escape(label)} — {escape(translator.t("methodology.missing"))}</li>')
    return f'<div class="methodology-ref-group"><dt>{escape(title)}</dt><dd><ul>{"".join(items)}</ul></dd></div>'


def _render_text_list(
    title: str,
    values: Sequence[str],
    *,
    missing: str = "None recorded",
    translator: Translator | None = None,
    method_id: str | None = None,
    field: str | None = None,
    fixture: bool = False,
) -> str:
    if not values:
        return (
            f'<div class="methodology-detail"><dt>{escape(title)}</dt><dd>{escape(missing)}</dd></div>'
        )
    items = "".join(
        f"<li>{escape(_fixture_methodology_text(translator, method_id, f'{field}.{index}', value, fixture=fixture) if translator and method_id and field else value)}</li>"
        for index, value in enumerate(values)
    )
    return (
        f'<div class="methodology-detail"><dt>{escape(title)}</dt><dd><ul>{items}</ul></dd></div>'
    )


def _render_method(
    method: MethodologyMethod,
    *,
    translator: Translator,
    fixture: bool,
    query_context: str | Mapping[str, object] | None = None,
) -> str:
    missing = translator.t("methodology.missing")
    usage_count = missing if method.usage_count is None else str(method.usage_count)
    version = method.version or missing
    if method.superseded is True:
        superseded = translator.t("label.methodology.superseded.superseded")
    elif method.superseded is False:
        superseded = translator.t("label.methodology.superseded.current")
    else:
        superseded = translator.t("label.methodology.superseded.unknown")
    superseded_by = (
        translator.t("methodology.superseded_by", method_id=method.superseded_by)
        if method.superseded_by
        else ""
    )
    usages = (
        f"<p>{escape(missing)}</p>"
        if not method.usage_records
        else "<ul>"
        + "".join(
            f'<li data-usage-id="{escape(usage.usage_id, quote=True)}">{escape(usage.summary or usage.usage_id)}'
            f"{f' · {escape(usage.used_at)}' if usage.used_at else ''}</li>"
            for usage in method.usage_records
        )
        + "</ul>"
    )
    results = (
        f"<p>{escape(missing)}</p>"
        if not method.associated_results
        else "<ul>"
        + "".join(
            f'<li data-result-id="{escape(result.result_id, quote=True)}">'
            f"{escape(_fixture_methodology_text(translator, method.method_id, 'result_title', result.title or result.result_id, fixture=fixture))}"
            f"{f' · {escape(result.status)}' if result.status else ''}"
            f"{f' — {escape(result.summary)}' if result.summary else ''}</li>"
            for result in method.associated_results
        )
        + "</ul>"
    )
    evidence = (
        f"<p>{escape(missing)}</p>"
        if not method.validity_evidence
        else "<ul>"
        + "".join(
            f'<li data-validity-evidence-id="{escape(item.evidence_id, quote=True)}">'
            f"{escape(_fixture_methodology_text(translator, method.method_id, 'evidence_label', item.label or item.evidence_id, fixture=fixture))}"
            f"{f' · {_methodology_status(translator, item.status, fixture=fixture)}' if item.status else ''}"
            f"{f' — {escape(item.summary)}' if item.summary else ''}</li>"
            for item in method.validity_evidence
        )
        + "</ul>"
    )
    return (
        f'<article class="methodology-method" data-method-id="{escape(method.method_id, quote=True)}" '
        f'data-methodology-category="{method.category.value}" '
        f'data-superseded="{"unknown" if method.superseded is None else str(method.superseded).lower()}">'
        f"<h3>{escape(_fixture_methodology_text(translator, method.method_id, 'title', method.title, fixture=fixture))}</h3>"
        '<dl class="methodology-details">'
        f'<div class="methodology-detail"><dt>{escape(translator.t("methodology.definition"))}</dt><dd>{escape(_fixture_methodology_text(translator, method.method_id, "definition", method.definition, fixture=fixture))}</dd></div>'
        f'<div class="methodology-detail"><dt>{escape(translator.t("methodology.version"))}</dt><dd>{escape(version)}</dd></div>'
        f'<div class="methodology-detail"><dt>{escape(translator.t("methodology.usage_count"))}</dt><dd>{escape(usage_count)}</dd></div>'
        f'<div class="methodology-detail"><dt>{escape(translator.t("methodology.superseded_status"))}</dt><dd>{escape(superseded)}{escape(superseded_by)}</dd></div>'
        f'<div class="methodology-detail"><dt>{escape(translator.t("methodology.usage_records"))}</dt><dd>{usages}</dd></div>'
        f'<div class="methodology-detail"><dt>{escape(translator.t("methodology.associated_results"))}</dt><dd>{results}</dd></div>'
        f'<div class="methodology-detail"><dt>{escape(translator.t("methodology.validity_evidence"))}</dt><dd>{evidence}</dd></div>'
        f"{_render_text_list(translator.t('methodology.limitations'), method.limitations, missing=missing, translator=translator, method_id=method.method_id, field='limitations', fixture=fixture)}"
        f"{_render_text_list(translator.t('methodology.failure_cases'), method.failure_cases, missing=missing, translator=translator, method_id=method.method_id, field='failure_cases', fixture=fixture)}"
        f"{_render_ref_list(translator.t('methodology.source_refs'), method.source_refs, translator=translator, query_context=query_context, fixture=fixture)}"
        f"{_render_ref_list(translator.t('methodology.document_refs'), method.document_refs, translator=translator, query_context=query_context, fixture=fixture)}"
        f"{_render_ref_list(translator.t('methodology.record_refs'), method.record_refs, translator=translator, query_context=query_context, fixture=fixture)}"
        "</dl></article>"
    )


def render_methodology(
    view_or_model: MethodologyViewModel | ManagerReadModel,
    *,
    query_context: str | Mapping[str, object] | None = None,
    translator: Translator | None = None,
) -> str:
    """Render a methodology archive fragment for a shared shell to mount."""

    selected_translator = translator or Translator()
    fixture = _is_methodology_fixture(view_or_model.read_model if isinstance(view_or_model, MethodologyViewModel) else view_or_model)
    view = (
        view_or_model
        if isinstance(view_or_model, MethodologyViewModel)
        else MethodologyViewModel.from_read_model(view_or_model)
    )
    model = view.read_model
    sources = ", ".join(source.source_id for source in model.source_refs) or selected_translator.t("methodology.missing")
    observed = model.as_of or selected_translator.t("shell.unavailable")
    snapshot = model.snapshot_token or selected_translator.t("shell.snapshot_missing")
    documents_url = _context_url(query_context, view="source-documents")
    history_url = _context_url(query_context, view="history")
    window = PageWindow.from_query(query_context, total=len(view.methods))
    paged_methods = view.methods[window.start : window.stop]
    paged_groups = tuple(
        (group, tuple(method for method in paged_methods if method.category is group.category))
        for group in view.groups
    )
    pieces = [
        '<section class="methodology-page" data-integration-hook="methodology-view" '
        f'data-index-state="{view.index_state.value}" data-boundary="canonical-fact">',
        f'<p class="eyebrow">{escape(selected_translator.t("methodology.eyebrow"))}</p>',
        f'<h1 class="page-title" data-page-title tabindex="-1">{escape(selected_translator.t("methodology.title"))}</h1>',
        f'<p class="page-intro">{escape(selected_translator.t("methodology.intro"))}</p>',
        f'<p class="boundary-note" data-boundary="canonical-fact">{selected_translator.html("methodology.boundary")}</p>',
        f'<nav class="methodology-related-nav" aria-label="{escape(selected_translator.t("methodology.related_aria"))}">'
        f'<a class="methodology-documents-link" href="{escape(documents_url, quote=True)}">{escape(selected_translator.t("documents.title"))}</a>'
        f'<a class="methodology-history-link" href="{escape(history_url, quote=True)}">{escape(selected_translator.t("history.title"))}</a></nav>',
        f'<p class="context-line methodology-context"><span><strong>{escape(selected_translator.t("shell.observed"))}</strong> {escape(observed)}</span>'
        f"<span><strong>{escape(selected_translator.t('shell.snapshot'))}</strong> {escape(snapshot)}</span><span><strong>{escape(selected_translator.t('shell.sources'))}</strong> {escape(sources)}</span></p>",
        render_status_block(model, translator=selected_translator),
    ]
    if view.index_state is MethodologyIndexState.NOT_INDEXED:
        pieces.append(
            render_operational_state(
                "error",
                translator=selected_translator,
                detail=selected_translator.t("methodology.not_indexed"),
            )
        )
    if not paged_methods and view.index_state is not MethodologyIndexState.NOT_INDEXED:
        if display_state_for(model) is DisplayState.ERROR:
            # A blocked/stale/incomparable/integrity-failed source has not proven an
            # empty scope, so the shared error state must not be relabeled as empty.
            pieces.append(
                render_operational_state(
                    DisplayState.ERROR,
                    translator=selected_translator,
                    detail=selected_translator.t("methodology.error_scope"),
                )
            )
        else:
            pieces.append(
                render_operational_state(
                    DisplayState.EMPTY,
                    translator=selected_translator,
                    detail=selected_translator.t("methodology.empty_scope"),
                )
            )
    for group, methods in paged_groups:
        body = (
            f'<p class="methodology-empty">{escape(selected_translator.t("methodology.empty_category"))}</p>'
            if not methods
            else "".join(_render_method(method, translator=selected_translator, fixture=fixture, query_context=query_context) for method in methods)
        )
        pieces.append(
            f'<section class="methodology-category" data-methodology-category="{group.category.value}" '
            f'aria-labelledby="methodology-category-{group.category.value}">'
            f'<h2 id="methodology-category-{group.category.value}">{escape(selected_translator.label("methodology.category", group.category.value))}</h2>{body}</section>'
        )
    pieces.append(window.render(query_context, view="methodology"))
    pieces.append("</section>")
    return "".join(pieces)


def methodology_view(
    provider: ManagerDataProvider,
    *,
    snapshot_token: str | None = None,
) -> MethodologyViewModel:
    """Read the approved ``methodology`` resource once and build its view model."""

    return MethodologyViewModel.from_read_model(
        provider.read(METHODOLOGY_RESOURCE, snapshot_token=snapshot_token)
    )


def render_methodology_view(
    source: ManagerDataProvider | ManagerReadModel,
    *,
    snapshot_token: str | None = None,
    query_context: str | Mapping[str, object] | None = None,
    translator: Translator | None = None,
) -> str:
    """S5-T3 integration hook accepting a provider or cached read model."""

    model = (
        source
        if isinstance(source, ManagerReadModel)
        else methodology_view(source, snapshot_token=snapshot_token).read_model
    )
    return render_methodology(
        model, query_context=query_context, translator=translator
    )


# --- deterministic fixtures ---------------------------------------------------


class MethodologyFixtureState(StrEnum):
    """Fixture states needed to exercise the S5-T1 page contract."""

    EMPTY = "empty"
    COMPLETE = "complete"
    PARTIAL = "partial"
    STALE = "stale"
    NOT_INDEXED = "not_indexed"


METHODOLOGY_FIXTURE_STATES = tuple(state.value for state in MethodologyFixtureState)


def _fixture_state(value: MethodologyFixtureState | str) -> MethodologyFixtureState:
    if isinstance(value, MethodologyFixtureState):
        return value
    return MethodologyFixtureState(_normalise(value))


def _fixture_source(source_id: str, locator: str) -> SourceReference:
    return SourceReference(
        source_id=source_id,
        owner="methodology-catalog",
        kind="public-methodology-record",
        locator=locator,
        schema="methodology.v0",
        revision="fixture-v0",
    )


def build_methodology_fixture(state: MethodologyFixtureState | str) -> ManagerReadModel:
    """Build a deterministic methodology envelope without filesystem access."""

    selected = _fixture_state(state)
    if selected is MethodologyFixtureState.EMPTY:
        return ManagerReadModel(
            data={},
            source_refs=(),
            as_of=None,
            snapshot_token=None,
            derivation=Derivation(kind="direct", version="methodology-fixture-v0"),
            availability=Availability(
                status=ReadModelStatus.MISSING,
                complete=False,
                reason="No methodology methods are present in the requested scope.",
            ),
        )
    if selected is MethodologyFixtureState.NOT_INDEXED:
        source = _fixture_source("methodology-index", "fixture://methodology/index")
        return ManagerReadModel(
            data={"index_state": "not_indexed"},
            source_refs=(source,),
            as_of=None,
            snapshot_token="methodology-not-indexed-v0",
            derivation=Derivation(kind="direct", inputs=(source.source_id,), version="v0"),
            availability=Availability(
                status=ReadModelStatus.API_UNAVAILABLE,
                complete=False,
                reason="The approved methodology document index is not indexed.",
                retryable=True,
            ),
            errors=(
                ReadModelError(
                    code="methodology_index_not_indexed",
                    message="No indexed methodology records are available.",
                    source_ref=source.source_id,
                    retryable=True,
                ),
            ),
        )

    source = _fixture_source("methodology-catalog", "fixture://methodology/catalog")
    methods: list[dict[str, object]] = [
        {
            "method_id": "g0",
            "title": "G0",
            "category": "workflow_process",
            "definition": "The declared research acceptance gate.",
            "version": "g0-v1",
            "usage_count": 12,
            "usage_records": [{"usage_id": "g0-use-1", "used_at": "2026-09-01"}],
            "associated_results": [{"result_id": "g0-result-1", "status": "recorded"}],
            "validity_evidence": [
                {
                    "evidence_id": "g0-evidence-1",
                    "label": "G0 acceptance record",
                    "status": "known",
                    "source_refs": [source.source_id],
                }
            ],
            "limitations": ["Does not replace owner qualification records."],
            "failure_cases": ["Required evidence may be missing."],
            "superseded": False,
            "source_refs": [source.source_id],
            "document_refs": [
                {"document_id": "doc-g0", "title": "G0 protocol", "locator": "fixture://docs/g0"}
            ],
            "record_refs": [{"record_id": "record-g0", "locator": "fixture://records/g0"}],
        },
        {
            "method_id": "golden-genome-flow",
            "title": "Golden Genome Flow",
            "category": "workflow_process",
            "definition": "The versioned genome research flow from candidate to evidence.",
            "version": "ggf-v2",
            "usage_count": 4,
            "associated_results": [{"result_id": "ggf-result-1", "title": "Flow audit"}],
            "validity_evidence": [],
            "limitations": ["Only the declared flow steps are covered."],
            "failure_cases": ["An unavailable step blocks the flow."],
            "superseded": True,
            "superseded_by": "golden-genome-flow-v3",
            "source_refs": [source.source_id],
            "document_refs": [
                {
                    "document_id": "doc-ggf",
                    "title": "Golden Genome Flow",
                    "locator": "fixture://docs/ggf",
                }
            ],
            "record_refs": [{"record_id": "record-ggf", "locator": "fixture://records/ggf"}],
        },
        {
            "method_id": "qualification-policy",
            "title": "Qualification policy",
            "category": "policy",
            "definition": "Rules for recording qualification decisions.",
            "version": "policy-v1",
            "usage_count": 3,
            "superseded": False,
            "source_refs": [source.source_id],
            "document_refs": [
                {"document_id": "doc-qualification", "locator": "fixture://docs/qualification"}
            ],
            "record_refs": [
                {"record_id": "record-qualification", "locator": "fixture://records/qualification"}
            ],
        },
        {
            "method_id": "memory-policy",
            "title": "Memory policy",
            "category": "policy",
            "definition": "Rules for preserving explicit research memory.",
            "version": "policy-v2",
            "usage_count": 8,
            "superseded": False,
            "source_refs": [source.source_id],
        },
        {
            "method_id": "visibility-policy",
            "title": "Visibility policy",
            "category": "policy",
            "definition": "Rules for what is visible to each read-only surface.",
            "version": "policy-v1",
            "usage_count": 5,
            "superseded": False,
            "source_refs": [source.source_id],
        },
        {
            "method_id": "currency-policy",
            "title": "Currency policy",
            "category": "policy",
            "definition": "Rules for current, stale, and revalidation-due evidence.",
            "version": "policy-v1",
            "usage_count": 6,
            "superseded": False,
            "source_refs": [source.source_id],
        },
        {
            "method_id": "frozen-statistical-protocol",
            "title": "Frozen statistical protocol",
            "category": "statistical_protocol",
            "definition": "The declared split, metrics, and comparison axes.",
            "version": "stats-v1",
            "usage_count": 2,
            "superseded": False,
            "source_refs": [source.source_id],
        },
        {
            "method_id": "baseline-benchmark",
            "title": "Baseline benchmark",
            "category": "benchmark",
            "definition": "The declared baseline used for comparison.",
            "version": "benchmark-v1",
            "usage_count": 2,
            "superseded": False,
            "source_refs": [source.source_id],
        },
        {
            "method_id": "data-gate-constraint",
            "title": "Data gate constraint",
            "category": "operational_constraint",
            "definition": "An explicit constraint that blocks claims when data is unavailable.",
            "version": "constraint-v1",
            "usage_count": 7,
            "superseded": False,
            "source_refs": [source.source_id],
        },
    ]
    if selected is MethodologyFixtureState.PARTIAL:
        methods = methods[:3]
        data: dict[str, object] = {"index_state": "indexed", "methods": methods}
        return ManagerReadModel(
            data=cast(JSONValue, data),
            source_refs=(source,),
            as_of="2026-10-03T09:00:00Z",
            snapshot_token="methodology-partial-v0",
            derivation=Derivation(kind="direct", inputs=(source.source_id,), version="v0"),
            availability=Availability(
                status=ReadModelStatus.KNOWN,
                complete=False,
                reason="Only part of the methodology catalog is indexed.",
            ),
            errors=(
                ReadModelError(
                    code="methodology_catalog_partial",
                    message="Some methodology categories are outside the indexed scope.",
                    source_ref=source.source_id,
                ),
            ),
        )
    if selected is MethodologyFixtureState.STALE:
        stale_data = {"index_state": "indexed", "methods": [methods[0], methods[1]]}
        return ManagerReadModel(
            data=cast(JSONValue, stale_data),
            source_refs=(source,),
            as_of="2025-01-01T00:00:00Z",
            snapshot_token="methodology-stale-v0",
            derivation=Derivation(kind="direct", inputs=(source.source_id,), version="v0"),
            availability=Availability(
                status=ReadModelStatus.STALE,
                complete=True,
                reason="The methodology catalog predates the current policy identity.",
            ),
            errors=(
                ReadModelError(
                    code="methodology_catalog_stale",
                    message="Historical methods are shown for reference, not current truth.",
                    source_ref=source.source_id,
                ),
            ),
        )
    return ManagerReadModel(
        data=cast(JSONValue, {"index_state": "indexed", "methods": methods}),
        source_refs=(source,),
        as_of="2026-10-03T09:00:00Z",
        snapshot_token="methodology-complete-v0",
        derivation=Derivation(kind="direct", inputs=(source.source_id,), version="v0"),
        availability=Availability(
            status=ReadModelStatus.KNOWN,
            complete=True,
            reason="The complete methodology fixture contains all five categories.",
        ),
    )


@dataclass(frozen=True, slots=True)
class MethodologyFixtureProvider:
    """Read-only provider for deterministic methodology fixtures."""

    state: MethodologyFixtureState

    def __init__(self, state: MethodologyFixtureState | str) -> None:
        object.__setattr__(self, "state", _fixture_state(state))

    def read(
        self,
        resource: str = METHODOLOGY_RESOURCE,
        *,
        snapshot_token: str | None = None,
    ) -> ManagerReadModel:
        if resource != METHODOLOGY_RESOURCE:
            raise ValueError(f"methodology fixture does not serve resource {resource!r}")
        del snapshot_token
        return build_methodology_fixture(self.state)


def methodology_fixture_provider(
    state: MethodologyFixtureState | str,
) -> MethodologyFixtureProvider:
    """Return a deterministic provider suitable for focused page tests."""

    return MethodologyFixtureProvider(state)


MethodologyFixture = MethodologyFixtureState
fixture_methodology_provider = methodology_fixture_provider
MethodologyEntry = MethodologyMethod
MethodologyArchiveViewModel = MethodologyViewModel


__all__ = [
    "CATEGORY_LABELS",
    "CATEGORY_ORDER",
    "METHODOLOGY_FIXTURE_STATES",
    "METHODOLOGY_INTEGRATION_HOOK",
    "METHODOLOGY_RESOURCE",
    "MethodologyArchiveViewModel",
    "MethodologyCategory",
    "MethodologyCategoryGroup",
    "MethodologyDocumentRef",
    "MethodologyEntry",
    "MethodologyFixture",
    "MethodologyFixtureProvider",
    "MethodologyFixtureState",
    "MethodologyIndexState",
    "MethodologyKind",
    "MethodologyMethod",
    "MethodologyRecordRef",
    "MethodologyResult",
    "MethodologySourceRef",
    "MethodologyUsage",
    "MethodologyValidityEvidence",
    "MethodologyViewModel",
    "build_methodology_fixture",
    "fixture_methodology_provider",
    "methodology_fixture_provider",
    "methodology_view",
    "render_methodology",
    "render_methodology_view",
]
