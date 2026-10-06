"""Compatibility import surface for the R5 History Reader."""

from .history_documents_reader import (
    HISTORY_DOCUMENTS_SCOPES,
    HISTORY_READER_HOOK,
    HISTORY_READER_INTEGRATION_HOOK,
    HISTORY_READER_RESOURCE,
    HISTORY_READER_RULE,
    HISTORY_READER_VERSION,
    HistoryDocumentsReaderView,
    HistoryReaderViewModel,
    build_history_reader_fixture,
    history_reader_fixture_provider,
    history_reader_view,
    project_history_reader,
    project_reader_history,
    render_history_reader,
    render_history_reader_view,
    render_reader_history,
)

__all__ = [
    "HISTORY_DOCUMENTS_SCOPES",
    "HISTORY_READER_HOOK",
    "HISTORY_READER_INTEGRATION_HOOK",
    "HISTORY_READER_RESOURCE",
    "HISTORY_READER_RULE",
    "HISTORY_READER_VERSION",
    "HistoryDocumentsReaderView",
    "HistoryReaderViewModel",
    "build_history_reader_fixture",
    "history_reader_fixture_provider",
    "history_reader_view",
    "project_history_reader",
    "project_reader_history",
    "render_history_reader",
    "render_history_reader_view",
    "render_reader_history",
]
