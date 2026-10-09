"""Client-side live-region messages injected into the static shell script."""

from __future__ import annotations

from ..translator import M

ENTRIES: dict[str, M] = {
    "client.workspace_cancelled": M("已取消浏览器自动读取。", "Browser automatic reads cancelled."),
    "client.copy_success": M("已复制不透明引用", "Copied opaque reference"),
    "client.copy_unavailable": M("无法复制引用", "Copy unavailable"),
    "client.export_success": M("当前视图已导出到本地", "Current view exported locally"),
    "client.export_unavailable": M("无法导出", "Export unavailable"),
    "client.load_pending": M(
        "正在读取当前版本的内容…", "Loading content from the current read view…",
    ),
    "client.load_unavailable": M(
        "无法读取内容；尚未完成核对。可再次打开重试。",
        "Content could not be loaded; verification is incomplete. Open again to retry.",
    ),
}

__all__ = ["ENTRIES"]
