from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "tools" / "verify_public_seam_architecture.py"
SPEC = importlib.util.spec_from_file_location("public_seam_verifier", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


class PublicSeamArchitectureTests(unittest.TestCase):
    def test_fixture_plan_uses_only_existing_public_module_seams(self) -> None:
        plan = verifier.fixture_plan(ROOT)
        self.assertEqual([item.owner for item in plan], [
            "strategy_workspace",
            "quant_runtime",
            "apex_research",
            "strategy_reporting",
            "spec014_installed_wheels",
        ])
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
        installed = next(item for item in plan if item.owner == "spec014_installed_wheels")
        self.assertEqual(installed.repository, ".")
        self.assertIn("tools/spec014_installed_wheel_tracer.py", installed.command)
        self.assertTrue((ROOT / "tools/spec014_installed_wheel_tracer.py").is_file())

    def test_spec014_source_guard_requires_public_evidence_and_reporting_seams(self) -> None:
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

    def test_spec014_source_guard_rejects_parallel_truth_scans_and_masquerade(self) -> None:
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
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                apex = root / "apex-research/src/apex_research"
                apex.mkdir(parents=True)
                (apex / "evidence_v2.py").write_text(required + addition, encoding="utf-8")
                with self.assertRaisesRegex(verifier.ArchitectureViolation, reason):
                    verifier.scan_sources(root)

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
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                source = root / "apex-research/src/apex_research"
                source.mkdir(parents=True)
                (source / "statistical_control.py").write_text(
                    required + source_text, encoding="utf-8"
                )
                (source / "statistical_reporting.py").write_text("", encoding="utf-8")
                with self.assertRaisesRegex(verifier.ArchitectureViolation, reason):
                    verifier.scan_sources(root)

    def test_validation_matrix_rejects_parallel_truth_and_execution_bypasses(self) -> None:
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
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as temporary:
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
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as temporary:
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
            (source / "memory_store.py").write_text("import sqlite3\n", encoding="utf-8")
            with self.assertRaisesRegex(verifier.ArchitectureViolation, "database"):
                verifier.scan_sources(root)

    def test_research_memory_requires_shared_snapshot_and_no_missing_root_downgrade(self) -> None:
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
            with self.subTest(source=source_text), tempfile.TemporaryDirectory() as temporary:
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
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as temporary:
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
            (source / "bad.py").write_text("from strategy_workspace.storage import secret\n")
            with self.assertRaisesRegex(verifier.ArchitectureViolation, "private Workspace access"):
                verifier.scan_sources(source_root)

    def test_source_scan_rejects_an_unguarded_apex_subprocess(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "apex-research" / "src" / "apex_research"
            source.mkdir(parents=True)
            (source / "rogue.py").write_text("import subprocess\nsubprocess.run(['tool'])\n")
            with self.assertRaisesRegex(verifier.ArchitectureViolation, "subprocess seam"):
                verifier.scan_sources(root)

    def test_external_adapter_must_depend_on_the_runner_interface(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            adapters = root / "apex-research" / "src" / "apex_research" / "adapters"
            adapters.mkdir(parents=True)
            candidate = adapters / "future_engine.py"
            candidate.write_text("class ResearchEngineAdapter:\n    pass\n")
            with self.assertRaisesRegex(verifier.ArchitectureViolation, "bypasses runner"):
                verifier.scan_sources(root)
            candidate.write_text(
                "from apex_research.external_runner import GovernedExternalResearchRunner\n"
                "class ResearchEngineAdapter:\n"
                "    production = True\n"
                "    def __init__(self, runner: GovernedExternalResearchRunner):\n"
                "        self.runner = runner\n"
            )
            verifier.scan_sources(root)

    def test_research_engine_adapter_rejects_direct_external_and_owner_seams(self) -> None:
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
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                adapters = root / "apex-research" / "src" / "apex_research" / "adapters"
                adapters.mkdir(parents=True)
                (adapters / "bad_engine.py").write_text(
                    "from apex_research.external_runner import GovernedExternalResearchRunner\n"
                    "class ResearchEngineAdapter:\n"
                    "    production = True\n"
                    + source_text
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
                "from apex_research.external_runner import GovernedExternalResearchRunner\n"
                "class Qrafti:\n"
                "    production = True\n"
                "    qualification = 'qualified'\n",
                "qualification",
            ),
            (
                "apex-research/src/apex_research/adapters/fake_production.py",
                "from apex_research.external_runner import GovernedExternalResearchRunner\n"
                "production = False\n",
                "must declare production execution",
            ),
            (
                "apex-research/src/apex_research/adapters/future.py",
                "from apex_research.external_runner import GovernedExternalResearchRunner\n"
                "production = True\n"
                "def publish(workspace):\n"
                "    workspace.publish_candidate({})\n",
                "Candidate publication",
            ),
        )
        for relative, source, reason in cases:
            with self.subTest(path=relative), tempfile.TemporaryDirectory() as temporary:
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
                root
                / "apex-research"
                / "src"
                / "apex_research"
                / "external_runner"
            )
            runner.mkdir(parents=True)
            (runner / "oci.py").write_text("import subprocess\n")
            (runner / "guardian.py").write_text("import subprocess\n")
            (runner / "recovery.py").write_text("import shutil\nshutil.copy2('a', 'b')\n")
            verifier.scan_sources(root)

    def test_rdagent_host_adapter_cannot_import_upstream_or_own_parallel_truth(self) -> None:
        forbidden = {
            "import rdagent\n": "direct RD-Agent import",
            "import subprocess\n": "subprocess seam",
            "import socket\n": "network",
            "import sqlite3\n": "parallel ledger",
            "workspace.register_package(source)\n": "package registration",
            "workspace.submit_run(request)\n": "Runtime submission",
        }
        required = (
            "RDAgentAdapterConfig GovernedExternalResearchRunner "
            "RunnerBackedResearchEngine forbidden_operations production = True\n"
        )
        for source_text, reason in forbidden.items():
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as temporary:
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
                "RDAgentAdapterConfig GovernedExternalResearchRunner "
                "RunnerBackedResearchEngine forbidden_operations production = True\n"
            )
            chain = source / "rdagent_strategy_chain.py"
            chain.write_text(
                "admit_proposal evaluate_strategy_static .intake( .assess( "
                "confirmed_preflight_request .preflight(\n"
                'formal: str = "not_evaluated"\n'
                "workspace.submit_run(request)\n"
            )
            with self.assertRaisesRegex(verifier.ArchitectureViolation, "formal submission"):
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
            "GovernedExternalResearchRunner readback_strategy_package_draft_artifacts "
            "StrategyCandidate.create\n"
        )
        for source_text, reason in forbidden.items():
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                adapter = root / "apex-research/src/apex_research/adapters/rdagent.py"
                adapter.parent.mkdir(parents=True)
                adapter.write_text(
                    "RDAgentAdapterConfig GovernedExternalResearchRunner "
                    "RunnerBackedResearchEngine forbidden_operations production = True\n"
                )
                strategy = adapter.parents[1] / "rdagent_strategy.py"
                strategy.write_text(required + source_text)
                with self.assertRaisesRegex(verifier.ArchitectureViolation, reason):
                    verifier.scan_sources(root)


if __name__ == "__main__":
    unittest.main()
