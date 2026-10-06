"""Shared Reader-mode page framing for the R2 Atlas and Story surfaces.

The surface is a presentation-only consumer of ``ReaderProjection``.  It does
not inspect private storage or manufacture a conclusion from the v0 payload.
Every sentence comes from the Reader catalogue; source identifiers and owner
availability notes remain escaped source values.
"""

# The HTML fragments intentionally remain readable at the call site.
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum
from html import escape
from typing import Final

from ..reader import ReaderClaim, ReaderProjection
from .i18n import Translator
from .i18n.catalog.reader import (
    ReaderTemplateParams,
    render_availability_explanation,
    render_claim_explanation,
    render_reader_template,
)
from .locators import public_locator
from .navigation import context_link


class ReaderPage(StrEnum):
    """Reader page identities with fixed catalogue copy."""

    ATLAS = "atlas"
    STORY = "story"
    GENOME = "genome"
    CONDITIONS = "conditions"
    REVISIONS = "revisions"
    COMPARISON = "comparison"
    MEMORY = "memory"
    FAILURE = "failure"
    FAILURE_PATTERNS = "failure-patterns"


ReaderQueryContext = str | Mapping[str, object] | None


def _mark_source_values(markup: str, values: Sequence[str | None]) -> str:
    """Keep source/derivation values out of locale translation checks."""

    marked = markup
    unique = sorted(
        {escape(value, quote=True) for value in values if value},
        key=len,
        reverse=True,
    )
    for value in unique:
        marked = marked.replace(
            value,
            f'<span translate="no" data-owner-text="true">{value}</span>',
        )
    return marked


_PAGE_COPY: Final[dict[ReaderPage, dict[str, str]]] = {
    ReaderPage.ATLAS: {
        "question": "reader.atlas.question",
        "confirmed": "reader.atlas.confirmed",
        "unknown": "reader.atlas.unknown",
        "why": "reader.atlas.why",
    },
    ReaderPage.STORY: {
        "question": "reader.story.question",
        "confirmed": "reader.story.confirmed",
        "unknown": "reader.story.unknown",
        "why": "reader.story.why",
    },
    ReaderPage.GENOME: {
        "question": "reader.genome.question",
        "confirmed": "reader.genome.confirmed",
        "unknown": "reader.genome.unknown",
        "why": "reader.genome.why",
    },
    ReaderPage.CONDITIONS: {
        "question": "reader.conditions.question",
        "confirmed": "reader.conditions.confirmed",
        "unknown": "reader.conditions.unknown",
        "why": "reader.conditions.why",
    },
    ReaderPage.REVISIONS: {
        "question": "reader.revisions.question",
        "confirmed": "reader.revisions.confirmed",
        "unknown": "reader.revisions.unknown",
        "why": "reader.revisions.why",
    },
    ReaderPage.COMPARISON: {
        "question": "reader.comparison.question",
        "confirmed": "reader.comparison.confirmed",
        "unknown": "reader.comparison.unknown",
        "why": "reader.comparison.why",
    },
    ReaderPage.MEMORY: {
        "question": "reader.memory.question",
        "confirmed": "reader.memory.confirmed",
        "unknown": "reader.memory.unknown",
        "why": "reader.memory.why",
    },
    ReaderPage.FAILURE: {
        "question": "reader.failure.question",
        "confirmed": "reader.failure.confirmed",
        "unknown": "reader.failure.unknown",
        "why": "reader.failure.why",
    },
    ReaderPage.FAILURE_PATTERNS: {
        "question": "reader.failure.question",
        "confirmed": "reader.failure.confirmed",
        "unknown": "reader.failure.unknown",
        "why": "reader.failure.why",
    },
}


def _source_context_link(
    query_context: ReaderQueryContext,
    *,
    source_id: str,
    translator: Translator,
) -> str:
    target = context_link(query_context, view="evidence", source_id=source_id)
    return (
        f'<a class="reader-evidence-link" data-reader-source-id="{escape(source_id, quote=True)}" '
        f'href="{escape(target, quote=True)}">{escape(translator.t("reader.evidence_entry"))}</a>'
    )


def _source_links(
    projection: ReaderProjection,
    *,
    query_context: ReaderQueryContext,
    translator: Translator,
) -> str:
    if not projection.source_refs:
        return f'<p class="reader-no-sources">{escape(translator.t("reader.no_sources"))}</p>'
    items = []
    for reference in projection.source_refs:
        evidence = _source_context_link(
            query_context, source_id=reference.source_id, translator=translator
        )
        target = public_locator(reference.locator)
        source_value = escape(reference.source_id)
        source = (
            f'<a class="reader-source-link" data-reader-source-id="{escape(reference.source_id, quote=True)}" '
            f'href="{escape(target, quote=True)}" translate="no">{source_value}</a>'
            if target
            else f'<span class="reader-source-unconfirmed" data-reader-source-id="{escape(reference.source_id, quote=True)}" '
            f'translate="no">{source_value}</span>'
        )
        items.append(f"<li>{source} · {evidence}</li>")
    return f'<ul class="reader-source-list">{"".join(items)}</ul>'


def _claim_links(
    claim: ReaderClaim,
    *,
    query_context: ReaderQueryContext,
    translator: Translator,
) -> str:
    links = [
        _source_context_link(query_context, source_id=ref.source_id, translator=translator)
        for ref in claim.source_refs
    ]
    return " · ".join(links)


def _render_claims(
    claims: Sequence[ReaderClaim],
    *,
    query_context: ReaderQueryContext,
    translator: Translator,
    empty_key: str,
) -> str:
    if not claims:
        return f'<p class="reader-no-claims">{escape(translator.t(empty_key))}</p>'
    items = []
    for claim in claims:
        explanation = _mark_source_values(
            render_claim_explanation(translator, claim, as_html=True),
            (*[ref.source_id for ref in claim.source_refs], claim.derivation.rule, claim.availability.reason),
        )
        links = _claim_links(claim, query_context=query_context, translator=translator)
        items.append(
            f'<li class="reader-claim reader-claim-{claim.kind.value.lower()}" '
            f'data-reader-claim-id="{escape(claim.claim_id, quote=True)}" '
            f'data-reader-claim-kind="{escape(claim.kind.value, quote=True)}" '
            f'data-reader-availability="{escape(claim.availability.status.value, quote=True)}">'
            f'<p>{explanation}</p><p class="reader-claim-links">{links}</p></li>'
        )
    return f'<ul class="reader-claim-list">{"".join(items)}</ul>'


def _render_unknowns(
    projection: ReaderProjection,
    *,
    query_context: ReaderQueryContext,
    translator: Translator,
) -> str:
    gaps = projection.limitations + projection.unknowns
    if not gaps:
        # An owner projection has no UI-authored claim set.  It is not safe to
        # turn an absent projection claim into a positive conclusion.
        if not projection.claims:
            return f'<p class="reader-no-conclusion">{escape(translator.t("reader.no_conclusion"))}</p>'
        return f'<p class="reader-no-gaps">{escape(translator.t("reader.no_gaps"))}</p>'
    return _render_claims(
        gaps,
        query_context=query_context,
        translator=translator,
        empty_key="reader.no_conclusion",
    )


def _render_why(
    projection: ReaderProjection,
    *,
    query_context: ReaderQueryContext,
    translator: Translator,
) -> str:
    availability = _mark_source_values(
        render_availability_explanation(
            translator, projection.availability, as_html=True
        ),
        (projection.availability.reason,),
    )
    if projection.source_refs:
        source_count = render_reader_template(
            translator,
            "reader.source.count",
            params=ReaderTemplateParams(n=len(projection.source_refs)),
            source_refs=projection.source_refs,
            as_html=True,
        )
        sources = _source_links(
            projection, query_context=query_context, translator=translator
        )
    else:
        source_count = translator.t("reader.no_sources")
        sources = _source_links(projection, query_context=query_context, translator=translator)
    rule = projection.derivation.rule or translator.t("reader.derivation.unrecorded")
    return (
        f'<p class="reader-availability-explanation">{availability}</p>'
        f'<p class="reader-source-count">{source_count}</p>'
        f'<p class="reader-derivation"><strong>{escape(translator.t("reader.derivation"))}:</strong> '
        f'<code translate="no">{escape(rule)}</code></p>'
        f'<div class="reader-sources"><h3>{escape(translator.t("reader.source"))}</h3>{sources}</div>'
    )


def render_reader_surface(
    projection: ReaderProjection,
    *,
    page: ReaderPage | str,
    query_context: ReaderQueryContext = None,
    translator: Translator | None = None,
    next_link: str | None = None,
) -> str:
    """Render the four-question Reader frame for one R2 page."""

    selected_page = ReaderPage(page)
    selected_translator = translator or Translator()
    copy = _PAGE_COPY[selected_page]
    next_markup = (
        f'<p class="reader-next-step"><a class="reader-next-link" href="{escape(next_link, quote=True)}">'
        f'{escape(selected_translator.t("reader.next_step"))}</a></p>'
        if next_link
        else ""
    )
    return (
        f'<section class="reader-page-surface" data-reader-page="{selected_page.value}" '
        f'aria-labelledby="reader-page-title-{selected_page.value}">'
        f'<h2 id="reader-page-title-{selected_page.value}" class="sr-only">'
        f'{escape(selected_translator.t("reader.mode.reader"))}</h2>'
        f'<section class="reader-question" aria-labelledby="reader-question-{selected_page.value}">'
        f'<h3 id="reader-question-{selected_page.value}">{escape(selected_translator.t("reader.page_question"))}</h3>'
        f'<p>{escape(selected_translator.t(copy["question"]))}</p></section>'
        f'<section class="reader-confirmed" aria-labelledby="reader-confirmed-{selected_page.value}">'
        f'<h3 id="reader-confirmed-{selected_page.value}">{escape(selected_translator.t("reader.currently_confirmed"))}</h3>'
        f'{_render_claims(projection.claims, query_context=query_context, translator=selected_translator, empty_key="reader.no_conclusion")}</section>'
        f'<section class="reader-unknowns" aria-labelledby="reader-unknowns-{selected_page.value}">'
        f'<h3 id="reader-unknowns-{selected_page.value}">{escape(selected_translator.t("reader.not_yet_known"))}</h3>'
        f'{_render_unknowns(projection, query_context=query_context, translator=selected_translator)}</section>'
        f'<section class="reader-why" aria-labelledby="reader-why-{selected_page.value}">'
        f'<h3 id="reader-why-{selected_page.value}">{escape(selected_translator.t("reader.why_this_is_said"))}</h3>'
        f'{_render_why(projection, query_context=query_context, translator=selected_translator)}'
        f'{next_markup}</section></section>'
    )


__all__ = ["ReaderPage", "render_reader_surface"]
