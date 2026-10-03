"""Focused tests for the shared T2 WebUI shell."""

from __future__ import annotations

import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from manager_gui import (
    FixtureState,
    ReadModelStatus,
    fixture_provider,
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
