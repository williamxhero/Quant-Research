"""Fixture-backed, read-only WebUI shell for the Manager GUI.

The web package owns the shared shell and the S1 page-hook mounts. Later domain
pages can register their own read-only views without changing the transport
envelope or provider boundary from S1-T1.
"""

from .app import ManagerGUIApp, WebRequestState
from .atlas import ATLAS_INTEGRATION_HOOK, render_atlas_view
from .comparison import (
    COMPARISON_INTEGRATION_HOOK,
    COMPARISON_ROUTE,
    render_genome_comparison_view,
)
from .conditions import (
    CONDITIONS_INTEGRATION_HOOK,
    CONDITIONS_ROUTE,
    render_genome_conditions_view,
)
from .documents import (
    ApprovedDirectoryBoundary,
    DocumentIndexState,
    DocumentType,
    SourceDocument,
    SourceDocumentsViewModel,
    render_source_documents_view,
)
from .failure_patterns import (
    FAILURE_PATTERNS_INTEGRATION_HOOK,
    FAILURE_PATTERNS_RESOURCE,
    MEMORY_FAILURE_INTEGRATION_HOOK,
    MEMORY_FAILURE_RESOURCE,
    render_failure_patterns_view,
    render_memory_failure_view,
)
from .genome import GENOME_INTEGRATION_HOOK, GENOME_ROUTE, render_genome_view
from .history import (
    HISTORY_SCOPES,
    HistoryEvent,
    HistoryEventType,
    HistoryViewModel,
    render_history_view,
)
from .interaction import (
    EXPORT_ENDPOINT,
    EXPORT_SCHEMA,
    current_view_export,
    export_filename,
    export_json,
    export_url,
    opaque_copy_button,
    render_alternative_view,
    render_current_view_export,
    render_export_control,
    render_graph_table_alternative,
    render_view_mode_controls,
)
from .memory import MEMORY_INTEGRATION_HOOK, render_memory_view
from .methodology import (
    METHODOLOGY_INTEGRATION_HOOK,
    MethodologyCategory,
    MethodologyIndexState,
    MethodologyMethod,
    MethodologyViewModel,
    render_methodology_view,
)
from .navigation import (
    NAVIGATION,
    NavigationItem,
    PageWindow,
    ViewId,
    clear_filters_link,
    context_link,
    navigation_label_zh,
    query_values,
)
from .research_story import (
    StoryMode,
    render_research_story,
    render_research_story_view,
)
from .server import create_server, run_server
from .status import (
    DISPLAY_STATE_LABELS,
    DISPLAY_STATE_LABELS_ZH,
    DisplayState,
    StatusDescriptor,
    describe_status,
    display_state_for,
    display_state_label_zh,
    render_common_state,
    render_operational_state,
    render_status_block,
    status_label_zh,
)

__all__ = [
    "ATLAS_INTEGRATION_HOOK",
    "COMPARISON_INTEGRATION_HOOK",
    "COMPARISON_ROUTE",
    "CONDITIONS_INTEGRATION_HOOK",
    "CONDITIONS_ROUTE",
    "DISPLAY_STATE_LABELS",
    "DISPLAY_STATE_LABELS_ZH",
    "EXPORT_ENDPOINT",
    "EXPORT_SCHEMA",
    "FAILURE_PATTERNS_INTEGRATION_HOOK",
    "FAILURE_PATTERNS_RESOURCE",
    "GENOME_INTEGRATION_HOOK",
    "GENOME_ROUTE",
    "HISTORY_SCOPES",
    "MEMORY_FAILURE_INTEGRATION_HOOK",
    "MEMORY_FAILURE_RESOURCE",
    "MEMORY_INTEGRATION_HOOK",
    "METHODOLOGY_INTEGRATION_HOOK",
    "NAVIGATION",
    "ApprovedDirectoryBoundary",
    "DisplayState",
    "DocumentIndexState",
    "DocumentType",
    "HistoryEvent",
    "HistoryEventType",
    "HistoryViewModel",
    "ManagerGUIApp",
    "MethodologyCategory",
    "MethodologyIndexState",
    "MethodologyMethod",
    "MethodologyViewModel",
    "NavigationItem",
    "PageWindow",
    "SourceDocument",
    "SourceDocumentsViewModel",
    "StatusDescriptor",
    "StoryMode",
    "ViewId",
    "WebRequestState",
    "clear_filters_link",
    "context_link",
    "create_server",
    "current_view_export",
    "describe_status",
    "display_state_for",
    "display_state_label_zh",
    "export_filename",
    "export_json",
    "export_url",
    "navigation_label_zh",
    "opaque_copy_button",
    "query_values",
    "render_alternative_view",
    "render_atlas_view",
    "render_common_state",
    "render_current_view_export",
    "render_export_control",
    "render_failure_patterns_view",
    "render_genome_comparison_view",
    "render_genome_conditions_view",
    "render_genome_view",
    "render_graph_table_alternative",
    "render_history_view",
    "render_memory_failure_view",
    "render_memory_view",
    "render_methodology_view",
    "render_operational_state",
    "render_research_story",
    "render_research_story_view",
    "render_source_documents_view",
    "render_status_block",
    "render_view_mode_controls",
    "run_server",
    "status_label_zh",
]
