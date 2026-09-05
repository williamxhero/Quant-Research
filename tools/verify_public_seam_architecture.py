"""Verify the QuantResearch architecture through existing public module seams."""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).parents[1]
HARNESS_PATH = ROOT / "tools" / "installed_wheel_harness.py"
HARNESS_SPEC = importlib.util.spec_from_file_location(
    "installed_wheel_harness", HARNESS_PATH
)
assert HARNESS_SPEC is not None and HARNESS_SPEC.loader is not None
HARNESS = importlib.util.module_from_spec(HARNESS_SPEC)
HARNESS_SPEC.loader.exec_module(HARNESS)

UNCHANGED_REPOSITORY_BASELINES = {
    "strategy-workspace": "1e9c58251efcf48dd8e4d8bc66007dbe105affba",
    "quant-runtime": "c97428c51e8f7265b006872c15999800e5ae1fc9",
    "strategy-reporting": "255442a9291ca49a67e05afa0123e10e07aeb754",
}


class ArchitectureViolation(ValueError):
    """A source tree violates the QuantResearch architecture constitution."""


class FixtureCheck(NamedTuple):
    owner: str
    repository: str
    command: tuple[str, ...]


class GateCheck(NamedTuple):
    owner: str
    repository: str
    category: str
    command: tuple[str, ...]
    connected: bool = False
    baseline_only: bool = False


class ApexSeamPolicy(NamedTuple):
    component: str
    forbidden_imports: tuple[tuple[str, str], ...]
    forbidden_calls: tuple[tuple[str, str], ...]
    forbidden_attributes: tuple[tuple[str, str], ...]
    required_classes: tuple[str, ...]
    required_names: tuple[str, ...]
    required_calls: tuple[str, ...]


def fixture_plan(repository_root: Path) -> tuple[FixtureCheck, ...]:
    """Return public-seam fixture tests without creating shared state or evidence."""
    repository_root = repository_root.resolve()
    return (
        FixtureCheck(
            "strategy_workspace",
            "strategy-workspace",
            (
                "uv",
                "run",
                "--extra",
                "dev",
                "pytest",
                "tests/test_lifecycle.py::test_completed_lifecycle_is_monotonic_and_result_is_public",
                "tests/test_schemas_and_package.py::test_preflight_request_requires_verified_data_semantics",
                "tests/test_lineage_query.py::test_reusable_snapshot_freezes_cross_root_queries_and_allows_empty_typed_root",
                "tests/test_lineage_query.py::test_snapshot_token_tamper_store_and_cursor_mismatch_fail_closed",
                "tests/test_lineage_query.py::test_root_published_after_reused_snapshot_is_not_treated_as_empty",
                "tests/test_lineage_query.py::test_snapshot_contract_and_future_high_water_fail_closed",
            ),
        ),
        FixtureCheck(
            "quant_runtime",
            "quant-runtime",
            (
                "uv",
                "run",
                "--extra",
                "dev",
                "pytest",
                "tests/test_nautilus_native.py::test_nautilus_preserves_native_evidence_and_observed_bar_decisions",
                "tests/test_preflight.py",
                "tests/test_preflight_run_order.py",
                "tests/test_cli_and_distribution.py",
            ),
        ),
        FixtureCheck(
            "apex_research",
            "apex-research",
            (
                "uv",
                "run",
                "--group",
                "dev",
                "pytest",
                "tests/test_report_source.py::test_source_round_trips_as_real_workspace_publication_envelope",
                "tests/test_candidate_closure.py::test_semantic_deduplication_preserves_each_publication_lineage",
                "tests/test_governance_seams.py",
                "tests/test_external_runner_governance.py",
                "tests/test_external_runner_recovery.py",
                "tests/test_research_engine_port.py",
                "tests/test_research_engine_runner.py",
                "tests/test_research_engine_orchestration.py",
                "tests/test_research_engine_contract_matrix.py",
                "tests/test_focused_loop_e2e.py",
                "tests/test_focused_stop_resume.py",
                "tests/test_memory_policy.py",
                "tests/test_memory_records.py",
                "tests/test_memory_query.py",
                "tests/test_memory_orchestration.py",
                "tests/test_validation_protocol.py",
                "tests/test_validation_eligibility.py",
                "tests/test_validation_execution.py",
                "tests/test_validation_staging.py",
                "tests/test_validation_evidence.py",
                "tests/test_validation_reporting.py",
                "tests/test_statistical_control.py",
                "tests/test_evidence_v2.py",
                "tests/test_qualification_policy.py",
                "tests/test_qualification_evaluation.py",
                "tests/test_qualification_validation.py",
                "tests/test_qualification_robustness.py",
                "tests/test_qualification_history.py",
                "tests/test_qualification_cli.py",
            ),
        ),
        FixtureCheck(
            "strategy_reporting",
            "strategy-reporting",
            (
                "uv",
                "run",
                "--extra",
                "dev",
                "pytest",
                "tests/test_workspace_roundtrip.py::test_real_workspace_client_publication_round_trip",
                "tests/test_research_reporting.py::test_validation_evidence_is_exactly_read_back_and_presented_without_recalculation",
                "tests/test_research_reporting.py::test_validation_external_readback_tamper_fails_closed",
                "tests/test_research_reporting.py::test_statistical_assessment_is_read_back_and_displayed_without_recalculation",
                "tests/test_research_reporting.py::test_statistical_external_readback_tamper_fails_closed",
                "tests/test_evidence_v2_read_model.py",
            ),
        ),
        FixtureCheck(
            "spec014_installed_wheels",
            ".",
            (
                "uv",
                "run",
                "--python",
                "3.12",
                "python",
                "tools/spec014_installed_wheel_tracer.py",
                "--repository-root",
                str(repository_root),
            ),
        ),
        FixtureCheck(
            "spec015_installed_wheels",
            ".",
            (
                "uv",
                "run",
                "--python",
                "3.12",
                "python",
                "tools/spec015_installed_wheel_tracer.py",
                "--repository-root",
                str(repository_root),
            ),
        ),
    )


def full_gate_plan(repository_root: Path) -> tuple[GateCheck, ...]:
    """Return the complete non-connected release gate plan for all five seams."""
    repository_root = repository_root.resolve()
    commands: list[GateCheck] = []

    def add(
        owner: str,
        repository: str,
        category: str,
        *command: str,
        baseline_only: bool = False,
    ) -> None:
        commands.append(
            GateCheck(
                owner,
                repository,
                category,
                command,
                baseline_only=baseline_only,
            )
        )

    root_python_files = (
        "tools/installed_wheel_harness.py",
        "tools/spec014_installed_wheel_tracer.py",
        "tools/spec015_installed_wheel_tracer.py",
        "tools/test_installed_wheel_harness.py",
        "tools/test_validate_architecture_constitution.py",
        "tools/test_verify_public_seam_architecture.py",
        "tools/validate_architecture_constitution.py",
        "tools/verify_public_seam_architecture.py",
    )
    add(
        "quant_research", ".", "format", "ruff", "format", "--check", *root_python_files
    )
    add(
        "quant_research",
        ".",
        "lint",
        "ruff",
        "check",
        *root_python_files,
    )
    add(
        "quant_research",
        ".",
        "pytest",
        "uv",
        "run",
        "--python",
        "3.12",
        "--with",
        "pytest",
        "python",
        "-m",
        "pytest",
        "tools/test_installed_wheel_harness.py",
        "tools/test_validate_architecture_constitution.py",
        "tools/test_verify_public_seam_architecture.py",
        "-q",
    )
    add(
        "quant_research",
        ".",
        "diff",
        "git",
        "diff",
        "--check",
        "5a514b6084f55cbf3206acb020acbbdcdbf882a4...HEAD",
    )

    for owner, repository, dev_switch in (
        ("strategy_workspace", "strategy-workspace", ("--extra", "dev")),
        ("quant_runtime", "quant-runtime", ("--extra", "dev")),
        ("apex_research", "apex-research", ("--group", "dev")),
        ("strategy_reporting", "strategy-reporting", ("--extra", "dev")),
    ):
        add(
            owner,
            repository,
            "format",
            "uv",
            "run",
            *dev_switch,
            "ruff",
            "format",
            "--check",
            ".",
            baseline_only=owner
            in {"strategy_workspace", "quant_runtime", "strategy_reporting"},
        )
        add(owner, repository, "lint", "uv", "run", *dev_switch, "ruff", "check", ".")
        if owner in {"apex_research", "strategy_reporting"}:
            add(owner, repository, "typing", "uv", "run", *dev_switch, "mypy")
        marker = {
            "quant_runtime": "not connected and not oci",
            "apex_research": "not oci",
            "strategy_reporting": "not connected",
        }.get(owner)
        pytest = ("uv", "run", *dev_switch, "pytest")
        add(owner, repository, "pytest", *pytest, *(("-m", marker) if marker else ()))
        add(
            owner,
            repository,
            "build",
            "uv",
            "build",
            "--wheel",
            "--out-dir",
            f"{{dist}}/{repository}",
        )
        add(owner, repository, "diff", "git", "diff", "--check")
    add(
        "spec014_installed_wheels",
        ".",
        "installed-wheel-smoke",
        "uv",
        "run",
        "--python",
        "3.12",
        "python",
        "tools/spec014_installed_wheel_tracer.py",
        "--repository-root",
        str(repository_root),
    )
    add(
        "spec015_installed_wheels",
        ".",
        "installed-wheel-smoke",
        "uv",
        "run",
        "--python",
        "3.12",
        "python",
        "tools/spec015_installed_wheel_tracer.py",
        "--repository-root",
        str(repository_root),
    )
    return tuple(commands)


def connected_status_plan() -> tuple[GateCheck, ...]:
    """Return independent connected checks; these are status, never fallback gates."""
    return (
        GateCheck(
            "quant_runtime",
            "quant-runtime",
            "connected-markethub",
            ("uv", "run", "--extra", "dev", "pytest", "-m", "connected", "-ra"),
            connected=True,
        ),
        GateCheck(
            "quant_runtime",
            "quant-runtime",
            "connected-oci",
            ("uv", "run", "--extra", "dev", "pytest", "-m", "oci", "-ra"),
            connected=True,
        ),
        GateCheck(
            "apex_research",
            "apex-research",
            "connected-external-validator",
            ("uv", "run", "--group", "dev", "pytest", "-m", "oci", "-ra"),
            connected=True,
        ),
        GateCheck(
            "strategy_reporting",
            "strategy-reporting",
            "connected-reporting",
            ("uv", "run", "--extra", "dev", "pytest", "-m", "connected", "-ra"),
            connected=True,
        ),
    )


SOURCE_RULES = {
    "strategy-workspace": (
        ("quant_runtime", "Workspace must not own Runtime behavior"),
        ("apex_research", "Workspace must not own Apex behavior"),
        ("strategy_reporting", "Workspace must not own Reporting behavior"),
        ("nautilus_trader", "Workspace must not own formal execution"),
        ("from qlib", "Workspace must not own discovery execution"),
        ("factorcandidate", "Workspace must not own Candidate semantics"),
        ("factor-candidate", "Workspace must not own Candidate schemas"),
        ("modelcandidate", "Workspace must not own Candidate semantics"),
        ("model-candidate", "Workspace must not own Candidate schemas"),
        ("strategycandidate", "Workspace must not own Candidate semantics"),
        ("strategy-candidate", "Workspace must not own Candidate schemas"),
        ("campaignpolicy", "Workspace must not interpret Apex budget policy"),
        ("budgetdimension", "Workspace must not interpret Apex budget dimensions"),
        ("researchengineport", "Workspace must not own ResearchEnginePort"),
        ("research-engine-request", "Workspace must not own research-engine contracts"),
        ("research-engine-result", "Workspace must not own research-engine contracts"),
    ),
    "quant-runtime": (
        ("strategy_workspace.storage", "private Workspace access"),
        ("strategy_workspace.core", "private Workspace access"),
        ("sqlite3", "Runtime must not create a parallel control plane"),
        ("apex_research", "Runtime must not own research orchestration"),
        ("strategy_reporting", "Runtime must not own presentation"),
        ("factorcandidate", "Runtime must not own Candidate semantics"),
        ("factor-candidate", "Runtime must not own Candidate schemas"),
        ("modelcandidate", "Runtime must not own Candidate semantics"),
        ("model-candidate", "Runtime must not own Candidate schemas"),
        ("strategycandidate", "Runtime must not own Candidate semantics"),
        ("strategy-candidate", "Runtime must not own Candidate schemas"),
        ("campaignpolicy", "Runtime must not interpret Apex budget policy"),
        ("budgetdimension", "Runtime must not interpret Apex budget dimensions"),
        ("researchengineport", "Runtime must not own ResearchEnginePort"),
        ("research-engine-request", "Runtime must not own research-engine contracts"),
        ("research-engine-result", "Runtime must not own research-engine contracts"),
    ),
    "apex-research": (
        ("strategy_workspace.storage", "private Workspace access"),
        ("strategy_workspace.core", "private Workspace access"),
        ("workspace.sqlite3", "private Workspace access"),
        ("import quant_runtime", "Apex must invoke Runtime only through its CLI seam"),
        ("from quant_runtime", "Apex must invoke Runtime only through its CLI seam"),
        ("shutil.copy", "Apex must not copy Runtime artifacts"),
    ),
    "strategy-reporting": (
        ("strategy_workspace.storage", "private Workspace access"),
        ("strategy_workspace.core", "private Workspace access"),
        ("workspace.sqlite3", "private Workspace access"),
        ("import quant_runtime", "Reporting must not own Runtime execution"),
        ("from quant_runtime", "Reporting must not own Runtime execution"),
        ("import apex_research", "Reporting must consume published Apex evidence"),
        ("from apex_research", "Reporting must consume published Apex evidence"),
        ("subprocess", "Reporting must not invoke upstream tools"),
        ("campaignpolicy", "Reporting must not interpret Apex budget policy"),
        ("budgetdimension", "Reporting must not interpret Apex budget dimensions"),
        ("researchengineport", "Reporting must not own ResearchEnginePort"),
        ("research-engine-request", "Reporting must not own research-engine contracts"),
        ("research-engine-result", "Reporting must not own research-engine contracts"),
    ),
}


def scan_sources(repository_root: Path) -> None:
    """Reject structural ownership and private cross-repository access violations."""
    for repository, rules in SOURCE_RULES.items():
        source_root = repository_root / repository / "src"
        if not source_root.is_dir():
            continue
        for path in _safe_python_sources(source_root):
            source = path.read_text(encoding="utf-8").lower()
            for forbidden, reason in rules:
                if (
                    repository == "apex-research"
                    and forbidden == "shutil.copy"
                    and path.as_posix().endswith("external_runner/recovery.py")
                ):
                    continue
                if forbidden in source:
                    raise ArchitectureViolation(f"{repository}: {reason}: {path}")
    _scan_apex_governance_seams(
        repository_root / "apex-research" / "src" / "apex_research"
    )
    _scan_rdagent_seams(repository_root / "apex-research")
    _scan_focused_loop_seams(repository_root / "apex-research")
    _scan_research_memory_seams(repository_root / "apex-research")
    _scan_validation_matrix_seams(repository_root / "apex-research")
    _scan_statistical_control_seams(repository_root / "apex-research")
    _scan_spec014_evidence_seams(repository_root)
    _scan_spec015_qualification_seam(
        repository_root / "apex-research",
        required=(
            repository_root / "docs" / "architecture-admissions" / "spec-015.v1.json"
        ).is_file(),
    )
    _scan_spec015_non_owner_repositories(repository_root)


def _safe_python_sources(source_root: Path) -> tuple[Path, ...]:
    """Enumerate Python source without ever traversing a link or junction."""
    if source_root.is_symlink() or getattr(source_root, "is_junction", lambda: False)():
        raise ArchitectureViolation(
            f"source root is a symbolic link or junction: {source_root}"
        )
    pending = [source_root]
    sources: list[Path] = []
    while pending:
        directory = pending.pop()
        try:
            entries = tuple(os.scandir(directory))
        except OSError as exc:
            raise ArchitectureViolation(
                f"cannot safely inspect source tree: {directory}"
            ) from exc
        for entry in entries:
            path = Path(entry.path)
            if entry.is_symlink() or getattr(path, "is_junction", lambda: False)():
                raise ArchitectureViolation(
                    f"source contains a symbolic link or junction: {path}"
                )
            if entry.is_dir(follow_symlinks=False):
                pending.append(path)
            elif entry.is_file(follow_symlinks=False) and path.suffix == ".py":
                sources.append(path)
    return tuple(sorted(sources))


def _scan_spec015_qualification_seam(
    repository: Path, *, required: bool = False
) -> None:
    package = repository / "src" / "apex_research"
    qualification = package / "qualification.py"
    if not qualification.is_file():
        if required:
            raise ArchitectureViolation(
                "apex-research: qualification owner seam is missing: "
                + str(qualification)
            )
        return
    all_package_paths = _safe_python_sources(package)
    qualification_package = package / "qualification"
    qualification_package_paths = tuple(
        path for path in all_package_paths if qualification_package in path.parents
    )
    subsystem_paths = tuple(
        sorted(
            {
                *(
                    path
                    for path in all_package_paths
                    if path.parent == package and path.name.startswith("qualification")
                ),
                *qualification_package_paths,
            }
        )
    )
    subsystem_trees = tuple(
        (path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        for path in subsystem_paths
    )
    class_entries = [
        (node.name, node)
        for _, subsystem_tree in subsystem_trees
        for node in subsystem_tree.body
        if isinstance(node, ast.ClassDef)
    ]
    class_names = [name for name, _ in class_entries]
    if len(class_names) != len(set(class_names)):
        raise ArchitectureViolation(
            "apex-research: qualification seam has duplicate module-level public classes"
        )
    classes = dict(class_entries)
    forbidden_owner_markers = (
        "Ledger",
        "Registry",
        "Runner",
        "Backtester",
        "ArtifactStore",
        "EvidenceStore",
        "FormalEngine",
        "CandidateTruth",
    )
    for path in all_package_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and (
                node.name == "CandidateTruth"
                or node.name in classes
                and path not in subsystem_paths
                or node.name
                in {
                    "MaturityService",
                    "QualificationPublisher",
                    "QualificationStateStore",
                    "ResearchQualificationPublisher",
                }
                or (
                    node.name not in classes
                    and "Qualification" in node.name
                    and any(marker in node.name for marker in forbidden_owner_markers)
                )
            ):
                raise ArchitectureViolation(
                    f"apex-research: parallel qualification owner {node.name}: {path}"
                )
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and path not in subsystem_paths
                and node.name in SPEC015_OWNER_METHODS
            ):
                raise ArchitectureViolation(
                    f"apex-research: parallel qualification owner {node.name}: {path}"
                )
    early_service = classes.get("QualificationService")
    if early_service is not None:
        early_methods = {
            node.name: node
            for node in early_service.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for method_name in (
            "publish_policy",
            "publish_decision",
            "publish_held_evaluation",
            "publish_retirement",
        ):
            method = early_methods.get(method_name)
            if method is not None and not any(
                isinstance(node, ast.Return)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute)
                and isinstance(node.value.func.value, ast.Name)
                and node.value.func.value.id == "self"
                and node.value.func.attr == "_execute_publication"
                for node in method.body
            ):
                raise ArchitectureViolation(
                    f"apex-research: {method_name} bypasses governed qualification publication"
                )
    required_classes = {
        "QualificationDecision",
        "QualificationEvaluation",
        "QualificationEvaluator",
        "QualificationHistoryReader",
        "QualificationPolicy",
        "QualificationRetirement",
        "QualificationRetirementRequest",
        "QualificationService",
        "QualificationState",
        "QualificationSuccessorClaim",
    }
    missing = required_classes - set(classes)
    if missing:
        raise ArchitectureViolation(
            "apex-research: qualification seam lacks public classes "
            + ", ".join(sorted(missing))
        )
    required_fields = {
        "QualificationPolicy": {
            "schema_id",
            "policy_id",
            "campaign",
            "strategy_class",
            "revision",
            "transitions",
            "scope",
            "operational_authority",
            "supersedes",
        },
        "QualificationEvaluation": {
            "schema_id",
            "evaluation_id",
            "campaign",
            "candidate",
            "strategy_package",
            "protocol",
            "evidence",
            "policy",
            "predecessor",
            "from_state",
            "to_state",
            "requirements",
            "blockers",
            "disposition",
            "reason",
            "scope",
            "operational_authority",
        },
        "QualificationDecision": {
            "schema_id",
            "decision_id",
            "evaluation",
            "governance",
            "scope",
            "operational_authority",
        },
        "QualificationRetirementRequest": {
            "schema_id",
            "retirement_id",
            "campaign",
            "candidate",
            "policy",
            "evidence",
            "predecessor",
            "reason",
            "scope",
            "operational_authority",
        },
        "QualificationRetirement": {
            "schema_id",
            "retirement_id",
            "request",
            "governance",
        },
        "QualificationSuccessorClaim": {
            "schema_id",
            "claim_id",
            "predecessor",
            "successor",
            "governance_reservation",
        },
    }
    for class_name, expected_fields in required_fields.items():
        declared = {
            node.target.id
            for node in classes[class_name].body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        }
        if declared != expected_fields:
            raise ArchitectureViolation(
                f"apex-research: {class_name} immutable identity fields drifted: "
                + ", ".join(sorted(declared ^ expected_fields))
            )

    service_methods = {
        node.name: node
        for node in classes["QualificationService"].body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for method_name in (
        "publish_policy",
        "publish_decision",
        "publish_held_evaluation",
        "publish_retirement",
    ):
        method = service_methods.get(method_name)
        governed_return = method is not None and any(
            isinstance(node, ast.Return)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and isinstance(node.value.func.value, ast.Name)
            and node.value.func.value.id == "self"
            and node.value.func.attr == "_execute_publication"
            for node in method.body
        )
        if not governed_return:
            raise ArchitectureViolation(
                f"apex-research: {method_name} bypasses governed qualification publication"
            )

    identity_methods = {
        "QualificationPolicy": {
            "create": ({"canonical_sha256"}, "policy_id", "identity")
        },
        "QualificationEvaluation": {
            "create": ({"canonical_sha256"}, "evaluation_id", "identity")
        },
        "QualificationDecision": {
            "target_ref": ({"canonical_sha256"}, "record_id", "identity"),
            "create": ({"target_ref"}, "decision_id", "evaluation"),
        },
        "QualificationRetirementRequest": {
            "create": ({"canonical_sha256"}, "retirement_id", "identity")
        },
        "QualificationSuccessorClaim": {
            "create": ({"_successor_slot_id"}, "claim_id", "predecessor")
        },
    }
    for class_name, method_contracts in identity_methods.items():
        methods_by_name = {
            node.name: node
            for node in classes[class_name].body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        if not set(method_contracts) <= set(methods_by_name):
            raise ArchitectureViolation(
                f"apex-research: {class_name} lacks canonical identity construction"
            )
        for method_name, (
            allowed_calls,
            identity_field,
            identity_input,
        ) in method_contracts.items():
            method = methods_by_name[method_name]

            def canonical_value(
                value: ast.AST,
                permitted_calls: frozenset[str] = frozenset(allowed_calls),
                expected_input: str = identity_input,
            ) -> bool:
                direct = value.value if isinstance(value, ast.Attribute) else value
                return (
                    isinstance(direct, ast.Call)
                    and (
                        direct.func.id
                        if isinstance(direct.func, ast.Name)
                        else direct.func.attr
                        if isinstance(direct.func, ast.Attribute)
                        else ""
                    )
                    in permitted_calls
                    and any(
                        isinstance(argument, ast.Name) and argument.id == expected_input
                        for argument in (
                            *direct.args,
                            *(item.value for item in direct.keywords),
                        )
                    )
                    and (
                        not isinstance(value, ast.Attribute)
                        or value.attr == "record_id"
                    )
                )

            supplies_identity = any(
                isinstance(node, ast.Dict)
                and any(
                    isinstance(key, ast.Constant)
                    and key.value == identity_field
                    and canonical_value(value)
                    for key, value in zip(node.keys, node.values, strict=True)
                    if key is not None
                )
                or isinstance(node, ast.keyword)
                and node.arg == identity_field
                and canonical_value(node.value)
                for node in ast.walk(method)
            )
            if not supplies_identity:
                raise ArchitectureViolation(
                    f"apex-research: {class_name}.{method_name} does not supply its "
                    f"identity field from the canonical constructor"
                )

    forbidden_imports = {
        "sqlite3": "second governance ledger",
        "quant_runtime": "Runtime implementation access",
        "strategy_reporting": "presentation ownership",
        "strategy_workspace.core": "private Workspace access",
        "strategy_workspace.storage": "private Workspace access",
    }
    subsystem_nodes = tuple(
        node
        for _, subsystem_tree in subsystem_trees
        for node in ast.walk(subsystem_tree)
    )
    functions = {
        node.name: node
        for _, subsystem_tree in subsystem_trees
        for node in subsystem_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    names = {
        node.id
        if isinstance(node, ast.Name)
        else node.attr
        if isinstance(node, ast.Attribute)
        else ""
        for node in subsystem_nodes
    }
    for required_name in (
        "ActionReservation",
        "CampaignLedgerReader",
        "QUALIFICATION_PUBLICATION",
        "canonical_sha256",
    ):
        if required_name not in names:
            raise ArchitectureViolation(
                f"apex-research: qualification seam lacks governed identity name {required_name}"
            )
    for subsystem_path, subsystem_tree in subsystem_trees:
        for node in ast.walk(subsystem_tree):
            if isinstance(node, ast.ClassDef) and any(
                marker in node.name for marker in forbidden_owner_markers
            ):
                raise ArchitectureViolation(
                    f"apex-research: parallel qualification owner {node.name}: {subsystem_path}"
                )
            modules = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            for module in modules:
                for prefix, reason in forbidden_imports.items():
                    if module == prefix or module.startswith(prefix + "."):
                        raise ArchitectureViolation(
                            f"apex-research: qualification owns forbidden {reason}: "
                            f"{subsystem_path}"
                        )
            if isinstance(node, ast.Call):
                call = (
                    node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else node.func.id
                    if isinstance(node.func, ast.Name)
                    else ""
                )
                if call in {"list_records", "submit_run"}:
                    raise ArchitectureViolation(
                        f"apex-research: qualification uses forbidden call {call}: "
                        f"{subsystem_path}"
                    )

    service = classes["QualificationService"]
    methods = {
        node.name: node
        for node in service.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    publication_methods = {
        "publish_policy",
        "publish_decision",
        "publish_held_evaluation",
        "publish_retirement",
    }
    missing_methods = publication_methods - set(methods)
    if missing_methods:
        raise ArchitectureViolation(
            "apex-research: qualification service lacks governed publication methods "
            + ", ".join(sorted(missing_methods))
        )
    for method_name in publication_methods:
        governed_returns = [
            node
            for node in methods[method_name].body
            if isinstance(node, ast.Return)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and isinstance(node.value.func.value, ast.Name)
            and node.value.func.value.id == "self"
            and node.value.func.attr == "_execute_publication"
        ]
        direct_publications = [
            node
            for statement in methods[method_name].body
            for node in ast.walk(statement)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "publish_record"
        ]
        if len(governed_returns) != 1 or direct_publications:
            raise ArchitectureViolation(
                f"apex-research: {method_name} bypasses governed qualification publication"
            )
        execute_call = governed_returns[0].value
        assert isinstance(execute_call, ast.Call)
        keywords = {
            item.arg: item.value
            for item in execute_call.keywords
            if item.arg is not None
        }
        if set(keywords) != {
            "action",
            "campaign_id",
            "target",
            "preflight",
            "launch",
            "complete",
        }:
            raise ArchitectureViolation(
                f"apex-research: {method_name} does not bind the governed publication contract"
            )
        if not isinstance(keywords["complete"], (ast.Lambda, ast.Name)):
            raise ArchitectureViolation(
                f"apex-research: {method_name} eagerly evaluates publication completion"
            )

        def reaches_workspace_publication(function_name: str, seen: set[str]) -> bool:
            if function_name in seen or function_name not in functions:
                return False
            seen.add(function_name)
            function = functions[function_name]
            for call in (
                node for node in ast.walk(function) if isinstance(node, ast.Call)
            ):
                called = (
                    call.func.attr
                    if isinstance(call.func, ast.Attribute)
                    else call.func.id
                    if isinstance(call.func, ast.Name)
                    else ""
                )
                if called == "publish_record":
                    return True
                if reaches_workspace_publication(called, seen):
                    return True
            return False

        complete_calls = {
            node.func.id
            if isinstance(node.func, ast.Name)
            else node.func.attr
            if isinstance(node.func, ast.Attribute)
            else ""
            for node in ast.walk(keywords["complete"])
            if isinstance(node, ast.Call)
        }
        if not any(
            reaches_workspace_publication(called, set()) for called in complete_calls
        ):
            raise ArchitectureViolation(
                f"apex-research: {method_name} completion does not reach Workspace publication"
            )
    execute_publication = methods.get("_execute_publication")
    governance_aliases = (
        {
            target.id
            for node in ast.walk(execute_publication)
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "_require_governance"
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        if execute_publication is not None
        else set()
    )
    governed_execute = execute_publication is not None and any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "execute"
        and (
            isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "_governance"
            or isinstance(node.func.value, ast.Name)
            and node.func.value.id in governance_aliases
        )
        and len(node.args) >= 2
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "action"
        and isinstance(node.args[1], ast.Name)
        and node.args[1].id == "authorize"
        for node in ast.walk(execute_publication)
    )
    if not governed_execute:
        raise ArchitectureViolation(
            "apex-research: qualification publication bypasses existing governance coordinator"
        )
    execute_assignments = [
        (index, statement)
        for index, statement in enumerate(execute_publication.body)
        if isinstance(statement, ast.Assign)
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Attribute)
        and statement.value.func.attr == "execute"
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
    ]
    completion_statements = [
        index
        for index, statement in enumerate(execute_publication.body)
        if isinstance(statement, ast.Try)
        and any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "complete"
            for node in ast.walk(statement)
        )
    ]
    direct_workspace_publications = [
        node
        for statement in execute_publication.body
        for node in ast.walk(statement)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "publish_record"
    ]
    result_name = (
        execute_assignments[0][1].targets[0].id if len(execute_assignments) == 1 else ""
    )

    def rejects_noncommitted(statement: ast.stmt) -> bool:
        return (
            isinstance(statement, ast.If)
            and any(
                isinstance(node, ast.Compare)
                and isinstance(node.left, ast.Attribute)
                and isinstance(node.left.value, ast.Name)
                and node.left.value.id == result_name
                and node.left.attr == "status"
                and len(node.ops) == 1
                and isinstance(node.ops[0], ast.NotEq)
                and len(node.comparators) == 1
                and isinstance(node.comparators[0], ast.Constant)
                and node.comparators[0].value == "committed"
                for node in ast.walk(statement.test)
            )
            and any(
                isinstance(node, ast.Return)
                and isinstance(node.value, ast.Name)
                and node.value.id == result_name
                for node in statement.body
            )
        )

    if (
        len(execute_assignments) != 1
        or len(completion_statements) != 1
        or execute_assignments[0][0] >= completion_statements[0]
        or not any(
            rejects_noncommitted(statement)
            and execute_assignments[0][0] < index < completion_statements[0]
            for index, statement in enumerate(execute_publication.body)
        )
        or direct_workspace_publications
    ):
        raise ArchitectureViolation(
            "apex-research: qualification publication ordering is not governed and committed-first"
        )

    reader_models = {
        "_read_policy": "QualificationPolicy",
        "_read_decision": "QualificationDecision",
        "_read_held_evaluation": "QualificationEvaluation",
        "_read_retirement": "QualificationRetirement",
        "_read_successor_claim": "QualificationSuccessorClaim",
    }
    for reader_name, model_name in reader_models.items():
        reader = functions.get(reader_name)
        if reader is None:
            raise ArchitectureViolation(
                f"apex-research: qualification lacks typed canonical readback {reader_name}"
            )

        def target_names(value: ast.AST) -> set[str]:
            if isinstance(value, ast.Name):
                return {value.id}
            if isinstance(value, (ast.Tuple, ast.List)):
                return {
                    name for element in value.elts for name in target_names(element)
                }
            return set()

        def value_origins(
            value: ast.AST | None, origins: dict[str, frozenset[str]]
        ) -> frozenset[str]:
            if value is None:
                return frozenset()
            return frozenset(
                origin
                for node in ast.walk(value)
                if isinstance(node, ast.Name)
                for origin in origins.get(node.id, ())
            )

        events = sorted(
            (
                node
                for node in ast.walk(reader)
                if isinstance(node, (ast.Assign, ast.AnnAssign))
                or (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "verify_publication"
                )
            ),
            key=lambda node: (node.lineno, node.col_offset),
        )
        origins: dict[str, frozenset[str]] = {}
        typed_origins: dict[str, frozenset[str]] = {}
        saw_fetch = False
        saw_parse = False
        verified = False
        for event in events:
            if isinstance(event, ast.Call):
                raw = frozenset(
                    origin
                    for argument in event.args
                    for origin in value_origins(argument, origins)
                )
                typed = frozenset(
                    origin
                    for argument in event.args
                    for origin in value_origins(argument, typed_origins)
                )
                if raw & typed:
                    verified = True
                continue
            targets = (
                event.targets if isinstance(event, ast.Assign) else (event.target,)
            )
            names = {name for target in targets for name in target_names(target)}
            value = event.value
            derived = value_origins(value, origins)
            typed = value_origins(value, typed_origins)
            fetch = value is not None and any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get_record"
                for node in ast.walk(value)
            )
            parses_model = value is not None and any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "model_validate_json"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == model_name
                for node in ast.walk(value)
            )
            for name in names:
                origins.pop(name, None)
                typed_origins.pop(name, None)
            if fetch:
                saw_fetch = True
                derived = frozenset({f"{reader_name}:{event.lineno}"})
            for name in names:
                if derived:
                    origins[name] = derived
                if parses_model and derived:
                    typed_origins[name] = derived
                    saw_parse = True
                elif typed:
                    typed_origins[name] = typed
        if not saw_fetch or not saw_parse or not verified:
            raise ArchitectureViolation(
                f"apex-research: qualification lacks typed canonical readback {reader_name}"
            )

    lineage_reader = functions.get("_query_lineage_records")
    lineage_calls = (
        [
            node
            for node in ast.walk(lineage_reader)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "query_lineage"
        ]
        if lineage_reader is not None
        else []
    )
    lineage_call = lineage_calls[0] if len(lineage_calls) == 1 else None
    lineage_keywords = (
        {
            keyword.arg: keyword.value
            for keyword in lineage_call.keywords
            if keyword.arg is not None
        }
        if lineage_call is not None
        else {}
    )
    lineage_loops = (
        [node for node in ast.walk(lineage_reader) if isinstance(node, ast.While)]
        if lineage_reader is not None
        else []
    )
    bounded_loop = next(
        (
            loop
            for loop in lineage_loops
            if lineage_call is not None and lineage_call in ast.walk(loop)
        ),
        None,
    )
    page_size = lineage_keywords.get("page_size")
    bounded_page_size = (
        isinstance(page_size, ast.Constant)
        and isinstance(page_size.value, int)
        and 1 <= page_size.value <= 1_000
    )
    max_depth = lineage_keywords.get("max_depth")
    bounded_depth = (
        isinstance(max_depth, ast.Constant)
        and isinstance(max_depth.value, int)
        and 1 <= max_depth.value <= 8
    )
    if isinstance(max_depth, ast.Name) and lineage_reader is not None:
        bounded_depth = any(
            isinstance(node, ast.If)
            and isinstance(node.test, ast.UnaryOp)
            and isinstance(node.test.op, ast.Not)
            and isinstance(node.test.operand, ast.Compare)
            and len(node.test.operand.ops) == 2
            and isinstance(node.test.operand.left, ast.Constant)
            and node.test.operand.left.value == 1
            and isinstance(node.test.operand.comparators[0], ast.Name)
            and node.test.operand.comparators[0].id == max_depth.id
            and isinstance(node.test.operand.comparators[1], ast.Constant)
            and node.test.operand.comparators[1].value == 8
            and all(isinstance(operator, ast.LtE) for operator in node.test.operand.ops)
            and any(isinstance(value, ast.Raise) for value in node.body)
            for node in ast.walk(lineage_reader)
        )

    def direct_guard(
        node: ast.AST,
        predicate: object,
    ) -> bool:
        return (
            isinstance(node, ast.If)
            and predicate(node.test)
            and any(isinstance(statement, ast.Raise) for statement in node.body)
        )

    def exact_name_constant_compare(
        value: ast.AST,
        name: str,
        operator_type: type[ast.cmpop],
        constant: object,
    ) -> bool:
        return (
            isinstance(value, ast.Compare)
            and isinstance(value.left, ast.Name)
            and value.left.id == name
            and len(value.ops) == 1
            and isinstance(value.ops[0], operator_type)
            and len(value.comparators) == 1
            and isinstance(value.comparators[0], ast.Constant)
            and value.comparators[0].value == constant
        )

    initial_names: dict[str, object] = {}
    if lineage_reader is not None and bounded_loop is not None:
        for statement in lineage_reader.body:
            if statement is bounded_loop:
                break
            targets = (
                statement.targets
                if isinstance(statement, ast.Assign)
                else (statement.target,)
                if isinstance(statement, ast.AnnAssign)
                else ()
            )
            value = (
                statement.value
                if isinstance(statement, (ast.Assign, ast.AnnAssign))
                else None
            )
            if (
                len(targets) == 1
                and isinstance(targets[0], ast.Name)
                and isinstance(value, ast.Constant)
            ):
                initial_names[targets[0].id] = value.value

    page_counter_bound = bounded_loop is not None and any(
        direct_guard(
            node,
            lambda test: (
                isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name)
                and test.left.id == "page_count"
                and len(test.ops) == 1
                and isinstance(test.ops[0], ast.GtE)
                and len(test.comparators) == 1
                and isinstance(test.comparators[0], ast.Constant)
                and isinstance(test.comparators[0].value, int)
                and 1 <= test.comparators[0].value <= 100
            ),
        )
        for node in bounded_loop.body
    )
    page_counter_advances = bounded_loop is not None and any(
        isinstance(node, ast.AugAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "page_count"
        and isinstance(node.op, ast.Add)
        and isinstance(node.value, ast.Constant)
        and node.value.value == 1
        for node in bounded_loop.body
    )
    cursor_cycle_rejected = bounded_loop is not None and any(
        direct_guard(
            node,
            lambda test: (
                isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name)
                and test.left.id == "next_cursor"
                and len(test.ops) == 1
                and isinstance(test.ops[0], ast.In)
                and len(test.comparators) == 1
                and isinstance(test.comparators[0], ast.Name)
                and test.comparators[0].id == "seen_cursors"
            ),
        )
        for node in bounded_loop.body
    )
    cursor_recorded = bounded_loop is not None and any(
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and isinstance(node.value.func.value, ast.Name)
        and node.value.func.value.id == "seen_cursors"
        and node.value.func.attr == "add"
        and len(node.value.args) == 1
        and isinstance(node.value.args[0], ast.Name)
        and node.value.args[0].id == "next_cursor"
        for node in bounded_loop.body
    )
    terminates_without_cursor = bounded_loop is not None and any(
        isinstance(node, ast.If)
        and exact_name_constant_compare(node.test, "next_cursor", ast.Is, None)
        and any(
            isinstance(statement, (ast.Return, ast.Break)) for statement in node.body
        )
        for node in bounded_loop.body
    )
    response_size_rejected = (
        bounded_loop is not None
        and bounded_page_size
        and any(
            direct_guard(
                node,
                lambda test: (
                    isinstance(test, ast.Compare)
                    and isinstance(test.left, ast.Call)
                    and isinstance(test.left.func, ast.Name)
                    and test.left.func.id == "len"
                    and len(test.left.args) == 1
                    and isinstance(test.left.args[0], ast.Name)
                    and test.left.args[0].id == "page_records"
                    and len(test.ops) == 1
                    and isinstance(test.ops[0], ast.Gt)
                    and len(test.comparators) == 1
                    and isinstance(test.comparators[0], ast.Constant)
                    and test.comparators[0].value == page_size.value
                ),
            )
            for node in bounded_loop.body
        )
    )
    snapshot_query_reused = (
        isinstance(lineage_keywords.get("snapshot_token"), ast.Name)
        and lineage_keywords["snapshot_token"].id == "snapshot_token"
    )
    snapshot_captured = bounded_loop is not None and any(
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "page_token"
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and isinstance(node.value.func.value, ast.Name)
        and node.value.func.value.id == "page"
        and node.value.func.attr == "get"
        and len(node.value.args) == 1
        and isinstance(node.value.args[0], ast.Constant)
        and node.value.args[0].value == "snapshot_token"
        for node in bounded_loop.body
    )
    snapshot_drift_rejected = bounded_loop is not None and any(
        direct_guard(
            node,
            lambda test: (
                isinstance(test, ast.BoolOp)
                and isinstance(test.op, ast.And)
                and len(test.values) == 2
                and exact_name_constant_compare(
                    test.values[0], "snapshot_token", ast.IsNot, None
                )
                and isinstance(test.values[1], ast.Compare)
                and isinstance(test.values[1].left, ast.Name)
                and test.values[1].left.id == "page_token"
                and len(test.values[1].ops) == 1
                and isinstance(test.values[1].ops[0], ast.NotEq)
                and len(test.values[1].comparators) == 1
                and isinstance(test.values[1].comparators[0], ast.Name)
                and test.values[1].comparators[0].id == "snapshot_token"
            ),
        )
        for node in bounded_loop.body
    )
    snapshot_advanced = bounded_loop is not None and any(
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "snapshot_token"
        and isinstance(node.value, ast.Name)
        and node.value.id == "page_token"
        for node in bounded_loop.body
    )
    loop_positions = (
        {id(statement): index for index, statement in enumerate(bounded_loop.body)}
        if bounded_loop is not None
        else {}
    )

    def containing_position(target: ast.AST | None) -> int:
        if bounded_loop is None or target is None:
            return -1
        return next(
            (
                index
                for index, statement in enumerate(bounded_loop.body)
                if target is statement or target in ast.walk(statement)
            ),
            -1,
        )

    query_position = containing_position(lineage_call)
    counter_guard_position = (
        next(
            (
                loop_positions[id(node)]
                for node in bounded_loop.body
                if page_counter_bound
                and direct_guard(
                    node,
                    lambda test: (
                        isinstance(test, ast.Compare)
                        and isinstance(test.left, ast.Name)
                        and test.left.id == "page_count"
                    ),
                )
            ),
            -1,
        )
        if bounded_loop is not None
        else -1
    )
    counter_advance_position = (
        next(
            (
                loop_positions[id(node)]
                for node in bounded_loop.body
                if isinstance(node, ast.AugAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == "page_count"
            ),
            -1,
        )
        if bounded_loop is not None
        else -1
    )
    token_position = (
        next(
            (
                index
                for index, node in enumerate(bounded_loop.body)
                if isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name) and target.id == "page_token"
                    for target in node.targets
                )
            ),
            -1,
        )
        if bounded_loop is not None
        else -1
    )
    drift_position = (
        next(
            (
                index
                for index, node in enumerate(bounded_loop.body)
                if isinstance(node, ast.If)
                and any(
                    isinstance(value, ast.Name) and value.id == "snapshot_token"
                    for value in ast.walk(node.test)
                )
                and any(
                    isinstance(value, ast.Name) and value.id == "page_token"
                    for value in ast.walk(node.test)
                )
            ),
            -1,
        )
        if bounded_loop is not None
        else -1
    )
    advance_position = (
        next(
            (
                index
                for index, node in enumerate(bounded_loop.body)
                if isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name) and target.id == "snapshot_token"
                    for target in node.targets
                )
            ),
            -1,
        )
        if bounded_loop is not None
        else -1
    )
    token_validated = bounded_loop is not None and any(
        isinstance(node, ast.If)
        and token_position < index < drift_position
        and any(
            isinstance(value, ast.Name) and value.id == "page_token"
            for value in ast.walk(node.test)
        )
        and any(isinstance(value, ast.Raise) for value in node.body)
        for index, node in enumerate(bounded_loop.body)
    )
    records_initialized = (
        lineage_reader is not None
        and bounded_loop is not None
        and any(
            isinstance(node, (ast.Assign, ast.AnnAssign))
            and any(
                isinstance(target, ast.Name) and target.id == "records"
                for target in (
                    node.targets if isinstance(node, ast.Assign) else (node.target,)
                )
            )
            and isinstance(node.value, ast.List)
            for node in lineage_reader.body[: lineage_reader.body.index(bounded_loop)]
        )
    )
    records_accumulated = bounded_loop is not None and any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "records"
        and node.func.attr in {"append", "extend"}
        for node in ast.walk(bounded_loop)
    )
    returns_accumulated = bounded_loop is not None and any(
        isinstance(node, ast.Return)
        and any(
            isinstance(value, ast.Name) and value.id == "records"
            for value in ast.walk(node.value)
        )
        for node in ast.walk(bounded_loop)
    )
    if (
        len(lineage_calls) != 1
        or not {"max_depth", "page_size", "cursor", "snapshot_token"}
        <= set(lineage_keywords)
        or not bounded_page_size
        or not bounded_depth
        or not page_counter_bound
        or not page_counter_advances
        or not cursor_cycle_rejected
        or not cursor_recorded
        or not terminates_without_cursor
        or not response_size_rejected
        or initial_names.get("page_count") != 0
        or initial_names.get("snapshot_token", object()) is not None
        or not snapshot_query_reused
        or not snapshot_captured
        or not snapshot_drift_rejected
        or not snapshot_advanced
        or not (
            0
            <= counter_guard_position
            < counter_advance_position
            < query_position
            < token_position
            < drift_position
            < advance_position
        )
        or not token_validated
        or not records_initialized
        or not records_accumulated
        or not returns_accumulated
    ):
        raise ArchitectureViolation(
            "apex-research: qualification lineage is not bounded snapshot pagination"
        )

    evaluator = classes["QualificationEvaluator"]
    evaluator_names = {
        node.id
        if isinstance(node, ast.Name)
        else node.attr
        if isinstance(node, ast.Attribute)
        else ""
        for node in ast.walk(evaluator)
    }
    if not {"CandidateRecordReader", "EvidenceV2Publisher", "read"} <= evaluator_names:
        raise ArchitectureViolation(
            "apex-research: qualification evaluator lacks typed Candidate/Evidence readback"
        )

    dependency_calls = {
        package / "package_intake.py": (
            "StrategyPackageIntakeService",
            "get_registered_package",
        ),
        package / "candidates.py": ("_verify_artifact", "verify_artifact"),
    }
    for dependency, (owner_name, required_call) in dependency_calls.items():
        if not dependency.is_file():
            raise ArchitectureViolation(
                f"apex-research: qualification owner dependency is missing: {dependency}"
            )
        dependency_tree = ast.parse(
            dependency.read_text(encoding="utf-8"), filename=str(dependency)
        )
        owners = [
            node
            for node in dependency_tree.body
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == owner_name
        ]
        if len(owners) != 1 or not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == required_call
            for node in ast.walk(owners[0])
        ):
            raise ArchitectureViolation(
                f"apex-research: qualification dependency lacks {required_call}: {dependency}"
            )

    def workspace_bound_call(call_name: str) -> bool:
        return any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == call_name
            and (
                isinstance(node.func.value, ast.Name)
                and node.func.value.id == "workspace"
                or isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "_workspace"
            )
            for node in subsystem_nodes
        )

    for call_name in ("get_record", "publish_record", "query_lineage"):
        if not workspace_bound_call(call_name):
            raise ArchitectureViolation(
                f"apex-research: qualification lacks Workspace-bound {call_name}"
            )

    calls = {
        node.func.attr
        if isinstance(node.func, ast.Attribute)
        else node.func.id
        if isinstance(node.func, ast.Name)
        else ""
        for node in subsystem_nodes
        if isinstance(node, ast.Call)
    }
    for required_call in ("execute", "get_record", "publish_record", "query_lineage"):
        if required_call not in calls:
            raise ArchitectureViolation(
                f"apex-research: qualification seam lacks {required_call}: {qualification}"
            )

    state_class = classes["QualificationState"]
    state_values = {
        node.value.value
        for node in state_class.body
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    state_names = {
        target.id
        for node in state_class.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    expected_states = {
        "idea",
        "experimental",
        "formally_tested",
        "research_validated",
        "robustness_validated",
        "research_qualified",
        "retired",
    }
    expected_state_names = {value.upper() for value in expected_states}
    if state_values != expected_states or state_names != expected_state_names:
        raise ArchitectureViolation(
            "apex-research: qualification maturity states drifted"
        )

    strings = {
        node.value
        for node in subsystem_nodes
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    if (
        not {
            "historical_research_maturity",
            "forbidden",
            "evaluation-of",
            "successor-of",
        }
        <= strings
    ):
        raise ArchitectureViolation(
            "apex-research: qualification lacks historical maturity-only semantics"
        )
    field_names = {
        node.target.id
        for class_name in required_fields
        for node in classes[class_name].body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    if field_names & {
        "current",
        "currency",
        "approved",
        "active",
        "tradable",
        "live",
        "production",
        "order",
        "position",
    }:
        raise ArchitectureViolation(
            "apex-research: qualification model declares non-historical authority fields"
        )


SPEC015_OWNER_CLASSES = {
    "QualificationDecision",
    "QualificationEvaluation",
    "QualificationEvaluator",
    "QualificationHistoryReader",
    "QualificationLedger",
    "QualificationPolicy",
    "QualificationRegistry",
    "QualificationRetirement",
    "QualificationRetirementRequest",
    "QualificationService",
    "QualificationState",
    "QualificationSuccessorClaim",
}
SPEC015_MATURITY_OWNER_CLASSES = {
    "MaturityDecision",
    "MaturityLedger",
    "MaturityPolicy",
    "MaturityRegistry",
    "MaturityService",
    "MaturityState",
}
SPEC015_PARALLEL_OWNER_CLASSES = {
    *SPEC015_OWNER_CLASSES,
    *SPEC015_MATURITY_OWNER_CLASSES,
    "QualificationPublisher",
    "QualificationStateStore",
    "ResearchQualificationPublisher",
}
SPEC015_OWNER_METHODS = {
    "evaluate_qualification",
    "publish_decision",
    "publish_held_evaluation",
    "publish_policy",
    "publish_qualification",
    "publish_qualification_policy",
    "publish_retirement",
}


def _scan_spec015_non_owner_repositories(repository_root: Path) -> None:
    for repository in ("strategy-workspace", "quant-runtime", "strategy-reporting"):
        source_root = repository_root / repository / "src"
        if not source_root.is_dir():
            continue
        for path in _safe_python_sources(source_root):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            qualification_modules: set[str] = set()
            qualification_symbols: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if (
                            alias.name == "apex_research"
                            or alias.name == "apex_research.qualification"
                            or alias.name.startswith("apex_research.qualification.")
                        ):
                            qualification_modules.add(
                                alias.asname or alias.name.split(".", maxsplit=1)[0]
                            )
                elif (
                    isinstance(node, ast.ImportFrom)
                    and node.module is not None
                    and (
                        node.module == "apex_research"
                        or node.module == "apex_research.qualification"
                        or node.module.startswith("apex_research.qualification.")
                    )
                ):
                    qualification_modules.update(
                        alias.asname or alias.name
                        for alias in node.names
                        if node.module == "apex_research"
                        and alias.name == "qualification"
                    )
                    qualification_symbols.update(
                        alias.asname or alias.name
                        for alias in node.names
                        if alias.name in SPEC015_PARALLEL_OWNER_CLASSES
                    )
            owns_qualification = any(
                isinstance(node, ast.ClassDef)
                and node.name in SPEC015_PARALLEL_OWNER_CLASSES
                or isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name in SPEC015_OWNER_METHODS
                for node in ast.walk(tree)
            )

            def references_qualification_owner(
                value: ast.AST,
                module_aliases: frozenset[str] = frozenset(qualification_modules),
                symbol_aliases: set[str] = qualification_symbols,
            ) -> bool:
                for candidate in ast.walk(value):
                    if (
                        isinstance(candidate, ast.Name)
                        and candidate.id in symbol_aliases
                    ):
                        return True
                    if not isinstance(candidate, ast.Attribute):
                        continue
                    root: ast.AST = candidate
                    attributes: set[str] = set()
                    while isinstance(root, ast.Attribute):
                        attributes.add(root.attr)
                        root = root.value
                    if (
                        isinstance(root, ast.Name)
                        and root.id in module_aliases
                        and any(
                            name in SPEC015_PARALLEL_OWNER_CLASSES
                            for name in attributes
                        )
                    ):
                        return True
                return False

            assignments = [
                node
                for node in ast.walk(tree)
                if isinstance(node, (ast.Assign, ast.AnnAssign))
            ]

            def assigned_names(node: ast.AST) -> set[str]:
                if isinstance(node, ast.Name):
                    return {node.id}
                if isinstance(node, (ast.Tuple, ast.List)):
                    return {name for item in node.elts for name in assigned_names(item)}
                return set()

            def assignment_parts(
                assignment: ast.Assign | ast.AnnAssign,
            ) -> tuple[set[str], ast.AST | None]:
                targets = (
                    assignment.targets
                    if isinstance(assignment, ast.Assign)
                    else (assignment.target,)
                )
                return (
                    {name for target in targets for name in assigned_names(target)},
                    assignment.value,
                )

            changed = True
            while changed:
                changed = False
                for assignment in assignments:
                    aliases, value = assignment_parts(assignment)
                    if (
                        value is not None
                        and references_qualification_owner(value)
                        and not aliases <= qualification_symbols
                    ):
                        qualification_symbols.update(aliases)
                        changed = True

            publication_aliases: set[str] = set()
            changed = True
            while changed:
                changed = False
                for assignment in assignments:
                    aliases, value = assignment_parts(assignment)
                    publication_source = (
                        isinstance(value, ast.Attribute)
                        and value.attr == "publish_record"
                    ) or (
                        isinstance(value, ast.Name) and value.id in publication_aliases
                    )
                    if publication_source and not aliases <= publication_aliases:
                        publication_aliases.update(aliases)
                        changed = True

            publish_calls = tuple(
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "publish_record"
                    or isinstance(node.func, ast.Name)
                    and node.func.id in publication_aliases
                )
            )

            def contains_qualification_value(value: ast.AST) -> bool:
                return references_qualification_owner(value) or any(
                    isinstance(candidate, ast.Constant)
                    and isinstance(candidate.value, str)
                    and (
                        candidate.value.startswith("apex-research.qualification-")
                        or candidate.value == "historical_research_maturity"
                    )
                    for candidate in ast.walk(value)
                )

            publishes_qualification = any(
                any(
                    contains_qualification_value(argument)
                    for argument in (
                        *call.args,
                        *(item.value for item in call.keywords),
                    )
                )
                for call in publish_calls
            )
            helper_publication_parameters: dict[str, set[int]] = {}
            for function in (
                node
                for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            ):
                parameters = [argument.arg for argument in function.args.args]
                indexes: set[int] = set()
                for call in (
                    node
                    for node in ast.walk(function)
                    if isinstance(node, ast.Call)
                    and (
                        isinstance(node.func, ast.Attribute)
                        and node.func.attr == "publish_record"
                        or isinstance(node.func, ast.Name)
                        and node.func.id in publication_aliases
                    )
                ):
                    indexes.update(
                        parameters.index(argument.id)
                        for argument in call.args
                        if isinstance(argument, ast.Name) and argument.id in parameters
                    )
                if indexes:
                    helper_publication_parameters[function.name] = indexes
            publishes_qualification = publishes_qualification or any(
                isinstance(call.func, ast.Name)
                and call.func.id in helper_publication_parameters
                and any(
                    index < len(call.args)
                    and contains_qualification_value(call.args[index])
                    for index in helper_publication_parameters[call.func.id]
                )
                for call in ast.walk(tree)
                if isinstance(call, ast.Call)
            )
            if owns_qualification or publishes_qualification:
                raise ArchitectureViolation(
                    f"{repository}: qualification ownership outside Apex Research: {path}"
                )


def _scan_spec014_evidence_seams(repository_root: Path) -> None:
    apex_root = repository_root / "apex-research" / "src" / "apex_research"
    reporting_root = (
        repository_root / "strategy-reporting" / "src" / "strategy_reporting"
    )
    apex_paths = tuple(
        sorted(
            {
                *apex_root.glob("evidence_*.py"),
                apex_root / "report_models.py",
            }
        )
    )
    apex_paths = tuple(path for path in apex_paths if path.is_file())
    reporting_paths = tuple(sorted(reporting_root.rglob("evidence_v2.py")))
    if not apex_paths and not reporting_paths:
        return
    _reject_spec014_forbidden(apex_paths, owner="apex-research")
    _reject_spec014_forbidden(reporting_paths, owner="strategy-reporting")

    apex_by_name = {path.name: path for path in apex_paths}
    if apex_paths:
        required_files = {
            "evidence_v2.py",
            "evidence_backfill.py",
            "evidence_extensions.py",
            "report_models.py",
        }
        if not required_files <= set(apex_by_name):
            raise ArchitectureViolation(
                "apex-research: Evidence v2 acceptance seam is incomplete"
            )
        evidence_source = "\n".join(
            path.read_text(encoding="utf-8") for path in apex_paths
        )
        for marker in (
            "EvidenceV2",
            "EvidenceSection",
            "EvidenceSourceRef",
            "EvidenceV2Publisher",
            "WorkspaceClientProtocol",
            "qualification_inference",
            "production_approval_inference",
            "get_record",
            "get_run",
            "get_result",
            "verify_artifact",
            "query_lineage",
        ):
            if marker not in evidence_source:
                raise ArchitectureViolation(
                    f"apex-research: Evidence v2 lacks public seam {marker}"
                )
        backfill_source = apex_by_name["evidence_backfill.py"].read_text(
            encoding="utf-8"
        )
        for marker in (
            "EvidenceV2BackfillService",
            "EvidenceV2StudySourcePublisher",
            "query_lineage",
            "snapshot_token",
            "max_depth",
            "page_size",
            "_BACKFILL_MAX_PAGES",
            "seen_cursors",
        ):
            if marker not in backfill_source:
                raise ArchitectureViolation(
                    f"apex-research: Evidence v2 backfill lacks bounded seam {marker}"
                )
        extension_source = apex_by_name["evidence_extensions.py"].read_text(
            encoding="utf-8"
        )
        for marker in ("AuxiliaryValidationRecord", "FutureOptionalEvidenceRecord"):
            if marker not in extension_source:
                raise ArchitectureViolation(
                    f"apex-research: Evidence v2 extensions lack strict record {marker}"
                )
        report_source = apex_by_name["report_models.py"].read_text(encoding="utf-8")
        if "EvidenceV2StudySource" not in report_source:
            raise ArchitectureViolation(
                "apex-research: Evidence v2 study-source contract is missing"
            )

    if reporting_paths:
        reporting_source = "\n".join(
            path.read_text(encoding="utf-8") for path in reporting_paths
        )
        for marker in (
            "EvidenceV2ReadModelBuilder",
            "EvidenceV2ReadModel",
            "qualification_inference",
            "production_approval_inference",
            "get_record",
            "get_run",
            "get_result",
        ):
            if marker not in reporting_source:
                raise ArchitectureViolation(
                    f"strategy-reporting: Evidence v2 read model lacks public seam {marker}"
                )
        if not any(
            marker in reporting_source
            for marker in ("WorkspaceAdapter", "WorkspaceClientPort")
        ):
            raise ArchitectureViolation(
                "strategy-reporting: Evidence v2 read model lacks Workspace public port"
            )
        if not any(
            marker in reporting_source for marker in ("verify_ref", "verify_artifact")
        ):
            raise ArchitectureViolation(
                "strategy-reporting: Evidence v2 read model lacks artifact verification"
            )


def _reject_spec014_forbidden(paths: tuple[Path, ...], *, owner: str) -> None:
    forbidden_imports = {
        "strategy_workspace.storage": "private Workspace access",
        "strategy_workspace.core": "private Workspace access",
        "quant_runtime": "private Runtime execution",
        "apex_research": "private Apex import",
        "sqlite3": "parallel state or evidence truth",
        "subprocess": "parallel runner",
        "requests": "direct network",
        "httpx": "direct network",
        "socket": "direct network",
    }
    forbidden_calls = {
        "list_records": "global record scan",
        "register_package": "package registry bypass",
        "submit_run": "formal runner bypass",
    }
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                modules = []
            for module in modules:
                for prefix, reason in forbidden_imports.items():
                    if module == prefix or module.startswith(prefix + "."):
                        if owner == "apex-research" and prefix == "apex_research":
                            continue
                        raise ArchitectureViolation(f"{owner}: {reason}: {path}")
            if isinstance(node, ast.Call):
                name = (
                    node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else node.func.id
                    if isinstance(node.func, ast.Name)
                    else ""
                )
                if name in forbidden_calls:
                    raise ArchitectureViolation(
                        f"{owner}: {forbidden_calls[name]}: {path}"
                    )
            if isinstance(node, ast.ClassDef) and any(
                term in node.name
                for term in (
                    "Registry",
                    "Ledger",
                    "Runner",
                    "Backtester",
                    "EvidenceTruth",
                )
            ):
                raise ArchitectureViolation(f"{owner}: parallel owner: {path}")
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
                names = {
                    target.id for target in targets if isinstance(target, ast.Name)
                }
                if "qualification" in names:
                    raise ArchitectureViolation(
                        f"{owner}: qualification masquerade: {path}"
                    )
                if "production_approval" in names:
                    raise ArchitectureViolation(
                        f"{owner}: production-approval masquerade: {path}"
                    )


def _scan_statistical_control_seams(repository: Path) -> None:
    source_root = repository / "src" / "apex_research"
    statistical = source_root / "statistical_control.py"
    reporting = source_root / "statistical_reporting.py"
    if not statistical.is_file():
        return
    _scan_apex_public_seam(
        (statistical, reporting),
        ApexSeamPolicy(
            component="statistical control",
            forbidden_imports=(
                ("strategy_workspace.storage", "private Workspace access"),
                ("strategy_workspace.core", "private Workspace access"),
                ("quant_runtime", "private Runtime execution"),
                ("sqlite3", "parallel state or evidence truth"),
                ("subprocess", "parallel runner"),
                ("requests", "direct network"),
                ("httpx", "direct network"),
            ),
            forbidden_calls=(
                ("list_records", "global record scan"),
                ("register_package", "package registry bypass"),
                ("submit_run", "formal runner bypass"),
            ),
            forbidden_attributes=(),
            required_classes=(
                "StatisticalControlPolicy",
                "TestFamily",
                "CampaignTrialCensus",
                "SelectionSnapshot",
                "PurgeEmbargoEvaluator",
                "RawPValueEvidence",
                "MultipleTestingService",
                "NautilusReturnArtifactReader",
                "DeflatedSharpeService",
                "StatisticalAssessment",
                "StatisticalAssessmentService",
                "StatisticalStudyReportPublisher",
            ),
            required_names=("WorkspaceClientProtocol", "PublishedRecordRef"),
            required_calls=("get_record", "verify_artifact", "read_artifact"),
        ),
    )


def _scan_validation_matrix_seams(repository: Path) -> None:
    validation = repository / "src" / "apex_research" / "validation.py"
    if not validation.is_file():
        return
    source = validation.read_text(encoding="utf-8")
    required = (
        "ValidationProtocolMatrix",
        "ValidationMatrixExpander",
        "ValidationEligibilityService",
        "ValidationCellExecutor",
        "ValidationMatrixOrchestrator",
        "ValidationEvidenceAggregator",
        "ValidationReconciliationRequired",
        "WorkspaceClientProtocol",
        "QuantRuntimeAdapter",
        "GovernedAction.EXTERNAL_VALIDATION",
        "GovernedAction.FORMAL_RUN",
    )
    for marker in required:
        if marker not in source:
            raise ArchitectureViolation(
                f"apex-research: validation matrix lacks canonical seam {marker}: {validation}"
            )
    forbidden = (
        ("import sqlite3", "parallel ledger"),
        ("from sqlite3", "parallel ledger"),
        ("import quant_runtime", "private Runtime"),
        ("from quant_runtime", "private Runtime"),
        ("submit_run(", "formal submission"),
        ("class ValidationRunner", "parallel runner"),
        ("class ValidationEvidenceStore", "parallel evidence"),
        ("class CandidateRegistry", "package registry"),
        ("import requests", "direct network"),
        ("import httpx", "direct network"),
        ("import socket", "direct network"),
    )
    for marker, reason in forbidden:
        if marker in source:
            raise ArchitectureViolation(
                f"apex-research: validation matrix owns forbidden {reason}: {validation}"
            )


def _scan_research_memory_seams(repository: Path) -> None:
    source_root = repository / "src" / "apex_research"
    memory = tuple(
        sorted(
            path
            for path in source_root.rglob("memory*.py")
            if "__pycache__" not in path.parts
        )
    )
    if not memory:
        return
    _scan_apex_public_seam(
        memory,
        ApexSeamPolicy(
            component="Research Memory",
            forbidden_imports=(
                ("strategy_workspace.storage", "private Workspace access"),
                ("strategy_workspace.core", "private Workspace access"),
                ("sqlite3", "authoritative memory database"),
                ("subprocess", "parallel runner"),
                ("socket", "direct network"),
                ("requests", "direct network"),
                ("httpx", "direct network"),
                ("urllib.request", "direct network"),
            ),
            forbidden_calls=(
                ("list_records", "bounded global record scan"),
                ("register_package", "package registry bypass"),
                ("submit_run", "formal runner bypass"),
            ),
            forbidden_attributes=(),
            required_classes=(
                "ResearchMemoryPolicy",
                "ResearchMemoryEntry",
                "ResearchMemoryQuery",
                "ResearchMemoryDuplicateService",
                "ResearchMemoryContextBuilder",
                "ResearchMemoryStep",
            ),
            required_names=("WorkspaceClientProtocol",),
            required_calls=("query_lineage",),
        ),
    )
    query_path = source_root / "memory_query.py"
    query_source = (
        query_path.read_text(encoding="utf-8") if query_path.is_file() else ""
    )
    if "snapshot_token" not in query_source:
        raise ArchitectureViolation(
            "apex-research: Research Memory lacks reusable Workspace snapshot token"
        )
    for forbidden in ("allow_missing_root", "lineage_root_not_found"):
        if forbidden in query_source:
            raise ArchitectureViolation(
                "apex-research: Research Memory must not downgrade missing lineage roots to empty"
            )


def _scan_focused_loop_seams(repository: Path) -> None:
    focused = repository / "src" / "apex_research" / "focused.py"
    _scan_apex_public_seam(
        focused,
        ApexSeamPolicy(
            component="focused loop",
            forbidden_imports=(
                ("strategy_workspace.storage", "private Workspace access"),
                ("strategy_workspace.core", "private Workspace access"),
                ("quant_runtime", "private Runtime execution"),
                ("subprocess", "parallel runner"),
                ("socket", "direct network"),
                ("httpx", "direct network"),
                ("requests", "direct network"),
                ("keyring", "host credential"),
                ("sqlite3", "parallel ledger"),
            ),
            forbidden_calls=(
                ("register_package", "package registry bypass"),
                ("submit_run", "formal runner bypass"),
            ),
            forbidden_attributes=(
                ("os.getenv", "host credential"),
                ("os.environ", "host credential"),
            ),
            required_classes=(
                "FocusedCandidateSelector",
                "FocusedStageRecord",
                "FocusedPreflightResult",
                "FocusedFormalRun",
                "FocusedReflection",
                "FocusedFeedback",
                "FocusedDecision",
            ),
            required_names=("WorkspaceClientProtocol", "PublishedRecordRef"),
            required_calls=(),
        ),
    )


def _scan_apex_public_seam(
    source_paths: Path | tuple[Path, ...],
    policy: ApexSeamPolicy,
) -> None:
    paths = (source_paths,) if isinstance(source_paths, Path) else source_paths
    paths = tuple(path for path in paths if path.is_file())
    if not paths:
        return
    trees = tuple(
        (path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        for path in paths
    )
    nodes = tuple(node for _, tree in trees for node in ast.walk(tree))
    classes = {node.name for node in nodes if isinstance(node, ast.ClassDef)}
    names = {node.id for node in nodes if isinstance(node, ast.Name)}
    imports = (
        {
            alias.name
            for node in nodes
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        | {node.module or "" for node in nodes if isinstance(node, ast.ImportFrom)}
        | {
            f"{node.module}.{alias.name}"
            for node in nodes
            if isinstance(node, ast.ImportFrom) and node.module
            for alias in node.names
        }
    )
    calls = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in nodes
        if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Attribute, ast.Name))
    }
    attributes = {
        f"{node.value.id}.{node.attr}"
        for node in nodes
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
    }
    path_label = ", ".join(str(path) for path in paths)
    for node in nodes:
        if isinstance(node, ast.ClassDef) and any(
            owner in node.name
            for owner in ("Ledger", "Registry", "Runner", "Backtester", "EvidenceTruth")
        ):
            raise ArchitectureViolation(
                f"apex-research: {policy.component} defines forbidden parallel owner {node.name}: {path_label}"
            )
    for module, reason in policy.forbidden_imports:
        if any(item == module or item.startswith(f"{module}.") for item in imports):
            raise ArchitectureViolation(
                f"apex-research: {policy.component} owns forbidden {reason}: {path_label}"
            )
    for call, reason in policy.forbidden_calls:
        if call in calls:
            raise ArchitectureViolation(
                f"apex-research: {policy.component} owns forbidden {reason}: {path_label}"
            )
    for attribute, reason in policy.forbidden_attributes:
        if attribute in attributes:
            raise ArchitectureViolation(
                f"apex-research: {policy.component} owns forbidden {reason}: {path_label}"
            )
    missing = (
        set(policy.required_classes) - classes,
        set(policy.required_names) - names,
        set(policy.required_calls) - calls,
    )
    if any(missing):
        absent = sorted(set().union(*missing))
        raise ArchitectureViolation(
            f"apex-research: {policy.component} lacks public tracer boundaries {absent}: {path_label}"
        )


def _scan_rdagent_seams(repository: Path) -> None:
    source_root = repository / "src" / "apex_research"
    adapter = source_root / "adapters" / "rdagent.py"
    if not adapter.is_file():
        return
    adapter_source = adapter.read_text(encoding="utf-8")
    for marker, reason in (
        ("import rdagent", "direct RD-Agent import"),
        ("from rdagent", "direct RD-Agent import"),
        ("import subprocess", "parallel runner"),
        ("import socket", "direct network"),
        ("os.environ", "host environment"),
        ("os.getenv", "host environment"),
        ("credential", "host credential"),
        ("sqlite3", "parallel ledger"),
        ("register_package(", "package registry bypass"),
        ("submit_run(", "Runtime bypass"),
    ):
        if marker in adapter_source:
            raise ArchitectureViolation(f"apex-research: RD-Agent {reason}: {adapter}")
    for marker in (
        "RDAgentAdapterConfig",
        "GovernedExternalResearchRunner",
        "RunnerBackedResearchEngine",
        "forbidden_operations",
    ):
        if marker not in adapter_source:
            raise ArchitectureViolation(
                f"apex-research: RD-Agent adapter lacks {marker}: {adapter}"
            )
    strategy = source_root / "rdagent_strategy.py"
    if strategy.is_file():
        strategy_source = strategy.read_text(encoding="utf-8")
        for marker, reason in (
            ("import rdagent", "direct RD-Agent import"),
            ("from rdagent", "direct RD-Agent import"),
            ("import subprocess", "parallel runner"),
            ("import socket", "direct network"),
            ("os.environ", "host environment"),
            ("os.getenv", "host environment"),
            ("sqlite3", "parallel ledger"),
            ("fin_quant", "forbidden operation"),
            ("register_package(", "package registry bypass"),
            ("submit_run(", "Runtime bypass"),
        ):
            if marker in strategy_source:
                raise ArchitectureViolation(
                    f"apex-research: RD-Agent {reason}: {strategy}"
                )
        for marker in (
            "GovernedExternalResearchRunner",
            "readback_strategy_package_draft_artifacts",
            "StrategyCandidate.create",
        ):
            if marker not in strategy_source:
                raise ArchitectureViolation(
                    f"apex-research: RD-Agent Strategy normalization lacks {marker}: {strategy}"
                )
    chain = source_root / "rdagent_strategy_chain.py"
    if chain.is_file():
        chain_source = chain.read_text(encoding="utf-8")
        for marker in (
            "admit_proposal",
            "evaluate_strategy_static",
            ".intake(",
            ".assess(",
            "confirmed_preflight_request",
            ".preflight(",
            'formal: str = "not_evaluated"',
        ):
            if marker not in chain_source:
                raise ArchitectureViolation(
                    f"apex-research: RD-Agent Strategy chain lacks canonical stage {marker}: {chain}"
                )
        for marker, reason in (
            ("submit_run(", "formal submission bypass"),
            ("GovernedAction.FORMAL_RUN", "formal run bypass"),
            ("import quant_runtime.", "private Runtime import"),
            ("from quant_runtime.", "private Runtime import"),
            ("strategy_workspace.", "private Workspace import"),
        ):
            if marker in chain_source:
                raise ArchitectureViolation(
                    f"apex-research: RD-Agent Strategy chain owns {reason}: {chain}"
                )


def _scan_apex_governance_seams(source_root: Path) -> None:
    if not source_root.is_dir():
        return
    adapter = source_root / "adapters" / "tools.py"
    allowed_process_seams = {
        adapter,
        source_root / "external_runner" / "oci.py",
        source_root / "external_runner" / "guardian.py",
    }
    application = source_root / "application.py"
    for path in source_root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        owns_process_control = (
            "import subprocess" in source or "from subprocess" in source
        )
        if owns_process_control and path not in allowed_process_seams:
            raise ArchitectureViolation(
                f"apex-research: ungoverned subprocess seam: {path}"
            )
    adapters = source_root / "adapters"
    if adapters.is_dir():
        for path in adapters.rglob("*.py"):
            if path.name in {"__init__.py", "tools.py"}:
                continue
            source = path.read_text(encoding="utf-8")
            external_adapter = True
            if external_adapter and not any(
                seam in source
                for seam in ("GovernedExternalResearchRunner", "ExternalResearchRunner")
            ):
                raise ArchitectureViolation(
                    f"apex-research: external adapter bypasses runner interface: {path}"
                )
            if external_adapter and not any(
                marker in source for marker in ("production = True", "production=True")
            ):
                raise ArchitectureViolation(
                    f"apex-research: external adapter must declare production execution: {path}"
                )
            if external_adapter:
                forbidden_adapter_seams = (
                    ("import socket", "network"),
                    ("from socket", "network"),
                    ("import httpx", "network"),
                    ("from httpx", "network"),
                    ("import requests", "network"),
                    ("from requests", "network"),
                    ("import urllib", "network"),
                    ("from urllib", "network"),
                    ("import aiohttp", "network"),
                    ("import http.client", "network"),
                    ("os.getenv", "host environment"),
                    ("os.environ", "host environment"),
                    ("from os import getenv", "host environment"),
                    ("from os import environ", "host environment"),
                    ("import dotenv", "host environment"),
                    ("import keyring", "host credential"),
                    ("from keyring", "host credential"),
                    ("os.system(", "process"),
                    ("create_subprocess", "process"),
                    ("import multiprocessing", "process"),
                    ("from multiprocessing", "process"),
                    ("strategy_workspace", "Workspace access"),
                    ("WorkspaceClient", "Workspace access"),
                    ("register_package(", "package registration"),
                    ("submit_run(", "Runtime submission"),
                    ("orchestrator.advance(", "lifecycle"),
                    ("campaign-transition", "lifecycle"),
                    ("apex-research.decision", "decision"),
                    ("publish_record(", "Workspace publication"),
                    ("publish_candidate(", "Candidate publication"),
                    ("candidate-publication", "Candidate publication"),
                    ("formal-run", "formal masquerade"),
                    ("qualification", "qualification"),
                    ("qualified", "qualification"),
                )
                for marker, reason in forbidden_adapter_seams:
                    if marker in source:
                        raise ArchitectureViolation(
                            f"apex-research: external adapter owns forbidden {reason} seam: {path}"
                        )
    if adapter.is_file():
        source = adapter.read_text(encoding="utf-8")
        for marker in ("ActionGrant", "runtime_resource_scope", "lease_expires_at"):
            if marker not in source:
                raise ArchitectureViolation(
                    f"apex-research: Runtime adapter lacks governed {marker} binding"
                )
    if application.is_file():
        source = application.read_text(encoding="utf-8")
        if "workspace.submit_run(" in source:
            raise ArchitectureViolation(
                "apex-research: run submitted before Runtime preflight"
            )
        for marker in (
            "governance.execute(",
            "GovernedAction.CANDIDATE_PACKAGE_INTAKE",
            "GovernedAction.FORMAL_RUN",
            "GovernedAction.REPORT_PUBLICATION",
        ):
            if marker not in source:
                raise ArchitectureViolation(
                    f"apex-research: application lacks governed side-effect marker {marker}"
                )


def validate_constitution() -> None:
    module_path = ROOT / "tools" / "validate_architecture_constitution.py"
    specification = importlib.util.spec_from_file_location(
        "constitution_validator", module_path
    )
    assert specification is not None and specification.loader is not None
    validator = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(validator)
    validator.validate_policy(
        validator.read_json(ROOT / "docs" / "architecture-constitution.v1.json")
    )


def run_fixture_checks(repository_root: Path) -> None:
    environment = dict(os.environ)
    for check in fixture_plan(repository_root):
        repository = repository_root / check.repository
        if not repository.is_dir():
            raise ArchitectureViolation(
                f"fixture repository is unavailable: {repository}"
            )
        try:
            HARNESS.run_command(
                list(check.command),
                cwd=repository,
                environment=environment,
                timeout_seconds=1_800,
            )
        except HARNESS.InstalledWheelFailure as exc:
            raise ArchitectureViolation(
                f"{check.owner} public-seam fixture failed:\n{exc}"
            ) from exc


def run_full_gate_checks(repository_root: Path) -> list[dict[str, str]]:
    """Execute every non-connected release gate without retaining build output."""
    baseline_formatter_drift: list[dict[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="spec014-full-gates-") as temporary:
        dist = Path(temporary).resolve()
        repository_root = repository_root.resolve()
        environment = HARNESS.sanitized_environment()
        for check in full_gate_plan(repository_root):
            if check.connected:
                raise ArchitectureViolation(
                    "connected checks must not enter the full gate plan"
                )
            repository = repository_root / check.repository
            if not repository.is_dir():
                raise ArchitectureViolation(
                    f"gate repository is unavailable: {repository}"
                )
            command = tuple(
                token.replace("{dist}", str(dist)) for token in check.command
            )
            try:
                HARNESS.run_command(
                    list(command),
                    cwd=repository,
                    environment=environment,
                    timeout_seconds=1_800,
                )
            except HARNESS.InstalledWheelFailure as exc:
                baseline = UNCHANGED_REPOSITORY_BASELINES.get(check.repository)
                exact_baseline = (
                    baseline is not None
                    and HARNESS.run_command(
                        ["git", "rev-parse", "HEAD"],
                        cwd=repository,
                        environment=environment,
                        timeout_seconds=30,
                    ).strip()
                    == baseline
                    and not HARNESS.run_command(
                        ["git", "status", "--porcelain"],
                        cwd=repository,
                        environment=environment,
                        timeout_seconds=30,
                    ).strip()
                )
                formatter_only = (
                    exc.returncode == 1
                    and "Would reformat:" in str(exc)
                    and "error:" not in str(exc).lower()
                )
                if check.baseline_only and exact_baseline and formatter_only:
                    baseline_formatter_drift.append(
                        {
                            "owner": check.owner,
                            "category": check.category,
                            "status": "baseline-only-drift",
                            "detail": str(exc),
                        }
                    )
                    continue
                raise ArchitectureViolation(
                    f"{check.owner} {check.category} gate failed:\n{exc}"
                ) from exc
    return baseline_formatter_drift


def run_connected_status_checks(repository_root: Path) -> list[dict[str, str]]:
    """Execute connected checks independently and preserve each exact status."""
    repository_root = repository_root.resolve()
    environment = HARNESS.sanitized_environment()
    statuses: list[dict[str, str]] = []
    for check in connected_status_plan():
        repository = repository_root / check.repository
        if not repository.is_dir():
            statuses.append(
                {
                    "owner": check.owner,
                    "category": check.category,
                    "status": "unavailable",
                    "detail": f"repository is unavailable: {repository}",
                }
            )
            continue
        try:
            output = HARNESS.run_command(
                list(check.command),
                cwd=repository,
                environment=environment,
                timeout_seconds=1_800,
            )
        except HARNESS.InstalledWheelFailure as exc:
            statuses.append(
                {
                    "owner": check.owner,
                    "category": check.category,
                    "status": "failed-or-unavailable",
                    "detail": str(exc),
                }
            )
        else:
            counts = {
                name: sum(
                    int(value) for value in re.findall(rf"(\d+)\s+{name}", output)
                )
                for name in ("passed", "skipped", "failed", "error")
            }
            if (
                counts["failed"]
                or counts["error"]
                or not (counts["passed"] or counts["skipped"])
            ):
                status = "indeterminate"
            elif counts["passed"] and counts["skipped"]:
                status = "partial"
            elif counts["passed"]:
                status = "passed"
            else:
                status = "skipped"
            statuses.append(
                {
                    "owner": check.owner,
                    "category": check.category,
                    "status": status,
                    "detail": output,
                }
            )
    return statuses


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--run-fixtures", action="store_true")
    parser.add_argument("--run-full-gates", action="store_true")
    parser.add_argument("--run-connected-status", action="store_true")
    arguments = parser.parse_args(argv)
    baseline_formatter_drift: list[dict[str, str]] = []
    connected_statuses: list[dict[str, str]] = []
    try:
        validate_constitution()
        scan_sources(arguments.repository_root)
        if arguments.run_fixtures:
            run_fixture_checks(arguments.repository_root)
        if arguments.run_full_gates:
            baseline_formatter_drift = run_full_gate_checks(arguments.repository_root)
        if arguments.run_connected_status:
            connected_statuses = run_connected_status_checks(arguments.repository_root)
    except ArchitectureViolation as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "fixtures": arguments.run_fixtures,
                "full_gates": arguments.run_full_gates,
                "baseline_formatter_drift": baseline_formatter_drift,
                "connected_statuses": connected_statuses,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
