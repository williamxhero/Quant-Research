"""Request-local UI support using only the envelope already read by the app.

Pointers, supplied records and supplied originals are different capabilities.
No locator is fetched. The request context keeps all page families on the same
mechanism without adding fields to either published read-model contract.
"""
from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from html import escape

from ..models import ManagerReadModel, ReadModelStatus
from .i18n import Translator
from .locators import public_locator
from .navigation import query_values

# These are existing public payload containers, not an owner schema or a search
# through arbitrary nested configuration. Relationships are never inherited.
_CONTAINERS = frozenset({
    "records", "items", "objects", "sources", "documents", "source_documents",
    "artifacts", "sections", "chapters", "research_story", "story", "storyline",
    "intent", "research_intent", "hypothesis", "initial_hypothesis", "design",
    "research_design", "attempts", "runs", "evidence", "conclusions", "failures",
    "limitations", "follow_up", "events", "timeline", "nodes", "edges", "ledger",
    "evidence_ledger", "methods", "reports", "source_publication", "generated_artifact",
    "genome", "genomes", "revisions", "memories", "patterns", "groups", "hits",
    "results", "campaign", "study", "strategy_family",
})
_ID_FIELDS = ("record_id", "document_id", "artifact_id", "source_id", "id", "object_id", "uid")
_POINTER_FIELDS = frozenset({
    *_ID_FIELDS, "record_type", "type", "kind", "title", "name", "label", "author",
    "owner", "schema", "revision", "version", "locator", "url", "href", "uri",
    "source_ref", "source_refs", "source_ids", "source", "snapshot_token",
    "original_source_id", "original_snapshot_token", "available", "approved",
    "fabricated_example",
})


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _public_items(data: object) -> Iterator[Mapping[str, object]]:
    if isinstance(data, (list, tuple)):
        for item in data:
            yield from _public_items(item)
    elif isinstance(data, Mapping):
        if any(key in data for key in _ID_FIELDS):
            yield data
        for key in _CONTAINERS:
            if key in data:
                yield from _public_items(data[key])


def _ids(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Mapping):
        return tuple(value[key] for key in ("source_id", "id") if isinstance(value.get(key), str))
    if isinstance(value, (list, tuple)):
        return tuple(identifier for item in value for identifier in _ids(item))
    return ()


def _source_ids(record: Mapping[str, object]) -> tuple[str, ...]:
    return tuple(identifier for key in ("source_ref", "source_id", "source_refs", "source_ids")
                 for identifier in _ids(record.get(key)))


def _has_content(record: Mapping[str, object]) -> bool:
    return any(key not in _POINTER_FIELDS and value not in (None, "", [], {})
               for key, value in record.items())


@dataclass
class SourceSupport:
    model: ManagerReadModel
    query_context: str
    translator: Translator
    sample: bool = False
    entries: list[tuple[str, str, Mapping[str, object] | None]] = field(default_factory=list)
    items: tuple[Mapping[str, object], ...] = field(init=False)
    computations: dict[int, tuple[tuple[Mapping[str, object], ...], str, bool]] = field(default_factory=dict)

    def computation(
        self, inputs: tuple[Mapping[str, object], ...], filters: str, complete: bool
    ) -> str:
        entry = self.reference(self.translator.t("support.count_inputs"))
        self.computations[len(self.entries)] = (inputs, filters, complete)
        return entry.replace(self._t("gap_entry", name=self.translator.t("support.count_inputs")),
                             self._t("count_inputs"))

    def _computation_markup(self, index: int) -> str:
        inputs, filters, complete = self.computations[index]
        markup = self._sample(None)
        for key in ("count_unit", "count_rule", "count_dedup", "count_complete" if complete else "count_partial"):
            markup += f'<p>{self._t(key)}</p>'
        markup += f'<p>{self._t("filters", filters=filters)}</p>'
        markup += f'<h3>{self._t("all_inputs", n=len(inputs))}</h3>'
        markup += "<ol>" + "".join(
            f'<li><pre data-owner-text="true" translate="no">'
            f'{escape(json.dumps(dict(record), ensure_ascii=False, indent=2))}</pre></li>'
            for record in inputs
        ) + "</ol>"
        return markup

    def __post_init__(self) -> None:
        self.items = tuple(_public_items(self.model.data))

    def _t(self, key: str, **params: object) -> str:
        return escape(self.translator.t("support." + key, **params))

    def _sample(self, record: Mapping[str, object] | None) -> str:
        if self.sample or (record is not None and record.get("fabricated_example") is True):
            return f'<p class="sample-note">{escape(self.translator.t("plain.result.sample"))}</p>'
        return ""

    def reference(
        self, source_id: str, record: Mapping[str, object] | None = None,
        *, record_id: str | None = None,
    ) -> str:
        if record is None and record_id:
            matches = [item for item in self.items if record_id in (item.get(key) for key in _ID_FIELDS)]
            # Ambiguous identifiers cannot select an arbitrary record as support.
            if len(matches) == 1:
                candidate = matches[0]
                if source_id in _source_ids(candidate) or source_id == record_id:
                    record = candidate
        index = len(self.entries) + 1
        panel_id, trigger_id = f"support-{index}", f"support-trigger-{index}"
        self.entries.append((source_id, trigger_id, record))
        title = _text(record.get("title")) if record else None
        name = title or source_id or self.translator.t("support.unnamed")
        key = "open" if record and _has_content(record) else "gap_entry"
        return (
            f'<a id="{trigger_id}" href="#{panel_id}" data-source-support="{panel_id}" '
            f'aria-controls="{panel_id}">{self._t(key, name=name)}</a>'
        )

    def _originals(self, record: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
        identifier = _text(record.get("original_source_id"))
        if identifier is None:
            return ()
        return tuple(item for item in self.items if identifier in
                     (item.get(key) for key in ("source_id", "document_id", "artifact_id")))

    def _source_issues(self, original: Mapping[str, object], record: Mapping[str, object]) -> list[str]:
        issues = []
        if original.get("available") is False or original.get("approved") is False:
            issues.append("restricted")
        locator = _text(original.get("locator", original.get("source_locator")))
        if locator and public_locator(locator) is None:
            issues.append("unsafe")
        original_snapshot = original.get("snapshot_token")
        expected = record.get("original_snapshot_token")
        if original_snapshot is not None and (
            expected != original_snapshot or original_snapshot != self.model.snapshot_token
        ):
            issues.append("version_change")
        availability = original.get("availability")
        status = availability.get("status") if isinstance(availability, Mapping) else availability
        status = status or original.get("read_status") or original.get("verification_status")
        if status in {"blocked", "stale", "integrity_failure", "api_unavailable", "missing", "hash_mismatch"}:
            issues.append("source_failure")
        return issues

    def _original_markup(self, record: Mapping[str, object], panel_id: str) -> str:
        originals = self._originals(record)
        if not originals:
            return ""
        conflict = len(originals) > 1 or bool(record.get("conflicts"))
        parts = [f'<p class="support-impact">{self._t("conflict")}</p>'] if conflict else []
        for index, original in enumerate(originals, 1):
            text = _text(original.get("text", original.get("content", original.get("original_text"))))
            if text is None:
                parts.append(f'<p>{self._t("original_missing")}</p>')
                continue
            issues = self._source_issues(original, record)
            title = _text(original.get("title"))
            title_markup = (
                f'<h3 data-owner-text="true" translate="no">{escape(title)}</h3>'
                if title else f'<h3>{self._t("title_missing")}</h3>'
            )
            excerpt = _text(record.get("excerpt"))
            matching = (
                not conflict and not issues and self.usable(record)
                and excerpt is not None and excerpt in text
                and record.get("original_snapshot_token") == original.get("snapshot_token")
                == self.model.snapshot_token and self.model.snapshot_token is not None
            )
            related = (
                f'<h3>{self._t("excerpt")}</h3><blockquote data-owner-text="true" translate="no">'
                f'{escape(excerpt)}</blockquote>' if matching
                else f'<p>{self._t("unlocated")}</p>'
            )
            original_id = f"{panel_id}-original-{index}"
            impacts = "".join(f'<p class="support-impact">{self._t(issue)}</p>' for issue in issues)
            parts.append(
                f'{title_markup}{impacts}{related}<a href="#{original_id}" data-support-original>'
                f'{self._t("original")}</a><section id="{original_id}" tabindex="-1">'
                f'{self._sample(record) or self._sample(original)}<h3>{self._t("original")}</h3>'
                f'<pre data-owner-text="true" translate="no">{escape(text)}</pre></section>'
            )
        return "".join(parts)

    def usable(self, record: Mapping[str, object] | None = None) -> bool:
        query = query_values(self.query_context)
        requested = query.get("snapshot_token") or query.get("snapshot")
        return (
            self.model.availability.status is ReadModelStatus.KNOWN and not self.model.errors
            and (not requested or requested == self.model.snapshot_token)
            and (record is None or not record.get("conflicts"))
            and (record is None or record.get("snapshot_token") in (None, self.model.snapshot_token))
        )

    def impact(self, record: Mapping[str, object] | None = None) -> str:
        status = self.model.availability.status.value
        keys = {"blocked", "stale", "integrity_failure", "api_unavailable", "missing", "incomparable"}
        messages = []
        if status in keys:
            messages.append(self.translator.t("support.impact." + status))
        if self.model.errors:
            messages.append(self.translator.t("support.impact.errors"))
        if not self.model.availability.complete:
            messages.append(self.translator.t("support.impact.partial"))
        query = query_values(self.query_context)
        requested = query.get("snapshot_token") or query.get("snapshot")
        if requested and requested != self.model.snapshot_token:
            messages.append(self.translator.t("plain.result.snapshot_drift"))
        if record and record.get("conflicts"):
            messages.append(self.translator.t("support.conflict"))
        markup = "".join(f'<p class="support-impact">{escape(text)}</p>' for text in messages)
        if self.model.availability.reason:
            markup += f'<p data-owner-text="true" translate="no">{escape(self.model.availability.reason)}</p>'
        for error in self.model.errors:
            markup += f'<p data-owner-text="true" translate="no">{escape(error.code)}: {escape(error.message)}</p>'
        return markup

    def render(self, page: str) -> str:
        panels = []
        for index, (source_id, trigger_id, record) in enumerate(self.entries, 1):
            # Hidden legacy markup has separate, prefixed IDs. Do not make its
            # discarded support entries part of the visible reading experience.
            if f'id="{trigger_id}"' not in page:
                continue
            panel_id, title_id = f"support-{index}", f"support-{index}-title"
            title = _text(record.get("title")) if record else None
            heading = escape(title) if title else self._t("title", source=source_id)
            body = self._sample(record) + self.impact(record)
            has_record = record is not None and _has_content(record)
            key = "record_original" if record and self._originals(record) else "structured"
            body += f'<p>{self._t(key if has_record else "pointer")}</p>'
            if record is not None:
                body += self._original_markup(record, panel_id)
                body += (
                    f'<h3>{self._t("fields")}</h3><pre data-owner-text="true" translate="no">'
                    f'{escape(json.dumps(dict(record), ensure_ascii=False, indent=2))}</pre>'
                )
            if index in self.computations:
                body = self._computation_markup(index)
            panels.append(
                f'<section class="source-support" id="{panel_id}" tabindex="-1" '
                f'aria-labelledby="{title_id}"><h2 id="{title_id}">{heading}</h2>'
                f'{body}<a href="#{trigger_id}" data-support-close>{self._t("close")}</a></section>'
            )
        return "".join(panels)


_CURRENT: ContextVar[SourceSupport | None] = ContextVar("source_support", default=None)


@contextmanager
def support_scope(
    model: ManagerReadModel, query_context: str, translator: Translator, *, sample: bool = False
) -> Iterator[SourceSupport]:
    support = SourceSupport(model, query_context, translator, sample)
    token = _CURRENT.set(support)
    try:
        yield support
    finally:
        _CURRENT.reset(token)


def source_support_entry(
    source_id: str, *, record: Mapping[str, object] | None = None, record_id: str | None = None
) -> str | None:
    """Register a native entry in the current page; no source is fetched."""
    support = _CURRENT.get()
    return None if support is None else support.reference(source_id, record, record_id=record_id)


def source_support_computation(
    inputs: tuple[Mapping[str, object], ...], *, filters: str, complete: bool
) -> str:
    support = _CURRENT.get()
    return "" if support is None else support.computation(inputs, filters, complete)


def source_support_impact(record: Mapping[str, object] | None = None) -> str:
    support = _CURRENT.get()
    return "" if support is None else support.impact(record)


def source_support_usable(record: Mapping[str, object]) -> bool:
    support = _CURRENT.get()
    return True if support is None else support.usable(record)
