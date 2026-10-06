"""Focused R3 Strategy/Genome Reader regressions."""

from __future__ import annotations

from dataclasses import replace
from html import unescape
from typing import cast
from urllib.parse import parse_qs, unquote, urlsplit

from manager_gui.models import JSONValue
from manager_gui.web.app import ManagerGUIApp
from manager_gui.web.genome import build_genome_fixture
from manager_gui.web.strategy_reader import (
    StrategyReaderViewModel,
    project_strategy_reader,
    render_strategy_reader,
)


def test_default_strategy_routes_mount_reader_and_preserve_expert_raw() -> None:
    app = ManagerGUIApp(default_fixture="complete")
    context = (
        "fixture=complete&scope=A0&root=record-1&filter=state%3Dknown&filter="
        "&snapshot_token=r3-snapshot&genome_id=genome-fixture-1"
    )

    genome = app.render(f"/?view=strategies&{context}")
    assert 'data-reader-page="genome"' in genome
    assert 'data-reader-hook="strategy-reader-view"' in genome
    assert 'data-integration-hook="strategy-genome-view"' in genome
    assert "What does this page answer?" in genome or "这项策略的结构" in genome
    assert "Signals" in genome or "信号" in genome
    assert "Risk controls" in genome or "风险控制" in genome
    assert "strategy effectiveness cannot be determined" not in genome
    assert "effectiveness" in genome.lower() or "有效性" in genome
    assert "r3-snapshot" in genome

    expert = app.render(f"/?view=strategies&{context}&mode=expert&lang=en")
    raw = app.render(f"/?view=strategies&{context}&mode=raw&lang=en")
    assert 'data-integration-hook="strategy-genome-view"' in expert
    assert 'class="genome-section genome-behavior"' in expert
    assert 'id="event-drawer"' in raw
    assert 'data-reader-page="genome"' not in expert


def test_conditions_and_comparison_reader_pages_preserve_context_and_states() -> None:
    app = ManagerGUIApp(default_fixture="complete")
    context = (
        "fixture=complete&scope=A0&root=record-1&filter=state%3Dknown&filter="
        "&snapshot_token=r3-snapshot&genome_id=genome-fixture-1"
    )
    conditions = app.render(f"/?view=strategy-conditions&{context}&lang=en")
    assert 'data-reader-page="conditions"' in conditions
    assert 'data-condition-group="applicability"' in conditions
    assert 'class="condition-genome-link"' in conditions
    assert 'class="condition-comparison-link"' in conditions
    assert "r3-snapshot" in conditions

    comparison = app.render(
        "/?view=strategy-genome-comparison&fixture=incomparable&scope=A0&root=record-1"
        "&filter=state%3Dknown&filter=&snapshot_token=r3-snapshot"
        "&left_genome_id=genome-left&right_genome_id=genome-right&lang=en"
    )
    assert 'data-reader-page="comparison"' in comparison
    assert 'data-comparison-result="incomparable"' in comparison
    assert "Incompatible axes" in comparison
    assert 'class="comparison-left-genome-link"' in comparison
    assert 'class="comparison-right-conditions-link"' in comparison
    assert "r3-snapshot" in comparison


def test_strategy_projection_keeps_owner_text_and_raw_v0_identity() -> None:
    source = build_genome_fixture("complete")
    data = cast(dict[str, JSONValue], source.data)
    genome = cast(dict[str, JSONValue], cast(list[JSONValue], data["genomes"])[0])
    genome["strategy_summary"] = "Owner wording <do not translate>"
    genome["qualification"] = "recorded_only"
    genome["currency"] = "current_until_2026-10-03"
    genome["conditions"] = [
        {"category": "applicability", "condition": "Liquidity", "outcome": "supported"},
        {"category": "invalidation", "condition": "Data gate", "outcome": "not_evaluated"},
    ]
    genome["revisions"] = [
        {"revision_id": "r1", "changes": {"entry": "old"}, "reason": "Owner reason"},
        {
            "revision_id": "r2",
            "parent_revision_id": "r1",
            "changes": {"entry": "new"},
            "evidence": ["evidence-1"],
            "limitations": ["small sample"],
        },
    ]
    model = replace(source, data=data)
    projection = project_strategy_reader(model)
    assert projection.to_dict()["data"] == model.data
    assert projection.raw_source.raw_bytes == model.to_json().encode("utf-8")
    view = StrategyReaderViewModel.from_read_model(model)
    assert view.owner_summary == "Owner wording <do not translate>"
    assert view.revisions[1].parent_id == "r1"
    assert view.revisions[1].reason is None
    rendered = render_strategy_reader(model, translator=None, query_context="/?lang=en&mode=reader")
    assert "Owner wording &lt;do not translate&gt;" in rendered
    assert "Owner reason" in rendered
    assert "reason is not recorded" in rendered or "reason" in rendered.lower()
    assert "not_evaluated" in rendered
    assert "r1" in rendered and "r2" in rendered


def test_reader_links_keep_opaque_repeated_query_values() -> None:
    app = ManagerGUIApp(default_fixture="complete")
    document = app.render(
        "/?view=strategies&fixture=complete&scope=A0&root=record-1"
        "&filter=a&filter=b&filter=&snapshot_token=s1&lang=en&mode=reader"
    )
    links = [
        unescape(unquote(match.split('href="', 1)[1].split('"', 1)[0]))
        for match in document.split("<a ")
        if "genome-conditions-link" in match or "genome-comparison-link" in match
    ]
    assert links
    for link in links:
        query = parse_qs(urlsplit(link).query, keep_blank_values=True)
        assert query["filter"] == ["a", "b", ""]
        assert query["snapshot_token"] == ["s1"]
        assert query["lang"] == ["en"]
