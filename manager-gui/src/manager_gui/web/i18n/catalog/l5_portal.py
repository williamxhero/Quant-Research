"""Additive catalog for the read-only Strategy Reporting Portal."""

from __future__ import annotations

from collections.abc import Mapping

from ..translator import M

_ARTIFACT_STATES = {
    "ready": M("就绪", "Ready"),
    "missing": M("未记录", "Missing"),
    "not_generated": M("未生成", "Not generated"),
    "partial": M("部分可用", "Partial"),
    "integrity_failure": M("完整性核验失败", "Integrity verification failed"),
    "api_unavailable": M("API 不可用", "API unavailable"),
}

_VERIFY_STATUSES = {
    "verified": M("已核验", "Verified"),
    "failed": M("失败", "Failed"),
    "not_verified": M("未核验", "Not verified"),
    "unknown": M("未知", "Unknown"),
}

_REBUILD_STATUSES = {
    "not_requested": M("未请求", "Not requested"),
    "not_generated": M("未生成", "Not generated"),
    "pending": M("待处理", "Pending"),
    "succeeded": M("已完成", "Succeeded"),
    "failed": M("失败", "Failed"),
    "unknown": M("未知", "Unknown"),
}

ENTRIES: Mapping[str, M] = {
    "l5.portal.eyebrow": M("报告门户 · 只读", "Report Portal · read-only"),
    "l5.portal.title": M("策略报告门户", "Strategy Reporting Portal"),
    "l5.portal.intro": M(
        "此静态门户分别显示来源发布记录、生成制品、渲染器身份和核验元数据。",
        "This static Portal separates source publication records, generated artifacts, "
        "renderer identity, and verification metadata.",
    ),
    "l5.portal.boundary_heading": M("只读发布信息", "Read-only publication"),
    "l5.portal.boundary": M(
        "不是规范研究状态。此视图不会触发重建或运行，也不会从制品推断属主事实。",
        "is not canonical research state. This view never triggers rebuilds or runs, "
        "or infers owner facts from an artifact.",
    ),
    "l5.portal.report": M("报告", "Report"),
    "l5.portal.observed": M("观察时间", "Observed"),
    "l5.portal.snapshot": M("快照", "Snapshot"),
    "l5.portal.sources": M("来源", "Sources"),
    "l5.portal.unavailable": M("不可用", "Unavailable"),
    "l5.portal.none_recorded": M("未记录", "None recorded"),
    "l5.portal.state": M("门户状态", "Portal state"),
    "l5.portal.state_missing": M(
        "未记录策略报告来源发布记录或生成制品。",
        "No Strategy Reporting source publication or generated artifact is recorded.",
    ),
    "l5.portal.state_not_generated": M(
        "来源发布记录可用，但尚未生成静态制品。",
        "The source publication is available, but the static artifact has not been generated.",
    ),
    "l5.portal.state_integrity_failure": M(
        "生成制品未通过其声明的完整性核验。",
        "The generated artifact failed its declared integrity verification.",
    ),
    "l5.portal.state_api_unavailable": M(
        "已批准的公开报告来源接口不可用。",
        "The approved public report-source seam is unavailable.",
    ),
    "l5.portal.state_partial": M(
        "部分门户元数据可用，但发布信息不完整。",
        "Some Portal metadata is available, but the publication is incomplete.",
    ),
    "l5.portal.state_ready": M(
        "已提供来源发布记录和生成静态制品的元数据。",
        "Published source and generated static artifact metadata are available.",
    ),
    "l5.portal.source_publication": M("来源发布记录", "Source publication"),
    "l5.portal.publication_id": M("发布记录 ID", "Publication ID"),
    "l5.portal.title_field": M("标题", "Title"),
    "l5.portal.version": M("版本", "Version"),
    "l5.portal.revision": M("修订", "Revision"),
    "l5.portal.published_at": M("发布时间", "Published at"),
    "l5.portal.source_locator": M("来源定位符", "Source locator"),
    "l5.portal.stable_link": M("稳定链接", "Stable link"),
    "l5.portal.open_source": M("打开来源元数据", "Open source metadata"),
    "l5.portal.generated_artifact": M("生成制品", "Generated artifact"),
    "l5.portal.artifact_id": M("制品 ID", "Artifact ID"),
    "l5.portal.artifact_locator": M("制品定位符", "Artifact locator"),
    "l5.portal.renderer": M("渲染器", "Renderer"),
    "l5.portal.renderer_version": M("渲染器版本", "Renderer version"),
    "l5.portal.generated_at": M("生成时间", "Generated at"),
    "l5.portal.verify_status": M("核验状态", "Verification status"),
    "l5.portal.rebuild_status": M("重建状态", "Rebuild status"),
    "l5.portal.digest": M("摘要哈希", "Digest"),
    "l5.portal.open_artifact": M("打开制品元数据", "Open artifact metadata"),
    "l5.portal.missing_unconfirmed": M("未记录 / 未确认", "Missing / Unconfirmed"),
    "l5.portal.missing_source": M(
        "未记录 / 未确认：没有记录已发布的报告来源。",
        "Missing / Unconfirmed: no published report source is recorded.",
    ),
    "l5.portal.missing_artifact": M(
        "未记录 / 未确认：没有记录生成的报告制品。",
        "Missing / Unconfirmed: no generated report artifact is recorded.",
    ),
    "l5.portal.not_generated_copy": M(
        "尚未生成：来源发布记录已存在，但没有已发布的静态制品。",
        "Not generated: the source publication exists, but no static artifact is published.",
    ),
    "l5.portal.api_artifact_unavailable": M(
        "API 不可用：无法通过已批准的接口读取生成制品元数据。",
        "API unavailable: generated artifact metadata cannot be read from the approved seam.",
    ),
    "l5.portal.no_artifact_metadata": M(
        "没有可用的生成制品元数据。", "No generated report artifact metadata is available."
    ),
    "l5.portal.report_index": M("报告索引", "Report index"),
    "l5.portal.untitled_report": M("未命名报告", "Untitled report"),
    **{f"label.l5_portal_artifact_state.{key}": value for key, value in _ARTIFACT_STATES.items()},
    **{f"label.l5_portal_verify_status.{key}": value for key, value in _VERIFY_STATUSES.items()},
    **{f"label.l5_portal_rebuild_status.{key}": value for key, value in _REBUILD_STATUSES.items()},
}

__all__ = ["ENTRIES"]
