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
from .i18n import Translator, source_text


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

DISPLAY_STATE_LABELS_ZH = {
    DisplayState.READY: "就绪",
    DisplayState.LOADING: "加载中",
    DisplayState.EMPTY: "空结果",
    DisplayState.PARTIAL: "部分可用",
    DisplayState.ERROR: "错误",
}


@dataclass(frozen=True, slots=True)
class StatusDescriptor:
    """Human-readable rendering metadata while preserving the machine status."""

    status: ReadModelStatus
    label: str
    tone: str
    explanation: str

    @property
    def label_zh(self) -> str:
        """Chinese label without changing the existing descriptor constructor."""

        return _STATUS_LABELS_ZH[self.status]


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

# The Chinese vocabulary is frozen by #655/#662.  These values are retained for
# compatibility helpers; localized rendering reads the same values from the catalog.
_STATUS_LABELS_ZH = {
    ReadModelStatus.KNOWN: "已记录",
    ReadModelStatus.DERIVED: "已派生",
    ReadModelStatus.INTERPRETED: "已解读",
    ReadModelStatus.MISSING: "未记录",
    ReadModelStatus.BLOCKED: "已阻塞",
    ReadModelStatus.STALE: "已过时",
    ReadModelStatus.INCOMPARABLE: "不可比较",
    ReadModelStatus.INTEGRITY_FAILURE: "完整性校验失败",
    ReadModelStatus.API_UNAVAILABLE: "API 不可用",
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


def _status_label(status: ReadModelStatus, translator: Translator | None) -> str:
    if translator is None:
        return _STATUS_LABELS[status]
    return translator.t(f"label.status.{status.value}")


def _status_explanation(status: ReadModelStatus, translator: Translator | None) -> str:
    if translator is None:
        return STATUS_SEMANTICS[status]
    return translator.t(f"status.explanation.{status.value}")


def _display_label(state: DisplayState, translator: Translator | None) -> str:
    if translator is None:
        return DISPLAY_STATE_LABELS[state]
    return translator.t(f"label.display_state.{state.value}")


def _display_copy(state: DisplayState, translator: Translator | None) -> str:
    if translator is None:
        return _OPERATIONAL_STATE_COPY[state]
    return translator.t(f"status.operational.{state.value}")


def describe_status(
    status: ReadModelStatus | str, *, translator: Translator | None = None
) -> StatusDescriptor:
    """Return stable copy suitable for both server HTML and future clients."""

    try:
        selected = ReadModelStatus(status)
    except ValueError as exc:
        raise ValueError(f"unknown Manager GUI status: {status!r}") from exc
    return StatusDescriptor(
        status=selected,
        label=_status_label(selected, translator),
        tone=_STATUS_TONES[selected],
        explanation=_status_explanation(selected, translator),
    )


def status_label_zh(status: ReadModelStatus | str) -> str:
    """Return the stable Chinese accessibility label for a source status."""

    return _STATUS_LABELS_ZH[ReadModelStatus(status)]


def display_state_label_zh(state: DisplayState | str) -> str:
    """Return the stable Chinese accessibility label for an operational state."""

    return DISPLAY_STATE_LABELS_ZH[DisplayState(state)]


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
    translator: Translator | None = None,
) -> str:
    """Render an operational state, keeping optional owner detail as source text."""

    selected = DisplayState(state)
    tone = _OPERATIONAL_STATE_TONES[selected]
    label = _display_label(selected, translator)
    copy = _display_copy(selected, translator)
    live = ' aria-live="polite"' if selected is DisplayState.LOADING else ""
    if translator is None:
        label_zh = DISPLAY_STATE_LABELS_ZH[selected]
        return (
            f'<section class="status-block tone-{tone} operational-state" '
            f'data-display-state="{selected.value}" data-display-state-label-zh="{label_zh}"{live}>'
            f'<div class="status-line"><span class="status-mark" aria-hidden="true"></span>'
            f'<span class="status-label">{escape(label)}</span>'
            f'<span class="status-label-zh" lang="zh-CN">{escape(label_zh)}</span></div>'
            f"<h2>{escape(copy if detail is None else detail)}</h2>"
            f"<p>{escape(copy)}</p></section>"
        )
    source = (
        f'<p class="status-source-note"><strong>{escape(translator.t("status.source_note"))}:</strong> '
        f"{source_text(detail)}</p>"
        if detail is not None
        else ""
    )
    return (
        f'<section class="status-block tone-{tone} operational-state" '
        f'data-display-state="{selected.value}"{live}>'
        f'<div class="status-line"><span class="status-mark" aria-hidden="true"></span>'
        f'<span class="status-label">{escape(label)}</span></div>'
        f"<h2>{escape(label)}</h2><p>{escape(copy)}</p>{source}</section>"
    )


def render_common_state(
    state_or_model: DisplayState | ReadModelStatus | ManagerReadModel | str,
    *,
    reason: str | None = None,
    complete: bool | None = None,
    errors: Sequence[ReadModelError] = (),
    translator: Translator | None = None,
) -> str:
    """Render the shared state vocabulary used by every page hook."""

    if isinstance(state_or_model, ManagerReadModel):
        return render_status_block(
            state_or_model,
            reason=reason,
            complete=complete,
            errors=errors,
            translator=translator,
        )
    if isinstance(state_or_model, DisplayState):
        return render_operational_state(state_or_model, detail=reason, translator=translator)
    try:
        return render_operational_state(
            DisplayState(state_or_model), detail=reason, translator=translator
        )
    except ValueError:
        return render_status_block(
            ReadModelStatus(state_or_model),
            reason=reason,
            complete=complete,
            errors=errors,
            translator=translator,
        )


def render_status_block(
    status_or_model: ReadModelStatus | str | ManagerReadModel,
    *,
    reason: str | None = None,
    complete: bool | None = None,
    errors: Sequence[ReadModelError] = (),
    translator: Translator | None = None,
) -> str:
    """Render one accessible status block while preserving owner reason verbatim."""

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

    if translator is None:
        reason_text = reason or descriptor.explanation
        rendered_errors = "".join(
            f"<li><strong>{escape(error.code)}</strong> {escape(error.message)}</li>"
            for error in errors
        )
        errors_markup = (
            f'<ul class="status-errors" aria-label="Read-model limitations">{rendered_errors}</ul>'
            if rendered_errors
            else ""
        )
        return (
            f'<section class="status-block tone-{descriptor.tone}" '
            f'data-status="{descriptor.status.value}" '
            f'data-status-label-zh="{escape(descriptor.label_zh, quote=True)}" '
            f'data-display-state="{state.value}" '
            f'data-display-state-label-zh="{escape(DISPLAY_STATE_LABELS_ZH[state], quote=True)}" '
            f'aria-labelledby="status-heading-{descriptor.status.value}">'
            f'<div class="status-line"><span class="status-mark" aria-hidden="true"></span>'
            f'<span class="status-label">{escape(descriptor.label)}</span>'
            f'<span class="status-label-zh" lang="zh-CN">{escape(descriptor.label_zh)}</span>'
            f'<span class="display-state">{escape(DISPLAY_STATE_LABELS[state])} · '
            f'<span lang="zh-CN">{escape(DISPLAY_STATE_LABELS_ZH[state])}</span></span></div>'
            f'<h2 id="status-heading-{descriptor.status.value}">{escape(reason_text)}</h2>'
            f"<p>{escape(descriptor.explanation)}</p>{errors_markup}</section>"
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
    source_note = (
        f'<p class="status-source-note"><strong>{escape(translator.t("status.source_note"))}:</strong> '
        f"{source_text(reason)}</p>"
        if reason is not None
        else ""
    )
    return (
        f'<section class="status-block tone-{descriptor.tone}" '
        f'data-status="{descriptor.status.value}" data-display-state="{state.value}" '
        f'aria-labelledby="status-heading-{descriptor.status.value}">'
        f'<div class="status-line"><span class="status-mark" aria-hidden="true"></span>'
        f'<span class="status-label">{escape(descriptor.label)}</span>'
        f'<span class="display-state">{escape(_display_label(state, translator))}</span></div>'
        f'<h2 id="status-heading-{descriptor.status.value}">{escape(descriptor.label)}</h2>'
        f"<p>{escape(descriptor.explanation)}</p>{source_note}{errors_markup}</section>"
    )


__all__ = [
    "DISPLAY_STATE_LABELS",
    "DISPLAY_STATE_LABELS_ZH",
    "DisplayState",
    "StatusDescriptor",
    "describe_status",
    "display_state_for",
    "display_state_label_zh",
    "render_common_state",
    "render_operational_state",
    "render_status_block",
    "status_label_zh",
]
