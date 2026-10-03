"""Stable shared navigation for every Manager GUI surface."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ViewId(StrEnum):
    """URL-stable identifiers for the shell's top-level views."""

    ATLAS = "atlas"
    STORIES = "stories"
    STRATEGIES = "strategies"
    MEMORY = "memory"
    EVIDENCE = "evidence"
    METHODOLOGY = "methodology"
    HISTORY = "history"
    SEARCH = "search"


@dataclass(frozen=True, slots=True)
class NavigationItem:
    """One navigation item and its future integration hook."""

    view_id: ViewId
    label: str
    short_label: str
    description: str
    integration_hook: str


NAVIGATION: tuple[NavigationItem, ...] = (
    NavigationItem(
        ViewId.ATLAS,
        "Atlas",
        "AT",
        "Workspace map and current read-model scope.",
        "atlas-view",
    ),
    NavigationItem(
        ViewId.STORIES,
        "Stories",
        "ST",
        "Research story index and provenance trail.",
        "research-story-view",
    ),
    NavigationItem(
        ViewId.STRATEGIES,
        "Strategies / Genomes",
        "SG",
        "Strategy and genome read surfaces.",
        "strategy-genome-view",
    ),
    NavigationItem(
        ViewId.MEMORY,
        "Memory",
        "ME",
        "Failure knowledge and retained research memory.",
        "memory-view",
    ),
    NavigationItem(
        ViewId.EVIDENCE,
        "Evidence",
        "EV",
        "Evidence lineage, source references, and comparisons.",
        "evidence-view",
    ),
    NavigationItem(
        ViewId.METHODOLOGY,
        "Methodology",
        "MO",
        "Methods, contracts, and interpretation notes.",
        "methodology-view",
    ),
    NavigationItem(
        ViewId.HISTORY,
        "History",
        "HI",
        "Historical snapshots and source revisions.",
        "history-view",
    ),
    NavigationItem(
        ViewId.SEARCH,
        "Search",
        "SE",
        "Search across approved read-model records.",
        "search-view",
    ),
)

NAVIGATION_BY_ID = {item.view_id: item for item in NAVIGATION}


def navigation_item(value: ViewId | str) -> NavigationItem:
    """Return a navigation item, raising a useful error for unknown URLs."""

    try:
        return NAVIGATION_BY_ID[ViewId(value)]
    except (KeyError, ValueError) as exc:
        raise ValueError(f"unknown Manager GUI view: {value!r}") from exc


__all__ = ["NAVIGATION", "NAVIGATION_BY_ID", "NavigationItem", "ViewId", "navigation_item"]
