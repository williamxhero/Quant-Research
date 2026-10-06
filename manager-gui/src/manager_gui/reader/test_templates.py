"""Focused bilingual and provenance tests for Reader R1-T2 copy."""

from __future__ import annotations

import re
from html import unescape
from typing import cast

import pytest

from manager_gui.models import Derivation
from manager_gui.web.i18n import Locale, M, Translator
from manager_gui.web.i18n.catalog import CatalogError, CatalogRegistry
from manager_gui.web.i18n.catalog.reader import (
    ENTRIES,
    READER_CLAIM_EXPLANATION_KEYS,
    READER_LABEL_KEYS,
    READER_MODE_LABEL_KEYS,
    READER_SECTION_KEYS,
)
from manager_gui.web.i18n.glossary import LATIN_ALLOWLIST, find_forbidden_translations

from .fixtures import build_reader_fixture
from .models import (
    ClaimKind,
    ProjectionMode,
    ReaderAvailability,
    ReaderAvailabilityStatus,
    ReaderClaim,
    ReaderSummary,
)
from .templates import ReaderSection, templates

_ASCII_COMMA_BEFORE_CJK = re.compile(r",[㐀-䶿一-鿿豈-﫿]" )
_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z0-9-]*(?: [A-Za-z][A-Za-z0-9-]*)?")
_TAG_OR_TOKEN = re.compile(r"<[^>]*>|\{[^}]*\}")


def _catalog() -> CatalogRegistry:
    registry = CatalogRegistry()
    registry.register(ENTRIES)
    return registry


def _translator(locale: Locale) -> Translator:
    return Translator(locale, strict=True, catalog=_catalog().entries)


def test_reader_catalog_registers_atomically_and_has_bilingual_placeholder_parity() -> None:
    registry = _catalog()
    assert set(READER_CLAIM_EXPLANATION_KEYS) == {
        "known",
        "derived",
        "interpreted",
        "missing",
        "blocked",
        "stale",
        "incomparable",
        "owner_text",
    }
    assert all(key in ENTRIES for key in READER_CLAIM_EXPLANATION_KEYS.values())
    assert set(READER_SECTION_KEYS.values()) <= set(ENTRIES)
    assert set(READER_LABEL_KEYS.values()) <= set(ENTRIES)
    assert set(READER_MODE_LABEL_KEYS.values()) <= set(ENTRIES)
    assert len(registry.entries) >= 40

    with pytest.raises(CatalogError, match="placeholders differ"):
        registry.register({"reader.test.bad": M("值：{name}", "Value")})


def test_reader_catalog_has_no_forbidden_terms_or_chinese_latin_leaks() -> None:
    assert find_forbidden_translations(ENTRIES) == ()
    for key, entry in ENTRIES.items():
        texts = [entry.zh]
        if isinstance(entry.en, str):
            texts.append(entry.en)
        else:
            texts.extend(entry.en.values())
        assert all(_ASCII_COMMA_BEFORE_CJK.search(text) is None for text in texts), key
        chinese = _TAG_OR_TOKEN.sub(" ", entry.zh)
        leaked = set(_LATIN_WORD.findall(chinese)) - LATIN_ALLOWLIST
        assert not leaked, f"{key} contains unapproved Latin: {sorted(leaked)}"


def test_reader_copy_is_bilingual_and_all_eight_claim_explanations_are_stable() -> None:
    zh = templates(_translator(Locale.ZH_CN))
    en = templates(_translator(Locale.EN))
    projection = build_reader_fixture("complete")

    assert zh.section(ReaderSection.QUESTION) == "这页回答什么"
    assert zh.section(ReaderSection.KNOWN) == "当前能确认什么"
    assert zh.section(ReaderSection.UNKNOWNS) == "还不知道什么"
    assert zh.section(ReaderSection.WHY) == "为什么这样说"
    assert en.section(ReaderSection.QUESTION) == "What this page answers"
    assert en.mode_label(ProjectionMode.READER) == "Reader mode"
    assert zh.mode_label(ProjectionMode.EXPERT) == "专业模式"
    assert en.mode_label(ProjectionMode.RAW) == "Raw mode"
    assert projection.sample_data is not None
    assert zh.sample_banner(projection.sample_data) == "样例数据，不代表真实研究结果。"
    assert en.sample_banner(projection.sample_data) == "Sample data; not real research results."

    expected = {
        ClaimKind.KNOWN: "reader.claim.known",
        ClaimKind.DERIVED: "reader.claim.derived",
        ClaimKind.INTERPRETED: "reader.claim.interpreted",
        ClaimKind.MISSING: "reader.claim.missing",
        ClaimKind.BLOCKED: "reader.claim.blocked",
        ClaimKind.STALE: "reader.claim.stale",
        ClaimKind.INCOMPARABLE: "reader.claim.incomparable",
        ClaimKind.OWNER_TEXT: "reader.claim.owner_text",
    }
    for kind, key in expected.items():
        assert key in READER_CLAIM_EXPLANATION_KEYS.values()
        assert zh.translator.t(key)
        assert en.translator.t(key)
        assert key == {
            ClaimKind.KNOWN: "reader.claim.known",
            ClaimKind.DERIVED: "reader.claim.derived",
            ClaimKind.INTERPRETED: "reader.claim.interpreted",
            ClaimKind.MISSING: "reader.claim.missing",
            ClaimKind.BLOCKED: "reader.claim.blocked",
            ClaimKind.STALE: "reader.claim.stale",
            ClaimKind.INCOMPARABLE: "reader.claim.incomparable",
            ClaimKind.OWNER_TEXT: "reader.claim.owner_text",
        }[kind]


def test_typed_templates_preserve_sources_derivation_owner_text_and_raw_values() -> None:
    projection = build_reader_fixture("complete")
    zh = templates(_translator(Locale.ZH_CN))
    en = templates(_translator(Locale.EN))
    source = projection.source_refs[0]

    source_html = zh.source_reference(source)
    assert source.source_id in unescape(source_html)
    assert source.locator in unescape(source_html)
    assert 'translate="no"' in source_html
    assert zh.source_count(projection.source_refs) == (
        "当前范围有 1 条来源引用。数量不表示证据强度。"
    )
    assert en.source_count(projection.source_refs) == (
        "There is 1 source reference in this scope. The count is not evidence strength."
    )

    derived = projection.claims[1]
    assert zh.derivation(derived.derivation).startswith("GUI 派生规则")
    assert "reader.fixture.record-count" in zh.derivation(derived.derivation)
    with pytest.raises(ValueError, match="rule and version"):
        zh.derivation(Derivation("derived", None, (source.source_id,), None))

    owner = ReaderClaim(
        "owner-text",
        ClaimKind.OWNER_TEXT,
        (source,),
        Derivation("direct", None, (source.source_id,), "v0"),
        ReaderAvailability(ReaderAvailabilityStatus.KNOWN, True),
        '原始 owner <text> & "quoted"',
    )
    owner_value = zh.claim_value(owner)
    assert owner_value == '原始 owner <text> & "quoted"'
    assert zh.owner_text(cast(str, owner.value)) == (
        "原始 owner &lt;text&gt; &amp; &quot;quoted&quot;"
    )
    assert en.claim_explanation(owner).startswith("The following is the owner's original text")
    assert zh.claim_value(derived) == derived.value


def test_summary_templates_are_closed_and_do_not_accept_arbitrary_prose() -> None:
    projection = build_reader_fixture("complete")
    zh = templates(_translator(Locale.ZH_CN))
    claim_ids = tuple(claim.claim_id for claim in projection.claims)
    summary = ReaderSummary("reader.summary.claim_count", claim_ids)
    assert zh.summary(summary, projection) == (
        "当前引用了 3 条带来源的陈述。数量不表示研究成功或结论已验证。"
    )

    arbitrary = ReaderSummary("reader.summary.claim_count", claim_ids, {"text": "generated prose"})
    with pytest.raises(ValueError, match="arbitrary params"):
        zh.summary(arbitrary, projection)
    unknown = ReaderSummary("reader.anything", claim_ids)
    with pytest.raises(ValueError, match="unsupported Reader summary"):
        zh.summary(unknown, projection)


def test_reader_template_facade_rejects_untyped_inputs() -> None:
    reader = templates(_translator(Locale.EN))
    with pytest.raises(TypeError, match="sample_data"):
        reader.sample_banner("fixture")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="sources"):
        reader.source_count([build_reader_fixture("complete").source_refs[0]])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unsupported Reader mode"):
        reader.mode_label("admin")
