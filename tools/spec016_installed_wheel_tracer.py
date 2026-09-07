"""Build and replay the five-seam SPEC-016 tracer from installed wheels only."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
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
TRANSCRIPT_PREFIX = "SPEC016_IDENTITY_TRANSCRIPT="


class TracerFailure(InstalledWheelFailure):
    pass


def _parse_transcript(output: str, label: str) -> dict[str, Any]:
    matches = re.findall(
        r"(?m)^" + re.escape(TRANSCRIPT_PREFIX) + r"(\{[^\r\n]*\})$", output
    )
    if len(matches) != 1 or output.count(TRANSCRIPT_PREFIX) != 1:
        raise TracerFailure(f"{label} identity transcript framing is invalid")
    try:
        value = json.loads(matches[0])
    except json.JSONDecodeError as exc:
        raise TracerFailure(f"{label} identity transcript is invalid JSON") from exc
    if not isinstance(value, dict) or value.get("label") != label:
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
    with tempfile.TemporaryDirectory(prefix="spec016-installed-") as temporary:
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
                path,
                snapshot / name,
                topology[name]["source_files"],
            )
        wheels = HARNESS.build_wheels(snapshot, PACKAGE_REPOSITORIES, dist, environment)
        python = HARNESS.create_installed_environment(
            isolated, wheels, environment, install_pytest=True
        )
        transcript_environment = dict(environment)
        transcript_environment["SPEC016_IDENTITY_TRANSCRIPT"] = "1"
        replays: list[list[dict[str, Any]]] = []
        for _ in range(2):
            apex_output = HARNESS.run_installed_pytest(
                python,
                (
                    snapshot
                    / "apex-research"
                    / "tests"
                    / "test_behavior_descriptors.py::test_public_exports_and_strict_cli_cover_taxonomy_and_both_descriptor_tiers",
                    snapshot
                    / "apex-research"
                    / "tests"
                    / "test_behavior_descriptors.py::test_formal_assignment_rejects_unit_mismatch_and_non_pit_regime",
                ),
                PACKAGE_REPOSITORIES,
                tuple(snapshot / name / "src" for name in PACKAGE_REPOSITORIES),
                cwd=isolated,
                environment=transcript_environment,
                timeout_seconds=1_800,
                pytest_args=("-s",),
            )
            reporting_output = HARNESS.run_installed_pytest(
                python,
                (
                    snapshot
                    / "strategy-reporting"
                    / "tests"
                    / "test_behavior_descriptor_read_model.py::test_behavior_cli_emits_one_distinct_json_read_model",
                ),
                PACKAGE_REPOSITORIES,
                tuple(snapshot / name / "src" for name in PACKAGE_REPOSITORIES),
                cwd=isolated,
                environment=transcript_environment,
                timeout_seconds=900,
                pytest_args=("-s",),
            )
            replays.append(
                [
                    _parse_transcript(apex_output, "apex"),
                    _parse_transcript(reporting_output, "reporting"),
                ]
            )
        if replays[0] != replays[1]:
            raise TracerFailure(
                "SPEC-016 installed identity transcript drifted on replay"
            )
        smoke_output = HARNESS.run_command(
            [
                str(python),
                "-I",
                "-B",
                str(
                    snapshot
                    / "quant-research"
                    / "tools"
                    / "spec016_installed_wheel_tracer.py"
                ),
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
            raise TracerFailure("SPEC-016 installed import smoke failed")
        final_topology = {
            name: HARNESS.verify_source_topology(path, environment)
            for name, path in repositories.items()
        }
        if final_topology != topology:
            raise TracerFailure("repository topology changed during SPEC-016 tracer")
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
        BehaviorDescriptorService,
        BehaviorTaxonomy,
        DiscoveryBehaviorDescriptor,
        FormalBehaviorDescriptor,
    )
    from strategy_reporting import (
        BehaviorDescriptorReadModel,
        BehaviorDescriptorReadModelBuilder,
    )
    from strategy_workspace import WorkspaceClient

    if "PYTHONPATH" in os.environ:
        raise TracerFailure("installed smoke inherited PYTHONPATH")
    distributions = HARNESS.installed_distribution_manifest(
        (apex_research, quant_runtime, strategy_reporting, strategy_workspace),
        ("apex-research", "quant-runtime", "strategy-reporting", "strategy-workspace"),
    )
    public_types = (
        BehaviorDescriptorService,
        BehaviorTaxonomy,
        DiscoveryBehaviorDescriptor,
        FormalBehaviorDescriptor,
        BehaviorDescriptorReadModel,
        BehaviorDescriptorReadModelBuilder,
    )
    if any(
        not value.__module__.startswith(("apex_research", "strategy_reporting"))
        for value in public_types
    ):
        raise TracerFailure("SPEC-016 public export resolved outside installed owners")
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
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
