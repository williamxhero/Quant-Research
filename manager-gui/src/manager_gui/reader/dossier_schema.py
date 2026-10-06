"""Machine-readable JSON Schema for the evidence-bound Dossier v2 model."""

from __future__ import annotations

from typing import Final

_SHA256: Final[dict[str, object]] = {
    "type": "string",
    "pattern": "^[0-9a-f]{64}$",
}

_RECORD_REF: Final[dict[str, object]] = {
    "type": "object",
    "required": ["record_id", "record_type"],
    "properties": {
        "record_id": _SHA256,
        "record_type": {"type": "string", "minLength": 1},
    },
    "additionalProperties": False,
}

_ARTIFACT: Final[dict[str, object]] = {
    "type": "object",
    "required": ["uri", "sha256", "name", "record_schema"],
    "properties": {
        "uri": {"type": "string", "pattern": "^workspace-artifact://sha256/[0-9a-f]{64}$"},
        "sha256": _SHA256,
        "name": {"type": "string", "minLength": 1},
        "record_schema": {"type": ["string", "null"]},
    },
    "additionalProperties": False,
}

_VALUE_SOURCE: Final[dict[str, object]] = {
    "type": "object",
    "required": ["record", "selector", "artifact"],
    "properties": {
        "record": _RECORD_REF,
        "selector": {"type": "string", "pattern": "^/"},
        "artifact": {"anyOf": [_ARTIFACT, {"type": "null"}]},
    },
    "additionalProperties": False,
}

_VALUE: Final[dict[str, object]] = {
    "type": "object",
    "required": [
        "path",
        "value",
        "status",
        "derivation",
        "derivation_reason",
        "sources",
        "reason",
    ],
    "properties": {
        "path": {"type": "string", "pattern": "^/"},
        "value": {"type": ["boolean", "integer", "number", "string", "null"]},
        "status": {"enum": ["evaluated", "not_evaluated"]},
        "derivation": {
            "enum": ["Runtime-native", "presentation-derived", "not_evaluated"]
        },
        "derivation_reason": {"type": "string", "minLength": 1},
        "sources": {"type": "array", "minItems": 1, "items": _VALUE_SOURCE},
        "reason": {"type": ["string", "null"]},
    },
    "additionalProperties": False,
}

_EVIDENCE: Final[dict[str, object]] = {
    "type": "object",
    "required": ["source", "payload_sha256", "lineage", "artifacts", "facts"],
    "properties": {
        "source": _RECORD_REF,
        "payload_sha256": {"anyOf": [_SHA256, {"type": "null"}]},
        "lineage": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["source_kind", "source_id", "relation"],
                "properties": {
                    "source_kind": {"type": "string", "minLength": 1},
                    "source_id": {"type": "string", "minLength": 1},
                    "relation": {"type": "string", "minLength": 1},
                },
                "additionalProperties": False,
            },
        },
        "artifacts": {"type": "array", "items": _ARTIFACT},
        "facts": {"type": "array", "items": _VALUE},
    },
    "additionalProperties": False,
}

_SECTION: Final[dict[str, object]] = {
    "type": "object",
    "required": ["name", "status", "reason", "evidence"],
    "properties": {
        "name": {
            "enum": [
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
            ]
        },
        "status": {"enum": ["evaluated", "not_evaluated"]},
        "reason": {"type": ["string", "null"]},
        "evidence": {"type": "array", "items": _EVIDENCE},
    },
    "additionalProperties": False,
}

_SOURCE_REFS_BASE: Final[dict[str, object]] = {
    "type": "object",
    "required": ["matrix", "t2", "report_source", "quarantine", "conclusion"],
    "properties": {
        "matrix": _RECORD_REF,
        "t2": _RECORD_REF,
        "report_source": _RECORD_REF,
        "quarantine": _RECORD_REF,
        "conclusion": _RECORD_REF,
    },
    "additionalProperties": False,
}
_SOURCE_REFS_V2: Final[dict[str, object]] = {
    "type": "object",
    "required": [
        "matrix",
        "t2",
        "report_source",
        "quarantine",
        "conclusion",
        "holdout_lock",
        "holdout_proof",
    ],
    "properties": {
        **_SOURCE_REFS_BASE["properties"],
        "holdout_lock": _RECORD_REF,
        "holdout_proof": _RECORD_REF,
    },
    "additionalProperties": False,
}

DOSSIER_REPORT_JSON_SCHEMA: Final[dict[str, object]] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "urn:manager-gui:dossier-report:v2",
    "title": "Evidence-bound development and validation Dossier v2",
    "type": "object",
    "required": [
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
    ],
    "properties": {
        "schema": {"const": "manager-gui.dossier-report.v2"},
        "title": {"type": "string", "minLength": 1},
        "banner": {"type": "string", "minLength": 1},
        "source_refs": {"anyOf": [_SOURCE_REFS_V2, _SOURCE_REFS_BASE]},
        "sections": {"type": "array", "minItems": 10, "maxItems": 10, "items": _SECTION},
        "source_records": {"type": "array", "items": _RECORD_REF},
        "source_artifacts": {"type": "array", "items": _ARTIFACT},
        "evidence_ceiling": {"const": "candidate_evidence"},
        "qualification_inference": {"const": "forbidden"},
        "causal_inference": {"const": "forbidden"},
        "production_approval_inference": {"const": "forbidden"},
        "holdout_results": {"const": "not_evaluated"},
    },
    "additionalProperties": False,
}

__all__ = ["DOSSIER_REPORT_JSON_SCHEMA"]
