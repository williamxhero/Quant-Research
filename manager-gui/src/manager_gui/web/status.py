"""Reusable localized status and operational-state rendering for the shared shell."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from html import escape

from ..models import ManagerReadModel, ReadModelError, ReadModelStatus
from .i18n import Translator, source_text


class DisplayState(StrEnum):
    """UI states intentionally distinct from source availability."""

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
    """Localized rendering metadata while preserving the machine status."""

    status: ReadModelStatus
    label: str
    tone: str
    explanation: str

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

_OPERATIONAL_STATE_TONES = {
    DisplayState.READY: "positive",
    DisplayState.LOADING: "accent",
    DisplayState.EMPTY: "quiet",
    DisplayState.PARTIAL: "warning",
    DisplayState.ERROR: "danger",
}


def _catalog_status_label(status: ReadModelStatus, translator: Translator) -> str:
    return translator.t(f"label.status.{status.value}")


def _catalog_status_explanation(status: ReadModelStatus, translator: Translator) -> str:
    return translator.t(f"status.explanation.{status.value}")


def _catalog_display_label(state: DisplayState, translator: Translator) -> str:
    return translator.t(f"label.display_state.{state.value}")


def _catalog_display_copy(state: DisplayState, translator: Translator) -> str:
    return translator.t(f"status.operational.{state.value}")


def describe_status(
    status: ReadModelStatus | str, *, translator: Translator | None = None
) -> StatusDescriptor:
    """Return localized metadata suitable for server HTML and future clients."""

    try:
        selected = ReadModelStatus(status)
    except ValueError as exc:
        raise ValueError(f"unknown Manager GUI status: {status!r}") from exc
    selected_translator = translator or Translator()
    return StatusDescriptor(
        status=selected,
        label=_catalog_status_label(selected, selected_translator),
        tone=_STATUS_TONES[selected],
        explanation=_catalog_status_explanation(selected, selected_translator),
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
    translator: Translator,
    detail: str | None = None,
) -> str:
    """Render localized operational copy and an optional verbatim owner note."""

    selected = DisplayState(state)
    label = _catalog_display_label(selected, translator)
    copy = _catalog_display_copy(selected, translator)
    live = ' aria-live="polite"' if selected is DisplayState.LOADING else ""
    source_note = (
        f'<p class="status-source-note"><strong>'
        f'{escape(translator.t("status.source_note"))}:</strong> {source_text(detail)}</p>'
        if detail is not None
        else ""
    )
    return (
        f'<section class="status-block tone-{_OPERATIONAL_STATE_TONES[selected]} '
        f'operational-state" data-display-state="{selected.value}"{live}>'
        f'<div class="status-line"><span class="status-mark" aria-hidden="true"></span>'
        f'<span class="status-label">{escape(label)}</span></div>'
        f"<h2>{escape(label)}</h2><p>{escape(copy)}</p>{source_note}</section>"
    )


def render_common_state(
    state_or_model: DisplayState | ReadModelStatus | ManagerReadModel | str,
    *,
    translator: Translator,
    reason: str | None = None,
    complete: bool | None = None,
    errors: Sequence[ReadModelError] = (),
) -> str:
    """Render the shared state vocabulary used by every page hook."""

    if isinstance(state_or_model, ManagerReadModel):
        return render_status_block(
            state_or_model,
            translator=translator,
            reason=reason,
            complete=complete,
            errors=errors,
        )
    if isinstance(state_or_model, DisplayState):
        return render_operational_state(state_or_model, translator=translator, detail=reason)
    try:
        return render_operational_state(
            DisplayState(state_or_model), translator=translator, detail=reason
        )
    except ValueError:
        return render_status_block(
            ReadModelStatus(state_or_model),
            translator=translator,
            reason=reason,
            complete=complete,
            errors=errors,
        )


def render_status_block(
    status_or_model: ReadModelStatus | str | ManagerReadModel,
    *,
    translator: Translator,
    reason: str | None = None,
    complete: bool | None = None,
    errors: Sequence[ReadModelError] = (),
) -> str:
    """Render a localized status headline/explanation and verbatim owner note."""

    if isinstance(status_or_model, ManagerReadModel):
        model = status_or_model
        status = model.availability.status
        reason = model.availability.reason
        complete = model.availability.complete
        errors = model.errors
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

    descriptor = describe_status(status, translator=translator)
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

    source_note = (
        f'<p class="status-source-note"><strong>'
        f'{escape(translator.t("status.source_note"))}:</strong> {source_text(reason)}</p>'
        if reason is not None
        else ""
    )
    rendered_errors = "".join(
        f"<li><strong>{escape(error.code)}</strong> {source_text(error.message)}</li>"
        for error in errors
    )
    errors_markup = (
        f'<ul class="status-errors" aria-label="{escape(translator.t("status.limitations"))}">'
        f"{rendered_errors}</ul>"
        if rendered_errors
        else ""
    )
    return (
        f'<section class="status-block tone-{descriptor.tone}" '
        f'data-status="{descriptor.status.value}" data-display-state="{state.value}" '
        f'aria-labelledby="status-heading-{descriptor.status.value}">'
        f'<div class="status-line"><span class="status-mark" aria-hidden="true"></span>'
        f'<span class="status-label">{escape(descriptor.label)}</span>'
        f'<span class="display-state">'
        f'{escape(_catalog_display_label(state, translator))}</span></div>'
        f'<h2 id="status-heading-{descriptor.status.value}">{escape(descriptor.label)}</h2>'
        f"<p>{escape(descriptor.explanation)}</p>{source_note}{errors_markup}</section>"
    )


__all__ = [
    "DISPLAY_STATE_LABELS",
    "DisplayState",
    "StatusDescriptor",
    "describe_status",
    "display_state_for",
    "render_common_state",
    "render_operational_state",
    "render_status_block",
]
