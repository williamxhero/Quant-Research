"""Focused S6-T3 tests: common states, accessibility, export, URL and read-only audit."""

from __future__ import annotations

import builtins
import json
import threading
from collections.abc import Iterator
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode, urlsplit
from urllib.request import Request, urlopen

import pytest

from manager_gui import (
    FORBIDDEN_PROVIDER_METHODS,
    FixtureState,
    ManagerReadModel,
    ReadModelStatus,
    fixture_provider,
    public_provider_methods,
)
from manager_gui.testing.i18n import assert_shared_shell_i18n
from manager_gui.web import (
    DisplayState,
    Locale,
    ManagerGUIApp,
    Translator,
    create_server,
    display_state_for,
    render_common_state,
    render_operational_state,
    render_status_block,
)
from manager_gui.web.assets import JS, js_messages, render_js
from manager_gui.web.interaction import (
    EXPORT_SCHEMA,
    current_view_export,
    export_filename,
    export_url,
    opaque_copy_button,
    render_alternative_view,
    render_export_control,
)
from manager_gui.web.lineage import _truncate
from manager_gui.web.navigation import NAVIGATION, ViewId, navigation_label_zh
from manager_gui.web.status import (
    DISPLAY_STATE_LABELS_ZH,
    display_state_label_zh,
    status_label_zh,
)

# Every page hook that S1-S5 already mounts in the shared shell.
MOUNTED_VIEWS: dict[str, str] = {
    "atlas": "atlas-view",
    "stories": "research-story-view",
    "strategies": "strategy-genome-view",
    "strategy-conditions": "strategy-genome-conditions-view",
    "strategy-genome-comparison": "strategy-genome-comparison-view",
    "memory": "memory-view",
    "memory-failures": "failure-patterns-view",
    "failure-patterns": "failure-patterns-view",
    "evidence": "evidence-view",
    "lineage": "lineage-view",
    "evidence-object-comparison": "evidence-comparison-view",
    "derived-failure-grouping": "failure-grouping-view",
    "methodology": "methodology-view",
    "history": "history-view",
    "source-documents": "source-documents-view",
}

UNUSABLE = (
    FixtureState.BLOCKED,
    FixtureState.STALE,
    FixtureState.INCOMPARABLE,
    FixtureState.INTEGRITY_FAILURE,
    FixtureState.API_UNAVAILABLE,
)

MUTATING_VERBS = ("POST", "PUT", "PATCH", "DELETE")
TRANSLATOR = Translator()
EN_TRANSLATOR = Translator(Locale.EN)


def _url(view: str, fixture: str = "complete", **extra: str) -> str:
    return "/?" + urlencode({"view": view, "fixture": fixture, **extra})


def _main(document: str) -> str:
    return document.split('<main id="main-content"', 1)[1].split("</main>", 1)[0]


class _Audit(HTMLParser):
    """Collects the structural facts needed for the shared accessibility audit."""

    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.references: list[tuple[str, str]] = []
        self.h1_count = 0
        self.forms: list[dict[str, str | None]] = []
        self.buttons: list[tuple[dict[str, str | None], str]] = []
        self.links: list[tuple[dict[str, str | None], str]] = []
        self.inputs: list[dict[str, str | None]] = []
        self.labels_for: set[str] = set()
        self.tables_without_headers = 0
        self.html_lang: str | None = None
        self._table_stack: list[bool] = []
        self._label_depth = 0
        self._capture: list[tuple[str, dict[str, str | None], list[str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "html":
            self.html_lang = values.get("lang")
        if element_id := values.get("id"):
            self.ids.append(element_id)
        for key in ("aria-labelledby", "aria-controls", "aria-describedby"):
            if values.get(key):
                for token in (values[key] or "").split():
                    self.references.append((key, token))
        if tag == "h1":
            self.h1_count += 1
        elif tag == "form":
            self.forms.append(values)
        elif tag == "input":
            # An input is named by a wrapping <label>, a <label for>, or aria-label.
            self.inputs.append({**values, "labelled-by-wrapper": str(self._label_depth > 0)})
        elif tag == "label":
            self._label_depth += 1
            if values.get("for"):
                self.labels_for.add(values["for"] or "")
        elif tag == "table":
            self._table_stack.append(False)
        elif tag == "th" and self._table_stack:
            self._table_stack[-1] = True
        if tag in {"a", "button"}:
            self._capture.append((tag, values, []))

    def handle_endtag(self, tag: str) -> None:
        if tag == "label" and self._label_depth:
            self._label_depth -= 1
        if tag == "table" and self._table_stack and not self._table_stack.pop():
            self.tables_without_headers += 1
        if tag in {"a", "button"} and self._capture:
            kind, values, text = self._capture.pop()
            target = self.links if kind == "a" else self.buttons
            target.append((values, "".join(text).strip()))

    def handle_data(self, data: str) -> None:
        for _, _, text in self._capture:
            text.append(data)


def _audit(document: str) -> _Audit:
    parser = _Audit()
    parser.feed(document)
    parser.close()
    return parser


def _accessible_name(values: dict[str, str | None], text: str) -> str:
    return (values.get("aria-label") or text).strip()


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


# --- common states -----------------------------------------------------------------


def test_every_status_and_display_state_has_a_stable_chinese_label() -> None:
    for status in ReadModelStatus:
        label = status_label_zh(status)
        rendered = render_status_block(
            status, translator=TRANSLATOR, reason=f"reason-{status.value}"
        )
        assert label.strip()
        assert f'<span class="status-label">{label}</span>' in rendered
        assert 'data-status-label-zh=' not in rendered
        assert 'status-label-zh' not in rendered
    assert len({status_label_zh(status) for status in ReadModelStatus}) == len(ReadModelStatus)
    for state in DisplayState:
        label = display_state_label_zh(state)
        rendered = render_operational_state(state, translator=TRANSLATOR)
        assert label == DISPLAY_STATE_LABELS_ZH[state]
        assert f'<span class="status-label">{label}</span>' in rendered
        assert 'data-display-state-label-zh=' not in rendered


def test_common_state_dispatches_loading_status_and_envelope_without_a_second_taxonomy() -> None:
    loading = render_common_state(
        DisplayState.LOADING, translator=TRANSLATOR, reason="Reading the approved source"
    )
    assert 'data-display-state="loading"' in loading
    assert 'aria-live="polite"' in loading
    assert "加载中" in loading
    assert render_common_state(
        "loading", translator=TRANSLATOR
    ) == render_common_state(DisplayState.LOADING, translator=TRANSLATOR)
    blocked = render_common_state(
        ReadModelStatus.BLOCKED, translator=TRANSLATOR, reason="Policy gate"
    )
    assert 'data-status="blocked"' in blocked
    assert 'data-display-state="error"' in blocked
    model = fixture_provider(FixtureState.STALE).read("atlas")
    assert render_common_state(model, translator=TRANSLATOR) == render_status_block(
        model, translator=TRANSLATOR
    )
    with pytest.raises(ValueError, match="not a valid"):
        render_common_state("not-a-state", translator=TRANSLATOR)


@pytest.mark.parametrize("view", sorted(MOUNTED_VIEWS))
@pytest.mark.parametrize("fixture", list(FixtureState))
def test_status_vocabulary_is_identical_on_every_mounted_page(
    view: str, fixture: FixtureState
) -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    url = _url(view, fixture.value, scope="A0")
    document = app.render(url)
    model = app.read_model(app.request_state(url))
    main = _main(document)

    assert MOUNTED_VIEWS[view] in main
    status = model.availability.status.value
    expected_display = display_state_for(model).value
    assert (
        f'data-status="{status}" data-display-state="{expected_display}"'
    ) in main
    assert 'lang="zh-CN"' in document
    if fixture in UNUSABLE:
        # A source that could not be determined must never be relabeled as an empty scope.
        assert 'data-display-state="empty"' not in main
        assert 'data-display-state="error"' in main


def test_comparison_incomparable_outcome_surfaces_the_shared_incomparable_state() -> None:
    document = ManagerGUIApp().render(_url("strategy-genome-comparison", "incomparable"))

    assert 'data-comparison-result="incomparable"' in document
    assert 'data-status="incomparable"' in document
    assert 'data-status="derived"' in document
    assert "不可比较" in document


def test_methodology_blocked_scope_is_an_error_not_an_empty_scope() -> None:
    document = _main(ManagerGUIApp().render(_url("methodology", "blocked") + "&lang=en"))

    assert 'data-display-state="empty"' not in document
    assert "not a recorded empty scope" in document
    complete = _main(ManagerGUIApp().render(_url("methodology", "empty") + "&lang=en"))
    assert "No methodology methods are recorded in this scope." in complete


# --- accessibility and keyboard paths -----------------------------------------------


@pytest.mark.parametrize("view", sorted(MOUNTED_VIEWS))
def test_mounted_pages_pass_the_shared_accessibility_audit(view: str) -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    for fixture in (FixtureState.COMPLETE, FixtureState.PARTIAL, FixtureState.BLOCKED):
        url = _url(view, fixture.value, panel="events")
        document = app.render(url)
        english = app.render(url + "&lang=en")
        assert_shared_shell_i18n(document, english, route=view, source_url=url)
        audit = _audit(document)

        # Both default Chinese and explicit English run the shared harness above.
        assert audit.html_lang == "zh-CN"
        assert audit.h1_count == 1
        assert len(audit.ids) == len(set(audit.ids)), "duplicate id attributes"
        for key, token in audit.references:
            assert token in audit.ids, f"{key} references a missing id: {token}"
        for values, text in audit.links:
            assert _accessible_name(values, text), f"link without a name: {values}"
        for values, text in audit.buttons:
            assert _accessible_name(values, text), f"button without a name: {values}"
            # Submit is legitimate only for the GET filter forms asserted below.
            assert values.get("type") in {"button", "submit"}
        for values in audit.inputs:
            if values.get("type") == "hidden":
                continue
            named = (
                values.get("labelled-by-wrapper") == "True"
                or values.get("id") in audit.labels_for
                or bool(values.get("aria-label"))
            )
            assert named, f"unlabelled input: {values}"
        assert audit.tables_without_headers == 0
        for values in audit.forms:
            assert (values.get("method") or "get").lower() == "get"


def test_shell_exposes_chinese_labels_and_keyboard_landmarks() -> None:
    document = ManagerGUIApp().render(_url("atlas", panel="events"))
    audit = _audit(document)

    assert 'href="#main-content"' in document
    assert 'id="main-content" class="main-column" tabindex="-1"' in document
    assert "跳到工作区" in document
    assert "只读" in document
    assert "全局搜索" in document
    assert 'aria-label="管理界面分区"' in document
    current = [values for values, _ in audit.links if values.get("aria-current") == "page"]
    assert len(current) == 1
    for item in NAVIGATION:
        assert f'aria-label="{navigation_label_zh(item.view_id)}"' in document
    assert len({navigation_label_zh(item.view_id) for item in NAVIGATION}) == len(NAVIGATION)
    # panel buttons are linked to the panels they control and report their state
    assert 'aria-controls="event-drawer" aria-expanded="true"' in document
    assert 'aria-controls="inspector" aria-expanded="false"' in document
    default = ManagerGUIApp().render(_url("atlas"))
    assert 'aria-controls="inspector" aria-expanded="true"' in default
    assert 'aria-controls="event-drawer" aria-expanded="false"' in default


def test_keyboard_script_contract_covers_navigation_escape_focus_return_and_no_trap() -> None:
    for key in ("ArrowRight", "ArrowLeft", "ArrowDown", "ArrowUp", "Home", "End", "Escape"):
        assert f'"{key}"' in JS
    assert "lastTrigger" in JS  # focus returns to the opener when a panel closes
    assert "aria-expanded" in JS
    assert "aria-pressed" in JS
    assert "navigator.clipboard" in JS and "execCommand" in JS  # copy has a safe fallback
    assert 'event.key === "Tab"' not in JS  # a non-modal drawer must not trap focus
    assert "new Blob" in JS  # export is a local download, never a network mutation
    assert "fetch(" not in JS
    assert 'method: "POST"' not in JS


# --- export ------------------------------------------------------------------------


def test_export_payload_is_the_unchanged_envelope_plus_reproducible_context() -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    url = _url(
        "memory",
        panel="events",
        q="data gate",
        snapshot_token="requested-snap",
        opaque_ref="a&b=c/é",
        presentation="graph",
    )
    payload = json.loads(app.render_export(url))

    assert payload["schema"] == EXPORT_SCHEMA
    assert payload["read_only"] is True
    assert payload["view"] == "memory"
    assert payload["requested_snapshot_token"] == "requested-snap"
    assert payload["snapshot_token"] == json.loads(app.render_json(url))["snapshot_token"]
    assert payload["read_model"] == json.loads(app.render_json(url))
    assert dict(parse_qsl(payload["query"])) == payload["query_params"]
    assert payload["query_params"]["opaque_ref"] == "a&b=c/é"
    assert payload["query_params"]["presentation"] == "graph"
    assert ManagerReadModel.from_dict(payload["read_model"]).to_dict() == payload["read_model"]


def test_export_filename_is_safe_and_stable() -> None:
    assert export_filename(view="atlas", snapshot_token="snap-1") == "manager-gui-atlas-snap-1.json"
    hostile = export_filename(view="../../etc/passwd", snapshot_token='a/b\\c:"*?<>|')
    assert "/" not in hostile and "\\" not in hostile and ".." not in hostile
    assert hostile.startswith("manager-gui-") and hostile.endswith(".json")
    assert export_filename() == "manager-gui-view.json"


def test_export_control_is_a_get_download_with_full_context_on_every_page() -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    for view in MOUNTED_VIEWS:
        url = _url(view, q="gate", snapshot_token="snap-9", opaque_ref="keep me", panel="events")
        document = app.render(url)
        assert 'data-export-control="current-view"' in document
        assert "导出当前视图" in document
        marker = 'data-export-url="'
        endpoint = unescape(document.split(marker, 1)[1].split('"', 1)[0])
        parts = urlsplit(endpoint)
        assert parts.path == "/api/export"
        query = dict(parse_qsl(parts.query))
        assert query["view"] == view
        assert query["snapshot_token"] == "snap-9"
        assert query["opaque_ref"] == "keep me"
        assert query["q"] == "gate"
    assert export_url(None) == "/api/export"
    assert 'data-export-filename="manager-gui-atlas-snap.json"' in render_export_control(
        "/?view=atlas", translator=TRANSLATOR, view="atlas", snapshot_token="snap"
    )


def test_export_reads_once_writes_nothing_and_touches_no_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, str | None]] = []

    class CountingProvider:
        def read(self, resource: str = "atlas", *, snapshot_token: str | None = None):
            calls.append((resource, snapshot_token))
            return fixture_provider("complete").read(resource, snapshot_token=snapshot_token)

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("the read-only export must not open a file")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(builtins, "open", refuse)
    provider = CountingProvider()
    app = ManagerGUIApp(provider)

    document = app.render(_url("atlas", snapshot_token="snap-x"))
    payload_values = [
        values for values, _ in _audit(document).buttons if "data-export-payload" in values
    ]
    assert len(payload_values) == 1
    payload = json.loads(payload_values[0]["data-export-payload"] or "")

    assert payload["requested_snapshot_token"] == "snap-x"
    assert calls == [("atlas", "snap-x")]
    assert list(tmp_path.iterdir()) == []
    assert public_provider_methods(provider) == ("read",)
    assert FORBIDDEN_PROVIDER_METHODS.isdisjoint(public_provider_methods(provider))
    app_methods = {name for name in dir(app) if not name.startswith("_")}
    assert FORBIDDEN_PROVIDER_METHODS.isdisjoint(app_methods)


def test_current_view_export_helper_is_pure() -> None:
    model = fixture_provider(FixtureState.STALE).read("atlas")
    first = current_view_export(model, view="atlas", query_context="/?view=atlas&fixture=stale")
    second = current_view_export(model, view="atlas", query_context="/?view=atlas&fixture=stale")

    assert first == second
    assert first["read_model"]["availability"]["status"] == "stale"  # type: ignore[index]
    assert first["snapshot_token"] == model.snapshot_token


def test_served_export_is_get_only_and_every_mutation_verb_is_rejected(served_app: str) -> None:
    with urlopen(f"{served_app}/api/export?view=atlas&fixture=partial&snapshot_token=s1") as reply:
        payload = json.loads(reply.read())
        assert reply.status == 200
        assert reply.headers["Cache-Control"] == "no-store"
        assert payload["schema"] == EXPORT_SCHEMA
        assert payload["requested_snapshot_token"] == "s1"
    with urlopen(Request(f"{served_app}/api/export?view=atlas", method="HEAD")) as reply:
        assert reply.status == 200

    for path in ("/", "/api/export", "/api/read-model", "/api/publish", "/api/retry", "/health"):
        for verb in MUTATING_VERBS:
            with pytest.raises(HTTPError) as caught:
                urlopen(Request(f"{served_app}{path}", method=verb, data=b"{}"))
            assert caught.value.code == 405, (verb, path)
            assert caught.value.headers["Allow"] == "GET, HEAD"
    for path in ("/api/publish", "/api/retry", "/export", "/api/ledger"):
        with pytest.raises(HTTPError) as caught:
            urlopen(f"{served_app}{path}")
        assert caught.value.code == 404


# --- stable URL, snapshot and copy --------------------------------------------------


def test_url_state_round_trips_hostile_opaque_values_through_every_shared_surface() -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    token = 'snap & token="1"<x>'
    ref = "ref=1&view=search é"
    url = _url("atlas", q="a b", snapshot_token=token, opaque_ref=ref, panel="inspector")
    state = app.request_state(url)

    assert dict(state.context)["snapshot_token"] == token
    assert dict(parse_qsl(urlsplit(state.url()).query))["opaque_ref"] == ref
    document = app.render(url)
    assert "<x>" not in document.replace("&lt;x&gt;", "")
    escaped_token = token.replace("&", "&amp;").replace(chr(34), "&quot;")
    escaped_token = escaped_token.replace("<", "&lt;").replace(">", "&gt;")
    assert f'value="{escaped_token}"' in document
    for link in _audit(document).links:
        href = link[0].get("href") or ""
        if href.startswith("/?"):
            query = dict(parse_qsl(urlsplit(unescape(href)).query))
            assert query["snapshot_token"] == token
            assert query["opaque_ref"] == ref


def test_copy_buttons_carry_escaped_opaque_values_and_never_link_to_them() -> None:
    document = ManagerGUIApp().render(_url("atlas"))
    audit = _audit(document)
    copy = [values for values, _ in audit.buttons if "data-copy-value" in values]
    model = ManagerGUIApp(default_fixture=FixtureState.COMPLETE).read_model(
        ManagerGUIApp().request_state(_url("atlas"))
    )

    expected = {model.snapshot_token, *(source.source_id for source in model.source_refs)}
    assert {values["data-copy-value"] for values in copy} == expected
    for values in copy:
        assert values["type"] == "button"
        assert "复制引用" in (values.get("aria-label") or "")
    assert 'id="copy-status"' in document and 'role="status"' in document

    hostile = opaque_copy_button('"><script>alert(1)</script>', translator=TRANSLATOR)
    assert "<script>" not in hostile
    assert "&quot;&gt;&lt;script&gt;" in hostile
    assert opaque_copy_button(None, translator=TRANSLATOR) == ""
    assert opaque_copy_button("", translator=TRANSLATOR) == ""
    empty = _audit(ManagerGUIApp().render(_url("atlas", "empty")))
    assert not [values for values, _ in empty.buttons if "data-copy-value" in values]


# --- graph/table alternative -------------------------------------------------------


def test_alternative_view_keeps_a_visible_table_and_a_reachable_graph() -> None:
    table = "<table><tr><th scope='col'>A</th></tr><tr><td>1</td></tr></table>"
    default = render_alternative_view(
        translator=EN_TRANSLATOR,
        target="t",
        graph_markup="<ol><li>g</li></ol>",
        table_markup=table,
    )

    assert 'data-view-mode="table"' in default
    assert 'aria-pressed="true">Table' in default
    assert 'aria-pressed="false">Graph' in default
    graph_marker = (
        'data-view-panel="graph" data-view-for="t" '
        'aria-label="Lineage view" hidden'
    )
    assert graph_marker in default
    assert 'data-view-panel="table"' in default
    assert "hidden>" not in default.split('data-view-panel="table"', 1)[1][:80]
    graph = render_alternative_view(
        translator=EN_TRANSLATOR,
        target="t",
        graph_markup="<ol><li>g</li></ol>",
        table_markup=table,
        selected="graph",
    )
    assert 'aria-pressed="true">Graph' in graph
    assert render_alternative_view(
        translator=EN_TRANSLATOR,
        target="t",
        graph_markup="g",
        table_markup=table,
        selected="bogus",
    ) == default.replace("<ol><li>g</li></ol>", "g")


def test_failure_lineage_pages_offer_a_table_alternative_with_all_six_dimensions() -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    for view, params in (
        ("memory-failures", {"failure_id": "memory-fixture-1"}),
        ("failure-patterns", {"pattern_id": "pattern-fixture-1"}),
    ):
        document = app.render(_url(view, **params))
        assert 'data-alternative-view="failure-lineage"' in document
        assert "谱系视图" in document
        assert 'aria-label="Lineage graph / 谱系图"' in document
        for kind in ("campaign", "candidate", "run", "evidence", "artifact", "source_document"):
            assert f'data-graph-node-kind="{kind}"' in document
            assert f'data-association-kind="{kind}"' in document
        # the semantic table/definition-list view is the visible default
        table_panel = document.split('data-view-panel="table"', 1)[1].split(">", 1)[0]
        assert "hidden" not in table_panel
        graph_panel = document.split('data-view-panel="graph"', 1)[1].split(">", 1)[0]
        assert "hidden" in graph_panel


def test_presentation_choice_is_stable_opaque_url_state() -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    url = _url("memory-failures", failure_id="memory-fixture-1", presentation="graph")
    state = app.request_state(url)

    assert dict(state.context)["presentation"] == "graph"
    export = json.loads(app.render_export(url))
    assert export["query_params"]["presentation"] == "graph"
    assert "presentation=graph" in unescape(app.render(url))


# --- read-only audit and regression ------------------------------------------------


@pytest.mark.parametrize("view", sorted(MOUNTED_VIEWS))
def test_mounted_pages_expose_only_read_only_controls(view: str) -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    allowed = (
        "data-panel-target",
        "data-close-panels",
        "data-copy-value",
        "data-export-current-view",
        "data-view-mode",
    )
    for fixture in FixtureState:
        document = app.render(_url(view, fixture.value))
        audit = _audit(document)
        assert "只读" in document
        for values, text in audit.buttons:
            if values.get("type") == "submit":
                assert audit.forms, f"submit button outside a GET form: {text!r}"
                continue
            assert any(key in values for key in allowed), f"unexpected control: {text!r}"
        for values in audit.forms:
            assert (values.get("method") or "get").lower() == "get"
        assert 'method="post"' not in document.lower()
        assert "formaction" not in document.lower()


def test_s1_to_s6_routes_mount_through_the_shared_interaction_shell() -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    for view, hook in MOUNTED_VIEWS.items():
        assert f'data-integration-hook="{hook}"' in app.render(_url(view))
    assert "Integration point ready" not in app.render(_url("atlas"))

    search = app.render(_url("search", q="campaign"))
    assert 'data-integration-hook="search-view"' in search
    assert 'class="search-page"' in search
    assert "Integration point ready" not in search
    portal = app.render(_url("portal"))
    assert 'data-integration-hook="portal-view"' in portal
    assert 'class="portal-page"' in portal
    assert "Integration point ready" not in portal
    assert {item.view_id.value for item in NAVIGATION} >= {"search", "portal"}
    assert ViewId.SEARCH in {item.view_id for item in NAVIGATION}
    assert ViewId.PORTAL in {item.view_id for item in NAVIGATION}


def test_pagination_links_keep_context_and_have_chinese_labels() -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    document = app.render(
        _url(
            "history",
            scope="CPA",
            page_size="1",
            snapshot_token="page-snap",
            opaque_ref="keep",
        )
    )
    audit = _audit(document)
    links = [values for values, _ in audit.links if values.get("rel") in {"prev", "next"}]

    assert links, "expected a next-page link for a one-item page"
    for values in links:
        query = dict(parse_qsl(urlsplit(unescape(values["href"] or "")).query))
        assert query["snapshot_token"] == "page-snap"
        assert query["opaque_ref"] == "keep"
        assert "页" in (values.get("aria-label") or "")
    assert "上一页" in document or "下一页" in document


def test_status_localization_uses_source_text_for_owner_reason() -> None:
    english = render_status_block(
        ReadModelStatus.BLOCKED,
        translator=EN_TRANSLATOR,
        reason='owner <reason> "verbatim"',
    )
    assert '<span class="status-label">Blocked</span>' in english
    assert "Source note" in english
    assert "owner &lt;reason&gt; &quot;verbatim&quot;" in english
    assert 'lang="zh-CN"' not in english
    chinese = render_status_block(
        ReadModelStatus.BLOCKED, translator=TRANSLATOR, reason="属主说明"
    )
    assert '<span class="status-label">已阻塞</span>' in chinese
    assert "已阻塞" in chinese and "已阻塞" not in english


def test_static_client_script_has_explicit_locale_message_injection_hook() -> None:
    messages = js_messages(EN_TRANSLATOR)
    assert set(messages) == {
        "copy_success",
        "copy_unavailable",
        "export_success",
        "export_unavailable",
    }
    rendered = render_js(translator=EN_TRANSLATOR)
    assert "__MANAGER_GUI_MESSAGES__" not in rendered
    assert '"copy_success":"Copied opaque reference"' in rendered
    assert "Copied opaque reference / 已复制不透明引用" not in JS


def test_client_messages_are_in_safe_json_separate_from_static_executable_js() -> None:
    from manager_gui.testing.i18n import parse_html
    from manager_gui.web.assets import JS_MESSAGE_KEYS

    owner = '</script><script>unsafe()</script>&' + chr(0x2028) + chr(0x2029)
    messages = {key: owner for key in JS_MESSAGE_KEYS}
    markup = render_js(messages)
    scripts = parse_html(markup).select("script")
    assert len(scripts) == 2
    assert scripts[0].attrs == {"type": "application/json", "id": "gui-messages"}
    payload = "".join(child for child in scripts[0].children if isinstance(child, str))
    assert json.loads(payload) == messages
    assert "<" not in payload and "&" not in payload
    assert chr(0x2028) not in payload and chr(0x2029) not in payload
    assert "".join(child for child in scripts[1].children if isinstance(child, str)) == JS
    for locale in Locale:
        document = ManagerGUIApp().render(f"/?lang={locale.value}")
        actual = parse_html(document).select("script")
        assert actual[0].attrs["id"] == "gui-messages"
        data = "".join(child for child in actual[0].children if isinstance(child, str))
        assert json.loads(data) == js_messages(Translator(locale))
        assert tuple(json.loads(data)) == JS_MESSAGE_KEYS
        assert "".join(child for child in actual[1].children if isinstance(child, str)) == JS


def test_lineage_truncation_uses_cjk_display_width() -> None:
    assert _truncate("中文中文abc", 7) == "中文中…"
    assert _truncate("中文a", 4) == "中…"
    assert _truncate("short", 26) == "short"
