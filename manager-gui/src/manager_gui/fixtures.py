"""Deterministic, synthetic fixtures for every first-slice availability state.

Fixtures are structural test data only.  They never read the workspace, Apex,
Runtime, Reporting, or any private SQLite/database path.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from .models import (
    Availability,
    Derivation,
    JSONValue,
    ManagerReadModel,
    ReadModelError,
    ReadModelStatus,
    SourceReference,
)


class FixtureState(StrEnum):
    EMPTY = "empty"
    COMPLETE = "complete"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    STALE = "stale"
    INCOMPARABLE = "incomparable"
    INTEGRITY_FAILURE = "integrity_failure"
    API_UNAVAILABLE = "api_unavailable"


FIXTURE_STATES = tuple(state.value for state in FixtureState)


def _source(
    source_id: str,
    *,
    owner: str = "fixture-owner",
    kind: str = "public-read-model",
    locator: str = "fixture://manager-gui/atlas",
    schema: str = "fixture.manager-gui.v0",
    revision: str = "fixture-v0",
) -> SourceReference:
    return SourceReference(
        source_id=source_id,
        owner=owner,
        kind=kind,
        locator=locator,
        schema=schema,
        revision=revision,
    )


def build_fixture(state: FixtureState | str, *, resource: str = "atlas") -> ManagerReadModel:
    """Build a fresh fixture envelope for ``state`` and ``resource``."""

    try:
        selected = FixtureState(state)
    except ValueError as exc:
        raise ValueError(f"unknown Manager GUI fixture state: {state!r}") from exc
    if not resource.strip():
        raise ValueError("resource must be a non-empty string")

    if selected is FixtureState.EMPTY:
        return ManagerReadModel(
            data={},
            source_refs=(),
            as_of=None,
            snapshot_token=None,
            derivation=Derivation(kind="direct", version="v0"),
            availability=Availability(
                status=ReadModelStatus.MISSING,
                complete=False,
                reason="No records are present in the requested fixture scope.",
            ),
        )

    if selected is FixtureState.COMPLETE:
        source = _source(
            "fixture-workspace-campaigns",
            owner="strategy-workspace",
            kind="public-record",
            locator=f"fixture://strategy-workspace/{resource}/campaigns",
        )
        if resource == "stories":
            return ManagerReadModel(
                data={
                    "campaign": {"id": "campaign-fixture-1", "title": "Fixture campaign"},
                    "study": {"id": "study-fixture-1", "title": "Fixture study"},
                    "strategy_family": {
                        "id": "family-fixture-1",
                        "title": "Fixture strategy family",
                    },
                    "chapters": {
                        "intent": [
                            {
                                "record_id": "intent-fixture-1",
                                "title": "Why test the fixture strategy?",
                                "summary": "Validate the complete fixture-backed research path.",
                                "source_ref": source.source_id,
                                "known_at": "2026-10-03T08:00:00Z",
                            }
                        ],
                        "initial_hypothesis": [
                            {
                                "record_id": "hypothesis-fixture-1",
                                "summary": "The fixture path is traceable end to end.",
                                "outcome": "success",
                                "source_ref": source.source_id,
                            }
                        ],
                        "research_design": [
                            {
                                "record_id": "design-fixture-1",
                                "title": "Frozen fixture design",
                                "summary": "Use only the declared public read seam.",
                            }
                        ],
                        "attempts": [
                            {
                                "record_id": "run-fixture-1",
                                "title": "Fixture run",
                                "summary": "The fixture run completed with explicit provenance.",
                                "outcome": "success",
                                "source_ref": source.source_id,
                                "source_event_time": "2026-10-03T08:30:00Z",
                                "system_known_at": "2026-10-03T08:31:00Z",
                            }
                        ],
                        "evidence": [
                            {
                                "record_id": "evidence-fixture-1",
                                "title": "Fixture evidence",
                                "summary": "The source reference is available for inspection.",
                                "source_ref": source.source_id,
                            }
                        ],
                        "conclusions": [
                            {
                                "record_id": "decision-fixture-1",
                                "title": "Fixture decision",
                                "summary": "Keep the read-only path as the integration contract.",
                                "outcome": "success",
                                "source_ref": source.source_id,
                            }
                        ],
                        "failures": [],
                        "follow_up": [],
                    },
                },
                source_refs=(source,),
                as_of="2026-10-03T09:00:00Z",
                snapshot_token="fixture-complete-v0",
                derivation=Derivation(kind="direct", inputs=(source.source_id,), version="v0"),
                availability=Availability(
                    status=ReadModelStatus.KNOWN,
                    complete=True,
                    reason="The complete fixture contains the declared integration path.",
                ),
            )
        return ManagerReadModel(
            data={
                "records": [
                    {
                        "id": "campaign-fixture-1",
                        "record_type": "campaign",
                        "title": "Fixture campaign",
                        "state": "active",
                        "changed_at": "2026-10-03T08:00:00Z",
                        "source": source.source_id,
                    },
                    {
                        "id": "hypothesis-fixture-1",
                        "record_type": "hypothesis",
                        "title": "Fixture hypothesis",
                        "state": "open",
                        "changed_at": "2026-10-03T08:05:00Z",
                        "source": source.source_id,
                        "conclusion_state": "unresolved",
                    },
                    {
                        "id": "candidate-fixture-1",
                        "record_type": "candidate",
                        "title": "Fixture candidate",
                        "state": "ready",
                        "changed_at": "2026-10-03T08:10:00Z",
                        "source": source.source_id,
                        "frontier": True,
                    },
                    {
                        "id": "run-fixture-1",
                        "record_type": "run",
                        "title": "Fixture run",
                        "state": "completed",
                        "changed_at": "2026-10-03T08:30:00Z",
                        "source": source.source_id,
                    },
                    {"id": "evidence-fixture-1", "record_type": "evidence", "state": "recorded"},
                    {
                        "id": "qualification-fixture-1",
                        "record_type": "qualification",
                        "state": "pending",
                    },
                    {
                        "id": "replication-fixture-1",
                        "record_type": "replication",
                        "state": "planned",
                    },
                    {
                        "id": "revalidation-fixture-1",
                        "record_type": "revalidation",
                        "state": "planned",
                    },
                ]
            },
            source_refs=(source,),
            as_of="2026-10-03T09:00:00Z",
            snapshot_token="fixture-complete-v0",
            derivation=Derivation(kind="direct", inputs=(source.source_id,), version="v0"),
            availability=Availability(
                status=ReadModelStatus.KNOWN,
                complete=True,
                reason="The complete fixture contains the declared lifecycle records.",
            ),
        )

    if selected is FixtureState.PARTIAL:
        source = _source(
            "fixture-workspace-campaigns",
            owner="strategy-workspace",
            kind="public-record",
            locator=f"fixture://strategy-workspace/{resource}/campaigns",
        )
        partial_data: dict[str, object]
        if resource == "stories":
            partial_data = {
                "campaign": {"id": "campaign-fixture-1", "title": "Fixture campaign"},
                "chapters": {
                    "intent": [
                        {
                            "record_id": "intent-fixture-1",
                            "title": "Partial fixture story",
                            "summary": (
                                "The campaign is available, but other story "
                                "chapters are not in scope."
                            ),
                            "source_ref": source.source_id,
                        }
                    ]
                },
            }
        else:
            partial_data = {
                "campaigns": [
                    {
                        "id": "campaign-fixture-1",
                        "title": "Fixture campaign",
                        "source": source.source_id,
                    }
                ],
                "runs": [],
            }
        return ManagerReadModel(
            data=cast(JSONValue, partial_data),
            source_refs=(source,),
            as_of="2026-10-03T00:00:00Z",
            snapshot_token="fixture-partial-v0",
            derivation=Derivation(kind="direct", inputs=(source.source_id,), version="v0"),
            availability=Availability(
                status=ReadModelStatus.KNOWN,
                complete=False,
                reason="Campaign records are available; other record types are not in scope.",
            ),
            errors=(
                ReadModelError(
                    code="record_type_missing",
                    message="The fixture intentionally omits some expected record types.",
                    source_ref=source.source_id,
                ),
            ),
        )

    if selected is FixtureState.BLOCKED:
        source = _source("fixture-blocked-source")
        return ManagerReadModel(
            data={},
            source_refs=(source,),
            as_of=None,
            snapshot_token="fixture-blocked-v0",
            derivation=Derivation(kind="direct", inputs=(source.source_id,), version="v0"),
            availability=Availability(
                status=ReadModelStatus.BLOCKED,
                complete=False,
                reason="The approved read seam is blocked by a policy or capability gate.",
            ),
            errors=(
                ReadModelError(
                    code="read_blocked",
                    message="The fixture does not permit access to this resource.",
                    source_ref=source.source_id,
                    details={"mutation_attempted": False},
                ),
            ),
        )

    if selected is FixtureState.STALE:
        source = _source(
            "fixture-stale-report", owner="strategy-reporting", kind="published-report"
        )
        return ManagerReadModel(
            data={"headline": "Historical fixture result"},
            source_refs=(source,),
            as_of="2025-01-01T00:00:00Z",
            snapshot_token="fixture-stale-v0",
            derivation=Derivation(kind="direct", inputs=(source.source_id,), version="v0"),
            availability=Availability(
                status=ReadModelStatus.STALE,
                complete=True,
                reason="The source predates the current package or policy identity.",
            ),
            errors=(
                ReadModelError(
                    code="source_stale",
                    message="The fixture is retained for historical viewing, not current truth.",
                    source_ref=source.source_id,
                ),
            ),
        )

    if selected is FixtureState.INCOMPARABLE:
        left = _source("fixture-comparison-left")
        right = _source("fixture-comparison-right", revision="fixture-v1")
        return ManagerReadModel(
            data={
                "left": {"id": "method-a", "metric": 1.0},
                "right": {"id": "method-b"},
                "incomparable_axes": ["data_snapshot"],
            },
            source_refs=(left, right),
            as_of="2026-10-03T00:00:00Z",
            snapshot_token="fixture-incomparable-v0",
            derivation=Derivation(
                kind="derived",
                rule="manager-gui.comparison.v0",
                inputs=(left.source_id, right.source_id),
                version="v0",
            ),
            availability=Availability(
                status=ReadModelStatus.INCOMPARABLE,
                complete=False,
                reason="The comparison axes do not share a compatible data snapshot.",
            ),
            errors=(
                ReadModelError(
                    code="comparison_axis_incompatible",
                    message="A result must not be ranked across incompatible snapshots.",
                    details={"axis": "data_snapshot"},
                ),
            ),
        )

    if selected is FixtureState.INTEGRITY_FAILURE:
        source = _source("fixture-integrity-artifact", kind="artifact")
        return ManagerReadModel(
            data={},
            source_refs=(source,),
            as_of="2026-10-03T00:00:00Z",
            snapshot_token="fixture-integrity-v0",
            derivation=Derivation(kind="direct", inputs=(source.source_id,), version="v0"),
            availability=Availability(
                status=ReadModelStatus.INTEGRITY_FAILURE,
                complete=False,
                reason="The fixture artifact failed its declared integrity check.",
            ),
            errors=(
                ReadModelError(
                    code="artifact_digest_mismatch",
                    message="The source digest does not match the declared digest.",
                    source_ref=source.source_id,
                    details={
                        "expected": "sha256:fixture-expected",
                        "observed": "sha256:fixture-observed",
                    },
                ),
            ),
        )

    source = _source("fixture-public-api")
    return ManagerReadModel(
        data={},
        source_refs=(source,),
        as_of=None,
        snapshot_token=None,
        derivation=Derivation(kind="direct", inputs=(source.source_id,), version="v0"),
        availability=Availability(
            status=ReadModelStatus.API_UNAVAILABLE,
            complete=False,
            reason="The approved public read API is not available in this environment.",
            retryable=True,
        ),
        errors=(
            ReadModelError(
                code="public_api_unavailable",
                message="No private-storage fallback is permitted for this read.",
                source_ref=source.source_id,
                retryable=True,
            ),
        ),
    )


@dataclass(frozen=True, slots=True)
class FixtureProvider:
    """A read-only provider returning one deterministic fixture state."""

    state: FixtureState

    def __init__(self, state: FixtureState | str) -> None:
        object.__setattr__(self, "state", FixtureState(state))

    def read(
        self,
        resource: str = "atlas",
        *,
        snapshot_token: str | None = None,
    ) -> ManagerReadModel:
        del snapshot_token  # Fixtures intentionally do not emulate a mutable backend.
        return build_fixture(self.state, resource=resource)


def fixture_provider(state: FixtureState | str) -> FixtureProvider:
    """Return a provider suitable for a page or smoke test."""

    return FixtureProvider(state)


__all__ = [
    "FIXTURE_STATES",
    "FixtureProvider",
    "FixtureState",
    "build_fixture",
    "fixture_provider",
]
