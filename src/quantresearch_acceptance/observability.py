"""Marker and duration admission for acceptance evidence."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from .core import AcceptanceFailure

_FIELDS = {
    "nodeid",
    "duration_seconds",
    "file_duration_seconds",
    "markers",
    "explanation",
}
_MARKERS = {"slow", "oci", "connected", "release"}


def audit_performance(records: Sequence[Mapping[str, object]]) -> tuple[()]:
    """Reject unmarked or unexplained tests exceeding the 2s/60s thresholds."""
    for record in records:
        if set(record) != _FIELDS:
            raise AcceptanceFailure("performance record fields are invalid")
        nodeid = record["nodeid"]
        duration = record["duration_seconds"]
        file_duration = record["file_duration_seconds"]
        markers = record["markers"]
        explanation = record["explanation"]
        if (
            not isinstance(nodeid, str)
            or not nodeid
            or not isinstance(duration, (int, float))
            or isinstance(duration, bool)
            or not math.isfinite(duration)
            or duration < 0
            or not isinstance(file_duration, (int, float))
            or isinstance(file_duration, bool)
            or not math.isfinite(file_duration)
            or file_duration < duration
            or not isinstance(markers, list)
            or markers != sorted(set(markers))
            or any(marker not in _MARKERS for marker in markers)
            or not isinstance(explanation, str)
        ):
            raise AcceptanceFailure(f"performance record is invalid: {nodeid!r}")
        if (duration > 2 or file_duration > 60) and (
            "slow" not in markers or not explanation.strip()
        ):
            raise AcceptanceFailure(
                f"slow test/file requires marker and explanation: {nodeid}"
            )
    return ()
