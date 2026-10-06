"""Focused R4-T1 Memory/Failure Reader contract tests."""

from __future__ import annotations

from dataclasses import replace
from html import unescape
from typing import cast
from urllib.parse import parse_qsl, urlsplit

import pytest

from manager_gui import Availability, ManagerReadModel, ReadModelError, ReadModelStatus
from manager_gui.fixtures import build_fixture
from manager_gui.models import JSONValue
from manager_gui.reader import ClaimKind, ReaderAvailabilityStatus
from manager_gui.web.i18n import Translator
from manager_gui.web.i18n.catalog import CATALOG
from manager_gui.web.memory_failure_reader import (
    FailureReaderState,
    FailureReaderViewModel,
    MemoryReaderViewModel,
    project_failure_reader,
    project_memory_reader,
    render_failure_reader,
    render_memory_reader,
)

EN = Translator("en", strict=True, catalog=CATALOG)
ZH = Translator("zh-CN", strict=True, catalog=CATALOG)


def _failure_model(
    data: object, *, status: ReadModelStatus = ReadModelStatus.KNOWN, complete: bool = True
) -> ManagerReadModel:
    base = build_fixture("complete", resource="memory")
    return replace(
        base,
        data=cast(JSONValue, data),
        availability=Availability(
            status=status,
            complete=complete,
            reason="fixture reader status",
            retryable=status is ReadModelStatus.API_UNAVAILABLE,
        ),
        errors=(
            (ReadModelError("not_evaluated", "No evaluation was published."),)
            if status is ReadModelStatus.KNOWN and not complete
            else ()
        ),
    )


def test_memory_reader_keeps_formal_failure_and_derived_layers_separate() -> None:
    model = build_fixture("complete", resource="memory")
    view = MemoryReaderViewModel.from_read_model(model)

    assert [entry.memory_id for entry in view.formal_memory] == ["memory-fixture-1"]
    assert [entry.failure_id for entry in view.failure_records] == ["failure-fixture-1"]
    assert [pattern.pattern_id for pattern in view.derived_patterns] == ["pattern-fixture-1"]
    assert view.records[0].layer.value == "formal_research_memory"
    assert view.records[1].layer.value == "failure_record"
    assert view.records[2].derived is True

    projection = project_memory_reader(model, sample=True)
    assert projection.sample_data is not None
    assert projection.sample_data.fixture_state == "complete"
    assert projection.claims
    assert any(claim.kind is ClaimKind.DERIVED for claim in projection.claims)
    assert projection.raw_source.raw_bytes == model.to_json().encode("utf-8")
    assert projection.to_dict()["data"] == model.data


def test_failure_reader_statuses_are_distinct_and_gaps_are_not_failures() -> None:
    model = _failure_model(
        {
            "failures": [
                {
                    "failure_id": "success-1",
                    "title": "A successful check",
                    "failure_category": "check",
                    "references": ["evidence-fixture-1"],
                    "outcome": "success",
                },
                {
                    "failure_id": "failure-1",
                    "title": "A failed check",
                    "failure_category": "check",
                    "references": ["evidence-fixture-1"],
                    "outcome": "failure",
                },
                {
                    "failure_id": "blocked-1",
                    "title": "A blocked check",
                    "failure_category": "check",
                    "references": ["evidence-fixture-1"],
                    "status": "blocked",
                },
                {
                    "failure_id": "unevaluated-1",
                    "title": "An unevaluated check",
                    "failure_category": "check",
                    "references": ["evidence-fixture-1"],
                    "status": "not_evaluated",
                },
                {
                    "failure_id": "stale-1",
                    "title": "A stale check",
                    "failure_category": "check",
                    "references": ["evidence-fixture-1"],
                    "status": "stale",
                },
                {
                    "failure_id": "incomparable-1",
                    "title": "An incomparable check",
                    "failure_category": "check",
                    "references": ["evidence-fixture-1"],
                    "status": "incomparable",
                },
            ]
        }
    )
    view = FailureReaderViewModel.from_read_model(model)
    states = {record.failure_id: record.state for record in view.records}

    assert states["success-1"] is FailureReaderState.SUCCESS
    assert states["failure-1"] is FailureReaderState.FAILURE
    assert states["blocked-1"] is FailureReaderState.BLOCKED
    assert states["unevaluated-1"] is FailureReaderState.NOT_EVALUATED
    assert states["stale-1"] is FailureReaderState.STALE
    assert states["incomparable-1"] is FailureReaderState.INCOMPARABLE
    assert states["blocked-1"] is not FailureReaderState.FAILURE

    projection = project_failure_reader(model)
    assert any(claim.kind is ClaimKind.BLOCKED for claim in projection.limitations)
    assert any(claim.kind is ClaimKind.STALE for claim in projection.limitations)
    assert any(claim.kind is ClaimKind.INCOMPARABLE for claim in projection.limitations)
    assert any(
        claim.availability.status is ReaderAvailabilityStatus.NOT_EVALUATED
        for claim in projection.unknowns
    )

    document = render_failure_reader(
        view,
        query_context="/?view=memory-failures&fixture=complete&filter=a&filter=b",
        translator=EN,
    )
    for marker in (
        'data-record-state="success"',
        'data-record-state="failure"',
        'data-record-state="blocked"',
        'data-record-state="not_evaluated"',
        'data-record-state="stale"',
        'data-record-state="incomparable"',
    ):
        assert marker in document
    assert "Success" in document
    assert "Blocked" in document
    assert "Not evaluated" in document
    assert "Stale" in document
    assert "Incomparable" in document
    assert "filter=a" in document and "filter=b" in document
    assert "success rate" not in document.lower()
    assert "ranking" not in document.lower()


def test_owner_text_raw_and_source_boundaries_survive_bilingual_rendering() -> None:
    model = _failure_model(
        {
            "memory_entries": [
                {
                    "memory_id": "owner-memory",
                    "title": "Owner wording <do not translate>",
                    "safe_summary": "Owner summary <keep raw>",
                    "failure_category": "owner_category",
                    "references": ["campaign-fixture-1"],
                }
            ],
            "failures": [
                {
                    "failure_id": "owner-failure",
                    "title": "Owner failure <raw>",
                    "summary": "Owner reason <raw>",
                    "failure_category": "owner_failure_category",
                    "outcome": "failure",
                    "references": ["campaign-fixture-1"],
                }
            ],
        }
    )
    projection = project_memory_reader(model)
    assert projection.raw_source.raw_bytes == model.to_json().encode("utf-8")
    assert projection.to_dict()["data"] == model.data
    rendered_en = render_memory_reader(model, translator=EN)
    rendered_zh = render_memory_reader(model, translator=ZH)
    for document in (rendered_en, rendered_zh):
        assert "Owner wording &lt;do not translate&gt;" in document
        assert "Owner summary &lt;keep raw&gt;" in document
        assert 'data-owner-text="true"' in document
        assert '<details class="memory-reader-raw">' in document
        assert "owner_category" in document
    assert "正式研究记忆" in rendered_zh
    assert "Formal Research Memory" in rendered_en


def test_reader_links_preserve_repeated_context_and_missing_source_is_not_a_url() -> None:
    model = _failure_model(
        {
            "failures": [
                {
                    "failure_id": "missing-source",
                    "title": "Missing source failure",
                    "failure_category": "runtime",
                    "outcome": "failure",
                    "references": ["unknown-source"],
                }
            ]
        }
    )
    document = render_failure_reader(
        model,
        query_context="/?view=memory-failures&fixture=complete&filter=a&filter=b&filter=",
        translator=EN,
    )
    links = [
        unescape(part.split('href="', 1)[1].split('"', 1)[0])
        for part in document.split("<a ")
        if "failure-reader-detail-link" in part
    ]
    assert links
    query = parse_qsl(urlsplit(links[0]).query, keep_blank_values=True)
    assert query.count(("filter", "a")) == 1
    assert query.count(("filter", "b")) == 1
    assert query.count(("filter", "")) == 1
    assert "https://unknown-source" not in document
    assert "Missing or unconfirmed source" in document


@pytest.mark.parametrize(
    ("status", "complete", "expected"),
    [
        (ReadModelStatus.BLOCKED, False, ReaderAvailabilityStatus.BLOCKED),
        (ReadModelStatus.STALE, False, ReaderAvailabilityStatus.STALE),
        (ReadModelStatus.INCOMPARABLE, False, ReaderAvailabilityStatus.INCOMPARABLE),
        (ReadModelStatus.KNOWN, False, ReaderAvailabilityStatus.NOT_EVALUATED),
    ],
)
def test_scope_status_is_kept_in_projection(
    status: ReadModelStatus, complete: bool, expected: ReaderAvailabilityStatus
) -> None:
    model = _failure_model({}, status=status, complete=complete)
    projection = project_memory_reader(model)
    gaps = projection.limitations + projection.unknowns
    assert gaps
    assert any(claim.availability.status is expected for claim in gaps)
