"""S6-T4 Search/Portal integration and final shared-shell exit gate."""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Iterator
from html import unescape
from typing import cast
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode, urlsplit
from urllib.request import Request, urlopen

import pytest

from manager_gui import (
    FORBIDDEN_PROVIDER_METHODS,
    FixtureState,
    ManagerReadModel,
    ReadModelStatus,
    SourceReference,
    fixture_provider,
    public_provider_methods,
)
from manager_gui.models import Availability, Derivation, JSONValue
from manager_gui.testing.i18n import assert_shared_shell_i18n
from manager_gui.web import ManagerGUIApp, create_server
from manager_gui.web.navigation import NAVIGATION
from manager_gui.web.s4_fixtures import S4_RESOURCES, build_s4_fixture
from manager_gui.web.s6_fixtures import S6_RESOURCES, build_s6_fixture
from manager_gui.web.status import display_state_for

ROUTES: dict[str, tuple[str, str]] = {
    "atlas": ("atlas-view", "atlas"),
    "stories": ("research-story-view", "stories"),
    "strategies": ("strategy-genome-view", "genomes"),
    "strategy-conditions": ("strategy-genome-conditions-view", "genome_conditions"),
    "strategy-genome-comparison": ("strategy-genome-comparison-view", "genome_comparison"),
    "memory": ("memory-view", "memory"),
    "memory-failures": ("failure-patterns-view", "memory"),
    "failure-patterns": ("failure-patterns-view", "failure_patterns"),
    "evidence": ("evidence-view", "evidence"),
    "lineage": ("lineage-view", "lineage"),
    "evidence-object-comparison": ("evidence-comparison-view", "evidence_comparison"),
    "derived-failure-grouping": ("failure-grouping-view", "failure_grouping"),
    "methodology": ("methodology-view", "methodology"),
    "history": ("history-view", "history"),
    "source-documents": ("source-documents-view", "source_documents"),
    "search": ("search-view", "search"),
    "portal": ("portal-view", "report_source"),
}

MUTATING_VERBS = ("POST", "PUT", "PATCH", "DELETE")
UNUSABLE_STATUSES = {
    ReadModelStatus.BLOCKED,
    ReadModelStatus.STALE,
    ReadModelStatus.INCOMPARABLE,
    ReadModelStatus.INTEGRITY_FAILURE,
    ReadModelStatus.API_UNAVAILABLE,
}


def _url(view: str, fixture: str = "complete", **extra: str) -> str:
    return "/?" + urlencode({"view": view, "fixture": fixture, **extra})


def _main(document: str) -> str:
    return document.split('<main id="main-content"', 1)[1].split("</main>", 1)[0]


def _hrefs(document: str, css_class: str) -> list[str]:
    return [
        unescape(value)
        for value in re.findall(rf'class="{css_class}"[^>]*href="([^"]+)"', document)
    ]


def _model_for(resource: str, state: FixtureState) -> ManagerReadModel:
    if resource in S6_RESOURCES:
        return build_s6_fixture(resource, state)
    if resource in S4_RESOURCES:
        return build_s4_fixture(resource, state)
    return fixture_provider(state).read(resource)


class _CountingProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def read(
        self, resource: str = "atlas", *, snapshot_token: str | None = None
    ) -> ManagerReadModel:
        self.calls.append((resource, snapshot_token))
        return _model_for(resource, FixtureState.COMPLETE)


@pytest.fixture
def served_app() -> Iterator[str]:
    server = create_server(port=0, fixture="complete")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("fixture", list(FixtureState))
def test_every_mounted_route_is_integrated_for_every_shared_fixture_state(
    fixture: FixtureState,
) -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    for view, (hook, resource) in ROUTES.items():
        url = _url(view, fixture.value, q="regression", panel="events", opaque="keep")
        document = app.render(url)
        english = app.render(url + "&lang=en")
        assert_shared_shell_i18n(document, english, route=view, source_url=url)
        model = app.read_model(app.request_state(url))
        main = _main(document)
        assert f'data-integration-hook="{hook}"' in main, view
        assert "Integration point ready" not in document, view
        assert f'data-status="{model.availability.status.value}"' in main, view
        assert 'class="read-only-badge"' in document
        assert 'class="raw-json"' in document
        assert 'method="post"' not in document.lower()
        if model.availability.status in UNUSABLE_STATUSES:
            assert 'data-display-state="error"' in main, (view, fixture)
            assert 'data-display-state="empty"' not in main, (view, fixture)
        elif model.availability.status is ReadModelStatus.MISSING:
            assert 'data-display-state="empty"' in main, (view, fixture)
        else:
            expected_display = display_state_for(model).value
            assert f'data-display-state="{expected_display}"' in main, (view, fixture)
        # The route's resource is selected by the mounted ViewId, not by payload text.
        assert app._resource_for_view(app.request_state(url).view) == resource


def test_s6_fixture_matrix_preserves_owner_status_and_round_trips() -> None:
    for resource in S6_RESOURCES:
        for fixture in FixtureState:
            model = build_s6_fixture(resource, fixture)
            assert isinstance(model, ManagerReadModel)
            assert ManagerReadModel.from_json(model.to_json()) == model
            view = "search" if resource == "search" else "portal"
            app = ManagerGUIApp(default_fixture=fixture)
            shell_model = app.read_model(app.request_state(_url(view, fixture.value)))
            assert model.availability.status is shell_model.availability.status


def test_navigation_has_search_and_portal_in_the_selected_locale() -> None:
    order = [item.view_id.value for item in NAVIGATION]
    assert order[-2:] == ["search", "portal"]
    chinese = ManagerGUIApp(default_fixture="complete").render(_url("portal"))
    assert 'aria-label="搜索"' in chinese
    assert 'aria-label="报告门户"' in chinese
    assert 'aria-current="page"' in chinese

    english = ManagerGUIApp(default_fixture="complete").render(_url("portal") + "&lang=en")
    assert 'aria-label="Search"' in english
    assert 'aria-label="Portal"' in english
    assert 'aria-current="page"' in english


def test_search_links_each_declared_identity_to_a_real_mounted_route() -> None:
    source = SourceReference(
        source_id="search-source",
        owner="fixture",
        kind="approved-index",
        locator="fixture://search/index",
        schema="search.v0",
        revision="r1",
    )
    records = [
        {
            "record_id": "record-1",
            "record_type": "record",
            "title": "link record",
            "source_ref": source.source_id,
        },
        {
            "record_id": "genome-1",
            "record_type": "genome",
            "genome_id": "genome-1",
            "title": "link genome",
            "source_ref": source.source_id,
        },
        {
            "record_id": "memory-1",
            "record_type": "memory-entry",
            "memory_id": "memory-1",
            "title": "link memory",
            "source_ref": source.source_id,
        },
        {
            "record_id": "evidence-1",
            "record_type": "evidence",
            "evidence_id": "evidence-1",
            "title": "link evidence",
            "source_ref": source.source_id,
        },
        {
            "record_id": "lineage-1",
            "record_type": "lineage",
            "lineage_id": "lineage-1",
            "title": "link lineage",
            "source_ref": source.source_id,
        },
        {
            "record_id": "document-1",
            "document_id": "document-1",
            "document_type": "report",
            "title": "link document",
            "source_ref": source.source_id,
        },
    ]
    model = ManagerReadModel(
        data=cast(JSONValue, {"records": records, "pagination": {"complete": True}}),
        source_refs=(source,),
        as_of="2026-10-03T12:00:00Z",
        snapshot_token="search-snapshot-v1",
        derivation=Derivation(kind="direct", version="v0"),
        availability=Availability(status=ReadModelStatus.KNOWN, complete=True),
    )
    from manager_gui.web.search import render_search_view

    document = render_search_view(
        model,
        query="link",
        query_context=(
            "/?view=search&fixture=complete&q=link&panel=events&snapshot_token=s1&"
            "opaque=keep&page=3&page_size=20&cursor=old"
        ),
    )
    targets = {}
    for href in _hrefs(document, "search-result-link"):
        query = dict(parse_qsl(urlsplit(href).query))
        targets[query.get("record_type", "")] = query
    assert targets["record"]["view"] == "atlas"
    assert targets["genome"]["view"] == "strategies"
    assert targets["genome"]["genome_id"] == "genome-1"
    assert targets["memory-entry"]["view"] == "memory"
    assert targets["memory-entry"]["memory_id"] == "memory-1"
    assert targets["evidence"]["view"] == "evidence"
    assert targets["evidence"]["record_id"] == "evidence-1"
    assert targets["lineage"]["view"] == "lineage"
    assert targets["lineage"]["record_id"] == "lineage-1"
    assert targets["report"]["view"] == "source-documents"
    assert targets["report"]["document_id"] == "document-1"
    for query in targets.values():
        assert query["fixture"] == "complete"
        assert query["q"] == "link"
        assert query["panel"] == "events"
        assert query["snapshot_token"] == "s1"
        assert query["opaque"] == "keep"
        assert "page" not in query and "page_size" not in query and "cursor" not in query


def test_search_partial_pagination_and_unavailable_states_are_honest() -> None:
    app = ManagerGUIApp(default_fixture="complete")
    partial = app.render(_url("search", "partial", q="absent") + "&lang=en")
    assert 'data-search-state="partial"' in partial
    assert 'data-pagination-complete="false"' in partial
    assert 'data-search-next-cursor="fixture-search-next-v0"' in partial
    assert "global no-match is not established" in partial
    assert "complete snapshot" not in partial
    unavailable = app.render(_url("search", "api_unavailable", q="absent") + "&lang=en")
    assert 'data-status="api_unavailable"' in unavailable
    assert 'data-search-state="api_unavailable"' in unavailable
    assert 'data-display-state="empty"' not in _main(unavailable)
    blocked = app.render(_url("search", "blocked") + "&lang=en")
    assert 'data-status="blocked"' in blocked
    assert 'data-display-state="error"' in _main(blocked)


def test_portal_keeps_publication_artifact_and_boundary_distinct() -> None:
    app = ManagerGUIApp(default_fixture="complete")
    complete = app.render(_url("portal") + "&lang=en")
    assert 'data-portal-state="ready"' in complete
    assert 'data-source-publication-state="published"' in complete
    assert 'data-artifact-state="ready"' in complete
    assert "Source publication" in complete and "Generated artifact" in complete
    assert "not canonical research state" in complete
    page_markup = _main(complete).split('<div class="panel-actions"', 1)[0]
    assert not re.search(r"<button[^>]*(rebuild|run)", page_markup, re.IGNORECASE)
    not_generated = app.render(_url("portal", "partial"))
    assert 'data-portal-state="partial"' in not_generated
    missing = app.render(_url("portal", "empty"))
    assert 'data-portal-state="missing"' in missing
    integrity = app.render(_url("portal", "integrity_failure"))
    assert 'data-status="integrity_failure"' in integrity
    assert 'data-portal-state="integrity-failure"' in integrity
    unavailable = app.render(_url("portal", "api_unavailable"))
    assert 'data-status="api_unavailable"' in unavailable
    assert 'data-portal-state="api-unavailable"' in unavailable


@pytest.mark.parametrize("view", list(ROUTES))
def test_each_mounted_route_reads_only_its_public_resource_once(view: str) -> None:
    provider = _CountingProvider()
    app = ManagerGUIApp(provider)
    app.render(_url(view, snapshot_token="pin", q="audit"))
    resource = ROUTES[view][1]
    assert provider.calls == [(resource, "pin")]
    assert public_provider_methods(provider) == ("read",)
    assert FORBIDDEN_PROVIDER_METHODS.isdisjoint(public_provider_methods(provider))


def test_all_routes_render_without_filesystem_access(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("Manager GUI routes must not access arbitrary storage")

    monkeypatch.setattr(builtins, "open", refuse)
    app = ManagerGUIApp(default_fixture="complete")
    for view in ROUTES:
        document = app.render(_url(view, panel="events"))
        assert 'class="read-only-badge"' in document
        assert 'lang="zh-CN"' in document


def test_cli_and_live_http_exit_gate_covers_every_route_and_read_only_verbs(
    served_app: str,
) -> None:
    for view, (hook, _) in ROUTES.items():
        with urlopen(f"{served_app}{_url(view)}") as response:
            assert response.status == 200
            assert f'data-integration-hook="{hook}"' in response.read().decode("utf-8")
        with urlopen(f"{served_app}/api/read-model?view={view}&fixture=complete") as response:
            assert json.loads(response.read())["schema"] == "manager-gui.manager-read-model.v0"
        with urlopen(f"{served_app}/api/export?view={view}&fixture=complete") as response:
            payload = json.loads(response.read())
            assert payload["view"] == view and payload["read_only"] is True
    for path in ("/", "/api/read-model", "/api/export", "/health"):
        for verb in MUTATING_VERBS:
            with pytest.raises(HTTPError) as caught:
                urlopen(Request(f"{served_app}{path}", method=verb, data=b"{}"))
            assert caught.value.code == 405
            assert caught.value.headers["Allow"] == "GET, HEAD"
