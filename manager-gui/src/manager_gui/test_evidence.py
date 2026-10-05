"""Focused S4-T1 tests for the Evidence Ledger and Artifact verification view."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from manager_gui import Availability, Derivation, ManagerReadModel, ReadModelStatus, SourceReference
from manager_gui.models import JSONValue
from manager_gui.provider import FORBIDDEN_PROVIDER_METHODS, public_provider_methods
from manager_gui.testing.i18n import (
    assert_dom_equivalent,
    assert_lang_propagation,
    assert_language_text,
    assert_owner_text_escaped,
    assert_pseudo_localized,
)
from manager_gui.web.evidence import (
    ArtifactVerificationStatus,
    EvidenceFixtureState,
    EvidenceKind,
    EvidenceOutcome,
    EvidenceViewModel,
    build_evidence_fixture,
    evidence_fixture_provider,
    render_evidence,
    render_evidence_view,
)
from manager_gui.web.evidence_trace import render_evidence_trace
from manager_gui.web.i18n import Locale, Translator
from manager_gui.web.s4_fixtures import build_s4_fixture


def _render_evidence_en(
    view_or_model: EvidenceViewModel | ManagerReadModel,
    *,
    query_context: str | None = None,
    include_raw_json: bool = True,
) -> str:
    return render_evidence(
        view_or_model,
        query_context=query_context,
        include_raw_json=include_raw_json,
        translator=Translator(Locale.EN),
    )


def test_complete_fixture_keeps_ledger_fields_and_both_evidence_classes() -> None:
    view = EvidenceViewModel.from_read_model(build_evidence_fixture("complete"))

    assert view.conclusion == "The protocol result is inspectable."
    assert view.decision == "Retain the published protocol result for review."
    assert view.evidence_level.value == "high"
    assert view.status is EvidenceOutcome.PASS
    assert len(view.sections) == 1
    assert view.sources[0].locator == "fixture://apex-research/evidence-ledger"
    assert view.ledger.limitations == ("This view does not recalculate metrics.",)
    assert view.ledger.blockers == ()
    assert view.ledger.incompatibilities == ()
    assert len(view.ledger.candidate_evidence) == 1
    assert len(view.ledger.protocol_conforming_evidence) == 1
    assert view.ledger.candidate_evidence[0].is_candidate is True
    assert view.ledger.candidate_evidence[0].is_protocol_conforming is False
    assert view.ledger.protocol_conforming_evidence[0].is_protocol_conforming is True

    artifact = view.artifacts[0]
    assert artifact.name == "evidence-report.json"
    assert artifact.media_type == "application/json"
    assert artifact.logical_role == "evidence_report"
    assert artifact.hash == "sha256:" + "a" * 64
    assert artifact.producer == "strategy-reporting"
    assert artifact.runtime_version == "runtime-v2"
    assert artifact.data_version == "prices-2026-09"
    assert artifact.verification_status is ArtifactVerificationStatus.VERIFIED


def test_renderer_separates_candidate_from_protocol_conforming_and_preserves_links() -> None:
    rendered = _render_evidence_en(
        build_evidence_fixture("complete"), query_context="/?view=evidence&fixture=complete"
    )

    assert 'data-integration-hook="evidence-view"' in rendered
    assert 'data-evidence-group="candidate"' in rendered
    assert 'data-evidence-group="protocol_conforming"' in rendered
    assert 'data-promotion="never"' in rendered
    assert "Candidate evidence is not protocol-conforming evidence" in rendered
    assert 'data-evidence-kind="candidate"' in rendered
    assert 'data-evidence-kind="protocol_conforming"' in rendered
    assert "fixture://apex-research/evidence-ledger" in rendered
    assert "fixture://strategy-reporting/artifacts/evidence-report.json" in rendered
    assert 'data-verification-status="verified"' in rendered
    assert "Raw JSON" in rendered
    assert "evidence-complete-v0" in rendered


def test_outcomes_keep_not_evaluated_blocked_fail_and_incomparable_distinct() -> None:
    expected = {
        EvidenceFixtureState.NOT_EVALUATED: EvidenceOutcome.NOT_EVALUATED,
        EvidenceFixtureState.BLOCKED: EvidenceOutcome.BLOCKED,
        EvidenceFixtureState.FAIL: EvidenceOutcome.FAIL,
        EvidenceFixtureState.INCOMPARABLE: EvidenceOutcome.INCOMPARABLE,
        EvidenceFixtureState.PASS: EvidenceOutcome.PASS,
    }
    for fixture, status in expected.items():
        view = EvidenceViewModel.from_read_model(build_evidence_fixture(fixture))
        assert view.status is status
        rendered = _render_evidence_en(view)
        assert f'data-evidence-status="{status.value}"' in rendered
        if status is EvidenceOutcome.BLOCKED:
            assert "The approved protocol source is blocked." in rendered
            assert 'data-evidence-status="fail"' not in rendered
        if status is EvidenceOutcome.NOT_EVALUATED:
            assert "Not evaluated" in rendered
            assert 'data-evidence-status="fail"' not in rendered
        if status is EvidenceOutcome.INCOMPARABLE:
            assert "Data snapshots are not comparable." in rendered


def test_artifact_error_states_keep_specific_reason_and_read_model_integrity_status() -> None:
    expected = {
        EvidenceFixtureState.HASH_MISMATCH: (
            ArtifactVerificationStatus.HASH_MISMATCH,
            ReadModelStatus.INTEGRITY_FAILURE,
            "Declared hash does not match",
        ),
        EvidenceFixtureState.MISSING_ARTIFACT: (
            ArtifactVerificationStatus.MISSING_ARTIFACT,
            ReadModelStatus.MISSING,
            "cannot be located",
        ),
        EvidenceFixtureState.UNKNOWN_SCHEMA: (
            ArtifactVerificationStatus.UNKNOWN_SCHEMA,
            ReadModelStatus.INTEGRITY_FAILURE,
            "schema is not recognised",
        ),
    }
    for fixture, (artifact_status, read_status, detail) in expected.items():
        model = build_evidence_fixture(fixture)
        view = EvidenceViewModel.from_read_model(model)
        assert model.availability.status is read_status
        assert view.artifacts[0].verification_status is artifact_status
        assert detail in (view.artifacts[0].verification_detail or "")
        rendered = _render_evidence_en(view)
        assert f'data-verification-status="{artifact_status.value}"' in rendered
        assert detail in rendered


def test_empty_and_unavailable_states_are_not_invented_into_evidence() -> None:
    empty = EvidenceViewModel.from_read_model(build_evidence_fixture("empty"))
    unavailable = EvidenceViewModel.from_read_model(build_evidence_fixture("api_unavailable"))

    assert empty.records == ()
    assert empty.artifacts == ()
    assert empty.read_model.availability.status is ReadModelStatus.MISSING
    assert unavailable.read_model.availability.status is ReadModelStatus.API_UNAVAILABLE
    assert unavailable.status is EvidenceOutcome.UNAVAILABLE
    assert 'data-display-state="empty"' in _render_evidence_en(empty)
    assert 'data-status="api_unavailable"' in _render_evidence_en(unavailable)


def test_raw_json_and_projection_are_stable() -> None:
    view = EvidenceViewModel.from_read_model(build_evidence_fixture("complete"))

    assert '"evidence-report.json"' in view.raw_json
    assert '"snapshot_token": "evidence-complete-v0"' in view.raw_json
    first = view.to_dict()
    second = EvidenceViewModel.from_read_model(ManagerReadModel.from_json(view.raw_json)).to_dict()
    assert first == second


def test_parser_handles_explicit_source_and_artifact_links_without_filesystem_access() -> None:
    source = SourceReference(
        source_id="public-source",
        owner="owner",
        kind="evidence-record",
        locator="https://example.invalid/evidence/1",
        schema="evidence.v2",
        revision="r1",
    )
    model = ManagerReadModel(
        data=cast(
            JSONValue,
            {
                "ledger": {
                    "conclusion": "A conclusion",
                    "decision": "A decision",
                    "evidence_kind": "candidate",
                    "evidence_level": "candidate",
                    "records": [
                        {
                            "id": "candidate-1",
                            "label": "Candidate",
                            "evidence_kind": "candidate",
                            "status": "not_evaluated",
                            "source_refs": ["public-source"],
                            "artifacts": [
                                {
                                    "id": "candidate-artifact",
                                    "name": "candidate.json",
                                    "artifact_link": "https://example.invalid/artifacts/candidate.json",
                                    "verification_status": "not_evaluated",
                                }
                            ],
                        }
                    ],
                }
            },
        ),
        source_refs=(source,),
        as_of="2026-10-03T10:00:00Z",
        snapshot_token="snapshot-1",
        derivation=Derivation(kind="direct", inputs=(source.source_id,), version="v1"),
        availability=Availability(status=ReadModelStatus.KNOWN, complete=True),
    )
    view = EvidenceViewModel.from_read_model(model)

    assert view.ledger.evidence_kind is EvidenceKind.CANDIDATE
    assert view.sources[0].locator == source.locator
    assert view.artifacts[0].locator == "https://example.invalid/artifacts/candidate.json"
    rendered = _render_evidence_en(view)
    assert source.locator in rendered
    assert "https://example.invalid/artifacts/candidate.json" in rendered
    assert 'data-promotion="never"' in rendered


def test_provider_hook_reads_only_evidence_resource_and_preserves_snapshot() -> None:
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
            return build_evidence_fixture("complete")

    provider = CountingProvider()
    rendered = render_evidence_view(
        provider, snapshot_token="requested-snapshot", translator=Translator(Locale.EN)
    )

    assert provider.calls == [("evidence", "requested-snapshot")]
    assert 'data-integration-hook="evidence-view"' in rendered
    assert "Evidence Ledger" in rendered


def test_fixture_provider_is_read_only_and_rejects_other_resources() -> None:
    provider = evidence_fixture_provider("complete")
    assert provider.read().availability.status is ReadModelStatus.KNOWN
    methods = public_provider_methods(provider)
    assert set(methods) <= {"read"}
    assert FORBIDDEN_PROVIDER_METHODS.isdisjoint(public_provider_methods(provider))
    try:
        provider.read("atlas")
    except ValueError as error:
        assert "does not serve resource" in str(error)
    else:  # pragma: no cover - the provider must keep its resource boundary
        raise AssertionError("evidence fixture provider served an unrelated resource")


def test_aliases_keep_the_s4_hook_discoverable_without_shared_integration_edits() -> None:
    from manager_gui.web.evidence import (
        EvidenceLedgerViewModel,
        build_evidence_ledger_fixture,
        render_evidence_ledger_view,
    )

    assert EvidenceLedgerViewModel is EvidenceViewModel
    assert build_evidence_ledger_fixture("complete").snapshot_token == "evidence-complete-v0"
    assert "evidence-view" in render_evidence_ledger_view(build_evidence_fixture("complete"))


def test_evidence_and_trace_localize_fixture_copy_in_both_locales() -> None:
    model = build_s4_fixture("evidence", "complete")
    canonical_json = model.to_json()
    context_zh = "/?view=evidence&fixture=complete&lang=zh-CN"
    context_en = "/?view=evidence&fixture=complete&lang=en"
    zh = Translator(Locale.ZH_CN)
    en = Translator(Locale.EN)
    evidence_zh = render_evidence(model, query_context=context_zh, translator=zh)
    evidence_en = render_evidence(model, query_context=context_en, translator=en)
    trace_zh = render_evidence_trace(model, query_context=context_zh, translator=zh)
    trace_en = render_evidence_trace(model, query_context=context_en, translator=en)

    assert "证据账本" in evidence_zh and "候选证据" in evidence_zh
    assert "协议结果可供检查。" in evidence_zh
    assert "符合研究协议的证据" in evidence_zh
    assert "Candidate evidence is not protocol-conforming evidence" not in evidence_zh
    assert "Evidence Ledger" in evidence_en and "Candidate evidence" in evidence_en
    assert "The protocol result is inspectable." in evidence_en
    assert "Conclusion → evidence → source → artifact trace" not in trace_zh
    assert "结论 → 证据 → 来源 → 制品追溯" in trace_zh
    assert "Conclusion → evidence → source → artifact trace" in trace_en
    assert "从此制品打开谱系" in trace_zh
    assert "Open lineage for this artifact" in trace_en

    assert_language_text(evidence_zh, Locale.ZH_CN)
    assert_language_text(evidence_en, Locale.EN)
    assert_language_text(trace_zh, Locale.ZH_CN)
    assert_language_text(trace_en, Locale.EN)
    assert_dom_equivalent(evidence_zh, evidence_en)
    assert_dom_equivalent(trace_zh, trace_en)
    assert_lang_propagation(evidence_zh, Locale.ZH_CN, source_url=context_zh)
    assert_lang_propagation(evidence_en, Locale.EN, source_url=context_en)
    assert_lang_propagation(trace_zh, Locale.ZH_CN, source_url=context_zh)
    assert_lang_propagation(trace_en, Locale.EN, source_url=context_en)

    evidence_pseudo = render_evidence(
        model, query_context=context_en, translator=Translator(Locale.EN, pseudo=True)
    )
    trace_pseudo = render_evidence_trace(
        model, query_context=context_en, translator=Translator(Locale.EN, pseudo=True)
    )
    assert_pseudo_localized(evidence_pseudo)
    assert_pseudo_localized(trace_pseudo)
    assert model.to_json() == canonical_json


def test_evidence_and_trace_escape_owner_text_exactly_once_without_translation() -> None:
    value = 'Owner <text> & "quoted" {x} 中文'
    base = build_evidence_fixture("complete")
    payload = dict(cast(dict[str, object], base.data))
    payload["conclusion"] = value
    model = replace(base, data=cast(JSONValue, payload))

    evidence = render_evidence(model, include_raw_json=False, translator=Translator(Locale.ZH_CN))
    trace = render_evidence_trace(model, translator=Translator(Locale.EN))
    assert_owner_text_escaped(evidence, value)
    assert_owner_text_escaped(trace, value)
    assert "Source note" not in evidence


def test_blocked_not_evaluated_and_fail_remain_distinct_in_chinese() -> None:
    for fixture, expected in (
        ("blocked", "已阻塞"),
        ("not_evaluated", "未评估"),
        ("fail", "失败"),
    ):
        rendered = render_evidence(
            build_evidence_fixture(fixture), translator=Translator(Locale.ZH_CN)
        )
        assert expected in rendered
        if fixture != "fail":
            assert 'data-evidence-status="fail"' not in rendered
