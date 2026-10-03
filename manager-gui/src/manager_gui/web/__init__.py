"""Fixture-backed, read-only WebUI shell for the Manager GUI.

The web package owns the shared shell and the S1 page-hook mounts. Later domain
pages can register their own read-only views without changing the transport
envelope or provider boundary from S1-T1.
"""

from .app import ManagerGUIApp, WebRequestState
from .atlas import ATLAS_INTEGRATION_HOOK, render_atlas_view
from .navigation import NAVIGATION, NavigationItem, ViewId
from .research_story import (
    StoryMode,
    render_research_story,
    render_research_story_view,
)
from .server import create_server, run_server
from .status import (
    DISPLAY_STATE_LABELS,
    DisplayState,
    StatusDescriptor,
    describe_status,
    display_state_for,
    render_operational_state,
    render_status_block,
)

__all__ = [
    "ATLAS_INTEGRATION_HOOK",
    "DISPLAY_STATE_LABELS",
    "NAVIGATION",
    "DisplayState",
    "ManagerGUIApp",
    "NavigationItem",
    "StatusDescriptor",
    "StoryMode",
    "ViewId",
    "WebRequestState",
    "create_server",
    "describe_status",
    "display_state_for",
    "render_atlas_view",
    "render_operational_state",
    "render_research_story",
    "render_research_story_view",
    "render_status_block",
    "run_server",
]
