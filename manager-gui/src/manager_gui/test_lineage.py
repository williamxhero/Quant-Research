"""Focused S4-T2 tests for the bounded Lineage graph and table view."""

from __future__ import annotations

import builtins
import html
import re
import sqlite3
import time
from dataclasses import replace
from typing import cast

import pytest

from manager_gui import (
    Availability,
    Derivation,
    ManagerReadModel,
    ReadModelError,
    ReadModelStatus,
    SourceReference,
)
from manager_gui.models import JSONValue
from manager_gui.provider import FORBIDDEN_PROVIDER_METHODS, public_provider_methods
from manager_gui.web.lineage import (
    LINEAGE_INTEGRATION_HOOK,
    LINEAGE_RESOURCE,
    LINEAGE_SCHEMA,
    MAX_DEPTH,
    MAX_EDGES,
    MAX_NODES,
    LineageDirection,
    LineageFailure,
    LineageFixtureState,
    LineageInspector,
    LineagePathState,
    LineageQuery,
    LineageRecordType,
    LineageRelation,
    LineageState,
    LineageViewModel,
    build_lineage_fixture,
    lineage_content_hash,
    lineage_fixture_provider,
    render_lineage,
    render_lineage_view,
    shortest_evidence_path,
)

CONTEXT = "/?view=lineage&fixture=complete&panel=events&q=abc&opaque=keep"


# --- helpers -------------------------------------------------------------------


def _n(node_id: str, kind: str = "evidence", **extra: object) -> dict[str, object]:
    return {"id": node_id, "record_type": kind, "label": node_id.title(), **extra}


def _e(source: str, relation: str, target: str) -> dict[str, object]:
    return {"source": source, "target": target, "relation": relation}


def _model(
    nodes: list[dict[str, object]],
    edges: list[dict[str, object]],
    *,
    root: str | None = None,
    pagination: dict[str, object] | None = None,
    snapshot: str | None = "snap-1",
    status: ReadModelStatus = ReadModelStatus.KNOWN,
    complete: bool = True,
    errors: tuple[ReadModelError, ...] = (),
    schema: str = LINEAGE_SCHEMA,
    content_hash: str | None = None,
    sources: tuple[SourceReference, ...] | None = None,
) -> ManagerReadModel:
    payload: dict[str, object] = {
        "schema": schema,
        "root": root if root is not None else nodes[0]["id"],
        "nodes": nodes,
        "edges": edges,
    }
    if pagination is not None:
        payload["pagination"] = pagination
    if content_hash is not None:
        payload["content_hash"] = content_hash
    refs = (
        sources
        if sources is not None
        else (
            SourceReference(
                source_id="src-1",
                owner="owner",
                kind="lineage",
                locator="https://example.invalid/lineage",
                schema="lineage.v1",
                revision="r1",
            ),
        )
    )
    return ManagerReadModel(
        data=cast(JSONValue, payload),
        source_refs=refs,
        as_of="2026-10-03T12:00:00Z",
        snapshot_token=snapshot,
        derivation=Derivation(kind="direct", version="v0"),
        availability=Availability(status=status, complete=complete, reason="test"),
        errors=errors,
    )


def _view(state: str = "complete", **query: object) -> LineageViewModel:
    return LineageViewModel.from_read_model(
        build_lineage_fixture(state), LineageQuery.from_query(query or None)
    )


def _ids(view: LineageViewModel) -> set[str]:
    return {node.node_id for node in view.visible_nodes}


def _render(state: str = "complete", context: str = CONTEXT, *, route: str = "lineage") -> str:
    return render_lineage_view(build_lineage_fixture(state), query_context=context, route=route)


def _graph_nodes(out: str) -> list[str]:
    return re.findall(r'<g class="lineage-node" data-node-id="([^"]+)"', out)


def _table_nodes(out: str) -> list[str]:
    return re.findall(r'<tr data-node-id="([^"]+)"', out)


def _graph_edges(out: str) -> list[str]:
    return re.findall(r'<g class="lineage-edge" data-edge-id="([^"]+)"', out)


def _table_edges(out: str) -> list[str]:
    return re.findall(r'<tr data-edge-id="([^"]+)"', out)


def _text_edges(out: str) -> list[str]:
    return re.findall(r'<li data-edge-id="([^"]+)"', out)


def _local_links(out: str) -> list[str]:
    return [html.unescape(href) for href in re.findall(r'href="(/\?[^"]*)"', out)]


def _failure(view: LineageViewModel) -> LineageFailure:
    assert view.state is LineageState.FAIL_CLOSED
    assert view.failure is not None
    assert view.nodes == () and view.visible_nodes == ()
    return view.failure.code


# --- query ---------------------------------------------------------------------


def test_query_defaults_and_csv_or_repeated_values() -> None:
    default = LineageQuery.from_query(None)
    assert default.direction is LineageDirection.BOTH
    assert (default.depth, default.page_size, default.cursor) == (2, 20, None)
    assert default.relations == () and default.record_types == ()

    query = LineageQuery.from_query(
        "/?direction=upstream&relations=supports,produces&relations=derives"
        "&record_types=evidence&depth=4&page_size=7&cursor=c-2&snapshot_token=s1&node=n&path_to=p"
    )
    assert query.direction is LineageDirection.UPSTREAM
    assert query.relations == (
        LineageRelation.SUPPORTS,
        LineageRelation.PRODUCES,
        LineageRelation.DERIVES,
    )
    assert query.record_types == (LineageRecordType.EVIDENCE,)
    assert (query.depth, query.page_size, query.cursor) == (4, 7, "c-2")
    assert (query.node, query.path_to, query.snapshot_token) == ("n", "p", "s1")

    mapping = LineageQuery.from_query({"depth": 3, "relations": ["supports", "produces"]})
    assert mapping.depth == 3 and len(mapping.relations) == 2


def test_query_bounds_are_clamped_and_reported_not_hidden() -> None:
    query = LineageQuery.from_query(
        "/?direction=sideways&relations=bogus&record_types=nothing&depth=99&page_size=0"
    )
    assert query.depth == MAX_DEPTH and query.page_size == 1
    assert query.direction is LineageDirection.BOTH
    assert query.relations == () and query.record_types == ()
    assert len(query.notes) == 5
    out = render_lineage(LineageViewModel.from_read_model(build_lineage_fixture("complete"), query))
    for fragment in ("Unknown direction", "Unknown relation", f"using {MAX_DEPTH}", "using 1"):
        assert fragment in out
    assert LineageQuery.from_query("/?depth=abc").depth == 2


def test_hook_record_id_and_snapshot_arguments_take_part_in_the_query() -> None:
    query = LineageQuery.from_query(
        "/?record_id=a&snapshot_token=s1", record_id="b", snapshot_token="s2"
    )
    assert query.record_id == "b"
    assert query.snapshot_tokens == ("s1", "s2")


# --- typed model, inspector, source refs --------------------------------------


def test_complete_fixture_has_typed_nodes_edges_and_all_record_types() -> None:
    view = _view()

    assert view.state is LineageState.READY and view.failure is None
    assert {node.record_type.value for node in view.nodes} == {
        "conclusion",
        "evidence",
        "artifact",
        "genome",
        "memory",
        "run",
        "campaign",
        "candidate",
        "source_document",
    }
    assert {edge.relation for edge in view.edges} == {
        LineageRelation.SUPPORTS,
        LineageRelation.SUPERSEDES,
        LineageRelation.PRODUCES,
        LineageRelation.DERIVES,
        LineageRelation.INFORMS,
        LineageRelation.DOCUMENTS,
    }
    assert all(isinstance(node.record_type, LineageRecordType) for node in view.nodes)
    assert view.pagination.complete and not view.pagination.has_more
    payload = view.to_dict()
    assert payload["state"] == "ready" and payload["root_id"] == "conclusion-1"
    assert payload["snapshot_token"] == "lineage-complete-v0"
    assert isinstance(view.inspector, LineageInspector)
    assert view.inspector.node_id == "conclusion-1"
    assert view.inspector.node_count == len(view.visible_nodes)
    assert view.inspector.to_dict()["state"] == "ready"
    assert shortest_evidence_path(view) == view.evidence_path
    assert (
        shortest_evidence_path(
            build_lineage_fixture("complete"),
            query=LineageQuery.from_query("/?depth=6"),
            root_id="memory-1",
        )
        is not None
    )


def test_inspector_exposes_metadata_relations_sources_and_derivation() -> None:
    out = _render(context=CONTEXT + "&node=run-1&depth=6")
    inspector = out.split('data-lineage-inspector="run-1"', 1)[1].split("</aside>", 1)[0]

    assert "Formal run" in inspector
    assert "direct · v1 (inputs: lineage-fixture-source)" in inspector
    assert "2026-10-03T09:00:00Z" in inspector
    assert 'href="fixture://apex-research/lineage"' in inspector
    assert "derives from" in inspector and "produces to" in inspector
    assert "lineage-complete-v0" in inspector
    assert 'aria-current="true"' in out

    artifact = _render(context=CONTEXT + "&node=artifact-1")
    assert "sha256:" + "a" * 64 + " (verified)" in artifact
    outside = _render(context=CONTEXT + "&node=document-orphan")
    assert "outside the current depth" in outside
    missing = _render(context=CONTEXT + "&node=nope")
    assert 'data-lineage-inspector="missing"' in missing


def test_source_refs_as_of_and_derivation_are_visible_and_unresolved_refs_are_not_linked() -> None:
    private = SourceReference(
        source_id="private-src",
        owner="owner",
        kind="lineage",
        locator="C:\\private\\lineage.json",
        schema="lineage.v1",
        revision="r1",
    )
    local_file = replace(private, source_id="file-src", locator="file:///etc/passwd")
    model = _model(
        [
            _n("a", "conclusion", source_refs=["private-src", "file-src", "ghost-src", "src-1"]),
            _n("b", "evidence", as_of="2026-01-01T00:00:00Z"),
        ],
        [_e("b", "supports", "a")],
        sources=(
            private,
            local_file,
            SourceReference("src-1", "owner", "lineage", "https://example.invalid/l", "s", "r"),
        ),
    )
    out = render_lineage_view(model, query_context="/?view=lineage")

    assert "ghost-src" in out and "Missing / Unconfirmed" in out
    assert 'href="https://example.invalid/l"' in out
    assert "private-src (owner · lineage) — Missing / Unconfirmed" in out
    assert "file-src (owner · lineage) — Missing / Unconfirmed" in out
    assert 'href="file:' not in out and 'href="C:' not in out
    assert "2026-01-01T00:00:00Z" in out
    assert "2026-10-03T12:00:00Z" in out  # node without as-of falls back to the envelope
    assert "direct · v0" in out  # envelope derivation


def test_labels_are_escaped() -> None:
    model = _model([_n("a", "conclusion", label="<script>alert(1)</script>")], [])
    out = render_lineage_view(model)
    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in out


# --- bounded expansion ---------------------------------------------------------


def test_depth_bounds_expansion_and_reports_outside_records() -> None:
    default = _view()
    assert _ids(default) == {
        "conclusion-1",
        "evidence-1",
        "evidence-2",
        "genome-1",
        "artifact-1",
        "document-1",
        "evidence-3",
        "memory-1",
    }
    assert default.outside_bounds == 3  # run, candidate, campaign
    assert [node.node_id for node in default.disconnected] == ["document-orphan"]
    assert _ids(_view(depth=1)) == {"conclusion-1", "evidence-1", "evidence-2", "genome-1"}
    assert len(_ids(_view(depth=MAX_DEPTH))) == 11
    assert _view(depth=999).query.depth == MAX_DEPTH


def test_direction_relations_and_record_types_bound_the_walk() -> None:
    upstream = _view(direction="upstream", depth=6)
    assert _ids(upstream) == {
        "conclusion-1",
        "evidence-1",
        "evidence-2",
        "genome-1",
        "artifact-1",
        "document-1",
        "memory-1",
        "run-1",
        "candidate-1",
        "campaign-1",
    }
    assert {name: upstream.depths[name] for name in ("run-1", "candidate-1", "campaign-1")} == {
        "run-1": 3,
        "candidate-1": 4,
        "campaign-1": 5,
    }
    assert _ids(_view(direction="downstream")) == {"conclusion-1"}
    assert _ids(_view(record_id="evidence-2", direction="downstream")) == {
        "evidence-2",
        "conclusion-1",
        "evidence-3",
    }
    assert _ids(_view(relations="supports", depth=6)) == {
        "conclusion-1",
        "evidence-1",
        "evidence-2",
        "artifact-1",
    }
    # A filtered-out record type cannot be walked through either.
    assert _ids(_view(record_types="evidence", depth=6)) == {
        "conclusion-1",
        "evidence-1",
        "evidence-2",
        "evidence-3",
    }
    visible_edges = {edge.edge_id for edge in _view(relations="supports", depth=6).visible_edges}
    assert visible_edges == {
        "evidence-1|supports|conclusion-1",
        "evidence-2|supports|conclusion-1",
        "artifact-1|supports|evidence-1",
    }


def test_expansion_never_includes_records_beyond_the_requested_depth() -> None:
    chain = [_n(f"n{i}", "run") for i in range(10)]
    edges = [_e(f"n{i}", "produces", f"n{i + 1}") for i in range(9)]
    view = LineageViewModel.from_read_model(
        _model(chain, edges), LineageQuery.from_query("/?depth=3&direction=downstream")
    )
    assert _ids(view) == {"n0", "n1", "n2", "n3"}
    assert view.outside_bounds == 6


# --- shortest evidence path ----------------------------------------------------


def test_shortest_evidence_path_is_deterministic_and_direction_aware() -> None:
    default = _view()
    assert default.path_state is LineagePathState.FOUND
    assert default.evidence_path is not None
    assert default.evidence_path.node_ids == ("conclusion-1", "evidence-1")  # ties break by id
    assert default.evidence_path.edge_ids == ("evidence-1|supports|conclusion-1",)

    through_genome = _view(record_id="memory-1", depth=6)
    assert through_genome.evidence_path is not None
    assert through_genome.evidence_path.node_ids == (
        "memory-1",
        "genome-1",
        "conclusion-1",
        "evidence-1",
    )
    assert _view(record_id="memory-1", direction="downstream", depth=6).path_state is (
        LineagePathState.NOT_FOUND
    )
    flow = _view(record_id="campaign-1", direction="downstream", depth=6)
    assert flow.evidence_path is not None and flow.evidence_path.length == 4
    assert flow.evidence_path.node_ids[-1] == "evidence-1"


def test_explicit_path_target_and_bounds_limit_the_path() -> None:
    targeted = _view(path_to="artifact-1").evidence_path
    assert targeted is not None
    assert targeted.node_ids == ("conclusion-1", "evidence-1", "artifact-1")
    assert _view(path_to="run-1").path_state is LineagePathState.NOT_FOUND
    assert _view(path_to="run-1", depth=3).path_state is LineagePathState.FOUND
    out = _render(context=CONTEXT + "&path_to=run-1")
    assert 'data-path-state="not-found"' in out
    assert "No evidence path exists within depth 2" in out


def test_path_is_highlighted_consistently_in_graph_table_and_text() -> None:
    out = _render(context=CONTEXT + "&record_id=memory-1&depth=6")
    assert 'data-path-state="found"' in out
    assert "Shortest path to Protocol evidence: 3 relation(s)" in out
    assert out.count('data-on-path="true"') >= 4 + 3  # nodes + edges in graph, plus table rows
    assert "Step 1" in out and "Step 4" in out


# --- disconnected records and partial pagination -------------------------------


def test_disconnected_records_are_listed_and_distinct_from_outside_bounds() -> None:
    out = _render()
    section = out.split('class="lineage-disconnected"', 1)[1].split("</section>", 1)[0]
    assert 'data-disconnected-count="1"' in out
    assert "Unlinked note" in section
    assert "No relation in this snapshot connects these records to the root." in section
    assert "3 connected record(s) lie outside the current depth" in section
    connected_only = _render(context=CONTEXT + "&depth=6")
    assert "3 connected record(s)" not in connected_only


def test_partial_pagination_never_claims_absence() -> None:
    view = _view("partial")
    assert view.state is LineageState.PARTIAL and view.partial
    assert view.dangling_edges == 1  # memory-1 lives on another owner page
    assert view.disconnected == ()
    assert view.pagination.next_cursor == "cursor-2"

    undecided = _view("partial", record_id="genome-1", direction="downstream", depth=6)
    assert undecided.path_state is LineagePathState.NOT_ESTABLISHED
    assert _view(record_id="genome-1", direction="downstream", depth=6).path_state is (
        LineagePathState.NOT_FOUND
    )

    out = _render("partial")
    assert 'data-lineage-state="partial"' in out
    assert 'data-pagination-complete="false"' in out
    assert "not evidence of absence" in out
    assert "1 relation(s) reference records on other owner pages" in out
    link = next(href for href in _local_links(out) if "cursor=cursor-2" in href)
    assert "snapshot_token=lineage-partial-v0" in link and "page=" not in link
    assert "Not established" in _render(
        "partial", CONTEXT + "&record_id=genome-1&direction=downstream&depth=6"
    )


def test_partial_page_with_unlinked_record_is_not_declared_disconnected() -> None:
    model = _model(
        [_n("a", "conclusion"), _n("lone")],
        [],
        pagination={"has_more": True, "next_cursor": "c-2", "complete": False},
    )
    view = LineageViewModel.from_read_model(model)
    assert [node.node_id for node in view.disconnected] == ["lone"]
    out = render_lineage(view)
    assert "Not determined: records on further owner pages may connect these." in out


# --- graph / table consistency, pagination, accessibility ----------------------


def test_graph_table_and_text_describe_the_same_records_and_relations() -> None:
    out = _render(context=CONTEXT + "&depth=6")
    view = _view(depth=6)

    assert sorted(_graph_nodes(out)) == sorted(_table_nodes(out))
    assert sorted(_graph_nodes(out)) == sorted(_ids(view))
    assert sorted(_graph_edges(out)) == sorted(_table_edges(out)) == sorted(_text_edges(out))
    assert sorted(_graph_edges(out)) == sorted(edge.edge_id for edge in view.visible_edges)
    assert len(_graph_nodes(out)) == 11  # all but the unconnected note


def test_pagination_keeps_graph_and_table_in_step() -> None:
    model = build_lineage_fixture("large")
    ctx = "/?view=lineage&page_size=5&depth=2"
    first = render_lineage_view(model, query_context=ctx)
    second = render_lineage_view(model, query_context=ctx + "&page=2")

    assert _graph_nodes(first) == _table_nodes(first)
    assert _graph_nodes(first) == [f"node-{i:04d}" for i in range(1, 6)]
    assert _graph_nodes(second) == _table_nodes(second) == ["node-0006", "node-0007"]
    assert sorted(_graph_edges(first)) == sorted(_table_edges(first))
    assert "data-off-page-relations" in first and "Page 1 of 2" in first
    assert "Page 2 of 2" in second
    assert not set(_graph_nodes(first)) & set(_graph_nodes(second))


def test_table_and_graph_use_keyboard_friendly_semantics() -> None:
    out = _render()

    assert "<caption>Records on this page (8 of 8 within the bounds)</caption>" in out
    assert '<th scope="col">Record</th>' in out and '<th scope="row">' in out
    assert 'role="region" aria-label="Lineage records table, scrollable" tabindex="0"' in out
    assert 'role="region" aria-label="Lineage graph, scrollable" tabindex="0"' in out
    assert '<a class="lineage-skip" href="#lineage-table">' in out
    assert 'id="lineage-table"' in out
    assert '<ol class="lineage-text-view"' in out
    assert 'aria-label="Protocol conclusion, conclusion, depth 0, root' in out
    assert out.count('aria-current="true"') == 1
    assert '<svg role="group" aria-labelledby="lineage-graph-caption"' in out
    assert re.search(r'<g class="lineage-node"[^>]*><a href="[^"]+" aria-label="', out)
    assert 'data-integration-hook="lineage-view"' in out
    assert LINEAGE_INTEGRATION_HOOK == "lineage-view"


def test_rendering_is_deterministic_and_input_order_independent() -> None:
    assert _render() == _render()
    nodes = [_n("a", "conclusion"), _n("b"), _n("c", "artifact")]
    edges = [_e("b", "supports", "a"), _e("c", "supports", "b")]
    first = LineageViewModel.from_read_model(_model(nodes, edges, root="a")).to_dict()
    second = LineageViewModel.from_read_model(
        _model(list(reversed(nodes)), list(reversed(edges)), root="a")
    ).to_dict()
    assert first == second


# --- stable context links ------------------------------------------------------


def test_links_preserve_context_and_reset_dependent_state() -> None:
    out = _render(
        context=CONTEXT + "&snapshot_token=lineage-complete-v0&path_to=artifact-1&node=genome-1"
    )
    links = _local_links(out)
    assert links
    assert all("view=lineage" in href for href in links)
    for href in links:
        for kept in ("fixture=complete", "panel=events", "q=abc", "opaque=keep"):
            assert kept in href
        assert "snapshot_token=lineage-complete-v0" in href
    reroot = [href for href in links if "record_id=evidence-1" in href]
    assert reroot
    assert all("node=" not in h and "path_to=" not in h and "cursor=" not in h for h in reroot)
    inspect = [href for href in links if "node=evidence-1" in href]
    assert inspect and all("path_to=artifact-1" in h for h in inspect)
    assert _local_links(_render(context=CONTEXT)) == _local_links(_render(context=CONTEXT))


def test_route_is_configurable_for_the_integration_slice() -> None:
    out = _render(route="evidence")
    assert all("view=evidence" in href for href in _local_links(out))
    form = out.split('class="lineage-filters"', 1)[1].split("</form>", 1)[0]
    assert 'name="view" value="evidence"' in form


def test_bounds_form_preserves_context_and_checked_state() -> None:
    out = _render(
        context=CONTEXT
        + "&relations=supports&record_types=evidence&snapshot_token=lineage-complete-v0&cursor=",
    )
    form = out.split('class="lineage-filters"', 1)[1].split("</form>", 1)[0]
    for name, value in (
        ("fixture", "complete"),
        ("panel", "events"),
        ("q", "abc"),
        ("opaque", "keep"),
        ("snapshot_token", "lineage-complete-v0"),
    ):
        assert f'<input type="hidden" name="{name}" value="{value}">' in form
    # Managed keys are rebuilt from the controls; a stale cursor or page offset never survives.
    assert 'name="cursor"' not in form and 'name="page"' not in form
    assert 'name="relations" value="supports" checked' in form
    assert 'name="relations" value="produces" checked' not in form
    assert 'name="record_types" value="evidence" checked' in form
    assert '<option value="both" selected>' in form


# --- fail-closed states --------------------------------------------------------


@pytest.mark.parametrize(
    ("state", "code"),
    [
        (LineageFixtureState.CURSOR_EXPIRED, LineageFailure.CURSOR_EXPIRED),
        (LineageFixtureState.SNAPSHOT_DRIFT, LineageFailure.SNAPSHOT_DRIFT),
        (LineageFixtureState.UNKNOWN_SCHEMA, LineageFailure.UNKNOWN_SCHEMA),
        (LineageFixtureState.HASH_MISMATCH, LineageFailure.HASH_MISMATCH),
        (LineageFixtureState.API_UNAVAILABLE, LineageFailure.SOURCE_UNAVAILABLE),
    ],
)
def test_fail_closed_fixtures_withhold_graph_table_and_path(
    state: LineageFixtureState, code: LineageFailure
) -> None:
    assert _failure(_view(state.value)) is code
    out = _render(state.value)
    assert f'data-lineage-failure="{code.value}"' in out
    assert 'data-graph="withheld"' in out and 'role="alert"' in out
    for forbidden in ("<svg", "lineage-table", "lineage-evidence-path", "lineage-inspector"):
        assert forbidden not in out
    assert 'data-lineage-state="fail-closed"' in out


def test_restart_link_is_offered_only_when_a_restart_can_help() -> None:
    for state in ("cursor_expired", "snapshot_drift"):
        out = _render(
            state, CONTEXT + "&snapshot_token=old&cursor=cursor-1&node=x&path_to=y&page=3"
        )
        links = [href for href in _local_links(out) if "view=lineage" in href]
        assert any(
            "cursor=" not in href and "snapshot_token=" not in href and "page=" not in href
            for href in links
        )
        assert "Restart from the current snapshot" in out
    for state in ("hash_mismatch", "unknown_schema"):
        assert "Restart from the current snapshot" not in _render(state)


def test_cursor_expired_by_state_error_code_and_mismatch() -> None:
    expired = _model(
        [_n("a", "conclusion")], [], pagination={"cursor": "c-1", "cursor_state": "Expired"}
    )
    assert _failure(LineageViewModel.from_read_model(expired)) is LineageFailure.CURSOR_EXPIRED
    by_error = _model(
        [_n("a", "conclusion")],
        [],
        status=ReadModelStatus.STALE,
        errors=(ReadModelError(code="cursor_expired", message="gone"),),
    )
    assert _failure(LineageViewModel.from_read_model(by_error)) is LineageFailure.CURSOR_EXPIRED

    page = _model([_n("a", "conclusion")], [], pagination={"cursor": "c-2", "next_cursor": "c-3"})
    ok = LineageViewModel.from_read_model(page, LineageQuery.from_query("/?cursor=c-2"))
    assert ok.state is LineageState.READY
    mismatch = LineageViewModel.from_read_model(page, LineageQuery.from_query("/?cursor=c-9"))
    assert _failure(mismatch) is LineageFailure.CURSOR_MISMATCH
    absent = LineageViewModel.from_read_model(
        _model([_n("a", "conclusion")], []), LineageQuery.from_query("/?cursor=c-1")
    )
    assert _failure(absent) is LineageFailure.CURSOR_MISMATCH


def test_snapshot_drift_is_detected_for_every_source_of_a_token() -> None:
    model = _model([_n("a", "conclusion")], [], pagination={"snapshot_token": "snap-1"})
    assert LineageViewModel.from_read_model(model).state is LineageState.READY
    same = LineageQuery.from_query("/?snapshot_token=snap-1", snapshot_token="snap-1")
    assert LineageViewModel.from_read_model(model, same).state is LineageState.READY

    requested = LineageQuery.from_query("/?snapshot_token=snap-0")
    assert (
        _failure(LineageViewModel.from_read_model(model, requested))
        is LineageFailure.SNAPSHOT_DRIFT
    )
    hook = LineageQuery.from_query(None, snapshot_token="snap-0")
    assert _failure(LineageViewModel.from_read_model(model, hook)) is LineageFailure.SNAPSHOT_DRIFT
    expected = LineageViewModel.from_read_model(model, expected_snapshots=("snap-0",))
    assert _failure(expected) is LineageFailure.SNAPSHOT_DRIFT

    page = _model([_n("a", "conclusion")], [], pagination={"snapshot_token": "snap-0"})
    assert _failure(LineageViewModel.from_read_model(page)) is LineageFailure.SNAPSHOT_DRIFT
    mixed = _model(
        [_n("a", "conclusion"), _n("b", snapshot_token="snap-0")], [_e("b", "supports", "a")]
    )
    assert _failure(LineageViewModel.from_read_model(mixed)) is LineageFailure.SNAPSHOT_DRIFT
    unpinned = _model([_n("a", "conclusion")], [], snapshot=None)
    assert (
        _failure(LineageViewModel.from_read_model(unpinned, requested))
        is LineageFailure.SNAPSHOT_DRIFT
    )


def test_hook_detects_drift_between_the_requested_and_the_read_snapshot() -> None:
    class Provider:
        def read(
            self, resource: str = "atlas", *, snapshot_token: str | None = None
        ) -> ManagerReadModel:
            del resource, snapshot_token
            return build_lineage_fixture("complete")

    drifted = render_lineage_view(Provider(), snapshot_token="lineage-older-v0")
    assert 'data-lineage-failure="snapshot_drift"' in drifted
    pinned = render_lineage_view(
        Provider(),
        query_context="/?snapshot_token=lineage-complete-v0",
        snapshot_token="lineage-complete-v0",
    )
    assert 'data-lineage-state="ready"' in pinned


def test_unknown_schema_record_type_and_relation_fail_closed() -> None:
    schema = _model([_n("a", "conclusion")], [], schema="manager-gui.lineage.v9")
    assert _failure(LineageViewModel.from_read_model(schema)) is LineageFailure.UNKNOWN_SCHEMA
    missing_schema = replace(schema, data=cast(JSONValue, {"nodes": [], "edges": []}))
    assert (
        _failure(LineageViewModel.from_read_model(missing_schema)) is LineageFailure.UNKNOWN_SCHEMA
    )
    kind = _model([_n("a", "conclusion"), _n("b", "spaceship")], [_e("b", "supports", "a")])
    assert _failure(LineageViewModel.from_read_model(kind)) is LineageFailure.UNKNOWN_SCHEMA
    relation = _model([_n("a", "conclusion"), _n("b")], [_e("b", "teleports", "a")])
    assert _failure(LineageViewModel.from_read_model(relation)) is LineageFailure.UNKNOWN_SCHEMA


def test_hash_mismatch_fails_closed_for_nodes_and_page_content() -> None:
    declared = "sha256:" + "1" * 64
    node = _model([_n("a", "conclusion", hash=declared, verified_hash="sha256:" + "2" * 64)], [])
    assert _failure(LineageViewModel.from_read_model(node)) is LineageFailure.HASH_MISMATCH
    status = _model([_n("a", "conclusion", verification_status="hash_mismatch")], [])
    assert _failure(LineageViewModel.from_read_model(status)) is LineageFailure.HASH_MISMATCH

    nodes, edges = [_n("a", "conclusion"), _n("b")], [_e("b", "supports", "a")]
    digest = lineage_content_hash(nodes, edges)
    good = LineageViewModel.from_read_model(_model(nodes, edges, content_hash=digest))
    assert good.state is LineageState.READY
    tampered = _model([_n("a", "conclusion", label="Edited"), _n("b")], edges, content_hash=digest)
    assert _failure(LineageViewModel.from_read_model(tampered)) is LineageFailure.HASH_MISMATCH
    unverified = _model([_n("a", "conclusion", hash=declared)], [])
    assert "(not verified)" in render_lineage(LineageViewModel.from_read_model(unverified))
    assert lineage_content_hash(nodes, edges) == digest  # stable across calls


@pytest.mark.parametrize(
    "status, code",
    [
        (ReadModelStatus.BLOCKED, LineageFailure.SOURCE_BLOCKED),
        (ReadModelStatus.INCOMPARABLE, LineageFailure.INCOMPARABLE),
        (ReadModelStatus.INTEGRITY_FAILURE, LineageFailure.INTEGRITY_FAILURE),
        (ReadModelStatus.API_UNAVAILABLE, LineageFailure.SOURCE_UNAVAILABLE),
    ],
)
def test_unusable_source_statuses_fail_closed_with_distinct_codes(
    status: ReadModelStatus, code: LineageFailure
) -> None:
    model = _model([_n("a", "conclusion")], [], status=status, complete=False)
    assert _failure(LineageViewModel.from_read_model(model)) is code
    assert f'data-status="{status.value}"' in render_lineage(
        LineageViewModel.from_read_model(model)
    )


def test_stale_lineage_is_labelled_not_withheld_and_missing_is_empty() -> None:
    stale = LineageViewModel.from_read_model(
        _model([_n("a", "conclusion")], [], status=ReadModelStatus.STALE)
    )
    assert stale.state is LineageState.READY
    assert 'data-status="stale"' in render_lineage(stale)
    out = _render("empty")
    assert 'data-lineage-state="empty"' in out and 'data-display-state="empty"' in out
    assert "<svg" not in out


def test_malformed_pages_fail_closed() -> None:
    cases = {
        "dangling on a complete page": _model(
            [_n("a", "conclusion")], [_e("ghost", "supports", "a")]
        ),
        "duplicate nodes": _model([_n("a", "conclusion"), _n("a")], []),
        "duplicate edges": _model(
            [_n("a", "conclusion"), _n("b")], [_e("b", "supports", "a"), _e("b", "supports", "a")]
        ),
        "self relation": _model([_n("a", "conclusion")], [_e("a", "supports", "a")]),
        "node without identity": _model([{"record_type": "run"}], [], root="x"),
        "bad derivation": _model([_n("a", "conclusion", derivation={"kind": "guess"})], []),
        "bad source ref": _model([_n("a", "conclusion", source_refs=[7])], []),
        "bad node list": replace(
            _model([_n("a", "conclusion")], []),
            data=cast(JSONValue, {"schema": LINEAGE_SCHEMA, "root": "a", "nodes": 5}),
        ),
    }
    for label, model in cases.items():
        view = LineageViewModel.from_read_model(model)
        assert _failure(view) is LineageFailure.INVALID_PAYLOAD, label


def test_missing_root_fails_closed() -> None:
    model = _model([_n("a", "conclusion")], [], root="elsewhere")
    assert _failure(LineageViewModel.from_read_model(model)) is LineageFailure.ROOT_NOT_FOUND
    other = LineageViewModel.from_read_model(
        _model([_n("a", "conclusion")], []), LineageQuery.from_query("/?record_id=nope")
    )
    assert _failure(other) is LineageFailure.ROOT_NOT_FOUND
    unrooted = replace(
        _model([_n("a", "conclusion")], []),
        data=cast(JSONValue, {"schema": LINEAGE_SCHEMA, "nodes": [_n("a", "conclusion")]}),
    )
    assert _failure(LineageViewModel.from_read_model(unrooted)) is LineageFailure.ROOT_NOT_FOUND


# --- hook, provider, read-only boundary ----------------------------------------


def test_hook_reads_only_the_lineage_resource_once_and_forwards_the_snapshot() -> None:
    class Provider:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None]] = []

        def read(
            self, resource: str = "atlas", *, snapshot_token: str | None = None
        ) -> ManagerReadModel:
            self.calls.append((resource, snapshot_token))
            return build_lineage_fixture("complete")

    provider = Provider()
    out = render_lineage_view(provider, snapshot_token="lineage-complete-v0")

    assert provider.calls == [(LINEAGE_RESOURCE, "lineage-complete-v0")]
    assert 'data-integration-hook="lineage-view"' in out
    assert public_provider_methods(provider) == ("read",)
    assert FORBIDDEN_PROVIDER_METHODS.isdisjoint(public_provider_methods(provider))
    assert render_lineage_view(build_lineage_fixture("complete")).count("lineage-page") >= 1


def test_fixture_provider_is_read_only_and_rejects_other_resources() -> None:
    provider = lineage_fixture_provider("complete")
    assert provider.read().availability.status is ReadModelStatus.KNOWN
    assert set(public_provider_methods(provider)) <= {"read"}
    with pytest.raises(ValueError, match="does not serve resource"):
        provider.read("atlas")
    for state in LineageFixtureState:
        model = lineage_fixture_provider(state).read(LINEAGE_RESOURCE)
        assert model.schema == "manager-gui.manager-read-model.v0"
        assert build_lineage_fixture(state).to_json() == build_lineage_fixture(state).to_json()


def test_rendering_uses_neither_sqlite_nor_the_filesystem(monkeypatch: pytest.MonkeyPatch) -> None:
    models = [build_lineage_fixture(state) for state in LineageFixtureState]

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("lineage rendering must not touch SQLite or the filesystem")

    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(builtins, "open", forbidden)
    for model in models:
        assert render_lineage_view(model, query_context=CONTEXT)


# --- bounded size and performance ----------------------------------------------


def test_large_graph_is_bounded_by_depth_page_size_and_time() -> None:
    model = build_lineage_fixture("large", size=MAX_NODES)
    started = time.perf_counter()
    out = render_lineage_view(
        model, query_context=f"/?view=lineage&depth={MAX_DEPTH}&page_size=50&page=2"
    )
    elapsed = time.perf_counter() - started

    assert elapsed < 5.0
    assert len(_graph_nodes(out)) == len(_table_nodes(out)) == 50
    assert sorted(_graph_edges(out)) == sorted(_table_edges(out))
    assert len(_graph_nodes(out)) <= 100
    view = LineageViewModel.from_read_model(model, LineageQuery.from_query(f"/?depth={MAX_DEPTH}"))
    assert (
        len(view.visible_nodes) == 2 ** (MAX_DEPTH + 1) - 1
    )  # a binary tree stops at the depth bound
    assert view.outside_bounds == MAX_NODES - len(view.visible_nodes)


def test_wide_graph_page_is_capped_at_the_requested_page_size() -> None:
    nodes = [_n("hub", "conclusion"), *[_n(f"leaf-{i:03d}") for i in range(MAX_NODES - 1)]]
    edges = [_e(f"leaf-{i:03d}", "supports", "hub") for i in range(MAX_NODES - 1)]
    out = render_lineage_view(_model(nodes, edges), query_context="/?page_size=25")
    assert len(_graph_nodes(out)) == len(_table_nodes(out)) == 25
    assert f"Page 1 of {-(-MAX_NODES // 25)}" in out


def test_pages_beyond_the_hard_bounds_fail_closed() -> None:
    too_many = _model([_n(f"n{i}", "run") for i in range(MAX_NODES + 1)], [])
    assert _failure(LineageViewModel.from_read_model(too_many)) is LineageFailure.BOUND_EXCEEDED
    too_many_edges = _model(
        [_n("a", "conclusion"), _n("b")], [_e("b", "supports", "a")] * (MAX_EDGES + 1)
    )
    assert (
        _failure(LineageViewModel.from_read_model(too_many_edges)) is LineageFailure.BOUND_EXCEEDED
    )
    at_limit = _model([_n(f"n{i}", "run") for i in range(MAX_NODES)], [])
    assert LineageViewModel.from_read_model(at_limit).state is LineageState.READY
