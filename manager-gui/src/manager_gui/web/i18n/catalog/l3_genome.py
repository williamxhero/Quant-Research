"""L3-T2 catalogs for Genome, condition evidence, and comparison pages.

This additive namespace is imported by ``catalog/__init__.py`` and registered
there exactly once. Page modules may import it for catalog constants without
mutating the registry.
"""

from __future__ import annotations

from collections.abc import Mapping

from ..translator import M

ENTRIES: Mapping[str, M] = {
    # Genome page copy.
    "genome.eyebrow": M(
        "策略 / {term:strategy_genome} · {term:read_only}",
        "Strategies / Genomes · read-only",
    ),
    "genome.title": M("策略基因组", "Strategy Genomes"),
    "genome.intro": M(
        "检查已发布的策略基因组身份、行为投影、验证绑定、生命周期事件和谱系，不推断属主事实。",
        (
            "Inspect published Genome identity, behavior projection, validation binding, "
            "lifecycle events, and lineage without inferring owner facts."
        ),
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
    "genome.detail_prefix": M("基因组详情", "Genome detail"),
    "genome.back_catalog": M("返回目录", "Back to catalog"),
    "genome.detail_empty": M(
        "选择一个策略基因组查看详情；如果没有可用基因组，详情为{term:missing}。",
        "Select a Genome for detail; if no Genome is available, detail is Missing.",
    ),
    "genome.behavior_title": M("行为投影", "Behavior projection"),
    "genome.behavior_intro": M(
        "已发布读模型中的十四个行为字段都会显示；不会推断缺失字段。",
        (
            "All fourteen behavior fields are shown from the published read model; "
            "missing fields are not inferred."
        ),
    ),
    "genome.field": M("字段", "Field"),
    "genome.value": M("值", "Value"),
    "genome.validation_title": M("验证绑定", "Validation binding"),
    "genome.validation_intro": M(
        "验证是独立绑定，不会改变策略基因组的内容身份。",
        "Validation is a separate binding and does not change Genome content identity.",
    ),
    "genome.binding": M("绑定", "Binding"),
    "genome.behavior_table": M("行为投影字段表", "Behavior projection fields"),
    "genome.validation_table": M("验证绑定字段表", "Validation binding fields"),
    "genome.lifecycle_title": M("生命周期时间线", "Lifecycle timeline"),
    "genome.lifecycle_intro": M(
        "这里只显示明确记录的已提出、已验证、已发布、已撤销和已设为墓碑来源事件；不会推断状态。",
        (
            "Only explicit proposed, validated, published, revoked, and tombstoned source "
            "events are shown; no state is inferred."
        ),
    ),
    "genome.lifecycle_aria": M("基因组生命周期事件时间线", "Genome lifecycle event timeline"),
    "genome.no_events": M(
        "没有记录明确的生命周期事件。{term:missing}。",
        "No explicit lifecycle events are recorded. Missing.",
    ),
    "genome.event_timeline": M("事件时间线", "Event timeline"),
    "genome.lineage_title": M("谱系入口", "Lineage entry points"),
    "genome.lineage_intro": M(
        "这些{term:candidate}、{term:hypothesis}、{term:strategy_family}、上下文、软件包、{term:run}和{term:evidence}引用，都是有来源支持的入口。",
        (
            "These {term:candidate}, {term:hypothesis}, {term:strategy_family}, context, "
            "package, {term:run}, and {term:evidence} refs are source-backed entry points."
        ),
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
    # Strategy Reader copy; structure is separate from effectiveness and revision quality.
    "strategy_reader.title": M("策略阅读", "Strategy Reader"),
    "strategy_reader.structure_title": M("策略结构", "Strategy structure"),
    "strategy_reader.structure_intro": M(
        "按已发布的行为字段说明策略结构；未记录的字段保持缺失，不推断策略有效。",
        (
            "Describe strategy structure through published behavior fields; unrecorded "
            "fields remain missing and strategy effectiveness is not inferred."
        ),
    ),
    "strategy_reader.structure_sentence": M(
        "已记录的行为字段为：{text}。",
        "The recorded behavior fields are: {text}.",
        note=(
            "Typed template: text is a deterministic list of published behavior values, "
            "not an effectiveness claim."
        ),
    ),
    "strategy_reader.validity_title": M("验证与有效性", "Validation and validity"),
    "strategy_reader.validity_intro": M(
        "分别查看验证绑定、资格评定、当前可用性和生命周期；这些记录不自动证明策略有效。",
        (
            "Inspect validation binding, qualification, current usability, and lifecycle "
            "separately; these records do not automatically prove strategy effectiveness."
        ),
    ),
    "strategy_reader.effectiveness_unknown": M(
        "有效性信息未记录；无法判断策略是否有效。",
        "Effectiveness information is not recorded; strategy effectiveness cannot be determined.",
    ),
    "strategy_reader.effectiveness_boundary": M(
        "这里只展示已记录的验证和资格信息；记录、验证绑定或资格状态本身不构成策略有效的结论。",
        (
            "Only recorded validation and qualification information is shown; a record, "
            "validation binding, or qualification status alone is not a conclusion of "
            "strategy effectiveness."
        ),
    ),
    "strategy_reader.conditions_title": M("条件与反例", "Conditions and counterexamples"),
    "strategy_reader.conditions_intro": M(
        "按明确记录的类别区分适用条件、失效条件、反例和描述性观察；未分类或未评估的内容不补成条件结论。",
        (
            "Separate applicability conditions, invalidation conditions, counterexamples, "
            "and descriptive observations by their explicit recorded categories; "
            "unclassified or unevaluated items do not become condition conclusions."
        ),
    ),
    "strategy_reader.applicability": M("{term:applicable_condition}", "Applicability conditions"),
    "strategy_reader.invalidation": M("{term:invalidating_condition}", "Invalidation conditions"),
    "strategy_reader.counterexample": M("反例", "Counterexamples"),
    "strategy_reader.descriptor": M("{term:descriptive_observation}", "Descriptive observations"),
    "strategy_reader.unclassified": M("未分类", "Unclassified"),
    "strategy_reader.qualification": M("{term:qualification}", "{term:qualification}"),
    "strategy_reader.currency": M(
        "当前可用性", "Current usability", note="Currency means current usability, not money."
    ),
    "strategy_reader.lifecycle": M("{term:lifecycle}", "{term:lifecycle}"),
    "strategy_reader.revisions_title": M("策略修订演进", "Strategy revision evolution"),
    "strategy_reader.revisions_intro": M(
        "只展示明确记录的父子关系、变化、原因、证据、结果和限制；修订编号、新旧时间和变化数量不代表优劣排名。",
        (
            "Show only explicitly recorded parent/child relationships, changes, reasons, "
            "evidence, results, and limitations; revision numbers, recency, and change "
            "counts do not rank quality."
        ),
    ),
    "strategy_reader.revisions_aria": M(
        "策略修订演进关系", "Strategy revision evolution relationships"
    ),
    "strategy_reader.parent": M("父修订", "Parent revision"),
    "strategy_reader.children": M("子修订", "Child revisions"),
    "strategy_reader.changes": M("变化", "Changes"),
    "strategy_reader.reason": M("原因", "Reason"),
    "strategy_reader.reason_not_recorded": M(
        "原因未记录；不推测修订动机。",
        "The reason is not recorded; revision motivation is not inferred.",
    ),
    "strategy_reader.evidence": M("{term:evidence}", "{term:evidence}"),
    "strategy_reader.result": M("结果", "Result"),
    "strategy_reader.limitations": M("限制", "Limitations"),
    "strategy_reader.condition_refs": M("条件引用", "Condition references"),
    "strategy_reader.identity": M("身份", "Identity"),
    "strategy_reader.eligibility": M("比较资格", "Comparison eligibility"),
    "strategy_reader.genome_link": M("查看策略基因组", "View Strategy Genome"),
    "strategy_reader.conditions_link": M("查看条件与证据", "View conditions and evidence"),
    "strategy_reader.evidence_link": M("查看证据", "View evidence"),
    "strategy_reader.comparison_link": M("查看比较", "View comparison"),
    "strategy_reader.expert_link": M("查看专业模式", "View Expert mode"),
    "strategy_reader.raw_link": M("查看原始模式", "View Raw mode"),
    "strategy_reader.related_aria": M("策略阅读相关视图", "Strategy Reader related views"),
    "strategy_reader.not_recorded": M(
        "未记录；无法得出结论。", "Not recorded; no conclusion can be drawn."
    ),
    "strategy_reader.empty_value": M("空值", "Empty value"),
    "strategy_reader.record_boundary": M(
        "已记录只表示来源发布了这项内容，不表示已经核实或策略有效。",
        (
            "Recorded means only that the source published this item; it does not mean "
            "the item was verified or the strategy is effective."
        ),
    ),
    "strategy_reader.derived_boundary": M(
        "这是按已命名输入和固定规则生成的派生视图；它不新增属主事实，也不证明策略有效。",
        (
            "This is a derived view generated from named inputs and a fixed rule; "
            "it adds no owner facts and does not prove strategy effectiveness."
        ),
    ),
    "strategy_reader.owner_boundary": M(
        "属主原文保持原样；界面不会翻译、改写或将其提升为已验证结论。",
        (
            "Owner text is preserved as supplied; the interface does not translate, "
            "rewrite, or promote it to a verified conclusion."
        ),
    ),
    "strategy_reader.gap_boundary": M(
        "缺失、未评估、已阻塞、已过时和不可比较保持各自状态；知识缺口不表示成功或失败。",
        (
            "Missing, not evaluated, blocked, stale, and incomparable retain their "
            "distinct states; a knowledge gap means neither success nor failure."
        ),
    ),
    "strategy_reader.revision_graph_gap": M(
        "父修订缺失、重复或父子关系成环时，无法推断有效的修订链。",
        (
            "Missing or duplicate parent revisions, or cyclic parent/child relationships, "
            "prevent inference of a valid revision chain."
        ),
    ),
    "strategy_reader.comparison_boundary": M(
        "身份和比较资格必须明确记录且兼容；否则为不可比较，不能声称相等或不同。",
        (
            "Identity and comparison eligibility must be explicitly recorded and "
            "compatible; otherwise the revisions are incomparable and equality or "
            "difference cannot be claimed."
        ),
    ),
    "strategy_reader.comparison_axes": M("比较轴", "Comparison axes"),
    "strategy_reader.comparison_missing": M(
        "明确的比较记录或所需比较轴未记录；无法得出比较结论。",
        (
            "An explicit comparison record or required axes are not recorded; no comparison "
            "conclusion can be drawn."
        ),
    ),
    "strategy_reader.schema": M("模式", "Schema"),
    "strategy_reader.validation": M("{term:validation_binding}", "{term:validation_binding}"),
    "strategy_reader.owner_summary": M("属主摘要", "Owner summary"),
    "strategy_reader.interpretation": M("结构解读", "Structure interpretation"),
    "strategy_reader.scope": M("范围", "Scope"),
    "strategy_reader.outcome": M("结果", "Outcome"),
    "strategy_reader.evidence_level": M("{term:evidence_grade}", "Evidence level"),
    "strategy_reader.time_range": M("时间范围", "Time range"),
    "strategy_reader.data_version": M("数据版本", "Data version"),
    "strategy_reader.sample": M("样本", "Sample"),
    "strategy_reader.source": M("{term:source}", "{term:source}"),
    "strategy_reader.derivation": M("{term:derivation}", "{term:derivation}"),
    "strategy_reader.availability": M("读取可用性", "Read availability"),
    "strategy_reader.expert_details": M("专业详情", "Expert details"),
    "strategy_reader.catalog": M("策略基因组目录", "Strategy Genome catalog"),
    "strategy_reader.catalog_aria": M("策略阅读基因组目录", "Strategy Reader Genome catalog"),
    "strategy_reader.select_genome": M("选择策略基因组", "Select a Strategy Genome"),
    "strategy_reader.revisions_link": M("查看修订演进", "View revision evolution"),
    "strategy_reader.revision_link": M("查看修订", "View revision"),
    "strategy_reader.validation_result": M("验证结果", "Validation result"),
    "strategy_reader.current_state": M("当前状态", "Current state"),
    "strategy_reader.behavior_unknown": M(
        "行为字段未记录；无法描述该项策略结构。",
        (
            "The behavior field is not recorded; this part of the strategy structure "
            "cannot be described."
        ),
    ),
    "strategy_reader.structure_table": M("策略行为字段表", "Strategy behavior fields"),
    "strategy_reader.field": M("字段", "Field"),
    "strategy_reader.value": M("值", "Value"),
    "strategy_reader.root_revision": M("父修订未记录", "Parent revision not recorded"),
    # Conditions page copy.
    "conditions.eyebrow": M(
        "策略 / 条件 · {term:read_only}", "Strategies / Conditions · read-only"
    ),
    "conditions.title": M("策略基因组条件与证据", "Genome conditions and evidence"),
    "conditions.intro": M(
        "只有属主记录发布证据时，才显示适用条件和失效条件。制度或行为描述仍是观察。",
        (
            "Applicability and invalidation conditions are shown only when an owner record "
            "publishes evidence. Regime and behaviour descriptors remain observations."
        ),
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
        (
            "Only explicit comparison axes are shown. Equal, different, and incomparable "
            "remain distinct outcomes."
        ),
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
        "此范围中没有记录明确的基因组比较。",
        "No explicit Genome comparison is recorded in this scope.",
    ),
    "comparison.no_comparison_explanation": M(
        "没有明确比较记录，不能声称相等或不同。",
        "Without an explicit comparison record, equality or difference cannot be claimed.",
    ),
    "comparison.axes_incompatible": M(
        "声明的比较轴不完整或不兼容。",
        "The declared comparison axes are not complete or compatible.",
    ),
    "comparison.generated_axes_reason": M(
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
    "label.comparison_axis.data_requirements.version": M(
        "数据要求 · 版本", "Data requirements · version"
    ),
}


__all__ = ["ENTRIES"]
