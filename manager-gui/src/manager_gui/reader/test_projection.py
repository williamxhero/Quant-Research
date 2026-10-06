"""Focused Reader R1-T1 contract tests; no domain storage or writes are needed."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import FrozenInstanceError, replace

import pytest

from manager_gui.fixtures import build_fixture
from manager_gui.models import Derivation, ManagerReadModel, SourceReference
from manager_gui.reader import (
    ClaimKind,
    ProjectionMode,
    ReaderAvailability,
    ReaderAvailabilityStatus,
    ReaderClaim,
    ReaderProjection,
    ReaderSummary,
    SampleData,
    project_read_model,
)


def test_minimal_round_trip_retains_v0_and_exact_noncanonical_bytes() -> None:
    model = build_fixture("complete")
    raw = (model.to_json(indent=2) + "\n").encode("utf-8")
    projection = project_read_model(model, raw_bytes=raw)
    restored = ReaderProjection.from_json(projection.to_json())
    assert restored == projection
    assert restored.raw_source.raw_bytes == raw
    assert restored.to_dict()["data"] == model.data
    assert restored.sample_data is None
    assert restored.mode_reference(ProjectionMode.EXPERT).schema == model.schema
    assert restored.mode_reference(ProjectionMode.RAW).sha256 == projection.raw_source.sha256


def test_projection_detaches_input_data_and_export_copies() -> None:
    model = build_fixture("complete")
    projection = project_read_model(model)
    original = projection.to_json()
    data = model.data
    assert isinstance(data, dict)
    data["records"] = []
    exported = projection.to_dict()
    exported["data"] = {"edited": True}
    assert projection.to_json() == original
    assert isinstance(projection.data, Mapping)
    with pytest.raises(TypeError):
        projection.data["edited"] = True  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        projection.as_of = "changed"  # type: ignore[misc]


def test_owner_text_is_preserved_and_summary_references_typed_claim() -> None:
    model = build_fixture("complete")
    text = "  owner 原文 <b>& test</b>\n"
    claim = ReaderClaim(
        "owner-note",
        ClaimKind.OWNER_TEXT,
        model.source_refs,
        Derivation("direct", inputs=(model.source_refs[0].source_id,)),
        ReaderAvailability(ReaderAvailabilityStatus.KNOWN, True),
        text,
    )
    summary = ReaderSummary("reader.summary.source_note", (claim.claim_id,), {"count": 1})
    projection = project_read_model(model, claims=(claim,), summary=summary)
    restored = ReaderProjection.from_json(projection.to_json())
    assert restored.claims[0].value == text
    assert restored.claims[0].explanation_key == "reader.claim.owner_text"
    assert restored.summary == summary


@pytest.mark.parametrize("state", ["empty", "blocked", "incomparable", "api_unavailable"])
def test_missing_and_blocked_availability_never_infers_an_outcome(state: str) -> None:
    model = build_fixture(state)
    projection = project_read_model(model)
    assert projection.availability.status.value == model.availability.status.value
    assert projection.claims == ()
    assert projection.summary is None
    availability = json.dumps(projection.availability.to_dict())
    assert all(word not in availability for word in ('"success"', '"failure"', '"pass"', '"fail"'))


def test_real_owner_scope_rejects_inherited_sample_metadata() -> None:
    model = build_fixture("complete")
    source = SourceReference("real-record", "owner", "record", "https://owner.invalid/record/1")
    real = replace(
        model, source_refs=(source,), derivation=Derivation("direct", inputs=("real-record",))
    )
    projection = project_read_model(real)
    with pytest.raises(ValueError, match="cannot inherit sample"):
        replace(projection, sample_data=SampleData("complete", "atlas"))
    assert ManagerReadModel.from_json(projection.raw_source.raw_bytes.decode()) == real
