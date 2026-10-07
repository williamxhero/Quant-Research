"""Reader-mode adapter for the public Methodology archive.

The existing :mod:`methodology` surface remains the Expert view.  This module
only adds a typed, UI-owned explanation layer over its ``ManagerReadModel``
envelope.  It never treats a method description, usage count, or document as a
research result and it never writes to the methodology source.
"""

# HTML fragments intentionally remain readable at the call site.
# ruff: noqa: E501

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from html import escape
from typing import TypeAlias, cast

from ..models import Derivation, JSONValue, ManagerReadModel, ReadModelStatus
from ..reader import (
    ClaimKind,
    FrozenJSON,
    ProjectionMode,
    ReaderAvailability,
    ReaderAvailabilityStatus,
    ReaderClaim,
    ReaderProjection,
    ReaderSummary,
    SampleData,
    project_read_model,
)
from ..reader.mode import ReaderURLState
from .i18n import Translator
from .locators import public_locator
from .material_reading import render_material_details
from .methodology import (
    METHODOLOGY_RESOURCE,
    MethodologyDocumentRef,
    MethodologyFixtureProvider,
    MethodologyFixtureState,
    MethodologyIndexState,
    MethodologyMethod,
    MethodologyRecordRef,
    MethodologyViewModel,
    build_methodology_fixture,
    render_methodology,
)
from .methodology import (
    _sequence as _methodology_sequence,
)
from .navigation import PageWindow, ViewId, context_link
from .reader_surface import ReaderPage, render_reader_surface
from .source_support import source_support_entry, source_support_impact, source_support_usable
from .status import render_status_block

QueryContext: TypeAlias = str | Mapping[str, object] | None
METHODOLOGY_READER_RESOURCE = METHODOLOGY_RESOURCE
METHODOLOGY_READER_RULE = "manager-gui.reader.methodology.v1"
METHODOLOGY_READER_VERSION = "v1"
METHODOLOGY_READER_HOOK = "methodology-reader-view"
METHODOLOGY_READER_INTEGRATION_HOOK = "methodology-view"
METHODOLOGY_SCOPES: tuple[str, ...] = ("A0", "S3", "CPA", "V1.x")


class MethodologyReaderSection(StrEnum):
    PROCESS = "workflow_process"
    STATISTICAL_PROTOCOL = "statistical_protocol"
    POLICY = "policy"
    BENCHMARK = "benchmark"
    OPERATIONAL_CONSTRAINT = "operational_constraint"


# Compatibility names parallel the older Methodology archive seam.
MethodologyReaderFixtureState = MethodologyFixtureState
METHODOLOGY_READER_FIXTURE_STATES = tuple(state.value for state in MethodologyFixtureState)


def _mapping(value: object) -> Mapping[str, object] | None:
    return cast(Mapping[str, object], value) if isinstance(value, Mapping) else None


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


def _json_value(value: object) -> JSONValue:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        return None
    return cast(JSONValue, value)


def _owner(value: object, translator: Translator) -> str:
    """Render owner/raw values without passing them through locale translation."""

    if value is None or value == "" or value == [] or value == {}:
        return escape(translator.t("reader.methodology.not_recorded"))
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return f'<span data-owner-text="true" translate="no">{escape(text)}</span>'


def _machine(value: object, translator: Translator) -> str:
    if value is None or value == "":
        return escape(translator.t("reader.methodology.not_recorded"))
    return f'<span translate="no">{escape(str(value))}</span>'


def _claim_availability(model: ManagerReadModel) -> ReaderAvailability:
    selected = ReaderAvailability.from_v0(model.availability)
    if selected.status in {ReaderAvailabilityStatus.DERIVED, ReaderAvailabilityStatus.INTERPRETED}:
        return ReaderAvailability(ReaderAvailabilityStatus.KNOWN, selected.complete, selected.reason, selected.retryable)
    return selected


def _gap_availability(model: ManagerReadModel, reason: str) -> ReaderAvailability:
    selected = ReaderAvailability.from_v0(model.availability)
    status = selected.status
    if status in {ReaderAvailabilityStatus.KNOWN, ReaderAvailabilityStatus.DERIVED, ReaderAvailabilityStatus.INTERPRETED}:
        status = ReaderAvailabilityStatus.MISSING
    if status is ReaderAvailabilityStatus.INTEGRITY_FAILURE:
        return ReaderAvailability(status, False, reason, selected.retryable)
    return ReaderAvailability(status, False, reason or selected.reason, selected.retryable)


def _gap_kind(status: ReaderAvailabilityStatus) -> ClaimKind:
    if status in {ReaderAvailabilityStatus.BLOCKED, ReaderAvailabilityStatus.INTEGRITY_FAILURE}:
        return ClaimKind.BLOCKED
    if status is ReaderAvailabilityStatus.STALE:
        return ClaimKind.STALE
    if status is ReaderAvailabilityStatus.INCOMPARABLE:
        return ClaimKind.INCOMPARABLE
    return ClaimKind.MISSING


def _direct_claim(
    claim_id: str,
    value: JSONValue,
    model: ManagerReadModel,
) -> ReaderClaim | None:
    if not model.source_refs or model.availability.status not in {
        ReadModelStatus.KNOWN,
        ReadModelStatus.DERIVED,
        ReadModelStatus.INTERPRETED,
    }:
        return None
    refs = tuple(model.source_refs)
    return ReaderClaim(
        claim_id,
        ClaimKind.KNOWN,
        refs,
        Derivation("direct", inputs=tuple(ref.source_id for ref in refs), version="v0"),
        _claim_availability(model),
        cast(FrozenJSON, value),
    )


def _gap_claim(claim_id: str, value: JSONValue, model: ManagerReadModel, reason: str) -> ReaderClaim | None:
    if not model.source_refs:
        return None
    availability = _gap_availability(model, reason)
    refs = tuple(model.source_refs)
    return ReaderClaim(
        claim_id,
        _gap_kind(availability.status),
        refs,
        Derivation("direct", inputs=tuple(ref.source_id for ref in refs), version="v0"),
        availability,
        cast(FrozenJSON, value),
    )


def _projection(
    model: ManagerReadModel,
    *,
    sample: bool,
    sample_state: str | None,
) -> ReaderProjection:
    view = MethodologyViewModel.from_read_model(model)
    claims: list[ReaderClaim] = []
    gaps: list[ReaderClaim] = []
    index_claim = _direct_claim(
        "methodology.index",
        cast(JSONValue, {"index_state": view.index_state.value, "method_count": len(view.methods)}),
        model,
    )
    if index_claim is not None:
        claims.append(index_claim)
    if view.methods:
        entries = _direct_claim(
            "methodology.entries",
            cast(JSONValue, {"method_ids": [method.method_id for method in view.methods]}),
            model,
        )
        if entries is not None:
            claims.append(entries)
    if not view.methods:
        gap = _gap_claim(
            "methodology.entries",
            {"index_state": view.index_state.value},
            model,
            "No published methodology entry is available in the current scope.",
        )
        if gap is not None:
            gaps.append(gap)
    elif not model.availability.complete:
        gap = _gap_claim(
            "methodology.scope",
            {"complete": False},
            model,
            model.availability.reason or "The methodology scope is incomplete.",
        )
        if gap is not None:
            gaps.append(gap)
    all_claims = (*claims, *gaps)
    summary = (
        ReaderSummary("reader.methodology.summary", tuple(claim.claim_id for claim in all_claims), {"n": len(all_claims)})
        if all_claims
        else None
    )
    projection = project_read_model(
        model,
        summary=summary,
        claims=tuple(claims),
        unknowns=tuple(gaps),
    )
    if sample:
        projection = replace(
            projection,
            sample_data=SampleData(sample_state or "complete", METHODOLOGY_READER_RESOURCE),
        )
    return projection


@dataclass(frozen=True, slots=True)
class MethodologyReaderViewModel:
    """Typed Methodology Reader view retaining the unchanged v0 envelope."""

    read_model: ManagerReadModel
    methodology: MethodologyViewModel
    scope: str | None = None

    @classmethod
    def from_read_model(cls, model: ManagerReadModel, *, scope: str | None = None) -> MethodologyReaderViewModel:
        payload = _mapping(model.data) or {}
        selected_scope = scope or _text(payload.get("scope")) or _text(payload.get("fixture"))
        return cls(model, MethodologyViewModel.from_read_model(model), selected_scope)

    @property
    def methods(self) -> tuple[MethodologyMethod, ...]:
        return self.methodology.methods

    @property
    def groups(self):
        return self.methodology.groups

    @property
    def index_state(self) -> MethodologyIndexState:
        return self.methodology.index_state

    @property
    def source_refs(self):
        return self.read_model.source_refs

    def to_dict(self) -> dict[str, object]:
        return {
            "view": METHODOLOGY_READER_RESOURCE,
            "scope": self.scope,
            "methodology": self.methodology.to_dict(),
            "availability": self.read_model.availability.to_dict(),
            "source_refs": [ref.to_dict() for ref in self.source_refs],
            "as_of": self.read_model.as_of,
            "snapshot_token": self.read_model.snapshot_token,
        }


def project_methodology_reader(
    model: ManagerReadModel,
    *,
    sample: bool = False,
    sample_state: str | None = None,
) -> ReaderProjection:
    return _projection(model, sample=sample, sample_state=sample_state)


def _scope_links(context: QueryContext, translator: Translator) -> str:
    links: list[str] = []
    for scope in METHODOLOGY_SCOPES:
        href = context_link(context, view=ViewId.METHODOLOGY, scope=scope)
        links.append(
            f'<a class="methodology-reader-scope-link" data-scope="{escape(scope, quote=True)}" '
            f'href="{escape(href, quote=True)}"><span translate="no">{escape(scope)}</span></a>'
        )
    return (
        f'<nav class="methodology-reader-scopes" aria-label="{escape(translator.t("reader.methodology.scope"), quote=True)}">'
        + "".join(links)
        + "</nav>"
    )


def _source_markup(view: MethodologyReaderViewModel, context: QueryContext, translator: Translator) -> str:
    if not view.source_refs:
        return f'<p class="methodology-reader-no-source">{escape(translator.t("reader.methodology.no_source"))}</p>'
    items: list[str] = []
    for ref in view.source_refs:
        if support := source_support_entry(ref.source_id):
            items.append(f"<li>{support}</li>")
            continue
        locator = public_locator(ref.locator)
        value = f'<span translate="no">{escape(ref.source_id)}</span>'
        if locator:
            value = f'<a href="{escape(locator, quote=True)}" translate="no">{escape(ref.source_id)}</a>'
        evidence = context_link(context, view=ViewId.EVIDENCE, source_id=ref.source_id)
        items.append(
            f'<li>{value} · <a href="{escape(evidence, quote=True)}">{escape(translator.t("reader.methodology.source"))}</a></li>'
        )
    return f'<ul class="methodology-reader-sources">{"".join(items)}</ul>'


def _child_records(record: Mapping[str, object], key: str, alias: str = "") -> tuple[object, ...]:
    # Match the existing typed archive parser, including public record containers.
    return _methodology_sequence(record.get(key, record.get(alias)))


def _record_support(record: Mapping[str, object], identifier: str) -> str:
    # Supply the exact visible record, never a generic envelope source list.
    source = record.get("source_ref", record.get("source_id"))
    if source is None:
        refs = record.get("source_refs", record.get("source_ids"))
        if isinstance(refs, (list, tuple)) and refs:
            source = refs[0]
    if isinstance(source, Mapping):
        source = source.get("source_id", source.get("id"))
    return source_support_entry(_text(source) or identifier, record=record) or ""


def _record_fields(record: Mapping[str, object], translator: Translator) -> str:
    fields = (
        ("check_scope", record.get("scope", record.get("study"))),
        ("period", record.get("period")),
        ("result", record.get("result", record.get("outcome"))),
    )
    return "".join(
        f'<div><dt>{escape(translator.t("reader.methodology." + key))}</dt>'
        f'<dd>{_owner(value, translator)}</dd></div>'
        for key, value in fields
    )


def _record_usable(record: Mapping[str, object], model: ManagerReadModel) -> bool:
    return model.availability.status is ReadModelStatus.KNOWN and not model.errors and source_support_usable(record)


def _reference_links(
    refs: tuple[MethodologyDocumentRef, ...] | tuple[MethodologyRecordRef, ...],
    translator: Translator,
    context: QueryContext,
) -> str:
    links: list[str] = []
    for ref in refs:
        document = isinstance(ref, MethodologyDocumentRef)
        kind = "document" if document else "record"
        title = ref.title if document else ref.label
        href = context_link(
            context,
            view=ViewId.SOURCE_DOCUMENTS if document else ViewId.HISTORY,
            **({"document_id": ref.document_id} if document else {"record_id": ref.record_id}),
        )
        label = (
            escape(translator.t("reader.methodology.read_" + kind)) + " " + _owner(title, translator)
            if title else escape(translator.t("reader.methodology.read_" + kind + "_unnamed"))
        )
        links.append(f'<a data-link-kind="{kind}" href="{escape(href, quote=True)}">{label}</a>')
    return " · ".join(links) or escape(translator.t("reader.methodology.related_missing"))


def _usage_markup(method: MethodologyMethod, translator: Translator, model: ManagerReadModel, context: QueryContext) -> str:
    if not method.usage_records:
        return f'<p data-reader-state="missing">{escape(translator.t("reader.methodology.usage_missing"))}</p>'
    records = _child_records(method.raw, "usage_records", "usages")
    items: list[str] = []
    for index, usage in enumerate(method.usage_records):
        record = _mapping(records[index]) or {}
        status = _text(record.get("execution_status", record.get("status", record.get("state"))))
        normalized = status.strip().lower().replace("-", "_").replace(" ", "_") if status else ""
        key = {
            "executed": "executed",
            "completed": "executed",
            "not_executed": "not_executed",
            "not_run": "not_executed",
            "skipped": "not_executed",
            "stopped": "stopped",
            "aborted": "stopped",
        }.get(normalized, "execution_missing")
        if not _record_usable(method.raw, model) or not _record_usable(record, model):
            key = "execution_unconfirmed"
        used_at = record.get("used_at", record.get("usedAt", record.get("date")))
        items.append(
            f'<li><p>{_owner(usage.summary, translator)}</p>'
            f'<p>{escape(translator.t("reader.methodology." + key))}</p><dl>'
            f'<div><dt>{escape(translator.t("reader.methodology.used_at"))}</dt><dd>{_owner(used_at, translator)}</dd></div>'
            f'{_record_fields(record, translator)}</dl>{source_support_impact(record)}{_record_support(record, usage.usage_id)}{_reference_links(usage.record_refs, translator, context)}</li>'
        )
    return f'<ul class="methodology-reader-usages">{"".join(items)}</ul>'


def _results_markup(method: MethodologyMethod, translator: Translator, context: QueryContext) -> str:
    if not method.associated_results:
        return f'<p>{escape(translator.t("reader.methodology.results_missing"))}</p>'
    records = _child_records(method.raw, "associated_results", "results")
    items: list[str] = []
    for index, result in enumerate(method.associated_results):
        record = _mapping(records[index]) or {}
        items.append(
            f'<li><h4>{_owner(result.title, translator)}</h4><p>{_owner(result.summary, translator)}</p>'
            f'<p>{escape(translator.t("reader.methodology.record_status"))}: {_owner(result.status, translator)}</p>'
            f'{render_material_details(record, translator)}{source_support_impact(record)}'
            f'{_record_support(record, result.result_id)}{_reference_links(result.record_refs, translator, context)}</li>'
        )
    return f'<ul class="methodology-reader-results">{"".join(items)}</ul>'


def _validity_markup(method: MethodologyMethod, translator: Translator, context: QueryContext) -> str:
    if not method.validity_evidence:
        return f'<p>{escape(translator.t("reader.methodology.validity_missing"))}</p>'
    records = _child_records(method.raw, "validity_evidence")
    items: list[str] = []
    for index, evidence in enumerate(method.validity_evidence):
        record = _mapping(records[index]) or {}
        items.append(
            f'<li><h4>{_owner(evidence.label, translator)}</h4><p>{_owner(evidence.summary, translator)}</p>'
            f'<p>{escape(translator.t("reader.methodology.record_status"))}: {_owner(evidence.status, translator)}</p>'
            f'{render_material_details(record, translator)}{source_support_impact(record)}'
            f'{_record_support(record, evidence.evidence_id)}'
            f'{_reference_links(evidence.document_refs, translator, context)}'
            f'{_reference_links(evidence.record_refs, translator, context)}</li>'
        )
    return f'<ul class="methodology-reader-validity">{"".join(items)}</ul>'


def _method_detail(method: MethodologyMethod, translator: Translator, context: QueryContext, model: ManagerReadModel) -> str:
    limitations = (*method.limitations, *method.failure_cases)
    limit_markup = (
        "<ul>" + "".join(f"<li>{_owner(value, translator)}</li>" for value in limitations) + "</ul>"
        if limitations
        else f'<span class="methodology-reader-missing">{escape(translator.t("reader.methodology.not_recorded"))}</span>'
    )
    usage = _usage_markup(method, translator, model, context)
    validity = _validity_markup(method, translator, context)
    lifecycle_key = (
        "reader.methodology.superseded" if method.superseded is True
        else "reader.methodology.current" if method.superseded is False
        else "reader.methodology.lifecycle_missing"
    )
    title = next((_text(method.raw.get(key)) for key in ("title", "name", "label") if _text(method.raw.get(key))), None)
    title_markup = _owner(title, translator) if title else escape(translator.t("reader.methodology.title_missing"))
    definition = _owner(method.definition, translator) if method.definition else escape(translator.t("reader.methodology.definition_missing"))
    checks = _child_records(method.raw, "checks", "check_steps")
    check_markup = "<ul>" + "".join(f"<li>{_owner(value, translator)}</li>" for value in checks) + "</ul>" if checks else escape(translator.t("reader.methodology.checks_missing"))
    document_links = _reference_links(method.document_refs, translator, context)
    record_links = _reference_links(method.record_refs, translator, context)
    return (
        f'<article class="methodology-reader-method" data-method-id="{escape(method.method_id, quote=True)}" '
        f'data-methodology-category="{escape(method.category.value, quote=True)}" '
        f'data-method-state="{"superseded" if method.superseded is True else "current" if method.superseded is False else "unknown"}">'
        + (f'<p class="sample-note">{escape(translator.t("plain.result.sample"))}</p>' if method.raw.get("fabricated_example") is True else "")
        + f'<h3>{title_markup}</h3>'
        f'<dl class="methodology-reader-details">'
        f'<div><dt>{escape(translator.t("reader.methodology.definition"))}</dt><dd>{definition}</dd></div>'
        f'<div><dt>{escape(translator.t("reader.methodology.checks"))}</dt><dd>{check_markup}</dd></div>'
        f'<div><dt>{escape(translator.t("reader.methodology.when"))}</dt><dd>{usage}</dd></div>'
        f'<div><dt>{escape(translator.t("reader.methodology.results"))}</dt><dd>{_results_markup(method, translator, context)}</dd></div>'
        f'<div><dt>{escape(translator.t("reader.methodology.limits"))}</dt><dd>{limit_markup}</dd></div>'
        f'<div><dt>{escape(translator.t("reader.methodology.validity"))}</dt><dd>{validity}</dd></div>'
        f'<div><dt>{escape(translator.t("reader.methodology.source"))}</dt><dd>{document_links}</dd></div>'
        f'<div><dt>{escape(translator.t("reader.methodology.source"))}</dt><dd>{record_links}</dd></div>'
        f'<div><dt>{escape(translator.t("reader.methodology.status"))}</dt><dd>{escape(translator.t(lifecycle_key))} · {_machine(method.version, translator)}</dd></div>'
        f'</dl><p>{escape(translator.t("reader.methodology.validity_boundary"))}</p>'
        f'{source_support_impact(method.raw)}{_record_support(method.raw, method.method_id)}</article>'
    )


def _methods_markup(view: MethodologyReaderViewModel, translator: Translator, context: QueryContext) -> str:
    if not view.methods:
        if view.index_state is MethodologyIndexState.NOT_INDEXED:
            key = "reader.methodology.no_entries"
        elif view.read_model.availability.status in {
            ReadModelStatus.API_UNAVAILABLE,
            ReadModelStatus.BLOCKED,
            ReadModelStatus.STALE,
            ReadModelStatus.INCOMPARABLE,
            ReadModelStatus.INTEGRITY_FAILURE,
        }:
            key = "methodology.error_scope"
        else:
            key = "methodology.empty_scope"
        return f'<p class="methodology-reader-no-entries">{escape(translator.t(key))}</p>{_source_markup(view, context, translator)}'
    sections: list[str] = []
    for group in view.groups:
        label = translator.t(f"reader.methodology.category.{group.category.value}")
        body = (
            f'<p class="methodology-reader-category-empty">{escape(translator.t("reader.methodology.not_recorded"))}</p>'
            if not group.methods
            else "".join(_method_detail(method, translator, context, view.read_model) for method in group.methods)
        )
        sections.append(
            f'<section class="methodology-reader-category" data-methodology-category="{escape(group.category.value, quote=True)}" '
            f'aria-labelledby="methodology-reader-category-{escape(group.category.value, quote=True)}">'
            f'<h3 id="methodology-reader-category-{escape(group.category.value, quote=True)}">{escape(label)}</h3>{body}</section>'
        )
    return "".join(sections)


def _raw_markup(projection: ReaderProjection, translator: Translator) -> str:
    raw = projection.raw_source.raw_bytes.decode("utf-8")
    return (
        f'<section class="methodology-reader-raw"><h2>{escape(translator.t("reader.methodology.raw_heading"))}</h2>'
        f'<pre data-v0-schema="manager-gui.manager-read-model.v0" translate="no">{escape(raw)}</pre>'
        f'<p translate="no" data-raw-sha256="{escape(projection.raw_source.sha256, quote=True)}">{projection.raw_source.sha256}</p></section>'
    )


def _related_links(context: QueryContext, translator: Translator) -> str:
    history = context_link(context, view=ViewId.HISTORY)
    documents = context_link(context, view=ViewId.SOURCE_DOCUMENTS)
    return (
        f'<nav class="methodology-reader-related" aria-label="{escape(translator.t("reader.methodology.scope"), quote=True)}">'
        f'<a data-link-kind="history" href="{escape(history, quote=True)}">{escape(translator.t("reader.methodology.open_history"))}</a>'
        f'<a data-link-kind="document" href="{escape(documents, quote=True)}">{escape(translator.t("reader.methodology.open_documents"))}</a></nav>'
    )


def render_methodology_reader(
    view_or_model: MethodologyReaderViewModel | ManagerReadModel,
    *,
    query_context: QueryContext = None,
    translator: Translator | None = None,
    projection: ReaderProjection | None = None,
    mode: ProjectionMode | str | None = None,
) -> str:
    """Render Methodology Reader, Expert, or Raw without changing v0 data."""

    selected = translator or Translator()
    view = view_or_model if isinstance(view_or_model, MethodologyReaderViewModel) else MethodologyReaderViewModel.from_read_model(view_or_model)
    reader_projection = projection or project_methodology_reader(view.read_model)
    state = ReaderURLState.from_url(query_context) if isinstance(query_context, str) else ReaderURLState(pairs=tuple((str(k), str(v)) for k, v in (query_context or {}).items() if v is not None))
    selected_mode = ProjectionMode(mode) if mode is not None else state.mode
    if selected_mode is ProjectionMode.RAW:
        body = _raw_markup(reader_projection, selected)
    elif selected_mode is ProjectionMode.EXPERT:
        body = f'<section class="methodology-reader-expert"><h2>{escape(selected.t("reader.methodology.expert_heading"))}</h2>{render_methodology(view.methodology, query_context=query_context, translator=selected)}</section>'
    else:
        body = (
            f'<details class="methodology-reader-technical"><summary>{escape(selected.t("reader.methodology.technical"))}</summary>'
            + render_reader_surface(reader_projection, page=ReaderPage.METHODOLOGY, query_context=query_context, translator=selected)
            + '</details>'
            + f'<section class="methodology-reader-scope" aria-labelledby="methodology-reader-scope-title"><h2 id="methodology-reader-scope-title">{escape(selected.t("reader.methodology.scope"))}</h2>'
            f'<p>{escape(selected.t("reader.methodology.scope_intro"))}</p>{_scope_links(query_context, selected)}</section>'
            f'<section class="methodology-reader-methods" aria-labelledby="methodology-reader-methods-title"><h2 id="methodology-reader-methods-title">{escape(selected.t("reader.methodology.categories"))}</h2>{_methods_markup(view, selected, query_context)}{PageWindow.from_query(query_context, total=len(view.methods)).render(query_context, view=ViewId.METHODOLOGY, translator=selected)}</section>'
            f'<p class="methodology-reader-boundary" data-boundary="canonical-fact">{escape(selected.t("reader.methodology.read_only"))}</p>'
        )
    # The unchanged Expert child owns its status heading; do not duplicate its ID.
    status = "" if selected_mode is ProjectionMode.EXPERT else render_status_block(view.read_model, translator=selected)
    scope = view.scope or ""
    context = (
        f'<p class="methodology-reader-context"><span><strong>{escape(selected.t("reader.methodology.as_of"))}</strong> '
        f'{_machine(view.read_model.as_of, selected)}</span><span><strong>{escape(selected.t("reader.methodology.snapshot"))}</strong> '
        f'{_machine(view.read_model.snapshot_token, selected)}</span><span data-scope="{escape(scope, quote=True)}"><strong>{escape(selected.t("reader.methodology.scope"))}</strong> '
        f'{_machine(scope, selected)}</span></p>'
    )
    if selected_mode is ProjectionMode.READER:
        context = (
            source_support_impact()
            + f'<details><summary>{escape(selected.t("reader.methodology.technical"))}</summary>'
            + status + context + '</details>'
        )
        status = ""
    return (
        f'<section class="methodology-reader-page" data-reader-hook="{METHODOLOGY_READER_HOOK}" '
        f'data-integration-hook="{METHODOLOGY_READER_INTEGRATION_HOOK}" data-reader-mode="{selected_mode.value}" '
        f'data-index-state="{view.index_state.value}" data-status="{view.read_model.availability.status.value}">'
        f'<p class="eyebrow">{escape(selected.t("reader.methodology.eyebrow"))}</p>'
        f'<h1 data-page-title tabindex="-1">{escape(selected.t("reader.methodology.title"))}</h1>'
        f'<p class="page-intro">{escape(selected.t("reader.methodology.confirmed_intro"))}</p>'
        f'{status}{context}{body}{_related_links(query_context, selected)}</section>'
    )


def methodology_reader_view(provider, *, snapshot_token: str | None = None) -> MethodologyReaderViewModel:
    return MethodologyReaderViewModel.from_read_model(provider.read(METHODOLOGY_READER_RESOURCE, snapshot_token=snapshot_token))


def render_methodology_reader_view(
    source,
    *,
    query_context: QueryContext = None,
    snapshot_token: str | None = None,
    translator: Translator | None = None,
    projection: ReaderProjection | None = None,
    mode: ProjectionMode | str | None = None,
) -> str:
    view = source if isinstance(source, MethodologyReaderViewModel) else (
        MethodologyReaderViewModel.from_read_model(source)
        if isinstance(source, ManagerReadModel)
        else methodology_reader_view(source, snapshot_token=snapshot_token)
    )
    return render_methodology_reader(view, query_context=query_context, translator=translator, projection=projection, mode=mode)


def build_methodology_reader_fixture(state: MethodologyReaderFixtureState | str) -> ManagerReadModel:
    return build_methodology_fixture(state)


def methodology_reader_fixture_provider(state: MethodologyReaderFixtureState | str) -> MethodologyFixtureProvider:
    return MethodologyFixtureProvider(state)


project_reader_methodology = project_methodology_reader
render_reader_methodology = render_methodology_reader

__all__ = [
    "METHODOLOGY_READER_FIXTURE_STATES",
    "METHODOLOGY_READER_HOOK",
    "METHODOLOGY_READER_INTEGRATION_HOOK",
    "METHODOLOGY_READER_RESOURCE",
    "METHODOLOGY_READER_RULE",
    "METHODOLOGY_READER_VERSION",
    "METHODOLOGY_SCOPES",
    "MethodologyReaderFixtureState",
    "MethodologyReaderSection",
    "MethodologyReaderViewModel",
    "build_methodology_reader_fixture",
    "methodology_reader_fixture_provider",
    "methodology_reader_view",
    "project_methodology_reader",
    "project_reader_methodology",
    "render_methodology_reader",
    "render_methodology_reader_view",
    "render_reader_methodology",
]
