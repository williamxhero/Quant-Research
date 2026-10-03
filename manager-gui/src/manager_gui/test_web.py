"""Focused tests for the shared T2 WebUI shell."""

from __future__ import annotations

import json
import re
import threading
from html import unescape
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from manager_gui import (
    FIXTURE_STATES,
    FORBIDDEN_PROVIDER_METHODS,
    FixtureState,
    ReadModelStatus,
    fixture_provider,
    public_provider_methods,
)
from manager_gui.web import (
    DisplayState,
    ManagerGUIApp,
    create_server,
    display_state_for,
    render_operational_state,
    render_status_block,
)


def test_status_renderer_covers_every_read_model_status() -> None:
    for status in ReadModelStatus:
        rendered = render_status_block(status, reason=f"reason-{status.value}")

        assert f'data-status="{status.value}"' in rendered
        assert f"reason-{status.value}" in rendered
        assert 'class="status-block' in rendered


def test_operational_renderer_keeps_loading_empty_partial_and_error_distinct() -> None:
    for state in DisplayState:
        rendered = render_operational_state(state)

        assert f'data-display-state="{state.value}"' in rendered
        assert state.value.title() in rendered
    assert 'aria-live="polite"' in render_operational_state(DisplayState.LOADING)


def test_fixture_status_maps_to_distinct_display_states() -> None:
    expected = {
        FixtureState.EMPTY: DisplayState.EMPTY,
        FixtureState.PARTIAL: DisplayState.PARTIAL,
        FixtureState.BLOCKED: DisplayState.ERROR,
        FixtureState.STALE: DisplayState.ERROR,
        FixtureState.INCOMPARABLE: DisplayState.ERROR,
        FixtureState.INTEGRITY_FAILURE: DisplayState.ERROR,
        FixtureState.API_UNAVAILABLE: DisplayState.ERROR,
    }
    for fixture, state in expected.items():
        assert display_state_for(fixture_provider(fixture).read()) is state


def test_shell_preserves_navigation_context_and_read_only_surface() -> None:
    document = ManagerGUIApp().render("/?view=evidence&fixture=partial&panel=events&q=campaign")

    for label in (
        "Atlas",
        "Stories",
        "Strategies / Genomes",
        "Memory",
        "Evidence",
        "Methodology",
        "History",
        "Search",
    ):
        assert label in document
    assert 'aria-current="page"' in document
    assert "READ ONLY" in document
    assert 'id="inspector"' in document
    assert 'id="event-drawer"' in document
    assert "campaign" in document
    assert 'data-integration-hook="evidence-view"' in document
    assert 'method="get"' in document
    assert "No mutation route" not in document


def test_s5_integrated_routes_preserve_shell_links_and_scope_context() -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    routes = {
        "methodology": 'data-integration-hook="methodology-view"',
        "history": 'data-integration-hook="history-view"',
        "source-documents": 'data-integration-hook="source-documents-view"',
    }
    for view, hook in routes.items():
        document = app.render(
            f"/?view={view}&fixture=complete&scope=CPA&panel=events&q=research&snapshot_token=s5"
        )
        assert hook in document
        assert 'class="read-only-badge"' in document
        assert 'id="inspector"' in document
        assert 'id="event-drawer"' in document
        assert "research" in document
        assert "s5" in document
        assert 'class="page-pagination"' in document

    methodology = app.render("/?view=methodology&fixture=complete&scope=A0&q=methods")
    assert 'data-boundary="canonical-fact"' in methodology
    assert 'data-link-kind="document"' in methodology
    assert 'view=source-documents' in unescape(methodology)
    assert 'document_id=doc-g0' in unescape(methodology)
    assert 'view=history' in unescape(methodology)
    assert 'record_id=record-g0' in unescape(methodology)

    history = app.render("/?view=history&fixture=complete&scope=S3&q=events")
    assert 'data-history-scope="S3"' in history
    assert 'data-boundary="canonical-fact"' in history
    assert 'data-link-kind="source-artifact"' in history
    assert 'data-link-kind="document"' in history
    assert 'document_id=s3-' in unescape(history)

    documents = app.render("/?view=source-documents&fixture=complete&scope=V1.x&q=docs")
    assert 'data-document-scope="V1.x"' in documents
    assert 'data-boundary="document-interpretation"' in documents
    assert 'data-link-kind="record"' in documents
    assert 'view=history' in unescape(documents)


def test_s5_scope_fixture_navigation_covers_all_declared_scopes() -> None:
    app = ManagerGUIApp(default_fixture="complete")
    for scope in ("A0", "S3", "CPA", "V1.x"):
        history = app.render(f"/?view=history&fixture=complete&scope={scope}")
        documents = app.render(f"/?view=source-documents&fixture=complete&scope={scope}")
        assert f'data-history-scope="{scope}"' in history
        assert f'data-document-scope="{scope}"' in documents
        assert f"fixture-history-{scope}-v0" in history
        assert f"fixture-documents-{scope}-v0" in documents


def test_s5_integrated_fixture_states_remain_explicit() -> None:
    app = ManagerGUIApp(default_fixture="complete")
    for fixture in FixtureState:
        expected = fixture_provider(fixture).read("atlas").availability.status.value
        for view in ("methodology", "history", "source-documents"):
            document = app.render(f"/?view={view}&fixture={fixture.value}&scope=A0")
            assert f'data-status="{expected}"' in document
            assert 'class="read-only-badge"' in document
            assert 'id="event-drawer"' in document
    assert 'data-document-index-state="boundary-blocked"' not in app.render(
        "/?view=source-documents&fixture=complete&scope=A0"
    )


def test_s5_integration_reads_each_injected_resource_once() -> None:
    from manager_gui.web.documents import build_source_documents_fixture
    from manager_gui.web.history import build_history_fixture
    from manager_gui.web.methodology import build_methodology_fixture

    class CountingProvider:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None]] = []

        def read(self, resource: str = "atlas", *, snapshot_token: str | None = None):
            self.calls.append((resource, snapshot_token))
            if resource == "methodology":
                return build_methodology_fixture("complete")
            if resource == "history":
                return build_history_fixture("A0")
            if resource == "source_documents":
                return build_source_documents_fixture("A0")
            return fixture_provider("complete").read(resource, snapshot_token=snapshot_token)

    provider = CountingProvider()
    app = ManagerGUIApp(provider)
    app.render("/?view=methodology&fixture=complete&snapshot_token=method")
    app.render("/?view=history&fixture=complete&snapshot_token=history")
    app.render("/?view=source-documents&fixture=complete&snapshot_token=documents")
    assert provider.calls == [
        ("methodology", "method"),
        ("history", "history"),
        ("source_documents", "documents"),
    ]
    assert public_provider_methods(provider) == ("read",)
    assert not FORBIDDEN_PROVIDER_METHODS.intersection(public_provider_methods(provider))


def test_local_server_serves_html_json_and_rejects_mutations() -> None:
    server = create_server(port=0, fixture="partial")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        with urlopen(f"{base_url}/?view=history&fixture=stale") as response:
            document = response.read().decode("utf-8")
            assert response.status == 200
            assert "History" in document
            assert 'data-status="stale"' in document

        with urlopen(f"{base_url}/api/read-model?view=atlas&fixture=partial") as response:
            payload = json.loads(response.read())
            assert response.status == 200
            assert payload["schema"] == "manager-gui.manager-read-model.v0"
            assert payload["availability"]["status"] == "known"

        request = Request(f"{base_url}/", method="POST")
        try:
            urlopen(request)
        except HTTPError as error:
            assert error.code == 405
            assert error.headers["Allow"] == "GET, HEAD"
        else:  # pragma: no cover - urlopen must raise for a 405 response
            raise AssertionError("the fixture server exposed a mutation route")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_s1_mounts_atlas_and_story_hooks_as_one_read_only_flow() -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    atlas_url = "/?view=atlas&fixture=complete&panel=events&q=campaign"
    atlas = app.render(atlas_url)

    assert 'data-integration-hook="atlas-view"' in atlas
    assert "Integration point ready" not in atlas
    assert 'data-status="known"' in atlas
    assert "fixture-complete-v0" in atlas
    assert 'class="read-only-badge"' in atlas
    assert 'data-record-story="campaign-fixture-1"' in atlas

    match = re.search(
        r'class="atlas-story-link"[^>]+href="([^"]+)"',
        atlas,
    )
    assert match is not None
    story_url = unescape(match.group(1))
    story_query = urlsplit(story_url).query
    assert "view=stories" in story_query
    assert "fixture=complete" in story_query
    assert "panel=events" in story_query
    assert "q=campaign" in story_query
    assert "record_id=campaign-fixture-1" in story_query

    story = app.render(story_url)
    assert 'data-integration-hook="research-story-view"' in story
    assert 'data-story-mode="narrative"' in story
    assert "Fixture campaign" in story
    assert "fixture://strategy-workspace/stories/campaigns" in story
    assert 'id="inspector"' in story
    assert 'id="event-drawer"' in story
    assert "READ ONLY" in story

    for mode in ("narrative", "evidence", "timeline"):
        mode_document = app.render(
            "/?view=stories&fixture=complete&mode="
            f"{mode}&campaign=campaign-fixture-1&record_type=campaign&q=campaign"
        )
        assert f'data-story-mode="{mode}"' in mode_document
        assert "campaign=campaign-fixture-1" in mode_document
        assert "record_type=campaign" in mode_document
        assert "q=campaign" in mode_document
        assert "view=stories" in mode_document


def test_s1_integrated_routes_keep_every_fixture_state_explicit() -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    for fixture in FixtureState:
        expected = fixture_provider(fixture).read("atlas").availability.status.value
        atlas = app.render(f"/?view=atlas&fixture={fixture.value}")
        story = app.render(f"/?view=stories&fixture={fixture.value}&mode=evidence")

        assert f'data-status="{expected}"' in atlas
        assert f'data-status="{expected}"' in story
        assert 'class="read-only-badge"' in atlas
        assert 'class="read-only-badge"' in story
        assert 'id="inspector"' in atlas
        assert 'id="event-drawer"' in story

    complete = app.render("/?view=atlas&fixture=complete")
    assert 'data-display-state="ready"' in complete
    empty = app.render("/?view=stories&fixture=empty")
    assert 'data-display-state="empty"' in empty
    assert "No research material recorded" in empty


def test_s1_provider_audit_exposes_only_the_read_operation() -> None:
    for fixture in FIXTURE_STATES:
        provider = fixture_provider(fixture)
        methods = public_provider_methods(provider)
        assert methods == ("read",)
        assert not FORBIDDEN_PROVIDER_METHODS.intersection(methods)


def test_s1_page_hooks_reuse_the_shell_read_without_a_second_provider_call() -> None:
    class CountingProvider:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None]] = []

        def read(
            self,
            resource: str = "atlas",
            *,
            snapshot_token: str | None = None,
        ):
            self.calls.append((resource, snapshot_token))
            return fixture_provider("complete").read(
                resource,
                snapshot_token=snapshot_token,
            )

    atlas_provider = CountingProvider()
    ManagerGUIApp(atlas_provider).render("/?view=atlas&fixture=complete")
    assert atlas_provider.calls == [("atlas", None)]

    story_provider = CountingProvider()
    ManagerGUIApp(story_provider).render("/?view=stories&fixture=complete")
    assert story_provider.calls == [("stories", None)]


    server = create_server(port=0, fixture="complete")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        with urlopen(
            f"{base_url}/?view=stories&fixture=complete&mode=timeline&q=campaign"
        ) as response:
            document = response.read().decode("utf-8")
            assert response.status == 200
            assert 'data-story-mode="timeline"' in document
            assert "fixture://strategy-workspace/stories/campaigns" in document

        with urlopen(
            f"{base_url}/api/read-model?view=stories&fixture=complete&mode=evidence"
        ) as response:
            payload = json.loads(response.read())
            assert response.status == 200
            assert payload["schema"] == "manager-gui.manager-read-model.v0"
            assert payload["availability"] == {
                "status": "known",
                "complete": True,
                "reason": "The complete fixture contains the declared integration path.",
                "retryable": False,
            }
            assert payload["data"]["campaign"]["id"] == "campaign-fixture-1"

        with urlopen(f"{base_url}/health") as response:
            payload = json.loads(response.read())
            assert response.status == 200
            assert payload == {
                "status": "ok",
                "read_only": True,
                "schema": "manager-gui.manager-read-model.v0",
            }

        request = Request(f"{base_url}/api/read-model", method="POST")
        try:
            urlopen(request)
        except HTTPError as error:
            assert error.code == 405
            assert error.headers["Allow"] == "GET, HEAD"
        else:  # pragma: no cover - urlopen must raise for a 405 response
            raise AssertionError("the fixture server exposed a mutation route")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_s2_integrated_genome_condition_and_comparison_routes_preserve_context() -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    context = (
        "fixture=complete&panel=events&q=signal&snapshot_token=s2-snapshot"
        "&genome_id=genome-fixture-1&right_genome_id=genome-right"
    )
    genome = app.render(f"/?view=strategies&{context}")
    assert 'data-integration-hook="strategy-genome-view"' in genome
    assert 'data-status="known"' in genome
    assert 'class="read-only-badge"' in genome
    assert 'id="inspector"' in genome
    assert 'id="event-drawer"' in genome
    assert "s2-snapshot" in genome
    assert "fixture://manager-gui/genomes" in genome

    genome_links = re.findall(
        r'class="genome-(?:conditions|comparison)-link" href="([^"]+)"', genome
    )
    assert len(genome_links) == 2
    for link in genome_links:
        query = urlsplit(unescape(link)).query
        assert "fixture=complete" in query
        assert "genome_id=genome-fixture-1" in query
        assert "panel=events" in query
        assert "q=signal" in query
        assert "snapshot_token=s2-snapshot" in query

    conditions = app.render(
        "/?view=strategy-conditions&fixture=complete&genome_id=genome-fixture-1"
        "&panel=events&q=signal&snapshot_token=s2-snapshot"
    )
    assert 'data-integration-hook="strategy-genome-conditions-view"' in conditions
    assert 'data-condition-group="applicability"' in conditions
    assert 'data-condition-group="invalidation"' in conditions
    assert 'data-condition-group="descriptor"' in conditions
    assert "fixture://manager-gui/genome-conditions" in conditions
    assert 'class="condition-genome-link"' in conditions
    assert 'class="condition-comparison-link"' in conditions
    assert 'class="read-only-badge"' in conditions

    comparison = app.render(
        "/?view=strategy-genome-comparison&fixture=incomparable"
        "&left_genome_id=genome-left&right_genome_id=genome-right"
        "&panel=events&q=signal&snapshot_token=s2-snapshot"
    )
    assert 'data-integration-hook="strategy-genome-comparison-view"' in comparison
    assert 'data-comparison-result="incomparable"' in comparison
    assert "data_requirements.version" in comparison
    assert 'class="comparison-left-genome-link"' in comparison
    assert 'class="comparison-left-conditions-link"' in comparison
    assert 'class="comparison-right-genome-link"' in comparison
    assert "s2-snapshot" in comparison
    assert 'id="inspector"' in comparison
    assert 'id="event-drawer"' in comparison


def test_s2_integrated_fixture_states_keep_empty_partial_and_failures_distinct() -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    expected_status = {
        FixtureState.EMPTY: "missing",
        FixtureState.COMPLETE: "known",
        FixtureState.PARTIAL: "known",
        FixtureState.BLOCKED: "blocked",
        FixtureState.STALE: "stale",
        FixtureState.INCOMPARABLE: "incomparable",
        FixtureState.INTEGRITY_FAILURE: "integrity_failure",
        FixtureState.API_UNAVAILABLE: "api_unavailable",
    }
    for fixture, status in expected_status.items():
        genome = app.render(f"/?view=strategies&fixture={fixture.value}")
        conditions = app.render(f"/?view=strategy-conditions&fixture={fixture.value}")
        assert f'data-status="{status}"' in genome
        assert f'data-status="{status}"' in conditions
        assert 'class="read-only-badge"' in genome
        assert 'id="event-drawer"' in conditions
        if fixture is FixtureState.EMPTY:
            assert 'data-display-state="empty"' in genome
            assert "No Genome records are present in this scope." in genome
        elif fixture is FixtureState.PARTIAL:
            assert 'data-display-state="partial"' in genome
            assert 'data-display-state="partial"' in conditions
        elif fixture in {
            FixtureState.BLOCKED,
            FixtureState.STALE,
            FixtureState.INCOMPARABLE,
            FixtureState.INTEGRITY_FAILURE,
            FixtureState.API_UNAVAILABLE,
        }:
            assert 'data-display-state="error"' in genome
            assert 'data-display-state="error"' in conditions

    comparison = app.render("/?view=strategy-genome-comparison&fixture=incomparable")
    assert 'data-comparison-result="incomparable"' in comparison
    assert "Incompatible axes" in comparison


def test_s2_integrated_provider_reads_each_route_once_and_exposes_no_mutations() -> None:
    from manager_gui.web.comparison import build_genome_comparison_fixture
    from manager_gui.web.conditions import build_conditions_fixture
    from manager_gui.web.genome import build_genome_fixture

    class CountingProvider:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None]] = []

        def read(self, resource: str = "atlas", *, snapshot_token: str | None = None):
            self.calls.append((resource, snapshot_token))
            if resource == "genomes":
                return build_genome_fixture("complete")
            if resource == "genome_conditions":
                return build_conditions_fixture("complete")
            if resource == "genome_comparison":
                return build_genome_comparison_fixture("different")
            return fixture_provider("complete").read(resource, snapshot_token=snapshot_token)

    provider = CountingProvider()
    app = ManagerGUIApp(provider)
    app.render("/?view=strategies&fixture=complete&snapshot_token=genome-snapshot")
    app.render("/?view=strategy-conditions&fixture=complete&snapshot_token=condition-snapshot")
    app.render("/?view=strategy-genome-comparison&fixture=complete&snapshot_token=comparison-snapshot")

    assert provider.calls == [
        ("genomes", "genome-snapshot"),
        ("genome_conditions", "condition-snapshot"),
        ("genome_comparison", "comparison-snapshot"),
    ]
    assert public_provider_methods(provider) == ("read",)
    assert not FORBIDDEN_PROVIDER_METHODS.intersection(public_provider_methods(provider))
