"""Build and replay the bounded installed-wheel SPEC-031 public tracer."""

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
    "quant-runtime": "62ae7b00f6b31515b81760fe1d34c7f13dc36857",
    "strategy-workspace": "1e9c58251efcf48dd8e4d8bc66007dbe105affba",
}
TIMEOUT_SECONDS = 240
NODES = (
    (
        "quant-research",
        "tools/test_validate_architecture_constitution.py",
        "ConstitutionValidationTests::test_spec_031_strict_replication_admission_is_valid",
    ),
    (
        "quant-research",
        "tools/test_verify_public_seam_architecture.py",
        "PublicSeamArchitectureTests::test_spec031_acceptance_scope_selects_replication_and_freezes_unchanged_owners",
    ),
    (
        "apex-research",
        "tests/test_replication_policy.py",
        "test_replication_case_round_trips_with_partitioned_evidence_and_identity",
    ),
    (
        "apex-research",
        "tests/test_replication_policy.py",
        "test_replication_case_rejects_partition_confusion_and_free_form_formal_rules",
    ),
    (
        "apex-research",
        "tests/test_replication_policy.py",
        "test_replication_identity_mutates_each_meaning_bearing_dimension",
    ),
    (
        "apex-research",
        "tests/test_replication_fail_closed.py",
        "test_non_executable_replication_finishes_with_design_and_zero_formal_side_effects",
    ),
    (
        "apex-research",
        "tests/test_replication_fail_closed.py",
        "test_prerequisite_ledger_preserves_every_decisive_gap",
    ),
    (
        "apex-research",
        "tests/test_replication_candidate_lane.py",
        "test_typed_replication_reuses_candidate_lane_and_stops_at_formal_eligibility",
    ),
    (
        "apex-research",
        "tests/test_replication_candidate_lane.py",
        "test_candidate_lane_rejection_publishes_exact_observation_and_stops",
    ),
    (
        "apex-research",
        "tests/test_replication_formal_execution.py",
        "test_formal_execution_attaches_identity_equivalent_completion_on_replay",
    ),
    (
        "apex-research",
        "tests/test_replication_formal_execution.py",
        "test_formal_execution_rejects_incompatible_owner_facts",
    ),
    (
        "apex-research",
        "tests/test_evidence_v2.py",
        "test_runtime_composer_binds_exact_lineage_data_costs_metrics_and_artifacts",
    ),
    (
        "apex-research",
        "tests/test_replication_comparison.py",
        "test_closed_comparison_outcomes_are_derived_only_from_frozen_selectors",
    ),
    (
        "apex-research",
        "tests/test_replication_comparison.py",
        "test_comparison_publishes_apex_decision_and_report_source_without_empirical_call",
    ),
    (
        "apex-research",
        "tests/test_replication_comparison.py",
        "test_comparison_dimensions_are_the_closed_specification_set",
    ),
    (
        "strategy-reporting",
        "tests/test_replication_reporting.py",
        "test_replication_report_publish_verify_and_rebuild_is_deterministic",
    ),
    (
        "strategy-reporting",
        "tests/test_replication_reporting.py",
        "test_replication_source_unknown_field_fails_without_weakening_legacy",
    ),
    (
        "strategy-reporting",
        "tests/test_replication_reporting.py",
        "test_render_study_cli_adds_replication_subject_without_changing_legacy_flag",
    ),
    (
        "strategy-reporting",
        "tests/test_replication_reporting.py",
        "test_render_study_cli_dispatches_each_closed_replication_outcome",
    ),
)


class TracerFailure(InstalledWheelFailure):
    pass


def _progress(message: str) -> None:
    print(f"SPEC031_PROGRESS {message}", file=__import__("sys").stderr, flush=True)


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
    VERIFIER._scan_spec031_replication_seams(repository_root, required=True)
    with tempfile.TemporaryDirectory(prefix="spec031-installed-") as temporary:
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
                    str(snapshot / "quant-research/tools/spec031_installed_wheel_tracer.py"),
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
            raise TracerFailure("SPEC-031 installed identity transcript drifted on replay")
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
        ComparisonCriterion,
        ReplicationComparisonPolicy,
        ReplicationOutcome,
        ResearchAssumption,
    )
    from strategy_reporting import ReplicationReadModelBuilder

    criterion = ComparisonCriterion(
        source_selector="source.metrics.sharpe",
        formal_selector="formal.nautilus.metrics.sharpe",
        mode="exact",
        tolerance_micros=0,
        direction=None,
    )
    policy = ReplicationComparisonPolicy.create(
        policy_version="installed-smoke.v1",
        criteria=(criterion,),
        empirical_methods=(),
    )
    changed_policy = ReplicationComparisonPolicy.create(
        policy_version="installed-smoke.v2",
        criteria=(criterion,),
        empirical_methods=(),
    )
    assumption = ResearchAssumption.create(
        selector="research.assumptions.rebalance_timing",
        value="close",
        rationale="installed public identity probe",
    )
    if policy.policy_id == changed_policy.policy_id:
        raise TracerFailure("meaning-bearing comparison policy change reused identity")
    if ReplicationReadModelBuilder is None:
        raise TracerFailure("installed Reporting lacks replication read model")
    outcomes = sorted(item.value for item in ReplicationOutcome)
    if outcomes != ["directional", "exact", "failed", "not_reproducible"]:
        raise TracerFailure("installed Apex replication outcomes are not closed")
    return {
        "ok": True,
        "comparison_policy_id": policy.policy_id,
        "assumption_id": assumption.assumption_id,
        "outcomes": outcomes,
        "identity_dimensions": [
            "assumptions",
            "comparison_policy",
            "data_mapping",
            "extracted_spec",
            "package",
            "protocol",
            "source",
        ],
        "connected_status": {
            "empirical": "not_run_policy_not_required",
            "markethub": "not_run_requires_connected_environment",
            "oci": "not_run_not_impacted",
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
