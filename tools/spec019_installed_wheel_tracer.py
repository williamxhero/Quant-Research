"""Build and replay the nodeized SPEC-019 empirical tracer from wheels only."""

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
    "strategy-reporting": "c601c5c03ed012fbba616713155fa80e527ba0d6",
}
NODE_TIMEOUT_SECONDS = 180
APEX_NODES = (
    "test_empirical_contract_is_exported_from_the_installed_package_surface",
    "test_capability_policy_is_frozen_published_and_read_back_before_use",
    "test_capability_policy_rejects_unbounded_unknown_and_external_bypass",
    "test_panel_analysis_runs_once_through_canonical_governance_and_publication",
    "test_result_publication_crash_recovers_canonical_outcome_without_second_execution",
    "test_denied_panel_request_has_zero_port_call_and_zero_empirical_result",
    "test_closed_task_family_is_deterministic_and_typed",
    "test_task_contract_rejects_implicit_semantics_and_nonfinite_inputs",
    "test_reference_factor_lag_is_applied_by_entity_and_time",
    "test_structured_output_is_workspace_owned_verified_and_bounded",
    "test_outcome_bounds_partial_items_and_namespace_isolation",
    "test_external_discovery_and_execution_only_cross_the_governed_runner",
)
TRANSCRIPT_NODE = "test_panel_analysis_runs_once_through_canonical_governance_and_publication"
TRANSCRIPT_PREFIX = "SPEC019_APEX_TRANSCRIPT="


class TracerFailure(InstalledWheelFailure):
    pass


def _progress(message: str) -> None:
    rendered = f"SPEC019_PROGRESS {message}"
    print(rendered, file=sys.stderr, flush=True)
    progress_file = os.environ.get("SPEC019_PROGRESS_FILE")
    if progress_file:
        with Path(progress_file).open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(rendered + "\n")
            stream.flush()


def _run_node(
    *,
    python: Path,
    test_file: Path,
    node: str,
    source_roots: tuple[Path, ...],
    cwd: Path,
    environment: dict[str, str],
    replay: int,
) -> str:
    started = time.monotonic()
    _progress(f"replay={replay} node={node} start timeout_seconds={NODE_TIMEOUT_SECONDS}")
    output = HARNESS.run_installed_pytest(
        python,
        (Path(f"{test_file}::{node}"),),
        PACKAGE_REPOSITORIES,
        source_roots,
        cwd=cwd,
        environment=environment,
        timeout_seconds=NODE_TIMEOUT_SECONDS,
        pytest_args=("-s",),
    )
    _progress(f"replay={replay} node={node} passed_seconds={time.monotonic() - started:.1f}")
    return output


def _transcript(output: str) -> dict[str, Any]:
    matches = re.findall(re.escape(TRANSCRIPT_PREFIX) + r"(\{[^\r\n]*\})", output)
    if len(matches) != 1 or output.count(TRANSCRIPT_PREFIX) != 1:
        raise TracerFailure("empirical identity transcript framing is invalid")
    value = json.loads(matches[0])
    if not isinstance(value, dict):
        raise TracerFailure("empirical identity transcript payload is invalid")
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
    with tempfile.TemporaryDirectory(prefix="spec019-installed-") as temporary:
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
        test_environment = dict(environment)
        test_environment["SPEC019_IDENTITY_TRANSCRIPT"] = "1"
        source_roots = tuple(snapshot / name / "src" for name in PACKAGE_REPOSITORIES)
        test_file = snapshot / "apex-research/tests/test_empirical_research.py"
        transcripts: list[dict[str, Any]] = []
        for replay in (1, 2):
            nodes = APEX_NODES if replay == 1 else (TRANSCRIPT_NODE,)
            output = ""
            for node in nodes:
                current = _run_node(
                    python=python,
                    test_file=test_file,
                    node=node,
                    source_roots=source_roots,
                    cwd=isolated,
                    environment=test_environment,
                    replay=replay,
                )
                if node == TRANSCRIPT_NODE:
                    output = current
            transcripts.append(_transcript(output))
        if transcripts[0] != transcripts[1]:
            raise TracerFailure("SPEC-019 installed identity transcript drifted on replay")
        smoke_output = HARNESS.run_command(
            [
                str(python),
                "-I",
                "-B",
                str(snapshot / "quant-research/tools/spec019_installed_wheel_tracer.py"),
                "--repository-root",
                str(snapshot),
                "--smoke-root",
                str(isolated / "smoke-workspace"),
            ],
            cwd=isolated,
            environment=environment,
            timeout_seconds=NODE_TIMEOUT_SECONDS,
        )
        smoke = json.loads(smoke_output)
        return {
            **smoke,
            "nodes": len(APEX_NODES),
            "node_timeout_seconds": NODE_TIMEOUT_SECONDS,
            "replays": 2,
            "identity_transcript": transcripts[0],
            "identity_transcript_sha256": hashlib.sha256(
                json.dumps(transcripts[0], sort_keys=True, separators=(",", ":")).encode()
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
        EmpiricalResearchApplication,
        EmpiricalResearchPort,
        InMemoryEmpiricalResearchPort,
        RunnerBackedEmpiricalResearchPort,
    )
    from strategy_workspace import WorkspaceClient

    if "PYTHONPATH" in os.environ:
        raise TracerFailure("installed smoke inherited PYTHONPATH")
    distributions = HARNESS.installed_distribution_manifest(
        (apex_research, quant_runtime, strategy_reporting, strategy_workspace),
        ("apex-research", "quant-runtime", "strategy-reporting", "strategy-workspace"),
    )
    workspace = WorkspaceClient(smoke_root)
    workspace.init()
    if workspace.list_records(limit=1) != []:
        raise TracerFailure("installed Workspace smoke root is not isolated")
    public_types = (
        EmpiricalResearchApplication,
        EmpiricalResearchPort,
        InMemoryEmpiricalResearchPort,
        RunnerBackedEmpiricalResearchPort,
    )
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
