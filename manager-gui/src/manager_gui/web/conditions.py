"""Read-only Genome condition evidence and descriptor surface.

The page consumes only the public :class:`~manager_gui.models.ManagerReadModel`
envelope (or a ``ManagerDataProvider``).  It keeps evidence-backed
applicability and invalidation conditions separate from contextual regime or
behaviour descriptors.  A descriptor is never promoted to a condition, and an
absent condition record is rendered as ``not recorded`` rather than as a
conclusion.

The S2-T3 integration seam is :func:`render_genome_conditions_view`.
No function in this module reads private storage or exposes a write operation.
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
from .i18n.catalog import l3_genome as _l3_genome_catalog  # noqa: F401
from .status import render_status_block

CONDITIONS_RESOURCE = "genome_conditions"
CONDITIONS_ROUTE = "strategy-conditions"
CONDITIONS_INTEGRATION_HOOK = "strategy-genome-conditions-view"
CONDITIONS_INTEGRATION_HOOK_PATH = "manager_gui.web.conditions.render_genome_conditions_view"

NOT_RECORDED = "not recorded"

QueryContext: TypeAlias = str | Mapping[str, object] | None
JSONMapping: TypeAlias = Mapping[str, JSONValue]


class ConditionCategory(StrEnum):
    """The three intentionally disjoint condition/observation families."""

    APPLICABILITY = "applicability"
    INVALIDATION = "invalidation"
    DESCRIPTOR = "descriptor"


class ConditionOutcome(StrEnum):
    """An explicit source outcome; it is never inferred from a descriptor."""

    SUPPORTED = "supported"
    FAILED = "failed"
    NOT_EVALUATED = "not_evaluated"
    BLOCKED = "blocked"
    MISSING = "missing"
    STALE = "stale"
    INTEGRITY_FAILURE = "integrity_failure"
    INCOMPARABLE = "incomparable"


class EvidenceLevel(StrEnum):
    """Evidence labels admitted from an owner record."""

    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    NOT_RECORDED = "not_recorded"


class ConditionFixtureState(StrEnum):
    """Deterministic condition fixtures used by tests and local previews."""

    COMPLETE = "complete"
    SUPPORTED = "supported"
    FAILED = "failed"
    NOT_EVALUATED = "not_evaluated"
    PARTIAL = "partial"
    EMPTY = "empty"
    MISSING = "missing"
    BLOCKED = "blocked"
    STALE = "stale"
    INTEGRITY_FAILURE = "integrity_failure"
    INCOMPARABLE = "incomparable"
    API_UNAVAILABLE = "api_unavailable"


CONDITION_CATEGORIES: tuple[ConditionCategory, ...] = tuple(ConditionCategory)
CONDITION_OUTCOMES: tuple[ConditionOutcome, ...] = tuple(ConditionOutcome)
EVIDENCE_LEVELS: tuple[EvidenceLevel, ...] = tuple(EvidenceLevel)
CONDITION_FIXTURE_STATES: tuple[str, ...] = tuple(state.value for state in ConditionFixtureState)

_CATEGORY_ALIASES = {
    "applicability-condition": ConditionCategory.APPLICABILITY,
    "applicability_condition": ConditionCategory.APPLICABILITY,
    "applicable": ConditionCategory.APPLICABILITY,
    "failure": ConditionCategory.INVALIDATION,
    "failure-condition": ConditionCategory.INVALIDATION,
    "failure_condition": ConditionCategory.INVALIDATION,
    "invalidation-condition": ConditionCategory.INVALIDATION,
    "invalidation_condition": ConditionCategory.INVALIDATION,
    "invalidating": ConditionCategory.INVALIDATION,
    "observation": ConditionCategory.DESCRIPTOR,
    "regime": ConditionCategory.DESCRIPTOR,
    "regime-descriptor": ConditionCategory.DESCRIPTOR,
    "regime_descriptor": ConditionCategory.DESCRIPTOR,
    "behavior-descriptor": ConditionCategory.DESCRIPTOR,
    "behaviour-descriptor": ConditionCategory.DESCRIPTOR,
}
_OUTCOME_ALIASES = {
    "not-evaluated": ConditionOutcome.NOT_EVALUATED,
    "not evaluated": ConditionOutcome.NOT_EVALUATED,
    "failure": ConditionOutcome.FAILED,
    "invalid": ConditionOutcome.FAILED,
    "unavailable": ConditionOutcome.BLOCKED,
}
_EVIDENCE_ALIASES = {
    "weak": EvidenceLevel.LOW,
    "medium": EvidenceLevel.MODERATE,
    "strong": EvidenceLevel.HIGH,
    "high-confidence": EvidenceLevel.HIGH,
    "not-recorded": EvidenceLevel.NOT_RECORDED,
}


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


def _mapping(value: object) -> Mapping[str, object] | None:
    return cast(Mapping[str, object], value) if isinstance(value, Mapping) else None


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(value)
    if isinstance(value, Mapping):
        return (value,)
    return ()


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


def _first_text(item: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        value = _text(item.get(key))
        if value is not None:
            return value
    return None


def _normalise(value: object) -> str | None:
    text = _text(value)
    if text is None:
        return None
    return text.strip().lower().replace("_", "-").replace(" ", "-")


def _source_refs(
    item: Mapping[str, object], source_index: Mapping[str, SourceReference]
) -> tuple[ConditionSourceRef, ...]:
    values: list[object] = []
    for key in ("source_ref", "source_id", "sourceRef", "source_refs", "source_ids", "sources"):
        if key in item:
            values.extend(_sequence(item[key]))
    result: list[ConditionSourceRef] = []
    seen: set[tuple[str, str | None]] = set()
    for value in values:
        source_id: str | None
        direct: str | None
        if isinstance(value, str):
            source_id = value.strip()
            direct = None
        else:
            nested = _mapping(value)
            if nested is None:
                continue
            source_id = _first_text(nested, "source_id", "sourceId", "id", "record_id")
            direct = _first_text(nested, "locator", "href", "url", "uri")
        if not source_id:
            continue
        source = source_index.get(source_id)
        locator = direct or (source.locator if source else None)
        result_item = ConditionSourceRef(
            source_id=source_id,
            label=source_id if source is None else source.source_id,
            locator=locator,
            owner=None if source is None else source.owner,
            schema=None if source is None else source.schema,
            revision=None if source is None else source.revision,
        )
        marker = (source_id, locator)
        if marker not in seen:
            seen.add(marker)
            result.append(result_item)
    return tuple(result)


def _category(value: object) -> ConditionCategory | None:
    normalised = _normalise(value)
    if normalised is None:
        return None
    try:
        return ConditionCategory(normalised)
    except ValueError:
        return _CATEGORY_ALIASES.get(normalised)


def _outcome(value: object) -> ConditionOutcome | None:
    normalised = _normalise(value)
    if normalised is None:
        return None
    try:
        return ConditionOutcome(normalised.replace("-", "_"))
    except ValueError:
        return _OUTCOME_ALIASES.get(normalised)


def _evidence_level(value: object) -> EvidenceLevel:
    normalised = _normalise(value)
    if normalised is None:
        return EvidenceLevel.NOT_RECORDED
    try:
        return EvidenceLevel(normalised.replace("-", "_"))
    except ValueError:
        return _EVIDENCE_ALIASES.get(normalised, EvidenceLevel.NOT_RECORDED)


def _limitations(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    values: list[str] = []
    for entry in _sequence(value):
        text = _text(entry)
        if text:
            values.append(text)
    return tuple(dict.fromkeys(values))


@dataclass(frozen=True, slots=True)
class TimeRange:
    """Explicit condition evidence interval; missing endpoints remain missing."""

    start: str | None = None
    end: str | None = None
    label: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {"start": self.start, "end": self.end, "label": self.label}


@dataclass(frozen=True, slots=True)
class ConditionSourceRef:
    """A source pointer carried by a condition evidence card."""

    source_id: str
    label: str
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
            "label": self.label,
            "locator": self.locator,
            "owner": self.owner,
            "schema": self.schema,
            "revision": self.revision,
        }


@dataclass(frozen=True, slots=True)
class ConditionEvidence:
    """One explicit condition or descriptor, with no inferred conclusion."""

    category: ConditionCategory
    condition: str | None
    scope: JSONValue | None
    outcome: ConditionOutcome | None
    evidence_level: EvidenceLevel
    time_range: TimeRange
    data_version: str | None
    sample: JSONValue | None
    limitations: tuple[str, ...]
    source_refs: tuple[ConditionSourceRef, ...]
    record_id: str | None = None
    raw: JSONMapping = field(default_factory=dict, repr=False, compare=False)

    @property
    def is_descriptor(self) -> bool:
        return self.category is ConditionCategory.DESCRIPTOR

    @property
    def is_validated_condition(self) -> bool:
        return self.category in {
            ConditionCategory.APPLICABILITY,
            ConditionCategory.INVALIDATION,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "category": self.category.value,
            "condition": self.condition,
            "scope": self.scope,
            "outcome": None if self.outcome is None else self.outcome.value,
            "evidence_level": self.evidence_level.value,
            "time_range": self.time_range.to_dict(),
            "data_version": self.data_version,
            "sample": self.sample,
            "limitations": list(self.limitations),
            "source_refs": [source.to_dict() for source in self.source_refs],
            "record_id": self.record_id,
        }


ConditionRecord = ConditionEvidence
ConditionDescriptor = ConditionEvidence
ConditionKind = ConditionCategory
ConditionStatus = ConditionOutcome
EvidenceStrength = EvidenceLevel


def _time_range(item: Mapping[str, object]) -> TimeRange:
    nested = _mapping(item.get("time_range", item.get("timeRange")))
    if nested is None:
        nested = _mapping(item.get("period"))
    start = _first_text(item, "start", "start_at", "from", "since")
    end = _first_text(item, "end", "end_at", "to", "until")
    label = _first_text(item, "time_label", "range_label")
    if nested is not None:
        start = start or _first_text(nested, "start", "start_at", "from", "since")
        end = end or _first_text(nested, "end", "end_at", "to", "until")
        label = label or _first_text(nested, "label", "name", "period")
    direct = _text(item.get("time_range"))
    label = label or direct
    return TimeRange(start=start, end=end, label=label)


def _condition_text(item: Mapping[str, object], category: ConditionCategory) -> str | None:
    keys = (
        ("condition", "statement", "rule", "title", "name")
        if category is not ConditionCategory.DESCRIPTOR
        else ("descriptor", "observation", "description", "statement", "title", "name")
    )
    return _first_text(item, *keys)


def _record_category(item: Mapping[str, object], group: object = None) -> ConditionCategory | None:
    raw = _first_text(item, "category", "condition_type", "conditionType", "kind", "type")
    return _category(raw or group)


def _iter_items(data: object) -> tuple[tuple[object, object], ...]:
    """Yield only explicit groups; arbitrary mapping fields are not conditions."""

    container = _mapping(data)
    if container is None:
        if isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
            return tuple((None, value) for value in data)
        return ()
    if _record_category(container) is not None:
        return ((None, container),)
    pairs: list[tuple[object, object]] = []
    explicit_keys = {
        "conditions": None,
        "condition_evidence": None,
        "applicability_conditions": ConditionCategory.APPLICABILITY,
        "applicability": ConditionCategory.APPLICABILITY,
        "invalidation_conditions": ConditionCategory.INVALIDATION,
        "failure_conditions": ConditionCategory.INVALIDATION,
        "failures": ConditionCategory.INVALIDATION,
        "descriptors": ConditionCategory.DESCRIPTOR,
        "regime_descriptors": ConditionCategory.DESCRIPTOR,
        "regime_observations": ConditionCategory.DESCRIPTOR,
        "observations": ConditionCategory.DESCRIPTOR,
        "behavior_descriptors": ConditionCategory.DESCRIPTOR,
        "behaviour_descriptors": ConditionCategory.DESCRIPTOR,
    }
    for key, group in explicit_keys.items():
        if key in container:
            pairs.extend((group or key, entry) for entry in _sequence(container[key]))
    return tuple(pairs)


def _condition_payload(data: object) -> Mapping[str, object] | object:
    container = _mapping(data)
    if container is None:
        return data
    if any(key in container for key in ("conditions", "condition_evidence", "descriptors", "applicability_conditions", "invalidation_conditions")):
        return container
    for key in ("genome", "genome_record", "record", "detail", "selected", "data"):
        nested = _mapping(container.get(key))
        if nested is not None and any(
            field in nested
            for field in ("conditions", "condition_evidence", "descriptors", "applicability_conditions", "invalidation_conditions")
        ):
            return nested
    genomes = _sequence(container.get("genomes"))
    if len(genomes) == 1 and (nested := _mapping(genomes[0])) is not None:
        return nested
    return container


def _evidence_source_item(item: Mapping[str, object]) -> Mapping[str, object]:
    evidence = _mapping(item.get("evidence"))
    return evidence or item


def _evidence_level_value(item: Mapping[str, object]) -> object:
    direct = item.get("evidence_level", item.get("evidenceLevel"))
    if direct is not None:
        return direct
    evidence = _mapping(item.get("evidence"))
    if evidence is not None:
        return evidence.get("level", evidence.get("evidence_level"))
    return None


def _outcome_value(item: Mapping[str, object]) -> object:
    direct = item.get("outcome", item.get("result", item.get("status")))
    if direct is not None:
        return direct
    evidence = _mapping(item.get("evidence"))
    return None if evidence is None else evidence.get("outcome")


def _parse_evidence(
    value: object,
    group: object,
    source_index: Mapping[str, SourceReference],
) -> ConditionEvidence | None:
    item = _mapping(value)
    if item is None:
        return None
    category = _record_category(item, group)
    if category is None:
        # A generic ``conditions`` entry without an explicit category is not
        # safe to classify, so it cannot become a validated condition.
        return None
    raw_outcome = _outcome_value(item)
    raw_evidence = _evidence_level_value(item)
    refs = _source_refs(item, source_index)
    evidence_source = _mapping(item.get("evidence"))
    if not refs and evidence_source is not None:
        refs = _source_refs(evidence_source, source_index)
    return ConditionEvidence(
        category=category,
        condition=_condition_text(item, category),
        scope=_json_value(item.get("scope", item.get("universe"))),
        outcome=_outcome(raw_outcome),
        evidence_level=_evidence_level(raw_evidence),
        time_range=_time_range(item),
        data_version=_first_text(item, "data_version", "dataVersion", "dataset_version", "version"),
        sample=_json_value(item.get("sample", item.get("sample_size", item.get("population")))),
        limitations=_limitations(item.get("limitations", item.get("limitations_note", item.get("limits")))),
        source_refs=refs,
        record_id=_first_text(item, "record_id", "recordId", "id", "uid"),
        raw=_json_mapping(item),
    )


@dataclass(frozen=True, slots=True)
class ConditionViewModel:
    """Typed condition evidence split into two condition families and descriptors."""

    read_model: ManagerReadModel
    evidence: tuple[ConditionEvidence, ...]
    genome_id: str | None = None

    @classmethod
    def from_read_model(
        cls, model: ManagerReadModel, *, genome_id: str | None = None
    ) -> ConditionViewModel:
        source_index = {source.source_id: source for source in model.source_refs}
        payload = _mapping(_condition_payload(model.data)) or {}
        selected_genome = genome_id or _first_text(payload, "genome_id", "genomeId")
        parsed: list[ConditionEvidence] = []
        seen: set[tuple[str, str | None, str | None]] = set()
        for group, value in _iter_items(payload):
            record = _parse_evidence(value, group, source_index)
            if record is None:
                continue
            marker = (record.category.value, record.record_id, record.condition)
            if marker in seen:
                continue
            seen.add(marker)
            parsed.append(record)
        return cls(model, tuple(parsed), selected_genome)

    @property
    def conditions(self) -> tuple[ConditionEvidence, ...]:
        return tuple(item for item in self.evidence if item.is_validated_condition)

    @property
    def applicability(self) -> tuple[ConditionEvidence, ...]:
        return tuple(item for item in self.evidence if item.category is ConditionCategory.APPLICABILITY)

    @property
    def applicability_conditions(self) -> tuple[ConditionEvidence, ...]:
        return self.applicability

    @property
    def invalidation(self) -> tuple[ConditionEvidence, ...]:
        return tuple(item for item in self.evidence if item.category is ConditionCategory.INVALIDATION)

    @property
    def invalidation_conditions(self) -> tuple[ConditionEvidence, ...]:
        return self.invalidation

    @property
    def descriptors(self) -> tuple[ConditionEvidence, ...]:
        return tuple(item for item in self.evidence if item.category is ConditionCategory.DESCRIPTOR)

    @property
    def as_of(self) -> str | None:
        return self.read_model.as_of

    @property
    def snapshot_token(self) -> str | None:
        return self.read_model.snapshot_token

    def to_dict(self) -> dict[str, object]:
        return {
            "view": CONDITIONS_ROUTE,
            "genome_id": self.genome_id,
            "applicability_conditions": [item.to_dict() for item in self.applicability],
            "invalidation_conditions": [item.to_dict() for item in self.invalidation],
            "descriptors": [item.to_dict() for item in self.descriptors],
            "as_of": self.as_of,
            "snapshot_token": self.snapshot_token,
            "availability": self.read_model.availability.to_dict(),
        }


ConditionsViewModel = ConditionViewModel


def _query_pairs(context: QueryContext) -> list[tuple[str, str]]:
    if context is None:
        return []
    if isinstance(context, str):
        query = urlsplit(context).query if "?" in context or "://" in context else context.lstrip("?")
        return [(key, value) for key, value in parse_qsl(query, keep_blank_values=True) if key]
    pairs: list[tuple[str, str]] = []
    for key, value in context.items():
        if not isinstance(key, str) or not key:
            continue
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            pairs.extend((key, str(entry)) for entry in value)
        elif value is not None:
            pairs.append((key, str(value)))
    return pairs


def _stable_query(pairs: Sequence[tuple[str, str]]) -> str:
    order = {key: index for index, key in enumerate(("view", "genome_id", "category", "fixture", "panel", "q"))}
    values: dict[str, list[str]] = {}
    for key, value in pairs:
        if key not in values:
            values[key] = []
        if value not in values[key]:
            values[key].append(value)
    return urlencode([(key, value) for key in sorted(values, key=lambda k: (order.get(k, 99), k)) for value in values[key]])


def genome_conditions_link(
    genome_id: str | None = None,
    *,
    query_context: QueryContext = None,
    category: ConditionCategory | str | None = None,
    base_path: str = "/",
) -> str:
    """Build a stable condition URL while retaining unrelated shell context."""

    pairs = [(key, value) for key, value in _query_pairs(query_context) if key not in {"view", "genome_id", "category"}]
    pairs.append(("view", CONDITIONS_ROUTE))
    if genome_id is not None:
        pairs.append(("genome_id", genome_id))
    if category is not None:
        pairs.append(("category", ConditionCategory(category).value))
    query = _stable_query(pairs)
    parsed = urlsplit(base_path)
    existing = parsed.query
    full_query = f"{existing}&{query}" if existing and query else existing or query
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", full_query, parsed.fragment)) if full_query else base_path


condition_link = genome_conditions_link


def _display(value: object, translator: Translator) -> str:
    if value is None or value == "" or value == [] or value == {}:
        return translator.t("conditions.not_recorded")
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return translator.t("conditions.not_recorded")


def _render_sources(sources: Sequence[ConditionSourceRef], translator: Translator) -> str:
    if not sources:
        return f'<span class="condition-not-recorded">{escape(translator.t("conditions.not_recorded"))}</span>'
    parts: list[str] = []
    for source in sources:
        label = translator.source_text(source.label or source.source_id)
        if source.locator:
            parts.append(
                f'<a class="condition-source-link" data-source-id="{escape(source.source_id, quote=True)}" href="{escape(source.locator, quote=True)}" translate="no">{label}</a>'
            )
        else:
            parts.append(
                f'<span class="condition-source-unconfirmed" data-source-id="{escape(source.source_id, quote=True)}" translate="no">{label} — {escape(translator.t("conditions.locator_missing"))}</span>'
            )
    return " · ".join(parts)


def _render_related_links(genome_id: str | None, context: QueryContext, translator: Translator) -> str:
    """Keep condition evidence connected to Genome identity and comparison."""

    if genome_id is None:
        return ""
    from .comparison import genome_comparison_link
    from .genome import genome_link

    values = dict(_query_pairs(context))
    comparison_href = genome_comparison_link(
        values.get("left_genome_id") or genome_id,
        values.get("right_genome_id"),
        query_context=context,
    )
    genome_href = genome_link(genome_id, query_context=context)
    return (
        f'<nav class="conditions-related-links" aria-label="{escape(translator.t("conditions.related_aria"))}">'
        f'<a class="condition-genome-link" href="{escape(genome_href, quote=True)}">'
        f'{escape(translator.t("conditions.back_genome"))} <span translate="no">{translator.source_text(genome_id)}</span></a>'
        f'<a class="condition-comparison-link" href="{escape(comparison_href, quote=True)}">'
        f'{escape(translator.t("conditions.compare"))}</a></nav>'
    )


_FIXTURE_COPY_KEYS = {
    "liquidity threshold is met": "conditions.fixture_liquidity",
    "data quality gate fails": "conditions.fixture_quality",
    "high-volatility regime": "conditions.fixture_regime",
    "fixture study window": "conditions.fixture_window",
    "Synthetic fixture; no conclusion beyond the published record.": "conditions.fixture_limitation",
}


def _fixture_or_owner(value: object, translator: Translator) -> str:
    if isinstance(value, str) and value in _FIXTURE_COPY_KEYS:
        return translator.t(_FIXTURE_COPY_KEYS[value])
    if isinstance(value, tuple) and len(value) == 1 and value[0] in _FIXTURE_COPY_KEYS:
        return translator.t(_FIXTURE_COPY_KEYS[value[0]])
    return _display(value, translator)


def _render_card(record: ConditionEvidence, translator: Translator) -> str:
    outcome = record.outcome.value if record.outcome is not None else NOT_RECORDED
    rows = (
        ("condition", record.condition),
        ("scope", record.scope),
        ("outcome", outcome),
        ("evidence_level", record.evidence_level.value),
        ("time_range", record.time_range.label or record.time_range.to_dict()),
        ("data_version", record.data_version),
        ("sample", record.sample),
        ("limitations", record.limitations),
        ("source_refs", _render_sources(record.source_refs, translator)),
    )
    def render_value(key: str, value: object) -> str:
        if key == "source_refs":
            return str(value)
        if key == "outcome":
            return translator.t("conditions.not_recorded") if value == NOT_RECORDED else translator.label("condition_outcome", str(value))
        if key == "evidence_level":
            return translator.label("evidence_level", str(value))
        return f'<span translate="no">{translator.source_text(_fixture_or_owner(value, translator))}</span>'
    body = "".join(
        f'<div class="condition-field" data-field="{escape(key, quote=True)}"><dt>{translator.t("conditions." + key) if key != "source_refs" else escape(translator.t("conditions.source_refs"))}</dt><dd>{render_value(key, value)}</dd></div>'
        for key, value in rows
    )
    condition = translator.source_text(_fixture_or_owner(record.condition, translator)) if record.condition else translator.t("conditions.not_recorded")
    return (
        f'<article class="condition-card" data-category="{record.category.value}" '
        f'data-outcome="{escape(outcome, quote=True)}" data-record-id="{escape(record.record_id or "", quote=True)}">'
        f'<h3 translate="no">{condition}</h3><dl>{body}</dl></article>'
    )


def _render_group(
    title: str,
    category: ConditionCategory,
    records: Sequence[ConditionEvidence],
    translator: Translator,
) -> str:
    if not records:
        body = f'<p class="conditions-not-recorded" data-category="{category.value}">{escape(translator.t("conditions.not_recorded"))}</p>'
    else:
        body = "".join(_render_card(record, translator) for record in records)
    return (
        f'<section class="condition-group" data-condition-group="{category.value}" aria-label="{escape(title)}">'
        f'<h2>{escape(title)}</h2>{body}</section>'
    )


def render_genome_conditions(
    view_or_model: ConditionViewModel | ManagerReadModel,
    *,
    query_context: QueryContext = None,
    genome_id: str | None = None,
    translator: Translator | None = None,
) -> str:
    """Render the condition evidence fragment for S2-T3 to mount."""

    selected_translator = translator or Translator()
    view = (
        view_or_model
        if isinstance(view_or_model, ConditionViewModel)
        else ConditionViewModel.from_read_model(view_or_model, genome_id=genome_id)
    )
    if isinstance(view_or_model, ConditionViewModel) and genome_id is not None and genome_id != view.genome_id:
        view = ConditionViewModel.from_read_model(view.read_model, genome_id=genome_id)
    model = view.read_model
    source_text = ", ".join(source.source_id for source in model.source_refs) or selected_translator.t("conditions.not_recorded")
    context_href = genome_conditions_link(view.genome_id, query_context=query_context)
    descriptor_group = _render_group("", ConditionCategory.DESCRIPTOR, view.descriptors, selected_translator)
    descriptor_group = descriptor_group.replace(
        '<section class="condition-group" data-condition-group="descriptor" aria-label="">',
        '<div class="condition-descriptor-list">',
        1,
    ).replace("</section>", "</div>", 1)
    return "".join(
        (
            f'<section class="genome-conditions-page" data-integration-hook="{CONDITIONS_INTEGRATION_HOOK}" data-genome-id="{escape(view.genome_id or "", quote=True)}">',
            f'<p class="eyebrow">{escape(selected_translator.t("conditions.eyebrow"))}</p>',
            f'<h1 class="page-title" data-page-title tabindex="-1">{escape(selected_translator.t("conditions.title"))}</h1>',
            f'<p class="page-intro">{escape(selected_translator.t("conditions.intro"))}</p>',
            f'<p class="context-line condition-context"><span><strong>{escape(selected_translator.t("conditions.observed"))}</strong> <span translate="no">{escape(model.as_of or selected_translator.t("conditions.not_recorded"))}</span></span><span><strong>{escape(selected_translator.t("conditions.snapshot"))}</strong> <span translate="no">{escape(model.snapshot_token or selected_translator.t("conditions.not_recorded"))}</span></span><span><strong>{escape(selected_translator.t("conditions.sources"))}</strong> <span translate="no">{escape(source_text)}</span></span></p>',
            f'<a class="conditions-context-link" href="{escape(context_href, quote=True)}">{escape(selected_translator.t("conditions.stable_context"))}</a>',
            _render_related_links(view.genome_id, query_context, selected_translator),
            render_status_block(model, translator=selected_translator),
            _render_group(selected_translator.t("conditions.applicability_group"), ConditionCategory.APPLICABILITY, view.applicability, selected_translator),
            _render_group(selected_translator.t("conditions.invalidation_group"), ConditionCategory.INVALIDATION, view.invalidation, selected_translator),
            f'<section class="condition-group condition-descriptors" data-condition-group="descriptor" aria-label="{escape(selected_translator.t("conditions.descriptor_group"))}"><h2>{escape(selected_translator.t("conditions.descriptor_group"))}</h2><p>{escape(selected_translator.t("conditions.descriptor_intro"))}</p>',
            descriptor_group,
            '</section>',
            '</section>',
        )
    )


def condition_view(
    provider: ManagerDataProvider,
    *,
    snapshot_token: str | None = None,
    genome_id: str | None = None,
) -> ConditionViewModel:
    """Read ``genome_conditions`` exactly once through the public seam."""

    return ConditionViewModel.from_read_model(
        provider.read(CONDITIONS_RESOURCE, snapshot_token=snapshot_token), genome_id=genome_id
    )


def render_genome_conditions_view(
    provider_or_model: ManagerDataProvider | ManagerReadModel,
    *,
    query_context: QueryContext = None,
    snapshot_token: str | None = None,
    genome_id: str | None = None,
    translator: Translator | None = None,
) -> str:
    """S2-T3 hook accepting either a provider or an already-read envelope."""

    selected_id = genome_id or dict(_query_pairs(query_context)).get("genome_id")
    if isinstance(provider_or_model, ManagerReadModel):
        view = ConditionViewModel.from_read_model(provider_or_model, genome_id=selected_id)
    else:
        view = condition_view(provider_or_model, snapshot_token=snapshot_token, genome_id=selected_id)
    return render_genome_conditions(
        view,
        query_context=query_context,
        genome_id=selected_id,
        translator=translator,
    )


render_conditions_view = render_genome_conditions_view
render_genome_condition_view = render_genome_conditions_view


def _condition_source(source_id: str, locator: str) -> SourceReference:
    return SourceReference(
        source_id=source_id,
        owner="apex-research",
        kind="public-record",
        locator=locator,
        schema="manager-genome-conditions.fixture.v0",
        revision="fixture-v0",
    )


def _condition_record(
    category: str,
    condition: str,
    outcome: str,
    source_id: str,
    *,
    record_id: str,
) -> dict[str, object]:
    return {
        "category": category,
        "record_id": record_id,
        "condition": condition,
        "scope": {"universe": "cn-equity", "frequency": "1d"},
        "outcome": outcome,
        "evidence_level": "high",
        "time_range": {"start": "2024-01-01", "end": "2026-09-30", "label": "fixture study window"},
        "data_version": "market-data-v3",
        "sample": {"n": 1280, "unit": "signals"},
        "limitations": ["Synthetic fixture; no conclusion beyond the published record."],
        "source_refs": [source_id],
    }


def build_conditions_fixture(state: ConditionFixtureState | str) -> ManagerReadModel:
    """Build deterministic condition evidence fixtures without storage access."""

    selected = ConditionFixtureState(state)
    source = _condition_source("fixture-conditions-source", "fixture://manager-gui/genome-conditions")
    if selected in {ConditionFixtureState.EMPTY, ConditionFixtureState.MISSING}:
        return ManagerReadModel(
            data=cast(JSONValue, {"genome_id": "genome-fixture-1", "conditions": [], "descriptors": []}),
            source_refs=(source,),
            as_of="2026-10-03T10:00:00Z",
            snapshot_token=f"conditions-fixture-{selected.value}-v0",
            derivation=Derivation(kind="direct", inputs=(source.source_id,), version="v0"),
            availability=Availability(ReadModelStatus.MISSING, False, "Condition records are not recorded in this scope."),
        )
    if selected in {ConditionFixtureState.BLOCKED, ConditionFixtureState.STALE, ConditionFixtureState.INTEGRITY_FAILURE, ConditionFixtureState.API_UNAVAILABLE}:
        statuses = {
            ConditionFixtureState.BLOCKED: (ReadModelStatus.BLOCKED, "The approved condition evidence read seam is blocked.", "condition_read_blocked"),
            ConditionFixtureState.STALE: (ReadModelStatus.STALE, "The condition evidence source is stale.", "condition_source_stale"),
            ConditionFixtureState.INTEGRITY_FAILURE: (ReadModelStatus.INTEGRITY_FAILURE, "The condition evidence artifact failed integrity validation.", "condition_integrity_failure"),
            ConditionFixtureState.API_UNAVAILABLE: (ReadModelStatus.API_UNAVAILABLE, "The approved condition evidence API is unavailable.", "condition_api_unavailable"),
        }
        status, reason, code = statuses[selected]
        return ManagerReadModel(
            data=cast(JSONValue, {}),
            source_refs=(source,),
            as_of=None if selected in {ConditionFixtureState.BLOCKED, ConditionFixtureState.API_UNAVAILABLE} else "2025-01-01T00:00:00Z",
            snapshot_token=f"conditions-fixture-{selected.value}-v0",
            derivation=Derivation(kind="direct", inputs=(source.source_id,), version="v0"),
            availability=Availability(status, False, reason),
            errors=(ReadModelError(code, reason, source.source_id),),
        )
    outcome = {
        ConditionFixtureState.COMPLETE: "supported",
        ConditionFixtureState.SUPPORTED: "supported",
        ConditionFixtureState.FAILED: "failed",
        ConditionFixtureState.NOT_EVALUATED: "not_evaluated",
        ConditionFixtureState.PARTIAL: "supported",
        ConditionFixtureState.INCOMPARABLE: "incomparable",
    }[selected]
    payload = {
        "genome_id": "genome-fixture-1",
        "conditions": [
            _condition_record("applicability", "liquidity threshold is met", outcome, source.source_id, record_id="app-1"),
            _condition_record("invalidation", "data quality gate fails", "failed" if outcome == "supported" else outcome, source.source_id, record_id="inv-1"),
        ],
        "descriptors": [
            {"category": "descriptor", "record_id": "descriptor-1", "descriptor": "high-volatility regime", "scope": {"universe": "cn-equity"}, "data_version": "market-data-v3", "source_refs": [source.source_id]},
        ],
    }
    partial = selected is ConditionFixtureState.PARTIAL
    incomparable = selected is ConditionFixtureState.INCOMPARABLE
    return ManagerReadModel(
        data=cast(JSONValue, payload),
        source_refs=(source,),
        as_of="2026-10-03T10:00:00Z",
        snapshot_token=f"conditions-fixture-{selected.value}-v0",
        derivation=Derivation(kind="direct", inputs=(source.source_id,), version="v0"),
        availability=Availability(
            ReadModelStatus.INCOMPARABLE if incomparable else ReadModelStatus.KNOWN,
            not partial and not incomparable,
            "The condition evidence cannot be evaluated on compatible axes."
            if incomparable
            else "Condition evidence is only partially recorded in this scope."
            if partial
            else "Condition evidence fixture.",
        ),
        errors=(
            (
                ReadModelError(
                    "condition_axes_incomparable",
                    "The condition evidence cannot be evaluated on compatible axes.",
                    source.source_id,
                )
                if incomparable
                else ReadModelError(
                    "condition_scope_partial",
                    "Some condition evidence categories are outside the indexed scope.",
                    source.source_id,
                ),
            )
            if partial or incomparable
            else ()
        ),
    )


@dataclass(frozen=True, slots=True)
class ConditionsFixtureProvider:
    """Read-only provider for condition fixtures."""

    state: ConditionFixtureState

    def __init__(self, state: ConditionFixtureState | str) -> None:
        object.__setattr__(self, "state", ConditionFixtureState(state))

    def read(self, resource: str = CONDITIONS_RESOURCE, *, snapshot_token: str | None = None) -> ManagerReadModel:
        del snapshot_token
        if resource not in {CONDITIONS_RESOURCE, "conditions", CONDITIONS_ROUTE}:
            raise ValueError(f"unsupported condition resource: {resource!r}")
        return build_conditions_fixture(self.state)


def conditions_fixture_provider(state: ConditionFixtureState | str) -> ConditionsFixtureProvider:
    return ConditionsFixtureProvider(state)


build_genome_conditions_fixture = build_conditions_fixture
GenomeCondition = ConditionEvidence
GenomeConditionViewModel = ConditionViewModel
CONDITIONS_FIXTURE_STATES = CONDITION_FIXTURE_STATES

__all__ = [
    "CONDITIONS_FIXTURE_STATES",
    "CONDITIONS_INTEGRATION_HOOK",
    "CONDITIONS_INTEGRATION_HOOK_PATH",
    "CONDITIONS_RESOURCE",
    "CONDITIONS_ROUTE",
    "CONDITION_CATEGORIES",
    "CONDITION_FIXTURE_STATES",
    "CONDITION_OUTCOMES",
    "EVIDENCE_LEVELS",
    "NOT_RECORDED",
    "ConditionCategory",
    "ConditionDescriptor",
    "ConditionEvidence",
    "ConditionFixtureState",
    "ConditionKind",
    "ConditionOutcome",
    "ConditionRecord",
    "ConditionSourceRef",
    "ConditionStatus",
    "ConditionViewModel",
    "ConditionsFixtureProvider",
    "ConditionsViewModel",
    "EvidenceLevel",
    "EvidenceStrength",
    "GenomeCondition",
    "GenomeConditionViewModel",
    "TimeRange",
    "build_conditions_fixture",
    "build_genome_conditions_fixture",
    "condition_link",
    "condition_view",
    "conditions_fixture_provider",
    "genome_conditions_link",
    "render_conditions_view",
    "render_genome_condition_view",
    "render_genome_conditions",
    "render_genome_conditions_view",
]
