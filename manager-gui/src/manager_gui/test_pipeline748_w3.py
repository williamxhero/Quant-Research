from __future__ import annotations

import json

import pytest
from strategy_workspace import WorkspaceClient

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
    expected = "当前公共接口无法列出" if lang == "zh-CN" else "The current public interface cannot list"
    assert expected in html
    assert f'data-resource-reading="{resource}"' in html
    assert 'data-sample-banner="fixture"' not in html
    assert "isolated-zero-genomes" in html
    assert json.loads(app.render_export(url))["read_model"] == model
