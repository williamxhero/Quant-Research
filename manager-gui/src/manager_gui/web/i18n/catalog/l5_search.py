"""L5-T1 additive catalog for the deterministic Search surface."""

from __future__ import annotations

from collections.abc import Mapping

from ..translator import M

# Bilingual catalog entries remain readable as complete sentence pairs.
# ruff: noqa: E501

_FIELDS = {
    "record_id": M("记录 ID", "Record ID"),
    "type": M("类型", "Type"),
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

_RECORD_TYPES = {
    "campaign": M("研究活动", "Campaign"),
    "strategy": M("策略", "Strategy"),
    "run": M("运行", "Run"),
    "report": M("报告", "Report"),
}

_STATUSES = {
    "active": M("活动", "Active"),
    "validated": M("已验证", "Validated"),
    "completed": M("已完成", "Completed"),
    "published": M("已发布", "Published"),
}

_FIXTURE_TEXT = {
    "campaign_title": M("样例研究活动", "Fixture campaign"),
    "campaign_statement": M("验证确定性研究路径。", "Validate the deterministic research path."),
    "campaign_summary": M("用于只读搜索的已批准样例研究活动。", "Approved fixture campaign for read-only search."),
    "strategy_title": M("样例策略", "Fixture strategy"),
    "strategy_statement": M("确定性的策略陈述。", "A deterministic strategy statement."),
    "strategy_summary": M("来自已批准读模型的策略元数据。", "Strategy metadata from an approved read model."),
    "run_title": M("样例运行", "Fixture run"),
    "run_summary": M("已完成的确定性样例运行。", "Completed deterministic fixture run."),
    "report_title": M("样例研究报告", "Fixture research report"),
    "report_statement": M("记录化的证据陈述。", "Documented evidence statement."),
    "report_summary": M("批准的文档标题仅作为可搜索元数据。", "Approved document title is searchable metadata only."),
}

ENTRIES: Mapping[str, M] = {
    "l5.search.eyebrow": M("搜索 · 已批准的确定性索引", "Search · deterministic approved index"),
    "l5.search.title": M("搜索", "Search"),
    "l5.search.intro": M(
        "在已批准的记录和文档元数据中进行字面、不区分大小写的匹配；不使用语义或大语言模型排序。",
        "Literal, case-insensitive matching across approved records and document metadata; no semantic or LLM ranking is used.",
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
        "The approved index is complete; an empty result is a global no-match only for this known snapshot.",
    ),
    "l5.search.pagination_partial": M(
        "当前仅提供已索引页面；空页面不表示全局无匹配。",
        "Only the indexed page is available; an empty page is not a global no-match.",
    ),
    "l5.search.no_global_match": M(
        "在完整快照中没有已批准的记录或文档匹配此查询。",
        "No approved record or document matches this query in the complete snapshot.",
    ),
    "l5.search.no_match_scope": M("当前范围中尚未索引匹配条目。", "No matching entry is currently indexed in this scope."),
    "l5.search.enter_query": M("输入查询以搜索已批准的记录和文档索引。", "Enter a query to search the approved record and document index."),
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
    "l5.search.page_empty": M("此页面没有可见的索引条目。", "No indexed entries are visible on this page."),
    "l5.search.results_aria": M("确定性搜索结果", "Deterministic search results"),
    "l5.search.matched_fields": M("匹配字段", "Matched fields"),
    "l5.search.reason": M("原因", "Reason"),
    "l5.search.source": M("来源", "Source"),
    "l5.search.missing_source": M("未记录 / 未确认来源引用", "Missing / Unconfirmed source reference"),
    "l5.search.missing": M("未记录 / 未确认", "Missing / Unconfirmed"),
    "l5.search.browse_entry": M("无（浏览条目）", "none (browse entry)"),
    "l5.search.next_page": M("下一页索引", "Next indexed page"),
    "l5.search.next_page_aria": M("加载下一页搜索索引", "Load next indexed Search page"),
    "l5.search.match_reason_terms": M("{query_term} 匹配 {fields}", "{query_term} matched {fields}"),
    "l5.search.browse_reason": M(
        "未提供查询词；此条目已编入索引。",
        "No query terms were supplied; this entry is indexed.",
    ),
    "l5.search.fixture.complete_reason": M(
        "完整样例包含所有已批准的记录和文档搜索条目。",
        "The complete fixture contains all approved record and document search entries.",
    ),
    "l5.search.fixture.partial_reason": M(
        "当前仅编入已批准搜索页面；可能还有其他条目。",
        "Only the current approved Search page is indexed; more entries may exist.",
    ),
    "l5.search.fixture.partial_error": M(
        "已批准搜索索引还有更多页面；不允许得出全局无匹配结论。",
        "The approved Search index has more pages; no global no-match claim is allowed.",
    ),
    "l5.search.fixture.empty_reason": M(
        "此样例范围内没有已批准的搜索记录。",
        "No approved Search records are present in this fixture scope.",
    ),
    "l5.search.fixture.api_reason": M(
        "此环境中的已批准搜索 API 不可用。",
        "The approved Search API is unavailable in this environment.",
    ),
    "l5.search.fixture.api_error": M(
        "全局搜索不允许回退到私有存储。",
        "No private-storage fallback is permitted for global Search.",
    ),
    **{f"label.l5_search_field.{key}": value for key, value in _FIELDS.items()},
    **{f"label.l5_search_kind.{key}": value for key, value in _LABELS.items()},
    **{f"label.l5_search_record_type.{key}": value for key, value in _RECORD_TYPES.items()},
    **{f"label.l5_search_status.{key}": value for key, value in _STATUSES.items()},
    **{f"l5.search.fixture.{key}": value for key, value in _FIXTURE_TEXT.items()},
}

__all__ = ["ENTRIES"]
