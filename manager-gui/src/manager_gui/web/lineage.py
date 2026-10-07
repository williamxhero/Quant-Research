"""Bounded, read-only Lineage graph and table view (Manager GUI S4-T2).

:func:`render_lineage_view` accepts either a ``ManagerReadModel`` or an object
exposing only the public ``read(resource, snapshot_token=...)`` seam.  The
envelope's ``data`` is an explicit, owner-published lineage page::

    {"schema": "manager-gui.lineage.v1", "root": "<record id>",
     "nodes": [{"id", "record_type", "label", "status", "hash", "verified_hash",
                "as_of", "snapshot_token", "source_refs", "derivation"}],
     "edges": [{"id", "source", "target", "relation", "source_refs", "as_of"}],
     "pagination": {"cursor", "next_cursor", "has_more", "cursor_state",
                    "snapshot_token", "complete"},
     "content_hash": "sha256:..."}

An edge reads ``source --relation--> target`` in the direction value flows:
``upstream`` follows edges backwards towards origins, ``downstream`` follows
them forwards towards dependants, and ``both`` ignores edge direction.

The module only projects an already-published page.  It never discovers
records, scans paths, opens SQLite or the filesystem, dereferences a locator,
recomputes owner facts, or exposes a mutation.  An expired cursor, snapshot
drift, an unknown schema or record type, a hash mismatch, an unusable source
status, a dangling edge on a complete page, or an unbounded page all fail
closed: no graph or table is shown for data that cannot be trusted.  A page
with further owner pages stays ``partial``: absence of a path or of a
connection is then reported as not established, never as proven.  The shell
route is intentionally owned by the S4 integration slice; the hook is
:func:`render_lineage_view`.
"""

# HTML fragments intentionally keep readable markup even when a line is long.
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from html import escape
from typing import TypeAlias, cast
from urllib.parse import parse_qsl, urlsplit

from ..models import (
    DERIVATION_KINDS,
    Availability,
    Derivation,
    JSONValue,
    ManagerReadModel,
    ReadModelError,
    ReadModelStatus,
    SourceReference,
)
from ..provider import ManagerDataProvider
from .i18n import CatalogError, Translator, merge
from .i18n.catalog import CATALOG
from .i18n.catalog.l4_lineage import ENTRIES as LINEAGE_CATALOG
from .locators import public_locator
from .navigation import PageWindow, context_link, query_values
from .source_support import source_support_entry, suspend_source_support
from .status import render_operational_state, render_status_block

LINEAGE_RESOURCE = "lineage"
LINEAGE_ROUTE = "lineage"
LINEAGE_INTEGRATION_HOOK = "lineage-view"
LINEAGE_INTEGRATION_HOOK_PATH = "manager_gui.web.lineage.render_lineage_view"
LINEAGE_SCHEMA = "manager-gui.lineage.v1"
SUPPORTED_LINEAGE_SCHEMAS: tuple[str, ...] = (
    LINEAGE_SCHEMA,
    "lineage.v1",
    "manager-gui.lineage.v0",
    "lineage",
)

DEFAULT_DEPTH = 2
MAX_DEPTH = 6
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
MAX_NODES = 500
MAX_EDGES = 2000
NOT_RECORDED = "Missing / Unconfirmed"

QueryContext: TypeAlias = str | Mapping[str, object] | None


@dataclass(frozen=True, slots=True)
class LineageQueryNote:
    key: str
    params: tuple[tuple[str, str | int], ...]


class LineageDirection(StrEnum):
    UPSTREAM = "upstream"
    DOWNSTREAM = "downstream"
    BOTH = "both"


class LineageRecordType(StrEnum):
    """Typed lineage nodes used by the published Manager GUI read seam."""

    CONCLUSION = "conclusion"
    EVIDENCE = "evidence"
    ARTIFACT = "artifact"
    GENOME = "genome"
    MEMORY = "memory"
    MEMORY_ENTRY = "memory_entry"
    RUN = "run"
    CAMPAIGN = "campaign"
    CANDIDATE = "candidate"
    SOURCE_DOCUMENT = "source_document"
    DOCUMENT = "document"
    STRATEGY = "strategy"
    STRATEGY_FAMILY = "strategy_family"
    STUDY = "study"
    HYPOTHESIS = "hypothesis"
    FAILURE = "failure"
    PATTERN = "pattern"
    QUALIFICATION = "qualification"
    REPLICATION = "replication"
    REVALIDATION = "revalidation"


class LineageRelation(StrEnum):
    """Typed lineage edges, read as ``source RELATION target``."""

    PRODUCES = "produces"
    SUPPORTS = "supports"
    INFORMS = "informs"
    DERIVES = "derives"
    DERIVED_FROM = "derived_from"
    SUPERSEDES = "supersedes"
    DOCUMENTS = "documents"
    CITES = "cites"
    REFERENCES = "references"
    CONTAINS = "contains"
    DEPENDS_ON = "depends_on"
    EXECUTES = "executes"
    GENERATED = "generated"
    VALIDATES = "validates"
    RECORDS = "records"
    ASSOCIATED_WITH = "associated_with"


class LineageState(StrEnum):
    READY = "ready"
    PARTIAL = "partial"
    EMPTY = "empty"
    FAIL_CLOSED = "fail-closed"


class LineagePathState(StrEnum):
    """Whether a shortest evidence path was found, ruled out, or not established."""

    FOUND = "found"
    NOT_FOUND = "not-found"
    NOT_ESTABLISHED = "not-established"
    NOT_APPLICABLE = "not-applicable"


class LineageFailure(StrEnum):
    CURSOR_EXPIRED = "cursor_expired"
    CURSOR_MISMATCH = "cursor_mismatch"
    SNAPSHOT_DRIFT = "snapshot_drift"
    UNKNOWN_SCHEMA = "unknown_schema"
    HASH_MISMATCH = "hash_mismatch"
    INTEGRITY_FAILURE = "integrity_failure"
    SOURCE_UNAVAILABLE = "source_unavailable"
    SOURCE_BLOCKED = "source_blocked"
    INCOMPARABLE = "incomparable"
    INVALID_PAYLOAD = "invalid_payload"
    BOUND_EXCEEDED = "bound_exceeded"
    ROOT_NOT_FOUND = "root_not_found"


class LineageFixtureState(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    EMPTY = "empty"
    CURSOR_EXPIRED = "cursor_expired"
    SNAPSHOT_DRIFT = "snapshot_drift"
    UNKNOWN_SCHEMA = "unknown_schema"
    HASH_MISMATCH = "hash_mismatch"
    API_UNAVAILABLE = "api_unavailable"
    LARGE = "large"


LINEAGE_DIRECTIONS: tuple[LineageDirection, ...] = tuple(LineageDirection)
LINEAGE_RECORD_TYPES: tuple[LineageRecordType, ...] = tuple(LineageRecordType)
LINEAGE_RELATIONS: tuple[LineageRelation, ...] = tuple(LineageRelation)
LINEAGE_FIXTURE_STATES: tuple[str, ...] = tuple(state.value for state in LineageFixtureState)


class LineageIntegrityError(ValueError):
    """A fail-closed lineage condition; never swallowed into partial output."""

    def __init__(self, code: LineageFailure, detail: str) -> None:
        super().__init__(f"{code.value}: {detail}")
        self.code = code
        self.detail = detail


# --- value helpers -------------------------------------------------------------


def _text(value: object) -> str | None:
    """Accept source text only; numbers and booleans never become identities."""

    return value.strip() if isinstance(value, str) and value.strip() else None


def _mapping(value: object) -> Mapping[str, object] | None:
    return cast(Mapping[str, object], value) if isinstance(value, Mapping) else None


def _items(value: object) -> tuple[object, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, Mapping)):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(value)
    raise LineageIntegrityError(LineageFailure.INVALID_PAYLOAD, "expected a list of entries")


def _first_text(item: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        value = _text(item.get(key))
        if value is not None:
            return value
    return None


def _normal(value: object) -> str | None:
    text = _text(value)
    return None if text is None else text.lower().replace("-", "_").replace(" ", "_")


def _bool(value: object, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def lineage_content_hash(nodes: object, edges: object) -> str:
    """Canonical digest owners publish as ``content_hash`` for a lineage page."""

    canonical = json.dumps(
        {"nodes": nodes, "edges": edges},
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --- query ---------------------------------------------------------------------


def _raw_query(context: QueryContext) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    if context is None:
        return result
    if isinstance(context, str):
        parsed = urlsplit(context)
        query = parsed.query if parsed.query or parsed.path.startswith("/") else context.lstrip("?")
        for key, value in parse_qsl(query, keep_blank_values=True):
            result.setdefault(key, []).append(value)
        return result
    for name, raw in context.items():
        if raw is None:
            continue
        if isinstance(raw, (list, tuple)):
            result[str(name)] = [str(item) for item in raw]
        else:
            result[str(name)] = [str(raw)]
    return result


def _csv(values: Sequence[str]) -> tuple[str, ...]:
    tokens = (part.strip() for value in values for part in value.split(","))
    return tuple(dict.fromkeys(token for token in tokens if token))


@dataclass(frozen=True, slots=True)
class LineageQuery:
    """Validated, bounded request parameters; invalid input is reported, not guessed."""

    record_id: str | None = None
    node: str | None = None
    path_to: str | None = None
    direction: LineageDirection = LineageDirection.BOTH
    relations: tuple[LineageRelation, ...] = ()
    record_types: tuple[LineageRecordType, ...] = ()
    depth: int = DEFAULT_DEPTH
    page_size: int = DEFAULT_PAGE_SIZE
    cursor: str | None = None
    snapshot_tokens: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    display_notes: tuple[LineageQueryNote, ...] = ()

    @property
    def snapshot_token(self) -> str | None:
        return self.snapshot_tokens[0] if self.snapshot_tokens else None

    @classmethod
    def from_query(
        cls,
        context: QueryContext = None,
        *,
        record_id: str | None = None,
        snapshot_token: str | None = None,
    ) -> LineageQuery:
        raw = _raw_query(context)

        def one(key: str) -> str | None:
            values = raw.get(key)
            return _text(values[0]) if values else None

        notes: list[str] = []
        display_notes: list[LineageQueryNote] = []
        direction = LineageDirection.BOTH
        raw_direction = one("direction")
        if raw_direction is not None:
            try:
                direction = LineageDirection(raw_direction)
            except ValueError:
                notes.append(f"Unknown direction {raw_direction!r} ignored; showing both.")
                display_notes.append(
                    LineageQueryNote("lineage.note.unknown_direction", (("value", raw_direction),))
                )

        def values_for(*keys: str) -> tuple[str, ...]:
            return tuple(value for key in keys for value in raw.get(key, ()))

        relations: list[LineageRelation] = []
        for token in _csv(values_for("relations", "relation")):
            try:
                relations.append(LineageRelation(token))
            except ValueError:
                notes.append(f"Unknown relation {token!r} ignored.")
                display_notes.append(
                    LineageQueryNote("lineage.note.unknown_relation", (("value", token),))
                )
        record_types: list[LineageRecordType] = []
        for token in _csv(values_for("record_types", "record_type")):
            try:
                record_types.append(LineageRecordType(token))
            except ValueError:
                notes.append(f"Unknown record type {token!r} ignored.")
                display_notes.append(
                    LineageQueryNote("lineage.note.unknown_record_type", (("value", token),))
                )
        depth = _bounded_int(
            one("depth"), DEFAULT_DEPTH, 1, MAX_DEPTH, "depth", "depth", notes, display_notes
        )
        page_size = _bounded_int(
            one("page_size"),
            DEFAULT_PAGE_SIZE,
            1,
            MAX_PAGE_SIZE,
            "page_size",
            "page_size",
            notes,
            display_notes,
        )
        tokens = tuple(
            dict.fromkeys(t for t in (one("snapshot_token"), _text(snapshot_token)) if t)
        )
        return cls(
            record_id=_text(record_id) or one("record_id") or one("root_id"),
            node=one("node") or one("node_id"),
            path_to=one("path_to") or one("target_id"),
            direction=direction,
            relations=tuple(dict.fromkeys(relations)),
            record_types=tuple(dict.fromkeys(record_types)),
            depth=depth,
            page_size=page_size,
            cursor=one("cursor"),
            snapshot_tokens=tokens,
            notes=tuple(notes),
            display_notes=tuple(display_notes),
        )


def _bounded_int(
    raw: str | None,
    default: int,
    low: int,
    high: int,
    name: str,
    param_name: str,
    notes: list[str],
    display_notes: list[LineageQueryNote],
) -> int:
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        notes.append(f"Invalid {name} {raw!r} ignored; using {default}.")
        display_notes.append(
            LineageQueryNote(
                "lineage.note.invalid_integer",
                (("name", param_name), ("value", raw), ("default", default)),
            )
        )
        return default
    clamped = max(low, min(high, value))
    if clamped != value:
        notes.append(f"{name} {value} is outside {low}..{high}; using {clamped}.")
        display_notes.append(
            LineageQueryNote(
                "lineage.note.clamped_integer",
                (
                    ("name", param_name),
                    ("value", value),
                    ("low", low),
                    ("high", high),
                    ("clamped", clamped),
                ),
            )
        )
    return clamped


# --- typed model ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LineageSourceRef:
    """A source pointer retained even when it cannot be resolved to a locator."""

    source_id: str
    locator: str | None = None
    owner: str | None = None
    kind: str | None = None
    schema: str | None = None
    revision: str | None = None

    @property
    def resolved(self) -> bool:
        return self.locator is not None

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "locator": self.locator,
            "owner": self.owner,
            "kind": self.kind,
            "schema": self.schema,
            "revision": self.revision,
        }


@dataclass(frozen=True, slots=True)
class LineageDerivation:
    kind: str
    rule: str | None = None
    inputs: tuple[str, ...] = ()
    version: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "rule": self.rule,
            "inputs": list(self.inputs),
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class LineageNode:
    node_id: str
    record_type: LineageRecordType
    label: str
    status: str | None = None
    hash: str | None = None
    verified_hash: str | None = None
    as_of: str | None = None
    snapshot_token: str | None = None
    source_refs: tuple[LineageSourceRef, ...] = ()
    derivation: LineageDerivation | None = None
    metadata: tuple[tuple[str, str], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "record_type": self.record_type.value,
            "label": self.label,
            "status": self.status,
            "hash": self.hash,
            "verified_hash": self.verified_hash,
            "as_of": self.as_of,
            "snapshot_token": self.snapshot_token,
            "source_refs": [ref.to_dict() for ref in self.source_refs],
            "derivation": None if self.derivation is None else self.derivation.to_dict(),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class LineageEdge:
    edge_id: str
    source_id: str
    target_id: str
    relation: LineageRelation
    as_of: str | None = None
    source_refs: tuple[LineageSourceRef, ...] = ()
    derivation: LineageDerivation | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "edge_id": self.edge_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation": self.relation.value,
            "as_of": self.as_of,
            "source_refs": [ref.to_dict() for ref in self.source_refs],
            "derivation": None if self.derivation is None else self.derivation.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class LineagePath:
    """The shortest path found within the bounded, visible graph."""

    node_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]

    @property
    def target_id(self) -> str:
        return self.node_ids[-1]

    @property
    def length(self) -> int:
        return len(self.edge_ids)

    def to_dict(self) -> dict[str, object]:
        return {"node_ids": list(self.node_ids), "edge_ids": list(self.edge_ids)}


@dataclass(frozen=True, slots=True)
class LineagePagination:
    cursor: str | None = None
    next_cursor: str | None = None
    has_more: bool = False
    page_size: int | None = None
    snapshot_token: str | None = None
    cursor_state: str = "valid"
    complete: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "cursor": self.cursor,
            "next_cursor": self.next_cursor,
            "has_more": self.has_more,
            "page_size": self.page_size,
            "snapshot_token": self.snapshot_token,
            "cursor_state": self.cursor_state,
            "complete": self.complete,
        }


@dataclass(frozen=True, slots=True)
class LineageFailureInfo:
    code: LineageFailure
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code.value, "detail": self.detail}


# --- parsing -------------------------------------------------------------------


def _source_refs(raw: object, index: Mapping[str, SourceReference]) -> tuple[LineageSourceRef, ...]:
    refs: list[LineageSourceRef] = []
    seen: set[str] = set()
    for entry in _items(raw):
        nested = _mapping(entry)
        source_id = (
            _first_text(nested, "source_id", "id", "ref") if nested is not None else _text(entry)
        )
        if source_id is None:
            raise LineageIntegrityError(
                LineageFailure.INVALID_PAYLOAD, "a source reference has no identity"
            )
        if source_id in seen:
            continue
        seen.add(source_id)
        known = index.get(source_id)
        explicit = _first_text(nested, "locator", "uri", "url") if nested is not None else None
        refs.append(
            LineageSourceRef(
                source_id=source_id,
                locator=known.locator if known is not None else explicit,
                owner=known.owner if known is not None else None,
                kind=known.kind if known is not None else None,
                schema=known.schema if known is not None else None,
                revision=known.revision if known is not None else None,
            )
        )
    return tuple(refs)


def _derivation(raw: object) -> LineageDerivation | None:
    if raw is None:
        return None
    item = _mapping(raw)
    kind = _text(item.get("kind")) if item is not None else None
    if item is None or kind not in DERIVATION_KINDS:
        raise LineageIntegrityError(LineageFailure.INVALID_PAYLOAD, "malformed derivation")
    inputs = tuple(_text(entry) for entry in _items(item.get("inputs")))
    if not all(inputs):
        raise LineageIntegrityError(LineageFailure.INVALID_PAYLOAD, "malformed derivation inputs")
    return LineageDerivation(
        kind=cast(str, kind),
        rule=_text(item.get("rule")),
        inputs=cast(tuple[str, ...], inputs),
        version=_text(item.get("version")),
    )


def _metadata(raw: object) -> tuple[tuple[str, str], ...]:
    item = _mapping(raw)
    if item is None:
        return ()
    return tuple(
        (key, str(value))
        for key, value in sorted(item.items())
        if isinstance(value, (str, int, float, bool))
    )


def _parse_node(
    raw: object, index: Mapping[str, SourceReference], model: ManagerReadModel
) -> LineageNode:
    item = _mapping(raw)
    node_id = _first_text(item, "id", "node_id", "record_id") if item is not None else None
    if item is None or node_id is None:
        raise LineageIntegrityError(LineageFailure.INVALID_PAYLOAD, "a node has no identity")
    record_type = _normal(item.get("record_type", item.get("type")))
    try:
        parsed_type = LineageRecordType(record_type or "")
    except ValueError:
        raise LineageIntegrityError(
            LineageFailure.UNKNOWN_SCHEMA,
            f"node {node_id!r} has unknown record type {record_type!r}",
        ) from None
    snapshot = _text(item.get("snapshot_token"))
    if (
        snapshot is not None
        and model.snapshot_token is not None
        and snapshot != model.snapshot_token
    ):
        raise LineageIntegrityError(
            LineageFailure.SNAPSHOT_DRIFT,
            f"node {node_id!r} belongs to snapshot {snapshot!r}, not {model.snapshot_token!r}",
        )
    declared, observed = _text(item.get("hash")), _text(item.get("verified_hash"))
    verification = _normal(item.get("verification_status"))
    if verification in {"hash_mismatch", "digest_mismatch"} or (
        declared is not None and observed is not None and declared != observed
    ):
        raise LineageIntegrityError(
            LineageFailure.HASH_MISMATCH,
            f"node {node_id!r} declared hash does not match its verified hash",
        )
    return LineageNode(
        node_id=node_id,
        record_type=parsed_type,
        label=_first_text(item, "label", "title", "name") or node_id,
        status=_first_text(item, "status", "state"),
        hash=declared,
        verified_hash=observed,
        as_of=_text(item.get("as_of")),
        snapshot_token=snapshot,
        source_refs=_source_refs(
            item.get("source_refs", item.get("source_ref", item.get("sources"))), index
        ),
        derivation=_derivation(item.get("derivation")),
        metadata=_metadata(item.get("metadata")),
    )


def _parse_edge(raw: object, index: Mapping[str, SourceReference]) -> LineageEdge:
    item = _mapping(raw)
    source = _first_text(item, "source", "source_id", "from") if item is not None else None
    target = _first_text(item, "target", "target_id", "to") if item is not None else None
    if item is None or source is None or target is None:
        raise LineageIntegrityError(LineageFailure.INVALID_PAYLOAD, "an edge lacks endpoints")
    if source == target:
        raise LineageIntegrityError(
            LineageFailure.INVALID_PAYLOAD, f"edge on {source!r} relates a record to itself"
        )
    relation = _normal(item.get("relation"))
    try:
        parsed_relation = LineageRelation(relation or "")
    except ValueError:
        raise LineageIntegrityError(
            LineageFailure.UNKNOWN_SCHEMA,
            f"edge {source!r} -> {target!r} has unknown relation {relation!r}",
        ) from None
    return LineageEdge(
        edge_id=_first_text(item, "id", "edge_id") or f"{source}|{parsed_relation.value}|{target}",
        source_id=source,
        target_id=target,
        relation=parsed_relation,
        as_of=_text(item.get("as_of")),
        source_refs=_source_refs(
            item.get("source_refs", item.get("source_ref", item.get("sources"))), index
        ),
        derivation=_derivation(item.get("derivation")),
    )


def _parse_pagination(payload: Mapping[str, object]) -> LineagePagination:
    item = _mapping(payload.get("pagination")) or {
        key: payload[key]
        for key in (
            "cursor",
            "next_cursor",
            "has_more",
            "cursor_state",
            "snapshot_token",
            "complete",
            "page_size",
        )
        if key in payload
    }
    page_size = item.get("page_size")
    return LineagePagination(
        cursor=_text(item.get("cursor")),
        next_cursor=_text(item.get("next_cursor")),
        has_more=_bool(item.get("has_more"), False),
        page_size=page_size
        if isinstance(page_size, int) and not isinstance(page_size, bool)
        else None,
        snapshot_token=_text(item.get("snapshot_token")),
        cursor_state=_normal(item.get("cursor_state")) or "valid",
        complete=_bool(item.get("complete"), True),
    )


_STATUS_FAILURES: Mapping[ReadModelStatus, LineageFailure] = {
    ReadModelStatus.API_UNAVAILABLE: LineageFailure.SOURCE_UNAVAILABLE,
    ReadModelStatus.BLOCKED: LineageFailure.SOURCE_BLOCKED,
    ReadModelStatus.INCOMPARABLE: LineageFailure.INCOMPARABLE,
    ReadModelStatus.INTEGRITY_FAILURE: LineageFailure.INTEGRITY_FAILURE,
}
_EXPIRED_ERROR_CODES = frozenset({"cursor_expired", "lineage_cursor_expired"})


def _error_code(value: str) -> str:
    return value.lower().replace("-", "_").replace(" ", "_")


def _check_envelope(model: ManagerReadModel, query: LineageQuery, expected: Sequence[str]) -> None:
    status = model.availability.status
    if status in _STATUS_FAILURES:
        raise LineageIntegrityError(
            _STATUS_FAILURES[status],
            model.availability.reason or f"The lineage source reports {status.value}.",
        )
    if any(_error_code(error.code) in _EXPIRED_ERROR_CODES for error in model.errors):
        raise LineageIntegrityError(
            LineageFailure.CURSOR_EXPIRED, "The owner reports the lineage cursor has expired."
        )
    for token in (*query.snapshot_tokens, *expected):
        if token != model.snapshot_token:
            raise LineageIntegrityError(
                LineageFailure.SNAPSHOT_DRIFT,
                f"Requested snapshot {token!r} differs from the read snapshot "
                f"{model.snapshot_token!r}; snapshots are never mixed.",
            )


@dataclass(frozen=True, slots=True)
class _Parsed:
    root_id: str | None
    nodes: tuple[LineageNode, ...]
    edges: tuple[LineageEdge, ...]
    pagination: LineagePagination
    dangling: int


def _check_page_integrity(payload: Mapping[str, object]) -> None:
    integrity = _mapping(payload.get("integrity")) or {}
    status = _normal(integrity.get("status", payload.get("integrity_status")))
    if status in {"hash_mismatch", "digest_mismatch", "failed"}:
        raise LineageIntegrityError(
            LineageFailure.HASH_MISMATCH,
            _text(integrity.get("reason")) or "The lineage page failed its hash integrity check.",
        )
    expected = _first_text(integrity, "expected_hash", "declared_hash", "hash")
    observed = _first_text(integrity, "observed_hash", "verified_hash", "actual_hash")
    if expected is not None and observed is not None and expected != observed:
        raise LineageIntegrityError(
            LineageFailure.HASH_MISMATCH,
            "The lineage page declared hash does not match its observed hash.",
        )


def _parse_payload(
    model: ManagerReadModel, query: LineageQuery, expected: Sequence[str]
) -> _Parsed:
    _check_envelope(model, query, expected)
    payload = _mapping(model.data)
    if payload is None:
        raise LineageIntegrityError(LineageFailure.INVALID_PAYLOAD, "data is not an object")
    schema = _text(payload.get("schema", payload.get("lineage_schema")))
    if schema not in SUPPORTED_LINEAGE_SCHEMAS:
        raise LineageIntegrityError(
            LineageFailure.UNKNOWN_SCHEMA,
            f"lineage schema {schema!r} is not one of {list(SUPPORTED_LINEAGE_SCHEMAS)}",
        )
    pagination = _parse_pagination(payload)
    if pagination.cursor_state == "expired":
        raise LineageIntegrityError(
            LineageFailure.CURSOR_EXPIRED, "The lineage cursor has expired; restart from the root."
        )
    if query.cursor is not None and pagination.cursor != query.cursor:
        raise LineageIntegrityError(
            LineageFailure.CURSOR_MISMATCH,
            f"Requested cursor {query.cursor!r} is not the cursor of the page that was read.",
        )
    if pagination.snapshot_token is not None and pagination.snapshot_token != model.snapshot_token:
        raise LineageIntegrityError(
            LineageFailure.SNAPSHOT_DRIFT,
            f"The page cursor snapshot {pagination.snapshot_token!r} differs from "
            f"the read snapshot {model.snapshot_token!r}.",
        )
    raw_nodes, raw_edges = payload.get("nodes", []), payload.get("edges", [])
    _check_page_integrity(payload)
    node_items, edge_items = _items(raw_nodes), _items(raw_edges)
    if len(node_items) > MAX_NODES or len(edge_items) > MAX_EDGES:
        raise LineageIntegrityError(
            LineageFailure.BOUND_EXCEEDED,
            f"A lineage page may hold at most {MAX_NODES} nodes and {MAX_EDGES} edges.",
        )
    index = {source.source_id: source for source in model.source_refs}
    nodes = tuple(
        sorted((_parse_node(raw, index, model) for raw in node_items), key=lambda n: n.node_id)
    )
    if len({node.node_id for node in nodes}) != len(nodes):
        raise LineageIntegrityError(LineageFailure.INVALID_PAYLOAD, "duplicate node identities")
    edges = tuple(sorted((_parse_edge(raw, index) for raw in edge_items), key=lambda e: e.edge_id))
    if len({edge.edge_id for edge in edges}) != len(edges):
        raise LineageIntegrityError(LineageFailure.INVALID_PAYLOAD, "duplicate edge identities")
    declared_hash = _text(payload.get("content_hash"))
    if declared_hash is not None and declared_hash != lineage_content_hash(raw_nodes, raw_edges):
        raise LineageIntegrityError(
            LineageFailure.HASH_MISMATCH, "The declared content hash does not match the page."
        )
    known = {node.node_id for node in nodes}
    dangling = sum(
        1 for edge in edges if edge.source_id not in known or edge.target_id not in known
    )
    partial = pagination.has_more or not pagination.complete or not model.availability.complete
    if dangling and not partial:
        raise LineageIntegrityError(
            LineageFailure.INVALID_PAYLOAD,
            "An edge references a record that is not on this complete page.",
        )
    return _Parsed(
        root_id=query.record_id or _first_text(payload, "root", "root_id"),
        nodes=nodes,
        edges=edges,
        pagination=pagination,
        dangling=dangling,
    )


# --- bounded traversal ---------------------------------------------------------


def _adjacency(
    edges: Sequence[LineageEdge], relations: Sequence[LineageRelation]
) -> tuple[dict[str, list[LineageEdge]], dict[str, list[LineageEdge]]]:
    outgoing: dict[str, list[LineageEdge]] = {}
    incoming: dict[str, list[LineageEdge]] = {}
    for edge in edges:
        if relations and edge.relation not in relations:
            continue
        outgoing.setdefault(edge.source_id, []).append(edge)
        incoming.setdefault(edge.target_id, []).append(edge)
    return outgoing, incoming


def _neighbors(
    node_id: str,
    direction: LineageDirection,
    outgoing: Mapping[str, Sequence[LineageEdge]],
    incoming: Mapping[str, Sequence[LineageEdge]],
) -> list[tuple[str, LineageEdge]]:
    found: list[tuple[str, LineageEdge]] = []
    if direction in (LineageDirection.DOWNSTREAM, LineageDirection.BOTH):
        found.extend((edge.target_id, edge) for edge in outgoing.get(node_id, ()))
    if direction in (LineageDirection.UPSTREAM, LineageDirection.BOTH):
        found.extend((edge.source_id, edge) for edge in incoming.get(node_id, ()))
    return sorted(found, key=lambda pair: (pair[0], pair[1].edge_id))


def _expand(
    root_id: str,
    nodes: Mapping[str, LineageNode],
    outgoing: Mapping[str, Sequence[LineageEdge]],
    incoming: Mapping[str, Sequence[LineageEdge]],
    query: LineageQuery,
) -> dict[str, int]:
    """Breadth-first expansion bounded by depth, relations, and record types."""

    depths = {root_id: 0}
    queue = deque([root_id])
    while queue:
        current = queue.popleft()
        if depths[current] >= query.depth:
            continue
        for neighbor, _edge in _neighbors(current, query.direction, outgoing, incoming):
            if neighbor in depths or neighbor not in nodes:
                continue
            if query.record_types and nodes[neighbor].record_type not in query.record_types:
                continue
            depths[neighbor] = depths[current] + 1
            queue.append(neighbor)
    return depths


def _component(
    root_id: str, nodes: Mapping[str, LineageNode], edges: Sequence[LineageEdge]
) -> set[str]:
    """Every record connected to the root by any relation, ignoring direction and bounds."""

    outgoing, incoming = _adjacency(edges, ())
    seen = {root_id}
    queue = deque([root_id])
    while queue:
        for neighbor, _edge in _neighbors(
            queue.popleft(), LineageDirection.BOTH, outgoing, incoming
        ):
            if neighbor not in seen and neighbor in nodes:
                seen.add(neighbor)
                queue.append(neighbor)
    return seen


def _shortest_path(
    root_id: str,
    targets: set[str],
    visible: Mapping[str, int],
    direction: LineageDirection,
    outgoing: Mapping[str, Sequence[LineageEdge]],
    incoming: Mapping[str, Sequence[LineageEdge]],
) -> LineagePath | None:
    """Deterministic shortest path inside the visible graph; ties break by record id."""

    parents: dict[str, tuple[str, str]] = {}
    seen = {root_id}
    frontier = [root_id]
    while frontier:
        reached = sorted(node for node in frontier if node in targets and node != root_id)
        if reached:
            node_ids, edge_ids = [reached[0]], []
            while node_ids[-1] != root_id:
                parent, edge_id = parents[node_ids[-1]]
                node_ids.append(parent)
                edge_ids.append(edge_id)
            return LineagePath(tuple(reversed(node_ids)), tuple(reversed(edge_ids)))
        upcoming: list[str] = []
        for current in frontier:
            for neighbor, edge in _neighbors(current, direction, outgoing, incoming):
                if neighbor in visible and neighbor not in seen:
                    seen.add(neighbor)
                    parents[neighbor] = (current, edge.edge_id)
                    upcoming.append(neighbor)
        frontier = upcoming
    return None


# --- view model ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LineageViewModel:
    """Immutable projection of one lineage page; failures leave it empty."""

    read_model: ManagerReadModel
    query: LineageQuery
    state: LineageState
    failure: LineageFailureInfo | None = None
    root_id: str | None = None
    nodes: tuple[LineageNode, ...] = ()
    edges: tuple[LineageEdge, ...] = ()
    pagination: LineagePagination = field(default_factory=LineagePagination)
    depths: Mapping[str, int] = field(default_factory=dict)
    visible_edges: tuple[LineageEdge, ...] = ()
    disconnected: tuple[LineageNode, ...] = ()
    outside_bounds: int = 0
    dangling_edges: int = 0
    evidence_path: LineagePath | None = None
    path_state: LineagePathState = LineagePathState.NOT_APPLICABLE

    @classmethod
    def from_read_model(
        cls,
        model: ManagerReadModel,
        query: LineageQuery | None = None,
        *,
        expected_snapshots: Sequence[str] = (),
    ) -> LineageViewModel:
        selected = query or LineageQuery()
        if model.availability.status is ReadModelStatus.MISSING:
            return cls(read_model=model, query=selected, state=LineageState.EMPTY)
        try:
            parsed = _parse_payload(model, selected, expected_snapshots)
        except LineageIntegrityError as error:
            return cls(
                read_model=model,
                query=selected,
                state=LineageState.FAIL_CLOSED,
                failure=LineageFailureInfo(error.code, error.detail),
            )
        partial = (
            parsed.pagination.has_more
            or not parsed.pagination.complete
            or not model.availability.complete
        )
        if not parsed.nodes:
            return cls(
                read_model=model,
                query=selected,
                state=LineageState.PARTIAL if partial else LineageState.EMPTY,
                root_id=parsed.root_id,
                pagination=parsed.pagination,
                dangling_edges=parsed.dangling,
            )
        by_id = {node.node_id: node for node in parsed.nodes}
        if parsed.root_id is None or parsed.root_id not in by_id:
            return cls(
                read_model=model,
                query=selected,
                state=LineageState.FAIL_CLOSED,
                failure=LineageFailureInfo(
                    LineageFailure.ROOT_NOT_FOUND,
                    f"Root record {parsed.root_id or '(none declared)'} is not in this snapshot page.",
                ),
                root_id=parsed.root_id,
            )
        outgoing, incoming = _adjacency(parsed.edges, selected.relations)
        depths = _expand(parsed.root_id, by_id, outgoing, incoming, selected)
        connected = _component(parsed.root_id, by_id, parsed.edges)
        visible_edges = tuple(
            edge
            for edge in parsed.edges
            if (not selected.relations or edge.relation in selected.relations)
            and edge.source_id in depths
            and edge.target_id in depths
        )
        if selected.path_to is not None:
            targets = {selected.path_to}
        else:
            targets = {
                node_id
                for node_id in depths
                if by_id[node_id].record_type is LineageRecordType.EVIDENCE
            }
        path = _shortest_path(
            parsed.root_id, targets, depths, selected.direction, outgoing, incoming
        )
        if path is not None:
            path_state = LineagePathState.FOUND
        elif partial:
            path_state = LineagePathState.NOT_ESTABLISHED
        else:
            path_state = LineagePathState.NOT_FOUND
        return cls(
            read_model=model,
            query=selected,
            state=LineageState.PARTIAL if partial else LineageState.READY,
            root_id=parsed.root_id,
            nodes=parsed.nodes,
            edges=parsed.edges,
            pagination=parsed.pagination,
            depths=depths,
            visible_edges=visible_edges,
            disconnected=tuple(node for node in parsed.nodes if node.node_id not in connected),
            outside_bounds=len(connected) - len(depths),
            dangling_edges=parsed.dangling,
            evidence_path=path,
            path_state=path_state,
        )

    @property
    def partial(self) -> bool:
        return self.state is LineageState.PARTIAL

    @property
    def visible_nodes(self) -> tuple[LineageNode, ...]:
        return tuple(
            sorted(
                (node for node in self.nodes if node.node_id in self.depths),
                key=lambda node: (self.depths[node.node_id], node.node_id),
            )
        )

    @property
    def as_of(self) -> str | None:
        return self.read_model.as_of

    @property
    def snapshot_token(self) -> str | None:
        return self.read_model.snapshot_token

    @property
    def raw_json(self) -> str:
        return self.read_model.to_json()

    @property
    def shortest_evidence_path(self) -> LineagePath | None:
        return self.evidence_path

    @property
    def disconnected_records(self) -> tuple[LineageNode, ...]:
        return self.disconnected

    @property
    def inspector(self) -> LineageInspector:
        node = self.node(self.query.node or self.root_id or "")
        return LineageInspector(
            node_id=None if node is None else node.node_id,
            record_type=None if node is None else node.record_type,
            label=None if node is None else node.label,
            metadata=() if node is None else node.metadata,
            source_refs=() if node is None else node.source_refs,
            as_of=self.as_of if node is None else node.as_of or self.as_of,
            snapshot_token=self.snapshot_token
            if node is None
            else node.snapshot_token or self.snapshot_token,
            derivation=self.read_model.derivation,
            node_count=len(self.visible_nodes),
            edge_count=len(self.visible_edges),
            state=self.state,
        )

    def node(self, node_id: str) -> LineageNode | None:
        return next((node for node in self.nodes if node.node_id == node_id), None)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.read_model.schema,
            "state": self.state.value,
            "failure": None if self.failure is None else self.failure.to_dict(),
            "root_id": self.root_id,
            "query": {
                "direction": self.query.direction.value,
                "relations": [relation.value for relation in self.query.relations],
                "record_types": [kind.value for kind in self.query.record_types],
                "depth": self.query.depth,
                "page_size": self.query.page_size,
                "cursor": self.query.cursor,
            },
            "nodes": [node.to_dict() for node in self.visible_nodes],
            "edges": [edge.to_dict() for edge in self.visible_edges],
            "depths": dict(sorted(self.depths.items())),
            "disconnected": [node.node_id for node in self.disconnected],
            "outside_bounds": self.outside_bounds,
            "dangling_edges": self.dangling_edges,
            "evidence_path": None if self.evidence_path is None else self.evidence_path.to_dict(),
            "path_state": self.path_state.value,
            "pagination": self.pagination.to_dict(),
            "availability": self.read_model.availability.to_dict(),
            "source_refs": [source.to_dict() for source in self.read_model.source_refs],
            "as_of": self.read_model.as_of,
            "snapshot_token": self.read_model.snapshot_token,
            "errors": [error.to_dict() for error in self.read_model.errors],
        }


LineageView = LineageViewModel


@dataclass(frozen=True, slots=True)
class LineageInspector:
    """Typed metadata for the selected record and its bounded graph context."""

    node_id: str | None
    record_type: LineageRecordType | None
    label: str | None
    metadata: tuple[tuple[str, str], ...]
    source_refs: tuple[LineageSourceRef, ...]
    as_of: str | None
    snapshot_token: str | None
    derivation: Derivation
    node_count: int
    edge_count: int
    state: LineageState

    def to_dict(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "record_type": None if self.record_type is None else self.record_type.value,
            "label": self.label,
            "metadata": dict(self.metadata),
            "source_refs": [ref.to_dict() for ref in self.source_refs],
            "as_of": self.as_of,
            "snapshot_token": self.snapshot_token,
            "derivation": self.derivation.to_dict(),
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "state": self.state.value,
        }


def shortest_evidence_path(
    view_or_model: LineageViewModel | ManagerReadModel,
    *,
    query: LineageQuery | None = None,
    root_id: str | None = None,
    target_id: str | None = None,
) -> LineagePath | None:
    """Return the deterministic shortest path without bypassing the read-model gate."""

    if isinstance(view_or_model, LineageViewModel):
        view = view_or_model
        if root_id is not None or target_id is not None:
            selected_query = replace(
                view.query,
                record_id=root_id or view.query.record_id,
                path_to=target_id or view.query.path_to,
            )
            view = LineageViewModel.from_read_model(view.read_model, selected_query)
    else:
        selected_query = query or LineageQuery()
        if root_id is not None or target_id is not None:
            selected_query = replace(
                selected_query,
                record_id=root_id or selected_query.record_id,
                path_to=target_id or selected_query.path_to,
            )
        view = LineageViewModel.from_read_model(view_or_model, selected_query)
    return view.shortest_evidence_path


# --- rendering -----------------------------------------------------------------

_NODE_W, _NODE_H, _COL_W, _ROW_H, _PAD = 180, 44, 240, 68, 16
# Keys the bounds form owns; changing any of them invalidates a cursor and the page offset.
_MANAGED_KEYS = frozenset(
    {"direction", "relations", "record_types", "depth", "page_size", "cursor", "page"}
)
_RESTARTABLE = frozenset(
    {LineageFailure.CURSOR_EXPIRED, LineageFailure.CURSOR_MISMATCH, LineageFailure.SNAPSHOT_DRIFT}
)
_LINEAGE_FIXTURE_REASONS = {
    "The fixture contains the published lineage projection.": "lineage.fixture_reason.complete",
    "No lineage records are published in this scope.": "lineage.fixture_reason.empty",
    "Only the first lineage page is published.": "lineage.fixture_reason.partial",
    "The lineage cursor expired.": "lineage.fixture_reason.cursor_expired",
    "The approved public lineage read API is unavailable.": "lineage.fixture_reason.api_unavailable",
    "The lineage page snapshot differs from the snapshot that was read.": "lineage.fixture_reason.shared_snapshot_drift",
    "A lineage record failed its declared hash check.": "lineage.fixture_reason.shared_integrity_failure",
    "The approved lineage read seam is blocked.": "lineage.fixture_reason.blocked",
    "The lineage inputs belong to incompatible snapshots.": "lineage.fixture_reason.incomparable",
    "The lineage page is retained as a stale historical projection.": "lineage.fixture_reason.stale",
}
_FIXTURE_NODE_LABELS = {
    "conclusion-1": "conclusion",
    "evidence-1": "evidence",
    "evidence-2": "replication_evidence",
    "evidence-3": "superseded_evidence",
    "artifact-1": "artifact",
    "run-1": "run",
    "campaign-1": "campaign",
    "candidate-1": "candidate",
    "genome-1": "genome",
    "memory-1": "memory",
    "document-1": "document",
    "document-orphan": "orphan_document",
}


def _is_fixture_model(model: ManagerReadModel) -> bool:
    return any(source.source_id == "lineage-fixture-source" for source in model.source_refs)


def _display_model(view: LineageViewModel, translator: Translator) -> ManagerReadModel:
    """Expose localized fixture reasons and page-local gates to the status renderer."""

    failure = view.failure
    status_for_failure = {
        LineageFailure.CURSOR_EXPIRED: ReadModelStatus.STALE,
        LineageFailure.CURSOR_MISMATCH: ReadModelStatus.STALE,
        LineageFailure.SNAPSHOT_DRIFT: ReadModelStatus.STALE,
        LineageFailure.UNKNOWN_SCHEMA: ReadModelStatus.INTEGRITY_FAILURE,
        LineageFailure.HASH_MISMATCH: ReadModelStatus.INTEGRITY_FAILURE,
        LineageFailure.INTEGRITY_FAILURE: ReadModelStatus.INTEGRITY_FAILURE,
        LineageFailure.INVALID_PAYLOAD: ReadModelStatus.INTEGRITY_FAILURE,
        LineageFailure.BOUND_EXCEEDED: ReadModelStatus.INTEGRITY_FAILURE,
        LineageFailure.ROOT_NOT_FOUND: ReadModelStatus.INTEGRITY_FAILURE,
        LineageFailure.SOURCE_UNAVAILABLE: ReadModelStatus.API_UNAVAILABLE,
        LineageFailure.SOURCE_BLOCKED: ReadModelStatus.BLOCKED,
        LineageFailure.INCOMPARABLE: ReadModelStatus.INCOMPARABLE,
    }
    if failure is not None:
        status = status_for_failure[failure.code]
        error = ReadModelError(code=failure.code.value, message=failure.detail)
        return replace(
            view.read_model,
            availability=Availability(
                status=status,
                complete=False,
                reason=failure.detail,
                retryable=status is ReadModelStatus.API_UNAVAILABLE,
            ),
            errors=tuple((*view.read_model.errors, error)),
        )

    model = view.read_model
    if _is_fixture_model(model):
        reason_key = _LINEAGE_FIXTURE_REASONS.get(model.availability.reason or "")
        if reason_key is not None:
            model = replace(
                model,
                availability=replace(model.availability, reason=translator.t(reason_key)),
            )
        error_keys = {
            "lineage_pagination_partial": "lineage.fixture_error.partial",
            "lineage_cursor_expired": "lineage.fixture_error.cursor_expired",
            "lineage_api_unavailable": "lineage.fixture_error.api_unavailable",
        }
        model = replace(
            model,
            errors=tuple(
                replace(error, message=translator.t(error_keys[error.code]))
                if error.code in error_keys
                else error
                for error in model.errors
            ),
        )
    if view.partial and model.availability.complete:
        model = replace(
            model,
            availability=Availability(
                status=model.availability.status,
                complete=False,
                reason=translator.t("lineage.partial_status_reason"),
                retryable=model.availability.retryable,
            ),
        )
    return model


def _attr(value: str) -> str:
    return escape(value, quote=True)


def _lineage_translator(translator: Translator | None) -> Translator:
    """Add this page's catalog without changing the shared registry."""

    selected = translator or Translator()
    overlap = {key for key in LINEAGE_CATALOG if key in CATALOG}
    if any(CATALOG[key] != LINEAGE_CATALOG[key] for key in overlap):
        raise CatalogError("registered Lineage catalog entries differ from the page catalog")
    additions = {key: value for key, value in LINEAGE_CATALOG.items() if key not in overlap}
    return Translator(
        selected.locale,
        strict=selected.strict,
        pseudo=selected.pseudo,
        catalog=merge(CATALOG, additions),
    )


def _flag(value: bool) -> str:
    return "true" if value else "false"


def _link(context: QueryContext, route: str, **updates: object) -> str:
    return context_link(context, view=route, **updates)


def _truncate(text: str, limit: int = 26) -> str:
    """Truncate by terminal display columns, not Python code-point count."""

    if limit <= 0:
        return ""
    if text.startswith("⟦") and text.endswith("⟧"):
        return f"⟦{_truncate(text[1:-1], max(0, limit - 2))}⟧"

    def width(value: str) -> int:
        return sum(2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1 for char in value)

    if width(text) <= limit:
        return text
    remaining = max(0, limit - 1)  # the ellipsis occupies one display column
    result: list[str] = []
    used = 0
    for char in text:
        char_width = 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
        if used + char_width > remaining:
            break
        result.append(char)
        used += char_width
    return "".join(result) + "…"


def _node_label(node: LineageNode, view: LineageViewModel, translator: Translator) -> str:
    if _is_fixture_model(view.read_model):
        key = _FIXTURE_NODE_LABELS.get(node.node_id)
        if key is not None:
            return translator.t(f"lineage.fixture_label.{key}")
        if node.node_id.startswith("node-") and node.node_id[5:].isdigit():
            return translator.t("lineage.fixture_label.large_record", number=int(node.node_id[5:]))
    return node.label


def _record_type(value: str, translator: Translator) -> str:
    return translator.label("lineage_record_type", value)


def _relation(value: str, translator: Translator) -> str:
    return translator.label("lineage_relation", value)


def _status(value: str | None, translator: Translator) -> str:
    return (
        translator.label("lineage_status", value)
        if value
        else escape(translator.t("lineage.not_recorded"))
    )


def _owner(value: str) -> str:
    return f'<span data-owner-text="true" translate="no">{escape(value, quote=True)}</span>'


def _render_sources(refs: Sequence[LineageSourceRef], *, translator: Translator) -> str:
    if not refs:
        return escape(translator.t("lineage.not_recorded"))
    parts: list[str] = []
    for ref in refs:
        if support := source_support_entry(ref.source_id):
            parts.append(support)
            continue
        origin = " · ".join(part for part in (ref.owner, ref.kind) if part)
        label = _owner(ref.source_id) + (f" ({_owner(origin)})" if origin else "")
        target = public_locator(ref.locator)
        if target is not None:
            parts.append(
                f'<a class="lineage-source-link" data-source-id="{_attr(ref.source_id)}" '
                f'href="{_attr(target)}" translate="no">{label}</a>'
            )
        else:
            parts.append(
                f'<span data-source-id="{_attr(ref.source_id)}"><span translate="no">{label}</span> — '
                f"{escape(translator.t('lineage.not_recorded'))}</span>"
            )
    return " · ".join(parts)


def _describe_derivation(derivation: LineageDerivation | None, *, translator: Translator) -> str:
    if derivation is None:
        return translator.t("lineage.derivation_unrecorded")
    values = [value for value in (derivation.kind, derivation.rule, derivation.version) if value]
    text = " · ".join(_owner(value) for value in values)
    if derivation.inputs:
        inputs = translator.join(_owner(value) for value in derivation.inputs)
        text += f" ({translator.t('lineage.derivation_inputs_prefix')}{inputs})"
    return text


def _describe_hash(node: LineageNode, *, translator: Translator) -> str:
    if node.hash is None:
        return translator.t("lineage.not_recorded_short")
    # A match is the only way a node reaches the renderer; absence of a check is never "verified".
    key = (
        "lineage.hash_verified" if node.verified_hash == node.hash else "lineage.hash_not_verified"
    )
    return f"{_owner(node.hash)} ({translator.t(key)})"


def _edge_sentence(
    nodes: Mapping[str, LineageNode],
    edge: LineageEdge,
    *,
    translator: Translator,
    view: LineageViewModel | None = None,
) -> str:
    def label(node_id: str) -> str:
        node = nodes.get(node_id)
        if node is None:
            return f"{node_id} ({translator.t('lineage.no_owner_page')})"
        return _node_label(node, view, translator) if view is not None else node.label

    return translator.t(
        "lineage.edge_sentence",
        source=label(edge.source_id),
        relation=_relation(edge.relation.value, translator),
        target=label(edge.target_id),
    )


def _edge_sentence_markup(
    nodes: Mapping[str, LineageNode],
    edge: LineageEdge,
    *,
    view: LineageViewModel,
    translator: Translator,
    context: QueryContext,
    route: str,
    link_node_id: str | None = None,
) -> str:
    def label(node_id: str) -> str:
        node = nodes.get(node_id)
        if node is None:
            return f"{_owner(node_id)} ({escape(translator.t('lineage.no_owner_page'))})"
        label_markup = (
            escape(_node_label(node, view, translator))
            if _is_fixture_model(view.read_model)
            else _owner(node.label)
        )
        if node_id == link_node_id and not translator.pseudo:
            return f'<a href="{_attr(_link(context, route, node=node_id))}">{label_markup}</a>'
        return label_markup

    return translator.t(
        "lineage.edge_sentence",
        source=label(edge.source_id),
        relation=_relation(edge.relation.value, translator),
        target=label(edge.target_id),
    )


def _node_label_markup(
    node: LineageNode, view: LineageViewModel, translator: Translator, *, truncate: bool = False
) -> str:
    label = _node_label(node, view, translator)
    if truncate:
        label = _truncate(label)
    return escape(label) if _is_fixture_model(view.read_model) else _owner(label)


def _layout(nodes: Sequence[LineageNode], depths: Mapping[str, int]) -> dict[str, tuple[int, int]]:
    rows: dict[int, int] = {}
    positions: dict[str, tuple[int, int]] = {}
    for node in nodes:
        column = depths[node.node_id]
        positions[node.node_id] = (column, rows.get(column, 0))
        rows[column] = rows.get(column, 0) + 1
    return positions


def _border(cx: float, cy: float, ox: float, oy: float) -> tuple[float, float]:
    """The point where the segment from a box centre towards (ox, oy) leaves the box."""

    dx, dy = ox - cx, oy - cy
    scale = min(
        (_NODE_W / 2) / abs(dx) if dx else float("inf"),
        (_NODE_H / 2) / abs(dy) if dy else float("inf"),
    )
    return cx + dx * scale, cy + dy * scale


def _render_graph(
    view: LineageViewModel,
    page_nodes: Sequence[LineageNode],
    page_edges: Sequence[LineageEdge],
    *,
    context: QueryContext,
    route: str,
    inspected_id: str | None,
    translator: Translator,
) -> str:
    positions = _layout(page_nodes, view.depths)
    columns = max(column for column, _ in positions.values()) + 1
    rows = max(row for _, row in positions.values()) + 1
    width = 2 * _PAD + (columns - 1) * _COL_W + _NODE_W
    height = 2 * _PAD + (rows - 1) * _ROW_H + _NODE_H
    centers = {
        node_id: (_PAD + column * _COL_W + _NODE_W / 2, _PAD + row * _ROW_H + _NODE_H / 2)
        for node_id, (column, row) in positions.items()
    }
    path_nodes = set(view.evidence_path.node_ids) if view.evidence_path else set()
    path_edges = set(view.evidence_path.edge_ids) if view.evidence_path else set()
    by_id = {node.node_id: node for node in page_nodes}
    edge_markup: list[str] = []
    for edge in page_edges:
        sx, sy = centers[edge.source_id]
        tx, ty = centers[edge.target_id]
        x1, y1 = _border(sx, sy, tx, ty)
        x2, y2 = _border(tx, ty, sx, sy)
        on_path = edge.edge_id in path_edges
        edge_label = translator.label("lineage_relation", edge.relation.value)
        edge_markup.append(
            f'<g class="lineage-edge" data-edge-id="{_attr(edge.edge_id)}" '
            f'data-relation="{edge.relation.value}" data-on-path="{_flag(on_path)}">'
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="currentColor" '
            f'stroke-width="{3 if on_path else 1.5}" marker-end="url(#lineage-arrow)"/>'
            f'<text x="{(x1 + x2) / 2:.1f}" y="{(y1 + y2) / 2 - 4:.1f}" text-anchor="middle" '
            'font-size="11" fill="currentColor" stroke="Canvas" stroke-width="3" paint-order="stroke">'
            f"{edge_label}</text>"
            f'<title translate="no">{escape(_edge_sentence(by_id, edge, translator=translator, view=view))}</title></g>'
        )
    node_markup: list[str] = []
    for node in page_nodes:
        column, row = positions[node.node_id]
        x, y = _PAD + column * _COL_W, _PAD + row * _ROW_H
        is_root = node.node_id == view.root_id
        on_path = node.node_id in path_nodes
        depth = view.depths[node.node_id]
        node_label = _node_label(node, view, translator)
        label_translate = "" if _is_fixture_model(view.read_model) else ' translate="no"'
        type_label = translator.label("lineage_record_type", node.record_type.value)
        spoken = translator.t(
            "lineage.node_accessible",
            label=node_label,
            record_type=translator.t(f"label.lineage_record_type.{node.record_type.value}"),
            depth=depth,
            root=translator.t("lineage.root_suffix") if is_root else "",
            path=translator.t("lineage.path_suffix") if on_path else "",
        )
        current = ' aria-current="true"' if node.node_id == inspected_id else ""
        node_markup.append(
            f'<g class="lineage-node" data-node-id="{_attr(node.node_id)}" '
            f'data-record-type="{node.record_type.value}" data-depth="{depth}" '
            f'data-root="{_flag(is_root)}" data-on-path="{_flag(on_path)}">'
            f'<a href="{_attr(_link(context, route, node=node.node_id))}" aria-label="{_attr(spoken)}"{current}{label_translate}>'
            f'<rect x="{x}" y="{y}" width="{_NODE_W}" height="{_NODE_H}" rx="6" fill="Canvas" '
            f'stroke="CanvasText" stroke-width="{3 if is_root or on_path else 1}"/>'
            f'<text x="{x + 10}" y="{y + 19}" font-size="13" fill="CanvasText"{label_translate}>'
            f"{escape(_truncate(node_label))}</text>"
            f'<text x="{x + 10}" y="{y + 36}" font-size="11" fill="GrayText">{type_label}</text>'
            f'<title translate="no">{escape(translator.t("lineage.node_title", label=node_label, id=node.node_id))}</title></a></g>'
        )
    caption = translator.t("lineage.graph_caption", nodes=len(page_nodes), edges=len(page_edges))
    svg_title = translator.t("lineage.svg_title")
    svg_description = translator.t(
        "lineage.svg_description", nodes=len(page_nodes), edges=len(page_edges)
    )
    return (
        '<figure class="lineage-graph" data-lineage-graph="true" data-lineage-view="graph" aria-labelledby="lineage-graph-caption">'
        f'<figcaption id="lineage-graph-caption">{escape(caption)} '
        f'<a class="lineage-skip" href="#lineage-table">{escape(translator.t("lineage.skip_table"))}</a></figcaption>'
        f'<div class="lineage-graph-scroll" role="region" aria-label="{_attr(translator.t("lineage.graph_region"))}" tabindex="0">'
        f'<svg role="group" aria-labelledby="lineage-svg-title" aria-describedby="lineage-svg-desc" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}"><title id="lineage-svg-title">{escape(svg_title)}</title>'
        f'<desc id="lineage-svg-desc">{escape(svg_description)}</desc>'
        '<defs><marker id="lineage-arrow" viewBox="0 0 8 8" refX="8" refY="4" markerWidth="8" '
        'markerHeight="8" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="currentColor"/></marker></defs>'
        f"{''.join(edge_markup)}{''.join(node_markup)}</svg></div></figure>"
    )


def _render_node_row(
    node: LineageNode,
    view: LineageViewModel,
    *,
    context: QueryContext,
    route: str,
    path_steps: Mapping[str, int],
    translator: Translator,
) -> str:
    step = path_steps.get(node.node_id)
    label = _node_label_markup(node, view, translator)
    type_label = _record_type(node.record_type.value, translator)
    status = _status(node.status, translator)
    as_of = node.as_of or view.as_of or translator.t("lineage.not_recorded")
    evidence_step = translator.t("lineage.step", number=step + 1) if step is not None else "—"
    return (
        f'<tr data-node-id="{_attr(node.node_id)}" data-record-type="{node.record_type.value}" '
        f'data-depth="{view.depths[node.node_id]}" data-root="{_flag(node.node_id == view.root_id)}" '
        f'data-on-path="{_flag(step is not None)}">'
        f'<th scope="row"><a href="{_attr(_link(context, route, node=node.node_id))}">{label}</a>'
        f'<br><small translate="no">{_attr(node.node_id)}</small></th>'
        f"<td>{type_label}</td><td>{status}</td>"
        f"<td>{view.depths[node.node_id]}</td>"
        f"<td>{escape(evidence_step)}</td>"
        f"<td>{_describe_hash(node, translator=translator)}</td>"
        f"<td>{_owner(as_of)}</td>"
        f"<td>{_render_sources(node.source_refs, translator=translator)}</td>"
        f"<td>{_describe_derivation(node.derivation, translator=translator)}</td>"
        f'<td><a href="{_attr(_link(context, route, record_id=node.node_id, node=None, path_to=None, cursor=None))}">'
        f"{escape(translator.t('lineage.trace_from_here'))}</a></td></tr>"
    )


def _render_edge_row(
    edge: LineageEdge,
    by_id: Mapping[str, LineageNode],
    view: LineageViewModel,
    *,
    context: QueryContext,
    route: str,
    on_path: bool,
    translator: Translator,
) -> str:
    def cell(node_id: str) -> str:
        node = by_id[node_id]
        label = _node_label_markup(node, view, translator)
        return f'<a href="{_attr(_link(context, route, node=node_id))}">{label}</a>'

    return (
        f'<tr data-edge-id="{_attr(edge.edge_id)}" data-relation="{edge.relation.value}" '
        f'data-on-path="{_flag(on_path)}"><th scope="row">{cell(edge.source_id)}</th>'
        f"<td>{_relation(edge.relation.value, translator)}</td><td>{cell(edge.target_id)}</td>"
        f"<td>{_owner(edge.as_of or view.as_of or translator.t('lineage.not_recorded'))}</td>"
        f"<td>{_render_sources(edge.source_refs, translator=translator)}</td>"
        f"<td>{_describe_derivation(edge.derivation, translator=translator)}</td></tr>"
    )


def _render_tables(
    view: LineageViewModel,
    page_nodes: Sequence[LineageNode],
    page_edges: Sequence[LineageEdge],
    *,
    context: QueryContext,
    route: str,
    total: int,
    off_page: int,
    translator: Translator,
) -> str:
    by_id = {node.node_id: node for node in page_nodes}
    path = view.evidence_path
    path_steps = {node_id: index for index, node_id in enumerate(path.node_ids)} if path else {}
    path_edges = set(path.edge_ids) if path else set()
    node_rows = "".join(
        _render_node_row(
            node, view, context=context, route=route, path_steps=path_steps, translator=translator
        )
        for node in page_nodes
    )
    edge_rows = "".join(
        _render_edge_row(
            edge,
            by_id,
            view,
            context=context,
            route=route,
            on_path=edge.edge_id in path_edges,
            translator=translator,
        )
        for edge in page_edges
    )
    edge_table = (
        f'<div role="region" aria-label="{_attr(translator.t("lineage.edges_region"))}" tabindex="0">'
        '<table class="lineage-table" data-lineage-table="edges">'
        f"<caption>{escape(translator.t('lineage.edges_caption', count=len(page_edges)))}</caption>"
        f'<thead><tr><th scope="col">{escape(translator.t("lineage.col_from"))}</th>'
        f'<th scope="col">{escape(translator.t("lineage.col_relation"))}</th>'
        f'<th scope="col">{escape(translator.t("lineage.col_to"))}</th>'
        f'<th scope="col">{escape(translator.t("lineage.col_as_of"))}</th>'
        f'<th scope="col">{escape(translator.t("lineage.col_sources"))}</th>'
        f'<th scope="col">{escape(translator.t("lineage.col_derivation"))}</th></tr></thead>'
        f"<tbody>{edge_rows}</tbody></table></div>"
        if page_edges
        else f'<p data-lineage-table="edges-empty">{escape(translator.t("lineage.no_edges"))}</p>'
    )
    texts = (
        "".join(
            f'<li data-edge-id="{_attr(edge.edge_id)}">'
            f"{_edge_sentence_markup(by_id, edge, view=view, translator=translator, context=context, route=route)}</li>"
            for edge in page_edges
        )
        or f"<li>{escape(translator.t('lineage.no_edges'))}</li>"
    )
    off_page_note = (
        f'<p data-off-page-relations="{off_page}">{escape(translator.t("lineage.off_page", count=off_page))}</p>'
        if off_page
        else ""
    )
    return (
        '<section id="lineage-table" class="lineage-table-view" data-lineage-view="table" aria-labelledby="lineage-table-heading" tabindex="-1">'
        f'<h2 id="lineage-table-heading">{escape(translator.t("lineage.table_heading"))}</h2>'
        f"<p>{escape(translator.t('lineage.table_intro'))}</p>{off_page_note}"
        f'<div role="region" aria-label="{_attr(translator.t("lineage.records_region"))}" tabindex="0">'
        '<table class="lineage-table" data-lineage-table="nodes">'
        f"<caption>{escape(translator.t('lineage.records_caption', count=len(page_nodes), total=total))}</caption>"
        f'<thead><tr><th scope="col">{escape(translator.t("lineage.col_record"))}</th>'
        f'<th scope="col">{escape(translator.t("lineage.col_type"))}</th>'
        f'<th scope="col">{escape(translator.t("lineage.col_status"))}</th>'
        f'<th scope="col">{escape(translator.t("lineage.col_depth"))}</th>'
        f'<th scope="col">{escape(translator.t("lineage.col_evidence_path"))}</th>'
        f'<th scope="col">{escape(translator.t("lineage.col_hash"))}</th>'
        f'<th scope="col">{escape(translator.t("lineage.col_as_of"))}</th>'
        f'<th scope="col">{escape(translator.t("lineage.col_sources"))}</th>'
        f'<th scope="col">{escape(translator.t("lineage.col_derivation"))}</th>'
        f'<th scope="col">{escape(translator.t("lineage.col_actions"))}</th></tr></thead>'
        f"<tbody>{node_rows}</tbody></table></div>{edge_table}"
        f"<h3>{escape(translator.t('lineage.text_view'))}</h3>"
        f'<ol class="lineage-text-view" aria-label="{_attr(translator.t("lineage.relations_text"))}">{texts}</ol>'
        "</section>"
    )


def _render_evidence_path(
    view: LineageViewModel, *, context: QueryContext, route: str, translator: Translator
) -> str:
    by_id = {node.node_id: node for node in view.nodes}
    edges = {edge.edge_id: edge for edge in view.edges}
    state = view.path_state
    path = view.evidence_path
    if path is not None:
        steps: list[str] = []
        for index, node_id in enumerate(path.node_ids):
            node = by_id[node_id]
            label = _node_label_markup(node, view, translator)
            steps.append(
                f'<li data-node-id="{_attr(node_id)}"><a href="{_attr(_link(context, route, node=node_id))}">'
                f"{label}</a> <small>{_record_type(node.record_type.value, translator)}</small>"
            )
            if index < len(path.edge_ids):
                edge = edges[path.edge_ids[index]]
                arrow = "→" if edge.source_id == node_id else "←"
                steps[-1] += (
                    f' <span class="lineage-hop">{arrow} {_relation(edge.relation.value, translator)}</span>'
                )
            steps[-1] += "</li>"
        body = (
            f"<p>{translator.html('lineage.shortest_path_summary', target=_node_label(by_id[path.target_id], view, translator), count=path.length)}</p>"
            f"<ol>{''.join(steps)}</ol>"
        )
    elif state is LineagePathState.NOT_ESTABLISHED:
        body = f"<p>{escape(translator.t('lineage.path_not_established'))}</p>"
    else:
        body = f"<p>{escape(translator.t('lineage.path_not_found', depth=view.query.depth))}</p>"
    return (
        f'<section class="lineage-evidence-path" data-path-state="{state.value}" '
        'aria-labelledby="lineage-path-heading">'
        f'<h2 id="lineage-path-heading">{escape(translator.t("lineage.path_heading"))}</h2>'
        f"{body}</section>"
    )


def _render_inspector(
    view: LineageViewModel,
    inspected_id: str | None,
    *,
    context: QueryContext,
    route: str,
    translator: Translator,
) -> str:
    node = view.node(inspected_id) if inspected_id else None
    heading = f'<h2 id="lineage-inspector-heading">{escape(translator.t("lineage.inspector_heading"))}</h2>'
    if node is None:
        body = escape(
            translator.t(
                "lineage.inspector_missing",
                record=inspected_id or translator.t("lineage.not_recorded"),
            )
        )
        return (
            '<aside class="lineage-inspector" data-lineage-inspector="missing" '
            f'aria-labelledby="lineage-inspector-heading"><p>{body}</p></aside>'
        )
    by_id = {item.node_id: item for item in view.nodes}

    def relation_items(edges: Sequence[LineageEdge], *, incoming: bool) -> str:
        items: list[str] = []
        for edge in edges:
            other_id = edge.source_id if incoming else edge.target_id
            other = by_id.get(other_id)
            sentence = _edge_sentence_markup(
                by_id,
                edge,
                view=view,
                translator=translator,
                context=context,
                route=route,
                link_node_id=other_id if other is not None else None,
            )
            items.append(f"<li>{sentence}</li>")
        return (
            f"<ul>{''.join(items)}</ul>"
            if items
            else f"<p>{escape(translator.t('lineage.not_recorded'))}</p>"
        )

    incoming = [edge for edge in view.edges if edge.target_id == node.node_id]
    outgoing = [edge for edge in view.edges if edge.source_id == node.node_id]
    metadata = "".join(
        f"<div><dt>{_owner(key)}</dt><dd>{_owner(value)}</dd></div>" for key, value in node.metadata
    )
    bounds = (
        ""
        if node.node_id in view.depths
        else f"<p>{escape(translator.t('lineage.inspector_outside_bounds'))}</p>"
    )
    label = _node_label_markup(node, view, translator)
    as_of = node.as_of or view.as_of or translator.t("lineage.not_recorded")
    snapshot = node.snapshot_token or view.snapshot_token or translator.t("lineage.not_recorded")
    return (
        f'<aside class="lineage-inspector" data-lineage-inspector="{_attr(node.node_id)}" '
        f'aria-labelledby="lineage-inspector-heading">{heading}{bounds}'
        '<dl class="lineage-inspector-details">'
        f"<div><dt>{escape(translator.t('lineage.label_record_id'))}</dt><dd>{_owner(node.node_id)}</dd></div>"
        f"<div><dt>{escape(translator.t('lineage.label'))}</dt><dd>{label}</dd></div>"
        f"<div><dt>{escape(translator.t('lineage.col_type'))}</dt><dd>{_record_type(node.record_type.value, translator)}</dd></div>"
        f"<div><dt>{escape(translator.t('lineage.col_status'))}</dt><dd>{_status(node.status, translator)}</dd></div>"
        f"<div><dt>{escape(translator.t('lineage.col_hash'))}</dt><dd>{_describe_hash(node, translator=translator)}</dd></div>"
        f"<div><dt>{escape(translator.t('lineage.col_as_of'))}</dt><dd>{_owner(as_of)}</dd></div>"
        f"<div><dt>{escape(translator.t('lineage.label_snapshot'))}</dt><dd>{_owner(snapshot)}</dd></div>"
        f"<div><dt>{escape(translator.t('lineage.label_source_refs'))}</dt><dd>{_render_sources(node.source_refs, translator=translator)}</dd></div>"
        f"<div><dt>{escape(translator.t('lineage.col_derivation'))}</dt><dd>{_describe_derivation(node.derivation, translator=translator)}</dd></div>"
        f"{metadata}"
        f"<div><dt>{escape(translator.t('lineage.incoming'))}</dt><dd>{relation_items(incoming, incoming=True)}</dd></div>"
        f"<div><dt>{escape(translator.t('lineage.outgoing'))}</dt><dd>{relation_items(outgoing, incoming=False)}</dd></div>"
        "</dl>"
        f'<p><a href="{_attr(_link(context, route, record_id=node.node_id, node=None, path_to=None, cursor=None))}">'
        f"{escape(translator.t('lineage.trace_from_record'))}</a></p></aside>"
    )


def _render_disconnected(
    view: LineageViewModel, *, context: QueryContext, route: str, translator: Translator
) -> str:
    if view.disconnected:
        items = "".join(
            f'<li data-node-id="{_attr(node.node_id)}"><a href="{_attr(_link(context, route, node=node.node_id))}">'
            f"{_node_label_markup(node, view, translator)}</a> <small>{_owner(node.node_id)} · "
            f"{_record_type(node.record_type.value, translator)}</small></li>"
            for node in view.disconnected
        )
        note = translator.t(
            "lineage.disconnected_partial" if view.partial else "lineage.disconnected_complete"
        )
        body = f"<p>{escape(note)}</p><ul>{items}</ul>"
    elif view.partial:
        body = f"<p>{escape(translator.t('lineage.disconnected_none_partial'))}</p>"
    else:
        body = f"<p>{escape(translator.t('lineage.disconnected_none_complete'))}</p>"
    outside = (
        f"<p>{escape(translator.t('lineage.outside_bounds', count=view.outside_bounds))}</p>"
        if view.outside_bounds
        else ""
    )
    return (
        f'<section class="lineage-disconnected" data-disconnected-count="{len(view.disconnected)}" '
        f'aria-labelledby="lineage-disconnected-heading"><h2 id="lineage-disconnected-heading">'
        f"{escape(translator.t('lineage.disconnected_heading'))}</h2>{body}{outside}</section>"
    )


def _render_bounds(
    view: LineageViewModel, *, context: QueryContext, route: str, translator: Translator
) -> str:
    query = view.query
    hidden = "".join(
        f'<input type="hidden" name="{_attr(key)}" value="{_attr(value)}">'
        for key, value in sorted(query_values(context).items())
        if key not in _MANAGED_KEYS and key != "view"
    )

    def checkboxes(
        domain: str, name: str, legend: str, options: Sequence[StrEnum], chosen: Sequence[StrEnum]
    ) -> str:
        boxes = "".join(
            f'<label><input type="checkbox" name="{name}" value="{option.value}"'
            f"{' checked' if option in chosen else ''}> "
            f"{translator.label(domain, option.value)}</label> "
            for option in options
        )
        return (
            f"<fieldset><legend>{escape(legend)} "
            f"({escape(translator.t('lineage.none_selected_all'))})</legend>{boxes}</fieldset>"
        )

    directions = "".join(
        f'<option value="{option.value}"{" selected" if option is query.direction else ""}>'
        f"{translator.label('lineage_direction', option.value)}</option>"
        for option in LINEAGE_DIRECTIONS
    )
    display_notes = []
    for note in query.display_notes:
        params = dict(note.params)
        if "name" in params:
            params["name"] = translator.t(f"lineage.{params['name']}")
        display_notes.append(translator.html(note.key, **params))
    notes = "".join(f"<li>{note}</li>" for note in display_notes)
    applied = translator.t(
        "lineage.applied_bounds",
        direction=translator.t(f"label.lineage_direction.{query.direction.value}"),
        depth=query.depth,
        page_size=query.page_size,
        relations=translator.join(
            translator.t(f"label.lineage_relation.{item.value}") for item in query.relations
        )
        or translator.t("lineage.all"),
        record_types=translator.join(
            translator.t(f"label.lineage_record_type.{item.value}") for item in query.record_types
        )
        or translator.t("lineage.all"),
    )
    return (
        f'<section class="lineage-bounds" aria-labelledby="lineage-bounds-heading" data-depth="{query.depth}" '
        f'data-direction="{query.direction.value}" data-page-size="{query.page_size}">'
        f'<h2 id="lineage-bounds-heading">{escape(translator.t("lineage.bounds_heading"))}</h2>'
        f"<p>{escape(applied)} {escape(translator.t('lineage.bounds_limit', depth=MAX_DEPTH, nodes=MAX_NODES))}</p>"
        f"{f'<ul class=lineage-notes>{notes}</ul>' if notes else ''}"
        f'<form class="lineage-filters" action="/" method="get" aria-label="{_attr(translator.t("lineage.bounds_heading"))}">'
        f'<input type="hidden" name="view" value="{_attr(route)}">{hidden}'
        f'<label>{escape(translator.t("lineage.direction"))} <select name="direction">{directions}</select></label> '
        f'<label>{escape(translator.t("lineage.depth"))} <input type="number" name="depth" min="1" max="{MAX_DEPTH}" value="{query.depth}"></label> '
        f'<label>{escape(translator.t("lineage.page_size"))} <input type="number" name="page_size" min="1" max="{MAX_PAGE_SIZE}" value="{query.page_size}"></label>'
        f"{checkboxes('lineage_relation', 'relations', translator.t('lineage.col_relation'), LINEAGE_RELATIONS, query.relations)}"
        f"{checkboxes('lineage_record_type', 'record_types', translator.t('lineage.record_types'), LINEAGE_RECORD_TYPES, query.record_types)}"
        f'<button type="submit">{escape(translator.t("lineage.apply_bounds"))}</button></form></section>'
    )


def _render_partial(
    view: LineageViewModel, *, context: QueryContext, route: str, translator: Translator
) -> str:
    next_cursor = view.pagination.next_cursor
    dangling = (
        f"<p>{escape(translator.t('lineage.dangling_edges', count=view.dangling_edges))}</p>"
        if view.dangling_edges
        else ""
    )
    nxt = ""
    if next_cursor is not None:
        href = _link(
            context, route, cursor=next_cursor, snapshot_token=view.snapshot_token, page=None
        )
        snapshot = _owner(view.snapshot_token or translator.t("lineage.not_recorded"))
        nxt = (
            f'<p><a class="lineage-next-cursor" data-lineage-next-cursor="{_attr(next_cursor)}" '
            f'href="{_attr(href)}">{escape(translator.t("lineage.next_page"))}</a>'
            f"{translator.t('lineage.next_page_snapshot', snapshot=snapshot)}</p>"
        )
    return (
        '<section class="lineage-partial" role="status" data-lineage-state="partial" '
        'data-pagination-complete="false" aria-labelledby="lineage-partial-heading">'
        f'<h2 id="lineage-partial-heading">{escape(translator.t("lineage.partial_heading"))}</h2>'
        f"<p>{escape(translator.t('lineage.partial_explanation'))}</p>"
        f"{dangling}{nxt}</section>"
    )


def _render_failure(
    view: LineageViewModel, *, context: QueryContext, route: str, translator: Translator
) -> str:
    failure = view.failure
    assert failure is not None
    restart = ""
    if failure.code in _RESTARTABLE:
        href = _link(
            context, route, cursor=None, snapshot_token=None, page=None, node=None, path_to=None
        )
        restart = (
            f'<p><a class="lineage-restart" href="{_attr(href)}">{escape(translator.t("lineage.restart"))}</a>'
            f"{escape(translator.t('lineage.restart_explanation'))}</p>"
        )
    title = translator.t(f"lineage.failure.{failure.code.value}")
    return (
        '<section class="lineage-withheld" role="alert" data-graph="withheld" '
        f'data-lineage-failure="{failure.code.value}"><h2>{escape(translator.t("lineage.failure_heading"))}</h2>'
        f"<p><strong>{escape(title)}.</strong> {_owner(failure.detail)}</p>"
        f"<p>{escape(translator.t('lineage.failure_explanation'))}</p>{restart}</section>"
    )


def render_reader_relationships(
    model: ManagerReadModel, *, query_context: QueryContext, translator: Translator,
) -> str:
    view = LineageViewModel.from_read_model(model, LineageQuery.from_query(query_context))
    if view.failure is not None:
        return _render_failure(view, context=query_context, route=LINEAGE_ROUTE, translator=translator)
    visible = view.visible_nodes
    if not visible:
        return (
            f'<section data-lineage-state="{view.state.value}">'
            f'<p>{escape(translator.t("lineage.empty_scope"))}</p></section>'
        )
    window = PageWindow.from_query(
        {**query_values(query_context), "page_size": str(view.query.page_size)}, total=len(visible),
    )
    nodes = visible[window.start:window.stop]
    identifiers = {node.node_id for node in nodes}
    edges = tuple(edge for edge in view.visible_edges
                  if edge.source_id in identifiers and edge.target_id in identifiers)
    with suspend_source_support():
        inspector = _render_inspector(
            view, view.query.node or view.root_id, context=query_context,
            route=LINEAGE_ROUTE, translator=translator,
        )
    partial = (
        _render_partial(view, context=query_context, route=LINEAGE_ROUTE, translator=translator)
        if view.partial else ""
    )
    return (
        f'<section data-lineage-state="{view.state.value}">'
        + partial
        + _render_graph(view, nodes, edges, context=query_context, route=LINEAGE_ROUTE,
                        inspected_id=view.query.node or view.root_id, translator=translator)
        + _render_evidence_path(view, context=query_context, route=LINEAGE_ROUTE, translator=translator)
        + _render_tables(view, nodes, edges, context=query_context, route=LINEAGE_ROUTE,
                         total=len(visible), off_page=len(view.visible_edges)-len(edges),
                         translator=translator)
        + f'<details><summary>{escape(translator.t("reader.mode.expert"))}</summary>{inspector}</details>'
        + '</section>'
    )


def render_lineage(
    view_or_model: LineageViewModel | ManagerReadModel,
    *,
    query_context: QueryContext = None,
    route: str = LINEAGE_ROUTE,
    include_raw_json: bool = True,
    translator: Translator | None = None,
) -> str:
    """Render a Lineage fragment for a shared shell to mount."""

    selected_translator = _lineage_translator(translator)
    view = (
        view_or_model
        if isinstance(view_or_model, LineageViewModel)
        else LineageViewModel.from_read_model(view_or_model, LineageQuery.from_query(query_context))
    )
    model = view.read_model
    display_model = _display_model(view, selected_translator)
    source_ids = selected_translator.join(_owner(source.source_id) for source in model.source_refs)
    sources = source_ids or selected_translator.t("lineage.none_recorded")
    derivation_parts = [
        _owner(part)
        for part in (model.derivation.kind, model.derivation.rule, model.derivation.version)
        if part
    ]
    derivation = " · ".join(derivation_parts) or selected_translator.t("lineage.not_recorded_short")
    observed = (
        _owner(model.as_of) if model.as_of else escape(selected_translator.t("lineage.unavailable"))
    )
    snapshot = (
        _owner(model.snapshot_token)
        if model.snapshot_token
        else escape(selected_translator.t("lineage.unavailable"))
    )
    pieces = [
        f'<section class="lineage-page" data-integration-hook="{LINEAGE_INTEGRATION_HOOK}" '
        f'data-lineage-state="{view.state.value}" data-read-status="{display_model.availability.status.value}">',
        f'<p class="eyebrow">{escape(selected_translator.t("lineage.page_eyebrow"))}</p>',
        f'<h1 class="page-title" data-page-title tabindex="-1">{escape(selected_translator.t("lineage.page_title"))}</h1>',
        f'<p class="page-intro">{escape(selected_translator.t("lineage.page_intro"))}</p>',
        f'<p class="context-line"><span><strong>{escape(selected_translator.t("lineage.observed"))}</strong> {observed}</span>'
        f"<span><strong>{escape(selected_translator.t('lineage.snapshot'))}</strong> {snapshot}</span>"
        f"<span><strong>{escape(selected_translator.t('lineage.derivation'))}</strong> {derivation}</span>"
        f"<span><strong>{escape(selected_translator.t('lineage.sources'))}</strong> {sources}</span></p>",
        render_status_block(display_model, translator=selected_translator),
    ]
    if view.failure is not None:
        pieces.append(
            _render_failure(
                view, context=query_context, route=route, translator=selected_translator
            )
        )
    elif view.state is LineageState.EMPTY:
        pieces.append(
            render_operational_state(
                "empty",
                translator=selected_translator,
                detail=selected_translator.t("lineage.empty_scope"),
            )
        )
    else:
        pieces.append(
            _render_bounds(view, context=query_context, route=route, translator=selected_translator)
        )
        if view.partial:
            pieces.append(
                _render_partial(
                    view, context=query_context, route=route, translator=selected_translator
                )
            )
        if not view.nodes:
            pieces.append(
                render_operational_state(
                    "partial",
                    translator=selected_translator,
                    detail=selected_translator.t("lineage.empty_owner_page"),
                )
            )
        else:
            visible = view.visible_nodes
            window = PageWindow.from_query(
                {**query_values(query_context), "page_size": str(view.query.page_size)},
                total=len(visible),
            )
            page_nodes = visible[window.start : window.stop]
            on_page = {node.node_id for node in page_nodes}
            page_edges = tuple(
                edge
                for edge in view.visible_edges
                if edge.source_id in on_page and edge.target_id in on_page
            )
            inspected = view.query.node or view.root_id
            pieces.append(
                _render_graph(
                    view,
                    page_nodes,
                    page_edges,
                    context=query_context,
                    route=route,
                    inspected_id=inspected,
                    translator=selected_translator,
                )
            )
            pieces.append(
                _render_evidence_path(
                    view, context=query_context, route=route, translator=selected_translator
                )
            )
            pieces.append(
                _render_inspector(
                    view,
                    inspected,
                    context=query_context,
                    route=route,
                    translator=selected_translator,
                )
            )
            pieces.append(
                _render_tables(
                    view,
                    page_nodes,
                    page_edges,
                    context=query_context,
                    route=route,
                    total=len(visible),
                    off_page=len(view.visible_edges) - len(page_edges),
                    translator=selected_translator,
                )
            )
            pieces.append(
                _render_disconnected(
                    view, context=query_context, route=route, translator=selected_translator
                )
            )
            pieces.append(window.render(query_context, view=route, translator=selected_translator))
    if include_raw_json:
        pieces.append(
            f'<details class="raw-json lineage-raw-json"><summary>{escape(selected_translator.t("lineage.raw_json"))}</summary>'
            f"<pre>{escape(view.raw_json)}</pre></details>"
        )
    pieces.append("</section>")
    return "".join(pieces)


def lineage_view(
    provider: ManagerDataProvider,
    *,
    query_context: QueryContext = None,
    snapshot_token: str | None = None,
    record_id: str | None = None,
) -> LineageViewModel:
    """Read the public lineage resource once and project it."""

    query = LineageQuery.from_query(
        query_context, record_id=record_id, snapshot_token=snapshot_token
    )
    model = provider.read(LINEAGE_RESOURCE, snapshot_token=snapshot_token or query.snapshot_token)
    return LineageViewModel.from_read_model(model, query)


def render_lineage_view(
    source: ManagerDataProvider | ManagerReadModel,
    *,
    query_context: QueryContext = None,
    snapshot_token: str | None = None,
    record_id: str | None = None,
    route: str = LINEAGE_ROUTE,
    translator: Translator | None = None,
) -> str:
    """Read and render the public Lineage resource, or render a cached envelope."""

    if isinstance(source, ManagerReadModel):
        query = LineageQuery.from_query(
            query_context, record_id=record_id, snapshot_token=snapshot_token
        )
        view = LineageViewModel.from_read_model(source, query)
    else:
        view = lineage_view(
            source,
            query_context=query_context,
            snapshot_token=snapshot_token,
            record_id=record_id,
        )
    return render_lineage(view, query_context=query_context, route=route, translator=translator)


# --- deterministic fixtures and read-only provider -----------------------------


def _fixture_sources() -> tuple[SourceReference, ...]:
    return (
        SourceReference(
            source_id="lineage-fixture-source",
            owner="apex-research-public-records",
            kind="lineage",
            locator="fixture://apex-research/lineage",
            schema="lineage.v1",
            revision="fixture-v1",
        ),
        SourceReference(
            source_id="lineage-fixture-document",
            owner="apex-research-public-records",
            kind="source_document",
            locator="fixture://apex-research/documents/protocol",
            schema="document.v1",
            revision="fixture-v1",
        ),
    )


def _fixture_node(
    node_id: str,
    record_type: str,
    label: str,
    *,
    source: str = "lineage-fixture-source",
    **extra: object,
) -> dict[str, object]:
    return {
        "id": node_id,
        "record_type": record_type,
        "label": label,
        "status": "recorded",
        "as_of": "2026-10-03T09:00:00Z",
        "source_refs": [source],
        **extra,
    }


def _fixture_edge(source: str, relation: str, target: str) -> dict[str, object]:
    return {
        "id": f"{source}|{relation}|{target}",
        "source": source,
        "target": target,
        "relation": relation,
        "as_of": "2026-10-03T09:00:00Z",
        "source_refs": ["lineage-fixture-source"],
    }


def _complete_graph() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    nodes = [
        _fixture_node("conclusion-1", "conclusion", "Protocol conclusion"),
        _fixture_node(
            "evidence-1",
            "evidence",
            "Protocol evidence",
            hash="sha256:" + "1" * 64,
            verified_hash="sha256:" + "1" * 64,
        ),
        _fixture_node("evidence-2", "evidence", "Replication evidence"),
        _fixture_node("evidence-3", "evidence", "Superseded evidence"),
        _fixture_node(
            "artifact-1",
            "artifact",
            "Evidence report",
            hash="sha256:" + "a" * 64,
            verified_hash="sha256:" + "a" * 64,
        ),
        _fixture_node(
            "run-1",
            "run",
            "Formal run",
            derivation={"kind": "direct", "inputs": ["lineage-fixture-source"], "version": "v1"},
        ),
        _fixture_node("campaign-1", "campaign", "Research campaign"),
        _fixture_node("candidate-1", "candidate", "Candidate"),
        _fixture_node("genome-1", "genome", "Strategy genome"),
        _fixture_node("memory-1", "memory", "Research memory"),
        _fixture_node(
            "document-1", "source_document", "Protocol document", source="lineage-fixture-document"
        ),
        _fixture_node(
            "document-orphan", "source_document", "Unlinked note", source="lineage-fixture-document"
        ),
    ]
    edges = [
        _fixture_edge("evidence-1", "supports", "conclusion-1"),
        _fixture_edge("evidence-2", "supports", "conclusion-1"),
        _fixture_edge("evidence-2", "supersedes", "evidence-3"),
        _fixture_edge("artifact-1", "supports", "evidence-1"),
        _fixture_edge("run-1", "produces", "artifact-1"),
        _fixture_edge("campaign-1", "produces", "candidate-1"),
        _fixture_edge("candidate-1", "derives", "run-1"),
        _fixture_edge("genome-1", "informs", "conclusion-1"),
        _fixture_edge("memory-1", "informs", "genome-1"),
        _fixture_edge("document-1", "documents", "evidence-2"),
    ]
    return nodes, edges


def _large_graph(node_count: int) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """A deterministic binary tree: record ``n`` supports its parent ``n // 2``."""

    nodes = [
        _fixture_node(
            f"node-{index:04d}",
            "conclusion" if index == 1 else "evidence",
            f"Record {index}",
        )
        for index in range(1, node_count + 1)
    ]
    edges = [
        _fixture_edge(f"node-{index:04d}", "supports", f"node-{index // 2:04d}")
        for index in range(2, node_count + 1)
    ]
    return nodes, edges


def _fixture_payload(
    state: LineageFixtureState, *, size: int
) -> tuple[dict[str, object], str | None]:
    nodes, edges = _large_graph(size) if state is LineageFixtureState.LARGE else _complete_graph()
    root = "node-0001" if state is LineageFixtureState.LARGE else "conclusion-1"
    pagination: dict[str, object] = {
        "cursor": None,
        "next_cursor": None,
        "has_more": False,
        "cursor_state": "valid",
        "complete": True,
    }
    snapshot: str | None = f"lineage-{state.value}-v0"
    if state is LineageFixtureState.PARTIAL:
        nodes = [node for node in nodes if node["id"] not in {"memory-1", "document-orphan"}]
        pagination.update(has_more=True, next_cursor="cursor-2", complete=False)
    elif state is LineageFixtureState.CURSOR_EXPIRED:
        pagination.update(cursor="cursor-1", cursor_state="expired")
    elif state is LineageFixtureState.SNAPSHOT_DRIFT:
        pagination.update(cursor="cursor-2", snapshot_token="lineage-earlier-v0")
    elif state is LineageFixtureState.HASH_MISMATCH:
        nodes[1] = {**nodes[1], "verified_hash": "sha256:" + "f" * 64}
    payload: dict[str, object] = {
        "schema": "manager-gui.lineage.v0-unknown"
        if state is LineageFixtureState.UNKNOWN_SCHEMA
        else LINEAGE_SCHEMA,
        "root": root,
        "nodes": nodes,
        "edges": edges,
        "pagination": pagination,
    }
    if state in {LineageFixtureState.COMPLETE, LineageFixtureState.LARGE}:
        payload["content_hash"] = lineage_content_hash(nodes, edges)
    if state is LineageFixtureState.EMPTY:
        return {}, None
    if state is LineageFixtureState.API_UNAVAILABLE:
        return {}, None
    return payload, snapshot


def build_lineage_fixture(
    state: LineageFixtureState | str = LineageFixtureState.COMPLETE, *, size: int = 300
) -> ManagerReadModel:
    """Build a fresh deterministic Lineage envelope without filesystem access."""

    selected = LineageFixtureState(state)
    payload, snapshot = _fixture_payload(selected, size=size)
    sources = _fixture_sources()
    status, complete, retryable = ReadModelStatus.KNOWN, True, False
    reason = "The fixture contains the published lineage projection."
    errors: tuple[ReadModelError, ...] = ()
    as_of: str | None = "2026-10-03T09:00:00Z"
    if selected is LineageFixtureState.EMPTY:
        status, complete, as_of = ReadModelStatus.MISSING, False, None
        reason = "No lineage records are published in this scope."
    elif selected is LineageFixtureState.PARTIAL:
        complete = False
        reason = "Only the first lineage page is published."
        errors = (
            ReadModelError(
                code="lineage_pagination_partial",
                message="Further lineage pages exist; absence of a link is not proven.",
                source_ref=sources[0].source_id,
            ),
        )
    elif selected is LineageFixtureState.CURSOR_EXPIRED:
        status, complete = ReadModelStatus.STALE, False
        reason = "The lineage cursor expired."
        errors = (
            ReadModelError(
                code="lineage_cursor_expired",
                message="The cursor is no longer valid.",
                source_ref=sources[0].source_id,
                retryable=True,
            ),
        )
    elif selected is LineageFixtureState.API_UNAVAILABLE:
        status, complete, retryable, as_of = ReadModelStatus.API_UNAVAILABLE, False, True, None
        reason = "The approved public lineage read API is unavailable."
        errors = (
            ReadModelError(
                code="lineage_api_unavailable",
                message="No private-storage fallback is permitted for lineage reads.",
                source_ref=sources[0].source_id,
                retryable=True,
            ),
        )
    return ManagerReadModel(
        data=cast(JSONValue, payload),
        source_refs=() if selected is LineageFixtureState.EMPTY else sources,
        as_of=as_of,
        snapshot_token=snapshot,
        derivation=Derivation(
            kind="direct",
            inputs=tuple(source.source_id for source in sources),
            version="lineage-fixture-v0",
        ),
        availability=Availability(
            status=status, complete=complete, reason=reason, retryable=retryable
        ),
        errors=errors,
    )


@dataclass(frozen=True, slots=True)
class LineageFixtureProvider:
    """Read-only provider serving one deterministic Lineage fixture."""

    state: LineageFixtureState

    def __init__(self, state: LineageFixtureState | str = LineageFixtureState.COMPLETE) -> None:
        object.__setattr__(self, "state", LineageFixtureState(state))

    def read(
        self,
        resource: str = LINEAGE_RESOURCE,
        *,
        snapshot_token: str | None = None,
    ) -> ManagerReadModel:
        # The fixture is not a mutable backend; the view itself detects drift.
        del snapshot_token
        if resource not in {LINEAGE_RESOURCE, LINEAGE_ROUTE}:
            raise ValueError(f"lineage fixture does not serve resource {resource!r}")
        return build_lineage_fixture(self.state)


def lineage_fixture_provider(
    state: LineageFixtureState | str = LineageFixtureState.COMPLETE,
) -> LineageFixtureProvider:
    return LineageFixtureProvider(state)


# Compatibility names mirror the other page modules while retaining one implementation.
LineageGraphViewModel = LineageViewModel
BoundedLineageViewModel = LineageViewModel
LineageGraphFixtureState = LineageFixtureState
LineageGraphProvider = LineageFixtureProvider
build_lineage_graph_fixture = build_lineage_fixture
lineage_graph_fixture_provider = lineage_fixture_provider
bounded_lineage_view = lineage_view
render_lineage_graph = render_lineage
render_lineage_graph_view = render_lineage_view


__all__ = [
    "DEFAULT_DEPTH",
    "DEFAULT_PAGE_SIZE",
    "LINEAGE_DIRECTIONS",
    "LINEAGE_FIXTURE_STATES",
    "LINEAGE_INTEGRATION_HOOK",
    "LINEAGE_INTEGRATION_HOOK_PATH",
    "LINEAGE_RECORD_TYPES",
    "LINEAGE_RELATIONS",
    "LINEAGE_RESOURCE",
    "LINEAGE_ROUTE",
    "LINEAGE_SCHEMA",
    "MAX_DEPTH",
    "MAX_EDGES",
    "MAX_NODES",
    "MAX_PAGE_SIZE",
    "NOT_RECORDED",
    "SUPPORTED_LINEAGE_SCHEMAS",
    "BoundedLineageViewModel",
    "LineageDerivation",
    "LineageDirection",
    "LineageEdge",
    "LineageFailure",
    "LineageFailureInfo",
    "LineageFixtureProvider",
    "LineageFixtureState",
    "LineageGraphFixtureState",
    "LineageGraphProvider",
    "LineageGraphViewModel",
    "LineageInspector",
    "LineageIntegrityError",
    "LineageNode",
    "LineagePagination",
    "LineagePath",
    "LineagePathState",
    "LineageQuery",
    "LineageRecordType",
    "LineageRelation",
    "LineageSourceRef",
    "LineageState",
    "LineageView",
    "LineageViewModel",
    "bounded_lineage_view",
    "build_lineage_fixture",
    "build_lineage_graph_fixture",
    "lineage_content_hash",
    "lineage_fixture_provider",
    "lineage_graph_fixture_provider",
    "lineage_view",
    "render_lineage",
    "render_lineage_graph",
    "render_lineage_graph_view",
    "render_lineage_view",
    "shortest_evidence_path",
]
