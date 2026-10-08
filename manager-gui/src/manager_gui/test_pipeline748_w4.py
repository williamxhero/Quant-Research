from __future__ import annotations

from pathlib import Path

import pytest
from strategy_workspace import WorkspaceClient, WorkspaceError

from manager_gui.models import ReadModelStatus
from manager_gui.workspace import WorkspaceDataProvider

RESOURCES = (
    "atlas",
    "stories",
    "genomes",
    "genome_conditions",
    "genome_comparison",
    "memory",
    "failure_patterns",
    "evidence",
    "lineage",
    "evidence_comparison",
    "failure_grouping",
    "methodology",
    "history",
    "source_documents",
    "search",
    "report_source",
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    owner = WorkspaceClient(root)
    owner.init()
    owner.publish_record(
        {
            "record_id": "report-1",
            "record_type": "apex-research.study-report-source.v1",
            "created_at": "2026-10-08T09:00:00Z",
            "payload": {
                "schema": "apex-research.study-report-source.v1",
                "title": "公开研究报告",
                "body": "冻结报告正文",
                "subject_id": "study-1",
                "version": "v1",
            },
        },
        artifacts=[{"source": b"original report v1", "media_type": "text/plain"}],
    )
    return root


def test_source_failure_is_part_of_read_view_version(workspace, monkeypatch):
    def unavailable(self, uri):
        raise WorkspaceError("artifact_read_failed", "Source unavailable")

    monkeypatch.setattr(WorkspaceClient, "read_artifact", unavailable)
    first = WorkspaceDataProvider(workspace).read("report_source")

    def corrupt(self, uri):
        raise WorkspaceError("artifact_integrity_failed", "Source integrity failed")

    monkeypatch.setattr(WorkspaceClient, "read_artifact", corrupt)
    second = WorkspaceDataProvider(workspace).read("report_source")

    assert first.snapshot_token != second.snapshot_token
    assert first.data["sources"][0]["read_status"] == "api_unavailable"
    assert second.data["sources"][0]["read_status"] == "integrity_failure"


@pytest.mark.parametrize("resource", RESOURCES)
def test_all_resources_declare_the_same_bounded_application_view(workspace, resource):
    provider = WorkspaceDataProvider(workspace)
    model = provider.read(resource)
    scope = model.data["coverage"]
    view = scope["application_read_view"]
    assert view["kind"] == "application-frozen-public-input"
    assert set(view["resources"]) == set(RESOURCES)
    assert view["workspace"].startswith("workspace-")
    assert scope["resource"] == resource
    assert scope["cross_resource_atomic_snapshot"] is False
    assert scope["global_catalog"] is False
    assert scope["lineage_depth"] == 1
    assert scope["lineage_page_size"] == 100
    assert model.as_of is None
    assert model.snapshot_token == provider.read("atlas").snapshot_token
    assert provider.read(resource, snapshot_token=model.snapshot_token).to_json() == model.to_json()
    if resource in {
        "genomes",
        "genome_conditions",
        "genome_comparison",
        "memory",
        "failure_patterns",
        "evidence_comparison",
        "failure_grouping",
        "methodology",
    }:
        assert model.availability.status is ReadModelStatus.API_UNAVAILABLE
