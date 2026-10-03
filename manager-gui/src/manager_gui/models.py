"""Typed, serializable contracts shared by the Manager GUI read-only pages.

The package deliberately uses the standard library only.  The envelope is a
transport/read-model contract, not a replacement for any owner domain model.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, TypeAlias, cast

JSONValue: TypeAlias = (
    bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"] | None
)

MANAGER_READ_MODEL_SCHEMA = "manager-gui.manager-read-model.v0"
MANAGER_READ_MODEL_VERSION = "v0"


class ReadModelStatus(StrEnum):
    """The only meanings a Manager GUI value may expose to a reader."""

    KNOWN = "known"
    DERIVED = "derived"
    INTERPRETED = "interpreted"
    MISSING = "missing"
    BLOCKED = "blocked"
    STALE = "stale"
    INCOMPARABLE = "incomparable"
    INTEGRITY_FAILURE = "integrity_failure"
    API_UNAVAILABLE = "api_unavailable"


STATUS_SEMANTICS: Mapping[ReadModelStatus, str] = {
    ReadModelStatus.KNOWN: "Directly present in an owner record or verifiable artifact.",
    ReadModelStatus.DERIVED: "Reproducibly computed from named inputs and a named rule.",
    ReadModelStatus.INTERPRETED: (
        "An interpretation published by a source and not a new owner fact."
    ),
    ReadModelStatus.MISSING: "The expected value or relationship is not recorded.",
    ReadModelStatus.BLOCKED: (
        "A policy, permission, capability, or data gate prevents a determination."
    ),
    ReadModelStatus.STALE: "The value was once usable but its inputs, package, or policy changed.",
    ReadModelStatus.INCOMPARABLE: "The requested comparison axes are not compatible or complete.",
    ReadModelStatus.INTEGRITY_FAILURE: "Schema, hash, artifact, or envelope validation failed.",
    ReadModelStatus.API_UNAVAILABLE: "The approved public read seam is unavailable.",
}

_DERIVATION_KINDS = frozenset({"direct", "derived", "interpreted"})


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, field_name)


def _json_value(value: object, field_name: str) -> JSONValue:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{field_name} must be JSON serializable") from exc
    return cast(JSONValue, value)


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    if not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field_name} keys must be strings")
    return cast(Mapping[str, object], value)


def _sequence(value: object, field_name: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{field_name} must be an array")
    return value


@dataclass(frozen=True, slots=True)
class SourceReference:
    """A stable pointer to the public source of a value or error."""

    source_id: str
    owner: str
    kind: str
    locator: str
    schema: str | None = None
    revision: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.source_id, "source_id")
        _require_text(self.owner, "owner")
        _require_text(self.kind, "kind")
        _require_text(self.locator, "locator")
        _optional_text(self.schema, "schema")
        _optional_text(self.revision, "revision")

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "owner": self.owner,
            "kind": self.kind,
            "locator": self.locator,
            "schema": self.schema,
            "revision": self.revision,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> SourceReference:
        item = _mapping(value, "source_ref")
        return cls(
            source_id=_require_text(item.get("source_id"), "source_id"),
            owner=_require_text(item.get("owner"), "owner"),
            kind=_require_text(item.get("kind"), "kind"),
            locator=_require_text(item.get("locator"), "locator"),
            schema=_optional_text(item.get("schema"), "schema"),
            revision=_optional_text(item.get("revision"), "revision"),
        )


@dataclass(frozen=True, slots=True)
class Availability:
    """Machine-readable completeness and usability of a read model."""

    status: ReadModelStatus
    complete: bool
    reason: str | None = None
    retryable: bool = False

    @property
    def state(self) -> str:
        """String form useful to clients that do not import the enum."""

        return self.status.value

    def __post_init__(self) -> None:
        if not isinstance(self.status, ReadModelStatus):
            raise ValueError("status must be a ReadModelStatus")
        if not isinstance(self.complete, bool):
            raise ValueError("complete must be a boolean")
        _optional_text(self.reason, "reason")
        if not isinstance(self.retryable, bool):
            raise ValueError("retryable must be a boolean")

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "complete": self.complete,
            "reason": self.reason,
            "retryable": self.retryable,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> Availability:
        item = _mapping(value, "availability")
        raw_status = item.get("status")
        if not isinstance(raw_status, str):
            raise ValueError(f"availability.status is invalid: {raw_status!r}")
        try:
            status = ReadModelStatus(raw_status)
        except ValueError as exc:
            raise ValueError(f"availability.status is invalid: {raw_status!r}") from exc
        complete = item.get("complete")
        retryable = item.get("retryable", False)
        if not isinstance(complete, bool) or not isinstance(retryable, bool):
            raise ValueError("availability.complete and retryable must be booleans")
        return cls(
            status=status,
            complete=complete,
            reason=_optional_text(item.get("reason"), "reason"),
            retryable=retryable,
        )


@dataclass(frozen=True, slots=True)
class ReadModelError:
    """A non-silent, machine-readable failure or limitation."""

    code: str
    message: str
    source_ref: str | None = None
    retryable: bool = False
    details: Mapping[str, JSONValue] | None = None

    def __post_init__(self) -> None:
        _require_text(self.code, "code")
        _require_text(self.message, "message")
        _optional_text(self.source_ref, "source_ref")
        if not isinstance(self.retryable, bool):
            raise ValueError("retryable must be a boolean")
        if self.details is not None:
            details = _mapping(self.details, "details")
            _json_value(dict(details), "details")

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "source_ref": self.source_ref,
            "retryable": self.retryable,
            "details": None if self.details is None else dict(self.details),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> ReadModelError:
        item = _mapping(value, "error")
        raw_details = item.get("details")
        details: Mapping[str, JSONValue] | None
        if raw_details is None:
            details = None
        else:
            details_mapping = _mapping(raw_details, "details")
            details = cast(Mapping[str, JSONValue], dict(details_mapping))
            _json_value(dict(details), "details")
        retryable = item.get("retryable", False)
        if not isinstance(retryable, bool):
            raise ValueError("error.retryable must be a boolean")
        return cls(
            code=_require_text(item.get("code"), "code"),
            message=_require_text(item.get("message"), "message"),
            source_ref=_optional_text(item.get("source_ref"), "source_ref"),
            retryable=retryable,
            details=details,
        )


@dataclass(frozen=True, slots=True)
class Derivation:
    """How the data was obtained without implying an owner-domain mutation."""

    kind: str
    rule: str | None = None
    inputs: tuple[str, ...] = ()
    version: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in _DERIVATION_KINDS:
            raise ValueError(f"derivation.kind must be one of {sorted(_DERIVATION_KINDS)}")
        _optional_text(self.rule, "rule")
        _optional_text(self.version, "version")
        if not all(isinstance(item, str) and item.strip() for item in self.inputs):
            raise ValueError("derivation.inputs must contain non-empty strings")

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "rule": self.rule,
            "inputs": list(self.inputs),
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> Derivation:
        item = _mapping(value, "derivation")
        raw_inputs = _sequence(item.get("inputs", ()), "derivation.inputs")
        inputs = tuple(_require_text(entry, "derivation.inputs[]") for entry in raw_inputs)
        return cls(
            kind=_require_text(item.get("kind"), "derivation.kind"),
            rule=_optional_text(item.get("rule"), "derivation.rule"),
            inputs=inputs,
            version=_optional_text(item.get("version"), "derivation.version"),
        )


@dataclass(frozen=True, slots=True)
class ManagerReadModel:
    """The v0 envelope used by every read-only Manager GUI surface."""

    data: JSONValue
    source_refs: tuple[SourceReference, ...]
    as_of: str | None
    snapshot_token: str | None
    derivation: Derivation
    availability: Availability
    errors: tuple[ReadModelError, ...] = ()

    schema: ClassVar[str] = MANAGER_READ_MODEL_SCHEMA

    def __post_init__(self) -> None:
        _json_value(self.data, "data")
        _optional_text(self.as_of, "as_of")
        _optional_text(self.snapshot_token, "snapshot_token")
        if not all(isinstance(item, SourceReference) for item in self.source_refs):
            raise ValueError("source_refs must contain SourceReference values")
        if not isinstance(self.derivation, Derivation):
            raise ValueError("derivation must be a Derivation")
        if not isinstance(self.availability, Availability):
            raise ValueError("availability must be an Availability")
        if not all(isinstance(item, ReadModelError) for item in self.errors):
            raise ValueError("errors must contain ReadModelError values")

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible envelope with stable field names."""

        return {
            "schema": self.schema,
            "data": self.data,
            "source_refs": [item.to_dict() for item in self.source_refs],
            "as_of": self.as_of,
            "snapshot_token": self.snapshot_token,
            "derivation": self.derivation.to_dict(),
            "availability": self.availability.to_dict(),
            "errors": [item.to_dict() for item in self.errors],
        }

    def to_json(self, *, indent: int | None = None) -> str:
        """Serialize the envelope without allowing non-JSON values through."""

        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=indent,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> ManagerReadModel:
        """Read back a previously serialized v0 envelope."""

        item = _mapping(value, "read_model")
        if item.get("schema") != MANAGER_READ_MODEL_SCHEMA:
            raise ValueError("read_model.schema is not ManagerReadModel v0")
        raw_refs = _sequence(item.get("source_refs"), "source_refs")
        raw_errors = _sequence(item.get("errors"), "errors")
        refs = tuple(
            SourceReference.from_dict(_mapping(entry, "source_refs[]")) for entry in raw_refs
        )
        errors = tuple(
            ReadModelError.from_dict(_mapping(entry, "errors[]")) for entry in raw_errors
        )
        return cls(
            data=_json_value(item.get("data"), "data"),
            source_refs=refs,
            as_of=_optional_text(item.get("as_of"), "as_of"),
            snapshot_token=_optional_text(item.get("snapshot_token"), "snapshot_token"),
            derivation=Derivation.from_dict(_mapping(item.get("derivation"), "derivation")),
            availability=Availability.from_dict(_mapping(item.get("availability"), "availability")),
            errors=errors,
        )

    @classmethod
    def from_json(cls, value: str) -> ManagerReadModel:
        parsed = json.loads(value)
        return cls.from_dict(_mapping(parsed, "read_model"))


SOURCE_REFERENCE_JSON_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "manager-gui.source-reference.v0",
    "title": "Manager GUI source reference v0",
    "type": "object",
    "required": ["source_id", "owner", "kind", "locator", "schema", "revision"],
    "properties": {
        "source_id": {"type": "string", "minLength": 1},
        "owner": {"type": "string", "minLength": 1},
        "kind": {"type": "string", "minLength": 1},
        "locator": {"type": "string", "minLength": 1},
        "schema": {"type": ["string", "null"]},
        "revision": {"type": ["string", "null"]},
    },
    "additionalProperties": False,
}

AVAILABILITY_JSON_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "manager-gui.availability.v0",
    "title": "Manager GUI availability v0",
    "type": "object",
    "required": ["status", "complete", "reason", "retryable"],
    "properties": {
        "status": {"type": "string", "enum": [status.value for status in ReadModelStatus]},
        "complete": {"type": "boolean"},
        "reason": {"type": ["string", "null"]},
        "retryable": {"type": "boolean"},
    },
    "additionalProperties": False,
}

ERROR_JSON_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "manager-gui.error.v0",
    "title": "Manager GUI read-model error v0",
    "type": "object",
    "required": ["code", "message", "source_ref", "retryable", "details"],
    "properties": {
        "code": {"type": "string", "minLength": 1},
        "message": {"type": "string", "minLength": 1},
        "source_ref": {"type": ["string", "null"]},
        "retryable": {"type": "boolean"},
        "details": {"type": ["object", "null"]},
    },
    "additionalProperties": False,
}

MANAGER_READ_MODEL_JSON_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": MANAGER_READ_MODEL_SCHEMA,
    "title": "ManagerReadModel v0",
    "type": "object",
    "required": [
        "schema",
        "data",
        "source_refs",
        "as_of",
        "snapshot_token",
        "derivation",
        "availability",
        "errors",
    ],
    "properties": {
        "schema": {"const": MANAGER_READ_MODEL_SCHEMA},
        "data": {},
        "source_refs": {"type": "array", "items": SOURCE_REFERENCE_JSON_SCHEMA},
        "as_of": {"type": ["string", "null"]},
        "snapshot_token": {"type": ["string", "null"]},
        "derivation": {
            "type": "object",
            "required": ["kind", "rule", "inputs", "version"],
            "properties": {
                "kind": {"type": "string", "enum": sorted(_DERIVATION_KINDS)},
                "rule": {"type": ["string", "null"]},
                "inputs": {"type": "array", "items": {"type": "string"}},
                "version": {"type": ["string", "null"]},
            },
            "additionalProperties": False,
        },
        "availability": AVAILABILITY_JSON_SCHEMA,
        "errors": {"type": "array", "items": ERROR_JSON_SCHEMA},
    },
    "additionalProperties": False,
}

# Short aliases keep imports pleasant while the explicit class names remain clear in schemas.
Error = ReadModelError
Status = ReadModelStatus

__all__ = [
    "AVAILABILITY_JSON_SCHEMA",
    "DERIVATION_KINDS",
    "ERROR_JSON_SCHEMA",
    "MANAGER_READ_MODEL_JSON_SCHEMA",
    "MANAGER_READ_MODEL_SCHEMA",
    "MANAGER_READ_MODEL_VERSION",
    "SOURCE_REFERENCE_JSON_SCHEMA",
    "STATUS_SEMANTICS",
    "Availability",
    "Derivation",
    "Error",
    "JSONValue",
    "ManagerReadModel",
    "ReadModelError",
    "ReadModelStatus",
    "SourceReference",
    "Status",
]

# Public, immutable view for callers that need to expose the allowed derivation values.
DERIVATION_KINDS = frozenset(_DERIVATION_KINDS)
