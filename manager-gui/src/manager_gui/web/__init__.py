"""Fixture-backed, read-only WebUI shell for the Manager GUI.

The web package owns only shared shell concerns. Domain pages can register their
own read-only views later without changing the transport envelope or provider
boundary from S1-T1.
"""

from .app import ManagerGUIApp, WebRequestState
from .navigation import NAVIGATION, NavigationItem, ViewId
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
    "DISPLAY_STATE_LABELS",
    "NAVIGATION",
    "DisplayState",
    "ManagerGUIApp",
    "NavigationItem",
    "StatusDescriptor",
    "ViewId",
    "WebRequestState",
    "create_server",
    "describe_status",
    "display_state_for",
    "render_operational_state",
    "render_status_block",
    "run_server",
]
