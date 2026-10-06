"""Bilingual catalogue for the R5 Methodology Reader."""

from __future__ import annotations

from collections.abc import Mapping

from ..translator import M

# Complete bilingual sentences are intentionally kept readable at each entry.
# ruff: noqa: E501

ENTRIES: Mapping[str, M] = {
    "reader.methodology.eyebrow": M("研究方法 · 只读", "Research methodology · read-only"),
    "reader.methodology.title": M("研究方法阅读器", "Methodology Reader"),
    "reader.methodology.question": M(
        "研究方法如何积累、何时使用，以及限制是什么？",
        "How has the methodology accumulated, when is it used, and what are its limits?",
    ),
    "reader.methodology.confirmed_intro": M(
        "这里只显示已发布的方法条目和明确记录的来源。方法说明不是研究结论。",
        "Only published method entries and explicit source records are shown here. A method description is not a research conclusion.",
    ),
    "reader.methodology.unknown_intro": M(
        "缺少属主记录时，无法得出方法有效性或研究结果结论。",
        "When an owner record is missing, no conclusion about method validity or research results can be drawn.",
    ),
    "reader.methodology.why_intro": M(
        "解释来自 Reader 的固定模板；来源、as-of、快照和可用性沿用同一份公开读模型。",
        "The explanation uses fixed Reader templates; source, as-of, snapshot, and availability come from the same public read model.",
    ),
    "reader.methodology.scope": M("研究范围入口", "Research scope entry"),
    "reader.methodology.scope_intro": M(
        "选择一个已命名范围；范围不会被名称相似或时间相邻的记录替代。",
        "Choose a named scope; similarly named or nearby records never replace an explicit scope.",
    ),
    "reader.methodology.scope_a0": M("A0", "A0"),
    "reader.methodology.scope_s3": M("S3", "S3"),
    "reader.methodology.scope_cpa": M("CPA", "CPA"),
    "reader.methodology.scope_v1x": M("V1.x", "V1.x"),
    "reader.methodology.categories": M("方法类别", "Method categories"),
    "reader.methodology.category.workflow_process": M("流程 / 过程", "Workflow / process"),
    "reader.methodology.category.statistical_protocol": M("统计协议", "Statistical protocol"),
    "reader.methodology.category.policy": M("政策", "Policy"),
    "reader.methodology.category.benchmark": M("基准", "Benchmark"),
    "reader.methodology.category.operational_constraint": M("运行约束", "Operational constraint"),
    "reader.methodology.method": M("方法条目", "Method entry"),
    "reader.methodology.definition": M("解决的问题 / 定义", "Problem addressed / definition"),
    "reader.methodology.when": M("何时使用", "When to use"),
    "reader.methodology.limits": M("限制", "Limits"),
    "reader.methodology.validity": M("有效性记录", "Validity record"),
    "reader.methodology.not_recorded": M("未记录；无法据此得出结论", "Not recorded; no conclusion can be drawn from this"),
    "reader.methodology.usage_recorded": M("已记录使用条目", "Usage record is present"),
    "reader.methodology.usage_missing": M("未记录使用条件", "Usage conditions are not recorded"),
    "reader.methodology.validity_recorded": M("已明确记录有效性证据", "Validity evidence is explicitly recorded"),
    "reader.methodology.validity_missing": M("未记录有效性证据", "Validity evidence is not recorded"),
    "reader.methodology.current": M("当前未标记为过时", "Not marked as superseded"),
    "reader.methodology.superseded": M("已标记为过时", "Marked as superseded"),
    "reader.methodology.status": M("方法状态", "Method status"),
    "reader.methodology.scope_missing": M("未提供明确范围", "No explicit scope was provided"),
    "reader.methodology.no_entries": M("当前范围没有已发布方法条目。", "No published method entries are available in the current scope."),
    "reader.methodology.no_source": M("没有已发布来源；无法确认方法条目。", "No published source is available; the method entry cannot be confirmed."),
    "reader.methodology.source": M("来源", "Source"),
    "reader.methodology.read_only": M("只读；不会运行、重建或修改方法记录。", "Read-only; this page does not run, rebuild, or modify method records."),
    "reader.methodology.expert_heading": M("方法专业视图", "Methodology Expert view"),
    "reader.methodology.raw_heading": M("方法原始来源", "Methodology raw source"),
    "reader.methodology.open_history": M("打开研究历史", "Open research history"),
    "reader.methodology.open_documents": M("打开来源文档", "Open source documents"),
    "reader.methodology.as_of": M("截至", "As of"),
    "reader.methodology.snapshot": M("快照", "Snapshot"),
}

__all__ = ["ENTRIES"]
