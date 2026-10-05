"""Stable shared navigation for every Manager GUI surface."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from html import escape
from urllib.parse import parse_qsl, urlencode, urlsplit


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
    """One navigation item and its future integration hook."""

    view_id: ViewId
    label: str
    short_label: str
    description: str
    integration_hook: str


NAVIGATION: tuple[NavigationItem, ...] = (
    NavigationItem(
        ViewId.ATLAS,
        "Atlas",
        "AT",
        "Workspace map and current read-model scope.",
        "atlas-view",
    ),
    NavigationItem(
        ViewId.STORIES,
        "Stories",
        "ST",
        "Research story index and provenance trail.",
        "research-story-view",
    ),
    NavigationItem(
        ViewId.STRATEGIES,
        "Strategies / Genomes",
        "SG",
        "Strategy and genome read surfaces.",
        "strategy-genome-view",
    ),
    NavigationItem(
        ViewId.CONDITIONS,
        "Genome Conditions",
        "GC",
        "Genome applicability, invalidation, and descriptor evidence.",
        "strategy-genome-conditions-view",
    ),
    NavigationItem(
        ViewId.COMPARISON,
        "Genome Comparison",
        "CP",
        "Explicit Genome comparison axes and provenance.",
        "strategy-genome-comparison-view",
    ),
    NavigationItem(
        ViewId.MEMORY,
        "Memory",
        "ME",
        "Failure knowledge and retained research memory.",
        "memory-view",
    ),
    NavigationItem(
        ViewId.MEMORY_FAILURES,
        "Memory Failures",
        "MF",
        "Formal Memory failure entries and explicit lineage.",
        "failure-patterns-view",
    ),
    NavigationItem(
        ViewId.FAILURE_PATTERNS,
        "Failure Patterns",
        "FP",
        "Ordinary failures and explicitly derived patterns.",
        "failure-patterns-view",
    ),
    NavigationItem(
        ViewId.EVIDENCE,
        "Evidence",
        "EV",
        "Evidence lineage, source references, and comparisons.",
        "evidence-view",
    ),
    NavigationItem(
        ViewId.LINEAGE,
        "Lineage",
        "LI",
        "Bounded evidence lineage graph, table, and source path.",
        "lineage-view",
    ),
    NavigationItem(
        ViewId.EVIDENCE_COMPARISON,
        "Evidence Comparison",
        "EC",
        "General object and evidence comparison by declared axes.",
        "evidence-comparison-view",
    ),
    NavigationItem(
        ViewId.FAILURE_GROUPING,
        "Derived Failure Grouping",
        "DG",
        "Explicit Derived success and failure groupings.",
        "failure-grouping-view",
    ),
    NavigationItem(
        ViewId.METHODOLOGY,
        "Methodology",
        "MO",
        "Methods, contracts, and interpretation notes.",
        "methodology-view",
    ),
    NavigationItem(
        ViewId.HISTORY,
        "History",
        "HI",
        "Historical snapshots and source revisions.",
        "history-view",
    ),
    NavigationItem(
        ViewId.SOURCE_DOCUMENTS,
        "Source Documents",
        "DO",
        "Approved document index and record citations.",
        "source-documents-view",
    ),
    NavigationItem(
        ViewId.SEARCH,
        "Search",
        "SE",
        "Search across approved read-model records.",
        "search-view",
    ),
    NavigationItem(
        ViewId.PORTAL,
        "Portal",
        "PO",
        "Published Strategy Reporting source and artifact metadata.",
        "portal-view",
    ),
)

NAVIGATION_BY_ID = {item.view_id: item for item in NAVIGATION}

NAVIGATION_LABELS_ZH: Mapping[ViewId, str] = {
    ViewId.ATLAS: "总览",
    ViewId.STORIES: "研究故事",
    ViewId.STRATEGIES: "策略 / 基因组",
    ViewId.CONDITIONS: "基因组条件",
    ViewId.COMPARISON: "基因组比较",
    ViewId.MEMORY: "记忆",
    ViewId.MEMORY_FAILURES: "记忆失败",
    ViewId.FAILURE_PATTERNS: "失败模式",
    ViewId.EVIDENCE: "证据",
    ViewId.LINEAGE: "谱系",
    ViewId.EVIDENCE_COMPARISON: "证据比较",
    ViewId.FAILURE_GROUPING: "派生失败分组",
    ViewId.METHODOLOGY: "方法论",
    ViewId.HISTORY: "历史",
    ViewId.SOURCE_DOCUMENTS: "来源文档",
    ViewId.SEARCH: "搜索",
    ViewId.PORTAL: "报告门户",
}


def navigation_label_zh(value: ViewId | str) -> str:
    """Return the stable Chinese navigation label for an accessibility name."""

    return NAVIGATION_LABELS_ZH[ViewId(value)]


def navigation_item(value: ViewId | str) -> NavigationItem:
    """Return a navigation item, raising a useful error for unknown URLs."""

    try:
        return NAVIGATION_BY_ID[ViewId(value)]
    except (KeyError, ValueError) as exc:
        raise ValueError(f"unknown Manager GUI view: {value!r}") from exc


def query_values(context: str | Mapping[str, object] | None) -> dict[str, str]:
    """Read opaque query context, never a filesystem path or domain request."""

    if isinstance(context, str):
        parsed = urlsplit(context)
        query = parsed.query if parsed.query or parsed.path.startswith("/") else context.lstrip("?")
        values: dict[str, str] = {}
        for key, value in parse_qsl(query, keep_blank_values=True):
            values.setdefault(key, value)
        return values
    if context is not None:
        return {str(key): str(value) for key, value in context.items() if value is not None}
    return {}


def context_link(
    context: str | Mapping[str, object] | None,
    *,
    view: ViewId | str,
    **updates: object,
) -> str:
    """Stable local links preserve context; a new target resets its page offset."""

    values = query_values(context)
    if values.get("view") != str(view) or any(
        values.get(key) != str(value)
        for key, value in updates.items()
        if key not in {"page", "lang"}
    ):
        values.pop("page", None)
    values["view"] = str(view)
    for key, value in updates.items():
        if value is None:
            values.pop(key, None)
        else:
            values[key] = str(value)
    return "/?" + urlencode(sorted(values.items()))


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

    def render(self, context: str | Mapping[str, object] | None, *, view: ViewId | str) -> str:
        pages = max(1, (self.total + self.page_size - 1) // self.page_size)
        links = []
        for label, label_zh, rel, target in (
            ("Previous", "上一页", "prev", self.page - 1),
            ("Next", "下一页", "next", self.page + 1),
        ):
            if 1 <= target <= pages:
                url = context_link(context, view=view, page=target, page_size=self.page_size)
                links.append(
                    f'<a class="pagination-link" rel="{rel}" '
                    f'href="{escape(url, quote=True)}" aria-label="{label} / {label_zh}">'
                    f'{label} / <span lang="zh-CN">{label_zh}</span></a>'
                )
        return (
            '<nav class="page-pagination" aria-label="Read-model pagination / 只读模型分页">'
            f'<span>Page {self.page} of {pages} · {self.total} indexed entries'
            f' / <span lang="zh-CN">第 {self.page} / {pages} 页 · '
            f'共 {self.total} 条索引</span></span>'
            + "".join(links)
            + "</nav>"
        )


__all__ = [
    "NAVIGATION",
    "NAVIGATION_BY_ID",
    "NAVIGATION_LABELS_ZH",
    "NavigationItem",
    "PageWindow",
    "ViewId",
    "clear_filters_link",
    "context_link",
    "navigation_item",
    "navigation_label_zh",
    "query_values",
]
