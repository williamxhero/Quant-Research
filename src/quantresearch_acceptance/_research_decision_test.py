"""Consumer-side tests for the duplicate-stop / non-duplicate call-order gate."""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from .core import AcceptanceFailure
from .research_context import BRIEF_TEMPLATE_ID, CONTEXT_DECLARATION_SCHEMA
from .research_decision import (
    DECISION_RECORD_SCHEMA,
    DECISION_REQUEST_SCHEMA,
    DECISION_STEP_CONTRACT,
    DECISION_STEP_CONTRACT_DIGEST,
    DECISION_STEPS,
    DecisionLedger,
    DecisionRefusal,
    DecisionRequest,
    ResearchFamilyRef,
    RunContract,
    StatisticalProtocol,
    decide_research_request,
    inspect_decision_history,
    reconstruct_decision_outcome,
)
from .research_exposure import EXPOSURE_EVENT_SCHEMA, ExposureLog
from .research_pagination import PAGINATED_DECLARATION_SCHEMA
from .research_visibility import VISIBILITY_REQUEST_SCHEMA

_ORDERING = "ordering:published-at"
_TRIMMING = "trimming:unit-atomic-v1"
_CUTOFF = "2026-09-10T00:00:00Z"
_SNAPSHOT_ID = "snapshot-2026-09-10"
_PARAMS = "sha256:" + "7" * 64
_OTHER_PARAMS = "sha256:" + "8" * 64


class RecordingEngine:
    """The engine seam, instrumented.

    Each spend is counted on its own attribute, because the acceptance criteria
    require the duplicate branch to be proved with four separate zeros rather
    than with one "nothing happened".
    """

    def __init__(self) -> None:
        self.contexts: list[str] = []
        self.budgets: list[tuple[str, int]] = []
        self.runs: list[str] = []
        self.calls: list[dict[str, object]] = []
        self.trace: list[str] = []

    def publish_context(self, record) -> str:
        self.trace.append("publish_context")
        identity = str(record["paginated_identity"])
        self.contexts.append(identity)
        return identity

    def reserve_budget(self, budget_id: str, units: int) -> str:
        self.trace.append("reserve_budget")
        self.budgets.append((budget_id, units))
        return f"reservation:{budget_id}"

    def execute_run(self, run_key: str, contract) -> str:
        self.trace.append("execute_run")
        self.runs.append(run_key)
        return f"run:{len(self.runs)}"

    def call_research_engine(self, request) -> str:
        self.trace.append("call_research_engine")
        self.calls.append(dict(request))
        return f"invocation:{len(self.calls)}"

    def counts(self) -> tuple[int, int, int, int]:
        return (len(self.contexts), len(self.budgets), len(self.runs), len(self.calls))


def _source(source_id: str, *, retrieval: str = "ok") -> dict[str, object]:
    return {
        "source_id": source_id,
        "record_type": "finding",
        "approved": True,
        "applicable": True,
        "retrieval": retrieval,
        "published_at": "2026-09-01T00:00:00Z",
        "provenance_ref": f"record:{source_id}",
        "content_digest": "sha256:" + "1" * 64,
        "derived_from": [],
    }


def _context_declaration(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": CONTEXT_DECLARATION_SCHEMA,
        "mode": "current_research",
        "purpose": "research-brief",
        "query_scope": {
            "campaign_id": "a0-campaign",
            "iteration_id": "a0-round-2",
            "question_id": "a0-v0-vs-v1",
            "ordering": _ORDERING,
            "trimming": _TRIMMING,
        },
        "snapshot": {
            "snapshot_id": _SNAPSHOT_ID,
            "knowledge_cutoff": _CUTOFF,
            "corrections_version": "corrections-v3",
        },
        "policy": {
            "policy_id": "research-policy",
            "policy_version": "v2",
            "template_id": BRIEF_TEMPLATE_ID,
            "template_version": "v1",
        },
        "budget": {"discussion_budget": 32, "closure_budget": 16},
        "required_closure": ["a0-support-v1", "a0-counter-v1"],
        "optional_scope": {"source_ids": [], "exhausted": True},
        "sources": [_source("a0-support-v1"), _source("a0-counter-v1")],
        "owner_facts": {
            "current_candidate": {
                "value": "a0-candidate-v1",
                "provenance": ["record:a0-candidate-v1"],
            }
        },
        "evidence_gaps": [],
        "candidate_next_steps": [],
        "conclusions": [
            {
                "conclusion_id": "a0-conclusion-1",
                "statement_ref": "record:a0-statement-1",
                "required_support": ["a0-support-v1"],
                "required_counter_evidence": ["a0-counter-v1"],
                "limitations": [],
                "optional": False,
            }
        ],
        "genome_compare": None,
        "visibility_request": None,
    }
    value.update(overrides)
    return value


def _page(index: int, sources: list[str], *, exhausted: bool = True) -> dict[str, object]:
    return {
        "page_index": index,
        "cursor_in": f"cursor-{index}",
        "cursor_out": f"cursor-{index + 1}",
        "status": "ok",
        "exhausted": exhausted,
        "records": [
            {
                "source_id": source_id,
                "sort_key": f"k-{position:02d}",
                "published_at": "2026-09-01T00:00:00Z",
            }
            for position, source_id in enumerate(sources)
        ],
    }


def _paginated(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": PAGINATED_DECLARATION_SCHEMA,
        "context": _context_declaration(),
        "retrieval": {
            "plan": {
                "retrieval_id": "retrieval-1",
                "ordering_key": _ORDERING,
                "trimming_policy": _TRIMMING,
                "policy_version": "v1",
                "page_size": 2,
                "page_budget": 4,
                "record_budget": 8,
                "cursor": {
                    "cursor_id": "cursor-0",
                    "snapshot_id": _SNAPSHOT_ID,
                    "ordering_key": _ORDERING,
                    "position": "start",
                    "page_index": 0,
                },
            },
            "pages": [_page(0, ["a0-counter-v1", "a0-support-v1"])],
        },
    }
    value.update(overrides)
    return value


def _visibility(
    source_ids: tuple[str, ...] = ("a0-support-v1", "a0-counter-v1"),
    *,
    authorized: bool = True,
    purpose: str = "research-brief",
) -> dict[str, object]:
    granted_purpose = purpose if authorized else "some-other-purpose"
    return {
        "schema": VISIBILITY_REQUEST_SCHEMA,
        "stage": "initial_read",
        "mode": "strict",
        "consumer": {
            "actor_id": "actor-1",
            "consumer": "research-model",
            "action": "assemble_context",
            "purpose": purpose,
            "capabilities": ["cap.research"],
            "authorization_policy_id": "auth-policy",
            "authorization_policy_version": "v1",
            "authorization_knowledge_cutoff": _CUTOFF,
            "grants": [
                {
                    "logical_dataset": "research-memory",
                    "universe": ["cn-a"],
                    "time_range": {"start": "2020-01-01", "end": "2026-09-01"},
                    "sample_roles": ["development"],
                    "purposes": [granted_purpose],
                }
            ],
        },
        "research_policy": {
            "policy_id": "research-policy",
            "policy_version": "v2",
            "knowledge_cutoff": _CUTOFF,
            "permitted_sample_roles": ["development"],
            "permitted_purposes": [purpose],
        },
        "materials": [
            {
                "material_id": source_id,
                "record_type": "finding",
                "logical_dataset": "research-memory",
                "universe": ["cn-a"],
                "time_range": {"start": "2021-01-01", "end": "2025-12-31"},
                "sample_role": "development",
                "derived_from": [],
                "allowed_purposes": [purpose],
                "required_capabilities": ["cap.research"],
            }
            for source_id in source_ids
        ],
        "context_material_ids": list(source_ids),
    }


def _run(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "package_id": "package-a0",
        "genome_id": "genome-ema-crossback",
        "parameter_digest": _PARAMS,
        "data_snapshot_id": _SNAPSHOT_ID,
        "data_range": "2020-01-01/2024-12-31",
        "cost_environment": "cost-model-v2",
        "execution_environment": "runtime-v4",
        "randomness": {"seed_policy": "fixed", "seed_ref": "seed-1", "replicates": 1},
        "terminal_state": "completed",
    }
    value.update(overrides)
    return value


def _protocol(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "protocol_id": "protocol-two-sided",
        "protocol_version": "v1",
        "multiplicity_policy": "bonferroni",
        "inference_fields": ["effect-size", "p-value"],
    }
    value.update(overrides)
    return value


def _question(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "question_id": "a0-does-v1-filter-help",
        "failure_direction": "volume-contraction-filter-adds-no-edge",
        "comparison_target": "a0-v0-baseline",
        "evidence_requirements": ["a0-counter-v1", "a0-support-v1"],
        "protocol": _protocol(),
    }
    value.update(overrides)
    return value


def _request(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": DECISION_REQUEST_SCHEMA,
        "key": {
            "campaign_id": "a0-campaign",
            "iteration_id": "a0-round-2",
            "consumer": "research-model",
            "action": "research_request",
            "idempotency_key": "idem-1",
        },
        "display_name": "A0-V1-volume-filter-study",
        "policy": {
            "policy_id": "research-policy",
            "policy_version": "v2",
            "predecessor_decision_id": "decision-0",
        },
        "research_family": {
            "family_id": "family-a0",
            "test_family": "test-family-a0-crossback",
            "prior_result_ids": ["prior-result-1"],
        },
        "approved_source_ids": ["a0-counter-v1", "a0-support-v1"],
        "intent": "initial",
        "question": _question(),
        "run": _run(),
        "blocker_repair": None,
        "budget_request": {"budget_id": "budget-research", "units": 10},
        "paginated_context": _paginated(),
        "visibility_request": _visibility(),
    }
    value.update(overrides)
    return value


def _decide(request: dict[str, object] | None = None, **kwargs: object):
    ledger = kwargs.pop("ledger", None) or DecisionLedger()
    exposure = kwargs.pop("exposure", None) or ExposureLog()
    engine = kwargs.pop("engine", None) or RecordingEngine()
    outcome = decide_research_request(
        request if request is not None else _request(),
        ledger=ledger,
        exposure=exposure,
        engine=engine,
    )
    return outcome, ledger, exposure, engine


def _parsed(request: dict[str, object] | None = None) -> DecisionRequest:
    return DecisionRequest.parse(request if request is not None else _request())


def _publish_completed_research(
    ledger: DecisionLedger,
    request: dict[str, object] | None = None,
    *,
    state: str = "completed",
    blocker_id: str | None = None,
) -> DecisionRequest:
    """Publish the prior run and judgment a later request will be compared to."""

    parsed = _parsed(request)
    # A judgment blocked by data never leaves behind a reusable execution fact.
    run_contract = (
        parsed.run
        if state == "completed"
        else RunContract.parse({**parsed.run.as_dict(), "terminal_state": "blocked"})
    )
    ledger.publish_run(
        run_id="run-original",
        run_contract=run_contract,
        protocol=parsed.question.protocol,
    )
    ledger.publish_judgment(
        judgment_id="judgment-original",
        research_key=parsed.research_key(),
        run_key=parsed.run_key(),
        family=parsed.research_family,
        state=state,
        blocker_id=blocker_id,
    )
    return parsed


# --- the step contract ------------------------------------------------------


def test_the_step_contract_is_frozen_ordered_and_versioned() -> None:
    assert tuple(step for step, _phase in DECISION_STEP_CONTRACT) == DECISION_STEPS
    phases = [phase for _step, phase in DECISION_STEP_CONTRACT]
    # Every act comes after every gate, which comes after every decision.
    assert phases.index("gate") > max(index for index, p in enumerate(phases) if p == "decide")
    assert phases.index("act") > max(index for index, p in enumerate(phases) if p == "gate")
    assert DECISION_STEP_CONTRACT_DIGEST.startswith("sha256:")


def test_the_step_contract_digest_binds_every_decision_identity() -> None:
    outcome, _ledger, _exposure, _engine = _decide()
    assert outcome.readback()["step_contract_digest"] == DECISION_STEP_CONTRACT_DIGEST


# --- the three decisions stay separate --------------------------------------


def test_the_run_key_excludes_the_statistical_protocol() -> None:
    base = _parsed()
    other = _parsed(_request(question=_question(protocol=_protocol(protocol_id="protocol-one"))))
    assert base.run_key() == other.run_key()
    # ...but a different protocol is a different piece of research.
    assert base.research_key() != other.research_key()


def test_a_genome_match_alone_is_not_a_run_match() -> None:
    base = _parsed()
    for field, value in (
        ("parameter_digest", _OTHER_PARAMS),
        ("data_range", "2015-01-01/2019-12-31"),
        ("data_snapshot_id", "snapshot-2026-08-01"),
        ("cost_environment", "cost-model-v3"),
        ("execution_environment", "runtime-v5"),
    ):
        other = _parsed(_request(run=_run(**{field: value})))
        assert other.run.genome_id == base.run.genome_id
        assert other.run_key() != base.run_key(), field


def test_a_different_randomness_contract_is_a_different_run() -> None:
    base = _parsed()
    randomness = {"seed_policy": "fixed", "seed_ref": "seed-2", "replicates": 3}
    other = _parsed(_request(run=_run(randomness=randomness)))
    assert other.run_key() != base.run_key()


def test_renaming_a_request_changes_no_key() -> None:
    base = _parsed()
    renamed = _parsed(_request(display_name="a-completely-different-title"))
    assert renamed.input_digest() == base.input_digest()
    assert renamed.run_key() == base.run_key()
    assert renamed.research_key() == base.research_key()


def test_the_declared_intent_changes_no_research_key() -> None:
    base = _parsed()
    claimed = _parsed(_request(intent="replication"))
    assert claimed.research_key() == base.research_key()


def test_the_readback_reports_three_decisions_not_one_flag() -> None:
    outcome, _ledger, _exposure, _engine = _decide()
    decisions = outcome.readback()["decisions"]
    assert set(decisions) == {"request_idempotency", "run_reuse", "research_duplication"}
    assert decisions["run_reuse"]["protocol_in_run_key"] is False
    assert decisions["run_reuse"]["matched_on"] == "execution_contract"
    assert decisions["research_duplication"]["strategy_falsified"] is False


# --- the duplicate branch ---------------------------------------------------


def test_a_true_duplicate_stops_before_context_budget_run_and_call() -> None:
    ledger = DecisionLedger()
    _publish_completed_research(ledger)
    engine = RecordingEngine()
    outcome, _ledger, _exposure, engine = _decide(ledger=ledger, engine=engine)
    assert outcome.outcome == "stopped_duplicate"
    assert outcome.research_disposition == "duplicate_research"
    # Four counters, asserted separately.
    assert engine.contexts == []
    assert engine.budgets == []
    assert engine.runs == []
    assert engine.calls == []
    assert engine.counts() == (0, 0, 0, 0)
    assert engine.trace == []
    counters = outcome.counters
    assert counters.engine_contexts_published == 0
    assert counters.budget_reservations == 0
    assert counters.runs_executed == 0
    assert counters.research_engine_calls == 0
    assert counters.total_external_calls() == 0


def test_the_duplicate_branch_completes_the_canonical_readback_before_stopping() -> None:
    ledger = DecisionLedger()
    _publish_completed_research(ledger)
    outcome, _ledger, _exposure, _engine = _decide(ledger=ledger)
    assert outcome.trace == (
        "read_predecessor_policy",
        "read_approved_sources",
        "decide_request_idempotency",
        "decide_run_reuse",
        "decide_research_duplication",
        "publish_decision_readback",
        "stop_on_research_duplicate",
    )
    readback = outcome.readback()
    assert readback["decisions"]["research_duplication"]["prior_judgment_id"] == "judgment-original"
    assert readback["context_identity"] is None
    assert readback["paginated_identity"] is None


def test_a_renamed_equivalent_request_is_still_a_duplicate() -> None:
    ledger = DecisionLedger()
    _publish_completed_research(ledger)
    renamed = _request(display_name="brand-new-sounding-study")
    outcome, _ledger, _exposure, engine = _decide(renamed, ledger=ledger)
    assert outcome.outcome == "stopped_duplicate"
    assert engine.counts() == (0, 0, 0, 0)


def test_a_self_declared_replication_that_changes_nothing_is_still_a_duplicate() -> None:
    ledger = DecisionLedger()
    _publish_completed_research(ledger)
    for index, intent in enumerate(
        ("replication", "revalidation", "new_sample", "randomness_experiment")
    ):
        request = _request(intent=intent)
        request["key"]["idempotency_key"] = f"idem-{index}"  # type: ignore[index]
        outcome, _ledger, _exposure, engine = _decide(request, ledger=ledger)
        assert outcome.outcome == "stopped_duplicate", intent
        assert engine.counts() == (0, 0, 0, 0), intent


# --- the non-duplicate branch -----------------------------------------------


def test_a_new_question_calls_the_engine_only_after_the_gates_pass() -> None:
    outcome, _ledger, _exposure, engine = _decide()
    assert outcome.outcome == "proceeded"
    # Every declared step but the duplicate stop, in the declared order.
    assert outcome.trace == tuple(
        step for step in DECISION_STEPS if step != "stop_on_research_duplicate"
    )
    assert engine.trace == [
        "publish_context",
        "reserve_budget",
        "execute_run",
        "call_research_engine",
    ]
    assert engine.counts() == (1, 1, 1, 1)
    assert engine.budgets == [("budget-research", 10)]


def test_a_blocked_visibility_gate_stops_before_any_spend() -> None:
    denied = _visibility(authorized=False)
    outcome, _ledger, _exposure, engine = _decide(_request(visibility_request=denied))
    assert outcome.outcome == "blocked_by_gate"
    assert engine.counts() == (0, 0, 0, 0)
    assert "check_visibility" in outcome.trace
    assert "publish_engine_context" not in outcome.trace


def test_an_incomplete_required_scope_stops_before_any_spend() -> None:
    declaration = _paginated()
    declaration["retrieval"]["pages"] = [_page(0, ["a0-counter-v1"])]  # type: ignore[index]
    outcome, _ledger, _exposure, engine = _decide(_request(paginated_context=declaration))
    assert outcome.outcome == "blocked_by_gate"
    assert outcome.reasons == ("retrieval:required_lineage_missing",)
    assert engine.counts() == (0, 0, 0, 0)
    assert "check_required_completeness" in outcome.trace
    assert "reserve_budget" not in outcome.trace


def test_a_blocked_brief_stops_before_any_spend() -> None:
    declaration = _paginated()
    context = _context_declaration(
        sources=[_source("a0-support-v1"), _source("a0-counter-v1", retrieval="failed")]
    )
    declaration["context"] = context
    outcome, _ledger, _exposure, engine = _decide(_request(paginated_context=declaration))
    assert outcome.outcome == "blocked_by_gate"
    assert outcome.reasons[0].startswith("brief_blocked:")
    assert engine.counts() == (0, 0, 0, 0)


def test_the_visibility_gate_is_checked_before_completeness() -> None:
    denied = _visibility(authorized=False)
    declaration = _paginated()
    declaration["retrieval"]["pages"] = [_page(0, ["a0-counter-v1"])]  # type: ignore[index]
    outcome, _ledger, _exposure, _engine = _decide(
        _request(visibility_request=denied, paginated_context=declaration)
    )
    # Both would fail; the declared order decides which answer is given.
    assert outcome.reasons == ("visibility:current_authorization_denied",)
    assert "check_required_completeness" not in outcome.trace


# --- request idempotency ----------------------------------------------------


def test_a_retry_of_the_same_action_recovers_instead_of_re_executing() -> None:
    ledger = DecisionLedger()
    engine = RecordingEngine()
    first, _l, exposure, _e = _decide(ledger=ledger, engine=engine)
    assert first.outcome == "proceeded"
    assert engine.counts() == (1, 1, 1, 1)
    second, _l, _e2, engine2 = _decide(ledger=ledger, exposure=exposure)
    assert second.outcome == "recovered_existing"
    assert second.request_disposition == "recovered_existing"
    assert engine2.counts() == (0, 0, 0, 0)
    assert engine.counts() == (1, 1, 1, 1)


def test_the_same_key_with_a_different_input_is_rejected() -> None:
    ledger = DecisionLedger()
    _first, _l, exposure, _e = _decide(ledger=ledger)
    conflicting = _request(run=_run(parameter_digest=_OTHER_PARAMS))
    second, _l, _e2, engine = _decide(conflicting, ledger=ledger, exposure=exposure)
    assert second.outcome == "rejected_key_conflict"
    assert second.reasons == ("idempotency_key_reused_with_different_input",)
    assert engine.counts() == (0, 0, 0, 0)


def test_a_rename_alone_is_not_a_key_conflict() -> None:
    ledger = DecisionLedger()
    _first, _l, exposure, _e = _decide(ledger=ledger)
    renamed = _request(display_name="same-request-new-title")
    second, _l, _e2, engine = _decide(renamed, ledger=ledger, exposure=exposure)
    assert second.outcome == "recovered_existing"
    assert engine.counts() == (0, 0, 0, 0)


def test_a_different_idempotency_key_is_a_different_action() -> None:
    ledger = DecisionLedger()
    _first, _l, exposure, _e = _decide(ledger=ledger)
    other_key = _request()
    other_key["key"]["idempotency_key"] = "idem-2"  # type: ignore[index]
    # A different action key with the same question is still research duplication.
    _publish_completed_research(ledger)
    second, _l, _e2, engine = _decide(other_key, ledger=ledger, exposure=exposure)
    assert second.request_disposition == "new_request"
    assert second.outcome == "stopped_duplicate"
    assert engine.counts() == (0, 0, 0, 0)


def test_a_second_idempotency_key_cannot_buy_the_same_research_twice() -> None:
    ledger = DecisionLedger()
    exposure = ExposureLog()
    engine = RecordingEngine()
    first = decide_research_request(
        _request(), ledger=ledger, exposure=exposure, engine=engine
    )
    assert first.outcome == "proceeded"
    second_request = _request()
    second_request["key"]["idempotency_key"] = "idem-2"  # type: ignore[index]
    second = decide_research_request(
        second_request, ledger=ledger, exposure=exposure, engine=engine
    )
    # A new action key, the identical question: a duplicate, not a new request.
    assert second.request_disposition == "new_request"
    assert second.outcome == "stopped_duplicate"
    assert "equivalent_research_already_in_flight" in second.reasons
    assert engine.counts() == (1, 1, 1, 1)


def test_an_uncertain_delivery_is_reconciled_before_anything_is_resent() -> None:
    exposure = ExposureLog()
    parsed = _parsed()
    exposure.append(_exposure_event("context_prepared", parsed))
    exposure.append(
        _exposure_event(
            "delivery_uncertain",
            parsed,
            uncertainty={
                "reason": "receipt_lost",
                "observation": "local_checkpoint",
                "transport": "real_process",
            },
        )
    )
    outcome, _ledger, _exposure, engine = _decide(exposure=exposure)
    assert outcome.outcome == "reconcile_required"
    assert outcome.reasons == ("delivery_uncertain_must_reconcile_first",)
    assert outcome.readback()["decisions"]["request_idempotency"]["resend_allowed"] is False
    assert engine.counts() == (0, 0, 0, 0)


def _exposure_event(
    event_type: str,
    parsed: DecisionRequest,
    *,
    uncertainty: dict[str, object] | None = None,
) -> dict[str, object]:
    event: dict[str, object] = {
        "schema": EXPOSURE_EVENT_SCHEMA,
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
    }
    if event_type == "context_prepared":
        event["context_material_ids"] = ["a0-support-v1"]
    if uncertainty is not None:
        event["uncertainty"] = uncertainty
    return event


# --- run reuse versus research duplication ----------------------------------


def test_a_new_statistical_protocol_attaches_to_the_run_and_still_judges_afresh() -> None:
    ledger = DecisionLedger()
    _publish_completed_research(ledger)
    reinterpreted = _request(
        question=_question(protocol=_protocol(protocol_id="protocol-one-sided")),
        intent="protocol_change",
    )
    outcome, _l, _e, engine = _decide(reinterpreted, ledger=ledger)
    assert outcome.outcome == "proceeded"
    assert outcome.run_disposition == "attached_run"
    assert outcome.reused_run_id == "run-original"
    assert outcome.research_disposition == "new_research"
    # The execution fact is reused: no backtest is re-run.
    assert engine.runs == []
    assert engine.counts() == (1, 1, 0, 1)
    assert engine.trace == ["publish_context", "reserve_budget", "call_research_engine"]


def test_a_legitimate_new_sample_is_not_blocked_by_a_matching_genome() -> None:
    ledger = DecisionLedger()
    prior = _publish_completed_research(ledger)
    new_sample = _request(
        run=_run(data_range="2025-01-01/2025-12-31"),
        intent="new_sample",
    )
    outcome, _l, _e, engine = _decide(new_sample, ledger=ledger)
    assert outcome.request.run.genome_id == prior.run.genome_id
    assert outcome.outcome == "proceeded"
    assert outcome.run_disposition == "new_run"
    assert outcome.research_disposition == "new_research"
    assert engine.counts() == (1, 1, 1, 1)


def test_a_reused_run_does_not_by_itself_make_the_research_a_duplicate() -> None:
    ledger = DecisionLedger()
    _publish_completed_research(ledger)
    # Same execution contract, different question: the run is reusable, the
    # research is new.  Two independent axes, not one combined check.
    new_question = _request(question=_question(question_id="a0-does-v1-help-in-drawdowns"))
    outcome, _l, _e, engine = _decide(new_question, ledger=ledger)
    assert outcome.run_disposition == "reused_run"
    assert outcome.research_disposition == "new_research"
    assert outcome.outcome == "proceeded"
    assert engine.runs == []
    assert engine.counts() == (1, 1, 0, 1)


def test_a_run_that_never_completed_is_not_reusable() -> None:
    ledger = DecisionLedger()
    parsed = _parsed(_request(run=_run(terminal_state="failed")))
    ledger.publish_run(
        run_id="run-failed", run_contract=parsed.run, protocol=parsed.question.protocol
    )
    outcome, _l, _e, engine = _decide(_request(run=_run(terminal_state="failed")), ledger=ledger)
    assert outcome.run_disposition == "new_run"
    assert engine.runs == [parsed.run_key()]


# --- data blockers ----------------------------------------------------------


def test_an_unrepaired_data_blocker_blocks_without_claiming_falsification() -> None:
    ledger = DecisionLedger()
    _publish_completed_research(ledger, state="blocked_by_data", blocker_id="blocker-gap-2024")
    outcome, _l, _e, engine = _decide(ledger=ledger)
    assert outcome.outcome == "blocked_prior_data_blocker"
    assert outcome.research_disposition == "blocked_prior_data_blocker"
    assert "not_strategy_falsification" in outcome.reasons
    assert outcome.readback()["decisions"]["research_duplication"]["strategy_falsified"] is False
    assert engine.counts() == (0, 0, 0, 0)


def test_a_repaired_blocker_with_an_owner_permitted_condition_proceeds() -> None:
    ledger = DecisionLedger()
    _publish_completed_research(ledger, state="blocked_by_data", blocker_id="blocker-gap-2024")
    retry = _request(
        intent="blocker_retry",
        blocker_repair={
            "blocker_id": "blocker-gap-2024",
            "new_condition": "vendor-backfill-verified",
            "owner_permitted": True,
            "repair_ref": "record:repair-1",
        },
    )
    outcome, _l, _e, engine = _decide(retry, ledger=ledger)
    assert outcome.outcome == "proceeded"
    assert outcome.research_disposition == "new_research"
    assert "blocker_repaired_under_owner_permitted_condition" in outcome.reasons
    assert "new_condition:vendor-backfill-verified" in outcome.reasons
    assert engine.counts() == (1, 1, 1, 1)


def test_a_repair_the_owner_did_not_permit_does_not_proceed() -> None:
    ledger = DecisionLedger()
    _publish_completed_research(ledger, state="blocked_by_data", blocker_id="blocker-gap-2024")
    retry = _request(
        intent="blocker_retry",
        blocker_repair={
            "blocker_id": "blocker-gap-2024",
            "new_condition": "self-declared-fix",
            "owner_permitted": False,
            "repair_ref": "record:repair-2",
        },
    )
    outcome, _l, _e, engine = _decide(retry, ledger=ledger)
    assert outcome.outcome == "blocked_prior_data_blocker"
    assert engine.counts() == (0, 0, 0, 0)


def test_a_repair_that_names_another_blocker_is_refused() -> None:
    ledger = DecisionLedger()
    _publish_completed_research(ledger, state="blocked_by_data", blocker_id="blocker-gap-2024")
    retry = _request(
        blocker_repair={
            "blocker_id": "blocker-something-else",
            "new_condition": "vendor-backfill-verified",
            "owner_permitted": True,
            "repair_ref": "record:repair-3",
        }
    )
    with pytest.raises(DecisionRefusal):
        _decide(retry, ledger=ledger)


# --- families, history and read-only access ---------------------------------


def test_a_new_campaign_never_resets_the_test_family() -> None:
    ledger = DecisionLedger()
    parsed = _publish_completed_research(ledger)
    with pytest.raises(DecisionRefusal):
        ledger.publish_judgment(
            judgment_id="judgment-2",
            research_key=parsed.research_key(),
            run_key=parsed.run_key(),
            family=ResearchFamilyRef.parse(
                {
                    "family_id": "family-a0",
                    "test_family": "test-family-fresh-start",
                    "prior_result_ids": [],
                }
            ),
            state="completed",
        )


def test_prior_results_are_preserved_across_campaigns_rather_than_replaced() -> None:
    ledger = DecisionLedger()
    parsed = _publish_completed_research(ledger)
    ledger.publish_judgment(
        judgment_id="judgment-2",
        research_key=parsed.research_key(),
        run_key=parsed.run_key(),
        family=ResearchFamilyRef.parse(
            {
                "family_id": "family-a0",
                "test_family": "test-family-a0-crossback",
                "prior_result_ids": ["prior-result-2"],
            }
        ),
        state="completed",
    )
    record = ledger.judgment_for(parsed.research_key())
    assert record is not None
    assert record.prior_result_ids == ("prior-result-1", "prior-result-2")
    outcome, _l, _e, engine = _decide(ledger=ledger)
    assert outcome.preserved_prior_result_ids == ("prior-result-1", "prior-result-2")
    assert engine.counts() == (0, 0, 0, 0)


def test_manual_read_only_history_never_reaches_the_engine() -> None:
    ledger = DecisionLedger()
    parsed = _publish_completed_research(ledger)
    engine = RecordingEngine()
    _decide(ledger=ledger, engine=engine)
    history = inspect_decision_history(
        ledger, ExposureLog(), research_key=parsed.research_key(), family_id="family-a0"
    )
    assert history["access"] == "read_only"
    assert history["invokes_engine"] is False
    assert history["reserves_budget"] is False
    assert history["publishes_context"] is False
    assert history["bypasses_duplicate_gate"] is False
    assert history["scanned_full_history"] is False
    assert history["judgment"]["judgment_id"] == "judgment-original"  # type: ignore[index]
    assert engine.counts() == (0, 0, 0, 0)


def test_read_only_history_repeated_never_accumulates_a_spend() -> None:
    ledger = DecisionLedger()
    parsed = _publish_completed_research(ledger)
    exposure = ExposureLog()
    for _ in range(25):
        inspect_decision_history(ledger, exposure, research_key=parsed.research_key())
    assert ledger.export()["decisions"] == []


def test_no_readback_ever_claims_eligibility_or_a_full_history_scan() -> None:
    outcome, ledger, _exposure, _engine = _decide()
    readback = outcome.readback()
    assert readback["grants_eligibility"] is False
    assert readback["fabricates_evidence"] is False
    assert readback["scanned_full_history"] is False
    for judgment in ledger.export()["judgments"]:  # type: ignore[union-attr]
        assert judgment["grants_eligibility"] is False


# --- recovery ---------------------------------------------------------------


def test_a_decision_is_replayed_from_its_frozen_public_record() -> None:
    outcome, _ledger, _exposure, _engine = _decide()
    record = outcome.public_record()
    assert record["schema"] == DECISION_RECORD_SCHEMA
    replayed = reconstruct_decision_outcome(record)
    assert replayed["decision_identity"] == outcome.identity
    assert replayed["replayed_from"] == "frozen_public_record"
    assert replayed["used_latest_query"] is False
    assert replayed["invoked_engine"] is False


def test_a_doctored_decision_record_fails_loudly() -> None:
    outcome, _ledger, _exposure, _engine = _decide()
    for field, value in (
        ("outcome", "stopped_duplicate"),
        ("run_disposition", "reused_run"),
        ("research_disposition", "duplicate_research"),
    ):
        record = outcome.public_record()
        record[field] = value
        with pytest.raises(DecisionRefusal):
            reconstruct_decision_outcome(record)


def test_a_doctored_spend_counter_fails_loudly() -> None:
    outcome, _ledger, _exposure, _engine = _decide()
    record = outcome.public_record()
    record["counters"]["research_engine_calls"] = 0  # type: ignore[index]
    with pytest.raises(DecisionRefusal):
        reconstruct_decision_outcome(record)


def test_a_reordered_call_trace_is_a_different_decision() -> None:
    outcome, _ledger, _exposure, _engine = _decide()
    record = outcome.public_record()
    record["trace"] = list(reversed(record["trace"]))  # type: ignore[arg-type]
    with pytest.raises(DecisionRefusal):
        reconstruct_decision_outcome(record)


def test_recovery_reuses_the_frozen_context_identity_not_a_new_query() -> None:
    ledger = DecisionLedger()
    first, _l, exposure, engine = _decide(ledger=ledger)
    identity = first.context_identity
    assert identity is not None
    second, _l, _e, engine2 = _decide(ledger=ledger, exposure=exposure)
    assert second.outcome == "recovered_existing"
    assert engine2.counts() == (0, 0, 0, 0)
    replayed = reconstruct_decision_outcome(first.public_record())
    assert replayed["decision_identity"] == first.identity
    assert engine.counts() == (1, 1, 1, 1)


# --- malformed declarations -------------------------------------------------


def test_a_malformed_declaration_is_refused() -> None:
    for mutate in (
        lambda value: value.update({"schema": "other"}),
        lambda value: value.update({"intent": "whatever"}),
        lambda value: value.update({"run": _run(terminal_state="unknown")}),
        lambda value: value.update({"run": _run(parameter_digest="not-a-digest")}),
        lambda value: value.update({"budget_request": {"budget_id": "b", "units": 0}}),
        lambda value: value.update({"unexpected": 1}),
    ):
        request = _request()
        mutate(request)
        with pytest.raises(AcceptanceFailure):
            DecisionRequest.parse(request)


def test_a_published_execution_fact_is_never_rewritten() -> None:
    ledger = DecisionLedger()
    parsed = _parsed()
    ledger.publish_run(
        run_id="run-original", run_contract=parsed.run, protocol=parsed.question.protocol
    )
    with pytest.raises(DecisionRefusal):
        ledger.publish_run(
            run_id="run-impostor", run_contract=parsed.run, protocol=parsed.question.protocol
        )


def test_an_invalid_judgment_state_is_refused() -> None:
    ledger = DecisionLedger()
    parsed = _parsed()
    with pytest.raises(DecisionRefusal):
        ledger.publish_judgment(
            judgment_id="judgment-x",
            research_key=parsed.research_key(),
            run_key=parsed.run_key(),
            family=parsed.research_family,
            state="probably_fine",
        )


def test_the_module_opens_no_store_and_makes_no_external_call() -> None:
    from pathlib import Path

    body = Path(__file__).with_name("research_decision.py").read_text(encoding="utf-8")
    for forbidden in ("socket", "sqlite3", "urllib", "requests", "subprocess", "open("):
        assert forbidden not in body, forbidden


# --- Hypothesis: property coverage ------------------------------------------


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    name=st.from_regex(r"\A[a-z][a-z-]{0,20}\Z"),
    intent=st.sampled_from(
        sorted({"initial", "replication", "revalidation", "new_sample", "randomness_experiment"})
    ),
)
def test_no_rename_or_declared_intent_ever_unlocks_a_completed_duplicate(
    name: str, intent: str
) -> None:
    ledger = DecisionLedger()
    _publish_completed_research(ledger)
    request = _request(display_name=name, intent=intent)
    engine = RecordingEngine()
    outcome = decide_research_request(
        request, ledger=ledger, exposure=ExposureLog(), engine=engine
    )
    assert outcome.outcome == "stopped_duplicate"
    assert engine.counts() == (0, 0, 0, 0)


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    field=st.sampled_from(
        sorted(
            {
                "protocol_id",
                "protocol_version",
                "multiplicity_policy",
            }
        )
    ),
    value=st.sampled_from(sorted({"alpha", "beta", "gamma"})),
)
def test_a_protocol_change_never_changes_the_run_key(field: str, value: str) -> None:
    base = _parsed()
    other = _parsed(_request(question=_question(protocol=_protocol(**{field: value}))))
    assert other.run_key() == base.run_key()
    if other.question.protocol.identity() != base.question.protocol.identity():
        assert other.research_key() != base.research_key()


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    data_range=st.sampled_from(
        sorted({"2020-01-01/2024-12-31", "2025-01-01/2025-12-31", "2019-01-01/2019-12-31"})
    ),
    seed_ref=st.sampled_from(sorted({"seed-1", "seed-2", "seed-3"})),
)
def test_every_distinct_execution_input_is_a_distinct_run(
    data_range: str, seed_ref: str
) -> None:
    ledger = DecisionLedger()
    _publish_completed_research(ledger)
    run = _run(
        data_range=data_range,
        randomness={"seed_policy": "fixed", "seed_ref": seed_ref, "replicates": 1},
    )
    request = _request(run=run, intent="new_sample")
    engine = RecordingEngine()
    outcome = decide_research_request(
        request, ledger=ledger, exposure=ExposureLog(), engine=engine
    )
    same_inputs = data_range == "2020-01-01/2024-12-31" and seed_ref == "seed-1"
    if same_inputs:
        assert outcome.outcome == "stopped_duplicate"
        assert engine.counts() == (0, 0, 0, 0)
    else:
        assert outcome.outcome == "proceeded"
        assert outcome.run_disposition == "new_run"
        assert engine.counts() == (1, 1, 1, 1)


@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(repeats=st.integers(min_value=2, max_value=6))
def test_repeating_the_same_action_never_spends_twice(repeats: int) -> None:
    ledger = DecisionLedger()
    exposure = ExposureLog()
    engine = RecordingEngine()
    request = _request()
    outcomes = [
        decide_research_request(request, ledger=ledger, exposure=exposure, engine=engine)
        for _ in range(repeats)
    ]
    assert outcomes[0].outcome == "proceeded"
    assert all(result.outcome == "recovered_existing" for result in outcomes[1:])
    assert engine.counts() == (1, 1, 1, 1)


# --- Hypothesis: the decision state machine ---------------------------------

_SPEND_LIMIT = 1


class ResearchDecisionMachine(RuleBasedStateMachine):
    """Duplicate / new sample / protocol attach / retry / conflict / blocker.

    The machine drives the gate through every branch in arbitrary order and
    holds the invariants that must survive all of them: the trace is always a
    prefix-consistent subsequence of the declared order, a duplicate never
    spends, a reuse never re-executes a run, and the engine is never reached
    without both gates having been passed first.
    """

    def __init__(self) -> None:
        super().__init__()
        self.ledger = DecisionLedger()
        self.exposure = ExposureLog()
        self.engine = RecordingEngine()
        self.outcomes: list[object] = []
        self.spent_keys: set[str] = set()

    def _drive(self, request: dict[str, object]) -> None:
        try:
            outcome = decide_research_request(
                request, ledger=self.ledger, exposure=self.exposure, engine=self.engine
            )
        except AcceptanceFailure:
            # A refused declaration never spends and never records a decision.
            return
        self.outcomes.append(outcome)
        assert list(outcome.trace) == [step for step in DECISION_STEPS if step in outcome.trace]
        if outcome.outcome in {"stopped_duplicate", "blocked_prior_data_blocker"}:
            assert outcome.counters.total_external_calls() == 0
        if outcome.run_disposition in {"reused_run", "attached_run"}:
            assert outcome.counters.runs_executed == 0
        if outcome.counters.research_engine_calls:
            assert "check_visibility" in outcome.trace
            assert "check_required_completeness" in outcome.trace
        if outcome.outcome == "proceeded":
            self.spent_keys.add(outcome.request.research_key())

    @rule(key=st.sampled_from(["idem-1", "idem-2", "idem-3"]))
    def initial_request(self, key: str) -> None:
        request = _request()
        request["key"]["idempotency_key"] = key  # type: ignore[index]
        self._drive(request)

    @rule(key=st.sampled_from(["idem-1", "idem-2", "idem-3"]))
    def conflicting_request(self, key: str) -> None:
        request = _request(run=_run(parameter_digest=_OTHER_PARAMS))
        request["key"]["idempotency_key"] = key  # type: ignore[index]
        self._drive(request)

    @rule(name=st.sampled_from(["study-a", "study-b", "study-c"]))
    def renamed_request(self, name: str) -> None:
        self._drive(_request(display_name=name))

    @rule(protocol=st.sampled_from(["protocol-one-sided", "protocol-two-sided"]))
    def protocol_change(self, protocol: str) -> None:
        request = _request(
            question=_question(protocol=_protocol(protocol_id=protocol)),
            intent="protocol_change",
        )
        request["key"]["idempotency_key"] = f"idem-{protocol}"  # type: ignore[index]
        self._drive(request)

    @rule(data_range=st.sampled_from(["2025-01-01/2025-12-31", "2019-01-01/2019-12-31"]))
    def new_sample(self, data_range: str) -> None:
        request = _request(run=_run(data_range=data_range), intent="new_sample")
        request["key"]["idempotency_key"] = f"idem-{data_range[:4]}"  # type: ignore[index]
        self._drive(request)

    @rule()
    def publish_prior_completed_research(self) -> None:
        _publish_completed_research(self.ledger)

    @rule()
    def read_only_inspection(self) -> None:
        before = self.engine.counts()
        inspect_decision_history(self.ledger, self.exposure)
        assert self.engine.counts() == before

    @invariant()
    def a_research_key_is_never_paid_for_twice(self) -> None:
        proceeded = [
            result.request.research_key()  # type: ignore[attr-defined]
            for result in self.outcomes
            if result.outcome == "proceeded"  # type: ignore[attr-defined]
        ]
        assert len(proceeded) == len(set(proceeded))

    @invariant()
    def the_engine_is_never_called_more_often_than_the_gate_says(self) -> None:
        expected = sum(
            result.counters.research_engine_calls  # type: ignore[attr-defined]
            for result in self.outcomes
        )
        assert len(self.engine.calls) == expected
        assert len(self.engine.runs) == sum(
            result.counters.runs_executed for result in self.outcomes  # type: ignore[attr-defined]
        )


TestResearchDecisionMachine = ResearchDecisionMachine.TestCase
TestResearchDecisionMachine.settings = settings(
    max_examples=25,
    stateful_step_count=12,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)


# --- A0 reference acceptance slice ------------------------------------------
#
# A0-B0-RULES and A0-FIXTURES-ORACLE are still `pending` in
# docs/research/a0/a0_delivery_index.json, so these assert contract shape on
# synthetic #437-shaped stand-ins.  They do not claim a real A0 round.


def test_a0_r01_retry_reconciles_conflict_rejects_and_duplicate_stops() -> None:
    ledger = DecisionLedger()
    exposure = ExposureLog()
    engine = RecordingEngine()
    # 1. First pass spends exactly once.
    first = decide_research_request(_request(), ledger=ledger, exposure=exposure, engine=engine)
    assert first.outcome == "proceeded"
    assert engine.counts() == (1, 1, 1, 1)
    # 2. The same action retried reconciles against the record instead of re-running.
    retry = decide_research_request(_request(), ledger=ledger, exposure=exposure, engine=engine)
    assert retry.outcome == "recovered_existing"
    assert engine.counts() == (1, 1, 1, 1)
    # 3. The same key with a different input is rejected.
    conflict = decide_research_request(
        _request(run=_run(parameter_digest=_OTHER_PARAMS)),
        ledger=ledger,
        exposure=exposure,
        engine=engine,
    )
    assert conflict.outcome == "rejected_key_conflict"
    assert engine.counts() == (1, 1, 1, 1)
    # 4. A genuinely duplicate research question stops before any new spend,
    #    with each side-effect count asserted separately.
    duplicate_ledger = DecisionLedger()
    _publish_completed_research(duplicate_ledger)
    duplicate_engine = RecordingEngine()
    duplicate = decide_research_request(
        _request(),
        ledger=duplicate_ledger,
        exposure=ExposureLog(),
        engine=duplicate_engine,
    )
    assert duplicate.outcome == "stopped_duplicate"
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


def test_a0_r02_attach_new_sample_and_blocker_recovery_stay_separate() -> None:
    ledger = DecisionLedger()
    prior = _publish_completed_research(ledger)
    # V1 same execution input, new statistical protocol -> attach, judge afresh.
    attach_engine = RecordingEngine()
    attach = decide_research_request(
        _request(
            question=_question(protocol=_protocol(protocol_id="protocol-one-sided")),
            intent="protocol_change",
        ),
        ledger=ledger,
        exposure=ExposureLog(),
        engine=attach_engine,
    )
    assert (attach.run_disposition, attach.research_disposition) == (
        "attached_run",
        "new_research",
    )
    assert attach_engine.runs == []
    # V1 legitimate new-sample revalidation is not Genome duplication.
    sample_engine = RecordingEngine()
    sample = decide_research_request(
        _request(run=_run(data_range="2025-01-01/2025-12-31"), intent="revalidation"),
        ledger=DecisionLedger(),
        exposure=ExposureLog(),
        engine=sample_engine,
    )
    assert sample.request.run.genome_id == prior.run.genome_id
    assert sample.research_disposition == "new_research"
    assert sample_engine.counts() == (1, 1, 1, 1)
    # A repaired data blocker follows the original owner's recovery policy.
    blocked_ledger = DecisionLedger()
    _publish_completed_research(
        blocked_ledger, state="blocked_by_data", blocker_id="blocker-gap-2024"
    )
    repair_engine = RecordingEngine()
    repaired = decide_research_request(
        _request(
            intent="blocker_retry",
            blocker_repair={
                "blocker_id": "blocker-gap-2024",
                "new_condition": "vendor-backfill-verified",
                "owner_permitted": True,
                "repair_ref": "record:repair-1",
            },
        ),
        ledger=blocked_ledger,
        exposure=ExposureLog(),
        engine=repair_engine,
    )
    assert repaired.outcome == "proceeded"
    assert repaired.readback()["decisions"]["research_duplication"]["strategy_falsified"] is False
    # The three decision types and the research family stay separate.
    decisions = repaired.readback()["decisions"]
    assert decisions["request_idempotency"]["disposition"] == "new_request"
    assert decisions["run_reuse"]["disposition"] in {"new_run", "reused_run", "attached_run"}
    assert decisions["research_duplication"]["disposition"] == "new_research"
    assert repaired.readback()["research_family"]["test_family"] == "test-family-a0-crossback"


def test_a0_p02_call_ordering_uncertain_delivery_and_frozen_recovery() -> None:
    # New envelope material passes the delivery gate before anything is spent.
    engine = RecordingEngine()
    ledger = DecisionLedger()
    proceeded = decide_research_request(
        _request(), ledger=ledger, exposure=ExposureLog(), engine=engine
    )
    assert proceeded.trace == tuple(
        step for step in DECISION_STEPS if step != "stop_on_research_duplicate"
    )
    assert engine.trace == [
        "publish_context",
        "reserve_budget",
        "execute_run",
        "call_research_engine",
    ]
    # Uncertain delivery is reconciled, never blindly resent.
    exposure = ExposureLog()
    parsed = _parsed()
    exposure.append(_exposure_event("context_prepared", parsed))
    exposure.append(
        _exposure_event(
            "delivery_uncertain",
            parsed,
            uncertainty={
                "reason": "request_timeout",
                "observation": "local_checkpoint",
                "transport": "real_process",
            },
        )
    )
    uncertain_engine = RecordingEngine()
    uncertain = decide_research_request(
        _request(), ledger=DecisionLedger(), exposure=exposure, engine=uncertain_engine
    )
    assert uncertain.outcome == "reconcile_required"
    assert uncertain_engine.counts() == (0, 0, 0, 0)
    # Recovery uses only the original frozen Context and events.
    replayed = reconstruct_decision_outcome(proceeded.public_record())
    assert replayed["decision_identity"] == proceeded.identity
    assert replayed["used_latest_query"] is False
    assert engine.counts() == (1, 1, 1, 1)


def test_a0_the_public_decision_inputs_and_outputs_are_the_submitted_evidence() -> None:
    """B0 stand-in: frozen public inputs, expected outputs, and the counts.

    Expected values are this test's own literals, not read back from the
    implementation, so a change of behaviour shows up here as a diff.
    """

    ledger = DecisionLedger()
    engine = RecordingEngine()
    request = _request()
    parsed = DecisionRequest.parse(request)
    # Frozen public inputs.
    assert parsed.key.action_key().startswith("sha256:")
    assert parsed.run.package_id == "package-a0"
    assert parsed.run.genome_id == "genome-ema-crossback"
    assert parsed.run.data_range == "2020-01-01/2024-12-31"
    assert parsed.question.protocol.protocol_id == "protocol-two-sided"
    assert parsed.budget_request.as_dict() == {"budget_id": "budget-research", "units": 10}
    # Expected outputs for the non-duplicate branch.
    outcome = decide_research_request(
        request, ledger=ledger, exposure=ExposureLog(), engine=engine
    )
    assert outcome.outcome == "proceeded"
    assert outcome.request_disposition == "new_request"
    assert outcome.run_disposition == "new_run"
    assert outcome.research_disposition == "new_research"
    assert outcome.counters.as_dict() == {
        "engine_contexts_published": 1,
        "budget_reservations": 1,
        "runs_executed": 1,
        "research_engine_calls": 1,
        "total_external_calls": 4,
    }
    assert len(outcome.trace) == len(DECISION_STEPS) - 1 == 12


def test_a0_u1_u3_miscall_run_reuse_and_external_call_counts() -> None:
    """The U1-U3 scenario counters #381 asks for, recorded explicitly.

    U1 -- an equivalent failure direction re-proposed under a new name.
    U2 -- a repaired data problem.
    U3 -- a legitimate new-sample revalidation of the same strategy.

    For each: how many *legitimate* requests were wrongly blocked, how many runs
    were reused instead of re-executed, and how many external calls were made.
    """

    counters: dict[str, dict[str, int]] = {}

    # U1: same question, same failure direction, renamed.  Expected: blocked as
    # a duplicate, and that block is correct rather than a miscall.
    u1_ledger = DecisionLedger()
    _publish_completed_research(u1_ledger)
    u1_engine = RecordingEngine()
    u1 = decide_research_request(
        _request(display_name="fresh-sounding-volume-study", intent="replication"),
        ledger=u1_ledger,
        exposure=ExposureLog(),
        engine=u1_engine,
    )
    assert u1.outcome == "stopped_duplicate"
    counters["U1"] = {
        "legitimate_requests": 0,
        "wrongly_blocked": 0,
        "runs_reused": 0,
        "external_calls": sum(u1_engine.counts()),
    }

    # U2: a repaired data blocker with an owner-permitted new condition.  It is
    # legitimate, so blocking it would be a miscall.
    u2_ledger = DecisionLedger()
    _publish_completed_research(u2_ledger, state="blocked_by_data", blocker_id="blocker-gap-2024")
    u2_engine = RecordingEngine()
    u2 = decide_research_request(
        _request(
            intent="blocker_retry",
            blocker_repair={
                "blocker_id": "blocker-gap-2024",
                "new_condition": "vendor-backfill-verified",
                "owner_permitted": True,
                "repair_ref": "record:repair-1",
            },
        ),
        ledger=u2_ledger,
        exposure=ExposureLog(),
        engine=u2_engine,
    )
    counters["U2"] = {
        "legitimate_requests": 1,
        "wrongly_blocked": 0 if u2.outcome == "proceeded" else 1,
        "runs_reused": 1 if u2.run_disposition in {"reused_run", "attached_run"} else 0,
        "external_calls": sum(u2_engine.counts()),
    }

    # U3: the same strategy on a genuinely new sample.  Legitimate; must not be
    # absorbed by the Genome match.
    u3_ledger = DecisionLedger()
    _publish_completed_research(u3_ledger)
    u3_engine = RecordingEngine()
    u3 = decide_research_request(
        _request(run=_run(data_range="2025-01-01/2025-12-31"), intent="revalidation"),
        ledger=u3_ledger,
        exposure=ExposureLog(),
        engine=u3_engine,
    )
    counters["U3"] = {
        "legitimate_requests": 1,
        "wrongly_blocked": 0 if u3.outcome == "proceeded" else 1,
        "runs_reused": 1 if u3.run_disposition in {"reused_run", "attached_run"} else 0,
        "external_calls": sum(u3_engine.counts()),
    }

    assert counters == {
        "U1": {
            "legitimate_requests": 0,
            "wrongly_blocked": 0,
            "runs_reused": 0,
            "external_calls": 0,
        },
        "U2": {
            "legitimate_requests": 1,
            "wrongly_blocked": 0,
            "runs_reused": 0,
            "external_calls": 4,
        },
        "U3": {
            "legitimate_requests": 1,
            "wrongly_blocked": 0,
            "runs_reused": 0,
            "external_calls": 4,
        },
    }
    # The attach case is the one that reuses a run without re-executing it.
    attach_ledger = DecisionLedger()
    _publish_completed_research(attach_ledger)
    attach_engine = RecordingEngine()
    attach = decide_research_request(
        _request(
            question=_question(protocol=_protocol(protocol_id="protocol-one-sided")),
            intent="protocol_change",
        ),
        ledger=attach_ledger,
        exposure=ExposureLog(),
        engine=attach_engine,
    )
    assert attach.run_disposition == "attached_run"
    assert attach_engine.counts() == (1, 1, 0, 1)


def test_a0_run_and_protocol_helpers_stay_publicly_constructible() -> None:
    contract = RunContract.parse(_run())
    protocol = StatisticalProtocol.parse(_protocol())
    assert contract.qualifies_for_reuse is True
    assert RunContract.parse(_run(terminal_state="blocked")).qualifies_for_reuse is False
    assert protocol.identity().startswith("sha256:")
    assert "protocol_id" not in contract.contract_dict()
