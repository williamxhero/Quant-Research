"""Bilingual catalogue for the R5 Search Reader."""

from __future__ import annotations

from collections.abc import Mapping

from ..translator import M

# Reader sentences intentionally remain complete and deterministic.
# ruff: noqa: E501

ENTRIES: Mapping[str, M] = {
    "reader.search.eyebrow": M("搜索阅读器 · 只读", "Search Reader · read-only"),
    "reader.search.title": M("搜索阅读器", "Search Reader"),
    "reader.search.question": M(
        "哪些已批准的记录或文档元数据匹配查询，匹配发生在哪个字段？",
        "Which approved records or document metadata match the query, and in which field did the match occur?",
    ),
    "reader.search.confirmed_intro": M(
        "这里只显示已批准索引中的命中；每个命中都保留匹配字段、筛选条件和来源范围。",
        "Only hits from the approved index are shown; each hit retains its matched fields, filters, and source scope.",
    ),
    "reader.search.unknown_intro": M(
        "部分索引、缺失来源或不可用 API 时，无法得出全局无匹配或研究结论。",
        "A partial index, missing source, or unavailable API cannot establish a global no-match or a research conclusion.",
    ),
    "reader.search.why_intro": M(
        "Reader 只使用固定字面匹配规则；命中说明查询词匹配了哪个字段，不把搜索命中当作研究结论。",
        "The Reader uses only a fixed literal-matching rule; a hit explains which field matched the query and is never a research conclusion.",
    ),
    "reader.search.read_only": M(
        "只读；不会运行搜索任务、修改索引、打开私有存储或把命中升级为研究结论。",
        "Read-only; this page does not run search jobs, modify the index, open private storage, or promote a hit to a research conclusion.",
    ),
    "reader.search.not_evidence": M(
        "搜索命中只是索引匹配，不是研究成功、失败、有效性或证据结论。",
        "A Search hit is an index match, not a conclusion about research success, failure, validity, or evidence.",
    ),
    "reader.search.match_heading": M("命中解释", "Why this hit matched"),
    "reader.search.match_fields": M("匹配字段", "Matched fields"),
    "reader.search.match_reason": M("固定匹配说明", "Deterministic match explanation"),
    "reader.search.filter_heading": M("当前筛选与范围", "Current filters and scope"),
    "reader.search.filter_type": M("类型筛选", "Type filter"),
    "reader.search.filter_source": M("来源筛选", "Source filter"),
    "reader.search.filter_snapshot": M("快照", "Snapshot"),
    "reader.search.filter_scope": M("索引范围", "Index scope"),
    "reader.search.scope_complete": M("完整已批准索引", "Complete approved index"),
    "reader.search.scope_partial": M("仅当前索引页面；不代表全局", "Current indexed page only; not global"),
    "reader.search.no_global": M("完整快照中没有匹配；这不是研究结论。", "No match exists in the complete snapshot; this is not a research conclusion."),
    "reader.search.no_conclusion": M("没有属主记录支持研究结论；无法得出结论。", "No owner record supports a research conclusion; no conclusion can be drawn."),
    "reader.search.expert_heading": M("搜索专业视图", "Search Expert view"),
    "reader.search.raw_heading": M("搜索原始来源", "Search raw source"),
    "reader.search.open_history": M("打开研究历史阅读器", "Open Research History Reader"),
    "reader.search.open_documents": M("打开来源文档阅读器", "Open Source Documents Reader"),
    "reader.search.as_of": M("截至", "As of"),
    "reader.search.snapshot": M("快照", "Snapshot"),
    "reader.search.summary": M("已记录 {n} 个搜索阅读器命中说明。", "The Search Reader recorded {n} hit explanations."),
    "reader.search.sample_banner": M("样例数据，不代表真实研究结果：{fixture}", "Sample data; not a real research result: {fixture}"),
}

__all__ = ["ENTRIES"]
