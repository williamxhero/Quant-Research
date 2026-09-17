"""Consumer-side tests for source corrections, formal currency and the Reporting projection."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from .core import AcceptanceFailure
from .research_context import (
    BRIEF_TEMPLATE_ID,
    CONTEXT_DECLARATION_SCHEMA,
    freeze_research_context,
)
from .research_currency import (
    CURRENCY_REFRESH_SCHEMA,
    CURRENCY_STATE_CONTRACT,
    CURRENCY_STATE_CONTRACT_DIGEST,
    CURRENCY_STATE_CONTRACT_ID,
    CURRENCY_STATE_CONTRACT_VERSION,
    CURRENCY_STATES,
    CURRENCY_VIEW_SCHEMA,
    IMPACT_STATES,
    REPORTING_DECLARATION_SCHEMA,
    REPORTING_READBACK_SCHEMA,
    REPORTING_RECORD_SCHEMA,
    CurrencyRefusal,
    SourceCurrencyView,
    assess_correction_impact,
    deliver_reporting_projection,
    freeze_reporting_projection,
    read_source_currency,
    reconstruct_reporting_projection,
    refresh_formal_currency,
)
from .research_visibility import VISIBILITY_REQUEST_SCHEMA

_OLD_CUTOFF = "2026-09-10T00:00:00Z"
_NEW_CUTOFF = "2026-09-30T00:00:00Z"
_CORRECTION_KNOWN_AT = "2026-09-20T00:00:00Z"
#: The corrected fact applies to 2019 data.  It is deliberately far older than
#: either cutoff, so applicability time and system-known time cannot be confused.
_CORRECTION_APPLIES_AT = "2019-01-01T00:00:00Z"


# --- #397 Context fixtures ----------------------------------------------------


def _source(
    source_id: str,
    *,
    approved: bool = True,
    applicable: bool = True,
    published_at: str = "2026-09-01T00:00:00Z",
) -> dict[str, object]:
    return {
        "source_id": source_id,
        "record_type": "finding",
        "approved": approved,
        "applicable": applicable,
        "retrieval": "ok",
        "published_at": published_at,
        "provenance_ref": f"record:{source_id}",
        "content_digest": "sha256:" + "1" * 64,
        "derived_from": [],
    }


def _declaration(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": CONTEXT_DECLARATION_SCHEMA,
        "mode": "current_research",
        "purpose": "research-brief",
        "query_scope": {
            "campaign_id": "campaign-a0",
            "iteration_id": "iteration-1",
            "question_id": "question-ema-crossback",
            "ordering": "ordering:frozen-v1",
            "trimming": "trimming:unit-atomic-v1",
        },
        "snapshot": {
            "snapshot_id": "snapshot-2026-09-10",
            "knowledge_cutoff": _OLD_CUTOFF,
            "corrections_version": "corrections-v3",
        },
        "policy": {
            "policy_id": "research-policy",
            "policy_version": "v2",
            "template_id": BRIEF_TEMPLATE_ID,
            "template_version": "v1",
        },
        "budget": {"discussion_budget": 32, "closure_budget": 16},
        "required_closure": ["support-1", "counter-1"],
        "optional_scope": {"source_ids": ["experience-1"], "exhausted": True},
        "sources": [_source("support-1"), _source("counter-1"), _source("experience-1")],
        "owner_facts": {
            "current_candidate": {"value": "candidate-v1", "provenance": ["record:candidate-v1"]},
            "current_genome": {"value": "genome-ema-crossback", "provenance": ["record:genome-1"]},
            "baseline_condition": {"value": "baseline-v0", "provenance": ["record:baseline-v0"]},
            "comparison_condition": {
                "value": "comparison-v0-vs-v1",
                "provenance": ["record:compare-v0-v1"],
            },
            "key_disagreements": {
                "values": ["disagreement-turnover"],
                "provenance": ["record:disagreement-turnover"],
            },
            "reusable_assets": {
                "values": ["package-a0", "run-1"],
                "provenance": ["record:package-a0", "record:run-1"],
            },
        },
        "evidence_gaps": [
            {
                "gap_id": "gap-holdout-untouched",
                "provenance_ref": "record:gap-1",
                "preconditions": ["approval:holdout-read"],
            }
        ],
        "candidate_next_steps": [
            {
                "step_id": "step-align-cost",
                "provenance_ref": "record:gap-1",
                "preconditions": ["approval:owner", "data:cost-model-aligned"],
            }
        ],
        "conclusions": [
            {
                "conclusion_id": "conclusion-1",
                "statement_ref": "record:statement-1",
                "required_support": ["support-1"],
                "required_counter_evidence": ["counter-1"],
                "limitations": [],
                "optional": False,
            }
        ],
        "genome_compare": {
            "semantic_path": "genome:filter/volume-contraction",
            "change_category": "single_component",
            "verified_unchanged_scope": ["scope:universe", "scope:signal-core"],
            "alignment": {"cost": "aligned", "data": "aligned", "execution": "unknown"},
            "provenance_ref": "record:genome-compare-1",
        },
        "visibility_request": None,
    }
    value.update(overrides)
    return value


def _visibility_request(
    *,
    purpose: str = "research-brief",
    authorized: bool = True,
    source_ids: tuple[str, ...] = ("support-1", "counter-1", "experience-1"),
) -> dict[str, object]:
    granted_purpose = purpose if authorized else "some-other-purpose"
    return {
        "schema": VISIBILITY_REQUEST_SCHEMA,
        "stage": "historical_redelivery",
        "mode": "strict",
        "consumer": {
            "actor_id": "actor-1",
            "consumer": "reporting",
            "action": "read_projection",
            "purpose": purpose,
            "capabilities": ["cap.research"],
            "authorization_policy_id": "auth-policy",
            "authorization_policy_version": "v1",
            "authorization_knowledge_cutoff": _NEW_CUTOFF,
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
            "knowledge_cutoff": _NEW_CUTOFF,
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


# --- currency / lineage fixtures ---------------------------------------------


def _node(
    statement_id: str,
    *,
    depends_on: list[dict[str, object]] | None = None,
    conditions_known: bool = True,
    conditions: list[str] | None = None,
) -> dict[str, object]:
    return {
        "statement_id": statement_id,
        "record_type": "finding",
        "depends_on": depends_on or [],
        "conditions": {
            "known": conditions_known,
            "values": sorted(conditions or []) if conditions_known else [],
        },
    }


def _edge(statement_id: str, *, known: bool = True) -> dict[str, object]:
    return {"statement_id": statement_id, "relationship": "derived_from", "known": known}


def _lineage(*, complete: bool = True) -> dict[str, object]:
    """data-1 -> support-1 -> counter-1 is the multi-hop chain under test."""

    return {
        "complete": complete,
        "nodes": [
            _node("data-1", conditions=["cond:cn-a"]),
            _node("support-1", depends_on=[_edge("data-1")], conditions=["cond:cn-a"]),
            _node("counter-1", depends_on=[_edge("support-1")], conditions=["cond:cn-a"]),
            _node("experience-1", conditions=["cond:cn-a"]),
        ],
    }


def _correction(
    correction_id: str = "correction-1",
    *,
    target: str = "data-1",
    system_known_at: str = _CORRECTION_KNOWN_AT,
    precise_conditions: list[str] | None = None,
) -> dict[str, object]:
    return {
        "correction_id": correction_id,
        "target_statement_id": target,
        "kind": "data",
        "applicable_at": _CORRECTION_APPLIES_AT,
        "system_known_at": system_known_at,
        "provenance_ref": f"record:{correction_id}",
        "precise_conditions": sorted(precise_conditions or []),
    }


def _fact(
    fact_id: str,
    statement_id: str,
    state: str,
    *,
    system_known_at: str = _CORRECTION_KNOWN_AT,
) -> dict[str, object]:
    return {
        "fact_id": fact_id,
        "statement_id": statement_id,
        "state": state,
        "applicable_at": _CORRECTION_APPLIES_AT,
        "system_known_at": system_known_at,
        "owner_evidence_ref": f"record:owner-evidence-{fact_id}",
        "provenance_ref": f"record:{fact_id}",
    }


def _view(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": CURRENCY_VIEW_SCHEMA,
        "lineage": _lineage(),
        "corrections": [_correction()],
        "currency_facts": [
            _fact("fact-1", "data-1", "superseded"),
            _fact("fact-2", "support-1", "revalidation_due"),
        ],
    }
    value.update(overrides)
    return value


class _ReadModel:
    """A stand-in for the owner-published read model that lives outside this repo."""

    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload
        self.calls: list[str] = []

    def lineage(self) -> dict[str, object]:
        self.calls.append("lineage")
        return self._payload["lineage"]  # type: ignore[return-value]

    def corrections(self) -> list[dict[str, object]]:
        self.calls.append("corrections")
        return self._payload["corrections"]  # type: ignore[return-value]

    def currency_facts(self) -> list[dict[str, object]]:
        self.calls.append("currency_facts")
        return self._payload["currency_facts"]  # type: ignore[return-value]


def _exposure(
    context_identity: str,
    *,
    replay_coverage: str = "limited",
    content_ref: str | None = None,
) -> dict[str, object]:
    return {
        "action_key": "sha256:" + "a" * 64,
        "context_identity": context_identity,
        "envelope_digest": "sha256:" + "b" * 64,
        "envelope_content_ref": content_ref,
        "replay_coverage": replay_coverage,
        "provider_request_id": "provider-request-1",
        "template_version": "template-v1",
        "tool_input_version": "tool-input-v1",
        "receipt_ref": "receipt-1",
        "response_ref": "response-1",
    }


def _projection(**overrides: object) -> dict[str, object]:
    context = freeze_research_context(_declaration())
    value: dict[str, object] = {
        "schema": REPORTING_DECLARATION_SCHEMA,
        "context_record": context.public_record(),
        "currency": _view(),
        "knowledge_cutoff": _NEW_CUTOFF,
        "correction_id": "correction-1",
        "exposure": _exposure(context.identity),
    }
    value.update(overrides)
    return value


# --- Criterion 1: potential impact, never blanket invalidation ---------------


def test_a_correction_locates_multi_hop_potential_impact_over_the_public_lineage() -> None:
    view = SourceCurrencyView.parse(_view())
    assessment = assess_correction_impact(view, "correction-1")
    # data-1 -> support-1 -> counter-1 is two hops; all three are located.
    assert assessment.by_state("potentially_affected") == ("counter-1", "data-1", "support-1")
    assert assessment.by_state("not_affected") == ("experience-1",)
    assert assessment.by_state("needs_review") == ()
    assert assessment.as_dict()["invalidates_downstream"] is False
    assert assessment.as_dict()["blanket_invalidation"] is False
    assert assessment.as_dict()["traversal"] == "bounded_explicit_stack_dfs"


def test_an_unknown_dependency_is_needs_review_and_never_invalidates_downstream() -> None:
    lineage = _lineage()
    lineage["nodes"][2]["depends_on"] = [_edge("support-1", known=False)]
    view = SourceCurrencyView.parse(_view(lineage=lineage))
    assessment = assess_correction_impact(view, "correction-1")
    assert "counter-1" in assessment.by_state("needs_review")
    assert "unknown_dependency" in assessment.codes
    # The uncertainty never becomes an invalidation, and never spreads to
    # everything: experience-1 is untouched.
    assert "invalidated" not in {state for _id, state in assessment.states}
    assert assessment.by_state("not_affected") == ("experience-1",)


def test_needs_review_travels_downstream_but_stays_needs_review() -> None:
    lineage = _lineage()
    lineage["nodes"][1]["depends_on"] = [_edge("data-1", known=False)]
    lineage["nodes"].append(
        _node("derived-1", depends_on=[_edge("counter-1")], conditions=["cond:cn-a"])
    )
    view = SourceCurrencyView.parse(_view(lineage=lineage))
    assessment = assess_correction_impact(view, "correction-1")
    assert set(assessment.by_state("needs_review")) == {"support-1", "counter-1", "derived-1"}
    assert assessment.by_state("potentially_affected") == ("data-1",)


def test_precise_owner_conditions_narrow_the_affected_scope() -> None:
    lineage = _lineage()
    lineage["nodes"][1]["conditions"] = {"known": True, "values": ["cond:hk"]}
    view = SourceCurrencyView.parse(
        _view(lineage=lineage, corrections=[_correction(precise_conditions=["cond:cn-a"])])
    )
    assessment = assess_correction_impact(view, "correction-1")
    assert "support-1" in assessment.by_state("not_affected")
    # Impact does not travel through a statement the owner's conditions exclude.
    assert "counter-1" in assessment.by_state("not_affected")


def test_a_statement_with_unknown_conditions_is_needs_review_not_excluded() -> None:
    lineage = _lineage()
    lineage["nodes"][1]["conditions"] = {"known": False, "values": []}
    view = SourceCurrencyView.parse(
        _view(lineage=lineage, corrections=[_correction(precise_conditions=["cond:cn-a"])])
    )
    assessment = assess_correction_impact(view, "correction-1")
    assert "support-1" in assessment.by_state("needs_review")


def test_an_incomplete_graph_downgrades_not_affected_rather_than_asserting_it() -> None:
    view = SourceCurrencyView.parse(_view(lineage=_lineage(complete=False)))
    assessment = assess_correction_impact(view, "correction-1")
    assert assessment.by_state("not_affected") == ()
    assert "experience-1" in assessment.by_state("needs_review")
    assert "lineage_graph_not_declared_complete" in assessment.codes
    assert assessment.graph_complete is False


def test_an_edge_to_an_undeclared_node_is_graph_incomplete_and_needs_review() -> None:
    lineage = _lineage()
    lineage["nodes"][3]["depends_on"] = [_edge("data-1"), _edge("ghost-1")]
    view = SourceCurrencyView.parse(_view(lineage=lineage))
    assessment = assess_correction_impact(view, "correction-1")
    assert "lineage_graph_incomplete" in assessment.codes
    assert assessment.graph_complete is False
    assert "invalidated" not in {state for _id, state in assessment.states}


def test_an_exhausted_impact_budget_is_needs_review_not_a_clean_answer() -> None:
    view = SourceCurrencyView.parse(_view())
    assessment = assess_correction_impact(view, "correction-1", budget=1)
    assert "impact_budget_exhausted" in assessment.codes
    assert assessment.by_state("not_affected") == ()


def test_a_cyclic_public_lineage_terminates_without_inventing_an_invalidation() -> None:
    lineage = _lineage()
    lineage["nodes"][0]["depends_on"] = [_edge("counter-1")]
    view = SourceCurrencyView.parse(_view(lineage=lineage))
    assessment = assess_correction_impact(view, "correction-1")
    assert set(assessment.by_state("potentially_affected")) == {
        "data-1",
        "support-1",
        "counter-1",
    }


def test_a_correction_target_outside_the_public_lineage_is_needs_review() -> None:
    view = SourceCurrencyView.parse(_view(corrections=[_correction(target="offgraph-1")]))
    assessment = assess_correction_impact(view, "correction-1")
    assert assessment.by_state("needs_review") == (
        "counter-1",
        "data-1",
        "experience-1",
        "offgraph-1",
        "support-1",
    )
    assert "correction_target_not_in_public_lineage" in assessment.codes


def test_the_impact_walk_is_the_declared_graph_not_the_declaration_order() -> None:
    lineage = _lineage()
    shuffled = deepcopy(lineage)
    shuffled["nodes"] = list(reversed(shuffled["nodes"]))
    for node in shuffled["nodes"]:
        # A repeated edge is an allowed-equivalent spelling of the same graph.
        node["depends_on"] = node["depends_on"] * 2
    base = assess_correction_impact(
        SourceCurrencyView.parse(_view(lineage=lineage)), "correction-1"
    )
    other = assess_correction_impact(
        SourceCurrencyView.parse(_view(lineage=shuffled)), "correction-1"
    )
    assert base.states == other.states


# --- Criterion 2: only owner evidence refreshes formal currency ---------------


def test_only_owner_evidence_or_decision_refreshes_formal_currency() -> None:
    view = SourceCurrencyView.parse(_view())
    for basis in ("owner_evidence", "owner_decision"):
        outcome = refresh_formal_currency(
            view,
            {
                "schema": CURRENCY_REFRESH_SCHEMA,
                "statement_id": "support-1",
                "basis": basis,
                "proposed_state": "current",
                "owner_evidence_ref": "record:owner-evidence-new",
                "system_known_at": _NEW_CUTOFF,
            },
        )
        assert outcome.refreshed is True
        assert outcome.resulting_state == "current"
        assert outcome.as_dict()["grants_eligibility"] is False


def test_a_new_summary_or_explanation_never_refreshes_formal_currency() -> None:
    view = SourceCurrencyView.parse(_view())
    for basis in ("summary", "explanation", "discovery_only_review"):
        outcome = refresh_formal_currency(
            view,
            {
                "schema": CURRENCY_REFRESH_SCHEMA,
                "statement_id": "support-1",
                "basis": basis,
                "proposed_state": "current",
                "owner_evidence_ref": "record:owner-evidence-new",
                "system_known_at": _NEW_CUTOFF,
            },
        )
        assert outcome.refreshed is False
        assert outcome.reason == f"{basis}_is_not_owner_evidence"
        # The owner's existing state is what is reported back, unchanged.
        assert outcome.resulting_state == "revalidation_due"


def test_an_owner_decision_without_evidence_does_not_refresh() -> None:
    view = SourceCurrencyView.parse(_view())
    outcome = refresh_formal_currency(
        view,
        {
            "schema": CURRENCY_REFRESH_SCHEMA,
            "statement_id": "support-1",
            "basis": "owner_decision",
            "proposed_state": "current",
            "owner_evidence_ref": None,
            "system_known_at": _NEW_CUTOFF,
        },
    )
    assert outcome.refreshed is False
    assert outcome.reason == "owner_evidence_ref_missing"


def test_the_currency_state_contract_is_frozen_and_versioned() -> None:
    assert CURRENCY_STATES == (
        "current",
        "revalidation_due",
        "stale",
        "superseded",
        "invalidated",
        "unknown",
    )
    assert CURRENCY_STATE_CONTRACT_ID == "quant-research.research-currency-state"
    assert CURRENCY_STATE_CONTRACT_VERSION == "v1"
    assert CURRENCY_STATE_CONTRACT_DIGEST.startswith("sha256:")
    usable = {state for state, flag, _d in CURRENCY_STATE_CONTRACT if flag}
    assert usable == {"current", "revalidation_due"}


def test_an_impact_assessment_never_refreshes_currency() -> None:
    view = SourceCurrencyView.parse(_view())
    before = view.status("support-1").as_dict()
    assess_correction_impact(view, "correction-1")
    assert view.status("support-1").as_dict() == before
    assert assess_correction_impact(view, "correction-1").as_dict()[
        "refreshes_formal_currency"
    ] is False


def test_the_old_context_keeps_its_identity_and_policy_after_a_correction() -> None:
    context = freeze_research_context(_declaration())
    before = context.readback()
    view = SourceCurrencyView.parse(_view(corrections=[]))
    after_view = view.append_correction(_correction())
    assert view.corrections == ()
    assert len(after_view.corrections) == 1
    assert context.readback() == before
    assert freeze_research_context(_declaration()).identity == context.identity


# --- Criterion 3: history is never contaminated by hindsight -----------------


def test_a_correction_published_later_is_invisible_to_an_older_cutoff() -> None:
    view = SourceCurrencyView.parse(_view())
    assert view.as_of(_OLD_CUTOFF).corrections == ()
    assert view.as_of(_OLD_CUTOFF).currency_facts == ()
    assert len(view.as_of(_NEW_CUTOFF).corrections) == 1
    # The corrected fact applies to 2019 -- far before the old cutoff -- so only
    # the system-known time can be what hides it.
    assert view.corrections[0].applicable_at < _OLD_CUTOFF
    assert view.corrections[0].system_known_at > _OLD_CUTOFF


def test_an_old_snapshot_projection_shows_no_hindsight_and_a_new_one_does() -> None:
    historical = freeze_reporting_projection(
        _projection(knowledge_cutoff=_OLD_CUTOFF, correction_id=None)
    )
    current = freeze_reporting_projection(_projection())
    assert historical.readback()["published_corrections"] == []
    assert historical.readback()["correction_impact"] is None
    assert [
        entry["correction_id"] for entry in current.readback()["published_corrections"]
    ] == ["correction-1"]
    # Same Context, two knowledge cutoffs, two different projections.
    assert historical.context.identity == current.context.identity
    assert historical.identity != current.identity


def test_the_system_known_time_is_published_and_independently_verifiable() -> None:
    projection = freeze_reporting_projection(_projection())
    published = projection.readback()["published_corrections"][0]
    assert published["system_known_at"] == _CORRECTION_KNOWN_AT
    assert published["applicable_at"] == _CORRECTION_APPLIES_AT
    status = next(
        entry
        for entry in projection.readback()["source_currency"]
        if entry["statement_id"] == "support-1"
    )
    assert status["as_known_at"] == _CORRECTION_KNOWN_AT
    assert status["provenance"] == ["record:fact-2"]


def test_a_projection_cannot_cite_a_correction_its_cutoff_cannot_see() -> None:
    with pytest.raises(CurrencyRefusal):
        freeze_reporting_projection(
            _projection(knowledge_cutoff=_OLD_CUTOFF, correction_id="correction-1")
        )


def test_a_known_invalidated_conclusion_is_not_presented_as_current_evidence() -> None:
    view = _view(
        currency_facts=[
            _fact("fact-1", "support-1", "invalidated"),
            _fact("fact-2", "counter-1", "current"),
        ]
    )
    readback = freeze_reporting_projection(_projection(currency=view)).readback()
    assert readback["unusable_as_current_evidence"] == ["experience-1", "support-1"]
    states = {entry["statement_id"]: entry for entry in readback["source_currency"]}
    assert states["support-1"]["usable_as_current_evidence"] is False
    assert states["counter-1"]["usable_as_current_evidence"] is True
    # A statement the owner never published a fact about is unknown, not current.
    assert states["experience-1"]["state"] == "unknown"
    assert states["experience-1"]["provenance"] == ["unknown"]


def test_the_latest_owner_fact_wins_by_system_known_time() -> None:
    view = SourceCurrencyView.parse(
        _view(
            currency_facts=[
                _fact("fact-1", "support-1", "current", system_known_at="2026-09-15T00:00:00Z"),
                _fact("fact-2", "support-1", "stale", system_known_at="2026-09-25T00:00:00Z"),
            ]
        )
    )
    assert view.status("support-1").state == "stale"
    assert view.as_of("2026-09-20T00:00:00Z").status("support-1").state == "current"


# --- Criterion 4: current authorization, and a refusal that rewrites nothing --


def test_a_currently_unauthorized_reader_cannot_re_read_via_the_old_policy() -> None:
    projection = freeze_reporting_projection(_projection())
    allowed = deliver_reporting_projection(projection, _visibility_request())
    assert allowed["delivery"] == "delivered"
    assert allowed["projection_identity"] == projection.identity
    denied = deliver_reporting_projection(projection, _visibility_request(authorized=False))
    assert denied == {
        "schema": REPORTING_READBACK_SCHEMA,
        "delivery": "blocked",
        "reason": "current_authorization_denied",
        "projection_identity": None,
        "grants_eligibility": False,
    }


def test_a_restricted_response_leaks_no_counts_reasons_or_identifiers() -> None:
    projection = freeze_reporting_projection(_projection())
    denied = deliver_reporting_projection(projection, _visibility_request(authorized=False))
    body = json.dumps(denied)
    for leak in (
        "support-1",
        "counter-1",
        "experience-1",
        "correction-1",
        "genome",
        "baseline",
        projection.identity,
        projection.context.identity,
    ):
        assert leak not in body
    assert not any(
        isinstance(value, int) and not isinstance(value, bool)
        for value in denied.values()
    )


def test_a_restricted_response_does_not_rewrite_the_original_objects() -> None:
    projection = freeze_reporting_projection(_projection())
    before_projection = projection.readback()
    before_context = projection.context.readback()
    before_record = projection.public_record()
    deliver_reporting_projection(projection, _visibility_request(authorized=False))
    assert projection.readback() == before_projection
    assert projection.context.readback() == before_context
    assert projection.public_record() == before_record


def test_revoking_access_after_a_delivery_blocks_the_next_one() -> None:
    projection = freeze_reporting_projection(_projection())
    assert deliver_reporting_projection(projection, _visibility_request())["delivery"] == (
        "delivered"
    )
    revoked = _visibility_request()
    revoked["consumer"]["grants"] = []  # type: ignore[index]
    assert deliver_reporting_projection(projection, revoked)["delivery"] == "blocked"
    # The old, still-valid request does not become a second key to the same door
    # for a consumer whose grants were revoked; each delivery is decided afresh.
    assert deliver_reporting_projection(projection, revoked)["projection_identity"] is None


# --- Criterion 5: Reporting displays, it never computes ----------------------


def test_reporting_shows_only_already_published_material() -> None:
    projection = freeze_reporting_projection(_projection())
    readback = projection.readback()
    assert readback["schema"] == REPORTING_READBACK_SCHEMA
    assert readback["template_id"] == BRIEF_TEMPLATE_ID
    assert readback["published_brief"] == projection.context.brief.as_dict()
    assert readback["context"]["context_identity"] == projection.context.identity
    for key in ("baseline_condition", "comparison_condition", "key_disagreements"):
        assert key in readback["published_brief"]["fields"]


def test_reporting_never_recomputes_metrics_independence_conflicts_or_a_genome_diff() -> None:
    projection = freeze_reporting_projection(_projection())
    guarantees = projection.readback()["reporting_guarantees"]
    for flag in (
        "recomputes_metrics",
        "recomputes_independence",
        "recomputes_conflicts",
        "recomputes_eligibility",
        "recomputes_genome_diff",
        "traverses_private_graph",
        "refreshes_formal_currency",
        "grants_eligibility",
        "invalidates_downstream",
        "scanned_full_history",
    ):
        assert guarantees[flag] is False
    assert guarantees["mlflow_deployment"] == "none"
    # The comparison is the owner's published record, byte for byte.
    declared = _declaration()["genome_compare"]
    shown = projection.readback()["genome_compare"]
    assert shown["semantic_path"] == declared["semantic_path"]  # type: ignore[index]
    assert shown["change_category"] == declared["change_category"]  # type: ignore[index]
    assert shown["alignment"] == declared["alignment"]  # type: ignore[index]


def test_every_gap_and_candidate_step_carries_an_owner_source_or_unknown() -> None:
    projection = freeze_reporting_projection(_projection())
    readback = projection.readback()
    for section in ("evidence_gaps", "candidate_next_steps", "coverage_limitations"):
        entries = readback[section]["entries"]
        assert entries
        for entry in entries:
            assert entry["provenance"]
            assert all(isinstance(ref, str) and ref for ref in entry["provenance"])
    steps = readback["candidate_next_steps"]["entries"]
    assert steps[0]["status"] == "suggestion_pending_approval"
    assert steps[0]["execution_preconditions"] == ["approval:owner", "data:cost-model-aligned"]


def test_a_digest_is_never_presented_as_the_delivered_content() -> None:
    limited = freeze_reporting_projection(_projection()).readback()["exposure"]
    assert limited["replay_coverage"] == "limited"
    assert limited["full_content_available"] is False
    assert limited["digest_is_not_content"] is True
    full = freeze_reporting_projection(
        _projection(
            exposure=_exposure(
                freeze_research_context(_declaration()).identity,
                replay_coverage="full",
                content_ref="store:envelope-1",
            )
        )
    ).readback()["exposure"]
    assert full["full_content_available"] is True
    assert full["digest_is_not_content"] is True


def test_full_replay_coverage_cannot_be_declared_without_a_stored_envelope() -> None:
    context = freeze_research_context(_declaration())
    with pytest.raises(CurrencyRefusal):
        freeze_reporting_projection(
            _projection(exposure=_exposure(context.identity, replay_coverage="full"))
        )


def test_the_exposure_link_must_name_the_projected_context() -> None:
    with pytest.raises(CurrencyRefusal):
        freeze_reporting_projection(_projection(exposure=_exposure("sha256:" + "c" * 64)))


def test_the_projection_surfaces_the_real_context_envelope_and_replay_linkage() -> None:
    projection = freeze_reporting_projection(_projection())
    exposure = projection.readback()["exposure"]
    assert exposure["context_identity"] == projection.context.identity
    assert exposure["provider_request_id"] == "provider-request-1"
    assert exposure["template_version"] == "template-v1"
    assert exposure["tool_input_version"] == "tool-input-v1"
    assert exposure["receipt_ref"] == "receipt-1"
    assert exposure["response_ref"] == "response-1"


def test_the_module_opens_no_store_and_makes_no_external_call() -> None:
    from pathlib import Path

    source = (Path(__file__).parent / "research_currency.py").read_text(encoding="utf-8")
    for forbidden in ("socket", "sqlite3", "urllib", "requests", "subprocess", "open("):
        assert forbidden not in source
    # NetworkX and MLflow appear only in prose, to record that neither is used
    # nor deployed here: there is no import of either, and no call into either.
    imports = [line for line in source.splitlines() if line.startswith(("import ", "from "))]
    assert not any("networkx" in line or "mlflow" in line for line in imports)
    assert "networkx." not in source
    assert "mlflow." not in source
    assert '"mlflow_deployment": "none"' in source


# --- Criterion 6: rebuildable from public facts alone ------------------------


def test_a_projection_is_rebuilt_from_its_public_record_alone() -> None:
    projection = freeze_reporting_projection(_projection())
    record = projection.public_record()
    assert record["schema"] == REPORTING_RECORD_SCHEMA
    rebuilt = reconstruct_reporting_projection(json.loads(json.dumps(record)))
    assert rebuilt.identity == projection.identity
    assert rebuilt.readback() == projection.readback()


def test_deleting_the_display_projection_loses_nothing() -> None:
    projection = freeze_reporting_projection(_projection())
    record = json.loads(json.dumps(projection.public_record()))
    del projection  # the display object is gone; only public facts remain
    rebuilt = reconstruct_reporting_projection(record)
    assert rebuilt.readback()["correction_impact"]["potentially_affected"] == [
        "counter-1",
        "data-1",
        "support-1",
    ]


def test_a_doctored_projection_record_fails_loudly() -> None:
    projection = freeze_reporting_projection(_projection())
    record = json.loads(json.dumps(projection.public_record()))
    record["declaration"]["knowledge_cutoff"] = "2026-10-01T00:00:00Z"
    with pytest.raises(CurrencyRefusal):
        reconstruct_reporting_projection(record)


def test_the_read_model_seam_is_consumed_once_and_then_frozen() -> None:
    model = _ReadModel(deepcopy(_view()))
    view = read_source_currency(model)
    assert model.calls == ["lineage", "corrections", "currency_facts"]
    assert view.as_dict() == SourceCurrencyView.parse(_view()).as_dict()
    projection = freeze_reporting_projection(_projection(currency=view.as_dict()))
    # Everything downstream reads the frozen view; the seam is not called again.
    projection.readback()
    assert model.calls == ["lineage", "corrections", "currency_facts"]


def test_appending_the_same_correction_twice_is_refused() -> None:
    view = SourceCurrencyView.parse(_view())
    with pytest.raises(CurrencyRefusal):
        view.append_correction(_correction())


def test_malformed_declarations_are_refused() -> None:
    with pytest.raises(CurrencyRefusal):
        SourceCurrencyView.parse({**_view(), "schema": "other"})
    with pytest.raises(CurrencyRefusal):
        SourceCurrencyView.parse(
            _view(currency_facts=[_fact("fact-1", "support-1", "made-up-state")])
        )
    with pytest.raises(CurrencyRefusal):
        SourceCurrencyView.parse(_view(corrections=[_correction(), _correction()]))
    with pytest.raises(CurrencyRefusal):
        freeze_reporting_projection({**_projection(), "schema": "other"})
    with pytest.raises(AcceptanceFailure):
        SourceCurrencyView.parse(
            _view(
                lineage={
                    "complete": True,
                    "nodes": [_node("a"), _node("a")],
                }
            )
        )


# --- Hypothesis coverage -----------------------------------------------------

_STATEMENTS = ("data-1", "support-1", "counter-1", "experience-1", "derived-1")


@st.composite
def _graphs(draw: st.DrawFn) -> dict[str, object]:
    names = list(_STATEMENTS)
    nodes: list[dict[str, object]] = []
    for index, name in enumerate(names):
        edges: list[dict[str, object]] = []
        for parent in names[:index]:
            if draw(st.booleans()):
                edges.append(_edge(parent, known=draw(st.booleans())))
        known = draw(st.booleans())
        conditions = draw(st.lists(st.sampled_from(["cond:cn-a", "cond:hk"]), unique=True))
        nodes.append(
            _node(name, depends_on=edges, conditions_known=known, conditions=conditions)
        )
    return {"complete": draw(st.booleans()), "nodes": nodes}


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    graph=_graphs(),
    target=st.sampled_from(_STATEMENTS),
    precise=st.lists(st.sampled_from(["cond:cn-a", "cond:hk"]), unique=True),
    budget=st.integers(min_value=1, max_value=64),
)
def test_impact_is_always_one_of_three_states_and_never_an_invalidation(
    graph: dict[str, object],
    target: str,
    precise: list[str],
    budget: int,
) -> None:
    view = SourceCurrencyView.parse(
        _view(lineage=graph, corrections=[_correction(target=target, precise_conditions=precise)])
    )
    assessment = assess_correction_impact(view, "correction-1", budget=budget)
    assert {state for _id, state in assessment.states} <= set(IMPACT_STATES)
    assert assessment.as_dict()["invalidates_downstream"] is False
    # An honest "not affected" is only ever claimed on a provably complete graph
    # that the walk finished.
    if assessment.by_state("not_affected"):
        assert assessment.graph_complete
        assert "impact_budget_exhausted" not in assessment.codes
    # The target itself is always located.
    assert dict(assessment.states)[target] in {"potentially_affected", "needs_review"}


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    graph=_graphs(),
    target=st.sampled_from(_STATEMENTS),
    known_at=st.sampled_from(
        ["2026-09-05T00:00:00Z", "2026-09-20T00:00:00Z", "2026-10-05T00:00:00Z"]
    ),
)
def test_appending_a_correction_never_changes_an_older_knowledge_cutoff(
    graph: dict[str, object],
    target: str,
    known_at: str,
) -> None:
    view = SourceCurrencyView.parse(_view(lineage=graph, corrections=[]))
    before = view.as_of(_OLD_CUTOFF).as_dict()
    after = view.append_correction(
        _correction("correction-append", target=target, system_known_at=known_at)
    )
    assert view.as_of(_OLD_CUTOFF).as_dict() == before
    if known_at > _OLD_CUTOFF:
        assert after.as_of(_OLD_CUTOFF).as_dict() == before
    assert len(after.as_of(_NEW_CUTOFF).corrections) == (1 if known_at <= _NEW_CUTOFF else 0)


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    cutoff=st.sampled_from([_OLD_CUTOFF, "2026-09-20T00:00:00Z", _NEW_CUTOFF]),
    state=st.sampled_from(CURRENCY_STATES),
    basis=st.sampled_from(
        ["owner_evidence", "owner_decision", "summary", "explanation", "discovery_only_review"]
    ),
)
def test_a_non_owner_basis_never_moves_a_published_state(
    cutoff: str,
    state: str,
    basis: str,
) -> None:
    view = SourceCurrencyView.parse(
        _view(currency_facts=[_fact("fact-1", "support-1", state)])
    ).as_of(cutoff)
    outcome = refresh_formal_currency(
        view,
        {
            "schema": CURRENCY_REFRESH_SCHEMA,
            "statement_id": "support-1",
            "basis": basis,
            "proposed_state": "current",
            "owner_evidence_ref": "record:owner-evidence-new",
            "system_known_at": cutoff,
        },
    )
    if basis in {"owner_evidence", "owner_decision"}:
        assert outcome.refreshed is True
    else:
        assert outcome.refreshed is False
        assert outcome.resulting_state == view.status("support-1").state


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(graph=_graphs(), cutoff=st.sampled_from([_OLD_CUTOFF, _NEW_CUTOFF]))
def test_a_projection_always_rebuilds_from_its_public_record(
    graph: dict[str, object],
    cutoff: str,
) -> None:
    declaration = _projection(
        currency=_view(lineage=graph),
        knowledge_cutoff=cutoff,
        correction_id="correction-1" if cutoff == _NEW_CUTOFF else None,
    )
    projection = freeze_reporting_projection(declaration)
    rebuilt = reconstruct_reporting_projection(
        json.loads(json.dumps(projection.public_record()))
    )
    assert rebuilt.identity == projection.identity
    assert rebuilt.readback() == projection.readback()


# --- A0 reference acceptance slice -------------------------------------------


def test_a0_h01_a_correction_updates_the_current_brief_without_touching_the_old_one() -> None:
    """A0-H01 -- append a correction in an isolated, test-only A0 scope.

    Public input: the V0/V1 Context frozen at snapshot ``snapshot-2026-09-10``
    (code version ``research_currency.v1``, template ``research-brief.v1``,
    currency state contract ``v1``), plus one owner correction published at
    ``2026-09-20`` about 2019 data.  Expected: the current brief carries the
    owner's new currency and gap, the old Context keeps its identity and the
    facts known at its own cutoff, and a new summary does not refresh anything.
    """

    context = freeze_research_context(_declaration())
    identity_before = context.identity
    readback_before = context.readback()

    base = SourceCurrencyView.parse(_view(corrections=[], currency_facts=[]))
    corrected = base.append_correction(_correction())
    corrected = SourceCurrencyView.parse(
        {
            **corrected.as_dict(),
            "currency_facts": [
                _fact("fact-a0-1", "data-1", "superseded"),
                _fact("fact-a0-2", "support-1", "revalidation_due"),
            ],
        }
    )

    historical = freeze_reporting_projection(
        _projection(
            currency=corrected.as_dict(), knowledge_cutoff=_OLD_CUTOFF, correction_id=None
        )
    ).readback()
    current = freeze_reporting_projection(
        _projection(currency=corrected.as_dict(), knowledge_cutoff=_NEW_CUTOFF)
    ).readback()

    # The old snapshot knows nothing of the correction, and the Context that was
    # frozen before it is byte-for-byte what it was.
    assert historical["published_corrections"] == []
    assert {
        entry["statement_id"]: entry["state"] for entry in historical["source_currency"]
    } == {"support-1": "unknown", "counter-1": "unknown", "experience-1": "unknown"}
    assert context.identity == identity_before
    assert context.readback() == readback_before

    # The current brief reflects the owner's new currency and the located gap.
    assert [entry["correction_id"] for entry in current["published_corrections"]] == [
        "correction-1"
    ]
    assert {
        entry["statement_id"]: entry["state"] for entry in current["source_currency"]
    } == {
        "support-1": "revalidation_due",
        "counter-1": "unknown",
        "experience-1": "unknown",
    }
    assert current["correction_impact"]["potentially_affected"] == [
        "counter-1",
        "data-1",
        "support-1",
    ]
    assert current["correction_impact"]["invalidates_downstream"] is False

    # A new summary is not new evidence, and does not refresh eligibility.
    outcome = refresh_formal_currency(
        corrected,
        {
            "schema": CURRENCY_REFRESH_SCHEMA,
            "statement_id": "support-1",
            "basis": "summary",
            "proposed_state": "current",
            "owner_evidence_ref": "record:summary-a0",
            "system_known_at": _NEW_CUTOFF,
        },
    )
    assert outcome.refreshed is False
    assert outcome.as_dict()["grants_eligibility"] is False
    assert current["reporting_guarantees"]["grants_eligibility"] is False


def test_a0_c01_l02_reporting_source_is_published_only_and_revocation_blocks_redelivery() -> None:
    """A0-C01 / A0-L02 -- the projection slice.

    Public input: the same frozen Context, the owner's published Genome
    comparison, the declared gaps and candidate steps, and #396's envelope link
    with ``replay_coverage: limited``.  Expected: only published baseline,
    counter-evidence, gaps and permitted envelope / replay coverage appear; a
    revoked consumer is blocked; the refusal rewrites nothing.
    """

    projection = freeze_reporting_projection(_projection())
    delivered = deliver_reporting_projection(projection, _visibility_request())
    fields = delivered["published_brief"]["fields"]

    # Baseline and counter-evidence are the owner's published values.
    assert fields["baseline_condition"]["value"] == "baseline-v0"
    assert fields["comparison_condition"]["value"] == "comparison-v0-vs-v1"
    conclusion = fields["conditional_conclusions"]["entries"][0]
    assert conclusion["required_counter_evidence"] == ["counter-1"]
    assert fields["key_disagreements"]["values"] == ["disagreement-turnover"]
    assert fields["reusable_assets"]["values"] == ["package-a0", "run-1"]
    assert "research_eligibility" in fields["must_not_claim"]["values"]

    # Permitted envelope and replay coverage only; the digest is not the body.
    assert delivered["exposure"]["replay_coverage"] == "limited"
    assert delivered["exposure"]["full_content_available"] is False
    assert delivered["exposure"]["envelope_content_ref"] is None

    # Every gap and suggestion is sourced.
    for section in ("evidence_gaps", "candidate_next_steps"):
        for entry in delivered[section]["entries"]:
            assert entry["provenance"]

    before = projection.readback()
    revoked = _visibility_request(authorized=False)
    blocked = deliver_reporting_projection(projection, revoked)
    assert blocked["delivery"] == "blocked"
    assert blocked["reason"] == "current_authorization_denied"
    assert projection.readback() == before
    # The old policy that admitted the Context does not re-deliver it now.
    assert deliver_reporting_projection(projection, revoked)["projection_identity"] is None


def test_a0_u5_and_limited_replay_coverage_pass_through_public_readback_only() -> None:
    """U5 (来源纠正) and limited replay coverage, with no new LLM or backtest call.

    U5 comes from #381's shared scenario table: a new brief uses the current
    correction / currency state while the old Context keeps the identity and the
    content it had at the time.  Nothing here loads an envelope, calls a model or
    executes a run -- the whole scenario is a public readback.
    """

    context = freeze_research_context(_declaration())
    view = SourceCurrencyView.parse(_view())

    old = freeze_reporting_projection(
        _projection(knowledge_cutoff=_OLD_CUTOFF, correction_id=None)
    )
    new = freeze_reporting_projection(_projection())

    assert old.context.identity == context.identity == new.context.identity
    assert old.readback()["published_brief"] == new.readback()["published_brief"]
    assert old.readback()["published_corrections"] == []
    assert new.readback()["published_corrections"][0]["correction_id"] == "correction-1"
    assert view.as_of(_OLD_CUTOFF).status("support-1").state == "unknown"
    assert view.as_of(_NEW_CUTOFF).status("support-1").state == "revalidation_due"

    # Limited replay coverage is stated, never papered over with the digest.
    assert new.readback()["exposure"]["replay_coverage"] == "limited"
    assert new.readback()["exposure"]["digest_is_not_content"] is True

    # No MLflow, no engine, no run: the projection is rebuildable offline.
    assert new.readback()["reporting_guarantees"]["mlflow_deployment"] == "none"
    rebuilt = reconstruct_reporting_projection(
        json.loads(json.dumps(new.public_record()))
    )
    assert rebuilt.readback() == new.readback()


def test_a0_a_manual_test_correction_does_not_touch_real_research_facts() -> None:
    """A manual, test-only correction is confined to its own view.

    Whether a real owner correction exists or not, this case covers the same
    branches: the A0 view is constructed here, the no-correction view is
    constructed here, and neither can reach the other.
    """

    without = SourceCurrencyView.parse(_view(corrections=[], currency_facts=[]))
    with_correction = without.append_correction(_correction())
    assert without.corrections == ()
    assert without.as_dict() != with_correction.as_dict()

    baseline = freeze_reporting_projection(
        _projection(currency=without.as_dict(), correction_id=None)
    )
    assert baseline.readback()["correction_impact"] is None
    assert baseline.readback()["published_corrections"] == []
    assert baseline.readback()["published_brief"] == (
        freeze_reporting_projection(_projection()).readback()["published_brief"]
    )
