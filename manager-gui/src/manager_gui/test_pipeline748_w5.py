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


def test_large_public_original_does_not_expand_initial_atlas_html(tmp_path):
    from manager_gui.web import ManagerGUIApp

    root = tmp_path / "isolated-workspace"
    owner = WorkspaceClient(root)
    owner.init()
    owner.publish_record(
        {
            "record_id": "large-report",
            "record_type": "apex-research.study-report-source.v1",
            "payload": {
                "schema": "apex-research.study-report-source.v1",
                "title": "Large public report",
                "description": "Metadata is not the original report.",
                "subject_id": "study-large",
                "version": "v1",
            },
        },
        artifacts=[{"source": b"public original & < > " * 80000, "media_type": "text/plain"}],
    )
    app = ManagerGUIApp(provider=WorkspaceDataProvider(root))
    document = app.render("/?view=atlas&lang=zh-CN&mode=reader")
    assert len(document.encode("utf-8")) <= 20_000_000
    assert "Large public report" in document
    import re
    from html import unescape

    urls = re.findall(r'data-demand-url="([^"]+)"', document)
    contents = [app.render(unescape(url)) for url in urls]
    assert any("Metadata is not the original report." in content for content in contents)
    assert any("public original &amp; &lt; &gt;" in content for content in contents)


@pytest.fixture(scope="module")
def large_public_app(tmp_path_factory):
    from manager_gui.web import ManagerGUIApp

    root = tmp_path_factory.mktemp("demand-workspace")
    owner = WorkspaceClient(root)
    owner.init()
    owner.publish_record(
        {
            "record_id": "demand-report",
            "record_type": "apex-research.study-report-source.v1",
            "payload": {
                "schema": "apex-research.study-report-source.v1",
                "title": "Demand report",
                "description": "Only a description",
                "version": "v3",
            },
        },
        artifacts=[{"source": b"DEMAND_ORIGINAL & < > " * 80000, "media_type": "text/plain"}],
    )
    owner.publish_record({
        "record_id": "second-report", "record_type": "apex-research.study-report-source.v1",
        "payload": {"schema": "apex-research.study-report-source.v1", "title": "Second report"},
    })
    return ManagerGUIApp(provider=WorkspaceDataProvider(root))


def test_demanded_count_pagination_preserves_entry_context_and_all_inputs(large_public_app):
    import re
    from html import unescape

    url = "/?view=atlas&lang=en&mode=reader&filter=x&filter=&filter=x&page=1"
    document = large_public_app.render(url)
    target = unescape(re.findall(r'data-demand-url="([^"]+)"', document)[0])
    first = large_public_app.render(target)
    second = large_public_app.render(target + "&ui_page=2")
    assert first != second
    assert ("Second report" in first) != ("Second report" in second)
    assert ("Demand report" in first) != ("Demand report" in second)
    assert "filter=x&amp;filter=&amp;filter=x" in target.replace("&", "&amp;")
    assert "ui_page=2" in first
    assert large_public_app.render_json(url) == large_public_app.render_json(target + "&ui_page=2")


def test_demanded_public_original_has_a_readable_body_not_just_metadata(large_public_app):
    import re
    from html import unescape

    document = large_public_app.render("/?view=atlas&lang=en&mode=reader")
    target = unescape(re.findall(r'data-demand-url="([^"]+)"', document)[1])
    content = large_public_app.render(target)
    assert "data-support-original" in content
    assert 'translate="no">DEMAND_ORIGINAL &amp; &lt; &gt; ' in content
    assert "demand-report" not in re.search(
        r'data-support-original>.*?</a><section[^>]*>.*?<pre[^>]*>(.*?)</pre>', content, re.S,
    ).group(1)


@pytest.mark.parametrize("lang", ["zh-CN", "en"])
@pytest.mark.parametrize("mode", ["reader", "expert", "raw"])
def test_demand_transport_keeps_published_reader_and_canonical_contract(
    large_public_app, lang, mode,
):
    import re
    from html import unescape

    from manager_gui.reader.mode import reader_contract_payload
    from manager_gui.web import create_server

    url = f"/?view=atlas&lang={lang}&mode={mode}&filter=x&filter=&root="
    document = large_public_app.render(url)
    target = unescape(re.search(r'data-reader-contract-url="([^"]+)"', document).group(1))
    server = create_server(app=large_public_app, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        with urlopen(base + target) as response:
            raw = response.read()
            assert response.headers["Content-Type"].startswith("application/json")
        payload = json.loads(raw)
        assert payload == reader_contract_payload(large_public_app.reader_projection(url), mode)
        canonical = json.loads(large_public_app.render_json(url))
        assert payload["projection"]["raw_source"]["sha256"] == hashlib.sha256(
            large_public_app.reader_projection(url).raw_source.raw_bytes
        ).hexdigest()
        assert payload["projection"]["data"] == canonical["data"]
        assert payload["projection"]["snapshot_token"] == canonical["snapshot_token"]
        from urllib.request import Request
        with urlopen(Request(base + target, method="HEAD")) as response:
            assert response.read() == b""
            assert int(response.headers["Content-Length"]) == len(raw)
        assert large_public_app.render_json(url) == large_public_app.render_json(target)
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@pytest.mark.parametrize("selection", ["not-a-number", "-1", "999999"])
def test_invalid_demand_selection_cannot_substitute_another_original(large_public_app, selection):
    content = large_public_app.render(f"/?view=atlas&lang=en&ui_support={selection}")
    assert "verification is incomplete" in content
    assert "DEMAND_ORIGINAL" not in content
    assert "data-support-original" not in content


def test_demanded_raw_pagination_retains_full_canonical_text(large_public_app):
    import re
    from html import unescape

    url = "/?view=atlas&mode=raw"
    text = large_public_app.reader_projection(url).raw_source.raw_bytes.decode("utf-8")
    fragments = []
    for page in range(1, (len(text) + 99999) // 100000 + 1):
        document = large_public_app.render(url + f"&ui_raw=1&ui_page={page}")
        fragments.append(unescape(re.search(r'<pre[^>]*>(.*?)</pre>', document, re.S).group(1)))
        assert len(document.encode("utf-8")) < 1_000_000
    assert "".join(fragments) == text


@pytest.mark.parametrize("view", ["atlas", "stories", "evidence", "lineage", "history",
                                  "source-documents", "search", "portal"])
@pytest.mark.parametrize("lang", ["zh-CN", "en"])
@pytest.mark.parametrize("mode", ["reader", "expert", "raw"])
def test_large_pages_defer_originals_in_all_languages_and_modes(large_public_app, view, lang, mode):
    document = large_public_app.render(f"/?view={view}&lang={lang}&mode={mode}")
    assert len(document.encode("utf-8")) <= 20_000_000
    assert "DEMAND_ORIGINAL" not in document
    assert f'data-reader-route-mode="{mode}"' in document
    assert f'<html lang="{lang}">' in document


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
