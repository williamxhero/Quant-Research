"""Build and replay the bounded installed-wheel SPEC-030 public tracer."""

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

InstalledWheelFailure = HARNESS.InstalledWheelFailure
REPOSITORIES = (
    "strategy-workspace",
    "quant-runtime",
    "apex-research",
    "strategy-reporting",
)
UNCHANGED_SOURCE_BASELINES = {
    "strategy-workspace": "1e9c58251efcf48dd8e4d8bc66007dbe105affba",
    "strategy-reporting": "c601c5c03ed012fbba616713155fa80e527ba0d6",
}
TIMEOUT_SECONDS = 240
NODES = (
    (
        "quant-research",
        "tools/test_validate_architecture_constitution.py",
        "ConstitutionValidationTests::test_spec_030_factor_model_coevolution_admission_is_valid",
    ),
    (
        "apex-research",
        "tests/test_factor_model_coevolution.py",
        "test_generation_plan_freezes_all_variation_intents_before_actions",
    ),
    (
        "apex-research",
        "tests/test_factor_model_coevolution.py",
        "test_complete_discovery_frontier_preserves_success_and_failure_siblings",
    ),
    (
        "apex-research",
        "tests/test_factor_model_descendants.py",
        "test_typed_descendant_runs_through_engine_publication_and_static_gate",
    ),
    (
        "apex-research",
        "tests/test_factor_model_discovery.py",
        "test_governed_discovery_publishes_request_before_runtime_and_reads_owner_result",
    ),
    (
        "apex-research",
        "tests/test_factor_model_discovery.py",
        "test_verified_training_outcome_materializes_artifact_bearing_model_proposal",
    ),
    (
        "quant-runtime",
        "tests/test_candidate_discovery_cli.py",
        "test_candidate_discovery_cli_calculates_factor_from_frozen_bytes",
    ),
    (
        "quant-runtime",
        "tests/test_candidate_discovery_cli.py",
        "test_candidate_discovery_trains_model_and_replays_exact_artifact",
    ),
)


class TracerFailure(InstalledWheelFailure):
    pass


def _progress(message: str) -> None:
    print(f"SPEC030_PROGRESS {message}", file=__import__("sys").stderr, flush=True)


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
    with tempfile.TemporaryDirectory(prefix="spec030-installed-") as temporary:
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
                        / "quant-research/tools/spec030_installed_wheel_tracer.py"
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
                "SPEC-030 installed identity transcript drifted on replay"
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
        CoevolutionLimits,
        CoevolutionPolicy,
        DeterministicCoevolutionRng,
        SelectionRule,
        StopReason,
        VariationKind,
    )
    from apex_research.records import PublishedRecordRef
    from quant_runtime.cli import runtime_capabilities

    campaign = PublishedRecordRef(
        record_id="c" * 64, record_type="apex-research.campaign.v1"
    )
    policy = CoevolutionPolicy.create(
        campaign=campaign,
        policy_revision="installed-smoke.v1",
        variations=tuple(VariationKind),
        selection=SelectionRule(
            metric="discovery.metrics.mean_rank_ic",
            direction="maximize",
            tie_breaker="semantic_identity",
        ),
        limits=CoevolutionLimits(
            max_factor_population=2,
            max_model_population=2,
            max_combinations_per_generation=4,
            max_seeds_per_model=2,
            max_iterations=2,
            max_training_actions=4,
            max_training_cost_micros=1000,
            max_formal_candidates=1,
        ),
        rng=DeterministicCoevolutionRng(
            algorithm="sha256-counter", version="1", seed="installed-smoke"
        ),
        stop_reasons=tuple(StopReason),
    )
    capabilities = runtime_capabilities()
    if "candidate-discovery.v1" not in capabilities["capabilities"]:
        raise TracerFailure("installed Runtime lacks candidate discovery")
    return {
        "ok": True,
        "policy_id": policy.policy_id,
        "runtime_capability_id": capabilities["capability_id"],
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
