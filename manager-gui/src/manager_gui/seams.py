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

WORKSPACE_PUBLIC_READ_SEAM = ReadSeamDecision(
    seam_id="workspace-public-read",
    owner="strategy-workspace",
    contract="Zero-write WorkspaceClient public read APIs (verified read_only=True acceptance)",
    operations=(
        "get_run",
        "list_runs",
        "get_result",
        "get_record",
        "list_records",
        "get_registered_package",
        "query_lineage",
        "read_artifact",
    ),
    status="verified-readonly-acceptance",
    prohibited_fallbacks=(
        "private database",
        "private repository",
        "private lock",
        "private artifact path",
        "CLI stdout scraping",
        "materialize",
        "fixture fallback",
        "preinitialization",
    ),
    decision=(
        "Block lifted for the listed operations: the owner's staged zero-write acceptance "
        "(strategy-workspace R1 #5, R2 #6, R3 #7; verified commit 169ea0f, merged as 22aea590) "
        "proves each listed public read leaves the owner workspace byte-for-byte unchanged - no "
        "initialization, migration, writer lock, cursor-key creation or WAL/SHM sidecar - when "
        "the client is constructed explicitly with read_only=True on an existing compatible root. "
        "Governing prerequisites stay mandatory: an explicit read-only construction, a frozen "
        "share-mode view of an existing compatible database, and no active writer or sidecar. "
        "Verified limits are part of the contract: non-frozen, missing, unpublished-artifact and "
        "unreadable-artifact states stay unverifiable, a missing or invalid cursor key stays "
        "lineage_cursor_unavailable, and lists stay bounded. get_genome, inspect_package, "
        "validate_parameters, verify_artifact and doctor remain unapproved reads and must still "
        "report api_unavailable. W1 (#763) may implement the Workspace provider on exactly these "
        "operations with the same prohibited fallbacks; this declaration adds no new owner API and "
        "claims no read-only guarantee beyond the verified scope."
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
    WORKSPACE_PUBLIC_READ_SEAM.seam_id: WORKSPACE_PUBLIC_READ_SEAM,
    HISTORICAL_DOCUMENT_INDEX_SEAM.seam_id: HISTORICAL_DOCUMENT_INDEX_SEAM,
}

__all__ = [
    "HISTORICAL_DOCUMENT_INDEX_SEAM",
    "PACKAGE_CATALOG_SEAM",
    "READ_SEAM_DECISIONS",
    "WORKSPACE_PUBLIC_READ_SEAM",
    "ReadSeamDecision",
]
