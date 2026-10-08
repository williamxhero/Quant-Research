from __future__ import annotations

from pathlib import Path

import pytest
from strategy_workspace import WorkspaceClient, WorkspaceError

from manager_gui.workspace import WorkspaceDataProvider


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
