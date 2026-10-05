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
    Locale,
    ManagerGUIApp,
    Translator,
    create_server,
    display_state_for,
    render_operational_state,
    render_status_block,
    with_lang,
)
from manager_gui.web.navigation import PageWindow, context_link
from manager_gui.web.server import build_parser

TRANSLATOR = Translator()


def test_status_renderer_covers_every_read_model_status() -> None:
    for status in ReadModelStatus:
        rendered = render_status_block(
            status, translator=TRANSLATOR, reason=f"reason-{status.value}"
        )

        assert f'data-status="{status.value}"' in rendered
        assert f"reason-{status.value}" in rendered
        assert 'class="status-block' in rendered


def test_operational_renderer_keeps_loading_empty_partial_and_error_distinct() -> None:
    for state in DisplayState:
        rendered = render_operational_state(state, translator=TRANSLATOR)

        assert f'data-display-state="{state.value}"' in rendered
        assert 'class="status-label"' in rendered
    assert 'aria-live="polite"' in render_operational_state(
        DisplayState.LOADING, translator=TRANSLATOR
    )


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
    document = ManagerGUIApp().render(
        "/?view=evidence&fixture=partial&panel=events&q=campaign&lang=en"
    )

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


def test_locale_request_state_normalizes_aliases_and_removes_invalid_context() -> None:
    app = ManagerGUIApp()

    assert app.request_state("/?lang=en").lang is Locale.EN
    assert app.request_state("/?lang=EN-us").locale is Locale.EN
    chinese = app.request_state("/?lang=zh")
    assert chinese.lang is Locale.ZH_CN
    assert chinese.locale is Locale.ZH_CN
    assert dict(chinese.context).get("lang") is None
    assert ("lang", "zh-CN") in chinese.query_pairs()

    invalid = app.request_state("/?view=atlas&lang=fr&scope=")
    assert invalid.lang is None
    assert invalid.locale is Locale.ZH_CN
    assert dict(invalid.context) == {"scope": ""}
    assert all(key != "lang" for key, _ in invalid.query_pairs())

    english_default = ManagerGUIApp(default_locale="en")
    assert english_default.request_state("/").locale is Locale.EN
    assert english_default.request_state("/?lang=fr").locale is Locale.EN


def test_shell_language_switcher_and_explicit_search_state() -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    raw_url = "/?view=search&fixture=complete&q=&tag=a&tag=b&tag=&page=2&lang=EN-us"
    document = app.render(raw_url)
    expected_chinese = with_lang(raw_url, Locale.ZH_CN)

    assert '<html lang="en">' in document
    assert 'name="lang" value="en"' in document
    assert 'aria-label="Language"' in document
    assert '<span lang="en" aria-current="true">English</span>' in document
    assert f'hreflang="zh-CN" href="{expected_chinese.replace("&", "&amp;")}"' in document
    assert 'name="lang" value="en"' in document
    nav_hrefs = re.findall(r'class="nav-link"[^>]+href="([^"]+)"', document)
    assert nav_hrefs and all("lang=en" in unescape(href) for href in nav_hrefs)

    invalid = app.render("/?view=search&fixture=complete&lang=fr&q=term")
    assert '<html lang="zh-CN">' in invalid
    assert "lang=fr" not in unescape(invalid)
    assert 'name="lang"' not in invalid
    assert 'aria-label="语言"' in invalid


def test_navigation_and_get_form_preserve_repeated_opaque_query_state() -> None:
    raw_url = "/?view=search&fixture=complete&lang=en&tag=a&tag=b&tag="
    document = ManagerGUIApp(default_fixture=FixtureState.COMPLETE).render(raw_url)
    nav_hrefs = re.findall(r'class="nav-link"[^>]+href="([^"]+)"', document)
    assert nav_hrefs
    for href in nav_hrefs:
        decoded = unescape(href)
        assert decoded.count("tag=") == 3
        assert "lang=en" in decoded
    assert document.count('name="tag"') >= 3


def test_language_context_preserves_page_and_api_exports_strip_lang() -> None:
    assert context_link("/?view=search&page=4&lang=en", view="search", lang="zh-CN") == (
        "/?lang=zh-CN&page=4&view=search"
    )
    repeated = context_link(
        "/?view=search&page=4&tag=b&tag=a&lang=en",
        view="search",
        page=3,
    )
    assert repeated.count("tag=") == 2
    assert "tag=a" in repeated and "tag=b" in repeated

    pagination = PageWindow(2, 2, 5).render(
        "/?view=search&lang=en&tag=a&tag=b", view="search"
    )
    assert "Previous" in pagination and "Next" in pagination
    assert "上一页" not in pagination and "下一页" not in pagination
    assert pagination.count("tag=") >= 4

    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    base = "/?view=atlas&fixture=complete&snapshot_token=s1&q=term"
    payloads = [
        app.render_export(base),
        app.render_export(base + "&lang=zh-CN"),
        app.render_export(base + "&lang=en"),
    ]
    assert payloads[0] == payloads[1] == payloads[2]
    payload = json.loads(payloads[0])
    assert "lang" not in payload["query"]
    assert "lang" not in payload["query_params"]
    assert app.render_json(base) == app.render_json(base + "&lang=en")


def test_web_server_cli_accepts_a_default_language() -> None:
    args = build_parser().parse_args(["--fixture", "complete", "--lang", "en"])
    assert args.lang == "en"
    server = create_server(port=0, fixture="complete", default_locale=args.lang)
    try:
        assert '<html lang="en">' in server.app.render("/")
    finally:
        server.server_close()


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
    assert "只读" in story

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


def test_s3_integrated_memory_and_failure_routes_preserve_context_and_lineage() -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    context = (
        "fixture=complete&panel=events&q=data-gate&snapshot_token=s3-snapshot"
        "&family=memory-family-fixture-1&failure_category=data_blocker"
    )
    memory = app.render(f"/?view=memory&{context}&memory_id=memory-fixture-1")
    assert 'data-integration-hook="memory-view"' in memory
    assert 'data-memory-authority="formal_research_memory"' in memory
    assert 'data-status="known"' in memory
    assert 'class="read-only-badge"' in memory
    assert 'id="inspector"' in memory and 'id="event-drawer"' in memory
    assert "Formal data-gate failure memory" in memory
    assert "Open Memory failure / lineage" in memory
    assert "Open derived pattern" in memory
    assert "fixture=complete" in unescape(memory)
    assert "snapshot_token=s3-snapshot" in unescape(memory)

    failures = app.render(
        f"/?view=memory-failures&{context}&failure_id=memory-fixture-1"
    )
    assert 'data-integration-hook="failure-patterns-view"' in failures
    assert 'data-memory-layer="formal-research-memory"' in failures
    assert 'data-lineage-coverage="complete"' in failures
    for target in (
        "fixture://manager-gui/campaign/campaign-fixture-1",
        "fixture://manager-gui/run/run-fixture-1",
        "fixture://manager-gui/evidence/evidence-fixture-1",
        "fixture://manager-gui/source-document/document-fixture-1",
    ):
        assert target in failures
    assert "snapshot_token=s3-snapshot" in unescape(failures)

    patterns = app.render(f"/?view=failure-patterns&{context}&pattern_id=pattern-fixture-1")
    assert 'data-integration-hook="failure-patterns-view"' in patterns
    assert 'data-pattern-status="derived"' in patterns
    assert "Formal Research Memory" in patterns
    assert "Ordinary failure records" in patterns
    assert "Open Memory" in patterns
    assert "pattern_id=pattern-fixture-1" in unescape(patterns)
    assert "failure_id=failure-fixture-1" in unescape(patterns)


def test_s3_integrated_fixture_states_keep_empty_partial_and_source_failures_distinct() -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    expected = {
        FixtureState.EMPTY: "missing",
        FixtureState.COMPLETE: "known",
        FixtureState.PARTIAL: "known",
        FixtureState.BLOCKED: "blocked",
        FixtureState.STALE: "stale",
        FixtureState.INCOMPARABLE: "incomparable",
        FixtureState.INTEGRITY_FAILURE: "integrity_failure",
        FixtureState.API_UNAVAILABLE: "api_unavailable",
    }
    for fixture, status in expected.items():
        memory = app.render(f"/?view=memory&fixture={fixture.value}")
        failures = app.render(f"/?view=failure-patterns&fixture={fixture.value}")
        assert f'data-status="{status}"' in memory
        assert f'data-status="{status}"' in failures
        assert 'class="read-only-badge"' in memory
        assert 'id="event-drawer"' in failures
        if fixture is FixtureState.EMPTY:
            assert 'data-display-state="empty"' in memory
            assert "No formal Research Memory entries are recorded" in memory
        elif fixture is FixtureState.PARTIAL:
            assert "Partial Memory scope" in memory
            assert 'data-memory-state="not-determined"' not in memory
        elif fixture in {
            FixtureState.BLOCKED,
            FixtureState.STALE,
            FixtureState.INCOMPARABLE,
            FixtureState.INTEGRITY_FAILURE,
            FixtureState.API_UNAVAILABLE,
        }:
            assert 'data-memory-empty-state="not-determined"' in memory
            assert 'data-memory-state="not-determined"' in failures


def test_s3_zero_entry_and_missing_lineage_states_are_honest() -> None:
    from dataclasses import replace

    complete = fixture_provider(FixtureState.COMPLETE).read("memory")
    zero_entry = replace(
        complete,
        data={"memory_entries": [], "failures": [], "derived_patterns": []},
    )

    class Provider:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None]] = []

        def read(self, resource: str = "atlas", *, snapshot_token: str | None = None):
            self.calls.append((resource, snapshot_token))
            return zero_entry

    provider = Provider()
    app = ManagerGUIApp(provider)
    memory = app.render("/?view=memory&fixture=complete&panel=events&q=zero")
    failures = app.render("/?view=memory-failures&fixture=complete&panel=events&q=zero")
    assert 'data-memory-empty="true"' in memory
    assert "No Research Memory entries are recorded" in memory
    assert "not evidence that Memory is empty" not in memory
    assert 'data-memory-state="empty"' in failures
    assert "No formal Research Memory entries are recorded" in failures
    assert provider.calls == [("memory", None), ("memory", None)]

    missing_lineage = replace(
        complete,
        data={
            "memory_entries": [
                {
                    "memory_id": "memory-missing-lineage",
                    "title": "Unlinked memory",
                    "safe_summary": "Only the explicit safe summary is known.",
                    "references": ["not-published"],
                    "lineage": ["not-published"],
                }
            ],
            "failures": [
                {
                    "failure_id": "failure-missing-lineage",
                    "title": "Unlinked failure",
                    "outcome": "rejected",
                }
            ],
            "derived_patterns": [],
        },
    )

    class MissingLineageProvider:
        def read(self, resource: str = "atlas", *, snapshot_token: str | None = None):
            del resource, snapshot_token
            return missing_lineage

    document = ManagerGUIApp(MissingLineageProvider()).render(
        "/?view=memory-failures&fixture=complete&failure_id=failure-missing-lineage"
    )
    assert "Missing / Unconfirmed link" in document
    assert "https://not-published" not in document
    for label in ("Campaign", "Candidate", "Run", "Evidence", "Artifact", "Source Document"):
        assert label in document


def test_s3_provider_audit_reads_memory_resources_once_and_exposes_no_mutations() -> None:
    class CountingProvider:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None]] = []

        def read(self, resource: str = "atlas", *, snapshot_token: str | None = None):
            self.calls.append((resource, snapshot_token))
            return fixture_provider("complete").read(resource, snapshot_token=snapshot_token)

    provider = CountingProvider()
    app = ManagerGUIApp(provider)
    app.render("/?view=memory&fixture=complete&snapshot_token=memory-snapshot")
    app.render("/?view=memory-failures&fixture=complete&snapshot_token=failure-snapshot")
    app.render("/?view=failure-patterns&fixture=complete&snapshot_token=pattern-snapshot")
    assert provider.calls == [
        ("memory", "memory-snapshot"),
        ("memory", "failure-snapshot"),
        ("failure_patterns", "pattern-snapshot"),
    ]
    assert public_provider_methods(provider) == ("read",)
    assert not FORBIDDEN_PROVIDER_METHODS.intersection(public_provider_methods(provider))
