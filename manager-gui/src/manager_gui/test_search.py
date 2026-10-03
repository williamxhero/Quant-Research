"""Focused tests for the S6-T1 deterministic global Search read model."""

from __future__ import annotations

from typing import cast

from manager_gui import Availability, Derivation, ManagerReadModel, ReadModelStatus, SourceReference
from manager_gui.models import JSONValue
from manager_gui.provider import FORBIDDEN_PROVIDER_METHODS, public_provider_methods
from manager_gui.web.search import (
    SEARCH_FIELDS,
    SEARCH_FIXTURE_STATES,
    SEARCH_RESOURCE,
    SearchFixtureState,
    SearchState,
    SearchViewModel,
    build_search_fixture,
    render_search_view,
    search_fixture_provider,
)


def _source(source_id: str, *, owner: str = "test-owner") -> SourceReference:
    return SourceReference(
        source_id=source_id,
        owner=owner,
        kind="approved-index",
        locator=f"fixture://tests/search/{source_id}",
        schema="tests.search.v0",
        revision="r1",
    )


def _model(
    data: object, *, complete: bool = True, status: ReadModelStatus = ReadModelStatus.KNOWN
) -> ManagerReadModel:
    source = _source("search-source")
    return ManagerReadModel(
        data=cast(JSONValue, data),
        source_refs=(source,),
        as_of="2026-10-03T12:00:00Z",
        snapshot_token="search-test-v1",
        derivation=Derivation(kind="direct", inputs=(source.source_id,), version="v0"),
        availability=Availability(
            status=status,
            complete=complete,
            reason="test search read model",
        ),
    )


def _entry(record_id: str, **values: object) -> dict[str, object]:
    return {
        "record_id": record_id,
        "record_type": "record",
        "source_ref": "search-source",
        **values,
    }


def test_search_matches_every_approved_field_and_explains_source() -> None:
    entry = _entry(
        "record-1",
        schema="schema.v1",
        hash="sha256:record-1",
        revision="rev-7",
        campaign="campaign-1",
        strategy="strategy-1",
        run="run-1",
        family="family-1",
        status="completed",
        date="2026-10-03",
        title="A titled record",
        statement="A precise statement",
        safe_summary="A safe summary",
        document_title="A source document",
    )
    model = _model({"records": [entry], "pagination": {"complete": True, "has_more": False}})

    for field_name in SEARCH_FIELDS:
        value = entry.get(field_name)
        assert isinstance(value, str)
        view = SearchViewModel.from_read_model(model, query=value)
        assert len(view.hits) == 1
        assert field_name in view.hits[0].matched_fields
        assert view.hits[0].source_refs[0].source_id == "search-source"

    hit = SearchViewModel.from_read_model(model, query="precise").hits[0]
    assert "statement" in hit.matched_fields
    assert "statement" in hit.reason
    assert hit.source_locator == "fixture://tests/search/search-source"


def test_search_order_is_stable_and_matching_is_literal_not_semantic() -> None:
    first = _entry("b", title="Campaign B")
    second = _entry("a", title="Campaign A")
    model_a = _model({"records": [first, second], "pagination": {"complete": True}})
    model_b = _model({"records": [second, first], "pagination": {"complete": True}})

    assert [
        hit.record_id for hit in SearchViewModel.from_read_model(model_a, query="campaign").hits
    ] == [
        "a",
        "b",
    ]
    assert (
        SearchViewModel.from_read_model(model_b, query="campaign").hits
        == SearchViewModel.from_read_model(model_a, query="campaign").hits
    )
    assert SearchViewModel.from_read_model(model_a, query="unrelated concept").hits == ()


def test_search_supports_type_and_source_filters_without_extra_reads() -> None:
    document_source = _source("document-source", owner="document-index")
    model = ManagerReadModel(
        data=cast(
            JSONValue,
            {
                "records": [_entry("record-1", title="same term")],
                "documents": [
                    {
                        "document_id": "doc-1",
                        "document_type": "report",
                        "title": "same term document",
                        "source_ref": "document-source",
                    }
                ],
                "pagination": {"complete": True},
            },
        ),
        source_refs=(_source("search-source"), document_source),
        as_of="2026-10-03T12:00:00Z",
        snapshot_token="filter-snapshot",
        derivation=Derivation(kind="direct", version="v0"),
        availability=Availability(status=ReadModelStatus.KNOWN, complete=True),
    )

    documents = SearchViewModel.from_read_model(model, query="same", record_type="report")
    assert [hit.record_id for hit in documents.hits] == ["doc-1"]
    assert documents.hits[0].result_kind == "document"
    source_filtered = SearchViewModel.from_read_model(model, query="same", source="document-index")
    assert [hit.record_id for hit in source_filtered.hits] == ["doc-1"]

    class CountingProvider:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None]] = []

        def read(
            self, resource: str = "atlas", *, snapshot_token: str | None = None
        ) -> ManagerReadModel:
            self.calls.append((resource, snapshot_token))
            return model

    provider = CountingProvider()
    rendered = render_search_view(
        provider,
        query="same",
        record_type="report",
        source_filter="document-index",
        snapshot_token="filter-snapshot",
    )
    assert provider.calls == [(SEARCH_RESOURCE, "filter-snapshot")]
    assert 'data-integration-hook="search-view"' in rendered
    assert 'data-record-type="report"' in rendered
    assert public_provider_methods(provider) == ("read",)
    assert not FORBIDDEN_PROVIDER_METHODS.intersection(public_provider_methods(provider))


def test_partial_page_never_claims_global_no_match() -> None:
    model = _model(
        {
            "records": [_entry("record-1", title="known campaign")],
            "pagination": {"complete": False, "has_more": True},
        },
        complete=False,
    )
    view = SearchViewModel.from_read_model(model, query="absent")

    assert view.state is SearchState.PARTIAL
    assert view.hits == ()
    assert view.pagination_complete is False
    assert view.global_no_match is False
    rendered = view.render(
        query_context="/?view=search&fixture=partial&q=absent&snapshot_token=partial"
    )
    assert 'data-search-state="partial"' in rendered
    assert 'data-pagination-complete="false"' in rendered
    assert "global no-match is not established" in rendered
    assert (
        "No approved record or document matches this query in the complete snapshot."
        not in rendered
    )


def test_complete_empty_and_missing_empty_are_distinct_from_partial() -> None:
    complete_empty = SearchViewModel.from_read_model(
        _model(
            {"records": [], "documents": [], "pagination": {"complete": True, "has_more": False}}
        ),
        query="nothing",
    )
    missing_empty = SearchViewModel.from_read_model(build_search_fixture("empty"), query="nothing")

    assert complete_empty.state is SearchState.EMPTY
    assert complete_empty.global_no_match is True
    assert (
        "global no-match" not in complete_empty.render().lower()
        or "complete snapshot" in complete_empty.render()
    )
    assert missing_empty.state is SearchState.EMPTY
    assert missing_empty.global_no_match is False
    assert 'data-status="missing"' in missing_empty.render()


def test_api_unavailable_is_explicit_and_has_no_fallback() -> None:
    view = SearchViewModel.from_read_model(
        build_search_fixture(SearchFixtureState.API_UNAVAILABLE), query="campaign"
    )

    assert view.state is SearchState.API_UNAVAILABLE
    assert view.hits == ()
    rendered = view.render()
    assert 'data-status="api_unavailable"' in rendered
    assert 'data-search-state="api_unavailable"' in rendered
    assert "private-storage fallback" in rendered


def test_stable_url_preserves_opaque_context_and_read_provenance() -> None:
    model = build_search_fixture("complete")
    rendered = render_search_view(
        model,
        query="campaign",
        query_context=(
            "/?view=search&fixture=complete&panel=events&q=campaign"
            "&snapshot_token=snap-1&opaque_ref=keep-me&page=3"
        ),
    )

    assert "fixture=complete" in rendered
    assert "panel=events" in rendered
    assert "snapshot_token=snap-1" in rendered
    assert "opaque_ref=keep-me" in rendered
    assert "record_id=campaign-fixture-1" in rendered
    assert "source_refs" not in rendered.split('data-integration-hook="search-view"', 1)[0]
    assert "fixture-search-complete-v0" in rendered
    assert "2026-10-03T12:00:00Z" in rendered

    view = SearchViewModel.from_read_model(model, query="campaign").with_context(
        "/?view=search&fixture=complete&q=campaign&snapshot_token=snap-1"
    )
    assert view.hits[0].stable_url is not None
    assert "snapshot_token=snap-1" in view.hits[0].stable_url
    payload = view.to_dict()
    assert payload["as_of"] == "2026-10-03T12:00:00Z"
    assert payload["snapshot_token"] == "fixture-search-complete-v0"
    assert payload["source_refs"]

    contextual = SearchViewModel.from_read_model(
        model,
        query="campaign",
        query_context="/?view=search&fixture=complete&snapshot_token=snap-2",
    )
    assert contextual.hits[0].url is not None
    assert "snapshot_token=snap-2" in contextual.hits[0].url


def test_deterministic_fixtures_cover_required_search_states_and_are_read_only() -> None:
    assert set(SEARCH_FIXTURE_STATES) == {"complete", "partial", "empty", "api_unavailable"}
    for state in SearchFixtureState:
        provider = search_fixture_provider(state)
        view = search_fixture_provider(state).read(SEARCH_RESOURCE)
        assert view.schema == "manager-gui.manager-read-model.v0"
        assert public_provider_methods(provider) == ("read",)
        assert not FORBIDDEN_PROVIDER_METHODS.intersection(public_provider_methods(provider))

    complete = SearchViewModel.from_read_model(build_search_fixture("complete"), query="Fixture")
    assert {hit.record_id for hit in complete.hits} == {
        "campaign-fixture-1",
        "strategy-fixture-1",
        "run-fixture-1",
        "document-fixture-1",
    }
    document = SearchViewModel.from_read_model(
        build_search_fixture("complete"), query="research report"
    )
    assert [hit.record_id for hit in document.hits] == ["document-fixture-1"]
    assert "document_title" in document.hits[0].matched_fields
