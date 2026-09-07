"""Build and replay the nodeized five-seam SPEC-018 evolution tracer from wheels only."""

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
}
NODE_TIMEOUT_SECONDS = 180
APEX_NODES = (
    "test_seeded_island_is_immutable_deterministic_and_workspace_roundtrippable",
    "test_variation_plan_freezes_owner_inputs_and_is_arrival_order_independent",
    "test_engine_and_static_gate_facts_must_match_the_published_intent",
    "test_bounded_promotion_frontier_preserves_the_whole_discovery_population",
    "test_only_promoted_candidates_may_attach_comparable_nautilus_evidence",
    "test_migration_stop_and_recovery_are_append_only_and_exactly_once",
    "test_evolution_identity_transcript_is_deterministic",
)
REPORTING_NODES = (
    "test_evolution_progress_is_complete_honest_and_deterministic",
    "test_evolution_cli_emits_one_deterministic_workspace_only_model",
    "test_evolution_reporting_identity_transcript_is_deterministic",
)
TRANSCRIPT_NODES = {
    "apex": APEX_NODES[-1],
    "reporting": REPORTING_NODES[-1],
}
TRANSCRIPT_PREFIXES = {
    "apex": "SPEC018_APEX_TRANSCRIPT=",
    "reporting": "SPEC018_REPORTING_TRANSCRIPT=",
}


class TracerFailure(InstalledWheelFailure):
    pass


def _progress(message: str) -> None:
    rendered = f"SPEC018_PROGRESS {message}"
    print(rendered, file=sys.stderr, flush=True)
    progress_file = os.environ.get("SPEC018_PROGRESS_FILE")
    if progress_file:
        with Path(progress_file).open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(rendered + "\n")
            stream.flush()


def _parse_transcript(output: str, label: str) -> dict[str, Any]:
    prefix = TRANSCRIPT_PREFIXES[label]
    matches = re.findall(re.escape(prefix) + r"(\{[^\r\n]*\})", output)
    if len(matches) != 1 or output.count(prefix) != 1:
        raise TracerFailure(f"{label} identity transcript framing is invalid")
    value = json.loads(matches[0])
    if not isinstance(value, dict):
        raise TracerFailure(f"{label} identity transcript payload is invalid")
    return value


def _run_node(
    *,
    python: Path,
    node: str,
    test_file: Path,
    source_roots: tuple[Path, ...],
    cwd: Path,
    environment: dict[str, str],
    replay: int,
) -> str:
    started = time.monotonic()
    _progress(
        f"replay={replay} node={node} start timeout_seconds={NODE_TIMEOUT_SECONDS}"
    )
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
    _progress(
        f"replay={replay} node={node} passed_seconds={time.monotonic() - started:.1f}"
    )
    return output


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
    with tempfile.TemporaryDirectory(prefix="spec018-installed-") as temporary:
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
        transcript_environment = dict(environment)
        transcript_environment["SPEC018_IDENTITY_TRANSCRIPT"] = "1"
        source_roots = tuple(snapshot / name / "src" for name in PACKAGE_REPOSITORIES)
        apex_file = snapshot / "apex-research/tests/test_evolution_research.py"
        reporting_file = (
            snapshot / "strategy-reporting/tests/test_evolution_read_model.py"
        )
        root_file = (
            snapshot / "quant-research/tools/test_validate_architecture_constitution.py"
        )
        root_node = (
            "ConstitutionValidationTests::"
            "test_spec_018_evolution_research_admission_is_valid"
        )
        transcripts: list[dict[str, dict[str, Any]]] = []
        for replay in (1, 2):
            outputs: dict[str, str] = {}
            if replay == 1:
                _run_node(
                    python=python,
                    node=root_node,
                    test_file=root_file,
                    source_roots=source_roots,
                    cwd=isolated,
                    environment=transcript_environment,
                    replay=replay,
                )
                apex_nodes = APEX_NODES
                reporting_nodes = REPORTING_NODES
            else:
                apex_nodes = (TRANSCRIPT_NODES["apex"],)
                reporting_nodes = (TRANSCRIPT_NODES["reporting"],)
            for node in apex_nodes:
                outputs[f"apex:{node}"] = _run_node(
                    python=python,
                    node=node,
                    test_file=apex_file,
                    source_roots=source_roots,
                    cwd=isolated,
                    environment=transcript_environment,
                    replay=replay,
                )
            for node in reporting_nodes:
                outputs[f"reporting:{node}"] = _run_node(
                    python=python,
                    node=node,
                    test_file=reporting_file,
                    source_roots=source_roots,
                    cwd=isolated,
                    environment=transcript_environment,
                    replay=replay,
                )
            transcripts.append(
                {
                    label: _parse_transcript(
                        outputs[f"{label}:{TRANSCRIPT_NODES[label]}"], label
                    )
                    for label in ("apex", "reporting")
                }
            )
        if transcripts[0] != transcripts[1]:
            raise TracerFailure(
                "SPEC-018 installed identity transcript drifted on replay"
            )
        smoke_output = HARNESS.run_command(
            [
                str(python),
                "-I",
                "-B",
                str(
                    snapshot / "quant-research/tools/spec018_installed_wheel_tracer.py"
                ),
                "--repository-root",
                str(snapshot),
                "--smoke-root",
                str(isolated / "workspace-smoke"),
            ],
            cwd=isolated,
            environment=environment,
            timeout_seconds=NODE_TIMEOUT_SECONDS,
        )
        smoke_result = json.loads(smoke_output)
        if smoke_result.get("ok") is not True:
            raise TracerFailure("SPEC-018 installed import smoke failed")
        final_topology = {
            name: HARNESS.verify_source_topology(path, environment)
            for name, path in repositories.items()
        }
        if final_topology != topology:
            raise TracerFailure("repository topology changed during SPEC-018 tracer")
        if (
            HARNESS.verify_unchanged_sources(
                repository_root, UNCHANGED_SOURCE_BASELINES, environment
            )
            != unchanged
        ):
            raise TracerFailure("unchanged owner source identity changed during tracer")
        transcript = transcripts[0]
        return {
            **smoke_result,
            "nodes": 1 + len(APEX_NODES) + len(REPORTING_NODES),
            "node_timeout_seconds": NODE_TIMEOUT_SECONDS,
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
        EvolutionPolicy,
        EvolutionPromotionFrontier,
        EvolutionResearchService,
    )
    from strategy_reporting import (
        EvolutionIslandRef,
        EvolutionProgressReadModel,
        EvolutionProgressReadModelBuilder,
    )
    from strategy_workspace import WorkspaceClient

    if "PYTHONPATH" in os.environ:
        raise TracerFailure("installed smoke inherited PYTHONPATH")
    distributions = HARNESS.installed_distribution_manifest(
        (apex_research, quant_runtime, strategy_reporting, strategy_workspace),
        ("apex-research", "quant-runtime", "strategy-reporting", "strategy-workspace"),
    )
    public_types = (
        EvolutionPolicy,
        EvolutionPromotionFrontier,
        EvolutionResearchService,
        EvolutionIslandRef,
        EvolutionProgressReadModel,
        EvolutionProgressReadModelBuilder,
    )
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
