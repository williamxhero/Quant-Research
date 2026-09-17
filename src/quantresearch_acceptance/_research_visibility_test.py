"""Focused, consumer-side tests for the Research Memory visibility gate."""

from __future__ import annotations

from copy import deepcopy

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from .core import AcceptanceFailure
from .research_visibility import (
    DEFAULT_PROTECTION_CLOSURE_BUDGET,
    VISIBILITY_REQUEST_SCHEMA,
    evaluate_visibility_request,
    guard_visibility_delivery,
)

_PROTECTED_SCOPE: dict[str, object] = {
    "logical_dataset": "a0-holdout",
    "universe": ["asset-protected"],
    "time_range": {"start": "2025-01-01", "end": "2025-12-31"},
    "sample_role": "protected-reference",
}


def _request(
    *,
    stage: str = "initial_read",
    mode: str = "strict",
    grants: list[dict[str, object]] | None = None,
    materials: list[dict[str, object]] | None = None,
    historical_context: dict[str, object] | None = None,
    context_material_ids: list[str] | None = None,
    closure_budget: int | None = None,
) -> dict[str, object]:
    scope = {
        "logical_dataset": "a0-holdout",
        "universe": ["asset-1"],
        "time_range": {"start": "2025-01-01", "end": "2025-12-31"},
        "sample_role": "protected-reference",
    }
    request: dict[str, object] = {
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
        "context_material_ids": (
            context_material_ids
            if context_material_ids is not None
            else [material["material_id"] for material in (materials or [])] or ["finding-a0"]
        ),
        "historical_context": historical_context,
    }
    if closure_budget is not None:
        request["closure_budget"] = closure_budget
    return request


def _chain(length: int, *, protected_tail: bool = True) -> list[dict[str, object]]:
    """A0 test-only derivation chain: node 0 is derived from node 1, and so on."""

    open_scope: dict[str, object] = {
        "logical_dataset": "a0-holdout",
        "universe": ["asset-1"],
        "time_range": {"start": "2025-01-01", "end": "2025-12-31"},
        "sample_role": "protected-reference",
    }
    materials: list[dict[str, object]] = []
    for index in range(length):
        last = index == length - 1
        scope = deepcopy(
            _PROTECTED_SCOPE if (last and protected_tail) else open_scope  # type: ignore[arg-type]
        )
        materials.append(
            {
                **scope,
                "material_id": f"node-{index}",
                "record_type": "parameter-suggestion" if index else "finding",
                "derived_from": (
                    []
                    if last
                    else [
                        {
                            **deepcopy(open_scope),
                            "material_id": f"node-{index + 1}",
                            "relationship": "derived-from",
                        }
                    ]
                ),
                "allowed_purposes": ["ranking"],
                "required_capabilities": ["memory.read"],
            }
        )
    return materials


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
    assert delivery.delivery_status == "delivered"
    assert delivery.as_dict()["payload_count"] == 1


def test_restricted_output_cannot_reveal_material_ids_counts_or_lineage() -> None:
    request = _request()
    material = request["materials"][0]  # type: ignore[index]
    assert isinstance(material, dict)
    material["material_id"] = "protected-finding-77"
    material["record_type"] = "protected-result"
    material["derived_from"] = [
        {
            "material_id": "protected-source-88",
            "relationship": "derived-from",
            "logical_dataset": "a0-holdout",
            "universe": ["asset-2"],
            "time_range": {"start": "2025-01-01", "end": "2025-12-31"},
            "sample_role": "protected-reference",
        }
    ]
    consumer = request["consumer"]
    assert isinstance(consumer, dict)
    consumer["grants"] = []

    delivery = guard_visibility_delivery(request, lambda _material_id: pytest.fail("must not load"))
    wire = delivery.as_dict()

    assert delivery.delivery_status == "restricted"
    assert delivery.payloads == ()
    assert wire["decision"]["delivery"] == "blocked"
    assert "materials" not in wire["decision"]
    assert "payload_count" not in wire
    assert "material_ids" not in wire
    assert "protected-finding-77" not in repr(wire)
    assert "protected-source-88" not in repr(wire)
    assert "protected-result" not in repr(wire)


def test_loader_failure_has_a_safe_public_result() -> None:
    def failing_loader(_material_id: str) -> object:
        raise RuntimeError("secret source body and provider debug details")

    delivery = guard_visibility_delivery(_request(stage="final_envelope"), failing_loader)
    wire = delivery.as_dict()

    assert delivery.decision.status == "allowed"
    assert delivery.delivery_status == "unavailable"
    assert delivery.payloads == ()
    assert "payload_count" not in wire
    assert "material_ids" not in wire
    assert "secret source body" not in repr(wire)
    assert "provider debug" not in repr(wire)


def test_multi_hop_derivation_cannot_launder_a_protected_source() -> None:
    decision = evaluate_visibility_request(_request(materials=_chain(3)))
    root = decision.materials[0]

    assert root.material_id == "node-0"
    assert root.status == "restricted"
    assert root.safe_codes == ("lineage_current_authorization_denied",)
    assert decision.status == "restricted"


def test_renaming_a_multi_hop_chain_does_not_lift_protection() -> None:
    original = _request(materials=_chain(3))
    renamed = _request(materials=_chain(3))
    for index, material in enumerate(renamed["materials"]):  # type: ignore[arg-type]
        assert isinstance(material, dict)
        material["display_name"] = f"a fresh label {index}"
        material["campaign_id"] = "campaign-v9"
        material["dataset_version"] = "dataset-v9"

    first = evaluate_visibility_request(original)
    second = evaluate_visibility_request(renamed)

    assert first.status == second.status == "restricted"
    assert first.materials[0].closure_digest == second.materials[0].closure_digest


def test_exhausted_traversal_budget_is_refused_not_downgraded_to_optional() -> None:
    materials = _chain(4, protected_tail=False)
    strict = evaluate_visibility_request(_request(materials=materials, closure_budget=1))
    audit = evaluate_visibility_request(
        _request(materials=materials, mode="audit", closure_budget=1)
    )

    assert evaluate_visibility_request(_request(materials=materials)).status == "allowed"
    assert strict.status == "restricted"
    assert strict.materials[0].safe_codes == ("closure_budget_exhausted",)
    assert audit.status == "unknown"
    assert audit.deliverable is False


@pytest.mark.parametrize(
    "record_type",
    ("parameter-suggestion", "component-rationale", "report-summary", "chart-projection"),
)
@pytest.mark.parametrize(
    "stage",
    ("initial_read", "ranking", "embedding", "summary", "research_model", "final_envelope"),
)
def test_a0_p01_derived_artifacts_are_blocked_before_any_consumer_read(
    record_type: str, stage: str
) -> None:
    """A0-P01 on test-only records: a derived artifact of a protected result."""

    materials = _chain(3)
    head = materials[0]
    assert isinstance(head, dict)
    head["record_type"] = record_type
    head["display_name"] = "renamed away from the protected source"
    head["campaign_id"] = "campaign-v2"
    head["dataset_version"] = "dataset-v9"
    reads: list[str] = []

    delivery = guard_visibility_delivery(
        _request(stage=stage, materials=materials),
        lambda material_id: reads.append(material_id),
    )
    wire = delivery.as_dict()

    assert reads == []
    assert delivery.payloads == ()
    assert delivery.delivery_status == "restricted"
    assert delivery.decision.materials[0].safe_codes == ("lineage_current_authorization_denied",)
    assert "payload_count" not in wire
    assert "materials" not in wire["decision"]  # type: ignore[operator]
    assert "asset-protected" not in repr(wire)
    assert record_type not in repr(wire)


def test_a_missing_closure_endpoint_is_never_read_as_unprotected() -> None:
    materials = _chain(3, protected_tail=False)
    tail = materials[-1]
    assert isinstance(tail, dict)
    tail.pop("time_range")

    strict = evaluate_visibility_request(_request(materials=materials))
    audit = evaluate_visibility_request(_request(materials=materials, mode="audit"))

    assert strict.materials[0].safe_codes == ("closure_incomplete",)
    assert strict.status == "restricted"
    assert audit.status == "unknown"
    assert audit.deliverable is False


def test_a_cyclic_derivation_graph_fails_closed_in_every_mode() -> None:
    materials = _chain(3, protected_tail=False)
    tail = materials[-1]
    assert isinstance(tail, dict)
    tail["derived_from"] = [
        {
            "logical_dataset": "a0-holdout",
            "universe": ["asset-1"],
            "time_range": {"start": "2025-01-01", "end": "2025-12-31"},
            "sample_role": "protected-reference",
            "material_id": "node-0",
            "relationship": "derived-from",
        }
    ]

    for mode in ("strict", "audit"):
        decision = evaluate_visibility_request(_request(materials=materials, mode=mode))
        assert decision.status == "restricted"
        assert "closure_not_acyclic" in decision.materials[0].safe_codes


def test_envelope_additions_are_blocked_and_get_a_safety_audit_status() -> None:
    materials = _chain(2, protected_tail=False)
    protected = deepcopy(materials[0])
    assert isinstance(protected, dict)
    protected.update(deepcopy(_PROTECTED_SCOPE))
    protected["material_id"] = "envelope-addition"
    protected["derived_from"] = []
    reads: list[str] = []

    context_only = evaluate_visibility_request(
        _request(stage="final_envelope", materials=materials)
    )
    delivery = guard_visibility_delivery(
        _request(
            stage="final_envelope",
            materials=[*materials, protected],
            context_material_ids=[str(item["material_id"]) for item in materials],
        ),
        lambda material_id: reads.append(material_id),
    )

    assert context_only.status == "allowed"
    assert context_only.safety_audit == {
        "stage": "final_envelope",
        "scope": "context_only",
        "status": "clear",
    }
    assert delivery.decision.status == "restricted"
    assert delivery.delivery_status == "restricted"
    assert reads == []
    assert delivery.decision.safety_audit == {
        "stage": "final_envelope",
        "scope": "envelope_addition",
        "status": "blocked",
    }
    assert delivery.as_dict()["decision"]["safety_audit"]["status"] == "blocked"  # type: ignore[index]


def test_tool_return_additions_are_audited_and_earlier_stages_are_not() -> None:
    materials = _chain(2, protected_tail=False)
    added = deepcopy(materials[0])
    assert isinstance(added, dict)
    added["material_id"] = "tool-return-addition"
    added["derived_from"] = []
    context_ids = [str(item["material_id"]) for item in materials]

    tool_return = evaluate_visibility_request(
        _request(
            stage="tool_return",
            materials=[*materials, added],
            context_material_ids=context_ids,
        )
    )
    ranking = evaluate_visibility_request(
        _request(
            stage="ranking",
            materials=[*materials, added],
            context_material_ids=context_ids,
        )
    )

    assert tool_return.status == "allowed"
    assert tool_return.safety_audit == {
        "stage": "tool_return",
        "scope": "envelope_addition",
        "status": "clear",
    }
    assert ranking.safety_audit["status"] == "not_applicable"


def test_a_restricted_delivery_does_not_mutate_the_submitted_context() -> None:
    request = _request(stage="historical_redelivery", materials=_chain(3))
    before = deepcopy(request)

    delivery = guard_visibility_delivery(request, lambda _id: pytest.fail("must not load"))

    assert delivery.delivery_status == "restricted"
    assert request == before


def test_parser_rejects_an_out_of_range_traversal_budget() -> None:
    for budget in (0, -1, 10**6):
        with pytest.raises(AcceptanceFailure):
            evaluate_visibility_request(_request(closure_budget=budget))
    bad = _request()
    bad["closure_budget"] = True
    with pytest.raises(AcceptanceFailure):
        evaluate_visibility_request(bad)


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


_settings = settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


@_settings
@given(length=st.integers(min_value=2, max_value=8))
def test_property_every_hop_of_a_chain_keeps_the_tail_protected(length: int) -> None:
    decision = evaluate_visibility_request(_request(materials=_chain(length)))

    assert decision.status == "restricted"
    assert decision.deliverable is False
    for material in decision.materials:
        assert material.status == "restricted"


@_settings
@given(
    length=st.integers(min_value=2, max_value=6),
    repeats=st.integers(min_value=2, max_value=4),
)
def test_property_duplicate_edges_and_nodes_do_not_change_a_decision(
    length: int, repeats: int
) -> None:
    plain = _chain(length)
    duplicated = _chain(length)
    for material in duplicated:
        edges = material["derived_from"]
        assert isinstance(edges, list)
        material["derived_from"] = [deepcopy(edge) for edge in edges for _ in range(repeats)]

    first = evaluate_visibility_request(_request(materials=plain))
    second = evaluate_visibility_request(_request(materials=duplicated))

    assert first.status == second.status
    assert [item.status for item in first.materials] == [item.status for item in second.materials]
    assert [item.closure_digest for item in first.materials] == [
        item.closure_digest for item in second.materials
    ]


@_settings
@given(
    length=st.integers(min_value=2, max_value=6),
    campaign=st.text(alphabet="abcdef-", min_size=1, max_size=12),
    version=st.text(alphabet="abcdef-", min_size=1, max_size=12),
)
def test_property_renaming_never_lifts_protection(length: int, campaign: str, version: str) -> None:
    renamed = _chain(length)
    for material in renamed:
        material["display_name"] = f"label {campaign}"
        material["campaign_id"] = campaign
        material["dataset_version"] = version

    baseline = evaluate_visibility_request(_request(materials=_chain(length)))
    decision = evaluate_visibility_request(_request(materials=renamed))

    assert decision.status == baseline.status == "restricted"
    assert [item.closure_digest for item in decision.materials] == [
        item.closure_digest for item in baseline.materials
    ]


@_settings
@given(
    length=st.integers(min_value=2, max_value=6),
    dropped=st.sampled_from(["time_range", "universe", "sample_role", "logical_dataset"]),
    hop=st.integers(min_value=0, max_value=5),
    mode=st.sampled_from(["strict", "audit"]),
)
def test_property_a_missing_closure_endpoint_is_never_deliverable(
    length: int, dropped: str, hop: int, mode: str
) -> None:
    materials = _chain(length, protected_tail=False)
    target = materials[hop % length]
    assert isinstance(target, dict)
    target.pop(dropped)

    decision = evaluate_visibility_request(_request(materials=materials, mode=mode))

    assert decision.deliverable is False
    assert decision.status in {"restricted", "unknown"}


@_settings
@given(length=st.integers(min_value=2, max_value=8), slack=st.integers(min_value=0, max_value=3))
def test_property_the_traversal_budget_boundary_fails_closed(length: int, slack: int) -> None:
    materials = _chain(length, protected_tail=False)
    edges = length - 1

    if edges:
        short = evaluate_visibility_request(
            _request(materials=materials, closure_budget=edges - 1 if edges > 1 else 1)
        )
        if edges > 1:
            assert short.deliverable is False
            assert "closure_budget_exhausted" in short.materials[0].safe_codes
    exact = evaluate_visibility_request(
        _request(materials=materials, closure_budget=max(edges, 1) + slack)
    )

    assert exact.status == "allowed"
    assert all("closure_budget_exhausted" not in item.safe_codes for item in exact.materials)
    assert edges <= DEFAULT_PROTECTION_CLOSURE_BUDGET


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
