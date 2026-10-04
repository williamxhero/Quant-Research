"""Locale values and the `lang` query semantics of the Manager GUI.

The language is carried only by the `lang` query parameter. There is no cookie and
no `Accept-Language` negotiation, so the server stays stateless and every URL is a
bookmarkable state.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class Locale(StrEnum):
    """The two supported UI languages; the value is the canonical `lang` token."""

    ZH_CN = "zh-CN"
    EN = "en"

    @property
    def html_lang(self) -> str:
        """Value for `<html lang>` and `hreflang`."""

        return self.value


DEFAULT_LOCALE = Locale.ZH_CN
LANG_PARAM = "lang"

# Lookup keys are lower-case with "_" folded to "-", so "zh_CN", "ZH-cn" and
# "zh-CN" all land on the same entry.
_ALIASES: dict[str, Locale] = {
    "zh": Locale.ZH_CN,
    "zh-cn": Locale.ZH_CN,
    "zh-hans": Locale.ZH_CN,
    "en": Locale.EN,
    "en-us": Locale.EN,
    "en-gb": Locale.EN,
}


def resolve_locale(value: str | Locale | Iterable[str] | None) -> Locale | None:
    """Map a `lang` value to a supported locale, or None when it is unspecified.

    `value` is either one raw value or the sequence of every repeated `lang`
    parameter; with repeats the first value decides, even when it is invalid.
    Aliases are matched case-insensitively. Empty and unknown values (including any
    test-only pseudo-locale name) return None, which callers treat as "not
    specified" and replace by `DEFAULT_LOCALE`.
    """

    if value is None:
        return None
    if isinstance(value, Locale):
        return value
    if not isinstance(value, str):
        value = next(iter(value), "")
    key = value.strip().lower().replace("_", "-")
    return _ALIASES.get(key)


def with_lang(url: str, locale: Locale | None) -> str:
    """Return `url` with its `lang` query parameter set to `locale`.

    Every other parameter keeps its order, duplicates and blank values. Existing
    `lang` parameters collapse into one at the position of the first occurrence; a
    missing one is appended. `None` strips `lang` entirely. `locale` must already be
    a canonical Locale: resolve aliases with `resolve_locale` first.
    """

    parts = urlsplit(url)
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    if locale is not None:
        locale = Locale(locale)
    elif all(key != LANG_PARAM for key, _ in pairs):
        return url

    rewritten: list[tuple[str, str]] = []
    placed = False
    for key, value in pairs:
        if key != LANG_PARAM:
            rewritten.append((key, value))
        elif locale is not None and not placed:
            rewritten.append((LANG_PARAM, locale.value))
            placed = True
    if locale is not None and not placed:
        rewritten.append((LANG_PARAM, locale.value))
    return urlunsplit(parts._replace(query=urlencode(rewritten)))


__all__ = ["DEFAULT_LOCALE", "LANG_PARAM", "Locale", "resolve_locale", "with_lang"]
