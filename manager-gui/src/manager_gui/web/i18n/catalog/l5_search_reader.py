"""Bilingual catalogue for the R5 Search Reader."""

from __future__ import annotations

from collections.abc import Mapping

from ..translator import M

# Reader sentences intentionally remain complete and deterministic.
# ruff: noqa: E501

ENTRIES: Mapping[str, M] = {
    "reader.search.technical_details": M("查看技术核对信息", "Technical checking details"),
    "reader.search.coverage": M("这里只搜索本次已提供、可搜索的记录与文档标题等信息，不搜索未接入材料或私有存储。", "Only the supplied searchable records and document metadata are searched, not unconnected materials or private storage."),
    "reader.search.no_existence": M("没有命中不等于材料不存在；内容可能未接入、未在可搜索字段中或不在当前范围。", "A search result not found does not mean it does not exist; content may be unconnected, outside searchable fields or outside this scope."),
    "reader.search.related": M("相关是因为已提供内容包含搜索词，不代表已经核对或研究成功。", "A match is related because the supplied content contains your search terms, not because the research was checked or succeeded."),
    "reader.search.browse": M("未输入搜索词，这里列出当前范围可搜索的内容。", "No search terms were entered; searchable content in this scope is listed."),
    "reader.search.content_heading": M("可核对的命中内容", "Matched content to check"),
    "reader.search.not_found_content": M("当前提供范围内没有命中内容。", "No matching content was found in the supplied scope."),
    "reader.search.untitled": M("标题未提供的内容", "Content with no supplied title"),
    "reader.search.document_category": M("命中文档信息；文档内容是否可读须另行核对。", "Matching document metadata; readability of the document itself needs checking."),
    "reader.search.record_category": M("命中记录；不能仅据此称为报告。", "Matching record; it cannot be called a report from this alone."),
    "reader.search.ambiguous": M("未能唯一对应完整公开记录，不能假称已定位原文。", "The complete public record could not be uniquely identified; this is not a located original."),
    "reader.search.open_destination": M("在{location}打开“{title}”的对应内容", "Open the corresponding content for “{title}” in {location}"),
    "reader.search.destination_limit": M("本页依据入口打开已提供的命中字段；页面入口保留对应对象。原文段落位置未提供时，不宣称已定位原文。", "The support entry here opens supplied matched fields; the page entry retains the corresponding object. No original-text location is claimed unless supplied."),
    "reader.search.form_label": M("搜索已提供的内容", "Search supplied content"),
    "reader.search.query_label": M("想找什么内容？", "What content do you want to find?"),
    "reader.search.submit_label": M("搜索内容", "Search content"),
    "reader.search.eyebrow": M("搜索阅读器 · 只读", "Search Reader · read-only"),
    "reader.search.title": M("找到了什么，为什么相关？", "What was found, and why is it related?"),
    "reader.search.question": M(
        "哪些已批准的记录或文档元数据匹配查询，匹配发生在哪个字段？",
        "Which approved records or document metadata match the query, and in which field did the match occur?",
    ),
    "reader.search.confirmed_intro": M(
        "查看哪些已提供的内容包含搜索词、为什么相关，以及能在哪里核对。没有搜到不代表不存在。",
        "See which supplied content contains your search terms, why it is related and where it can be checked. No match does not mean nonexistence.",
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
    "reader.search.scope_complete": M("本次提供的可搜索范围已完整读取，不代表所有资料", "The supplied searchable scope was read completely, not all materials"),
    "reader.search.scope_partial": M("仅提供了部分可搜索内容，其他内容仍未知，不能断言全部范围未命中", "Only some searchable content was supplied; global no-match is not established"),
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
