from __future__ import annotations

import json

import pytest
from strategy_workspace import WorkspaceClient

from manager_gui.models import (
    Availability,
    Derivation,
    ManagerReadModel,
    ReadModelError,
    ReadModelStatus,
    SourceReference,
)
from manager_gui.web import ManagerGUIApp
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
        "公共读取已确认：当前范围没有记录"
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
        assert "公共读取已确认：当前范围没有记录" not in html
        assert "Public read confirmed: no records in the current scope" not in html
        assert 'data-sample-banner="fixture"' not in html
        for error in errors:
            assert error.message in html


@pytest.mark.parametrize(("view", "resource"), VIEWS)
def test_present_object_without_collection_fields_is_not_an_empty_collection(view, resource):
    model = resource_model({"record_id": "public-record-17", "title": "Fieldless public object"})
    html = ManagerGUIApp(PublicResourceProvider(resource, model)).render(f"/?view={view}")
    assert "对象存在，但所需字段或集合未记录" in html
    assert "公共读取已确认：当前范围没有记录" not in html
    assert "Fieldless public object" in html
