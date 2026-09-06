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
SPEC015_ADMISSION_CONTRACT = {
    "schema": "quant-research.future-spec-admission.v1",
    "spec": "SPEC-015",
    "canonical_owner": "apex_research",
    "public_seam": (
        "Apex qualification policy, pure evaluator, and governed publisher / "
        "WorkspaceClient immutable publication, canonical record readback, bounded "
        "lineage query, registered Strategy Package lookup, and artifact verification"
    ),
    "identity_impact": (
        "Policy, held evaluation, advancement, and retirement identities freeze one "
        "exact Candidate revision, historical research maturity state, predecessor, "
        "Evidence v2 revision, policy revision, requirement observations, owner "
        "sources, thresholds, comparability rules, governance evidence, and lineage "
        "while excluding publication timestamps, local paths, storage metadata, and "
        "evidence currency."
    ),
    "evidence_level": (
        "Apex-owned deterministic historical research maturity decisions over exact "
        "Evidence v2 owner facts; no current evidence currency, Runtime single-run "
        "truth, production approval, or operational authority is created."
    ),
    "fail_closed_behavior": (
        "Require strict typed canonical owner readback and the existing governance "
        "reservation and grant lifecycle for qualification publication; reject "
        "skipped or regressive transitions, stale predecessors, multiple "
        "state-changing successors, mandatory not_evaluated, blocked, incomparable, "
        "stale, superseded, identity-mismatched, denominator-drifting, ownerless, or "
        "currency-masquerading evidence without metric reconstruction, auxiliary-to-"
        "formal substitution, a second ledger, or production-authority inference."
    ),
    "compatibility": [
        "spec-006-governance",
        "spec-009-candidate-gate",
        "spec-012-validation-matrix",
        "spec-013-statistical-control",
        "spec-014-evidence-v2",
        "spec-028-candidate-ir",
        "spec-032-currency-separate",
    ],
    "claims": [],
    "lifecycle_states": [
        "idea",
        "experimental",
        "formally_tested",
        "research_validated",
        "robustness_validated",
        "research_qualified",
        "retired",
    ],
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
        "tools/test_spec015_installed_wheel_tracer.py",
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
        "tools/test_spec015_installed_wheel_tracer.py",
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
            "--quiet",
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
        if repository in UNCHANGED_REPOSITORY_BASELINES:
            add(
                owner,
                repository,
                "spec015-source-diff",
                "git",
                "diff",
                "--quiet",
                UNCHANGED_REPOSITORY_BASELINES[repository],
                "HEAD",
                "--",
                "src",
                baseline_only=True,
            )
            add(
                owner,
                repository,
                "spec015-worktree-source-diff",
                "git",
                "diff",
                "--quiet",
                "HEAD",
                "--",
                "src",
                baseline_only=True,
            )
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
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for forbidden, reason in rules:
                if (
                    repository == "apex-research"
                    and forbidden == "shutil.copy"
                    and path.as_posix().endswith("external_runner/recovery.py")
                ):
                    continue
                if _ast_rule_present(tree, forbidden):
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
    admission = (
        repository_root / "docs" / "architecture-admissions" / "spec-015.v1.json"
    )
    constitution = repository_root / "docs" / "architecture-constitution.v1.json"
    if constitution.is_file() and not admission.is_file():
        raise ArchitectureViolation(
            "quant-research: SPEC-015 architecture admission is missing"
        )
    _scan_spec015_qualification_seam(
        repository_root / "apex-research",
        required=constitution.is_file() or admission.is_file(),
    )
    _scan_spec015_non_owner_repositories(repository_root)


def _ast_rule_present(tree: ast.Module, forbidden: str) -> bool:
    """Match ownership-bearing syntax, never comments or explanatory prose."""

    def constant_string(value: ast.AST) -> str | None:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value.lower()
        if isinstance(value, ast.BinOp) and isinstance(value.op, ast.Add):
            left = constant_string(value.left)
            right = constant_string(value.right)
            return left + right if left is not None and right is not None else None
        return None

    lowered = forbidden.lower()
    import_prefixes = ("import ", "from ")
    requested_module = (
        lowered.removeprefix("import ").removeprefix("from ")
        if lowered.startswith(import_prefixes)
        else lowered
    )
    for node in ast.walk(tree):
        modules: tuple[str, ...] = ()
        if isinstance(node, ast.Import):
            modules = tuple(alias.name.lower() for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules = ((node.module or "").lower(),)
        if modules and any(
            module == requested_module or module.startswith(requested_module + ".")
            for module in modules
        ):
            return True
        if isinstance(node, ast.Call):
            call_name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else ""
            )
            if call_name in {"__import__", "import_module"} and node.args:
                module = constant_string(node.args[0])
                if module is not None and (
                    module == requested_module
                    or module.startswith(requested_module + ".")
                ):
                    return True
        if "-" in lowered or lowered == "workspace.sqlite3":
            literal = constant_string(node)
            if literal == lowered or (
                literal is not None and literal.startswith(lowered + ".")
            ):
                return True
        elif "." in lowered and isinstance(node, ast.Attribute):
            expression = ast.unparse(node).lower()
            if expression == lowered or expression.startswith(lowered + "."):
                return True
        elif "." not in lowered and not lowered.startswith(import_prefixes):
            identifier = (
                node.id
                if isinstance(node, ast.Name)
                else node.attr
                if isinstance(node, ast.Attribute)
                else node.name
                if isinstance(
                    node,
                    (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
                )
                else ""
            )
            if identifier.lower() == lowered:
                return True
    return False


def _safe_python_sources(source_root: Path) -> tuple[Path, ...]:
    """Enumerate Python source without ever traversing a link or junction."""

    def approved_worktree_junction(path: Path) -> bool:
        git_file = path / ".git"
        try:
            marker = git_file.read_text(encoding="utf-8", errors="strict").strip()
            if not git_file.is_file() or not marker.startswith("gitdir: "):
                return False
            git_directory = Path(marker.removeprefix("gitdir: "))
            return (
                git_directory.is_absolute()
                and git_directory.is_dir()
                and (git_directory / "commondir").is_file()
                and (git_directory / "gitdir").is_file()
                and git_file.samefile(
                    Path(
                        (git_directory / "gitdir")
                        .read_text(encoding="utf-8", errors="strict")
                        .strip()
                    )
                )
            )
        except OSError:
            return False

    protected_ancestors = (source_root, *source_root.parents[:3])
    linked_ancestor = next(
        (
            path
            for path in protected_ancestors
            if path.exists()
            and (path.is_symlink() or getattr(path, "is_junction", lambda: False)())
            and not approved_worktree_junction(path)
        ),
        None,
    )
    if linked_ancestor is not None:
        raise ArchitectureViolation(
            f"source root or repository ancestor is a symbolic link or junction: "
            f"{linked_ancestor}"
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
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_")
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
    canonical_class_names = {
        "QualificationDecision",
        "QualificationEvaluation",
        "QualificationEvaluator",
        "QualificationHistory",
        "QualificationHistoryReader",
        "QualificationPolicy",
        "QualificationRetirement",
        "QualificationRetirementRequest",
        "QualificationService",
        "QualificationState",
    }

    def bound_names(target: ast.AST) -> set[str]:
        if isinstance(target, ast.Name):
            return {target.id}
        if isinstance(target, (ast.Tuple, ast.List)):
            return {name for item in target.elts for name in bound_names(item)}
        if isinstance(target, ast.Starred):
            return bound_names(target.value)
        return set()

    for path, tree in subsystem_trees:
        declarations_seen: set[str] = set()
        for statement in tree.body:
            if isinstance(statement, ast.ClassDef):
                declarations_seen.add(statement.name)
                continue
            if (
                isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef))
                and statement.name in canonical_class_names
            ):
                raise ArchitectureViolation(
                    f"apex-research: qualification canonical owner is rebound: {path}"
                )
            targets: tuple[ast.AST, ...] = ()
            if isinstance(statement, ast.Assign):
                targets = tuple(statement.targets)
            elif isinstance(statement, (ast.AnnAssign, ast.AugAssign)):
                targets = (statement.target,)
            rebound = {
                name for target in targets for name in bound_names(target)
            } & canonical_class_names
            if isinstance(statement, ast.Import):
                rebound.update(
                    (alias.asname or alias.name.split(".", maxsplit=1)[0])
                    for alias in statement.names
                    if (alias.asname or alias.name.split(".", maxsplit=1)[0])
                    in canonical_class_names
                )
            elif isinstance(statement, ast.ImportFrom):
                rebound.update(
                    alias.asname or alias.name
                    for alias in statement.names
                    if (alias.asname or alias.name) in canonical_class_names
                )
            if rebound & declarations_seen:
                raise ArchitectureViolation(
                    f"apex-research: qualification canonical owner is rebound: {path}"
                )
    for path in all_package_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        owner_aliases = set(classes)
        aliases_changed = True
        while aliases_changed:
            aliases_changed = False
            for statement in ast.walk(tree):
                if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
                    continue
                targets = (
                    tuple(statement.targets)
                    if isinstance(statement, ast.Assign)
                    else (statement.target,)
                )
                target_names = {
                    name for target in targets for name in bound_names(target)
                }
                value = statement.value
                source_name = (
                    value.id
                    if isinstance(value, ast.Name)
                    else value.attr
                    if isinstance(value, ast.Attribute)
                    else ""
                )
                if source_name in owner_aliases and not target_names <= owner_aliases:
                    owner_aliases.update(target_names)
                    aliases_changed = True
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                top_level = node in tree.body
                methods = {
                    item.name
                    for item in node.body
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
                inherited_owner = any(
                    isinstance(base, ast.Name)
                    and base.id in owner_aliases
                    or isinstance(base, ast.Attribute)
                    and base.attr in owner_aliases
                    for base in node.bases
                )
                alternative_owner = (
                    bool(methods & SPEC015_OWNER_METHODS)
                    or inherited_owner
                    or (
                        "Qualification" in node.name
                        and (
                            node.name.endswith(
                                (
                                    "Service",
                                    "Publisher",
                                    "Ledger",
                                    "Registry",
                                    "StateStore",
                                )
                            )
                        )
                    )
                )
                canonical_owner = (
                    top_level
                    and path in subsystem_paths
                    and node.name in canonical_class_names
                )
                if (
                    node.name
                    in {
                        "CandidateTruth",
                        "QualificationSuccessorClaim",
                        "MaturityDecision",
                        "MaturityLedger",
                        "MaturityPolicy",
                        "MaturityRegistry",
                        "MaturityService",
                        "MaturityState",
                    }
                    or node.name in canonical_class_names
                    and not canonical_owner
                    or node.name
                    in {
                        "MaturityService",
                        "QualificationPublisher",
                        "QualificationStateStore",
                        "ResearchQualificationPublisher",
                    }
                    or alternative_owner
                    and not canonical_owner
                    or (
                        node.name not in classes
                        and "Qualification" in node.name
                        and any(
                            marker in node.name for marker in forbidden_owner_markers
                        )
                    )
                ):
                    raise ArchitectureViolation(
                        f"apex-research: parallel qualification owner {node.name}: {path}"
                    )
                if (
                    any(
                        isinstance(item, (ast.Assign, ast.AnnAssign))
                        and any(
                            name in SPEC015_OWNER_METHODS
                            for target in (
                                tuple(item.targets)
                                if isinstance(item, ast.Assign)
                                else (item.target,)
                            )
                            for name in bound_names(target)
                        )
                        for item in node.body
                    )
                    and not canonical_owner
                ):
                    raise ArchitectureViolation(
                        f"apex-research: parallel qualification owner {node.name}: {path}"
                    )
            allowed_owner_methods = {
                id(item)
                for candidate in tree.body
                if isinstance(candidate, ast.ClassDef)
                and candidate.name == "QualificationService"
                for item in candidate.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name in SPEC015_OWNER_METHODS
                and id(node) not in allowed_owner_methods
            ):
                raise ArchitectureViolation(
                    f"apex-research: parallel qualification owner {node.name}: {path}"
                )
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and any(
                name in canonical_class_names
                for target in (
                    tuple(node.targets)
                    if isinstance(node, ast.Assign)
                    else (node.target,)
                )
                for name in bound_names(target)
            ):
                raise ArchitectureViolation(
                    f"apex-research: qualification canonical owner is rebound: {path}"
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
        "QualificationHistory",
        "QualificationHistoryReader",
        "QualificationPolicy",
        "QualificationRetirement",
        "QualificationRetirementRequest",
        "QualificationService",
        "QualificationState",
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
            "supersedes_qualification",
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
        "QualificationHistory": {
            "candidate",
            "state",
            "decisions",
            "held_evaluations",
            "retirement",
            "scope",
            "operational_authority",
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

    for class_name in required_fields:
        class_node = classes[class_name]
        source_tree = next(
            tree for _, tree in subsystem_trees if class_node in tree.body
        )
        frozen_model_imported = any(
            isinstance(node, ast.ImportFrom)
            and node.module == "apex_research.records"
            and any(
                alias.name == "FrozenModel" and alias.asname in {None, "FrozenModel"}
                for alias in node.names
            )
            for node in source_tree.body
        )
        frozen_model_rebound = any(
            isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "FrozenModel"
            or isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign))
            and any(
                "FrozenModel" in bound_names(target)
                for target in (
                    tuple(node.targets)
                    if isinstance(node, ast.Assign)
                    else (node.target,)
                )
            )
            for node in source_tree.body
        )
        directly_frozen = any(
            isinstance(base, ast.Name) and base.id == "FrozenModel"
            for base in class_node.bases
        )
        if not frozen_model_imported or frozen_model_rebound or not directly_frozen:
            raise ArchitectureViolation(
                f"apex-research: {class_name} must be a frozen strict owner record"
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

            returns = [
                node for node in ast.walk(method) if isinstance(node, ast.Return)
            ]
            returned = returns[0].value if len(returns) == 1 else None
            supplies_identity = isinstance(returned, ast.Call) and any(
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
                for node in ast.walk(returned)
            )
            if not supplies_identity or any(
                isinstance(node, ast.IfExp) for node in ast.walk(returned)
            ):
                raise ArchitectureViolation(
                    f"apex-research: {class_name}.{method_name} does not supply its "
                    f"identity field from the canonical constructor"
                )

            identity_assignments = [
                node
                for node in method.body
                if isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name) and target.id == "identity"
                    for target in node.targets
                )
                and isinstance(node.value, ast.Dict)
            ]
            if allowed_calls == {"canonical_sha256"}:
                if len(identity_assignments) != 1:
                    raise ArchitectureViolation(
                        f"apex-research: {class_name}.{method_name} canonical identity "
                        "must be one explicit literal mapping"
                    )
                identity_dict = identity_assignments[0].value
                assert isinstance(identity_dict, ast.Dict)
                explicit = {
                    "schema_id" if key.value == "schema" else str(key.value)
                    for key in identity_dict.keys
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)
                }
                includes_values = any(
                    key is None and isinstance(value, ast.Name) and value.id == "values"
                    for key, value in zip(
                        identity_dict.keys, identity_dict.values, strict=True
                    )
                )
                popped = {
                    str(call.args[0].value)
                    for call in ast.walk(method)
                    if isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and isinstance(call.func.value, ast.Name)
                    and call.func.value.id == "values"
                    and call.func.attr == "pop"
                    and call.args
                    and isinstance(call.args[0], ast.Constant)
                    and isinstance(call.args[0].value, str)
                    and call.lineno < identity_assignments[0].lineno
                }
                declared = required_fields[class_name]
                identity_id = identity_field.replace("record_id", "decision_id")
                required_identity = declared - {identity_id, "governance"}
                represented = set(explicit)
                if includes_values:
                    represented.update(declared - popped - {identity_id})
                if not required_identity <= represented:
                    raise ArchitectureViolation(
                        f"apex-research: {class_name}.{method_name} canonical identity omits "
                        + ", ".join(sorted(required_identity - represented))
                    )
                substituted = (
                    explicit
                    & (declared - popped - {identity_id})
                    - {"schema_id", "scope", "operational_authority"}
                    if includes_values
                    else set()
                )
                if substituted:
                    raise ArchitectureViolation(
                        f"apex-research: {class_name}.{method_name} canonical identity "
                        "substitutes meaning-bearing fields: "
                        + ", ".join(sorted(substituted))
                    )

                def identity_target(target: ast.AST) -> bool:
                    root = target
                    while isinstance(root, (ast.Attribute, ast.Subscript)):
                        root = root.value
                    return isinstance(root, ast.Name) and root.id == "identity"

                identity_mutations = [
                    node
                    for node in ast.walk(method)
                    if getattr(node, "lineno", -1) > identity_assignments[0].lineno
                    and (
                        isinstance(
                            node,
                            (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr),
                        )
                        and any(
                            identity_target(target)
                            for target in (
                                tuple(node.targets)
                                if isinstance(node, ast.Assign)
                                else (node.target,)
                            )
                        )
                        or isinstance(node, ast.Call)
                        and (
                            isinstance(node.func, ast.Attribute)
                            and identity_target(node.func.value)
                            or (
                                node.func.id
                                if isinstance(node.func, ast.Name)
                                else node.func.attr
                                if isinstance(node.func, ast.Attribute)
                                else ""
                            )
                            != "canonical_sha256"
                            and any(
                                isinstance(argument, ast.Name)
                                and argument.id == "identity"
                                for argument in (
                                    *node.args,
                                    *(item.value for item in node.keywords),
                                )
                            )
                        )
                    )
                ]
                if identity_mutations:
                    raise ArchitectureViolation(
                        f"apex-research: {class_name}.{method_name} canonical identity "
                        "is mutable after construction"
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
    required_governance_imports = {
        "ActionReservation",
        "CampaignLedgerReader",
        "GovernanceCoordinator",
        "GovernedAction",
    }
    governance_imports = {
        alias.name
        for _, subsystem_tree in subsystem_trees
        for node in subsystem_tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "apex_research.governance"
        for alias in node.names
        if alias.asname in {None, alias.name}
    }
    governance_names_rebound: set[str] = set()
    for _, subsystem_tree in subsystem_trees:
        for node in ast.walk(subsystem_tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                candidates = {node.name}
            elif isinstance(
                node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr)
            ):
                candidates = {
                    item
                    for target in (
                        tuple(node.targets)
                        if isinstance(node, ast.Assign)
                        else (node.target,)
                    )
                    for item in bound_names(target)
                }
            elif isinstance(node, ast.arg):
                candidates = {node.arg}
            else:
                candidates = set()
            governance_names_rebound.update(candidates & required_governance_imports)
    if (
        not required_governance_imports <= governance_imports
        or governance_names_rebound
    ):
        raise ArchitectureViolation(
            "apex-research: qualification governance types must come directly from "
            "apex_research.governance"
        )
    trusted_integrity_imports = {
        "canonical_sha256": "apex_research.canonical",
        "verify_publication": "apex_research.evidence_workspace",
    }
    for subsystem_path, subsystem_tree in subsystem_trees:
        loaded_names = {
            node.id
            for node in ast.walk(subsystem_tree)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        }
        for helper_name, trusted_module in trusted_integrity_imports.items():
            if helper_name not in loaded_names:
                continue
            imported_directly = any(
                isinstance(node, ast.ImportFrom)
                and node.module == trusted_module
                and any(
                    alias.name == helper_name and alias.asname in {None, helper_name}
                    for alias in node.names
                )
                for node in subsystem_tree.body
            )
            rebound = any(
                isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == helper_name
                or isinstance(
                    node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr)
                )
                and any(
                    helper_name in bound_names(target)
                    for target in (
                        tuple(node.targets)
                        if isinstance(node, ast.Assign)
                        else (node.target,)
                    )
                )
                or isinstance(node, ast.arg)
                and node.arg == helper_name
                for node in ast.walk(subsystem_tree)
            )
            if not imported_directly or rebound:
                raise ArchitectureViolation(
                    "apex-research: qualification integrity helpers must come directly "
                    f"from trusted owner modules: {subsystem_path}"
                )
    for required_name in ("canonical_sha256",):
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
        workspace_method_aliases: dict[str, str] = {}
        aliases_changed = True
        while aliases_changed:
            aliases_changed = False
            for node in ast.walk(subsystem_tree):
                if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue
                value = node.value
                method = (
                    value.attr
                    if isinstance(value, ast.Attribute)
                    and value.attr in {"publish_record", "list_records", "submit_run"}
                    else workspace_method_aliases.get(value.id)
                    if isinstance(value, ast.Name)
                    else None
                )
                if method is None:
                    continue
                targets = (
                    tuple(node.targets)
                    if isinstance(node, ast.Assign)
                    else (node.target,)
                )
                for alias in {
                    name for target in targets for name in bound_names(target)
                }:
                    if workspace_method_aliases.get(alias) != method:
                        workspace_method_aliases[alias] = method
                        aliases_changed = True
        aliased_calls = [
            node
            for node in ast.walk(subsystem_tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in workspace_method_aliases
        ]
        if aliased_calls:
            raise ArchitectureViolation(
                "apex-research: qualification uses forbidden workspace method alias "
                f"{workspace_method_aliases[aliased_calls[0].func.id]}: {subsystem_path}"
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
        nested_return_ids = {
            id(node)
            for nested in ast.walk(methods[method_name])
            if isinstance(nested, (ast.FunctionDef, ast.AsyncFunctionDef))
            and nested is not methods[method_name]
            for node in ast.walk(nested)
            if isinstance(node, ast.Return)
        }
        all_method_returns = [
            node
            for node in ast.walk(methods[method_name])
            if isinstance(node, ast.Return) and id(node) not in nested_return_ids
        ]
        if (
            len(governed_returns) != 1
            or all_method_returns != governed_returns
            or direct_publications
        ):
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
            "idempotency_key",
            "preflight",
            "complete",
        }:
            raise ArchitectureViolation(
                f"apex-research: {method_name} does not bind the governed publication contract"
            )
        publication_value = {
            "publish_policy": "policy",
            "publish_decision": "evaluation",
            "publish_held_evaluation": "evaluation",
            "publish_retirement": "request",
        }[method_name]
        if (
            ast.unparse(keywords["action"]) != "action"
            or ast.unparse(keywords["campaign_id"])
            != f"{publication_value}.campaign.record_id"
            or ast.unparse(keywords["idempotency_key"])
            != f"qualification_publication_idempotency_key({publication_value})"
        ):
            raise ArchitectureViolation(
                f"apex-research: {method_name} does not bind the governed publication contract"
            )
        if not isinstance(keywords["complete"], (ast.Lambda, ast.Name)):
            raise ArchitectureViolation(
                f"apex-research: {method_name} eagerly evaluates publication completion"
            )
        completion_callable = keywords["complete"]
        named_completion = next(
            (
                local
                for local in methods[method_name].body
                if isinstance(completion_callable, ast.Name)
                and isinstance(local, (ast.FunctionDef, ast.AsyncFunctionDef))
                and local.name == completion_callable.id
            ),
            None,
        )
        completion_definition = (
            completion_callable
            if isinstance(completion_callable, ast.Lambda)
            else named_completion
        )
        completion_defaults = (
            (
                *completion_definition.args.defaults,
                *completion_definition.args.kw_defaults,
            )
            if completion_definition is not None
            else ()
        )
        if any(
            default is not None
            and any(isinstance(node, ast.Call) for node in ast.walk(default))
            for default in completion_defaults
        ):
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
                if called == "publish_record" and (
                    isinstance(call.func, ast.Attribute)
                    and isinstance(call.func.value, ast.Name)
                    and call.func.value.id
                    in {argument.arg for argument in function.args.args}
                    or isinstance(call.func, ast.Attribute)
                    and isinstance(call.func.value, ast.Attribute)
                    and isinstance(call.func.value.value, ast.Name)
                    and call.func.value.value.id == "self"
                    and call.func.value.attr == "_workspace"
                ):
                    return True
                if reaches_workspace_publication(called, seen):
                    return True
            return False

        local_functions = {
            node.name: node
            for node in methods[method_name].body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

        def callback_calls(
            value: ast.AST,
            local_catalog: dict[
                str, ast.FunctionDef | ast.AsyncFunctionDef
            ] = local_functions,
        ) -> set[str]:
            if isinstance(value, ast.Name) and value.id in local_catalog:
                roots: tuple[ast.AST, ...] = (local_catalog[value.id],)
            else:
                roots = (value,)
            return {
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else ""
                for root in roots
                for node in ast.walk(root)
                if isinstance(node, ast.Call)
            }

        publication_calls = {
            callback_name: {
                called
                for called in callback_calls(keywords[callback_name])
                if reaches_workspace_publication(called, set())
            }
            for callback_name in ("preflight", "complete")
        }
        if publication_calls["preflight"]:
            raise ArchitectureViolation(
                f"apex-research: {method_name} publishes outside an allowed deferred phase"
            )

        if not publication_calls["complete"]:
            raise ArchitectureViolation(
                f"apex-research: {method_name} completion does not reach Workspace publication"
            )
        eager_publication = any(
            reaches_workspace_publication(
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else "",
                set(),
            )
            for statement in methods[method_name].body
            if not isinstance(
                statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Return)
            )
            for node in ast.walk(statement)
            if isinstance(node, ast.Call)
        )
        eager_publication = eager_publication or any(
            reaches_workspace_publication(
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else "",
                set(),
            )
            for argument in (
                *execute_call.args,
                *(
                    keyword.value
                    for keyword in execute_call.keywords
                    if keyword.arg not in {"preflight", "complete"}
                ),
            )
            for node in ast.walk(argument)
            if isinstance(node, ast.Call)
        )
        if eager_publication:
            raise ArchitectureViolation(
                f"apex-research: {method_name} eagerly publishes before governance"
            )
    execute_publication = methods.get("_execute_publication")
    if execute_publication is None:
        raise ArchitectureViolation(
            "apex-research: qualification service lacks _execute_publication"
        )
    scope_function = functions.get("qualification_publication_scope")
    scope_returns = (
        [node for node in scope_function.body if isinstance(node, ast.Return)]
        if scope_function is not None
        else []
    )
    if (
        scope_function is None
        or [argument.arg for argument in scope_function.args.args] != ["reference"]
        or len(scope_returns) != 1
        or ast.unparse(scope_returns[0].value)
        != "(ResourceRef(kind=ResourceKind.QUALIFICATION_PUBLICATION, "
        "resource_id=reference.record_id, version=reference.record_type),)"
    ):
        raise ArchitectureViolation(
            "apex-research: qualification publication action/resource contract is not exact"
        )
    expected_resource_assignments = [
        (index, statement)
        for index, statement in enumerate(execute_publication.body)
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
        and statement.targets[0].id == "expected_resources"
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Name)
        and statement.value.func.id == "qualification_publication_scope"
        and len(statement.value.args) == 1
        and isinstance(statement.value.args[0], ast.Name)
        and statement.value.args[0].id == "target"
        and not statement.value.keywords
    ]

    def boolean_terms(value: ast.AST) -> tuple[ast.AST, ...]:
        if isinstance(value, ast.BoolOp) and isinstance(value.op, ast.Or):
            return tuple(term for item in value.values for term in boolean_terms(item))
        return (value,)

    def exact_attribute_compare(
        value: ast.AST,
        *,
        left_attribute: str,
        operator: type[ast.cmpop],
        right_name: str | None = None,
        right_attribute: tuple[str, str] | None = None,
    ) -> bool:
        if not (
            isinstance(value, ast.Compare)
            and isinstance(value.left, ast.Attribute)
            and isinstance(value.left.value, ast.Name)
            and value.left.value.id == "action"
            and value.left.attr == left_attribute
            and len(value.ops) == 1
            and isinstance(value.ops[0], operator)
            and len(value.comparators) == 1
        ):
            return False
        comparator = value.comparators[0]
        if right_name is not None:
            return isinstance(comparator, ast.Name) and comparator.id == right_name
        assert right_attribute is not None
        return (
            isinstance(comparator, ast.Attribute)
            and isinstance(comparator.value, ast.Name)
            and comparator.value.id == right_attribute[0]
            and comparator.attr == right_attribute[1]
        )

    action_contract_guards = [
        (index, statement)
        for index, statement in enumerate(execute_publication.body)
        if isinstance(statement, ast.If)
        and any(isinstance(item, ast.Raise) for item in statement.body)
        and (terms := boolean_terms(statement.test))
        and any(
            exact_attribute_compare(
                term,
                left_attribute="action",
                operator=ast.IsNot,
                right_attribute=("GovernedAction", "QUALIFICATION_PUBLICATION"),
            )
            for term in terms
        )
        and any(
            exact_attribute_compare(
                term,
                left_attribute="campaign_id",
                operator=ast.NotEq,
                right_name="campaign_id",
            )
            for term in terms
        )
        and any(
            exact_attribute_compare(
                term,
                left_attribute="resources",
                operator=ast.NotEq,
                right_name="expected_resources",
            )
            for term in terms
        )
        and any(
            exact_attribute_compare(
                term,
                left_attribute="idempotency_key",
                operator=ast.NotEq,
                right_name="idempotency_key",
            )
            for term in terms
        )
    ]
    if (
        len(expected_resource_assignments) != 1
        or len(action_contract_guards) != 1
        or expected_resource_assignments[0][0] >= action_contract_guards[0][0]
    ):
        raise ArchitectureViolation(
            "apex-research: qualification publication action/resource contract is not exact"
        )
    authorize_functions = [
        node
        for node in execute_publication.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "authorize"
    ]
    exact_grant_guard = len(authorize_functions) == 1 and any(
        isinstance(statement, ast.If)
        and ast.unparse(statement.test) == "grant.reservation.request != action"
        and len(statement.body) == 1
        and isinstance(statement.body[0], ast.Raise)
        and not statement.orelse
        for statement in authorize_functions[0].body
    )
    if not exact_grant_guard:
        raise ArchitectureViolation(
            "apex-research: qualification publication grant must bind the exact action request"
        )
    governance_assignments = [
        (index, node)
        for index, node in enumerate(execute_publication.body)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and isinstance(node.value.func.value, ast.Name)
        and node.value.func.value.id == "self"
        and node.value.func.attr == "_require_governance"
        and not node.value.args
        and not node.value.keywords
    ]
    governance_aliases = (
        {governance_assignments[0][1].targets[0].id}
        if len(governance_assignments) == 1
        else set()
    )
    execute_assignments = [
        (index, statement)
        for index, statement in enumerate(execute_publication.body)
        if isinstance(statement, ast.Assign)
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Attribute)
        and statement.value.func.attr == "execute"
        and isinstance(statement.value.func.value, ast.Name)
        and statement.value.func.value.id in governance_aliases
        and len(statement.value.args) == 2
        and isinstance(statement.value.args[0], ast.Name)
        and statement.value.args[0].id == "action"
        and isinstance(statement.value.args[1], ast.Name)
        and statement.value.args[1].id == "authorize"
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
    ]
    action_rebindings = [
        node
        for node in ast.walk(execute_publication)
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr))
        and any(
            "action" in bound_names(target)
            for target in (
                tuple(node.targets) if isinstance(node, ast.Assign) else (node.target,)
            )
        )
    ]
    if action_rebindings:
        raise ArchitectureViolation(
            "apex-research: qualification publication action contract is rebound"
        )
    governance_rebindings = [
        node
        for index, statement in enumerate(execute_publication.body)
        if governance_assignments
        and execute_assignments
        and governance_assignments[0][0] < index < execute_assignments[0][0]
        for node in ast.walk(statement)
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr))
        and any(
            bool(bound_names(target) & governance_aliases)
            for target in (
                tuple(node.targets) if isinstance(node, ast.Assign) else (node.target,)
            )
        )
    ]
    if len(governance_assignments) != 1 or governance_rebindings:
        raise ArchitectureViolation(
            "apex-research: qualification publication bypasses existing governance coordinator"
        )
    completion_statements = [
        index
        for index, statement in enumerate(execute_publication.body)
        if isinstance(statement, ast.Try)
        and any(
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "complete"
            for node in statement.body
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

    def writes_result(target: ast.AST) -> bool:
        if isinstance(target, ast.Name):
            return target.id == result_name
        if isinstance(target, (ast.Tuple, ast.List)):
            return any(writes_result(item) for item in target.elts)
        if isinstance(target, ast.Starred):
            return writes_result(target.value)
        if isinstance(target, (ast.Attribute, ast.Subscript)):
            root = target.value
            while isinstance(root, (ast.Attribute, ast.Subscript)):
                root = root.value
            return isinstance(root, ast.Name) and root.id == result_name
        return False

    result_rebindings = [
        node
        for node in ast.walk(execute_publication)
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr))
        and any(
            writes_result(target)
            for target in (
                tuple(node.targets) if isinstance(node, ast.Assign) else (node.target,)
            )
        )
        and node is not (execute_assignments[0][1] if execute_assignments else None)
    ]
    allowed_recovery_rebind = (
        len(result_rebindings) == 1
        and isinstance(result_rebindings[0], ast.Assign)
        and isinstance(result_rebindings[0].value, ast.Name)
        and result_rebindings[0].value.id == "recovered"
        and any(
            isinstance(parent, ast.If)
            and result_rebindings[0] in parent.body
            and ast.unparse(parent.test) == "recovered is not None"
            for parent in ast.walk(execute_publication)
        )
        and any(
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "recovered"
                for target in node.targets
            )
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "complete_recovered"
            for node in ast.walk(execute_publication)
        )
    )

    def result_inequality(value: ast.AST, field: str, expected: str) -> bool:
        return (
            isinstance(value, ast.Compare)
            and isinstance(value.left, ast.Attribute)
            and isinstance(value.left.value, ast.Name)
            and value.left.value.id == result_name
            and value.left.attr == field
            and len(value.ops) == 1
            and isinstance(value.ops[0], ast.NotEq)
            and len(value.comparators) == 1
            and (
                isinstance(value.comparators[0], ast.Constant)
                and value.comparators[0].value == expected
                or expected == "success"
                and ast.unparse(value.comparators[0]) == "TerminalReason.SUCCESS.value"
            )
        )

    def rejects_noncommitted(statement: ast.stmt) -> bool:
        return (
            isinstance(statement, ast.If)
            and isinstance(statement.test, ast.BoolOp)
            and isinstance(statement.test.op, ast.Or)
            and len(statement.test.values) == 2
            and {
                field
                for field, expected in (
                    ("status", "committed"),
                    ("reason", "success"),
                )
                if any(
                    result_inequality(value, field, expected)
                    for value in statement.test.values
                )
            }
            == {"status", "reason"}
            and len(statement.body) == 1
            and isinstance(statement.body[0], ast.Return)
            and isinstance(statement.body[0].value, ast.Name)
            and statement.body[0].value.id == result_name
            and not statement.orelse
        )

    noncommitted_guard_indices = [
        index
        for index, statement in enumerate(execute_publication.body)
        if rejects_noncommitted(statement)
    ]
    preguard_result_calls = [
        node
        for index, statement in enumerate(execute_publication.body)
        if execute_assignments
        and noncommitted_guard_indices
        and execute_assignments[0][0] < index < noncommitted_guard_indices[0]
        for node in ast.walk(statement)
        if isinstance(node, ast.Call)
        and any(
            isinstance(descendant, ast.Name) and descendant.id == result_name
            for descendant in ast.walk(node)
        )
    ]

    completion_uses_result = len(completion_statements) == 1 and any(
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Name)
        and statement.value.func.id == "complete"
        and len(statement.value.args) == 2
        and all(
            isinstance(argument, ast.Attribute)
            and isinstance(argument.value, ast.Name)
            and argument.value.id == result_name
            and argument.attr == field
            for argument, field in zip(
                statement.value.args, ("reservation", "settlement"), strict=True
            )
        )
        for statement in execute_publication.body[completion_statements[0]].body
    )
    all_completion_calls = [
        node
        for node in ast.walk(execute_publication)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "complete"
    ]
    indirect_precommit_publication = len(completion_statements) == 1 and any(
        reaches_workspace_publication(
            node.func.id
            if isinstance(node.func, ast.Name)
            else node.func.attr
            if isinstance(node.func, ast.Attribute)
            else "",
            set(),
        )
        for statement in execute_publication.body[: completion_statements[0]]
        for node in ast.walk(statement)
        if isinstance(node, ast.Call)
    )
    all_execute_calls = [
        node
        for node in ast.walk(execute_publication)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "execute"
    ]
    if len(all_execute_calls) != 1:
        raise ArchitectureViolation(
            "apex-research: qualification publication bypasses existing governance coordinator"
        )

    if (
        len(governance_assignments) != 1
        or len(execute_assignments) != 1
        or governance_assignments[0][0] >= execute_assignments[0][0]
        or action_contract_guards[0][0] >= governance_assignments[0][0]
        or governance_rebindings
        or len(completion_statements) != 1
        or execute_assignments[0][0] >= completion_statements[0]
        or not any(
            rejects_noncommitted(statement)
            and execute_assignments[0][0] < index < completion_statements[0]
            for index, statement in enumerate(execute_publication.body)
        )
        or preguard_result_calls
        or not completion_uses_result
        or len(all_completion_calls) != 1
        or indirect_precommit_publication
        or direct_workspace_publications
        or result_rebindings
        and not allowed_recovery_rebind
    ):
        raise ArchitectureViolation(
            "apex-research: qualification publication ordering is not governed and committed-first"
        )

    reader_models = {
        "_read_policy": "QualificationPolicy",
        "_read_decision": "QualificationDecision",
        "_read_held_evaluation": "QualificationEvaluation",
        "_read_retirement": "QualificationRetirement",
    }
    reader_publications = {
        "_read_policy": "_policy_publication",
        "_read_decision": "_decision_publication",
        "_read_held_evaluation": "_held_publication",
        "_read_retirement": "_retirement_publication",
    }
    for reader_name, model_name in reader_models.items():
        reader = functions.get(reader_name)
        if reader is None:
            raise ArchitectureViolation(
                f"apex-research: qualification lacks typed canonical readback {reader_name}"
            )

        lexical_assignments = [
            node
            for node in ast.walk(reader)
            if isinstance(
                node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr)
            )
        ]
        top_level_assignments: list[ast.Assign | ast.AnnAssign] = []
        for statement in reader.body:
            if isinstance(statement, (ast.Assign, ast.AnnAssign)):
                top_level_assignments.append(statement)
            elif isinstance(statement, ast.Try):
                top_level_assignments.extend(
                    item
                    for item in statement.body
                    if isinstance(item, (ast.Assign, ast.AnnAssign))
                )
        fetched_names: set[str] = set()
        envelope_names: set[str] = set()
        typed_name = ""
        typed_line = -1

        def exact_workspace_get_record(value: ast.AST) -> bool:
            return (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Attribute)
                and value.func.attr == "get_record"
                and (
                    isinstance(value.func.value, ast.Name)
                    and value.func.value.id == "workspace"
                    or isinstance(value.func.value, ast.Attribute)
                    and isinstance(value.func.value.value, ast.Name)
                    and value.func.value.value.id == "self"
                    and value.func.value.attr == "_workspace"
                )
            )

        def exact_envelope_expression(value: ast.AST, names: set[str]) -> bool:
            if isinstance(value, ast.Name):
                return value.id in names
            if not isinstance(value, ast.Call):
                return False
            call_name = (
                value.func.id
                if isinstance(value.func, ast.Name)
                else value.func.attr
                if isinstance(value.func, ast.Attribute)
                else ""
            )
            return call_name in {"as_mapping", "record_payload", "dumps"} and any(
                exact_envelope_expression(argument, names)
                for argument in value.args[:1]
            )

        for assignment in top_level_assignments:
            targets = (
                assignment.targets
                if isinstance(assignment, ast.Assign)
                else (assignment.target,)
            )
            names = {name for target in targets for name in bound_names(target)}
            value = assignment.value
            direct_fetch = exact_workspace_get_record(value)
            direct_mapping = (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id == "as_mapping"
                and bool(value.args)
                and (
                    exact_envelope_expression(
                        value.args[0], fetched_names | envelope_names
                    )
                    or exact_workspace_get_record(value.args[0])
                )
            )
            direct_model_parse = (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Attribute)
                and value.func.attr == "model_validate_json"
                and isinstance(value.func.value, ast.Name)
                and value.func.value.id == model_name
                and bool(value.args)
                and exact_envelope_expression(
                    value.args[0], fetched_names | envelope_names
                )
            )
            fetched_names.difference_update(names)
            envelope_names.difference_update(names)
            if direct_fetch:
                fetched_names.update(names)
                envelope_names.update(names)
            elif direct_mapping:
                envelope_names.update(names)
            if direct_model_parse and len(names) == 1:
                typed_name = next(iter(names))
                typed_line = assignment.lineno
        verify_statements = [
            statement
            for statement in reader.body
            if isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Name)
            and statement.value.func.id == "verify_publication"
        ]
        verified = len(verify_statements) == 1 and typed_name != ""
        if verified:
            verify_call = verify_statements[0].value
            expected_value = verify_call.args[1] if len(verify_call.args) >= 2 else None
            verified = (
                verify_call.lineno > typed_line
                and len(verify_call.args) >= 2
                and isinstance(verify_call.args[0], ast.Name)
                and verify_call.args[0].id in envelope_names
                and verify_call.args[0].id != typed_name
                and isinstance(expected_value, ast.Call)
                and isinstance(expected_value.func, ast.Name)
                and expected_value.func.id == reader_publications[reader_name]
                and bool(expected_value.args)
                and isinstance(expected_value.args[0], ast.Name)
                and expected_value.args[0].id == typed_name
            )
        returns = [
            statement for statement in reader.body if isinstance(statement, ast.Return)
        ]
        returns_verified = (
            len(returns) == 1
            and len([node for node in ast.walk(reader) if isinstance(node, ast.Return)])
            == 1
            and isinstance(returns[0].value, ast.Name)
            and returns[0].value.id == typed_name
            and bool(verify_statements)
            and returns[0].lineno > verify_statements[0].lineno
            and not any(
                typed_name
                in {
                    name
                    for target in (
                        tuple(assignment.targets)
                        if isinstance(assignment, ast.Assign)
                        else (assignment.target,)
                    )
                    for name in bound_names(target)
                }
                and assignment.lineno > verify_statements[0].lineno
                for assignment in lexical_assignments
            )
        )
        protected_names = envelope_names | {typed_name}
        for assignment in sorted(
            lexical_assignments,
            key=lambda item: (
                getattr(item, "lineno", -1),
                getattr(item, "col_offset", -1),
            ),
        ):
            value = assignment.value
            targets = (
                tuple(assignment.targets)
                if isinstance(assignment, ast.Assign)
                else (assignment.target,)
            )
            if isinstance(value, ast.Name) and value.id in protected_names:
                protected_names.update(
                    name for target in targets for name in bound_names(target)
                )

        def protected_root(
            value: ast.AST, names: frozenset[str] = frozenset(protected_names)
        ) -> bool:
            while isinstance(value, (ast.Attribute, ast.Subscript)):
                value = value.value
            return isinstance(value, ast.Name) and value.id in names

        post_verify_mutation = bool(verify_statements) and any(
            getattr(node, "lineno", -1) > verify_statements[0].lineno
            and (
                isinstance(
                    node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr)
                )
                and any(
                    isinstance(target, (ast.Attribute, ast.Subscript))
                    and protected_root(target)
                    for target in (
                        tuple(node.targets)
                        if isinstance(node, ast.Assign)
                        else (node.target,)
                    )
                )
                or isinstance(node, ast.Delete)
                and any(protected_root(target) for target in node.targets)
                or isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and (
                    protected_root(node.func.value)
                    and node.func.attr
                    in {
                        "clear",
                        "pop",
                        "remove",
                        "update",
                        "append",
                        "extend",
                        "__setitem__",
                    }
                    or isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "object"
                    and node.func.attr == "__setattr__"
                    and bool(node.args)
                    and protected_root(node.args[0])
                )
            )
            for node in ast.walk(reader)
        )

        def helper_mutates_parameter(
            helper_name: str,
            parameter: str,
            seen: frozenset[tuple[str, str]] = frozenset(),
        ) -> bool:
            key = (helper_name, parameter)
            helper = functions.get(helper_name)
            if helper is None or key in seen:
                return False
            visited = seen | {key}

            def parameter_root(value: ast.AST) -> bool:
                while isinstance(value, (ast.Attribute, ast.Subscript)):
                    value = value.value
                return isinstance(value, ast.Name) and value.id == parameter

            for node in ast.walk(helper):
                if isinstance(
                    node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr)
                ) and any(
                    parameter_root(target)
                    for target in (
                        tuple(node.targets)
                        if isinstance(node, ast.Assign)
                        else (node.target,)
                    )
                ):
                    return True
                if not isinstance(node, ast.Call):
                    continue
                if (
                    isinstance(node.func, ast.Attribute)
                    and parameter_root(node.func.value)
                    and node.func.attr
                    in {
                        "clear",
                        "pop",
                        "remove",
                        "update",
                        "append",
                        "extend",
                        "__setitem__",
                    }
                    or isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "object"
                    and node.func.attr == "__setattr__"
                    and bool(node.args)
                    and parameter_root(node.args[0])
                ):
                    return True
                called = (
                    node.func.id
                    if isinstance(node.func, ast.Name)
                    else node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else ""
                )
                nested = functions.get(called)
                if nested is None:
                    continue
                for index, argument in enumerate(node.args):
                    if (
                        isinstance(argument, ast.Name)
                        and argument.id == parameter
                        and index < len(nested.args.args)
                        and helper_mutates_parameter(
                            called, nested.args.args[index].arg, visited
                        )
                    ):
                        return True
            return False

        post_verify_indirect_mutation = (
            bool(verify_statements)
            and bool(returns)
            and any(
                verify_statements[0].lineno
                < getattr(node, "lineno", -1)
                < returns[0].lineno
                and isinstance(node, ast.Call)
                and (
                    called := (
                        node.func.id
                        if isinstance(node.func, ast.Name)
                        else node.func.attr
                        if isinstance(node.func, ast.Attribute)
                        else ""
                    )
                )
                in functions
                and any(
                    isinstance(argument, ast.Name)
                    and argument.id in protected_names
                    and index < len(functions[called].args.args)
                    and helper_mutates_parameter(
                        called, functions[called].args.args[index].arg
                    )
                    for index, argument in enumerate(node.args)
                )
                for node in ast.walk(reader)
            )
        )
        protected_rebound = (
            any(
                assignment.lineno > typed_line
                and assignment.lineno != verify_statements[0].lineno
                and any(
                    bool(bound_names(target) & protected_names)
                    for target in (
                        tuple(assignment.targets)
                        if isinstance(assignment, ast.Assign)
                        else (assignment.target,)
                    )
                )
                for assignment in lexical_assignments
            )
            if verify_statements and typed_name
            else True
        )
        if (
            not envelope_names
            or not typed_name
            or not verified
            or not returns_verified
            or protected_rebound
            or post_verify_mutation
            or post_verify_indirect_mutation
        ):
            raise ArchitectureViolation(
                f"apex-research: qualification lacks typed canonical readback {reader_name}"
            )

    history_reader = classes["QualificationHistoryReader"]
    history_reader_methods = {
        node.name: node
        for node in history_reader.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    history_read = history_reader_methods.get("read")
    history_read_returns = (
        [node for node in history_read.body if isinstance(node, ast.Return)]
        if history_read is not None
        else []
    )
    history_function = functions.get("read_qualification_history")
    history_calls = (
        [node for node in ast.walk(history_function) if isinstance(node, ast.Call)]
        if history_function is not None
        else []
    )
    history_returns = (
        [node for node in history_function.body if isinstance(node, ast.Return)]
        if history_function is not None
        else []
    )
    history_result = history_returns[0].value if len(history_returns) == 1 else None
    history_keywords = (
        {
            item.arg: item.value
            for item in history_result.keywords
            if item.arg is not None
        }
        if isinstance(history_result, ast.Call)
        and isinstance(history_result.func, ast.Name)
        and history_result.func.id == "QualificationHistory"
        else {}
    )
    history_call_names = {
        node.func.id
        if isinstance(node.func, ast.Name)
        else node.func.attr
        if isinstance(node.func, ast.Attribute)
        else ""
        for node in history_calls
    }
    query_calls = [
        node
        for node in history_calls
        if isinstance(node.func, ast.Name)
        and node.func.id == "_query_lineage_records"
        and len(node.args) >= 2
        and ast.unparse(node.args[0]) == "workspace"
        and ast.unparse(node.args[1]) == "candidate"
    ]
    history_read_connected = (
        len(history_read_returns) == 1
        and isinstance(history_read_returns[0].value, ast.Call)
        and isinstance(history_read_returns[0].value.func, ast.Name)
        and history_read_returns[0].value.func.id == "read_qualification_history"
        and [ast.unparse(item) for item in history_read_returns[0].value.args]
        == ["self._workspace", "candidate"]
    )
    separated_history = (
        {"decisions", "held_evaluations"} <= set(history_keywords)
        and ast.unparse(history_keywords["decisions"])
        != ast.unparse(history_keywords["held_evaluations"])
        and {"_history_successors", "_held_for"} <= history_call_names
    )
    if (
        not history_read_connected
        or history_function is None
        or len(query_calls) != 1
        or not separated_history
    ):
        raise ArchitectureViolation(
            "apex-research: qualification history reader is disconnected from "
            "canonical state and held lineage"
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

    def reaches_lineage_query(function_name: str, seen: set[str]) -> bool:
        if function_name in seen or function_name not in functions:
            return False
        seen.add(function_name)
        for call in (
            node
            for node in ast.walk(functions[function_name])
            if isinstance(node, ast.Call)
        ):
            called = (
                call.func.id
                if isinstance(call.func, ast.Name)
                else call.func.attr
                if isinstance(call.func, ast.Attribute)
                else ""
            )
            if called == "query_lineage" or reaches_lineage_query(called, seen):
                return True
        return False

    indirect_lineage_queries = (
        [
            call
            for call in ast.walk(lineage_reader)
            if isinstance(call, ast.Call)
            and (
                called := (
                    call.func.id
                    if isinstance(call.func, ast.Name)
                    else call.func.attr
                    if isinstance(call.func, ast.Attribute)
                    else ""
                )
            )
            != "query_lineage"
            and reaches_lineage_query(called, set())
        ]
        if lineage_reader is not None
        else []
    )
    lineage_keywords = (
        {
            keyword.arg: keyword.value
            for keyword in lineage_call.keywords
            if keyword.arg is not None
        }
        if lineage_call is not None
        else {}
    )
    roots_argument = lineage_keywords.get("roots")
    relations_argument = lineage_keywords.get("relations")
    lineage_bound_to_root = (
        lineage_reader is not None
        and [argument.arg for argument in lineage_reader.args.args[:2]]
        == ["workspace", "root"]
        and roots_argument is not None
        and ast.unparse(roots_argument)
        == "({'kind': root.record_type, 'id': root.record_id},)"
        and isinstance(lineage_keywords.get("direction"), ast.Constant)
        and lineage_keywords["direction"].value == "descendants"
        and relations_argument is not None
        and ast.unparse(relations_argument)
        == "(relation,) if isinstance(relation, str) else relation"
        and isinstance(lineage_keywords.get("record_types"), ast.Name)
        and lineage_keywords["record_types"].id == "record_types"
    )
    lineage_loops = (
        [
            node
            for node in lineage_reader.body
            if isinstance(node, ast.While)
            and isinstance(node.test, ast.Constant)
            and node.test.value is True
        ]
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
            for index, node in enumerate(lineage_reader.body)
            if bounded_loop is not None
            and index < lineage_reader.body.index(bounded_loop)
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
        and len(node.body) == 1
        and isinstance(node.body[0], ast.Return)
        and isinstance(node.body[0].value, ast.Call)
        and isinstance(node.body[0].value.func, ast.Name)
        and node.body[0].value.func.id == "tuple"
        and len(node.body[0].value.args) == 1
        and isinstance(node.body[0].value.args[0], ast.Name)
        and node.body[0].value.args[0].id == "records"
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
    cursor_query_reused = (
        isinstance(lineage_keywords.get("cursor"), ast.Name)
        and lineage_keywords["cursor"].id == "cursor"
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

    def rejects_invalid_snapshot_token(test: ast.AST) -> bool:
        if not (
            isinstance(test, ast.BoolOp)
            and isinstance(test.op, ast.Or)
            and len(test.values) == 2
        ):
            return False
        checks = {ast.dump(value, include_attributes=False) for value in test.values}
        return checks == {
            ast.dump(
                ast.UnaryOp(
                    op=ast.Not(),
                    operand=ast.Call(
                        func=ast.Name(id="isinstance", ctx=ast.Load()),
                        args=[
                            ast.Name(id="page_token", ctx=ast.Load()),
                            ast.Name(id="str", ctx=ast.Load()),
                        ],
                        keywords=[],
                    ),
                ),
                include_attributes=False,
            ),
            ast.dump(
                ast.UnaryOp(
                    op=ast.Not(), operand=ast.Name(id="page_token", ctx=ast.Load())
                ),
                include_attributes=False,
            ),
        }

    token_validated = bounded_loop is not None and any(
        isinstance(node, ast.If)
        and token_position < index < drift_position
        and rejects_invalid_snapshot_token(node.test)
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
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "tuple"
        and len(node.value.args) == 1
        and isinstance(node.value.args[0], ast.Name)
        and node.value.args[0].id == "records"
        for node in ast.walk(bounded_loop)
    )
    page_records_assignments = (
        [
            (index, node)
            for index, node in enumerate(bounded_loop.body)
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "page_records"
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and isinstance(node.value.func.value, ast.Name)
            and node.value.func.value.id == "page"
            and node.value.func.attr == "get"
            and len(node.value.args) == 1
            and isinstance(node.value.args[0], ast.Constant)
            and node.value.args[0].value == "records"
        ]
        if bounded_loop is not None
        else []
    )
    record_loops = (
        [
            (index, node)
            for index, node in enumerate(bounded_loop.body)
            if isinstance(node, ast.For)
            and isinstance(node.target, ast.Name)
            and node.target.id == "value"
            and isinstance(node.iter, ast.Name)
            and node.iter.id == "page_records"
        ]
        if bounded_loop is not None
        else []
    )
    page_records_position = (
        page_records_assignments[0][0] if len(page_records_assignments) == 1 else -1
    )
    record_loop_position = record_loops[0][0] if len(record_loops) == 1 else -1
    page_records_type_guard = bounded_loop is not None and any(
        page_records_position < index < record_loop_position
        and isinstance(node, ast.If)
        and isinstance(node.test, ast.UnaryOp)
        and isinstance(node.test.op, ast.Not)
        and isinstance(node.test.operand, ast.Call)
        and isinstance(node.test.operand.func, ast.Name)
        and node.test.operand.func.id == "isinstance"
        and len(node.test.operand.args) == 2
        and isinstance(node.test.operand.args[0], ast.Name)
        and node.test.operand.args[0].id == "page_records"
        and isinstance(node.test.operand.args[1], ast.Name)
        and node.test.operand.args[1].id == "list"
        and any(isinstance(item, ast.Raise) for item in node.body)
        for index, node in enumerate(bounded_loop.body)
    )
    record_loop_valid = False
    if len(record_loops) == 1:
        record_loop = record_loops[0][1]
        publication_assignments = [
            (index, node)
            for index, node in enumerate(record_loop.body)
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "publication"
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "as_mapping"
            and any(
                isinstance(argument, ast.Name) and argument.id == "value"
                for argument in node.value.args
            )
        ]
        payload_positions = [
            index
            for index, node in enumerate(record_loop.body)
            if isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "record_payload"
            and len(node.value.args) == 1
            and isinstance(node.value.args[0], ast.Name)
            and node.value.args[0].id == "publication"
        ]
        append_positions = [
            index
            for index, node in enumerate(record_loop.body)
            if isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and isinstance(node.value.func.value, ast.Name)
            and node.value.func.value.id == "records"
            and node.value.func.attr == "append"
            and len(node.value.args) == 1
            and isinstance(node.value.args[0], ast.Name)
            and node.value.args[0].id == "publication"
        ]
        record_loop_valid = (
            len(publication_assignments) == 1
            and len(payload_positions) == 1
            and len(append_positions) == 1
            and publication_assignments[0][0]
            < payload_positions[0]
            < append_positions[0]
        )
    next_cursor_assignments = (
        [
            node
            for node in bounded_loop.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "next_cursor"
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and isinstance(node.value.func.value, ast.Name)
            and node.value.func.value.id == "page"
            and node.value.func.attr == "get"
            and len(node.value.args) == 1
            and isinstance(node.value.args[0], ast.Constant)
            and node.value.args[0].value == "next_cursor"
        ]
        if bounded_loop is not None
        else []
    )
    next_cursor_position = (
        bounded_loop.body.index(next_cursor_assignments[0])
        if bounded_loop is not None and len(next_cursor_assignments) == 1
        else -1
    )

    def invalid_cursor_term(value: ast.AST) -> bool:
        return (
            isinstance(value, ast.UnaryOp)
            and isinstance(value.op, ast.Not)
            and (
                isinstance(value.operand, ast.Name)
                and value.operand.id == "next_cursor"
                or isinstance(value.operand, ast.Call)
                and isinstance(value.operand.func, ast.Name)
                and value.operand.func.id == "isinstance"
                and len(value.operand.args) == 2
                and isinstance(value.operand.args[0], ast.Name)
                and value.operand.args[0].id == "next_cursor"
                and isinstance(value.operand.args[1], ast.Name)
                and value.operand.args[1].id == "str"
            )
        )

    next_cursor_type_guards = (
        [
            (index, node)
            for index, node in enumerate(bounded_loop.body)
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.BoolOp)
            and isinstance(node.test.op, ast.Or)
            and len(node.test.values) == 2
            and all(invalid_cursor_term(value) for value in node.test.values)
            and any(isinstance(item, ast.Raise) for item in node.body)
        ]
        if bounded_loop is not None
        else []
    )
    cursor_cycle_positions = (
        [
            index
            for index, node in enumerate(bounded_loop.body)
            if direct_guard(
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
        ]
        if bounded_loop is not None
        else []
    )
    cursor_record_positions = (
        [
            index
            for index, node in enumerate(bounded_loop.body)
            if isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and isinstance(node.value.func.value, ast.Name)
            and node.value.func.value.id == "seen_cursors"
            and node.value.func.attr == "add"
            and len(node.value.args) == 1
            and isinstance(node.value.args[0], ast.Name)
            and node.value.args[0].id == "next_cursor"
        ]
        if bounded_loop is not None
        else []
    )
    cursor_advance_positions = (
        [
            index
            for index, node in enumerate(bounded_loop.body)
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "cursor"
            and isinstance(node.value, ast.Name)
            and node.value.id == "next_cursor"
        ]
        if bounded_loop is not None
        else []
    )
    cursor_advances = bounded_loop is not None and any(
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "cursor"
        and isinstance(node.value, ast.Name)
        and node.value.id == "next_cursor"
        for node in bounded_loop.body
    )
    records_reset_in_loop = bounded_loop is not None and any(
        isinstance(node, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(target, ast.Name) and target.id == "records"
            for target in (
                node.targets if isinstance(node, ast.Assign) else (node.target,)
            )
        )
        for node in ast.walk(bounded_loop)
    )
    lineage_mutations = (
        tuple(ast.walk(lineage_reader)) if lineage_reader is not None else ()
    )

    def mutation_targets_name(node: ast.AST, name: str) -> bool:
        targets: tuple[ast.AST, ...] = ()
        if isinstance(node, ast.Assign):
            targets = tuple(node.targets)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
            targets = (node.target,)
        elif isinstance(node, ast.Delete):
            targets = tuple(node.targets)

        def contains_target(target: ast.AST) -> bool:
            if isinstance(target, ast.Name):
                return target.id == name
            if isinstance(target, (ast.Tuple, ast.List)):
                return any(contains_target(item) for item in target.elts)
            if isinstance(target, ast.Starred):
                return contains_target(target.value)
            if isinstance(target, (ast.Attribute, ast.Subscript)):
                return contains_target(target.value)
            return False

        return any(contains_target(target) for target in targets)

    mutation_counts = {
        name: sum(mutation_targets_name(node, name) for node in lineage_mutations)
        for name in ("page_count", "page_token", "snapshot_token", "cursor", "records")
    }
    record_aliases = {"records"}
    records_destructively_mutated = False
    for node in sorted(
        lineage_mutations,
        key=lambda item: (getattr(item, "lineno", -1), getattr(item, "col_offset", -1)),
    ):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = (
                tuple(node.targets) if isinstance(node, ast.Assign) else (node.target,)
            )
            target_names = {
                candidate.id
                for target in targets
                for candidate in ast.walk(target)
                if isinstance(candidate, ast.Name)
            }
            value = node.value
            derives_records = isinstance(value, ast.Name) and value.id in record_aliases
            record_aliases.difference_update(target_names - {"records"})
            if derives_records:
                record_aliases.update(target_names)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in record_aliases
            and node.func.attr
            in {
                "clear",
                "pop",
                "remove",
                "sort",
                "reverse",
                "__delitem__",
                "__setitem__",
            }
            or isinstance(node, ast.Delete)
            and any(mutation_targets_name(node, alias) for alias in record_aliases)
        ):
            records_destructively_mutated = True
    if (
        len(lineage_calls) != 1
        or indirect_lineage_queries
        or not lineage_bound_to_root
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
        or not cursor_query_reused
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
        or len(page_records_assignments) != 1
        or not page_records_type_guard
        or not record_loop_valid
        or len(next_cursor_assignments) != 1
        or len(next_cursor_type_guards) != 1
        or next_cursor_position >= next_cursor_type_guards[0][0]
        or len(cursor_cycle_positions) != 1
        or len(cursor_record_positions) != 1
        or len(cursor_advance_positions) != 1
        or not (
            next_cursor_type_guards[0][0]
            < cursor_cycle_positions[0]
            < cursor_record_positions[0]
            < cursor_advance_positions[0]
        )
        or not cursor_advances
        or records_reset_in_loop
        or mutation_counts
        != {
            "page_count": 2,
            "page_token": 1,
            "snapshot_token": 2,
            "cursor": 2,
            "records": 1,
        }
        or records_destructively_mutated
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
    state_mapping = {
        target.id: node.value.value
        for node in state_class.body
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    declared_state_members = {
        target.id
        for node in state_class.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        for target in (
            tuple(node.targets) if isinstance(node, ast.Assign) else (node.target,)
        )
        if isinstance(target, ast.Name) and not target.id.startswith("_")
    }
    expected_state_mapping = {
        "IDEA": "idea",
        "EXPERIMENTAL": "experimental",
        "FORMALLY_TESTED": "formally_tested",
        "RESEARCH_VALIDATED": "research_validated",
        "ROBUSTNESS_VALIDATED": "robustness_validated",
        "RESEARCH_QUALIFIED": "research_qualified",
        "RETIRED": "retired",
    }
    str_enum_base = any(
        isinstance(base, ast.Name)
        and base.id == "StrEnum"
        or isinstance(base, ast.Attribute)
        and base.attr == "StrEnum"
        for base in state_class.bases
    )
    state_tree = next(tree for _, tree in subsystem_trees if state_class in tree.body)
    str_enum_imported = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "enum"
        and any(
            alias.name == "StrEnum" and (alias.asname in {None, "StrEnum"})
            for alias in node.names
        )
        for node in state_tree.body
    )
    str_enum_rebound = any(
        isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "StrEnum"
        or isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign))
        and any(
            isinstance(target, ast.Name) and target.id == "StrEnum"
            for target in (
                tuple(node.targets) if isinstance(node, ast.Assign) else (node.target,)
            )
        )
        for node in state_tree.body
    )
    if (
        not str_enum_base
        or not str_enum_imported
        or str_enum_rebound
        or declared_state_members != set(expected_state_mapping)
        or state_mapping != expected_state_mapping
        or any(isinstance(node, ast.AnnAssign) for node in state_class.body)
    ):
        raise ArchitectureViolation(
            "apex-research: qualification maturity states drifted"
        )

    for class_name, expected_fields in required_fields.items():
        if not {"scope", "operational_authority"} <= expected_fields:
            continue
        semantic_defaults = {
            node.target.id: node.value.value
            for node in classes[class_name].body
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id in {"scope", "operational_authority"}
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        }
        if semantic_defaults != {
            "scope": "historical_research_maturity",
            "operational_authority": "forbidden",
        }:
            raise ArchitectureViolation(
                f"apex-research: {class_name} lacks historical maturity-only semantics"
            )
    relation_contracts = {
        "_held_publication": ("evaluation-of", "successor-of"),
        "_decision_publication": ("successor-of", "evaluation-of"),
        "_retirement_publication": ("successor-of", "evaluation-of"),
    }
    for function_name, (
        required_relation,
        forbidden_relation,
    ) in relation_contracts.items():
        function = functions.get(function_name)
        returns = (
            [node for node in function.body if isinstance(node, ast.Return)]
            if function is not None
            else []
        )
        returned_expression: ast.AST | None = (
            returns[0].value if len(returns) == 1 else None
        )
        if (
            isinstance(returned_expression, ast.Call)
            and returned_expression.args
            and isinstance(returned_expression.args[-1], ast.Name)
            and function is not None
        ):
            relation_name = returned_expression.args[-1].id
            relation_assignments = [
                node
                for node in function.body
                if isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name) and target.id == relation_name
                    for target in node.targets
                )
            ]
            returned_expression = (
                relation_assignments[0].value
                if len(relation_assignments) == 1
                else None
            )

        def constant_relation(value: ast.AST) -> str | None:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                return value.value
            if isinstance(value, ast.BinOp) and isinstance(value.op, ast.Add):
                left = constant_relation(value.left)
                right = constant_relation(value.right)
                if left is not None and right is not None:
                    return left + right
            return None

        returned_relations = (
            [
                (relation, node.elts[0])
                for node in ast.walk(returned_expression)
                if isinstance(node, (ast.Tuple, ast.List))
                and len(node.elts) >= 2
                and (relation := constant_relation(node.elts[1])) is not None
            ]
            if returned_expression is not None
            else []
        )
        required_sources = [
            source
            for relation, source in returned_relations
            if relation == required_relation
        ]

        parameter = function.args.args[0].arg if function is not None else ""
        predecessor_owner = {
            "_held_publication": None,
            "_decision_publication": "evaluation",
            "_retirement_publication": "request",
        }[function_name]
        canonical_sources = {
            (
                f"{parameter}.predecessor.record"
                if predecessor_owner is None
                else f"{parameter}.{predecessor_owner}.predecessor.record"
            )
        }
        if function is not None and predecessor_owner is not None:
            canonical_sources.update(
                f"{target.id}.predecessor.record"
                for assignment in function.body
                if isinstance(assignment, ast.Assign)
                and ast.unparse(assignment.value) == f"{parameter}.{predecessor_owner}"
                for target in assignment.targets
                if isinstance(target, ast.Name)
            )

        def exact_predecessor_record(
            value: ast.AST,
            expected_sources: frozenset[str] = frozenset(canonical_sources),
        ) -> bool:
            return ast.unparse(value) in expected_sources

        if (
            len(required_sources) != 1
            or not exact_predecessor_record(required_sources[0])
            or any(relation == forbidden_relation for relation, _ in returned_relations)
        ):
            raise ArchitectureViolation(
                f"apex-research: {function_name} qualification lineage relation is invalid"
            )
    field_names = {
        node.target.id
        for class_name, class_node in classes.items()
        if class_name.startswith("Qualification")
        and class_name
        not in {
            "QualificationEvaluator",
            "QualificationHistoryReader",
            "QualificationService",
        }
        and not class_name.endswith("Cursor")
        for node in class_node.body
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
    "QualificationHistory",
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
    "CandidateTruth",
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
                    if any(alias.name == "*" for alias in node.names):
                        qualification_symbols.update(SPEC015_PARALLEL_OWNER_CLASSES)
            module_aliases_changed = True

            def constant_module(value: ast.AST) -> str | None:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    return value.value
                if isinstance(value, ast.BinOp) and isinstance(value.op, ast.Add):
                    left = constant_module(value.left)
                    right = constant_module(value.right)
                    if left is not None and right is not None:
                        return left + right
                return None

            while module_aliases_changed:
                module_aliases_changed = False

                def assignment_pairs(
                    target: ast.AST, value: ast.AST
                ) -> tuple[tuple[ast.AST, ast.AST], ...]:
                    if (
                        isinstance(target, (ast.Tuple, ast.List))
                        and isinstance(value, (ast.Tuple, ast.List))
                        and len(target.elts) == len(value.elts)
                    ):
                        return tuple(
                            pair
                            for child_target, child_value in zip(
                                target.elts, value.elts, strict=True
                            )
                            for pair in assignment_pairs(child_target, child_value)
                        )
                    return ((target, value),)

                for node in ast.walk(tree):
                    if not (
                        isinstance(node, (ast.Assign, ast.AnnAssign))
                        and node.value is not None
                    ):
                        continue
                    targets = (
                        tuple(node.targets)
                        if isinstance(node, ast.Assign)
                        else (node.target,)
                    )
                    for target in targets:
                        for bound_target, bound_value in assignment_pairs(
                            target, node.value
                        ):
                            dynamic_qualification_module = (
                                isinstance(bound_value, ast.Call)
                                and (
                                    bound_value.func.id
                                    if isinstance(bound_value.func, ast.Name)
                                    else bound_value.func.attr
                                    if isinstance(bound_value.func, ast.Attribute)
                                    else ""
                                )
                                in {"__import__", "import_module"}
                                and bool(bound_value.args)
                                and constant_module(bound_value.args[0])
                                == "apex_research.qualification"
                            )
                            if not dynamic_qualification_module and not (
                                isinstance(bound_value, ast.Attribute)
                                and bound_value.attr == "qualification"
                                and isinstance(bound_value.value, ast.Name)
                                and bound_value.value.id in qualification_modules
                            ):
                                continue
                            if (
                                isinstance(bound_target, ast.Name)
                                and bound_target.id not in qualification_modules
                            ):
                                qualification_modules.add(bound_target.id)
                                module_aliases_changed = True
            owns_qualification = any(
                isinstance(node, ast.ClassDef)
                and (
                    node.name in SPEC015_PARALLEL_OWNER_CLASSES
                    or any(
                        isinstance(base, ast.Name)
                        and base.id in qualification_symbols
                        or isinstance(base, ast.Attribute)
                        and base.attr in SPEC015_PARALLEL_OWNER_CLASSES
                        and isinstance(base.value, ast.Name)
                        and base.value.id in qualification_modules
                        for base in node.bases
                    )
                    or any(
                        isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and item.name in SPEC015_OWNER_METHODS
                        for item in node.body
                    )
                )
                for node in ast.walk(tree)
            ) or any(
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name in SPEC015_OWNER_METHODS
                for node in tree.body
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

            def assigned_names(node: ast.AST) -> set[str]:
                if isinstance(node, ast.Name):
                    return {node.id}
                if isinstance(node, ast.Attribute):
                    return {ast.unparse(node), *assigned_names(node.value)}
                if isinstance(node, ast.Subscript):
                    return {ast.unparse(node), *assigned_names(node.value)}
                if isinstance(node, ast.Starred):
                    return assigned_names(node.value)
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

            def contains_direct_qualification(value: ast.AST) -> bool:
                if references_qualification_owner(value):
                    return True

                def constant_text(candidate: ast.AST) -> str | None:
                    if isinstance(candidate, ast.Constant) and isinstance(
                        candidate.value, str
                    ):
                        return candidate.value
                    if isinstance(candidate, ast.BinOp) and isinstance(
                        candidate.op, ast.Add
                    ):
                        left = constant_text(candidate.left)
                        right = constant_text(candidate.right)
                        if left is not None and right is not None:
                            return left + right
                    return None

                direct_text = constant_text(value)
                if direct_text is not None and direct_text.startswith(
                    "apex-research.qualification-"
                ):
                    return True
                return any(
                    (
                        isinstance(candidate, ast.Dict)
                        and any(
                            isinstance(key, ast.Constant)
                            and key.value in {"record_type", "schema_id"}
                            and (semantic_type := constant_text(item)) is not None
                            and semantic_type.startswith("apex-research.qualification-")
                            for key, item in zip(
                                candidate.keys, candidate.values, strict=True
                            )
                            if key is not None
                        )
                    )
                    or (
                        isinstance(candidate, ast.Call)
                        and isinstance(candidate.func, ast.Name)
                        and candidate.func.id == "dict"
                        and any(
                            item.arg in {"record_type", "schema_id"}
                            and (semantic_type := constant_text(item.value)) is not None
                            and semantic_type.startswith("apex-research.qualification-")
                            for item in candidate.keywords
                        )
                    )
                    for candidate in ast.walk(value)
                )

            functions_by_name: dict[
                str, list[ast.FunctionDef | ast.AsyncFunctionDef]
            ] = {}
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions_by_name.setdefault(node.name, []).append(node)

            def parameter_names(
                function: ast.FunctionDef | ast.AsyncFunctionDef,
            ) -> tuple[str, ...]:
                return tuple(
                    argument.arg
                    for argument in (
                        *function.args.posonlyargs,
                        *function.args.args,
                        *function.args.kwonlyargs,
                    )
                )

            def called_name(call: ast.Call) -> str:
                return (
                    call.func.id
                    if isinstance(call.func, ast.Name)
                    else call.func.attr
                    if isinstance(call.func, ast.Attribute)
                    else ""
                )

            def call_argument(
                call: ast.Call,
                function: ast.FunctionDef | ast.AsyncFunctionDef,
                parameter: str,
            ) -> ast.AST | None:
                parameters = parameter_names(function)
                if parameter in parameters:
                    index = parameters.index(parameter)
                    positional_count = len(function.args.posonlyargs) + len(
                        function.args.args
                    )
                    if index < positional_count and index < len(call.args):
                        return call.args[index]
                return next(
                    (
                        keyword.value
                        for keyword in call.keywords
                        if keyword.arg == parameter
                    ),
                    None,
                )

            helper_parameters: dict[str, set[str]] = {
                name: set() for name in functions_by_name
            }
            changed = True
            while changed:
                changed = False
                for name, candidates in functions_by_name.items():
                    for function in candidates:
                        parameters = set(parameter_names(function))
                        dependencies: dict[str, set[str]] = {
                            parameter: {parameter} for parameter in parameters
                        }
                        publication_aliases: set[str] = set()
                        helper_aliases: dict[str, str] = {}
                        sensitive: set[str] = set(helper_parameters[name])
                        for node in sorted(
                            (
                                item
                                for item in ast.walk(function)
                                if isinstance(
                                    item, (ast.Assign, ast.AnnAssign, ast.Call)
                                )
                            ),
                            key=lambda item: (item.lineno, item.col_offset),
                        ):
                            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                                aliases, value = assignment_parts(node)
                                value_dependencies = (
                                    {
                                        dependency
                                        for candidate in ast.walk(value)
                                        if isinstance(candidate, ast.Name)
                                        for dependency in dependencies.get(
                                            candidate.id, ()
                                        )
                                    }
                                    if value is not None
                                    else set()
                                )
                                for alias in aliases:
                                    dependencies.pop(alias, None)
                                    publication_aliases.discard(alias)
                                    helper_aliases.pop(alias, None)
                                if value_dependencies:
                                    for alias in aliases:
                                        dependencies[alias] = set(value_dependencies)
                                if value is not None and (
                                    isinstance(value, ast.Attribute)
                                    and value.attr == "publish_record"
                                    or isinstance(value, ast.Name)
                                    and value.id in publication_aliases
                                ):
                                    publication_aliases.update(aliases)
                                if value is not None and (
                                    isinstance(value, ast.Lambda)
                                    and any(
                                        isinstance(call, ast.Call)
                                        and isinstance(call.func, ast.Attribute)
                                        and call.func.attr == "publish_record"
                                        for call in ast.walk(value)
                                    )
                                    or isinstance(value, ast.Call)
                                    and (
                                        value.func.id
                                        if isinstance(value.func, ast.Name)
                                        else value.func.attr
                                        if isinstance(value.func, ast.Attribute)
                                        else ""
                                    )
                                    == "partial"
                                    and any(
                                        isinstance(argument, ast.Attribute)
                                        and argument.attr == "publish_record"
                                        for argument in value.args
                                    )
                                ):
                                    publication_aliases.update(aliases)
                                helper_name = (
                                    value.id
                                    if isinstance(value, ast.Name)
                                    else value.attr
                                    if isinstance(value, ast.Attribute)
                                    else ""
                                )
                                if helper_name in functions_by_name:
                                    for alias in aliases:
                                        helper_aliases[alias] = helper_name
                                continue
                            direct_publish = (
                                isinstance(node.func, ast.Attribute)
                                and node.func.attr == "publish_record"
                                or isinstance(node.func, ast.Name)
                                and node.func.id in publication_aliases
                            )
                            if direct_publish:
                                sensitive.update(
                                    dependency
                                    for argument in (
                                        *node.args,
                                        *(item.value for item in node.keywords),
                                    )
                                    for candidate in ast.walk(argument)
                                    if isinstance(candidate, ast.Name)
                                    for dependency in dependencies.get(candidate.id, ())
                                )
                            callee_name = helper_aliases.get(
                                called_name(node), called_name(node)
                            )
                            callees = functions_by_name.get(callee_name, ())
                            for callee in callees:
                                for parameter in helper_parameters[callee.name]:
                                    argument = call_argument(node, callee, parameter)
                                    if argument is None:
                                        continue
                                    sensitive.update(
                                        dependency
                                        for candidate in ast.walk(argument)
                                        if isinstance(candidate, ast.Name)
                                        for dependency in dependencies.get(
                                            candidate.id, ()
                                        )
                                    )
                        if not sensitive <= helper_parameters[name]:
                            helper_parameters[name].update(sensitive)
                            changed = True

            helper_returns_direct: set[str] = set()
            helper_return_parameters: dict[str, set[str]] = {
                name: set() for name in functions_by_name
            }
            returns_changed = True
            while returns_changed:
                returns_changed = False
                for name, candidates in functions_by_name.items():
                    direct = name in helper_returns_direct
                    parameters = set(helper_return_parameters[name])
                    for function in candidates:
                        function_parameters = set(parameter_names(function))
                        local_direct: set[str] = set()
                        ordered_nodes = sorted(
                            (
                                node
                                for node in ast.walk(function)
                                if isinstance(
                                    node, (ast.Assign, ast.AnnAssign, ast.Return)
                                )
                            ),
                            key=lambda item: (item.lineno, item.col_offset),
                        )
                        for returned in ordered_nodes:
                            if isinstance(returned, (ast.Assign, ast.AnnAssign)):
                                aliases, value = assignment_parts(returned)
                                local_direct.difference_update(aliases)
                                if value is not None and (
                                    contains_direct_qualification(value)
                                    or any(
                                        isinstance(node, ast.Name)
                                        and node.id in local_direct
                                        for node in ast.walk(value)
                                    )
                                    or any(
                                        isinstance(node, ast.Call)
                                        and called_name(node) in helper_returns_direct
                                        for node in ast.walk(value)
                                    )
                                ):
                                    local_direct.update(aliases)
                                continue
                            if returned.value is None:
                                continue
                            if contains_direct_qualification(returned.value) or any(
                                isinstance(node, ast.Name) and node.id in local_direct
                                for node in ast.walk(returned.value)
                            ):
                                direct = True
                            parameters.update(
                                node.id
                                for node in ast.walk(returned.value)
                                if isinstance(node, ast.Name)
                                and node.id in function_parameters
                            )
                            for call in (
                                node
                                for node in ast.walk(returned.value)
                                if isinstance(node, ast.Call)
                            ):
                                callee_name = called_name(call)
                                if callee_name in helper_returns_direct:
                                    direct = True
                                for callee in functions_by_name.get(callee_name, ()):
                                    for parameter in helper_return_parameters[
                                        callee.name
                                    ]:
                                        argument = call_argument(
                                            call, callee, parameter
                                        )
                                        if argument is not None:
                                            parameters.update(
                                                node.id
                                                for node in ast.walk(argument)
                                                if isinstance(node, ast.Name)
                                                and node.id in function_parameters
                                            )
                    if direct and name not in helper_returns_direct:
                        helper_returns_direct.add(name)
                        returns_changed = True
                    if not parameters <= helper_return_parameters[name]:
                        helper_return_parameters[name].update(parameters)
                        returns_changed = True

            publishes_qualification = False
            frozen_helper_returns = frozenset(helper_returns_direct)
            frozen_return_parameters = {
                name: set(parameters)
                for name, parameters in helper_return_parameters.items()
            }

            def scan_statements(
                statements: list[ast.stmt],
                qualification_values: set[str],
                publication_aliases: set[str],
                function_catalog: dict[
                    str, list[ast.FunctionDef | ast.AsyncFunctionDef]
                ],
                helper_catalog: dict[str, set[str]],
            ) -> tuple[set[str], set[str]]:
                nonlocal publishes_qualification
                callable_aliases: dict[str, str] = {}
                safe_publication_values: set[str] = set()

                def explicitly_non_owner_record(value: ast.AST) -> bool:
                    if isinstance(value, ast.Name):
                        return value.id in safe_publication_values
                    if not isinstance(value, ast.Dict):
                        return False
                    discriminators = [
                        item.value
                        for key, item in zip(value.keys, value.values, strict=True)
                        if isinstance(key, ast.Constant)
                        and key.value in {"record_type", "schema_id"}
                        and isinstance(item, ast.Constant)
                        and isinstance(item.value, str)
                    ]
                    return bool(discriminators) and all(
                        not item.startswith("apex-research.qualification-")
                        for item in discriminators
                    )

                def contains_qualification(
                    value: ast.AST,
                    direct_returns: frozenset[str] = frozen_helper_returns,  # noqa: B023
                    return_parameters: dict[str, set[str]] = frozen_return_parameters,  # noqa: B023
                ) -> bool:
                    if contains_direct_qualification(value):
                        return True
                    for call in (
                        node for node in ast.walk(value) if isinstance(node, ast.Call)
                    ):
                        callee_name = called_name(call)
                        if callee_name in direct_returns:
                            return True
                        for callee in function_catalog.get(callee_name, ()):
                            if any(
                                (argument := call_argument(call, callee, parameter))
                                is not None
                                and contains_qualification(argument)
                                for parameter in return_parameters[callee.name]
                            ):
                                return True
                    return any(
                        isinstance(candidate, ast.Name)
                        and candidate.id in qualification_values
                        or isinstance(candidate, ast.Attribute)
                        and ast.unparse(candidate) in qualification_values
                        or isinstance(candidate, ast.Subscript)
                        and ast.unparse(candidate) in qualification_values
                        for candidate in ast.walk(value)
                    )

                def assign_target(target: ast.AST, value: ast.AST | None) -> None:
                    aliases = assigned_names(target)
                    mutates_container = isinstance(
                        target, (ast.Attribute, ast.Subscript)
                    )
                    if not mutates_container:
                        qualification_values.difference_update(aliases)
                        publication_aliases.difference_update(aliases)
                        for alias in aliases:
                            callable_aliases.pop(alias, None)
                        safe_publication_values.difference_update(aliases)
                    assigns_qualification_discriminator = (
                        isinstance(target, ast.Subscript)
                        and isinstance(target.slice, ast.Constant)
                        and target.slice.value in {"record_type", "schema_id"}
                        and isinstance(value, ast.Constant)
                        and isinstance(value.value, str)
                        and value.value.startswith("apex-research.qualification-")
                    )
                    if value is not None and (
                        contains_qualification(value)
                        or assigns_qualification_discriminator
                    ):
                        qualification_values.update(aliases)
                    if assigns_qualification_discriminator:
                        safe_publication_values.difference_update(aliases)
                    if value is not None and explicitly_non_owner_record(value):
                        safe_publication_values.update(aliases)
                    if value is not None and (
                        isinstance(value, ast.Attribute)
                        and value.attr == "publish_record"
                        or isinstance(value, ast.Name)
                        and value.id in publication_aliases
                    ):
                        publication_aliases.update(aliases)
                    if value is not None and (
                        isinstance(value, ast.Lambda)
                        and any(
                            isinstance(call, ast.Call)
                            and isinstance(call.func, ast.Attribute)
                            and call.func.attr == "publish_record"
                            for call in ast.walk(value)
                        )
                        or isinstance(value, ast.Call)
                        and (
                            value.func.id
                            if isinstance(value.func, ast.Name)
                            else value.func.attr
                            if isinstance(value.func, ast.Attribute)
                            else ""
                        )
                        == "partial"
                        and any(
                            isinstance(argument, ast.Attribute)
                            and argument.attr == "publish_record"
                            for argument in value.args
                        )
                    ):
                        publication_aliases.update(aliases)
                    helper_name = (
                        value.id
                        if isinstance(value, ast.Name)
                        else value.attr
                        if isinstance(value, ast.Attribute)
                        else ""
                    )
                    if helper_name in function_catalog:
                        for alias in aliases:
                            callable_aliases[alias] = helper_name
                    if value is not None:
                        for expression in ast.walk(value):
                            if isinstance(expression, ast.NamedExpr):
                                assign_target(expression.target, expression.value)

                def inspect_calls(value: ast.AST) -> None:
                    nonlocal publishes_qualification
                    for call in (
                        node for node in ast.walk(value) if isinstance(node, ast.Call)
                    ):
                        arguments = (
                            *call.args,
                            *(item.value for item in call.keywords),
                        )
                        if (
                            isinstance(call.func, ast.Attribute)
                            and call.func.attr == "update"
                            and any(
                                contains_direct_qualification(argument)
                                for argument in arguments
                            )
                        ):
                            mutated = ast.unparse(call.func.value)
                            qualification_values.add(mutated)
                            safe_publication_values.discard(mutated)
                        direct_publish = (
                            isinstance(call.func, ast.Attribute)
                            and call.func.attr == "publish_record"
                            or isinstance(call.func, ast.Name)
                            and call.func.id in publication_aliases
                        )
                        if direct_publish and any(
                            contains_qualification(argument)
                            and not explicitly_non_owner_record(argument)
                            for argument in arguments
                        ):
                            publishes_qualification = True
                        resolved_callee = callable_aliases.get(
                            called_name(call), called_name(call)
                        )
                        for callee in function_catalog.get(resolved_callee, ()):
                            sensitive_call = False
                            for parameter in helper_catalog[callee.name]:
                                argument: ast.AST | None = None
                                if resolved_callee != called_name(call):
                                    parameters = parameter_names(callee)
                                    if (
                                        parameters
                                        and parameters[0] in {"self", "cls"}
                                        and parameter in parameters[1:]
                                    ):
                                        index = parameters[1:].index(parameter)
                                        if index < len(call.args):
                                            argument = call.args[index]
                                if argument is None:
                                    argument = call_argument(call, callee, parameter)
                                if argument is not None and contains_qualification(
                                    argument
                                ):
                                    sensitive_call = True
                                    break
                            if sensitive_call:
                                publishes_qualification = True

                for statement in statements:
                    if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        scan_statements(
                            statement.body,
                            set(qualification_values),
                            set(publication_aliases),
                            function_catalog,
                            helper_catalog,
                        )
                        continue
                    if isinstance(statement, ast.ClassDef):
                        continue
                    if isinstance(statement, ast.Try):
                        initial_qualification = set(qualification_values)
                        initial_publications = set(publication_aliases)
                        body_values, body_publications = scan_statements(
                            statement.body,
                            set(initial_qualification),
                            set(initial_publications),
                            function_catalog,
                            helper_catalog,
                        )
                        normal_values, normal_publications = scan_statements(
                            statement.orelse,
                            set(body_values),
                            set(body_publications),
                            function_catalog,
                            helper_catalog,
                        )
                        branch_results = [(normal_values, normal_publications)]
                        branch_results.extend(
                            scan_statements(
                                handler.body,
                                set(initial_qualification) | set(body_values),
                                set(initial_publications) | set(body_publications),
                                function_catalog,
                                helper_catalog,
                            )
                            for handler in statement.handlers
                        )
                        merged_values = set(initial_qualification)
                        merged_publications = set(initial_publications)
                        for branch_values, branch_publications in branch_results:
                            merged_values.update(branch_values)
                            merged_publications.update(branch_publications)
                        final_values, final_publications = scan_statements(
                            statement.finalbody,
                            merged_values,
                            merged_publications,
                            function_catalog,
                            helper_catalog,
                        )
                        qualification_values.clear()
                        qualification_values.update(final_values)
                        publication_aliases.clear()
                        publication_aliases.update(final_publications)
                        continue
                    inspect_calls(statement)
                    if isinstance(statement, ast.Assign):
                        for target in statement.targets:
                            if (
                                isinstance(target, (ast.Tuple, ast.List))
                                and isinstance(statement.value, (ast.Tuple, ast.List))
                                and len(target.elts) == len(statement.value.elts)
                            ):
                                for item, value in zip(
                                    target.elts, statement.value.elts, strict=True
                                ):
                                    assign_target(item, value)
                            else:
                                assign_target(target, statement.value)
                    elif isinstance(statement, ast.AnnAssign):
                        assign_target(statement.target, statement.value)
                    branches: list[list[ast.stmt]] = []
                    if isinstance(statement, ast.If):
                        branches = [statement.body, statement.orelse]
                    elif isinstance(statement, (ast.For, ast.While, ast.With)):
                        branches = [statement.body]
                        branches.extend(
                            [statement.orelse] if hasattr(statement, "orelse") else []
                        )
                    if branches:
                        branch_results = [
                            scan_statements(
                                branch,
                                set(qualification_values),
                                set(publication_aliases),
                                function_catalog,
                                helper_catalog,
                            )
                            for branch in branches
                        ]
                        qualification_values.clear()
                        publication_aliases.clear()
                        for branch_values, branch_aliases in branch_results:
                            qualification_values.update(branch_values)
                            publication_aliases.update(branch_aliases)
                return qualification_values, publication_aliases

            scan_statements(
                tree.body,
                set(qualification_symbols),
                set(),
                functions_by_name,
                helper_parameters,
            )
            for candidates in functions_by_name.values():
                for function in candidates:
                    scan_statements(
                        function.body,
                        set(),
                        set(),
                        functions_by_name,
                        helper_parameters,
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
    policy = validator.read_json(ROOT / "docs" / "architecture-constitution.v1.json")
    try:
        validator.validate_policy(policy)
        candidate = validator.read_json(
            ROOT / "docs" / "architecture-admissions" / "spec-015.v1.json"
        )
        validator.validate_candidate(candidate, policy)
        if candidate != SPEC015_ADMISSION_CONTRACT:
            raise validator.ConstitutionError(
                "SPEC-015 machine admission contract drifted"
            )
    except Exception as exc:
        raise ArchitectureViolation(
            f"quant-research: SPEC-015 architecture admission is invalid: {exc}"
        ) from exc


def run_fixture_checks(repository_root: Path) -> None:
    environment = HARNESS.sanitized_environment()
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


def _formatter_only_drift(exc: HARNESS.InstalledWheelFailure) -> bool:
    if exc.returncode != 1:
        return False
    output = str(exc).split("\n", 1)[-1].lstrip()
    try:
        payload, end = json.JSONDecoder().raw_decode(output)
    except json.JSONDecodeError:
        return False
    if output[end:].strip() or not isinstance(payload, list) or not payload:
        return False
    return all(
        isinstance(item, dict)
        and item.get("code") == "unformatted"
        and item.get("name") == "unformatted"
        and item.get("message") == "File would be reformatted"
        and item.get("severity") == "error"
        and isinstance(item.get("filename"), str)
        for item in payload
    )


def _pytest_terminal_counts(output: str) -> dict[str, int] | None:
    categories = "passed|skipped|failed|errors?|xfailed|xpassed|deselected|warnings?"
    summary = next(
        (
            line.strip().strip("=").strip()
            for line in reversed(output.splitlines())
            if re.fullmatch(
                rf"(?:=+\s*)?(?:\d+\s+(?:{categories}))"
                rf"(?:,\s*\d+\s+(?:{categories}))*"
                r"\s+in\s+\d+(?:\.\d+)?s(?:\s*=+)?",
                line.strip(),
            )
        ),
        None,
    )
    if summary is None:
        return None
    counts = {
        name: 0
        for name in (
            "passed",
            "skipped",
            "failed",
            "error",
            "xfailed",
            "xpassed",
            "deselected",
            "warning",
        )
    }
    for value, name in re.findall(rf"(\d+)\s+({categories})", summary):
        canonical = (
            "error"
            if name.startswith("error")
            else "warning"
            if name.startswith("warning")
            else name
        )
        counts[canonical] = int(value)
    return counts


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
                baseline_head = ""
                baseline_status = ""
                if baseline is not None:
                    try:
                        baseline_head = HARNESS.run_command(
                            ["git", "rev-parse", "HEAD"],
                            cwd=repository,
                            environment=environment,
                            timeout_seconds=30,
                        ).strip()
                        baseline_status = HARNESS.run_command(
                            ["git", "status", "--porcelain"],
                            cwd=repository,
                            environment=environment,
                            timeout_seconds=30,
                        ).strip()
                    except HARNESS.InstalledWheelFailure as probe_exc:
                        raise ArchitectureViolation(
                            f"{check.owner} baseline probe failed:\n{probe_exc}"
                        ) from probe_exc
                exact_baseline = (
                    baseline is not None
                    and baseline_head == baseline
                    and not baseline_status
                )
                formatter_only = _formatter_only_drift(exc)
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
            detail = str(exc)
            if detail.startswith("command could not start:"):
                status = "unavailable"
            elif detail.startswith("command timed out"):
                status = "timed-out"
            elif exc.returncode is not None:
                status = "failed"
            else:
                status = "indeterminate"
            statuses.append(
                {
                    "owner": check.owner,
                    "category": check.category,
                    "status": status,
                    "detail": detail,
                }
            )
        else:
            counts = _pytest_terminal_counts(output)
            passed = 0 if counts is None else counts["passed"] + counts["xpassed"]
            skipped = 0 if counts is None else counts["skipped"] + counts["xfailed"]
            if counts is None or (
                counts["failed"] or counts["error"] or not (passed or skipped)
            ):
                status = "indeterminate"
            elif passed and skipped:
                status = "partial"
            elif passed:
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
