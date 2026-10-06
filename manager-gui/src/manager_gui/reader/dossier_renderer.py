"""Deterministic, self-contained Chinese HTML renderer for Dossier v2.

The renderer accepts only an already-built :class:`DossierReport` (or its exact
JSON representation).  It never reads a provider, recalculates a research
metric, dereferences a locator, or publishes an artifact.  Every displayed fact
keeps the record, JSON pointer, and derivation that came from the report model.
"""

# HTML fragments intentionally use readable long lines.
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import html
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Final, cast

from .dossier import (
    DossierEvidence,
    DossierLineageEdge,
    DossierRecordRef,
    DossierReport,
    DossierSection,
    DossierValue,
    DossierValueSource,
)

DOSSIER_RENDERER_SCHEMA: Final = "manager-gui.dossier-html-renderer.v2"
DOSSIER_RENDERER_VERSION: Final = "dossier-html-v2.0"
DOSSIER_BANNER_TEXT: Final = "非前向 Holdout / 非实盘结论"

# This is the fixed categorical order from the dataviz palette validation.  The
# first three slots are safe for all-pairs marks; the renderer uses bar marks and
# therefore keeps the adjacent order for the full set.
LIGHT_CATEGORICAL_PALETTE: Final[tuple[str, ...]] = (
    "#2a78d6",
    "#eb6834",
    "#1baf7a",
    "#eda100",
    "#e87ba4",
    "#008300",
    "#4a3aa7",
    "#e34948",
)
DARK_CATEGORICAL_PALETTE: Final[tuple[str, ...]] = (
    "#3987e5",
    "#d95926",
    "#199e70",
    "#c98500",
    "#d55181",
    "#008300",
    "#9085e9",
    "#e66767",
)
LIGHT_SURFACE: Final[str] = "#fcfcfb"
DARK_SURFACE: Final[str] = "#1a1a19"

_SECTION_LABELS: Final[dict[str, str]] = {
    "source": "研究问题与报告来源",
    "experiment_matrix": "实验矩阵与版本演进",
    "lineage": "研究谱系与数据身份",
    "metrics": "绩效与风险视图",
    "audits": "执行、拒绝与孤儿审计",
    "comparisons": "比较与置信区间",
    "attributions": "归因矩阵",
    "quarantine": "隔离与排除",
    "holdout_lock": "前向 Holdout 锁定状态",
    "limitations": "结论边界与限制",
}
_STATUS_LABELS: Final[dict[str, str]] = {
    "evaluated": "已评估",
    "not_evaluated": "not_evaluated",
}


class DossierRenderError(ValueError):
    """The supplied report model cannot be rendered safely."""


def _canonical_model_json(report: DossierReport) -> str:
    """Return the one canonical JSON representation embedded in the artifact."""

    return json.dumps(
        report.to_dict(),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _model_sha256(report: DossierReport) -> str:
    return hashlib.sha256(_canonical_model_json(report).encode("utf-8")).hexdigest()


def _report(value: DossierReport | Mapping[str, object] | str) -> DossierReport:
    if isinstance(value, DossierReport):
        return value
    try:
        if isinstance(value, str):
            return DossierReport.from_json(value)
        if isinstance(value, Mapping):
            return DossierReport.from_dict(cast(Mapping[str, object], value))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise DossierRenderError("invalid Dossier v2 report model") from exc
    raise TypeError("renderer requires a DossierReport or its JSON object/string")


def _typed_sections(report: DossierReport) -> tuple[DossierSection, ...]:
    return cast(tuple[DossierSection, ...], report.sections)


def _typed_evidence(section: DossierSection) -> tuple[DossierEvidence, ...]:
    return cast(tuple[DossierEvidence, ...], section.evidence)


def _typed_facts(evidence: DossierEvidence) -> tuple[DossierValue, ...]:
    return cast(tuple[DossierValue, ...], evidence.facts)


def _typed_sources(fact: DossierValue) -> tuple[DossierValueSource, ...]:
    return cast(tuple[DossierValueSource, ...], fact.sources)


def _typed_edges(evidence: DossierEvidence) -> tuple[DossierLineageEdge, ...]:
    return cast(tuple[DossierLineageEdge, ...], evidence.lineage)


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _json_for_html(value: object) -> str:
    # JSON inside a script element is data, never executable source.  Escaping
    # the HTML-significant characters also keeps hostile owner text inert.
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    return encoded.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _value_text(value: DossierValue) -> str:
    if value.status == "not_evaluated":
        return "not_evaluated"
    if isinstance(value.value, bool):
        return "是" if value.value else "否"
    if isinstance(value.value, float):
        return format(value.value, ".15g")
    if value.value is None:
        return "not_evaluated"
    return str(value.value)


def _fact_rows(report: DossierReport) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for section in _typed_sections(report):
        for evidence in _typed_evidence(section):
            owner = cast(DossierRecordRef, evidence.source)
            for fact in _typed_facts(evidence):
                source = _typed_sources(fact)[0]
                source_record = cast(DossierRecordRef, source.record)
                rows.append(
                    {
                        "section": section.name,
                        "section_label": _SECTION_LABELS[section.name],
                        "record_id": owner.record_id,
                        "record_type": owner.record_type,
                        "path": fact.path,
                        "value": fact.value,
                        "value_text": _value_text(fact),
                        "status": fact.status,
                        "derivation": fact.derivation,
                        "derivation_reason": fact.derivation_reason,
                        "selector": source.selector,
                        "source_record_id": source_record.record_id,
                        "source_record_type": source_record.record_type,
                    }
                )
    return tuple(rows)


def _numeric_rows(rows: tuple[dict[str, object], ...]) -> tuple[dict[str, object], ...]:
    return tuple(
        row
        for row in rows
        if row["status"] == "evaluated"
        and isinstance(row["value"], (int, float))
        and not isinstance(row["value"], bool)
        and math.isfinite(float(row["value"]))
    )


def _section_narrative(section: DossierSection) -> str:
    if section.status == "not_evaluated":
        return f"{_SECTION_LABELS[section.name]}没有可用的公共属主证据；状态保持 not_evaluated，不作推断。"
    evidence = _typed_evidence(section)
    count = sum(len(_typed_facts(item)) for item in evidence)
    return f"本节复制 {len(evidence)} 条公共证据和 {count} 个带来源事实；没有在报告层重算引擎指标。"


def _render_fact_row(row: Mapping[str, object], index: int) -> str:
    source = f"{row['source_record_type']}:{row['source_record_id']}"
    tooltip = f"{row['section_label']} · {row['path']} · {_value_text_from_row(row)} · 来源 {source}"
    return (
        f'<tr data-fact-row data-section="{_esc(row["section"])}" data-status="{_esc(row["status"])}" '
        f'data-search="{_esc(str(row["section_label"]) + " " + str(row["path"]) + " " + str(row["value_text"]))}">'
        f'<th scope="row"><code>{_esc(row["path"])}</code></th>'
        f'<td class="fact-value" data-tooltip="{_esc(tooltip)}" tabindex="0">{_esc(row["value_text"])}</td>'
        f'<td><span class="status status-{_esc(row["status"])}">{_esc(_STATUS_LABELS.get(str(row["status"]), str(row["status"])))}</span></td>'
        f'<td><code>{_esc(row["derivation"])}</code><small>{_esc(row["derivation_reason"])}</small></td>'
        f'<td><code>{_esc(source)}</code><small>{_esc(row["selector"])}</small></td>'
        f'<td class="row-number">{index}</td>'
        "</tr>"
    )


def _value_text_from_row(row: Mapping[str, object]) -> str:
    value = row["value_text"]
    return str(value)


def _render_bars(rows: tuple[dict[str, object], ...]) -> str:
    numeric = _numeric_rows(rows)[:24]
    if not numeric:
        return '<p class="empty-note">没有可直接复制的数值；图表保持 not_evaluated。</p>'
    max_abs = max(abs(float(cast(int | float, row["value"]))) for row in numeric) or 1.0
    bars: list[str] = []
    for index, row in enumerate(numeric):
        value = float(cast(int | float, row["value"]))
        width = min(100.0, abs(value) / max_abs * 100.0)
        fill = LIGHT_CATEGORICAL_PALETTE[index % len(LIGHT_CATEGORICAL_PALETTE)]
        tooltip = f"{row['path']}：{row['value_text']}；来源 {row['source_record_type']}:{row['source_record_id']}"
        bars.append(
            f'<g class="chart-mark" tabindex="0" data-tooltip="{_esc(tooltip)}" role="img" aria-label="{_esc(tooltip)}">'
            f'<title>{_esc(tooltip)}</title><text class="chart-label" x="0" y="{index * 30 + 18}">{_esc(str(row["path"]))}</text>'
            f'<rect x="190" y="{index * 30 + 7}" width="{width:.3f}%" height="16" rx="4" fill="{fill}" />'
            f'<text class="chart-value" x="{min(98.0, 19.0 + width * 0.8):.3f}%" y="{index * 30 + 19}">{_esc(str(row["value_text"]))}</text></g>'
        )
    height = len(numeric) * 30 + 12
    return (
        f'<svg class="dossier-chart" data-chart="source-values" viewBox="0 0 1000 {height}" role="img" '
        'aria-labelledby="chart-title chart-desc" preserveAspectRatio="xMinYMin meet">'
        '<title id="chart-title">公共证据中的数值</title>'
        '<desc id="chart-desc">仅将已发布数值按视觉比例排列；这不是重新计算的引擎指标。</desc>'
        + "".join(bars)
        + "</svg>"
    )


def _render_sections(report: DossierReport, rows: tuple[dict[str, object], ...]) -> str:
    pieces: list[str] = []
    for index, section in enumerate(_typed_sections(report)):
        facts = tuple(row for row in rows if row["section"] == section.name)
        visible = "" if index == 0 else " hidden"
        cards = []
        for evidence in _typed_evidence(section):
            owner = cast(DossierRecordRef, evidence.source)
            cards.append(
                f'<article class="evidence-card" data-record-id="{_esc(owner.record_id)}">'
                f'<h3>{_esc(owner.record_type)}</h3>'
                f'<p class="record-id"><code>{_esc(owner.record_id)}</code></p>'
                f'<p class="evidence-lineage">谱系边数：{len(evidence.lineage)}；引用制品：{len(evidence.artifacts)}</p>'
                "</article>"
            )
        card_markup = "".join(cards) or '<p class="empty-note">not_evaluated：没有公共证据。</p>'
        chart_markup = _render_bars(facts) if section.name in {"metrics", "comparisons", "attributions"} else ""
        pieces.append(
            f'<section class="dossier-panel" id="panel-{_esc(section.name)}" data-panel="{_esc(section.name)}" '
            f'data-section-status="{_esc(section.status)}"{visible} role="tabpanel" aria-labelledby="tab-{_esc(section.name)}">'
            f'<h2>{_esc(_SECTION_LABELS[section.name])}</h2>'
            f'<p class="section-narrative">{_esc(_section_narrative(section))}</p>'
            f'<p class="section-state state-{_esc(section.status)}"><strong>状态</strong> {_esc(_STATUS_LABELS.get(section.status, section.status))}</p>'
            f'<div class="evidence-cards">{card_markup}</div>'
            f'<div class="section-chart">{chart_markup}</div>'
            "</section>"
        )
    return "".join(pieces)


def _render_table(rows: tuple[dict[str, object], ...]) -> str:
    body = "".join(_render_fact_row(row, index) for index, row in enumerate(rows, 1))
    return (
        '<div class="table-wrap" role="region" aria-label="证据事实表，可横向滚动" tabindex="0">'
        '<table id="fact-table" class="fact-table"><caption>所有已复制事实、状态、推导和来源</caption>'
        '<thead><tr><th scope="col">JSON 指针</th><th scope="col">值</th><th scope="col">状态</th><th scope="col">推导</th><th scope="col">来源</th><th scope="col">序号</th></tr></thead>'
        f'<tbody>{body}</tbody></table></div>'
    )


def _render_lineage(report: DossierReport) -> str:
    rows: list[str] = []
    for section in _typed_sections(report):
        for evidence in _typed_evidence(section):
            for edge in _typed_edges(evidence):
                rows.append(
                    f'<tr><th scope="row">{_esc(edge.source_kind)}</th><td><code>{_esc(edge.source_id)}</code></td><td>{_esc(edge.relation)}</td><td>{_esc(section.name)}</td></tr>'
                )
    if not rows:
        rows.append('<tr><td colspan="4">not_evaluated：没有公开谱系边。</td></tr>')
    return (
        '<table class="lineage-table"><caption>研究问题到结论的公开谱系边</caption>'
        '<thead><tr><th scope="col">来源类型</th><th scope="col">来源 ID</th><th scope="col">关系</th><th scope="col">所在节</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
    )


def _render_html(report: DossierReport) -> str:
    rows = _fact_rows(report)
    model_hash = _model_sha256(report)
    tabs: list[str] = []
    sections = _typed_sections(report)
    for index, section in enumerate(sections):
        selected = "true" if index == 0 else "false"
        tab_index = "0" if index == 0 else "-1"
        tabs.append(
            f'<button class="tab-button" id="tab-{_esc(section.name)}" data-tab="{_esc(section.name)}" role="tab" aria-controls="panel-{_esc(section.name)}" aria-selected="{selected}" tabindex="{tab_index}">{_esc(_SECTION_LABELS[section.name])}</button>'
        )
    source_records = cast(tuple[DossierRecordRef, ...], report.source_records)
    source_ids = "、".join(record.record_id for record in source_records)
    return f'''<!doctype html>
<html lang="zh-CN" data-dossier-schema="{DOSSIER_RENDERER_SCHEMA}" data-model-sha256="{model_hash}">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(report.title)}</title>
<style>
:root {{ color-scheme: light; --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --muted:#52514e; --quiet:#898781; --line:#e1e0d9; --axis:#c3c2b7; --accent:#2a78d6; --warning:#eda100; --danger:#e34948; --good:#008300; --shadow:0 8px 24px rgba(11,11,11,.06); }}
:root[data-theme="dark"] {{ color-scheme: dark; --page:#0d0d0d; --surface:#1a1a19; --ink:#fff; --muted:#c3c2b7; --quiet:#aaa9a2; --line:#2c2c2a; --axis:#383835; --accent:#3987e5; --warning:#c98500; --danger:#e66767; --good:#008300; --shadow:0 8px 24px rgba(0,0,0,.28); }}
@media (prefers-color-scheme:dark) {{ :root:not([data-theme="light"]) {{ color-scheme:dark; --page:#0d0d0d; --surface:#1a1a19; --ink:#fff; --muted:#c3c2b7; --quiet:#aaa9a2; --line:#2c2c2a; --axis:#383835; --accent:#3987e5; --warning:#c98500; --danger:#e66767; --good:#008300; --shadow:0 8px 24px rgba(0,0,0,.28); }} }}
* {{ box-sizing:border-box; }} html {{ background:var(--page); }} body {{ margin:0; background:var(--page); color:var(--ink); font:16px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif; }}
main {{ width:min(1440px,100% - 32px); margin:0 auto; padding:24px 0 64px; }} h1,h2,h3 {{ line-height:1.25; }} h1 {{ font-size:clamp(1.8rem,4vw,3rem); margin:.5rem 0 1rem; }} h2 {{ font-size:1.35rem; }} h3 {{ font-size:1rem; }} code,.record-id,.row-number {{ font-variant-numeric:tabular-nums; }} code {{ overflow-wrap:anywhere; }}
.utility-bar,.filter-bar,.report-meta,.boundary-banner,.section-state,.evidence-card,.table-wrap,.lineage-table,.chart-card {{ background:var(--surface); border:1px solid var(--line); border-radius:12px; box-shadow:var(--shadow); }} .utility-bar,.filter-bar {{ display:flex; align-items:center; gap:12px; flex-wrap:wrap; padding:12px 16px; }} .utility-bar {{ justify-content:space-between; }} button,input,select {{ font:inherit; color:var(--ink); background:var(--surface); border:1px solid var(--axis); border-radius:8px; padding:8px 10px; }} button {{ cursor:pointer; }} button:hover,button:focus-visible,input:focus-visible,select:focus-visible {{ outline:3px solid color-mix(in srgb,var(--accent),transparent 65%); outline-offset:2px; }}
.boundary-banner {{ position:sticky; top:0; z-index:3; margin:16px 0; padding:14px 18px; background:color-mix(in srgb,var(--danger),var(--surface) 88%); border-left:6px solid var(--danger); font-weight:700; }} .boundary-banner small {{ display:block; font-weight:400; color:var(--muted); }} .eyebrow,.muted,.section-narrative,.evidence-lineage,small {{ color:var(--muted); }} .report-meta {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; padding:16px; margin:16px 0; }} .report-meta dt {{ color:var(--muted); font-size:.82rem; }} .report-meta dd {{ margin:0; overflow-wrap:anywhere; }}
.filter-bar {{ margin:16px 0; }} .filter-bar label {{ display:flex; align-items:center; gap:6px; }} .filter-bar input[type="search"] {{ min-width:min(360px,100%); }} .tabs {{ display:flex; gap:6px; overflow-x:auto; padding:4px 0 10px; }} .tab-button {{ white-space:nowrap; border-radius:999px; }} .tab-button[aria-selected="true"] {{ background:var(--accent); color:#fff; border-color:var(--accent); }}
.dossier-panel {{ padding:20px 0; }} .dossier-panel[hidden] {{ display:none; }} .section-state {{ display:inline-block; padding:5px 10px; box-shadow:none; }} .state-not_evaluated {{ border-color:var(--warning); }} .evidence-cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:12px; }} .evidence-card {{ padding:14px; box-shadow:none; }} .evidence-card h3 {{ margin:.1rem 0; }} .evidence-card p {{ margin:.25rem 0; }} .record-id {{ font-size:.78rem; }} .empty-note {{ color:var(--muted); font-style:italic; }}
.chart-card {{ margin:16px 0; padding:16px; }} .dossier-chart {{ display:block; width:100%; min-height:80px; color:var(--muted); overflow:visible; }} .chart-label,.chart-value {{ fill:var(--ink); font-size:14px; dominant-baseline:middle; }} .chart-label {{ font-family:ui-monospace,SFMono-Regular,Consolas,monospace; }} .chart-mark {{ outline:none; }} .chart-mark:focus rect,.chart-mark:hover rect {{ filter:brightness(1.12); stroke:var(--ink); stroke-width:2; }}
.table-wrap {{ overflow:auto; margin:16px 0; box-shadow:none; }} table {{ border-collapse:collapse; width:100%; min-width:820px; }} caption {{ text-align:left; padding:12px 14px; font-weight:700; }} th,td {{ border-top:1px solid var(--line); padding:9px 10px; text-align:left; vertical-align:top; }} thead th {{ color:var(--muted); font-size:.85rem; position:sticky; top:0; background:var(--surface); }} tbody th {{ font-weight:500; }} .fact-value {{ font-weight:650; }} td small {{ display:block; margin-top:3px; }} .status {{ display:inline-block; padding:1px 7px; border-radius:999px; border:1px solid var(--axis); font-size:.82rem; }} .status-evaluated {{ color:var(--good); }} .status-not_evaluated {{ color:var(--warning); }} .lineage-table {{ margin:16px 0; box-shadow:none; }}
.tooltip {{ position:fixed; z-index:8; max-width:min(420px,calc(100vw - 24px)); padding:8px 10px; border:1px solid var(--axis); border-radius:8px; background:var(--ink); color:var(--page); box-shadow:var(--shadow); pointer-events:none; }} .tooltip[hidden] {{ display:none; }} .sr-only {{ position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }} footer {{ border-top:1px solid var(--line); padding-top:20px; margin-top:24px; color:var(--muted); }}
@media (max-width:700px) {{ main {{ width:min(100% - 20px,1440px); padding-top:12px; }} .utility-bar,.filter-bar {{ align-items:stretch; flex-direction:column; }} .filter-bar label {{ display:block; }} .filter-bar input,.filter-bar select {{ width:100%; }} .report-meta {{ grid-template-columns:1fr; }} .boundary-banner {{ position:relative; }} .chart-label {{ font-size:11px; }} }}
@media (forced-colors:active) {{ .tab-button[aria-selected="true"] {{ forced-color-adjust:none; background:Highlight; color:HighlightText; }} .chart-mark rect {{ fill:Highlight; fill-opacity:.7; }} }}
</style>
</head>
<body data-palette-validation="validated-light-dark">
<main id="dossier" data-renderer-version="{DOSSIER_RENDERER_VERSION}">
<div class="utility-bar"><span class="eyebrow">离线证据账本 · {DOSSIER_RENDERER_VERSION}</span><button type="button" id="theme-toggle" aria-pressed="false">切换深色主题</button></div>
<div class="boundary-banner" role="note" aria-label="结论边界"><span>{_esc(report.banner or DOSSIER_BANNER_TEXT)}</span><small>本页面只使用已发布的公共 Workspace 与 Strategy Reporting 证据；不读取前向 Holdout，不代表实盘或生产资格。</small></div>
<header><p class="eyebrow">Quant Research Dossier v2</p><h1>{_esc(report.title)}</h1><p class="section-narrative">这是一份可离线检查的开发与验证证据说明。数值只在公共属主证据存在时展示；缺少证据会明确标记为 not_evaluated。</p></header>
<dl class="report-meta"><div><dt>证据上限</dt><dd>{_esc(report.evidence_ceiling)}</dd></div><div><dt>Holdout 结果</dt><dd>not_evaluated（锁定或延期）</dd></div><div><dt>资格、因果、生产推断</dt><dd>forbidden</dd></div><div><dt>模型 SHA-256</dt><dd><code>{model_hash}</code></dd></div><div><dt>公共记录数</dt><dd>{len(report.source_records)}</dd></div><div><dt>公共制品数</dt><dd>{len(report.source_artifacts)}</dd></div><div><dt>来源闭包</dt><dd><code>{_esc(source_ids)}</code></dd></div></dl>
<div class="filter-bar" role="search"><label for="fact-filter">筛选事实 <input id="fact-filter" type="search" placeholder="按 JSON 指针、节或值筛选" autocomplete="off"></label><label for="status-filter">状态 <select id="status-filter"><option value="all">全部状态</option><option value="evaluated">已评估</option><option value="not_evaluated">not_evaluated</option></select></label><span id="filter-count" class="muted" aria-live="polite">共 {len(rows)} 条事实</span></div>
<nav class="tabs" aria-label="报告章节" role="tablist">{"".join(tabs)}</nav>
<div id="panels">{_render_sections(report, rows)}</div>
<section class="chart-card" aria-labelledby="numbers-title"><h2 id="numbers-title">公共数值视图</h2><p class="section-narrative">图表只把模型中已有的数值做视觉排版；它不补齐缺失字段，也不重算任何引擎指标。悬停或聚焦图形可查看来源。</p>{_render_bars(rows)}</section>
<section aria-labelledby="facts-title"><h2 id="facts-title">可访问表格视图</h2><p class="section-narrative">表格是图形的完整替代入口；每一行都显示状态、推导理由、记录 ID 和 JSON 指针。</p>{_render_table(rows)}</section>
<section aria-labelledby="lineage-title"><h2 id="lineage-title">证据谱系表</h2>{_render_lineage(report)}</section>
<footer><p>生成器：<code>{DOSSIER_RENDERER_SCHEMA}</code> · 模型和 HTML 均为确定性输出。</p><p>本页不能用来推出盈利性、因果关系、生产批准或前向 Holdout 结果。</p></footer>
</main>
<div id="tooltip" class="tooltip" role="tooltip" hidden></div>
<script type="application/json" id="dossier-model">{_json_for_html(report.to_dict())}</script>
<script>
(() => {{
  const root = document.documentElement;
  const themeButton = document.getElementById('theme-toggle');
  const setTheme = (theme) => {{ root.dataset.theme = theme; themeButton.setAttribute('aria-pressed', theme === 'dark' ? 'true' : 'false'); themeButton.textContent = theme === 'dark' ? '切换浅色主题' : '切换深色主题'; }};
  themeButton.addEventListener('click', () => setTheme(root.dataset.theme === 'dark' ? 'light' : 'dark'));
  const tooltip = document.getElementById('tooltip');
  const showTip = (event) => {{ const text = event.currentTarget.dataset.tooltip; if (!text) return; tooltip.textContent = text; tooltip.hidden = false; const x = Math.min(event.clientX + 12, window.innerWidth - tooltip.offsetWidth - 12); const y = Math.min(event.clientY + 12, window.innerHeight - tooltip.offsetHeight - 12); tooltip.style.left = `${{Math.max(8, x)}}px`; tooltip.style.top = `${{Math.max(8, y)}}px`; }};
  const hideTip = () => {{ tooltip.hidden = true; }};
  document.querySelectorAll('[data-tooltip]').forEach((node) => {{ node.addEventListener('pointermove', showTip); node.addEventListener('focus', showTip); node.addEventListener('pointerleave', hideTip); node.addEventListener('blur', hideTip); }});
  const buttons = [...document.querySelectorAll('[data-tab]')];
  const panels = [...document.querySelectorAll('[data-panel]')];
  const activate = (name) => {{ buttons.forEach((button) => {{ const selected = button.dataset.tab === name; button.setAttribute('aria-selected', selected ? 'true' : 'false'); button.tabIndex = selected ? 0 : -1; }}); panels.forEach((panel) => {{ panel.hidden = panel.dataset.panel !== name; }}); }};
  buttons.forEach((button, index) => {{ button.addEventListener('click', () => activate(button.dataset.tab)); button.addEventListener('keydown', (event) => {{ if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return; event.preventDefault(); const next = (index + (event.key === 'ArrowRight' ? 1 : -1) + buttons.length) % buttons.length; buttons[next].focus(); activate(buttons[next].dataset.tab); }}); }});
  const query = document.getElementById('fact-filter'); const status = document.getElementById('status-filter'); const count = document.getElementById('filter-count'); const rows = [...document.querySelectorAll('[data-fact-row]')];
  const apply = () => {{ const needle = query.value.trim().toLocaleLowerCase(); const selected = status.value; let visible = 0; rows.forEach((row) => {{ const matchText = !needle || row.dataset.search.toLocaleLowerCase().includes(needle); const matchStatus = selected === 'all' || row.dataset.status === selected; row.hidden = !(matchText && matchStatus); if (matchText && matchStatus) visible += 1; }}); count.textContent = `显示 ${{visible}} / ${{rows.length}} 条事实`; }};
  query.addEventListener('input', apply); status.addEventListener('change', apply);
}})();
</script>
</body></html>'''


@dataclass(frozen=True, slots=True)
class PaletteValidation:
    """Result of the fixed light/dark palette check."""

    passed: bool
    light_contrast: float
    dark_contrast: float
    categorical_slots: int = len(LIGHT_CATEGORICAL_PALETTE)

    def __bool__(self) -> bool:
        return self.passed


def _hex_luminance(value: str) -> float:
    channels = [int(value[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(foreground: str, background: str) -> float:
    first, second = _hex_luminance(foreground), _hex_luminance(background)
    return (max(first, second) + 0.05) / (min(first, second) + 0.05)


def validate_chart_palette() -> PaletteValidation:
    """Validate palette surfaces and presence of the fixed categorical order.

    CVD and adjacent-pair validation is recorded in the dataviz reference
    palette; this local check re-runs the machine-checkable contrast and shape
    invariants so the HTML cannot silently ship without both themes.
    """

    light = min(_contrast(color, LIGHT_SURFACE) for color in LIGHT_CATEGORICAL_PALETTE)
    dark = min(_contrast(color, DARK_SURFACE) for color in DARK_CATEGORICAL_PALETTE)
    passed = (
        len(LIGHT_CATEGORICAL_PALETTE) == len(DARK_CATEGORICAL_PALETTE) == 8
        and all(re.fullmatch(r"#[0-9a-f]{6}", color) for color in LIGHT_CATEGORICAL_PALETTE + DARK_CATEGORICAL_PALETTE)
        and light > 1.5
        and dark > 3.0
    )
    return PaletteValidation(passed, light, dark)


@dataclass(frozen=True, slots=True)
class DossierHTMLInspection:
    """Static properties found in one rendered HTML artifact."""

    html_sha256: str
    model_sha256: str | None
    self_contained: bool
    has_boundary_banner: bool
    has_accessible_table: bool
    has_theme_toggle: bool
    has_filters: bool
    has_tabs: bool
    has_tooltips: bool
    has_responsive_layout: bool
    has_chart: bool
    fact_count: int
    external_dependencies: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return self.self_contained and self.has_boundary_banner and self.has_accessible_table and self.has_theme_toggle and self.has_filters and self.has_tabs and self.has_tooltips and self.has_responsive_layout


class _HTMLInspectionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.model_text: list[str] = []
        self.in_model = False
        self.external: list[str] = []
        self.fact_count = 0
        self.tags: set[str] = set()
        self.attributes: dict[str, list[dict[str, str]]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.add(tag)
        values = {key: value or "" for key, value in attrs}
        self.attributes.setdefault(tag, []).append(values)
        if tag == "script" and values.get("id") == "dossier-model":
            self.in_model = True
        if "data-fact-row" in values:
            self.fact_count += 1
        for key in ("src", "href"):
            value = values.get(key, "")
            if value and (value.startswith("http://") or value.startswith("https://")):
                self.external.append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self.in_model:
            self.in_model = False

    def handle_data(self, data: str) -> None:
        if self.in_model:
            self.model_text.append(data)


def inspect_dossier_html(value: str) -> DossierHTMLInspection:
    if not isinstance(value, str):
        raise TypeError("HTML inspection requires a string")
    parser = _HTMLInspectionParser()
    parser.feed(value)
    root = parser.attributes.get("html", [{}])[0]
    model_hash = root.get("data-model-sha256")
    try:
        embedded = json.loads("".join(parser.model_text)) if parser.model_text else None
        if isinstance(embedded, Mapping):
            model_hash = hashlib.sha256(json.dumps(embedded, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    except (json.JSONDecodeError, TypeError, ValueError):
        model_hash = None
    all_markup = value.lower()
    external = tuple(sorted(set(parser.external)))
    return DossierHTMLInspection(
        html_sha256=hashlib.sha256(value.encode("utf-8")).hexdigest(),
        model_sha256=model_hash,
        self_contained=not external and "<link" not in all_markup and "<script src=" not in all_markup and "@import" not in all_markup,
        has_boundary_banner=DOSSIER_BANNER_TEXT in value,
        has_accessible_table='<table id="fact-table"' in value and 'scope="col"' in value and 'scope="row"' in value,
        has_theme_toggle='id="theme-toggle"' in value and 'data-theme="dark"' in value,
        has_filters='id="fact-filter"' in value and 'id="status-filter"' in value,
        has_tabs='role="tablist"' in value and 'role="tabpanel"' in value,
        has_tooltips='data-tooltip=' in value and 'role="tooltip"' in value,
        has_responsive_layout="@media (max-width:700px)" in value,
        has_chart='data-chart="source-values"' in value,
        fact_count=parser.fact_count,
        external_dependencies=external,
    )


@dataclass(frozen=True, slots=True)
class DossierHTMLVerification:
    """Deterministic and accessibility verification result."""

    passed: bool
    errors: tuple[str, ...]
    inspection: DossierHTMLInspection
    expected_model_sha256: str | None = None

    def __bool__(self) -> bool:
        return self.passed


def verify_dossier_html(
    value: str, model: DossierReport | Mapping[str, object] | str | None = None
) -> DossierHTMLVerification:
    """Verify a self-contained artifact, optionally against its source model."""

    inspection = inspect_dossier_html(value)
    errors: list[str] = []
    expected_hash: str | None = None
    if not inspection.self_contained:
        errors.append("external HTML dependency")
    for field, message in (
        (inspection.has_boundary_banner, "persistent boundary banner is missing"),
        (inspection.has_accessible_table, "accessible fact table is missing"),
        (inspection.has_theme_toggle, "light/dark theme control is missing"),
        (inspection.has_filters, "fact filters are missing"),
        (inspection.has_tabs, "accessible section tabs are missing"),
        (inspection.has_tooltips, "tooltip layer is missing"),
        (inspection.has_responsive_layout, "responsive layout is missing"),
    ):
        if not field:
            errors.append(message)
    palette = validate_chart_palette()
    if not palette:
        errors.append("chart palette validation failed")
    if model is not None:
        report = _report(model)
        expected_hash = _model_sha256(report)
        if inspection.model_sha256 != expected_hash:
            errors.append("embedded model hash differs")
        expected_html = _render_html(report)
        if value != expected_html:
            errors.append("HTML is not the deterministic rendering of the model")
        if inspection.fact_count != len(_fact_rows(report)):
            errors.append("fact row count differs from model")
    elif inspection.model_sha256 is None:
        errors.append("embedded model is missing or invalid")
    return DossierHTMLVerification(not errors, tuple(errors), inspection, expected_hash)


@dataclass(frozen=True, slots=True)
class DossierHTMLRenderer:
    """Stateless renderer facade used by the release/rebuild gate."""

    version: str = DOSSIER_RENDERER_VERSION

    def render(self, model: DossierReport | Mapping[str, object] | str) -> str:
        report = _report(model)
        return _render_html(report)

    def render_html(self, model: DossierReport | Mapping[str, object] | str) -> str:
        return self.render(model)

    def inspect(self, html_value: str) -> DossierHTMLInspection:
        return inspect_dossier_html(html_value)

    def verify(
        self, html_value: str, model: DossierReport | Mapping[str, object] | str | None = None
    ) -> DossierHTMLVerification:
        return verify_dossier_html(html_value, model)


InteractiveDossierRenderer = DossierHTMLRenderer
DossierRenderer = DossierHTMLRenderer
def render_dossier_html(model: DossierReport | Mapping[str, object] | str) -> str:
    """Render an offline dossier from an already-published evidence model."""

    return DossierHTMLRenderer().render(model)


render_dossier = render_dossier_html
inspect_dossier = inspect_dossier_html
verify_dossier = verify_dossier_html


__all__ = [
    "DARK_CATEGORICAL_PALETTE",
    "DARK_SURFACE",
    "DOSSIER_BANNER_TEXT",
    "DOSSIER_RENDERER_SCHEMA",
    "DOSSIER_RENDERER_VERSION",
    "LIGHT_CATEGORICAL_PALETTE",
    "LIGHT_SURFACE",
    "DossierHTMLInspection",
    "DossierHTMLRenderer",
    "DossierHTMLVerification",
    "DossierRenderError",
    "DossierRenderer",
    "InteractiveDossierRenderer",
    "PaletteValidation",
    "inspect_dossier",
    "inspect_dossier_html",
    "render_dossier",
    "render_dossier_html",
    "validate_chart_palette",
    "verify_dossier",
    "verify_dossier_html",
]
