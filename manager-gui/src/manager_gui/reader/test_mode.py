"""Focused Reader R1-T3 tests for URL state, modes, and sample boundaries."""

from __future__ import annotations

from dataclasses import replace
from html import unescape
from urllib.parse import parse_qsl, urlsplit

from manager_gui.fixtures import build_fixture
from manager_gui.models import Derivation, MANAGER_READ_MODEL_SCHEMA, SourceReference
from manager_gui.reader import (
    ProjectionMode,
    ReaderURLState,
    build_reader_fixture,
    compatibility_reference,
    expert_reference,
    parse_reader_url,
    project_read_model,
    raw_reference,
    render_mode_switch,
    render_mode_switch_form,
    render_sample_banner,
)


CONTEXT_URL = (
    "/reader?lang=en&fixture=complete&scope=A0&root=record-1&filter=state%3Dknown"
    "&filter=owner%3Dfixture&snapshot=snap-1&mode=raw&mode=expert"
)


def _query(url: str) -> list[tuple[str, str]]:
    return parse_qsl(urlsplit(url).query, keep_blank_values=True)


def test_reader_url_defaults_to_reader_and_round_trips_duplicate_context() -> None:
    state = parse_reader_url(CONTEXT_URL)

    assert state.mode is ProjectionMode.RAW  # first duplicate wins deterministically
    assert state.lang == "en"
    assert state.fixture == "complete"
    assert state.scope == "A0"
    assert state.root == "record-1"
    assert state.filter == "state=known"
    assert state.snapshot == "snap-1"

    expert_url = state.mode_url("expert")
    query = _query(expert_url)
    assert query.count(("mode", "expert")) == 1
    assert not any(key == "mode" and value == "raw" for key, value in query)
    assert query.count(("filter", "state=known")) == 1
    assert query.count(("filter", "owner=fixture")) == 1
    assert parse_reader_url(expert_url).mode is ProjectionMode.EXPERT

    default = parse_reader_url("/reader?lang=en&fixture=complete")
    assert default.mode is ProjectionMode.READER
    assert _query(default.url()) == [("lang", "en"), ("fixture", "complete"), ("mode", "reader")]


def test_reader_url_invalid_mode_is_reader_without_losing_context() -> None:
    state = ReaderURLState.from_url("/reader?mode=not-a-mode&scope=S3&snapshot_token=s-2")

    assert state.mode is ProjectionMode.READER
    assert state.snapshot == "s-2"
    assert _query(state.mode_url(ProjectionMode.RAW)) == [
        ("mode", "raw"),
        ("scope", "S3"),
        ("snapshot_token", "s-2"),
    ]


def test_mode_switch_links_are_get_only_accessible_and_no_javascript() -> None:
    markup = render_mode_switch(CONTEXT_URL, locale="en")

    assert markup.startswith('<nav class="reader-mode-switch"')
    assert markup.count("class=\"reader-mode-link\"") == 3
    assert markup.count('aria-current="page"') == 1
    assert 'aria-label="Reader modes"' in markup
    assert "onclick" not in markup
    assert "<script" not in markup
    assert 'data-reader-mode="reader"' in markup
    assert 'data-reader-mode="expert"' in markup
    assert 'data-reader-mode="raw"' in markup
    assert "filter=state%3Dknown" in unescape(markup)
    assert "filter=owner%3Dfixture" in unescape(markup)


def test_mode_switch_form_is_get_only_and_retains_repeated_hidden_values() -> None:
    markup = render_mode_switch_form(CONTEXT_URL, locale="en")

    assert '<form class="reader-mode-switch-form" method="get"' in markup
    assert 'name="mode"' in markup
    assert 'name="filter" value="state=known"' in unescape(markup)
    assert 'name="filter" value="owner=fixture"' in unescape(markup)
    assert markup.count('name="filter"') == 2
    assert 'aria-label="Reader modes"' in markup
    assert 'type="submit"' in markup
    assert "onclick" not in markup
    assert "<script" not in markup


def test_fixture_banner_is_exact_deterministic_and_has_no_owner_identity() -> None:
    fixture = build_reader_fixture("complete", resource="atlas")
    first = render_sample_banner(fixture)
    second = render_sample_banner(fixture)

    assert first == second
    assert first == (
        '<aside class="reader-sample-banner" data-sample-banner="fixture" '
        'role="note" aria-label="样例数据，不代表真实研究结果">'
        "样例数据，不代表真实研究结果</aside>"
    )
    assert "fixture_state" not in first
    assert "atlas" not in first
    assert "fixture://" not in first
    assert "owner" not in first


def test_owner_envelope_never_gets_a_sample_banner() -> None:
    owner = project_read_model(build_fixture("complete"))
    assert render_sample_banner(owner) == ""
    assert render_sample_banner(build_fixture("complete")) == ""

    owner_ref = SourceReference("owner", "system", "record", "https://owner.invalid/1")
    owner_model = replace(
        build_fixture("complete"),
        source_refs=(owner_ref,),
        derivation=Derivation("direct", inputs=(owner_ref.source_id,), version="owner-v1"),
    )
    assert render_sample_banner(project_read_model(owner_model)) == ""


def test_expert_and_raw_references_remain_manager_read_model_v0() -> None:
    projection = build_reader_fixture("complete")

    expert = expert_reference(projection)
    raw = raw_reference(projection)
    assert expert.schema == MANAGER_READ_MODEL_SCHEMA
    assert raw.schema == MANAGER_READ_MODEL_SCHEMA
    assert expert.sha256 == projection.raw_source.sha256
    assert raw.sha256 == projection.raw_source.sha256
    assert compatibility_reference(projection, "expert") == expert
    assert compatibility_reference(projection, "raw") == raw
