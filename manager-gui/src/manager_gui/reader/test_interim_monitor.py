"""Fail-closed public seams for the interim forward monitor."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from manager_gui.reader import (
    INTERIM_MONITOR_ID,
    InterimMonitorAccessDenied,
    InterimMonitorContractError,
    InterimMonitorDescriptor,
    InterimMonitorExceptionRelation,
    InterimMonitorGuard,
    InterimMonitorPrimaryUseDenied,
    authorize_interim_access,
    read_interim_monitor_descriptor,
    read_interim_monitor_exception,
    validate_descriptor_publication,
    validate_exception_publication,
)


def test_descriptor_is_hash_bound_immutable_and_strictly_readable() -> None:
    descriptor = InterimMonitorDescriptor()
    assert descriptor.identity_sha256 == INTERIM_MONITOR_ID
    assert validate_descriptor_publication(descriptor.to_publication()) == descriptor
    with pytest.raises(FrozenInstanceError):
        descriptor.status = "changed"  # type: ignore[misc]

    tampered = descriptor.to_publication()
    tampered["payload"]["mode"] = "primary"  # type: ignore[index]
    with pytest.raises(ValueError, match=r"hash|identity"):
        validate_descriptor_publication(tampered)


def test_health_only_is_allowed_but_strategy_checkpoint_is_fail_closed_before_gate() -> None:
    authorize_interim_access("health_only", as_of="2026-10-15")
    relation = InterimMonitorExceptionRelation.create(
        owner_basis="owner_direct",
        approver="owner",
        basis_reference="#690-owner-approval",
    )
    with pytest.raises(InterimMonitorAccessDenied, match="date gate"):
        authorize_interim_access(
            "strategy_checkpoint",
            as_of="2026-12-31",
            exception=relation.to_publication(),
            data_complete=True,
        )


def test_post_gate_strategy_checkpoint_requires_published_exact_exception() -> None:
    with pytest.raises(InterimMonitorAccessDenied, match="exception"):
        authorize_interim_access("strategy_checkpoint", as_of="2027-01-01", data_complete=True)

    relation = InterimMonitorExceptionRelation.create(
        owner_basis="owner_direct",
        approver="owner",
        basis_reference="#690-owner-approval",
    )
    with pytest.raises(InterimMonitorAccessDenied, match="published"):
        authorize_interim_access(
            "strategy_checkpoint",
            as_of="2027-01-01",
            exception=relation,
            data_complete=True,
        )

    published = relation.to_publication()
    assert validate_exception_publication(published) == relation
    authorize_interim_access(
        "strategy_checkpoint",
        as_of="2027-01-01",
        exception=published,
        data_complete=True,
    )


class _ExactPublicReader:
    def __init__(self, records: dict[str, object]) -> None:
        self.records = records
        self.calls: list[str] = []
        self.list_called = False

    def get_record(self, record_id: str) -> object:
        self.calls.append(record_id)
        if record_id not in self.records:
            raise KeyError(record_id)
        return self.records[record_id]

    def list_records(self, **_: object) -> object:
        self.list_called = True
        raise AssertionError("readback must not select from a listing")


def test_readback_requires_exact_identity_and_never_selects_latest() -> None:
    descriptor = InterimMonitorDescriptor()
    relation = InterimMonitorExceptionRelation.create(
        owner_basis="owner_direct",
        approver="owner",
        basis_reference="#690-owner-approval",
    )
    reader = _ExactPublicReader(
        {
            INTERIM_MONITOR_ID: descriptor.to_publication(),
            relation.relation_id: relation.to_publication(),
        }
    )
    assert read_interim_monitor_descriptor(reader) == descriptor
    assert read_interim_monitor_exception(reader, relation.relation_id) == relation
    assert reader.calls == [INTERIM_MONITOR_ID, relation.relation_id]
    assert reader.list_called is False

    missing = _ExactPublicReader({})
    with pytest.raises(InterimMonitorContractError, match="unavailable"):
        read_interim_monitor_descriptor(missing)
    assert missing.list_called is False


def test_exception_lineage_and_primary_destinations_fail_closed() -> None:
    relation = InterimMonitorExceptionRelation.create(
        owner_basis="owner_direct",
        approver="owner",
        basis_reference="#690-owner-approval",
    )
    publication = relation.to_publication()
    publication["lineage"] = publication["lineage"][:-1]  # type: ignore[index]
    with pytest.raises(ValueError, match="lineage"):
        validate_exception_publication(publication)

    guard = InterimMonitorGuard()
    for destination in ("primary_matrix", "t2", "conclusion"):
        with pytest.raises(InterimMonitorPrimaryUseDenied):
            guard.assert_non_primary_use(destination)
