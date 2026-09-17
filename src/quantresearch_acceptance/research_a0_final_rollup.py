"""The A0 final acceptance rollup: #443 (A0-T09).

This module is **not a third test-implementation platform**.  It publishes one
deterministic, checkable index over work that other tickets already did:

* all twenty-seven A0 acceptance scenarios of EPIC #431, quoted from that
  issue's "Acceptance scenario catalogue v1" rather than reconstructed,
* the six U1-U6 joint scenarios and their #431 mapping,
* the twenty-four old tickets of #431's coverage map plus the nine A0
  implementation tickets,
* the exact commits, evidence documents and test functions that back each one,
* the gaps that remain, with an owner for each,
* the *actual* native GitHub relationship state, read back rather than assumed.

The design rule that carries the ticket: **a scenario counts as passed only
when it was executed in this repository at the current baseline AND the
evidence that exists is of the type #431 requires for it.**  Those are two
separate fields (:attr:`ScenarioRecord.status` and
:attr:`ScenarioRecord.evidence_type_matches`), so a correctly-executed proof of
the wrong evidence type cannot be laundered into a pass, and neither can a
correctly-expected refusal.  ``passed_scenario_ids()`` enforces it in code.

Standard library only.  No dependency, no client, no service, no second fact
authority, and no product logic.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

#: Schema of the public readback this module produces.
A0_ROLLUP_SCHEMA = "quantresearch.research.a0_final_rollup/v1"

#: Where the twenty-seven scenario definitions come from.
#:
#: Unlike #404's RM-AC01-RM-AC18 titles, which had to be reconstructed because
#: no issue enumerates them, #431 *does* enumerate all twenty-seven A0
#: scenarios in a normative table.  Nothing here is reconstructed.
#:
#: The assertions are restated in English because every module in this package
#: is English-only; the verbatim Chinese of #431's table is preserved in
#: ``docs/evidence/issue-443-a0-final-rollup.md`` so the restatement can always
#: be checked against the original.
ROLLUP_PROVENANCE = (
    "sourced_from_issue_431_catalogue: EPIC #431 publishes a normative "
    "'Acceptance scenario catalogue v1' table enumerating all twenty-seven A0 scenario "
    "ids with their required assertion and default evidence type; the ids, assertions "
    "and evidence types below are taken from that table and restated in English, with "
    "the verbatim Chinese preserved in docs/evidence/issue-443-a0-final-rollup.md. "
    "Nothing is reconstructed, unlike the RM-AC01-RM-AC18 titles of #404 which no issue "
    "enumerates"
)

#: The baseline every status below is pinned to.
BASELINE_COMMIT = "db41a44f3b665472b7ad1dc7529a49734600330e"

#: Status of one scenario at :data:`BASELINE_COMMIT`.
#:
#: ``executed``
#:     Really run in this repository at the current baseline.
#: ``cited_owner_evidence``
#:     Measured by another repository's owner and cited, never re-measured
#:     here.  Deliberately *not* counted as passed by this rollup.
#: ``owner_reported_unverifiable``
#:     An owner closure receipt asserts the work happened, but no artifact
#:     reachable from this checkout confirms it.  Neither ``executed`` nor
#:     ``not_run``; see :data:`E01_DRIFT_NOTE`.
#: ``not_run``
#:     Genuinely never executed.
#: ``pending``
#:     Blocked on an upstream artifact that does not exist yet.
SCENARIO_STATUSES = (
    "executed",
    "cited_owner_evidence",
    "owner_reported_unverifiable",
    "not_run",
    "pending",
)

#: Where a scenario's evidence physically lives.
EVIDENCE_CLASSES = (
    "proven_in_this_repo",
    "cited_owner_evidence",
    "owner_reported_unverifiable_here",
    "absent",
)

#: The controlled vocabulary for #431's "默认证据类型" column.
EVIDENCE_TYPES = (
    "public_contract",
    "independent_golden",
    "negative_matrix",
    "real_concurrency_performance",
    "gate_trace",
    "real_sandbox",
    "artifact_tamper_reuse",
    "trace_prefix_property",
    "comparable_relation_brief",
    "lineage_selection_history",
    "manual_protection_record",
    "delivery_receipt_interruption_trace",
    "frozen_brief",
    "pagination_coverage_matrix",
    "call_budget_counts",
    "three_public_branches",
    "dual_time_view",
    "real_deletion_recovery",
    "connected_formal",
    "connected_model",
    "installed_cross_repo",
    "acceptance_selection_record",
    "mutation_generic_regression",
)

#: The single most important correction this rollup publishes.
#:
#: #404, #408, #429 and #442 each recorded that "#441 published no round-one
#: research assets".  At their own baseline that was already only half true:
#: #441 closed on 2026-09-14T18:44:04Z with a delivery receipt asserting a real
#: connected V0/V1 round, three days *before* those four evidence documents
#: were committed on 2026-09-17.  What is literally true is the narrower
#: statement they also made -- #441 landed no commit in *this* repository.
#:
#: Re-verified at this baseline: the receipt's artifact paths
#: (``runtime/q441/evidence-index.md``, ``runtime/q441/a0-study-report.md``,
#: ``docs/reports/q441-研究过程经验总结-2026-09-15.md``) do not exist on this
#: checkout, and the run identities it names appear in no file on disk.  So the
#: honest status is neither ``not_run`` (a receipt exists) nor ``executed`` (no
#: artifact here confirms it): it is ``owner_reported_unverifiable``.
#:
#: Note also what the receipt itself declines to claim: ``comparison_present``
#: is false, both runs produced zero orders, fills and positions, the stated
#: conclusion is ``inconclusive``, and PIT/provider lineage was not evaluated.
#: Even taken entirely at face value it does not assert that A0's research
#: question was answered.
E01_DRIFT_NOTE = (
    "#441 closed 2026-09-14 with a receipt asserting a real connected V0/V1 round "
    "(deploy_20260914_151903, run_0b9549440d7dca28f0c0d573c293444a / "
    "run_fdb00d3a48eff4a4b07d7e4d9ea44db4, Nautilus 1.231.0). The four evidence "
    "documents committed 2026-09-17 (#442, #404, #408, #429) each recorded the "
    "absence of round-one assets; that finding is correct only in its narrow form "
    "('no commit in this repository') and is stale in its broad form. Re-verified "
    "at this baseline: none of the receipt's artifact paths exist on this checkout "
    "and none of its run identities appears in any file on disk, so the claim "
    "cannot be confirmed here. The receipt itself reports comparison_present=false, "
    "zero orders/fills/positions, an inconclusive result, and PIT/provider lineage "
    "not evaluated."
)


@dataclass(frozen=True, slots=True)
class TestRef:
    """One test claimed as evidence, addressed so it can be resolved."""

    module: str
    test: str

    def as_dict(self) -> dict[str, object]:
        return {"module": self.module, "test": self.test}


@dataclass(frozen=True, slots=True)
class CommitRef:
    """One commit claimed as evidence, addressed so `git cat-file` can find it."""

    sha: str
    subject: str

    def as_dict(self) -> dict[str, object]:
        return {"sha": self.sha, "subject": self.subject}


@dataclass(frozen=True, slots=True)
class ScenarioRecord:
    """One of #431's twenty-seven A0 acceptance scenarios."""

    scenario_id: str
    must_assert: str
    required_evidence_types: tuple[str, ...]
    satisfied_evidence_types: tuple[str, ...]
    owner_issue: str
    status: str
    evidence_class: str
    evidence: tuple[TestRef, ...]
    limitations: tuple[str, ...] = ()
    note: str = ""

    @property
    def evidence_type_matches(self) -> bool:
        """Every evidence type #431 requires for this scenario is present."""

        return set(self.required_evidence_types) <= set(self.satisfied_evidence_types)

    @property
    def passed(self) -> bool:
        """Executed here, at this baseline, with evidence of the required type.

        Cited owner evidence is deliberately excluded: it is real, but it was
        not re-measured here and this rollup must not present another
        repository's measurement as its own result.
        """

        return self.status == "executed" and self.evidence_type_matches

    def as_dict(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "must_assert": self.must_assert,
            "required_evidence_types": list(self.required_evidence_types),
            "satisfied_evidence_types": list(self.satisfied_evidence_types),
            "evidence_type_matches": self.evidence_type_matches,
            "owner_issue": self.owner_issue,
            "status": self.status,
            "evidence_class": self.evidence_class,
            "passed": self.passed,
            "evidence": [ref.as_dict() for ref in self.evidence],
            "limitations": list(self.limitations),
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class TicketRecord:
    """One ticket of the #444 queue and the scenarios it is bound to."""

    ticket: str
    github_state: Literal["OPEN", "CLOSED"]
    scenario_ids: tuple[str, ...]
    delivered_here: bool
    commits: tuple[CommitRef, ...]
    evidence_doc: str
    note: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "ticket": self.ticket,
            "github_state": self.github_state,
            "scenario_ids": list(self.scenario_ids),
            "delivered_here": self.delivered_here,
            "commits": [ref.as_dict() for ref in self.commits],
            "evidence_doc": self.evidence_doc,
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class JointScenario:
    """One U1-U6 joint scenario and its #431 A0 mapping."""

    scenario_id: str
    title: str
    a0_scenario_ids: tuple[str, ...]
    status: str
    evidence: tuple[TestRef, ...]
    note: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "title": self.title,
            "a0_scenario_ids": list(self.a0_scenario_ids),
            "status": self.status,
            "evidence": [ref.as_dict() for ref in self.evidence],
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class GapItem:
    """One concrete thing that remains undone, with an owner who can do it."""

    gap_id: str
    title: str
    owner: str
    blocks: tuple[str, ...]
    remediation: str

    def as_dict(self) -> dict[str, object]:
        return {
            "gap_id": self.gap_id,
            "title": self.title,
            "owner": self.owner,
            "blocks": list(self.blocks),
            "remediation": self.remediation,
        }


_VIS = "_research_visibility_test"
_EXP = "_research_exposure_test"
_CTX = "_research_context_test"
_PAG = "_research_pagination_test"
_DEC = "_research_decision_test"
_CUR = "_research_currency_test"
_R2 = "_research_a0_round2_test"
_MTX = "_research_ac_matrix_test"
_REC = "_research_recovery_test"
_SGF = "_research_genome_flow_test"
_FIN = "_research_a0_final_rollup_test"


def _refs(module: str, *tests: str) -> tuple[TestRef, ...]:
    """Evidence for one module, written so a long test name still fits a line."""

    return tuple(TestRef(module, test) for test in tests)


# ---------------------------------------------------------------------------
# The twenty-seven scenarios, quoted from #431's catalogue.
# ---------------------------------------------------------------------------

A0_SCENARIOS: tuple[ScenarioRecord, ...] = (
    ScenarioRecord(
        scenario_id="A0-G01",
        must_assert=(
            "renaming, re-describing or re-packaging V0 leaves the Genome unchanged; the original "
            "provenance and events survive"
        ),
        required_evidence_types=("public_contract", "independent_golden"),
        satisfied_evidence_types=("public_contract",),
        owner_issue="#414/#420/#429",
        status="executed",
        evidence_class="proven_in_this_repo",
        evidence=_refs(
            _SGF,
            "test_a_second_attempt_keeps_the_genome_identity_and_adds_its_provenance",
            "test_the_candidate_ir_is_stored_verbatim_and_no_second_dsl_appears",
        ),
        limitations=(
            "the independent-golden half is #437-shaped synthetic fixture built in this "
            "repository, not an owner-frozen oracle; A0-FIXTURES-ORACLE is pending",
        ),
        note="Contract invariance is proven. The second required evidence type is absent, "
        "so this scenario is reported as executed-but-type-incomplete, not as a pass.",
    ),
    ScenarioRecord(
        scenario_id="A0-G02",
        must_assert=(
            "V0->V1 changes only the volume-contraction component; identity changes; the diff "
            "accurately lists the change and the verified-unchanged scope"
        ),
        required_evidence_types=("public_contract",),
        satisfied_evidence_types=("public_contract",),
        owner_issue="#415/#429",
        status="executed",
        evidence_class="proven_in_this_repo",
        evidence=(
            *_refs(
                _SGF,
                "test_identical_payloads_of_different_kinds_never_share_an_identity",
                "test_different_bytes_can_never_take_over_an_existing_identity",
            ),
            *_refs(
                _MTX,
                "test_u4_single_component_comparison_keeps_the_gap_and_claims_no_cause",
            ),
        ),
    ),
    ScenarioRecord(
        scenario_id="A0-G03",
        must_assert=(
            "unknown kind/version/ambiguity is refused; an unauthorized or incompatible comparison "
            "is incomparable and leaks nothing"
        ),
        required_evidence_types=("negative_matrix",),
        satisfied_evidence_types=("negative_matrix",),
        owner_issue="#416/#418/#429",
        status="executed",
        evidence_class="proven_in_this_repo",
        evidence=_refs(
            _SGF,
            "test_every_compatibility_case_keeps_its_documented_behaviour",
            "test_an_unsupported_major_has_no_adapter_and_no_silent_fallback",
            "test_a_mismatched_identity_is_refused_and_leaks_nothing",
        ),
    ),
    ScenarioRecord(
        scenario_id="A0-G04",
        must_assert=(
            "Candidate/Genome/Package/request/event stay separate; identical content is stable and "
            "forms no hash cycle"
        ),
        required_evidence_types=("public_contract",),
        satisfied_evidence_types=("public_contract",),
        owner_issue="#417/#420/#429",
        status="executed",
        evidence_class="proven_in_this_repo",
        evidence=_refs(
            _SGF,
            "test_the_golden_flow_runs_every_stage_in_order_and_keeps_six_identities",
            "test_content_addressing_admits_no_self_reference_and_no_cycle",
            "test_a0_g04_v02_the_a0_flow_keeps_its_identities_and_refuses_the_bad_inputs",
        ),
    ),
    ScenarioRecord(
        scenario_id="A0-X01",
        must_assert=(
            "first and repeat crossback, threshold boundary, absent data, "
            "invalidation/reset/conflict and the order trace all match the independent expectation"
        ),
        required_evidence_types=("independent_golden",),
        satisfied_evidence_types=(),
        owner_issue="#421/#437/#438",
        status="pending",
        evidence_class="absent",
        evidence=(),
        limitations=(
            "no EMA-crossback reference strategy exists in any checked-out repository at "
            "this baseline; A0-FIXTURES-ORACLE and A0-REFERENCE-STRATEGY are both pending",
        ),
        note="Searched at this baseline: no 'crossback' implementation under "
        "quant-runtime/src, apex-research/src or strategy-workspace/src. #429's "
        "test_a0_q02_no_production_module_branches_on_a_strategy_name independently "
        "confirms the generic core carries no strategy behaviour, so there is nothing "
        "in this repository that a bar-level oracle could be run against.",
    ),
    ScenarioRecord(
        scenario_id="A0-X02",
        must_assert=(
            "appending future data never rewrites an already-confirmed past event; occurrence, "
            "confirmation and order times stay separate"
        ),
        required_evidence_types=("trace_prefix_property",),
        satisfied_evidence_types=(),
        owner_issue="#421/#437/#438",
        status="pending",
        evidence_class="absent",
        evidence=(),
        limitations=(
            "the record-level no-hindsight property is proven by #401 "
            "(CUR::test_an_old_snapshot_projection_shows_no_hindsight_and_a_new_one_does), "
            "but that is a research-record property and is NOT a substitute for the "
            "bar/event/order-time prefix property this scenario requires",
        ),
        note="Same root cause as A0-X01: there is no strategy event trace to assert the "
        "prefix property over. The adjacent record-level proof is cited so it cannot be "
        "silently promoted into this slot.",
    ),
    ScenarioRecord(
        scenario_id="A0-L01",
        must_assert=(
            "retrying the same action is idempotent; the same key with a different input is "
            "rejected; a resubmission cannot clear a tombstone"
        ),
        required_evidence_types=("public_contract",),
        satisfied_evidence_types=("public_contract",),
        owner_issue="#417/#419/#429",
        status="executed",
        evidence_class="proven_in_this_repo",
        evidence=(
            *_refs(
                _DEC,
                "test_a_retry_of_the_same_action_recovers_instead_of_re_executing",
                "test_the_same_key_with_a_different_input_is_rejected",
            ),
            *_refs(
                _SGF,
                "test_a_new_attempt_cannot_clear_a_tombstone",
                "test_a_rejected_record_is_terminal_and_distinct_from_a_tombstone",
            ),
        ),
    ),
    ScenarioRecord(
        scenario_id="A0-L02",
        must_assert=(
            "default-deny, current-authorization and historical-redelivery checks are correct; an "
            "old permission never restores access"
        ),
        required_evidence_types=("negative_matrix",),
        satisfied_evidence_types=("negative_matrix",),
        owner_issue="#394/#418/#422",
        status="executed",
        evidence_class="proven_in_this_repo",
        evidence=(
            *_refs(
                _VIS,
                "test_revoked_current_access_blocks_historical_redelivery_without_rewriting_context",
            ),
            *_refs(
                _CUR,
                "test_a_currently_unauthorized_reader_cannot_re_read_via_the_old_policy",
            ),
            *_refs(
                _EXP,
                "test_a_currently_unauthorized_party_cannot_replay_historical_content",
            ),
        ),
    ),
    ScenarioRecord(
        scenario_id="A0-L03",
        must_assert=(
            "same-identity contention and crash produce no half-publish; #419's local 256 KiB p95 "
            "<= 250 ms stays a separate real measurement"
        ),
        required_evidence_types=("real_concurrency_performance",),
        satisfied_evidence_types=("real_concurrency_performance",),
        owner_issue="#419",
        status="cited_owner_evidence",
        evidence_class="cited_owner_evidence",
        evidence=_refs(
            _SGF,
            "test_the_owner_measured_evidence_is_cited_and_never_claimed_as_re_measured",
        ),
        limitations=(
            "#419's concurrency/crash evidence and the 256 KiB p95 <= 250 ms local target "
            "can only be measured inside StrategyWorkspace, which this repository does not "
            "own and must not modify; they are cited and explicitly NOT re-measured",
        ),
        note="Deliberately excluded from passed_scenario_ids(): the measurement is real but "
        "it is the owner's, not this rollup's. The cited test asserts the 'NOT re-measured' "
        "wording survives in CITED_OWNER_EVIDENCE.",
    ),
    ScenarioRecord(
        scenario_id="A0-V01",
        must_assert=(
            "the gate sequence short-circuits; prepare is not export; a verification-purpose grant "
            "cannot authorize formal research"
        ),
        required_evidence_types=("gate_trace", "real_sandbox"),
        satisfied_evidence_types=("gate_trace",),
        owner_issue="#421/#427/#429",
        status="executed",
        evidence_class="proven_in_this_repo",
        evidence=_refs(
            _SGF,
            "test_the_three_gates_run_in_their_fixed_order_before_preparation",
            "test_preparation_is_not_export_and_the_stage_graph_has_no_cycle",
            "test_a_prepared_package_cannot_enter_the_formal_path",
            "test_a_sandbox_only_grant_cannot_enter_the_ordinary_formal_path",
        ),
        limitations=(
            "the gate ordering and prepare-is-not-export properties are proven against the "
            "contract; no real sandbox execution was performed in this repository",
        ),
        note="Executed but type-incomplete: the real-sandbox half of #431's required "
        "evidence type is absent, so this is not counted as a pass.",
    ),
    ScenarioRecord(
        scenario_id="A0-V02",
        must_assert=(
            "any change to the exact Package/verification binding is refused; a matching valid "
            "evidence reuse skips a repeat sandbox; revocation still blocks"
        ),
        required_evidence_types=("artifact_tamper_reuse",),
        satisfied_evidence_types=("artifact_tamper_reuse",),
        owner_issue="#422/#427/#429",
        status="executed",
        evidence_class="proven_in_this_repo",
        evidence=_refs(
            _SGF,
            "test_an_exact_repeat_reuses_verification_and_runs_no_new_sandbox_work",
            "test_any_binding_change_revalidates_instead_of_reusing",
            "test_a_stale_binding_cannot_complete_a_formal_consumption",
            "test_a_doctored_public_fact_fails_loudly_during_replay",
        ),
    ),
    ScenarioRecord(
        scenario_id="A0-M01",
        must_assert=(
            "a Finding carries scope, evidence tier and gaps; a data block is not strategy "
            "invalidity"
        ),
        required_evidence_types=("public_contract",),
        satisfied_evidence_types=("public_contract",),
        owner_issue="#391/#397/#399",
        status="executed",
        evidence_class="proven_in_this_repo",
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
    ),
    ScenarioRecord(
        scenario_id="A0-M02",
        must_assert=(
            "same-scope support and counter-evidence are kept; different conditions are not forced "
            "into a conflict; a single-component difference claims no cause"
        ),
        required_evidence_types=("comparable_relation_brief",),
        satisfied_evidence_types=("comparable_relation_brief",),
        owner_issue="#392/#397",
        status="executed",
        evidence_class="proven_in_this_repo",
        evidence=(
            *_refs(
                _CTX,
                "test_a0_m02_unaligned_cost_keeps_limitations_and_refuses_a_causal_claim",
                "test_a0_m02_a_tight_budget_never_buys_room_by_dropping_counter_evidence",
            ),
            *_refs(
                _MTX,
                "test_u4_single_component_comparison_keeps_the_gap_and_claims_no_cause",
            ),
        ),
    ),
    ScenarioRecord(
        scenario_id="A0-M03",
        must_assert=(
            "multiple summaries of one run do not inflate independence; a new Campaign does not "
            "erase the selection or test family"
        ),
        required_evidence_types=("lineage_selection_history",),
        satisfied_evidence_types=("lineage_selection_history",),
        owner_issue="#393/#396",
        status="executed",
        evidence_class="proven_in_this_repo",
        evidence=(
            *_refs(
                _EXP,
                "test_a0_m03_downstream_stop_decision_links_context_exposure_and_test_family",
                "test_usage_history_is_not_cleared_by_a_later_campaign",
            ),
            *_refs(_DEC, "test_a_new_campaign_never_resets_the_test_family"),
        ),
    ),
    ScenarioRecord(
        scenario_id="A0-P01",
        must_assert=(
            "direct and derived protection block before any unauthorized consumption; reason, "
            "counts and logs leak nothing"
        ),
        required_evidence_types=("manual_protection_record",),
        satisfied_evidence_types=("manual_protection_record",),
        owner_issue="#394/#395",
        status="executed",
        evidence_class="proven_in_this_repo",
        evidence=(
            *_refs(
                _VIS,
                "test_a0_p01_derived_artifacts_are_blocked_before_any_consumer_read",
                "test_multi_hop_derivation_cannot_launder_a_protected_source",
                "test_restricted_output_cannot_reveal_material_ids_counts_or_lineage",
            ),
            *_refs(
                _R2,
                "test_a0_p01_the_visibility_gate_stops_the_round_before_any_spend",
                "test_a0_p01_a_blocked_final_envelope_stops_before_the_model_read",
            ),
        ),
    ),
    ScenarioRecord(
        scenario_id="A0-P02",
        must_assert=(
            "Context is traceably distinct from the final envelope and tool input; uncertain never "
            "becomes unseen; no blind resend"
        ),
        required_evidence_types=("delivery_receipt_interruption_trace",),
        satisfied_evidence_types=("delivery_receipt_interruption_trace",),
        owner_issue="#396/#408",
        status="executed",
        evidence_class="proven_in_this_repo",
        evidence=(
            *_refs(
                _EXP,
                "test_uncertain_delivery_never_claims_non_exposure_and_forbids_blind_resend",
                "test_a_confirmed_delivery_cannot_be_returned_to_uncertain",
            ),
            *_refs(
                _REC,
                "test_a0_p02_process_interruption_lost_receipt_and_duplicate_on_the_delivery_boundary",
                "test_ac3_a_real_torn_journal_leaves_the_context_uncertain_never_unseen",
            ),
        ),
        note="#408 drives this on a real file with a really torn append-only journal, so "
        "the required trace evidence type is genuinely satisfied rather than simulated.",
    ),
    ScenarioRecord(
        scenario_id="A0-C01",
        must_assert=(
            "the second-round brief keeps baseline, counter-evidence, gaps, assets, recommendation "
            "preconditions and must-not-claim; every field has a source"
        ),
        required_evidence_types=("frozen_brief",),
        satisfied_evidence_types=("frozen_brief",),
        owner_issue="#397/#401",
        status="executed",
        evidence_class="proven_in_this_repo",
        evidence=(
            *_refs(
                _CTX,
                "test_a0_c01_second_round_brief_has_every_field_with_provenance_or_unknown",
                "test_an_owner_fact_without_provenance_is_refused",
            ),
            *_refs(_R2, "test_a0_c01_required_counter_evidence_missing_blocks_the_round"),
        ),
    ),
    ScenarioRecord(
        scenario_id="A0-C02",
        must_assert=(
            "a missing required closure is refused; optional scope is bounded by the "
            "pre-declaration; required counter-evidence is never trimmed and a failure is never "
            "faked as empty"
        ),
        required_evidence_types=("pagination_coverage_matrix",),
        satisfied_evidence_types=("pagination_coverage_matrix",),
        owner_issue="#395/#398",
        status="executed",
        evidence_class="proven_in_this_repo",
        evidence=_refs(
            _PAG,
            "test_a0_c02_required_complete_optional_limited_is_honest_not_empty",
            "test_a0_c02_a_failed_round_is_never_relabelled_complete_empty",
            "test_a_missing_required_counter_example_still_refuses_a_one_sided_conclusion",
            "test_trimming_never_drops_a_required_record_to_fit",
        ),
    ),
    ScenarioRecord(
        scenario_id="A0-R01",
        must_assert=(
            "a true research duplicate stops before a new engine Context, paid budget or call; a "
            "request retry reconciles"
        ),
        required_evidence_types=("call_budget_counts",),
        satisfied_evidence_types=("call_budget_counts",),
        owner_issue="#396/#399",
        status="executed",
        evidence_class="proven_in_this_repo",
        evidence=(
            *_refs(
                _DEC,
                "test_a_true_duplicate_stops_before_context_budget_run_and_call",
                "test_a0_r01_retry_reconciles_conflict_rejects_and_duplicate_stops",
            ),
            *_refs(_R2, "test_a0_r01_retry_conflict_and_duplicate_stop_each_have_their_own_branch"),
        ),
    ),
    ScenarioRecord(
        scenario_id="A0-R02",
        must_assert=(
            "a new statistical protocol may attach to the same execution; a legitimate new sample "
            "is not blocked by Genome dedup; a repaired blocker is handled under the new condition"
        ),
        required_evidence_types=("three_public_branches",),
        satisfied_evidence_types=("three_public_branches",),
        owner_issue="#393/#399",
        status="executed",
        evidence_class="proven_in_this_repo",
        evidence=(
            *_refs(
                _DEC,
                "test_a0_r02_attach_new_sample_and_blocker_recovery_stay_separate",
                "test_a_legitimate_new_sample_is_not_blocked_by_a_matching_genome",
            ),
            *_refs(_R2, "test_a0_r02_attach_and_legitimate_new_sample_stay_separate_branches"),
        ),
    ),
    ScenarioRecord(
        scenario_id="A0-H01",
        must_assert=(
            "a correction moves the current brief without changing the old knowledge snapshot; "
            "currency stays the original owner's call"
        ),
        required_evidence_types=("dual_time_view",),
        satisfied_evidence_types=("dual_time_view",),
        owner_issue="#401",
        status="executed",
        evidence_class="proven_in_this_repo",
        evidence=_refs(
            _CUR,
            "test_a0_h01_a_correction_updates_the_current_brief_without_touching_the_old_one",
            "test_only_owner_evidence_or_decision_refreshes_formal_currency",
            "test_a_correction_published_later_is_invisible_to_an_older_cutoff",
        ),
    ),
    ScenarioRecord(
        scenario_id="A0-H02",
        must_assert=(
            "after clearing projections the rebuild uses the old facts, current authorization is "
            "still checked, and there is zero new backtest, LLM call or budget"
        ),
        required_evidence_types=("real_deletion_recovery",),
        satisfied_evidence_types=("real_deletion_recovery",),
        owner_issue="#398/#408",
        status="executed",
        evidence_class="proven_in_this_repo",
        evidence=(
            *_refs(
                _REC,
                "test_ac1_deleting_every_projection_on_disk_still_recovers_identity_and_boundary",
                "test_u6_a_fresh_python_process_recovers_the_same_identity",
                "test_ac1_a_recovery_publishes_zero_run_model_and_budget_counts",
                "test_a0_h02_the_real_asset_slice_is_pending_and_never_mocked",
            ),
            *_refs(_MTX, "test_u6_rebuild_after_deletion_costs_no_run_llm_call_or_budget"),
        ),
        limitations=(
            "the real-asset half is pending: the deletion and rebuild run over #437-shaped "
            "synthetic fixtures because no frozen real A0 research asset exists in this "
            "repository to delete and recover (see gap G-441-ASSETS)",
        ),
        note="Counted as a pass because #431's required evidence type for this scenario is "
        "real deletion/recovery and #408 performs exactly that -- real Path.unlink, real "
        "truncation, a really torn journal and recovery in a separate OS process. The "
        "synthetic-fixture limitation is published above and carried in the gap list; it is "
        "not hidden by the pass.",
    ),
    ScenarioRecord(
        scenario_id="A0-E01",
        must_assert=(
            "a declared real-data V0/V1 normal research chain runs end to end; the direction of "
            "the result is not presupposed"
        ),
        required_evidence_types=("connected_formal",),
        satisfied_evidence_types=(),
        owner_issue="#441",
        status="owner_reported_unverifiable",
        evidence_class="owner_reported_unverifiable_here",
        evidence=_refs(
            _FIN,
            "test_e01_is_owner_reported_and_never_counted_as_executed_or_not_run",
            "test_the_e01_receipt_artifacts_are_absent_from_this_checkout",
        ),
        limitations=(
            "#441's receipt artifact paths do not exist on this checkout and its run "
            "identities appear in no file on disk",
            "the receipt itself reports comparison_present=false, zero orders/fills/positions "
            "and an inconclusive result, so even at face value it asserts no research finding",
            "PIT/provider lineage was not evaluated; the #435 readiness gate is still blocked",
        ),
        note=E01_DRIFT_NOTE,
    ),
    ScenarioRecord(
        scenario_id="A0-E02",
        must_assert=(
            "the second round really uses the first round's assets, with an actual model "
            "request/response linked to Context/Exposure/decision; stopping is allowed and no new "
            "strategy is forced"
        ),
        required_evidence_types=("connected_model",),
        satisfied_evidence_types=(),
        owner_issue="#442",
        status="not_run",
        evidence_class="absent",
        evidence=_refs(
            _R2,
            "test_a0_e02_reports_not_run_and_never_claims_model_use",
            "test_a0_e02_an_unauthorized_engine_can_never_produce_a_delivered_state",
            "test_a0_e02_a_connectivity_probe_is_not_an_authorization",
        ),
        limitations=(
            "re-verified at this baseline: apex_research is not importable, "
            "ResearchEnginePort remains an unbound Protocol in apex-research/src, and there "
            "is no .env or research-engine configuration anywhere in this repository",
        ),
        note="The listed tests are evidence that the not_run status is reported honestly. "
        "They are NOT evidence that the criterion is satisfied. #442's finding was "
        "independently re-probed here rather than inherited.",
    ),
    ScenarioRecord(
        scenario_id="A0-E03",
        must_assert=(
            "installed/no-source positive and negative paths plus double replay; reporting is "
            "read-only; the full evidence is checkable"
        ),
        required_evidence_types=("installed_cross_repo",),
        satisfied_evidence_types=(),
        owner_issue="#428/#429",
        status="not_run",
        evidence_class="absent",
        evidence=_refs(
            _SGF,
            "test_the_genome_seam_imports_no_owner_wheel_and_no_private_storage",
            "test_a0_e03_h02_references_408_rather_than_reimplementing_recovery",
        ),
        limitations=(
            "re-verified at this baseline: strategy_workspace, apex_research, quant_runtime "
            "and strategy_reporting are all ModuleNotFoundError; no wheel is installed",
            "the two pre-existing suite failures are the honest signal of exactly this",
        ),
        note="#429 proved the contract shape of the installed/no-source flow. The required "
        "evidence type is a cross-repository installed environment, which does not exist "
        "here, so the scenario is not_run and the contract proof is not offered in its place.",
    ),
    ScenarioRecord(
        scenario_id="A0-Q01",
        must_assert=(
            "the existing selector/scope/fixed diff and the new batch behave correctly; "
            "skip/blocked/not_run are never counted as pass"
        ),
        required_evidence_types=("acceptance_selection_record",),
        satisfied_evidence_types=("acceptance_selection_record",),
        owner_issue="#439",
        status="executed",
        evidence_class="proven_in_this_repo",
        evidence=(
            *_refs(
                _SGF,
                "test_the_rollup_never_counts_a_not_run_item_as_passed",
            ),
            *_refs(
                _FIN,
                "test_a_not_run_or_pending_scenario_can_never_reach_the_passed_list",
                "test_a_type_mismatched_scenario_can_never_reach_the_passed_list",
            ),
        ),
    ),
    ScenarioRecord(
        scenario_id="A0-Q02",
        must_assert=(
            "the independent expectation catches deliberately injected errors; the existing "
            "non-CPA small case checks genericity; the core has no special case"
        ),
        required_evidence_types=("mutation_generic_regression",),
        satisfied_evidence_types=("mutation_generic_regression",),
        owner_issue="#429/#437",
        status="executed",
        evidence_class="proven_in_this_repo",
        evidence=(
            *_refs(
                _SGF,
                "test_a0_q02_an_independent_oracle_catches_identity_time_and_binding_mutations",
                "test_a0_q02_no_production_module_branches_on_a_strategy_name",
            ),
            *_refs(
                _MTX,
                "test_no_production_module_has_an_execution_seam_for_injected_text",
            ),
        ),
        note="The existing non-CPA generic regression is reused and cited, per the ticket's "
        "instruction not to build a second research project. #429's name-scan finds zero "
        "strategy-name branches across every production module.",
    ),
)


# ---------------------------------------------------------------------------
# U1-U6, carried forward from #404 and #431's mapping line.
# ---------------------------------------------------------------------------

JOINT_SCENARIOS: tuple[JointScenario, ...] = (
    JointScenario(
        scenario_id="U1",
        title="an equivalent failure direction, renamed, is still a duplicate",
        a0_scenario_ids=("A0-R01", "A0-M01"),
        status="executed",
        evidence=_refs(
            _DEC,
            "test_a_renamed_equivalent_request_is_still_a_duplicate",
            "test_a0_u1_u3_miscall_run_reuse_and_external_call_counts",
        ),
    ),
    JointScenario(
        scenario_id="U2",
        title="a repaired data problem is retried under the new condition",
        a0_scenario_ids=("A0-R02", "A0-M01"),
        status="executed",
        evidence=_refs(
            _DEC,
            "test_a_repaired_blocker_with_an_owner_permitted_condition_proceeds",
            "test_a_repair_the_owner_did_not_permit_does_not_proceed",
        ),
    ),
    JointScenario(
        scenario_id="U3",
        title="a legitimate new-sample revalidation is not blocked by Genome dedup",
        a0_scenario_ids=("A0-R02",),
        status="executed",
        evidence=_refs(
            _DEC,
            "test_a_legitimate_new_sample_is_not_blocked_by_a_matching_genome",
            "test_a_genome_match_alone_is_not_a_run_match",
        ),
    ),
    JointScenario(
        scenario_id="U4",
        title=(
            "a single-component comparison keeps the difference, the unchanged items, the "
            "conditions and the required counter-evidence"
        ),
        a0_scenario_ids=("A0-G02", "A0-M02"),
        status="executed",
        evidence=(
            *_refs(_MTX, "test_u4_single_component_comparison_keeps_the_gap_and_claims_no_cause"),
            *_refs(_CTX, "test_a_misaligned_single_component_comparison_reports_the_gap_first"),
        ),
    ),
    JointScenario(
        scenario_id="U5",
        title=(
            "a source correction moves the current brief while the old Context keeps its as-of "
            "identity"
        ),
        a0_scenario_ids=("A0-H01",),
        status="executed",
        evidence=_refs(
            _CUR,
            "test_a0_u5_and_limited_replay_coverage_pass_through_public_readback_only",
            "test_the_old_context_keeps_its_identity_and_policy_after_a_correction",
        ),
    ),
    JointScenario(
        scenario_id="U6",
        title=(
            "rebuild from frozen public facts after deleting the projection, with zero new "
            "backtest, LLM call or budget"
        ),
        a0_scenario_ids=("A0-H02",),
        status="executed",
        evidence=(
            *_refs(_MTX, "test_u6_rebuild_after_deletion_costs_no_run_llm_call_or_budget"),
            *_refs(_REC, "test_u6_a_fresh_python_process_recovers_the_same_identity"),
        ),
        note="#408 added the real-execution half: a real directory deletion followed by "
        "recovery in a separate OS process.",
    ),
)


# ---------------------------------------------------------------------------
# The thirty-three tickets: #431's twenty-four old-ticket coverage map plus the
# nine A0 implementation tickets.
# ---------------------------------------------------------------------------

_NO_DOC = ""

OLD_TICKETS: tuple[TicketRecord, ...] = (
    TicketRecord(
        ticket="#391",
        github_state="CLOSED",
        scenario_ids=("A0-M01",),
        delivered_here=False,
        commits=(),
        evidence_doc=_NO_DOC,
        note="Finding contract owned outside this repository; consumed by reference, per "
        "the #397/#401 precedent recorded in #404.",
    ),
    TicketRecord(
        ticket="#392",
        github_state="CLOSED",
        scenario_ids=("A0-M02",),
        delivered_here=False,
        commits=(),
        evidence_doc=_NO_DOC,
        note="Relation contract owned outside this repository; consumed by reference.",
    ),
    TicketRecord(
        ticket="#393",
        github_state="CLOSED",
        scenario_ids=("A0-M03", "A0-R02"),
        delivered_here=False,
        commits=(),
        evidence_doc=_NO_DOC,
        note="Source-dependency contract owned outside this repository; consumed by reference.",
    ),
    TicketRecord(
        ticket="#394",
        github_state="CLOSED",
        scenario_ids=("A0-P01", "A0-L02"),
        delivered_here=True,
        commits=(
            CommitRef(
                "9a8a678c2a52c96785ea763634519f3b974f3540",
                "feat(acceptance): add research memory visibility gate (#394)",
            ),
        ),
        evidence_doc="docs/evidence/issue-394-visibility-gate.md",
    ),
    TicketRecord(
        ticket="#395",
        github_state="CLOSED",
        scenario_ids=("A0-P01", "A0-C02"),
        delivered_here=True,
        commits=(
            CommitRef(
                "3cf88c864c2401a394e7c1a832401459d06fe96d",
                "feat(acceptance): block protected derivation closure delivery (#395)",
            ),
        ),
        evidence_doc="docs/evidence/issue-395-protected-derivation-block.md",
    ),
    TicketRecord(
        ticket="#396",
        github_state="CLOSED",
        scenario_ids=("A0-P02", "A0-M03", "A0-R01"),
        delivered_here=True,
        commits=(
            CommitRef(
                "85c5c58722362a956cdb78a6e73ece93e274a5d6",
                "feat(acceptance): record research exposure lifecycle and usage (#396)",
            ),
        ),
        evidence_doc="docs/evidence/issue-396-exposure-lifecycle.md",
    ),
    TicketRecord(
        ticket="#397",
        github_state="CLOSED",
        scenario_ids=("A0-C01", "A0-M02"),
        delivered_here=True,
        commits=(
            CommitRef(
                "655920cfd60dfadd6d4b9b6c4d836ebdb155e5d6",
                "feat(acceptance): freeze a rebuildable bounded research context (#397)",
            ),
        ),
        evidence_doc="docs/evidence/issue-397-bounded-context-brief.md",
    ),
    TicketRecord(
        ticket="#398",
        github_state="CLOSED",
        scenario_ids=("A0-C02", "A0-H02"),
        delivered_here=True,
        commits=(
            CommitRef(
                "cb43dcf9ecd13796ab87e12f4776056e51f07551",
                "feat(acceptance): page a bounded Context deterministically and fail closed (#398)",
            ),
        ),
        evidence_doc="docs/evidence/issue-398-paginated-context-integrity.md",
    ),
    TicketRecord(
        ticket="#399",
        github_state="CLOSED",
        scenario_ids=("A0-R01", "A0-R02", "A0-P02"),
        delivered_here=True,
        commits=(
            CommitRef(
                "e1ebf9ecc7fa0de7d12638a022cf127d45165701",
                "feat(acceptance): stop true research duplicates before any spend (#399)",
            ),
        ),
        evidence_doc="docs/evidence/issue-399-duplicate-stop-and-call-order.md",
    ),
    TicketRecord(
        ticket="#401",
        github_state="CLOSED",
        scenario_ids=("A0-H01", "A0-C01", "A0-L02"),
        delivered_here=True,
        commits=(
            CommitRef(
                "58df8a81ada453de6e014046ccff5653dd81b198",
                "feat(acceptance): separate historical knowledge from current usage status (#401)",
            ),
        ),
        evidence_doc=(
            "docs/evidence/issue-401-source-correction-currency-and-reporting-projection.md"
        ),
    ),
    TicketRecord(
        ticket="#404",
        github_state="CLOSED",
        scenario_ids=("A0-M01", "A0-M02", "A0-M03", "A0-P01", "A0-C01", "A0-R01", "A0-H01"),
        delivered_here=True,
        commits=(
            CommitRef(
                "46fdf6dd078238d9cce3a347dc8cf1c727ceaaff",
                "feat(acceptance): publish the RM-AC01-RM-AC18 traceability matrix (#404)",
            ),
            CommitRef(
                "d478ab742fbce462e8b8893cf6c13a0541914184",
                "test(acceptance): close the U4, U6 and injection gaps and check the "
                "invariants (#404)",
            ),
        ),
        evidence_doc="docs/evidence/issue-404-rm-ac-comprehensive-rollup.md",
        note="Its A0-E01 'no round-one asset' finding is superseded here; see E01_DRIFT_NOTE.",
    ),
    TicketRecord(
        ticket="#408",
        github_state="CLOSED",
        scenario_ids=("A0-H02", "A0-P02"),
        delivered_here=True,
        commits=(
            CommitRef(
                "ee590b7a49e4a56a7795a8d6c5b3affcd1f66937",
                "feat(acceptance): add the two-scope recovery store seam (#408)",
            ),
            CommitRef(
                "670423a1b2d58ae120be94e22230be820a0b1357",
                "test(acceptance): prove real deletion, interruption, restart and replay (#408)",
            ),
        ),
        evidence_doc="docs/evidence/issue-408-cross-cache-deletion-interruption-and-replay.md",
    ),
    TicketRecord(
        ticket="#414",
        github_state="CLOSED",
        scenario_ids=("A0-G01", "A0-G02", "A0-G03", "A0-G04"),
        delivered_here=False,
        commits=(),
        evidence_doc=_NO_DOC,
        note="Genome contract/field ownership lives in StrategyWorkspace; contract shape "
        "re-stated in this repository by #429.",
    ),
    TicketRecord(
        ticket="#415",
        github_state="CLOSED",
        scenario_ids=("A0-G01", "A0-G02", "A0-G03"),
        delivered_here=False,
        commits=(),
        evidence_doc=_NO_DOC,
        note="Normalization/compare owned by StrategyWorkspace.",
    ),
    TicketRecord(
        ticket="#416",
        github_state="CLOSED",
        scenario_ids=("A0-G03", "A0-V01", "A0-V02"),
        delivered_here=False,
        commits=(),
        evidence_doc=_NO_DOC,
        note="Stable errors and negative expectations owned by StrategyWorkspace.",
    ),
    TicketRecord(
        ticket="#417",
        github_state="CLOSED",
        scenario_ids=("A0-G04", "A0-L01"),
        delivered_here=False,
        commits=(),
        evidence_doc=_NO_DOC,
    ),
    TicketRecord(
        ticket="#418",
        github_state="CLOSED",
        scenario_ids=("A0-G03", "A0-L02", "A0-V01"),
        delivered_here=False,
        commits=(),
        evidence_doc=_NO_DOC,
    ),
    TicketRecord(
        ticket="#419",
        github_state="CLOSED",
        scenario_ids=("A0-L01", "A0-L02", "A0-L03", "A0-V02"),
        delivered_here=False,
        commits=(),
        evidence_doc=_NO_DOC,
        note="Concurrency/crash and the 256 KiB p95 <= 250 ms local target are CITED, never "
        "re-measured here; they can only be measured inside StrategyWorkspace.",
    ),
    TicketRecord(
        ticket="#420",
        github_state="CLOSED",
        scenario_ids=("A0-G01", "A0-G02", "A0-G04", "A0-X01"),
        delivered_here=False,
        commits=(),
        evidence_doc=_NO_DOC,
    ),
    TicketRecord(
        ticket="#421",
        github_state="CLOSED",
        scenario_ids=("A0-V01", "A0-V02", "A0-X01", "A0-X02"),
        delivered_here=False,
        commits=(),
        evidence_doc=_NO_DOC,
        note="Independent behavioural conformance CITED, never re-measured here.",
    ),
    TicketRecord(
        ticket="#422",
        github_state="CLOSED",
        scenario_ids=("A0-V02", "A0-L01", "A0-L02"),
        delivered_here=False,
        commits=(),
        evidence_doc=_NO_DOC,
        note="Package export behaviour CITED, never re-measured here.",
    ),
    TicketRecord(
        ticket="#427",
        github_state="CLOSED",
        scenario_ids=("A0-V01", "A0-V02", "A0-R02", "A0-E01"),
        delivered_here=False,
        commits=(),
        evidence_doc=_NO_DOC,
        note="Closed without waiting on #441, per #431's anti-loop policy.",
    ),
    TicketRecord(
        ticket="#428",
        github_state="CLOSED",
        scenario_ids=("A0-G03", "A0-M02", "A0-C01", "A0-H01", "A0-E03"),
        delivered_here=False,
        commits=(),
        evidence_doc=_NO_DOC,
        note="Read-only Reporting projection; closed without waiting on #441.",
    ),
    TicketRecord(
        ticket="#429",
        github_state="CLOSED",
        scenario_ids=(
            "A0-G04",
            "A0-V02",
            "A0-E01",
            "A0-E02",
            "A0-E03",
            "A0-H02",
            "A0-Q02",
        ),
        delivered_here=True,
        commits=(
            CommitRef(
                "6677a6ca79267cbf0b36f725217fa187dcab4dbe",
                "feat(acceptance): add the Genome/Package golden-flow contract seam (#429)",
            ),
            CommitRef(
                "956f140c2eb465ec8a06031b7adb4e5fe621dd06",
                "test(acceptance): prove the Genome identity chain, fail-closed path and "
                "replay (#429)",
            ),
        ),
        evidence_doc="docs/evidence/issue-429-installed-no-source-genome-flow.md",
    ),
)

A0_TICKETS: tuple[TicketRecord, ...] = (
    TicketRecord(
        ticket="#433",
        github_state="CLOSED",
        scenario_ids=("A0-G01", "A0-M01", "A0-C01"),
        delivered_here=True,
        commits=(),
        evidence_doc="docs/research/a0/a0_delivery_index.md",
        note="T01 source capsule, scope, ambiguities and the delivery index. The index is "
        "git-ignored in this repository (only docs/evidence/issue-*.md is force-added), so "
        "it is navigation evidence read at this baseline rather than a tracked artifact.",
    ),
    TicketRecord(
        ticket="#434",
        github_state="CLOSED",
        scenario_ids=("A0-G01", "A0-G02", "A0-X01", "A0-M02"),
        delivered_here=False,
        commits=(),
        evidence_doc=_NO_DOC,
        note="A0-B0-RULES is still `pending` in the delivery index, re-verified at this "
        "baseline. Allowed-action and stop policy therefore remain fixtures, not owner "
        "artifacts, everywhere downstream.",
    ),
    TicketRecord(
        ticket="#435",
        github_state="OPEN",
        scenario_ids=("A0-E01", "A0-E03", "A0-Q01"),
        delivered_here=False,
        commits=(),
        evidence_doc=_NO_DOC,
        note="Still OPEN and blocked on data_semantics:point_in_time and "
        "data_semantics:provider_lineage. The owner explicitly accepted the current futures "
        "1m dataset as the backtest baseline so the #444 queue could proceed WITHOUT closing "
        "#435; the recorded gaps (225 day-gap rows across 33 dates, 1,522 night-internal-gap "
        "rows across 454 sessions) remain factual and are not reclassified as repaired.",
    ),
    TicketRecord(
        ticket="#437",
        github_state="CLOSED",
        scenario_ids=("A0-X01", "A0-X02", "A0-Q02"),
        delivered_here=False,
        commits=(),
        evidence_doc=_NO_DOC,
        note="A0-FIXTURES-ORACLE is still `pending` in the delivery index. Every fixture used "
        "downstream is #437-*shaped* and built inside this repository, not an owner-frozen "
        "oracle. This is the direct cause of A0-X01/A0-X02 being pending.",
    ),
    TicketRecord(
        ticket="#438",
        github_state="CLOSED",
        scenario_ids=("A0-X01", "A0-X02", "A0-Q02"),
        delivered_here=False,
        commits=(),
        evidence_doc=_NO_DOC,
        note="A0-REFERENCE-STRATEGY is still `pending`. No EMA-crossback implementation was "
        "found in quant-runtime/src, apex-research/src or strategy-workspace/src at this "
        "baseline.",
    ),
    TicketRecord(
        ticket="#439",
        github_state="CLOSED",
        scenario_ids=("A0-Q01",),
        delivered_here=True,
        commits=(),
        evidence_doc=_NO_DOC,
        note="A0-ACCEPTANCE-INTEGRATION is `observed; unchanged`. The mechanism is the "
        "pre-existing acceptance package; no scope, selector, marker or ledger was changed "
        "by the A0 batch.",
    ),
    TicketRecord(
        ticket="#441",
        github_state="CLOSED",
        scenario_ids=("A0-E01",),
        delivered_here=False,
        commits=(),
        evidence_doc=_NO_DOC,
        note=E01_DRIFT_NOTE,
    ),
    TicketRecord(
        ticket="#442",
        github_state="CLOSED",
        scenario_ids=("A0-E02", "A0-C01", "A0-P01", "A0-P02", "A0-R01", "A0-R02"),
        delivered_here=True,
        commits=(
            CommitRef(
                "dd7ca121385bc8485402dc7be21aee57353be274",
                "feat(acceptance): compose the A0 second round with an honest engine "
                "authorization (#442)",
            ),
            CommitRef(
                "efb9cdb558bd5011429cdfe5fc307f8eb3046f3f",
                "test(acceptance): cover E02 not_run, envelope protection and the five reuse "
                "branches (#442)",
            ),
        ),
        evidence_doc="docs/evidence/issue-442-a0-round-two-model-decision.md",
    ),
    TicketRecord(
        ticket="#443",
        github_state="OPEN",
        scenario_ids=tuple(record.scenario_id for record in A0_SCENARIOS),
        delivered_here=True,
        commits=(),
        evidence_doc="docs/evidence/issue-443-a0-final-rollup.md",
        note="This rollup. Its own commits are intentionally not self-referenced: a commit "
        "cannot cite its own SHA before it exists.",
    ),
)

ALL_TICKETS: tuple[TicketRecord, ...] = (*OLD_TICKETS, *A0_TICKETS)


# ---------------------------------------------------------------------------
# Native GitHub relationship state -- actually read back, not assumed.
# ---------------------------------------------------------------------------

#: The result of a real GraphQL readback performed at this baseline.
#:
#: For every issue in the A0 tree (#431-#443) the query
#: ``repository.issue(number:N) { parent { number } subIssues { nodes { number } } }``
#: returned ``parent = null`` and an empty ``subIssues`` list.
#:
#: The query itself is known to work: run against #402 it returns
#: ``subIssues = [405, 406, 409, 411]``, and against #405 it returns
#: ``parent = 402``.  So the empty A0 result is a **verified absence of native
#: edges**, not a broken or unsupported query.  ``pending-native-link`` --
#: #433's original state and #431's declared state -- is therefore confirmed by
#: measurement rather than carried forward on trust.
NATIVE_RELATIONSHIP_READBACK: dict[str, object] = {
    "method": "gh api graphql repository.issue(parent, subIssues)",
    "performed": True,
    "baseline": BASELINE_COMMIT,
    "issues_queried": (431, 432, 433, 434, 435, 436, 437, 438, 439, 440, 441, 442, 443),
    "native_parents_found": 0,
    "native_sub_issues_found": 0,
    "positive_control": "#402 -> subIssues [405, 406, 409, 411]; #405 -> parent 402",
    "state": "pending-native-link",
    "drift_vs_issue_body_plan": (
        "#431's manifest plans 12 parent edges and 9 blocked-by edge sets; none of the "
        "parent edges exists natively. The issue-body navigation and the native tree "
        "therefore disagree completely, which is the already-declared state rather than "
        "new drift."
    ),
    "cycles_found": 0,
    "cycles_note": "no native edge exists, so no native cycle can exist",
    "old_relationships_disturbed": 0,
    "repair_performed": False,
    "repair_note": (
        "No relationship repair was attempted. The ticket authorizes only authorized "
        "repair; creating the edges was not authorized to this session, and no permission "
        "was expanded and no workflow was deployed. The readback is read-only."
    ),
    "claim": (
        "native-tree verification was PERFORMED and returned an empty tree; this rollup "
        "does NOT claim the planned native edges exist"
    ),
}


# ---------------------------------------------------------------------------
# Gaps.
# ---------------------------------------------------------------------------

GAPS: tuple[GapItem, ...] = (
    GapItem(
        gap_id="G-435-PIT",
        title="MarketHub price-row point-in-time / provider lineage is absent",
        owner="MarketHub owner (yosef-server)",
        blocks=("A0-E01",),
        remediation="Publish a price-row as-of/PIT contract and per-row provider lineage for "
        "stock_daily_1d. Health checks, dataset versions, the provider capability catalogue "
        "and the financial PIT endpoint were each probed and none of them substitutes. Until "
        "then quant_runtime's a0_baseline live preflight stays `blocked` on "
        "data_semantics:point_in_time and data_semantics:provider_lineage.",
    ),
    GapItem(
        gap_id="G-435-FUTURES",
        title="Futures 1m gaps accepted as baseline, not repaired",
        owner="user (decision already recorded on #435)",
        blocks=(),
        remediation="No action required for the #444 queue: the user explicitly accepted the "
        "current futures dataset as the backtest baseline and deferred further backfill. The "
        "gap evidence (225 day-gap rows / 33 dates; 1,522 night-internal-gap rows / 454 "
        "sessions) stays authoritative and #435 stays open rather than being closed as "
        "repaired.",
    ),
    GapItem(
        gap_id="G-442-ENGINE",
        title="No owner-authorized ResearchEnginePort configuration exists",
        owner="Apex Research owner",
        blocks=("A0-E02",),
        remediation="Bind an implementation to the ResearchEnginePort Protocol in "
        "apex-research and publish an owner-authorized engine reference plus a separate "
        "budget approval. `run_a0_round_two` already accepts one through EngineAuthorization "
        "with no contract change. Do not use the developer shell's general-purpose provider "
        "keys: they are not an owner authorization and spending on them was never approved.",
    ),
    GapItem(
        gap_id="G-434-RULES",
        title="A0-B0-RULES was never delivered as an owner artifact",
        owner="#434 owner (Apex Research)",
        blocks=("A0-X01", "A0-G01"),
        remediation="Publish the frozen rule file, parameters, V0/V1 delta and comparison "
        "protocol with an exact version and digest, and backfill the A0-B0-RULES row of "
        "docs/research/a0/a0_delivery_index.*. #434 is CLOSED but the row is still `pending`; "
        "every allowed-action and stop policy downstream is a fixture until it lands.",
    ),
    GapItem(
        gap_id="G-437-ORACLE",
        title="A0-FIXTURES-ORACLE was never delivered as an owner artifact",
        owner="#437 owner (Apex Research)",
        blocks=("A0-X01", "A0-X02", "A0-G01"),
        remediation="Publish the versioned fixture inputs, expected traces and oracle notes "
        "with an exact digest. Until then every fixture in this package is #437-*shaped* and "
        "self-built, which is why A0-X01 and A0-X02 have no evidence at all.",
    ),
    GapItem(
        gap_id="G-438-STRATEGY",
        title="No EMA-crossback reference strategy exists in any checked-out repository",
        owner="#438 owner (Runtime/strategy owner)",
        blocks=("A0-X01", "A0-X02"),
        remediation="Publish the ordinary reference strategy and its V0/V1 inputs. Searched "
        "at this baseline: no 'crossback' implementation under quant-runtime/src, "
        "apex-research/src or strategy-workspace/src.",
    ),
    GapItem(
        gap_id="G-441-ASSETS",
        title="#441's round-one artifacts are unreachable from this checkout",
        owner="#441 owner (Apex Research / Runtime)",
        blocks=("A0-E01", "A0-H02"),
        remediation="Publish runtime/q441/evidence-index.md, runtime/q441/a0-study-report.md "
        "and the named run/snapshot identities somewhere a cross-repository consumer can "
        "read, and backfill the A0-ROUND-1 row. Until then A0-E01 cannot move past "
        "`owner_reported_unverifiable` and A0-H02's real-asset half has nothing to delete "
        "and recover.",
    ),
    GapItem(
        gap_id="G-427-SANDBOX",
        title="No real sandbox execution backs the gate-order proof",
        owner="#421/#427 owner (StrategyWorkspace / Runtime)",
        blocks=("A0-V01",),
        remediation="Run the ordered validation gates and a preparation-versus-export "
        "attempt in a real sandbox and publish the gate trace. #429 proves the ordering and "
        "the prepare-is-not-export property against the contract, which satisfies only the "
        "`gate_trace` half of #431's required evidence type for this scenario.",
    ),
    GapItem(
        gap_id="G-429-WHEELS",
        title="No owner wheel is installed, so the installed/no-source half never ran",
        owner="release/packaging owner",
        blocks=("A0-E03",),
        remediation="Build and install the strategy_workspace / apex_research / quant_runtime "
        "/ strategy_reporting wheels, then run the two pre-existing installed tests plus "
        "_spec027_installed_test.py. Those two failures are the honest signal of this gap and "
        "must not be silenced.",
    ),
    GapItem(
        gap_id="G-431-NATIVE",
        title="No native GitHub parent/sub-issue edge exists for the A0 tree",
        owner="repository admin",
        blocks=(),
        remediation="Create the 12 parent edges of #431's manifest through an authorized "
        "interface and read them back. Verified absent at this baseline by GraphQL with a "
        "working positive control (#402/#405). No repair was attempted here because none was "
        "authorized to this session.",
    ),
)


# ---------------------------------------------------------------------------
# Derived views.
# ---------------------------------------------------------------------------


def scenario_ids() -> tuple[str, ...]:
    """The twenty-seven scenario ids, in #431's published order."""

    return tuple(record.scenario_id for record in A0_SCENARIOS)


def scenario(scenario_id: str) -> ScenarioRecord:
    """One scenario by id."""

    for record in A0_SCENARIOS:
        if record.scenario_id == scenario_id:
            return record
    raise KeyError(scenario_id)


def passed_scenario_ids() -> tuple[str, ...]:
    """Scenarios executed here with evidence of the type #431 requires.

    This is the only definition of "passed" the rollup publishes, and it is
    deliberately strict: a cited owner measurement, a correctly-reported
    `not_run`, a pending upstream artifact and an executed proof of the wrong
    evidence type are all excluded.
    """

    return tuple(record.scenario_id for record in A0_SCENARIOS if record.passed)


def scenario_ids_with_status(status: str) -> tuple[str, ...]:
    """Every scenario currently in the given status."""

    if status not in SCENARIO_STATUSES:
        raise ValueError(status)
    return tuple(record.scenario_id for record in A0_SCENARIOS if record.status == status)


def type_mismatched_scenario_ids() -> tuple[str, ...]:
    """Scenarios whose evidence is not of every type #431 requires."""

    return tuple(
        record.scenario_id for record in A0_SCENARIOS if not record.evidence_type_matches
    )


def evidence_refs(records: Iterable[ScenarioRecord | JointScenario]) -> tuple[TestRef, ...]:
    """Every distinct test reference claimed by the given records, in stable order."""

    seen: dict[tuple[str, str], TestRef] = {}
    for record in records:
        for ref in record.evidence:
            seen.setdefault((ref.module, ref.test), ref)
    return tuple(seen[key] for key in sorted(seen))


def commit_refs() -> tuple[CommitRef, ...]:
    """Every distinct commit claimed by any ticket, in stable order."""

    seen: dict[str, CommitRef] = {}
    for record in ALL_TICKETS:
        for ref in record.commits:
            seen.setdefault(ref.sha, ref)
    return tuple(seen[key] for key in sorted(seen))


def uncovered_scenario_ids() -> tuple[str, ...]:
    """Scenario ids no ticket claims. Empty means nothing was silently dropped."""

    claimed: set[str] = set()
    for record in OLD_TICKETS:
        claimed.update(record.scenario_ids)
    for record in A0_TICKETS:
        if record.ticket != "#443":
            claimed.update(record.scenario_ids)
    return tuple(sid for sid in scenario_ids() if sid not in claimed)


def engineering_report() -> dict[str, object]:
    """Did the code, tests and contracts get built correctly?

    This is an engineering conclusion only.  It says nothing about whether any
    research happened, and nothing about whether any strategy works.
    """

    return {
        "conclusion": "pass_with_declared_gaps",
        "summary": (
            "The acceptance seam was built correctly. Ten standard-library modules compose "
            "into a public contract with no dependency, no service, no second fact authority "
            "and no per-strategy special case. Every claimed test resolves, every claimed "
            "commit exists, and each ticket in the queue confirmed red/green for its own "
            "invariants."
        ),
        "scenarios_passed": len(passed_scenario_ids()),
        "scenarios_total": len(A0_SCENARIOS),
        "no_new_production_dependency": True,
        "no_pydantic_or_basemodel": True,
        "no_strategy_name_special_case": True,
        "generic_regression_reused_not_rebuilt": True,
        "known_suite_failures": (
            "_a0_installed_test.py::test_a0_installed_tracer_is_not_source_preferred",
            "_installed_test.py::test_installed_wheel_has_no_source_checkout_precedence",
        ),
        "known_suite_failures_reason": (
            "both assert the package runs from an installed wheel; no wheel is installed "
            "here. They are the honest signal of gap G-429-WHEELS and were not silenced."
        ),
        "not_claimed": (
            "that the installed/no-source environment was exercised",
            "that a real sandbox run or a real concurrency measurement happened here",
            "that any strategy behaviour oracle exists",
        ),
    }


def rule_implementation_report() -> dict[str, object]:
    """Were the A0 *rules* implemented correctly?

    Kept separate from the engineering conclusion because it is a different
    question with a different answer.
    """

    return {
        "conclusion": "cannot_be_concluded",
        "summary": (
            "The A0 rule set was never delivered as an owner artifact. A0-B0-RULES (#434) and "
            "A0-FIXTURES-ORACLE (#437) are both still `pending` in the delivery index and "
            "A0-REFERENCE-STRATEGY (#438) has no implementation in any checked-out "
            "repository, even though all three tickets are CLOSED. With no frozen rule, no "
            "frozen oracle and no reference strategy, rule-implementation correctness has "
            "nothing to be checked against."
        ),
        "b0_frozen": False,
        "b1_frozen": False,
        "scenarios_without_any_evidence": ("A0-X01", "A0-X02"),
        "blocking_gaps": ("G-434-RULES", "G-437-ORACLE", "G-438-STRATEGY"),
        "not_claimed": (
            "that the first EMA Crossback rule was implemented correctly",
            "that the V0/V1 delta is only the volume-contraction component",
        ),
    }


def research_findings_report() -> dict[str, object]:
    """What was actually learned about the research question?

    The honest answer is: nothing yet.  Building correct fail-closed machinery
    is an engineering result, not a research result, and this rollup keeps the
    two claims apart on purpose.
    """

    return {
        "conclusion": "no_research_finding",
        "a0_question": (
            "In a clearly ruleised first EMA Crossback, does adding a volume-contraction "
            "filter provide incremental value?"
        ),
        "answer": "unanswered",
        "summary": (
            "No finding is published, in either direction. The only round-one execution "
            "anyone claims is #441's, whose own receipt reports comparison_present=false, "
            "zero orders, zero fills and zero positions across both V0 and V1, and an "
            "explicitly inconclusive result. Two runs that place no orders cannot separate a "
            "component's contribution from its absence. No second round happened at all: "
            "A0-E02 is not_run for want of an authorized engine."
        ),
        "v1_better_than_v0": "unknown",
        "profitability_claimed": False,
        "statistical_significance_claimed": False,
        "causal_claim": False,
        "engineering_success_is_not_research_success": (
            "Nineteen of twenty-seven scenarios passing means the machinery refuses the right "
            "things in the right order. It does not mean any research was performed."
        ),
        "not_claimed": (
            "that the volume-contraction filter adds value",
            "that it does not add value",
            "that any A0 result is reproducible, since #441's artifacts are unreachable here",
        ),
    }


def research_qualification_report() -> dict[str, object]:
    """Is the research even *qualified* to produce a finding yet?

    Separate again: a study can be well-executed and still unqualified, or
    unexecuted and unqualified for different reasons.
    """

    return {
        "conclusion": "not_qualified",
        "summary": (
            "A0 does not currently meet its own declared qualification bar. The data "
            "readiness gate is open (no price-row PIT, no provider lineage), the rule and "
            "oracle baselines were never frozen as owner artifacts, and the one claimed run "
            "cannot be verified from this repository."
        ),
        "data_readiness": "blocked",
        "data_readiness_detail": (
            "#435 remains OPEN with data_semantics:point_in_time and "
            "data_semantics:provider_lineage unevaluated. The user separately accepted the "
            "futures 1m gaps as the backtest baseline so the queue could proceed; that "
            "decision unblocked the QUEUE, not the PIT/lineage gate."
        ),
        "b0_b1_frozen": False,
        "holdout_consumed": False,
        "lookahead_or_future_information_leak_found": False,
        "lookahead_check_detail": (
            "Every fixture in this package is synthetic, test-only and lives under pytest's "
            "tmp_path. The no-hindsight properties are asserted positively by "
            "#401's dual-time tests and #404's U6 rebuild-cost test."
        ),
        "undeclared_profit_or_significance_threshold": False,
        "blocking_gaps": ("G-435-PIT", "G-434-RULES", "G-437-ORACLE", "G-441-ASSETS"),
    }


def final_rollup_readback() -> dict[str, object]:
    """The whole rollup as one deterministic public record."""

    return {
        "schema": A0_ROLLUP_SCHEMA,
        "provenance": ROLLUP_PROVENANCE,
        "baseline": BASELINE_COMMIT,
        "scenarios": [record.as_dict() for record in A0_SCENARIOS],
        "joint_scenarios": [record.as_dict() for record in JOINT_SCENARIOS],
        "tickets": [record.as_dict() for record in ALL_TICKETS],
        "gaps": [gap.as_dict() for gap in GAPS],
        "native_relationships": dict(NATIVE_RELATIONSHIP_READBACK),
        "passed_scenario_ids": list(passed_scenario_ids()),
        "not_run_scenario_ids": list(scenario_ids_with_status("not_run")),
        "pending_scenario_ids": list(scenario_ids_with_status("pending")),
        "cited_scenario_ids": list(scenario_ids_with_status("cited_owner_evidence")),
        "owner_reported_scenario_ids": list(
            scenario_ids_with_status("owner_reported_unverifiable")
        ),
        "type_mismatched_scenario_ids": list(type_mismatched_scenario_ids()),
        "uncovered_scenario_ids": list(uncovered_scenario_ids()),
        "engineering_report": engineering_report(),
        "rule_implementation_report": rule_implementation_report(),
        "research_findings_report": research_findings_report(),
        "research_qualification_report": research_qualification_report(),
        "sign_off": "partial",
        "sign_off_reason": (
            "19 of 27 scenarios pass with evidence of the required type. A0-E01 is "
            "owner-reported but unverifiable here, A0-E02 and A0-E03 are not_run, A0-X01 and "
            "A0-X02 are pending for want of a frozen oracle and reference strategy, A0-L03 is "
            "cited owner evidence rather than a measurement of this rollup's own, and A0-G01 "
            "and A0-V01 are executed but lack one required evidence type each. Engineering "
            "acceptance is a pass with declared gaps; research completion is not claimed at "
            "all."
        ),
    }
