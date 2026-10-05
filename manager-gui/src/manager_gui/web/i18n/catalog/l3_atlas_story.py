"""L3 page copy for Atlas and Research Story.

The module owns only page-specific entries and registers them through the shared,
append-only catalog API when imported.  The central integration hook for a future
catalog initializer is::

    from . import l3_atlas_story

The catalog initializer imports this namespace and registers ``ENTRIES`` once;
page modules may import it for fixture keys without registering a second time.
"""

from __future__ import annotations

from collections.abc import Mapping

from ..translator import M

ENTRIES: Mapping[str, M] = {
    # Atlas page chrome and context.
    "atlas.eyebrow": M("研究总览 · 只读", "Atlas overview · read-only"),
    "atlas.title": M("{term:atlas}", "{term:atlas}"),
    "atlas.intro": M(
        "从 {start} 到 {end} 导航研究生命周期。计数只描述已记录对象，不表示成功、排名或建议。",
        "Navigate the research lifecycle from {start} through {end}. "
        "Counts describe recorded objects only; they do not establish success, ranking, or advice.",
    ),
    "atlas.observed": M("截至时间", "Observed"),
    "atlas.snapshot": M("快照", "Snapshot"),
    "atlas.sources": M("来源", "Sources"),
    "atlas.none_recorded": M("未记录", "None recorded"),
    "atlas.unavailable": M("不可用", "Unavailable"),
    "atlas.lifecycle.title": M("研究生命周期", "Research lifecycle"),
    "atlas.lifecycle.other": M("其他记录类型", "Other record types"),
    "atlas.lifecycle.empty": M("此生命周期范围中没有记录。", "No records in this lifecycle scope."),
    "atlas.count.records": M("{n} 条记录", {"one": "{n} record", "other": "{n} records"}),
    "atlas.section.status_groups": M("状态分组", "Status groups"),
    "atlas.section.recently_changed": M("最近变更", "Recently changed"),
    "atlas.section.blocked_or_unavailable": M("已阻塞或不可用", "Blocked or unavailable"),
    "atlas.section.unresolved_conclusions": M("未解决结论", "Unresolved conclusions"),
    "atlas.section.research_gaps": M("研究缺口", "Research gaps"),
    "atlas.section.frontier": M("可导航前沿", "Navigable frontier"),
    "atlas.record.open_story": M("打开研究故事", "Open Research Story"),
    "atlas.filters.aria": M("研究总览筛选器", "Atlas filters"),
    "atlas.filters.record_type": M("记录类型", "Record type"),
    "atlas.filters.state": M("状态", "State"),
    "atlas.filters.date": M("日期", "Date"),
    "atlas.filters.source": M("来源", "Source"),
    "atlas.filters.availability": M("可用性", "Availability"),
    "atlas.filters.date_placeholder": M("年-月-日", "YYYY-MM-DD"),
    "atlas.filters.all": M("全部", "All"),
    "atlas.filters.apply": M("应用筛选", "Apply filters"),
    "atlas.filters.clear": M("清除", "Clear"),
    # Atlas's closed lifecycle and fixture state vocabularies.
    "label.atlas.lifecycle.campaign": M("{term:campaign}", "{term:campaign}"),
    "label.atlas.lifecycle.hypothesis": M("{term:hypothesis}", "{term:hypothesis}"),
    "label.atlas.lifecycle.candidate": M("{term:candidate}", "{term:candidate}"),
    "label.atlas.lifecycle.run": M("{term:run}", "{term:run}"),
    "label.atlas.lifecycle.evidence": M("{term:evidence}", "{term:evidence}"),
    "label.atlas.lifecycle.qualification": M("{term:qualification}", "{term:qualification}"),
    "label.atlas.lifecycle.replication": M("{term:replication}", "{term:replication}"),
    "label.atlas.lifecycle.revalidation": M("{term:revalidation}", "{term:revalidation}"),
    "label.atlas.lifecycle.study": M("研究", "Study"),
    "label.atlas.lifecycle.strategy_family": M("{term:strategy_family}", "{term:strategy_family}"),
    "label.atlas.state.active": M("活跃", "Active"),
    "label.atlas.state.open": M("开放", "Open"),
    "label.atlas.state.blocked": M("已阻塞", "Blocked"),
    "label.atlas.state.ready": M("就绪", "Ready"),
    "label.atlas.state.completed": M("已完成", "Completed"),
    "label.atlas.state.recorded": M("已记录", "Recorded"),
    "label.atlas.state.pending": M("待处理", "Pending"),
    "label.atlas.state.planned": M("已计划", "Planned"),
    "label.atlas.state.unresolved": M("未解决", "Unresolved"),
    "label.atlas.state.unknown": M("未知", "Unknown"),
    "label.atlas.state.missing": M("未记录", "Missing"),
    "label.atlas.state.unavailable": M("不可用", "Unavailable"),
    "label.atlas.state.api_unavailable": M("API 不可用", "API unavailable"),
    # Research Story chrome, modes, chapters and closed vocabularies.
    "story.eyebrow": M("研究故事", "Research Story"),
    "story.title": M("研究故事", "Research Story"),
    "story.root_unavailable": M("研究故事（根对象不可用）", "Research Story (root unavailable)"),
    "story.mode.aria": M("研究故事阅读模式", "Research Story reading mode"),
    "label.story.mode.narrative": M("叙事", "Narrative"),
    "label.story.mode.evidence": M("证据", "Evidence"),
    "label.story.mode.timeline": M("时间线", "Timeline"),
    "label.story.outcome.success": M("成功", "Success"),
    "label.story.outcome.failure": M("失败", "Failure"),
    "label.story.outcome.blocked": M("已阻塞", "Blocked"),
    "label.story.outcome.not_evaluated": M("未评估", "Not evaluated"),
    "label.story.outcome.incomparable": M("不可比较", "Incomparable"),
    "label.story.evidence_state.known": M("已记录", "Known"),
    "label.story.evidence_state.derived": M("已派生", "Derived"),
    "label.story.evidence_state.interpreted": M("已解读", "Interpreted"),
    "label.story.evidence_state.missing": M("未记录", "Missing"),
    "label.story.evidence_state.unconfirmed": M("未确认", "Unconfirmed"),
    "label.story.evidence_state.blocked": M("已阻塞", "Blocked"),
    "label.story.evidence_state.stale": M("已过时", "Stale"),
    "label.story.evidence_state.incomparable": M("不可比较", "Incomparable"),
    "label.story.chapter.intent": M("意图与目的", "Intent / purpose"),
    "label.story.chapter.events": M("时间线事件", "Timeline event"),
    "label.story.chapter.initial_hypothesis": M("初始研究假设", "Initial hypothesis"),
    "label.story.chapter.research_design": M("研究设计", "Research design"),
    "label.story.chapter.attempts": M("尝试 / 运行", "Attempts / runs"),
    "label.story.chapter.evidence": M("证据入口", "Evidence entry points"),
    "label.story.chapter.conclusions": M("结论 / 决策", "Conclusions / decisions"),
    "label.story.chapter.failures": M("失败 / 局限", "Failures / limitations"),
    "label.story.chapter.follow_up": M("后续 / 演进", "Follow-up / evolution"),
    "label.story.root.campaign": M("研究活动", "Campaign"),
    "label.story.root.study": M("研究", "Study"),
    "label.story.root.strategy_family": M("策略族", "Strategy family"),
    "label.story.link_kind.artifact": M("制品", "Artifact"),
    "label.story.link_kind.lineage": M("谱系", "Lineage"),
    "label.story.link_kind.record": M("记录", "Record"),
    "label.story.link_kind.report": M("报告", "Report"),
    "label.story.link_kind.source": M("来源", "Source"),
    "story.missing": M("未记录 / 未确认", "Missing / Unconfirmed"),
    "story.record_id": M(
        "记录 ID：<span translate=\"no\">{record_id}</span>",
        "Record ID: <span translate=\"no\">{record_id}</span>",
    ),
    "story.source_missing": M("未记录或未确认的来源", "Missing / Unconfirmed source"),
    "story.source_reference": M(
        "来源引用 <span translate=\"no\">{source_id}</span>",
        "Source <span translate=\"no\">{source_id}</span>",
    ),
    "story.link.missing": M("未记录或未确认", "Missing / Unconfirmed"),
    "story.record_id.label": M("记录 ID", "Record ID"),
    "story.temporal.both": M(
        "来源事件 <time translate=\"no\">{event_time}</time>；"
        "系统获知时间 <time translate=\"no\">{known_at}</time>。",
        "Source event <time translate=\"no\">{event_time}</time>; "
        "known at <time translate=\"no\">{known_at}</time>.",
    ),
    "story.temporal.event_only": M(
        "来源事件 <time translate=\"no\">{event_time}</time>；系统获知时间不可用。",
        "Source event <time translate=\"no\">{event_time}</time>; known-at time unavailable.",
    ),
    "story.temporal.known_only": M(
        "系统获知时间 <time translate=\"no\">{known_at}</time>；来源事件时间不可用。",
        "Known at <time translate=\"no\">{known_at}</time>; source event time unavailable.",
    ),
    "story.temporal.none": M(
        "来源事件时间和系统获知时间均不可用。",
        "Source event time and known-at time unavailable.",
    ),
    "story.chapter.empty": M(
        "本章节未记录研究材料。", "No research material recorded for this chapter."
    ),
    "story.evidence.empty": M(
        "未记录研究事实或证据入口。未记录 / 未确认。",
        "No research facts or evidence entries are recorded. Missing / Unconfirmed.",
    ),
    "story.evidence.caption": M(
        "事实、证据状态和溯源信息", "Facts, evidence state, and provenance"
    ),
    "story.evidence.chapter_fact": M("章节 / 事实", "Chapter / fact"),
    "story.evidence.state": M("证据状态", "Evidence state"),
    "story.evidence.record_id": M("记录 ID", "Record ID"),
    "story.evidence.source_refs": M("来源引用", "Source refs"),
    "story.evidence.event_time": M("来源事件时间", "Source event time"),
    "story.evidence.known_at": M("系统获知时间", "Known to system at"),
    "story.evidence.links": M("链接", "Links"),
    "story.timeline.empty": M(
        "未记录来源事件时间；未推断阶段转换。",
        "No source event times recorded; no phase transitions inferred.",
    ),
    "story.timeline.note": M(
        "只显示明确的来源事件时间；不推断 GUI 阶段转换。",
        "Only explicit source event times are shown; GUI phase transitions are not inferred.",
    ),
    "story.timeline.aria": M("来源事件时间线", "Source event timeline"),
    "story.timeline.default_category": M("来源事件", "Source event"),
    "story.entry.title_missing": M("已记录项目", "Recorded item"),
    "story.entry.summary_missing": M("未记录叙述文本。", "No narrative text recorded."),
    "story.link_kind.unknown": M("{kind}", "{kind}"),
}


# Display copies of the shipped synthetic envelopes only. Page code verifies the
# entire envelope before using this map; matching one owner phrase is insufficient.
FIXTURE_TEXT: dict[str, M] = {
    "Fixture campaign": M("样例研究活动", "Fixture campaign"),
    "Fixture hypothesis": M("样例研究假设", "Fixture hypothesis"),
    "Fixture candidate": M("样例候选对象", "Fixture candidate"),
    "Fixture run": M("样例运行", "Fixture run"),
    "Fixture study": M("样例研究", "Fixture study"),
    "Fixture strategy family": M("样例策略族", "Fixture strategy family"),
    "Why test the fixture strategy?": M("为何测试样例策略？", "Why test the fixture strategy?"),
    "Validate the complete fixture-backed research path.": M(
        "验证完整的样例数据研究路径。", "Validate the complete fixture-backed research path."
    ),
    "The fixture path is traceable end to end.": M(
        "样例路径可以端到端追溯。", "The fixture path is traceable end to end."
    ),
    "Frozen fixture design": M("冻结的样例设计", "Frozen fixture design"),
    "Use only the declared public read seam.": M(
        "仅使用声明的公开读取接口。", "Use only the declared public read seam."
    ),
    "The fixture run completed with explicit provenance.": M(
        "样例运行已完成，并具有明确的溯源信息。",
        "The fixture run completed with explicit provenance.",
    ),
    "Fixture evidence": M("样例证据", "Fixture evidence"),
    "The source reference is available for inspection.": M(
        "来源引用可供检查。", "The source reference is available for inspection."
    ),
    "Fixture decision": M("样例决策", "Fixture decision"),
    "Keep the read-only path as the integration contract.": M(
        "将只读路径保留为集成契约。", "Keep the read-only path as the integration contract."
    ),
    "Partial fixture story": M("部分可用的样例研究故事", "Partial fixture story"),
    "The campaign is available, but other story chapters are not in scope.": M(
        "研究活动可用，但其他故事章节不在范围内。",
        "The campaign is available, but other story chapters are not in scope.",
    ),
    "Historical fixture result": M("历史样例结果", "Historical fixture result"),
    "The complete fixture contains the declared lifecycle records.": M(
        "完整样例包含声明的生命周期记录。",
        "The complete fixture contains the declared lifecycle records.",
    ),
    "The complete fixture contains the declared integration path.": M(
        "完整样例包含声明的集成路径。",
        "The complete fixture contains the declared integration path.",
    ),
    "No records are present in the requested fixture scope.": M(
        "请求的样例范围中没有记录。", "No records are present in the requested fixture scope."
    ),
    "Campaign records are available; other record types are not in scope.": M(
        "研究活动记录可用；其他记录类型不在范围内。",
        "Campaign records are available; other record types are not in scope.",
    ),
    "The fixture intentionally omits some expected record types.": M(
        "样例有意省略了部分预期记录类型。",
        "The fixture intentionally omits some expected record types.",
    ),
    "The approved read seam is blocked by a policy or capability gate.": M(
        "批准的读取接口已被政策或能力关口阻塞。",
        "The approved read seam is blocked by a policy or capability gate.",
    ),
    "The fixture does not permit access to this resource.": M(
        "样例不允许访问此资源。", "The fixture does not permit access to this resource."
    ),
    "The source predates the current package or policy identity.": M(
        "来源早于当前包或政策身份。", "The source predates the current package or policy identity."
    ),
    "The fixture is retained for historical viewing, not current truth.": M(
        "样例仅保留用于历史查看，不作为当前事实。",
        "The fixture is retained for historical viewing, not current truth.",
    ),
    "The comparison axes do not share a compatible data snapshot.": M(
        "比较维度不具有兼容的数据快照。",
        "The comparison axes do not share a compatible data snapshot.",
    ),
    "A result must not be ranked across incompatible snapshots.": M(
        "不得在不兼容快照之间对结果排名。",
        "A result must not be ranked across incompatible snapshots.",
    ),
    "The fixture artifact failed its declared integrity check.": M(
        "样例制品未通过声明的完整性校验。",
        "The fixture artifact failed its declared integrity check.",
    ),
    "The source digest does not match the declared digest.": M(
        "来源摘要哈希与声明的摘要哈希不匹配。",
        "The source digest does not match the declared digest.",
    ),
    "The approved public read API is not available in this environment.": M(
        "此环境中批准的公开读取 API 不可用。",
        "The approved public read API is not available in this environment.",
    ),
    "No private-storage fallback is permitted for this read.": M(
        "此读取不允许回退到私有存储。", "No private-storage fallback is permitted for this read."
    ),
    "The requested resource has not been evaluated in this scope.": M(
        "请求的资源在此范围内尚未评估。",
        "The requested resource has not been evaluated in this scope.",
    ),
    "No evaluation result is published for this resource.": M(
        "此资源尚未发布评估结果。", "No evaluation result is published for this resource."
    ),
    "The requested lineage cursor expired.": M(
        "请求的谱系游标已失效。", "The requested lineage cursor expired."
    ),
    "The requested lineage snapshot drifted.": M(
        "请求的谱系快照发生漂移。", "The requested lineage snapshot drifted."
    ),
}
FIXTURE_KEYS = {text: f"atlas_story.fixture.{index}" for index, text in enumerate(FIXTURE_TEXT)}
ENTRIES = {**ENTRIES, **{FIXTURE_KEYS[text]: message for text, message in FIXTURE_TEXT.items()}}
__all__ = ["ENTRIES", "FIXTURE_KEYS"]
