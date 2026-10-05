"""Standard-library DOM inspection and assertions for Manager GUI i18n tests.

This is a static HTML harness, not a browser: visibility follows HTML ``hidden``
and ``aria-hidden`` plus script/style/template exclusion, not computed CSS.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from functools import partial
from html import escape
from html.parser import HTMLParser
from unittest.mock import patch
from urllib.parse import parse_qsl, urlencode, urlsplit

from manager_gui.fixtures import FixtureState
from manager_gui.models import ReadModelStatus
from manager_gui.web.app import ManagerGUIApp
from manager_gui.web.i18n import Locale, M, Translator
from manager_gui.web.i18n.catalog import REGISTRY
from manager_gui.web.status import DisplayState

_VOID_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
_NON_TEXT_TAGS = frozenset({"script", "style", "template"})
TEXT_ATTRIBUTES = ("aria-label", "title", "placeholder", "alt")


@dataclass(eq=False, slots=True)
class Element:
    """One parsed element; attributes and text have been entity-decoded once."""

    tag: str
    attrs: dict[str, str | None] = field(default_factory=dict)
    children: list[Element | str] = field(default_factory=list)
    parent: Element | None = field(default=None, repr=False)

    @property
    def classes(self) -> frozenset[str]:
        return frozenset((self.attrs.get("class") or "").split())

    def ancestors(self) -> Iterator[Element]:
        current: Element | None = self
        while current is not None:
            yield current
            current = current.parent

    @property
    def hidden(self) -> bool:
        return any(
            "hidden" in node.attrs
            or node.attrs.get("aria-hidden") == "true"
            or node.tag in _NON_TEXT_TAGS
            or node.tag == "head"
            for node in self.ancestors()
        )

    def text(self, *, include_hidden: bool = False) -> str:
        """Descendant text without inventing spaces between inline elements."""

        if self.tag in _NON_TEXT_TAGS or (self.hidden and not include_hidden):
            return ""
        return "".join(
            child if isinstance(child, str) else child.text(include_hidden=include_hidden)
            for child in self.children
        )

    def descendants(self, *tags: str) -> Iterator[Element]:
        for child in self.children:
            if isinstance(child, Element):
                if not tags or child.tag in tags:
                    yield child
                yield from child.descendants(*tags)

    @property
    def location(self) -> str:
        suffix = f"#{self.attrs['id']}" if self.attrs.get("id") else ""
        return self.tag + suffix


@dataclass(frozen=True, slots=True)
class TextSurface:
    element: Element
    text: str
    attribute: str | None = None

    @property
    def location(self) -> str:
        suffix = f"[{self.attribute}]" if self.attribute else " text"
        return self.element.location + suffix


@dataclass(slots=True)
class HTMLDocument:
    root: Element
    elements: list[Element]

    def select(self, *tags: str) -> list[Element]:
        return [node for node in self.elements if node.tag in tags]

    @property
    def visible_text(self) -> tuple[TextSurface, ...]:
        surfaces: list[TextSurface] = []

        def visit(node: Element) -> None:
            if node.tag in _NON_TEXT_TAGS or node.hidden:
                return
            for child in node.children:
                if isinstance(child, str):
                    if child.strip():
                        surfaces.append(TextSurface(node, child))
                else:
                    visit(child)

        visit(self.root)
        return tuple(surfaces)

    @property
    def attributes(self) -> tuple[TextSurface, ...]:
        return tuple(
            TextSurface(node, value, key)
            for node in self.elements
            if not node.hidden
            for key in TEXT_ATTRIBUTES
            if (value := node.attrs.get(key)) is not None
        )

    @property
    def surfaces(self) -> tuple[TextSurface, ...]:
        return self.visible_text + self.attributes

    @property
    def headings(self) -> list[Element]:
        return self.select("h1", "h2", "h3", "h4", "h5", "h6")

    @property
    def tables(self) -> list[Element]:
        return self.select("table")

    @property
    def svgs(self) -> list[Element]:
        return self.select("svg")

    @property
    def ids(self) -> dict[str, Element]:
        return {value: node for node in self.elements if (value := node.attrs.get("id"))}

    @property
    def html_lang(self) -> str | None:
        html = self.select("html")
        return html[0].attrs.get("lang") if html else None

    @property
    def h1_count(self) -> int:
        return len(self.select("h1"))

    @property
    def forms(self) -> list[Element]:
        return self.select("form")

    @property
    def links(self) -> list[Element]:
        return self.select("a")

    @property
    def buttons(self) -> list[Element]:
        return self.select("button")

    @property
    def inputs(self) -> list[Element]:
        return self.select("input")

    @property
    def references(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (key, token)
            for node in self.elements
            for key in ("aria-labelledby", "aria-controls", "aria-describedby")
            for token in (node.attrs.get(key) or "").split()
        )

    @property
    def tables_without_headers(self) -> int:
        return sum(
            not any(child.tag == "th" for child in table.descendants()) for table in self.tables
        )

    def accessible_name(self, node: Element, *, _seen: frozenset[int] = frozenset()) -> str:
        """Resolve static names, including forward and hidden labelled-by references."""

        if id(node) in _seen:
            return ""
        seen = _seen | {id(node)}
        if references := node.attrs.get("aria-labelledby"):
            return " ".join(
                self.accessible_name(self.ids[token], _seen=seen)
                for token in references.split()
                if token in self.ids
            ).strip()
        if label := node.attrs.get("aria-label"):
            return label.strip()
        if node.tag in {"input", "select", "textarea"}:
            labels = [
                label
                for label in self.select("label")
                if (node.attrs.get("id") and label.attrs.get("for") == node.attrs["id"])
                or any(ancestor is label for ancestor in node.ancestors())
            ]
            if labels:
                return " ".join(label.text(include_hidden=True).strip() for label in labels)
            if node.tag == "input" and node.attrs.get("type") in {"button", "submit", "reset"}:
                return (node.attrs.get("value") or "").strip()
            if node.tag == "input" and node.attrs.get("type") == "image":
                return (node.attrs.get("alt") or "").strip()
        if node.tag == "img":
            return (node.attrs.get("alt") or "").strip()
        if node.tag in {"svg", "table"}:
            tag = "title" if node.tag == "svg" else "caption"
            names = [
                child for child in node.children if isinstance(child, Element) and child.tag == tag
            ]
            if names:
                return " ".join(child.text(include_hidden=True).strip() for child in names)
            # Data cells and graph labels are content, not a name for the container.
            return (node.attrs.get("title") or "").strip()
        text = node.text(include_hidden=True).strip()
        return text or (node.attrs.get("title") or "").strip()


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Element("#document")
        self.elements: list[Element] = []
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        parent = self.stack[-1]
        node = Element(tag, dict(attrs), parent=parent)
        parent.children.append(node)
        self.elements.append(node)
        if tag not in _VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def parse_html(markup: str) -> HTMLDocument:
    parser = _Parser()
    parser.feed(markup)
    parser.close()
    return HTMLDocument(parser.root, parser.elements)


def render_pseudo_document(app: ManagerGUIApp, url: str = "/") -> str:
    """Render through the public app seam with a test-only pseudo translator."""

    with patch(
        "manager_gui.web.app.Translator",
        side_effect=partial(Translator, pseudo=True),
    ), patch(
        "manager_gui.web.navigation.Translator",
        side_effect=partial(Translator, pseudo=True),
    ):
        return app.render(url)


# Every mounted route is audited, including L5 Search and Portal. Keep this
# explicit set as an exit-gate inventory; it no longer excludes page copy.
MIGRATED_ROUTES: frozenset[str] = frozenset(
    {
        "atlas",
        "stories",
        "strategies",
        "strategy-conditions",
        "strategy-genome-comparison",
        "memory",
        "memory-failures",
        "failure-patterns",
        "evidence",
        "lineage",
        "evidence-object-comparison",
        "derived-failure-grouping",
        "methodology",
        "history",
        "source-documents",
        "search",
        "portal",
    }
)
_SHARED_CLASSES = frozenset(
    {
        "skip-link",
        "topbar",
        "nav-strip",
        "inspector",
        "event-drawer",
        "panel-actions",
        "status-block",
        "page-pagination",
        "view-mode-controls",
        "opaque-copy-button",
    }
)
_EXCLUDED_CLASSES = frozenset({"raw-json", "language-switcher"})
# Only direct payload text is excluded. Their labels/ARIA and nested UI controls
# still go through the audit (e.g. status-source-note's <strong>Source note</strong>).
OWNER_TEXT_ALLOWLIST = frozenset(
    {
        "raw-json",
        "status-source-note",
        "status-errors",
        "workspace-note",
        "inspector-list",
        "copy-status",
    }
)
_OWNER_DIRECT_TAGS = frozenset({"dd", "li", "p", "pre", "span"})
LATIN_ALLOWLIST = frozenset(
    {
        "Manager GUI",
        "ManagerReadModel v0",
        "ID",
        "JSON",
        "API",
        "URL",
        "SHA-256",
        "Schema",
        "GUI",
        "manager-read-model.v0",
    }
)
_HAN = re.compile("[\\u3400-\\u4dbf\\u4e00-\\u9fff\\uf900-\\ufaff\\U00020000-\\U000323af]")
_LATIN = re.compile(r"[A-Za-z][A-Za-z0-9_.-]*")
_BILINGUAL = re.compile(r"[A-Za-z][A-Za-z ]*\s*/\s*[㐀-鿿]|[㐀-鿿]+\s*/\s*[A-Za-z]")


def _shared(node: Element) -> bool:
    return any(ancestor.classes & _SHARED_CLASSES for ancestor in node.ancestors())


def _switcher(node: Element) -> bool:
    return any("data-language-switcher" in ancestor.attrs for ancestor in node.ancestors())


def is_owner_text(surface: TextSurface) -> bool:
    """Return whether a surface is owner payload rather than UI vocabulary."""

    node = surface.element
    if surface.attribute is not None:
        return False
    if node.attrs.get("data-owner-text") == "true":
        return True
    if node.attrs.get("translate") == "no":
        return True
    if node.classes & OWNER_TEXT_ALLOWLIST:
        return True
    if any("status-errors" in ancestor.classes for ancestor in node.ancestors()):
        return True
    if node.tag == "dt" and any(
        "inspector-list" in ancestor.classes for ancestor in node.ancestors()
    ):
        # Source owner/kind pairs are owner payload; ordinary <dt> labels are not.
        return " · " in node.text(include_hidden=True)
    return node.tag in _OWNER_DIRECT_TAGS and any(
        ancestor.classes & OWNER_TEXT_ALLOWLIST for ancestor in node.ancestors()
    )


def _in_scope(node: Element, route: str | None) -> bool:
    return route is None or route in MIGRATED_ROUTES or _shared(node)


def _surfaces(document: HTMLDocument, route: str | None) -> tuple[TextSurface, ...]:
    return tuple(
        surface
        for surface in document.surfaces
        if _in_scope(surface.element, route)
        and not is_owner_text(surface)
        and not any(
            ancestor.classes & _EXCLUDED_CLASSES for ancestor in surface.element.ancestors()
        )
    )


def _without_allowed(text: str, allowed: Iterable[str]) -> str:
    # Match complete tokens: allowing API must not exempt APIUnavailable or Api.
    for value in sorted(set(allowed), key=len, reverse=True):
        if value:
            pattern = re.escape(value)
            if value[0].isascii() and value[0].isalnum():
                pattern = r"(?<![A-Za-z0-9_])" + pattern
            if value[-1].isascii() and value[-1].isalnum():
                pattern += r"(?![A-Za-z0-9_])"
            text = re.sub(pattern, "", text)
    return text


def assert_pseudo_localized(
    document: HTMLDocument | str,
    *,
    owner_text: Iterable[str] = (),
    allowed_text: Iterable[str] = (),
    route: str | None = None,
) -> None:
    """Fail on unwrapped UI words, while admitting explicit owner/technical text."""

    document = parse_html(document) if isinstance(document, str) else document
    surfaces = _surfaces(document, route)
    # A catalog HTML template may put its opening/closing markers around tags.
    streams = [("visible text", "".join(s.text for s in surfaces if s.attribute is None))]
    streams.extend((s.location, s.text) for s in surfaces if s.attribute is not None)
    allowed = (*owner_text, *allowed_text)
    for location, text in streams:
        depth = 0
        remaining: list[str] = []
        for character in text:
            if character == "⟦":
                depth += 1
            elif character == "⟧":
                assert depth > 0, f"unbalanced pseudo marker at {location}"
                depth -= 1
            elif not depth:
                remaining.append(character)
        assert depth == 0, f"unbalanced pseudo marker at {location}"
        leak = _without_allowed("".join(remaining), allowed)
        assert not _LATIN.search(leak) and not _HAN.search(leak), (
            f"pseudo-locale leak at {location}: {leak!r}"
        )


def assert_language_text(
    document: HTMLDocument | str,
    locale: Locale,
    *,
    owner_text: Iterable[str] = (),
    latin_allowlist: Iterable[str] = LATIN_ALLOWLIST,
    route: str | None = None,
) -> None:
    """Chinese admits only frozen Latin tokens; English excludes UI Han text."""

    document = parse_html(document) if isinstance(document, str) else document
    owner = tuple(owner_text)
    for surface in _surfaces(document, route):
        text = _without_allowed(surface.text, owner)
        if locale is Locale.EN:
            assert not _HAN.search(text), f"English Han leak at {surface.location}: {text!r}"
        else:
            text = _without_allowed(text, latin_allowlist)
            assert not _LATIN.search(text), f"Chinese Latin leak at {surface.location}: {text!r}"


def _normalized_url(value: str) -> str:
    parts = urlsplit(value)
    pairs = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key != "lang"
    ]
    return parts._replace(query=urlencode(pairs)).geturl()


def dom_skeleton(document: HTMLDocument | str) -> tuple[object, ...]:
    """Structure + machine attributes, ignoring only text and locale presentation.

    The switcher has a current span and a destination link in opposite positions.
    Its two locale choices normalize to the same semantic choice nodes. Hidden lang
    form controls are request state and absent for default Chinese.
    """

    document = parse_html(document) if isinstance(document, str) else document

    def visit(node: Element) -> object:
        if node.tag == "input" and node.attrs.get("name") == "lang":
            return None
        attrs: list[tuple[str, str | None]] = []
        switcher_choice = _switcher(node) and node.tag in {"a", "span"} and "lang" in node.attrs
        for key, value in sorted(node.attrs.items()):
            if key in {*TEXT_ATTRIBUTES, "lang", "hreflang"}:
                continue
            if switcher_choice and key in {"href", "aria-current"}:
                continue
            if key in {"href", "action"} and value is not None:
                value = _normalized_url(value)
            attrs.append((key, value))
        children = tuple(
            result
            for child in node.children
            if isinstance(child, Element)
            if (result := visit(child)) is not None
        )
        return ("locale-choice" if switcher_choice else node.tag, tuple(attrs), children)

    return (visit(document.root),)


def assert_dom_equivalent(zh: HTMLDocument | str, en: HTMLDocument | str) -> None:
    assert dom_skeleton(zh) == dom_skeleton(en), "zh/en DOM skeletons differ"


def _local_url(value: str) -> bool:
    parts = urlsplit(value)
    return (
        not parts.scheme
        and not parts.netloc
        and not (not parts.path and not parts.query and parts.fragment)
    )


def _lang_values(pairs: Iterable[tuple[str, str]]) -> list[str]:
    return [value for key, value in pairs if key == "lang"]


def assert_lang_propagation(
    document: HTMLDocument | str,
    explicit_locale: Locale | None,
    *,
    source_url: str | None = None,
) -> None:
    """Audit all UI links/GET forms; API export payloads remain language-neutral.

    Query parsing always keeps duplicate/blank pairs. With source_url, switchers,
    shared navigation/home and GET controls must preserve opaque query values.
    """

    document = parse_html(document) if isinstance(document, str) else document
    expected = [] if explicit_locale is None else [explicit_locale.value]
    source_pairs = parse_qsl(urlsplit(source_url or "").query, keep_blank_values=True)
    opaque = [
        (key, value)
        for key, value in source_pairs
        if key not in {"view", "fixture", "lang", "q", "panel", "mode"}
    ]
    for link in document.links:
        href = link.attrs.get("href")
        if href is None or not _local_url(href):
            continue
        parts = urlsplit(href)
        pairs = parse_qsl(parts.query, keep_blank_values=True)
        if parts.path.startswith("/api/"):
            assert not _lang_values(pairs), f"API URL contains lang: {href}"
            continue
        if _switcher(link):
            target = link.attrs.get("hreflang")
            assert target in {locale.value for locale in Locale}, "switcher has invalid hreflang"
            assert _lang_values(pairs) == [target], f"switcher lang mismatch: {href}"
            assert target != document.html_lang, "switcher links to the current locale"
            if source_url is not None:
                assert [(key, value) for key, value in pairs if key != "lang"] == [
                    (key, value) for key, value in source_pairs if key != "lang"
                ], "switcher lost query duplicates/blanks/order"
        else:
            assert _lang_values(pairs) == expected, f"internal link lang mismatch: {href}"
            if source_url is not None and link.classes & {"nav-link", "brand"}:
                actual = Counter((key, value) for key, value in pairs if key in dict(opaque))
                assert actual == Counter(opaque), f"shared link lost opaque query pairs: {href}"
    for form in document.forms:
        assert (form.attrs.get("method") or "get").lower() == "get", "non-GET form"
        if not _local_url(form.attrs.get("action") or ""):
            continue
        # Browsers replace an action's query on GET: a query lang is not a substitute
        # for a successful hidden input. Include associated controls outside the form.
        controls = [
            node
            for node in document.select("input", "select", "textarea", "button")
            if any(ancestor is form for ancestor in node.ancestors())
            or (form.attrs.get("id") and node.attrs.get("form") == form.attrs["id"])
        ]
        pairs = [
            (node.attrs["name"] or "", node.attrs.get("value") or "")
            for node in controls
            if node.attrs.get("name") and "disabled" not in node.attrs
        ]
        lang_controls = [node for node in controls if node.attrs.get("name") == "lang"]
        assert _lang_values(pairs) == expected, f"GET form lang mismatch at {form.location}"
        assert all(
            node.tag == "input" and node.attrs.get("type") == "hidden" for node in lang_controls
        ), "lang must be a hidden GET control"
        if source_url is not None and "search-form" in form.classes:
            assert Counter((key, value) for key, value in pairs if key in dict(opaque)) == Counter(
                opaque
            ), "GET form lost opaque query duplicates/blanks"


def assert_accessible(
    document: HTMLDocument | str,
    *,
    route: str | None = None,
    owner_text: Iterable[str] = (),
) -> None:
    """Name/reference audits cover all controls, including revealable hidden panels.

    New name/heading rules cover shared surfaces and MIGRATED_ROUTES; deferred page
    containers keep their existing reference/action/header assertions.
    """

    document = parse_html(document) if isinstance(document, str) else document
    for surface in _surfaces(document, route):
        assert not _BILINGUAL.search(surface.text), (
            f"bilingual UI text at {surface.location}: {surface.text!r}"
        )
    ids = [node.attrs["id"] for node in document.elements if node.attrs.get("id")]
    assert len(ids) == len(set(ids)), "duplicate id attributes"
    for key, token in document.references:
        assert token in document.ids, f"{key} references a missing id: {token}"
    for node in document.select("a", "button", "input", "select", "textarea"):
        if node.tag == "a" and "href" not in node.attrs:
            continue
        if node.tag == "input" and node.attrs.get("type") == "hidden":
            continue
        name = document.accessible_name(node)
        assert name.strip(), f"action without an accessible name: {node.location}"
        if _in_scope(node, route) and not _switcher(node):
            clean = _without_allowed(name, owner_text)
            assert not _BILINGUAL.search(clean), f"bilingual accessible name: {name!r}"
        if node.tag == "button":
            assert node.attrs.get("type") in {"button", "submit"}, "button type must be explicit"
    assert document.tables_without_headers == 0, "table without headers"
    for node in (*document.svgs, *document.tables):
        if _in_scope(node, route) and node.attrs.get("aria-hidden") != "true":
            name = document.accessible_name(node)
            assert name, f"{node.tag} without an accessible name"
            assert not _BILINGUAL.search(_without_allowed(name, owner_text)), (
                f"bilingual {node.tag} name: {name!r}"
            )
    headings = [node for node in document.headings if _in_scope(node, route) or node.tag == "h1"]
    if document.select("html"):
        assert document.h1_count == 1, "document must have exactly one h1"
    previous = 0
    for heading in headings:
        level = int(heading.tag[1])
        assert level <= previous + 1, f"heading order skips h{previous} to h{level}"
        previous = level
    for form in document.forms:
        assert (form.attrs.get("method") or "get").lower() == "get", "non-GET form"


FIXTURE_ENUM_VOCABULARY = frozenset(state.value for state in FixtureState)


def assert_enum_vocabulary(
    domain: str,
    values: Iterable[str],
    *,
    catalog: Mapping[str, M] | None = None,
) -> None:
    """A closed enum must have a strict label in both languages for every value."""

    catalog = REGISTRY.entries if catalog is None else catalog
    for locale in Locale:
        translator = Translator(locale, strict=True, catalog=catalog)
        for value in values:
            key = f"label.{domain}.{value}"
            assert key in catalog, f"enum vocabulary missing {key} ({locale.value})"
            assert translator.t(key).strip(), f"empty enum label: {key}"


def assert_l5_vocabulary(*, catalog: Mapping[str, M] | None = None) -> None:
    """Audit every closed Search/Portal sample value in both locales."""

    from manager_gui.web.portal import (
        PortalArtifactState,
        ReportRebuildStatus,
        ReportVerifyStatus,
    )
    from manager_gui.web.search import SEARCH_FIELDS

    field_values = tuple(dict.fromkeys(("type", *SEARCH_FIELDS)))
    domains = {
        "l5_search_field": field_values,
        "l5_search_kind": ("record", "document", "all", "none"),
        "l5_search_record_type": ("campaign", "strategy", "run", "report"),
        "l5_search_status": ("active", "validated", "completed", "published"),
        "l5_portal_artifact_state": tuple(
            state.value.replace("-", "_") for state in PortalArtifactState
        ),
        "l5_portal_verify_status": tuple(status.value for status in ReportVerifyStatus),
        "l5_portal_rebuild_status": tuple(status.value for status in ReportRebuildStatus),
    }
    for domain, values in domains.items():
        assert_enum_vocabulary(domain, values, catalog=catalog)


def assert_fixture_vocabulary(
    document: HTMLDocument | str,
    *,
    route: str | None = None,
) -> None:
    """Audit fixture controls and rendered closed status/display vocabulary."""

    document = parse_html(document) if isinstance(document, str) else document
    assert_enum_vocabulary("status", tuple(status.value for status in ReadModelStatus))
    assert_enum_vocabulary("display_state", tuple(state.value for state in DisplayState))
    if route in {"search", "portal"}:
        assert_l5_vocabulary()
    translator = Translator(document.html_lang or Locale.ZH_CN, strict=True)
    for node in document.elements:
        if node.tag == "input" and node.attrs.get("name") == "fixture":
            assert node.attrs.get("value") in FIXTURE_ENUM_VOCABULARY, "unknown fixture vocabulary"
        if not _in_scope(node, route) or "status-block" not in node.classes:
            continue
        domain = "status" if "data-status" in node.attrs else "display_state"
        value = node.attrs.get(f"data-{domain.replace('_', '-')}")
        allowed = (
            {item.value for item in ReadModelStatus}
            if domain == "status"
            else {item.value for item in DisplayState}
        )
        assert value in allowed, f"unknown {domain} vocabulary: {value!r}"
        labels = [child for child in node.descendants() if "status-label" in child.classes]
        assert len(labels) == 1, f"{domain} block must have exactly one label"
        assert labels[0].text(include_hidden=True) == translator.t(f"label.{domain}.{value}"), (
            f"unlocalized {domain} label: {value!r}"
        )


def assert_owner_text_escaped(
    markup: str,
    owner_text: str | Mapping[str, int] | Iterable[str],
    *,
    expected_count: int = 1,
) -> None:
    """Check owner text is HTML-escaped once and decodes to the source once.

    A mapping supplies exact counts for values intentionally repeated in a page;
    a scalar/iterable uses ``expected_count`` for each value.
    """

    if isinstance(owner_text, str):
        expected = {owner_text: expected_count}
    elif isinstance(owner_text, Mapping):
        expected = dict(owner_text)
    else:
        expected = {value: expected_count for value in owner_text}
    document = parse_html(markup)
    decoded = "".join(surface.text for surface in document.surfaces)
    for value, count in expected.items():
        encoded = escape(value, quote=True)
        assert decoded.count(value) == count, (
            f"owner text decoded {decoded.count(value)} times, expected {count}: {value!r}"
        )
        assert markup.count(encoded) == count, (
            f"owner text escaped {markup.count(encoded)} times, expected {count}: {value!r}"
        )
        if encoded != value:
            assert value not in markup, f"owner text appears unescaped: {value!r}"


def assert_shared_shell_i18n(
    zh_markup: str,
    en_markup: str,
    *,
    route: str,
    source_url: str | None = None,
    owner_text: Iterable[str] = (),
) -> None:
    """Run the complete L2-T3 audit for one route's two locale documents."""

    zh = parse_html(zh_markup)
    en = parse_html(en_markup)
    assert_dom_equivalent(zh, en)
    assert zh.html_lang == Locale.ZH_CN.html_lang
    assert en.html_lang == Locale.EN.html_lang
    assert_language_text(zh, Locale.ZH_CN, owner_text=owner_text, route=route)
    assert_language_text(en, Locale.EN, owner_text=owner_text, route=route)
    assert_lang_propagation(zh, None, source_url=source_url)
    assert_lang_propagation(en, Locale.EN, source_url=source_url)
    assert_accessible(zh, route=route, owner_text=owner_text)
    assert_accessible(en, route=route, owner_text=owner_text)
    assert_fixture_vocabulary(zh, route=route)
    assert_fixture_vocabulary(en, route=route)


# Descriptive aliases make focused tests read as audits rather than implementation calls.
assert_no_pseudo_locale_leaks = assert_pseudo_localized
assert_dom_skeleton_equivalent = assert_dom_equivalent
assert_internal_language_propagation = assert_lang_propagation
assert_accessibility = assert_accessible
assert_exactly_once_owner_text_escaping = assert_owner_text_escaped


__all__ = [
    "FIXTURE_ENUM_VOCABULARY",
    "LATIN_ALLOWLIST",
    "MIGRATED_ROUTES",
    "OWNER_TEXT_ALLOWLIST",
    "Element",
    "HTMLDocument",
    "TextSurface",
    "assert_accessibility",
    "assert_accessible",
    "assert_dom_equivalent",
    "assert_dom_skeleton_equivalent",
    "assert_enum_vocabulary",
    "assert_exactly_once_owner_text_escaping",
    "assert_fixture_vocabulary",
    "assert_internal_language_propagation",
    "assert_l5_vocabulary",
    "assert_lang_propagation",
    "assert_language_text",
    "assert_no_pseudo_locale_leaks",
    "assert_owner_text_escaped",
    "assert_pseudo_localized",
    "assert_shared_shell_i18n",
    "dom_skeleton",
    "is_owner_text",
    "parse_html",
    "render_pseudo_document",
]
