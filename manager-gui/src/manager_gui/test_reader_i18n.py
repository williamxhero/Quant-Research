"""Focused bilingual catalog and template tests for Reader R1-T2."""

from __future__ import annotations

from dataclasses import replace

import pytest

from manager_gui.fixtures import build_fixture
from manager_gui.models import Derivation, SourceReference
from manager_gui.reader import (
    ClaimKind,
    ReaderAvailability,
    ReaderAvailabilityStatus,
    ReaderClaim,
    ReaderSummary,
    build_reader_fixture,
)
from manager_gui.web.i18n import Locale, TranslationError, Translator
from manager_gui.web.i18n.catalog import CATALOG
from manager_gui.web.i18n.catalog.reader import (
    ENTRIES,
    EXPLANATION_KEYS,
    READER_PLACEHOLDER_NAMES,
    READER_TEMPLATES,
    ReaderTemplateParams,
    reader_catalog_policy_violations,
    render_availability_explanation,
    render_claim_explanation,
    render_projection_summary,
    render_reader_template,
    render_summary,
)
from manager_gui.web.i18n.translator import validate_entry


def _translator(locale: Locale) -> Translator:
    return Translator(locale, strict=True, catalog=ENTRIES)


def test_reader_catalog_is_additive_and_has_the_required_bilingual_surfaces() -> None:
    required = {
        "reader.page_question",
        "reader.currently_confirmed",
        "reader.not_yet_known",
        "reader.why_this_is_said",
        "reader.sample.banner",
        "reader.source",
        "reader.derivation",
        "reader.limitation",
        "reader.gap",
        "reader.mode.reader",
        "reader.mode.expert",
        "reader.mode.raw",
        "label.reader_source",
        "label.reader_derivation",
        "label.reader_limitation",
        "label.reader_gap",
        "label.reader_mode.reader",
        "label.reader_mode.expert",
        "label.reader_mode.raw",
    }
    assert required <= set(ENTRIES)
    assert all(key.startswith(("reader.", "label.reader_")) for key in ENTRIES)
    # R1-T4 owns central registration; importing this module must not mutate it.
    assert not set(ENTRIES) & set(CATALOG)


def test_every_claim_kind_has_one_stable_explanation_entry() -> None:
    assert set(EXPLANATION_KEYS) == set(ClaimKind)
    for kind in ClaimKind:
        key = EXPLANATION_KEYS[kind]
        assert key.startswith("reader.claim.")
        assert key in ENTRIES
        assert key in READER_TEMPLATES
        # OwnerText has a source value; other explanations are fixed sentences.
        params = ReaderTemplateParams(text="owner text") if kind is ClaimKind.OWNER_TEXT else None
        for locale in Locale:
            assert _translator(locale).t(key, **({"text": "owner text"} if params else {}))


def test_placeholder_parity_and_reader_policy_are_enforced() -> None:
    for key, message in ENTRIES.items():
        validate_entry(key, message)
    assert reader_catalog_policy_violations() == ()
    assert READER_PLACEHOLDER_NAMES
    assert {
        "fixture",
        "n",
        "scope",
        "source_id",
        "text",
        "value",
    } >= READER_PLACEHOLDER_NAMES


def test_bilingual_page_questions_statuses_modes_and_banner_render() -> None:
    zh = _translator(Locale.ZH_CN)
    en = _translator(Locale.EN)
    assert zh.t("reader.page_question") == "这页回答什么？"
    assert en.t("reader.page_question") == "What does this page answer?"
    assert zh.t("reader.currently_confirmed") == "当前能确认什么？"
    assert en.t("reader.not_yet_known") == "What is not known yet?"
    assert zh.t("label.reader_mode.reader") == "阅读模式"
    assert en.t("label.reader_mode.reader") == "Reader"
    assert zh.t("reader.sample.banner", fixture="complete") == (
        "当前显示的是样例数据，不代表真实研究结果：complete"
    )
    assert en.t("reader.sample.banner", fixture="complete") == (
        "The current view uses sample data and does not represent real research results: complete"
    )


def test_typed_template_params_and_source_refs_are_required() -> None:
    source = SourceReference(
        "record-1",
        "owner",
        "record",
        "https://owner.invalid/record/1",
    )
    zh = _translator(Locale.ZH_CN)
    en = _translator(Locale.EN)
    assert render_reader_template(
        zh,
        "reader.source.reference",
        source_refs=(source,),
    ) == "来源引用：record-1"
    assert render_reader_template(
        en,
        "reader.derivation.detail",
        params=ReaderTemplateParams(value="reader.rule"),
        source_refs=(source,),
    ) == "This item is derived from the named source by rule reader.rule: record-1"
    with pytest.raises(ValueError, match="requires at least one source"):
        render_reader_template(zh, "reader.source.reference")
    with pytest.raises(ValueError, match="does not accept source_refs"):
        render_reader_template(zh, "reader.claim.known", source_refs=(source,))
    with pytest.raises(ValueError, match="missing typed parameter"):
        render_reader_template(zh, "reader.sample.banner")
    with pytest.raises(TranslationError, match="unknown Reader template"):
        render_reader_template(zh, "reader.generated.prose")
    with pytest.raises(TypeError, match="ReaderTemplateParams"):
        render_reader_template(zh, "reader.sample.banner", params={"fixture": "x"})  # type: ignore[arg-type]


def test_plural_reader_templates_use_typed_counts_and_source_refs() -> None:
    sources = (
        SourceReference("record-1", "owner", "record", "https://owner.invalid/1"),
        SourceReference("record-2", "owner", "record", "https://owner.invalid/2"),
    )
    zh = _translator(Locale.ZH_CN)
    en = _translator(Locale.EN)

    assert render_reader_template(
        zh,
        "reader.source.count",
        params=ReaderTemplateParams(n=len(sources)),
        source_refs=sources,
    ) == "当前范围有 2 条来源引用；数量不表示证据强度。"
    assert render_reader_template(
        en,
        "reader.source.count",
        params=ReaderTemplateParams(n=1),
        source_refs=(sources[0],),
    ) == "There is 1 source reference in this scope; the count is not evidence strength."
    with pytest.raises(ValueError, match="requires a count"):
        render_reader_template(zh, "reader.source.count", source_refs=sources)
    with pytest.raises(ValueError, match="match source_refs"):
        render_reader_template(
            en,
            "reader.source.count",
            params=ReaderTemplateParams(n=1),
            source_refs=sources,
        )
    with pytest.raises(ValueError, match="does not accept source_refs"):
        render_reader_template(
            zh,
            "reader.summary.claim_count",
            params=ReaderTemplateParams(n=2),
            source_refs=(sources[0],),
        )


def test_availability_explanations_cover_non_claim_statuses() -> None:
    for status in (
        ReaderAvailabilityStatus.NOT_EVALUATED,
        ReaderAvailabilityStatus.INTEGRITY_FAILURE,
        ReaderAvailabilityStatus.API_UNAVAILABLE,
    ):
        zh = render_availability_explanation(_translator(Locale.ZH_CN), status)
        en = render_availability_explanation(_translator(Locale.EN), status)
        assert zh and en and zh != en
        assert "未评估" in zh or "完整性" in zh or "API" in zh
        assert "not evaluated" in en.lower() or "integrity" in en.lower() or "api" in en.lower()


def test_owner_text_is_preserved_and_html_escaped_without_reparsing() -> None:
    owner = "  owner 原文 <b>& {term:known}</b>  "
    zh = _translator(Locale.ZH_CN)
    params = ReaderTemplateParams(text=owner)
    assert render_reader_template(zh, "reader.claim.owner_text", params=params) == (
        "以下是属主原文；界面不会翻译或改写：  owner 原文 <b>& {term:known}</b>  "
    )
    assert render_reader_template(
        zh, "reader.claim.owner_text", params=params, as_html=True
    ) == (
        "以下是属主原文；界面不会翻译或改写：  owner 原文 &lt;b&gt;&amp; {term:known}&lt;/b&gt;  "
    )


def test_claim_and_projection_helpers_use_exact_reader_projection_api() -> None:
    projection = build_reader_fixture("complete")
    claim = projection.claims[0]
    assert "系统记录到" in render_claim_explanation(_translator(Locale.ZH_CN), claim)
    assert "system records" in render_claim_explanation(_translator(Locale.EN), claim)

    model = build_fixture("complete")
    owner = ReaderClaim(
        "owner-note",
        ClaimKind.OWNER_TEXT,
        model.source_refs,
        Derivation("direct", inputs=(model.source_refs[0].source_id,)),
        ReaderAvailability(ReaderAvailabilityStatus.KNOWN, True),
        "owner source note",
    )
    summary = ReaderSummary(
        "reader.summary.source_note", (owner.claim_id,), {"text": "owner source note"}
    )
    with_summary = replace(projection, claims=(owner,), summary=summary)
    assert render_summary(_translator(Locale.EN), summary) == "Source note: owner source note"
    assert render_projection_summary(
        _translator(Locale.ZH_CN), with_summary
    ) == "来源说明：owner source note"
    assert render_projection_summary(_translator(Locale.EN), projection) is None


def test_summary_params_cannot_be_used_as_an_open_ended_prose_channel() -> None:
    with pytest.raises(ValueError, match="unsupported Reader template parameter"):
        ReaderTemplateParams.from_summary(
            ReaderSummary("reader.summary.source_note", ("claim",), {"prompt": "free prose"})
        )
    with pytest.raises(TypeError, match="non-empty string"):
        ReaderTemplateParams(fixture=" ")
    with pytest.raises(TypeError, match="integer"):
        ReaderTemplateParams(n=True)


def test_catalog_module_has_no_page_renderer_dependency() -> None:
    # Catalog/template ownership stays in i18n and cannot reach page renderers.
    import manager_gui.web.i18n.catalog.reader as reader_catalog

    assert not hasattr(reader_catalog, "render_page")
