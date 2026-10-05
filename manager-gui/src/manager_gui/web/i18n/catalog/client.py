"""Client-side live-region messages injected into the static shell script."""

from __future__ import annotations

from ..translator import M


ENTRIES: dict[str, M] = {
    "client.copy_success": M("已复制不透明引用", "Copied opaque reference"),
    "client.copy_unavailable": M("无法复制引用", "Copy unavailable"),
    "client.export_success": M("当前视图已导出到本地", "Current view exported locally"),
    "client.export_unavailable": M("无法导出", "Export unavailable"),
}

__all__ = ["ENTRIES"]
