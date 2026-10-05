"""Focused tests for the Manager GUI i18n core package (locale, glossary, translator)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import pytest

import manager_gui.web as web
from manager_gui.web.i18n import (
    DEFAULT_LOCALE,
    LANG_PARAM,
    PSEUDO_CLOSE,
    PSEUDO_OPEN,
    TERMS,
    Locale,
    M,
    Term,
    TranslationError,
    Translator,
    resolve_locale,
    source_text,
    with_lang,
)
from manager_gui.web.i18n import glossary as glossary_module
from manager_gui.web.i18n.catalog import REGISTRY, CatalogError, CatalogRegistry, merge, register
from manager_gui.web.i18n.translator import label_key, validate_entry

CATALOG: Mapping[str, M] = merge(
    {
        "common.title": M("研究总览", "Research overview"),
        "common.greeting": M("你好，{name}！", "Hello, {name}!", note="greeting with a name"),
        "common.braces": M("字面量 {{x}}", "literal {{x}}"),
        "common.term_zh": M(
            "查看{term:artifact}和{term:lineage}",
            "View {term:artifact} and {term:lineage}",
        ),
        "common.term_html": M("<b>{term:known}</b>：{name}", "<b>{term:known}</b>: {name}"),
        "common.items": M(
            "共 {n} 项",
            {"one": "{n} item", "other": "{n} items"},
        ),
        "common.items_in": M(
            "{scope}中共 {n} 项",
            {"one": "{n} item in {scope}", "other": "{n} items in {scope}"},
        ),
        "label.status.ready": M("就绪", "Ready"),
        "label.status.blocked": M("已阻塞", "Blocked"),
        "label.status.mixed": M("A & B", "A & B"),
        "common.html_link": M(
            '<a href="{href}">{text}</a>',
            '<a href="{href}">{text}</a>',
        ),
    }
)


def _translator(locale: Locale = Locale.EN, **options: Any) -> Translator:
    catalog = options.pop("catalog", CATALOG)
    return Translator(locale, catalog=catalog, **options)


# --- Locale and resolve_locale ------------------------------------------------------


def test_locale_values_and_default() -> None:
    assert [item.value for item in Locale] == ["zh-CN", "en"]
    assert DEFAULT_LOCALE is Locale.ZH_CN
    assert LANG_PARAM == "lang"
    assert Locale.ZH_CN.html_lang == "zh-CN"
    assert Locale.EN.html_lang == "en"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("zh-CN", Locale.ZH_CN),
        ("zh", Locale.ZH_CN),
        ("zh_CN", Locale.ZH_CN),
        ("zh-Hans", Locale.ZH_CN),
        ("ZH-cn", Locale.ZH_CN),
        ("ZH_hans", Locale.ZH_CN),
        ("en", Locale.EN),
        ("EN", Locale.EN),
        ("en-US", Locale.EN),
        ("en-GB", Locale.EN),
        ("EN-gb", Locale.EN),
        (" en ", Locale.EN),
        (Locale.EN, Locale.EN),
        (Locale.ZH_CN, Locale.ZH_CN),
    ],
)
def test_resolve_locale_accepts_aliases_case_insensitively(
    value: str, expected: Locale
) -> None:
    assert resolve_locale(value) is expected


@pytest.mark.parametrize(
    "value",
    [None, "", "  ", "fr", "zh-TW", "zh-Hant", "en-AU", "english", "中文", "pseudo", "pseudo-en"],
)
def test_resolve_locale_returns_none_for_unspecified_or_invalid(value: str | None) -> None:
    assert resolve_locale(value) is None


def test_resolve_locale_first_repeated_value_wins() -> None:
    assert resolve_locale(["en", "zh"]) is Locale.EN
    assert resolve_locale(("ZH_CN", "en")) is Locale.ZH_CN
    # The first value decides even when it is invalid.
    assert resolve_locale(["fr", "en"]) is None
    assert resolve_locale(["", "en"]) is None
    assert resolve_locale([]) is None
    assert resolve_locale(iter(["en-US", "zh"])) is Locale.EN


def test_pseudo_locale_is_not_reachable_through_resolve_locale() -> None:
    reachable = {resolve_locale(item.value) for item in Locale}
    assert reachable == set(Locale)
    assert len(Locale) == 2
    for spelling in ("pseudo", "PSEUDO", "pseudo-locale", "x-pseudo", "qps", "qps-ploc", "⟦en⟧"):
        assert resolve_locale(spelling) is None
        assert resolve_locale([spelling, "en"]) is None
    with pytest.raises(ValueError, match="pseudo"):
        Translator("pseudo")  # type: ignore[arg-type]


# --- with_lang -------------------------------------------------------------------------


def test_with_lang_appends_and_keeps_every_other_parameter_verbatim() -> None:
    url = "/?view=search&q=&tag=a&tag=b&tag=&page=2"
    assert with_lang(url, Locale.EN) == url + "&lang=en"
    assert with_lang("/", Locale.ZH_CN) == "/?lang=zh-CN"
    assert with_lang("/?", Locale.EN) == "/?lang=en"
    assert with_lang("/atlas?a=1#frag", Locale.EN) == "/atlas?a=1&lang=en#frag"


def test_with_lang_keeps_duplicates_blanks_and_order() -> None:
    parsed = with_lang("/?z=1&a=&z=2&a=&m=x", Locale.EN)
    assert parsed == "/?z=1&a=&z=2&a=&m=x&lang=en"


def test_with_lang_collapses_existing_lang_at_first_position() -> None:
    assert with_lang("/?lang=en&view=a", Locale.ZH_CN) == "/?lang=zh-CN&view=a"
    assert with_lang("/?view=a&lang=fr&x=1&lang=en&lang=", Locale.EN) == "/?view=a&lang=en&x=1"
    assert with_lang("/?lang=&view=a", Locale.EN) == "/?lang=en&view=a"
    once = with_lang("/?a=1&lang=zh&lang=en", Locale.EN)
    assert with_lang(once, Locale.EN) == once


def test_with_lang_none_strips_every_lang() -> None:
    assert with_lang("/?lang=en&view=a&lang=zh", None) == "/?view=a"
    assert with_lang("/?lang=en", None) == "/"
    assert with_lang("/?view=a&lang=&x=&x=1", None) == "/?view=a&x=&x=1"
    assert with_lang("/?view=a#top&lang=en", None) == "/?view=a#top&lang=en"


def test_with_lang_none_without_lang_returns_the_url_unchanged() -> None:
    for url in ("/", "/?", "/?view=a&q=a%20b&flag", "fixture://x/y?q=1"):
        assert with_lang(url, None) == url


def test_with_lang_only_touches_the_lang_parameter() -> None:
    assert with_lang("/?language=x&xlang=y&Lang=z", Locale.EN) == (
        "/?language=x&xlang=y&Lang=z&lang=en"
    )


def test_with_lang_requires_a_canonical_locale() -> None:
    with pytest.raises(ValueError):
        with_lang("/", "zh")  # type: ignore[arg-type]
    assert with_lang("/", "en") == "/?lang=en"  # type: ignore[arg-type]


# --- glossary --------------------------------------------------------------------------


def test_frozen_terms_are_present_and_immutable() -> None:
    assert {"artifact", "lineage", "evidence_ledger", "known", "fixture"} <= set(TERMS)
    assert len(TERMS) >= 60
    assert TERMS["artifact"].zh == "制品"
    assert TERMS["artifact"].forbidden_zh == ("产物",)
    assert TERMS["known"].zh == "已记录"
    for term in TERMS.values():
        assert term.id and term.en and term.zh and term.zh_short and term.note
        assert isinstance(term.forbidden_zh, tuple)
        assert all(spelling not in term.zh for spelling in term.forbidden_zh)
    with pytest.raises(TypeError):
        TERMS["x"] = TERMS["artifact"]  # type: ignore[index]
    with pytest.raises(AttributeError):
        TERMS["artifact"].zh = "产物"  # type: ignore[misc]


def test_term_is_a_frozen_record_and_registry_rejects_duplicate_ids() -> None:
    term = Term("any-id", "en", "中", "短", "说明", ("坏",))
    assert (term.id, term.zh_short, term.note, term.forbidden_zh) == (
        "any-id", "短", "说明", ("坏",)
    )
    with pytest.raises(AttributeError):
        term.zh = "改"  # type: ignore[misc]
    with pytest.raises(ValueError, match="duplicate"):
        glossary_module._registry([term, term])


# --- M and registration ----------------------------------------------------------------


def test_m_requires_both_languages_structurally() -> None:
    entry = M(zh="中", en="en")
    assert (entry.zh, entry.en, entry.note) == ("中", "en", None)
    with pytest.raises(TypeError):
        M(zh="只有中文")  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        M(en="english only")  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        M()  # type: ignore[call-arg]
    with pytest.raises(AttributeError):
        entry.zh = "改"  # type: ignore[misc]


def test_m_rejects_wrong_value_types() -> None:
    with pytest.raises(TranslationError):
        M(1, "en")  # type: ignore[arg-type]
    with pytest.raises(TranslationError):
        M("中", 3)  # type: ignore[arg-type]
    with pytest.raises(TranslationError):
        M("中", "en", note=3)  # type: ignore[arg-type]


def test_m_plural_table_is_copied_and_equal_by_value() -> None:
    plural = {"one": "{n} item", "other": "{n} items"}
    entry = M("{n} 项", plural)
    plural["other"] = "changed"
    assert cast(Mapping[str, str], entry.en)["other"] == "{n} items"
    assert entry.is_plural
    assert entry == M("{n} 项", {"one": "{n} item", "other": "{n} items"})
    assert not M("中", "en").is_plural


def test_registration_rejects_placeholder_mismatch_between_languages() -> None:
    registry = CatalogRegistry()
    with pytest.raises(CatalogError, match="placeholders differ"):
        registry.register({"a.b": M("你好，{name}", "Hello")})
    with pytest.raises(CatalogError, match="placeholders differ"):
        registry.register({"a.b": M("你好", "Hello, {name}")})
    with pytest.raises(CatalogError, match="placeholders differ"):
        registry.register({"a.b": M("你好，{name}", "Hello, {user}")})
    assert dict(registry.entries) == {}
    with pytest.raises(TranslationError):  # CatalogError is a TranslationError
        merge({"a.b": M("{n} 项", "{m} items")})


def test_registration_checks_every_plural_form() -> None:
    with pytest.raises(TranslationError, match=r"en\.one"):
        validate_entry("a.b", M("共 {n} 项", {"one": "one item", "other": "{n} items"}))
    with pytest.raises(TranslationError, match="exactly 'one' and 'other'"):
        validate_entry("a.b", M("共 {n} 项", {"other": "{n} items"}))
    with pytest.raises(TranslationError, match="exactly 'one' and 'other'"):
        validate_entry("a.b", M("共 {n} 项", {"one": "{n}", "other": "{n}", "few": "{n}"}))
    validate_entry("a.b", M("共 {n} 项", {"one": "{n} item", "other": "{n} items"}))


@pytest.mark.parametrize(
    "zh",
    [
        "", "   ", "半个 {", "半个 }", "{ name}", "{0}", "{}", "{name!r}",
        "{name:>4}", "{a.b}", "{term}",
    ],
)
def test_registration_rejects_malformed_text(zh: str) -> None:
    with pytest.raises(TranslationError):
        validate_entry("a.b", M(zh, "en"))
    with pytest.raises(TranslationError):
        validate_entry("a.b", M("中", zh))


@pytest.mark.parametrize("key", ["", " a", "a b", "a{b}", "a\nb", "a}"])
def test_registration_rejects_invalid_keys(key: str) -> None:
    with pytest.raises(TranslationError, match="invalid catalog key"):
        validate_entry(key, M("中", "en"))


def test_registration_rejects_non_entries() -> None:
    with pytest.raises(TranslationError, match="must be an M"):
        validate_entry("a.b", ("中", "en"))  # type: ignore[arg-type]


def test_registration_rejects_unknown_terms_and_accepts_known_ones() -> None:
    with pytest.raises(TranslationError, match="no_such_term"):
        validate_entry("a.b", M("见{term:no_such_term}", "see"))
    with pytest.raises(TranslationError, match="no_such_term"):
        validate_entry("a.b", M("见", "see {term:no_such_term}"))
    validate_entry("a.b", M("见{term:artifact}", "see {term:artifact}"))


def test_registration_rejects_label_entries_with_placeholders_or_plurals() -> None:
    with pytest.raises(TranslationError, match="label entries"):
        validate_entry("label.status.x", M("{n}", "{n}"))
    with pytest.raises(TranslationError, match="label entries"):
        validate_entry("label.status.x", M("{n}", {"one": "{n}", "other": "{n}"}))
    validate_entry("label.status.x", M("见{term:artifact}", "see {term:artifact}"))


def test_registry_is_atomic_append_only_and_read_only() -> None:
    registry = CatalogRegistry()
    registry.register({"a.one": M("一", "one")})
    with pytest.raises(CatalogError, match="duplicate catalog key"):
        registry.register({"a.two": M("二", "two"), "a.one": M("一", "one")})
    assert set(registry.entries) == {"a.one"}  # the failed batch left nothing behind
    with pytest.raises(CatalogError, match=r"invalid|placeholders"):
        registry.register({"a.three": M("三", "three"), "a.bad": M("{x}", "bad")})
    assert set(registry.entries) == {"a.one"}
    with pytest.raises(TypeError):
        registry.entries["a.hack"] = M("黑", "hack")  # type: ignore[index]

    view = registry.entries
    registry.register({"a.late": M("晚", "late")})
    assert "a.late" in view  # the view is live

    registry.register("a.single", M("单个", "single"))
    assert registry.entries["a.single"].en == "single"
    with pytest.raises(CatalogError, match="missing message"):
        registry.register("a.missing")
    with pytest.raises(CatalogError, match="only accepted"):
        registry.register({"a.extra": M("额外", "extra")}, M("多余", "extra"))

    translator = Translator(Locale.EN, strict=True, catalog=registry.entries)
    assert translator.t("a.late") == "late"


def test_merge_validates_combines_and_rejects_duplicates() -> None:
    merged = merge({"a.one": M("一", "one")}, {"a.two": M("二", "two")})
    assert list(merged) == ["a.one", "a.two"]
    assert merge() == {}
    with pytest.raises(CatalogError, match="duplicate catalog key"):
        merge({"a.one": M("一", "one")}, {"a.one": M("一", "one")})


def test_default_registry_contains_shared_shell_catalogs_and_keeps_unknown_keys_lenient() -> None:
    assert {
        "label.status.known",
        "status.explanation.known",
        "interaction.copy_reference",
        "client.copy_success",
    } <= set(REGISTRY.entries)
    before = len(REGISTRY.entries)
    register({})
    assert len(REGISTRY.entries) == before
    assert Translator().t("any.key") == "any.key"


def test_module_level_register_feeds_default_translators() -> None:
    import manager_gui.web.i18n.catalog as catalog_module

    fresh = CatalogRegistry()
    original = catalog_module.REGISTRY
    catalog_module.REGISTRY = fresh
    try:
        catalog_module.register({"zz.only": M("仅此", "only this")})
        assert Translator(Locale.EN, strict=True).t("zz.only") == "only this"
        assert Translator(Locale.ZH_CN, strict=True).t("zz.only") == "仅此"
    finally:
        catalog_module.REGISTRY = original
    assert "zz.only" not in original.entries


# --- Translator: t, count, html --------------------------------------------------------


def test_t_returns_the_locale_text_with_named_parameters() -> None:
    assert _translator(Locale.EN).t("common.title") == "Research overview"
    assert _translator(Locale.ZH_CN).t("common.title") == "研究总览"
    assert _translator(Locale.EN).t("common.greeting", name="Ann") == "Hello, Ann!"
    assert _translator(Locale.ZH_CN).t("common.greeting", name="安") == "你好，安！"
    # t() is plain text: the caller escapes, so nothing is escaped here.
    assert _translator().t("common.greeting", name="<i>&</i>") == "Hello, <i>&</i>!"


def test_parameters_are_substituted_once_and_never_reparsed() -> None:
    assert _translator().t("common.greeting", name="{name}") == "Hello, {name}!"
    assert _translator().t("common.greeting", name="{term:artifact}") == "Hello, {term:artifact}!"
    assert _translator().t("common.greeting", name=7) == "Hello, 7!"


def test_double_braces_are_literal_braces() -> None:
    assert _translator(Locale.EN).t("common.braces") == "literal {x}"
    assert _translator(Locale.ZH_CN).t("common.braces") == "字面量 {x}"


def test_term_references_expand_in_the_current_language() -> None:
    assert _translator(Locale.ZH_CN).t("common.term_zh") == "查看制品和谱系"
    assert _translator(Locale.ZH_CN).html("common.term_html", name="x") == "<b>已记录</b>：x"
    assert _translator(Locale.EN).html("common.term_html", name="x") == "<b>Known</b>: x"


def test_term_text_is_escaped_in_html_templates_only() -> None:
    custom = Term("amp_term", "R&D <lab>", "研发 & <室>")
    original = glossary_module.TERMS
    from manager_gui.web.i18n import translator as translator_module

    patched = {**original, "amp_term": custom}
    translator_module.TERMS = patched  # type: ignore[assignment]
    try:
        catalog = merge({"a.t": M("见{term:amp_term}", "see {term:amp_term}")})
        english = Translator(Locale.EN, catalog=catalog)
        chinese = Translator(Locale.ZH_CN, catalog=catalog)
        assert english.t("a.t") == "see R&D <lab>"
        assert english.html("a.t") == "see R&amp;D &lt;lab&gt;"
        assert chinese.html("a.t") == "见研发 &amp; &lt;室&gt;"
    finally:
        translator_module.TERMS = glossary_module.TERMS


def test_unknown_term_in_an_unvalidated_catalog_raises_in_every_mode() -> None:
    raw: Mapping[str, M] = {"a.t": M("见{term:no_such_term}", "see {term:no_such_term}")}
    for strict in (True, False):
        for locale in Locale:
            with pytest.raises(TranslationError, match="no_such_term"):
                Translator(locale, strict=strict, catalog=raw).t("a.t")


def test_html_trusts_the_template_and_escapes_every_parameter() -> None:
    html = _translator().html(
        "common.html_link", href='/?q="a"&x=<1>', text="<script>alert(1)</script> & {x}"
    )
    assert html == (
        '<a href="/?q=&quot;a&quot;&amp;x=&lt;1&gt;">'
        "&lt;script&gt;alert(1)&lt;/script&gt; &amp; {x}</a>"
    )
    assert _translator().html("common.title") == "Research overview"


def test_count_selects_english_plural_forms_and_provides_n() -> None:
    english = _translator(Locale.EN, strict=True)
    assert english.count("common.items", 0) == "0 items"
    assert english.count("common.items", 1) == "1 item"
    assert english.count("common.items", 2) == "2 items"
    assert english.count("common.items", 101) == "101 items"
    assert english.count("common.items", -1) == "-1 items"
    assert english.count("common.items_in", 1, scope="Atlas") == "1 item in Atlas"
    assert english.count("common.items_in", 5, scope="Atlas") == "5 items in Atlas"


def test_count_uses_a_single_form_in_chinese() -> None:
    chinese = _translator(Locale.ZH_CN, strict=True)
    assert [chinese.count("common.items", n) for n in (0, 1, 2)] == [
        "共 0 项", "共 1 项", "共 2 项"
    ]
    assert chinese.count("common.items_in", 1, scope="总览") == "总览中共 1 项"


def test_count_reserves_n_and_works_for_non_plural_entries() -> None:
    with pytest.raises(TranslationError, match="supplies"):
        _translator().count("common.items", 1, n=2)
    assert _translator(strict=True).count("common.title", 3) == "Research overview"


def test_plural_entry_without_count() -> None:
    assert _translator(Locale.EN).t("common.items", n=1) == "1 items"  # lenient uses "other"
    assert _translator(Locale.ZH_CN).t("common.items", n=1) == "共 1 项"
    for locale in Locale:
        with pytest.raises(TranslationError, match="count"):
            _translator(locale, strict=True).t("common.items", n=1)
        with pytest.raises(TranslationError, match="count"):
            _translator(locale, strict=True).html("common.items")
    assert _translator(Locale.EN, strict=True).html("common.items", n=1) == "1 item"
    assert _translator(Locale.EN, strict=True).html("common.items", n=2) == "2 items"


def test_key_and_self_parameters_do_not_collide_with_method_arguments() -> None:
    catalog = merge({"a.key": M("{key}/{self}", "{key}/{self}")})
    assert Translator(Locale.EN, catalog=catalog).t("a.key", key="k", self="s") == "k/s"


# --- strict and lenient lookup ---------------------------------------------------------


def test_strict_mode_raises_on_missing_key_and_missing_parameter() -> None:
    strict = _translator(strict=True)
    with pytest.raises(TranslationError, match="missing catalog key"):
        strict.t("no.such.key")
    with pytest.raises(TranslationError, match="missing catalog key"):
        strict.html("no.such.key")
    with pytest.raises(TranslationError, match="missing catalog key"):
        strict.count("no.such.key", 2)
    with pytest.raises(TranslationError, match="name"):
        strict.t("common.greeting")
    assert strict.t("common.greeting", name="x", unused="ignored") == "Hello, x!"


def test_lenient_mode_never_raises_for_lookups() -> None:
    lenient = _translator()
    assert lenient.t("no.such.key") == "no.such.key"
    assert lenient.html("no.<such>.key") == "no.&lt;such&gt;.key"
    assert lenient.count("no.such.key", 2) == "no.such.key"
    assert lenient.t("common.greeting") == "Hello, {name}!"
    assert Translator().t("no.such.key") == "no.such.key"
    assert not lenient.strict


def test_lenient_fallback_chain_is_requested_then_zh_then_en_then_key() -> None:
    # Validated entries are always bilingual, so build blanks around validation.
    raw: Mapping[str, M] = {
        "blank.en": M("仅中文", ""),
        "blank.zh": M("", "English only"),
        "blank.both": M("", ""),
        "blank.plural": M("共 {n} 项", {"one": "", "other": ""}),
    }
    english = Translator(Locale.EN, catalog=raw)
    chinese = Translator(Locale.ZH_CN, catalog=raw)
    assert english.t("blank.en") == "仅中文"  # en -> zh
    assert chinese.t("blank.zh") == "English only"  # zh -> en
    assert english.t("blank.zh") == "English only"
    assert english.t("blank.both") == "blank.both"  # -> key
    assert chinese.t("blank.both") == "blank.both"
    assert english.count("blank.plural", 2) == "共 2 项"
    assert english.t("missing") == "missing"
    # Strict mode never substitutes another language.
    for locale, key in ((Locale.EN, "blank.en"), (Locale.ZH_CN, "blank.zh")):
        with pytest.raises(TranslationError, match="no "):
            Translator(locale, strict=True, catalog=raw).t(key)


def test_fallback_text_expands_terms_in_the_language_it_came_from() -> None:
    raw: Mapping[str, M] = {"a.t": M("见{term:artifact}", "")}
    assert Translator(Locale.EN, catalog=raw).t("a.t") == "见制品"


# --- label -----------------------------------------------------------------------------


def test_label_renders_known_values_in_the_current_language() -> None:
    assert _translator(Locale.EN).label("status", "ready") == "Ready"
    assert _translator(Locale.ZH_CN).label("status", "ready") == "就绪"
    assert _translator(Locale.ZH_CN).label("status", "blocked") == "已阻塞"
    assert _translator(Locale.EN).label("status", "mixed") == "A &amp; B"  # HTML-safe
    assert label_key("status", "ready") == "label.status.ready"


@pytest.mark.parametrize("locale", list(Locale))
@pytest.mark.parametrize(
    ("value", "rendered"),
    [
        ("strategy_genome", "<code>strategy_genome</code>"),
        ("evidence-record", "<code>evidence-record</code>"),
        ("Already Capitalised", "<code>Already Capitalised</code>"),
        ("a<b>&c", "<code>a&lt;b&gt;&amp;c</code>"),
        ("{x}", "<code>{x}</code>"),
        ("", "<code></code>"),
    ],
)
def test_label_renders_unknown_values_verbatim_in_code_never_title_cased(
    locale: Locale, value: str, rendered: str
) -> None:
    for strict in (True, False):
        assert _translator(locale, strict=strict).label("status", value) == rendered
        assert _translator(locale, strict=strict).label("never_registered", value) == rendered


def test_label_with_an_unregistered_domain_is_an_unknown_code_value() -> None:
    assert _translator(strict=True).label("Bad.Domain", "x") == "<code>x</code>"
    assert _translator().label("Bad.Domain", "x") == "<code>x</code>"


# --- pseudo-locale ---------------------------------------------------------------------


def test_pseudo_locale_wraps_and_lengthens_catalog_text_only() -> None:
    pseudo = _translator(Locale.EN, pseudo=True, strict=True)
    title = pseudo.t("common.title")
    assert title.startswith(PSEUDO_OPEN) and title.endswith(PSEUDO_CLOSE)
    assert "Research overview" in title
    assert len(title) > len("Research overview") * 1.3
    assert pseudo.t("common.greeting", name="Ann").startswith(f"{PSEUDO_OPEN}Hello, Ann!")
    assert pseudo.count("common.items", 1).startswith(f"{PSEUDO_OPEN}1 item")
    assert pseudo.html("common.term_html", name="x").startswith(f"{PSEUDO_OPEN}<b>Known</b>")
    assert pseudo.label("status", "ready").startswith(f"{PSEUDO_OPEN}Ready")
    zh_title = _translator(Locale.ZH_CN, pseudo=True).t("common.title")
    assert zh_title.startswith(f"{PSEUDO_OPEN}研究总览") and zh_title.endswith(PSEUDO_CLOSE)
    assert len(zh_title) > len("研究总览") + 2


def test_pseudo_locale_leaves_owner_data_and_missing_keys_visibly_unwrapped() -> None:
    pseudo = _translator(Locale.EN, pseudo=True)
    assert pseudo.source_text("<b>x</b>") == "&lt;b&gt;x&lt;/b&gt;"
    assert pseudo.label("status", "unknown_value") == "<code>unknown_value</code>"
    assert pseudo.t("no.such.key") == "no.such.key"
    assert pseudo.join(["a", "b"]) == "a, b"


def test_pseudo_locale_is_only_an_explicit_constructor_flag() -> None:
    assert not Translator().pseudo
    assert not Translator(Locale.EN).pseudo
    assert Translator(pseudo=True).pseudo
    assert Translator(Locale.EN, pseudo=True).html_lang == "en"
    assert Translator(pseudo=True).locale is DEFAULT_LOCALE


# --- source_text, join, immutability ---------------------------------------------------


def test_source_text_escapes_owner_text_exactly_once() -> None:
    owner = '<b>&"{x}"</b>'
    expected = "&lt;b&gt;&amp;&quot;{x}&quot;&lt;/b&gt;"
    assert source_text(owner) == expected
    assert _translator().source_text(owner) == expected
    assert _translator(Locale.ZH_CN).source_text(owner) == expected
    assert source_text("it's 中文") == "it&#x27;s 中文"
    assert source_text("") == ""
    assert source_text("&amp;") == "&amp;amp;"  # input is raw text, so it is escaped as such


def test_join_uses_the_locale_separator() -> None:
    assert _translator(Locale.ZH_CN).join(["甲", "乙", "丙"]) == "甲、乙、丙"
    assert _translator(Locale.EN).join(["a", "b", "c"]) == "a, b, c"
    assert _translator(Locale.EN).join(iter(["only"])) == "only"
    assert _translator(Locale.EN).join([]) == ""


def test_translator_properties_and_defaults() -> None:
    default = Translator()
    assert default.locale is Locale.ZH_CN and default.html_lang == "zh-CN"
    assert not default.strict and not default.pseudo
    english = Translator(Locale.EN, strict=True)
    assert english.locale is Locale.EN and english.html_lang == "en" and english.strict
    assert Translator("en").locale is Locale.EN
    assert "en" in repr(english) and "strict=True" in repr(english)


def test_translator_is_immutable() -> None:
    translator = _translator()
    for name, value in (
        ("locale", Locale.ZH_CN),
        ("strict", True),
        ("pseudo", True),
        ("_locale", Locale.ZH_CN),
        ("_catalog", {}),
        ("extra", 1),
    ):
        with pytest.raises(AttributeError):
            setattr(translator, name, value)
    with pytest.raises(AttributeError):
        del translator._locale
    assert translator.locale is Locale.EN


# --- package surface -------------------------------------------------------------------


def test_web_package_exports_the_i18n_entry_points() -> None:
    assert web.Locale is Locale
    assert web.Translator is Translator
    assert web.DEFAULT_LOCALE is DEFAULT_LOCALE
    assert web.resolve_locale is resolve_locale
    assert web.with_lang is with_lang
    for name in ("Locale", "Translator", "DEFAULT_LOCALE", "resolve_locale", "with_lang"):
        assert name in web.__all__
    assert len(web.__all__) == len(set(web.__all__))


def test_chinese_catalog_text_may_use_full_width_punctuation() -> None:
    # Exercises the ruff `allowed-confusables` setting: ，：；（）！？、 in string literals.
    entry = M("成功，失败：未知；（括号）！真的？甲、乙", "ok")
    validate_entry("zh.punctuation", entry)
    assert _translator(Locale.ZH_CN, catalog=merge({"zh.punctuation": entry})).t(
        "zh.punctuation"
    ) == ("成功，失败：未知；（括号）！真的？甲、乙")
