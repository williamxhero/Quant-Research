"""Build five-repository SPEC-015 acceptance and run with installed wheels only."""

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
build_wheels = HARNESS.build_wheels
create_installed_environment = HARNESS.create_installed_environment
installed_distribution_manifest = HARNESS.installed_distribution_manifest
run_command = HARNESS.run_command
run_installed_pytest = HARNESS.run_installed_pytest
verify_unchanged_sources = HARNESS.verify_unchanged_sources
verify_source_topology = HARNESS.verify_source_topology
sanitized_environment = HARNESS.sanitized_environment
snapshot_repository = HARNESS.snapshot_repository
source_fingerprint = HARNESS._source_fingerprint

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
            "tests/test_qualification_validation.py",
            "tests/test_qualification_robustness.py",
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
STABLE_BEHAVIORAL_TESTS = (
    (
        "tests/test_qualification_policy.py::"
        "test_owner_publishes_a_frozen_historical_maturity_policy_through_governance"
    ),
    (
        "tests/test_qualification_validation.py::"
        "test_blocked_validation_remains_structurally_distinct"
    ),
    (
        "tests/test_qualification_validation.py::"
        "test_validation_incomparability_remains_structurally_distinct"
    ),
    (
        "tests/test_qualification_robustness.py::"
        "test_complete_multidimensional_evidence_reaches_research_qualified"
    ),
    (
        "tests/test_qualification_history.py::"
        "test_held_evaluations_do_not_consume_the_one_successor_slot"
    ),
)
IDENTITY_TRANSCRIPT_PREFIX = "SPEC015_IDENTITY_TRANSCRIPT="
HEX_ID = re.compile(r"[0-9a-f]{64}\Z")
IDENTITY_TRANSCRIPT_FIELDS = {
    "policy": {
        "campaign_id",
        "policy_id",
        "reservation_id",
        "settlement_id",
    },
    "qualified-chain": {
        "candidate_id",
        "evidence_id",
        "policy_id",
        "decision_ids",
        "decision_reservation_ids",
        "decision_settlement_ids",
        "terminal_state",
    },
    "held-successor-retirement": {
        "candidate_id",
        "policy_id",
        "held_evaluation_id",
        "held_reservation_id",
        "held_settlement_id",
        "revised_held_evaluation_id",
        "revised_held_reservation_id",
        "revised_held_settlement_id",
        "decision_id",
        "decision_reservation_id",
        "decision_settlement_id",
        "retirement_id",
        "retirement_reservation_id",
        "retirement_settlement_id",
        "terminal_state",
    },
}


class TracerFailure(InstalledWheelFailure):
    pass


def _validated_identity_transcript(
    transcript: list[object],
) -> list[dict[str, Any]]:
    if len(transcript) != len(IDENTITY_TRANSCRIPT_FIELDS):
        raise TracerFailure(
            "stable installed identity transcript labels are incomplete or duplicated"
        )
    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in transcript:
        if not isinstance(item, dict) or set(item) != {"label", "identities"}:
            raise TracerFailure(
                "stable installed identity transcript payload is invalid"
            )
        label = item["label"]
        identities = item["identities"]
        if (
            not isinstance(label, str)
            or label in seen
            or label not in IDENTITY_TRANSCRIPT_FIELDS
            or not isinstance(identities, dict)
            or set(identities) != IDENTITY_TRANSCRIPT_FIELDS[label]
        ):
            raise TracerFailure(
                "stable installed identity transcript payload is invalid"
            )
        seen.add(label)
        terminal = identities.get("terminal_state")
        expected_terminal = {
            "qualified-chain": "research_qualified",
            "held-successor-retirement": "retired",
        }.get(label)
        if expected_terminal is not None and terminal != expected_terminal:
            raise TracerFailure(
                "stable installed identity transcript payload is invalid"
            )
        for key, value in identities.items():
            if key == "terminal_state":
                continue
            if key in {
                "decision_ids",
                "decision_reservation_ids",
                "decision_settlement_ids",
            }:
                if (
                    not isinstance(value, list)
                    or len(value) != 5
                    or len(set(value)) != 5
                    or any(
                        not isinstance(member, str) or HEX_ID.fullmatch(member) is None
                        for member in value
                    )
                ):
                    raise TracerFailure(
                        "stable installed identity transcript payload is invalid"
                    )
            elif not isinstance(value, str) or HEX_ID.fullmatch(value) is None:
                raise TracerFailure(
                    "stable installed identity transcript payload is invalid"
                )
        validated.append({"label": label, "identities": identities})
    by_label = {str(item["label"]): item["identities"] for item in validated}
    policy = by_label["policy"]
    qualified = by_label["qualified-chain"]
    held = by_label["held-successor-retirement"]
    if not (
        policy["policy_id"] == qualified["policy_id"] == held["policy_id"]
        and qualified["candidate_id"] == held["candidate_id"]
    ):
        raise TracerFailure(
            "stable installed identity transcript relationships drifted"
        )
    domain_ids = [
        qualified["evidence_id"],
        *qualified["decision_ids"],
        held["held_evaluation_id"],
        held["revised_held_evaluation_id"],
        held["decision_id"],
        held["retirement_id"],
    ]
    governance_ids = [
        policy["reservation_id"],
        policy["settlement_id"],
        *qualified["decision_reservation_ids"],
        *qualified["decision_settlement_ids"],
        held["held_reservation_id"],
        held["held_settlement_id"],
        held["revised_held_reservation_id"],
        held["revised_held_settlement_id"],
        held["decision_reservation_id"],
        held["decision_settlement_id"],
        held["retirement_reservation_id"],
        held["retirement_settlement_id"],
    ]
    if (
        len(domain_ids) != len(set(domain_ids))
        or len(governance_ids) != len(set(governance_ids))
        or set(domain_ids) & set(governance_ids)
    ):
        raise TracerFailure("stable installed identity transcript cardinality drifted")
    return sorted(validated, key=lambda value: str(value["label"]))


def _snapshot_tree_identity(repository: Path) -> dict[str, object]:
    files: list[str] = []
    for path in sorted(repository.rglob("*")):
        if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
            raise TracerFailure(f"attested snapshot contains a link: {path}")
        if path.is_file():
            files.append(path.relative_to(repository).as_posix())
    return {
        "files": files,
        "fingerprint": source_fingerprint(repository, files),
    }


def _assert_snapshot_trees(
    snapshot_root: Path,
    repositories: dict[str, Path],
    expected: dict[str, dict[str, object]],
    *,
    phase: str,
) -> None:
    observed = {
        repository: _snapshot_tree_identity(snapshot_root / repository)
        for repository in repositories
    }
    if observed != expected:
        raise TracerFailure(f"attested build snapshot mutated during {phase}")


def build_and_run(repository_root: Path) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    root_repository = Path(__file__).resolve().parents[1]
    for repository in PACKAGE_REPOSITORIES:
        if not (repository_root / repository / "pyproject.toml").is_file():
            raise TracerFailure(f"repository is unavailable: {repository}")
    with tempfile.TemporaryDirectory(prefix="spec015-installed-") as temporary:
        isolated = Path(temporary).resolve()
        environment = sanitized_environment()
        dist = isolated / "dist"
        dist.mkdir()
        repositories = {
            "quant-research": root_repository,
            **{
                repository: repository_root / repository
                for repository in PACKAGE_REPOSITORIES
            },
        }
        source_topology = {
            repository: verify_source_topology(path, environment)
            for repository, path in repositories.items()
        }
        unchanged_sources = verify_unchanged_sources(
            repository_root,
            UNCHANGED_SOURCE_BASELINES,
            environment,
        )
        snapshot_root = isolated / "source-snapshot"
        snapshot_root.mkdir()
        for repository, path in repositories.items():
            snapshot_repository(
                path,
                snapshot_root / repository,
                source_topology[repository]["source_files"],
            )
        snapshot_fingerprints = {
            repository: source_fingerprint(
                snapshot_root / repository,
                source_topology[repository]["source_files"],
            )
            for repository in repositories
        }
        if snapshot_fingerprints != {
            repository: source_topology[repository]["source_fingerprint"]
            for repository in repositories
        }:
            raise TracerFailure(
                "build snapshot does not match initial source attestation"
            )
        snapshot_trees = {
            repository: _snapshot_tree_identity(snapshot_root / repository)
            for repository in repositories
        }
        wheels = build_wheels(
            snapshot_root,
            PACKAGE_REPOSITORIES,
            dist,
            environment,
        )
        _assert_snapshot_trees(
            snapshot_root, repositories, snapshot_trees, phase="wheel build"
        )
        source_topology_after_build = {
            repository: verify_source_topology(path, environment)
            for repository, path in repositories.items()
        }
        if source_topology_after_build != source_topology:
            raise TracerFailure("repository source topology raced during wheel build")
        unchanged_after_build = verify_unchanged_sources(
            repository_root,
            UNCHANGED_SOURCE_BASELINES,
            environment,
        )
        if unchanged_after_build != unchanged_sources:
            raise TracerFailure(
                "unchanged repository source identity raced during wheel build"
            )
        python = create_installed_environment(
            isolated,
            wheels,
            environment,
            install_pytest=True,
        )
        for repository, targets in INSTALLED_TESTS:
            run_installed_pytest(
                python,
                (snapshot_root / repository / target for target in targets),
                (
                    "apex_research",
                    "quant_runtime",
                    "strategy_reporting",
                    "strategy_workspace",
                ),
                (snapshot_root / name / "src" for name in PACKAGE_REPOSITORIES),
                cwd=isolated,
                environment=environment,
                timeout_seconds=900,
            )
            _assert_snapshot_trees(
                snapshot_root, repositories, snapshot_trees, phase="installed tests"
            )
        stable_identity_transcripts: list[list[dict[str, Any]]] = []
        transcript_environment = dict(environment)
        transcript_environment["SPEC015_IDENTITY_TRANSCRIPT"] = "1"
        for _ in range(2):
            stable_output = run_installed_pytest(
                python,
                (
                    snapshot_root / "apex-research" / target
                    for target in STABLE_BEHAVIORAL_TESTS
                ),
                (
                    "apex_research",
                    "quant_runtime",
                    "strategy_reporting",
                    "strategy_workspace",
                ),
                (snapshot_root / name / "src" for name in PACKAGE_REPOSITORIES),
                cwd=isolated,
                environment=transcript_environment,
                timeout_seconds=1_200,
                pytest_args=("-s",),
            )
            encoded_transcript = re.findall(
                r"(?m)^" + re.escape(IDENTITY_TRANSCRIPT_PREFIX) + r"(\{[^\r\n]*\})$",
                stable_output,
            )
            if stable_output.count(IDENTITY_TRANSCRIPT_PREFIX) != len(
                encoded_transcript
            ):
                raise TracerFailure(
                    "stable installed identity transcript framing is invalid"
                )
            try:
                transcript = [json.loads(value) for value in encoded_transcript]
            except json.JSONDecodeError as exc:
                raise TracerFailure(
                    "stable installed identity transcript JSON is invalid"
                ) from exc
            stable_identity_transcripts.append(
                _validated_identity_transcript(transcript)
            )
            _assert_snapshot_trees(
                snapshot_root,
                repositories,
                snapshot_trees,
                phase="stable behavioral tests",
            )
        if not stable_identity_transcripts[0]:
            raise TracerFailure("stable installed tests emitted no identity transcript")
        if stable_identity_transcripts[0] != stable_identity_transcripts[1]:
            raise TracerFailure("stable installed identity transcripts drifted")
        output = run_command(
            [
                str(python),
                "-I",
                str(
                    snapshot_root
                    / "quant-research"
                    / "tools"
                    / "spec015_installed_wheel_tracer.py"
                ),
                "--repository-root",
                str(snapshot_root),
                "--smoke-root",
                str(isolated / "workspace-import-smoke"),
            ],
            cwd=isolated,
            environment=environment,
            timeout_seconds=300,
        )
        try:
            result = json.loads(output)
        except json.JSONDecodeError as exc:
            raise TracerFailure(
                f"installed tracer emitted invalid JSON: {output}"
            ) from exc
        if result.get("ok") is not True:
            raise TracerFailure(f"installed tracer failed: {result}")
        _assert_snapshot_trees(
            snapshot_root, repositories, snapshot_trees, phase="installed smoke"
        )
        final_source_topology = {
            repository: verify_source_topology(path, environment)
            for repository, path in repositories.items()
        }
        if final_source_topology != source_topology:
            raise TracerFailure(
                "repository source topology raced during installed execution"
            )
        final_unchanged_sources = verify_unchanged_sources(
            repository_root,
            UNCHANGED_SOURCE_BASELINES,
            environment,
        )
        if final_unchanged_sources != unchanged_sources:
            raise TracerFailure(
                "unchanged repository source identity raced during installed execution"
            )
        result["repositories"] = list(repositories)
        result["installed_tests"] = [
            f"{repository}/{target}"
            for repository, targets in INSTALLED_TESTS
            for target in targets
        ]
        result["stable_behavioral_runs"] = 2
        result["stable_behavioral_tests"] = list(STABLE_BEHAVIORAL_TESTS)
        result["stable_identity_transcript"] = stable_identity_transcripts[0]
        result["stable_identity_transcript_sha256"] = hashlib.sha256(
            json.dumps(
                stable_identity_transcripts[0],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        result["wheel_sha256"] = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(wheels)
        }
        result["unchanged_sources"] = unchanged_sources
        result["source_topology"] = source_topology
        return result


def smoke(repository_root: Path, smoke_root: Path) -> dict[str, Any]:
    import apex_research
    import quant_runtime
    import strategy_reporting
    import strategy_workspace
    from apex_research import (
        QualificationEvaluationRequest,
        QualificationEvaluator,
        QualificationHistoryReader,
        QualificationPolicy,
        QualificationRetirementRequest,
        QualificationService,
        QualificationValidationMetricRequirement,
    )
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
        QualificationEvaluator,
        QualificationRetirementRequest,
        QualificationHistoryReader,
        QualificationService,
        QualificationValidationMetricRequirement,
    )
    if any(
        not value.__module__.startswith("apex_research.qualification")
        for value in public_types
    ):
        raise TracerFailure(
            "qualification public exports do not resolve to the installed owner"
        )
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
    except (InstalledWheelFailure, ImportError, OSError, TypeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
