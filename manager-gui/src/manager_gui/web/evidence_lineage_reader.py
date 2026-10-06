"""Typed, read-only Evidence and Lineage trace Reader.

This module is an additive Reader seam over the existing Evidence Ledger and
Lineage expert projections.  It does not change the v0 envelope, call an LLM,
read private storage, or infer a relation that is not published.  Reader mode
uses a source-chain/table explanation; the existing graph renderer is mounted
only when ``mode=expert`` is requested.
"""

# HTML fragments intentionally remain readable at the call site.
# ruff: noqa: E501

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from html import escape
from typing import TypeAlias, cast

from ..models import Derivation, JSONValue, ManagerReadModel, ReadModelStatus, SourceReference
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
from .evidence import (
    _FIXTURE_TEXT_KEYS,
    EvidenceArtifact,
    EvidenceKind,
    EvidenceOutcome,
    EvidenceRecord,
    EvidenceViewModel,
)
from .i18n import Translator
from .i18n.catalog import CATALOG, CatalogError
from .i18n.catalog.l4_evidence_lineage_reader import ENTRIES as READER_ENTRIES
from .i18n.catalog.l4_lineage import ENTRIES as LINEAGE_ENTRIES
from .i18n.catalog import merge
from .lineage import LineageQuery, LineageViewModel, render_lineage
from .locators import public_locator
from .navigation import ViewId, context_link
from .reader_surface import ReaderPage, render_reader_surface

QueryContext: TypeAlias = str | Mapping[str, object] | None

EVIDENCE_LINEAGE_READER_RESOURCE = "evidence"
EVIDENCE_LINEAGE_READER_RULE = "manager-gui.reader.evidence-lineage.v1"
EVIDENCE_LINEAGE_READER_VERSION = "v1"
EVIDENCE_LINEAGE_READER_HOOK = "evidence-lineage-reader"


class ReaderTraceMode(StrEnum):
    """Presentation modes; the underlying read model is identical in each."""

    READER = "reader"
    EXPERT = "expert"
    RAW = "raw"


class TraceStepKind(StrEnum):
    CONCLUSION = "conclusion"
    EVIDENCE = "evidence"
    SOURCE = "source"
    ARTIFACT = "artifact"
    LINEAGE = "lineage"


@dataclass(frozen=True, slots=True)
class EvidenceTraceStep:
    """One trace step with explicit owner scope, derivation, and availability."""

    step_id: str
    kind: TraceStepKind
    label: str
    value: JSONValue | None
    source_refs: tuple[SourceReference, ...]
    derivation: Derivation
    availability: ReaderAvailability
    evidence_kind: EvidenceKind | None = None
    status: EvidenceOutcome | None = None
    locator: str | None = None
    recorded: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "step_id": self.step_id,
            "kind": self.kind.value,
            "label": self.label,
            "value": self.value,
            "source_refs": [ref.to_dict() for ref in self.source_refs],
            "derivation": self.derivation.to_dict(),
            "availability": self.availability.to_dict(),
            "evidence_kind": None if self.evidence_kind is None else self.evidence_kind.value,
            "status": None if self.status is None else self.status.value,
            "locator": self.locator,
            "recorded": self.recorded,
        }


@dataclass(frozen=True, slots=True)
class LineageRelationExplanation:
    """A published relation and its separately tracked explanation boundary."""

    relation_id: str
    source_id: str
    target_id: str
    relation: str | None
    why: str | None
    recorded: bool
    source_refs: tuple[SourceReference, ...]
    derivation: Derivation
    availability: ReaderAvailability
    why_availability: ReaderAvailability

    def to_dict(self) -> dict[str, object]:
        return {
            "relation_id": self.relation_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation": self.relation,
            "why": self.why,
            "recorded": self.recorded,
            "source_refs": [ref.to_dict() for ref in self.source_refs],
            "derivation": self.derivation.to_dict(),
            "availability": self.availability.to_dict(),
            "why_availability": self.why_availability.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class EvidenceLineageReaderViewModel:
    """Immutable Reader view composed from one Evidence envelope and optional Lineage envelope."""

    read_model: ManagerReadModel
    evidence: EvidenceViewModel
    lineage: LineageViewModel | None
    steps: tuple[EvidenceTraceStep, ...]
    relations: tuple[LineageRelationExplanation, ...]
    gaps: tuple[ReaderClaim, ...]
    lineage_scope_recorded: bool

    @classmethod
    def from_read_model(
        cls,
        model: ManagerReadModel,
        *,
        lineage_model: ManagerReadModel | None = None,
        query_context: QueryContext = None,
    ) -> EvidenceLineageReaderViewModel:
        evidence = EvidenceViewModel.from_read_model(model)
        source_index = {ref.source_id: ref for ref in model.source_refs}
        scope = _scope_availability(model)
        steps: list[EvidenceTraceStep] = []

        conclusion = evidence.conclusion
        steps.append(
            _step(
                "evidence.conclusion",
                TraceStepKind.CONCLUSION,
                conclusion or "",
                conclusion,
                model.source_refs,
                model=model,
                availability=scope if conclusion is not None else _missing_availability("conclusion"),
                recorded=conclusion is not None,
            )
        )
        for record in evidence.records:
            refs = _refs_for_evidence(record.source_refs, source_index, model.source_refs)
            availability = _record_availability(record, scope)
            steps.append(
                _step(
                    f"evidence.{record.evidence_kind.value}.{record.record_id}",
                    TraceStepKind.EVIDENCE,
                    record.label,
                    cast(JSONValue, record.to_dict()),
                    refs,
                    model=model,
                    availability=availability,
                    evidence_kind=record.evidence_kind,
                    status=record.status,
                    recorded=True,
                )
            )
            for artifact in record.artifacts:
                _append_artifact_step(steps, artifact, source_index, model, scope)
        for artifact in evidence.artifacts:
            if not any(step.kind is TraceStepKind.ARTIFACT and step.step_id.endswith(artifact.artifact_id) for step in steps):
                _append_artifact_step(steps, artifact, source_index, model, scope)

        seen_sources: set[str] = set()
        for source in evidence.sources:
            if source.source_id in seen_sources:
                continue
            seen_sources.add(source.source_id)
            canonical = source_index.get(source.source_id)
            if canonical is None:
                continue
            steps.append(
                _step(
                    f"evidence.source.{source.source_id}",
                    TraceStepKind.SOURCE,
                    source.source_id,
                    cast(JSONValue, source.to_dict()),
                    (canonical,),
                    model=model,
                    availability=scope if source.available else _missing_availability("source"),
                    locator=source.locator,
                )
            )
        for source in model.source_refs:
            if source.source_id not in seen_sources:
                steps.append(
                    _step(
                        f"evidence.source.{source.source_id}",
                        TraceStepKind.SOURCE,
                        source.source_id,
                        cast(JSONValue, source.to_dict()),
                        (source,),
                        model=model,
                        availability=scope,
                        locator=source.locator,
                    )
                )

        selected_lineage: LineageViewModel | None = None
        if lineage_model is not None:
            selected_lineage = LineageViewModel.from_read_model(
                lineage_model, LineageQuery.from_query(query_context)
            )
        nested_relations = _nested_relations(model.data, source_index, model.source_refs)
        if selected_lineage is not None and selected_lineage.nodes:
            relations = _relations_from_lineage(selected_lineage, source_index, model.source_refs, scope)
            lineage_scope_recorded = True
        elif nested_relations:
            relations = nested_relations
            lineage_scope_recorded = True
        else:
            relations = ()
            lineage_scope_recorded = False

        gaps = _build_gaps(model, steps, relations, lineage_scope_recorded)
        return cls(model, evidence, selected_lineage, tuple(steps), tuple(relations), gaps, lineage_scope_recorded)

    @property
    def source_refs(self) -> tuple[SourceReference, ...]:
        return self.read_model.source_refs

    @property
    def availability(self) -> ReaderAvailability:
        return _scope_availability(self.read_model)

    @property
    def as_of(self) -> str | None:
        return self.read_model.as_of

    @property
    def snapshot_token(self) -> str | None:
        return self.read_model.snapshot_token

    @property
    def raw_json(self) -> str:
        return self.read_model.to_json()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.read_model.schema,
            "steps": [step.to_dict() for step in self.steps],
            "relations": [relation.to_dict() for relation in self.relations],
            "lineage_scope_recorded": self.lineage_scope_recorded,
            "availability": self.availability.to_dict(),
            "source_refs": [ref.to_dict() for ref in self.source_refs],
            "as_of": self.as_of,
            "snapshot_token": self.snapshot_token,
        }


EvidenceLineageReaderView = EvidenceLineageReaderViewModel
EvidenceTraceReaderViewModel = EvidenceLineageReaderViewModel


def _mapping(value: object) -> Mapping[str, object] | None:
    return cast(Mapping[str, object], value) if isinstance(value, Mapping) else None


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, Mapping):
        return (value,)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(value)
    return ()


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _first(item: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        if (value := _text(item.get(key))) is not None:
            return value
    return None


def _scope_availability(model: ManagerReadModel) -> ReaderAvailability:
    payload = _mapping(model.data) or {}
    owner_status = _text(payload.get("status"))
    if model.availability.status is ReadModelStatus.KNOWN and owner_status == "not_evaluated":
        return ReaderAvailability(
            ReaderAvailabilityStatus.NOT_EVALUATED,
            False,
            model.availability.reason,
            model.availability.retryable,
        )
    if model.availability.status is ReadModelStatus.KNOWN and any(
        error.code == "not_evaluated" for error in model.errors
    ):
        return ReaderAvailability(
            ReaderAvailabilityStatus.NOT_EVALUATED,
            False,
            model.availability.reason,
            model.availability.retryable,
        )
    return ReaderAvailability.from_v0(model.availability)


def _missing_availability(reason: str) -> ReaderAvailability:
    return ReaderAvailability(ReaderAvailabilityStatus.MISSING, False, reason)


def _refs_for_evidence(
    refs: Sequence[object], index: Mapping[str, SourceReference], fallback: tuple[SourceReference, ...]
) -> tuple[SourceReference, ...]:
    selected: list[SourceReference] = []
    for ref in refs:
        source_id = getattr(ref, "source_id", None)
        if isinstance(source_id, str) and source_id in index:
            selected.append(index[source_id])
    return tuple(dict.fromkeys(selected)) or fallback


def _record_availability(record: EvidenceRecord, scope: ReaderAvailability) -> ReaderAvailability:
    # Acquisition availability and protocol outcome are separate boundaries.
    # A candidate may be available while its protocol outcome is not evaluated;
    # the outcome remains on ``EvidenceTraceStep.status``.
    del record
    return scope


def _step(
    step_id: str,
    kind: TraceStepKind,
    label: str,
    value: JSONValue | None,
    refs: tuple[SourceReference, ...],
    *,
    model: ManagerReadModel,
    availability: ReaderAvailability,
    evidence_kind: EvidenceKind | None = None,
    status: EvidenceOutcome | None = None,
    locator: str | None = None,
    recorded: bool = True,
) -> EvidenceTraceStep:
    del model
    return EvidenceTraceStep(
        step_id,
        kind,
        label,
        value,
        refs,
        Derivation("direct", inputs=tuple(ref.source_id for ref in refs), version="v0") if refs else Derivation("direct"),
        availability,
        evidence_kind,
        status,
        locator,
        recorded,
    )


def _append_artifact_step(
    steps: list[EvidenceTraceStep],
    artifact: EvidenceArtifact,
    source_index: Mapping[str, SourceReference],
    model: ManagerReadModel,
    scope: ReaderAvailability,
) -> None:
    refs = _refs_for_evidence(artifact.source_refs, source_index, model.source_refs)
    available = scope if artifact.verification_status.value not in {"missing_artifact", "unavailable"} else _missing_availability("artifact")
    steps.append(
        _step(
            f"evidence.artifact.{artifact.artifact_id}",
            TraceStepKind.ARTIFACT,
            artifact.name,
            cast(JSONValue, artifact.to_dict()),
            refs,
            model=model,
            availability=available,
            locator=artifact.locator,
        )
    )


def _relation_availability(scope: ReaderAvailability) -> ReaderAvailability:
    if scope.status is ReaderAvailabilityStatus.KNOWN:
        return ReaderAvailability(ReaderAvailabilityStatus.KNOWN, scope.complete)
    return scope


def _relations_from_lineage(
    view: LineageViewModel,
    source_index: Mapping[str, SourceReference],
    fallback: tuple[SourceReference, ...],
    scope: ReaderAvailability,
) -> tuple[LineageRelationExplanation, ...]:
    result: list[LineageRelationExplanation] = []
    for edge in view.edges:
        refs = tuple(source_index[ref.source_id] for ref in edge.source_refs if ref.source_id in source_index) or fallback
        result.append(
            LineageRelationExplanation(
                edge.edge_id,
                edge.source_id,
                edge.target_id,
                edge.relation.value,
                None,
                True,
                refs,
                Derivation("direct", inputs=tuple(ref.source_id for ref in refs), version="v0") if refs else Derivation("direct"),
                _relation_availability(scope),
                _missing_availability("why this relation exists"),
            )
        )
    return tuple(result)


def _nested_relations(
    data: JSONValue,
    source_index: Mapping[str, SourceReference],
    fallback: tuple[SourceReference, ...],
) -> tuple[LineageRelationExplanation, ...]:
    payload = _mapping(data) or {}
    lineage = _mapping(payload.get("lineage")) or _mapping(payload.get("lineage_graph")) or payload
    raw_values: list[object] = []
    for key in ("relations", "edges", "lineage_relations"):
        raw_values.extend(_sequence(lineage.get(key)))
    result: list[LineageRelationExplanation] = []
    for index, raw in enumerate(raw_values, start=1):
        item = _mapping(raw)
        if item is None:
            continue
        source_id = _first(item, "source", "source_id", "from")
        target_id = _first(item, "target", "target_id", "to")
        relation = _first(item, "relation", "kind", "type")
        if source_id is None or target_id is None:
            continue
        source_ids = tuple(
            value
            for value in (_text(entry) for entry in _sequence(item.get("source_refs", item.get("sources"))))
            if value is not None and value in source_index
        )
        refs = tuple(source_index[value] for value in dict.fromkeys(source_ids)) or fallback
        why = _first(item, "why", "reason", "rationale", "association_reason")
        relation_id = _first(item, "id", "relation_id", "edge_id") or f"relation-{index}"
        derivation = Derivation("direct", inputs=tuple(ref.source_id for ref in refs), version="v0") if refs else Derivation("direct")
        relation_availability = (
            ReaderAvailability(ReaderAvailabilityStatus.KNOWN, True)
            if relation is not None
            else _missing_availability("lineage relation")
        )
        why_availability = (
            ReaderAvailability(ReaderAvailabilityStatus.KNOWN, True)
            if why is not None
            else _missing_availability("why this relation exists")
        )
        # A row is not fully available until both its relation and its reason
        # are published.  Keep ``why_availability`` separately so the UI can
        # say exactly which half is missing without inventing a reason.
        if relation is not None and why is None:
            relation_availability = why_availability
        result.append(
            LineageRelationExplanation(
                relation_id,
                source_id,
                target_id,
                relation,
                why,
                relation is not None,
                refs,
                derivation,
                relation_availability,
                why_availability,
            )
        )
    return tuple(result)


def _build_gaps(
    model: ManagerReadModel,
    steps: Sequence[EvidenceTraceStep],
    relations: Sequence[LineageRelationExplanation],
    lineage_scope_recorded: bool,
) -> tuple[ReaderClaim, ...]:
    refs = model.source_refs
    if not refs:
        return ()
    scope = _scope_availability(model)
    gaps: list[ReaderClaim] = []
    if scope.status is not ReaderAvailabilityStatus.KNOWN:
        gaps.append(_gap_claim("reader.scope", refs, scope, "The evidence and lineage scope is not complete."))
        return tuple(gaps)
    for step in steps:
        if step.recorded and step.availability.status not in {
            ReaderAvailabilityStatus.NOT_EVALUATED,
            ReaderAvailabilityStatus.MISSING,
            ReaderAvailabilityStatus.BLOCKED,
            ReaderAvailabilityStatus.STALE,
            ReaderAvailabilityStatus.INCOMPARABLE,
            ReaderAvailabilityStatus.INTEGRITY_FAILURE,
            ReaderAvailabilityStatus.API_UNAVAILABLE,
        }:
            continue
        gaps.append(_gap_claim(step.step_id, step.source_refs or refs, step.availability, step.label or step.kind.value))
    if not lineage_scope_recorded:
        gaps.append(_gap_claim("lineage.scope", refs, _missing_availability("lineage relation"), "lineage relation"))
    for relation in relations:
        if relation.why_availability.status is not ReaderAvailabilityStatus.KNOWN:
            gaps.append(_gap_claim(f"{relation.relation_id}.why", relation.source_refs or refs, relation.why_availability, "why this relation exists"))
    return tuple(gaps)


def _gap_claim(
    claim_id: str,
    refs: tuple[SourceReference, ...],
    availability: ReaderAvailability,
    value: str,
) -> ReaderClaim:
    status = availability.status
    kind = {
        ReaderAvailabilityStatus.BLOCKED: ClaimKind.BLOCKED,
        ReaderAvailabilityStatus.INTEGRITY_FAILURE: ClaimKind.BLOCKED,
        ReaderAvailabilityStatus.STALE: ClaimKind.STALE,
        ReaderAvailabilityStatus.INCOMPARABLE: ClaimKind.INCOMPARABLE,
    }.get(status, ClaimKind.MISSING)
    safe = availability
    if kind is ClaimKind.MISSING and status not in {
        ReaderAvailabilityStatus.MISSING,
        ReaderAvailabilityStatus.NOT_EVALUATED,
        ReaderAvailabilityStatus.API_UNAVAILABLE,
    }:
        safe = ReaderAvailability(ReaderAvailabilityStatus.MISSING, False, availability.reason)
    return ReaderClaim(
        claim_id,
        kind,
        refs,
        Derivation("direct", inputs=tuple(ref.source_id for ref in refs), version="v0"),
        safe,
        cast(FrozenJSON, value),
    )


def _build_claims(view: EvidenceLineageReaderViewModel) -> tuple[tuple[ReaderClaim, ...], tuple[ReaderClaim, ...]]:
    claims: list[ReaderClaim] = []
    gaps = list(view.gaps)
    for step in view.steps:
        if not step.source_refs:
            continue
        if step.availability.status is ReaderAvailabilityStatus.KNOWN:
            claim_id = step.step_id.replace("evidence.protocol_conforming.", "evidence.protocol.")
            claims.append(
                ReaderClaim(
                    claim_id,
                    ClaimKind.KNOWN,
                    step.source_refs,
                    step.derivation,
                    step.availability,
                    cast(FrozenJSON, step.value),
                )
            )
    for relation in view.relations:
        if not relation.source_refs:
            continue
        if relation.availability.status is ReaderAvailabilityStatus.KNOWN:
            claims.append(
                ReaderClaim(
                    f"lineage.relation.{relation.relation_id}",
                    ClaimKind.KNOWN,
                    relation.source_refs,
                    relation.derivation,
                    relation.availability,
                    cast(FrozenJSON, relation.to_dict()),
                )
            )
    return tuple(claims), tuple(gaps)


def _sample_projection(projection: ReaderProjection, state: str, resource: str) -> ReaderProjection:
    if projection.sample_data is not None:
        return projection
    if not projection.source_refs or any(not ref.locator.startswith("fixture://") for ref in projection.source_refs):
        return projection
    return replace(projection, sample_data=SampleData(state, resource))


def project_evidence_lineage_reader(
    model: ManagerReadModel,
    *,
    lineage_model: ManagerReadModel | None = None,
    query_context: QueryContext = None,
    sample: bool = False,
    sample_state: str | None = None,
) -> ReaderProjection:
    """Project Evidence/Lineage into Reader v1 while preserving the v0 envelope."""

    view = EvidenceLineageReaderViewModel.from_read_model(
        model, lineage_model=lineage_model, query_context=query_context
    )
    claims, gaps = _build_claims(view)
    ids = tuple(claim.claim_id for claim in (*claims, *gaps))
    summary = ReaderSummary("reader.evidence_lineage.summary", ids, {"n": len(ids)}) if ids else None
    projection = project_read_model(model, summary=summary, claims=claims, limitations=gaps)
    if sample:
        projection = _sample_projection(
            projection, sample_state or "complete", EVIDENCE_LINEAGE_READER_RESOURCE
        )
    return projection


def build_evidence_lineage_reader_fixture(state: str = "complete") -> ManagerReadModel:
    """Return a fresh complete Evidence fixture for standalone Reader previews/tests."""

    from .evidence import build_evidence_fixture

    base = build_evidence_fixture(state)
    if state != "complete":
        return base
    payload = _mapping(base.data)
    if payload is None:
        return base
    enriched = dict(payload)
    enriched["lineage"] = {
        "relations": [
            {
                "id": "protocol-supports-conclusion",
                "source": "protocol-evidence-1",
                "target": "conclusion-1",
                "relation": "supports",
                "source_refs": ["evidence-fixture-source"],
            }
        ]
    }
    return replace(base, data=cast(JSONValue, enriched))


def _reader_translator(translator: Translator | None) -> Translator:
    selected = translator or Translator()
    catalog = dict(CATALOG)
    for part in (LINEAGE_ENTRIES, READER_ENTRIES):
        for key, message in part.items():
            existing = catalog.get(key)
            if existing is not None and existing != message:
                raise CatalogError(f"conflicting Reader catalog entry: {key!r}")
            catalog[key] = message
    return Translator(selected.locale, strict=selected.strict, pseudo=selected.pseudo, catalog=merge(catalog))


def _fixture_owner(value: str | None, translator: Translator, *, fixture: bool) -> str:
    if value is None or not value:
        return escape(translator.t("reader.evidence_lineage.no_value"))
    if fixture and value in _FIXTURE_TEXT_KEYS:
        return escape(translator.t(_FIXTURE_TEXT_KEYS[value]))
    return f'<span data-owner-text="true">{escape(value)}</span>'


def _id_owner(value: str) -> str:
    return f'<span data-owner-text="true" translate="no">{escape(value)}</span>'


def _availability(value: ReaderAvailability, translator: Translator) -> str:
    label = translator.label("reader_trace_availability", value.status.value)
    reason = (
        f' <span class="reader-availability-reason" data-owner-text="true">{escape(value.reason)}</span>'
        if value.reason
        else ""
    )
    return f'<span class="reader-availability" data-availability="{escape(value.status.value, quote=True)}">{label}</span>{reason}'


def _derivation(value: Derivation, translator: Translator) -> str:
    parts = [value.kind, value.rule, value.version]
    fields = " · ".join(f'<code translate="no">{escape(part)}</code>' for part in parts if part)
    inputs = translator.join(_id_owner(item) for item in value.inputs)
    if inputs:
        fields += f" ({escape(translator.t('reader.evidence_lineage.source'))}: {inputs})"
    return fields or escape(translator.t("reader.evidence_lineage.no_derivation"))


def _source_markup(
    refs: Sequence[SourceReference], context: QueryContext, translator: Translator
) -> str:
    if not refs:
        return escape(translator.t("reader.evidence_lineage.no_source"))
    items: list[str] = []
    for ref in refs:
        local = context_link(context, view=ViewId.EVIDENCE, source_id=ref.source_id, reader_step=f"source:{ref.source_id}")
        link = public_locator(ref.locator)
        external = (
            f' <a class="reader-source-public-link" href="{escape(link, quote=True)}">{escape(translator.t("reader.evidence_lineage.open_source"))}</a>'
            if link
            else ""
        )
        items.append(
            f'<li>{_id_owner(ref.source_id)} <a class="reader-evidence-link" data-source-id="{escape(ref.source_id, quote=True)}" href="{escape(local, quote=True)}">{escape(translator.t("reader.evidence_lineage.open_evidence"))}</a>{external}</li>'
        )
    return "<ul>" + "".join(items) + "</ul>"


def _step_href(step: EvidenceTraceStep, context: QueryContext) -> str:
    updates: dict[str, object] = {"reader_step": step.step_id}
    if step.kind is TraceStepKind.SOURCE:
        updates["source_id"] = step.label
    elif step.kind is TraceStepKind.ARTIFACT:
        updates["artifact_id"] = step.step_id.rsplit(".", 1)[-1]
    elif step.kind is TraceStepKind.EVIDENCE:
        updates["record_id"] = step.step_id.rsplit(".", 1)[-1]
    return context_link(context, view=ViewId.EVIDENCE, **updates)


def _render_step(
    step: EvidenceTraceStep,
    *,
    context: QueryContext,
    translator: Translator,
    fixture: bool,
) -> str:
    kind_label = translator.label("reader_trace_step", step.kind.value)
    evidence_label = (
        f'<div><dt>{escape(translator.t("reader.evidence_lineage.evidence_class"))}</dt><dd>{translator.label("evidence_kind", step.evidence_kind.value)}</dd></div>'
        if step.evidence_kind is not None
        else ""
    )
    status_label = (
        f'<div><dt>{escape(translator.t("reader.evidence_lineage.status"))}</dt><dd>{translator.label("evidence_outcome", step.status.value)}</dd></div>'
        if step.status is not None
        else ""
    )
    value = _fixture_owner(step.label, translator, fixture=fixture)
    href = _step_href(step, context)
    return (
        f'<li class="reader-trace-step" data-trace-step="{escape(step.kind.value, quote=True)}" data-step-id="{escape(step.step_id, quote=True)}" data-availability="{escape(step.availability.status.value, quote=True)}"'
        + (f' data-evidence-status="{escape(step.status.value, quote=True)}"' if step.status else "")
        + (f' data-evidence-class="{escape(step.evidence_kind.value, quote=True)}"' if step.evidence_kind else "")
        + f'><h3><a class="reader-trace-link" href="{escape(href, quote=True)}">{kind_label}: {value}</a></h3>'
        f'<dl class="reader-trace-facts"><div><dt>{escape(translator.t("reader.evidence_lineage.source"))}</dt><dd>{_source_markup(step.source_refs, context, translator)}</dd></div>'
        f'<div><dt>{escape(translator.t("reader.evidence_lineage.derivation"))}</dt><dd>{_derivation(step.derivation, translator)}</dd></div>'
        f'<div><dt>{escape(translator.t("reader.evidence_lineage.availability"))}</dt><dd>{_availability(step.availability, translator)}</dd></div>'
        f'{evidence_label}{status_label}</dl></li>'
    )


def _render_relation(
    relation: LineageRelationExplanation,
    *,
    context: QueryContext,
    translator: Translator,
    fixture: bool,
) -> str:
    relation_value = _id_owner(relation.relation) if relation.relation else escape(translator.t("reader.evidence_lineage.not_recorded"))
    why = _fixture_owner(relation.why, translator, fixture=fixture) if relation.why else escape(translator.t("reader.evidence_lineage.unknown_reason"))
    explicit = translator.t("reader.evidence_lineage.explicit_yes" if relation.recorded else "reader.evidence_lineage.explicit_no")
    lineage_href = context_link(context, view=ViewId.LINEAGE, record_id=relation.target_id, node=relation.target_id)
    return (
        f'<tr data-relation-id="{escape(relation.relation_id, quote=True)}" data-relation-recorded="{str(relation.recorded).lower()}" data-relation-availability="{escape(relation.availability.status.value, quote=True)}">'
        f'<th scope="row">{_id_owner(relation.source_id)}</th><td>{_id_owner(relation.target_id)}</td><td>{relation_value}</td>'
        f'<td>{why}</td><td>{escape(explicit)}</td><td>{_availability(relation.why_availability, translator)}</td>'
        f'<td><a class="reader-lineage-link" href="{escape(lineage_href, quote=True)}">{escape(translator.t("reader.evidence_lineage.open_lineage"))}</a></td></tr>'
    )


def _render_reader(
    view: EvidenceLineageReaderViewModel,
    projection: ReaderProjection,
    *,
    context: QueryContext,
    translator: Translator,
    page: ReaderPage,
) -> str:
    fixture = projection.sample_data is not None
    banner = (
        f'<p class="reader-sample-banner" data-sample-banner="fixture">{escape(translator.t("reader.evidence_lineage.sample_banner"))}</p>'
        if fixture
        else ""
    )
    has_candidate = any(step.evidence_kind is EvidenceKind.CANDIDATE for step in view.steps)
    has_protocol = any(step.evidence_kind is EvidenceKind.PROTOCOL_CONFORMING for step in view.steps)
    evidence_boundary = (
        f'<p class="reader-evidence-boundary" data-candidate-boundary="true">{escape(translator.t("evidence.candidate_notice"))}</p>'
        if has_candidate and has_protocol
        else ""
    )
    rows = "".join(
        _render_step(step, context=context, translator=translator, fixture=fixture) for step in view.steps
    )
    relation_rows = "".join(
        _render_relation(relation, context=context, translator=translator, fixture=fixture)
        for relation in view.relations
    )
    if not relation_rows:
        relation_rows = f'<tr data-relation-recorded="false"><td colspan="7">{escape(translator.t("reader.evidence_lineage.no_lineage"))}</td></tr>'
    expert_href = context_link(context, view=ViewId.LINEAGE, mode=ReaderTraceMode.EXPERT.value)
    surface = render_reader_surface(
        projection,
        page=page,
        query_context=context,
        translator=translator,
    )
    return (
        f'<section class="evidence-lineage-reader" data-reader-hook="{EVIDENCE_LINEAGE_READER_HOOK}" data-reader-mode="reader" data-status="{escape(view.availability.status.value, quote=True)}" data-evidence-status="{escape(view.evidence.status.value, quote=True)}" aria-labelledby="evidence-lineage-reader-title">'
        f'<p class="eyebrow">{escape(translator.t("reader.evidence_lineage.eyebrow"))}</p>'
        f'<h1 id="evidence-lineage-reader-title" tabindex="-1">{escape(translator.t("reader.evidence_lineage.title"))}</h1>'
        f'<p class="reader-intro">{escape(translator.t("reader.evidence_lineage.intro"))}</p>{banner}{evidence_boundary}{surface}'
        f'<section class="reader-trace-chain" aria-labelledby="reader-trace-chain-heading"><h2 id="reader-trace-chain-heading">{escape(translator.t("reader.evidence_lineage.chain_heading"))}</h2><p>{escape(translator.t("reader.evidence_lineage.chain_caption"))}</p><ol>{rows}</ol></section>'
        f'<section class="reader-lineage-relations" aria-labelledby="reader-lineage-relations-heading" data-lineage-view="table"><h2 id="reader-lineage-relations-heading">{escape(translator.t("reader.evidence_lineage.relations_heading"))}</h2><p>{escape(translator.t("reader.evidence_lineage.relations_intro"))}</p><table class="reader-lineage-table"><caption>{escape(translator.t("reader.evidence_lineage.relations_heading"))}</caption><thead><tr><th scope="col">{escape(translator.t("reader.evidence_lineage.from"))}</th><th scope="col">{escape(translator.t("reader.evidence_lineage.to"))}</th><th scope="col">{escape(translator.t("reader.evidence_lineage.what"))}</th><th scope="col">{escape(translator.t("reader.evidence_lineage.why"))}</th><th scope="col">{escape(translator.t("reader.evidence_lineage.recorded"))}</th><th scope="col">{escape(translator.t("reader.evidence_lineage.availability"))}</th><th scope="col">{escape(translator.t("reader.evidence_lineage.open_lineage"))}</th></tr></thead><tbody>{relation_rows}</tbody></table></section>'
        f'<p class="reader-expert-link"><a class="reader-lineage-expert-link" href="{escape(expert_href, quote=True)}">{escape(translator.t("reader.evidence_lineage.open_lineage"))}</a></p>'
        f'</section>'
    )


def _render_raw(
    model: ManagerReadModel,
    projection: ReaderProjection,
    *,
    lineage_model: ManagerReadModel | None,
    translator: Translator,
) -> str:
    del model
    raw = projection.raw_source.raw_bytes.decode("utf-8")
    lineage_raw = "" if lineage_model is None else f"\n{lineage_model.to_json()}"
    # Raw mode is an explicit transport view: preserve the canonical bytes
    # verbatim rather than translating or rewriting owner payload values.
    return (
        f'<section class="evidence-lineage-reader" data-reader-hook="{EVIDENCE_LINEAGE_READER_HOOK}" data-reader-mode="raw">'
        f'<h1>{escape(translator.t("reader.evidence_lineage.raw_heading"))}</h1><pre class="reader-raw-json">{raw + lineage_raw}</pre></section>'
    )


def _render_expert(
    view: EvidenceLineageReaderViewModel,
    *,
    context: QueryContext,
    translator: Translator,
) -> str:
    evidence_html = view.evidence.read_model
    evidence_markup = __import__("manager_gui.web.evidence", fromlist=["render_evidence"]).render_evidence(
        evidence_html, query_context=context, include_raw_json=False, translator=translator
    )
    lineage_markup = (
        render_lineage(view.lineage, query_context=context, route=ViewId.LINEAGE.value, include_raw_json=False, translator=translator)
        if view.lineage is not None
        else f'<p class="reader-lineage-gap">{escape(translator.t("reader.evidence_lineage.no_lineage"))}</p>'
    )
    return (
        f'<section class="evidence-lineage-reader" data-reader-hook="{EVIDENCE_LINEAGE_READER_HOOK}" data-reader-mode="expert">'
        f'<h1>{escape(translator.t("reader.evidence_lineage.expert_heading"))}</h1><p>{escape(translator.t("reader.evidence_lineage.expert_intro"))}</p>'
        f'<div data-lineage-graph="expert">{lineage_markup}</div>{evidence_markup}</section>'
    )


def render_evidence_lineage_reader(
    source: ManagerReadModel | EvidenceLineageReaderViewModel | ReaderProjection,
    *,
    projection: ReaderProjection | None = None,
    lineage_model: ManagerReadModel | None = None,
    query_context: QueryContext = None,
    mode: ReaderTraceMode | str = ReaderTraceMode.READER,
    translator: Translator | None = None,
    page: ReaderPage = ReaderPage.EVIDENCE,
) -> str:
    """Render Reader, Expert, or Raw mode without changing the supplied envelope."""

    selected = ReaderTraceMode(mode)
    if isinstance(source, EvidenceLineageReaderViewModel):
        view = source
        model = view.read_model
    elif isinstance(source, ReaderProjection):
        model = ManagerReadModel.from_json(source.raw_source.raw_bytes.decode("utf-8"))
        view = EvidenceLineageReaderViewModel.from_read_model(model, lineage_model=lineage_model, query_context=query_context)
        projection = source
    else:
        model = source
        view = EvidenceLineageReaderViewModel.from_read_model(model, lineage_model=lineage_model, query_context=query_context)
    selected_projection = projection or project_evidence_lineage_reader(
        model, lineage_model=lineage_model, query_context=query_context
    )
    if selected_projection.sample_data is None and model.source_refs and all(
        ref.locator.startswith("fixture://") for ref in model.source_refs
    ):
        selected_projection = _sample_projection(
            selected_projection, "complete", EVIDENCE_LINEAGE_READER_RESOURCE
        )
    selected_translator = _reader_translator(translator)
    if selected is ReaderTraceMode.RAW:
        return _render_raw(model, selected_projection, lineage_model=lineage_model, translator=selected_translator)
    if selected is ReaderTraceMode.EXPERT:
        return _render_expert(view, context=query_context, translator=selected_translator)
    return _render_reader(
        view,
        selected_projection,
        context=query_context,
        translator=selected_translator,
        page=page,
    )


def render_evidence_lineage_reader_view(
    source: ManagerReadModel | EvidenceLineageReaderViewModel | ReaderProjection,
    **kwargs: object,
) -> str:
    """Compatibility alias following the other Manager GUI page hooks."""

    return render_evidence_lineage_reader(source, **cast(dict[str, object], kwargs))


# Discoverable aliases used by integration slices.
project_evidence_trace_reader = project_evidence_lineage_reader
render_evidence_trace_reader = render_evidence_lineage_reader
EvidenceTraceReaderView = EvidenceLineageReaderViewModel


__all__ = [
    "EVIDENCE_LINEAGE_READER_HOOK",
    "EVIDENCE_LINEAGE_READER_RESOURCE",
    "EVIDENCE_LINEAGE_READER_RULE",
    "EVIDENCE_LINEAGE_READER_VERSION",
    "EvidenceLineageReaderView",
    "EvidenceLineageReaderViewModel",
    "EvidenceTraceReaderView",
    "EvidenceTraceStep",
    "LineageRelationExplanation",
    "ReaderTraceMode",
    "TraceStepKind",
    "build_evidence_lineage_reader_fixture",
    "project_evidence_lineage_reader",
    "project_evidence_trace_reader",
    "render_evidence_lineage_reader",
    "render_evidence_lineage_reader_view",
    "render_evidence_trace_reader",
]
