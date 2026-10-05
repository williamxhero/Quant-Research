"""Positive and mutation tests for the shared, stdlib-only i18n harness."""

from __future__ import annotations

from html import escape

import pytest

from manager_gui import FixtureState, ManagerGUIApp
from manager_gui.testing.i18n import (
    FIXTURE_ENUM_VOCABULARY,
    MIGRATED_ROUTES,
    assert_accessible,
    assert_dom_equivalent,
    assert_enum_vocabulary,
    assert_fixture_vocabulary,
    assert_lang_propagation,
    assert_language_text,
    assert_owner_text_escaped,
    assert_pseudo_localized,
    assert_shared_shell_i18n,
    parse_html,
    render_pseudo_document,
)
from manager_gui.web.i18n import Locale, Translator
from manager_gui.web.navigation import NAVIGATION


def test_parser_extracts_visible_text_and_decodes_entities_once() -> None:
    document = parse_html(
        "<p>Alpha <strong>Beta &amp; &lt;x&gt;</strong> Gamma &amp;lt;y&amp;gt;</p>"
        '<p hidden>hidden</p><div aria-hidden="true"><p>decorative</p></div>'
        "<script>script text</script><style>style text</style>"
        "<template>template text</template><!-- comment text -->"
    )
    assert [surface.text for surface in document.visible_text] == [
        "Alpha ",
        "Beta & <x>",
        " Gamma &lt;y&gt;",
    ]
    assert document.select("p")[0].text() == "Alpha Beta & <x> Gamma &lt;y&gt;"
    assert document.select("p")[1].text() == ""
    assert document.select("p")[1].text(include_hidden=True) == "hidden"


def test_parser_extracts_translatable_attributes_without_machine_values() -> None:
    document = parse_html(
        '<a href="/?q=opaque" aria-label="Open &amp; inspect" title="Details">go</a>'
        '<input placeholder="Search" value="owner value"><img alt="Graph">'
        '<div hidden aria-label="Hidden label"></div>'
    )
    assert [(surface.attribute, surface.text) for surface in document.attributes] == [
        ("aria-label", "Open & inspect"),
        ("title", "Details"),
        ("placeholder", "Search"),
        ("alt", "Graph"),
    ]


def test_parser_tracks_svg_table_and_heading_content() -> None:
    document = parse_html(
        "<h1>Main <span>title</span></h1><h2>Graph</h2>"
        '<svg role="img"><title>Lineage</title><text>node</text><path d="M0 0"/></svg>'
        "<table><caption>Evidence</caption><tr><th>ID</th></tr><tr><td>1</td></tr></table>"
    )
    assert [(node.tag, node.text()) for node in document.headings] == [
        ("h1", "Main title"),
        ("h2", "Graph"),
    ]
    assert len(document.svgs) == len(document.tables) == 1
    assert document.accessible_name(document.svgs[0]) == "Lineage"
    assert document.accessible_name(document.tables[0]) == "Evidence"
    assert "node" in document.svgs[0].text()
    assert [node.text() for node in document.tables[0].descendants("th", "td")] == ["ID", "1"]


def test_void_and_self_closing_elements_do_not_capture_later_siblings() -> None:
    document = parse_html('<main><input name="q"><br><img alt="x"/><p>next</p></main>')
    assert all(node.parent is document.select("main")[0] for node in document.elements[1:])
    assert document.select("input")[0].children == []
    assert document.select("main")[0].text() == "next"


def test_accessible_names_resolve_forward_hidden_and_multiple_labelledby_references() -> None:
    document = parse_html(
        '<button aria-labelledby="verb subject" aria-label="fallback"></button>'
        '<span id="verb" hidden>Open</span><span id="subject">Evidence</span>'
    )
    assert document.accessible_name(document.select("button")[0]) == "Open Evidence"


def test_accessible_names_resolve_label_for_and_wrapping_label() -> None:
    document = parse_html(
        '<label for="q">Search</label><input id="q">'
        "<label>Fixture<select><option>Complete</option></select></label>"
        '<input type="submit" value="Apply"><input type="image" alt="Open">'
    )
    assert [document.accessible_name(node) for node in document.select("input")] == [
        "Search",
        "Apply",
        "Open",
    ]
    assert document.accessible_name(document.select("select")[0]) == "FixtureComplete"


def test_accessible_name_does_not_use_svg_nodes_or_table_cells_as_container_name() -> None:
    document = parse_html("<svg><text>node</text></svg><table><tr><th>ID</th></tr></table>")
    assert document.accessible_name(document.svgs[0]) == ""
    assert document.accessible_name(document.tables[0]) == ""


def test_accessible_name_cycles_terminate() -> None:
    document = parse_html(
        '<span id="a" aria-labelledby="b"></span><span id="b" aria-labelledby="a"></span>'
    )
    assert document.accessible_name(document.ids["a"]) == ""


def test_head_title_is_inspectable_but_not_visible_body_text() -> None:
    document = parse_html(
        '<html lang="en"><head><title>Page</title></head><body><h1>Body</h1></body></html>'
    )
    assert [surface.text for surface in document.visible_text] == ["Body"]
    assert document.select("title")[0].text(include_hidden=True) == "Page"
    assert document.select("html")[0].attrs["lang"] == "en"


def test_shared_shell_matrix_runs_all_routes_and_fixtures_in_both_locales() -> None:
    assert frozenset() == MIGRATED_ROUTES
    routes = tuple(item.view_id.value for item in NAVIGATION)
    assert len(routes) == 17
    count = 0
    for fixture in FixtureState:
        app = ManagerGUIApp(default_fixture=fixture)
        for route in routes:
            url = f"/?view={route}&fixture={fixture.value}&panel=events&tag=a&tag=b&tag="
            assert_shared_shell_i18n(
                app.render(url),
                app.render(url + "&lang=en"),
                route=route,
                source_url=url + "&lang=en",
            )
            for locale_url in (url, url + "&lang=en"):
                assert_pseudo_localized(render_pseudo_document(app, locale_url), route=route)
            count += 2
    assert count == 374


def test_dom_skeleton_audit_rejects_added_or_missing_elements() -> None:
    assert_dom_equivalent(
        '<html><body><h1>中文</h1><a href="/?lang=zh-CN">中文</a></body></html>',
        '<html><body><h1>English</h1><a href="/?lang=en">English</a></body></html>',
    )
    with pytest.raises(AssertionError, match="skeleton"):
        assert_dom_equivalent(
            "<html><body><h1>中文</h1></body></html>",
            "<html><body><h1>English</h1><button>Extra</button></body></html>",
        )


def test_pseudo_locale_and_language_audits_identify_untranslated_text() -> None:
    pseudo_document = render_pseudo_document(
        ManagerGUIApp(default_fixture=FixtureState.COMPLETE),
        "/?view=atlas&fixture=complete&panel=events",
    )
    assert_pseudo_localized(pseudo_document, route="atlas")
    translated = Translator(Locale.EN, pseudo=True).t("shell.read_only")
    assert_pseudo_localized(f"<html><body><p>{translated}</p></body></html>")
    with pytest.raises(AssertionError, match="pseudo-locale leak"):
        assert_pseudo_localized("<html><body><p>⟦已翻译⟧ leaked</p></body></html>")
    with pytest.raises(AssertionError, match="Chinese Latin leak"):
        assert_language_text("<html><body><p>中文 badword</p></body></html>", Locale.ZH_CN)
    with pytest.raises(AssertionError, match="English Han leak"):
        assert_language_text("<html><body><p>English 中文</p></body></html>", Locale.EN)
    assert_language_text("<html><body><p>Manager GUI JSON</p></body></html>", Locale.ZH_CN)
    assert_language_text(
        "<html><body><p>English 中文 owner</p></body></html>", Locale.EN, owner_text=("中文 owner",)
    )


def test_link_form_accessibility_and_vocabulary_audits_reject_mutations() -> None:
    with pytest.raises(AssertionError, match="lang mismatch"):
        assert_lang_propagation(
            '<html lang="en"><body><a href="/?view=atlas">Atlas</a></body></html>', Locale.EN
        )
    with pytest.raises(AssertionError, match="accessible name"):
        assert_accessible("<html><body><h1>Page</h1><button></button></body></html>")
    with pytest.raises(AssertionError, match="enum vocabulary"):
        assert_enum_vocabulary("status", ("missing_value",))
    assert_fixture_vocabulary(
        "<html><body><form><input type=\"hidden\" name=\"fixture\" "
        "value=\"complete\"></form></body></html>"
    )
    assert "complete" in FIXTURE_ENUM_VOCABULARY


def test_owner_text_is_escaped_exactly_once() -> None:
    value = 'owner <note> "quoted" & value'
    markup = f'<p class="status-source-note">{escape(value, quote=True)}</p>'
    assert_owner_text_escaped(markup, value)
    with pytest.raises(AssertionError, match="owner text"):
        assert_owner_text_escaped(f"<p>{value}</p>", value)


def test_default_and_explicit_english_shell_have_expected_locale_and_translator() -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    zh = parse_html(app.render("/?view=atlas&fixture=complete"))
    en = parse_html(app.render("/?view=atlas&fixture=complete&lang=en"))
    assert zh.html_lang == Locale.ZH_CN.value
    assert en.html_lang == Locale.EN.value
    assert Translator(Locale.EN).t("shell.read_only") == "READ ONLY"


def test_invalid_locale_falls_back_and_is_removed_without_losing_url_state() -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    raw = "/?view=search&fixture=complete&lang=fr&q=&tag=a&tag=&panel=events"
    state = app.request_state(raw)
    assert state.lang is None
    assert state.locale is Locale.ZH_CN
    document = parse_html(app.render(raw))
    assert document.html_lang == Locale.ZH_CN.value
    assert all(
        "lang=fr" not in (link.attrs.get("href") or "")
        for link in document.links
    )
    switcher = [
        link
        for link in document.links
        if link.attrs.get("data-language-switcher") is not None
        or link.attrs.get("hreflang") == Locale.EN.value
    ]
    english = next(link for link in document.links if link.attrs.get("hreflang") == "en")
    assert "lang=en" in (english.attrs.get("href") or "")
    assert "tag=a" in (english.attrs.get("href") or "")
    assert "tag=" in (english.attrs.get("href") or "")
    assert "panel=events" in (english.attrs.get("href") or "")
    assert switcher

    english_default = ManagerGUIApp(
        default_fixture=FixtureState.COMPLETE, default_locale=Locale.EN
    )
    fallback = parse_html(english_default.render("/?view=atlas&lang=fr&tag=x"))
    assert fallback.html_lang == Locale.EN.value
    assert all("lang=fr" not in (link.attrs.get("href") or "") for link in fallback.links)
