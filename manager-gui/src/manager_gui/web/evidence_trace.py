"""Conclusion -> evidence -> source/artifact -> lineage trace for the Evidence route."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import escape
from typing import TypeAlias

from ..models import ManagerReadModel
from .evidence import (
    _FIXTURE_TEXT_KEYS,
    ArtifactVerificationStatus,
    EvidenceArtifact,
    EvidenceKind,
    EvidenceLevel,
    EvidenceOutcome,
    EvidenceRecord,
    EvidenceSourceRef,
    EvidenceViewModel,
)
from .i18n import Translator
from .i18n.catalog.l4_evidence import page_translator
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


def _owner(value: str | None, translator: Translator, *, is_fixture: bool) -> str:
    if value is None:
        return escape(translator.t("evidence.not_recorded"))
    key = _FIXTURE_TEXT_KEYS.get(value) if is_fixture else None
    if key is not None:
        return escape(translator.t(key))
    return f'<span data-owner-text="true">{escape(value)}</span>'


def _label(
    value: EvidenceKind | EvidenceLevel | EvidenceOutcome | ArtifactVerificationStatus,
    translator: Translator,
) -> str:
    if isinstance(value, EvidenceKind):
        domain = "evidence_kind"
    elif isinstance(value, EvidenceLevel):
        domain = "evidence_level"
    elif isinstance(value, EvidenceOutcome):
        domain = "evidence_outcome"
    else:
        domain = "artifact_verification"
    if isinstance(value, EvidenceLevel):
        return translator.t(f"label.l4_evidence_level.{value.value}")
    return translator.label(domain, value.value)


class _TraceRenderer:
    def __init__(
        self,
        view: EvidenceViewModel,
        *,
        context: QueryContext,
        translator: Translator,
    ) -> None:
        self.view = view
        self.model = view.read_model
        self.context = context
        self.translator = translator
        self.is_fixture = any(
            ref.source_id == "evidence-fixture-source" for ref in self.model.source_refs
        )

    def missing(self, what: str, key: str) -> str:
        return (
            f'<span class="trace-missing" data-trace-missing="{_attr(key)}">{escape(what)} — '
            f"{escape(self.translator.t('evidence.missing_unconfirmed'))}</span>"
        )

    def lineage_link(self, lineage_id: str | None, label: str) -> str:
        if lineage_id is None:
            return self.missing(self.translator.t("trace.lineage"), "lineage")
        href = _cross_link(self.context, ViewId.LINEAGE, record_id=lineage_id)
        return (
            f'<a class="trace-lineage-link" data-lineage-id="{_attr(lineage_id)}" '
            f'href="{_attr(href)}">{escape(label)}</a>'
        )

    @staticmethod
    def source_item(source_id: str, locator: str | None, translator: Translator) -> str:
        target = public_locator(locator)
        source = f'<span data-owner-text="true" translate="no">{escape(source_id)}</span>'
        if target is not None:
            return (
                f'<a class="trace-source-link" data-source-id="{_attr(source_id)}" '
                f'href="{_attr(target)}">{source}</a>'
            )
        missing = _missing_static(source, translator, "source")
        return f'<span data-source-id="{_attr(source_id)}">{missing}</span>'

    def sources(self, refs: Sequence[EvidenceSourceRef]) -> str:
        if not refs:
            return self.missing(self.translator.t("trace.sources"), "source")
        items = "".join(
            f"<li>{self.source_item(ref.source_id, ref.locator, self.translator)}</li>"
            for ref in refs
        )
        return f"<ul>{items}</ul>"

    def artifact_name(self, artifact: EvidenceArtifact) -> str:
        target = public_locator(artifact.locator)
        name = _owner(artifact.name, self.translator, is_fixture=self.is_fixture)
        if target is not None:
            return f'<a class="trace-artifact-link" href="{_attr(target)}">{name}</a>'
        return f"{name} — {self.missing(self.translator.t('trace.artifact_locator'), 'artifact')}"

    def artifact_item(self, artifact: EvidenceArtifact) -> str:
        status = artifact.verification_status.value
        detail = _detail_link(self.context, artifact_id=artifact.artifact_id)
        lineage_id = _pointer(artifact.raw, "lineage_id", "lineageId")
        hash_value = (
            _owner(artifact.hash, self.translator, is_fixture=self.is_fixture)
            if artifact.hash
            else self.missing(self.translator.t("trace.hash"), "artifact")
        )
        verification = _label(artifact.verification_status, self.translator)
        details_label = escape(self.translator.t("trace.details"))
        lineage = self.lineage_link(
            lineage_id, self.translator.t("trace.open_lineage_artifact")
        )
        return (
            f'<li data-trace-artifact="{_attr(artifact.artifact_id)}" '
            f'data-verification-status="{_attr(status)}">{self.artifact_name(artifact)} · '
            f"{escape(self.translator.t('trace.verification'))} {verification} · "
            f"{escape(self.translator.t('trace.hash'))} {hash_value} · "
            f'<a class="trace-detail-link" href="{_attr(detail)}">{details_label}</a> · '
            f"{lineage}</li>"
        )

    def record_item(self, record: EvidenceRecord) -> str:
        detail = _detail_link(self.context, record_id=record.record_id)
        lineage_id = _pointer(record.raw, "lineage_id", "lineageId")
        status = _label(record.status, self.translator)
        lineage = self.lineage_link(
            lineage_id, self.translator.t("trace.open_lineage_record")
        )
        return (
            f'<li data-trace-record="{_attr(record.record_id)}" '
            f'data-evidence-kind="{record.evidence_kind.value}" '
            f'data-evidence-status="{record.status.value}">'
            f'<a class="trace-detail-link" href="{_attr(detail)}">'
            f"{_owner(record.label, self.translator, is_fixture=self.is_fixture)}</a> · "
            f"{_label(record.evidence_kind, self.translator)} · "
            f"{escape(self.translator.t('trace.status'))} {status} · {lineage}</li>"
        )

    def bounded(self, items: Sequence[str], total: int, noun_key: str) -> str:
        noun = self.translator.t(noun_key)
        if not items:
            return self.missing(self.translator.t("trace.no_noun_published", noun=noun), noun_key)
        more = ""
        if total > len(items):
            more_text = self.translator.t("trace.showing", shown=len(items), total=total, noun=noun)
            more = f"<p>{escape(more_text)}</p>"
        return f"<ul>{''.join(items)}</ul>{more}"

    def list_or_none(self, values: Sequence[str]) -> str:
        if not values:
            return escape(self.translator.t("trace.none_published"))
        return (
            "<ul>"
            + "".join(
                f"<li>{_owner(value, self.translator, is_fixture=self.is_fixture)}</li>"
                for value in values
            )
            + "</ul>"
        )

    def panel(self, kind: str, title: str, body: str, *, found: bool) -> str:
        heading = f"trace-detail-{kind}-heading"
        return (
            f'<section class="evidence-trace-detail" data-trace-detail="{kind}" '
            f'data-trace-found="{"true" if found else "false"}" aria-labelledby="{heading}">'
            f'<h3 id="{heading}">{escape(title)}</h3>{body}</section>'
        )

    def not_published(self, kind: str, title: str, value: str) -> str:
        body = f"<p>{self.translator.html('trace.not_published', value=value)}</p>"
        return self.panel(kind, title, body, found=False)

    @staticmethod
    def fact(label: str, value: str) -> str:
        return f"<div><dt>{escape(label)}</dt><dd>{value}</dd></div>"

    def record_detail(self, record_id: str) -> str:
        title = self.translator.t("trace.selected_record")
        record = next((item for item in self.view.records if item.record_id == record_id), None)
        if record is None:
            return self.not_published("record", title, record_id)
        lineage_id = _pointer(record.raw, "lineage_id", "lineageId")
        artifacts = "".join(self.artifact_item(artifact) for artifact in record.artifacts)
        artifact_cell = (
            f"<ul>{artifacts}</ul>"
            if artifacts
            else self.missing(self.translator.t("trace.artifacts"), "artifact")
        )
        body = (
            "<dl>"
            + self.fact(
                self.translator.t("trace.record"),
                f"{_owner(record.label, self.translator, is_fixture=self.is_fixture)} "
                f'(<span data-owner-text="true" translate="no">{escape(record.record_id)}</span>)',
            )
            + self.fact(
                self.translator.t("trace.evidence_class"),
                _label(record.evidence_kind, self.translator),
            )
            + self.fact(self.translator.t("trace.status"), _label(record.status, self.translator))
            + self.fact(
                self.translator.t("evidence.level"), _label(record.evidence_level, self.translator)
            )
            + self.fact(self.translator.t("trace.blockers"), self.list_or_none(record.blockers))
            + self.fact(
                self.translator.t("trace.incompatibilities"),
                self.list_or_none(record.incompatibilities),
            )
            + self.fact(self.translator.t("trace.sources"), self.sources(record.source_refs))
            + self.fact(self.translator.t("trace.artifacts"), artifact_cell)
            + self.fact(
                self.translator.t("trace.lineage"),
                self.lineage_link(lineage_id, self.translator.t("trace.open_lineage_record")),
            )
            + "</dl>"
        )
        return self.panel("record", title, body, found=True)

    def artifact_detail(self, artifact_id: str) -> str:
        title = self.translator.t("trace.selected_artifact")
        artifact = self.view.artifact(artifact_id)
        if artifact is None:
            return self.not_published("artifact", title, artifact_id)
        lineage_id = _pointer(artifact.raw, "lineage_id", "lineageId")
        body = (
            "<dl>"
            + self.fact(self.translator.t("trace.artifact"), self.artifact_name(artifact))
            + self.fact(
                self.translator.t("evidence.verification_status"),
                _label(artifact.verification_status, self.translator),
            )
            + self.fact(
                self.translator.t("evidence.verification_detail"),
                _owner(artifact.verification_detail, self.translator, is_fixture=self.is_fixture),
            )
            + self.fact(
                self.translator.t("trace.hash"),
                _owner(artifact.hash, self.translator, is_fixture=self.is_fixture),
            )
            + self.fact(
                self.translator.t("trace.producer"),
                _owner(artifact.producer, self.translator, is_fixture=self.is_fixture),
            )
            + self.fact(
                self.translator.t("trace.runtime_version"),
                _owner(artifact.runtime_version, self.translator, is_fixture=self.is_fixture),
            )
            + self.fact(
                self.translator.t("trace.data_version"),
                _owner(artifact.data_version, self.translator, is_fixture=self.is_fixture),
            )
            + self.fact(self.translator.t("trace.sources"), self.sources(artifact.source_refs))
            + self.fact(
                self.translator.t("trace.lineage"),
                self.lineage_link(lineage_id, self.translator.t("trace.open_lineage_artifact")),
            )
            + "</dl>"
        )
        return self.panel("artifact", title, body, found=True)

    def source_detail(self, source_id: str) -> str:
        title = self.translator.t("trace.selected_source")
        ledger_ref = next((ref for ref in self.view.sources if ref.source_id == source_id), None)
        envelope_ref = next(
            (ref for ref in self.model.source_refs if ref.source_id == source_id), None
        )
        if ledger_ref is None and envelope_ref is None:
            return self.not_published("source", title, source_id)
        refs = [ref for ref in (ledger_ref, envelope_ref) if ref is not None]
        locator = next((ref.locator for ref in refs if ref.locator), None)
        owner = next((ref.owner for ref in refs if ref.owner), None)
        kind = next((ref.kind for ref in refs if ref.kind), None)
        body = (
            "<dl>"
            + self.fact(
                self.translator.t("trace.source"),
                self.source_item(source_id, locator, self.translator),
            )
            + self.fact(
                self.translator.t("trace.owner"),
                _owner(owner, self.translator, is_fixture=self.is_fixture),
            )
            + self.fact(
                self.translator.t("trace.kind"),
                _owner(kind, self.translator, is_fixture=self.is_fixture),
            )
            + "</dl>"
        )
        return self.panel("source", title, body, found=True)

    def selected_detail(self) -> str:
        values = query_values(self.context)
        panels: list[str] = []
        if (record_id := _text(values.get("record_id"))) is not None:
            panels.append(self.record_detail(record_id))
        if (artifact_id := _text(values.get("artifact_id"))) is not None:
            panels.append(self.artifact_detail(artifact_id))
        if (source_id := _text(values.get("source_id"))) is not None:
            panels.append(self.source_detail(source_id))
        return "".join(panels)

    def render(self) -> str:
        ledger = self.view.ledger
        conclusion_id = _pointer(ledger.raw, "conclusion_id", "conclusionId")
        conclusion = (
            _owner(ledger.conclusion, self.translator, is_fixture=self.is_fixture)
            if ledger.conclusion
            else self.missing(self.translator.t("trace.conclusion"), "conclusion")
        )
        records = [self.record_item(record) for record in ledger.records[:MAX_TRACE_ROWS]]
        sources = [
            f"<li>{self.source_item(ref.source_id, ref.locator, self.translator)}</li>"
            for ref in ledger.sources[:MAX_TRACE_ROWS]
        ]
        artifacts = [self.artifact_item(item) for item in ledger.artifacts[:MAX_TRACE_ROWS]]
        comparison = _cross_link(self.context, ViewId.EVIDENCE_COMPARISON)
        grouping = _cross_link(self.context, ViewId.FAILURE_GROUPING)
        t = self.translator.t
        return (
            f'<section class="evidence-trace" data-evidence-trace="{EVIDENCE_TRACE_HOOK}" '
            'aria-labelledby="evidence-trace-heading">'
            f'<h2 id="evidence-trace-heading">{escape(t("trace.title"))}</h2>'
            f"<p>{escape(t('trace.intro'))}</p>"
            '<ol class="trace-steps">'
            f'<li data-trace-step="conclusion"><strong>{escape(t("trace.conclusion"))}'
            f"</strong>: {conclusion} · {escape(t('trace.evidence_level'))} "
            f"{_label(ledger.evidence_level, self.translator)} · "
            f"{self.lineage_link(conclusion_id, t('trace.open_lineage_conclusion'))}</li>"
            f'<li data-trace-step="evidence"><strong>{escape(t("trace.evidence_records"))}</strong>'
            f"{self.bounded(records, len(ledger.records), 'trace.evidence_records')}</li>"
            f'<li data-trace-step="source"><strong>{escape(t("trace.sources"))}</strong>'
            f"{self.bounded(sources, len(ledger.sources), 'trace.sources')}</li>"
            f'<li data-trace-step="artifact"><strong>{escape(t("trace.artifacts"))}</strong>'
            f"{self.bounded(artifacts, len(ledger.artifacts), 'trace.artifacts')}</li>"
            "</ol>"
            f'<p class="evidence-trace-related">{escape(t("trace.related_views"))}: '
            f'<a href="{_attr(comparison)}">{escape(t("trace.evidence_comparison"))}</a> · '
            f'<a href="{_attr(grouping)}">{escape(t("trace.derived_grouping"))}</a></p>'
            f"{self.selected_detail()}</section>"
        )


def _missing_static(value: str, translator: Translator, key: str) -> str:
    return (
        f'<span class="trace-missing" data-trace-missing="{_attr(key)}">{value} — '
        f"{escape(translator.t('evidence.missing_unconfirmed'))}</span>"
    )


def render_evidence_trace(
    model: ManagerReadModel,
    *,
    query_context: QueryContext = None,
    translator: Translator | None = None,
) -> str:
    """Render the trace and selected-detail panels from one Evidence envelope."""

    view = EvidenceViewModel.from_read_model(model)
    return _TraceRenderer(
        view,
        context=query_context,
        translator=page_translator(translator),
    ).render()


__all__ = ["EVIDENCE_TRACE_HOOK", "MAX_TRACE_ROWS", "MISSING", "render_evidence_trace"]
