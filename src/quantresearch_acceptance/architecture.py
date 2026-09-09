"""Machine admission for the TEST-001 infrastructure owner seam."""

from __future__ import annotations

import json
from pathlib import Path

from .core import AcceptanceFailure

_FIELDS = {
    "schema",
    "test",
    "canonical_owner",
    "public_seam",
    "identity_impact",
    "evidence_level",
    "fail_closed_behavior",
    "owner_semantics_changed",
}


def validate_test001_admission(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceFailure(f"cannot read TEST-001 admission: {exc}") from exc
    if not isinstance(value, dict) or set(value) != _FIELDS:
        raise AcceptanceFailure("TEST-001 admission fields are invalid")
    if (
        value["schema"] != "quant-research.test-infrastructure-admission.v1"
        or value["test"] != "TEST-001"
        or value["canonical_owner"] != "quant_research"
        or value["owner_semantics_changed"] is not False
        or not all(
            isinstance(value[field], str) and value[field].strip()
            for field in (
                "public_seam",
                "identity_impact",
                "evidence_level",
                "fail_closed_behavior",
            )
        )
        or "AcceptanceSelector" not in value["public_seam"]
        or "fail closed" not in value["fail_closed_behavior"].lower()
    ):
        raise AcceptanceFailure("TEST-001 admission violates the constitution")
    return value
