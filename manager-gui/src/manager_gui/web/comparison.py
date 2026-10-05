"""Read-only Genome comparison view and deterministic comparison fixtures.

This module compares only explicit, JSON-compatible axes supplied by a public
read model.  It reports ``equal``, ``different``, or ``incomparable`` and
preserves changed paths, missing/incompatible axes, provenance, as-of values,
and snapshot tokens.  It never fills a missing axis with a default and never
calls a mutation or private-storage API.

The S2-T3 integration seam is :func:`render_genome_comparison_view`.
"""

# HTML fragments intentionally keep readable markup even when a line is long.
# ruff: noqa: E501

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from html import escape
from typing import TypeAlias, cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ..models import (
    Availability,
    Derivation,
    JSONValue,
    ManagerReadModel,
    ReadModelError,
    ReadModelStatus,
    SourceReference,
)
from ..provider import ManagerDataProvider
from .i18n import Translator
from .status import render_status_block

COMPARISON_RESOURCE = "genome_comparison"
COMPARISON_ROUTE = "strategy-genome-comparison"
COMPARISON_INTEGRATION_HOOK = "strategy-genome-comparison-view"
COMPARISON_INTEGRATION_HOOK_PATH = "manager_gui.web.comparison.render_genome_comparison_view"
NOT_RECORDED = "not recorded"

QueryContext: TypeAlias = str | Mapping[str, object] | None
JSONMapping: TypeAlias = Mapping[str, JSONValue]


class ComparisonResult(StrEnum):
    """Result of an explicit Genome comparison."""

    EQUAL = "equal"
    DIFFERENT = "different"
    INCOMPARABLE = "incomparable"


ComparisonStatus = ComparisonResult
ComparisonState = ComparisonResult
GenomeComparisonStatus = ComparisonResult


class ComparisonFixtureState(StrEnum):
    """Deterministic result and read-seam states for focused tests."""

    COMPLETE = "complete"
    EQUAL = "equal"
    DIFFERENT = "different"
    INCOMPARABLE = "incomparable"
    PARTIAL = "partial"
    MISSING = "missing"
    BLOCKED = "blocked"
    STALE = "stale"
    INTEGRITY_FAILURE = "integrity_failure"
    API_UNAVAILABLE = "api_unavailable"


COMPARISON_FIXTURE_STATES: tuple[str, ...] = tuple(state.value for state in ComparisonFixtureState)


def _mapping(value: object) -> Mapping[str, object] | None:
    return cast(Mapping[str, object], value) if isinstance(value, Mapping) else None


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(value)
    return ()


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


def _first_text(item: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        text = _text(item.get(key))
        if text is not None:
            return text
    return None


def _json_value(value: object) -> JSONValue | None:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        return None
    return cast(JSONValue, value)


def _json_mapping(value: object) -> JSONMapping:
    item = _mapping(value)
    if item is None:
        return {}
    return cast(JSONMapping, {str(key): _json_value(child) for key, child in item.items()})


def _normalise(value: object) -> str | None:
    text = _text(value)
    return None if text is None else text.strip().lower().replace("-", "_").replace(" ", "_")


def _source_refs(
    item: Mapping[str, object], source_index: Mapping[str, SourceReference]
) -> tuple[ComparisonSourceRef, ...]:
    values: list[object] = []
    for key in ("source_ref", "source_id", "source_refs", "source_ids", "sources"):
        if key in item:
            value = item[key]
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                values.extend(value)
            else:
                values.append(value)
    result: list[ComparisonSourceRef] = []
    seen: set[tuple[str, str | None]] = set()
    for value in values:
        source_id: str | None
        locator: str | None
        if isinstance(value, str):
            source_id = value.strip()
            locator = None
        else:
            nested = _mapping(value)
            if nested is None:
                continue
            source_id = _first_text(nested, "source_id", "sourceId", "id", "record_id")
            locator = _first_text(nested, "locator", "href", "url", "uri")
        if not source_id:
            continue
        source = source_index.get(source_id)
        locator = locator or (source.locator if source else None)
        marker = (source_id, locator)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(
            ComparisonSourceRef(
                source_id=source_id,
                locator=locator,
                owner=None if source is None else source.owner,
                schema=None if source is None else source.schema,
                revision=None if source is None else source.revision,
            )
        )
    return tuple(result)


@dataclass(frozen=True, slots=True)
class ComparisonSourceRef:
    """A source pointer retained on a comparison result."""

    source_id: str
    locator: str | None = None
    owner: str | None = None
    schema: str | None = None
    revision: str | None = None

    @property
    def available(self) -> bool:
        return self.locator is not None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "source_id": self.source_id,
            "locator": self.locator,
            "owner": self.owner,
            "schema": self.schema,
            "revision": self.revision,
        }


def _walk_differences(left: object, right: object, path: str = "") -> tuple[str, ...]:
    """Return deterministic JSON paths for explicit value differences."""

    if isinstance(left, Mapping) and isinstance(right, Mapping):
        paths: list[str] = []
        keys = sorted({str(key) for key in left} | {str(key) for key in right})
        for key in keys:
            child = f"{path}.{key}" if path else key
            if key not in left or key not in right:
                continue
            paths.extend(_walk_differences(left[key], right[key], child))
        return tuple(paths)
    if isinstance(left, Sequence) and not isinstance(left, (str, bytes, bytearray)) and isinstance(right, Sequence) and not isinstance(right, (str, bytes, bytearray)):
        paths = []
        for index in range(min(len(left), len(right))):
            child = f"{path}[{index}]" if path else f"[{index}]"
            paths.extend(_walk_differences(left[index], right[index], child))
        return tuple(paths) + tuple(
            f"{path}[{index}]" if path else f"[{index}]"
            for index in range(min(len(left), len(right)), max(len(left), len(right)))
        )
    if left != right:
        return (path or "$",)
    return ()


def _axis_values(item: Mapping[str, object], axes: Sequence[str] | None) -> Mapping[str, object]:
    explicit = _mapping(item.get("axes"))
    if explicit is not None:
        return explicit
    if axes is not None:
        return {axis: item[axis] for axis in axes if axis in item}
    # Only compare named, public Genome projection axes.  Unknown metadata is
    # not silently treated as a behavior change.
    selected = ("schema", "content_hash", "behavior", "data_requirements")
    return {axis: item[axis] for axis in selected if axis in item}


def _axis_incompatibility(left: object, right: object) -> bool:
    for value in (left, right):
        mapping = _mapping(value)
        if mapping is None:
            continue
        if mapping.get("compatible") is False or mapping.get("incompatible") is True:
            return True
    return False


@dataclass(frozen=True, slots=True)
class GenomeComparison:
    """An explicit comparison result with all unavailable axes preserved."""

    result: ComparisonResult
    left_genome_id: str | None = None
    right_genome_id: str | None = None
    changed_paths: tuple[str, ...] = ()
    missing_axes: tuple[str, ...] = ()
    incompatible_axes: tuple[str, ...] = ()
    left_provenance: JSONMapping = field(default_factory=dict)
    right_provenance: JSONMapping = field(default_factory=dict)
    left_as_of: str | None = None
    right_as_of: str | None = None
    left_snapshot: str | None = None
    right_snapshot: str | None = None
    source_refs: tuple[ComparisonSourceRef, ...] = ()
    reason: str | None = None
    raw: JSONMapping = field(default_factory=dict, repr=False, compare=False)

    @property
    def status(self) -> ComparisonResult:
        return self.result

    @property
    def is_comparable(self) -> bool:
        return self.result is not ComparisonResult.INCOMPARABLE

    def to_dict(self) -> dict[str, object]:
        return {
            "result": self.result.value,
            "left_genome_id": self.left_genome_id,
            "right_genome_id": self.right_genome_id,
            "changed_paths": list(self.changed_paths),
            "missing_axes": list(self.missing_axes),
            "incompatible_axes": list(self.incompatible_axes),
            "left_provenance": self.left_provenance,
            "right_provenance": self.right_provenance,
            "left_as_of": self.left_as_of,
            "right_as_of": self.right_as_of,
            "left_snapshot": self.left_snapshot,
            "right_snapshot": self.right_snapshot,
            "source_refs": [source.to_dict() for source in self.source_refs],
            "reason": self.reason,
        }


def compare_genomes(
    left: Mapping[str, object],
    right: Mapping[str, object],
    *,
    axes: Sequence[str] | None = None,
    source_refs: Sequence[ComparisonSourceRef] = (),
) -> GenomeComparison:
    """Compare only explicit axes and return missing/incompatible axes honestly."""

    left_axes = _axis_values(left, axes)
    right_axes = _axis_values(right, axes)
    axis_names = tuple(dict.fromkeys((*left_axes.keys(), *right_axes.keys())))
    missing = tuple(axis for axis in axis_names if axis not in left_axes or axis not in right_axes)
    incompatible = tuple(
        axis for axis in axis_names if axis in left_axes and axis in right_axes and _axis_incompatibility(left_axes[axis], right_axes[axis])
    )
    changed: list[str] = []
    for axis in axis_names:
        if axis in missing or axis in incompatible:
            continue
        changed.extend(f"{axis}.{path}" if path != "$" else axis for path in _walk_differences(left_axes[axis], right_axes[axis]))
    result = ComparisonResult.INCOMPARABLE if missing or incompatible else ComparisonResult.DIFFERENT if changed else ComparisonResult.EQUAL
    return GenomeComparison(
        result=result,
        left_genome_id=_first_text(left, "genome_id", "genomeId", "id", "record_id"),
        right_genome_id=_first_text(right, "genome_id", "genomeId", "id", "record_id"),
        changed_paths=tuple(dict.fromkeys(changed)),
        missing_axes=missing,
        incompatible_axes=incompatible,
        left_provenance=_json_mapping(left.get("provenance")),
        right_provenance=_json_mapping(right.get("provenance")),
        left_as_of=_first_text(left, "as_of", "asOf", "observed_at"),
        right_as_of=_first_text(right, "as_of", "asOf", "observed_at"),
        left_snapshot=_first_text(left, "snapshot_token", "snapshotToken", "snapshot"),
        right_snapshot=_first_text(right, "snapshot_token", "snapshotToken", "snapshot"),
        source_refs=tuple(source_refs),
        reason="The declared comparison axes are not complete or compatible." if result is ComparisonResult.INCOMPARABLE else None,
        raw=_json_mapping({"left": left, "right": right}),
    )


def _result(value: object) -> ComparisonResult | None:
    normalised = _normalise(value)
    if normalised is None:
        return None
    try:
        return ComparisonResult(normalised)
    except ValueError:
        if normalised in {"same", "identical"}:
            return ComparisonResult.EQUAL
        if normalised in {"changed", "not_equal"}:
            return ComparisonResult.DIFFERENT
        return None


def _text_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    return tuple(text for entry in _sequence(value) if (text := _text(entry)) is not None)


def _explicit_comparison(
    payload: Mapping[str, object], source_index: Mapping[str, SourceReference]
) -> GenomeComparison | None:
    comparison = _mapping(payload.get("comparison"))
    if comparison is None:
        for key in ("comparisons", "items", "records"):
            entries = _sequence(payload.get(key))
            if len(entries) == 1 and (candidate := _mapping(entries[0])) is not None:
                comparison = candidate
                break
    comparison = comparison or payload
    left = _mapping(comparison.get("left", comparison.get("left_genome")))
    right = _mapping(comparison.get("right", comparison.get("right_genome")))
    if left is None or right is None:
        return None
    refs = _source_refs(comparison, source_index)
    declared = _result(comparison.get("result", comparison.get("status", comparison.get("comparison_status"))))
    if declared is None:
        return compare_genomes(left, right, source_refs=refs)
    return GenomeComparison(
        result=declared,
        left_genome_id=_first_text(left, "genome_id", "genomeId", "id", "record_id"),
        right_genome_id=_first_text(right, "genome_id", "genomeId", "id", "record_id"),
        changed_paths=_text_tuple(comparison.get("changed_paths", comparison.get("changedPaths"))),
        missing_axes=_text_tuple(comparison.get("missing_axes", comparison.get("missingAxes"))),
        incompatible_axes=_text_tuple(comparison.get("incompatible_axes", comparison.get("incompatibleAxes"))),
        left_provenance=_json_mapping(left.get("provenance")),
        right_provenance=_json_mapping(right.get("provenance")),
        left_as_of=_first_text(left, "as_of", "asOf", "observed_at"),
        right_as_of=_first_text(right, "as_of", "asOf", "observed_at"),
        left_snapshot=_first_text(left, "snapshot_token", "snapshotToken", "snapshot"),
        right_snapshot=_first_text(right, "snapshot_token", "snapshotToken", "snapshot"),
        source_refs=refs,
        reason=_first_text(comparison, "reason", "message"),
        raw=_json_mapping(comparison),
    )


@dataclass(frozen=True, slots=True)
class ComparisonViewModel:
    """Comparison plus its read-model provenance envelope."""

    read_model: ManagerReadModel
    comparison: GenomeComparison | None

    @classmethod
    def from_read_model(cls, model: ManagerReadModel) -> ComparisonViewModel:
        payload = _mapping(model.data) or {}
        source_index = {source.source_id: source for source in model.source_refs}
        comparison = _explicit_comparison(payload, source_index)
        if comparison is not None and not comparison.source_refs:
            comparison = GenomeComparison(
                result=comparison.result,
                left_genome_id=comparison.left_genome_id,
                right_genome_id=comparison.right_genome_id,
                changed_paths=comparison.changed_paths,
                missing_axes=comparison.missing_axes,
                incompatible_axes=comparison.incompatible_axes,
                left_provenance=comparison.left_provenance,
                right_provenance=comparison.right_provenance,
                left_as_of=comparison.left_as_of,
                right_as_of=comparison.right_as_of,
                left_snapshot=comparison.left_snapshot,
                right_snapshot=comparison.right_snapshot,
                source_refs=tuple(
                    ComparisonSourceRef(source.source_id, source.locator, source.owner, source.schema, source.revision)
                    for source in model.source_refs
                ),
                reason=comparison.reason,
                raw=comparison.raw,
            )
        return cls(model, comparison)

    @property
    def result(self) -> ComparisonResult | None:
        return None if self.comparison is None else self.comparison.result

    @property
    def as_of(self) -> str | None:
        return self.read_model.as_of

    @property
    def snapshot_token(self) -> str | None:
        return self.read_model.snapshot_token

    def to_dict(self) -> dict[str, object]:
        return {
            "view": COMPARISON_ROUTE,
            "comparison": None if self.comparison is None else self.comparison.to_dict(),
            "as_of": self.as_of,
            "snapshot_token": self.snapshot_token,
            "availability": self.read_model.availability.to_dict(),
        }


GenomeComparisonViewModel = ComparisonViewModel


def _query_pairs(context: QueryContext) -> list[tuple[str, str]]:
    if context is None:
        return []
    if isinstance(context, str):
        query = urlsplit(context).query if "?" in context or "://" in context else context.lstrip("?")
        return [(key, value) for key, value in parse_qsl(query, keep_blank_values=True) if key]
    return [(key, str(value)) for key, value in context.items() if isinstance(key, str) and value is not None]


def genome_comparison_link(
    left_genome_id: str | None = None,
    right_genome_id: str | None = None,
    *,
    query_context: QueryContext = None,
    base_path: str = "/",
) -> str:
    """Build a stable comparison URL while preserving shell context."""

    pairs = [(key, value) for key, value in _query_pairs(query_context) if key not in {"view", "left_genome_id", "right_genome_id"}]
    pairs.append(("view", COMPARISON_ROUTE))
    if left_genome_id is not None:
        pairs.append(("left_genome_id", left_genome_id))
    if right_genome_id is not None:
        pairs.append(("right_genome_id", right_genome_id))
    order = {"view": 0, "left_genome_id": 1, "right_genome_id": 2}
    values: dict[str, list[str]] = {}
    for key, value in pairs:
        values.setdefault(key, [])
        if value not in values[key]:
            values[key].append(value)
    query = urlencode([(key, value) for key in sorted(values, key=lambda item: (order.get(item, 99), item)) for value in values[key]])
    parsed = urlsplit(base_path)
    existing = parsed.query
    full_query = f"{existing}&{query}" if existing and query else existing or query
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", full_query, parsed.fragment)) if full_query else base_path


comparison_link = genome_comparison_link


def _display(value: object) -> str:
    if value is None or value == "" or value == [] or value == {}:
        return NOT_RECORDED
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return NOT_RECORDED


def _render_refs(refs: Sequence[ComparisonSourceRef]) -> str:
    if not refs:
        return NOT_RECORDED
    values: list[str] = []
    for source in refs:
        label = escape(source.source_id)
        if source.locator:
            values.append(f'<a class="comparison-source-link" href="{escape(source.locator, quote=True)}">{label}</a>')
        else:
            values.append(f'<span class="comparison-source-unconfirmed">{label} — {NOT_RECORDED}</span>')
    return " · ".join(values)


def _render_related_links(comparison: GenomeComparison | None, context: QueryContext) -> str:
    """Expose stable paths back to each Genome and its condition evidence."""

    values = dict(_query_pairs(context))
    left_id = None if comparison is None else comparison.left_genome_id
    right_id = None if comparison is None else comparison.right_genome_id
    left_id = left_id or values.get("left_genome_id")
    right_id = right_id or values.get("right_genome_id")
    if left_id is None and right_id is None:
        return ""
    from .conditions import genome_conditions_link
    from .genome import genome_link

    links: list[str] = []
    if left_id is not None:
        links.append(
            f'<a class="comparison-left-genome-link" href="{escape(genome_link(left_id, query_context=context), quote=True)}">'
            f"Left Genome {escape(left_id)}</a>"
        )
        links.append(
            f'<a class="comparison-left-conditions-link" href="{escape(genome_conditions_link(left_id, query_context=context), quote=True)}">'
            "Left condition evidence</a>"
        )
    if right_id is not None:
        links.append(
            f'<a class="comparison-right-genome-link" href="{escape(genome_link(right_id, query_context=context), quote=True)}">'
            f"Right Genome {escape(right_id)}</a>"
        )
    return '<nav class="comparison-related-links" aria-label="Comparison related views">' + "".join(links) + "</nav>"


def _list_section(title: str, values: Sequence[str], *, marker: str) -> str:
    if not values:
        body = f'<p class="comparison-not-recorded" data-axis-list="{marker}">{NOT_RECORDED}</p>'
    else:
        body = "<ul>" + "".join(f"<li>{escape(value)}</li>" for value in values) + "</ul>"
    return f'<section class="comparison-list" data-axis-list="{marker}"><h3>{escape(title)}</h3>{body}</section>'


def render_genome_comparison(
    view_or_model: ComparisonViewModel | ManagerReadModel,
    *,
    query_context: QueryContext = None,
    translator: Translator | None = None,
) -> str:
    """Render a comparison result without replacing missing axes with defaults."""

    selected_translator = translator or Translator()
    view = view_or_model if isinstance(view_or_model, ComparisonViewModel) else ComparisonViewModel.from_read_model(view_or_model)
    model = view.read_model
    comparison = view.comparison
    result = comparison.result.value if comparison is not None else NOT_RECORDED
    comparison_href = genome_comparison_link(
        None if comparison is None else comparison.left_genome_id,
        None if comparison is None else comparison.right_genome_id,
        query_context=query_context,
    )
    fields: tuple[str, ...]
    if comparison is None:
        detail = "No explicit Genome comparison is recorded in this scope."
        fields = (
            f'<p class="comparison-not-recorded" data-comparison-result="{result}">{NOT_RECORDED}</p>',
            '<p class="comparison-explanation">' + detail + "</p>",
            _list_section("Changed paths", (), marker="changed_paths"),
            _list_section("Missing axes", (), marker="missing_axes"),
            _list_section("Incompatible axes", (), marker="incompatible_axes"),
        )
    else:
        fields = (
            f'<p class="comparison-result" data-comparison-result="{escape(result, quote=True)}">Result: {escape(result)}</p>',
            f'<p class="comparison-reason">{escape(comparison.reason or NOT_RECORDED)}</p>',
            '<dl class="comparison-provenance">'
            f'<div><dt>Left Genome</dt><dd>{escape(comparison.left_genome_id or NOT_RECORDED)}</dd></div>'
            f'<div><dt>Right Genome</dt><dd>{escape(comparison.right_genome_id or NOT_RECORDED)}</dd></div>'
            f'<div><dt>Left provenance</dt><dd>{escape(_display(comparison.left_provenance))}</dd></div>'
            f'<div><dt>Right provenance</dt><dd>{escape(_display(comparison.right_provenance))}</dd></div>'
            f'<div><dt>Left as-of</dt><dd>{escape(comparison.left_as_of or NOT_RECORDED)}</dd></div>'
            f'<div><dt>Right as-of</dt><dd>{escape(comparison.right_as_of or NOT_RECORDED)}</dd></div>'
            f'<div><dt>Left snapshot</dt><dd>{escape(comparison.left_snapshot or NOT_RECORDED)}</dd></div>'
            f'<div><dt>Right snapshot</dt><dd>{escape(comparison.right_snapshot or NOT_RECORDED)}</dd></div>'
            f'<div><dt>Source refs</dt><dd>{_render_refs(comparison.source_refs)}</dd></div>'
            '</dl>',
            _list_section("Changed paths", comparison.changed_paths, marker="changed_paths"),
            _list_section("Missing axes", comparison.missing_axes, marker="missing_axes"),
            _list_section("Incompatible axes", comparison.incompatible_axes, marker="incompatible_axes"),
        )
    # A derived comparison can legitimately be published with an ``incomparable``
    # result; surface the shared incomparable state beside the envelope provenance.
    incomparable_state = (
        render_status_block(
            ReadModelStatus.INCOMPARABLE,
            translator=selected_translator,
            reason=comparison.reason or "The declared comparison axes are not complete or compatible.",
        )
        if comparison is not None
        and comparison.result is ComparisonResult.INCOMPARABLE
        and model.availability.status is not ReadModelStatus.INCOMPARABLE
        else ""
    )
    return "".join(
        (
            f'<section class="genome-comparison-page" data-integration-hook="{COMPARISON_INTEGRATION_HOOK}">',
            '<p class="eyebrow">Strategies / Genome comparison · read-only</p>',
            '<h1 class="page-title" data-page-title tabindex="-1">Genome comparison</h1>',
            '<p class="page-intro">Only explicit comparison axes are shown. Equal, different, and incomparable remain distinct outcomes.</p>',
            f'<p class="context-line comparison-context"><span><strong>Observed</strong> {escape(model.as_of or NOT_RECORDED)}</span><span><strong>Snapshot</strong> {escape(model.snapshot_token or NOT_RECORDED)}</span></p>',
            f'<a class="comparison-context-link" href="{escape(comparison_href, quote=True)}">Stable comparison context</a>',
            _render_related_links(comparison, query_context),
            render_status_block(model, translator=selected_translator),
            incomparable_state,
            *fields,
            '</section>',
        )
    )


def comparison_view(provider: ManagerDataProvider, *, snapshot_token: str | None = None) -> ComparisonViewModel:
    """Read ``genome_comparison`` once through the public provider seam."""

    return ComparisonViewModel.from_read_model(provider.read(COMPARISON_RESOURCE, snapshot_token=snapshot_token))


def render_genome_comparison_view(
    provider_or_model: ManagerDataProvider | ManagerReadModel,
    *,
    query_context: QueryContext = None,
    snapshot_token: str | None = None,
    translator: Translator | None = None,
) -> str:
    """S2-T3 hook accepting either an approved provider or a read envelope."""

    view = (
        ComparisonViewModel.from_read_model(provider_or_model)
        if isinstance(provider_or_model, ManagerReadModel)
        else comparison_view(provider_or_model, snapshot_token=snapshot_token)
    )
    return render_genome_comparison(
        view, query_context=query_context, translator=translator
    )


render_comparison_view = render_genome_comparison_view
render_genome_compare_view = render_genome_comparison_view


def _comparison_source(source_id: str, locator: str, revision: str = "fixture-v0") -> SourceReference:
    return SourceReference(
        source_id=source_id,
        owner="strategy-workspace",
        kind="public-record",
        locator=locator,
        schema="manager-genome-comparison.fixture.v0",
        revision=revision,
    )


def _genome(genome_id: str, metric: int, source_id: str, snapshot: str) -> dict[str, object]:
    return {
        "genome_id": genome_id,
        "schema": "strategy-genome.v1",
        "content_hash": f"sha256:{genome_id}",
        "behavior": {"entry": {"rule": "signal_positive"}, "metric": metric},
        "data_requirements": {"version": "market-data-v3"},
        "provenance": {"candidate": f"candidate-{genome_id}", "source_ref": source_id},
        "as_of": "2026-10-03T10:00:00Z",
        "snapshot_token": snapshot,
    }


def build_genome_comparison_fixture(state: ComparisonFixtureState | str) -> ManagerReadModel:
    """Build equal/different/incomparable and read-seam failure fixtures."""

    selected = ComparisonFixtureState(state)
    left_source = _comparison_source("fixture-comparison-left", "fixture://manager-gui/genome-left")
    right_source = _comparison_source("fixture-comparison-right", "fixture://manager-gui/genome-right", "fixture-v1")
    sources = (left_source, right_source)
    if selected in {ComparisonFixtureState.BLOCKED, ComparisonFixtureState.STALE, ComparisonFixtureState.INTEGRITY_FAILURE, ComparisonFixtureState.API_UNAVAILABLE}:
        statuses = {
            ComparisonFixtureState.BLOCKED: (ReadModelStatus.BLOCKED, "The approved Genome comparison read seam is blocked.", "comparison_read_blocked"),
            ComparisonFixtureState.STALE: (ReadModelStatus.STALE, "The comparison source is stale.", "comparison_source_stale"),
            ComparisonFixtureState.INTEGRITY_FAILURE: (ReadModelStatus.INTEGRITY_FAILURE, "The comparison artifact failed integrity validation.", "comparison_integrity_failure"),
            ComparisonFixtureState.API_UNAVAILABLE: (ReadModelStatus.API_UNAVAILABLE, "The approved Genome comparison API is unavailable.", "comparison_api_unavailable"),
        }
        status, reason, code = statuses[selected]
        return ManagerReadModel(
            data=cast(JSONValue, {}),
            source_refs=sources,
            as_of=None if selected in {ComparisonFixtureState.BLOCKED, ComparisonFixtureState.API_UNAVAILABLE} else "2025-01-01T00:00:00Z",
            snapshot_token=f"comparison-fixture-{selected.value}-v0",
            derivation=Derivation(kind="direct", inputs=tuple(source.source_id for source in sources), version="v0"),
            availability=Availability(status, False, reason),
            errors=(ReadModelError(code, reason),),
        )
    if selected is ComparisonFixtureState.MISSING:
        return ManagerReadModel(
            data=cast(JSONValue, {}),
            source_refs=sources,
            as_of="2026-10-03T10:00:00Z",
            snapshot_token="comparison-fixture-missing-v0",
            derivation=Derivation(kind="direct", inputs=(), version="v0"),
            availability=Availability(ReadModelStatus.MISSING, False, "No explicit Genome comparison is recorded in this scope."),
        )
    partial = selected is ComparisonFixtureState.PARTIAL
    left = _genome("genome-left", 1, left_source.source_id, "snapshot-left-v1")
    right = _genome(
        "genome-right",
        1 if selected in {ComparisonFixtureState.EQUAL, ComparisonFixtureState.COMPLETE} else 2,
        right_source.source_id,
        "snapshot-right-v1",
    )
    if selected is ComparisonFixtureState.INCOMPARABLE:
        right["data_requirements"] = {"version": "market-data-v4", "compatible": False}
        declared = {
            "result": "incomparable",
            "missing_axes": [],
            "incompatible_axes": ["data_requirements.version"],
            "reason": "The data versions are incompatible.",
        }
    else:
        declared = {
            "result": "equal"
            if selected in {ComparisonFixtureState.EQUAL, ComparisonFixtureState.COMPLETE}
            else "different"
        }
    payload = {"comparison": {"left": left, "right": right, **declared, "source_refs": [source.source_id for source in sources]}}
    return ManagerReadModel(
        data=cast(JSONValue, payload),
        source_refs=sources,
        as_of="2026-10-03T10:00:00Z",
        snapshot_token=f"comparison-fixture-{selected.value}-v0",
        derivation=Derivation(kind="derived", rule="manager-gui.genome-comparison.v0", inputs=tuple(source.source_id for source in sources), version="v0"),
        availability=Availability(
            ReadModelStatus.KNOWN if partial else ReadModelStatus.DERIVED,
            not partial,
            "Genome comparison is only partially recorded in this scope."
            if partial
            else "Genome comparison fixture.",
        ),
        errors=(
            ReadModelError(
                "comparison_scope_partial",
                "Some comparison axes are outside the indexed scope.",
            ),
        )
        if partial
        else (),
    )


@dataclass(frozen=True, slots=True)
class ComparisonFixtureProvider:
    """Read-only provider for comparison fixtures."""

    state: ComparisonFixtureState

    def __init__(self, state: ComparisonFixtureState | str) -> None:
        object.__setattr__(self, "state", ComparisonFixtureState(state))

    def read(self, resource: str = COMPARISON_RESOURCE, *, snapshot_token: str | None = None) -> ManagerReadModel:
        del snapshot_token
        if resource not in {COMPARISON_RESOURCE, "comparison", COMPARISON_ROUTE}:
            raise ValueError(f"unsupported comparison resource: {resource!r}")
        return build_genome_comparison_fixture(self.state)


def comparison_fixture_provider(state: ComparisonFixtureState | str) -> ComparisonFixtureProvider:
    return ComparisonFixtureProvider(state)


build_comparison_fixture = build_genome_comparison_fixture
GenomeComparisonResult = ComparisonResult

__all__ = [
    "COMPARISON_FIXTURE_STATES",
    "COMPARISON_INTEGRATION_HOOK",
    "COMPARISON_INTEGRATION_HOOK_PATH",
    "COMPARISON_RESOURCE",
    "COMPARISON_ROUTE",
    "ComparisonFixtureProvider",
    "ComparisonFixtureState",
    "ComparisonResult",
    "ComparisonSourceRef",
    "ComparisonState",
    "ComparisonStatus",
    "ComparisonViewModel",
    "GenomeComparison",
    "GenomeComparisonResult",
    "GenomeComparisonStatus",
    "GenomeComparisonViewModel",
    "build_comparison_fixture",
    "build_genome_comparison_fixture",
    "compare_genomes",
    "comparison_fixture_provider",
    "comparison_link",
    "comparison_view",
    "genome_comparison_link",
    "render_comparison_view",
    "render_genome_compare_view",
    "render_genome_comparison",
    "render_genome_comparison_view",
]
