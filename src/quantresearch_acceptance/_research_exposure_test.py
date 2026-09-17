"""Consumer-side tests for the immutable Research Exposure lifecycle."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from hypothesis import HealthCheck, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from .core import AcceptanceFailure
from .research_exposure import (
    EXPOSURE_EVENT_SCHEMA,
    ExposureLog,
    ExposurePersistenceFailure,
    replay_exposure_delivery,
)
from .research_visibility import VISIBILITY_REQUEST_SCHEMA

_CONTEXT_IDENTITY = "sha256:" + "a" * 64
_ENVELOPE_DIGEST = "sha256:" + "b" * 64
_OTHER_ENVELOPE_DIGEST = "sha256:" + "c" * 64


def _key(
    *,
    campaign_id: str = "campaign-a0",
    iteration_id: str = "iteration-2",
    idempotency_key: str = "idem-1",
) -> dict[str, str]:
    return {
        "campaign_id": campaign_id,
        "iteration_id": iteration_id,
        "consumer": "research-model",
        "action": "final_request",
        "idempotency_key": idempotency_key,
    }


def _event(
    event_type: str,
    *,
    key: dict[str, str] | None = None,
    research_action_id: str = "research-action-1",
    context_identity: str = _CONTEXT_IDENTITY,
    invocation_id: str = "invocation-1",
    family_id: str = "family-momentum",
    delivery: dict[str, object] | None = None,
    uncertainty: dict[str, object] | None = None,
    completion: dict[str, object] | None = None,
    visibility_request: dict[str, object] | None = None,
) -> dict[str, object]:
    event: dict[str, object] = {
        "schema": EXPOSURE_EVENT_SCHEMA,
        "event_type": event_type,
        "key": key if key is not None else _key(),
        "research_action_id": research_action_id,
        "context_identity": context_identity,
        "research_family": {
            "family_id": family_id,
            "test_family": "test-family-momentum",
            "prior_result_ids": ["prior-result-1"],
        },
        "policy": {
            "policy_id": "auth-policy",
            "policy_version": "v1",
            "knowledge_cutoff": "2026-09-14T00:00:00Z",
        },
        "invocation_id": invocation_id,
    }
    if event_type == "context_prepared":
        event["context_material_ids"] = ["context-material-1"]
    if delivery is not None:
        event["delivery"] = delivery
    if uncertainty is not None:
        event["uncertainty"] = uncertainty
    if completion is not None:
        event["completion"] = completion
    if visibility_request is not None:
        event["visibility_request"] = visibility_request
    return event


def _delivery(
    *,
    envelope_digest: str = _ENVELOPE_DIGEST,
    content_ref: str | None = "approved-store:envelope-1",
    receipt_ref: str | None = "receipt-1",
    response_ref: str | None = "response-1",
    added: list[str] | None = None,
    coverage: str = "full",
    provider_request_id: str = "provider-request-1",
    template_version: str = "template-v3",
    tool_input_version: str = "tool-input-v2",
) -> dict[str, object]:
    return {
        "envelope_digest": envelope_digest,
        "envelope_content_ref": content_ref,
        "provider_request_id": provider_request_id,
        "template_version": template_version,
        "tool_input_version": tool_input_version,
        "receipt_ref": receipt_ref,
        "response_ref": response_ref,
        "added_material_ids": added if added is not None else [],
        "replay_coverage": coverage,
    }


def _uncertainty(
    *,
    reason: str = "receipt_lost",
    observation: str = "local_checkpoint",
    transport: str = "real_process",
) -> dict[str, object]:
    return {"reason": reason, "observation": observation, "transport": transport}


def _completion(
    *,
    result_ref: str = "completion-result-1",
    candidates: list[str] | None = None,
    decisions: list[str] | None = None,
    confirmed_by: str = "real_receipt",
) -> dict[str, object]:
    return {
        "result_ref": result_ref,
        "candidate_ids": candidates if candidates is not None else ["candidate-1"],
        "selection_decision_ids": decisions if decisions is not None else ["selection-1"],
        "confirmed_by": confirmed_by,
    }


def _visibility_request(
    *,
    material_id: str = "added-material-1",
    sample_role: str = "exploration",
    stage: str = "final_envelope",
) -> dict[str, object]:
    scope: dict[str, object] = {
        "logical_dataset": "a0-exploration",
        "universe": ["asset-1"],
        "time_range": {"start": "2025-01-01", "end": "2025-12-31"},
        "sample_role": sample_role,
    }
    return {
        "schema": VISIBILITY_REQUEST_SCHEMA,
        "stage": stage,
        "mode": "strict",
        "consumer": {
            "actor_id": "actor-a0",
            "consumer": "research-model",
            "action": "final_request",
            "purpose": "research",
            "capabilities": ["memory.read"],
            "authorization_policy_id": "auth-policy",
            "authorization_policy_version": "v1",
            "authorization_knowledge_cutoff": "2026-09-14T00:00:00Z",
            "grants": [
                {
                    "logical_dataset": "a0-exploration",
                    "universe": ["asset-1"],
                    "time_range": {"start": "2025-01-01", "end": "2025-12-31"},
                    "sample_roles": ["exploration"],
                    "purposes": ["research"],
                }
            ],
        },
        "research_policy": {
            "policy_id": "research-policy",
            "policy_version": "v1",
            "knowledge_cutoff": "2026-09-14T00:00:00Z",
            "permitted_sample_roles": ["exploration"],
            "permitted_purposes": ["research"],
        },
        "materials": [
            {
                "material_id": material_id,
                "record_type": "research-note",
                **scope,
                "derived_from": [],
                "allowed_purposes": ["research"],
                "required_capabilities": ["memory.read"],
                "content_digest": "sha256:" + "d" * 64,
            }
        ],
        "context_material_ids": [],
    }


def _prepared_log() -> tuple[ExposureLog, str]:
    log = ExposureLog()
    event = log.append(_event("context_prepared"))
    return log, event.action_key


# --- criterion 1: canonical readback of all four states ----------------------


def test_all_four_states_have_canonical_readback_with_full_linkage() -> None:
    log, action_key = _prepared_log()
    assert log.state(action_key) == "prepared"
    assert log.readback(action_key)["state"] == "prepared"

    log.append(_event("delivery_uncertain", uncertainty=_uncertainty()))
    assert log.state(action_key) == "delivery_uncertain"

    log.append(
        _event(
            "envelope_delivered",
            invocation_id="invocation-2",
            delivery=_delivery(receipt_ref="receipt-public-1"),
        )
    )
    assert log.state(action_key) == "delivered"

    log.append(_event("completion_linked", invocation_id="invocation-2", completion=_completion()))
    readback = log.readback(action_key)
    assert readback["state"] == "completed"
    assert readback["state_trajectory"] == [
        "context_prepared",
        "delivery_uncertain",
        "envelope_delivered",
        "completion_linked",
    ]
    assert readback["key"]["campaign_id"] == "campaign-a0"
    assert readback["key"]["iteration_id"] == "iteration-2"
    assert readback["key"]["consumer"] == "research-model"
    assert readback["key"]["action"] == "final_request"
    assert readback["context_identity"] == _CONTEXT_IDENTITY
    assert readback["research_family"]["family_id"] == "family-momentum"
    assert readback["research_family"]["test_family"] == "test-family-momentum"
    assert readback["policy"]["policy_id"] == "auth-policy"
    assert readback["invocation_count"] == 2
    assert readback["invocations"] == ["invocation-1", "invocation-2"]
    assert readback["delivery_confirmed_by"] == "real_receipt"
    assert readback["grants_eligibility"] is False


def test_readback_of_an_unknown_action_is_empty_not_an_error() -> None:
    log = ExposureLog()
    readback = log.readback("sha256:" + "f" * 64)
    assert readback["state"] is None
    assert readback["events"] == []


# --- criterion 2: envelope differs from Context ------------------------------


def test_envelope_additions_are_traceable_with_versions_and_references() -> None:
    log, action_key = _prepared_log()
    log.append(
        _event(
            "envelope_delivered",
            invocation_id="invocation-2",
            delivery=_delivery(added=["added-material-1"]),
            visibility_request=_visibility_request(),
        )
    )
    delivered = next(
        event for event in log.events(action_key) if event.event_type == "envelope_delivered"
    )
    assert delivered.delivery is not None
    # The Context draft identity and the delivered envelope are bound separately.
    assert delivered.context_identity == _CONTEXT_IDENTITY
    assert delivered.delivery.envelope_digest == _ENVELOPE_DIGEST
    assert delivered.delivery.added_material_ids == ("added-material-1",)
    assert delivered.delivery.provider_request_id == "provider-request-1"
    assert delivered.delivery.template_version == "template-v3"
    assert delivered.delivery.tool_input_version == "tool-input-v2"
    assert delivered.delivery.receipt_ref == "receipt-1"
    assert delivered.delivery.response_ref == "response-1"
    assert delivered.gate_identity is not None


def test_a_tool_turn_delivery_links_to_the_same_research_action() -> None:
    log, first_key = _prepared_log()
    log.append(_event("envelope_delivered", delivery=_delivery()))
    tool_key = _key(idempotency_key="idem-tool-turn-1")
    log.append(_event("context_prepared", key=tool_key, invocation_id="invocation-3"))
    log.append(
        _event(
            "envelope_delivered",
            key=tool_key,
            invocation_id="invocation-3",
            delivery=_delivery(
                envelope_digest=_OTHER_ENVELOPE_DIGEST,
                content_ref="approved-store:envelope-2",
                receipt_ref="receipt-2",
                added=["added-material-1"],
                tool_input_version="tool-input-v3",
            ),
            visibility_request=_visibility_request(stage="tool_return"),
        )
    )
    grouped = log.research_action_readback("research-action-1")
    assert len(grouped["actions"]) == 2
    keys = {action["action_key"] for action in grouped["actions"]}
    assert first_key in keys
    # The tool turn is its own exposure action, not an overwrite of the draft.
    assert len(keys) == 2
    assert {action["state"] for action in grouped["actions"]} == {"delivered"}


def test_added_material_blocked_by_the_visibility_gate_is_never_recorded_as_delivered() -> None:
    log, action_key = _prepared_log()
    blocked = _visibility_request(sample_role="protected-reference")
    with pytest.raises(AcceptanceFailure):
        log.append(
            _event(
                "envelope_delivered",
                delivery=_delivery(added=["added-material-1"]),
                visibility_request=blocked,
            )
        )
    assert log.state(action_key) == "prepared"


def test_added_material_without_a_visibility_request_is_refused() -> None:
    log, action_key = _prepared_log()
    with pytest.raises(AcceptanceFailure):
        log.append(_event("envelope_delivered", delivery=_delivery(added=["added-material-1"])))
    assert log.state(action_key) == "prepared"


def test_an_ungated_addition_cannot_ride_along_with_a_gated_one() -> None:
    log, _action_key = _prepared_log()
    with pytest.raises(AcceptanceFailure):
        log.append(
            _event(
                "envelope_delivered",
                delivery=_delivery(added=["added-material-1", "smuggled-material"]),
                visibility_request=_visibility_request(),
            )
        )


# --- criterion 3: conservative uncertainty -----------------------------------


def test_uncertain_delivery_never_claims_non_exposure_and_forbids_blind_resend() -> None:
    log, action_key = _prepared_log()
    log.append(_event("delivery_uncertain", uncertainty=_uncertainty(reason="request_timeout")))
    readback = log.readback(action_key)
    assert readback["state"] == "delivery_uncertain"
    assert readback["resend_allowed"] is False
    assert log.context_exposure(_CONTEXT_IDENTITY) == "uncertain"
    # A local checkpoint or timeout is not evidence the consumer missed it.
    assert readback["uncertainty"]["observation"] == "local_checkpoint"


def test_reconciling_an_uncertain_delivery_requires_a_real_receipt() -> None:
    log, action_key = _prepared_log()
    log.append(_event("delivery_uncertain", uncertainty=_uncertainty()))
    with pytest.raises(AcceptanceFailure):
        log.append(_event("envelope_delivered", delivery=_delivery(receipt_ref=None)))
    assert log.state(action_key) == "delivery_uncertain"
    log.append(_event("envelope_delivered", delivery=_delivery(receipt_ref="receipt-public-1")))
    assert log.state(action_key) == "delivered"


def test_a_new_campaign_does_not_restore_unseen_for_an_exposed_context() -> None:
    log, _action_key = _prepared_log()
    log.append(_event("envelope_delivered", delivery=_delivery()))
    assert log.context_exposure(_CONTEXT_IDENTITY) == "exposed"
    log.append(
        _event(
            "context_prepared",
            key=_key(campaign_id="campaign-b0", idempotency_key="idem-2"),
            research_action_id="research-action-2",
        )
    )
    assert log.context_exposure(_CONTEXT_IDENTITY) == "exposed"


def test_a_confirmed_delivery_cannot_be_returned_to_uncertain() -> None:
    log, action_key = _prepared_log()
    log.append(_event("envelope_delivered", delivery=_delivery()))
    with pytest.raises(AcceptanceFailure):
        log.append(_event("delivery_uncertain", uncertainty=_uncertainty()))
    assert log.state(action_key) == "delivered"


def test_an_out_of_order_event_is_refused() -> None:
    log = ExposureLog()
    with pytest.raises(AcceptanceFailure):
        log.append(_event("envelope_delivered", delivery=_delivery()))
    with pytest.raises(AcceptanceFailure):
        log.append(_event("completion_linked", completion=_completion()))


# --- criterion 4: idempotency ------------------------------------------------


def test_the_same_key_and_the_same_input_recovers_the_existing_event() -> None:
    log, action_key = _prepared_log()
    first = log.append(_event("envelope_delivered", delivery=_delivery()))
    duplicate = log.append(_event("envelope_delivered", delivery=_delivery()))
    assert duplicate is first
    assert len(log.events(action_key)) == 2
    assert log.readback(action_key)["state_trajectory"].count("envelope_delivered") == 1


def test_the_same_key_with_a_different_input_is_refused_not_merged() -> None:
    log, action_key = _prepared_log()
    log.append(_event("envelope_delivered", delivery=_delivery()))
    with pytest.raises(AcceptanceFailure):
        log.append(
            _event(
                "envelope_delivered",
                delivery=_delivery(envelope_digest=_OTHER_ENVELOPE_DIGEST),
            )
        )
    delivered = next(
        event for event in log.events(action_key) if event.event_type == "envelope_delivered"
    )
    assert delivered.delivery is not None
    assert delivered.delivery.envelope_digest == _ENVELOPE_DIGEST


def test_a_new_research_intent_is_not_treated_as_a_retry_of_an_old_request() -> None:
    log, first_key = _prepared_log()
    log.append(_event("envelope_delivered", delivery=_delivery()))
    fresh = log.append(
        _event(
            "context_prepared",
            key=_key(idempotency_key="idem-fresh-intent"),
            research_action_id="research-action-9",
            context_identity="sha256:" + "e" * 64,
            family_id="family-reversal",
        )
    )
    assert fresh.action_key != first_key
    assert log.state(fresh.action_key) == "prepared"
    assert log.state(first_key) == "delivered"


def test_an_action_binding_cannot_drift_between_events() -> None:
    log, action_key = _prepared_log()
    with pytest.raises(AcceptanceFailure):
        log.append(
            _event(
                "envelope_delivered",
                context_identity="sha256:" + "e" * 64,
                delivery=_delivery(),
            )
        )
    assert log.state(action_key) == "prepared"


def test_one_research_action_cannot_carry_two_context_identities() -> None:
    log, _action_key = _prepared_log()
    with pytest.raises(AcceptanceFailure):
        log.append(
            _event(
                "context_prepared",
                key=_key(idempotency_key="idem-other"),
                context_identity="sha256:" + "e" * 64,
            )
        )


# --- criterion 5: interruption and persistence failure -----------------------


def test_a_torn_tail_leaves_a_prepared_action_uncertain_not_unseen(tmp_path: Path) -> None:
    path = tmp_path / "exposure.jsonl"
    log = ExposureLog(_file_sink(path))
    prepared = log.append(_event("context_prepared"))
    # A real interruption: the process died part-way through the next append.
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write('{"schema":"quant-research.research-exposure-event.v1","event_ty')
    recovered = ExposureLog.load(path)
    assert recovered.torn_tail is True
    assert recovered.state(prepared.action_key) == "delivery_uncertain"
    assert recovered.context_exposure(_CONTEXT_IDENTITY) == "uncertain"
    readback = recovered.readback(prepared.action_key)
    assert readback["uncertainty"]["reason"] == "process_interrupted"
    assert readback["resend_allowed"] is False


def test_a_clean_reload_preserves_every_public_fact(tmp_path: Path) -> None:
    path = tmp_path / "exposure.jsonl"
    log = ExposureLog(_file_sink(path))
    prepared = log.append(_event("context_prepared"))
    log.append(_event("envelope_delivered", delivery=_delivery()))
    log.append(_event("completion_linked", completion=_completion()))
    recovered = ExposureLog.load(path)
    assert recovered.torn_tail is False
    assert recovered.readback(prepared.action_key) == log.readback(prepared.action_key)


def test_a_persistence_failure_leaves_the_exposure_uncertain(tmp_path: Path) -> None:
    path = tmp_path / "exposure.jsonl"
    sink = _file_sink(path)
    failing = {"armed": False}

    def guarded(event: dict[str, object]) -> None:
        if failing["armed"]:
            raise OSError("disk full")
        sink(event)

    log = ExposureLog(guarded)
    prepared = log.append(_event("context_prepared"))
    failing["armed"] = True
    with pytest.raises(ExposurePersistenceFailure):
        log.append(_event("envelope_delivered", delivery=_delivery()))
    # The external fact may well have happened; "unseen" would be a lie.
    assert log.state(prepared.action_key) == "delivery_uncertain"
    readback = log.readback(prepared.action_key)
    assert readback["uncertainty"]["reason"] == "persistence_failure"
    assert readback["state_trajectory"] == ["context_prepared", "delivery_uncertain"]
    assert any(event["persisted"] is False for event in readback["events"])


def test_a_persistence_failure_never_downgrades_an_already_delivered_action(
    tmp_path: Path,
) -> None:
    path = tmp_path / "exposure.jsonl"
    sink = _file_sink(path)
    failing = {"armed": False}

    def guarded(event: dict[str, object]) -> None:
        if failing["armed"]:
            raise OSError("disk full")
        sink(event)

    log = ExposureLog(guarded)
    prepared = log.append(_event("context_prepared"))
    log.append(_event("envelope_delivered", delivery=_delivery()))
    failing["armed"] = True
    with pytest.raises(ExposurePersistenceFailure):
        log.append(_event("completion_linked", completion=_completion()))
    assert log.state(prepared.action_key) == "delivered"


def _file_sink(path: Path):
    def sink(event: dict[str, object]) -> None:
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")

    return sink


# --- criterion 6: replay coverage and leak prevention ------------------------


def test_replay_coverage_cannot_be_full_without_a_stored_envelope() -> None:
    log, _action_key = _prepared_log()
    with pytest.raises(AcceptanceFailure):
        log.append(
            _event("envelope_delivered", delivery=_delivery(content_ref=None, coverage="full"))
        )


def test_a_missing_payload_yields_only_a_limited_reconstruction() -> None:
    log, action_key = _prepared_log()
    log.append(
        _event("envelope_delivered", delivery=_delivery(content_ref=None, coverage="limited"))
    )
    calls: list[str] = []
    replay, payload = replay_exposure_delivery(
        log,
        action_key,
        _visibility_request(),
        lambda reference: calls.append(reference),
    )
    assert replay.reconstruction == "limited"
    assert replay.declared_coverage == "limited"
    assert replay.payload_present is False
    assert payload is None
    # The digest is an identity, never a body: nothing is re-fetched or re-invoked.
    assert calls == []


def test_full_coverage_replays_from_the_approved_store_only() -> None:
    log, action_key = _prepared_log()
    log.append(_event("envelope_delivered", delivery=_delivery()))
    replay, payload = replay_exposure_delivery(
        log,
        action_key,
        _visibility_request(),
        lambda reference: {"reference": reference},
    )
    assert replay.reconstruction == "full"
    assert replay.payload_present is True
    assert payload == {"reference": "approved-store:envelope-1"}


def test_the_event_record_cannot_carry_secrets_or_free_text() -> None:
    log, _action_key = _prepared_log()
    for extra in ({"api_key": "sk-secret"}, {"prompt_text": "protected body"}):
        event = _event("envelope_delivered", delivery=_delivery())
        event.update(extra)
        with pytest.raises(AcceptanceFailure):
            log.append(event)


def test_the_persisted_log_never_contains_protected_body_text(tmp_path: Path) -> None:
    path = tmp_path / "exposure.jsonl"
    log = ExposureLog(_file_sink(path))
    log.append(_event("context_prepared"))
    log.append(_event("envelope_delivered", delivery=_delivery()))
    log.append(_event("completion_linked", completion=_completion()))
    body = path.read_text(encoding="utf-8")
    for forbidden in ("sk-", "secret", "protected body", "BEGIN PRIVATE KEY"):
        assert forbidden not in body
    assert "approved-store:envelope-1" in body


# --- criterion 7: current authorization governs historical redelivery --------


def test_a_currently_unauthorized_party_cannot_replay_historical_content() -> None:
    log, action_key = _prepared_log()
    log.append(_event("envelope_delivered", delivery=_delivery()))
    before = deepcopy(log.export())
    revoked = _visibility_request()
    consumer = revoked["consumer"]
    assert isinstance(consumer, dict)
    consumer["grants"] = []
    calls: list[str] = []
    replay, payload = replay_exposure_delivery(
        log,
        action_key,
        revoked,
        lambda reference: calls.append(reference),
    )
    assert replay.reconstruction == "denied"
    assert replay.payload_present is False
    assert replay.context_identity is None
    assert payload is None
    assert calls == []
    # The historical events and the Context identity are untouched.
    assert log.export() == before
    assert log.readback(action_key)["context_identity"] == _CONTEXT_IDENTITY


def test_usage_history_publishes_relations_without_granting_eligibility() -> None:
    log, _action_key = _prepared_log()
    log.append(_event("envelope_delivered", delivery=_delivery()))
    log.append(
        _event(
            "completion_linked",
            completion=_completion(candidates=["candidate-7"], decisions=["selection-stop-1"]),
        )
    )
    history = log.usage_history(family_id="family-momentum")
    assert history["grants_eligibility"] is False
    entry = history["entries"][0]
    assert entry["candidate_ids"] == ["candidate-7"]
    assert entry["selection_decision_ids"] == ["selection-stop-1"]
    assert entry["research_family"]["test_family"] == "test-family-momentum"
    assert entry["context_identity"] == _CONTEXT_IDENTITY
    assert log.usage_history(family_id="family-absent")["entries"] == []


def test_usage_history_is_not_cleared_by_a_later_campaign() -> None:
    log, _action_key = _prepared_log()
    log.append(_event("envelope_delivered", delivery=_delivery()))
    log.append(_event("completion_linked", completion=_completion()))
    log.append(
        _event(
            "context_prepared",
            key=_key(campaign_id="campaign-b0", idempotency_key="idem-b0"),
            research_action_id="research-action-2",
        )
    )
    history = log.usage_history(context_identity=_CONTEXT_IDENTITY)
    campaigns = {entry["campaign_id"] for entry in history["entries"]}
    assert campaigns == {"campaign-a0", "campaign-b0"}
    assert any(entry["candidate_ids"] == ["candidate-1"] for entry in history["entries"])


# --- A0-P02 / A0-M03 / A0-R01 reference slice --------------------------------


def test_a0_p02_second_round_envelope_differs_from_context_and_loses_its_receipt(
    tmp_path: Path,
) -> None:
    """A0-P02 on #437-shaped controlled-delivery fixtures, not a real model run."""

    path = tmp_path / "a0-round-2.jsonl"
    log = ExposureLog(_file_sink(path))
    prepared = log.append(_event("context_prepared"))
    # Round two adds material the Context draft never carried; it is gated first.
    log.append(
        _event(
            "envelope_delivered",
            invocation_id="invocation-round-2",
            delivery=_delivery(
                added=["added-material-1"],
                content_ref=None,
                coverage="limited",
                receipt_ref="receipt-round-2",
                response_ref="response-round-2",
            ),
            visibility_request=_visibility_request(),
        )
    )
    tool_key = _key(idempotency_key="idem-tool-2")
    tool_prepared = log.append(
        _event("context_prepared", key=tool_key, invocation_id="invocation-tool-2")
    )
    tool_action_key = tool_prepared.action_key
    log.append(
        _event(
            "delivery_uncertain",
            key=tool_key,
            invocation_id="invocation-tool-2",
            uncertainty=_uncertainty(reason="receipt_lost", transport="offline_stand_in"),
        )
    )
    assert log.state(tool_action_key) == "delivery_uncertain"

    # A restart must not walk the tool turn back to "unseen".
    recovered = ExposureLog.load(path)
    assert recovered.state(tool_action_key) == "delivery_uncertain"
    assert recovered.context_exposure(_CONTEXT_IDENTITY) == "exposed"

    replay, payload = replay_exposure_delivery(
        recovered, prepared.action_key, _visibility_request()
    )
    assert replay.reconstruction == "limited"
    assert payload is None
    uncertain = recovered.readback(tool_action_key)["uncertainty"]
    # Offline stand-in transport is labelled as such, not as a real process failure.
    assert uncertain["transport"] == "offline_stand_in"
    assert recovered.readback(prepared.action_key)["replay_coverage"] == "limited"


def test_a0_m03_downstream_stop_decision_links_context_exposure_and_test_family() -> None:
    log, action_key = _prepared_log()
    log.append(_event("envelope_delivered", delivery=_delivery()))
    log.append(
        _event(
            "completion_linked",
            completion=_completion(
                result_ref="a0-round-2-result",
                candidates=["candidate-stop-1"],
                decisions=["selection-stop-1"],
                confirmed_by="completion_result",
            ),
        )
    )
    readback = log.readback(action_key)
    assert readback["state"] == "completed"
    assert readback["delivery_confirmed_by"] == "completion_result"
    entry = log.usage_history(family_id="family-momentum")["entries"][0]
    assert entry["candidate_ids"] == ["candidate-stop-1"]
    assert entry["context_identity"] == readback["context_identity"]
    assert entry["research_family"]["test_family"] == "test-family-momentum"


def test_a0_r01_same_key_retry_reconciles_and_a_different_input_is_refused() -> None:
    log, action_key = _prepared_log()
    first = log.append(_event("envelope_delivered", delivery=_delivery()))
    assert log.append(_event("envelope_delivered", delivery=_delivery())) is first
    with pytest.raises(AcceptanceFailure):
        log.append(
            _event("envelope_delivered", delivery=_delivery(provider_request_id="provider-2"))
        )
    assert log.readback(action_key)["state_trajectory"] == [
        "context_prepared",
        "envelope_delivered",
    ]


def test_independent_invocation_counts_are_reported_per_action() -> None:
    log, action_key = _prepared_log()
    log.append(_event("envelope_delivered", invocation_id="invocation-2", delivery=_delivery()))
    log.append(_event("completion_linked", invocation_id="invocation-3", completion=_completion()))
    assert log.readback(action_key)["invocation_count"] == 3


# --- Hypothesis state machine ------------------------------------------------


_STATE_RANK: dict[str | None, int] = {
    None: 0,
    "prepared": 1,
    "delivery_uncertain": 2,
    "delivered": 3,
    "completed": 4,
}
_CONTEXT_RANK: dict[str, int] = {"unseen": 0, "prepared": 1, "uncertain": 2, "exposed": 3}
_SLOTS = st.integers(min_value=0, max_value=2)


def _slot_key(slot: int) -> dict[str, str]:
    # Distinct Campaigns on purpose: cross-Campaign sequences are in scope.
    return _key(campaign_id=f"campaign-{slot}", idempotency_key=f"idem-{slot}")


def _slot_event(slot: int, event_type: str, *, variant: int = 0) -> dict[str, object]:
    key = _slot_key(slot)
    research_action_id = f"research-action-{slot}"
    if event_type == "context_prepared":
        return _event("context_prepared", key=key, research_action_id=research_action_id)
    if event_type == "envelope_delivered":
        return _event(
            "envelope_delivered",
            key=key,
            research_action_id=research_action_id,
            delivery=_delivery(
                receipt_ref=None if variant == 1 else f"receipt-{slot}",
                provider_request_id=f"provider-request-{slot}-{variant}",
            ),
        )
    if event_type == "delivery_uncertain":
        return _event(
            "delivery_uncertain",
            key=key,
            research_action_id=research_action_id,
            uncertainty=_uncertainty(reason="receipt_lost"),
        )
    return _event(
        "completion_linked",
        key=key,
        research_action_id=research_action_id,
        completion=_completion(),
    )


class ExposureLifecycleMachine(RuleBasedStateMachine):
    """Prepare / send / lost receipt / duplicate callback / retry / cross-Campaign."""

    def __init__(self) -> None:
        super().__init__()
        self.log = ExposureLog()
        self.ranks: dict[int, int] = dict.fromkeys(range(3), 0)
        self.context_rank = 0

    def _action_key(self, slot: int) -> str:
        from .research_exposure import ExposureKey

        return ExposureKey.parse(_slot_key(slot)).action_key()

    def _step(self, slot: int, event: dict[str, object]) -> None:
        action_key = self._action_key(slot)
        before = self.log.state(action_key)
        try:
            self.log.append(event)
        except AcceptanceFailure:
            # A refused event never mutates a recorded fact.
            assert self.log.state(action_key) == before
            return
        after = self.log.state(action_key)
        assert _STATE_RANK[after] >= _STATE_RANK[before]
        self.ranks[slot] = _STATE_RANK[after]

    @rule(slot=_SLOTS)
    def prepare(self, slot: int) -> None:
        self._step(slot, _slot_event(slot, "context_prepared"))

    @rule(slot=_SLOTS, variant=st.integers(min_value=0, max_value=1))
    def send(self, slot: int, variant: int) -> None:
        self._step(slot, _slot_event(slot, "envelope_delivered", variant=variant))

    @rule(slot=_SLOTS)
    def lose_receipt(self, slot: int) -> None:
        self._step(slot, _slot_event(slot, "delivery_uncertain"))

    @rule(slot=_SLOTS)
    def duplicate_callback(self, slot: int) -> None:
        event = _slot_event(slot, "envelope_delivered")
        action_key = self._action_key(slot)
        before = len(self.log.events(action_key))
        try:
            self.log.append(event)
        except AcceptanceFailure:
            assert len(self.log.events(action_key)) == before
            return
        first = len(self.log.events(action_key))
        # A repeated callback with the same frozen input never re-confirms.
        self.log.append(event)
        assert len(self.log.events(action_key)) == first
        self.ranks[slot] = _STATE_RANK[self.log.state(action_key)]

    @rule(slot=_SLOTS)
    def retry_with_a_different_input(self, slot: int) -> None:
        action_key = self._action_key(slot)
        if self.log.state(action_key) != "delivered":
            return
        before = self.log.readback(action_key)
        with pytest.raises(AcceptanceFailure):
            self.log.append(_slot_event(slot, "envelope_delivered", variant=2))
        assert self.log.readback(action_key) == before

    @rule(slot=_SLOTS)
    def complete(self, slot: int) -> None:
        self._step(slot, _slot_event(slot, "completion_linked"))

    @invariant()
    def exposure_never_regresses(self) -> None:
        for slot, rank in self.ranks.items():
            assert _STATE_RANK[self.log.state(self._action_key(slot))] >= rank
        current = _CONTEXT_RANK[self.log.context_exposure(_CONTEXT_IDENTITY)]
        assert current >= self.context_rank
        self.context_rank = current

    @invariant()
    def each_event_type_is_recorded_at_most_once_per_action(self) -> None:
        for action_key in self.log.action_keys:
            trajectory = self.log.readback(action_key)["state_trajectory"]
            assert len(trajectory) == len(set(trajectory))


TestExposureLifecycle = ExposureLifecycleMachine.TestCase
TestExposureLifecycle.settings = settings(
    max_examples=40,
    stateful_step_count=20,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
