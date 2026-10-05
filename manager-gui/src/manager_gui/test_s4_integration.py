"""S4-T4 integration tests: Evidence, Lineage, comparison and grouping in the shared shell."""

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Iterator
from dataclasses import replace
from html import unescape
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode, urlsplit
from urllib.request import Request, urlopen

import pytest

from manager_gui import (
    FORBIDDEN_PROVIDER_METHODS,
    FixtureState,
    ManagerReadModel,
    fixture_provider,
    public_provider_methods,
)
from manager_gui.__main__ import main as cli_main
from manager_gui.web import ManagerGUIApp, create_server
from manager_gui.web.evidence import build_evidence_fixture
from manager_gui.web.evidence_comparison import build_evidence_comparison_fixture
from manager_gui.web.evidence_trace import MAX_TRACE_ROWS, render_evidence_trace
from manager_gui.web.failure_grouping import build_failure_grouping_fixture
from manager_gui.web.lineage import LINEAGE_RESOURCE, build_lineage_fixture
from manager_gui.web.navigation import NAVIGATION, ViewId
from manager_gui.web.s4_fixtures import (
    LINEAGE_CONCLUSION_ID,
    S4_FIXTURE_STATES,
    S4_RESOURCES,
    build_s4_fixture,
)

S4_ROUTES: dict[str, tuple[str, str]] = {
    # view id -> (integration hook, provider resource)
    "evidence": ("evidence-view", "evidence"),
    "lineage": ("lineage-view", "lineage"),
    "evidence-object-comparison": ("evidence-comparison-view", "evidence_comparison"),
    "derived-failure-grouping": ("failure-grouping-view", "failure_grouping"),
}

# Every page hook that S1-S3 and S5 already mounted before S4-T4.
PREVIOUS_ROUTES: dict[str, str] = {
    "atlas": "atlas-view",
    "stories": "research-story-view",
    "strategies": "strategy-genome-view",
    "strategy-conditions": "strategy-genome-conditions-view",
    "strategy-genome-comparison": "strategy-genome-comparison-view",
    "memory": "memory-view",
    "memory-failures": "failure-patterns-view",
    "failure-patterns": "failure-patterns-view",
    "methodology": "methodology-view",
    "history": "history-view",
    "source-documents": "source-documents-view",
}

MUTATING_VERBS = ("POST", "PUT", "PATCH", "DELETE")


def _url(view: str, fixture: str = "complete", **extra: str) -> str:
    return "/?" + urlencode({"view": view, "fixture": fixture, **extra})


def _main(document: str) -> str:
    return document.split('<main id="main-content"', 1)[1].split("</main>", 1)[0]


def _render(view: str, fixture: str = "complete", **extra: str) -> str:
    return ManagerGUIApp(default_fixture=FixtureState.COMPLETE).render(_url(view, fixture, **extra))


def _hrefs(markup: str, css_class: str) -> list[str]:
    pattern = rf'class="{css_class}"[^>]*href="([^"]+)"'
    return [unescape(href) for href in re.findall(pattern, markup)]


def _trace(document: str) -> str:
    """The trace section, up to the shell's panel actions that always follow the page."""

    start = document.split('data-evidence-trace="evidence-trace"', 1)[1]
    return start.split('<div class="panel-actions"', 1)[0]


class _FixedProvider:
    """Returns one prepared envelope for every read."""

    def __init__(self, model: ManagerReadModel) -> None:
        self._model = model

    def read(self, resource: str = "atlas", *, snapshot_token: str | None = None):
        del resource, snapshot_token
        return self._model


class _CountingProvider:
    """Serves S4 fixtures by resource and records every read."""

    def __init__(self, state: str = "complete") -> None:
        self.state = state
        self.calls: list[tuple[str, str | None]] = []

    def read(self, resource: str = "atlas", *, snapshot_token: str | None = None):
        self.calls.append((resource, snapshot_token))
        if resource in S4_RESOURCES:
            return build_s4_fixture(resource, self.state)
        return fixture_provider(self.state).read(resource, snapshot_token=snapshot_token)


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


# --- routes, navigation and shell chrome -----------------------------------------------


@pytest.mark.parametrize("view", sorted(S4_ROUTES))
def test_each_s4_route_mounts_its_hook_inside_the_shared_shell(view: str) -> None:
    hook, _ = S4_ROUTES[view]
    document = _render(view, panel="events", q="gate")

    assert f'data-integration-hook="{hook}"' in _main(document)
    assert "Integration point ready" not in document
    assert 'class="read-only-badge"' in document
    assert 'id="inspector"' in document and 'id="event-drawer"' in document
    assert 'class="raw-json"' in document
    current = re.findall(r'<a [^>]*aria-current="page"[^>]*>', document)
    assert len(current) == 1 and f"view={view}" in unescape(current[0])
    # the shared top bar keeps the global search and the typed query
    assert 'name="q" value="gate"' in document
    assert "manager-read-model.v0" in document


def test_navigation_adds_the_s4_items_without_reordering_existing_ones() -> None:
    order = [item.view_id.value for item in NAVIGATION]
    previous = [
        "atlas",
        "stories",
        "strategies",
        "strategy-conditions",
        "strategy-genome-comparison",
        "memory",
        "memory-failures",
        "failure-patterns",
        "evidence",
        "methodology",
        "history",
        "source-documents",
        "search",
    ]

    assert [view for view in order if view in previous] == previous
    for view in S4_ROUTES:
        assert order.count(view) == 1
    # S6-T4 appends Search and Portal without reordering S1-S5/S4 items.
    assert order[-2:] == ["search", "portal"]


def test_s4_general_comparison_is_separate_from_the_s2_genome_comparison() -> None:
    s4 = _render("evidence-object-comparison")
    s2 = _render("strategy-genome-comparison")

    assert 'data-integration-hook="evidence-comparison-view"' in s4
    assert 'data-integration-hook="strategy-genome-comparison-view"' not in s4
    assert "not the S2 Strategy Genome comparison" in s4
    assert 'data-integration-hook="strategy-genome-comparison-view"' in s2
    assert 'data-integration-hook="evidence-comparison-view"' not in s2
    assert ViewId.EVIDENCE_COMPARISON.value != ViewId.COMPARISON.value
    # the two routes read different resources
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    s4_model = app.read_model(app.request_state(_url("evidence-object-comparison")))
    s2_model = app.read_model(app.request_state(_url("strategy-genome-comparison")))
    assert s4_model.snapshot_token != s2_model.snapshot_token


def test_s4_pages_never_ship_a_mutation_control() -> None:
    for view in S4_ROUTES:
        for fixture in FixtureState:
            document = _render(view, fixture.value)
            assert 'method="post"' not in document.lower()
            assert "formaction" not in document.lower()
            for forbidden in ("retry", "revalidate", "publish", "promote"):
                assert not re.search(rf"<button[^>]*>[^<]*{forbidden}", document, re.IGNORECASE)


# --- integrated fixture matrix -----------------------------------------------------------


def test_every_shell_fixture_state_is_defined_for_every_s4_resource() -> None:
    for resource in S4_RESOURCES:
        for state in FixtureState:
            model = build_s4_fixture(resource, state)
            assert isinstance(model, ManagerReadModel)
            assert ManagerReadModel.from_json(model.to_json()) == model
    with pytest.raises(ValueError, match="not an S4 resource"):
        build_s4_fixture("atlas", "complete")
    assert set(S4_FIXTURE_STATES) == {
        FixtureState.NOT_EVALUATED,
        FixtureState.CURSOR_EXPIRED,
        FixtureState.SNAPSHOT_DRIFT,
    }


def test_complete_fixture_publishes_all_four_s4_routes() -> None:
    evidence = _render("evidence")
    lineage = _render("lineage")
    comparison = _render("evidence-object-comparison")
    grouping = _render("derived-failure-grouping")

    assert 'data-status="known"' in evidence
    assert 'data-evidence-group="candidate"' in evidence
    assert 'data-evidence-group="protocol_conforming"' in evidence
    assert 'data-lineage-state="ready"' in lineage
    assert 'data-graph="withheld"' not in lineage
    assert 'data-status="derived"' in comparison
    assert 'data-comparison-result="equal"' in comparison
    assert 'data-status="derived"' in grouping
    assert 'data-group-outcome="success"' in grouping
    assert 'data-group-outcome="failure"' in grouping


def test_empty_fixture_is_a_recorded_absence_not_a_failure() -> None:
    for view in S4_ROUTES:
        main = _main(_render(view, "empty"))
        assert 'data-status="missing"' in main
        assert 'data-display-state="empty"' in main
        assert 'data-display-state="error"' not in main
    evidence = _render("evidence", "empty")
    assert "No Evidence Ledger records are published in this scope." in evidence
    assert 'data-evidence-status="fail"' not in evidence
    assert 'data-trace-missing="conclusion"' in evidence


def test_blocked_is_never_shown_as_a_failure_or_as_empty() -> None:
    evidence = _render("evidence", "blocked")
    assert 'data-status="blocked"' in evidence
    assert 'data-evidence-status="blocked"' in evidence
    assert 'data-evidence-status="fail"' not in evidence
    assert "The approved protocol source is blocked." in evidence

    lineage = _render("lineage", "blocked")
    assert 'data-lineage-failure="source_blocked"' in lineage
    assert "<svg" not in lineage and 'id="lineage-table"' not in lineage

    for view in ("evidence-object-comparison", "derived-failure-grouping"):
        main = _main(_render(view, "blocked"))
        assert 'data-status="blocked"' in main
        assert 'data-display-state="error"' in main
        assert 'data-display-state="empty"' not in main


def test_not_evaluated_stays_distinct_from_failure_on_every_route() -> None:
    evidence = _render("evidence", "not_evaluated")
    assert 'data-evidence-status="not_evaluated"' in evidence
    assert "Not evaluated" in evidence
    assert 'data-evidence-status="fail"' not in evidence

    lineage = _render("lineage", "not_evaluated", depth="6", lang="en")
    assert 'data-lineage-state="ready"' in lineage
    statuses = {
        node: status
        for node, status in re.findall(
            r'<tr data-node-id="([^"]+)" data-record-type="evidence"[^>]*>.*?</th><td>Evidence</td>'
            r"<td>([^<]*)</td>",
            lineage,
            re.DOTALL,
        )
    }
    assert statuses and set(statuses.values()) == {"Not evaluated"}
    node_statuses = re.findall(r"</th><td>[\w_]+</td><td>([^<]*)</td>", lineage)
    assert not {"fail", "failed", "failure"} & set(node_statuses)

    grouping = _render("derived-failure-grouping", "not_evaluated")
    groups = grouping.split('data-grouping-state="ready"', 1)[1].split("</section>", 1)[0]
    failure_group = groups.split('data-group-outcome="failure"', 1)[1].split("</article>", 1)[0]
    assert "run-failure-1" in failure_group
    assert "run-not-evaluated-1" not in groups  # joins neither bucket
    assert "run-success-1" in groups.split('data-group-outcome="failure"', 1)[0]
    # excluded from the groups, yet still visible as published data in the raw envelope
    assert "run-not-evaluated-1" in grouping.split('class="raw-json"', 1)[1]
    assert "joins neither group" in grouping

    comparison = _render("evidence-object-comparison", "not_evaluated")
    assert "has not been evaluated" in comparison
    assert 'data-comparison-result="different"' not in comparison
    assert 'data-display-state="error"' not in _main(comparison)


def test_stale_is_labelled_stale_and_never_current() -> None:
    evidence = _render("evidence", "stale")
    assert 'data-status="stale"' in evidence
    assert "The Evidence Ledger source is stale." in evidence

    lineage = _render("lineage", "stale")
    assert 'data-status="stale"' in lineage
    assert 'data-lineage-state="ready"' in lineage  # retained for history, not withheld

    for view in ("evidence-object-comparison", "derived-failure-grouping"):
        main = _main(_render(view, "stale"))
        assert 'data-status="stale"' in main
        assert 'data-display-state="error"' in main
        assert 'data-display-state="empty"' not in main
    assert 'data-group-outcome="success"' not in _render("derived-failure-grouping", "stale")


def test_incomparable_keeps_the_per_axis_reason_and_is_never_ranked() -> None:
    comparison = _render("evidence-object-comparison", "incomparable")
    assert 'data-status="incomparable"' in comparison
    assert 'data-comparison-result="incomparable"' in comparison
    assert re.search(r'data-axis="data_version" data-axis-state="incomparable"', comparison)
    assert 'data-statistics="not-generated"' in comparison
    assert "success rate" not in comparison.lower()

    evidence = _render("evidence", "incomparable")
    assert 'data-evidence-status="incomparable"' in evidence
    assert "Data snapshots are not comparable." in evidence

    lineage = _render("lineage", "incomparable")
    assert 'data-lineage-failure="incomparable"' in lineage
    assert "<svg" not in lineage


def test_integrity_failure_keeps_the_specific_artifact_reason() -> None:
    evidence = _render("evidence", "integrity_failure")
    assert 'data-status="integrity_failure"' in evidence
    assert 'data-verification-status="hash_mismatch"' in evidence
    assert "Declared hash does not match the observed bytes." in evidence

    lineage = _render("lineage", "integrity_failure")
    assert 'data-lineage-failure="integrity_failure"' in lineage
    assert "<svg" not in lineage and 'id="lineage-table"' not in lineage

    for view in ("evidence-object-comparison", "derived-failure-grouping"):
        main = _main(_render(view, "integrity_failure"))
        assert 'data-status="integrity_failure"' in main
        assert 'data-display-state="error"' in main


def test_api_unavailable_publishes_nothing_and_is_never_empty() -> None:
    evidence = _render("evidence", "api_unavailable")
    assert 'data-status="api_unavailable"' in evidence
    assert "The protocol result is inspectable." not in evidence  # no conclusion beside an outage
    assert 'data-trace-missing="conclusion"' in evidence

    lineage = _render("lineage", "api_unavailable")
    assert 'data-lineage-failure="source_unavailable"' in lineage

    for view in S4_ROUTES:
        assert 'data-display-state="empty"' not in _main(_render(view, "api_unavailable"))


def test_cursor_expired_and_snapshot_drift_fail_closed_and_offer_a_clean_restart() -> None:
    for fixture in ("cursor_expired", "snapshot_drift"):
        code = fixture  # the failure code is named after the fixture state
        lineage = _render("lineage", fixture, snapshot_token="old", cursor="cursor-1", page="3")
        assert f'data-lineage-failure="{code}"' in lineage
        assert 'data-graph="withheld"' in lineage and 'role="alert"' in lineage
        assert "<svg" not in lineage and "data-path-state=" not in lineage
        restart = [
            href
            for href in _hrefs(lineage, "lineage-restart")
            if "cursor=" not in href and "snapshot_token=" not in href and "page=" not in href
        ]
        assert restart, "a restart link without the stale cursor, pin and page must be offered"
        assert all(f"fixture={fixture}" in href for href in restart)

        for view in ("evidence", "evidence-object-comparison", "derived-failure-grouping"):
            main = _main(_render(view, fixture))
            assert 'data-status="stale"' in main
            assert code in main  # the real cause is kept in the raw envelope / errors


def test_partial_lineage_pagination_never_claims_absence_and_unserved_cursors_fail_closed() -> None:
    document = _render("lineage", "partial", lang="en")
    assert 'data-lineage-state="partial"' in document
    assert 'data-pagination-complete="false"' in document
    assert "not evidence of absence" in document
    assert 'data-lineage-next-cursor="cursor-2"' in document
    link = _hrefs(document, "lineage-next-cursor")[0]
    query = dict(parse_qsl(urlsplit(link).query))
    assert query["cursor"] == "cursor-2"
    assert query["snapshot_token"] == "lineage-partial-v0"  # pages are pinned, never merged
    assert query["fixture"] == "partial" and query["view"] == "lineage"

    # The fixture provider serves only the first page, so a cursor it never issued is refused.
    followed = ManagerGUIApp(default_fixture=FixtureState.COMPLETE).render(link)
    assert 'data-lineage-failure="cursor_mismatch"' in followed
    assert "<svg" not in followed


def test_evidence_local_pagination_keeps_every_shared_context_key() -> None:
    document = _render(
        "evidence", page_size="1", q="gate", panel="events", opaque="keep", snapshot_token="pin"
    )
    links = [
        unescape(match)
        for match in re.findall(r'rel="next"\s+href="([^"]+)"', document)
    ]
    assert links, "a one-record page must offer a next link"
    query = dict(parse_qsl(urlsplit(links[0]).query))
    assert query["view"] == "evidence" and query["page"] == "2"
    for key, value in (
        ("fixture", "complete"),
        ("q", "gate"),
        ("panel", "events"),
        ("opaque", "keep"),
        ("snapshot_token", "pin"),
        ("page_size", "1"),
    ):
        assert query[key] == value


# --- stable context and snapshot behavior -------------------------------------------------


def test_navigation_between_s4_routes_keeps_fixture_query_panel_and_opaque_context() -> None:
    document = _render("evidence", q="gate", panel="events", opaque="keep me", presentation="graph")
    nav = document.split('aria-label="管理界面分区', 1)[1].split("</nav>", 1)[0]
    for view in S4_ROUTES:
        match = re.search(rf'href="(/\?[^"]*view={re.escape(view)}(?:&|")[^"]*)"', nav)
        assert match is not None, view
        query = dict(parse_qsl(urlsplit(unescape(match.group(1))).query))
        assert query["fixture"] == "complete"
        assert query["q"] == "gate"
        assert query["panel"] == "events"
        assert query["opaque"] == "keep me"
        assert query["presentation"] == "graph"


def test_lineage_pinned_to_the_snapshot_it_read_renders_but_a_foreign_pin_fails_closed() -> None:
    pinned = _render("lineage", snapshot_token="lineage-complete-v0")
    assert 'data-lineage-state="ready"' in pinned

    foreign = _render("lineage", snapshot_token="evidence-complete-v0")
    assert 'data-lineage-failure="snapshot_drift"' in foreign
    assert "<svg" not in foreign  # snapshots are never mixed


def test_trace_links_cross_resources_without_forwarding_the_snapshot_pin() -> None:
    document = _render(
        "evidence", q="gate", panel="events", opaque="keep", snapshot_token="evidence-complete-v0"
    )
    trace = _trace(document)
    cross = _hrefs(trace, "trace-lineage-link")
    sibling = "(?:evidence-object-comparison|derived-failure-grouping)"
    related = [
        unescape(h) for h in re.findall(rf'href="([^"]*view={sibling}[^"]*)"', trace)
    ]
    assert cross and related
    for href in {*cross, *related}:
        query = dict(parse_qsl(urlsplit(href).query))
        assert "snapshot_token" not in query, "each resource owns its own snapshot"
        assert query["fixture"] == "complete"
        assert query["q"] == "gate" and query["panel"] == "events" and query["opaque"] == "keep"
        assert "page" not in query and "page_size" not in query and "cursor" not in query

    in_route = [unescape(h) for h in re.findall(r'class="trace-detail-link" href="([^"]+)"', trace)]
    assert in_route
    for href in in_route:
        query = dict(parse_qsl(urlsplit(href).query))
        assert query["view"] == "evidence"
        assert query["snapshot_token"] == "evidence-complete-v0"  # same resource: pin kept


def test_hostile_context_values_are_escaped_on_the_s4_routes() -> None:
    hostile = '"><script>alert(1)</script>'
    for view in S4_ROUTES:
        document = _render(
            view, q=hostile, record_id=hostile, artifact_id=hostile, source_id=hostile
        )
        assert "<script>alert(1)</script>" not in document
    evidence = _render("evidence", record_id=hostile, artifact_id=hostile, source_id=hostile)
    assert evidence.count('data-trace-found="false"') == 3
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in evidence


# --- end-to-end conclusion -> evidence -> source/artifact/lineage -------------------------


def test_conclusion_leads_to_evidence_sources_artifacts_and_lineage() -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    evidence = app.render(_url("evidence", q="gate", panel="events"))
    trace = _trace(evidence)

    assert re.findall(r'data-trace-step="(\w+)"', trace) == [
        "conclusion",
        "evidence",
        "source",
        "artifact",
    ]
    assert "The protocol result is inspectable." in trace
    assert "evidence level high" in trace

    # conclusion -> lineage rooted at the published conclusion id
    links = _hrefs(trace, "trace-lineage-link")
    root_link = next(href for href in links if f"record_id={LINEAGE_CONCLUSION_ID}" in href)
    lineage = app.render(root_link)
    assert 'data-integration-hook="lineage-view"' in lineage
    assert 'data-lineage-state="ready"' in lineage
    assert f'data-lineage-inspector="{LINEAGE_CONCLUSION_ID}"' in lineage
    assert 'data-path-state="found"' in lineage  # the shortest evidence path is reachable
    assert 'href="fixture://apex-research/lineage"' in lineage  # onward to the real source

    # evidence record and artifact each reach their own lineage root
    for lineage_id in ("evidence-1", "artifact-1"):
        link = next(href for href in links if f"record_id={lineage_id}" in href)
        page = app.render(link)
        assert f'data-lineage-inspector="{lineage_id}"' in page
        assert 'data-lineage-state="ready"' in page

    # sources and artifacts resolve to the published fixture locators
    assert 'href="fixture://apex-research/evidence-ledger"' in trace
    assert 'href="fixture://strategy-reporting/artifacts/evidence-report.json"' in trace
    assert 'data-verification-status="verified"' in trace


def test_unpublished_hops_stay_missing_and_are_not_guessed() -> None:
    trace = _trace(_render("evidence"))
    # the candidate record publishes no lineage id, so exactly that hop is missing
    candidate = trace.split('data-trace-record="candidate-evidence-1"', 1)[1].split("</li>", 1)[0]
    assert 'data-trace-missing="lineage"' in candidate
    assert "Missing / Unconfirmed" in candidate
    protocol = trace.split('data-trace-record="protocol-evidence-1"', 1)[1].split("</li>", 1)[0]
    assert 'data-trace-missing="lineage"' not in protocol

    # no ledger pointer at all: nothing is inferred from similar-looking ids
    bare = build_evidence_fixture("complete")
    data = json.loads(json.dumps(bare.data))
    bare_trace = render_evidence_trace(replace(bare, data=data), query_context="/?view=evidence")
    assert 'data-trace-missing="lineage"' in bare_trace
    assert "trace-lineage-link" not in bare_trace
    assert "Open lineage" not in bare_trace

    # a source without a public locator is Missing, not linked
    unresolved = replace(bare, source_refs=())
    text = render_evidence_trace(unresolved, query_context="/?view=evidence")
    assert 'data-trace-missing="source"' in text


def test_selected_detail_resolves_record_artifact_and_source() -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    found = app.render(
        _url(
            "evidence",
            record_id="protocol-evidence-1",
            artifact_id="artifact-report-1",
            source_id="evidence-fixture-source",
        )
    )
    assert found.count('data-trace-found="true"') == 3
    assert 'data-trace-detail="record"' in found
    assert "Protocol result" in found and "Protocol-conforming evidence" in found
    assert "sha256:" + "a" * 64 in found
    assert 'href="fixture://apex-research/evidence-ledger"' in found

    missing = app.render(
        _url("evidence", record_id="nope", artifact_id="nope", source_id="nope")
    )
    assert missing.count('data-trace-found="false"') == 3
    assert "not a failure and not proof that the record does not exist" in missing

    mismatch = ManagerGUIApp(default_fixture=FixtureState.COMPLETE).render(
        _url("evidence", "integrity_failure", artifact_id="artifact-report-1")
    )
    detail = mismatch.split('data-trace-detail="artifact"', 1)[1].split("</section>", 1)[0]
    assert "hash mismatch" in detail
    assert "Declared hash does not match the observed bytes." in detail


def test_the_ledgers_existing_context_links_now_reach_a_real_detail() -> None:
    # An unresolved source in the ledger links to ?source_id=...; that must not be a dead end.
    base = build_evidence_fixture("complete")
    unresolved = replace(
        base,
        source_refs=(),
        data={**json.loads(base.to_json())["data"], "sources": ["ghost-source"]},
    )
    class Provider:
        def read(self, resource: str = "atlas", *, snapshot_token: str | None = None):
            del resource, snapshot_token
            return unresolved

    app = ManagerGUIApp(Provider())
    page = app.render(_url("evidence"))
    ledger_links = [
        href
        for href in _hrefs(page, "evidence-source-context-link")
        if "source_id=ghost-source" in href
    ]
    assert ledger_links
    detail = app.render(ledger_links[0])
    assert 'data-trace-detail="source"' in detail and 'data-trace-found="true"' in detail
    assert "Missing / Unconfirmed" in detail


# --- private locators ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "locator", ["C:\\private\\ledger.json", "file:///etc/passwd", "https://user:pw@host.invalid/x"]
)
def test_private_locators_are_never_rendered_as_links_on_any_s4_route(locator: str) -> None:
    # Each page words an unlinked reference in its own owner-facing vocabulary.
    published = {
        "evidence": (build_evidence_fixture("complete"), "Missing / Unconfirmed"),
        "lineage": (build_lineage_fixture("complete"), "Missing / Unconfirmed"),
        "evidence-object-comparison": (
            build_evidence_comparison_fixture("complete"),
            "not recorded",
        ),
        "derived-failure-grouping": (
            build_failure_grouping_fixture("complete"),
            "not recorded",
        ),
    }
    for view, (model, unlinked) in published.items():
        swapped = replace(
            model, source_refs=tuple(replace(ref, locator=locator) for ref in model.source_refs)
        )
        document = ManagerGUIApp(_FixedProvider(swapped)).render(
            _url(view, lang="en") if view == "lineage" else _url(view)
        )
        for prefix in ('href="C:', 'href="file:', 'href="https://user:pw@'):
            assert prefix not in document, (view, prefix)
        assert unlinked in _main(document), view


# --- read-only boundary and single-read audit --------------------------------------------


@pytest.mark.parametrize("view", sorted(S4_ROUTES))
def test_each_s4_route_reads_exactly_its_resource_once_with_the_requested_snapshot(
    view: str,
) -> None:
    _, resource = S4_ROUTES[view]
    provider = _CountingProvider()
    app = ManagerGUIApp(provider)
    # evidence with selected detail and trace must still be one read
    app.render(_url(view, snapshot_token="pin", record_id="x", artifact_id="y", source_id="z"))

    assert provider.calls == [(resource, "pin")]
    assert public_provider_methods(provider) == ("read",)
    assert FORBIDDEN_PROVIDER_METHODS.isdisjoint(public_provider_methods(provider))
    app_methods = {name for name in dir(app) if not name.startswith("_")}
    assert FORBIDDEN_PROVIDER_METHODS.isdisjoint(app_methods)


def test_json_and_export_endpoints_share_the_single_read_envelope() -> None:
    for view, (_, resource) in S4_ROUTES.items():
        provider = _CountingProvider()
        app = ManagerGUIApp(provider)
        url = _url(view, snapshot_token="pin", q="gate", opaque="keep")
        payload = json.loads(app.render_export(url))
        envelope = json.loads(app.render_json(url))

        assert payload["view"] == view and payload["read_only"] is True
        assert payload["read_model"] == envelope
        assert payload["requested_snapshot_token"] == "pin"
        assert payload["query_params"]["opaque"] == "keep"
        assert provider.calls == [(resource, "pin"), (resource, "pin")]  # one read per call


def test_s4_rendering_is_deterministic_and_has_no_filesystem_side_effects(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import builtins

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("an S4 route must not open a file")

    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    first = {view: app.render(_url(view)) for view in S4_ROUTES}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(builtins, "open", refuse)
    second = {view: app.render(_url(view)) for view in S4_ROUTES}

    assert first == second
    assert list(tmp_path.iterdir()) == []


def test_large_lineage_graph_stays_bounded_inside_the_shell() -> None:
    model = build_lineage_fixture("large", size=500)

    class Provider:
        calls = 0

        def read(self, resource: str = "atlas", *, snapshot_token: str | None = None):
            del snapshot_token
            assert resource == LINEAGE_RESOURCE
            Provider.calls += 1
            return model

    started = time.perf_counter()
    document = ManagerGUIApp(Provider()).render("/?view=lineage&depth=6&page_size=50")
    elapsed = time.perf_counter() - started

    assert Provider.calls == 1
    assert len(re.findall(r'<g class="lineage-node" data-node-id="', document)) <= 50
    assert 'data-lineage-state="ready"' in document
    assert elapsed < 10, f"bounded 500-node lineage render took {elapsed:.2f}s"


def test_the_trace_is_bounded_for_a_large_ledger() -> None:
    base = build_evidence_fixture("complete")
    payload = json.loads(base.to_json())["data"]
    template = payload["records"][1]
    payload["records"] = [
        {**template, "record_id": f"record-{index}", "label": f"Record {index}", "artifacts": []}
        for index in range(MAX_TRACE_ROWS * 3)
    ]
    trace = render_evidence_trace(replace(base, data=payload), query_context="/?view=evidence")

    assert trace.count("data-trace-record=") == MAX_TRACE_ROWS
    assert f"Showing {MAX_TRACE_ROWS} of {MAX_TRACE_ROWS * 3} evidence records" in trace


# --- regression: S1-S3, S5 and S6 behavior is unchanged ----------------------------------


@pytest.mark.parametrize("view", sorted(PREVIOUS_ROUTES))
@pytest.mark.parametrize("fixture", list(FixtureState))
def test_previously_mounted_routes_still_mount_with_every_fixture_state(
    view: str, fixture: FixtureState
) -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    url = _url(view, fixture.value, scope="A0", panel="events", q="regression")
    document = app.render(url)
    model = app.read_model(app.request_state(url))

    assert f'data-integration-hook="{PREVIOUS_ROUTES[view]}"' in _main(document)
    assert f'data-status="{model.availability.status.value}"' in _main(document)
    assert 'class="read-only-badge"' in document
    assert 'id="inspector"' in document and 'id="event-drawer"' in document
    # S4 hooks never leak onto a route that does not own them
    for _, (hook, _) in S4_ROUTES.items():
        assert f'data-integration-hook="{hook}"' not in _main(document)


@pytest.mark.parametrize("fixture", sorted(state.value for state in S4_FIXTURE_STATES))
def test_s4_only_selector_values_give_other_routes_the_shared_generic_envelope(
    fixture: str,
) -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    generic = fixture_provider(fixture).read()
    for view in PREVIOUS_ROUTES:
        model = app.read_model(app.request_state(_url(view, fixture, scope="A0")))
        assert model.availability.status is generic.availability.status, view
        assert [error.code for error in model.errors] == [error.code for error in generic.errors]


def test_search_and_portal_mount_after_s6_t4_without_remapping_s4_resources() -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    search = app.render(_url("search"))
    assert 'data-integration-hook="search-view"' in search
    assert 'class="search-page"' in search
    assert "Integration point ready" not in search
    portal = app.render(_url("portal"))
    assert 'data-integration-hook="portal-view"' in portal
    assert 'class="portal-page"' in portal
    assert "portal" in {item.view_id.value for item in NAVIGATION}
    provider = _CountingProvider()
    ManagerGUIApp(provider).render(_url("search", q="x"))
    ManagerGUIApp(provider).render(_url("portal"))
    assert provider.calls == [("search", None), ("report_source", None)]


def test_s2_comparison_and_s3_failure_routes_keep_their_resources() -> None:
    provider = _CountingProvider()
    app = ManagerGUIApp(provider)
    app.render(_url("strategy-genome-comparison"))
    app.render(_url("failure-patterns"))
    app.render(_url("memory-failures"))
    app.render(_url("source-documents"))

    assert [resource for resource, _ in provider.calls] == [
        "genome_comparison",
        "failure_patterns",
        "memory",
        "source_documents",
    ]


# --- CLI and HTTP smoke -------------------------------------------------------------------


def test_cli_accepts_the_new_selector_values(capsys: pytest.CaptureFixture[str]) -> None:
    for fixture, status in (
        ("not_evaluated", "known"),
        ("cursor_expired", "stale"),
        ("snapshot_drift", "stale"),
    ):
        assert cli_main(["--fixture", fixture, "--resource", "lineage"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["availability"]["status"] == status


def test_served_s4_routes_json_export_and_mutations(served_app: str) -> None:
    for view, (hook, _) in S4_ROUTES.items():
        with urlopen(f"{served_app}/?view={view}&fixture=complete") as reply:
            assert reply.status == 200
            assert f'data-integration-hook="{hook}"' in reply.read().decode("utf-8")
        with urlopen(f"{served_app}/api/read-model?view={view}&fixture=complete") as reply:
            assert json.loads(reply.read())["schema"] == "manager-gui.manager-read-model.v0"
        export_url = f"{served_app}/api/export?view={view}&fixture=complete&snapshot_token=s"
        with urlopen(export_url) as reply:
            assert reply.headers["Cache-Control"] == "no-store"
            exported = json.loads(reply.read())
            assert exported["view"] == view and exported["read_only"] is True
        for verb in MUTATING_VERBS:
            with pytest.raises(HTTPError) as caught:
                urlopen(Request(f"{served_app}/?view={view}", method=verb, data=b"{}"))
            assert caught.value.code == 405
            assert caught.value.headers["Allow"] == "GET, HEAD"
    with urlopen(Request(f"{served_app}/?view=lineage&fixture=complete", method="HEAD")) as reply:
        assert reply.status == 200
