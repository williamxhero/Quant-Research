"""Registry of validated translation catalogs.

Catalog namespaces are separate modules so L2 tickets can append entries without
silently replacing another namespace. Registration still happens through one
validated, append-only registry used by the default :class:`Translator`.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from ..translator import M, TranslationError, validate_entry
from . import nav, pagination, shell


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


# Keep namespace registration explicit and additive. Each page namespace calls
# ``register`` once at import time; importing here makes it available to the
# default Translator without re-registering entries in the page modules.
SHELL_CATALOG = shell.ENTRIES
NAVIGATION_CATALOG = nav.ENTRIES
PAGINATION_CATALOG = pagination.ENTRIES
register(merge(SHELL_CATALOG, NAVIGATION_CATALOG, PAGINATION_CATALOG))

from . import l3_atlas_story, l3_genome, l3_method_history  # noqa: E402

REGISTRY.register(l3_atlas_story.ENTRIES)
REGISTRY.register(l3_genome.ENTRIES)
REGISTRY.register(l3_method_history.ENTRIES)

# L4 page namespaces are registered exactly once at the integration boundary.
# Their page-local translators remain compatible with this process-wide registry,
# while duplicate keys fail closed through CatalogRegistry.register().
from . import (  # noqa: E402
    l4_evidence,
    l4_evidence_lineage_reader,
    l4_lineage,
    l4_memory,
)

REGISTRY.register(l4_memory.ENTRIES)
REGISTRY.register(l4_evidence.ENTRIES)
REGISTRY.register(l4_lineage.ENTRIES)
REGISTRY.register(l4_evidence_lineage_reader.ENTRIES)

# L5 Search and Portal namespaces are registered exactly once at the integration
# boundary, preserving the append-only collision checks used by every slice.
from . import (  # noqa: E402
    l5_history_documents_reader,
    l5_methodology_reader,
    l5_portal,
    l5_portal_reader,
    l5_search,
    l5_search_reader,
)

REGISTRY.register(l5_search.ENTRIES)
REGISTRY.register(l5_portal.ENTRIES)
REGISTRY.register(l5_portal_reader.ENTRIES)
REGISTRY.register(l5_methodology_reader.ENTRIES)
REGISTRY.register(l5_history_documents_reader.ENTRIES)
REGISTRY.register(l5_search_reader.ENTRIES)

# Reader owns its bilingual templates, while this module owns the one validated
# process-wide registry.  Registration here makes Reader copy available to the
# default request Translator exactly once and keeps duplicate keys fail closed.
from . import reader as reader_catalog  # noqa: E402

READER_CATALOG = reader_catalog.ENTRIES
REGISTRY.register(READER_CATALOG)

from . import material_reading, plain_result, source_support  # noqa: E402

REGISTRY.register(material_reading.ENTRIES)
REGISTRY.register(plain_result.ENTRIES)
REGISTRY.register(source_support.ENTRIES)


__all__ = [
    "CATALOG",
    "NAVIGATION_CATALOG",
    "PAGINATION_CATALOG",
    "READER_CATALOG",
    "REGISTRY",
    "SHELL_CATALOG",
    "CatalogError",
    "CatalogRegistry",
    "merge",
    "register",
]
