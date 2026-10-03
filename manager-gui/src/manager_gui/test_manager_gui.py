"""S1-T1 smoke tests for the ManagerReadModel and provider boundary."""

from __future__ import annotations

import json

from manager_gui import (
    FIXTURE_STATES,
    FORBIDDEN_PROVIDER_METHODS,
    MANAGER_READ_MODEL_JSON_SCHEMA,
    MANAGER_READ_MODEL_SCHEMA,
    STATUS_SEMANTICS,
    FixtureProvider,
    FixtureState,
    ManagerDataProvider,
    ManagerReadModel,
    ReadModelStatus,
    fixture_provider,
    public_provider_methods,
)


def test_read_model_serializes_round_trips_and_preserves_provenance() -> None:
    model = fixture_provider(FixtureState.PARTIAL).read("atlas")

    wire = json.loads(model.to_json())
    restored = ManagerReadModel.from_dict(wire)

    assert wire["schema"] == MANAGER_READ_MODEL_SCHEMA
    assert set(wire) == {
        "schema",
        "data",
        "source_refs",
        "as_of",
        "snapshot_token",
        "derivation",
        "availability",
        "errors",
    }
    assert restored == model
    assert restored.source_refs[0].owner == "strategy-workspace"
    assert restored.errors[0].source_ref == restored.source_refs[0].source_id


def test_fixtures_cover_every_first_slice_availability_state() -> None:
    expected = {
        "empty": ReadModelStatus.MISSING,
        "complete": ReadModelStatus.KNOWN,
        "partial": ReadModelStatus.KNOWN,
        "blocked": ReadModelStatus.BLOCKED,
        "stale": ReadModelStatus.STALE,
        "incomparable": ReadModelStatus.INCOMPARABLE,
        "integrity_failure": ReadModelStatus.INTEGRITY_FAILURE,
        "api_unavailable": ReadModelStatus.API_UNAVAILABLE,
    }

    assert set(FIXTURE_STATES) == set(expected)
    for state, status in expected.items():
        model = fixture_provider(state).read()
        assert model.availability.status is status
        availability = model.to_dict()["availability"]
        assert isinstance(availability, dict)
        assert availability["status"] == status.value
        assert STATUS_SEMANTICS[status]


def test_provider_is_read_only_and_has_no_mutation_shape() -> None:
    provider = FixtureProvider("partial")

    assert isinstance(provider, ManagerDataProvider)
    assert public_provider_methods(provider) == ("read",)
    assert public_provider_methods(ManagerDataProvider) == ("read",)
    assert not FORBIDDEN_PROVIDER_METHODS.intersection(public_provider_methods(provider))
    assert provider.read().availability.status is ReadModelStatus.KNOWN


def test_machine_schema_declares_v0_envelope_and_statuses() -> None:
    assert MANAGER_READ_MODEL_JSON_SCHEMA["$id"] == MANAGER_READ_MODEL_SCHEMA
    assert MANAGER_READ_MODEL_JSON_SCHEMA["required"] == [
        "schema",
        "data",
        "source_refs",
        "as_of",
        "snapshot_token",
        "derivation",
        "availability",
        "errors",
    ]
    properties = MANAGER_READ_MODEL_JSON_SCHEMA["properties"]
    assert isinstance(properties, dict)
    availability = properties["availability"]
    assert isinstance(availability, dict)
    availability_properties = availability["properties"]
    assert isinstance(availability_properties, dict)
    status_schema = availability_properties["status"]
    assert isinstance(status_schema, dict)
    assert set(status.value for status in ReadModelStatus) == set(status_schema["enum"])


def test_fixture_provider_has_no_private_storage_dependency() -> None:
    source = fixture_provider("api_unavailable").read()

    assert source.availability.status is ReadModelStatus.API_UNAVAILABLE
    assert "sqlite" not in source.to_json().lower()
    assert all("private" not in ref.locator for ref in source.source_refs)
