"""Read-only Derived success/failure grouping for Manager GUI S4-T3.

A grouping is an explicitly named, reproducible projection over public records.
It is kept visibly ``Derived`` and is never promoted to owner Memory, Evidence,
or a success/failure fact.  This module does not recalculate metrics, inspect
private storage, infer a denominator, or expose mutation operations.
"""

# HTML fragments intentionally keep readable markup even when a line is long.
# ruff: noqa: E501

from __future__ import annotations

import hashlib
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
from .i18n import Translator
from .locators import public_locator
from .memory import memory_source_link, render_memory_text, render_memory_value
from .status import render_operational_state, render_status_block

FAILURE_GROUPING_RESOURCE = "failure_grouping"
FAILURE_GROUPING_ROUTE = "derived-failure-grouping"
FAILURE_GROUPING_INTEGRATION_HOOK = "failure-grouping-view"
FAILURE_GROUPING_INTEGRATION_HOOK_PATH = (
    "manager_gui.web.failure_grouping.render_failure_grouping_view"
)
NOT_RECORDED = "not recorded"

QueryContext: TypeAlias = str | Mapping[str, object] | None
JSONMapping: TypeAlias = Mapping[str, JSONValue]


class GroupOutcome(StrEnum):
    """Outcome bucket for a derived group, not an owner adjudication."""

    SUCCESS = "success"
    FAILURE = "failure"


class GroupingFixtureState(StrEnum):
    """Fixture states for complete, absent, and fail-closed grouping reads."""

    COMPLETE = "complete"
    SUCCESS_ONLY = "success_only"
    FAILURE_ONLY = "failure_only"
    PARTIAL = "partial"
    MISSING = "missing"
    STALE = "stale"
    BLOCKED = "blocked"
    INCOMPARABLE = "incomparable"
    INTEGRITY_FAILURE = "integrity_failure"
    API_UNAVAILABLE = "api_unavailable"


FailureGroupingFixtureState = GroupingFixtureState
DERIVED_GROUPING_FIXTURE_STATES: tuple[str, ...] = tuple(
    state.value for state in GroupingFixtureState
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


def _first(item: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        if (value := _text(item.get(key))) is not None:
            return value
    return None


def _normalise(value: object) -> str:
    return (_text(value) or "").strip().lower().replace("-", "_").replace(" ", "_")


def _json_value(value: object) -> JSONValue | None:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        return None
    return cast(JSONValue, value)


def _compact(value: object) -> str | None:
    if isinstance(value, Mapping):
        parts = [f"{key}={_compact(raw) or str(raw)}" for key, raw in value.items()]
        return ", ".join(parts) if parts else None
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        parts = [_compact(raw) or str(raw) for raw in value]
        return ", ".join(parts) if parts else None
    return _text(value)


def _scope(value: object) -> tuple[str, ...]:
    if isinstance(value, str) and value.strip():
        return (value.strip(),)
    if isinstance(value, Mapping):
        return (compact,) if (compact := _compact(value)) else ()
    return tuple(compact for raw in _sequence(value) if (compact := _compact(raw)) is not None)


def _source_refs(
    item: Mapping[str, object], source_index: Mapping[str, SourceReference]
) -> tuple[GroupingSourceRef, ...]:
    values: list[object] = []
    for key in ("source_ref", "source_id", "source_refs", "source_ids", "sources"):
        if key not in item:
            continue
        value = item[key]
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            values.extend(value)
        else:
            values.append(value)
    refs: list[GroupingSourceRef] = []
    seen: set[tuple[str, str | None]] = set()
    for raw in values:
        nested = _mapping(raw)
        source_id = (
            _first(nested, "source_id", "sourceId", "id", "record_id", "ref")
            if nested is not None
            else _text(raw)
        )
        if source_id is None:
            continue
        source = source_index.get(source_id)
        locator = (
            _first(nested, "locator", "href", "url", "uri") if nested is not None else None
        ) or (source.locator if source is not None else None)
        marker = (source_id, locator)
        if marker in seen:
            continue
        seen.add(marker)
        refs.append(
            GroupingSourceRef(
                source_id=source_id,
                locator=locator,
                owner=None if source is None else source.owner,
                schema=None if source is None else source.schema,
                revision=None if source is None else source.revision,
            )
        )
    return tuple(refs)


@dataclass(frozen=True, slots=True)
class GroupingSourceRef:
    """A source pointer retained on a group or participant."""

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
class GroupingParticipant:
    """One explicitly participating record in a derived grouping."""

    record_id: str
    label: str | None = None
    outcome: str | None = None
    source_refs: tuple[GroupingSourceRef, ...] = ()
    raw: Mapping[str, object] = field(default_factory=dict, repr=False, compare=False)

    def to_dict(self) -> dict[str, object]:
        return {
            "record_id": self.record_id,
            "label": self.label,
            "outcome": self.outcome,
            "source_refs": [ref.to_dict() for ref in self.source_refs],
        }


@dataclass(frozen=True, slots=True)
class DerivedFailureGrouping:
    """A named Derived grouping with all reproducibility fields visible."""

    group_id: str
    title: str
    outcome: GroupOutcome | None
    rule: str | None
    input_scope: tuple[str, ...]
    sample_count: int | None
    participants: tuple[GroupingParticipant, ...]
    source_refs: tuple[GroupingSourceRef, ...]
    status: ReadModelStatus = ReadModelStatus.DERIVED
    reason: str | None = None
    raw: Mapping[str, object] = field(default_factory=dict, repr=False, compare=False)

    @property
    def derived(self) -> bool:
        return self.status is ReadModelStatus.DERIVED

    @property
    def participant_ids(self) -> tuple[str, ...]:
        return tuple(item.record_id for item in self.participants)

    @property
    def denominator(self) -> None:
        """Grouping never invents a denominator for a performance statistic."""

        return None

    def to_dict(self) -> dict[str, object]:
        return {
            "group_id": self.group_id,
            "title": self.title,
            "status": self.status.value,
            "outcome": None if self.outcome is None else self.outcome.value,
            "rule": self.rule,
            "input_scope": list(self.input_scope),
            "sample_count": self.sample_count,
            "participants": [item.to_dict() for item in self.participants],
            "participant_ids": list(self.participant_ids),
            "source_refs": [ref.to_dict() for ref in self.source_refs],
            "reason": self.reason,
        }


FailureGroup = DerivedFailureGrouping
DerivedGrouping = DerivedFailureGrouping


def _participant_id(item: Mapping[str, object], fallback: str) -> str:
    return _first(item, "record_id", "recordId", "participant_id", "id", "run_id", "failure_id") or fallback


def _participant_values(item: Mapping[str, object]) -> tuple[object, ...]:
    for key in ("participants", "members", "records", "failure_ids", "participant_ids", "inputs"):
        if key in item:
            value = item[key]
            if isinstance(value, Mapping):
                return tuple({"record_id": key, **(raw if isinstance(raw, Mapping) else {"value": raw})} for key, raw in value.items())
            return _sequence(value)
    return ()


def _participants(
    item: Mapping[str, object], source_index: Mapping[str, SourceReference]
) -> tuple[GroupingParticipant, ...]:
    result: list[GroupingParticipant] = []
    seen: set[str] = set()
    group_refs = _source_refs(item, source_index)
    for index, raw in enumerate(_participant_values(item)):
        nested = _mapping(raw)
        if nested is None:
            identifier = _text(raw)
            nested = {"record_id": identifier} if identifier else {}
        identifier = _participant_id(nested, f"participant-{index + 1}")
        if identifier in seen:
            continue
        seen.add(identifier)
        refs = _source_refs(nested, source_index) or group_refs
        result.append(
            GroupingParticipant(
                record_id=identifier,
                label=_first(nested, "label", "title", "name"),
                outcome=_first(nested, "outcome", "status", "state", "result"),
                source_refs=refs,
                raw=nested,
            )
        )
    return tuple(result)


def _sample_count(item: Mapping[str, object]) -> int | None:
    for key in ("sample_count", "sample_size", "count", "n_samples"):
        value = item.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int) and value >= 0:
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
    return None


def _outcome(value: object) -> GroupOutcome | None:
    token = _normalise(value)
    if token in {"success", "succeeded", "passed", "pass", "accepted", "qualified", "completed"}:
        return GroupOutcome.SUCCESS
    if token in {"failure", "failed", "failure_record", "rejected", "error", "execution_error"}:
        return GroupOutcome.FAILURE
    return None


def _group(
    item: Mapping[str, object],
    source_index: Mapping[str, SourceReference],
    model: ManagerReadModel,
    *,
    generated: bool = False,
) -> DerivedFailureGrouping | None:
    identifier = _first(item, "group_id", "groupId", "pattern_id", "record_id", "id", "key")
    if identifier is None:
        return None
    aggregation = _mapping(item.get("aggregation")) or _mapping(item.get("derivation")) or {}
    rule = _first(item, "rule", "grouping_rule", "aggregation_rule", "derivation_rule") or _first(
        aggregation, "rule", "grouping_rule", "aggregation_rule", "derivation_rule"
    )
    scope_value = item.get("input_scope", item.get("scope", item.get("source_scope")))
    if scope_value is None:
        scope_value = aggregation.get("input_scope", aggregation.get("scope"))
    scope = _scope(scope_value)
    if not scope and model.derivation.kind == "derived":
        scope = tuple(model.derivation.inputs)
    if rule is None and model.derivation.kind == "derived":
        rule = model.derivation.rule
    participants = _participants(item, source_index)
    sample_count = _sample_count(item)
    if generated and sample_count is None:
        sample_count = len(participants)
    raw_status = _normalise(item.get("status", item.get("state")))
    status = ReadModelStatus.DERIVED
    if raw_status in {"blocked", "stale", "incomparable", "missing", "integrity_failure", "api_unavailable"}:
        status = ReadModelStatus(raw_status)
    return DerivedFailureGrouping(
        group_id=identifier,
        title=_first(item, "title", "label", "name") or identifier,
        outcome=_outcome(item.get("outcome", item.get("group_outcome", item.get("result")))),
        rule=rule,
        input_scope=scope,
        sample_count=sample_count,
        participants=participants,
        source_refs=_source_refs(item, source_index),
        status=status,
        reason=_first(item, "reason", "message", "detail"),
        raw=item,
    )


def _group_items(root: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    values: list[Mapping[str, object]] = []
    for key in (
        "derived_groupings",
        "derived_groups",
        "failure_groupings",
        "success_failure_groupings",
        "groupings",
        "groups",
    ):
        values.extend(item for raw in _sequence(root.get(key)) if (item := _mapping(raw)) is not None)
    # A singular group is also a valid public read shape.
    singular = _mapping(root.get("grouping"))
    if singular is not None and any(key in singular for key in ("group_id", "rule", "participants", "members")):
        values.append(singular)
    result: list[Mapping[str, object]] = []
    seen: set[str] = set()
    for index, item in enumerate(values):
        identifier = _first(item, "group_id", "groupId", "pattern_id", "record_id", "id") or f"group-{index + 1}"
        if identifier not in seen:
            seen.add(identifier)
            result.append(item)
    return tuple(result)


def _records_for_derivation(root: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    values: list[Mapping[str, object]] = []
    for key in ("records", "participants", "failures", "successes", "runs"):
        values.extend(item for raw in _sequence(root.get(key)) if (item := _mapping(raw)) is not None)
    return tuple(values)


def _explicit_rule_and_scope(root: Mapping[str, object], model: ManagerReadModel) -> tuple[str | None, tuple[str, ...]]:
    container = _mapping(root.get("grouping")) or _mapping(root.get("aggregation")) or root
    rule = _first(container, "rule", "grouping_rule", "aggregation_rule", "derivation_rule")
    scope = _scope(container.get("input_scope", container.get("scope", container.get("source_scope"))))
    if not scope and model.derivation.kind == "derived":
        scope = tuple(model.derivation.inputs)
    if rule is None and model.derivation.kind == "derived":
        rule = model.derivation.rule
    return rule, scope


def _bucket(value: object) -> GroupOutcome | None:
    """Only explicit terminal outcomes enter a bucket; blocked/missing stay out."""

    token = _normalise(value)
    if token in {"success", "succeeded", "passed", "pass", "accepted", "qualified", "completed"}:
        return GroupOutcome.SUCCESS
    if token in {"failure", "failed", "rejected", "error", "execution_error", "failure_record"}:
        return GroupOutcome.FAILURE
    return None


def derive_success_failure_groupings(
    records: Sequence[Mapping[str, object]],
    *,
    rule: str,
    input_scope: Sequence[str],
    source_refs: Sequence[GroupingSourceRef] = (),
) -> tuple[DerivedFailureGrouping, ...]:
    """Derive deterministic outcome buckets from named public records.

    This is a structural grouping only.  Records with missing, blocked,
    incomparable, or not-evaluated outcomes are deliberately excluded rather
    than labelled as failures.
    """

    if not isinstance(rule, str) or not rule.strip():
        raise ValueError("rule must be a non-empty string")
    buckets: dict[GroupOutcome, list[GroupingParticipant]] = {
        GroupOutcome.SUCCESS: [],
        GroupOutcome.FAILURE: [],
    }
    for index, item in enumerate(records):
        outcome = _bucket(item.get("outcome", item.get("status", item.get("result"))))
        if outcome is None:
            continue
        identifier = _participant_id(item, f"participant-{index + 1}")
        refs = source_refs
        buckets[outcome].append(
            GroupingParticipant(
                record_id=identifier,
                label=_first(item, "label", "title", "name"),
                outcome=_first(item, "outcome", "status", "state", "result"),
                source_refs=tuple(refs),
                raw=item,
            )
        )
    groups: list[DerivedFailureGrouping] = []
    scope = tuple(value for value in input_scope if isinstance(value, str) and value.strip())
    for outcome in (GroupOutcome.SUCCESS, GroupOutcome.FAILURE):
        participants = tuple(buckets[outcome])
        if not participants:
            continue
        digest_input = json.dumps(
            {"outcome": outcome.value, "rule": rule, "scope": scope, "participants": [p.record_id for p in participants]},
            sort_keys=True,
        ).encode("utf-8")
        identifier = f"derived-{outcome.value}-{hashlib.sha256(digest_input).hexdigest()[:12]}"
        groups.append(
            DerivedFailureGrouping(
                group_id=identifier,
                title=f"Derived {outcome.value} records",
                outcome=outcome,
                rule=rule,
                input_scope=scope,
                sample_count=len(participants),
                participants=participants,
                source_refs=tuple(source_refs),
                status=ReadModelStatus.DERIVED,
                reason="Structural grouping of explicitly published terminal outcomes.",
            )
        )
    return tuple(groups)


@dataclass(frozen=True, slots=True)
class FailureGroupingViewModel:
    """Immutable read-model projection of explicit or named Derived groups."""

    read_model: ManagerReadModel
    groups: tuple[DerivedFailureGrouping, ...]
    explicit_payload: bool = False

    @classmethod
    def from_read_model(cls, model: ManagerReadModel) -> FailureGroupingViewModel:
        root = _mapping(model.data) or {}
        source_index = {source.source_id: source for source in model.source_refs}
        groups: list[DerivedFailureGrouping] = []
        explicit_items = _group_items(root)
        if model.availability.status not in {
            ReadModelStatus.BLOCKED,
            ReadModelStatus.STALE,
            ReadModelStatus.INTEGRITY_FAILURE,
            ReadModelStatus.API_UNAVAILABLE,
            ReadModelStatus.MISSING,
        }:
            for item in explicit_items:
                if (group := _group(item, source_index, model)) is not None:
                    groups.append(group)
            if not groups and not explicit_items:
                rule, scope = _explicit_rule_and_scope(root, model)
                if rule is not None:
                    source_refs = tuple(
                        GroupingSourceRef(source.source_id, source.locator, source.owner, source.schema, source.revision)
                        for source in model.source_refs
                    )
                    groups.extend(
                        derive_success_failure_groupings(
                            _records_for_derivation(root),
                            rule=rule,
                            input_scope=scope,
                            source_refs=source_refs,
                        )
                    )
        return cls(model, tuple(groups), explicit_payload=bool(explicit_items))

    @property
    def status(self) -> ReadModelStatus:
        return self.read_model.availability.status

    @property
    def source_refs(self) -> tuple[SourceReference, ...]:
        return self.read_model.source_refs

    @property
    def success_groups(self) -> tuple[DerivedFailureGrouping, ...]:
        return tuple(group for group in self.groups if group.outcome is GroupOutcome.SUCCESS)

    @property
    def failure_groups(self) -> tuple[DerivedFailureGrouping, ...]:
        return tuple(group for group in self.groups if group.outcome is GroupOutcome.FAILURE)

    @property
    def empty(self) -> bool:
        return not self.groups

    @property
    def raw_json(self) -> str:
        return self.read_model.to_json()

    def to_dict(self) -> dict[str, object]:
        return {
            "view": FAILURE_GROUPING_ROUTE,
            "explicit_payload": self.explicit_payload,
            "groups": [group.to_dict() for group in self.groups],
            "success_groups": [group.group_id for group in self.success_groups],
            "failure_groups": [group.group_id for group in self.failure_groups],
            "availability": self.read_model.availability.to_dict(),
            "source_refs": [source.to_dict() for source in self.read_model.source_refs],
            "as_of": self.read_model.as_of,
            "snapshot_token": self.read_model.snapshot_token,
        }


DerivedFailureGroupingViewModel = FailureGroupingViewModel
DerivedGroupingViewModel = FailureGroupingViewModel


_GROUP_FIXTURE_COPY = {
    "Published terminal successes": "group_success_title",
    "Published terminal failures": "group_failure_title",
    "bucket explicit terminal outcome by outcome and protocol": "group_rule",
    "Successful run 1": "success_run_1",
    "Successful run 2": "success_run_2",
    "Failed run 1": "failure_run_1",
    "Failed run 2": "failure_run_2",
}


def _group_text(value: str | None, translator: Translator, model: ManagerReadModel) -> str:
    fixture = bool(model.source_refs) and all(source.schema == "manager-gui.failure-grouping.fixture.v0" for source in model.source_refs) and (model.snapshot_token or "").startswith("failure-grouping-")
    if fixture and value in _GROUP_FIXTURE_COPY:
        return translator.html("l4.fixture." + _GROUP_FIXTURE_COPY[value])
    return render_memory_text(value, translator, missing="l4.none_recorded")


def _render_refs(refs: Sequence[GroupingSourceRef], *, translator: Translator, context: QueryContext) -> str:
    if not refs:
        return translator.html("l4.none_recorded")
    parts: list[str] = []
    for ref in refs:
        label = render_memory_value(ref.source_id, translator)
        if target := public_locator(ref.locator):
            target = memory_source_link(target, context)
            parts.append(f'<a class="grouping-source-link" href="{escape(target, quote=True)}">{label}</a>')
        else:
            parts.append(f'<span class="grouping-source-unconfirmed">{label} · {translator.html("l4.missing_source")}</span>')
    return " · ".join(parts)


def _render_group(group: DerivedFailureGrouping, *, translator: Translator, model: ManagerReadModel, context: QueryContext) -> str:
    participants = " · ".join(
        f'<span class="grouping-participant" data-participant-id="{escape(item.record_id, quote=True)}">{_group_text(item.label, translator, model) if item.label else render_memory_value(item.record_id, translator)}</span>'
        for item in group.participants
    ) or translator.html("l4.none_recorded")
    outcome = group.outcome.value if group.outcome is not None else NOT_RECORDED
    title = _group_text(group.title, translator, model)
    reason = _group_text(group.reason, translator, model)
    return (
        f'<article class="derived-failure-group" data-group-id="{escape(group.group_id, quote=True)}" data-group-outcome="{escape(outcome, quote=True)}" data-group-status="{group.status.value}">'
        f'<p class="eyebrow">{translator.html("l4.derived_group_boundary")}</p><h3>{title}</h3>'
        f'<p><strong>{translator.html("l4.status")}</strong> <span data-status="derived">{translator.label("group_status", "derived")}</span> · '
        f'<strong>{translator.html("l4.outcome_bucket")}</strong> {render_memory_value(group.outcome.value if group.outcome else None, translator, "group_outcome", missing="l4.none_recorded")}</p>'
        f'<dl class="grouping-facts"><div><dt>{translator.html("l4.rule")}</dt><dd>{_group_text(group.rule, translator, model)}</dd></div>'
        f'<div><dt>{translator.html("l4.input_scope")}</dt><dd>{translator.join(render_memory_value(value, translator) for value in group.input_scope) if group.input_scope else translator.html("l4.none_recorded")}</dd></div>'
        f'<div><dt>{translator.html("l4.sample_count")}</dt><dd>{group.sample_count if group.sample_count is not None else translator.html("l4.none_recorded")}</dd></div>'
        f'<div><dt>{translator.html("l4.source_refs")}</dt><dd>{_render_refs(group.source_refs, translator=translator, context=context)}</dd></div></dl>'
        f'<p><strong>{translator.html("l4.participating_records")}</strong> {participants}</p><p class="grouping-reason">{reason}</p></article>'
    )


def render_failure_grouping(
    view_or_model: FailureGroupingViewModel | ManagerReadModel,
    *,
    query_context: QueryContext = None,
    include_raw_json: bool = True,
    translator: Translator | None = None,
) -> str:
    """Render explicitly named Derived success/failure groups."""

    selected_translator = translator or Translator()
    view = (
        view_or_model
        if isinstance(view_or_model, FailureGroupingViewModel)
        else FailureGroupingViewModel.from_read_model(view_or_model)
    )
    model = view.read_model
    pieces = [
        f'<section class="failure-grouping-page" data-integration-hook="{FAILURE_GROUPING_INTEGRATION_HOOK}" '
        f'data-grouping-status="{model.availability.status.value}" data-grouping-empty="{"true" if view.empty else "false"}">',
        f'<p class="eyebrow">{selected_translator.html("l4.derived_grouping_eyebrow")}</p>',
        f'<h1 class="page-title" data-page-title tabindex="-1">{selected_translator.html("l4.derived_grouping_title")}</h1>',
        f'<p class="page-intro">{selected_translator.html("l4.derived_grouping_intro")}</p>',
        f'<p class="context-line grouping-context"><span><strong>{selected_translator.html("l4.observed")}</strong> {render_memory_value(model.as_of, selected_translator, missing="l4.unavailable")}</span>'
        f'<span><strong>{selected_translator.html("l4.snapshot")}</strong> {render_memory_value(model.snapshot_token, selected_translator, missing="l4.unavailable")}</span></p>',
        render_status_block(model, translator=selected_translator),
    ]
    if view.empty:
        state = "empty" if model.availability.status is ReadModelStatus.MISSING else "error"
        detail = selected_translator.html("l4.no_named_group") if state == "empty" else selected_translator.html("l4.grouping_not_determined", status=selected_translator.t("label.status." + model.availability.status.value))
        pieces.append(render_operational_state(state, translator=selected_translator))
        pieces.append(f'<p class="grouping-unavailable">{detail}</p>')
    else:
        pieces.append(
            '<section class="derived-grouping-boundary" data-statistics="not-generated">'
            f'<p>{selected_translator.html("l4.no_aggregate_stat")}</p></section>'
        )
        pieces.append(
            f'<section class="derived-groupings" data-grouping-state="ready"><h2>{selected_translator.html("l4.named_derived_groups")}</h2>'
            + "".join(_render_group(group, translator=selected_translator, model=model, context=query_context) for group in view.groups)
            + "</section>"
        )
    if include_raw_json:
        pieces.append(
            f'<details class="grouping-raw-json"><summary>{selected_translator.html("l4.raw_json")}</summary>'
            f'<pre translate="no">{selected_translator.source_text(view.raw_json)}</pre></details>'
        )
    pieces.append("</section>")
    return "".join(pieces)


def failure_grouping_view(
    provider: ManagerDataProvider, *, snapshot_token: str | None = None
) -> FailureGroupingViewModel:
    """Read the approved grouping resource once."""

    return FailureGroupingViewModel.from_read_model(
        provider.read(FAILURE_GROUPING_RESOURCE, snapshot_token=snapshot_token)
    )


def render_failure_grouping_view(
    provider_or_model: ManagerDataProvider | ManagerReadModel,
    *,
    snapshot_token: str | None = None,
    query_context: QueryContext = None,
    translator: Translator | None = None,
) -> str:
    """S4-T3 integration hook accepting a provider or cached envelope."""

    view = (
        FailureGroupingViewModel.from_read_model(provider_or_model)
        if isinstance(provider_or_model, ManagerReadModel)
        else failure_grouping_view(provider_or_model, snapshot_token=snapshot_token)
    )
    return render_failure_grouping(
        view, query_context=query_context, translator=translator
    )


render_derived_failure_grouping = render_failure_grouping
render_derived_failure_grouping_view = render_failure_grouping_view
render_failure_groups_view = render_failure_grouping_view


# ----------------------------- deterministic fixtures ------------------------


def _fixture_source(source_id: str, locator: str, revision: str = "fixture-v0") -> SourceReference:
    return SourceReference(
        source_id=source_id,
        owner="manager-gui-public-fixture",
        kind="published-grouping-record",
        locator=locator,
        schema="manager-gui.failure-grouping.fixture.v0",
        revision=revision,
    )


def _fixture_group(
    group_id: str,
    title: str,
    outcome: str,
    source_id: str,
    members: Sequence[tuple[str, str]],
) -> dict[str, object]:
    return {
        "group_id": group_id,
        "title": title,
        "outcome": outcome,
        "status": "derived",
        "rule": "bucket explicit terminal outcome by outcome and protocol",
        "input_scope": ["study-fixture-1", "runs:fixture-2026-Q3"],
        "sample_count": len(members),
        "participants": [
            {
                "record_id": record_id,
                "label": label,
                "outcome": outcome,
                "source_refs": [source_id],
            }
            for record_id, label in members
        ],
        "source_refs": [source_id],
    }


def build_failure_grouping_fixture(
    state: GroupingFixtureState | str = GroupingFixtureState.COMPLETE,
) -> ManagerReadModel:
    """Build deterministic grouping data and fail-closed source states."""

    selected = GroupingFixtureState(state)
    group_source = _fixture_source("grouping-fixture-source", "fixture://manager-gui/grouping")
    run_source = _fixture_source("grouping-fixture-runs", "fixture://manager-gui/runs")
    sources = (group_source, run_source)
    status = ReadModelStatus.DERIVED
    complete = True
    reason = "The fixture contains explicitly named Derived grouping records."
    errors: tuple[ReadModelError, ...] = ()
    as_of: str | None = "2026-10-03T13:30:00Z"
    snapshot: str | None = f"failure-grouping-{selected.value}-v0"
    success = _fixture_group(
        "group-success-fixture",
        "Published terminal successes",
        "success",
        run_source.source_id,
        (("run-success-1", "Successful run 1"), ("run-success-2", "Successful run 2")),
    )
    failure = _fixture_group(
        "group-failure-fixture",
        "Published terminal failures",
        "failure",
        run_source.source_id,
        (("run-failure-1", "Failed run 1"), ("run-failure-2", "Failed run 2")),
    )
    if selected is GroupingFixtureState.COMPLETE:
        data = {"derived_groupings": [success, failure]}
    elif selected is GroupingFixtureState.SUCCESS_ONLY:
        data = {"derived_groupings": [success]}
    elif selected is GroupingFixtureState.FAILURE_ONLY:
        data = {"derived_groupings": [failure]}
    elif selected is GroupingFixtureState.PARTIAL:
        data = {"derived_groupings": [success]}
        status, complete, reason = ReadModelStatus.KNOWN, False, "Only the success grouping is published in this scope."
        errors = (ReadModelError("grouping_scope_partial", reason, source_ref=group_source.source_id),)
    elif selected is GroupingFixtureState.MISSING:
        data = {}
        status, complete, reason, as_of, snapshot = ReadModelStatus.MISSING, False, "No Derived grouping is published in this scope.", None, None
    elif selected is GroupingFixtureState.STALE:
        data = {"derived_groupings": [success, failure]}
        status, complete, reason = ReadModelStatus.STALE, False, "The Derived grouping source is stale."
        errors = (ReadModelError("grouping_source_stale", reason),)
    elif selected is GroupingFixtureState.BLOCKED:
        data = {}
        status, complete, reason, as_of = ReadModelStatus.BLOCKED, False, "The approved grouping read seam is blocked.", None
        errors = (ReadModelError("grouping_read_blocked", reason),)
    elif selected is GroupingFixtureState.INCOMPARABLE:
        data = {}
        status, complete, reason = ReadModelStatus.INCOMPARABLE, False, "The grouping inputs are not compatible."
        errors = (ReadModelError("grouping_inputs_incomparable", reason),)
    elif selected is GroupingFixtureState.INTEGRITY_FAILURE:
        data = {}
        status, complete, reason = ReadModelStatus.INTEGRITY_FAILURE, False, "The grouping artifact failed integrity validation."
        errors = (ReadModelError("grouping_integrity_failure", reason),)
    else:
        data = {}
        status, complete, reason, as_of, snapshot = ReadModelStatus.API_UNAVAILABLE, False, "The approved public grouping API is unavailable.", None, None
        errors = (ReadModelError("grouping_api_unavailable", reason, retryable=True),)
    return ManagerReadModel(
        data=cast(JSONValue, data),
        source_refs=sources,
        as_of=as_of,
        snapshot_token=snapshot,
        derivation=Derivation(
            kind="derived" if status is ReadModelStatus.DERIVED else "direct",
            rule="manager-gui.failure-grouping.v0" if status is ReadModelStatus.DERIVED else None,
            inputs=tuple(source.source_id for source in sources),
            version="v0",
        ),
        availability=Availability(status=status, complete=complete, reason=reason, retryable=status is ReadModelStatus.API_UNAVAILABLE),
        errors=errors,
    )


@dataclass(frozen=True, slots=True)
class FailureGroupingFixtureProvider:
    """Read-only provider serving grouping fixtures."""

    state: GroupingFixtureState

    def __init__(self, state: GroupingFixtureState | str = GroupingFixtureState.COMPLETE) -> None:
        object.__setattr__(self, "state", GroupingFixtureState(state))

    def read(
        self,
        resource: str = FAILURE_GROUPING_RESOURCE,
        *,
        snapshot_token: str | None = None,
    ) -> ManagerReadModel:
        del snapshot_token
        if resource not in {
            FAILURE_GROUPING_RESOURCE,
            "derived_failure_grouping",
            "derived-failure-grouping",
            FAILURE_GROUPING_ROUTE,
        }:
            raise ValueError(f"grouping fixture does not serve resource {resource!r}")
        return build_failure_grouping_fixture(self.state)


def failure_grouping_fixture_provider(
    state: GroupingFixtureState | str = GroupingFixtureState.COMPLETE,
) -> FailureGroupingFixtureProvider:
    return FailureGroupingFixtureProvider(state)


build_derived_failure_grouping_fixture = build_failure_grouping_fixture
derived_failure_grouping_fixture_provider = failure_grouping_fixture_provider
fixture_failure_grouping_provider = failure_grouping_fixture_provider
FailureGroupingProvider = FailureGroupingFixtureProvider
FailureGroupingView = FailureGroupingViewModel
DerivedFailureGroupingView = FailureGroupingViewModel


__all__ = [
    "DERIVED_GROUPING_FIXTURE_STATES",
    "FAILURE_GROUPING_FIXTURE_STATES",
    "FAILURE_GROUPING_INTEGRATION_HOOK",
    "FAILURE_GROUPING_INTEGRATION_HOOK_PATH",
    "FAILURE_GROUPING_RESOURCE",
    "FAILURE_GROUPING_ROUTE",
    "DerivedFailureGrouping",
    "DerivedFailureGroupingView",
    "DerivedFailureGroupingViewModel",
    "DerivedGrouping",
    "DerivedGroupingViewModel",
    "FailureGroup",
    "FailureGroupingFixtureProvider",
    "FailureGroupingFixtureState",
    "FailureGroupingProvider",
    "FailureGroupingView",
    "FailureGroupingViewModel",
    "GroupOutcome",
    "GroupingFixtureState",
    "GroupingParticipant",
    "GroupingSourceRef",
    "build_derived_failure_grouping_fixture",
    "build_failure_grouping_fixture",
    "derive_success_failure_groupings",
    "derived_failure_grouping_fixture_provider",
    "failure_grouping_fixture_provider",
    "failure_grouping_view",
    "fixture_failure_grouping_provider",
    "render_derived_failure_grouping",
    "render_derived_failure_grouping_view",
    "render_failure_grouping",
    "render_failure_grouping_view",
    "render_failure_groups_view",
]

# Historical name retained as a discoverable constant alias.
FAILURE_GROUPING_FIXTURE_STATES = DERIVED_GROUPING_FIXTURE_STATES
