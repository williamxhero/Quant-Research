"""Focused tests for the T3 Atlas page-local view and renderer."""

from __future__ import annotations

from typing import cast

from manager_gui import (
    Availability,
    Derivation,
    ManagerReadModel,
    ReadModelStatus,
    SourceReference,
    fixture_provider,
)
from manager_gui.models import JSONValue
from manager_gui.web.atlas import (
    LIFECYCLE_SPINE,
    AtlasFilters,
    AtlasViewModel,
    atlas_link,
    render_atlas,
)


def _complete_model() -> ManagerReadModel:
    source = SourceReference(
        source_id="workspace-atlas",
        owner="strategy-workspace",
        kind="public-record",
        locator="workspace://atlas",
        schema="workspace.atlas.v1",
        revision="r7",
    )
    records = [
        {
            "id": "campaign-1",
            "record_type": "campaign",
            "title": "Campaign one",
            "state": "active",
            "changed_at": "2026-10-03T08:00:00Z",
            "source": "workspace-atlas",
        },
        {
            "id": "hypothesis-1",
            "record_type": "hypothesis",
            "title": "Hypothesis one",
            "state": "open",
            "changed_at": "2026-10-02T08:00:00Z",
            "source": "workspace-atlas",
            "conclusion_state": "unresolved",
            "research_gaps": ["Need replication evidence"],
        },
        {
            "id": "candidate-1",
            "record_type": "candidate",
            "title": "Candidate one",
            "state": "blocked",
            "changed_at": "2026-10-01T08:00:00Z",
            "source": "workspace-atlas",
            "availability": "blocked",
            "frontier": True,
        },
        {
            "id": "run-1",
            "record_type": "run",
            "title": "Run one",
            "state": "completed",
            "changed_at": "2026-09-30T08:00:00Z",
            "source": "workspace-atlas",
        },
        {"id": "evidence-1", "record_type": "evidence", "state": "recorded"},
        {"id": "qualification-1", "record_type": "qualification", "state": "pending"},
        {"id": "replication-1", "record_type": "replication", "state": "planned"},
        {"id": "revalidation-1", "record_type": "revalidation", "state": "planned"},
    ]
    return ManagerReadModel(
        data=cast(
            JSONValue,
            {
                "records": records,
                "research_gaps": [
                    {"id": "gap-1", "title": "Coverage gap", "detail": "More dates are needed."}
                ],
            },
        ),
        source_refs=(source,),
        as_of="2026-10-03T09:00:00Z",
        snapshot_token="atlas-snapshot-7",
        derivation=Derivation(kind="direct", inputs=(source.source_id,), version="v1"),
        availability=Availability(status=ReadModelStatus.KNOWN, complete=True),
    )


def test_complete_atlas_preserves_lifecycle_and_explicit_sections() -> None:
    view = AtlasViewModel.from_read_model(_complete_model(), recent_limit=None)

    assert tuple(record.record_type for record in view.records)[:3] == (
        "campaign",
        "hypothesis",
        "candidate",
    )
    assert tuple(record_type for record_type, _ in view.lifecycle_counts) == LIFECYCLE_SPINE
    assert view.status_counts == (
        ("active", 1),
        ("blocked", 1),
        ("completed", 1),
        ("open", 1),
        ("pending", 1),
        ("planned", 2),
        ("recorded", 1),
    )
    assert [record.record_id for record in view.blocked_or_unavailable] == ["candidate-1"]
    assert [record.record_id for record in view.unresolved_conclusions] == ["hypothesis-1"]
    assert [record.record_id for record in view.frontier] == ["candidate-1"]
    assert len(view.research_gaps) == 2

    document = render_atlas(view, query_context="/?fixture=partial&q=alpha")
    for label in (
        "Campaign",
        "Hypothesis",
        "Candidate",
        "Run",
        "Evidence",
        "Qualification",
        "Replication",
        "Revalidation",
    ):
        assert label in document
    assert "Recently changed" in document
    assert "Blocked or unavailable" in document
    assert "Unresolved conclusions" in document
    assert "Research gaps" in document
    assert "Navigable frontier" in document
    assert "success, ranking, or advice" in document
    assert "atlas-snapshot-7" in document


def test_empty_atlas_says_scope_has_no_records() -> None:
    model = fixture_provider("empty").read("atlas")
    view = AtlasViewModel.from_read_model(model)

    assert view.records == ()
    document = render_atlas(view)
    assert 'data-status="missing"' in document
    assert 'data-display-state="empty"' in document
    assert "No records are present in this Atlas scope." in document
    assert "research does not exist" not in document.lower()


def test_partial_atlas_keeps_available_records_and_context() -> None:
    model = fixture_provider("partial").read("atlas")
    view = AtlasViewModel.from_read_model(model)

    assert view.read_model.availability.complete is False
    assert [record.record_id for record in view.records] == ["campaign-fixture-1"]
    document = render_atlas(view, query_context="/?fixture=partial&q=campaign")
    assert 'data-display-state="partial"' in document
    assert "Fixture campaign" in document
    assert "fixture-partial-v0" in document
    assert "campaign" in document


def test_blocked_atlas_uses_shared_status_semantics_without_fake_empty_copy() -> None:
    model = fixture_provider("blocked").read("atlas")
    document = render_atlas(AtlasViewModel.from_read_model(model))

    assert 'data-status="blocked"' in document
    assert 'data-display-state="error"' in document
    assert "The approved read seam is blocked" in document
    assert "research does not exist" not in document.lower()


def test_filters_and_links_are_stable_and_preserve_query_context() -> None:
    view = AtlasViewModel.from_read_model(
        _complete_model(),
        filters=AtlasFilters(record_type="candidate", state="blocked", date="2026-10-01"),
    )

    assert [record.record_id for record in view.records] == ["candidate-1"]
    assert atlas_link(
        "candidate/1",
        query_context="/?fixture=partial&panel=events&q=alpha",
    ) == ("/?view=atlas&fixture=partial&panel=events&q=alpha&record_id=candidate%2F1")
    assert atlas_link(
        "candidate/1",
        query_context="/?q=alpha&fixture=partial",
    ) == atlas_link("candidate/1", query_context="/?fixture=partial&q=alpha")

    document = render_atlas(view, query_context="/?fixture=partial&q=alpha")
    assert 'name="record_type"' in document
    assert 'name="state"' in document
    assert 'name="date"' in document
    assert 'name="source"' in document
    assert 'name="availability"' in document
    assert (
        'href="/?view=atlas&amp;fixture=partial&amp;q=alpha&amp;record_type=candidate'
        '&amp;state=blocked&amp;date=2026-10-01&amp;record_id=candidate-1"' in document
    )
