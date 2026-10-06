"""Global Reader route registry and the unavailable-projection boundary.

The shell owns route discovery and URL context, while each page module remains
responsible for its typed projection, catalogue copy, and mode-specific view.
This module deliberately has no provider access: a missing page projection is a
visible limitation, never an inferred conclusion.
"""

from __future__ import annotations

import re

# HTML attributes stay readable at the call site.
# ruff: noqa: E501
from dataclasses import dataclass
from html import escape
from typing import Final

from ..reader import ProjectionMode, ReaderAvailabilityStatus, ReaderProjection
from .i18n import Translator
from .navigation import NAVIGATION, ViewId, context_link, navigation_item, navigation_label
from .reader_surface import ReaderPage, render_reader_surface


@dataclass(frozen=True, slots=True)
class ReaderRoute:
    """The stable Reader contract for one mounted Manager GUI route."""

    view: ViewId
    page: ReaderPage
    integration_hook: str
    projection_published: bool = True


# Keep this list explicit.  It is the global completeness boundary for Reader
# v1, and the import-time check below prevents a new shell route from silently
# disappearing from the Reader matrix.
READER_ROUTES: Final[tuple[ReaderRoute, ...]] = (
    ReaderRoute(ViewId.ATLAS, ReaderPage.ATLAS, "atlas-view"),
    ReaderRoute(ViewId.STORIES, ReaderPage.STORY, "research-story-view"),
    ReaderRoute(ViewId.STRATEGIES, ReaderPage.GENOME, "strategy-genome-view"),
    ReaderRoute(ViewId.CONDITIONS, ReaderPage.CONDITIONS, "strategy-genome-conditions-view"),
    ReaderRoute(ViewId.COMPARISON, ReaderPage.COMPARISON, "strategy-genome-comparison-view"),
    ReaderRoute(ViewId.MEMORY, ReaderPage.MEMORY, "memory-view"),
    ReaderRoute(ViewId.MEMORY_FAILURES, ReaderPage.FAILURE, "failure-patterns-view"),
    ReaderRoute(ViewId.FAILURE_PATTERNS, ReaderPage.FAILURE_PATTERNS, "failure-patterns-view"),
    ReaderRoute(ViewId.EVIDENCE, ReaderPage.EVIDENCE, "evidence-view"),
    ReaderRoute(ViewId.LINEAGE, ReaderPage.LINEAGE, "lineage-view"),
    ReaderRoute(ViewId.EVIDENCE_COMPARISON, ReaderPage.EVIDENCE_COMPARISON, "evidence-comparison-view"),
    ReaderRoute(ViewId.FAILURE_GROUPING, ReaderPage.FAILURE_GROUPING, "failure-grouping-view"),
    ReaderRoute(ViewId.METHODOLOGY, ReaderPage.METHODOLOGY, "methodology-view"),
    ReaderRoute(ViewId.HISTORY, ReaderPage.HISTORY, "history-view"),
    ReaderRoute(ViewId.SOURCE_DOCUMENTS, ReaderPage.DOCUMENTS, "source-documents-view"),
    ReaderRoute(ViewId.SEARCH, ReaderPage.SEARCH, "search-view"),
    ReaderRoute(ViewId.PORTAL, ReaderPage.PORTAL, "portal-view"),
)

READER_ROUTE_BY_VIEW: Final[dict[ViewId, ReaderRoute]] = {
    route.view: route for route in READER_ROUTES
}
if tuple(item.view_id for item in NAVIGATION) != tuple(route.view for route in READER_ROUTES):
    raise RuntimeError("Reader route registry must cover NAVIGATION in order")
if len(READER_ROUTE_BY_VIEW) != len(READER_ROUTES):
    raise RuntimeError("Reader route registry contains duplicate views")


_ROUTE_OPEN_TAG = re.compile(r"^(?P<prefix>\s*<(?P<tag>[A-Za-z][A-Za-z0-9:_-]*))(?P<attrs>[^>]*)(?P<close>>)", re.DOTALL)


def reader_route(view: ViewId | str) -> ReaderRoute:
    """Return the registered Reader route, failing closed for unknown views."""

    try:
        return READER_ROUTE_BY_VIEW[ViewId(view)]
    except (KeyError, ValueError) as exc:
        raise ValueError(f"unknown Reader route: {view!r}") from exc


def reader_route_context(
    context: str | dict[str, object] | None,
    *,
    view: ViewId | str,
    **updates: object,
) -> str:
    """Build a cross-route link while retaining opaque URL context."""

    reader_route(view)
    return context_link(context, view=view, **updates)


def annotate_reader_mount(
    markup: str,
    *,
    route: ReaderRoute,
    mode: ProjectionMode,
    availability: str,
) -> str:
    """Add the shell-level route contract to a page's existing root element.

    Page modules keep their own root and integration hook.  The additional
    attributes make the global route/mode matrix machine-auditable without
    wrapping or rewriting owner markup.
    """

    match = _ROUTE_OPEN_TAG.match(markup)
    if match is None:
        return markup
    attrs = (
        f' data-reader-route="{escape(route.view.value, quote=True)}"'
        f' data-reader-route-page="{escape(route.page.value, quote=True)}"'
        f' data-reader-route-mode="{escape(mode.value, quote=True)}"'
        f' data-reader-route-contract="v1"'
        f' data-reader-route-availability="{escape(availability, quote=True)}"'
    )
    return f"{match.group('prefix')}{match.group('attrs')}{attrs}{match.group('close')}{markup[match.end():]}"


def _reader_display_state(projection: ReaderProjection) -> str:
    """Keep the unavailable route aligned with the v0 display-state contract."""

    availability = projection.availability
    if availability.status is ReaderAvailabilityStatus.MISSING:
        return "empty"
    if availability.status is ReaderAvailabilityStatus.KNOWN and not availability.complete:
        return "partial"
    if availability.status in {
        ReaderAvailabilityStatus.BLOCKED,
        ReaderAvailabilityStatus.STALE,
        ReaderAvailabilityStatus.INCOMPARABLE,
        ReaderAvailabilityStatus.INTEGRITY_FAILURE,
        ReaderAvailabilityStatus.API_UNAVAILABLE,
    }:
        return "error"
    return "ready"


def render_unavailable_reader(
    projection: ReaderProjection,
    *,
    route: ReaderRoute,
    query_context: str | dict[str, object] | None,
    translator: Translator,
) -> str:
    """Render a route whose dedicated Reader projection is not published."""

    item = navigation_item(route.view)
    label = navigation_label(route.view, translator)
    surface = render_reader_surface(
        projection,
        page=route.page,
        query_context=query_context,
        translator=translator,
    )
    return (
        f'<section class="reader-route-unavailable" data-reader-hook="{escape(item.integration_hook, quote=True)}" '
        f'data-integration-hook="{escape(item.integration_hook, quote=True)}" '
        f'data-status="{escape(projection.availability.status.value, quote=True)}" '
        f'data-display-state="{_reader_display_state(projection)}" data-reader-contract="v1" '
        f'data-reader-mode="{ProjectionMode.READER.value}" data-reader-route="{escape(route.view.value, quote=True)}" '
        f'data-reader-route-page="{escape(route.page.value, quote=True)}" '
        f'data-reader-route-availability="unavailable" aria-labelledby="reader-route-title-{escape(route.view.value, quote=True)}">'
        f'<p class="eyebrow">{escape(translator.t("reader.global.route_context"))}</p>'
        f'<h1 id="reader-route-title-{escape(route.view.value, quote=True)}" data-page-title tabindex="-1">{escape(label)}</h1>'
        f'<p class="reader-route-unavailable-title">{escape(translator.t("reader.global.unavailable"))}</p>'
        f'<p class="reader-route-unavailable-detail">{escape(translator.t("reader.global.unavailable_detail"))}</p>'
        f"{surface}</section>"
    )


__all__ = [
    "READER_ROUTES",
    "READER_ROUTE_BY_VIEW",
    "ReaderRoute",
    "annotate_reader_mount",
    "reader_route",
    "reader_route_context",
    "render_unavailable_reader",
]
