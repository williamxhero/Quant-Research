"""Verify the QuantResearch architecture through existing public module seams."""

from __future__ import annotations

import argparse
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
            external_adapter = any(
                marker in source
                for marker in (
                    "ResearchEnginePort",
                    "EmpiricalResearchPort",
                    "ResearchEngineAdapter",
                    "EmpiricalResearchAdapter",
                )
            )
            if external_adapter and not any(
                seam in source
                for seam in ("GovernedExternalResearchRunner", "ExternalResearchRunner")
            ):
                raise ArchitectureViolation(
                    f"apex-research: external adapter bypasses runner interface: {path}"
                )
            if external_adapter:
                forbidden_adapter_seams = (
                    ("import socket", "network"),
                    ("from socket", "network"),
                    ("import httpx", "network"),
                    ("import requests", "network"),
                    ("import urllib", "network"),
                    ("os.getenv", "host environment"),
                    ("os.environ", "host environment"),
                    ("register_package(", "package registration"),
                    ("submit_run(", "Runtime submission"),
                    ("orchestrator.advance(", "lifecycle"),
                    ("campaign-transition", "lifecycle"),
                    ("apex-research.decision", "decision"),
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
