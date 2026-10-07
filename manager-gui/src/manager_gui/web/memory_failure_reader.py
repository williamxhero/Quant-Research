"""R4-T1 Reader projections for Research Memory and failure records.

This module is a read-only presentation adapter over the existing public Memory
and failure parsers.  It keeps Formal Research Memory, ordinary failure
records, and GUI-derived patterns as separate layers.  Reader claims use the
R1 typed envelope and fixed catalog templates; no prose is generated from a
language model and no source value is translated or rewritten.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from html import escape
from typing import TypeAlias, cast

from ..fixtures import FixtureState, build_fixture
from ..models import (
    Derivation,
    JSONValue,
    ManagerReadModel,
    ReadModelStatus,
    SourceReference,
)
from ..reader import (
    ClaimKind,
    FrozenJSON,
    ReaderAvailability,
    ReaderAvailabilityStatus,
    ReaderClaim,
    ReaderProjection,
    ReaderSummary,
    SampleData,
    project_read_model,
)
from .failure_lineage import FailureLineage
from .failure_patterns import (
    FailureExperience,
    FailureFilters,
    FailurePattern,
    FailureViewModel,
    render_failure_lineage,
)
from .i18n import Translator
from .i18n.catalog.reader import render_claim_explanation
from .locators import public_locator
from .memory import MemoryEntry, MemoryFilters, MemoryViewModel, render_memory_text
from .navigation import context_link, query_values
from .plain_memory import render_attempt, render_case_group
from .reader_surface import ReaderPage, render_reader_surface
from .source_support import source_support_entry, source_support_impact, suspend_source_support
from .status import display_state_for

# HTML fragments intentionally keep readable markup at the call site.
# ruff: noqa: E501

QueryContext: TypeAlias = str | Mapping[str, object] | None

MEMORY_READER_RESOURCE = "memory"
FAILURE_READER_RESOURCE = "failure_patterns"
MEMORY_READER_HOOK = "memory-reader-view"
FAILURE_READER_HOOK = "failure-reader-view"
MEMORY_FAILURE_READER_RULE = "manager-gui.reader.memory-failure.v1"
MEMORY_FAILURE_READER_VERSION = "v1"


class ReaderRecordLayer(StrEnum):
    FORMAL_MEMORY = "formal_research_memory"
    FAILURE_RECORD = "failure_record"
    GUI_DERIVED = "gui_derived"


class FailureReaderState(StrEnum):
    """Human-facing state; gaps never collapse into the FAILURE bucket."""

    SUCCESS = "success"
    FAILURE = "failure"
    BLOCKED = "blocked"
    NOT_EVALUATED = "not_evaluated"
    STALE = "stale"
    INCOMPARABLE = "incomparable"
    MISSING = "missing"
    UNKNOWN = "unknown"


_STATUS_TOKENS = {
    "blocked": FailureReaderState.BLOCKED,
    "not_evaluated": FailureReaderState.NOT_EVALUATED,
    "not-evaluated": FailureReaderState.NOT_EVALUATED,
    "unevaluated": FailureReaderState.NOT_EVALUATED,
    "stale": FailureReaderState.STALE,
    "incomparable": FailureReaderState.INCOMPARABLE,
    "missing": FailureReaderState.MISSING,
}
_SUCCESS_TOKENS = frozenset({"success", "succeeded", "passed", "pass", "accepted", "qualified", "completed"})
_FAILURE_TOKENS = frozenset({"failure", "failed", "rejected", "error", "execution_error", "execution-error"})


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


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


def _first(item: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        if (value := _text(item.get(key))) is not None:
            return value
    return None


def _normalise(value: object) -> str:
    return (_text(value) or "").strip().lower().replace("-", "_").replace(" ", "_")


def _json_value(value: object) -> JSONValue:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        return None
    return cast(JSONValue, value)


def _reader_availability(model: ManagerReadModel) -> ReaderAvailability:
    if model.availability.status is ReadModelStatus.KNOWN and not model.availability.complete:
        if any(error.code == "not_evaluated" for error in model.errors):
            return ReaderAvailability(
                ReaderAvailabilityStatus.NOT_EVALUATED,
                False,
                model.availability.reason,
            )
        return ReaderAvailability(
            ReaderAvailabilityStatus.KNOWN,
            False,
            model.availability.reason,
            model.availability.retryable,
        )
    return ReaderAvailability.from_v0(model.availability)


def _gap_kind(status: ReaderAvailabilityStatus) -> ClaimKind:
    if status in {ReaderAvailabilityStatus.BLOCKED, ReaderAvailabilityStatus.INTEGRITY_FAILURE}:
        return ClaimKind.BLOCKED
    if status is ReaderAvailabilityStatus.STALE:
        return ClaimKind.STALE
    if status is ReaderAvailabilityStatus.INCOMPARABLE:
        return ClaimKind.INCOMPARABLE
    return ClaimKind.MISSING


def _source_ids(raw: Mapping[str, object]) -> tuple[str, ...]:
    values: list[object] = []
    for key in (
        "source_id",
        "source_ref",
        "source_refs",
        "source_ids",
        "sources",
        "references",
        "lineage",
    ):
        if key not in raw:
            continue
        value = raw[key]
        if isinstance(value, Mapping):
            values.extend(value.values() if not any(name in value for name in ("source_id", "record_id", "id")) else (value,))
        elif isinstance(value, (str, int, float, bool)):
            values.append(value)
        else:
            values.extend(_sequence(value))
    result: list[str] = []
    for value in values:
        item = _mapping(value)
        source_id = _first(item, "source_id", "source_ref", "source", "record_id", "id") if item else _text(value)
        if source_id is not None and source_id not in result:
            result.append(source_id)
    return tuple(result)


def _state(raw: Mapping[str, object], model: ManagerReadModel) -> FailureReaderState:
    status = _normalise(_first(raw, "reader_status", "record_status", "status", "state"))
    if status in _STATUS_TOKENS:
        return _STATUS_TOKENS[status]
    if status in _SUCCESS_TOKENS:
        return FailureReaderState.SUCCESS
    if status in _FAILURE_TOKENS:
        return FailureReaderState.FAILURE
    outcome = _normalise(_first(raw, "outcome", "outcome_state", "result", "failure_outcome"))
    if outcome in _SUCCESS_TOKENS:
        return FailureReaderState.SUCCESS
    if outcome in _FAILURE_TOKENS:
        return FailureReaderState.FAILURE
    source_status = model.availability.status
    if source_status is ReadModelStatus.BLOCKED:
        return FailureReaderState.BLOCKED
    if source_status is ReadModelStatus.STALE:
        return FailureReaderState.STALE
    if source_status is ReadModelStatus.INCOMPARABLE:
        return FailureReaderState.INCOMPARABLE
    if source_status is ReadModelStatus.KNOWN and any(error.code == "not_evaluated" for error in model.errors):
        return FailureReaderState.NOT_EVALUATED
    if status is not None or outcome:
        return FailureReaderState.UNKNOWN
    return FailureReaderState.MISSING


def _status_for_state(state: FailureReaderState) -> ReaderAvailabilityStatus:
    return {
        FailureReaderState.BLOCKED: ReaderAvailabilityStatus.BLOCKED,
        FailureReaderState.NOT_EVALUATED: ReaderAvailabilityStatus.NOT_EVALUATED,
        FailureReaderState.STALE: ReaderAvailabilityStatus.STALE,
        FailureReaderState.INCOMPARABLE: ReaderAvailabilityStatus.INCOMPARABLE,
        FailureReaderState.MISSING: ReaderAvailabilityStatus.MISSING,
        FailureReaderState.UNKNOWN: ReaderAvailabilityStatus.MISSING,
    }.get(state, ReaderAvailabilityStatus.KNOWN)


@dataclass(frozen=True, slots=True)
class MemoryFailureReaderRecord:
    """A layer-labelled record used by both Memory and Failure Reader paths."""

    record_id: str
    title: str
    summary: str | None
    layer: ReaderRecordLayer
    state: FailureReaderState
    source_ids: tuple[str, ...]
    source_refs: tuple[SourceReference, ...]
    raw: Mapping[str, object] = field(default_factory=dict, repr=False, compare=False)
    memory_target_id: str | None = field(default=None, repr=False, compare=False)

    @property
    def memory_id(self) -> str | None:
        if self.layer is not ReaderRecordLayer.FORMAL_MEMORY:
            return None
        return self.memory_target_id or self.record_id

    @property
    def failure_id(self) -> str | None:
        return self.record_id if self.layer is ReaderRecordLayer.FAILURE_RECORD else None

    @property
    def pattern_id(self) -> str | None:
        return self.record_id if self.layer is ReaderRecordLayer.GUI_DERIVED else None

    @property
    def is_gap(self) -> bool:
        return self.state not in {FailureReaderState.SUCCESS, FailureReaderState.FAILURE, FailureReaderState.UNKNOWN}

    @property
    def derived(self) -> bool:
        return self.layer is ReaderRecordLayer.GUI_DERIVED

    def to_dict(self) -> dict[str, object]:
        return {
            "record_id": self.record_id,
            "title": self.title,
            "summary": self.summary,
            "layer": self.layer.value,
            "state": self.state.value,
            "source_ids": list(self.source_ids),
            "source_refs": [ref.to_dict() for ref in self.source_refs],
            "memory_id": self.memory_id,
        }


MemoryReaderRecord = MemoryFailureReaderRecord
FailureReaderRecord = MemoryFailureReaderRecord


def _record(
    raw: Mapping[str, object],
    model: ManagerReadModel,
    *,
    layer: ReaderRecordLayer,
    record_id: str,
    title: str,
    summary: str | None,
    memory_target_id: str | None = None,
) -> MemoryFailureReaderRecord:
    source_ids = _source_ids(raw)
    source_index = {ref.source_id: ref for ref in model.source_refs}
    source_refs = tuple(
        source_index[source_id] for source_id in source_ids if source_id in source_index
    )
    return MemoryFailureReaderRecord(
        record_id=record_id,
        title=title,
        summary=summary,
        layer=layer,
        state=_state(raw, model),
        source_ids=source_ids,
        source_refs=source_refs,
        raw=raw,
        memory_target_id=memory_target_id,
    )


def _memory_record(entry: MemoryEntry, model: ManagerReadModel) -> MemoryFailureReaderRecord:
    return _record(
        entry.raw,
        model,
        layer=ReaderRecordLayer.FORMAL_MEMORY,
        record_id=entry.memory_id,
        title=entry.title,
        summary=entry.safe_summary,
    )


def _failure_record(entry: FailureExperience, model: ManagerReadModel) -> MemoryFailureReaderRecord:
    return _record(
        entry.raw,
        model,
        layer=ReaderRecordLayer.FAILURE_RECORD,
        record_id=entry.failure_id,
        title=entry.title,
        summary=entry.summary,
    )


def _pattern_record(pattern: FailurePattern, model: ManagerReadModel) -> MemoryFailureReaderRecord:
    return _record(
        pattern.raw,
        model,
        layer=ReaderRecordLayer.GUI_DERIVED,
        record_id=pattern.pattern_id,
        title=pattern.title,
        summary=None,
    )


@dataclass(frozen=True, slots=True)
class MemoryReaderViewModel:
    """Combined typed view preserving all three Memory/Failure layers."""

    read_model: ManagerReadModel
    memory_view: MemoryViewModel
    failure_view: FailureViewModel
    records: tuple[MemoryFailureReaderRecord, ...]

    @classmethod
    def from_read_model(cls, model: ManagerReadModel) -> MemoryReaderViewModel:
        memory_view = MemoryViewModel.from_read_model(model)
        failure_view = FailureViewModel.from_read_model(model)
        records = tuple(
            _memory_record(entry, model) for entry in memory_view.entries
        ) + tuple(_failure_record(entry, model) for entry in failure_view.failures) + tuple(
            _pattern_record(pattern, model) for pattern in failure_view.patterns
        )
        return cls(model, memory_view, failure_view, records)

    @property
    def formal_memory(self) -> tuple[MemoryEntry, ...]:
        return self.memory_view.entries

    @property
    def failure_records(self) -> tuple[FailureExperience, ...]:
        return self.failure_view.failures

    @property
    def derived_patterns(self) -> tuple[FailurePattern, ...]:
        return self.failure_view.patterns

    @property
    def source_refs(self) -> tuple[SourceReference, ...]:
        return self.read_model.source_refs

    @property
    def empty(self) -> bool:
        return not self.records

    def to_dict(self) -> dict[str, object]:
        return {
            "formal_memory": [entry.to_dict() for entry in self.formal_memory],
            "failure_records": [entry.to_dict() for entry in self.failure_records],
            "derived_patterns": [pattern.to_dict() for pattern in self.derived_patterns],
            "records": [record.to_dict() for record in self.records],
        }


@dataclass(frozen=True, slots=True)
class FailureReaderViewModel:
    """Failure-focused view with formal memory and Derived kept addressable."""

    read_model: ManagerReadModel
    failure_view: FailureViewModel
    records: tuple[MemoryFailureReaderRecord, ...]

    @classmethod
    def from_read_model(cls, model: ManagerReadModel) -> FailureReaderViewModel:
        failure_view = FailureViewModel.from_read_model(model)
        records = tuple(_failure_record(entry, model) for entry in failure_view.failures)
        return cls(model, failure_view, records)

    @property
    def formal_memory(self) -> tuple[FailureExperience, ...]:
        return self.failure_view.memory_entries

    @property
    def derived_patterns(self) -> tuple[FailurePattern, ...]:
        return self.failure_view.patterns

    @property
    def source_refs(self) -> tuple[SourceReference, ...]:
        return self.read_model.source_refs

    @property
    def empty(self) -> bool:
        return not self.records and not self.formal_memory and not self.derived_patterns

    def to_dict(self) -> dict[str, object]:
        return {
            "formal_memory": [entry.to_dict() for entry in self.formal_memory],
            "failure_records": [record.to_dict() for record in self.records],
            "derived_patterns": [pattern.to_dict() for pattern in self.derived_patterns],
        }


MemoryFailureReaderViewModel = MemoryReaderViewModel


def _claim(
    model: ManagerReadModel,
    claim_id: str,
    value: JSONValue,
    *,
    kind: ClaimKind,
    status: ReaderAvailabilityStatus,
    rule: str | None = None,
    complete: bool = True,
    source_refs: Sequence[SourceReference] | None = None,
) -> ReaderClaim | None:
    refs = tuple(model.source_refs) if source_refs is None else tuple(source_refs)
    if not refs:
        return None
    source_ids = tuple(ref.source_id for ref in refs)
    derived = kind in {ClaimKind.DERIVED, ClaimKind.INTERPRETED}
    derivation = Derivation(
        "derived" if derived else "direct",
        rule if derived else None,
        source_ids,
        MEMORY_FAILURE_READER_VERSION if derived else "v0",
    )
    return ReaderClaim(
        claim_id,
        kind,
        refs,
        derivation,
        ReaderAvailability(status, complete, model.availability.reason, model.availability.retryable),
        cast(FrozenJSON, value),
    )


def _scope_gap(model: ManagerReadModel, claim_id: str) -> ReaderClaim | None:
    availability = _reader_availability(model)
    status = availability.status
    if status in {
        ReaderAvailabilityStatus.KNOWN,
        ReaderAvailabilityStatus.DERIVED,
        ReaderAvailabilityStatus.INTERPRETED,
    } and availability.complete:
        return None
    if status in {
        ReaderAvailabilityStatus.KNOWN,
        ReaderAvailabilityStatus.DERIVED,
        ReaderAvailabilityStatus.INTERPRETED,
    }:
        status = ReaderAvailabilityStatus.MISSING
    return _claim(
        model,
        claim_id,
        "reader.reason.scope_incomplete",
        kind=_gap_kind(status),
        status=status,
        complete=False,
    )


def _projection(
    model: ManagerReadModel,
    records: Sequence[MemoryFailureReaderRecord],
    *,
    resource: str,
    sample: bool,
    sample_state: str | None,
) -> ReaderProjection:
    claims: list[ReaderClaim] = []
    limitations: list[ReaderClaim] = []
    unknowns: list[ReaderClaim] = []
    scope_gap = _scope_gap(model, f"{resource}.read_scope")
    if scope_gap is not None:
        (unknowns if scope_gap.kind is ClaimKind.MISSING else limitations).append(scope_gap)
    else:
        for record in records:
            state = record.state
            status = _status_for_state(state)
            if state in {
                FailureReaderState.BLOCKED,
                FailureReaderState.STALE,
                FailureReaderState.INCOMPARABLE,
                FailureReaderState.NOT_EVALUATED,
                FailureReaderState.MISSING,
                FailureReaderState.UNKNOWN,
            }:
                gap = _claim(
                    model,
                    f"{resource}.{record.layer.value}.{record.record_id}.status",
                    record.record_id,
                    kind=_gap_kind(status),
                    status=status,
                    complete=False,
                    source_refs=record.source_refs,
                )
                if gap is not None:
                    (unknowns if gap.kind is ClaimKind.MISSING else limitations).append(gap)
                continue
            kind = ClaimKind.DERIVED if record.derived else ClaimKind.KNOWN
            fact = _claim(
                model,
                f"{resource}.{record.layer.value}.{record.record_id}",
                _json_value(record.raw),
                kind=kind,
                status=ReaderAvailabilityStatus.DERIVED if record.derived else ReaderAvailabilityStatus.KNOWN,
                rule=MEMORY_FAILURE_READER_RULE if record.derived else None,
                source_refs=record.source_refs,
            )
            if fact is not None:
                claims.append(fact)
            title = _claim(
                model,
                f"{resource}.{record.layer.value}.{record.record_id}.title",
                record.title,
                kind=ClaimKind.KNOWN,
                status=ReaderAvailabilityStatus.KNOWN,
                source_refs=record.source_refs,
            )
            if title is not None:
                claims.append(title)
    if not claims and not limitations and not unknowns:
        gap = _claim(
            model,
            f"{resource}.records",
            "reader.reason.record_missing",
            kind=ClaimKind.MISSING,
            status=ReaderAvailabilityStatus.MISSING,
            complete=False,
        )
        if gap is not None:
            unknowns.append(gap)
    ids = tuple(claim.claim_id for claim in (*claims, *limitations, *unknowns))
    summary = ReaderSummary(f"reader.{resource}.summary", ids, {"n": len(ids)}) if ids else None
    projection = project_read_model(
        model,
        summary=summary,
        claims=tuple(claims),
        limitations=tuple(limitations),
        unknowns=tuple(unknowns),
    )
    if sample:
        projection = replace(projection, sample_data=SampleData(sample_state or "complete", resource))
    return projection


def project_memory_reader(
    model: ManagerReadModel,
    *,
    sample: bool = False,
    sample_state: str | None = None,
) -> ReaderProjection:
    view = MemoryReaderViewModel.from_read_model(model)
    return _projection(model, view.records, resource=MEMORY_READER_RESOURCE, sample=sample, sample_state=sample_state)


def project_failure_reader(
    model: ManagerReadModel,
    *,
    sample: bool = False,
    sample_state: str | None = None,
) -> ReaderProjection:
    view = FailureReaderViewModel.from_read_model(model)
    records = tuple(view.records) + tuple(_pattern_record(pattern, model) for pattern in view.derived_patterns)
    return _projection(model, records, resource=FAILURE_READER_RESOURCE, sample=sample, sample_state=sample_state)


def build_memory_reader_fixture(state: FixtureState | str = FixtureState.COMPLETE) -> ManagerReadModel:
    return build_fixture(state, resource=MEMORY_READER_RESOURCE)


def build_failure_reader_fixture(state: FixtureState | str = FixtureState.COMPLETE) -> ManagerReadModel:
    return build_fixture(state, resource=MEMORY_READER_RESOURCE)


def _record_source_links(record: MemoryFailureReaderRecord, model: ManagerReadModel, *, translator: Translator) -> str:
    if not record.source_ids:
        return (
            f'<span class="memory-reader-source-missing">{translator.t("reader.memory.missing_source")}</span>'
            f' · <span class="memory-reader-lineage-missing">{translator.html("l4_memory.missing_link")}</span>'
        )
    index = {ref.source_id: ref for ref in model.source_refs}
    rendered: list[str] = []
    for source_id in record.source_ids:
        if support := source_support_entry(source_id, record=record.raw):
            rendered.append(support)
            continue
        source = index.get(source_id)
        if source is None:
            rendered.append(
                f'<span class="memory-reader-source-unconfirmed" translate="no">{escape(source_id)}</span>'
                f' · {translator.t("reader.memory.missing_source")} · '
                f'<span class="memory-reader-lineage-missing">{translator.html("l4_memory.missing_link")}</span>'
            )
            continue
        target = public_locator(source.locator)
        label = f'<span translate="no">{escape(source.source_id)}</span>'
        if target:
            rendered.append(f'<a class="memory-reader-source-link" href="{escape(target, quote=True)}">{label}</a>')
        else:
            rendered.append(
                f'<span class="memory-reader-source-unconfirmed">{label} · '
                f'{translator.t("reader.memory.missing_source")} · '
                f'<span class="memory-reader-lineage-missing">{translator.html("l4_memory.missing_link")}</span></span>'
            )
    return " · ".join(rendered)


def _record_boundary_details(
    record: MemoryFailureReaderRecord,
    model: ManagerReadModel,
    translator: Translator,
) -> str:
    """Expose owner-published Memory boundaries without deriving new prose."""

    fields = (
        ("where_produced", "reader.memory.where_produced"),
        ("produced_by", "reader.memory.where_produced"),
        ("origin", "reader.memory.where_produced"),
        ("production", "reader.memory.where_produced"),
        ("limitations", "reader.memory.limitations"),
        ("limitation", "reader.memory.limitations"),
        ("bounds", "reader.memory.limitations"),
        ("counterexample", "reader.memory.counterexample"),
        ("counterexamples", "reader.memory.counterexample"),
        ("conflicts", "reader.memory.counterexample"),
        ("lineage", "reader.memory.where_produced"),
    )
    rendered: list[str] = []
    seen: set[str] = set()
    for key, label_key in fields:
        value = record.raw.get(key)
        if value is None or value in ("", [], {}):
            continue
        if isinstance(value, str):
            content = render_memory_text(value, translator, model)
        else:
            content = (
                f'<span translate="no">{escape(json.dumps(value, ensure_ascii=False, sort_keys=True))}</span>'
            )
        if label_key in seen:
            continue
        seen.add(label_key)
        rendered.append(
            f'<div><dt>{escape(translator.t(label_key))}</dt><dd>{content}</dd></div>'
        )
    for label_key in (
        "reader.memory.where_produced",
        "reader.memory.limitations",
        "reader.memory.counterexample",
    ):
        if label_key in seen:
            continue
        rendered.append(
            f'<div><dt>{escape(translator.t(label_key))}</dt><dd>'
            f'<span class="memory-reader-boundary-missing">{escape(translator.t("reader.memory.not_recorded"))}</span></dd></div>'
        )
    return f'<dl class="memory-reader-boundaries">{"".join(rendered)}</dl>'


def _record_link(record: MemoryFailureReaderRecord, context: QueryContext) -> str:
    if record.layer is ReaderRecordLayer.FORMAL_MEMORY:
        return context_link(context, view="memory", memory_id=record.record_id)
    if record.layer is ReaderRecordLayer.GUI_DERIVED:
        return context_link(context, view="failure-patterns", pattern_id=record.record_id)
    return context_link(context, view="memory-failures", failure_id=record.record_id)


def _render_record(
    record: MemoryFailureReaderRecord,
    model: ManagerReadModel,
    *,
    context: QueryContext,
    translator: Translator,
    lineage: FailureLineage | None = None,
    pattern: FailurePattern | None = None,
    cases: Sequence[FailureExperience] = (),
    sample: bool = False,
) -> str:
    if pattern is not None:
        inputs = tuple(
            (identifier, matches[0].raw if len(matches := [item for item in cases if item.failure_id == identifier]) == 1 else None)
            for identifier in pattern.failure_ids
        )
        readable = render_case_group(
            record.raw, translator=translator, rule=pattern.rule, scope=pattern.input_scope,
            sample_count=pattern.sample_count, inputs=inputs, query_context=str(context or ""),
            complete=model.availability.complete, sample=sample,
        )
    else:
        readable = render_attempt(
            record.raw, translator=translator, lesson=record.layer is ReaderRecordLayer.FORMAL_MEMORY,
            sample=sample,
        )
    with suspend_source_support():
        technical = _render_technical_record(record, model, context=context, translator=translator, lineage=lineage)
    return readable + f'<details><summary>{translator.html("plain.memory.technical")}</summary>{technical}</details>'


def _render_technical_record(
    record: MemoryFailureReaderRecord, model: ManagerReadModel, *,
    context: QueryContext, translator: Translator, lineage: FailureLineage | None,
) -> str:
    claim_kind = "derived" if record.derived else "known"
    claim_copy = translator.html(
        "reader.claim.derived" if record.derived else "reader.claim.known"
    )
    state_copy = translator.html(f"reader.failure.state.{record.state.value}")
    layer_copy = translator.html(f"reader.memory.layer.{record.layer.value}")
    title = render_memory_text(record.title, translator, model)
    summary = (
        f'<p class="memory-reader-record-summary">{render_memory_text(record.summary, translator, model)}</p>'
        if record.summary is not None
        else ""
    )
    if record.layer is ReaderRecordLayer.FORMAL_MEMORY:
        lineage_link = f'<p class="memory-reader-lineage-link"><a href="{escape(context_link(context, view="memory-failures", failure_id=record.record_id), quote=True)}">{translator.html("l4_memory.open_memory_failure")}</a></p>'
    elif record.layer is ReaderRecordLayer.GUI_DERIVED:
        lineage_link = f'<p class="memory-reader-lineage-link"><a href="{escape(context_link(context, view="failure-patterns", pattern_id=record.record_id), quote=True)}">{translator.html("l4_memory.failure_patterns_open")}</a></p>'
    else:
        lineage_link = ""
    lineage_markup = (
        render_failure_lineage(
            lineage,
            translator=translator,
            query_context=context,
            model=model,
        )
        if lineage is not None
        else ""
    )
    pattern_attribute = ' data-pattern-status="derived"' if record.derived else ""
    return (
        f'<article class="memory-reader-record" data-record-id="{escape(record.record_id, quote=True)}" data-record-layer="{record.layer.value}" data-memory-authority="{record.layer.value}" data-record-state="{record.state.value}" data-claim-kind="{claim_kind}"{pattern_attribute}>'
        f'<h3><a class="failure-reader-detail-link" href="{escape(_record_link(record, context), quote=True)}">{title}</a></h3>'
        f'<p class="memory-reader-layer"><strong>{escape(translator.t("reader.memory.layer_label"))}</strong> {layer_copy}</p>'
        f'<p class="memory-reader-state"><strong>{escape(translator.t("reader.failure.state_label"))}</strong> {state_copy}</p>'
        f'{summary}<p class="memory-reader-claim-explanation">{claim_copy}</p>'
        f'{_record_boundary_details(record, model, translator)}'
        f'<p class="memory-reader-sources"><strong>{escape(translator.t("reader.source"))}</strong> {_record_source_links(record, model, translator=translator)}</p>'
        f'<p class="memory-reader-record-link"><a href="{escape(_record_link(record, context), quote=True)}">{escape(translator.t("reader.memory.open_record"))}</a></p>{lineage_link}{lineage_markup}</article>'
    )


def _render_claims(projection: ReaderProjection, *, translator: Translator) -> str:
    if not projection.claims:
        return f'<p class="memory-reader-no-claims">{escape(translator.t("reader.no_conclusion"))}</p>'
    return "".join(
        f'<li data-claim-id="{escape(claim.claim_id, quote=True)}" data-claim-kind="{claim.kind.value}">{render_claim_explanation(translator, claim, as_html=True)}</li>'
        for claim in projection.claims
    )


def _render_gaps(projection: ReaderProjection, *, translator: Translator) -> str:
    gaps = (*projection.limitations, *projection.unknowns)
    if not gaps:
        return f'<p class="memory-reader-no-gaps">{escape(translator.t("reader.no_gaps"))}</p>'
    return "".join(
        f'<li data-gap-kind="{claim.kind.value}" data-availability="{claim.availability.status.value}">{render_claim_explanation(translator, claim, as_html=True)}</li>'
        for claim in gaps
    )


def _render_page(
    view: MemoryReaderViewModel | FailureReaderViewModel,
    projection: ReaderProjection,
    *,
    context: QueryContext,
    translator: Translator,
    failure_only: bool,
    page: ReaderPage,
) -> str:
    model = view.read_model
    records = view.records
    if failure_only and isinstance(view, FailureReaderViewModel):
        formal_records = tuple(
            _record(
                entry.raw,
                model,
                layer=ReaderRecordLayer.FORMAL_MEMORY,
                record_id=entry.memory_id,
                title=entry.title,
                summary=entry.summary,
                memory_target_id=entry.memory_id,
            )
            for entry in view.formal_memory
        )
        records = (
            formal_records
            + tuple(view.records)
            + tuple(_pattern_record(pattern, model) for pattern in view.derived_patterns)
        )
    # Apply the existing public parser's exact filters only to its own layer.
    memory_ids = {entry.memory_id for entry in MemoryViewModel.from_read_model(model, filters=MemoryFilters.from_query(context)).entries}
    failure_ids = {entry.failure_id for entry in FailureViewModel.from_read_model(model, filters=FailureFilters.from_query(context)).failures}
    records = tuple(record for record in records if (
        record.layer is ReaderRecordLayer.GUI_DERIVED
        or (record.layer is ReaderRecordLayer.FORMAL_MEMORY and record.record_id in memory_ids)
        or (record.layer is ReaderRecordLayer.FAILURE_RECORD and record.record_id in failure_ids)
    ))
    selected = query_values(context)
    if selected.get("pattern_id"):
        records = tuple(record for record in records if record.derived and record.record_id == selected["pattern_id"])
    elif identifier := selected.get("failure_id") or selected.get("memory_id"):
        records = tuple(record for record in records if not record.derived and record.record_id == identifier)
    elif identifier := selected.get("record_id"):
        records = tuple(record for record in records if record.record_id == identifier)
    title_key = "reader.failure.title" if failure_only else "reader.memory.title"
    banner = ""
    if projection.sample_data is not None:
        banner = f'<aside class="memory-reader-sample-banner" data-sample-banner="fixture" role="note">{escape(translator.t("reader.sample.banner.fixed"))}</aside>'
    empty = not records
    display_state = display_state_for(model).value
    empty_scope = empty and (
        model.availability.status is ReadModelStatus.MISSING
        or (
            model.availability.status is ReadModelStatus.KNOWN
            and model.availability.complete
        )
    )
    if empty and failure_only and empty_scope:
        empty_message = f'<p data-memory-empty="true" data-display-state="empty">{translator.html("l4_memory.no_formal_memory")}</p>'
    elif empty and empty_scope:
        explicit_memory_payload = (
            isinstance(view, MemoryReaderViewModel)
            and view.memory_view.explicit_memory_payload
        )
        empty_key = (
            "l4_memory.no_formal_memory_scope"
            if explicit_memory_payload
            else "l4_memory.no_formal_memory"
        )
        empty_message = f'<p data-memory-empty="true" data-display-state="empty">{translator.html(empty_key)}</p>'
    elif empty:
        status = translator.t("label.status." + model.availability.status.value)
        empty_message = f'<p data-memory-empty="true" data-memory-empty-state="not-determined" data-display-state="{display_state}">{translator.html("l4_memory.memory_not_determined", status=status)}</p>'
    else:
        empty_message = ""
    partial_message = (
        f'<p class="memory-partial-note">{translator.html("l4_memory.partial_memory_scope")}</p>'
        if model.availability.status is ReadModelStatus.KNOWN and not model.availability.complete
        else ""
    )
    lineage_by_id: dict[str, FailureLineage] = {}
    if isinstance(view, FailureReaderViewModel):
        lineage_by_id.update(
            {entry.memory_id: entry.lineage for entry in view.formal_memory}
        )
        lineage_by_id.update(
            {entry.failure_id: entry.lineage for entry in view.failure_view.failures}
        )
        lineage_by_id.update(
            {pattern.pattern_id: pattern.lineage for pattern in view.derived_patterns}
        )
    rendered_lineages = tuple(
        lineage_by_id[record.record_id]
        for record in records
        if record.record_id in lineage_by_id
    )
    layer_summary = (
        f'<p class="memory-reader-layer-summary">'
        f'<span data-memory-layer="formal-research-memory">{escape(translator.t("reader.memory.layer.formal_research_memory"))}</span> · '
        f'<span data-memory-layer="failure-record">{escape(translator.t("l4_memory.ordinary_failure_records"))}</span> · '
        f'<span data-memory-layer="gui-derived">{escape(translator.t("reader.memory.layer.gui_derived"))}</span></p>'
        if failure_only
        else ""
    )
    patterns_by_id = {item.pattern_id: item for item in view.derived_patterns}
    # Keep the original navigation capabilities available without explaining unrelated siblings.
    technical_navigation = "".join(
        f'<p><a href="{escape(context_link(context, view="failure-patterns", pattern_id=item.pattern_id, memory_id=None, failure_id=None, record_id=None), quote=True)}">{translator.html("l4_memory.open_derived_pattern")}</a></p>'
        for item in view.derived_patterns
    ) + "".join(
        f'<p><a href="{escape(context_link(context, view="memory", memory_id=item.memory_id, pattern_id=None, failure_id=None, record_id=None), quote=True)}">{translator.html("l4_memory.open_memory")}</a></p>'
        for item in view.formal_memory if item.memory_id is not None
    ) + "".join(
        f'<p><a href="{escape(context_link(context, view="memory-failures", failure_id=identifier, memory_id=None, pattern_id=None, record_id=None), quote=True)}">{translator.html("l4_memory.open_memory_failure")}</a></p>'
        for item in view.derived_patterns for identifier in item.failure_ids
    )
    details = (
        f'<section class="memory-reader-records" aria-labelledby="memory-reader-records-title">'
        f'<details><summary>{translator.html("plain.memory.technical")}</summary>{layer_summary}{technical_navigation}</details>'
        f'<h2 id="memory-reader-records-title">{escape(translator.t(title_key))}</h2>'
        f'{translator.html("plain.memory.missing") if empty else ""}{empty_message}{partial_message}'
        f'{"".join(_render_record(record, model, context=context, translator=translator, lineage=lineage_by_id.get(record.record_id), pattern=patterns_by_id.get(record.record_id) if record.derived else None, cases=view.failure_view.all_failures, sample=projection.sample_data is not None) for record in records)}'
        f'</section>'
        f'<details class="memory-reader-raw"><summary>{escape(translator.t("reader.raw_source"))}</summary>'
        f'<pre translate="no">{translator.source_text(model.to_json())}</pre></details>'
    )
    with suspend_source_support():
        surface = render_reader_surface(
            projection, page=page, query_context=context, translator=translator,
        )
    empty_sources = "".join(source_support_entry(ref.source_id) or "" for ref in model.source_refs) if empty else ""
    memory_state = (
        "empty"
        if empty_scope
        else "not-determined"
        if empty
        else "ready"
    )
    integration_hook = "failure-patterns-view" if failure_only else "memory-view"
    lineage_coverage = ""
    if failure_only and rendered_lineages:
        coverage_values = tuple(lineage.coverage for lineage in rendered_lineages)
        lineage_coverage = (
            "complete"
            if all(value == "complete" for value in coverage_values)
            else "partial"
            if any(value == "partial" for value in coverage_values)
            else "missing"
        )
    lineage_attribute = (
        f' data-lineage-coverage="{lineage_coverage}"'
        if lineage_coverage
        else ""
    )
    memory_layer = (
        ' data-memory-layer="formal-research-memory"'
        if failure_only and view.formal_memory
        else ""
    )
    return (
        f'<section class="memory-failure-reader-page" data-reader-hook="memory-failure-reader" '
        f'data-integration-hook="{integration_hook}"{memory_layer}{lineage_attribute} '
        f'data-reader-resource="{"failure" if failure_only else "memory"}" '
        f'data-status="{escape(model.availability.status.value, quote=True)}" '
        f'data-display-state="{display_state}" data-memory-state="{memory_state}">'
        f'<h1>{escape(translator.t(title_key))}</h1>{banner}{source_support_impact()}{details}{empty_sources}'
        f'<details><summary>{translator.html("plain.memory.technical")}</summary>{surface}</details></section>'
    )


def render_memory_reader(
    view_or_model: MemoryReaderViewModel | ManagerReadModel,
    *,
    query_context: QueryContext = None,
    translator: Translator | None = None,
    projection: ReaderProjection | None = None,
) -> str:
    selected = translator or Translator()
    view = view_or_model if isinstance(view_or_model, MemoryReaderViewModel) else MemoryReaderViewModel.from_read_model(view_or_model)
    return _render_page(
        view,
        projection or project_memory_reader(view.read_model),
        context=query_context,
        translator=selected,
        failure_only=False,
        page=ReaderPage.MEMORY,
    )


def render_failure_reader(
    view_or_model: FailureReaderViewModel | ManagerReadModel,
    *,
    query_context: QueryContext = None,
    translator: Translator | None = None,
    projection: ReaderProjection | None = None,
    page: ReaderPage = ReaderPage.FAILURE,
) -> str:
    selected = translator or Translator()
    view = view_or_model if isinstance(view_or_model, FailureReaderViewModel) else FailureReaderViewModel.from_read_model(view_or_model)
    return _render_page(
        view,
        projection or project_failure_reader(view.read_model),
        context=query_context,
        translator=selected,
        failure_only=True,
        page=page,
    )


def render_failure_patterns_reader(
    view_or_model: FailureReaderViewModel | ManagerReadModel,
    *,
    query_context: QueryContext = None,
    translator: Translator | None = None,
    projection: ReaderProjection | None = None,
) -> str:
    return render_failure_reader(
        view_or_model,
        query_context=query_context,
        translator=translator,
        projection=projection,
        page=ReaderPage.FAILURE_PATTERNS,
    )


# Discoverable aliases parallel the Strategy/Genome Reader seam.
project_memory_failure_reader = project_memory_reader
render_memory_failure_reader = render_failure_reader
render_memory_failure_reader_view = render_failure_reader
render_failure_reader_view = render_failure_reader
MemoryFailureReaderView = MemoryReaderViewModel
FailureReaderView = FailureReaderViewModel

__all__ = [
    "FAILURE_READER_HOOK",
    "FAILURE_READER_RESOURCE",
    "MEMORY_FAILURE_READER_RULE",
    "MEMORY_FAILURE_READER_VERSION",
    "MEMORY_READER_HOOK",
    "MEMORY_READER_RESOURCE",
    "FailureReaderRecord",
    "FailureReaderState",
    "FailureReaderView",
    "FailureReaderViewModel",
    "MemoryFailureReaderRecord",
    "MemoryFailureReaderView",
    "MemoryFailureReaderViewModel",
    "MemoryReaderRecord",
    "MemoryReaderViewModel",
    "ReaderRecordLayer",
    "build_failure_reader_fixture",
    "build_memory_reader_fixture",
    "project_failure_reader",
    "project_memory_failure_reader",
    "project_memory_reader",
    "render_failure_patterns_reader",
    "render_failure_reader",
    "render_failure_reader_view",
    "render_memory_failure_reader",
    "render_memory_failure_reader_view",
    "render_memory_reader",
]
