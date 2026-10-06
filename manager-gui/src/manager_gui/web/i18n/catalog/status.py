"""Status and operational-state messages for the shared Manager GUI surfaces."""

from __future__ import annotations

from ..translator import M

ENTRIES: dict[str, M] = {
    "label.status.known": M("{term:known}", "Known"),
    "label.status.derived": M("{term:derived}", "Derived"),
    "label.status.interpreted": M("{term:interpreted}", "Interpreted"),
    "label.status.missing": M("{term:missing}", "Missing"),
    "label.status.blocked": M("{term:blocked}", "Blocked"),
    "label.status.stale": M("{term:stale}", "Stale"),
    "label.status.incomparable": M("{term:incomparable}", "Incomparable"),
    "label.status.integrity_failure": M("{term:integrity_failure}", "Integrity failure"),
    "label.status.api_unavailable": M("{term:api_unavailable}", "API unavailable"),
    "label.display_state.ready": M("就绪", "Ready"),
    "label.display_state.loading": M("加载中", "Loading"),
    "label.display_state.empty": M("空结果", "Empty"),
    "label.display_state.partial": M("部分可用", "Partial"),
    "label.display_state.error": M("错误", "Error"),
    "status.explanation.known": M(
        "直接记录于属主记录或可核验制品。",
        "Directly present in an owner record or verifiable artifact.",
    ),
    "status.explanation.derived": M(
        "根据具名输入和具名规则可复现地计算。",
        "Reproducibly computed from named inputs and a named rule.",
    ),
    "status.explanation.interpreted": M(
        "由来源发布的解读，不是新的属主事实。",
        "An interpretation published by a source and not a new owner fact.",
    ),
    "status.explanation.missing": M(
        "预期值或关系未记录。",
        "The expected value or relationship is not recorded.",
    ),
    "status.explanation.blocked": M(
        "政策、权限、能力或数据关口阻止了判定。",
        "A policy, permission, capability, or data gate prevents a determination.",
    ),
    "status.explanation.stale": M(
        "该值曾可用，但其输入、包或政策已发生变化。",
        "The value was once usable but its inputs, package, or policy changed.",
    ),
    "status.explanation.incomparable": M(
        "请求的比较轴不兼容或不完整。",
        "The requested comparison axes are not compatible or complete.",
    ),
    "status.explanation.integrity_failure": M(
        "Schema、哈希、制品或信封核验失败。",
        "Schema, hash, artifact, or envelope validation failed.",
    ),
    "status.explanation.api_unavailable": M(
        "批准的公开读取接口不可用。",
        "The approved public read seam is unavailable.",
    ),
    "status.operational.ready": M(
        "读取模型已准备好供检查。",
        "The read-model is ready to inspect.",
    ),
    "status.operational.loading": M(
        "正在读取批准的公开来源……",
        "Reading the approved public source…",
    ),
    "status.operational.empty": M(
        "此范围中没有记录。",
        "No records are present in this scope.",
    ),
    "status.operational.partial": M(
        "部分预期记录尚不可用。",
        "Some expected records are not available yet.",
    ),
    "status.operational.error": M(
        "读取模型不能作为完整的当前事实使用。",
        "The read-model cannot be used as complete current truth.",
    ),
    "status.source_note": M("来源说明", "Source note"),
    "status.limitations": M("读取模型限制", "Read-model limitations"),
}

__all__ = ["ENTRIES"]
