"""Stable shared navigation for every Manager GUI surface."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from html import escape
from urllib.parse import parse_qsl, urlencode, urlsplit

from .i18n import DEFAULT_LOCALE, Locale, Translator, resolve_locale


class ViewId(StrEnum):
    """URL-stable identifiers for the shell's top-level views."""

    ATLAS = "atlas"
    STORIES = "stories"
    STRATEGIES = "strategies"
    CONDITIONS = "strategy-conditions"
    COMPARISON = "strategy-genome-comparison"
    MEMORY = "memory"
    MEMORY_FAILURES = "memory-failures"
    FAILURE_PATTERNS = "failure-patterns"
    EVIDENCE = "evidence"
    LINEAGE = "lineage"
    EVIDENCE_COMPARISON = "evidence-object-comparison"
    FAILURE_GROUPING = "derived-failure-grouping"
    METHODOLOGY = "methodology"
    HISTORY = "history"
    SOURCE_DOCUMENTS = "source-documents"
    SEARCH = "search"
    PORTAL = "portal"


@dataclass(frozen=True, slots=True)
class NavigationItem:
    """One URL-stable navigation item and its integration hook.

    User-facing labels and descriptions live in the shared i18n catalog.  Keeping
    only identifiers here prevents a renderer from accidentally mixing languages.
    """

    view_id: ViewId
    short_label: str
    integration_hook: str


NAVIGATION: tuple[NavigationItem, ...] = (
    NavigationItem(ViewId.ATLAS, "AT", "atlas-view"),
    NavigationItem(ViewId.STORIES, "ST", "research-story-view"),
    NavigationItem(ViewId.STRATEGIES, "SG", "strategy-genome-view"),
    NavigationItem(ViewId.CONDITIONS, "GC", "strategy-genome-conditions-view"),
    NavigationItem(ViewId.COMPARISON, "CP", "strategy-genome-comparison-view"),
    NavigationItem(ViewId.MEMORY, "ME", "memory-view"),
    NavigationItem(ViewId.MEMORY_FAILURES, "MF", "failure-patterns-view"),
    NavigationItem(ViewId.FAILURE_PATTERNS, "FP", "failure-patterns-view"),
    NavigationItem(ViewId.EVIDENCE, "EV", "evidence-view"),
    NavigationItem(ViewId.LINEAGE, "LI", "lineage-view"),
    NavigationItem(ViewId.EVIDENCE_COMPARISON, "EC", "evidence-comparison-view"),
    NavigationItem(ViewId.FAILURE_GROUPING, "DG", "failure-grouping-view"),
    NavigationItem(ViewId.METHODOLOGY, "MO", "methodology-view"),
    NavigationItem(ViewId.HISTORY, "HI", "history-view"),
    NavigationItem(ViewId.SOURCE_DOCUMENTS, "DO", "source-documents-view"),
    NavigationItem(ViewId.SEARCH, "SE", "search-view"),
    NavigationItem(ViewId.PORTAL, "PO", "portal-view"),
)

NAVIGATION_BY_ID = {item.view_id: item for item in NAVIGATION}


def _resolved_translator(translator: Translator | None) -> Translator:
    return translator or Translator(DEFAULT_LOCALE)


def navigation_label(
    value: ViewId | str, translator: Translator | None = None
) -> str:
    """Return the catalog label for a view in ``translator``'s locale."""

    view = ViewId(value)
    return _resolved_translator(translator).t(f"nav.{view.value}.label")


def navigation_description(
    value: ViewId | str, translator: Translator | None = None
) -> str:
    """Return the catalog description for a view in ``translator``'s locale."""

    view = ViewId(value)
    return _resolved_translator(translator).t(f"nav.{view.value}.description")


def navigation_label_zh(value: ViewId | str) -> str:
    """Compatibility helper returning the catalog's Chinese navigation label."""

    return navigation_label(value, Translator(Locale.ZH_CN))


def navigation_item(value: ViewId | str) -> NavigationItem:
    """Return a navigation item, raising a useful error for unknown URLs."""

    try:
        return NAVIGATION_BY_ID[ViewId(value)]
    except (KeyError, ValueError) as exc:
        raise ValueError(f"unknown Manager GUI view: {value!r}") from exc


def _query_pairs(context: str | Mapping[str, object] | None) -> list[tuple[str, str]]:
    """Read query pairs without collapsing repeated opaque state."""

    if isinstance(context, str):
        parsed = urlsplit(context)
        query = parsed.query if parsed.query or parsed.path.startswith("/") else context.lstrip("?")
        return parse_qsl(query, keep_blank_values=True)
    if context is not None:
        return [
            (str(key), str(value))
            for key, value in context.items()
            if value is not None
        ]
    return []


def query_values(context: str | Mapping[str, object] | None) -> dict[str, str]:
    """Read the first value for each key while retaining the opaque-query contract."""

    values: dict[str, str] = {}
    for key, value in _query_pairs(context):
        values.setdefault(key, value)
    return values


def context_link(
    context: str | Mapping[str, object] | None,
    *,
    view: ViewId | str,
    **updates: object,
) -> str:
    """Stable local links preserve context, including repeated query parameters."""

    values = query_values(context)
    pairs = _query_pairs(context)
    if values.get("view") != str(view) or any(
        values.get(key) != str(value)
        for key, value in updates.items()
        if key not in {"page", "lang"}
    ):
        pairs = [(key, value) for key, value in pairs if key != "page"]
    pairs = [(key, value) for key, value in pairs if key != "view"]
    pairs.append(("view", str(view)))
    for key, value in updates.items():
        pairs = [(pair_key, pair_value) for pair_key, pair_value in pairs if pair_key != key]
        if value is not None:
            pairs.append((key, str(value)))
    return "/?" + urlencode(sorted(pairs))


def clear_filters_link(
    context: str | Mapping[str, object] | None,
    *,
    view: ViewId | str,
    filter_keys: Sequence[str],
    selection_keys: Sequence[str] = (),
) -> str:
    """Reset a page's filters/selection while keeping shell context.

    Fixture, snapshot token, panel, query, presentation, and unrelated opaque
    context are retained so "Clear" never silently changes the read being viewed.
    """

    return context_link(
        context,
        view=view,
        **{key: None for key in (*filter_keys, *selection_keys)},
    )


@dataclass(frozen=True, slots=True)
class PageWindow:
    """Bounded local presentation of an already-read envelope, not an owner cursor."""

    page: int
    page_size: int
    total: int

    @classmethod
    def from_query(
        cls, context: str | Mapping[str, object] | None, *, total: int
    ) -> PageWindow:
        values = query_values(context)
        try:
            size = max(1, min(100, int(values.get("page_size", "20"))))
        except ValueError:
            size = 20
        pages = max(1, (total + size - 1) // size)
        try:
            page = max(1, min(pages, int(values.get("page", "1"))))
        except ValueError:
            page = 1
        return cls(page, size, total)

    @property
    def start(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def stop(self) -> int:
        return self.start + self.page_size

    def render(
        self,
        context: str | Mapping[str, object] | None,
        *,
        view: ViewId | str,
        translator: Translator | None = None,
    ) -> str:
        """Render localized pagination while retaining all opaque link state."""

        values = query_values(context)
        selected = resolve_locale(values.get("lang")) or DEFAULT_LOCALE
        translator = translator or Translator(selected)
        pages = max(1, (self.total + self.page_size - 1) // self.page_size)
        links = []
        for key, rel, target in (
            ("pagination.previous", "prev", self.page - 1),
            ("pagination.next", "next", self.page + 1),
        ):
            if 1 <= target <= pages:
                url = context_link(context, view=view, page=target, page_size=self.page_size)
                label = translator.t(key)
                links.append(
                    f'<a class="pagination-link" rel="{rel}" '
                    f'href="{escape(url, quote=True)}" aria-label="{escape(label, quote=True)}">'
                    f'{escape(label)}</a>'
                )
        summary = translator.t(
            "pagination.summary", page=self.page, pages=pages, n=self.total
        )
        aria_label = translator.t("pagination.aria")
        return (
            f'<nav class="page-pagination" aria-label="{escape(aria_label, quote=True)}">'
            f'<span>{escape(summary)}</span>'
            + "".join(links)
            + "</nav>"
        )


__all__ = [
    "NAVIGATION",
    "NAVIGATION_BY_ID",
    "NavigationItem",
    "PageWindow",
    "ViewId",
    "clear_filters_link",
    "context_link",
    "navigation_description",
    "navigation_item",
    "navigation_label",
    "navigation_label_zh",
    "query_values",
]
