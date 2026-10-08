from __future__ import annotations

from collections.abc import Mapping
from html import escape

from ..models import ManagerReadModel, ReadModelStatus
from .comparison_reader import ComparisonReaderViewModel
from .conditions import ConditionViewModel
from .failure_grouping import FailureGroupingViewModel
from .failure_patterns import FailureViewModel
from .genome import GenomeViewModel
from .i18n import Translator
from .memory import MemoryViewModel
from .methodology import MethodologyViewModel
from .status import render_status_block

_COLLECTIONS = {
    "genomes": ("genomes",),
    "genome_conditions": (
        "conditions",
        "condition_evidence",
        "applicability_conditions",
        "invalidation_conditions",
        "failure_conditions",
        "descriptors",
    ),
    "genome_comparison": ("comparisons",),
    "memory": ("memory_entries", "entries", "failures", "failure_records"),
    "failure_patterns": ("patterns", "failure_patterns", "derived_patterns"),
    "failure_grouping": (
        "groups",
        "groupings",
        "derived_groupings",
        "derived_groups",
        "failure_groupings",
        "success_failure_groupings",
    ),
    "evidence_comparison": ("comparisons",),
    "methodology": ("methods", "methodologies"),
}
RESOURCES = frozenset(_COLLECTIONS)


def _has_entries(model: ManagerReadModel, resource: str, view: str) -> bool:
    if resource == "genomes":
        return bool(GenomeViewModel.from_read_model(model).catalog)
    if resource == "genome_conditions":
        return bool(ConditionViewModel.from_read_model(model).evidence)
    if resource == "memory":
        if view == "memory-failures":
            return bool(FailureViewModel.from_read_model(model).all_failures)
        return bool(MemoryViewModel.from_read_model(model).entries)
    if resource == "failure_patterns":
        return bool(FailureViewModel.from_read_model(model).patterns)
    if resource == "failure_grouping":
        return bool(FailureGroupingViewModel.from_read_model(model).groups)
    if resource == "methodology":
        return bool(MethodologyViewModel.from_read_model(model).methods)
    if ComparisonReaderViewModel.from_read_model(model).comparison is not None:
        return True
    root = model.data if isinstance(model.data, Mapping) else {}
    return any(
        root.get(key)
        for key in (
            "comparison_reader",
            "comparison",
            "object_comparison",
            "evidence_comparison",
            "left",
            "objects",
        )
    )


def _empty_collection(model: ManagerReadModel, resource: str) -> bool:
    root = model.data if isinstance(model.data, Mapping) else {}
    values = [root[key] for key in _COLLECTIONS[resource] if key in root]
    return bool(values) and all(isinstance(value, list) and not value for value in values)


def _message(model: ManagerReadModel, *, has_entries: bool, resource: str) -> str:
    status = model.availability.status
    if status is ReadModelStatus.API_UNAVAILABLE:
        return (
            "read_failed"
            if any(error.code != "api_unavailable" for error in model.errors)
            else "cannot_list"
        )
    if status in {
        ReadModelStatus.MISSING,
        ReadModelStatus.BLOCKED,
        ReadModelStatus.STALE,
        ReadModelStatus.INTEGRITY_FAILURE,
        ReadModelStatus.INCOMPARABLE,
    }:
        return status.value
    if model.errors:
        return "read_failed"
    if not model.availability.complete:
        return "partial"
    if has_entries:
        return "supplied"
    if status is ReadModelStatus.KNOWN and _empty_collection(model, resource):
        return "confirmed_empty"
    return "object_fields" if model.data else "missing"


def render_resource_reading(
    model: ManagerReadModel,
    *,
    resource: str,
    view: str,
    title: str,
    page: str,
    translator: Translator,
) -> str:
    has_entries = _has_entries(model, resource, view)
    message = _message(model, has_entries=has_entries, resource=resource)
    reason = (
        f'<p data-owner-text="true" translate="no">{escape(model.availability.reason)}</p>'
        if model.availability.reason
        else ""
    )
    errors = "".join(
        f"<li><code>{escape(error.code)}</code> "
        f'<span data-owner-text="true" translate="no">{escape(error.message)}</span></li>'
        for error in model.errors
    )
    notice = (
        f'<section data-resource-reading="{resource}" '
        f'data-status="{model.availability.status.value}" role="note">'
        f"<p>{translator.html('resource_reading.' + message)}</p>"
        f"<p>{translator.html('resource_reading.impact.' + view)}</p>"
        f"<p>{translator.html('resource_reading.unknown_fields')}</p>"
        f"{reason}{'<ul>' + errors + '</ul>' if errors else ''}</section>"
    )
    if has_entries:
        return notice + page
    return (
        f'<section class="resource-reading-page"><h1>{escape(title)}</h1>{notice}'
        f"{render_status_block(model, translator=translator)}"
        f"<details><summary>{translator.html('reader.raw_source')}</summary>"
        f'<pre translate="no">{escape(model.to_json(indent=2))}</pre></details></section>'
    )
