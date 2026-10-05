"""Focused S3-T2 tests for failure experiences and Derived patterns."""

from __future__ import annotations

from functools import partial
from typing import cast

from manager_gui import Availability, Derivation, ManagerReadModel, ReadModelStatus, SourceReference
from manager_gui.models import JSONValue
from manager_gui.web.failure_patterns import (
    FailureFilters,
    FailureViewModel,
    failure_patterns_view,
)
from manager_gui.web.failure_patterns import (
    render_failure_patterns as _render_failure_patterns,
)
from manager_gui.web.failure_patterns import (
    render_failure_patterns_view as _render_failure_patterns_view,
)
from manager_gui.web.failure_patterns import (
    render_memory_failure_view as _render_memory_failure_view,
)
from manager_gui.web.i18n import Translator
from manager_gui.web.i18n.catalog import CATALOG, merge
from manager_gui.web.i18n.catalog.l4_memory import ENTRIES

EN_TRANSLATOR = Translator("en", strict=True, catalog=merge(CATALOG, ENTRIES))
render_failure_patterns = partial(_render_failure_patterns, translator=EN_TRANSLATOR)
render_failure_patterns_view = partial(_render_failure_patterns_view, translator=EN_TRANSLATOR)
render_memory_failure_view = partial(_render_memory_failure_view, translator=EN_TRANSLATOR)


def _source(source_id: str, locator: str, *, kind: str = "public-record") -> SourceReference:
    return SourceReference(
        source_id=source_id,
        owner="apex-research",
        kind=kind,
        locator=locator,
        schema="failure.v1",
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
        source_refs=(
            _source("source-campaign", "fixture://failure/campaign"),
            _source("source-run", "fixture://failure/run"),
            _source("source-evidence", "fixture://failure/evidence"),
            _source("source-pattern", "fixture://failure/pattern"),
        ),
        as_of=(
            "2026-10-03T12:00:00Z"
            if status not in {ReadModelStatus.BLOCKED, ReadModelStatus.API_UNAVAILABLE}
            else None
        ),
        snapshot_token=(
            "failure-snapshot-1" if status is not ReadModelStatus.API_UNAVAILABLE else None
        ),
        derivation=derivation or Derivation(kind="direct", version="v0"),
        availability=Availability(
            status=status,
            complete=complete,
            reason="fixture failure status",
            retryable=status is ReadModelStatus.API_UNAVAILABLE,
        ),
    )


def _layered_data() -> dict[str, object]:
    return {
        "memory_entries": [
            {
                "memory_id": "memory-failure-1",
                "title": "Formal data gate failure",
                "safe_summary": "The declared data gate rejected the candidate.",
                "failure_category": "data_blocker",
                "stage": "formal",
                "outcome": "rejected",
                "campaign_id": "campaign-1",
                "references": ["source-evidence"],
                "conflicts": [{"record_id": "memory-conflict", "record_type": "memory-entry"}],
                "supersedes": {"record_id": "memory-old", "record_type": "memory-entry"},
                "lineage": [
                    {"source_kind": "apex-research.campaign.v1", "source_id": "campaign-1"},
                    {"source_kind": "apex-research.run.v1", "source_id": "run-1"},
                ],
            }
        ],
        "failures": [
            {
                "failure_id": "failure-1",
                "title": "Adapter failure",
                "summary": "The adapter did not expose the required field.",
                "failure_category": "adapter_failure",
                "stage": "adapter",
                "outcome": "execution_error",
                "campaign_id": "campaign-1",
                "candidate_id": "candidate-1",
                "run_id": "run-1",
                "evidence_id": "evidence-1",
                "artifact_id": "artifact-1",
                "source_document_id": "document-1",
                "references": ["source-evidence"],
                "conflicts": ["conflict-1"],
                "supersedes": ["failure-old"],
                "lineage": {
                    "state": "partial",
                    "reason": "artifact lineage was not published",
                    "edges": ["source-run"],
                },
            }
        ],
        "records": [
            {"id": "successful-run", "record_type": "run", "outcome": "success"},
        ],
        "derived_patterns": [
            {
                "pattern_id": "pattern-1",
                "title": "Repeated adapter failures",
                "status": "derived",
                "rule": "group by failure_category and stage",
                "input_scope": ["campaign-1", "runs:2026-Q3"],
                "sample_count": 3,
                "failure_ids": ["failure-1", "failure-2", "failure-3"],
                "failure_category": "adapter_failure",
                "stage": "adapter",
                "outcome": "execution_error",
                "source_refs": ["source-pattern"],
                "lineage": {"state": "stale", "edges": ["source-pattern"]},
            }
        ],
    }


def test_layers_preserve_failures_formal_memory_and_explicit_derived_fields() -> None:
    view = FailureViewModel.from_read_model(_model(_layered_data()), failure_id="failure-1")

    assert view.formal_memory_present is True
    assert [entry.failure_id for entry in view.memory_entries] == ["memory-failure-1"]
    assert [entry.failure_id for entry in view.failures] == ["failure-1"]
    assert view.failures[0].failure_category == "adapter_failure"
    assert view.failures[0].stage == "adapter"
    assert view.failures[0].outcome == "execution_error"
    assert view.failures[0].lineage.declared_state == "partial"
    assert view.failures[0].artifact.record_id == "artifact-1"
    assert view.patterns[0].status is ReadModelStatus.DERIVED
    assert view.patterns[0].rule == "group by failure_category and stage"
    assert view.patterns[0].input_scope == ("campaign-1", "runs:2026-Q3")
    assert view.patterns[0].sample_count == 3
    assert view.patterns[0].lineage.declared_state == "stale"

    document = render_failure_patterns(
        view,
        query_context="/?view=failure-patterns&fixture=complete&q=adapter",
    )
    for text in (
        "Formal Research Memory failure entries",
        "Ordinary failure records",
        "Failure category",
        "execution_error",
        "Derived",
        "group by failure_category and stage",
        "runs:2026-Q3",
        "Sample count",
        "fixture://failure/pattern",
        "Campaign",
        "Candidate",
        "Run",
        "Evidence",
        "Artifact",
        "Source Document",
        "partial",
        "stale",
        "Conflicts",
        "Supersedes",
    ):
        assert text in document
    assert "successfully" not in document
    assert 'data-pattern-status="derived"' in document
    assert 'data-memory-layer="formal-research-memory"' in document


def test_empty_formal_memory_keeps_raw_failures_separate_and_success_is_not_invented() -> None:
    model = _model(
        {
            "records": [
                {
                    "record_id": "raw-failure-1",
                    "record_type": "failure",
                    "failure_category": "data_blocker",
                    "stage": "intake",
                    "outcome": "rejected",
                    "summary": "Raw failure remains visible.",
                },
                {"record_id": "run-success", "record_type": "run", "outcome": "success"},
            ]
        }
    )
    view = failure_patterns_view(model)
    assert view.formal_memory_present is False
    assert view.memory_entries == ()
    assert [entry.failure_id for entry in view.failures] == ["raw-failure-1"]
    assert view.failures[0].outcome == "rejected"
    document = render_failure_patterns(view)
    assert "No formal Research Memory entries are recorded" in document
    assert "Raw failure records remain a separate layer" in document
    assert "Raw failure remains visible." in document
    assert "run-success" not in document
    assert "success" not in document


def test_missing_links_never_become_fake_urls_and_conflicts_remain_visible() -> None:
    model = _model(
        {
            "failures": [
                {
                    "failure_id": "missing-links",
                    "failure_category": "runtime_failure",
                    "stage": "behavioral",
                    "outcome": "execution_error",
                    "campaign_id": "unknown-campaign",
                    "conflicts": ["conflict-record"],
                }
            ]
        }
    )
    view = FailureViewModel.from_read_model(model, failure_id="missing-links")
    entry = view.selected_failure
    assert entry is not None
    assert entry.campaign.target is None
    assert entry.candidate.record_id is None
    document = render_failure_patterns(view)
    assert "unknown-campaign" in document
    assert "Missing / Unconfirmed link" in document
    assert "https://unknown-campaign" not in document
    assert "conflict-record" in document
    for label in ("Candidate", "Run", "Evidence", "Artifact", "Source Document"):
        assert label in document


def test_all_source_availability_states_remain_distinct() -> None:
    states = (
        (ReadModelStatus.MISSING, False, 'data-display-state="empty"'),
        (ReadModelStatus.KNOWN, False, 'data-display-state="partial"'),
        (ReadModelStatus.BLOCKED, False, 'data-status="blocked"'),
        (ReadModelStatus.STALE, True, 'data-status="stale"'),
        (ReadModelStatus.INTEGRITY_FAILURE, False, 'data-status="integrity_failure"'),
        (ReadModelStatus.API_UNAVAILABLE, False, 'data-status="api_unavailable"'),
    )
    for status, complete, marker in states:
        document = render_failure_patterns(_model({}, status=status, complete=complete))
        assert marker in document
        if status is ReadModelStatus.MISSING:
            assert 'data-display-state="empty"' in document
        elif status is ReadModelStatus.KNOWN and complete:
            assert "No formal Research Memory entries are recorded" in document
        else:
            assert 'data-memory-state="not-determined"' in document
            assert 'data-display-state="empty"' not in document


def test_filters_and_provider_hooks_use_read_only_resources_once() -> None:
    class Provider:
        def __init__(self) -> None:
            self.resources: list[str] = []

        def read(
            self,
            resource: str = "atlas",
            *,
            snapshot_token: str | None = None,
        ) -> ManagerReadModel:
            del snapshot_token
            self.resources.append(resource)
            return _model(_layered_data())

    provider = Provider()
    view = failure_patterns_view(
        provider,
        filters=FailureFilters(failure_category="adapter_failure", stage="adapter"),
    )
    assert provider.resources == ["failure_patterns"]
    assert [entry.failure_id for entry in view.failures] == ["failure-1"]
    rendered = render_memory_failure_view(provider)
    assert provider.resources == ["failure_patterns", "memory"]
    assert 'data-integration-hook="failure-patterns-view"' in rendered
    assert "Failure experiences" in rendered
    assert "Derived" in rendered
    rendered_direct = render_failure_patterns_view(_model(_layered_data()))
    assert "Repeated adapter failures" in rendered_direct
