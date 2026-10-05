"""L3 page copy for Atlas and Research Story.

The module owns only page-specific entries and registers them through the shared,
append-only catalog API when imported.  The central integration hook for a future
catalog initializer is::

    from . import l3_atlas_story

The import is intentionally not added to ``catalog/__init__.py`` by L3-T1; the
page modules import this namespace for standalone use, while the L3 integration
ticket can make the import explicit in the registry initializer.
"""

from __future__ import annotations

from collections.abc import Mapping

from ..translator import M
from . import register


ENTRIES: Mapping[str, M] = {
    # Atlas page chrome and context.
    "atlas.eyebrow": M("研究总览 · 只读", "Atlas overview · read-only"),
    "atlas.title": M("{term:atlas}", "{term:atlas}"),
    "atlas.intro": M(
        "从 {start} 到 {end} 导航研究生命周期。计数只描述已记录对象，不表示成功、排名或建议。",
        "Navigate the research lifecycle from {start} through {end}. Counts describe recorded objects only; they do not establish success, ranking, or advice.",
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
    "atlas.empty_scope": M("此研究总览范围中没有记录。", "No records are present in this Atlas scope."),
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
    "atlas.filters.date_placeholder": M("YYYY-MM-DD", "YYYY-MM-DD"),
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
    "label.atlas.state.active": M("活跃", "Active"),
    "label.atlas.state.open": M("开放", "Open"),
    "label.atlas.state.blocked": M("已阻塞", "Blocked"),
    "label.atlas.state.ready": M("就绪", "Ready"),
    "label.atlas.state.completed": M("已完成", "Completed"),
    "label.atlas.state.recorded": M("已记录", "Recorded"),
    "label.atlas.state.pending": M("待处理", "Pending"),
    "label.atlas.state.planned": M("已计划", "Planned"),
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
    "label.story.chapter.intent": M("意图 / 目的", "Intent / purpose"),
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
    "story.record_id": M("记录 ID：{record_id}", "Record ID: {record_id}"),
    "story.source_missing": M("未记录 / 未确认的来源", "Missing / Unconfirmed source"),
    "story.source_unconfirmed": M(
        "{source_id} — 未记录 / 未确认", "{source_id} — Missing / Unconfirmed"
    ),
    "story.temporal.both": M(
        "来源事件 {event_time}；系统获知时间 {known_at}。",
        "Source event {event_time}; known at {known_at}.",
    ),
    "story.temporal.event_only": M(
        "来源事件 {event_time}；系统获知时间不可用。",
        "Source event {event_time}; known-at time unavailable.",
    ),
    "story.temporal.known_only": M(
        "系统获知时间 {known_at}；来源事件时间不可用。",
        "Known at {known_at}; source event time unavailable.",
    ),
    "story.temporal.none": M(
        "来源事件时间和系统获知时间均不可用。",
        "Source event time and known-at time unavailable.",
    ),
    "story.chapter.empty": M("本章节未记录研究材料。", "No research material recorded for this chapter."),
    "story.evidence.empty": M(
        "未记录研究事实或证据入口。未记录 / 未确认。",
        "No research facts or evidence entries are recorded. Missing / Unconfirmed.",
    ),
    "story.evidence.caption": M("事实、证据状态和溯源信息", "Facts, evidence state, and provenance"),
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
    "story.link_kind.unknown": M("{kind}", "{kind}"),
}


register(ENTRIES)

__all__ = ["ENTRIES"]
