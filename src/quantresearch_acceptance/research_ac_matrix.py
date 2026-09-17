"""#404 RM-V1D.2: the RM-AC01-RM-AC18 traceability matrix, as an executable record.

This module is a *rollup*, not new business logic.  It carries no research
semantics of its own: every acceptance item points at the module that owns the
behaviour and at the test that already proves it, and the accompanying test file
resolves every one of those pointers against the real test functions, so a
renamed or deleted test breaks the matrix instead of silently leaving an
acceptance item uncovered.

Provenance of the RM-AC numbering — read this before trusting the titles
--------------------------------------------------------------------------
The **verbatim** RM-AC01-RM-AC18 text is not published anywhere this repository
or the issue tracker can read.  #381, #383-#386, #404, #431 and #437 all
*reference* the numbering ("保留 RM-AC01-RM-AC18 编号") and none of them
enumerates it.  A search of the tracker and of `artifacts/` and `docs/` returns
no list.

So the titles below are **reconstructed from the published enumeration** that
#381, #386 and #404 give of the same comprehensive fixture — the eleven named
scenarios (success / failure siblings, data-blocked, unknown, counter-evidence,
duplicate summary, protected derivation, superseding correction, delivery
interruption, cache deletion, prompt injection / secrets), replay, and the seven
groups #404's R2 revision adds — laid out in the order those documents state
them.  Eighteen slots, in the published order, nothing dropped and nothing
renumbered.

`MATRIX_PROVENANCE` states this in the public readback, so no consumer can
mistake a reconstruction for the owner's verbatim list.  If the owner later
publishes the original text, the fix is to re-title these items in place: the
ids, their order and their evidence stay as they are.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

#: Schema of the public readback this module produces.
AC_MATRIX_SCHEMA = "quantresearch.research.ac_matrix/v1"

#: How the RM-AC titles below were arrived at.  Published in every readback.
MATRIX_PROVENANCE = (
    "reconstructed_from_published_enumeration: the verbatim RM-AC01-RM-AC18 list is "
    "unpublished in #381/#383-#386/#404/#431/#437 and absent from this repository; the "
    "titles restate the comprehensive-fixture enumeration those issues do publish, in "
    "their published order, with no item deleted and no id renumbered"
)

EvidenceKind = Literal["offline_regression", "real_connected"]


@dataclass(frozen=True, slots=True)
class TestRef:
    """One test that is claimed as evidence, addressed so it can be resolved."""

    module: str
    test: str

    def as_dict(self) -> dict[str, object]:
        return {"module": self.module, "test": self.test}


@dataclass(frozen=True, slots=True)
class AcceptanceItem:
    """One original RM-AC item, its R2 requirement, and its evidence."""

    ac_id: str
    title: str
    r2_requirement: str
    owner_issue: str
    evidence: tuple[TestRef, ...]
    kind: EvidenceKind = "offline_regression"

    def as_dict(self) -> dict[str, object]:
        return {
            "ac_id": self.ac_id,
            "title": self.title,
            "r2_requirement": self.r2_requirement,
            "owner_issue": self.owner_issue,
            "kind": self.kind,
            "evidence": [ref.as_dict() for ref in self.evidence],
        }


@dataclass(frozen=True, slots=True)
class JointScenario:
    """One U1-U6 joint scenario shared with Genome #429."""

    scenario_id: str
    title: str
    expected_observable: str
    acceptance_ids: tuple[str, ...]
    evidence: tuple[TestRef, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "title": self.title,
            "expected_observable": self.expected_observable,
            "acceptance_ids": list(self.acceptance_ids),
            "evidence": [ref.as_dict() for ref in self.evidence],
        }


@dataclass(frozen=True, slots=True)
class A0Item:
    """One A0 reference-acceptance scenario from #431's catalogue."""

    item_id: str
    must_assert: str
    acceptance_ids: tuple[str, ...]
    scenario_ids: tuple[str, ...]
    owner_issue: str
    status: Literal["executed", "not_run"]
    evidence: tuple[TestRef, ...]
    note: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "item_id": self.item_id,
            "must_assert": self.must_assert,
            "acceptance_ids": list(self.acceptance_ids),
            "scenario_ids": list(self.scenario_ids),
            "owner_issue": self.owner_issue,
            "status": self.status,
            "evidence": [ref.as_dict() for ref in self.evidence],
            "note": self.note,
        }


_VIS = "_research_visibility_test"
_EXP = "_research_exposure_test"
_CTX = "_research_context_test"
_PAG = "_research_pagination_test"
_DEC = "_research_decision_test"
_CUR = "_research_currency_test"
_R2 = "_research_a0_round2_test"
_MTX = "_research_ac_matrix_test"


def _refs(module: str, *tests: str) -> tuple[TestRef, ...]:
    """Evidence for one module, written so a long test name still fits a line."""

    return tuple(TestRef(module, test) for test in tests)


RM_ACCEPTANCE_MATRIX: tuple[AcceptanceItem, ...] = (
    AcceptanceItem(
        ac_id="RM-AC01",
        title="success sibling: a supported conclusion ships with its support and limitations",
        r2_requirement="RM-R2-1 Finding keeps scope, source, evidence tier and limitations",
        owner_issue="#397",
        evidence=(
            *_refs(
                _CTX,
                "test_a_conclusion_ships_with_its_support_counter_evidence_and_limitations",
                "test_the_brief_carries_every_fixed_field_with_provenance_or_unknown",
            ),
        ),
    ),
    AcceptanceItem(
        ac_id="RM-AC02",
        title="failure sibling: a failure keeps its real cause and is never downgraded",
        r2_requirement="RM-R2-1 reuse the existing failure classification",
        owner_issue="#397/#398",
        evidence=(
            *_refs(
                _CTX,
                "test_a_retrieval_failure_is_never_downgraded_to_an_optional_miss",
            ),
            *_refs(
                _PAG,
                "test_a_failure_is_never_reclassified_as_optional_after_the_fact",
            ),
        ),
    ),
    AcceptanceItem(
        ac_id="RM-AC03",
        title="data-blocked is not strategy-invalid",
        r2_requirement="RM-R2-1 a data block is never written up as the strategy failing",
        owner_issue="#399",
        evidence=(
            *_refs(
                _DEC,
                "test_an_unrepaired_data_blocker_blocks_without_claiming_falsification",
                "test_a_repaired_blocker_with_an_owner_permitted_condition_proceeds",
            ),
        ),
    ),
    AcceptanceItem(
        ac_id="RM-AC04",
        title="unknown / not_evaluated stays explicit and is never invented",
        r2_requirement="RM-R2-1 known/unknown/not_applicable/not_evaluated keep their meanings",
        owner_issue="#397",
        evidence=(
            *_refs(
                _CTX,
                "test_an_absent_owner_fact_is_unknown_and_never_invented",
                "test_an_unknown_alignment_is_a_gap_and_not_an_alignment",
            ),
            *_refs(
                _CUR,
                "test_an_unknown_dependency_is_needs_review_and_never_invalidates_downstream",
            ),
        ),
    ),
    AcceptanceItem(
        ac_id="RM-AC05",
        title="counter-evidence stays visible next to support and is never trimmed away",
        r2_requirement="RM-R2-3 a required counter-example may not be squeezed out by budget",
        owner_issue="#397/#398",
        evidence=(
            *_refs(
                _CTX,
                "test_a_conclusion_whose_counter_evidence_is_unavailable_is_not_delivered",
                "test_a0_m02_a_tight_budget_never_buys_room_by_dropping_counter_evidence",
            ),
            *_refs(
                _PAG,
                "test_a_missing_required_counter_example_still_refuses_a_one_sided_conclusion",
            ),
        ),
    ),
    AcceptanceItem(
        ac_id="RM-AC06",
        title="duplicate same-source summaries add no independent verification",
        r2_requirement="RM-R2-5 source-dependency dedup is not the selection history",
        owner_issue="#393/#396",
        evidence=(
            *_refs(
                _EXP,
                "test_a0_m03_downstream_stop_decision_links_context_exposure_and_test_family",
                "test_usage_history_publishes_relations_without_granting_eligibility",
            ),
            *_refs(
                _CTX,
                "test_duplicate_source_ids_are_refused",
            ),
        ),
    ),
    AcceptanceItem(
        ac_id="RM-AC07",
        title="protected material and its derivations are blocked before any unauthorized read",
        r2_requirement="RM-R2-6 protection is enforced ahead of the consumer, and leaks nothing",
        owner_issue="#394/#395",
        evidence=(
            *_refs(
                _VIS,
                "test_protected_lineage_is_denied_before_consumer_read",
                "test_a0_p01_derived_artifacts_are_blocked_before_any_consumer_read",
                "test_multi_hop_derivation_cannot_launder_a_protected_source",
                "test_restricted_output_cannot_reveal_material_ids_counts_or_lineage",
            ),
        ),
    ),
    AcceptanceItem(
        ac_id="RM-AC08",
        title="a superseding correction reaches the current view without editing the old one",
        r2_requirement="RM-R2-6 a correction marks impact; only the owner refreshes currency",
        owner_issue="#401",
        evidence=(
            *_refs(
                _CUR,
                "test_a0_h01_a_correction_updates_the_current_brief_without_touching_the_old_one",
                "test_only_owner_evidence_or_decision_refreshes_formal_currency",
                "test_a_new_summary_or_explanation_never_refreshes_formal_currency",
            ),
        ),
    ),
    AcceptanceItem(
        ac_id="RM-AC09",
        title="an interrupted delivery stays uncertain, is never washed back to unseen or resent "
        "blind",
        r2_requirement="RM-R2-7 prepared is not delivered; a receipt is not model cognition",
        owner_issue="#396",
        evidence=(
            *_refs(
                _EXP,
                "test_uncertain_delivery_never_claims_non_exposure_and_forbids_blind_resend",
                "test_a_torn_tail_leaves_a_prepared_action_uncertain_not_unseen",
                "test_a_confirmed_delivery_cannot_be_returned_to_uncertain",
            ),
        ),
    ),
    AcceptanceItem(
        ac_id="RM-AC10",
        title="deleting every derived projection still rebuilds the same identity and content",
        r2_requirement="RM-R2-3/6 projections are droppable; the public record is authoritative",
        owner_issue="#398/#401",
        evidence=(
            *_refs(
                _CTX,
                "test_dropping_every_derived_projection_still_recovers_identity_and_content",
            ),
            *_refs(
                _PAG,
                "test_a0_h02_the_same_context_is_recovered_after_the_projection_is_deleted",
            ),
            *_refs(
                _CUR,
                "test_deleting_the_display_projection_loses_nothing",
            ),
            *_refs(
                _MTX,
                "test_u6_rebuild_after_deletion_costs_no_run_llm_call_or_budget",
            ),
        ),
    ),
    AcceptanceItem(
        ac_id="RM-AC11",
        title="prompt injection, secrets, private paths and tool-control text never gain execution",
        r2_requirement="#404 AC2 fixture text must not be interpreted as an instruction",
        owner_issue="#404",
        evidence=(
            *_refs(
                _MTX,
                "test_injected_instruction_text_is_data_and_changes_no_decision",
                "test_a_private_path_shaped_identifier_is_never_opened",
                "test_no_production_module_has_an_execution_seam_for_injected_text",
            ),
            *_refs(
                _EXP,
                "test_the_event_record_cannot_carry_secrets_or_free_text",
            ),
            *_refs(
                _R2,
                "test_a0_e02_an_authorization_declaration_may_never_carry_a_credential",
            ),
        ),
    ),
    AcceptanceItem(
        ac_id="RM-AC12",
        title="replay reproduces the frozen decision, and limited coverage is stated honestly",
        r2_requirement="RM-R2-7 a digest is not the body; replay coverage is declared, not assumed",
        owner_issue="#396/#399/#401",
        evidence=(
            *_refs(
                _DEC,
                "test_a_decision_is_replayed_from_its_frozen_public_record",
                "test_a_doctored_decision_record_fails_loudly",
            ),
            *_refs(
                _EXP,
                "test_a_missing_payload_yields_only_a_limited_reconstruction",
            ),
            *_refs(
                _CUR,
                "test_a_digest_is_never_presented_as_the_delivered_content",
            ),
        ),
    ),
    AcceptanceItem(
        ac_id="RM-AC13",
        title="same-action retry, same-key conflict and true duplicate are three separate branches",
        r2_requirement="RM-R2-2 request idempotency is not run reuse is not research duplication",
        owner_issue="#399",
        evidence=(
            *_refs(
                _DEC,
                "test_the_readback_reports_three_decisions_not_one_flag",
                "test_a_retry_of_the_same_action_recovers_instead_of_re_executing",
                "test_the_same_key_with_a_different_input_is_rejected",
                "test_a_true_duplicate_stops_before_context_budget_run_and_call",
            ),
            *_refs(
                _R2,
                "test_a0_r01_retry_conflict_and_duplicate_stop_each_have_their_own_branch",
            ),
        ),
    ),
    AcceptanceItem(
        ac_id="RM-AC14",
        title="dedup neither wipes selection history nor wrongly blocks legitimate new research",
        r2_requirement="RM-R2-2/5 a new protocol attaches; a new sample is new research",
        owner_issue="#399",
        evidence=(
            *_refs(
                _DEC,
                "test_a_new_statistical_protocol_attaches_to_the_run_and_still_judges_afresh",
                "test_a_legitimate_new_sample_is_not_blocked_by_a_matching_genome",
                "test_a_new_campaign_never_resets_the_test_family",
                "test_a0_u1_u3_miscall_run_reuse_and_external_call_counts",
            ),
            *_refs(
                _EXP,
                "test_usage_history_is_not_cleared_by_a_later_campaign",
            ),
        ),
    ),
    AcceptanceItem(
        ac_id="RM-AC15",
        title="required closure fails closed; optional scope is bounded and reported, never faked "
        "empty",
        r2_requirement="RM-R2-3 declare the scope first, then prove the closure is complete",
        owner_issue="#398",
        evidence=(
            *_refs(
                _PAG,
                "test_an_unavailable_index_is_refused_and_distinct_from_complete_empty",
                "test_a0_c02_required_complete_optional_limited_is_honest_not_empty",
                "test_a0_c02_a_failed_round_is_never_relabelled_complete_empty",
            ),
            *_refs(
                _CTX,
                "test_an_exhausted_closure_budget_is_incomplete_not_empty",
            ),
        ),
    ),
    AcceptanceItem(
        ac_id="RM-AC16",
        title="a required unit is blocked rather than shipped stripped, and a failure stays a "
        "failure",
        r2_requirement="RM-R2-3 the unit is conclusion + required support/counter + limits",
        owner_issue="#397/#398",
        evidence=(
            *_refs(
                _CTX,
                "test_a_small_budget_blocks_a_required_unit_instead_of_dropping_its_evidence",
                "test_an_optional_unit_missing_its_evidence_is_dropped_not_degraded",
            ),
            *_refs(
                _PAG,
                "test_trimming_never_drops_a_required_record_to_fit",
                "test_a_refusal_never_silently_shrinks_the_target_sample",
            ),
        ),
    ),
    AcceptanceItem(
        ac_id="RM-AC17",
        title="every brief field has provenance or unknown; a single-component diff claims no "
        "cause",
        r2_requirement="RM-R2-4 fixed versioned projection, deterministic rules, consumed diff",
        owner_issue="#397",
        evidence=(
            *_refs(
                _CTX,
                "test_an_owner_fact_without_provenance_is_refused",
                "test_a_gap_carries_its_preconditions",
                "test_a_next_step_without_preconditions_is_refused",
                "test_a_misaligned_single_component_comparison_reports_the_gap_first",
            ),
            *_refs(
                _MTX,
                "test_u4_single_component_comparison_keeps_the_gap_and_claims_no_cause",
            ),
        ),
    ),
    AcceptanceItem(
        ac_id="RM-AC18",
        title="historical and current views stay apart, and every read rechecks current "
        "authorization",
        r2_requirement="RM-R2-6 old policy never restores old access; no hindsight backfill",
        owner_issue="#394/#401",
        evidence=(
            *_refs(
                _CUR,
                "test_a_correction_published_later_is_invisible_to_an_older_cutoff",
                "test_an_old_snapshot_projection_shows_no_hindsight_and_a_new_one_does",
                "test_a_currently_unauthorized_reader_cannot_re_read_via_the_old_policy",
            ),
            *_refs(
                _VIS,
                "test_revoked_current_access_blocks_historical_redelivery_without_rewriting_context",
            ),
            *_refs(
                _EXP,
                "test_a_currently_unauthorized_party_cannot_replay_historical_content",
            ),
        ),
    ),
)


JOINT_SCENARIOS: tuple[JointScenario, ...] = (
    JointScenario(
        scenario_id="U1",
        title="等价失败方向换名再提",
        expected_observable="the same question and real failure cause are recognised; no "
        "equivalent "
        "work is paid for again, and the block is not a natural-language similarity match",
        acceptance_ids=("RM-AC02", "RM-AC13"),
        evidence=(
            *_refs(
                _DEC,
                "test_a_renamed_equivalent_request_is_still_a_duplicate",
                "test_a0_u1_u3_miscall_run_reuse_and_external_call_counts",
            ),
        ),
    ),
    JointScenario(
        scenario_id="U2",
        title="数据问题修复",
        expected_observable="the old blocker is kept; a governed retry under a new owner-permitted "
        "condition proceeds; the old fault never becomes a permanent verdict on the strategy",
        acceptance_ids=("RM-AC03", "RM-AC14"),
        evidence=(
            *_refs(
                _DEC,
                "test_a_repaired_blocker_with_an_owner_permitted_condition_proceeds",
                "test_a_repair_the_owner_did_not_permit_does_not_proceed",
                "test_a0_u1_u3_miscall_run_reuse_and_external_call_counts",
            ),
        ),
    ),
    JointScenario(
        scenario_id="U3",
        title="同策略合法新样本复验",
        expected_observable="not caught by Genome-level dedup; only an exact input match reuses a "
        "run; independence stays the statistical owner's call",
        acceptance_ids=("RM-AC14",),
        evidence=(
            *_refs(
                _DEC,
                "test_a_legitimate_new_sample_is_not_blocked_by_a_matching_genome",
                "test_a_genome_match_alone_is_not_a_run_match",
                "test_a0_u1_u3_miscall_run_reuse_and_external_call_counts",
            ),
        ),
    ),
    JointScenario(
        scenario_id="U4",
        title="单组件对照",
        expected_observable="the difference, the verified-unchanged scope, the comparison "
        "conditions "
        "and the required counter-evidence are all kept; with conditions unaligned no cause is "
        "claimed",
        acceptance_ids=("RM-AC05", "RM-AC17"),
        evidence=(
            *_refs(
                _MTX,
                "test_u4_single_component_comparison_keeps_the_gap_and_claims_no_cause",
            ),
            *_refs(
                _CTX,
                "test_a_misaligned_single_component_comparison_reports_the_gap_first",
                "test_genome_compare_is_consumed_and_never_recomputed",
            ),
        ),
    ),
    JointScenario(
        scenario_id="U5",
        title="来源纠正",
        expected_observable="the new brief uses the current correction and currency; the old "
        "Context "
        "keeps its as-of identity and content",
        acceptance_ids=("RM-AC08", "RM-AC18"),
        evidence=(
            *_refs(
                _CUR,
                "test_a0_u5_and_limited_replay_coverage_pass_through_public_readback_only",
                "test_the_old_context_keeps_its_identity_and_policy_after_a_correction",
            ),
        ),
    ),
    JointScenario(
        scenario_id="U6",
        title="删除投影后重建",
        expected_observable="the same identity and content boundary are rebuilt from the frozen "
        "public facts, with no new backtest, LLM call or budget reservation",
        acceptance_ids=("RM-AC10", "RM-AC12"),
        evidence=(
            *_refs(
                _MTX,
                "test_u6_rebuild_after_deletion_costs_no_run_llm_call_or_budget",
            ),
            *_refs(
                _PAG,
                "test_a0_h02_the_same_context_is_recovered_after_the_projection_is_deleted",
            ),
            *_refs(
                _CTX,
                "test_dropping_every_derived_projection_still_recovers_identity_and_content",
            ),
        ),
    ),
)


A0_REFERENCE_ITEMS: tuple[A0Item, ...] = (
    A0Item(
        item_id="A0-M01",
        must_assert="a Finding carries scope, evidence type and gaps; a data block is not "
        "invalidity",
        acceptance_ids=("RM-AC01", "RM-AC03", "RM-AC04"),
        scenario_ids=("U1", "U2"),
        owner_issue="#391",
        status="executed",
        evidence=(
            *_refs(
                _CTX,
                "test_the_brief_carries_every_fixed_field_with_provenance_or_unknown",
            ),
            *_refs(
                _DEC,
                "test_an_unrepaired_data_blocker_blocks_without_claiming_falsification",
            ),
        ),
        note="specified in #431's scenario catalogue; consumed here, not redefined",
    ),
    A0Item(
        item_id="A0-M02",
        must_assert="same-scope support and counter-evidence are kept; a single-component diff is "
        "not a causal claim",
        acceptance_ids=("RM-AC05", "RM-AC17"),
        scenario_ids=("U4",),
        owner_issue="#392/#397",
        status="executed",
        evidence=(
            *_refs(
                _CTX,
                "test_a0_m02_unaligned_cost_keeps_limitations_and_refuses_a_causal_claim",
            ),
            *_refs(
                _MTX,
                "test_u4_single_component_comparison_keeps_the_gap_and_claims_no_cause",
            ),
        ),
    ),
    A0Item(
        item_id="A0-M03",
        must_assert="many summaries of one run do not inflate independence; a new Campaign erases "
        "no "
        "selection or test family",
        acceptance_ids=("RM-AC06", "RM-AC14"),
        scenario_ids=("U3",),
        owner_issue="#393/#396",
        status="executed",
        evidence=(
            *_refs(
                _EXP,
                "test_a0_m03_downstream_stop_decision_links_context_exposure_and_test_family",
            ),
            *_refs(
                _DEC,
                "test_a_new_campaign_never_resets_the_test_family",
            ),
        ),
        note="#393 is owned outside this repository and is consumed by reference",
    ),
    A0Item(
        item_id="A0-P01",
        must_assert="direct and derived protection block before any unauthorized consumer read; "
        "reasons, counts and logs leak nothing",
        acceptance_ids=("RM-AC07", "RM-AC11"),
        scenario_ids=(),
        owner_issue="#394/#395",
        status="executed",
        evidence=(
            *_refs(
                _VIS,
                "test_a0_p01_derived_artifacts_are_blocked_before_any_consumer_read",
            ),
            *_refs(
                _R2,
                "test_a0_p01_the_visibility_gate_stops_the_round_before_any_spend",
            ),
        ),
        note="manual test-only protection records; never a real holdout",
    ),
    A0Item(
        item_id="A0-P02",
        must_assert="Context and the final envelope / tool input stay distinguishable; uncertain "
        "never becomes unseen and is never resent blind",
        acceptance_ids=("RM-AC09", "RM-AC12"),
        scenario_ids=(),
        owner_issue="#396",
        status="executed",
        evidence=(
            *_refs(
                _EXP,
                "test_a0_p02_second_round_envelope_differs_from_context_and_loses_its_receipt",
            ),
            *_refs(
                _R2,
                "test_a0_p02_an_uncertain_delivery_is_reconciled_and_never_resent",
            ),
        ),
    ),
    A0Item(
        item_id="A0-C01",
        must_assert="the second-round brief keeps baseline, counter-evidence, gaps, assets, "
        "next-step "
        "preconditions and must-not-claim, each field with a source",
        acceptance_ids=("RM-AC01", "RM-AC17"),
        scenario_ids=("U4",),
        owner_issue="#397/#401",
        status="executed",
        evidence=(
            *_refs(
                _CTX,
                "test_a0_c01_second_round_brief_has_every_field_with_provenance_or_unknown",
            ),
            *_refs(
                _CUR,
                "test_a0_c01_l02_reporting_source_is_published_only_and_revocation_blocks_redelivery",
            ),
        ),
    ),
    A0Item(
        item_id="A0-C02",
        must_assert="a missing required closure refuses; optional scope stays inside its declared "
        "bound; no required counter-evidence trimmed and no fake-empty on failure",
        acceptance_ids=("RM-AC15", "RM-AC16"),
        scenario_ids=(),
        owner_issue="#395/#398",
        status="executed",
        evidence=(
            *_refs(
                _PAG,
                "test_a0_c02_required_complete_optional_limited_is_honest_not_empty",
                "test_a0_c02_a_failed_round_is_never_relabelled_complete_empty",
                "test_a0_c02_a_missing_protection_lineage_blocks_the_round",
            ),
        ),
    ),
    A0Item(
        item_id="A0-R01",
        must_assert="a true research duplicate stops before the engine Context, the paid budget "
        "and "
        "the call; a request retry reconciles instead",
        acceptance_ids=("RM-AC13",),
        scenario_ids=("U1",),
        owner_issue="#399",
        status="executed",
        evidence=(
            *_refs(
                _DEC,
                "test_a0_r01_retry_reconciles_conflict_rejects_and_duplicate_stops",
            ),
            *_refs(
                _R2,
                "test_a0_r01_retry_conflict_and_duplicate_stop_each_have_their_own_branch",
            ),
        ),
    ),
    A0Item(
        item_id="A0-R02",
        must_assert="a new protocol attaches to the same execution; a legitimate new sample is not "
        "blocked by Genome dedup; a repaired blocker proceeds on the new condition",
        acceptance_ids=("RM-AC14", "RM-AC03"),
        scenario_ids=("U2", "U3"),
        owner_issue="#399",
        status="executed",
        evidence=(
            *_refs(
                _DEC,
                "test_a0_r02_attach_new_sample_and_blocker_recovery_stay_separate",
            ),
            *_refs(
                _R2,
                "test_a0_r02_attach_and_legitimate_new_sample_stay_separate_branches",
            ),
        ),
    ),
    A0Item(
        item_id="A0-H01",
        must_assert="a correction changes the current brief without touching the old knowledge "
        "snapshot; currency stays the original owner's decision",
        acceptance_ids=("RM-AC08", "RM-AC18"),
        scenario_ids=("U5",),
        owner_issue="#401",
        status="executed",
        evidence=(
            *_refs(
                _CUR,
                "test_a0_h01_a_correction_updates_the_current_brief_without_touching_the_old_one",
                "test_a0_u5_and_limited_replay_coverage_pass_through_public_readback_only",
            ),
        ),
    ),
    A0Item(
        item_id="A0-H02",
        must_assert="after the projection is cleared the context rebuilds from the old facts, "
        "current "
        "authorization is still checked, and zero new backtest / LLM / budget occurs",
        acceptance_ids=("RM-AC10", "RM-AC12", "RM-AC18"),
        scenario_ids=("U6",),
        owner_issue="#398/#408",
        status="executed",
        evidence=(
            *_refs(
                _PAG,
                "test_a0_h02_the_same_context_is_recovered_after_the_projection_is_deleted",
                "test_a0_h02_authorization_restriction_and_fact_absence_are_separate",
            ),
            *_refs(
                _MTX,
                "test_u6_rebuild_after_deletion_costs_no_run_llm_call_or_budget",
            ),
        ),
        note="#408 owns the full recovery slice; this is the #404 mapping only",
    ),
    A0Item(
        item_id="A0-E01",
        must_assert="a real V0/V1 normal research round runs end to end on real data",
        acceptance_ids=("RM-AC01", "RM-AC02"),
        scenario_ids=(),
        owner_issue="#441",
        status="not_run",
        evidence=(),
        note="#441 landed no commit in this repository and published no round-one asset; "
        "`A0-ROUND-1` is still pending in docs/research/a0/a0_delivery_index.json. No offline "
        "fixture substitutes for it.",
    ),
    A0Item(
        item_id="A0-E02",
        must_assert="the second round really reads the first round's assets through an authorized "
        "model request, response, Context, Exposure and decision",
        acceptance_ids=("RM-AC09", "RM-AC12"),
        scenario_ids=(),
        owner_issue="#442",
        status="not_run",
        evidence=(
            *_refs(
                _R2,
                "test_a0_e02_reports_not_run_and_never_claims_model_use",
            ),
        ),
        note="#442 confirmed no owner-authorized ResearchEnginePort configuration exists. The "
        "listed test is evidence that the `not_run` status is reported honestly — it is NOT "
        "evidence that the criterion is satisfied.",
    ),
)


def acceptance_ids() -> tuple[str, ...]:
    return tuple(item.ac_id for item in RM_ACCEPTANCE_MATRIX)


def evidence_refs(items: Iterable[AcceptanceItem | JointScenario | A0Item]) -> tuple[TestRef, ...]:
    """Every distinct test reference claimed by the given items, in stable order."""

    seen: dict[tuple[str, str], TestRef] = {}
    for item in items:
        for ref in item.evidence:
            seen.setdefault((ref.module, ref.test), ref)
    return tuple(seen[key] for key in sorted(seen))


def unmapped_acceptance_ids() -> tuple[str, ...]:
    """RM-AC ids that no U1-U6 scenario and no A0 item points at.

    It currently returns nothing: every one of the eighteen items is reachable
    from a joint scenario or an A0 reference item.  The function exists so that
    if a future edit adds an item without wiring it up, the hole is reported
    here rather than discovered later.
    """

    mapped: set[str] = set()
    for scenario in JOINT_SCENARIOS:
        mapped.update(scenario.acceptance_ids)
    for item in A0_REFERENCE_ITEMS:
        mapped.update(item.acceptance_ids)
    return tuple(ac_id for ac_id in acceptance_ids() if ac_id not in mapped)


def not_run_items() -> tuple[A0Item, ...]:
    """The A0 items whose real status is `not_run`, kept separate from the passes."""

    return tuple(item for item in A0_REFERENCE_ITEMS if item.status == "not_run")


def matrix_readback() -> dict[str, object]:
    """The whole rollup as one deterministic public record."""

    return {
        "schema": AC_MATRIX_SCHEMA,
        "provenance": MATRIX_PROVENANCE,
        "acceptance_items": [item.as_dict() for item in RM_ACCEPTANCE_MATRIX],
        "joint_scenarios": [scenario.as_dict() for scenario in JOINT_SCENARIOS],
        "a0_reference_items": [item.as_dict() for item in A0_REFERENCE_ITEMS],
        "unmapped_acceptance_ids": list(unmapped_acceptance_ids()),
        "not_run_item_ids": [item.item_id for item in not_run_items()],
        "sign_off": "partial",
        "sign_off_reason": "the contract and offline-regression layer is complete; A0-E01 and "
        "A0-E02 have no real connected evidence, and a correctly expected block satisfies only "
        "its own negative case",
    }
