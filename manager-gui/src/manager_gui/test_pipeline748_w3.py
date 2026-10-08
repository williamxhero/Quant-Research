from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Thread
from urllib.request import urlopen

import pytest
from strategy_workspace import WorkspaceClient, WorkspaceError

from manager_gui.models import (
    Availability,
    Derivation,
    ManagerReadModel,
    ReadModelError,
    ReadModelStatus,
    SourceReference,
)
from manager_gui.web import ManagerGUIApp
from manager_gui.web.server import create_server
from manager_gui.workspace import WorkspaceDataProvider

VIEWS = (
    ("strategies", "genomes"),
    ("strategy-conditions", "genome_conditions"),
    ("strategy-genome-comparison", "genome_comparison"),
    ("memory", "memory"),
    ("memory-failures", "memory"),
    ("failure-patterns", "failure_patterns"),
    ("derived-failure-grouping", "failure_grouping"),
    ("evidence-object-comparison", "evidence_comparison"),
    ("methodology", "methodology"),
)


@pytest.fixture
def workspace_provider(tmp_path):
    WorkspaceClient(tmp_path).init()
    return WorkspaceDataProvider(tmp_path)


@pytest.mark.parametrize(("view", "resource"), VIEWS)
@pytest.mark.parametrize("lang", ("zh-CN", "en"))
@pytest.mark.parametrize("mode", ("reader", "expert", "raw"))
def test_public_workspace_without_enumeration_is_not_an_empty_catalog(
    workspace_provider, view, resource, lang, mode
):
    app = ManagerGUIApp(workspace_provider)
    url = f"/?view={view}&lang={lang}&mode={mode}&scope=isolated-zero-genomes"
    model = json.loads(app.render_json(url))
    assert model["availability"]["status"] == "api_unavailable"
    assert model["availability"]["complete"] is False
    html = app.render(url)
    expected = (
        "当前公共接口无法列出" if lang == "zh-CN" else "The current public interface cannot list"
    )
    assert expected in html
    assert f'data-resource-reading="{resource}"' in html
    assert 'data-sample-banner="fixture"' not in html
    assert "isolated-zero-genomes" in html
    assert json.loads(app.render_export(url))["read_model"] == model


COLLECTIONS = {
    "strategies": "genomes",
    "strategy-conditions": "conditions",
    "strategy-genome-comparison": "comparisons",
    "memory": "memory_entries",
    "memory-failures": "failures",
    "failure-patterns": "patterns",
    "derived-failure-grouping": "groups",
    "evidence-object-comparison": "comparisons",
    "methodology": "methods",
}


class PublicResourceProvider:
    def __init__(self, resource, model):
        self.resource = resource
        self.model = model

    def read(self, resource="atlas", *, snapshot_token=None):
        assert resource == self.resource
        assert snapshot_token in (None, self.model.snapshot_token)
        return self.model


def resource_model(data, *, status=ReadModelStatus.KNOWN, complete=True, errors=()):
    return ManagerReadModel(
        data,
        (
            SourceReference(
                "public-record-17",
                "test-owner",
                "publication",
                "workspace://record/public-record-17",
            ),
        ),
        None,
        "public-read-17",
        Derivation("direct"),
        Availability(status, complete, "Public scope: isolated research collection."),
        errors,
    )


@pytest.mark.parametrize(("view", "resource"), VIEWS)
@pytest.mark.parametrize("lang", ("zh-CN", "en"))
@pytest.mark.parametrize("mode", ("reader", "expert", "raw"))
def test_only_explicit_successful_complete_collection_reads_confirm_no_records(
    view, resource, lang, mode
):
    model = resource_model({COLLECTIONS[view]: []})
    app = ManagerGUIApp(PublicResourceProvider(resource, model))
    url = f"/?view={view}&lang={lang}&mode={mode}&snapshot_token=public-read-17"
    html = app.render(url)
    expected = (
        "公共读取确认：当前范围没有记录"
        if lang == "zh-CN"
        else "Public read confirmed: no records in the current scope"
    )
    assert expected in html
    assert "Public scope: isolated research collection." in html
    assert json.loads(app.render_json(url)) == model.to_dict()
    assert json.loads(app.render_export(url))["read_model"] == model.to_dict()


@pytest.mark.parametrize(("view", "resource"), VIEWS)
@pytest.mark.parametrize("lang", ("zh-CN", "en"))
@pytest.mark.parametrize(
    ("status", "complete", "errors", "zh", "en"),
    (
        (
            ReadModelStatus.MISSING,
            False,
            (),
            "字段或集合未记录",
            "The field or collection is not recorded",
        ),
        (
            ReadModelStatus.KNOWN,
            False,
            (),
            "当前可读取范围尚不完整",
            "The currently readable scope is incomplete",
        ),
        (ReadModelStatus.BLOCKED, False, (), "公共读取被阻塞", "Public reading is blocked"),
        (ReadModelStatus.STALE, False, (), "读取结果已过时", "The read result is stale"),
        (
            ReadModelStatus.INTEGRITY_FAILURE,
            False,
            (),
            "读取完整性验证失败",
            "Read integrity validation failed",
        ),
        (
            ReadModelStatus.INCOMPARABLE,
            False,
            (),
            "对象或条件不可比",
            "Objects or conditions are incomparable",
        ),
        (
            ReadModelStatus.API_UNAVAILABLE,
            False,
            (ReadModelError("read_failed", "Owner read failed", "public-record-17"),),
            "公共读取失败",
            "Public reading failed",
        ),
        (
            ReadModelStatus.KNOWN,
            True,
            (
                ReadModelError(
                    "source_unreadable", "Original source could not be read", "public-record-17"
                ),
            ),
            "公共读取失败",
            "Public reading failed",
        ),
    ),
)
def test_missing_blocked_stale_integrity_incomparable_and_errors_are_not_empty(
    view, resource, lang, status, complete, errors, zh, en
):
    model = resource_model({COLLECTIONS[view]: []}, status=status, complete=complete, errors=errors)
    app = ManagerGUIApp(PublicResourceProvider(resource, model))
    for mode in ("reader", "expert", "raw"):
        html = app.render(f"/?view={view}&lang={lang}&mode={mode}")
        assert (zh if lang == "zh-CN" else en) in html
        assert "公共读取确认：当前范围没有记录" not in html
        assert "Public read confirmed: no records in the current scope" not in html
        assert 'data-sample-banner="fixture"' not in html
        for error in errors:
            assert error.message in html


@pytest.mark.parametrize(("view", "resource"), VIEWS)
def test_present_object_without_collection_fields_is_not_an_empty_collection(view, resource):
    model = resource_model({"record_id": "public-record-17", "title": "Fieldless public object"})
    html = ManagerGUIApp(PublicResourceProvider(resource, model)).render(f"/?view={view}")
    assert "对象存在，但所需字段或集合未记录" in html
    assert "公共读取确认：当前范围没有记录" not in html
    assert "Fieldless public object" in html


LIVE_INPUTS = {
    "strategies": {
        "genomes": [
            {
                "genome_id": "live-genome-1",
                "title": "Observed strategy structure",
                "behavior": {"entry": {"description": "Enter only after the declared signal"}},
                "source_ref": "public-record-17",
            }
        ],
    },
    "strategy-conditions": {
        "genome_id": "live-genome-1",
        "conditions": [
            {
                "record_id": "live-condition-1",
                "category": "applicability",
                "condition": "Only the tested liquid-market subset",
                "outcome": "supported",
                "source_refs": ["public-record-17"],
            }
        ],
    },
    "strategy-genome-comparison": {
        "left": {"object_id": "live-left-1", "object_type": "genome", "axes": {"identity": "left"}},
        "right": {
            "object_id": "live-right-1",
            "object_type": "genome",
            "axes": {"identity": "right"},
        },
    },
    "memory": {
        "memory_entries": [
            {
                "memory_id": "live-memory-1",
                "title": "Independent published experience",
                "safe_summary": "The market-data gate must be checked before reuse",
                "source_ref": "public-record-17",
            }
        ],
    },
    "memory-failures": {
        "failures": [
            {
                "failure_id": "live-failure-1",
                "title": "Declared adapter failure experience",
                "summary": "The required input was absent in the tested adapter",
                "failure_category": "adapter_failure",
                "outcome": "execution_error",
                "references": ["public-record-17"],
            }
        ],
    },
    "failure-patterns": {
        "derived_patterns": [
            {
                "pattern_id": "live-pattern-1",
                "title": "Published adapter pattern",
                "rule": "group by failure_category and stage",
                "input_scope": ["live-failure-1"],
                "sample_count": 1,
                "failure_ids": ["live-failure-1"],
                "source_refs": ["public-record-17"],
            }
        ],
    },
    "derived-failure-grouping": {
        "rule": "bucket explicit terminal outcome by outcome and protocol",
        "input_scope": ["public-record-17"],
        "records": [{"record_id": "live-group-input-1", "outcome": "failed"}],
    },
    "evidence-object-comparison": {
        "left": {
            "object_id": "live-evidence-left-1",
            "object_type": "evidence",
            "axes": {"identity": "left"},
        },
        "right": {
            "object_id": "live-evidence-right-1",
            "object_type": "evidence",
            "axes": {"identity": "right"},
        },
    },
    "methodology": {
        "methods": [
            {
                "method_id": "live-method-1",
                "title": "Explicit research method",
                "category": "workflow_process",
                "definition": "Freeze the declared inputs before comparison",
                "source_refs": ["public-record-17"],
            }
        ],
    },
}


@pytest.mark.parametrize(("view", "resource"), VIEWS)
@pytest.mark.parametrize("lang", ("zh-CN", "en"))
@pytest.mark.parametrize("mode", ("reader", "expert", "raw"))
def test_new_public_resource_records_are_rendered_without_example_defaults(
    view, resource, lang, mode
):
    model = resource_model(LIVE_INPUTS[view])
    app = ManagerGUIApp(PublicResourceProvider(resource, model))
    url = f"/?view={view}&lang={lang}&mode={mode}&filter=a&filter=b&scope=isolated-live"
    html = app.render(url)
    expected = (
        "按本次公共输入呈现记录"
        if lang == "zh-CN"
        else "Records are shown from the supplied public input"
    )
    assert expected in html
    assert "公共读取确认：当前范围没有记录" not in html
    assert "fixture://" not in html
    assert 'data-sample-banner="fixture"' not in html
    assert "filter=a" in html and "filter=b" in html
    assert "public-record-17" in html
    assert "USD" not in json.dumps(model.data)
    assert json.loads(app.render_json(url)) == model.to_dict()
    exported = json.loads(app.render_export(url))
    assert exported["read_model"] == model.to_dict()
    assert exported["query_params"]["scope"] == "isolated-live"
    if "comparison" in resource:
        assert 'data-comparison-result="not_comparable"' in html
        assert 'name="ranking"' not in html


@pytest.mark.parametrize(
    ("view", "resource", "records"),
    (
        (
            "strategies",
            "genomes",
            [
                {
                    "record_id": "package-26",
                    "record_type": "package",
                    "title": "Package is not a Genome",
                }
            ],
        ),
        (
            "strategies",
            "genomes",
            [{"record_id": "failed-run-116", "record_type": "run", "outcome": "execution_error"}],
        ),
        (
            "memory-failures",
            "memory",
            [{"record_id": "failed-run-116", "record_type": "run", "outcome": "execution_error"}],
        ),
        (
            "memory",
            "memory",
            [
                {
                    "record_id": "report-summary",
                    "record_type": "report",
                    "summary": "Summary is not independent Memory",
                }
            ],
        ),
        (
            "failure-patterns",
            "failure_patterns",
            [{"record_id": "failed-run-116", "record_type": "run", "outcome": "execution_error"}],
        ),
        (
            "methodology",
            "methodology",
            [
                {
                    "record_id": "package-26",
                    "record_type": "package",
                    "title": "Package is not a method",
                }
            ],
        ),
        (
            "evidence-object-comparison",
            "evidence_comparison",
            [
                {
                    "record_id": "evidence-983",
                    "record_type": "evidence",
                    "summary": "Evidence alone is not a comparison",
                }
            ],
        ),
        (
            "derived-failure-grouping",
            "failure_grouping",
            [{"record_id": "failed-run-116", "record_type": "run", "outcome": "execution_error"}],
        ),
    ),
)
def test_unrelated_public_records_are_not_promoted_to_semantic_resources(view, resource, records):
    model = resource_model({"records": records})
    app = ManagerGUIApp(PublicResourceProvider(resource, model))
    for mode in ("reader", "expert", "raw"):
        html = app.render(f"/?view={view}&mode={mode}")
        assert "按本次公共输入呈现记录" not in html
        assert "对象存在，但所需字段或集合未记录" in html
        assert records[0]["record_id"] in html
        assert "公共读取确认：当前范围没有记录" not in html


@pytest.mark.parametrize(
    ("view", "data"),
    (("memory", {"failures": []}), ("memory-failures", {"memory_entries": []})),
)
def test_empty_sibling_collection_does_not_confirm_the_selected_collection(view, data):
    app = ManagerGUIApp(PublicResourceProvider("memory", resource_model(data)))
    html = app.render(f"/?view={view}")
    assert "公共读取确认：当前范围没有记录" not in html
    assert "对象存在，但所需字段或集合未记录" in html


@pytest.fixture
def http_server():
    servers = []

    def start(provider):
        server = create_server(provider=provider, port=0)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append((server, thread))
        return f"http://127.0.0.1:{server.server_port}"

    yield start
    for server, thread in servers:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def http_get(url):
    with urlopen(url, timeout=15) as response:
        assert response.status == 200
        return response.read().decode("utf-8")


@pytest.mark.parametrize(("view", "resource"), VIEWS)
@pytest.mark.parametrize("lang", ("zh-CN", "en"))
def test_workspace_provider_http_capability_gap_and_stale_token(
    workspace_provider, http_server, view, resource, lang
):
    base = http_server(workspace_provider)
    query = f"?view={view}&lang={lang}&scope=isolated-http"
    html = http_get(base + "/" + query)
    assert f'data-resource-reading="{resource}"' in html
    assert (
        "当前公共接口无法列出" if lang == "zh-CN" else "The current public interface cannot list"
    ) in html
    model = json.loads(http_get(base + "/api/read-model" + query))
    assert model["availability"]["status"] == "api_unavailable"
    assert json.loads(http_get(base + "/api/export" + query))["read_model"] == model
    stale_query = query + "&snapshot_token=unknown-public-view"
    assert ("读取结果已过时" if lang == "zh-CN" else "The read result is stale") in http_get(
        base + "/" + stale_query
    )
    assert (
        json.loads(http_get(base + "/api/read-model" + stale_query))["availability"]["status"]
        == "stale"
    )


@pytest.mark.parametrize(("view", "resource"), VIEWS)
@pytest.mark.parametrize("lang", ("zh-CN", "en"))
@pytest.mark.parametrize("scenario", ("confirmed_empty", "read_error", "live"))
def test_public_resource_http_empty_error_and_nonempty_reads(
    http_server, view, resource, lang, scenario
):
    data = LIVE_INPUTS[view] if scenario == "live" else {COLLECTIONS[view]: []}
    errors = (
        (ReadModelError("owner_read_failed", "Owner failed to read source-17", "public-record-17"),)
        if scenario == "read_error"
        else ()
    )
    model = resource_model(data, errors=errors)
    base = http_server(PublicResourceProvider(resource, model))
    for mode in ("reader", "expert", "raw"):
        query = f"?view={view}&lang={lang}&mode={mode}&snapshot_token=public-read-17"
        html = http_get(base + "/" + query)
        assert f'data-resource-reading="{resource}"' in html
        expected = {
            "confirmed_empty": (
                "公共读取确认：当前范围没有记录",
                "Public read confirmed: no records in the current scope",
            ),
            "read_error": ("公共读取失败", "Public reading failed"),
            "live": ("按本次公共输入呈现记录", "Records are shown from the supplied public input"),
        }[scenario][lang == "en"]
        assert expected in html
        assert 'data-sample-banner="fixture"' not in html
        assert json.loads(http_get(base + "/api/read-model" + query)) == model.to_dict()
        assert json.loads(http_get(base + "/api/export" + query))["read_model"] == model.to_dict()


def test_workspace_public_inputs_do_not_create_semantic_records_or_use_writes(
    tmp_path, monkeypatch
):
    client = WorkspaceClient(tmp_path)
    client.init()
    client.publish_record(
        {
            "record_id": "report-source-17",
            "record_type": "apex-research.study-report-source.v1",
            "payload": {
                "schema": "apex-research.study-report-source.v1",
                "summary": "Report is not Memory",
                "method_protocol": "Report is not a method",
            },
        }
    )

    def forbidden_write(*args, **kwargs):
        pytest.fail("W3 used an owner write or unapproved read")

    for name in (
        "init",
        "register_package",
        "publish_record",
        "submit_run",
        "propose_genome",
        "publish_genome",
        "genome_operation",
        "get_genome",
        "inspect_package",
        "validate_parameters",
        "verify_artifact",
        "doctor",
    ):
        monkeypatch.setattr(WorkspaceClient, name, forbidden_write)

    monkeypatch.setattr(
        WorkspaceClient,
        "list_runs",
        lambda self, **kw: [
            {
                "run_id": "failed-run-116",
                "status": "failed",
                "request": {"strategy_package": "package-26"},
                "result": {
                    "schema": "quant-research.result.v1",
                    "summary": "Run failure is not failure experience",
                },
            }
        ],
    )
    monkeypatch.setattr(
        WorkspaceClient,
        "get_registered_package",
        lambda self, ref: {
            "package_ref": ref,
            "title": "Package is not a Genome or a method",
        },
    )
    provider = WorkspaceDataProvider(tmp_path)
    atlas = provider.read("atlas").data
    assert atlas["public_input"]["packages"][0]["package_ref"] == "package-26"
    assert atlas["public_input"]["runs"][0]["status"] == "failed"
    assert atlas["public_input"]["records"][0]["record_id"] == "report-source-17"
    app = ManagerGUIApp(provider)
    for view, _ in VIEWS:
        html = app.render(f"/?view={view}")
        assert "当前公共接口无法列出" in html
        assert "公共读取确认：当前范围没有记录" not in html
        model = json.loads(app.render_json(f"/?view={view}"))
        assert model["data"] == {}
        assert model["availability"]["status"] == "api_unavailable"


def test_no_inputs_produce_no_groups_and_concurrent_languages_do_not_change_facts():
    model = resource_model(
        {
            "rule": "bucket explicit terminal outcome by outcome and protocol",
            "input_scope": ["empty-public-input"],
            "records": [],
        }
    )
    app = ManagerGUIApp(PublicResourceProvider("failure_grouping", model))
    urls = [
        f"/?view=derived-failure-grouping&lang={lang}&mode={mode}"
        for lang in ("zh-CN", "en")
        for mode in ("reader", "expert", "raw")
    ]
    with ThreadPoolExecutor(max_workers=6) as pool:
        pages = list(pool.map(app.render, urls))
    for page in pages:
        assert 'data-group-outcome="failure"' not in page
        assert 'data-group-outcome="success"' not in page
        assert "empty-public-input" in page
    assert len({app.render_json(url) for url in urls}) == 1


@pytest.mark.parametrize(("view", "resource"), VIEWS)
@pytest.mark.parametrize(
    "failure",
    (
        OSError("Public connection failed"),
        WorkspaceError("owner_unavailable", "Public owner read failed"),
    ),
)
def test_provider_read_exceptions_use_existing_error_envelope_instead_of_http_500(
    http_server, view, resource, failure
):
    class FailedPublicProvider:
        def read(self, requested="atlas", *, snapshot_token=None):
            assert requested == resource
            raise failure

    app = ManagerGUIApp(FailedPublicProvider())
    model = json.loads(app.render_json(f"/?view={view}"))
    assert model["availability"]["status"] == "api_unavailable"
    assert model["availability"]["complete"] is False
    assert model["errors"][0]["message"] == str(failure)
    assert model["data"] == {}
    base = http_server(FailedPublicProvider())
    for mode in ("reader", "expert", "raw"):
        html = http_get(base + f"/?view={view}&mode={mode}")
        assert "公共读取失败" in html
        assert 'data-sample-banner="fixture"' not in html
    assert json.loads(http_get(base + f"/api/read-model?view={view}")) == model
    assert json.loads(http_get(base + f"/api/export?view={view}"))["read_model"] == model


@pytest.mark.parametrize(("view", "resource"), VIEWS)
@pytest.mark.parametrize(
    "status",
    (ReadModelStatus.STALE, ReadModelStatus.INTEGRITY_FAILURE, ReadModelStatus.INCOMPARABLE),
)
def test_unusable_nonempty_inputs_preserve_identity_and_unknown_fields(view, resource, status):
    model = resource_model(LIVE_INPUTS[view], status=status, complete=False)
    app = ManagerGUIApp(PublicResourceProvider(resource, model))
    for lang in ("zh-CN", "en"):
        for mode in ("reader", "expert", "raw"):
            url = f"/?view={view}&lang={lang}&mode={mode}&scope=isolated-unusable"
            html = app.render(url)
            assert f'data-status="{status.value}"' in html
            assert "public-record-17" in html
            assert "isolated-unusable" in html
            assert "公共读取确认：当前范围没有记录" not in html
            assert ">USD<" not in html and ">CNY<" not in html
            if view == "strategies" and lang == "en" and mode == "reader":
                assert "CNY cannot be assumed" in html
            assert json.loads(app.render_json(url)) == model.to_dict()
            assert json.loads(app.render_export(url))["read_model"] == model.to_dict()


@pytest.mark.parametrize("view", ("strategies", "memory", "evidence-object-comparison"))
@pytest.mark.parametrize("lang", ("zh-CN", "en"))
@pytest.mark.parametrize(
    "source_status", ("api_unavailable", "stale", "integrity_failure", "incomparable")
)
def test_unusable_original_support_is_not_promoted_to_verified_evidence(view, lang, source_status):
    data = deepcopy(LIVE_INPUTS[view])
    if view == "strategies":
        records = data["genomes"]
    elif view == "memory":
        records = data["memory_entries"]
    else:
        records = [data["left"], data["right"]]
    for record in records:
        record.update(
            {
                "source_ref": "public-record-17",
                "original_source_id": "public-original-17",
                "original_snapshot_token": "public-read-17",
            }
        )
    data["sources"] = [
        {
            "source_id": "public-original-17",
            "title": "Unusable original support",
            "text": "Retained original wording is not a verified finding",
            "read_status": source_status,
            "snapshot_token": "public-read-17",
        }
    ]
    resource = dict(VIEWS)[view]
    model = resource_model(data)
    app = ManagerGUIApp(PublicResourceProvider(resource, model))
    html = app.render(f"/?view={view}&lang={lang}&mode=reader")
    expected = (
        "对应文字不能作为已核验支持"
        if lang == "zh-CN"
        else "the corresponding text is not verified support"
    )
    assert expected in html
    assert "public-original-17" in html
    assert json.loads(app.render_json(f"/?view={view}")) == model.to_dict()


@pytest.mark.parametrize(
    ("view", "resource", "record"),
    (
        (
            "strategies",
            "genomes",
            {"record_id": "package-schema-only", "schema": "quant-research.strategy-package.v1"},
        ),
        (
            "memory-failures",
            "memory",
            {
                "record_id": "result-schema-only",
                "schema": "quant-research.result.v4",
                "failure_category": "runtime_failure",
                "outcome": "execution_error",
            },
        ),
    ),
)
def test_package_and_run_result_schemas_do_not_supply_semantic_identity(view, resource, record):
    model = resource_model({"records": [record]})
    html = ManagerGUIApp(PublicResourceProvider(resource, model)).render(f"/?view={view}")
    assert "按本次公共输入呈现记录" not in html
    assert "对象存在，但所需字段或集合未记录" in html
    assert record["record_id"] in html
