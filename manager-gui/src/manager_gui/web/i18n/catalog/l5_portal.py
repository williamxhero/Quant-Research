"""Page-owned bilingual copy for the read-only Strategy Reporting Portal.

This namespace is intentionally additive.  The L5 integration hook (#684) may
register ``ENTRIES`` in the process-wide catalog later; until then the Portal
uses :func:`page_translator` so importing the page cannot mutate shared state.
"""

from __future__ import annotations

from collections.abc import Mapping

from ..translator import M, Translator, validate_entry

ENTRIES: Mapping[str, M] = {
    # Portal page chrome and the static-publication boundary.
    "l5.portal.eyebrow": M("报告门户 · 只读", "Strategy Reporting Portal · read-only"),
    "l5.portal.title": M("报告门户", "Strategy Reporting Portal"),
    "l5.portal.intro": M(
        "此静态报告门户索引将来源发布记录与生成制品、渲染器身份和核验元数据分开显示。",
        "This static report portal index separates a source publication from its generated "
        "artifact, renderer identity, and verification metadata.",
    ),
    "l5.portal.boundary": M(
        "只读发布内容不是规范研究状态。此视图不会触发重建或运行，也不会从制品推断属主事实。",
        "Read-only publication is not canonical research state. This view never triggers "
        "rebuild or run, and never infers owner facts from an artifact.",
    ),
    "l5.portal.boundary_heading": M("只读发布", "Read-only publication"),
    "l5.portal.report": M("报告", "Report"),
    "l5.portal.observed": M("截至时间", "Observed"),
    "l5.portal.snapshot": M("快照", "Snapshot"),
    "l5.portal.sources": M("来源", "Sources"),
    "l5.portal.portal_state": M("门户状态", "Portal state"),
    "l5.portal.report_index": M("报告索引", "Report index"),
    "l5.portal.untitled_report": M("未命名报告", "Untitled report"),
    "l5.portal.none_recorded": M("未记录", "None recorded"),
    "l5.portal.unavailable": M("不可用", "Unavailable"),
    "l5.portal.missing_unconfirmed": M("未记录 / 未确认", "Missing / Unconfirmed"),
    "l5.portal.open_source": M("打开来源元数据", "Open source metadata"),
    "l5.portal.open_artifact": M("打开制品元数据", "Open artifact metadata"),

    # Source publication and generated artifact remain separate sections.
    "l5.portal.source.heading": M("来源发布记录", "Source publication"),
    "l5.portal.source.missing": M(
        "未记录 / 未确认：没有已发布的报告来源记录。",
        "Missing / Unconfirmed: no published report source is recorded.",
    ),
    "l5.portal.source.publication_id": M("发布记录 ID", "Publication ID"),
    "l5.portal.source.title": M("标题", "Title"),
    "l5.portal.source.version": M("版本", "Version"),
    "l5.portal.source.revision": M("修订版本", "Revision"),
    "l5.portal.source.published_at": M("发布时间", "Published at"),
    "l5.portal.source.locator": M("来源定位器", "Source locator"),
    "l5.portal.source.stable_link": M("稳定链接", "Stable link"),
    "l5.portal.artifact.heading": M("生成制品", "Generated artifact"),
    "l5.portal.artifact.missing": M(
        "未记录 / 未确认：没有已记录的生成制品。",
        "Missing / Unconfirmed: no generated report artifact is recorded.",
    ),
    "l5.portal.artifact.not_generated": M(
        "尚未生成：来源发布记录存在，但没有发布静态制品。",
        "Not generated: the source publication exists, but no static artifact is published.",
    ),
    "l5.portal.artifact.api_unavailable": M(
        "API 不可用：无法通过批准的接口读取生成制品元数据。",
        "API unavailable: generated artifact metadata cannot be read from the approved seam.",
    ),
    "l5.portal.artifact.unavailable": M(
        "没有可用的生成制品元数据。", "No generated report artifact metadata is available."
    ),
    "l5.portal.artifact.id": M("制品 ID", "Artifact ID"),
    "l5.portal.artifact.title": M("标题", "Title"),
    "l5.portal.artifact.locator": M("制品定位器", "Artifact locator"),
    "l5.portal.artifact.renderer": M("渲染器", "Renderer"),
    "l5.portal.artifact.renderer_version": M("渲染器版本", "Renderer version"),
    "l5.portal.artifact.generated_at": M("生成时间", "Generated at"),
    "l5.portal.artifact.verify_status": M("核验状态", "Verify status"),
    "l5.portal.artifact.rebuild_status": M("重建状态", "Rebuild status"),
    "l5.portal.artifact.digest": M("摘要哈希", "Digest"),
    "l5.portal.artifact.stable_link": M("稳定链接", "Stable link"),

    # Program-generated state explanations, not owner-provided reasons.
    "l5.portal.state.ready": M(
        "已发布的来源和生成静态制品元数据均可用。",
        "Published source and generated static artifact metadata are available.",
    ),
    "l5.portal.state.missing": M(
        "未记录来源发布记录或生成制品。",
        "No source publication or generated artifact is recorded.",
    ),
    "l5.portal.state.not_generated": M(
        "来源发布记录可用，但尚未生成静态制品。",
        "The source publication is available, but the static artifact has not been generated.",
    ),
    "l5.portal.state.integrity_failure": M(
        "生成制品未通过其声明的完整性核验。",
        "The generated artifact failed its declared integrity verification.",
    ),
    "l5.portal.state.api_unavailable": M(
        "批准的公开报告来源接口不可用。",
        "The approved public report-source seam is unavailable.",
    ),
    "l5.portal.state.partial": M(
        "部分门户元数据可用，但发布内容不完整。",
        "Some Portal metadata is available, but the publication is incomplete.",
    ),

    # Closed state vocabularies are namespaced to this page.
    "label.l5_portal_state.ready": M("就绪", "Ready"),
    "label.l5_portal_state.missing": M("未记录", "Missing"),
    "label.l5_portal_state.not-generated": M("尚未生成", "Not generated"),
    "label.l5_portal_state.partial": M("部分可用", "Partial"),
    "label.l5_portal_state.integrity-failure": M("完整性校验失败", "Integrity failure"),
    "label.l5_portal_state.api-unavailable": M("API 不可用", "API unavailable"),
    "label.l5_portal_verify.verified": M("已核验", "Verified"),
    "label.l5_portal_verify.failed": M("失败", "Failed"),
    "label.l5_portal_verify.not_verified": M("未核验", "Not verified"),
    "label.l5_portal_verify.unknown": M("未知", "Unknown"),
    "label.l5_portal_rebuild.not_requested": M("未请求", "Not requested"),
    "label.l5_portal_rebuild.not_generated": M("尚未生成", "Not generated"),
    "label.l5_portal_rebuild.pending": M("处理中", "Pending"),
    "label.l5_portal_rebuild.succeeded": M("已成功", "Succeeded"),
    "label.l5_portal_rebuild.failed": M("失败", "Failed"),
    "label.l5_portal_rebuild.unknown": M("未知", "Unknown"),
    "l5.portal.status.read_model": M("读取状态", "Read status"),

    # Exact prose emitted by the deterministic Portal fixtures. Owner payloads
    # never use these entries unless the complete fixture identity is proven.
    "l5.portal.fixture.source_title": M(
        "样例策略报告来源发布记录", "Fixture Strategy Reporting source publication"
    ),
    "l5.portal.fixture.artifact_title": M("样例静态策略报告", "Fixture static Strategy Report"),
    "l5.portal.fixture.missing_reason": M(
        "请求范围中未记录策略报告来源。",
        "No Strategy Reporting report source is recorded in the requested scope.",
    ),
    "l5.portal.fixture.api_reason": M(
        "此环境中批准的公开报告来源 API 不可用。",
        "The approved public report-source API is unavailable in this environment.",
    ),
    "l5.portal.fixture.api_error": M(
        "Portal 元数据不允许回退到私有 SQLite 或文件系统。",
        "No private SQLite or filesystem fallback is permitted for Portal metadata.",
    ),
    "l5.portal.fixture.integrity_reason": M(
        "生成制品未通过其声明的完整性核验。",
        "The generated artifact failed its declared integrity verification.",
    ),
    "l5.portal.fixture.integrity_error": M(
        "已发布制品摘要哈希与声明值不匹配。",
        "The published artifact digest does not match the declared digest.",
    ),
    "l5.portal.fixture.not_generated_reason": M(
        "来源发布记录可用，但没有发布生成制品。",
        "The source publication is available, but no generated artifact is published.",
    ),
    "l5.portal.fixture.not_generated_error": M(
        "静态制品尚未生成；没有触发重建。",
        "The static artifact has not been generated; no rebuild was triggered.",
    ),
    "l5.portal.fixture.partial_reason": M(
        "来源发布记录和制品均存在，但渲染器核验元数据不完整。",
        "The publication and artifact are present, but renderer verification metadata "
        "is incomplete.",
    ),
    "l5.portal.fixture.partial_error": M(
        "未记录渲染器版本和核验状态。",
        "Renderer version and verification status are not recorded.",
    ),
    "l5.portal.fixture.complete_reason": M(
        "样例包含来源发布记录和生成制品元数据。",
        "The fixture contains source publication and generated artifact metadata.",
    ),
}


def page_translator(translator: Translator | None = None) -> Translator:
    """Return a translator extended with the additive Portal namespace."""

    from .. import REGISTRY, CatalogError

    base = translator or Translator()
    catalog = dict(REGISTRY.entries)
    for key, entry in ENTRIES.items():
        registered = catalog.get(key)
        if registered is not None:
            if registered != entry:
                raise CatalogError(f"conflicting L5 Portal catalog entry: {key!r}")
            continue
        validate_entry(key, entry)
        catalog[key] = entry
    return Translator(base.locale, strict=base.strict, pseudo=base.pseudo, catalog=catalog)


__all__ = ["ENTRIES", "page_translator"]
