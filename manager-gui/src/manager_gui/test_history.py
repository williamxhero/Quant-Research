"""Focused tests for the S5-T2 source-event history surface."""

from __future__ import annotations

from typing import cast

from manager_gui import Availability, Derivation, ManagerReadModel, ReadModelStatus, SourceReference
from manager_gui.models import JSONValue
from manager_gui.web.history import (
    HISTORY_SCOPES,
    HistoryEventType,
    HistoryViewModel,
    build_history_fixture,
    render_history_view,
)


def _history_model(
    data: object, status: ReadModelStatus = ReadModelStatus.KNOWN
) -> ManagerReadModel:
    source = SourceReference(
        source_id="history-source",
        owner="test-owner",
        kind="source-events",
        locator="fixture://tests/history",
        schema="test.history.v0",
        revision="r1",
    )
    return ManagerReadModel(
        data=cast(JSONValue, data),
        source_refs=(source,),
        as_of="2026-10-03T12:00:00Z",
        snapshot_token="history-test-v1",
        derivation=Derivation(kind="direct", inputs=(source.source_id,), version="v0"),
        availability=Availability(status=status, complete=status is ReadModelStatus.KNOWN),
    )


def test_history_admits_only_allowed_source_events_and_orders_by_source_time() -> None:
    model = _history_model(
        {
            "events": [
                {"id": "run-late", "type": "run", "source_event_time": "2026-10-03T09:00:00Z"},
                {
                    "id": "gui-phase",
                    "type": "phase-transition",
                    "changed_at": "2026-10-03T08:00:00Z",
                },
                {
                    "id": "campaign-first",
                    "type": "campaign",
                    "source_event_time": "2026-10-01T09:00:00Z",
                },
                {"id": "gui-known", "type": "study", "known_at": "2026-10-01T10:00:00Z"},
                {"id": "study-middle", "type": "study", "event_time": "2026-10-02T09:00:00Z"},
            ]
        }
    )

    view = HistoryViewModel.from_read_model(model)

    assert [event.event_id for event in view.events] == [
        "campaign-first",
        "study-middle",
        "run-late",
    ]
    assert [event.event_type for event in view.events] == [
        HistoryEventType.CAMPAIGN,
        HistoryEventType.STUDY,
        HistoryEventType.RUN,
    ]
    rendered = view.render()
    assert "phase-transition" not in rendered
    assert "GUI phase transitions are never inferred" in rendered


def test_single_event_payload_is_supported_without_inventing_other_events() -> None:
    model = _history_model(
        {
            "id": "single-run",
            "event_type": "run",
            "source_event_time": "2026-10-03T09:00:00Z",
        }
    )

    view = HistoryViewModel.from_read_model(model)

    assert [event.event_id for event in view.events] == ["single-run"]
    assert [event.event_type for event in view.events] == [HistoryEventType.RUN]


    for scope in HISTORY_SCOPES:
        view = HistoryViewModel.from_read_model(build_history_fixture(scope))
        assert view.scope == scope
        assert set(view.event_types) == set(HistoryEventType)
        assert f'data-history-scope="{scope}"' in view.render()


def test_history_hook_reads_provider_once() -> None:
    class CountingProvider:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def read(
            self, resource: str = "atlas", *, snapshot_token: str | None = None
        ) -> ManagerReadModel:
            del snapshot_token
            self.calls.append(resource)
            return build_history_fixture("A0")

    provider = CountingProvider()
    document = render_history_view(provider, scope="A0")

    assert provider.calls == ["history"]
    assert 'data-integration-hook="history-view"' in document
    assert "A0" in document


def test_history_api_unavailable_remains_explicit() -> None:
    view = HistoryViewModel.from_read_model(_history_model({}, ReadModelStatus.API_UNAVAILABLE))

    rendered = view.render()

    assert view.events == ()
    assert 'data-status="api_unavailable"' in rendered
    assert 'data-display-state="error"' in rendered
