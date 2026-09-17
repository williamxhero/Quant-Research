"""Consumer-side tests for the frozen bounded research Context and its brief."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from .core import AcceptanceFailure
from .research_context import (
    _BLOCK_REASONS,
    _EXCLUSION_REASONS,
    BRIEF_FIELDS,
    BRIEF_TEMPLATE_ID,
    CONTEXT_DECLARATION_SCHEMA,
    CONTEXT_RECORD_SCHEMA,
    ContextAssemblyFailure,
    deliver_research_brief,
    freeze_research_context,
    reconstruct_research_context,
)
from .research_exposure import EXPOSURE_EVENT_SCHEMA, ExposureLog
from .research_visibility import VISIBILITY_REQUEST_SCHEMA


def _source(
    source_id: str,
    *,
    approved: bool = True,
    applicable: bool = True,
    retrieval: str = "ok",
    published_at: str = "2026-09-01T00:00:00Z",
    derived_from: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    return {
        "source_id": source_id,
        "record_type": "finding",
        "approved": approved,
        "applicable": applicable,
        "retrieval": retrieval,
        "published_at": published_at,
        "provenance_ref": f"record:{source_id}",
        "content_digest": "sha256:" + "1" * 64,
        "derived_from": derived_from if derived_from is not None else [],
    }


def _declaration(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": CONTEXT_DECLARATION_SCHEMA,
        "mode": "current_research",
        "purpose": "research-brief",
        "query_scope": {
            "campaign_id": "campaign-a0",
            "iteration_id": "iteration-2",
            "question_id": "question-momentum-round-2",
            "ordering": "ordering:frozen-v1",
            "trimming": "trimming:unit-atomic-v1",
        },
        "snapshot": {
            "snapshot_id": "snapshot-2026-09-10",
            "knowledge_cutoff": "2026-09-10T00:00:00Z",
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
        "sources": [
            _source("support-1"),
            _source("counter-1"),
            _source("experience-1"),
        ],
        "owner_facts": {
            "current_candidate": {
                "value": "candidate-v1",
                "provenance": ["record:candidate-v1"],
            },
            "current_genome": {"value": "genome-v1", "provenance": ["record:genome-v1"]},
            "baseline_condition": {
                "value": "baseline-v0",
                "provenance": ["record:baseline-v0"],
            },
            "comparison_condition": {
                "value": "comparison-v0-vs-v1",
                "provenance": ["record:compare-v0-v1"],
            },
            "key_disagreements": {
                "values": ["disagreement-turnover"],
                "provenance": ["record:disagreement-turnover"],
            },
            "reusable_assets": {
                "values": ["package-1", "run-1"],
                "provenance": ["record:package-1", "record:run-1"],
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
        "genome_compare": None,
        "visibility_request": None,
    }
    value.update(overrides)
    return value


def _genome_compare(
    *,
    cost: str = "aligned",
    data: str = "aligned",
    execution: str = "aligned",
) -> dict[str, object]:
    return {
        "semantic_path": "genome:sizing/turnover-cap",
        "change_category": "single_component",
        "verified_unchanged_scope": ["scope:universe", "scope:signal-core"],
        "alignment": {"cost": cost, "data": data, "execution": execution},
        "provenance_ref": "record:genome-compare-1",
    }


def _visibility_request(
    *,
    purpose: str = "research-brief",
    authorized: bool = True,
    source_ids: tuple[str, ...] = ("support-1", "counter-1", "experience-1"),
) -> dict[str, object]:
    # When ``authorized`` is false the consumer still asks for the same purpose,
    # but no current grant covers it -- that is a current-authorization denial,
    # not a malformed request.
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
            "authorization_knowledge_cutoff": "2026-09-10T00:00:00Z",
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
            "knowledge_cutoff": "2026-09-10T00:00:00Z",
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


def _fields(context) -> dict[str, dict[str, object]]:
    return dict(context.brief.fields)


# --- Identity, manifest and declared scope -----------------------------------


def test_the_identity_binds_snapshot_scope_policy_purpose_sources_and_manifest() -> None:
    base = freeze_research_context(_declaration())
    readback = base.readback()
    assert readback["context_identity"] == base.identity
    assert readback["snapshot"]["snapshot_id"] == "snapshot-2026-09-10"
    assert readback["query_scope"]["question_id"] == "question-momentum-round-2"
    assert readback["policy"]["template_version"] == "v1"
    assert readback["purpose"] == "research-brief"
    assert {entry["source_id"] for entry in readback["manifest"]} == {
        "support-1",
        "counter-1",
        "experience-1",
    }
    for name, value in (
        (
            "snapshot",
            {
                "snapshot_id": "snapshot-2026-09-11",
                "knowledge_cutoff": "2026-09-11T00:00:00Z",
                "corrections_version": "corrections-v4",
            },
        ),
        ("purpose", "audit-brief"),
    ):
        assert freeze_research_context(_declaration(**{name: value})).identity != base.identity
    other_scope = dict(_declaration()["query_scope"])
    other_scope["ordering"] = "ordering:frozen-v2"
    assert freeze_research_context(_declaration(query_scope=other_scope)).identity != base.identity
    other_policy = dict(_declaration()["policy"])
    other_policy["template_version"] = "v2"
    assert freeze_research_context(_declaration(policy=other_policy)).identity != base.identity


def test_only_approved_and_applicable_sources_are_included() -> None:
    sources = [
        _source("support-1"),
        _source("counter-1"),
        _source("experience-1", approved=False),
        _source("experience-2", applicable=False),
    ]
    context = freeze_research_context(
        _declaration(
            sources=sources,
            optional_scope={"source_ids": ["experience-1", "experience-2"], "exhausted": True},
        )
    )
    manifest = {entry.source_id: entry for entry in context.manifest}
    assert manifest["experience-1"].decision == "excluded"
    assert manifest["experience-1"].reason == "not_approved"
    assert manifest["experience-2"].reason == "not_applicable"
    assert manifest["support-1"].decision == "included"
    assert set(context.included_source_ids) == {"support-1", "counter-1"}
    assert {entry.reason for entry in context.manifest if entry.decision == "excluded"} <= (
        _EXCLUSION_REASONS
    )


def test_a_different_manifest_cannot_share_an_identity() -> None:
    included = freeze_research_context(_declaration())
    excluded = freeze_research_context(
        _declaration(
            sources=[
                _source("support-1"),
                _source("counter-1"),
                _source("experience-1", approved=False),
            ]
        )
    )
    assert included.identity != excluded.identity


def test_an_unauthorized_source_is_excluded_by_the_reused_gate() -> None:
    context = freeze_research_context(
        _declaration(visibility_request=_visibility_request(authorized=False))
    )
    manifest = {entry.source_id: entry for entry in context.manifest}
    assert manifest["support-1"].reason == "not_authorized"
    assert context.brief.status == "blocked"
    assert "required_closure_incomplete" in context.brief.block_reasons


# --- Coverage states ---------------------------------------------------------


def test_the_five_coverage_states_are_distinguishable() -> None:
    complete = freeze_research_context(_declaration())
    assert complete.coverage.state == "complete"

    empty = freeze_research_context(
        _declaration(
            required_closure=[],
            optional_scope={"source_ids": [], "exhausted": True},
            sources=[],
            conclusions=[],
        )
    )
    assert empty.coverage.state == "complete_empty"

    partial = freeze_research_context(
        _declaration(optional_scope={"source_ids": ["experience-1"], "exhausted": False})
    )
    assert partial.coverage.state == "optional_not_exhausted"

    failed = freeze_research_context(
        _declaration(
            sources=[
                _source("support-1"),
                _source("counter-1"),
                _source("experience-1", retrieval="failed"),
            ]
        )
    )
    assert failed.coverage.state == "retrieval_failure"
    assert failed.coverage.retrieval_failures == ("experience-1",)

    missing = freeze_research_context(
        _declaration(sources=[_source("support-1"), _source("experience-1")])
    )
    assert missing.coverage.state == "required_incomplete"
    assert missing.coverage.required_missing == ("counter-1",)


def test_a_retrieval_failure_is_never_downgraded_to_an_optional_miss() -> None:
    context = freeze_research_context(
        _declaration(
            optional_scope={"source_ids": ["experience-1"], "exhausted": False},
            sources=[
                _source("support-1"),
                _source("counter-1"),
                _source("experience-1", retrieval="failed"),
            ],
        )
    )
    assert context.coverage.state == "retrieval_failure"
    assert context.coverage.optional_uncovered == ("experience-1",)


def test_no_readback_ever_claims_that_full_history_was_scanned() -> None:
    context = freeze_research_context(_declaration())
    coverage = context.readback()["coverage"]
    assert coverage["scanned_full_history"] is False
    assert coverage["declared_scope_only"] is True
    must_not_claim = _fields(context)["must_not_claim"]
    assert "full_history_scanned" in must_not_claim["values"]


def test_an_empty_declared_scope_is_not_a_retrieval_failure() -> None:
    empty = freeze_research_context(
        _declaration(
            required_closure=[],
            optional_scope={"source_ids": [], "exhausted": True},
            sources=[],
            conclusions=[],
        )
    )
    assert empty.coverage.state == "complete_empty"
    assert empty.coverage.retrieval_failures == ()
    assert empty.brief.status == "assembled"


# --- Brief fields, provenance and non-fabrication ----------------------------


def test_the_brief_carries_every_fixed_field_with_provenance_or_unknown() -> None:
    context = freeze_research_context(_declaration(genome_compare=_genome_compare()))
    fields = _fields(context)
    assert tuple(fields) == BRIEF_FIELDS
    for name, value in fields.items():
        assert value["state"] in {"present", "unknown"}
        if value["state"] == "unknown":
            continue
        if "provenance" in value:
            assert value["provenance"], name
        else:
            for entry in value["entries"]:
                assert entry.get("provenance") or entry.get("required_support"), name


def test_an_absent_owner_fact_is_unknown_and_never_invented() -> None:
    facts = deepcopy(_declaration()["owner_facts"])
    del facts["current_genome"]
    del facts["key_disagreements"]
    context = freeze_research_context(_declaration(owner_facts=facts))
    fields = _fields(context)
    assert fields["current_genome"] == {"state": "unknown", "value": None, "provenance": []}
    assert fields["key_disagreements"] == {"state": "unknown", "values": [], "provenance": []}
    assert fields["current_candidate"]["value"] == "candidate-v1"


def test_an_owner_fact_without_provenance_is_refused() -> None:
    facts = deepcopy(_declaration()["owner_facts"])
    facts["current_candidate"] = {"value": "candidate-v1", "provenance": []}
    with pytest.raises(AcceptanceFailure):
        freeze_research_context(_declaration(owner_facts=facts))


def test_a_next_step_without_preconditions_is_refused() -> None:
    with pytest.raises(AcceptanceFailure):
        freeze_research_context(
            _declaration(
                candidate_next_steps=[
                    {
                        "step_id": "step-1",
                        "provenance_ref": "record:gap-1",
                        "preconditions": [],
                    }
                ]
            )
        )


def test_next_steps_stay_suggestions_and_never_create_a_task() -> None:
    context = freeze_research_context(_declaration())
    brief = context.brief.as_dict()
    assert brief["creates_tasks"] is False
    assert brief["reserves_budget"] is False
    assert brief["invokes_engine"] is False
    assert brief["grants_eligibility"] is False
    steps = _fields(context)["candidate_next_steps"]["entries"]
    assert [step["status"] for step in steps] == ["suggestion_pending_approval"]
    assert steps[0]["execution_preconditions"] == ["approval:owner", "data:cost-model-aligned"]
    assert steps[0]["provenance"] == ["record:gap-1"]


def test_a_gap_carries_its_preconditions() -> None:
    context = freeze_research_context(_declaration())
    gaps = _fields(context)["evidence_gaps"]["entries"]
    assert gaps[0]["gap_id"] == "gap-holdout-untouched"
    assert gaps[0]["preconditions"] == ["approval:holdout-read"]
    assert gaps[0]["provenance"] == ["record:gap-1"]


def test_the_brief_cannot_carry_free_text() -> None:
    facts = deepcopy(_declaration()["owner_facts"])
    facts["current_candidate"] = {
        "value": "the model clearly beats the baseline",
        "provenance": ["record:candidate-v1"],
    }
    with pytest.raises(AcceptanceFailure):
        freeze_research_context(_declaration(owner_facts=facts))


# --- Assembly units, counter-evidence and budget -----------------------------


def test_a_conclusion_ships_with_its_support_counter_evidence_and_limitations() -> None:
    context = freeze_research_context(
        _declaration(
            required_closure=["support-1", "counter-1", "limitation-1"],
            sources=[
                _source("support-1"),
                _source("counter-1"),
                _source("limitation-1"),
                _source("experience-1"),
            ],
            conclusions=[
                {
                    "conclusion_id": "conclusion-1",
                    "statement_ref": "record:statement-1",
                    "required_support": ["support-1"],
                    "required_counter_evidence": ["counter-1"],
                    "limitations": ["limitation-1"],
                    "optional": False,
                }
            ],
        )
    )
    assert context.brief.status == "assembled"
    unit = _fields(context)["conditional_conclusions"]["entries"][0]
    assert unit["required_support"] == ["support-1"]
    assert unit["required_counter_evidence"] == ["counter-1"]
    assert unit["limitations"] == ["limitation-1"]


def test_a_conclusion_whose_counter_evidence_is_unavailable_is_not_delivered() -> None:
    context = freeze_research_context(
        _declaration(
            required_closure=["support-1"],
            sources=[
                _source("support-1"),
                _source("counter-1", approved=False),
                _source("experience-1"),
            ],
        )
    )
    assert context.brief.status == "blocked"
    assert "required_counter_evidence_unavailable" in context.brief.block_reasons
    assert _fields(context)["conditional_conclusions"]["state"] == "unknown"


def test_a_tight_budget_drops_optional_units_before_required_ones() -> None:
    context = freeze_research_context(
        _declaration(
            budget={"discussion_budget": 3, "closure_budget": 16},
            required_closure=["support-1", "counter-1", "experience-1"],
            conclusions=[
                {
                    "conclusion_id": "conclusion-1",
                    "statement_ref": "record:statement-1",
                    "required_support": ["support-1"],
                    "required_counter_evidence": ["counter-1"],
                    "limitations": [],
                    "optional": False,
                },
                {
                    "conclusion_id": "conclusion-2",
                    "statement_ref": "record:statement-2",
                    "required_support": ["experience-1"],
                    "required_counter_evidence": [],
                    "limitations": [],
                    "optional": True,
                },
            ],
        )
    )
    assert context.brief.status == "assembled"
    assert context.brief.dropped_optional_units == ("conclusion-2",)
    units = _fields(context)["conditional_conclusions"]["entries"]
    assert [unit["conclusion_id"] for unit in units] == ["conclusion-1"]
    assert units[0]["required_counter_evidence"] == ["counter-1"]


def test_a_small_budget_blocks_a_required_unit_instead_of_dropping_its_evidence() -> None:
    context = freeze_research_context(
        _declaration(budget={"discussion_budget": 2, "closure_budget": 16})
    )
    assert context.brief.status == "blocked"
    assert "discussion_budget_insufficient_for_required_units" in context.brief.block_reasons
    assert _fields(context)["conditional_conclusions"]["state"] == "unknown"
    assert set(context.brief.block_reasons) <= _BLOCK_REASONS
    assert context.readback()["budget"]["pagination_owner"] == "issue-398"


def test_an_optional_unit_missing_its_evidence_is_dropped_not_degraded() -> None:
    context = freeze_research_context(
        _declaration(
            conclusions=[
                {
                    "conclusion_id": "conclusion-1",
                    "statement_ref": "record:statement-1",
                    "required_support": ["support-1"],
                    "required_counter_evidence": ["counter-1"],
                    "limitations": [],
                    "optional": False,
                },
                {
                    "conclusion_id": "conclusion-2",
                    "statement_ref": "record:statement-2",
                    "required_support": ["support-1"],
                    "required_counter_evidence": ["counter-missing"],
                    "limitations": [],
                    "optional": True,
                },
            ]
        )
    )
    assert context.brief.status == "assembled"
    units = _fields(context)["conditional_conclusions"]["entries"]
    assert [unit["conclusion_id"] for unit in units] == ["conclusion-1"]


# --- Single-component comparison --------------------------------------------


def test_a_misaligned_single_component_comparison_reports_the_gap_first() -> None:
    context = freeze_research_context(
        _declaration(genome_compare=_genome_compare(cost="not_aligned"))
    )
    gaps = _fields(context)["evidence_gaps"]["entries"]
    assert gaps[0]["gap_id"] == "comparison_gap:cost"
    assert gaps[0]["preconditions"] == ["align:cost"]
    assert gaps[0]["provenance"] == ["record:genome-compare-1"]
    limitation_ids = [
        item["limitation_id"] for item in _fields(context)["coverage_limitations"]["entries"]
    ]
    assert "comparability_limited:cost" in limitation_ids
    assert "verified_unchanged:scope:universe" in limitation_ids
    assert "verified_unchanged:scope:signal-core" in limitation_ids
    assert "changed_component:genome:sizing/turnover-cap" in limitation_ids
    assert "causal_improvement" in _fields(context)["must_not_claim"]["values"]


def test_a_fully_aligned_comparison_does_not_add_a_causal_claim_or_a_gap() -> None:
    context = freeze_research_context(_declaration(genome_compare=_genome_compare()))
    gap_ids = [item["gap_id"] for item in _fields(context)["evidence_gaps"]["entries"]]
    assert not any(gap_id.startswith("comparison_gap:") for gap_id in gap_ids)
    assert "causal_improvement" not in _fields(context)["must_not_claim"]["values"]
    limitation_ids = [
        item["limitation_id"] for item in _fields(context)["coverage_limitations"]["entries"]
    ]
    assert "verified_unchanged:scope:universe" in limitation_ids


def test_an_unknown_alignment_is_a_gap_and_not_an_alignment() -> None:
    context = freeze_research_context(
        _declaration(genome_compare=_genome_compare(execution="unknown"))
    )
    gap_ids = [item["gap_id"] for item in _fields(context)["evidence_gaps"]["entries"]]
    assert "comparison_gap:execution" in gap_ids
    assert "causal_improvement" in _fields(context)["must_not_claim"]["values"]


def test_genome_compare_is_consumed_and_never_recomputed() -> None:
    compare = _genome_compare(cost="not_aligned")
    context = freeze_research_context(_declaration(genome_compare=compare))
    echoed = context.declaration.genome_compare
    assert echoed is not None
    assert echoed.semantic_path == compare["semantic_path"]
    assert echoed.change_category == "single_component"
    assert list(echoed.verified_unchanged_scope) == ["scope:signal-core", "scope:universe"]


# --- Reconstruction, corrections and current authorization -------------------


def test_a_context_is_reconstructable_from_its_public_record_alone() -> None:
    context = freeze_research_context(
        _declaration(genome_compare=_genome_compare(data="not_aligned"))
    )
    record = json.loads(json.dumps(context.public_record()))
    assert record["schema"] == CONTEXT_RECORD_SCHEMA
    rebuilt = reconstruct_research_context(record)
    assert rebuilt.identity == context.identity
    assert rebuilt.readback() == context.readback()


def test_a_tampered_record_cannot_reproduce_its_identity() -> None:
    context = freeze_research_context(_declaration())
    record = json.loads(json.dumps(context.public_record()))
    record["declaration"]["purpose"] = "audit-brief"
    with pytest.raises(AcceptanceFailure):
        reconstruct_research_context(record)


def test_dropping_every_derived_projection_still_recovers_identity_and_content() -> None:
    context = freeze_research_context(_declaration())
    record = json.loads(json.dumps(context.public_record()))
    # Nothing but the public record survives: no graph, no search index, no
    # cached brief, no second Context authority.
    del context
    rebuilt = reconstruct_research_context(record)
    again = reconstruct_research_context(json.loads(json.dumps(rebuilt.public_record())))
    assert again.identity == rebuilt.identity
    assert again.readback() == rebuilt.readback()


def test_a_correction_published_after_the_snapshot_never_joins_a_historical_context() -> None:
    sources = [
        _source("support-1"),
        _source("counter-1"),
        _source("correction-1", published_at="2026-09-12T00:00:00Z"),
    ]
    historical = freeze_research_context(
        _declaration(
            mode="historical_reconstruction",
            sources=sources,
            optional_scope={"source_ids": ["correction-1"], "exhausted": True},
        )
    )
    manifest = {entry.source_id: entry for entry in historical.manifest}
    assert manifest["correction-1"].reason == "published_after_snapshot"
    assert "correction-1" not in historical.included_source_ids

    current = freeze_research_context(
        _declaration(
            mode="current_research",
            sources=sources,
            optional_scope={"source_ids": ["correction-1"], "exhausted": True},
        )
    )
    assert "correction-1" in current.included_source_ids
    assert current.identity != historical.identity


def test_current_authorization_still_blocks_delivery_of_an_old_context() -> None:
    context = freeze_research_context(_declaration())
    allowed = deliver_research_brief(context, _visibility_request())
    assert allowed["delivery"] == "delivered"
    assert allowed["context_identity"] == context.identity

    denied = deliver_research_brief(context, _visibility_request(authorized=False))
    assert denied["delivery"] == "blocked"
    assert denied["reason"] == "current_authorization_denied"
    assert denied["context_identity"] is None
    assert "brief" not in denied
    assert "manifest" not in denied
    # The refusal changes nothing about the frozen Context itself.
    assert freeze_research_context(_declaration()).identity == context.identity


def test_the_context_identity_is_the_one_an_exposure_event_references() -> None:
    context = freeze_research_context(_declaration())
    log = ExposureLog()
    event = log.append(
        {
            "schema": EXPOSURE_EVENT_SCHEMA,
            "event_type": "context_prepared",
            "key": {
                "campaign_id": "campaign-a0",
                "iteration_id": "iteration-2",
                "consumer": "research-model",
                "action": "final_request",
                "idempotency_key": "idem-1",
            },
            "research_action_id": "research-action-1",
            "context_identity": context.identity,
            "research_family": {
                "family_id": "family-momentum",
                "test_family": "test-family-momentum",
                "prior_result_ids": ["prior-result-1"],
            },
            "policy": {
                "policy_id": "auth-policy",
                "policy_version": "v1",
                "knowledge_cutoff": "2026-09-10T00:00:00Z",
            },
            "invocation_id": "invocation-1",
            "context_material_ids": list(context.included_source_ids),
        }
    )
    assert event.context_identity == context.identity
    assert log.context_exposure(context.identity) == "prepared"


# --- Structural refusals -----------------------------------------------------


def test_an_unknown_template_is_refused() -> None:
    policy = dict(_declaration()["policy"])
    policy["template_id"] = "some-other-template"
    with pytest.raises(ContextAssemblyFailure):
        freeze_research_context(_declaration(policy=policy))


def test_an_unknown_declaration_field_is_refused() -> None:
    with pytest.raises(AcceptanceFailure):
        freeze_research_context({**_declaration(), "extra": "value"})


def test_a_missing_discussion_budget_is_refused() -> None:
    with pytest.raises(ContextAssemblyFailure):
        freeze_research_context(_declaration(budget={"closure_budget": 16}))


def test_duplicate_source_ids_are_refused() -> None:
    with pytest.raises(ContextAssemblyFailure):
        freeze_research_context(
            _declaration(sources=[_source("support-1"), _source("support-1"), _source("counter-1")])
        )


def test_an_exhausted_closure_budget_is_incomplete_not_empty() -> None:
    chain = [
        _source(
            f"support-{index}",
            derived_from=[
                {"source_id": f"support-{index + 1}", "relationship": "derived_from"}
            ],
        )
        for index in range(1, 6)
    ]
    chain.append(_source("support-6"))
    chain.append(_source("counter-1"))
    context = freeze_research_context(
        _declaration(
            budget={"discussion_budget": 32, "closure_budget": 2},
            required_closure=["support-1", "counter-1"],
            sources=chain,
            optional_scope={"source_ids": [], "exhausted": True},
            conclusions=[],
        )
    )
    assert context.coverage.state == "required_incomplete"
    assert context.brief.status == "blocked"


# --- Determinism properties --------------------------------------------------


_SOURCE_IDS = ("support-1", "counter-1", "experience-1")


def _shuffled(value: dict[str, object], seed: int) -> dict[str, object]:
    """Reorder every list the declaration allows to be reordered."""

    shuffled = deepcopy(value)
    for name in ("sources", "conclusions", "evidence_gaps", "candidate_next_steps"):
        items = shuffled[name]
        assert isinstance(items, list)
        offset = seed % max(len(items), 1)
        shuffled[name] = items[offset:] + items[:offset]
    for source in shuffled["sources"]:
        edges = source["derived_from"]
        if edges:
            offset = seed % len(edges)
            source["derived_from"] = edges[offset:] + edges[:offset]
    required = shuffled["required_closure"]
    shuffled["required_closure"] = list(reversed(required))
    return shuffled


@given(seed=st.integers(min_value=0, max_value=32))
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_input_ordering_never_changes_the_frozen_output(seed: int) -> None:
    declaration = _declaration(
        genome_compare=_genome_compare(cost="not_aligned"),
        sources=[
            _source(
                "support-1",
                derived_from=[{"source_id": "support-0", "relationship": "derived_from"}],
            ),
            _source("support-0"),
            _source("counter-1"),
            _source("experience-1"),
        ],
        required_closure=["support-1", "counter-1"],
    )
    baseline = freeze_research_context(declaration)
    reordered = freeze_research_context(_shuffled(declaration, seed))
    assert reordered.identity == baseline.identity
    assert reordered.readback() == baseline.readback()


@given(repeats=st.integers(min_value=1, max_value=4), reverse=st.booleans())
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_allowed_equivalent_representations_freeze_to_the_same_context(
    repeats: int, reverse: bool
) -> None:
    """A repeated edge, and a flat versus a compact closure, are the same graph."""

    edge = {"source_id": "support-0", "relationship": "derived_from"}
    compact = _declaration(
        sources=[
            _source("support-1", derived_from=[deepcopy(edge) for _ in range(repeats)]),
            _source("support-0"),
            _source("counter-1"),
            _source("experience-1"),
        ],
        required_closure=["support-1", "counter-1"],
    )
    flat = deepcopy(compact)
    # Naming the transitive ancestor explicitly is an allowed-equivalent form.
    flat["required_closure"] = ["counter-1", "support-0", "support-1"]
    if reverse:
        flat["required_closure"] = list(reversed(flat["required_closure"]))
    # A source listed in both scopes is required; the optional scope is the rest.
    flat["optional_scope"] = {"source_ids": ["experience-1", "support-1"], "exhausted": True}
    assert freeze_research_context(flat).identity == freeze_research_context(compact).identity
    assert freeze_research_context(flat).readback() == freeze_research_context(compact).readback()


@given(
    seed=st.integers(min_value=0, max_value=32),
    extra=st.sampled_from(_SOURCE_IDS),
)
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_changing_a_nested_input_after_freezing_never_changes_the_output(
    seed: int, extra: str
) -> None:
    declaration = _declaration(genome_compare=_genome_compare(data="not_aligned"))
    context = freeze_research_context(declaration)
    before = json.dumps(context.readback(), sort_keys=True)
    # Mutate the caller's nested structures after the Context was frozen.
    declaration["sources"].append(_source("late-arrival"))
    declaration["sources"][seed % 3]["approved"] = False
    declaration["required_closure"].append(extra)
    declaration["owner_facts"]["current_candidate"]["provenance"].append("record:forged")
    declaration["conclusions"][0]["required_counter_evidence"] = []
    assert declaration["genome_compare"] is not None
    declaration["genome_compare"]["alignment"]["cost"] = "aligned"
    assert json.dumps(context.readback(), sort_keys=True) == before
    assert context.identity == freeze_research_context(_declaration(
        genome_compare=_genome_compare(data="not_aligned")
    )).identity


@given(order=st.permutations(["a", "b", "c"]))
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_graph_traversal_order_never_changes_the_canonical_output(order: list[str]) -> None:
    """A diamond lineage, walked from every declared edge order, is one Context."""

    edges = [
        {"source_id": f"ancestor-{name}", "relationship": "derived_from"} for name in order
    ]
    sources = [
        _source("support-1", derived_from=edges),
        _source("counter-1", derived_from=list(reversed(edges))),
        _source("experience-1"),
    ]
    sources.extend(
        _source(
            f"ancestor-{name}",
            derived_from=[{"source_id": "ancestor-root", "relationship": "derived_from"}],
        )
        for name in ("a", "b", "c")
    )
    sources.append(_source("ancestor-root"))
    declaration = _declaration(sources=sources, required_closure=["support-1", "counter-1"])
    context = freeze_research_context(declaration)
    canonical = _declaration(
        sources=[
            _source(
                "support-1",
                derived_from=[
                    {"source_id": f"ancestor-{name}", "relationship": "derived_from"}
                    for name in ("a", "b", "c")
                ],
            ),
            _source(
                "counter-1",
                derived_from=[
                    {"source_id": f"ancestor-{name}", "relationship": "derived_from"}
                    for name in ("a", "b", "c")
                ],
            ),
            _source("experience-1"),
            *(
                _source(
                    f"ancestor-{name}",
                    derived_from=[{"source_id": "ancestor-root", "relationship": "derived_from"}],
                )
                for name in ("a", "b", "c")
            ),
            _source("ancestor-root"),
        ],
        required_closure=["support-1", "counter-1"],
    )
    expected = freeze_research_context(canonical)
    assert context.identity == expected.identity
    assert context.readback() == expected.readback()
    assert set(context.included_source_ids) >= {"ancestor-root", "ancestor-a", "support-1"}


# --- A0 reference acceptance slice -------------------------------------------
#
# These run on synthetic, #437-shaped, explicitly test-only records.  The A0
# fixture oracle (#434 / #437) is still `pending` in
# docs/research/a0/a0_delivery_index.json, so these assert the contract's shape
# on frozen stand-ins.  They do not claim a real A0 round, a real second-round
# model delivery, or any research qualification.


def _a0_declaration(**overrides: object) -> dict[str, object]:
    value = _declaration(
        query_scope={
            "campaign_id": "a0-campaign",
            "iteration_id": "a0-round-2",
            "question_id": "a0-v0-vs-v1",
            "ordering": "ordering:frozen-v1",
            "trimming": "trimming:unit-atomic-v1",
        },
        required_closure=["a0-support-v1", "a0-counter-v1", "a0-limitation-cost"],
        optional_scope={"source_ids": ["a0-experience-v0"], "exhausted": True},
        sources=[
            _source("a0-support-v1", published_at="2026-09-02T00:00:00Z"),
            _source("a0-counter-v1", published_at="2026-09-02T00:00:00Z"),
            _source("a0-limitation-cost", published_at="2026-09-02T00:00:00Z"),
            _source("a0-experience-v0", published_at="2026-09-01T00:00:00Z"),
        ],
        owner_facts={
            "current_candidate": {
                "value": "a0-candidate-v1",
                "provenance": ["record:a0-candidate-v1"],
            },
            "current_genome": {"value": "a0-genome-v1", "provenance": ["record:a0-genome-v1"]},
            "baseline_condition": {"value": "a0-v0", "provenance": ["record:a0-v0"]},
            "comparison_condition": {
                "value": "a0-v0-vs-v1-test-only",
                "provenance": ["record:a0-compare"],
            },
            "key_disagreements": {
                "values": ["a0-disagreement-turnover"],
                "provenance": ["record:a0-counter-v1"],
            },
            "reusable_assets": {
                "values": ["a0-package-v1", "a0-run-v1"],
                "provenance": ["record:a0-package-v1", "record:a0-run-v1"],
            },
            "must_not_claim": {
                "values": ["a0-real-round-executed"],
                "provenance": ["record:a0-scope"],
            },
        },
        evidence_gaps=[
            {
                "gap_id": "a0-gap-cost-model",
                "provenance_ref": "record:a0-compare",
                "preconditions": ["align:cost"],
            }
        ],
        candidate_next_steps=[
            {
                "step_id": "a0-step-align-cost-then-rerun",
                "provenance_ref": "record:a0-compare",
                "preconditions": ["approval:owner", "align:cost"],
            }
        ],
        conclusions=[
            {
                "conclusion_id": "a0-conclusion-1",
                "statement_ref": "record:a0-statement-1",
                "required_support": ["a0-support-v1"],
                "required_counter_evidence": ["a0-counter-v1"],
                "limitations": ["a0-limitation-cost"],
                "optional": False,
            }
        ],
        genome_compare={
            "semantic_path": "genome:sizing/turnover-cap",
            "change_category": "single_component",
            "verified_unchanged_scope": ["scope:a0-universe", "scope:a0-signal-core"],
            "alignment": {"cost": "not_aligned", "data": "aligned", "execution": "aligned"},
            "provenance_ref": "record:a0-genome-compare",
        },
    )
    value.update(overrides)
    return value


def test_a0_c01_second_round_brief_has_every_field_with_provenance_or_unknown() -> None:
    context = freeze_research_context(_a0_declaration())
    assert context.brief.status == "assembled"
    fields = _fields(context)
    assert fields["baseline_condition"]["value"] == "a0-v0"
    assert fields["comparison_condition"]["value"] == "a0-v0-vs-v1-test-only"
    unit = fields["conditional_conclusions"]["entries"][0]
    assert unit["required_support"] == ["a0-support-v1"]
    assert unit["required_counter_evidence"] == ["a0-counter-v1"]
    assert unit["limitations"] == ["a0-limitation-cost"]
    assert fields["evidence_gaps"]["entries"][0]["gap_id"] == "comparison_gap:cost"
    assert "a0-gap-cost-model" in [
        item["gap_id"] for item in fields["evidence_gaps"]["entries"]
    ]
    assert fields["reusable_assets"]["values"] == ["a0-package-v1", "a0-run-v1"]
    step = fields["candidate_next_steps"]["entries"][0]
    assert step["execution_preconditions"] == ["align:cost", "approval:owner"]
    assert step["status"] == "suggestion_pending_approval"
    assert "a0-real-round-executed" in fields["must_not_claim"]["values"]
    for name, value in fields.items():
        assert value["state"] in {"present", "unknown"}, name
    brief = context.brief.as_dict()
    assert brief["creates_tasks"] is False
    assert brief["invokes_engine"] is False


def test_a0_m02_unaligned_cost_keeps_limitations_and_refuses_a_causal_claim() -> None:
    context = freeze_research_context(_a0_declaration())
    fields = _fields(context)
    limitation_ids = [item["limitation_id"] for item in fields["coverage_limitations"]["entries"]]
    assert "comparability_limited:cost" in limitation_ids
    assert "verified_unchanged:scope:a0-universe" in limitation_ids
    assert "verified_unchanged:scope:a0-signal-core" in limitation_ids
    assert "changed_component:genome:sizing/turnover-cap" in limitation_ids
    assert "causal_improvement" in fields["must_not_claim"]["values"]
    # The required counter-evidence is still there, not traded for the gap.
    unit = fields["conditional_conclusions"]["entries"][0]
    assert unit["required_counter_evidence"] == ["a0-counter-v1"]


def test_a0_m02_a_tight_budget_never_buys_room_by_dropping_counter_evidence() -> None:
    context = freeze_research_context(
        _a0_declaration(budget={"discussion_budget": 3, "closure_budget": 16})
    )
    assert context.brief.status == "blocked"
    assert "discussion_budget_insufficient_for_required_units" in context.brief.block_reasons
    assert _fields(context)["conditional_conclusions"]["state"] == "unknown"
    # Even blocked, the comparison limitation survives -- the refusal is not a
    # quieter version of the positive conclusion.
    limitation_ids = [
        item["limitation_id"] for item in _fields(context)["coverage_limitations"]["entries"]
    ]
    assert "comparability_limited:cost" in limitation_ids


def test_a0_the_frozen_result_survives_reordering_and_losing_every_projection() -> None:
    declaration = _a0_declaration()
    context = freeze_research_context(declaration)
    frozen_identity = context.identity
    frozen_readback = json.loads(json.dumps(context.readback()))

    reordered = freeze_research_context(_shuffled(declaration, 2))
    assert reordered.identity == frozen_identity
    assert reordered.readback() == frozen_readback

    record = json.loads(json.dumps(context.public_record()))
    rebuilt = reconstruct_research_context(record)
    assert rebuilt.identity == frozen_identity
    assert rebuilt.readback() == frozen_readback
