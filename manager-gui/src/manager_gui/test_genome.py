"""Focused S2-T1 tests for the read-only Genome catalog/detail surface."""

from __future__ import annotations

import json
from typing import cast

from manager_gui import Availability, Derivation, ManagerReadModel, ReadModelStatus, SourceReference
from manager_gui.models import JSONValue
from manager_gui.web.genome import (
    BEHAVIOR_PROJECTION_FIELDS,
    LIFECYCLE_EVENT_KINDS,
    LINEAGE_ENTRY_KINDS,
    VALIDATION_BINDING_FIELDS,
    GenomeFilters,
    GenomeFixtureState,
    GenomeViewModel,
    build_genome_fixture,
    genome_fixture_provider,
    genome_link,
    render_genome,
    render_genome_view,
)
from manager_gui.web.i18n import Locale, Translator


def test_complete_fixture_exposes_catalog_detail_behavior_validation_lifecycle_and_lineage() -> (
    None
):
    model = build_genome_fixture(GenomeFixtureState.COMPLETE)
    view = GenomeViewModel.from_read_model(model)

    assert [genome.genome_id for genome in view.catalog] == ["genome-fixture-1"]
    assert view.detail is not None
    assert view.detail.schema == "apex-research.strategy-genome.v1"
    assert view.detail.content_hash == "sha256:fixture-content-1"
    assert view.detail.candidate_revision_text == "1"
    assert tuple(field.name for field in view.detail.behavior_fields) == BEHAVIOR_PROJECTION_FIELDS
    assert all(field.available for field in view.detail.behavior_fields)
    assert tuple(field.name for field in view.detail.validation.fields) == VALIDATION_BINDING_FIELDS
    assert view.detail.validation.result == "accepted"
    assert tuple(event.event_kind for event in view.detail.events) == LIFECYCLE_EVENT_KINDS
    assert tuple(entry.kind for entry in view.detail.lineage) == LINEAGE_ENTRY_KINDS
    assert view.detail.source_refs[0].locator == "fixture://manager-gui/genomes"

    document = render_genome(
        view,
        query_context="/?fixture=complete&panel=events&q=signal",
        translator=Translator(Locale.EN),
    )
    chinese_document = render_genome(view, query_context="/?fixture=complete&panel=events&q=signal")
    assert "基因组目录" in chinese_document
    assert "行为投影" in chinese_document
    assert "验证绑定" in chinese_document
    for value in (
        "Genome catalog",
        "Genome detail",
        "genome-fixture-1",
        "Behavior projection",
        "Validation binding",
        "proposed",
        "validated",
        "published",
        "revoked",
        "tombstoned",
        "Candidate",
        "Hypothesis",
        "Family",
        "Context",
        "Package",
        "Run",
        "Evidence",
        "Raw JSON",
        "fixture://manager-gui/genomes",
    ):
        assert value in document
    assert 'data-integration-hook="strategy-genome-view"' in document
    assert 'data-status="known"' in document
    assert 'data-genome-id="genome-fixture-1"' in document
    assert 'data-display-state="ready"' in document
    assert "fixture=complete" in document
    assert "panel=events" in document
    assert "q=signal" in document


def test_empty_fixture_has_distinct_empty_state_without_claiming_genomes_do_not_exist() -> None:
    model = build_genome_fixture(GenomeFixtureState.EMPTY)
    document = render_genome(model)

    assert 'data-status="missing"' in document
    assert 'data-display-state="empty"' in document
    assert "此范围中没有策略基因组记录。未记录。" in document
    assert document.count("No Genome records are present in this scope.") == 1
    assert "research does not exist" not in document.lower()
    assert "基因组目录" in document


def test_blocked_stale_and_integrity_failure_remain_explicit_and_do_not_become_empty() -> None:
    expected = {
        GenomeFixtureState.BLOCKED: ReadModelStatus.BLOCKED,
        GenomeFixtureState.STALE: ReadModelStatus.STALE,
        GenomeFixtureState.INTEGRITY_FAILURE: ReadModelStatus.INTEGRITY_FAILURE,
    }
    for fixture, status in expected.items():
        model = build_genome_fixture(fixture)
        document = render_genome(model)

        assert model.availability.status is status
        assert f'data-status="{status.value}"' in document
        assert 'data-display-state="error"' in document
        assert 'data-display-state="empty"' not in document
        assert model.availability.reason is not None
        assert model.availability.reason in document
        assert 'class="read-only-badge"' not in document or "read-only" in document.lower()


def test_missing_fields_are_explicit_across_required_genome_axes() -> None:
    model = build_genome_fixture(GenomeFixtureState.MISSING_FIELDS)
    view = GenomeViewModel.from_read_model(model)
    assert view.detail is not None
    assert view.detail.genome_id == "genome-missing-1"
    assert view.detail.content_hash is None
    assert view.detail.candidate_revision is None
    assert view.detail.events == ()
    assert view.detail.lineage == ()
    assert [field.name for field in view.detail.behavior_fields if field.state == "missing"] == [
        field for field in BEHAVIOR_PROJECTION_FIELDS if field != "signals"
    ]
    assert all(field.state == "missing" for field in view.detail.validation.fields)

    document = render_genome(view)
    assert 'data-display-state="partial"' in document
    assert document.count("未记录") >= 20
    assert "没有记录明确的生命周期事件。未记录。" in document
    assert "没有记录候选对象谱系入口。未记录。" in document
    assert 'data-value-state="empty"' in document


def _catalog_model() -> ManagerReadModel:
    source = SourceReference(
        source_id="catalog-source",
        owner="workspace",
        kind="public-record",
        locator="fixture://workspace/genomes",
        schema="workspace.genomes.v0",
        revision="r1",
    )
    data: dict[str, object] = {
        "genomes": [
            {
                "genome_id": "genome-a",
                "schema": "schema-a",
                "content_hash": "hash-a",
                "candidate_revision": {"revision": 1},
                "behavior": {"schema": "behavior-a"},
                "source_refs": ["catalog-source"],
            },
            {
                "genome_id": "genome-b",
                "schema": "schema-b",
                "content_hash": "hash-b",
                "candidate_revision": {"revision": 2},
                "behavior": {"schema": "behavior-b"},
                "source_refs": ["catalog-source"],
            },
        ]
    }
    return ManagerReadModel(
        data=cast(JSONValue, data),
        source_refs=(source,),
        as_of="2026-10-03T12:00:00Z",
        snapshot_token="catalog-snapshot-1",
        derivation=Derivation(kind="direct", version="v0"),
        availability=Availability(ReadModelStatus.KNOWN, True, "catalog fixture"),
    )


def test_catalog_filters_and_context_links_are_stable_and_select_detail() -> None:
    model = _catalog_model()
    filters = GenomeFilters(schema="schema-b", q="genome-b")
    view = GenomeViewModel.from_read_model(model, filters=filters)
    assert [genome.genome_id for genome in view.catalog] == ["genome-b"]
    assert view.detail is not None
    assert view.detail.genome_id == "genome-b"

    link_filters = GenomeFilters(schema="schema-b")
    first = genome_link(
        "genome-b", query_context="/?fixture=complete&panel=events&q=alpha", filters=link_filters
    )
    second = genome_link(
        "genome-b", query_context="/?q=alpha&panel=events&fixture=complete", filters=link_filters
    )
    assert first == second
    assert "view=strategies" in first
    assert "genome_id=genome-b" in first
    assert "fixture=complete" in first
    assert "panel=events" in first
    assert "q=alpha" in first
    assert "schema=schema-b" in first

    document = render_genome(model, query_context="/?fixture=complete&genome_id=genome-b")
    assert 'data-genome-id="genome-b"' in document
    assert "schema-b" in document
    assert "genome-a" in document


def test_lifecycle_timeline_does_not_infer_state_from_as_of_or_unrecognised_events() -> None:
    model = build_genome_fixture(GenomeFixtureState.COMPLETE)
    payload = json.loads(model.to_json())
    payload["data"]["genomes"][0]["events"].append(
        {"event_kind": "active", "occurred_at": "2099-01-01T00:00:00Z"}
    )
    model_with_unknown = ManagerReadModel.from_dict(payload)
    view = GenomeViewModel.from_read_model(model_with_unknown)

    assert view.detail is not None
    assert "active" not in view.detail.lifecycle_states
    document = render_genome(view, translator=Translator(Locale.EN))
    timeline_start = document.index('<ol class="genome-event-timeline"')
    timeline_end = document.index("</ol>", timeline_start)
    timeline = document[timeline_start:timeline_end]
    assert "2099-01-01" not in timeline
    assert "current state" not in timeline.lower()
    assert "no state is inferred" in document.lower()


def test_raw_json_is_json_compatible_and_provider_hook_reads_once_without_mutation_methods() -> (
    None
):
    class CountingProvider:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None]] = []

        def read(
            self,
            resource: str = "atlas",
            *,
            snapshot_token: str | None = None,
        ) -> ManagerReadModel:
            self.calls.append((resource, snapshot_token))
            return build_genome_fixture(GenomeFixtureState.COMPLETE)

    provider = CountingProvider()
    document = render_genome_view(
        provider, query_context="/?fixture=complete&panel=events", snapshot_token="snapshot-request"
    )
    assert provider.calls == [("genomes", "snapshot-request")]
    assert 'data-integration-hook="strategy-genome-view"' in document
    json.dumps(GenomeViewModel.from_read_model(build_genome_fixture("complete")).to_dict())
    assert not any(
        name in dir(provider) for name in ("publish", "propose", "update", "delete", "write")
    )

    fixture_provider = genome_fixture_provider("complete")
    assert fixture_provider.read("genome").availability.status is ReadModelStatus.KNOWN
    public_methods = tuple(
        name
        for name in dir(fixture_provider)
        if not name.startswith("_") and callable(getattr(fixture_provider, name))
    )
    assert public_methods == ("read",)


def test_render_hook_accepts_an_already_read_model_without_a_provider_call() -> None:
    document = render_genome_view(
        build_genome_fixture("complete"),
        genome_id="genome-fixture-1",
        query_context="/?q=signal",
        translator=Translator(Locale.EN),
    )
    assert 'data-genome-id="genome-fixture-1"' in document
    assert "q=signal" in document
    assert "Raw JSON" in document
