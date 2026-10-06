"""Reader mode URL state and no-JavaScript presentation helpers.

This module is a UI-only seam.  It owns neither the Manager GUI shell nor an
owner read model: query state is opaque context, and Expert/Raw references point
back to the unchanged ManagerReadModel v0 bytes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from html import escape
import json
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from manager_gui.models import MANAGER_READ_MODEL_SCHEMA

from .models import ProjectionMode, ReaderProjection, SampleData

READER_MODE_QUERY_KEY = "mode"
READER_CONTEXT_KEYS = (
    "lang",
    "fixture",
    "scope",
    "root",
    "filter",
    "snapshot",
    "snapshot_token",
    "page",
    "page_size",
)
READER_MODE_VALUES = tuple(mode.value for mode in ProjectionMode)
SAMPLE_BANNER_TEXT = "样例数据，不代表真实研究结果"
SAMPLE_BANNER_TEXT_EN = "Sample data; not a real research result."
READER_SHELL_CONTRACT_SCHEMA = "manager-gui.reader-shell.v1"

_QueryPair = tuple[str, str]
_QueryContext = str | Mapping[str, object] | Sequence[tuple[str, object]]

_MODE_LABELS: Mapping[str, tuple[str, str]] = {
    ProjectionMode.READER.value: ("阅读模式", "Reader"),
    ProjectionMode.EXPERT.value: ("专业模式", "Expert"),
    ProjectionMode.RAW.value: ("原始模式", "Raw"),
}


def _pairs_from_context(context: _QueryContext | ReaderURLState | None) -> tuple[_QueryPair, ...]:
    """Read query pairs without collapsing repeated opaque state."""

    if context is None:
        return ()
    if isinstance(context, ReaderURLState):
        return context.pairs
    if isinstance(context, str):
        return tuple(parse_qsl(urlsplit(context).query, keep_blank_values=True))
    if isinstance(context, Mapping):
        pairs: list[_QueryPair] = []
        for key, value in context.items():
            key_text = str(key)
            if isinstance(value, (list, tuple)):
                pairs.extend((key_text, str(item)) for item in value if item is not None)
            elif value is not None:
                pairs.append((key_text, str(value)))
        return tuple(pairs)
    return tuple((str(key), str(value)) for key, value in context)


def _first_value(pairs: Sequence[_QueryPair], key: str) -> str | None:
    for pair_key, value in pairs:
        if pair_key == key:
            return value
    return None


def _mode(value: ProjectionMode | str | None) -> ProjectionMode:
    if value is None:
        return ProjectionMode.READER
    try:
        return ProjectionMode(value)
    except ValueError:
        return ProjectionMode.READER


def _locale_is_english(locale: str | None) -> bool:
    if locale is None:
        return False
    return locale.lower().replace("_", "-") in {"en", "en-us", "en-gb"}


@dataclass(frozen=True, slots=True)
class ReaderURLState:
    """A deterministic, shareable Reader URL state.

    Query pairs other than ``mode`` are opaque to this layer and are retained in
    their original order, including duplicate names and blank values.  When a
    duplicate key is interpreted as a scalar, the first value wins, matching the
    existing WebUI URL convention.  Duplicate ``mode`` values are replaced by a
    single canonical mode in generated URLs.
    """

    path: str = "/"
    pairs: tuple[_QueryPair, ...] = ()
    fragment: str = ""
    mode: ProjectionMode = ProjectionMode.READER

    def __post_init__(self) -> None:
        if not isinstance(self.path, str) or not self.path:
            raise ValueError("path must be a non-empty string")
        if not isinstance(self.mode, ProjectionMode):
            object.__setattr__(self, "mode", _mode(self.mode))
        normalized = tuple((str(key), str(value)) for key, value in self.pairs)
        object.__setattr__(self, "pairs", normalized)

    @classmethod
    def from_url(cls, url: str = "/") -> ReaderURLState:
        """Parse a URL, defaulting invalid or absent ``mode`` to Reader."""

        if not isinstance(url, str):
            raise TypeError("url must be a string")
        parsed = urlsplit(url)
        path = parsed.path or "/"
        pairs = tuple(parse_qsl(parsed.query, keep_blank_values=True))
        return cls(path, pairs, parsed.fragment, _mode(_first_value(pairs, READER_MODE_QUERY_KEY)))

    @classmethod
    def parse(cls, url: str = "/") -> ReaderURLState:
        """Alias for :meth:`from_url` for callers that prefer parser wording."""

        return cls.from_url(url)

    @property
    def query(self) -> tuple[_QueryPair, ...]:
        """All retained query pairs, including the current mode duplicates."""

        return self.pairs

    @property
    def context(self) -> tuple[_QueryPair, ...]:
        """Opaque query context with all ``mode`` pairs removed."""

        return tuple(pair for pair in self.pairs if pair[0] != READER_MODE_QUERY_KEY)

    @property
    def values(self) -> Mapping[str, str]:
        """First-value view for scalar context fields."""

        result: dict[str, str] = {}
        for key, value in self.context:
            result.setdefault(key, value)
        return result

    def value(self, key: str, default: str | None = None) -> str | None:
        """Return the first value for an opaque context key."""

        return self.values.get(key, default)

    @property
    def lang(self) -> str | None:
        return self.value("lang")

    @property
    def fixture(self) -> str | None:
        return self.value("fixture")

    @property
    def scope(self) -> str | None:
        return self.value("scope")

    @property
    def root(self) -> str | None:
        return self.value("root")

    @property
    def filter(self) -> str | None:
        return self.value("filter")

    @property
    def snapshot(self) -> str | None:
        return self.value("snapshot") or self.value("snapshot_token")

    def query_pairs(self, *, mode: ProjectionMode | str | None = None) -> tuple[_QueryPair, ...]:
        """Return canonical pairs with exactly one deterministic mode value."""

        selected = self.mode if mode is None else _mode(mode)
        pairs = list(self.context)
        first_mode = next(
            (index for index, (key, _) in enumerate(self.pairs) if key == READER_MODE_QUERY_KEY),
            None,
        )
        if first_mode is None:
            pairs.append((READER_MODE_QUERY_KEY, selected.value))
        else:
            # Keep the mode at the position of its first occurrence while removing
            # duplicate mode values.  All non-mode duplicate context stays intact.
            insertion = sum(1 for key, _ in self.pairs[:first_mode] if key != READER_MODE_QUERY_KEY)
            pairs.insert(insertion, (READER_MODE_QUERY_KEY, selected.value))
        return tuple(pairs)

    def url(self, *, mode: ProjectionMode | str | None = None) -> str:
        """Serialize state as a stable URL, retaining all opaque context."""

        query = urlencode(self.query_pairs(mode=mode), doseq=True)
        return urlunsplit(("", "", self.path, query, self.fragment))

    def to_url(self, *, mode: ProjectionMode | str | None = None) -> str:
        """Alias for :meth:`url`."""

        return self.url(mode=mode)

    def with_mode(self, mode: ProjectionMode | str) -> ReaderURLState:
        """Return an immutable state copy with one validated mode."""

        return ReaderURLState(self.path, self.pairs, self.fragment, _mode(mode))

    def mode_url(self, mode: ProjectionMode | str) -> str:
        """Build a no-JavaScript link to another Reader mode."""

        return self.url(mode=mode)


def parse_reader_url(url: str = "/") -> ReaderURLState:
    """Parse Reader URL state."""

    return ReaderURLState.from_url(url)


def reader_mode_url(
    context: _QueryContext | ReaderURLState | None,
    mode: ProjectionMode | str,
) -> str:
    """Build a stable mode link while preserving every non-mode query pair."""

    if isinstance(context, ReaderURLState):
        return context.mode_url(mode)
    state = ReaderURLState.from_url(context if isinstance(context, str) else "/")
    if not isinstance(context, str):
        state = ReaderURLState(pairs=_pairs_from_context(context))
    return state.mode_url(mode)


mode_url = reader_mode_url
build_mode_url = reader_mode_url


def _mode_label(
    mode: ProjectionMode,
    *,
    locale: str | None,
    labels: Mapping[str, str] | None = None,
) -> str:
    if labels is not None and mode.value in labels:
        return labels[mode.value]
    values = _MODE_LABELS[mode.value]
    return values[1] if _locale_is_english(locale) else values[0]


def _mode_group_label(*, locale: str | None) -> str:
    return "Reader modes" if _locale_is_english(locale) else "阅读模式切换"


def render_mode_switch(
    context: _QueryContext | ReaderURLState | None = None,
    *,
    locale: str | None = None,
    aria_label: str | None = None,
    labels: Mapping[str, str] | None = None,
    current_attribute: str = "page",
) -> str:
    """Render accessible GET links for Reader/Expert/Raw without JavaScript."""

    state = context if isinstance(context, ReaderURLState) else ReaderURLState.from_url(
        context if isinstance(context, str) else "/"
    )
    if not isinstance(context, (str, ReaderURLState)):
        state = ReaderURLState(pairs=_pairs_from_context(context))
    group_label = aria_label or _mode_group_label(locale=locale)
    links: list[str] = []
    for selected in ProjectionMode:
        label = _mode_label(selected, locale=locale, labels=labels)
        selected_attributes = (
            f' aria-current="{escape(current_attribute, quote=True)}"'
            if selected is state.mode
            else ""
        )
        links.append(
            f'<a class="reader-mode-link" data-reader-mode="{selected.value}" '
            f'href="{escape(state.mode_url(selected), quote=True)}" '
            f'aria-label="{escape(label, quote=True)}"{selected_attributes}>'
            f"{escape(label)}</a>"
        )
    return (
        f'<nav class="reader-mode-switch" aria-label="{escape(group_label, quote=True)}">'
        + "".join(links)
        + "</nav>"
    )


def render_mode_switch_form(
    context: _QueryContext | ReaderURLState | None = None,
    *,
    locale: str | None = None,
    action: str | None = None,
    control_id: str = "reader-mode",
    aria_label: str | None = None,
) -> str:
    """Render an accessible GET form preserving duplicate opaque query values."""

    state = context if isinstance(context, ReaderURLState) else ReaderURLState.from_url(
        context if isinstance(context, str) else "/"
    )
    if not isinstance(context, (str, ReaderURLState)):
        state = ReaderURLState(pairs=_pairs_from_context(context))
    group_label = aria_label or _mode_group_label(locale=locale)
    label = _mode_label(state.mode, locale=locale)
    options = "".join(
        f'<option value="{mode.value}"{" selected" if mode is state.mode else ""}>'
        f"{escape(_mode_label(mode, locale=locale))}</option>"
        for mode in ProjectionMode
    )
    hidden = "".join(
        f'<input type="hidden" name="{escape(key, quote=True)}" '
        f'value="{escape(value, quote=True)}">'
        for key, value in state.context
    )
    destination = action or state.path
    if not destination.startswith("/"):
        destination = "/"
    form_attributes = (
        f'<form class="reader-mode-switch-form" method="get" '
        f'action="{escape(destination, quote=True)}" '
        f'aria-label="{escape(group_label, quote=True)}">'
    )
    return form_attributes + (
        f"{hidden}"
        f'<label for="{escape(control_id, quote=True)}">{escape(label)}</label>'
        f'<select id="{escape(control_id, quote=True)}" name="{READER_MODE_QUERY_KEY}">'
        f"{options}</select>"
        f'<button type="submit">{escape(label)}</button>'
        "</form>"
    )


render_reader_mode_switch = render_mode_switch
mode_switch = render_mode_switch
mode_switch_form = render_mode_switch_form


def _sample_projection(value: object) -> bool:
    if not isinstance(value, ReaderProjection):
        return False
    sample = value.sample_data
    return sample is not None and all(
        reference.locator.startswith("fixture://") for reference in value.source_refs
    )


def is_fixture_projection(value: object) -> bool:
    """Return whether a projection carries explicit fixture-only provenance."""

    return _sample_projection(value)


def sample_banner_text(*, locale: str | None = None) -> str:
    """Return the fixed, non-provenance-bearing sample warning text."""

    return SAMPLE_BANNER_TEXT_EN if _locale_is_english(locale) else SAMPLE_BANNER_TEXT


def render_sample_banner(
    projection: object,
    *,
    locale: str | None = None,
    text: str | None = None,
) -> str:
    """Render a fixture warning, or nothing for an owner/unsourced envelope.

    The markup intentionally contains no fixture state, resource name, owner,
    source id, or locator.  A real owner projection therefore cannot be
    identified or relabeled by this helper.
    """

    if isinstance(projection, ReaderProjection):
        if not _sample_projection(projection):
            return ""
    elif not isinstance(projection, SampleData):
        return ""
    displayed = sample_banner_text(locale=locale) if text is None else text
    if not isinstance(displayed, str) or not displayed:
        return ""
    return (
        f'<aside class="reader-sample-banner" data-sample-banner="fixture" '
        f'role="note" aria-label="{escape(displayed, quote=True)}">{escape(displayed)}</aside>'
    )


fixture_sample_banner = render_sample_banner
sample_banner = render_sample_banner


def reader_contract_payload(
    projection: ReaderProjection,
    mode: ProjectionMode | str,
) -> dict[str, object]:
    """Return the shell-only Reader payload without changing the v0 response."""

    if not isinstance(projection, ReaderProjection):
        raise TypeError("projection must be a ReaderProjection")
    selected = ProjectionMode(mode)
    return {
        "schema": READER_SHELL_CONTRACT_SCHEMA,
        "mode": selected.value,
        "projection": projection.to_dict(),
    }


def render_reader_contract(
    projection: ReaderProjection,
    mode: ProjectionMode | str,
) -> str:
    """Expose Reader v1 fields to future page consumers through HTML only.

    The payload is deliberately not an API/read-model response.  ``<`` is escaped
    at JSON serialization time so owner text cannot terminate the JSON script tag;
    no client-side behavior or generated prose is introduced by this seam.
    """

    payload = reader_contract_payload(projection, mode)
    selected = ProjectionMode(mode)
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True)
    encoded = encoded.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    gaps = len(projection.limitations) + len(projection.unknowns)
    sample = "true" if projection.sample_data is not None else "false"
    return (
        f'<section class="reader-contract-seam" data-reader-contract="v1" '
        f'data-reader-mode="{escape(selected.value, quote=True)}" '
        f'data-reader-availability="{escape(projection.availability.status.value, quote=True)}" '
        f'data-reader-complete="{str(projection.availability.complete).lower()}" '
        f'data-reader-claims="{len(projection.claims)}" data-reader-gaps="{gaps}" '
        f'data-reader-source-refs="{len(projection.source_refs)}" '
        f'data-reader-sample="{sample}" hidden>'
        f'<script id="reader-contract" type="application/json">{encoded}</script>'
        "</section>"
    )


def compatibility_reference(
    projection: ReaderProjection,
    mode: ProjectionMode | str,
):
    """Return the projection's Expert/Raw reference to unchanged v0 bytes."""

    selected = ProjectionMode(mode)
    reference = projection.mode_reference(selected)
    if (
        selected in {ProjectionMode.EXPERT, ProjectionMode.RAW}
        and reference.schema != MANAGER_READ_MODEL_SCHEMA
    ):
        raise ValueError("Expert and Raw modes must reference ManagerReadModel v0")
    return reference


def expert_reference(projection: ReaderProjection):
    """Return the unchanged v0 reference used by Expert mode."""

    return compatibility_reference(projection, ProjectionMode.EXPERT)


def raw_reference(projection: ReaderProjection):
    """Return the unchanged v0 reference used by Raw mode."""

    return compatibility_reference(projection, ProjectionMode.RAW)


v0_compatibility_reference = compatibility_reference
reader_mode_reference = compatibility_reference


__all__ = [
    "READER_CONTEXT_KEYS",
    "READER_MODE_QUERY_KEY",
    "READER_MODE_VALUES",
    "READER_SHELL_CONTRACT_SCHEMA",
    "SAMPLE_BANNER_TEXT",
    "SAMPLE_BANNER_TEXT_EN",
    "ReaderURLState",
    "build_mode_url",
    "compatibility_reference",
    "expert_reference",
    "fixture_sample_banner",
    "is_fixture_projection",
    "mode_switch",
    "mode_switch_form",
    "mode_url",
    "parse_reader_url",
    "reader_mode_reference",
    "reader_mode_url",
    "render_mode_switch",
    "render_mode_switch_form",
    "render_reader_contract",
    "render_reader_mode_switch",
    "render_sample_banner",
    "reader_contract_payload",
    "raw_reference",
    "sample_banner",
    "sample_banner_text",
    "v0_compatibility_reference",
]
