"""Focused R4-T2 tests for the standalone Evidence/Lineage Reader seam."""

from __future__ import annotations

from dataclasses import replace
from html import unescape
from typing import cast
from urllib.parse import parse_qsl, urlsplit

from manager_gui import Availability, Derivation, ManagerReadModel, ReadModelStatus, SourceReference
from manager_gui.models import JSONValue
from manager_gui.web.evidence import build_evidence_fixture
from manager_gui.web.evidence_lineage_reader import (
    ReaderTraceMode,
    EvidenceLineageReaderViewModel,
    build_evidence_lineage_reader_fixture,
    project_evidence_lineage_reader,
    render_evidence_lineage_reader,
)
from manager_gui.web.i18n import Locale, Translator
from manager_gui.web.lineage import build_lineage_fixture


def test_reader_projection_keeps_candidate_protocol_and_v0_bytes() -> None:
    model = build_evidence_lineage_reader_fixture("complete")
    projection = project_evidence_lineage_reader(model, sample=True)

    assert projection.to_dict()["data"] == model.data
    assert projection.raw_source.raw_bytes == model.to_json().encode("utf-8")
    assert projection.sample_data is not None
    assert projection.sample_data.fixture_state == "complete"
    assert {claim.claim_id for claim in projection.claims} >= {
        "evidence.conclusion",
        "evidence.candidate.candidate-evidence-1",
        "evidence.protocol.protocol-evidence-1",
    }
    assert any(claim.claim_id.startswith("evidence.source.") for claim in projection.claims)
    assert all(claim.source_refs for claim in projection.claims)
    assert all(claim.derivation.inputs for claim in projection.claims)


def test_reader_default_is_table_trace_and_links_preserve_opaque_context() -> None:
    context = (
        "/?view=evidence&fixture=complete&scope=A0&filter=a&filter=b&"
        "snapshot_token=evidence-complete-v0&lang=en"
    )
    rendered = render_evidence_lineage_reader(
        build_evidence_lineage_reader_fixture("complete"),
        query_context=context,
        translator=Translator(Locale.EN),
    )

    assert 'data-reader-mode="reader"' in rendered
    assert 'data-lineage-view="table"' in rendered
    assert 'data-evidence-class="candidate"' in rendered
    assert 'data-evidence-class="protocol_conforming"' in rendered
    assert "Source" in rendered and "Derivation" in rendered and "Availability" in rendered
    assert "Candidate evidence is not protocol-conforming evidence" in rendered
    assert 'data-sample-banner="fixture"' in rendered
    links = [
        unescape(chunk.split('href="', 1)[1].split('"', 1)[0])
        for chunk in rendered.split("<a ")
        if "reader-lineage-link" in chunk or "reader-evidence-link" in chunk
    ]
    assert links
    for link in links:
        query = parse_qsl(urlsplit(link).query, keep_blank_values=True)
        assert query.count(("filter", "a")) == 1
        assert query.count(("filter", "b")) == 1
        assert ("snapshot_token", "evidence-complete-v0") in query


def test_expert_graph_and_raw_modes_remain_explicit() -> None:
    model = build_evidence_lineage_reader_fixture("complete")
    lineage = build_lineage_fixture("complete")
    expert = render_evidence_lineage_reader(
        model,
        lineage_model=lineage,
        mode=ReaderTraceMode.EXPERT,
        query_context="/?view=evidence&fixture=complete&lang=en",
        translator=Translator(Locale.EN),
    )
    raw = render_evidence_lineage_reader(model, mode=ReaderTraceMode.RAW, translator=Translator(Locale.EN))

    assert 'data-reader-mode="expert"' in expert
    assert 'data-lineage-graph="expert"' in expert
    assert '<svg' in expert
    assert 'data-reader-mode="raw"' in raw
    assert '<pre class="reader-raw-json">' in raw
    assert model.to_json() in raw


def test_lineage_relation_without_explicit_reason_stays_unknown_not_inferred() -> None:
    source = SourceReference("trace-source", "owner", "evidence", "https://example.invalid/evidence")
    evidence = replace(
        build_evidence_fixture("complete"),
        source_refs=(source,),
        data=cast(
            JSONValue,
            {
                "conclusion": "Published conclusion",
                "records": [{"id": "record-1", "label": "Protocol", "evidence_kind": "protocol_conforming", "source_refs": ["trace-source"]}],
                "sources": ["trace-source"],
                "artifacts": [],
                "lineage": {
                    "relations": [{"source": "record-1", "target": "conclusion-1", "relation": "supports", "source_refs": ["trace-source"]}]
                },
            },
        ),
    )
    view = EvidenceLineageReaderViewModel.from_read_model(evidence)
    assert len(view.relations) == 1
    assert view.relations[0].recorded is True
    assert view.relations[0].why is None
    assert view.relations[0].availability.status.value == "missing"
    assert "why this relation exists" in render_evidence_lineage_reader(evidence, translator=Translator(Locale.EN))


def test_gaps_keep_blocked_stale_incomparable_and_not_evaluated_distinct() -> None:
    for status in (
        ReadModelStatus.BLOCKED,
        ReadModelStatus.STALE,
        ReadModelStatus.INCOMPARABLE,
    ):
        base = build_evidence_lineage_reader_fixture("complete")
        model = replace(base, availability=Availability(status, False, "owner boundary"))
        view = EvidenceLineageReaderViewModel.from_read_model(model)
        assert view.gaps
        assert {gap.availability.status for gap in view.gaps} == {
            view.availability.status
        }
    not_evaluated = build_evidence_lineage_reader_fixture("not_evaluated")
    view = EvidenceLineageReaderViewModel.from_read_model(not_evaluated)
    assert any(gap.availability.status.value == "not_evaluated" for gap in view.gaps)
    out = render_evidence_lineage_reader(not_evaluated, translator=Translator(Locale.EN))
    assert 'data-evidence-status="not_evaluated"' in out
    assert 'data-evidence-status="fail"' not in out


def test_reader_copy_is_bilingual_and_owner_text_is_not_translated_or_double_escaped() -> None:
    base = build_evidence_lineage_reader_fixture("complete")
    payload = dict(cast(dict[str, JSONValue], base.data))
    payload["conclusion"] = 'Owner <text> & "quoted" 中文'
    model = replace(base, data=cast(JSONValue, payload))
    original_json = model.to_json()
    zh = render_evidence_lineage_reader(model, translator=Translator(Locale.ZH_CN))
    en = render_evidence_lineage_reader(model, translator=Translator(Locale.EN))

    assert "证据追溯阅读器" in zh
    assert "Evidence trace Reader" in en
    assert 'Owner &lt;text&gt; &amp; &quot;quoted&quot; 中文' in en
    assert '<span data-owner-text="true">Owner &lt;text&gt;' in en
    assert 'Owner &amp;lt;text&amp;gt;' not in en
    assert model.to_json() == original_json  # rendering never mutates the envelope
