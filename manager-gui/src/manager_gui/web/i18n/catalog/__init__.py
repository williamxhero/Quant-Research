"""Registry of validated translation catalogs.

Each catalog module builds a dict of `M` entries and calls `register()` at import
time. Registration validates every entry (see `validate_entry`) and rejects any key
that is already registered, so two modules can never silently override each other.
Page catalogs are imported at the bottom of this file, after `REGISTRY` exists, so
that importing the package populates the registry. No page catalog exists yet.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from ..translator import M, TranslationError, validate_entry


class CatalogError(TranslationError):
    """A catalog entry is invalid or collides with an existing key."""


def _entries_arg(entries: Mapping[str, M] | str, message: M | None) -> Mapping[str, M]:
    if isinstance(entries, str):
        if message is None:
            raise CatalogError(f"missing message for catalog key: {entries!r}")
        return {entries: message}
    if message is not None:
        raise CatalogError("message is only accepted with a single catalog key")
    if not isinstance(entries, Mapping):
        raise CatalogError(f"catalog entries must be a mapping, got {type(entries).__name__}")
    return entries


def merge(*parts: Mapping[str, M]) -> dict[str, M]:
    """Combine catalog dicts into a new validated dict; a repeated key is an error."""

    merged: dict[str, M] = {}
    for part in parts:
        for key, message in part.items():
            validate_entry(key, message)
            if key in merged:
                raise CatalogError(f"duplicate catalog key: {key!r}")
            merged[key] = message
    return merged


class CatalogRegistry:
    """An append-only set of validated entries, exposed as a read-only view."""

    __slots__ = ("_entries", "_view")

    def __init__(self) -> None:
        self._entries: dict[str, M] = {}
        self._view: Mapping[str, M] = MappingProxyType(self._entries)

    @property
    def entries(self) -> Mapping[str, M]:
        """Live read-only view; entries registered later become visible through it."""

        return self._view

    def register(
        self, entries: Mapping[str, M] | str, message: M | None = None
    ) -> None:
        """Validate and add entries atomically: on any error nothing is registered."""

        try:
            staged = merge(_entries_arg(entries, message))
        except TranslationError as exc:
            if isinstance(exc, CatalogError):
                raise
            raise CatalogError(str(exc)) from exc
        for key in staged:
            if key in self._entries:
                raise CatalogError(f"duplicate catalog key: {key!r}")
        self._entries.update(staged)


REGISTRY = CatalogRegistry()
# A short public alias for callers that only need the read-only catalog mapping.
CATALOG = REGISTRY.entries


def register(entries: Mapping[str, M] | str, message: M | None = None) -> None:
    """Register entries in the process-wide registry used by default Translators."""

    REGISTRY.register(entries, message)


# Shared shell text is registered here rather than in a renderer.  Keeping the
# entries in the catalog package means every shell surface uses the same
# placeholder validation and future page catalogs can append without creating a
# second translation layer.
SHELL_CATALOG: Mapping[str, M] = {
    "shell.brand": M("{term:manager_gui}", "{term:manager_gui}"),
    "shell.title": M("{view} · {term:manager_gui}", "{view} · {term:manager_gui}"),
    "shell.skip_to_workspace": M("跳到工作区", "Skip to workspace"),
    "shell.brand_home": M("管理界面首页", "Manager GUI home"),
    "shell.workspace_snapshot": M(
        "{term:fixture} · {term:snapshot} {snapshot}",
        "{term:fixture} workspace · {term:snapshot} {snapshot}",
    ),
    "shell.read_only": M("只读", "READ ONLY"),
    "shell.read_only_aria": M("只读，已禁用变更", "Read-only; mutations are disabled"),
    "shell.global_search": M("全局搜索", "Global search"),
    "shell.search_placeholder": M("搜索只读模型…", "Search read models…"),
    "shell.shared_panels": M("共享面板", "Shared panels"),
    "shell.open_inspector": M("打开检查器", "Open inspector"),
    "shell.open_events": M("打开事件与原始 JSON", "Open events and raw JSON"),
    "shell.inspector": M("{term:inspector}", "{term:inspector}"),
    "shell.read_context": M("读取上下文", "Read context"),
    "shell.read_model": M("读取模型", "Read model"),
    "shell.status": M("状态", "Status"),
    "shell.snapshot": M("{term:snapshot}", "{term:snapshot}"),
    "shell.observed_at": M("观测时间", "Observed at"),
    "shell.sources": M("{term:source}", "{term:source}"),
    "shell.none_recorded": M("未记录", "None recorded"),
    "shell.opaque_reference": M("{term:opaque_reference}", "{term:opaque_reference}"),
    "shell.raw_json": M("{term:raw_json}", "{term:raw_json}"),
    "shell.view_raw_json": M("查看原始 JSON", "View raw JSON"),
    "shell.events_raw_json": M("事件与原始 JSON", "Events & raw JSON"),
    "shell.close_panels": M("关闭面板", "Close panels"),
    "shell.close": M("关闭", "Close"),
    "shell.raw_json_aria": M(
        "原始 ManagerReadModel v0 JSON", "Raw ManagerReadModel v0 JSON"
    ),
    "shell.shared_shell": M("共享外壳 · 样例数据驱动", "Shared shell · fixture-backed"),
    "shell.page_intro": M(
        "本页面仅提供方向与溯源信息；领域页面通过公开读模型钩子接入。",
        "This slice provides orientation and provenance only; domain pages attach through the public read-model hook.",
    ),
    "shell.view": M("视图", "View"),
    "shell.fixture": M("样例数据", "Fixture"),
    "shell.observed": M("截至时间", "Observed"),
    "shell.integration_ready": M("集成点已就绪", "Integration point ready"),
    "shell.placeholder_intro": M(
        "此占位内容不会推断属主事实。未来视图可使用相同的 {schema} 信封，并保留此外壳、详情面板和事件抽屉。",
        "This placeholder deliberately does not infer owner facts. A future view can consume the same {schema} envelope and keep this shell, inspector, and event drawer.",
    ),
    "shell.hook": M("钩子：{hook}", "hook: {hook}"),
    "shell.snapshot_missing": M("无快照令牌", "No snapshot token"),
    "shell.unavailable": M("不可用", "Unavailable"),
    "shell.copy_reference": M("复制引用", "Copy reference"),
    "shell.language": M("语言", "Language"),
    "shell.language_zh": M("中文", "中文"),
    "shell.language_en": M("English", "English"),
}

NAVIGATION_CATALOG: Mapping[str, M] = {
    "nav.aria": M("管理界面分区", "Manager GUI sections"),
    "nav.atlas.label": M("总览", "Atlas"),
    "nav.atlas.description": M("工作区地图与当前只读模型范围。", "Workspace map and current read-model scope."),
    "nav.stories.label": M("研究故事", "Stories"),
    "nav.stories.description": M("研究故事索引与溯源轨迹。", "Research story index and provenance trail."),
    "nav.strategies.label": M("策略 / {term:strategy_genome}", "Strategies / Genomes"),
    "nav.strategies.description": M("策略与策略基因组只读界面。", "Strategy and genome read surfaces."),
    "nav.strategy-conditions.label": M("基因组条件", "Genome Conditions"),
    "nav.strategy-conditions.description": M("基因组适用性、失效条件与描述证据。", "Genome applicability, invalidation, and descriptor evidence."),
    "nav.strategy-genome-comparison.label": M("基因组比较", "Genome Comparison"),
    "nav.strategy-genome-comparison.description": M("明确的基因组比较维度与溯源信息。", "Explicit Genome comparison axes and provenance."),
    "nav.memory.label": M("记忆", "Memory"),
    "nav.memory.description": M("失败知识与保留的研究记忆。", "Failure knowledge and retained research memory."),
    "nav.memory-failures.label": M("记忆失败", "Memory Failures"),
    "nav.memory-failures.description": M("正式研究记忆失败条目与明确谱系。", "Formal Memory failure entries and explicit lineage."),
    "nav.failure-patterns.label": M("失败模式", "Failure Patterns"),
    "nav.failure-patterns.description": M("普通失败与明确派生的失败模式。", "Ordinary failures and explicitly derived patterns."),
    "nav.evidence.label": M("证据", "Evidence"),
    "nav.evidence.description": M("证据谱系、来源引用与比较。", "Evidence lineage, source references, and comparisons."),
    "nav.lineage.label": M("谱系", "Lineage"),
    "nav.lineage.description": M("有界证据谱系图、表格与来源路径。", "Bounded evidence lineage graph, table, and source path."),
    "nav.evidence-object-comparison.label": M("证据比较", "Evidence Comparison"),
    "nav.evidence-object-comparison.description": M("按声明维度进行通用对象与证据比较。", "General object and evidence comparison by declared axes."),
    "nav.derived-failure-grouping.label": M("派生失败分组", "Derived Failure Grouping"),
    "nav.derived-failure-grouping.description": M("明确派生的成功与失败分组。", "Explicit Derived success and failure groupings."),
    "nav.methodology.label": M("研究方法库", "Methodology"),
    "nav.methodology.description": M("方法、契约与解读说明。", "Methods, contracts, and interpretation notes."),
    "nav.history.label": M("历史", "History"),
    "nav.history.description": M("历史快照与来源修订。", "Historical snapshots and source revisions."),
    "nav.source-documents.label": M("来源文档", "Source Documents"),
    "nav.source-documents.description": M("已批准的文档索引与记录引用。", "Approved document index and record citations."),
    "nav.search.label": M("搜索", "Search"),
    "nav.search.description": M("在已批准索引的只读模型记录中搜索。", "Search across approved read-model records."),
    "nav.portal.label": M("报告门户", "Portal"),
    "nav.portal.description": M("已发布的策略报告来源与制品元数据。", "Published Strategy Reporting source and artifact metadata."),
}

PAGINATION_CATALOG: Mapping[str, M] = {
    "pagination.previous": M("上一页", "Previous"),
    "pagination.next": M("下一页", "Next"),
    "pagination.aria": M("只读模型分页", "Read-model pagination"),
    "pagination.summary": M(
        "第 {page} / {pages} 页 · 共 {n} 条索引",
        "Page {page} of {pages} · {n} indexed entries",
    ),
}

register(merge(SHELL_CATALOG, NAVIGATION_CATALOG, PAGINATION_CATALOG))


__all__ = [
    "CATALOG",
    "NAVIGATION_CATALOG",
    "PAGINATION_CATALOG",
    "REGISTRY",
    "SHELL_CATALOG",
    "CatalogError",
    "CatalogRegistry",
    "merge",
    "register",
]
