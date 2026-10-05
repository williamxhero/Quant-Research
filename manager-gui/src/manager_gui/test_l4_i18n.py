"""Focused zh/en evidence for L4-T1 page-owned renderers."""

from __future__ import annotations

from manager_gui import FixtureState
from manager_gui.fixtures import build_fixture
from manager_gui.web.failure_grouping import build_failure_grouping_fixture, render_failure_grouping
from manager_gui.web.failure_patterns import render_failure_patterns
from manager_gui.web.i18n import Locale, Translator
from manager_gui.web.i18n.catalog import CATALOG, merge
from manager_gui.web.i18n.catalog.l4_memory import ENTRIES
from manager_gui.web.memory import render_memory

CATALOG_L4 = merge(CATALOG, ENTRIES)


def _translator(locale: Locale) -> Translator:
    return Translator(locale, strict=True, catalog=CATALOG_L4)


def test_memory_failure_and_derived_grouping_have_zh_and_en_page_copy() -> None:
    models = (
        build_fixture(FixtureState.COMPLETE, resource="memory"),
        build_fixture(FixtureState.COMPLETE, resource="failure_patterns"),
        build_failure_grouping_fixture("complete"),
    )
    zh = [
        render_memory(models[0], translator=_translator(Locale.ZH_CN)),
        render_failure_patterns(models[1], translator=_translator(Locale.ZH_CN)),
        render_failure_grouping(models[2], translator=_translator(Locale.ZH_CN)),
    ]
    en = [
        render_memory(models[0], translator=_translator(Locale.EN)),
        render_failure_patterns(models[1], translator=_translator(Locale.EN)),
        render_failure_grouping(models[2], translator=_translator(Locale.EN)),
    ]

    assert "研究记忆" in zh[0] and "正式研究记忆" in zh[0]
    assert "Memory-entry catalog" in en[0] and "Formal Research Memory" in en[0]
    assert "普通失败记录" in zh[1] and "派生失败模式" in zh[1]
    assert "Ordinary failure records" in en[1] and "Derived failure patterns" in en[1]
    assert "具名派生分组" in zh[2] and "不是属主事实" in zh[2]
    assert "Named Derived groups" in en[2] and "not an owner fact" in en[2]


def test_l4_catalog_is_additive_and_does_not_change_shared_registry() -> None:
    assert len(ENTRIES) >= 240
    assert "l4_memory.memory_title" not in CATALOG
    assert "l4_memory.memory_title" in CATALOG_L4
    assert all(
        key.startswith(("l4_memory.", "label.l4_memory_")) for key in ENTRIES
    )


def test_memory_catalog_merges_with_existing_lineage_and_failure_keys() -> None:
    from manager_gui.web.i18n import M

    sibling_entries = {
        "label.lineage_kind.candidate": M("候选证据", "Candidate evidence"),
        "label.failure_category.data_blocker": M("其他页面数据阻塞", "Other data blocker"),
        "label.decision.included": M("其他纳入", "Other inclusion"),
    }
    combined = merge(sibling_entries, ENTRIES)
    translator = Translator(Locale.EN, strict=True, catalog=combined)
    assert translator.label("lineage_kind", "candidate") == "Candidate evidence"
    assert translator.label("l4_memory_lineage_kind", "candidate") == "Candidate"
    assert translator.label("l4_memory_failure_category", "data_blocker") == "Data blocker"
    assert translator.label("l4_memory_decision", "included") == "Included"
