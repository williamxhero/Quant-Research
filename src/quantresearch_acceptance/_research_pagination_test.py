"""Consumer-side tests for paginated retrieval, snapshot integrity and trimming."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from .core import AcceptanceFailure
from .research_context import BRIEF_TEMPLATE_ID, CONTEXT_DECLARATION_SCHEMA
from .research_pagination import (
    _FAILURE_DETAILS,
    _RECORD_REASONS,
    PAGINATED_DECLARATION_SCHEMA,
    PAGINATED_RECORD_SCHEMA,
    RETRIEVAL_STATE_CONTRACT,
    RETRIEVAL_STATE_CONTRACT_DIGEST,
    RETRIEVAL_STATE_CONTRACT_ID,
    RETRIEVAL_STATE_CONTRACT_VERSION,
    RETRIEVAL_STATES,
    PaginatedResearchContext,
    RetrievalRefusal,
    deliver_paginated_research_brief,
    freeze_paginated_research_context,
    reconstruct_paginated_research_context,
)
from .research_visibility import VISIBILITY_REQUEST_SCHEMA

_ORDERING = "ordering:published-at"
_TRIMMING = "trimming:unit-atomic-v1"
_CUTOFF = "2026-09-10T00:00:00Z"
_SNAPSHOT_ID = "snapshot-2026-09-10"


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


def _context(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": CONTEXT_DECLARATION_SCHEMA,
        "mode": "current_research",
        "purpose": "research-brief",
        "query_scope": {
            "campaign_id": "campaign-a0",
            "iteration_id": "iteration-2",
            "question_id": "question-momentum-round-2",
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
        "required_closure": ["support-1", "counter-1"],
        "optional_scope": {"source_ids": ["experience-1"], "exhausted": True},
        "sources": [_source("support-1"), _source("counter-1"), _source("experience-1")],
        "owner_facts": {
            "current_candidate": {"value": "candidate-v1", "provenance": ["record:candidate-v1"]},
        },
        "evidence_gaps": [],
        "candidate_next_steps": [],
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


def _plan(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
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
    }
    value.update(overrides)
    return value


def _record(source_id: str, sort_key: str, published_at: str | None = None) -> dict[str, str]:
    return {
        "source_id": source_id,
        "sort_key": sort_key,
        "published_at": published_at if published_at is not None else "2026-09-01T00:00:00Z",
    }


def _page(
    index: int,
    records: list[dict[str, str]],
    *,
    status: str = "ok",
    exhausted: bool = False,
) -> dict[str, object]:
    return {
        "page_index": index,
        "cursor_in": f"cursor-{index}",
        "cursor_out": f"cursor-{index + 1}",
        "status": status,
        "exhausted": exhausted,
        "records": records,
    }


def _pages() -> list[dict[str, object]]:
    return [
        _page(0, [_record("counter-1", "k-01"), _record("experience-1", "k-02")]),
        _page(1, [_record("support-1", "k-03")], exhausted=True),
    ]


def _declaration(**overrides: object) -> dict[str, object]:
    context = overrides.pop("context", None)
    plan = overrides.pop("plan", None)
    pages = overrides.pop("pages", None)
    value: dict[str, object] = {
        "schema": PAGINATED_DECLARATION_SCHEMA,
        "context": _context() if context is None else context,
        "retrieval": {
            "plan": _plan() if plan is None else plan,
            "pages": _pages() if pages is None else pages,
        },
    }
    value.update(overrides)
    return value


def _freeze(**overrides: object) -> PaginatedResearchContext:
    return freeze_paginated_research_context(_declaration(**overrides))


def _visibility_request(
    *,
    purpose: str = "research-brief",
    authorized: bool = True,
    source_ids: tuple[str, ...] = ("support-1", "counter-1", "experience-1"),
    restricted: tuple[str, ...] = (),
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
                "allowed_purposes": (
                    ["protected-purpose"] if source_id in restricted else [purpose]
                ),
                "required_capabilities": ["cap.research"],
            }
            for source_id in source_ids
        ],
        "context_material_ids": list(source_ids),
    }


def _entries(context: PaginatedResearchContext) -> dict[str, tuple[str, str, str]]:
    return {
        entry.source_id: (entry.decision, entry.reason, entry.role)
        for entry in context.outcome.manifest
    }


# --- The frozen state contract -----------------------------------------------


def test_the_retrieval_state_contract_is_frozen_and_versioned() -> None:
    assert RETRIEVAL_STATES == (
        "complete",
        "complete_empty",
        "optional_scope_not_exhausted",
        "cursor_invalidated",
        "snapshot_contaminated",
        "index_unavailable",
        "retrieval_interrupted",
        "budget_exhausted",
        "required_lineage_missing",
    )
    assert RETRIEVAL_STATE_CONTRACT_ID == "quant-research.research-retrieval-state"
    assert RETRIEVAL_STATE_CONTRACT_VERSION == "v1"
    deliverable = {state for state, _c, ok, _p in RETRIEVAL_STATE_CONTRACT if ok}
    assert deliverable == {"complete", "complete_empty", "optional_scope_not_exhausted"}
    # Every state projects onto exactly one #397 coverage state, and no failure
    # state is ever allowed to project onto a "complete" one.
    for state, _category, ok, projection in RETRIEVAL_STATE_CONTRACT:
        assert state in RETRIEVAL_STATES
        assert projection in {
            "complete",
            "complete_empty",
            "optional_not_exhausted",
            "required_incomplete",
            "retrieval_failure",
        }
        if not ok:
            assert projection in {"required_incomplete", "retrieval_failure"}
    context = _freeze()
    assert context.readback()["state_contract_digest"] == RETRIEVAL_STATE_CONTRACT_DIGEST
    assert context.outcome.as_dict()["state_contract_version"] == "v1"


def test_the_state_contract_digest_moves_when_a_state_name_moves() -> None:
    from .research_pagination import _digest, _state_contract_dict

    baseline = _state_contract_dict()
    renamed = deepcopy(baseline)
    assert isinstance(renamed["states"], list)
    renamed["states"][0]["state"] = "complete_v2"
    assert _digest(renamed) != RETRIEVAL_STATE_CONTRACT_DIGEST
    assert _digest(baseline) == RETRIEVAL_STATE_CONTRACT_DIGEST


def test_every_reported_reason_and_detail_comes_from_the_frozen_vocabulary() -> None:
    scenarios = [
        _declaration(),
        _declaration(plan=_plan(page_budget=1)),
        _declaration(pages=[_page(0, [], status="interrupted")]),
        _declaration(pages=[_page(0, [], status="index_unavailable")]),
        _declaration(plan=_plan(record_budget=1)),
    ]
    for value in scenarios:
        context = freeze_paginated_research_context(value)
        assert set(context.outcome.failure_details) <= _FAILURE_DETAILS
        assert {entry.reason for entry in context.outcome.manifest} <= _RECORD_REASONS
        assert context.outcome.state in RETRIEVAL_STATES


# --- Required scope: fail closed ---------------------------------------------


def test_a_cursor_from_another_snapshot_is_refused() -> None:
    cursor = dict(_plan()["cursor"])  # type: ignore[arg-type]
    cursor["snapshot_id"] = "snapshot-2026-09-11"
    context = _freeze(plan=_plan(cursor=cursor))
    assert context.outcome.state == "cursor_invalidated"
    assert "cursor_snapshot_mismatch" in context.outcome.failure_details
    assert context.status == "refused"
    assert context.readback()["brief"] is None


def test_an_unknown_opening_cursor_is_refused_not_answered_empty() -> None:
    cursor = dict(_plan()["cursor"])  # type: ignore[arg-type]
    cursor["cursor_id"] = "cursor-elsewhere"
    context = _freeze(plan=_plan(cursor=cursor))
    assert context.outcome.state == "cursor_invalidated"
    assert "unreachable_page" in context.outcome.failure_details
    assert context.outcome.state != "complete_empty"
    assert context.outcome.pages_read == 0


def test_an_out_of_sequence_page_invalidates_the_cursor() -> None:
    pages = _pages()
    pages[1]["page_index"] = 7
    context = _freeze(pages=pages)
    assert context.outcome.state == "cursor_invalidated"
    assert "page_index_out_of_sequence" in context.outcome.failure_details


def test_a_page_that_overflows_the_declared_page_size_is_refused() -> None:
    pages = [
        _page(
            0,
            [
                _record("counter-1", "k-01"),
                _record("support-1", "k-02"),
                _record("experience-1", "k-03"),
            ],
            exhausted=True,
        )
    ]
    context = _freeze(pages=pages)
    assert context.outcome.state == "cursor_invalidated"
    assert "page_over_declared_size" in context.outcome.failure_details


def test_a_record_that_moves_backwards_in_the_frozen_ordering_is_refused() -> None:
    pages = _pages()
    pages[1]["records"] = [_record("support-1", "k-00")]
    context = _freeze(pages=pages)
    assert context.outcome.state == "cursor_invalidated"
    assert "record_ordering_violation" in context.outcome.failure_details


def test_an_interrupted_page_is_refused_and_never_an_optional_miss() -> None:
    pages = _pages()
    pages[1] = _page(1, [], status="interrupted")
    context = _freeze(pages=pages)
    assert context.outcome.state == "retrieval_interrupted"
    assert context.outcome.state != "optional_scope_not_exhausted"
    assert context.status == "refused"
    assert context.effective_coverage_state == "retrieval_failure"


def test_an_unavailable_index_is_refused_and_distinct_from_complete_empty() -> None:
    pages = _pages()
    pages[1] = _page(1, [], status="index_unavailable")
    unavailable = _freeze(pages=pages)
    assert unavailable.outcome.state == "index_unavailable"
    assert unavailable.status == "refused"

    empty = freeze_paginated_research_context(
        _declaration(
            context=_context(
                required_closure=[],
                optional_scope={"source_ids": [], "exhausted": True},
                sources=[],
                conclusions=[],
            ),
            pages=[_page(0, [], exhausted=True)],
        )
    )
    assert empty.outcome.state == "complete_empty"
    assert empty.status == "bounded"
    assert empty.identity != unavailable.identity


def test_a_record_published_after_the_snapshot_is_contamination_not_a_miss() -> None:
    pages = _pages()
    pages[1]["records"] = [_record("support-1", "k-03", "2026-09-12T00:00:00Z")]
    context = _freeze(pages=pages)
    assert context.outcome.state == "snapshot_contaminated"
    assert "record_after_snapshot_cutoff" in context.outcome.failure_details
    assert context.status == "refused"
    # The contaminating record was neither kept nor quietly discarded.
    assert context.readback()["brief"] is None


def test_an_exhausted_page_budget_is_never_reported_as_an_absent_record() -> None:
    context = _freeze(plan=_plan(page_budget=1))
    assert context.outcome.truncated is True
    assert context.outcome.state == "budget_exhausted"
    assert context.outcome.state != "required_lineage_missing"
    assert "page_budget_exhausted" in context.outcome.failure_details
    assert context.status == "refused"


def test_a_chain_that_never_says_it_is_exhausted_is_truncated_not_complete() -> None:
    pages = _pages()
    pages[1]["exhausted"] = False
    context = _freeze(pages=pages)
    assert context.outcome.truncated is True
    assert context.outcome.state == "optional_scope_not_exhausted"
    assert context.outcome.state != "complete"


def test_a_required_record_an_exhausted_chain_never_returned_is_missing_lineage() -> None:
    pages = [_page(0, [_record("counter-1", "k-01")], exhausted=True)]
    context = _freeze(pages=pages)
    assert context.outcome.state == "required_lineage_missing"
    assert context.outcome.required_unseen == ("support-1",)
    assert "required_records_never_paged" in context.outcome.failure_details
    assert context.status == "refused"


def test_a_failure_is_never_reclassified_as_optional_after_the_fact() -> None:
    pages = [_page(0, [_record("counter-1", "k-01")], exhausted=True)]
    failed = _freeze(pages=pages)
    assert failed.status == "refused"
    # Demoting the undelivered source to the optional scope produces a *different*
    # Context, so the refusal cannot be reissued under the original identity.
    demoted = freeze_paginated_research_context(
        _declaration(
            context=_context(
                required_closure=["counter-1"],
                optional_scope={"source_ids": ["experience-1", "support-1"], "exhausted": False},
                conclusions=[],
            ),
            pages=pages,
        )
    )
    assert demoted.identity != failed.identity
    assert demoted.context.identity != failed.context.identity
    assert failed.outcome.state == "required_lineage_missing"
    assert freeze_paginated_research_context(_declaration(pages=pages)).identity == failed.identity


def test_a_refusal_never_silently_shrinks_the_target_sample() -> None:
    complete = _freeze()
    truncated = _freeze(plan=_plan(page_budget=1))
    assert complete.status == "bounded"
    assert truncated.status == "refused"
    # The refused retrieval does not hand back a smaller but "successful" sample.
    assert truncated.readback()["brief"] is None
    assert truncated.readback()["retrieval"]["required_unseen"] == ["support-1"]


# --- Optional scope: bounded, with stated limitations -------------------------


def test_required_complete_but_optional_trimmed_produces_a_bounded_context() -> None:
    context = _freeze(plan=_plan(record_budget=2))
    assert context.outcome.state == "optional_scope_not_exhausted"
    assert context.status == "bounded"
    assert context.outcome.trimmed == ("experience-1",)
    entries = _entries(context)
    assert entries["support-1"] == ("retrieved", "declared_and_paged", "required")
    assert entries["counter-1"] == ("retrieved", "declared_and_paged", "required")
    assert entries["experience-1"] == ("trimmed", "optional_trimmed_by_policy", "optional")
    brief = context.readback()["brief"]
    assert brief is not None
    assert brief["status"] == "assembled"
    limitation_ids = [item["limitation_id"] for item in context.limitations()]
    assert "optional_trimmed:experience-1" in limitation_ids
    assert "retrieval_state:optional_scope_not_exhausted" in limitation_ids
    assert context.effective_coverage_state == "optional_not_exhausted"


def test_trimming_never_drops_a_required_record_to_fit() -> None:
    context = _freeze(plan=_plan(record_budget=1))
    assert context.outcome.state == "budget_exhausted"
    assert "record_budget_insufficient_for_required" in context.outcome.failure_details
    assert context.status == "refused"
    assert not any(
        entry.decision == "trimmed" and entry.role == "required"
        for entry in context.outcome.manifest
    )


def test_a_missing_required_counter_example_still_refuses_a_one_sided_conclusion() -> None:
    context = freeze_paginated_research_context(
        _declaration(
            context=_context(
                required_closure=["support-1"],
                sources=[
                    _source("support-1"),
                    _source("counter-1", approved=False),
                    _source("experience-1"),
                ],
            )
        )
    )
    assert context.outcome.state == "complete"
    brief = context.readback()["brief"]
    assert brief is not None
    assert brief["status"] == "blocked"
    assert "required_counter_evidence_unavailable" in brief["block_reasons"]
    assert brief["fields"]["conditional_conclusions"]["state"] == "unknown"


def test_an_undeclared_record_is_excluded_rather_than_smuggled_in() -> None:
    pages = _pages()
    pages[1]["records"] = [_record("support-1", "k-03"), _record("stray-1", "k-04")]
    context = _freeze(pages=pages)
    assert context.outcome.state == "complete"
    assert _entries(context)["stray-1"] == ("excluded", "outside_declared_scope", "undeclared")


# --- Identity and protected-side disclosure ----------------------------------


def test_the_identity_binds_the_plan_the_pages_and_the_outcome() -> None:
    base = _freeze()
    variants = [
        _declaration(plan=_plan(page_size=3)),
        _declaration(plan=_plan(page_budget=8)),
        _declaration(plan=_plan(record_budget=2)),
        _declaration(plan=_plan(retrieval_id="retrieval-2")),
        _declaration(plan=_plan(policy_version="v2")),
    ]
    cursor = dict(_plan()["cursor"])  # type: ignore[arg-type]
    cursor["position"] = "resumed"
    variants.append(_declaration(plan=_plan(cursor=cursor)))
    moved = _pages()
    moved[1]["records"] = [_record("support-1", "k-09")]
    variants.append(_declaration(pages=moved))
    identities = {base.identity}
    for variant in variants:
        identity = freeze_paginated_research_context(variant).identity
        assert identity != base.identity
        identities.add(identity)
    assert len(identities) == len(variants) + 1


def test_a_different_ordering_or_trimming_policy_is_a_different_context() -> None:
    base = _freeze()
    scope = dict(_context()["query_scope"])  # type: ignore[arg-type]
    scope["ordering"] = "ordering:published-at-v2"
    reordered = freeze_paginated_research_context(
        _declaration(
            context=_context(query_scope=scope),
            plan=_plan(ordering_key="ordering:published-at-v2"),
        )
    )
    assert reordered.identity != base.identity
    assert reordered.context.identity != base.context.identity


def test_a_plan_that_contradicts_the_declared_policy_is_refused_outright() -> None:
    with pytest.raises(RetrievalRefusal):
        _freeze(plan=_plan(ordering_key="ordering:something-else"))
    with pytest.raises(RetrievalRefusal):
        _freeze(plan=_plan(trimming_policy="trimming:something-else"))


def _protected_declaration() -> dict[str, object]:
    ids = ("support-1", "counter-1", "experience-1", "protected-1")
    pages = _pages()
    pages[1]["records"] = [_record("support-1", "k-03"), _record("protected-1", "k-04")]
    return _declaration(
        context=_context(
            visibility_request=_visibility_request(
                source_ids=ids, restricted=("protected-1",)
            )
        ),
        pages=pages,
    )


def test_protected_material_is_withheld_from_the_consumer_but_binds_the_identity() -> None:
    context = freeze_paginated_research_context(_protected_declaration())
    assert _entries(context)["protected-1"][:2] == ("excluded", "not_authorized")
    assert context.outcome.withheld is True

    audit = json.dumps(context.audit_readback())
    assert "protected-1" in audit

    delivered = deliver_paginated_research_brief(context, _visibility_request())
    assert delivered["delivery"] == "delivered"
    body = json.dumps(delivered)
    assert "protected-1" not in body
    assert delivered["retrieval"]["withheld"] == {"present": True, "reason": "not_authorized"}
    # No count of the withheld material is disclosed either.
    assert all(
        entry["reason"] != "not_authorized" for entry in delivered["retrieval"]["manifest"]
    )
    assert "protected_material_withheld" in [
        item["limitation_id"] for item in context.limitations()
    ]

    # The withheld entry still takes part in the identity, so a Context that
    # withheld nothing cannot pass itself off as this one.
    assert context.identity != _freeze().identity


def test_a_clean_context_does_not_claim_material_was_withheld() -> None:
    delivered = deliver_paginated_research_brief(_freeze(), _visibility_request())
    assert delivered["retrieval"]["withheld"] == {"present": False, "reason": "not_authorized"}


def test_no_readback_ever_claims_the_whole_store_was_scanned() -> None:
    context = _freeze()
    assert context.outcome.as_dict()["scanned_full_history"] is False
    assert context.outcome.as_dict()["declared_scope_only"] is True
    assert context.readback()["retrieval"]["scanned_full_history"] is False
    assert context.readback()["grants_eligibility"] is False


# --- Delivery: three distinct outcomes ---------------------------------------


def test_authorization_denial_and_retrieval_refusal_are_reported_separately() -> None:
    bounded = _freeze()
    denied = deliver_paginated_research_brief(bounded, _visibility_request(authorized=False))
    assert denied["delivery"] == "blocked"
    assert denied["reason"] == "current_authorization_denied"
    assert denied["paginated_identity"] is None
    assert denied["context_identity"] is None
    assert "retrieval" not in denied
    assert "brief" not in denied

    missing = _freeze(pages=[_page(0, [_record("counter-1", "k-01")], exhausted=True)])
    refused = deliver_paginated_research_brief(missing, _visibility_request())
    assert refused["delivery"] == "refused"
    assert refused["reason"] == "required_lineage_missing"
    assert refused["paginated_identity"] == missing.identity
    assert refused["brief"] is None

    delivered = deliver_paginated_research_brief(bounded, _visibility_request())
    assert delivered["delivery"] == "delivered"
    assert delivered["brief"] is not None
    assert delivered["paginated_identity"] == bounded.identity


# --- Reconstruction from frozen public facts ---------------------------------


def test_a_paginated_context_is_rebuilt_from_its_public_record_alone() -> None:
    context = _freeze(plan=_plan(record_budget=2))
    record = json.loads(json.dumps(context.public_record()))
    assert record["schema"] == PAGINATED_RECORD_SCHEMA
    rebuilt = reconstruct_paginated_research_context(record)
    assert rebuilt.identity == context.identity
    assert rebuilt.audit_readback() == context.audit_readback()


def test_dropping_every_projection_recovers_the_same_identity_and_content() -> None:
    context = _freeze()
    record = json.loads(json.dumps(context.public_record()))
    frozen = json.loads(json.dumps(context.audit_readback()))
    # Nothing but the public record survives: no full-text index, no graph, no
    # cached page buffer, no second retrieval authority.
    del context
    rebuilt = reconstruct_paginated_research_context(record)
    again = reconstruct_paginated_research_context(
        json.loads(json.dumps(rebuilt.public_record()))
    )
    assert again.identity == rebuilt.identity
    assert again.audit_readback() == frozen


def test_a_record_whose_frozen_pages_are_gone_fails_explicitly() -> None:
    context = _freeze()
    record = json.loads(json.dumps(context.public_record()))
    record["declaration"]["retrieval"]["pages"] = []
    with pytest.raises(RetrievalRefusal):
        reconstruct_paginated_research_context(record)

    stripped = json.loads(json.dumps(context.public_record()))
    del stripped["declaration"]["retrieval"]["plan"]
    with pytest.raises(AcceptanceFailure):
        reconstruct_paginated_research_context(stripped)


def test_history_cannot_be_patched_with_a_newer_retrieval_result() -> None:
    context = _freeze()
    record = json.loads(json.dumps(context.public_record()))
    record["declaration"]["retrieval"]["pages"][1]["records"].append(
        _record("experience-2", "k-04")
    )
    with pytest.raises(RetrievalRefusal):
        reconstruct_paginated_research_context(record)


def test_a_tampered_paginated_identity_is_refused() -> None:
    context = _freeze()
    record = json.loads(json.dumps(context.public_record()))
    record["paginated_identity"] = "sha256:" + "0" * 64
    with pytest.raises(RetrievalRefusal):
        reconstruct_paginated_research_context(record)


def test_the_module_opens_no_store_and_makes_no_external_call() -> None:
    from pathlib import Path

    source = Path(__file__).with_name("research_pagination.py").read_text(encoding="utf-8")
    for forbidden in (
        "import socket",
        "import sqlite3",
        "import urllib",
        "import requests",
        "import http",
        "subprocess",
        "open(",
    ):
        assert forbidden not in source, forbidden


# --- Determinism properties --------------------------------------------------


@given(
    seed=st.integers(min_value=0, max_value=64),
    repeats=st.integers(min_value=1, max_value=3),
)
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_page_order_and_repetition_never_change_the_frozen_output(
    seed: int, repeats: int
) -> None:
    """A reordered or repeated page delivery is the same retrieval."""

    pages = [
        _page(0, [_record("counter-1", "k-01"), _record("support-1", "k-02")]),
        _page(1, [_record("experience-1", "k-03")]),
        _page(2, [], exhausted=True),
    ]
    baseline = _freeze(pages=deepcopy(pages))
    shuffled = [deepcopy(page) for page in pages for _ in range(repeats)]
    offset = seed % len(shuffled)
    shuffled = shuffled[offset:] + shuffled[:offset]
    replayed = _freeze(pages=shuffled)
    assert replayed.identity == baseline.identity
    assert replayed.audit_readback() == baseline.audit_readback()
    assert baseline.outcome.state == "complete"


@given(field=st.sampled_from(["cursor_out", "exhausted", "records", "status"]))
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_a_conflicting_duplicate_page_is_always_refused(field: str) -> None:
    """Two different pages behind one cursor mean the ordering moved."""

    pages = _pages()
    twin = deepcopy(pages[0])
    if field == "cursor_out":
        twin["cursor_out"] = "cursor-9"
    elif field == "exhausted":
        twin["exhausted"] = True
    elif field == "status":
        twin["status"] = "interrupted"
    else:
        twin["records"] = [_record("counter-1", "k-01")]
    context = _freeze(pages=[*pages, twin])
    assert context.outcome.state == "cursor_invalidated"
    assert "conflicting_page_for_cursor" in context.outcome.failure_details
    assert context.status == "refused"


@given(mutation=st.sampled_from(["snapshot_id", "ordering_key", "cursor_id", "page_index"]))
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_an_invalid_cursor_is_always_refused(mutation: str) -> None:
    cursor = dict(_plan()["cursor"])  # type: ignore[arg-type]
    if mutation == "snapshot_id":
        cursor["snapshot_id"] = "snapshot-2026-09-11"
    elif mutation == "ordering_key":
        cursor["ordering_key"] = "ordering:other"
    elif mutation == "cursor_id":
        cursor["cursor_id"] = "cursor-nowhere"
    else:
        cursor["page_index"] = 5
    context = _freeze(plan=_plan(cursor=cursor))
    assert context.outcome.state == "cursor_invalidated"
    assert context.status == "refused"
    assert context.readback()["brief"] is None


@given(
    page=st.integers(min_value=0, max_value=1),
    stamp=st.sampled_from(["2026-09-10T00:00:01Z", "2026-09-11T00:00:00Z", "2027-01-01T00:00:00Z"]),
)
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_a_post_snapshot_record_is_always_refused(page: int, stamp: str) -> None:
    pages = _pages()
    records = pages[page]["records"]
    assert isinstance(records, list)
    records[0]["published_at"] = stamp
    context = _freeze(pages=pages)
    assert context.outcome.state == "snapshot_contaminated"
    assert context.status == "refused"


@given(
    page_budget=st.integers(min_value=1, max_value=4),
    record_budget=st.integers(min_value=1, max_value=6),
)
@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_budget_boundaries_never_turn_unread_into_absent(
    page_budget: int, record_budget: int
) -> None:
    context = _freeze(plan=_plan(page_budget=page_budget, record_budget=record_budget))
    if context.outcome.truncated:
        # Not having read to the end can never be reported as genuine absence,
        # and it can never be reported as complete.
        assert context.outcome.state != "required_lineage_missing"
        assert context.outcome.state not in {"complete", "complete_empty"}
    if context.outcome.state == "complete":
        assert context.outcome.required_unseen == ()
        assert context.outcome.trimmed == ()
    if record_budget < 2:
        assert context.outcome.state == "budget_exhausted"
    assert not any(
        entry.decision == "trimmed" and entry.role == "required"
        for entry in context.outcome.manifest
    )
    # Whatever the budget, the frozen output is a function of the budget alone.
    assert (
        _freeze(plan=_plan(page_budget=page_budget, record_budget=record_budget)).identity
        == context.identity
    )


# --- A0 reference acceptance slice -------------------------------------------
#
# These run on synthetic, #437-shaped, explicitly test-only records.  The A0
# fixture oracle (#434 / #437) is still `pending` in
# docs/research/a0/a0_delivery_index.json, so these assert the contract's shape
# on frozen stand-ins.  They claim no real A0 round and no model delivery.


def _a0_context(**overrides: object) -> dict[str, object]:
    value = _context(
        query_scope={
            "campaign_id": "a0-campaign",
            "iteration_id": "a0-round-2",
            "question_id": "a0-v0-vs-v1",
            "ordering": _ORDERING,
            "trimming": _TRIMMING,
        },
        required_closure=["a0-support-v1", "a0-counter-v1", "a0-limitation-cost"],
        optional_scope={"source_ids": ["a0-experience-v0"], "exhausted": True},
        sources=[
            _source("a0-support-v1"),
            _source("a0-counter-v1"),
            _source("a0-limitation-cost"),
            _source("a0-experience-v0"),
        ],
        owner_facts={
            "current_candidate": {
                "value": "a0-candidate-v1",
                "provenance": ["record:a0-candidate-v1"],
            },
            "baseline_condition": {"value": "a0-v0", "provenance": ["record:a0-v0"]},
            "must_not_claim": {
                "values": ["a0-real-round-executed"],
                "provenance": ["record:a0-scope"],
            },
        },
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
    )
    value.update(overrides)
    return value


def _a0_pages() -> list[dict[str, object]]:
    return [
        _page(0, [_record("a0-counter-v1", "k-01"), _record("a0-limitation-cost", "k-02")]),
        _page(1, [_record("a0-experience-v0", "k-03"), _record("a0-support-v1", "k-04")]),
        _page(2, [], exhausted=True),
    ]


def _a0_freeze(**overrides: object) -> PaginatedResearchContext:
    overrides.setdefault("context", _a0_context())
    overrides.setdefault("pages", _a0_pages())
    overrides.setdefault("plan", _plan(page_budget=4, record_budget=8))
    return freeze_paginated_research_context(_declaration(**overrides))


def test_a0_c02_a_missing_protection_lineage_blocks_the_round() -> None:
    pages = _a0_pages()
    pages[1]["records"] = [_record("a0-experience-v0", "k-03")]
    context = _a0_freeze(pages=pages)
    assert context.outcome.state == "required_lineage_missing"
    assert context.outcome.required_unseen == ("a0-support-v1",)
    assert context.status == "refused"
    assert context.readback()["brief"] is None


def test_a0_c02_an_invalid_cursor_or_insufficient_budget_blocks_the_round() -> None:
    cursor = dict(_plan()["cursor"])  # type: ignore[arg-type]
    cursor["snapshot_id"] = "a0-snapshot-other"
    invalid = _a0_freeze(plan=_plan(cursor=cursor))
    assert invalid.outcome.state == "cursor_invalidated"
    assert invalid.status == "refused"

    starved = _a0_freeze(plan=_plan(page_budget=4, record_budget=2))
    assert starved.outcome.state == "budget_exhausted"
    assert starved.status == "refused"
    assert "record_budget_insufficient_for_required" in starved.outcome.failure_details
    assert invalid.identity != starved.identity


def test_a0_c02_required_complete_optional_limited_is_honest_not_empty() -> None:
    context = _a0_freeze(plan=_plan(page_budget=4, record_budget=3))
    assert context.outcome.state == "optional_scope_not_exhausted"
    assert context.status == "bounded"
    assert context.outcome.trimmed == ("a0-experience-v0",)
    assert context.outcome.state != "complete_empty"
    brief = context.readback()["brief"]
    assert brief is not None
    assert brief["status"] == "assembled"
    unit = brief["fields"]["conditional_conclusions"]["entries"][0]
    # The favourable conclusion never travels without its counter-evidence.
    assert unit["required_counter_evidence"] == ["a0-counter-v1"]
    assert unit["limitations"] == ["a0-limitation-cost"]
    limitation_ids = [item["limitation_id"] for item in context.limitations()]
    assert "optional_trimmed:a0-experience-v0" in limitation_ids
    assert "a0-real-round-executed" in brief["fields"]["must_not_claim"]["values"]


def test_a0_c02_a_failed_round_is_never_relabelled_complete_empty() -> None:
    for context in (
        _a0_freeze(pages=[_page(0, [], status="index_unavailable")]),
        _a0_freeze(plan=_plan(page_budget=1, record_budget=8)),
    ):
        assert context.outcome.state != "complete_empty"
        assert context.status == "refused"
        assert context.effective_coverage_state in {"retrieval_failure", "required_incomplete"}


def test_a0_h02_the_same_context_is_recovered_after_the_projection_is_deleted() -> None:
    context = _a0_freeze(plan=_plan(page_budget=4, record_budget=3))
    frozen_identity = context.identity
    frozen_readback = json.loads(json.dumps(context.audit_readback()))
    record = json.loads(json.dumps(context.public_record()))

    # Reordering the delivered pages and losing every derived projection.
    shuffled = list(reversed(deepcopy(_a0_pages())))
    replayed = _a0_freeze(plan=_plan(page_budget=4, record_budget=3), pages=shuffled)
    assert replayed.identity == frozen_identity

    del context
    rebuilt = reconstruct_paginated_research_context(record)
    assert rebuilt.identity == frozen_identity
    assert rebuilt.audit_readback() == frozen_readback
    assert rebuilt.plan.cursor.snapshot_id == _SNAPSHOT_ID


def test_a0_h02_a_latest_reselection_cannot_impersonate_the_frozen_context() -> None:
    context = _a0_freeze(plan=_plan(page_budget=4, record_budget=3))
    record = json.loads(json.dumps(context.public_record()))
    record["declaration"]["retrieval"]["pages"][1]["records"].append(
        _record("a0-latest-v2", "k-05")
    )
    with pytest.raises(RetrievalRefusal):
        reconstruct_paginated_research_context(record)


def test_a0_h02_authorization_restriction_and_fact_absence_are_separate() -> None:
    bounded = _a0_freeze()
    denied = deliver_paginated_research_brief(bounded, _visibility_request(authorized=False))
    assert denied["delivery"] == "blocked"
    assert denied["reason"] == "current_authorization_denied"
    assert denied["paginated_identity"] is None

    pages = _a0_pages()
    pages[1]["records"] = [_record("a0-experience-v0", "k-03")]
    absent = _a0_freeze(pages=pages)
    missing = deliver_paginated_research_brief(absent, _visibility_request())
    assert missing["delivery"] == "refused"
    assert missing["reason"] == "required_lineage_missing"
    assert missing["retrieval"]["required_unseen"] == ["a0-support-v1"]
    assert missing["reason"] != denied["reason"]


def test_a0_the_public_pagination_inputs_and_outputs_are_the_submitted_evidence() -> None:
    context = _a0_freeze(plan=_plan(page_budget=4, record_budget=3))
    readback = context.readback()
    assert readback["plan"]["page_size"] == 2
    assert readback["plan"]["page_budget"] == 4
    assert readback["plan"]["record_budget"] == 3
    assert readback["plan"]["ordering_key"] == _ORDERING
    assert readback["plan"]["trimming_policy"] == _TRIMMING
    assert readback["snapshot"]["snapshot_id"] == _SNAPSHOT_ID
    assert readback["retrieval"]["pages_read"] == 3
    assert readback["retrieval"]["state"] == "optional_scope_not_exhausted"
    assert readback["retrieval"]["trimmed"] == ["a0-experience-v0"]
    assert readback["effective_coverage_state"] == "optional_not_exhausted"
    assert readback["paginated_identity"] == context.identity
