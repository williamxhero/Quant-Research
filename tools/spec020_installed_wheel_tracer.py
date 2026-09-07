"""Build and replay the nodeized SPEC-020 QRAFTI tracer from wheels only."""

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
HARNESS_SPEC = importlib.util.spec_from_file_location(
    "installed_wheel_harness", HARNESS_PATH
)
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
QRAFTI_NODES = (
    "test_qrafti_official_source_is_exact_and_disabled_by_default",
    "test_qrafti_contract_is_exported_from_the_installed_package_surface",
    "test_qrafti_source_contract_is_strict_and_identity_checked",
    "test_qrafti_mcp_snapshot_freezes_catalog_and_invocation_allowlist",
    "test_qrafti_policy_binds_exact_observed_mcp_and_runtime_identity",
    "test_qrafti_capability_discovery_is_a_separately_governed_runner_call",
    "test_qrafti_mapping_matrix_closes_all_task_families_without_guessing",
    "test_qrafti_result_keeps_valid_siblings_and_rejects_unsafe_output",
    "test_qrafti_replication_uses_distinct_grant_and_replays_without_execute",
)
IMPACTED_NODES = (
    (
        "test_empirical_research.py",
        "test_result_publication_crash_recovers_canonical_outcome_without_second_execution",
    ),
    (
        "test_external_runner_recovery.py",
        "test_success_publication_crash_recovers_retained_output_without_rerun",
    ),
)
TRANSCRIPT_NODE = (
    "test_qrafti_replication_uses_distinct_grant_and_replays_without_execute"
)
TRANSCRIPT_PREFIX = "SPEC020_APEX_TRANSCRIPT="


class TracerFailure(InstalledWheelFailure):
    pass


def _progress(message: str) -> None:
    rendered = f"SPEC020_PROGRESS {message}"
    print(rendered, file=sys.stderr, flush=True)
    progress_file = os.environ.get("SPEC020_PROGRESS_FILE")
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
    _progress(f"replay={replay} node={node} start timeout={NODE_TIMEOUT_SECONDS}")
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
    _progress(f"replay={replay} node={node} passed={time.monotonic() - started:.1f}s")
    return output


def _transcript(output: str) -> dict[str, Any]:
    matches = re.findall(re.escape(TRANSCRIPT_PREFIX) + r"(\{[^\r\n]*\})", output)
    if len(matches) != 1 or output.count(TRANSCRIPT_PREFIX) != 1:
        raise TracerFailure("QRAFTI identity transcript framing is invalid")
    value = json.loads(matches[0])
    if not isinstance(value, dict):
        raise TracerFailure("QRAFTI identity transcript payload is invalid")
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
    with tempfile.TemporaryDirectory(prefix="spec020-installed-") as temporary:
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
        wheels = HARNESS.build_wheels(snapshot, PACKAGE_REPOSITORIES, dist, environment)
        python = HARNESS.create_installed_environment(
            isolated, wheels, environment, install_pytest=True
        )
        test_environment = dict(environment)
        test_environment["SPEC020_IDENTITY_TRANSCRIPT"] = "1"
        source_roots = tuple(snapshot / name / "src" for name in PACKAGE_REPOSITORIES)
        qrafti_test = snapshot / "apex-research/tests/test_qrafti_adapter.py"
        transcripts: list[dict[str, Any]] = []
        for replay in (1, 2):
            nodes = QRAFTI_NODES if replay == 1 else (TRANSCRIPT_NODE,)
            output = ""
            for node in nodes:
                current = _run_node(
                    python=python,
                    test_file=qrafti_test,
                    node=node,
                    source_roots=source_roots,
                    cwd=isolated,
                    environment=test_environment,
                    replay=replay,
                )
                if node == TRANSCRIPT_NODE:
                    output = current
            transcripts.append(_transcript(output))
        for filename, node in IMPACTED_NODES:
            _run_node(
                python=python,
                test_file=snapshot / f"apex-research/tests/{filename}",
                node=node,
                source_roots=source_roots,
                cwd=isolated,
                environment=test_environment,
                replay=1,
            )
        if transcripts[0] != transcripts[1]:
            raise TracerFailure(
                "SPEC-020 installed identity transcript drifted on replay"
            )
        smoke_output = HARNESS.run_command(
            [
                str(python),
                "-I",
                "-B",
                str(
                    snapshot / "quant-research/tools/spec020_installed_wheel_tracer.py"
                ),
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
            "nodes": len(QRAFTI_NODES) + len(IMPACTED_NODES),
            "node_timeout_seconds": NODE_TIMEOUT_SECONDS,
            "replays": 2,
            "identity_transcript": transcripts[0],
            "identity_transcript_sha256": hashlib.sha256(
                json.dumps(
                    transcripts[0], sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest(),
            "wheel_sha256": {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(wheels)
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
        QraftiAdapterConfig,
        QraftiMappingMatrix,
        QraftiMcpCapabilitySnapshot,
        create_qrafti_empirical_port,
        production_qrafti_config,
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
    production = production_qrafti_config()
    if production.enabled or production != QraftiAdapterConfig.disabled():
        raise TracerFailure("unattested QRAFTI production configuration was enabled")
    public_types = (
        QraftiAdapterConfig,
        QraftiMappingMatrix,
        QraftiMcpCapabilitySnapshot,
        create_qrafti_empirical_port,
    )
    manifest = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "docs/architecture-admissions/spec-020.worker-manifest.v1.json"
        ).read_text(encoding="utf-8")
    )
    if (
        manifest.get("production_ready") is not False
        or manifest.get("status") != "blocked"
    ):
        raise TracerFailure("QRAFTI worker manifest must remain fail-closed")
    return {
        "ok": True,
        "pythonpath": "cleared",
        "distributions": distributions,
        "public_exports": [value.__name__ for value in public_types],
        "production_status": "disabled",
        "connected_oci": manifest["connected_test"],
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
