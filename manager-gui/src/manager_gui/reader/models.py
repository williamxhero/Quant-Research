"""UI-only Reader v1 contracts; owner values and v0 bytes remain authoritative.

Copy belongs to the Reader catalog. This module exposes machine keys and typed
values only: availability describes what can be read, never a research outcome.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import ClassVar, TypeAlias, cast

from manager_gui.models import (
    MANAGER_READ_MODEL_SCHEMA,
    Availability,
    Derivation,
    ManagerReadModel,
    SourceReference,
)

READER_PROJECTION_SCHEMA = "manager-gui.reader-projection.v1"
READER_PROJECTION_VERSION = "v1"
SAMPLE_BANNER_KEY = "reader.sample.banner"

FrozenJSON: TypeAlias = (
    bool | int | float | str | tuple["FrozenJSON", ...] | Mapping[str, "FrozenJSON"] | None
)
TemplateValue: TypeAlias = bool | int | float | str | None


class ClaimKind(StrEnum):
    KNOWN = "Known"
    DERIVED = "Derived"
    INTERPRETED = "Interpreted"
    MISSING = "Missing"
    BLOCKED = "Blocked"
    STALE = "Stale"
    INCOMPARABLE = "Incomparable"
    OWNER_TEXT = "OwnerText"


class ReaderAvailabilityStatus(StrEnum):
    KNOWN = "known"
    DERIVED = "derived"
    INTERPRETED = "interpreted"
    MISSING = "missing"
    BLOCKED = "blocked"
    STALE = "stale"
    INCOMPARABLE = "incomparable"
    NOT_EVALUATED = "not_evaluated"
    INTEGRITY_FAILURE = "integrity_failure"
    API_UNAVAILABLE = "api_unavailable"


class ProjectionMode(StrEnum):
    READER = "reader"
    EXPERT = "expert"
    RAW = "raw"


_GAP_KINDS = frozenset(
    {ClaimKind.MISSING, ClaimKind.BLOCKED, ClaimKind.STALE, ClaimKind.INCOMPARABLE}
)
_EXPLANATION_KEYS: dict[ClaimKind, str] = {
    kind: f"reader.claim.{kind.value.lower()}"
    for kind in ClaimKind
    if kind is not ClaimKind.OWNER_TEXT
}
_EXPLANATION_KEYS[ClaimKind.OWNER_TEXT] = "reader.claim.owner_text"


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value  # Never strip or translate source text, identifiers or locators.


def _optional_text(value: object, name: str) -> str | None:
    return None if value is None else _text(value, name)


def _object(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be an object with string keys")
    return cast(Mapping[str, object], value)


def _array(value: object, name: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{name} must be an array")
    return value


def _fields(value: Mapping[str, object], names: set[str], name: str) -> None:
    if set(value) != names:
        raise ValueError(f"{name} fields must be {sorted(names)}")


def _freeze(value: object) -> FrozenJSON:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    if isinstance(value, Mapping):
        item = _object(value, "JSON value")
        return MappingProxyType({key: _freeze(entry) for key, entry in item.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(entry) for entry in value)
    raise ValueError("Reader values must be finite JSON values")


def _thaw(value: FrozenJSON) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw(entry) for key, entry in value.items()}
    if isinstance(value, tuple):
        return [_thaw(entry) for entry in value]
    return value


def _params(value: Mapping[str, TemplateValue]) -> Mapping[str, TemplateValue]:
    item = _object(value, "params")
    frozen = {key: _freeze(entry) for key, entry in item.items()}
    if any(isinstance(entry, (Mapping, tuple)) for entry in frozen.values()):
        raise ValueError("template params must be JSON scalars")
    return cast(Mapping[str, TemplateValue], MappingProxyType(frozen))


def _derivation(value: Derivation) -> Derivation:
    if not isinstance(value, Derivation):
        raise ValueError("derivation must be a Derivation")
    # v0 is frozen but permits a mutable input list; detach it at this boundary.
    return Derivation(value.kind, value.rule, tuple(value.inputs), value.version)


def _refs(value: tuple[SourceReference, ...]) -> tuple[SourceReference, ...]:
    refs = tuple(value)
    if not all(isinstance(ref, SourceReference) for ref in refs):
        raise ValueError("source_refs must contain SourceReference values")
    if len({ref.source_id for ref in refs}) != len(refs):
        raise ValueError("source_refs must have unique source_id values")
    return refs


@dataclass(frozen=True, slots=True)
class ReaderAvailability:
    """Completeness of the source scope; no pass/fail or success/failure inference."""

    status: ReaderAvailabilityStatus
    complete: bool
    reason: str | None = None
    retryable: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.status, ReaderAvailabilityStatus):
            raise ValueError("status must be a ReaderAvailabilityStatus")
        if not isinstance(self.complete, bool) or not isinstance(self.retryable, bool):
            raise ValueError("complete and retryable must be booleans")
        _optional_text(self.reason, "reason")
        if self.complete and self.status in {
            ReaderAvailabilityStatus.MISSING,
            ReaderAvailabilityStatus.BLOCKED,
            ReaderAvailabilityStatus.NOT_EVALUATED,
            ReaderAvailabilityStatus.API_UNAVAILABLE,
            ReaderAvailabilityStatus.INTEGRITY_FAILURE,
            ReaderAvailabilityStatus.INCOMPARABLE,
        }:
            raise ValueError("unavailable or unevaluated scope cannot be complete")

    @classmethod
    def from_v0(cls, availability: Availability) -> ReaderAvailability:
        return cls(
            ReaderAvailabilityStatus(availability.status.value),
            availability.complete,
            availability.reason,
            availability.retryable,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "complete": self.complete,
            "reason": self.reason,
            "retryable": self.retryable,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> ReaderAvailability:
        _fields(value, {"status", "complete", "reason", "retryable"}, "availability")
        return cls(
            ReaderAvailabilityStatus(_text(value["status"], "status")),
            cast(bool, value["complete"]),
            _optional_text(value["reason"], "reason"),
            cast(bool, value["retryable"]),
        )


@dataclass(frozen=True, slots=True)
class ReaderClaim:
    """A typed assertion or gap with explicit source scope and acquisition rule.

    ``value`` is source content or a named rule's result. ``explanation_key`` is
    for later catalog rendering; it never upgrades owner text or gaps to facts.
    """

    claim_id: str
    kind: ClaimKind
    source_refs: tuple[SourceReference, ...]
    derivation: Derivation
    availability: ReaderAvailability
    value: FrozenJSON = None

    def __post_init__(self) -> None:
        _text(self.claim_id, "claim_id")
        if not isinstance(self.kind, ClaimKind):
            raise ValueError("kind must be a ClaimKind")
        object.__setattr__(self, "source_refs", _refs(self.source_refs))
        object.__setattr__(self, "derivation", _derivation(self.derivation))
        object.__setattr__(self, "value", _freeze(self.value))
        if not self.source_refs:
            raise ValueError("every claim must name a source scope, including a gap")
        if not isinstance(self.availability, ReaderAvailability):
            raise ValueError("availability must be a ReaderAvailability")
        source_ids = {ref.source_id for ref in self.source_refs}
        if not self.derivation.inputs or not set(self.derivation.inputs) <= source_ids:
            raise ValueError("claim derivation inputs must name its source_refs")
        expected_derivation = {
            ClaimKind.KNOWN: "direct",
            ClaimKind.OWNER_TEXT: "direct",
            ClaimKind.DERIVED: "derived",
            ClaimKind.INTERPRETED: "interpreted",
        }.get(self.kind)
        if expected_derivation is not None and self.derivation.kind != expected_derivation:
            raise ValueError("claim kind and derivation kind disagree")
        if self.derivation.kind != "direct" and (
            self.derivation.rule is None or self.derivation.version is None
        ):
            raise ValueError("non-direct claims require a named rule and version")
        expected_status: dict[ClaimKind, set[ReaderAvailabilityStatus]] = {
            ClaimKind.KNOWN: {ReaderAvailabilityStatus.KNOWN},
            ClaimKind.DERIVED: {ReaderAvailabilityStatus.DERIVED},
            ClaimKind.INTERPRETED: {ReaderAvailabilityStatus.INTERPRETED},
            ClaimKind.OWNER_TEXT: {ReaderAvailabilityStatus.KNOWN},
            ClaimKind.MISSING: {
                ReaderAvailabilityStatus.MISSING,
                ReaderAvailabilityStatus.NOT_EVALUATED,
                ReaderAvailabilityStatus.API_UNAVAILABLE,
            },
            ClaimKind.BLOCKED: {
                ReaderAvailabilityStatus.BLOCKED,
                ReaderAvailabilityStatus.INTEGRITY_FAILURE,
            },
            ClaimKind.STALE: {ReaderAvailabilityStatus.STALE},
            ClaimKind.INCOMPARABLE: {ReaderAvailabilityStatus.INCOMPARABLE},
        }
        if self.availability.status not in expected_status[self.kind]:
            raise ValueError("claim kind and availability disagree")
        if self.kind is ClaimKind.OWNER_TEXT and not isinstance(self.value, str):
            raise ValueError("OwnerText must retain an original string")

    @property
    def explanation_key(self) -> str:
        return _EXPLANATION_KEYS[self.kind]

    @property
    def is_gap(self) -> bool:
        return self.kind in _GAP_KINDS

    def to_dict(self) -> dict[str, object]:
        return {
            "claim_id": self.claim_id,
            "kind": self.kind.value,
            "source_refs": [ref.to_dict() for ref in self.source_refs],
            "derivation": self.derivation.to_dict(),
            "availability": self.availability.to_dict(),
            "value": _thaw(self.value),
            "explanation_key": self.explanation_key,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> ReaderClaim:
        _fields(
            value,
            {
                "claim_id",
                "kind",
                "source_refs",
                "derivation",
                "availability",
                "value",
                "explanation_key",
            },
            "claim",
        )
        claim = cls(
            _text(value["claim_id"], "claim_id"),
            ClaimKind(_text(value["kind"], "kind")),
            tuple(
                SourceReference.from_dict(_object(ref, "source_ref"))
                for ref in _array(value["source_refs"], "source_refs")
            ),
            Derivation.from_dict(_object(value["derivation"], "derivation")),
            ReaderAvailability.from_dict(_object(value["availability"], "availability")),
            _freeze(value["value"]),
        )
        if value["explanation_key"] != claim.explanation_key:
            raise ValueError("claim explanation_key must match its kind")
        return claim


@dataclass(frozen=True, slots=True)
class ReaderSummary:
    """Reproducible copy template inputs; prose is rendered outside the envelope."""

    template_key: str
    claim_ids: tuple[str, ...]
    params: Mapping[str, TemplateValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _text(self.template_key, "template_key")
        ids = tuple(self.claim_ids)
        if not ids or any(not isinstance(value, str) or not value.strip() for value in ids):
            raise ValueError("summary must reference at least one claim")
        if len(ids) != len(set(ids)):
            raise ValueError("summary claim_ids must be unique")
        object.__setattr__(self, "claim_ids", ids)
        object.__setattr__(self, "params", _params(self.params))

    def to_dict(self) -> dict[str, object]:
        return {
            "template_key": self.template_key,
            "claim_ids": list(self.claim_ids),
            "params": dict(self.params),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> ReaderSummary:
        _fields(value, {"template_key", "claim_ids", "params"}, "summary")
        return cls(
            _text(value["template_key"], "template_key"),
            tuple(_text(entry, "claim_id") for entry in _array(value["claim_ids"], "claim_ids")),
            cast(Mapping[str, TemplateValue], _object(value["params"], "params")),
        )


@dataclass(frozen=True, slots=True)
class SampleData:
    """Explicit fixture provenance, never inferred from a URL or source contents."""

    fixture_state: str
    resource: str
    version: str = READER_PROJECTION_VERSION
    banner_key: ClassVar[str] = SAMPLE_BANNER_KEY

    def __post_init__(self) -> None:
        for name in ("fixture_state", "resource", "version"):
            _text(getattr(self, name), name)

    def to_dict(self) -> dict[str, object]:
        return {
            "fixture_state": self.fixture_state,
            "resource": self.resource,
            "version": self.version,
            "banner_key": self.banner_key,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> SampleData:
        _fields(value, {"fixture_state", "resource", "version", "banner_key"}, "sample_data")
        if value["banner_key"] != SAMPLE_BANNER_KEY:
            raise ValueError("invalid sample banner_key")
        return cls(
            _text(value["fixture_state"], "fixture_state"),
            _text(value["resource"], "resource"),
            _text(value["version"], "version"),
        )


@dataclass(frozen=True, slots=True)
class RawSource:
    """The exact v0 transport bytes, or v0 canonical serialization if none supplied."""

    raw_bytes: bytes
    _model: ManagerReadModel = field(init=False, repr=False, compare=False)
    schema: ClassVar[str] = MANAGER_READ_MODEL_SCHEMA

    def __post_init__(self) -> None:
        if not isinstance(self.raw_bytes, bytes):
            raise ValueError("raw_bytes must be immutable bytes")
        object.__setattr__(
            self, "_model", ManagerReadModel.from_json(self.raw_bytes.decode("utf-8")),
        )

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.raw_bytes).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "encoding": "base64",
            "bytes": base64.b64encode(self.raw_bytes).decode("ascii"),
            "sha256": self.sha256,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> RawSource:
        _fields(value, {"schema", "encoding", "bytes", "sha256"}, "raw_source")
        if value["schema"] != cls.schema or value["encoding"] != "base64":
            raise ValueError("raw_source must contain a base64 ManagerReadModel v0")
        try:
            raw = base64.b64decode(_text(value["bytes"], "bytes"), validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("invalid raw_source bytes") from exc
        source = cls(raw)
        if source.sha256 != value["sha256"]:
            raise ValueError("raw_source digest mismatch")
        return source


@dataclass(frozen=True, slots=True)
class ProjectionReference:
    """A mode points to Reader v1 or its retained v0 source; it mutates neither."""

    mode: ProjectionMode
    schema: str
    snapshot_token: str | None
    sha256: str


@dataclass(frozen=True, slots=True)
class ReaderProjection:
    """A replayable, deeply immutable view of one public v0 envelope."""

    data: FrozenJSON
    summary: ReaderSummary | None
    claims: tuple[ReaderClaim, ...]
    limitations: tuple[ReaderClaim, ...]
    unknowns: tuple[ReaderClaim, ...]
    source_refs: tuple[SourceReference, ...]
    as_of: str | None
    snapshot_token: str | None
    derivation: Derivation
    availability: ReaderAvailability
    raw_source: RawSource
    sample_data: SampleData | None = None

    schema: ClassVar[str] = READER_PROJECTION_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", _freeze(self.data))
        object.__setattr__(self, "source_refs", _refs(self.source_refs))
        object.__setattr__(self, "derivation", _derivation(self.derivation))
        _optional_text(self.as_of, "as_of")
        _optional_text(self.snapshot_token, "snapshot_token")
        if self.summary is not None and not isinstance(self.summary, ReaderSummary):
            raise ValueError("summary must be a ReaderSummary or null")
        if not isinstance(self.availability, ReaderAvailability):
            raise ValueError("availability must be a ReaderAvailability")
        if not isinstance(self.raw_source, RawSource):
            raise ValueError("raw_source must be a RawSource")
        all_claims: list[ReaderClaim] = []
        source_index = {ref.source_id: ref for ref in self.source_refs}
        for name in ("claims", "limitations", "unknowns"):
            entries = tuple(getattr(self, name))
            if not all(isinstance(entry, ReaderClaim) for entry in entries):
                raise ValueError(f"{name} must contain ReaderClaim values")
            if name == "unknowns" and any(not entry.is_gap for entry in entries):
                raise ValueError("unknowns must be gap claims")
            for entry in entries:
                if any(source_index.get(ref.source_id) != ref for ref in entry.source_refs):
                    raise ValueError("claim source_refs must match the projection source scope")
            object.__setattr__(self, name, entries)
            all_claims.extend(entries)
        ids = [entry.claim_id for entry in all_claims]
        if len(set(ids)) != len(ids):
            raise ValueError("claim_ids must be unique across claims, limitations and unknowns")
        if self.summary is not None and not set(self.summary.claim_ids) <= set(ids):
            raise ValueError("summary references an unknown claim")
        if (
            self.derivation.kind != "derived"
            or not self.derivation.rule
            or not self.derivation.version
        ):
            raise ValueError("Reader projection must name its GUI derivation rule and version")
        if not set(self.derivation.inputs) <= set(source_index):
            raise ValueError("projection derivation inputs must name source_refs")
        original = self.raw_source._model
        if (
            _thaw(self.data) != original.data
            or self.source_refs != original.source_refs
            or self.as_of != original.as_of
            or self.snapshot_token != original.snapshot_token
        ):
            raise ValueError("projection must preserve v0 data and source provenance")
        if self.sample_data is not None:
            if not isinstance(self.sample_data, SampleData):
                raise ValueError("sample_data must be SampleData or null")
            if any(not ref.locator.startswith("fixture://") for ref in self.source_refs):
                raise ValueError("owner source scope cannot inherit sample metadata")

    def mode_reference(self, mode: ProjectionMode | str) -> ProjectionReference:
        selected = ProjectionMode(mode)
        if selected is ProjectionMode.READER:
            return ProjectionReference(
                selected,
                self.schema,
                self.snapshot_token,
                hashlib.sha256(self.to_json().encode("utf-8")).hexdigest(),
            )
        return ProjectionReference(
            selected, self.raw_source.schema, self.snapshot_token, self.raw_source.sha256
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "data": _thaw(self.data),
            "summary": None if self.summary is None else self.summary.to_dict(),
            "claims": [claim.to_dict() for claim in self.claims],
            "limitations": [claim.to_dict() for claim in self.limitations],
            "unknowns": [claim.to_dict() for claim in self.unknowns],
            "source_refs": [ref.to_dict() for ref in self.source_refs],
            "as_of": self.as_of,
            "snapshot_token": self.snapshot_token,
            "derivation": self.derivation.to_dict(),
            "availability": self.availability.to_dict(),
            "raw_source": self.raw_source.to_dict(),
            "sample_data": None if self.sample_data is None else self.sample_data.to_dict(),
        }

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(
            self.to_dict(), ensure_ascii=False, allow_nan=False, sort_keys=True, indent=indent
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> ReaderProjection:
        _fields(
            value,
            {
                "schema",
                "data",
                "summary",
                "claims",
                "limitations",
                "unknowns",
                "source_refs",
                "as_of",
                "snapshot_token",
                "derivation",
                "availability",
                "raw_source",
                "sample_data",
            },
            "projection",
        )
        if value["schema"] != READER_PROJECTION_SCHEMA:
            raise ValueError("projection.schema is not ReaderProjection v1")
        summary, sample = value["summary"], value["sample_data"]
        groups = {
            name: tuple(
                ReaderClaim.from_dict(_object(entry, name)) for entry in _array(value[name], name)
            )
            for name in ("claims", "limitations", "unknowns")
        }
        return cls(
            _freeze(value["data"]),
            None if summary is None else ReaderSummary.from_dict(_object(summary, "summary")),
            groups["claims"],
            groups["limitations"],
            groups["unknowns"],
            tuple(
                SourceReference.from_dict(_object(entry, "source_ref"))
                for entry in _array(value["source_refs"], "source_refs")
            ),
            _optional_text(value["as_of"], "as_of"),
            _optional_text(value["snapshot_token"], "snapshot_token"),
            Derivation.from_dict(_object(value["derivation"], "derivation")),
            ReaderAvailability.from_dict(_object(value["availability"], "availability")),
            RawSource.from_dict(_object(value["raw_source"], "raw_source")),
            None if sample is None else SampleData.from_dict(_object(sample, "sample_data")),
        )

    @classmethod
    def from_json(cls, value: str) -> ReaderProjection:
        return cls.from_dict(_object(json.loads(value), "projection"))


def project_read_model(
    model: ManagerReadModel,
    *,
    summary: ReaderSummary | None = None,
    claims: tuple[ReaderClaim, ...] = (),
    limitations: tuple[ReaderClaim, ...] = (),
    unknowns: tuple[ReaderClaim, ...] = (),
    raw_bytes: bytes | None = None,
) -> ReaderProjection:
    """Copy a public envelope without guessing claims, evaluations or sample origin.

    Providers returning only a v0 object cannot recover original transport bytes;
    pass them explicitly when available. Otherwise v0's own serialization is kept.
    Sample labeling is reserved for the explicit Reader fixture factory.
    """

    raw = RawSource(model.to_json().encode("utf-8") if raw_bytes is None else raw_bytes)
    original = raw._model
    if original.to_dict() != model.to_dict():
        raise ValueError("raw_bytes must describe the supplied v0 envelope")
    return ReaderProjection(
        _freeze(model.data),
        summary,
        claims,
        limitations,
        unknowns,
        tuple(model.source_refs),
        model.as_of,
        model.snapshot_token,
        Derivation(
            "derived",
            "manager-gui.reader.identity-projection",
            tuple(ref.source_id for ref in model.source_refs),
            READER_PROJECTION_VERSION,
        ),
        (
            ReaderAvailability(
                ReaderAvailabilityStatus.NOT_EVALUATED,
                False,
                model.availability.reason,
                model.availability.retryable,
            )
            if model.availability.status.value == "known"
            and any(error.code == "not_evaluated" for error in model.errors)
            else ReaderAvailability.from_v0(model.availability)
        ),
        raw,
    )
