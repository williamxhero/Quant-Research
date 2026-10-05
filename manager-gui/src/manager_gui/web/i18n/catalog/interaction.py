"""Shared interaction-control labels for the Manager GUI."""

from __future__ import annotations

from ..translator import M


ENTRIES: dict[str, M] = {
    "interaction.copy_reference": M("复制引用", "Copy reference"),
    "interaction.export_current_view": M("导出当前视图", "Export current view"),
    "interaction.export_note": M(
        "仅生成本地 JSON，不写入证据账本或属主记录。",
        "Local JSON only; no ledger or owner record is written.",
    ),
    "interaction.alternative_view": M("替代视图", "Alternative view"),
    "interaction.lineage_view": M("谱系视图", "Lineage view"),
    "label.view_mode.graph": M("图谱", "Graph"),
    "label.view_mode.table": M("表格", "Table"),
}

__all__ = ["ENTRIES"]
