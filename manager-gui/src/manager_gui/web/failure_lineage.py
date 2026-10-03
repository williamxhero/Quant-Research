"""Explicit failure/Memory associations; no discovery, dereferencing, or I/O.

The six traceability dimensions always appear, with Missing for unpublished
relationships. Declared lineage state and observed link coverage are separate:
a source's blocked/stale/partial declaration is never upgraded by available URLs.
Only public/fixture locators are clickable; local/private paths are not a fallback.
"""

# HTML fragments intentionally keep readable markup even when a line is long.
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from html import escape
from typing import cast
from urllib.parse import urlsplit

from ..models import SourceReference

LINEAGE_KINDS = ("campaign", "candidate", "run", "evidence", "artifact", "source_document")
_UNUSABLE = frozenset({"missing", "blocked", "integrity_failure", "api_unavailable"})


def text(value: object) -> str | None:
    """Accept source text, never coerce a boolean or number into an identity."""
    return value if isinstance(value, str) and value.strip() else None


def mapping(value: object) -> Mapping[str, object]:
    return cast(Mapping[str, object], value) if isinstance(value, Mapping) else {}


def sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, (Mapping, str)):
        return (value,)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return tuple(value)
    return ()


def first_text(item: Mapping[str, object], *keys: str) -> str | None:
    return next((value for key in keys if (value := text(item.get(key))) is not None), None)


def link_kind(value: str | None) -> str:
    """Recognize explicit owner record types, not labels or similar prose."""
    token = (value or "source").replace("-", "_")
    for kind in LINEAGE_KINDS:
        if token == kind or token.endswith(f".{kind}.v1"):
            return kind
    if token.endswith(".focused_formal_run.v1"):
        return "run"
    if token in {"document", "source_doc"}:
        return "source_document"
    return value or "source"


def _public_target(value: str | None) -> str | None:
    if value is None or any(ord(char) < 32 for char in value) or "\\" in value:
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme in {"https", "http"}:
        return value if parsed.netloc and not parsed.username and not parsed.password else None
    if parsed.scheme in {"fixture", "workspace", "artifact"}:
        return value
    if not parsed.scheme and value.startswith(("/?", "#")):
        return value
    return None


@dataclass(frozen=True, slots=True)
class FailureReference:
    kind: str
    record_id: str | None
    label: str
    locator: str | None = None
    source_id: str | None = None
    relation: str | None = None
    state: str | None = None

    @property
    def target(self) -> str | None:
        return None if self.state in _UNUSABLE else _public_target(self.locator)

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "record_id": self.record_id,
            "label": self.label,
            "source_id": self.source_id,
            "relation": self.relation,
            "state": self.state,
            "locator": self.locator,
            "target": self.target,
        }


def references(
    value: object,
    sources: Mapping[str, SourceReference],
    *,
    kind: str = "source",
    relation: str | None = None,
) -> tuple[FailureReference, ...]:
    result: list[FailureReference] = []
    raw_values = sequence(value)
    if isinstance(value, Mapping) and not any(
        key in value
        for key in ("record_id", "id", "source_id", "source_ref", "document_id", "locator", "href", "url")
    ):
        raw_values = tuple(
            {"label": key, **(raw if isinstance(raw, Mapping) else {"record_id": raw})}
            for key, raw in value.items()
        )
    for raw in raw_values:
        item = mapping(raw)
        record_id = first_text(item, "record_id", "id", "document_id") or text(raw)
        source_id = first_text(item, "source_id", "source_ref") or record_id
        source = sources.get(source_id or "")
        locator = first_text(item, "locator", "href", "url", "uri")
        result.append(
            FailureReference(
                kind=link_kind(first_text(item, "kind", "record_type", "source_kind") or kind),
                record_id=record_id or source_id,
                label=first_text(item, "label", "title") or record_id or source_id or "Missing",
                locator=locator or (source.locator if source is not None else None),
                source_id=source_id,
                relation=first_text(item, "relation", "relationship") or relation,
                state=first_text(item, "status", "state"),
            )
        )
    # Only exact repeated edges collapse; competing relationships/states survive.
    return tuple(dict.fromkeys(result))


@dataclass(frozen=True, slots=True)
class FailureLineage:
    associations: tuple[FailureReference, ...]
    sources: tuple[FailureReference, ...]
    edges: tuple[FailureReference, ...]
    conflicts: tuple[FailureReference, ...]
    supersedes: tuple[FailureReference, ...]
    declared_state: str | None = None
    reason: str | None = None

    @property
    def missing_kinds(self) -> tuple[str, ...]:
        return tuple(
            kind for kind in LINEAGE_KINDS
            if not any(link.kind == kind and link.target for link in self.associations)
        )

    @property
    def coverage(self) -> str:
        if not self.missing_kinds and all(link.target for link in self.edges):
            return "complete"
        return "partial" if any(
            link.target for link in (*self.associations, *self.sources, *self.edges)
        ) else "missing"

    def to_dict(self) -> dict[str, object]:
        return {
            "declared_state": self.declared_state,
            "coverage": self.coverage,
            "missing_kinds": list(self.missing_kinds),
            "reason": self.reason,
            **{
                key: [link.to_dict() for link in getattr(self, key)]
                for key in ("associations", "sources", "edges", "conflicts", "supersedes")
            },
        }


def failure_lineage(
    item: Mapping[str, object], sources: Mapping[str, SourceReference]
) -> FailureLineage:
    """Project explicitly supplied association IDs, typed refs, and lineage edges."""
    source_links = tuple(dict.fromkeys(
        link for key in ("references", "source_refs", "source_ref", "source_id")
        for link in references(item.get(key), sources)
    ))
    raw_lineage = item.get("lineage", item.get("lineage_refs"))
    metadata = mapping(raw_lineage)
    if metadata and any(key in metadata for key in ("links", "edges", "state", "status", "complete")):
        edges = references(metadata.get("links", metadata.get("edges")), sources)
        declared = first_text(metadata, "state", "status")
        if declared is None and isinstance(metadata.get("complete"), bool):
            declared = "complete" if metadata["complete"] else "partial"
    else:
        edges = references(raw_lineage, sources)
        declared = None
    associations: list[FailureReference] = []
    for kind in LINEAGE_KINDS:
        values = tuple(dict.fromkeys(
            link
            for key in (kind, f"{kind}_id", f"{kind}_ref", f"{kind}s")
            for link in references(item.get(key), sources, kind=kind)
        ))
        if kind == "candidate":
            subject = references(item.get("subject"), sources)
            values += tuple(link for link in subject if link.kind == kind)
        values += tuple(link for link in (*source_links, *edges) if link.kind == kind)
        associations.extend(dict.fromkeys(values))
    return FailureLineage(
        associations=tuple(associations),
        sources=source_links,
        edges=edges,
        conflicts=references(item.get("conflicts"), sources, relation="conflicts"),
        supersedes=references(item.get("supersedes"), sources, relation="supersedes"),
        declared_state=declared or first_text(item, "lineage_state", "lineage_status"),
        reason=first_text(metadata, "reason", "detail") or text(item.get("lineage_reason")),
    )


def render_references(links: Sequence[FailureReference], *, empty: str = "Missing") -> str:
    parts: list[str] = []
    for link in links:
        attrs = f'data-link-kind="{escape(link.kind, quote=True)}"'
        if link.relation:
            attrs += f' data-relation="{escape(link.relation, quote=True)}"'
        if link.state:
            attrs += f' data-link-state="{escape(link.state, quote=True)}"'
        label = escape(link.label)
        if link.target:
            parts.append(f'<a {attrs} href="{escape(link.target, quote=True)}">{label}</a>')
        else:
            state = link.state if link.state in _UNUSABLE else "Missing"
            parts.append(f'<span {attrs}>{label} — {escape(state)} / Unconfirmed link</span>')
    return " · ".join(parts) or f'<span class="failure-missing">{escape(empty)}</span>'


def render_failure_lineage(trace: FailureLineage) -> str:
    rows = "".join(
        f'<div data-association-kind="{kind}"><dt>{kind.replace("_", " ").title()}</dt>'
        f'<dd>{render_references(tuple(link for link in trace.associations if link.kind == kind))}</dd></div>'
        for kind in LINEAGE_KINDS
    )
    sections = "".join(
        f'<section data-lineage-relation="{key}"><h4>{label}</h4>'
        f'{render_references(getattr(trace, key), empty=empty)}</section>'
        for key, label, empty in (
            ("sources", "Source refs", "Missing source refs"),
            ("edges", "Declared lineage edges", "Missing lineage edges"),
            ("conflicts", "Conflicts", "None recorded; not proof of no conflicts"),
            ("supersedes", "Supersedes", "None recorded; no supersession inferred"),
        )
    )
    return (
        f'<section class="failure-lineage" data-lineage-coverage="{trace.coverage}" '
        f'data-lineage-state="{escape(trace.declared_state or "missing", quote=True)}">'
        '<h3>Lineage / traceability</h3>'
        f'<p>Declared state: {escape(trace.declared_state or "Missing")} · '
        f'Observed link coverage: {trace.coverage}. {escape(trace.reason or "")}</p>'
        f'<dl>{rows}</dl>{sections}</section>'
    )
