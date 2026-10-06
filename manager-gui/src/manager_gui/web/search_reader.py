"""Reader-mode adapter for the deterministic Search surface.

The existing :mod:`search` module remains the Search Expert projection.  This
module adds only the UI-owned Reader explanation layer: a hit is a typed,
reproducible index match with field and scope provenance, never a research
conclusion.  It does not scan storage, call an LLM, or mutate the Search index.
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
from .navigation import ViewId, context_link
from .reader_surface import ReaderPage, render_reader_surface
from .search import SEARCH_RESOURCE, SearchViewModel, _query_from_context, render_search_view

QueryContext: TypeAlias = str | Mapping[str, object] | None

SEARCH_READER_RESOURCE = SEARCH_RESOURCE
SEARCH_READER_RULE = "manager-gui.reader.search.v1"
SEARCH_READER_VERSION = "v1"
SEARCH_READER_HOOK = "search-reader-view"
SEARCH_READER_INTEGRATION_HOOK = "search-view"


def _source_availability(model: ManagerReadModel) -> ReaderAvailability:
    selected = ReaderAvailability.from_v0(model.availability)
    if selected.status is ReaderAvailabilityStatus.KNOWN and any(
        error.code == "not_evaluated" for error in model.errors
    ):
        return ReaderAvailability(
            ReaderAvailabilityStatus.NOT_EVALUATED,
            False,
            selected.reason,
            selected.retryable,
        )
    return selected


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


def project_search_reader(
    model: ManagerReadModel,
    *,
    query: str = "",
    record_type: str | None = None,
    source: str | None = None,
    source_id: str | None = None,
    sample: bool = False,
    sample_state: str | None = None,
) -> ReaderProjection:
    """Project one Search envelope without adding owner-domain facts."""

    view = SearchViewModel.from_read_model(
        model,
        query=query,
        record_type=record_type,
        source_id=source_id if source is None else source,
    )
    source_refs = tuple(model.source_refs)
    inputs = tuple(ref.source_id for ref in source_refs)
    source_availability = _source_availability(model)
    derivation = Derivation(
        "derived",
        SEARCH_READER_RULE,
        inputs,
        SEARCH_READER_VERSION,
    )
    claims: list[ReaderClaim] = []
    for index, hit in enumerate(view.hits):
        refs = hit.source_refs or source_refs
        if not refs or source_availability.status not in {
            ReaderAvailabilityStatus.KNOWN,
            ReaderAvailabilityStatus.DERIVED,
            ReaderAvailabilityStatus.INTERPRETED,
        }:
            continue
        claim_inputs = tuple(ref.source_id for ref in refs)
        claims.append(
            _claim(
                f"search.hit.{hit.result_id}.{index}",
                kind=ClaimKind.DERIVED,
                source_refs=refs,
                availability=ReaderAvailability(
                    ReaderAvailabilityStatus.DERIVED,
                    source_availability.complete,
                    source_availability.reason,
                    source_availability.retryable,
                ),
                value=cast(FrozenJSON, hit.to_dict()),
                derivation=Derivation(
                    "derived",
                    SEARCH_READER_RULE,
                    claim_inputs,
                    SEARCH_READER_VERSION,
                ),
            )
        )

    gaps: list[ReaderClaim] = []
    if source_refs and (
        not claims
        or view.pagination.is_partial
        or source_availability.status
        not in {
            ReaderAvailabilityStatus.KNOWN,
            ReaderAvailabilityStatus.DERIVED,
            ReaderAvailabilityStatus.INTERPRETED,
        }
    ):
        gap_availability = _gap_availability(
            model,
            "Search scope is incomplete or does not contain an explicit matching owner record.",
        )
        gaps.append(
            _claim(
                "search.scope",
                kind=_gap_kind(gap_availability.status),
                source_refs=source_refs,
                availability=gap_availability,
                value=cast(
                    FrozenJSON,
                    {
                        "query": view.query,
                        "record_type": view.record_type,
                        "source": view.source,
                        "global_no_match": view.global_no_match,
                        "pagination": view.pagination.to_dict(),
                    },
                ),
                derivation=Derivation(
                    "direct",
                    None,
                    inputs,
                    SEARCH_READER_VERSION,
                ),
            )
        )

    projection = project_read_model(
        model,
        claims=tuple(claims),
        unknowns=tuple(gaps),
    )
    projection = replace(projection, derivation=derivation)
    if sample:
        projection = replace(
            projection,
            sample_data=SampleData(sample_state or "complete", SEARCH_READER_RESOURCE),
        )
    return projection


@dataclass(frozen=True, slots=True)
class SearchReaderViewModel:
    """Search projection plus its typed Reader query and filter context."""

    read_model: ManagerReadModel
    search: SearchViewModel

    @property
    def hits(self):
        return self.search.hits

    @property
    def source_refs(self):
        return self.read_model.source_refs

    @property
    def query(self) -> str:
        return self.search.query

    @property
    def state(self):
        return self.search.state

    def to_dict(self) -> dict[str, object]:
        return self.search.to_dict()


def _filter_markup(
    view: SearchViewModel,
    *,
    context: QueryContext,
    translator: Translator,
) -> str:
    record_type = view.record_type or translator.t("l5.search.none")
    source = view.source or translator.t("l5.search.none")
    snapshot = view.snapshot_token or translator.t("l5.search.unavailable")
    scope = (
        translator.t("reader.search.scope_complete")
        if view.pagination.complete
        else translator.t("reader.search.scope_partial")
    )
    return (
        f'<section class="search-reader-filters" aria-labelledby="search-reader-filters-title">'
        f'<h2 id="search-reader-filters-title">{escape(translator.t("reader.search.filter_heading"))}</h2>'
        f'<dl><div><dt>{escape(translator.t("reader.search.filter_type"))}</dt><dd translate="no">{escape(record_type)}</dd></div>'
        f'<div><dt>{escape(translator.t("reader.search.filter_source"))}</dt><dd translate="no">{escape(source)}</dd></div>'
        f'<div><dt>{escape(translator.t("reader.search.filter_snapshot"))}</dt><dd translate="no">{escape(snapshot)}</dd></div>'
        f'<div><dt>{escape(translator.t("reader.search.filter_scope"))}</dt><dd>{escape(scope)}</dd></div></dl>'
        f'<p class="search-reader-context-link"><a href="{escape(context_link(context, view=ViewId.SEARCH), quote=True)}">'
        f'{escape(translator.t("reader.search.title"))}</a></p></section>'
    )


def _raw_markup(projection: ReaderProjection, translator: Translator) -> str:
    raw = projection.raw_source.raw_bytes.decode("utf-8")
    return (
        f'<section class="search-reader-raw" data-reader-hook="{SEARCH_READER_HOOK}" '
        f'data-integration-hook="{SEARCH_READER_INTEGRATION_HOOK}" data-reader-mode="raw">'
        f'<h1>{escape(translator.t("reader.search.raw_heading"))}</h1>'
        f'<pre data-v0-schema="manager-gui.manager-read-model.v0" translate="no">{escape(raw)}</pre>'
        f'<p translate="no" data-raw-sha256="{escape(projection.raw_source.sha256, quote=True)}">{projection.raw_source.sha256}</p></section>'
    )


def _without_page_heading(markup: str) -> str:
    """Keep the shell/Reader wrapper as the only document-level h1."""

    return re.sub(r'<h1\b[^>]*>.*?</h1>', "", markup, count=1, flags=re.DOTALL)


def _reader_markup(
    view: SearchViewModel,
    projection: ReaderProjection,
    *,
    context: QueryContext,
    translator: Translator,
) -> str:
    surface = render_reader_surface(
        projection,
        page=ReaderPage.SEARCH,
        query_context=context,
        translator=translator,
    )
    search_markup = _without_page_heading(view.render(query_context=context, translator=translator))
    return (
        f'<section class="search-reader-page" data-reader-hook="{SEARCH_READER_HOOK}" '
        f'data-integration-hook="{SEARCH_READER_INTEGRATION_HOOK}" data-reader-contract="v1" '
        f'data-reader-mode="reader" data-search-reader-state="{escape(view.state.value, quote=True)}" '
        f'data-status="{escape(view.status.value, quote=True)}" aria-labelledby="search-reader-title">'
        f'<p class="eyebrow">{escape(translator.t("reader.search.eyebrow"))}</p>'
        f'<h1 id="search-reader-title" data-page-title tabindex="-1">{escape(translator.t("reader.search.title"))}</h1>'
        f'<p class="reader-intro">{escape(translator.t("reader.search.confirmed_intro"))}</p>'
        f'{surface}{_filter_markup(view, context=context, translator=translator)}'
        f'<p class="search-reader-boundary" data-boundary="search-match">{escape(translator.t("reader.search.not_evidence"))}</p>'
        f'{search_markup}'
        f'<p class="search-reader-read-only">{escape(translator.t("reader.search.read_only"))}</p></section>'
    )


def _expert_markup(
    view: SearchViewModel,
    *,
    context: QueryContext,
    translator: Translator,
) -> str:
    return (
        f'<section class="search-reader-page" data-reader-hook="{SEARCH_READER_HOOK}" '
        f'data-integration-hook="{SEARCH_READER_INTEGRATION_HOOK}" data-reader-contract="v1" '
        f'data-reader-mode="expert" data-status="{escape(view.status.value, quote=True)}">'
        f'<h1>{escape(translator.t("reader.search.expert_heading"))}</h1>'
        f'{_without_page_heading(render_search_view(view.read_model, query=view.query, record_type=view.record_type, source_filter=view.source, query_context=context, translator=translator))}</section>'
    )


def render_search_reader(
    source: ManagerReadModel | SearchReaderViewModel | ReaderProjection,
    *,
    query: str | None = None,
    record_type: str | None = None,
    source_filter: str | None = None,
    source_id: str | None = None,
    query_context: QueryContext = None,
    projection: ReaderProjection | None = None,
    mode: ProjectionMode | str | None = None,
    sample: bool = False,
    sample_state: str | None = None,
    translator: Translator | None = None,
) -> str:
    """Render Search Reader, Expert, or Raw mode from one v0 envelope."""

    if isinstance(source, SearchReaderViewModel):
        model = source.read_model
        view = source.search
    elif isinstance(source, ReaderProjection):
        model = ManagerReadModel.from_json(source.raw_source.raw_bytes.decode("utf-8"))
        selected_query = _query_from_context(query_context) if query is None else query
        view = SearchViewModel.from_read_model(
            model,
            query=selected_query,
            record_type=record_type,
            source=source_filter if source_filter is not None else source_id,
            query_context=query_context,
        )
        projection = source
    else:
        model = source
        selected_query = _query_from_context(query_context) if query is None else query
        view = SearchViewModel.from_read_model(
            model,
            query=selected_query,
            record_type=record_type,
            source=source_filter if source_filter is not None else source_id,
            query_context=query_context,
        )
    selected_translator = translator or Translator()
    selected_projection = projection or project_search_reader(
        model,
        query=view.query,
        record_type=view.record_type,
        source=view.source,
        sample=sample,
        sample_state=sample_state,
    )
    context_pairs = tuple(
        (str(key), str(value))
        for key, value in (query_context or {}).items()
        if value is not None
    ) if isinstance(query_context, Mapping) else ()
    context_mode = next((value for key, value in context_pairs if key == "mode"), None)
    url_state = (
        ReaderURLState.from_url(query_context)
        if isinstance(query_context, str)
        else ReaderURLState(pairs=context_pairs, mode=context_mode or ProjectionMode.READER)
    )
    selected_mode = ProjectionMode(mode) if mode is not None else url_state.mode
    if selected_mode is ProjectionMode.RAW:
        return _raw_markup(selected_projection, selected_translator)
    if selected_mode is ProjectionMode.EXPERT:
        return _expert_markup(view, context=query_context, translator=selected_translator)
    return _reader_markup(
        view,
        selected_projection,
        context=query_context,
        translator=selected_translator,
    )


def search_reader_view(
    provider: ManagerDataProvider,
    *,
    query: str = "",
    record_type: str | None = None,
    source: str | None = None,
    snapshot_token: str | None = None,
) -> SearchReaderViewModel:
    model = provider.read(SEARCH_READER_RESOURCE, snapshot_token=snapshot_token)
    return SearchReaderViewModel(
        model,
        SearchViewModel.from_read_model(
            model,
            query=query,
            record_type=record_type,
            source=source,
        ),
    )


def render_search_reader_view(source, **kwargs: object) -> str:
    return render_search_reader(source, **kwargs)


# Compatibility aliases parallel the existing Search integration names.
project_reader_search = project_search_reader
project_search = project_search_reader
render_reader_search = render_search_reader
SearchReaderView = SearchReaderViewModel


__all__ = [
    "SEARCH_READER_HOOK",
    "SEARCH_READER_INTEGRATION_HOOK",
    "SEARCH_READER_RESOURCE",
    "SEARCH_READER_RULE",
    "SEARCH_READER_VERSION",
    "SearchReaderView",
    "SearchReaderViewModel",
    "project_reader_search",
    "project_search",
    "project_search_reader",
    "render_reader_search",
    "render_search_reader",
    "render_search_reader_view",
    "search_reader_view",
]
