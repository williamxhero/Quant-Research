from __future__ import annotations

from pathlib import Path

import pytest
from strategy_workspace import WorkspaceClient, WorkspaceError

from manager_gui.models import ReadModelStatus
from manager_gui.web import ManagerGUIApp
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


@pytest.mark.parametrize(
    "query",
    [
        "snapshot_token=",
        "snapshot=",
        "snapshot_token=%20",
        "snapshot_token={token}&snapshot_token=unknown",
        "snapshot_token={token}&snapshot=unknown",
        "snapshot_token=&snapshot={token}",
    ],
)
def test_blank_or_conflicting_tokens_do_not_fall_back_to_latest(workspace, query):
    provider = WorkspaceDataProvider(workspace)
    token = provider.read().snapshot_token
    app = ManagerGUIApp(provider)
    model = app.read_model(app.request_state("/?" + query.format(token=token)))
    assert model.availability.status is ReadModelStatus.STALE
    assert model.data == {}
    assert model.errors[0].code == "snapshot_drift"


@pytest.mark.parametrize("token", ["", " ", "unknown"])
def test_direct_provider_rejects_unusable_tokens(workspace, token):
    model = WorkspaceDataProvider(workspace).read("atlas", snapshot_token=token)
    assert model.availability.status is ReadModelStatus.STALE
    assert model.data == {}


def test_provider_that_ignores_requested_token_cannot_expose_latest(workspace):
    latest = WorkspaceDataProvider(workspace).read()

    class IgnoringProvider:
        def read(self, resource="atlas", *, snapshot_token=None):
            return latest

    app = ManagerGUIApp(IgnoringProvider())
    rejected = app.read_model(app.request_state("/?snapshot_token=unavailable"))
    assert rejected.availability.status is ReadModelStatus.STALE
    assert rejected.snapshot_token == "unavailable"
    assert rejected.data == {}
    assert "冻结报告正文" not in app.render("/?snapshot_token=unavailable")


def test_publication_and_original_bind_verifiable_versions_to_identity(workspace):
    model = WorkspaceDataProvider(workspace).read("report_source")
    report = model.data["reports"][0]
    original = model.data["sources"][0]
    refs = {ref.source_id: ref for ref in model.source_refs}
    assert report["source_revision"] == refs["report-1"].revision
    assert report["snapshot_token"] == model.snapshot_token
    assert report["original_source_revision"] == original["source_revision"]
    assert original["source_revision"] == refs[original["source_id"]].revision
    assert report["raw_source"]["payload"]["subject_id"] == report["subject_id"] == "study-1"
    assert report["original_source_id"] == original["source_id"]


@pytest.mark.parametrize("change", ["record-revision", "original-revision", "linked-revision"])
def test_same_token_does_not_hide_evidence_revision_drift(workspace, change):
    model = WorkspaceDataProvider(workspace).read("report_source")
    report = model.data["reports"][0]
    original = model.data["sources"][0]
    if change == "record-revision":
        report["source_revision"] = "different-publication-version"
    elif change == "original-revision":
        original["source_revision"] = "different-original-version"
    else:
        report["original_source_revision"] = "different-linked-version"

    class SuppliedProvider:
        def read(self, resource="atlas", *, snapshot_token=None):
            return model

    app = ManagerGUIApp(SuppliedProvider())
    document = app.render("/?view=portal&lang=en&mode=reader")
    assert "Original and result versions differ" in document
    assert (
        "Cannot open the original; this content cannot be treated as verified support." in document
    )


@pytest.mark.parametrize("change", ["missing-original", "unreadable-original"])
def test_unreadable_linked_original_is_not_verified_support(workspace, change):
    model = WorkspaceDataProvider(workspace).read("report_source")
    if change == "missing-original":
        model.data["sources"] = []
    else:
        model.data["sources"][0].pop("text")

    class SuppliedProvider:
        def read(self, resource="atlas", *, snapshot_token=None):
            return model

    document = ManagerGUIApp(SuppliedProvider()).render("/?view=portal&lang=en&mode=reader")
    assert "The matching source did not supply a readable original" in document
    assert (
        "Cannot open the original; this content cannot be treated as verified support." in document
    )
