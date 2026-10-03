"""Focused tests for the S3-T1 Research Memory page-local contract."""

from __future__ import annotations

from typing import cast

from manager_gui import Availability, Derivation, ManagerReadModel, ReadModelStatus, SourceReference
from manager_gui.models import JSONValue
from manager_gui.web.memory import (
    MemoryAuthority,
    MemoryFilters,
    MemoryViewModel,
    render_memory,
    render_memory_view,
)


def _source(source_id: str, locator: str) -> SourceReference:
    return SourceReference(
        source_id=source_id,
        owner="apex-research",
        kind="public-record",
        locator=locator,
        schema="memory.v1",
        revision="r1",
    )


def _model(
    data: object,
    *,
    status: ReadModelStatus = ReadModelStatus.KNOWN,
    complete: bool = True,
    derivation: Derivation | None = None,
) -> ManagerReadModel:
    return ManagerReadModel(
        data=cast(JSONValue, data),
        source_refs=(_source("source-entry", "fixture://memory/source-entry"),),
        as_of="2026-10-03T12:00:00Z"
        if status not in {ReadModelStatus.BLOCKED, ReadModelStatus.API_UNAVAILABLE}
        else None,
        snapshot_token="memory-snapshot-1"
        if status is not ReadModelStatus.API_UNAVAILABLE
        else None,
        derivation=derivation or Derivation(kind="direct", version="v0"),
        availability=Availability(
            status=status,
            complete=complete,
            reason="fixture memory status",
            retryable=status is ReadModelStatus.API_UNAVAILABLE,
        ),
    )


def _complete_data() -> dict[str, object]:
    return {
        "memory_policies": [
            {
                "policy_id": "policy-1",
                "policy_version": "v1",
                "bounds": {"max_items": 10, "max_depth": 4},
                "source_trust": [{"record_type": "apex-research.run.v1", "rank": 1}],
                "snapshot": {"token": "policy-snapshot-1", "as_of": "2026-10-03T11:00:00Z"},
                "inclusion_rule": "admitted by owner policy",
                "exclusion_rule": "out of declared scope",
            }
        ],
        "memory_families": [
            {
                "family_id": "family-1",
                "family_key": "quality-family",
                "campaign_id": "campaign-1",
                "entry_ids": ["memory-1"],
            }
        ],
        "memory_entries": [
            {
                "memory_id": "memory-1",
                "title": "Data gate failure",
                "safe_summary": "The declared data gate was unavailable.",
                "family_id": "family-1",
                "family_label": "Quality family",
                "stage": "formal",
                "outcome": "rejected",
                "failure_category": "data_blocker",
                "campaign_id": "campaign-1",
                "subject": {
                    "semantic_id": "subject-semantic-1",
                    "structural_fingerprint": "fingerprint-1",
                    "label": "Quality candidate",
                },
                "references": ["source-entry"],
                "conflicts": ["unknown-source"],
                "supersedes": [{"href": "fixture://memory/old-entry", "label": "old-entry"}],
                "lineage": ["source-entry"],
                "policy_id": "policy-1",
                "decisions": {
                    "inclusion": "included",
                    "exclusion": "not excluded",
                    "duplicate": "novel",
                    "repeated_equivalent": "not repeated",
                    "reconciliation": "not required",
                },
            }
        ],
        "family_memory": {
            "memory_id": "family-memory-1",
            "policy": {"record_id": "policy-1"},
            "target_family": {"record_id": "family-1"},
            "source_families": [{"record_id": "family-1"}],
            "snapshot_token": "family-snapshot-1",
            "decisions": [{"fact": {"record_id": "memory-1"}, "included": True}],
        },
        "duplicate_decisions": [
            {
                "decision_id": "duplicate-1",
                "disposition": "novel",
                "matched": [],
                "subject_semantic_id": "subject-semantic-1",
                "structural_fingerprint": "fingerprint-1",
            }
        ],
    }


def test_complete_memory_catalog_detail_policy_and_traceability() -> None:
    model = _model(_complete_data())
    view = MemoryViewModel.from_read_model(model, memory_id="memory-1")

    assert view.authority is MemoryAuthority.FORMAL_RESEARCH_MEMORY
    assert view.formal_memory_present is True
    assert [entry.memory_id for entry in view.entries] == ["memory-1"]
    assert view.entries[0].subject.semantic_id == "subject-semantic-1"
    assert view.entries[0].subject.structural_fingerprint == "fingerprint-1"
    assert view.family_memories[0].snapshot_token == "family-snapshot-1"
    assert view.duplicate_decisions[0].disposition == "novel"

    document = render_memory(view, query_context="/?view=memory&q=gate")
    for text in (
        "Memory-entry catalog",
        "safe_summary",
        "References",
        "Conflicts",
        "Supersedes",
        "Subject semantic ID",
        "Structural fingerprint",
        "Policy",
        "Bounds",
        "Source trust",
        "Snapshot",
        "Inclusion decision",
        "Exclusion decision",
        "Duplicate decision",
        "Repeated-equivalent decision",
        "Reconciliation decision",
        "family-memory",
        "fixture://memory/source-entry",
        "Missing / Unconfirmed",
    ):
        assert text in document
    assert 'data-memory-authority="formal_research_memory"' in document
    assert "memory_id=memory-1" in document
    assert "ordinary records are not promoted" in document


def test_memory_filters_and_stable_detail_links_preserve_context() -> None:
    model = _model(_complete_data())
    view = MemoryViewModel.from_read_model(
        model,
        filters=MemoryFilters(
            family="family-1",
            stage="formal",
            outcome="rejected",
            failure_category="data_blocker",
            campaign="campaign-1",
            subject="subject-semantic-1",
        ),
    )
    assert [entry.memory_id for entry in view.entries] == ["memory-1"]
    document = render_memory(view, query_context="/?view=memory&fixture=complete&q=gate")
    assert 'name="family"' in document
    assert 'name="failure_category"' in document
    assert "fixture=complete" in document
    assert "q=gate" in document
    assert "family=family-1" in document
    assert "stage=formal" in document


def test_ordinary_records_never_become_formal_memory() -> None:
    model = _model({"records": [{"id": "run-1", "record_type": "run", "summary": "failed"}]})
    view = MemoryViewModel.from_read_model(model)
    document = render_memory(view)

    assert view.entries == ()
    assert view.formal_memory_present is False
    assert 'data-memory-empty="true"' in document
    assert "No formal Research Memory entries are recorded" in document
    assert "failed" not in document


def test_derived_memory_is_not_presented_as_formal_memory() -> None:
    model = _model(
        _complete_data(),
        derivation=Derivation(
            kind="derived", rule="gui.memory.aggregate.v0", inputs=("source-entry",)
        ),
    )
    view = MemoryViewModel.from_read_model(model)
    document = render_memory(view)

    assert view.authority is MemoryAuthority.GUI_DERIVED
    assert view.formal_memory_present is False
    assert 'data-memory-authority="gui_derived"' in document
    assert "GUI Derived" in document
    assert "not formal Research Memory" in document
    assert "gui.memory.aggregate.v0" in document
    assert "Named inputs" in document
    assert "Sample count" in document


def test_empty_partial_blocked_stale_integrity_and_api_unavailable_states_are_visible() -> None:
    states = (
        (ReadModelStatus.MISSING, False, 'data-display-state="empty"'),
        (ReadModelStatus.KNOWN, False, 'data-display-state="partial"'),
        (ReadModelStatus.BLOCKED, False, 'data-status="blocked"'),
        (ReadModelStatus.STALE, True, 'data-status="stale"'),
        (ReadModelStatus.INTEGRITY_FAILURE, False, 'data-status="integrity_failure"'),
        (ReadModelStatus.API_UNAVAILABLE, False, 'data-status="api_unavailable"'),
    )
    for status, complete, marker in states:
        document = render_memory(_model({}, status=status, complete=complete))
        assert marker in document
        if status in {ReadModelStatus.MISSING, ReadModelStatus.KNOWN}:
            assert "No formal Research Memory entries are recorded" in document
        else:
            assert 'data-memory-empty-state="not-determined"' in document
            assert 'data-display-state="empty"' not in document
    partial = render_memory(_model({"memory_entries": []}, complete=False))
    assert "Partial Memory scope" in partial


def test_missing_source_is_not_converted_to_a_fake_url() -> None:
    data = {
        "memory_entries": [
            {
                "memory_id": "missing-source",
                "safe_summary": "Known safe text",
                "references": ["does-not-exist"],
                "lineage": ["does-not-exist"],
            }
        ]
    }
    document = render_memory(_model(data), query_context="/?view=memory&memory_id=missing-source")

    assert "does-not-exist" in document
    assert "Missing / Unconfirmed source" in document
    assert "https://does-not-exist" not in document


def test_canonical_public_record_envelopes_are_supported_without_ordinary_record_inference() -> (
    None
):
    data = {
        "records": [
            {
                "record_id": "policy-1",
                "record_type": "apex-research.memory-policy.v1",
                "payload": {
                    "policy_id": "policy-1",
                    "policy_version": "v1",
                    "bounds": {"max_items": 4},
                },
                "lineage": [],
            },
            {
                "record_id": "family-1",
                "record_type": "apex-research.memory-family.v1",
                "payload": {"family_id": "family-1", "family_key": "quality"},
                "lineage": [],
            },
            {
                "record_id": "entry-1",
                "record_type": "apex-research.memory-entry.v1",
                "payload": {
                    "memory_id": "entry-1",
                    "campaign_id": "campaign-1",
                    "policy": {
                        "record_id": "policy-1",
                        "record_type": "apex-research.memory-policy.v1",
                    },
                    "family": {
                        "record_id": "family-1",
                        "record_type": "apex-research.memory-family.v1",
                    },
                    "subject": {"record_id": "subject-1", "record_type": "candidate"},
                    "stage": "formal",
                    "outcome": "rejected",
                    "failure_category": "data_blocker",
                    "safe_summary": "Canonical safe summary",
                    "references": [{"record_id": "source-entry", "record_type": "run"}],
                    "subject_semantic_id": "semantic-1",
                    "structural_fingerprint": "fingerprint-1",
                },
                "lineage": [],
            },
        ]
    }
    view = MemoryViewModel.from_read_model(_model(data))

    assert [entry.memory_id for entry in view.entries] == ["entry-1"]
    assert view.entries[0].policy is not None
    assert view.entries[0].policy.policy_id == "policy-1"
    assert view.entries[0].family_id == "family-1"
    assert view.entries[0].subject.semantic_id == "semantic-1"


def test_provider_hook_reads_only_memory_resource() -> None:
    class Provider:
        def __init__(self) -> None:
            self.resources: list[str] = []

        def read(
            self, resource: str = "atlas", *, snapshot_token: str | None = None
        ) -> ManagerReadModel:
            del snapshot_token
            self.resources.append(resource)
            return _model(_complete_data())

    provider = Provider()
    document = render_memory_view(provider, query_context="/?view=memory&family=family-1")

    assert provider.resources == ["memory"]
    assert 'data-integration-hook="memory-view"' in document
    assert "Memory-entry catalog" in document
