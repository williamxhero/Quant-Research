from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "tools" / "verify_public_seam_architecture.py"
SPEC = importlib.util.spec_from_file_location("public_seam_verifier", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


class PublicSeamArchitectureTests(unittest.TestCase):
    def test_normal_constitution_validation_includes_the_spec015_admission(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            docs = root / "docs"
            admissions = docs / "architecture-admissions"
            admissions.mkdir(parents=True)
            tools = root / "tools"
            tools.mkdir()
            (tools / "validate_architecture_constitution.py").write_text(
                (ROOT / "tools/validate_architecture_constitution.py").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            policy = json.loads(
                (ROOT / "docs/architecture-constitution.v1.json").read_text(
                    encoding="utf-8"
                )
            )
            candidate = json.loads(
                (ROOT / "docs/architecture-admissions/spec-015.v1.json").read_text(
                    encoding="utf-8"
                )
            )
            candidate["public_seam"] = ""
            (docs / "architecture-constitution.v1.json").write_text(
                json.dumps(policy), encoding="utf-8"
            )
            (admissions / "spec-015.v1.json").write_text(
                json.dumps(candidate), encoding="utf-8"
            )

            with (
                mock.patch.object(verifier, "ROOT", root),
                self.assertRaisesRegex(
                    verifier.ArchitectureViolation,
                    "SPEC-015 architecture admission is invalid",
                ),
            ):
                verifier.validate_constitution()

    def test_spec015_admission_pins_the_complete_machine_contract(self) -> None:
        for field, replacement in (
            ("schema", "other-schema.v1"),
            ("spec", "SPEC-999"),
            ("canonical_owner", "strategy_reporting"),
            ("public_seam", "not-workspace"),
            ("identity_impact", "mutable current state"),
            ("evidence_level", "current production approval"),
            ("fail_closed_behavior", "allow"),
            ("compatibility", ["unrelated"]),
            ("claims", ["unrelated-claim"]),
            ("lifecycle_states", ["idea"]),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                docs = root / "docs"
                admissions = docs / "architecture-admissions"
                admissions.mkdir(parents=True)
                tools = root / "tools"
                tools.mkdir()
                (tools / "validate_architecture_constitution.py").write_text(
                    (ROOT / "tools/validate_architecture_constitution.py").read_text(
                        encoding="utf-8"
                    ),
                    encoding="utf-8",
                )
                (docs / "architecture-constitution.v1.json").write_text(
                    (ROOT / "docs/architecture-constitution.v1.json").read_text(
                        encoding="utf-8"
                    ),
                    encoding="utf-8",
                )
                candidate = json.loads(
                    (ROOT / "docs/architecture-admissions/spec-015.v1.json").read_text(
                        encoding="utf-8"
                    )
                )
                candidate[field] = replacement
                (admissions / "spec-015.v1.json").write_text(
                    json.dumps(candidate), encoding="utf-8"
                )

                with (
                    self.assertRaisesRegex(
                        verifier.ArchitectureViolation,
                        "SPEC-015 architecture admission is invalid",
                    ),
                    mock.patch.object(verifier, "ROOT", root),
                ):
                    verifier.validate_constitution()

    def test_fixture_plan_uses_only_existing_public_module_seams(self) -> None:
        plan = verifier.fixture_plan(ROOT)
        self.assertEqual(
            [item.owner for item in plan],
            [
                "strategy_workspace",
                "quant_runtime",
                "apex_research",
                "strategy_reporting",
                "spec014_installed_wheels",
                "spec015_installed_wheels",
            ],
        )
        command_by_owner = {item.owner: item.command[:5] for item in plan}
        self.assertEqual(
            command_by_owner["strategy_workspace"],
            ("uv", "run", "--extra", "dev", "pytest"),
        )
        self.assertEqual(
            command_by_owner["quant_runtime"],
            ("uv", "run", "--extra", "dev", "pytest"),
        )
        self.assertEqual(
            command_by_owner["apex_research"],
            ("uv", "run", "--group", "dev", "pytest"),
        )
        self.assertEqual(
            command_by_owner["strategy_reporting"],
            ("uv", "run", "--extra", "dev", "pytest"),
        )
        workspace = next(item for item in plan if item.owner == "strategy_workspace")
        runtime = next(item for item in plan if item.owner == "quant_runtime")
        self.assertIn(
            "tests/test_schemas_and_package.py::test_preflight_request_requires_verified_data_semantics",
            workspace.command,
        )
        self.assertIn(
            "tests/test_lineage_query.py::test_reusable_snapshot_freezes_cross_root_queries_and_allows_empty_typed_root",
            workspace.command,
        )
        self.assertIn(
            "tests/test_lineage_query.py::test_snapshot_token_tamper_store_and_cursor_mismatch_fail_closed",
            workspace.command,
        )
        self.assertIn("tests/test_preflight.py", runtime.command)
        self.assertIn("tests/test_preflight_run_order.py", runtime.command)
        self.assertIn("tests/test_cli_and_distribution.py", runtime.command)
        apex = next(item for item in plan if item.owner == "apex_research")
        self.assertIn(
            "tests/test_candidate_closure.py::test_semantic_deduplication_preserves_each_publication_lineage",
            apex.command,
        )
        self.assertIn("tests/test_governance_seams.py", apex.command)
        self.assertIn("tests/test_external_runner_governance.py", apex.command)
        self.assertIn("tests/test_external_runner_recovery.py", apex.command)
        self.assertIn("tests/test_research_engine_contract_matrix.py", apex.command)
        self.assertIn("tests/test_focused_loop_e2e.py", apex.command)
        self.assertIn("tests/test_focused_stop_resume.py", apex.command)
        self.assertIn("tests/test_memory_policy.py", apex.command)
        self.assertIn("tests/test_memory_records.py", apex.command)
        self.assertIn("tests/test_memory_query.py", apex.command)
        self.assertIn("tests/test_memory_orchestration.py", apex.command)
        self.assertIn("tests/test_validation_protocol.py", apex.command)
        self.assertIn("tests/test_validation_eligibility.py", apex.command)
        self.assertIn("tests/test_validation_execution.py", apex.command)
        self.assertIn("tests/test_validation_staging.py", apex.command)
        self.assertIn("tests/test_validation_evidence.py", apex.command)
        self.assertIn("tests/test_validation_reporting.py", apex.command)
        self.assertIn("tests/test_statistical_control.py", apex.command)
        self.assertIn("tests/test_evidence_v2.py", apex.command)
        self.assertIn("tests/test_qualification_policy.py", apex.command)
        self.assertIn("tests/test_qualification_evaluation.py", apex.command)
        self.assertIn("tests/test_qualification_validation.py", apex.command)
        self.assertIn("tests/test_qualification_robustness.py", apex.command)
        self.assertIn("tests/test_qualification_history.py", apex.command)
        self.assertIn("tests/test_qualification_cli.py", apex.command)
        reporting = next(item for item in plan if item.owner == "strategy_reporting")
        self.assertIn(
            "tests/test_research_reporting.py::test_validation_evidence_is_exactly_read_back_and_presented_without_recalculation",
            reporting.command,
        )
        self.assertIn(
            "tests/test_research_reporting.py::test_statistical_assessment_is_read_back_and_displayed_without_recalculation",
            reporting.command,
        )
        self.assertIn("tests/test_evidence_v2_read_model.py", reporting.command)
        installed = next(
            item for item in plan if item.owner == "spec014_installed_wheels"
        )
        self.assertEqual(installed.repository, ".")
        self.assertIn("tools/spec014_installed_wheel_tracer.py", installed.command)
        self.assertTrue((ROOT / "tools/spec014_installed_wheel_tracer.py").is_file())
        installed_015 = next(
            item for item in plan if item.owner == "spec015_installed_wheels"
        )
        self.assertEqual(installed_015.repository, ".")
        self.assertIn("tools/spec015_installed_wheel_tracer.py", installed_015.command)
        self.assertTrue((ROOT / "tools/spec015_installed_wheel_tracer.py").is_file())

    def test_spec014_installed_tracer_runs_complete_apex_flows_from_wheels(
        self,
    ) -> None:
        tracer = ROOT / "tools/spec014_installed_wheel_tracer.py"
        source = tracer.read_text(encoding="utf-8")

        completed = subprocess.run(
            [sys.executable, "-I", str(tracer), "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

        self.assertIn("tests/test_evidence_v2.py", source)
        self.assertIn(
            "test_governed_behavioral_gate_uses_runtime_conformance_without_live_engines",
            source,
        )
        self.assertIn(
            "test_source_round_trips_as_real_workspace_publication_envelope",
            source,
        )
        self.assertIn("test_real_workspace_client_publication_round_trip", source)
        self.assertIn("installed_acceptance_tests", source)
        self.assertIn("environment = sanitized_environment()", source)
        self.assertIn("run_installed_pytest(", source)
        self.assertIn("build_wheels", source)
        harness = (ROOT / "tools/installed_wheel_harness.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('["uv", "build", "--wheel"', harness)

    def test_spec015_installed_tracer_runs_the_golden_qualification_flow(self) -> None:
        tracer = ROOT / "tools/spec015_installed_wheel_tracer.py"
        completed = subprocess.run(
            [sys.executable, "-I", str(tracer), "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("--repository-root", completed.stdout)
        installed = next(
            item
            for item in verifier.fixture_plan(ROOT)
            if item.owner == "spec015_installed_wheels"
        )
        self.assertIn("tools/spec015_installed_wheel_tracer.py", installed.command)
        source = tracer.read_text(encoding="utf-8")
        for required in (
            "test_owner_publishes_a_frozen_historical_maturity_policy_through_governance",
            "test_validation_incomparability_remains_structurally_distinct",
            "test_held_evaluations_do_not_consume_the_one_successor_slot",
            "stable_behavioral_runs",
        ):
            self.assertIn(required, source)

    def test_full_gate_plan_covers_every_repository_gate_without_connected_fallback(
        self,
    ) -> None:
        plan = verifier.full_gate_plan(ROOT)
        owners = {item.owner for item in plan}

        self.assertEqual(
            owners,
            {
                "quant_research",
                "strategy_workspace",
                "quant_runtime",
                "apex_research",
                "strategy_reporting",
                "spec014_installed_wheels",
                "spec015_installed_wheels",
            },
        )
        commands = {token for item in plan for token in item.command}
        for required in ("format", "check", "mypy", "pytest", "build", "diff"):
            self.assertTrue(any(required in token for token in commands), required)
        self.assertTrue(all(not item.connected for item in plan))
        baseline_only = {
            item.owner
            for item in plan
            if item.category == "format" and item.baseline_only
        }
        self.assertEqual(
            baseline_only,
            {"strategy_workspace", "quant_runtime", "strategy_reporting"},
        )
        package_format_checks = (
            item
            for item in plan
            if item.category == "format" and item.repository != "."
        )
        self.assertTrue(
            all("--output-format" not in item.command for item in package_format_checks)
        )
        source_attestations = {
            (item.owner, item.category): item
            for item in plan
            if item.category in {"spec015-source-diff", "spec015-worktree-source-diff"}
        }
        self.assertEqual(
            set(source_attestations),
            {
                (owner, category)
                for owner in (
                    "strategy_workspace",
                    "quant_runtime",
                    "strategy_reporting",
                )
                for category in (
                    "spec015-source-diff",
                    "spec015-worktree-source-diff",
                )
            },
        )
        for (_owner, category), item in source_attestations.items():
            self.assertTrue(item.baseline_only)
            self.assertEqual(item.command[:3], ("git", "diff", "--quiet"))
            self.assertEqual(item.command[-2:], ("--", "src"))
            if category == "spec015-source-diff":
                self.assertEqual(item.command[-3], "HEAD")
                self.assertEqual(len(item.command), 7)
            else:
                self.assertEqual(item.command[3], "HEAD")
                self.assertEqual(len(item.command), 6)
        runtime_pytest = next(
            item
            for item in plan
            if item.owner == "quant_runtime" and item.category == "pytest"
        )
        reporting_pytest = next(
            item
            for item in plan
            if item.owner == "strategy_reporting" and item.category == "pytest"
        )
        self.assertIn("not connected", " ".join(runtime_pytest.command))
        self.assertIn("not connected", " ".join(reporting_pytest.command))
        root_checks = [item for item in plan if item.owner == "quant_research"]
        self.assertEqual(
            {item.category for item in root_checks},
            {"format", "lint", "pytest", "diff"},
        )
        root_tokens = {token for item in root_checks for token in item.command}
        for changed in (
            "tools/spec014_installed_wheel_tracer.py",
            "tools/test_validate_architecture_constitution.py",
            "tools/validate_architecture_constitution.py",
        ):
            self.assertIn(changed, root_tokens)

        root_pytest = next(item for item in root_checks if item.category == "pytest")
        self.assertIn(
            "tools/test_validate_architecture_constitution.py", root_pytest.command
        )
        self.assertEqual(
            root_pytest.command[:6],
            ("uv", "run", "--python", "3.12", "--with", "pytest"),
        )
        python_launches = [
            item.command
            for item in plan
            if item.owner
            in {
                "quant_research",
                "spec014_installed_wheels",
                "spec015_installed_wheels",
            }
            and item.category in {"pytest", "installed-wheel-smoke"}
        ]
        self.assertTrue(
            all(
                command[:4] == ("uv", "run", "--python", "3.12")
                for command in python_launches
            )
        )

    def test_connected_status_plan_keeps_each_external_dependency_independent(
        self,
    ) -> None:
        plan = verifier.connected_status_plan()

        self.assertEqual(
            {(item.owner, item.category) for item in plan},
            {
                ("quant_runtime", "connected-markethub"),
                ("quant_runtime", "connected-oci"),
                ("apex_research", "connected-external-validator"),
                ("strategy_reporting", "connected-reporting"),
            },
        )
        self.assertTrue(all(item.connected for item in plan))
        self.assertTrue(all("pytest" in item.command for item in plan))

    def test_connected_status_distinguishes_passed_partial_and_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repository"
            repository.mkdir()
            plan = tuple(
                verifier.GateCheck(
                    owner,
                    "repository",
                    category,
                    ("pytest",),
                    connected=True,
                )
                for owner, category in (
                    ("passed-owner", "passed"),
                    ("partial-owner", "partial"),
                    ("skipped-owner", "skipped"),
                )
            )
            with (
                mock.patch.object(verifier, "connected_status_plan", return_value=plan),
                mock.patch.object(
                    verifier.HARNESS,
                    "run_command",
                    side_effect=(
                        "2 passed, 1 warning in 1.0s\n",
                        "setup note: 99 passed\n1 passed, 1 deselected in 1.0s\n",
                        "1 skipped, 1 xfailed in 1.0s\n",
                    ),
                ),
            ):
                statuses = verifier.run_connected_status_checks(root)

        self.assertEqual(
            [item["status"] for item in statuses],
            ["passed", "passed", "skipped"],
        )

    def test_pytest_terminal_counts_accepts_all_terminal_summary_categories(
        self,
    ) -> None:
        counts = verifier._pytest_terminal_counts(
            "= 2 passed, 1 skipped, 3 xfailed, 1 xpassed, 4 deselected, "
            "2 warnings in 1.25s =\n"
        )

        self.assertIsNotNone(counts)
        assert counts is not None
        self.assertEqual(counts["passed"], 2)
        self.assertEqual(counts["xfailed"], 3)
        self.assertEqual(counts["xpassed"], 1)
        self.assertEqual(counts["deselected"], 4)
        self.assertEqual(counts["warning"], 2)

    def test_connected_status_distinguishes_launch_timeout_and_test_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "repository"
            repository.mkdir()
            plan = tuple(
                verifier.GateCheck(
                    owner,
                    "repository",
                    category,
                    ("pytest",),
                    connected=True,
                )
                for owner, category in (
                    ("unavailable-owner", "unavailable"),
                    ("timeout-owner", "timeout"),
                    ("failed-owner", "failed"),
                )
            )
            with (
                mock.patch.object(verifier, "connected_status_plan", return_value=plan),
                mock.patch.object(
                    verifier.HARNESS,
                    "run_command",
                    side_effect=(
                        verifier.HARNESS.InstalledWheelFailure(
                            "command could not start: pytest"
                        ),
                        verifier.HARNESS.InstalledWheelFailure(
                            "command timed out after 1s: pytest"
                        ),
                        verifier.HARNESS.InstalledWheelFailure(
                            "command failed (1): pytest", returncode=1
                        ),
                    ),
                ),
            ):
                statuses = verifier.run_connected_status_checks(root)

        self.assertEqual(
            [item["status"] for item in statuses],
            ["unavailable", "timed-out", "failed"],
        )

    def test_baseline_formatter_waiver_accepts_only_complete_formatter_output(
        self,
    ) -> None:
        baseline = verifier.UNCHANGED_REPOSITORY_BASELINES["strategy-workspace"]
        check = verifier.GateCheck(
            "strategy_workspace",
            "strategy-workspace",
            "format",
            ("ruff", "format", "--check", "."),
            baseline_only=True,
        )
        formatter_json = json.dumps(
            [
                {
                    "code": "unformatted",
                    "name": "unformatted",
                    "message": "File would be reformatted",
                    "severity": "error",
                    "filename": "src/example.py",
                }
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "strategy-workspace").mkdir()
            with (
                mock.patch.object(verifier, "full_gate_plan", return_value=(check,)),
                mock.patch.object(
                    verifier.HARNESS,
                    "run_command",
                    side_effect=(
                        verifier.HARNESS.InstalledWheelFailure(
                            "command failed (1): ruff format --check .\n"
                            + formatter_json,
                            returncode=1,
                        ),
                        baseline,
                        "",
                    ),
                ),
            ):
                drift = verifier.run_full_gate_checks(root)
            self.assertEqual(drift[0]["status"], "baseline-only-drift")

            with (
                mock.patch.object(verifier, "full_gate_plan", return_value=(check,)),
                mock.patch.object(
                    verifier.HARNESS,
                    "run_command",
                    side_effect=(
                        verifier.HARNESS.InstalledWheelFailure(
                            "command failed (1): ruff format --check .\n"
                            + formatter_json
                            + "\nwarning: unrelated configuration drift",
                            returncode=1,
                        ),
                        baseline,
                        "",
                    ),
                ),
                self.assertRaises(verifier.ArchitectureViolation),
            ):
                verifier.run_full_gate_checks(root)

    def test_baseline_probe_failure_is_wrapped_as_architecture_violation(self) -> None:
        check = verifier.GateCheck(
            "strategy_workspace",
            "strategy-workspace",
            "format",
            ("ruff", "format", "--check", "."),
            baseline_only=True,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "strategy-workspace").mkdir()
            with (
                mock.patch.object(verifier, "full_gate_plan", return_value=(check,)),
                mock.patch.object(
                    verifier.HARNESS,
                    "run_command",
                    side_effect=(
                        verifier.HARNESS.InstalledWheelFailure("format failed"),
                        verifier.HARNESS.InstalledWheelFailure("git unavailable"),
                    ),
                ),
                self.assertRaisesRegex(
                    verifier.ArchitectureViolation, "baseline probe failed"
                ),
            ):
                verifier.run_full_gate_checks(root)

    def test_spec014_source_guard_requires_public_evidence_and_reporting_seams(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            apex = root / "apex-research/src/apex_research"
            reporting = root / "strategy-reporting/src/strategy_reporting"
            apex.mkdir(parents=True)
            reporting.mkdir(parents=True)
            (apex / "evidence_v2.py").write_text(
                "class EvidenceV2: pass\n"
                "class EvidenceSection: pass\n"
                "class EvidenceSourceRef: pass\n"
                "class EvidenceV2Publisher: pass\n"
                "WorkspaceClientProtocol = object\n"
                "qualification_inference = 'forbidden'\n"
                "production_approval_inference = 'forbidden'\n"
                "def read(workspace):\n"
                "    workspace.get_record('id')\n"
                "    workspace.get_run('run')\n"
                "    workspace.get_result('run')\n"
                "    workspace.verify_artifact('uri')\n"
                "    workspace.query_lineage(snapshot_token='frozen')\n",
                encoding="utf-8",
            )
            (apex / "evidence_backfill.py").write_text(
                "class EvidenceV2BackfillService: pass\n"
                "class EvidenceV2StudySourcePublisher: pass\n"
                "max_depth = 4\n"
                "page_size = 100\n"
                "_BACKFILL_MAX_PAGES = 100\n"
                "seen_cursors = set()\n"
                "snapshot_token = 'frozen'\n"
                "def read(workspace):\n"
                "    workspace.query_lineage(snapshot_token=snapshot_token)\n"
                "    workspace.get_record('id')\n",
                encoding="utf-8",
            )
            (apex / "evidence_extensions.py").write_text(
                "class AuxiliaryValidationRecord: pass\n"
                "class FutureOptionalEvidenceRecord: pass\n"
                "qualification_inference = 'forbidden'\n"
                "production_approval_inference = 'forbidden'\n",
                encoding="utf-8",
            )
            (apex / "report_models.py").write_text(
                "class EvidenceV2StudySource: pass\n"
                "qualification_inference = 'forbidden'\n"
                "production_approval_inference = 'forbidden'\n",
                encoding="utf-8",
            )
            (reporting / "evidence_v2.py").write_text(
                "class EvidenceV2ReadModelBuilder: pass\n"
                "class EvidenceV2ReadModel: pass\n"
                "WorkspaceClientPort = object\n"
                "qualification_inference = 'forbidden'\n"
                "production_approval_inference = 'forbidden'\n"
                "def read(workspace):\n"
                "    workspace.get_record('id')\n"
                "    workspace.get_run('run')\n"
                "    workspace.get_result('run')\n"
                "    workspace.verify_artifact('uri')\n",
                encoding="utf-8",
            )

            verifier.scan_sources(root)

    def test_spec014_source_guard_rejects_parallel_truth_scans_and_masquerade(
        self,
    ) -> None:
        required = (
            "class EvidenceV2: pass\n"
            "class EvidenceSection: pass\n"
            "class EvidenceSourceRef: pass\n"
            "class EvidenceV2Publisher: pass\n"
            "WorkspaceClientProtocol = object\n"
            "qualification_inference = 'forbidden'\n"
            "production_approval_inference = 'forbidden'\n"
            "def read(workspace):\n"
            "    workspace.get_record('id')\n"
            "    workspace.get_run('run')\n"
            "    workspace.get_result('run')\n"
            "    workspace.verify_artifact('uri')\n"
            "    workspace.query_lineage(snapshot_token='frozen')\n"
        )
        forbidden = {
            "workspace.list_records(limit=10000)\n": "global record scan",
            "import sqlite3\n": "parallel state or evidence truth",
            "class CandidateRegistry: pass\n": "parallel owner",
            "class EvidenceTruth: pass\n": "parallel owner",
            "workspace.submit_run({})\n": "formal runner bypass",
            "qualification = 'passed'\n": "qualification masquerade",
            "production_approval = 'approved'\n": "production-approval masquerade",
        }
        for addition, reason in forbidden.items():
            with (
                self.subTest(reason=reason),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                apex = root / "apex-research/src/apex_research"
                apex.mkdir(parents=True)
                (apex / "evidence_v2.py").write_text(
                    required + addition, encoding="utf-8"
                )
                with self.assertRaisesRegex(verifier.ArchitectureViolation, reason):
                    verifier.scan_sources(root)

    def test_spec015_guard_accepts_only_the_scoped_apex_historical_maturity_seam(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            apex = root / "apex-research/src/apex_research"
            apex.mkdir(parents=True)
            (apex / "qualification.py").write_text(
                "from enum import StrEnum\n"
                "from apex_research.canonical import canonical_sha256\n"
                "from apex_research.evidence_workspace import verify_publication\n"
                "from apex_research.governance import ActionReservation, CampaignLedgerReader, GovernanceCoordinator, GovernedAction, ResourceKind, ResourceRef\n"
                "from apex_research.records import FrozenModel\n"
                "class CandidateRecordReader:\n"
                "    def __init__(self, workspace): pass\n"
                "    def read(self, value): return value\n"
                "class EvidenceV2Publisher:\n"
                "    def __init__(self, workspace): pass\n"
                "    def read(self, value): return value\n"
                "class QualificationState(StrEnum):\n"
                "    IDEA = 'idea'\n"
                "    EXPERIMENTAL = 'experimental'\n"
                "    FORMALLY_TESTED = 'formally_tested'\n"
                "    RESEARCH_VALIDATED = 'research_validated'\n"
                "    ROBUSTNESS_VALIDATED = 'robustness_validated'\n"
                "    RESEARCH_QUALIFIED = 'research_qualified'\n"
                "    RETIRED = 'retired'\n"
                "class QualificationPolicy(FrozenModel):\n"
                "    schema_id: str; policy_id: str; campaign: object; strategy_class: str; revision: int; transitions: tuple; scope: str = 'historical_research_maturity'; operational_authority: str = 'forbidden'; supersedes: object\n"
                "    @classmethod\n"
                "    def create(cls, **values):\n"
                "        identity={'schema': 'apex-research.qualification-policy.v1', **values}\n"
                "        return cls(policy_id=canonical_sha256(identity))\n"
                "class QualificationEvaluation(FrozenModel):\n"
                "    schema_id: str; evaluation_id: str; campaign: object; candidate: object; strategy_package: object; protocol: object; evidence: object; policy: object; predecessor: object; supersedes_qualification: object; from_state: object; to_state: object; requirements: tuple; blockers: tuple; disposition: str; reason: str; scope: str = 'historical_research_maturity'; operational_authority: str = 'forbidden'\n"
                "    @classmethod\n"
                "    def create(cls, **values):\n"
                "        identity={'schema': 'apex-research.qualification-evaluation.v1', **values}\n"
                "        return cls(evaluation_id=canonical_sha256(identity))\n"
                "class QualificationEvaluator:\n"
                "    def __init__(self, workspace): self._workspace = workspace\n"
                "    def evaluate(self, candidate, evidence):\n"
                "        CandidateRecordReader(self._workspace).read(candidate)\n"
                "        return EvidenceV2Publisher(self._workspace).read(evidence)\n"
                "class QualificationDecision(FrozenModel):\n"
                "    schema_id: str; decision_id: str; evaluation: object; governance: object; scope: str = 'historical_research_maturity'; operational_authority: str = 'forbidden'\n"
                "    @classmethod\n"
                "    def target_ref(cls, evaluation):\n"
                "        identity={'schema': 'apex-research.qualification-decision.v1', 'evaluation': evaluation, 'scope': 'historical_research_maturity', 'operational_authority': 'forbidden'}\n"
                "        return cls(record_id=canonical_sha256(identity))\n"
                "    @classmethod\n"
                "    def create(cls, evaluation): return cls(decision_id=cls.target_ref(evaluation).record_id)\n"
                "class QualificationRetirementRequest(FrozenModel):\n"
                "    schema_id: str; retirement_id: str; campaign: object; candidate: object; policy: object; evidence: object; predecessor: object; reason: str; scope: str = 'historical_research_maturity'; operational_authority: str = 'forbidden'\n"
                "    @classmethod\n"
                "    def create(cls, **values):\n"
                "        identity={'schema': 'apex-research.qualification-retirement-request.v1', **values}\n"
                "        return cls(retirement_id=canonical_sha256(identity))\n"
                "class QualificationRetirement(FrozenModel):\n"
                "    schema_id: str; retirement_id: str; request: object; governance: object\n"
                "class QualificationHistory(FrozenModel):\n"
                "    candidate: object; state: object; decisions: tuple; held_evaluations: tuple; retirement: object; scope: str = 'historical_research_maturity'; operational_authority: str = 'forbidden'\n"
                "class QualificationHistoryReader:\n"
                "    def __init__(self, workspace): self._workspace = workspace\n"
                "    def read(self, candidate): return read_qualification_history(self._workspace, candidate)\n"
                "class QualificationPageCursor:\n"
                "    current: str\n"
                "class QualificationService:\n"
                "    def publish_policy(self, policy, action): return self._execute_publication(action=action, campaign_id=policy.campaign.record_id, target=policy.ref(), idempotency_key=qualification_publication_idempotency_key(policy), preflight=lambda: None, complete=lambda *_: _publish_record(self._workspace))\n"
                "    def publish_decision(self, evaluation, action): return self._execute_publication(action=action, campaign_id=evaluation.campaign.record_id, target=evaluation.ref(), idempotency_key=qualification_publication_idempotency_key(evaluation), preflight=lambda: None, complete=lambda *_: _publish_record(self._workspace))\n"
                "    def publish_held_evaluation(self, evaluation, action): return self._execute_publication(action=action, campaign_id=evaluation.campaign.record_id, target=evaluation.ref(), idempotency_key=qualification_publication_idempotency_key(evaluation), preflight=lambda: None, complete=lambda *_: _publish_record(self._workspace))\n"
                "    def publish_retirement(self, request, action): return self._execute_publication(action=action, campaign_id=request.campaign.record_id, target=request.ref(), idempotency_key=qualification_publication_idempotency_key(request), preflight=lambda: None, complete=lambda *_: _publish_record(self._workspace))\n"
                "    def _execute_publication(self, *, action, campaign_id, target, idempotency_key, preflight, complete):\n"
                "        expected_resources = qualification_publication_scope(target)\n"
                "        if action.action is not GovernedAction.QUALIFICATION_PUBLICATION or action.campaign_id != campaign_id or action.resources != expected_resources or action.idempotency_key != idempotency_key: raise RuntimeError('scope')\n"
                "        def authorize(grant):\n"
                "            if grant.reservation.request != action: raise RuntimeError('grant')\n"
                "            preflight(); return target\n"
                "        governance = self._require_governance()\n"
                "        result = governance.execute(action, authorize)\n"
                "        if result.status != 'committed' or result.reason != 'success': return result\n"
                "        try: complete(result.reservation, result.settlement)\n"
                "        except Exception: return result\n"
                "        return result\n"
                "    def _require_governance(self) -> GovernanceCoordinator: return self._governance\n"
                "def qualification_publication_scope(reference): return (ResourceRef(kind=ResourceKind.QUALIFICATION_PUBLICATION, resource_id=reference.record_id, version=reference.record_type),)\n"
                "def qualification_publication_idempotency_key(value): return f'qualification-slot:{canonical_sha256(value)}'\n"
                "def _publish_record(workspace): workspace.publish_record({})\n"
                "def _policy_publication(value): return {'lineage': []}\n"
                "def _decision_publication(value): return {'lineage': [(value.evaluation.predecessor.record, 'successor-of')]}\n"
                "def _held_publication(value): return {'lineage': [(value.predecessor.record, 'evaluation-of')]}\n"
                "def _retirement_publication(value): return {'lineage': [(value.request.predecessor.record, 'successor-of')]}\n"
                "def read_qualification_history(workspace, candidate):\n"
                "    records = _query_lineage_records(workspace, candidate)\n"
                "    decisions = _history_successors(records)\n"
                "    held = _held_for(records)\n"
                "    return QualificationHistory(candidate=candidate, state=QualificationState.IDEA, decisions=tuple(decisions), held_evaluations=tuple(held), retirement=None)\n"
                "def _history_successors(records): return ()\n"
                "def _held_for(records): return ()\n"
                "def _read_policy(workspace):\n"
                "    raw=workspace.get_record('id')\n"
                "    value=QualificationPolicy.model_validate_json(raw)\n"
                "    verify_publication(raw, _policy_publication(value))\n"
                "    return value\n"
                "def _read_decision(workspace):\n"
                "    raw=workspace.get_record('id')\n"
                "    value=QualificationDecision.model_validate_json(raw)\n"
                "    verify_publication(raw, _decision_publication(value))\n"
                "    return value\n"
                "def _read_held_evaluation(workspace):\n"
                "    raw=workspace.get_record('id')\n"
                "    value=QualificationEvaluation.model_validate_json(raw)\n"
                "    verify_publication(raw, _held_publication(value))\n"
                "    return value\n"
                "def _read_retirement(workspace):\n"
                "    raw=workspace.get_record('id')\n"
                "    value=QualificationRetirement.model_validate_json(raw)\n"
                "    verify_publication(raw, _retirement_publication(value))\n"
                "    return value\n"
                "def _query_lineage_records(workspace, root, relation='successor-of', record_types=(), max_depth=1):\n"
                "    if not 1 <= max_depth <= 8: raise RuntimeError('bounded depth')\n"
                "    records=[]; seen_cursors=set(); page_count=0; cursor=None; snapshot_token=None\n"
                "    while True:\n"
                "        if page_count >= 100: raise RuntimeError('bounded')\n"
                "        page_count += 1\n"
                "        page=workspace.query_lineage(roots=({'kind': root.record_type, 'id': root.record_id},), direction='descendants', relations=(relation,) if isinstance(relation, str) else relation, record_types=record_types, max_depth=max_depth, page_size=100, cursor=cursor, snapshot_token=snapshot_token)\n"
                "        page_token=page.get('snapshot_token')\n"
                "        if not isinstance(page_token, str) or not page_token: raise RuntimeError('invalid token')\n"
                "        if snapshot_token is not None and page_token != snapshot_token: raise RuntimeError('drift')\n"
                "        snapshot_token=page_token\n"
                "        page_records=page.get('records')\n"
                "        if not isinstance(page_records, list): raise RuntimeError('invalid records')\n"
                "        if len(page_records) > 100: raise RuntimeError('oversized')\n"
                "        for value in page_records:\n"
                "            publication=as_mapping(value); record_payload(publication); records.append(publication)\n"
                "        next_cursor=page.get('next_cursor')\n"
                "        if next_cursor is None: return tuple(records)\n"
                "        if not isinstance(next_cursor, str) or not next_cursor: raise RuntimeError('invalid cursor')\n"
                "        if next_cursor in seen_cursors: raise RuntimeError('cycle')\n"
                "        seen_cursors.add(next_cursor)\n"
                "        cursor=next_cursor\n"
                "scope = 'historical_research_maturity'\n"
                "operational_authority = 'forbidden'\n"
                "EXPLANATION = 'Active and live are explicitly not granted here.'\n",
                encoding="utf-8",
            )
            (apex / "package_intake.py").write_text(
                "class StrategyPackageIntakeService:\n"
                "    def read(self, workspace): workspace.get_registered_package({})\n",
                encoding="utf-8",
            )
            (apex / "candidates.py").write_text(
                "def _verify_artifact(workspace): workspace.verify_artifact('uri')\n",
                encoding="utf-8",
            )

            verifier.scan_sources(root)

            qualification = apex / "qualification.py"
            accepted = qualification.read_text(encoding="utf-8")
            masked_policy = accepted.replace(
                "        return cls(policy_id=canonical_sha256(identity))",
                "        canonical_sha256(identity)\n"
                "        return cls(policy_id='nondeterministic')",
                1,
            )
            qualification.write_text(masked_policy, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "QualificationPolicy.create"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            forged_descendant = accepted.replace(
                "policy_id=canonical_sha256(identity)",
                "policy_id=(canonical_sha256(identity), 'forged')[1]",
            )
            qualification.write_text(forged_descendant, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "QualificationPolicy.create"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            for bypass, message in (
                (
                    accepted
                    + "\nAlias = QualificationService\nclass Mirror(Alias): pass\n",
                    "parallel qualification owner",
                ),
                (
                    accepted + "\ndef nested_owner():\n"
                    "    Alias = QualificationService\n"
                    "    class Mirror(Alias): pass\n",
                    "parallel qualification owner",
                ),
                (
                    accepted.replace(
                        "return cls(policy_id=canonical_sha256(identity))",
                        "return (cls(policy_id=canonical_sha256(identity)), "
                        "cls(policy_id='forged'))[1]",
                        1,
                    ),
                    "QualificationPolicy.create",
                ),
                (
                    accepted.replace(
                        "    verify_publication(raw, _policy_publication(value))\n"
                        "    return value\n",
                        "    verify_publication(raw, _policy_publication(value))\n"
                        "    object.__setattr__(value, 'policy_id', 'forged')\n"
                        "    return value\n",
                        1,
                    ),
                    "typed canonical readback _read_policy",
                ),
                (
                    accepted.replace(
                        "def _publish_record(workspace): workspace.publish_record({})",
                        "def _publish_record(workspace): workspace.mirror.publish_record({})\n"
                        "def _dead_workspace_publish(workspace): workspace.publish_record({})",
                    ),
                    "completion does not reach Workspace publication",
                ),
                (
                    accepted.replace(
                        "action.action is not GovernedAction.QUALIFICATION_PUBLICATION",
                        "action.action is not GovernedAction.UNRELATED",
                    ),
                    "action/resource contract is not exact",
                ),
                (
                    accepted.replace(
                        "campaign_id=policy.campaign.record_id",
                        "campaign_id='unrelated'",
                        1,
                    ),
                    "does not bind the governed publication contract",
                ),
                (
                    accepted.replace(
                        "idempotency_key=qualification_publication_idempotency_key(policy)",
                        "idempotency_key='fresh-retry-key'",
                        1,
                    ),
                    "does not bind the governed publication contract",
                ),
                (
                    accepted.replace(
                        "ResourceKind.QUALIFICATION_PUBLICATION",
                        "ResourceKind.UNRELATED",
                        1,
                    ),
                    "action/resource contract is not exact",
                ),
                (
                    accepted.replace(
                        "            if grant.reservation.request != action: raise RuntimeError('grant')\n",
                        "",
                        1,
                    ),
                    "grant must bind the exact action request",
                ),
                (
                    accepted.replace(
                        "            if grant.reservation.request != action: raise RuntimeError('grant')\n",
                        "            if grant.reservation.request != action:\n"
                        "                return target\n"
                        "                raise RuntimeError('grant')\n",
                        1,
                    ),
                    "grant must bind the exact action request",
                ),
                (
                    accepted.replace(
                        "from apex_research.canonical import canonical_sha256",
                        "def canonical_sha256(value): return 'id'",
                    ),
                    "integrity helpers must come directly",
                ),
                (
                    accepted.replace(
                        "from apex_research.evidence_workspace import verify_publication",
                        "def verify_publication(*values, **options): pass",
                    ),
                    "integrity helpers must come directly",
                ),
                (
                    accepted.replace(
                        "class QualificationPolicy(FrozenModel):",
                        "class QualificationPolicy:",
                    ),
                    "frozen strict owner record",
                ),
                (
                    accepted.replace(
                        "        expected_resources = qualification_publication_scope(target)\n",
                        "        GovernedAction = object()\n"
                        "        expected_resources = qualification_publication_scope(target)\n",
                        1,
                    ),
                    "governance types must come directly",
                ),
                (
                    accepted.replace(
                        "target=policy.ref(), idempotency_key=qualification_publication_idempotency_key(policy)",
                        "target=(_publish_record(self._workspace), policy.ref())[1], "
                        "idempotency_key=qualification_publication_idempotency_key(policy)",
                        1,
                    ),
                    "eagerly publishes before governance",
                ),
                (
                    accepted.replace(
                        "        governance = self._require_governance()\n",
                        "        governance = self._require_governance()\n"
                        "        governance = object()\n",
                        1,
                    ),
                    "existing governance coordinator",
                ),
                (
                    accepted.replace(
                        "        governance = self._require_governance()\n",
                        "        action = forged_action\n"
                        "        governance = self._require_governance()\n",
                        1,
                    ),
                    "action contract is rebound",
                ),
                (
                    accepted.replace(
                        "    raw=workspace.get_record('id')\n",
                        "    raw=mirror.get_record('id')\n",
                        1,
                    ),
                    "typed canonical readback _read_policy",
                ),
                (
                    accepted.replace(
                        "    verify_publication(raw, _policy_publication(value))\n",
                        "    verify_publication(raw, disguise(value))\n",
                        1,
                    )
                    + "\ndef disguise(value): return _policy_publication(value)\n",
                    "typed canonical readback _read_policy",
                ),
                (
                    accepted.replace(
                        "        expected_resources = qualification_publication_scope(target)\n"
                        "        if action.action is not GovernedAction.QUALIFICATION_PUBLICATION or action.campaign_id != campaign_id or action.resources != expected_resources or action.idempotency_key != idempotency_key: raise RuntimeError('scope')\n",
                        "        if False:\n"
                        "            expected_resources = qualification_publication_scope(target)\n"
                        "            if action.action is not GovernedAction.QUALIFICATION_PUBLICATION or action.campaign_id != campaign_id or action.resources != expected_resources or action.idempotency_key != idempotency_key: raise RuntimeError('scope')\n",
                    ),
                    "action/resource contract is not exact",
                ),
                (
                    accepted.replace(
                        "def _held_publication(value): return {'lineage': [(value.predecessor.record, 'evaluation-of')]}",
                        "def _held_publication(value): return {'lineage': [(value.predecessor.record, 'successor-of')]}",
                    ),
                    "lineage relation is invalid",
                ),
                (
                    accepted.replace(
                        "def _held_publication(value): return {'lineage': [(value.predecessor.record, 'evaluation-of')]}",
                        "def _held_publication(value): return {'lineage': [(value.predecessor.record, 'evaluation-of'), (value.predecessor.record, 'evaluation-of')]}",
                    ),
                    "lineage relation is invalid",
                ),
                (
                    accepted.replace(
                        "def _held_publication(value): return {'lineage': [(value.predecessor.record, 'evaluation-of')]}",
                        "def _held_publication(value): return {'lineage': [(value.predecessor.record, 'evaluation-of'), (value.predecessor.record, 'evaluation-' + 'of')]}",
                    ),
                    "lineage relation is invalid",
                ),
                (
                    accepted.replace(
                        "def _held_publication(value): return {'lineage': [(value.predecessor.record, 'evaluation-of')]}",
                        "def _held_publication(value): return {'lineage': [(value.candidate, 'evaluation-of')]}",
                    ),
                    "lineage relation is invalid",
                ),
                (
                    accepted.replace(
                        "def _held_publication(value): return {'lineage': [(value.predecessor.record, 'evaluation-of')]}",
                        "def _held_publication(value): return {'lineage': [(forged.predecessor.record, 'evaluation-of')]}",
                    ),
                    "lineage relation is invalid",
                ),
                (
                    accepted.replace(
                        "        result = governance.execute(action, authorize)\n",
                        "        result = governance.execute(action, authorize)\n"
                        "        mark_committed(result)\n",
                    )
                    + "\ndef mark_committed(result):\n"
                    "    result.status = 'committed'\n"
                    "    result.reason = 'success'\n",
                    "ordering is not governed and committed-first",
                ),
                (
                    accepted + "\nclass QualificationAuthority:\n    live: bool\n",
                    "non-historical authority fields",
                ),
                (
                    accepted.replace(
                        "scope: str = 'historical_research_maturity'",
                        "scope: str = 'current'",
                        1,
                    ),
                    "historical maturity-only semantics",
                ),
                (
                    accepted.replace(
                        "    def _execute_publication(self, *,",
                        "    def _execute_publication_missing(self, *,",
                    ),
                    "lacks _execute_publication",
                ),
                (
                    accepted.replace(
                        "    def read(self, candidate): return read_qualification_history(self._workspace, candidate)",
                        "    def read(self, candidate): return None",
                    ),
                    "history reader is disconnected",
                ),
                (
                    accepted.replace(
                        "roots=({'kind': root.record_type, 'id': root.record_id},)",
                        "roots=()",
                        1,
                    ),
                    "bounded snapshot pagination",
                ),
                (
                    accepted.replace(
                        "    def publish_decision(self, evaluation, action): return self._execute_publication(",
                        "    def publish_decision(self, evaluation, action):\n"
                        "        if evaluation: return _publish_record(self._workspace)\n"
                        "        return self._execute_publication(",
                        1,
                    ),
                    "bypasses governed qualification publication",
                ),
                (
                    accepted.replace(
                        "    def publish_policy(self, policy, action): return self._execute_publication(",
                        "    def publish_policy(self, policy, action):\n"
                        "        publish = self._workspace.publish_record\n"
                        "        publish({})\n"
                        "        return self._execute_publication(",
                        1,
                    ),
                    "workspace method alias",
                ),
                (
                    accepted.replace(
                        "    records=[]; seen_cursors=set(); page_count=0; cursor=None; snapshot_token=None\n",
                        "    global_scan = workspace.list_records\n"
                        "    global_scan(limit=10000)\n"
                        "    records=[]; seen_cursors=set(); page_count=0; cursor=None; snapshot_token=None\n",
                        1,
                    ),
                    "workspace method alias",
                ),
            ):
                qualification.write_text(bypass, encoding="utf-8")
                with self.assertRaisesRegex(verifier.ArchitectureViolation, message):
                    verifier._scan_spec015_qualification_seam(root / "apex-research")

            incomplete_identity = accepted.replace(
                "        identity={'schema': 'apex-research.qualification-policy.v1', **values}",
                "        identity={'schema': 'apex-research.qualification-policy.v1', "
                "'campaign': values['campaign']}",
                1,
            )
            qualification.write_text(incomplete_identity, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "canonical identity omits"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            substituted_identity = accepted.replace(
                "        identity={'schema': 'apex-research.qualification-policy.v1', **values}",
                "        identity={'schema': 'apex-research.qualification-policy.v1', "
                "**values, 'strategy_class': 'fixed'}",
                1,
            )
            qualification.write_text(substituted_identity, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "canonical identity"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            mutated_identity = accepted.replace(
                "        return cls(evaluation_id=canonical_sha256(identity))",
                "        identity['candidate'] = alternate_candidate\n"
                "        return cls(evaluation_id=canonical_sha256(identity))",
                1,
            )
            qualification.write_text(mutated_identity, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "canonical identity"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            opaque_identity = accepted.replace(
                "    def create(cls, **values):\n"
                "        identity={'schema': 'apex-research.qualification-policy.v1', **values}\n"
                "        return cls(policy_id=canonical_sha256(identity))",
                "    def create(cls, identity):\n"
                "        return cls(policy_id=canonical_sha256(identity))",
                1,
            )
            qualification.write_text(opaque_identity, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "canonical identity"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            nested_depth_guard = accepted.replace(
                "def _query_lineage_records(workspace, root, relation='successor-of', record_types=(), max_depth=1):\n"
                "    if not 1 <= max_depth <= 8: raise RuntimeError('bounded depth')\n",
                "def _query_lineage_records(workspace, root, relation='successor-of', record_types=(), max_depth=99):\n"
                "    def unused():\n"
                "        if not 1 <= max_depth <= 8: raise RuntimeError('bounded')\n",
            ).replace(
                "max_depth=1, page_size=100", "max_depth=max_depth, page_size=100"
            )
            qualification.write_text(nested_depth_guard, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "bounded snapshot pagination"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            dead_pagination_return = accepted.replace(
                "        if next_cursor is None: return tuple(records)\n",
                "        if next_cursor is None: break\n",
            ).replace(
                "scope = 'historical_research_maturity'",
                "    return tuple(records)\nscope = 'historical_research_maturity'",
            )
            qualification.write_text(dead_pagination_return, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "bounded snapshot pagination"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            masked = accepted.replace(
                "def create(cls, evaluation): return cls(decision_id=cls.target_ref(evaluation).record_id)",
                "def create(cls, evaluation): return cls(decision_id='nondeterministic')",
            )
            qualification.write_text(masked, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "QualificationDecision.create"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            unbounded = accepted.replace("page_size=100", "page_size=1000000")
            qualification.write_text(unbounded, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "bounded snapshot pagination"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            no_snapshot_guard = accepted.replace(
                "if snapshot_token is not None and page_token != snapshot_token: raise RuntimeError('drift')",
                "if False: raise RuntimeError('drift')",
            )
            qualification.write_text(no_snapshot_guard, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "bounded snapshot pagination"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            disconnected_readback = accepted.replace(
                "    raw=workspace.get_record('id')\n"
                "    value=QualificationPolicy.model_validate_json(raw)\n"
                "    verify_publication(raw, _policy_publication(value))\n",
                "    workspace.get_record('id')\n"
                "    value=QualificationPolicy.model_validate_json('{}')\n"
                "    verify_publication({}, _policy_publication(value))\n",
            )
            qualification.write_text(disconnected_readback, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "typed canonical readback _read_policy"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            early_readback = accepted.replace(
                "    verify_publication(raw, _policy_publication(value))\n",
                "    if raw: return value\n"
                "    verify_publication(raw, _policy_publication(value))\n",
                1,
            )
            qualification.write_text(early_readback, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "typed canonical readback _read_policy"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            overwritten_readback = accepted.replace(
                "    verify_publication(raw, _policy_publication(value))\n",
                "    raw={}\n    value={}\n"
                "    verify_publication(raw, _policy_publication(value))\n",
                1,
            )
            qualification.write_text(overwritten_readback, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "typed canonical readback _read_policy"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            no_cycle_guard = accepted.replace(
                "if next_cursor in seen_cursors: raise RuntimeError('cycle')",
                "if False: raise RuntimeError('cycle')",
            )
            qualification.write_text(no_cycle_guard, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "bounded snapshot pagination"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            malformed_cursor = accepted.replace(
                "        if not isinstance(next_cursor, str) or not next_cursor: raise RuntimeError('invalid cursor')\n",
                "        if False: raise RuntimeError('invalid cursor')\n",
            )
            qualification.write_text(malformed_cursor, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "bounded snapshot pagination"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            late_cursor_guard = accepted.replace(
                "        if not isinstance(next_cursor, str) or not next_cursor: raise RuntimeError('invalid cursor')\n"
                "        if next_cursor in seen_cursors: raise RuntimeError('cycle')\n",
                "        if next_cursor in seen_cursors: raise RuntimeError('cycle')\n"
                "        if not isinstance(next_cursor, str) or not next_cursor: raise RuntimeError('invalid cursor')\n",
            )
            qualification.write_text(late_cursor_guard, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "bounded snapshot pagination"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            dead_query = accepted.replace("    while True:\n", "    while False:\n", 1)
            qualification.write_text(dead_query, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "bounded snapshot pagination"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            no_token_validation = accepted.replace(
                "if not isinstance(page_token, str) or not page_token: raise RuntimeError('invalid token')",
                "if False: raise RuntimeError('invalid token')",
            )
            qualification.write_text(no_token_validation, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "bounded snapshot pagination"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            final_page_only = accepted.replace(
                "if next_cursor is None: return tuple(records)",
                "if next_cursor is None: return tuple(page_records)",
            )
            qualification.write_text(final_page_only, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "bounded snapshot pagination"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            enum_alias = accepted.replace(
                "    RETIRED = 'retired'\n",
                "    RETIRED = 'retired'\n    APPROVED = 'research_qualified'\n",
            )
            qualification.write_text(enum_alias, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "maturity states drifted"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            eager_completion = accepted.replace(
                "complete=lambda *_: _publish_record(self._workspace)",
                "complete=_publish_record(self._workspace)",
                1,
            )
            qualification.write_text(eager_completion, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "eagerly evaluates"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            eager_default = accepted.replace(
                "complete=lambda *_: _publish_record(self._workspace)",
                "complete=lambda eager=_publish_record(self._workspace): eager",
                1,
            )
            qualification.write_text(eager_default, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "eagerly evaluates"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            dead_identity = accepted.replace(
                "    def create(cls, **values):\n"
                "        identity={'schema': 'apex-research.qualification-policy.v1', **values}\n"
                "        return cls(policy_id=canonical_sha256(identity))",
                "    def create(cls, **values):\n"
                "        identity={'schema': 'apex-research.qualification-policy.v1', **values}\n"
                "        if False: return cls(policy_id=canonical_sha256(identity))\n"
                "        return cls(policy_id='forged')",
            )
            qualification.write_text(dead_identity, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "QualificationPolicy.create"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            ineffective_status_guard = accepted.replace(
                "if result.status != 'committed' or result.reason != 'success': return result",
                "if result.status != 'committed' and False: return result",
            )
            qualification.write_text(ineffective_status_guard, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "committed-first"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            dead_readback = accepted.replace(
                "    verify_publication(raw, _policy_publication(value))\n",
                "    if False: verify_publication(raw, _policy_publication(value))\n",
                1,
            )
            qualification.write_text(dead_readback, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "typed canonical readback _read_policy"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            discarded_readback = accepted.replace(
                "    return value\n", "    return {}\n", 1
            )
            qualification.write_text(discarded_readback, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "typed canonical readback _read_policy"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            for corrupted_readback in (
                accepted.replace(
                    "    verify_publication(raw, _policy_publication(value))\n",
                    "    verify_publication(value, _policy_publication(value))\n",
                    1,
                ),
                accepted.replace(
                    "    value=QualificationPolicy.model_validate_json(raw)\n",
                    "    value=(QualificationPolicy.model_validate_json(raw), {})[1]\n",
                    1,
                ),
                accepted.replace(
                    "    value=QualificationPolicy.model_validate_json(raw)\n",
                    "    value=QualificationPolicy.model_validate_json((raw, '{}')[1])\n",
                    1,
                ),
                accepted.replace(
                    "    verify_publication(raw, _policy_publication(value))\n",
                    "    verify_publication(raw, _policy_publication((value, object())[1]))\n",
                    1,
                ),
                accepted.replace(
                    "    verify_publication(raw, _policy_publication(value))\n",
                    "    verify_publication(raw, _policy_publication(value))\n"
                    "    if opaque: value={}\n",
                    1,
                ),
                accepted.replace(
                    "    verify_publication(raw, _policy_publication(value))\n",
                    "    raw, value = {}, object()\n"
                    "    verify_publication(raw, _policy_publication(value))\n",
                    1,
                ),
                accepted.replace(
                    "    verify_publication(raw, _policy_publication(value))\n",
                    "    verify_publication(raw, _policy_publication(value))\n"
                    "    mutate(value)\n",
                    1,
                )
                + "\ndef mutate(value): object.__setattr__(value, 'policy_id', 'forged')\n",
            ):
                qualification.write_text(corrupted_readback, encoding="utf-8")
                with self.assertRaisesRegex(
                    verifier.ArchitectureViolation,
                    "typed canonical readback _read_policy",
                ):
                    verifier._scan_spec015_qualification_seam(root / "apex-research")

            for premature_publication in (
                accepted.replace(
                    "def publish_policy(self, policy, action): return self._execute_publication(",
                    "def publish_policy(self, policy, action): "
                    "_publish_record(self._workspace); return self._execute_publication(",
                    1,
                ),
                accepted.replace(
                    "preflight=lambda: None, complete=",
                    "preflight=lambda: _publish_record(self._workspace), complete=",
                    1,
                ),
            ):
                qualification.write_text(premature_publication, encoding="utf-8")
                with self.assertRaisesRegex(
                    verifier.ArchitectureViolation, "publish|deferred phase"
                ):
                    verifier._scan_spec015_qualification_seam(root / "apex-research")

            forged_result = accepted.replace(
                "        if result.status != 'committed' or result.reason != 'success': return result\n",
                "        result=ForgedResult()\n"
                "        if result.status != 'committed' or result.reason != 'success': return result\n",
            )
            qualification.write_text(forged_result, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "committed-first"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            for forged_mutation in (
                "        result.status='committed'; result.reason='success'\n",
                "        (result,)=(ForgedResult(),)\n",
            ):
                source = accepted.replace(
                    "        if result.status != 'committed' or result.reason != 'success': return result\n",
                    forged_mutation
                    + "        if result.status != 'committed' or result.reason != 'success': return result\n",
                )
                qualification.write_text(source, encoding="utf-8")
                with self.assertRaisesRegex(
                    verifier.ArchitectureViolation, "committed-first"
                ):
                    verifier._scan_spec015_qualification_seam(root / "apex-research")

            named_eager_default = accepted.replace(
                "    def publish_policy(self, policy, action): return self._execute_publication(action=action, campaign_id=policy.campaign.record_id, target=policy.ref(), idempotency_key=qualification_publication_idempotency_key(policy), preflight=lambda: None, complete=lambda *_: _publish_record(self._workspace))\n",
                "    def publish_policy(self, policy, action):\n"
                "        def done(eager=_publish_record(self._workspace)): return eager\n"
                "        return self._execute_publication(action=action, campaign_id=policy.campaign.record_id, target=policy.ref(), idempotency_key=qualification_publication_idempotency_key(policy), preflight=lambda: None, complete=done)\n",
            )
            qualification.write_text(named_eager_default, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "eagerly evaluates"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            premature_complete = accepted.replace(
                "        result = governance.execute(action, authorize)\n",
                "        complete(None, None)\n"
                "        result = governance.execute(action, authorize)\n",
            )
            qualification.write_text(premature_complete, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "committed-first"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            wrong_cursor_input = accepted.replace(
                "page_size=100, cursor=cursor, snapshot_token=snapshot_token",
                "page_size=100, cursor=None, snapshot_token=snapshot_token",
            )
            qualification.write_text(wrong_cursor_input, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "bounded snapshot pagination"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            discarded_cursor = accepted.replace(
                "        cursor=next_cursor\n", "        cursor=None\n"
            )
            qualification.write_text(discarded_cursor, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "bounded snapshot pagination"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            reset_records = accepted.replace(
                "        page_records=page.get('records')\n",
                "        records=[]\n        page_records=page.get('records')\n",
            )
            qualification.write_text(reset_records, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "bounded snapshot pagination"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            for pagination_corruption in (
                accepted.replace(
                    "        page_count += 1\n",
                    "        page_count += 1\n        page_count=0\n",
                ),
                accepted.replace(
                    "if not isinstance(page_token, str) or not page_token: raise RuntimeError('invalid token')",
                    "if page_token is None: raise RuntimeError('invalid token')",
                ),
                accepted.replace(
                    "        snapshot_token=page_token\n",
                    "        snapshot_token=page_token\n        page_token='forged'\n",
                ),
                accepted.replace(
                    "        cursor=next_cursor\n",
                    "        cursor=next_cursor\n        cursor=None\n",
                ),
                accepted.replace(
                    "if next_cursor is None: return tuple(records)",
                    "if next_cursor is None: records.clear(); return tuple(records)",
                ),
                accepted.replace(
                    "if next_cursor is None: return tuple(records)",
                    "if next_cursor is None: return (records, page_records)[1]",
                ),
                accepted.replace(
                    "if next_cursor is None: return tuple(records)",
                    "if next_cursor is None: alias=records; alias.clear(); return tuple(records)",
                ),
                accepted.replace(
                    "        page_token=page.get('snapshot_token')\n",
                    "        page_token=page.get('snapshot_token')\n"
                    "        page_token, safe = ('forged', None)\n",
                ),
                accepted.replace(
                    "def _query_lineage_records(workspace, root, relation='successor-of', record_types=(), max_depth=1):\n",
                    "def _unbounded(workspace):\n"
                    "    return workspace.query_lineage(page_size=1000000)\n"
                    "def _query_lineage_records(workspace, root, relation='successor-of', record_types=(), max_depth=1):\n",
                ).replace(
                    "    records=[]; seen_cursors=set(); page_count=0; cursor=None; snapshot_token=None\n",
                    "    records=[]; records.extend(_unbounded(workspace)); "
                    "seen_cursors=set(); page_count=0; cursor=None; snapshot_token=None\n",
                ),
            ):
                qualification.write_text(pagination_corruption, encoding="utf-8")
                with (
                    self.subTest(pagination_corruption=pagination_corruption),
                    self.assertRaisesRegex(
                        verifier.ArchitectureViolation,
                        "bounded snapshot pagination",
                        msg=pagination_corruption,
                    ),
                ):
                    verifier._scan_spec015_qualification_seam(root / "apex-research")

            append_before_validation = accepted.replace(
                "publication=as_mapping(value); record_payload(publication); records.append(publication)",
                "publication=as_mapping(value); records.append(publication); record_payload(publication)",
            )
            qualification.write_text(append_before_validation, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "bounded snapshot pagination"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            no_enum_base = accepted.replace(
                "class QualificationState(StrEnum):", "class QualificationState:"
            )
            qualification.write_text(no_enum_base, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "maturity states drifted"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            annotated_enum = accepted.replace(
                "    RETIRED = 'retired'\n", "    RETIRED: str = 'retired'\n"
            )
            qualification.write_text(annotated_enum, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "maturity states drifted"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            fake_str_enum = accepted.replace(
                "from enum import StrEnum\n", "class StrEnum: pass\n"
            )
            qualification.write_text(fake_str_enum, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "maturity states drifted"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            extra_enum_member = accepted.replace(
                "    RETIRED = 'retired'\n",
                "    RETIRED = 'retired'\n    APPROVED = RESEARCH_QUALIFIED\n",
            )
            qualification.write_text(extra_enum_member, encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "maturity states drifted"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

            for rebound_owner in (
                "\nQualificationService = object\n",
                "\nQualificationService, safe = object, object\n",
                "\nfrom replacement import value as QualificationService\n",
                "\ndef QualificationPolicy(): pass\n",
                "\nclass MaturityCoordinator:\n    def publish_policy(self): pass\n",
            ):
                qualification.write_text(accepted + rebound_owner, encoding="utf-8")
                with self.assertRaisesRegex(
                    verifier.ArchitectureViolation,
                    "canonical owner is rebound|parallel qualification owner",
                ):
                    verifier._scan_spec015_qualification_seam(root / "apex-research")

            qualification.write_text(
                accepted + "\nclass _Helper: pass\n", encoding="utf-8"
            )
            (apex / "qualification_extra.py").write_text(
                "class _Helper: pass\n", encoding="utf-8"
            )
            verifier._scan_spec015_qualification_seam(root / "apex-research")
            (apex / "qualification_extra.py").unlink()

            for hidden_owner in (
                "\ndef hidden():\n    class QualificationPolicy: pass\n",
                (
                    "\nclass AlternateQualificationService:\n"
                    "    def publish_policy(self): pass\n"
                ),
                "\nclass Mirror(QualificationService): pass\n",
                "\nQualificationService = type('Mirror', (), {})\n",
                "\nclass Mirror:\n    publish_policy = lambda self: None\n",
                "\ndef publish_policy(): pass\n",
            ):
                qualification.write_text(accepted + hidden_owner, encoding="utf-8")
                with self.assertRaisesRegex(
                    verifier.ArchitectureViolation,
                    "parallel qualification owner|canonical owner is rebound",
                ):
                    verifier._scan_spec015_qualification_seam(root / "apex-research")

    def test_spec015_guard_rejects_parallel_qualification_owners(self) -> None:
        forbidden = (
            "QualificationLedger",
            "QualificationRegistry",
            "QualificationRunner",
            "QualificationBacktester",
            "QualificationArtifactStore",
            "QualificationEvidenceStore",
            "QualificationFormalEngine",
            "CandidateTruth",
            "MaturityLedger",
            "MaturityRegistry",
        )
        for class_name in forbidden:
            with (
                self.subTest(class_name=class_name),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                apex = root / "apex-research/src/apex_research"
                apex.mkdir(parents=True)
                (apex / "qualification.py").write_text(
                    "# qualification package marker\n",
                    encoding="utf-8",
                )
                (apex / "unrelated_owner.py").write_text(
                    f"class {class_name}: pass\n",
                    encoding="utf-8",
                )

                with self.assertRaisesRegex(
                    verifier.ArchitectureViolation, "parallel qualification owner"
                ):
                    verifier.scan_sources(root)

    def test_spec015_guard_rejects_qualification_ownership_outside_apex(self) -> None:
        for repository in ("strategy-workspace", "quant-runtime", "strategy-reporting"):
            with (
                self.subTest(repository=repository),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                source = root / repository / "src" / "owner.py"
                source.parent.mkdir(parents=True)
                source.write_text("class QualificationPolicy: pass\n", encoding="utf-8")
                with self.assertRaisesRegex(
                    verifier.ArchitectureViolation,
                    "ownership outside Apex Research",
                ):
                    verifier.scan_sources(root)

    def test_spec015_guard_rejects_every_non_owner_state_and_publication_symbol(
        self,
    ) -> None:
        forbidden = (
            "QualificationEvaluation",
            "QualificationRetirementRequest",
            "QualificationState",
            "QualificationSuccessorClaim",
            "QualificationPublisher",
            "QualificationStateStore",
            "ResearchQualificationPublisher",
            "CandidateTruth",
            "MaturityState",
            "MaturityService",
        )
        for symbol in forbidden:
            with (
                self.subTest(symbol=symbol),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                source = (
                    root / "strategy-reporting/src/strategy_reporting/qualification.py"
                )
                source.parent.mkdir(parents=True)
                source.write_text(f"class {symbol}: pass\n", encoding="utf-8")
                with self.assertRaisesRegex(
                    verifier.ArchitectureViolation, "ownership outside Apex Research"
                ):
                    verifier._scan_spec015_non_owner_repositories(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "quant-runtime/src/quant_runtime/qualification.py"
            source.parent.mkdir(parents=True)
            source.write_text("def publish_policy(): pass\n", encoding="utf-8")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "ownership outside Apex Research"
            ):
                verifier._scan_spec015_non_owner_repositories(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "strategy-workspace/src/strategy_workspace/maturity.py"
            source.parent.mkdir(parents=True)
            source.write_text(
                "class ResearchMaturityCoordinator:\n"
                "    def publish_policy(self): pass\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "ownership outside Apex Research"
            ):
                verifier._scan_spec015_non_owner_repositories(root)

        for case_index, source_text in enumerate(
            (
                (
                    "from apex_research import QualificationDecision\n"
                    "def save(workspace, value):\n"
                    "    publish = workspace.publish_record\n"
                    "    schema = QualificationDecision\n"
                    "    record = schema(value)\n"
                    "    publish(record)\n"
                ),
                (
                    "import apex_research as ar\n"
                    "def save(workspace, value):\n"
                    "    workspace.publish_record(ar.QualificationDecision(value))\n"
                ),
                (
                    "from apex_research import qualification as q\n"
                    "def save(workspace, value):\n"
                    "    record: object = q.QualificationDecision(value)\n"
                    "    workspace.publish_record(record)\n"
                ),
                (
                    "from apex_research import QualificationDecision\n"
                    "def relay(workspace, record): workspace.publish_record(record)\n"
                    "def save(workspace, value): relay(workspace, QualificationDecision(value))\n"
                ),
                (
                    "def save(workspace):\n"
                    "    payload={'record_type': 'apex-research.qualification-decision.v1'}\n"
                    "    workspace.publish_record(payload)\n"
                ),
                (
                    "def save(workspace, fields):\n"
                    "    workspace.publish_record(dict(record_type="
                    "'apex-research.qualification-decision.v1', **fields))\n"
                ),
                (
                    "def save(workspace):\n"
                    "    payload={}\n"
                    "    payload['record_type']='apex-research.qualification-decision.v1'\n"
                    "    workspace.publish_record(payload)\n"
                ),
                (
                    "def save(workspace):\n"
                    "    payload={'record_type': 'report-summary.v1', "
                    "'schema_id': 'apex-research.qualification-decision.v1'}\n"
                    "    workspace.publish_record(payload)\n"
                ),
                (
                    "def save(workspace):\n"
                    "    payload={'record_type': 'report-summary.v1'}\n"
                    "    payload['record_type']='apex-research.qualification-decision.v1'\n"
                    "    workspace.publish_record(payload)\n"
                ),
                (
                    "def save(workspace):\n"
                    "    payload={'record_type': 'report-summary.v1'}\n"
                    "    payload.update({'record_type': "
                    "'apex-research.qualification-decision.v1'})\n"
                    "    workspace.publish_record(payload)\n"
                ),
                (
                    "SCHEMA='apex-research.qualification-decision.v1'\n"
                    "def save(workspace):\n"
                    "    payload={'record_type': SCHEMA}\n"
                    "    workspace.publish_record(payload)\n"
                ),
                (
                    "from apex_research import QualificationDecision\n"
                    "def make(value):\n"
                    "    local=QualificationDecision(value)\n"
                    "    return local\n"
                    "def save(workspace, value): workspace.publish_record(make(value))\n"
                ),
                (
                    "from apex_research import QualificationDecision\n"
                    "def save(workspace, value):\n"
                    "    publication={}\n"
                    "    try:\n"
                    "        publication=QualificationDecision(value)\n"
                    "    finally:\n"
                    "        workspace.publish_record(publication)\n"
                ),
                (
                    "from apex_research import QualificationDecision\n"
                    "class Box: pass\n"
                    "def save(workspace, value):\n"
                    "    box=Box()\n"
                    "    box.payload: object = QualificationDecision(value)\n"
                    "    workspace.publish_record(box.payload)\n"
                ),
                (
                    "from apex_research import QualificationDecision\n"
                    "def save(workspace, value):\n"
                    "    safe, *records = ({}, QualificationDecision(value))\n"
                    "    workspace.publish_record(records)\n"
                ),
                (
                    "from apex_research import QualificationDecision\n"
                    "def outer(workspace, payload):\n"
                    "    def inner(*, publication):\n"
                    "        workspace.publish_record(publication)\n"
                    "    inner(publication=payload)\n"
                    "def save(workspace, value):\n"
                    "    outer(workspace, QualificationDecision(value))\n"
                ),
                (
                    "from apex_research import QualificationDecision\n"
                    "def final(workspace, payload): workspace.publish_record(payload)\n"
                    "def middle(workspace, payload): final(workspace, payload)\n"
                    "def save(workspace, value):\n"
                    "    middle(workspace, QualificationDecision(value))\n"
                ),
            )
        ):
            with (
                self.subTest(source_text=source_text),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                source = root / "strategy-reporting/src/strategy_reporting/publisher.py"
                source.parent.mkdir(parents=True)
                source.write_text(source_text, encoding="utf-8")
                with self.assertRaisesRegex(
                    verifier.ArchitectureViolation,
                    "ownership outside Apex Research",
                    msg=f"case {case_index}: {source_text}",
                ):
                    verifier._scan_spec015_non_owner_repositories(root)

    def test_source_scan_rejects_linked_python_before_following_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "quant-runtime/src/quant_runtime"
            external = root / "external"
            source_root.mkdir(parents=True)
            external.mkdir()
            (external / "injected.py").write_text("VALUE = 1\n", encoding="utf-8")
            try:
                (source_root / "linked").symlink_to(external, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory links unavailable: {exc}")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "symbolic link or junction"
            ):
                verifier.scan_sources(root)

    def test_source_scan_mocked_junction_detection_is_platform_independent(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "quant-runtime/src/quant_runtime"
            source_root.mkdir(parents=True)
            injected = source_root / "injected.py"
            injected.write_text("VALUE = 1\n", encoding="utf-8")
            original = Path.is_junction

            with (
                mock.patch.object(
                    Path,
                    "is_junction",
                    autospec=True,
                    side_effect=lambda path: path == injected or original(path),
                ),
                self.assertRaisesRegex(
                    verifier.ArchitectureViolation, "symbolic link or junction"
                ),
            ):
                verifier.scan_sources(root)

    def test_source_scan_rejects_a_linked_repository_ancestor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "quant-runtime"
            source_root = repository / "src/quant_runtime"
            source_root.mkdir(parents=True)
            (source_root / "injected.py").write_text("VALUE = 1\n", encoding="utf-8")
            original = Path.is_junction

            with (
                mock.patch.object(
                    Path,
                    "is_junction",
                    autospec=True,
                    side_effect=lambda path: path == repository or original(path),
                ),
                self.assertRaisesRegex(
                    verifier.ArchitectureViolation, "repository ancestor"
                ),
            ):
                verifier.scan_sources(root)

    def test_spec015_nonowner_publication_aliases_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "strategy-workspace/src/strategy_workspace/records.py"
            source.parent.mkdir(parents=True)
            source.write_text(
                "def save(workspace):\n"
                "    workspace.publish_record({'record_type': "
                "'apex-research.qualification-decision.v1'})\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "ownership outside Apex Research"
            ):
                verifier._scan_spec015_non_owner_repositories(root)

        for case_index, source_text in enumerate(
            (
                (
                    "import apex_research as ar\n"
                    "q = ar.qualification\n"
                    "def save(workspace, value):\n"
                    "    workspace.publish_record(q.QualificationDecision(value))\n"
                ),
                (
                    "import apex_research as ar\n"
                    "q, safe = ar.qualification, None\n"
                    "def save(workspace, value):\n"
                    "    workspace.publish_record(q.QualificationDecision(value))\n"
                ),
                (
                    "from apex_research import *\n"
                    "def save(workspace, value):\n"
                    "    workspace.publish_record(QualificationDecision(value))\n"
                ),
                (
                    "from apex_research import QualificationDecision\n"
                    "class Publisher:\n"
                    "    def relay(self, workspace, record):\n"
                    "        workspace.publish_record(record)\n"
                    "    def save(self, workspace, value):\n"
                    "        alias = self.relay\n"
                    "        alias(workspace, QualificationDecision(value))\n"
                ),
                (
                    "from apex_research import QualificationDecision\n"
                    "def save(workspace, value):\n"
                    "    record = QualificationDecision(value)\n"
                    "    def inner():\n"
                    "        workspace.publish_record(record)\n"
                    "    inner()\n"
                ),
                (
                    "from apex_research import QualificationDecision\n"
                    "def build(value):\n"
                    "    return QualificationDecision(value)\n"
                    "def save(workspace, value):\n"
                    "    workspace.publish_record(build(value))\n"
                ),
                (
                    "from apex_research import QualificationDecision\n"
                    "def publish_helper(workspace, record):\n"
                    "    workspace.publish_record(record)\n"
                    "def relay(workspace, record):\n"
                    "    sink = publish_helper\n"
                    "    sink(workspace, record)\n"
                    "def save(workspace, value):\n"
                    "    relay(workspace, QualificationDecision(value))\n"
                ),
                (
                    "from apex_research import QualificationDecision\n"
                    "def save(workspace, value):\n"
                    "    box = {}\n"
                    "    box['record'] = QualificationDecision(value)\n"
                    "    workspace.publish_record(box['record'])\n"
                ),
                (
                    "import importlib\n"
                    "q = importlib.import_module('apex_research.' + 'qualification')\n"
                    "def save(workspace, value):\n"
                    "    workspace.publish_record(q.QualificationDecision(value))\n"
                ),
                (
                    "def save(workspace):\n"
                    "    payload={'record_type': 'apex-research.' + "
                    "'qualification-decision.v1'}\n"
                    "    workspace.publish_record(payload)\n"
                ),
                (
                    "from apex_research import QualificationDecision\n"
                    "def save(workspace, value):\n"
                    "    sink=lambda record: workspace.publish_record(record)\n"
                    "    sink(QualificationDecision(value))\n"
                ),
                (
                    "from functools import partial\n"
                    "from apex_research import QualificationDecision\n"
                    "def save(workspace, value):\n"
                    "    sink=partial(workspace.publish_record)\n"
                    "    sink(QualificationDecision(value))\n"
                ),
            )
        ):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                source = root / "strategy-reporting/src/strategy_reporting/relay.py"
                source.parent.mkdir(parents=True)
                source.write_text(source_text, encoding="utf-8")
                with self.assertRaisesRegex(
                    verifier.ArchitectureViolation,
                    "ownership outside Apex Research",
                    msg=f"new case {case_index}: {source_text}",
                ):
                    verifier._scan_spec015_non_owner_repositories(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "strategy-reporting/src/strategy_reporting/publisher.py"
            source.parent.mkdir(parents=True)
            source.write_text(
                "import apex_research.qualification as q\n"
                "def save(workspace, value):\n"
                "    workspace.publish_record(q.QualificationDecision(value))\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "ownership outside Apex Research"
            ):
                verifier._scan_spec015_non_owner_repositories(root)

    def test_spec015_guard_allows_non_owner_read_models(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "strategy-reporting/src/strategy_reporting/qualification.py"
            source.parent.mkdir(parents=True)
            source.write_text("class QualificationReadModel: pass\n", encoding="utf-8")

            verifier._scan_spec015_non_owner_repositories(root)

        for safe_source in (
            (
                "def save(workspace):\n"
                "    workspace.publish_record({'record_type': 'report-summary.v1', "
                "'source_schema': 'apex-research.qualification-decision.v1', "
                "'scope': 'historical_research_maturity'})\n"
            ),
            (
                "from apex_research import QualificationDecision\n"
                "def save(workspace, value):\n"
                "    payload = {'record_type': 'report-summary.v1', "
                "'source': QualificationDecision(value)}\n"
                "    workspace.publish_record(payload)\n"
            ),
            (
                "from apex_research import QualificationDecision\n"
                "def save(workspace, value, flag):\n"
                "    record = QualificationDecision(value)\n"
                "    if flag:\n"
                "        record = {}\n"
                "    else:\n"
                "        record = {}\n"
                "    workspace.publish_record(record)\n"
            ),
        ):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                source = root / "strategy-reporting/src/strategy_reporting/safe.py"
                source.parent.mkdir(parents=True)
                source.write_text(safe_source, encoding="utf-8")
                verifier._scan_spec015_non_owner_repositories(root)

        for source_text in (
            (
                "from apex_research import QualificationDecision\n"
                "def save(workspace, value):\n"
                "    record=QualificationDecision(value)\n"
                "    record={}\n"
                "    workspace.publish_record(record)\n"
            ),
            (
                "from apex_research import QualificationDecision\n"
                "def save(workspace, value):\n"
                "    owned, safe=(QualificationDecision(value), {})\n"
                "    workspace.publish_record(safe)\n"
            ),
            (
                "from apex_research import QualificationDecision\n"
                "def save(workspace, value):\n"
                "    sink=workspace.publish_record\n"
                "    sink=lambda record: record\n"
                "    sink(QualificationDecision(value))\n"
            ),
        ):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                source = root / "strategy-reporting/src/strategy_reporting/safe.py"
                source.parent.mkdir(parents=True)
                source.write_text(source_text, encoding="utf-8")
                verifier._scan_spec015_non_owner_repositories(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "strategy-reporting/src/strategy_reporting/summary.py"
            source.parent.mkdir(parents=True)
            source.write_text("class QualificationSummary: pass\n", encoding="utf-8")

            verifier._scan_spec015_non_owner_repositories(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = (
                root
                / "strategy-workspace/src/strategy_workspace/qualification/cache.py"
            )
            source.parent.mkdir(parents=True)
            source.write_text(
                "def save(workspace): workspace.publish_record({})\n", encoding="utf-8"
            )
            verifier._scan_spec015_non_owner_repositories(root)

    def test_source_scan_allows_lifecycle_words_in_explanations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "quant-runtime/src/quant_runtime/explanation.py"
            source.parent.mkdir(parents=True)
            source.write_text(
                "# import apex_research and sqlite3 are forbidden implementation choices.\n"
                "MESSAGE = 'This does not grant production approval or live trading; "
                "do not import apex_research.'\n",
                encoding="utf-8",
            )

            verifier.scan_sources(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "quant-runtime/src/quant_runtime/dynamic_import.py"
            source.parent.mkdir(parents=True)
            source.write_text(
                "module = __import__('apex_' + 'research')\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "research orchestration"
            ):
                verifier.scan_sources(root)

    def test_spec015_guard_fails_closed_when_apex_owner_module_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "apex-research/src/apex_research").mkdir(parents=True)

            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "owner seam is missing"
            ):
                verifier._scan_spec015_qualification_seam(
                    root / "apex-research", required=True
                )

    def test_spec015_guard_requires_admission_independently_of_owner_module(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "docs").mkdir()
            (root / "docs/architecture-constitution.v1.json").write_text(
                "{}\n", encoding="utf-8"
            )
            (root / "apex-research/src/apex_research").mkdir(parents=True)

            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "architecture admission is missing"
            ):
                verifier.scan_sources(root)

    def test_spec015_guard_rejects_publication_bypassing_governance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            apex = root / "apex-research/src/apex_research"
            apex.mkdir(parents=True)
            source = (
                "from enum import StrEnum\n"
                "def canonical_sha256(value): return 'id'\n"
                "ActionReservation = object\n"
                "CampaignLedgerReader = object\n"
                "class GovernedAction: QUALIFICATION_PUBLICATION='qualification_publication'\n"
                "class QualificationState(StrEnum):\n"
                "    IDEA='idea'; EXPERIMENTAL='experimental'; "
                "FORMALLY_TESTED='formally_tested'; RESEARCH_VALIDATED='research_validated'; "
                "ROBUSTNESS_VALIDATED='robustness_validated'; "
                "RESEARCH_QUALIFIED='research_qualified'; RETIRED='retired'\n"
                "class QualificationPolicy: policy_id: str\n"
                "class QualificationEvaluation:\n"
                "    evaluation_id: str; policy: object; evidence: object; predecessor: object\n"
                "class QualificationEvaluator: pass\n"
                "class QualificationDecision:\n"
                "    decision_id: str; evaluation: object; governance_reservation: object; "
                "governance_settlement: object\n"
                "class QualificationRetirementRequest:\n"
                "    retirement_id: str; policy: object; evidence: object; predecessor: object\n"
                "class QualificationRetirement:\n"
                "    retirement_id: str; governance_reservation: object; "
                "governance_settlement: object\n"
                "class QualificationHistoryReader: pass\n"
                "class QualificationService:\n"
                "    def publish_policy(self): return self._workspace.publish_record({})\n"
                "    def publish_decision(self): return self._execute_publication()\n"
                "    def publish_held_evaluation(self): return self._execute_publication()\n"
                "    def publish_retirement(self): return self._execute_publication()\n"
                "    def _execute_publication(self):\n"
                "        self._governance.execute(None, None)\n"
                "        self._workspace.get_record('id')\n"
                "        self._workspace.query_lineage(roots=(), direction='descendants')\n"
                "        return canonical_sha256(GovernedAction.QUALIFICATION_PUBLICATION)\n"
                "scope='historical_research_maturity'\n"
                "authority='forbidden'\n"
                "held='evaluation-of'\n"
                "successor='successor-of'\n"
            )
            (apex / "qualification.py").write_text(source, encoding="utf-8")

            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "bypasses governed"
            ):
                verifier._scan_spec015_qualification_seam(root / "apex-research")

    def test_statistical_control_rejects_parallel_execution_and_truth(self) -> None:
        required = """
class StatisticalControlPolicy: pass
class TestFamily: pass
class CampaignTrialCensus: pass
class SelectionSnapshot: pass
class PurgeEmbargoEvaluator: pass
class RawPValueEvidence: pass
class MultipleTestingService: pass
class NautilusReturnArtifactReader: pass
class DeflatedSharpeService: pass
class StatisticalAssessment: pass
class StatisticalAssessmentService: pass
class StatisticalStudyReportPublisher: pass
WorkspaceClientProtocol = object
PublishedRecordRef = object
def use_public(workspace):
    workspace.get_record('id')
    workspace.verify_artifact('uri')
    workspace.read_artifact('uri')
"""
        forbidden = {
            "import sqlite3\n": "state or evidence truth",
            "import quant_runtime\n": "Runtime",
            "workspace.list_records(limit=10000)\n": "global record scan",
            "workspace.submit_run({})\n": "formal runner bypass",
            "import requests\n": "direct network",
        }
        for source_text, reason in forbidden.items():
            with (
                self.subTest(reason=reason),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                source = root / "apex-research/src/apex_research"
                source.mkdir(parents=True)
                (source / "statistical_control.py").write_text(
                    required + source_text, encoding="utf-8"
                )
                (source / "statistical_reporting.py").write_text("", encoding="utf-8")
                with self.assertRaisesRegex(verifier.ArchitectureViolation, reason):
                    verifier.scan_sources(root)

    def test_validation_matrix_rejects_parallel_truth_and_execution_bypasses(
        self,
    ) -> None:
        required = """
class ValidationProtocolMatrix: pass
class ValidationMatrixExpander: pass
class ValidationEligibilityService: pass
class ValidationCellExecutor: pass
class ValidationMatrixOrchestrator: pass
class ValidationEvidenceAggregator: pass
class ValidationReconciliationRequired: pass
WorkspaceClientProtocol = object
QuantRuntimeAdapter = object
GovernedAction.EXTERNAL_VALIDATION
GovernedAction.FORMAL_RUN
"""
        forbidden = {
            "import sqlite3\n": "parallel ledger",
            "import quant_runtime\n": "Runtime",
            "workspace.submit_run({})\n": "formal submission",
            "class ValidationRunner: pass\n": "parallel runner",
            "class ValidationEvidenceStore: pass\n": "parallel evidence",
            "class CandidateRegistry: pass\n": "package registry",
            "import requests\n": "direct network",
        }
        for source_text, reason in forbidden.items():
            with (
                self.subTest(reason=reason),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                validation = root / "apex-research/src/apex_research/validation.py"
                validation.parent.mkdir(parents=True)
                validation.write_text(required + source_text, encoding="utf-8")
                with self.assertRaisesRegex(verifier.ArchitectureViolation, reason):
                    verifier.scan_sources(root)

    def test_research_memory_rejects_private_truth_and_global_scans(self) -> None:
        required = """
class ResearchMemoryPolicy: pass
class ResearchMemoryEntry: pass
class ResearchMemoryQuery: pass
class ResearchMemoryDuplicateService: pass
class ResearchMemoryContextBuilder: pass
class ResearchMemoryStep: pass
WorkspaceClientProtocol = object
def use_lineage(workspace):
    return workspace.query_lineage(snapshot_token=snapshot_token)
"""
        forbidden = {
            "import sqlite3\n": "database",
            "from strategy_workspace import storage\n": "private Workspace alias",
            "workspace.list_records(limit=10000)\n": "global scan",
            "import subprocess\n": "runner",
            "import requests\n": "requests network",
            "import httpx\n": "httpx network",
            "from urllib.request import urlopen\n": "urllib network",
            "workspace.register_package(source)\n": "registry",
            "workspace.submit_run(request)\n": "formal path",
            "class MemoryLedger: pass\n": "parallel owner",
        }
        for source_text, reason in forbidden.items():
            with (
                self.subTest(reason=reason),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                memory = root / "apex-research/src/apex_research/memory_query.py"
                memory.parent.mkdir(parents=True)
                memory.write_text(required + source_text, encoding="utf-8")
                with self.assertRaises(verifier.ArchitectureViolation):
                    verifier.scan_sources(root)

    def test_research_memory_scans_new_memory_helpers(self) -> None:
        required = """
class ResearchMemoryPolicy: pass
class ResearchMemoryEntry: pass
class ResearchMemoryQuery: pass
class ResearchMemoryDuplicateService: pass
class ResearchMemoryContextBuilder: pass
class ResearchMemoryStep: pass
WorkspaceClientProtocol = object
def use_lineage(workspace):
    return workspace.query_lineage(snapshot_token=snapshot_token)
"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "apex-research/src/apex_research"
            source.mkdir(parents=True)
            (source / "memory_query.py").write_text(required, encoding="utf-8")
            (source / "memory_store.py").write_text(
                "import sqlite3\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(verifier.ArchitectureViolation, "database"):
                verifier.scan_sources(root)

    def test_research_memory_requires_shared_snapshot_and_no_missing_root_downgrade(
        self,
    ) -> None:
        required = """
class ResearchMemoryPolicy: pass
class ResearchMemoryEntry: pass
class ResearchMemoryQuery: pass
class ResearchMemoryDuplicateService: pass
class ResearchMemoryContextBuilder: pass
class ResearchMemoryStep: pass
WorkspaceClientProtocol = object
def use_lineage(workspace):
    return workspace.query_lineage(snapshot_token=snapshot_token)
"""
        forbidden = (
            required.replace("snapshot_token=snapshot_token", "cursor=cursor"),
            required + "\nallow_missing_root = True\n",
            required + "\nlineage_root_not_found = 'empty'\n",
        )
        for source_text in forbidden:
            with (
                self.subTest(source=source_text),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                memory = root / "apex-research/src/apex_research/memory_query.py"
                memory.parent.mkdir(parents=True)
                memory.write_text(source_text, encoding="utf-8")
                with self.assertRaises(verifier.ArchitectureViolation):
                    verifier.scan_sources(root)

    def test_focused_loop_rejects_private_execution_and_parallel_truth(self) -> None:
        required = (
            "# FocusedCandidateSelector FocusedStageRecord FocusedPreflightResult "
            "FocusedFormalRun FocusedReflection FocusedFeedback FocusedDecision "
            "WorkspaceClientProtocol PublishedRecordRef\n"
        )
        forbidden = {
            "import subprocess\n": "subprocess seam",
            "import socket\n": "direct network",
            "import sqlite3\n": "parallel ledger",
            "import quant_runtime\n": "Runtime",
            "workspace.register_package(source)\n": "package registry bypass",
            "workspace.submit_run(request)\n": "formal runner bypass",
            "os.environ['TOKEN']\n": "host credential",
            "class FocusedLedger: pass\n": "parallel owner",
        }
        for source_text, reason in forbidden.items():
            with (
                self.subTest(reason=reason),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                focused = root / "apex-research/src/apex_research/focused.py"
                focused.parent.mkdir(parents=True)
                focused.write_text(required + source_text)
                with self.assertRaisesRegex(verifier.ArchitectureViolation, reason):
                    verifier.scan_sources(root)

    def test_source_scan_rejects_private_cross_repository_access(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source_root = Path(temporary)
            source = source_root / "apex-research" / "src" / "apex_research"
            source.mkdir(parents=True)
            (source / "bad.py").write_text(
                "from strategy_workspace.storage import secret\n"
            )
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "private Workspace access"
            ):
                verifier.scan_sources(source_root)

    def test_source_scan_rejects_an_unguarded_apex_subprocess(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "apex-research" / "src" / "apex_research"
            source.mkdir(parents=True)
            (source / "rogue.py").write_text(
                "import subprocess\nsubprocess.run(['tool'])\n"
            )
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "subprocess seam"
            ):
                verifier.scan_sources(root)

    def test_external_adapter_must_depend_on_the_runner_interface(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            adapters = root / "apex-research" / "src" / "apex_research" / "adapters"
            adapters.mkdir(parents=True)
            candidate = adapters / "future_engine.py"
            candidate.write_text("class ResearchEngineAdapter:\n    pass\n")
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "bypasses runner"
            ):
                verifier.scan_sources(root)
            candidate.write_text(
                "from apex_research.external_runner import GovernedExternalResearchRunner\n"
                "class ResearchEngineAdapter:\n"
                "    production = True\n"
                "    def __init__(self, runner: GovernedExternalResearchRunner):\n"
                "        self.runner = runner\n"
            )
            verifier.scan_sources(root)

    def test_research_engine_adapter_rejects_direct_external_and_owner_seams(
        self,
    ) -> None:
        forbidden = {
            "import subprocess\n": "process",
            "import socket\n": "network",
            "import httpx\n": "network",
            "from httpx import Client\n": "network",
            "import os\nos.getenv('TOKEN')\n": "host environment",
            "from os import getenv\ngetenv('TOKEN')\n": "host environment",
            "import keyring\n": "host credential",
            "from strategy_workspace.storage import SQLiteRepository\n": "private Workspace",
            "from strategy_workspace import WorkspaceClient\n": "Workspace access",
            "workspace.register_package(source)\n": "package registration",
            "workspace.submit_run(request)\n": "Runtime submission",
            "orchestrator.advance(campaign)\n": "lifecycle",
            "workspace.publish_record({'record_type': 'apex-research.decision.v2'})\n": "decision",
        }
        for source_text, reason in forbidden.items():
            with (
                self.subTest(reason=reason),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                adapters = root / "apex-research" / "src" / "apex_research" / "adapters"
                adapters.mkdir(parents=True)
                (adapters / "bad_engine.py").write_text(
                    "from apex_research.external_runner import GovernedExternalResearchRunner\n"
                    "class ResearchEngineAdapter:\n"
                    "    production = True\n" + source_text
                )
                with self.assertRaisesRegex(verifier.ArchitectureViolation, reason):
                    verifier.scan_sources(root)

    def test_research_engine_owner_and_future_adapter_guard_matrix(self) -> None:
        cases = (
            (
                "strategy-workspace/src/strategy_workspace/engine.py",
                "class ResearchEnginePort: pass\n",
                "Workspace must not own ResearchEnginePort",
            ),
            (
                "quant-runtime/src/quant_runtime/engine.py",
                "class ResearchEnginePort: pass\n",
                "Runtime must not own ResearchEnginePort",
            ),
            (
                "strategy-reporting/src/strategy_reporting/engine.py",
                "class ResearchEnginePort: pass\n",
                "Reporting must not own ResearchEnginePort",
            ),
            (
                "apex-research/src/apex_research/adapters/rdagent.py",
                "class RDAgent: pass\n",
                "bypasses runner",
            ),
            (
                "apex-research/src/apex_research/adapters/qrafti.py",
                (
                    "from apex_research.external_runner import GovernedExternalResearchRunner\n"
                    "class Qrafti:\n"
                    "    production = True\n"
                    "    qualification = 'qualified'\n"
                ),
                "qualification",
            ),
            (
                "apex-research/src/apex_research/adapters/fake_production.py",
                (
                    "from apex_research.external_runner import GovernedExternalResearchRunner\n"
                    "production = False\n"
                ),
                "must declare production execution",
            ),
            (
                "apex-research/src/apex_research/adapters/future.py",
                (
                    "from apex_research.external_runner import GovernedExternalResearchRunner\n"
                    "production = True\n"
                    "def publish(workspace):\n"
                    "    workspace.publish_candidate({})\n"
                ),
                "Candidate publication",
            ),
        )
        for relative, source, reason in cases:
            with (
                self.subTest(path=relative),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                path = root / relative
                path.parent.mkdir(parents=True)
                path.write_text(source)
                with self.assertRaisesRegex(verifier.ArchitectureViolation, reason):
                    verifier.scan_sources(root)

    def test_only_dedicated_apex_process_control_files_are_admitted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = (
                root / "apex-research" / "src" / "apex_research" / "external_runner"
            )
            runner.mkdir(parents=True)
            (runner / "oci.py").write_text("import subprocess\n")
            (runner / "guardian.py").write_text("import subprocess\n")
            (runner / "recovery.py").write_text(
                "import shutil\nshutil.copy2('a', 'b')\n"
            )
            verifier.scan_sources(root)

    def test_rdagent_host_adapter_cannot_import_upstream_or_own_parallel_truth(
        self,
    ) -> None:
        forbidden = {
            "import rdagent\n": "direct RD-Agent import",
            "import subprocess\n": "subprocess seam",
            "import socket\n": "network",
            "import sqlite3\n": "parallel ledger",
            "workspace.register_package(source)\n": "package registration",
            "workspace.submit_run(request)\n": "Runtime submission",
        }
        required = (
            "MARKERS = 'RDAgentAdapterConfig GovernedExternalResearchRunner "
            "RunnerBackedResearchEngine forbidden_operations production = True'\n"
        )
        for source_text, reason in forbidden.items():
            with (
                self.subTest(reason=reason),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                adapter = root / "apex-research/src/apex_research/adapters/rdagent.py"
                adapter.parent.mkdir(parents=True)
                adapter.write_text(required + source_text)
                with self.assertRaisesRegex(verifier.ArchitectureViolation, reason):
                    verifier.scan_sources(root)

    def test_rdagent_strategy_chain_cannot_skip_to_formal_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "apex-research/src/apex_research"
            adapter = source / "adapters/rdagent.py"
            adapter.parent.mkdir(parents=True)
            adapter.write_text(
                "MARKERS = 'RDAgentAdapterConfig GovernedExternalResearchRunner "
                "RunnerBackedResearchEngine forbidden_operations production = True'\n"
            )
            chain = source / "rdagent_strategy_chain.py"
            chain.write_text(
                "MARKERS = 'admit_proposal evaluate_strategy_static .intake( .assess( "
                "confirmed_preflight_request .preflight('\n"
                'formal: str = "not_evaluated"\n'
                "workspace.submit_run(request)\n"
            )
            with self.assertRaisesRegex(
                verifier.ArchitectureViolation, "formal submission"
            ):
                verifier.scan_sources(root)

    def test_rdagent_strategy_normalizer_must_use_governed_public_seams(self) -> None:
        forbidden = {
            "import rdagent\n": "direct RD-Agent import",
            "import subprocess\n": "subprocess seam",
            "import sqlite3\n": "parallel ledger",
            "fin_quant()\n": "forbidden operation",
            "workspace.register_package(source)\n": "package registry bypass",
        }
        required = (
            "MARKERS = 'GovernedExternalResearchRunner "
            "readback_strategy_package_draft_artifacts StrategyCandidate.create'\n"
        )
        for source_text, reason in forbidden.items():
            with (
                self.subTest(reason=reason),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                adapter = root / "apex-research/src/apex_research/adapters/rdagent.py"
                adapter.parent.mkdir(parents=True)
                adapter.write_text(
                    "MARKERS = 'RDAgentAdapterConfig GovernedExternalResearchRunner "
                    "RunnerBackedResearchEngine forbidden_operations production = True'\n"
                )
                strategy = adapter.parents[1] / "rdagent_strategy.py"
                strategy.write_text(required + source_text)
                with self.assertRaisesRegex(verifier.ArchitectureViolation, reason):
                    verifier.scan_sources(root)


if __name__ == "__main__":
    unittest.main()
