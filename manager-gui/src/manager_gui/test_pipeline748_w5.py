from __future__ import annotations

import hashlib
import json
import threading
from urllib.request import urlopen

import pytest
from strategy_workspace import WorkspaceClient

from manager_gui.models import (
    Availability,
    Derivation,
    ManagerReadModel,
    ReadModelError,
    ReadModelStatus,
)
from manager_gui.testing.acceptance import reading_answer
from manager_gui.workspace import WorkspaceDataProvider


def test_unavailable_catalog_answer_never_certifies_absence():
    coverage = {
        "resource": "memory",
        "global_catalog": False,
        "cross_resource_atomic_snapshot": False,
        "application_read_view": {"workspace": "workspace-test"},
    }
    model = ManagerReadModel(
        {}, (), None, "workspace-view-test", Derivation("direct"),
        Availability(ReadModelStatus.API_UNAVAILABLE, False, "No public catalog."),
        (ReadModelError("api_unavailable", "No public catalog.", details={"coverage": coverage}),),
    )
    answer = reading_answer(model, view="memory-failures", commit="a" * 40)
    assert answer["input"]["resource"] == "memory"
    assert answer["input"]["commit"] == "a" * 40
    assert answer["input"]["snapshot_token"] == "workspace-view-test"
    assert answer["coverage"] == coverage
    assert answer["result"]["kind"] == "cannot_enumerate"
    assert answer["result"]["records"] == []
    assert answer["unknowns"]["currency"] is None
    assert "absence_not_confirmed" in answer["cannot_conclude"]


def test_report_answer_binds_public_record_and_original_without_inventing_money(tmp_path):
    root = tmp_path / "isolated-workspace"
    owner = WorkspaceClient(root)
    owner.init()
    owner.publish_record(
        {
            "record_id": "report-1",
            "record_type": "apex-research.study-report-source.v1",
            "created_at": "2026-10-09T09:00:00Z",
            "payload": {
                "schema": "apex-research.study-report-source.v1",
                "title": "原文包含 fixture 一词也不能改写",
                "description": "公开报告描述，不是全文",
                "subject_id": "study-1",
                "version": "v3",
            },
        },
        artifacts=[{"source": b"Published original", "media_type": "text/plain"}],
    )
    provider = WorkspaceDataProvider(root)
    model = provider.read("report_source")
    answer = reading_answer(model, view="portal", commit="b" * 40)
    record = answer["result"]["records"][0]
    assert answer["result"]["kind"] == "partial"
    assert record["identity"] == "report-1"
    assert record["title"] == "原文包含 fixture 一词也不能改写"
    assert record["provided"]["description"] == "公开报告描述，不是全文"
    assert record["provided"]["version"] == "v3"
    assert record["unknowns"] == {
        "target": None, "author": None, "complete_trading_rules": None,
        "amount": None, "currency": None, "costs_included": None,
        "period": None, "market": None,
    }
    assert record["source"]["revision"] == model.data["reports"][0]["source_revision"]
    assert record["original"]["source_id"] == model.data["sources"][0]["source_id"]
    assert record["original"]["revision"] == model.data["sources"][0]["source_revision"]
    assert record["original"]["read_status"] == "known"
    assert record["original"]["readable"] is True
    assert answer["input"]["as_of"] is None
    assert "not_cross_resource_atomic" in answer["cannot_conclude"]
    assert "execution_is_not_research_success" in answer["cannot_conclude"]
    assert reading_answer(model, view="portal", commit="b" * 40) == answer


@pytest.mark.parametrize("failure", ["stale", "unreadable", "integrity_failure"])
def test_answer_key_does_not_certify_unreadable_or_mismatched_original(failure):
    from manager_gui.models import SourceReference

    original = {
        "source_id": "original-1", "source_revision": "v1", "snapshot_token": "view-1",
        "read_status": "known", "text": "Original support",
    }
    if failure == "stale":
        original["source_revision"] = "v2"
    elif failure == "unreadable":
        original.pop("text")
    else:
        original["read_status"] = failure
    model = ManagerReadModel(
        {"reports": [{
            "record_id": "report-1", "source_ref": "report-1",
            "snapshot_token": "view-1", "original_source_id": "original-1",
            "original_source_revision": "v1", "original_snapshot_token": "view-1",
        }], "sources": [original]},
        (SourceReference("original-1", "strategy-workspace", "artifact", "workspace://original",
                         revision="v1"),),
        None, "view-1", Derivation("direct"), Availability(ReadModelStatus.KNOWN, False),
    )
    record = reading_answer(model, view="portal", commit="c" * 40)["result"]["records"][0]
    assert record["original"]["readable"] is False
    assert record["original"]["limitation"] == failure


@pytest.mark.parametrize(
    "view,resource",
    [
        ("atlas", "atlas"), ("stories", "stories"), ("strategies", "genomes"),
        ("strategy-conditions", "genome_conditions"),
        ("strategy-genome-comparison", "genome_comparison"), ("memory", "memory"),
        ("memory-failures", "memory"), ("failure-patterns", "failure_patterns"),
        ("evidence", "evidence"), ("lineage", "lineage"),
        ("evidence-object-comparison", "evidence_comparison"),
        ("derived-failure-grouping", "failure_grouping"), ("methodology", "methodology"),
        ("history", "history"), ("source-documents", "source_documents"),
        ("search", "search"), ("portal", "report_source"),
    ],
)
def test_all_seventeen_answers_use_the_same_public_input_scope(tmp_path, view, resource):
    root = tmp_path / "isolated-workspace"
    WorkspaceClient(root).init()
    provider = WorkspaceDataProvider(root)
    model = provider.read(resource)
    answer = reading_answer(model, view=view, commit="d" * 40)
    assert answer["input"]["view"] == view
    assert answer["input"]["resource"] == resource
    assert answer["input"]["snapshot_token"] == provider.read().snapshot_token
    assert len(answer["coverage"]["application_read_view"]["resources"]) == 16
    assert answer["result"]["records"] == []
    assert "not_cross_resource_atomic" in answer["cannot_conclude"]
    assert "absence_not_confirmed" in answer["cannot_conclude"]
    assert answer["unknowns"]["complete_trading_rules"] is None


@pytest.mark.parametrize(
    "status,complete,data,kind",
    [
        (ReadModelStatus.KNOWN, True, {"genomes": []}, "confirmed_empty_within_scope"),
        (ReadModelStatus.KNOWN, False, {"genomes": []}, "partial"),
        (ReadModelStatus.KNOWN, True, {}, "fields_missing"),
        (ReadModelStatus.BLOCKED, False, {}, "blocked"),
        (ReadModelStatus.STALE, False, {}, "stale"),
        (ReadModelStatus.API_UNAVAILABLE, False, {}, "cannot_enumerate"),
        (ReadModelStatus.INTEGRITY_FAILURE, False, {}, "integrity_failure"),
        (ReadModelStatus.INCOMPARABLE, False, {}, "incomparable"),
        (ReadModelStatus.MISSING, False, {}, "missing"),
    ],
)
def test_answer_key_distinguishes_empty_partial_missing_and_failures(status, complete, data, kind):
    model = ManagerReadModel(
        data, (), None, "read-view", Derivation("direct"), Availability(status, complete),
    )
    answer = reading_answer(model, view="strategies", commit="e" * 40)
    assert answer["result"]["kind"] == kind
    assert ("absence_not_confirmed" in answer["cannot_conclude"]) == (
        kind != "confirmed_empty_within_scope"
    )


def test_answers_bind_actual_http_bytes_not_cli_output(tmp_path):
    from manager_gui.web import create_server

    root = tmp_path / "isolated-workspace"
    WorkspaceClient(root).init()
    server = create_server(provider=WorkspaceDataProvider(root), port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/api/read-model?view=atlas"
        with urlopen(url) as response:
            raw = response.read()
        model = ManagerReadModel.from_dict(json.loads(raw))
        answer = reading_answer(model, view="atlas", commit="f" * 40)
        assert answer["input"]["canonical_sha256"] == hashlib.sha256(raw).hexdigest()
        assert answer["input"]["canonical_bytes"] == len(raw)
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
