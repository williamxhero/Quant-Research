"""General read-only comparison of published research objects and evidence.

This module is deliberately separate from :mod:`manager_gui.web.comparison`.
That module owns the S2 Strategy Genome comparison contract; this module owns
S4's broader object/evidence comparison contract for Genome, Package, Study,
Run, Method, and Evidence records.  It compares only explicitly published
axes, keeps missing and incompatible axes visible, and never recalculates a
metric or writes to an owner system.
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
from .locators import public_locator
from .status import render_status_block

EVIDENCE_COMPARISON_RESOURCE = "evidence_comparison"
EVIDENCE_COMPARISON_ROUTE = "evidence-object-comparison"
EVIDENCE_COMPARISON_INTEGRATION_HOOK = "evidence-comparison-view"
EVIDENCE_COMPARISON_INTEGRATION_HOOK_PATH = (
    "manager_gui.web.evidence_comparison.render_evidence_comparison_view"
)
NOT_RECORDED = "not recorded"

QueryContext: TypeAlias = str | Mapping[str, object] | None
JSONMapping: TypeAlias = Mapping[str, JSONValue]
_MISSING = object()


class ComparisonAxis(StrEnum):
    """The complete S4-T3 object comparison axis set."""

    IDENTITY = "identity"
    DATA_VERSION = "data_version"
    UNIVERSE = "universe"
    TIME_RANGE = "time_range"
    PROTOCOL = "protocol"
    RANDOMNESS = "randomness"
    COSTS = "costs"
    FILLS = "fills"
    METRIC_DEFINITION = "metric_definition"
    EVIDENCE_SECTIONS = "evidence_sections"
    CURRENCY = "currency"


OBJECT_COMPARISON_AXES: tuple[ComparisonAxis, ...] = tuple(ComparisonAxis)


class AxisComparisonState(StrEnum):
    """State of one declared axis; no state is inferred as a success/failure."""

    EQUAL = "equal"
    DIFFERENT = "different"
    MISSING = "missing"
    INCOMPARABLE = "incomparable"


class ComparisonOutcome(StrEnum):
    """Overall outcome with missing distinct from an incompatible comparison."""

    EQUAL = "equal"
    DIFFERENT = "different"
    MISSING = "missing"
    INCOMPARABLE = "incomparable"


# Friendly aliases make the contract discoverable without introducing a second
# comparison implementation or colliding with the S2 module's names.
ComparisonAxisState = AxisComparisonState
ComparisonResult = ComparisonOutcome
ComparisonStatus = ComparisonOutcome
ObjectComparisonResult = ComparisonOutcome


class EvidenceComparisonFixtureState(StrEnum):
    """Deterministic fixture states used by focused tests and local previews."""

    COMPLETE = "complete"
    EQUAL = "equal"
    DIFFERENT = "different"
    MISSING = "missing"
    INCOMPARABLE = "incomparable"
    INCOMPATIBLE = "incompatible"
    PROTOCOL_INCOMPATIBLE = "protocol_incompatible"
    DATA_VERSION_INCONSISTENT = "data_version_inconsistent"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    STALE = "stale"
    INTEGRITY_FAILURE = "integrity_failure"
    API_UNAVAILABLE = "api_unavailable"


ComparisonFixtureState = EvidenceComparisonFixtureState
EVIDENCE_COMPARISON_FIXTURE_STATES: tuple[str, ...] = tuple(
    state.value for state in EvidenceComparisonFixtureState
)


def _mapping(value: object) -> Mapping[str, object] | None:
    return cast(Mapping[str, object], value) if isinstance(value, Mapping) else None


def _sequence(value: object) -> tuple[object, ...]:
    if value is None or isinstance(value, (str, bytes, bytearray)):
        return ()
    if isinstance(value, Mapping):
        return (value,)
    if isinstance(value, Sequence):
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
        if (value := _text(item.get(key))) is not None:
            return value
    return None


def _normalise(value: object) -> str | None:
    text = _text(value)
    if text is None:
        return None
    return text.strip().lower().replace("-", "_").replace(" ", "_")


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
    return cast(JSONMapping, {str(key): _json_value(raw) for key, raw in item.items()})


def _display(value: object) -> str:
    if value is None or value is _MISSING:
        return NOT_RECORDED
    try:
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return NOT_RECORDED
    return rendered if rendered not in {"null", "\"\""} else NOT_RECORDED


def _canonical(value: object) -> str:
    """Use JSON equality only; this is not a metric or result recalculation."""

    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError):
        return repr(value)


def _is_present(value: object) -> bool:
    return value is not _MISSING and value is not None


def _source_refs(
    item: Mapping[str, object], source_index: Mapping[str, SourceReference]
) -> tuple[ComparisonSourceRef, ...]:
    values: list[object] = []
    for key in ("source_ref", "source_id", "source_refs", "source_ids", "sources"):
        if key not in item:
            continue
        value = item[key]
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            values.extend(value)
        else:
            values.append(value)
    result: list[ComparisonSourceRef] = []
    seen: set[tuple[str, str | None]] = set()
    for value in values:
        nested = _mapping(value)
        source_id = (
            _first_text(nested, "source_id", "sourceId", "id", "record_id", "ref")
            if nested is not None
            else _text(value)
        )
        if source_id is None:
            continue
        source = source_index.get(source_id)
        locator = (
            _first_text(nested, "locator", "href", "url", "uri")
            if nested is not None
            else None
        ) or (source.locator if source is not None else None)
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
    """A public source pointer retained on a comparison or axis."""

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


@dataclass(frozen=True, slots=True)
class AxisComparison:
    """One axis comparison with both values and its explicit limitation."""

    axis: ComparisonAxis
    state: AxisComparisonState
    left_value: JSONValue | None = None
    right_value: JSONValue | None = None
    reason: str | None = None
    source_refs: tuple[ComparisonSourceRef, ...] = ()
    raw: Mapping[str, object] = field(default_factory=dict, repr=False, compare=False)

    @property
    def left(self) -> JSONValue | None:
        return self.left_value

    @property
    def right(self) -> JSONValue | None:
        return self.right_value

    @property
    def comparable(self) -> bool:
        return self.state in {AxisComparisonState.EQUAL, AxisComparisonState.DIFFERENT}

    def to_dict(self) -> dict[str, object]:
        return {
            "axis": self.axis.value,
            "state": self.state.value,
            "left": self.left_value,
            "right": self.right_value,
            "reason": self.reason,
            "source_refs": [ref.to_dict() for ref in self.source_refs],
        }


@dataclass(frozen=True, slots=True)
class ObjectComparison:
    """A general object comparison, explicitly not an S2 Genome comparison."""

    axes: tuple[AxisComparison, ...]
    left_object_type: str | None = None
    right_object_type: str | None = None
    left_object_id: str | None = None
    right_object_id: str | None = None
    source_refs: tuple[ComparisonSourceRef, ...] = ()
    reason: str | None = None
    raw: Mapping[str, object] = field(default_factory=dict, repr=False, compare=False)
    denominator: int | None = None

    @property
    def result(self) -> ComparisonOutcome:
        states = {axis.state for axis in self.axes}
        if AxisComparisonState.INCOMPARABLE in states:
            return ComparisonOutcome.INCOMPARABLE
        if AxisComparisonState.MISSING in states:
            return ComparisonOutcome.MISSING
        if AxisComparisonState.DIFFERENT in states:
            return ComparisonOutcome.DIFFERENT
        return ComparisonOutcome.EQUAL

    @property
    def status(self) -> ComparisonOutcome:
        return self.result

    @property
    def equal_axes(self) -> tuple[str, ...]:
        return tuple(axis.axis.value for axis in self.axes if axis.state is AxisComparisonState.EQUAL)

    @property
    def changed_axes(self) -> tuple[str, ...]:
        return tuple(
            axis.axis.value for axis in self.axes if axis.state is AxisComparisonState.DIFFERENT
        )

    @property
    def missing_axes(self) -> tuple[str, ...]:
        return tuple(axis.axis.value for axis in self.axes if axis.state is AxisComparisonState.MISSING)

    @property
    def incompatible_axes(self) -> tuple[str, ...]:
        return tuple(
            axis.axis.value
            for axis in self.axes
            if axis.state is AxisComparisonState.INCOMPARABLE
        )

    @property
    def success_rate(self) -> None:
        """No aggregate metric is generated by a comparison projection."""

        return None

    @property
    def ranking(self) -> None:
        """No ranking is generated by a comparison projection."""

        return None

    def axis(self, name: ComparisonAxis | str) -> AxisComparison:
        selected = ComparisonAxis(name)
        return next(item for item in self.axes if item.axis is selected)

    def to_dict(self) -> dict[str, object]:
        return {
            "comparison_kind": "general_object_comparison",
            "result": self.result.value,
            "left_object_type": self.left_object_type,
            "right_object_type": self.right_object_type,
            "left_object_id": self.left_object_id,
            "right_object_id": self.right_object_id,
            "axes": [axis.to_dict() for axis in self.axes],
            "equal_axes": list(self.equal_axes),
            "changed_axes": list(self.changed_axes),
            "missing_axes": list(self.missing_axes),
            "incompatible_axes": list(self.incompatible_axes),
            "source_refs": [ref.to_dict() for ref in self.source_refs],
            "reason": self.reason,
            "denominator": self.denominator,
        }


# More explicit names are useful to consumers that do not want the generic
# ObjectComparison spelling.
EvidenceObjectComparison = ObjectComparison
EvidenceComparison = ObjectComparison
ObjectComparisonAxis = AxisComparison


_AXIS_ALIASES: dict[ComparisonAxis, tuple[str, ...]] = {
    ComparisonAxis.IDENTITY: ("identity", "object_identity", "object"),
    ComparisonAxis.DATA_VERSION: (
        "data_version",
        "dataVersion",
        "data_snapshot",
        "dataSnapshot",
        "data_requirements",
    ),
    ComparisonAxis.UNIVERSE: ("universe", "universe_definition", "instrument_universe"),
    ComparisonAxis.TIME_RANGE: ("time_range", "timeRange", "date_range", "period"),
    ComparisonAxis.PROTOCOL: ("protocol", "protocol_definition", "protocol_id"),
    ComparisonAxis.RANDOMNESS: ("randomness", "random_seed", "seed"),
    ComparisonAxis.COSTS: ("costs", "cost", "cost_model", "fees", "fee_model"),
    ComparisonAxis.FILLS: ("fills", "fill_policy", "execution_fills", "fill_model"),
    ComparisonAxis.METRIC_DEFINITION: (
        "metric_definition",
        "metricDefinition",
        "metrics",
        "metric_policy",
    ),
    ComparisonAxis.EVIDENCE_SECTIONS: (
        "evidence_sections",
        "evidenceSections",
        "sections",
    ),
    ComparisonAxis.CURRENCY: ("currency", "currency_policy", "base_currency"),
}


def _axis_container(item: Mapping[str, object]) -> Mapping[str, object]:
    for key in ("axes", "comparison_axes", "comparisonAxes"):
        nested = _mapping(item.get(key))
        if nested is not None:
            return nested
    return item


def _axis_value(item: Mapping[str, object], axis: ComparisonAxis) -> object:
    container = _axis_container(item)
    for key in _AXIS_ALIASES[axis]:
        if key in container:
            return container[key]
        if key in item:
            return item[key]
    if axis is ComparisonAxis.IDENTITY:
        values: dict[str, object] = {}
        for key in ("object_type", "objectType", "record_type", "type"):
            if key in item:
                values["object_type"] = item[key]
                break
        for key in ("object_id", "objectId", "record_id", "recordId", "id"):
            if key in item:
                values["object_id"] = item[key]
                break
        for key in ("revision", "version", "content_hash", "contentHash"):
            if key in item:
                values[key] = item[key]
        if values:
            return values
    if axis is ComparisonAxis.DATA_VERSION:
        requirements = _mapping(item.get("data_requirements"))
        if requirements is not None:
            return requirements
    if axis is ComparisonAxis.EVIDENCE_SECTIONS:
        evidence = _mapping(item.get("evidence"))
        if evidence is not None and "sections" in evidence:
            return evidence["sections"]
    return _MISSING


def _incompatibility(value: object) -> str | None:
    item = _mapping(value)
    if item is None:
        return None
    compatible = item.get("compatible")
    if compatible is False:
        return "The published axis declares the two values incompatible."
    if item.get("incompatible") is True:
        return "The published axis declares an incompatibility."
    status = _normalise(item.get("status", item.get("state")))
    if status in {"incomparable", "incompatible", "not_comparable", "blocked"}:
        return f"The published axis status is {status}."
    nested = item.get("compatibility")
    nested_item = _mapping(nested)
    if nested_item is not None and nested_item.get("compatible") is False:
        return "The published compatibility declaration is false."
    return None


def _normalise_axis(value: object) -> ComparisonAxis | None:
    token = _normalise(value)
    if token is None:
        return None
    for axis in OBJECT_COMPARISON_AXES:
        aliases = {_normalise(axis.value), *(_normalise(alias) for alias in _AXIS_ALIASES[axis])}
        if token in aliases:
            return axis
    return None


def _normalise_state(value: object) -> AxisComparisonState | None:
    token = _normalise(value)
    if token in {"same", "identical", "match", "matched"}:
        return AxisComparisonState.EQUAL
    if token in {"changed", "not_equal", "different"}:
        return AxisComparisonState.DIFFERENT
    if token in {"absent", "not_recorded", "unknown", "missing"}:
        return AxisComparisonState.MISSING
    if token in {"incompatible", "not_comparable", "incomparable", "blocked"}:
        return AxisComparisonState.INCOMPARABLE
    if token is None:
        return None
    try:
        return AxisComparisonState(token)
    except ValueError:
        return None


def _explicit_axis_results(payload: Mapping[str, object]) -> dict[ComparisonAxis, Mapping[str, object]]:
    raw = None
    for key in ("axis_results", "axis_comparisons", "axisComparisons", "results"):
        if key in payload:
            raw = payload[key]
            break
    if raw is None:
        candidate = payload.get("axes")
        if isinstance(candidate, Mapping) and any(
            _normalise_state(value) is not None or isinstance(value, Mapping)
            for value in candidate.values()
        ):
            raw = candidate
    result: dict[ComparisonAxis, Mapping[str, object]] = {}
    entries: list[tuple[object, object]]
    if isinstance(raw, Mapping):
        entries = [(key, value) for key, value in raw.items()]
    else:
        entries = [
            (_first_text(_mapping(entry) or {}, "axis", "name", "key"), entry)
            for entry in _sequence(raw)
        ]
    for name, value in entries:
        axis = _normalise_axis(name)
        if axis is None:
            continue
        if isinstance(value, Mapping):
            result[axis] = value
        else:
            result[axis] = {"state": value}
    return result


def _axis_sets(payload: Mapping[str, object]) -> tuple[set[ComparisonAxis], set[ComparisonAxis]]:
    missing: set[ComparisonAxis] = set()
    incompatible: set[ComparisonAxis] = set()
    for key, target in (("missing_axes", missing), ("incompatible_axes", incompatible)):
        raw_values = (
            (payload[key],)
            if isinstance(payload.get(key), str)
            else _sequence(payload.get(key))
        )
        for raw in raw_values:
            axis = _normalise_axis(raw)
            if axis is not None:
                target.add(axis)
    return missing, incompatible


def _object_pair(payload: Mapping[str, object]) -> tuple[Mapping[str, object], Mapping[str, object]] | None:
    comparison = _mapping(payload.get("comparison")) or _mapping(payload.get("object_comparison"))
    candidate = comparison or payload
    left = _mapping(candidate.get("left", candidate.get("left_object")))
    right = _mapping(candidate.get("right", candidate.get("right_object")))
    if left is not None and right is not None:
        return left, right
    objects = [item for item in _sequence(candidate.get("objects")) if _mapping(item) is not None]
    if len(objects) >= 2:
        return cast(Mapping[str, object], objects[0]), cast(Mapping[str, object], objects[1])
    return None


def _comparison_payload(data: object) -> Mapping[str, object]:
    root = _mapping(data) or {}
    for key in ("evidence_comparison", "object_comparison", "comparison"):
        nested = _mapping(root.get(key))
        if nested is not None:
            return nested
    return root


def _ref_union(*groups: Sequence[ComparisonSourceRef]) -> tuple[ComparisonSourceRef, ...]:
    result: list[ComparisonSourceRef] = []
    seen: set[tuple[str, str | None]] = set()
    for group in groups:
        for ref in group:
            marker = (ref.source_id, ref.locator)
            if marker not in seen:
                seen.add(marker)
                result.append(ref)
    return tuple(result)


def compare_objects(
    left: Mapping[str, object],
    right: Mapping[str, object],
    *,
    axis_results: Mapping[ComparisonAxis | str, object] | None = None,
    missing_axes: Sequence[ComparisonAxis | str] = (),
    incompatible_axes: Sequence[ComparisonAxis | str] = (),
    source_refs: Sequence[ComparisonSourceRef] = (),
) -> ObjectComparison:
    """Compare explicit public values for all S4 axes.

    The function only compares JSON values.  It does not execute a run,
    calculate a metric, dereference an artifact, or infer a denominator.
    """

    declared: dict[ComparisonAxis, Mapping[str, object]] = {}
    for name, value in (axis_results or {}).items():
        axis = _normalise_axis(name)
        if axis is None:
            continue
        declared[axis] = value if isinstance(value, Mapping) else {"state": value}
    missing = {_normalise_axis(value) for value in missing_axes}
    incompatible = {_normalise_axis(value) for value in incompatible_axes}
    missing.discard(None)
    incompatible.discard(None)
    axes: list[AxisComparison] = []
    for axis in OBJECT_COMPARISON_AXES:
        left_value = _axis_value(left, axis)
        right_value = _axis_value(right, axis)
        declaration = declared.get(axis, {})
        declared_left = declaration.get("left", declaration.get("left_value", _MISSING))
        declared_right = declaration.get("right", declaration.get("right_value", _MISSING))
        if declared_left is not _MISSING:
            left_value = declared_left
        if declared_right is not _MISSING:
            right_value = declared_right
        declared_state = _normalise_state(
            declaration.get("state", declaration.get("status", declaration.get("result")))
        )
        state: AxisComparisonState
        reason = _first_text(declaration, "reason", "message", "detail")
        if axis in incompatible or declared_state is AxisComparisonState.INCOMPARABLE:
            state = AxisComparisonState.INCOMPARABLE
            reason = reason or "The published comparison marks this axis incompatible."
        elif axis in missing or declared_state is AxisComparisonState.MISSING:
            state = AxisComparisonState.MISSING
            reason = reason or "The axis is not published for both objects."
        elif declared_state is not None:
            state = declared_state
            reason = reason or {
                AxisComparisonState.EQUAL: "The published axis values are equal.",
                AxisComparisonState.DIFFERENT: "The published axis values differ.",
                AxisComparisonState.MISSING: "The axis is not published for both objects.",
                AxisComparisonState.INCOMPARABLE: "The published axis values are incompatible.",
            }[state]
        elif not _is_present(left_value) or not _is_present(right_value):
            state = AxisComparisonState.MISSING
            reason = reason or "The axis is not published for both objects."
        elif (incompatibility := _incompatibility(left_value)) is not None or (
            incompatibility := _incompatibility(right_value)
        ) is not None:
            state = AxisComparisonState.INCOMPARABLE
            reason = reason or incompatibility
        elif _canonical(left_value) == _canonical(right_value):
            state = AxisComparisonState.EQUAL
            reason = reason or "The published axis values are equal."
        else:
            state = AxisComparisonState.DIFFERENT
            reason = reason or "The published axis values differ."
        axes.append(
            AxisComparison(
                axis=axis,
                state=state,
                left_value=_json_value(None if left_value is _MISSING else left_value),
                right_value=_json_value(None if right_value is _MISSING else right_value),
                reason=reason,
                source_refs=tuple(source_refs),
                raw=declaration,
            )
        )
    return ObjectComparison(
        axes=tuple(axes),
        left_object_type=_first_text(left, "object_type", "objectType", "record_type", "type"),
        right_object_type=_first_text(right, "object_type", "objectType", "record_type", "type"),
        left_object_id=_first_text(left, "object_id", "objectId", "record_id", "recordId", "id"),
        right_object_id=_first_text(right, "object_id", "objectId", "record_id", "recordId", "id"),
        source_refs=tuple(source_refs),
        reason=(
            "The declared object axes are not complete or compatible."
            if any(axis.state in {AxisComparisonState.MISSING, AxisComparisonState.INCOMPARABLE} for axis in axes)
            else None
        ),
        raw={"left": dict(left), "right": dict(right)},
    )


def _explicit_comparison(
    payload: Mapping[str, object], source_index: Mapping[str, SourceReference]
) -> ObjectComparison | None:
    pair = _object_pair(payload)
    if pair is None:
        return None
    left, right = pair
    nested = _mapping(payload.get("comparison")) or _mapping(payload.get("object_comparison")) or payload
    refs = _ref_union(
        _source_refs(nested, source_index),
        _source_refs(left, source_index),
        _source_refs(right, source_index),
        tuple(
            ComparisonSourceRef(source.source_id, source.locator, source.owner, source.schema, source.revision)
            for source in source_index.values()
        ),
    )
    declared = _explicit_axis_results(nested)
    missing, incompatible = _axis_sets(nested)
    comparison = compare_objects(
        left,
        right,
        axis_results=cast(Mapping[ComparisonAxis | str, object], declared),
        missing_axes=tuple(missing),
        incompatible_axes=tuple(incompatible),
        source_refs=refs,
    )
    denominator = nested.get("denominator")
    if isinstance(denominator, bool) or not isinstance(denominator, int) or denominator < 0:
        denominator = None
    return ObjectComparison(
        axes=comparison.axes,
        left_object_type=comparison.left_object_type,
        right_object_type=comparison.right_object_type,
        left_object_id=comparison.left_object_id,
        right_object_id=comparison.right_object_id,
        source_refs=refs,
        reason=_first_text(nested, "reason", "message") or comparison.reason,
        raw=_json_mapping(nested),
        denominator=denominator,
    )


@dataclass(frozen=True, slots=True)
class EvidenceComparisonViewModel:
    """The immutable comparison projection and its read-model envelope."""

    read_model: ManagerReadModel
    comparison: ObjectComparison | None

    @classmethod
    def from_read_model(cls, model: ManagerReadModel) -> EvidenceComparisonViewModel:
        comparison = None
        if model.availability.status not in {
            ReadModelStatus.BLOCKED,
            ReadModelStatus.STALE,
            ReadModelStatus.INTEGRITY_FAILURE,
            ReadModelStatus.API_UNAVAILABLE,
            ReadModelStatus.MISSING,
        }:
            payload = _comparison_payload(model.data)
            comparison = _explicit_comparison(payload, {ref.source_id: ref for ref in model.source_refs})
        return cls(read_model=model, comparison=comparison)

    @property
    def result(self) -> ComparisonOutcome | None:
        return None if self.comparison is None else self.comparison.result

    @property
    def axes(self) -> tuple[AxisComparison, ...]:
        return () if self.comparison is None else self.comparison.axes

    @property
    def source_refs(self) -> tuple[SourceReference, ...]:
        return self.read_model.source_refs

    @property
    def as_of(self) -> str | None:
        return self.read_model.as_of

    @property
    def snapshot_token(self) -> str | None:
        return self.read_model.snapshot_token

    @property
    def raw_json(self) -> str:
        return self.read_model.to_json()

    def to_dict(self) -> dict[str, object]:
        return {
            "view": EVIDENCE_COMPARISON_ROUTE,
            "comparison": None if self.comparison is None else self.comparison.to_dict(),
            "availability": self.read_model.availability.to_dict(),
            "source_refs": [source.to_dict() for source in self.read_model.source_refs],
            "as_of": self.as_of,
            "snapshot_token": self.snapshot_token,
            "errors": [error.to_dict() for error in self.read_model.errors],
        }


ObjectComparisonViewModel = EvidenceComparisonViewModel
EvidenceObjectComparisonViewModel = EvidenceComparisonViewModel


def _render_refs(refs: Sequence[ComparisonSourceRef]) -> str:
    if not refs:
        return NOT_RECORDED
    values: list[str] = []
    for ref in refs:
        label = escape(ref.source_id)
        if target := public_locator(ref.locator):
            values.append(f'<a class="comparison-source-link" href="{escape(target, quote=True)}">{label}</a>')
        else:
            values.append(f'<span class="comparison-source-unconfirmed">{label} — {NOT_RECORDED}</span>')
    return " · ".join(values)


def _axis_label(axis: ComparisonAxis) -> str:
    return axis.value.replace("_", " ").title()


def render_evidence_comparison(
    view_or_model: EvidenceComparisonViewModel | ManagerReadModel,
    *,
    query_context: QueryContext = None,
    include_raw_json: bool = True,
) -> str:
    """Render the general S4 object comparison without shell integration."""

    del query_context  # The shell owns routing; this fragment has no navigation side effects.
    view = (
        view_or_model
        if isinstance(view_or_model, EvidenceComparisonViewModel)
        else EvidenceComparisonViewModel.from_read_model(view_or_model)
    )
    model = view.read_model
    comparison = view.comparison
    result = comparison.result.value if comparison is not None else NOT_RECORDED
    refs = (
        comparison.source_refs
        if comparison is not None
        else tuple(
            ComparisonSourceRef(source.source_id, source.locator, source.owner, source.schema, source.revision)
            for source in model.source_refs
        )
    )
    pieces = [
        f'<section class="evidence-comparison-page" data-integration-hook="{EVIDENCE_COMPARISON_INTEGRATION_HOOK}" '
        f'data-comparison-result="{escape(result, quote=True)}" data-read-status="{model.availability.status.value}">',
        '<p class="eyebrow">Evidence / object comparison · read-only</p>',
        '<h1 class="page-title" data-page-title tabindex="-1">Evidence/object comparison</h1>',
        '<p class="page-intro">This is the general S4 object comparison contract, not the S2 Strategy Genome comparison. '
        'Only the eleven declared axes are shown; no missing value is filled with a default.</p>',
        f'<p class="context-line comparison-context"><span><strong>Observed</strong> {escape(model.as_of or "Unavailable")}</span>'
        f'<span><strong>Snapshot</strong> {escape(model.snapshot_token or "Unavailable")}</span></p>',
        render_status_block(model),
    ]
    if comparison is None:
        detail = (
            "No explicit object comparison is recorded in this scope."
            if model.availability.status is ReadModelStatus.MISSING
            else model.availability.reason or "The object comparison is not determined in this scope."
        )
        pieces.append(
            f'<section class="comparison-not-recorded" data-display-state="empty"><h2>Comparison not recorded</h2>'
            f'<p>{escape(detail)}</p></section>'
        )
    else:
        pieces.append(
            f'<section class="comparison-summary" data-comparison-kind="general-object">'
            f'<p class="comparison-result" data-comparison-result="{comparison.result.value}">Result: {comparison.result.value}</p>'
            f'<p>{escape(comparison.reason or "All declared comparison axes are available.")}</p>'
            f'<dl class="comparison-provenance"><div><dt>Left object</dt><dd>{escape(comparison.left_object_type or NOT_RECORDED)} / {escape(comparison.left_object_id or NOT_RECORDED)}</dd></div>'
            f'<div><dt>Right object</dt><dd>{escape(comparison.right_object_type or NOT_RECORDED)} / {escape(comparison.right_object_id or NOT_RECORDED)}</dd></div>'
            f'<div><dt>Source refs</dt><dd>{_render_refs(refs)}</dd></div></dl></section>'
        )
        rows = "".join(
            f'<tr data-axis="{axis.axis.value}" data-axis-state="{axis.state.value}">'
            f'<th scope="row">{escape(_axis_label(axis.axis))}</th>'
            f'<td><span class="axis-state" data-axis-state="{axis.state.value}">{axis.state.value}</span></td>'
            f'<td>{escape(_display(axis.left_value))}</td><td>{escape(_display(axis.right_value))}</td>'
            f'<td>{escape(axis.reason or NOT_RECORDED)}</td><td>{_render_refs(axis.source_refs)}</td></tr>'
            for axis in comparison.axes
        )
        pieces.append(
            '<section class="comparison-axes"><h2>Axis-by-axis comparison</h2>'
            '<table><caption>General object comparison axes</caption><thead><tr><th>Axis</th><th>State</th>'
            '<th>Left</th><th>Right</th><th>Reason</th><th>Source refs</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></section>'
        )
        pieces.append(
            '<section class="comparison-boundary" data-statistics="not-generated">'
            '<h2>Interpretation boundary</h2><p>No aggregate performance statistic or ordering is generated here without an explicit denominator. '
            'This projection does not recalculate metrics, fills, costs, or evidence.</p></section>'
        )
    if include_raw_json:
        pieces.append(
            '<details class="comparison-raw-json"><summary>Raw JSON</summary>'
            f'<pre>{escape(view.raw_json)}</pre></details>'
        )
    pieces.append("</section>")
    return "".join(pieces)


def evidence_comparison_view(
    provider: ManagerDataProvider, *, snapshot_token: str | None = None
) -> EvidenceComparisonViewModel:
    """Read the approved comparison resource exactly once."""

    return EvidenceComparisonViewModel.from_read_model(
        provider.read(EVIDENCE_COMPARISON_RESOURCE, snapshot_token=snapshot_token)
    )


def render_evidence_comparison_view(
    provider_or_model: ManagerDataProvider | ManagerReadModel,
    *,
    snapshot_token: str | None = None,
    query_context: QueryContext = None,
) -> str:
    """S4-T3 integration hook accepting a provider or cached envelope."""

    view = (
        EvidenceComparisonViewModel.from_read_model(provider_or_model)
        if isinstance(provider_or_model, ManagerReadModel)
        else evidence_comparison_view(provider_or_model, snapshot_token=snapshot_token)
    )
    return render_evidence_comparison(view, query_context=query_context)


# Hook aliases keep the public seam easy to discover while retaining one
# implementation and avoiding any dependency on the shared router.
render_object_comparison = render_evidence_comparison
render_object_comparison_view = render_evidence_comparison_view
render_comparison = render_evidence_comparison
render_comparison_view = render_evidence_comparison_view
object_comparison_view = evidence_comparison_view


# ----------------------------- deterministic fixtures ------------------------


def _fixture_source(source_id: str, locator: str, revision: str = "fixture-v0") -> SourceReference:
    return SourceReference(
        source_id=source_id,
        owner="manager-gui-public-fixture",
        kind="published-object-record",
        locator=locator,
        schema="manager-gui.evidence-comparison.fixture.v0",
        revision=revision,
    )


def _fixture_axes() -> dict[str, object]:
    return {
        "identity": {"logical_identity": "strategy-run-fixture", "revision": "r1"},
        "data_version": {"dataset": "prices-2026-09", "adjustment": "split"},
        "universe": {"name": "fixture-universe", "members": ["AAA", "BBB"]},
        "time_range": {"start": "2020-01-01", "end": "2024-12-31", "timezone": "UTC"},
        "protocol": {"id": "protocol-fixture-v1", "version": "1"},
        "randomness": {"seed": 7, "policy": "frozen"},
        "costs": {"commission_bps": 5, "slippage_bps": 2},
        "fills": {"policy": "published-fills-v1", "partial_fills": True},
        "metric_definition": {"return": "time_weighted", "drawdown": "peak_to_trough"},
        "evidence_sections": ["conclusion", "protocol", "limitations"],
        "currency": {"base": "USD", "conversion": "published-fx-v1"},
    }


def _fixture_payload(state: EvidenceComparisonFixtureState) -> dict[str, object]:
    left_axes = _fixture_axes()
    right_axes = dict(left_axes)
    if state is EvidenceComparisonFixtureState.DIFFERENT:
        right_axes["costs"] = {"commission_bps": 8, "slippage_bps": 2}
        right_axes["metric_definition"] = {"return": "money_weighted", "drawdown": "peak_to_trough"}
    elif state in {
        EvidenceComparisonFixtureState.INCOMPARABLE,
        EvidenceComparisonFixtureState.INCOMPATIBLE,
        EvidenceComparisonFixtureState.DATA_VERSION_INCONSISTENT,
    }:
        right_axes["data_version"] = {
            "dataset": "prices-2026-10",
            "adjustment": "split",
            "compatible": False,
        }
    elif state is EvidenceComparisonFixtureState.PROTOCOL_INCOMPATIBLE:
        right_axes["protocol"] = {
            "id": "protocol-fixture-v2",
            "version": "2",
            "compatible": False,
        }
    elif state is EvidenceComparisonFixtureState.MISSING:
        right_axes.pop("currency")
    elif state is EvidenceComparisonFixtureState.PARTIAL:
        right_axes.pop("fills")
        right_axes.pop("evidence_sections")
    left = {
        "object_type": "run",
        "object_id": "run-fixture-left",
        "axes": left_axes,
        "source_refs": ["comparison-fixture-left"],
    }
    right = {
        "object_type": "run",
        "object_id": "run-fixture-right",
        "axes": right_axes,
        "source_refs": ["comparison-fixture-right"],
    }
    return {
        "comparison": {
            "left": left,
            "right": right,
            "source_refs": ["comparison-fixture-left", "comparison-fixture-right"],
            "reason": "Synthetic public object comparison fixture.",
        }
    }


def build_evidence_comparison_fixture(
    state: EvidenceComparisonFixtureState | str = EvidenceComparisonFixtureState.COMPLETE,
) -> ManagerReadModel:
    """Build a fresh fixture without filesystem, private storage, or writes."""

    selected = EvidenceComparisonFixtureState(state)
    left_source = _fixture_source(
        "comparison-fixture-left", "fixture://manager-gui/comparison/object-left"
    )
    right_source = _fixture_source(
        "comparison-fixture-right", "fixture://manager-gui/comparison/object-right", "fixture-v1"
    )
    sources = (left_source, right_source)
    status = ReadModelStatus.DERIVED
    complete = True
    reason = "The fixture contains the published general object comparison."
    errors: tuple[ReadModelError, ...] = ()
    as_of: str | None = "2026-10-03T13:00:00Z"
    snapshot: str | None = f"evidence-comparison-{selected.value}-v0"
    if selected is EvidenceComparisonFixtureState.MISSING:
        status, complete, reason, as_of, snapshot = (
            ReadModelStatus.MISSING,
            False,
            "No explicit object comparison is recorded in this scope.",
            None,
            None,
        )
        data: dict[str, object] = {}
    elif selected is EvidenceComparisonFixtureState.BLOCKED:
        status, complete, reason, as_of = (
            ReadModelStatus.BLOCKED,
            False,
            "The approved object comparison read seam is blocked.",
            None,
        )
        data = {}
        errors = (ReadModelError("comparison_read_blocked", reason),)
    elif selected is EvidenceComparisonFixtureState.STALE:
        status, complete, reason = (
            ReadModelStatus.STALE,
            False,
            "The object comparison source is stale.",
        )
        data = {}
        errors = (ReadModelError("comparison_source_stale", reason),)
    elif selected is EvidenceComparisonFixtureState.INTEGRITY_FAILURE:
        status, complete, reason = (
            ReadModelStatus.INTEGRITY_FAILURE,
            False,
            "The object comparison artifact failed integrity validation.",
        )
        data = {}
        errors = (ReadModelError("comparison_integrity_failure", reason),)
    elif selected is EvidenceComparisonFixtureState.API_UNAVAILABLE:
        status, complete, reason, as_of, snapshot = (
            ReadModelStatus.API_UNAVAILABLE,
            False,
            "The approved public object comparison API is unavailable.",
            None,
            None,
        )
        data = {}
        errors = (ReadModelError("comparison_api_unavailable", reason, retryable=True),)
    else:
        data = _fixture_payload(selected)
        if selected is EvidenceComparisonFixtureState.PARTIAL:
            status, complete, reason = (
                ReadModelStatus.KNOWN,
                False,
                "Only part of the object comparison is published in this scope.",
            )
            errors = (ReadModelError("comparison_scope_partial", reason),)
    return ManagerReadModel(
        data=cast(JSONValue, data),
        source_refs=sources,
        as_of=as_of,
        snapshot_token=snapshot,
        derivation=Derivation(
            kind="derived" if status is ReadModelStatus.DERIVED else "direct",
            rule="manager-gui.evidence-object-comparison.v0" if status is ReadModelStatus.DERIVED else None,
            inputs=tuple(source.source_id for source in sources),
            version="v0",
        ),
        availability=Availability(status=status, complete=complete, reason=reason, retryable=status is ReadModelStatus.API_UNAVAILABLE),
        errors=errors,
    )


@dataclass(frozen=True, slots=True)
class EvidenceComparisonFixtureProvider:
    """Read-only provider for general object comparison fixtures."""

    state: EvidenceComparisonFixtureState

    def __init__(self, state: EvidenceComparisonFixtureState | str = EvidenceComparisonFixtureState.COMPLETE) -> None:
        object.__setattr__(self, "state", EvidenceComparisonFixtureState(state))

    def read(
        self,
        resource: str = EVIDENCE_COMPARISON_RESOURCE,
        *,
        snapshot_token: str | None = None,
    ) -> ManagerReadModel:
        del snapshot_token
        if resource not in {
            EVIDENCE_COMPARISON_RESOURCE,
            "object_comparison",
            "object-comparison",
            EVIDENCE_COMPARISON_ROUTE,
        }:
            raise ValueError(f"comparison fixture does not serve resource {resource!r}")
        return build_evidence_comparison_fixture(self.state)


def evidence_comparison_fixture_provider(
    state: EvidenceComparisonFixtureState | str = EvidenceComparisonFixtureState.COMPLETE,
) -> EvidenceComparisonFixtureProvider:
    return EvidenceComparisonFixtureProvider(state)


# Compatibility aliases describe the same S4-T3 general comparison, never S2
# Genome comparison semantics.
build_object_comparison_fixture = build_evidence_comparison_fixture
build_comparison_fixture = build_evidence_comparison_fixture
comparison_fixture_provider = evidence_comparison_fixture_provider
fixture_evidence_comparison_provider = evidence_comparison_fixture_provider
EvidenceComparisonProvider = EvidenceComparisonFixtureProvider
EvidenceComparisonView = EvidenceComparisonViewModel
ObjectComparisonView = EvidenceComparisonViewModel


__all__ = [
    "EVIDENCE_COMPARISON_FIXTURE_STATES",
    "EVIDENCE_COMPARISON_INTEGRATION_HOOK",
    "EVIDENCE_COMPARISON_INTEGRATION_HOOK_PATH",
    "EVIDENCE_COMPARISON_RESOURCE",
    "EVIDENCE_COMPARISON_ROUTE",
    "OBJECT_COMPARISON_AXES",
    "AxisComparison",
    "AxisComparisonState",
    "ComparisonAxis",
    "ComparisonAxisState",
    "ComparisonFixtureState",
    "ComparisonOutcome",
    "ComparisonResult",
    "ComparisonSourceRef",
    "ComparisonStatus",
    "EvidenceComparison",
    "EvidenceComparisonFixtureProvider",
    "EvidenceComparisonFixtureState",
    "EvidenceComparisonProvider",
    "EvidenceComparisonView",
    "EvidenceComparisonViewModel",
    "EvidenceObjectComparison",
    "EvidenceObjectComparisonViewModel",
    "ObjectComparison",
    "ObjectComparisonAxis",
    "ObjectComparisonResult",
    "ObjectComparisonView",
    "ObjectComparisonViewModel",
    "build_comparison_fixture",
    "build_evidence_comparison_fixture",
    "build_object_comparison_fixture",
    "compare_objects",
    "comparison_fixture_provider",
    "evidence_comparison_fixture_provider",
    "evidence_comparison_view",
    "fixture_evidence_comparison_provider",
    "object_comparison_view",
    "render_comparison",
    "render_comparison_view",
    "render_evidence_comparison",
    "render_evidence_comparison_view",
    "render_object_comparison",
    "render_object_comparison_view",
]
