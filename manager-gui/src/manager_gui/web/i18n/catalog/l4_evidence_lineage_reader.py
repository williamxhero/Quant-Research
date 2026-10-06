"""Page-owned bilingual catalogue for the R4 Evidence/Lineage Reader."""

from __future__ import annotations

from ..translator import M

ENTRIES: dict[str, M] = {
    "reader.evidence_lineage.eyebrow": M("证据与谱系 · 只读", "Evidence and lineage · read-only"),
    "reader.evidence_lineage.title": M("证据追溯阅读器", "Evidence trace Reader"),
    "reader.evidence_lineage.intro": M(
        "从结论沿已记录的证据、来源、制品和谱系关系追溯。候选证据不会被提升为符合研究协议的证据。",
        "Trace a conclusion through recorded evidence, sources, artifacts, and lineage "
        "relations. Candidate evidence is never promoted to protocol-conforming evidence.",
    ),
    "reader.evidence_lineage.chain_heading": M("追溯链", "Trace chain"),
    "reader.evidence_lineage.chain_caption": M(
        "结论到来源、制品和谱系的已记录路径",
        "Recorded path from conclusion to sources, artifacts, and lineage",
    ),
    "reader.evidence_lineage.source": M("来源", "Source"),
    "reader.evidence_lineage.derivation": M("派生方式", "Derivation"),
    "reader.evidence_lineage.availability": M("可用性", "Availability"),
    "reader.evidence_lineage.evidence_class": M("证据类别", "Evidence class"),
    "reader.evidence_lineage.status": M("状态", "Status"),
    "reader.evidence_lineage.recorded": M("明确记录", "Explicitly recorded"),
    "reader.evidence_lineage.not_recorded": M("未记录或未确认", "Missing / Unconfirmed"),
    "reader.evidence_lineage.no_value": M("没有已发布值", "No published value"),
    "reader.evidence_lineage.no_source": M("未发布来源", "No source published"),
    "reader.evidence_lineage.no_derivation": M("派生方式未记录", "Derivation not recorded"),
    "reader.evidence_lineage.no_lineage": M(
        "未发布明确的谱系关系；阅读器不会猜测关联原因。",
        "No explicit lineage relation is published; the Reader does not guess why "
        "records are related.",
    ),
    "reader.evidence_lineage.relations_heading": M("谱系关系表", "Lineage relation table"),
    "reader.evidence_lineage.relations_intro": M(
        "默认以来源链和表格显示关系；每条关系区分关系是什么、为什么关联以及是否明确记录。",
        "Relations are shown as a source chain and table by default; each row "
        "separates what the relation is, why it is associated, and whether it is explicit.",
    ),
    "reader.evidence_lineage.what": M("关系是什么", "What this relation is"),
    "reader.evidence_lineage.why": M("为什么关联", "Why these records are related"),
    "reader.evidence_lineage.relation": M("关系", "Relation"),
    "reader.evidence_lineage.from": M("来源记录", "From record"),
    "reader.evidence_lineage.to": M("目标记录", "To record"),
    "reader.evidence_lineage.unknown_reason": M(
        "关联原因未明确记录；不能补猜测。",
        "The reason for this association is not explicitly recorded; no inference is added.",
    ),
    "reader.evidence_lineage.explicit_yes": M("是，关系已发布", "Yes, relation is published"),
    "reader.evidence_lineage.explicit_no": M("否，关系未发布", "No, relation is not published"),
    "reader.evidence_lineage.open_evidence": M("返回证据结论", "Return to evidence conclusion"),
    "reader.evidence_lineage.open_lineage": M("打开谱系专业模式", "Open Lineage Expert"),
    "reader.evidence_lineage.open_source": M("查看来源", "View source"),
    "reader.evidence_lineage.open_artifact": M("查看制品", "View artifact"),
    "reader.evidence_lineage.expert_heading": M("专业谱系图", "Expert lineage graph"),
    "reader.evidence_lineage.expert_intro": M(
        "图谱保留为 Expert 视图；Reader 默认语义来自同一份已发布关系和表格。",
        "The graph remains an Expert view; Reader semantics use the same published "
        "relations and table.",
    ),
    "reader.evidence_lineage.raw_heading": M(
        "原始证据与谱系载荷", "Raw evidence and lineage payload"
    ),
    "reader.evidence_lineage.sample_banner": M(
        "以下为完整公开样例，不代表实时数据。", "Complete public fixture; not live data."
    ),
    "reader.evidence_lineage.derived_boundary": M(
        "这是阅读器派生的解释，不是属主事实。",
        "This is a Reader-derived interpretation, not an owner fact.",
    ),
    "reader.evidence_lineage.relation_gap": M(
        "谱系关系未在当前范围内发布。",
        "The lineage relation is not published in the current scope.",
    ),
    "reader.evidence_lineage.read_only": M("只读", "Read-only"),
    "reader.evidence_lineage.none": M("无", "None"),
    "label.reader_trace_step.conclusion": M("结论", "Conclusion"),
    "label.reader_trace_step.evidence": M("证据", "Evidence"),
    "label.reader_trace_step.source": M("来源", "Source"),
    "label.reader_trace_step.artifact": M("制品", "Artifact"),
    "label.reader_trace_step.lineage": M("谱系", "Lineage"),
    "label.reader_trace_recorded.yes": M("已明确记录", "Explicitly recorded"),
    "label.reader_trace_recorded.no": M("未明确记录", "Not explicitly recorded"),
    "label.reader_trace_availability.known": M("可用", "Known"),
    "label.reader_trace_availability.missing": M("缺失", "Missing"),
    "label.reader_trace_availability.blocked": M("已阻塞", "Blocked"),
    "label.reader_trace_availability.stale": M("已过时", "Stale"),
    "label.reader_trace_availability.incomparable": M("不可比较", "Incomparable"),
    "label.reader_trace_availability.not_evaluated": M("未评估", "Not evaluated"),
    "label.reader_trace_availability.integrity_failure": M("完整性失败", "Integrity failure"),
    "label.reader_trace_availability.api_unavailable": M("接口不可用", "API unavailable"),
}


__all__ = ["ENTRIES"]
