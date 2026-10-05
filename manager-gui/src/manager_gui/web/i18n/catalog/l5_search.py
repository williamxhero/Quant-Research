"""L5-T1 additive catalog for the deterministic Search surface."""

from __future__ import annotations

from collections.abc import Mapping

from ..translator import M

_FIELDS = {
    "record_id": M("记录 ID", "Record ID"),
    "schema": M("Schema", "Schema"),
    "hash": M("哈希", "Hash"),
    "revision": M("修订", "Revision"),
    "campaign": M("研究活动", "Campaign"),
    "strategy": M("策略", "Strategy"),
    "run": M("运行", "Run"),
    "family": M("策略族", "Family"),
    "status": M("状态", "Status"),
    "date": M("日期", "Date"),
    "title": M("标题", "Title"),
    "statement": M("陈述", "Statement"),
    "safe_summary": M("安全摘要", "Safe summary"),
    "document_title": M("文档标题", "Document title"),
}

_LABELS = {
    "record": M("记录", "Record"),
    "document": M("文档", "Document"),
    "all": M("全部", "All"),
    "none": M("无", "None"),
}

ENTRIES: Mapping[str, M] = {
    "l5.search.eyebrow": M("搜索 · 已批准的确定性索引", "Search · deterministic approved index"),
    "l5.search.title": M("搜索", "Search"),
    "l5.search.intro": M(
        "在已批准的记录和文档元数据中进行字面、不区分大小写的匹配；不使用语义或 LLM 排序。",
        "Literal, case-insensitive matching across approved records and document metadata; "
        "no semantic or LLM ranking is used.",
    ),
    "l5.search.query": M("查询", "Query"),
    "l5.search.form_aria": M("搜索表单", "Search form"),
    "l5.search.query_placeholder": M("输入查询", "Enter a query"),
    "l5.search.query_aria": M("搜索查询", "Search query"),
    "l5.search.query_title": M("输入字面搜索查询", "Enter a literal search query"),
    "l5.search.submit": M("搜索", "Search"),
    "l5.search.none": M("无", "None"),
    "l5.search.observed": M("观察时间", "Observed"),
    "l5.search.snapshot": M("快照", "Snapshot"),
    "l5.search.sources": M("来源", "Sources"),
    "l5.search.unavailable": M("不可用", "Unavailable"),
    "l5.search.none_recorded": M("未记录", "None recorded"),
    "l5.search.pagination_complete": M(
        "已批准索引完整；只有在此已知快照中，空结果才表示全局无匹配。",
        "The approved index is complete; an empty result is a global no-match only "
        "for this known snapshot.",
    ),
    "l5.search.pagination_partial": M(
        "当前仅提供已索引页面；空页面不表示全局无匹配。",
        "Only the indexed page is available; an empty page is not a global no-match.",
    ),
    "l5.search.no_global_match": M(
        "在完整快照中没有已批准的记录或文档匹配此查询。",
        "No approved record or document matches this query in the complete snapshot.",
    ),
    "l5.search.no_match_scope": M(
        "当前范围中尚未索引匹配条目。", "No matching entry is currently indexed in this scope."
    ),
    "l5.search.enter_query": M(
        "输入查询以搜索已批准的记录和文档索引。",
        "Enter a query to search the approved record and document index.",
    ),
    "l5.search.partial_empty": M(
        "当前索引页面没有匹配条目；尚未建立全局无匹配结论。",
        "The current indexed page has no matching entry; global no-match is not established.",
    ),
    "l5.search.partial_hits": M(
        "搜索结果仅覆盖当前索引页面；可能还有其他记录匹配。",
        "Search results cover only the current indexed page; more records may match.",
    ),
    "l5.search.api_unavailable": M(
        "已批准的搜索 API 不可用；不会回退到私有存储。",
        "The approved Search API is unavailable; no private-storage fallback is used.",
    ),
    "l5.search.error": M(
        "已批准的搜索读模型不能作为完整的当前事实使用。",
        "The approved Search read model cannot be used as complete current truth.",
    ),
    "l5.search.page_empty": M(
        "此页面没有可见的索引条目。", "No indexed entries are visible on this page."
    ),
    "l5.search.results_aria": M("确定性搜索结果", "Deterministic search results"),
    "l5.search.matched_fields": M("匹配字段", "Matched fields"),
    "l5.search.reason": M("原因", "Reason"),
    "l5.search.source": M("来源", "Source"),
    "l5.search.missing_source": M(
        "未记录 / 未确认来源引用", "Missing / Unconfirmed source reference"
    ),
    "l5.search.missing": M("未记录 / 未确认", "Missing / Unconfirmed"),
    "l5.search.browse_entry": M("无（浏览条目）", "none (browse entry)"),
    "l5.search.next_page": M("下一页索引", "Next indexed page"),
    "l5.search.next_page_aria": M("加载下一页搜索索引", "Load next indexed Search page"),
    "l5.search.match_reason_terms": M("{term} 匹配 {fields}", "{term} matched {fields}"),
    **{f"label.l5_search_field.{key}": value for key, value in _FIELDS.items()},
    **{f"label.l5_search_kind.{key}": value for key, value in _LABELS.items()},
}

__all__ = ["ENTRIES"]
