"""Integrated Search and Portal fixtures for the shared S6 shell.

The shell exposes one fixture selector for every mounted route.  Search and
Portal own their complete/partial/empty/integrity/API-specific envelopes; the
remaining shared selectors use the generic read-model envelope so their source
status and limitations remain visible rather than being relabeled as empty.
No fixture builder reads storage or dereferences a locator.
"""

from __future__ import annotations

from ..fixtures import FixtureState, build_fixture
from ..models import ManagerReadModel
from .portal import REPORT_SOURCE_RESOURCE, build_portal_fixture
from .search import SEARCH_RESOURCE, SearchFixtureState, build_search_fixture

S6_RESOURCES = frozenset({SEARCH_RESOURCE, REPORT_SOURCE_RESOURCE})
S6_FIXTURE_STATES = frozenset(FixtureState)


def build_s6_fixture(resource: str, state: FixtureState | str) -> ManagerReadModel:
    """Build one integrated S6 envelope for every shared fixture selector."""

    selected = FixtureState(state)
    if resource == SEARCH_RESOURCE:
        if selected in {
            FixtureState.COMPLETE,
            FixtureState.PARTIAL,
            FixtureState.EMPTY,
            FixtureState.API_UNAVAILABLE,
        }:
            search_state = SearchFixtureState(selected.value)
            return build_search_fixture(search_state)
        return build_fixture(selected, resource=resource)
    if resource == REPORT_SOURCE_RESOURCE:
        if selected is FixtureState.COMPLETE:
            return build_portal_fixture("complete")
        if selected is FixtureState.PARTIAL:
            return build_portal_fixture("partial")
        if selected is FixtureState.EMPTY:
            return build_portal_fixture("missing")
        if selected is FixtureState.INTEGRITY_FAILURE:
            return build_portal_fixture("integrity_failure")
        if selected is FixtureState.API_UNAVAILABLE:
            return build_portal_fixture("api_unavailable")
        return build_fixture(selected, resource=resource)
    raise ValueError(f"{resource!r} is not an S6 resource")


__all__ = ["S6_FIXTURE_STATES", "S6_RESOURCES", "build_s6_fixture"]
