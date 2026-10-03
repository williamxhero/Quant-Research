"""Reusable status and operational-state rendering for the shared shell."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from html import escape

from ..models import (
    STATUS_SEMANTICS,
    ManagerReadModel,
    ReadModelError,
    ReadModelStatus,
)


class DisplayState(StrEnum):
    """UI states that are intentionally distinct from source availability."""

    READY = "ready"
    LOADING = "loading"
    EMPTY = "empty"
    PARTIAL = "partial"
    ERROR = "error"


DISPLAY_STATE_LABELS = {
    DisplayState.READY: "Ready",
    DisplayState.LOADING: "Loading",
    DisplayState.EMPTY: "Empty",
    DisplayState.PARTIAL: "Partial",
    DisplayState.ERROR: "Error",
}


@dataclass(frozen=True, slots=True)
class StatusDescriptor:
    """Human-readable rendering metadata while preserving the machine status."""

    status: ReadModelStatus
    label: str
    tone: str
    explanation: str


_STATUS_LABELS = {
    ReadModelStatus.KNOWN: "Known",
    ReadModelStatus.DERIVED: "Derived",
    ReadModelStatus.INTERPRETED: "Interpreted",
    ReadModelStatus.MISSING: "Missing",
    ReadModelStatus.BLOCKED: "Blocked",
    ReadModelStatus.STALE: "Stale",
    ReadModelStatus.INCOMPARABLE: "Incomparable",
    ReadModelStatus.INTEGRITY_FAILURE: "Integrity failure",
    ReadModelStatus.API_UNAVAILABLE: "API unavailable",
}

_STATUS_TONES = {
    ReadModelStatus.KNOWN: "positive",
    ReadModelStatus.DERIVED: "accent",
    ReadModelStatus.INTERPRETED: "accent",
    ReadModelStatus.MISSING: "quiet",
    ReadModelStatus.BLOCKED: "warning",
    ReadModelStatus.STALE: "warning",
    ReadModelStatus.INCOMPARABLE: "warning",
    ReadModelStatus.INTEGRITY_FAILURE: "danger",
    ReadModelStatus.API_UNAVAILABLE: "danger",
}

_OPERATIONAL_STATE_COPY = {
    DisplayState.READY: "The read-model is ready to inspect.",
    DisplayState.LOADING: "Reading the approved public source…",
    DisplayState.EMPTY: "No records are present in this scope.",
    DisplayState.PARTIAL: "Some expected records are not available yet.",
    DisplayState.ERROR: "The read-model cannot be used as complete current truth.",
}

_OPERATIONAL_STATE_TONES = {
    DisplayState.READY: "positive",
    DisplayState.LOADING: "accent",
    DisplayState.EMPTY: "quiet",
    DisplayState.PARTIAL: "warning",
    DisplayState.ERROR: "danger",
}


def describe_status(status: ReadModelStatus | str) -> StatusDescriptor:
    """Return stable copy suitable for both server HTML and future clients."""

    try:
        selected = ReadModelStatus(status)
    except ValueError as exc:
        raise ValueError(f"unknown Manager GUI status: {status!r}") from exc
    return StatusDescriptor(
        status=selected,
        label=_STATUS_LABELS[selected],
        tone=_STATUS_TONES[selected],
        explanation=STATUS_SEMANTICS[selected],
    )


def display_state_for(model: ManagerReadModel) -> DisplayState:
    """Map source availability to a separate user-facing loading/data state."""

    availability = model.availability
    if availability.status is ReadModelStatus.MISSING:
        return DisplayState.EMPTY
    if availability.status is ReadModelStatus.KNOWN and not availability.complete:
        return DisplayState.PARTIAL
    if availability.status in {
        ReadModelStatus.BLOCKED,
        ReadModelStatus.STALE,
        ReadModelStatus.INCOMPARABLE,
        ReadModelStatus.INTEGRITY_FAILURE,
        ReadModelStatus.API_UNAVAILABLE,
    }:
        return DisplayState.ERROR
    return DisplayState.READY


def render_operational_state(
    state: DisplayState | str,
    *,
    detail: str | None = None,
) -> str:
    """Render loading/empty/partial/error states without inventing a source status."""

    selected = DisplayState(state)
    label = DISPLAY_STATE_LABELS[selected]
    tone = _OPERATIONAL_STATE_TONES[selected]
    copy = detail or _OPERATIONAL_STATE_COPY[selected]
    live = ' aria-live="polite"' if selected is DisplayState.LOADING else ""
    return (
        f'<section class="status-block tone-{tone} operational-state" '
        f'data-display-state="{selected.value}"{live}>'
        f'<div class="status-line"><span class="status-mark" aria-hidden="true"></span>'
        f'<span class="status-label">{escape(label)}</span></div>'
        f"<h2>{escape(copy)}</h2></section>"
    )


def render_status_block(
    status_or_model: ReadModelStatus | str | ManagerReadModel,
    *,
    reason: str | None = None,
    complete: bool | None = None,
    errors: Sequence[ReadModelError] = (),
) -> str:
    """Render one accessible status block for any read-model surface.

    Passing a ``ManagerReadModel`` is the common path.  Passing a status keeps
    the renderer useful for loading placeholders and future page-local states.
    """

    if isinstance(status_or_model, ManagerReadModel):
        model = status_or_model
        status = status_or_model.availability.status
        reason = status_or_model.availability.reason
        complete = status_or_model.availability.complete
        errors = status_or_model.errors
    else:
        model = None
        status = ReadModelStatus(status_or_model)
        if complete is None:
            complete = status not in {
                ReadModelStatus.MISSING,
                ReadModelStatus.BLOCKED,
                ReadModelStatus.STALE,
                ReadModelStatus.INCOMPARABLE,
                ReadModelStatus.INTEGRITY_FAILURE,
                ReadModelStatus.API_UNAVAILABLE,
            }

    descriptor = describe_status(status)
    if model is not None:
        state = display_state_for(model)
    elif status is ReadModelStatus.MISSING:
        state = DisplayState.EMPTY
    elif status is ReadModelStatus.KNOWN and not complete:
        state = DisplayState.PARTIAL
    elif status in {
        ReadModelStatus.BLOCKED,
        ReadModelStatus.STALE,
        ReadModelStatus.INCOMPARABLE,
        ReadModelStatus.INTEGRITY_FAILURE,
        ReadModelStatus.API_UNAVAILABLE,
    }:
        state = DisplayState.ERROR
    else:
        state = DisplayState.READY
    reason_text = reason or descriptor.explanation
    rendered_errors = "".join(
        "".join(
            (
                "<li><strong>",
                escape(error.code),
                "</strong> ",
                escape(error.message),
                "</li>",
            )
        )
        for error in errors
    )
    errors_markup = (
        f'<ul class="status-errors" aria-label="Read-model limitations">{rendered_errors}</ul>'
        if rendered_errors
        else ""
    )
    return (
        f'<section class="status-block tone-{descriptor.tone}" '
        f'data-status="{descriptor.status.value}" data-display-state="{state.value}" '
        f'aria-labelledby="status-heading-{descriptor.status.value}">'
        f'<div class="status-line"><span class="status-mark" aria-hidden="true"></span>'
        f'<span class="status-label">{escape(descriptor.label)}</span>'
        f'<span class="display-state">{escape(DISPLAY_STATE_LABELS[state])}</span></div>'
        f'<h2 id="status-heading-{descriptor.status.value}">{escape(reason_text)}</h2>'
        f"<p>{escape(descriptor.explanation)}</p>{errors_markup}"
        "</section>"
    )


__all__ = [
    "DISPLAY_STATE_LABELS",
    "DisplayState",
    "StatusDescriptor",
    "describe_status",
    "display_state_for",
    "render_operational_state",
    "render_status_block",
]
