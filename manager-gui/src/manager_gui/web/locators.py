"""Shared rule for which published locators may become clickable links.

Every S4 page shows source and artifact locators exactly as published, but only
a public or fixture locator may be rendered as a link.  A local path, a
``file:`` URL, or a URL carrying credentials is withheld and the reference is
shown as ``Missing / Unconfirmed``; the page never dereferences a locator.
"""

from __future__ import annotations

from urllib.parse import urlsplit

# Schemes that denote a public read seam or a deterministic fixture.
LINKABLE_SCHEMES = frozenset({"fixture", "workspace", "artifact"})


def public_locator(value: str | None) -> str | None:
    """Only public or fixture locators become links; local and private paths never do."""

    if value is None or "\\" in value or any(ord(char) < 32 for char in value):
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme in {"http", "https"}:
        return value if parsed.netloc and not parsed.username and not parsed.password else None
    return value if parsed.scheme in LINKABLE_SCHEMES else None


__all__ = ["LINKABLE_SCHEMES", "public_locator"]
