"""Shared S6-T3 interaction primitives for read-only Manager GUI pages.

The module contains browser-facing helpers only. It never writes a file, ledger,
owner record, or snapshot. Export embeds the already-read envelope and current
URL context in the document; the browser creates a local JSON download with a
Blob, without a request, second provider read, or export endpoint.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from html import escape
from urllib.parse import urlencode

from ..models import ManagerReadModel
from .navigation import query_values

EXPORT_SCHEMA = "manager-gui.current-view-export.v0"
EXPORT_ENDPOINT = "/api/export"

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def opaque_copy_button(
    value: str | None,
    *,
    label: str = "Copy reference",
    label_zh: str = "复制引用",
    css_class: str = "copy-reference",
) -> str:
    """Render a copy affordance for an opaque, non-dereferenced reference."""

    if not value:
        return ""
    safe_value = escape(value, quote=True)
    return (
        f'<button class="{escape(css_class, quote=True)}" type="button" '
        f'data-copy-value="{safe_value}" aria-label="{escape(label)} / '
        f'{escape(label_zh)}">{escape(label)} / <span lang="zh-CN">'
        f"{escape(label_zh)}</span></button>"
    )


def export_url(
    context: str | Mapping[str, object] | None,
    *,
    endpoint: str = EXPORT_ENDPOINT,
) -> str:
    """Build a stable GET export URL while retaining every opaque query value."""

    values = query_values(context)
    if not values:
        return endpoint
    return f"{endpoint}?{urlencode(sorted(values.items()))}"


def export_filename(
    *,
    view: str = "view",
    snapshot_token: str | None = None,
) -> str:
    """Return a filesystem-safe browser download name without touching disk."""

    parts = [_SAFE_FILENAME.sub("-", view).strip("-._") or "view"]
    if snapshot_token:
        token = _SAFE_FILENAME.sub("-", snapshot_token).strip("-._")
        if token:
            parts.append(token[:80])
    return "manager-gui-" + "-".join(parts) + ".json"


def current_view_export(
    model: ManagerReadModel,
    *,
    view: str = "atlas",
    query_context: str | Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build a self-contained current-view export payload.

    The nested v0 envelope is unchanged and remains the source of truth. The
    outer metadata records the view/query context needed to reproduce the same
    read, including the requested opaque snapshot token. This function is pure
    and intentionally has no ledger or provider write path.
    """

    values = query_values(query_context)
    selected_view = values.get("view", view) or view
    payload: dict[str, object] = {
        "schema": EXPORT_SCHEMA,
        "read_only": True,
        "view": selected_view,
        "query": urlencode(sorted(values.items())) if values else "",
        "query_params": dict(sorted(values.items())),
        "snapshot_token": model.snapshot_token,
        "requested_snapshot_token": values.get("snapshot_token"),
        "read_model": model.to_dict(),
    }
    return payload


def export_json(
    model: ManagerReadModel,
    *,
    view: str = "atlas",
    query_context: str | Mapping[str, object] | None = None,
    indent: int | None = 2,
) -> str:
    """Serialize :func:`current_view_export` for a local browser download."""

    return json.dumps(
        current_view_export(
            model,
            view=view,
            query_context=query_context,
        ),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        indent=indent,
    )


def render_export_control(
    context: str | Mapping[str, object] | None,
    *,
    view: str = "atlas",
    snapshot_token: str | None = None,
    model: ManagerReadModel | None = None,
) -> str:
    """Render a local-download button; no form submission or mutation occurs.

    When ``model`` is supplied (the shared shell path), the serialized payload is
    embedded in the current document. The button therefore downloads exactly the
    current read without issuing a second provider request.
    """

    url = export_url(context)
    filename = export_filename(view=view, snapshot_token=snapshot_token)
    payload = (
        export_json(
            model,
            view=view,
            query_context=context,
            indent=None,
        )
        if model is not None
        else ""
    )
    payload_attribute = (
        f' data-export-payload="{escape(payload, quote=True)}"' if payload else ""
    )
    return (
        '<div class="export-control" data-export-control="current-view">'
        f'<button class="panel-button" type="button" data-export-current-view '
        f'data-export-url="{escape(url, quote=True)}" '
        f'data-export-filename="{escape(filename, quote=True)}"{payload_attribute} '
        'aria-label="Export current view / 导出当前视图">'
        'Export current view / <span lang="zh-CN">导出当前视图</span></button>'
        '<p class="export-note">Local JSON only; no ledger or owner record is written. '
        '<span lang="zh-CN">仅生成本地 JSON, 不写入 ledger 或业务记录。</span></p>'
        '</div>'
    )


def _mode_button(mode: str, *, selected: bool) -> str:
    labels = {
        "graph": ("Graph", "图谱"),
        "table": ("Table", "表格"),
    }
    label, label_zh = labels.get(mode, (mode.title(), mode))
    return (
        f'<button class="panel-button" type="button" data-view-mode="{escape(mode, quote=True)}" '
        f'aria-pressed="{"true" if selected else "false"}">{escape(label)} / '
        f'<span lang="zh-CN">{escape(label_zh)}</span></button>'
    )


def render_view_mode_controls(
    *,
    target: str,
    selected: str = "table",
    label: str = "Alternative view",
    label_zh: str = "替代视图",
) -> str:
    """Render keyboard-operable graph/table mode controls for a page hook."""

    selected_mode = selected if selected in {"graph", "table"} else "table"
    return (
        f'<div class="view-mode-controls" data-view-mode-target="{escape(target, quote=True)}" '
        f'role="group" aria-label="{escape(label)} / {escape(label_zh)}">'
        f'<span class="view-mode-label">{escape(label)} / '
        f'<span lang="zh-CN">{escape(label_zh)}</span></span>'
        f"{_mode_button('graph', selected=selected_mode == 'graph')}"
        f"{_mode_button('table', selected=selected_mode == 'table')}"
        "</div>"
    )


def render_alternative_view(
    *,
    target: str,
    graph_markup: str,
    table_markup: str,
    selected: str = "table",
    label: str = "Lineage view",
    label_zh: str = "谱系视图",
) -> str:
    """Render both a graph hook and a semantic table alternative.

    Page owners can replace ``graph_markup`` with a visualization while keeping
    ``table_markup`` as the deterministic keyboard/screen-reader path.
    """

    selected_mode = selected if selected in {"graph", "table"} else "table"
    graph_hidden = "" if selected_mode == "graph" else " hidden"
    table_hidden = "" if selected_mode == "table" else " hidden"
    controls = render_view_mode_controls(
        target=target, selected=selected_mode, label=label, label_zh=label_zh
    )
    return (
        f'<section class="alternative-view" data-alternative-view="{escape(target, quote=True)}" '
        f'data-view-mode="{escape(selected_mode, quote=True)}">'
        f"{controls}"
        f'<div data-view-panel="graph" data-view-for="{escape(target, quote=True)}" '
        f'aria-label="{escape(label)} / {escape(label_zh)}"{graph_hidden}>{graph_markup}</div>'
        f'<div data-view-panel="table" data-view-for="{escape(target, quote=True)}" '
        f'aria-label="{escape(label)} / {escape(label_zh)}"{table_hidden}>{table_markup}</div>'
        "</section>"
    )


# Compatibility aliases keep the seam discoverable for page owners and S6-T4.
copy_opaque_reference = opaque_copy_button
build_export_url = export_url
build_current_view_export = current_view_export
export_current_view = current_view_export
render_current_view_export = render_export_control
render_graph_table_alternative = render_alternative_view

__all__ = [
    "EXPORT_ENDPOINT",
    "EXPORT_SCHEMA",
    "build_current_view_export",
    "build_export_url",
    "copy_opaque_reference",
    "current_view_export",
    "export_current_view",
    "export_filename",
    "export_json",
    "export_url",
    "opaque_copy_button",
    "render_alternative_view",
    "render_current_view_export",
    "render_export_control",
    "render_graph_table_alternative",
    "render_view_mode_controls",
]
