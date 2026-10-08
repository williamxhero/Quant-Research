from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from html import unescape
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import pytest
from strategy_workspace import WorkspaceClient, WorkspaceError

from manager_gui.models import Availability, Derivation, ManagerReadModel, ReadModelStatus
from manager_gui.web import ManagerGUIApp, create_server
from manager_gui.web.navigation import ViewId
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


@pytest.fixture
def read_guard(workspace, monkeypatch):
    allowed = {
        "list_runs",
        "list_records",
        "get_registered_package",
        "query_lineage",
        "read_artifact",
    }
    calls = []
    constructor = WorkspaceClient.__init__

    def readonly(self, root, **kwargs):
        assert kwargs.get("read_only") is True
        constructor(self, root, **kwargs)

    def deny(*args, **kwargs):
        pytest.fail("Owner write/non-approved operation during read-view consumption")

    def audit(method, name):
        def checked(self, *args, **kwargs):
            assert self.read_only
            if name != "query_lineage":
                assert "snapshot_token" not in kwargs and "cursor" not in kwargs
            calls.append((name, kwargs.copy()))
            return method(self, *args, **kwargs)

        return checked

    monkeypatch.setattr(WorkspaceClient, "__init__", readonly)
    for name in dir(WorkspaceClient):
        method = getattr(WorkspaceClient, name)
        if not name.startswith("_") and callable(method):
            monkeypatch.setattr(
                WorkspaceClient, name, audit(method, name) if name in allowed else deny
            )

    active = True
    root = workspace.resolve()

    def filesystem_sentinel(event, args):
        if not active:
            return
        if event == "open":
            path, _, flags = args
            mutating = flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            paths = (path,) if mutating else ()
        elif event in {"os.mkdir", "os.remove", "os.rmdir", "os.rename"}:
            paths = args[:2] if event == "os.rename" else args[:1]
        else:
            return
        for path in paths:
            if isinstance(path, (str, bytes, os.PathLike)):
                candidate = Path(os.fsdecode(path)).resolve()
                assert candidate != root and root not in candidate.parents

    sys.addaudithook(filesystem_sentinel)
    try:
        yield calls
    finally:
        active = False


@contextmanager
def serving(provider):
    server = create_server(provider=provider, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def get(path):
        with urlopen(f"http://127.0.0.1:{server.server_port}" + path, timeout=10) as response:
            assert response.status == 200
            return response.read()

    try:
        yield server.app, get
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        assert not thread.is_alive()


@pytest.mark.parametrize("event", ["open", "os.mkdir", "os.rename"])
def test_read_only_filesystem_sentinel_is_active(workspace, read_guard, event):
    args = {
        "open": (str(workspace / "would-write"), "wb", os.O_CREAT),
        "os.mkdir": (str(workspace), 0o777, -1),
        "os.rename": (str(workspace.parent / "outside"), str(workspace / "would-write"), -1, -1),
    }[event]
    with pytest.raises(AssertionError):
        sys.audit(event, *args)


@pytest.mark.parametrize("failure", ["unavailable", "integrity", "tampered-bytes"])
def test_source_failures_never_replace_old_evidence_or_verify_new_content(
    workspace, read_guard, monkeypatch, failure
):
    old_provider = WorkspaceDataProvider(workspace)
    old_app = ManagerGUIApp(old_provider)
    old_bytes = old_app.render_json("/?view=portal")
    actual_read = WorkspaceClient.read_artifact

    def failed_read(self, uri):
        if failure == "tampered-bytes":
            result = actual_read(self, uri)
            return {**result, "content": base64.b64encode(b"tampered bytes").decode()}
        code = "artifact_read_failed" if failure == "unavailable" else "artifact_integrity_failed"
        raise WorkspaceError(code, "Public original could not be verified")

    monkeypatch.setattr(WorkspaceClient, "read_artifact", failed_read)
    new_provider = WorkspaceDataProvider(workspace)
    model = new_provider.read("report_source")
    status = "api_unavailable" if failure == "unavailable" else "integrity_failure"
    assert model.data["sources"][0]["read_status"] == status
    assert "text" not in model.data["sources"][0]
    assert model.errors
    assert model.snapshot_token != old_provider.read().snapshot_token
    assert old_app.render_json("/?view=portal") == old_bytes
    assert "original report v1" in old_bytes
    with serving(new_provider) as (app, get):
        for lang in ("zh-CN", "en"):
            for mode in ("reader", "expert", "raw"):
                query = f"?view=portal&lang={lang}&mode={mode}"
                assert json.loads(get("/api/read-model" + query)) == model.to_dict()
                assert json.loads(get("/api/export" + query))["read_model"] == model.to_dict()
                assert get("/" + query) == app.render("/" + query).encode()
        reader = get("/?view=portal&lang=en").decode()
        assert (
            "Cannot open the original; this content cannot be treated as verified support."
            in reader
        )
        assert "The source reports a read, version, or integrity problem" in reader


def test_caller_cannot_mutate_frozen_public_input(workspace):
    provider = WorkspaceDataProvider(workspace)
    expected = provider.read("report_source").to_json()
    supplied = provider.read("report_source")
    supplied.data["reports"][0]["summary"] = "Caller replacement"
    supplied.data["public_input"]["records"].clear()
    supplied.data["sources"][0]["text"] = "Caller replacement"
    assert (
        provider.read("report_source", snapshot_token=supplied.snapshot_token).to_json() == expected
    )


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


@pytest.mark.parametrize("resource", ["genomes", "methodology", "memory"])
def test_unmapped_resources_keep_empty_data_and_declare_the_view_in_failure_details(
    workspace, resource
):
    model = WorkspaceDataProvider(workspace).read(resource)
    assert model.data == {}
    assert model.source_refs == ()
    assert model.errors[0].details["coverage"]["resource"] == resource
    assert set(model.errors[0].details["coverage"]["application_read_view"]["resources"]) == set(
        RESOURCES
    )


@pytest.mark.parametrize("resource", RESOURCES)
def test_all_resources_declare_the_same_bounded_application_view(workspace, resource):
    provider = WorkspaceDataProvider(workspace)
    model = provider.read(resource)
    scope = (
        model.data["coverage"]
        if model.availability.status is ReadModelStatus.KNOWN
        else model.errors[0].details["coverage"]
    )
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


@pytest.mark.parametrize(
    "token_query",
    [
        "snapshot_token=",
        "snapshot_token=%20",
        "snapshot_token=frozen-read&snapshot_token=unknown",
        "snapshot_token=frozen-read&snapshot=unknown",
    ],
)
def test_resource_read_failure_does_not_override_invalid_token_rejection(token_query):
    class FailedProvider:
        def read(self, resource="atlas", *, snapshot_token=None):
            raise OSError("Public Memory read failed")

    with serving(FailedProvider()) as (app, get):
        query = "?view=memory-failures&" + token_query
        expected = app.render_json(query).encode()
        model = json.loads(expected)
        assert model["availability"]["status"] == "stale"
        assert model["errors"][0]["code"] == "snapshot_drift"
        assert model["data"] == {}
        assert get("/api/read-model" + query) == expected
        assert json.loads(get("/api/export" + query))["read_model"] == model
        assert 'data-status="stale"' in get("/" + query).decode()


def test_resource_read_failure_preserves_requested_view_and_existing_failure_envelope():
    class FailedProvider:
        def read(self, resource="atlas", *, snapshot_token=None):
            assert resource == "memory" and snapshot_token == "frozen-read"
            raise WorkspaceError("owner_unavailable", "Public Memory read failed")

    with serving(FailedProvider()) as (app, get):
        base = "?view=memory-failures&snapshot_token=frozen-read"
        expected = app.render_json(base).encode()
        model = json.loads(expected)
        assert model["availability"]["status"] == "api_unavailable"
        assert model["snapshot_token"] == "frozen-read"
        assert model["data"] == {} and model["source_refs"] == []
        assert model["errors"][0]["code"] == "provider_read_failed"
        assert model["errors"][0]["details"]["owner_code"] == "owner_unavailable"
        for lang in ("zh-CN", "en"):
            for mode in ("reader", "expert", "raw"):
                query = base + f"&lang={lang}&mode={mode}"
                assert get("/api/read-model" + query) == get("/api/read-model" + query) == expected
                assert json.loads(get("/api/export" + query))["read_model"] == model
                document = get("/" + query)
                assert document == get("/" + query) == app.render("/" + query).encode()
                assert "Public Memory read failed" in document.decode()
                assert 'data-resource-reading="memory"' in document.decode()
                assert 'data-sample-banner="fixture"' not in document.decode()


def test_resource_notice_cannot_turn_an_unhonored_token_into_confirmed_empty():
    latest = ManagerReadModel(
        {"memory_entries": [], "failures": []},
        (),
        None,
        "latest-read",
        Derivation("direct"),
        Availability(ReadModelStatus.KNOWN, True),
    )

    class IgnoringProvider:
        def read(self, resource="atlas", *, snapshot_token=None):
            return latest

    with serving(IgnoringProvider()) as (app, get):
        query = "?view=memory-failures&lang=en&snapshot_token=old-read"
        model = json.loads(get("/api/read-model" + query))
        assert model["availability"]["status"] == "stale"
        assert model["snapshot_token"] == "old-read" and model["data"] == {}
        assert json.loads(get("/api/export" + query))["read_model"] == model
        document = get("/" + query).decode()
        assert 'data-status="stale"' in document
        assert "Public read confirmed: no records" not in document
        assert json.loads(app.render_json(query)) == model


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


@pytest.mark.parametrize("lang,label", [("en", "Workspace read view"), ("zh-CN", "工作区只读视图")])
def test_owner_page_names_application_view_not_fixture_snapshot(workspace, lang, label):
    app = ManagerGUIApp(WorkspaceDataProvider(workspace))
    document = app.render("/?view=portal&lang=" + lang)
    note = unescape(re.search(r'<span class="workspace-note">(.*?)</span>', document)[1])
    assert label in note
    assert "fixture workspace" not in note and "样例数据" not in note
    assert app.read_model(app.request_state("/")).snapshot_token in note


def test_page_export_and_navigation_pin_the_observed_input(workspace):
    app = ManagerGUIApp(WorkspaceDataProvider(workspace))
    token = app.read_model(app.request_state("/")).snapshot_token
    document = app.render("/?view=portal&lang=en")
    export_url = unescape(re.search(r'data-export-url="([^"]+)"', document)[1])
    assert "snapshot_token=" + token in export_url
    payload = json.loads(unescape(re.search(r'data-export-payload="([^"]+)"', document)[1]))
    assert payload == json.loads(app.render_export(export_url))
    links = re.findall(r'class="(?:nav-link|reading-task-link)"[^>]*href="([^"]+)"', document)
    assert links and all("snapshot_token=" + token in unescape(link) for link in links)
    assert 'name="snapshot_token" value="' + token + '"' in document


@pytest.mark.parametrize("view", list(ViewId))
def test_public_http_matrix_reuses_canonical_bytes(workspace, read_guard, view):
    provider = WorkspaceDataProvider(workspace)
    initial_calls = list(read_guard)
    token = provider.read().snapshot_token
    with serving(provider) as (app, get):
        expected = app.render_json("/?view=" + view.value).encode()
        for context in (
            "",
            "&filter=a&filter=&filter=a&root=study-1&scope=A0&record_id=report-1",
            "&q=&q=ignored&root=&scope=&object_id=&opaque_ref=&filter=&filter=",
        ):
            base = "?" + urlencode({"view": view.value, "snapshot_token": token}) + context
            expected_export = app.render_export(base).encode()
            for lang in ("zh-CN", "en"):
                for mode in ("reader", "expert", "raw"):
                    query = base + f"&lang={lang}&mode={mode}"
                    assert (
                        app.read_model(app.request_state(query)).to_json(indent=2).encode()
                        == expected
                    )
                    assert app.render_json(query).encode() == expected
                    assert app.render_export(query).encode() == expected_export
                    assert (
                        get("/api/read-model" + query) == get("/api/read-model" + query) == expected
                    )
                    assert (
                        get("/api/export" + query) == get("/api/export" + query) == expected_export
                    )
                    document = get("/" + query)
                    assert document == get("/" + query) == app.render("/" + query).encode()
                    raw = unescape(
                        re.search(
                            r'<pre class="raw-json"[^>]*>(.*?)</pre>', document.decode(), re.S
                        )[1]
                    )
                    assert raw.encode() == expected
                    embedded = json.loads(
                        unescape(re.search(r'data-export-payload="([^"]+)"', document.decode())[1])
                    )
                    assert embedded["read_model"] == json.loads(expected)
                    assert (
                        app.reader_projection(query).raw_source.raw_bytes
                        == app.read_model(app.request_state(query)).to_json().encode()
                    )
    assert read_guard == initial_calls
    assert {name for name, _ in read_guard} == {"list_runs", "list_records", "read_artifact"}


def test_input_updates_keep_old_bytes_and_reject_old_tokens_in_new_views(workspace, tmp_path):
    first = WorkspaceDataProvider(workspace)
    first_app = ManagerGUIApp(first)
    old_token = first.read().snapshot_token
    query = "?view=portal&snapshot_token=" + old_token
    old_json, old_export, old_page = (
        first_app.render_json(query),
        first_app.render_export(query),
        first_app.render(query),
    )
    owner = WorkspaceClient(workspace)
    owner.publish_record(
        {
            "record_id": "report-2",
            "record_type": "apex-research.study-report-source.v1",
            "created_at": "2026-10-08T10:00:00Z",
            "payload": {
                "schema": "apex-research.study-report-source.v1",
                "title": "更新研究报告",
                "body": "更新报告正文",
                "subject_id": "study-1",
                "version": "v2",
            },
        },
        artifacts=[{"source": b"original report v2", "media_type": "text/plain"}],
    )
    second = WorkspaceDataProvider(workspace)
    new_token = second.read().snapshot_token
    assert old_token != new_token
    assert first_app.render_json(query) == old_json
    assert first_app.render_export(query) == old_export
    assert first_app.render(query) == old_page
    assert "更新报告正文" not in old_json
    assert "original report v2" not in old_export
    assert "更新报告正文" in ManagerGUIApp(second).render_json("/?view=portal")
    same_new_input = WorkspaceDataProvider(workspace)
    assert same_new_input.read().snapshot_token == new_token
    assert same_new_input.read("report_source").to_json() == second.read("report_source").to_json()

    other_root = tmp_path / "other-workspace"
    WorkspaceClient(other_root).init()
    other = WorkspaceDataProvider(other_root)
    assert other.read().snapshot_token != new_token
    for provider in (second, other):
        with serving(provider) as (app, get):
            for token in (old_token, "unknown", ""):
                rejected_query = "?view=portal&snapshot_token=" + token
                raw = get("/api/read-model" + rejected_query)
                rejected = json.loads(raw)
                exported = json.loads(get("/api/export" + rejected_query))
                assert rejected["availability"]["status"] == "stale"
                assert rejected["data"] == {}
                assert rejected["source_refs"] == []
                assert exported["read_model"] == rejected
                assert raw == app.render_json(rejected_query).encode()
                assert "更新报告正文" not in get("/" + rejected_query).decode()
    assert (
        first.read("report_source", snapshot_token=new_token).availability.status
        is ReadModelStatus.STALE
    )


def test_lineage_without_public_key_is_disclosed_without_initialization(workspace, request):
    WorkspaceClient(workspace).publish_record(
        {
            "record_id": "unready-lineage",
            "record_type": "apex-research.research-conclusion.v1",
            "payload": {"schema": "apex-research.research-conclusion.v1"},
            "lineage": [
                {"source_kind": "publication", "source_id": "report-1", "relation": "supported_by"}
            ],
        }
    )
    calls = request.getfixturevalue("read_guard")
    provider = WorkspaceDataProvider(workspace)
    model = provider.read("lineage")
    assert model.availability.status is ReadModelStatus.API_UNAVAILABLE
    assert model.errors
    assert model.data["public_input"]["lineage_pages"] == []
    assert "query_lineage" in {name for name, _ in calls}
    document = ManagerGUIApp(provider).render("/?view=lineage&lang=en")
    assert model.errors[0].code in document
    assert provider.read("lineage").to_json() == model.to_json()


def test_lineage_tokens_remain_scoped_paged_and_expiring(workspace):
    owner = WorkspaceClient(workspace)
    for index in range(101):
        owner.publish_record(
            {
                "record_id": f"parent-{index:03d}",
                "record_type": "apex-research.evidence.v1",
                "created_at": "2026-10-08T09:00:00Z",
                "payload": {"schema": "apex-research.evidence.v1"},
            }
        )
    owner.publish_record(
        {
            "record_id": "lineage-root",
            "record_type": "apex-research.research-conclusion.v1",
            "created_at": "2026-10-08T10:00:00Z",
            "payload": {"schema": "apex-research.research-conclusion.v1"},
            "lineage": [
                {
                    "source_kind": "publication",
                    "source_id": f"parent-{index:03d}",
                    "relation": "supported_by",
                }
                for index in range(101)
            ],
        }
    )
    owner.query_lineage(
        roots=[{"kind": "publication", "id": "lineage-root"}], direction="ancestors"
    )
    provider = WorkspaceDataProvider(workspace, limit=3)
    model = provider.read("lineage")
    page = model.data["public_input"]["lineage_pages"][0]
    assert len(page["records"]) == 100
    assert page["next_cursor"]
    assert model.data["pagination"] == {"complete": False, "has_more": True}
    assert model.data["coverage"]["publications_limit_reached"] is True
    assert model.data["coverage"]["lineage_pages"][0]["snapshot_token"] == page["snapshot_token"]
    query = {
        "roots": [{"kind": "publication", "id": "lineage-root"}],
        "direction": "ancestors",
        "relations": [],
        "record_types": [],
        "max_depth": 1,
        "page_size": 100,
        "snapshot_token": page["snapshot_token"],
        "cursor": page["next_cursor"],
    }
    readonly = WorkspaceClient(workspace, read_only=True)
    continuation = readonly.query_lineage(**query)
    assert len(continuation["records"]) == 1 and continuation["next_cursor"] is None
    with pytest.raises(WorkspaceError) as mismatch:
        readonly.query_lineage(**{**query, "page_size": 99})
    assert mismatch.value.code == "lineage_cursor_query_mismatch"
    late = WorkspaceClient(
        workspace, read_only=True, clock=lambda: datetime.now(UTC) + timedelta(days=1)
    )
    with pytest.raises(WorkspaceError) as expired:
        late.query_lineage(**query)
    assert expired.value.code == "expired_lineage_cursor"
    for owner_token in (page["snapshot_token"], page["next_cursor"]):
        for resource in RESOURCES:
            rejected = provider.read(resource, snapshot_token=owner_token)
            assert rejected.availability.status is ReadModelStatus.STALE and rejected.data == {}
    assert (
        provider.read("lineage", snapshot_token=model.snapshot_token).to_json() == model.to_json()
    )


def test_bytes_are_stable_across_process_hash_seeds(workspace):
    code = """
import hashlib, json, sys
from manager_gui.web import ManagerGUIApp
from manager_gui.web.navigation import ViewId
from manager_gui.workspace import WorkspaceDataProvider
app = ManagerGUIApp(WorkspaceDataProvider(sys.argv[1]))
print(json.dumps([
    hashlib.sha256(method('/?view=' + view.value).encode()).hexdigest()
    for view in ViewId for method in (app.render_json, app.render_export, app.render)
]))
"""
    outputs = [
        subprocess.check_output(
            [sys.executable, "-c", code, str(workspace)],
            env={**os.environ, "PYTHONHASHSEED": seed, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        for seed in ("1", "7", "23")
    ]
    assert outputs[0] == outputs[1] == outputs[2]


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
