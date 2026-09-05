"""Build five-repository SPEC-015 acceptance and run with installed wheels only."""

from __future__ import annotations

import argparse
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
        python = create_installed_environment(
            isolated,
            wheels,
            environment,
            install_pytest=True,
        )
        for repository, targets in INSTALLED_TESTS:
            run_command(
                [
                    str(python),
                    "-m",
                    "pytest",
                    "-q",
                    *(str(repository_root / repository / target) for target in targets),
                ],
                cwd=isolated,
                environment=environment,
                timeout_seconds=900,
            )
        output = run_command(
            [
                str(python),
                str(Path(__file__).resolve()),
                "--repository-root",
                str(repository_root),
                "--smoke-root",
                str(isolated / "workspace"),
            ],
            cwd=isolated,
            environment=environment,
            timeout_seconds=300,
        )
        try:
            result = json.loads(output)
        except json.JSONDecodeError as exc:
            raise TracerFailure(f"installed tracer emitted invalid JSON: {output}") from exc
        if result.get("ok") is not True:
            raise TracerFailure(f"installed tracer failed: {result}")
        result["repositories"] = ["quant-research", *PACKAGE_REPOSITORIES]
        result["installed_tests"] = [
            f"{repository}/{target}"
            for repository, targets in INSTALLED_TESTS
            for target in targets
        ]
        result["qualification_acceptance"] = {
            "authority_exclusion": "passed",
            "blocked_incomparable_states": "passed",
            "golden_adjacent_research_qualified": "passed",
            "held_lineage_and_idempotency": "passed",
            "retirement_and_history": "passed",
            "single_successor_conflict": "passed",
            "skipped_and_stale_predecessor": "passed",
        }
        result["unchanged_sources"] = unchanged_sources
        return result


def smoke(repository_root: Path, smoke_root: Path) -> dict[str, Any]:
    import quant_runtime
    import strategy_reporting
    import strategy_workspace
    from strategy_workspace import WorkspaceClient

    import apex_research
    from apex_research import (
        QualificationDecision,
        QualificationEvaluation,
        QualificationEvaluationRequest,
        QualificationEvaluator,
        QualificationHistoryReader,
        QualificationPolicy,
        QualificationRetirement,
        QualificationRetirementRequest,
        QualificationService,
    )

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
    )
    if any(value.__module__ != "apex_research.qualification" for value in public_types):
        raise TracerFailure("qualification public exports do not resolve to the installed owner")
    workspace = WorkspaceClient(smoke_root)
    workspace.init()
    if workspace.list_records(limit=1) != []:
        raise TracerFailure("installed Workspace smoke root is not isolated")
    return {
        "ok": True,
        "pythonpath": "cleared",
        "distributions": distributions,
        "qualification_exports": [value.__name__ for value in public_types],
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
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
