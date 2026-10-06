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
from typing import TypeAlias, cast

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
from .navigation import ViewId, context_link
from .portal import (
    PORTAL_RESOURCE,
    PortalArtifactState,
    PortalViewModel,
    ReportSourceProvider,
    _render_artifact,
    _render_publication,
    _render_report_index,
    render_portal,
    report_source_view,
)
from .reader_surface import ReaderPage, render_reader_surface
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


def _metadata_markup(
    view: PortalReaderViewModel,
    *,
    query_context: QueryContext,
    translator: Translator,
) -> str:
    indexed = _render_report_index(
        view.reports,
        query_context=query_context,
        translator=translator,
    )
    if indexed:
        return indexed
    return (
        _render_publication(
            view.source_publication,
            query_context=query_context,
            report_id=view.report_id,
            translator=translator,
        )
        + _render_artifact(
            view.generated_artifact,
            state=view.artifact_state,
            query_context=query_context,
            report_id=view.report_id,
            translator=translator,
        )
    )


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
        url_state = ReaderURLState(pairs=pairs, mode=raw_mode or ProjectionMode.READER)
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
            render_reader_surface(
                reader_projection,
                page=ReaderPage.PORTAL,
                query_context=context,
                translator=selected,
            )
            + _context_markup(view, query_context=context, translator=selected)
            + _metadata_markup(view, query_context=context, translator=selected)
            + f'<section class="portal-reader-boundary" data-boundary="static-publication-not-canonical">'
            f'<h2>{escape(selected.t("reader.portal.boundary_heading"))}</h2>'
            f'<p>{escape(selected.t("reader.portal.boundary"))}</p>'
            f'<p>{escape(selected.t("reader.portal.rendered_copy"))}</p></section>'
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
        f'<p class="page-intro">{escape(selected.t("reader.portal.confirmed_intro"))}</p>'
        f'{render_status_block(view.read_model, translator=selected)}{body}</div></section>'
    )


def portal_reader_view(
    provider: ManagerDataProvider | ReportSourceProvider,
    *,
    snapshot_token: str | None = None,
) -> PortalReaderViewModel:
    return PortalReaderViewModel.from_read_model(
        report_source_view(provider, snapshot_token=snapshot_token).read_model
    )


def render_portal_reader_view(source, **kwargs: object) -> str:
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
