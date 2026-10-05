"""Regression tests for the frozen Manager GUI terminology contract."""

from __future__ import annotations

import re

import pytest

from manager_gui.web.i18n import M
from manager_gui.web.i18n.catalog import REGISTRY
from manager_gui.web.i18n.glossary import (
    ALLOWED_LATIN_TERMS,
    ALLOWED_PLACEHOLDERS,
    FORBIDDEN_ZH,
    LATIN_ALLOWLIST,
    PLACEHOLDER_ALLOWLIST,
    TERMS,
    Term,
    find_forbidden_translations,
    main,
    render_markdown,
)

_REQUIRED_TERM_IDS = {
    # UI/common.
    "manager_gui",
    "read_only",
    "atlas",
    "inspector",
    "raw_json",
    "snapshot",
    "snapshot_token",
    "as_of",
    "known_at",
    "source",
    "source_reference",
    "provenance",
    "derivation",
    "cursor",
    "opaque_reference",
    "fixture",
    "owner",
    # Lifecycle.
    "campaign",
    "hypothesis",
    "candidate",
    "candidate_factor",
    "candidate_model",
    "candidate_strategy",
    "run",
    "experiment",
    "evidence",
    "qualification",
    "replication",
    "revalidation",
    "conclusion",
    "decision",
    "focused_research",
    "strategy_family",
    # Controlled statuses.
    "known",
    "derived",
    "interpreted",
    "missing",
    "blocked",
    "stale",
    "incomparable",
    "integrity_failure",
    "api_unavailable",
    "not_evaluated",
    "unconfirmed",
    "cursor_expired",
    "snapshot_drift",
    # Genome and conditions.
    "strategy_genome",
    "behavior_projection",
    "validation_binding",
    "content_hash",
    "lifecycle",
    "applicable_condition",
    "invalidating_condition",
    "descriptive_observation",
    # Evidence and lineage.
    "evidence_ledger",
    "evidence_grade",
    "evidence_category",
    "candidate_evidence",
    "protocol_conforming_evidence",
    "artifact",
    "generated_artifact",
    "verify",
    "hash_mismatch",
    "lineage",
    "shortest_evidence_path",
    "upstream",
    "downstream",
    # Memory.
    "research_memory",
    "formal_research_memory",
    "gui_derived_view",
    "candidate_family",
    "family_memory",
    "failure_category",
    "inclusion",
    "exclusion",
    # Methodology.
    "methodology",
    "workflow",
    "statistical_protocol",
    "policy",
    "benchmark",
    "operational_constraint",
    # History and documents.
    "source_event",
    "source_document",
    "plan",
    "design",
    "report",
    "retrospective",
    "future_idea",
    "external_source",
    "raw_evidence",
    "reverse_citations",
    "approved_catalog_boundary",
    # Search and Portal.
    "search",
    "global_no_match",
    "report_portal",
    "source_publication",
    "renderer",
    "digest",
    "approved_index",
    "deterministic_literal_match",
    "rebuild",
}

_ASCII_COMMA_BEFORE_CJK = re.compile(r",[㐀-䶿一-鿿豈-﫿]")
_PLACEHOLDER_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_REQUIRED_LATIN = {
    "ID",
    "JSON",
    "API",
    "URL",
    "SHA-256",
    "Schema",
    "GUI",
    "ManagerReadModel v0",
}


def _catalog_texts(catalog: dict[str, M]) -> list[tuple[str, str, str]]:
    texts: list[tuple[str, str, str]] = []
    for key, entry in catalog.items():
        if isinstance(entry.zh, str):
            texts.append((key, "zh", entry.zh))
        if isinstance(entry.en, str):
            texts.append((key, "en", entry.en))
        else:
            texts.extend((key, f"en.{form}", text) for form, text in entry.en.items())
    return texts


def test_required_groups_are_covered_and_every_term_is_complete() -> None:
    assert set(TERMS) >= _REQUIRED_TERM_IDS
    assert len(TERMS) >= 60
    ids = [term.id for term in TERMS.values()]
    assert len(ids) == len(set(ids))
    for term in TERMS.values():
        assert isinstance(term, Term)
        assert term.id.strip()
        assert term.en.strip()
        assert term.zh.strip()
        assert term.zh_short is not None and term.zh_short.strip()
        assert term.note is not None and term.note.strip()
        assert isinstance(term.forbidden_zh, tuple)
        assert all(spelling and spelling not in term.zh for spelling in term.forbidden_zh)


def test_frozen_decisions_and_disabled_translation_list() -> None:
    expected = {
        "artifact": ("制品", "产物"),
        "lineage": ("谱系", "血缘"),
        "evidence_ledger": ("证据账本", "台账"),
        "candidate": ("候选对象", "候选策略"),
        "known": ("已记录", "已确认"),
        "blocked": ("已阻塞", "已阻断"),
        "stale": ("已过时", "过期"),
        "reverse_citations": ("被引用于", "反向引用"),
        "fixture": ("样例数据", "夹具"),
        "qualification": ("资格评定", "准入评定"),
        "revalidation": ("重新验证", "再验证"),
        "campaign": ("研究活动", "战役"),
    }
    for term_id, (zh, forbidden) in expected.items():
        term = TERMS[term_id]
        assert term.zh == zh
        assert forbidden in term.forbidden_zh
    assert _REQUIRED_LATIN <= LATIN_ALLOWLIST
    assert _REQUIRED_LATIN <= ALLOWED_LATIN_TERMS
    assert _REQUIRED_LATIN <= FORBIDDEN_ZH | LATIN_ALLOWLIST


def test_registered_catalogs_contain_no_forbidden_translation() -> None:
    assert find_forbidden_translations(REGISTRY.entries) == ()


def test_forbidden_translation_audit_catches_temporary_fixture_data() -> None:
    # This intentionally bad entry is local test data and is never registered.
    temporary_catalog = {"test.bad_translation": M("展示产物", "show artifact")}
    violations = find_forbidden_translations(temporary_catalog)
    assert ("test.bad_translation", "zh", "产物") in violations
    with pytest.raises(AssertionError):
        assert not violations

    valid_catalog = {"test.good_translation": M("展示制品", "show artifact")}
    assert find_forbidden_translations(valid_catalog) == ()


def test_allowlists_are_immutable_and_well_formed() -> None:
    assert LATIN_ALLOWLIST is ALLOWED_LATIN_TERMS
    assert PLACEHOLDER_ALLOWLIST is ALLOWED_PLACEHOLDERS
    assert LATIN_ALLOWLIST
    assert PLACEHOLDER_ALLOWLIST
    assert all(isinstance(value, str) and value.strip() for value in LATIN_ALLOWLIST)
    assert all(_PLACEHOLDER_NAME.fullmatch(value) for value in PLACEHOLDER_ALLOWLIST)
    assert "term" not in PLACEHOLDER_ALLOWLIST
    with pytest.raises(AttributeError):
        LATIN_ALLOWLIST.add("not-allowed")  # type: ignore[attr-defined]


def test_chinese_text_uses_full_width_punctuation_before_cjk() -> None:
    for term in TERMS.values():
        assert _ASCII_COMMA_BEFORE_CJK.search(term.zh) is None, term.id
    for key, field, text in _catalog_texts(dict(REGISTRY.entries)):
        if field == "zh":
            assert _ASCII_COMMA_BEFORE_CJK.search(text) is None, f"{key} [{field}]"


def test_generated_markdown_contains_every_registered_term() -> None:
    markdown = render_markdown()
    assert markdown.startswith("# Manager GUI 中文术语表\n")
    assert "| ID | English | 中文 | 简称 | 说明 | 禁用译法 |" in markdown
    assert markdown.endswith("\n")
    for term in TERMS.values():
        assert f"| {term.id} |" in markdown
        assert term.zh in markdown


def test_module_generator_prints_the_generated_markdown(capsys: pytest.CaptureFixture[str]) -> None:
    main()
    assert capsys.readouterr().out == render_markdown()
