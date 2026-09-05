"""Build five-repository SPEC-015 acceptance and run with installed wheels only."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from installed_wheel_harness import (
    InstalledWheelFailure,
    build_wheels,
    create_installed_environment,
    installed_distribution_manifest,
    run_command,
    run_installed_pytest,
    verify_unchanged_sources,
)

PACKAGE_REPOSITORIES = (
    "strategy-workspace",
    "quant-runtime",
    "apex-research",
    "strategy-reporting",
)
UNCHANGED_SOURCE_BASELINES = {
    "quant-runtime": "c97428c51e8f7265b006872c15999800e5ae1fc9",
    "strategy-reporting": "255442a9291ca49a67e05afa0123e10e07aeb754",
    "strategy-workspace": "1e9c58251efcf48dd8e4d8bc66007dbe105affba",
}
INSTALLED_TESTS = (
    (
        "strategy-workspace",
        ("tests/test_lineage_query.py",),
    ),
    (
        "quant-runtime",
        ("tests/test_architecture.py",),
    ),
    (
        "apex-research",
        (
            "tests/test_qualification_policy.py",
            (
                "tests/test_evidence_v2.py::"
                "test_four_section_states_are_closed_mutually_exclusive_and_require_owner_sources"
            ),
            "tests/test_qualification_evaluation.py",
            (
                "tests/test_qualification_validation.py::"
                "test_early_stopped_cell_remains_in_denominator_and_holds_validation"
            ),
            (
                "tests/test_qualification_validation.py::"
                "test_unknown_predecessor_decision_fails_closed"
            ),
            (
                "tests/test_qualification_robustness.py::"
                "test_complete_multidimensional_evidence_reaches_research_qualified"
            ),
            (
                "tests/test_qualification_robustness.py::"
                "test_partial_multidimensional_evidence_holds_at_validation_boundary"
            ),
            (
                "tests/test_qualification_history.py::"
                "test_held_evaluations_do_not_consume_the_one_successor_slot"
            ),
            "tests/test_qualification_cli.py",
        ),
    ),
    (
        "strategy-reporting",
        ("tests/test_workspace_roundtrip.py",),
    ),
)


class TracerFailure(InstalledWheelFailure):
    pass


def build_and_run(repository_root: Path) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    for repository in PACKAGE_REPOSITORIES:
        if not (repository_root / repository / "pyproject.toml").is_file():
            raise TracerFailure(f"repository is unavailable: {repository}")
    with tempfile.TemporaryDirectory(prefix="spec015-installed-") as temporary:
        isolated = Path(temporary).resolve()
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        dist = isolated / "dist"
        dist.mkdir()
        unchanged_sources = verify_unchanged_sources(
            repository_root,
            UNCHANGED_SOURCE_BASELINES,
            environment,
        )
        wheels = build_wheels(
            repository_root,
            PACKAGE_REPOSITORIES,
            dist,
            environment,
        )
        unchanged_after_build = verify_unchanged_sources(
            repository_root,
            UNCHANGED_SOURCE_BASELINES,
            environment,
        )
        if unchanged_after_build != unchanged_sources:
            raise TracerFailure("unchanged repository source identity raced during wheel build")
        python = create_installed_environment(
            isolated,
            wheels,
            environment,
            install_pytest=True,
        )
        for repository, targets in INSTALLED_TESTS:
            run_installed_pytest(
                python,
                (repository_root / repository / target for target in targets),
                ("apex_research", "quant_runtime", "strategy_reporting", "strategy_workspace"),
                (repository_root / name / "src" for name in PACKAGE_REPOSITORIES),
                cwd=isolated,
                environment=environment,
                timeout_seconds=900,
            )
        smoke_results = []
        for index in range(2):
            output = run_command(
                [
                    str(python),
                    "-I",
                    str(Path(__file__).resolve()),
                    "--repository-root",
                    str(repository_root),
                    "--smoke-root",
                    str(isolated / f"workspace-{index}"),
                ],
                cwd=isolated,
                environment=environment,
                timeout_seconds=300,
            )
            try:
                smoke_results.append(json.loads(output))
            except json.JSONDecodeError as exc:
                raise TracerFailure(f"installed tracer emitted invalid JSON: {output}") from exc
        if smoke_results[0] != smoke_results[1]:
            raise TracerFailure("installed tracer identity output is not stable across processes")
        result = smoke_results[0]
        if result.get("ok") is not True:
            raise TracerFailure(f"installed tracer failed: {result}")
        result["repositories"] = ["quant-research", *PACKAGE_REPOSITORIES]
        result["installed_tests"] = [
            f"{repository}/{target}"
            for repository, targets in INSTALLED_TESTS
            for target in targets
        ]
        result["stable_smoke_runs"] = 2
        result["wheel_sha256"] = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(wheels)
        }
        result["unchanged_sources"] = unchanged_sources
        return result


def smoke(repository_root: Path, smoke_root: Path) -> dict[str, Any]:
    import apex_research
    import quant_runtime
    import strategy_reporting
    import strategy_workspace
    from apex_research import (
        QualificationDecision,
        QualificationEvaluation,
        QualificationEvaluationRequest,
        QualificationEvaluator,
        QualificationHistoryReader,
        QualificationPolicy,
        QualificationPredecessor,
        QualificationRequirementObservation,
        QualificationRetirement,
        QualificationRetirementReason,
        QualificationRetirementRequest,
        QualificationService,
        QualificationState,
        QualificationValidationMetricRequirement,
    )
    from apex_research.candidates import StrategyRevisionRef
    from apex_research.evidence_v2 import (
        CampaignRecordRef,
        EvidenceV2RecordRef,
        ValidationProtocolRecordRef,
    )
    from apex_research.models import StrategyPackageRef
    from apex_research.records import PublishedRecordRef
    from strategy_workspace import WorkspaceClient

    if "PYTHONPATH" in os.environ:
        raise TracerFailure("installed tracer inherited PYTHONPATH")
    modules = (apex_research, quant_runtime, strategy_reporting, strategy_workspace)
    distributions = installed_distribution_manifest(
        modules,
        ("apex-research", "quant-runtime", "strategy-reporting", "strategy-workspace"),
    )
    public_types = (
        QualificationPolicy,
        QualificationEvaluationRequest,
        QualificationEvaluation,
        QualificationEvaluator,
        QualificationDecision,
        QualificationRetirementRequest,
        QualificationRetirement,
        QualificationHistoryReader,
        QualificationService,
        QualificationValidationMetricRequirement,
    )
    if any(value.__module__ != "apex_research.qualification" for value in public_types):
        raise TracerFailure("qualification public exports do not resolve to the installed owner")
    workspace = WorkspaceClient(smoke_root)
    workspace.init()
    if workspace.list_records(limit=1) != []:
        raise TracerFailure("installed Workspace smoke root is not isolated")
    candidate = StrategyRevisionRef(
        record_id="1" * 64,
        semantic_id="2" * 64,
        family_id="installed-tracer",
        revision=1,
    )
    predecessor = QualificationPredecessor(state=QualificationState.IDEA, record=candidate)
    common = {
        "campaign": CampaignRecordRef(record_id="3" * 64),
        "candidate": candidate,
        "strategy_package": StrategyPackageRef(
            schema="quant-research.strategy-package-ref.v1",
            strategy_id="installed-tracer",
            revision=1,
            package_hash="4" * 64,
        ),
        "protocol": ValidationProtocolRecordRef(record_id="5" * 64),
        "evidence": EvidenceV2RecordRef(record_id="6" * 64),
        "policy": PublishedRecordRef(
            record_id="7" * 64,
            record_type="apex-research.qualification-policy.v1",
        ),
        "predecessor": predecessor,
        "from_state": QualificationState.IDEA,
        "to_state": QualificationState.EXPERIMENTAL,
    }
    advance = QualificationEvaluation.create(
        **common,
        requirements=(
            QualificationRequirementObservation(
                requirement_id="candidate-gate",
                status="satisfied",
                reason="Exact installed identity fixture passed.",
                sources=(),
            ),
        ),
        disposition="advance",
        reason="Exact installed identity fixture passed.",
    )
    held = QualificationEvaluation.create(
        **common,
        requirements=(
            QualificationRequirementObservation(
                requirement_id="candidate-gate",
                status="failed",
                reason="Exact installed identity fixture held.",
                sources=(),
            ),
        ),
        disposition="held",
        reason="Exact installed identity fixture held.",
    )
    retirement = QualificationRetirementRequest.create(
        campaign=common["campaign"],
        candidate=candidate,
        policy=common["policy"],
        evidence=common["evidence"],
        predecessor=predecessor,
        reason=QualificationRetirementReason.POLICY_CHANGE,
    )
    reproduced = {
        "advance_evaluation": advance.evaluation_id,
        "decision": QualificationDecision.target_ref(advance).record_id,
        "held_evaluation": held.evaluation_id,
        "retirement": retirement.retirement_id,
        "scope": advance.scope,
        "operational_authority": advance.operational_authority,
    }
    if reproduced != {
        "advance_evaluation": QualificationEvaluation.create(
            **common,
            requirements=advance.requirements,
            disposition="advance",
            reason=advance.reason,
        ).evaluation_id,
        "decision": QualificationDecision.target_ref(advance).record_id,
        "held_evaluation": QualificationEvaluation.create(
            **common,
            requirements=held.requirements,
            disposition="held",
            reason=held.reason,
        ).evaluation_id,
        "retirement": QualificationRetirementRequest.create(
            campaign=common["campaign"],
            candidate=candidate,
            policy=common["policy"],
            evidence=common["evidence"],
            predecessor=predecessor,
            reason=QualificationRetirementReason.POLICY_CHANGE,
        ).retirement_id,
        "scope": "historical_research_maturity",
        "operational_authority": "forbidden",
    }:
        raise TracerFailure("installed qualification identities do not reproduce")
    return {
        "ok": True,
        "pythonpath": "cleared",
        "distributions": distributions,
        "qualification_exports": [value.__name__ for value in public_types],
        "identity_reproduction": reproduced,
        "smoke_workspace_isolated": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--smoke-root", type=Path)
    arguments = parser.parse_args(argv)
    try:
        result = (
            smoke(arguments.repository_root, arguments.smoke_root)
            if arguments.smoke_root is not None
            else build_and_run(arguments.repository_root)
        )
    except (InstalledWheelFailure, ImportError, OSError, TypeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
