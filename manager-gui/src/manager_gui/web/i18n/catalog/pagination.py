"""Shared pagination translations."""

from collections.abc import Mapping

from ..translator import M

ENTRIES: Mapping[str, M] = {
    "pagination.previous": M("上一页", "Previous"),
    "pagination.next": M("下一页", "Next"),
    "pagination.aria": M("只读模型分页", "Read-model pagination"),
    "pagination.summary": M(
        "第 {page} / {pages} 页 · 共 {n} 条索引",
        "Page {page} of {pages} · {n} indexed entries",
    ),
}
