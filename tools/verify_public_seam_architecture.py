"""Verify the QuantResearch architecture through existing public module seams."""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple


ROOT = Path(__file__).parents[1]


class ArchitectureViolation(ValueError):
    """A source tree violates the QuantResearch architecture constitution."""


class FixtureCheck(NamedTuple):
    owner: str
    repository: str
    command: tuple[str, ...]


class ApexSeamPolicy(NamedTuple):
    component: str
    forbidden_imports: tuple[tuple[str, str], ...]
    forbidden_calls: tuple[tuple[str, str], ...]
    forbidden_attributes: tuple[tuple[str, str], ...]
    required_classes: tuple[str, ...]
    required_names: tuple[str, ...]
    required_calls: tuple[str, ...]


def fixture_plan(_: Path) -> tuple[FixtureCheck, ...]:
    """Return public-seam fixture tests without creating shared state or evidence."""
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
            ),
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
FORBIDDEN_LIFECYCLE_TERMS = (
    "production approval",
    "live trading",
    "live-trading",
    "order routing",
    "position management",
)


def scan_sources(repository_root: Path) -> None:
    """Reject private cross-repository access and production-trading lifecycle claims."""
    for repository, rules in SOURCE_RULES.items():
        source_root = repository_root / repository / "src"
        if not source_root.is_dir():
            continue
        for path in source_root.rglob("*.py"):
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
            for term in FORBIDDEN_LIFECYCLE_TERMS:
                if term in source:
                    raise ArchitectureViolation(
                        f"{repository}: forbidden production-trading lifecycle term {term!r}: {path}"
                    )
    _scan_apex_governance_seams(repository_root / "apex-research" / "src" / "apex_research")
    _scan_rdagent_seams(repository_root / "apex-research")
    _scan_focused_loop_seams(repository_root / "apex-research")
    _scan_research_memory_seams(repository_root / "apex-research")
    _scan_validation_matrix_seams(repository_root / "apex-research")


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
    query_source = query_path.read_text(encoding="utf-8") if query_path.is_file() else ""
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
    imports = {
        alias.name
        for node in nodes
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or ""
        for node in nodes
        if isinstance(node, ast.ImportFrom)
    } | {
        f"{node.module}.{alias.name}"
        for node in nodes
        if isinstance(node, ast.ImportFrom) and node.module
        for alias in node.names
    }
    calls = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in nodes
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name))
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
            raise ArchitectureViolation(f"apex-research: RD-Agent adapter lacks {marker}: {adapter}")
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
                raise ArchitectureViolation(f"apex-research: RD-Agent {reason}: {strategy}")
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
        owns_process_control = "import subprocess" in source or "from subprocess" in source
        if owns_process_control and path not in allowed_process_seams:
            raise ArchitectureViolation(f"apex-research: ungoverned subprocess seam: {path}")
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
            raise ArchitectureViolation("apex-research: run submitted before Runtime preflight")
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
    specification = importlib.util.spec_from_file_location("constitution_validator", module_path)
    assert specification is not None and specification.loader is not None
    validator = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(validator)
    validator.validate_policy(validator.read_json(ROOT / "docs" / "architecture-constitution.v1.json"))


def run_fixture_checks(repository_root: Path) -> None:
    for check in fixture_plan(repository_root):
        repository = repository_root / check.repository
        if not repository.is_dir():
            raise ArchitectureViolation(f"fixture repository is unavailable: {repository}")
        completed = subprocess.run(check.command, cwd=repository, text=True, capture_output=True, check=False)
        if completed.returncode:
            detail = completed.stdout + completed.stderr
            raise ArchitectureViolation(f"{check.owner} public-seam fixture failed:\n{detail}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--run-fixtures", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        validate_constitution()
        scan_sources(arguments.repository_root)
        if arguments.run_fixtures:
            run_fixture_checks(arguments.repository_root)
    except ArchitectureViolation as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "fixtures": arguments.run_fixtures}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
