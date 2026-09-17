"""#429 SG-V1D: the Genome/Package flow acceptance pass.

Every test here is evidence for exactly one item in
``research_genome_flow.GENOME_ACCEPTANCE_ITEMS`` or ``A0_GENOME_ITEMS``, and the
last section resolves the whole matrix against the real test functions so a
renamed or deleted test breaks the rollup instead of silently leaving an item
uncovered -- the same discipline #404 used for RM-AC01-RM-AC18.

Two honesty rules apply throughout.

* The Genome product lives in ``williamxhero/StrategyWorkspace``.  Nothing here
  imports it, and no test claims to have exercised it.  What is proved is the
  **public contract shape** over #437-shaped synthetic fixtures.
* ``A0-E01`` and ``A0-E02`` have no real asset.  The test below asserts they are
  reported ``not_run``; that is evidence the status is honest, not evidence the
  criterion is met.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

from .research_genome_flow import (
    A0_GENOME_ITEMS,
    BINDING_FIELDS,
    COMPATIBILITY_MATRIX,
    CONSUMPTION_REFUSALS,
    CURRENT_MAJOR,
    FORMALLY_CONSUMABLE,
    GENOME_ACCEPTANCE_ITEMS,
    GENOME_MATRIX_SCHEMA,
    GOLDEN_STAGES,
    IDENTITY_KINDS,
    LEGACY_ADAPTERS,
    ORDERED_GATES,
    STAGE_PREREQUISITES,
    ConformanceBinding,
    ContentAddressStore,
    GenomeRecord,
    GenomeRefusal,
    Provenance,
    QualificationFlags,
    VerificationLedger,
    adapter_for,
    canonical_digest,
    compare_packages,
    consume_for_formal_run,
    genome_matrix_readback,
    identity_kind,
    identity_of,
    not_run_items,
    replay_from_public_facts,
    run_golden_flow,
    stage_cycles,
)

_PACKAGE_DIR = Path(__file__).resolve().parent


# --- #437-shaped synthetic fixtures (test-only; never a real strategy) -------


def _candidate_ir() -> dict[str, object]:
    """The *existing* typed Candidate IR, verbatim.  No second DSL is defined."""

    return {
        "ir_schema": "a0.candidate-ir.v1",
        "nodes": [
            {"id": "n1", "op": "select_universe", "args": {"as_of": "2025-12-31"}},
            {"id": "n2", "op": "rank", "args": {"by": "n1", "lag": 1}},
            {"id": "n3", "op": "allocate", "args": {"by": "n2", "cap": 20}},
        ],
        "outputs": ["n3"],
    }


def _genome() -> dict[str, object]:
    return {"ir_digest": canonical_digest(_candidate_ir()), "parameters": {"cap": 20, "lag": 1}}


def _package() -> dict[str, object]:
    return {"genome_digest": canonical_digest(_genome()), "artifact": "sha256:" + "a" * 64}


def _binding(**overrides: str) -> ConformanceBinding:
    base = {
        "validator_id": "a0-validator",
        "suite_id": "a0-conformance-suite",
        "comparator_id": "a0-comparator",
        "environment_id": "a0-env",
        "dependency_lock": "sha256:" + "d" * 64,
        "configuration_id": "a0-config",
        "policy_id": "a0-policy",
    }
    base.update(overrides)
    return ConformanceBinding(**base)  # type: ignore[arg-type]


def _provenance(attempt: str = "attempt-1") -> Provenance:
    return Provenance(attempt_id=attempt, proposer="a0-owner", recorded_at="2026-01-01T00:00:00Z")


def _flow(store: ContentAddressStore, ledger: VerificationLedger, **kwargs: object):
    params: dict[str, object] = {
        "candidate_ir": _candidate_ir(),
        "genome_content": _genome(),
        "package_content": _package(),
        "binding": _binding(),
        "provenance": _provenance(),
    }
    params.update(kwargs)
    return run_golden_flow(store, ledger, **params)  # type: ignore[arg-type]


# --- SG-AC01: the golden flow and its identities ----------------------------


def test_the_golden_flow_runs_every_stage_in_order_and_keeps_six_identities() -> None:
    store, ledger = ContentAddressStore(), VerificationLedger()
    outcome = _flow(store, ledger)

    assert outcome.stages == GOLDEN_STAGES
    assert tuple(sorted(outcome.identities)) == tuple(sorted(IDENTITY_KINDS))
    # Six identities, six distinct values, each labelled with its own kind.
    assert len(set(outcome.identities.values())) == len(IDENTITY_KINDS)
    for kind, identity in outcome.identities.items():
        assert identity_kind(identity) == kind

    readback = outcome.readback()
    assert readback["new_backtests"] == 0
    assert readback["model_invocations"] == 0
    assert readback["budget_reservations"] == 0
    assert readback["used_private_storage"] is False
    assert readback["second_dsl_introduced"] is False
    # Deterministic: the whole readback is canonically serialisable.
    assert json.loads(json.dumps(readback, sort_keys=True)) == readback


def test_preparation_is_not_export_and_the_stage_graph_has_no_cycle() -> None:
    """The ticket's non-circularity requirement, as a checkable fact."""

    assert stage_cycles() == ()
    # Verification depends on preparation and on nothing downstream of it.
    assert STAGE_PREREQUISITES["independent_conformance"] == ("package_preparation",)
    assert "owner_publication" not in STAGE_PREREQUISITES["independent_conformance"]
    assert "formal_package_export" not in STAGE_PREREQUISITES["independent_conformance"]
    # Preparation and export are different stages, in that order.
    assert GOLDEN_STAGES.index("package_preparation") < GOLDEN_STAGES.index(
        "formal_package_export"
    )
    # Every prerequisite is itself a declared stage, listed earlier.
    for stage, needs in STAGE_PREREQUISITES.items():
        for need in needs:
            assert GOLDEN_STAGES.index(need) < GOLDEN_STAGES.index(stage)


def test_the_candidate_ir_is_stored_verbatim_and_no_second_dsl_appears() -> None:
    store, ledger = ContentAddressStore(), VerificationLedger()
    outcome = _flow(store, ledger)
    candidate = store.get(outcome.identities["candidate"])
    assert candidate is not None
    assert dict(candidate.content) == _candidate_ir()
    assert candidate.content["ir_schema"] == "a0.candidate-ir.v1"
    # The Genome cites the IR digest rather than restating the program.
    genome = store.get(outcome.identities["genome"])
    assert genome is not None
    assert genome.content["ir_digest"] == canonical_digest(_candidate_ir())
    assert genome.references == (candidate.identity,)


def test_the_three_gates_run_in_their_fixed_order_before_preparation() -> None:
    store, ledger = ContentAddressStore(), VerificationLedger()
    stages = _flow(store, ledger).stages
    positions = [stages.index(gate) for gate in ORDERED_GATES]
    assert positions == sorted(positions)
    assert max(positions) < stages.index("package_preparation")


def test_identical_payloads_of_different_kinds_never_share_an_identity() -> None:
    payload = {"same": "bytes"}
    identities = {identity_of(kind, payload) for kind in IDENTITY_KINDS}
    assert len(identities) == len(IDENTITY_KINDS)
    # The *digest* differs too, not merely the label.  Were the kind outside the
    # digest, a Package identity could be re-labelled a Genome identity by
    # rewriting its prefix and would still reproduce.
    digests = {identity.split(":", 1)[1] for identity in identities}
    assert len(digests) == len(IDENTITY_KINDS)
    with pytest.raises(GenomeRefusal):
        identity_of("strategy", payload)
    with pytest.raises(GenomeRefusal):
        identity_kind("genome:not-a-digest")


# --- SG-AC02: compatibility, no private read --------------------------------


def test_every_compatibility_case_keeps_its_documented_behaviour() -> None:
    store, mirror = ContentAddressStore(), ContentAddressStore()
    prov = _provenance()
    left = store.register("package", {"a": 1}, provenance=prov)
    # A genuinely separate record, written by a separate store, with the same
    # canonical content: the comparison is real rather than object identity.
    same = mirror.register("package", {"a": 1}, provenance=_provenance("attempt-2"))
    other = store.register("package", {"a": 2}, provenance=prov)
    legacy = store.register("package", {"a": 1, "legacy": True}, major=0, provenance=prov)
    redacted = store.register("package", {"a": "<redacted>"}, provenance=prov)
    genome = store.register("genome", {"a": 1}, provenance=prov)

    assert left.identity == same.identity

    assert compare_packages(left, same) == "equal"
    assert compare_packages(left, other) == "different"
    assert compare_packages(left, legacy) == "incomparable"
    assert compare_packages(left, redacted) == "incomparable"
    assert compare_packages(left, genome) == "incomparable"

    assert adapter_for(CURRENT_MAJOR) == "current"
    assert adapter_for(0) == LEGACY_ADAPTERS[0]
    assert set(COMPATIBILITY_MATRIX) == {
        "current_major",
        "named_legacy_adapter",
        "unsupported_major",
        "unsupported_kind",
        "redacted_compare",
        "incompatible_compare",
    }


def test_an_unsupported_major_has_no_adapter_and_no_silent_fallback() -> None:
    with pytest.raises(GenomeRefusal):
        adapter_for(99)
    store, ledger = ContentAddressStore(), VerificationLedger()
    with pytest.raises(GenomeRefusal):
        _flow(store, ledger, major=99)
    # The refusal happened before anything was written or verified.
    assert store.identities() == ()
    assert ledger.sandbox_invocations == 0


def test_the_genome_seam_imports_no_owner_wheel_and_no_private_storage() -> None:
    """A structural check: the module cannot reach the owner's repository."""

    tree = ast.parse((_PACKAGE_DIR / "research_genome_flow.py").read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    forbidden = {
        "apex_research",
        "quant_runtime",
        "strategy_reporting",
        "strategy_workspace",
        "networkx",
        "sqlalchemy",
        "pydantic",
        "mlflow",
        "optuna",
        "hypothesis",
        "os",
        "subprocess",
        "socket",
        "urllib",
        "pickle",
    }
    assert roots & forbidden == set()
    # And the owner wheels really are absent from this environment, which is
    # why the installed half of this ticket is reported not_run.
    assert "strategy_workspace" not in sys.modules
    assert genome_matrix_readback()["installed_wheels_present"] is False


# --- SG-AC03: preparation, reuse and stale bindings -------------------------


def test_a_prepared_package_cannot_enter_the_formal_path() -> None:
    store = ContentAddressStore()
    prepared = store.register(
        "package", _package(), state="prepared", provenance=_provenance()
    )
    outcome = consume_for_formal_run(
        store, prepared.identity, grant_scope="formal", authorization_current=True
    )
    assert outcome.admitted is False
    assert outcome.refusal == "not_formally_consumable"
    assert "prepared" not in FORMALLY_CONSUMABLE
    assert "registered" not in FORMALLY_CONSUMABLE

    store.advance(prepared.identity, "validated")
    assert consume_for_formal_run(
        store, prepared.identity, grant_scope="formal", authorization_current=True
    ).admitted is True


def test_a_sandbox_only_grant_cannot_enter_the_ordinary_formal_path() -> None:
    store = ContentAddressStore()
    record = store.register("package", _package(), state="published", provenance=_provenance())
    outcome = consume_for_formal_run(
        store, record.identity, grant_scope="sandbox", authorization_current=True
    )
    assert outcome.refusal == "sandbox_only_grant"
    assert outcome.execution_eligible is False


def test_an_exact_repeat_reuses_verification_and_runs_no_new_sandbox_work() -> None:
    store, ledger = ContentAddressStore(), VerificationLedger()
    first = _flow(store, ledger)
    assert first.sandbox_invocations == 1

    record = store.get(first.identities["package"])
    assert record is not None
    again = ledger.verify(record, _binding())
    assert again.reused is True
    assert ledger.sandbox_invocations == 1
    assert again.evidence_ref == ledger.evidence_for(record, _binding()).evidence_ref


def test_any_binding_change_revalidates_instead_of_reusing() -> None:
    store, ledger = ContentAddressStore(), VerificationLedger()
    flow = _flow(store, ledger)
    record = store.get(flow.identities["package"])
    assert record is not None

    for index, name in enumerate(BINDING_FIELDS, start=1):
        changed = ledger.verify(record, _binding(**{name: f"changed-{name}"}))
        assert changed.reused is False, name
        assert ledger.sandbox_invocations == 1 + index, name


def test_a_stale_binding_cannot_complete_a_formal_consumption() -> None:
    store, ledger = ContentAddressStore(), VerificationLedger()
    flow = _flow(store, ledger)
    outcome = consume_for_formal_run(
        store,
        flow.identities["package"],
        grant_scope="formal",
        authorization_current=True,
        binding=_binding(environment_id="a-different-environment"),
        ledger=ledger,
    )
    assert outcome.admitted is False
    assert outcome.refusal == "binding_stale"
    # The exact declared binding still admits it.
    assert consume_for_formal_run(
        store,
        flow.identities["package"],
        grant_scope="formal",
        authorization_current=True,
        binding=_binding(),
        ledger=ledger,
    ).admitted is True


def test_a_non_conformant_result_is_never_admitted_and_never_reclassified() -> None:
    store, ledger = ContentAddressStore(), VerificationLedger()
    record = store.register("package", _package(), state="published", provenance=_provenance())
    evidence = ledger.verify(record, _binding(), conformant=False)
    assert evidence.conformant is False
    outcome = consume_for_formal_run(
        store,
        record.identity,
        grant_scope="formal",
        authorization_current=True,
        binding=_binding(),
        ledger=ledger,
    )
    assert outcome.refusal == "not_conformant"


def test_the_four_qualification_flags_are_independent() -> None:
    store, ledger = ContentAddressStore(), VerificationLedger()
    flow = _flow(store, ledger)
    # Published and behaviour-conformant, yet NOT research-qualified: that
    # remains the statistical owner's separate decision.
    assert flow.flags.published is True
    assert flow.flags.behavior_conformant is True
    assert flow.flags.research_qualified is False
    # And the four are stored, never derived.
    flags = QualificationFlags(True, False, False, False)
    assert flags.as_dict() == {
        "contract_valid": True,
        "behavior_conformant": False,
        "published": False,
        "research_qualified": False,
    }


# --- SG-AC04: identity, idempotency and content addressing ------------------


def test_a_second_attempt_keeps_the_genome_identity_and_adds_its_provenance() -> None:
    store = ContentAddressStore()
    first = store.register("genome", _genome(), provenance=_provenance("attempt-1"))
    second = store.register("genome", _genome(), provenance=_provenance("attempt-2"))
    assert first.identity == second.identity
    assert [item.attempt_id for item in second.provenances] == ["attempt-1", "attempt-2"]
    # Provenance is outside the digest, so it cannot move the identity.
    assert second.identity == identity_of("genome", _genome())


def test_different_bytes_can_never_take_over_an_existing_identity() -> None:
    store = ContentAddressStore()
    record = store.register("genome", _genome(), provenance=_provenance())

    # A different payload simply gets its own identity.  It never lands on an
    # existing one, and the first record is untouched.
    other = store.register("genome", {"different": "bytes"}, provenance=_provenance())
    assert other.identity != record.identity
    stored = store.get(record.identity)
    assert stored is not None and dict(stored.content) == _genome()

    # And the re-bind guard itself: a tampered store entry holding the wrong
    # bytes under a real identity is refused rather than accepted or silently
    # overwritten when the true content is offered again.
    tampered = ContentAddressStore()
    tampered.register("genome", {"different": "bytes"}, provenance=_provenance())
    hijacked = GenomeRecord(
        kind="genome",
        identity=record.identity,
        content={"different": "bytes"},
        references=(),
        state="registered",
        major=CURRENT_MAJOR,
        provenances=(),
    )
    tampered._records[record.identity] = hijacked
    with pytest.raises(GenomeRefusal):
        tampered.register("genome", _genome(), provenance=_provenance())


def test_the_same_identity_with_a_different_reference_set_is_rejected() -> None:
    store = ContentAddressStore()
    anchor = store.register("candidate", _candidate_ir(), provenance=_provenance())
    store.register("genome", _genome(), references=(anchor.identity,), provenance=_provenance())
    with pytest.raises(GenomeRefusal):
        store.register("genome", _genome(), references=(), provenance=_provenance())


def test_a_new_attempt_cannot_clear_a_tombstone() -> None:
    store = ContentAddressStore()
    record = store.register("package", _package(), provenance=_provenance("attempt-1"))
    store.advance(record.identity, "tombstoned")
    assert store.tombstoned() == (record.identity,)
    with pytest.raises(GenomeRefusal):
        store.register("package", _package(), provenance=_provenance("attempt-2"))
    with pytest.raises(GenomeRefusal):
        store.advance(record.identity, "published")
    assert consume_for_formal_run(
        store, record.identity, grant_scope="formal", authorization_current=True
    ).refusal == "tombstoned"


def test_content_addressing_admits_no_self_reference_and_no_cycle() -> None:
    store, ledger = ContentAddressStore(), VerificationLedger()
    _flow(store, ledger)
    assert store.reference_cycles() == ()
    # A forward reference is refused, which is what makes a cycle unbuildable.
    with pytest.raises(GenomeRefusal):
        store.register(
            "genome", {"x": 1}, references=("genome:sha256:" + "0" * 64,),
            provenance=_provenance(),
        )
    # And an identity cannot cite itself: it is not in the store yet.
    with pytest.raises(GenomeRefusal):
        store.register(
            "genome", {"y": 1}, references=(identity_of("genome", {"y": 1}),),
            provenance=_provenance(),
        )


def test_a_rejected_record_is_terminal_and_distinct_from_a_tombstone() -> None:
    store = ContentAddressStore()
    record = store.register("package", _package(), provenance=_provenance())
    store.advance(record.identity, "rejected")
    with pytest.raises(GenomeRefusal):
        store.advance(record.identity, "published")
    assert consume_for_formal_run(
        store, record.identity, grant_scope="formal", authorization_current=True
    ).refusal == "rejected"
    assert "rejected" != "tombstoned"


# --- SG-AC05: the joint research-use scenarios ------------------------------


def test_the_u1_u6_scenarios_are_referenced_from_the_research_memory_evidence() -> None:
    """#381's U1-U6 are established by #399/#401/#404/#408 and referenced here.

    Re-deriving them would create a second source of truth, which the ticket
    explicitly forbids.  So the check is that the reference resolves.
    """

    from .research_ac_matrix import JOINT_SCENARIOS

    assert tuple(scenario.scenario_id for scenario in JOINT_SCENARIOS) == (
        "U1", "U2", "U3", "U4", "U5", "U6",
    )
    for scenario in JOINT_SCENARIOS:
        assert scenario.evidence, scenario.scenario_id
        for ref in scenario.evidence:
            module = sys.modules.get(f"{__package__}.{ref.module}")
            if module is None:
                module = __import__(f"{__package__}.{ref.module}", fromlist=["_"])
            assert callable(getattr(module, ref.test)), f"{ref.module}.{ref.test}"


def test_a_matching_genome_alone_neither_blocks_nor_establishes_equivalence() -> None:
    """A Genome identity is one input, never the whole run key.

    #399's decision layer owns this rule; here it is restated at the Genome
    seam, because "same Genome" is exactly the shortcut this architecture must
    not take.
    """

    store = ContentAddressStore()
    genome = store.register("genome", _genome(), provenance=_provenance())
    # Two runs over the same Genome but different data ranges are two runs.
    first = store.register(
        "run",
        {"genome": genome.identity, "data_range": "2020-2023"},
        references=(genome.identity,),
        provenance=_provenance(),
    )
    second = store.register(
        "run",
        {"genome": genome.identity, "data_range": "2024-2025"},
        references=(genome.identity,),
        provenance=_provenance(),
    )
    assert first.identity != second.identity
    # And the same Genome with the same inputs is one run, not two pieces of
    # independent evidence.
    repeat = store.register(
        "run",
        {"genome": genome.identity, "data_range": "2020-2023"},
        references=(genome.identity,),
        provenance=_provenance("attempt-2"),
    )
    assert repeat.identity == first.identity
    assert len(repeat.provenances) == 2


# --- SG-AC06: replay, and the three separate permissions --------------------


def test_replay_rebuilds_frozen_identities_with_zero_run_call_and_budget() -> None:
    store, ledger = ContentAddressStore(), VerificationLedger()
    flow = _flow(store, ledger)
    facts = [
        {"kind": record.kind, "identity": record.identity, "content": dict(record.content)}
        for record in (store.get(identity) for identity in store.identities())
        if record is not None
    ]
    outcome = replay_from_public_facts(facts, flow.identities.values())
    assert outcome.coverage == "complete"
    assert set(outcome.rebuilt) == set(flow.identities.values())
    readback = outcome.as_dict()
    assert readback["new_backtests"] == 0
    assert readback["model_invocations"] == 0
    assert readback["budget_reservations"] == 0
    assert readback["used_fixture_substitute"] is False


def test_an_unavailable_payload_replays_as_limited_and_is_never_substituted() -> None:
    store, ledger = ContentAddressStore(), VerificationLedger()
    flow = _flow(store, ledger)
    missing = flow.identities["run"]
    facts = [
        {"kind": record.kind, "identity": record.identity, "content": dict(record.content)}
        for record in (store.get(identity) for identity in store.identities())
        if record is not None and record.identity != missing
    ]
    outcome = replay_from_public_facts(facts, flow.identities.values())
    assert outcome.coverage == "limited"
    assert outcome.unavailable == (missing,)
    assert missing not in outcome.rebuilt


def test_a_doctored_public_fact_fails_loudly_during_replay() -> None:
    doctored = [
        {
            "kind": "genome",
            "identity": identity_of("genome", {"not": "this"}),
            "content": _genome(),
        }
    ]
    with pytest.raises(GenomeRefusal):
        replay_from_public_facts(doctored, ())
    with pytest.raises(GenomeRefusal):
        replay_from_public_facts([{"kind": "genome"}], ())


def test_historical_readability_is_not_eligibility_is_not_redelivery() -> None:
    store = ContentAddressStore()
    record = store.register("package", _package(), state="published", provenance=_provenance())

    revoked = consume_for_formal_run(
        store, record.identity, grant_scope="formal", authorization_current=False
    )
    assert revoked.refusal == "authorization_revoked"
    # The record is still historically readable, but neither runnable nor
    # re-deliverable today.  Three booleans, three answers.
    assert revoked.historically_readable is True
    assert revoked.execution_eligible is False
    assert revoked.redelivery_permitted is False

    absent = consume_for_formal_run(
        store, identity_of("package", {"gone": True}),
        grant_scope="formal", authorization_current=True,
    )
    assert absent.refusal == "facts_missing"
    assert absent.historically_readable is False
    # A refusal publishes no content and no count.
    assert absent.as_dict()["package_identity"] is None


def test_a_mismatched_identity_is_refused_and_leaks_nothing() -> None:
    store = ContentAddressStore()
    genome = store.register("genome", _genome(), state="published", provenance=_provenance())
    outcome = consume_for_formal_run(
        store, genome.identity, grant_scope="formal", authorization_current=True
    )
    assert outcome.refusal == "identity_mismatch"
    assert outcome.package_identity is None
    assert set(CONSUMPTION_REFUSALS) >= {
        "identity_mismatch", "facts_missing", "authorization_revoked", "unknown_major",
    }


def test_a_record_whose_major_is_not_current_cannot_run_formally() -> None:
    store = ContentAddressStore()
    legacy = store.register(
        "package", _package(), state="published", major=0, provenance=_provenance()
    )
    outcome = consume_for_formal_run(
        store, legacy.identity, grant_scope="formal", authorization_current=True, declared_major=0
    )
    assert outcome.refusal == "unknown_major"
    # The named adapter still lets it be *read*; reading is not running.
    assert adapter_for(0) == LEGACY_ADAPTERS[0]
    assert outcome.historically_readable is True


# --- SG-AC07: owner boundary, dependencies, honest status -------------------


def test_the_owner_measured_evidence_is_cited_and_never_claimed_as_re_measured() -> None:
    readback = genome_matrix_readback()
    cited = readback["cited_owner_evidence"]
    assert isinstance(cited, dict)
    assert set(cited) == {"#419", "#422", "#427/#428"}
    for issue, text in cited.items():
        assert "NOT re" in text or "not repeated" in text, issue
    assert readback["owner_repository"] == "williamxhero/StrategyWorkspace"
    assert "neither imported nor modified here" in str(readback["owner_boundary"])
    # Conformance, performance, concurrency and end-to-end stay separate: none
    # of this repository's items claims any of them.
    for item in GENOME_ACCEPTANCE_ITEMS:
        assert item.evidence_class != "cited_from_owner_ticket" or item.status == "not_run"


def test_the_seam_adds_no_dependency_and_needs_no_optional_service() -> None:
    """Standard library only: no OPA, MLflow, Optuna, graph or vector service."""

    source = (_PACKAGE_DIR / "research_genome_flow.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    assert roots <= {"__future__", "hashlib", "json", "collections", "dataclasses", "typing"}
    # No class in the module derives from a BaseModel, and pydantic is absent.
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                name = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", "")
                assert name != "BaseModel", node.name


def test_the_rollup_never_counts_a_not_run_item_as_passed() -> None:
    readback = genome_matrix_readback()
    assert readback["schema"] == GENOME_MATRIX_SCHEMA
    pending = set(readback["not_run_item_ids"])  # type: ignore[arg-type]
    passed = set(readback["passed_item_ids"])  # type: ignore[arg-type]
    assert pending == {"A0-E01", "A0-E02"}
    assert pending & passed == set()
    assert readback["sign_off"] == "partial"
    assert readback["stage_cycles"] == []
    assert json.loads(json.dumps(readback, sort_keys=True)) == readback


# --- the A0 reference slice -------------------------------------------------


def test_a0_g04_v02_the_a0_flow_keeps_its_identities_and_refuses_the_bad_inputs() -> None:
    store, ledger = ContentAddressStore(), VerificationLedger()
    flow = _flow(store, ledger)

    # 1. Every identity survives and stays distinct.
    assert len(set(flow.identities.values())) == len(IDENTITY_KINDS)
    package = flow.identities["package"]

    # 2. Permitted reuse avoids redundant verification.
    before = ledger.sandbox_invocations
    assert consume_for_formal_run(
        store, package, grant_scope="formal", authorization_current=True,
        binding=_binding(), ledger=ledger,
    ).admitted is True
    assert ledger.sandbox_invocations == before

    # 3. Preparation-only, mismatched and revoked inputs are each refused, with
    #    their own reason.
    prepared = store.register(
        "package", {"prepared": "only"}, state="prepared", provenance=_provenance()
    )
    refusals = {
        consume_for_formal_run(
            store, prepared.identity, grant_scope="formal", authorization_current=True
        ).refusal,
        consume_for_formal_run(
            store, flow.identities["genome"], grant_scope="formal", authorization_current=True
        ).refusal,
        consume_for_formal_run(
            store, package, grant_scope="formal", authorization_current=False
        ).refusal,
    }
    assert refusals == {"not_formally_consumable", "identity_mismatch", "authorization_revoked"}


def test_a0_q02_an_independent_oracle_catches_identity_time_and_binding_mutations() -> None:
    """Three declared mutations, three detections, by recomputation not by trust."""

    store, ledger = ContentAddressStore(), VerificationLedger()
    flow = _flow(store, ledger)
    record = store.get(flow.identities["package"])
    assert record is not None

    # (a) identity mutation: the declared identity no longer reproduces.
    with pytest.raises(GenomeRefusal):
        replay_from_public_facts(
            [{"kind": "package", "identity": flow.identities["genome"],
              "content": dict(record.content)}],
            (),
        )

    # (b) time mutation: a provenance timestamp change must not move the
    #     identity, and must not be lost either.
    later = store.register(
        "package",
        dict(record.content),
        references=record.references,
        state=record.state,
        provenance=Provenance("attempt-2", "a0-owner", "2027-06-01T00:00:00Z"),
    )
    assert later.identity == record.identity
    assert {item.recorded_at for item in later.provenances} == {
        "2026-01-01T00:00:00Z", "2027-06-01T00:00:00Z",
    }

    # (c) binding mutation: a single changed field is detected as stale.
    assert consume_for_formal_run(
        store, record.identity, grant_scope="formal", authorization_current=True,
        binding=_binding(policy_id="mutated-policy"), ledger=ledger,
    ).refusal == "binding_stale"


def test_a0_q02_no_production_module_branches_on_a_strategy_name() -> None:
    """The generic framework has no per-strategy route.

    The check is structural: no production module in this package contains a
    string literal naming a strategy, so there is nothing for a comparison to
    branch on.  A0's non-CPA small regression therefore exercises the same code
    path any other strategy would.
    """

    names = {
        "cpa", "doub", "momentum", "reversal", "breakout", "pairs", "meanrev",
        "turtle", "macd", "rsi", "grid", "martingale",
    }
    offenders: list[str] = []
    for path in sorted(_PACKAGE_DIR.glob("*.py")):
        if path.name.endswith("_test.py") or path.name == Path(__file__).name:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                token = node.value.strip().lower().replace("-", "").replace("_", "")
                if token in names:
                    offenders.append(f"{path.name}: {node.value!r}")
    assert offenders == []


def test_a0_e01_e02_report_not_run_and_are_never_substituted() -> None:
    """The two real-asset items are pending.  This test is NOT their evidence.

    It asserts only that the rollup reports them ``not_run``, names the owner
    issue that would supply the asset, and offers no fixture in their place.
    """

    pending = {item.item_id: item for item in not_run_items()}
    assert set(pending) == {"A0-E01", "A0-E02"}
    assert pending["A0-E01"].owner_issue == "#441"
    assert pending["A0-E02"].owner_issue == "#442"
    for item in pending.values():
        assert item.evidence_class == "pending_real_asset"
        assert item.status == "not_run"
        assert "NOT evidence" in item.note or "never mocked" in item.note

    # The #442 finding is unchanged by this ticket: still no real asset.
    index = Path(__file__).resolve().parents[2] / "docs/research/a0/a0_delivery_index.json"
    if index.exists():
        assert "pending" in index.read_text(encoding="utf-8")


def test_a0_e03_h02_references_408_rather_than_reimplementing_recovery() -> None:
    from . import research_recovery

    item = {entry.item_id: entry for entry in A0_GENOME_ITEMS}["A0-E03/H02"]
    assert item.owner_issue == "#408"
    assert any(ref.module == "_research_recovery_test" for ref in item.evidence)
    # The reference is live: #408's public recovery seam still exists and is
    # not duplicated here.
    assert callable(research_recovery.recover_end_to_end)
    genome_source = (_PACKAGE_DIR / "research_genome_flow.py").read_text(encoding="utf-8")
    assert "def recover_end_to_end" not in genome_source


# --- the matrix resolves against the real tests -----------------------------


def test_every_matrix_evidence_reference_resolves_to_a_real_test() -> None:
    unresolved: list[str] = []
    for item in (*GENOME_ACCEPTANCE_ITEMS, *A0_GENOME_ITEMS):
        for ref in item.evidence:
            module = __import__(f"{__package__}.{ref.module}", fromlist=["_"])
            if not callable(getattr(module, ref.test, None)):
                unresolved.append(f"{item.item_id} -> {ref.module}.{ref.test}")
    assert unresolved == []


def test_every_acceptance_item_has_evidence_and_a_declared_class() -> None:
    for item in (*GENOME_ACCEPTANCE_ITEMS, *A0_GENOME_ITEMS):
        assert item.evidence, item.item_id
        assert item.evidence_class in {
            "proven_in_this_repo", "cited_from_owner_ticket", "pending_real_asset",
        }
        # A pending item is never marked executed, and vice versa.
        assert (item.evidence_class == "pending_real_asset") == (item.status == "not_run")


def test_the_seven_ticket_acceptance_criteria_each_have_one_item() -> None:
    assert tuple(item.item_id for item in GENOME_ACCEPTANCE_ITEMS) == (
        "SG-AC01", "SG-AC02", "SG-AC03", "SG-AC04", "SG-AC05", "SG-AC06", "SG-AC07",
    )
    assert tuple(item.item_id for item in A0_GENOME_ITEMS) == (
        "A0-G04/V02", "A0-E01", "A0-E02", "A0-E03/H02", "A0-Q02",
    )
