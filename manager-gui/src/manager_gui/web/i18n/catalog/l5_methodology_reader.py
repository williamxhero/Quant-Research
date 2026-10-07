"""Bilingual catalogue for the R5 Methodology Reader."""

from __future__ import annotations

from collections.abc import Mapping

from ..translator import M

# Complete bilingual sentences are intentionally kept readable at each entry.
# ruff: noqa: E501

ENTRIES: Mapping[str, M] = {
    "reader.methodology.eyebrow": M("研究方法 · 只读", "Research methodology · read-only"),
    "reader.methodology.title": M("检查了什么，实际做过什么？", "What was checked, and what was actually done?"),
    "reader.methodology.question": M(
        "研究方法如何积累、何时使用，以及限制是什么？",
        "How has the methodology accumulated, when is it used, and what are its limits?",
    ),
    "reader.methodology.confirmed_intro": M(
        "查看每项方法检查什么、是否有检查记录，以及记录中的结果和范围。方法目录中的条目不能证明已经执行检查。方法说明不是研究结论。",
        "Read what each method checks, whether a check was recorded, its results and scope. A method catalog entry is not proof that a check was executed. A method description is not a research conclusion.",
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
        "选择要浏览的资料范围。未提供的研究范围不由名称或时间推断。",
        "Choose the material scope to browse. Missing research scope is not inferred from names or times.",
    ),
    "reader.methodology.scope_a0": M("A0", "A0"),
    "reader.methodology.scope_s3": M("S3", "S3"),
    "reader.methodology.scope_cpa": M("CPA", "CPA"),
    "reader.methodology.scope_v1x": M("V1.x", "V1.x"),
    "reader.methodology.technical": M("技术核对", "Technical verification"),
    "reader.methodology.categories": M("方法类别", "Method categories"),
    "reader.methodology.category.workflow_process": M("怎样安排检查？", "How are checks organized?"),
    "reader.methodology.category.statistical_protocol": M("怎样核对计算和数据？", "How are calculations and data checked?"),
    "reader.methodology.category.policy": M("必须遵守哪些要求？", "Which requirements must be followed?"),
    "reader.methodology.category.benchmark": M("用什么作对照？", "What is used for comparison?"),
    "reader.methodology.category.operational_constraint": M("执行受到哪些限制？", "What limits execution?"),
    "reader.methodology.method": M("方法条目", "Method entry"),
    "reader.methodology.definition": M("解决的问题 / 定义", "Problem addressed / definition"),
    "reader.methodology.when": M("实际检查记录", "Actual check records"),
    "reader.methodology.used_at": M("记录中的检查时间", "Check time in the record"),
    "reader.methodology.check_scope": M("检查对象与范围", "Check subjects and scope"),
    "reader.methodology.period": M("检查所用数据期间", "Period of data checked"),
    "reader.methodology.result": M("记录中的检查结果", "Check result in the record"),
    "reader.methodology.results": M("关联结果记录", "Associated result records"),
    "reader.methodology.results_missing": M("未提供关联结果记录；不能据此判断方法是否有效。", "No associated result record was supplied; method validity cannot be judged from this."),
    "reader.methodology.limits": M("限制", "Limits"),
    "reader.methodology.validity": M("有效性记录", "Validity record"),
    "reader.methodology.record_status": M("记录中的状态", "Status in the record"),
    "reader.methodology.validity_boundary": M("关联结果或有效性记录本身不能证明方法有效。", "An associated result or validity record does not by itself prove the method is valid."),
    "reader.methodology.not_recorded": M("未记录；无法据此得出结论", "Not recorded; no conclusion can be drawn from this"),
    "reader.methodology.usage_recorded": M("已记录使用条目", "Usage record is present"),
    "reader.methodology.usage_missing": M("未提供检查记录；这不代表没有执行检查。", "No check record was supplied; this does not mean the check was not executed."),
    "reader.methodology.execution_unconfirmed": M("无法从这份记录确认是否执行了检查。", "Execution cannot be confirmed from this record."),
    "reader.methodology.executed": M("记录明确写明已执行这项检查。", "The record explicitly says this check was executed."),
    "reader.methodology.not_executed": M("记录明确写明未执行这项检查。", "The record explicitly says this check was not executed."),
    "reader.methodology.stopped": M("记录写明这项检查中止；这不是已完成的检查。", "The record says this check stopped; this is not a completed check."),
    "reader.methodology.execution_missing": M("未记录是否执行了这项检查。", "Whether this check was executed was not recorded."),
    "reader.methodology.title_missing": M("未提供方法标题。", "Method title was not supplied."),
    "reader.methodology.definition_missing": M("未记录这个方法检查什么。", "What this method checks was not recorded."),
    "reader.methodology.checks": M("具体检查步骤", "Specific check steps"),
    "reader.methodology.checks_missing": M("未提供具体检查步骤。", "Specific check steps were not supplied."),
    "reader.methodology.lifecycle_missing": M("未记录是否已被替代。", "Superseded status was not recorded."),
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
    "reader.methodology.read_document": M("阅读材料条目：", "Read material entry:"),
    "reader.methodology.read_document_unnamed": M("阅读材料条目（未提供标题）", "Read material entry (title not supplied)"),
    "reader.methodology.read_record": M("阅读历史记录：", "Read history record:"),
    "reader.methodology.read_record_unnamed": M("阅读历史记录（未提供标题）", "Read history record (title not supplied)"),
    "reader.methodology.related_missing": M("未提供关联材料或记录。", "No related material or record was supplied."),
    "reader.methodology.open_history": M("打开研究历史", "Open research history"),
    "reader.methodology.open_documents": M("打开来源文档", "Open source documents"),
    "reader.methodology.as_of": M("截至", "As of"),
    "reader.methodology.snapshot": M("快照", "Snapshot"),
}

__all__ = ["ENTRIES"]
