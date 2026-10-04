"""Integrated, deterministic fixtures for the four S4 shared-shell routes.

The shell exposes one ``fixture`` selector.  This module maps each selector
value onto the four S4 read seams (Evidence Ledger, bounded Lineage, general
object comparison, Derived grouping) by choosing the owning module's own
builder.  It never reads storage, never fabricates an owner fact, and adds only
the explicit cross-resource pointers (``conclusion_id`` / ``lineage_id``) that
make the conclusion -> evidence -> artifact -> lineage path walkable in a
fixture run.  A state a seam cannot express natively (for example an expired
cursor on the Evidence Ledger) is represented as a ``stale`` envelope that
names the real cause, never as an empty or successful read.
"""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any, cast

from ..fixtures import FixtureState
from ..models import Availability, ManagerReadModel, ReadModelError, ReadModelStatus
from .evidence import EVIDENCE_RESOURCE, EvidenceFixtureState, build_evidence_fixture
from .evidence_comparison import (
    EVIDENCE_COMPARISON_RESOURCE,
    EvidenceComparisonFixtureState,
    build_evidence_comparison_fixture,
)
from .failure_grouping import (
    FAILURE_GROUPING_RESOURCE,
    GroupingFixtureState,
    build_failure_grouping_fixture,
)
from .lineage import (
    LINEAGE_RESOURCE,
    LineageFixtureState,
    build_lineage_fixture,
    lineage_content_hash,
)

S4_RESOURCES = frozenset(
    {
        EVIDENCE_RESOURCE,
        LINEAGE_RESOURCE,
        EVIDENCE_COMPARISON_RESOURCE,
        FAILURE_GROUPING_RESOURCE,
    }
)

# Selector values introduced for S4.  Routes that do not own them receive the
# shared generic envelope for the state, so S1/S2/S3/S5 behavior is unchanged.
S4_FIXTURE_STATES = frozenset(
    {FixtureState.NOT_EVALUATED, FixtureState.CURSOR_EXPIRED, FixtureState.SNAPSHOT_DRIFT}
)

# The lineage ids a fixture ledger points at (see ``web/lineage.py`` fixtures).
LINEAGE_CONCLUSION_ID = "conclusion-1"
LINEAGE_EVIDENCE_ID = "evidence-1"
LINEAGE_ARTIFACT_ID = "artifact-1"
_PROTOCOL_RECORD_ID = "protocol-evidence-1"

_STALE_CAUSES: dict[FixtureState, tuple[str, str]] = {
    FixtureState.CURSOR_EXPIRED: (
        "cursor_expired",
        "The requested cursor expired; restart from the current snapshot.",
    ),
    FixtureState.SNAPSHOT_DRIFT: (
        "snapshot_drift",
        "The requested snapshot drifted from the snapshot that was read.",
    ),
}

_EVIDENCE: dict[FixtureState, EvidenceFixtureState] = {
    FixtureState.EMPTY: EvidenceFixtureState.EMPTY,
    FixtureState.COMPLETE: EvidenceFixtureState.COMPLETE,
    FixtureState.PARTIAL: EvidenceFixtureState.PARTIAL,
    FixtureState.BLOCKED: EvidenceFixtureState.BLOCKED,
    FixtureState.STALE: EvidenceFixtureState.STALE,
    FixtureState.INCOMPARABLE: EvidenceFixtureState.INCOMPARABLE,
    # A failed artifact hash is the Evidence seam's integrity failure, with its reason kept.
    FixtureState.INTEGRITY_FAILURE: EvidenceFixtureState.HASH_MISMATCH,
    FixtureState.API_UNAVAILABLE: EvidenceFixtureState.API_UNAVAILABLE,
    FixtureState.NOT_EVALUATED: EvidenceFixtureState.NOT_EVALUATED,
    FixtureState.CURSOR_EXPIRED: EvidenceFixtureState.STALE,
    FixtureState.SNAPSHOT_DRIFT: EvidenceFixtureState.STALE,
}

_COMPARISON: dict[FixtureState, EvidenceComparisonFixtureState] = {
    FixtureState.EMPTY: EvidenceComparisonFixtureState.MISSING,
    FixtureState.COMPLETE: EvidenceComparisonFixtureState.COMPLETE,
    FixtureState.PARTIAL: EvidenceComparisonFixtureState.PARTIAL,
    FixtureState.BLOCKED: EvidenceComparisonFixtureState.BLOCKED,
    FixtureState.STALE: EvidenceComparisonFixtureState.STALE,
    FixtureState.INCOMPARABLE: EvidenceComparisonFixtureState.INCOMPARABLE,
    FixtureState.INTEGRITY_FAILURE: EvidenceComparisonFixtureState.INTEGRITY_FAILURE,
    FixtureState.API_UNAVAILABLE: EvidenceComparisonFixtureState.API_UNAVAILABLE,
    FixtureState.NOT_EVALUATED: EvidenceComparisonFixtureState.MISSING,
    FixtureState.CURSOR_EXPIRED: EvidenceComparisonFixtureState.STALE,
    FixtureState.SNAPSHOT_DRIFT: EvidenceComparisonFixtureState.STALE,
}

_GROUPING: dict[FixtureState, GroupingFixtureState] = {
    FixtureState.EMPTY: GroupingFixtureState.MISSING,
    FixtureState.COMPLETE: GroupingFixtureState.COMPLETE,
    FixtureState.PARTIAL: GroupingFixtureState.PARTIAL,
    FixtureState.BLOCKED: GroupingFixtureState.BLOCKED,
    FixtureState.STALE: GroupingFixtureState.STALE,
    FixtureState.INCOMPARABLE: GroupingFixtureState.INCOMPARABLE,
    FixtureState.INTEGRITY_FAILURE: GroupingFixtureState.INTEGRITY_FAILURE,
    FixtureState.API_UNAVAILABLE: GroupingFixtureState.API_UNAVAILABLE,
    FixtureState.NOT_EVALUATED: GroupingFixtureState.COMPLETE,
    FixtureState.CURSOR_EXPIRED: GroupingFixtureState.STALE,
    FixtureState.SNAPSHOT_DRIFT: GroupingFixtureState.STALE,
}


def _mark_stale(model: ManagerReadModel, state: FixtureState) -> ManagerReadModel:
    """Replace a stale envelope's cause with an expired cursor or snapshot drift."""

    code, reason = _STALE_CAUSES[state]
    source_ref = model.source_refs[0].source_id if model.source_refs else None
    return replace(
        model,
        availability=Availability(status=ReadModelStatus.STALE, complete=False, reason=reason),
        errors=(ReadModelError(code=code, message=reason, source_ref=source_ref, retryable=True),),
    )


def _payload(model: ManagerReadModel) -> dict[str, Any] | None:
    data = copy.deepcopy(model.data)
    return cast(dict[str, Any], data) if isinstance(data, dict) else None


def _evidence(state: FixtureState) -> ManagerReadModel:
    model = build_evidence_fixture(_EVIDENCE[state])
    if state in _STALE_CAUSES:
        model = _mark_stale(model, state)
    if state is FixtureState.API_UNAVAILABLE:
        # An unavailable seam publishes nothing; never keep a conclusion beside it.
        return replace(model, data={})
    payload = _payload(model)
    if not payload:
        return model
    # Explicit pointers into the lineage seam; the candidate record deliberately has none.
    payload["conclusion_id"] = LINEAGE_CONCLUSION_ID
    for artifact in payload.get("artifacts", []):
        artifact["lineage_id"] = LINEAGE_ARTIFACT_ID
    for record in payload.get("records", []):
        if record.get("record_id") == _PROTOCOL_RECORD_ID:
            record["lineage_id"] = LINEAGE_EVIDENCE_ID
            for artifact in record.get("artifacts", []):
                artifact["lineage_id"] = LINEAGE_ARTIFACT_ID
    return replace(model, data=payload)


def _lineage_gate(
    model: ManagerReadModel, status: ReadModelStatus, reason: str, code: str | None = None
) -> ManagerReadModel:
    """A lineage seam that is blocked or incomparable publishes no graph at all."""

    errors = (ReadModelError(code=code, message=reason),) if code else ()
    return replace(
        model,
        data={},
        availability=Availability(status=status, complete=False, reason=reason),
        errors=errors,
    )


def _lineage(state: FixtureState) -> ManagerReadModel:
    complete = build_lineage_fixture(LineageFixtureState.COMPLETE)
    if state is FixtureState.COMPLETE:
        return complete
    if state is FixtureState.EMPTY:
        return build_lineage_fixture(LineageFixtureState.EMPTY)
    if state is FixtureState.PARTIAL:
        return build_lineage_fixture(LineageFixtureState.PARTIAL)
    if state is FixtureState.API_UNAVAILABLE:
        return build_lineage_fixture(LineageFixtureState.API_UNAVAILABLE)
    if state is FixtureState.CURSOR_EXPIRED:
        return build_lineage_fixture(LineageFixtureState.CURSOR_EXPIRED)
    if state is FixtureState.SNAPSHOT_DRIFT:
        # The page itself fails closed; the envelope states the same cause for the shell.
        return replace(
            build_lineage_fixture(LineageFixtureState.SNAPSHOT_DRIFT),
            availability=Availability(
                status=ReadModelStatus.STALE,
                complete=False,
                reason="The lineage page snapshot differs from the snapshot that was read.",
            ),
        )
    if state is FixtureState.INTEGRITY_FAILURE:
        return replace(
            build_lineage_fixture(LineageFixtureState.HASH_MISMATCH),
            availability=Availability(
                status=ReadModelStatus.INTEGRITY_FAILURE,
                complete=False,
                reason="A lineage record failed its declared hash check.",
            ),
        )
    if state is FixtureState.BLOCKED:
        return _lineage_gate(
            complete,
            ReadModelStatus.BLOCKED,
            "The approved lineage read seam is blocked.",
            "lineage_read_blocked",
        )
    if state is FixtureState.INCOMPARABLE:
        return _lineage_gate(
            complete,
            ReadModelStatus.INCOMPARABLE,
            "The lineage inputs belong to incompatible snapshots.",
            "lineage_incomparable",
        )
    if state is FixtureState.STALE:
        return replace(
            complete,
            availability=Availability(
                status=ReadModelStatus.STALE,
                complete=True,
                reason="The lineage page is retained as a stale historical projection.",
            ),
        )
    # NOT_EVALUATED: the graph is published, but its evidence nodes carry no evaluation yet.
    payload = _payload(complete)
    assert payload is not None  # the complete fixture always publishes a graph
    for node in payload["nodes"]:
        if node["record_type"] == "evidence":
            node["status"] = "not_evaluated"
    payload["content_hash"] = lineage_content_hash(payload["nodes"], payload["edges"])
    return replace(complete, data=payload)


def _comparison(state: FixtureState) -> ManagerReadModel:
    model = build_evidence_comparison_fixture(_COMPARISON[state])
    if state in _STALE_CAUSES:
        return _mark_stale(model, state)
    if state is FixtureState.INCOMPARABLE:
        # The shared status must say incomparable; the per-axis reasons stay on the page.
        reason = "The compared objects declare incompatible axes; they are not ranked."
        return replace(
            model,
            availability=Availability(
                status=ReadModelStatus.INCOMPARABLE, complete=False, reason=reason
            ),
            errors=(ReadModelError(code="comparison_axis_incompatible", message=reason),),
        )
    if state is FixtureState.NOT_EVALUATED:
        reason = "The object comparison has not been evaluated in this scope."
        return replace(
            model,
            availability=Availability(status=ReadModelStatus.KNOWN, complete=False, reason=reason),
            errors=(ReadModelError(code="not_evaluated", message=reason),),
        )
    return model


def _grouping(state: FixtureState) -> ManagerReadModel:
    model = build_failure_grouping_fixture(_GROUPING[state])
    if state in _STALE_CAUSES:
        return _mark_stale(model, state)
    if state is FixtureState.NOT_EVALUATED:
        # Derived through the explicit rule path: the not-evaluated record joins neither bucket.
        reason = "One record is not evaluated; it joins neither group and is not counted failed."
        return replace(
            model,
            data={
                "aggregation": {
                    "rule": "bucket explicit terminal outcome by outcome",
                    "input_scope": ["study-fixture-1", "runs:fixture-2026-Q3"],
                },
                "records": [
                    {"record_id": "run-success-1", "label": "Successful run", "outcome": "success"},
                    {"record_id": "run-failure-1", "label": "Failed run", "outcome": "failure"},
                    {
                        "record_id": "run-not-evaluated-1",
                        "label": "Not evaluated run",
                        "outcome": "not_evaluated",
                    },
                ],
            },
            availability=Availability(
                status=ReadModelStatus.DERIVED, complete=False, reason=reason
            ),
        )
    return model


_BUILDERS = {
    EVIDENCE_RESOURCE: _evidence,
    LINEAGE_RESOURCE: _lineage,
    EVIDENCE_COMPARISON_RESOURCE: _comparison,
    FAILURE_GROUPING_RESOURCE: _grouping,
}


def build_s4_fixture(resource: str, state: FixtureState | str) -> ManagerReadModel:
    """Build a fresh envelope for one S4 resource and shell fixture state."""

    try:
        builder = _BUILDERS[resource]
    except KeyError:
        raise ValueError(f"{resource!r} is not an S4 resource") from None
    return builder(FixtureState(state))


__all__ = [
    "LINEAGE_ARTIFACT_ID",
    "LINEAGE_CONCLUSION_ID",
    "LINEAGE_EVIDENCE_ID",
    "S4_FIXTURE_STATES",
    "S4_RESOURCES",
    "build_s4_fixture",
]
