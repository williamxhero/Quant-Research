"""Focused, consumer-side tests for the Research Memory visibility gate."""

from __future__ import annotations

from copy import deepcopy

import pytest

from .core import AcceptanceFailure
from .research_visibility import (
    VISIBILITY_REQUEST_SCHEMA,
    evaluate_visibility_request,
    guard_visibility_delivery,
)


def _request(
    *,
    stage: str = "initial_read",
    mode: str = "strict",
    grants: list[dict[str, object]] | None = None,
    materials: list[dict[str, object]] | None = None,
    historical_context: dict[str, object] | None = None,
) -> dict[str, object]:
    scope = {
        "logical_dataset": "a0-holdout",
        "universe": ["asset-1"],
        "time_range": {"start": "2025-01-01", "end": "2025-12-31"},
        "sample_role": "protected-reference",
    }
    return {
        "schema": VISIBILITY_REQUEST_SCHEMA,
        "stage": stage,
        "mode": mode,
        "consumer": {
            "actor_id": "actor-a0",
            "consumer": "ranking-service",
            "action": "read",
            "purpose": "ranking",
            "capabilities": ["memory.read"],
            "authorization_policy_id": "auth-policy",
            "authorization_policy_version": "v1",
            "authorization_knowledge_cutoff": "2026-09-14T00:00:00Z",
            "grants": grants
            if grants is not None
            else [
                {
                    "logical_dataset": scope["logical_dataset"],
                    "universe": scope["universe"],
                    "time_range": scope["time_range"],
                    "sample_roles": [scope["sample_role"]],
                    "purposes": ["ranking"],
                }
            ],
        },
        "research_policy": {
            "policy_id": "research-policy",
            "policy_version": "v1",
            "knowledge_cutoff": "2026-09-13T00:00:00Z",
            "permitted_sample_roles": [scope["sample_role"]],
            "permitted_purposes": ["ranking"],
        },
        "materials": materials
        if materials is not None
        else [
            {
                **scope,
                "material_id": "finding-a0",
                "record_type": "finding",
                "derived_from": [],
                "allowed_purposes": ["ranking"],
                "required_capabilities": ["memory.read"],
                "content_digest": "sha256:" + "1" * 64,
                "display_name": "renamable display label",
                "campaign_id": "campaign-v1",
                "dataset_version": "dataset-v1",
            }
        ],
        "context_material_ids": ["finding-a0"],
        "historical_context": historical_context,
    }


@pytest.mark.parametrize(
    "stage",
    (
        "initial_read",
        "ranking",
        "embedding",
        "summary",
        "planning",
        "research_model",
        "final_envelope",
        "tool_return",
        "historical_redelivery",
    ),
)
def test_allowed_material_is_checked_at_every_delivery_stage(stage: str) -> None:
    decision = evaluate_visibility_request(_request(stage=stage))

    assert decision.status == "allowed"
    assert decision.deliverable is True
    assert decision.materials[0].status == "allowed"


def test_logical_scope_survives_renames_campaigns_and_dataset_versions() -> None:
    original = _request()
    renamed = deepcopy(original)
    renamed_material = renamed["materials"][0]  # type: ignore[index]
    assert isinstance(renamed_material, dict)
    renamed_material.update(
        {
            "display_name": "a completely different label",
            "campaign_id": "campaign-v2",
            "dataset_version": "dataset-v9",
        }
    )

    first = evaluate_visibility_request(original)
    second = evaluate_visibility_request(renamed)

    assert first.status == second.status == "allowed"
    assert first.request_identity == second.request_identity


def test_protected_lineage_is_denied_before_consumer_read() -> None:
    request = _request()
    material = request["materials"][0]  # type: ignore[index]
    assert isinstance(material, dict)
    material["derived_from"] = [
        {
            "material_id": "source-a0",
            "relationship": "derived-from",
            "logical_dataset": "a0-holdout",
            "universe": ["asset-2"],
            "time_range": {"start": "2025-01-01", "end": "2025-12-31"},
            "sample_role": "protected-reference",
        }
    ]
    reads: list[str] = []

    delivery = guard_visibility_delivery(request, lambda material_id: reads.append(material_id))

    assert delivery.decision.status == "restricted"
    assert delivery.payloads == ()
    assert reads == []
    assert delivery.decision.materials[0].safe_codes == ("lineage_current_authorization_denied",)


def test_missing_metadata_is_restricted_in_strict_and_unknown_in_audit() -> None:
    strict = _request()
    audit = _request(mode="audit")
    for request in (strict, audit):
        material = request["materials"][0]  # type: ignore[index]
        assert isinstance(material, dict)
        material.pop("time_range")

    strict_decision = evaluate_visibility_request(strict)
    audit_decision = evaluate_visibility_request(audit)

    assert strict_decision.status == "restricted"
    assert strict_decision.deliverable is False
    assert audit_decision.status == "unknown"
    assert audit_decision.deliverable is False
    assert audit_decision.current_access["status"] == "unknown"
    assert audit_decision.research_policy["status"] == "unknown"


def test_missing_protection_closure_fields_never_mean_an_empty_closure() -> None:
    strict = _request()
    audit = _request(mode="audit")
    for request in (strict, audit):
        material = request["materials"][0]  # type: ignore[index]
        assert isinstance(material, dict)
        material.pop("derived_from")
        material.pop("allowed_purposes")
        material.pop("required_capabilities")

    strict_decision = evaluate_visibility_request(strict)
    audit_decision = evaluate_visibility_request(audit)

    assert strict_decision.status == "restricted"
    assert audit_decision.status == "unknown"
    assert audit_decision.deliverable is False


def test_current_purpose_and_capability_denials_are_not_presented_as_allowed_access() -> None:
    purpose_denied = _request()
    purpose_consumer = purpose_denied["consumer"]
    assert isinstance(purpose_consumer, dict)
    purpose_consumer["purpose"] = "summary"

    capability_denied = _request()
    capability_consumer = capability_denied["consumer"]
    assert isinstance(capability_consumer, dict)
    capability_consumer["capabilities"] = []

    purpose_decision = evaluate_visibility_request(purpose_denied)
    capability_decision = evaluate_visibility_request(capability_denied)

    assert purpose_decision.status == "restricted"
    assert purpose_decision.current_access["status"] == "restricted"
    assert capability_decision.status == "restricted"
    assert capability_decision.current_access["status"] == "restricted"


def test_revoked_current_access_blocks_historical_redelivery_without_rewriting_context() -> None:
    historical_context = {
        "context_id": "context-a0",
        "original_actor_id": "actor-a0",
        "original_authorization_policy_id": "auth-policy",
        "original_decision": "allowed",
    }
    original = _request(
        stage="historical_redelivery",
        historical_context=historical_context,
    )
    revoked = deepcopy(original)
    consumer = revoked["consumer"]
    assert isinstance(consumer, dict)
    consumer["grants"] = []

    before = evaluate_visibility_request(original)
    after = evaluate_visibility_request(revoked)
    after_wire = after.as_dict()

    assert before.status == "allowed"
    assert after.status == "restricted"
    assert after.historical_context_digest == before.historical_context_digest
    assert after.current_access["status"] == "restricted"
    assert after_wire["historical_context_digest"] == before.historical_context_digest
    assert "actor-a0" not in repr(after_wire)
    assert "context-a0" not in repr(after_wire)


def test_guard_loads_only_after_an_allowed_decision() -> None:
    reads: list[str] = []
    delivery = guard_visibility_delivery(
        _request(),
        lambda material_id: reads.append(material_id) or {"payload": "test-only"},
    )

    assert delivery.payloads == (("finding-a0", {"payload": "test-only"}),)
    assert reads == ["finding-a0"]
    assert delivery.as_dict()["payload_count"] == 1


def test_parser_rejects_noncanonical_or_unknown_contract_input() -> None:
    unknown = _request()
    unknown["unexpected"] = True
    with pytest.raises(AcceptanceFailure):
        evaluate_visibility_request(unknown)

    noncanonical = _request()
    consumer = noncanonical["consumer"]
    assert isinstance(consumer, dict)
    consumer["capabilities"] = ["memory.read", "memory.read"]
    with pytest.raises(AcceptanceFailure):
        evaluate_visibility_request(noncanonical)


def test_denied_decision_wire_contract_contains_only_stable_safe_fields() -> None:
    request = _request()
    consumer = request["consumer"]
    assert isinstance(consumer, dict)
    consumer["purpose"] = "unapproved-purpose"
    decision = evaluate_visibility_request(request)
    wire = decision.as_dict()

    assert decision.status == "restricted"
    assert wire["schema"] == "quant-research.memory-visibility-decision.v1"
    assert "content_digest" not in repr(wire)
    assert "display_name" not in repr(wire)
    assert "unapproved-purpose" in repr(wire)
