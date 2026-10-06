"""Deterministic Reader fixtures with explicit sample provenance."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import cast

from manager_gui.fixtures import FixtureState, build_fixture
from manager_gui.models import Derivation, ManagerReadModel

from .models import (
    READER_PROJECTION_VERSION,
    ClaimKind,
    FrozenJSON,
    ReaderAvailability,
    ReaderAvailabilityStatus,
    ReaderClaim,
    ReaderProjection,
    SampleData,
    project_read_model,
)


class ReaderFixtureState(StrEnum):
    EMPTY = "empty"
    COMPLETE = "complete"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    STALE = "stale"
    INCOMPARABLE = "incomparable"
    INTEGRITY_FAILURE = "integrity_failure"
    API_UNAVAILABLE = "api_unavailable"
    NOT_EVALUATED = "not_evaluated"
    CURSOR_EXPIRED = "cursor_expired"
    SNAPSHOT_DRIFT = "snapshot_drift"


READER_FIXTURE_STATES = tuple(state.value for state in ReaderFixtureState)


def _claim(
    model: ManagerReadModel,
    claim_id: str,
    kind: ClaimKind,
    status: ReaderAvailabilityStatus,
    *,
    complete: bool = False,
    value: object = None,
    rule: str | None = None,
) -> ReaderClaim | None:
    if not model.source_refs:
        return None
    source_ids = tuple(source.source_id for source in model.source_refs)
    derivation_kind = {
        ClaimKind.KNOWN: "direct",
        ClaimKind.OWNER_TEXT: "direct",
        ClaimKind.DERIVED: "derived",
        ClaimKind.INTERPRETED: "interpreted",
    }.get(kind, "direct")
    derivation = Derivation(
        derivation_kind,
        rule if derivation_kind != "direct" else None,
        source_ids,
        READER_PROJECTION_VERSION if derivation_kind != "direct" else "v0",
    )
    return ReaderClaim(
        claim_id,
        kind,
        tuple(model.source_refs),
        derivation,
        ReaderAvailability(status, complete, model.availability.reason),
        cast(FrozenJSON, value),
    )


def _projection_claims(
    model: ManagerReadModel,
    state: ReaderFixtureState,
) -> tuple[tuple[ReaderClaim, ...], tuple[ReaderClaim, ...], tuple[ReaderClaim, ...]]:
    if state in {ReaderFixtureState.COMPLETE, ReaderFixtureState.PARTIAL}:
        known = _claim(
            model,
            "fixture-source-records",
            ClaimKind.KNOWN,
            ReaderAvailabilityStatus.KNOWN,
            complete=model.availability.complete,
            value={
                "resource": "fixture",
                "source_ids": [ref.source_id for ref in model.source_refs],
            },
        )
        records = model.data.get("records") if isinstance(model.data, dict) else None
        derived = _claim(
            model,
            "fixture-record-count",
            ClaimKind.DERIVED,
            ReaderAvailabilityStatus.DERIVED,
            complete=True,
            value=len(records) if isinstance(records, list) else 0,
            rule="reader.fixture.record-count",
        )
        interpreted = _claim(
            model,
            "fixture-source-interpretation",
            ClaimKind.INTERPRETED,
            ReaderAvailabilityStatus.INTERPRETED,
            complete=True,
            value="fixture-source-published-interpretation",
            rule="reader.fixture.interpretation",
        )
        unknown = _claim(
            model,
            "fixture-scope-unknown",
            ClaimKind.MISSING,
            ReaderAvailabilityStatus.MISSING,
            value=None,
        )
        claims: tuple[ReaderClaim, ...] = tuple(
            item for item in (known, derived, interpreted) if item is not None
        )
        limitations: tuple[ReaderClaim, ...] = ()
        unknowns: tuple[ReaderClaim, ...] = tuple(item for item in (unknown,) if item is not None)
        if state is ReaderFixtureState.PARTIAL:
            limitation = _claim(
                model,
                "fixture-record-types-out-of-scope",
                ClaimKind.MISSING,
                ReaderAvailabilityStatus.MISSING,
            )
            limitations = tuple(item for item in (limitation,) if item is not None)
            unknowns = ()
        return claims, limitations, unknowns

    status = ReaderAvailabilityStatus(model.availability.status.value)
    if state is ReaderFixtureState.NOT_EVALUATED:
        status = ReaderAvailabilityStatus.NOT_EVALUATED
    if state in {
        ReaderFixtureState.EMPTY,
        ReaderFixtureState.API_UNAVAILABLE,
        ReaderFixtureState.NOT_EVALUATED,
    }:
        kind = ClaimKind.MISSING
        target = "unknowns"
    elif state is ReaderFixtureState.BLOCKED or state is ReaderFixtureState.INTEGRITY_FAILURE:
        kind = ClaimKind.BLOCKED
        target = "limitations"
    elif state in {
        ReaderFixtureState.STALE,
        ReaderFixtureState.CURSOR_EXPIRED,
        ReaderFixtureState.SNAPSHOT_DRIFT,
    }:
        kind = ClaimKind.STALE
        target = "limitations"
    else:
        kind = ClaimKind.INCOMPARABLE
        target = "limitations"
    gap = _claim(model, f"fixture-{kind.value.lower()}-scope", kind, status)
    if gap is None:
        return (), (), ()
    return (
        ((gap,), (), ())
        if target == "claims"
        else (((), (gap,), ()) if target == "limitations" else ((), (), (gap,)))
    )


def build_reader_fixture(
    state: ReaderFixtureState | FixtureState | str,
    *,
    resource: str = "atlas",
) -> ReaderProjection:
    """Build one fresh, labeled sample projection without consulting owner storage."""

    selected = ReaderFixtureState(state)
    model = build_fixture(FixtureState(selected), resource=resource)
    claims, limitations, unknowns = _projection_claims(model, selected)
    projection = project_read_model(
        model,
        claims=claims,
        limitations=limitations,
        unknowns=unknowns,
    )
    return replace(
        projection,
        sample_data=SampleData(selected.value, resource),
    )


@dataclass(frozen=True, slots=True)
class ReaderFixtureProvider:
    """A read-only provider that returns explicitly labeled sample projections."""

    state: ReaderFixtureState

    def __init__(self, state: ReaderFixtureState | FixtureState | str) -> None:
        object.__setattr__(self, "state", ReaderFixtureState(state))

    def read(
        self,
        resource: str = "atlas",
        *,
        snapshot_token: str | None = None,
        mode: str = "reader",
    ) -> ReaderProjection:
        del snapshot_token
        if mode not in {"reader", "expert", "raw"}:
            raise ValueError(f"unknown Reader mode: {mode!r}")
        return build_reader_fixture(self.state, resource=resource)


def reader_fixture_provider(
    state: ReaderFixtureState | FixtureState | str,
) -> ReaderFixtureProvider:
    return ReaderFixtureProvider(state)


__all__ = [
    "READER_FIXTURE_STATES",
    "ReaderFixtureProvider",
    "ReaderFixtureState",
    "build_reader_fixture",
    "reader_fixture_provider",
]
