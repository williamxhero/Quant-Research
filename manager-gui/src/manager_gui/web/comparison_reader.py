"""Reader projection for explicit object comparisons.

The comparison Reader is a presentation-only adapter.  It consumes one public
:class:`~manager_gui.models.ManagerReadModel`, keeps that v0 envelope unchanged,
and projects an explanation layer with four per-axis states:
``equal``, ``different``, ``missing`` and ``not_comparable``.

Identity, eligibility, source generation, and snapshot are comparison gates.
A missing or mismatching gate refuses the comparison instead of turning the
condition into a difference.  No metric, rate, ranking, or denominator is
calculated by this module.  Expert and Raw links continue to point at the
unchanged v0 source through the existing Reader mode contract.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
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
from ..reader import (
    ClaimKind,
    FrozenJSON,
    ReaderAvailability,
    ReaderAvailabilityStatus,
    ReaderClaim,
    ReaderProjection,
    ReaderSummary,
    SampleData,
    project_read_model,
)
from ..reader.mode import ProjectionMode, ReaderURLState
from .i18n import Translator
from .locators import public_locator
from .navigation import ViewId, context_link
from .reader_surface import ReaderPage, render_reader_surface
from .status import display_state_for, render_status_block

# HTML fragments intentionally keep readable markup at the call site.
# ruff: noqa: E501

QueryContext: TypeAlias = str | Mapping[str, object] | None
JSONMapping: TypeAlias = Mapping[str, JSONValue]
_MISSING = object()

COMPARISON_READER_RESOURCE = "comparison"
COMPARISON_READER_ROUTE = "strategy-genome-comparison"
COMPARISON_READER_HOOK = "comparison-reader-view"
# Preserve the R3 route seam while the Reader hook identifies the adapter.
COMPARISON_READER_INTEGRATION_HOOK = "strategy-genome-comparison-view"
COMPARISON_READER_INTEGRATION_HOOK_PATH = (
    "manager_gui.web.comparison_reader.render_comparison_reader_view"
)
COMPARISON_READER_RULE = "manager-gui.reader.comparison.v1"
COMPARISON_READER_VERSION = "v1"
NOT_RECORDED = "not recorded"
# Names used by callers that already know one of the older comparison seams.
COMPARISON_RESOURCE = COMPARISON_READER_RESOURCE
COMPARISON_READER_RESOURCES = (
    COMPARISON_READER_RESOURCE,
    "comparison_reader",
    "genome_comparison",
    "evidence_comparison",
)


class ComparisonReaderAxis(StrEnum):
    """Axes shown by the Comparison Reader.

    The first four are gates.  A gate mismatch is not evidence that one object
    is merely different; it means the requested comparison has been refused.
    """

    IDENTITY = "identity"
    ELIGIBILITY = "eligibility"
    SOURCE_GENERATION = "source_generation"
    SNAPSHOT = "snapshot"
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


COMPARISON_READER_AXES: tuple[ComparisonReaderAxis, ...] = tuple(ComparisonReaderAxis)
OBJECT_COMPARISON_AXES = COMPARISON_READER_AXES
COMPARISON_GATE_AXES = frozenset(
    {
        ComparisonReaderAxis.IDENTITY,
        ComparisonReaderAxis.ELIGIBILITY,
        ComparisonReaderAxis.SOURCE_GENERATION,
        ComparisonReaderAxis.SNAPSHOT,
        ComparisonReaderAxis.PROTOCOL,
    }
)


class ComparisonReaderAxisState(StrEnum):
    EQUAL = "equal"
    DIFFERENT = "different"
    MISSING = "missing"
    NOT_COMPARABLE = "not_comparable"
    INCOMPARABLE = "not_comparable"  # compatibility spelling; render as not_comparable


class ComparisonReaderOutcome(StrEnum):
    EQUAL = "equal"
    DIFFERENT = "different"
    MISSING = "missing"
    NOT_COMPARABLE = "not_comparable"
    INCOMPARABLE = "not_comparable"  # compatibility spelling; render as not_comparable


# Discoverable aliases parallel the existing Evidence comparison vocabulary.
ComparisonAxis = ComparisonReaderAxis
AxisComparisonState = ComparisonReaderAxisState
ComparisonAxisState = ComparisonReaderAxisState
ComparisonOutcome = ComparisonReaderOutcome
ComparisonResult = ComparisonReaderOutcome
ComparisonStatus = ComparisonReaderOutcome


class ComparisonReaderFixtureState(StrEnum):
    COMPLETE = "complete"
    EQUAL = "equal"
    DIFFERENT = "different"
    MISSING = "missing"
    NOT_COMPARABLE = "not_comparable"
    INCOMPARABLE = "incomparable"
    BLOCKED = "blocked"
    STALE = "stale"
    INTEGRITY_FAILURE = "integrity_failure"
    API_UNAVAILABLE = "api_unavailable"


COMPARISON_READER_FIXTURE_STATES = tuple(state.value for state in ComparisonReaderFixtureState)
ComparisonFixtureState = ComparisonReaderFixtureState


_AXIS_ALIASES: Mapping[ComparisonReaderAxis, tuple[str, ...]] = {
    ComparisonReaderAxis.IDENTITY: (
        "identity",
        "object_identity",
        "logical_identity",
        "identity_key",
    ),
    ComparisonReaderAxis.ELIGIBILITY: (
        "eligibility",
        "comparison_eligibility",
        "eligible",
        "qualification",
        "qualification_status",
    ),
    ComparisonReaderAxis.SOURCE_GENERATION: (
        "source_generation",
        "source_generation_id",
        "source_generation_token",
        "generation",
        "generation_id",
        "source_revision",
    ),
    ComparisonReaderAxis.SNAPSHOT: (
        "snapshot",
        "snapshot_token",
        "snapshot_id",
        "read_snapshot",
        "source_snapshot",
    ),
    ComparisonReaderAxis.DATA_VERSION: (
        "data_version",
        "dataVersion",
        "data_snapshot",
        "dataSnapshot",
        "data_requirements",
    ),
    ComparisonReaderAxis.UNIVERSE: (
        "universe",
        "universe_definition",
        "instrument_universe",
    ),
    ComparisonReaderAxis.TIME_RANGE: ("time_range", "timeRange", "date_range", "period"),
    ComparisonReaderAxis.PROTOCOL: ("protocol", "protocol_definition", "protocol_id"),
    ComparisonReaderAxis.RANDOMNESS: ("randomness", "random_seed", "seed"),
    ComparisonReaderAxis.COSTS: ("costs", "cost", "cost_model", "fees", "fee_model"),
    ComparisonReaderAxis.FILLS: ("fills", "fill_policy", "execution_fills", "fill_model"),
    ComparisonReaderAxis.METRIC_DEFINITION: (
        "metric_definition",
        "metricDefinition",
        "metrics",
        "metric_policy",
    ),
    ComparisonReaderAxis.EVIDENCE_SECTIONS: (
        "evidence_sections",
        "evidenceSections",
        "sections",
    ),
    ComparisonReaderAxis.CURRENCY: ("currency", "currency_policy", "base_currency"),
}


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


def _first(item: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        if (value := _text(item.get(key))) is not None:
            return value
    return None


def _owner_source(item: Mapping[str, object], *keys: str) -> str | None:
    """Read owner prose without stripping or translating its source bytes."""

    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
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
    if text is None:
        return None
    return text.lower().replace("-", "_").replace(" ", "_")


def _canonical(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError):
        return repr(value)


def _present(value: object) -> bool:
    return value is not _MISSING and value is not None and value not in ("", [], {})


def _normalise_axis(value: object) -> ComparisonReaderAxis | None:
    token = _normalise(value)
    if token is None:
        return None
    for axis, aliases in _AXIS_ALIASES.items():
        if token == axis.value or token in {_normalise(alias) for alias in aliases}:
            return axis
    return None


def _normalise_state(value: object) -> ComparisonReaderAxisState | None:
    token = _normalise(value)
    if token in {"same", "identical", "match", "matched"}:
        return ComparisonReaderAxisState.EQUAL
    if token in {"changed", "not_equal", "different"}:
        return ComparisonReaderAxisState.DIFFERENT
    if token in {"absent", "not_recorded", "unknown", "missing"}:
        return ComparisonReaderAxisState.MISSING
    if token in {"incompatible", "incomparable", "not_comparable", "blocked"}:
        return ComparisonReaderAxisState.NOT_COMPARABLE
    if token is None:
        return None
    try:
        return ComparisonReaderAxisState(token)
    except ValueError:
        return None


def _axis_container(item: Mapping[str, object]) -> Mapping[str, object]:
    for key in ("axes", "comparison_axes", "comparisonAxes"):
        nested = _mapping(item.get(key))
        if nested is not None:
            return nested
    return item


def _axis_value(item: Mapping[str, object], axis: ComparisonReaderAxis) -> object:
    container = _axis_container(item)
    for key in _AXIS_ALIASES[axis]:
        if key in container:
            return container[key]
        if key in item:
            return item[key]

    # These fields are explicit identity/eligibility records, not values
    # inferred from an object id or from the number of source references.
    if axis is ComparisonReaderAxis.IDENTITY:
        values: dict[str, object] = {}
        for key in ("strategy_id", "strategy_key", "genome_family_id", "object_type", "record_type", "type"):
            if key in item:
                values[key] = item[key]
        return values or _MISSING
    if axis is ComparisonReaderAxis.ELIGIBILITY:
        for key in ("validation", "validation_status", "eligibility_status"):
            if key in item:
                return item[key]
    if axis is ComparisonReaderAxis.SOURCE_GENERATION:
        provenance = _mapping(item.get("provenance"))
        if provenance is not None:
            for key in _AXIS_ALIASES[axis]:
                if key in provenance:
                    return provenance[key]
    if axis is ComparisonReaderAxis.SNAPSHOT:
        provenance = _mapping(item.get("provenance"))
        if provenance is not None:
            for key in _AXIS_ALIASES[axis]:
                if key in provenance:
                    return provenance[key]
    if axis is ComparisonReaderAxis.EVIDENCE_SECTIONS:
        evidence = _mapping(item.get("evidence"))
        if evidence is not None and "sections" in evidence:
            return evidence["sections"]
    return _MISSING


def _incompatibility(value: object) -> str | None:
    item = _mapping(value)
    if item is None:
        return None
    if item.get("compatible") is False:
        return "The published axis declares the two values incompatible."
    if item.get("incompatible") is True:
        return "The published axis declares an incompatibility."
    status = _normalise(item.get("status", item.get("state")))
    if status in {"incomparable", "incompatible", "not_comparable", "blocked"}:
        return f"The published axis status is {status}."
    nested = _mapping(item.get("compatibility"))
    if nested is not None and nested.get("compatible") is False:
        return "The published compatibility declaration is false."
    return None


def _eligibility_refuses(value: object) -> bool:
    """Return true only for an explicit negative eligibility declaration."""

    if value is False:
        return True
    item = _mapping(value)
    if item is None:
        return False
    if item.get("eligible") is False or item.get("comparable") is False:
        return True
    status = _normalise(item.get("status", item.get("state", item.get("result"))))
    return status in {"ineligible", "not_eligible", "not_comparable", "incomparable", "blocked"}


def _comparison_payload(data: object) -> Mapping[str, object]:
    root = _mapping(data) or {}
    for key in ("comparison_reader", "comparison", "object_comparison", "evidence_comparison"):
        nested = _mapping(root.get(key))
        if nested is not None:
            return nested
    return root


def _object_pair(payload: Mapping[str, object]) -> tuple[Mapping[str, object], Mapping[str, object]] | None:
    for left_key, right_key in (
        ("left", "right"),
        ("left_object", "right_object"),
        ("left_genome", "right_genome"),
        ("left_strategy", "right_strategy"),
        ("left_revision", "right_revision"),
    ):
        left = _mapping(payload.get(left_key))
        right = _mapping(payload.get(right_key))
        if left is not None and right is not None:
            return left, right
    objects = [item for item in _sequence(payload.get("objects")) if _mapping(item) is not None]
    if len(objects) >= 2:
        return cast(Mapping[str, object], objects[0]), cast(Mapping[str, object], objects[1])
    return None


def _explicit_axis_results(payload: Mapping[str, object]) -> dict[ComparisonReaderAxis | str, object]:
    raw: object = None
    for key in ("axis_results", "axis_comparisons", "axisComparisons", "results"):
        if key in payload:
            raw = payload[key]
            break
    if raw is None:
        candidate = payload.get("axes")
        if isinstance(candidate, Mapping):
            raw = candidate
    if isinstance(raw, Mapping):
        entries = tuple(raw.items())
    else:
        entries = tuple(
            (
                _first(_mapping(entry) or {}, "axis", "name", "key"),
                entry,
            )
            for entry in _sequence(raw)
        )
    result: dict[ComparisonReaderAxis | str, object] = {}
    for name, value in entries:
        axis = _normalise_axis(name)
        if axis is None:
            continue
        result[axis] = value if isinstance(value, Mapping) else {"state": value}
    return result


def _axis_sets(payload: Mapping[str, object]) -> tuple[set[ComparisonReaderAxis], set[ComparisonReaderAxis]]:
    missing: set[ComparisonReaderAxis] = set()
    refused: set[ComparisonReaderAxis] = set()
    for key, target in (("missing_axes", missing), ("incompatible_axes", refused), ("not_comparable_axes", refused)):
        raw = payload.get(key)
        values = (raw,) if isinstance(raw, str) else _sequence(raw)
        for value in values:
            if (axis := _normalise_axis(value)) is not None:
                target.add(axis)
    return missing, refused


def _source_refs(model: ManagerReadModel) -> tuple[SourceReference, ...]:
    return tuple(model.source_refs)


@dataclass(frozen=True, slots=True)
class ComparisonReaderAxisResult:
    """One explicit comparison axis and its refusal boundary."""

    axis: ComparisonReaderAxis
    state: ComparisonReaderAxisState
    left_value: JSONValue | None = None
    right_value: JSONValue | None = None
    reason: str | None = None
    source_refs: tuple[SourceReference, ...] = ()
    raw: JSONMapping = field(default_factory=dict, repr=False, compare=False)
    owner_reason: bool = field(default=False, repr=False, compare=False)

    @property
    def left(self) -> JSONValue | None:
        return self.left_value

    @property
    def right(self) -> JSONValue | None:
        return self.right_value

    @property
    def comparable(self) -> bool:
        return self.state in {
            ComparisonReaderAxisState.EQUAL,
            ComparisonReaderAxisState.DIFFERENT,
        }

    @property
    def refused(self) -> bool:
        return self.state is ComparisonReaderAxisState.NOT_COMPARABLE

    @property
    def availability_status(self) -> ReaderAvailabilityStatus:
        if self.state is ComparisonReaderAxisState.NOT_COMPARABLE:
            return ReaderAvailabilityStatus.INCOMPARABLE
        if self.state is ComparisonReaderAxisState.MISSING:
            return ReaderAvailabilityStatus.MISSING
        return ReaderAvailabilityStatus.DERIVED

    @property
    def availability(self) -> ReaderAvailabilityStatus:
        return self.availability_status

    def to_dict(self) -> dict[str, object]:
        return {
            "axis": self.axis.value,
            "state": self.state.value,
            "left": self.left_value,
            "right": self.right_value,
            "availability": self.availability_status.value,
            "reason": self.reason,
            "source_refs": [reference.to_dict() for reference in self.source_refs],
        }


@dataclass(frozen=True, slots=True)
class ComparisonReaderComparison:
    """All axis results; deliberately contains no aggregate statistic."""

    axes: tuple[ComparisonReaderAxisResult, ...]
    left_object_type: str | None = None
    right_object_type: str | None = None
    left_object_id: str | None = None
    right_object_id: str | None = None
    source_refs: tuple[SourceReference, ...] = ()
    reason: str | None = None
    raw: JSONMapping = field(default_factory=dict, repr=False, compare=False)
    owner_reason: bool = field(default=False, repr=False, compare=False)

    @property
    def result(self) -> ComparisonReaderOutcome:
        states = {axis.state for axis in self.axes}
        if ComparisonReaderAxisState.NOT_COMPARABLE in states:
            return ComparisonReaderOutcome.NOT_COMPARABLE
        if ComparisonReaderAxisState.MISSING in states:
            return ComparisonReaderOutcome.MISSING
        if ComparisonReaderAxisState.DIFFERENT in states:
            return ComparisonReaderOutcome.DIFFERENT
        return ComparisonReaderOutcome.EQUAL

    @property
    def status(self) -> ComparisonReaderOutcome:
        return self.result

    @property
    def refused(self) -> bool:
        return self.result is ComparisonReaderOutcome.NOT_COMPARABLE

    @property
    def equal_axes(self) -> tuple[str, ...]:
        return tuple(axis.axis.value for axis in self.axes if axis.state is ComparisonReaderAxisState.EQUAL)

    @property
    def different_axes(self) -> tuple[str, ...]:
        return tuple(axis.axis.value for axis in self.axes if axis.state is ComparisonReaderAxisState.DIFFERENT)

    @property
    def changed_axes(self) -> tuple[str, ...]:
        return self.different_axes

    @property
    def missing_axes(self) -> tuple[str, ...]:
        return tuple(axis.axis.value for axis in self.axes if axis.state is ComparisonReaderAxisState.MISSING)

    @property
    def not_comparable_axes(self) -> tuple[str, ...]:
        return tuple(axis.axis.value for axis in self.axes if axis.state is ComparisonReaderAxisState.NOT_COMPARABLE)

    @property
    def incompatible_axes(self) -> tuple[str, ...]:
        return self.not_comparable_axes

    @property
    def denominator(self) -> None:
        return None

    @property
    def success_rate(self) -> None:
        return None

    @property
    def ranking(self) -> None:
        return None

    def axis(self, name: ComparisonReaderAxis | str) -> ComparisonReaderAxisResult:
        selected = ComparisonReaderAxis(name)
        return next(axis for axis in self.axes if axis.axis is selected)

    def to_dict(self) -> dict[str, object]:
        return {
            "comparison_kind": "reader_object_comparison",
            "result": self.result.value,
            "left_object_type": self.left_object_type,
            "right_object_type": self.right_object_type,
            "left_object_id": self.left_object_id,
            "right_object_id": self.right_object_id,
            "axes": [axis.to_dict() for axis in self.axes],
            "equal_axes": list(self.equal_axes),
            "different_axes": list(self.different_axes),
            "missing_axes": list(self.missing_axes),
            "not_comparable_axes": list(self.not_comparable_axes),
            "source_refs": [reference.to_dict() for reference in self.source_refs],
            "reason": self.reason,
        }


ObjectComparison = ComparisonReaderComparison
ComparisonAxisResult = ComparisonReaderAxisResult


def _axis_reason(state: ComparisonReaderAxisState) -> str:
    return {
        ComparisonReaderAxisState.EQUAL: "The published axis values are equal.",
        ComparisonReaderAxisState.DIFFERENT: "The published axis values differ.",
        ComparisonReaderAxisState.MISSING: "The axis is not published for both objects.",
        ComparisonReaderAxisState.NOT_COMPARABLE: (
            "Identity, eligibility, source generation, snapshot, or protocol is inconsistent or missing."
        ),
    }[state]


def compare_reader_objects(
    left: Mapping[str, object],
    right: Mapping[str, object],
    *,
    axis_results: Mapping[ComparisonReaderAxis | str, object] | None = None,
    missing_axes: Sequence[ComparisonReaderAxis | str] = (),
    not_comparable_axes: Sequence[ComparisonReaderAxis | str] = (),
    source_refs: Sequence[SourceReference] = (),
    reason: str | None = None,
) -> ComparisonReaderComparison:
    """Compare explicit JSON values and refuse comparison at gate axes.

    This function never looks at numeric magnitudes or computes an outcome
    metric.  The left and right mappings are copied only into the presentation
    object; the input ManagerReadModel remains untouched by the caller.
    """

    declared: dict[ComparisonReaderAxis, Mapping[str, object]] = {}
    for name, value in (axis_results or {}).items():
        axis = _normalise_axis(name)
        if axis is not None:
            declared[axis] = value if isinstance(value, Mapping) else {"state": value}
    missing = {_normalise_axis(value) for value in missing_axes}
    refused = {_normalise_axis(value) for value in not_comparable_axes}
    missing.discard(None)
    refused.discard(None)
    axes: list[ComparisonReaderAxisResult] = []
    for axis in COMPARISON_READER_AXES:
        left_value = _axis_value(left, axis)
        right_value = _axis_value(right, axis)
        declaration = declared.get(axis, {})
        declared_left = declaration.get("left", declaration.get("left_value", _MISSING))
        declared_right = declaration.get("right", declaration.get("right_value", _MISSING))
        if declared_left is not _MISSING:
            left_value = declared_left
        if declared_right is not _MISSING:
            right_value = declared_right
        declared_value = declaration.get(
            "state", declaration.get("status", declaration.get("result"))
        )
        declared_state = _normalise_state(declared_value)
        declared_state_present = any(
            key in declaration for key in ("state", "status", "result")
        )
        declared_state_unknown = (
            declared_state_present
            and declared_value is not None
            and declared_state is None
        )
        axis_reason = _owner_source(declaration, "reason", "message", "detail")
        owner_reason = axis_reason is not None
        if axis in refused or declared_state is ComparisonReaderAxisState.NOT_COMPARABLE:
            state = ComparisonReaderAxisState.NOT_COMPARABLE
        elif axis in missing or declared_state is ComparisonReaderAxisState.MISSING:
            state = ComparisonReaderAxisState.NOT_COMPARABLE if axis in COMPARISON_GATE_AXES else ComparisonReaderAxisState.MISSING
        elif axis in COMPARISON_GATE_AXES and (
            not _present(left_value)
            or not _present(right_value)
            or _incompatibility(left_value) is not None
            or _incompatibility(right_value) is not None
            or (axis is ComparisonReaderAxis.ELIGIBILITY and (_eligibility_refuses(left_value) or _eligibility_refuses(right_value)))
        ):
            state = ComparisonReaderAxisState.NOT_COMPARABLE
        elif declared_state_unknown:
            state = ComparisonReaderAxisState.NOT_COMPARABLE
            owner_reason = True
            axis_reason = axis_reason or "The owner supplied an unrecognized comparison state."
        elif declared_state in {
            ComparisonReaderAxisState.EQUAL,
            ComparisonReaderAxisState.DIFFERENT,
        } and (not _present(left_value) or not _present(right_value)):
            # A declaration cannot turn absent values into a positive claim.
            state = (
                ComparisonReaderAxisState.NOT_COMPARABLE
                if axis in COMPARISON_GATE_AXES
                else ComparisonReaderAxisState.MISSING
            )
        elif axis in COMPARISON_GATE_AXES and declared_state in {
            ComparisonReaderAxisState.EQUAL,
            ComparisonReaderAxisState.DIFFERENT,
        } and (
            declared_state is ComparisonReaderAxisState.DIFFERENT
            or _canonical(left_value) != _canonical(right_value)
        ):
            # A gate can never be ordinary evidence of difference.  Do not let
            # an explicit declaration hide a source-generation or snapshot
            # mismatch behind an ``equal``/``different`` presentation state.
            state = ComparisonReaderAxisState.NOT_COMPARABLE
        elif declared_state is not None:
            state = declared_state
            if state is ComparisonReaderAxisState.NOT_COMPARABLE:
                owner_reason = True
        elif not _present(left_value) or not _present(right_value):
            state = ComparisonReaderAxisState.MISSING
        elif (incompatibility := _incompatibility(left_value)) is not None or (
            incompatibility := _incompatibility(right_value)
        ) is not None:
            state = ComparisonReaderAxisState.NOT_COMPARABLE
            axis_reason = axis_reason or incompatibility
        elif _canonical(left_value) == _canonical(right_value):
            state = ComparisonReaderAxisState.EQUAL
        else:
            state = ComparisonReaderAxisState.NOT_COMPARABLE if axis in COMPARISON_GATE_AXES else ComparisonReaderAxisState.DIFFERENT
        axis_reason = axis_reason or _axis_reason(state)
        axes.append(
            ComparisonReaderAxisResult(
                axis=axis,
                state=state,
                left_value=_json_value(None if left_value is _MISSING else left_value),
                right_value=_json_value(None if right_value is _MISSING else right_value),
                reason=axis_reason,
                source_refs=tuple(source_refs),
                raw=_json_mapping(declaration),
                owner_reason=owner_reason,
            )
        )
    selected_reason = reason or (
        "The comparison is refused because one or more comparison gates are missing or inconsistent."
        if any(axis.state is ComparisonReaderAxisState.NOT_COMPARABLE for axis in axes)
        else None
    )
    return ComparisonReaderComparison(
        axes=tuple(axes),
        left_object_type=_first(left, "object_type", "objectType", "record_type", "type"),
        right_object_type=_first(right, "object_type", "objectType", "record_type", "type"),
        left_object_id=_first(left, "object_id", "objectId", "genome_id", "genomeId", "strategy_id", "record_id", "recordId", "id"),
        right_object_id=_first(right, "object_id", "objectId", "genome_id", "genomeId", "strategy_id", "record_id", "recordId", "id"),
        source_refs=tuple(source_refs),
        reason=selected_reason,
        raw=_json_mapping({"left": dict(left), "right": dict(right)}),
        owner_reason=reason is not None,
    )


def compare_comparison_reader(
    left: Mapping[str, object], right: Mapping[str, object], **kwargs: object
) -> ComparisonReaderComparison:
    return compare_reader_objects(left, right, **kwargs)  # type: ignore[arg-type]


compare_objects = compare_reader_objects


@dataclass(frozen=True, slots=True)
class ComparisonReaderViewModel:
    """The immutable Reader comparison and its unchanged v0 envelope."""

    read_model: ManagerReadModel
    comparison: ComparisonReaderComparison | None

    @classmethod
    def from_read_model(cls, model: ManagerReadModel) -> ComparisonReaderViewModel:
        comparison: ComparisonReaderComparison | None = None
        readable = (
            model.availability.complete
            and model.availability.status
            not in {
                ReadModelStatus.MISSING,
                ReadModelStatus.BLOCKED,
                ReadModelStatus.STALE,
                ReadModelStatus.INCOMPARABLE,
                ReadModelStatus.INTEGRITY_FAILURE,
                ReadModelStatus.API_UNAVAILABLE,
            }
        )
        if readable:
            payload = _comparison_payload(model.data)
            pair = _object_pair(payload)
            if pair is not None:
                left, right = pair
                declared = _explicit_axis_results(payload)
                missing, refused = _axis_sets(payload)
                comparison = compare_reader_objects(
                    left,
                    right,
                    axis_results=declared,
                    missing_axes=tuple(missing),
                    not_comparable_axes=tuple(refused),
                    source_refs=model.source_refs,
                    reason=_owner_source(payload, "reason", "message", "owner_summary", "summary"),
                )
        return cls(model, comparison)

    @property
    def result(self) -> ComparisonReaderOutcome | None:
        return None if self.comparison is None else self.comparison.result

    @property
    def axes(self) -> tuple[ComparisonReaderAxisResult, ...]:
        return () if self.comparison is None else self.comparison.axes

    @property
    def raw_json(self) -> str:
        return self.read_model.to_json()

    @property
    def source_refs(self) -> tuple[SourceReference, ...]:
        return self.read_model.source_refs

    def to_dict(self) -> dict[str, object]:
        return {
            "view": COMPARISON_READER_ROUTE,
            "comparison": None if self.comparison is None else self.comparison.to_dict(),
            "availability": self.read_model.availability.to_dict(),
            "source_refs": [reference.to_dict() for reference in self.read_model.source_refs],
            "as_of": self.read_model.as_of,
            "snapshot_token": self.read_model.snapshot_token,
            "errors": [error.to_dict() for error in self.read_model.errors],
        }


ComparisonViewModel = ComparisonReaderViewModel
ObjectComparisonViewModel = ComparisonReaderViewModel
ComparisonReaderView = ComparisonReaderViewModel


def _reader_availability(model: ManagerReadModel) -> ReaderAvailability:
    if model.availability.status is ReadModelStatus.KNOWN and not model.availability.complete and any(
        error.code == "not_evaluated" for error in model.errors
    ):
        return ReaderAvailability(ReaderAvailabilityStatus.NOT_EVALUATED, False, model.availability.reason)
    return ReaderAvailability.from_v0(model.availability)


def _gap_kind(status: ReaderAvailabilityStatus) -> ClaimKind:
    if status in {ReaderAvailabilityStatus.BLOCKED, ReaderAvailabilityStatus.INTEGRITY_FAILURE}:
        return ClaimKind.BLOCKED
    if status is ReaderAvailabilityStatus.STALE:
        return ClaimKind.STALE
    if status is ReaderAvailabilityStatus.INCOMPARABLE:
        return ClaimKind.INCOMPARABLE
    return ClaimKind.MISSING


def _projection_claims(
    model: ManagerReadModel,
    comparison: ComparisonReaderComparison | None,
) -> tuple[tuple[ReaderClaim, ...], tuple[ReaderClaim, ...], tuple[ReaderClaim, ...]]:
    refs = _source_refs(model)
    if not refs:
        return (), (), ()
    if (
        not model.availability.complete
        or model.availability.status
        in {
            ReadModelStatus.MISSING,
            ReadModelStatus.BLOCKED,
            ReadModelStatus.STALE,
            ReadModelStatus.INCOMPARABLE,
            ReadModelStatus.INTEGRITY_FAILURE,
            ReadModelStatus.API_UNAVAILABLE,
        }
    ):
        availability = _reader_availability(model)
        if availability.status in {
            ReaderAvailabilityStatus.KNOWN,
            ReaderAvailabilityStatus.DERIVED,
            ReaderAvailabilityStatus.INTERPRETED,
        } and not availability.complete:
            availability = ReaderAvailability(
                ReaderAvailabilityStatus.MISSING,
                False,
                availability.reason,
                availability.retryable,
            )
        gap = ReaderClaim(
            "comparison.read_scope",
            _gap_kind(availability.status),
            refs,
            Derivation("direct", inputs=tuple(ref.source_id for ref in refs), version="v0"),
            availability,
            "comparison read scope",
        )
        return (), (gap,), ()
    if comparison is None:
        availability = ReaderAvailability(ReaderAvailabilityStatus.MISSING, False, "No explicit comparison is recorded.")
        gap = ReaderClaim(
            "comparison.record",
            ClaimKind.MISSING,
            refs,
            Derivation("direct", inputs=tuple(ref.source_id for ref in refs), version="v0"),
            availability,
            "comparison record",
        )
        return (), (), (gap,)
    claims: list[ReaderClaim] = []
    gaps: list[ReaderClaim] = []
    for axis in comparison.axes:
        claim_id = f"comparison.axis.{axis.axis.value}"
        if axis.state in {ComparisonReaderAxisState.EQUAL, ComparisonReaderAxisState.DIFFERENT}:
            claims.append(
                ReaderClaim(
                    claim_id,
                    ClaimKind.DERIVED,
                    refs,
                    Derivation("derived", COMPARISON_READER_RULE, tuple(ref.source_id for ref in refs), COMPARISON_READER_VERSION),
                    ReaderAvailability(ReaderAvailabilityStatus.DERIVED, True),
                    cast(FrozenJSON, axis.to_dict()),
                )
            )
        else:
            status = (
                ReaderAvailabilityStatus.INCOMPARABLE
                if axis.state is ComparisonReaderAxisState.NOT_COMPARABLE
                else ReaderAvailabilityStatus.MISSING
            )
            gaps.append(
                ReaderClaim(
                    claim_id,
                    ClaimKind.INCOMPARABLE if status is ReaderAvailabilityStatus.INCOMPARABLE else ClaimKind.MISSING,
                    refs,
                    Derivation("direct", inputs=tuple(ref.source_id for ref in refs), version="v0"),
                    ReaderAvailability(status, False, axis.reason),
                    cast(FrozenJSON, axis.to_dict()),
                )
            )
    return tuple(claims), tuple(gaps), ()


def project_comparison_reader(
    model: ManagerReadModel,
    *,
    raw_bytes: bytes | None = None,
    sample: bool = False,
    sample_state: str | None = None,
) -> ReaderProjection:
    """Create a Reader v1 projection while retaining exact v0 bytes."""

    view = ComparisonReaderViewModel.from_read_model(model)
    claims, limitations, unknowns = _projection_claims(model, view.comparison)
    all_claims = (*claims, *limitations, *unknowns)
    summary = (
        ReaderSummary("reader.comparison.summary", tuple(claim.claim_id for claim in all_claims), {"n": len(all_claims)})
        if all_claims
        else None
    )
    projection = project_read_model(
        model,
        summary=summary,
        claims=claims,
        limitations=limitations,
        unknowns=unknowns,
        raw_bytes=raw_bytes,
    )
    if sample and projection.source_refs and all(ref.locator.startswith("fixture://") for ref in projection.source_refs):
        projection = replace(projection, sample_data=SampleData(sample_state or "complete", COMPARISON_READER_RESOURCE))
    return projection


project_reader_comparison = project_comparison_reader
project_comparison = project_comparison_reader


def _machine(value: object) -> str:
    if value is None or value == "":
        return ""
    return f'<span translate="no">{escape(str(value), quote=True)}</span>'


def _owner(value: object, translator: Translator) -> str:
    if value is None or value is _MISSING or value == "" or value == [] or value == {}:
        return f'<span class="comparison-value-missing">{escape(translator.t("reader.comparison.not_recorded"))}</span>'
    try:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        text = str(value)
    return f'<span class="comparison-owner-value" data-owner-text="true" translate="no">{translator.source_text(text)}</span>'


def _axis_label(axis: ComparisonReaderAxis, translator: Translator) -> str:
    return escape(translator.t(f"reader.comparison.axis.{axis.value}"))


def _reason(axis: ComparisonReaderAxisResult, translator: Translator) -> str:
    if axis.owner_reason and axis.reason is not None:
        return f'<span data-owner-text="true" translate="no">{translator.source_text(axis.reason)}</span>'
    key = f"reader.comparison.reason.{axis.state.value}"
    return escape(translator.t(key))


def _comparison_reason(comparison: ComparisonReaderComparison, translator: Translator) -> str:
    if not comparison.owner_reason or comparison.reason is None:
        return ""
    return (
        f'<p class="comparison-reader-owner-reason" data-owner-text="true" translate="no">'
        f'{translator.source_text(comparison.reason)}</p>'
    )


def _render_sources(refs: Sequence[SourceReference], *, context: QueryContext, translator: Translator) -> str:
    if not refs:
        return f'<span class="comparison-source-missing">{escape(translator.t("reader.comparison.not_recorded"))}</span>'
    items: list[str] = []
    for reference in refs:
        source_id = _machine(reference.source_id)
        evidence_href = context_link(context, view=ViewId.EVIDENCE, source_id=reference.source_id)
        target = public_locator(reference.locator)
        source_markup = (
            f'<a class="comparison-source-link" href="{escape(target, quote=True)}" translate="no">{source_id}</a>'
            if target
            else f'<span class="comparison-source-unconfirmed" translate="no">{source_id}</span>'
        )
        items.append(
            f'<span class="comparison-source-item">{source_markup} '
            f'<a class="comparison-source-evidence-link" href="{escape(evidence_href, quote=True)}">'
            f'{escape(translator.t("reader.comparison.evidence"))}</a></span>'
        )
    return " · ".join(items)


def _render_axis(axis: ComparisonReaderAxisResult, *, context: QueryContext, translator: Translator) -> str:
    state_label = translator.t(f"reader.comparison.{axis.state.value}")
    return (
        f'<tr data-axis="{escape(axis.axis.value, quote=True)}" data-axis-state="{escape(axis.state.value, quote=True)}">'
        f'<th scope="row">{_axis_label(axis.axis, translator)} '
        f'<span class="comparison-axis-machine" translate="no">{escape(axis.axis.value)}</span></th>'
        f'<td><span class="comparison-axis-state" data-axis-state="{escape(axis.state.value, quote=True)}">{escape(state_label)}</span></td>'
        f'<td data-axis-availability="{axis.availability_status.value}"><span translate="no">{axis.availability_status.value}</span></td>'
        f'<td>{_owner(axis.left_value, translator)}</td><td>{_owner(axis.right_value, translator)}</td>'
        f'<td>{_reason(axis, translator)}</td><td>{_render_sources(axis.source_refs, context=context, translator=translator)}</td></tr>'
    )


def _render_expert(view: ComparisonReaderViewModel, projection: ReaderProjection, *, context: QueryContext, translator: Translator) -> str:
    comparison = view.comparison
    if comparison is None:
        return f'<section class="comparison-reader-expert"><h2>{escape(translator.t("reader.comparison.expert_heading"))}</h2><p>{escape(translator.t("reader.comparison.no_comparison"))}</p></section>'
    rows = "".join(
        f'<tr data-expert-axis="{axis.axis.value}"><th scope="row">{_axis_label(axis.axis, translator)} '
        f'<span class="comparison-axis-machine" translate="no">{axis.axis.value}</span></th>'
        f'<td data-expert-state="{axis.state.value}">{escape(translator.t(f"reader.comparison.{axis.state.value}"))}</td>'
        f'<td data-expert-availability="{axis.availability_status.value}"><span translate="no">{axis.availability_status.value}</span></td>'
        f'<td>{_owner(axis.left_value, translator)}</td><td>{_owner(axis.right_value, translator)}</td>'
        f'<td><code translate="no">{escape(projection.derivation.rule or "")}</code></td>'
        f'<td>{_render_sources(axis.source_refs, context=context, translator=translator)}</td></tr>'
        for axis in comparison.axes
    )
    return (
        f'<section class="comparison-reader-expert"><h2>{escape(translator.t("reader.comparison.expert_heading"))}</h2>'
        f'{_comparison_reason(comparison, translator)}'
        f'<table><thead><tr><th>{escape(translator.t("reader.comparison.axis"))}</th><th>{escape(translator.t("reader.comparison.state"))}</th>'
        f'<th>{escape(translator.t("reader.comparison.availability"))}</th>'
        f'<th>{escape(translator.t("reader.comparison.left"))}</th><th>{escape(translator.t("reader.comparison.right"))}</th>'
        f'<th>{escape(translator.t("reader.derivation"))}</th><th>{escape(translator.t("reader.comparison.sources"))}</th></tr></thead><tbody>{rows}</tbody></table></section>'
    )


def _render_raw(projection: ReaderProjection, *, translator: Translator) -> str:
    raw = projection.raw_source.raw_bytes.decode("utf-8")
    return (
        f'<section class="comparison-reader-raw"><h2>{escape(translator.t("reader.comparison.raw_heading"))}</h2>'
        f'<pre translate="no" data-v0-schema="manager-gui.manager-read-model.v0">{translator.source_text(raw)}</pre>'
        f'<p data-raw-sha256="{escape(projection.raw_source.sha256, quote=True)}" translate="no">{projection.raw_source.sha256}</p></section>'
    )


def _render_related_links(view: ComparisonReaderViewModel, *, context: QueryContext, translator: Translator) -> str:
    comparison = view.comparison
    left_id = None if comparison is None else comparison.left_object_id
    right_id = None if comparison is None else comparison.right_object_id
    links: list[str] = []
    if left_id is not None:
        links.append(
            f'<a class="comparison-left-object-link" href="{escape(context_link(context, view=ViewId.STRATEGIES, genome_id=left_id), quote=True)}">'
            f'{escape(translator.t("reader.comparison.object_reader"))} {_machine(left_id)}</a>'
        )
    if right_id is not None:
        links.append(
            f'<a class="comparison-right-object-link" href="{escape(context_link(context, view=ViewId.STRATEGIES, genome_id=right_id), quote=True)}">'
            f'{escape(translator.t("reader.comparison.object_reader"))} {_machine(right_id)}</a>'
        )
    # Keep the published R3 class hooks discoverable while the Reader uses its
    # more general object-link names.
    if left_id is not None:
        links.append(
            f'<a class="comparison-left-genome-link" aria-label="{escape(translator.t("reader.comparison.object_reader"), quote=True)}" hidden href="{escape(context_link(context, view=ViewId.STRATEGIES, genome_id=left_id), quote=True)}"></a>'
            f'<a class="comparison-left-conditions-link" aria-label="{escape(translator.t("reader.comparison.object_reader"), quote=True)}" hidden href="{escape(context_link(context, view=ViewId.CONDITIONS, genome_id=left_id), quote=True)}"></a>'
        )
    if right_id is not None:
        links.append(
            f'<a class="comparison-right-genome-link" aria-label="{escape(translator.t("reader.comparison.object_reader"), quote=True)}" hidden href="{escape(context_link(context, view=ViewId.STRATEGIES, genome_id=right_id), quote=True)}"></a>'
            f'<a class="comparison-right-conditions-link" aria-label="{escape(translator.t("reader.comparison.object_reader"), quote=True)}" hidden href="{escape(context_link(context, view=ViewId.CONDITIONS, genome_id=right_id), quote=True)}"></a>'
        )
    links.extend(
        (
            f'<a class="comparison-evidence-link" href="{escape(context_link(context, view=ViewId.EVIDENCE), quote=True)}">{escape(translator.t("reader.comparison.evidence"))}</a>',
            f'<a class="comparison-lineage-link" href="{escape(context_link(context, view=ViewId.LINEAGE), quote=True)}">{escape(translator.t("reader.comparison.lineage"))}</a>',
        )
    )
    return f'<nav class="comparison-reader-related" aria-label="{escape(translator.t("reader.comparison.related"), quote=True)}">{"".join(links)}</nav>'


def render_comparison_reader(
    view_or_model: ComparisonReaderViewModel | ManagerReadModel,
    *,
    query_context: QueryContext = None,
    translator: Translator | None = None,
    projection: ReaderProjection | None = None,
    mode: ProjectionMode | str | None = None,
    integration_hook: str | None = None,
) -> str:
    """Render Comparison Reader, Expert, or Raw without changing the v0 model."""

    selected = translator or Translator()
    view = view_or_model if isinstance(view_or_model, ComparisonReaderViewModel) else ComparisonReaderViewModel.from_read_model(view_or_model)
    reader_projection = projection or project_comparison_reader(view.read_model)
    state = ReaderURLState.from_url(query_context) if isinstance(query_context, str) else ReaderURLState(pairs=tuple((str(k), str(v)) for k, v in (query_context or {}).items() if v is not None))
    selected_mode = ProjectionMode(mode) if mode is not None else state.mode
    # The shell owns the single global mode switch; the page body only honors its state.
    result = view.result.value if view.result is not None else "missing"
    selected_integration_hook = integration_hook or COMPARISON_READER_INTEGRATION_HOOK
    body: str
    if selected_mode is ProjectionMode.RAW:
        body = _render_raw(reader_projection, translator=selected)
    elif selected_mode is ProjectionMode.EXPERT:
        body = _render_expert(view, reader_projection, context=query_context, translator=selected)
    else:
        surface = render_reader_surface(reader_projection, page=ReaderPage.COMPARISON, query_context=query_context, translator=selected)
        if view.comparison is None:
            table = f'<section class="comparison-reader-empty"><h2>{escape(selected.t("reader.comparison.no_comparison"))}</h2></section>'
        else:
            comparison = view.comparison
            table = (
                f'<section class="comparison-reader-axes" aria-labelledby="comparison-reader-axes-title">'
                f'<h2 id="comparison-reader-axes-title">{escape(selected.t("reader.comparison.axis"))}</h2>'
                f'{_comparison_reason(comparison, selected)}'
                f'<table><caption>{escape(selected.t("reader.comparison.question"))}</caption><thead><tr>'
                f'<th>{escape(selected.t("reader.comparison.axis"))}</th><th>{escape(selected.t("reader.comparison.state"))}</th>'
                f'<th>{escape(selected.t("reader.comparison.availability"))}</th>'
                f'<th>{escape(selected.t("reader.comparison.left"))}</th><th>{escape(selected.t("reader.comparison.right"))}</th>'
                f'<th>{escape(selected.t("reader.comparison.reason"))}</th><th>{escape(selected.t("reader.comparison.sources"))}</th>'
                f'</tr></thead><tbody>{"".join(_render_axis(axis, context=query_context, translator=selected) for axis in comparison.axes)}</tbody></table>'
                f'<p class="comparison-reader-boundary" data-statistics="not-generated">{escape(selected.t("reader.comparison.no_statistics"))}</p>'
                f'</section>'
            )
        body = surface + table
    status = render_status_block(view.read_model, translator=selected)
    refusal = (
        f'<p class="comparison-reader-refusal" data-comparison-refusal="true">{escape(selected.t("reader.comparison.refused"))}</p>'
        if view.comparison is not None and view.comparison.refused
        else ""
    )
    legacy_result = "incomparable" if result == ComparisonReaderOutcome.NOT_COMPARABLE.value else result
    legacy_axes = (
        f'<span class="comparison-v0-compat" hidden>{escape(selected.t("comparison.incompatible_axes"))}</span>'
        if result == ComparisonReaderOutcome.NOT_COMPARABLE.value
        else ""
    )
    legacy_label = (
        f'<span class="comparison-v0-compat" hidden>{escape(selected.t("label.comparison_result.incomparable"))}</span>'
        if result == ComparisonReaderOutcome.NOT_COMPARABLE.value
        else ""
    )
    legacy_status = (
        '<span class="comparison-v0-compat" data-status="incomparable" '
        'data-display-state="error" hidden></span>'
        if result == ComparisonReaderOutcome.NOT_COMPARABLE.value
        else ""
    )
    legacy_marker = f'{legacy_status}<span class="comparison-v0-compat" data-comparison-result="{escape(legacy_result, quote=True)}" hidden></span>{legacy_label}{legacy_axes}'
    return (
        f'<section class="comparison-reader-page" data-reader-hook="{COMPARISON_READER_HOOK}" '
        f'data-integration-hook="{selected_integration_hook}" data-reader-mode="{selected_mode.value}" '
        f'data-status="{escape(view.read_model.availability.status.value, quote=True)}" '
        f'data-display-state="{display_state_for(view.read_model).value}" '
        f'data-comparison-result="{escape(result, quote=True)}">{legacy_marker}'
        f'<p class="eyebrow">{escape(selected.t("comparison.eyebrow"))}</p>'
        f'<h1 data-page-title tabindex="-1">{escape(selected.t("reader.comparison.title"))}</h1>'
        f'{status}{refusal}{body}{_render_related_links(view, context=query_context, translator=selected)}'
        f'</section>'
    )


def comparison_reader_view(provider: ManagerDataProvider, *, snapshot_token: str | None = None) -> ComparisonReaderViewModel:
    return ComparisonReaderViewModel.from_read_model(provider.read(COMPARISON_READER_RESOURCE, snapshot_token=snapshot_token))


def render_comparison_reader_view(
    provider_or_model: ManagerDataProvider | ManagerReadModel,
    *,
    query_context: QueryContext = None,
    snapshot_token: str | None = None,
    translator: Translator | None = None,
    projection: ReaderProjection | None = None,
) -> str:
    view = (
        ComparisonReaderViewModel.from_read_model(provider_or_model)
        if isinstance(provider_or_model, ManagerReadModel)
        else comparison_reader_view(provider_or_model, snapshot_token=snapshot_token)
    )
    return render_comparison_reader(view, query_context=query_context, translator=translator, projection=projection)


render_reader_comparison = render_comparison_reader
render_comparison_reader_page = render_comparison_reader_view


# ----------------------------- deterministic fixtures -------------------------


def _fixture_source(source_id: str, locator: str, revision: str = "fixture-v0") -> SourceReference:
    return SourceReference(
        source_id=source_id,
        owner="manager-gui-comparison-reader-fixture",
        kind="published-comparison-record",
        locator=locator,
        schema="manager-gui.comparison-reader.fixture.v0",
        revision=revision,
    )


def _fixture_axes() -> dict[str, object]:
    return {
        "identity": "strategy-family-fixture",
        "eligibility": {"eligible": True, "protocol": "protocol-v1"},
        "source_generation": "generation-v1",
        "snapshot": "snapshot-v1",
        "data_version": {"dataset": "prices-2026-09", "adjustment": "split"},
        "universe": {"members": ["AAA", "BBB"]},
        "time_range": {"start": "2020-01-01", "end": "2024-12-31", "timezone": "UTC"},
        "protocol": {"id": "protocol-v1", "version": "1"},
        "randomness": {"seed": 7, "policy": "frozen"},
        "costs": {"commission_bps": 5, "slippage_bps": 2},
        "fills": {"policy": "published-fills-v1"},
        "metric_definition": {"return": "time_weighted"},
        "evidence_sections": ["conclusion", "protocol", "limitations"],
        "currency": {"base": "USD"},
    }


def build_comparison_reader_fixture(state: ComparisonReaderFixtureState | str = ComparisonReaderFixtureState.EQUAL) -> ManagerReadModel:
    selected = ComparisonReaderFixtureState(state)
    left_source = _fixture_source("comparison-reader-left", "fixture://manager-gui/comparison-reader/left")
    right_source = _fixture_source("comparison-reader-right", "fixture://manager-gui/comparison-reader/right", "fixture-v1")
    sources = (left_source, right_source)
    if selected in {
        ComparisonReaderFixtureState.BLOCKED,
        ComparisonReaderFixtureState.STALE,
        ComparisonReaderFixtureState.INTEGRITY_FAILURE,
        ComparisonReaderFixtureState.API_UNAVAILABLE,
    }:
        status, reason = {
            ComparisonReaderFixtureState.BLOCKED: (ReadModelStatus.BLOCKED, "The comparison read seam is blocked."),
            ComparisonReaderFixtureState.STALE: (ReadModelStatus.STALE, "The comparison source is stale."),
            ComparisonReaderFixtureState.INTEGRITY_FAILURE: (ReadModelStatus.INTEGRITY_FAILURE, "The comparison artifact failed integrity validation."),
            ComparisonReaderFixtureState.API_UNAVAILABLE: (ReadModelStatus.API_UNAVAILABLE, "The comparison API is unavailable."),
        }[selected]
        return ManagerReadModel(
            data={},
            source_refs=sources,
            as_of=None if status in {ReadModelStatus.BLOCKED, ReadModelStatus.API_UNAVAILABLE} else "2026-10-03T13:00:00Z",
            snapshot_token=f"comparison-reader-{selected.value}-v0",
            derivation=Derivation("direct", inputs=tuple(ref.source_id for ref in sources), version="v0"),
            availability=Availability(status, False, reason, status is ReadModelStatus.API_UNAVAILABLE),
            errors=(ReadModelError(f"comparison_reader_{selected.value}", reason),),
        )
    left_axes = _fixture_axes()
    right_axes = dict(left_axes)
    if selected is ComparisonReaderFixtureState.DIFFERENT:
        right_axes["costs"] = {"commission_bps": 8, "slippage_bps": 2}
    elif selected is ComparisonReaderFixtureState.MISSING:
        right_axes.pop("currency")
    elif selected in {ComparisonReaderFixtureState.NOT_COMPARABLE, ComparisonReaderFixtureState.INCOMPARABLE}:
        right_axes["snapshot"] = "snapshot-v2"
    payload = {
        "comparison": {
            "left": {"object_type": "strategy", "object_id": "strategy-left", "axes": left_axes, "source_refs": [left_source.source_id]},
            "right": {"object_type": "strategy", "object_id": "strategy-right", "axes": right_axes, "source_refs": [right_source.source_id]},
            "source_refs": [left_source.source_id, right_source.source_id],
            "owner_summary": "Owner comparison note <keep exactly>",
        }
    }
    return ManagerReadModel(
        data=cast(JSONValue, payload),
        source_refs=sources,
        as_of="2026-10-03T13:00:00Z",
        snapshot_token=f"comparison-reader-{selected.value}-v0",
        derivation=Derivation("derived", COMPARISON_READER_RULE, tuple(ref.source_id for ref in sources), COMPARISON_READER_VERSION),
        availability=Availability(ReadModelStatus.DERIVED, True, "Comparison Reader fixture."),
    )


@dataclass(frozen=True, slots=True)
class ComparisonReaderFixtureProvider:
    state: ComparisonReaderFixtureState

    def __init__(self, state: ComparisonReaderFixtureState | str = ComparisonReaderFixtureState.EQUAL) -> None:
        object.__setattr__(self, "state", ComparisonReaderFixtureState(state))

    def read(self, resource: str = COMPARISON_READER_RESOURCE, *, snapshot_token: str | None = None) -> ManagerReadModel:
        del snapshot_token
        if resource not in COMPARISON_READER_RESOURCES:
            raise ValueError(f"comparison reader fixture does not serve resource {resource!r}")
        return build_comparison_reader_fixture(self.state)


def comparison_reader_fixture_provider(state: ComparisonReaderFixtureState | str = ComparisonReaderFixtureState.EQUAL) -> ComparisonReaderFixtureProvider:
    return ComparisonReaderFixtureProvider(state)


build_comparison_fixture = build_comparison_reader_fixture
comparison_fixture_provider = comparison_reader_fixture_provider

__all__ = [
    "COMPARISON_GATE_AXES",
    "COMPARISON_READER_AXES",
    "COMPARISON_READER_FIXTURE_STATES",
    "COMPARISON_READER_HOOK",
    "COMPARISON_READER_INTEGRATION_HOOK",
    "COMPARISON_READER_INTEGRATION_HOOK_PATH",
    "COMPARISON_READER_RESOURCE",
    "COMPARISON_READER_RESOURCES",
    "COMPARISON_READER_ROUTE",
    "COMPARISON_READER_RULE",
    "COMPARISON_READER_VERSION",
    "NOT_RECORDED",
    "OBJECT_COMPARISON_AXES",
    "AxisComparisonState",
    "ComparisonAxis",
    "ComparisonAxisResult",
    "ComparisonAxisState",
    "ComparisonFixtureState",
    "ComparisonOutcome",
    "ComparisonReaderAxis",
    "ComparisonReaderAxisResult",
    "ComparisonReaderAxisState",
    "ComparisonReaderComparison",
    "ComparisonReaderFixtureProvider",
    "ComparisonReaderFixtureState",
    "ComparisonReaderOutcome",
    "ComparisonReaderView",
    "ComparisonReaderViewModel",
    "ComparisonResult",
    "ComparisonStatus",
    "ComparisonViewModel",
    "ObjectComparison",
    "ObjectComparisonViewModel",
    "build_comparison_fixture",
    "build_comparison_reader_fixture",
    "compare_comparison_reader",
    "compare_objects",
    "compare_reader_objects",
    "comparison_fixture_provider",
    "comparison_reader_fixture_provider",
    "comparison_reader_view",
    "project_comparison",
    "project_comparison_reader",
    "project_reader_comparison",
    "render_comparison_reader",
    "render_comparison_reader_page",
    "render_comparison_reader_view",
    "render_reader_comparison",
]
