"""Reader-mode adapter for the read-only Strategy Reporting Portal.

The existing :mod:`portal` module remains the Portal Expert projection.  This
module adds the UI-owned Reader framing and typed object/availability claims;
it never opens a generated artifact and never exposes a rebuild, run, publish,
or revalidation operation.
"""

# HTML fragments intentionally remain readable at the call site.
# ruff: noqa: E501

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from html import escape
from typing import Any, TypeAlias, cast

from ..models import Derivation, ManagerReadModel
from ..provider import ManagerDataProvider
from ..reader import (
    ClaimKind,
    FrozenJSON,
    ProjectionMode,
    ReaderAvailability,
    ReaderAvailabilityStatus,
    ReaderClaim,
    ReaderProjection,
    SampleData,
    project_read_model,
)
from ..reader.mode import ReaderURLState
from .i18n import Translator
from .i18n.catalog.l5_portal_reader import ENTRIES as PORTAL_READER_CATALOG
from .material_reading import render_material_details
from .navigation import ViewId, context_link, query_values
from .portal import (
    PORTAL_RESOURCE,
    PortalArtifactState,
    PortalViewModel,
    ReportSourceProvider,
    _portal_index_items,
    render_portal,
    report_source_view,
)
from .reader_surface import ReaderPage, render_reader_surface
from .source_support import source_support_entry, source_support_impact, source_support_usable
from .status import render_status_block

QueryContext: TypeAlias = str | Mapping[str, object] | None

PORTAL_READER_RESOURCE = PORTAL_RESOURCE
PORTAL_READER_RULE = "manager-gui.reader.portal.v1"
PORTAL_READER_VERSION = "v1"
PORTAL_READER_HOOK = "portal-reader-view"
PORTAL_READER_INTEGRATION_HOOK = "portal-view"


def _portal_reader_translator(translator: Translator | None) -> Translator:
    selected = translator or Translator()
    from .i18n.catalog import CATALOG
    from .i18n.catalog.l5_portal import ENTRIES as PORTAL_CATALOG

    return Translator(
        selected.locale,
        strict=selected.strict,
        pseudo=selected.pseudo,
        catalog={**CATALOG, **PORTAL_CATALOG, **PORTAL_READER_CATALOG},
    )


def _source_availability(model: ManagerReadModel) -> ReaderAvailability:
    return ReaderAvailability.from_v0(model.availability)


def _claim_availability(model: ManagerReadModel) -> ReaderAvailability:
    selected = _source_availability(model)
    if selected.status in {
        ReaderAvailabilityStatus.KNOWN,
        ReaderAvailabilityStatus.DERIVED,
        ReaderAvailabilityStatus.INTERPRETED,
    }:
        return ReaderAvailability(
            ReaderAvailabilityStatus.DERIVED,
            selected.complete,
            selected.reason,
            selected.retryable,
        )
    return selected


def _gap_availability(model: ManagerReadModel, reason: str) -> ReaderAvailability:
    selected = _source_availability(model)
    status = selected.status
    if status in {
        ReaderAvailabilityStatus.KNOWN,
        ReaderAvailabilityStatus.DERIVED,
        ReaderAvailabilityStatus.INTERPRETED,
    }:
        status = ReaderAvailabilityStatus.MISSING
    return ReaderAvailability(status, False, reason or selected.reason, selected.retryable)


def _gap_kind(status: ReaderAvailabilityStatus) -> ClaimKind:
    if status in {
        ReaderAvailabilityStatus.BLOCKED,
        ReaderAvailabilityStatus.INTEGRITY_FAILURE,
    }:
        return ClaimKind.BLOCKED
    if status is ReaderAvailabilityStatus.STALE:
        return ClaimKind.STALE
    if status is ReaderAvailabilityStatus.INCOMPARABLE:
        return ClaimKind.INCOMPARABLE
    return ClaimKind.MISSING


def _claim(
    claim_id: str,
    *,
    kind: ClaimKind,
    source_refs,
    availability: ReaderAvailability,
    value: FrozenJSON,
    derivation: Derivation,
) -> ReaderClaim:
    return ReaderClaim(
        claim_id,
        kind,
        tuple(source_refs),
        derivation,
        availability,
        value,
    )


def project_portal_reader(
    model: ManagerReadModel,
    *,
    sample: bool = False,
    sample_state: str | None = None,
) -> ReaderProjection:
    """Project Portal metadata without turning publication into research state."""

    view = PortalViewModel.from_read_model(model)
    source_refs = tuple(model.source_refs)
    inputs = tuple(ref.source_id for ref in source_refs)
    source_availability = _source_availability(model)
    claim_availability = _claim_availability(model)
    derivation = Derivation(
        "derived",
        PORTAL_READER_RULE,
        inputs,
        PORTAL_READER_VERSION,
    )
    claims: list[ReaderClaim] = []
    unknowns: list[ReaderClaim] = []

    can_claim = claim_availability.status is ReaderAvailabilityStatus.DERIVED
    if source_refs and view.source_publication is not None and can_claim:
        publication = view.source_publication
        claims.append(
            _claim(
                "portal.source_publication",
                kind=ClaimKind.DERIVED,
                source_refs=source_refs,
                availability=claim_availability,
                value=cast(FrozenJSON, publication.to_dict()),
                derivation=Derivation(
                    "derived", PORTAL_READER_RULE, inputs, PORTAL_READER_VERSION
                ),
            )
        )
    elif source_refs:
        gap_availability = _gap_availability(
            model,
            "Source publication metadata is missing or unavailable in the current scope.",
        )
        unknowns.append(
            _claim(
                "portal.source_publication",
                kind=_gap_kind(gap_availability.status),
                source_refs=source_refs,
                availability=gap_availability,
                value=cast(FrozenJSON, {"object": "source_publication"}),
                derivation=Derivation("direct", None, inputs, PORTAL_READER_VERSION),
            )
        )

    if source_refs and view.generated_artifact is not None and can_claim:
        artifact = view.generated_artifact
        claims.append(
            _claim(
                "portal.generated_artifact",
                kind=ClaimKind.DERIVED,
                source_refs=source_refs,
                availability=claim_availability,
                value=cast(FrozenJSON, artifact.to_dict()),
                derivation=Derivation(
                    "derived", PORTAL_READER_RULE, inputs, PORTAL_READER_VERSION
                ),
            )
        )
        if view.artifact_state is PortalArtifactState.INTEGRITY_FAILURE:
            blocked = ReaderAvailability(
                ReaderAvailabilityStatus.INTEGRITY_FAILURE,
                False,
                "The generated artifact did not pass its declared integrity verification.",
                source_availability.retryable,
            )
            unknowns.append(
                _claim(
                    "portal.generated_artifact.integrity",
                    kind=ClaimKind.BLOCKED,
                    source_refs=source_refs,
                    availability=blocked,
                    value=cast(
                        FrozenJSON,
                        {"artifact_state": view.artifact_state.value},
                    ),
                    derivation=Derivation("direct", None, inputs, PORTAL_READER_VERSION),
                )
            )
    elif source_refs:
        gap_availability = _gap_availability(
            model,
            "Generated artifact metadata is missing or unavailable in the current scope."
            if view.generated_artifact is not None
            else "No generated report artifact is recorded in the current scope.",
        )
        unknowns.append(
            _claim(
                "portal.generated_artifact",
                kind=_gap_kind(gap_availability.status),
                source_refs=source_refs,
                availability=gap_availability,
                value=cast(
                    FrozenJSON,
                    {"artifact_state": view.artifact_state.value},
                ),
                derivation=Derivation("direct", None, inputs, PORTAL_READER_VERSION),
            )
        )

    if source_refs and not model.availability.complete and model.availability.status.value == "known":
        scope_gap = _gap_availability(
            model, "The report-source scope is incomplete; unavailable metadata is not inferred."
        )
        unknowns.append(
            _claim(
                "portal.scope",
                kind=_gap_kind(scope_gap.status),
                source_refs=source_refs,
                availability=scope_gap,
                value=cast(FrozenJSON, {"complete": False}),
                derivation=Derivation("direct", None, inputs, PORTAL_READER_VERSION),
            )
        )

    projection = project_read_model(
        model,
        claims=tuple(claims),
        unknowns=tuple(unknowns),
    )
    projection = replace(projection, derivation=derivation)
    if sample:
        projection = replace(
            projection,
            sample_data=SampleData(sample_state or "complete", PORTAL_READER_RESOURCE),
        )
    return projection


@dataclass(frozen=True, slots=True)
class PortalReaderViewModel:
    """Typed Portal Reader view over one unchanged v0 report-source envelope."""

    read_model: ManagerReadModel
    portal: PortalViewModel

    @classmethod
    def from_read_model(cls, model: ManagerReadModel) -> PortalReaderViewModel:
        return cls(model, PortalViewModel.from_read_model(model))

    @property
    def report_id(self) -> str | None:
        return self.portal.report_id

    @property
    def source_publication(self):
        return self.portal.source_publication

    @property
    def generated_artifact(self):
        return self.portal.generated_artifact

    @property
    def artifact_state(self) -> PortalArtifactState:
        return self.portal.artifact_state

    @property
    def reports(self):
        return self.portal.reports

    @property
    def source_refs(self):
        return self.read_model.source_refs

    def to_dict(self) -> dict[str, object]:
        return self.portal.to_dict()


def _machine(value: object, translator: Translator) -> str:
    if value is None or value == "":
        return escape(translator.t("reader.portal.missing"))
    return f'<span translate="no" data-owner-text="true">{escape(str(value))}</span>'


def _context_markup(
    view: PortalReaderViewModel,
    *,
    query_context: QueryContext,
    translator: Translator,
) -> str:
    source_links = []
    for source in view.source_refs:
        if support := source_support_entry(source.source_id):
            source_links.append(f"<li>{support}</li>")
            continue
        target = context_link(query_context, view=ViewId.EVIDENCE, source_id=source.source_id)
        source_links.append(
            f'<li><a data-link-kind="source-ref" href="{escape(target, quote=True)}" translate="no">'
            f'{escape(source.source_id)}</a></li>'
        )
    sources = (
        f'<ul class="portal-reader-source-refs">{"".join(source_links)}</ul>'
        if source_links
        else f'<span>{escape(translator.t("reader.portal.missing"))}</span>'
    )
    availability = view.read_model.availability
    derivation = view.read_model.derivation
    return (
        '<section class="portal-reader-context" aria-labelledby="portal-reader-context-title">'
        f'<h2 id="portal-reader-context-title">{escape(translator.t("reader.portal.scope"))}</h2>'
        '<dl>'
        f'<div><dt>{escape(translator.t("reader.portal.as_of"))}</dt><dd>{_machine(view.read_model.as_of, translator)}</dd></div>'
        f'<div><dt>{escape(translator.t("reader.portal.snapshot"))}</dt><dd>{_machine(view.read_model.snapshot_token, translator)}</dd></div>'
        f'<div><dt>{escape(translator.t("reader.portal.availability"))}</dt><dd><span translate="no">{escape(availability.status.value)}</span></dd></div>'
        f'<div><dt>{escape(translator.t("reader.portal.derivation"))}</dt><dd><code translate="no">{escape(derivation.rule or translator.t("reader.portal.missing"))}</code></dd></div>'
        f'<div><dt>{escape(translator.t("reader.portal.source_refs"))}</dt><dd>{sources}</dd></div>'
        '</dl></section>'
    )


def _verification_failed(record: Mapping[str, object]) -> bool:
    for key in ("verify_status", "verification_status", "verify", "verification"):
        value = record.get(key)
        if isinstance(value, Mapping):
            value = value.get("status", value.get("state", value.get("result")))
        if isinstance(value, str) and value.lower().replace("-", "_") in {
            "failed", "failure", "fail", "invalid", "digest_mismatch", "hash_mismatch",
        }:
            return True
    return False


def _object_markup(
    record: Mapping[str, object],
    *,
    kind: str,
    artifact_state: PortalArtifactState,
    report_id: str | None,
    query_context: QueryContext,
    translator: Translator,
) -> str:
    """Retain metadata selectors, never turn a locator into an original entry."""
    artifact = kind == "generated-artifact"
    id_key = "artifact_id" if artifact else "source_publication_id"
    id_keys = ("artifact_id", "artifactId", "id") if artifact else ("publication_id", "publicationId", "source_publication_id", "sourcePublicationId", "id", "source_ref", "source_id")
    identifier = None
    for key in id_keys:
        candidate = record.get(key)
        if isinstance(candidate, str) and candidate.strip():
            identifier = candidate
            break
    title = None
    for key in ("title", "name", "label"):
        candidate = record.get(key)
        if isinstance(candidate, str) and candidate.strip():
            title = candidate
            break
    heading = _machine(title, translator) if title else escape(translator.t("reader.portal.untitled_material"))
    link = ""
    if isinstance(identifier, str) and identifier:
        updates = {"artifact_id": None, "source_publication_id": None, id_key: identifier}
        target = context_link(query_context, view="portal", report_id=report_id, **updates)
        link = (
            f'<a class="portal-metadata-link" data-link-kind="{kind}" '
            f'href="{escape(target, quote=True)}">{escape(translator.t("reader.portal.open_artifact" if artifact else "reader.portal.open_source"))}</a>'
        )
    failed = _verification_failed(record)
    usable = source_support_usable(record) and not failed
    has_original = False
    for name in ("text", "content", "original_text", "original_source_id"):
        candidate = record.get(name)
        if isinstance(candidate, str) and candidate.strip():
            has_original = True
            break
    readability_key = "verify_failed" if failed else "original_blocked" if not usable else None if has_original else "original_missing"
    source_id = record.get("source_ref", record.get("source_id", identifier))
    support = (
        source_support_entry(source_id, record=record)
        if usable and isinstance(source_id, str) and source_id
        else None
    )
    readability = f'<p>{escape(translator.t("reader.portal." + readability_key))}</p>' if readability_key else ""
    state = "integrity-failure" if failed else artifact_state.value if artifact else "published"
    return (
        f'<article class="portal-{kind}" data-{"artifact-id" if artifact else "source-publication-id"}="{escape(str(identifier or ""), quote=True)}" '
        f'data-{"artifact-state" if artifact else "source-publication-state"}="{state}">'
        f'<h3>{heading}</h3>{render_material_details(record, translator)}'
        f'{readability}{source_support_impact(record)}{support or ""}'
        f'<details><summary>{escape(translator.t("reader.portal.technical"))}</summary>'
        f'<p>{escape(translator.t("reader.portal.artifact_object" if artifact else "reader.portal.publication_object"))}</p>'
        f'{link}</details></article>'
    )


def _material_gap(view: PortalReaderViewModel, translator: Translator, query_context: QueryContext) -> str:
    entries = [source_support_entry(source.source_id) for source in view.source_refs]
    context = query_values(query_context)
    selection_gap = f'<p>{escape(translator.t("reader.portal.selection_missing"))}</p>' if any(context.get(key) for key in ("report_id", "source_publication_id", "artifact_id")) else ""
    return (
        selection_gap + f'<p>{escape(translator.t("reader.portal.no_material"))}</p>'
        + source_support_impact()
        + "".join(f'<p>{entry}</p>' for entry in entries if entry)
    )


def _metadata_markup(
    view: PortalReaderViewModel,
    *,
    query_context: QueryContext,
    translator: Translator,
) -> str:
    payload = view.read_model.data
    if not isinstance(payload, Mapping):
        return _material_gap(view, translator, query_context)
    records = _portal_index_items(payload)
    if not records and not any(key in payload for key in ("reports", "report_index", "reportIndex", "entries", "items")):
        records = (payload,) if payload else ()
    if not records:
        return _material_gap(view, translator, query_context)
    context = query_values(query_context)
    selectors = {key: context[key] for key in ("report_id", "source_publication_id", "artifact_id") if context.get(key)}
    matches = []
    for index, entry in enumerate(view.reports):
        identities = {
            "report_id": entry.report_id,
            "source_publication_id": entry.source_publication.publication_id if entry.source_publication else None,
            "artifact_id": entry.generated_artifact.artifact_id if entry.generated_artifact else None,
        }
        if selectors and all(identities[key] == value for key, value in selectors.items()):
            matches.append(index)
    order = list(range(len(records)))
    if matches:
        order = [index for index in order if index in matches] + [index for index in order if index not in matches]
    selection_gap = f'<p>{escape(translator.t("reader.portal.selection_missing"))}</p>' if selectors and not matches else ""
    cards = []
    for index in order:
        supplied_record = records[index]
        # Match the existing Portal parser's wrapper/child precedence while
        # retaining supplied fields for reading and support, not a typed copy.
        nested = supplied_record.get("report")
        record = {**supplied_record, **nested} if isinstance(nested, Mapping) else supplied_record
        entry = view.reports[index] if index < len(view.reports) else None
        state = entry.artifact_state if entry is not None else view.artifact_state
        title = record.get("title") or (entry.title if entry is not None else None)
        heading = (
            _machine(title, translator)
            if isinstance(title, str) and title.strip()
            else escape(translator.t("reader.portal.untitled_material"))
        )
        report_id = entry.report_id if entry is not None else record.get("report_id", record.get("reportId", record.get("id")))
        source_id = record.get("source_ref", record.get("source_id", report_id))
        failed = _verification_failed(record)
        usable = source_support_usable(record) and not failed
        support = (
            source_support_entry(source_id, record=record)
            if usable and isinstance(source_id, str) and source_id
            else None
        )
        readability = (
            f'<p>{escape(translator.t("reader.portal.verify_failed" if failed else "reader.portal.original_blocked"))}</p>'
            if not usable else ""
        ) + source_support_impact(record)
        if usable and not any(record.get(key) for key in ("original_source_id", "original_text", "text", "content")):
            readability += f'<p>{escape(translator.t("reader.portal.original_missing"))}</p>'
        objects = ""
        selected_object = ""
        requested_kind = "generated-artifact" if "artifact_id" in selectors else "source-publication" if "source_publication_id" in selectors else None
        for kind, keys in (
            ("source-publication", ("source_publication", "sourcePublication", "report_source", "reportSource", "publication", "source")),
            ("generated-artifact", ("generated_artifact", "generatedArtifact", "report_artifact", "reportArtifact", "artifact", "generated")),
        ):
            for key in keys:
                item = record.get(key)
                if isinstance(item, Mapping):
                    markup = _object_markup(item, kind=kind, artifact_state=state, report_id=str(report_id) if report_id else None, query_context=query_context, translator=translator)
                    if index in matches and kind == requested_kind:
                        selected_object += markup
                    else:
                        objects += markup
                    break
        cards.append(
            f'<article class="portal-report-entry" data-report-id="{escape(str(report_id or ""), quote=True)}" data-portal-state="{state.value}">'
            f'<h2>{heading}</h2>{selected_object}{render_material_details(record, translator)}{readability}{support or ""}{objects}</article>'
        )
    return selection_gap + '<section class="portal-report-index">' + "".join(cards) + '</section>'


def _raw_markup(projection: ReaderProjection, *, translator: Translator) -> str:
    raw = projection.raw_source.raw_bytes.decode("utf-8")
    return (
        f'<section class="portal-reader-raw" data-reader-mode="raw">'
        f'<h2>{escape(translator.t("reader.portal.raw_heading"))}</h2>'
        f'<pre data-v0-schema="manager-gui.manager-read-model.v0" translate="no">{escape(raw)}</pre>'
        f'<p translate="no" data-raw-sha256="{escape(projection.raw_source.sha256, quote=True)}">{projection.raw_source.sha256}</p></section>'
    )


def _without_page_heading(markup: str) -> str:
    """Keep the Reader wrapper as the only document-level h1."""

    return re.sub(r'<h1\b[^>]*>.*?</h1>', "", markup, count=1, flags=re.DOTALL)


def render_portal_reader(
    source: ManagerDataProvider | ReportSourceProvider | PortalReaderViewModel | PortalViewModel | ManagerReadModel,
    *,
    base_path: str = "/?view=portal",
    query: QueryContext = None,
    query_context: QueryContext = None,
    translator: Translator | None = None,
    projection: ReaderProjection | None = None,
    mode: ProjectionMode | str | None = None,
    snapshot_token: str | None = None,
) -> str:
    """Render Portal Reader, Expert, or Raw from one public v0 envelope."""

    if isinstance(source, PortalReaderViewModel):
        view = source
    elif isinstance(source, PortalViewModel):
        view = PortalReaderViewModel(source.read_model, source)
    elif isinstance(source, ManagerReadModel):
        view = PortalReaderViewModel.from_read_model(source)
    else:
        view = PortalReaderViewModel.from_read_model(
            report_source_view(source, snapshot_token=snapshot_token).read_model
        )
    context = query_context if query_context is not None else query if query is not None else base_path
    selected = _portal_reader_translator(translator)
    reader_projection = projection or project_portal_reader(view.read_model)
    if isinstance(context, str):
        url_state = ReaderURLState.from_url(context)
    else:
        pairs = tuple(
            (str(key), str(value))
            for key, value in (context or {}).items()
            if value is not None
        )
        raw_mode = next((value for key, value in pairs if key == "mode"), None)
        try:
            selected_context_mode = (
                ProjectionMode(raw_mode) if raw_mode is not None else ProjectionMode.READER
            )
        except ValueError:
            selected_context_mode = ProjectionMode.READER
        url_state = ReaderURLState(pairs=pairs, mode=selected_context_mode)
    selected_mode = ProjectionMode(mode) if mode is not None else url_state.mode

    if selected_mode is ProjectionMode.RAW:
        body = _raw_markup(reader_projection, translator=selected)
    elif selected_mode is ProjectionMode.EXPERT:
        body = (
            f'<section class="portal-reader-expert"><h2>{escape(selected.t("reader.portal.expert_heading"))}</h2>'
            f'{_without_page_heading(render_portal(view.portal, query_context=context, translator=selected))}</section>'
        )
    else:
        body = (
            _metadata_markup(view, query_context=context, translator=selected)
            + f'<p>{escape(selected.t("reader.portal.generation_boundary"))}</p>'
            + '<details class="portal-reader-technical"><summary>'
            + escape(selected.t("reader.portal.technical")) + '</summary>'
            + render_status_block(view.read_model, translator=selected)
            + render_reader_surface(
                reader_projection,
                page=ReaderPage.PORTAL,
                query_context=context,
                translator=selected,
            )
            + _context_markup(view, query_context=context, translator=selected)
            + f'<section class="portal-reader-boundary" data-boundary="static-publication-not-canonical">'
            f'<h2>{escape(selected.t("reader.portal.boundary_heading"))}</h2>'
            f'<p>{escape(selected.t("reader.portal.boundary"))}</p>'
            f'<p>{escape(selected.t("reader.portal.rendered_copy"))}</p></section></details>'
            + f'<p class="portal-reader-read-only">{escape(selected.t("reader.portal.read_only"))}</p>'
        )
    return (
        f'<section class="portal-reader-page" data-reader-hook="{PORTAL_READER_HOOK}" '
        f'data-reader-contract="v1" data-integration-hook="{PORTAL_READER_INTEGRATION_HOOK}" '
        f'data-reader-mode="{selected_mode.value}" data-portal-state="{view.artifact_state.value}" '
        f'data-status="{view.read_model.availability.status.value}" aria-labelledby="portal-reader-title">'
        f'<div class="portal-page">'
        f'<p class="eyebrow">{escape(selected.t("reader.portal.eyebrow"))}</p>'
        f'<h1 id="portal-reader-title" data-page-title tabindex="-1">{escape(selected.t("reader.portal.title"))}</h1>'
        f'<p class="page-intro">{escape(selected.t("reader.portal.reading_intro" if selected_mode is ProjectionMode.READER else "reader.portal.confirmed_intro"))}</p>'
        f'{render_status_block(view.read_model, translator=selected) if selected_mode is ProjectionMode.RAW else ""}{body}</div></section>'
    )


def portal_reader_view(
    provider: ManagerDataProvider | ReportSourceProvider,
    *,
    snapshot_token: str | None = None,
) -> PortalReaderViewModel:
    return PortalReaderViewModel.from_read_model(
        report_source_view(provider, snapshot_token=snapshot_token).read_model
    )


def render_portal_reader_view(source: Any, **kwargs: Any) -> str:
    return render_portal_reader(source, **kwargs)


# Compatibility aliases parallel the existing Portal and Reader integration names.
project_reader_portal = project_portal_reader
project_portal = project_portal_reader
render_reader_portal = render_portal_reader
PortalReaderView = PortalReaderViewModel


__all__ = [
    "PORTAL_READER_HOOK",
    "PORTAL_READER_INTEGRATION_HOOK",
    "PORTAL_READER_RESOURCE",
    "PORTAL_READER_RULE",
    "PORTAL_READER_VERSION",
    "PortalReaderView",
    "PortalReaderViewModel",
    "portal_reader_view",
    "project_portal",
    "project_portal_reader",
    "project_reader_portal",
    "render_portal_reader",
    "render_portal_reader_view",
    "render_reader_portal",
]
