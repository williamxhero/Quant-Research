"""Consumer-side tests for the A0 second round: E02 honesty, gates, reuse and stop.

The A0-E02 criterion asks for a real authorized model request and response.  No
owner-authorized `ResearchEnginePort` configuration exists for this repository,
so every test here runs the *offline regression* layer and asserts that the
connected layer stays empty and says so.  The invariants that matter most are
therefore negative ones: a blocked or not-run round can never carry a response,
can never claim model use, and can never yield a Candidate.
"""

from __future__ import annotations

import pytest

from ._research_decision_test import (
    RecordingEngine,
    _page,
    _paginated,
    _protocol,
    _publish_completed_research,
    _question,
    _request,
    _run,
    _visibility,
)
from .research_a0_round2 import (
    ALLOWED_MODEL_ACTIONS,
    ROUND2_DECLARATION_SCHEMA,
    ROUND2_READBACK_SCHEMA,
    EngineAuthorization,
    GovernedRoundTwoEngine,
    ModelDelivery,
    RoundTwoFreeze,
    RoundTwoRefusal,
    review_model_response,
    run_a0_round_two,
    unauthorized_engine,
)
from .research_decision import DecisionLedger, DecisionRequest, RunContract
from .research_exposure import ExposureLog

_CUTOFF = "2026-09-10T00:00:00Z"
_NO_ENGINE_REASON = (
    "no owner-authorized ResearchEnginePort configuration exists for this repository; "
    "A0-E02 is not_run"
)
_EVIDENCE = "record:issue-442-connectivity-probe"


# --- fixtures ----------------------------------------------------------------


def _authorization(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "state": "unauthorized",
        "engine_ref": None,
        "transport": "offline_stand_in",
        "evidence_ref": _EVIDENCE,
        "reason": _NO_ENGINE_REASON,
    }
    value.update(overrides)
    return value


def _envelope(*, authorized: bool = True, added: str = "envelope-addition-1") -> dict[str, object]:
    """A final-envelope check over material the Context never declared."""

    request = _visibility((added,), authorized=authorized)
    request["stage"] = "final_envelope"
    request["context_material_ids"] = []
    return request


def _declaration(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": ROUND2_DECLARATION_SCHEMA,
        "knowledge_cutoff": _CUTOFF,
        "purpose": "research-brief",
        "consumer": "research-model",
        "required_closure": ["a0-counter-v1", "a0-support-v1"],
        "optional_scope": [],
        "template_version": "template-v1",
        "model_version": "model-version-unbound",
        "parameter_digest": "sha256:" + "7" * 64,
        "tool_input_version": "tool-input-v1",
        "allowed_actions": list(ALLOWED_MODEL_ACTIONS),
        "authorization": _authorization(),
        "decision_request": _request(),
        "envelope_request": _envelope(),
        "tool_return_request": None,
    }
    value.update(overrides)
    return value


def _run_round(declaration: dict[str, object] | None = None, **kwargs: object):
    ledger = kwargs.pop("ledger", None) or DecisionLedger()
    exposure = kwargs.pop("exposure", None) or ExposureLog()
    engine = kwargs.pop("engine", None) or RecordingEngine()
    outcome = run_a0_round_two(
        declaration if declaration is not None else _declaration(),
        ledger=ledger,
        exposure=exposure,
        engine=engine,
        **kwargs,  # type: ignore[arg-type]
    )
    return outcome, ledger, exposure, engine


# --- A0-E02: the model call is reported, never simulated ---------------------


def test_a0_e02_reports_not_run_and_never_claims_model_use() -> None:
    outcome, _ledger, _exposure, engine = _run_round()
    assert outcome.e02_status == "not_run"
    assert outcome.delivery.state == "not_run"
    assert outcome.delivery.proves_model_use is False
    assert outcome.delivery.reason == _NO_ENGINE_REASON
    # Nothing that looks like a response exists on a not-run round.
    assert outcome.delivery.invocation_id is None
    assert outcome.delivery.response_ref is None
    assert outcome.delivery.response_digest is None
    assert outcome.review is None
    # The owner's already-permitted actions still ran; the model call did not.
    # The fourth counter is the provider-facing one, and it is zero.
    assert engine.counts() == (1, 1, 1, 0)
    assert engine.calls == []
    assert outcome.engine_counts == {"attempted_calls": 1, "real_calls": 0, "not_run": 1}


def test_a0_e02_a_not_run_round_creates_no_candidate() -> None:
    outcome, _ledger, _exposure, _engine = _run_round()
    assert outcome.candidate_id is None
    assert outcome.no_candidate_reason == "model_delivery_not_run"


def test_a0_e02_a_blocked_or_not_run_delivery_cannot_carry_a_response() -> None:
    authorization = EngineAuthorization.parse(_authorization())
    for state in ("blocked", "not_run"):
        with pytest.raises(RoundTwoRefusal, match="must not carry a model response"):
            ModelDelivery.build(
                state=state,  # type: ignore[arg-type]
                authorization=authorization,
                reason="probe",
                invocation_id="invocation-1",
                response_ref="controlled-store:1",
                raw_response={"proposed_action": "stop"},
            )


def test_a0_e02_an_unauthorized_engine_can_never_produce_a_delivered_state() -> None:
    authorization = EngineAuthorization.parse(_authorization())
    assert authorization.authorized is False
    assert authorization.layer == "offline_regression"
    with pytest.raises(RoundTwoRefusal, match="requires an authorized real engine"):
        ModelDelivery.build(
            state="delivered",
            authorization=authorization,
            reason="probe",
            invocation_id="invocation-1",
            response_ref="controlled-store:1",
            raw_response={"proposed_action": "stop"},
        )


def test_a0_e02_a_connectivity_probe_is_not_an_authorization() -> None:
    """A reachable endpoint with no real transport stays unauthorized."""

    with pytest.raises(RoundTwoRefusal, match="requires a public engine_ref and a real transport"):
        EngineAuthorization.parse(
            _authorization(
                state="authorized",
                engine_ref="engine:probe",
                transport="offline_stand_in",
            )
        )
    with pytest.raises(RoundTwoRefusal, match="requires a public engine_ref and a real transport"):
        EngineAuthorization.parse(
            _authorization(state="authorized", engine_ref=None, transport="real_process")
        )


def test_a0_e02_the_engine_call_is_attempted_but_never_made() -> None:
    engine = RecordingEngine()
    governed = GovernedRoundTwoEngine(engine, EngineAuthorization.parse(_authorization()))
    marker = governed.call_research_engine({"request": "x"})
    assert marker == "not_run:engine_not_authorized"
    assert governed.counts() == {"attempted_calls": 1, "real_calls": 0, "not_run": 1}
    # The delegate — the thing that would reach a provider — was never touched.
    assert engine.calls == []


def test_a0_e02_an_authorization_declaration_may_never_carry_a_credential() -> None:
    for field in ("api_key", "token", "secret", "password", "authorization"):
        with pytest.raises(RoundTwoRefusal, match="must not carry credentials"):
            EngineAuthorization.parse({**_authorization(), field: "any-value"})


def test_a0_e02_the_unauthorized_helper_is_the_documented_default() -> None:
    authorization = unauthorized_engine(_NO_ENGINE_REASON, evidence_ref=_EVIDENCE)
    assert authorization.state == "unauthorized"
    assert authorization.authorized is False
    assert authorization.as_dict()["layer"] == "offline_regression"


# --- A0-P01/P02: protection before any model or tool read --------------------


def test_a0_p01_a_blocked_final_envelope_stops_before_the_model_read() -> None:
    declaration = _declaration(envelope_request=_envelope(authorized=False))
    outcome, _ledger, _exposure, _engine = _run_round(declaration)
    assert outcome.delivery.state == "blocked"
    assert outcome.delivery.reason == "final_envelope_gate:restricted"
    assert outcome.no_candidate_reason == "final_envelope_gate_blocked"
    assert outcome.candidate_id is None
    assert outcome.envelope_gate is not None
    assert outcome.envelope_gate.status == "restricted"
    # A restricted addition is reported, not silently dropped.
    assert outcome.envelope_gate.safety_audit["status"] == "blocked"


def test_a0_p01_the_visibility_gate_stops_the_round_before_any_spend() -> None:
    declaration = _declaration(
        decision_request=_request(visibility_request=_visibility(authorized=False))
    )
    outcome, _ledger, _exposure, engine = _run_round(declaration)
    assert outcome.decision.outcome == "blocked_by_gate"
    assert outcome.delivery.state == "blocked"
    assert engine.counts() == (0, 0, 0, 0)
    assert outcome.counters.total_external_calls() == 0
    assert outcome.envelope_gate is None


def test_a0_p02_an_uncertain_delivery_is_reconciled_and_never_resent() -> None:
    exposure = ExposureLog()
    parsed = DecisionRequest.parse(_request())
    for event_type, extra in (
        ("context_prepared", {"context_material_ids": ["a0-support-v1"]}),
        (
            "delivery_uncertain",
            {
                "uncertainty": {
                    "reason": "request_timeout",
                    "observation": "local_checkpoint",
                    "transport": "real_process",
                }
            },
        ),
    ):
        exposure.append(
            {
                "schema": "quant-research.research-exposure-event.v1",
                "event_type": event_type,
                "key": parsed.key.as_dict(),
                "research_action_id": "research-action-a0",
                "context_identity": "sha256:" + "a" * 64,
                "research_family": parsed.research_family.as_dict(),
                "policy": {
                    "policy_id": "research-policy",
                    "policy_version": "v2",
                    "knowledge_cutoff": _CUTOFF,
                },
                "invocation_id": "invocation-1",
                **extra,
            }
        )
    outcome, _ledger, _exposure, engine = _run_round(exposure=exposure)
    assert outcome.decision.outcome == "reconcile_required"
    assert outcome.delivery.state == "blocked"
    assert engine.counts() == (0, 0, 0, 0)
    # The uncertain state is not washed back to "unseen".
    assert exposure.state(parsed.action_key()) == "delivery_uncertain"


def test_a0_p02_the_public_record_carries_a_digest_not_the_payload() -> None:
    outcome, _ledger, _exposure, _engine = _run_round()
    record = outcome.public_record()
    assert record["delivery"]["response_digest"] is None
    assert "raw_response" not in record["delivery"]
    assert "api_key" not in repr(record)


# --- A0-R01/R02: separate public branch evidence -----------------------------


def test_a0_r01_retry_conflict_and_duplicate_stop_each_have_their_own_branch() -> None:
    ledger = DecisionLedger()
    exposure = ExposureLog()
    engine = RecordingEngine()
    first, *_ = _run_round(ledger=ledger, exposure=exposure, engine=engine)
    assert first.decision.outcome == "proceeded"
    assert engine.counts() == (1, 1, 1, 0)

    # Branch 1: the same action retried reconciles against the record.
    retry, *_ = _run_round(ledger=ledger, exposure=exposure, engine=engine)
    assert retry.decision.outcome == "recovered_existing"
    assert engine.counts() == (1, 1, 1, 0)

    # Branch 2: the same key with a different input is rejected outright.
    conflict, *_ = _run_round(
        _declaration(decision_request=_request(run=_run(parameter_digest="sha256:" + "8" * 64))),
        ledger=ledger,
        exposure=exposure,
        engine=engine,
    )
    assert conflict.decision.outcome == "rejected_key_conflict"
    assert engine.counts() == (1, 1, 1, 0)

    # Branch 3: a truly equivalent research request stops with zero new spend.
    duplicate_ledger = DecisionLedger()
    _publish_completed_research(duplicate_ledger)
    duplicate_engine = RecordingEngine()
    duplicate, *_ = _run_round(
        ledger=duplicate_ledger, exposure=ExposureLog(), engine=duplicate_engine
    )
    assert duplicate.decision.outcome == "stopped_duplicate"
    assert duplicate.delivery.state == "blocked"
    assert len(duplicate_engine.contexts) == 0
    assert len(duplicate_engine.budgets) == 0
    assert len(duplicate_engine.runs) == 0
    assert len(duplicate_engine.calls) == 0
    assert duplicate.counters.as_dict() == {
        "engine_contexts_published": 0,
        "budget_reservations": 0,
        "runs_executed": 0,
        "research_engine_calls": 0,
        "total_external_calls": 0,
    }
    assert duplicate.engine_counts == {"attempted_calls": 0, "real_calls": 0, "not_run": 0}


def test_a0_r02_attach_and_legitimate_new_sample_stay_separate_branches() -> None:
    ledger = DecisionLedger()
    prior = _publish_completed_research(ledger)

    # Branch 4: same execution, new statistical protocol -> attach only.
    attach_engine = RecordingEngine()
    attach, *_ = _run_round(
        _declaration(
            decision_request=_request(
                question=_question(protocol=_protocol(protocol_id="protocol-one-sided")),
                intent="protocol_change",
            )
        ),
        ledger=ledger,
        engine=attach_engine,
    )
    assert attach.decision.run_disposition == "attached_run"
    assert attach.decision.research_disposition == "new_research"
    assert attach_engine.runs == []

    # Branch 5: a legitimate new sample is not caught by Genome-level dedup.
    sample_engine = RecordingEngine()
    sample, *_ = _run_round(
        _declaration(
            decision_request=_request(
                run=_run(data_range="2025-01-01/2025-12-31"), intent="revalidation"
            )
        ),
        engine=sample_engine,
    )
    assert sample.decision.request.run.genome_id == prior.run.genome_id
    assert sample.decision.research_disposition == "new_research"
    assert sample_engine.counts() == (1, 1, 1, 0)
    # Even a legitimate new round still does not reach a model.
    assert sample.e02_status == "not_run"


def test_a0_r02_usage_history_survives_a_new_campaign() -> None:
    ledger = DecisionLedger()
    exposure = ExposureLog()
    first, *_ = _run_round(ledger=ledger, exposure=exposure)
    other_campaign = _request()
    other_campaign["key"]["campaign_id"] = "a0-campaign-2"  # type: ignore[index]
    second, *_ = _run_round(
        _declaration(decision_request=other_campaign), ledger=ledger, exposure=exposure
    )
    # The first Campaign's usage history is still readable from the second, and
    # it is exactly what makes the equivalent question stop there.
    assert first.decision.request.research_family.family_id == "family-a0"
    assert second.decision.outcome == "stopped_duplicate"
    assert "equivalent_research_already_in_flight" in second.decision.reasons
    entries = second.exposure_readback["entries"]
    assert [entry["campaign_id"] for entry in entries] == ["a0-campaign"]
    assert all(entry["research_family"]["family_id"] == "family-a0" for entry in entries)
    # Memory publishes the relation; it never grants eligibility on its own.
    assert second.exposure_readback["grants_eligibility"] is False


def test_a0_r02_a_new_campaign_with_new_research_keeps_both_histories() -> None:
    ledger = DecisionLedger()
    exposure = ExposureLog()
    _first, *_ = _run_round(ledger=ledger, exposure=exposure)
    other_campaign = _request(
        run=_run(data_range="2025-01-01/2025-12-31"), intent="revalidation"
    )
    other_campaign["key"]["campaign_id"] = "a0-campaign-2"  # type: ignore[index]
    second, *_ = _run_round(
        _declaration(decision_request=other_campaign), ledger=ledger, exposure=exposure
    )
    assert second.decision.outcome == "proceeded"
    entries = second.exposure_readback["entries"]
    assert {entry["campaign_id"] for entry in entries} == {"a0-campaign", "a0-campaign-2"}


# --- A0-C01/M02/M03: sources, counter-evidence and the test family -----------


def test_a0_c01_required_counter_evidence_missing_blocks_the_round() -> None:
    paginated = _paginated()
    paginated["retrieval"]["pages"] = [_page(0, ["a0-support-v1"])]  # type: ignore[index]
    outcome, _ledger, _exposure, engine = _run_round(
        _declaration(decision_request=_request(paginated_context=paginated))
    )
    assert outcome.decision.outcome == "blocked_by_gate"
    assert outcome.delivery.state == "blocked"
    assert outcome.candidate_id is None
    assert engine.counts() == (0, 0, 0, 0)


def test_a0_m03_the_test_family_is_preserved_on_the_readback() -> None:
    outcome, _ledger, _exposure, _engine = _run_round()
    readback = outcome.readback()
    assert readback["schema"] == ROUND2_READBACK_SCHEMA
    assert readback["decision"]["research_family"]["test_family"] == "test-family-a0-crossback"
    assert readback["e02_status"] == "not_run"


# --- the structured review ---------------------------------------------------


def _response(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "proposed_action": "stop",
        "cited_source_ids": ["a0-counter-v1"],
        "proposed_step_ids": [],
        "assumptions": ["the 2024 cost model still applies"],
        "boundaries": ["development sample only"],
    }
    value.update(overrides)
    return value


def test_a_response_may_only_continue_add_evidence_or_stop() -> None:
    for action in ALLOWED_MODEL_ACTIONS:
        review = review_model_response(
            _response(proposed_action=action),
            approved_source_ids=("a0-counter-v1",),
            permitted_step_ids=(),
        )
        assert review.verdict == action
        assert review.accepted is True


def test_a_response_that_asks_for_a_new_run_budget_or_strategy_is_refused() -> None:
    for field, code in (
        ("requests_new_run", "new_run_not_authorized"),
        ("requests_new_budget", "new_budget_not_authorized"),
        ("requests_new_strategy", "new_strategy_not_authorized"),
    ):
        review = review_model_response(
            _response(**{field: True}),
            approved_source_ids=("a0-counter-v1",),
            permitted_step_ids=(),
        )
        assert review.verdict == "refused"
        assert code in review.codes
        assert review.accepted is False


def test_a_response_citing_an_unapproved_source_is_refused_not_patched() -> None:
    review = review_model_response(
        _response(cited_source_ids=["a0-counter-v1", "invented-source"]),
        approved_source_ids=("a0-counter-v1",),
        permitted_step_ids=(),
    )
    assert review.verdict == "refused"
    assert review.codes == ("source_not_approved",)
    assert review.unapproved_source_ids == ("invented-source",)


def test_a_response_proposing_an_unpermitted_step_is_refused() -> None:
    review = review_model_response(
        _response(proposed_step_ids=["step-nobody-approved"]),
        approved_source_ids=("a0-counter-v1",),
        permitted_step_ids=("a0-step-1",),
    )
    assert review.verdict == "refused"
    assert review.codes == ("step_not_permitted",)


def test_an_unsourced_conclusion_never_becomes_a_verified_one() -> None:
    review = review_model_response(
        _response(proposed_action="continue", cited_source_ids=[]),
        approved_source_ids=("a0-counter-v1",),
        permitted_step_ids=(),
    )
    assert review.verdict == "refused"
    assert "unsourced_conclusion" in review.codes
    # Stopping with no citation is still a legitimate answer.
    stop = review_model_response(
        _response(cited_source_ids=[]),
        approved_source_ids=("a0-counter-v1",),
        permitted_step_ids=(),
    )
    assert stop.verdict == "stop"


def test_a_response_without_declared_boundaries_is_refused() -> None:
    review = review_model_response(
        _response(boundaries=[]),
        approved_source_ids=("a0-counter-v1",),
        permitted_step_ids=(),
    )
    assert review.verdict == "refused"
    assert "boundary_declaration_missing" in review.codes


def test_the_review_judges_structure_not_wording() -> None:
    """Different prose, same structure, same verdict."""

    first = review_model_response(
        _response(assumptions=["cost model v2 holds"]),
        approved_source_ids=("a0-counter-v1",),
        permitted_step_ids=(),
    )
    second = review_model_response(
        _response(assumptions=["we assume the v2 cost model continues to apply"]),
        approved_source_ids=("a0-counter-v1",),
        permitted_step_ids=(),
    )
    assert first.verdict == second.verdict == "stop"
    assert first.codes == second.codes == ()


# --- the layered report ------------------------------------------------------


def test_the_two_evidence_layers_are_reported_separately() -> None:
    outcome, _ledger, _exposure, _engine = _run_round()
    layers = outcome.evidence_layers
    assert set(layers) == {"real_connected", "offline_regression"}
    connected = layers["real_connected"]
    assert connected["status"] == "not_run"
    assert connected["proves_model_use"] is False
    assert connected["response_digest"] is None
    offline = layers["offline_regression"]
    assert offline["decision_outcome"] == "proceeded"
    # The offline layer never presents itself as the connected evidence.
    assert offline["substitutes_for_connected"] is False


def test_the_round_identity_is_deterministic_and_binds_the_freeze() -> None:
    first, *_ = _run_round()
    second, *_ = _run_round()
    assert first.identity == second.identity
    assert first.freeze.identity == second.freeze.identity
    changed, *_ = _run_round(_declaration(model_version="model-version-other"))
    assert changed.freeze.identity != first.freeze.identity


# --- declaration refusals ----------------------------------------------------


def test_a_declaration_may_not_allow_an_action_outside_the_policy() -> None:
    with pytest.raises(RoundTwoRefusal, match="exceed the permitted actions"):
        RoundTwoFreeze.parse(_declaration(allowed_actions=["continue", "start_new_backtest"]))


def test_a_malformed_declaration_is_refused() -> None:
    for broken in (
        _declaration(schema="something-else"),
        {**_declaration(), "unexpected": 1},
        _declaration(knowledge_cutoff=""),
        _declaration(required_closure=[]),
    ):
        with pytest.raises(RoundTwoRefusal):
            RoundTwoFreeze.parse(broken)


def test_the_round_opens_no_store_and_reaches_no_provider(monkeypatch) -> None:
    """The offline layer must be provable without any network or filesystem."""

    import socket

    def _forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the A0 second round must not open a socket")

    monkeypatch.setattr(socket, "socket", _forbidden)
    monkeypatch.setattr(socket, "create_connection", _forbidden)
    outcome, _ledger, _exposure, _engine = _run_round()
    assert outcome.e02_status == "not_run"


def test_a_blocked_run_contract_still_parses_publicly() -> None:
    """The helper the duplicate fixtures rely on stays constructible."""

    parsed = DecisionRequest.parse(_request())
    blocked = RunContract.parse({**parsed.run.as_dict(), "terminal_state": "blocked"})
    assert blocked.qualifies_for_reuse is False


# --- the authorized path, exercised by a harness and labelled as such ---------
#
# NOTHING BELOW IS A0-E02 EVIDENCE.  No owner-authorized ResearchEnginePort
# configuration exists for this repository, so the authorized branch is driven
# here by a local harness purely to keep it exercised.  The harness declares its
# own engine reference; it reaches no provider and spends nothing.  A0-E02
# remains not_run, which the tests above are the evidence for.


def _harness_authorization() -> dict[str, object]:
    return _authorization(
        state="authorized",
        engine_ref="engine:local-test-harness",
        transport="real_process",
        reason="local test harness; not an owner authorization and not E02 evidence",
    )


def test_harness_only_the_authorized_branch_reviews_and_admits_a_candidate() -> None:
    outcome, _ledger, exposure, engine = _run_round(
        _declaration(authorization=_harness_authorization()),
        model_response=_response(proposed_action="add_evidence"),
    )
    assert outcome.delivery.state == "delivered"
    assert outcome.delivery.response_digest is not None
    assert outcome.review is not None
    assert outcome.review.verdict == "add_evidence"
    assert outcome.candidate_id == f"candidate:{outcome.freeze.identity}"
    # The harness delegate really was called, exactly once.
    assert engine.counts() == (1, 1, 1, 1)
    assert exposure.state(outcome.decision.request.action_key()) == "delivered"


def test_harness_only_a_refused_response_never_yields_a_candidate() -> None:
    outcome, _ledger, _exposure, _engine = _run_round(
        _declaration(authorization=_harness_authorization()),
        model_response=_response(proposed_action="continue", requests_new_run=True),
    )
    assert outcome.delivery.state == "delivered"
    assert outcome.review is not None
    assert outcome.review.verdict == "refused"
    assert "new_run_not_authorized" in outcome.review.codes
    assert outcome.candidate_id is None
    assert outcome.no_candidate_reason.startswith("model_response_refused:")


def test_harness_only_a_stop_decision_is_a_successful_round() -> None:
    outcome, _ledger, _exposure, _engine = _run_round(
        _declaration(authorization=_harness_authorization()),
        model_response=_response(proposed_action="stop"),
    )
    assert outcome.review is not None
    assert outcome.review.verdict == "stop"
    assert outcome.candidate_id is None
    assert outcome.no_candidate_reason == "model_proposed_stop"


def test_harness_only_an_authorized_round_without_a_response_is_refused() -> None:
    with pytest.raises(RoundTwoRefusal, match="requires the real controlled model response"):
        _run_round(_declaration(authorization=_harness_authorization()))
