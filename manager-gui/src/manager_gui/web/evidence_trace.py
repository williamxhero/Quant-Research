"""Conclusion -> evidence -> source/artifact -> lineage trace for the Evidence route.

The shell mounts :func:`render_evidence_trace` after the Evidence Ledger so a
reader can walk from a published conclusion to its evidence records, their
sources and artifacts, and on to the bounded lineage view.  It also gives the
``record_id`` / ``artifact_id`` / ``source_id`` links that the ledger already
emits a real target: a selected-detail panel.

The trace reads only the public :class:`EvidenceViewModel` and two *explicit*
published pointers: ``conclusion_id`` on the ledger and ``lineage_id`` on a
record or artifact.  It never matches ids by similarity, never dereferences a
locator, and never recomputes an owner fact.  Every hop that is not published
stays ``Missing / Unconfirmed``; a missing hop is not a failure and not proof
of absence.  Cross-resource links (Evidence to Lineage, comparison, grouping)
do not forward ``snapshot_token`` or any page cursor: each resource owns its
own snapshot and snapshots are never mixed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import escape
from typing import TypeAlias

from ..models import ManagerReadModel
from .evidence import (
    EvidenceArtifact,
    EvidenceKind,
    EvidenceRecord,
    EvidenceSourceRef,
    EvidenceViewModel,
)
from .locators import public_locator
from .navigation import ViewId, context_link, query_values

QueryContext: TypeAlias = str | Mapping[str, object] | None

EVIDENCE_TRACE_HOOK = "evidence-trace"
MAX_TRACE_ROWS = 20
MISSING = "Missing / Unconfirmed"
MISSING_ZH = "缺失 / 未确认"

# Page state that belongs to one resource and must not leak into another resource's page.
_PAGE_STATE: Mapping[str, None] = {
    "snapshot_token": None,
    "page": None,
    "page_size": None,
    "cursor": None,
    "node": None,
    "path_to": None,
    "record_id": None,
    "artifact_id": None,
    "source_id": None,
}

_KIND_LABELS: Mapping[EvidenceKind, str] = {
    EvidenceKind.CANDIDATE: "Candidate evidence",
    EvidenceKind.PROTOCOL_CONFORMING: "Protocol-conforming evidence",
    EvidenceKind.NOT_RECORDED: "Evidence class not recorded",
}


def _attr(value: str) -> str:
    return escape(value, quote=True)


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _pointer(raw: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        if (value := _text(raw.get(key))) is not None:
            return value
    return None


def _cross_link(context: QueryContext, view: ViewId, **updates: str | None) -> str:
    return context_link(context, view=view, **{**_PAGE_STATE, **updates})


def _detail_link(context: QueryContext, **updates: str | None) -> str:
    cleared: dict[str, str | None] = {"record_id": None, "artifact_id": None, "source_id": None}
    return context_link(context, view=ViewId.EVIDENCE, **{**cleared, **updates})


def _missing(what: str, key: str) -> str:
    return (
        f'<span class="trace-missing" data-trace-missing="{_attr(key)}">{escape(what)} — '
        f'{MISSING} / <span lang="zh-CN">{MISSING_ZH}</span></span>'
    )


def _lineage_link(context: QueryContext, lineage_id: str | None, label: str) -> str:
    if lineage_id is None:
        return _missing("Lineage", "lineage")
    href = _cross_link(context, ViewId.LINEAGE, record_id=lineage_id)
    return (
        f'<a class="trace-lineage-link" data-lineage-id="{_attr(lineage_id)}" '
        f'href="{_attr(href)}">{escape(label)}</a>'
    )


def _source_item(source_id: str, locator: str | None) -> str:
    target = public_locator(locator)
    if target is not None:
        return (
            f'<a class="trace-source-link" data-source-id="{_attr(source_id)}" '
            f'href="{_attr(target)}">{escape(source_id)}</a>'
        )
    return f'<span data-source-id="{_attr(source_id)}">{_missing(source_id, "source")}</span>'


def _sources(refs: Sequence[EvidenceSourceRef]) -> str:
    if not refs:
        return _missing("Sources", "source")
    items = "".join(f"<li>{_source_item(ref.source_id, ref.locator)}</li>" for ref in refs)
    return f"<ul>{items}</ul>"


def _artifact_name(artifact: EvidenceArtifact) -> str:
    target = public_locator(artifact.locator)
    if target is not None:
        return f'<a class="trace-artifact-link" href="{_attr(target)}">{escape(artifact.name)}</a>'
    return f"{escape(artifact.name)} — {_missing('Artifact locator', 'artifact')}"


def _artifact_item(artifact: EvidenceArtifact, context: QueryContext) -> str:
    status = artifact.verification_status.value
    detail = _detail_link(context, artifact_id=artifact.artifact_id)
    lineage_id = _pointer(artifact.raw, "lineage_id", "lineageId")
    return (
        f'<li data-trace-artifact="{_attr(artifact.artifact_id)}" '
        f'data-verification-status="{_attr(status)}">{_artifact_name(artifact)} · '
        f"verification {escape(status.replace('_', ' '))} · "
        f"hash {escape(artifact.hash or MISSING)} · "
        f'<a class="trace-detail-link" href="{_attr(detail)}">Details</a> · '
        f"{_lineage_link(context, lineage_id, 'Open lineage for this artifact')}</li>"
    )


def _record_item(record: EvidenceRecord, context: QueryContext) -> str:
    detail = _detail_link(context, record_id=record.record_id)
    lineage_id = _pointer(record.raw, "lineage_id", "lineageId")
    return (
        f'<li data-trace-record="{_attr(record.record_id)}" '
        f'data-evidence-kind="{record.evidence_kind.value}" '
        f'data-evidence-status="{record.status.value}">'
        f'<a class="trace-detail-link" href="{_attr(detail)}">{escape(record.label)}</a> · '
        f"{escape(_KIND_LABELS[record.evidence_kind])} · "
        f"status {escape(record.status.value.replace('_', ' '))} · "
        f"{_lineage_link(context, lineage_id, 'Open lineage for this record')}</li>"
    )


def _bounded(items: Sequence[str], total: int, noun: str) -> str:
    if not items:
        return _missing(f"No {noun} published", noun)
    more = (
        f"<p>Showing {len(items)} of {total} {noun}; the Evidence Ledger lists the rest.</p>"
        if total > len(items)
        else ""
    )
    return f"<ul>{''.join(items)}</ul>{more}"


def _list_or_none(values: Sequence[str]) -> str:
    if not values:
        return "None published"
    return "<ul>" + "".join(f"<li>{escape(value)}</li>" for value in values) + "</ul>"


def _detail_panel(kind: str, title: str, body: str, *, found: bool) -> str:
    heading = f"trace-detail-{kind}-heading"
    return (
        f'<section class="evidence-trace-detail" data-trace-detail="{kind}" '
        f'data-trace-found="{"true" if found else "false"}" aria-labelledby="{heading}">'
        f'<h3 id="{heading}">{escape(title)}</h3>{body}</section>'
    )


def _not_published(kind: str, title: str, value: str) -> str:
    body = (
        f"<p>{escape(value)} is not published in this ledger scope — {MISSING}. This is not a "
        "failure and not proof that the record does not exist.</p>"
    )
    return _detail_panel(kind, title, body, found=False)


def _fact(label: str, value: str) -> str:
    return f"<div><dt>{escape(label)}</dt><dd>{value}</dd></div>"


def _record_detail(view: EvidenceViewModel, record_id: str, context: QueryContext) -> str:
    title = "Selected evidence record"
    record = next((item for item in view.records if item.record_id == record_id), None)
    if record is None:
        return _not_published("record", title, record_id)
    lineage_id = _pointer(record.raw, "lineage_id", "lineageId")
    artifacts = "".join(_artifact_item(artifact, context) for artifact in record.artifacts)
    artifact_cell = f"<ul>{artifacts}</ul>" if artifacts else _missing("Artifacts", "artifact")
    body = (
        "<dl>"
        + _fact("Record", f"{escape(record.label)} ({escape(record.record_id)})")
        + _fact("Evidence class", escape(_KIND_LABELS[record.evidence_kind]))
        + _fact("Status", escape(record.status.value.replace("_", " ")))
        + _fact("Evidence level", escape(record.evidence_level.value.replace("_", " ")))
        + _fact("Blockers", _list_or_none(record.blockers))
        + _fact("Incompatibilities", _list_or_none(record.incompatibilities))
        + _fact("Sources", _sources(record.source_refs))
        + _fact("Artifacts", artifact_cell)
        + _fact("Lineage", _lineage_link(context, lineage_id, "Open lineage for this record"))
        + "</dl>"
    )
    return _detail_panel("record", title, body, found=True)


def _artifact_detail(view: EvidenceViewModel, artifact_id: str, context: QueryContext) -> str:
    title = "Selected artifact"
    artifact = view.artifact(artifact_id)
    if artifact is None:
        return _not_published("artifact", title, artifact_id)
    lineage_id = _pointer(artifact.raw, "lineage_id", "lineageId")
    body = (
        "<dl>"
        + _fact("Artifact", _artifact_name(artifact))
        + _fact("Verification status", escape(artifact.verification_status.value.replace("_", " ")))
        + _fact("Verification detail", escape(artifact.verification_detail or MISSING))
        + _fact("Hash", escape(artifact.hash or MISSING))
        + _fact("Producer", escape(artifact.producer or MISSING))
        + _fact("Runtime version", escape(artifact.runtime_version or MISSING))
        + _fact("Data version", escape(artifact.data_version or MISSING))
        + _fact("Sources", _sources(artifact.source_refs))
        + _fact("Lineage", _lineage_link(context, lineage_id, "Open lineage for this artifact"))
        + "</dl>"
    )
    return _detail_panel("artifact", title, body, found=True)


def _source_detail(view: EvidenceViewModel, model: ManagerReadModel, source_id: str) -> str:
    title = "Selected source"
    ledger_ref = next((ref for ref in view.sources if ref.source_id == source_id), None)
    envelope_ref = next((ref for ref in model.source_refs if ref.source_id == source_id), None)
    if ledger_ref is None and envelope_ref is None:
        return _not_published("source", title, source_id)
    # The ledger's own reference wins; the envelope reference only fills what it left out.
    refs = [ref for ref in (ledger_ref, envelope_ref) if ref is not None]
    locator = next((ref.locator for ref in refs if ref.locator), None)
    owner = next((ref.owner for ref in refs if ref.owner), None)
    kind = next((ref.kind for ref in refs if ref.kind), None)
    body = (
        "<dl>"
        + _fact("Source", _source_item(source_id, locator))
        + _fact("Owner", escape(owner or MISSING))
        + _fact("Kind", escape(kind or MISSING))
        + "</dl>"
    )
    return _detail_panel("source", title, body, found=True)


def _selected_detail(
    view: EvidenceViewModel, model: ManagerReadModel, context: QueryContext
) -> str:
    values = query_values(context)
    panels: list[str] = []
    if (record_id := _text(values.get("record_id"))) is not None:
        panels.append(_record_detail(view, record_id, context))
    if (artifact_id := _text(values.get("artifact_id"))) is not None:
        panels.append(_artifact_detail(view, artifact_id, context))
    if (source_id := _text(values.get("source_id"))) is not None:
        panels.append(_source_detail(view, model, source_id))
    return "".join(panels)


def render_evidence_trace(model: ManagerReadModel, *, query_context: QueryContext = None) -> str:
    """Render the trace and any selected-detail panel for one already-read Evidence envelope."""

    view = EvidenceViewModel.from_read_model(model)
    ledger = view.ledger
    conclusion_id = _pointer(ledger.raw, "conclusion_id", "conclusionId")
    conclusion = (
        escape(ledger.conclusion)
        if ledger.conclusion
        else _missing("Conclusion", "conclusion")
    )
    records = [_record_item(record, query_context) for record in ledger.records[:MAX_TRACE_ROWS]]
    sources = [
        f"<li>{_source_item(ref.source_id, ref.locator)}</li>"
        for ref in ledger.sources[:MAX_TRACE_ROWS]
    ]
    artifacts = [_artifact_item(item, query_context) for item in ledger.artifacts[:MAX_TRACE_ROWS]]
    comparison = _cross_link(query_context, ViewId.EVIDENCE_COMPARISON)
    grouping = _cross_link(query_context, ViewId.FAILURE_GROUPING)
    return (
        f'<section class="evidence-trace" data-evidence-trace="{EVIDENCE_TRACE_HOOK}" '
        'aria-labelledby="evidence-trace-heading">'
        '<h2 id="evidence-trace-heading">Conclusion → evidence → source trace / '
        '<span lang="zh-CN">结论 → 证据 → 来源追溯</span></h2>'
        "<p>Each step links only to what the owner published. A step that is not published is "
        f"shown as {MISSING}; that is not a failure and not proof of absence.</p>"
        '<ol class="trace-steps">'
        f'<li data-trace-step="conclusion"><strong>Conclusion</strong>: {conclusion} · '
        f"evidence level {escape(ledger.evidence_level.value.replace('_', ' '))} · "
        f"{_lineage_link(query_context, conclusion_id, 'Open lineage from this conclusion')}</li>"
        '<li data-trace-step="evidence"><strong>Evidence records</strong>'
        f"{_bounded(records, len(ledger.records), 'evidence records')}</li>"
        '<li data-trace-step="source"><strong>Sources</strong>'
        f"{_bounded(sources, len(ledger.sources), 'sources')}</li>"
        '<li data-trace-step="artifact"><strong>Artifacts</strong>'
        f"{_bounded(artifacts, len(ledger.artifacts), 'artifacts')}</li>"
        "</ol>"
        '<p class="evidence-trace-related">Related views: '
        f'<a href="{_attr(comparison)}">Evidence comparison</a> · '
        f'<a href="{_attr(grouping)}">Derived failure grouping</a></p>'
        f"{_selected_detail(view, model, query_context)}</section>"
    )


__all__ = ["EVIDENCE_TRACE_HOOK", "MAX_TRACE_ROWS", "MISSING", "render_evidence_trace"]
