from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any

from manager_gui.models import ManagerReadModel, ReadModelStatus

_UNKNOWN_FIELDS = (
    "target", "author", "complete_trading_rules", "amount", "currency", "costs_included",
    "period", "market",
)
_COLLECTIONS = {
    "atlas": ("records",),
    "stories": ("intent", "hypothesis", "design", "attempts", "evidence", "conclusions"),
    "strategies": ("genomes",),
    "strategy-conditions": ("conditions",),
    "strategy-genome-comparison": ("comparisons",),
    "memory": ("memory_entries",),
    "memory-failures": ("failures",),
    "failure-patterns": ("patterns",),
    "evidence": ("records",),
    "lineage": ("relations",),
    "evidence-object-comparison": ("comparisons",),
    "derived-failure-grouping": ("groups",),
    "methodology": ("methods",),
    "history": ("events",),
    "source-documents": ("documents",),
    "search": ("records",),
    "portal": ("reports",),
}


def reading_answer(model: ManagerReadModel, *, view: str, commit: str) -> dict[str, Any]:
    data: dict[str, Any] = model.data if isinstance(model.data, dict) else {}
    coverage = data.get("coverage")
    if not isinstance(coverage, dict):
        coverage = next(
            (scope for error in model.errors if error.details
             if isinstance(scope := error.details.get("coverage"), dict)), {}
        )
    records = []
    refs = {ref.source_id: ref.to_dict() for ref in model.source_refs}
    sources = {source.get("source_id"): source for source in data.get("sources", [])}
    for collection in _COLLECTIONS[view]:
        for index, record in enumerate(data.get(collection, [])):
            identifier = next(
                (record[key] for key in ("record_id", "document_id", "id") if key in record), None
            )
            source_id = record.get("source_ref")
            source = refs.get(source_id)
            original = sources.get(record.get("original_source_id"))
            limitation = None
            if original is not None:
                original_ref = refs.get(original.get("source_id"), {})
                if original.get("read_status") != "known":
                    limitation = original.get("read_status") or "unreadable"
                elif (
                    original.get("snapshot_token") != model.snapshot_token
                    or record.get("original_snapshot_token") != model.snapshot_token
                    or original.get("source_revision") != record.get("original_source_revision")
                    or original.get("source_revision") != original_ref.get("revision")
                ):
                    limitation = "stale"
                elif not isinstance(original.get("text"), str):
                    limitation = "unreadable"
            records.append({
                "pointer": f"/data/{collection}/{index}",
                "identity": identifier,
                "title": record.get("title"),
                "source": deepcopy(source),
                "provided": deepcopy({
                    key: value for key, value in record.items()
                    if key not in {"raw_source", "source_publication", "snapshot_token"}
                }),
                "unknowns": {key: None for key in _UNKNOWN_FIELDS if record.get(key) is None},
                "original": {
                    "source_id": original.get("source_id"),
                    "revision": original.get("source_revision"),
                    "read_status": original.get("read_status"),
                    "readable": limitation is None,
                    "limitation": limitation,
                } if original is not None else None,
            })
    status = model.availability.status
    kind = status.value
    if status is ReadModelStatus.API_UNAVAILABLE:
        kind = "cannot_enumerate" if not model.data else "read_failed"
    elif status is ReadModelStatus.KNOWN:
        if not model.availability.complete:
            kind = "partial"
        elif records:
            kind = "supplied"
        elif any(key in data for key in _COLLECTIONS[view]):
            kind = "confirmed_empty_within_scope"
        else:
            kind = "fields_missing"
    cannot = ["execution_is_not_research_success", "not_trading_permission"]
    if kind != "confirmed_empty_within_scope":
        cannot.append("absence_not_confirmed")
    if not coverage.get("global_catalog"):
        cannot.append("not_global_catalog")
    if not coverage.get("cross_resource_atomic_snapshot"):
        cannot.append("not_cross_resource_atomic")
    canonical = model.to_json(indent=2).encode("utf-8")
    return {
        "input": {
            "canonical_sha256": hashlib.sha256(canonical).hexdigest(),
            "canonical_bytes": len(canonical),
            "commit": commit,
            "view": view,
            "resource": coverage.get("resource"),
            "snapshot_token": model.snapshot_token,
            "as_of": model.as_of,
        },
        "coverage": deepcopy(coverage),
        "availability": model.availability.to_dict(),
        "errors": [error.to_dict() for error in model.errors],
        "source_refs": [ref.to_dict() for ref in model.source_refs],
        "result": {"kind": kind, "records": records},
        "unknowns": {key: None for key in _UNKNOWN_FIELDS} if not records else {},
        "unknown_field_boundary": "Missing projected field; raw_source is not searched or inferred.",
        "cannot_conclude": cannot,
    }
