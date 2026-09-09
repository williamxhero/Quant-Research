"""Build and replay the five-seam SPEC-017 archive tracer from wheels only."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

HARNESS_PATH = Path(__file__).with_name("installed_wheel_harness.py")
HARNESS_SPEC = importlib.util.spec_from_file_location("installed_wheel_harness", HARNESS_PATH)
assert HARNESS_SPEC is not None and HARNESS_SPEC.loader is not None
HARNESS = importlib.util.module_from_spec(HARNESS_SPEC)
HARNESS_SPEC.loader.exec_module(HARNESS)

InstalledWheelFailure = HARNESS.InstalledWheelFailure
PACKAGE_REPOSITORIES = (
    "strategy-workspace",
    "quant-runtime",
    "apex-research",
    "strategy-reporting",
)
UNCHANGED_SOURCE_BASELINES = {
    "strategy-workspace": "1e9c58251efcf48dd8e4d8bc66007dbe105affba",
    "quant-runtime": "c97428c51e8f7265b006872c15999800e5ae1fc9",
}
TRANSCRIPT_PREFIXES = {
    "generation": "SPEC017_APEX_GENERATION_TRANSCRIPT=",
    "evidence": "SPEC017_APEX_EVIDENCE_TRANSCRIPT=",
    "reporting": "SPEC017_REPORTING_TRANSCRIPT=",
}
APEX_ARCHIVE_TESTS = (
    "test_first_exploration_insertion_is_immutable_and_not_formal",
    "test_exploration_lifecycle_views_require_explicit_events_and_preserve_history",
    "test_public_exports_and_strict_archive_cli_cover_pure_evaluate_publish_and_replay",
    "test_lexicographic_policy_records_capacity_reject_tie_and_replacement",
    "test_pareto_policy_records_nondominance_unavailable_and_incomparable",
    "test_evidence_equal_values_from_different_comparability_groups_are_incomparable",
    "test_evidence_pareto_aligns_multiobjective_values_by_objective_id",
    "test_complete_generation_is_arrival_order_independent_and_strictly_replayable",
    "test_evidence_archive_publishes_only_historical_leader_and_blocks_current_view",
)
REPLAY_TESTS = APEX_ARCHIVE_TESTS[-2:]


class TracerFailure(InstalledWheelFailure):
    pass


def _progress(message: str) -> None:
    rendered = f"SPEC017_PROGRESS {message}"
    print(rendered, file=sys.stderr, flush=True)
    progress_file = os.environ.get("SPEC017_PROGRESS_FILE")
    if progress_file:
        with Path(progress_file).open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(rendered + "\n")
            stream.flush()


def _parse_transcript(output: str, label: str) -> dict[str, Any]:
    prefix = TRANSCRIPT_PREFIXES[label]
    matches = re.findall(re.escape(prefix) + r"(\{[^\r\n]*\})", output)
    if len(matches) != 1 or output.count(prefix) != 1:
        raise TracerFailure(f"{label} identity transcript framing is invalid")
    try:
        value = json.loads(matches[0])
    except json.JSONDecodeError as exc:
        raise TracerFailure(f"{label} identity transcript is invalid JSON") from exc
    if not isinstance(value, dict):
        raise TracerFailure(f"{label} identity transcript payload is invalid")
    return value


def build_and_run(repository_root: Path) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    root_repository = Path(__file__).resolve().parents[1]
    environment = HARNESS.sanitized_environment()
    if "PYTHONPATH" in environment:
        raise TracerFailure("sanitized tracer environment retained PYTHONPATH")
    repositories = {
        "quant-research": root_repository,
        **{name: repository_root / name for name in PACKAGE_REPOSITORIES},
    }
    with tempfile.TemporaryDirectory(prefix="spec017-installed-") as temporary:
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
            HARNESS.snapshot_repository(path, snapshot / name, topology[name]["source_files"])
        wheels = HARNESS.build_wheels(snapshot, PACKAGE_REPOSITORIES, dist, environment)
        python = HARNESS.create_installed_environment(
            isolated, wheels, environment, install_pytest=True
        )
        transcript_environment = dict(environment)
        transcript_environment["SPEC017_IDENTITY_TRANSCRIPT"] = "1"
        replays: list[dict[str, dict[str, Any]]] = []
        source_roots = tuple(snapshot / name / "src" for name in PACKAGE_REPOSITORIES)
        apex_test_file = snapshot / "apex-research" / "tests" / "test_quality_diversity_archives.py"
        reporting_test_file = (
            snapshot
            / "strategy-reporting"
            / "tests"
            / "test_quality_diversity_archive_read_model.py"
        )
        for replay_index in range(2):
            selected = APEX_ARCHIVE_TESTS if replay_index == 0 else REPLAY_TESTS
            apex_outputs: dict[str, str] = {}
            for test_name in selected:
                started = time.monotonic()
                _progress(f"replay={replay_index + 1} apex={test_name} start")
                apex_outputs[test_name] = HARNESS.run_installed_pytest(
                    python,
                    (Path(f"{apex_test_file}::{test_name}"),),
                    PACKAGE_REPOSITORIES,
                    source_roots,
                    cwd=isolated,
                    environment=transcript_environment,
                    timeout_seconds=300,
                    pytest_args=("-s",),
                )
                _progress(
                    f"replay={replay_index + 1} apex={test_name} "
                    f"passed_seconds={time.monotonic() - started:.1f}"
                )
            _progress(f"replay={replay_index + 1} reporting=start")
            reporting_output = HARNESS.run_installed_pytest(
                python,
                (reporting_test_file,),
                PACKAGE_REPOSITORIES,
                source_roots,
                cwd=isolated,
                environment=transcript_environment,
                timeout_seconds=900,
                pytest_args=("-s",),
            )
            _progress(f"replay={replay_index + 1} reporting=passed")
            replays.append(
                {
                    "generation": _parse_transcript(apex_outputs[REPLAY_TESTS[0]], "generation"),
                    "evidence": _parse_transcript(apex_outputs[REPLAY_TESTS[1]], "evidence"),
                    "reporting": _parse_transcript(reporting_output, "reporting"),
                }
            )
        if replays[0] != replays[1]:
            raise TracerFailure("SPEC-017 installed identity transcript drifted on replay")
        smoke_output = HARNESS.run_command(
            [
                str(python),
                "-I",
                "-B",
                str(snapshot / "quant-research" / "tools" / "spec017_installed_wheel_tracer.py"),
                "--repository-root",
                str(snapshot),
                "--smoke-root",
                str(isolated / "workspace-smoke"),
            ],
            cwd=isolated,
            environment=environment,
            timeout_seconds=300,
        )
        smoke_result = json.loads(smoke_output)
        if smoke_result.get("ok") is not True:
            raise TracerFailure("SPEC-017 installed import smoke failed")
        final_topology = {
            name: HARNESS.verify_source_topology(path, environment)
            for name, path in repositories.items()
        }
        if final_topology != topology:
            raise TracerFailure("repository topology changed during SPEC-017 tracer")
        if (
            HARNESS.verify_unchanged_sources(
                repository_root, UNCHANGED_SOURCE_BASELINES, environment
            )
            != unchanged
        ):
            raise TracerFailure("unchanged owner source identity changed during tracer")
        transcript = replays[0]
        return {
            **smoke_result,
            "replays": 2,
            "identity_transcript": transcript,
            "identity_transcript_sha256": hashlib.sha256(
                json.dumps(
                    transcript,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
            "wheel_sha256": {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(wheels)
            },
            "unchanged_sources": unchanged,
            "source_topology": topology,
        }


def smoke(smoke_root: Path) -> dict[str, Any]:
    import apex_research
    import quant_runtime
    import strategy_reporting
    import strategy_workspace
    from apex_research import (
        EvidenceArchivePolicy,
        ExplorationArchivePolicy,
        QualityDiversityArchiveService,
    )
    from strategy_reporting import (
        EvidenceArchiveReadModel,
        ExplorationArchiveReadModel,
        QualityDiversityArchiveReadModelBuilder,
    )
    from strategy_workspace import WorkspaceClient

    if "PYTHONPATH" in os.environ:
        raise TracerFailure("installed smoke inherited PYTHONPATH")
    distributions = HARNESS.installed_distribution_manifest(
        (apex_research, quant_runtime, strategy_reporting, strategy_workspace),
        ("apex-research", "quant-runtime", "strategy-reporting", "strategy-workspace"),
    )
    public_types = (
        EvidenceArchivePolicy,
        ExplorationArchivePolicy,
        QualityDiversityArchiveService,
        EvidenceArchiveReadModel,
        ExplorationArchiveReadModel,
        QualityDiversityArchiveReadModelBuilder,
    )
    if any(
        not value.__module__.startswith(("apex_research", "strategy_reporting"))
        for value in public_types
    ):
        raise TracerFailure("SPEC-017 public export resolved outside installed owners")
    workspace = WorkspaceClient(smoke_root)
    workspace.init()
    if workspace.list_records(limit=1) != []:
        raise TracerFailure("installed Workspace smoke root is not isolated")
    return {
        "ok": True,
        "pythonpath": "cleared",
        "distributions": distributions,
        "public_exports": [value.__name__ for value in public_types],
        "workspace_isolated": True,
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
    except (InstalledWheelFailure, ImportError, OSError, TypeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
