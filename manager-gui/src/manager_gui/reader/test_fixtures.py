"""Fixture/provider tests for Reader R1-T1 truth semantics."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from manager_gui.fixtures import FixtureState, build_fixture
from manager_gui.models import Derivation, SourceReference
from manager_gui.provider import public_provider_methods
from manager_gui.reader import (
    READER_FIXTURE_STATES,
    ClaimKind,
    ReaderAvailabilityStatus,
    ReaderFixtureProvider,
    ReaderFixtureState,
    ReaderProjection,
    V0ReaderProjectionProvider,
    build_reader_fixture,
    reader_fixture_provider,
)


EXPECTED_AVAILABILITY = {
    "empty": ReaderAvailabilityStatus.MISSING,
    "complete": ReaderAvailabilityStatus.KNOWN,
    "partial": ReaderAvailabilityStatus.KNOWN,
    "blocked": ReaderAvailabilityStatus.BLOCKED,
    "stale": ReaderAvailabilityStatus.STALE,
    "incomparable": ReaderAvailabilityStatus.INCOMPARABLE,
    "integrity_failure": ReaderAvailabilityStatus.INTEGRITY_FAILURE,
    "api_unavailable": ReaderAvailabilityStatus.API_UNAVAILABLE,
    "not_evaluated": ReaderAvailabilityStatus.NOT_EVALUATED,
    "cursor_expired": ReaderAvailabilityStatus.STALE,
    "snapshot_drift": ReaderAvailabilityStatus.STALE,
}


def test_reader_fixture_matrix_is_labeled_and_round_trips() -> None:
    assert set(READER_FIXTURE_STATES) == set(EXPECTED_AVAILABILITY)
    for state, availability in EXPECTED_AVAILABILITY.items():
        projection = build_reader_fixture(state)
        assert projection.sample_data is not None
        assert projection.sample_data.fixture_state == state
        assert projection.sample_data.banner_key == "reader.sample.banner"
        assert projection.availability.status is availability
        assert ReaderProjection.from_json(projection.to_json()) == projection
        assert json.dumps(projection.to_dict(), ensure_ascii=False)


def test_fixture_gaps_are_typed_and_neutral() -> None:
    for state in ("empty", "blocked", "not_evaluated", "api_unavailable", "stale"):
        projection = build_reader_fixture(state)
        gaps = projection.limitations + projection.unknowns
        assert gaps or state == "empty"
        for claim in gaps:
            assert claim.kind in {
                ClaimKind.MISSING, ClaimKind.BLOCKED, ClaimKind.STALE, ClaimKind.INCOMPARABLE,
            }
            assert claim.availability.status not in {
                ReaderAvailabilityStatus.KNOWN,
                ReaderAvailabilityStatus.DERIVED,
                ReaderAvailabilityStatus.INTERPRETED,
            }
        assert "success" not in projection.to_json().lower()
        assert '"failure"' not in projection.to_json().lower()


def test_partial_fixture_keeps_known_and_missing_separate() -> None:
    projection = build_reader_fixture("partial")
    assert any(claim.kind is ClaimKind.KNOWN for claim in projection.claims)
    assert all(claim.kind is ClaimKind.MISSING for claim in projection.limitations)
    assert projection.unknowns == ()


def test_fixture_provider_is_read_only_and_mode_is_reference_only() -> None:
    provider = reader_fixture_provider("complete")
    assert isinstance(provider, ReaderFixtureProvider)
    assert public_provider_methods(provider) == ("read",)
    reader = provider.read(mode="reader")
    expert = provider.read(mode="expert")
    raw = provider.read(mode="raw")
    assert reader == expert == raw
    assert reader.mode_reference("expert").schema == "manager-gui.manager-read-model.v0"
    assert reader.mode_reference("raw").sha256 == reader.raw_source.sha256
    with pytest.raises(ValueError, match="unknown Reader mode"):
        provider.read(mode="mutating")


def test_v0_adapter_never_inherits_sample_provenance() -> None:
    owner_model = build_fixture("complete")
    owner_ref = SourceReference(
        "owner-record", "owner-system", "public-record", "https://owner.invalid/record/1"
    )
    owner_model = replace(
        owner_model,
        source_refs=(owner_ref,),
        derivation=Derivation("direct", inputs=(owner_ref.source_id,), version="owner-v1"),
    )

    class OwnerProvider:
        def read(self, resource: str = "atlas", *, snapshot_token: str | None = None):
            del resource, snapshot_token
            return owner_model

    provider = V0ReaderProjectionProvider(OwnerProvider())
    projection = provider.read()
    assert projection.sample_data is None
    assert projection.raw_source.schema == "manager-gui.manager-read-model.v0"
    assert projection.mode_reference("raw").mode.value == "raw"
    assert projection.source_refs == (owner_ref,)
    assert projection.raw_source.raw_bytes == owner_model.to_json().encode("utf-8")


def test_fixture_source_is_unchanged_v0_and_no_mutation_methods_are_exposed() -> None:
    fixture = build_reader_fixture(ReaderFixtureState.COMPLETE)
    original = build_fixture(FixtureState.COMPLETE)
    assert fixture.to_dict()["data"] == original.data
    assert fixture.source_refs == original.source_refs
    assert fixture.raw_source.raw_bytes == original.to_json().encode("utf-8")
    assert public_provider_methods(reader_fixture_provider("blocked")) == ("read",)
