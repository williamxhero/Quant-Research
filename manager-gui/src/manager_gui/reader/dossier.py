"""Immutable, read-only Dossier v2 projection for public Workspace evidence.

This module deliberately contains no Workspace client, Runtime client, or
reporting calculations.  ``DossierReportBuilder`` follows explicit record
references, copies owner facts, and reads only verified native artifacts.
Missing, incomparable, or corrupt inputs become ``not_evaluated`` values.
"""

from __future__ import annotations

import base64
import binascii
import csv
import hashlib
import io
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import ClassVar, Protocol, TypeAlias, cast, runtime_checkable

DOSSIER_REPORT_SCHEMA = "manager-gui.dossier-report.v2"
DOSSIER_REPORT_VERSION = "v2"

MATRIX_TYPE = "apex-research.v1.2-s5-formal-matrix.v1"
T2_TYPE = "apex-research.v1.2-s5-t2-source.v1"
SOURCE_TYPE = "apex-research.strategy-report-source.v2"
QUARANTINE_TYPE = "apex-research.v1.2-s5-quarantine.v1"
CONCLUSION_TYPE = "apex-research.research-conclusion.v1"
FACTS_TYPE = "apex-research.study-runtime-facts.v1"
METRICS_TYPE = "apex-research.cpa-object-performance.v1"
COMPARISON_TYPE = "apex-research.cpa-bootstrap-comparison.v1"
ATTRIBUTION_TYPE = "apex-research.cpa-object-attribution.v2"
LOCK_TYPE = "apex-research.prospective-holdout-lock.v1"
PROOF_TYPE = "apex-research.prospective-holdout-access-proof.v1"
REGISTRATION_TYPE = "apex-research.study-registration.v1"
EXCLUDED_TYPE = "apex-research.v1.2-s5-formal-matrix-excluded-attempts.v1"

DossierSectionName = str
DOSSIER_SECTION_ORDER: tuple[str, ...] = (
    "source",
    "experiment_matrix",
    "lineage",
    "metrics",
    "audits",
    "comparisons",
    "attributions",
    "quarantine",
    "holdout_lock",
    "limitations",
)

_UNAVAILABLE_STATES = frozenset(
    {"not_evaluated", "unavailable", "blocked", "incomparable", "insufficient_statistics"}
)
_RECORD_SECTIONS: dict[str, str] = {
    SOURCE_TYPE: "source",
    MATRIX_TYPE: "experiment_matrix",
    T2_TYPE: "experiment_matrix",
    REGISTRATION_TYPE: "lineage",
    "apex-research.sample-exposure.v1": "lineage",
    "apex-research.cpa-research-profile.v1": "lineage",
    "apex-research.cpa-bootstrap-method.v1": "lineage",
    "apex-research.cpa-regime-definition.v1": "lineage",
    "apex-research.revision-decision.v1": "lineage",
    "apex-research.cpa-revision-search-budget.v1": "lineage",
    FACTS_TYPE: "audits",
    EXCLUDED_TYPE: "audits",
    METRICS_TYPE: "metrics",
    COMPARISON_TYPE: "comparisons",
    ATTRIBUTION_TYPE: "attributions",
    "apex-research.cpa-object-event-evidence.v1": "attributions",
    QUARANTINE_TYPE: "quarantine",
    LOCK_TYPE: "holdout_lock",
    PROOF_TYPE: "holdout_lock",
    CONCLUSION_TYPE: "limitations",
}
_NATIVE_ARTIFACT_SUFFIXES = (
    "/native_statistics.json",
    "/native_account.csv",
    "runtime_manifest.json",
)
_SHA256_HEX = frozenset("0123456789abcdef")
_JSON_SCALAR: TypeAlias = bool | int | float | str | None
FrozenJSON: TypeAlias = _JSON_SCALAR | tuple["FrozenJSON", ...] | Mapping[str, "FrozenJSON"]


class DossierBuildError(ValueError):
    """A source identity or contract error that prevents a trustworthy report."""


@runtime_checkable
class DossierSourceProvider(Protocol):
    """The complete source boundary used by the dossier builder.

    The protocol intentionally has no discovery, Runtime, or mutation method.
    A provider may implement additional methods for its own purposes, but the
    builder never calls them.
    """

    def get_record(self, record_id: str) -> Mapping[str, object] | None:
        """Read one public record by its complete identity."""

    def verify_artifact(self, ref: Mapping[str, object]) -> Mapping[str, object] | object:
        """Verify the identity and integrity metadata of one artifact reference."""

    def read_artifact(self, uri: str) -> bytes | Mapping[str, object]:
        """Read the already verified artifact bytes by opaque URI."""


# Compatibility spelling used by callers that call the source a read adapter.
ReadOnlyDossierSourceProvider = DossierSourceProvider


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _optional_text(value: object, name: str) -> str | None:
    return None if value is None else _text(value, name)


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be an object with string keys")
    return cast(Mapping[str, object], value)


def _sequence(value: object, name: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{name} must be an array")
    return value


def _sha256(value: str, name: str = "sha256") -> str:
    if len(value) != 64 or any(char not in _SHA256_HEX for char in value):
        raise ValueError(f"{name} must be a lowercase SHA-256 value")
    return value


def _freeze(value: object) -> FrozenJSON:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Dossier values must contain finite JSON numbers")
        return value
    if isinstance(value, Mapping):
        item = _mapping(value, "JSON value")
        return cast(
            Mapping[str, FrozenJSON],
            {key: _freeze(entry) for key, entry in sorted(item.items())},
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(entry) for entry in value)
    raise ValueError("Dossier values must be JSON-compatible")


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw(entry) for key, entry in value.items()}
    if isinstance(value, tuple):
        return [_thaw(entry) for entry in value]
    return value


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        _thaw(_freeze(value)),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _content_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _pointer_part(value: object) -> str:
    return str(value).replace("~", "~0").replace("/", "~1")


def _record_ref(
    value: DossierRecordRef | Mapping[str, object], name: str = "record"
) -> DossierRecordRef:
    if isinstance(value, DossierRecordRef):
        return value
    return DossierRecordRef.from_dict(_mapping(value, name))


@dataclass(frozen=True, slots=True)
class DossierRecordRef:
    """A complete public record identity; no prefix or latest lookup is valid."""

    record_id: str
    record_type: str

    def __post_init__(self) -> None:
        _sha256(_text(self.record_id, "record_id"), "record_id")
        _text(self.record_type, "record_type")

    def to_dict(self) -> dict[str, str]:
        return {"record_id": self.record_id, "record_type": self.record_type}

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> DossierRecordRef:
        item = _mapping(value, "record_ref")
        return cls(
            _text(item.get("record_id"), "record_id"), _text(item.get("record_type"), "record_type")
        )


# The nested strategy-reporting package uses this established vocabulary.
StudyRecordRef = DossierRecordRef


@dataclass(frozen=True, slots=True)
class DossierSourceRefs:
    """The five explicit roots from which a Dossier v2 can be projected."""

    matrix: DossierRecordRef | Mapping[str, object]
    t2: DossierRecordRef | Mapping[str, object]
    report_source: DossierRecordRef | Mapping[str, object]
    quarantine: DossierRecordRef | Mapping[str, object]
    conclusion: DossierRecordRef | Mapping[str, object]

    def __post_init__(self) -> None:
        refs = tuple(
            _record_ref(value, name)
            for name, value in (
                ("matrix", self.matrix),
                ("t2", self.t2),
                ("report_source", self.report_source),
                ("quarantine", self.quarantine),
                ("conclusion", self.conclusion),
            )
        )
        expected = (MATRIX_TYPE, T2_TYPE, SOURCE_TYPE, QUARANTINE_TYPE, CONCLUSION_TYPE)
        if tuple(ref.record_type for ref in refs) != expected:
            raise ValueError("dossier source reference types differ")
        if len({ref.record_id for ref in refs}) != len(refs):
            raise ValueError("dossier source identities must be unique")
        object.__setattr__(self, "matrix", refs[0])
        object.__setattr__(self, "t2", refs[1])
        object.__setattr__(self, "report_source", refs[2])
        object.__setattr__(self, "quarantine", refs[3])
        object.__setattr__(self, "conclusion", refs[4])

    def records(self) -> tuple[DossierRecordRef, ...]:
        return (self.matrix, self.t2, self.report_source, self.quarantine, self.conclusion)

    def to_dict(self) -> dict[str, object]:
        return {
            name: ref.to_dict()
            for name, ref in zip(
                ("matrix", "t2", "report_source", "quarantine", "conclusion"),
                self.records(),
                strict=True,
            )
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> DossierSourceRefs:
        item = _mapping(value, "source_refs")
        expected = {"matrix", "t2", "report_source", "quarantine", "conclusion"}
        if set(item) != expected:
            raise ValueError("source_refs fields are incomplete")
        return cls(
            _record_ref(item["matrix"], "matrix"),
            _record_ref(item["t2"], "t2"),
            _record_ref(item["report_source"], "report_source"),
            _record_ref(item["quarantine"], "quarantine"),
            _record_ref(item["conclusion"], "conclusion"),
        )


CURRENT_DOSSIER_SOURCE_REFS = DossierSourceRefs(
    matrix=DossierRecordRef(
        "7523f0c34e7d90b6e603f63cc53884284d05664351b68d0a59805e9cf8d95bb5", MATRIX_TYPE
    ),
    t2=DossierRecordRef(
        "0cc1f61f6528720a0145206419362872d4ff8fba9e676ef8f3ac358e4450cf35", T2_TYPE
    ),
    report_source=DossierRecordRef(
        "79d7bf225182dcaa7999e38613f0da690291c21b8ed7396d291ac389d5a9f99f", SOURCE_TYPE
    ),
    quarantine=DossierRecordRef(
        "33a9500fad482531b6a4747c67c62dd16132f579782d28234bf8815ee5dfedfc", QUARANTINE_TYPE
    ),
    conclusion=DossierRecordRef(
        "539390079a3dc4eb8061d83f52ca59f2ad169f38ee3d2419b9ffba99164e5dc9", CONCLUSION_TYPE
    ),
)


@dataclass(frozen=True, slots=True)
class DossierArtifactRef:
    """A content-addressed artifact citation retained by a report value."""

    uri: str
    sha256: str
    name: str
    record_schema: str | None = None

    def __post_init__(self) -> None:
        digest = _sha256(self.sha256)
        if self.uri != f"workspace-artifact://sha256/{digest}":
            raise ValueError("artifact URI must be workspace-artifact://sha256/<sha256>")
        _text(self.name, "name")
        _optional_text(self.record_schema, "record_schema")

    def to_dict(self) -> dict[str, object]:
        return {
            "uri": self.uri,
            "sha256": self.sha256,
            "name": self.name,
            "record_schema": self.record_schema,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> DossierArtifactRef:
        item = _mapping(value, "artifact")
        return cls(
            _text(item.get("uri"), "uri"),
            _sha256(_text(item.get("sha256"), "sha256")),
            _text(item.get("name"), "name"),
            _optional_text(item.get("record_schema"), "record_schema"),
        )


@dataclass(frozen=True, slots=True)
class DossierValueSource:
    record: DossierRecordRef | Mapping[str, object]
    selector: str
    artifact: DossierArtifactRef | Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "record", _record_ref(self.record))
        if not self.selector.startswith("/"):
            raise ValueError("selector must be an absolute JSON pointer")
        if self.artifact is not None and not isinstance(self.artifact, DossierArtifactRef):
            object.__setattr__(
                self, "artifact", DossierArtifactRef.from_dict(_mapping(self.artifact, "artifact"))
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "record": self.record.to_dict(),
            "selector": self.selector,
            "artifact": None if self.artifact is None else self.artifact.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> DossierValueSource:
        item = _mapping(value, "value_source")
        artifact = item.get("artifact")
        return cls(
            _record_ref(_mapping(item.get("record"), "record")),
            _text(item.get("selector"), "selector"),
            None
            if artifact is None
            else DossierArtifactRef.from_dict(_mapping(artifact, "artifact")),
        )


@dataclass(frozen=True, slots=True)
class DossierValue:
    """A scalar owner value or an explicitly unavailable value with provenance."""

    path: str
    value: _JSON_SCALAR
    status: str
    derivation: str
    derivation_reason: str
    sources: tuple[DossierValueSource | Mapping[str, object], ...]
    reason: str | None = None

    def __post_init__(self) -> None:
        if not self.path.startswith("/"):
            raise ValueError("path must be an absolute JSON pointer")
        if self.status not in {"evaluated", "not_evaluated"}:
            raise ValueError("status must be evaluated or not_evaluated")
        if self.derivation not in {"Runtime-native", "presentation-derived", "not_evaluated"}:
            raise ValueError("invalid dossier derivation")
        _text(self.derivation_reason, "derivation_reason")
        sources = tuple(
            source
            if isinstance(source, DossierValueSource)
            else DossierValueSource.from_dict(_mapping(source, "source"))
            for source in self.sources
        )
        if not sources:
            raise ValueError("dossier values require at least one source")
        object.__setattr__(self, "sources", sources)
        if self.value is not None and not isinstance(self.value, (bool, int, float, str)):
            raise ValueError("dossier values must be JSON scalars")
        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise ValueError("dossier values must contain finite JSON numbers")
        if self.status == "not_evaluated":
            if self.value is not None or self.derivation != "not_evaluated" or not self.reason:
                raise ValueError("not_evaluated dossier values require null, reason and status")
        elif self.value is None or self.reason is not None or self.derivation == "not_evaluated":
            raise ValueError("evaluated dossier values require a value and derivation")
        if self.derivation == "Runtime-native" and any(
            source.artifact is None for source in sources
        ):
            raise ValueError("Runtime-native values require a verified native artifact citation")
        _optional_text(self.reason, "reason")

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "value": self.value,
            "status": self.status,
            "derivation": self.derivation,
            "derivation_reason": self.derivation_reason,
            "sources": [source.to_dict() for source in self.sources],
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> DossierValue:
        item = _mapping(value, "dossier_value")
        raw_sources = _sequence(item.get("sources"), "sources")
        return cls(
            _text(item.get("path"), "path"),
            cast(_JSON_SCALAR, item.get("value")),
            _text(item.get("status"), "status"),
            _text(item.get("derivation"), "derivation"),
            _text(item.get("derivation_reason"), "derivation_reason"),
            tuple(
                DossierValueSource.from_dict(_mapping(source, "source")) for source in raw_sources
            ),
            _optional_text(item.get("reason"), "reason"),
        )


@dataclass(frozen=True, slots=True)
class DossierLineageEdge:
    source_kind: str
    source_id: str
    relation: str

    def __post_init__(self) -> None:
        _text(self.source_kind, "source_kind")
        _text(self.source_id, "source_id")
        _text(self.relation, "relation")

    def to_dict(self) -> dict[str, str]:
        return {
            "source_kind": self.source_kind,
            "source_id": self.source_id,
            "relation": self.relation,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> DossierLineageEdge:
        item = _mapping(value, "lineage")
        return cls(
            _text(item.get("source_kind"), "source_kind"),
            _text(item.get("source_id"), "source_id"),
            _text(item.get("relation"), "relation"),
        )


LineageEdge = DossierLineageEdge


@dataclass(frozen=True, slots=True)
class DossierEvidence:
    source: DossierRecordRef | Mapping[str, object]
    payload_sha256: str | None
    lineage: tuple[DossierLineageEdge | Mapping[str, object], ...]
    artifacts: tuple[DossierArtifactRef | Mapping[str, object], ...]
    facts: tuple[DossierValue | Mapping[str, object], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", _record_ref(self.source))
        if self.payload_sha256 is not None:
            _sha256(self.payload_sha256, "payload_sha256")
        lineage = tuple(
            edge
            if isinstance(edge, DossierLineageEdge)
            else DossierLineageEdge.from_dict(_mapping(edge, "lineage"))
            for edge in self.lineage
        )
        artifacts = tuple(
            artifact
            if isinstance(artifact, DossierArtifactRef)
            else DossierArtifactRef.from_dict(_mapping(artifact, "artifact"))
            for artifact in self.artifacts
        )
        facts = tuple(
            fact
            if isinstance(fact, DossierValue)
            else DossierValue.from_dict(_mapping(fact, "fact"))
            for fact in self.facts
        )
        if tuple(fact.path for fact in facts) != tuple(sorted({fact.path for fact in facts})):
            raise ValueError("dossier fact paths must be unique and canonical")
        if artifacts != tuple(sorted(set(artifacts), key=lambda item: (item.sha256, item.name))):
            raise ValueError("dossier artifacts must be unique and canonical")
        artifact_set = set(artifacts)
        if any(
            source.record != self.source
            or (source.artifact is not None and source.artifact not in artifact_set)
            for fact in facts
            for source in fact.sources
        ):
            raise ValueError("dossier fact citations differ from their evidence owner")
        object.__setattr__(self, "lineage", lineage)
        object.__setattr__(self, "artifacts", artifacts)
        object.__setattr__(self, "facts", facts)

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source.to_dict(),
            "payload_sha256": self.payload_sha256,
            "lineage": [edge.to_dict() for edge in self.lineage],
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "facts": [fact.to_dict() for fact in self.facts],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> DossierEvidence:
        item = _mapping(value, "evidence")
        return cls(
            _record_ref(_mapping(item.get("source"), "source")),
            None
            if item.get("payload_sha256") is None
            else _sha256(_text(item.get("payload_sha256"), "payload_sha256")),
            tuple(
                DossierLineageEdge.from_dict(_mapping(edge, "lineage"))
                for edge in _sequence(item.get("lineage"), "lineage")
            ),
            tuple(
                DossierArtifactRef.from_dict(_mapping(artifact, "artifact"))
                for artifact in _sequence(item.get("artifacts"), "artifacts")
            ),
            tuple(
                DossierValue.from_dict(_mapping(fact, "fact"))
                for fact in _sequence(item.get("facts"), "facts")
            ),
        )


@dataclass(frozen=True, slots=True)
class DossierSection:
    name: str
    status: str
    reason: str | None
    evidence: tuple[DossierEvidence | Mapping[str, object], ...]

    def __post_init__(self) -> None:
        if self.name not in DOSSIER_SECTION_ORDER:
            raise ValueError("unknown dossier section")
        if self.status not in {"evaluated", "not_evaluated"}:
            raise ValueError("section status must be evaluated or not_evaluated")
        evidence = tuple(
            item
            if isinstance(item, DossierEvidence)
            else DossierEvidence.from_dict(_mapping(item, "evidence"))
            for item in self.evidence
        )
        keys = tuple((item.source.record_type, item.source.record_id) for item in evidence)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("dossier evidence must be unique and canonical")
        if self.status == "not_evaluated" and (evidence or not self.reason):
            raise ValueError("unavailable dossier sections require only a reason")
        if self.status == "evaluated" and (not evidence or self.reason is not None):
            raise ValueError("evaluated dossier sections require public evidence")
        object.__setattr__(self, "evidence", evidence)
        _optional_text(self.reason, "reason")

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "reason": self.reason,
            "evidence": [item.to_dict() for item in self.evidence],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> DossierSection:
        item = _mapping(value, "section")
        return cls(
            _text(item.get("name"), "name"),
            _text(item.get("status"), "status"),
            _optional_text(item.get("reason"), "reason"),
            tuple(
                DossierEvidence.from_dict(_mapping(entry, "evidence"))
                for entry in _sequence(item.get("evidence"), "evidence")
            ),
        )


@dataclass(frozen=True, slots=True)
class DossierReport:
    """Complete immutable Dossier v2 source projection."""

    source_refs: DossierSourceRefs
    sections: tuple[DossierSection | Mapping[str, object], ...]
    source_records: tuple[DossierRecordRef | Mapping[str, object], ...]
    source_artifacts: tuple[DossierArtifactRef | Mapping[str, object], ...]
    title: str = "Quant Research Dossier v2 · 开发与验证"
    banner: str = "非前向 Holdout / 非实盘结论"
    evidence_ceiling: str = "candidate_evidence"
    qualification_inference: str = "forbidden"
    causal_inference: str = "forbidden"
    production_approval_inference: str = "forbidden"
    holdout_results: str = "not_evaluated"

    schema: ClassVar[str] = DOSSIER_REPORT_SCHEMA

    def __post_init__(self) -> None:
        if not isinstance(self.source_refs, DossierSourceRefs):
            object.__setattr__(
                self,
                "source_refs",
                DossierSourceRefs.from_dict(cast(Mapping[str, object], self.source_refs)),
            )
        sections = tuple(
            item
            if isinstance(item, DossierSection)
            else DossierSection.from_dict(_mapping(item, "section"))
            for item in self.sections
        )
        if tuple(section.name for section in sections) != DOSSIER_SECTION_ORDER:
            raise ValueError("dossier sections must be complete and canonical")
        records = tuple(
            item
            if isinstance(item, DossierRecordRef)
            else DossierRecordRef.from_dict(_mapping(item, "source_record"))
            for item in self.source_records
        )
        keys = tuple((item.record_type, item.record_id) for item in records)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("dossier source records must be unique and canonical")
        artifacts = tuple(
            item
            if isinstance(item, DossierArtifactRef)
            else DossierArtifactRef.from_dict(_mapping(item, "artifact"))
            for item in self.source_artifacts
        )
        if artifacts != tuple(sorted(set(artifacts), key=lambda item: (item.sha256, item.name))):
            raise ValueError("dossier source artifacts must be unique and canonical")
        evidence = tuple(item for section in sections for item in section.evidence)
        cited = {item.source for item in evidence}
        if cited != set(records) or not set(self.source_refs.records()) <= cited:
            raise ValueError("dossier public source closure is incomplete")
        cited_artifacts = {artifact for item in evidence for artifact in item.artifacts}
        if set(artifacts) != cited_artifacts:
            raise ValueError("dossier artifact closure differs")
        _text(self.title, "title")
        _text(self.banner, "banner")
        if self.evidence_ceiling != "candidate_evidence":
            raise ValueError("unsupported evidence ceiling")
        if any(
            value != "forbidden"
            for value in (
                self.qualification_inference,
                self.causal_inference,
                self.production_approval_inference,
            )
        ):
            raise ValueError("dossier inference policies are forbidden")
        if self.holdout_results != "not_evaluated":
            raise ValueError("holdout results must remain not_evaluated")
        object.__setattr__(self, "sections", sections)
        object.__setattr__(self, "source_records", records)
        object.__setattr__(self, "source_artifacts", artifacts)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "title": self.title,
            "banner": self.banner,
            "source_refs": self.source_refs.to_dict(),
            "sections": [section.to_dict() for section in self.sections],
            "source_records": [record.to_dict() for record in self.source_records],
            "source_artifacts": [artifact.to_dict() for artifact in self.source_artifacts],
            "evidence_ceiling": self.evidence_ceiling,
            "qualification_inference": self.qualification_inference,
            "causal_inference": self.causal_inference,
            "production_approval_inference": self.production_approval_inference,
            "holdout_results": self.holdout_results,
        }

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(
            self.to_dict(), ensure_ascii=False, allow_nan=False, sort_keys=True, indent=indent
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> DossierReport:
        item = _mapping(value, "dossier_report")
        expected = {
            "schema",
            "title",
            "banner",
            "source_refs",
            "sections",
            "source_records",
            "source_artifacts",
            "evidence_ceiling",
            "qualification_inference",
            "causal_inference",
            "production_approval_inference",
            "holdout_results",
        }
        if set(item) != expected or item.get("schema") != DOSSIER_REPORT_SCHEMA:
            raise ValueError("invalid Dossier v2 schema or fields")
        return cls(
            DossierSourceRefs.from_dict(_mapping(item["source_refs"], "source_refs")),
            tuple(
                DossierSection.from_dict(_mapping(section, "section"))
                for section in _sequence(item["sections"], "sections")
            ),
            tuple(
                DossierRecordRef.from_dict(_mapping(record, "source_record"))
                for record in _sequence(item["source_records"], "source_records")
            ),
            tuple(
                DossierArtifactRef.from_dict(_mapping(artifact, "artifact"))
                for artifact in _sequence(item["source_artifacts"], "source_artifacts")
            ),
            _text(item["title"], "title"),
            _text(item["banner"], "banner"),
            _text(item["evidence_ceiling"], "evidence_ceiling"),
            _text(item["qualification_inference"], "qualification_inference"),
            _text(item["causal_inference"], "causal_inference"),
            _text(item["production_approval_inference"], "production_approval_inference"),
            _text(item["holdout_results"], "holdout_results"),
        )

    @classmethod
    def from_json(cls, value: str) -> DossierReport:
        return cls.from_dict(_mapping(json.loads(value), "dossier_report"))


@dataclass(frozen=True, slots=True)
class _Publication:
    record: DossierRecordRef
    payload: Mapping[str, object]
    lineage: tuple[DossierLineageEdge, ...]
    payload_sha256: str
    artifacts: tuple[Mapping[str, object], ...]


class DossierReportBuilder:
    """Build a Dossier by explicit public reads, never by discovery or calculation."""

    def __init__(self, provider: DossierSourceProvider) -> None:
        for name in ("get_record", "verify_artifact", "read_artifact"):
            if not callable(getattr(provider, name, None)):
                raise TypeError(f"dossier source provider must implement {name}")
        self.provider = provider

    def build(self, refs: DossierSourceRefs = CURRENT_DOSSIER_SOURCE_REFS) -> DossierReport:
        if not isinstance(refs, DossierSourceRefs):
            raise TypeError("dossier builder requires typed DossierSourceRefs")
        roots: dict[tuple[str, str], _Publication] = {}
        for ref in refs.records():
            roots[(ref.record_type, ref.record_id)] = self._read_required(ref)
        self._verify_bindings(refs, roots)
        selected = self._references(roots)
        publications = dict(roots)
        missing: dict[tuple[str, str], str] = {}
        for key, ref in sorted(selected.items()):
            if key in publications:
                continue
            try:
                publications[key] = self._read_optional(ref)
            except DossierBuildError as exc:
                missing[key] = str(exc)
        grouped: dict[str, list[DossierEvidence]] = {name: [] for name in DOSSIER_SECTION_ORDER}
        for key, ref in sorted(selected.items()):
            publication = publications.get(key)
            if publication is None:
                evidence = _missing_evidence(ref, missing.get(key, "public record is unavailable"))
            else:
                evidence = self._project(publication)
                if ref.record_type in {COMPARISON_TYPE, ATTRIBUTION_TYPE}:
                    gap = self._comparison_gap(publication.payload, publications)
                    if gap:
                        evidence = _missing_evidence(ref, gap, publication)
            grouped[_RECORD_SECTIONS[ref.record_type]].append(evidence)
        sections = tuple(
            DossierSection(
                name,
                "evaluated" if grouped[name] else "not_evaluated",
                None if grouped[name] else "no public owner evidence was supplied",
                tuple(grouped[name]),
            )
            for name in DOSSIER_SECTION_ORDER
        )
        artifacts = tuple(
            sorted(
                {
                    artifact
                    for entries in grouped.values()
                    for evidence in entries
                    for artifact in evidence.artifacts
                },
                key=lambda artifact: (artifact.sha256, artifact.name),
            )
        )
        records = tuple(selected[key] for key in sorted(selected))
        return DossierReport(refs, sections, records, artifacts)

    def read(self, refs: DossierSourceRefs = CURRENT_DOSSIER_SOURCE_REFS) -> DossierReport:
        """Compatibility alias for the strategy-reporting adapter vocabulary."""
        return self.build(refs)

    def _read_required(self, ref: DossierRecordRef) -> _Publication:
        try:
            raw = self.provider.get_record(ref.record_id)
        except Exception as exc:
            raise DossierBuildError(
                f"cannot read required dossier record {ref.record_type}:{ref.record_id}"
            ) from exc
        if raw is None:
            raise DossierBuildError(f"required dossier record is unavailable: {ref.record_id}")
        return _publication(raw, ref)

    def _read_optional(self, ref: DossierRecordRef) -> _Publication:
        try:
            raw = self.provider.get_record(ref.record_id)
        except Exception as exc:
            raise DossierBuildError(
                f"cannot read dossier record {ref.record_type}:{ref.record_id}"
            ) from exc
        if raw is None:
            raise DossierBuildError(
                f"dossier record is unavailable: {ref.record_type}:{ref.record_id}"
            )
        return _publication(raw, ref)

    @staticmethod
    def _verify_bindings(
        refs: DossierSourceRefs, roots: Mapping[tuple[str, str], _Publication]
    ) -> None:
        for ref, identity_field in zip(
            refs.records(),
            ("matrix_id", "source_id", "source_id", "quarantine_id", "conclusion_id"),
            strict=True,
        ):
            payload = roots[(ref.record_type, ref.record_id)].payload
            if identity_field in payload:
                if payload.get(identity_field) != ref.record_id:
                    raise DossierBuildError(f"dossier {identity_field} identity differs")
                identity = dict(payload)
                identity.pop(identity_field, None)
                if _content_sha256(identity) != ref.record_id:
                    raise DossierBuildError(f"dossier {identity_field} canonical identity differs")
        matrix = roots[(MATRIX_TYPE, refs.matrix.record_id)].payload
        t2 = roots[(T2_TYPE, refs.t2.record_id)].payload
        source = roots[(SOURCE_TYPE, refs.report_source.record_id)].payload
        if t2.get("matrix") is not None and t2.get("matrix") != refs.matrix.to_dict():
            raise DossierBuildError("matrix/T2 binding differs")
        expected = {
            "quarantine_ref": refs.quarantine.to_dict(),
            "current_matrix": refs.matrix.record_id,
            "current_t2_source": refs.t2.record_id,
            "quarantine": refs.quarantine.record_id,
        }
        for payload, fields in (
            (matrix, ("quarantine_ref",)),
            (t2, ("quarantine_ref",)),
            (
                _mapping(source.get("constraints", {}), "source.constraints"),
                ("current_matrix", "current_t2_source", "quarantine"),
            ),
        ):
            for field in fields:
                if field in payload and payload.get(field) != expected[field]:
                    raise DossierBuildError("matrix/T2/source/quarantine bindings differ")
        if (
            source.get("conclusion") is not None
            and source.get("conclusion") != refs.conclusion.to_dict()
        ):
            raise DossierBuildError("source/conclusion binding differs")
        conclusion = roots[(CONCLUSION_TYPE, refs.conclusion.record_id)].payload
        evidence = conclusion.get("evidence")
        if isinstance(evidence, Sequence) and not isinstance(evidence, (str, bytes, bytearray)):
            required = {
                (ref.record_type, ref.record_id)
                for ref in (refs.matrix, refs.t2, refs.report_source, refs.quarantine)
            }
            actual = {
                (str(item.get("record_type")), str(item.get("record_id")))
                for item in evidence
                if isinstance(item, Mapping)
            }
            if not required <= actual:
                raise DossierBuildError("conclusion evidence scope differs")
        roles = _mapping(conclusion.get("scope", {}), "conclusion.scope").get("data_roles")
        if roles is not None and tuple(roles) != ("development", "validation"):
            raise DossierBuildError("conclusion historical roles differ")
        for payload in (matrix, t2, _mapping(source.get("constraints", {}), "source.constraints")):
            if "data_cutoff" in payload and payload.get("data_cutoff") != "2026-09-30":
                raise DossierBuildError("dossier historical cutoff differs")
            if (
                "holdout_guard" in payload
                and payload.get("holdout_guard") != "no_data_on_or_after_2026-10-01"
            ):
                raise DossierBuildError("dossier holdout guard differs")

    @staticmethod
    def _references(
        roots: Mapping[tuple[str, str], _Publication],
    ) -> dict[tuple[str, str], DossierRecordRef]:
        selected: dict[tuple[str, str], DossierRecordRef] = {
            key: publication.record for key, publication in roots.items()
        }

        def add(value: object, *, holdout: bool = False) -> None:
            if not isinstance(value, Mapping):
                return
            record_id, record_type = value.get("record_id"), value.get("record_type")
            if (holdout and record_type not in {LOCK_TYPE, PROOF_TYPE}) or not (
                isinstance(record_id, str)
                and isinstance(record_type, str)
                and record_type in _RECORD_SECTIONS
            ):
                return
            try:
                ref = DossierRecordRef(record_id, record_type)
            except ValueError:
                return
            selected[(record_type, record_id)] = ref

        def visit(value: object, *, holdout: bool = False) -> None:
            if isinstance(value, Mapping):
                state = value.get("data_role") or value.get("role")
                local_holdout = holdout or (isinstance(state, str) and "holdout" in state.lower())
                add(value, holdout=local_holdout)
                for key, entry in value.items():
                    key_holdout = local_holdout or "holdout" in key.lower()
                    visit(entry, holdout=key_holdout)
            elif isinstance(value, (list, tuple)):
                for entry in value:
                    visit(entry, holdout=holdout)

        for publication in roots.values():
            visit(publication.payload)
        return selected

    @staticmethod
    def _comparison_gap(
        payload: Mapping[str, object], publications: Mapping[tuple[str, str], _Publication]
    ) -> str | None:
        refs = [
            payload.get(name)
            for name in ("baseline_metrics", "comparator_metrics", "metrics")
            if payload.get(name) is not None
        ]
        identities: list[object] = []
        for raw in refs:
            if not isinstance(raw, Mapping):
                return "comparison input reference is invalid"
            key = (str(raw.get("record_type", "")), str(raw.get("record_id", "")))
            owner = publications.get(key)
            if owner is None:
                return "comparison input has no selected public owner readback"
            registration = owner.payload.get("registration")
            if not isinstance(registration, Mapping):
                return "comparison input has no registered data identity"
            registration_key = (
                REGISTRATION_TYPE,
                str(_mapping(registration, "registration").get("record_id", "")),
            )
            registration_record = publications.get(registration_key)
            if registration_record is None or "data_identity" not in registration_record.payload:
                return "registered data identity is unavailable"
            identities.append(registration_record.payload["data_identity"])
        if identities and any(identity != identities[0] for identity in identities):
            return "registered data identities are incomparable"
        return None

    def _project(self, publication: _Publication) -> DossierEvidence:
        facts = _project_scalars(publication.payload, publication.record)
        artifacts: list[DossierArtifactRef] = []
        if publication.record.record_type == FACTS_TYPE:
            for index, raw in enumerate(publication.artifacts):
                name = raw.get("name")
                if not isinstance(name, str) or not name.endswith(_NATIVE_ARTIFACT_SUFFIXES):
                    continue
                prefix = f"/native_artifacts/{index}"
                try:
                    citation, content = self._read_verified_artifact(raw)
                    if name.endswith(".csv"):
                        rows = list(csv.DictReader(io.StringIO(content.decode("utf-8"))))
                        facts.extend(
                            _project_scalars(
                                rows[:1000],
                                publication.record,
                                prefix=prefix,
                                artifact=citation,
                                native=True,
                            )
                        )
                        facts.extend(
                            _project_scalars(
                                {"total_rows": len(rows), "omitted_rows": max(0, len(rows) - 1000)},
                                publication.record,
                                prefix=prefix + "/preview",
                                artifact=citation,
                                native=False,
                            )
                        )
                    else:
                        parsed = json.loads(content.decode("utf-8"))
                        if not isinstance(parsed, Mapping):
                            raise ValueError("native artifact JSON must be an object")
                        declared = raw.get("record_schema")
                        if declared is not None and parsed.get("schema") != declared:
                            raise ValueError("native artifact schema differs")
                        facts.extend(
                            _project_scalars(
                                parsed,
                                publication.record,
                                prefix=prefix,
                                artifact=citation,
                                native=True,
                            )
                        )
                    artifacts.append(citation)
                except Exception as exc:
                    facts.append(_unavailable(prefix, publication.record, str(exc)))
        return DossierEvidence(
            publication.record,
            publication.payload_sha256,
            publication.lineage,
            tuple(sorted(set(artifacts), key=lambda item: (item.sha256, item.name))),
            tuple(sorted(facts, key=lambda item: item.path)),
        )

    def _read_verified_artifact(
        self, raw: Mapping[str, object]
    ) -> tuple[DossierArtifactRef, bytes]:
        try:
            response = self.provider.verify_artifact(raw)
        except Exception as exc:
            raise DossierBuildError(
                f"artifact verification failed: {raw.get('name', 'unknown')}"
            ) from exc
        descriptor: Mapping[str, object]
        if isinstance(response, Mapping) and "verified" in response:
            if response.get("verified") is not True:
                raise DossierBuildError(f"artifact is not verified: {raw.get('name', 'unknown')}")
            descriptor = _mapping(response.get("artifact"), "verified artifact")
        elif isinstance(response, Mapping):
            descriptor = response
        else:
            raise DossierBuildError("provider returned an invalid artifact verification")
        citation = DossierArtifactRef.from_dict(_artifact_public_dict(descriptor))
        requested = DossierArtifactRef.from_dict(_artifact_public_dict(raw))
        if citation != requested:
            raise DossierBuildError("verified artifact identity differs from source reference")
        try:
            response_bytes = self.provider.read_artifact(citation.uri)
        except Exception as exc:
            raise DossierBuildError(f"artifact read failed: {citation.name}") from exc
        content = _decode_artifact_response(response_bytes, citation)
        if hashlib.sha256(content).hexdigest() != citation.sha256:
            raise DossierBuildError(f"artifact bytes mismatch: {citation.name}")
        declared_bytes = raw.get("bytes")
        if isinstance(declared_bytes, int) and len(content) != declared_bytes:
            raise DossierBuildError(f"artifact byte count mismatch: {citation.name}")
        return citation, content


def _artifact_public_dict(value: Mapping[str, object]) -> dict[str, object]:
    return {
        "uri": _text(value.get("uri"), "artifact.uri"),
        "sha256": _sha256(_text(value.get("sha256"), "artifact.sha256")),
        "name": _text(value.get("name"), "artifact.name"),
        "record_schema": _optional_text(value.get("record_schema"), "artifact.record_schema"),
    }


def _decode_artifact_response(
    value: bytes | Mapping[str, object], citation: DossierArtifactRef
) -> bytes:
    if isinstance(value, bytes):
        return value
    item = _mapping(value, "artifact response")
    content = item.get("content")
    if item.get("encoding") != "base64" or not isinstance(content, str):
        raise DossierBuildError(f"artifact {citation.name} is not strict base64")
    try:
        return base64.b64decode(content, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise DossierBuildError(f"artifact {citation.name} has invalid base64") from exc


def _project_scalars(
    value: object,
    ref: DossierRecordRef,
    *,
    prefix: str = "",
    artifact: DossierArtifactRef | None = None,
    native: bool = True,
) -> list[DossierValue]:
    result: list[DossierValue] = []
    for pointer, item, reason in _scalars(value):
        path = prefix + pointer
        result.append(
            DossierValue(
                path,
                cast(_JSON_SCALAR, None if reason else item),
                "not_evaluated" if reason else "evaluated",
                "not_evaluated"
                if reason
                else "Runtime-native"
                if artifact and native
                else "presentation-derived",
                "no comparable verified owner value"
                if reason
                else "copied verbatim from verified Runtime artifact"
                if artifact and native
                else "public owner fact copied without metric recomputation",
                (DossierValueSource(ref, pointer, artifact),),
                reason,
            )
        )
    return result


def _scalars(value: object, pointer: str = "", inherited: str | None = None):
    if isinstance(value, Mapping):
        state = value.get("status")
        absent = (
            str(value.get("reason") or f"owner status is {state}")
            if isinstance(state, str) and state in _UNAVAILABLE_STATES
            else inherited
        )
        for key in sorted(value):
            path = pointer + "/" + _pointer_part(key)
            yield from _scalars(value[key], path, None if key in {"status", "reason"} else absent)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _scalars(item, f"{pointer}/{index}", inherited)
    else:
        yield (
            pointer or "/",
            value,
            inherited or ("owner value is unavailable" if value is None else None),
        )


def _unavailable(path: str, ref: DossierRecordRef, reason: str) -> DossierValue:
    return DossierValue(
        path,
        None,
        "not_evaluated",
        "not_evaluated",
        "no comparable verified owner value",
        (DossierValueSource(ref, path),),
        reason or "artifact value is unavailable",
    )


def _publication(raw: Mapping[str, object], expected: DossierRecordRef) -> _Publication:
    item = _mapping(raw, "publication")
    if (
        item.get("record_id") != expected.record_id
        or item.get("record_type") != expected.record_type
    ):
        raise DossierBuildError("dossier owner reference differs from public readback")
    payload = _mapping(item.get("payload"), "publication.payload")
    if payload.get("schema") not in (None, expected.record_type):
        raise DossierBuildError("dossier payload schema differs from record type")
    raw_lineage = item.get("lineage", ())
    lineage: list[DossierLineageEdge] = []
    if isinstance(raw_lineage, Sequence) and not isinstance(raw_lineage, (str, bytes, bytearray)):
        for edge in raw_lineage:
            if isinstance(edge, Mapping):
                try:
                    lineage.append(DossierLineageEdge.from_dict(edge))
                except ValueError:
                    continue
    raw_artifacts = payload.get("artifacts", item.get("artifacts", ()))
    artifacts: tuple[Mapping[str, object], ...]
    if isinstance(raw_artifacts, Sequence) and not isinstance(
        raw_artifacts, (str, bytes, bytearray)
    ):
        artifacts = tuple(_mapping(artifact, "artifact") for artifact in raw_artifacts)
    else:
        artifacts = ()
    return _Publication(
        expected,
        cast(Mapping[str, object], _freeze(payload)),
        tuple(lineage),
        _content_sha256(payload),
        artifacts,
    )


def _missing_evidence(
    ref: DossierRecordRef, reason: str, publication: _Publication | None = None
) -> DossierEvidence:
    return DossierEvidence(
        ref,
        None if publication is None else publication.payload_sha256,
        () if publication is None else publication.lineage,
        (),
        (_unavailable("/evidence", ref, reason),),
    )


__all__ = [
    "ATTRIBUTION_TYPE",
    "COMPARISON_TYPE",
    "CONCLUSION_TYPE",
    "CURRENT_DOSSIER_SOURCE_REFS",
    "DOSSIER_REPORT_SCHEMA",
    "DOSSIER_REPORT_VERSION",
    "DOSSIER_SECTION_ORDER",
    "FACTS_TYPE",
    "MATRIX_TYPE",
    "METRICS_TYPE",
    "QUARANTINE_TYPE",
    "SOURCE_TYPE",
    "T2_TYPE",
    "DossierArtifactRef",
    "DossierBuildError",
    "DossierEvidence",
    "DossierLineageEdge",
    "DossierRecordRef",
    "DossierReport",
    "DossierReportBuilder",
    "DossierSection",
    "DossierSectionName",
    "DossierSourceProvider",
    "DossierSourceRefs",
    "DossierValue",
    "DossierValueSource",
    "LineageEdge",
    "ReadOnlyDossierSourceProvider",
    "StudyRecordRef",
]
