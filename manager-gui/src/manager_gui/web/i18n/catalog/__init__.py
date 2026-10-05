"""Registry of validated translation catalogs.

Each catalog module builds a dict of `M` entries and calls `register()` at import
time. Registration validates every entry (see `validate_entry`) and rejects any key
that is already registered, so two modules can never silently override each other.
Page catalogs are imported at the bottom of this file, after `REGISTRY` exists, so
that importing the package populates the registry. No page catalog exists yet.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from ..translator import M, TranslationError, validate_entry


class CatalogError(TranslationError):
    """A catalog entry is invalid or collides with an existing key."""


def _entries_arg(entries: Mapping[str, M] | str, message: M | None) -> Mapping[str, M]:
    if isinstance(entries, str):
        if message is None:
            raise CatalogError(f"missing message for catalog key: {entries!r}")
        return {entries: message}
    if message is not None:
        raise CatalogError("message is only accepted with a single catalog key")
    if not isinstance(entries, Mapping):
        raise CatalogError(f"catalog entries must be a mapping, got {type(entries).__name__}")
    return entries


def merge(*parts: Mapping[str, M]) -> dict[str, M]:
    """Combine catalog dicts into a new validated dict; a repeated key is an error."""

    merged: dict[str, M] = {}
    for part in parts:
        for key, message in part.items():
            validate_entry(key, message)
            if key in merged:
                raise CatalogError(f"duplicate catalog key: {key!r}")
            merged[key] = message
    return merged


class CatalogRegistry:
    """An append-only set of validated entries, exposed as a read-only view."""

    __slots__ = ("_entries", "_view")

    def __init__(self) -> None:
        self._entries: dict[str, M] = {}
        self._view: Mapping[str, M] = MappingProxyType(self._entries)

    @property
    def entries(self) -> Mapping[str, M]:
        """Live read-only view; entries registered later become visible through it."""

        return self._view

    def register(
        self, entries: Mapping[str, M] | str, message: M | None = None
    ) -> None:
        """Validate and add entries atomically: on any error nothing is registered."""

        try:
            staged = merge(_entries_arg(entries, message))
        except TranslationError as exc:
            if isinstance(exc, CatalogError):
                raise
            raise CatalogError(str(exc)) from exc
        for key in staged:
            if key in self._entries:
                raise CatalogError(f"duplicate catalog key: {key!r}")
        self._entries.update(staged)


REGISTRY = CatalogRegistry()
# Shared shell catalogs are imported only after the registry exists.  Each module
# owns one namespace and registration remains append-only and collision-checked.
from . import client, interaction, status  # noqa: E402

REGISTRY.register(status.ENTRIES)
REGISTRY.register(interaction.ENTRIES)
REGISTRY.register(client.ENTRIES)

# A short public alias for callers that only need the read-only catalog mapping.
CATALOG = REGISTRY.entries


def register(entries: Mapping[str, M] | str, message: M | None = None) -> None:
    """Register entries in the process-wide registry used by default Translators."""

    REGISTRY.register(entries, message)


__all__ = ["CATALOG", "REGISTRY", "CatalogError", "CatalogRegistry", "merge", "register"]
