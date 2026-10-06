"""Machine-readable JSON Schema for the UI-only ReaderProjection v1 contract."""

from __future__ import annotations

from typing import Final

from .models import (
    ClaimKind,
    READER_PROJECTION_SCHEMA,
    ReaderAvailabilityStatus,
)

_SOURCE_REF: Final[dict[str, object]] = {
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

_DERIVATION: Final[dict[str, object]] = {
    "type": "object",
    "required": ["kind", "rule", "inputs", "version"],
    "properties": {
        "kind": {"type": "string", "enum": ["direct", "derived", "interpreted"]},
        "rule": {"type": ["string", "null"]},
        "inputs": {"type": "array", "items": {"type": "string"}},
        "version": {"type": ["string", "null"]},
    },
    "additionalProperties": False,
}

_AVAILABILITY: Final[dict[str, object]] = {
    "type": "object",
    "required": ["status", "complete", "reason", "retryable"],
    "properties": {
        "status": {"type": "string", "enum": [status.value for status in ReaderAvailabilityStatus]},
        "complete": {"type": "boolean"},
        "reason": {"type": ["string", "null"]},
        "retryable": {"type": "boolean"},
    },
    "additionalProperties": False,
}

_CLAIM: Final[dict[str, object]] = {
    "type": "object",
    "required": [
        "claim_id", "kind", "source_refs", "derivation", "availability", "value",
        "explanation_key",
    ],
    "properties": {
        "claim_id": {"type": "string", "minLength": 1},
        "kind": {"type": "string", "enum": [kind.value for kind in ClaimKind]},
        "source_refs": {"type": "array", "items": _SOURCE_REF},
        "derivation": _DERIVATION,
        "availability": _AVAILABILITY,
        "value": {},
        "explanation_key": {"type": "string", "minLength": 1},
    },
    "additionalProperties": False,
}

_SUMMARY: Final[dict[str, object]] = {
    "type": "object",
    "required": ["template_key", "claim_ids", "params"],
    "properties": {
        "template_key": {"type": "string", "minLength": 1},
        "claim_ids": {"type": "array", "items": {"type": "string", "minLength": 1}},
        "params": {"type": "object", "additionalProperties": {"type": [
            "boolean", "integer", "number", "string", "null",
        ]}},
    },
    "additionalProperties": False,
}

_SAMPLE_DATA: Final[dict[str, object]] = {
    "type": "object",
    "required": ["fixture_state", "resource", "version", "banner_key"],
    "properties": {
        "fixture_state": {"type": "string", "minLength": 1},
        "resource": {"type": "string", "minLength": 1},
        "version": {"type": "string", "minLength": 1},
        "banner_key": {"const": "reader.sample.banner"},
    },
    "additionalProperties": False,
}

_RAW_SOURCE: Final[dict[str, object]] = {
    "type": "object",
    "required": ["schema", "encoding", "bytes", "sha256"],
    "properties": {
        "schema": {"const": "manager-gui.manager-read-model.v0"},
        "encoding": {"const": "base64"},
        "bytes": {"type": "string", "minLength": 1},
        "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    },
    "additionalProperties": False,
}

READER_PROJECTION_JSON_SCHEMA: Final[dict[str, object]] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": READER_PROJECTION_SCHEMA,
    "title": "Manager GUI ReaderProjection v1",
    "type": "object",
    "required": [
        "schema", "data", "summary", "claims", "limitations", "unknowns", "source_refs",
        "as_of", "snapshot_token", "derivation", "availability", "raw_source", "sample_data",
    ],
    "properties": {
        "schema": {"const": READER_PROJECTION_SCHEMA},
        "data": {},
        "summary": {"type": ["object", "null"], "allOf": [{"$ref": "#/$defs/summary"}]},
        "claims": {"type": "array", "items": {"$ref": "#/$defs/claim"}},
        "limitations": {"type": "array", "items": {"$ref": "#/$defs/claim"}},
        "unknowns": {"type": "array", "items": {"$ref": "#/$defs/claim"}},
        "source_refs": {"type": "array", "items": {"$ref": "#/$defs/source_ref"}},
        "as_of": {"type": ["string", "null"]},
        "snapshot_token": {"type": ["string", "null"]},
        "derivation": {"$ref": "#/$defs/derivation"},
        "availability": {"$ref": "#/$defs/availability"},
        "raw_source": {"$ref": "#/$defs/raw_source"},
        "sample_data": {"type": ["object", "null"], "allOf": [{"$ref": "#/$defs/sample_data"}]},
    },
    "$defs": {
        "source_ref": _SOURCE_REF,
        "derivation": _DERIVATION,
        "availability": _AVAILABILITY,
        "claim": _CLAIM,
        "summary": _SUMMARY,
        "sample_data": _SAMPLE_DATA,
        "raw_source": _RAW_SOURCE,
    },
    "additionalProperties": False,
}

__all__ = ["READER_PROJECTION_JSON_SCHEMA"]
