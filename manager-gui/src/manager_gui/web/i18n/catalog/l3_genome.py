"""L3-T2 catalogs for Genome, condition evidence, and comparison pages.

This is intentionally an additive namespace module.  It registers through the
existing ``manager_gui.web.i18n.catalog.register`` API when imported by one of
the three page modules; ``catalog/__init__.py`` is deliberately unchanged in
L3-T2.  The L3 integration ticket should import this module once during catalog
bootstrap (after the registry exists), or retain the page imports as the
integration hook, and must not duplicate-register ``ENTRIES``.
"""

from __future__ import annotations

from collections.abc import Mapping

from ..translator import M
from . import register


ENTRIES: Mapping[str, M] = {
    # Genome page copy.
    "genome.eyebrow": M(
        "策略 / {term:strategy_genome} · {term:read_only}",
        "Strategies / Genomes · read-only",
    ),
    "genome.title": M("策略基因组", "Strategy Genomes"),
    "genome.intro": M(
        "检查已发布的策略基因组身份、行为投影、验证绑定、生命周期事件和谱系，不推断属主事实。",
        "Inspect published Genome identity, behavior projection, validation binding, lifecycle events, and lineage without inferring owner facts.",
    ),
    "genome.observed": M("截至时间", "Observed"),
    "genome.snapshot": M("快照", "Snapshot"),
    "genome.sources": M("来源", "Sources"),
    "genome.catalog": M("基因组目录", "Genome catalog"),
    "genome.catalog_aria": M("策略基因组目录", "Strategy Genome catalog"),
    "genome.no_records": M(
        "此范围中没有策略基因组记录。{term:missing}。",
        "No Genome records are present in this scope. Missing.",
    ),
    "genome.detail": M("基因组详情：{genome_id}", "Genome detail: {genome_id}"),
    "genome.back_catalog": M("返回目录", "Back to catalog"),
    "genome.detail_empty": M(
        "选择一个策略基因组查看详情；如果没有可用基因组，详情为{term:missing}。",
        "Select a Genome for detail; if no Genome is available, detail is Missing.",
    ),
    "genome.behavior_title": M("行为投影", "Behavior projection"),
    "genome.behavior_intro": M(
        "已发布读模型中的十四个行为字段都会显示；不会推断缺失字段。",
        "All fourteen behavior fields are shown from the published read model; missing fields are not inferred.",
    ),
    "genome.field": M("字段", "Field"),
    "genome.value": M("值", "Value"),
    "genome.validation_title": M("验证绑定", "Validation binding"),
    "genome.validation_intro": M(
        "验证是独立绑定，不会改变策略基因组的内容身份。",
        "Validation is a separate binding and does not change Genome content identity.",
    ),
    "genome.binding": M("绑定", "Binding"),
    "genome.lifecycle_title": M("生命周期时间线", "Lifecycle timeline"),
    "genome.lifecycle_intro": M(
        "这里只显示明确记录的 proposed、validated、published、revoked 和 tombstoned 来源事件；不会推断状态。",
        "Only explicit proposed, validated, published, revoked, and tombstoned source events are shown; no state is inferred.",
    ),
    "genome.lifecycle_aria": M("基因组生命周期事件时间线", "Genome lifecycle event timeline"),
    "genome.no_events": M(
        "没有记录明确的生命周期事件。{term:missing}。",
        "No explicit lifecycle events are recorded. Missing.",
    ),
    "genome.event_timeline": M("事件时间线", "Event timeline"),
    "genome.lineage_title": M("谱系入口", "Lineage entry points"),
    "genome.lineage_intro": M(
        "这些候选对象、研究假设、策略族、上下文、软件包、运行和证据引用，都是有来源支持的入口。",
        "These candidate, hypothesis, family, context, package, run, and evidence refs are source-backed entry points.",
    ),
    "genome.lineage_empty": M(
        "没有记录{kind}谱系入口。{term:missing}。",
        "No {kind} lineage entry recorded. Missing.",
    ),
    "genome.raw_json": M("原始 JSON", "Raw JSON"),
    "genome.sources_missing": M("缺少来源引用", "Missing source ref"),
    "genome.locator_missing": M("缺少定位器", "Missing locator"),
    "genome.related_aria": M("基因组相关视图", "Genome related views"),
    "genome.condition_evidence": M("条件证据", "Condition evidence"),
    "genome.compare": M("比较基因组", "Compare Genome"),
    "genome.filters_aria": M("基因组筛选器", "Genome filters"),
    "genome.filter_label": M("{label}", "{label}"),
    "label.genome_filter.schema": M("模式", "Schema"),
    "label.genome_filter.content_hash": M("内容哈希", "Content hash"),
    "label.genome_filter.candidate_revision": M("候选对象修订", "Candidate revision"),
    "label.genome_filter.lifecycle_state": M("生命周期状态", "Lifecycle state"),
    "label.genome_filter.q": M("关键词", "Query"),
    "genome.apply_filters": M("应用筛选", "Apply filters"),
    "genome.clear": M("清除", "Clear"),
    "genome.none_recorded": M("未记录", "None recorded"),
    "genome.unavailable": M("不可用", "Unavailable"),
    "genome.value_missing": M("未记录", "Missing"),
    "genome.value_empty": M("空值", "Empty"),
    "genome.fixture_actor": M("样例数据", "fixture"),
    "genome.fixture_lineage_label": M("样例数据 {kind}", "Fixture {kind}"),
    # Conditions page copy.
    "conditions.eyebrow": M(
        "策略 / 条件 · {term:read_only}", "Strategies / Conditions · read-only"
    ),
    "conditions.title": M("策略基因组条件与证据", "Genome conditions and evidence"),
    "conditions.intro": M(
        "只有属主记录发布证据时，才显示适用条件和失效条件。制度或行为描述仍是观察。",
        "Applicability and invalidation conditions are shown only when an owner record publishes evidence. Regime and behaviour descriptors remain observations.",
    ),
    "conditions.observed": M("截至时间", "Observed"),
    "conditions.snapshot": M("快照", "Snapshot"),
    "conditions.sources": M("来源", "Sources"),
    "conditions.stable_context": M("稳定条件上下文", "Stable condition context"),
    "conditions.related_aria": M("条件相关视图", "Condition related views"),
    "conditions.back_genome": M("返回策略基因组", "Back to Genome"),
    "conditions.compare": M("比较基因组", "Compare Genome"),
    "conditions.applicability_group": M(
        "有证据支持的适用条件", "Evidence-supported applicability conditions"
    ),
    "conditions.invalidation_group": M(
        "有证据支持的失效 / 失败条件", "Evidence-supported invalidation / failure conditions"
    ),
    "conditions.descriptor_group": M(
        "上下文描述 / 制度观察", "Contextual descriptors / regime observations"
    ),
    "conditions.descriptor_intro": M(
        "描述只是观察，不是经过验证的条件。",
        "Descriptors are observations only; they are not validated conditions.",
    ),
    "conditions.not_recorded": M("未记录", "not recorded"),
    "conditions.condition": M("条件", "Condition"),
    "conditions.scope": M("范围", "Scope"),
    "conditions.outcome": M("结果", "Outcome"),
    "conditions.evidence_level": M("证据等级", "Evidence level"),
    "conditions.time_range": M("时间范围", "Time range"),
    "conditions.data_version": M("数据版本", "Data version"),
    "conditions.sample": M("样本", "Sample"),
    "conditions.limitations": M("限制", "Limitations"),
    "conditions.source_refs": M("来源引用", "Source refs"),
    "conditions.fixture_liquidity": M("流动性阈值已满足", "liquidity threshold is met"),
    "conditions.fixture_quality": M("数据质量关口未通过", "data quality gate fails"),
    "conditions.fixture_regime": M("高波动制度", "high-volatility regime"),
    "conditions.fixture_window": M("样例研究窗口", "fixture study window"),
    "conditions.fixture_limitation": M(
        "合成样例数据；结论不超出已发布记录。",
        "Synthetic fixture; no conclusion beyond the published record.",
    ),
    "conditions.locator_missing": M("未记录定位器", "not recorded"),
    # Comparison page copy.
    "comparison.eyebrow": M(
        "策略 / 基因组比较 · {term:read_only}", "Strategies / Genome comparison · read-only"
    ),
    "comparison.title": M("基因组比较", "Genome comparison"),
    "comparison.intro": M(
        "只显示明确的比较轴。相等、不同和不可比较仍是不同结果。",
        "Only explicit comparison axes are shown. Equal, different, and incomparable remain distinct outcomes.",
    ),
    "comparison.observed": M("截至时间", "Observed"),
    "comparison.snapshot": M("快照", "Snapshot"),
    "comparison.stable_context": M("稳定比较上下文", "Stable comparison context"),
    "comparison.related_aria": M("比较相关视图", "Comparison related views"),
    "comparison.left_genome": M("左侧基因组", "Left Genome"),
    "comparison.right_genome": M("右侧基因组", "Right Genome"),
    "comparison.left_genome_link": M("左侧基因组 {genome_id}", "Left Genome {genome_id}"),
    "comparison.right_genome_link": M("右侧基因组 {genome_id}", "Right Genome {genome_id}"),
    "comparison.left_condition": M("左侧条件证据", "Left condition evidence"),
    "comparison.result": M("结果：{result}", "Result: {result}"),
    "comparison.reason": M("原因", "Reason"),
    "comparison.no_comparison": M(
        "此范围中没有记录明确的基因组比较。", "No explicit Genome comparison is recorded in this scope."
    ),
    "comparison.no_comparison_explanation": M(
        "没有明确比较记录，不能声称相等或不同。",
        "Without an explicit comparison record, equality or difference cannot be claimed.",
    ),
    "comparison.axes_incompatible": M(
        "声明的比较轴不完整或不兼容。",
        "The declared comparison axes are not complete or compatible.",
    ),
    "comparison.fixture_incompatible_reason": M(
        "数据版本不兼容。", "The data versions are incompatible."
    ),
    "comparison.changed_paths": M("已变更路径", "Changed paths"),
    "comparison.missing_axes": M("缺失轴", "Missing axes"),
    "comparison.incompatible_axes": M("不兼容轴", "Incompatible axes"),
    "comparison.left_provenance": M("左侧溯源信息", "Left provenance"),
    "comparison.right_provenance": M("右侧溯源信息", "Right provenance"),
    "comparison.left_as_of": M("左侧截至时间", "Left as-of"),
    "comparison.right_as_of": M("右侧截至时间", "Right as-of"),
    "comparison.left_snapshot": M("左侧快照", "Left snapshot"),
    "comparison.right_snapshot": M("右侧快照", "Right snapshot"),
    "comparison.source_refs": M("来源引用", "Source refs"),
    "comparison.not_recorded": M("未记录", "not recorded"),
    # Closed enum labels.  Values remain in data-* attributes; only labels are translated.
    "label.genome_behavior.schema": M("模式", "Schema"),
    "label.genome_behavior.signals": M("信号", "Signals"),
    "label.genome_behavior.composition": M("组合方式", "Composition"),
    "label.genome_behavior.universe": M("股票池", "Universe"),
    "label.genome_behavior.portfolio": M("投资组合", "Portfolio"),
    "label.genome_behavior.sizing": M("仓位规模", "Sizing"),
    "label.genome_behavior.timing": M("时机", "Timing"),
    "label.genome_behavior.state": M("状态", "State"),
    "label.genome_behavior.risk_controls": M("风险控制", "Risk controls"),
    "label.genome_behavior.entry": M("入场", "Entry"),
    "label.genome_behavior.exit": M("出场", "Exit"),
    "label.genome_behavior.costs": M("成本", "Costs"),
    "label.genome_behavior.data_requirements": M("数据要求", "Data requirements"),
    "label.genome_behavior.required_capabilities": M("所需能力", "Required capabilities"),
    "label.genome_validation.validator": M("验证器", "Validator"),
    "label.genome_validation.test_suite": M("测试套件", "Test suite"),
    "label.genome_validation.dependencies": M("依赖", "Dependencies"),
    "label.genome_validation.environment": M("环境", "Environment"),
    "label.genome_validation.policy": M("政策", "Policy"),
    "label.genome_validation.result": M("结果", "Result"),
    "label.genome_identity.genome_id": M("基因组 ID", "Genome ID"),
    "label.genome_identity.schema": M("模式", "Schema"),
    "label.genome_identity.content_hash": M("内容哈希", "Content hash"),
    "label.genome_identity.candidate_revision": M("候选对象修订", "Candidate revision"),
    "label.genome_identity.provenance": M("溯源信息", "Provenance"),
    "label.genome_identity.explicit_state": M("明确状态", "Explicit state"),
    "label.lifecycle_event.proposed": M("已提出", "Proposed"),
    "label.lifecycle_event.validated": M("已验证", "Validated"),
    "label.lifecycle_event.published": M("已发布", "Published"),
    "label.lifecycle_event.revoked": M("已撤销", "Revoked"),
    "label.lifecycle_event.tombstoned": M("已设为墓碑", "Tombstoned"),
    "label.lineage_kind.candidate": M("候选对象", "Candidate"),
    "label.lineage_kind.hypothesis": M("研究假设", "Hypothesis"),
    "label.lineage_kind.family": M("策略族", "Family"),
    "label.lineage_kind.context": M("上下文", "Context"),
    "label.lineage_kind.package": M("软件包", "Package"),
    "label.lineage_kind.run": M("运行", "Run"),
    "label.lineage_kind.evidence": M("证据", "Evidence"),
    "label.value_state.missing": M("未记录", "Missing"),
    "label.value_state.empty": M("空值", "Empty"),
    "label.value_state.known": M("已记录", "Known"),
    "label.condition_category.applicability": M("适用条件", "Applicability"),
    "label.condition_category.invalidation": M("失效条件", "Invalidation"),
    "label.condition_category.descriptor": M("描述性观察", "Descriptor"),
    "label.condition_outcome.supported": M("受支持", "Supported"),
    "label.condition_outcome.failed": M("失败", "Failed"),
    "label.condition_outcome.not_evaluated": M("未评估", "Not evaluated"),
    "label.condition_outcome.blocked": M("已阻塞", "Blocked"),
    "label.condition_outcome.missing": M("未记录", "Missing"),
    "label.condition_outcome.stale": M("已过时", "Stale"),
    "label.condition_outcome.integrity_failure": M("完整性校验失败", "Integrity failure"),
    "label.condition_outcome.incomparable": M("不可比较", "Incomparable"),
    "label.evidence_level.none": M("无", "None"),
    "label.evidence_level.low": M("低", "Low"),
    "label.evidence_level.moderate": M("中", "Moderate"),
    "label.evidence_level.high": M("高", "High"),
    "label.evidence_level.not_recorded": M("未记录", "Not recorded"),
    "label.comparison_result.equal": M("相等", "Equal"),
    "label.comparison_result.different": M("不同", "Different"),
    "label.comparison_result.incomparable": M("不可比较", "Incomparable"),
    "label.comparison_axis.identity": M("身份", "Identity"),
    "label.comparison_axis.data_version": M("数据版本", "Data version"),
    "label.comparison_axis.universe": M("股票池", "Universe"),
    "label.comparison_axis.time_range": M("时间范围", "Time range"),
    "label.comparison_axis.protocol": M("研究协议", "Protocol"),
    "label.comparison_axis.randomness": M("随机性", "Randomness"),
    "label.comparison_axis.costs": M("成本", "Costs"),
    "label.comparison_axis.fills": M("成交", "Fills"),
    "label.comparison_axis.metric_definition": M("指标定义", "Metric definition"),
    "label.comparison_axis.evidence_sections": M("证据章节", "Evidence sections"),
    "label.comparison_axis.currency": M("货币", "Currency"),
    "label.comparison_axis.data_requirements.version": M("数据要求 · 版本", "Data requirements · version"),
}


# Page modules import this namespace and therefore register it through the existing API.
# The integration ticket may move this import to application bootstrap; do not call
# ``register(ENTRIES)`` a second time after doing so.
register(ENTRIES)

__all__ = ["ENTRIES"]
