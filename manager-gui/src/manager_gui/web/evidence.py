"""Read-only Evidence Ledger and Artifact verification view.

The :func:`render_evidence_view` hook accepts either a ``ManagerReadModel`` or
an object exposing only ``read(resource, snapshot_token=...)`` from the public
``ManagerDataProvider`` seam.  The envelope's ``data`` is expected to be a JSON
object containing ``ledger`` (or ``evidence_ledger``), with optional
``conclusion``, ``decision``, ``evidence_level``, ``evidence_kind``
(``candidate`` or ``protocol_conforming``), ``sections``, ``sources``,
``limitations``, ``blockers``, ``incompatibilities``, ``records`` and
``artifacts``.  A section or record may repeat those fields and may carry
source IDs or explicit source locators.  Artifacts may contain ``name``,
``media_type``, ``logical_role``, ``hash``, ``producer``, ``runtime`` or
``runtime_version``, ``data_version``, ``verification_status`` and a public
``locator``/``artifact_link``.  The envelope remains authoritative for
``source_refs``, ``as_of``, ``snapshot_token``, ``availability``, errors and
raw JSON.

The module only projects already-published JSON into immutable view models and
HTML.  It never recalculates metrics, adjudicates or promotes evidence, reads
private SQLite/filesystem state, dereferences artifacts, or exposes a write,
retry, or revalidation operation.  Candidate evidence is rendered in a
separate group and is never relabelled as protocol-conforming evidence.  The
integration hook is :func:`render_evidence_view`; shell routing is intentionally
owned by a later integration slice.
"""

# HTML fragments intentionally keep readable markup even when a line is long.
# ruff: noqa: E501

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from html import escape
from typing import TypeAlias, cast

from ..models import (
    Availability,
    Derivation,
    JSONValue,
    ManagerReadModel,
    ReadModelError,
    ReadModelStatus,
    SourceReference,
)
from ..provider import ManagerDataProvider
from .i18n import Translator
from .i18n.catalog.l4_evidence import page_translator
from .locators import public_locator
from .navigation import PageWindow, context_link
from .status import render_operational_state, render_status_block

EVIDENCE_RESOURCE = "evidence"
EVIDENCE_ROUTE = "evidence"
EVIDENCE_INTEGRATION_HOOK = "evidence-view"
EVIDENCE_INTEGRATION_HOOK_PATH = "manager_gui.web.evidence.render_evidence_view"
NOT_RECORDED = "not recorded"

QueryContext: TypeAlias = str | Mapping[str, object] | None


class EvidenceKind(StrEnum):
    """The provenance class of evidence, kept distinct in every projection."""

    CANDIDATE = "candidate"
    PROTOCOL_CONFORMING = "protocol_conforming"
    NOT_RECORDED = "not_recorded"


class EvidenceLevel(StrEnum):
    """Owner-published level labels; unknown labels remain not recorded."""

    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CANDIDATE = "candidate"
    PROTOCOL_CONFORMING = "protocol_conforming"
    NOT_RECORDED = "not_recorded"


class EvidenceOutcome(StrEnum):
    """An outcome whose meaning must not be collapsed by presentation."""

    PASS = "pass"
    FAIL = "fail"
    EVALUATED = "evaluated"
    NOT_EVALUATED = "not_evaluated"
    BLOCKED = "blocked"
    INCOMPARABLE = "incomparable"
    UNAVAILABLE = "unavailable"
    UNKNOWN_SCHEMA = "unknown_schema"


EvidenceStatus = EvidenceOutcome
EvidenceClass = EvidenceKind


class ArtifactVerificationStatus(StrEnum):
    """Artifact verification states, including the reason for integrity failure."""

    VERIFIED = "verified"
    PASS = "pass"
    FAIL = "fail"
    HASH_MISMATCH = "hash_mismatch"
    MISSING_ARTIFACT = "missing_artifact"
    MISSING = "missing_artifact"
    UNKNOWN_SCHEMA = "unknown_schema"
    UNAVAILABLE = "unavailable"
    NOT_EVALUATED = "not_evaluated"
    BLOCKED = "blocked"
    INCOMPARABLE = "incomparable"


ArtifactStatus = ArtifactVerificationStatus
VerificationStatus = ArtifactVerificationStatus


class EvidenceFixtureState(StrEnum):
    """Deterministic states used by focused tests and local previews."""

    COMPLETE = "complete"
    CANDIDATE = "candidate"
    PROTOCOL_CONFORMING = "protocol_conforming"
    PASS = "pass"
    FAIL = "fail"
    EVALUATED = "evaluated"
    NOT_EVALUATED = "not_evaluated"
    BLOCKED = "blocked"
    INCOMPARABLE = "incomparable"
    HASH_MISMATCH = "hash_mismatch"
    MISSING_ARTIFACT = "missing_artifact"
    UNKNOWN_SCHEMA = "unknown_schema"
    UNAVAILABLE = "unavailable"
    PARTIAL = "partial"
    EMPTY = "empty"
    STALE = "stale"
    API_UNAVAILABLE = "api_unavailable"
    INTEGRITY_FAILURE = "integrity_failure"


EVIDENCE_LEVELS: tuple[EvidenceLevel, ...] = tuple(EvidenceLevel)
EVIDENCE_KINDS: tuple[EvidenceKind, ...] = tuple(EvidenceKind)
EVIDENCE_OUTCOMES: tuple[EvidenceOutcome, ...] = tuple(EvidenceOutcome)
ARTIFACT_VERIFICATION_STATUSES: tuple[ArtifactVerificationStatus, ...] = tuple(
    ArtifactVerificationStatus
)
EVIDENCE_FIXTURE_STATES: tuple[str, ...] = tuple(state.value for state in EvidenceFixtureState)


@dataclass(frozen=True, slots=True)
class EvidenceSourceRef:
    """A source pointer retained even when its public locator is unavailable."""

    source_id: str
    locator: str | None = None
    owner: str | None = None
    kind: str | None = None
    schema: str | None = None
    revision: str | None = None
    available: bool = True
    raw: Mapping[str, object] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        _require_text(self.source_id, "source_id")
        for name in ("locator", "owner", "kind", "schema", "revision"):
            _optional_text(getattr(self, name), name)
        if not isinstance(self.available, bool):
            raise ValueError("available must be a boolean")

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "locator": self.locator,
            "owner": self.owner,
            "kind": self.kind,
            "schema": self.schema,
            "revision": self.revision,
            "available": self.available,
        }


@dataclass(frozen=True, slots=True)
class EvidenceArtifact:
    """Public artifact metadata and an unmodified verification outcome."""

    artifact_id: str
    name: str
    media_type: str | None = None
    logical_role: str | None = None
    hash: str | None = None
    producer: str | None = None
    runtime_version: str | None = None
    data_version: str | None = None
    verification_status: ArtifactVerificationStatus = ArtifactVerificationStatus.NOT_EVALUATED
    verification_detail: str | None = None
    locator: str | None = None
    source_refs: tuple[EvidenceSourceRef, ...] = ()
    raw_status: str | None = None
    raw: Mapping[str, object] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        _require_text(self.artifact_id, "artifact_id")
        _require_text(self.name, "name")
        for name in (
            "media_type",
            "logical_role",
            "hash",
            "producer",
            "runtime_version",
            "data_version",
            "verification_detail",
            "locator",
            "raw_status",
        ):
            _optional_text(getattr(self, name), name)
        if not isinstance(self.verification_status, ArtifactVerificationStatus):
            raise ValueError("verification_status must be an ArtifactVerificationStatus")
        if not all(isinstance(ref, EvidenceSourceRef) for ref in self.source_refs):
            raise ValueError("source_refs must contain EvidenceSourceRef values")

    @property
    def runtime(self) -> str | None:
        return self.runtime_version

    @property
    def artifact_hash(self) -> str | None:
        return self.hash

    @property
    def hash_value(self) -> str | None:
        return self.hash

    @property
    def link(self) -> str | None:
        return self.locator

    @property
    def available(self) -> bool:
        return self.verification_status is not ArtifactVerificationStatus.MISSING_ARTIFACT

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "name": self.name,
            "media_type": self.media_type,
            "logical_role": self.logical_role,
            "hash": self.hash,
            "producer": self.producer,
            "runtime_version": self.runtime_version,
            "data_version": self.data_version,
            "verification_status": self.verification_status.value,
            "verification_detail": self.verification_detail,
            "locator": self.locator,
            "source_refs": [ref.to_dict() for ref in self.source_refs],
            "raw_status": self.raw_status,
        }


@dataclass(frozen=True, slots=True)
class EvidenceSection:
    """One bounded ledger section with its own provenance and limitations."""

    section_id: str
    title: str
    status: EvidenceOutcome = EvidenceOutcome.NOT_EVALUATED
    evidence_kind: EvidenceKind = EvidenceKind.NOT_RECORDED
    evidence_level: EvidenceLevel = EvidenceLevel.NOT_RECORDED
    summary: str | None = None
    source_refs: tuple[EvidenceSourceRef, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    raw: Mapping[str, object] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        _require_text(self.section_id, "section_id")
        _require_text(self.title, "title")
        _optional_text(self.summary, "summary")
        if not isinstance(self.status, EvidenceOutcome):
            raise ValueError("status must be an EvidenceOutcome")
        if not isinstance(self.evidence_kind, EvidenceKind):
            raise ValueError("evidence_kind must be an EvidenceKind")
        if not isinstance(self.evidence_level, EvidenceLevel):
            raise ValueError("evidence_level must be an EvidenceLevel")
        if not all(isinstance(item, str) and item.strip() for item in self.artifact_refs):
            raise ValueError("artifact_refs must contain non-empty strings")
        if not all(isinstance(item, str) and item.strip() for item in self.limitations):
            raise ValueError("limitations must contain non-empty strings")

    @property
    def is_candidate(self) -> bool:
        return self.evidence_kind is EvidenceKind.CANDIDATE

    @property
    def is_protocol_conforming(self) -> bool:
        return self.evidence_kind is EvidenceKind.PROTOCOL_CONFORMING

    def to_dict(self) -> dict[str, object]:
        return {
            "section_id": self.section_id,
            "title": self.title,
            "status": self.status.value,
            "evidence_kind": self.evidence_kind.value,
            "evidence_level": self.evidence_level.value,
            "summary": self.summary,
            "source_refs": [ref.to_dict() for ref in self.source_refs],
            "artifact_refs": list(self.artifact_refs),
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """An evidence item; candidate items remain candidate in every field."""

    record_id: str
    label: str
    status: EvidenceOutcome = EvidenceOutcome.NOT_EVALUATED
    evidence_kind: EvidenceKind = EvidenceKind.NOT_RECORDED
    evidence_level: EvidenceLevel = EvidenceLevel.NOT_RECORDED
    summary: str | None = None
    sections: tuple[EvidenceSection, ...] = ()
    source_refs: tuple[EvidenceSourceRef, ...] = ()
    artifacts: tuple[EvidenceArtifact, ...] = ()
    limitations: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    incompatibilities: tuple[str, ...] = ()
    raw: Mapping[str, object] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        _require_text(self.record_id, "record_id")
        _require_text(self.label, "label")
        _optional_text(self.summary, "summary")
        if not isinstance(self.status, EvidenceOutcome):
            raise ValueError("status must be an EvidenceOutcome")
        if not isinstance(self.evidence_kind, EvidenceKind):
            raise ValueError("evidence_kind must be an EvidenceKind")
        if not isinstance(self.evidence_level, EvidenceLevel):
            raise ValueError("evidence_level must be an EvidenceLevel")
        for name in ("limitations", "blockers", "incompatibilities"):
            if not all(isinstance(item, str) and item.strip() for item in getattr(self, name)):
                raise ValueError(f"{name} must contain non-empty strings")

    @property
    def is_candidate(self) -> bool:
        return self.evidence_kind is EvidenceKind.CANDIDATE

    @property
    def is_protocol_conforming(self) -> bool:
        return self.evidence_kind is EvidenceKind.PROTOCOL_CONFORMING

    def to_dict(self) -> dict[str, object]:
        return {
            "record_id": self.record_id,
            "label": self.label,
            "status": self.status.value,
            "evidence_kind": self.evidence_kind.value,
            "evidence_level": self.evidence_level.value,
            "summary": self.summary,
            "sections": [section.to_dict() for section in self.sections],
            "source_refs": [ref.to_dict() for ref in self.source_refs],
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "limitations": list(self.limitations),
            "blockers": list(self.blockers),
            "incompatibilities": list(self.incompatibilities),
        }


@dataclass(frozen=True, slots=True)
class EvidenceLedger:
    """Typed ledger projection; no candidate item is promoted during parsing."""

    conclusion: str | None = None
    decision: str | None = None
    evidence_level: EvidenceLevel = EvidenceLevel.NOT_RECORDED
    evidence_kind: EvidenceKind = EvidenceKind.NOT_RECORDED
    status: EvidenceOutcome = EvidenceOutcome.NOT_EVALUATED
    sections: tuple[EvidenceSection, ...] = ()
    sources: tuple[EvidenceSourceRef, ...] = ()
    artifacts: tuple[EvidenceArtifact, ...] = ()
    limitations: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    incompatibilities: tuple[str, ...] = ()
    records: tuple[EvidenceRecord, ...] = ()
    raw: Mapping[str, object] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        for name in ("conclusion", "decision"):
            _optional_text(getattr(self, name), name)
        for name, expected in (
            ("evidence_level", EvidenceLevel),
            ("evidence_kind", EvidenceKind),
            ("status", EvidenceOutcome),
        ):
            if not isinstance(getattr(self, name), expected):
                raise ValueError(f"{name} has an invalid type")
        for name in ("limitations", "blockers", "incompatibilities"):
            if not all(isinstance(item, str) and item.strip() for item in getattr(self, name)):
                raise ValueError(f"{name} must contain non-empty strings")

    @property
    def candidate_evidence(self) -> tuple[EvidenceRecord, ...]:
        return tuple(item for item in self.records if item.is_candidate)

    @property
    def protocol_conforming_evidence(self) -> tuple[EvidenceRecord, ...]:
        return tuple(item for item in self.records if item.is_protocol_conforming)

    @property
    def candidate_records(self) -> tuple[EvidenceRecord, ...]:
        return self.candidate_evidence

    @property
    def protocol_records(self) -> tuple[EvidenceRecord, ...]:
        return self.protocol_conforming_evidence

    def to_dict(self) -> dict[str, object]:
        return {
            "conclusion": self.conclusion,
            "decision": self.decision,
            "evidence_level": self.evidence_level.value,
            "evidence_kind": self.evidence_kind.value,
            "status": self.status.value,
            "sections": [section.to_dict() for section in self.sections],
            "sources": [source.to_dict() for source in self.sources],
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "limitations": list(self.limitations),
            "blockers": list(self.blockers),
            "incompatibilities": list(self.incompatibilities),
            "records": [record.to_dict() for record in self.records],
        }


@dataclass(frozen=True, slots=True)
class EvidenceViewModel:
    """Deterministic, typed projection of one Evidence ``ManagerReadModel``."""

    read_model: ManagerReadModel
    ledger: EvidenceLedger

    @classmethod
    def from_read_model(cls, model: ManagerReadModel) -> EvidenceViewModel:
        payload = _ledger_payload(model.data)
        source_index = {source.source_id: source for source in model.source_refs}
        ledger = _parse_ledger(payload, source_index, model.availability.status)
        return cls(read_model=model, ledger=ledger)

    @property
    def conclusion(self) -> str | None:
        return self.ledger.conclusion

    @property
    def decision(self) -> str | None:
        return self.ledger.decision

    @property
    def evidence_level(self) -> EvidenceLevel:
        return self.ledger.evidence_level

    @property
    def evidence_kind(self) -> EvidenceKind:
        return self.ledger.evidence_kind

    @property
    def status(self) -> EvidenceOutcome:
        return self.ledger.status

    @property
    def sections(self) -> tuple[EvidenceSection, ...]:
        return self.ledger.sections

    @property
    def records(self) -> tuple[EvidenceRecord, ...]:
        return self.ledger.records

    @property
    def artifacts(self) -> tuple[EvidenceArtifact, ...]:
        return self.ledger.artifacts

    @property
    def sources(self) -> tuple[EvidenceSourceRef, ...]:
        return self.ledger.sources

    @property
    def source_refs(self) -> tuple[SourceReference, ...]:
        return self.read_model.source_refs

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
    def raw(self) -> Mapping[str, object]:
        return _mapping(self.read_model.data) or {}

    def artifact(self, artifact_id: str) -> EvidenceArtifact | None:
        return next((item for item in self.artifacts if item.artifact_id == artifact_id), None)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.read_model.schema,
            "ledger": self.ledger.to_dict(),
            "availability": self.read_model.availability.to_dict(),
            "source_refs": [source.to_dict() for source in self.read_model.source_refs],
            "as_of": self.read_model.as_of,
            "snapshot_token": self.read_model.snapshot_token,
            "errors": [error.to_dict() for error in self.read_model.errors],
        }


EvidenceLedgerViewModel = EvidenceViewModel
EvidenceView = EvidenceViewModel
ArtifactInspection = EvidenceArtifact
EvidenceSectionView = EvidenceSection


# --- parsing helpers -----------------------------------------------------------


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, field_name)


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


def _mapping(value: object) -> Mapping[str, object] | None:
    return cast(Mapping[str, object], value) if isinstance(value, Mapping) else None


def _sequence(value: object) -> tuple[object, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, bytearray)):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(value)
    if isinstance(value, Mapping):
        for key in ("items", "entries", "records", "values", "sections", "artifacts"):
            nested = value.get(key)
            if isinstance(nested, Sequence) and not isinstance(nested, (str, bytes, bytearray)):
                return tuple(nested)
        return (value,)
    return (value,)


def _first_text(item: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        value = _text(item.get(key))
        if value is not None:
            return value
    return None


def _normalise(value: object) -> str | None:
    text = _text(value)
    if text is None:
        return None
    return text.strip().lower().replace("-", "_").replace(" ", "_")


def _json_value(value: object) -> JSONValue:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("evidence payload must contain JSON-compatible values") from exc
    return cast(JSONValue, value)


def _text_list(item: Mapping[str, object], *keys: str) -> tuple[str, ...]:
    values: list[str] = []
    for key in keys:
        if key not in item:
            continue
        for raw in _sequence(item[key]):
            text = _text(raw)
            if text is not None:
                values.append(text)
                continue
            nested = _mapping(raw)
            if nested is not None:
                nested_text = _first_text(
                    nested, "text", "summary", "detail", "description", "message", "reason", "label"
                )
                if nested_text is not None:
                    values.append(nested_text)
    return tuple(dict.fromkeys(values))


def _ledger_payload(data: object) -> Mapping[str, object]:
    payload = _mapping(data)
    if payload is None:
        return {}
    for key in ("evidence_ledger", "evidenceLedger", "ledger"):
        nested = _mapping(payload.get(key))
        if nested is not None:
            return nested
    return payload


def _kind(value: object) -> EvidenceKind:
    normalised = _normalise(value)
    if normalised in {"candidate", "candidate_evidence", "candidate_record", "proposed"}:
        return EvidenceKind.CANDIDATE
    if normalised in {
        "protocol_conforming",
        "protocol_conformant",
        "protocol_evidence",
        "conforming",
        "formal",
    }:
        return EvidenceKind.PROTOCOL_CONFORMING
    return EvidenceKind.NOT_RECORDED


def _level(value: object) -> EvidenceLevel:
    normalised = _normalise(value)
    aliases = {
        "weak": EvidenceLevel.LOW,
        "medium": EvidenceLevel.MODERATE,
        "strong": EvidenceLevel.HIGH,
        "high_confidence": EvidenceLevel.HIGH,
        "not_recorded": EvidenceLevel.NOT_RECORDED,
        "unknown": EvidenceLevel.NOT_RECORDED,
    }
    if normalised in aliases:
        return aliases[normalised]
    if normalised is not None:
        try:
            return EvidenceLevel(normalised)
        except ValueError:
            pass
    return EvidenceLevel.NOT_RECORDED


def _outcome(value: object, default: EvidenceOutcome = EvidenceOutcome.NOT_EVALUATED) -> EvidenceOutcome:
    normalised = _normalise(value)
    aliases = {
        "passed": EvidenceOutcome.PASS,
        "success": EvidenceOutcome.PASS,
        "supported": EvidenceOutcome.PASS,
        "failed": EvidenceOutcome.FAIL,
        "failure": EvidenceOutcome.FAIL,
        "pending": EvidenceOutcome.NOT_EVALUATED,
        "not_evaluated": EvidenceOutcome.NOT_EVALUATED,
        "not_recorded": EvidenceOutcome.NOT_EVALUATED,
        "incompatible": EvidenceOutcome.INCOMPARABLE,
        "api_unavailable": EvidenceOutcome.UNAVAILABLE,
    }
    if normalised in aliases:
        return aliases[normalised]
    if normalised is not None:
        try:
            return EvidenceOutcome(normalised)
        except ValueError:
            return EvidenceOutcome.UNKNOWN_SCHEMA
    return default


def _artifact_status(value: object) -> ArtifactVerificationStatus:
    normalised = _normalise(value)
    aliases = {
        "verified": ArtifactVerificationStatus.VERIFIED,
        "valid": ArtifactVerificationStatus.VERIFIED,
        "passed": ArtifactVerificationStatus.PASS,
        "success": ArtifactVerificationStatus.PASS,
        "failed": ArtifactVerificationStatus.FAIL,
        "failure": ArtifactVerificationStatus.FAIL,
        "digest_mismatch": ArtifactVerificationStatus.HASH_MISMATCH,
        "hash_mismatch": ArtifactVerificationStatus.HASH_MISMATCH,
        "artifact_missing": ArtifactVerificationStatus.MISSING_ARTIFACT,
        "missing": ArtifactVerificationStatus.MISSING_ARTIFACT,
        "schema_unknown": ArtifactVerificationStatus.UNKNOWN_SCHEMA,
        "unknown": ArtifactVerificationStatus.UNKNOWN_SCHEMA,
        "api_unavailable": ArtifactVerificationStatus.UNAVAILABLE,
        "pending": ArtifactVerificationStatus.NOT_EVALUATED,
        "incompatible": ArtifactVerificationStatus.INCOMPARABLE,
    }
    if normalised in aliases:
        return aliases[normalised]
    if normalised is not None:
        try:
            return ArtifactVerificationStatus(normalised)
        except ValueError:
            return ArtifactVerificationStatus.UNKNOWN_SCHEMA
    return ArtifactVerificationStatus.NOT_EVALUATED


def _source_refs(
    item: Mapping[str, object], source_index: Mapping[str, SourceReference]
) -> tuple[EvidenceSourceRef, ...]:
    values: list[object] = []
    for key in ("source_ref", "source_id", "source_refs", "source_ids", "sources"):
        if key in item:
            values.extend(_sequence(item[key]))
    refs: list[EvidenceSourceRef] = []
    seen: set[tuple[str, str | None]] = set()
    for raw in values:
        nested = _mapping(raw)
        source_id = (
            _first_text(nested, "source_id", "sourceId", "id", "record_id", "ref")
            if nested is not None
            else _text(raw)
        )
        if source_id is None:
            continue
        source = source_index.get(source_id)
        locator = (
            _first_text(nested, "locator", "url", "uri", "href", "source_link")
            if nested is not None
            else None
        ) or (source.locator if source is not None else None)
        marker = (source_id, locator)
        if marker in seen:
            continue
        seen.add(marker)
        refs.append(
            EvidenceSourceRef(
                source_id=source_id,
                locator=locator,
                owner=(
                    _first_text(nested, "owner", "producer") if nested is not None else None
                )
                or (source.owner if source is not None else None),
                kind=(
                    _first_text(nested, "kind", "type") if nested is not None else None
                )
                or (source.kind if source is not None else None),
                schema=(
                    _first_text(nested, "schema", "schema_id") if nested is not None else None
                )
                or (source.schema if source is not None else None),
                revision=(
                    _first_text(nested, "revision", "version") if nested is not None else None
                )
                or (source.revision if source is not None else None),
                available=locator is not None,
                raw={} if nested is None else nested,
            )
        )
    return tuple(refs)


def _artifact_refs(item: Mapping[str, object]) -> tuple[str, ...]:
    values: list[str] = []
    for key in ("artifact_ref", "artifact_id", "artifact_refs", "artifact_ids", "artifacts"):
        if key not in item:
            continue
        for raw in _sequence(item[key]):
            nested = _mapping(raw)
            identifier = (
                _first_text(nested, "artifact_id", "artifactId", "id", "name")
                if nested is not None
                else _text(raw)
            )
            if identifier is not None:
                values.append(identifier)
    return tuple(dict.fromkeys(values))


def _parse_artifact(
    raw: object,
    index: int,
    source_index: Mapping[str, SourceReference],
) -> EvidenceArtifact | None:
    item = _mapping(raw)
    if item is None:
        name = _text(raw)
        if name is None:
            return None
        return EvidenceArtifact(
            artifact_id=name,
            name=name,
            verification_status=ArtifactVerificationStatus.MISSING_ARTIFACT,
            verification_detail="Artifact metadata was referenced but no artifact record was published.",
            raw={"name": name},
        )
    identifier = _first_text(item, "artifact_id", "artifactId", "id", "uid")
    name = _first_text(item, "name", "artifact_name", "filename", "title")
    if identifier is None:
        identifier = name or f"artifact-{index}"
    if name is None:
        name = identifier
    raw_status = _first_text(item, "verification_status", "verify_status", "status", "verification")
    locator = _first_text(item, "artifact_link", "artifact_url", "locator", "url", "uri", "href")
    refs = _source_refs(item, source_index)
    if locator is None:
        locator = next((ref.locator for ref in refs if ref.locator), None)
    return EvidenceArtifact(
        artifact_id=identifier,
        name=name,
        media_type=_first_text(item, "media_type", "mediaType", "mime_type", "mime"),
        logical_role=_first_text(item, "logical_role", "logicalRole", "role"),
        hash=_first_text(item, "hash", "artifact_hash", "digest", "sha256"),
        producer=_first_text(item, "producer", "produced_by", "producer_id"),
        runtime_version=_first_text(item, "runtime_version", "runtimeVersion", "runtime"),
        data_version=_first_text(item, "data_version", "dataVersion", "dataset_version"),
        verification_status=_artifact_status(raw_status),
        verification_detail=_first_text(
            item, "verification_detail", "verification_reason", "detail", "reason", "message"
        ),
        locator=locator,
        source_refs=refs,
        raw_status=raw_status,
        raw=item,
    )


def _parse_section(
    raw: object,
    index: int,
    source_index: Mapping[str, SourceReference],
    *,
    kind_hint: EvidenceKind = EvidenceKind.NOT_RECORDED,
) -> EvidenceSection | None:
    item = _mapping(raw)
    if item is None:
        title = _text(raw)
        if title is None:
            return None
        return EvidenceSection(section_id=f"section-{index}", title=title, evidence_kind=kind_hint)
    section_id = _first_text(item, "section_id", "sectionId", "id", "key") or f"section-{index}"
    title = _first_text(item, "title", "name", "label") or section_id
    kind = _kind(
        _first_text(item, "evidence_kind", "evidence_type", "kind", "classification", "tier")
    )
    if kind is EvidenceKind.NOT_RECORDED:
        kind = kind_hint
    return EvidenceSection(
        section_id=section_id,
        title=title,
        status=_outcome(_first_text(item, "status", "outcome", "evaluation_status")),
        evidence_kind=kind,
        evidence_level=_level(_first_text(item, "evidence_level", "level", "strength")),
        summary=_first_text(item, "summary", "description", "detail", "text"),
        source_refs=_source_refs(item, source_index),
        artifact_refs=_artifact_refs(item),
        limitations=_text_list(item, "limitations", "limits"),
        raw=item,
    )


def _parse_sections(
    item: Mapping[str, object],
    source_index: Mapping[str, SourceReference],
    *,
    kind_hint: EvidenceKind = EvidenceKind.NOT_RECORDED,
) -> tuple[EvidenceSection, ...]:
    raw_sections: list[object] = []
    for key in ("sections", "evidence_sections"):
        raw_value = item.get(key)
        if isinstance(raw_value, Mapping):
            raw_sections.extend(
                {"section_id": str(section_id), **(_mapping(value) or {"title": str(value)})}
                for section_id, value in raw_value.items()
            )
        else:
            raw_sections.extend(_sequence(raw_value))
    result: list[EvidenceSection] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_sections, start=1):
        section = _parse_section(raw, index, source_index, kind_hint=kind_hint)
        if section is not None and section.section_id not in seen:
            seen.add(section.section_id)
            result.append(section)
    return tuple(result)


def _parse_record(
    raw: object,
    index: int,
    source_index: Mapping[str, SourceReference],
    *,
    kind_hint: EvidenceKind = EvidenceKind.NOT_RECORDED,
) -> EvidenceRecord | None:
    item = _mapping(raw)
    if item is None:
        label = _text(raw)
        if label is None:
            return None
        return EvidenceRecord(record_id=f"evidence-{index}", label=label, evidence_kind=kind_hint)
    record_id = _first_text(item, "record_id", "recordId", "evidence_id", "evidenceId", "id")
    label = _first_text(item, "label", "title", "name", "summary")
    if record_id is None:
        record_id = label or f"evidence-{index}"
    if label is None:
        label = record_id
    kind = _kind(
        _first_text(item, "evidence_kind", "evidence_type", "kind", "classification", "tier")
    )
    if kind is EvidenceKind.NOT_RECORDED:
        kind = kind_hint
    sections = _parse_sections(item, source_index, kind_hint=kind)
    artifact_items = _sequence(item.get("artifacts"))
    artifacts = tuple(
        artifact
        for artifact_index, value in enumerate(artifact_items, start=1)
        if (artifact := _parse_artifact(value, artifact_index, source_index)) is not None
    )
    return EvidenceRecord(
        record_id=record_id,
        label=label,
        status=_outcome(_first_text(item, "status", "outcome", "evaluation_status")),
        evidence_kind=kind,
        evidence_level=_level(_first_text(item, "evidence_level", "level", "strength")),
        summary=_first_text(item, "summary", "description", "detail", "text"),
        sections=sections,
        source_refs=_source_refs(item, source_index),
        artifacts=artifacts,
        limitations=_text_list(item, "limitations", "limits"),
        blockers=_text_list(item, "blockers", "blocked_by", "blocking_reasons"),
        incompatibilities=_text_list(item, "incompatibilities", "incompatible_with", "incompatible_axes"),
        raw=item,
    )


def _parse_records(
    payload: Mapping[str, object], source_index: Mapping[str, SourceReference]
) -> tuple[EvidenceRecord, ...]:
    entries: list[tuple[object, EvidenceKind]] = []
    for key in ("records", "evidence_records", "items", "evidence_items"):
        entries.extend((raw, EvidenceKind.NOT_RECORDED) for raw in _sequence(payload.get(key)))
    entries.extend((raw, EvidenceKind.CANDIDATE) for raw in _sequence(payload.get("candidate_evidence")))
    entries.extend(
        (raw, EvidenceKind.PROTOCOL_CONFORMING)
        for raw in _sequence(payload.get("protocol_conforming_evidence"))
    )
    result: list[EvidenceRecord] = []
    seen: set[str] = set()
    for index, (raw, kind_hint) in enumerate(entries, start=1):
        record = _parse_record(raw, index, source_index, kind_hint=kind_hint)
        if record is not None and record.record_id not in seen:
            seen.add(record.record_id)
            result.append(record)
    return tuple(result)


def _parse_ledger(
    payload: Mapping[str, object],
    source_index: Mapping[str, SourceReference],
    read_status: ReadModelStatus,
) -> EvidenceLedger:
    top_kind = _kind(
        _first_text(payload, "evidence_kind", "evidence_type", "kind", "classification", "tier")
    )
    level_value = _first_text(payload, "evidence_level", "level", "strength")
    if level_value is None and top_kind in {
        EvidenceKind.CANDIDATE,
        EvidenceKind.PROTOCOL_CONFORMING,
    }:
        level_value = top_kind.value
    status = _outcome(_first_text(payload, "status", "outcome", "evaluation_status"))
    if "status" not in payload and "outcome" not in payload and "evaluation_status" not in payload:
        status = {
            ReadModelStatus.BLOCKED: EvidenceOutcome.BLOCKED,
            ReadModelStatus.INCOMPARABLE: EvidenceOutcome.INCOMPARABLE,
            ReadModelStatus.API_UNAVAILABLE: EvidenceOutcome.UNAVAILABLE,
            ReadModelStatus.INTEGRITY_FAILURE: EvidenceOutcome.BLOCKED,
            ReadModelStatus.MISSING: EvidenceOutcome.NOT_EVALUATED,
        }.get(read_status, status)
    sections = _parse_sections(payload, source_index, kind_hint=top_kind)
    records = _parse_records(payload, source_index)
    artifacts_values: list[object] = list(_sequence(payload.get("artifacts")))
    for record in records:
        artifacts_values.extend(record.artifacts)
    artifacts: list[EvidenceArtifact] = []
    seen_artifacts: set[str] = set()
    for index, raw in enumerate(artifacts_values, start=1):
        parsed = raw if isinstance(raw, EvidenceArtifact) else _parse_artifact(raw, index, source_index)
        if parsed is not None and parsed.artifact_id not in seen_artifacts:
            seen_artifacts.add(parsed.artifact_id)
            artifacts.append(parsed)
    sources = list(_source_refs(payload, source_index))
    for record in records:
        for source in record.source_refs:
            if (source.source_id, source.locator) not in {(x.source_id, x.locator) for x in sources}:
                sources.append(source)
    for artifact in artifacts:
        for source in artifact.source_refs:
            if (source.source_id, source.locator) not in {(x.source_id, x.locator) for x in sources}:
                sources.append(source)
    return EvidenceLedger(
        conclusion=_first_text(payload, "conclusion", "conclusion_text", "conclusion_statement"),
        decision=_first_text(payload, "decision", "decision_text", "decision_statement"),
        evidence_level=_level(level_value),
        evidence_kind=top_kind,
        status=status,
        sections=sections,
        sources=tuple(sources),
        artifacts=tuple(artifacts),
        limitations=_text_list(payload, "limitations", "limits"),
        blockers=_text_list(payload, "blockers", "blocked_by", "blocking_reasons"),
        incompatibilities=_text_list(
            payload, "incompatibilities", "incompatible_with", "incompatible_axes"
        ),
        records=records,
        raw=payload,
    )


# --- rendering -----------------------------------------------------------------


_FIXTURE_TEXT_KEYS: Mapping[str, str] = {
    "The protocol result is inspectable.": "fixture.evidence.conclusion",
    "Retain the published protocol result for review.": "fixture.evidence.decision",
    "Conclusion and decision": "fixture.evidence.section_conclusion",
    "Conclusion is linked to a public source and artifact.": "fixture.evidence.section_summary",
    "Candidate screening result": "fixture.evidence.candidate_label",
    "Candidate signal": "fixture.evidence.candidate_section",
    "A candidate result awaiting the frozen protocol.": "fixture.evidence.candidate_summary",
    "Candidate evidence is not a protocol result.": "fixture.evidence.candidate_limit",
    "Protocol result": "fixture.evidence.protocol_label",
    "Protocol evaluation": "fixture.evidence.protocol_section",
    "A result evaluated under the declared protocol.": "fixture.evidence.protocol_summary",
    "Synthetic fixture; not a live data gate.": "fixture.evidence.synthetic_limit",
    "Fixture data only.": "fixture.evidence.fixture_only",
    "This view does not recalculate metrics.": "fixture.evidence.ledger_limit",
    "Some protocol sections are outside the published scope.": "fixture.evidence.partial_limit",
    "The approved protocol source is blocked.": "fixture.evidence.blocker",
    "Data snapshots are not comparable.": "fixture.evidence.incomparable",
    "Failed protocol result": "fixture.evidence.failed_label",
    "Not evaluated result": "fixture.evidence.not_evaluated_label",
    "Declared hash does not match the observed bytes.": "fixture.evidence.artifact_hash_detail",
    "The published artifact cannot be located.": "fixture.evidence.artifact_missing_detail",
    "Artifact schema is not recognised by this reader.": "fixture.evidence.artifact_schema_detail",
    "The fixture contains the published Evidence Ledger projection.": "fixture.evidence.read_reason",
    "Only part of the Evidence Ledger is published in this scope.": "fixture.evidence.partial_reason",
    "Some protocol evidence sections are outside the indexed scope.": "fixture.evidence.partial_error",
    "The approved Evidence read seam is blocked.": "fixture.evidence.blocked_reason",
    "The fixture preserves a blocked evidence determination.": "fixture.evidence.blocked_error",
    "The evidence snapshots are incompatible.": "fixture.evidence.incomparable_reason",
    "The fixture preserves incomparable evidence rather than ranking it.": "fixture.evidence.incomparable_error",
    "The artifact verification did not pass its integrity gate.": "fixture.evidence.integrity_reason",
    "The artifact hash does not match the declared hash.": "fixture.evidence.hash_error",
    "The artifact schema is unknown to this reader.": "fixture.evidence.schema_error",
    "A referenced artifact is missing.": "fixture.evidence.missing_reason",
    "The evidence record references an unavailable artifact.": "fixture.evidence.missing_error",
    "The Evidence Ledger source is stale.": "fixture.evidence.stale_reason",
    "The published evidence is retained for historical inspection only.": "fixture.evidence.stale_error",
    "The approved public Evidence read API is unavailable.": "fixture.evidence.api_reason",
    "No private-storage fallback is permitted for Evidence reads.": "fixture.evidence.api_error",
}


def _display(value: object, fallback: str = NOT_RECORDED) -> str:
    text = _text(value)
    return text if text is not None else fallback


def _fixture_text(value: str | None, translator: Translator, *, is_fixture: bool = True) -> str | None:
    if value is None:
        return None
    key = _FIXTURE_TEXT_KEYS.get(value) if is_fixture else None
    return translator.t(key) if key is not None else value


def _owner_text(value: str | None, translator: Translator, *, is_fixture: bool) -> str:
    if value is None:
        return escape(translator.t("evidence.not_recorded"))
    if is_fixture and value in _FIXTURE_TEXT_KEYS:
        return escape(translator.t(_FIXTURE_TEXT_KEYS[value]))
    return f'<span data-owner-text="true">{escape(value)}</span>'


def _status_label(status: StrEnum, translator: Translator) -> str:
    if isinstance(status, EvidenceKind):
        return translator.label("evidence_kind", status.value)
    if isinstance(status, EvidenceLevel):
        return escape(translator.t(f"label.l4_evidence_level.{status.value}"))
    if isinstance(status, EvidenceOutcome):
        return translator.label("evidence_outcome", status.value)
    if isinstance(status, ArtifactVerificationStatus):
        return translator.label("artifact_verification", status.value)
    return escape(str(status.value).replace("_", " ").title())


def _kind_label(kind: EvidenceKind, translator: Translator) -> str:
    return translator.label("evidence_kind", kind.value)


def _fixture_status_model(
    model: ManagerReadModel, translator: Translator, *, is_fixture: bool
) -> ManagerReadModel:
    if not is_fixture:
        return model
    availability = replace(
        model.availability,
        reason=_fixture_text(model.availability.reason, translator) if model.availability.reason else None,
    )
    errors = tuple(
        replace(error, message=_fixture_text(error.message, translator) or error.message)
        for error in model.errors
    )
    return replace(model, availability=availability, errors=errors)


def _render_source_refs(
    refs: Sequence[EvidenceSourceRef], *, query_context: QueryContext = None, translator: Translator,
    is_fixture: bool = True,
) -> str:
    label = escape(translator.t("evidence.sources"))
    empty = escape(translator.t("evidence.not_recorded"))
    if not refs:
        return f'<div class="evidence-ref-group"><dt>{label}</dt><dd>{empty}</dd></div>'
    items: list[str] = []
    for ref in refs:
        source_label = f'<span data-owner-text="true">{escape(ref.source_id)}</span>'
        target = public_locator(ref.locator)
        if target:
            items.append(
                f'<li><a class="evidence-source-link" data-source-id="{escape(ref.source_id, quote=True)}" '
                f'href="{escape(target, quote=True)}">{source_label}</a></li>'
            )
        else:
            fallback = context_link(query_context, view=EVIDENCE_ROUTE, source_id=ref.source_id)
            items.append(
                f'<li data-source-id="{escape(ref.source_id, quote=True)}">{source_label} — '
                f'<a class="evidence-source-context-link" href="{escape(fallback, quote=True)}">'
                f'{escape(translator.t("evidence.missing_unconfirmed"))}</a></li>'
            )
    return f'<div class="evidence-ref-group"><dt>{label}</dt><dd><ul>{"".join(items)}</ul></dd></div>'


def _render_text_list(
    title: str,
    values: Sequence[str],
    *,
    translator: Translator,
    is_fixture: bool,
    empty: str | None = None,
) -> str:
    empty_text = empty or translator.t("evidence.not_recorded")
    if not values:
        return f'<div class="evidence-detail"><dt>{escape(title)}</dt><dd>{escape(empty_text)}</dd></div>'
    items = "".join(
        f'<li>{_owner_text(value, translator, is_fixture=is_fixture)}</li>' for value in values
    )
    return f'<div class="evidence-detail"><dt>{escape(title)}</dt><dd><ul>{items}</ul></dd></div>'


def _owner_markup(value: str | None, translator: Translator, *, is_fixture: bool) -> str:
    if value is None:
        return escape(translator.t("evidence.not_recorded"))
    key = _FIXTURE_TEXT_KEYS.get(value) if is_fixture else None
    if key is not None:
        return escape(translator.t(key))
    return f'<span data-owner-text="true">{escape(value)}</span>'


def _render_artifact(
    artifact: EvidenceArtifact, *, query_context: QueryContext = None, translator: Translator,
    is_fixture: bool = True, heading_level: int = 3,
) -> str:
    status = artifact.verification_status.value
    public = public_locator(artifact.locator)
    link = public or context_link(query_context, view=EVIDENCE_ROUTE, artifact_id=artifact.artifact_id)
    name = _owner_markup(artifact.name, translator, is_fixture=is_fixture)
    link_markup = (
        f'<a class="evidence-artifact-link" href="{escape(link, quote=True)}">{name}</a>'
        if public
        else f'<a class="evidence-artifact-context-link" href="{escape(link, quote=True)}">{name}</a>'
    )
    detail = _owner_markup(artifact.verification_detail, translator, is_fixture=is_fixture)
    source_markup = _render_source_refs(artifact.source_refs, query_context=query_context, translator=translator, is_fixture=is_fixture)
    return (
        f'<article class="evidence-artifact" data-artifact-id="{escape(artifact.artifact_id, quote=True)}" '
        f'data-verification-status="{escape(status, quote=True)}">'
        f"<h{heading_level}>{link_markup}</h{heading_level}><dl class=\"evidence-artifact-details\">"
        f'<div class="evidence-detail"><dt>{escape(translator.t("evidence.media_type"))}</dt><dd>{_owner_markup(artifact.media_type, translator, is_fixture=is_fixture)}</dd></div>'
        f'<div class="evidence-detail"><dt>{escape(translator.t("evidence.logical_role"))}</dt><dd>{_owner_markup(artifact.logical_role, translator, is_fixture=is_fixture)}</dd></div>'
        f'<div class="evidence-detail"><dt>{escape(translator.t("evidence.hash"))}</dt><dd>{_owner_markup(artifact.hash, translator, is_fixture=is_fixture)}</dd></div>'
        f'<div class="evidence-detail"><dt>{escape(translator.t("evidence.producer"))}</dt><dd>{_owner_markup(artifact.producer, translator, is_fixture=is_fixture)}</dd></div>'
        f'<div class="evidence-detail"><dt>{escape(translator.t("evidence.runtime_version"))}</dt><dd>{_owner_markup(artifact.runtime_version, translator, is_fixture=is_fixture)}</dd></div>'
        f'<div class="evidence-detail"><dt>{escape(translator.t("evidence.data_version"))}</dt><dd>{_owner_markup(artifact.data_version, translator, is_fixture=is_fixture)}</dd></div>'
        f'<div class="evidence-detail"><dt>{escape(translator.t("evidence.verification_status"))}</dt><dd>{_status_label(artifact.verification_status, translator)}</dd></div>'
        f'<div class="evidence-detail"><dt>{escape(translator.t("evidence.verification_detail"))}</dt><dd>{detail}</dd></div>'
        f"{source_markup}</dl></article>"
    )


def _render_section(
    section: EvidenceSection, *, query_context: QueryContext = None, translator: Translator,
    is_fixture: bool = True,
) -> str:
    sources = _render_source_refs(section.source_refs, query_context=query_context, translator=translator, is_fixture=is_fixture)
    artifacts = (
        ", ".join(f'<span data-owner-text="true">{escape(ref)}</span>' for ref in section.artifact_refs)
        if section.artifact_refs
        else escape(translator.t("evidence.not_recorded"))
    )
    return (
        f'<article class="evidence-section" data-section-id="{escape(section.section_id, quote=True)}" '
        f'data-evidence-kind="{section.evidence_kind.value}" data-evidence-status="{section.status.value}">'
        f'<h3>{_owner_markup(section.title, translator, is_fixture=is_fixture)}</h3>'
        f'<p class="evidence-kind-label">{_kind_label(section.evidence_kind, translator)}</p>'
        f'<dl class="evidence-details">'
        f'<div class="evidence-detail"><dt>{escape(translator.t("evidence.level"))}</dt><dd>{_status_label(section.evidence_level, translator)}</dd></div>'
        f'<div class="evidence-detail"><dt>{escape(translator.t("evidence.status"))}</dt><dd>{_status_label(section.status, translator)}</dd></div>'
        f'<div class="evidence-detail"><dt>{escape(translator.t("evidence.summary"))}</dt><dd>{_owner_markup(section.summary, translator, is_fixture=is_fixture)}</dd></div>'
        f'<div class="evidence-detail"><dt>{escape(translator.t("evidence.artifacts"))}</dt><dd>{artifacts}</dd></div>'
        f'{sources}{_render_text_list(translator.t("evidence.limitations"), section.limitations, translator=translator, is_fixture=is_fixture)}</dl></article>'
    )


def _render_record(
    record: EvidenceRecord,
    *,
    query_context: QueryContext = None,
    translator: Translator,
    is_fixture: bool,
) -> str:
    sections = "".join(
        _render_section(
            section,
            query_context=query_context,
            translator=translator,
            is_fixture=is_fixture,
        )
        for section in record.sections
    )
    artifacts = "".join(
        _render_artifact(
            artifact,
            query_context=query_context,
            translator=translator,
            is_fixture=is_fixture,
            heading_level=5,
        )
        for artifact in record.artifacts
    )
    not_recorded = f"<p>{escape(translator.t('evidence.not_recorded'))}</p>"
    return (
        f'<article class="evidence-record" data-record-id="{escape(record.record_id, quote=True)}" '
        f'data-evidence-kind="{record.evidence_kind.value}" data-evidence-status="{record.status.value}">'
        f'<h3>{_owner_markup(record.label, translator, is_fixture=is_fixture)}</h3>'
        f'<p class="evidence-kind-label">{_kind_label(record.evidence_kind, translator)}</p>'
        f'<dl class="evidence-details">'
        f'<div class="evidence-detail"><dt>{escape(translator.t("evidence.level"))}</dt><dd>{_status_label(record.evidence_level, translator)}</dd></div>'
        f'<div class="evidence-detail"><dt>{escape(translator.t("evidence.status"))}</dt><dd>{_status_label(record.status, translator)}</dd></div>'
        f'<div class="evidence-detail"><dt>{escape(translator.t("evidence.summary"))}</dt><dd>{_owner_markup(record.summary, translator, is_fixture=is_fixture)}</dd></div>'
        f'{_render_source_refs(record.source_refs, query_context=query_context, translator=translator)}'
        f'{_render_text_list(translator.t("evidence.limitations"), record.limitations, translator=translator, is_fixture=is_fixture)}'
        f'{_render_text_list(translator.t("evidence.blockers"), record.blockers, translator=translator, is_fixture=is_fixture)}'
        f'{_render_text_list(translator.t("evidence.incompatibilities"), record.incompatibilities, translator=translator, is_fixture=is_fixture)}</dl>'
        f'<section class="evidence-record-sections"><h4>{escape(translator.t("evidence.sections"))}</h4>{sections or not_recorded}</section>'
        f'<section class="evidence-record-artifacts"><h4>{escape(translator.t("evidence.artifacts"))}</h4>{artifacts or not_recorded}</section>'
        "</article>"
    )


def render_evidence(
    view_or_model: EvidenceViewModel | ManagerReadModel,
    *,
    query_context: QueryContext = None,
    include_raw_json: bool = True,
    translator: Translator | None = None,
) -> str:
    """Render an Evidence Ledger fragment for a shared shell to mount."""

    selected_translator = page_translator(translator)
    view = (
        view_or_model
        if isinstance(view_or_model, EvidenceViewModel)
        else EvidenceViewModel.from_read_model(view_or_model)
    )
    model, ledger = view.read_model, view.ledger
    is_fixture = any(source.source_id == "evidence-fixture-source" for source in model.source_refs)
    sources = selected_translator.join(
        f'<span data-owner-text="true">{escape(source.source_id)}</span>'
        for source in model.source_refs
    ) or escape(selected_translator.t("evidence.not_recorded"))
    observed = model.as_of or selected_translator.t("evidence.unavailable")
    snapshot = model.snapshot_token or selected_translator.t("evidence.unavailable")
    window = PageWindow.from_query(query_context, total=len(ledger.records))
    page_records = ledger.records[window.start : window.stop]
    candidate = tuple(record for record in page_records if record.is_candidate)
    conforming = tuple(record for record in page_records if record.is_protocol_conforming)
    unclassified = tuple(
        record for record in page_records if not record.is_candidate and not record.is_protocol_conforming
    )
    pieces = [
        '<section class="evidence-page" data-integration-hook="evidence-view" '
        f'data-evidence-status="{ledger.status.value}" data-read-status="{model.availability.status.value}">',
        f'<p class="eyebrow">{escape(selected_translator.t("evidence.eyebrow"))}</p>',
        f'<h1 class="page-title" data-page-title tabindex="-1">{escape(selected_translator.t("evidence.title"))}</h1>',
        f'<p class="page-intro">{escape(selected_translator.t("evidence.intro"))}</p>',
        f'<p class="context-line evidence-context"><span><strong>{escape(selected_translator.t("evidence.observed"))}</strong> <span translate="no">{escape(observed)}</span></span>'
        f'<span><strong>{escape(selected_translator.t("evidence.snapshot"))}</strong> <span translate="no">{escape(snapshot)}</span></span><span><strong>{escape(selected_translator.t("evidence.sources"))}</strong> {sources}</span></p>',
        render_status_block(
            _fixture_status_model(model, selected_translator, is_fixture=is_fixture),
            translator=selected_translator,
        ),
        f'<section class="evidence-ledger-summary" data-ledger-summary="true"><h2>{escape(selected_translator.t("evidence.ledger_summary"))}</h2>'
        '<dl class="evidence-details">'
        f'<div class="evidence-detail"><dt>{escape(selected_translator.t("evidence.conclusion"))}</dt><dd>{_owner_markup(ledger.conclusion, selected_translator, is_fixture=is_fixture)}</dd></div>'
        f'<div class="evidence-detail"><dt>{escape(selected_translator.t("evidence.decision"))}</dt><dd>{_owner_markup(ledger.decision, selected_translator, is_fixture=is_fixture)}</dd></div>'
        f'<div class="evidence-detail"><dt>{escape(selected_translator.t("evidence.level"))}</dt><dd>{_status_label(ledger.evidence_level, selected_translator)}</dd></div>'
        f'<div class="evidence-detail"><dt>{escape(selected_translator.t("evidence.category"))}</dt><dd>{_kind_label(ledger.evidence_kind, selected_translator)}</dd></div>'
        f'<div class="evidence-detail"><dt>{escape(selected_translator.t("evidence.outcome"))}</dt><dd>{_status_label(ledger.status, selected_translator)}</dd></div>'
        f"{_render_source_refs(ledger.sources, query_context=query_context, translator=selected_translator)}"
        f"{_render_text_list(selected_translator.t('evidence.limitations'), ledger.limitations, translator=selected_translator, is_fixture=is_fixture)}"
        f"{_render_text_list(selected_translator.t('evidence.blockers'), ledger.blockers, translator=selected_translator, is_fixture=is_fixture)}"
        f"{_render_text_list(selected_translator.t('evidence.incompatibilities'), ledger.incompatibilities, translator=selected_translator, is_fixture=is_fixture)}</dl></section>",
    ]
    if not page_records and model.availability.status is not ReadModelStatus.API_UNAVAILABLE:
        state = "empty" if model.availability.status is ReadModelStatus.MISSING else "partial"
        detail = selected_translator.t(
            "evidence.no_records" if state == "empty" else "evidence.partial_records"
        )
        pieces.append(
            render_operational_state(state, translator=selected_translator, detail=detail)
        )
    if candidate:
        pieces.append(
            f'<section class="evidence-group" data-evidence-group="candidate" '
            f'data-promotion="never"><h2>{escape(selected_translator.t("evidence.candidate_heading"))}</h2>'
            f'<p>{escape(selected_translator.t("evidence.candidate_notice"))}</p>'
            + "".join(
                _render_record(record, query_context=query_context, translator=selected_translator, is_fixture=is_fixture)
                for record in candidate
            )
            + "</section>"
        )
    if conforming:
        pieces.append(
            f'<section class="evidence-group" data-evidence-group="protocol_conforming" '
            f'data-promotion="published"><h2>{escape(selected_translator.t("evidence.conforming_heading"))}</h2>'
            + "".join(
                _render_record(record, query_context=query_context, translator=selected_translator, is_fixture=is_fixture)
                for record in conforming
            )
            + "</section>"
        )
    if unclassified:
        pieces.append(
            f'<section class="evidence-group" data-evidence-group="not_recorded">'
            f'<h2>{escape(selected_translator.t("evidence.class_not_recorded"))}</h2>'
            + "".join(
                _render_record(record, query_context=query_context, translator=selected_translator, is_fixture=is_fixture)
                for record in unclassified
            )
            + "</section>"
        )
    if ledger.sections:
        pieces.append(
            f'<section class="evidence-sections"><h2>{escape(selected_translator.t("evidence.sections"))}</h2>'
            + "".join(
                _render_section(section, query_context=query_context, translator=selected_translator, is_fixture=is_fixture)
                for section in ledger.sections
            )
            + "</section>"
        )
    if ledger.artifacts:
        pieces.append(
            f'<section class="evidence-artifacts"><h2>{escape(selected_translator.t("evidence.artifacts"))}</h2>'
            + "".join(
                _render_artifact(artifact, query_context=query_context, translator=selected_translator, is_fixture=is_fixture)
                for artifact in ledger.artifacts
            )
            + "</section>"
        )
    pieces.append(window.render(query_context, view=EVIDENCE_ROUTE, translator=selected_translator))
    if include_raw_json:
        pieces.append(
            f'<details class="raw-json evidence-raw-json"><summary>{escape(selected_translator.t("evidence.raw_json"))}</summary>'
            f"<pre>{escape(view.raw_json)}</pre></details>"
        )
    pieces.append("</section>")
    return "".join(pieces)


def evidence_view(provider: ManagerDataProvider, *, snapshot_token: str | None = None) -> EvidenceViewModel:
    """Read the public evidence resource once and build its immutable view model."""

    return EvidenceViewModel.from_read_model(
        provider.read(EVIDENCE_RESOURCE, snapshot_token=snapshot_token)
    )


def render_evidence_view(
    source: ManagerDataProvider | ManagerReadModel,
    *,
    snapshot_token: str | None = None,
    query_context: QueryContext = None,
    translator: Translator | None = None,
) -> str:
    """Read and render the public Evidence resource, or render a cached envelope."""

    model = (
        source
        if isinstance(source, ManagerReadModel)
        else evidence_view(source, snapshot_token=snapshot_token).read_model
    )
    return render_evidence(model, query_context=query_context, translator=translator)


# --- deterministic fixtures and read-only provider ----------------------------


def _fixture_source(source_id: str = "evidence-fixture-source") -> SourceReference:
    return SourceReference(
        source_id=source_id,
        owner="apex-research-public-records",
        kind="evidence-ledger",
        locator="fixture://apex-research/evidence-ledger",
        schema="evidence.v2",
        revision="fixture-v1",
    )


def _fixture_artifact(
    *,
    status: str = "verified",
    name: str = "evidence-report.json",
    detail: str | None = None,
) -> dict[str, object]:
    return {
        "artifact_id": "artifact-report-1",
        "name": name,
        "media_type": "application/json",
        "logical_role": "evidence_report",
        "hash": "sha256:" + "a" * 64,
        "producer": "strategy-reporting",
        "runtime_version": "runtime-v2",
        "data_version": "prices-2026-09",
        "verification_status": status,
        "verification_detail": detail,
        "artifact_link": "fixture://strategy-reporting/artifacts/evidence-report.json",
        "source_refs": ["evidence-fixture-source"],
    }


def _fixture_payload(state: EvidenceFixtureState) -> dict[str, object]:
    candidate = {
        "record_id": "candidate-evidence-1",
        "label": "Candidate screening result",
        "status": "not_evaluated",
        "evidence_kind": "candidate",
        "evidence_level": "candidate",
        "summary": "A candidate result awaiting the frozen protocol.",
        "sections": [
            {
                "section_id": "candidate-section",
                "title": "Candidate signal",
                "status": "not_evaluated",
                "evidence_kind": "candidate",
                "source_refs": ["evidence-fixture-source"],
            }
        ],
        "source_refs": ["evidence-fixture-source"],
        "artifacts": [],
        "limitations": ["Candidate evidence is not a protocol result."],
    }
    conforming = {
        "record_id": "protocol-evidence-1",
        "label": "Protocol result",
        "status": "pass",
        "evidence_kind": "protocol_conforming",
        "evidence_level": "high",
        "summary": "A result evaluated under the declared protocol.",
        "sections": [
            {
                "section_id": "protocol-section",
                "title": "Protocol evaluation",
                "status": "pass",
                "evidence_kind": "protocol_conforming",
                "evidence_level": "high",
                "source_refs": ["evidence-fixture-source"],
                "artifact_refs": ["artifact-report-1"],
            }
        ],
        "source_refs": ["evidence-fixture-source"],
        "artifacts": [_fixture_artifact()],
        "limitations": ["Synthetic fixture; not a live data gate."],
    }
    payload: dict[str, object] = {
        "conclusion": "The protocol result is inspectable.",
        "decision": "Retain the published protocol result for review.",
        "evidence_level": "high",
        "evidence_kind": "protocol_conforming",
        "status": "pass",
        "sections": [
            {
                "section_id": "conclusion",
                "title": "Conclusion and decision",
                "status": "pass",
                "evidence_kind": "protocol_conforming",
                "evidence_level": "high",
                "summary": "Conclusion is linked to a public source and artifact.",
                "source_refs": ["evidence-fixture-source"],
                "artifact_refs": ["artifact-report-1"],
                "limitations": ["Fixture data only."],
            }
        ],
        "sources": ["evidence-fixture-source"],
        "artifacts": [_fixture_artifact()],
        "records": [candidate, conforming],
        "limitations": ["This view does not recalculate metrics."],
        "blockers": [],
        "incompatibilities": [],
    }
    if state is EvidenceFixtureState.CANDIDATE:
        payload["evidence_kind"] = "candidate"
        payload["evidence_level"] = "candidate"
        payload["status"] = "not_evaluated"
        payload["records"] = [candidate]
        payload["artifacts"] = []
    elif state is EvidenceFixtureState.EVALUATED:
        payload["status"] = "evaluated"
        payload["records"] = [{**conforming, "status": "evaluated"}]
    elif state in {EvidenceFixtureState.PROTOCOL_CONFORMING, EvidenceFixtureState.PASS}:
        payload["records"] = [conforming]
    elif state is EvidenceFixtureState.FAIL:
        payload["status"] = "fail"
        payload["records"] = [{**conforming, "status": "fail", "label": "Failed protocol result"}]
    elif state is EvidenceFixtureState.NOT_EVALUATED:
        payload["status"] = "not_evaluated"
        payload["records"] = [{**candidate, "label": "Not evaluated result"}]
    elif state is EvidenceFixtureState.BLOCKED:
        payload["status"] = "blocked"
        payload["blockers"] = ["The approved protocol source is blocked."]
        payload["records"] = [{**conforming, "status": "blocked", "blockers": payload["blockers"]}]
    elif state is EvidenceFixtureState.INCOMPARABLE:
        payload["status"] = "incomparable"
        payload["incompatibilities"] = ["Data snapshots are not comparable."]
        payload["records"] = [{**conforming, "status": "incomparable", "incompatibilities": payload["incompatibilities"]}]
    elif state is EvidenceFixtureState.HASH_MISMATCH:
        payload["status"] = "fail"
        payload["artifacts"] = [_fixture_artifact(status="hash_mismatch", detail="Declared hash does not match the observed bytes.")]
        payload["records"] = [conforming]
    elif state is EvidenceFixtureState.MISSING_ARTIFACT:
        payload["status"] = "blocked"
        payload["artifacts"] = [_fixture_artifact(status="missing_artifact", detail="The published artifact cannot be located.")]
        payload["records"] = [conforming]
    elif state is EvidenceFixtureState.UNKNOWN_SCHEMA:
        payload["status"] = "blocked"
        payload["artifacts"] = [_fixture_artifact(status="unknown_schema", detail="Artifact schema is not recognised by this reader.")]
        payload["records"] = [conforming]
    elif state in {EvidenceFixtureState.UNAVAILABLE, EvidenceFixtureState.API_UNAVAILABLE}:
        payload["status"] = "unavailable"
        payload["records"] = []
    elif state is EvidenceFixtureState.PARTIAL:
        payload["records"] = [candidate]
        payload["limitations"] = ["Some protocol sections are outside the published scope."]
    elif state is EvidenceFixtureState.EMPTY:
        payload = {}
    return payload


def build_evidence_fixture(state: EvidenceFixtureState | str = EvidenceFixtureState.COMPLETE) -> ManagerReadModel:
    """Build a fresh deterministic Evidence envelope without filesystem access."""

    selected = EvidenceFixtureState(state)
    source = _fixture_source()
    payload = _fixture_payload(selected)
    read_status = ReadModelStatus.KNOWN
    complete = True
    reason = "The fixture contains the published Evidence Ledger projection."
    errors: tuple[ReadModelError, ...] = ()
    as_of: str | None = "2026-10-03T09:00:00Z"
    snapshot: str | None = f"evidence-{selected.value}-v0"
    if selected is EvidenceFixtureState.EMPTY:
        read_status = ReadModelStatus.MISSING
        complete = False
        reason = "No Evidence Ledger records are published in this scope."
        as_of = None
        snapshot = None
    elif selected is EvidenceFixtureState.PARTIAL:
        complete = False
        reason = "Only part of the Evidence Ledger is published in this scope."
        errors = (
            ReadModelError(
                code="evidence_scope_partial",
                message="Some protocol evidence sections are outside the indexed scope.",
                source_ref=source.source_id,
            ),
        )
    elif selected is EvidenceFixtureState.BLOCKED:
        read_status = ReadModelStatus.BLOCKED
        complete = False
        reason = "The approved Evidence read seam is blocked."
        errors = (
            ReadModelError(
                code="evidence_read_blocked",
                message="The fixture preserves a blocked evidence determination.",
                source_ref=source.source_id,
            ),
        )
    elif selected is EvidenceFixtureState.INCOMPARABLE:
        read_status = ReadModelStatus.INCOMPARABLE
        complete = False
        reason = "The evidence snapshots are incompatible."
        errors = (
            ReadModelError(
                code="evidence_incomparable",
                message="The fixture preserves incomparable evidence rather than ranking it.",
                source_ref=source.source_id,
            ),
        )
    elif selected in {EvidenceFixtureState.HASH_MISMATCH, EvidenceFixtureState.UNKNOWN_SCHEMA}:
        read_status = ReadModelStatus.INTEGRITY_FAILURE
        complete = False
        reason = "The artifact verification did not pass its integrity gate."
        code = "artifact_digest_mismatch" if selected is EvidenceFixtureState.HASH_MISMATCH else "artifact_unknown_schema"
        errors = (
            ReadModelError(
                code=code,
                message=(
                    "The artifact hash does not match the declared hash."
                    if selected is EvidenceFixtureState.HASH_MISMATCH
                    else "The artifact schema is unknown to this reader."
                ),
                source_ref=source.source_id,
            ),
        )
    elif selected is EvidenceFixtureState.MISSING_ARTIFACT:
        read_status = ReadModelStatus.MISSING
        complete = False
        reason = "A referenced artifact is missing."
        errors = (
            ReadModelError(
                code="artifact_missing",
                message="The evidence record references an unavailable artifact.",
                source_ref=source.source_id,
            ),
        )
    elif selected is EvidenceFixtureState.STALE:
        read_status = ReadModelStatus.STALE
        complete = False
        reason = "The Evidence Ledger source is stale."
        errors = (
            ReadModelError(
                code="evidence_source_stale",
                message="The published evidence is retained for historical inspection only.",
                source_ref=source.source_id,
            ),
        )
    elif selected in {EvidenceFixtureState.UNAVAILABLE, EvidenceFixtureState.API_UNAVAILABLE}:
        read_status = ReadModelStatus.API_UNAVAILABLE
        complete = False
        reason = "The approved public Evidence read API is unavailable."
        as_of = None
        snapshot = None
        errors = (
            ReadModelError(
                code="evidence_api_unavailable",
                message="No private-storage fallback is permitted for Evidence reads.",
                source_ref=source.source_id,
                retryable=True,
            ),
        )
    return ManagerReadModel(
        data=cast(JSONValue, payload),
        source_refs=() if selected is EvidenceFixtureState.EMPTY else (source,),
        as_of=as_of,
        snapshot_token=snapshot,
        derivation=Derivation(kind="direct", inputs=(source.source_id,), version="evidence-fixture-v0"),
        availability=Availability(status=read_status, complete=complete, reason=reason, retryable=read_status is ReadModelStatus.API_UNAVAILABLE),
        errors=errors,
    )


@dataclass(frozen=True, slots=True)
class EvidenceFixtureProvider:
    """Read-only provider serving one deterministic Evidence fixture."""

    state: EvidenceFixtureState

    def __init__(self, state: EvidenceFixtureState | str = EvidenceFixtureState.COMPLETE) -> None:
        object.__setattr__(self, "state", EvidenceFixtureState(state))

    def read(
        self,
        resource: str = EVIDENCE_RESOURCE,
        *,
        snapshot_token: str | None = None,
    ) -> ManagerReadModel:
        del snapshot_token
        if resource not in {EVIDENCE_RESOURCE, "evidence_ledger", "evidence-ledger", EVIDENCE_ROUTE}:
            raise ValueError(f"evidence fixture does not serve resource {resource!r}")
        return build_evidence_fixture(self.state)


def evidence_fixture_provider(
    state: EvidenceFixtureState | str = EvidenceFixtureState.COMPLETE,
) -> EvidenceFixtureProvider:
    """Return a deterministic provider suitable for focused page tests."""

    return EvidenceFixtureProvider(state)


# Naming aliases follow the other Manager GUI page modules and keep the hook discoverable.
EvidenceLedgerFixture = EvidenceFixtureState
EvidenceLedgerFixtureState = EvidenceFixtureState
EvidenceLedgerProvider = EvidenceFixtureProvider
EvidenceLedgerView = EvidenceViewModel
build_evidence_ledger_fixture = build_evidence_fixture
fixture_evidence_provider = evidence_fixture_provider
render_evidence_ledger = render_evidence
render_evidence_ledger_view = render_evidence_view


__all__ = [
    "ARTIFACT_VERIFICATION_STATUSES",
    "EVIDENCE_FIXTURE_STATES",
    "EVIDENCE_INTEGRATION_HOOK",
    "EVIDENCE_INTEGRATION_HOOK_PATH",
    "EVIDENCE_KINDS",
    "EVIDENCE_LEVELS",
    "EVIDENCE_OUTCOMES",
    "EVIDENCE_RESOURCE",
    "EVIDENCE_ROUTE",
    "NOT_RECORDED",
    "ArtifactInspection",
    "ArtifactStatus",
    "ArtifactVerificationStatus",
    "EvidenceArtifact",
    "EvidenceClass",
    "EvidenceFixtureProvider",
    "EvidenceFixtureState",
    "EvidenceKind",
    "EvidenceLedger",
    "EvidenceLedgerFixture",
    "EvidenceLedgerFixtureState",
    "EvidenceLedgerProvider",
    "EvidenceLedgerView",
    "EvidenceLedgerViewModel",
    "EvidenceLevel",
    "EvidenceOutcome",
    "EvidenceRecord",
    "EvidenceSection",
    "EvidenceSectionView",
    "EvidenceSourceRef",
    "EvidenceStatus",
    "EvidenceView",
    "EvidenceViewModel",
    "VerificationStatus",
    "build_evidence_fixture",
    "build_evidence_ledger_fixture",
    "evidence_fixture_provider",
    "evidence_view",
    "fixture_evidence_provider",
    "render_evidence",
    "render_evidence_ledger",
    "render_evidence_ledger_view",
    "render_evidence_view",
]
