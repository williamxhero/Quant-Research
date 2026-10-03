"""Explicit public-seam decisions for later Manager GUI slices.

These declarations are planning/contract metadata, not adapters.  Until the
owner publishes the named read API, the GUI must surface ``api_unavailable``
rather than inspect private storage or guess from filenames.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReadSeamDecision:
    """One owner-boundary decision that later pages must preserve."""

    seam_id: str
    owner: str
    contract: str
    operations: tuple[str, ...]
    status: str
    prohibited_fallbacks: tuple[str, ...]
    decision: str


PACKAGE_CATALOG_SEAM = ReadSeamDecision(
    seam_id="package-catalog",
    owner="strategy-workspace",
    contract="WorkspaceClient public package-catalog record read API",
    operations=("list_records", "get_record"),
    status="pending-public-catalog-record",
    prohibited_fallbacks=("private packages table", "workspace SQLite", "CLI stdout scraping"),
    decision=(
        "Choose a versioned package-catalog publication read through "
        "list_records(record_type=package_catalog), with get_record for detail. "
        "Until Workspace publishes that contract, Manager GUI reports api_unavailable and "
        "never infers packages from private storage."
    ),
)

HISTORICAL_DOCUMENT_INDEX_SEAM = ReadSeamDecision(
    seam_id="historical-document-index",
    owner="manager-gui",
    contract="Configured historical-document index adapter",
    operations=("search_documents", "get_document"),
    status="adapter-required",
    prohibited_fallbacks=("arbitrary filesystem scan", "private SQLite", "filename-as-identity"),
    decision=(
        "The adapter must expose stable document_id, document_type, revision, source reference, "
        "and relation metadata. A document is not promoted to an owner fact merely because it is "
        "indexed; interpretation remains marked interpreted and provenance-bearing."
    ),
)

READ_SEAM_DECISIONS = {
    PACKAGE_CATALOG_SEAM.seam_id: PACKAGE_CATALOG_SEAM,
    HISTORICAL_DOCUMENT_INDEX_SEAM.seam_id: HISTORICAL_DOCUMENT_INDEX_SEAM,
}

__all__ = [
    "HISTORICAL_DOCUMENT_INDEX_SEAM",
    "PACKAGE_CATALOG_SEAM",
    "READ_SEAM_DECISIONS",
    "ReadSeamDecision",
]
