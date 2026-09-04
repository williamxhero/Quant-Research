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
        self.assertIn("tests/test_preflight.py", runtime.command)
        self.assertIn("tests/test_preflight_run_order.py", runtime.command)
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

    def test_research_memory_rejects_private_truth_and_global_scans(self) -> None:
        required = (
            "# ResearchMemoryPolicy ResearchMemoryEntry ResearchMemoryQuery "
            "ResearchMemoryDuplicateService ResearchMemoryContextBuilder "
            "ResearchMemoryStep WorkspaceClientProtocol query_lineage(\n"
        )
        forbidden = {
            "import sqlite3\n": "database",
            "workspace.list_records(limit=10000)\n": "global scan",
            "import subprocess\n": "runner",
            "workspace.register_package(source)\n": "registry",
            "workspace.submit_run(request)\n": "formal path",
            "class MemoryLedger: pass\n": "parallel owner",
        }
        for source_text, reason in forbidden.items():
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                memory = root / "apex-research/src/apex_research/memory.py"
                memory.parent.mkdir(parents=True)
                memory.write_text(required + source_text, encoding="utf-8")
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
