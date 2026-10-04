"""Catalog entries, entry validation and the immutable per-request `Translator`.

Catalog text is a Python value, not a gettext file: every entry is a bilingual
pair `M(zh, en)`, so a missing language is impossible by construction. Templates
use named placeholders (`{name}`) and glossary references (`{term:<id>}`); `{{` and
`}}` are literal braces. Parameters are substituted in a single pass and are never
parsed again, so a value that itself contains `{x}` is left untouched.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from html import escape
from types import MappingProxyType

from .glossary import TERMS
from .locale import DEFAULT_LOCALE, Locale

PSEUDO_OPEN = "⟦"
PSEUDO_CLOSE = "⟧"
PSEUDO_FILL = "~"
PLURAL_FORMS = frozenset({"one", "other"})
LABEL_PREFIX = "label"

_TOKEN = re.compile(
    r"\{\{|\}\}"
    r"|\{term:(?P<term>[a-z][a-z0-9_]*)\}"
    r"|\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)\}"
    r"|(?P<stray>[{}])"
)
_KEY = re.compile(r"[^\s{}]+")
_LABEL_DOMAIN = re.compile(r"[a-z][a-z0-9_]*")
_JOIN_SEPARATORS = {Locale.ZH_CN: "、", Locale.EN: ", "}


class TranslationError(Exception):
    """Malformed catalog data, or (in strict mode only) a lookup that cannot resolve."""


@dataclass(frozen=True, slots=True)
class M:
    """One bilingual catalog entry.

    `zh` has a single form. `en` is either one string or `{"one": ..., "other": ...}`
    for English plurals. `note` is context for translators and is never rendered.
    """

    zh: str
    en: str | Mapping[str, str]
    note: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.zh, str):
            raise TranslationError(f"M.zh must be a string, got {type(self.zh).__name__}")
        if isinstance(self.en, Mapping):
            # Copy so a plural table cannot change after registration validated it.
            plural = dict(self.en)
            if any(not isinstance(key, str) or not isinstance(value, str) for key, value in plural.items()):
                raise TranslationError("M.en plural values must be string-to-string")
            object.__setattr__(self, "en", MappingProxyType(plural))
        elif not isinstance(self.en, str):
            raise TranslationError(f"M.en must be a string or a mapping, got {type(self.en).__name__}")
        if self.note is not None and not isinstance(self.note, str):
            raise TranslationError("M.note must be a string or None")

    @property
    def is_plural(self) -> bool:
        return not isinstance(self.en, str)

    def template(self, locale: Locale, n: int | None) -> str:
        """The raw template for `locale`; English plurals are chosen by `n`."""

        if locale is Locale.ZH_CN:
            return self.zh
        if isinstance(self.en, str):
            return self.en
        return self.en.get("one" if n == 1 else "other", "")


def label_key(domain: str, value: str) -> str:
    """Catalog key of a known value of an enumerated domain, e.g. `label.status.ready`."""

    if not _LABEL_DOMAIN.fullmatch(domain):
        raise TranslationError(f"label domain must be lower snake_case: {domain!r}")
    if not value:
        raise TranslationError(f"label value for domain {domain!r} must not be empty")
    return f"{LABEL_PREFIX}.{domain}.{value}"


def _scan(template: str, where: str) -> tuple[frozenset[str], frozenset[str]]:
    """Return the (placeholder names, glossary term ids) used by a template."""

    names: set[str] = set()
    terms: set[str] = set()
    for match in _TOKEN.finditer(template):
        if match["stray"]:
            raise TranslationError(
                f"{where}: malformed or unbalanced brace at index {match.start()} in {template!r}"
            )
        if match["term"]:
            terms.add(match["term"])
        elif match["name"]:
            if match["name"] == "term":
                raise TranslationError(f"{where}: placeholder name 'term' is reserved")
            names.add(match["name"])
    return frozenset(names), frozenset(terms)


def validate_entry(key: str, message: M) -> None:
    """Raise TranslationError unless `message` is a well-formed catalog entry for `key`.

    Checks the key shape, non-empty text in every form, the exact English plural
    forms, balanced braces, identical named placeholders in every form of both
    languages, and that every `{term:<id>}` exists in the glossary.
    """

    if not isinstance(key, str) or not _KEY.fullmatch(key):
        raise TranslationError(f"invalid catalog key: {key!r}")
    if not isinstance(message, M):
        raise TranslationError(f"{key}: entry must be an M, got {type(message).__name__}")

    forms: dict[str, str] = {"zh": message.zh}
    if isinstance(message.en, str):
        forms["en"] = message.en
    else:
        if set(message.en) != PLURAL_FORMS:
            raise TranslationError(
                f"{key}: plural en must define exactly 'one' and 'other', got {sorted(message.en)}"
            )
        forms["en.one"] = message.en["one"]
        forms["en.other"] = message.en["other"]

    placeholders: dict[str, frozenset[str]] = {}
    term_ids: set[str] = set()
    for form, template in forms.items():
        if not isinstance(template, str) or not template.strip():
            raise TranslationError(f"{key} [{form}]: text must be a non-empty string")
        names, terms = _scan(template, f"{key} [{form}]")
        placeholders[form] = names
        term_ids |= terms

    expected = placeholders["zh"]
    for form, names in placeholders.items():
        if names != expected:
            raise TranslationError(
                f"{key}: placeholders differ between zh {sorted(expected)} and {form} {sorted(names)}"
            )
    unknown = sorted(term_id for term_id in term_ids if term_id not in TERMS)
    if unknown:
        raise TranslationError(f"{key}: unknown glossary term(s) {unknown}")
    if key.startswith(f"{LABEL_PREFIX}."):
        if expected or message.is_plural:
            raise TranslationError(f"{key}: label entries take no placeholders and no plural forms")


def source_text(value: str) -> str:
    """Escape owner free text exactly once; it is never translated or re-parsed.

    This is the single entry point for owner-provided text (titles, summaries,
    `reason`, error messages), so any later source-language annotation changes here.
    """

    return escape(value, quote=True)


def _pseudo(text: str) -> str:
    """Wrap catalog text for the test-only pseudo-locale and lengthen it by ~30%."""

    fill = PSEUDO_FILL * max(2, len(text) * 3 // 10)
    return f"{PSEUDO_OPEN}{text}{fill}{PSEUDO_CLOSE}"


def _code(raw: str) -> str:
    return f"<code>{escape(raw)}</code>"


def _expand(
    template: str,
    params: Mapping[str, object],
    locale: Locale,
    *,
    as_html: bool,
    strict: bool,
    where: str,
) -> str:
    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        if token == "{{":
            return "{"
        if token == "}}":
            return "}"
        if match["stray"]:
            if strict:
                raise TranslationError(f"{where}: malformed or unbalanced brace in {template!r}")
            return token
        if match["term"]:
            term = TERMS.get(match["term"])
            if term is None:
                # Registration rejects unknown terms, so this is an authoring error in
                # an unvalidated catalog; fail in every mode rather than guess a term.
                raise TranslationError(f"{where}: unknown glossary term {match['term']!r}")
            text = term.zh if locale is Locale.ZH_CN else term.en
        elif match["name"] and match["name"] in params:
            text = str(params[match["name"]])
        elif strict:
            raise TranslationError(f"{where}: missing parameter for {token}")
        else:
            return token
        return escape(text, quote=True) if as_html else text

    return _TOKEN.sub(replace, template)


class Translator:
    """Immutable, per-request translation facade for one locale.

    `strict=True` (tests) raises TranslationError on a missing key, a missing
    parameter or a plural entry used without `count()`. The default lenient mode
    never raises for lookups: a missing key renders as the key itself, and text
    falls back zh -> en -> key, so a page cannot crash on a catalog gap.
    `pseudo=True` is the test-only pseudo-locale: every catalog string is wrapped in
    `⟦…⟧` and lengthened so untranslated text stands out. It is a constructor flag
    only and cannot be selected through `resolve_locale` or the URL.
    """

    __slots__ = ("_catalog", "_locale", "_pseudo", "_strict")

    def __init__(
        self,
        locale: Locale = DEFAULT_LOCALE,
        *,
        strict: bool = False,
        pseudo: bool = False,
        catalog: Mapping[str, M] | None = None,
    ) -> None:
        if catalog is None:
            # Deferred: the catalog package imports this module for M and validation.
            from .catalog import REGISTRY

            catalog = REGISTRY.entries
        object.__setattr__(self, "_locale", Locale(locale))
        object.__setattr__(self, "_strict", bool(strict))
        object.__setattr__(self, "_pseudo", bool(pseudo))
        object.__setattr__(self, "_catalog", catalog)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("Translator is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("Translator is immutable")

    def __repr__(self) -> str:
        return (
            f"Translator({self._locale.value!r}, strict={self._strict}, pseudo={self._pseudo})"
        )

    @property
    def locale(self) -> Locale:
        return self._locale

    @property
    def html_lang(self) -> str:
        return self._locale.html_lang

    @property
    def strict(self) -> bool:
        return self._strict

    @property
    def pseudo(self) -> bool:
        return self._pseudo

    def t(self, key: str, /, **params: object) -> str:
        """Plain text for `key`; the caller escapes it where it is written out."""

        return self._format(key, params, n=None, as_html=False)

    def count(self, key: str, n: int, /, **params: object) -> str:
        """Plain text for `key` with English plural selection by `n` (`{n}` is provided)."""

        if "n" in params:
            raise TranslationError("count() supplies {n} itself; do not pass n=")
        return self._format(key, {**params, "n": n}, n=n, as_html=False)

    def html(self, key: str, /, **params: object) -> str:
        """Markup for a trusted catalog template; every parameter is HTML-escaped."""

        return self._format(key, params, n=None, as_html=True)

    def label(self, domain: str, value: str) -> str:
        """HTML fragment naming `value` within an enumerated `domain`.

        A known value renders its escaped catalog label (`label.<domain>.<value>`).
        Unknown values are open-vocabulary data: they render verbatim and escaped
        inside `<code>`, never title-cased or translated.
        """

        raw = str(value)
        if not raw:
            return _code(raw)
        try:
            key = label_key(domain, raw)
        except TranslationError:
            if self._strict:
                raise
            return _code(raw)
        if key not in self._catalog:
            return _code(raw)
        return escape(self._format(key, {}, n=None, as_html=False), quote=True)

    def join(self, items: Iterable[str]) -> str:
        """Join list items with the locale's separator ("、" for zh-CN, ", " for en)."""

        return _JOIN_SEPARATORS[self._locale].join(items)

    def source_text(self, value: str) -> str:
        """Same as the module-level `source_text`; owner text is escaped once, untranslated."""

        return source_text(value)

    def _format(
        self, key: str, params: Mapping[str, object], *, n: int | None, as_html: bool
    ) -> str:
        message = self._catalog.get(key)
        if message is None:
            if self._strict:
                raise TranslationError(f"missing catalog key: {key!r}")
            return escape(key) if as_html else key
        if self._strict and message.is_plural and n is None:
            raise TranslationError(f"{key}: plural entry must be rendered with count()")

        # Strict mode never substitutes another language; lenient mode tries the
        # requested locale, then zh, then en, then falls back to the key.
        chain = (self._locale,) if self._strict else (self._locale, Locale.ZH_CN, Locale.EN)
        for locale in dict.fromkeys(chain):
            template = message.template(locale, n)
            if template.strip():
                text = _expand(
                    template, params, locale, as_html=as_html, strict=self._strict, where=key
                )
                return _pseudo(text) if self._pseudo else text
        if self._strict:
            raise TranslationError(f"{key}: no {self._locale.value} text")
        return escape(key) if as_html else key


__all__ = [
    "LABEL_PREFIX",
    "PLURAL_FORMS",
    "PSEUDO_CLOSE",
    "PSEUDO_FILL",
    "PSEUDO_OPEN",
    "M",
    "TranslationError",
    "Translator",
    "label_key",
    "source_text",
    "validate_entry",
]
