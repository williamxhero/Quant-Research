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
from .material_reading import MATERIAL_RECORD_KINDS, render_material_details
from .navigation import query_values

# These are existing public payload containers, not an owner schema or a search
# through arbitrary nested configuration. Relationships are never inherited.
_CONTAINERS = frozenset(
    {
        "records",
        "items",
        "objects",
        "sources",
        "documents",
        "source_documents",
        "artifacts",
        "sections",
        "chapters",
        "research_story",
        "story",
        "storyline",
        "intent",
        "research_intent",
        "hypothesis",
        "initial_hypothesis",
        "design",
        "research_design",
        "attempts",
        "runs",
        "evidence",
        "conclusions",
        "failures",
        "limitations",
        "follow_up",
        "events",
        "timeline",
        "nodes",
        "edges",
        "ledger",
        "evidence_ledger",
        "methods",
        "reports",
        "source_publication",
        "generated_artifact",
        "genome",
        "genomes",
        "revisions",
        "memories",
        "patterns",
        "groups",
        "hits",
        "results",
        "campaign",
        "study",
        "strategy_family",
    }
)
_ID_FIELDS = ("record_id", "document_id", "artifact_id", "source_id", "id", "object_id", "uid")
_POINTER_FIELDS = frozenset(
    {
        *_ID_FIELDS,
        "record_type",
        "type",
        "kind",
        "title",
        "name",
        "label",
        "author",
        "owner",
        "schema",
        "revision",
        "version",
        "locator",
        "url",
        "href",
        "uri",
        "source_ref",
        "source_refs",
        "source_ids",
        "source",
        "snapshot_token",
        "original_source_id",
        "original_snapshot_token",
        "available",
        "approved",
        "fabricated_example",
    }
)


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
    return tuple(
        identifier
        for key in ("source_ref", "source_id", "source_refs", "source_ids")
        for identifier in _ids(record.get(key))
    )


def _has_content(record: Mapping[str, object]) -> bool:
    return any(
        key not in _POINTER_FIELDS and value not in (None, "", [], {})
        for key, value in record.items()
    )


@dataclass
class SourceSupport:
    model: ManagerReadModel
    query_context: str
    translator: Translator
    sample: bool = False
    entries: list[tuple[str, Mapping[str, object] | None]] = field(default_factory=list)
    explanations: dict[int, str] = field(default_factory=dict)
    fabricated_entries: set[int] = field(default_factory=set)
    display_names: dict[int, str] = field(default_factory=dict)
    items: tuple[Mapping[str, object], ...] = field(init=False)
    computations: dict[int, tuple[tuple[Mapping[str, object], ...], str, bool, str | None]] = field(
        default_factory=dict
    )
    matched_fields: dict[int, tuple[tuple[str, str], ...]] = field(default_factory=dict)

    def computation(
        self, inputs: tuple[Mapping[str, object], ...], filters: str, complete: bool,
        description: str | None = None,
    ) -> str:
        index = len(self.entries) + 1
        panel_id, trigger_id = f"support-{index}", f"support-trigger-{index}"
        self.entries.append((trigger_id, None))
        self.computations[index] = (inputs, filters, complete, description)
        return (
            f'<a id="{trigger_id}" href="#{panel_id}" data-source-support="{panel_id}" '
            f'aria-controls="{panel_id}">{self._t("count_inputs")}</a>'
        )

    def _computation_markup(self, index: int) -> str:
        inputs, filters, complete, description = self.computations[index]
        markup = self._sample(None) + self.impact()
        if description is None:
            for key in ("count_unit", "count_rule", "count_dedup"):
                markup += f"<p>{self._t(key)}</p>"
        else:
            markup += f"<p>{escape(description)}</p>"
        markup += f'<p>{self._t("count_complete" if complete else "count_partial")}</p>'
        markup += (
            f"<p>{self._t('query')}</p>"
            f'<pre data-owner-text="true" translate="no">{escape(filters)}</pre>'
        )
        markup += f"<h3>{self._t('all_inputs', n=len(inputs))}</h3>"
        markup += (
            "<ol>"
            + "".join(
                f'<li>{self._sample(record)}<pre data-owner-text="true" translate="no">'
                f"{escape(json.dumps(dict(record), ensure_ascii=False, indent=2))}</pre></li>"
                for record in inputs
            )
            + "</ol>"
        )
        return markup

    def __post_init__(self) -> None:
        self.items = tuple(_public_items(self.model.data))

    def _t(self, key: str, **params: object) -> str:
        return escape(self.translator.t("support." + key, **params))

    def _sample(
        self, record: Mapping[str, object] | None, *, fabricated_example: bool = False
    ) -> str:
        if (
            self.sample
            or fabricated_example
            or (record is not None and record.get("fabricated_example") is True)
        ):
            return f'<p class="sample-note">{escape(self.translator.t("plain.result.sample"))}</p>'
        return ""

    def reference(
        self,
        source_id: str,
        record: Mapping[str, object] | None = None,
        *,
        record_id: str | None = None,
        fields: tuple[tuple[str, str], ...] = (),
        explanation: str | None = None,
        fabricated_example: bool = False,
        display_name: str | None = None,
    ) -> str:
        if record is None and record_id:
            matches = [
                item for item in self.items if record_id in (item.get(key) for key in _ID_FIELDS)
            ]
            # Ambiguous identifiers cannot select an arbitrary record as support.
            if len(matches) == 1:
                candidate = matches[0]
                if source_id in _source_ids(candidate) or source_id == record_id:
                    record = candidate
        if record is None and record_id is None:
            matches = [item for item in self.items if item.get("source_id") == source_id]
            if len(matches) == 1:
                record = matches[0]
        index = len(self.entries) + 1
        panel_id, trigger_id = f"support-{index}", f"support-trigger-{index}"
        self.entries.append((trigger_id, record))
        self.matched_fields[index] = fields
        if explanation is not None:
            # GUI-rendered, escaped, ID-free prose; the original supplied mapping remains below.
            self.explanations[index] = explanation
        if fabricated_example:
            self.fabricated_entries.add(index)
        if (name := _text(display_name)) is not None:
            self.display_names[index] = name
        title = self.display_names.get(index) or (_text(record.get("title")) if record else None)
        has_content = record is not None and _has_content(record)
        if title is None:
            label = self._t("open_unnamed" if has_content else "gap_unnamed")
        else:
            label = self._t("open" if has_content else "gap_entry", name=title)
            label = label.replace(
                escape(title),
                f'<span data-owner-text="true" translate="no">{escape(title)}</span>',
                1,
            )
        return (
            f'<a id="{trigger_id}" href="#{panel_id}" data-source-support="{panel_id}" '
            f'aria-controls="{panel_id}">{label}</a>'
        )

    def _originals(self, record: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
        identifier = _text(record.get("original_source_id"))
        if identifier is None:
            return ()
        return tuple(
            item
            for item in self.items
            if identifier in (item.get(key) for key in ("source_id", "document_id", "artifact_id"))
        )

    def _read_issues(self, original: Mapping[str, object], expected: object) -> list[str]:
        issues = []
        if original.get("conflicts"):
            issues.append("conflict")
        if original.get("available") is False or original.get("approved") is False:
            issues.append("restricted")
        locators = (
            _text(original.get(key))
            for key in ("locator", "source_locator", "source_url", "url", "href", "uri",
                        "artifact_locator")
        )
        if any(locator and public_locator(locator) is None for locator in locators):
            issues.append("unsafe")
        revision = original.get("source_revision")
        if revision is not None:
            source_id = original.get("source_ref", original.get("source_id"))
            refs = tuple(ref for ref in self.model.source_refs if ref.source_id == source_id)
            if len(refs) != 1 or refs[0].revision != revision:
                issues.append("version_change")
        if original.get("original_source_id"):
            linked = self._originals(original)
            if not linked or any(
                not _text(item.get("text", item.get("content", item.get("original_text"))))
                for item in linked
            ):
                issues.append("original_missing")
            expected_revision = original.get("original_source_revision")
            if expected_revision is not None and any(
                item.get("source_revision") != expected_revision for item in linked
            ):
                issues.append("version_change")
        original_snapshot = original.get("snapshot_token")
        if original_snapshot is not None and (
            expected != original_snapshot or original_snapshot != self.model.snapshot_token
        ):
            issues.append("version_change")
        availability = original.get("availability")
        if isinstance(availability, Mapping) and availability.get("complete") is False:
            issues.append("impact.partial")
        status = availability.get("status") if isinstance(availability, Mapping) else availability
        source_status = original.get("status")
        if not isinstance(source_status, str) or source_status not in {
            "blocked", "stale", "integrity_failure", "api_unavailable", "missing", "incomparable"
        }:
            source_status = None
        statuses = tuple(
            value.get("status", value.get("state", value.get("result")))
            if isinstance(value, Mapping) else value
            for value in (
                status, source_status, original.get("read_status"),
                original.get("verification_status"), original.get("verify_status"),
                original.get("verify"), original.get("verification"),
            )
        )
        failures = {
            "incomparable",
            "blocked",
            "stale",
            "integrity_failure",
            "api_unavailable",
            "missing",
            "hash_mismatch",
            "digest_mismatch",
            "invalid",
            "fail",
            "failed",
            "failure",
        }
        if any(
            isinstance(value, str) and value.strip().lower().replace("-", "_") in failures
            for value in statuses
        ):
            issues.append("source_failure")
        return issues

    def _original_markup(
        self, record: Mapping[str, object], panel_id: str, *, fabricated_example: bool = False
    ) -> str:
        originals = self._originals(record)
        if not originals:
            return ""
        conflict = (
            len(originals) > 1
            or bool(record.get("conflicts"))
            or any(original.get("conflicts") for original in originals)
        )
        parts = [f'<p class="support-impact">{self._t("conflict")}</p>'] if conflict else []
        for index, original in enumerate(originals, 1):
            issues = self._read_issues(original, record.get("original_snapshot_token"))
            if issues:
                parts.extend(f'<p class="support-impact">{self._t(issue)}</p>' for issue in issues)
            text = _text(
                original.get("text", original.get("content", original.get("original_text")))
            )
            if text is None:
                parts.append(f"<p>{self._t('original_missing')}</p>")
                continue
            title = _text(original.get("title"))
            title_markup = (
                f'<h3 data-owner-text="true" translate="no">{escape(title)}</h3>'
                if title
                else f"<h3>{self._t('title_missing')}</h3>"
            )
            if issues:
                sample = self._sample(
                    record, fabricated_example=fabricated_example
                ) or self._sample(original)
                parts.append(
                    f'{title_markup}<p>{self._t("unverified_content")}</p>'
                    f'{sample}'
                    f'<pre data-owner-text="true" translate="no">{escape(text)}</pre>'
                )
                continue
            excerpt = _text(record.get("excerpt"))
            matching = (
                not conflict
                and not issues
                and self.usable(record)
                and excerpt is not None
                and excerpt in text
                and record.get("original_snapshot_token")
                == original.get("snapshot_token")
                == self.model.snapshot_token
                and self.model.snapshot_token is not None
            )
            related = (
                f'<h3>{self._t("excerpt")}</h3><blockquote data-owner-text="true" translate="no">'
                f"{escape(excerpt)}</blockquote>"
                if matching and excerpt is not None
                else f"<p>{self._t('unlocated')}</p>"
            )
            original_id = f"{panel_id}-original-{index}"
            sample = self._sample(
                record, fabricated_example=fabricated_example
            ) or self._sample(original)
            impacts = "".join(f'<p class="support-impact">{self._t(issue)}</p>' for issue in issues)
            parts.append(
                f'{title_markup}{impacts}{related}<a href="#{original_id}" data-support-original>'
                f'{self._t("original")}</a><section id="{original_id}" tabindex="-1">'
                f"{sample}<h3>{self._t('original')}</h3>"
                f'<pre data-owner-text="true" translate="no">{escape(text)}</pre></section>'
            )
        return "".join(parts)

    def usable(
        self, record: Mapping[str, object] | None = None, *, require_complete: bool = False
    ) -> bool:
        query = query_values(self.query_context)
        requested = query.get("snapshot_token") or query.get("snapshot")
        return (
            self.model.availability.status is ReadModelStatus.KNOWN
            and not self.model.errors
            and (not requested or requested == self.model.snapshot_token)
            and (record is None or not any(
                issue != "impact.partial" or require_complete
                for issue in self._read_issues(record, self.model.snapshot_token)
            ))
            and (record is None or len(self._originals(record)) <= 1)
            and (
                record is None
                or not any(
                    issue != "impact.partial" or require_complete
                    for original in self._originals(record)
                    for issue in self._read_issues(original, record.get("original_snapshot_token"))
                )
            )
        )

    def impact(self, record: Mapping[str, object] | None = None) -> str:
        status = self.model.availability.status.value
        keys = {
            "blocked",
            "stale",
            "integrity_failure",
            "api_unavailable",
            "missing",
            "incomparable",
        }
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
        if record is not None:
            messages.extend(
                self.translator.t("support." + issue)
                for issue in self._read_issues(record, self.model.snapshot_token)
            )
            originals = self._originals(record)
            if len(originals) > 1:
                messages.append(self.translator.t("support.conflict"))
            for original in originals:
                messages.extend(
                    self.translator.t("support." + issue)
                    for issue in self._read_issues(original, record.get("original_snapshot_token"))
                )
        markup = "".join(f'<p class="support-impact">{escape(text)}</p>' for text in messages)
        if self.model.availability.reason:
            markup += (
                '<p data-owner-text="true" translate="no">'
                f"{escape(self.model.availability.reason)}</p>"
            )
        for error in self.model.errors:
            markup += (
                '<p data-owner-text="true" translate="no">'
                f"{escape(error.code)}: {escape(error.message)}</p>"
            )
        return markup

    def render(self, page: str) -> str:
        panels = []
        for index, (trigger_id, record) in enumerate(self.entries, 1):
            # Hidden legacy markup has separate, prefixed IDs. Do not make its
            # discarded support entries part of the visible reading experience.
            if f'id="{trigger_id}"' not in page:
                continue
            panel_id, title_id = f"support-{index}", f"support-{index}-title"
            title = self.display_names.get(index) or (
                _text(record.get("title")) if record else None
            )
            heading = (
                f'<span data-owner-text="true" translate="no">{escape(title)}</span>'
                if title
                else self._t("heading_unnamed")
            )
            fabricated_example = index in self.fabricated_entries
            body = (
                self._sample(record, fabricated_example=fabricated_example)
                + self.impact(record) + self.explanations.get(index, "")
            )
            has_record = record is not None and _has_content(record)
            key = (
                "record_original" if record and self._originals(record)
                else "record_content" if record and any(
                    _text(record.get(name)) for name in ("content", "text", "original_text")
                )
                else "structured"
            )
            body += f"<p>{self._t(key if has_record else 'pointer')}</p>"
            if record is not None:
                located = tuple(
                    (name, label) for name, label in self.matched_fields.get(index, ())
                    if name in record
                )
                if located:
                    body += f"<h3>{escape(self.translator.t('reader.search.content_heading'))}</h3>"
                    for name, label in located:
                        content = json.dumps(record[name], ensure_ascii=False)
                        body += (
                            f"<h4>{escape(label)}</h4>"
                            f'<pre data-owner-text="true" translate="no">{escape(content)}</pre>'
                        )
                record_type = record.get("record_type")
                if "document_type" in record or (
                    isinstance(record_type, str) and record_type in MATERIAL_RECORD_KINDS
                ):
                    body += render_material_details(record, self.translator)
                body += self._original_markup(
                    record, panel_id, fabricated_example=fabricated_example
                )
                body += (
                    f'<h3>{self._t("fields")}</h3><pre data-owner-text="true" translate="no">'
                    f"{escape(json.dumps(dict(record), ensure_ascii=False, indent=2))}</pre>"
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
    model: ManagerReadModel,
    query_context: str,
    translator: Translator,
    *,
    sample: bool = False,
    active: bool = True,
) -> Iterator[SourceSupport]:
    support = SourceSupport(model, query_context, translator, sample)
    token = _CURRENT.set(support if active else None)
    try:
        yield support
    finally:
        _CURRENT.reset(token)


@contextmanager
def suspend_source_support() -> Iterator[None]:
    token = _CURRENT.set(None)
    try:
        yield
    finally:
        _CURRENT.reset(token)


def source_support_entry(
    source_id: str,
    *,
    record: Mapping[str, object] | None = None,
    record_id: str | None = None,
    fields: tuple[tuple[str, str], ...] = (),
    explanation: str | None = None,
    fabricated_example: bool = False,
    display_name: str | None = None,
) -> str | None:
    """Register a native entry in the current page; no source is fetched."""
    support = _CURRENT.get()
    return (
        None
        if support is None
        else support.reference(
            source_id,
            record,
            record_id=record_id,
            fields=fields,
            explanation=explanation,
            fabricated_example=fabricated_example,
            display_name=display_name,
        )
    )


def source_support_computation(
    inputs: tuple[Mapping[str, object], ...], *, filters: str, complete: bool,
    description: str | None = None,
) -> str:
    support = _CURRENT.get()
    return "" if support is None else support.computation(inputs, filters, complete, description)


def source_support_impact(
    record: Mapping[str, object] | None = None, *, require_original: bool = False,
) -> str:
    support = _CURRENT.get()
    if support is None:
        return ""
    markup = support.impact(record)
    if require_original and record is not None and not _original_supplied(support, record):
        markup += f'<p class="support-impact">{support._t("original_missing")}</p>'
    return markup


def _original_supplied(support: SourceSupport, record: Mapping[str, object]) -> bool:
    if _text(record.get("original_source_id")) is None:
        return True
    originals = support._originals(record)
    return bool(originals) and all(
        _text(item.get("text", item.get("content", item.get("original_text")))) is not None
        for item in originals
    )


def source_support_usable(
    record: Mapping[str, object], *, require_complete: bool = False,
) -> bool:
    support = _CURRENT.get()
    return support is None or (
        (not require_complete or (
            support.model.availability.complete and _original_supplied(support, record)
        )) and support.usable(record, require_complete=require_complete)
    )
