"""Build and execute the SPEC-014 tracer using only installed repository wheels."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any


REPOSITORIES = (
    "strategy-workspace",
    "quant-runtime",
    "apex-research",
    "strategy-reporting",
)
INSTALLED_ACCEPTANCE_TEST_GROUPS = (
    (
        "apex-research",
        (
            "tests/test_evidence_v2.py",
            (
                "tests/test_behavioral_gate.py::"
                "test_governed_behavioral_gate_uses_runtime_conformance_without_live_engines"
            ),
            (
                "tests/test_report_source.py::"
                "test_source_round_trips_as_real_workspace_publication_envelope"
            ),
        ),
    ),
    (
        "strategy-reporting",
        (
            (
                "tests/test_workspace_roundtrip.py::"
                "test_real_workspace_client_publication_round_trip"
            ),
        ),
    ),
)


class TracerFailure(RuntimeError):
    """The installed-wheel tracer failed a closed acceptance condition."""


def _run(command: list[str], *, cwd: Path, environment: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise TracerFailure(
            f"command failed ({completed.returncode}): {' '.join(command)}\n"
            f"{completed.stdout}{completed.stderr}"
        )
    return completed.stdout


def build_and_run(repository_root: Path) -> dict[str, Any]:
    root = repository_root.resolve()
    for repository in REPOSITORIES:
        if not (root / repository / "pyproject.toml").is_file():
            raise TracerFailure(f"repository is unavailable: {repository}")
    with tempfile.TemporaryDirectory(prefix="spec014-installed-") as temporary:
        isolated = Path(temporary)
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        dist = isolated / "dist"
        dist.mkdir()
        wheels: list[Path] = []
        for repository in REPOSITORIES:
            before = set(dist.glob("*.whl"))
            _run(
                ["uv", "build", "--wheel", "--out-dir", str(dist)],
                cwd=root / repository,
                environment=environment,
            )
            built = set(dist.glob("*.whl")) - before
            if len(built) != 1:
                raise TracerFailure(f"{repository} did not produce exactly one wheel")
            wheels.extend(built)
        virtual_environment = isolated / "venv"
        _run(
            ["uv", "venv", str(virtual_environment)],
            cwd=isolated,
            environment=environment,
        )
        python = (
            virtual_environment / "Scripts" / "python.exe"
            if os.name == "nt"
            else virtual_environment / "bin" / "python"
        )
        _run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                *(str(path) for path in wheels),
            ],
            cwd=isolated,
            environment=environment,
        )
        _run(
            ["uv", "pip", "install", "--python", str(python), "pytest>=8.3,<9"],
            cwd=isolated,
            environment=environment,
        )
        for repository, targets in INSTALLED_ACCEPTANCE_TEST_GROUPS:
            _run(
                [
                    str(python),
                    "-m",
                    "pytest",
                    "-q",
                    *(str(root / repository / target) for target in targets),
                ],
                cwd=isolated,
                environment=environment,
            )
        output = _run(
            [
                str(python),
                str(Path(__file__).resolve()),
                "--repository-root",
                str(root),
                "--smoke-root",
                str(isolated / "workspace"),
            ],
            cwd=isolated,
            environment=environment,
        )
        try:
            result = json.loads(output)
        except json.JSONDecodeError as exc:
            raise TracerFailure(f"installed tracer emitted invalid JSON: {output}") from exc
        if result.get("ok") is not True:
            raise TracerFailure(f"installed tracer failed: {result}")
        result["installed_acceptance_tests"] = [
            f"{repository}/{target}"
            for repository, targets in INSTALLED_ACCEPTANCE_TEST_GROUPS
            for target in targets
        ]
        return result


def _publication_lineage(evidence: Any) -> list[dict[str, str]]:
    lineage = [
        {
            "source_kind": item.record.record_type,
            "source_id": item.record.record_id,
            "relation": "evidence-source",
        }
        for item in evidence.sources
    ]
    lineage.append(
        {
            "source_kind": "quant-research.strategy-package-ref.v1",
            "source_id": evidence.scope.strategy_package.package_hash,
            "relation": "evidence-strategy-package",
        }
    )
    if evidence.supersedes is not None:
        lineage.append(
            {
                "source_kind": evidence.supersedes.record_type,
                "source_id": evidence.supersedes.record_id,
                "relation": "supersedes-evidence",
            }
        )
    return lineage


def _source_lineage(source: Any) -> list[dict[str, str]]:
    return [
        {
            "source_kind": source.evidence_ref.record_type,
            "source_id": source.evidence_ref.record_id,
            "relation": "evidence-v2",
        },
        *(
            {
                "source_kind": item.record_type,
                "source_id": item.record_id,
                "relation": "evidence-source",
            }
            for item in source.sources
        ),
    ]


def smoke(repository_root: Path, workspace_root: Path) -> dict[str, Any]:
    import apex_research
    import quant_runtime
    import strategy_reporting
    import strategy_workspace
    from apex_research import EvidenceV2, EvidenceV2StudySource
    from apex_research.canonical import canonical_sha256
    from strategy_reporting.adapters.evidence_v2 import EvidenceV2ReadModelBuilder
    from strategy_reporting.adapters.workspace import WorkspaceAdapter
    from strategy_reporting.contracts.evidence_v2 import EvidenceV2SourceRef
    from strategy_reporting.errors import ReportingError
    from strategy_workspace import WorkspaceClient

    source_root = repository_root.resolve()
    modules = (apex_research, quant_runtime, strategy_reporting, strategy_workspace)
    for module in modules:
        module_path = Path(str(module.__file__)).resolve()
        if module_path.is_relative_to(source_root):
            raise TracerFailure(f"source-tree import is forbidden: {module_path}")

    workspace = WorkspaceClient(workspace_root)
    workspace.init()

    def publish_owner(
        record_type: str,
        identity_field: str,
        **values: Any,
    ) -> dict[str, Any]:
        identity = {"schema": record_type, **values}
        record_id = canonical_sha256(identity)
        workspace.publish_record(
            {
                "record_id": record_id,
                "record_type": record_type,
                "payload": {**identity, identity_field: record_id},
            }
        )
        return {"record_id": record_id, "record_type": record_type}

    package = {
        "schema": "quant-research.strategy-package-ref.v1",
        "strategy_id": "spec014-installed-tracer",
        "revision": 1,
        "package_hash": "9" * 64,
    }
    campaign = publish_owner(
        "apex-research.campaign.v1",
        "campaign_id",
        title="SPEC-014 installed tracer",
    )
    strategy_identity = {
        "schema": "apex-research.strategy-candidate.v1",
        "semantic_id": "8" * 64,
        "envelope": {"family_id": "spec014-installed", "revision": 1},
        "semantics": {"signals": []},
    }
    strategy_id = canonical_sha256(strategy_identity)
    strategy = {
        "record_id": strategy_id,
        "record_type": "apex-research.strategy-candidate.v1",
        "semantic_id": "8" * 64,
        "family_id": "spec014-installed",
        "revision": 1,
    }
    workspace.publish_record(
        {
            "record_id": strategy_id,
            "record_type": strategy["record_type"],
            "payload": {**strategy_identity, "revision_id": strategy_id},
        }
    )
    protocol = publish_owner(
        "apex-research.validation-protocol-matrix.v1",
        "protocol_id",
        campaign=campaign,
        candidate={
            "record_id": strategy["record_id"],
            "record_type": strategy["record_type"],
        },
        strategy_package=package,
    )

    def owner_source(reference: dict[str, Any], namespace: str) -> dict[str, Any]:
        return {
            "canonical_owner": "apex_research",
            "namespace": namespace,
            "record": reference,
        }

    campaign_source = owner_source(campaign, "apex.control")
    protocol_source = owner_source(protocol, "apex.control")
    strategy_source = owner_source(strategy, "strategy.composition")
    sources = sorted(
        (campaign_source, protocol_source, strategy_source),
        key=lambda item: (
            item["canonical_owner"],
            item["namespace"],
            item["record"]["record_type"],
            item["record"]["record_id"],
        ),
    )

    def section(
        status: str,
        reason: str,
        *,
        source_values: list[dict[str, Any]] | None = None,
        outcome: str | None = None,
        blockers: list[dict[str, Any]] | None = None,
        incompatibilities: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "reason": reason,
            "sources": source_values or [],
            "outcome": outcome,
            "blockers": blockers or [],
            "incompatibilities": incompatibilities or [],
        }

    absent = section(
        "not_evaluated",
        "No canonical future owner record exists in the frozen snapshot.",
    )
    sections = {
        "source_mapping": section(
            "evaluated",
            "Every canonical owner source was read back.",
            source_values=sources,
        ),
        "candidates": {
            "factor": deepcopy(absent),
            "model": deepcopy(absent),
            "strategy": section(
                "evaluated",
                "The canonical StrategyCandidate is present.",
                source_values=[strategy_source],
                outcome="pass",
            ),
        },
        "candidate_gates": deepcopy(absent),
        "data_identity": deepcopy(absent),
        "execution_costs": deepcopy(absent),
        "formal_results": deepcopy(absent),
        "validation_matrix": section(
            "not_evaluated",
            "This installed-wheel partial fixture does not claim validation coverage.",
        ),
        "statistical_controls": deepcopy(absent),
        "robustness": section(
            "incomparable",
            "The frozen Candidate and protocol axes are intentionally incomparable.",
            source_values=[protocol_source, strategy_source],
            incompatibilities=[
                {
                    "axis": "strategy.scope",
                    "left": protocol_source,
                    "right": strategy_source,
                }
            ],
        ),
        "auxiliary_validation": deepcopy(absent),
        "failures": section(
            "blocked",
            "The exact campaign owner fact is the frozen blocker.",
            source_values=[campaign_source],
            blockers=[campaign_source],
        ),
        "warnings": deepcopy(absent),
        "limitations": deepcopy(absent),
        "co_evolution": deepcopy(absent),
        "currency": deepcopy(absent),
        "revalidation": deepcopy(absent),
    }

    def build_evidence(supersedes: dict[str, str] | None = None) -> Any:
        identity = {
            "schema": "apex-research.evidence.v2",
            "scope": {
                "campaign": campaign,
                "protocol": protocol,
                "candidate": strategy,
                "strategy_package": package,
                "hypothesis": None,
                "iteration": None,
            },
            "sources": sources,
            "sections": sections,
            "candidate_composition": {
                "factors": [],
                "models": [],
                "strategy": strategy,
                "factor_namespace": "discovery.non_formal",
                "model_namespace": "discovery.non_formal",
                "formal_source": "strategy_package_only",
            },
            "candidate_gate": None,
            "runtime_formal": [],
            "validation_coverage": None,
            "statistical_control": None,
            "honesty": None,
            "qualification_inference": "forbidden",
            "production_approval_inference": "forbidden",
            "supersedes": supersedes,
        }
        return EvidenceV2.model_validate_json(
            json.dumps({**identity, "evidence_id": canonical_sha256(identity)}),
            strict=True,
        )

    def publish_evidence(evidence: Any) -> Any:
        workspace.publish_record(
            {
                "record_id": evidence.evidence_id,
                "record_type": evidence.schema_id,
                "payload": evidence.model_dump(mode="json", by_alias=True),
                "lineage": _publication_lineage(evidence),
            }
        )
        source_refs = [
            {
                "record_id": item.record.record_id,
                "record_type": item.record.record_type,
            }
            for item in evidence.sources
        ]
        source_identity = {
            "schema": "apex-research.study-report-source.v2",
            "evidence_ref": {
                "record_id": evidence.evidence_id,
                "record_type": evidence.schema_id,
            },
            "evidence": evidence.model_dump(mode="json", by_alias=True),
            "sources": source_refs,
            "source_record_ids": [item["record_id"] for item in source_refs],
            "workspace_runs": [],
            "qualification_inference": "forbidden",
            "production_approval_inference": "forbidden",
        }
        source = EvidenceV2StudySource.model_validate_json(
            json.dumps(
                {**source_identity, "source_id": canonical_sha256(source_identity)}
            ),
            strict=True,
        )
        workspace.publish_record(
            {
                "record_id": source.source_id,
                "record_type": source.schema_id,
                "payload": source.model_dump(mode="json", by_alias=True),
                "lineage": _source_lineage(source),
            }
        )
        return source

    predecessor_evidence = build_evidence()
    predecessor_source = publish_evidence(predecessor_evidence)
    predecessor_publication = deepcopy(
        workspace.get_record(predecessor_evidence.evidence_id)
    )
    successor_evidence = build_evidence(
        {
            "record_id": predecessor_evidence.evidence_id,
            "record_type": predecessor_evidence.schema_id,
        }
    )
    successor_source = publish_evidence(successor_evidence)

    reader = EvidenceV2ReadModelBuilder(WorkspaceAdapter(workspace))
    predecessor = reader.read(EvidenceV2SourceRef(record_id=predecessor_source.source_id))
    successor = reader.read(EvidenceV2SourceRef(record_id=successor_source.source_id))
    replay = reader.read(EvidenceV2SourceRef(record_id=successor_source.source_id))
    if successor != replay or predecessor.source.evidence.supersedes is not None:
        raise TracerFailure("installed Evidence/report read-model identity is not deterministic")
    if successor.source.evidence.supersedes is None or (
        successor.source.evidence.supersedes.record_id
        != predecessor.source.evidence.evidence_id
    ):
        raise TracerFailure("installed supersession identity is incomplete")
    if workspace.get_record(predecessor_evidence.evidence_id) != predecessor_publication:
        raise TracerFailure("supersession mutated predecessor evidence")
    statuses = {
        successor.source.evidence.sections.candidates.strategy.status,
        successor.source.evidence.sections.validation_matrix.status,
        successor.source.evidence.sections.failures.status,
        successor.source.evidence.sections.robustness.status,
    }
    if statuses != {"evaluated", "not_evaluated", "blocked", "incomparable"}:
        raise TracerFailure("installed tracer lost closed four-state semantics")
    if any(
        getattr(successor.source.evidence.sections, name).status != "not_evaluated"
        for name in ("co_evolution", "currency", "revalidation")
    ):
        raise TracerFailure("absent future sources did not remain not_evaluated")

    class TamperedWorkspace:
        def __init__(self, client: Any, record_id: str) -> None:
            self.client = client
            self.record_id = record_id

        def __getattr__(self, name: str) -> Any:
            return getattr(self.client, name)

        def get_record(self, record_id: str) -> dict[str, Any]:
            value = self.client.get_record(record_id)
            if record_id == self.record_id:
                value["lineage"] = []
            return value

    try:
        EvidenceV2ReadModelBuilder(
            WorkspaceAdapter(TamperedWorkspace(workspace, successor_source.source_id))
        ).read(EvidenceV2SourceRef(record_id=successor_source.source_id))
    except ReportingError:
        pass
    else:
        raise TracerFailure("tampered installed-wheel source did not fail closed")

    return {
        "ok": True,
        "wheels": [module.__name__ for module in modules],
        "predecessor_evidence_id": predecessor.source.evidence.evidence_id,
        "successor_evidence_id": successor.source.evidence.evidence_id,
        "report_model_schema": successor.schema_id,
        "source_record_ids": successor.source.source_record_ids,
        "states": sorted(statuses),
        "future_sources": "not_evaluated",
        "tamper": "rejected",
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
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
