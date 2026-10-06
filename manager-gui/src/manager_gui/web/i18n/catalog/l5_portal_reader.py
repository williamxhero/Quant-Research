"""Bilingual catalogue for the read-only Portal Reader framing."""

from __future__ import annotations

from collections.abc import Mapping

from ..translator import M

# Reader sentences are fixed catalogue templates; owner and machine values stay opaque.
# ruff: noqa: E501

ENTRIES: Mapping[str, M] = {
    "reader.portal.eyebrow": M("门户阅读器 · 只读", "Portal Reader · read-only"),
    "reader.portal.title": M("报告门户阅读器", "Portal Reader"),
    "reader.portal.question": M(
        "来源发布记录、生成制品、渲染器、核验与重建状态分别记录了什么？",
        "What do the source publication, generated artifact, renderer, verification, and rebuild states each record?",
    ),
    "reader.portal.confirmed_intro": M(
        "这里只显示已批准报告来源接口中明确记录的发布与制品元数据。",
        "This page shows only publication and artifact metadata explicitly recorded by the approved report-source seam.",
    ),
    "reader.portal.unknown_intro": M(
        "缺失、部分可用、核验失败或接口不可用时，无法得出报告内容、研究有效性或重建结果结论。",
        "Missing, partial, failed verification, or unavailable metadata cannot establish a conclusion about report content, research validity, or a rebuild result.",
    ),
    "reader.portal.why_intro": M(
        "Reader 保留来源范围、读取可用性、截至时间、快照和固定派生规则；它不会把静态制品提升为规范研究状态。",
        "The Reader retains source scope, availability, as-of time, snapshot, and a fixed derivation rule; it never promotes a static artifact to canonical research state.",
    ),
    "reader.portal.read_only": M(
        "只读；不会运行、重建、重新核验、发布或打开私有存储。",
        "Read-only; this page never runs, rebuilds, revalidates, publishes, or opens private storage.",
    ),
    "reader.portal.boundary_heading": M("发布与研究状态边界", "Publication and research-state boundary"),
    "reader.portal.boundary": M(
        "来源发布记录、生成制品和渲染结果是不同对象；门户不是规范研究状态，核验证据与重建意图也不会被本页代替或触发。",
        "Source publication, generated artifact, and rendered result are distinct objects; the Portal is not canonical research state, and verification evidence and rebuild intent are neither replaced nor triggered here.",
    ),
    "reader.portal.scope": M("报告来源范围", "Report-source scope"),
    "reader.portal.as_of": M("截至", "As of"),
    "reader.portal.snapshot": M("快照", "Snapshot"),
    "reader.portal.availability": M("可用性", "Availability"),
    "reader.portal.derivation": M("派生规则", "Derivation rule"),
    "reader.portal.source_refs": M("来源引用", "Source references"),
    "reader.portal.publication_object": M("来源发布记录", "Source publication record"),
    "reader.portal.artifact_object": M("生成制品元数据", "Generated artifact metadata"),
    "reader.portal.rendered_object": M("渲染结果边界", "Rendered-result boundary"),
    "reader.portal.rendered_copy": M(
        "门户只展示已发布制品的元数据，不读取制品内容，也不从渲染结果推断属主事实。",
        "The Portal displays metadata for a published artifact only; it does not read artifact contents or infer owner facts from a rendered result.",
    ),
    "reader.portal.expert_heading": M("门户专业视图", "Portal Expert view"),
    "reader.portal.raw_heading": M("门户原始来源", "Portal raw source"),
    "reader.portal.open_source": M("打开来源元数据", "Open source metadata"),
    "reader.portal.open_artifact": M("打开制品元数据", "Open artifact metadata"),
    "reader.portal.missing": M("未记录 / 无法得出结论", "Not recorded / no conclusion can be drawn"),
    "reader.portal.sample_banner": M("样例数据，不代表真实研究结果：{fixture}", "Sample data; not a real research result: {fixture}"),
}

__all__ = ["ENTRIES"]
