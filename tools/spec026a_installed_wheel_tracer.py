"""Build and replay the bounded installed-wheel SPEC-026A public tracer."""

from __future__ import annotations

import argparse
import importlib.util
import json
import tempfile
import time
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
REPOSITORIES = ("strategy-workspace", "apex-research")
UNCHANGED_SOURCE_BASELINES = {
    "quant-runtime": "72a1dfec6ebdbe132e7359afc61ed9ca07dd15e4",
    "strategy-reporting": "087ae2be9a0e0b7c04eef5e4dee4c735e5a6a082",
    "strategy-workspace": "1e9c58251efcf48dd8e4d8bc66007dbe105affba",
}
TIMEOUT_SECONDS = 240
REPLAYS = 2
NODES = (
    "test_campaign_source_contract_has_canonical_identity_and_closed_availability",
    "test_unavailable_campaign_sections_require_a_reason",
    "test_campaign_source_rejects_publication_metadata_private_paths_and_secrets",
    "test_service_assembles_public_campaign_graph_in_deterministic_order",
    "test_service_selects_current_owner_facts_and_keeps_archives_distinct",
    "test_service_places_coevolution_in_iterations",
    "test_service_ignores_stale_and_superseded_currency_and_selects_revalidated",
    "test_service_rejects_missing_current_owner_reference",
    "test_service_rejects_identity_mismatch_and_cycles",
    "test_service_rejects_conflicting_current_currency_owner_facts",
    "test_service_publishes_reads_and_backfills_one_immutable_source",
    "test_service_marks_incomplete_terminal_campaigns_honestly",
)


class TracerFailure(InstalledWheelFailure):
    pass


def _progress(message: str) -> None:
    print(f"SPEC026A_PROGRESS {message}", file=__import__("sys").stderr, flush=True)


def build_and_run(repository_root: Path) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    environment = HARNESS.sanitized_environment()
    if "PYTHONPATH" in environment:
        raise TracerFailure("sanitized tracer environment retained PYTHONPATH")
    repositories = {name: repository_root / name for name in REPOSITORIES}
    with tempfile.TemporaryDirectory(prefix="spec026a-installed-") as temporary:
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
                path, snapshot / name, topology[name]["source_files"]
            )
        wheels = HARNESS.build_wheels(snapshot, REPOSITORIES, dist, environment)
        python = HARNESS.create_installed_environment(
            isolated, wheels, environment, install_pytest=True
        )
        source_roots = tuple(snapshot / name / "src" for name in REPOSITORIES)
        test_file = snapshot / "apex-research/tests/test_campaign_report_source.py"
        for replay in range(1, REPLAYS + 1):
            for node in NODES:
                started = time.monotonic()
                _progress(f"replay={replay} node={node} start")
                HARNESS.run_installed_pytest(
                    python,
                    (Path(f"{test_file}::{node}"),),
                    REPOSITORIES,
                    source_roots,
                    cwd=isolated,
                    environment=environment,
                    timeout_seconds=TIMEOUT_SECONDS,
                )
                _progress(
                    f"replay={replay} node={node} passed_seconds={time.monotonic() - started:.1f}"
                )
        smoke_results = []
        for replay in range(1, REPLAYS + 1):
            output = HARNESS.run_command(
                [
                    str(python),
                    "-I",
                    "-B",
                    str(Path(__file__).resolve()),
                    "--repository-root",
                    str(repository_root),
                    "--smoke-root",
                    str(isolated / f"smoke-{replay}"),
                ],
                cwd=isolated,
                environment=environment,
                timeout_seconds=TIMEOUT_SECONDS,
            )
            smoke_results.append(json.loads(output))
        if smoke_results[0] != smoke_results[1]:
            raise TracerFailure(
                "SPEC-026A installed identity transcript drifted on replay"
            )
        return {
            **smoke_results[0],
            "nodes": len(NODES),
            "replays": REPLAYS,
            "node_timeout_seconds": TIMEOUT_SECONDS,
            "unchanged_sources": unchanged,
            "source_topology": topology,
        }


def smoke(root: Path) -> dict[str, Any]:
    import apex_research
    import strategy_workspace
    from apex_research.campaign_report_source import (
        CampaignReportSectionName,
        CampaignReportSourceRef,
        CampaignReportSourceService,
    )
    from apex_research.campaigns import CampaignRecordPublisher
    from apex_research.models import Campaign, Hypothesis, ResearchBrief
    from strategy_workspace import WorkspaceClient

    workspace = WorkspaceClient(root / "workspace")
    publisher = CampaignRecordPublisher(workspace)
    brief = ResearchBrief.create(
        question="Can one frozen campaign source be rebuilt?",
        constraints=("public Workspace only",),
        source_evidence=(),
        legacy_evidence=(),
        assumptions=("owner facts are immutable",),
    )
    campaign = Campaign.create(brief=brief, title="Installed campaign")
    hypothesis = Hypothesis.create(
        campaign=campaign,
        statement="The source remains deterministic.",
        source_evidence=(),
        assumptions=(),
    )
    publisher.publish(brief)
    publisher.publish(campaign)
    publisher.publish(hypothesis)
    campaign_ref = CampaignReportSourceRef(
        record_id=campaign.campaign_id,
        record_type="apex-research.campaign.v1",
    )
    service = CampaignReportSourceService(workspace)
    first = service.publish(campaign_ref)
    second = service.backfill(campaign_ref)
    source = service.read(first)
    if first != second or source.source_id != first.record_id:
        raise TracerFailure("installed campaign source replay did not reuse identity")
    sections = {item.name: item for item in source.sections}
    if sections[CampaignReportSectionName.HYPOTHESES].items[0].source.record_id != (
        hypothesis.hypothesis_id
    ):
        raise TracerFailure("installed campaign hypothesis ordering drifted")
    serialized = json.dumps(
        source.model_dump(mode="json", by_alias=True), sort_keys=True
    )
    for forbidden in ("created_at", "local_path", "raw_prompt", "raw_logs", "secret"):
        if forbidden in serialized:
            raise TracerFailure(f"installed campaign source leaked {forbidden}")
    return {
        "ok": True,
        "source_id": source.source_id,
        "publication_reused": first == second,
        "section_statuses": {
            item.name.value: item.availability.status.value for item in source.sections
        },
        "scenario_coverage": [
            "auxiliary_validation",
            "blocked",
            "budget_exhausted",
            "cancelled",
            "co_evolution",
            "complete",
            "conflicting",
            "cyclic",
            "failed",
            "identity_mismatched",
            "partial",
            "stale",
            "superseded",
            "two_archive",
            "revalidated",
        ],
        "runtime_or_external_invocations": 0,
        "connected_status": {
            "markethub": "not_run_not_impacted",
            "runtime_oci": "not_run_not_impacted",
            "apex_external_validation": "not_run_not_impacted",
            "reporting_connected": "not_run_not_impacted",
        },
        "versions": {
            "apex_research": apex_research.__version__,
            "strategy_workspace": strategy_workspace.__version__,
        },
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
    except (InstalledWheelFailure, TracerFailure, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
