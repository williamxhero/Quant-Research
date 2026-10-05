"""Standard-library DOM inspection and assertions for Manager GUI i18n tests.

This is a static HTML harness, not a browser: visibility follows HTML ``hidden``
and ``aria-hidden`` plus script/style/template exclusion, not computed CSS.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from html.parser import HTMLParser

_VOID_TAGS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
    "param", "source", "track", "wbr",
})
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
            "hidden" in node.attrs or node.attrs.get("aria-hidden") == "true"
            or node.tag in _NON_TEXT_TAGS or node.tag == "head"
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
            for node in self.elements if not node.hidden
            for key in TEXT_ATTRIBUTES if (value := node.attrs.get(key)) is not None
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

    def accessible_name(self, node: Element, *, _seen: frozenset[int] = frozenset()) -> str:
        """Resolve static names, including forward and hidden labelled-by references."""

        if id(node) in _seen:
            return ""
        seen = _seen | {id(node)}
        if references := node.attrs.get("aria-labelledby"):
            return " ".join(
                self.accessible_name(self.ids[token], _seen=seen)
                for token in references.split() if token in self.ids
            ).strip()
        if label := node.attrs.get("aria-label"):
            return label.strip()
        if node.tag in {"input", "select", "textarea"}:
            labels = [
                label for label in self.select("label")
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
            names = [child for child in node.children if isinstance(child, Element) and child.tag == tag]
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
