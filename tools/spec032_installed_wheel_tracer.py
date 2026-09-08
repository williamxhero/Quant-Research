"""Build and replay the bounded installed-wheel SPEC-032 public tracer."""

from __future__ import annotations

import argparse
import importlib.util
import json
import tempfile
import time
from pathlib import Path
from typing import Any

HARNESS_PATH = Path(__file__).with_name("installed_wheel_harness.py")
HARNESS_SPEC = importlib.util.spec_from_file_location(
    "installed_wheel_harness", HARNESS_PATH
)
assert HARNESS_SPEC is not None and HARNESS_SPEC.loader is not None
HARNESS = importlib.util.module_from_spec(HARNESS_SPEC)
HARNESS_SPEC.loader.exec_module(HARNESS)
VERIFIER_PATH = Path(__file__).with_name("verify_public_seam_architecture.py")
VERIFIER_SPEC = importlib.util.spec_from_file_location(
    "verify_public_seam_architecture", VERIFIER_PATH
)
assert VERIFIER_SPEC is not None and VERIFIER_SPEC.loader is not None
VERIFIER = importlib.util.module_from_spec(VERIFIER_SPEC)
VERIFIER_SPEC.loader.exec_module(VERIFIER)

InstalledWheelFailure = HARNESS.InstalledWheelFailure
REPOSITORIES = (
    "strategy-workspace",
    "quant-runtime",
    "apex-research",
    "strategy-reporting",
)
UNCHANGED_SOURCE_BASELINES = {
    "strategy-workspace": "1e9c58251efcf48dd8e4d8bc66007dbe105affba"
}
TIMEOUT_SECONDS = 240
NODES = (
    (
        "quant-research",
        "tools/test_validate_architecture_constitution.py",
        "ConstitutionValidationTests::test_spec_032_revalidation_admission_is_valid",
    ),
    (
        "quant-research",
        "tools/test_verify_public_seam_architecture.py",
        "PublicSeamArchitectureTests::test_spec032_acceptance_scope_selects_revalidation_and_freezes_owner_bounds",
    ),
    (
        "quant-runtime",
        "tests/test_preflight.py",
        "test_versioned_preflight_exposes_runtime_owned_sample_observation",
    ),
    (
        "apex-research",
        "tests/test_revalidation.py",
        "test_elapsed_trigger_publishes_due_currency_without_changing_maturity",
    ),
    (
        "apex-research",
        "tests/test_revalidation.py",
        "test_schedule_freezes_identity_scope_stages_and_budget",
    ),
    (
        "apex-research",
        "tests/test_revalidation.py",
        "test_strategy_decay_uses_only_comparable_formal_owner_facts",
    ),
    (
        "apex-research",
        "tests/test_revalidation.py",
        "test_revalidation_reissues_evidence_and_qualification_through_public_seams",
    ),
    (
        "apex-research",
        "tests/test_revalidation.py",
        "test_evidence_archive_exposes_currency_aware_active_and_historical_view",
    ),
    (
        "apex-research",
        "tests/test_revalidation_cli.py",
        "test_revalidation_cli_publishes_policy_with_stable_envelope",
    ),
    (
        "strategy-reporting",
        "tests/test_revalidation_read_model.py",
        "test_builder_copies_maturity_currency_budget_decay_and_archive_without_recalculation",
    ),
    (
        "strategy-reporting",
        "tests/test_revalidation_read_model.py",
        "test_renderer_escapes_owner_text_and_cli_is_deterministic",
    ),
    (
        "strategy-reporting",
        "tests/test_revalidation_read_model.py",
        "test_unknown_referenced_schema_fails_closed",
    ),
)


class TracerFailure(InstalledWheelFailure):
    pass


def _progress(message: str) -> None:
    print(f"SPEC032_PROGRESS {message}", file=__import__("sys").stderr, flush=True)


def build_and_run(repository_root: Path) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    root_repository = Path(__file__).resolve().parents[1]
    environment = HARNESS.sanitized_environment()
    if "PYTHONPATH" in environment:
        raise TracerFailure("sanitized tracer environment retained PYTHONPATH")
    repositories = {
        "quant-research": root_repository,
        **{name: repository_root / name for name in REPOSITORIES},
    }
    VERIFIER._scan_spec032_revalidation_seams(repository_root, required=True)
    with tempfile.TemporaryDirectory(prefix="spec032-installed-") as temporary:
        isolated = Path(temporary).resolve()
        dist = isolated / "dist"
        dist.mkdir()
        topology = {
            name: HARNESS.verify_source_topology(path, environment)
            for name, path in repositories.items()
        }
        unchanged = HARNESS.verify_unchanged_sources(
            repository_root, UNCHANGED_SOURCE_BASELINES, environment
        )
        snapshot = isolated / "source-snapshot"
        snapshot.mkdir()
        for name, path in repositories.items():
            HARNESS.snapshot_repository(
                path, snapshot / name, topology[name]["source_files"]
            )
        wheels = HARNESS.build_wheels(snapshot, REPOSITORIES, dist, environment)
        python = HARNESS.create_installed_environment(
            isolated, wheels, environment, install_pytest=True
        )
        source_roots = tuple(snapshot / name / "src" for name in REPOSITORIES)
        for replay in (1, 2):
            for owner, relative, node in NODES:
                started = time.monotonic()
                _progress(f"replay={replay} node={node} start")
                HARNESS.run_installed_pytest(
                    python,
                    (Path(f"{snapshot / owner / relative}::{node}"),),
                    REPOSITORIES,
                    source_roots,
                    cwd=isolated,
                    environment=environment,
                    timeout_seconds=TIMEOUT_SECONDS,
                )
                _progress(
                    f"replay={replay} node={node} passed_seconds={time.monotonic() - started:.1f}"
                )
        smoke_results = []
        for replay in (1, 2):
            output = HARNESS.run_command(
                [
                    str(python),
                    "-I",
                    "-B",
                    str(
                        snapshot
                        / "quant-research/tools/spec032_installed_wheel_tracer.py"
                    ),
                    "--repository-root",
                    str(snapshot),
                    "--smoke-root",
                    str(isolated / f"smoke-{replay}"),
                ],
                cwd=isolated,
                environment=environment,
                timeout_seconds=TIMEOUT_SECONDS,
            )
            smoke_results.append(json.loads(output))
        if smoke_results[0] != smoke_results[1]:
            raise TracerFailure(
                "SPEC-032 installed identity transcript drifted on replay"
            )
        return {
            **smoke_results[0],
            "nodes": len(NODES),
            "replays": 2,
            "node_timeout_seconds": TIMEOUT_SECONDS,
            "unchanged_sources": unchanged,
            "source_topology": topology,
        }


def smoke(_root: Path) -> dict[str, Any]:
    import apex_research
    import quant_runtime
    import strategy_reporting
    import strategy_workspace
    from apex_research import (
        CurrencyAwareEvidenceArchiveView,
        CurrencyStatus,
        DecayCandidateKind,
        DecayEvaluator,
        DecayObservation,
        EvidenceCurrencyBinding,
        EvidenceV2RecordRef,
        RevalidationPlan,
        RevalidationPolicy,
        RevalidationPolicyService,
        RevalidationService,
        RevalidationStage,
        RevalidationStageExecution,
        RevalidationStagePlan,
        RevalidationTrigger,
    )
    from apex_research.governance import (
        ActionGrant,
        BudgetAmount,
        BudgetDimension,
        BudgetUnit,
        GovernedAction,
        GovernedActionResult,
        Principal,
        PrincipalKind,
        ResourceClass,
        ResourceKind,
        ResourceRef,
    )
    from apex_research.records import PublishedRecordRef
    from strategy_reporting import RevalidationReadModelBuilder, RevalidationRenderer

    class Workspace:
        def __init__(self) -> None:
            self.records: dict[str, dict[str, Any]] = {}

        def publish_record(self, value: dict[str, Any]) -> dict[str, Any]:
            publication = {
                "schema": "quant-research.publication.v1",
                "record_id": value["record_id"],
                "record_type": value["record_type"],
                "created_at": "2026-09-09T00:00:00Z",
                "payload": value["payload"],
                "artifacts": value.get("artifacts", []),
                "lineage": value.get("lineage", []),
            }
            current = self.records.setdefault(str(value["record_id"]), publication)
            if current != publication:
                raise TracerFailure("immutable Workspace publication conflicted")
            return current

        def get_record(self, record_id: str) -> dict[str, Any]:
            return self.records[record_id]

        def list_records(
            self, *, record_type: str | None = None, limit: int = 100
        ) -> list[dict[str, Any]]:
            values = [
                value
                for value in self.records.values()
                if record_type is None or value["record_type"] == record_type
            ]
            return sorted(values, key=lambda value: str(value["record_id"]))[:limit]

    events: list[str] = []

    class Governance:
        def execute(self, request: Any, adapter: Any) -> GovernedActionResult:
            events.append("reservation")
            response = adapter(ActionGrant(reservation=None))
            return GovernedActionResult(
                status="committed",
                reason=response.reason.value,
                value=response.value,
                reservation=PublishedRecordRef(
                    record_id="d" * 64,
                    record_type="apex-research.action-reservation.v1",
                ),
                settlement=PublishedRecordRef(
                    record_id="e" * 64,
                    record_type="apex-research.action-settlement.v1",
                ),
            )

        def recover(self, _campaign_id: str) -> tuple[GovernedActionResult, ...]:
            events.append("recover")
            return ()

    workspace = Workspace()
    policy = RevalidationPolicy.create(
        version="installed.v1",
        due_after_seconds=10,
        stale_after_seconds=20,
        new_sample_threshold=2,
        required_triggers=(RevalidationTrigger.ELAPSED_TIME,),
    )
    policy_service = RevalidationPolicyService(workspace)
    policy_service.publish_policy(policy)
    evidence = PublishedRecordRef(
        record_id="1" * 64, record_type="apex-research.evidence.v2"
    )
    qualification = PublishedRecordRef(
        record_id="2" * 64, record_type="apex-research.qualification-decision.v1"
    )
    currency = policy_service.evaluate(
        policy=policy,
        evidence=evidence,
        qualification=qualification,
        qualification_maturity="research_qualified",
        qualified_at="2026-01-01T00:00:00Z",
        as_of="2026-01-01T00:00:15Z",
        observations=(),
    )
    resource = ResourceRef(
        kind=ResourceKind.DATASET, resource_id="fixture", version="v1"
    )
    budget = (
        BudgetAmount(
            dimension=BudgetDimension.ACTION_CALLS,
            unit=BudgetUnit.COUNT,
            currency=None,
            resource_class=ResourceClass.GENERAL,
            amount=1,
        ),
    )
    stage = RevalidationStagePlan(
        stage=RevalidationStage.DATA,
        action=GovernedAction.EXTERNAL_VALIDATION,
        resource_class=ResourceClass.GENERAL,
        resources=(resource,),
        budget=budget,
    )

    def plan(key: str) -> RevalidationPlan:
        return RevalidationPlan.create(
            campaign_id="3" * 64,
            idempotency_key=key,
            policy=policy.ref(),
            governance_policy=PublishedRecordRef(
                record_id="4" * 64, record_type="apex-research.campaign-policy.v1"
            ),
            principal=Principal(
                kind=PrincipalKind.ORCHESTRATOR, principal_id="installed-revalidator"
            ),
            evidence=evidence,
            qualification=qualification,
            candidate_closure=(
                PublishedRecordRef(
                    record_id="5" * 64,
                    record_type="apex-research.strategy-candidate.v1",
                ),
            ),
            runtime_observation_sha256="6" * 64,
            package_lock_sha256="7" * 64,
            dependency_lock_sha256="8" * 64,
            model_artifact_sha256=None,
            as_of="2026-01-01T00:00:15Z",
            stages=(stage,),
        )

    service = RevalidationService(workspace, Governance())
    success_plan = service.schedule_from_plan(plan("installed-success"))

    def success_adapter(_stage: Any, _grant: Any) -> RevalidationStageExecution:
        events.append("adapter")
        return RevalidationStageExecution(
            status="completed",
            evidence_level="data-observation",
            owner_refs=(
                PublishedRecordRef(
                    record_id="9" * 64,
                    record_type="quant-runtime.data-change-observation.v1",
                ),
            ),
            reason="Runtime observation complete",
        )

    outcome = service.advance(success_plan.ref(), success_adapter)
    decay = DecayEvaluator().evaluate(
        candidate_kind=DecayCandidateKind.STRATEGY,
        plan=success_plan.ref(),
        observations=(
            DecayObservation(
                selector="formal.nautilus.metrics.sharpe_ratio",
                unit="ratio",
                direction="maximize",
                status="evaluated",
                prior_value_micros=1_000_000,
                current_value_micros=1_100_000,
                prior_comparability_group="a" * 64,
                current_comparability_group="a" * 64,
                sources=(
                    PublishedRecordRef(
                        record_id="b" * 64,
                        record_type="apex-research.validation-evidence.v1",
                    ),
                ),
                reason="comparable formal owner fact",
            ),
        ),
    )
    closure = service.close(
        success_plan.ref(), decays=(decay,), prior_currency=currency
    )
    recovered = service.recover(success_plan.ref())
    failure_plan = service.schedule_from_plan(plan("installed-failure"))
    failed = service.advance(
        failure_plan.ref(),
        lambda _stage, _grant: RevalidationStageExecution(
            status="failed",
            evidence_level="data-observation",
            owner_refs=(),
            reason="declared stage failure",
        ),
    )
    cancellation = service.cancel(failure_plan.ref(), reason="operator cancellation")
    unavailable = DecayEvaluator().evaluate(
        candidate_kind=DecayCandidateKind.STRATEGY,
        plan=success_plan.ref(),
        observations=(
            DecayObservation(
                selector="formal.nautilus.metrics.sharpe_ratio",
                unit="ratio",
                direction="maximize",
                status="blocked",
                prior_value_micros=None,
                current_value_micros=None,
                prior_comparability_group=None,
                current_comparability_group=None,
                sources=(
                    PublishedRecordRef(
                        record_id="c" * 64,
                        record_type="apex-research.validation-evidence.v1",
                    ),
                ),
                reason="formal owner fact unavailable",
            ),
        ),
    )
    current_evidence = EvidenceV2RecordRef(record_id="1" * 64)
    stale_evidence = EvidenceV2RecordRef(record_id="f" * 64)
    archive = CurrencyAwareEvidenceArchiveView.create(
        predecessor=PublishedRecordRef(
            record_id="0" * 64, record_type="apex-research.evidence-archive.v1"
        ),
        historical_entries=(current_evidence, stale_evidence),
        bindings=(
            EvidenceCurrencyBinding(
                evidence=current_evidence,
                currency_source=currency.ref(),
                currency=currency.currency,
                policy_overdue=False,
                reason="within stale threshold",
            ),
            EvidenceCurrencyBinding(
                evidence=stale_evidence,
                currency_source=currency.ref(),
                currency=CurrencyStatus.STALE,
                policy_overdue=True,
                reason="overdue historical Evidence",
            ),
        ),
        reason="installed archive projection",
    )
    if events[:2] != ["reservation", "adapter"]:
        raise TracerFailure("adapter ran before budget reservation")
    if RevalidationReadModelBuilder is None or RevalidationRenderer is None:
        raise TracerFailure("installed Reporting revalidation seam is unavailable")
    return {
        "ok": True,
        "policy_id": policy.policy_id,
        "currency": currency.currency,
        "maturity": currency.qualification_maturity,
        "plan_id": success_plan.plan_id,
        "outcome_id": outcome.outcome_id,
        "closure_id": closure.closure_id,
        "disposition": closure.disposition,
        "budget_reserved_before_adapter": True,
        "recovered_outcomes": [item.outcome_id for item in recovered],
        "failure_status": failed.status,
        "cancellation_id": cancellation.cancellation_id,
        "unavailable_status": unavailable.status,
        "historical_entries": [item.record_id for item in archive.historical_entries],
        "active_entries": [item.record_id for item in archive.active_entries],
        "connected_status": {
            "markethub": "not_run_requires_connected_environment",
            "runtime_oci": "not_run_requires_oci_environment",
            "apex_external_validation": "not_run_requires_oci_environment",
            "reporting_connected": "not_run_requires_connected_environment",
        },
        "versions": {
            "apex_research": apex_research.__version__,
            "quant_runtime": quant_runtime.__version__,
            "strategy_reporting": strategy_reporting.__version__,
            "strategy_workspace": strategy_workspace.__version__,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--smoke-root", type=Path)
    arguments = parser.parse_args(argv)
    try:
        result = (
            smoke(arguments.smoke_root)
            if arguments.smoke_root is not None
            else build_and_run(arguments.repository_root)
        )
    except (InstalledWheelFailure, TracerFailure, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
