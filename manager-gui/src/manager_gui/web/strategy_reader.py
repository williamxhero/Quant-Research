"""Reader-mode projections for Strategy, Genome, conditions, and revisions.

This module is a presentation-only adapter over the public ``ManagerReadModel``
envelope.  It deliberately keeps strategy structure, validation/qualification,
condition evidence, and revision evolution as separate typed sections.  No
field is promoted to an effectiveness conclusion and no relationship is
inferred from identifiers, timestamps, or revision numbers.
"""

# HTML fragments intentionally keep readable markup at the call site.
# ruff: noqa: E501

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from html import escape
from typing import TypeAlias, cast
from urllib.parse import parse_qsl, urlencode, urlsplit

from ..models import Derivation, JSONValue, ManagerReadModel, ReadModelStatus, SourceReference
from ..reader import (
    ClaimKind,
    FrozenJSON,
    ReaderAvailability,
    ReaderAvailabilityStatus,
    ReaderClaim,
    ReaderProjection,
    ReaderSummary,
    project_read_model,
)
from .comparison import genome_comparison_link
from .conditions import ConditionCategory, genome_conditions_link
from .genome import BEHAVIOR_PROJECTION_FIELDS, GenomeViewModel, genome_link
from .i18n import Translator
from .reader_surface import ReaderPage, render_reader_surface
from .status import render_status_block

STRATEGY_READER_RESOURCE = "genomes"
STRATEGY_READER_RULE = "manager-gui.reader.strategy-genome.v1"
STRATEGY_READER_VERSION = "v1"
STRATEGY_READER_HOOK = "strategy-reader-view"

QueryContext: TypeAlias = str | Mapping[str, object] | None
JSONMapping: TypeAlias = Mapping[str, JSONValue]


class StrategyReaderSection(StrEnum):
    STRUCTURE = "structure"
    VALIDITY = "validity"
    CONDITIONS = "conditions"
    REVISIONS = "revisions"


def _mapping(value: object) -> Mapping[str, object] | None:
    return cast(Mapping[str, object], value) if isinstance(value, Mapping) else None


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(value)
    if isinstance(value, Mapping):
        return (value,)
    return ()


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _first_text(item: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        value = _text(item.get(key))
        if value is not None:
            return value
    return None


def _json_value(value: object) -> JSONValue | None:
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


def _query_pairs(context: QueryContext) -> list[tuple[str, str]]:
    if context is None:
        return []
    if isinstance(context, str):
        parsed = urlsplit(context)
        query = parsed.query if parsed.query or parsed.path.startswith("/") else context.lstrip("?")
        return [(key, value) for key, value in parse_qsl(query, keep_blank_values=True) if key]
    pairs: list[tuple[str, str]] = []
    for key, value in context.items():
        if not isinstance(key, str) or not key or value is None:
            continue
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            pairs.extend((key, str(entry)) for entry in value)
        else:
            pairs.append((key, str(value)))
    return pairs


def _context_url(context: QueryContext, *, view: str, **updates: object) -> str:
    pairs = _query_pairs(context)
    pairs = [(key, value) for key, value in pairs if key != "view" and key not in updates]
    pairs.append(("view", view))
    pairs.extend((key, str(value)) for key, value in updates.items() if value is not None)
    return "/?" + urlencode(pairs)


def _source_refs(model: ManagerReadModel) -> tuple[SourceReference, ...]:
    return tuple(model.source_refs)


def _claim_availability(model: ManagerReadModel) -> ReaderAvailability:
    return ReaderAvailability.from_v0(model.availability)


def _direct_claim(
    claim_id: str,
    value: JSONValue,
    refs: tuple[SourceReference, ...],
    *,
    model: ManagerReadModel,
    kind: ClaimKind = ClaimKind.KNOWN,
    availability: ReaderAvailability | None = None,
) -> ReaderClaim | None:
    if not refs:
        return None
    selected = availability or _claim_availability(model)
    if kind is ClaimKind.KNOWN and selected.status in {
        ReaderAvailabilityStatus.DERIVED,
        ReaderAvailabilityStatus.INTERPRETED,
    }:
        # The v0 envelope may describe how the read was acquired while this
        # claim remains a direct field from that already-published envelope.
        selected = ReaderAvailability(
            ReaderAvailabilityStatus.KNOWN,
            selected.complete,
            selected.reason,
            selected.retryable,
        )
    if kind is ClaimKind.KNOWN and selected.status is not ReaderAvailabilityStatus.KNOWN:
        return None
    if kind is ClaimKind.MISSING:
        selected = ReaderAvailability(
            ReaderAvailabilityStatus.MISSING, False, selected.reason or "The value is not recorded."
        )
    return ReaderClaim(
        claim_id=claim_id,
        kind=kind,
        source_refs=refs,
        derivation=Derivation("direct", inputs=tuple(ref.source_id for ref in refs), version="v0"),
        availability=selected,
        value=cast(FrozenJSON, value),
    )


def _derived_claim(
    claim_id: str, value: JSONValue, refs: tuple[SourceReference, ...]
) -> ReaderClaim | None:
    if not refs:
        return None
    return ReaderClaim(
        claim_id=claim_id,
        kind=ClaimKind.INTERPRETED,
        source_refs=refs,
        derivation=Derivation(
            "interpreted", STRATEGY_READER_RULE, tuple(ref.source_id for ref in refs), STRATEGY_READER_VERSION
        ),
        availability=ReaderAvailability(
            ReaderAvailabilityStatus.INTERPRETED,
            True,
            "The sentence is a fixed Reader interpretation of published fields.",
        ),
        value=cast(FrozenJSON, value),
    )


def _gap_kind(status: ReaderAvailabilityStatus) -> ClaimKind:
    return {
        ReaderAvailabilityStatus.BLOCKED: ClaimKind.BLOCKED,
        ReaderAvailabilityStatus.INTEGRITY_FAILURE: ClaimKind.BLOCKED,
        ReaderAvailabilityStatus.STALE: ClaimKind.STALE,
        ReaderAvailabilityStatus.INCOMPARABLE: ClaimKind.INCOMPARABLE,
    }.get(status, ClaimKind.MISSING)


def _gap_claim(
    claim_id: str,
    value: JSONValue,
    refs: tuple[SourceReference, ...],
    *,
    status: ReaderAvailabilityStatus = ReaderAvailabilityStatus.MISSING,
    reason: str,
) -> ReaderClaim | None:
    if not refs:
        return None
    return ReaderClaim(
        claim_id=claim_id,
        kind=_gap_kind(status),
        source_refs=refs,
        derivation=Derivation("direct", inputs=tuple(ref.source_id for ref in refs), version="v0"),
        availability=ReaderAvailability(status, False, reason),
        value=cast(FrozenJSON, value),
    )


def _condition_items(data: object) -> tuple[Mapping[str, object], ...]:
    item = _mapping(data)
    if item is None:
        return ()
    values: list[Mapping[str, object]] = []
    explicit_groups = {
        "applicability_conditions": ConditionCategory.APPLICABILITY.value,
        "invalidation_conditions": ConditionCategory.INVALIDATION.value,
        "failure_conditions": ConditionCategory.INVALIDATION.value,
        "counterexamples": "counterexample",
        "descriptors": "descriptor",
    }
    for key in (
        "conditions",
        "condition_evidence",
        "applicability_conditions",
        "invalidation_conditions",
        "failure_conditions",
        "counterexamples",
        "descriptors",
    ):
        for entry in _sequence(item.get(key)):
            mapped = _mapping(entry)
            if mapped is None:
                continue
            # A named collection is an explicit category; a generic conditions
            # collection remains unclassified unless its item says otherwise.
            category = explicit_groups.get(key)
            if category is not None and not _text(mapped.get("category", mapped.get("kind"))):
                mapped = {**mapped, "category": category}
            values.append(mapped)
    return tuple(values)


def _revision_items(data: object) -> tuple[Mapping[str, object], ...]:
    item = _mapping(data)
    if item is None:
        return ()
    values: list[Mapping[str, object]] = []
    for key in ("revisions", "strategy_revisions", "evolution", "revision_tree", "history"):
        raw = item.get(key)
        nested = _mapping(raw)
        entries = _sequence(nested.get("revisions")) if nested is not None else _sequence(raw)
        for entry in entries:
            if (mapped := _mapping(entry)) is not None:
                values.append(mapped)
    return tuple(values)


@dataclass(frozen=True, slots=True)
class StrategyField:
    """One explicitly published behavior field; absence stays visible."""

    name: str
    value: JSONValue | None
    recorded: bool


@dataclass(frozen=True, slots=True)
class StrategyRevision:
    """An owner-recorded revision node with no quality ordering."""

    revision_id: str | None
    parent_id: str | None
    children: tuple[str, ...] = ()
    changes: JSONValue | None = None
    reason: str | None = None
    evidence: JSONValue | None = None
    result: JSONValue | None = None
    limitations: JSONValue | None = None
    condition_refs: tuple[str, ...] = ()
    genome_id: str | None = None
    source_refs: tuple[SourceReference, ...] = ()
    raw: JSONMapping = field(default_factory=dict, repr=False, compare=False)

    @property
    def has_reason(self) -> bool:
        return self.reason is not None

    def to_dict(self) -> dict[str, object]:
        return {
            "revision_id": self.revision_id,
            "parent_id": self.parent_id,
            "children": list(self.children),
            "changes": self.changes,
            "reason": self.reason,
            "evidence": self.evidence,
            "result": self.result,
            "limitations": self.limitations,
            "condition_refs": list(self.condition_refs),
            "genome_id": self.genome_id,
            "source_refs": [source.to_dict() for source in self.source_refs],
        }


@dataclass(frozen=True, slots=True)
class StrategyReaderViewModel:
    """Reader-oriented view over Genome and explicitly related records."""

    read_model: ManagerReadModel
    genome_id: str | None
    schema: str | None
    behavior: tuple[StrategyField, ...]
    validation: JSONMapping
    conditions: tuple[Mapping[str, object], ...]
    revisions: tuple[StrategyRevision, ...]
    qualification: JSONValue | None
    currency: JSONValue | None
    counterexamples: tuple[Mapping[str, object], ...]
    owner_summary: str | None

    @classmethod
    def from_read_model(cls, model: ManagerReadModel) -> StrategyReaderViewModel:
        genomes = GenomeViewModel.from_read_model(model).catalog
        genome = genomes[0] if len(genomes) == 1 else None
        raw = genome.raw if genome is not None else (_mapping(model.data) or {})
        behavior_map = genome.behavior if genome is not None else _mapping(raw.get("behavior")) or {}
        behavior = tuple(
            StrategyField(name, _json_value(behavior_map.get(name)), name in behavior_map)
            for name in BEHAVIOR_PROJECTION_FIELDS
        )
        validation = (
            _json_mapping(genome.validation.to_dict())
            if genome is not None and genome.validation.present
            else _json_mapping(raw.get("validation"))
        )
        conditions = _condition_items(raw)
        counterexamples = tuple(
            item
            for item in conditions
            if _text(item.get("category", item.get("kind"))) in {"counterexample", "counter-example"}
            or item.get("counterexample") is True
        )
        revisions = _parse_revisions(model, raw)
        qualification = raw.get("qualification", raw.get("qualification_status"))
        currency = raw.get("currency", raw.get("currency_status"))
        owner_summary = _first_text(raw, "strategy_summary", "summary", "description", "behavior_summary")
        return cls(
            model,
            None if genome is None else genome.genome_id,
            None if genome is None else genome.schema,
            behavior,
            validation,
            conditions,
            revisions,
            _json_value(qualification),
            _json_value(currency),
            counterexamples,
            owner_summary,
        )

    @property
    def applicability(self) -> tuple[Mapping[str, object], ...]:
        return tuple(item for item in self.conditions if _text(item.get("category", item.get("kind"))) in {ConditionCategory.APPLICABILITY.value, "applicable"})

    @property
    def invalidation(self) -> tuple[Mapping[str, object], ...]:
        return tuple(item for item in self.conditions if _text(item.get("category", item.get("kind"))) in {ConditionCategory.INVALIDATION.value, "failure", "invalidating"})

    @property
    def descriptors(self) -> tuple[Mapping[str, object], ...]:
        return tuple(
            item
            for item in self.conditions
            if _text(item.get("category", item.get("kind")))
            in {"descriptor", "descriptive_observation", "observation"}
        )

    @property
    def unclassified(self) -> tuple[Mapping[str, object], ...]:
        classified = self.applicability + self.invalidation + self.counterexamples + self.descriptors
        return tuple(item for item in self.conditions if item not in classified)

    @property
    def validation_recorded(self) -> bool:
        return bool(self.validation)

    @property
    def effectiveness_evaluated(self) -> bool:
        return self.qualification is not None or any(key in self.validation for key in ("result", "qualification", "status"))

    def to_dict(self) -> dict[str, object]:
        return {
            "view": "strategy-reader",
            "genome_id": self.genome_id,
            "schema": self.schema,
            "behavior": [field.__dict__ if hasattr(field, "__dict__") else {"name": field.name, "value": field.value, "recorded": field.recorded} for field in self.behavior],
            "validation": self.validation,
            "conditions": [dict(item) for item in self.conditions],
            "revisions": [revision.to_dict() for revision in self.revisions],
            "qualification": self.qualification,
            "currency": self.currency,
            "counterexamples": [dict(item) for item in self.counterexamples],
        }


def _lifecycle_value(view: StrategyReaderViewModel) -> JSONValue | None:
    genomes = GenomeViewModel.from_read_model(view.read_model).catalog
    if len(genomes) == 1 and genomes[0].events:
        return _json_value([event.to_dict() for event in genomes[0].events])
    raw = _mapping(view.read_model.data) or {}
    return _json_value(raw.get("lifecycle", raw.get("lifecycle_events", raw.get("events"))))


def _reference_text(value: object, *keys: str) -> str | None:
    if isinstance(value, Mapping):
        mapped = _mapping(value)
        return None if mapped is None else _first_text(mapped, *keys)
    return _text(value)


def _parse_revisions(model: ManagerReadModel, raw: Mapping[str, object]) -> tuple[StrategyRevision, ...]:
    source_index = {source.source_id: source for source in model.source_refs}
    records: list[StrategyRevision] = []
    for item in _revision_items(raw):
        revision_id = _first_text(item, "revision_id", "revisionId", "revision", "id", "record_id")
        parent_id = _first_text(item, "parent_revision", "parent_revision_id", "parentRevision", "parent_id", "parent")
        children = tuple(
            text
            for value in _sequence(item.get("children", item.get("child_revisions")))
            if (text := _reference_text(value, "revision_id", "id")) is not None
        )
        refs: list[SourceReference] = []
        for value in _sequence(item.get("source_refs", item.get("source_ref", item.get("source_ids")))):
            source_id = _reference_text(value, "source_id", "id")
            if source_id in source_index:
                refs.append(source_index[cast(str, source_id)])
        records.append(
            StrategyRevision(
                revision_id,
                parent_id,
                children,
                _json_value(item.get("changes", item.get("change_set", item.get("diff")))),
                _first_text(item, "reason", "owner_reason", "rationale"),
                _json_value(item.get("evidence", item.get("evidence_refs"))),
                _json_value(item.get("result", item.get("outcome"))),
                _json_value(item.get("limitations", item.get("limits"))),
                tuple(
                    condition_ref
                    for value in _sequence(item.get("condition_refs", item.get("conditions")))
                    if (condition_ref := _reference_text(value, "condition_id", "condition_ref", "id")) is not None
                ),
                _first_text(item, "genome_id", "genomeId"),
                tuple(dict.fromkeys(refs)),
                _json_mapping(item),
            )
        )
    known = {revision.revision_id for revision in records if revision.revision_id is not None}
    if records:
        children_by_parent: dict[str, list[str]] = {}
        for revision in records:
            if revision.parent_id in known and revision.revision_id is not None:
                children_by_parent.setdefault(cast(str, revision.parent_id), []).append(revision.revision_id)
        records = [
            StrategyRevision(
                revision.revision_id,
                revision.parent_id,
                tuple(dict.fromkeys((*revision.children, *children_by_parent.get(revision.revision_id or "", ())))),
                revision.changes,
                revision.reason,
                revision.evidence,
                revision.result,
                revision.limitations,
                revision.condition_refs,
                revision.genome_id,
                revision.source_refs or model.source_refs,
                revision.raw,
            )
            for revision in records
        ]
    return tuple(records)


def _build_claims(view: StrategyReaderViewModel) -> tuple[tuple[ReaderClaim, ...], tuple[ReaderClaim, ...], tuple[ReaderClaim, ...]]:
    refs = _source_refs(view.read_model)
    claims: list[ReaderClaim] = []
    gaps: list[ReaderClaim] = []
    if view.read_model.availability.status in {
        ReadModelStatus.MISSING,
        ReadModelStatus.BLOCKED,
        ReadModelStatus.STALE,
        ReadModelStatus.INCOMPARABLE,
        ReadModelStatus.INTEGRITY_FAILURE,
        ReadModelStatus.API_UNAVAILABLE,
    }:
        status = ReaderAvailabilityStatus(view.read_model.availability.status.value)
        claim = _gap_claim("strategy.read_scope", "The strategy read scope is not currently complete.", refs, status=status, reason=view.read_model.availability.reason or "The strategy read scope is unavailable.")
        if claim is not None:
            gaps.append(claim)
        return tuple(claims), tuple(gaps), ()
    interpreted = _derived_claim(
        "strategy.structure.interpretation",
        "strategy_structure",
        refs,
    )
    if interpreted is not None:
        claims.append(interpreted)
    for behavior_field in view.behavior:
        if behavior_field.recorded:
            claim = _direct_claim(f"strategy.structure.{behavior_field.name}", behavior_field.value, refs, model=view.read_model)
            if claim is not None:
                claims.append(claim)
        else:
            claim = _gap_claim(
                f"strategy.structure.{behavior_field.name}",
                behavior_field.name,
                refs,
                reason=f"The strategy field {behavior_field.name} is not recorded.",
            )
            if claim is not None:
                gaps.append(claim)
    if view.validation_recorded:
        claim = _direct_claim("strategy.validation.binding", cast(JSONValue, dict(view.validation)), refs, model=view.read_model)
        if claim is not None:
            claims.append(claim)
    else:
        claim = _gap_claim("strategy.validation.binding", "validation binding", refs, reason="Validation binding is not recorded.")
        if claim is not None:
            gaps.append(claim)
    condition_statuses = {
        "blocked": ReaderAvailabilityStatus.BLOCKED,
        "stale": ReaderAvailabilityStatus.STALE,
        "integrity_failure": ReaderAvailabilityStatus.INTEGRITY_FAILURE,
        "incomparable": ReaderAvailabilityStatus.INCOMPARABLE,
        "missing": ReaderAvailabilityStatus.MISSING,
        "not_evaluated": ReaderAvailabilityStatus.NOT_EVALUATED,
        "not-evaluated": ReaderAvailabilityStatus.NOT_EVALUATED,
    }
    for index, item in enumerate(view.conditions):
        outcome = _text(item.get("outcome", item.get("result", item.get("status"))))
        status = condition_statuses.get(outcome or "", ReaderAvailabilityStatus.KNOWN)
        reason = "Condition has not been evaluated." if status is ReaderAvailabilityStatus.NOT_EVALUATED else "Condition record is unavailable."
        if status is ReaderAvailabilityStatus.KNOWN:
            claim = _direct_claim(
                f"strategy.condition.{index}",
                _json_value(item) or {},
                refs,
                model=view.read_model,
                availability=ReaderAvailability(status, True),
            )
        else:
            claim = _gap_claim(
                f"strategy.condition.{index}",
                _json_value(item) or {},
                refs,
                status=status,
                reason=reason,
            )
        if claim is not None:
            (claims if status is ReaderAvailabilityStatus.KNOWN else gaps).append(claim)
    if not view.conditions:
        claim = _gap_claim("strategy.conditions", "conditions", refs, reason="No applicability or invalidation condition record is published.")
        if claim is not None:
            gaps.append(claim)
    if view.qualification is None:
        claim = _gap_claim("strategy.qualification", "qualification", refs, reason="Qualification has not been recorded; effectiveness cannot be determined.")
        if claim is not None:
            gaps.append(claim)
    if view.currency is None:
        claim = _gap_claim("strategy.currency", "currency", refs, reason="Currency information is not recorded.")
        if claim is not None:
            gaps.append(claim)
    else:
        claim = _direct_claim("strategy.currency", view.currency, refs, model=view.read_model)
        if claim is not None:
            claims.append(claim)
    if view.qualification is not None:
        claim = _direct_claim("strategy.qualification", view.qualification, refs, model=view.read_model)
        if claim is not None:
            claims.append(claim)
    lifecycle = _lifecycle_value(view)
    if lifecycle is not None:
        claim = _direct_claim("strategy.lifecycle", lifecycle, refs, model=view.read_model)
        if claim is not None:
            claims.append(claim)
    for index, revision in enumerate(view.revisions):
        claim = _direct_claim(f"strategy.revision.{index}", cast(JSONValue, revision.to_dict()), refs, model=view.read_model)
        if claim is not None:
            claims.append(claim)
    return tuple(claims), tuple(gaps), ()


def project_strategy_reader(
    model: ManagerReadModel,
    *,
    resource: str = STRATEGY_READER_RESOURCE,
    sample: bool = False,
    sample_state: str | None = None,
) -> ReaderProjection:
    """Build a ReaderProjection from an owner-aware Strategy/Genome adapter."""

    view = StrategyReaderViewModel.from_read_model(model)
    claims, limitations, unknowns = _build_claims(view)
    summary_ids = tuple(claim.claim_id for claim in (*claims, *limitations, *unknowns))
    summary = ReaderSummary("reader.strategy-genome.summary", summary_ids, {"n": len(summary_ids)}) if summary_ids else None
    projection = project_read_model(model, summary=summary, claims=claims, limitations=limitations, unknowns=unknowns)
    if sample:
        from ..reader import SampleData

        state = sample_state or "complete"
        if all(ref.locator.startswith("fixture://") for ref in projection.source_refs):
            projection = projection.__class__(
                projection.data,
                projection.summary,
                projection.claims,
                projection.limitations,
                projection.unknowns,
                projection.source_refs,
                projection.as_of,
                projection.snapshot_token,
                projection.derivation,
                projection.availability,
                projection.raw_source,
                SampleData(state, resource),
            )
    return projection


def _display(value: object, translator: Translator, *, owner: bool = True) -> str:
    if value is None or value == "" or value == [] or value == {}:
        return escape(translator.t("strategy_reader.not_recorded"))
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    markup = escape(text)
    return f'<span translate="no">{markup}</span>' if owner else markup


def _field_table(view: StrategyReaderViewModel, translator: Translator) -> str:
    rows = "".join(
        f'<tr data-strategy-field="{escape(behavior_field.name, quote=True)}" data-recorded="{str(behavior_field.recorded).lower()}">'
        f'<th scope="row">{escape(translator.label("genome_behavior", behavior_field.name))}</th><td>{_display(behavior_field.value, translator)}</td></tr>'
        for behavior_field in view.behavior
    )
    return f'<table class="strategy-reader-fields"><caption>{escape(translator.t("strategy_reader.structure_table"))}</caption><thead><tr><th scope="col">{escape(translator.t("strategy_reader.field"))}</th><th scope="col">{escape(translator.t("strategy_reader.value"))}</th></tr></thead><tbody>{rows}</tbody></table>'


def _links(
    view: StrategyReaderViewModel,
    context: QueryContext,
    translator: Translator,
    page: ReaderPage,
) -> str:
    genome_id = view.genome_id
    query = dict(_query_pairs(context))
    genome_id = genome_id or query.get("genome_id")
    if page is ReaderPage.COMPARISON:
        left_id = query.get("left_genome_id")
        right_id = query.get("right_genome_id")
        left_href = genome_link(left_id, query_context=context)
        right_href = genome_link(right_id, query_context=context)
        left_conditions = genome_conditions_link(left_id, query_context=context)
        right_conditions = genome_conditions_link(right_id, query_context=context)
        comparison_href = genome_comparison_link(left_id, right_id, query_context=context)
        evidence_href = _context_url(context, view="evidence")
        return (
            f'<nav class="strategy-reader-links" aria-label="{escape(translator.t("strategy_reader.related_aria"))}">'
            f'<a class="comparison-left-genome-link" href="{escape(left_href, quote=True)}">{escape(translator.t("strategy_reader.genome_link"))}</a>'
            f'<a class="comparison-right-genome-link" href="{escape(right_href, quote=True)}">{escape(translator.t("strategy_reader.genome_link"))}</a>'
            f'<a class="comparison-left-conditions-link" href="{escape(left_conditions, quote=True)}">{escape(translator.t("strategy_reader.conditions_link"))}</a>'
            f'<a class="comparison-right-conditions-link" href="{escape(right_conditions, quote=True)}">{escape(translator.t("strategy_reader.conditions_link"))}</a>'
            f'<a class="comparison-link" href="{escape(comparison_href, quote=True)}">{escape(translator.t("strategy_reader.comparison_link"))}</a>'
            f'<a class="comparison-evidence-link" href="{escape(evidence_href, quote=True)}">{escape(translator.t("strategy_reader.evidence_link"))}</a></nav>'
        )
    if genome_id is None:
        return ""
    genome_href = genome_link(genome_id, query_context=context)
    condition_href = genome_conditions_link(genome_id, query_context=context)
    comparison_href = genome_comparison_link(genome_id, None, query_context=context)
    evidence_href = _context_url(context, view="evidence")
    genome_class = "genome-self-link" if page is ReaderPage.GENOME else "condition-genome-link"
    condition_class = "genome-conditions-link" if page is ReaderPage.GENOME else "condition-conditions-link"
    comparison_class = "genome-comparison-link" if page is ReaderPage.GENOME else "condition-comparison-link"
    return (
        f'<nav class="strategy-reader-links" aria-label="{escape(translator.t("strategy_reader.related_aria"))}">'
        f'<a class="{genome_class}" href="{escape(genome_href, quote=True)}">{escape(translator.t("strategy_reader.expert_link"))}</a>'
        f'<a class="{condition_class}" href="{escape(condition_href, quote=True)}">{escape(translator.t("strategy_reader.conditions_link"))}</a>'
        f'<a class="{comparison_class}" href="{escape(comparison_href, quote=True)}">{escape(translator.t("strategy_reader.comparison_link"))}</a>'
        f'<a class="strategy-reader-evidence-link" href="{escape(evidence_href, quote=True)}">{escape(translator.t("strategy_reader.evidence_link"))}</a></nav>'
    )


def _validation_section(view: StrategyReaderViewModel, translator: Translator) -> str:
    lifecycle = _lifecycle_value(view)
    validity_fields = (
        ("qualification", translator.t("strategy_reader.qualification"), view.qualification),
        ("currency", translator.t("strategy_reader.currency"), view.currency),
        ("lifecycle", translator.t("strategy_reader.lifecycle"), lifecycle),
    )
    if not view.validation and all(value is None for _, _, value in validity_fields):
        body = f'<p class="strategy-reader-not-recorded">{escape(translator.t("strategy_reader.effectiveness_unknown"))}</p>'
    else:
        validation_rows = "".join(
            f'<div><dt>{escape(translator.label("genome_validation", key))}</dt><dd>{_display(value, translator)}</dd></div>'
            for key, value in view.validation.items()
        )
        recorded_rows = "".join(
            f'<div><dt>{escape(label)}</dt><dd>{_display(value, translator)}</dd></div>'
            for _, label, value in validity_fields
        )
        body = f'<dl class="strategy-reader-validation">{validation_rows}{recorded_rows}</dl><p>{escape(translator.t("strategy_reader.effectiveness_boundary"))}</p>'
    return f'<section class="strategy-reader-validity" aria-labelledby="strategy-reader-validity-title"><h3 id="strategy-reader-validity-title">{escape(translator.t("strategy_reader.validity_title"))}</h3><p>{escape(translator.t("strategy_reader.validity_intro"))}</p>{body}</section>'


def _condition_section(view: StrategyReaderViewModel, translator: Translator) -> str:
    groups = (
        ("applicability", view.applicability),
        ("invalidation", view.invalidation),
        ("counterexample", view.counterexamples),
        ("descriptor", view.descriptors),
        ("unclassified", view.unclassified),
    )
    sections: list[str] = []
    for category, items in groups:
        if not items:
            body = f'<p data-condition-state="not_recorded">{escape(translator.t("strategy_reader.not_recorded"))}</p>'
        else:
            body = "<ul>" + "".join(
                f'<li data-condition-category="{category}" data-condition-outcome="{escape(_text(item.get("outcome", item.get("result", item.get("status")))) or "not_recorded", quote=True)}">'
                f'<strong>{_display(item.get("condition", item.get("statement", item.get("description"))), translator)}</strong>'
                f'<span>{_display(item.get("outcome", item.get("result", item.get("status"))), translator)}</span>'
                f'<span>{_display(item.get("limitations", item.get("limits")), translator)}</span></li>'
                for item in items
            ) + "</ul>"
        sections.append(f'<section class="strategy-reader-condition-group" data-condition-group="{category}"><h4>{escape(translator.t("strategy_reader." + category))}</h4>{body}</section>')
    return f'<section class="strategy-reader-conditions" aria-labelledby="strategy-reader-conditions-title"><h3 id="strategy-reader-conditions-title">{escape(translator.t("strategy_reader.conditions_title"))}</h3><p>{escape(translator.t("strategy_reader.conditions_intro"))}</p>{"".join(sections)}</section>'


def _comparison_section(view: StrategyReaderViewModel, translator: Translator) -> str:
    payload = _mapping(view.read_model.data) or {}
    comparison = _mapping(payload.get("comparison")) or {}
    if not comparison:
        return f'<section class="strategy-reader-comparison" aria-labelledby="strategy-reader-comparison-title"><h3 id="strategy-reader-comparison-title">{escape(translator.t("comparison.title"))}</h3><p data-comparison-state="not_recorded">{escape(translator.t("strategy_reader.comparison_missing"))}</p><p>{escape(translator.t("strategy_reader.comparison_boundary"))}</p></section>'
    fields = (
        ("changed_paths", "comparison.changed_paths"),
        ("missing_axes", "comparison.missing_axes"),
        ("incompatible_axes", "comparison.incompatible_axes"),
        ("reason", "comparison.reason"),
    )
    rows = ""
    if comparison.get("result") is not None:
        result_value = str(comparison["result"])
        result_label = translator.label("comparison_result", result_value)
        rows += (
            f'<div data-comparison-axis="result"><dt>{escape(translator.t("comparison.result", result=result_label))}</dt>'
            f'<dd>{_display(comparison.get("result"), translator)}</dd></div>'
        )
    rows += "".join(
        f'<div data-comparison-axis="{escape(key, quote=True)}"><dt>{escape(translator.t(label))}</dt><dd>{_display(comparison.get(key), translator)}</dd></div>'
        for key, label in fields
        if comparison.get(key) is not None
    )
    return f'<section class="strategy-reader-comparison" aria-labelledby="strategy-reader-comparison-title"><h3 id="strategy-reader-comparison-title">{escape(translator.t("comparison.title"))}</h3><dl>{rows}</dl><p>{escape(translator.t("strategy_reader.comparison_boundary"))}</p></section>'


def _revision_graph_invalid(revisions: Sequence[StrategyRevision]) -> bool:
    identifiers = [revision.revision_id for revision in revisions if revision.revision_id is not None]
    known = set(identifiers)
    if len(identifiers) != len(known):
        return True
    if any(revision.parent_id is not None and revision.parent_id not in known for revision in revisions):
        return True
    if any(child not in known for revision in revisions for child in revision.children):
        return True
    parents = {revision.revision_id: revision.parent_id for revision in revisions if revision.revision_id is not None}
    for start in parents:
        seen: set[str] = set()
        current: str | None = start
        while current is not None:
            if current in seen:
                return True
            seen.add(current)
            current = parents.get(current)
    return False


def _revision_section(view: StrategyReaderViewModel, context: QueryContext, translator: Translator) -> str:
    if not view.revisions:
        body = f'<p data-revision-state="not_recorded">{escape(translator.t("strategy_reader.not_recorded"))}</p>'
    else:
        graph_notice = (
            f'<p class="strategy-revision-graph-gap" data-revision-state="invalid">{escape(translator.t("strategy_reader.revision_graph_gap"))}</p>'
            if _revision_graph_invalid(view.revisions)
            else ""
        )
        items = []
        for revision in view.revisions:
            rid = revision.revision_id or translator.t("strategy_reader.not_recorded")
            parent = revision.parent_id or translator.t("strategy_reader.root_revision")
            children = ", ".join(revision.children) if revision.children else None
            reason = revision.reason or translator.t("strategy_reader.reason_not_recorded")
            links = ""
            revision_genome_id = revision.genome_id or view.genome_id
            if revision_genome_id:
                links += f'<a href="{escape(genome_link(revision_genome_id, query_context=context), quote=True)}">{escape(translator.t("strategy_reader.genome_link"))}</a>'
                links += f'<a href="{escape(genome_conditions_link(revision_genome_id, query_context=context), quote=True)}">{escape(translator.t("strategy_reader.conditions_link"))}</a>'
            if revision.evidence is not None:
                links += f'<a href="{escape(_context_url(context, view="evidence"), quote=True)}">{escape(translator.t("strategy_reader.evidence_link"))}</a>'
            if revision_genome_id:
                links += f'<a href="{escape(genome_comparison_link(revision_genome_id, None, query_context=context), quote=True)}">{escape(translator.t("strategy_reader.comparison_link"))}</a>'
            items.append(
                f'<li class="strategy-revision" data-revision-id="{escape(rid, quote=True)}" data-parent-revision="{escape(parent, quote=True)}">'
                f'<h4 translate="no">{escape(rid)}</h4><p><strong>{escape(translator.t("strategy_reader.parent"))}</strong> <span translate="no">{escape(parent)}</span></p>'
                f'<p><strong>{escape(translator.t("strategy_reader.children"))}</strong> <span translate="no">{escape(children or translator.t("strategy_reader.not_recorded"))}</span></p>'
                f'<dl><div><dt>{escape(translator.t("strategy_reader.changes"))}</dt><dd>{_display(revision.changes, translator)}</dd></div>'
                f'<div><dt>{escape(translator.t("strategy_reader.reason"))}</dt><dd>{_display(reason, translator)}</dd></div>'
                f'<div><dt>{escape(translator.t("strategy_reader.evidence"))}</dt><dd>{_display(revision.evidence, translator)}</dd></div>'
                f'<div><dt>{escape(translator.t("strategy_reader.result"))}</dt><dd>{_display(revision.result, translator)}</dd></div>'
                f'<div><dt>{escape(translator.t("strategy_reader.limitations"))}</dt><dd>{_display(revision.limitations, translator)}</dd></div>'
                f'<div><dt>{escape(translator.t("strategy_reader.condition_refs"))}</dt><dd>{_display(revision.condition_refs, translator)}</dd></div></dl>'
                f'<p class="strategy-revision-links">{links}</p></li>'
            )
        body = f'{graph_notice}<ol class="strategy-revision-tree" aria-label="{escape(translator.t("strategy_reader.revisions_aria"))}">{"".join(items)}</ol>'
    return f'<section class="strategy-reader-revisions" aria-labelledby="strategy-reader-revisions-title"><h3 id="strategy-reader-revisions-title">{escape(translator.t("strategy_reader.revisions_title"))}</h3><p>{escape(translator.t("strategy_reader.revisions_intro"))}</p>{body}</section>'


def _comparison_result(model: ManagerReadModel) -> str | None:
    payload = _mapping(model.data) or {}
    comparison = _mapping(payload.get("comparison")) or payload
    value = _first_text(comparison, "result", "status", "comparison_status")
    return None if value is None else value.lower().replace("-", "_").replace(" ", "_")


def render_strategy_reader(
    view_or_model: StrategyReaderViewModel | ManagerReadModel,
    *,
    query_context: QueryContext = None,
    translator: Translator | None = None,
    page: ReaderPage | str = ReaderPage.GENOME,
    projection: ReaderProjection | None = None,
) -> str:
    """Render the Strategy/Genome Reader surface and linked semantic sections."""

    selected = translator or Translator()
    view = view_or_model if isinstance(view_or_model, StrategyReaderViewModel) else StrategyReaderViewModel.from_read_model(view_or_model)
    model = view.read_model
    reader_projection = projection or project_strategy_reader(model)
    recorded_fields = selected.join(
        selected.label("genome_behavior", behavior_field.name)
        for behavior_field in view.behavior
        if behavior_field.recorded
    )
    sentence = (
        _display(view.owner_summary, selected)
        if view.owner_summary
        else escape(selected.t("strategy_reader.structure_sentence", text=recorded_fields or selected.t("strategy_reader.not_recorded")))
    )
    comparison_result = _comparison_result(model) if ReaderPage(page) is ReaderPage.COMPARISON else None
    status = render_status_block(model, translator=selected)
    if comparison_result == "incomparable":
        status += render_status_block(
            ReadModelStatus.INCOMPARABLE,
            translator=selected,
            reason="The declared comparison axes are not complete or compatible.",
            complete=False,
        )
    legacy_hook = {
        ReaderPage.GENOME: "strategy-genome-view",
        ReaderPage.CONDITIONS: "strategy-genome-conditions-view",
        ReaderPage.COMPARISON: "strategy-genome-comparison-view",
    }.get(ReaderPage(page), STRATEGY_READER_HOOK)
    comparison_attribute = (
        f' data-comparison-result="{escape(comparison_result, quote=True)}"'
        if comparison_result
        else ""
    )
    return "".join(
        (
            f'<section class="strategy-reader-page" data-integration-hook="{legacy_hook}" data-reader-hook="{STRATEGY_READER_HOOK}" data-reader-page="{ReaderPage(page).value}" data-genome-id="{escape(view.genome_id or "", quote=True)}"{comparison_attribute}>',
            f'<h1>{escape(selected.t("strategy_reader.title"))}</h1>',
            status,
            f'<p class="strategy-reader-sentence" data-boundary="strategy-structure">{sentence}</p>',
            render_reader_surface(reader_projection, page=page, query_context=query_context, translator=selected),
            f'<section class="strategy-reader-structure" aria-labelledby="strategy-reader-structure-title"><h3 id="strategy-reader-structure-title">{escape(selected.t("strategy_reader.structure_title"))}</h3><p>{escape(selected.t("strategy_reader.structure_intro"))}</p>{_field_table(view, selected)}</section>',
            _validation_section(view, selected),
            _condition_section(view, selected),
            _comparison_section(view, selected),
            _revision_section(view, query_context, selected),
            _links(view, query_context, selected, ReaderPage(page)),
            "</section>",
        )
    )


def render_strategy_reader_view(
    source: ManagerReadModel,
    *,
    query_context: QueryContext = None,
    translator: Translator | None = None,
    page: ReaderPage | str = ReaderPage.GENOME,
) -> str:
    return render_strategy_reader(source, query_context=query_context, translator=translator, page=page)


# Compatibility aliases make the seam discoverable alongside the existing S2 hooks.
project_genome_reader = project_strategy_reader
render_genome_reader = render_strategy_reader
render_strategy_reader_page = render_strategy_reader_view
StrategyGenomeReaderViewModel = StrategyReaderViewModel
GenomeRevision = StrategyRevision

__all__ = [
    "STRATEGY_READER_HOOK",
    "STRATEGY_READER_RESOURCE",
    "STRATEGY_READER_RULE",
    "STRATEGY_READER_VERSION",
    "GenomeRevision",
    "StrategyField",
    "StrategyGenomeReaderViewModel",
    "StrategyReaderSection",
    "StrategyReaderViewModel",
    "StrategyRevision",
    "project_genome_reader",
    "project_strategy_reader",
    "render_genome_reader",
    "render_strategy_reader",
    "render_strategy_reader_page",
    "render_strategy_reader_view",
]
