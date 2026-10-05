"""Positive and mutation tests for the shared, stdlib-only i18n harness."""

from __future__ import annotations

from manager_gui.testing.i18n import parse_html


def test_parser_extracts_visible_text_and_decodes_entities_once() -> None:
    document = parse_html(
        '<p>Alpha <strong>Beta &amp; &lt;x&gt;</strong> Gamma &amp;lt;y&amp;gt;</p>'
        '<p hidden>hidden</p><div aria-hidden="true"><p>decorative</p></div>'
        '<script>script text</script><style>style text</style>'
        '<template>template text</template><!-- comment text -->'
    )
    assert [surface.text for surface in document.visible_text] == [
        "Alpha ", "Beta & <x>", " Gamma &lt;y&gt;",
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
        ("aria-label", "Open & inspect"), ("title", "Details"),
        ("placeholder", "Search"), ("alt", "Graph"),
    ]


def test_parser_tracks_svg_table_and_heading_content() -> None:
    document = parse_html(
        '<h1>Main <span>title</span></h1><h2>Graph</h2>'
        '<svg role="img"><title>Lineage</title><text>node</text><path d="M0 0"/></svg>'
        '<table><caption>Evidence</caption><tr><th>ID</th></tr><tr><td>1</td></tr></table>'
    )
    assert [(node.tag, node.text()) for node in document.headings] == [
        ("h1", "Main title"), ("h2", "Graph"),
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
        '<label>Fixture<select><option>Complete</option></select></label>'
        '<input type="submit" value="Apply"><input type="image" alt="Open">'
    )
    assert [document.accessible_name(node) for node in document.select("input")] == [
        "Search", "Apply", "Open",
    ]
    assert document.accessible_name(document.select("select")[0]) == "FixtureComplete"


def test_accessible_name_does_not_use_svg_nodes_or_table_cells_as_container_name() -> None:
    document = parse_html('<svg><text>node</text></svg><table><tr><th>ID</th></tr></table>')
    assert document.accessible_name(document.svgs[0]) == ""
    assert document.accessible_name(document.tables[0]) == ""


def test_accessible_name_cycles_terminate() -> None:
    document = parse_html('<span id="a" aria-labelledby="b"></span><span id="b" aria-labelledby="a"></span>')
    assert document.accessible_name(document.ids["a"]) == ""


def test_head_title_is_inspectable_but_not_visible_body_text() -> None:
    document = parse_html('<html lang="en"><head><title>Page</title></head><body><h1>Body</h1></body></html>')
    assert [surface.text for surface in document.visible_text] == ["Body"]
    assert document.select("title")[0].text(include_hidden=True) == "Page"
    assert document.select("html")[0].attrs["lang"] == "en"
