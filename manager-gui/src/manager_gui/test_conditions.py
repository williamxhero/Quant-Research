"""Focused S2-T2 tests for condition evidence and descriptors."""

from __future__ import annotations

from manager_gui.models import ReadModelStatus
from manager_gui.web.conditions import (
    CONDITION_OUTCOMES,
    ConditionCategory,
    ConditionFixtureState,
    ConditionOutcome,
    ConditionViewModel,
    EvidenceLevel,
    build_conditions_fixture,
    conditions_fixture_provider,
    genome_conditions_link,
    render_genome_conditions,
    render_genome_conditions_view,
)
from manager_gui.web.i18n import Locale, Translator


def test_complete_fixture_separates_applicability_invalidation_and_descriptors() -> None:
    view = ConditionViewModel.from_read_model(build_conditions_fixture("complete"))

    assert len(view.applicability_conditions) == 1
    assert len(view.invalidation_conditions) == 1
    assert len(view.descriptors) == 1
    assert all(item.category is not ConditionCategory.DESCRIPTOR for item in view.conditions)
    assert view.descriptors[0].is_descriptor
    assert not view.descriptors[0].is_validated_condition
    assert view.applicability[0].evidence_level is EvidenceLevel.HIGH
    assert view.applicability[0].time_range.start == "2024-01-01"
    assert view.applicability[0].data_version == "market-data-v3"
    assert view.applicability[0].sample == {"n": 1280, "unit": "signals"}
    assert view.applicability[0].source_refs[0].locator == "fixture://manager-gui/genome-conditions"

    document = render_genome_conditions(view, translator=Translator(Locale.EN))
    chinese_document = render_genome_conditions(view)
    assert "证据等级" in chinese_document
    assert "描述只是观察，不是经过验证的条件。" in chinese_document
    assert 'data-integration-hook="strategy-genome-conditions-view"' in document
    assert 'class="conditions-context-link"' in document
    context_document = render_genome_conditions(
        view, query_context="/?fixture=complete&panel=evidence"
    )
    assert "fixture=complete" in context_document
    assert "panel=evidence" in context_document
    assert 'data-condition-group="applicability"' in document
    assert 'data-condition-group="invalidation"' in document
    assert 'data-condition-group="descriptor"' in document
    assert "Evidence level" in document
    assert "Limitations" in document
    assert "fixture://manager-gui/genome-conditions" in document
    assert "Descriptors are observations only; they are not validated conditions." in document


def test_descriptor_never_becomes_a_condition_and_uncategorised_records_are_ignored() -> None:
    model = build_conditions_fixture("complete")
    payload = dict(model.data)  # type: ignore[arg-type]
    payload["conditions"] = [
        {"condition": "unclassified narrative", "outcome": "supported"},
        {"category": "descriptor", "descriptor": "quiet regime", "outcome": "supported"},
    ]
    from manager_gui.models import ManagerReadModel

    replaced = ManagerReadModel(
        data=payload,
        source_refs=model.source_refs,
        as_of=model.as_of,
        snapshot_token=model.snapshot_token,
        derivation=model.derivation,
        availability=model.availability,
        errors=model.errors,
    )
    view = ConditionViewModel.from_read_model(replaced)

    assert not any(item.condition == "unclassified narrative" for item in view.evidence)
    assert len(view.descriptors) == 2
    assert not any(item.category is ConditionCategory.DESCRIPTOR for item in view.conditions)
    assert 'data-category="descriptor" data-outcome="supported"' in render_genome_conditions(view)


def test_missing_conditions_are_not_recorded_not_a_negative_conclusion() -> None:
    document = render_genome_conditions_view(
        build_conditions_fixture(ConditionFixtureState.MISSING), translator=Translator(Locale.EN)
    )
    chinese_document = render_genome_conditions_view(
        build_conditions_fixture(ConditionFixtureState.MISSING)
    )

    assert 'data-status="missing"' in document
    assert document.count("not recorded") >= 2
    assert chinese_document.count("未记录") >= 2
    assert "no valid conditions" not in document.lower()
    assert "no applicability condition is valid" not in document.lower()


def test_condition_outcome_fixture_states_are_explicit() -> None:
    expected = {
        ConditionFixtureState.SUPPORTED: ConditionOutcome.SUPPORTED,
        ConditionFixtureState.FAILED: ConditionOutcome.FAILED,
        ConditionFixtureState.NOT_EVALUATED: ConditionOutcome.NOT_EVALUATED,
        ConditionFixtureState.INCOMPARABLE: ConditionOutcome.INCOMPARABLE,
    }
    assert set(CONDITION_OUTCOMES) >= set(ConditionOutcome)
    for fixture, outcome in expected.items():
        view = ConditionViewModel.from_read_model(build_conditions_fixture(fixture))
        assert view.applicability[0].outcome is outcome
        rendered = render_genome_conditions(view)
        assert f'data-outcome="{outcome.value}"' in rendered


def test_blocked_stale_integrity_and_api_unavailable_use_shared_status_components() -> None:
    expected = {
        ConditionFixtureState.BLOCKED: ReadModelStatus.BLOCKED,
        ConditionFixtureState.STALE: ReadModelStatus.STALE,
        ConditionFixtureState.INTEGRITY_FAILURE: ReadModelStatus.INTEGRITY_FAILURE,
        ConditionFixtureState.API_UNAVAILABLE: ReadModelStatus.API_UNAVAILABLE,
    }
    for fixture, status in expected.items():
        model = build_conditions_fixture(fixture)
        document = render_genome_conditions(model)
        assert model.availability.status is status
        assert f'data-status="{status.value}"' in document
        assert 'data-display-state="error"' in document
        assert model.availability.reason is not None
        assert model.availability.reason in document


def test_condition_context_links_are_stable_and_provider_is_read_only() -> None:
    first = genome_conditions_link(
        "genome-1",
        query_context="/?panel=evidence&fixture=complete&q=signal",
        category="applicability",
    )
    second = genome_conditions_link(
        "genome-1",
        query_context="/?q=signal&fixture=complete&panel=evidence",
        category=ConditionCategory.APPLICABILITY,
    )
    assert first == second
    assert "view=strategy-conditions" in first
    assert "genome_id=genome-1" in first
    assert "category=applicability" in first
    assert "fixture=complete" in first

    class CountingProvider:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None]] = []

        def read(self, resource: str = "atlas", *, snapshot_token: str | None = None):
            self.calls.append((resource, snapshot_token))
            return build_conditions_fixture("complete")

    provider = CountingProvider()
    document = render_genome_conditions_view(
        provider, snapshot_token="snapshot-request", translator=Translator(Locale.EN)
    )
    assert provider.calls == [("genome_conditions", "snapshot-request")]
    assert "read-only" in document
    fixture_provider = conditions_fixture_provider("complete")
    assert fixture_provider.read().availability.status is ReadModelStatus.KNOWN
    assert (
        tuple(name for name in dir(fixture_provider) if name in {"write", "update", "delete"}) == ()
    )
